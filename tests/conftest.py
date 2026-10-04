"""
tests/conftest.py — общие фикстуры: временная база, бот с поддельным
Telegram API и диспетчер с роутерами бота.
"""

import pytest
from aiogram import Bot, Dispatcher

import database
from handlers import ALL_ROUTERS
from tests.telegram_mock import FakeTelegramSession


@pytest.fixture(autouse=True)
async def db(tmp_path, monkeypatch):
    """Каждый тест получает свою чистую базу SQLite во временной папке."""
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "test.db"))
    await database.init_db()


@pytest.fixture(scope="session")
def dp() -> Dispatcher:
    """Диспетчер с роутерами бота — тот же порядок, что и в main.py.

    Роутер aiogram можно подключить только к одному диспетчеру,
    поэтому диспетчер общий на все тесты (состояния он не хранит).
    """
    dispatcher = Dispatcher()
    for router in ALL_ROUTERS:
        dispatcher.include_router(router)
    return dispatcher


@pytest.fixture
def session() -> FakeTelegramSession:
    return FakeTelegramSession()


@pytest.fixture
def bot(session) -> Bot:
    # Токен ненастоящий: запросы всё равно не покидают FakeTelegramSession
    return Bot(token="42:TEST-TOKEN", session=session)


@pytest.fixture
def feed(dp, bot):
    """Передаёт апдейт боту — так, будто он пришёл от Telegram."""

    async def _feed(update):
        return await dp.feed_update(bot, update)

    return _feed
