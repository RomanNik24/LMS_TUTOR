"""Пользователи для сквозных тестов Playwright (задача T8.07).

Создаёт владельца и ученика с известными Telegram ID (переменные ``E2E_OWNER_TG_ID`` и
``E2E_STUDENT_TG_ID``), чтобы тест мог войти по подписанному ``initData``. Нужны справочники
(``scripts/seed_reference.py``). Записи помечены ``telegram_username`` вида ``e2e_*`` и удаляются
командой ``--purge``.

Запуск (на отдельной базе для E2E, не на рабочей)::

    uv run python scripts/e2e_seed.py
    uv run python scripts/e2e_seed.py --purge

При ``APP_ENV=prod`` скрипт отказывается работать.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Позволяет запускать скрипт напрямую: корень репозитория — в sys.path.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import delete, func, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402
from src.core.config import Settings  # noqa: E402
from src.core.constants import APP_ENV_PROD  # noqa: E402
from src.core.enums import UserRole  # noqa: E402
from src.db.models import StudentProfile, Subject, User  # noqa: E402
from src.db.session import create_engine, create_session_factory, session_scope  # noqa: E402

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_REFUSED = 2

USERNAME_PREFIX = "e2e_"
OWNER_USERNAME = "e2e_owner"
STUDENT_USERNAME = "e2e_student"
DEFAULT_OWNER_TG_ID = 900_000_001
DEFAULT_STUDENT_TG_ID = 900_000_002
STUDENT_NAME = "E2E Ученик"
OWNER_NAME = "E2E Владелец"
LESSON_PRICE = 1500


class E2eSeedError(Exception):
    """Понятная пользователю ошибка скрипта (печатается без трейсбека)."""


async def purge_e2e(session: AsyncSession) -> int:
    """Удалить пользователей E2E и всё, что к ним привязано. Коммит выполняет вызывающий."""
    from src.db.models import (  # noqa: PLC0415 - только для удаления
        Homework,
        HomeworkAssignment,
        Notification,
    )

    ids = list(
        (
            await session.execute(
                select(User.id).where(User.telegram_username.like(f"{USERNAME_PREFIX}%"))
            )
        ).scalars()
    )
    if not ids:
        return 0
    await session.execute(delete(Notification).where(Notification.user_id.in_(ids)))
    await session.execute(delete(HomeworkAssignment).where(HomeworkAssignment.student_id.in_(ids)))
    await session.execute(delete(Homework).where(Homework.created_by.in_(ids)))
    await session.execute(delete(StudentProfile).where(StudentProfile.user_id.in_(ids)))
    return (await session.execute(delete(User).where(User.id.in_(ids)))).rowcount


async def seed_e2e(
    session: AsyncSession, *, owner_tg_id: int, student_tg_id: int
) -> tuple[int, int]:
    """Создать владельца и ученика E2E (идемпотентно). Возвращает их идентификаторы.

    Raises:
        E2eSeedError: Нет справочников или Telegram ID заняты настоящими пользователями.
    """
    if (await session.execute(select(func.count()).select_from(Subject))).scalar_one() == 0:
        raise E2eSeedError("Нет справочников: сначала выполните scripts/seed_reference.py")
    owner = await _ensure(session, OWNER_USERNAME, UserRole.OWNER, OWNER_NAME, owner_tg_id)
    student = await _ensure(
        session, STUDENT_USERNAME, UserRole.STUDENT, STUDENT_NAME, student_tg_id
    )
    if await session.get(StudentProfile, student.id) is None:
        session.add(
            StudentProfile(user_id=student.id, teacher_id=owner.id, lesson_price=LESSON_PRICE)
        )
    await session.flush()
    return owner.id, student.id


async def _ensure(
    session: AsyncSession, username: str, role: UserRole, name: str, telegram_id: int
) -> User:
    existing = (
        await session.execute(select(User).where(User.telegram_username == username))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    taken = (
        await session.execute(select(User.id).where(User.telegram_id == telegram_id))
    ).scalar_one_or_none()
    if taken is not None:
        raise E2eSeedError(f"Telegram ID {telegram_id} уже занят другим пользователем")
    user = User(role=role, display_name=name, telegram_id=telegram_id, telegram_username=username)
    session.add(user)
    await session.flush()
    return user


async def run(settings: Settings, args: argparse.Namespace) -> str:
    """Выполнить создание или удаление."""
    engine = create_engine(settings.database_url)
    try:
        factory = create_session_factory(engine)
        async with session_scope(factory) as session:
            if args.purge:
                removed = await purge_e2e(session)
                await session.commit()
                return f"Удалено пользователей E2E: {removed}"
            await seed_e2e(session, owner_tg_id=args.owner_tg_id, student_tg_id=args.student_tg_id)
            await session.commit()
            return "Готово: владелец и ученик E2E созданы"
    finally:
        await engine.dispose()


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Разобрать параметры командной строки."""
    parser = argparse.ArgumentParser(description="Пользователи для E2E: создать или удалить")
    parser.add_argument(
        "--owner-tg-id",
        type=int,
        default=int(os.environ.get("E2E_OWNER_TG_ID", DEFAULT_OWNER_TG_ID)),
    )
    parser.add_argument(
        "--student-tg-id",
        type=int,
        default=int(os.environ.get("E2E_STUDENT_TG_ID", DEFAULT_STUDENT_TG_ID)),
    )
    parser.add_argument("--purge", action="store_true", help="удалить пользователей E2E")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Точка входа CLI."""
    if os.environ.get("APP_ENV") == APP_ENV_PROD:
        print("Отказ: скрипт только для разработки, при APP_ENV=prod он не запускается.")
        return EXIT_REFUSED
    args = parse_args(sys.argv[1:] if argv is None else argv)
    settings = Settings()
    if settings.app_env == APP_ENV_PROD:
        print("Отказ: скрипт только для разработки, при APP_ENV=prod он не запускается.")
        return EXIT_REFUSED
    try:
        print(asyncio.run(run(settings, args)))
    except E2eSeedError as error:
        print(f"Ошибка: {error}")
        return EXIT_ERROR
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
