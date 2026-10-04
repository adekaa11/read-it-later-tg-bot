"""
config.py — загрузка настроек бота из переменных окружения (.env).

Токен бота НЕ хранится в коде: он подтягивается из файла .env
с помощью библиотеки python-dotenv.
"""

import os
import sys

from dotenv import load_dotenv

# Загружаем переменные окружения из файла .env (если он существует)
load_dotenv()

# Токен бота, полученный у @BotFather
BOT_TOKEN: str | None = os.getenv("BOT_TOKEN")

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


def validate_config() -> None:
    """Проверяет наличие обязательных настроек перед стартом бота."""
    if not BOT_TOKEN or BOT_TOKEN == "PASTE_YOUR_TELEGRAM_BOT_TOKEN_HERE":
        sys.exit(
            "❌ Ошибка: не задан BOT_TOKEN.\n"
            "   1. Скопируйте .env.example в .env\n"
            "   2. Получите токен у @BotFather в Telegram\n"
            "   3. Вставьте токен в файл .env и запустите бота снова."
        )
