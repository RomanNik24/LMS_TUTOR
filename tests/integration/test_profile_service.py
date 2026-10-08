"""``ProfileService``: профиль, учётные записи и флаг блокировки бота (аудит 2026-10-08, п. 15)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.current_user import CurrentUser
from src.core.enums import UserRole
from src.core.exceptions import NotFoundError
from src.db.models import User
from src.services.profile import ProfileService


async def _user(db: AsyncSession, **fields: object) -> User:
    user = User(role=UserRole.STUDENT, display_name="Аня", **fields)
    db.add(user)
    await db.commit()
    return user


def _actor(user: User) -> CurrentUser:
    return CurrentUser(id=user.id, role=user.role, timezone=user.timezone)


async def test_update_me_changes_only_given_fields_and_touches_updated_at(
    db_session: AsyncSession,
) -> None:
    user = await _user(db_session)
    before = user.updated_at
    service = ProfileService(db_session)

    renamed = await service.update_me(_actor(user), timezone=None, display_name="Анна")
    assert (renamed.display_name, renamed.timezone) == ("Анна", "Europe/Moscow")
    moved = await service.update_me(_actor(user), timezone="Asia/Yekaterinburg", display_name=None)
    assert (moved.display_name, moved.timezone) == ("Анна", "Asia/Yekaterinburg")
    assert moved.updated_at > before


async def test_get_me_of_missing_user_is_not_found(db_session: AsyncSession) -> None:
    ghost = CurrentUser(id=999_999, role=UserRole.STUDENT, timezone="UTC")
    with pytest.raises(NotFoundError):
        await ProfileService(db_session).get_me(ghost)
    with pytest.raises(NotFoundError):
        await ProfileService(db_session).update_me(ghost, timezone="UTC", display_name=None)


async def test_find_account_by_id_and_telegram_id(db_session: AsyncSession) -> None:
    user = await _user(db_session, telegram_id=777_001)
    service = ProfileService(db_session)

    by_id = await service.find_account(user.id)
    by_telegram = await service.find_account_by_telegram_id(777_001)
    assert by_id is not None
    assert by_telegram == by_id
    assert (by_id.user.id, by_id.user.role, by_id.is_active) == (user.id, UserRole.STUDENT, True)
    assert await service.find_account(999_999) is None
    assert await service.find_account_by_telegram_id(1) is None


async def test_archived_account_is_reported_inactive(db_session: AsyncSession) -> None:
    user = await _user(db_session, telegram_id=777_002, is_active=False)
    account = await ProfileService(db_session).find_account(user.id)
    assert account is not None
    assert account.is_active is False


async def test_set_bot_blocked_flips_flag_and_ignores_unknown_user(
    db_session: AsyncSession,
) -> None:
    user = await _user(db_session, telegram_id=777_003)
    service = ProfileService(db_session)

    await service.set_bot_blocked(777_003, True)
    await db_session.refresh(user)
    assert user.bot_blocked is True
    await service.set_bot_blocked(777_003, False)
    await db_session.refresh(user)
    assert user.bot_blocked is False
    await service.set_bot_blocked(1, True)  # неизвестный Telegram ID: тихо игнорируется
