"""Интеграционные тесты репозиториев и транзакций T1.06 (реальная PostgreSQL)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, InvalidRequestError
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.enums import AuthTokenPurpose, UserRole
from src.db.models import AuthToken, StudentProfile, User
from src.db.session import create_engine, create_session_factory, session_scope
from src.repositories.audit_log import AuditLogRepository
from src.repositories.auth_tokens import AuthTokenRepository
from src.repositories.student_profiles import StudentProfileRepository
from src.repositories.users import UserRepository

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


async def _make_student(session: AsyncSession) -> tuple[User, User]:
    users = UserRepository(session)
    teacher = await users.add(User(role=UserRole.OWNER, display_name="Teacher", telegram_id=101))
    student = await users.add(User(role=UserRole.STUDENT, display_name="Student"))
    session.add(StudentProfile(user_id=student.id, teacher_id=teacher.id))
    await session.flush()
    return teacher, student


async def test_user_repository_lookups(db_session: AsyncSession) -> None:
    teacher, student = await _make_student(db_session)
    repo = UserRepository(db_session)
    assert (await repo.get_by_id(teacher.id)) is teacher
    found = await repo.get_by_telegram_id(101)
    assert found is not None
    assert found.id == teacher.id
    assert await repo.get_by_telegram_id(999) is None
    assert student.id is not None


async def test_duplicate_telegram_id_is_rejected(db_session: AsyncSession) -> None:
    repo = UserRepository(db_session)
    await repo.add(User(role=UserRole.STUDENT, display_name="A", telegram_id=555))
    with pytest.raises(IntegrityError):
        await repo.add(User(role=UserRole.STUDENT, display_name="B", telegram_id=555))


async def test_lazy_loading_is_forbidden_and_selectinload_works(db_session: AsyncSession) -> None:
    _, student = await _make_student(db_session)
    student_id = student.id
    db_session.expire_all()

    plain = await UserRepository(db_session).get_by_id(student_id)
    assert plain is not None
    with pytest.raises(InvalidRequestError):
        _ = plain.student_profile  # неявная ленивая загрузка запрещена (lazy="raise")

    db_session.expire_all()
    loaded = await UserRepository(db_session).get_by_id(student_id, with_profile=True)
    assert loaded is not None
    assert loaded.student_profile is not None
    assert loaded.student_profile.teacher_id is not None


async def test_student_profile_repository(db_session: AsyncSession) -> None:
    _, student = await _make_student(db_session)
    repo = StudentProfileRepository(db_session)
    profile = await repo.get_by_user_id(student.id)
    assert profile is not None
    assert profile.lesson_price == 0
    assert await repo.get_by_user_id(987654) is None


async def test_auth_token_repository_active_filter(db_session: AsyncSession) -> None:
    teacher, student = await _make_student(db_session)
    repo = AuthTokenRepository(db_session)

    def token(h: str, **kw: datetime | None) -> AuthToken:
        return AuthToken(
            purpose=AuthTokenPurpose.INVITE,
            user_id=student.id,
            token_hash=h.ljust(64, "0"),
            created_by=teacher.id,
            expires_at=kw.pop("expires_at", NOW + timedelta(days=7)) or NOW,
            used_at=kw.get("used_at"),
            revoked_at=kw.get("revoked_at"),
        )

    await repo.add(token("a"))
    await repo.add(token("b", used_at=NOW))
    await repo.add(token("c", revoked_at=NOW))
    await repo.add(token("d", expires_at=NOW - timedelta(seconds=1)))

    active = await repo.list_active(student.id, AuthTokenPurpose.INVITE, NOW)
    assert [t.token_hash[0] for t in active] == ["a"]
    assert await repo.list_active(student.id, AuthTokenPurpose.WEB_LOGIN, NOW) == []
    by_hash = await repo.get_by_hash("a".ljust(64, "0"))
    assert by_hash is not None
    assert await repo.get_by_hash("z" * 64) is None


async def test_audit_log_repository_records(db_session: AsyncSession) -> None:
    teacher, student = await _make_student(db_session)
    entry = await AuditLogRepository(db_session).record(
        actor_user_id=teacher.id,
        action="invite.created",
        entity_type="user",
        entity_id=student.id,
        data={"ttl_days": 7},
    )
    assert entry.id is not None
    assert entry.data == {"ttl_days": 7}
    assert entry.created_at is not None


async def test_repository_flush_does_not_commit(migrated_postgres_url: str) -> None:
    """После flush строка видна только своей транзакции, а не другому соединению."""
    engine = create_engine(migrated_postgres_url)
    factory = create_session_factory(engine)
    try:
        async with session_scope(factory) as session:
            await UserRepository(session).add(
                User(role=UserRole.STUDENT, display_name="no-commit", telegram_id=777001)
            )
            async with engine.connect() as other:
                seen = await other.scalar(
                    text("SELECT count(*) FROM users WHERE telegram_id=777001")
                )
            assert seen == 0
        # Сессия закрыта без commit → строки нет и после выхода.
        async with factory() as check:
            gone = await check.scalar(
                select(func.count()).select_from(User).where(User.telegram_id == 777001)
            )
        assert gone == 0
    finally:
        await engine.dispose()


async def test_session_scope_rolls_back_on_exception(migrated_postgres_url: str) -> None:
    engine = create_engine(migrated_postgres_url)
    factory = create_session_factory(engine)
    try:
        with pytest.raises(RuntimeError, match="boom"):
            async with session_scope(factory) as session:
                await UserRepository(session).add(
                    User(role=UserRole.STUDENT, display_name="rb", telegram_id=777002)
                )
                raise RuntimeError("boom")
        async with factory() as check:
            count = await check.scalar(
                select(func.count()).select_from(User).where(User.telegram_id == 777002)
            )
        assert count == 0
    finally:
        await engine.dispose()


async def test_service_commit_persists_and_get_session_dependency(
    migrated_postgres_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """commit в «сервисе» сохраняет данные; get_session отдаёт рабочую сессию."""
    from src.api import deps

    engine = create_engine(migrated_postgres_url)
    factory = create_session_factory(engine)
    monkeypatch.setattr(deps, "get_session_factory", lambda: factory)
    try:
        gen = deps.get_session()
        session = await anext(gen)
        await UserRepository(session).add(
            User(role=UserRole.STUDENT, display_name="persist", telegram_id=777003)
        )
        await session.commit()  # commit делает «сервис», не репозиторий
        await gen.aclose()
        async with factory() as check:
            user = await UserRepository(check).get_by_telegram_id(777003)
            assert user is not None
            await check.delete(user)
            await check.commit()
    finally:
        await engine.dispose()
