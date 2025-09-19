import os
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import Update, Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from rq import Queue
from redis import Redis
from downloader.task import download_job  # твой воркер
from bot.handlers import register_handlers

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot.main")

# === Config ===
TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", 10000))
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")
WEBHOOK_PATH = f"/webhook/{TOKEN}"

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_conn = Redis.from_url(REDIS_URL)
queue = Queue(connection=redis_conn)

if not TOKEN or not RENDER_EXTERNAL_URL:
    logger.error("BOT_TOKEN and RENDER_EXTERNAL_URL must be set")
    raise SystemExit(1)


# === Handlers ===
async def cmd_start(message: Message):
    await message.answer("Привет! Я бот для скачивания медиа. Отправь ссылку или запрос 🔗")


async def process_link(message: Message):
    url = message.text.strip()
    # Заглушка: определяем форматы
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="MP4 720p", callback_data=f"dl|{url}|720p")],
            [InlineKeyboardButton(text="MP3", callback_data=f"dl|{url}|mp3")],
        ]
    )
    await message.answer("Выбери формат:", reply_markup=kb)


async def process_callback(callback: CallbackQuery):
    _, url, fmt = callback.data.split("|")
    job = queue.enqueue(download_job, url, fmt)
    await callback.message.edit_text(f"Задача поставлена в очередь ✅\nФормат: {fmt}\nURL: {url}\nJob ID: {job.id}")


# === Webhook ===
async def handle_update(request: web.Request):
    data = await request.json()
    update = Update(**data)
    await request.app["dp"].feed_webhook_update(request.app["bot"], update)
    return web.Response(text="ok")


async def on_startup(app: web.Application):
    bot: Bot = app["bot"]
    webhook_url = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}"
    await bot.set_webhook(webhook_url)
    logger.info("Webhook set: %s", webhook_url)


async def on_shutdown(app: web.Application):
    bot: Bot = app["bot"]
    await bot.delete_webhook()
    await bot.session.close()


# === Application ===
def create_app():
    session = AiohttpSession()
    bot = Bot(token=TOKEN, session=session)
    dp = Dispatcher()

    # Регистрация хендлеров
    dp.message.register(cmd_start, F.text == "/start")
    dp.message.register(process_link, F.text.startswith("http"))
    dp.callback_query.register(process_callback, F.data.startswith("dl|"))

    register_handlers(dp)

    app = web.Application()
    app["bot"] = bot
    app["dp"] = dp

    app.router.add_post(WEBHOOK_PATH, handle_update)

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    return app


if __name__ == "__main__":
    app = create_app()
    web.run_app(app, host="0.0.0.0", port=PORT)
