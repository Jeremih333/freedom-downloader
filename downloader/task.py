import os
from yt_dlp import YoutubeDL
import boto3

def download_job(url, chat_id, format="mp4", quality="best"):
    """
    Скачивает видео/аудио и отправляет напрямую или через S3 при превышении лимита.
    """
    max_bytes = int(os.getenv("MAX_DIRECT_SEND_BYTES", 50000000))
    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'outtmpl': '/tmp/%(title)s.%(ext)s',
        'quiet': True,
    }

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        file_path = ydl.prepare_filename(info)
        file_size = os.path.getsize(file_path)

    if file_size > max_bytes:
        s3 = boto3.client(
            's3',
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            region_name=os.getenv("S3_REGION"),
        )
        key = os.path.basename(file_path)
        s3.upload_file(file_path, os.getenv("S3_BUCKET"), key)
        download_link = f"https://{os.getenv('S3_BUCKET')}.{os.getenv('S3_REGION')}/{key}"
        return f"Файл слишком большой, скачайте здесь: {download_link}\n\nСкачано через Freedom Downloader: https://t.me/freedom_downloadbot"
    else:
        return file_path  # Telegram бот отправит файл напрямую
