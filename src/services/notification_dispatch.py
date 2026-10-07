"""``NotificationDispatcher``: отправка накопленных уведомлений (T5.03, docs/03 §8, docs/05 §6.4).

Порядок для каждой записи ``pending`` с ``scheduled_for <= now``:
1. записи берутся пачкой под ``FOR UPDATE SKIP LOCKED``: второй диспетчер, запущенный
   параллельно, пропускает чужие строки, поэтому дублей нет;
2. получатель не найден или архивирован → ``skipped``;
3. актуальность: напоминание об уроке — урок ещё ``scheduled`` и начинается в то же время;
   напоминание о дедлайне — выдача ещё ``assigned``/``needs_revision`` с тем же сроком;
   иначе ``skipped``;
4. тихие часы 22:00–08:00 по поясу получателя: несрочное переносится на 08:00 (остаётся
   ``pending``), срочное идёт сразу;
5. текст собирает ``NotificationRenderer``; битые данные → ``failed``;
6. отправка и учёт результата — ``DeliveryService`` (блокировка бота, повторы 1/5/15 минут);
7. после каждой пачки — commit; между отправками небольшая пауза (~25 сообщений в секунду).
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import (
    NOTIFICATION_BATCH_SIZE,
    NOTIFICATION_MAX_BATCHES,
    NOTIFICATION_SEND_PAUSE_SECONDS,
    QUIET_HOURS_END,
    QUIET_HOURS_START,
)
from src.core.enums import AssignmentStatus, LessonStatus, NotificationStatus, NotificationType
from src.core.exceptions import AppError
from src.core.timeutils import local_date_of, local_to_utc, to_local, utcnow
from src.db.models import Notification
from src.repositories.homework import HomeworkAssignmentRepository
from src.repositories.lessons import LessonRepository
from src.repositories.notifications import NotificationRepository
from src.repositories.users import UserRepository
from src.services.delivery import DeliveryResult, DeliveryService
from src.services.notification_render import NotificationRenderer
from src.services.notifier import Notifier

logger = logging.getLogger(__name__)

REASON_NO_USER = "user_unavailable"
REASON_STALE = "stale"
ACTIVE_ASSIGNMENT = (AssignmentStatus.ASSIGNED, AssignmentStatus.NEEDS_REVISION)


@dataclass(slots=True)
class DispatchStats:
    """Итоги запуска диспетчера."""

    sent: int = 0
    skipped: int = 0
    deferred: int = 0
    retried: int = 0
    failed: int = 0

    @property
    def total(self) -> int:
        """Сколько записей обработано."""
        return self.sent + self.skipped + self.deferred + self.retried + self.failed


def quiet_hours_end(now: datetime, tz_name: str) -> datetime | None:
    """Момент окончания тихих часов (08:00 по поясу), если ``now`` внутри 22:00–08:00.

    Returns:
        UTC-время ближайших 08:00 или ``None``, если сейчас не тихие часы.
    """
    local = to_local(now, tz_name)
    today = local_date_of(now, tz_name)
    if local.hour >= QUIET_HOURS_START:
        return local_to_utc(today + timedelta(days=1), time(QUIET_HOURS_END), tz_name)
    if local.hour < QUIET_HOURS_END:
        return local_to_utc(today, time(QUIET_HOURS_END), tz_name)
    return None


class NotificationDispatcher:
    """Отправляет готовые к доставке уведомления."""

    def __init__(
        self,
        session: AsyncSession,
        notifier: Notifier,
        renderer: NotificationRenderer,
        *,
        pause_seconds: float = NOTIFICATION_SEND_PAUSE_SECONDS,
    ) -> None:
        """Создать диспетчер.

        Args:
            session: Сессия БД на этот запуск (транзакцией владеет диспетчер).
            notifier: Транспорт (Telegram или подмена).
            renderer: Сборщик текстов.
            pause_seconds: Пауза между отправками.
        """
        self._session = session
        self._notifications = NotificationRepository(session)
        self._users = UserRepository(session)
        self._lessons = LessonRepository(session)
        self._assignments = HomeworkAssignmentRepository(session)
        self._delivery = DeliveryService(notifier)
        self._renderer = renderer
        self._pause = pause_seconds

    async def dispatch_due(self, now: datetime | None = None) -> DispatchStats:
        """Отправить всё, что пора; вернуть счётчики.

        Пачки идут одна за другой, пока есть готовые записи (но не больше
        ``NOTIFICATION_MAX_BATCHES`` за запуск). Каждая пачка фиксируется отдельно.
        """
        moment = now or utcnow()
        stats = DispatchStats()
        for _ in range(NOTIFICATION_MAX_BATCHES):
            rows = await self._notifications.claim_due(moment, NOTIFICATION_BATCH_SIZE)
            if not rows:
                await self._session.rollback()
                break
            for index, row in enumerate(rows):
                if index > 0 and self._pause > 0:
                    await asyncio.sleep(self._pause)
                self._count(stats, await self._process(row, moment))
            await self._session.commit()
        return stats

    # ------------------------------------------------------------------ внутреннее

    @staticmethod
    def _count(stats: DispatchStats, outcome: str) -> None:
        match outcome:
            case DeliveryResult.SENT:
                stats.sent += 1
            case DeliveryResult.RETRY:
                stats.retried += 1
            case DeliveryResult.FAILED:
                stats.failed += 1
            case "deferred":
                stats.deferred += 1
            case _:
                stats.skipped += 1

    async def _process(self, row: Notification, now: datetime) -> str:
        user = await self._users.get_by_id(row.user_id)
        if user is None or not user.is_active:
            return self._close(row, NotificationStatus.SKIPPED, now, REASON_NO_USER)
        if not await self._is_actual(row):
            return self._close(row, NotificationStatus.SKIPPED, now, REASON_STALE)
        if not row.is_urgent:
            resume = quiet_hours_end(now, user.timezone)
            if resume is not None:
                row.scheduled_for = resume
                row.updated_at = now
                return "deferred"
        try:
            message = self._renderer.render(row, user)
        except AppError as error:
            logger.error("Уведомление %s не собрано: %s", row.id, error.code)
            return self._close(row, NotificationStatus.FAILED, now, error.code)
        return await self._delivery.deliver(row, user, message, now=now)

    @staticmethod
    def _close(row: Notification, status: NotificationStatus, now: datetime, reason: str) -> str:
        row.status = status
        row.last_error = reason
        row.updated_at = now
        return DeliveryResult.FAILED if status == NotificationStatus.FAILED else "skipped"

    async def _is_actual(self, row: Notification) -> bool:
        """Не устарело ли уведомление к моменту отправки (отмена, перенос, сдача)."""
        data = row.payload
        match row.type:
            case NotificationType.LESSON_REMINDER:
                lesson_id, epoch = data.get("lesson_id"), data.get("start_epoch")
                if not isinstance(lesson_id, int) or not isinstance(epoch, int):
                    return False
                lesson = await self._lessons.get_by_id(lesson_id)
                return (
                    lesson is not None
                    and lesson.status == LessonStatus.SCHEDULED
                    and int(lesson.start_at.astimezone(UTC).timestamp()) == epoch
                )
            case NotificationType.HOMEWORK_DEADLINE:
                assignment_id, epoch = data.get("assignment_id"), data.get("due_epoch")
                if not isinstance(assignment_id, int) or not isinstance(epoch, int):
                    return False
                assignment = await self._assignments.get_by_id(assignment_id)
                return (
                    assignment is not None
                    and assignment.status in ACTIVE_ASSIGNMENT
                    and int(assignment.due_at.astimezone(UTC).timestamp()) == epoch
                )
            case _:
                return True
