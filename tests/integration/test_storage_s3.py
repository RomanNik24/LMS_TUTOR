"""Хранилище файлов против настоящего S3 API (T4.03).

По умолчанию поднимается локальный S3-сервер ``moto`` (HTTP-протокол S3 без Docker). Чтобы
прогнать тесты против MinIO, задайте ``S3_TEST_ENDPOINT``, ``S3_TEST_BUCKET``,
``S3_TEST_ACCESS_KEY`` и ``S3_TEST_SECRET_KEY`` (бакет должен существовать). Настоящий MinIO проверяет TERM (T4.04).
"""

import os
import uuid
from collections.abc import Iterator

import httpx
import pytest
from moto.server import ThreadedMotoServer
from src.core.storage import S3Storage, homework_key

pytestmark = pytest.mark.integration

REGION = "us-east-1"


@pytest.fixture(scope="module")
def storage() -> Iterator[S3Storage]:
    endpoint = os.environ.get("S3_TEST_ENDPOINT")
    if endpoint:
        yield S3Storage(
            endpoint=endpoint,
            bucket=os.environ["S3_TEST_BUCKET"],
            access_key=os.environ["S3_TEST_ACCESS_KEY"],
            secret_key=os.environ["S3_TEST_SECRET_KEY"],
            region=REGION,
        )
        return
    server = ThreadedMotoServer(port=0)
    server.start()
    host, port = server.get_host_and_port()
    url = f"http://{host}:{port}"
    bucket = f"lms-test-{uuid.uuid4().hex[:8]}"
    httpx.put(f"{url}/{bucket}")  # создать bucket: S3 API CreateBucket
    try:
        yield S3Storage(
            endpoint=url,
            bucket=bucket,
            access_key="testing",
            secret_key="testing",  # noqa: S106 - заглушка локального мок-сервера
            region=REGION,
        )
    finally:
        server.stop()


async def test_put_presign_download_and_delete(storage: S3Storage) -> None:
    key = homework_key(1, "png")
    await storage.put(key, b"\x89PNG-test-bytes", "image/png")
    url = await storage.presign_get(key)
    assert "X-Amz-Expires=600" in url
    assert "X-Amz-Signature=" in url
    async with httpx.AsyncClient() as http:
        response = await http.get(url)
    assert response.status_code == 200
    assert response.content == b"\x89PNG-test-bytes"
    assert response.headers["content-type"] == "image/png"
    await storage.delete(key)
    async with httpx.AsyncClient() as http:
        gone = await http.get(await storage.presign_get(key))
    assert gone.status_code == 404


async def test_delete_of_missing_object_is_not_an_error(storage: S3Storage) -> None:
    await storage.delete(homework_key(99, "jpg"))


async def test_presigned_url_uses_public_endpoint(storage: S3Storage) -> None:
    public = S3Storage(
        endpoint="http://internal-minio:9000",
        bucket="lms-files",
        access_key="k",
        secret_key="s",  # noqa: S106
        region=REGION,
        public_endpoint="https://files.example.com",
    )
    url = await public.presign_get("homework/1/a.jpg")
    assert url.startswith("https://files.example.com/lms-files/homework/1/a.jpg?")
    del storage
