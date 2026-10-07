"""``AuthService``: приглашения, ссылки входа, перепривязка, владелец (задача T1.09).

Реализует US-01 (docs/01), docs/04 §2.5 и §7.2, docs/05 §3, docs/09 §2.
Правила:
- токены хранятся только как SHA-256 хэш, одноразовые, с TTL;
- одноразовое погашение защищено блокировкой строки (``FOR UPDATE``);
- commit выполняет только сервис (один публичный метод = одна транзакция);
- чувствительные действия пишутся в ``audit_log`` (docs/04 §7.2) без токенов и
  персональных данных;
- сервис не зависит от веб-фреймворка и библиотеки Telegram-бота (docs/03 §4).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from sqlalchemy.ext.asyncio import AsyncSession

from src.core import texts
from src.core.constants import (
    INVITE_FAILED_ATTEMPTS_LIMIT,
    INVITE_FAILED_ATTEMPTS_WINDOW_SECONDS,
    INVITE_FAILURE_SCOPE,
    INVITE_TTL_DAYS,
    WEB_LOGIN_TTL_MINUTES,
)
from src.core.current_user import CurrentUser
from src.core.enums import AuthTokenPurpose, UserRole
from src.core.exceptions import (
    AppError,
    BusinessRuleError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
)
from src.core.rate_limit import RateLimiter
from src.core.security import TelegramUser, hash_token, new_token, validate_init_data
from src.core.session_store import SessionStore
from src.core.timeutils import utcnow
from src.db.models import AuthToken, User
from src.repositories.audit_log import AuditLogRepository
from src.repositories.auth_tokens import AuthTokenRepository
from src.repositories.users import UserRepository
from src.services.notification_events import NotificationEvents

STAFF_ROLES = frozenset({UserRole.OWNER, UserRole.MANAGER})
OWNER_DISPLAY_NAME = texts.OWNER_DISPLAY_NAME

AUDIT_INVITE_CREATED = "invite.created"
AUDIT_INVITE_REVOKED = "invite.revoked"
AUDIT_INVITE_ACCEPTED = "invite.accepted"
AUDIT_TELEGRAM_RELINKED = "telegram.relinked"
AUDIT_TELEGRAM_UNLINKED = "telegram.unlinked"
AUDIT_ENTITY_USER = "user"


class InviteAcceptStatus(StrEnum):
    """Итог принятия приглашения."""

    LINKED = "linked"
    RELINK_REQUIRED = "relink_required"


@dataclass(frozen=True)
class IssuedToken:
    """Только что выпущенный токен (показывается один раз, в БД его нет).

    Attributes:
        id: ``auth_tokens.id`` (по нему приглашение отзывают, ``DELETE /admin/invitations/{id}``).
        token: Токен для ссылки.
        expires_at: Момент истечения (UTC).
    """

    id: int
    token: str
    expires_at: datetime


@dataclass(frozen=True)
class InviteAcceptResult:
    """Результат ``accept_invite`` / ``confirm_relink``.

    Attributes:
        status: ``linked`` — привязано; ``relink_required`` — нужно подтверждение.
        user_id: Профиль, к которому относится приглашение.
        role: Роль профиля (для меню бота).
        display_name: Имя для приветствия.
    """

    status: InviteAcceptStatus
    user_id: int
    role: UserRole
    display_name: str


def _invalid_invite() -> AppError:
    return NotFoundError(texts.INVITE_INVALID, code="invite_invalid")


class AuthService:
    """Сервис аутентификации и привязки Telegram."""

    def __init__(
        self,
        session: AsyncSession,
        sessions: SessionStore,
        limiter: RateLimiter,
        bot_token: str = "",
    ) -> None:
        """Создать сервис.

        Args:
            session: Сессия БД на текущую единицу работы.
            sessions: Хранилище серверных сессий (Redis).
            limiter: Ограничитель неудачных попыток (Redis).
            bot_token: Токен бота для проверки ``initData``.
        """
        self._session = session
        self._sessions = sessions
        self._limiter = limiter
        self._bot_token = bot_token
        self._users = UserRepository(session)
        self._tokens = AuthTokenRepository(session)
        self._audit = AuditLogRepository(session)

    # ------------------------------------------------------------------ приглашения

    async def create_invite(self, actor: CurrentUser, user_id: int) -> IssuedToken:
        """Выпустить приглашение; прежние активные приглашения отзываются.

        Args:
            actor: Кто выпускает (персонал; сотрудников приглашает только владелец).
            user_id: Для кого приглашение (профиль ученика или сотрудника).

        Returns:
            Токен и срок его действия (7 дней).

        Raises:
            PermissionDeniedError: Нет прав.
            NotFoundError: Пользователь не найден.
            BusinessRuleError: Пользователь в архиве.
        """
        target = await self._require_manageable_target(actor, user_id)
        now = utcnow()
        revoked = await self._revoke_active(target.id, AuthTokenPurpose.INVITE, now)
        token = new_token()
        expires_at = now + timedelta(days=INVITE_TTL_DAYS)
        record = await self._tokens.add(
            AuthToken(
                purpose=AuthTokenPurpose.INVITE,
                user_id=target.id,
                token_hash=hash_token(token),
                created_by=actor.id,
                expires_at=expires_at,
            )
        )
        await self._audit_user(
            actor.id, AUDIT_INVITE_CREATED, target.id, {"revoked_previous": revoked}
        )
        await self._session.commit()
        return IssuedToken(id=record.id, token=token, expires_at=expires_at)

    async def revoke_invite(self, actor: CurrentUser, user_id: int) -> None:
        """Отозвать действующие приглашения пользователя.

        Raises:
            PermissionDeniedError: Нет прав.
            NotFoundError: Пользователь или активное приглашение не найдены.
        """
        target = await self._require_manageable_target(actor, user_id)
        revoked = await self._revoke_active(target.id, AuthTokenPurpose.INVITE, utcnow())
        if revoked == 0:
            raise NotFoundError(texts.INVITE_NOT_FOUND, code="invite_not_found")
        await self._audit_user(actor.id, AUDIT_INVITE_REVOKED, target.id, {"count": revoked})
        await self._session.commit()

    async def revoke_invitation(self, actor: CurrentUser, invitation_id: int) -> None:
        """Отозвать одно приглашение по ``auth_tokens.id`` (``DELETE /admin/invitations/{id}``).

        Приглашение сотрудника отзывает только владелец (как и выпускает).

        Raises:
            NotFoundError: ``invite_not_found`` — нет такого действующего приглашения.
            PermissionDeniedError: Нет прав на пользователя, которому оно выпущено.
        """
        now = utcnow()
        record = await self._tokens.get_by_id(invitation_id, for_update=True)
        if (
            record is None
            or record.purpose != AuthTokenPurpose.INVITE
            or record.used_at is not None
            or record.revoked_at is not None
            or record.expires_at <= now
        ):
            raise NotFoundError(texts.INVITE_NOT_FOUND, code="invite_not_found")
        target = await self._require_manageable_target(actor, record.user_id)
        record.revoked_at = now
        record.updated_at = now
        await self._audit_user(
            actor.id, AUDIT_INVITE_REVOKED, target.id, {"count": 1, "invitation_id": record.id}
        )
        await self._session.commit()

    async def accept_invite(
        self, token: str, telegram_id: int, telegram_username: str | None = None
    ) -> InviteAcceptResult:
        """Принять приглашение (``/start inv_<token>``).

        Если у профиля уже привязан ДРУГОЙ Telegram, токен не погашается, а
        возвращается ``relink_required``: нужно подтверждение (``confirm_relink``).

        Args:
            token: Токен из ссылки.
            telegram_id: Telegram ID принимающего.
            telegram_username: Username (необязательно).

        Returns:
            Результат принятия.

        Raises:
            AppError: 429 ``rate_limited`` — больше 5 неудач за 10 минут.
            NotFoundError: ``invite_invalid`` — нет/просрочен/отозван.
            ConflictError: ``invite_already_used``; ``telegram_already_linked``.
        """
        return await self._accept(
            hash_token(token), telegram_id, telegram_username, confirmed=False
        )

    async def confirm_relink(
        self, token: str, telegram_id: int, telegram_username: str | None = None
    ) -> InviteAcceptResult:
        """Подтвердить перепривязку: старая привязка снимается, сессии удаляются.

        Те же ошибки, что у ``accept_invite``.
        """
        return await self.confirm_relink_by_hash(hash_token(token), telegram_id, telegram_username)

    async def confirm_relink_by_hash(
        self, token_hash: str, telegram_id: int, telegram_username: str | None = None
    ) -> InviteAcceptResult:
        """То же, что ``confirm_relink``, но по SHA-256 токена.

        Бот хранит в FSM (Redis) только хэш: сам токен в Redis не попадает (docs/09 §2.1).
        """
        return await self._accept(token_hash, telegram_id, telegram_username, confirmed=True)

    async def _accept(
        self, token_hash: str, telegram_id: int, username: str | None, *, confirmed: bool
    ) -> InviteAcceptResult:
        subject = str(telegram_id)
        if await self._limiter.is_blocked(
            INVITE_FAILURE_SCOPE, subject, INVITE_FAILED_ATTEMPTS_LIMIT
        ):
            raise AppError(texts.TOO_MANY_ATTEMPTS, code="rate_limited", http_status=429)
        try:
            return await self._accept_checked(
                token_hash, telegram_id, username, confirmed=confirmed
            )
        except (NotFoundError, ConflictError):
            await self._session.rollback()
            await self._limiter.register_failure(
                INVITE_FAILURE_SCOPE, subject, INVITE_FAILED_ATTEMPTS_WINDOW_SECONDS
            )
            raise

    async def _accept_checked(
        self, token_hash: str, telegram_id: int, username: str | None, *, confirmed: bool
    ) -> InviteAcceptResult:
        now = utcnow()
        record = await self._tokens.get_by_hash(token_hash, for_update=True)
        if record is None or record.purpose != AuthTokenPurpose.INVITE:
            raise _invalid_invite()
        if record.used_at is not None:
            raise ConflictError(texts.INVITE_ALREADY_USED, code="invite_already_used")
        if record.revoked_at is not None or record.expires_at <= now:
            raise _invalid_invite()
        target = await self._users.get_by_id(record.user_id)
        if target is None or not target.is_active:
            raise _invalid_invite()

        owner_of_id = await self._users.get_by_telegram_id(telegram_id)
        if owner_of_id is not None and owner_of_id.id != target.id:
            raise ConflictError(texts.TELEGRAM_ALREADY_LINKED, code="telegram_already_linked")

        relink = target.telegram_id is not None and target.telegram_id != telegram_id
        if relink and not confirmed:
            # Результат собирается ДО rollback: после него атрибуты ORM-объекта сброшены.
            pending = InviteAcceptResult(
                InviteAcceptStatus.RELINK_REQUIRED, target.id, target.role, target.display_name
            )
            await self._session.rollback()
            return pending

        first_link = target.telegram_id is None
        target.telegram_id = telegram_id
        target.telegram_username = username
        target.updated_at = now
        record.used_at = now
        record.updated_at = now
        if relink:
            await self._sessions.delete_all_for_user(target.id)
            await self._audit_user(
                target.id, AUDIT_TELEGRAM_RELINKED, target.id, {"invite_token_id": record.id}
            )
        await self._audit_user(
            record.created_by, AUDIT_INVITE_ACCEPTED, target.id, {"invite_token_id": record.id}
        )
        if first_link and target.role == UserRole.STUDENT:
            await NotificationEvents(self._session).student_joined(target.id, target.display_name)
        await self._session.commit()
        return InviteAcceptResult(
            InviteAcceptStatus.LINKED, target.id, target.role, target.display_name
        )

    # ------------------------------------------------------------------ ссылки входа

    async def create_web_login_link(self, actor: CurrentUser) -> IssuedToken:
        """Выпустить одноразовую ссылку входа в браузере (``/web``, 10 минут).

        Args:
            actor: Пользователь, запросивший ссылку (определён по ``telegram_id``).

        Returns:
            Токен и срок действия.
        """
        user = await self._users.get_by_id(actor.id)
        if user is None or not user.is_active:
            raise PermissionDeniedError()
        expires_at = utcnow() + timedelta(minutes=WEB_LOGIN_TTL_MINUTES)
        token = new_token()
        record = await self._tokens.add(
            AuthToken(
                purpose=AuthTokenPurpose.WEB_LOGIN,
                user_id=user.id,
                token_hash=hash_token(token),
                created_by=None,
                expires_at=expires_at,
            )
        )
        await self._session.commit()
        return IssuedToken(id=record.id, token=token, expires_at=expires_at)

    async def consume_web_login(self, token: str) -> CurrentUser:
        """Погасить ссылку входа (только POST, одноразово) и вернуть пользователя.

        Сессию по результату создаёт вызывающий (``create_session``).

        Raises:
            NotFoundError: ``login_link_invalid`` — нет/просрочена/отозвана/архив.
            ConflictError: ``invite_already_used`` — ссылка уже использована.
        """
        now = utcnow()
        record = await self._tokens.get_by_hash(hash_token(token), for_update=True)
        if record is None or record.purpose != AuthTokenPurpose.WEB_LOGIN:
            raise NotFoundError(texts.LOGIN_LINK_INVALID, code="login_link_invalid")
        if record.used_at is not None:
            raise ConflictError(texts.INVITE_ALREADY_USED, code="invite_already_used")
        if record.revoked_at is not None or record.expires_at <= now:
            raise NotFoundError(texts.LOGIN_LINK_INVALID, code="login_link_invalid")
        user = await self._users.get_by_id(record.user_id)
        if user is None or not user.is_active:
            raise NotFoundError(texts.LOGIN_LINK_INVALID, code="login_link_invalid")
        record.used_at = now
        record.updated_at = now
        await self._session.commit()
        return CurrentUser(id=user.id, role=user.role, timezone=user.timezone)

    # ------------------------------------------------------------------ сессии и Telegram

    def validate_init_data(self, init_data: str) -> TelegramUser:
        """Проверить подпись и срок ``initData`` (см. ``core.security``)."""
        return validate_init_data(init_data, self._bot_token)

    async def authenticate_telegram(self, init_data: str) -> CurrentUser:
        """Войти по ``initData`` Mini App: проверить подпись и найти активного пользователя.

        Права и роль берутся из БД, а не из данных клиента (docs/09 §2.2).

        Raises:
            AppError: 401 ``unauthenticated`` — подпись/срок неверны, пользователь
                не найден или в архиве.
        """
        telegram_user = self.validate_init_data(init_data)
        user = await self._users.get_by_telegram_id(telegram_user.id)
        if user is None or not user.is_active:
            raise AppError(texts.UNAUTHENTICATED_TELEGRAM, code="unauthenticated", http_status=401)
        now = utcnow()
        user.last_seen_at = now
        if telegram_user.username is not None:
            user.telegram_username = telegram_user.username
        await self._session.commit()
        return CurrentUser(id=user.id, role=user.role, timezone=user.timezone)

    async def create_session(self, user: CurrentUser) -> tuple[str, int]:
        """Создать серверную сессию; вернуть (id для cookie, TTL в секундах)."""
        return await self._sessions.create(user.id, user.role)

    async def delete_sessions(self, actor: CurrentUser, user_id: int) -> int:
        """Удалить все сессии пользователя (себе — всегда, чужие — персонал).

        Returns:
            Число удалённых сессий.
        """
        if actor.id != user_id and actor.role not in STAFF_ROLES:
            raise PermissionDeniedError()
        return await self._sessions.delete_all_for_user(user_id)

    async def unlink_telegram(self, actor: CurrentUser, user_id: int) -> None:
        """Снять привязку Telegram (``/logout`` самому себе или персоналом).

        Сотрудников отвязывает только владелец. Все сессии пользователя удаляются.

        Raises:
            PermissionDeniedError: Нет прав.
            NotFoundError: Пользователь не найден.
            BusinessRuleError: Telegram не привязан.
        """
        target = await self._users.get_by_id(user_id)
        if target is None:
            raise NotFoundError(texts.USER_NOT_FOUND)
        self._ensure_can_unlink(actor, target)
        if target.telegram_id is None:
            raise BusinessRuleError(texts.TELEGRAM_NOT_LINKED, code="telegram_not_linked")
        target.telegram_id = None
        target.telegram_username = None
        target.updated_at = utcnow()
        await self._audit_user(actor.id, AUDIT_TELEGRAM_UNLINKED, target.id, {})
        # Сначала сессии, потом commit: сбой между шагами не оставит живых сессий.
        await self._sessions.delete_all_for_user(target.id)
        await self._session.commit()

    # ------------------------------------------------------------------ владелец

    async def has_owner(self) -> bool:
        """Есть ли в БД хотя бы один владелец."""
        return await self._users.get_first_by_role(UserRole.OWNER) is not None

    async def ensure_owner(self, owner_telegram_id: int) -> User:
        """Создать владельца по ``OWNER_TELEGRAM_ID``, если владельца ещё нет.

        Идемпотентно: если владелец уже есть, ничего не создаётся.

        Raises:
            ConflictError: Этот Telegram ID занят пользователем не с ролью владельца.
        """
        existing_owner = await self._users.get_first_by_role(UserRole.OWNER)
        if existing_owner is not None:
            return existing_owner
        occupied = await self._users.get_by_telegram_id(owner_telegram_id)
        if occupied is not None:
            raise ConflictError(texts.OWNER_TELEGRAM_ID_TAKEN, code="owner_telegram_id_taken")
        owner = await self._users.add(
            User(
                role=UserRole.OWNER,
                telegram_id=owner_telegram_id,
                display_name=OWNER_DISPLAY_NAME,
            )
        )
        await self._session.commit()
        return owner

    # ------------------------------------------------------------------ внутреннее

    async def _require_manageable_target(self, actor: CurrentUser, user_id: int) -> User:
        if actor.role not in STAFF_ROLES:
            raise PermissionDeniedError()
        target = await self._users.get_by_id(user_id)
        if target is None:
            raise NotFoundError(texts.USER_NOT_FOUND)
        if target.role in STAFF_ROLES and actor.role != UserRole.OWNER:
            raise PermissionDeniedError()
        if not target.is_active:
            raise BusinessRuleError(texts.USER_ARCHIVED, code="user_archived")
        return target

    @staticmethod
    def _ensure_can_unlink(actor: CurrentUser, target: User) -> None:
        if actor.id == target.id:
            # Владелец без привязки не сможет войти: ensure_owner уже не перепривяжет его.
            if target.role == UserRole.OWNER:
                raise BusinessRuleError(texts.OWNER_CANNOT_UNLINK, code="owner_cannot_unlink")
            return
        if actor.role not in STAFF_ROLES:
            raise PermissionDeniedError()
        if target.role in STAFF_ROLES and actor.role != UserRole.OWNER:
            raise PermissionDeniedError()

    async def _revoke_active(self, user_id: int, purpose: AuthTokenPurpose, now: datetime) -> int:
        active = await self._tokens.list_active(user_id, purpose, now)
        for record in active:
            record.revoked_at = now
            record.updated_at = now
        await self._tokens.flush()
        return len(active)

    async def _audit_user(
        self, actor_id: int | None, action: str, target_id: int, data: dict[str, object]
    ) -> None:
        await self._audit.record(
            actor_user_id=actor_id,
            action=action,
            entity_type=AUDIT_ENTITY_USER,
            entity_id=target_id,
            data=data,
        )
