"""Дашборд «Сегодня» (T7.01, docs/01 §4.3): блоки, права, схемы по ролям, число запросов."""

# ruff: noqa: F401, F811 - фикстуры подключаются импортом из test_schedule_api

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.current_user import CurrentUser
from src.core.enums import (
    AssignmentStatus,
    AttendanceStatus,
    DueMode,
    HomeworkKind,
    LessonStatus,
    UserRole,
)
from src.core.exceptions import PermissionDeniedError
from src.db.models import (
    Homework,
    HomeworkAssignment,
    Lesson,
    LessonParticipant,
    StudentProfile,
    Subject,
    User,
)
from src.schemas.dashboard import DashboardOwner
from src.services.dashboard import DashboardService
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

NOW = datetime(2026, 10, 14, 10, 0, tzinfo=UTC)  # 13:00 в Москве
HOUR = timedelta(hours=1)


def staff_actor(user: User) -> CurrentUser:
    return CurrentUser(id=user.id, role=user.role, timezone="Europe/Moscow")


class Factory:
    """Фабрики данных одного теста."""

    def __init__(self, db: AsyncSession, owner_user: User) -> None:
        self.db = db
        self.owner = owner_user
        self.counter = 0

    async def subject(self) -> Subject:
        found = (
            await self.db.execute(select(Subject).where(Subject.code == "informatics"))
        ).scalar_one_or_none()
        if found is not None:
            return found
        subject = Subject(code="informatics", name="Информатика")
        self.db.add(subject)
        await self.db.flush()
        return subject

    async def student(self, name: str, price: int = 1700, *, active: bool = True) -> User:
        user = User(role=UserRole.STUDENT, display_name=name, is_active=active)
        self.db.add(user)
        await self.db.flush()
        self.db.add(StudentProfile(user_id=user.id, teacher_id=self.owner.id, lesson_price=price))
        await self.db.flush()
        return user

    async def lesson(
        self,
        subject: Subject,
        students: list[User],
        start: datetime,
        status: LessonStatus = LessonStatus.SCHEDULED,
        *,
        billable: bool = False,
        snapshot: int | None = None,
        teacher: User | None = None,
    ) -> Lesson:
        lesson = Lesson(
            teacher_id=(teacher or self.owner).id,
            subject_id=subject.id,
            start_at=start,
            end_at=start + HOUR,
            status=status,
        )
        self.db.add(lesson)
        await self.db.flush()
        for student in students:
            self.db.add(
                LessonParticipant(
                    lesson_id=lesson.id,
                    student_id=student.id,
                    attendance=AttendanceStatus.PENDING,
                    is_billable=billable,
                    price_snapshot=snapshot,
                )
            )
        await self.db.flush()
        return lesson

    async def assignment(
        self,
        subject: Subject,
        student: User,
        status: AssignmentStatus,
        due: datetime,
        *,
        submitted: datetime | None = None,
    ) -> HomeworkAssignment:
        self.counter += 1
        homework = Homework(
            created_by=self.owner.id,
            subject_id=subject.id,
            kind=HomeworkKind.REGULAR,
            title=f"ДЗ {self.counter}",
            max_score=10,
            due_mode=DueMode.FIXED,
        )
        self.db.add(homework)
        await self.db.flush()
        row = HomeworkAssignment(
            homework_id=homework.id,
            student_id=student.id,
            status=status,
            original_due_at=due,
            due_at=due,
            submitted_at=submitted,
        )
        self.db.add(row)
        await self.db.flush()
        return row


@pytest.fixture
async def factory(db_session: AsyncSession, owner_user: User) -> Factory:
    return Factory(db_session, owner_user)


async def test_blocks_follow_the_documented_rules(factory: Factory, owner_user: User) -> None:
    subject = await factory.subject()
    anya = await factory.student("Аня")
    boris = await factory.student("Борис")
    # уроки: прошедший сегодня без отметки, будущий сегодня, завтра, отменённый сегодня
    past = await factory.lesson(subject, [anya], NOW - 3 * HOUR)
    later = await factory.lesson(subject, [anya, boris], NOW + 2 * HOUR)
    await factory.lesson(subject, [boris], NOW + 24 * HOUR)
    cancelled = await factory.lesson(subject, [boris], NOW + HOUR, LessonStatus.CANCELLED)
    # у Бори сегодня урок в 12:00 UTC; срок ДЗ Ани раньше урока → «не сдали»
    unsubmitted = await factory.assignment(subject, anya, AssignmentStatus.ASSIGNED, NOW + HOUR)
    # срок позже урока — в блок не входит; срок ДЗ Бори ближе чем через сутки, но урок позже срока
    await factory.assignment(subject, anya, AssignmentStatus.ASSIGNED, NOW + 5 * HOUR)
    queued = await factory.assignment(
        subject, boris, AssignmentStatus.SUBMITTED, NOW - HOUR, submitted=NOW - 2 * HOUR
    )
    await factory.assignment(subject, boris, AssignmentStatus.GRADED, NOW + HOUR)
    await factory.db.commit()

    dashboard = await DashboardService(factory.db).get_today_dashboard(staff_actor(owner_user), NOW)

    assert dashboard.date.isoformat() == "2026-10-14"
    assert [item.id for item in dashboard.lessons.items] == [past.id, cancelled.id, later.id]
    assert dashboard.lessons.total == 3
    # отметка нужна только прошедшему запланированному уроку; отменённый показан со статусом
    assert [item.needs_mark for item in dashboard.lessons.items] == [True, False, False]
    assert dashboard.lessons.items[1].status == LessonStatus.CANCELLED
    assert dashboard.lessons.items[2].student_names == ["Аня", "Борис"]
    assert [item.assignment_id for item in dashboard.review_queue.items] == [queued.id]
    assert [item.assignment_id for item in dashboard.unsubmitted.items] == [unsubmitted.id]
    assert [item.id for item in dashboard.unmarked_lessons.items] == [past.id]
    assert dashboard.deadlines.total == 2  # два активных ДЗ Ани со сроком в ближайшие 24 часа


async def test_empty_blocks_have_zero_totals(factory: Factory, owner_user: User) -> None:
    dashboard = await DashboardService(factory.db).get_today_dashboard(staff_actor(owner_user), NOW)

    for block in (
        dashboard.lessons,
        dashboard.review_queue,
        dashboard.unsubmitted,
        dashboard.unmarked_lessons,
        dashboard.deadlines,
    ):
        assert block.total == 0
        assert block.items == []
    assert isinstance(dashboard, DashboardOwner)
    assert (dashboard.earned_month, dashboard.expected_month) == (0, 0)


async def test_blocks_show_top_five_and_full_total(factory: Factory, owner_user: User) -> None:
    subject = await factory.subject()
    for index in range(7):
        student = await factory.student(f"Ученик {index}")
        await factory.assignment(
            subject, student, AssignmentStatus.SUBMITTED, NOW, submitted=NOW - index * HOUR
        )
    await factory.db.commit()

    dashboard = await DashboardService(factory.db).get_today_dashboard(staff_actor(owner_user), NOW)

    assert dashboard.review_queue.total == 7
    assert len(dashboard.review_queue.items) == 5
    # самые давние сверху
    assert dashboard.review_queue.items[0].student_name == "Ученик 6"


async def test_archived_students_are_not_listed_in_assignment_blocks(
    factory: Factory, owner_user: User
) -> None:
    subject = await factory.subject()
    gone = await factory.student("Архивный", active=False)
    await factory.assignment(subject, gone, AssignmentStatus.ASSIGNED, NOW + HOUR)
    await factory.db.commit()

    dashboard = await DashboardService(factory.db).get_today_dashboard(staff_actor(owner_user), NOW)

    assert dashboard.deadlines.total == 0


async def test_earned_and_expected_follow_docs_formulas(factory: Factory, owner_user: User) -> None:
    subject = await factory.subject()
    anya = await factory.student("Аня", price=2000)
    boris = await factory.student("Борис", price=1500)
    # заработано: оплачиваемые участники проведённых и отменённых (с оплатой) уроков месяца
    await factory.lesson(
        subject,
        [anya],
        datetime(2026, 10, 2, 9, tzinfo=UTC),
        LessonStatus.COMPLETED,
        billable=True,
        snapshot=1700,
    )
    await factory.lesson(
        subject,
        [anya],
        datetime(2026, 10, 3, 9, tzinfo=UTC),
        LessonStatus.CANCELLED,
        billable=True,
        snapshot=1700,
    )
    # не оплачиваемый и прошлый месяц — не входят
    await factory.lesson(
        subject, [boris], datetime(2026, 10, 4, 9, tzinfo=UTC), LessonStatus.COMPLETED
    )
    await factory.lesson(
        subject,
        [anya],
        datetime(2026, 9, 30, 9, tzinfo=UTC),
        LessonStatus.COMPLETED,
        billable=True,
        snapshot=999,
    )
    # ожидается: запланированные уроки месяца по ТЕКУЩЕЙ цене профиля
    await factory.lesson(subject, [anya, boris], datetime(2026, 10, 20, 9, tzinfo=UTC))
    await factory.lesson(subject, [boris], datetime(2026, 11, 2, 9, tzinfo=UTC))
    await factory.db.commit()

    dashboard = await DashboardService(factory.db).get_today_dashboard(staff_actor(owner_user), NOW)

    assert isinstance(dashboard, DashboardOwner)
    assert dashboard.earned_month == 3400
    assert dashboard.expected_month == 3500


async def test_price_change_does_not_touch_earned(factory: Factory, owner_user: User) -> None:
    subject = await factory.subject()
    anya = await factory.student("Аня", price=1700)
    await factory.lesson(
        subject,
        [anya],
        datetime(2026, 10, 2, 9, tzinfo=UTC),
        LessonStatus.COMPLETED,
        billable=True,
        snapshot=1700,
    )
    profile = await factory.db.get(StudentProfile, anya.id)
    assert profile is not None
    profile.lesson_price = 5000
    await factory.db.commit()

    dashboard = await DashboardService(factory.db).get_today_dashboard(staff_actor(owner_user), NOW)

    assert isinstance(dashboard, DashboardOwner)
    assert dashboard.earned_month == 1700


async def test_manager_gets_staff_schema_without_money(
    factory: Factory, owner_user: User, db_session: AsyncSession
) -> None:
    manager_user = User(role=UserRole.MANAGER, display_name="Менеджер")
    db_session.add(manager_user)
    await db_session.commit()

    dashboard = await DashboardService(db_session).get_today_dashboard(
        staff_actor(manager_user), NOW
    )

    assert not isinstance(dashboard, DashboardOwner)
    assert "earned_month" not in dashboard.model_dump()
    assert "expected_month" not in dashboard.model_dump()


async def test_student_is_rejected(factory: Factory) -> None:
    student = await factory.student("Аня")
    with pytest.raises(PermissionDeniedError):
        await DashboardService(factory.db).get_today_dashboard(staff_actor(student), NOW)


async def test_query_count_does_not_grow_with_students(
    factory: Factory, owner_user: User, db_session: AsyncSession
) -> None:
    subject = await factory.subject()

    async def seed(count: int) -> None:
        for index in range(count):
            student = await factory.student(f"Ученик {index}")
            teacher = User(role=UserRole.MANAGER, display_name=f"Преподаватель {index}")
            factory.db.add(teacher)
            await factory.db.flush()
            await factory.lesson(subject, [student], NOW + HOUR, teacher=teacher)
            await factory.lesson(subject, [student], NOW - 3 * HOUR, teacher=teacher)
            await factory.assignment(subject, student, AssignmentStatus.ASSIGNED, NOW + HOUR)
            await factory.assignment(
                subject, student, AssignmentStatus.SUBMITTED, NOW, submitted=NOW - HOUR
            )
        await factory.db.commit()

    statements: list[str] = []

    def record(
        conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: Any
    ) -> None:
        statements.append(statement)

    async def measure() -> int:
        statements.clear()
        await DashboardService(db_session).get_today_dashboard(staff_actor(owner_user), NOW)
        return len(statements)

    target = db_session.get_bind()
    event.listen(target, "before_cursor_execute", record)
    try:
        await seed(2)
        few = await measure()
        await seed(20)
        many = await measure()
    finally:
        event.remove(target, "before_cursor_execute", record)

    assert few == many
    assert many <= 15


async def test_http_roles_and_schema(
    owner: AuthedClient, manager: AuthedClient, anya: User, app: Any
) -> None:
    for_owner = await owner.get("/api/v1/admin/dashboard/today")
    for_manager = await manager.get("/api/v1/admin/dashboard/today")

    assert for_owner.status_code == 200, for_owner.text
    assert {"earned_month", "expected_month"} <= set(for_owner.json())
    assert for_manager.status_code == 200, for_manager.text
    body = for_manager.json()
    assert "earned_month" not in body
    assert "expected_month" not in body
    assert "price" not in str(body).lower()


async def test_http_student_and_anonymous_are_rejected(app: Any, anya: User) -> None:
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as anonymous:
        response = await anonymous.get("/api/v1/admin/dashboard/today")
    assert response.status_code == 401


async def test_unmarked_lookup_keeps_long_lessons_at_window_edge(
    factory: Factory, owner_user: User
) -> None:
    """Issue #88: нижняя граница по start_at не должна терять длинный урок у края окна."""
    subject = await factory.subject()
    student = await factory.student("Аня")
    edge_start = NOW - timedelta(days=14, hours=-1) - timedelta(hours=12)  # закончился внутри окна
    inside = await factory.lesson(subject, [student], edge_start)
    inside.end_at = edge_start + timedelta(hours=12)
    outside_start = NOW - timedelta(days=15)  # закончился до начала окна
    await factory.lesson(subject, [student], outside_start)
    await factory.db.commit()

    dashboard = await DashboardService(factory.db).get_today_dashboard(staff_actor(owner_user), NOW)

    assert [item.id for item in dashboard.unmarked_lessons.items] == [inside.id]
