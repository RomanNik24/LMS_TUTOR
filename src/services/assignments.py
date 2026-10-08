"""``AssignmentQueryService``: чтение выдач ДЗ для ученика и персонала (T4.11, docs/08 §4, §5.5).

Правила:
- ученик видит только свои выдачи; чужая и несуществующая выдача неотличимы (404);
- ученику отдаётся ``extensions_left``, но не журнал переносов; журнал видит только персонал;
- ``is_overdue``: срок вышел, а статус ``assigned`` или ``needs_revision`` (``expired`` — отдельно);
- ``on_time`` вычисляется на лету: ``submitted_at <= original_due_at``;
- сервис только читает, commit не нужен.
"""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.core import texts
from src.core.constants import LIST_LIMIT_DEFAULT, LIST_LIMIT_MAX
from src.core.current_user import CurrentUser
from src.core.enums import AssignmentStatus, UserRole
from src.core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from src.core.timeutils import utcnow
from src.db.models import Homework, HomeworkAssignment, HomeworkFile, HomeworkMaterial
from src.db.models.homework import MAX_EXTENSIONS
from src.repositories.homework import (
    HomeworkAssignmentRepository,
    HomeworkFileRepository,
    HomeworkRepository,
)
from src.schemas.files import HomeworkFileItem, MaterialItem
from src.schemas.homework import score_percent
from src.schemas.homework_views import (
    AdminAssignmentDetail,
    AdminAssignmentItem,
    AdminAssignmentPage,
    ExtensionLogItem,
    StudentAssignmentDetail,
    StudentAssignmentItem,
    StudentAssignmentPage,
    StudentHomeworkFilter,
)
from src.services.auth import STAFF_ROLES

ACTIVE = [AssignmentStatus.ASSIGNED, AssignmentStatus.NEEDS_REVISION]
_FILTERS: dict[StudentHomeworkFilter, list[AssignmentStatus]] = {
    StudentHomeworkFilter.ACTIVE: ACTIVE,
    StudentHomeworkFilter.SUBMITTED: [AssignmentStatus.SUBMITTED],
    StudentHomeworkFilter.GRADED: [AssignmentStatus.GRADED],
    StudentHomeworkFilter.EXPIRED: [AssignmentStatus.EXPIRED],
}

Row = tuple[HomeworkAssignment, Homework, str, str]


def _overdue(assignment: HomeworkAssignment, now: datetime) -> bool:
    return assignment.status in ACTIVE and now > assignment.due_at


def _on_time(assignment: HomeworkAssignment) -> bool | None:
    if assignment.submitted_at is None:
        return None
    return assignment.submitted_at <= assignment.original_due_at


def _file_item(file: HomeworkFile) -> HomeworkFileItem:
    return HomeworkFileItem(
        id=file.id,
        assignment_id=file.assignment_id,
        role=file.role,
        original_name=file.original_name,
        content_type=file.content_type,
        size_bytes=file.size_bytes,
        created_at=file.created_at,
    )


def _material_item(material: HomeworkMaterial) -> MaterialItem:
    return MaterialItem(
        id=material.id,
        homework_id=material.homework_id,
        original_name=material.original_name,
        content_type=material.content_type,
        size_bytes=material.size_bytes,
    )


class AssignmentQueryService:
    """Списки и карточки выдач."""

    def __init__(self, session: AsyncSession) -> None:
        """Создать сервис.

        Args:
            session: Сессия БД на текущую единицу работы.
        """
        self._assignments = HomeworkAssignmentRepository(session)
        self._files = HomeworkFileRepository(session)
        self._homeworks = HomeworkRepository(session)

    # ------------------------------------------------------------------ ученик

    async def list_student(
        self,
        actor: CurrentUser,
        status: StudentHomeworkFilter | None,
        *,
        limit: int = LIST_LIMIT_DEFAULT,
        offset: int = 0,
    ) -> StudentAssignmentPage:
        """Свои выдачи; ``status`` — вкладка (активные, сданные, проверенные, просроченные).

        Raises:
            PermissionDeniedError: Не ученик.
            ValidationError: ``invalid_list_params``.
        """
        self._require_student(actor)
        self._check_page(limit, offset)
        rows, total = await self._assignments.page(
            student_id=actor.id,
            statuses=_FILTERS[status] if status else None,
            sort_by_due=True,
            limit=limit,
            offset=offset,
        )
        now = utcnow()
        return StudentAssignmentPage(
            items=[self._student_item(row, now) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_student(self, actor: CurrentUser, assignment_id: int) -> StudentAssignmentDetail:
        """Карточка своей выдачи.

        Raises:
            PermissionDeniedError: Не ученик.
            NotFoundError: ``assignment_not_found`` (в том числе чужая выдача).
        """
        self._require_student(actor)
        row = await self._assignments.detail(assignment_id)
        if row is None or row[0].student_id != actor.id:
            raise NotFoundError(texts.ASSIGNMENT_NOT_FOUND, code="assignment_not_found")
        assignment, homework, _code, _name = row
        base = self._student_item(row, utcnow())
        materials = await self._homeworks.materials(homework.id)
        files = await self._files.list_for(assignment.id)
        return StudentAssignmentDetail(
            **base.model_dump(),
            description=homework.description,
            original_due_at=assignment.original_due_at,
            on_time=_on_time(assignment),
            submission_type=assignment.submission_type,
            student_comment=assignment.student_comment,
            teacher_comment=assignment.teacher_comment,
            materials=[_material_item(m) for m in materials],
            files=[_file_item(f) for f in files],
        )

    # ------------------------------------------------------------------ персонал

    async def list_staff(
        self,
        actor: CurrentUser,
        *,
        status: AssignmentStatus | None = None,
        student_id: int | None = None,
        overdue: bool = False,
        limit: int = LIST_LIMIT_DEFAULT,
        offset: int = 0,
    ) -> AdminAssignmentPage:
        """Выдачи всех учеников с фильтрами по статусу, ученику и «просрочено».

        Raises:
            PermissionDeniedError: Не сотрудник.
            ValidationError: ``invalid_list_params``.
        """
        self._require_staff(actor)
        self._check_page(limit, offset)
        now = utcnow()
        rows, total = await self._assignments.page(
            student_id=student_id,
            statuses=[status] if status else None,
            overdue_at=now if overdue else None,
            limit=limit,
            offset=offset,
        )
        return self._staff_page(rows, total, limit, offset, now)

    async def review_queue(
        self, actor: CurrentUser, *, limit: int = LIST_LIMIT_DEFAULT, offset: int = 0
    ) -> AdminAssignmentPage:
        """Очередь проверки: сданные работы, самые давние первыми.

        Raises:
            PermissionDeniedError: Не сотрудник.
            ValidationError: ``invalid_list_params``.
        """
        self._require_staff(actor)
        self._check_page(limit, offset)
        rows, total = await self._assignments.review_queue(limit=limit, offset=offset)
        return self._staff_page(rows, total, limit, offset, utcnow())

    async def get_staff(self, actor: CurrentUser, assignment_id: int) -> AdminAssignmentDetail:
        """Карточка выдачи: файлы ученика и проверки, журнал переносов.

        Raises:
            PermissionDeniedError: Не сотрудник.
            NotFoundError: ``assignment_not_found``.
        """
        self._require_staff(actor)
        row = await self._assignments.detail(assignment_id)
        if row is None:
            raise NotFoundError(texts.ASSIGNMENT_NOT_FOUND, code="assignment_not_found")
        assignment, homework, _code, _name = row
        base = self._admin_item(row, utcnow())
        materials = await self._homeworks.materials(homework.id)
        files = await self._files.list_for(assignment.id)
        extensions = await self._assignments.extensions(assignment.id)
        return AdminAssignmentDetail(
            **base.model_dump(),
            description=homework.description,
            original_due_at=assignment.original_due_at,
            on_time=_on_time(assignment),
            submission_type=assignment.submission_type,
            student_comment=assignment.student_comment,
            teacher_comment=assignment.teacher_comment,
            graded_after_expiry=assignment.graded_after_expiry,
            score_percent=score_percent(assignment.score, homework.max_score),
            materials=[_material_item(m) for m in materials],
            files=[_file_item(f) for f in files],
            extensions=[
                ExtensionLogItem(
                    old_due_at=e.old_due_at,
                    new_due_at=e.new_due_at,
                    created_by=e.created_by,
                    created_at=e.created_at,
                )
                for e in extensions
            ],
        )

    # ------------------------------------------------------------------ внутреннее

    @staticmethod
    def _require_student(actor: CurrentUser) -> None:
        if actor.role != UserRole.STUDENT:
            raise PermissionDeniedError()

    @staticmethod
    def _require_staff(actor: CurrentUser) -> None:
        if actor.role not in STAFF_ROLES:
            raise PermissionDeniedError()

    @staticmethod
    def _check_page(limit: int, offset: int) -> None:
        if not 1 <= limit <= LIST_LIMIT_MAX or offset < 0:
            raise ValidationError(texts.LIST_PARAMS_INVALID, code="invalid_list_params")

    @staticmethod
    def _student_item(row: Row, now: datetime) -> StudentAssignmentItem:
        assignment, homework, code, _name = row
        return StudentAssignmentItem(
            assignment_id=assignment.id,
            homework_id=homework.id,
            title=homework.title,
            kind=homework.kind,
            subject_code=code,
            status=assignment.status,
            due_at=assignment.due_at,
            is_overdue=_overdue(assignment, now),
            extensions_left=MAX_EXTENSIONS - assignment.extensions_count,
            max_score=homework.max_score,
            score=assignment.score,
            score_percent=score_percent(assignment.score, homework.max_score),
            submitted_at=assignment.submitted_at,
        )

    @staticmethod
    def _admin_item(row: Row, now: datetime) -> AdminAssignmentItem:
        assignment, homework, _code, name = row
        return AdminAssignmentItem(
            assignment_id=assignment.id,
            homework_id=homework.id,
            title=homework.title,
            kind=homework.kind,
            exam_type_id=homework.exam_type_id,
            student_id=assignment.student_id,
            student_name=name,
            status=assignment.status,
            due_at=assignment.due_at,
            is_overdue=_overdue(assignment, now),
            extensions_count=assignment.extensions_count,
            submitted_at=assignment.submitted_at,
            score=assignment.score,
            max_score=homework.max_score,
        )

    def _staff_page(
        self, rows: list[Row], total: int, limit: int, offset: int, now: datetime
    ) -> AdminAssignmentPage:
        return AdminAssignmentPage(
            items=[self._admin_item(row, now) for row in rows],
            total=total,
            limit=limit,
            offset=offset,
        )
