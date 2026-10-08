"""Демо-данные для проверки производительности и показа (задача T7.05).

Создаёт до 100 учеников с профилями, предметами, уроками (прошедшими, сегодняшними и будущими),
домашними заданиями в разных статусах и результатами пробников. Ведущий преподаватель — первый
владелец (``scripts/create_owner.py``); справочники должны быть засеяны
(``scripts/seed_reference.py``).

Демо-данные помечены и удаляются одной командой:

* ученик — ``telegram_username`` вида ``demo_001`` и ``telegram_id IS NULL`` (настоящий ученик
  с Telegram под признак не попадает);
* урок — ``topic = "Демо-урок"``; задание — название начинается с «Демо: ».

Запуск::

    uv run python scripts/seed_demo.py --students 100
    uv run python scripts/seed_demo.py --purge

Только для разработки: при ``APP_ENV=prod`` скрипт отказывается работать. Уведомления и сообщения
в Telegram не создаются, пользователи без Telegram.
"""

import argparse
import asyncio
import os
import random
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Позволяет запускать скрипт напрямую: корень репозитория — в sys.path.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import delete, func, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402
from src.core.config import Settings  # noqa: E402
from src.core.constants import APP_ENV_PROD  # noqa: E402
from src.core.current_user import CurrentUser  # noqa: E402
from src.core.enums import (  # noqa: E402
    AssignmentStatus,
    AttendanceStatus,
    DueMode,
    HomeworkKind,
    LessonStatus,
    SubmissionType,
    UserRole,
)
from src.core.exceptions import AppError  # noqa: E402
from src.core.timeutils import day_bounds_utc, local_date_of, to_local, utcnow  # noqa: E402
from src.db.models import (  # noqa: E402
    ExamType,
    Homework,
    HomeworkAssignment,
    Lesson,
    LessonParticipant,
    MockExamResult,
    StudentProfile,
    StudentSubject,
    Subject,
    User,
)
from src.db.session import create_engine, create_session_factory, session_scope  # noqa: E402
from src.schemas.exams import MockExamCreate  # noqa: E402
from src.services.exams import ExamService  # noqa: E402

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_REFUSED = 2

MAX_STUDENTS = 100
DEFAULT_STUDENTS = 100
DEFAULT_SEED = 20261008
WEEKS_BACK = 4
WEEKS_FORWARD = 3

DEMO_USERNAME_PREFIX = "demo_"
DEMO_TOPIC = "Демо-урок"
DEMO_HOMEWORK_PREFIX = "Демо: "

FIRST_NAMES = (
    "Аня",
    "Борис",
    "Вера",
    "Глеб",
    "Дарья",
    "Егор",
    "Жанна",
    "Захар",
    "Ирина",
    "Кирилл",
)
LAST_NAMES = (
    "Иванов",
    "Петров",
    "Сидоров",
    "Смирнов",
    "Кузнецов",
    "Попов",
    "Васильев",
    "Соколов",
    "Михайлов",
    "Новиков",
)
TIMEZONES = ("Europe/Moscow", "Asia/Yekaterinburg", "Asia/Vladivostok")
PRICES = (1500, 1700, 2000, 2200, 2500)
HOMEWORK_TITLES = ("Графы", "Системы счисления", "Логика", "Функции", "Геометрия", "Алгоритмы")
SLOT_HOURS = range(8, 21)  # начала занятий по местному времени владельца: 08:00–20:00
LESSON_MINUTES = 60
GROUP_LESSON_EVERY = 10  # каждое десятое занятие — групповое (два ученика)
RECENT_UNMARKED_HOURS = 48


class DevScriptError(Exception):
    """Понятная пользователю ошибка скрипта (печатается без трейсбека)."""


@dataclass(slots=True)
class DemoStats:
    """Сколько объектов создано (``seed``) или удалено (``purge``)."""

    students: int = 0
    lessons: int = 0
    assignments: int = 0
    mock_exams: int = 0

    def line(self) -> str:
        """Одна строка отчёта."""
        return (
            f"ученики: {self.students}, уроки: {self.lessons}, "
            f"выдачи ДЗ: {self.assignments}, пробники: {self.mock_exams}"
        )


# ---------------------------------------------------------------------------- удаление


async def _demo_student_ids(session: AsyncSession) -> list[int]:
    stmt = select(User.id).where(
        User.role == UserRole.STUDENT,
        User.telegram_id.is_(None),
        User.telegram_username.like(f"{DEMO_USERNAME_PREFIX}%"),
    )
    return list((await session.execute(stmt)).scalars())


async def purge_demo(session: AsyncSession) -> DemoStats:
    """Удалить все демо-данные (и только их). Коммит выполняет вызывающий."""
    stats = DemoStats()
    ids = await _demo_student_ids(session)
    if ids:
        stats.mock_exams = (
            await session.execute(delete(MockExamResult).where(MockExamResult.student_id.in_(ids)))
        ).rowcount
        stats.assignments = (
            await session.execute(
                delete(HomeworkAssignment).where(HomeworkAssignment.student_id.in_(ids))
            )
        ).rowcount
        await session.execute(
            delete(LessonParticipant).where(LessonParticipant.student_id.in_(ids))
        )
    has_assignments = select(HomeworkAssignment.id).where(
        HomeworkAssignment.homework_id == Homework.id
    )
    await session.execute(
        delete(Homework).where(
            Homework.title.like(f"{DEMO_HOMEWORK_PREFIX}%"), ~has_assignments.exists()
        )
    )
    has_participants = select(LessonParticipant.student_id).where(
        LessonParticipant.lesson_id == Lesson.id
    )
    stats.lessons = (
        await session.execute(
            delete(Lesson).where(Lesson.topic == DEMO_TOPIC, ~has_participants.exists())
        )
    ).rowcount
    if ids:
        await session.execute(delete(StudentSubject).where(StudentSubject.student_id.in_(ids)))
        await session.execute(delete(StudentProfile).where(StudentProfile.user_id.in_(ids)))
        stats.students = (await session.execute(delete(User).where(User.id.in_(ids)))).rowcount
    return stats


# ---------------------------------------------------------------------------- создание


def _student_name(index: int) -> str:
    first = FIRST_NAMES[index % len(FIRST_NAMES)]
    last = LAST_NAMES[(index // len(FIRST_NAMES)) % len(LAST_NAMES)]
    return f"{first} {last}"


async def _create_students(
    session: AsyncSession, owner: User, subjects: list[Subject], count: int, rng: random.Random
) -> list[tuple[User, int]]:
    students: list[tuple[User, int]] = []
    for index in range(count):
        user = User(
            role=UserRole.STUDENT,
            display_name=_student_name(index),
            telegram_username=f"{DEMO_USERNAME_PREFIX}{index + 1:03d}",
            timezone=rng.choice(TIMEZONES),
        )
        session.add(user)
        await session.flush()
        price = rng.choice(PRICES)
        session.add(
            StudentProfile(
                user_id=user.id,
                teacher_id=owner.id,
                school_class=rng.randint(8, 11),
                lesson_price=price,
            )
        )
        for subject in rng.sample(subjects, k=rng.randint(1, len(subjects))):
            session.add(StudentSubject(student_id=user.id, subject_id=subject.id))
        students.append((user, price))
    await session.flush()
    return students


async def _free_slots(session: AsyncSession, owner: User, now: datetime) -> list[datetime]:
    """Свободные часовые слоты владельца: четыре недели назад — три недели вперёд."""
    first_day = local_date_of(now - timedelta(weeks=WEEKS_BACK), owner.timezone)
    last_day = local_date_of(now + timedelta(weeks=WEEKS_FORWARD), owner.timezone)
    window_start = day_bounds_utc(first_day, owner.timezone)[0]
    window_end = day_bounds_utc(last_day + timedelta(days=1), owner.timezone)[0]
    busy_rows = await session.execute(
        select(Lesson.start_at, Lesson.end_at).where(
            Lesson.teacher_id == owner.id,
            Lesson.status != LessonStatus.CANCELLED,
            Lesson.end_at > window_start,
            Lesson.start_at < window_end,
        )
    )
    busy = [(row[0], row[1]) for row in busy_rows.all()]
    slots: list[datetime] = []
    day = first_day
    while day <= last_day:
        midnight = day_bounds_utc(day, owner.timezone)[0]
        local_midnight = to_local(midnight, owner.timezone)
        for hour in SLOT_HOURS:
            start = local_midnight.replace(hour=hour).astimezone(UTC)
            end = start + timedelta(minutes=LESSON_MINUTES)
            if all(end <= b_start or start >= b_end for b_start, b_end in busy):
                slots.append(start)
        day += timedelta(days=1)
    return slots


def _lesson_status(start: datetime, now: datetime, rng: random.Random) -> LessonStatus:
    end = start + timedelta(minutes=LESSON_MINUTES)
    if end > now:
        return LessonStatus.SCHEDULED
    if now - end < timedelta(hours=RECENT_UNMARKED_HOURS) and rng.random() < 0.3:
        return LessonStatus.SCHEDULED  # недавний урок без отметки: попадает на дашборд
    return LessonStatus.CANCELLED if rng.random() < 0.07 else LessonStatus.COMPLETED


async def _create_lessons(
    session: AsyncSession,
    owner: User,
    subjects: list[Subject],
    students: list[tuple[User, int]],
    now: datetime,
    rng: random.Random,
) -> int:
    slots = await _free_slots(session, owner, now)
    created = 0
    cursor = 0
    for number, start in enumerate(slots):
        group = number % GROUP_LESSON_EVERY == GROUP_LESSON_EVERY - 1 and len(students) > 1
        size = 2 if group else 1
        members = [students[(cursor + offset) % len(students)] for offset in range(size)]
        cursor += size
        status = _lesson_status(start, now, rng)
        end = start + timedelta(minutes=LESSON_MINUTES)
        lesson = Lesson(
            teacher_id=owner.id,
            subject_id=rng.choice(subjects).id,
            start_at=start,
            end_at=end,
            status=status,
            topic=DEMO_TOPIC,
            completed_at=end if status == LessonStatus.COMPLETED else None,
            cancelled_at=start - timedelta(hours=24) if status == LessonStatus.CANCELLED else None,
            cancelled_by=owner.id if status == LessonStatus.CANCELLED else None,
            cancel_reason="Демо" if status == LessonStatus.CANCELLED else None,
        )
        session.add(lesson)
        await session.flush()
        for user, price in members:
            session.add(_participant(lesson.id, user.id, price, status, rng))
        created += 1
    await session.flush()
    return created


def _participant(
    lesson_id: int, student_id: int, price: int, status: LessonStatus, rng: random.Random
) -> LessonParticipant:
    if status == LessonStatus.COMPLETED:
        came = rng.random() > 0.05
        return LessonParticipant(
            lesson_id=lesson_id,
            student_id=student_id,
            attendance=AttendanceStatus.ATTENDED if came else AttendanceStatus.NO_SHOW,
            is_billable=came,
            price_snapshot=price if came else None,
        )
    if status == LessonStatus.CANCELLED:
        billable = rng.random() < 0.2  # поздняя отмена остаётся оплачиваемой
        return LessonParticipant(
            lesson_id=lesson_id,
            student_id=student_id,
            attendance=AttendanceStatus.CANCELLED,
            is_billable=billable,
            price_snapshot=price if billable else None,
        )
    return LessonParticipant(lesson_id=lesson_id, student_id=student_id)


async def _create_homework(
    session: AsyncSession,
    owner: User,
    subjects: list[Subject],
    students: list[tuple[User, int]],
    now: datetime,
    rng: random.Random,
) -> int:
    created = 0
    for user, _price in students:
        for number in range(rng.randint(3, 5)):
            kind = rng.choices(
                ("graded", "submitted", "active", "overdue", "expired"), (6, 2, 3, 1, 1)
            )[0]
            due = _due_at(kind, now, rng)
            homework = Homework(
                created_by=owner.id,
                subject_id=rng.choice(subjects).id,
                kind=HomeworkKind.REGULAR,
                title=f"{DEMO_HOMEWORK_PREFIX}{rng.choice(HOMEWORK_TITLES)} {number + 1}",
                max_score=10,
                due_mode=DueMode.FIXED,
            )
            session.add(homework)
            await session.flush()
            session.add(_assignment(homework.id, user.id, owner.id, kind, due, rng))
            created += 1
    await session.flush()
    return created


def _due_at(kind: str, now: datetime, rng: random.Random) -> datetime:
    if kind == "graded":
        return now - timedelta(days=rng.randint(3, 25), hours=rng.randint(0, 12))
    if kind == "submitted":
        return now + timedelta(hours=rng.randint(-20, 70))
    if kind == "active":
        return now + timedelta(hours=rng.randint(2, 120))
    return now - timedelta(days=rng.randint(1, 10))  # overdue / expired


def _assignment(
    homework_id: int,
    student_id: int,
    owner_id: int,
    kind: str,
    due: datetime,
    rng: random.Random,
) -> HomeworkAssignment:
    base = HomeworkAssignment(
        homework_id=homework_id,
        student_id=student_id,
        status=AssignmentStatus.ASSIGNED,
        original_due_at=due,
        due_at=due,
    )
    if kind == "graded":
        submitted = due - timedelta(hours=rng.randint(1, 30))
        base.status = AssignmentStatus.GRADED
        base.submission_type = SubmissionType.FILES
        base.submitted_at = submitted
        base.score = rng.randint(3, 10)
        base.graded_at = submitted + timedelta(hours=rng.randint(2, 40))
        base.graded_by = owner_id
        base.teacher_comment = "Демо"
    elif kind == "submitted":
        base.status = AssignmentStatus.SUBMITTED
        base.submission_type = SubmissionType.SELF_REPORTED
        base.submitted_at = due - timedelta(hours=rng.randint(1, 20))
    elif kind == "expired":
        base.status = AssignmentStatus.EXPIRED
        base.expired_at = due
    return base


async def _create_mock_exams(
    session: AsyncSession,
    owner: User,
    students: list[tuple[User, int]],
    now: datetime,
    rng: random.Random,
) -> int:
    exam_types = list((await session.execute(select(ExamType))).scalars())
    service = ExamService(session)
    actor = CurrentUser(id=owner.id, role=owner.role, timezone=owner.timezone)
    created = 0
    for user, _price in students:
        for weeks_ago in rng.sample(range(1, WEEKS_BACK + 1), k=rng.randint(1, 3)):
            exam_type = rng.choice(exam_types)
            geometry = rng.randint(2, 8) if exam_type.config.get("min_geometry") else None
            score = rng.randint(max(geometry or 0, 3), exam_type.max_primary)
            try:
                await service.record_mock_result(
                    actor,
                    MockExamCreate(
                        student_id=user.id,
                        exam_type_id=exam_type.id,
                        exam_date=(now - timedelta(weeks=weeks_ago)).date(),
                        primary_score=score,
                        max_primary=exam_type.max_primary,
                        geometry_score=geometry,
                    ),
                )
            except AppError:
                continue  # пропускаем несовместимую комбинацию, демо-данные не критичны
            created += 1
    return created


async def seed_demo(
    session: AsyncSession, *, students: int, seed: int = DEFAULT_SEED, now: datetime | None = None
) -> DemoStats:
    """Создать демо-данные. Остальное в БД не меняется; коммит выполняет вызывающий.

    Raises:
        DevScriptError: Нет владельца или справочников, число учеников вне 1..100, демо уже есть.
    """
    if not 1 <= students <= MAX_STUDENTS:
        raise DevScriptError(f"Число учеников — от 1 до {MAX_STUDENTS}")
    owner = (
        (await session.execute(select(User).where(User.role == UserRole.OWNER).order_by(User.id)))
        .scalars()
        .first()
    )
    if owner is None:
        raise DevScriptError("Нет владельца: сначала выполните scripts/create_owner.py")
    subjects = list((await session.execute(select(Subject).order_by(Subject.id))).scalars())
    exam_types = (await session.execute(select(func.count()).select_from(ExamType))).scalar_one()
    if not subjects or exam_types == 0:
        raise DevScriptError("Нет справочников: сначала выполните scripts/seed_reference.py")
    if await _demo_student_ids(session):
        raise DevScriptError("Демо-данные уже есть: сначала выполните --purge")
    rng = random.Random(seed)  # noqa: S311 - детерминированные демо-данные, не криптография
    moment = now or utcnow()
    created = await _create_students(session, owner, subjects, students, rng)
    stats = DemoStats(students=len(created))
    stats.lessons = await _create_lessons(session, owner, subjects, created, moment, rng)
    stats.assignments = await _create_homework(session, owner, subjects, created, moment, rng)
    await session.commit()
    stats.mock_exams = await _create_mock_exams(session, owner, created, moment, rng)
    return stats


# ---------------------------------------------------------------------------- CLI


async def run(settings: Settings, args: argparse.Namespace) -> tuple[str, DemoStats]:
    """Выполнить создание или удаление в одной сессии."""
    engine = create_engine(settings.database_url)
    try:
        factory = create_session_factory(engine)
        async with session_scope(factory) as session:
            if args.purge:
                stats = await purge_demo(session)
                await session.commit()
                return "Удалено", stats
            stats = await seed_demo(session, students=args.students, seed=args.seed)
            return "Создано", stats
    finally:
        await engine.dispose()


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Разобрать параметры командной строки."""
    parser = argparse.ArgumentParser(description="Демо-данные: создать или удалить (--purge)")
    parser.add_argument(
        "--students", type=int, default=DEFAULT_STUDENTS, help=f"учеников, до {MAX_STUDENTS}"
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="зерно генератора")
    parser.add_argument("--purge", action="store_true", help="удалить все демо-данные")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Точка входа CLI."""
    # Проверка окружения ДО загрузки настроек и любых подключений.
    if os.environ.get("APP_ENV") == APP_ENV_PROD:
        print("Отказ: скрипт только для разработки, при APP_ENV=prod он не запускается.")
        return EXIT_REFUSED
    args = parse_args(sys.argv[1:] if argv is None else argv)
    settings = Settings()
    if settings.app_env == APP_ENV_PROD:
        print("Отказ: скрипт только для разработки, при APP_ENV=prod он не запускается.")
        return EXIT_REFUSED
    try:
        title, stats = asyncio.run(run(settings, args))
    except DevScriptError as error:
        print(f"Ошибка: {error}")
        return EXIT_ERROR
    print(f"{title}: {stats.line()}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
