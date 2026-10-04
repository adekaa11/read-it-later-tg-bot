"""
tests/telegram_mock.py — поддельный Telegram Bot API для тестов.

FakeTelegramSession встаёт на место HTTP-сессии aiogram: вместо запросов
к api.telegram.org она складывает вызванные методы (SendMessage,
EditMessageText, AnswerCallbackQuery, ...) в список и отвечает заглушками.
Реальный токен, сеть и живой бот не нужны.
"""

import itertools
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import EditMessageText, SendMessage, TelegramMethod
from aiogram.types import (
    CallbackQuery,
    Chat,
    Message,
    MessageEntity,
    MessageOriginChannel,
    PhotoSize,
    Update,
    User,
)

USER_ID = 111
OTHER_USER_ID = 222

_ids = itertools.count(1)


class FakeTelegramSession(BaseSession):
    """Сессия aiogram, которая ничего не отправляет, а только записывает."""

    def __init__(self) -> None:
        super().__init__()
        self.requests: list[TelegramMethod] = []
        # Тип метода → текст ошибки, которой «ответит» Telegram
        self.fail_on: dict[type[TelegramMethod], str] = {}

    async def make_request(
        self, bot: Bot, method: TelegramMethod, timeout: int | None = None
    ):
        self.requests.append(method)

        if type(method) in self.fail_on:
            raise TelegramBadRequest(method=method, message=self.fail_on[type(method)])

        if isinstance(method, (SendMessage, EditMessageText)):
            return Message(
                message_id=getattr(method, "message_id", None) or next(_ids),
                date=datetime.now(timezone.utc),
                chat=Chat(id=method.chat_id, type="private"),
                text=method.text,
            )
        return True

    async def stream_content(self, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError("Скачивание файлов в тестах не используется")
        yield b""

    async def close(self) -> None:
        pass

    def sent(self, method_type: type[TelegramMethod]) -> list:
        """Все вызовы метода указанного типа, в порядке отправки."""
        return [m for m in self.requests if isinstance(m, method_type)]

    def texts(self) -> list[str]:
        """Тексты всех отправленных сообщений (SendMessage)."""
        return [m.text for m in self.sent(SendMessage)]


def _user(user_id: int) -> User:
    return User(id=user_id, is_bot=False, first_name="Tester")


def message_update(text: str | None = None, user_id: int = USER_ID, **fields) -> Update:
    """Входящее сообщение от пользователя (как его прислал бы Telegram).

    В fields можно передать любые поля Message: entities, caption,
    caption_entities, photo, forward_origin и т.д.
    """
    return Update(
        update_id=next(_ids),
        message=Message(
            message_id=next(_ids),
            date=datetime.now(timezone.utc),
            chat=Chat(id=user_id, type="private"),
            from_user=_user(user_id),
            text=text,
            **fields,
        ),
    )


def entity(kind: str, text: str, fragment: str, **fields) -> MessageEntity:
    """Разметка Telegram для куска текста (смещения — в единицах UTF-16)."""
    start = text.index(fragment)
    return MessageEntity(
        type=kind,
        offset=len(text[:start].encode("utf-16-le")) // 2,
        length=len(fragment.encode("utf-16-le")) // 2,
        **fields,
    )


def from_channel() -> MessageOriginChannel:
    """Отметка «переслано из канала»."""
    return MessageOriginChannel(
        type="channel",
        date=datetime.now(timezone.utc),
        chat=Chat(id=-1001234567890, type="channel", title="Канал"),
        message_id=42,
    )


PHOTO = [PhotoSize(file_id="photo", file_unique_id="photo", width=640, height=480)]


def callback_update(data: str, user_id: int = USER_ID) -> Update:
    """Нажатие inline-кнопки под сообщением бота."""
    return Update(
        update_id=next(_ids),
        callback_query=CallbackQuery(
            id=str(next(_ids)),
            from_user=_user(user_id),
            chat_instance="test-chat",
            data=data,
            message=Message(
                message_id=next(_ids),
                date=datetime.now(timezone.utc),
                chat=Chat(id=user_id, type="private"),
                text="📌 Старый текст сообщения",
            ),
        ),
    )
