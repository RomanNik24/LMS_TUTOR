"""Точка входа backend-приложения MY_LMS (docs/03 §12).

``create_app`` собирает приложение: JSON-логи с request_id, обработчики
ошибок (docs/08 §1), CSRF-проверку (docs/09 §2.3.1), CORS только в ``local``.
В ``prod`` отключены ``/docs``, ``/redoc`` и ``/openapi.json``.

Lifespan: настройки, Sentry (только при непустом ``SENTRY_DSN``, без PII),
клиент Redis и корректное закрытие Redis и движка БД. Aiogram и роутеры
``/api/v1`` подключаются в следующих задачах (T1.10, T1.11).
"""

import logging
import os
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_engine, get_redis, get_session, get_session_factory
from src.api.telegram import router as telegram_router
from src.api.v1 import api_router
from src.bot.runtime import start_bot
from src.core.config import get_settings
from src.core.constants import (
    API_V1_PREFIX,
    APP_ENV_LOCAL,
    APP_ENV_PROD,
    HEALTH_COMPONENT_ERROR,
    HEALTH_COMPONENT_OK,
    HEALTH_STATUS_DEGRADED,
    HEALTH_STATUS_OK,
    LOCAL_CORS_ORIGINS,
)
from src.core.csrf import CsrfMiddleware
from src.core.error_handlers import register_error_handlers
from src.core.logging import RequestIdMiddleware, setup_logging
from src.core.sentry import init_sentry
from src.db.session import session_scope
from src.schemas.health import HealthResponse
from src.services.bootstrap import ensure_owner_from_settings

# Логи — JSON в stdout, request_id из контекста запроса (docs/09 §4).
setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Поднять и корректно закрыть ресурсы приложения (Sentry, Redis, БД)."""
    settings = get_settings()
    init_sentry(settings)
    redis = Redis.from_url(settings.redis_url)
    app.state.redis = redis
    try:
        # Первый владелец по OWNER_TELEGRAM_ID (docs/05 §3.2); без ID — пропуск.
        await ensure_owner_from_settings(settings, get_session_factory(), redis)
        runtime = await start_bot(settings, redis, _session_scope)
        app.state.bot_runtime = runtime
        try:
            yield
        finally:
            if runtime is not None:
                await runtime.stop()
    finally:
        await redis.aclose()
        if get_engine.cache_info().currsize:
            await get_engine().dispose()


def _session_scope() -> AbstractAsyncContextManager[AsyncSession]:
    """Контекст сессии БД для бота (общая фабрика приложения)."""
    return session_scope(get_session_factory())


def _public_base_url() -> str:
    """Лениво прочитать ``PUBLIC_BASE_URL`` (только для изменяющих запросов)."""
    return get_settings().public_base_url


def create_app(app_env: str | None = None) -> FastAPI:
    """Создать приложение FastAPI.

    Args:
        app_env: Окружение; по умолчанию из переменной ``APP_ENV`` (``local``).
            Читается без полной валидации ``Settings``, чтобы приложение
            импортировалось без остальных переменных окружения.

    Returns:
        Настроенное приложение.
    """
    env = app_env if app_env is not None else os.environ.get("APP_ENV", APP_ENV_LOCAL)
    is_prod = env == APP_ENV_PROD
    app = FastAPI(
        title="MY_LMS API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if is_prod else "/docs",
        redoc_url=None if is_prod else "/redoc",
        openapi_url=None if is_prod else "/openapi.json",
    )

    # Порядок: последний добавленный — внешний. request_id снаружи, чтобы его
    # получали и ответы CSRF-отказов.
    app.add_middleware(CsrfMiddleware, public_base_url=_public_base_url)
    if env == APP_ENV_LOCAL:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(LOCAL_CORS_ORIGINS),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.middleware("http")(RequestIdMiddleware(app).dispatch)
    register_error_handlers(app)
    app.include_router(api_router, prefix=API_V1_PREFIX)
    app.include_router(telegram_router)

    @app.get(
        "/health",
        response_model=HealthResponse,
        responses={503: {"model": HealthResponse}},
        tags=["health"],
        summary="Проверка БД и Redis",
        operation_id="health_check",
    )
    async def health_check(
        response: Response,
        session: Annotated[AsyncSession, Depends(get_session)],
        redis: Annotated[Redis, Depends(get_redis)],
    ) -> HealthResponse:
        """Проверить доступность PostgreSQL и Redis.

        Returns:
            `ok` (200) либо `degraded` (503) с состоянием каждого компонента.
        """
        database = await _probe_database(session)
        redis_state = await _probe_redis(redis)
        healthy = HEALTH_COMPONENT_ERROR not in (database, redis_state)
        if not healthy:
            response.status_code = 503
        return HealthResponse(
            status=HEALTH_STATUS_OK if healthy else HEALTH_STATUS_DEGRADED,
            database=database,
            redis=redis_state,
        )

    return app


async def _probe_database(session: AsyncSession) -> str:
    """Выполнить ``SELECT 1``; при любой ошибке вернуть ``error``."""
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        logger.warning("health: PostgreSQL недоступна", exc_info=True)
        return HEALTH_COMPONENT_ERROR
    return HEALTH_COMPONENT_OK


async def _probe_redis(redis: Redis) -> str:
    """Выполнить ``PING``; при любой ошибке вернуть ``error``."""
    try:
        await redis.ping()
    except Exception:
        logger.warning("health: Redis недоступен", exc_info=True)
        return HEALTH_COMPONENT_ERROR
    return HEALTH_COMPONENT_OK


app = create_app()
