"""Настройки приложения MY_LMS.

Значения берутся из переменных окружения и из локального файла `.env.local`.
Файл с реальными секретами не коммитится и никогда не выводится в лог.
"""

from typing import Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.core.constants import (
    APP_ENV_LOCAL,
    APP_ENV_PROD,
    APP_ENVIRONMENTS,
    BOT_MODE_POLLING,
    BOT_MODES,
    ENV_FILE_NAME,
    S3_REGION_DEFAULT,
    SCHEDULE_HORIZON_WEEKS_DEFAULT,
    SECRET_MIN_BYTES,
)


class Settings(BaseSettings):
    """Конфигурация приложения.

    Полный список переменных окружения — `docs/02` §7 (шаблон `.env.example`).
    В `local` почти всё необязательно; в `prod` включается строгая проверка
    секретов (см. `_validate_prod_secrets`).

    Attributes:
        app_env: Окружение приложения (`local`, `staging`, `prod`).
        database_url: Строка подключения к PostgreSQL (async-драйвер).
        redis_url: Строка подключения к Redis.
        session_secret: Секрет для подписи серверных сессий.
        session_cookie_secure: Флаг `Secure` у cookie сессии; `false` допустим только
            в `local` (HTTP без TLS), в `prod` обязателен `true`.
        default_timezone: Часовой пояс по умолчанию (IANA) для новых пользователей.
        bot_token: Токен Telegram-бота от @BotFather.
        bot_mode: Режим бота: `polling` (локально) или `webhook` (сервер).
        webhook_url: Публичный HTTPS-адрес эндпоинта вебхука бота.
        webhook_secret: Секрет заголовка `X-Telegram-Bot-Api-Secret-Token`.
        owner_telegram_id: Числовой Telegram ID владельца (роль `owner`).
        teacher_contact_url: Ссылка на контакт преподавателя для учеников.
        public_base_url: Публичный базовый URL backend (ссылки входа, вебхуки).
        s3_endpoint / s3_bucket / s3_access_key / s3_secret_key / s3_region:
            Параметры S3-совместимого хранилища приватных файлов (docs/10 §5).
        sentry_dsn: DSN Sentry; пусто — интеграция отключена.
        schedule_horizon_weeks: Горизонт генерации уроков из шаблонов, недель.
        telegram_api_base: Альтернативный базовый URL Telegram API (docs/02 §6).
        telegram_proxy_url: SOCKS/HTTP-прокси для исходящих запросов бота.
    """

    model_config = SettingsConfigDict(
        env_file=ENV_FILE_NAME,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default=APP_ENV_LOCAL, validation_alias="APP_ENV")
    database_url: str = Field(validation_alias="DATABASE_URL")
    redis_url: str = Field(validation_alias="REDIS_URL")
    session_secret: SecretStr = Field(default=SecretStr(""), validation_alias="SESSION_SECRET")
    session_cookie_secure: bool = Field(default=True, validation_alias="SESSION_COOKIE_SECURE")
    default_timezone: str = Field(validation_alias="DEFAULT_TIMEZONE")

    # --- Telegram-бот (docs/02 §7) ---
    bot_token: SecretStr = Field(default=SecretStr(""), validation_alias="BOT_TOKEN")
    bot_mode: str = Field(default=BOT_MODE_POLLING, validation_alias="BOT_MODE")
    webhook_url: str = Field(default="", validation_alias="WEBHOOK_URL")
    webhook_secret: SecretStr = Field(default=SecretStr(""), validation_alias="WEBHOOK_SECRET")
    owner_telegram_id: int | None = Field(default=None, validation_alias="OWNER_TELEGRAM_ID")
    teacher_contact_url: str = Field(default="", validation_alias="TEACHER_CONTACT_URL")
    public_base_url: str = Field(default="", validation_alias="PUBLIC_BASE_URL")

    # --- S3-совместимое хранилище файлов (docs/02 §7, docs/10 §5) ---
    s3_endpoint: str = Field(default="", validation_alias="S3_ENDPOINT")
    s3_bucket: str = Field(default="", validation_alias="S3_BUCKET")
    s3_access_key: str = Field(default="", validation_alias="S3_ACCESS_KEY")
    s3_secret_key: SecretStr = Field(default=SecretStr(""), validation_alias="S3_SECRET_KEY")
    s3_region: str = Field(default=S3_REGION_DEFAULT, validation_alias="S3_REGION")

    # --- Мониторинг ошибок ---
    sentry_dsn: SecretStr = Field(default=SecretStr(""), validation_alias="SENTRY_DSN")

    # --- Расписание ---
    schedule_horizon_weeks: int = Field(
        default=SCHEDULE_HORIZON_WEEKS_DEFAULT, validation_alias="SCHEDULE_HORIZON_WEEKS"
    )

    # --- Доступ к Telegram из РФ (docs/02 §6) ---
    telegram_api_base: str = Field(default="", validation_alias="TELEGRAM_API_BASE")
    telegram_proxy_url: SecretStr = Field(
        default=SecretStr(""), validation_alias="TELEGRAM_PROXY_URL"
    )

    @model_validator(mode="after")
    def validate_core_fields(self) -> Self:
        """Проверить допустимость значений, важных для запуска приложения.

        Строгость — только по секретам (см. `validate_prod_secrets`); здесь
        сверяются справочники: окружение, часовой пояс, режим бота и
        горизонт расписания (docs/02 §7).

        Raises:
            ValueError: Какое-либо поле недопустимо.
        """
        if self.app_env not in APP_ENVIRONMENTS:
            raise ValueError(
                f"APP_ENV={self.app_env!r}: допустимы только {', '.join(APP_ENVIRONMENTS)}"
            )
        try:
            ZoneInfo(self.default_timezone)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError(f"DEFAULT_TIMEZONE неизвестен: {self.default_timezone!r}") from error
        if self.bot_mode not in BOT_MODES:
            raise ValueError(f"BOT_MODE={self.bot_mode!r}: допустимы {', '.join(BOT_MODES)}")
        if self.schedule_horizon_weeks < 1:
            raise ValueError("SCHEDULE_HORIZON_WEEKS должен быть >= 1")
        return self

    @model_validator(mode="after")
    def validate_prod_secrets(self) -> Self:
        """В production обязательны непустые секреты (задача T1.01).

        Требования: `BOT_TOKEN`, `WEBHOOK_SECRET` и `SESSION_SECRET` длиной
        не менее 32 байт. Значения в текст ошибки не попадают — наружу идёт
        только имя переменной (docs/09: секреты не логируются и не раскрываются).

        В остальных окружениях (`local`, `staging`) эти поля необязательны:
        локально бот без токена просто не стартует (поведение — задачи этапа 2).

        Raises:
            ValueError: Если какой-то из обязательных prod-секретов отсутствует
                или `SESSION_SECRET` короче 32 байт.
        """
        if self.app_env != APP_ENV_PROD:
            return self
        if not self.session_cookie_secure:
            raise ValueError("APP_ENV=prod: SESSION_COOKIE_SECURE должен быть true")
        missing = [
            name
            for name, value in (
                ("BOT_TOKEN", self.bot_token.get_secret_value().strip()),
                ("WEBHOOK_SECRET", self.webhook_secret.get_secret_value().strip()),
            )
            if not value
        ]
        secret = self.session_secret.get_secret_value()
        if len(secret.encode("utf-8")) < SECRET_MIN_BYTES:
            missing.append(
                f"SESSION_SECRET (минимум {SECRET_MIN_BYTES} байт, "
                f"сейчас {len(secret.encode('utf-8'))})"
            )
        if missing:
            raise ValueError(
                "APP_ENV=prod: отсутствуют обязательные настройки: " + "; ".join(missing)
            )
        return self
