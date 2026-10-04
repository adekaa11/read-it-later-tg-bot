"""Сохранение ссылок из сообщений пользователя."""

import pytest

import database
import handlers.links as links
from tests.telegram_mock import USER_ID, message_update

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
