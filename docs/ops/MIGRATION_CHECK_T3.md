# Проверка схемы расписания на реальной БД (T3.02)

Дата: 2026-10-08. PostgreSQL 16 из `docker-compose.yml`, отдельная пустая база `lms_audit_mig` (рабочая база не затрагивалась, после проверки база удалена). Секретов в документе нет.

| № | Проверка | Результат |
|---|---|---|
| 1 | `alembic upgrade head` на пустой базе | пять ревизий применены, голова `e6f7a8b9c0d1` |
| 2 | `alembic downgrade a3b1c0d4e5f6` → `upgrade head` | откат трёх ревизий и повторное применение без ошибок |
| 3 | `alembic check` | `No new upgrade operations detected.` |
| 4 | Два урока одного преподавателя с пересекающимся временем (10:00–11:00 и 10:30–11:30) | второй отклонён: `exclusion constraint "ex_lessons_teacher_no_overlap"` |
| 5 | Урок с `end_at = start_at` | `check constraint "ck_lessons_end_after_start"` |
| 6 | Дубль `(template_id, start_at)` (второй урок у другого преподавателя, чтобы не сработал `EXCLUDE`) | `unique constraint "uq_lessons_template_id_start_at"` |

Три нарушения — три ошибки ограничений. Замечание: дубль шаблона у того же преподавателя ловит раньше `EXCLUDE` (то же время), поэтому для проверки `UNIQUE` использован второй преподаватель.
