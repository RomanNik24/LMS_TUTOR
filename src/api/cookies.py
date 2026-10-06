"""Cookie сессии (задача T1.08, docs/09 §2.3).

``HttpOnly; Secure; SameSite=Lax; Path=/``. Флаг ``Secure`` управляется
настройкой ``SESSION_COOKIE_SECURE`` (отключать можно только в ``local``).
"""

from fastapi import Response

from src.core.constants import SESSION_COOKIE_NAME


def set_session_cookie(
    response: Response, session_id: str, ttl_seconds: int, *, secure: bool
) -> None:
    """Поставить cookie сессии.

    Args:
        response: Ответ FastAPI.
        session_id: Идентификатор сессии.
        ttl_seconds: Время жизни cookie, секунды.
        secure: Флаг ``Secure``.
    """
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        max_age=ttl_seconds,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response, *, secure: bool) -> None:
    """Удалить cookie сессии (выход)."""
    response.delete_cookie(
        key=SESSION_COOKIE_NAME, path="/", httponly=True, secure=secure, samesite="lax"
    )
