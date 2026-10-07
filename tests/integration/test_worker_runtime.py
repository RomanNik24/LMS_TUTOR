"""Воркер TaskIQ как процесс: задача доходит через Redis, SIGTERM завершает его (T5.04)."""

import asyncio
import importlib
import os
import signal
import sys
import uuid
from pathlib import Path

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from sqlalchemy import text
from taskiq import Context, TaskiqState

ROOT = Path(__file__).resolve().parents[2]
WAIT_SECONDS = 30
# Дольше пяти секунд: столько redis-py 8 по умолчанию ждёт ответ, пока воркер простаивает
IDLE_SECONDS = 9


async def hc_server() -> tuple[TestServer, list[str], asyncio.Event]:
    hits: list[str] = []
    arrived = asyncio.Event()

    async def handler(request: web.Request) -> web.Response:
        hits.append(request.path)
        arrived.set()
        return web.Response(text="OK")

    app = web.Application()
    app.router.add_get("/ping/{key}", handler)
    server = TestServer(app)
    await server.start_server()
    return server, hits, arrived


def read_log(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


async def wait_for_log(path: Path, marker: str) -> None:
    """Дождаться строки в журнале воркера (журнал в файле, а не в канале, см. stop_worker)."""
    async with asyncio.timeout(WAIT_SECONDS):
        while marker not in read_log(path):  # noqa: ASYNC110 - опрос файла, событий нет
            await asyncio.sleep(0.2)


async def stop_worker(process: asyncio.subprocess.Process) -> None:
    """Остановить воркер вместе с дочерними процессами.

    POSIX: SIGTERM, процесс обязан завершиться сам и с кодом 0 (корректное завершение).
    Windows: сигналов нет, ``TerminateProcess`` убил бы только родителя, а дочерний процесс
    воркера остался бы жить и держать порты и файлы, поэтому дерево убивается ``taskkill /T``.
    """
    if process.returncode is not None:
        return
    if sys.platform == "win32":
        killer = await asyncio.create_subprocess_exec(
            "taskkill", "/PID", str(process.pid), "/T", "/F", stdout=asyncio.subprocess.DEVNULL
        )
        await killer.wait()
    else:
        process.send_signal(signal.SIGTERM)
    try:
        await asyncio.wait_for(process.wait(), WAIT_SECONDS)
    except TimeoutError:
        process.kill()
        await process.wait()
        pytest.fail("Воркер не завершился после сигнала остановки")


async def test_worker_process_runs_heartbeat_and_stops_on_sigterm(
    redis_url: str, migrated_postgres_url: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    server, hits, arrived = await hc_server()
    log_path = tmp_path / "worker.log"
    env = {
        **os.environ,
        "APP_ENV": "local",
        "DATABASE_URL": migrated_postgres_url,
        "REDIS_URL": redis_url,
        "DEFAULT_TIMEZONE": "UTC",
        "SESSION_SECRET": "",
        "HEALTHCHECK_URL": str(server.make_url("/ping/runtime-check")),
        "SENTRY_DSN": "",
        # своя очередь: даже на общем Redis тестовый воркер не заберёт задачи рабочего стенда
        "WORKER_QUEUE_NAME": f"taskiq-test-{uuid.uuid4().hex}",
    }
    # журнал в файл: канал наследуют дочерние процессы воркера, и на Windows его закрытие
    # не наступало бы, пока жив любой из них (так тест и зависал)
    with log_path.open("wb") as log:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "taskiq",
            "worker",
            "src.worker.broker:broker",
            "src.worker.tasks",
            "--workers",
            "1",
            cwd=ROOT,
            env=env,
            stdout=log,
            stderr=asyncio.subprocess.STDOUT,
        )
    config_module = None
    try:
        await wait_for_log(log_path, "Listening started")
        # воркер простаивает дольше таймаута чтения по умолчанию и обязан остаться живым
        await asyncio.sleep(IDLE_SECONDS)
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        from src.core import config as config_module  # noqa: PLC0415
        from src.worker import broker as broker_module  # noqa: PLC0415
        from src.worker import tasks as tasks_module  # noqa: PLC0415

        config_module.get_settings.cache_clear()
        importlib.reload(broker_module)
        importlib.reload(tasks_module)
        client = broker_module.broker
        await client.startup()
        try:
            await tasks_module.heartbeat.kiq()
            await asyncio.wait_for(arrived.wait(), WAIT_SECONDS)
        finally:
            await client.shutdown()
        assert hits == ["/ping/runtime-check"]
    finally:
        await stop_worker(process)
        await server.close()
        if config_module is not None:
            config_module.get_settings.cache_clear()
    output = read_log(log_path)
    if sys.platform != "win32":
        assert process.returncode == 0, output[-800:]
    assert "is dead" not in output
    assert "TimeoutError" not in output


async def test_task_session_dependency_gives_working_database_session(
    migrated_postgres_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("DATABASE_URL", migrated_postgres_url)
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("DEFAULT_TIMEZONE", "UTC")
    monkeypatch.setenv("SESSION_SECRET", "")
    from src.core import config as config_module  # noqa: PLC0415

    config_module.get_settings.cache_clear()
    from src.worker import broker as broker_module  # noqa: PLC0415
    from src.worker import deps as deps_module  # noqa: PLC0415

    importlib.reload(broker_module)
    state = TaskiqState()
    await broker_module.open_resources(state)
    try:
        context = Context.__new__(Context)
        context.state = state
        generator = deps_module.get_session(context)
        session = await anext(generator)
        assert (await session.execute(text("SELECT 1"))).scalar_one() == 1
        await generator.aclose()
    finally:
        await broker_module.close_resources(state)
        config_module.get_settings.cache_clear()
