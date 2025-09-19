import os
import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

TOKEN = os.getenv("BOT_TOKEN", "8124694420:AAF_JEs9oG3MxJzvx0X_9Vebxq0B5Fv0KUA")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"https://freedom-downloader-2duc.onrender.com{WEBHOOK_PATH}"

bot = Bot(token=TOKEN)
dp = Dispatcher()


# === HANDLERS ===
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Привет! Я бот для скачивания медиа. Отправь ссылку или запрос 🔗")


@dp.message()
async def handle_message(message: types.Message):
    await message.answer(f"Ты прислал: {message.text}")


# === WEBHOOK ===
async def handle_webhook(request: web.Request):
    try:
        data = await request.json()
        print("Webhook received:", data)  # Логируем апдейт
        update = types.Update(**data)
        await dp.feed_update(bot, update)  # ✅ правильный вызов
        return web.Response(text="OK")
    except Exception as e:
        print("Webhook error:", e)
        return web.Response(status=500, text="Error")


async def on_startup(app: web.Application):
    # Удаляем старые вебхуки
    await bot.delete_webhook(drop_pending_updates=True)
    # Ставим новый
    await bot.set_webhook(WEBHOOK_URL)
    print(f"Webhook установлен: {WEBHOOK_URL}")


async def on_shutdown(app: web.Application):
    await bot.session.close()


def init_app():
    app = web.Application()
    app.router.add_post(WEBHOOK_PATH, handle_webhook)
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_shutdown)
    return app


if __name__ == "__main__":
    web.run_app(init_app(), host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
