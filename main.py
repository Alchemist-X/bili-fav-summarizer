"""
main.py — CLI entry point for bili-fav-summarizer.

Usage:
  python3 main.py --demo                        Offline demo, no cookie/key needed
  python3 main.py --folder <media_id>           Summarize one favorite folder
  python3 main.py --folder-name "英语学习"       Select folder by name
  python3 main.py --all                         Summarize all favorite folders
  python3 main.py --all --limit 10              Only first 10 videos per folder
  python3 main.py --all --refresh               Bypass cache (re-download everything)

Env vars (optional for --demo):
  BILI_SESSDATA       Your Bilibili SESSDATA cookie value
  ANTHROPIC_API_KEY   Anthropic API key for LLM summaries
"""

import argparse
import json
import os
import pathlib
import sys
import time


OUT_DIR = pathlib.Path("out")
SAMPLE_SUBTITLE = pathlib.Path(__file__).parent / "sample" / "sample-subtitle.json"


# ── Helpers ────────────────────────────────────────────────────────────────────


def _ensure_out_dir() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)


def _write_file(path: pathlib.Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    from cli_ui import print_wrote
    print_wrote(str(path))


def _load_env() -> tuple[str | None, str | None]:
    """Return (BILI_SESSDATA, ANTHROPIC_API_KEY) from environment."""
    return os.environ.get("BILI_SESSDATA"), os.environ.get("ANTHROPIC_API_KEY")


def _safe_filename(title: str, bvid: str = "", max_len: int = 40) -> str:
    """Build a filesystem-safe filename component."""
    safe = "".join(c for c in title if c.isalnum() or c in "-_ ")[:max_len]
    if bvid:
        return f"{bvid}-{safe}".replace(" ", "_")
    return safe.replace(" ", "_")


# ── Demo mode ──────────────────────────────────────────────────────────────────


def run_demo() -> None:
    """
    Offline demo: loads bundled sample subtitle, runs extractive summarize,
    writes per-video JSON + combined script.md + report.html to out/.
    No network, no cookie, no API key required.
    """
    from cli_ui import (
        print_banner, print_section, print_ok, print_info,
        print_progress, print_summary_box, bold, cyan, dim,
    )
    from summarize import summarize_video, build_combined_script
    from report import generate_report

    print_banner()
    print_section("Demo Mode (offline · no cookie/key needed)")

    if not SAMPLE_SUBTITLE.exists():
        from cli_ui import print_err
        print_err(f"Sample file not found: {SAMPLE_SUBTITLE}")
        sys.exit(1)

    with SAMPLE_SUBTITLE.open(encoding="utf-8") as f:
        subtitle_payload = json.load(f)

    lines = subtitle_payload.get("body", [])
    print_info(f"Loaded sample subtitle: {bold(str(len(lines)))} lines from {dim(SAMPLE_SUBTITLE.name)}")

    demo_videos = [
        {
            "title": "Python异步编程入门（示例视频）",
            "bvid": "BV1demo0001",
            "subtitle_lines": lines,
        },
        {
            "title": "asyncio高级用法：Task与gather（示例）",
            "bvid": "BV1demo0002",
            "subtitle_lines": lines,  # reuse same sample content
        },
        {
            "title": "无字幕示例视频（演示跳过逻辑）",
            "bvid": "BV1demo0003",
            "subtitle_lines": [],
        },
    ]

    _ensure_out_dir()

    print_section("Processing Videos")
    results: list[dict] = []
    no_subtitle_list: list[str] = []

    for i, v in enumerate(demo_videos, 1):
        print_progress(i, len(demo_videos), v["title"], v["bvid"])
        vs = summarize_video(
            title=v["title"],
            subtitle_lines=v["subtitle_lines"],
            api_key=None,
        )
        vs["bvid"] = v["bvid"]

        s = vs.get("summary", {})
        has_content = isinstance(s, dict) and s.get("summary") not in (
            "(no subtitle content)", "(no subtitle)", ""
        )

        if has_content:
            print_ok(f"{dim(s.get('method', ''))} · {s.get('reading_time', '')} read")
            if s.get("tags"):
                print_info("Tags: " + ", ".join(s["tags"][:5]))
        else:
            from cli_ui import print_skip
            print_skip("No subtitle — skipped from summarization")
            no_subtitle_list.append(v["title"])

        results.append(vs)

    print_section("Writing Output")

    # Per-video markdown files
    for vs in results:
        _write_per_video_md(vs)

    # Combined script.md
    script = build_combined_script(results, api_key=None)
    script_path = OUT_DIR / "script.md"
    _write_file(script_path, script)

    # HTML report
    html_report = generate_report(results, title="Bilibili 学习笔记 — Demo", folder_name="Demo Run")
    report_path = OUT_DIR / "report.html"
    _write_file(report_path, html_report)

    # Per-video JSON (for inspection)
    for vs in results:
        bvid = vs.get("bvid", "")
        title = vs.get("title", "video")
        fname = _safe_filename(title, bvid) + ".json"
        _write_file(OUT_DIR / fname, json.dumps(vs, ensure_ascii=False, indent=2))

    if no_subtitle_list:
        print_section("No-Subtitle Videos")
        for t in no_subtitle_list:
            from cli_ui import print_skip
            print_skip(t)

    print_summary_box(
        total=len(demo_videos),
        summarized=len(demo_videos) - len(no_subtitle_list),
        no_subtitle=len(no_subtitle_list),
        skipped_cache=0,
        errors=0,
        out_files=["out/script.md", "out/report.html"],
    )

    # Quick preview of script
    print_section("script.md preview (first 20 lines)")
    for line in script.splitlines()[:20]:
        print(f"  {line}")
    print()

    script_size = script_path.stat().st_size
    report_size = report_path.stat().st_size
    print_info(f"script.md  — {script_size:,} bytes")
    print_info(f"report.html — {report_size:,} bytes")
    print()


def _write_per_video_md(vs: dict) -> None:
    """Write a per-video markdown summary file."""
    title = vs.get("title", "video")
    bvid = vs.get("bvid", "")
    s = vs.get("summary", {})

    lines = [f"# {title}", ""]
    if bvid:
        lines += [f"> [▶ 在B站观看](https://www.bilibili.com/video/{bvid})", ""]

    if isinstance(s, dict):
        rt = s.get("reading_time", "")
        method = s.get("method", "")
        if rt or method:
            meta = " · ".join(x for x in [f"⏱ {rt}" if rt else "", f"方法: {method}" if method else ""] if x)
            lines += [f"*{meta}*", ""]

        summary_text = s.get("summary", "")
        if summary_text and summary_text not in ("(no subtitle content)", "(no subtitle)"):
            lines += ["## 摘要", "", summary_text, ""]

        kps = s.get("key_points", [])
        if kps:
            lines += ["## 核心知识点", ""]
            lines.extend(kps)
            lines.append("")

        tags = s.get("tags", [])
        if tags:
            lines += [f"**标签:** " + " ".join(f"`{t}`" for t in tags), ""]
    else:
        lines += [str(s), ""]

    content = "\n".join(lines)
    safe = _safe_filename(title, bvid) + ".md"
    path = OUT_DIR / safe
    _write_file(path, content)


# ── Video processing pipeline ──────────────────────────────────────────────────


def _process_videos(
    videos: list[dict],
    sessdata: str,
    api_key: str | None,
    refresh: bool = False,
    limit: int | None = None,
) -> tuple[list[dict], list[str], list[str]]:
    """
    Fetch subtitles and summarize a list of video dicts.

    Returns (results, no_subtitle_titles, error_titles).
    """
    from bili_api import fetch_subtitles_for_video
    from summarize import summarize_video
    from cache import get_cached_subtitle, save_subtitle_cache, get_cached_summary, save_summary_cache
    from cli_ui import print_progress, print_ok, print_skip, print_err, print_info, bold, dim

    if limit is not None:
        videos = videos[:limit]

    results: list[dict] = []
    no_subtitle_list: list[str] = []
    error_list: list[str] = []
    cache_hits = 0
    total = len(videos)

    for i, video in enumerate(videos, 1):
        bvid = video.get("bvid") or video.get("id") or ""
        title = video.get("title", f"video-{i}")

        print_progress(i, total, title, bvid)

        if not bvid:
            print_err("No BVID found — skipping")
            error_list.append(title)
            continue

        try:
            # ── Check summary cache first ──────────────────────────────────
            cached_vs = get_cached_summary(bvid, refresh=refresh)
            if cached_vs is not None:
                cached_vs["title"] = title  # ensure title is fresh
                results.append(cached_vs)
                cache_hits += 1
                s = cached_vs.get("summary", {})
                rt = s.get("reading_time", "") if isinstance(s, dict) else ""
                print_ok(f"from cache · {dim(rt + ' read') if rt else ''}")
                continue

            # ── Fetch subtitle (with subtitle cache) ───────────────────────
            lines = get_cached_subtitle(bvid, refresh=refresh)
            lang = ""
            from_cache = False

            if lines is not None:
                from_cache = True
            else:
                lines, lang = fetch_subtitles_for_video(sessdata, bvid)
                if lines:
                    save_subtitle_cache(bvid, lines)

            time.sleep(0.1)  # small politeness delay even when cached

            if not lines:
                print_skip(f"No subtitle (lang={lang or 'none'})")
                vs = {
                    "title": title,
                    "bvid": bvid,
                    "summary": {
                        "summary": "(no subtitle)",
                        "key_points": [],
                        "tags": [],
                        "reading_time": "< 1 min",
                        "method": "none",
                    },
                }
                results.append(vs)
                no_subtitle_list.append(title)
                save_summary_cache(bvid, vs)
                continue

            cache_tag = " (subtitle cached)" if from_cache else f" lang={lang}"
            print_info(f"{len(lines)} subtitle lines{cache_tag}")

            # ── Summarize ──────────────────────────────────────────────────
            vs = summarize_video(title=title, subtitle_lines=lines, api_key=api_key)
            vs["bvid"] = bvid

            s = vs.get("summary", {})
            rt = s.get("reading_time", "") if isinstance(s, dict) else ""
            method = s.get("method", "") if isinstance(s, dict) else ""
            tags = s.get("tags", []) if isinstance(s, dict) else []

            print_ok(f"{dim(method)} · {rt} read")
            if tags:
                print_info("Tags: " + ", ".join(tags[:5]))

            results.append(vs)
            save_summary_cache(bvid, vs)

        except RuntimeError as exc:
            print_err(f"{exc}")
            error_vs = {
                "title": title,
                "bvid": bvid,
                "summary": {
                    "summary": f"Error: {exc}",
                    "key_points": [],
                    "tags": [],
                    "reading_time": "< 1 min",
                    "method": "error",
                },
            }
            results.append(error_vs)
            error_list.append(title)

    return results, no_subtitle_list, error_list


def _finish_run(
    results: list[dict],
    no_subtitle_list: list[str],
    error_list: list[str],
    api_key: str | None,
    folder_name: str = "",
) -> None:
    """Write all output files and print summary box."""
    from summarize import build_combined_script
    from report import generate_report
    from cli_ui import print_section, print_skip, print_summary_box, print_info

    _ensure_out_dir()

    # Per-video markdown + JSON
    for vs in results:
        _write_per_video_md(vs)
        bvid = vs.get("bvid", "")
        title = vs.get("title", "video")
        fname = _safe_filename(title, bvid) + ".json"
        _write_file(OUT_DIR / fname, json.dumps(vs, ensure_ascii=False, indent=2))

    # Combined script
    script = build_combined_script(results, api_key=api_key)
    script_path = OUT_DIR / "script.md"
    _write_file(script_path, script)

    # HTML report
    page_title = f"Bilibili 学习笔记{' — ' + folder_name if folder_name else ''}"
    html_report = generate_report(results, title=page_title, folder_name=folder_name)
    report_path = OUT_DIR / "report.html"
    _write_file(report_path, html_report)

    # No-subtitle list
    if no_subtitle_list:
        print_section("Videos without subtitles")
        for t in no_subtitle_list:
            print_skip(t)

    summarized = len(results) - len(no_subtitle_list) - len(error_list)
    from_cache = 0  # would need to track separately; approximated as 0 here

    print_summary_box(
        total=len(results),
        summarized=summarized,
        no_subtitle=len(no_subtitle_list),
        skipped_cache=from_cache,
        errors=len(error_list),
        out_files=["out/script.md", "out/report.html"],
    )

    script_size = script_path.stat().st_size
    report_size = report_path.stat().st_size
    print_info(f"script.md  — {script_size:,} bytes")
    print_info(f"report.html — {report_size:,} bytes")


# ── Live modes ─────────────────────────────────────────────────────────────────


def run_folder(media_id: int, refresh: bool = False, limit: int | None = None) -> None:
    """Summarize all videos in a specific favorite folder."""
    from bili_api import list_videos_in_folder
    from cli_ui import print_banner, print_section, print_info, bold

    print_banner()

    sessdata, api_key = _load_env()
    if not sessdata:
        from cli_ui import print_err
        print_err("BILI_SESSDATA env var is required.")
        sys.exit(1)

    print_section(f"Folder media_id={media_id}")
    print_info(f"Fetching video list…")
    videos = list_videos_in_folder(sessdata, media_id)
    print_info(f"Found {bold(str(len(videos)))} videos" + (f" · limit={limit}" if limit else ""))

    _ensure_out_dir()
    results, no_sub, errors = _process_videos(videos, sessdata, api_key, refresh=refresh, limit=limit)

    print_section("Writing Output")
    _finish_run(results, no_sub, errors, api_key, folder_name=f"Folder {media_id}")


def run_folder_by_name(folder_name: str, refresh: bool = False, limit: int | None = None) -> None:
    """Select a favorite folder by name and summarize it."""
    from bili_api import list_favorite_folders, list_videos_in_folder
    from cli_ui import print_banner, print_section, print_info, print_err, bold

    print_banner()

    sessdata, api_key = _load_env()
    if not sessdata:
        print_err("BILI_SESSDATA env var is required.")
        sys.exit(1)

    print_section("Searching folders")
    folders = list_favorite_folders(sessdata)
    print_info(f"Found {len(folders)} folders")

    # Case-insensitive match
    match = next(
        (f for f in folders if folder_name.lower() in f.get("title", "").lower()),
        None,
    )
    if match is None:
        print_err(f"No folder matching '{folder_name}'. Available folders:")
        for f in folders:
            print_info(f"  [{f.get('id')}] {f.get('title')} ({f.get('media_count', 0)} videos)")
        sys.exit(1)

    media_id = match["id"]
    title = match.get("title", str(media_id))
    print_info(f"Matched: {bold(title)} (id={media_id})")

    videos = list_videos_in_folder(sessdata, media_id)
    print_info(f"Found {bold(str(len(videos)))} videos" + (f" · limit={limit}" if limit else ""))

    _ensure_out_dir()
    results, no_sub, errors = _process_videos(videos, sessdata, api_key, refresh=refresh, limit=limit)

    print_section("Writing Output")
    _finish_run(results, no_sub, errors, api_key, folder_name=title)


def run_all_folders(refresh: bool = False, limit: int | None = None) -> None:
    """Summarize videos across all favorite folders."""
    from bili_api import list_favorite_folders, list_videos_in_folder
    from cli_ui import print_banner, print_section, print_info, print_err, bold, dim

    print_banner()

    sessdata, api_key = _load_env()
    if not sessdata:
        print_err("BILI_SESSDATA env var is required.")
        sys.exit(1)

    print_section("All Favorite Folders")
    print_info("Fetching folder list…")
    folders = list_favorite_folders(sessdata)
    print_info(f"Found {bold(str(len(folders)))} folders:")
    for f in folders:
        count = f.get("media_count", 0)
        print_info(f"  [{f.get('id')}] {f.get('title')} — {dim(str(count) + ' videos')}")
    print()

    _ensure_out_dir()
    all_results: list[dict] = []
    all_no_sub: list[str] = []
    all_errors: list[str] = []

    for folder in folders:
        media_id = folder.get("id")
        folder_title = folder.get("title", str(media_id))
        count = folder.get("media_count", 0)

        if count == 0:
            from cli_ui import print_skip
            print_skip(f"Empty folder: {folder_title}")
            continue

        print_section(f"Folder: {folder_title} ({count} videos)")
        videos = list_videos_in_folder(sessdata, media_id)
        results, no_sub, errors = _process_videos(
            videos, sessdata, api_key, refresh=refresh, limit=limit
        )
        all_results.extend(results)
        all_no_sub.extend(no_sub)
        all_errors.extend(errors)

        # Per-folder JSON bundle
        folder_safe = _safe_filename(folder_title, str(media_id))
        bundle_path = OUT_DIR / f"folder-{folder_safe}.json"
        _write_file(
            bundle_path,
            json.dumps({"folder": folder_title, "videos": results}, ensure_ascii=False, indent=2),
        )

    print_section("Writing Combined Output")
    _finish_run(all_results, all_no_sub, all_errors, api_key, folder_name="All Folders")


# ── Main ────────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize Bilibili favorited videos and generate a study script + HTML report.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 main.py --demo                         Offline demo, no credentials needed
  python3 main.py --folder 12345678              Summarize specific folder by ID
  python3 main.py --folder-name "英语学习"        Summarize folder by name
  python3 main.py --all                          Summarize all favorite folders
  python3 main.py --all --limit 5                Only process first 5 videos per folder
  python3 main.py --folder 12345678 --refresh    Re-download everything (bypass cache)

Environment variables:
  BILI_SESSDATA       Required for --folder/--all (your Bilibili SESSDATA cookie)
  ANTHROPIC_API_KEY   Optional (enables Claude LLM summaries; falls back to TextRank)
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
        help="Summarize videos in a specific favorite folder by numeric ID",
    )
    group.add_argument(
        "--folder-name",
        metavar="NAME",
        help="Summarize videos in a folder matching the given name (case-insensitive substring)",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Summarize videos across all favorite folders",
    )

    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Bypass the subtitle/summary cache and re-download everything",
    )
    parser.add_argument(
        "--limit",
        type=int,
        metavar="N",
        help="Only process the first N videos (useful for testing)",
    )

    args = parser.parse_args()

    try:
        if args.demo:
            run_demo()
        elif args.folder:
            run_folder(args.folder, refresh=args.refresh, limit=args.limit)
        elif args.folder_name:
            run_folder_by_name(args.folder_name, refresh=args.refresh, limit=args.limit)
        elif args.all:
            run_all_folders(refresh=args.refresh, limit=args.limit)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)
    except RuntimeError as exc:
        from cli_ui import print_err
        print_err(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()
