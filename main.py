#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import logging
import asyncio
import subprocess
import tempfile
import shutil
from datetime import datetime
from io import BytesIO
import random
import string
import time
import json
from typing import Optional, Tuple, Dict, Any, List

import requests
from PIL import Image
from pathlib import Path
from urllib.parse import quote_plus

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
    InputFile
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
from yt_dlp import YoutubeDL, DownloadError
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB

# ---------- Настройка логирования ----------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------- Конфигурация ----------
PORT = int(os.environ.get("PORT", 5000))
TOKEN = os.environ.get("TOKEN")
if not TOKEN:
    logger.critical("Environment variable TOKEN is required. Exiting.")
    raise SystemExit("TOKEN environment variable is not set")

SUPPORT_CHAT_LINK = os.environ.get("SUPPORT_CHAT_LINK", "https://t.me/freedom346")
YOUTUBE_COOKIES = os.environ.get("YOUTUBE_COOKIES") or None
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", 3))
RETRY_DELAY = float(os.environ.get("RETRY_DELAY", 5))

# ---------- Состояния ----------
USER_STATES: Dict[int, Dict[str, Any]] = {}
SEARCH_RESULTS: Dict[int, List[Dict[str, Any]]] = {}
SEARCH_PAGE: Dict[int, int] = {}

# ---------- Поддерживаемые платформы ----------
SUPPORTED_PLATFORMS = [
    "youtube.com",
    "youtu.be",
    "pinterest.com",
    "yandex.ru",
    "vk.com",
    "tiktok.com",
    "instagram.com",
    "spotify.com",
    "deezer.com",
    "yandex.music",
    "music.yandex.ru"
]


# ---------- Утилиты ----------
def get_chat_id_from_update(update: Update) -> int:
    if update.effective_chat:
        return update.effective_chat.id
    if update.message and update.message.chat:
        return update.message.chat.id
    if update.callback_query and update.callback_query.message and update.callback_query.message.chat:
        return update.callback_query.message.chat.id
    raise ValueError("Cannot determine chat_id from update")


def safe_remove(path: Optional[str]):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        logger.exception(f"Failed to remove file: {path}")


async def run_blocking(func, *args, **kwargs):
    """Запуск блокирующей функции в пуле потоков."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


# ---------- Класс обработки медиа ----------
class MediaProcessor:
    @staticmethod
    def _base_ydl_opts(audio_only: bool = True) -> dict:
        opts = {
            "format": "bestaudio/best" if audio_only else "bestvideo+bestaudio/best",
            "outtmpl": "%(title)s.%(ext)s",
            "writethumbnail": True,
            "ignoreerrors": True,
            "source_address": "0.0.0.0",
            "force_ipv4": True,
            "retries": 10,
            "fragment_retries": 10,
            "skip_unavailable_fragments": True,
            "sleep_interval": 5,
            "max_sleep_interval": 30,
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "quiet": True,
        }
        if YOUTUBE_COOKIES:
            opts["cookiefile"] = YOUTUBE_COOKIES
        return opts

    @staticmethod
    def download_media(url: str, media_type: str = "audio") -> Tuple[str, Optional[str], Dict[str, Any]]:
        """
        Скачивает медиа (audio/video). Возвращает (file_path, thumbnail_path_or_None, info_dict)
        Бросает исключение в случае фатальной ошибки.
        """
        audio_only = (media_type == "audio")
        ydl_opts = MediaProcessor._base_ydl_opts(audio_only=audio_only)

        if audio_only:
            # Постобработка для извлечения аудио в mp3
            ydl_opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]
        # Временно включаем writethumbnail, quiet handled above

        retries = 0
        last_exc = None
        while retries < MAX_RETRIES:
            try:
                with YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    if not info:
                        raise DownloadError("yt-dlp returned no info")

                    # Если плейлист (избегаем, ожидаем один элемент)
                    if info.get("_type") == "playlist":
                        # Берём первый элемент если есть
                        entries = info.get("entries") or []
                        if not entries:
                            raise DownloadError("Playlist is empty")
                        info = entries[0]  # использовать первый элемент

                    # Попытка получить путь к файлу
                    try:
                        filename = ydl.prepare_filename(info)
                    except Exception:
                        # В некоторых случаях prepare_filename не работает напрямую; пытаемся собрать вручную
                        ext = "mp3" if audio_only else info.get("ext", "mp4")
                        # sanitize title fallback
                        title = (info.get("title") or "file").replace("/", "_")
                        filename = f"{title}.{ext}"

                    # Если postprocessor конвертировал в mp3, заменяем расширение корректно
                    if audio_only:
                        filename = filename.rsplit(".", 1)[0] + ".mp3"

                    thumbnail_path = None
                    # Обычно yt-dlp создаёт thumb с тем же базовым именем и webp/jpeg/png
                    base_no_ext = filename.rsplit(".", 1)[0]
                    for ext in ("webp", "jpg", "jpeg", "png"):
                        candidate = f"{base_no_ext}.{ext}"
                        if os.path.exists(candidate):
                            # Конвертируем webp в jpg, оставляя jpg/png как есть
                            if candidate.endswith(".webp"):
                                try:
                                    img = Image.open(candidate)
                                    jpg_path = f"{base_no_ext}.jpg"
                                    img.convert("RGB").save(jpg_path, "JPEG")
                                    safe_remove(candidate)
                                    thumbnail_path = jpg_path
                                except Exception:
                                    logger.exception("Failed to convert thumbnail webp -> jpg")
                                    thumbnail_path = candidate
                            else:
                                thumbnail_path = candidate
                            break

                    return filename, thumbnail_path, info

            except Exception as e:
                last_exc = e
                logger.warning(f"download_media attempt {retries+1} failed: {e}")
                # Если это 429-like или временная сет. ошибка — попытаться повторить
                retries += 1
                if retries < MAX_RETRIES:
                    time.sleep(RETRY_DELAY)
                else:
                    logger.exception("All download attempts failed")
                    raise

        # Если цикл вышел по ошибке
        raise last_exc or Exception("Unknown download error")

    @staticmethod
    def add_metadata(file_path: str, thumbnail_path: Optional[str], info: Dict[str, Any]):
        """
        Добавляет ID3 теги и обложку для mp3.
        Мягко пропускает ошибки.
        """
        if not file_path.lower().endswith(".mp3"):
            return

        try:
            audio = MP3(file_path, ID3=ID3)
        except Exception:
            audio = MP3(file_path)
        try:
            if audio.tags is None:
                audio.add_tags()
        except Exception:
            # Если теги уже есть или не удалось - продолжаем
            pass

        try:
            if thumbnail_path and os.path.exists(thumbnail_path):
                with open(thumbnail_path, "rb") as fh:
                    img_data = fh.read()
                audio.tags.add(
                    APIC(
                        encoding=3,
                        mime="image/jpeg",
                        type=3,
                        desc="Cover",
                        data=img_data
                    )
                )
        except Exception:
            logger.exception("Failed to attach cover to mp3")

        # Теги текста
        try:
            title = info.get("title", "")
            uploader = info.get("uploader", "") or info.get("uploader_id", "")
            album = info.get("album") or ""
            if title:
                audio.tags.add(TIT2(encoding=3, text=title))
            if uploader:
                audio.tags.add(TPE1(encoding=3, text=uploader))
            if album:
                audio.tags.add(TALB(encoding=3, text=album))
            audio.save()
        except Exception:
            logger.exception("Failed to write ID3 tags")

    @staticmethod
    def trim_media(file_path: str, start: float, end: Optional[float] = None) -> str:
        """
        Обрезает медиа с помощью ffmpeg. Возвращает путь к обрезанному файлу.
        Запускается синхронно (рекомендуется вызывать через run_in_executor).
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError("Input file not found")

        base, ext = os.path.splitext(file_path)
        output_path = f"{base}_trimmed{ext}"

        start = max(0.0, float(start))
        duration = None
        if end is not None:
            end = float(end)
            if end <= start:
                raise ValueError("End time must be greater than start time")
            duration = end - start

        cmd = ["ffmpeg", "-y", "-ss", str(start), "-i", file_path]

        if duration is not None:
            cmd.extend(["-t", str(duration)])

        # В зависимости от типа файла выбираем параметры кодирования
        if ext.lower() in [".mp4", ".mkv", ".avi", ".mov", ".webm"]:
            cmd.extend(["-c:v", "libx264", "-c:a", "aac", "-strict", "experimental"])
        elif ext.lower() in [".mp3", ".wav", ".ogg", ".m4a"]:
            cmd.extend(["-c:a", "libmp3lame"])
        else:
            # fallback copy streams
            cmd.extend(["-c", "copy"])

        cmd.append(output_path)

        try:
            proc = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            return output_path
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode(errors="ignore") if e.stderr else ""
            logger.error(f"FFmpeg error: {stderr}")
            raise RuntimeError(f"FFmpeg error: {stderr}") from e

    @staticmethod
    def parse_time(time_str: str) -> float:
        """
        Парсит строки форматов: "SS", "MM:SS", "HH:MM:SS", "M.SS" (дробные секунды),
        допускает пробелы. Возвращает секунды (float).
        """
        if not isinstance(time_str, str):
            raise ValueError("Time must be a string")

        s = time_str.strip()
        if s == "":
            raise ValueError("Empty time string")

        # Функция для безопасного преобразования в float
        def to_float(x: str) -> float:
            return float(x) if x else 0.0

        # Если содержит ":" - час/мин/сек
        if ":" in s:
            parts = [p.strip() for p in s.split(":")]
            # Поддерживаем дробную часть в последнем сегменте
            parts = [p if p != "" else "0" for p in parts]
            if len(parts) == 2:
                minutes = to_float(parts[0])
                seconds = to_float(parts[1])
                return minutes * 60.0 + seconds
            elif len(parts) == 3:
                hours = to_float(parts[0])
                minutes = to_float(parts[1])
                seconds = to_float(parts[2])
                return hours * 3600.0 + minutes * 60.0 + seconds
            else:
                # Неожиданный формат
                raise ValueError("Unsupported time format")
        else:
            # Может быть просто число (секунды) или дробное
            return to_float(s)


    @staticmethod
    def search_multiple_sources(query: str) -> List[Dict[str, Any]]:
        """
        Ищет в нескольких источниках. Основной источник -- YouTube (через yt-dlp).
        Остальные источники имитируются (заглушки).
        """
        results: List[Dict[str, Any]] = []

        # YouTube поиск
        try:
            ydl_opts = MediaProcessor._base_ydl_opts(audio_only=True)
            ydl_opts.update({
                "default_search": "ytsearch10",
                "quiet": True,
            })
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch10:{query}", download=False)
                if info and "entries" in info:
                    for entry in info["entries"]:
                        if not entry:
                            continue
                        results.append({
                            "id": entry.get("id") or entry.get("webpage_url") or str(random.random()),
                            "title": entry.get("title", "Без названия"),
                            "uploader": entry.get("uploader", "Неизвестный исполнитель"),
                            "url": entry.get("webpage_url") or f"https://youtu.be/{entry.get('id')}",
                            "source": "youtube",
                            "duration": entry.get("duration", 0) or 0
                        })
        except Exception:
            logger.exception("YouTube search error")

        # Заглушки для других сервисов (могут быть расширены по API)
        try:
            results.extend(MediaProcessor.search_vk(query))
            results.extend(MediaProcessor.search_spotify(query))
            results.extend(MediaProcessor.search_deezer(query))
            results.extend(MediaProcessor.search_yandex_music(query))
        except Exception:
            logger.exception("Secondary sources search error")

        # Сортировка: релевантные (название содержит запрос), длительность > 0, потом по убыванию длительности
        qlower = query.lower()
        results.sort(key=lambda x: (
            (qlower in x.get("title", "").lower()),
            (x.get("duration", 0) > 0),
            x.get("duration", 0)
        ), reverse=True)

        return results[:50]

    @staticmethod
    def search_vk(query: str) -> List[Dict[str, Any]]:
        return [{
            "id": f"vk_{''.join(random.choices(string.ascii_letters + string.digits, k=10))}",
            "title": f"{query} (VK)",
            "uploader": "VK Artist",
            "url": f"https://vk.com/music?q={quote_plus(query)}",
            "source": "vk",
            "duration": random.randint(120, 300)
        } for _ in range(2)]

    @staticmethod
    def search_spotify(query: str) -> List[Dict[str, Any]]:
        return [{
            "id": f"spotify_{''.join(random.choices(string.ascii_letters + string.digits, k=10))}",
            "title": f"{query} (Spotify)",
            "uploader": "Spotify Artist",
            "url": f"https://open.spotify.com/search/{quote_plus(query)}",
            "source": "spotify",
            "duration": random.randint(120, 300)
        } for _ in range(2)]

    @staticmethod
    def search_deezer(query: str) -> List[Dict[str, Any]]:
        return [{
            "id": f"deezer_{''.join(random.choices(string.ascii_letters + string.digits, k=10))}",
            "title": f"{query} (Deezer)",
            "uploader": "Deezer Artist",
            "url": f"https://www.deezer.com/search/{quote_plus(query)}",
            "source": "deezer",
            "duration": random.randint(120, 300)
        } for _ in range(2)]

    @staticmethod
    def search_yandex_music(query: str) -> List[Dict[str, Any]]:
        return [{
            "id": f"yandex_{''.join(random.choices(string.ascii_letters + string.digits, k=10))}",
            "title": f"{query} (Yandex Music)",
            "uploader": "Yandex Artist",
            "url": f"https://music.yandex.ru/search?text={quote_plus(query)}",
            "source": "yandex",
            "duration": random.randint(120, 300)
        } for _ in range(2)]


# ---------- Хэндлеры команд ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = get_chat_id_from_update(update)
    welcome_text = (
        "🌟 Добро пожаловать в Freedom Downloader!\n\n"
        "Я могу скачивать контент с различных платформ:\n"
        "- YouTube\n- TikTok\n- Instagram\n- Spotify\n- VK\n- Pinterest\n- Яндекс\n- Deezer\n\n"
        "Просто отправьте мне ссылку или название трека для поиска!\n\n"
        "После скачивания вы можете конвертировать файл или обрезать его.\n\n"
        f"Бот поддерживается: {SUPPORT_CHAT_LINK}"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Поиск музыки", switch_inline_query_current_chat="")],
        [InlineKeyboardButton("💬 Чат поддержки", url=SUPPORT_CHAT_LINK)]
    ])

    await context.bot.send_message(chat_id=chat_id, text=welcome_text, reply_markup=keyboard)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = get_chat_id_from_update(update)
    text = (
        "/start — Запуск\n"
        "/help — Помощь\n"
        "/ping — Пинг бота\n\n"
        "Отправьте ссылку или название трека. После скачивания доступны опции конвертации и обрезки."
    )
    await context.bot.send_message(chat_id=chat_id, text=text)


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = get_chat_id_from_update(update)
    await context.bot.send_message(chat_id=chat_id, text="PONG 🟢")


# ---------- Обработка входящих сообщений ----------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Основной обработчик текстовых сообщений: ссылка -> варианты загрузки,
    иначе — поиск музыки.
    """
    if not update.message or not update.message.text:
        return

    user_input = update.message.text.strip()
    chat_id = get_chat_id_from_update(update)

    # Если в предыдущем состоянии пользователь ожидает временной диапазон, передаём в обработчик времени
    user_state = USER_STATES.get(chat_id, {})
    if user_state.get("waiting_for_trim") and re.search(r"^\s*\d+[:.\d\-]*\d*\s*$", user_input):
        # Перенаправляем к обработчику временных диапазонов
        return await handle_time_range(update, context)

    # Проверка на ссылку
    if any(domain in user_input for domain in SUPPORTED_PLATFORMS):
        # Попробуем определить плейлист
        try:
            ydl_opts = MediaProcessor._base_ydl_opts(audio_only=True)
            ydl_opts.update({'extract_flat': True})
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(user_input, download=False)
                if info and info.get('_type') == 'playlist':
                    USER_STATES[chat_id] = {'playlist': info, 'url': user_input}
                    await show_playlist_options(update, info)
                    return
        except Exception:
            logger.exception("Ошибка при проверке плейлиста")

        # Обычная ссылка
        USER_STATES[chat_id] = {"url": user_input}
        await show_conversion_options(update)
    else:
        # Поиск музыки
        await search_music(update, user_input)


# ---------- Вспомогательные UI ----------
async def show_playlist_options(update: Update, playlist_info: dict):
    chat_id = get_chat_id_from_update(update)
    title = playlist_info.get("title", "Без названия")
    count = len(playlist_info.get("entries", []))
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 Выбрать треки", callback_data="playlist_choose_tracks")],
        [InlineKeyboardButton("⬇️ Скачать все треки", callback_data="playlist_download_all")]
    ])
    text = f"🎵 Найден плейлист: {title}\nКоличество треков: {count}\n\nВыберите действие:"
    await (update.message.reply_text(text, reply_markup=keyboard) if update.message else update.callback_query.message.reply_text(text, reply_markup=keyboard))


async def show_conversion_options(update: Update):
    chat_id = get_chat_id_from_update(update)
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎵 Аудио", callback_data="convert_audio"),
            InlineKeyboardButton("🎥 Видео", callback_data="convert_video"),
        ],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel")]
    ])
    await (update.message.reply_text("Выберите формат для скачивания:", reply_markup=keyboard)
           if update.message else update.callback_query.message.reply_text("Выберите формат для скачивания:", reply_markup=keyboard))


# ---------- Обработка выбора конвертации ----------
async def handle_conversion_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = get_chat_id_from_update(update)
    choice_token = (query.data or "").split("_", 1)
    choice = choice_token[1] if len(choice_token) > 1 else ""

    if choice == "cancel" or choice == "":
        try:
            await query.edit_message_text("Операция отменена.")
        except Exception:
            await query.message.reply_text("Операция отменена.")
        return

    url = USER_STATES.get(chat_id, {}).get("url")
    if not url:
        await query.edit_message_text("Ошибка: URL не найден.")
        return

    try:
        await query.edit_message_text(f"⏳ Начинаю обработку {choice}...")
    except Exception:
        pass

    # Скачивание в пуле потоков (блокирующий код)
    try:
        file_path, thumbnail_path, info = await run_blocking(MediaProcessor.download_media, url, choice)
    except Exception as e:
        logger.exception("Ошибка при скачивании медиа")
        await query.edit_message_text(f"❌ Произошла ошибка при скачивании: {str(e)}")
        return

    # Добавляем метаданные если аудио
    if choice == "audio":
        try:
            await run_blocking(MediaProcessor.add_metadata, file_path, thumbnail_path, info)
        except Exception:
            logger.exception("Metadata error")

    # Отправка файла (используем InputFile)
    try:
        caption = f"{info.get('title', '')}\n\nПрисоединяйтесь: {SUPPORT_CHAT_LINK}"
        with open(file_path, "rb") as media_file:
            if choice == "audio":
                thumb_file = open(thumbnail_path, "rb") if thumbnail_path and os.path.exists(thumbnail_path) else None
                await context.bot.send_audio(
                    chat_id,
                    audio=media_file,
                    caption=caption,
                    thumb=thumb_file,
                    title=info.get("title", ""),
                    performer=info.get("uploader", "")
                )
                if thumb_file:
                    thumb_file.close()
            else:
                thumb_file = open(thumbnail_path, "rb") if thumbnail_path and os.path.exists(thumbnail_path) else None
                await context.bot.send_video(
                    chat_id,
                    video=media_file,
                    caption=caption,
                    thumb=thumb_file,
                    supports_streaming=True
                )
                if thumb_file:
                    thumb_file.close()

        # Сохраняем информацию о файле для возможной обрезки
        USER_STATES[chat_id] = {
            "file_path": file_path,
            "media_type": choice,
            "info": info
        }

        # Предложение обрезки
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✂️ Обрезать файл", callback_data="trim_media")],
            [InlineKeyboardButton("✅ Готово", callback_data="done")]
        ])
        await context.bot.send_message(chat_id, "Файл успешно отправлен! Хотите обрезать его?", reply_markup=keyboard)

    except Exception:
        logger.exception("Failed to send media")
        await query.edit_message_text("❌ Произошла ошибка при отправке файла.")
        # Удаляем скачанный файл при ошибке отправки
        safe_remove(file_path)
        safe_remove(thumbnail_path)
        return

    # Удаляем временные файлы только если пользователь не собирается обрезать (файл = источник для обрезки)
    # Здесь мы не удаляем сразу file_path, т.к. пользователь может захотеть обрезать файл.
    # Однако если нет надежного сохранения, можно удалить через отложенную очистку по TTL (не реализовано).


# ---------- Поиск музыки ----------
async def search_music(update: Update, query_text: str):
    chat_id = get_chat_id_from_update(update)
    try:
        await update.message.reply_text(f"🔍 Ищу музыку по запросу: {query_text}...")
    except Exception:
        pass

    try:
        # Поиск выполняется в пуле потоков, т.к. yt-dlp может блокировать
        tracks = await run_blocking(MediaProcessor.search_multiple_sources, query_text)
        if not tracks:
            await update.message.reply_text("Ничего не найдено 😔")
            return

        SEARCH_RESULTS[chat_id] = tracks
        SEARCH_PAGE[chat_id] = 0

        await show_search_results(update, chat_id, 0)
    except Exception:
        logger.exception("Ошибка поиска")
        await update.message.reply_text("❌ Произошла ошибка при поиске. Попробуйте позже.")


# ---------- Показ результатов поиска ----------
async def show_search_results(update: Update, chat_id: int, page: int):
    tracks = SEARCH_RESULTS.get(chat_id, [])
    if not tracks:
        await (update.message.reply_text("Ничего не найдено.") if update.message else update.callback_query.message.reply_text("Ничего не найдено."))
        return

    page_size = 5
    total_pages = (len(tracks) + page_size - 1) // page_size
    page = max(0, min(page, total_pages - 1))
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, len(tracks))
    page_tracks = tracks[start_idx:end_idx]

    keyboard_rows = []
    for idx_offset, track in enumerate(page_tracks, start=1):
        i = idx_offset
        source_icon = {
            "vk": "🔵",
            "spotify": "🟢",
            "deezer": "🟣",
            "yandex": "🟡",
            "youtube": "🔴"
        }.get(track.get("source"), "🔴")

        title = track.get("title", "Без названия")
        if len(title) > 40:
            title = title[:37] + "..."
        keyboard_rows.append([InlineKeyboardButton(f"{i}. {source_icon} {title}", callback_data=f"track_{track['id']}")])

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Назад", callback_data=f"page_{page-1}"))
    nav_buttons.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="current_page"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Вперед ▶️", callback_data=f"page_{page+1}"))

    if nav_buttons:
        keyboard_rows.append(nav_buttons)

    keyboard_rows.append([
        InlineKeyboardButton("⬇️ Скачать все", callback_data="download_all"),
        InlineKeyboardButton("🎧 Альбомы", callback_data="albums")
    ])

    markup = InlineKeyboardMarkup(keyboard_rows)
    message_text = f"🔍 Результаты поиска ({len(tracks)}):"

    # Редактируем если есть callback, иначе отправляем новое сообщение
    try:
        if update.callback_query:
            await update.callback_query.edit_message_text(message_text, reply_markup=markup)
        else:
            await update.message.reply_text(message_text, reply_markup=markup)
    except Exception:
        # Иногда редактирование может не работать (старое сообщение) — отправим новое
        try:
            await context_bot_send_safe(update, message_text, reply_markup=markup)
        except Exception:
            logger.exception("Failed to display search results")


# Helper to send messages safely via context.bot regardless of update type
async def context_bot_send_safe(update: Update, text: str, **kwargs):
    chat_id = get_chat_id_from_update(update)
    app = update._bot if hasattr(update, "_bot") else None
    # Use provided context if available else use update.effective_chat via Application (we will rely on update)
    await update.get_bot().send_message(chat_id=chat_id, text=text, **kwargs)


# ---------- Обрезка ----------
async def handle_trim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = get_chat_id_from_update(update)

    await query.edit_message_text(
        "✂️ Введите временной диапазон для обрезки в формате:\n"
        "Примеры:\n"
        "0 (от начала до конца)\n"
        "5 (от 5 секунды до конца)\n"
        "2:33 (от 2:33 до конца)\n"
        "0-5 (первые 5 секунд)\n"
        "1:32-5:48 (от 1:32 до 5:48)\n"
        "0.55-2:3.75 (дробные секунды)\n"
    )

    USER_STATES.setdefault(chat_id, {})["waiting_for_trim"] = True


async def handle_time_range(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает текст с временным диапазоном, ожидаемый после вызова handle_trim.
    """
    chat_id = get_chat_id_from_update(update)
    user_state = USER_STATES.get(chat_id, {})

    if not user_state.get("waiting_for_trim"):
        # не ожидаем этот ввод
        return

    time_range = update.message.text.strip()
    file_path = user_state.get("file_path")
    media_type = user_state.get("media_type")

    if not file_path or not media_type:
        await update.message.reply_text("Ошибка: информация о файле отсутствует.")
        user_state.pop("waiting_for_trim", None)
        return

    try:
        if "-" in time_range:
            parts = time_range.split("-", 1)
            start_time = MediaProcessor.parse_time(parts[0].strip())
            end_time = MediaProcessor.parse_time(parts[1].strip())
        else:
            start_time = MediaProcessor.parse_time(time_range)
            end_time = None

        await update.message.reply_text("⏳ Обрезаю файл...")

        # Выполняем обрезку в потоке (FFmpeg блокирующий)
        trimmed_path = await run_blocking(MediaProcessor.trim_media, file_path, start_time, end_time)

        # Отправка обрезанного файла
        with open(trimmed_path, "rb") as media_file:
            caption = f"✂️ Обрезанный файл\n\nПрисоединяйтесь к нашему чату: {SUPPORT_CHAT_LINK}"
            if media_type == "audio":
                await context.bot.send_audio(chat_id, audio=media_file, caption=caption)
            else:
                await context.bot.send_video(chat_id, video=media_file, caption=caption, supports_streaming=True)

        # Удаление временных файлов
        safe_remove(trimmed_path)
        # Исходный файл можно удалить: мы предполагаем, что он больше не нужен
        safe_remove(file_path)

        user_state.pop("waiting_for_trim", None)
        await update.message.reply_text("✅ Обрезка выполнена.")
    except Exception as e:
        logger.exception("Ошибка обрезки")
        user_state.pop("waiting_for_trim", None)
        await update.message.reply_text(f"❌ Ошибка при обрезке: {str(e)}")


# ---------- Обработка inline-кнопок ----------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    chat_id = get_chat_id_from_update(update)

    try:
        if data.startswith("convert_"):
            await handle_conversion_choice(update, context)
        elif data == "trim_media":
            await handle_trim(update, context)
        elif data.startswith("track_"):
            track_id = data.split("_", 1)[1]
            await download_track(update, context, track_id)
        elif data.startswith("page_"):
            page = int(data.split("_", 1)[1])
            SEARCH_PAGE[chat_id] = page
            await show_search_results(update, chat_id, page)
        elif data == "download_all":
            await download_all_tracks(update, context, chat_id)
        elif data == "playlist_choose_tracks":
            await choose_playlist_tracks(update, context)
        elif data == "playlist_download_all":
            await download_playlist_all(update, context)
        elif data == "done":
            await query.edit_message_text("Ок. Если нужно — напишите снова.")
        else:
            await query.edit_message_text("Неизвестная команда.")
    except Exception:
        logger.exception("Error in button_handler")
        try:
            await query.edit_message_text("Произошла ошибка при обработке кнопки.")
        except Exception:
            pass


# ---------- Плейлист: выбор треков ----------
async def choose_playlist_tracks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = get_chat_id_from_update(update)
    playlist_info = USER_STATES.get(chat_id, {}).get('playlist')
    if not playlist_info:
        await query.edit_message_text("Информация о плейлисте отсутствует.")
        return

    # Некоторые плейлисты из yt-dlp содержат entries с минимальной информацией (flat)
    entries = playlist_info.get('entries', [])
    tracks = []
    for e in entries:
        # Попытка извлечь ключевые поля, fallback на генерацию id
        tracks.append({
            "id": e.get("id") or e.get("url") or f"pl_{''.join(random.choices(string.ascii_lowercase+string.digits, k=8))}",
            "title": e.get("title", "Без названия"),
            "uploader": e.get("uploader", "Unknown"),
            "url": e.get("url") or e.get("webpage_url") or None,
            "source": "youtube",
            "duration": e.get("duration", 0) or 0
        })
    SEARCH_RESULTS[chat_id] = tracks
    SEARCH_PAGE[chat_id] = 0
    await show_search_results(update, chat_id, 0)


# ---------- Скачать весь плейлист ----------
async def download_playlist_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = get_chat_id_from_update(update)
    state = USER_STATES.get(chat_id, {})
    playlist_url = state.get("url")
    if not playlist_url:
        await query.edit_message_text("URL плейлиста не найден.")
        return

    await query.edit_message_text("⏳ Начинаю скачивание плейлиста...")

    # Создаём временную дирректорию
    playlist_dir = tempfile.mkdtemp(prefix=f"playlist_{chat_id}_")
    try:
        ydl_opts = MediaProcessor._base_ydl_opts(audio_only=True)
        ydl_opts.update({
            "outtmpl": os.path.join(playlist_dir, "%(title)s.%(ext)s"),
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
            "writethumbnail": True,
            "ignoreerrors": True,
        })
        if YOUTUBE_COOKIES:
            ydl_opts["cookiefile"] = YOUTUBE_COOKIES

        # Загружаем плейлист
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(playlist_url, download=True)
            if not info or 'entries' not in info:
                await query.edit_message_text("❌ Не удалось скачать плейлист")
                return

            for entry in info['entries']:
                if not entry:
                    continue
                # Формируем имя файла
                try:
                    file_path = ydl.prepare_filename(entry)
                except Exception:
                    title_safe = (entry.get("title") or "file").replace("/", "_")
                    file_path = os.path.join(playlist_dir, f"{title_safe}.mp3")
                if file_path.endswith(".webm") or file_path.endswith(".m4a"):
                    file_path = file_path.rsplit(".", 1)[0] + ".mp3"

                thumb = None
                base_no_ext = file_path.rsplit(".", 1)[0]
                for ext in ("webp", "jpg", "jpeg", "png"):
                    candidate = f"{base_no_ext}.{ext}"
                    if os.path.exists(candidate):
                        if candidate.endswith(".webp"):
                            try:
                                img = Image.open(candidate)
                                jpg_path = f"{base_no_ext}.jpg"
                                img.convert("RGB").save(jpg_path, "JPEG")
                                safe_remove(candidate)
                                thumb = jpg_path
                            except Exception:
                                thumb = candidate
                        else:
                            thumb = candidate
                        break

                # Добавляем теги
                try:
                    MediaProcessor.add_metadata(file_path, thumb, entry)
                except Exception:
                    logger.exception("add_metadata failed")

                # Отправляем файл
                try:
                    with open(file_path, "rb") as audio_file:
                        thumb_file = open(thumb, "rb") if thumb and os.path.exists(thumb) else None
                        await context.bot.send_audio(
                            chat_id,
                            audio=audio_file,
                            caption=f"🎵 {entry.get('title','')}\n\nПрисоединяйтесь: {SUPPORT_CHAT_LINK}",
                            thumb=thumb_file
                        )
                        if thumb_file:
                            thumb_file.close()
                except Exception:
                    logger.exception("Failed to send playlist item")
                finally:
                    safe_remove(file_path)
                    safe_remove(thumb)
                    await asyncio.sleep(1)

        await query.edit_message_text("✅ Весь плейлист успешно скачан и отправлен!")
    except Exception:
        logger.exception("Ошибка при скачивании плейлиста")
        await query.edit_message_text("❌ Ошибка при скачивании плейлиста.")
    finally:
        # Очистка временной директории
        try:
            shutil.rmtree(playlist_dir, ignore_errors=True)
        except Exception:
            logger.exception("Failed to remove temporary playlist dir")


# ---------- Скачать конкретный трек ----------
async def download_track(update: Update, context: ContextTypes.DEFAULT_TYPE, track_id: str):
    query = update.callback_query
    await query.answer()
    chat_id = get_chat_id_from_update(update)
    tracks = SEARCH_RESULTS.get(chat_id, [])
    track = next((t for t in tracks if t.get("id") == track_id), None)
    if not track:
        await query.edit_message_text("Трек не найден.")
        return

    await query.edit_message_text(f"⏳ Скачиваю: {track['title']}...")

    url = track.get("url") or f"https://youtu.be/{track_id}"
    try:
        file_path, thumbnail_path, info = await run_blocking(MediaProcessor.download_media, url, "audio")
    except Exception as e:
        logger.exception("Error downloading track")
        await query.edit_message_text(f"❌ Ошибка при скачивании трека: {str(e)}")
        return

    try:
        await run_blocking(MediaProcessor.add_metadata, file_path, thumbnail_path, info)
    except Exception:
        logger.exception("add_metadata failed")

    try:
        with open(file_path, "rb") as audio_file:
            thumb_file = open(thumbnail_path, "rb") if thumbnail_path and os.path.exists(thumbnail_path) else None
            await context.bot.send_audio(
                chat_id,
                audio=audio_file,
                caption=f"🎵 {track.get('title','')}\n\nПрисоединяйтесь: {SUPPORT_CHAT_LINK}",
                thumb=thumb_file,
                title=track.get("title", ""),
                performer=track.get("uploader", "")
            )
            if thumb_file:
                thumb_file.close()
    except Exception:
        logger.exception("Failed to send downloaded track")
        await query.edit_message_text("❌ Ошибка при отправке трека.")
    finally:
        safe_remove(file_path)
        safe_remove(thumbnail_path)


# ---------- Скачать все треки на странице ----------
async def download_all_tracks(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⏳ Начинаю скачивание всех треков на странице...")

    tracks = SEARCH_RESULTS.get(chat_id, [])
    page = SEARCH_PAGE.get(chat_id, 0)
    page_size = 5
    start_idx = page * page_size
    end_idx = min(start_idx + page_size, len(tracks))
    page_tracks = tracks[start_idx:end_idx]

    for i, track in enumerate(page_tracks, start=1):
        try:
            url = track.get("url") or f"https://youtu.be/{track['id']}"
            file_path, thumbnail_path, info = await run_blocking(MediaProcessor.download_media, url, "audio")
            await run_blocking(MediaProcessor.add_metadata, file_path, thumbnail_path, info)
            with open(file_path, "rb") as audio_file:
                thumb_file = open(thumbnail_path, "rb") if thumbnail_path and os.path.exists(thumbnail_path) else None
                await context.bot.send_audio(
                    chat_id,
                    audio=audio_file,
                    caption=f"{i}. 🎵 {track.get('title','')}\n\nПрисоединяйтесь: {SUPPORT_CHAT_LINK}",
                    thumb=thumb_file
                )
                if thumb_file:
                    thumb_file.close()
            safe_remove(file_path)
            safe_remove(thumbnail_path)
            await asyncio.sleep(1)
        except Exception:
            logger.exception("Error downloading sending track in download_all_tracks")
            continue

    await query.edit_message_text("✅ Все треки страницы успешно отправлены!")


# ---------- Основная функция ----------
def main():
    application = Application.builder().token(TOKEN).build()

    # Команды
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("ping", ping))

    # Обработчики сообщений и кнопок
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_handler))

    # Обработчик для ввода временного диапазона (регекс)
    time_regex = re.compile(r"^\s*\d+[:.\d\-]*\d*\s*$")
    application.add_handler(MessageHandler(filters.Text(time_regex) & ~filters.COMMAND, handle_time_range))

    # Запуск (polling или webhook)
    if os.environ.get('RENDER'):
        hostname = os.environ.get('RENDER_EXTERNAL_HOSTNAME', None)
        if not hostname:
            logger.warning("RENDER environment variable set but RENDER_EXTERNAL_HOSTNAME not found; running polling instead")
            application.run_polling()
        else:
            webhook_url = f"https://{hostname}/{TOKEN}"
            application.run_webhook(
                listen="0.0.0.0",
                port=PORT,
                url_path=TOKEN,
                webhook_url=webhook_url
            )
    else:
        application.run_polling()


if __name__ == "__main__":
    main()
