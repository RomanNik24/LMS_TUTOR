# Проверка применения миграции T1.04 (локальная PostgreSQL)

Отчёт о фактической проверке миграции и сидов T1.03 на локальной Docker PostgreSQL.
Задача: T1.04 (docs/11 roadmap). Секреты и содержимое `.env.local` в файл не попадают.

## Environment

- Локальная Docker PostgreSQL: контейнер `my-lms-postgres` (образ `postgres:16`, сервис `postgres` из `docker-compose.yml`), БД `lms`.
- Дата проверки: 2026-10-06.
- Alembic head: `fddb2f6cef06` (initial schema t1 02 core tables).
- Команды миграций выполнялись через `uv run alembic ...` (env.py читает `DATABASE_URL` из `Settings`).

## Migration cycle

| Шаг | Результат |
|---|---|
| `alembic upgrade head` (первичный) | PASS |
| `alembic downgrade base` | PASS |
| `alembic upgrade head` (повторный) | PASS |

Цикл выполнен полностью: сброс схемы до `<base>` и повторный подъём до head без ошибок.
`downgrade base` дополнительно удалил расширение `btree_gist` (создаётся заново при upgrade).

## Drift

- `alembic check` → `No new upgrade operations detected` — PASS.
- `alembic heads` → единственный head `fddb2f6cef06`.
- `alembic current` → база находится на head `fddb2f6cef06`.

## Seeds

Сиды: `uv run python scripts/seed_reference.py` (скрипт из T1.03, данные — `docs/04` §9–§10).

| Запуск | Вставлено (subjects / exam_types / grade_scales) | Итоговые количества строк |
|---|---|---|
| До сида | — | 0 / 0 / 0 (схема после re-upgrade) |
| 1-й запуск | 2 / 4 / 117 | 2 / 4 / 117 |
| 2-й запуск | 0 / 0 / 0 | 2 / 4 / 117 |

**Идемпотентность подтверждена**: второй запуск не изменил количество строк (проверено SQL-запросом, не только логом скрипта).

Количество `grade_scales` по типам экзаменов (SQL):

| code | max_primary | шкал |
|---|---|---|
| ege_informatics | 29 | 30 |
| ege_math_profile | 32 | 33 |
| oge_informatics | 21 | 22 |
| oge_math | 31 | 32 |

Итог: 30 / 33 / 22 / 32 — соответствует ожиданиям T1.03.

## Schema

В `public` присутствуют 10 таблиц: 9 сущностей T1.02 (`subjects`, `users`, `exam_types`,
`student_profiles`, `guardians`, `student_subjects`, `auth_tokens`, `audit_log`,
`grade_scales`) + служебная `alembic_version`. Таблиц будущих этапов нет.

`users` (\d users):

- PK `pk_users` (bigint identity always, `id`);
- UNIQUE `uq_users_telegram_id` (telegram_id);
- CHECK `ck_users_role` (`role IN ('owner','manager','student')`);
- временные колонки — `timestamp with time zone` (TIMESTAMPTZ), `created_at`/`updated_at` default `now()`;
- `timezone` default `'Europe/Moscow'`, `is_active` default `true`, `bot_blocked` default `false`;
- FK: `audit_log.actor_user_id` (SET NULL), `auth_tokens.user_id` (CASCADE), `auth_tokens.created_by` (SET NULL), `guardians.student_id` (CASCADE), `guardians.user_id` (SET NULL), `student_profiles.user_id` (CASCADE), `student_profiles.teacher_id` (RESTRICT), `student_subjects.student_id` (CASCADE).

`student_profiles` (\d student_profiles):

- PK `pk_student_profiles` (`user_id`, PK и FK → users ON DELETE CASCADE);
- FK `fk_student_profiles_teacher_id` → users ON DELETE RESTRICT;
- CHECK `ck_student_profiles_lesson_price_nonneg` (`lesson_price >= 0`);
- `created_at`/`updated_at` TIMESTAMPTZ default `now()`.

Контроль constraints и индексов (pg_constraint / pg_indexes):

- PK: 9 по таблицам T1.02; UNIQUE: `uq_subjects_code`, `uq_users_telegram_id`, `uq_exam_types_code`, `uq_auth_tokens_token_hash`, `uq_grade_scales_exam_type_id_valid_year_primary_score`;
- CHECK: 6 (см. список выше);
- FK: 13 (SET NULL / CASCADE / RESTRICT по docs/04);
- индекс `ix_auth_tokens_user_id_purpose` (user_id, purpose) присутствует;
- расширения: `btree_gist` (требование docs/04 §0) и штатный `plpgsql`.

## Unique constraint

Проверка UNIQUE на `users.telegram_id` (тестовые значения, не production):

1. Вставка пользователя `role=student`, `telegram_id=900000000001` → `INSERT 0 1`.
2. Вторая вставка с тем же `telegram_id` → `ERROR: duplicate key value violates unique constraint "uq_users_telegram_id"` — PASS.
3. Тестовые записи удалены (`DELETE 1`, остаточных строк 0).

## Result

**T1.04 PASS**
