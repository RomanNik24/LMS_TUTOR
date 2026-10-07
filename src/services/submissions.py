"""``SubmissionService``: сдача решений учеником (T4.06→T4.07, docs/01 US-04, docs/04 §5.3).

Правила:
- сдавать может только ученик-владелец выдачи; чужая или несуществующая выдача — одинаково 404;
- сдать можно только в статусах ``assigned`` и ``needs_revision``; ``expired`` — отказ
  ``assignment_expired``; ``submitted`` и ``graded`` — ``assignment_not_submittable``;
- «просрочено» (срок вышел, но переносы не исчерпаны) сдаче не мешает: решает преподаватель;
- ``on_time`` вычисляется на лету: ``submitted_at <= original_due_at`` (перенос срока «в срок»
  не возвращает);
- «Сделал» (``self_reported``) не требует файлов; если ученик уже загрузил файлы, сдача
  считается файловой (``files``), чтобы преподаватель увидел приложенное;
- файлы до сдачи добавляет и удаляет ``FileService``; здесь только перевод в ``submitted``;
- commit выполняет только этот сервис, один публичный метод = одна транзакция.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from src.core import texts
from src.core.current_user import CurrentUser
from src.core.enums import AssignmentStatus, HomeworkFileRole, SubmissionType, UserRole
from src.core.exceptions import BusinessRuleError, NotFoundError, PermissionDeniedError
from src.core.timeutils import utcnow
from src.db.models import HomeworkAssignment
from src.repositories.homework import HomeworkAssignmentRepository, HomeworkFileRepository
from src.schemas.homework import SubmissionItem, SubmitRequest

SUBMITTABLE = frozenset({AssignmentStatus.ASSIGNED, AssignmentStatus.NEEDS_REVISION})


class SubmissionService:
    """Сдача решений: файлами или кнопкой «Сделал»."""

    def __init__(self, session: AsyncSession) -> None:
        """Создать сервис.

        Args:
            session: Сессия БД на текущую единицу работы.
        """
        self._session = session
        self._assignments = HomeworkAssignmentRepository(session)
        self._files = HomeworkFileRepository(session)

    async def submit_files(
        self, actor: CurrentUser, assignment_id: int, data: SubmitRequest
    ) -> SubmissionItem:
        """Сдать работу с файлами (нужен хотя бы один загруженный файл решения).

        Raises:
            PermissionDeniedError: Не ученик.
            NotFoundError: ``assignment_not_found``.
            BusinessRuleError: ``assignment_expired``, ``assignment_not_submittable``,
                ``no_files`` — файлов нет.
        """
        assignment = await self._lock_submittable(actor, assignment_id)
        count = await self._files.count_for(assignment.id, HomeworkFileRole.STUDENT_SOLUTION)
        if count == 0:
            raise BusinessRuleError(texts.SUBMISSION_NO_FILES, code="no_files")
        return await self._submit(assignment, SubmissionType.FILES, data, count)

    async def submit_self_reported(
        self, actor: CurrentUser, assignment_id: int, data: SubmitRequest
    ) -> SubmissionItem:
        """Сдать кнопкой «Сделал»: файлы не обязательны.

        Если файлы уже загружены, сдача записывается как файловая.

        Raises:
            PermissionDeniedError: Не ученик.
            NotFoundError: ``assignment_not_found``.
            BusinessRuleError: ``assignment_expired``, ``assignment_not_submittable``.
        """
        assignment = await self._lock_submittable(actor, assignment_id)
        count = await self._files.count_for(assignment.id, HomeworkFileRole.STUDENT_SOLUTION)
        kind = SubmissionType.FILES if count else SubmissionType.SELF_REPORTED
        return await self._submit(assignment, kind, data, count)

    # ------------------------------------------------------------------ внутреннее

    async def _lock_submittable(self, actor: CurrentUser, assignment_id: int) -> HomeworkAssignment:
        if actor.role != UserRole.STUDENT:
            raise PermissionDeniedError()
        assignment = await self._assignments.get_by_id(assignment_id, for_update=True)
        if assignment is None or assignment.student_id != actor.id:
            raise NotFoundError(texts.ASSIGNMENT_NOT_FOUND, code="assignment_not_found")
        if assignment.status == AssignmentStatus.EXPIRED:
            raise BusinessRuleError(texts.ASSIGNMENT_EXPIRED, code="assignment_expired")
        if assignment.status not in SUBMITTABLE:
            raise BusinessRuleError(
                texts.ASSIGNMENT_NOT_SUBMITTABLE, code="assignment_not_submittable"
            )
        return assignment

    async def _submit(
        self,
        assignment: HomeworkAssignment,
        kind: SubmissionType,
        data: SubmitRequest,
        files_count: int,
    ) -> SubmissionItem:
        now = utcnow()
        assignment.status = AssignmentStatus.SUBMITTED
        assignment.submission_type = kind
        assignment.submitted_at = now
        assignment.student_comment = data.student_comment
        assignment.updated_at = now
        await self._session.commit()
        return SubmissionItem(
            assignment_id=assignment.id,
            status=assignment.status,
            submission_type=kind,
            submitted_at=now,
            on_time=now <= assignment.original_due_at,
            files_count=files_count,
        )
