"""Ядро безопасности: токены и проверка Telegram ``initData`` (задача T1.07).

По ``docs/09`` §2: токены приглашений и входа — случайные (256 бит), в БД
хранится только SHA-256 хэш; ``initData`` Mini App проверяется на сервере по
алгоритму Telegram WebApp (HMAC) с ограничением возраста ``auth_date``.
Права определяются по записи в БД, а не по данным клиента.
"""

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from urllib.parse import parse_qsl

from src.core import texts
from src.core.constants import (
    INIT_DATA_FUTURE_TOLERANCE_SECONDS,
    INIT_DATA_MAX_AGE_SECONDS,
    TOKEN_BYTES,
)
from src.core.exceptions import AppError
from src.core.timeutils import utcnow

# Код и HTTP-статус при невалидных данных входа (docs/08 §1: 401 unauthenticated).
_UNAUTHENTICATED_CODE = "unauthenticated"


@dataclass(frozen=True)
class TelegramUser:
    """Пользователь Telegram из проверенных ``initData``.

    Attributes:
        id: Telegram ID (BIGINT).
        first_name: Имя.
        last_name: Фамилия (может отсутствовать).
        username: Username без ``@`` (может отсутствовать).
        language_code: Код языка интерфейса (может отсутствовать).
    """

    id: int
    first_name: str
    last_name: str | None
    username: str | None
    language_code: str | None


def new_token() -> str:
    """Сгенерировать случайный токен (256 бит) для приглашения или ссылки входа.

    Returns:
        URL-безопасная строка; сам токен в БД не хранится.
    """
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    """Вычислить SHA-256 хэш токена для хранения в ``auth_tokens.token_hash``.

    Args:
        token: Исходный токен.

    Returns:
        64 hex-символа.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _invalid(reason: str) -> AppError:
    """Единая ошибка проверки initData; причина идёт в details без данных клиента."""
    return AppError(
        texts.AUTH_INIT_DATA_INVALID,
        code=_UNAUTHENTICATED_CODE,
        details={"reason": reason},
        http_status=401,
    )


def _optional_str(payload: dict[str, object], key: str) -> str | None:
    """Вернуть необязательное строковое поле user или ``None``."""
    value = payload.get(key)
    return value if isinstance(value, str) else None


def validate_init_data(
    init_data: str,
    bot_token: str,
    max_age_seconds: int = INIT_DATA_MAX_AGE_SECONDS,
) -> TelegramUser:
    """Проверить подпись и срок ``initData`` Telegram WebApp.

    Алгоритм: ``secret_key = HMAC_SHA256(key="WebAppData", msg=bot_token)``;
    ``hash = HMAC_SHA256(secret_key, data_check_string)``, где строка —
    отсортированные пары ``key=value`` (кроме ``hash``) через ``\\n``.
    Подпись сравнивается через ``hmac.compare_digest``.

    Args:
        init_data: Сырая строка ``Telegram.WebApp.initData``.
        bot_token: Токен бота (секрет, в логи не попадает).
        max_age_seconds: Максимальный возраст ``auth_date`` (по умолчанию 24 ч).

    Returns:
        Пользователь Telegram из подписанных данных.

    Raises:
        AppError: 401 ``unauthenticated`` — подпись неверна, данные битые,
            ``auth_date`` просрочен или находится в будущем, нет ``user``.
    """
    if not init_data or not bot_token:
        raise _invalid("empty")
    pairs = parse_qsl(init_data, keep_blank_values=True)
    fields: dict[str, str] = {}
    for key, value in pairs:
        if key in fields:
            raise _invalid("duplicate_field")
        fields[key] = value
    received_hash = fields.pop("hash", "")
    if not received_hash:
        raise _invalid("no_hash")

    data_check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    expected = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected.encode("ascii"), received_hash.encode("utf-8")):
        raise _invalid("bad_signature")

    try:
        auth_date = int(fields["auth_date"])
    except (KeyError, ValueError):
        raise _invalid("bad_auth_date") from None
    age = utcnow().timestamp() - auth_date
    if age > max_age_seconds:
        raise _invalid("expired")
    if age < -INIT_DATA_FUTURE_TOLERANCE_SECONDS:
        raise _invalid("auth_date_in_future")

    raw_user = fields.get("user")
    if raw_user is None:
        raise _invalid("no_user")
    try:
        payload = json.loads(raw_user)
    except ValueError:
        raise _invalid("bad_user") from None
    if not isinstance(payload, dict):
        raise _invalid("bad_user")
    user_id = payload.get("id")
    first_name = payload.get("first_name")
    if not isinstance(user_id, int) or isinstance(user_id, bool) or not isinstance(first_name, str):
        raise _invalid("bad_user")
    return TelegramUser(
        id=user_id,
        first_name=first_name,
        last_name=_optional_str(payload, "last_name"),
        username=_optional_str(payload, "username"),
        language_code=_optional_str(payload, "language_code"),
    )
