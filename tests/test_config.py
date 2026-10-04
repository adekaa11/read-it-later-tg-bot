"""Проверка настроек перед запуском (config.validate_config)."""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

import config

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def valid_settings(monkeypatch):
    monkeypatch.setattr(config, "BOT_TOKEN", "42:TEST-TOKEN")
    monkeypatch.setattr(config, "DATABASE_URL", None)
    monkeypatch.setattr(config, "WEBHOOK_BASE_URL", None)
    monkeypatch.setattr(config, "WEBHOOK_SECRET", "test-secret_1")


def test_valid_config_passes():
    config.validate_config()


def test_missing_token(monkeypatch):
    monkeypatch.setattr(config, "BOT_TOKEN", None)

    with pytest.raises(SystemExit, match="BOT_TOKEN"):
        config.validate_config()


def test_supabase_session_pooler_url_is_accepted(monkeypatch):
    monkeypatch.setattr(
        config,
        "DATABASE_URL",
        "postgresql://postgres.abcd:secret@aws-0-eu-central-1.pooler.supabase.com:5432/postgres",
    )

    config.validate_config()


def test_values_pasted_with_spaces_are_trimmed():
    # При копировании в настройки хостинга легко захватить пробел или
    # перевод строки. Настройки читаются при импорте, поэтому — отдельный процесс.
    env = {
        **os.environ,
        "BOT_TOKEN": " 42:TEST-TOKEN\n",
        "DATABASE_URL": " postgresql://user:pass@host:5432/postgres \n",
    }
    code = "import config; print(config.BOT_TOKEN, config.DATABASE_URL, sep='|')"

    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip() == (
        "42:TEST-TOKEN|postgresql://user:pass@host:5432/postgres"
    )


def test_project_url_instead_of_database_url(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", "https://abcd.supabase.co")

    with pytest.raises(SystemExit, match="postgresql://"):
        config.validate_config()


def test_password_placeholder_left_in_url(monkeypatch):
    monkeypatch.setattr(
        config,
        "DATABASE_URL",
        "postgresql://postgres.abcd:[YOUR-PASSWORD]@aws-0-eu-central-1.pooler.supabase.com:5432/postgres",
    )

    with pytest.raises(SystemExit, match="YOUR-PASSWORD"):
        config.validate_config()


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({}, None),  # локально → polling
        (
            {"RENDER_EXTERNAL_URL": "https://read-it-later.onrender.com"},
            "https://read-it-later.onrender.com",
        ),
        (
            {
                "WEBHOOK_BASE_URL": "https://bot.example.com/",
                "RENDER_EXTERNAL_URL": "https://read-it-later.onrender.com",
            },
            "https://bot.example.com",  # явный адрес важнее адреса Render
        ),
    ],
)
def test_webhook_base_url(monkeypatch, env, expected):
    for name in ("WEBHOOK_BASE_URL", "RENDER_EXTERNAL_URL"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)

    assert config._webhook_base_url() == expected


def test_webhook_needs_https(monkeypatch):
    monkeypatch.setattr(config, "WEBHOOK_BASE_URL", "http://bot.example.com")

    with pytest.raises(SystemExit, match="https://"):
        config.validate_config()


def test_webhook_secret_with_bad_characters(monkeypatch):
    monkeypatch.setattr(config, "WEBHOOK_SECRET", "секрет с пробелами")

    with pytest.raises(SystemExit, match="WEBHOOK_SECRET"):
        config.validate_config()


def test_default_webhook_secret_comes_from_token(monkeypatch):
    monkeypatch.delenv("WEBHOOK_SECRET", raising=False)

    secret = config._webhook_secret()
    monkeypatch.setattr(config, "BOT_TOKEN", "43:OTHER-TOKEN")

    # Подходит Telegram и меняется вместе с токеном
    assert re.fullmatch(r"[A-Za-z0-9_-]{1,256}", secret)
    assert config._webhook_secret() != secret


def test_webhook_secret_from_env(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET", "my-own_secret")

    assert config._webhook_secret() == "my-own_secret"
