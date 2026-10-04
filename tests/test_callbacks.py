"""Inline-кнопка «✅ Отметить прочитанным»."""

import pytest
from aiogram.methods import AnswerCallbackQuery, EditMessageText

import database
from tests.telegram_mock import OTHER_USER_ID, USER_ID, callback_update


async def test_mark_read_updates_db_and_edits_message(feed, session):
    link_id = await database.add_link(USER_ID, "https://example.com", "Hello World")

    await feed(callback_update(f"mark_read:{link_id}"))

    [edit] = session.sent(EditMessageText)
    # Заголовок зачёркнут, пробел между словами сохранился, кнопка убрана
    assert edit.text == "✅ Прочитано\nH̶e̶l̶l̶o̶ W̶o̶r̶l̶d̶\nhttps://example.com"
    assert edit.reply_markup is None

    [answer] = session.sent(AnswerCallbackQuery)
    assert answer.text == "Отмечено прочитанным ✔️"

    link = await database.get_link_by_id(link_id)
    assert link["is_read"] == 1


async def test_foreign_link_cannot_be_marked(feed, session):
    link_id = await database.add_link(OTHER_USER_ID, "https://example.com", "Чужая")

    await feed(callback_update(f"mark_read:{link_id}", user_id=USER_ID))

    [answer] = session.sent(AnswerCallbackQuery)
    assert answer.text == "Эта ссылка вам не доступна."
    assert answer.show_alert is True
    assert session.sent(EditMessageText) == []
    assert (await database.get_link_by_id(link_id))["is_read"] == 0


async def test_missing_link(feed, session):
    await feed(callback_update("mark_read:999"))

    [answer] = session.sent(AnswerCallbackQuery)
    assert answer.text == "Эта ссылка вам не доступна."


async def test_already_read_link(feed, session):
    link_id = await database.add_link(USER_ID, "https://example.com", "Пример")
    await database.mark_as_read(link_id)

    await feed(callback_update(f"mark_read:{link_id}"))

    [answer] = session.sent(AnswerCallbackQuery)
    assert answer.text == "Ссылка уже отмечена прочитанной."
    assert session.sent(EditMessageText) == []


@pytest.mark.parametrize(
    "data",
    ["mark_read:abc", "mark_read:-5", "mark_read:0", f"mark_read:{2**63}"],
)
async def test_invalid_callback_data(feed, session, data):
    await feed(callback_update(data))

    [answer] = session.sent(AnswerCallbackQuery)
    assert answer.text == "Некорректные данные."
    assert answer.show_alert is True


async def test_edit_error_still_answers_callback(feed, session):
    # Например, сообщение уже удалено — Telegram отвечает ошибкой
    session.fail_on[EditMessageText] = "Bad Request: message to edit not found"
    link_id = await database.add_link(USER_ID, "https://example.com", "Пример")

    await feed(callback_update(f"mark_read:{link_id}"))

    [answer] = session.sent(AnswerCallbackQuery)
    assert answer.text == "Отмечено прочитанным ✔️"
    assert (await database.get_link_by_id(link_id))["is_read"] == 1
