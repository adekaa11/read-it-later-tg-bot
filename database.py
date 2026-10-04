"""
database.py — хранение ссылок пользователей.

Где лежат данные, решает переменная окружения DATABASE_URL:
- задана     → PostgreSQL (например, Supabase). Таблица живёт в отдельной
               схеме readit, чтобы не смешиваться с другими таблицами проекта;
- не задана  → SQLite-файл DB_PATH (для локального запуска и тестов).

Функции модуля одинаковые для обеих баз: обработчики не знают,
с какой из них работают.

Таблица links:
    id         — первичный ключ
    user_id    — Telegram ID пользователя
    url        — сохранённая ссылка
    title      — заголовок страницы (или сам url, если парсинг не удался)
    is_read    — флаг прочтения
    created_at — дата и время сохранения (UTC)
"""

import logging
from datetime import datetime, timezone

import aiosqlite
import asyncpg

from config import DATABASE_URL, DB_PATH

logger = logging.getLogger(__name__)

# Схема PostgreSQL, в которой живут таблицы бота
PG_SCHEMA = "readit"

# Пул подключений к PostgreSQL; None — значит, работаем с SQLite
_pool: asyncpg.Pool | None = None


def _pg_schema_sql() -> str:
    """SQL, создающий схему и таблицу в PostgreSQL (если их ещё нет)."""
    return f"""
        CREATE SCHEMA IF NOT EXISTS {PG_SCHEMA};

        CREATE TABLE IF NOT EXISTS {PG_SCHEMA}.links (
            id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            user_id    BIGINT      NOT NULL,  -- ID в Telegram бывают > 2^31
            url        TEXT        NOT NULL,
            title      TEXT        NOT NULL,
            is_read    BOOLEAN     NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );

        CREATE INDEX IF NOT EXISTS idx_links_user_unread
        ON {PG_SCHEMA}.links (user_id, is_read);

        -- Защита на случай, если схему когда-нибудь откроют через API
        -- Supabase: без политик RLS посторонние роли не увидят ни строки.
        -- Бот подключается владельцем таблицы, на него RLS не действует.
        ALTER TABLE {PG_SCHEMA}.links ENABLE ROW LEVEL SECURITY;
    """


async def init_db() -> None:
    """Подключается к базе и создаёт таблицу links, если её ещё нет."""
    global _pool
    if DATABASE_URL:
        if _pool is None:
            _pool = await asyncpg.create_pool(
                DATABASE_URL,
                min_size=1,
                max_size=3,
                # Пулер Supabase в режиме Transaction не поддерживает
                # подготовленные запросы — отключаем их кэш
                statement_cache_size=0,
                command_timeout=15,
            )
        await _pool.execute(_pg_schema_sql())
        logger.info("База данных: PostgreSQL, схема %s.", PG_SCHEMA)
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS links (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                url        TEXT    NOT NULL,
                title      TEXT    NOT NULL,
                is_read    INTEGER NOT NULL DEFAULT 0,
                created_at TEXT    NOT NULL
            )
            """
        )
        # Индекс для быстрого поиска непрочитанных ссылок пользователя
        await db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_links_user_unread
            ON links (user_id, is_read)
            """
        )
        await db.commit()
    logger.info("База данных: SQLite, файл %s.", DB_PATH)


async def close_db() -> None:
    """Закрывает подключения к PostgreSQL (для SQLite ничего делать не нужно)."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def add_link(user_id: int, url: str, title: str) -> int:
    """
    Сохраняет новую ссылку пользователя (is_read=False).
    Возвращает id созданной записи.
    """
    if _pool is not None:
        return await _pool.fetchval(
            f"""
            INSERT INTO {PG_SCHEMA}.links (user_id, url, title)
            VALUES ($1, $2, $3)
            RETURNING id
            """,
            user_id,
            url,
            title,
        )

    created_at = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO links (user_id, url, title, is_read, created_at)
            VALUES (?, ?, ?, 0, ?)
            """,
            (user_id, url, title, created_at),
        )
        await db.commit()
        return cursor.lastrowid  # id новой записи


async def get_unread_links(user_id: int, limit: int = 5) -> list[dict]:
    """
    Возвращает список из `limit` последних непрочитанных ссылок пользователя
    (от самых новых к самым старым).
    """
    if _pool is not None:
        rows = await _pool.fetch(
            f"""
            SELECT id, url, title, created_at
            FROM {PG_SCHEMA}.links
            WHERE user_id = $1 AND NOT is_read
            ORDER BY created_at DESC, id DESC
            LIMIT $2
            """,
            user_id,
            limit,
        )
        return [dict(row) for row in rows]

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT id, url, title, created_at
            FROM links
            WHERE user_id = ? AND is_read = 0
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (user_id, limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_random_unread(user_id: int) -> dict | None:
    """Возвращает одну случайную непрочитанную ссылку пользователя или None."""
    if _pool is not None:
        row = await _pool.fetchrow(
            f"""
            SELECT id, url, title, created_at
            FROM {PG_SCHEMA}.links
            WHERE user_id = $1 AND NOT is_read
            ORDER BY random()
            LIMIT 1
            """,
            user_id,
        )
        return dict(row) if row else None

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """
            SELECT id, url, title, created_at
            FROM links
            WHERE user_id = ? AND is_read = 0
            ORDER BY RANDOM()
            LIMIT 1
            """,
            (user_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_link_by_id(link_id: int) -> dict | None:
    """Возвращает запись по её id (нужно для обработки inline-кнопки)."""
    if _pool is not None:
        row = await _pool.fetchrow(
            f"""
            SELECT id, user_id, url, title, is_read
            FROM {PG_SCHEMA}.links
            WHERE id = $1
            """,
            link_id,
        )
        return dict(row) if row else None

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, user_id, url, title, is_read FROM links WHERE id = ?",
            (link_id,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def mark_as_read(link_id: int) -> None:
    """Отмечает запись как прочитанную (is_read=True)."""
    if _pool is not None:
        await _pool.execute(
            f"UPDATE {PG_SCHEMA}.links SET is_read = TRUE WHERE id = $1", link_id
        )
        return

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE links SET is_read = 1 WHERE id = ?", (link_id,))
        await db.commit()
