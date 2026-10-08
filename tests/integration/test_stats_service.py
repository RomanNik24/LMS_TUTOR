"""Отчёты по ученику (T6.04, docs/04 §11): формулы на фиксированных данных."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.current_user import CurrentUser
from src.core.enums import (
    AssignmentStatus,
    AttendanceStatus,
    DueMode,
    ExamKind,
    ExamResultKind,
    HomeworkKind,
    LessonStatus,
    UserRole,
)
from src.core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from src.db.models import (
    ExamType,
    Homework,
    HomeworkAssignment,
    Lesson,
    LessonParticipant,
    MockExamResult,
    StudentProfile,
    Subject,
    User,
)
from src.services.stats import StatsService

TZ = "Asia/Vladivostok"  # UTC+10: границы недели и суток отличаются от UTC
START = datetime(2026, 10, 1, tzinfo=UTC)
END = datetime(2026, 11, 1, tzinfo=UTC)


def utc(day: int, hour: int, month: int = 10) -> datetime:
    return datetime(2026, month, day, hour, tzinfo=UTC)


DEFAULT_DEADLINE = utc(10, 12)


class World:
    """Ученик, преподаватель и фабрики данных для одного теста."""

    def __init__(self, db: AsyncSession, owner: User, student: User, subject: Subject) -> None:
        self.db = db
        self.owner = owner
        self.student = student
        self.subject = subject

    async def assignment(
        self,
        status: AssignmentStatus,
        *,
        max_score: int = 10,
        score: int | None = None,
        graded_at: datetime | None = None,
        original_due_at: datetime = DEFAULT_DEADLINE,
        submitted_at: datetime | None = None,
    ) -> HomeworkAssignment:
        homework = Homework(
            created_by=self.owner.id,
            subject_id=self.subject.id,
            kind=HomeworkKind.REGULAR,
            title="ДЗ",
            max_score=max_score,
            due_mode=DueMode.FIXED,
        )
        self.db.add(homework)
        await self.db.flush()
        row = HomeworkAssignment(
            homework_id=homework.id,
            student_id=self.student.id,
            status=status,
            original_due_at=original_due_at,
            due_at=original_due_at,
            score=score,
            graded_at=graded_at,
            submitted_at=submitted_at,
        )
        self.db.add(row)
        await self.db.flush()
        return row


@pytest.fixture
async def world(db_session: AsyncSession) -> World:
    subject = Subject(code="informatics", name="Информатика")
    owner = User(role=UserRole.OWNER, display_name="Роман")
    student = User(role=UserRole.STUDENT, display_name="Аня", timezone=TZ)
    db_session.add_all([subject, owner, student])
    await db_session.flush()
    db_session.add(StudentProfile(user_id=student.id, teacher_id=owner.id))
    await db_session.commit()
    return World(db_session, owner, student, subject)


def actor(user: User) -> CurrentUser:
    return CurrentUser(id=user.id, role=user.role, timezone=user.timezone)


async def test_weekly_average_uses_iso_weeks_in_student_timezone(world: World) -> None:
    graded = AssignmentStatus.GRADED
    # Пн 5 окт 17:00 по Владивостоку и вс 11 окт 23:00 — одна неделя (с 5 окт)
    await world.assignment(graded, score=9, graded_at=utc(5, 7))
    await world.assignment(graded, score=5, graded_at=utc(11, 13))
    # 11 окт 15:00 UTC = пн 12 окт 01:00 по Владивостоку — уже следующая неделя
    await world.assignment(graded, max_score=13, score=11, graded_at=utc(11, 15))
    # вне периода, без оценки и не проверенное в расчёт не входят
    await world.assignment(graded, score=1, graded_at=utc(1, 12, month=9))
    await world.assignment(AssignmentStatus.EXPIRED, original_due_at=utc(9, 12))
    await world.assignment(AssignmentStatus.SUBMITTED, submitted_at=utc(9, 9))
    await world.db.commit()

    report = await StatsService(world.db).my_report(actor(world.student), START, END)

    assert [(p.week_start, p.average_percent, p.graded_count) for p in report.homework_weekly] == [
        (date(2026, 10, 5), 70, 2),  # (90 + 50) / 2
        (date(2026, 10, 12), 85, 1),  # 11 из 13 = 84,6 → 85
    ]
    assert report.homework_last_percent == 85
    assert report.timezone == TZ


async def test_on_time_percent_counts_submitted_graded_and_expired(world: World) -> None:
    deadline = utc(10, 12)
    ok = deadline - timedelta(hours=1)
    # вовремя: сдано до срока и ровно в срок
    await world.assignment(AssignmentStatus.GRADED, score=5, graded_at=utc(12, 1), submitted_at=ok)
    await world.assignment(AssignmentStatus.SUBMITTED, submitted_at=deadline)
    # поздно
    await world.assignment(
        AssignmentStatus.GRADED,
        score=5,
        graded_at=utc(14, 1),
        submitted_at=deadline + timedelta(hours=2),
    )
    # сгорело: в знаменателе, но не вовремя
    await world.assignment(AssignmentStatus.EXPIRED)
    # не учитываются: ещё не сдано, на доработке, срок вне периода
    await world.assignment(AssignmentStatus.ASSIGNED)
    await world.assignment(AssignmentStatus.NEEDS_REVISION)
    await world.assignment(
        AssignmentStatus.SUBMITTED,
        submitted_at=utc(2, 1, month=9),
        original_due_at=utc(3, 1, month=9),
    )
    await world.db.commit()

    report = await StatsService(world.db).my_report(actor(world.student), START, END)

    assert (report.on_time.on_time_count, report.on_time.total_count, report.on_time.percent) == (
        2,
        4,
        50,
    )


async def test_empty_report_has_no_percentages(world: World) -> None:
    report = await StatsService(world.db).my_report(actor(world.student), START, END)
    assert report.homework_weekly == []
    assert report.homework_last_percent is None
    assert (report.on_time.total_count, report.on_time.percent) == (0, None)
    assert report.mock_exams == []
    assert report.attendance.model_dump() == {
        "attended": 0,
        "no_show": 0,
        "cancelled": 0,
        "pending": 0,
    }


async def test_mock_exams_series_with_percent_for_nonstandard_maximum(world: World) -> None:
    informatics = ExamType(
        code="ege_informatics",
        subject_id=world.subject.id,
        kind=ExamKind.EGE,
        result_kind=ExamResultKind.TEST_100,
        max_primary=29,
        name="ЕГЭ — Информатика",
    )
    world.db.add(informatics)
    await world.db.flush()

    def result(
        exam_date: date, primary: int, maximum: int, converted: int | None
    ) -> MockExamResult:
        return MockExamResult(
            student_id=world.student.id,
            exam_type_id=informatics.id,
            exam_date=exam_date,
            primary_score=primary,
            max_primary=maximum,
            converted_value=converted,
            created_by=world.owner.id,
        )

    world.db.add_all(
        [
            result(date(2026, 10, 20), 20, 29, 78),
            result(date(2026, 10, 3), 20, 27, None),  # «пробник на 27 баллов»: шкала неприменима
            result(date(2026, 9, 30), 29, 29, 100),  # до периода
            result(date(2026, 11, 2), 29, 29, 100),  # после периода
        ]
    )
    await world.db.commit()

    report = await StatsService(world.db).my_report(actor(world.student), START, END)

    assert [
        (
            p.exam_date,
            p.primary_score,
            p.max_primary,
            p.converted_value,
            p.scale_applicable,
            p.percent,
        )
        for p in report.mock_exams
    ] == [
        (date(2026, 10, 3), 20, 27, None, False, 74),  # 20 / 27 = 74,07 %
        (date(2026, 10, 20), 20, 29, 78, True, 69),  # 20 / 29 = 68,97 %
    ]
    assert report.mock_exams[0].result_kind == ExamResultKind.TEST_100


async def test_attendance_counts_marks_of_lessons_in_period(world: World) -> None:
    def lesson(day: int, status: LessonStatus, hour: int) -> Lesson:
        start = utc(day, hour)
        return Lesson(
            teacher_id=world.owner.id,
            subject_id=world.subject.id,
            start_at=start,
            end_at=start + timedelta(hours=1),
            status=status,
        )

    done = lesson(6, LessonStatus.COMPLETED, 8)
    no_show = lesson(7, LessonStatus.COMPLETED, 8)
    planned = lesson(30, LessonStatus.SCHEDULED, 8)
    cancelled = lesson(8, LessonStatus.CANCELLED, 8)
    outside = lesson(1, LessonStatus.COMPLETED, 8)
    outside.start_at = utc(15, 8, month=9)
    outside.end_at = utc(15, 9, month=9)
    world.db.add_all([done, no_show, planned, cancelled, outside])
    await world.db.flush()
    for row, attendance in (
        (done, AttendanceStatus.ATTENDED),
        (no_show, AttendanceStatus.NO_SHOW),
        (planned, AttendanceStatus.PENDING),
        (cancelled, AttendanceStatus.PENDING),  # отменённый урок не считается
        (outside, AttendanceStatus.ATTENDED),  # вне периода
    ):
        world.db.add(
            LessonParticipant(lesson_id=row.id, student_id=world.student.id, attendance=attendance)
        )
    await world.db.commit()

    report = await StatsService(world.db).my_report(actor(world.student), START, END)

    assert report.attendance.model_dump() == {
        "attended": 1,
        "no_show": 1,
        "cancelled": 0,
        "pending": 1,
    }


async def test_access_rules_and_period_validation(world: World, db_session: AsyncSession) -> None:
    other = User(role=UserRole.STUDENT, display_name="Борис")
    manager = User(role=UserRole.MANAGER, display_name="Мария")
    db_session.add_all([other, manager])
    await db_session.commit()
    service = StatsService(db_session)

    # ученик: только свой отчёт, чужой запросить нельзя (метода для этого нет), персонал — любой
    staff_view = await service.student_report(actor(manager), world.student.id, START, END)
    assert staff_view.student_id == world.student.id
    with pytest.raises(PermissionDeniedError):
        await service.student_report(actor(world.student), other.id, START, END)
    with pytest.raises(PermissionDeniedError):
        await service.my_report(actor(manager), START, END)
    with pytest.raises(NotFoundError):
        await service.student_report(actor(manager), 999_999, START, END)
    with pytest.raises(NotFoundError):  # сотрудник — не ученик
        await service.student_report(actor(manager), manager.id, START, END)
    for bad_start, bad_end in ((END, START), (START, START), (START, START + timedelta(days=367))):
        with pytest.raises(ValidationError) as error:
            await service.my_report(actor(world.student), bad_start, bad_end)
        assert error.value.code == "invalid_period"
    year = await service.my_report(actor(world.student), START, START + timedelta(days=366))
    assert year.student_id == world.student.id
