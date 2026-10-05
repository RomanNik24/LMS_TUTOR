# Локальная инфраструктура: проверенное окружение

Дата проверки: 2026-10-05
Задача: T0.08 (верификация локальной инфраструктуры)
Репозиторий: `RomanNik24/LMS_TUTOR`
Коммит: `d5739d0 fix(ops): build minio images from source`

Документ фиксирует фактическое состояние рабочей машины на момент проверки.
Секреты и содержимое `.env.local` здесь не приводятся.

## 1. ОС и инструменты

| Компонент | Версия |
|---|---|
| ОС | Windows 11, build 10.0.26300.0 |
| Git | 2.53.0.windows.1 |
| Python (проектная, через uv) | 3.11.9 (`requires-python = ">=3.11"` из `pyproject.toml`) |
| Системный `python` | не установлен — `C:\Users\user\AppData\Local\Microsoft\WindowsApps\python.exe`, заглушка Microsoft Store; все команды Python выполняются через `uv run` |
| uv | 0.12.23 (46b84fd0b 2026-10-03, x86_64-pc-windows-msvc) |
| Node | v24.15.0 |
| pnpm | 12.8.1 |
| Docker CLI | 29.8.0 (build 88096ef) |
| Docker Engine (server) | 29.8.0 |
| Docker Compose | v5.5.1 |

## 2. Состояние сервисов

Проект: `my-lms-local` (`docker compose up -d`)

| Сервис | Образ | Статус | Порты |
|---|---|---|---|
| postgres | `postgres:16` | Up (healthy) | `127.0.0.1:5432->5432` |
| redis | `redis:7` | Up (healthy) | `127.0.0.1:6379->6379` |
| minio | `lms-minio:RELEASE.2025-10-15T17-29-55Z` | Up (healthy) | `127.0.0.1:9000-9001->9000-9001` |
| minio-init | `lms-mc:RELEASE.2025-08-13T08-35-41Z` | Exited (0) | — |
| app | `my-lms-local-app` | Up (healthy) | `127.0.0.1:8000->8000` |

`minio-init` — одноразовый контейнер: дождался готовности MinIO, создал bucket
`lms-files`, снял anonymous-доступ и завершился с кодом `0`, как и предусмотрено
в `docker-compose.yml`.

Версии серверов:

| Компонент | Версия |
|---|---|
| PostgreSQL | 16.15 (Debian 16.15-1.pgdg13+2) |
| Redis | 7.4.11 |
| MinIO | `DEVELOPMENT.GOGET` — сборка из исходников, тег репозитория не встраивается в `minio --version` |

## 3. Результаты проверок

| Проверка | Результат |
|---|---|
| `docker compose up -d` | PASS — все сервисы поднялись |
| `pg_isready` | PASS — `/var/run/postgresql:5432 - accepting connections` |
| `redis-cli ping` | PASS — `PONG` |
| MinIO доступен | PASS — `mc ready local` → `The cluster 'local' is ready` |
| bucket `lms-files` существует | PASS — `mc ls local` → `0B lms-files/` |
| bucket приватный | PASS — `mc anonymous get local/lms-files` → `private` |
| анонимное чтение объекта | PASS — HTTP **403** на `GET /lms-files/no-such-object.txt` без авторизации |
| анонимный листинг bucket | PASS — HTTP **403** на `GET /lms-files/` |
| `GET /health` | PASS — HTTP **200**, тело `{"status":"ok"}` |
| `btree_gist` | PASS — `CREATE EXTENSION` (exit 0), установлена версия **1.7** |

### Доступ к PostgreSQL

В задании указана команда от роли `postgres` к БД `my_lms`. В `docker-compose.yml`
заданы другие значения, поэтому команда в исходном виде не выполняется:

```
FATAL:  role "postgres" does not exist
```

Фактические параметры: пользователь `lms`, база данных `lms`. Безопасные тестовые
значения, соответствующие `docker-compose.yml`; пароль здесь не приводится.

Расширение установлено командой:

```
docker compose exec postgres psql -U lms -d lms -c "CREATE EXTENSION IF NOT EXISTS btree_gist;"
CREATE EXTENSION
```

Проверка: `select extname, extversion from pg_extension where extname='btree_gist'`
→ `btree_gist|1.7`.

### Проверка MinIO

В образе MinIO-сервера бинарника `mc` нет (собран из исходников, содержит только
`minio`), поэтому проверки выполнялись одноразовым контейнером из образа `lms-mc`
в сети Compose:

```
docker compose run --rm --no-deps \
  -e MC_HOST_local=http://lmsadmin:lms_dev_password@minio:9000 \
  --entrypoint /usr/bin/mc minio-init ready local
```

Приватность подтверждена двумя независимыми способами: политика anonymous-access
в самом MinIO (`private`) и фактические HTTP-ответы **403** на неавторизованные
запросы чтения и листинга. Эндпоинт `/minio/health/live` отвечает **200** без
авторизации — это штатное поведение healthcheck, утечки данных он не даёт.

## 4. Сетевая изоляция

Порты публикуются только на loopback и с внешнего интерфейса недоступны.
Проверено сканированием с LAN-адреса машины: порты `5432`, `6379`, `9000`, `8000`
недоступны.

```
docker compose port postgres 5432  → 127.0.0.1:5432
docker compose port redis 6379     → 127.0.0.1:6379
```

## 5. Особенности сборки образов

Официальные community-образы `minio/minio` и `minio/mc` больше не публикуются
в реестрах (`pull access denied` / `404`). Поэтому оба образа собираются локально
из официальных исходников по строгим тегам:

| Образ | Контекст сборки | Тег | Dockerfile |
|---|---|---|---|
| MinIO server | `./minio` | `RELEASE.2025-10-15T17-29-55Z` | `minio/Dockerfile` |
| MinIO client | `./minio/mc` | `RELEASE.2025-08-13T08-35-41Z` | `minio/mc/Dockerfile` |

Первая сборка занимает около двух минут (Go toolchain, клонирование репозитория,
`apt-get`). Последующие сборки кэшируются слоями.

## 6. Что не проверялось

| Область | Причина |
|---|---|
| Миграции `alembic upgrade head` | Запускаются вручную, в T0.08 не выполнялись |
| Продакшен-окружение | `docker-compose.prod.yml` и nginx появятся на более поздних этапах |
| Worker и scheduler | Ещё не добавлены в Compose |
| Интеграционные тесты с реальными S3-операциями | Требуют следующих задач по функциональности |