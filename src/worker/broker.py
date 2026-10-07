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

from src.bot.client import build_bot
from src.core.config import get_settings
from src.core.constants import REDIS_CONNECT_TIMEOUT_SECONDS, WORKER_QUEUE_NAME_DEFAULT
from src.core.sentry import init_sentry
from src.db.session import create_engine, create_session_factory

logger = logging.getLogger(__name__)

STATE_SETTINGS = "settings"
STATE_ENGINE = "engine"
STATE_SESSION_FACTORY = "session_factory"
STATE_BOT = "bot"


def create_broker(redis_url: str, queue_name: str = WORKER_QUEUE_NAME_DEFAULT) -> ListQueueBroker:
    """Создать брокер очереди на Redis.

    Воркер ждёт задачи блокирующим ``BRPOP`` без таймаута. Клиент redis-py 8 по умолчанию
    ставит ``socket_timeout`` в 5 секунд, поэтому на простое чтение обрывалось
    ``TimeoutError``, которого брокер не ловит, и воркер перезапускался каждые ~12 секунд.
    Для брокера таймаут чтения отключён (``None``); обрыв соединения ловит TCP keepalive,
    а подключение по-прежнему ограничено ``socket_connect_timeout``.

    Args:
        redis_url: Адрес Redis (``REDIS_URL``).
        queue_name: Имя очереди (``WORKER_QUEUE_NAME``): все процессы стенда берут её из настроек.
    """
    return ListQueueBroker(
        redis_url,
        queue_name=queue_name,
        socket_timeout=None,
        socket_connect_timeout=REDIS_CONNECT_TIMEOUT_SECONDS,
        socket_keepalive=True,
    )


_settings = get_settings()
broker = create_broker(_settings.redis_url, _settings.worker_queue_name)
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
    # Бот нужен только для отправки уведомлений; без BOT_TOKEN отправка пропускается.
    state[STATE_BOT] = build_bot(settings)
    logger.info("Воркер запущен")


@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def close_resources(state: TaskiqState) -> None:
    """Закрыть подключение к БД при остановке воркера."""
    bot = state.get(STATE_BOT)
    if bot is not None:
        await bot.session.close()
    engine = state.get(STATE_ENGINE)
    if engine is not None:
        await engine.dispose()
    logger.info("Воркер остановлен")
