"""
handlers/common.py — общие утилиты для обработчиков.
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import MAX_TITLE_LENGTH

# Комбинирующий символ Unicode "длинное зачёркивание" (U+0336).
# Добавляется после каждого символа, чтобы визуально зачеркнуть текст.
_STRIKETHROUGH_CHAR = "\u0336"

# Telegram не отправит сообщение длиннее 4096 символов (считает в UTF-16)
_TELEGRAM_TEXT_LIMIT = 4096


def mark_read_keyboard(link_id: int) -> InlineKeyboardMarkup:
    """Inline-клавиатура с кнопкой «Отметить прочитанным» для записи link_id."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Отметить прочитанным",
                    callback_data=f"mark_read:{link_id}",
                )
            ]
        ]
    )


def format_link_text(link: dict, prefix: str = "") -> str:
    """Форматирует текст сообщения со ссылкой: заголовок + URL."""
    lines = []
    if prefix:
        lines.append(prefix)
    lines.append(f"📌 {shorten(link['title'])}")
    lines.append(link["url"])
    return fit_message("\n".join(lines))


def strikethrough(text: str) -> str:
    """Зачёркивает текст символом U+0336; пробелы оставляет как есть."""
    return "".join(ch if ch.isspace() else ch + _STRIKETHROUGH_CHAR for ch in text)


def shorten(text: str, limit: int = MAX_TITLE_LENGTH) -> str:
    """Обрезает текст до limit символов, ставя «…» в конце."""
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def fit_message(text: str) -> str:
    """Обрезает текст сообщения, если он не влезает в лимит Telegram."""
    # Эмодзи и другие символы вне BMP занимают в UTF-16 две единицы
    if len(text.encode("utf-16-le")) // 2 <= _TELEGRAM_TEXT_LIMIT:
        return text
    result, size = [], 1  # 1 — место под «…»
    for ch in text:
        size += 2 if ord(ch) > 0xFFFF else 1
        if size > _TELEGRAM_TEXT_LIMIT:
            break
        result.append(ch)
    return "".join(result) + "…"
