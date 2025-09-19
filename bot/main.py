import os
from aiogram import Bot, Dispatcher, types
from aiogram.utils.executor import start_webhook
from redis import Redis
from rq import Queue
from downloader.task import download_job

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_URL") + "/webhook"

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# Подключение к Redis и очередь задач
redis_conn = Redis.from_url(os.getenv("REDIS_URL"))
queue = Queue(connection=redis_conn)

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Отправьте ссылку на видео или название трека/альбома."
    )

@dp.message_handler()
async def handle_link(message: types.Message):
    url = message.text
    # Добавляем задачу в очередь
    job = queue.enqueue(download_job, url, message.chat.id)
    await message.answer(f"Задача принята! ID: {job.id}")

async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(dp):
    await bot.delete_webhook()

if __name__ == "__main__":
    start_webhook(
        dispatcher=dp,
        webhook_path="/webhook",
        skip_updates=True,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
    )
