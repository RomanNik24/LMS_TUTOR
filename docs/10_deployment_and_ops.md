# 10. Развёртывание и эксплуатация

## 1. Окружения

| Окружение | Где | Бот | БД/Redis/S3 | Режим бота | Фронтенд |
|---|---|---|---|---|---|
| `local` | Ноутбук (docker-compose для БД/Redis/MinIO) | Тот же `@romchik_infomat_bot`, что и в бою (ADR 0009); после боевого запуска — отдельный dev-бот | Локальные контейнеры | `polling` | `pnpm dev` (порт 5173, прокси на бэкенд) |
| `staging` | Тот же VPS, отдельный compose-проект и поддомен | Отдельный бот из BotFather | Отдельные БД и бакет | `webhook` | Сборка в образе nginx |
| `prod` | VPS в РФ | Боевой бот | Боевая БД, S3 | `webhook` | Сборка в образе nginx |

Окружение задаётся `APP_ENV` (`local|staging|prod`). Данные окружений не смешиваются.

## 2. Сервер
- VPS в РФ (Timeweb Cloud или Selectel), Ubuntu LTS, 2 vCPU / 4 ГБ RAM / 40+ ГБ SSD.
- Docker + Docker Compose plugin.
- Файрвол (ufw): открыты 22 (SSH по ключам), 80, 443. Остальное закрыто. Вход по паролю SSH отключён, fail2ban включён.
- Пользователь деплоя без root-прав, в группе `docker`.
- Часовой пояс сервера: UTC.

## 3. Контейнеры (`docker-compose.prod.yml`)

| Сервис | Образ / команда | Примечания |
|---|---|---|
| `app` | `uvicorn src.main:app` | FastAPI (REST `/api/v1`, `/health`, вебхук) + Aiogram. Healthcheck `/health` |
| `worker` | `taskiq worker src.worker.broker:broker src.worker.tasks` | Фоновые задачи |
| `scheduler` | `taskiq scheduler src.worker.broker:scheduler src.worker.tasks` | Строго один экземпляр |
| `postgres` | `postgres:16` | Volume, наружу не публикуется |
| `redis` | `redis:7` | Persistence AOF, наружу не публикуется |
| `nginx` | Образ из `frontend/Dockerfile` | Содержит собранный фронтенд, раздаёт статику, проксирует `/api`, `/telegram`, `/health` на `app`, SSL |

### Сборка фронтенда (`frontend/Dockerfile`, multi-stage)
1. Этап `build`: образ Node LTS → `corepack enable` → `pnpm install --frozen-lockfile` → `pnpm build` (результат `dist/`).
2. Этап `runtime`: образ nginx + копирование `dist/` и конфигурации.
Переменные `VITE_*` передаются на этапе сборки (это публичные значения: имя бота и т. п.).

### Конфигурация Nginx (суть)
- `location /api/` и `location /telegram/` и `location = /health` → `proxy_pass` на `app:8000`, заголовки `X-Forwarded-*`.
- `location /` → статика; `try_files $uri /index.html` (поддержка маршрутов SPA).
- Кеш: файлы с хэшем в имени (`/assets/*`) кешируются надолго (`Cache-Control: public, max-age=31536000, immutable`); `index.html` не кешируется (`no-cache`), чтобы обновления доходили сразу.
- `client_max_body_size 12m` (загрузка файлов ДЗ до 10 МБ).
- Заголовки безопасности: HSTS, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Content-Security-Policy` (разрешить только свой домен; `frame-ancestors` — домены Telegram, чтобы Mini App открывался; точный список уточняется при тестировании в Telegram).
- Сжатие gzip/brotli для статики. WebSocket не нужен.

## 4. Домен и SSL
- Домены: `app.<домен>` — prod, `stg.<домен>` — staging.
- Сертификаты Let's Encrypt (Certbot), автообновление. HTTPS обязателен для Mini App.
- Фронтенд и API работают на **одном домене** (CORS не нужен, cookie первичные).

## 5. Конфигурация
- `.env.example` (бэкенд) и `frontend/.env.example` (`VITE_*`) в репозитории без значений.
- Реальные `.env` лежат на сервере (права 600), отдельные для `staging` и `prod`.
- GitHub Secrets: `SSH_HOST`, `SSH_USER`, `SSH_KEY`, переменные окружения деплоя.
- `BOT_MODE=polling|webhook`. Прокси к Telegram при необходимости: `TELEGRAM_PROXY_URL`, `TELEGRAM_API_BASE`.
- Эндпоинт `/openapi.json` на `prod` отключён или закрыт.

## 6. CI/CD (GitHub Actions)

**На каждый Pull Request и push в `main`** (параллельные задачи):

*Бэкенд:*
1. `uv sync --frozen`
2. `ruff check` и `ruff format --check`
3. `mypy --strict`
4. `pytest` (PostgreSQL и Redis через service containers/testcontainers)

*Фронтенд:*
1. `pnpm install --frozen-lockfile`
2. `pnpm lint`
3. `pnpm typecheck`
4. `pnpm test`
5. **Проверка актуальности типов API:** запуск бэкенда (или экспорт OpenAPI скриптом без запуска сервера) → `pnpm gen:api` → `git diff --exit-code frontend/src/api/schema.d.ts`; если файл изменился, сборка падает.
6. `pnpm build`

**При push в `main`** (после успеха обеих групп проверок):
1. Сборка Docker-образов (`app`, `nginx` с фронтендом), публикация в реестр (GHCR или реестр провайдера).
2. Деплой на `staging` по SSH: `docker compose pull && docker compose up -d`.
3. Ручное подтверждение (environment protection) → деплой на `prod`.

**Миграции:** отдельным шагом **перед** запуском новой версии: `alembic upgrade head` в одноразовом контейнере. При ошибке деплой останавливается, старая версия продолжает работать. Миграции совместимы с предыдущей версией кода (expand/contract), чтобы откат образа был безопасен. Перед критичными миграциями делается внеплановый бэкап.

**Откат:** предыдущий тег образов + `alembic downgrade`, если миграция обратима.

## 7. Бэкапы
- Ежедневно (03:30 UTC) `pg_dump` (custom format) → сжатие → загрузка в отдельный S3-бакет бэкапов, хранение **14 дней**.
- Файлы ДЗ в S3: версионирование/репликация средствами провайдера или периодическая синхронизация.
- Раз в месяц: **проверка восстановления** на staging (развернуть дамп, проверить целостность, запустить приложение).
- `scripts/backup.sh` + cron/systemd timer; сигнал в Healthchecks об успехе/ошибке.

## 8. Мониторинг
- **Sentry:** ошибки бэкенда (FastAPI, Aiogram, TaskIQ) и фронтенда (без PII; URL с токенами очищаются).
- **Uptime:** внешний мониторинг `https://<домен>/health` раз в минуту; алерты владельцу.
- **Heartbeat воркера:** задача каждые 5 минут пингует Healthchecks; нет пинга → алерт.
- **Логи:** JSON в stdout, ротация (`max-size`, `max-file`).
- **Ресурсы:** диск и память — алерты провайдера.
- Prometheus/Grafana не используются.

## 9. Доступность Telegram
- Если исходящие запросы к `api.telegram.org` недоступны с сервера, настраиваются `TELEGRAM_PROXY_URL` или `TELEGRAM_API_BASE`.
- Вебхук требует, чтобы серверы Telegram достучались до домена: мониторить `getWebhookInfo` (поле `last_error_message`).
- Деградация: уведомления накапливаются в `notifications` и повторяются, ничего не теряется; веб-интерфейс по ссылке входа продолжает работать в браузере.
- Фронтенд не зависит от внешних скриптов и шрифтов (всё отдаётся с нашего домена).

## 10. Начальная настройка проекта (чек-лист)
1. Создать ботов в BotFather (staging и prod): имя, описание, аватар, меню команд.
2. Создать VPS: пользователь, ssh-ключи, ufw, Docker.
3. Зарегистрировать домен, DNS, SSL.
4. Создать S3-бакеты (`files`, `backups`) и ключи.
5. Заполнить `.env` на сервере; `OWNER_TELEGRAM_ID` — Telegram ID владельца.
6. Настроить GitHub Secrets и environments.
7. Применить миграции и сиды (`subjects`, `exam_types`, `grade_scales`).
8. Проверить `/health`, вебхук, вход владельца, тестовое приглашение, открытие Mini App на iOS и Android.
9. Подключить Sentry и uptime-мониторинг.
10. Включить бэкапы и проверить восстановление.

## 11. Регламент обслуживания
| Периодичность | Действие |
|---|---|
| Еженедельно | Просмотр ошибок в Sentry, свободного места |
| Ежемесячно | Проверка восстановления бэкапа; обновление зависимостей (`uv lock --upgrade`, `pnpm update`) с прогоном тестов; обновление образов |
| Ежегодно (май–июнь, после публикации шкал) | Обновление `grade_scales` и `exam_types.max_primary` на следующий год |
