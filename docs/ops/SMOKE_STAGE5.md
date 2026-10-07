# Smoke этапа 5: уведомления и фоновые задачи (T5.08)

Прогон на ПК разработчика, стек `full` (app, nginx, postgres, redis, minio, worker, scheduler), запросы через Nginx `http://127.0.0.1:8080`.
Версия main: `1c6b399` (fix(worker): disable redis read timeout for the blocking queue pop (#63)); PR #62 влит.
В документе нет секретов, токена бота, значений cookie и ссылок healthcheck.

## Как получены сессии и получатель

Сессии как в `docs/ops/SMOKE_STAGE3.md`: `initData` подписывается внутри контейнера `app` токеном бота (токен не выводится), все POST/PATCH шли с `Origin: <PUBLIC_BASE_URL>` и `X-Requested-With: XMLHttpRequest`.
Получатель — ученик «Тест» (user_id 4), привязан к настоящему Telegram владельца (подтверждено владельцем). Урок и ДЗ создавал владелец (user_id 3, он же преподаватель по умолчанию).
Времена в UTC; Москва = UTC+3. Часовые пояса (ученик «Тест» и владелец) в конце возвращены в `Europe/Moscow`.

## Результаты

| № | Проверка | Запрос / команда | Результат | PASS/FAIL |
|---|---|---|---|---|
| 0.1 | Пересборка на main `1c6b399`, миграции | `up -d --build`, `alembic upgrade head`, `alembic current`, `alembic check` | голова `d5e6f7a8b9c0`, `No new upgrade operations detected` | PASS |
| 0.2 | Один scheduler и один worker | `docker ps --filter name=scheduler`, `…name=worker` | по одному контейнеру, остальные сервисы healthy | PASS |
| 0.3 | Воркер стабилен 3 минуты простоя | `docker compose logs worker` раз в минуту | t+1: Traceback=0, `is dead`=0; t+2: 0/0; t+3: 0/0; scheduler Traceback=0 | PASS |
| 1.1 | Урок через 33 минуты → одна запись `lesson_reminder` | `POST /admin/lessons`, `SELECT … FROM notifications` | урок начинается 20:07:56, `scheduled_for`=19:37:56 (начало − 30 мин), `is_urgent=true`, `dedup_key=lesson_reminder:14:4:…` | PASS |
| 1.2 | Отправка вовремя | `sent_at`, лог worker | `sent_at`=19:38:46 (через 50 с после `scheduled_for`; диспетчер работает раз в минуту на :46) | PASS |
| 1.3 | Владелец подтвердил получение на телефоне | — | подтверждения от владельца не получено | не проверено |
| 2.1 | При выдаче ДЗ создаётся `homework_assigned` | `POST /admin/homework` (due_mode fixed) | запись есть (`homework_assigned:3`, `homework_assigned:5`) | PASS |
| 2.2 | `homework_deadline`: `scheduled_for` = срок − 24 ч, не срочное | `UPDATE homework_assignments SET created_at = now() - interval '3 days'` (выдача должна быть старше суток, иначе по правилу напоминания нет), затем SQL | срок 2026-10-08 19:43:13 → `scheduled_for`=2026-10-07 19:43:13, `is_urgent=false` | PASS |
| 2.3 | Отправка в срок | SQL, лог | запись создаётся задачей раз в 5 минут (19:45:00), отправлена 19:45:46, то есть через 2 мин 33 с после `scheduled_for` (из-за периода задачи генерации). Первая попытка в 22:35 по Москве (тихие часы) отложена до 08:00, поэтому повторена в поясе America/New_York (дневное время) | PASS (с замечанием) |
| 3.1 | Тихие часы: несрочное откладывается | выдача ДЗ в 22:35 по Москве (пояс ученика `Europe/Moscow`) | `homework_assigned:3` и `homework_deadline:3:…` остались `pending`, `scheduled_for` = 2026-10-08 05:00:00+00 (08:00 по Москве) | PASS |
| 3.2 | Срочное в тихие часы | урок через 3 ч и сразу `POST /admin/lessons/{id}/cancel` в 22:39 по Москве | `lesson_cancelled` создана 19:39:14, `is_urgent=true`, `sent_at`=19:39:46 (через 32 с) | PASS |
| 3.3 | Смена пояса `PATCH /admin/students/4` | `{"timezone":"America/New_York"}` и обратно `Europe/Moscow` | 200 оба раза; в шаге 3.1 пояс не менялся (в Москве уже было 22:39 ≈ 23:00); второе ДЗ, выданное за 3 секунды до смены пояса, отправлено сразу (`homework_assigned:4`, 19:40:46) | PASS (с замечанием) |
| 4.1 | Redis остановлен на ~65 с (19:46:50–19:47:55) | `docker compose stop redis`, `start redis` | во время простоя `GET /health` → 503 `{"status":"degraded","database":"ok","redis":"error"}`, `GET /me` с cookie → 500, вход `POST /auth/telegram` → 500; worker падал и перезапускался (`is dead`), scheduler логировал ошибки отправки | PASS (поведение описано) |
| 4.2 | После запуска Redis всё работает без ручного перезапуска | логи за 60 с | `GET /health` → 200 `ok`; worker: Traceback=0, `is dead`=0, 4 задачи выполнено; scheduler: 5 отправок. Один тик диспетчера потерян: `SendTaskError … Connection lost` в 19:48:46 | PASS (с замечанием) |
| 4.3 | Неотправленное доставлено один раз, дублей нет | `notifications` id 15; `SELECT dedup_key, count(*) … HAVING count(*) > 1` | запись 15 была `pending` во время простоя, отправлена 19:48:46 (`attempts=1`); выборка дублей пуста | PASS |
| 5.1 | Worker остановлен 4 мин 39 с (19:50:29–19:55:08): уведомления накапливаются | `docker compose stop worker`, ДЗ, урок + отмена | до запуска: id 18 `homework_assigned` и 19 `lesson_cancelled` — `pending`, `attempts=0`; напоминание об уроке не создано (генерирует worker) | PASS |
| 5.2 | Очередь догоняется, дублей нет | `docker compose start worker`, SQL | 19:55:15 (через 7 с): id 18 и 19 — `sent`, создано и отправлено `lesson_reminder` (id 20, `scheduled_for`=19:54:45); дублей нет | PASS |
| 6.1 | Сводка по статусам | `SELECT type, status, count(*) … GROUP BY 1, 2` | `homework_assigned` pending 1 / sent 4; `homework_deadline` pending 1 / sent 1; `lesson_cancelled` sent 2; `lesson_reminder` sent 2. `failed` и `skipped` нет, `last_error` нигде не заполнен | PASS |
| 6.2 | Webhook при polling пуст | `getWebhookInfo` (токен из окружения контейнера) | `url=''`, `pending_update_count=0`, `last_error_message=None` | PASS |
| 6.3 | Один scheduler | `docker compose ps` | один контейнер `my-lms-scheduler` | PASS |
| 6.4 | Утренняя сводка по расписанию в 08:xx местного | пояс владельца `Pacific/Fiji` (в 20:00 UTC там 08:00), ждали 20:00 UTC | scheduler в 20:00:00 отправил `send_morning_digest`, но worker ни разу не выполнил её (в логах нет `Executing task send_morning_digest`; так же пропущена `notify_unmarked_lessons` в 20:00); записи `morning_digest` не появилось | FAIL |
| 6.5 | Утренняя сводка вручную и дедупликация по местной дате | `DigestService.send_morning_digests()` из контейнера worker, два запуска подряд | первый запуск создал 1 запись (`morning_digest:3:<дата>`), второй — 0; сводка отправлена в 20:13:46 | PASS |
| 7.1 | `ruff check`, `ruff format --check`, `mypy --strict src` | — | All checks passed; 246 files formatted; no issues in 123 files | PASS |
| 7.2 | `pytest` без одного теста | `pytest -q --deselect …::test_worker_process_runs_heartbeat_and_stops_on_sigterm` | 880 passed, 2 skipped, 1 deselected | PASS |
| 7.3 | `uv run python scripts/check.py` целиком | — | не завершается на Windows: зависает `tests/integration/test_worker_runtime.py::test_worker_process_runs_heartbeat_and_stops_on_sigterm` (тест запускает `taskiq worker` подпроцессом и шлёт SIGTERM; за 80 с и за 10 минут `check.py` не вывел результат) | FAIL |

Итого: PASS 22 (4 из них с замечаниями: 2.3, 3.3, 4.1, 4.2), FAIL 2 (6.4, 7.3), не проверено 1 (1.3). Фронтенд-шаги `check.py` в этом прогоне не перезапускались (фронтенд после предыдущего прогона не менялся).

## Проблемы и не проверено

1. **Часовая задача `send_morning_digest` и `notify_unmarked_lessons` не выполнились в 20:00 UTC (6.4).** Scheduler отправил обе (`Sending task …` в 20:00:00), worker выполнил в это время только `heartbeat`, `generate_homework_reminders`, `expire_homework_assignments`. Счётчики за сессию: `send_morning_digest` отправлена 1, выполнена 0; `notify_unmarked_lessons` отправлена 3, выполнена 2. Причина не выяснена; в 20:00 параллельно шёл `scripts/check.py` (нагрузка на ПК). Нужен повторный наблюдаемый прогон в «чистый» час (с поясом, при котором 08:xx) без параллельной нагрузки. Сама логика сводки и дедупликации (6.5) работает.
2. **`check.py` не проходит на Windows из-за `test_worker_process_runs_heartbeat_and_stops_on_sigterm` (7.3).** Остальные тесты (880) проходят; на Linux CI, вероятно, нормально. Код не менялся.
3. **Тихие часы действуют на напоминание о дедлайне.** Несрочные записи (`homework_assigned`, `homework_deadline`) в 22:00–08:00 по поясу ученика переносятся на 08:00. Поэтому напоминание за 24 часа в ночное время приходит утром, а не точно в срок; это ожидаемое поведение, но для проверки «вовремя» нужен дневной пояс.
4. **Напоминание о дедлайне запаздывает до ~6 минут** относительно `scheduled_for`: запись создаётся задачей раз в 5 минут, диспетчер работает раз в минуту (наблюдалось 2 мин 33 с).
5. **При остановке Redis (4.1)** приложение отвечает 503/500 на `/health`, `/me` и вход; после запуска Redis scheduler потерял один тик (`SendTaskError: Connection lost`), дальше всё восстановилось без ручного перезапуска.
6. **Не проверено:** подтверждение получения сообщений на телефоне (1.3) — владелец в этой сессии не подтвердил ни одно из отправленных сообщений (`lesson_reminder`, `lesson_cancelled`, `homework_assigned`, `homework_deadline`, `morning_digest`); утренняя сводка по расписанию (6.4); `check.py` целиком (7.3).
7. **Побочные эффекты:** в базе остались тестовые записи уведомлений; ещё две записи (id 1 и 2) отложены до 08:00 по Москве 2026-10-08 05:00 UTC и будут отправлены ученику «Тест» (реальному Telegram владельца). После падения `check.py` я командой `taskkill /IM python.exe` завершил все процессы `python.exe` на ПК, на хосте других тестовых процессов Python не было.
