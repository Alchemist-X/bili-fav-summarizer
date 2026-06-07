# bili-fav-summarizer

Fetch your Bilibili (B站) favorited videos, download their subtitles, and generate per-video summaries + a consolidated study script — all via Python stdlib, no pip installs required.

## What it does

1. **Fetches your favorite folders** via the Bilibili API using your `SESSDATA` cookie
2. **Lists all videos** in a folder (or all folders)
3. **Downloads subtitles** for each video (Chinese preferred, falls back to first available)
4. **Summarizes** each video:
   - With `ANTHROPIC_API_KEY` set → Claude `claude-sonnet-4-5` generates a structured summary + key points
   - Without an API key → pure-Python extractive summarizer (top-scored sentences), works offline
5. **Writes output** to `out/`: per-video JSON files + a combined `script.md` study script

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
# ANTHROPIC_API_KEY is optional — extractive fallback works without it
source .env   # or: export BILI_SESSDATA=...
```

## Quickstart

### Offline demo (no cookie, no API key needed)

```bash
python3 main.py --demo
```

Runs the full summarize pipeline on the bundled `sample/sample-subtitle.json` and writes `out/script.md`. Use this to verify everything works before touching the network.

### Summarize a specific favorite folder

```bash
# Find your media_id: run --all first or check the URL on bilibili.com/medialist/...
python3 main.py --folder 12345678
```

### Summarize all favorite folders

```bash
python3 main.py --all
```

### With LLM summaries

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python3 main.py --folder 12345678
```

## Output

```
out/
  script.md                     # Combined study script across all videos
  BV1xx...-VideoTitle.json      # Per-video summary (title, key points, method)
  folder-12345678-MyFolder.json  # Per-folder bundle (--all mode)
```

## Limitations

- **Subtitles only:** Videos without CC subtitles (no auto-generated or uploaded subs) are noted as "no subtitle" and skipped from summarization.
- **Auto-generated subtitles:** Bilibili's AI-generated subs may have transcription errors; summaries reflect the source quality.
- **Rate limiting:** Requests are throttled with 0.5 s delays between API calls. Very large libraries may take a few minutes.
- **SESSDATA expiry:** Cookies expire; re-fetch from browser if you get 401/403 errors.
- **Chinese content:** The extractive summarizer is tuned for Chinese text (CJK character ranges). English subtitles also work.

## Legal / Terms of Service notice

This tool is intended **solely for personal use of your own Bilibili favorites**. It accesses only the authenticated user's own data through the same public APIs the Bilibili web app uses. Do not use it to scrape or archive content you do not own rights to. Respect Bilibili's [Terms of Use](https://www.bilibili.com/blackboard/help.html). The authors are not responsible for any misuse.

## Project structure

```
bili_api.py          — Bilibili API client (urllib only)
summarize.py         — Summarization engine (LLM + extractive fallback)
main.py              — CLI entry point
sample/
  sample-subtitle.json  — Bundled fake subtitle for --demo mode
.env.example         — Environment variable template
```

## License

MIT © 2026 Alchemist-X
