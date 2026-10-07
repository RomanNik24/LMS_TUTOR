"""Воркер TaskIQ как процесс: задача доходит через Redis, SIGTERM завершает его (T5.04)."""

import asyncio
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
    }
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "taskiq",
        "worker",
        "src.worker.broker:broker",
        "src.worker.tasks",
        "--workers",
        "1",
        "--no-configure-logging",
        cwd=ROOT,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
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
        process.send_signal(signal.SIGTERM)
        try:
            output, _ = await asyncio.wait_for(process.communicate(), WAIT_SECONDS)
        except TimeoutError:
            process.kill()
            output, _ = await process.communicate()
            pytest.fail(f"Воркер не завершился по SIGTERM: {output.decode()[-500:]}")
        finally:
            await server.close()
            config_module.get_settings.cache_clear()
    assert process.returncode == 0, output.decode()[-800:]


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
