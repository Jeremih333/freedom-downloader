from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def build_main_keyboard() -> InlineKeyboardMarkup:
    """Главное меню."""
    keyboard = [
        [InlineKeyboardButton(text="🔍 Поиск", callback_data="search")],
        [InlineKeyboardButton(text="📂 Мои загрузки", callback_data="downloads")],
        [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_format_keyboard(video_id: str) -> InlineKeyboardMarkup:
    """Кнопки выбора формата для загрузки."""
    keyboard = [
        [
            InlineKeyboardButton(text="🎵 MP3", callback_data=f"format:mp3:{video_id}"),
            InlineKeyboardButton(text="🎬 MP4", callback_data=f"format:mp4:{video_id}"),
        ],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def build_pagination_keyboard(page: int, total_pages: int) -> InlineKeyboardMarkup:
    """Клавиатура для переключения страниц поиска/результатов."""
    buttons = []

    if page > 1:
        buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"page:{page-1}"))

    buttons.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))

    if page < total_pages:
        buttons.append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"page:{page+1}"))

    return InlineKeyboardMarkup(inline_keyboard=[buttons])


def build_back_keyboard(callback: str = "back_to_main") -> InlineKeyboardMarkup:
    """Простая кнопка 'Назад'."""
    keyboard = [
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=callback)]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
