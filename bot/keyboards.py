# bot/keyboards.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict, Tuple


def build_format_keyboard(formats: List[Dict], token_id: int) -> InlineKeyboardMarkup:
    """
    Клавиатура для выбора формата (например, видео 720p, аудио mp3).
    formats: список словарей {"format_id": str, "ext": str, "resolution": str}
    """
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for fmt in formats:
        text = f"{fmt.get('ext', '')} {fmt.get('resolution', '')}".strip()
        callback = f"FORMAT|{fmt['url']}|{fmt['format_id']}"
        kb.inline_keyboard.append([InlineKeyboardButton(text=text, callback_data=callback)])
    return kb


def build_search_results_keyboard(
    results: List[Dict],
    pagination: Tuple[int, int, int],
    token_id: int
) -> InlineKeyboardMarkup:
    """
    Клавиатура для результатов поиска YouTube.
    results: [{"title": str, "url": str}]
    pagination: (page, total_pages, per_page)
    """
    page, total_pages, _ = pagination
    kb = InlineKeyboardMarkup(inline_keyboard=[])

    # результаты поиска
    for r in results:
        kb.inline_keyboard.append([
            InlineKeyboardButton(text=r["title"], callback_data=f"FORMAT|{r['url']}|best")
        ])

    # пагинация
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"SEARCHPAGE|{r['query']}|{page-1}"))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"SEARCHPAGE|{r['query']}|{page+1}"))

    if nav:
        kb.inline_keyboard.append(nav)

    return kb


def build_album_keyboard(meta: Dict, token_id: int) -> InlineKeyboardMarkup:
    """
    Клавиатура для альбома (скачать весь альбом или треки по отдельности).
    meta: {"id": str, "title": str, "tracks": [{"title": str, "url": str}]}
    """
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬇️ Скачать альбом", callback_data=f"ALBUM_DOWNLOAD|{meta['id']}")]
    ])

    for track in meta.get("tracks", []):
        kb.inline_keyboard.append([
            InlineKeyboardButton(text=track["title"], callback_data=f"FORMAT|{track['url']}|best")
        ])
    return kb


def build_pagination_keyboard(query: str, page: int, total_pages: int) -> InlineKeyboardMarkup:
    """
    Общая пагинация (например, при поиске).
    """
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"SEARCHPAGE|{query}|{page-1}"))
    nav.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="IGNORE"))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"SEARCHPAGE|{query}|{page+1}"))
    kb.inline_keyboard.append(nav)
    return kb
