"""
summarize.py — Summarization engine (LLM-backed or extractive fallback).

If ANTHROPIC_API_KEY is set, uses Claude claude-sonnet-4-5 via urllib.
Otherwise uses a pure-Python extractive summarizer (no external deps).
"""

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any


# ── Constants ──────────────────────────────────────────────────────────────────

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
CLAUDE_MODEL = "claude-sonnet-4-5"
MAX_TOKENS = 1024

# Max subtitle chars to send to LLM (avoid huge prompts)
MAX_SUBTITLE_CHARS = 8000


# ── Subtitle text extraction ───────────────────────────────────────────────────


def subtitle_lines_to_text(lines: list[dict[str, Any]]) -> str:
    """Convert raw subtitle body entries to plain text."""
    texts = [entry.get("content", "").strip() for entry in lines if entry.get("content")]
    return "\n".join(texts)


def _truncate(text: str, max_chars: int = MAX_SUBTITLE_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n[... truncated for length ...]"


# ── Extractive fallback summarizer (no API key required) ──────────────────────


def _score_sentence(sentence: str, word_freq: dict[str, int]) -> float:
    """Score a sentence by summed word frequency (simple TF-style scoring)."""
    words = re.findall(r"[\w一-鿿]+", sentence.lower())
    if not words:
        return 0.0
    return sum(word_freq.get(w, 0) for w in words) / len(words)


def _word_frequencies(text: str) -> dict[str, int]:
    """Count word/character n-gram frequencies in text."""
    words = re.findall(r"[\w一-鿿]+", text.lower())
    freq: dict[str, int] = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    return freq


def extractive_summarize(text: str, top_n: int = 6) -> dict[str, Any]:
    """
    Simple extractive summarizer: picks top-N highest-scoring sentences.
    Works for both Chinese and English text.
    """
    # Split on punctuation or newlines
    raw_sentences = re.split(r"[。！？\n.!?]+", text)
    sentences = [s.strip() for s in raw_sentences if len(s.strip()) > 8]

    if not sentences:
        return {
            "summary": text[:300] if text else "(no content)",
            "key_points": [],
            "method": "extractive-fallback",
        }

    word_freq = _word_frequencies(text)
    scored = [(s, _score_sentence(s, word_freq)) for s in sentences]
    scored.sort(key=lambda x: x[1], reverse=True)

    top_sentences = [s for s, _ in scored[:top_n]]
    # Restore original order
    order_map = {s: i for i, s in enumerate(sentences)}
    top_sentences.sort(key=lambda s: order_map.get(s, 9999))

    summary = "。".join(top_sentences[:3]) + "。"
    key_points = [f"- {s}" for s in top_sentences]

    return {
        "summary": summary,
        "key_points": key_points,
        "method": "extractive-fallback",
    }


def extractive_combine_script(video_summaries: list[dict[str, Any]]) -> str:
    """
    Build a study script from multiple video summaries without an LLM.
    """
    lines = [
        "# 学习笔记 / Study Notes",
        "",
        f"共收录 {len(video_summaries)} 个视频的要点。",
        "",
    ]
    for i, vs in enumerate(video_summaries, 1):
        title = vs.get("title", f"视频 {i}")
        summary = vs.get("summary", {})
        lines.append(f"## {i}. {title}")
        lines.append("")
        if isinstance(summary, dict):
            lines.append(summary.get("summary", ""))
            lines.append("")
            for kp in summary.get("key_points", []):
                lines.append(kp)
        else:
            lines.append(str(summary))
        lines.append("")

    lines.append("---")
    lines.append("*生成方式: 提取式摘要（无需API密钥）*")
    return "\n".join(lines)


# ── Anthropic LLM summarizer ───────────────────────────────────────────────────


def _call_anthropic(api_key: str, prompt: str) -> str:
    """
    Call Claude claude-sonnet-4-5 and return the text response.
    Uses urllib — no external dependencies.
    """
    payload = json.dumps(
        {
            "model": CLAUDE_MODEL,
            "max_tokens": MAX_TOKENS,
            "messages": [{"role": "user", "content": prompt}],
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        ANTHROPIC_API_URL,
        data=payload,
        headers={
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
            return data["content"][0]["text"]
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Anthropic API HTTP {exc.code}: {body[:400]}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Anthropic API network error: {exc.reason}") from exc


def llm_summarize_video(api_key: str, title: str, subtitle_text: str) -> dict[str, Any]:
    """Use Claude to summarize a single video's subtitle text."""
    text = _truncate(subtitle_text)
    prompt = (
        f"你是一个学习助手。以下是B站视频《{title}》的字幕内容：\n\n"
        f"{text}\n\n"
        "请用中文输出：\n"
        "1. 一段简洁的摘要（3-5句话）\n"
        "2. 5个核心知识点（每点一句话，以「- 」开头）\n\n"
        "格式：\n摘要：\n<摘要内容>\n\n核心知识点：\n<知识点列表>"
    )
    response = _call_anthropic(api_key, prompt)

    # Parse the structured response
    summary_part = ""
    key_points: list[str] = []

    if "摘要：" in response and "核心知识点：" in response:
        parts = response.split("核心知识点：", 1)
        summary_part = parts[0].replace("摘要：", "").strip()
        kp_block = parts[1].strip()
        key_points = [
            line.strip()
            for line in kp_block.splitlines()
            if line.strip().startswith("-")
        ]
    else:
        summary_part = response.strip()

    return {
        "summary": summary_part,
        "key_points": key_points,
        "method": "claude-claude-sonnet-4-5",
    }


def llm_combine_script(
    api_key: str, video_summaries: list[dict[str, Any]]
) -> str:
    """Use Claude to write a cohesive study script across all videos."""
    combined_notes = []
    for vs in video_summaries:
        title = vs.get("title", "未知视频")
        s = vs.get("summary", {})
        if isinstance(s, dict):
            note = f"**{title}**\n摘要: {s.get('summary','')}\n" + "\n".join(
                s.get("key_points", [])
            )
        else:
            note = f"**{title}**\n{s}"
        combined_notes.append(note)

    notes_text = "\n\n".join(combined_notes)
    prompt = (
        "你是一个专业的知识整理助手。以下是用户收藏的多个B站视频的摘要和知识点：\n\n"
        f"{_truncate(notes_text, 6000)}\n\n"
        "请用中文撰写一份综合学习脚本，包括：\n"
        "1. 整体主题概述\n"
        "2. 各视频核心内容串联\n"
        "3. 综合学习建议\n\n"
        "格式要清晰，使用Markdown标题和列表。"
    )

    script = _call_anthropic(api_key, prompt)
    header = f"# 学习脚本 / Study Script\n\n*AI生成 · {len(video_summaries)} 个视频*\n\n"
    return header + script


# ── Public dispatch functions ──────────────────────────────────────────────────


def summarize_video(
    title: str,
    subtitle_lines: list[dict[str, Any]],
    api_key: str | None = None,
) -> dict[str, Any]:
    """
    Summarize a single video. Uses LLM if api_key is provided, else extractive.

    Returns dict with keys: title, summary (dict), method.
    """
    text = subtitle_lines_to_text(subtitle_lines)

    if not text.strip():
        return {
            "title": title,
            "summary": {"summary": "(no subtitle content)", "key_points": [], "method": "none"},
        }

    if api_key:
        try:
            result = llm_summarize_video(api_key, title, text)
        except RuntimeError as exc:
            print(f"[warn] LLM failed for '{title}': {exc}. Falling back to extractive.")
            result = extractive_summarize(text)
    else:
        result = extractive_summarize(text)

    return {"title": title, "summary": result}


def build_combined_script(
    video_summaries: list[dict[str, Any]],
    api_key: str | None = None,
) -> str:
    """
    Build a combined study script from per-video summary dicts.
    Uses LLM if api_key provided, else extractive combination.
    """
    if not video_summaries:
        return "# 学习脚本\n\n（没有视频内容）"

    if api_key:
        try:
            return llm_combine_script(api_key, video_summaries)
        except RuntimeError as exc:
            print(f"[warn] LLM script generation failed: {exc}. Using extractive fallback.")

    return extractive_combine_script(video_summaries)
