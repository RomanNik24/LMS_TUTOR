# MY_LMS — «Ромчик | ИнфоМат»

Система автоматизации работы частного преподавателя: расписание, домашние задания и пробные экзамены.
Telegram-бот и связанный с ним веб-интерфейс (Mini App) работают как единое целое.
Ученик видит свои уроки, задания и прогресс; преподаватель — ещё и аналитику и расчёт заработка.

**Статус: в разработке.**

Документация проекта: [docs/00_README_INDEX.md](docs/00_README_INDEX.md)

## Локальный запуск инфраструктуры

Локальные PostgreSQL, Redis и MinIO поднимаются через Docker Compose
(`docker-compose.yml`), а backend и frontend при разработке запускаются на хосте
(см. «Запуск для разработки» ниже). Продакшен-деплой описывается отдельно (см. `docs/10`)
и здесь не рассматривается.

1. Скопируйте шаблон настроек и заполните локальные значения
   (файл `.env.local` не коммитится в Git):

   ```bash
   cp .env.example .env.local
   ```

2. Поднимите инфраструктуру:

   ```bash
   docker compose up -d postgres redis minio minio-init
   ```

3. Проверьте состояние сервисов (все должны быть `healthy`,
   `minio-init` — успешно завершённым `exited`):

   ```bash
   docker compose ps
   ```

Сервис `app` (backend в контейнере) входит в профиль `full`:
`docker compose --profile full up -d --build`. Не запускайте его вместе с backend на хосте:
оба займут порт 8000, а при заданном `BOT_TOKEN` получится два polling одного бота.

Остановить окружение: `docker compose down` (с удалением томов данных —
`docker compose down -v`).

## Запуск для разработки

Нужны Docker, `uv`, Node 22 и `pnpm`. После шагов выше (инфраструктура поднята, `.env.local` заполнен):

```bash
uv sync                                        # зависимости backend
uv run alembic upgrade head                    # миграции
uv run python scripts/seed_reference.py        # справочники (идемпотентно)
uv run python scripts/create_owner.py          # владелец по OWNER_TELEGRAM_ID
uv run uvicorn src.main:app --reload           # backend на 127.0.0.1:8000 (+ бот в polling)
cd frontend && pnpm install && pnpm dev        # frontend на http://localhost:5173
curl http://127.0.0.1:8000/health              # {"status":"ok",...}
```

`PUBLIC_BASE_URL` в `.env.local` — адрес фронтенда (`http://localhost:5173`). Mini App открывается
только по HTTPS: туннель (`scripts/dev_tunnel.*`) и тестовый ученик (`scripts/dev_create_student.py`)
описаны в [docs/ops/DEV_TOOLS.md](docs/ops/DEV_TOOLS.md).

## База данных и миграции

Миграции Alembic лежат в `src/db/migrations/` (модели — `src/db/models/`),
конфигурация — `alembic.ini` в корне репозитория. Применить миграции:

```bash
uv run alembic upgrade head
```

## Типы API для фронтенда

Типы фронтенда генерируются из OpenAPI бэкенда и **не правятся вручную**:

```bash
cd frontend
pnpm gen:api    # export_openapi.py -> openapi-typescript -> src/api/schema.d.ts
```

Скрипт сам выгружает OpenAPI (нужны `uv` и установленные зависимости бэкенда),
файл `frontend/src/api/schema.d.ts` коммитится. После любого изменения схем или
эндпоинтов бэкенда запустите `pnpm gen:api` и закоммитьте результат. В CI шаг
«Check API types are in sync with backend» падает, если файл устарел.

## Проверка кода

Единая команда запускает все проверки проекта и печатает итог:

```bash
uv run python scripts/check.py
```

Отдельные группы: `--backend-only` (ruff, ruff format, mypy, pytest) и
`--frontend-only` (pnpm lint, typecheck, test, build).

Перед коммитом настройте локальные хуки один раз:

```bash
uv run pre-commit install
```
