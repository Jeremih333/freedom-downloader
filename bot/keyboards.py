from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from math import ceil
import html

def build_format_keyboard(options: list, token_id: int = 0) -> InlineKeyboardMarkup:
    """
    options: [{'id':format_id, 'label':str, 'url':url}, ...]
    token_id: used for tying callbacks to message to help stateless operations if needed
    """
    kb = InlineKeyboardMarkup(row_width=2)
    for opt in options:
        cb = f"FORMAT|{opt['url']}|{opt['id']}"
        kb.insert(InlineKeyboardButton(text=opt['label'], callback_data=cb))
    kb.insert(InlineKeyboardButton(text="Отмена ❌", callback_data="CANCEL"))
    return kb


def build_search_results_keyboard(results: list, pagination: dict, token_id: int = 0) -> InlineKeyboardMarkup:
    """
    results: [{'title':..., 'uploader':..., 'url':..., 'id':...}, ...]
    pagination: {'prev':callback_data, 'next':callback_data, 'page':int}
    """
    kb = InlineKeyboardMarkup(row_width=1)
    for r in results:
        title = r.get("title", "")[:55]
        uploader = r.get("uploader", "")
        cb = f"FORMAT|{r['url']}|best"
        kb.insert(InlineKeyboardButton(text=f"{title} — {uploader}", callback_data=cb))
    # pagination row
    row = []
    if pagination.get("prev"):
        row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=pagination["prev"]))
    if pagination.get("next"):
        row.append(InlineKeyboardButton(text="Ещё ▶️", callback_data=pagination["next"]))
    if row:
        kb.row(*row)
    kb.insert(InlineKeyboardButton(text="🔎 Новый поиск", callback_data="NEW_SEARCH"))
    return kb


def build_album_keyboard(album_meta: dict, token_id: int = 0) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    kb.insert(InlineKeyboardButton(text="Скачать весь альбом ▶️", callback_data=f"ALBUM_DOWNLOAD|{album_meta['id']}"))
    for t in album_meta.get("tracks", []):
        cb = f"FORMAT|{t['url']}|audio_mp3_320"
        kb.insert(InlineKeyboardButton(text=t['title'], callback_data=cb))
    kb.insert(InlineKeyboardButton(text="⬅️ Назад", callback_data="BACK"))
    return kb
