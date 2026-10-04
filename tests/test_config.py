"""Проверка настроек перед запуском (config.validate_config)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

import config

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def valid_token(monkeypatch):
    monkeypatch.setattr(config, "BOT_TOKEN", "42:TEST-TOKEN")
    monkeypatch.setattr(config, "DATABASE_URL", None)


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
