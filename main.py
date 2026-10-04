"""
main.py — точка входа Telegram-бота «Read It Later».

Запуск: python main.py

Режим работы выбирается сам:
- webhook — на хостинге. Telegram сам присылает каждое сообщение на
  адрес бота, и этот входящий запрос будит уснувший сервис Render.
  Включается, если известен публичный адрес бота: WEBHOOK_BASE_URL
  или RENDER_EXTERNAL_URL (её Render задаёт сам);
- polling — локально: бот сам опрашивает Telegram.
"""

import asyncio
import logging
import sys
from collections import deque

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.types import Update
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from aiohttp import web

import database
from config import (
    BOT_TOKEN,
    PORT,
    WEBHOOK_BASE_URL,
    WEBHOOK_PATH,
    WEBHOOK_SECRET,
    validate_config,
)
from handlers import ALL_ROUTERS

# Включаем логирование, чтобы видеть предупреждения парсера и ошибки
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class SkipDuplicateUpdates(BaseMiddleware):
    """
    Пропускает повторную доставку одного и того же сообщения.

    Telegram повторяет запрос к webhook, если не дождался ответа, —
    например, пока Render будит уснувший сервис. Без этой проверки
    ссылка могла бы сохраниться дважды.
    """

    def __init__(self, remember: int = 1000) -> None:
        self._seen: deque[int] = deque(maxlen=remember)

    async def __call__(self, handler, event: Update, data: dict):
        if event.update_id in self._seen:
            logger.info("Апдейт %s уже обработан — пропускаем.", event.update_id)
            return None
        self._seen.append(event.update_id)
        return await handler(event, data)


def create_dispatcher() -> Dispatcher:
    """Диспетчер со всеми роутерами бота (порядок важен — см. handlers)."""
    dp = Dispatcher()
    dp.update.outer_middleware(SkipDuplicateUpdates())
    for router in ALL_ROUTERS:
        dp.include_router(router)
    return dp


async def health(request: web.Request) -> web.Response:
    """Страница «бот жив» — для Render и сервисов мониторинга."""
    return web.Response(text="Bot is live!")


def create_webhook_app(bot: Bot, dp: Dispatcher) -> web.Application:
    """Веб-приложение для режима webhook: Telegram шлёт сообщения на WEBHOOK_PATH."""
    app = web.Application()
    app.router.add_get("/", health)

    # Запросы без правильного секрета (не от Telegram) получат 401.
    # Telegram отвечаем сразу, а сообщение обрабатываем в фоне:
    # загрузка заголовков может занять несколько секунд.
    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=WEBHOOK_SECRET,
        handle_in_background=True,
    ).register(app, path=WEBHOOK_PATH)

    async def on_startup(app: web.Application) -> None:
        await database.init_db()
        await bot.set_webhook(
            url=WEBHOOK_BASE_URL + WEBHOOK_PATH,
            secret_token=WEBHOOK_SECRET,
            allowed_updates=dp.resolve_used_update_types(),
            # Не выбрасываем сообщения, пришедшие, пока сервис спал:
            # одно из них его и разбудило
            drop_pending_updates=False,
        )
        logger.info("Webhook установлен: %s%s", WEBHOOK_BASE_URL, WEBHOOK_PATH)

    async def on_cleanup(app: web.Application) -> None:
        # Webhook при остановке НЕ удаляем: Render усыпляет сервис,
        # и разбудить его может только входящий запрос от Telegram
        await database.close_db()

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    return app


async def start_health_server(port: int) -> None:
    """HTTP-заглушка для хостингов, которые требуют открытый порт."""
    app = web.Application()
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", port).start()


async def run_polling(bot: Bot, dp: Dispatcher) -> None:
    """Локальный режим: бот сам опрашивает Telegram."""
    webhook = await bot.get_webhook_info()
    if webhook.url:
        await bot.session.close()
        # Иначе локальный запуск «перехватит» бота у сервера: Telegram
        # перестанет слать сообщения на webhook, и бот на Render замолчит
        sys.exit(
            f"❌ У этого бота включён webhook ({webhook.url}) — он работает "
            "на сервере.\n"
            "   Для локального запуска создайте тестового бота у @BotFather\n"
            "   и впишите его токен в .env. Если webhook больше не нужен,\n"
            "   удалите его: https://api.telegram.org/bot<токен>/deleteWebhook"
        )

    await database.init_db()
    if PORT:
        await start_health_server(PORT)
    try:
        logger.info("Бот запущен в режиме polling.")
        await dp.start_polling(bot)
    finally:
        await database.close_db()


def main() -> None:
    # Проверяем настройки (токен, база, webhook) до старта
    validate_config()

    bot = Bot(token=BOT_TOKEN)
    dp = create_dispatcher()

    if WEBHOOK_BASE_URL:
        logger.info("Режим webhook: %s%s", WEBHOOK_BASE_URL, WEBHOOK_PATH)
        web.run_app(
            create_webhook_app(bot, dp), host="0.0.0.0", port=PORT or 10000
        )
    else:
        asyncio.run(run_polling(bot, dp))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Бот остановлен.")
