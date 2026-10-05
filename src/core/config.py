"""Настройки приложения MY_LMS.

Значения берутся из переменных окружения и из локального файла `.env.local`.
Файл с реальными секретами не коммитится и никогда не выводится в лог.
"""

from typing import Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.core.constants import APP_ENV_LOCAL, APP_ENV_PROD, ENV_FILE_NAME


class Settings(BaseSettings):
    """Конфигурация приложения.

    Attributes:
        app_env: Окружение приложения (`local`, `staging`, `prod`).
        database_url: Строка подключения к PostgreSQL (async-драйвер).
        redis_url: Строка подключения к Redis.
        session_secret: Секрет для подписи серверных сессий.
        default_timezone: Часовой пояс по умолчанию (IANA) для новых пользователей.
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
    default_timezone: str = Field(validation_alias="DEFAULT_TIMEZONE")

    @model_validator(mode="after")
    def validate_session_secret_in_prod(self) -> Self:
        """В production пустой `SESSION_SECRET` — ошибка запуска.

        В остальных окружениях секрет можно оставить пустым:
        подпись сессий там ещё не используется.
        """
        if self.app_env == APP_ENV_PROD and not self.session_secret.get_secret_value().strip():
            raise ValueError("SESSION_SECRET обязателен при APP_ENV=prod")
        return self
