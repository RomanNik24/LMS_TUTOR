# Smoke этапа 3: расписание, шаблоны, уроки, права (T3.xx)

Прогон на ПК разработчика, стек `full`, запросы через Nginx `http://127.0.0.1:8080`.
Версия main: `0b0a75c` (feat(frontend): add student schedule screens (#43)).
В документе нет секретов, значений cookie и токенов приглашений.

## Как получены сессии

Telegram-клиента для тестовых учётных записей нет, поэтому `initData` подписывается внутри контейнера `app` токеном бота из настроек (токен не выводится),
приглашения принимаются через `AuthService.accept_invite`. Все POST/PATCH/DELETE шли с `Origin: <PUBLIC_BASE_URL>` и `X-Requested-With: XMLHttpRequest`.
Тестовые данные: менеджер `SMOKE-T304 manager` (user_id 12), ученики «Аня SMOKE» (user_id 15, цена 1500 → позже 3000) и «Борис SMOKE» (user_id 16, цена 2000).

## Результаты

| № | Проверка | Запрос / команда | Результат | PASS/FAIL |
|---|---|---|---|---|
| 1.1 | Подготовка: `git pull --ff-only`, `pnpm install --frozen-lockfile` | — | main = `0b0a75c` | PASS |
| 1.2 | `uv run python scripts/check.py` | — | 8 из 8 | PASS |
| 1.3 | `pnpm gen:api`, `git status` | — | `schema.d.ts` не изменился | PASS |
| 1.4 | `up -d --build`, healthy, `alembic current`, `alembic check` | — | 5 сервисов healthy; единственная голова `a3b1c0d4e5f6`; `No new upgrade operations detected` | PASS |
| 1.5 | Бот в режиме polling, один процесс | `BOT_MODE=polling` | В логе `Run polling for bot @romchik_infomat_bot`, процесс только в контейнере `app`, на хосте процессов бота нет | PASS |
| 1.6 | Бот отвечает на `/start` | — | требуется живой Telegram-аккаунт | не проверено |
| 2 | Менеджер, Аня (1500, `video_url`, `board_url`), Борис (2000), приглашения, вход | `POST /admin/staff`, `POST /admin/students`, `…/invitations` | 201, 201, 201; вход 200 | PASS |
| 3.1 | Два шаблона: вторник 17:00 и пятница 17:00, Europe/Moscow, 12.10–08.11, участник Аня | `POST /admin/schedule-templates` | 201, 201; `SELECT count(*) FROM lessons WHERE template_id IS NOT NULL` = 3 (создание заполняет ближайшие 2 недели) | PASS |
| 3.2 | `generate?horizon_weeks=4` первый раз | `POST /admin/schedule-templates/generate` | 200 `{"templates":2,"created":4,"skipped":0}`, count = 7 | PASS |
| 3.3 | `generate?horizon_weeks=4` второй раз | то же | 200 `created=0`, count = 7 (не изменился) | PASS |
| 3.4 | Все начала в 17:00 по Москве | `SELECT start_at AT TIME ZONE 'Europe/Moscow' FROM lessons` | 13.10 Tue, 16.10 Fri, 20.10 Tue, 23.10 Fri, 27.10 Tue, 30.10 Fri, 03.11 Tue — все 17:00; не-17:00: 0 | PASS |
| 3.5 | `PATCH` шаблона `duration_minutes=90` | `PATCH /admin/schedule-templates/1` | 200; будущие уроки шаблона пересозданы (id 1,2,4,5 → 8,9), длительность 90; шаблон 2 остался 60 | PASS |
| 3.6 | `deactivate` шаблона, затем `generate` | `POST /admin/schedule-templates/1/deactivate` | 200; будущих уроков шаблона 1: 0; после `generate` 200 `created=0`, уроков шаблона 1 по-прежнему 0, у шаблона 2 осталось 3 | PASS |
| 4.1 | Разовый урок в будущем | `POST /admin/lessons` | 201 | PASS |
| 4.2 | Пересекающийся урок того же преподавателя | `POST /admin/lessons` | 409 `lesson_overlap` | PASS |
| 4.3 | Урок встык | `POST /admin/lessons` | 201 | PASS |
| 4.4 | Групповой урок (Аня и Борис) | `POST /admin/lessons` | 201 | PASS |
| 4.5 | `reschedule` на новое время | `POST /admin/lessons/{id}/reschedule` | 200, `is_detached=true` | PASS |
| 4.6 | `reschedule` в занятое время | то же | 409 `lesson_overlap` | PASS |
| 4.7 | `cancel`, `billable_student_ids=[Борис]` | `POST /admin/lessons/{id}/cancel` | 200, `status=cancelled`; SQL: Борис `cancelled billable=true price_snapshot=2000` | PASS |
| 4.8 | `complete` группового урока: Аня attended, Борис no_show | `POST /admin/lessons/{id}/complete` | 200, `status=completed`; SQL: Аня `attended billable=true price_snapshot=1500`; Борис `no_show billable=false price_snapshot=NULL` | PASS |
| 4.9 | Смена цены Ани после отметки | `PATCH /admin/students/15` `lesson_price=3000` | 200; SQL: `price_snapshot` Ани остался 1500 | PASS |
| 4.10 | Повторный `complete` | `POST /admin/lessons/{id}/complete` | 400 `lesson_already_completed` | PASS |
| 5.1 | Сессия Ани: свои уроки | `GET /student/lessons?from=..&to=..` | 200, возвращены только уроки Ани (id 3, 6, 7, 10, 13), урока Бориса нет | PASS |
| 5.2 | Чужой урок | `GET /student/lessons/{id чужого}` | 404 `lesson_not_found` | PASS |
| 5.3 | В ответах ученика нет `price`, `teacher_note`, `billable`, имени Бориса, чисел 1500/2000/3000, посещаемости | поиск подстрок по телу | совпадений нет (в карточке группового урока только `participants_count=2`) | PASS |
| 5.4 | Ссылки: урок → профиль | список и карточка урока | `video_url` и `board_url` совпадают со ссылками профиля Ани | PASS |
| 5.5 | Менеджер: список и карточка урока без `price_snapshot` и `is_billable`; карточка ученика без `lesson_price` | `GET /admin/lessons`, `/admin/lessons/{id}`, `/admin/students/15` | 200, запрещённых полей и значений цены нет | PASS |
| 5.6 | Менеджер на `/admin/staff` | `GET /admin/staff` | 403 `permission_denied` | PASS |
| 5.7 | Владелец: `lesson_price` на карточке ученика | `GET /admin/students/15` | 200, `"lesson_price":3000` | PASS |
| 5.8 | Период больше года | `GET /admin/lessons?from=2026-01-01&to=2028-01-01`, то же для `/student/lessons` | 422 `invalid_period` (оба) | PASS |
| 6.1 | `/today` у ученика: уроки на 24 часа, кнопки «Телемост» и «Доска» | — | нужен живой аккаунт ученика | не проверено |
| 6.2 | `/today` у персонала: сводка дня | — | нужен живой аккаунт персонала (владелец) | не проверено |

Итого: PASS 30 из 30 проверенных, 3 пункта не проверены (1.6, 6.1, 6.2).

## Замечания

- Данные не удалялись. Два лишних тестовых ученика («Anya SMOKE», «Anya») появились из-за ошибки кодировки в запросе, архивированы (user_id 13 и 14). Остальные тестовые записи (`SMOKE-T209`, `SMOKE-T303`, `SMOKE-T304`, «Аня SMOKE», «Борис SMOKE») оставлены.
- После `docker compose up -d --build` Nginx отдаёт 502, пока не перезапущен: он хранит старый IP контейнера `app` (`proxy_pass http://app:8000` без `resolver`). Обход: `docker compose --env-file .env.local --profile full restart nginx`. Конфиг не менялся.
- Запрос создания шаблона заполняет только ближайшие 2 недели; полный период (4 недели) появляется после `generate?horizon_weeks=4`. После `PATCH` шаблона пересоздаются только уроки в этом ближайшем горизонте (2 из 4).
- В `docs/08_api_spec.md` код `lesson_overlap` указан и в строке для 400, и в строке для 409; фактически API отдаёт 409.
- Кириллица в теле запроса `curl` из Git Bash на Windows портится (ответ 400 `bad_request`); тела с кириллицей отправлялись из файла (`-d @file`).
- Constraint-проверки БД (EXCLUDE на пересечение, CHECK `end_at > start_at`, UNIQUE `(template_id, start_at)`) и `alembic downgrade -1` / `upgrade head` проверены раньше в этом же цикле (T3.02): каждое нарушение падает, миграции проходят. После `downgrade` таблицы расписания пересоздавались заново.
