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

from redis.asyncio.retry import Retry
from redis.backoff import ExponentialBackoff
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError
from taskiq import ScheduledTask, ScheduleSource, TaskiqEvents, TaskiqScheduler, TaskiqState
from taskiq.schedule_sources import LabelScheduleSource
from taskiq_redis import ListQueueBroker

from src.bot.client import build_bot
from src.core.config import get_settings
from src.core.constants import (
    REDIS_CONNECT_TIMEOUT_SECONDS,
    REDIS_HEALTH_CHECK_INTERVAL_SECONDS,
    REDIS_RETRY_ATTEMPTS,
    REDIS_RETRY_BACKOFF_CAP_SECONDS,
)
from src.core.sentry import init_sentry
from src.db.session import create_engine, create_session_factory

logger = logging.getLogger(__name__)

STATE_SETTINGS = "settings"
STATE_ENGINE = "engine"
STATE_SESSION_FACTORY = "session_factory"
STATE_BOT = "bot"


def create_broker(redis_url: str) -> ListQueueBroker:
    """Создать брокер очереди на Redis.

    Воркер ждёт задачи блокирующим ``BRPOP`` без таймаута. Клиент redis-py 8 по умолчанию
    ставит ``socket_timeout`` в 5 секунд, поэтому на простое чтение обрывалось
    ``TimeoutError``, которого брокер не ловит, и воркер перезапускался каждые ~12 секунд.
    Для брокера таймаут чтения отключён (``None``); обрыв соединения ловит TCP keepalive,
    а подключение по-прежнему ограничено ``socket_connect_timeout``.

    Соединения из пула переживают перезапуск Redis «мёртвыми»: без повтора первая команда через
    каждое такое соединение падала (``Connection lost``), и планировщик терял задачу. Соединения
    №4–5 пула нужны только на границе часа (5 отправок сразу), поэтому после перезапуска Redis
    пропадали именно часовые задачи (аудит 2026-10-08, п. 1). Поэтому включены проверка
    простаивающего соединения перед командой (``health_check_interval``) и повтор команды с
    переподключением при ``ConnectionError``/``TimeoutError``; заодно воркер переживает короткий
    обрыв без перезапуска процесса.

    Args:
        redis_url: Адрес Redis (``REDIS_URL``).
    """
    return ListQueueBroker(
        redis_url,
        socket_timeout=None,
        socket_connect_timeout=REDIS_CONNECT_TIMEOUT_SECONDS,
        socket_keepalive=True,
        health_check_interval=REDIS_HEALTH_CHECK_INTERVAL_SECONDS,
        retry=Retry(ExponentialBackoff(cap=REDIS_RETRY_BACKOFF_CAP_SECONDS), REDIS_RETRY_ATTEMPTS),
        retry_on_error=[RedisConnectionError, RedisTimeoutError],
    )


class LoggingScheduler(TaskiqScheduler):
    """Планировщик, который не теряет сбой отправки молча.

    TaskIQ пишет «Sending task …» до отправки и запускает её в отдельной задаче asyncio:
    исключение отправки всплывало только при сборке мусора («Task exception was never
    retrieved»), и по журналу казалось, что задача ушла. Здесь сбой сразу пишется в журнал
    уровня ERROR с именем задачи (и уходит в Sentry, если он включён).
    """

    async def on_ready(self, source: ScheduleSource, task: ScheduledTask) -> None:
        """Поставить задачу в очередь; сбой записать в журнал, а не терять молча."""
        try:
            await super().on_ready(source, task)
        except Exception:
            logger.exception("Задача %s не поставлена в очередь", task.task_name)


broker = create_broker(get_settings().redis_url)
scheduler = LoggingScheduler(broker=broker, sources=[LabelScheduleSource(broker)])


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
