"""
handlers/links.py — обработка входящих сообщений со ссылками.

Если пользователь присылает текст, содержащий http/https ссылку:
1. Бот асинхронно скачивает начало HTML страницы через aiohttp.
2. Парсит тег <title> через BeautifulSoup.
3. Сохраняет ссылку и заголовок в БД (is_read=False).
4. Отвечает «✅ Сохранено: [Заголовок]».

Если сайт недоступен или заголовка нет — сохраняем просто URL.

Безопасность: бот загружает только страницы из публичного интернета.
Ссылки на localhost, домашнюю/офисную сеть и служебные адреса облака
(например, 169.254.169.254) сохраняются без заголовка и не открываются —
иначе любой пользователь мог бы «подсмотреть» через бота внутренние
страницы сервера (атака SSRF).
"""

import asyncio
import ipaddress
import logging
import re
import socket

import aiohttp
from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiohttp.abc import AbstractResolver
from aiohttp.resolver import DefaultResolver
from bs4 import BeautifulSoup
from yarl import URL

import database
from config import (
    FETCH_TIMEOUT_SECONDS,
    MAX_HTML_BYTES,
    MAX_LINKS_PER_MESSAGE,
    MAX_REDIRECTS,
)
from handlers.common import shorten

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

# HTTP-коды, при которых сервер отправляет нас по другому адресу
REDIRECT_STATUSES = {301, 302, 303, 307, 308}


def is_public_ip(address: str) -> bool:
    """True, если IP-адрес публичный (не localhost, не локальная сеть и т.п.)."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    # ::ffff:127.0.0.1 — это тот же 127.0.0.1, проверяем вложенный IPv4
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def is_allowed_url(url: URL) -> bool:
    """Можно ли загружать адрес: схема http/https и публичный хост."""
    host = url.raw_host  # именно к этому хосту подключится aiohttp
    if url.scheme not in ("http", "https") or not host:
        return False
    try:
        ipaddress.ip_address(host)
    except ValueError:
        # Числовые записи вроде 2130706433 или 127.1 — это тоже 127.0.0.1
        if host.replace(".", "").isdigit():
            return False
        return True  # доменное имя: его адреса проверит PublicOnlyResolver
    return is_public_ip(host)


class PublicOnlyResolver(AbstractResolver):
    """
    DNS-резолвер, который отбрасывает непубличные адреса.

    Проверка именно здесь защищает и от подмены DNS (DNS rebinding):
    aiohttp подключается ровно к тем адресам, которые прошли проверку.
    """

    def __init__(self) -> None:
        self._resolver = DefaultResolver()

    async def resolve(
        self, host: str, port: int = 0, family: int = socket.AF_INET
    ) -> list[dict]:
        addresses = await self._resolver.resolve(host, port, family)
        public = [addr for addr in addresses if is_public_ip(addr["host"])]
        if not public:
            raise OSError(f"{host} указывает на непубличный адрес")
        return public

    async def close(self) -> None:
        await self._resolver.close()


async def _read_head(response: aiohttp.ClientResponse) -> bytes:
    """Читает начало страницы: до </title> или до MAX_HTML_BYTES."""
    html = b""
    # Один read() может вернуть лишь первый кусок ответа, поэтому
    # дочитываем по частям, пока не встретим конец заголовка
    async for chunk in response.content.iter_chunked(64 * 1024):
        html += chunk
        if len(html) >= MAX_HTML_BYTES or b"</title>" in html.lower():
            break
    return html[:MAX_HTML_BYTES]


def _extract_title(html: bytes, encoding: str | None) -> str | None:
    """Достаёт заголовок из HTML: <title>, а если его нет — og:title."""
    # Кодировку из HTTP-заголовка передаём явно: без неё страницы
    # в windows-1251 превращаются в «кракозябры»
    soup = BeautifulSoup(html, "html.parser", from_encoding=encoding)
    title = soup.title.get_text() if soup.title else ""
    if not title.strip():
        og_title = soup.find("meta", attrs={"property": "og:title"})
        title = (og_title.get("content") or "") if og_title else ""
    # Сжимаем пробелы и переносы строк внутри заголовка
    return " ".join(title.split()) or None


async def _fetch_title(url: str) -> str | None:
    """Загружает страницу (с проверкой каждого редиректа) и парсит заголовок."""
    current = URL(url)
    resolver = PublicOnlyResolver()
    try:
        connector = aiohttp.TCPConnector(resolver=resolver)
        async with aiohttp.ClientSession(
            connector=connector, headers=REQUEST_HEADERS
        ) as session:
            # Редиректы проходим вручную, чтобы проверить каждый адрес
            for _ in range(MAX_REDIRECTS + 1):
                if not is_allowed_url(current):
                    logger.warning("Заблокирован непубличный адрес: %s", current)
                    return None

                async with session.get(current, allow_redirects=False) as response:
                    location = response.headers.get("Location")
                    if response.status in REDIRECT_STATUSES and location:
                        current = response.url.join(URL(location))
                        continue

                    if response.status != 200:
                        logger.warning("HTTP %s для %s", response.status, current)
                        return None

                    html = await _read_head(response)
                    return _extract_title(html, response.charset)

            logger.warning("Слишком много редиректов: %s", url)
            return None
    finally:
        await resolver.close()


async def fetch_page_title(url: str) -> str | None:
    """
    Асинхронно скачивает начало HTML-страницы и возвращает её заголовок.
    Если что-то пошло не так (сайт недоступен, таймаут, нет заголовка,
    непубличный адрес, «кривая» ссылка) — возвращает None.
    """
    try:
        return await asyncio.wait_for(_fetch_title(url), FETCH_TIMEOUT_SECONDS)
    except Exception as exc:
        # Заголовок — лишь «приятное дополнение»: любая ошибка здесь
        # не должна мешать сохранить саму ссылку
        logger.warning(
            "Не удалось получить заголовок %s: %s", url, str(exc) or type(exc).__name__
        )
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
    # Убираем «прилипшую» пунктуацию в конце ссылки (точки, запятые и т.п.)
    # и повторы, сохраняя порядок ссылок в сообщении
    urls = list(
        dict.fromkeys(url.rstrip(".,;:!?") for url in URL_REGEX.findall(message.text))
    )
    skipped = len(urls) - MAX_LINKS_PER_MESSAGE
    urls = urls[:MAX_LINKS_PER_MESSAGE]

    # Заголовки загружаем параллельно: 10 ссылок — это ~10 секунд, а не 100
    titles = await asyncio.gather(*(fetch_page_title(url) for url in urls))

    for url, title in zip(urls, titles):
        # Если заголовок получить не удалось — используем сам URL;
        # слишком длинный заголовок обрезаем
        title = shorten(title or url)

        await database.add_link(
            user_id=message.from_user.id,
            url=url,
            title=title,
        )
        await message.answer(f"✅ Сохранено: {title}")

    if skipped > 0:
        await message.answer(
            f"⚠️ За раз я сохраняю не больше {MAX_LINKS_PER_MESSAGE} ссылок. "
            f"Остальные ({skipped}) пришлите отдельным сообщением."
        )
