"""Воркер TaskIQ как процесс: задача доходит через Redis, SIGTERM завершает его (T5.04).

Остановка зависит от ОС (аудит 2026-10-08, п. 2). В POSIX (Linux в Docker и CI) воркер получает
SIGTERM и обязан корректно завершиться с кодом 0. В Windows SIGTERM — это ``TerminateProcess``
только главного процесса: TaskIQ слушает лишь SIGINT/SIGTERM, а его дочерний процесс
(``multiprocessing.spawn``) оставался сиротой, держал вывод, и тест (а с ним ``check.py``)
зависал навсегда. Поэтому в Windows останавливается всё дерево процессов воркера по PID,
и тест проверяет остальное поведение; ожидание вывода везде ограничено по времени.
"""

import asyncio
import contextlib
import importlib
import os
import signal
import sys
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
IS_WINDOWS = sys.platform == "win32"


async def _kill_tree(process: asyncio.subprocess.Process) -> None:
    """Принудительно остановить воркер вместе с дочерними процессами (только его PID)."""
    if IS_WINDOWS:
        killer = await asyncio.create_subprocess_exec(
            "taskkill",
            "/PID",
            str(process.pid),
            "/T",
            "/F",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await killer.wait()
    else:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)


async def _stop_worker(process: asyncio.subprocess.Process) -> bytes:
    """Остановить воркер штатным для ОС способом и вернуть остаток вывода.

    Raises:
        AssertionError: Воркер не завершился вовремя (дерево процессов уже остановлено).
    """
    if IS_WINDOWS:
        await _kill_tree(process)
    else:
        process.send_signal(signal.SIGTERM)
    try:
        rest, _ = await asyncio.wait_for(process.communicate(), WAIT_SECONDS)
    except TimeoutError:
        await _kill_tree(process)
        rest, _ = await asyncio.wait_for(process.communicate(), WAIT_SECONDS)
        pytest.fail(f"Воркер не завершился вовремя: {rest.decode()[-500:]}")
    return rest


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


async def test_worker_process_runs_heartbeat_and_stops_on_sigterm(
    redis_url: str, migrated_postgres_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    server, hits, arrived = await hc_server()
    env = {
        **os.environ,
        "APP_ENV": "local",
        "DATABASE_URL": migrated_postgres_url,
        "REDIS_URL": redis_url,
        "DEFAULT_TIMEZONE": "UTC",
        "SESSION_SECRET": "",
        "HEALTHCHECK_URL": str(server.make_url("/ping/runtime-check")),
        "SENTRY_DSN": "",
        # Журнал воркера по-русски: без этого в Windows он идёт в кодировке консоли (cp1251)
        "PYTHONIOENCODING": "utf-8",
    }
    from src.core import config as config_module  # noqa: PLC0415

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
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        # В POSIX своя группа процессов: при сбое её можно остановить целиком (killpg).
        start_new_session=not IS_WINDOWS,
    )
    seen: list[str] = []

    async def wait_until_listening() -> None:
        assert process.stdout is not None
        async for raw in process.stdout:
            seen.append(raw.decode())
            if "Listening started" in seen[-1]:
                return

    try:
        await asyncio.wait_for(wait_until_listening(), WAIT_SECONDS)
        # воркер простаивает дольше таймаута чтения по умолчанию и обязан остаться живым
        await asyncio.sleep(IDLE_SECONDS)
        for name, value in env.items():
            monkeypatch.setenv(name, value)
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
        try:
            rest = await _stop_worker(process)
        finally:
            await server.close()
            config_module.get_settings.cache_clear()
    output = "".join(seen) + rest.decode()
    if not IS_WINDOWS:
        # Корректное завершение по SIGTERM — поведение POSIX (прод и CI); в Windows сигнала нет.
        assert process.returncode == 0, output[-800:]
    assert process.returncode is not None
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
