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

## Полный локальный стек (профиль `full`)

Профиль `full` поднимает backend (`app`), Nginx со сборкой фронтенда, а также `worker` и `scheduler` (TaskIQ: напоминания, утренняя сводка, истечение ДЗ) — так же, как будет на сервере. `scheduler` всегда ровно один.
Nginx слушает `http://127.0.0.1:8080`: раздаёт SPA и проксирует `/api/`, `/telegram/`, `/health` на `app`.
Адреса БД, Redis и MinIO для контейнера `app` задаёт `docker-compose.yml` (по именам сервисов).

```bash
# останови backend на хосте: app займёт порт 8000, а второй polling бота не нужен
docker compose --env-file .env.local --profile full up -d --build
docker compose --profile full ps              # postgres, redis, minio, app, nginx — healthy; worker и scheduler — Up
curl http://127.0.0.1:8080/health             # через Nginx → app
docker compose --profile full exec app alembic upgrade head   # миграции (разово)
docker compose --profile full exec app python scripts/seed_reference.py
docker compose --profile full exec app python scripts/create_owner.py
```

- `VITE_BOT_USERNAME` (username бота без `@`) вшивается в сборку фронтенда: задайте его в `.env.local`
  (или переменной окружения) до `--build`.
- `PUBLIC_BASE_URL` в `.env.local` — адрес, по которому открывают приложение: `http://127.0.0.1:8080`
  или адрес туннеля (`scripts/dev_tunnel.sh 8080`).
- IP клиента для лимита `/auth/*` — адрес соединения с Nginx: `X-Forwarded-For` от клиента не
  принимается (подделка невозможна). Локально Docker Desktop показывает Nginx адрес шлюза Docker
  для всего, что приходит с хоста (и через туннель), поэтому лимит там общий; на сервере Nginx
  смотрит в интернет напрямую и видит реальный адрес.
- Конфигурация Nginx — `nginx/conf.d/default.conf` и `nginx/snippets/`. Заголовки безопасности
  (CSP, `nosniff`, `Referrer-Policy`) уже включены; TLS и HSTS добавляются на сервере (T9.02).
- `worker` и `scheduler` берут `BOT_TOKEN` из `.env.local`: с токеном уведомления уходят в Telegram по-настоящему (получателям с привязанным Telegram). Чтобы ничего не отправлять, запускайте воркер с пустым `BOT_TOKEN`.
- `S3_PUBLIC_ENDPOINT` передаётся и `app`, и `nginx`: на этот адрес ведут подписанные ссылки на фото, и он же разрешён в CSP (`img-src`).
- Остановить: `docker compose --profile full down`.

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

## Сквозные тесты (E2E)

Playwright проверяет сценарий «вход → сдача ДЗ → оценка → уведомления» на полном стеке. В `pnpm test`
и CI они не входят: нужен запущенный стек и подставной Telegram. Вход выполняется по `initData`,
подписанному **тестовым** токеном бота (`100000:E2E_TEST_TOKEN_NOT_REAL`, не настоящий), поэтому
сервер ничего не подменяет. Запускайте только на отдельной базе для E2E, не на рабочей.

1. Стек с тестовыми настройками (отдельная база, `BOT_TOKEN` — тестовый,
   `TELEGRAM_API_BASE=http://host.docker.internal:18081` — адрес подставного Telegram, который
   поднимает сам тест; рассылка уведомлений идёт задачей раз в минуту, поэтому тест ждёт до 2,5 мин).
2. Справочники и пользователи E2E (владелец и ученик с известными Telegram ID):

   ```bash
   uv run python scripts/seed_reference.py
   uv run python scripts/e2e_seed.py          # удалить: --purge
   ```

3. Браузер и запуск:

   ```bash
   cd frontend
   pnpm exec playwright install chromium
   pnpm e2e                                   # E2E_BASE_URL по умолчанию http://127.0.0.1:8080
   ```

Переменные (значения по умолчанию подходят для описанной выше схемы): `E2E_BASE_URL`,
`E2E_BOT_TOKEN`, `E2E_OWNER_TG_ID`, `E2E_STUDENT_TG_ID`, `E2E_TELEGRAM_MOCK_PORT`. Отчёт —
`frontend/e2e-report`, видео и трассировки упавших сценариев — `frontend/e2e-results`.
