"""
main.py — точка входа Telegram-бота «Read It Later».

Запуск: python main.py
"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand

import database
from config import BOT_TOKEN, validate_config
from handlers import ALL_ROUTERS

# Включаем логирование, чтобы видеть предупреждения парсера и ошибки
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def set_bot_menu(bot: Bot) -> None:
    """Регистрирует команды в меню Telegram (кнопка слева от поля ввода)."""
    await bot.set_my_commands(
        [
            BotCommand(command="list", description="Непрочитанные ссылки"),
            BotCommand(command="random", description="Случайная ссылка"),
        ]
    )


async def main() -> None:
    # Проверяем наличие токена в .env до старта
    validate_config()

    # Инициализация базы данных (создание таблицы, если её нет)
    await database.init_db()
    logger.info("База данных инициализирована.")

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # Подключаем все роутеры (порядок важен — см. handlers/__init__.py)
    dp.include_routers(*ALL_ROUTERS)

    await set_bot_menu(bot)

    me = await bot.get_me()
    logger.info("Бот @%s запущен. Ожидание сообщений...", me.username)

    # Long-polling: aiogram сам обрабатывает обновления в бесконечном цикле
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")
