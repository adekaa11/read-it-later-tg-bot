"""
handlers/common.py — общие утилиты для обработчиков.
"""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

# Комбинирующий символ Unicode "длинное зачёркивание" (U+0336).
# Добавляется после каждого символа, чтобы визуально зачеркнуть текст.
_STRIKETHROUGH_CHAR = "\u0336"


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
    lines.append(f"📌 {link['title']}")
    lines.append(link["url"])
    return "\n".join(lines)


def strikethrough(text: str) -> str:
    """Зачёркивает текст с помощью комбинируемого символа U+0336."""
    return "".join(ch + _STRIKETHROUGH_CHAR for ch in text if not ch.isspace())
