"""
handlers/commands.py — команды /list и /random.

/list   — 5 последних непрочитанных ссылок (каждая отдельным сообщением
          с inline-кнопкой «Отметить прочитанным»).
/random — одна случайная непрочитанная ссылка.
"""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

import database
from handlers.common import format_link_text, mark_read_keyboard

router = Router(name="commands")


@router.message(Command("list"))
async def cmd_list(message: Message) -> None:
    """Показывает 5 последних непрочитанных ссылок пользователя."""
    links = await database.get_unread_links(message.from_user.id, limit=5)

    if not links:
        await message.answer(
            "📭 Непрочитанных ссылок нет.\n"
            "Пришлите мне ссылку, и я её сохраню!"
        )
        return

    await message.answer(f"📚 Ваши непрочитанные ссылки ({len(links)}):")

    # Каждую ссылку отправляем отдельным сообщением со своей inline-кнопкой,
    # чтобы при нажатии кнопки можно было отредактировать именно это сообщение
    for link in links:
        await message.answer(
            format_link_text(link),
            reply_markup=mark_read_keyboard(link["id"]),
        )


@router.message(Command("random"))
async def cmd_random(message: Message) -> None:
    """Выдаёт одну случайную непрочитанную ссылку."""
    link = await database.get_random_unread(message.from_user.id)

    if not link:
        await message.answer(
            "📭 Непрочитанных ссылок нет.\n"
            "Пришлите мне ссылку, и я её сохраню!"
        )
        return

    await message.answer(
        format_link_text(link, prefix="🎲 Почитайте прямо сейчас:"),
        reply_markup=mark_read_keyboard(link["id"]),
    )
