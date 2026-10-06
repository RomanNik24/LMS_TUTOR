"""Репозиторий приглашений и ссылок входа (задача T1.06, docs/04 §2.5).

Токен действителен, если ``used_at IS NULL AND revoked_at IS NULL AND
expires_at > now``. Текущее время передаётся параметром (UTC), чтобы
репозиторий не вызывал часы сам и логику можно было тестировать.
"""

from datetime import datetime

from sqlalchemy import select

from src.core.enums import AuthTokenPurpose
from src.db.models import AuthToken
from src.repositories.base import BaseRepository


class AuthTokenRepository(BaseRepository[AuthToken]):
    """Доступ к таблице ``auth_tokens``."""

    async def get_by_hash(self, token_hash: str, *, for_update: bool = False) -> AuthToken | None:
        """Найти токен по SHA-256 хэшу (сам токен в БД не хранится).

        Args:
            token_hash: Хэш токена (64 hex-символа).
            for_update: Заблокировать строку (``SELECT ... FOR UPDATE``), чтобы
                две одновременные попытки не погасили одноразовый токен дважды.

        Returns:
            Токен (в любом состоянии) или ``None``.
        """
        stmt = select(AuthToken).where(AuthToken.token_hash == token_hash)
        if for_update:
            stmt = stmt.with_for_update()
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_active(
        self, user_id: int, purpose: AuthTokenPurpose, now: datetime
    ) -> list[AuthToken]:
        """Вернуть действующие токены пользователя (для отзыва прежних приглашений).

        Args:
            user_id: Для кого выпущены токены.
            purpose: Назначение (``invite`` / ``web_login``).
            now: Текущий момент, aware UTC.

        Returns:
            Список неиспользованных, неотозванных и непросроченных токенов.
        """
        stmt = select(AuthToken).where(
            AuthToken.user_id == user_id,
            AuthToken.purpose == purpose,
            AuthToken.used_at.is_(None),
            AuthToken.revoked_at.is_(None),
            AuthToken.expires_at > now,
        )
        return list((await self._session.execute(stmt)).scalars().all())
