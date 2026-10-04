"""Сохранение ссылок из сообщений пользователя."""

import pytest

import database
import handlers.links as links
from tests.telegram_mock import PHOTO, USER_ID, entity, from_channel, message_update

TITLES = {
    "https://example.com/article": "Пример статьи",
    "https://example.org/": "Example Domain",
}


@pytest.fixture
def fetched(monkeypatch) -> list[str]:
    """Подменяет загрузку заголовков: сайты не нужны, адреса запоминаются."""
    requested = []

    async def fake_fetch_page_title(url: str) -> str | None:
        requested.append(url)
        return TITLES.get(url)

    monkeypatch.setattr(links, "fetch_page_title", fake_fetch_page_title)
    return requested


async def saved_links() -> list[tuple[str, str]]:
    rows = await database.get_unread_links(USER_ID, limit=100)
    return sorted((row["url"], row["title"]) for row in rows)


async def test_link_is_saved_with_page_title(feed, session, fetched):
    await feed(message_update("Почитать потом: https://example.com/article."))

    assert fetched == ["https://example.com/article"]  # точка в конце отрезана
    assert session.texts() == ["✅ Сохранено: Пример статьи"]
    assert await saved_links() == [("https://example.com/article", "Пример статьи")]


async def test_link_without_title_is_saved_as_url(feed, session, fetched):
    await feed(message_update("https://no-title.example/page"))

    assert session.texts() == ["✅ Сохранено: https://no-title.example/page"]
    assert await saved_links() == [
        ("https://no-title.example/page", "https://no-title.example/page")
    ]


async def test_several_links_are_saved_in_order_without_duplicates(
    feed, session, fetched
):
    await feed(
        message_update(
            "https://example.org/ и https://example.com/article, "
            "а ещё раз https://example.org/"
        )
    )

    assert session.texts() == [
        "✅ Сохранено: Example Domain",
        "✅ Сохранено: Пример статьи",
    ]
    assert len(await saved_links()) == 2


async def test_too_many_links_are_capped(feed, session, fetched):
    urls = [f"https://example.com/{n}" for n in range(links.MAX_LINKS_PER_MESSAGE + 2)]

    await feed(message_update(" ".join(urls)))

    texts = session.texts()
    assert len(await saved_links()) == links.MAX_LINKS_PER_MESSAGE
    assert len(texts) == links.MAX_LINKS_PER_MESSAGE + 1
    assert texts[-1].startswith("⚠️") and "(2)" in texts[-1]


async def test_long_title_is_shortened(feed, session, monkeypatch):
    async def long_title(url: str) -> str:
        return "Очень длинный заголовок " * 100

    monkeypatch.setattr(links, "fetch_page_title", long_title)

    await feed(message_update("https://example.com/long"))

    [(_, title)] = await saved_links()
    assert len(title) <= 300 and title.endswith("…")
    assert session.texts() == [f"✅ Сохранено: {title}"]


async def test_broken_link_is_still_saved(feed, session):
    # Настоящая загрузка заголовка: раньше UnicodeError ронял обработчик,
    # и пользователь не получал ответа
    await feed(message_update("https://a..b"))

    assert session.texts() == ["✅ Сохранено: https://a..b"]
    assert await saved_links() == [("https://a..b", "https://a..b")]


async def test_text_without_links_is_ignored(feed, session, fetched):
    await feed(message_update("просто текст без ссылок"))

    assert session.requests == []
    assert fetched == []
    assert await saved_links() == []


# --- пересланные посты, скрытые ссылки, подписи к фото ---


async def test_hidden_link_in_forwarded_post(feed, session, fetched):
    text = "Новая статья в блоге. Читать далее"
    await feed(
        message_update(
            text,
            entities=[
                entity(
                    "text_link", text, "Читать далее", url="https://example.com/article"
                )
            ],
            forward_origin=from_channel(),
        )
    )

    assert session.texts() == ["✅ Сохранено: Пример статьи"]
    assert await saved_links() == [("https://example.com/article", "Пример статьи")]


async def test_link_in_photo_caption(feed, session, fetched):
    caption = "Фото дня, подробнее: https://example.org/"
    await feed(
        message_update(
            photo=PHOTO,
            caption=caption,
            caption_entities=[entity("url", caption, "https://example.org/")],
        )
    )

    assert session.texts() == ["✅ Сохранено: Example Domain"]
    assert await saved_links() == [("https://example.org/", "Example Domain")]


async def test_hidden_link_in_forwarded_photo_caption(feed, session, fetched):
    caption = "Разбор новой версии → по ссылке"
    await feed(
        message_update(
            photo=PHOTO,
            caption=caption,
            caption_entities=[
                entity("text_link", caption, "по ссылке", url="https://example.org/")
            ],
            forward_origin=from_channel(),
        )
    )

    assert session.texts() == ["✅ Сохранено: Example Domain"]


async def test_caption_without_markup_is_parsed_too(feed, session, fetched):
    # Разметки нет — ссылку находит регулярное выражение
    await feed(message_update(photo=PHOTO, caption="Тут: https://example.org/."))

    assert fetched == ["https://example.org/"]


async def test_url_entity_keeps_parentheses(feed, fetched):
    # Регулярное выражение обрезало бы ссылку на «(»; разметка Telegram — нет
    url = "https://en.wikipedia.org/wiki/Python_(programming_language)"
    text = f"Про язык: {url}"

    await feed(message_update(text, entities=[entity("url", text, url)]))

    assert fetched == [url]


async def test_offsets_after_emoji(feed, fetched):
    # Эмодзи занимает в UTF-16 две единицы — смещения Telegram это учитывают
    text = "🔥🔥 Смотри тут и вот https://example.org/"
    await feed(
        message_update(
            text,
            entities=[
                entity("text_link", text, "тут", url="https://example.com/article"),
                entity("url", text, "https://example.org/"),
            ],
        )
    )

    assert fetched == ["https://example.com/article", "https://example.org/"]


async def test_same_link_visible_and_hidden_is_saved_once(feed, session, fetched):
    text = "https://example.org/ — и ещё раз здесь"
    await feed(
        message_update(
            text,
            entities=[
                entity("url", text, "https://example.org/"),
                entity("text_link", text, "здесь", url="https://example.org/"),
            ],
        )
    )

    assert session.texts() == ["✅ Сохранено: Example Domain"]


async def test_non_http_hidden_link_is_ignored(feed, session, fetched):
    text = "Подписывайтесь на канал"
    await feed(
        message_update(
            text,
            entities=[
                entity("text_link", text, "канал", url="tg://resolve?domain=example")
            ],
        )
    )

    assert session.requests == []
    assert fetched == []


async def test_photo_without_caption_is_ignored(feed, session, fetched):
    await feed(message_update(photo=PHOTO))

    assert session.requests == []
