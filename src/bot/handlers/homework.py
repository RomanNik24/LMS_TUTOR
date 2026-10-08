"""Команда ``/hw`` и кнопки «Мои ДЗ» / «На проверку» (docs/05 §2, §3.6, §5.1).

Ученику — активные ДЗ со сроками, каждое отдельным сообщением с кнопкой «Открыть в приложении»
(deep link на карточку ДЗ). Персоналу — очередь проверки: число работ и самые давние.
Время показывается в часовом поясе получателя. Данные — из ``AssignmentQueryService``.
"""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession
from src.bot import keyboards
from src.core import texts
from src.core.config import Settings
from src.core.constants import BOT_HOMEWORK_LIST_LIMIT, DIGEST_TOP_ITEMS
from src.core.current_user import CurrentUser
from src.core.enums import UserRole
from src.core.timeutils import to_local
from src.schemas.homework_views import (
    AdminAssignmentItem,
    StudentAssignmentItem,
    StudentHomeworkFilter,
)
from src.services.assignments import AssignmentQueryService


def _student_text(item: StudentAssignmentItem, timezone: str) -> str:
    due = to_local(item.due_at, timezone)
    lines = [f"«{item.title}»", texts.BOT_HW_DUE.format(when=texts.local_when(due))]
    if item.is_overdue:
        lines.append(texts.BOT_HW_OVERDUE)
    return "\n".join(lines)


def _queue_line(item: AdminAssignmentItem, timezone: str) -> str:
    line = f"«{item.title}» — {item.student_name}"
    if item.submitted_at is not None:
        line += f", {texts.local_when(to_local(item.submitted_at, timezone))}"
    return line


async def homework(
    message: Message, session: AsyncSession, settings: Settings, current_user: CurrentUser | None
) -> None:
    """Ученику — активные ДЗ, персоналу — очередь проверки."""
    if current_user is None:
        await message.answer(texts.BOT_GUEST_GREETING)
        return
    service = AssignmentQueryService(session)
    if current_user.role == UserRole.STUDENT:
        page = await service.list_student(
            current_user, StudentHomeworkFilter.ACTIVE, limit=BOT_HOMEWORK_LIST_LIMIT
        )
        if not page.items:
            await message.answer(texts.BOT_HW_STUDENT_EMPTY)
            return
        for item in page.items:
            await message.answer(
                _student_text(item, current_user.timezone),
                reply_markup=keyboards.homework_button(
                    settings.public_base_url, item.assignment_id
                ),
            )
        if page.total > len(page.items):
            await message.answer(texts.BOT_HW_MORE.format(count=page.total - len(page.items)))
        return
    queue = await service.review_queue(current_user, limit=DIGEST_TOP_ITEMS)
    if not queue.items:
        await message.answer(texts.BOT_HW_QUEUE_EMPTY)
        return
    lines = [texts.BOT_HW_QUEUE_HEADER.format(count=queue.total)]
    lines += [_queue_line(item, current_user.timezone) for item in queue.items]
    if queue.total > len(queue.items):
        lines.append(texts.BOT_HW_QUEUE_MORE.format(count=queue.total - len(queue.items)))
    await message.answer(
        "\n".join(lines),
        reply_markup=keyboards.staff_review_buttons(
            settings.public_base_url,
            [(item.assignment_id, f"{item.student_name}: {item.title}") for item in queue.items],
            current_user.role,
        ),
    )


def create_router() -> Router:
    """Создать роутер (новый на каждый ``Dispatcher``)."""
    router = Router(name="homework")
    router.message.register(homework, Command("hw"))
    router.message.register(
        homework, F.text.in_({texts.BOT_BUTTON_HOMEWORK, texts.BOT_BUTTON_REVIEW})
    )
    return router
