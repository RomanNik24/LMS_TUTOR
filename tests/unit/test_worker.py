"""Воркер и планировщик TaskIQ: брокер, heartbeat, compose (T5.04)."""

import importlib
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from aiohttp import web
from aiohttp.test_utils import TestServer
from src.core.config import Settings
from src.worker.heartbeat import ping
from taskiq import TaskiqState
from taskiq.schedule_sources import LabelScheduleSource
from taskiq_redis import ListQueueBroker

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def worker(app_settings_env: None):  # noqa: ANN201, ARG001
    """Модули воркера, загруженные заново под тестовым окружением."""
    from src.worker import broker as broker_module  # noqa: PLC0415
    from src.worker import tasks as tasks_module  # noqa: PLC0415

    importlib.reload(broker_module)
    importlib.reload(tasks_module)
    return SimpleNamespace(broker=broker_module, tasks=tasks_module)


def test_broker_is_redis_list_queue_and_scheduler_reads_task_labels(
    worker: SimpleNamespace,
) -> None:
    assert isinstance(worker.broker.broker, ListQueueBroker)
    scheduler = worker.broker.scheduler
    assert scheduler.broker is worker.broker.broker
    assert any(isinstance(source, LabelScheduleSource) for source in scheduler.sources)


def test_heartbeat_is_scheduled_every_five_minutes(worker: SimpleNamespace) -> None:
    task = worker.tasks.heartbeat
    assert task.task_name == "heartbeat"
    assert task.labels["schedule"] == [{"cron": "*/5 * * * *"}]


async def test_startup_opens_and_shutdown_closes_database(
    worker: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = worker.broker.create_engine
    disposed: list[bool] = []
    engines: list[object] = []

    class SpyEngine:
        """Настоящий движок с учётом вызова dispose."""

        def __init__(self, url: str) -> None:
            self.engine = real(url)
            engines.append(self.engine)

        def __getattr__(self, name: str) -> object:
            return getattr(self.engine, name)

        async def dispose(self) -> None:
            disposed.append(True)
            await self.engine.dispose()

    monkeypatch.setattr(worker.broker, "create_engine", SpyEngine)
    state = TaskiqState()
    await worker.broker.open_resources(state)
    assert isinstance(state["settings"], Settings)
    assert state["session_factory"] is not None
    assert disposed == []
    await worker.broker.close_resources(state)
    assert disposed == [True]


async def test_shutdown_without_startup_is_safe(worker: SimpleNamespace) -> None:
    await worker.broker.close_resources(TaskiqState())


async def test_heartbeat_task_pings_configured_url(
    worker: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []

    async def fake_ping(url: str) -> bool:
        seen.append(url)
        return True

    monkeypatch.setattr(worker.tasks, "ping", fake_ping)
    settings = SimpleNamespace(healthcheck_url="https://hc.example/abc")
    context = SimpleNamespace(state={"settings": settings})
    assert await worker.tasks.heartbeat.original_func(context) is True
    assert seen == ["https://hc.example/abc"]


# ---------------------------------------------------------------- ping


async def serve(status: int) -> tuple[TestServer, list[str]]:
    hits: list[str] = []

    async def handler(request: web.Request) -> web.Response:
        hits.append(request.path)
        return web.Response(status=status)

    app = web.Application()
    app.router.add_get("/ping/{key}", handler)
    server = TestServer(app)
    await server.start_server()
    return server, hits


async def test_ping_success_hits_url() -> None:
    server, hits = await serve(200)
    try:
        assert await ping(str(server.make_url("/ping/secret-id"))) is True
    finally:
        await server.close()
    assert hits == ["/ping/secret-id"]


async def test_ping_server_error_is_false_and_url_is_not_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    server, _ = await serve(500)
    try:
        with caplog.at_level(logging.WARNING):
            assert await ping(str(server.make_url("/ping/secret-id"))) is False
    finally:
        await server.close()
    assert "secret-id" not in caplog.text
    assert "500" in caplog.text


async def test_ping_empty_url_does_nothing() -> None:
    assert await ping("") is False


async def test_ping_connection_failure_does_not_raise(caplog: pytest.LogCaptureFixture) -> None:
    server, _ = await serve(200)
    url = str(server.make_url("/ping/secret-id"))
    await server.close()  # порт закрыт: соединение будет отклонено
    with caplog.at_level(logging.WARNING):
        assert await ping(url) is False
    assert "secret-id" not in caplog.text


# ---------------------------------------------------------------- compose


def compose() -> dict[str, object]:
    return yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))


def test_compose_has_exactly_one_scheduler_without_replicas() -> None:
    services = compose()["services"]
    assert isinstance(services, dict)
    schedulers = [
        name for name, body in services.items() if "scheduler" in str(body.get("command"))
    ]
    assert schedulers == ["scheduler"]
    scheduler = services["scheduler"]
    assert scheduler["profiles"] == ["dev", "full"]
    assert "deploy" not in scheduler  # replicas не задаются
    assert "ports" not in scheduler
    assert scheduler["command"][:2] == ["taskiq", "scheduler"]


def test_compose_worker_runs_taskiq_in_dev_and_full() -> None:
    services = compose()["services"]
    assert isinstance(services, dict)
    worker = services["worker"]
    assert worker["profiles"] == ["dev", "full"]
    assert worker["command"][:3] == ["taskiq", "worker", "src.worker.broker:broker"]
    assert "src.worker.tasks" in worker["command"]
    assert worker["environment"]["REDIS_URL"] == "redis://redis:6379/0"
    assert worker["healthcheck"] == {"disable": True}
    assert worker["stop_grace_period"] == "30s"
