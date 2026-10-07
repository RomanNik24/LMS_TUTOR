"""Утренняя сводка персоналу на реальной PostgreSQL (T5.07, docs/05 §6.3)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.enums import (
    AssignmentStatus,
    AttendanceStatus,
    DueMode,
    HomeworkKind,
    LessonStatus,
    NotificationType,
    UserRole,
)
from src.db.models import (
    Homework,
    HomeworkAssignment,
    Lesson,
    LessonParticipant,
    Notification,
    Subject,
    User,
)
from src.services.digest import DigestService
from src.services.notification_dispatch import NotificationDispatcher
from src.services.notification_render import NotificationRenderer
from src.services.notifier import OutgoingMessage

# 14 октября 2030 (понедельник), 05:00 UTC = 08:00 по Москве = 10:00 по Екатеринбургу
NOW = datetime(2030, 10, 14, 5, 0, tzinfo=UTC)
MOSCOW = "Europe/Moscow"
YEKATERINBURG = "Asia/Yekaterinburg"


async def user(
    db: AsyncSession, name: str, role: UserRole, tg: int | None, zone: str = MOSCOW, **extra: object
) -> User:
    item = User(role=role, display_name=name, telegram_id=tg, timezone=zone, **extra)
    db.add(item)
    await db.flush()
    return item


@pytest.fixture
async def owner(db_session: AsyncSession) -> User:
    return await user(db_session, "Роман", UserRole.OWNER, 1)


@pytest.fixture
async def anya(db_session: AsyncSession) -> User:
    return await user(db_session, "Аня", UserRole.STUDENT, 11)


@pytest.fixture
async def boris(db_session: AsyncSession) -> User:
    return await user(db_session, "Борис", UserRole.STUDENT, 12)


@pytest.fixture
async def subject(db_session: AsyncSession) -> Subject:
    found = (
        await db_session.execute(select(Subject).where(Subject.code == "informatics"))
    ).scalar_one_or_none()
    if found is not None:
        return found
    item = Subject(code="informatics", name="Информатика")
    db_session.add(item)
    await db_session.flush()
    return item


async def lesson(
    db: AsyncSession,
    teacher: User,
    subject: Subject,
    start: datetime,
    students: list[User],
    **extra: object,
) -> Lesson:
    item = Lesson(
        teacher_id=teacher.id,
        subject_id=subject.id,
        start_at=start,
        end_at=start + timedelta(hours=1),
        **extra,
    )
    db.add(item)
    await db.flush()
    for student in students:
        db.add(LessonParticipant(lesson_id=item.id, student_id=student.id))
    await db.flush()
    return item


async def assignment(
    db: AsyncSession,
    teacher: User,
    subject: Subject,
    student: User,
    title: str,
    due: datetime,
    status: AssignmentStatus = AssignmentStatus.ASSIGNED,
    submitted_at: datetime | None = None,
) -> HomeworkAssignment:
    homework = Homework(
        created_by=teacher.id,
        subject_id=subject.id,
        kind=HomeworkKind.REGULAR,
        title=title,
        max_score=13,
        due_mode=DueMode.FIXED,
    )
    db.add(homework)
    await db.flush()
    row = HomeworkAssignment(
        homework_id=homework.id,
        student_id=student.id,
        original_due_at=due,
        due_at=due,
        status=status,
        submitted_at=submitted_at,
    )
    db.add(row)
    await db.flush()
    return row


async def digests(db: AsyncSession) -> list[Notification]:
    stmt = (
        select(Notification)
        .where(Notification.type == NotificationType.MORNING_DIGEST.value)
        .order_by(Notification.id)
    )
    return list((await db.execute(stmt)).scalars())


def lines_of(note: Notification) -> list[str]:
    lines = note.payload["lines"]
    assert isinstance(lines, list)
    return [str(line) for line in lines]


async def full_day(
    db: AsyncSession, owner: User, anya: User, boris: User, subject: Subject
) -> None:
    """Типичный день: два урока, отменённый урок, очередь проверки, несданное, дедлайн."""
    await lesson(db, owner, subject, NOW + timedelta(hours=9), [anya, boris])  # 17:00
    await lesson(db, owner, subject, NOW + timedelta(hours=11), [boris])  # 19:00
    await lesson(
        db, owner, subject, NOW + timedelta(hours=7), [anya], status=LessonStatus.CANCELLED
    )
    await assignment(
        db,
        owner,
        subject,
        boris,
        "Графы",
        NOW - timedelta(days=1),
        AssignmentStatus.SUBMITTED,
        submitted_at=NOW - timedelta(hours=20),
    )
    await assignment(db, owner, subject, anya, "Циклы", NOW + timedelta(hours=10))
    # прошлый урок без отметки
    await lesson(db, owner, subject, NOW - timedelta(days=2, hours=-9), [anya])


async def test_owner_gets_full_digest_at_8_local(
    db_session: AsyncSession, owner: User, anya: User, boris: User, subject: Subject
) -> None:
    await full_day(db_session, owner, anya, boris, subject)
    assert await DigestService(db_session).send_morning_digests(NOW) == 1
    (note,) = await digests(db_session)
    assert note.user_id == owner.id
    assert note.is_urgent is False
    assert note.dedup_key == f"morning_digest:{owner.id}:2030-10-14"
    lines = lines_of(note)
    assert lines[0] == "☀ Сводка на пн, 14 окт"
    assert "Уроки сегодня (2):" in lines
    assert "• 17:00 Информатика: Аня, Борис" in lines
    assert "• 19:00 Информатика: Борис" in lines
    assert "ДЗ на проверку: 1" in lines
    assert "• Борис — Графы" in lines
    assert "Не сдано к сегодняшним урокам (1):" in lines
    assert "• Аня — Циклы, срок пн, 14 окт, 18:00" in lines
    assert "Уроки без отметки (1):" in lines
    assert "Дедлайны ближайших 24 часов (1):" in lines
    assert lines[-1] == "Заработано в этом месяце: 0 ₽"


async def test_only_staff_at_their_own_8am_get_digest(
    db_session: AsyncSession, owner: User, anya: User, boris: User, subject: Subject
) -> None:
    manager = await user(db_session, "Мария", UserRole.MANAGER, 2, YEKATERINBURG)
    await user(db_session, "Без Telegram", UserRole.MANAGER, None)
    await user(db_session, "Архив", UserRole.MANAGER, 4, is_active=False)
    await full_day(db_session, owner, anya, boris, subject)
    service = DigestService(db_session)
    # 05:00 UTC: у владельца 08:00, у менеджера 10:00
    assert await service.send_morning_digests(NOW) == 1
    # 03:00 UTC: у менеджера (Екатеринбург) 08:00, а у владельца 06:00
    assert await service.send_morning_digests(NOW - timedelta(hours=2)) == 1
    recipients = {note.user_id for note in await digests(db_session)}
    assert recipients == {owner.id, manager.id}
    manager_note = next(n for n in await digests(db_session) if n.user_id == manager.id)
    assert not lines_of(manager_note)[-1].startswith("Заработано")  # финансы только владельцу


async def test_digest_is_not_duplicated_and_repeats_next_day(
    db_session: AsyncSession, owner: User, anya: User, boris: User, subject: Subject
) -> None:
    await full_day(db_session, owner, anya, boris, subject)
    service = DigestService(db_session)
    assert await service.send_morning_digests(NOW) == 1
    assert await service.send_morning_digests(NOW + timedelta(minutes=30)) == 0  # тот же час
    assert len(await digests(db_session)) == 1
    tomorrow = NOW + timedelta(days=1)
    await lesson(db_session, owner, subject, tomorrow + timedelta(hours=9), [anya])
    assert await service.send_morning_digests(tomorrow) == 1
    assert len(await digests(db_session)) == 2


async def test_empty_day_sends_nothing(db_session: AsyncSession, owner: User) -> None:
    assert await DigestService(db_session).send_morning_digests(NOW) == 0
    assert await digests(db_session) == []


async def test_review_queue_shows_count_and_top_five(
    db_session: AsyncSession, owner: User, anya: User, subject: Subject
) -> None:
    for number in range(7):
        await assignment(
            db_session,
            owner,
            subject,
            anya,
            f"Работа {number}",
            NOW + timedelta(days=9),
            AssignmentStatus.SUBMITTED,
            submitted_at=NOW - timedelta(hours=number + 1),
        )
    await DigestService(db_session).send_morning_digests(NOW)
    (note,) = await digests(db_session)
    lines = lines_of(note)
    assert "ДЗ на проверку: 7" in lines
    assert sum(line.startswith("• Аня — Работа") for line in lines) == 5
    assert "…и ещё 2" in lines
    # самые давние сдачи идут первыми
    assert "• Аня — Работа 6" in lines
    assert "• Аня — Работа 0" not in lines


async def test_owner_sees_month_earnings_only_from_billable_lessons(
    db_session: AsyncSession, owner: User, anya: User, boris: User, subject: Subject
) -> None:
    month_start = datetime(2030, 10, 1, 12, 0, tzinfo=UTC)
    lessons = [
        (month_start, anya, 1500, True),
        (month_start + timedelta(days=2), boris, 2000, True),
        (month_start + timedelta(days=3), boris, 3000, False),  # не оплачивается
        (month_start - timedelta(days=5), anya, 9000, True),  # прошлый месяц
    ]
    for start, student, price, billable in lessons:
        item = await lesson(db_session, owner, subject, start, [], status=LessonStatus.COMPLETED)
        db_session.add(
            LessonParticipant(
                lesson_id=item.id,
                student_id=student.id,
                attendance=AttendanceStatus.ATTENDED,
                is_billable=billable,
                price_snapshot=price,
            )
        )
    await lesson(db_session, owner, subject, NOW + timedelta(hours=9), [anya])
    await db_session.flush()
    await DigestService(db_session).send_morning_digests(NOW)
    (note,) = await digests(db_session)
    assert lines_of(note)[-1] == "Заработано в этом месяце: 3 500 ₽"


async def test_digest_renders_with_admin_button_and_is_sent_by_dispatcher(
    db_session: AsyncSession, owner: User, anya: User, boris: User, subject: Subject
) -> None:
    await full_day(db_session, owner, anya, boris, subject)
    await DigestService(db_session).send_morning_digests(NOW)

    class Recorder:
        def __init__(self) -> None:
            self.messages: list[tuple[int, OutgoingMessage]] = []

        async def send(self, telegram_id: int, message: OutgoingMessage) -> None:
            self.messages.append((telegram_id, message))

    recorder = Recorder()
    dispatcher = NotificationDispatcher(
        db_session, recorder, NotificationRenderer("https://lms.example.com"), pause_seconds=0
    )
    assert (await dispatcher.dispatch_due(NOW)).sent == 1
    ((telegram_id, message),) = recorder.messages
    assert telegram_id == 1
    assert "Уроки сегодня (2):" in message.text
    button = message.buttons[0][0]
    assert button.text == "Открыть Admin App"
    assert button.url == "https://lms.example.com/admin/"
