import os
import subprocess
import shutil
from redis import Redis
from rq import get_current_job
from aiogram import Bot
from yt_dlp import YoutubeDL

# ========================
# Переменные окружения
# ========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CDN_BASE_URL = os.getenv("CDN_BASE_URL", "https://example.com/files/")  # пример ссылки, замените на S3/Cloudflare
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

bot = Bot(token=BOT_TOKEN)

# ========================
# Функция задачи для очереди
# ========================
def download_job(url: str, chat_id: int):
    job = get_current_job()
    tmp_dir = "/tmp/freedom_download"
    os.makedirs(tmp_dir, exist_ok=True)

    # Опции yt-dlp
    ydl_opts = {
        'outtmpl': f'{tmp_dir}/%(title)s.%(ext)s',
        'format': 'best',
        'noplaylist': False,
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)

        # Проверяем размер
        file_size = os.path.getsize(file_path)
        if file_size < MAX_FILE_SIZE:
            # Отправляем файл напрямую
            with open(file_path, 'rb') as f:
                bot.send_document(chat_id, f,
                                  caption=f"Скачано через [Freedom Downloader](https://t.me/freedom_downloadbot)")
        else:
            # Если большой файл — отправляем ссылку (пример)
            file_name = os.path.basename(file_path)
            download_link = f"{CDN_BASE_URL}{file_name}"
            bot.send_message(chat_id,
                             f"Файл слишком большой для Telegram. Скачивайте по ссылке: {download_link}\n"
                             f"Скачано через [Freedom Downloader](https://t.me/freedom_downloadbot)")
    except Exception as e:
        bot.send_message(chat_id, f"Произошла ошибка при скачивании: {e}")
    finally:
        # Убираем временные файлы
        shutil.rmtree(tmp_dir, ignore_errors=True)
