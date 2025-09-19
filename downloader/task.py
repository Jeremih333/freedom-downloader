import os
import tempfile
import subprocess
import shutil
import logging
from utils.s3 import upload_file_preserve
from utils.telegram_client import send_document_or_link
from utils.validation import sanitize_filename

logger = logging.getLogger("downloader.task")

MAX_DIRECT = int(os.getenv("MAX_DIRECT_SEND_BYTES", "50000000"))
RESULT_TTL_SECONDS = int(os.getenv("RESULT_TTL_SECONDS", "86400"))
SIGNATURE = os.getenv("DOWNLOAD_SIGNATURE", "Скачано через Freedom Downloader — https://t.me/freedom_downloadbot")

def download_job(url_or_id: str, fmt: str, user_id: int):
    """
    This function will be executed by the worker (RQ).
    - If fmt == 'album' treat url_or_id as playlist and download tracks as archive
    - Else use yt-dlp to download a single media in requested format
    """
    tmpdir = tempfile.mkdtemp(prefix="dl_")
    try:
        if fmt == "album":
            # For MVP: download playlist as individual tracks and pack to zip
            out_template = os.path.join(tmpdir, "%(playlist_index)s - %(title)s.%(ext)s")
            cmd = ["yt-dlp", "-o", out_template, url_or_id]
            subprocess.check_call(cmd, cwd=tmpdir)
            # pack to zip
            archive = os.path.join(tmpdir, "album.zip")
            shutil.make_archive(archive.replace(".zip", ""), "zip", tmpdir)
            filepath = archive
        else:
            # single file download
            out_template = os.path.join(tmpdir, "%(title)s.%(ext)s")
            cmd = ["yt-dlp", "-f", fmt, "-o", out_template, url_or_id]
            subprocess.check_call(cmd, cwd=tmpdir)
            files = [os.path.join(tmpdir, f) for f in os.listdir(tmpdir) if not f.startswith(".")]
            if not files:
                raise RuntimeError("No file produced")
            filepath = sorted(files, key=lambda p: os.path.getsize(p), reverse=True)[0]

        size = os.path.getsize(filepath)
        if size <= MAX_DIRECT:
            # send file directly
            send_document_or_link(user_id, filepath, SIGNATURE)
        else:
            # upload to S3 and send link
            url = upload_file_preserve(filepath)
            send_document_or_link(user_id, url, SIGNATURE, external=True)
    except Exception as e:
        logger.exception("Download job failed")
        try:
            from utils.telegram_client import send_text
            send_text(user_id, f"Ошибка при скачивании: {e}")
        except Exception:
            logger.exception("Failed to notify user about error")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
