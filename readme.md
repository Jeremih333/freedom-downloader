# Freedom Downloader — Telegram media downloader bot (webhook)

Production-minded scaffold for a Telegram bot that:
- accepts links or search queries (artist / track / album)
- shows interactive inline results and format/quality options
- downloads via `yt-dlp` + `ffmpeg` in background workers
- returns small files directly and large files via presigned S3 URLs
- uses webhook (Render) + RQ worker (Redis)

⚠️ **Legal**: be mindful of Terms of Service and copyright. Use only for non-infringing content or users' own content.

## Features
- Webhook mode (recommended)
- Search via `yt-dlp` (MVP) — replace with provider APIs for production
- FSM state via Redis
- Pagination, album / artist workflows
- Presigned S3 URLs + TTL
- Signature on downloads: "Скачано через Freedom Downloader — https://t.me/freedom_downloadbot"

## Quick start (local)
1. Copy `.env.example` → `.env` and apply credentials.
2. Start `docker-compose up` (it will start Redis + MinIO for local S3 emulation).
3. Run worker: `python downloader/worker.py`
4. Run bot web: `python bot/main.py` (or use `Procfile` tooling)

## Deploy to Render
- Create two services:
  - **Web Service** (webhook): run `web: python bot/main.py` (or use Docker)
  - **Worker**: run `worker: python downloader/worker.py`
- Add environment variables in Render UI (BOT_TOKEN, RENDER_EXTERNAL_URL, REDIS_URL, AWS_* etc.)
- For Render free-tier, configure worker concurrency low and enable TTL cleanup.

See NOTES.md for more deployment details and security notes.

Bot creator - https://t.me/odinnadsat
