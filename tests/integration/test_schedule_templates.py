"""Шаблоны расписания и генерация уроков (T3.06, US-02) на реальной PostgreSQL."""

from collections.abc import Iterator
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
import time_machine
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.current_user import CurrentUser
from src.core.enums import LessonStatus, UserRole
from src.core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from src.db.models import Lesson, LessonParticipant, ScheduleTemplate, StudentProfile, Subject, User
from src.schemas.schedule import (
    LessonCancel,
    LessonCreate,
    LessonReschedule,
    TemplateCreate,
    TemplateUpdate,
)
from src.services.schedule import ScheduleService

pytestmark = pytest.mark.security

# Вторник 6 октября 2026, 12:00 UTC (15:00 в Москве).
NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
MSK = ZoneInfo("Europe/Moscow")
BERLIN = ZoneInfo("Europe/Berlin")


@pytest.fixture(autouse=True)
def _frozen() -> Iterator[None]:
    with time_machine.travel(NOW, tick=False):
        yield


@pytest.fixture
def service(db_session: AsyncSession) -> ScheduleService:
    return ScheduleService(db_session, horizon_weeks=2)


async def _user(db: AsyncSession, role: UserRole, name: str, *, active: bool = True) -> User:
    user = User(role=role, display_name=name, is_active=active)
    db.add(user)
    await db.commit()
    return user


def _actor(user: User) -> CurrentUser:
    return CurrentUser(id=user.id, role=user.role, timezone=user.timezone)


async def _student(db: AsyncSession, name: str, teacher: User, *, active: bool = True) -> User:
    user = await _user(db, UserRole.STUDENT, name, active=active)
    db.add(StudentProfile(user_id=user.id, teacher_id=teacher.id, lesson_price=1000))
    await db.commit()
    return user


@pytest.fixture
async def owner(db_session: AsyncSession) -> User:
    return await _user(db_session, UserRole.OWNER, "Роман")


@pytest.fixture
async def anya(db_session: AsyncSession, owner: User) -> User:
    return await _student(db_session, "Аня", owner)


@pytest.fixture
async def boris(db_session: AsyncSession, owner: User) -> User:
    return await _student(db_session, "Борис", owner)


@pytest.fixture(autouse=True)
async def _subjects(db_session: AsyncSession) -> None:
    db_session.add(Subject(code="informatics", name="Информатика"))
    await db_session.commit()


def tpl(students: list[int], **patch: object) -> TemplateCreate:
    base: dict[str, object] = {
        "subject_code": "informatics",
        "student_ids": students,
        "weekday": 2,  # вторник
        "start_local_time": time(17, 0),
        "timezone": "Europe/Moscow",
        "starts_on": date(2026, 10, 6),
    }
    return TemplateCreate.model_validate(base | patch)


async def _lessons(db: AsyncSession, template_id: int | None = None) -> list[Lesson]:
    stmt = select(Lesson).order_by(Lesson.start_at).execution_options(populate_existing=True)
    if template_id is not None:
        stmt = stmt.where(Lesson.template_id == template_id)
    return list((await db.execute(stmt)).scalars())


def local_times(lessons: list[Lesson], zone: ZoneInfo) -> list[tuple[date, time]]:
    return [
        (lesson.start_at.astimezone(zone).date(), lesson.start_at.astimezone(zone).time())
        for lesson in lessons
    ]


# ---------------------------------------------------------------- создание и генерация


async def test_create_template_generates_lessons_for_horizon(
    service: ScheduleService, db_session: AsyncSession, owner: User, anya: User, boris: User
) -> None:
    item = await service.create_template(_actor(owner), tpl([anya.id, boris.id]))
    assert item.student_ids == sorted([anya.id, boris.id])
    assert item.generated_until == date(2026, 10, 20)
    lessons = await _lessons(db_session, item.id)
    # вторники 6, 13, 20 октября 17:00 по Москве (сегодняшний ещё впереди: 15:00 < 17:00)
    assert local_times(lessons, MSK) == [(date(2026, 10, d), time(17, 0)) for d in (6, 13, 20)]
    assert all(lesson.teacher_id == owner.id for lesson in lessons)
    assert all(not lesson.is_detached for lesson in lessons)
    participants = (
        await db_session.execute(select(func.count()).select_from(LessonParticipant))
    ).scalar_one()
    assert participants == 3 * 2


async def test_past_occurrences_are_not_created(
    service: ScheduleService, db_session: AsyncSession, owner: User, anya: User
) -> None:
    with time_machine.travel(
        NOW.replace(hour=15), tick=False
    ):  # 18:00 МСК: сегодняшний урок прошёл
        item = await service.create_template(_actor(owner), tpl([anya.id]))
    dates = [d for d, _ in local_times(await _lessons(db_session, item.id), MSK)]
    assert dates == [date(2026, 10, 13), date(2026, 10, 20)]


async def test_generation_is_idempotent_and_extends_with_horizon(
    service: ScheduleService, db_session: AsyncSession, owner: User, anya: User
) -> None:
    item = await service.create_template(_actor(owner), tpl([anya.id]))
    again = await service.generate_lessons(_actor(owner))
    assert (again.templates, again.created, again.skipped) == (1, 0, 0)
    assert len(await _lessons(db_session, item.id)) == 3
    longer = await service.generate_lessons(_actor(owner), horizon_weeks=4)
    assert longer.created == 2
    dates = [d for d, _ in local_times(await _lessons(db_session, item.id), MSK)]
    assert dates[-2:] == [date(2026, 10, 27), date(2026, 11, 3)]
    assert len(dates) == len(set(dates)) == 5


async def test_unique_index_protects_even_without_watermark(
    service: ScheduleService, db_session: AsyncSession, owner: User, anya: User
) -> None:
    item = await service.create_template(_actor(owner), tpl([anya.id]))
    template = await db_session.get(ScheduleTemplate, item.id)
    assert template is not None
    template.generated_until = None
    await db_session.commit()
    result = await service.generate_lessons(_actor(owner))
    assert (result.created, result.skipped) == (0, 3)
    assert len(await _lessons(db_session, item.id)) == 3


async def test_generation_skips_time_taken_by_manual_lesson(
    service: ScheduleService, db_session: AsyncSession, owner: User, anya: User
) -> None:
    taken = datetime(2026, 10, 13, 14, 30, tzinfo=UTC)  # пересекает вторник 17:00 МСК
    await service.create_lesson(
        _actor(owner),
        LessonCreate(
            subject_code="informatics",
            student_ids=[anya.id],
            start_at=taken,
            end_at=taken + timedelta(minutes=30),
        ),
    )
    item = await service.create_template(_actor(owner), tpl([anya.id]))
    dates = [d for d, _ in local_times(await _lessons(db_session, item.id), MSK)]
    assert dates == [date(2026, 10, 6), date(2026, 10, 20)]


async def test_template_period_end_is_respected(
    service: ScheduleService, db_session: AsyncSession, owner: User, anya: User
) -> None:
    item = await service.create_template(_actor(owner), tpl([anya.id], ends_on=date(2026, 10, 13)))
    assert len(await _lessons(db_session, item.id)) == 2
    assert item.generated_until == date(2026, 10, 13)


async def test_future_start_date_is_respected(
    service: ScheduleService, db_session: AsyncSession, owner: User, anya: User
) -> None:
    item = await service.create_template(
        _actor(owner), tpl([anya.id], starts_on=date(2026, 10, 14))
    )
    dates = [d for d, _ in local_times(await _lessons(db_session, item.id), MSK)]
    assert dates == [date(2026, 10, 20)]


async def test_dst_change_does_not_shift_local_time(
    db_session: AsyncSession, owner: User, anya: User
) -> None:
    long_service = ScheduleService(db_session, horizon_weeks=4)
    item = await long_service.create_template(
        _actor(owner),
        tpl([anya.id], weekday=7, timezone="Europe/Berlin", starts_on=date(2026, 10, 11)),
    )
    lessons = await _lessons(db_session, item.id)
    assert {t for _, t in local_times(lessons, BERLIN)} == {time(17, 0)}
    utc_hours = [lesson.start_at.hour for lesson in lessons]
    # до перехода 25 октября UTC+2 (15:00 UTC), после — UTC+1 (16:00 UTC)
    assert utc_hours == [15, 15, 16, 16]


async def test_archived_participants_are_not_invited(
    service: ScheduleService, db_session: AsyncSession, owner: User, anya: User, boris: User
) -> None:
    item = await service.create_template(_actor(owner), tpl([anya.id, boris.id]))
    boris.is_active = False
    await db_session.commit()
    await service.update_template(_actor(owner), item.id, TemplateUpdate(duration_minutes=45))
    rows = (await db_session.execute(select(LessonParticipant.student_id).distinct())).scalars()
    assert list(rows) == [anya.id]
    boris.is_active = False
    anya.is_active = False
    await db_session.commit()
    await service.update_template(_actor(owner), item.id, TemplateUpdate(duration_minutes=50))
    assert await _lessons(db_session, item.id) == []


# ---------------------------------------------------------------- правка шаблона


async def test_update_touches_only_future_unmodified_lessons(
    service: ScheduleService, db_session: AsyncSession, owner: User, anya: User
) -> None:
    item = await service.create_template(_actor(owner), tpl([anya.id]))
    first, second, third = await _lessons(db_session, item.id)
    moved_start = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
    await service.reschedule_lesson(
        _actor(owner),
        second.id,
        LessonReschedule(start_at=moved_start, end_at=moved_start + timedelta(minutes=60)),
    )
    updated = await service.update_template(
        _actor(owner), item.id, TemplateUpdate(duration_minutes=90)
    )
    lessons = await _lessons(db_session, item.id)
    by_id = {lesson.id: lesson for lesson in lessons}
    # вручную перенесённый урок не тронут: тот же id, время и длительность
    assert by_id[second.id].start_at == moved_start
    assert by_id[second.id].end_at - by_id[second.id].start_at == timedelta(minutes=60)
    assert by_id[second.id].is_detached is True
    # остальные пересозданы по новым правилам
    others = [lesson for lesson in lessons if lesson.id != second.id]
    assert {lesson.end_at - lesson.start_at for lesson in others} == {timedelta(minutes=90)}
    assert first.id not in by_id and third.id not in by_id
    assert updated.duration_minutes == 90


async def test_update_weekday_and_time_regenerates(
    service: ScheduleService, db_session: AsyncSession, owner: User, anya: User
) -> None:
    item = await service.create_template(_actor(owner), tpl([anya.id]))
    await service.update_template(
        _actor(owner), item.id, TemplateUpdate(weekday=4, start_local_time=time(10, 30))
    )
    lessons = await _lessons(db_session, item.id)
    assert local_times(lessons, MSK) == [(date(2026, 10, d), time(10, 30)) for d in (8, 15)]


async def test_update_keeps_completed_cancelled_and_does_not_resurrect_cancelled(
    service: ScheduleService, db_session: AsyncSession, owner: User, anya: User
) -> None:
    item = await service.create_template(_actor(owner), tpl([anya.id]))
    first, second, _ = await _lessons(db_session, item.id)
    await service.cancel_lesson(_actor(owner), second.id, LessonCancel())
    await service.update_template(_actor(owner), item.id, TemplateUpdate(duration_minutes=75))
    lessons = await _lessons(db_session, item.id)
    cancelled = [lesson for lesson in lessons if lesson.status == LessonStatus.CANCELLED]
    assert [lesson.id for lesson in cancelled] == [second.id]
    # отменённая дата (13 октября) заново не создаётся
    dates = [d for d, _ in local_times(lessons, MSK)]
    assert dates.count(date(2026, 10, 13)) == 1


async def test_update_participants_replaces_template_students(
    service: ScheduleService, db_session: AsyncSession, owner: User, anya: User, boris: User
) -> None:
    item = await service.create_template(_actor(owner), tpl([anya.id]))
    updated = await service.update_template(
        _actor(owner), item.id, TemplateUpdate(student_ids=[boris.id])
    )
    assert updated.student_ids == [boris.id]
    rows = (await db_session.execute(select(LessonParticipant.student_id).distinct())).scalars()
    assert list(rows) == [boris.id]


async def test_update_ends_on_before_start_is_rejected(
    service: ScheduleService, owner: User, anya: User
) -> None:
    item = await service.create_template(_actor(owner), tpl([anya.id]))
    with pytest.raises(ValidationError) as raised:
        await service.update_template(
            _actor(owner), item.id, TemplateUpdate(ends_on=date(2026, 10, 1))
        )
    assert raised.value.code == "invalid_period"


# ---------------------------------------------------------------- пауза


async def test_deactivate_removes_future_lessons_and_stops_generation(
    service: ScheduleService, db_session: AsyncSession, owner: User, anya: User
) -> None:
    item = await service.create_template(_actor(owner), tpl([anya.id]))
    first = (await _lessons(db_session, item.id))[0]
    await service.complete_lesson(
        _actor(owner),
        first.id,
        __import__(
            "src.schemas.schedule", fromlist=["LessonComplete"]
        ).LessonComplete.model_validate(
            {"marks": [{"student_id": anya.id, "attendance": "attended"}]}
        ),
    )
    paused = await service.deactivate_template(_actor(owner), item.id)
    assert paused.is_active is False
    remaining = await _lessons(db_session, item.id)
    assert [lesson.id for lesson in remaining] == [first.id]  # проведённый урок остаётся
    result = await service.generate_lessons(_actor(owner), horizon_weeks=8)
    assert (result.templates, result.created) == (0, 0)


async def test_resume_template_regenerates(
    service: ScheduleService, db_session: AsyncSession, owner: User, anya: User
) -> None:
    item = await service.create_template(_actor(owner), tpl([anya.id]))
    await service.deactivate_template(_actor(owner), item.id)
    resumed = await service.update_template(_actor(owner), item.id, TemplateUpdate(is_active=True))
    assert resumed.is_active is True
    assert len(await _lessons(db_session, item.id)) == 3


# ---------------------------------------------------------------- права и ошибки


async def test_permissions_and_errors(service: ScheduleService, owner: User, anya: User) -> None:
    item = await service.create_template(_actor(owner), tpl([anya.id]))
    with pytest.raises(PermissionDeniedError):
        await service.create_template(_actor(anya), tpl([anya.id]))
    with pytest.raises(PermissionDeniedError):
        await service.update_template(_actor(anya), item.id, TemplateUpdate(weekday=3))
    with pytest.raises(PermissionDeniedError):
        await service.deactivate_template(_actor(anya), item.id)
    with pytest.raises(PermissionDeniedError):
        await service.generate_lessons(_actor(anya))
    with pytest.raises(PermissionDeniedError):
        await service.list_templates(_actor(anya))
    with pytest.raises(NotFoundError) as missing:
        await service.update_template(_actor(owner), 999_999_999, TemplateUpdate(weekday=3))
    assert missing.value.code == "template_not_found"
    for weeks in (0, 53):
        with pytest.raises(ValidationError):
            await service.generate_lessons(_actor(owner), horizon_weeks=weeks)


async def test_system_generation_without_actor_and_list(
    service: ScheduleService, db_session: AsyncSession, owner: User, anya: User
) -> None:
    item = await service.create_template(_actor(owner), tpl([anya.id]))
    result = await service.generate_lessons(None, horizon_weeks=3)
    assert result.created == 1  # к 3 вторникам добавился 27 октября
    templates = await service.list_templates(_actor(owner))
    assert [t.id for t in templates] == [item.id]
    assert templates[0].subject_code == "informatics"


# ---------------------------------------------------------------- срок генерации (период и правка)


async def test_template_with_period_generates_whole_period_beyond_horizon(
    service: ScheduleService, db_session: AsyncSession, owner: User, anya: User
) -> None:
    """Горизонт службы — 2 недели, но шаблон с датой окончания заполняется весь период."""
    item = await service.create_template(_actor(owner), tpl([anya.id], ends_on=date(2026, 11, 3)))
    dates = [d for d, _ in local_times(await _lessons(db_session, item.id), MSK)]
    assert dates == [date(2026, 10, d) for d in (6, 13, 20, 27)] + [date(2026, 11, 3)]
    assert item.generated_until == date(2026, 11, 3)


async def test_unbounded_template_is_limited_by_horizon(
    service: ScheduleService, db_session: AsyncSession, owner: User, anya: User
) -> None:
    item = await service.create_template(_actor(owner), tpl([anya.id]))
    assert len(await _lessons(db_session, item.id)) == 3


async def test_update_keeps_the_generated_extent(
    service: ScheduleService, db_session: AsyncSession, owner: User, anya: User
) -> None:
    """Если уроки сгенерированы на 4 недели, правка шаблона не должна сокращать их до горизонта."""
    item = await service.create_template(_actor(owner), tpl([anya.id]))
    await service.generate_lessons(_actor(owner), horizon_weeks=4)
    assert len(await _lessons(db_session, item.id)) == 5
    await service.update_template(_actor(owner), item.id, TemplateUpdate(duration_minutes=45))
    lessons = await _lessons(db_session, item.id)
    assert len(lessons) == 5
    assert {lesson.end_at - lesson.start_at for lesson in lessons} == {timedelta(minutes=45)}


async def test_update_of_bounded_template_regenerates_whole_period(
    service: ScheduleService, db_session: AsyncSession, owner: User, anya: User
) -> None:
    item = await service.create_template(_actor(owner), tpl([anya.id], ends_on=date(2026, 11, 3)))
    await service.update_template(_actor(owner), item.id, TemplateUpdate(duration_minutes=75))
    assert len(await _lessons(db_session, item.id)) == 5


async def test_very_long_period_is_capped_at_52_weeks(
    service: ScheduleService, db_session: AsyncSession, owner: User, anya: User
) -> None:
    item = await service.create_template(_actor(owner), tpl([anya.id], ends_on=date(2030, 12, 31)))
    lessons = await _lessons(db_session, item.id)
    assert len(lessons) == 53  # 52 недель вперёд включительно, по одному вторнику
    assert item.generated_until is not None
    assert (item.generated_until - date(2026, 10, 6)).days <= 52 * 7
