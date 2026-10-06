"""Юнит-тесты конфигурации Settings (задача T1.01).

Проверяют: полный набор переменных docs/02 §7, строгую проверку секретов
в prod и мягкую в local, а также понятные сообщения об ошибках без
утечки значений секретов (docs/09).
"""

import pytest
from pydantic import ValidationError
from src.core.config import Settings

# Обязательные базовые переменные (тестовые значения, не секреты).
BASE_ENV = {
    "DATABASE_URL": "postgresql+asyncpg://lms:lms@localhost:5432/lms",
    "REDIS_URL": "redis://localhost:6379/0",
    "DEFAULT_TIMEZONE": "Europe/Moscow",
}

# Корректный набор секретов для prod (SESSION_SECRET >= 32 байт).
PROD_SECRETS = {
    "BOT_TOKEN": "123456:AA-test-token",
    "WEBHOOK_SECRET": "webhook-secret-value",
    "SESSION_SECRET": "s" * 40,
}


def _settings(monkeypatch: pytest.MonkeyPatch, **extra: str) -> Settings:
    """Собрать Settings с изолированным окружением (без .env.local).

    Args:
        monkeypatch: Fixture pytest для подмены окружения.
        **extra: Пары имя переменной → значение поверх BASE_ENV.

    Returns:
        Собранная конфигурация.
    """
    env = {**BASE_ENV, **extra}
    for key in env:
        monkeypatch.setenv(key, env[key])
    return Settings(_env_file=None)


def test_local_allows_missing_optional_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    """В `local` BOT_TOKEN/WEBHOOK_SECRET/SESSION_SECRET необязательны."""
    settings = _settings(monkeypatch, APP_ENV="local")

    assert settings.app_env == "local"
    assert settings.bot_token.get_secret_value() == ""
    assert settings.webhook_secret.get_secret_value() == ""
    assert settings.session_secret.get_secret_value() == ""


@pytest.mark.parametrize("missing", ["BOT_TOKEN", "WEBHOOK_SECRET", "SESSION_SECRET"])
def test_prod_requires_secrets(missing: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """Без любого из обязательных prod-секретов конфигурация не собирается."""
    env = {"APP_ENV": "prod", **PROD_SECRETS}
    env[missing] = ""

    with pytest.raises(ValidationError) as excinfo:
        _settings(monkeypatch, **env)

    assert missing in str(excinfo.value)


def test_prod_rejects_short_session_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """`SESSION_SECRET` короче 32 байт — ошибка запуска в prod."""
    with pytest.raises(ValidationError) as excinfo:
        _settings(monkeypatch, APP_ENV="prod", **{**PROD_SECRETS, "SESSION_SECRET": "x" * 31})

    assert "SESSION_SECRET" in str(excinfo.value)


def test_prod_error_does_not_leak_secret_values(monkeypatch: pytest.MonkeyPatch) -> None:
    """Сообщение об ошибке содержит имена переменных, но не их значения."""
    secret_value = "super-secret-session-value-that-is-long-enough-1234"  # noqa: S105
    with pytest.raises(ValidationError) as excinfo:
        _settings(
            monkeypatch,
            APP_ENV="prod",
            BOT_TOKEN="",
            WEBHOOK_SECRET="wh",  # noqa: S106
            SESSION_SECRET=secret_value,
        )

    text = str(excinfo.value)
    assert "BOT_TOKEN" in text
    assert secret_value not in text


def test_prod_accepts_full_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Полный корректный набор prod-переменных собирается без ошибок."""
    settings = _settings(monkeypatch, APP_ENV="prod", **PROD_SECRETS)

    assert settings.bot_token.get_secret_value() == PROD_SECRETS["BOT_TOKEN"]


def test_new_variables_are_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Все переменные docs/02 §7 читаются из окружения с нужными типами."""
    settings = _settings(
        monkeypatch,
        BOT_MODE="webhook",
        WEBHOOK_URL="https://example.org/tg/webhook",
        OWNER_TELEGRAM_ID="123456789",
        TEACHER_CONTACT_URL="https://t.me/teacher",
        PUBLIC_BASE_URL="https://api.example.org",
        S3_ENDPOINT="https://s3.timeweb.cloud",
        S3_BUCKET="lms-files",
        S3_ACCESS_KEY="ak",
        S3_SECRET_KEY="sk",  # noqa: S106
        S3_REGION="nl-ams-1",
        SENTRY_DSN="https://public@sentry.example.com/1",
        SCHEDULE_HORIZON_WEEKS="4",
        TELEGRAM_API_BASE="https://tg-api.example.org/bot",
        TELEGRAM_PROXY_URL="socks5://proxy:1080",
    )

    assert settings.bot_mode == "webhook"
    assert settings.webhook_url == "https://example.org/tg/webhook"
    assert settings.owner_telegram_id == 123456789
    assert settings.teacher_contact_url == "https://t.me/teacher"
    assert settings.public_base_url == "https://api.example.org"
    assert settings.s3_endpoint == "https://s3.timeweb.cloud"
    assert settings.s3_bucket == "lms-files"
    assert settings.s3_access_key == "ak"
    assert settings.s3_secret_key.get_secret_value() == "sk"
    assert settings.s3_region == "nl-ams-1"
    assert settings.sentry_dsn.get_secret_value() == "https://public@sentry.example.com/1"
    assert settings.schedule_horizon_weeks == 4
    assert settings.telegram_api_base == "https://tg-api.example.org/bot"
    assert settings.telegram_proxy_url.get_secret_value() == "socks5://proxy:1080"


def test_defaults_for_optional_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    """Необязательные поля имеют безопасные значения по умолчанию."""
    settings = _settings(monkeypatch)

    assert settings.bot_mode == "polling"
    assert settings.s3_region == "us-east-1"
    assert settings.schedule_horizon_weeks == 2
    assert settings.owner_telegram_id is None


def test_invalid_bot_mode_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Неизвестный `BOT_MODE` — понятная ошибка конфигурации."""
    with pytest.raises(ValidationError) as excinfo:
        _settings(monkeypatch, BOT_MODE="carrier-pigeon")

    assert "BOT_MODE" in str(excinfo.value)


def test_invalid_timezone_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Неизвестный IANA-пояс в `DEFAULT_TIMEZONE` — ошибка конфигурации."""
    with pytest.raises(ValidationError) as excinfo:
        _settings(monkeypatch, DEFAULT_TIMEZONE="Mars/Olympus_Mons")

    assert "DEFAULT_TIMEZONE" in str(excinfo.value)


def test_invalid_app_env_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """Неизвестное `APP_ENV` — ошибка конфигурации."""
    with pytest.raises(ValidationError) as excinfo:
        _settings(monkeypatch, APP_ENV="development")

    assert "APP_ENV" in str(excinfo.value)
