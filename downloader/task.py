import os
import yt_dlp
from aiogram import Bot
from bot.main import BOT_TOKEN

# Подпись для всех файлов
SIGNATURE_TEXT = "Скачано через [Freedom Downloader](https://t.me/freedom_downloadbot)"

def download_job(url: str, chat_id: int):
    bot = Bot(token=BOT_TOKEN)
    ydl_opts = {
        'format': 'best',
        'outtmpl': f'/tmp/%(title)s.%(ext)s',
        'noplaylist': False,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

        # Отправляем файл пользователю с подписью
        asyncio.run(send_file(bot, chat_id, filename))

    except Exception as e:
        asyncio.run(bot.send_message(chat_id, f"Ошибка при скачивании: {e}"))

async def send_file(bot: Bot, chat_id: int, path: str):
    if os.path.exists(path):
        try:
            with open(path, "rb") as f:
                await bot.send_document(chat_id, f, caption=SIGNATURE_TEXT, parse_mode="Markdown")
        finally:
            os.remove(path)
    else:
        await bot.send_message(chat_id, "Файл не найден после скачивания.")
