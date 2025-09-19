import logging
from aiogram import Dispatcher
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command

from bot.keyboards import (
    build_format_keyboard,
    build_search_results_keyboard,
    build_album_keyboard,
    build_pagination_keyboard,
)
from bot.state import DownloadStates
from bot.messages import (
    MSG_WELCOME,
    MSG_SELECT_FORMAT,
    MSG_JOB_QUEUED,
    MSG_UNKNOWN_ACTION,
)
from bot.utils import (
    is_url,
    probe_formats_async,
    enqueue_download_task,
    search_youtube_async,
    get_album_meta_async,
)

logger = logging.getLogger("bot.handlers")


def register_handlers(dp: Dispatcher):
    dp.message.register(cmd_start, Command("start"))
    dp.message.register(handle_text)
    dp.callback_query.register(handle_callback)


async def cmd_start(message: Message):
    await message.reply(MSG_WELCOME)
    await DownloadStates.waiting_for_link.set()


async def handle_text(message: Message):
    text = message.text.strip()
    if is_url(text):
        # Ссылка → получаем форматы
        opts = await probe_formats_async(text)
        if not opts:
            await message.reply(
                "Не удалось получить форматы для этой ссылки. "
                "Попробуйте другую или отправьте текстовый запрос."
            )
            return
        kb = build_format_keyboard(opts, token_id=message.message_id)
        await message.reply(MSG_SELECT_FORMAT, reply_markup=kb)
        await DownloadStates.waiting_for_format.set()
        return

    # Текстовый поиск
    query = text
    results, pagination = await search_youtube_async(query, page=1)
    if not results:
        await message.reply(f"По запросу '{query}' ничего не найдено.")
        return
    kb = build_search_results_keyboard(results, pagination, token_id=message.message_id)
    await message.reply(f"Результаты поиска для «{query}»:",
                        reply_markup=kb)
    await DownloadStates.waiting_for_format.set()


async def handle_callback(callback: CallbackQuery):
    data = callback.data or ""

    # FORMAT|<url>|<format_id>
    if data.startswith("FORMAT|"):
        _, url, fmt = data.split("|", 2)
        await callback.answer("Запускаю загрузку...")
        enqueue_download_task(url, fmt, callback.from_user.id)
        await callback.message.reply(MSG_JOB_QUEUED)
        return

    # SEARCHPAGE|<query>|<page>
    if data.startswith("SEARCHPAGE|"):
        _, query, page = data.split("|", 2)
        results, pagination = await search_youtube_async(query, page=int(page))
        kb = build_search_results_keyboard(results, pagination, token_id=callback.message.message_id)
        await callback.message.edit_reply_markup(reply_markup=kb)
        await callback.answer()
        return

    # ALBUM|<album_id>
    if data.startswith("ALBUM|"):
        _, album_id = data.split("|", 1)
        meta = await get_album_meta_async(album_id)
        kb = build_album_keyboard(meta, token_id=callback.message.message_id)
        await callback.message.reply(f"Альбом: {meta['title']}", reply_markup=kb)
        await callback.answer()
        return

    # ALBUM_DOWNLOAD|<album_id>
    if data.startswith("ALBUM_DOWNLOAD|"):
        _, album_id = data.split("|", 1)
        await callback.answer("Поставил задачу на скачивание альбома...")
        enqueue_download_task(album_id, "album", callback.from_user.id)
        await callback.message.reply(MSG_JOB_QUEUED)
        return

    await callback.answer(MSG_UNKNOWN_ACTION, show_alert=True)
