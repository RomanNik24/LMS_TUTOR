"""Команда ``/today`` и кнопки «Расписание» / «Сегодня» (T3.08, docs/05 §3.6).

Ученику — уроки на ближайшие 24 часа, каждый отдельным сообщением с кнопками «Телемост» и
«Доска». Персоналу — компактная сводка дня. Время показывается в часовом поясе получателя.
"""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from src.bot import keyboards
from src.core import texts
from src.core.current_user import CurrentUser
from src.core.enums import LessonStatus, UserRole
from src.core.timeutils import to_local
from src.schemas.schedule import LessonItem, StudentLessonItem
from src.services.schedule import ScheduleService


def _student_text(item: StudentLessonItem, timezone: str) -> str:
    start = to_local(item.start_at, timezone)
    end = to_local(item.end_at, timezone)
    lines = [texts.lesson_when(start, end), texts.subject_name(item.subject_code)]
    if item.topic:
        lines.append(item.topic)
    return "\n".join(lines)


def _staff_line(item: LessonItem, timezone: str) -> str:
    start = to_local(item.start_at, timezone)
    names = ", ".join(p.display_name for p in item.participants)
    line = f"{start:%H:%M} {texts.subject_name(item.subject_code)}: {names}"
    if item.status == LessonStatus.COMPLETED:
        line += f" ({texts.BOT_LESSON_DONE_MARK})"
    elif item.status == LessonStatus.CANCELLED:
        line += f" ({texts.BOT_LESSON_CANCELLED_MARK})"
    return line


async def today(message: Message, session: AsyncSession, current_user: CurrentUser | None) -> None:
    """Расписание на сегодня: ученику — 24 часа вперёд, персоналу — сводка дня."""
    if current_user is None:
        await message.answer(texts.BOT_GUEST_GREETING)
        return
    service = ScheduleService(session)
    if current_user.role == UserRole.STUDENT:
        lessons = await service.student_upcoming(current_user)
        if not lessons:
            await message.answer(texts.BOT_STUDENT_NO_LESSONS)
            return
        for lesson in lessons:
            await message.answer(
                _student_text(lesson, current_user.timezone),
                reply_markup=keyboards.lesson_links(lesson.video_url, lesson.board_url),
            )
        return
    day, items = await service.staff_today(current_user)
    if not items:
        await message.answer(texts.BOT_STAFF_NO_LESSONS)
        return
    header = texts.BOT_STAFF_TODAY_HEADER.format(date=texts.short_date(day))
    body = "\n".join(_staff_line(item, current_user.timezone) for item in items)
    await message.answer(f"{header}\n{body}")


def create_router() -> Router:
    """Создать роутер (новый на каждый ``Dispatcher``)."""
    router = Router(name="schedule")
    router.message.register(today, Command("today"))
    router.message.register(today, F.text.in_({texts.BOT_BUTTON_SCHEDULE, texts.BOT_BUTTON_TODAY}))
    return router
