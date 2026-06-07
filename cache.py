"""
cache.py — Filesystem cache for subtitle downloads and per-video summaries.

Cache lives at ~/.bili-fav-cache/ keyed by bvid.
Each bvid has two slots:
  <bvid>.subtitle.json  — raw subtitle body lines (list[dict])
  <bvid>.summary.json   — summarization result dict

All operations are safe to call with no cache dir (first-run creates it).
Pass refresh=True to bypass cache reads (still writes updated entries).
"""

import json
import pathlib
from typing import Any


# ── Cache root ─────────────────────────────────────────────────────────────────

_CACHE_ROOT = pathlib.Path.home() / ".bili-fav-cache"


def _ensure_cache_dir() -> pathlib.Path:
    _CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    return _CACHE_ROOT


def _subtitle_path(bvid: str) -> pathlib.Path:
    return _CACHE_ROOT / f"{bvid}.subtitle.json"


def _summary_path(bvid: str) -> pathlib.Path:
    return _CACHE_ROOT / f"{bvid}.summary.json"


# ── Subtitle cache ─────────────────────────────────────────────────────────────

def get_cached_subtitle(bvid: str, refresh: bool = False) -> list[dict[str, Any]] | None:
    """
    Return cached subtitle lines for bvid, or None if not cached.
    Returns None when refresh=True (forces re-download).
    """
    if refresh:
        return None
    path = _subtitle_path(bvid)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return None


def save_subtitle_cache(bvid: str, lines: list[dict[str, Any]]) -> None:
    """Persist subtitle lines to cache."""
    _ensure_cache_dir()
    try:
        _subtitle_path(bvid).write_text(
            json.dumps(lines, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass  # cache write failure is non-fatal


# ── Summary cache ──────────────────────────────────────────────────────────────

def get_cached_summary(bvid: str, refresh: bool = False) -> dict[str, Any] | None:
    """
    Return cached summary dict for bvid, or None if not cached.
    Returns None when refresh=True.
    """
    if refresh:
        return None
    path = _summary_path(bvid)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return None


def save_summary_cache(bvid: str, summary: dict[str, Any]) -> None:
    """Persist summary dict to cache."""
    _ensure_cache_dir()
    try:
        _summary_path(bvid).write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


# ── Cache stats ────────────────────────────────────────────────────────────────

def cache_stats() -> dict[str, int]:
    """Return counts of cached subtitle and summary entries."""
    if not _CACHE_ROOT.exists():
        return {"subtitles": 0, "summaries": 0}
    subs = len(list(_CACHE_ROOT.glob("*.subtitle.json")))
    summs = len(list(_CACHE_ROOT.glob("*.summary.json")))
    return {"subtitles": subs, "summaries": summs}
