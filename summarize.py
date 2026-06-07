"""
summarize.py — Summarization engine (LLM-backed or extractive fallback).

If ANTHROPIC_API_KEY is set, uses Claude claude-sonnet-4-5 via urllib.
Otherwise uses a pure-Python TextRank-style extractive summarizer (no external deps).

CJK-aware sentence splitting handles Chinese, Japanese, and mixed text.
"""

import json
import math
import os
import re
import time
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

# Approximate reading speed (characters per minute for Chinese, words per min for English)
CJK_READ_CPM = 350
EN_READ_WPM = 200

# TextRank damping factor and iterations
_TR_DAMPING = 0.85
_TR_ITERATIONS = 20
_TR_MIN_SCORE_DIFF = 1e-5


# ── Subtitle text extraction ───────────────────────────────────────────────────


def subtitle_lines_to_text(lines: list[dict[str, Any]]) -> str:
    """Convert raw subtitle body entries to plain text."""
    texts = [entry.get("content", "").strip() for entry in lines if entry.get("content")]
    return "\n".join(texts)


def _truncate(text: str, max_chars: int = MAX_SUBTITLE_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n[... truncated for length ...]"


# ── CJK-aware sentence splitting ───────────────────────────────────────────────

_CJK_PUNCT = r"。！？；!?;"
_EN_PUNCT = r"\.!?\?"
_SPLIT_RE = re.compile(rf"(?<=[{_CJK_PUNCT}])|(?<=[{_EN_PUNCT}])\s+")


def _split_sentences(text: str) -> list[str]:
    """
    Split text into sentences, handling CJK (。！？；) and Latin (. ! ?) punctuation.
    Deduplicates consecutive identical subtitle lines (common in Bilibili).
    """
    # Merge subtitle lines, removing exact duplicates adjacent to each other
    raw_lines = text.split("\n")
    deduped: list[str] = []
    prev = None
    for line in raw_lines:
        line = line.strip()
        if line and line != prev:
            deduped.append(line)
            prev = line
    merged = " ".join(deduped)

    # Split on CJK / Latin sentence boundaries
    parts = _SPLIT_RE.split(merged)
    return [p.strip() for p in parts if len(p.strip()) > 6]


# ── Word/character frequency ───────────────────────────────────────────────────

_STOPWORDS = frozenset([
    # Chinese stopwords
    "的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都",
    "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会",
    "着", "没有", "看", "好", "自己", "这", "那", "来", "他", "她", "它",
    "们", "这个", "那个", "这些", "那些", "可以", "就是", "但是", "因为",
    "所以", "如果", "虽然", "然后", "还是", "其实", "已经", "非常",
    # English stopwords
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "to", "of", "in", "on", "at", "by",
    "for", "with", "this", "that", "it", "we", "you", "he", "she", "they",
    "and", "or", "but", "so", "if", "as", "from", "not", "no", "also",
])


def _tokenize(text: str) -> list[str]:
    """
    Tokenize text into meaningful units, filtering stopwords.

    For CJK text: extract runs of 2+ CJK characters (bigrams / words).
    For Latin text: words of 2+ characters.
    Single CJK characters are too ambiguous to be useful keywords.
    """
    # CJK word-like runs (2+ chars) and Latin words (2+ chars)
    tokens = re.findall(r"[一-鿿぀-ヿ가-힯]{2,}|[a-zA-Z]{2,}", text)
    return [t.lower() for t in tokens if t.lower() not in _STOPWORDS]


def _word_frequencies(tokens: list[str]) -> dict[str, float]:
    """Compute normalized TF for a list of tokens."""
    freq: dict[str, int] = {}
    for t in tokens:
        freq[t] = freq.get(t, 0) + 1
    max_f = max(freq.values()) if freq else 1
    return {w: c / max_f for w, c in freq.items()}


# ── TextRank-style sentence ranking ───────────────────────────────────────────


def _sentence_similarity(s1_tokens: set[str], s2_tokens: set[str]) -> float:
    """Cosine-like similarity between two token sets (Jaccard with length penalty)."""
    if not s1_tokens or not s2_tokens:
        return 0.0
    intersection = len(s1_tokens & s2_tokens)
    if intersection == 0:
        return 0.0
    # Log-normalization discourages very short sentences getting high similarity
    denom = math.log(len(s1_tokens) + 1) + math.log(len(s2_tokens) + 1)
    return intersection / denom if denom > 0 else 0.0


def _textrank_scores(sentences: list[str]) -> list[float]:
    """
    Compute TextRank scores for each sentence.
    Returns a list of scores in the same order as `sentences`.
    """
    n = len(sentences)
    if n == 0:
        return []
    if n == 1:
        return [1.0]

    # Tokenize each sentence once
    token_sets = [set(_tokenize(s)) for s in sentences]

    # Build similarity matrix
    sim: list[list[float]] = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            s = _sentence_similarity(token_sets[i], token_sets[j])
            sim[i][j] = s
            sim[j][i] = s

    # Initialize scores
    scores = [1.0 / n] * n

    # Power-iterate TextRank
    for _ in range(_TR_ITERATIONS):
        new_scores = [0.0] * n
        for i in range(n):
            rank_sum = 0.0
            for j in range(n):
                if j == i:
                    continue
                out_weight = sum(sim[j])
                if out_weight > 0:
                    rank_sum += sim[j][i] / out_weight * scores[j]
            new_scores[i] = (1 - _TR_DAMPING) / n + _TR_DAMPING * rank_sum

        # Check convergence
        diff = sum(abs(new_scores[i] - scores[i]) for i in range(n))
        scores = new_scores
        if diff < _TR_MIN_SCORE_DIFF:
            break

    return scores


# ── Keyword extraction ─────────────────────────────────────────────────────────


def extract_keywords(text: str, top_n: int = 8) -> list[str]:
    """
    Extract top-N keywords from text using TF-IDF-style scoring.
    Works for CJK and Latin text using stdlib only.
    """
    tokens = _tokenize(text)
    if not tokens:
        return []

    freq: dict[str, int] = {}
    for t in tokens:
        freq[t] = freq.get(t, 0) + 1

    # Bonus for longer tokens (more specific terms)
    scored = {
        w: c * (1 + 0.3 * min(len(w), 6))
        for w, c in freq.items()
    }

    sorted_kw = sorted(scored.items(), key=lambda x: x[1], reverse=True)
    return [w for w, _ in sorted_kw[:top_n]]


# ── Reading time estimation ────────────────────────────────────────────────────


def estimate_reading_time(text: str) -> str:
    """
    Estimate reading time for text.
    Returns a human-readable string like '2 min' or '< 1 min'.
    Uses CJK reading speed for predominantly CJK text.
    """
    cjk_chars = len(re.findall(r"[一-鿿぀-ヿ]", text))
    total_chars = len(text.replace(" ", "").replace("\n", ""))

    if total_chars == 0:
        return "< 1 min"

    is_cjk_dominant = cjk_chars / total_chars > 0.4

    if is_cjk_dominant:
        minutes = cjk_chars / CJK_READ_CPM
    else:
        words = len(re.findall(r"\b\w+\b", text))
        minutes = words / EN_READ_WPM

    if minutes < 1:
        return "< 1 min"
    return f"{round(minutes)} min"


# ── Extractive fallback summarizer ────────────────────────────────────────────


def extractive_summarize(text: str, top_n: int = 6) -> dict[str, Any]:
    """
    TextRank-style extractive summarizer.

    Picks the top-N highest-ranked sentences while preserving original order.
    Extracts keywords and estimates reading time.
    Works for both Chinese and English text (CJK-aware splitting).
    """
    sentences = _split_sentences(text)

    if not sentences:
        return {
            "summary": text[:300] if text else "(no content)",
            "key_points": [],
            "tags": [],
            "reading_time": "< 1 min",
            "method": "extractive-textrank",
        }

    # TextRank scoring
    scores = _textrank_scores(sentences)
    indexed = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)
    top_indices = sorted([idx for idx, _ in indexed[:top_n]])
    top_sentences = [sentences[i] for i in top_indices]

    # Summary = top 3 sentences; key_points = all top_n
    summary_sentences = top_sentences[:3]
    # Use CJK period where text is CJK-dominant, else period+space
    cjk_count = sum(
        1 for c in text if "一" <= c <= "鿿"
    )
    joiner = "。" if cjk_count > len(text) * 0.3 else ". "
    summary = joiner.join(summary_sentences)
    if cjk_count > len(text) * 0.3 and not summary.endswith("。"):
        summary += "。"

    key_points = [f"- {s}" for s in top_sentences]
    tags = extract_keywords(text, top_n=8)
    reading_time = estimate_reading_time(text)

    return {
        "summary": summary,
        "key_points": key_points,
        "tags": tags,
        "reading_time": reading_time,
        "method": "extractive-textrank",
    }


def extractive_combine_script(video_summaries: list[dict[str, Any]]) -> str:
    """
    Build a study script from multiple video summaries without an LLM.
    Includes a table of contents and per-video anchor links.
    """
    lines = [
        "# 学习笔记 / Study Notes",
        "",
        f"> 共收录 **{len(video_summaries)}** 个视频的要点。",
        "",
        "---",
        "",
        "## 目录 / Table of Contents",
        "",
    ]

    # TOC
    for i, vs in enumerate(video_summaries, 1):
        title = vs.get("title", f"视频 {i}")
        bvid = vs.get("bvid", "")
        anchor = re.sub(r"[^\w\-]", "-", title.lower())[:40]
        bvid_link = f" ([{bvid}](https://www.bilibili.com/video/{bvid}))" if bvid else ""
        reading_time = ""
        s = vs.get("summary", {})
        if isinstance(s, dict) and s.get("reading_time"):
            reading_time = f" · {s['reading_time']} read"
        lines.append(f"{i}. [{title}](#{anchor}){bvid_link}{reading_time}")

    lines += ["", "---", ""]

    # Per-video sections
    for i, vs in enumerate(video_summaries, 1):
        title = vs.get("title", f"视频 {i}")
        bvid = vs.get("bvid", "")
        anchor = re.sub(r"[^\w\-]", "-", title.lower())[:40]
        s = vs.get("summary", {})

        lines.append(f"## {i}. {title} {{#{anchor}}}")
        lines.append("")

        if bvid:
            lines.append(f"> [▶ 在B站观看](https://www.bilibili.com/video/{bvid})")
            lines.append("")

        if isinstance(s, dict):
            reading_time = s.get("reading_time", "")
            method = s.get("method", "")
            if reading_time or method:
                meta_parts = []
                if reading_time:
                    meta_parts.append(f"⏱ {reading_time}")
                if method:
                    meta_parts.append(f"方法: {method}")
                lines.append(f"*{' · '.join(meta_parts)}*")
                lines.append("")

            summary_text = s.get("summary", "")
            if summary_text and summary_text != "(no subtitle)":
                lines.append("### 摘要")
                lines.append("")
                lines.append(summary_text)
                lines.append("")

            kps = s.get("key_points", [])
            if kps:
                lines.append("### 核心知识点")
                lines.append("")
                for kp in kps:
                    lines.append(kp)
                lines.append("")

            tags = s.get("tags", [])
            if tags:
                tag_str = " ".join(f"`{t}`" for t in tags)
                lines.append(f"**标签:** {tag_str}")
                lines.append("")
        else:
            lines.append(str(s))
            lines.append("")

        lines.append("---")
        lines.append("")

    lines.append("*生成方式: 提取式摘要（TextRank · 无需API密钥）*")
    return "\n".join(lines)


# ── Anthropic LLM summarizer ───────────────────────────────────────────────────

_MAX_RETRIES = 3
_RETRY_BACKOFF = [2, 5, 10]  # seconds


def _call_anthropic(api_key: str, prompt: str) -> str:
    """
    Call Claude claude-sonnet-4-5 and return the text response.
    Retries up to 3 times with exponential backoff on transient errors.
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

    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read())
                return data["content"][0]["text"]
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            # Don't retry 4xx client errors (except 429 rate limit)
            if exc.code == 429:
                wait = _RETRY_BACKOFF[min(attempt, len(_RETRY_BACKOFF) - 1)]
                time.sleep(wait)
                last_exc = RuntimeError(f"Anthropic rate limit (429); retried {attempt+1}x")
                continue
            raise RuntimeError(
                f"Anthropic API HTTP {exc.code}: {body[:400]}"
            ) from exc
        except urllib.error.URLError as exc:
            wait = _RETRY_BACKOFF[min(attempt, len(_RETRY_BACKOFF) - 1)]
            time.sleep(wait)
            last_exc = RuntimeError(f"Anthropic API network error: {exc.reason}")
            continue

    raise last_exc or RuntimeError("Anthropic API: all retries failed")


def llm_summarize_video(api_key: str, title: str, subtitle_text: str) -> dict[str, Any]:
    """Use Claude to summarize a single video's subtitle text."""
    text = _truncate(subtitle_text)
    prompt = (
        f"你是一个学习助手。以下是B站视频《{title}》的字幕内容：\n\n"
        f"{text}\n\n"
        "请用中文输出：\n"
        "1. 一段简洁的摘要（3-5句话）\n"
        "2. 5个核心知识点（每点一句话，以「- 」开头）\n"
        "3. 5-8个关键词/标签（用英文逗号分隔，放在「标签：」行后）\n\n"
        "格式：\n摘要：\n<摘要内容>\n\n核心知识点：\n<知识点列表>\n\n标签：<标签1>, <标签2>, ..."
    )
    response = _call_anthropic(api_key, prompt)

    # Parse the structured response
    summary_part = ""
    key_points: list[str] = []
    tags: list[str] = []

    if "摘要：" in response and "核心知识点：" in response:
        parts = response.split("核心知识点：", 1)
        summary_part = parts[0].replace("摘要：", "").strip()
        remainder = parts[1]

        if "标签：" in remainder:
            kp_block, tag_block = remainder.split("标签：", 1)
            tags = [t.strip() for t in tag_block.split(",") if t.strip()]
        else:
            kp_block = remainder

        key_points = [
            line.strip()
            for line in kp_block.splitlines()
            if line.strip().startswith("-")
        ]
    else:
        summary_part = response.strip()

    reading_time = estimate_reading_time(subtitle_text_to_plain(subtitle_text))

    return {
        "summary": summary_part,
        "key_points": key_points,
        "tags": tags,
        "reading_time": reading_time,
        "method": f"claude-{CLAUDE_MODEL}",
    }


def subtitle_text_to_plain(text: str) -> str:
    """Strip truncation marker from subtitle text."""
    return text.split("\n[... truncated")[0]


def llm_combine_script(
    api_key: str, video_summaries: list[dict[str, Any]]
) -> str:
    """Use Claude to write a cohesive study script across all videos."""
    combined_notes = []
    for vs in video_summaries:
        title = vs.get("title", "未知视频")
        s = vs.get("summary", {})
        if isinstance(s, dict):
            note = (
                f"**{title}**\n"
                f"摘要: {s.get('summary','')}\n"
                + "\n".join(s.get("key_points", []))
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
    Summarize a single video. Uses LLM if api_key is provided, else TextRank extractive.

    Returns dict with keys: title, summary (dict with summary/key_points/tags/reading_time/method).
    """
    text = subtitle_lines_to_text(subtitle_lines)

    if not text.strip():
        return {
            "title": title,
            "summary": {
                "summary": "(no subtitle content)",
                "key_points": [],
                "tags": [],
                "reading_time": "< 1 min",
                "method": "none",
            },
        }

    if api_key:
        try:
            result = llm_summarize_video(api_key, title, text)
        except RuntimeError as exc:
            from cli_ui import yellow
            print(f"  {yellow('⚠')} LLM failed for '{title[:40]}': {exc}. Falling back to extractive.")
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
    Uses LLM if api_key provided, else extractive combination with TOC.
    """
    if not video_summaries:
        return "# 学习脚本\n\n（没有视频内容）"

    if api_key:
        try:
            return llm_combine_script(api_key, video_summaries)
        except RuntimeError as exc:
            from cli_ui import yellow
            print(f"  {yellow('⚠')} LLM script generation failed: {exc}. Using extractive fallback.")

    return extractive_combine_script(video_summaries)
