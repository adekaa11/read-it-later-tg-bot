"""
Запуск бота: webhook (на Render) и polling (локально).

Webhook-приложение запускается по-настоящему — на локальном порту,
а Telegram заменяет поддельная сессия из tests/telegram_mock.py.
"""

import asyncio

import pytest
from aiogram.methods import DeleteWebhook, GetUpdates, SetWebhook
from aiohttp.test_utils import TestClient, TestServer

import main
from tests.telegram_mock import message_update

BASE_URL = "https://read-it-later.onrender.com"
SECRET = "test-secret"


@pytest.fixture
def webhook_settings(monkeypatch):
    monkeypatch.setattr(main, "WEBHOOK_BASE_URL", BASE_URL)
    monkeypatch.setattr(main, "WEBHOOK_SECRET", SECRET)


@pytest.fixture
async def client(webhook_settings, bot, dp):
    """Запущенное webhook-приложение бота (как на Render) и клиент к нему."""
    async with TestClient(TestServer(main.create_webhook_app(bot, dp))) as client:
        yield client


def telegram_json(text: str) -> dict:
    """Апдейт в том виде, в котором Telegram присылает его на webhook."""
    return message_update(text).model_dump(
        mode="json", by_alias=True, exclude_none=True
    )


async def wait_until(condition, timeout: float = 3.0) -> None:
    """Ждёт, пока фоновая обработка апдейта дойдёт до результата."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not condition():
        assert loop.time() < deadline, "не дождались обработки апдейта"
        await asyncio.sleep(0.01)


async def test_startup_sets_webhook(client, session):
    [request] = session.sent(SetWebhook)

    assert request.url == f"{BASE_URL}/webhook"
    assert request.secret_token == SECRET
    assert set(request.allowed_updates) == {"message", "callback_query"}
    # Сообщение, которое разбудило сервис, не должно потеряться
    assert request.drop_pending_updates is False


async def test_health_page(client):
    response = await client.get("/")

    assert response.status == 200
    assert await response.text() == "Bot is live!"


async def test_message_from_telegram_is_handled(client, session):
    response = await client.post(
        "/webhook",
        json=telegram_json("/start"),
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
    )

    assert response.status == 200
    await wait_until(lambda: session.texts())
    assert "Read It Later" in session.texts()[0]


@pytest.mark.parametrize(
    "headers", [{}, {"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"}]
)
async def test_request_without_secret_is_rejected(client, session, headers):
    response = await client.post(
        "/webhook", json=telegram_json("/start"), headers=headers
    )

    assert response.status == 401
    await asyncio.sleep(0.1)
    assert session.texts() == []


async def test_shutdown_keeps_webhook(webhook_settings, bot, dp, session):
    async with TestClient(TestServer(main.create_webhook_app(bot, dp))):
        pass  # запуск и остановка, как когда Render усыпляет сервис

    assert len(session.sent(SetWebhook)) == 1
    assert session.sent(DeleteWebhook) == []


async def test_repeated_update_is_handled_once(feed, session):
    # Telegram повторил доставку, пока Render будил сервис
    update = message_update("/start")

    await feed(update)
    await feed(update)

    assert len(session.texts()) == 1


async def test_polling_does_not_steal_webhook_from_server(bot, dp, session):
    session.webhook_url = f"{BASE_URL}/webhook"

    with pytest.raises(SystemExit, match="webhook"):
        await main.run_polling(bot, dp)

    assert session.sent(DeleteWebhook) == []
    assert session.sent(GetUpdates) == []
    assert session.closed  # без предупреждений о незакрытой сессии


async def test_polling_starts_without_webhook(bot, dp, monkeypatch):
    started = []

    async def fake_start_polling(*bots, **kwargs):
        started.append(bots)

    monkeypatch.setattr(dp, "start_polling", fake_start_polling)
    monkeypatch.setattr(main, "PORT", None)

    await main.run_polling(bot, dp)

    assert started == [(bot,)]
