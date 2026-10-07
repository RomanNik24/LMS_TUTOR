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
from datetime import date, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core import texts
from src.core.constants import (
    LIST_LIMIT_DEFAULT,
    LIST_LIMIT_MAX,
    SCHEDULE_HORIZON_WEEKS_DEFAULT,
)
from src.core.current_user import CurrentUser
from src.core.enums import AttendanceStatus, LessonStatus, UserRole
from src.core.exceptions import (
    BusinessRuleError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from src.core.timeutils import day_bounds_utc, local_date_of, utcnow, weekly_starts_utc
from src.db.models import Lesson, ScheduleTemplate, User
from src.repositories.audit_log import AuditLogRepository
from src.repositories.lessons import LessonRepository
from src.repositories.schedule_templates import ScheduleTemplateRepository
from src.repositories.student_profiles import StudentProfileRepository
from src.repositories.subjects import SubjectRepository
from src.repositories.users import UserRepository
from src.schemas.schedule import (
    HORIZON_WEEKS_MAX,
    PERIOD_MAX_DAYS,
    GenerationResult,
    LessonCancel,
    LessonComplete,
    LessonCreate,
    LessonItem,
    LessonListPage,
    LessonParticipantItem,
    LessonReschedule,
    LessonUpdate,
    StudentLessonItem,
    TemplateCreate,
    TemplateItem,
    TemplateUpdate,
)
from src.services.auth import STAFF_ROLES

AUDIT_LESSON_CREATED = "lesson.created"
AUDIT_LESSON_RESCHEDULED = "lesson.rescheduled"
AUDIT_LESSON_CANCELLED = "lesson.cancelled"
AUDIT_LESSON_COMPLETED = "lesson.completed"
AUDIT_LESSON_UPDATED = "lesson.updated"
AUDIT_TEMPLATE_CREATED = "schedule_template.created"
AUDIT_TEMPLATE_UPDATED = "schedule_template.updated"
AUDIT_TEMPLATE_DEACTIVATED = "schedule_template.deactivated"
AUDIT_LESSONS_GENERATED = "lessons.generated"
AUDIT_ENTITY_TEMPLATE = "schedule_template"
AUDIT_ENTITY_LESSON = "lesson"
OVERLAP_CONSTRAINT = "ex_lessons_teacher_no_overlap"


class ScheduleService:
    """Расписание: создание урока с защитой от пересечений."""

    def __init__(
        self, session: AsyncSession, horizon_weeks: int = SCHEDULE_HORIZON_WEEKS_DEFAULT
    ) -> None:
        """Создать сервис.

        Args:
            session: Сессия БД на текущую единицу работы.
            horizon_weeks: Горизонт генерации, недель (``SCHEDULE_HORIZON_WEEKS``).
        """
        self._session = session
        self._horizon_weeks = horizon_weeks
        self._templates = ScheduleTemplateRepository(session)
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

    async def list_lessons(
        self,
        actor: CurrentUser,
        *,
        start: datetime,
        end: datetime,
        student_id: int | None = None,
        teacher_id: int | None = None,
        status: LessonStatus | None = None,
        limit: int = LIST_LIMIT_DEFAULT,
        offset: int = 0,
    ) -> LessonListPage:
        """Уроки с началом в ``[start, end)`` для сотрудников; период не больше года.

        Raises:
            PermissionDeniedError: Не сотрудник.
            ValidationError: ``invalid_period`` или ``invalid_list_params``.
        """
        self._require_staff(actor)
        self._check_period(start, end)
        if not 1 <= limit <= LIST_LIMIT_MAX or offset < 0:
            raise ValidationError(texts.LIST_PARAMS_INVALID, code="invalid_list_params")
        lessons, total = await self._lessons.list_in_period(
            start,
            end,
            student_id=student_id,
            teacher_id=teacher_id,
            status=status,
            limit=limit,
            offset=offset,
        )
        return LessonListPage(
            items=await self._build_items(lessons), total=total, limit=limit, offset=offset
        )

    async def get_lesson(self, actor: CurrentUser, lesson_id: int) -> LessonItem:
        """Детали урока для сотрудников.

        Raises:
            PermissionDeniedError: Не сотрудник.
            NotFoundError: ``lesson_not_found``.
        """
        self._require_staff(actor)
        lesson = await self._lessons.get_by_id(lesson_id)
        if lesson is None:
            raise NotFoundError(texts.LESSON_NOT_FOUND, code="lesson_not_found")
        return await self._build_item(lesson)

    async def update_lesson(
        self, actor: CurrentUser, lesson_id: int, data: LessonUpdate
    ) -> LessonItem:
        """Изменить тему, заметку, ссылки и/или участников урока.

        Урок из шаблона после правки получает ``is_detached = true``: правка шаблона его не
        затрагивает. Участников можно менять только у запланированного урока.

        Raises:
            PermissionDeniedError: Не сотрудник.
            NotFoundError: ``lesson_not_found`` или участник не найден.
            BusinessRuleError: ``lesson_not_scheduled`` (участники проведённого/отменённого
                урока) или ``student_archived``.
        """
        self._require_staff(actor)
        lesson = await self._lessons.get_by_id(lesson_id, for_update=True)
        if lesson is None:
            raise NotFoundError(texts.LESSON_NOT_FOUND, code="lesson_not_found")
        fields = data.model_fields_set
        if "student_ids" in fields and data.student_ids is not None:
            if lesson.status != LessonStatus.SCHEDULED:
                raise BusinessRuleError(texts.LESSON_NOT_SCHEDULED, code="lesson_not_scheduled")
            current = set(await self._lessons.participant_ids(lesson.id))
            wanted = list(dict.fromkeys(data.student_ids))
            added = [sid for sid in wanted if sid not in current]
            await self._resolve_students(added)
            await self._lessons.remove_participants(lesson.id, sorted(current - set(wanted)))
            await self._lessons.add_participants(lesson.id, added)
        for name in ("topic", "teacher_note", "video_url_override", "board_url_override"):
            if name in fields:
                setattr(lesson, name, getattr(data, name))
        if lesson.template_id is not None:
            lesson.is_detached = True
        lesson.updated_at = utcnow()
        await self._audit.record(
            actor_user_id=actor.id,
            action=AUDIT_LESSON_UPDATED,
            entity_type=AUDIT_ENTITY_LESSON,
            entity_id=lesson.id,
            data={"fields": sorted(fields)},
        )
        await self._session.commit()
        return await self._build_item(lesson)

    # ------------------------------------------------------------------ уроки ученика

    async def list_student_lessons(
        self, actor: CurrentUser, *, start: datetime, end: datetime
    ) -> list[StudentLessonItem]:
        """Уроки самого ученика с началом в ``[start, end)``; период не больше года.

        Raises:
            PermissionDeniedError: Не ученик.
            ValidationError: ``invalid_period``.
        """
        self._require_student(actor)
        self._check_period(start, end)
        lessons = await self._lessons.list_for_student(actor.id, start, end)
        return await self._student_items(actor.id, lessons)

    async def get_student_lesson(self, actor: CurrentUser, lesson_id: int) -> StudentLessonItem:
        """Карточка урока ученика; чужой или несуществующий урок — одинаково 404.

        Raises:
            PermissionDeniedError: Не ученик.
            NotFoundError: ``lesson_not_found``.
        """
        self._require_student(actor)
        lesson = await self._lessons.get_for_student(lesson_id, actor.id)
        if lesson is None:
            raise NotFoundError(texts.LESSON_NOT_FOUND, code="lesson_not_found")
        return (await self._student_items(actor.id, [lesson]))[0]

    async def _student_items(
        self, student_id: int, lessons: list[Lesson]
    ) -> list[StudentLessonItem]:
        """Уроки ученика: ссылки «урок → профиль», только число участников."""
        profile = await self._profiles.get_by_user_id(student_id)
        counts = await self._lessons.participant_counts([lesson.id for lesson in lessons])
        codes = await self._lessons.subject_codes(sorted({lesson.subject_id for lesson in lessons}))
        return [
            StudentLessonItem(
                id=lesson.id,
                subject_code=codes[lesson.subject_id],
                start_at=lesson.start_at,
                end_at=lesson.end_at,
                status=lesson.status,
                topic=lesson.topic,
                video_url=lesson.video_url_override or (profile.video_url if profile else None),
                board_url=lesson.board_url_override or (profile.board_url if profile else None),
                participants_count=counts.get(lesson.id, 0),
            )
            for lesson in lessons
        ]

    async def student_upcoming(
        self, actor: CurrentUser, *, hours: int = 24
    ) -> list[StudentLessonItem]:
        """Запланированные уроки ученика в ближайшие ``hours`` часов (для ``/today`` в боте).

        Raises:
            PermissionDeniedError: Не ученик.
        """
        self._require_student(actor)
        now = utcnow()
        lessons = await self._lessons.list_for_student(actor.id, now, now + timedelta(hours=hours))
        scheduled = [lesson for lesson in lessons if lesson.status == LessonStatus.SCHEDULED]
        return await self._student_items(actor.id, scheduled)

    async def staff_today(self, actor: CurrentUser) -> tuple[date, list[LessonItem]]:
        """Все уроки «сегодня» в поясе сотрудника (для ``/today`` в боте).

        Returns:
            Местная дата и уроки этих суток по времени начала.

        Raises:
            PermissionDeniedError: Не сотрудник.
        """
        self._require_staff(actor)
        today = local_date_of(utcnow(), actor.timezone)
        start, end = day_bounds_utc(today, actor.timezone)
        lessons, _ = await self._lessons.list_in_period(
            start,
            end,
            student_id=None,
            teacher_id=None,
            status=None,
            limit=LIST_LIMIT_MAX,
            offset=0,
        )
        return today, await self._build_items(lessons)

    @staticmethod
    def _require_student(actor: CurrentUser) -> None:
        if actor.role != UserRole.STUDENT:
            raise PermissionDeniedError()

    # ------------------------------------------------------------------ шаблоны (T3.06)

    async def create_template(self, actor: CurrentUser, data: TemplateCreate) -> TemplateItem:
        """Создать шаблон «каждую неделю» и сразу сгенерировать уроки на горизонт.

        Raises:
            PermissionDeniedError: Не сотрудник.
            ValidationError: Неизвестный предмет или недопустимый преподаватель.
            NotFoundError / BusinessRuleError: Участник не найден или в архиве.
        """
        self._require_staff(actor)
        teacher_id = await self._resolve_teacher(actor, data.teacher_id)
        subject_id = await self._resolve_subject(data.subject_code)
        await self._resolve_students(data.student_ids)
        template = await self._templates.add(
            ScheduleTemplate(
                teacher_id=teacher_id,
                subject_id=subject_id,
                weekday=data.weekday,
                start_local_time=data.start_local_time,
                duration_minutes=data.duration_minutes,
                timezone=data.timezone,
                starts_on=data.starts_on,
                ends_on=data.ends_on,
            )
        )
        await self._templates.replace_participants(template.id, data.student_ids)
        created, skipped = await self._generate(template, utcnow(), self._horizon_weeks)
        await self._audit.record(
            actor_user_id=actor.id,
            action=AUDIT_TEMPLATE_CREATED,
            entity_type=AUDIT_ENTITY_TEMPLATE,
            entity_id=template.id,
            data={"created": created, "skipped": skipped},
        )
        await self._session.commit()
        return await self._template_item(template, data.subject_code)

    async def list_templates(self, actor: CurrentUser) -> list[TemplateItem]:
        """Все шаблоны по возрастанию id (включая отключённые)."""
        self._require_staff(actor)
        return [
            await self._template_item(
                template, await self._lessons.subject_code(template.subject_id)
            )
            for template in await self._templates.list_all()
        ]

    async def update_template(
        self, actor: CurrentUser, template_id: int, data: TemplateUpdate
    ) -> TemplateItem:
        """Изменить шаблон; затрагивает ТОЛЬКО будущие неизменённые уроки.

        Будущие запланированные уроки шаблона с ``is_detached = false`` удаляются и создаются
        заново по новым правилам. Изменённые вручную (``is_detached``), проведённые, отменённые
        и прошедшие уроки не трогаются; даты, где у шаблона уже есть урок (в т. ч. отменённый
        или перенесённый внутри суток), заново не создаются.

        Raises:
            PermissionDeniedError: Не сотрудник.
            NotFoundError: ``template_not_found``.
            ValidationError: ``ends_on`` раньше ``starts_on``.
            NotFoundError / BusinessRuleError: Новый участник не найден или в архиве.
        """
        self._require_staff(actor)
        template = await self._load_template(template_id)
        fields = data.model_fields_set
        if "student_ids" in fields and data.student_ids is not None:
            await self._resolve_students(data.student_ids)
            await self._templates.replace_participants(template.id, data.student_ids)
        for name in ("weekday", "start_local_time", "duration_minutes", "timezone", "starts_on"):
            value = getattr(data, name)
            if name in fields and value is not None:
                setattr(template, name, value)
        if "ends_on" in fields:
            template.ends_on = data.ends_on
        if "is_active" in fields and data.is_active is not None:
            template.is_active = data.is_active
        if template.ends_on is not None and template.ends_on < template.starts_on:
            raise ValidationError(texts.TEMPLATE_ENDS_BEFORE_START, code="invalid_period")
        template.updated_at = utcnow()
        removed, created, skipped = await self._regenerate(template)
        await self._audit.record(
            actor_user_id=actor.id,
            action=AUDIT_TEMPLATE_UPDATED,
            entity_type=AUDIT_ENTITY_TEMPLATE,
            entity_id=template.id,
            data={"removed": removed, "created": created, "skipped": skipped},
        )
        await self._session.commit()
        return await self._template_item(
            template, await self._lessons.subject_code(template.subject_id)
        )

    async def deactivate_template(self, actor: CurrentUser, template_id: int) -> TemplateItem:
        """Отключить шаблон: новые уроки не создаются, будущие неизменённые уроки удаляются."""
        self._require_staff(actor)
        template = await self._load_template(template_id)
        template.is_active = False
        template.updated_at = utcnow()
        removed, _, _ = await self._regenerate(template)
        await self._audit.record(
            actor_user_id=actor.id,
            action=AUDIT_TEMPLATE_DEACTIVATED,
            entity_type=AUDIT_ENTITY_TEMPLATE,
            entity_id=template.id,
            data={"removed": removed},
        )
        await self._session.commit()
        return await self._template_item(
            template, await self._lessons.subject_code(template.subject_id)
        )

    async def generate_lessons(
        self, actor: CurrentUser | None = None, horizon_weeks: int | None = None
    ) -> GenerationResult:
        """Дозаполнить уроки по всем включённым шаблонам на горизонт (идемпотентно).

        ``actor = None`` — вызов воркера (ежедневно в 03:00); с ``actor`` — ручной запуск
        сотрудником. Повторный запуск не создаёт дублей; занятое время пропускается.

        Raises:
            PermissionDeniedError: ``actor`` не сотрудник.
            ValidationError: Горизонт вне 1..52 недель.
        """
        if actor is not None:
            self._require_staff(actor)
        weeks = self._horizon_weeks if horizon_weeks is None else horizon_weeks
        if not 1 <= weeks <= HORIZON_WEEKS_MAX:
            raise ValidationError(texts.TEMPLATE_HORIZON_INVALID, code="invalid_horizon")
        now = utcnow()
        templates = await self._templates.list_all(only_active=True)
        total_created = total_skipped = 0
        for template in templates:
            created, skipped = await self._generate(template, now, weeks)
            total_created += created
            total_skipped += skipped
        await self._audit.record(
            actor_user_id=None if actor is None else actor.id,
            action=AUDIT_LESSONS_GENERATED,
            entity_type=AUDIT_ENTITY_TEMPLATE,
            entity_id=None,
            data={"templates": len(templates), "created": total_created, "skipped": total_skipped},
        )
        await self._session.commit()
        return GenerationResult(
            templates=len(templates), created=total_created, skipped=total_skipped
        )

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
        return (await self._build_items([lesson]))[0]

    async def _build_items(self, lessons: list[Lesson]) -> list[LessonItem]:
        """Ответы для сотрудников по нескольким урокам (участники и предметы — пачкой)."""
        participants = await self._lessons.participants_for([lesson.id for lesson in lessons])
        codes = await self._lessons.subject_codes(sorted({lesson.subject_id for lesson in lessons}))
        return [
            LessonItem(
                id=lesson.id,
                teacher_id=lesson.teacher_id,
                subject_code=codes[lesson.subject_id],
                start_at=lesson.start_at,
                end_at=lesson.end_at,
                status=lesson.status,
                is_detached=lesson.is_detached,
                video_url_override=lesson.video_url_override,
                board_url_override=lesson.board_url_override,
                topic=lesson.topic,
                teacher_note=lesson.teacher_note,
                completed_at=lesson.completed_at,
                cancelled_at=lesson.cancelled_at,
                cancel_reason=lesson.cancel_reason,
                participants=[
                    LessonParticipantItem(
                        student_id=participant.student_id,
                        display_name=name,
                        attendance=participant.attendance,
                    )
                    for participant, name in participants.get(lesson.id, [])
                ],
            )
            for lesson in lessons
        ]

    @staticmethod
    def _check_period(start: datetime, end: datetime) -> None:
        """Период фильтра: конец позже начала и не больше года."""
        if end <= start or end - start > timedelta(days=PERIOD_MAX_DAYS):
            raise ValidationError(texts.LESSON_PERIOD_INVALID, code="invalid_period")

    # ------------------------------------------------------------------ генерация уроков

    async def _load_template(self, template_id: int) -> ScheduleTemplate:
        template = await self._templates.get_by_id(template_id, for_update=True)
        if template is None:
            raise NotFoundError(texts.TEMPLATE_NOT_FOUND, code="template_not_found")
        return template

    async def _template_item(self, template: ScheduleTemplate, subject_code: str) -> TemplateItem:
        return TemplateItem(
            id=template.id,
            teacher_id=template.teacher_id,
            subject_code=subject_code,
            student_ids=await self._templates.student_ids(template.id),
            weekday=template.weekday,
            start_local_time=template.start_local_time,
            duration_minutes=template.duration_minutes,
            timezone=template.timezone,
            starts_on=template.starts_on,
            ends_on=template.ends_on,
            is_active=template.is_active,
            generated_until=template.generated_until,
        )

    async def _regenerate(self, template: ScheduleTemplate) -> tuple[int, int, int]:
        """Убрать будущие неизменённые уроки шаблона и создать их заново (если включён).

        Returns:
            ``(удалено, создано, пропущено)``.
        """
        now = utcnow()
        removed = await self._lessons.delete_future_generated(template.id, now)
        template.generated_until = None
        if not template.is_active:
            return removed, 0, 0
        created, skipped = await self._generate(
            template, now, self._horizon_weeks, skip_existing_dates=True
        )
        return removed, created, skipped

    async def _generate(
        self,
        template: ScheduleTemplate,
        now: datetime,
        horizon_weeks: int,
        *,
        skip_existing_dates: bool = False,
    ) -> tuple[int, int]:
        """Создать уроки шаблона на горизонт; вернуть ``(создано, пропущено)``.

        Окно: от «сегодня» (в поясе шаблона) или ``starts_on`` до горизонта или ``ends_on``;
        при обычном запуске — только после ``generated_until``, чтобы перенесённый или
        отменённый урок не возвращался на своё прежнее место. Прошедшее время не создаётся.
        """
        today = local_date_of(now, template.timezone)
        upper = today + timedelta(weeks=horizon_weeks)
        if template.ends_on is not None:
            upper = min(upper, template.ends_on)
        lower = max(template.starts_on, today)
        if template.generated_until is not None:
            lower = max(lower, template.generated_until + timedelta(days=1))
        if lower > upper:
            return 0, 0
        student_ids = await self._active_student_ids(template.id)
        if not student_ids:
            return 0, 0
        taken: set[date] = (
            await self._lessons.local_dates_of_template(template.id, template.timezone)
            if skip_existing_dates
            else set()
        )
        starts = [
            start
            for start in weekly_starts_utc(
                template.weekday, template.start_local_time, template.timezone, lower, upper
            )
            if start > now and local_date_of(start, template.timezone) not in taken
        ]
        duration = timedelta(minutes=template.duration_minutes)
        created = await self._lessons.insert_generated(
            [
                {
                    "teacher_id": template.teacher_id,
                    "subject_id": template.subject_id,
                    "start_at": start,
                    "end_at": start + duration,
                    "template_id": template.id,
                }
                for start in starts
            ]
        )
        await self._lessons.add_participants_bulk(
            [(lesson_id, sid) for lesson_id, _ in created for sid in student_ids]
        )
        template.generated_until = max(template.generated_until or upper, upper)
        template.updated_at = utcnow()
        await self._session.flush()
        return len(created), len(starts) - len(created)

    async def _active_student_ids(self, template_id: int) -> list[int]:
        """Участники шаблона, которые существуют и не в архиве (архивных не приглашаем)."""
        ids = await self._templates.student_ids(template_id)
        users = await self._users.list_by_ids(ids)
        return [u.id for u in users if u.role == UserRole.STUDENT and u.is_active]
