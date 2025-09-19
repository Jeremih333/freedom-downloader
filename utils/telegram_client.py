import os
import logging
from aiogram import Bot
from aiogram.types import InputFile
from aiogram.utils.exceptions import TelegramAPIError

TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=TOKEN)
logger = logging.getLogger("utils.telegram_client")

def send_text(user_id: int, text: str):
    try:
        bot.send_message(chat_id=user_id, text=text)
    except TelegramAPIError as e:
        logger.exception("Failed to send text to %s: %s", user_id, e)

def send_document_or_link(user_id: int, payload: str, signature: str, external: bool=False):
    """
    payload: local path (if external=False) or URL
    Sends document if local; otherwise sends link.
    Adds signature to message.
    """
    message = f"{signature}"
    if external:
        message = f"{message}\n\nСсылка (доступно ограниченное время): {payload}"
        send_text(user_id, message)
        return
    try:
        doc = InputFile(payload)
        bot.send_document(chat_id=user_id, document=doc, caption=message)
    except TelegramAPIError as e:
        logger.warning("Direct send failed, fallback to upload -> link")
        # fallback: upload to s3 and send link (requires upload)
        try:
            from utils.s3 import upload_file_preserve
            url = upload_file_preserve(payload)
            send_text(user_id, f"{signature}\n\nСсылка: {url}")
        except Exception:
            logger.exception("Fallback upload failed")
