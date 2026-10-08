"""Финансы и статистика (T7.02, US-07): суммы, срезы, CSV, отмены, журнал, права."""

# ruff: noqa: F401, F811 - фикстуры подключаются импортом из соседних тестов

import csv
import io
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.current_user import CurrentUser
from src.core.enums import LessonStatus, UserRole
from src.core.exceptions import PermissionDeniedError, ValidationError
from src.db.models import AuditLog, StudentProfile, User
from src.schemas.finance import EarningsGroupBy
from src.services.stats import StatsService
from tests.integration.test_dashboard import Factory, factory, staff_actor
from tests.integration.test_schedule_api import (
    AuthedClient,
    anya,
    app,
    boris,
    manager,
    owner,
    owner_user,
    redis_clean,
)

START = datetime(2026, 10, 1, tzinfo=UTC)
END = datetime(2026, 11, 1, tzinfo=UTC)
PERIOD = {"from": "2026-10-01T00:00:00Z", "to": "2026-11-01T00:00:00Z"}


def day(number: int, hour: int = 9, month: int = 10) -> datetime:
    return datetime(2026, month, number, hour, tzinfo=UTC)


async def seed_month(factory: Factory) -> tuple[User, User]:
    """Аня (2000 ₽) и Борис (1500 ₽): проведённые, отменённый, запланированные уроки."""
    informatics = await factory.subject()
    anya = await factory.student("Аня", price=2000)
    boris = await factory.student("Борис", price=1500)
    done = LessonStatus.COMPLETED
    await factory.lesson(informatics, [anya], day(1), done, billable=True, snapshot=1700)
    await factory.lesson(informatics, [anya, boris], day(8), done, billable=True, snapshot=1000)
    await factory.lesson(
        informatics, [boris], day(9), LessonStatus.CANCELLED, billable=True, snapshot=1500
    )
    await factory.lesson(informatics, [boris], day(10), done)  # не оплачивается
    await factory.lesson(informatics, [anya], day(20))
    await factory.lesson(informatics, [anya, boris], day(21))
    await factory.db.commit()
    return anya, boris


async def test_earned_and_expected_by_month_and_week(factory: Factory, owner_user: User) -> None:
    await seed_month(factory)
    service = StatsService(factory.db)

    month = await service.earnings(staff_actor(owner_user), START, END, EarningsGroupBy.MONTH)
    week = await service.earnings(staff_actor(owner_user), START, END, EarningsGroupBy.WEEK)

    assert month.earned_total == 1700 + 1000 + 1000 + 1500
    assert month.expected_total == 2000 + 2000 + 1500
    assert [(row.key, row.earned, row.expected) for row in month.rows] == [
        ("2026-10-01", 5200, 5500)
    ]
    # недели с понедельника в поясе владельца: 1 окт (ср) — неделя с 28 сен
    assert [(row.key, row.earned, row.expected) for row in week.rows] == [
        ("2026-09-28", 1700, 0),
        ("2026-10-05", 3500, 0),
        ("2026-10-19", 0, 5500),
    ]
    assert week.rows[1].earned_lessons == 3


async def test_breakdown_by_student_and_subject(factory: Factory, owner_user: User) -> None:
    await seed_month(factory)
    service = StatsService(factory.db)

    by_student = await service.earnings(
        staff_actor(owner_user), START, END, EarningsGroupBy.STUDENT
    )
    by_subject = await service.earnings(
        staff_actor(owner_user), START, END, EarningsGroupBy.SUBJECT
    )

    names = {row.label: (row.earned, row.expected) for row in by_student.rows}
    assert names == {"Аня": (2700, 4000), "Борис": (2500, 1500)}
    assert [(row.key, row.earned, row.expected) for row in by_subject.rows] == [
        ("informatics", 5200, 5500)
    ]


async def test_price_change_does_not_change_past_lessons(
    factory: Factory, owner_user: User
) -> None:
    anya, _ = await seed_month(factory)
    service = StatsService(factory.db)
    before = await service.earnings(staff_actor(owner_user), START, END, EarningsGroupBy.MONTH)

    profile = await factory.db.get(StudentProfile, anya.id)
    assert profile is not None
    profile.lesson_price = 9000
    await factory.db.commit()
    after = await service.earnings(staff_actor(owner_user), START, END, EarningsGroupBy.MONTH)

    assert after.earned_total == before.earned_total
    # а ожидаемое считается по ТЕКУЩЕЙ цене: два будущих урока Ани стали по 9000
    assert after.expected_total == before.expected_total + 2 * (9000 - 2000)


async def test_period_rules(factory: Factory, owner_user: User) -> None:
    service = StatsService(factory.db)
    actor = staff_actor(owner_user)
    too_long = datetime(2027, 10, 3, tzinfo=UTC)  # 367 дней

    with pytest.raises(ValidationError) as long_period:
        await service.earnings(actor, START, too_long, EarningsGroupBy.MONTH)
    with pytest.raises(ValidationError):
        await service.export_csv(actor, START, too_long)
    with pytest.raises(ValidationError):
        await service.earnings(actor, END, START, EarningsGroupBy.MONTH)

    assert long_period.value.code == "invalid_period"


async def test_manager_and_student_cannot_use_finance_service(
    factory: Factory, owner_user: User, db_session: AsyncSession
) -> None:
    manager_user = User(role=UserRole.MANAGER, display_name="Менеджер")
    db_session.add(manager_user)
    await db_session.commit()
    service = StatsService(db_session)
    actor = staff_actor(manager_user)

    with pytest.raises(PermissionDeniedError):
        await service.earnings(actor, START, END, EarningsGroupBy.MONTH)
    with pytest.raises(PermissionDeniedError):
        await service.export_csv(actor, START, END)
    with pytest.raises(PermissionDeniedError):
        await service.list_audit(actor)
    # отмены доступны персоналу
    assert (await service.cancellations(actor, START, END)).cancelled_lessons == 0


async def test_csv_has_only_required_columns_and_is_audited(
    factory: Factory, owner_user: User
) -> None:
    await seed_month(factory)
    service = StatsService(factory.db)

    content = await service.export_csv(staff_actor(owner_user), START, END)

    rows = list(csv.reader(io.StringIO(content)))
    assert rows[0] == ["Дата", "Ученик", "Предмет", "Сумма, ₽"]
    assert all(len(row) == 4 for row in rows)
    assert rows[1:] == [
        ["2026-10-01", "Аня", "Информатика", "1700"],
        ["2026-10-08", "Аня", "Информатика", "1000"],
        ["2026-10-08", "Борис", "Информатика", "1000"],
        ["2026-10-09", "Борис", "Информатика", "1500"],
    ]
    audit = (await service.list_audit(staff_actor(owner_user))).items
    assert audit[0].action == "finance.exported"
    assert audit[0].data["rows"] == 4
    assert audit[0].actor_name == owner_user.display_name


async def test_csv_neutralizes_spreadsheet_formulas(factory: Factory, owner_user: User) -> None:
    subject = await factory.subject()
    evil = await factory.student("=HYPERLINK(1)")
    await factory.lesson(
        subject, [evil], day(2), LessonStatus.COMPLETED, billable=True, snapshot=100
    )
    await factory.db.commit()

    content = await StatsService(factory.db).export_csv(staff_actor(owner_user), START, END)

    assert list(csv.reader(io.StringIO(content)))[1][1] == "'=HYPERLINK(1)"


async def test_cancellation_stats(factory: Factory, owner_user: User) -> None:
    await seed_month(factory)
    subject = await factory.subject()
    anya = await factory.student("Вера")
    await factory.lesson(subject, [anya], day(11), LessonStatus.CANCELLED)
    await factory.lesson(subject, [anya], day(12), LessonStatus.CANCELLED)
    await factory.db.commit()

    stats = await StatsService(factory.db).cancellations(staff_actor(owner_user), START, END)

    assert stats.cancelled_lessons == 3
    assert stats.cancelled_participations == 3
    assert [(row.student_name, row.cancelled_lessons) for row in stats.by_student] == [
        ("Вера", 2),
        ("Борис", 1),
    ]


async def test_audit_is_paged_newest_first(factory: Factory, owner_user: User) -> None:
    for index in range(3):
        factory.db.add(
            AuditLog(
                actor_user_id=owner_user.id,
                action=f"test.event{index}",
                entity_type="test",
                entity_id=index,
                data={},
            )
        )
    await factory.db.commit()
    service = StatsService(factory.db)

    page = await service.list_audit(staff_actor(owner_user), limit=2, offset=0)

    assert page.total == 3
    assert [item.action for item in page.items] == ["test.event2", "test.event1"]
    with pytest.raises(ValidationError):
        await service.list_audit(staff_actor(owner_user), limit=0)


async def test_manager_forbidden_all_finance_endpoints(
    owner: AuthedClient, manager: AuthedClient
) -> None:
    paths = [
        ("/api/v1/admin/finance/earnings", PERIOD),
        ("/api/v1/admin/finance/export.csv", PERIOD),
        ("/api/v1/admin/audit", {}),
    ]
    for path, params in paths:
        denied = await manager.get(path, params=params)
        assert denied.status_code == 403, path
        allowed = await owner.get(path, params=params)
        assert allowed.status_code == 200, (path, allowed.text)
    # статистика отмен доступна персоналу, денег в ней нет
    staff = await manager.get("/api/v1/admin/stats/cancellations", params=PERIOD)
    assert staff.status_code == 200
    assert "earned" not in staff.text and "price" not in staff.text.lower()


async def test_http_csv_headers_and_period_validation(owner: AuthedClient) -> None:
    response = await owner.get("/api/v1/admin/finance/export.csv", params=PERIOD)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    assert response.content.startswith(b"\xef\xbb\xbf")  # BOM для Excel

    bad = await owner.get(
        "/api/v1/admin/finance/earnings",
        params={"from": "2026-01-01T00:00:00Z", "to": "2028-01-01T00:00:00Z"},
    )
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "invalid_period"
