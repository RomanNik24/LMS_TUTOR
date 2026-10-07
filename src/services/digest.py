"""``DigestService``: утренняя сводка персоналу (T5.07, docs/05 §6.3).

Задача запускается каждый час и выбирает сотрудников, у которых по их часовому поясу сейчас
08:00–08:59. Каждому ставится одно уведомление ``morning_digest`` с ключом
``morning_digest:{user_id}:{yyyy-mm-dd}`` (дата — местная), поэтому повторный запуск в тот же день
дубля не создаёт. Если событий для сводки нет, сообщение не отправляется.

В сводке: уроки сегодня; ДЗ на проверку (число и пять самых давних); несданное к сегодняшним
урокам; уроки без отметки за прошлые дни; дедлайны ближайших 24 часов; для владельца — сумма,
заработанная в этом месяце (оплачиваемые занятия по зафиксированным ценам).
"""

from datetime import date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.core import texts
from src.core.constants import (
    DIGEST_LESSON_LINES,
    DIGEST_LOCAL_HOUR,
    DIGEST_TOP_ITEMS,
    UNMARKED_LESSON_LOOKBACK_DAYS,
)
from src.core.enums import NotificationType, UserRole
from src.core.timeutils import day_bounds_utc, local_date_of, to_local, utcnow
from src.db.models import User
from src.repositories.digest import DigestAssignment, DigestRepository
from src.repositories.homework import HomeworkAssignmentRepository
from src.repositories.reminders import ReminderRepository
from src.repositories.users import UserRepository
from src.services.notifications import NotificationService


def _more(total: int, shown: int) -> list[str]:
    return [texts.DIGEST_MORE.format(count=total - shown)] if total > shown else []


class DigestService:
    """Собирает и ставит в очередь утренние сводки."""

    def __init__(self, session: AsyncSession) -> None:
        """Создать сервис.

        Args:
            session: Сессия БД на текущую единицу работы.
        """
        self._session = session
        self._users = UserRepository(session)
        self._digest = DigestRepository(session)
        self._reminders = ReminderRepository(session)
        self._assignments = HomeworkAssignmentRepository(session)
        self._queue = NotificationService(session)

    async def send_morning_digests(self, now: datetime | None = None) -> int:
        """Поставить сводки сотрудникам, у которых сейчас 08:xx по местному времени.

        Returns:
            Сколько сводок поставлено в очередь.
        """
        moment = now or utcnow()
        created = 0
        for staff in await self._users.list_staff(include_archived=False):
            if staff.telegram_id is None:
                continue
            if to_local(moment, staff.timezone).hour != DIGEST_LOCAL_HOUR:
                continue
            lines = await self._lines_for(staff, moment)
            if not lines:
                continue
            day = local_date_of(moment, staff.timezone)
            added = await self._queue.enqueue(
                staff.id,
                NotificationType.MORNING_DIGEST,
                {"lines": lines},
                f"morning_digest:{staff.id}:{day.isoformat()}",
                scheduled_for=moment,
            )
            created += int(added)
        await self._session.commit()
        return created

    async def _lines_for(self, staff: User, now: datetime) -> list[str]:
        zone = staff.timezone
        today = local_date_of(now, zone)
        day_start, day_end = day_bounds_utc(today, zone)
        blocks: list[list[str]] = [
            await self._lessons_block(zone, day_start, day_end),
            await self._review_block(),
            await self._unsubmitted_block(zone, day_start, day_end),
            await self._unmarked_block(zone, now, day_start),
            await self._deadlines_block(zone, now),
        ]
        lines: list[str] = []
        for block in blocks:
            if block:
                lines += ["", *block]
        if not lines:
            return []
        title = texts.DIGEST_TITLE.format(date=texts.short_date(today))
        result = [title, *lines]
        if staff.role == UserRole.OWNER:
            result += ["", await self._earned_line(zone, today)]
        return result

    # ------------------------------------------------------------------ блоки

    async def _lessons_block(self, zone: str, start: datetime, end: datetime) -> list[str]:
        lessons = await self._digest.lessons_between(start, end)
        if not lessons:
            return []
        lines = [texts.DIGEST_LESSONS.format(count=len(lessons))]
        for lesson in lessons[:DIGEST_LESSON_LINES]:
            lines.append(
                texts.DIGEST_LESSON_LINE.format(
                    time=f"{to_local(lesson.start_at, zone):%H:%M}",
                    subject=texts.subject_name(lesson.subject_code),
                    students=", ".join(lesson.students),
                )
            )
        return lines + _more(len(lessons), DIGEST_LESSON_LINES)

    async def _review_block(self) -> list[str]:
        rows, total = await self._assignments.review_queue(limit=DIGEST_TOP_ITEMS, offset=0)
        if total == 0:
            return []
        lines = [texts.DIGEST_REVIEW.format(count=total)]
        for _assignment, homework, _code, student in rows:
            lines.append(texts.DIGEST_REVIEW_LINE.format(student=student, title=homework.title))
        return lines + _more(total, len(rows))

    async def _unsubmitted_block(self, zone: str, start: datetime, end: datetime) -> list[str]:
        rows = await self._digest.unsubmitted_for_lessons(start, end)
        return self._assignment_block(
            rows, texts.DIGEST_UNSUBMITTED, texts.DIGEST_UNSUBMITTED_LINE, zone
        )

    async def _deadlines_block(self, zone: str, now: datetime) -> list[str]:
        rows = await self._digest.deadlines_between(now, now + timedelta(hours=24))
        return self._assignment_block(
            rows, texts.DIGEST_DEADLINES, texts.DIGEST_DEADLINE_LINE, zone
        )

    @staticmethod
    def _assignment_block(
        rows: list[DigestAssignment], header: str, line: str, zone: str
    ) -> list[str]:
        if not rows:
            return []
        lines = [header.format(count=len(rows))]
        for row in rows[:DIGEST_TOP_ITEMS]:
            lines.append(
                line.format(
                    student=row.student_name,
                    title=row.title,
                    due=texts.local_when(to_local(row.due_at, zone)),
                )
            )
        return lines + _more(len(rows), DIGEST_TOP_ITEMS)

    async def _unmarked_block(self, zone: str, now: datetime, day_start: datetime) -> list[str]:
        past = await self._reminders.unmarked_lessons(
            now - timedelta(days=UNMARKED_LESSON_LOOKBACK_DAYS), day_start
        )
        if not past:
            return []
        lines = [texts.DIGEST_UNMARKED.format(count=len(past))]
        for lesson in past[:DIGEST_TOP_ITEMS]:
            lines.append(
                texts.DIGEST_UNMARKED_LINE.format(
                    when=texts.local_when(to_local(lesson.start_at, zone)),
                    subject=texts.subject_name(lesson.subject_code),
                )
            )
        return lines + _more(len(past), DIGEST_TOP_ITEMS)

    async def _earned_line(self, zone: str, today: date) -> str:
        first = today.replace(day=1)
        following = (first + timedelta(days=32)).replace(day=1)
        start, _ = day_bounds_utc(first, zone)
        end, _ = day_bounds_utc(following, zone)
        amount = await self._digest.earned_between(start, end)
        return texts.DIGEST_EARNED.format(amount=texts.money(amount))
