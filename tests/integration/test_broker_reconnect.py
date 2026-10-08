"""Брокер переживает обрыв соединений с Redis (аудит 2026-10-08, п. 1).

После перезапуска Redis в пуле брокера остаются соединения, закрытые сервером. Раньше первая
команда через каждое из них падала: планировщик терял задачу (``SendTaskError``), а воркер
падал на ``BRPOP``. Здесь сервер сам закрывает соединения брокера (``CLIENT KILL``), как при
перезапуске, и проверяется, что отправка и приём продолжают работать.
"""

import asyncio
import contextlib

import pytest
import redis.asyncio as aioredis
from taskiq.message import BrokerMessage
from taskiq_redis import ListQueueBroker

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("app_settings_env")]

QUEUE = "taskiq"
WAIT_SECONDS = 10


def _broker(redis_url: str) -> ListQueueBroker:
    """Брокер с настройками приложения (модуль читает Settings при импорте — импорт под env)."""
    from src.worker.broker import create_broker  # noqa: PLC0415

    return create_broker(redis_url)


def _message(task_id: str) -> BrokerMessage:
    return BrokerMessage(
        task_id=task_id, task_name="heartbeat", message=task_id.encode(), labels={}
    )


async def _kill_clients(admin: aioredis.Redis, command: str) -> int:
    """Закрыть со стороны сервера все соединения, последней командой которых была ``command``."""
    killed = 0
    for client in await admin.client_list():
        if client.get("cmd") == command:
            await admin.execute_command("CLIENT", "KILL", "ID", client["id"])
            killed += 1
    return killed


async def test_kick_survives_connections_closed_by_server(
    redis_client: aioredis.Redis, redis_url: str
) -> None:
    await redis_client.delete(QUEUE)
    broker = _broker(redis_url)
    await broker.startup()
    try:
        await broker.kick(_message("first"))
        assert await _kill_clients(redis_client, "lpush") >= 1
        await broker.kick(_message("second"))  # без повтора здесь был ConnectionError
        assert await redis_client.llen(QUEUE) == 2
    finally:
        await broker.shutdown()
        await redis_client.delete(QUEUE)


async def test_listen_survives_connection_closed_by_server(
    redis_client: aioredis.Redis, redis_url: str
) -> None:
    await redis_client.delete(QUEUE)
    broker = _broker(redis_url)
    await broker.startup()
    listener = broker.listen()
    receive = asyncio.ensure_future(anext(listener))
    try:
        # дождаться, пока воркер повиснет на BRPOP, и оборвать это соединение со стороны сервера
        for _ in range(50):
            if any(c.get("cmd") == "brpop" for c in await redis_client.client_list()):
                break
            await asyncio.sleep(0.1)
        assert await _kill_clients(redis_client, "brpop") == 1
        await redis_client.lpush(QUEUE, b"after-reconnect")
        assert await asyncio.wait_for(receive, WAIT_SECONDS) == b"after-reconnect"
    finally:
        receive.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await receive
        await listener.aclose()
        await broker.shutdown()
        await redis_client.delete(QUEUE)
