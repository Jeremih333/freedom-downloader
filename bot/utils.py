import os
import asyncio
import json
import shlex
import logging
from typing import List, Tuple
from utils.validation import is_url as _is_url
from utils.validation import safe_quote

logger = logging.getLogger("bot.utils")

# probe and search should be fast; use yt-dlp in worker where heavy. But probing small JSON is OK here.

async def probe_formats_async(url: str, max_options: int = 6):
    """Return list of formats for keyboard"""
    cmd = f"yt-dlp -J --no-warnings {safe_quote(url)}"
    proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await proc.communicate()
    if proc.returncode != 0:
        logger.warning("Probe failed: %s", err.decode()[:200])
        return []
    try:
        info = json.loads(out.decode())
    except Exception as e:
        logger.exception("Parse probe JSON failed")
        return []
    formats = info.get("formats", [])
    options = []
    seen = set()
    for f in formats:
        fid = f.get("format_id")
        if not fid or fid in seen:
            continue
        seen.add(fid)
        note = f.get("format_note") or f.get("ext") or ""
        desc = f"{f.get('ext','')} — {f.get('height') or f.get('abr') or ''} {note}".strip()
        label = desc[:45]
        options.append({"id": fid, "label": label, "url": url})
        if len(options) >= max_options:
            break
    # add always 'best video' and 'best audio'
    options.insert(0, {"id": "bestvideo+bestaudio/best", "label": "Видео (лучшее)", "url": url})
    options.insert(1, {"id": "bestaudio", "label": "Аудио (лучшее)", "url": url})
    return options

async def search_youtube_async(query: str, page: int = 1, per_page: int = 5):
    """Use yt-dlp ytsearch for MVP."""
    # yt-dlp doesn't support paged ytsearch natively; implement via ytsearchN: and slicing server-side.
    cmd = f'yt-dlp "ytsearch{per_page}:{shlex.quote(query)}" --dump-json'
    proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await proc.communicate()
    if proc.returncode != 0:
        logger.warning("Search yt-dlp failed: %s", err.decode()[:200])
        return [], {}
    lines = out.decode().splitlines()
    results = []
    for line in lines:
        try:
            info = json.loads(line)
        except Exception:
            continue
        results.append({
            "title": info.get("title"),
            "uploader": info.get("uploader"),
            "url": info.get("webpage_url"),
            "id": info.get("id"),
        })
    pagination = {
        "next": f"SEARCHPAGE|{query}|{page+1}",
    }
    if page > 1:
        pagination["prev"] = f"SEARCHPAGE|{query}|{page-1}"
    return results, pagination

async def get_album_meta_async(album_id: str):
    """MVP: try to use yt-dlp to get playlist info."""
    # album_id could be playlist URL or id
    cmd = f"yt-dlp -J {shlex.quote(album_id)}"
    proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, err = await proc.communicate()
    if proc.returncode != 0:
        return {}
    try:
        info = json.loads(out.decode())
    except Exception:
        return {}
    tracks = []
    for entry in info.get("entries", [])[:50]:
        tracks.append({"title": entry.get("title"), "url": entry.get("webpage_url")})
    return {"id": album_id, "title": info.get("title", "Album"), "tracks": tracks}

def is_url(text: str) -> bool:
    return _is_url(text)

# enqueue download (send to RQ)
from rq import Queue
import redis
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_conn = redis.from_url(REDIS_URL)
q = Queue("downloads", connection=_conn)

def enqueue_download_task(url_or_id: str, fmt: str, user_id: int):
    # pack metadata and push job. Worker will handle special fmt like 'album'
    job = q.enqueue("downloader.task.download_job", url_or_id, fmt, user_id, job_timeout=int(os.getenv("DOWNLOAD_TIMEOUT", "1800")))
    return {"job_id": job.id}
