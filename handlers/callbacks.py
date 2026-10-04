"""
handlers/callbacks.py — обработка нажатий inline-кнопок.

Callback data имеет вид: mark_read:<id записи в БД>
При нажатии:
1. Запись в БД обновляется (is_read=True).
2. Сообщение бота редактируется: заголовок зачёркивается,
   кнопка убирается.
"""

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery

import database
from handlers.common import fit_message, shorten, strikethrough

logger = logging.getLogger(__name__)

router = Router(name="callbacks")


@router.callback_query(F.data.startswith("mark_read:"))
async def cb_mark_read(callback: CallbackQuery) -> None:
    """Отмечает ссылку прочитанной и редактирует сообщение."""
    try:
        link_id = int(callback.data.split(":", 1)[1])
    except ValueError:
        await callback.answer("Некорректные данные.", show_alert=True)
        return

    link = await database.get_link_by_id(link_id)

    # Защита: запись отсутствует или принадлежит другому пользователю
    if not link or link["user_id"] != callback.from_user.id:
        await callback.answer("Эта ссылка вам не доступна.", show_alert=True)
        return

    if link["is_read"]:
        await callback.answer("Ссылка уже отмечена прочитанной.")
        return

    # Обновляем запись в базе
    await database.mark_as_read(link_id)

    # Редактируем сообщение: зачёркиваем заголовок и убираем кнопку
    new_text = fit_message(
        "✅ Прочитано\n"
        f"{strikethrough(shorten(link['title']))}\n"
        f"{link['url']}"
    )
    try:
        await callback.message.edit_text(new_text, reply_markup=None)
    except TelegramBadRequest as exc:
        # Сообщение не изменилось или уже удалено — не критично
        logger.warning("Не удалось отредактировать сообщение: %s", exc)

    await callback.answer("Отмечено прочитанным ✔️")
