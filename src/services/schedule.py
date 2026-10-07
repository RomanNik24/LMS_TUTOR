"""``ScheduleService``: расписание и уроки (T3.04, docs/08 §5.4, docs/01 US-02).

Правила:
- создавать уроки могут только ``owner`` и ``manager``;
- участники — только существующие активные ученики (архивный ученик — отказ);
- пересечение с другим не отменённым уроком преподавателя запрещает сама БД
  (``EXCLUDE``); сервис превращает это нарушение в ``ConflictError`` с кодом ``lesson_overlap``;
- commit выполняет только этот сервис, один публичный метод = одна транзакция.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core import texts
from src.core.current_user import CurrentUser
from src.core.enums import AttendanceStatus, LessonStatus, UserRole
from src.core.exceptions import (
    BusinessRuleError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from src.core.timeutils import utcnow
from src.db.models import Lesson, User
from src.repositories.audit_log import AuditLogRepository
from src.repositories.lessons import LessonRepository
from src.repositories.student_profiles import StudentProfileRepository
from src.repositories.subjects import SubjectRepository
from src.repositories.users import UserRepository
from src.schemas.schedule import (
    LessonCancel,
    LessonComplete,
    LessonCreate,
    LessonItem,
    LessonParticipantItem,
    LessonReschedule,
)
from src.services.auth import STAFF_ROLES

AUDIT_LESSON_CREATED = "lesson.created"
AUDIT_LESSON_RESCHEDULED = "lesson.rescheduled"
AUDIT_LESSON_CANCELLED = "lesson.cancelled"
AUDIT_LESSON_COMPLETED = "lesson.completed"
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
        self._profiles = StudentProfileRepository(session)
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
        self._require_staff(actor)
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
        async with self._overlap_guard():
            self._session.add(lesson)
        await self._lessons.add_participants(lesson.id, [s.id for s in students])
        await self._audit.record(
            actor_user_id=actor.id,
            action=AUDIT_LESSON_CREATED,
            entity_type=AUDIT_ENTITY_LESSON,
            entity_id=lesson.id,
            data={"teacher_id": teacher_id, "students": len(students)},
        )
        await self._session.commit()
        return await self._build_item(lesson)

    async def reschedule_lesson(
        self, actor: CurrentUser, lesson_id: int, data: LessonReschedule
    ) -> LessonItem:
        """Перенести запланированный урок: новое время, ``is_detached = true``, аудит.

        Raises:
            PermissionDeniedError: Не сотрудник.
            NotFoundError: ``lesson_not_found``.
            BusinessRuleError: ``lesson_not_scheduled`` — урок проведён или отменён.
            ConflictError: ``lesson_overlap`` — новое время пересекается с другим уроком.
        """
        self._require_staff(actor)
        lesson = await self._load_scheduled(lesson_id)
        old = {"start_at": lesson.start_at.isoformat(), "end_at": lesson.end_at.isoformat()}
        async with self._overlap_guard():
            lesson.start_at = data.start_at
            lesson.end_at = data.end_at
            lesson.is_detached = True
            lesson.updated_at = utcnow()
        await self._audit.record(
            actor_user_id=actor.id,
            action=AUDIT_LESSON_RESCHEDULED,
            entity_type=AUDIT_ENTITY_LESSON,
            entity_id=lesson.id,
            data={
                "old": old,
                "new": {
                    "start_at": data.start_at.isoformat(),
                    "end_at": data.end_at.isoformat(),
                },
            },
        )
        await self._session.commit()
        return await self._build_item(lesson)

    async def cancel_lesson(
        self, actor: CurrentUser, lesson_id: int, data: LessonCancel
    ) -> LessonItem:
        """Отменить запланированный урок.

        Участники получают посещаемость «отменено»; за учеников из ``billable_student_ids`` отмена
        засчитывается (``is_billable``) и фиксируется текущая цена (``price_snapshot``).

        Raises:
            PermissionDeniedError: Не сотрудник.
            NotFoundError: ``lesson_not_found``.
            BusinessRuleError: ``lesson_not_scheduled``; ``not_participant`` — в списке
                «засчитать» есть не участник урока.
        """
        self._require_staff(actor)
        lesson = await self._load_scheduled(lesson_id)
        participants = await self._lessons.participants(lesson.id)
        member_ids = {p.student_id for p in participants}
        billable = set(data.billable_student_ids)
        if not billable <= member_ids:
            raise BusinessRuleError(texts.LESSON_NOT_PARTICIPANT, code="not_participant")
        prices = await self._profiles.prices_for(sorted(billable))
        now = utcnow()
        for participant in participants:
            participant.attendance = AttendanceStatus.CANCELLED
            if participant.student_id in billable:
                participant.is_billable = True
                participant.price_snapshot = prices.get(participant.student_id, 0)
        lesson.status = LessonStatus.CANCELLED
        lesson.cancelled_at = now
        lesson.cancelled_by = actor.id
        lesson.cancel_reason = data.reason
        lesson.updated_at = now
        await self._audit.record(
            actor_user_id=actor.id,
            action=AUDIT_LESSON_CANCELLED,
            entity_type=AUDIT_ENTITY_LESSON,
            entity_id=lesson.id,
            data={"reason": data.reason, "billable": len(billable)},
        )
        await self._session.commit()
        return await self._build_item(lesson)

    async def complete_lesson(
        self, actor: CurrentUser, lesson_id: int, data: LessonComplete
    ) -> LessonItem:
        """Отметить проведение: посещаемость каждого участника и фиксация цены.

        По умолчанию «был» → оплачиваемо, «не пришёл» и «отменено» → нет (можно включить).
        ``price_snapshot`` копируется В МОМЕНТ отметки для «был» и для отмеченных «засчитать»;
        последующая смена цены ученика проведённые уроки не меняет. Повторная отметка запрещена:
        иначе цена пересчиталась бы по новому значению.

        Raises:
            PermissionDeniedError: Не сотрудник.
            NotFoundError: ``lesson_not_found``.
            BusinessRuleError: ``lesson_already_completed``; ``lesson_not_scheduled`` (отменён);
                ``marks_mismatch`` — отмечены не все участники или лишние.
        """
        self._require_staff(actor)
        lesson = await self._lessons.get_by_id(lesson_id, for_update=True)
        if lesson is None:
            raise NotFoundError(texts.LESSON_NOT_FOUND, code="lesson_not_found")
        if lesson.status == LessonStatus.COMPLETED:
            raise BusinessRuleError(texts.LESSON_ALREADY_COMPLETED, code="lesson_already_completed")
        if lesson.status != LessonStatus.SCHEDULED:
            raise BusinessRuleError(texts.LESSON_NOT_SCHEDULED, code="lesson_not_scheduled")
        participants = await self._lessons.participants(lesson.id)
        marks = {mark.student_id: mark for mark in data.marks}
        if set(marks) != {p.student_id for p in participants}:
            raise BusinessRuleError(texts.LESSON_MARKS_MISMATCH, code="marks_mismatch")
        prices = await self._profiles.prices_for(list(marks))
        now = utcnow()
        for participant in participants:
            mark = marks[participant.student_id]
            attended = mark.attendance == AttendanceStatus.ATTENDED
            billable = attended if mark.is_billable is None else mark.is_billable
            participant.attendance = mark.attendance
            participant.is_billable = billable
            participant.price_snapshot = (
                prices.get(participant.student_id, 0) if attended or billable else None
            )
        lesson.status = LessonStatus.COMPLETED
        lesson.completed_at = now
        lesson.updated_at = now
        await self._audit.record(
            actor_user_id=actor.id,
            action=AUDIT_LESSON_COMPLETED,
            entity_type=AUDIT_ENTITY_LESSON,
            entity_id=lesson.id,
            data={"participants": len(participants)},
        )
        await self._session.commit()
        return await self._build_item(lesson)

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
    def _require_staff(actor: CurrentUser) -> None:
        if actor.role not in STAFF_ROLES:
            raise PermissionDeniedError()

    async def _load_scheduled(self, lesson_id: int) -> Lesson:
        """Урок под блокировкой; менять можно только запланированный."""
        lesson = await self._lessons.get_by_id(lesson_id, for_update=True)
        if lesson is None:
            raise NotFoundError(texts.LESSON_NOT_FOUND, code="lesson_not_found")
        if lesson.status != LessonStatus.SCHEDULED:
            raise BusinessRuleError(texts.LESSON_NOT_SCHEDULED, code="lesson_not_scheduled")
        return lesson

    @asynccontextmanager
    async def _overlap_guard(self) -> AsyncIterator[None]:
        """Savepoint вокруг записи урока: нарушение ``EXCLUDE`` → ``lesson_overlap``.

        Изменения полей урока делаются ВНУТРИ блока: вход в savepoint сам сбрасывает
        накопленные изменения, и отказ БД случился бы вне защиты.
        """
        try:
            async with self._session.begin_nested():
                yield
                await self._session.flush()
        except IntegrityError as error:
            if OVERLAP_CONSTRAINT in str(error.orig):
                raise ConflictError(texts.LESSON_OVERLAP, code="lesson_overlap") from error
            raise

    async def _build_item(self, lesson: Lesson) -> LessonItem:
        """Ответ для сотрудников по текущему состоянию урока в БД."""
        rows = await self._lessons.participants_with_names(lesson.id)
        return LessonItem(
            id=lesson.id,
            teacher_id=lesson.teacher_id,
            subject_code=await self._lessons.subject_code(lesson.subject_id),
            start_at=lesson.start_at,
            end_at=lesson.end_at,
            status=lesson.status,
            is_detached=lesson.is_detached,
            video_url_override=lesson.video_url_override,
            board_url_override=lesson.board_url_override,
            topic=lesson.topic,
            completed_at=lesson.completed_at,
            cancelled_at=lesson.cancelled_at,
            cancel_reason=lesson.cancel_reason,
            participants=[
                LessonParticipantItem(
                    student_id=participant.student_id,
                    display_name=name,
                    attendance=participant.attendance,
                )
                for participant, name in rows
            ],
        )
