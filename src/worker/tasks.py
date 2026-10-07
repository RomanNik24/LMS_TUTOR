"""Задачи воркера и их расписание (T5.04–T5.05, docs/03 §9).

Расписание задаётся меткой ``schedule`` (cron, UTC) и читается планировщиком. Каждая задача
идемпотентна: повторный или одновременный запуск не создаёт дублей (``dedup_key``, блокировка
``SKIP LOCKED``, условные ``UPDATE``). Бизнес-логика живёт в сервисах, здесь только вызовы.
"""

import logging
from typing import Annotated

from sqlalchemy.ext.asyncio import AsyncSession
from taskiq import Context, TaskiqDepends

from src.bot.notifier import TelegramNotifier
from src.core.config import Settings
from src.core.constants import (
    CRON_EVERY_5_MINUTES,
    CRON_EVERY_15_MINUTES,
    CRON_EVERY_HOUR,
    CRON_EVERY_MINUTE,
    CRON_LESSON_GENERATION,
    CRON_LINKS_CLEANUP,
    HEARTBEAT_CRON,
)
from src.services.digest import DigestService
from src.services.expiry import ExpiryService
from src.services.maintenance import MaintenanceService
from src.services.notification_dispatch import NotificationDispatcher
from src.services.notification_render import NotificationRenderer
from src.services.reminders import ReminderService
from src.services.schedule import ScheduleService
from src.worker.broker import STATE_BOT, STATE_SETTINGS, broker
from src.worker.deps import get_session
from src.worker.heartbeat import ping

logger = logging.getLogger(__name__)

Ctx = Annotated[Context, TaskiqDepends()]
Session = Annotated[AsyncSession, TaskiqDepends(get_session)]


@broker.task(task_name="heartbeat", schedule=[{"cron": HEARTBEAT_CRON}])
async def heartbeat(context: Ctx) -> bool:
    """Пинг мониторинга (Healthchecks): воркер жив и принимает задачи.

    Returns:
        ``True``, если пинг отправлен; ``False``, если адрес не задан или пинг не прошёл.
    """
    settings: Settings = context.state[STATE_SETTINGS]
    return await ping(settings.healthcheck_url)


@broker.task(task_name="dispatch_due_notifications", schedule=[{"cron": CRON_EVERY_MINUTE}])
async def dispatch_due_notifications(context: Ctx, session: Session) -> int:
    """Отправить накопленные уведомления.

    Returns:
        Сколько уведомлений обработано; 0, если бот не настроен (нет ``BOT_TOKEN``).
    """
    bot = context.state[STATE_BOT]
    if bot is None:
        logger.warning("Уведомления не отправляются: BOT_TOKEN не задан")
        return 0
    settings: Settings = context.state[STATE_SETTINGS]
    dispatcher = NotificationDispatcher(
        session, TelegramNotifier(bot), NotificationRenderer(settings.public_base_url)
    )
    return (await dispatcher.dispatch_due()).total


@broker.task(task_name="generate_lesson_reminders", schedule=[{"cron": CRON_EVERY_MINUTE}])
async def generate_lesson_reminders(session: Session) -> int:
    """Поставить напоминания об уроках за 30 минут до начала."""
    return await ReminderService(session).generate_lesson_reminders()


@broker.task(task_name="generate_homework_reminders", schedule=[{"cron": CRON_EVERY_5_MINUTES}])
async def generate_homework_reminders(session: Session) -> int:
    """Поставить напоминания о дедлайнах ДЗ за 24 часа."""
    return await ReminderService(session).generate_homework_reminders()


@broker.task(task_name="expire_homework_assignments", schedule=[{"cron": CRON_EVERY_5_MINUTES}])
async def expire_homework_assignments(session: Session) -> int:
    """Перевести просроченные выдачи с исчерпанными переносами в ``expired``."""
    return (await ExpiryService(session).expire_due_assignments()).expired


@broker.task(task_name="notify_unmarked_lessons", schedule=[{"cron": CRON_EVERY_15_MINUTES}])
async def notify_unmarked_lessons(session: Session) -> int:
    """Напомнить об уроках без отметки через час после окончания."""
    return await ReminderService(session).notify_unmarked_lessons()


@broker.task(task_name="generate_scheduled_lessons", schedule=[{"cron": CRON_LESSON_GENERATION}])
async def generate_scheduled_lessons(context: Ctx, session: Session) -> int:
    """Дозаполнить уроки по шаблонам на горизонт (ежедневно в 03:00 UTC)."""
    settings: Settings = context.state[STATE_SETTINGS]
    result = await ScheduleService(session, settings.schedule_horizon_weeks).generate_lessons()
    return result.created


@broker.task(task_name="cleanup_tokens", schedule=[{"cron": CRON_LINKS_CLEANUP}])
async def cleanup_tokens(session: Session) -> int:
    """Удалить истёкшие приглашения и ссылки входа (ежедневно в 03:30 UTC)."""
    return await MaintenanceService(session).cleanup_tokens()


@broker.task(task_name="send_morning_digest", schedule=[{"cron": CRON_EVERY_HOUR}])
async def send_morning_digest(session: Session) -> int:
    """Поставить утреннюю сводку сотрудникам, у которых сейчас 08:00 по их часовому поясу."""
    return await DigestService(session).send_morning_digests()
