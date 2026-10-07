"""Брокер, воркер и планировщик TaskIQ (T5.04, docs/03 §9, docs/10 §3).

Запуск (см. ``docker-compose.yml``):

- воркер: ``taskiq worker src.worker.broker:broker src.worker.tasks --workers 1``;
- планировщик: ``taskiq scheduler src.worker.broker:scheduler src.worker.tasks``.

Планировщик должен работать СТРОГО в одном экземпляре: два планировщика поставят каждую
задачу дважды. Воркеров может быть несколько: задачи идемпотентны, а доставка уведомлений
защищена ``dedup_key`` и блокировкой ``SKIP LOCKED``.

Ресурсы воркера (движок БД, настройки) создаются при старте и закрываются при остановке:
процесс завершается корректно по SIGTERM, не оставляя открытых соединений.
"""

import logging

from taskiq import TaskiqEvents, TaskiqScheduler, TaskiqState
from taskiq.schedule_sources import LabelScheduleSource
from taskiq_redis import ListQueueBroker

from src.core.config import get_settings
from src.core.sentry import init_sentry
from src.db.session import create_engine, create_session_factory

logger = logging.getLogger(__name__)

STATE_SETTINGS = "settings"
STATE_ENGINE = "engine"
STATE_SESSION_FACTORY = "session_factory"


def create_broker(redis_url: str) -> ListQueueBroker:
    """Создать брокер очереди на Redis.

    Args:
        redis_url: Адрес Redis (``REDIS_URL``).
    """
    return ListQueueBroker(redis_url)


broker = create_broker(get_settings().redis_url)
scheduler = TaskiqScheduler(broker=broker, sources=[LabelScheduleSource(broker)])


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def open_resources(state: TaskiqState) -> None:
    """Подготовить настройки, Sentry и подключение к БД при старте воркера."""
    settings = get_settings()
    init_sentry(settings)
    engine = create_engine(settings.database_url)
    state[STATE_SETTINGS] = settings
    state[STATE_ENGINE] = engine
    state[STATE_SESSION_FACTORY] = create_session_factory(engine)
    logger.info("Воркер запущен")


@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def close_resources(state: TaskiqState) -> None:
    """Закрыть подключение к БД при остановке воркера."""
    engine = state.get(STATE_ENGINE)
    if engine is not None:
        await engine.dispose()
    logger.info("Воркер остановлен")
