"""``StaffService``: управление сотрудниками, только для владельца (T2.03, docs/08 §5.3).

Правила:
- любая операция доступна только ``owner``; менеджер и ученик получают 403;
- сотрудником может быть только ``owner`` или ``manager`` (ученика этим сервисом не тронуть: 404);
- смена роли и архивация пишутся в ``audit_log`` и удаляют все сессии сотрудника;
- нельзя понизить или архивировать последнего активного владельца: список активных владельцев
  блокируется ``FOR UPDATE``, поэтому два параллельных запроса не оставят систему без владельца;
- commit выполняет только этот сервис, один публичный метод = одна транзакция.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from src.core import texts
from src.core.current_user import CurrentUser
from src.core.enums import UserRole
from src.core.exceptions import BusinessRuleError, NotFoundError, PermissionDeniedError
from src.core.timeutils import utcnow
from src.db.models import User
from src.repositories.audit_log import AuditLogRepository
from src.repositories.users import UserRepository
from src.schemas.staff import StaffCreate, StaffItem, StaffUpdate
from src.services.auth import AUDIT_ENTITY_USER, STAFF_ROLES, AuthService, IssuedToken

AUDIT_STAFF_CREATED = "staff.created"
AUDIT_STAFF_ROLE_CHANGED = "staff.role_changed"
AUDIT_STAFF_ARCHIVED = "staff.archived"


class StaffService:
    """Сотрудники: создание, список, имя и роль, приглашение, архивация."""

    def __init__(self, session: AsyncSession, auth: AuthService) -> None:
        """Создать сервис.

        Args:
            session: Сессия БД на текущую единицу работы.
            auth: ``AuthService``: приглашения и удаление сессий.
        """
        self._session = session
        self._auth = auth
        self._users = UserRepository(session)
        self._audit = AuditLogRepository(session)

    async def create_staff(self, actor: CurrentUser, data: StaffCreate) -> StaffItem:
        """Создать профиль сотрудника (``manager`` или ``owner``) без Telegram.

        Доступ к приложению сотрудник получает по приглашению (``invite_staff``).

        Raises:
            PermissionDeniedError: Не владелец.
        """
        self._require_owner(actor)
        user = await self._users.add(
            User(role=data.role, display_name=data.display_name, timezone=data.timezone)
        )
        await self._audit_staff(actor.id, AUDIT_STAFF_CREATED, user.id, {"role": data.role.value})
        await self._session.commit()
        return self._item(user)

    async def list_staff(
        self, actor: CurrentUser, *, include_archived: bool = False
    ) -> list[StaffItem]:
        """Список сотрудников по алфавиту имени (по умолчанию без архивных).

        Raises:
            PermissionDeniedError: Не владелец.
        """
        self._require_owner(actor)
        return [
            self._item(user)
            for user in await self._users.list_staff(include_archived=include_archived)
        ]

    async def update_staff(self, actor: CurrentUser, staff_id: int, data: StaffUpdate) -> StaffItem:
        """Изменить имя и/или роль сотрудника.

        Смена роли пишется в ``audit_log`` (было/стало) и удаляет все сессии сотрудника;
        нельзя понизить последнего владельца.

        Raises:
            PermissionDeniedError: Не владелец.
            NotFoundError: Сотрудника нет (ученик сотрудником не является).
            BusinessRuleError: ``last_owner`` — попытка понизить последнего владельца.
        """
        self._require_owner(actor)
        user = await self._load_staff(staff_id)
        fields = data.model_fields_set
        role_changed = False
        if "role" in fields and data.role is not None and data.role != user.role:
            if user.role == UserRole.OWNER and user.is_active:
                await self._ensure_not_last_owner(user.id)
            old_role = user.role
            user.role = data.role
            await self._audit_staff(
                actor.id,
                AUDIT_STAFF_ROLE_CHANGED,
                user.id,
                {"old": old_role.value, "new": data.role.value},
            )
            role_changed = True
        if "display_name" in fields and data.display_name is not None:
            user.display_name = data.display_name
        user.updated_at = utcnow()
        if role_changed:
            # Сначала сессии, потом commit: сбой между шагами не оставит сессий со старой ролью.
            await self._auth.delete_sessions(actor, user.id)
        await self._session.commit()
        return self._item(user)

    async def change_role(self, actor: CurrentUser, staff_id: int, role: UserRole) -> StaffItem:
        """Сменить роль сотрудника (``owner`` ↔ ``manager``); см. ``update_staff``.

        Роль ``student`` отклоняет валидация ``StaffUpdate`` (``pydantic.ValidationError``).
        """
        return await self.update_staff(actor, staff_id, StaffUpdate.model_validate({"role": role}))

    async def invite_staff(self, actor: CurrentUser, staff_id: int) -> IssuedToken:
        """Выпустить приглашение сотруднику (прежние отзываются, TTL 7 дней).

        Raises:
            PermissionDeniedError: Не владелец.
            NotFoundError: Сотрудника нет.
            BusinessRuleError: Сотрудник в архиве.
        """
        self._require_owner(actor)
        await self._load_staff(staff_id)
        return await self._auth.create_invite(actor, staff_id)

    async def archive_staff(self, actor: CurrentUser, staff_id: int) -> StaffItem:
        """Архивировать сотрудника: вход закрыт, все сессии удалены, данные остаются.

        Raises:
            PermissionDeniedError: Не владелец.
            NotFoundError: Сотрудника нет.
            BusinessRuleError: ``staff_already_archived``; ``last_owner`` — последний владелец.
        """
        self._require_owner(actor)
        user = await self._load_staff(staff_id)
        if not user.is_active:
            raise BusinessRuleError(texts.STAFF_ALREADY_ARCHIVED, code="staff_already_archived")
        if user.role == UserRole.OWNER:
            await self._ensure_not_last_owner(user.id)
        now = utcnow()
        user.is_active = False
        user.archived_at = now
        user.updated_at = now
        await self._audit_staff(actor.id, AUDIT_STAFF_ARCHIVED, user.id, {})
        await self._auth.delete_sessions(actor, user.id)
        await self._session.commit()
        return self._item(user)

    # ------------------------------------------------------------------ внутреннее

    @staticmethod
    def _require_owner(actor: CurrentUser) -> None:
        if actor.role != UserRole.OWNER:
            raise PermissionDeniedError()

    async def _load_staff(self, staff_id: int) -> User:
        """Сотрудник (owner/manager) по id; ученик и несуществующий — 404."""
        user = await self._users.get_by_id(staff_id)
        if user is None or user.role not in STAFF_ROLES:
            raise NotFoundError(texts.STAFF_NOT_FOUND, code="staff_not_found")
        return user

    async def _ensure_not_last_owner(self, owner_id: int) -> None:
        """Запретить понижение и архивацию, если ``owner_id`` — единственный активный владелец."""
        if await self._users.lock_active_owner_ids() == [owner_id]:
            raise BusinessRuleError(texts.STAFF_LAST_OWNER, code="last_owner")

    @staticmethod
    def _item(user: User) -> StaffItem:
        return StaffItem(
            user_id=user.id,
            display_name=user.display_name,
            role=user.role,
            timezone=user.timezone,
            is_active=user.is_active,
            bot_blocked=user.bot_blocked,
            telegram_linked=user.telegram_id is not None,
            invite_pending=user.telegram_id is None,
        )

    async def _audit_staff(
        self, actor_id: int, action: str, staff_id: int, data: dict[str, object]
    ) -> None:
        await self._audit.record(
            actor_user_id=actor_id,
            action=action,
            entity_type=AUDIT_ENTITY_USER,
            entity_id=staff_id,
            data=data,
        )
