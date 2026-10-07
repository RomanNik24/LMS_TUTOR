"""``GradingService``: проверка, оценка и возврат на доработку (T4.08, docs/01 US-06, docs/04 §5.3).

Правила:
- всё это делает только персонал (owner и manager);
- оценить можно сданную работу (``submitted``); просроченную (``expired``) — вручную, тогда
  ставится ``graded_after_expiry = true`` и пишется запись в ``audit_log``; уже оценённую можно
  исправить (старый и новый балл попадают в аудит); остальные статусы — ``assignment_not_gradable``;
- балл — целое от 0 до ``homeworks.max_score``, иначе 400 ``score_out_of_range``;
- вернуть на доработку можно только сданную работу: комментарий обязателен, новый срок — заданный
  или начало ближайшего урока ученика (``no_next_lesson``, если урока нет и срок не задан);
- конвертация баллов пробников в оценку — этап 6, здесь её нет;
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
from src.db.models import Homework, HomeworkAssignment
from src.repositories.audit_log import AuditLogRepository
from src.repositories.homework import HomeworkAssignmentRepository, HomeworkRepository
from src.repositories.lessons import LessonRepository
from src.schemas.homework import GradeItem, GradeRequest, ReturnRequest
from src.services.auth import STAFF_ROLES
from src.services.notification_events import NotificationEvents

AUDIT_GRADED = "assignment.graded"
AUDIT_GRADED_AFTER_EXPIRY = "assignment.graded_after_expiry"
AUDIT_RETURNED = "assignment.returned"
AUDIT_ENTITY_ASSIGNMENT = "homework_assignment"

GRADABLE = frozenset(
    {AssignmentStatus.SUBMITTED, AssignmentStatus.EXPIRED, AssignmentStatus.GRADED}
)
PERCENT = 100


class GradingService:
    """Оценка работ и возврат на доработку."""

    def __init__(self, session: AsyncSession) -> None:
        """Создать сервис.

        Args:
            session: Сессия БД на текущую единицу работы.
        """
        self._session = session
        self._assignments = HomeworkAssignmentRepository(session)
        self._homeworks = HomeworkRepository(session)
        self._lessons = LessonRepository(session)
        self._audit = AuditLogRepository(session)
        self._events = NotificationEvents(session)

    async def grade_assignment(
        self, actor: CurrentUser, assignment_id: int, data: GradeRequest
    ) -> GradeItem:
        """Поставить оценку.

        Raises:
            PermissionDeniedError: Не сотрудник.
            NotFoundError: ``assignment_not_found``.
            BusinessRuleError: ``score_out_of_range``; ``assignment_not_gradable``.
        """
        self._require_staff(actor)
        assignment, homework = await self._load(assignment_id)
        if assignment.status not in GRADABLE:
            raise BusinessRuleError(texts.ASSIGNMENT_NOT_GRADABLE, code="assignment_not_gradable")
        if not 0 <= data.score <= homework.max_score:
            raise BusinessRuleError(
                texts.SCORE_OUT_OF_RANGE.format(max_score=homework.max_score),
                code="score_out_of_range",
                details={"max_score": homework.max_score},
            )
        now = utcnow()
        after_expiry = assignment.status == AssignmentStatus.EXPIRED
        previous_score = assignment.score
        assignment.status = AssignmentStatus.GRADED
        assignment.score = data.score
        assignment.graded_at = now
        assignment.graded_by = actor.id
        assignment.teacher_comment = data.comment
        assignment.updated_at = now
        if after_expiry:
            assignment.graded_after_expiry = True
        audit_data: dict[str, object] = {"score": data.score, "max_score": homework.max_score}
        if previous_score is not None:
            audit_data["previous_score"] = previous_score
        await self._audit.record(
            actor_user_id=actor.id,
            action=AUDIT_GRADED_AFTER_EXPIRY if after_expiry else AUDIT_GRADED,
            entity_type=AUDIT_ENTITY_ASSIGNMENT,
            entity_id=assignment.id,
            data=audit_data,
        )
        await self._events.homework_graded(
            assignment.student_id, assignment.id, homework.title, data.score, homework.max_score
        )
        await self._session.commit()
        return self._item(assignment, homework)

    async def return_for_revision(
        self, actor: CurrentUser, assignment_id: int, data: ReturnRequest
    ) -> GradeItem:
        """Вернуть сданную работу на доработку с комментарием и новым сроком.

        Raises:
            PermissionDeniedError: Не сотрудник.
            NotFoundError: ``assignment_not_found``.
            ValidationError: ``due_in_past`` — новый срок не в будущем.
            BusinessRuleError: ``assignment_not_returnable``; ``no_next_lesson``.
        """
        self._require_staff(actor)
        assignment, homework = await self._load(assignment_id)
        if assignment.status != AssignmentStatus.SUBMITTED:
            raise BusinessRuleError(
                texts.ASSIGNMENT_NOT_RETURNABLE, code="assignment_not_returnable"
            )
        now = utcnow()
        new_due = await self._new_due(assignment, data.new_due_at, now)
        old_due = assignment.due_at
        submitted_at = assignment.submitted_at
        assignment.status = AssignmentStatus.NEEDS_REVISION
        assignment.teacher_comment = data.comment
        assignment.due_at = new_due
        assignment.updated_at = now
        await self._audit.record(
            actor_user_id=actor.id,
            action=AUDIT_RETURNED,
            entity_type=AUDIT_ENTITY_ASSIGNMENT,
            entity_id=assignment.id,
            data={"old_due_at": old_due.isoformat(), "new_due_at": new_due.isoformat()},
        )
        await self._events.homework_returned(
            assignment.student_id, assignment.id, homework.title, data.comment, submitted_at
        )
        await self._session.commit()
        return self._item(assignment, homework)

    # ------------------------------------------------------------------ внутреннее

    @staticmethod
    def _require_staff(actor: CurrentUser) -> None:
        if actor.role not in STAFF_ROLES:
            raise PermissionDeniedError()

    async def _load(self, assignment_id: int) -> tuple[HomeworkAssignment, Homework]:
        assignment = await self._assignments.get_by_id(assignment_id, for_update=True)
        if assignment is None:
            raise NotFoundError(texts.ASSIGNMENT_NOT_FOUND, code="assignment_not_found")
        homework = await self._homeworks.get_by_id(assignment.homework_id)
        if homework is None:  # внешний ключ гарантирует наличие; защита от гонки удаления
            raise NotFoundError(texts.HOMEWORK_NOT_FOUND, code="homework_not_found")
        return assignment, homework

    async def _new_due(
        self, assignment: HomeworkAssignment, requested: datetime | None, now: datetime
    ) -> datetime:
        if requested is not None:
            if requested <= now:
                raise ValidationError(texts.HOMEWORK_DUE_IN_PAST, code="due_in_past")
            return requested
        starts = await self._lessons.next_starts_for_students([assignment.student_id], now)
        due = starts.get(assignment.student_id)
        if due is None:
            raise BusinessRuleError(texts.RETURN_DUE_NOT_FOUND, code="no_next_lesson")
        return due

    @staticmethod
    def _item(assignment: HomeworkAssignment, homework: Homework) -> GradeItem:
        percent = (
            None
            if assignment.score is None
            else round(assignment.score * PERCENT / homework.max_score)
        )
        return GradeItem(
            assignment_id=assignment.id,
            status=assignment.status,
            score=assignment.score,
            max_score=homework.max_score,
            score_percent=percent,
            graded_at=assignment.graded_at,
            graded_after_expiry=assignment.graded_after_expiry,
            teacher_comment=assignment.teacher_comment,
            due_at=assignment.due_at,
        )
