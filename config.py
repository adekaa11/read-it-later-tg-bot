"""
config.py — загрузка настроек бота из переменных окружения (.env).

Токен бота НЕ хранится в коде: он подтягивается из файла .env
с помощью библиотеки python-dotenv.
"""

import hashlib
import os
import re
import sys

from dotenv import load_dotenv

# Загружаем переменные окружения из файла .env (если он существует)
load_dotenv()

# Токен бота, полученный у @BotFather. Лишние пробелы и переводы строк
# (их легко захватить при копировании в настройки хостинга) отрезаем.
BOT_TOKEN: str | None = os.getenv("BOT_TOKEN", "").strip() or None

# Строка подключения к PostgreSQL (Supabase → Connect → Session pooler).
# Если не задана — данные хранятся в SQLite-файле DB_PATH (локальный запуск).
DATABASE_URL: str | None = os.getenv("DATABASE_URL", "").strip() or None

# Путь к файлу базы данных SQLite (можно переопределить через .env)
DB_PATH: str = os.getenv("DB_PATH", "read_it_later.db")

# Таймаут (в секундах) на загрузку веб-страниц при парсинге заголовков
FETCH_TIMEOUT_SECONDS: int = int(os.getenv("FETCH_TIMEOUT", "10"))

# Максимальный объём скачиваемого HTML (байты). Заголовок <title>
# находится в начале страницы, поэтому качать весь документ не нужно.
MAX_HTML_BYTES: int = 256 * 1024

# Сколько редиректов можно пройти при загрузке страницы
MAX_REDIRECTS: int = 5

# Сколько ссылок из одного сообщения сохраняем за раз (защита от флуда)
MAX_LINKS_PER_MESSAGE: int = 10

# Максимальная длина заголовка (символы): длинные обрезаются с «…»
MAX_TITLE_LENGTH: int = 300


def _webhook_base_url() -> str | None:
    """Публичный адрес бота: WEBHOOK_BASE_URL или адрес сервиса на Render."""
    url = os.getenv("WEBHOOK_BASE_URL") or os.getenv("RENDER_EXTERNAL_URL") or ""
    return url.rstrip("/") or None


def _webhook_secret() -> str:
    """Секрет из WEBHOOK_SECRET, а если его нет — производный от токена."""
    return (
        os.getenv("WEBHOOK_SECRET")
        or hashlib.sha256(f"read-it-later:{BOT_TOKEN}".encode()).hexdigest()
    )


# Публичный https-адрес бота для режима webhook. На Render задавать
# не нужно: Render сам передаёт адрес сервиса в RENDER_EXTERNAL_URL.
# Если адреса нет — бот работает в режиме polling (локальный запуск).
WEBHOOK_BASE_URL: str | None = _webhook_base_url()

# Путь, на который Telegram присылает сообщения
WEBHOOK_PATH: str = "/webhook"

# Секрет, которым Telegram подписывает свои запросы к webhook (заголовок
# X-Telegram-Bot-Api-Secret-Token). Если не задан — выводится из токена
# бота, поэтому хранить его отдельно не нужно.
WEBHOOK_SECRET: str = _webhook_secret()

# Порт веб-сервера (Render задаёт PORT сам, по умолчанию 10000)
PORT: int | None = int(os.environ["PORT"]) if os.getenv("PORT") else None


def validate_config() -> None:
    """Проверяет наличие обязательных настроек перед стартом бота."""
    if not BOT_TOKEN or BOT_TOKEN == "PASTE_YOUR_TELEGRAM_BOT_TOKEN_HERE":
        sys.exit(
            "❌ Ошибка: не задан BOT_TOKEN.\n"
            "   1. Скопируйте .env.example в .env\n"
            "   2. Получите токен у @BotFather в Telegram\n"
            "   3. Вставьте токен в файл .env и запустите бота снова."
        )

    if DATABASE_URL:
        # Частая путаница: вставить адрес проекта https://….supabase.co
        # вместо строки подключения к базе
        if not DATABASE_URL.startswith(("postgresql://", "postgres://")):
            sys.exit(
                "❌ DATABASE_URL должен начинаться с postgresql://.\n"
                "   Это строка подключения к базе (Supabase → Connect → "
                "Session pooler), а не адрес проекта https://….supabase.co"
            )
        if "[YOUR-PASSWORD]" in DATABASE_URL:
            sys.exit(
                "❌ В DATABASE_URL остался шаблон [YOUR-PASSWORD] — "
                "подставьте пароль от базы Supabase."
            )

    if WEBHOOK_BASE_URL and not WEBHOOK_BASE_URL.startswith("https://"):
        sys.exit(
            "❌ WEBHOOK_BASE_URL должен начинаться с https:// — "
            "Telegram отправляет webhook только по HTTPS."
        )
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", WEBHOOK_SECRET):
        sys.exit(
            "❌ WEBHOOK_SECRET: допустимы только латинские буквы, цифры, "
            "_ и -, не длиннее 256 символов."
        )
