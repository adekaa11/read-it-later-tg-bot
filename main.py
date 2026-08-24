import asyncio
import logging
import os
from aiohttp import web
from aiogram import Bot, Dispatcher
from config import BOT_TOKEN, validate_config
from database import init_db
from handlers import ALL_ROUTERS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def dummy_server():
    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="Bot is live!"))
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

async def main():
    validate_config()
    await init_db()
    logger.info("База данных инициализирована.")
    
    await dummy_server()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    for router in ALL_ROUTERS:
        dp.include_router(router)

    logger.info("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
