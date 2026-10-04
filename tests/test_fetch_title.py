"""
Загрузка заголовков страниц и защита от SSRF.

Вместо интернета — локальный aiohttp-сервер на 127.0.0.1.
"""

import asyncio

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from yarl import URL

import handlers.links as links

LATE_TITLE_PADDING = b"<!--" + b"x" * 100_000 + b"-->"


async def late_title(request: web.Request) -> web.StreamResponse:
    """<title> приходит не в первом куске ответа, а чуть позже."""
    response = web.StreamResponse(headers={"Content-Type": "text/html"})
    await response.prepare(request)
    await response.write(b"<html><head>" + LATE_TITLE_PADDING)
    await asyncio.sleep(0.1)
    await response.write(b"<title>Late title</title></head></html>")
    return response


async def slow(request: web.Request) -> web.Response:
    await asyncio.sleep(5)
    return web.Response(text="<title>Too slow</title>", content_type="text/html")


def page(body: str):
    """Обработчик, отдающий HTML-страницу."""

    async def handler(request: web.Request) -> web.Response:
        return web.Response(text=body, content_type="text/html")

    return handler


def redirect(location: str):
    """Обработчик, перенаправляющий на другой адрес (HTTP 302)."""

    async def handler(request: web.Request) -> web.Response:
        raise web.HTTPFound(location)

    return handler


async def cp1251(request: web.Request) -> web.Response:
    """Кодировка указана только в HTTP-заголовке, как на многих старых сайтах."""
    return web.Response(
        body="<title>Привет, мир</title>".encode("cp1251"),
        headers={"Content-Type": "text/html; charset=windows-1251"},
    )


async def missing(request: web.Request) -> web.Response:
    return web.Response(status=404)


@pytest.fixture
async def site():
    """Локальный «сайт»; site.hits — пути, которые у него запросили."""
    hits = []

    @web.middleware
    async def track(request, handler):
        hits.append(request.path)
        return await handler(request)

    app = web.Application(middlewares=[track])
    app.router.add_get("/page", page("<head><title> Hello\n  World </title></head>"))
    app.router.add_get(
        "/og", page('<head><meta property="og:title" content="OG title"></head>')
    )
    app.router.add_get("/no-title", page("<p>без заголовка</p>"))
    app.router.add_get("/cp1251", cp1251)
    app.router.add_get("/late", late_title)
    app.router.add_get("/slow", slow)
    app.router.add_get("/missing", missing)
    app.router.add_get("/to-page", redirect("/page"))
    app.router.add_get("/to-private", redirect("http://10.0.0.1/"))
    app.router.add_get("/loop", redirect("/loop"))

    server = TestServer(app, host="127.0.0.1")
    await server.start_server()
    server.hits = hits
    yield server
    await server.close()


@pytest.fixture
def allow_local(monkeypatch):
    """Разрешает 127.0.0.1, будто тестовый сервер — публичный сайт.

    Остальные непубличные адреса (10.0.0.1 и т.п.) по-прежнему запрещены.
    """
    real_is_public_ip = links.is_public_ip
    monkeypatch.setattr(
        links,
        "is_public_ip",
        lambda ip: ip == "127.0.0.1" or real_is_public_ip(ip),
    )


# --- обычная загрузка заголовков ---


@pytest.mark.parametrize(
    ("path", "title"),
    [
        ("/page", "Hello World"),  # лишние пробелы и переносы убраны
        ("/og", "OG title"),  # нет <title> — берём og:title
        ("/cp1251", "Привет, мир"),  # кодировка из HTTP-заголовка
        ("/late", "Late title"),  # заголовок не в первом куске ответа
        ("/to-page", "Hello World"),  # относительный редирект
        ("/no-title", None),
        ("/missing", None),  # HTTP 404
    ],
)
async def test_fetch_title(site, allow_local, path, title):
    assert await links.fetch_page_title(str(site.make_url(path))) == title


async def test_slow_site_times_out(site, allow_local, monkeypatch):
    monkeypatch.setattr(links, "FETCH_TIMEOUT_SECONDS", 0.5)

    assert await links.fetch_page_title(str(site.make_url("/slow"))) is None


async def test_redirect_loop_gives_up(site, allow_local, caplog):
    assert await links.fetch_page_title(str(site.make_url("/loop"))) is None
    assert site.hits.count("/loop") == links.MAX_REDIRECTS + 1
    assert "Слишком много редиректов" in caplog.text


@pytest.mark.parametrize("url", ["https://a..b", "http://[::1", "http://:80/"])
async def test_malformed_url_returns_none(url):
    assert await links.fetch_page_title(url) is None


# --- защита от SSRF ---


@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1",
        "localhost",
        "[::1]",
        "[::ffff:127.0.0.1]",
        "2130706433",  # 127.0.0.1 одним числом
        "127.1",  # сокращённая запись 127.0.0.1
        "0.0.0.0",
    ],
)
async def test_local_addresses_are_never_requested(site, host):
    url = f"http://{host}:{site.port}/page"

    assert await links.fetch_page_title(url) is None
    assert site.hits == []  # бот даже не обратился к серверу


async def test_redirect_to_private_network_is_blocked(site, allow_local, caplog):
    assert await links.fetch_page_title(str(site.make_url("/to-private"))) is None
    assert "Заблокирован непубличный адрес: http://10.0.0.1/" in caplog.text


async def test_cloud_metadata_address_is_blocked(caplog):
    url = "http://169.254.169.254/latest/meta-data/"

    assert await links.fetch_page_title(url) is None
    assert "Заблокирован непубличный адрес" in caplog.text


async def test_resolver_drops_private_addresses():
    resolver = links.PublicOnlyResolver()
    try:
        with pytest.raises(OSError):
            await resolver.resolve("localhost", 80)
    finally:
        await resolver.close()


@pytest.mark.parametrize(
    ("address", "public"),
    [
        ("8.8.8.8", True),
        ("2606:4700:4700::1111", True),
        ("127.0.0.1", False),
        ("10.1.2.3", False),
        ("172.16.0.1", False),
        ("192.168.1.1", False),
        ("169.254.169.254", False),
        ("100.64.0.1", False),  # CGNAT
        ("0.0.0.0", False),
        ("224.0.0.1", False),  # мультикаст
        ("::1", False),
        ("fd00::1", False),
        ("fe80::1", False),
        ("::ffff:127.0.0.1", False),
        ("::ffff:8.8.8.8", True),
        ("not-an-ip", False),
    ],
)
def test_is_public_ip(address, public):
    assert links.is_public_ip(address) is public


@pytest.mark.parametrize(
    ("url", "allowed"),
    [
        ("https://example.com/", True),
        ("http://8.8.8.8/", True),
        ("http://127.0.0.1/", False),
        ("http://127.0.0.1./", False),
        ("http://１２７.０.０.１/", False),  # «широкие» цифры
        ("http://2130706433/", False),
        ("ftp://example.com/", False),
        ("http:///path", False),
    ],
)
def test_is_allowed_url(url, allowed):
    assert links.is_allowed_url(URL(url)) is allowed
