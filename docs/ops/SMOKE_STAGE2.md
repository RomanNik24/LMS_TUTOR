# Smoke этапа 2 (T2.09): роли, приватность цены, архив ученика

Прогон на ПК разработчика, стек `full` (postgres, redis, minio, app, nginx), запросы через Nginx `http://127.0.0.1:8080`.
В документе нет секретов, значений cookie и токенов приглашений.

- Коммит: `74166c4 test: ignore .env.local in backend tests (#33)` (main).
- Все POST/PATCH/DELETE шли с заголовками `Origin: <PUBLIC_BASE_URL>` и `X-Requested-With: XMLHttpRequest`.

## Как получены сессии

Telegram-клиента в прогоне нет, поэтому `initData` подписывается внутри контейнера `app` токеном бота из настроек (токен не выводится).
Вспомогательный скрипт запускается так: `docker compose --env-file .env.local --profile full exec -T app python - <команда> < helper.py`.
Команды: `owner_init` (подписанный `initData` владельца), `init <telegram_id>` (то же для тестового пользователя), `accept <токен> <telegram_id>`
(вызывает `AuthService.accept_invite`, как бот при `/start inv_<токен>`). Сессия берётся из cookie ответа `POST /api/v1/auth/telegram`.
Тестовые данные: менеджер `SMOKE-T209 manager` (user_id 5, telegram_id 910000001), ученик `SMOKE-T209 student` (user_id 6, telegram_id 910000002, lesson_price=2500).

## Результаты

| № | Проверка | Команда / запрос | Статус ответа | Результат |
|---|---|---|---|---|
| 1a | `scripts/check.py` на ветке `claude/epic-lovelace-oommx3` (содержит исправление #33) | `uv run python scripts/check.py` | 8 из 8 | PASS |
| 1b | `scripts/check.py` на main до `pnpm install` и до #33 | то же | 3 из 8 | FAIL (в `frontend/node_modules` не было новых пакетов; 5 backend-тестов брали настоящий Postgres с `.env.local`, исправлено в #33) |
| 2 | `pnpm gen:api`, затем `git status` | `cd frontend && pnpm gen:api` | — | PASS, `schema.d.ts` не изменился, дерево чистое |
| 3 | Сборка и запуск, миграции | `docker compose --env-file .env.local --profile full up -d --build`; `exec app alembic upgrade head` | — | PASS, все сервисы healthy, ревизия `fddb2f6cef06 (head)` |
| 4a | Владелец (bootstrap) | `exec app python scripts/create_owner.py` | — | PASS (владелец уже существовал) |
| 4b | Вход владельца | `POST /api/v1/auth/telegram` | 200 | PASS |
| 4c | Создание менеджера | `POST /api/v1/admin/staff` | 201 | PASS |
| 4d | Создание ученика, `lesson_price=2500` | `POST /api/v1/admin/students` | 201 | PASS |
| 4e | Приглашение менеджеру, принятие, вход | `POST /api/v1/admin/staff/{id}/invitations`; `accept_invite`; `POST /api/v1/auth/telegram` | 201; `linked manager`; 200 | PASS |
| 4f | Приглашение ученику, принятие, вход | `POST /api/v1/admin/students/{id}/invitations`; `accept_invite`; `POST /api/v1/auth/telegram` | 201; `linked student`; 200 | PASS |
| 5a | Менеджер: список учеников | `GET /api/v1/admin/students` | 200 | PASS, нет `lesson_price`, `price_snapshot`, `2500`; ученик в списке есть |
| 5b | Менеджер: карточка ученика | `GET /api/v1/admin/students/6` | 200 | PASS, нет `lesson_price`, `price_snapshot`, `2500` |
| 5c | Менеджер: свой профиль | `GET /api/v1/me` | 200 | PASS, нет `lesson_price`, `price_snapshot`, `2500` |
| 5d | Владелец: карточка ученика | `GET /api/v1/admin/students/6` | 200 | PASS, `"lesson_price":2500` присутствует |
| 5e | Менеджер на `/admin/staff` | `GET /api/v1/admin/staff` | 403 | PASS |
| 5f | Ученик на `/admin/students` | `GET /api/v1/admin/students` | 403 | PASS |
| 5g | Без cookie | `GET /api/v1/admin/students`, `GET /api/v1/me` | 401, 401 | PASS |
| 6a | Сессия ученика до архива | `GET /api/v1/me` | 200 | PASS |
| 6b | Архив ученика владельцем | `POST /api/v1/admin/students/6/archive` | 200 | PASS |
| 6c | Сессия архивного ученика | `GET /api/v1/me` | 401 | PASS |
| 6d | Повторный вход архивного ученика | `POST /api/v1/auth/telegram` | 401 | PASS |
| 6e | Восстановление ученика | `POST /api/v1/admin/students/6/restore` | 200 | PASS |
| 6f | Старая сессия после восстановления | `GET /api/v1/me` | 401 | PASS (сессии удалены при архиве) |
| 6g | Новое приглашение, принятие, вход | `POST /api/v1/admin/students/6/invitations`; `accept_invite`; `POST /api/v1/auth/telegram` | 201; `linked student`; 200 | PASS |
| 6h | Новая сессия работает, старая нет | `GET /api/v1/me` | 200 (новая), 401 (старая) | PASS |

## Замечания

- Тестовые менеджер (user_id 5) и ученик (user_id 6) оставлены в базе, имена начинаются с `SMOKE-T209`. Их можно архивировать через API владельца.
- Проверка «в ответах нет 2500» делалась поиском подстроки по телу ответа менеджера, поэтому сама по себе не отличает значение цены от случайного совпадения чисел. Совпадений не найдено.
- Для входа без Telegram используется подписанный `initData`; вход по ссылке `/web` в этом прогоне не проверялся.
