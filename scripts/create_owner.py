"""Создание первого владельца (задача T1.09, docs/05 §3.2).

Берёт ``OWNER_TELEGRAM_ID`` из настроек (``.env.local`` / окружение) и создаёт
пользователя с ролью ``owner``, если владельца ещё нет. Идемпотентно:
повторный запуск не создаёт дублей и не меняет существующего владельца.

Запуск: ``uv run python scripts/create_owner.py``.
"""

import asyncio
import sys
from pathlib import Path

# Позволяет запускать скрипт напрямую: корень репозитория — в sys.path.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from redis.asyncio import Redis  # noqa: E402
from src.core.config import Settings  # noqa: E402
from src.db.session import create_engine, create_session_factory  # noqa: E402
from src.services.bootstrap import ensure_owner_from_settings  # noqa: E402


async def run(settings: Settings) -> bool:
    """Создать владельца; вернуть ``True``, если он создан сейчас."""
    engine = create_engine(settings.database_url)
    redis = Redis.from_url(settings.redis_url)
    try:
        return await ensure_owner_from_settings(settings, create_session_factory(engine), redis)
    finally:
        await redis.aclose()
        await engine.dispose()


def main() -> int:
    """Точка входа CLI."""
    settings = Settings()
    if settings.owner_telegram_id is None:
        print("OWNER_TELEGRAM_ID не задан: владелец не создан.")
        return 1
    created = asyncio.run(run(settings))
    print("Владелец создан." if created else "Владелец уже существует: ничего не изменено.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
