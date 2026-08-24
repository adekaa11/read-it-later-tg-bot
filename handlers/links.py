"""
handlers/links.py — обработка входящих сообщений со ссылками.

Если пользователь присылает текст, содержащий http/https ссылку:
1. Бот асинхронно скачивает HTML страницы через aiohttp.
2. Парсит тег <title> через BeautifulSoup.
3. Сохраняет ссылку и заголовок в БД (is_read=False).
4. Отвечает «✅ Сохранено: [Заголовок]».

Если сайт недоступен или заголовка нет — сохраняем просто URL.
"""

import logging
import re

import aiohttp
from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from bs4 import BeautifulSoup

import database
from config import FETCH_TIMEOUT_SECONDS, MAX_HTML_BYTES

logger = logging.getLogger(__name__)

router = Router(name="links")

# Регулярное выражение для поиска http/https ссылок в тексте сообщения
URL_REGEX = re.compile(r"https?://[^\s<>()\"']+")

# Заголовки браузера, чтобы некоторые сайты не блокировали запросы
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}


async def fetch_page_title(url: str) -> str | None:
    """
    Асинхронно скачивает начало HTML-страницы и возвращает содержимое
    тега <title>. Если что-то пошло не так (сайт недоступен, таймаут,
    нет заголовка) — возвращает None.
    """
    timeout = aiohttp.ClientTimeout(total=FETCH_TIMEOUT_SECONDS)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                url, headers=REQUEST_HEADERS, allow_redirects=True
            ) as response:
                if response.status != 200:
                    logger.warning("HTTP %s для %s", response.status, url)
                    return None

                # Читаем только первые MAX_HTML_BYTES — <title> в начале страницы
                html_bytes = await response.content.read(MAX_HTML_BYTES)

        soup = BeautifulSoup(html_bytes, "html.parser")
        if soup.title and soup.title.string:
            # Сжимаем пробелы и переносы строк внутри заголовка
            return " ".join(soup.title.string.split())
        return None
    except (aiohttp.ClientError, TimeoutError, UnicodeDecodeError) as exc:
        # Сайт недоступен / таймаут / битая кодировка — это не критично
        logger.warning("Не удалось получить заголовок %s: %s", url, exc)
        return None


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """Приветственное сообщение по команде /start."""
    await message.answer(
        "👋 Привет! Я бот «Read It Later».\n\n"
        "Просто пришли мне ссылку (http/https) — я сохраню её, "
        "чтобы ты мог прочитать позже.\n\n"
        "Команды:\n"
        "/list — 5 последних непрочитанных ссылок\n"
        "/random — случайная непрочитанная ссылка"
    )


@router.message(lambda message: message.text and URL_REGEX.search(message.text))
async def handle_link_message(message: Message) -> None:
    """Сохраняет все ссылки, найденные в текстовом сообщении пользователя."""
    urls = URL_REGEX.findall(message.text)

    for url in urls:
        # Убираем «прилипшую» пунктуацию в конце ссылки (точки, запятые и т.п.)
        url = url.rstrip(".,;:!?")

        # Пытаемся получить заголовок страницы; при неудаче используем сам URL
        title = await fetch_page_title(url) or url

        await database.add_link(
            user_id=message.from_user.id,
            url=url,
            title=title,
        )
        await message.answer(f"✅ Сохранено: {title}")
