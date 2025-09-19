from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def build_format_keyboard(video_id: str) -> InlineKeyboardMarkup:
    """
    Клавиатура выбора формата (аудио / видео).
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎵 MP3", callback_data=f"format:mp3:{video_id}"),
                InlineKeyboardButton(text="🎥 MP4", callback_data=f"format:mp4:{video_id}"),
            ]
        ]
    )


def build_pagination_keyboard(current_page: int, total_pages: int) -> InlineKeyboardMarkup:
    """
    Клавиатура пагинации с кнопками назад/вперёд.
    """
    buttons = []

    if current_page > 1:
        buttons.append(
            InlineKeyboardButton(text="⬅️ Назад", callback_data=f"page:{current_page - 1}")
        )

    buttons.append(
        InlineKeyboardButton(text=f"{current_page}/{total_pages}", callback_data="noop")
    )

    if current_page < total_pages:
        buttons.append(
            InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"page:{current_page + 1}")
        )

    return InlineKeyboardMarkup(inline_keyboard=[buttons])


def build_back_keyboard(callback: str = "back") -> InlineKeyboardMarkup:
    """
    Клавиатура только с кнопкой 'Назад'.
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=callback)]
        ]
    )


def build_results_keyboard(results: list[dict], page: int = 1, per_page: int = 5) -> InlineKeyboardMarkup:
    """
    Клавиатура для отображения списка результатов (поиск).
    results: список словарей вида {"title": str, "id": str}
    """
    start = (page - 1) * per_page
    end = start + per_page
    page_results = results[start:end]

    keyboard = []

    for item in page_results:
        keyboard.append([
            InlineKeyboardButton(
                text=item["title"],
                callback_data=f"select:{item['id']}"
            )
        ])

    total_pages = (len(results) + per_page - 1) // per_page
    if total_pages > 1:
        keyboard.append([
            InlineKeyboardButton(
                text=f"⬅️ {page - 1}" if page > 1 else " ",
                callback_data=f"page:{page - 1}" if page > 1 else "noop"
            ),
            InlineKeyboardButton(
                text=f"{page}/{total_pages}",
                callback_data="noop"
            ),
            InlineKeyboardButton(
                text=f"{page + 1} ➡️" if page < total_pages else " ",
                callback_data=f"page:{page + 1}" if page < total_pages else "noop"
            ),
        ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)
