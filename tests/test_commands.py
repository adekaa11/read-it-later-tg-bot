"""Команды /start, /list и /random."""

from aiogram.methods import SendMessage

import database
from tests.telegram_mock import OTHER_USER_ID, USER_ID, message_update


def button_data(method: SendMessage) -> str:
    """callback_data единственной inline-кнопки под сообщением."""
    return method.reply_markup.inline_keyboard[0][0].callback_data


async def test_start_greets_and_lists_commands(feed, session):
    await feed(message_update("/start"))

    [text] = session.texts()
    assert "Read It Later" in text
    assert "/list" in text and "/random" in text


async def test_list_without_links(feed, session):
    await feed(message_update("/list"))

    assert session.texts() == [
        "📭 Непрочитанных ссылок нет.\nПришлите мне ссылку, и я её сохраню!"
    ]


async def test_list_shows_five_newest_unread_links_with_buttons(feed, session):
    ids = [
        await database.add_link(USER_ID, f"https://example.com/{n}", f"Статья {n}")
        for n in range(1, 8)
    ]

    await feed(message_update("/list"))

    header, *cards = session.sent(SendMessage)
    assert header.text == "📚 Ваши непрочитанные ссылки (5):"
    assert [card.text for card in cards] == [
        f"📌 Статья {n}\nhttps://example.com/{n}" for n in (7, 6, 5, 4, 3)
    ]
    assert [button_data(card) for card in cards] == [
        f"mark_read:{link_id}" for link_id in reversed(ids[2:])
    ]


async def test_list_hides_read_and_foreign_links(feed, session):
    read_id = await database.add_link(USER_ID, "https://read.example", "Прочитанная")
    await database.mark_as_read(read_id)
    await database.add_link(OTHER_USER_ID, "https://other.example", "Чужая")
    await database.add_link(USER_ID, "https://mine.example", "Моя")

    await feed(message_update("/list"))

    assert session.texts() == [
        "📚 Ваши непрочитанные ссылки (1):",
        "📌 Моя\nhttps://mine.example",
    ]


async def test_list_survives_huge_url(feed, session):
    # Ссылка почти на весь лимит сообщения: вместе с заголовком она раньше
    # не влезала в 4096 символов, Telegram отклонял ответ, и /list падал
    huge_url = "https://example.com/?q=" + "x" * 4000
    await database.add_link(USER_ID, huge_url, huge_url)
    await database.add_link(USER_ID, "https://example.com/ok", "Обычная")

    await feed(message_update("/list"))

    texts = session.texts()
    assert len(texts) == 3  # заголовок + обе ссылки
    assert all(len(text) <= 4096 for text in texts)


async def test_random_without_links(feed, session):
    await feed(message_update("/random"))

    assert session.texts() == [
        "📭 Непрочитанных ссылок нет.\nПришлите мне ссылку, и я её сохраню!"
    ]


async def test_random_returns_unread_link_with_button(feed, session):
    link_id = await database.add_link(USER_ID, "https://example.com", "Пример")

    await feed(message_update("/random"))

    [reply] = session.sent(SendMessage)
    assert reply.text == "🎲 Почитайте прямо сейчас:\n📌 Пример\nhttps://example.com"
    assert button_data(reply) == f"mark_read:{link_id}"
