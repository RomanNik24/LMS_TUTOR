"""Ограничения таблицы notifications на реальной PostgreSQL (T5.01, docs/04 §7.1)."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.enums import NotificationStatus, NotificationType, UserRole
from src.db.models import Notification, User

WHEN = datetime(2030, 10, 14, 14, 0, tzinfo=UTC)


@pytest.fixture
async def user(db_session: AsyncSession) -> User:
    item = User(role=UserRole.STUDENT, display_name="Аня")
    db_session.add(item)
    await db_session.flush()
    return item


def make(user: User, key: str = "k1", **extra: object) -> Notification:
    return Notification(
        user_id=user.id,
        type=NotificationType.HOMEWORK_GRADED.value,
        payload={"assignment_id": 1},
        dedup_key=key,
        scheduled_for=WHEN,
        **extra,
    )


async def test_defaults_are_applied_by_database(db_session: AsyncSession, user: User) -> None:
    db_session.add(make(user))
    await db_session.flush()
    row = (await db_session.execute(select(Notification))).scalar_one()
    assert row.status == NotificationStatus.PENDING
    assert row.attempts == 0
    assert row.is_urgent is False
    assert row.sent_at is None
    assert row.last_error is None
    assert row.payload == {"assignment_id": 1}
    assert row.created_at is not None


async def test_dedup_key_is_unique(db_session: AsyncSession, user: User) -> None:
    db_session.add(make(user, "same"))
    await db_session.flush()
    async with db_session.begin_nested():
        db_session.add(make(user, "same"))
        with pytest.raises(IntegrityError):
            await db_session.flush()


async def test_unknown_status_is_rejected(db_session: AsyncSession, user: User) -> None:
    db_session.add(make(user))
    await db_session.flush()
    with pytest.raises(IntegrityError, match="ck_notifications_status"):
        async with db_session.begin_nested():
            await db_session.execute(text("UPDATE notifications SET status = 'queued'"))


async def test_user_must_exist(db_session: AsyncSession) -> None:
    async with db_session.begin_nested():
        db_session.add(
            Notification(
                user_id=999_999, type="x", dedup_key="orphan", scheduled_for=WHEN, payload={}
            )
        )
        with pytest.raises(IntegrityError):
            await db_session.flush()


async def test_deleting_user_removes_their_queue(db_session: AsyncSession, user: User) -> None:
    db_session.add(make(user))
    await db_session.flush()
    await db_session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user.id})
    assert (await db_session.execute(select(Notification))).first() is None
