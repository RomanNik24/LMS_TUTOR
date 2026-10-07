"""``MaintenanceService``: плановая уборка (T5.05, docs/03 §9)."""

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import TOKEN_RETENTION_DAYS
from src.core.timeutils import utcnow
from src.repositories.auth_tokens import AuthTokenRepository


class MaintenanceService:
    """Удаление устаревших служебных данных."""

    def __init__(self, session: AsyncSession) -> None:
        """Создать сервис.

        Args:
            session: Сессия БД на текущую единицу работы.
        """
        self._session = session
        self._tokens = AuthTokenRepository(session)

    async def cleanup_tokens(self, now: datetime | None = None) -> int:
        """Удалить приглашения и ссылки входа, истёкшие больше суток назад.

        Сутки хранения нужны, чтобы «ссылка устарела» отличалась от «ссылки не было».

        Returns:
            Сколько токенов удалено.
        """
        moment = now or utcnow()
        deleted = await self._tokens.delete_expired(moment - timedelta(days=TOKEN_RETENTION_DAYS))
        await self._session.commit()
        return deleted
