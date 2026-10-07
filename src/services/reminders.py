"""``ReminderService``: генераторы напоминаний (T5.05, docs/03 §9, docs/05 §6).

Каждый метод — одна транзакция: находит, кому и о чём напомнить, кладёт записи в очередь
уведомлений и фиксирует. Повторный запуск (в том числе после перезапуска воркера) дублей не
создаёт: у каждой записи свой ``dedup_key`` по шаблонам docs/05 §6.4.

- напоминание об уроке за 30 минут: ``lesson_reminder:{lesson_id}:{student_id}:{start_epoch}``;
  срочное; перенос урока меняет ``start_epoch``, поэтому создаётся новое, а старое диспетчер
  отбросит как устаревшее;
- напоминание о дедлайне за 24 часа: ``homework_deadline:{assignment_id}:{due_epoch}``; создаётся
  только если выдача существовала уже за 24 часа до срока (иначе «завтра» было бы неправдой);
  перенос срока меняет ``due_epoch`` и даёт новое напоминание;
- уроки без отметки: ``lesson_unmarked:{lesson_id}:{teacher_id}``, через час после окончания.
"""

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.core import texts
from src.core.constants import (
    HOMEWORK_REMINDER_HOURS,
    HOMEWORK_REMINDER_LOOKAHEAD_MINUTES,
    LESSON_REMINDER_LATE_TOLERANCE_MINUTES,
    LESSON_REMINDER_LOOKAHEAD_MINUTES,
    LESSON_REMINDER_MINUTES,
    UNMARKED_LESSON_AFTER_MINUTES,
    UNMARKED_LESSON_LOOKBACK_DAYS,
)
from src.core.enums import NotificationType
from src.core.timeutils import utcnow
from src.repositories.reminders import ReminderRepository
from src.services.notifications import NotificationService


def _epoch(moment: datetime) -> int:
    return int(moment.timestamp())


class ReminderService:
    """Создаёт напоминания по расписанию воркера."""

    def __init__(self, session: AsyncSession) -> None:
        """Создать сервис.

        Args:
            session: Сессия БД на текущую единицу работы.
        """
        self._session = session
        self._targets = ReminderRepository(session)
        self._queue = NotificationService(session)

    async def generate_lesson_reminders(self, now: datetime | None = None) -> int:
        """Напомнить ученикам об уроках, до которых остаётся около 30 минут.

        Запись ставится заранее на точный момент «начало минус 30 минут»; если воркер простоял
        и момент уже прошёл (не больше чем на 5 минут), напоминание уходит сразу.

        Returns:
            Сколько напоминаний создано (без учёта уже существующих).
        """
        moment = now or utcnow()
        first = moment + timedelta(minutes=LESSON_REMINDER_MINUTES)
        window_from = first - timedelta(minutes=LESSON_REMINDER_LATE_TOLERANCE_MINUTES)
        window_to = moment + timedelta(minutes=LESSON_REMINDER_LOOKAHEAD_MINUTES)
        created = 0
        for target in await self._targets.lessons_starting(window_from, window_to):
            epoch = _epoch(target.start_at)
            added = await self._queue.enqueue(
                target.student_id,
                NotificationType.LESSON_REMINDER,
                {
                    "lesson_id": target.lesson_id,
                    "start_epoch": epoch,
                    "subject": texts.subject_name(target.subject_code),
                    "video_url": target.video_url,
                    "board_url": target.board_url,
                },
                f"lesson_reminder:{target.lesson_id}:{target.student_id}:{epoch}",
                scheduled_for=target.start_at - timedelta(minutes=LESSON_REMINDER_MINUTES),
                is_urgent=True,
            )
            created += int(added)
        await self._session.commit()
        return created

    async def generate_homework_reminders(self, now: datetime | None = None) -> int:
        """Напомнить ученикам о дедлайне ДЗ за сутки.

        Returns:
            Сколько напоминаний создано.
        """
        moment = now or utcnow()
        before = timedelta(hours=HOMEWORK_REMINDER_HOURS)
        due_to = moment + before + timedelta(minutes=HOMEWORK_REMINDER_LOOKAHEAD_MINUTES)
        created = 0
        for target in await self._targets.deadlines_between(moment, due_to):
            remind_at = target.due_at - before
            if remind_at < target.created_at:
                continue  # выдано меньше чем за сутки до срока: «завтра» было бы неправдой
            epoch = _epoch(target.due_at)
            added = await self._queue.enqueue(
                target.student_id,
                NotificationType.HOMEWORK_DEADLINE,
                {"assignment_id": target.assignment_id, "due_epoch": epoch, "title": target.title},
                f"homework_deadline:{target.assignment_id}:{epoch}",
                scheduled_for=remind_at,
            )
            created += int(added)
        await self._session.commit()
        return created

    async def notify_unmarked_lessons(self, now: datetime | None = None) -> int:
        """Напомнить преподавателю об уроках без отметки (через час после окончания).

        Returns:
            Сколько уведомлений создано.
        """
        moment = now or utcnow()
        end_to = moment - timedelta(minutes=UNMARKED_LESSON_AFTER_MINUTES)
        end_from = moment - timedelta(days=UNMARKED_LESSON_LOOKBACK_DAYS)
        created = 0
        for lesson in await self._targets.unmarked_lessons(end_from, end_to):
            added = await self._queue.enqueue(
                lesson.teacher_id,
                NotificationType.LESSON_UNMARKED,
                {
                    "lesson_id": lesson.lesson_id,
                    "start_epoch": _epoch(lesson.start_at),
                    "subject": texts.subject_name(lesson.subject_code),
                },
                f"lesson_unmarked:{lesson.lesson_id}:{lesson.teacher_id}",
                scheduled_for=moment,
            )
            created += int(added)
        await self._session.commit()
        return created
