"""Rate limiting на Redis (задача T1.08, docs/08 §10).

Фиксированное окно: счётчик ``INCR`` + ``EXPIRE`` при первом обращении.
Лимиты: ``/auth/*`` — 10 запросов в минуту на IP; остальное — 120 в минуту
на пользователя. При превышении — 429 ``rate_limited``.
"""

from redis.asyncio import Redis

from src.core.constants import RATE_LIMIT_KEY_PREFIX, RATE_LIMIT_WINDOW_SECONDS
from src.core.exceptions import AppError


class RateLimiter:
    """Счётчик запросов в окне на ключ."""

    def __init__(self, redis: Redis) -> None:
        """Сохранить клиента Redis."""
        self._redis = redis

    async def hit(self, scope: str, subject: str, limit: int) -> None:
        """Засчитать запрос и отклонить, если лимит окна превышен.

        Args:
            scope: Группа лимита (``auth``, ``user``).
            subject: Кого считаем (IP или ``user_id``).
            limit: Максимум запросов в окне.

        Raises:
            AppError: 429 ``rate_limited``.
        """
        key = f"{RATE_LIMIT_KEY_PREFIX}{scope}:{subject}"
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, RATE_LIMIT_WINDOW_SECONDS, nx=True)
            count, _ = await pipe.execute()
        if int(count) > limit:
            raise AppError(
                "Слишком много запросов. Попробуйте позже.",
                code="rate_limited",
                http_status=429,
            )
