"""
bili_api.py — Bilibili API client using stdlib only (urllib).

Fetches favorite folders, video lists, and subtitles for a given user,
using their SESSDATA cookie for authentication.

Features:
  - Automatic retry with exponential backoff on transient network errors
  - Rate-limit politeness delay between requests
  - CJK-safe URL handling
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


# ── Constants ──────────────────────────────────────────────────────────────────

BASE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bilibili.com",
    "Accept": "application/json, text/plain, */*",
}

API_BASE = "https://api.bilibili.com"
REQUEST_DELAY = 0.6          # seconds between API calls (politeness)
MAX_RETRIES = 3              # retry count for transient errors
RETRY_BACKOFF = [2, 5, 10]  # wait seconds per retry attempt


# ── HTTP helpers ───────────────────────────────────────────────────────────────


def _make_headers(sessdata: str) -> dict[str, str]:
    """Return headers with authentication cookie."""
    return {**BASE_HEADERS, "Cookie": f"SESSDATA={sessdata}"}


def _get_json(
    url: str,
    headers: dict[str, str],
    timeout: int = 15,
    retries: int = MAX_RETRIES,
) -> dict[str, Any]:
    """
    Perform a GET request and return parsed JSON.
    Retries on network errors with exponential backoff.
    """
    req = urllib.request.Request(url, headers=headers)
    last_exc: Exception | None = None

    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            # Retry on 429 (rate limit) or 5xx server errors
            if exc.code == 429 or exc.code >= 500:
                wait = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
                time.sleep(wait)
                last_exc = RuntimeError(f"HTTP {exc.code} fetching {url}: {exc.reason}")
                continue
            raise RuntimeError(f"HTTP {exc.code} fetching {url}: {exc.reason}") from exc
        except urllib.error.URLError as exc:
            wait = RETRY_BACKOFF[min(attempt, len(RETRY_BACKOFF) - 1)]
            time.sleep(wait)
            last_exc = RuntimeError(f"Network error fetching {url}: {exc.reason}")
            continue
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON from {url}: {exc}") from exc

    raise last_exc or RuntimeError(f"Request failed after {retries} retries: {url}")


def _get_raw(url: str, timeout: int = 20) -> bytes:
    """Fetch raw bytes (used for subtitle JSON files hosted on CDN)."""
    req = urllib.request.Request(url, headers=BASE_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        raise RuntimeError(f"Error downloading {url}: {exc}") from exc


def _check_api(data: dict[str, Any], context: str) -> Any:
    """Validate Bilibili API envelope (code==0) and return data field."""
    code = data.get("code", -1)
    if code != 0:
        msg = data.get("message") or data.get("msg") or "unknown error"
        raise RuntimeError(f"Bilibili API error [{code}] in {context}: {msg}")
    return data.get("data")


# ── Public API functions ───────────────────────────────────────────────────────


def list_favorite_folders(sessdata: str) -> list[dict[str, Any]]:
    """
    Return all favorite folders created by the authenticated user.

    Each folder dict contains at minimum:
      id (int), title (str), media_count (int)
    """
    url = f"{API_BASE}/x/v3/fav/folder/created/list-all?up_mid=0&type=2"
    headers = _make_headers(sessdata)
    raw = _get_json(url, headers)
    folders_data = _check_api(raw, "list_favorite_folders")

    folders = folders_data.get("list") or []
    if not folders:
        # Try alternate key
        folders = folders_data if isinstance(folders_data, list) else []
    return folders


def list_videos_in_folder(
    sessdata: str, media_id: int, page_size: int = 20
) -> list[dict[str, Any]]:
    """
    Return all videos in a favorite folder, paginating automatically.

    Each video dict contains at minimum:
      id (bvid), title, intro, upper (uploader info), page (count)
    """
    headers = _make_headers(sessdata)
    all_videos: list[dict[str, Any]] = []
    page = 1

    while True:
        params = urllib.parse.urlencode(
            {"media_id": media_id, "pn": page, "ps": page_size, "platform": "web"}
        )
        url = f"{API_BASE}/x/v3/fav/resource/list?{params}"
        raw = _get_json(url, headers)
        data = _check_api(raw, f"list_videos_in_folder(page={page})")

        medias = data.get("medias") or []
        all_videos.extend(medias)

        has_more = data.get("has_more", False)
        if not has_more or not medias:
            break

        page += 1
        time.sleep(REQUEST_DELAY)

    return all_videos


def get_video_cid(sessdata: str, bvid: str) -> int | None:
    """
    Return the first cid (page) for a video, used to fetch subtitles.
    Returns None if the request fails.
    """
    params = urllib.parse.urlencode({"bvid": bvid})
    url = f"{API_BASE}/x/player/pagelist?{params}"
    headers = _make_headers(sessdata)
    try:
        raw = _get_json(url, headers)
        pages = _check_api(raw, f"get_video_cid({bvid})")
        if pages and isinstance(pages, list):
            return pages[0].get("cid")
    except RuntimeError:
        return None
    return None


def get_subtitle_urls(sessdata: str, bvid: str, cid: int) -> list[dict[str, Any]]:
    """
    Return subtitle entries for a video+cid combination.

    Each entry contains: lan (language code), lan_doc (display name),
    subtitle_url (CDN URL to the JSON subtitle file).
    """
    params = urllib.parse.urlencode({"bvid": bvid, "cid": cid})
    url = f"{API_BASE}/x/player/v2?{params}"
    headers = _make_headers(sessdata)
    raw = _get_json(url, headers)
    data = _check_api(raw, f"get_subtitle_urls({bvid}, {cid})")

    subtitle_info = data.get("subtitle") or {}
    return subtitle_info.get("subtitles") or []


def download_subtitle(subtitle_url: str) -> list[dict[str, Any]]:
    """
    Download and parse a subtitle JSON from the CDN URL.

    Returns list of body entries: [{from, to, content}, ...]
    Handles both https:// and protocol-relative (//...) URLs.
    """
    if subtitle_url.startswith("//"):
        subtitle_url = "https:" + subtitle_url

    raw = _get_raw(subtitle_url)
    payload = json.loads(raw)
    return payload.get("body") or []


def fetch_subtitles_for_video(
    sessdata: str, bvid: str, prefer_lang: str = "zh-CN"
) -> tuple[list[dict[str, Any]], str]:
    """
    High-level helper: fetch subtitle lines for a video.

    Returns (lines, language_code). Lines may be empty if no subtitle found.
    prefer_lang tries to pick the specified language first; falls back to first available.
    """
    cid = get_video_cid(sessdata, bvid)
    if cid is None:
        return [], ""

    time.sleep(REQUEST_DELAY)
    subtitle_entries = get_subtitle_urls(sessdata, bvid, cid)
    if not subtitle_entries:
        return [], ""

    # Pick preferred language or first available
    chosen = None
    for entry in subtitle_entries:
        if entry.get("lan") == prefer_lang:
            chosen = entry
            break
    if chosen is None:
        chosen = subtitle_entries[0]

    time.sleep(REQUEST_DELAY)
    lines = download_subtitle(chosen["subtitle_url"])
    return lines, chosen.get("lan", "")
