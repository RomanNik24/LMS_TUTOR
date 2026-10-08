"""Команда ``/today`` и кнопки «Расписание» / «Сегодня» (T3.08, T7.03, docs/05 §3.6).

Ученику — уроки на ближайшие 24 часа, каждый отдельным сообщением с кнопками «Телемост» и
«Доска». Персоналу — сводка дня из ``DashboardService``: уроки и блоки «на проверку», «не сдано»,
«без отметки», «дедлайны»; денег в ней нет. Время показывается в часовом поясе получателя.
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
from src.schemas.dashboard import DashboardAssignmentsBlock, DashboardLesson, DashboardStaff
from src.schemas.schedule import StudentLessonItem
from src.services.dashboard import DashboardService
from src.services.schedule import ScheduleService

BLOCK_SEPARATOR = "\n\n"


def _student_text(item: StudentLessonItem, timezone: str) -> str:
    start = to_local(item.start_at, timezone)
    end = to_local(item.end_at, timezone)
    lines = [texts.lesson_when(start, end), texts.subject_name(item.subject_code)]
    if item.topic:
        lines.append(item.topic)
    return "\n".join(lines)


def _staff_line(item: DashboardLesson, timezone: str) -> str:
    start = to_local(item.start_at, timezone)
    names = ", ".join(item.student_names)
    line = f"{start:%H:%M} {texts.subject_name(item.subject_code)}: {names}"
    if item.status == LessonStatus.COMPLETED:
        line += f" ({texts.BOT_LESSON_DONE_MARK})"
    elif item.status == LessonStatus.CANCELLED:
        line += f" ({texts.BOT_LESSON_CANCELLED_MARK})"
    return line


def _assignment_lines(
    block: DashboardAssignmentsBlock, header: str, line: str, zone: str
) -> list[str]:
    if block.total == 0:
        return []
    lines = [header.format(count=block.total)]
    for item in block.items:
        due = texts.local_when(to_local(item.due_at, zone))
        lines.append(line.format(student=item.student_name, title=item.title, due=due))
    if block.total > len(block.items):
        lines.append(texts.DIGEST_MORE.format(count=block.total - len(block.items)))
    return lines


def _staff_text(dashboard: DashboardStaff) -> str | None:
    """Текст сводки дня или ``None``, если день пуст."""
    zone = dashboard.timezone
    header = texts.BOT_STAFF_TODAY_HEADER.format(date=texts.short_date(dashboard.date))
    blocks: list[list[str]] = [
        [header, *(_staff_line(item, zone) for item in dashboard.lessons.items)],
        [texts.DIGEST_REVIEW.format(count=dashboard.review_queue.total)]
        if dashboard.review_queue.total
        else [],
        _assignment_lines(
            dashboard.unsubmitted, texts.DIGEST_UNSUBMITTED, texts.DIGEST_UNSUBMITTED_LINE, zone
        ),
        [texts.DIGEST_UNMARKED.format(count=dashboard.unmarked_lessons.total)]
        if dashboard.unmarked_lessons.total
        else [],
        _assignment_lines(
            dashboard.deadlines, texts.DIGEST_DEADLINES, texts.DIGEST_DEADLINE_LINE, zone
        ),
    ]
    if not any(blocks[1:]) and not dashboard.lessons.items:
        return None
    return BLOCK_SEPARATOR.join("\n".join(block) for block in blocks if block)


async def today(message: Message, session: AsyncSession, current_user: CurrentUser | None) -> None:
    """Расписание на сегодня: ученику — 24 часа вперёд, персоналу — сводка дня."""
    if current_user is None:
        await message.answer(texts.BOT_GUEST_GREETING)
        return
    if current_user.role == UserRole.STUDENT:
        lessons = await ScheduleService(session).student_upcoming(current_user)
        if not lessons:
            await message.answer(texts.BOT_STUDENT_NO_LESSONS)
            return
        for lesson in lessons:
            await message.answer(
                _student_text(lesson, current_user.timezone),
                reply_markup=keyboards.lesson_links(lesson.video_url, lesson.board_url),
            )
        return
    dashboard = await DashboardService(session).get_today_dashboard(current_user)
    await message.answer(_staff_text(dashboard) or texts.BOT_STAFF_NO_LESSONS)


def create_router() -> Router:
    """Создать роутер (новый на каждый ``Dispatcher``)."""
    router = Router(name="schedule")
    router.message.register(today, Command("today"))
    router.message.register(today, F.text.in_({texts.BOT_BUTTON_SCHEDULE, texts.BOT_BUTTON_TODAY}))
    return router
