"""Тесты ядра безопасности T1.07: токены и проверка initData (docs/09 §2)."""

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import pytest
import time_machine
from src.core.exceptions import AppError
from src.core.security import hash_token, new_token, validate_init_data

pytestmark = pytest.mark.security

BOT_TOKEN = "123:TEST"  # noqa: S105 - тестовый токен, не секрет
NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
USER = {"id": 5_000_000_001, "first_name": "Аня", "username": "anya", "language_code": "ru"}


def _sign(fields: dict[str, str], bot_token: str = BOT_TOKEN) -> str:
    """Собрать initData тем же алгоритмом, что и Telegram."""
    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    digest = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": digest})


def _fields(auth_date: datetime = NOW, user: object = USER) -> dict[str, str]:
    result = {"auth_date": str(int(auth_date.timestamp())), "query_id": "AAH"}
    if user is not None:
        result["user"] = json.dumps(user, ensure_ascii=False)
    return result


def _reason(exc: pytest.ExceptionInfo[AppError]) -> object:
    return exc.value.details["reason"]


@pytest.fixture(autouse=True)
def _frozen() -> object:
    with time_machine.travel(NOW, tick=False):
        yield


def test_new_token_is_random_and_long() -> None:
    first, second = new_token(), new_token()
    assert first != second
    assert len(first) >= 43  # 32 байта в base64url


def test_hash_token_is_sha256_hex() -> None:
    digest = hash_token("abc")
    assert digest == hashlib.sha256(b"abc").hexdigest()
    assert len(digest) == 64
    assert hash_token("abc") != hash_token("abd")


def test_valid_init_data_returns_user() -> None:
    user = validate_init_data(_sign(_fields()), BOT_TOKEN)
    assert user.id == USER["id"]
    assert user.first_name == "Аня"
    assert user.username == "anya"
    assert user.language_code == "ru"
    assert user.last_name is None


def test_tampered_field_is_rejected() -> None:
    signed = _sign(_fields())
    tampered = signed.replace("AAH", "AAX")
    with pytest.raises(AppError) as exc:
        validate_init_data(tampered, BOT_TOKEN)
    assert exc.value.http_status == 401
    assert exc.value.code == "unauthenticated"
    assert _reason(exc) == "bad_signature"


def test_tampered_user_id_is_rejected() -> None:
    fields = _fields()
    signed = _sign(fields)
    forged = signed.replace("5000000001", "5000000002")
    with pytest.raises(AppError) as exc:
        validate_init_data(forged, BOT_TOKEN)
    assert _reason(exc) == "bad_signature"


def test_tampered_hash_is_rejected() -> None:
    signed = _sign(_fields())
    head, _, digest = signed.rpartition("hash=")
    flipped = ("0" if digest[0] != "0" else "1") + digest[1:]
    with pytest.raises(AppError) as exc:
        validate_init_data(head + "hash=" + flipped, BOT_TOKEN)
    assert _reason(exc) == "bad_signature"


def test_wrong_bot_token_is_rejected() -> None:
    with pytest.raises(AppError) as exc:
        validate_init_data(_sign(_fields(), "999:OTHER"), BOT_TOKEN)
    assert _reason(exc) == "bad_signature"


def test_expired_auth_date_is_rejected() -> None:
    old = NOW - timedelta(hours=24, seconds=1)
    with pytest.raises(AppError) as exc:
        validate_init_data(_sign(_fields(old)), BOT_TOKEN)
    assert _reason(exc) == "expired"


def test_auth_date_exactly_24h_is_accepted() -> None:
    edge = NOW - timedelta(hours=24)
    assert validate_init_data(_sign(_fields(edge)), BOT_TOKEN).id == USER["id"]


def test_auth_date_in_future_is_rejected() -> None:
    future = NOW + timedelta(minutes=10)
    with pytest.raises(AppError) as exc:
        validate_init_data(_sign(_fields(future)), BOT_TOKEN)
    assert _reason(exc) == "auth_date_in_future"


def test_custom_max_age() -> None:
    old = NOW - timedelta(hours=2)
    with pytest.raises(AppError):
        validate_init_data(_sign(_fields(old)), BOT_TOKEN, max_age_seconds=3600)


@pytest.mark.parametrize("raw", ["", "   ", "garbage", "auth_date=1&user=%7B%7D"])
def test_empty_or_broken_init_data_is_rejected(raw: str) -> None:
    with pytest.raises(AppError) as exc:
        validate_init_data(raw, BOT_TOKEN)
    assert exc.value.http_status == 401


def test_empty_bot_token_is_rejected() -> None:
    with pytest.raises(AppError):
        validate_init_data(_sign(_fields()), "")


def test_missing_user_is_rejected() -> None:
    with pytest.raises(AppError) as exc:
        validate_init_data(_sign(_fields(user=None)), BOT_TOKEN)
    assert _reason(exc) == "no_user"


@pytest.mark.parametrize(
    "user",
    [
        {"first_name": "A"},
        {"id": "7", "first_name": "A"},
        {"id": 7},
        [1, 2],
        {"id": True, "first_name": "A"},
    ],
)
def test_malformed_user_is_rejected(user: object) -> None:
    with pytest.raises(AppError) as exc:
        validate_init_data(_sign(_fields(user=user)), BOT_TOKEN)
    assert _reason(exc) == "bad_user"


def test_user_not_json_is_rejected() -> None:
    fields = _fields()
    fields["user"] = "{not json"
    with pytest.raises(AppError) as exc:
        validate_init_data(_sign(fields), BOT_TOKEN)
    assert _reason(exc) == "bad_user"


def test_bad_auth_date_is_rejected() -> None:
    fields = _fields()
    fields["auth_date"] = "yesterday"
    with pytest.raises(AppError) as exc:
        validate_init_data(_sign(fields), BOT_TOKEN)
    assert _reason(exc) == "bad_auth_date"


def test_duplicate_field_is_rejected() -> None:
    signed = _sign(_fields()) + "&query_id=EVIL"
    with pytest.raises(AppError) as exc:
        validate_init_data(signed, BOT_TOKEN)
    assert _reason(exc) == "duplicate_field"


def test_signature_is_compared_in_constant_time() -> None:
    """В коде нет сравнения подписи через == (проверка из плана T1.07)."""
    from pathlib import Path

    source = Path("src/core/security.py").read_text(encoding="utf-8")
    assert "hmac.compare_digest" in source
    assert "== received_hash" not in source
    assert "received_hash ==" not in source
