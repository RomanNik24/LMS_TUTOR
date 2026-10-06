"""Создание тестового ученика и ссылки-приглашения для разработки (задача T1.14a).

Создаёт ученика (профиль + приглашение через ``AuthService``) и печатает
одноразовую ссылку ``https://t.me/<бот>?start=inv_<token>``. Только для
локальной разработки: при ``APP_ENV=prod`` скрипт отказывается работать.

``StudentService`` появится в T2.02; до тех пор ученик и профиль создаются
репозиториями слоя данных (не прямым SQL), приглашение — сервисом ``AuthService``.
Нужен владелец (``scripts/create_owner.py``): он становится ведущим преподавателем.

Запуск::

    uv run python scripts/dev_create_student.py --name "Аня" --timezone Europe/Moscow

Имя бота берётся из ``--bot-username``; если не задано, запрашивается у Telegram
методом ``getMe`` (нужен ``BOT_TOKEN`` в ``.env.local``).
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Позволяет запускать скрипт напрямую: корень репозитория — в sys.path.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from redis.asyncio import Redis  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402
from src.bot.client import build_bot  # noqa: E402
from src.core.config import Settings  # noqa: E402
from src.core.constants import APP_ENV_PROD  # noqa: E402
from src.core.current_user import CurrentUser  # noqa: E402
from src.core.enums import UserRole  # noqa: E402
from src.core.rate_limit import RateLimiter  # noqa: E402
from src.core.session_store import SessionStore  # noqa: E402
from src.db.models import StudentProfile, User  # noqa: E402
from src.db.session import create_engine, create_session_factory, session_scope  # noqa: E402
from src.repositories.student_profiles import StudentProfileRepository  # noqa: E402
from src.repositories.users import UserRepository  # noqa: E402
from src.services.auth import AuthService  # noqa: E402

DEFAULT_NAME = "Тестовый ученик"
DEFAULT_TIMEZONE = "Europe/Moscow"
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_REFUSED = 2


class DevScriptError(Exception):
    """Понятная пользователю ошибка скрипта (печатается без трейсбека)."""


def build_invite_link(bot_username: str, token: str) -> str:
    """Ссылка-приглашение ``https://t.me/<бот>?start=inv_<token>`` (docs/09 §2.1)."""
    return f"https://t.me/{bot_username.lstrip('@')}?start=inv_{token}"


def validate_timezone(name: str) -> str:
    """Проверить IANA-пояс; вернуть его же или бросить ``DevScriptError``."""
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise DevScriptError(f"Неизвестный часовой пояс: {name!r}") from error
    return name


async def create_test_student(
    session: AsyncSession,
    redis: Redis,
    *,
    name: str,
    timezone: str,
) -> tuple[int, str]:
    """Создать ученика с профилем и выпустить приглашение.

    Args:
        session: Сессия БД.
        redis: Клиент Redis (нужен ``AuthService``).
        name: Отображаемое имя ученика.
        timezone: IANA-пояс ученика.

    Returns:
        Пара (``user_id`` ученика, токен приглашения).

    Raises:
        DevScriptError: Нет владельца или неверные данные.
    """
    if not name.strip():
        raise DevScriptError("Имя ученика не может быть пустым")
    validate_timezone(timezone)
    users = UserRepository(session)
    owner = await users.get_first_by_role(UserRole.OWNER)
    if owner is None:
        raise DevScriptError("Нет владельца: сначала выполните scripts/create_owner.py")
    student = await users.add(
        User(role=UserRole.STUDENT, display_name=name.strip(), timezone=timezone)
    )
    await StudentProfileRepository(session).add(
        StudentProfile(user_id=student.id, teacher_id=owner.id)
    )
    await session.commit()
    service = AuthService(session, SessionStore(redis), RateLimiter(redis))
    actor = CurrentUser(id=owner.id, role=owner.role, timezone=owner.timezone)
    issued = await service.create_invite(actor, student.id)
    return student.id, issued.token


async def resolve_bot_username(settings: Settings, explicit: str | None) -> str:
    """Имя бота из параметра либо из ``getMe`` (токен остаётся только в клиенте)."""
    if explicit:
        return explicit.lstrip("@")
    bot = build_bot(settings)
    if bot is None:
        raise DevScriptError("Укажите --bot-username или задайте BOT_TOKEN в .env.local")
    try:
        me = await bot.get_me()
    finally:
        await bot.session.close()
    if not me.username:
        raise DevScriptError("Telegram не вернул username бота")
    return me.username


async def run(settings: Settings, args: argparse.Namespace) -> str:
    """Создать ученика и вернуть ссылку-приглашение."""
    validate_timezone(args.timezone)
    bot_username = await resolve_bot_username(settings, args.bot_username)
    engine = create_engine(settings.database_url)
    redis = Redis.from_url(settings.redis_url)
    try:
        factory = create_session_factory(engine)
        async with session_scope(factory) as session:
            _, token = await create_test_student(
                session, redis, name=args.name, timezone=args.timezone
            )
    finally:
        await redis.aclose()
        await engine.dispose()
    return build_invite_link(bot_username, token)


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Разобрать параметры командной строки."""
    parser = argparse.ArgumentParser(description="Создать тестового ученика и ссылку-приглашение")
    parser.add_argument("--name", default=DEFAULT_NAME, help="имя ученика")
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE, help="IANA-пояс ученика")
    parser.add_argument("--bot-username", default=None, help="username бота (иначе getMe)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Точка входа CLI."""
    # Проверка окружения ДО загрузки настроек и любых подключений.
    if os.environ.get("APP_ENV") == APP_ENV_PROD:
        print("Отказ: скрипт только для разработки, при APP_ENV=prod он не запускается.")
        return EXIT_REFUSED
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        link = asyncio.run(run(Settings(), args))
    except DevScriptError as error:
        print(f"Ошибка: {error}")
        return EXIT_ERROR
    print("Ссылка-приглашение (одноразовая, действует 7 дней):")
    print(link)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
