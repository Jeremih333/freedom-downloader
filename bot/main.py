import sys
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from redis import Redis
from rq import Queue
from downloader.task import download_job
from aiohttp import web

# ========================
# Проверка переменных окружения
# ========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
REDIS_URL = os.getenv("REDIS_URL")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")
PORT = int(os.environ.get("PORT", 10000))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан в переменных окружения")
if not REDIS_URL:
    raise RuntimeError("REDIS_URL не задан в переменных окружения")
if not RENDER_URL:
    raise RuntimeError("RENDER_EXTERNAL_URL не задана в переменных окружения")

WEBHOOK_URL = RENDER_URL + "/webhook"

# ========================
# Добавляем корень проекта в sys.path
# ========================
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
# Обработка апдейтов через aiohttp
# ========================
async def handle_webhook(request: web.Request):
    try:
        data = await request.json()
        print("Webhook received:", data)  # лог апдейта
        update = types.Update(**data)
        await dp.feed_update(update, bot)  # <-- Важно: передаём bot
        return web.Response(text="OK")
    except Exception as e:
        print("Webhook error:", e)
        return web.Response(status=500, text="Error")

# ========================
# Запуск Aiohttp веб-сервера
# ========================
async def init_app():
    app = web.Application()
    app.router.add_post("/webhook", handle_webhook)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_shutdown)
    return app

if __name__ == "__main__":
    web.run_app(init_app(), host="0.0.0.0", port=PORT)
