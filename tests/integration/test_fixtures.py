"""Проверка тестовой инфраструктуры T0.09: сессия с откатом, API-клиент, время."""

from datetime import UTC, datetime

import httpx
import time_machine
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.enums import UserRole
from src.db.models import User


async def test_db_session_sees_migrated_schema(db_session: AsyncSession) -> None:
    """Сессия видит таблицы, созданные `alembic upgrade head`."""
    tables = await db_session.scalar(
        text("SELECT count(*) FROM information_schema.tables WHERE table_name = 'users'")
    )
    assert tables == 1


async def test_db_session_commit_is_rolled_back_after_test_part1(db_session: AsyncSession) -> None:
    """Часть 1: запись с commit() внутри теста..."""
    db_session.add(User(role=UserRole.OWNER, display_name="rollback-probe"))
    await db_session.commit()
    count = await db_session.scalar(text("SELECT count(*) FROM users"))
    assert count is not None
    assert count >= 1


async def test_db_session_commit_is_rolled_back_after_test_part2(db_session: AsyncSession) -> None:
    """Часть 2: ...не видна следующему тесту (откат после теста)."""
    count = await db_session.scalar(
        text("SELECT count(*) FROM users WHERE display_name = 'rollback-probe'")
    )
    assert count == 0


async def test_api_client_reaches_app(api_client: httpx.AsyncClient) -> None:
    """`api_client` ходит в FastAPI без сети."""
    response = await api_client.get("/health")
    assert response.status_code == 200


def test_frozen_time_fixture(frozen_time: time_machine.travel) -> None:
    """`frozen_time` фиксирует «сейчас» и позволяет двигать время."""
    from src.core.timeutils import utcnow

    assert utcnow() == datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
    frozen_time.move_to(datetime(2026, 10, 7, tzinfo=UTC))
    assert utcnow() == datetime(2026, 10, 7, tzinfo=UTC)
