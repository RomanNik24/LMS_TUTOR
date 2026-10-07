"""Серверные сессии в Redis (задача T1.08, docs/09 §2.3, docs/03 §7).

В cookie уходит только случайный идентификатор (256 бит). В Redis данные
лежат под ключом от SHA-256 идентификатора, поэтому дамп Redis не даёт
готовых cookie. Права и активность пользователя читаются из БД на каждом
запросе (``current_user``), в сессии хранится только ``user_id``.

TTL — скользящий: 30 дней для ученика, 7 дней для персонала; каждое
успешное обращение продлевает срок. Для массового удаления («архивация,
смена роли, смена telegram_id») ведётся множество сессий пользователя.
"""

import hashlib
import hmac
import json
from dataclasses import dataclass

from redis.asyncio import Redis

from src.core.constants import (
    SESSION_KEY_PREFIX,
    SESSION_TTL_STAFF_SECONDS,
    SESSION_TTL_STUDENT_SECONDS,
    USER_SESSIONS_KEY_PREFIX,
)
from src.core.enums import UserRole
from src.core.security import new_token


@dataclass(frozen=True)
class SessionData:
    """Содержимое сессии.

    Attributes:
        user_id: Владелец сессии (``users.id``).
        ttl_seconds: Срок жизни без активности для этой сессии.
    """

    user_id: int
    ttl_seconds: int


def session_ttl_seconds(role: UserRole) -> int:
    """Вернуть срок жизни сессии для роли (ученик 30 дней, персонал 7)."""
    return SESSION_TTL_STUDENT_SECONDS if role == UserRole.STUDENT else SESSION_TTL_STAFF_SECONDS


def _session_key(session_id: str, secret: str) -> str:
    """Ключ сессии в Redis: HMAC-SHA256 идентификатора с ключом ``SESSION_SECRET``.

    Без секрета дамп Redis не позволяет подобрать ключи по украденным cookie, а смена
    ``SESSION_SECRET`` делает все существующие сессии недействительными (docs/09 §8).
    """
    digest = hmac.new(secret.encode("utf-8"), session_id.encode("utf-8"), hashlib.sha256)
    return SESSION_KEY_PREFIX + digest.hexdigest()


def _user_sessions_key(user_id: int) -> str:
    return f"{USER_SESSIONS_KEY_PREFIX}{user_id}"


class SessionStore:
    """Хранилище сессий поверх ``redis.asyncio.Redis``."""

    def __init__(self, redis: Redis, secret: str = "") -> None:
        """Сохранить клиента Redis и секрет ключей.

        Args:
            redis: Асинхронный клиент Redis (``decode_responses`` не обязателен).
            secret: ``SESSION_SECRET``; в ``local`` может быть пустым.
        """
        self._redis = redis
        self._secret = secret

    async def create(self, user_id: int, role: UserRole) -> tuple[str, int]:
        """Создать сессию.

        Args:
            user_id: Владелец сессии.
            role: Роль — определяет TTL.

        Returns:
            Пара (идентификатор для cookie, TTL в секундах).
        """
        session_id = new_token()
        ttl = session_ttl_seconds(role)
        key = _session_key(session_id, self._secret)
        index_key = _user_sessions_key(user_id)
        payload = json.dumps({"user_id": user_id, "ttl": ttl})
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.set(key, payload, ex=ttl)
            pipe.sadd(index_key, key)
            pipe.expire(index_key, ttl)
            await pipe.execute()
        return session_id, ttl

    async def get(self, session_id: str) -> SessionData | None:
        """Прочитать сессию и продлить её срок (скользящее обновление).

        Args:
            session_id: Идентификатор из cookie.

        Returns:
            Данные сессии или ``None``, если её нет или она истекла.
        """
        if not session_id:
            return None
        key = _session_key(session_id, self._secret)
        raw = await self._redis.get(key)
        if raw is None:
            return None
        try:
            payload = json.loads(raw)
            data = SessionData(user_id=int(payload["user_id"]), ttl_seconds=int(payload["ttl"]))
        except (ValueError, KeyError, TypeError):
            await self._redis.delete(key)
            return None
        await self._redis.expire(key, data.ttl_seconds)
        await self._redis.expire(_user_sessions_key(data.user_id), data.ttl_seconds)
        return data

    async def delete(self, session_id: str) -> None:
        """Удалить одну сессию (выход, ``POST /auth/logout``)."""
        key = _session_key(session_id, self._secret)
        raw = await self._redis.get(key)
        await self._redis.delete(key)
        if raw is None:
            return
        try:
            user_id = int(json.loads(raw)["user_id"])
        except (ValueError, KeyError, TypeError):
            return
        await self._redis.srem(_user_sessions_key(user_id), key)

    async def delete_all_for_user(self, user_id: int) -> int:
        """Удалить ВСЕ сессии пользователя (архивация, смена роли/telegram_id).

        Args:
            user_id: Чьи сессии удалить.

        Returns:
            Число удалённых сессий.
        """
        index_key = _user_sessions_key(user_id)
        keys = await self._redis.smembers(index_key)
        names = [k.decode("utf-8") if isinstance(k, bytes) else str(k) for k in keys]
        removed = 0
        if names:
            removed = int(await self._redis.delete(*names))
        await self._redis.delete(index_key)
        return removed
