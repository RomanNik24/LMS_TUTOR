"""``HomeworkService``: создание и выдача домашних заданий (T4.06, docs/01 US-03, docs/04 §5).

Правила:
- создавать и выдавать задания может только персонал;
- одно задание = одно ``homework`` и N выдач (``homework_assignments``): у каждого ученика свой
  статус, свой срок и своя оценка;
- выдаются только существующим активным ученикам;
- первоначальный срок: ``fixed`` — заданная дата, ``next_lesson`` — начало ближайшего
  запланированного урока ученика (для учеников без урока — запасной ``due_at``, иначе ошибка
  ``no_next_lesson``); срок обязан быть в будущем;
- ``mock_exam``: предмет берётся из типа экзамена, максимальный балл по умолчанию равен
  максимальному первичному баллу экзамена;
- commit выполняет только этот сервис, один публичный метод = одна транзакция.
"""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from src.core import texts
from src.core.constants import LIST_LIMIT_DEFAULT, LIST_LIMIT_MAX
from src.core.current_user import CurrentUser
from src.core.enums import DueMode, HomeworkKind, UserRole
from src.core.exceptions import (
    BusinessRuleError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from src.core.timeutils import utcnow
from src.db.models import Homework, HomeworkAssignment, User
from src.repositories.audit_log import AuditLogRepository
from src.repositories.homework import ExamTypeRepository, HomeworkRepository
from src.repositories.lessons import LessonRepository
from src.repositories.subjects import SubjectRepository
from src.repositories.users import UserRepository
from src.schemas.files import MaterialItem
from src.schemas.homework import (
    AssigneesAdd,
    AssignmentItem,
    HomeworkCreate,
    HomeworkItem,
    HomeworkListItem,
    HomeworkListPage,
)
from src.services.auth import STAFF_ROLES
from src.services.notification_events import NotificationEvents

AUDIT_HOMEWORK_CREATED = "homework.created"
AUDIT_HOMEWORK_ASSIGNED = "homework.assignees_added"
AUDIT_ENTITY_HOMEWORK = "homework"


class HomeworkService:
    """Задания: создание, выдача ученикам, просмотр."""

    def __init__(self, session: AsyncSession) -> None:
        """Создать сервис.

        Args:
            session: Сессия БД на текущую единицу работы.
        """
        self._session = session
        self._homeworks = HomeworkRepository(session)
        self._exam_types = ExamTypeRepository(session)
        self._subjects = SubjectRepository(session)
        self._lessons = LessonRepository(session)
        self._users = UserRepository(session)
        self._audit = AuditLogRepository(session)
        self._events = NotificationEvents(session)

    async def create_homework(self, actor: CurrentUser, data: HomeworkCreate) -> HomeworkItem:
        """Создать задание и выдать его ученикам.

        Raises:
            PermissionDeniedError: Не сотрудник.
            ValidationError: неизвестные предмет, тип экзамена или урок (``unknown_subject``,
                ``unknown_exam_type``, ``unknown_lesson``), срок в прошлом (``due_in_past``),
                предмет не совпадает с предметом экзамена (``subject_mismatch``).
            NotFoundError: ``student_not_found`` — ученика нет.
            BusinessRuleError: ``student_archived``; ``no_next_lesson`` — у ученика нет урока
                для срока «следующее занятие».
        """
        self._require_staff(actor)
        subject_id, max_score = await self._resolve_subject_and_score(data)
        if data.lesson_id is not None and await self._lessons.get_by_id(data.lesson_id) is None:
            raise ValidationError(texts.HOMEWORK_LESSON_UNKNOWN, code="unknown_lesson")
        students = await self._resolve_students(data.student_ids)
        now = utcnow()
        due = await self._due_dates(data.due_mode, data.due_at, students, now)

        homework = await self._homeworks.add(
            Homework(
                created_by=actor.id,
                lesson_id=data.lesson_id,
                subject_id=subject_id,
                kind=data.kind,
                exam_type_id=data.exam_type_id,
                title=data.title,
                description=data.description,
                max_score=max_score,
                due_mode=data.due_mode,
            )
        )
        rows = [
            HomeworkAssignment(
                homework_id=homework.id,
                student_id=student.id,
                original_due_at=due[student.id],
                due_at=due[student.id],
            )
            for student in students
        ]
        await self._homeworks.add_assignments(rows)
        await self._notify_assigned(homework.title, rows)
        await self._audit.record(
            actor_user_id=actor.id,
            action=AUDIT_HOMEWORK_CREATED,
            entity_type=AUDIT_ENTITY_HOMEWORK,
            entity_id=homework.id,
            data={"kind": data.kind.value, "assignees": len(students)},
        )
        await self._session.commit()
        return await self._build_item(homework)

    async def add_assignees(
        self, actor: CurrentUser, homework_id: int, data: AssigneesAdd
    ) -> HomeworkItem:
        """Добавить учеников к заданию; уже получившие его пропускаются.

        Срок новым ученикам: ``fixed`` — ``due_at`` из запроса или самый ранний первоначальный
        срок задания; ``next_lesson`` — ближайший урок ученика (запасной вариант — ``due_at``).

        Raises:
            PermissionDeniedError: Не сотрудник.
            NotFoundError: ``homework_not_found`` или ``student_not_found``.
            ValidationError: ``due_in_past``.
            BusinessRuleError: ``student_archived``, ``no_next_lesson``.
        """
        self._require_staff(actor)
        homework = await self._homeworks.get_by_id(homework_id)
        if homework is None:
            raise NotFoundError(texts.HOMEWORK_NOT_FOUND, code="homework_not_found")
        already = await self._homeworks.assigned_student_ids(homework.id)
        students = await self._resolve_students(
            [sid for sid in data.student_ids if sid not in already]
        )
        if students:
            now = utcnow()
            fallback = data.due_at
            if homework.due_mode == DueMode.FIXED and fallback is None:
                fallback = await self._homeworks.first_original_due(homework.id)
            due = await self._due_dates(homework.due_mode, fallback, students, now)
            rows = [
                HomeworkAssignment(
                    homework_id=homework.id,
                    student_id=student.id,
                    original_due_at=due[student.id],
                    due_at=due[student.id],
                )
                for student in students
            ]
            await self._homeworks.add_assignments(rows)
            await self._notify_assigned(homework.title, rows)
            await self._audit.record(
                actor_user_id=actor.id,
                action=AUDIT_HOMEWORK_ASSIGNED,
                entity_type=AUDIT_ENTITY_HOMEWORK,
                entity_id=homework.id,
                data={"added": len(students)},
            )
            await self._session.commit()
        return await self._build_item(homework)

    async def get_homework(self, actor: CurrentUser, homework_id: int) -> HomeworkItem:
        """Задание со всеми выдачами и материалами.

        Raises:
            PermissionDeniedError: Не сотрудник.
            NotFoundError: ``homework_not_found``.
        """
        self._require_staff(actor)
        homework = await self._homeworks.get_by_id(homework_id)
        if homework is None:
            raise NotFoundError(texts.HOMEWORK_NOT_FOUND, code="homework_not_found")
        return await self._build_item(homework)

    async def list_homeworks(
        self, actor: CurrentUser, *, limit: int = LIST_LIMIT_DEFAULT, offset: int = 0
    ) -> HomeworkListPage:
        """Список заданий (новые сверху) со счётчиками «сдали N из M».

        Raises:
            PermissionDeniedError: Не сотрудник.
            ValidationError: ``invalid_list_params``.
        """
        self._require_staff(actor)
        if not 1 <= limit <= LIST_LIMIT_MAX or offset < 0:
            raise ValidationError(texts.LIST_PARAMS_INVALID, code="invalid_list_params")
        rows, total = await self._homeworks.list_page(limit=limit, offset=offset)
        items = [
            HomeworkListItem(
                id=homework.id,
                kind=homework.kind,
                title=homework.title,
                subject_code=code,
                max_score=homework.max_score,
                created_at=homework.created_at,
                assigned_count=assigned,
                submitted_count=submitted,
            )
            for homework, code, assigned, submitted in rows
        ]
        return HomeworkListPage(items=items, total=total, limit=limit, offset=offset)

    # ------------------------------------------------------------------ внутреннее

    async def _notify_assigned(self, title: str, rows: list[HomeworkAssignment]) -> None:
        for row in rows:
            await self._events.homework_assigned(row.student_id, row.id, title, row.due_at)

    @staticmethod
    def _require_staff(actor: CurrentUser) -> None:
        if actor.role not in STAFF_ROLES:
            raise PermissionDeniedError()

    async def _resolve_subject_and_score(self, data: HomeworkCreate) -> tuple[int, int]:
        """Предмет и максимальный балл с учётом вида задания."""
        if data.kind == HomeworkKind.MOCK_EXAM:
            if data.exam_type_id is None:  # схема этого не допускает; защита от обхода
                raise ValidationError(texts.HOMEWORK_EXAM_TYPE_REQUIRED, code="exam_type_required")
            exam = await self._exam_types.get_by_id(data.exam_type_id)
            if exam is None:
                raise ValidationError(texts.HOMEWORK_EXAM_TYPE_UNKNOWN, code="unknown_exam_type")
            if data.subject_code is not None:
                found = await self._subjects.active_by_codes([data.subject_code])
                if not found or found[0].id != exam.subject_id:
                    raise ValidationError(texts.HOMEWORK_SUBJECT_MISMATCH, code="subject_mismatch")
            return exam.subject_id, data.max_score or exam.max_primary
        if data.subject_code is None or data.max_score is None:
            raise ValidationError(texts.HOMEWORK_SUBJECT_REQUIRED, code="validation_error")
        found = await self._subjects.active_by_codes([data.subject_code])
        if not found:
            raise ValidationError(
                texts.LESSON_UNKNOWN_SUBJECT,
                code="unknown_subject",
                details={"codes": [data.subject_code]},
            )
        return found[0].id, data.max_score

    async def _resolve_students(self, student_ids: list[int]) -> list[User]:
        """Существующие активные ученики по порядку запроса."""
        by_id = {user.id: user for user in await self._users.list_by_ids(student_ids)}
        students: list[User] = []
        for student_id in student_ids:
            user = by_id.get(student_id)
            if user is None or user.role != UserRole.STUDENT:
                raise NotFoundError(texts.LESSON_STUDENT_NOT_FOUND, code="student_not_found")
            if not user.is_active:
                raise BusinessRuleError(texts.LESSON_STUDENT_ARCHIVED, code="student_archived")
            students.append(user)
        return students

    async def _due_dates(
        self,
        due_mode: DueMode,
        due_at: datetime | None,
        students: list[User],
        now: datetime,
    ) -> dict[int, datetime]:
        """Первоначальный срок каждого ученика по режиму; срок обязан быть в будущем."""
        if due_at is not None and due_at <= now:
            raise ValidationError(texts.HOMEWORK_DUE_IN_PAST, code="due_in_past")
        if due_mode == DueMode.FIXED:
            if due_at is None:
                raise ValidationError(texts.HOMEWORK_DUE_AT_REQUIRED, code="due_at_required")
            return {student.id: due_at for student in students}
        starts = await self._lessons.next_starts_for_students([s.id for s in students], now)
        due: dict[int, datetime] = {}
        missing: list[int] = []
        for student in students:
            start = starts.get(student.id, due_at)
            if start is None:
                missing.append(student.id)
            else:
                due[student.id] = start
        if missing:
            raise BusinessRuleError(
                texts.HOMEWORK_NO_NEXT_LESSON,
                code="no_next_lesson",
                details={"student_ids": missing},
            )
        return due

    async def _build_item(self, homework: Homework) -> HomeworkItem:
        assignments = await self._homeworks.assignments_with_names(homework.id)
        materials = await self._homeworks.materials(homework.id)
        return HomeworkItem(
            id=homework.id,
            kind=homework.kind,
            title=homework.title,
            description=homework.description,
            subject_code=await self._homeworks.subject_code(homework.subject_id),
            exam_type_id=homework.exam_type_id,
            lesson_id=homework.lesson_id,
            max_score=homework.max_score,
            due_mode=homework.due_mode,
            created_at=homework.created_at,
            materials=[
                MaterialItem(
                    id=material.id,
                    homework_id=homework.id,
                    original_name=material.original_name,
                    content_type=material.content_type,
                    size_bytes=material.size_bytes,
                )
                for material in materials
            ],
            assignments=[
                AssignmentItem(
                    id=row.id,
                    student_id=row.student_id,
                    display_name=name,
                    status=row.status,
                    original_due_at=row.original_due_at,
                    due_at=row.due_at,
                    extensions_count=row.extensions_count,
                )
                for row, name in assignments
            ],
        )
