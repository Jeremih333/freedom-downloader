import sys
import os

# Добавляем корень проекта в путь поиска модулей
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from redis import Redis
from rq import Queue
from downloader.task import download_job
from aiohttp import web
import asyncio

# ========================
# Переменные окружения
# ========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_URL") + "/webhook"
PORT = int(os.environ.get("PORT", 10000))
REDIS_URL = os.getenv("REDIS_URL")

# ========================
# Инициализация бота и диспетчера
# ========================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ========================
# Подключение к Redis и очередь задач
# ========================
redis_conn = Redis.from_url(REDIS_URL)
queue = Queue(connection=redis_conn)

# ========================
# Обработчики команд
# ========================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Отправьте ссылку на видео или название трека/альбома."
    )

@dp.message()
async def handle_link(message: types.Message):
    url = message.text.strip()
    if not url:
        await message.answer("Пустая ссылка или название. Попробуйте снова.")
        return
    # Добавляем задачу в очередь
    job = queue.enqueue(download_job, url, message.chat.id)
    await message.answer(f"Задача принята! ID: {job.id}")

# ========================
# Функции для webhook
# ========================
async def on_startup(app: web.Application):
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(app: web.Application):
    await bot.delete_webhook()
    await bot.session.close()

# ========================
# Запуск Aiohttp веб-сервера для webhook
# ========================
async def init_app():
    app = web.Application()
    app.router.add_post("/webhook", lambda request: dp.process_update(request))
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_shutdown)
    return app

if __name__ == "__main__":
    web.run_app(init_app(), host="0.0.0.0", port=PORT)
