"""Хранилище файлов (T4.03): ключи и вызовы клиента S3 без сети."""

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from src.core.constants import S3_PRESIGN_TTL_SECONDS
from src.core.storage import S3Storage, homework_key, material_key

UUID_KEY = r"[0-9a-f]{32}"


class FakeClient:
    """Записывает вызовы так, как их видит aioboto3-клиент."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def put_object(self, **kwargs: Any) -> None:
        self.calls.append(("put_object", kwargs))

    async def delete_object(self, **kwargs: Any) -> None:
        self.calls.append(("delete_object", kwargs))

    async def generate_presigned_url(self, operation: str, **kwargs: Any) -> str:
        self.calls.append((operation, kwargs))
        return "https://files.example/signed"


def make_storage() -> tuple[S3Storage, FakeClient, list[bool]]:
    client = FakeClient()
    signing_flags: list[bool] = []

    @asynccontextmanager
    async def factory(for_signing: bool) -> AsyncIterator[FakeClient]:
        signing_flags.append(for_signing)
        yield client

    storage = S3Storage(
        endpoint="http://minio:9000",
        bucket="lms-files",
        access_key="key",
        secret_key="secret",  # noqa: S106 - заглушка теста
        region="us-east-1",
        public_endpoint="https://files.example",
        client_factory=factory,
    )
    return storage, client, signing_flags


def test_homework_key_has_uuid_and_extension() -> None:
    key = homework_key(42, "JPG")
    assert re.fullmatch(rf"homework/42/{UUID_KEY}\.jpg", key)


def test_material_key_layout() -> None:
    assert re.fullmatch(rf"materials/7/{UUID_KEY}\.pdf", material_key(7, ".pdf"))


def test_keys_are_unique() -> None:
    assert homework_key(1, "png") != homework_key(1, "png")


@pytest.mark.parametrize("bad", ["", "jpeg1234", "j/g", "../x", "jpg ", "я"])
def test_unsafe_extension_is_rejected(bad: str) -> None:
    with pytest.raises(ValueError, match="расширение"):
        homework_key(1, bad)


async def test_put_sends_bucket_key_body_and_content_type() -> None:
    storage, client, flags = make_storage()
    await storage.put("homework/1/a.jpg", b"data", "image/jpeg")
    assert client.calls == [
        (
            "put_object",
            {
                "Bucket": "lms-files",
                "Key": "homework/1/a.jpg",
                "Body": b"data",
                "ContentType": "image/jpeg",
            },
        )
    ]
    assert flags == [False]


async def test_delete_sends_bucket_and_key() -> None:
    storage, client, _ = make_storage()
    await storage.delete("homework/1/a.jpg")
    assert client.calls == [("delete_object", {"Bucket": "lms-files", "Key": "homework/1/a.jpg"})]


async def test_presign_defaults_to_ten_minutes_and_uses_public_client() -> None:
    storage, client, flags = make_storage()
    url = await storage.presign_get("homework/1/a.jpg")
    assert url == "https://files.example/signed"
    assert S3_PRESIGN_TTL_SECONDS == 600
    assert client.calls == [
        (
            "get_object",
            {
                "Params": {"Bucket": "lms-files", "Key": "homework/1/a.jpg"},
                "ExpiresIn": 600,
            },
        )
    ]
    assert flags == [True]


async def test_presign_accepts_custom_ttl() -> None:
    storage, client, _ = make_storage()
    await storage.presign_get("k", expires=5)
    assert client.calls[0][1]["ExpiresIn"] == 5
