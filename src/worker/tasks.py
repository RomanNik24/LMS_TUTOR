"""Задачи воркера (T5.04). Периодические задачи этапа 5 добавляются в T5.05.

Расписание задаётся меткой ``schedule`` (cron, UTC) и читается планировщиком.
"""

from typing import Annotated

from taskiq import Context, TaskiqDepends

from src.core.config import Settings
from src.core.constants import HEARTBEAT_CRON
from src.worker.broker import STATE_SETTINGS, broker
from src.worker.heartbeat import ping


@broker.task(task_name="heartbeat", schedule=[{"cron": HEARTBEAT_CRON}])
async def heartbeat(context: Annotated[Context, TaskiqDepends()]) -> bool:
    """Пинг мониторинга (Healthchecks): воркер жив и принимает задачи.

    Returns:
        ``True``, если пинг отправлен; ``False``, если адрес не задан или пинг не прошёл.
    """
    settings: Settings = context.state[STATE_SETTINGS]
    return await ping(settings.healthcheck_url)
