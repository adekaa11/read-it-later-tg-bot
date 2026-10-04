"""
tests/conftest.py — общие фикстуры: временная база, бот с поддельным
Telegram API и диспетчер с роутерами бота.

По умолчанию тесты работают с SQLite. Если задать переменную окружения
TEST_DATABASE_URL (строка подключения к PostgreSQL), все тесты пройдут
на PostgreSQL — каждый в своей временной схеме, которая потом удаляется.
"""

import os
import uuid

import asyncpg
import pytest
from aiogram import Bot, Dispatcher

import database
from handlers import ALL_ROUTERS
from tests.telegram_mock import FakeTelegramSession


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@pytest.fixture(autouse=True)
async def db(tmp_path, monkeypatch):
    """Каждый тест получает свою чистую базу."""
    if TEST_DATABASE_URL:
        schema = f"readit_test_{uuid.uuid4().hex[:12]}"
        monkeypatch.setattr(database, "DATABASE_URL", TEST_DATABASE_URL)
        monkeypatch.setattr(database, "PG_SCHEMA", schema)
    else:
        monkeypatch.setattr(database, "DATABASE_URL", None)
        monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "test.db"))

    await database.init_db()
    yield
    await database.close_db()

    if TEST_DATABASE_URL:
        conn = await asyncpg.connect(TEST_DATABASE_URL)
        try:
            await conn.execute(f"DROP SCHEMA {schema} CASCADE")
        finally:
            await conn.close()


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
