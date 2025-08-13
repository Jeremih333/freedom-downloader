import os
import re
import logging
import asyncio
from datetime import datetime
from io import BytesIO

import requests
from PIL import Image
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaAudio,
    InputMediaVideo,
    BotCommand
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
from yt_dlp import YoutubeDL
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB
from moviepy.editor import VideoFileClip, AudioFileClip

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
PORT = int(os.environ.get("PORT", 5000))
TOKEN = os.environ["TOKEN"]
SUPPORT_CHAT_LINK = "https://t.me/freedom346"

# Глобальные переменные для управления состоянием
USER_STATES = {}
SEARCH_RESULTS = {}
SEARCH_PAGE = {}

# Поддерживаемые платформы
SUPPORTED_PLATFORMS = [
    "youtube.com", 
    "youtu.be",
    "pinterest.com",
    "yandex.ru",
    "vk.com",
    "tiktok.com",
    "instagram.com",
    "spotify.com"
]

class MediaProcessor:
    @staticmethod
    def download_media(url: str, media_type: str = "audio") -> tuple:
        ydl_opts = {
            "format": "bestaudio/best" if media_type == "audio" else "bestvideo+bestaudio",
            "outtmpl": "%(title)s.%(ext)s",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }] if media_type == "audio" else [],
            "writethumbnail": True,
            "ignoreerrors": True
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            if media_type == "audio":
                filename = filename.replace(".webm", ".mp3").replace(".m4a", ".mp3")
            
            thumbnail_path = filename.rsplit(".", 1)[0] + ".webp"
            
            # Конвертируем thumbnail в JPG
            if os.path.exists(thumbnail_path):
                img = Image.open(thumbnail_path)
                jpg_path = thumbnail_path.replace(".webp", ".jpg")
                img.convert("RGB").save(jpg_path, "JPEG")
                thumbnail_path = jpg_path
            
            return filename, thumbnail_path, info

    @staticmethod
    def add_metadata(file_path: str, thumbnail_path: str, info: dict):
        if file_path.endswith(".mp3"):
            audio = MP3(file_path, ID3=ID3)
            try:
                audio.add_tags()
            except:
                pass

            audio.tags.add(
                APIC(
                    encoding=3,
                    mime="image/jpeg",
                    type=3,
                    desc="Cover",
                    data=open(thumbnail_path, "rb").read()
                )
            )
            audio.tags.add(TIT2(encoding=3, text=info.get("title", "")))
            audio.tags.add(TPE1(encoding=3, text=info.get("uploader", "")))
            audio.tags.add(TALB(encoding=3, text=info.get("album", "")))
            audio.save()

    @staticmethod
    def trim_media(file_path: str, start: float, end: float = None):
        output_path = file_path.replace(".", "_trimmed.")
        
        if file_path.endswith(".mp4") or file_path.endswith(".mkv"):
            clip = VideoFileClip(file_path).subclip(start, end)
            clip.write_videofile(output_path, codec="libx264", audio_codec="aac")
            clip.close()
        else:
            clip = AudioFileClip(file_path).subclip(start, end)
            clip.write_audiofile(output_path)
            clip.close()
            
        return output_path

    @staticmethod
    def parse_time(time_str: str) -> float:
        if ":" in time_str:
            parts = time_str.split(":")
            if len(parts) == 2:
                return float(parts[0]) * 60 + float(parts[1])
            elif len(parts) == 3:
                return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        return float(time_str)

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "🌟 Добро пожаловать в Media Downloader Bot!\n\n"
        "Я могу скачивать контент с различных платформ:\n"
        "- YouTube\n- TikTok\n- Instagram\n- Spotify\n- VK\n- Pinterest\n- Яндекс\n\n"
        "Просто отправьте мне ссылку или название трека для поиска!\n\n"
        "После скачивания вы можете конвертировать файл или обрезать его.\n\n"
        f"Присоединяйтесь к нашему чату: {SUPPORT_CHAT_LINK}"
    )
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔍 Поиск музыки", switch_inline_query_current_chat="")],
            [InlineKeyboardButton("💬 Чат поддержки", url=SUPPORT_CHAT_LINK)]
        ])
    )

# Обработчик текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text
    chat_id = update.message.chat_id
    
    # Проверка на ссылку
    if any(domain in user_input for domain in SUPPORTED_PLATFORMS):
        USER_STATES[chat_id] = {"url": user_input}
        await show_conversion_options(update)
    else:
        # Поиск музыки
        await search_music(update, user_input)

# Показать варианты конвертации
async def show_conversion_options(update: Update):
    keyboard = [
        [
            InlineKeyboardButton("🎵 Аудио", callback_data="convert_audio"),
            InlineKeyboardButton("🎥 Видео", callback_data="convert_video"),
        ],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel")]
    ]
    
    await update.message.reply_text(
        "Выберите формат для скачивания:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# Обработка выбора конвертации
async def handle_conversion_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    choice = query.data.split("_")[1]
    
    if choice == "cancel":
        await query.edit_message_text("Операция отменена.")
        return
    
    url = USER_STATES.get(chat_id, {}).get("url")
    if not url:
        await query.edit_message_text("Ошибка: URL не найден.")
        return
    
    await query.edit_message_text(f"⏳ Начинаю обработку {'аудио' if choice == 'audio' else 'видео'}...")
    
    try:
        file_path, thumbnail_path, info = MediaProcessor.download_media(url, choice)
        
        if choice == "audio":
            MediaProcessor.add_metadata(file_path, thumbnail_path, info)
        
        # Отправка файла
        with open(file_path, "rb") as media_file:
            caption = f"{info.get('title', '')}\n\nПрисоединяйтесь к нашему чату: {SUPPORT_CHAT_LINK}"
            
            if choice == "audio":
                await context.bot.send_audio(
                    chat_id,
                    audio=media_file,
                    caption=caption,
                    thumb=open(thumbnail_path, "rb") if os.path.exists(thumbnail_path) else None,
                    title=info.get("title", ""),
                    performer=info.get("uploader", "")
                )
            else:
                await context.bot.send_video(
                    chat_id,
                    video=media_file,
                    caption=caption,
                    thumb=open(thumbnail_path, "rb") if os.path.exists(thumbnail_path) else None,
                    supports_streaming=True
                )
        
        # Предложение обрезать файл
        keyboard = [
            [InlineKeyboardButton("✂️ Обрезать файл", callback_data="trim_media")],
            [InlineKeyboardButton("✅ Готово", callback_data="done")]
        ]
        
        await query.message.reply_text(
            "Файл успешно отправлен! Хотите обрезать его?",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # Сохраняем информацию о файле
        USER_STATES[chat_id] = {
            "file_path": file_path,
            "media_type": choice,
            "info": info
        }
        
        # Удаление временных файлов
        os.remove(file_path)
        if os.path.exists(thumbnail_path):
            os.remove(thumbnail_path)
            
    except Exception as e:
        logger.error(f"Ошибка обработки медиа: {e}")
        await query.edit_message_text("❌ Произошла ошибка при обработке файла.")

# Поиск музыки
async def search_music(update: Update, query: str):
    chat_id = update.message.chat_id
    await update.message.reply_text(f"🔍 Ищу музыку по запросу: {query}...")
    
    try:
        ydl_opts = {
            "format": "bestaudio/best",
            "default_search": "ytsearch10",
            "quiet": True
        }
        
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch10:{query}", download=False)
            if not info or "entries" not in info:
                await update.message.reply_text("Ничего не найдено 😔")
                return
                
            tracks = info["entries"]
            SEARCH_RESULTS[chat_id] = tracks
            SEARCH_PAGE[chat_id] = 0
            
            await show_search_results(update, chat_id, 0)
            
    except Exception as e:
        logger.error(f"Ошибка поиска: {e}")
        await update.message.reply_text("❌ Произошла ошибка при поиске.")

# Показать результаты поиска
async def show_search_results(update: Update, chat_id: int, page: int):
    tracks = SEARCH_RESULTS.get(chat_id, [])
    if not tracks:
        return
        
    page_size = 5
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, len(tracks))
    page_tracks = tracks[start_idx:end_idx]
    
    if not page_tracks:
        await update.message.reply_text("Больше результатов нет.")
        return
    
    keyboard = []
    for track in page_tracks:
        title = track.get("title", "Без названия")[:30] + "..." if len(track.get("title", "")) > 30 else track.get("title", "Без названия")
        keyboard.append([InlineKeyboardButton(
            f"🎵 {title}",
            callback_data=f"track_{track['id']}"
        )])
    
    # Кнопки навигации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Назад", callback_data=f"page_{page-1}"))
    if end_idx < len(tracks):
        nav_buttons.append(InlineKeyboardButton("Вперед ▶️", callback_data=f"page_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([
        InlineKeyboardButton("⬇️ Скачать все", callback_data="download_all"),
        InlineKeyboardButton("🎧 Альбомы", callback_data="albums")
    ])
    
    message_text = f"🔍 Результаты поиска (страница {page+1}):"
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            message_text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            message_text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# Обработка обрезки медиа
async def handle_trim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    
    await query.edit_message_text(
        "✂️ Введите временной диапазон для обрезки в формате:\n"
        "Примеры:\n"
        "0 (от начала до конца)\n"
        "5 (от 5 секунды до конца)\n"
        "2:33 (от 2:33 до конца)\n"
        "0-5 (первые 5 секунд)\n"
        "1:32-5:48 (от 1:32 до 5:48)\n"
        "0.55-2:3.75 (от 55 сотых секунды до 2 минут 3 секунд и 75 сотых)"
    )
    
    USER_STATES[chat_id]["waiting_for_trim"] = True

# Обработка ввода временного диапазона
async def handle_time_range(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user_state = USER_STATES.get(chat_id, {})
    
    if not user_state.get("waiting_for_trim"):
        return
        
    time_range = update.message.text
    file_path = user_state.get("file_path")
    media_type = user_state.get("media_type")
    
    if not file_path or not media_type:
        await update.message.reply_text("Ошибка: информация о файле отсутствует.")
        return
        
    try:
        if "-" in time_range:
            start_str, end_str = time_range.split("-")
            start_time = MediaProcessor.parse_time(start_str)
            end_time = MediaProcessor.parse_time(end_str)
        else:
            start_time = MediaProcessor.parse_time(time_range)
            end_time = None
            
        await update.message.reply_text("⏳ Обрезаю файл...")
        
        # Выполняем обрезку
        trimmed_path = MediaProcessor.trim_media(file_path, start_time, end_time)
        
        # Отправка обрезанного файла
        with open(trimmed_path, "rb") as media_file:
            caption = f"✂️ Обрезанный файл\n\nПрисоединяйтесь к нашему чату: {SUPPORT_CHAT_LINK}"
            
            if media_type == "audio":
                await context.bot.send_audio(
                    chat_id,
                    audio=media_file,
                    caption=caption
                )
            else:
                await context.bot.send_video(
                    chat_id,
                    video=media_file,
                    caption=caption,
                    supports_streaming=True
                )
        
        # Удаление временных файлов
        os.remove(trimmed_path)
        if os.path.exists(file_path):
            os.remove(file_path)
            
        del USER_STATES[chat_id]["waiting_for_trim"]
        
    except Exception as e:
        logger.error(f"Ошибка обрезки: {e}")
        await update.message.reply_text("❌ Ошибка при обработке временного диапазона.")

# Обработка инлайн-кнопок
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat_id
    
    if data.startswith("convert_"):
        await handle_conversion_choice(update, context)
    elif data == "trim_media":
        await handle_trim(update, context)
    elif data.startswith("track_"):
        track_id = data.split("_")[1]
        await download_track(update, track_id)
    elif data.startswith("page_"):
        page = int(data.split("_")[1])
        SEARCH_PAGE[chat_id] = page
        await show_search_results(update, chat_id, page)
    elif data == "download_all":
        await download_all_tracks(update, chat_id)

# Скачать конкретный трек
async def download_track(update: Update, track_id: str):
    query = update.callback_query
    chat_id = query.message.chat_id
    tracks = SEARCH_RESULTS.get(chat_id, [])
    
    track = next((t for t in tracks if t.get("id") == track_id), None)
    if not track:
        await query.edit_message_text("Трек не найден.")
        return
        
    await query.edit_message_text(f"⏳ Скачиваю: {track['title']}...")
    
    try:
        url = track.get("url") or f"https://youtu.be/{track_id}"
        file_path, thumbnail_path, info = MediaProcessor.download_media(url, "audio")
        MediaProcessor.add_metadata(file_path, thumbnail_path, info)
        
        with open(file_path, "rb") as audio_file:
            await context.bot.send_audio(
                chat_id,
                audio=audio_file,
                caption=f"🎵 {track['title']}\n\nПрисоединяйтесь к нашему чату: {SUPPORT_CHAT_LINK}",
                thumb=open(thumbnail_path, "rb") if os.path.exists(thumbnail_path) else None,
                title=track.get("title", ""),
                performer=track.get("uploader", "")
            )
        
        # Удаление временных файлов
        os.remove(file_path)
        if os.path.exists(thumbnail_path):
            os.remove(thumbnail_path)
            
    except Exception as e:
        logger.error(f"Ошибка скачивания трека: {e}")
        await query.edit_message_text("❌ Ошибка при скачивании трека.")

# Скачать все треки на странице
async def download_all_tracks(update: Update, chat_id: int):
    query = update.callback_query
    await query.edit_message_text("⏳ Начинаю скачивание всех треков...")
    
    tracks = SEARCH_RESULTS.get(chat_id, [])
    page = SEARCH_PAGE.get(chat_id, 0)
    page_size = 5
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, len(tracks))
    page_tracks = tracks[start_idx:end_idx]
    
    for track in page_tracks:
        try:
            url = track.get("url") or f"https://youtu.be/{track['id']}"
            file_path, thumbnail_path, info = MediaProcessor.download_media(url, "audio")
            MediaProcessor.add_metadata(file_path, thumbnail_path, info)
            
            with open(file_path, "rb") as audio_file:
                await context.bot.send_audio(
                    chat_id,
                    audio=audio_file,
                    caption=f"🎵 {track['title']}\n\nПрисоединяйтесь к нашему чату: {SUPPORT_CHAT_LINK}",
                    thumb=open(thumbnail_path, "rb") if os.path.exists(thumbnail_path) else None
                )
            
            os.remove(file_path)
            if os.path.exists(thumbnail_path):
                os.remove(thumbnail_path)
                
            await asyncio.sleep(2)  # Задержка между отправками
                
        except Exception as e:
            logger.error(f"Ошибка скачивания трека {track['title']}: {e}")
            continue
    
    await query.edit_message_text("✅ Все треки страницы успешно отправлены!")

# Основная функция
def main():
    application = Application.builder().token(TOKEN).build()
    
    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"(\d+:\d+|\d+\.\d+|\d+)-?(\d+:\d+|\d+\.\d+|\d+)?"), handle_time_range))
    
    # Запуск бота на Render
    if "RENDER" in os.environ:
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=TOKEN,
            webhook_url=f"https://your-render-app-name.onrender.com/{TOKEN}"
        )
    else:
        application.run_polling()

if __name__ == "__main__":
    main()
