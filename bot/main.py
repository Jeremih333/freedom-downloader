import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
from redis import Redis
from rq import Queue
from downloader.task import download_job
from aiohttp import web

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_URL") + WEBHOOK_PATH

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Подключение к Redis и очередь задач
redis_conn = Redis.from_url(os.getenv("REDIS_URL"))
queue = Queue(connection=redis_conn)

# Хендлер /start
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Привет! Отправьте ссылку на видео или название трека/альбома."
    )

# Хендлер для текста (ссылки)
@dp.message()
async def handle_link(message: Message):
    url = message.text
    # Добавляем задачу в очередь
    job = queue.enqueue(download_job, url, message.chat.id)
    await message.answer(f"Задача принята! ID: {job.id}")

# aiohttp сервер для webhook
async def handle_webhook(request):
    try:
        data = await request.json()
        update = types.Update(**data)
        await dp.feed_update(update)
    except Exception as e:
        print(f"Ошибка webhook: {e}")
    return web.Response(text="OK")

async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(app):
    await bot.delete_webhook()
    await bot.session.close()

app = web.Application()
app.router.add_post(WEBHOOK_PATH, handle_webhook)
app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    web.run_app(app, host="0.0.0.0", port=port)
