"""
Хранилище ссылок (database.py).

Тесты одинаковые для обеих баз: по умолчанию идут на SQLite, а с
переменной TEST_DATABASE_URL — на PostgreSQL (см. tests/conftest.py).
"""

import pytest

import database
from tests.conftest import TEST_DATABASE_URL
from tests.telegram_mock import OTHER_USER_ID, USER_ID

# Реальные Telegram ID давно не влезают в 32-битное число
BIG_USER_ID = 9_000_000_001

# Схема по умолчанию — до того, как фикстура db подменит её на временную
# (модуль импортируется раньше, чем запускаются тесты)
DEFAULT_PG_SCHEMA = database.PG_SCHEMA


async def test_add_and_get_link():
    link_id = await database.add_link(USER_ID, "https://example.com", "Пример 🔥")

    link = await database.get_link_by_id(link_id)

    assert link["user_id"] == USER_ID
    assert link["url"] == "https://example.com"
    assert link["title"] == "Пример 🔥"
    assert not link["is_read"]


async def test_missing_link():
    assert await database.get_link_by_id(123456) is None


async def test_unread_links_newest_first_with_limit():
    for n in range(1, 8):
        await database.add_link(USER_ID, f"https://example.com/{n}", f"Статья {n}")

    links = await database.get_unread_links(USER_ID, limit=5)

    assert [link["title"] for link in links] == [f"Статья {n}" for n in (7, 6, 5, 4, 3)]


async def test_unread_links_skip_read_and_foreign():
    read_id = await database.add_link(USER_ID, "https://read.example", "Прочитанная")
    await database.mark_as_read(read_id)
    await database.add_link(OTHER_USER_ID, "https://other.example", "Чужая")
    await database.add_link(USER_ID, "https://mine.example", "Моя")

    links = await database.get_unread_links(USER_ID)

    assert [link["url"] for link in links] == ["https://mine.example"]


async def test_mark_as_read_touches_only_one_link():
    first = await database.add_link(USER_ID, "https://one.example", "Один")
    second = await database.add_link(USER_ID, "https://two.example", "Два")

    await database.mark_as_read(first)

    assert (await database.get_link_by_id(first))["is_read"]
    assert not (await database.get_link_by_id(second))["is_read"]


async def test_random_unread():
    assert await database.get_random_unread(USER_ID) is None

    link_id = await database.add_link(USER_ID, "https://example.com", "Пример")
    read_id = await database.add_link(USER_ID, "https://read.example", "Прочитано")
    await database.mark_as_read(read_id)

    for _ in range(5):
        assert (await database.get_random_unread(USER_ID))["id"] == link_id


async def test_big_telegram_user_id():
    link_id = await database.add_link(BIG_USER_ID, "https://example.com", "Пример")

    assert (await database.get_link_by_id(link_id))["user_id"] == BIG_USER_ID
    assert len(await database.get_unread_links(BIG_USER_ID)) == 1


async def test_init_db_twice_keeps_data():
    link_id = await database.add_link(USER_ID, "https://example.com", "Пример")

    await database.init_db()  # бот вызывает его при каждом запуске

    assert await database.get_link_by_id(link_id) is not None


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="нужен TEST_DATABASE_URL")
async def test_postgres_table_lives_in_own_schema_with_rls():
    row = await database._pool.fetchrow(
        """
        SELECT c.relrowsecurity
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = $1 AND c.relname = 'links'
        """,
        database.PG_SCHEMA,
    )

    assert row is not None  # таблица создана именно в схеме бота
    assert row["relrowsecurity"] is True  # RLS включён


def test_default_postgres_schema_is_readit():
    assert DEFAULT_PG_SCHEMA == "readit"
