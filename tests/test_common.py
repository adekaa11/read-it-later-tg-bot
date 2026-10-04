"""Утилиты форматирования из handlers/common.py."""

from handlers.common import (
    fit_message,
    format_link_text,
    mark_read_keyboard,
    shorten,
    strikethrough,
)


def utf16_len(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def test_strikethrough_keeps_spaces():
    assert strikethrough("Hello World") == "H̶e̶l̶l̶o̶ W̶o̶r̶l̶d̶"


def test_shorten():
    assert shorten("короткий") == "короткий"
    long_text = shorten("слово " * 100, limit=20)
    assert len(long_text) <= 20 and long_text.endswith("…")


def test_fit_message_keeps_short_text():
    assert fit_message("привет") == "привет"


def test_fit_message_respects_telegram_limit():
    assert utf16_len(fit_message("x" * 5000)) <= 4096
    # Эмодзи занимают в UTF-16 две единицы — это тоже учитывается
    trimmed = fit_message("😀" * 3000)
    assert utf16_len(trimmed) <= 4096 and trimmed.endswith("…")


def test_format_link_text():
    link = {"title": "Заголовок", "url": "https://example.com"}

    assert format_link_text(link) == "📌 Заголовок\nhttps://example.com"
    assert format_link_text(link, prefix="🎲 Почитайте прямо сейчас:") == (
        "🎲 Почитайте прямо сейчас:\n📌 Заголовок\nhttps://example.com"
    )


def test_mark_read_keyboard():
    [[button]] = mark_read_keyboard(42).inline_keyboard

    assert button.text == "✅ Отметить прочитанным"
    assert button.callback_data == "mark_read:42"
