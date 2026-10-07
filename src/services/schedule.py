"""``ScheduleService``: расписание и уроки (T3.04, docs/08 §5.4, docs/01 US-02).

Правила:
- создавать уроки могут только ``owner`` и ``manager``;
- участники — только существующие активные ученики (архивный ученик — отказ);
- пересечение с другим не отменённым уроком преподавателя запрещает сама БД
  (``EXCLUDE``); сервис превращает это нарушение в ``ConflictError`` с кодом ``lesson_overlap``;
- commit выполняет только этот сервис, один публичный метод = одна транзакция.
"""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core import texts
from src.core.current_user import CurrentUser
from src.core.enums import AttendanceStatus, UserRole
from src.core.exceptions import (
    BusinessRuleError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from src.db.models import Lesson, User
from src.repositories.audit_log import AuditLogRepository
from src.repositories.lessons import LessonRepository
from src.repositories.subjects import SubjectRepository
from src.repositories.users import UserRepository
from src.schemas.schedule import LessonCreate, LessonItem, LessonParticipantItem
from src.services.auth import STAFF_ROLES

AUDIT_LESSON_CREATED = "lesson.created"
AUDIT_ENTITY_LESSON = "lesson"
OVERLAP_CONSTRAINT = "ex_lessons_teacher_no_overlap"


class ScheduleService:
    """Расписание: создание урока с защитой от пересечений."""

    def __init__(self, session: AsyncSession) -> None:
        """Создать сервис.

        Args:
            session: Сессия БД на текущую единицу работы.
        """
        self._session = session
        self._users = UserRepository(session)
        self._subjects = SubjectRepository(session)
        self._lessons = LessonRepository(session)
        self._audit = AuditLogRepository(session)

    async def create_lesson(self, actor: CurrentUser, data: LessonCreate) -> LessonItem:
        """Создать разовый урок с участниками.

        Args:
            actor: Сотрудник (``owner`` или ``manager``).
            data: Предмет, участники, время, переопределения ссылок, тема.

        Returns:
            Созданный урок с участниками.

        Raises:
            PermissionDeniedError: Не сотрудник.
            ValidationError: Неизвестный предмет или недопустимый преподаватель.
            NotFoundError: Участник не найден (нет такого ученика).
            BusinessRuleError: ``student_archived`` — участник в архиве.
            ConflictError: ``lesson_overlap`` — у преподавателя уже есть урок в это время.
        """
        if actor.role not in STAFF_ROLES:
            raise PermissionDeniedError()
        teacher_id = await self._resolve_teacher(actor, data.teacher_id)
        subject_id = await self._resolve_subject(data.subject_code)
        students = await self._resolve_students(data.student_ids)

        lesson = Lesson(
            teacher_id=teacher_id,
            subject_id=subject_id,
            start_at=data.start_at,
            end_at=data.end_at,
            video_url_override=data.video_url_override,
            board_url_override=data.board_url_override,
            topic=data.topic,
        )
        try:
            # Savepoint: после отказа БД сессия остаётся рабочей, а ошибка — понятной.
            async with self._session.begin_nested():
                await self._lessons.add(lesson)
        except IntegrityError as error:
            if OVERLAP_CONSTRAINT in str(error.orig):
                raise ConflictError(texts.LESSON_OVERLAP, code="lesson_overlap") from error
            raise
        await self._lessons.add_participants(lesson.id, [s.id for s in students])
        await self._audit.record(
            actor_user_id=actor.id,
            action=AUDIT_LESSON_CREATED,
            entity_type=AUDIT_ENTITY_LESSON,
            entity_id=lesson.id,
            data={"teacher_id": teacher_id, "students": len(students)},
        )
        await self._session.commit()
        return self._item(lesson, data.subject_code, students)

    # ------------------------------------------------------------------ внутреннее

    async def _resolve_teacher(self, actor: CurrentUser, teacher_id: int | None) -> int:
        """Преподаватель: по умолчанию сам сотрудник; иначе активный owner/manager."""
        if teacher_id is None or teacher_id == actor.id:
            return actor.id
        teacher = await self._users.get_by_id(teacher_id)
        if teacher is None or not teacher.is_active or teacher.role not in STAFF_ROLES:
            raise ValidationError(texts.LESSON_INVALID_TEACHER, code="invalid_teacher")
        return teacher.id

    async def _resolve_subject(self, code: str) -> int:
        found = await self._subjects.active_by_codes([code])
        if not found:
            raise ValidationError(
                texts.LESSON_UNKNOWN_SUBJECT, code="unknown_subject", details={"codes": [code]}
            )
        return found[0].id

    async def _resolve_students(self, student_ids: list[int]) -> list[User]:
        """Участники по порядку запроса: только существующие активные ученики."""
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

    @staticmethod
    def _item(lesson: Lesson, subject_code: str, students: list[User]) -> LessonItem:
        return LessonItem(
            id=lesson.id,
            teacher_id=lesson.teacher_id,
            subject_code=subject_code,
            start_at=lesson.start_at,
            end_at=lesson.end_at,
            status=lesson.status,
            is_detached=lesson.is_detached,
            video_url_override=lesson.video_url_override,
            board_url_override=lesson.board_url_override,
            topic=lesson.topic,
            participants=[
                LessonParticipantItem(
                    student_id=s.id,
                    display_name=s.display_name,
                    attendance=AttendanceStatus.PENDING,
                )
                for s in students
            ],
        )
