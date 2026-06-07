"""
report.py — Generate a beautiful standalone HTML study-notes report.

Produces a single self-contained HTML file with:
  - Dark theme, clean typography
  - Sidebar TOC of all videos
  - Video cards with title, summary, key points, tags, reading time
  - Client-side search/filter (vanilla JS)
  - Responsive layout
  - Zero external dependencies (inline CSS + JS)
"""

import html
import json
import re
from datetime import datetime
from typing import Any


# ── HTML generation helpers ────────────────────────────────────────────────────

def _esc(text: str) -> str:
    """HTML-escape a string."""
    return html.escape(str(text), quote=True)


def _tag(name: str, content: str, **attrs: str) -> str:
    """Wrap content in an HTML tag."""
    attr_str = "".join(
        f' {k.replace("_", "-")}="{_esc(v)}"'
        for k, v in attrs.items()
        if v
    )
    return f"<{name}{attr_str}>{content}</{name}>"


# ── Inline CSS ─────────────────────────────────────────────────────────────────

_CSS = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg: #0f1117;
  --bg2: #161b22;
  --bg3: #1c2333;
  --bg4: #21262d;
  --border: #30363d;
  --text: #e6edf3;
  --text2: #8b949e;
  --text3: #6e7681;
  --accent: #58a6ff;
  --accent2: #79c0ff;
  --green: #3fb950;
  --yellow: #d29922;
  --red: #f85149;
  --tag-bg: #1f6feb33;
  --tag-border: #1f6feb66;
  --tag-text: #79c0ff;
  --card-hover: #1c2333;
  --shadow: 0 4px 24px rgba(0,0,0,0.4);
  --radius: 10px;
  --sidebar-w: 280px;
  --font: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif;
  --font-mono: ui-monospace, "Cascadia Code", "Source Code Pro", monospace;
}

html { scroll-behavior: smooth; }

body {
  font-family: var(--font);
  background: var(--bg);
  color: var(--text);
  line-height: 1.6;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

/* ── Header ── */
.header {
  background: linear-gradient(135deg, #0d1117 0%, #161b22 50%, #1a1f2e 100%);
  border-bottom: 1px solid var(--border);
  padding: 20px 28px;
  position: sticky;
  top: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  gap: 20px;
  backdrop-filter: blur(8px);
}

.header-title {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
}

.header-title h1 {
  font-size: 1.2rem;
  font-weight: 700;
  color: var(--accent2);
  letter-spacing: -0.01em;
}

.header-title .subtitle {
  font-size: 0.8rem;
  color: var(--text3);
  margin-top: 2px;
}

.header-meta {
  font-size: 0.78rem;
  color: var(--text3);
  text-align: right;
}

/* ── Layout ── */
.layout {
  display: flex;
  flex: 1;
  height: calc(100vh - 72px);
}

/* ── Sidebar ── */
.sidebar {
  width: var(--sidebar-w);
  background: var(--bg2);
  border-right: 1px solid var(--border);
  overflow-y: auto;
  flex-shrink: 0;
  position: sticky;
  top: 72px;
  height: calc(100vh - 72px);
}

.sidebar-header {
  padding: 16px 16px 8px;
  position: sticky;
  top: 0;
  background: var(--bg2);
  border-bottom: 1px solid var(--border);
  z-index: 10;
}

.sidebar-header h2 {
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text3);
  margin-bottom: 10px;
}

.search-box {
  width: 100%;
  background: var(--bg4);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 7px 10px;
  color: var(--text);
  font-size: 0.8rem;
  font-family: var(--font);
  outline: none;
  transition: border-color 0.2s;
}

.search-box:focus {
  border-color: var(--accent);
}

.search-box::placeholder {
  color: var(--text3);
}

.sidebar-list {
  list-style: none;
  padding: 8px 8px;
}

.sidebar-item {
  margin-bottom: 2px;
}

.sidebar-link {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  text-decoration: none;
  color: var(--text2);
  font-size: 0.8rem;
  transition: background 0.15s, color 0.15s;
  cursor: pointer;
}

.sidebar-link:hover, .sidebar-link.active {
  background: var(--bg4);
  color: var(--text);
}

.sidebar-link.no-sub {
  opacity: 0.5;
}

.sidebar-idx {
  flex-shrink: 0;
  font-size: 0.7rem;
  color: var(--text3);
  font-variant-numeric: tabular-nums;
  padding-top: 1px;
  min-width: 20px;
}

.sidebar-title {
  flex: 1;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  line-height: 1.4;
}

.sidebar-time {
  flex-shrink: 0;
  font-size: 0.68rem;
  color: var(--text3);
  white-space: nowrap;
  padding-top: 2px;
}

/* ── Main content ── */
.main {
  flex: 1;
  overflow-y: auto;
  padding: 28px 32px;
}

/* ── Stats bar ── */
.stats-bar {
  display: flex;
  gap: 20px;
  margin-bottom: 28px;
  flex-wrap: wrap;
}

.stat-card {
  background: var(--bg2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 20px;
  min-width: 120px;
  text-align: center;
}

.stat-value {
  font-size: 1.8rem;
  font-weight: 700;
  color: var(--accent2);
  line-height: 1;
}

.stat-label {
  font-size: 0.72rem;
  color: var(--text3);
  margin-top: 4px;
}

/* ── Video cards ── */
.video-card {
  background: var(--bg2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin-bottom: 20px;
  overflow: hidden;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.video-card:hover {
  border-color: var(--accent);
  box-shadow: var(--shadow);
}

.video-card.no-subtitle {
  opacity: 0.6;
}

.card-header {
  padding: 18px 22px 12px;
  display: flex;
  align-items: flex-start;
  gap: 12px;
  border-bottom: 1px solid var(--border);
  background: var(--bg3);
}

.card-num {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--bg4);
  border: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--text3);
  margin-top: 2px;
}

.card-title-area {
  flex: 1;
  min-width: 0;
}

.card-title {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text);
  line-height: 1.4;
  margin-bottom: 6px;
}

.card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}

.meta-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 0.72rem;
  color: var(--text3);
}

.meta-badge.method {
  background: var(--bg4);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 2px 6px;
}

.card-link {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 0.75rem;
  color: var(--accent);
  text-decoration: none;
  border: 1px solid var(--tag-border);
  border-radius: 6px;
  padding: 4px 10px;
  white-space: nowrap;
  transition: background 0.15s;
}

.card-link:hover {
  background: var(--tag-bg);
}

/* ── Card body ── */
.card-body {
  padding: 18px 22px;
  display: grid;
  gap: 16px;
}

.section-label {
  font-size: 0.68rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--text3);
  margin-bottom: 8px;
}

.summary-text {
  font-size: 0.875rem;
  color: var(--text2);
  line-height: 1.7;
}

.key-points-list {
  list-style: none;
  display: grid;
  gap: 6px;
}

.key-point {
  display: flex;
  gap: 8px;
  font-size: 0.85rem;
  color: var(--text);
  line-height: 1.5;
}

.key-point::before {
  content: "▸";
  color: var(--accent);
  flex-shrink: 0;
  margin-top: 1px;
}

.tags-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tag {
  display: inline-block;
  background: var(--tag-bg);
  border: 1px solid var(--tag-border);
  color: var(--tag-text);
  font-size: 0.72rem;
  padding: 2px 8px;
  border-radius: 12px;
  font-family: var(--font-mono);
}

.no-content-msg {
  font-size: 0.85rem;
  color: var(--text3);
  font-style: italic;
  padding: 12px 0;
}

/* ── No results ── */
.no-results {
  display: none;
  text-align: center;
  color: var(--text3);
  padding: 60px 0;
  font-size: 0.9rem;
}

/* ── Footer ── */
.footer {
  border-top: 1px solid var(--border);
  padding: 14px 32px;
  font-size: 0.75rem;
  color: var(--text3);
  text-align: center;
  background: var(--bg2);
}

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--text3); }

/* ── Responsive ── */
@media (max-width: 768px) {
  :root { --sidebar-w: 220px; }
  .main { padding: 16px; }
  .stats-bar { gap: 10px; }
}

@media (max-width: 580px) {
  .layout { flex-direction: column; height: auto; }
  .sidebar { width: 100%; height: auto; position: relative; top: 0; border-right: none; border-bottom: 1px solid var(--border); max-height: 200px; }
  .main { padding: 14px; }
}

/* ── Active highlight ── */
.video-card.highlight {
  border-color: var(--accent2);
}
"""


# ── Inline JS ──────────────────────────────────────────────────────────────────

_JS = """
(function () {
  const searchBox = document.getElementById('search-box');
  const cards = Array.from(document.querySelectorAll('.video-card'));
  const sidebarItems = Array.from(document.querySelectorAll('.sidebar-item'));
  const noResults = document.getElementById('no-results');

  function normalize(s) {
    return s.toLowerCase().replace(/\\s+/g, ' ').trim();
  }

  function filterCards(query) {
    const q = normalize(query);
    let visible = 0;
    cards.forEach(function (card, idx) {
      const text = normalize(card.textContent);
      const match = !q || text.includes(q);
      card.style.display = match ? '' : 'none';
      sidebarItems[idx].style.display = match ? '' : 'none';
      if (match) visible++;
    });
    noResults.style.display = visible === 0 ? 'block' : 'none';
  }

  if (searchBox) {
    searchBox.addEventListener('input', function () {
      filterCards(searchBox.value);
    });
  }

  // Sidebar active highlight on scroll
  const observer = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      const id = entry.target.id;
      const link = document.querySelector('.sidebar-link[href="#' + id + '"]');
      if (link) {
        if (entry.isIntersecting) {
          document.querySelectorAll('.sidebar-link').forEach(function (l) { l.classList.remove('active'); });
          link.classList.add('active');
        }
      }
    });
  }, { threshold: 0.3, rootMargin: '-72px 0px 0px 0px' });

  cards.forEach(function (card) {
    if (card.id) observer.observe(card);
  });
})();
"""


# ── Card rendering ─────────────────────────────────────────────────────────────

def _render_card(idx: int, vs: dict[str, Any]) -> str:
    title = vs.get("title", f"视频 {idx}")
    bvid = vs.get("bvid", "")
    s = vs.get("summary", {})
    if not isinstance(s, dict):
        s = {"summary": str(s), "key_points": [], "tags": [], "reading_time": "", "method": ""}

    summary_text = s.get("summary", "")
    key_points = s.get("key_points", [])
    tags = s.get("tags", [])
    reading_time = s.get("reading_time", "")
    method = s.get("method", "")

    has_content = summary_text and summary_text not in ("(no subtitle content)", "(no subtitle)")
    card_class = "video-card" + ("" if has_content else " no-subtitle")
    card_id = f"card-{idx}"

    # Header
    link_html = ""
    if bvid:
        bili_url = f"https://www.bilibili.com/video/{_esc(bvid)}"
        link_html = f'<a class="card-link" href="{bili_url}" target="_blank" rel="noopener">▶ B站</a>'

    meta_parts = []
    if reading_time:
        meta_parts.append(f'<span class="meta-badge">⏱ {_esc(reading_time)}</span>')
    if bvid:
        meta_parts.append(f'<span class="meta-badge">{_esc(bvid)}</span>')
    if method:
        meta_parts.append(f'<span class="meta-badge method">{_esc(method)}</span>')

    header = f"""
    <div class="card-header">
      <div class="card-num">{idx}</div>
      <div class="card-title-area">
        <div class="card-title">{_esc(title)}</div>
        <div class="card-meta">
          {"".join(meta_parts)}
        </div>
      </div>
      {link_html}
    </div>"""

    # Body
    body_parts = []

    if has_content:
        body_parts.append(f"""
      <div>
        <div class="section-label">摘要 / Summary</div>
        <p class="summary-text">{_esc(summary_text)}</p>
      </div>""")

        if key_points:
            kp_items = "".join(
                f'<li class="key-point">{_esc(kp.lstrip("- ").strip())}</li>'
                for kp in key_points
                if kp.strip()
            )
            body_parts.append(f"""
      <div>
        <div class="section-label">核心知识点 / Key Points</div>
        <ul class="key-points-list">{kp_items}</ul>
      </div>""")

        if tags:
            tag_html = "".join(f'<span class="tag">{_esc(t)}</span>' for t in tags)
            body_parts.append(f"""
      <div>
        <div class="section-label">关键词 / Tags</div>
        <div class="tags-row">{tag_html}</div>
      </div>""")
    else:
        body_parts.append('<p class="no-content-msg">无字幕 — 此视频暂无可用字幕。</p>')

    body = f'<div class="card-body">{"".join(body_parts)}</div>'

    return f'<div class="{_esc(card_class)}" id="{_esc(card_id)}">{header}{body}</div>'


# ── Sidebar rendering ──────────────────────────────────────────────────────────

def _render_sidebar_item(idx: int, vs: dict[str, Any]) -> str:
    title = vs.get("title", f"视频 {idx}")
    s = vs.get("summary", {})
    reading_time = ""
    has_content = True

    if isinstance(s, dict):
        reading_time = s.get("reading_time", "")
        method = s.get("method", "")
        has_content = s.get("summary", "") not in ("(no subtitle content)", "(no subtitle)", "")

    link_class = "sidebar-link" + ("" if has_content else " no-sub")
    time_html = f'<span class="sidebar-time">{_esc(reading_time)}</span>' if reading_time else ""

    return f"""<li class="sidebar-item">
      <a class="{link_class}" href="#card-{idx}">
        <span class="sidebar-idx">{idx}</span>
        <span class="sidebar-title">{_esc(title)}</span>
        {time_html}
      </a>
    </li>"""


# ── Full report ────────────────────────────────────────────────────────────────

def generate_report(
    video_summaries: list[dict[str, Any]],
    title: str = "Bilibili 学习笔记",
    folder_name: str = "",
) -> str:
    """
    Generate a complete standalone HTML study-notes report.

    Parameters
    ----------
    video_summaries : list of per-video summary dicts
    title : page title
    folder_name : optional folder/session label shown in the header

    Returns
    -------
    str — complete HTML document (self-contained, no CDN)
    """
    total = len(video_summaries)
    with_content = sum(
        1 for vs in video_summaries
        if isinstance(vs.get("summary"), dict)
        and vs["summary"].get("summary") not in ("(no subtitle content)", "(no subtitle)", "")
    )
    no_sub = total - with_content

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    subtitle_label = folder_name or f"{total} videos"

    # Stats bar
    stats_html = f"""
    <div class="stats-bar">
      <div class="stat-card">
        <div class="stat-value">{total}</div>
        <div class="stat-label">视频总数</div>
      </div>
      <div class="stat-card">
        <div class="stat-value" style="color:var(--green)">{with_content}</div>
        <div class="stat-label">已摘要</div>
      </div>
      <div class="stat-card">
        <div class="stat-value" style="color:var(--yellow)">{no_sub}</div>
        <div class="stat-label">无字幕</div>
      </div>
    </div>"""

    # Cards
    cards_html = "\n".join(_render_card(i, vs) for i, vs in enumerate(video_summaries, 1))

    # Sidebar items
    sidebar_items_html = "\n".join(
        _render_sidebar_item(i, vs) for i, vs in enumerate(video_summaries, 1)
    )

    # Assemble
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{_esc(title)}</title>
  <style>{_CSS}</style>
</head>
<body>

  <!-- Header -->
  <header class="header">
    <div class="header-title">
      <div>
        <h1>🎬 {_esc(title)}</h1>
        <div class="subtitle">{_esc(subtitle_label)}</div>
      </div>
    </div>
    <div class="header-meta">
      生成于 {_esc(generated_at)}<br>
      bili-fav-summarizer
    </div>
  </header>

  <div class="layout">

    <!-- Sidebar -->
    <aside class="sidebar">
      <div class="sidebar-header">
        <h2>视频列表 / {total} videos</h2>
        <input
          class="search-box"
          id="search-box"
          type="text"
          placeholder="搜索标题或内容…"
          autocomplete="off"
        >
      </div>
      <ul class="sidebar-list">
        {sidebar_items_html}
      </ul>
    </aside>

    <!-- Main content -->
    <main class="main">
      {stats_html}
      {cards_html}
      <div class="no-results" id="no-results">
        未找到匹配的视频 / No matching videos found.
      </div>
    </main>

  </div>

  <!-- Footer -->
  <footer class="footer">
    bili-fav-summarizer · 生成于 {_esc(generated_at)} · Python stdlib only · MIT License
  </footer>

  <script>{_JS}</script>
</body>
</html>"""
