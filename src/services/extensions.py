"""``ExtensionService``: перенос дедлайна выдачи (T4.09, docs/01 US-05, docs/04 §5.4).

Правила:
- переносит только персонал; не более двух раз на выдачу, третья попытка — 400
  ``homework_extension_limit``;
- переносить можно только ``assigned`` и ``needs_revision``: сданную, оценённую и истёкшую —
  нельзя (``assignment_not_extendable``);
- без даты новый срок — начало ближайшего запланированного урока ученика после текущего срока
  (а если срок уже прошёл, то после текущего момента, иначе новый срок оказался бы в прошлом);
  урока нет — ``no_next_lesson``, тогда персонал задаёт дату вручную (это тоже перенос);
- дата вручную допустима всегда, но должна быть в будущем и позже текущего срока;
- каждый перенос пишется в журнал ``homework_extensions`` и в ``audit_log``; ``original_due_at``
  не меняется (от него считается «сдано в срок»);
- commit выполняет только этот сервис, один публичный метод = одна транзакция.
"""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.core import texts
from src.core.current_user import CurrentUser
from src.core.enums import AssignmentStatus
from src.core.exceptions import (
    BusinessRuleError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from src.core.timeutils import utcnow
from src.db.models import HomeworkAssignment, HomeworkExtension
from src.db.models.homework import MAX_EXTENSIONS
from src.repositories.audit_log import AuditLogRepository
from src.repositories.homework import HomeworkAssignmentRepository
from src.repositories.lessons import LessonRepository
from src.schemas.homework import ExtendRequest, ExtensionItem
from src.services.auth import STAFF_ROLES

AUDIT_EXTENDED = "assignment.extended"
AUDIT_ENTITY_ASSIGNMENT = "homework_assignment"
EXTENDABLE = frozenset({AssignmentStatus.ASSIGNED, AssignmentStatus.NEEDS_REVISION})


class ExtensionService:
    """Перенос дедлайна на следующее занятие или на дату вручную."""

    def __init__(self, session: AsyncSession) -> None:
        """Создать сервис.

        Args:
            session: Сессия БД на текущую единицу работы.
        """
        self._session = session
        self._assignments = HomeworkAssignmentRepository(session)
        self._lessons = LessonRepository(session)
        self._audit = AuditLogRepository(session)

    async def extend_deadline(
        self, actor: CurrentUser, assignment_id: int, data: ExtendRequest
    ) -> ExtensionItem:
        """Перенести срок сдачи.

        Raises:
            PermissionDeniedError: Не сотрудник.
            NotFoundError: ``assignment_not_found``.
            BusinessRuleError: ``assignment_not_extendable``; ``homework_extension_limit``;
                ``no_next_lesson`` — урока нет, а дата не задана.
            ValidationError: ``due_in_past`` или ``due_not_later`` — дата вручную неверна.
        """
        if actor.role not in STAFF_ROLES:
            raise PermissionDeniedError()
        assignment = await self._assignments.get_by_id(assignment_id, for_update=True)
        if assignment is None:
            raise NotFoundError(texts.ASSIGNMENT_NOT_FOUND, code="assignment_not_found")
        if assignment.status not in EXTENDABLE:
            raise BusinessRuleError(
                texts.ASSIGNMENT_NOT_EXTENDABLE, code="assignment_not_extendable"
            )
        if assignment.extensions_count >= MAX_EXTENSIONS:
            raise BusinessRuleError(texts.EXTENSION_LIMIT, code="homework_extension_limit")
        now = utcnow()
        new_due = await self._new_due(assignment, data.due_at, now)
        old_due = assignment.due_at
        assignment.due_at = new_due
        assignment.extensions_count += 1
        assignment.updated_at = now
        self._session.add(
            HomeworkExtension(
                assignment_id=assignment.id,
                old_due_at=old_due,
                new_due_at=new_due,
                created_by=actor.id,
            )
        )
        await self._audit.record(
            actor_user_id=actor.id,
            action=AUDIT_EXTENDED,
            entity_type=AUDIT_ENTITY_ASSIGNMENT,
            entity_id=assignment.id,
            data={
                "old_due_at": old_due.isoformat(),
                "new_due_at": new_due.isoformat(),
                "manual": data.due_at is not None,
            },
        )
        await self._session.commit()
        return ExtensionItem(
            assignment_id=assignment.id,
            old_due_at=old_due,
            new_due_at=new_due,
            extensions_count=assignment.extensions_count,
            extensions_left=MAX_EXTENSIONS - assignment.extensions_count,
        )

    async def _new_due(
        self, assignment: HomeworkAssignment, requested: datetime | None, now: datetime
    ) -> datetime:
        if requested is not None:
            if requested <= now:
                raise ValidationError(texts.HOMEWORK_DUE_IN_PAST, code="due_in_past")
            if requested <= assignment.due_at:
                raise ValidationError(texts.EXTENSION_DUE_NOT_LATER, code="due_not_later")
            return requested
        after = max(assignment.due_at, now)
        starts = await self._lessons.next_starts_for_students([assignment.student_id], after)
        due = starts.get(assignment.student_id)
        if due is None:
            raise BusinessRuleError(texts.RETURN_DUE_NOT_FOUND, code="no_next_lesson")
        return due
