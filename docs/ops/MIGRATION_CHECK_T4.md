# Проверка схемы ДЗ на реальной БД (T4.02)

Дата: 2026-10-08. PostgreSQL 16, отдельная пустая база `lms_audit_mig` (после проверки удалена). Секретов в документе нет.

| № | Проверка | Результат |
|---|---|---|
| 1 | `alembic upgrade head` → `downgrade -1` → `upgrade head` → `alembic check` | без ошибок, дрейфа нет (`No new upgrade operations detected.`); ревизия `e6f7a8b9c0d1` (индексы по FK) откатывается и применяется |
| 2 | Выдача с `extensions_count = 3` | `check constraint "ck_homework_assignments_extensions_count_range"` |
| 3 | Дубль `(homework_id, student_id)` | `unique constraint "uq_homework_assignments_homework_id_student_id"` |

Два нарушения — две ошибки ограничений.
