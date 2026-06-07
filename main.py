"""
main.py — CLI entry point for bili-fav-summarizer.

Usage:
  python3 main.py --demo                   # offline demo, no cookie/key needed
  python3 main.py --folder <media_id>      # summarize one favorite folder
  python3 main.py --all                    # summarize all favorite folders

Env vars (optional for --demo):
  BILI_SESSDATA       Your Bilibili SESSDATA cookie value
  ANTHROPIC_API_KEY   Anthropic API key for LLM summaries
"""

import argparse
import json
import os
import pathlib
import sys


OUT_DIR = pathlib.Path("out")
SAMPLE_SUBTITLE = pathlib.Path(__file__).parent / "sample" / "sample-subtitle.json"


# ── Helpers ────────────────────────────────────────────────────────────────────


def _ensure_out_dir() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)


def _write_file(path: pathlib.Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    print(f"  [wrote] {path}")


def _load_env() -> tuple[str | None, str | None]:
    """Return (BILI_SESSDATA, ANTHROPIC_API_KEY) from environment."""
    return os.environ.get("BILI_SESSDATA"), os.environ.get("ANTHROPIC_API_KEY")


def _print_summary_preview(video_summary: dict) -> None:
    title = video_summary.get("title", "?")
    s = video_summary.get("summary", {})
    method = s.get("method", "?")
    print(f"  [{method}] {title[:60]}")
    for kp in (s.get("key_points") or [])[:3]:
        print(f"    {kp}")


# ── Demo mode ──────────────────────────────────────────────────────────────────


def run_demo() -> None:
    """
    Offline demo: loads bundled sample subtitle, runs extractive summarize,
    writes per-video JSON + combined script.md to out/.
    No network, no cookie, no API key required.
    """
    from summarize import summarize_video, build_combined_script

    print("=== bili-fav-summarizer DEMO (offline, no cookie/key needed) ===")
    print()

    if not SAMPLE_SUBTITLE.exists():
        print(f"[error] Sample file not found: {SAMPLE_SUBTITLE}", file=sys.stderr)
        sys.exit(1)

    with SAMPLE_SUBTITLE.open(encoding="utf-8") as f:
        subtitle_payload = json.load(f)

    lines = subtitle_payload.get("body", [])
    print(f"Loaded sample subtitle: {len(lines)} lines from {SAMPLE_SUBTITLE.name}")
    print()

    demo_title = "Python异步编程入门（示例视频）"
    print(f"Summarizing: 《{demo_title}》 ...")
    video_summary = summarize_video(
        title=demo_title,
        subtitle_lines=lines,
        api_key=None,  # extractive fallback
    )

    _print_summary_preview(video_summary)
    print()

    _ensure_out_dir()

    # Write per-video JSON
    video_json_path = OUT_DIR / "demo-video-summary.json"
    _write_file(video_json_path, json.dumps(video_summary, ensure_ascii=False, indent=2))

    # Build + write combined script
    script = build_combined_script([video_summary], api_key=None)
    script_path = OUT_DIR / "script.md"
    _write_file(script_path, script)

    print()
    print("── out/script.md preview (first 20 lines) ──────────────────────")
    for line in script.splitlines()[:20]:
        print(line)
    print("────────────────────────────────────────────────────────────────")
    print()
    print("Demo complete. Check out/ for full output.")


# ── Live modes ─────────────────────────────────────────────────────────────────


def _process_videos(
    videos: list[dict],
    sessdata: str,
    api_key: str | None,
) -> list[dict]:
    """Fetch subtitles and summarize a list of video dicts from the API."""
    from bili_api import fetch_subtitles_for_video
    from summarize import summarize_video

    results = []
    total = len(videos)

    for i, video in enumerate(videos, 1):
        bvid = video.get("bvid") or video.get("id") or ""
        title = video.get("title", f"video-{i}")
        print(f"  [{i}/{total}] {title[:50]} ({bvid})")

        if not bvid:
            print("    [skip] No BVID found")
            continue

        try:
            lines, lang = fetch_subtitles_for_video(sessdata, bvid)
            if not lines:
                print(f"    [no subtitle] language: {lang or 'none'}")
                vs = {"title": title, "bvid": bvid, "summary": {"summary": "(no subtitle)", "key_points": [], "method": "none"}}
            else:
                print(f"    [subtitle] {len(lines)} lines, lang={lang}")
                vs = summarize_video(title=title, subtitle_lines=lines, api_key=api_key)
                vs["bvid"] = bvid

            results.append(vs)
            _print_summary_preview(vs)

        except RuntimeError as exc:
            print(f"    [error] {exc}")
            results.append({"title": title, "bvid": bvid, "summary": {"summary": f"Error: {exc}", "key_points": [], "method": "error"}})

    return results


def run_folder(media_id: int) -> None:
    """Summarize all videos in a specific favorite folder."""
    from bili_api import list_videos_in_folder
    from summarize import build_combined_script

    sessdata, api_key = _load_env()
    if not sessdata:
        print("[error] BILI_SESSDATA env var is required.", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching videos in folder media_id={media_id} ...")
    videos = list_videos_in_folder(sessdata, media_id)
    print(f"Found {len(videos)} videos.")
    print()

    _ensure_out_dir()
    results = _process_videos(videos, sessdata, api_key)

    # Write per-video summaries
    for vs in results:
        safe_title = "".join(c for c in vs.get("title", "video") if c.isalnum() or c in "-_ ")[:40]
        bvid = vs.get("bvid", "")
        fname = f"{bvid}-{safe_title}.json".replace(" ", "_")
        _write_file(OUT_DIR / fname, json.dumps(vs, ensure_ascii=False, indent=2))

    # Write combined script
    script = build_combined_script(results, api_key=api_key)
    _write_file(OUT_DIR / "script.md", script)

    print(f"\nDone. {len(results)} videos processed. See out/script.md")


def run_all_folders() -> None:
    """Summarize videos across all favorite folders."""
    from bili_api import list_favorite_folders, list_videos_in_folder
    from summarize import build_combined_script

    sessdata, api_key = _load_env()
    if not sessdata:
        print("[error] BILI_SESSDATA env var is required.", file=sys.stderr)
        sys.exit(1)

    print("Fetching all favorite folders ...")
    folders = list_favorite_folders(sessdata)
    print(f"Found {len(folders)} folders:")
    for f in folders:
        print(f"  [{f.get('id')}] {f.get('title')} ({f.get('media_count', 0)} videos)")
    print()

    _ensure_out_dir()
    all_results: list[dict] = []

    for folder in folders:
        media_id = folder.get("id")
        folder_title = folder.get("title", str(media_id))
        count = folder.get("media_count", 0)

        if count == 0:
            print(f"Skipping empty folder: {folder_title}")
            continue

        print(f"\n── Folder: 《{folder_title}》 ({count} videos) ──")
        videos = list_videos_in_folder(sessdata, media_id)
        results = _process_videos(videos, sessdata, api_key)
        all_results.extend(results)

        # Per-folder JSON
        folder_safe = "".join(c for c in folder_title if c.isalnum() or c in "-_ ")[:30]
        fname = f"folder-{media_id}-{folder_safe}.json".replace(" ", "_")
        _write_file(
            OUT_DIR / fname,
            json.dumps({"folder": folder_title, "videos": results}, ensure_ascii=False, indent=2),
        )

    script = build_combined_script(all_results, api_key=api_key)
    _write_file(OUT_DIR / "script.md", script)

    print(f"\nDone. {len(all_results)} total videos processed. See out/script.md")


# ── Main ────────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize Bilibili favorited videos and generate a study script.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 main.py --demo                    Offline demo, no credentials needed
  python3 main.py --folder 12345678         Summarize specific folder
  python3 main.py --all                     Summarize all favorite folders

Environment variables:
  BILI_SESSDATA       Required for --folder/--all (your Bilibili SESSDATA cookie)
  ANTHROPIC_API_KEY   Optional (enables Claude LLM summaries; falls back to extractive)
        """,
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--demo",
        action="store_true",
        help="Run offline demo with bundled sample subtitle (no cookie/key needed)",
    )
    group.add_argument(
        "--folder",
        type=int,
        metavar="MEDIA_ID",
        help="Summarize videos in a specific favorite folder",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Summarize videos across all favorite folders",
    )

    args = parser.parse_args()

    try:
        if args.demo:
            run_demo()
        elif args.folder:
            run_folder(args.folder)
        elif args.all:
            run_all_folders()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
    except RuntimeError as exc:
        print(f"\n[error] {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
