"""
database.py — вся логика работы с базой данных SQLite (через aiosqlite).

Таблица links:
    id         INTEGER  — первичный ключ
    user_id    INTEGER  — Telegram ID пользователя
    url        TEXT     — сохранённая ссылка
    title      TEXT     — заголовок страницы (или сам url, если парсинг не удался)
    is_read    INTEGER  — флаг прочтения (0 = не прочитано, 1 = прочитано)
    created_at TEXT     — дата и время сохранения (UTC, ISO-формат)
"""

from datetime import datetime, timezone

import aiosqlite

from config import DB_PATH


async def init_db() -> None:
    """Создаёт таблицу links при старте бота, если она ещё не существует."""
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


async def add_link(user_id: int, url: str, title: str) -> int:
    """
    Сохраняет новую ссылку пользователя (is_read=False).
    Возвращает id созданной записи.
    """
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
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE links SET is_read = 1 WHERE id = ?", (link_id,))
        await db.commit()
