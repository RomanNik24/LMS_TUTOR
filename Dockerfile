# syntax=docker/dockerfile:1
# Docker-образ backend-приложения MY_LMS (docs/02 §2, docs/10 §3).
# Multi-stage сборка: uv-этап с зависимостями + минимальный runtime-слой.
# Python 3.12 — та же версия, что в CI (.github/workflows/ci.yml); pyproject допускает >= 3.11.

# ---------- Этап builder: установка зависимостей через uv ----------
FROM python:3.12-slim-bookworm AS builder

# Версия uv закреплена (минорная ветка), без `latest`: сборка воспроизводима.
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app

# Сначала копируем только манифест и лок-файл: слой с зависимостями
# пересобирается только при их изменении (кэширование сборки).
COPY pyproject.toml uv.lock ./

# Точная установка зависимостей из lock-файла, без dev-группы.
# --no-install-project: своё пакет-приложение ставим ниже вместе с кодом.
RUN uv sync --frozen --no-dev --no-install-project

# Копируем исходный код и финализируем установку проекта в /opt/venv.
COPY src ./src
RUN uv sync --frozen --no-dev


# ---------- Этап runtime: минимальный слой ----------
FROM python:3.12-slim-bookworm AS runtime

# Непривилегированный пользователь (без shell, фиксированные uid/gid 10001).
RUN groupadd --system --gid 10001 appuser \
    && useradd --system --uid 10001 --gid appuser --no-create-home --shell /usr/sbin/nologin appuser

WORKDIR /app

# Виртуальное окружение с зависимостями из builder-слоя.
COPY --from=builder /opt/venv /opt/venv
# Код приложения (пакет src) и метаданные проекта.
COPY --from=builder /app/src ./src
# Миграции и служебные скрипты (alembic upgrade head, create_owner.py) запускаются
# в одноразовом контейнере из этого же образа (docs/10 §6).
COPY alembic.ini ./
COPY scripts ./scripts

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# .env.local (реальные секреты локальной разработки) в образ не попадает:
# он исключён через .dockerignore и .gitignore. Настройки читаются
# только из переменных окружения контейнера (docs/10 §5).

USER appuser

EXPOSE 8000

# Healthcheck проверяет GET /health (docs/02 §4, docs/10 §3).
# stdlib urllib, чтобы не добавлять зависимостей в образ.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; r = urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4); sys.exit(0 if r.status == 200 else 1)"]

# Запуск FastAPI-приложения (docs/10 §3: uvicorn src.main:app).
# --proxy-headers: реальный IP клиента берётся из X-Forwarded-For, который ставит Nginx;
# без этого лимит /auth/* (10 в минуту на IP) считался бы общим для всех на IP прокси.
# --forwarded-allow-ips "*": порт app наружу не публикуется (только внутренняя сеть Docker
# и 127.0.0.1), доверять заголовку может только Nginx.
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
