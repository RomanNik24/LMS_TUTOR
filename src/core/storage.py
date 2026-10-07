"""Хранилище приватных файлов: S3-совместимый API через ``aioboto3`` (T4.03, docs/02 §2, docs/09).

Правила:
- bucket приватный: файлы отдаются только по подписанной ссылке на 10 минут;
- ключ объекта — UUID и безопасное расширение, имя файла от пользователя в ключ не попадает:
  ``homework/{assignment_id}/{uuid}.{ext}`` и ``materials/{homework_id}/{uuid}.{ext}``;
- ``boto3`` напрямую не используется (блокирует event loop): только ``aioboto3``;
- слой знает только про байты и ключи: проверка содержимого и прав — в ``FileService`` (T4.05).
"""

import re
import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol

import aioboto3
from botocore.config import Config

from src.core.config import Settings
from src.core.constants import S3_PRESIGN_TTL_SECONDS

_EXTENSION = re.compile(r"[a-z0-9]{1,5}")

ClientFactory = Callable[[bool], AbstractAsyncContextManager[Any]]


class ObjectStorage(Protocol):
    """Что нужно сервисам от хранилища (подменяется в тестах)."""

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        """Сохранить объект."""

    async def delete(self, key: str) -> None:
        """Удалить объект (отсутствующий объект — не ошибка)."""

    async def presign_get(self, key: str, *, expires: int = S3_PRESIGN_TTL_SECONDS) -> str:
        """Подписанная ссылка на скачивание."""


def _key(prefix: str, owner_id: int, extension: str) -> str:
    ext = extension.lower().lstrip(".")
    if not _EXTENSION.fullmatch(ext):
        raise ValueError(f"Недопустимое расширение файла: {extension!r}")
    return f"{prefix}/{owner_id}/{uuid.uuid4().hex}.{ext}"


def homework_key(assignment_id: int, extension: str) -> str:
    """Ключ файла выдачи (решение ученика или файл проверки): ``homework/{id}/{uuid}.{ext}``."""
    return _key("homework", assignment_id, extension)


def material_key(homework_id: int, extension: str) -> str:
    """Ключ материала преподавателя: ``materials/{id}/{uuid}.{ext}``."""
    return _key("materials", homework_id, extension)


class S3Storage:
    """Реализация ``ObjectStorage`` поверх S3-совместимого сервиса (MinIO, Timeweb, Selectel)."""

    def __init__(
        self,
        *,
        endpoint: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        region: str,
        public_endpoint: str = "",
        client_factory: ClientFactory | None = None,
    ) -> None:
        """Создать клиент хранилища.

        Args:
            endpoint: Адрес S3 API для самого приложения.
            bucket: Приватный bucket.
            access_key: Ключ доступа.
            secret_key: Секретный ключ.
            region: Регион (для MinIO любой согласованный).
            public_endpoint: Адрес, доступный клиенту, для подписанных ссылок; пусто — ``endpoint``.
            client_factory: Подмена создания клиента (тесты); получает флаг «для подписи ссылки».
        """
        self._bucket = bucket
        self._endpoint = endpoint
        self._public_endpoint = public_endpoint or endpoint
        self._access_key = access_key
        self._secret_key = secret_key
        self._region = region
        self._session = aioboto3.Session()
        self._client_factory = client_factory

    @classmethod
    def from_settings(cls, settings: Settings) -> "S3Storage":
        """Собрать хранилище из ``S3_*`` настроек."""
        return cls(
            endpoint=settings.s3_endpoint,
            bucket=settings.s3_bucket,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key.get_secret_value(),
            region=settings.s3_region,
            public_endpoint=settings.s3_public_endpoint,
        )

    def _client(self, for_signing: bool = False) -> AbstractAsyncContextManager[Any]:
        if self._client_factory is not None:
            return self._client_factory(for_signing)
        client: AbstractAsyncContextManager[Any] = self._session.client(
            "s3",
            endpoint_url=self._public_endpoint if for_signing else self._endpoint,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            region_name=self._region,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        return client

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        """Сохранить объект с типом содержимого."""
        async with self._client() as client:
            await client.put_object(
                Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
            )

    async def delete(self, key: str) -> None:
        """Удалить объект; S3 не считает ошибкой удаление отсутствующего ключа."""
        async with self._client() as client:
            await client.delete_object(Bucket=self._bucket, Key=key)

    async def presign_get(self, key: str, *, expires: int = S3_PRESIGN_TTL_SECONDS) -> str:
        """Подписанная ссылка на скачивание, действует ``expires`` секунд (по умолчанию 10 минут).

        Ссылка строится от ``S3_PUBLIC_ENDPOINT`` (или ``S3_ENDPOINT``): она должна открываться у
        клиента, а не только внутри сети сервера.
        """
        async with self._client(True) as client:
            url = await client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=expires,
            )
        return str(url)
