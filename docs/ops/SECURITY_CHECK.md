# Проверки безопасности окружения (T8.10)

Прогон на ПК разработчика по состоянию main после PR #98 (`7632e69`) плюс правка `frontend/Dockerfile` из этого PR. В отчёте нет секретов, токенов и cookie; значения в находках — только идентификаторы уязвимостей и версии пакетов.

## Итог

| Проверка | Результат |
|---|---|
| gitleaks по всей истории | **PASS**: 179 коммитов (все ветки), утечек нет |
| Зависимости Python (`uv audit`) | **PASS**: 135 пакетов, уязвимостей нет |
| Зависимости фронтенда (`pnpm audit`) | **PASS**: уязвимостей нет (в том числе `@sentry/react`, `@playwright/test`) |
| Образы (Trivy 0.57.1, HIGH и CRITICAL) | **Замечания**: образ `app` — ОС без исправлений; образ `nginx` — 61 → 5 после `apk upgrade`; пакеты Python/Node — 0. Оформлены issues [#99](https://github.com/RomanNik24/LMS_TUTOR/issues/99) и [#100](https://github.com/RomanNik24/LMS_TUTOR/issues/100) |
| Порты postgres, redis, minio, app, nginx | **PASS**: опубликованы только на `127.0.0.1`; с адреса в локальной сети порты 5432, 6379, 9000, 9001, 8000, 8080 закрыты |
| Заголовки ответов | **PASS** (подробности ниже) |
| `/openapi.json`, `/docs`, `/redoc` в `APP_ENV=prod` | **PASS**: 404; в `local` и `staging` открыты (так задано в `docs/08` §7) |

Критических находок, которые нужно закрывать прямо сейчас, нет. Две находки по образам блокируют боевой запуск (этап 9, T9.02) и заведены как issues.

## gitleaks

`gitleaks 8.30.1 detect --redact` по всем 179 коммитам (6,1 МБ): `no leaks found`.

## Зависимости

- Python: `uv audit` — «Found no known vulnerabilities and no adverse project statuses in 135 packages».
- Фронтенд: `pnpm audit` — «No known vulnerabilities found». Версия `@sentry/react` 10.75.3 выбрана старше двух недель.

## Образы (Trivy)

Сканирование `HIGH` и `CRITICAL`, образы собраны из текущего main.

| Образ | ОС | HIGH | CRITICAL | С исправлением | Пакеты Python/Node |
|---|---|---|---|---|---|
| `app` | Debian 12.15 (`python:3.12-slim`) | 53 | 2 | 0 | 0 уязвимостей |
| `nginx` до правки | Alpine 3.23.3 (`nginx:1.28-alpine`) | 59 | 2 | 61 | не применимо |
| `nginx` после `apk upgrade` | Alpine 3.23.3 | 5 | 0 | 5 | не применимо |

- **`app`:** критические — `CVE-2025-7458` (`libsqlite3-0`, исправления нет) и `CVE-2023-45853` (`zlib1g`, `will_not_fix`: уязвимость только в minizip). Приложение не использует ни sqlite, ни minizip, пакеты Python чистые. Остальные 53 HIGH пока без исправлений в Debian. Issue [#100](https://github.com/RomanNik24/LMS_TUTOR/issues/100).
- **`nginx`:** в образ добавлен `RUN apk upgrade --no-cache` (`frontend/Dockerfile`): закрыто 56 находок (openssl, curl, pcre2, zlib, libxml2 и др.), критических не осталось. Осталось 5 HIGH в самом nginx 1.28.3-r1 (`CVE-2026-42055`, `-42533`, `-49975`, `-60005`, `-9256`; исправлены в r2…r6): пакет закреплён сборкой образа, `apk upgrade nginx` его не обновляет. Issue [#99](https://github.com/RomanNik24/LMS_TUTOR/issues/99).

## Порты

Опубликованные порты рабочего стека: `127.0.0.1:5432` (postgres), `127.0.0.1:6379` (redis), `127.0.0.1:9000-9001` (minio), `127.0.0.1:8000` (app), `127.0.0.1:8080` (nginx). У изолированного стека E2E postgres и redis наружу не публикуются, nginx — `127.0.0.1:18080`, minio — `127.0.0.1:19000`. Проверка через адрес компьютера в локальной сети: все шесть портов закрыты.

## Заголовки

Запросы `curl -I` к nginx (главная, статика с хэшем, `/api/v1/me`, `/health`, маршрут SPA): везде по одному разу `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `Content-Security-Policy` (`default-src 'self'`, `script-src 'self'`, `style-src 'self'`, `font-src 'self'`, `object-src 'none'`, `frame-ancestors` — Telegram), `Server: nginx` без версии. Для `/api/*` добавлен `Cache-Control: no-store`; статика с хэшем — `immutable`, `index.html` — `no-cache`. Дублей заголовков нет (backend и nginx ставят одинаковый набор, одноимённые заголовки backend nginx скрывает).

Не включено намеренно: `Strict-Transport-Security` — TLS локально завершает туннель; HSTS и TLS-блок добавляются в T9.02.

## Что осталось

- До T9.02: issues [#99](https://github.com/RomanNik24/LMS_TUTOR/issues/99) и [#100](https://github.com/RomanNik24/LMS_TUTOR/issues/100) (обновить базовые образы, повторить Trivy).
- HSTS и проверка заголовков на боевом домене — T9.02.
