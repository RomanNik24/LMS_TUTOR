# 03. Архитектура и структура проекта

ИИ-агенты обязаны строго следовать этому распределению логики.

## 1. Принципы
1. **API-first.** Ядро — бэкенд на FastAPI. Он единственный, кто работает с БД, S3 и содержит бизнес-логику.
2. **Три клиента ядра:**
   - **Telegram-бот** (Aiogram) — вызывает `services/` напрямую, в одном процессе с API.
   - **Веб-интерфейс** (React SPA) — общается с бэкендом только по REST `/api/v1`.
   - **Воркер** (TaskIQ) — вызывает `services/` напрямую.
3. **Слоистая архитектура бэкенда:** `api/ bot/ worker` → `services/` → `repositories/` → `db/models`.
4. **Все права проверяет сервер.** Фронтенд может скрывать кнопки, но безопасность обеспечивает только бэкенд.
5. **Независимость ядра от мессенджера.** Сервисы не импортируют `aiogram`; сообщения идут через интерфейс `Notifier`.
6. **Время:** в БД и API — UTC; форматирование в часовом поясе пользователя делает фронтенд.
7. **Фронтенд не содержит бизнес-правил.** Расчёты (оценки, конвертация баллов, заработок, дедлайны, лимит переносов) выполняет бэкенд. Фронтенд показывает результат.

## 2. Схема потоков

```
                         ┌──────────────── Nginx (HTTPS) ─────────────────┐
Браузер / Mini App ────▶ │ /            → статика React (frontend/dist)    │
                         │ /api/*       → FastAPI                          │
Telegram ──webhook─────▶ │ /telegram/*  → FastAPI (Aiogram)                │
                         └─────────────────────────────────────────────────┘

[FastAPI routers /api/v1] ─┐
[Aiogram handlers]       ──┼─▶ services/ ─▶ repositories/ ─▶ PostgreSQL
[TaskIQ tasks]           ──┘       │
                                   ├─▶ S3 (файлы)
                                   └─▶ Notifier ─▶ TelegramNotifier ─▶ Bot API
Redis: сессии, FSM, брокер очереди, rate limiting
```

## 3. Структура монорепозитория

```
my_lms/
├── .github/workflows/        # CI/CD
├── docs/                     # Документация 00–12
├── src/                      # БЭКЕНД (Python)
│   ├── main.py               # Точка входа: FastAPI + lifespan + Aiogram
│   ├── api/                  # Роутеры /api/v1/*, зависимости (auth, rate limit), webhook, /health
│   ├── bot/                  # Aiogram: handlers/, keyboards/, middlewares/, filters/, states/, client.py
│   ├── services/             # Бизнес-логика
│   ├── repositories/         # Доступ к БД
│   ├── schemas/              # Pydantic-схемы запросов и ответов (из них строится OpenAPI)
│   ├── db/                   # base.py, session.py, models/, migrations/ (Alembic, путь src/db/migrations/)
│   ├── core/                 # config.py, logging.py, exceptions.py, security.py, texts.py, timeutils.py, enums.py
│   └── worker/               # broker.py, tasks/
├── frontend/                 # ФРОНТЕНД (TypeScript) — подробно в 12_frontend_guide.md
│   ├── src/
│   ├── public/
│   ├── package.json
│   └── vite.config.ts
├── tests/                    # Тесты бэкенда: unit/, integration/
├── scripts/                  # create_owner.py, backup.sh и т. п.
├── nginx/                    # Конфиги Nginx
├── pyproject.toml, uv.lock
├── alembic.ini               # конфиг Alembic (ревизии — в src/db/migrations/)
├── .env.example
├── .pre-commit-config.yaml
├── docker-compose.yml        # local
├── docker-compose.prod.yml
├── Dockerfile                # бэкенд
├── frontend/Dockerfile       # сборка фронтенда → образ nginx со статикой
└── README.md
```

## 4. Слои бэкенда

| Слой | Папка | Можно | Нельзя |
|---|---|---|---|
| Интерфейсы | `api/`, `bot/`, `worker/` | Вызывать `services/`, `schemas/`, `core/` | SQLAlchemy, `repositories/`, бизнес-правила |
| Бизнес-логика | `services/` | Вызывать `repositories/`, `Notifier`, S3; управлять транзакцией | Импортировать `aiogram`/`fastapi`; знать про HTTP |
| Доступ к данным | `repositories/` | `select/insert/update/delete`, `flush` | `commit`, бизнес-правила |
| Модели | `db/models/` | Описание таблиц | Бизнес-логика |
| Схемы | `schemas/` | Pydantic-модели запросов/ответов | Логика |
| Ядро | `core/` | Конфиг, исключения, утилиты | Зависеть от других слоёв |

Роутеры `api/` тонкие: разбор запроса (Pydantic) → зависимость `current_user` → вызов сервиса → ответ (схема ответа). Схемы ответов **разные для ученика и персонала** (см. `08`).

## 5. Паттерн Repository
- Один класс на сущность (`UserRepository`, `LessonRepository`, …).
- Принимает `AsyncSession` в конструкторе.
- Сложные выборки (дашборд, статистика) — отдельные именованные методы.

## 6. Транзакции (Unit of Work)
- Сессия создаётся на запрос (зависимость FastAPI), на событие бота (middleware), на задачу воркера.
- **Commit делает только сервисный слой.** Репозитории делают `flush`.
- При исключении — `rollback` и лог.
- Побочные эффекты наружу (сообщения, запись в S3) выполняются после коммита или через outbox `notifications`.

## 7. Сессии и авторизация
- Вход: `POST /api/v1/auth/telegram` (Mini App, `initData`) или `POST /api/v1/auth/link` (одноразовая ссылка в браузере).
- Сервер создаёт запись сессии в **Redis** (случайный идентификатор 256 бит, TTL), отдаёт cookie `HttpOnly; Secure; SameSite=Lax; Path=/`.
- Каждый запрос: зависимость `current_user` читает cookie → Redis → пользователь из БД (роль, активность).
- Выход, архивация пользователя или смена `telegram_id` удаляют его сессии.
- Фронтенд и API на **одном домене** (Nginx), поэтому CORS не нужен и cookie первичные (first-party).
- Если при тестировании Telegram-WebView на каком-то устройстве cookie блокируются, запасной вариант: короткоживущий bearer-токен в памяти приложения. Решение принимается по результатам прототипа (этап 0), без заблаговременного усложнения.

## 8. Доставка уведомлений (outbox)
1. Событие (выдано ДЗ, отменён урок …) → сервис вставляет запись в `notifications` (`pending`, `scheduled_for`, `dedup_key`) в той же транзакции.
2. Scheduler раз в минуту запускает `dispatch_due_notifications`: выбирает `pending` с `scheduled_for <= now`, проверяет актуальность и тихие часы, отправляет через `Notifier`, помечает `sent/failed/skipped`.
3. Периодические напоминания создаются задачами-генераторами через `INSERT … ON CONFLICT DO NOTHING` с `dedup_key` вида `lesson_reminder:{lesson_id}:{student_id}:{start_epoch}`. Перенос урока меняет `start_epoch`, поэтому напоминание создаётся заново.
4. `TelegramForbiddenError` → `users.bot_blocked = true`, уведомление `skipped`.
5. До 3 повторов с растущей паузой, затем `failed` и запись в Sentry.

## 9. Периодические задачи (TaskIQ scheduler)

| Задача | Периодичность | Что делает |
|---|---|---|
| `dispatch_due_notifications` | каждую минуту | Отправка накопленных уведомлений |
| `generate_lesson_reminders` | каждую минуту | Напоминания за 30 минут до уроков |
| `generate_homework_reminders` | каждые 5 минут | Напоминания за 24 ч до дедлайна ДЗ |
| `expire_homework_assignments` | каждые 5 минут | `expired` при дедлайне и исчерпанных переносах |
| `notify_unmarked_lessons` | каждые 15 минут | Напоминание персоналу об уроках без отметки |
| `generate_scheduled_lessons` | ежедневно в 03:00 | Дозаполнение уроков по шаблонам |
| `send_morning_digest` | каждый час (проверяет, у кого сейчас 08:00) | Утренняя сводка персоналу |
| `cleanup_tokens` | ежедневно | Удаление просроченных токенов и временных файлов |
| `heartbeat` | каждые 5 минут | Пинг Healthchecks (жив ли воркер) |

## 10. Файлы (S3)
- Ключи: `homework/{assignment_id}/{uuid}.{ext}`, материалы преподавателя: `materials/{homework_id}/{uuid}.{ext}`.
- Бакет приватный. Чтение — только через presigned URL с TTL 5–15 минут, выдаётся после проверки прав (`GET /api/v1/files/{id}/url`).
- Загрузка идёт **через API** (multipart): валидация размера и типа → HEIC в JPEG → сжатие (длинная сторона ≤ 2400 px, JPEG 85) → S3 → запись в `homework_files`.
- Антивирус в MVP не используется; ограничиваем типы и размер.

## 11. Обработка ошибок
- Кастомные исключения в `core/exceptions.py`: `AppError`, `NotFoundError`, `PermissionDeniedError`, `ValidationError`, `ConflictError`, `BusinessRuleError`, `ExternalServiceError`.
- Глобальные обработчики FastAPI переводят их в единый JSON-формат ошибок и коды HTTP (`08`).
- Бот переводит их в понятные сообщения (`core/texts.py`).
- Неожиданные ошибки: лог `ERROR` с трейсбеком + Sentry + нейтральное сообщение клиенту.

## 12. Точка входа бэкенда (`src/main.py`)
1. Создаёт `FastAPI` с `lifespan`.
2. В lifespan: Sentry, Redis, S3-клиент, Aiogram `Dispatcher`; в режиме `webhook` вызывает `set_webhook`, в `polling` запускает polling фоновой задачей.
3. Подключает роутеры `api/`, обработчики ошибок, middleware (request id, проверка `Origin`).
4. Воркер и scheduler запускаются отдельными процессами.

## 13. Фронтенд (кратко)
Одностраничное приложение (SPA) на React. Подробно — `12_frontend_guide.md`.
- Маршруты: `/app/*` (ученик), `/admin/*` (персонал), `/login/:token` (вход по ссылке).
- Один бандл на обе роли; код админ-части подгружается лениво (`React.lazy`), чтобы ученик не скачивал лишнее.
- Определение режима: если есть `Telegram.WebApp.initData` — вход через `initData`, иначе — экран «Откройте приложение через бота / используйте ссылку входа».
- Nginx отдаёт `index.html` для любых маршрутов SPA (`try_files … /index.html`).

## 14. Контракт API ↔ фронтенд
- Источник истины — Pydantic-схемы бэкенда → OpenAPI (`/openapi.json`).
- Фронтенд генерирует типы командой `pnpm gen:api` в `frontend/src/api/schema.d.ts` (файл не правится вручную).
- Изменение схемы бэкенда без перегенерации типов ломает сборку фронтенда: это защита от рассинхронизации (проверка в CI).

## 15. Масштабирование и будущее
- Несколько преподавателей: `teacher_id` уже в моделях, изоляция добавляется фильтром в репозиториях.
- Другие мессенджеры (MAX): реализация `Notifier` и адаптер входа; сервисы и фронтенд не меняются.
- Родители: таблица `guardians` создана, функционала нет.
