import os
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import Update

from bot.handlers import register_handlers

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bot.main")

TOKEN = os.getenv("BOT_TOKEN")
PORT = int(os.getenv("PORT", 10000))
RENDER_EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL")
WEBHOOK_PATH = f"/webhook/{TOKEN}"

if not TOKEN or not RENDER_EXTERNAL_URL:
    logger.error("BOT_TOKEN and RENDER_EXTERNAL_URL must be set")
    raise SystemExit(1)


async def handle_update(request: web.Request):
    data = await request.json()
    update = Update(**data)
    await request.app["dp"].feed_webhook_update(request.app["bot"], update)
    return web.Response(text="ok")


async def on_startup(app: web.Application):
    bot: Bot = app["bot"]
    webhook_url = f"{RENDER_EXTERNAL_URL}{WEBHOOK_PATH}"
    await bot.set_webhook(webhook_url, drop_pending_updates=True)
    logger.info("Webhook set: %s", webhook_url)


async def on_shutdown(app: web.Application):
    bot: Bot = app["bot"]
    await bot.delete_webhook()
    await bot.session.close()


def create_app():
    session = AiohttpSession()
    bot = Bot(token=TOKEN, session=session)
    dp = Dispatcher()

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
