# bili-fav-summarizer

Fetch your Bilibili (B站) favorited videos, download their subtitles, and generate per-video summaries + a consolidated study script and a beautiful HTML dashboard — all via **Python stdlib only**, no pip installs required.

## What it does

1. **Fetches your favorite folders** via the Bilibili API using your `SESSDATA` cookie
2. **Lists all videos** in a folder (or all folders)
3. **Downloads subtitles** for each video (Chinese preferred, falls back to first available)
4. **Caches** subtitle downloads and per-video summaries in `~/.bili-fav-cache/` for fast resumable reruns
5. **Summarizes** each video with keyword/tag extraction and reading-time estimation:
   - With `ANTHROPIC_API_KEY` → Claude `claude-sonnet-4-5` generates structured summaries
   - Without API key → pure-Python **TextRank**-style extractive summarizer, CJK-aware, works fully offline
6. **Writes output** to `out/`:
   - Per-video `.md` and `.json` files
   - `script.md` — combined study script with **table of contents** and anchor links
   - `report.html` — **standalone HTML dashboard** (dark theme, sidebar TOC, search/filter, video cards)

## How to get your SESSDATA cookie

1. Log into [bilibili.com](https://www.bilibili.com) in your browser
2. Open DevTools → **Application** (Chrome) or **Storage** (Firefox)
3. Navigate to **Cookies → `https://api.bilibili.com`** (or `.bilibili.com`)
4. Copy the value of the **`SESSDATA`** cookie
5. Paste it into your `.env` file (see below)

> **Note:** SESSDATA expires periodically. If you get auth errors, re-copy it from your browser.

## Environment setup

```bash
cp .env.example .env
# Edit .env and fill in BILI_SESSDATA (required for live modes)
# ANTHROPIC_API_KEY is optional — TextRank extractive fallback works without it
source .env   # or: export BILI_SESSDATA=...
```

## Quickstart

### Offline demo (no cookie, no API key needed)

```bash
python3 main.py --demo
```

Runs the full pipeline on the bundled `sample/sample-subtitle.json` and writes `out/script.md` and `out/report.html`. Use this to verify everything works before touching the network.

### Summarize a specific favorite folder

```bash
# By numeric ID (find it in the Bilibili URL: /medialist/detail/ml12345678)
python3 main.py --folder 12345678

# By folder name (case-insensitive substring match)
python3 main.py --folder-name "英语学习"
```

### Summarize all favorite folders

```bash
python3 main.py --all
```

### Useful options

```bash
# Limit to first 10 videos (great for testing)
python3 main.py --all --limit 10

# Force re-download of all subtitles and summaries (bypass cache)
python3 main.py --folder 12345678 --refresh

# With LLM summaries
export ANTHROPIC_API_KEY=sk-ant-...
python3 main.py --folder 12345678
```

## Output

```
out/
  script.md                         # Combined study script with TOC
  report.html                       # Standalone HTML dashboard (open in browser)
  BV1xx...-VideoTitle.md            # Per-video markdown summary
  BV1xx...-VideoTitle.json          # Per-video summary JSON
  folder-12345678-MyFolder.json     # Per-folder bundle (--all mode)

~/.bili-fav-cache/
  BV1xx....subtitle.json            # Cached raw subtitle lines
  BV1xx....summary.json             # Cached summary results
```

## HTML Report features

Open `out/report.html` in any browser — it is a fully self-contained file (no CDN, no network needed):

- **Dark theme** with clean, readable typography
- **Sidebar TOC** listing all videos with estimated reading time
- **Search/filter box** — instantly filters cards by title or content (vanilla JS)
- **Video cards** — title, summary, key points, tags, reading time, B站 link
- **Stats bar** — total videos / summarized / no-subtitle counts
- **Responsive** layout, works on mobile

## Features

| Feature | Detail |
|---|---|
| Summarizer | TextRank graph-based sentence ranking (stdlib only) |
| CJK support | CJK-aware sentence splitting (。！？；) + Chinese stopwords |
| Keyword extraction | TF-based keyword scoring with length bonus |
| Reading time | CJK: 350 chars/min · English: 200 words/min |
| Cache | `~/.bili-fav-cache/` keyed by bvid; `--refresh` to bust |
| Retries | Up to 3 retries with exponential backoff (2/5/10 s) |
| Progress | ANSI-colored progress lines (✓/✗/⏭), degrades gracefully on non-TTY |
| CLI | Header banner, per-video progress, final summary box |
| `--limit N` | Process only first N videos per folder |
| `--folder-name` | Select folder by name instead of numeric ID |

## Project structure

```
bili_api.py      — Bilibili API client (urllib only, retry+backoff)
summarize.py     — TextRank extractive + Claude LLM summarization
cache.py         — Subtitle and summary caching (~/.bili-fav-cache)
report.py        — Standalone HTML report generator (inline CSS/JS)
cli_ui.py        — ANSI-colored CLI output helpers
main.py          — CLI entry point
sample/
  sample-subtitle.json  — Bundled sample for --demo mode
.env.example     — Environment variable template
```

## Limitations

- **Subtitles only:** Videos without CC subtitles are listed as "no subtitle" and skipped from summarization.
- **Auto-generated subtitles:** Bilibili's AI-generated subs may have transcription errors.
- **Rate limiting:** Requests are throttled with 0.6 s delays + automatic retry.
- **SESSDATA expiry:** Cookies expire; re-fetch from browser if you get 401/403 errors.

## Legal / Terms of Service notice

This tool is intended **solely for personal use of your own Bilibili favorites**. It accesses only the authenticated user's own data through the same public APIs the Bilibili web app uses. Do not use it to scrape or archive content you do not own rights to. Respect Bilibili's [Terms of Use](https://www.bilibili.com/blackboard/help.html). The authors are not responsible for any misuse.

## License

MIT © 2026 Alchemist-X
