"""``StudentService``: профили учеников для персонала и «мой профиль» ученика (T2.02, docs/08 §5.2).

Правила:
- создавать, менять, архивировать и смотреть список могут только ``owner`` и ``manager``;
  ученик получает только свою карточку, чужая — 404 (docs/08 §1);
- цену занятия (``lesson_price``) видит и меняет только ``owner``: менеджер получает карточку
  другой схемы (``StudentCardManager``, без цены), а попытка задать цену — 403; смена цены
  пишется в ``audit_log`` (docs/04 §7.2);
- архивация удаляет все сессии ученика, данные остаются;
- commit выполняет только этот сервис, один публичный метод = одна транзакция.
"""

from collections.abc import Sequence
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from src.core import texts
from src.core.constants import LIST_LIMIT_MAX
from src.core.current_user import CurrentUser
from src.core.enums import UserRole
from src.core.exceptions import (
    BusinessRuleError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from src.core.timeutils import utcnow
from src.db.models import StudentProfile, User
from src.repositories.audit_log import AuditLogRepository
from src.repositories.student_profiles import StudentProfileRepository
from src.repositories.subjects import StudentSubjectRepository, SubjectRepository
from src.repositories.users import UserRepository
from src.schemas.students import (
    StudentCardManager,
    StudentCardOwner,
    StudentCreate,
    StudentListItem,
    StudentListPage,
    StudentSelfProfile,
    StudentUpdate,
)
from src.services.auth import AUDIT_ENTITY_USER, STAFF_ROLES, AuthService

AUDIT_STUDENT_CREATED = "student.created"
AUDIT_STUDENT_PRICE_CHANGED = "student.price_changed"
AUDIT_STUDENT_ARCHIVED = "student.archived"
AUDIT_STUDENT_RESTORED = "student.restored"

StudentCard = StudentCardManager | StudentCardOwner


class StudentStatus(StrEnum):
    """Фильтр списка: ``status=active|archived`` (docs/08 §5.2)."""

    ACTIVE = "active"
    ARCHIVED = "archived"


class StudentService:
    """Профили учеников (создание, правка, архив, список, карточка)."""

    def __init__(self, session: AsyncSession, auth: AuthService) -> None:
        """Создать сервис.

        Args:
            session: Сессия БД на текущую единицу работы.
            auth: ``AuthService``: удаление сессий и отвязка Telegram.
        """
        self._session = session
        self._auth = auth
        self._users = UserRepository(session)
        self._profiles = StudentProfileRepository(session)
        self._subjects = SubjectRepository(session)
        self._student_subjects = StudentSubjectRepository(session)
        self._audit = AuditLogRepository(session)

    # ------------------------------------------------------------------ создание и правка

    async def create_student(self, actor: CurrentUser, data: StudentCreate) -> StudentCard:
        """Создать профиль ученика (без Telegram: он ждёт приглашения).

        Args:
            actor: Сотрудник (``owner`` или ``manager``).
            data: Поля профиля; ``lesson_price`` допустим только для владельца.

        Returns:
            Карточка по роли сотрудника (у менеджера без цены).

        Raises:
            PermissionDeniedError: Не сотрудник, либо менеджер задал цену.
            ValidationError: Неизвестный предмет или недопустимый ведущий преподаватель.
        """
        self._require_staff(actor)
        if data.lesson_price is not None and actor.role != UserRole.OWNER:
            raise PermissionDeniedError(texts.STUDENT_PRICE_OWNER_ONLY)
        teacher_id = await self._resolve_teacher(actor, data.teacher_id)
        subject_ids = await self._resolve_subjects(data.subject_codes)

        user = await self._users.add(
            User(role=UserRole.STUDENT, display_name=data.display_name, timezone=data.timezone)
        )
        profile = await self._profiles.add(
            StudentProfile(
                user_id=user.id,
                teacher_id=teacher_id,
                school_class=data.school_class,
                lesson_price=data.lesson_price or 0,
                video_url=data.video_url,
                board_url=data.board_url,
                teacher_notes=data.teacher_notes,
            )
        )
        await self._student_subjects.replace(user.id, subject_ids)
        await self._audit_student(
            actor.id, AUDIT_STUDENT_CREATED, user.id, {"teacher_id": teacher_id}
        )
        await self._session.commit()
        return self._card(actor, user, profile, await self._codes(user.id))

    async def update_student(
        self, actor: CurrentUser, student_id: int, data: StudentUpdate
    ) -> StudentCard:
        """Изменить переданные поля профиля ученика.

        Изменение цены разрешено только владельцу и пишется в ``audit_log`` (было/стало).

        Raises:
            PermissionDeniedError: Не сотрудник, либо менеджер пытается менять цену.
            NotFoundError: Ученика нет.
            ValidationError: Неизвестный предмет или недопустимый ведущий преподаватель.
        """
        self._require_staff(actor)
        fields = data.model_fields_set
        if "lesson_price" in fields and actor.role != UserRole.OWNER:
            raise PermissionDeniedError(texts.STUDENT_PRICE_OWNER_ONLY)
        user, profile = await self._load_student(student_id)

        subject_ids = None
        if "subject_codes" in fields and data.subject_codes is not None:
            subject_ids = await self._resolve_subjects(data.subject_codes)
        if "teacher_id" in fields and data.teacher_id is not None:
            profile.teacher_id = await self._resolve_teacher(actor, data.teacher_id)

        if "display_name" in fields and data.display_name is not None:
            user.display_name = data.display_name
        if "timezone" in fields and data.timezone is not None:
            user.timezone = data.timezone
        for name in ("school_class", "video_url", "board_url", "teacher_notes"):
            if name in fields:
                setattr(profile, name, getattr(data, name))
        if "lesson_price" in fields and data.lesson_price is not None:
            old_price = profile.lesson_price
            if data.lesson_price != old_price:
                profile.lesson_price = data.lesson_price
                await self._audit_student(
                    actor.id,
                    AUDIT_STUDENT_PRICE_CHANGED,
                    user.id,
                    {"old": old_price, "new": data.lesson_price},
                )
        if subject_ids is not None:
            await self._student_subjects.replace(user.id, subject_ids)

        now = utcnow()
        user.updated_at = now
        profile.updated_at = now
        await self._session.commit()
        return self._card(actor, user, profile, await self._codes(user.id))

    # ------------------------------------------------------------------ архив

    async def archive_student(self, actor: CurrentUser, student_id: int) -> StudentCard:
        """Перенести ученика в архив: вход закрыт, все его сессии удалены, данные остаются.

        Raises:
            PermissionDeniedError: Не сотрудник.
            NotFoundError: Ученика нет.
            BusinessRuleError: ``student_already_archived``.
        """
        self._require_staff(actor)
        user, profile = await self._load_student(student_id)
        if not user.is_active:
            raise BusinessRuleError(texts.STUDENT_ALREADY_ARCHIVED, code="student_already_archived")
        now = utcnow()
        user.is_active = False
        user.archived_at = now
        user.updated_at = now
        await self._audit_student(actor.id, AUDIT_STUDENT_ARCHIVED, user.id, {})
        # Сначала сессии, потом commit: сбой между шагами не оставит живых сессий архивного ученика.
        await self._auth.delete_sessions(actor, user.id)
        await self._session.commit()
        return self._card(actor, user, profile, await self._codes(user.id))

    async def restore_student(self, actor: CurrentUser, student_id: int) -> StudentCard:
        """Вернуть ученика из архива (Telegram-привязка сохраняется, сессии не восстанавливаются).

        Raises:
            PermissionDeniedError: Не сотрудник.
            NotFoundError: Ученика нет.
            BusinessRuleError: ``student_not_archived``.
        """
        self._require_staff(actor)
        user, profile = await self._load_student(student_id)
        if user.is_active:
            raise BusinessRuleError(texts.STUDENT_NOT_ARCHIVED, code="student_not_archived")
        user.is_active = True
        user.archived_at = None
        user.updated_at = utcnow()
        await self._audit_student(actor.id, AUDIT_STUDENT_RESTORED, user.id, {})
        await self._session.commit()
        return self._card(actor, user, profile, await self._codes(user.id))

    # ------------------------------------------------------------------ чтение

    async def list_students(
        self,
        actor: CurrentUser,
        *,
        status: StudentStatus = StudentStatus.ACTIVE,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> StudentListPage:
        """Список учеников: фильтр active/archived, поиск ``q`` по имени, пагинация.

        В строке есть признаки «бот заблокирован» и «приглашение не принято»
        (``invite_pending``: Telegram ещё не привязан); цены в списке нет.

        Raises:
            PermissionDeniedError: Не сотрудник.
            ValidationError: Неверные ``limit`` или ``offset``.
        """
        self._require_staff(actor)
        if not 1 <= limit <= LIST_LIMIT_MAX or offset < 0:
            raise ValidationError(texts.LIST_PARAMS_INVALID, code="invalid_list_params")
        query = q.strip() if q else None
        rows, total = await self._profiles.search(
            is_active=status == StudentStatus.ACTIVE, q=query or None, limit=limit, offset=offset
        )
        codes = await self._student_subjects.codes_for([user.id for user, _ in rows])
        items = [
            StudentListItem(
                user_id=user.id,
                display_name=user.display_name,
                school_class=profile.school_class,
                is_active=user.is_active,
                bot_blocked=user.bot_blocked,
                telegram_linked=user.telegram_id is not None,
                invite_pending=user.telegram_id is None,
                subjects=codes[user.id],
            )
            for user, profile in rows
        ]
        return StudentListPage(items=items, total=total, limit=limit, offset=offset)

    async def get_student_card(
        self, actor: CurrentUser, student_id: int
    ) -> StudentSelfProfile | StudentCard:
        """Карточка ученика; схема зависит от роли (docs/08 §8).

        Ученик получает только свою (``StudentSelfProfile``), чужая — 404 (не раскрываем
        существование). Менеджер — без цены, владелец — с ценой.

        Raises:
            NotFoundError: Ученика нет (либо ученик запросил чужую карточку).
            PermissionDeniedError: Нет прав.
        """
        if actor.role == UserRole.STUDENT:
            if actor.id != student_id:
                raise NotFoundError(texts.STUDENT_NOT_FOUND)
            user, profile = await self._load_student(student_id)
            return StudentSelfProfile(
                user_id=user.id,
                display_name=user.display_name,
                timezone=user.timezone,
                school_class=profile.school_class,
                video_url=profile.video_url,
                board_url=profile.board_url,
                subjects=await self._codes(user.id),
            )
        self._require_staff(actor)
        user, profile = await self._load_student(student_id)
        return self._card(actor, user, profile, await self._codes(user.id))

    # ------------------------------------------------------------------ Telegram

    async def unlink_telegram(self, actor: CurrentUser, student_id: int) -> None:
        """Снять привязку Telegram ученика (сессии удаляются, запись в ``audit_log``).

        Raises:
            PermissionDeniedError: Не сотрудник.
            NotFoundError: Ученика нет.
            BusinessRuleError: Telegram не привязан.
        """
        self._require_staff(actor)
        await self._load_student(student_id)
        await self._auth.unlink_telegram(actor, student_id)

    # ------------------------------------------------------------------ внутреннее

    @staticmethod
    def _require_staff(actor: CurrentUser) -> None:
        if actor.role not in STAFF_ROLES:
            raise PermissionDeniedError()

    async def _load_student(self, student_id: int) -> tuple[User, StudentProfile]:
        """Пользователь-ученик с профилем; иначе 404."""
        user = await self._users.get_by_id(student_id, with_profile=True)
        if user is None or user.role != UserRole.STUDENT or user.student_profile is None:
            raise NotFoundError(texts.STUDENT_NOT_FOUND)
        return user, user.student_profile

    async def _codes(self, student_id: int) -> list[str]:
        return (await self._student_subjects.codes_for([student_id]))[student_id]

    async def _resolve_subjects(self, codes: Sequence[str]) -> list[int]:
        """``subjects.id`` по кодам; неизвестный или неактивный предмет — ошибка."""
        wanted = set(codes)
        found = await self._subjects.active_by_codes(wanted)
        missing = sorted(wanted - {subject.code for subject in found})
        if missing:
            raise ValidationError(
                texts.STUDENT_UNKNOWN_SUBJECT,
                code="unknown_subject",
                details={"codes": missing},
            )
        return [subject.id for subject in found]

    async def _resolve_teacher(self, actor: CurrentUser, teacher_id: int | None) -> int:
        """Ведущий преподаватель: по умолчанию сам сотрудник; иначе активный owner/manager."""
        if teacher_id is None or teacher_id == actor.id:
            return actor.id
        teacher = await self._users.get_by_id(teacher_id)
        if teacher is None or not teacher.is_active or teacher.role not in STAFF_ROLES:
            raise ValidationError(texts.STUDENT_INVALID_TEACHER, code="invalid_teacher")
        return teacher.id

    @staticmethod
    def _card(
        actor: CurrentUser, user: User, profile: StudentProfile, subjects: list[str]
    ) -> StudentCard:
        """Карточка по роли: владелец — с ценой, менеджер — без неё."""
        common = {
            "user_id": user.id,
            "display_name": user.display_name,
            "timezone": user.timezone,
            "is_active": user.is_active,
            "bot_blocked": user.bot_blocked,
            "telegram_linked": user.telegram_id is not None,
            "teacher_id": profile.teacher_id,
            "school_class": profile.school_class,
            "video_url": profile.video_url,
            "board_url": profile.board_url,
            "teacher_notes": profile.teacher_notes,
            "subjects": subjects,
        }
        if actor.role == UserRole.OWNER:
            return StudentCardOwner(**common, lesson_price=profile.lesson_price)
        return StudentCardManager(**common)

    async def _audit_student(
        self, actor_id: int, action: str, student_id: int, data: dict[str, object]
    ) -> None:
        await self._audit.record(
            actor_user_id=actor_id,
            action=action,
            entity_type=AUDIT_ENTITY_USER,
            entity_id=student_id,
            data=data,
        )
