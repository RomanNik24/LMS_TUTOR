# 04. Схема базы данных

PostgreSQL 16+, SQLAlchemy 2.0 async. Эта схема — источник истины по данным.

## 0. Общие правила
- Первичные ключи: `BIGINT GENERATED ALWAYS AS IDENTITY` (кроме составных). Идентификаторы для ссылок во внешний мир (токены) — отдельные поля.
- Время: `TIMESTAMPTZ` (UTC). Даты без времени — `DATE`. Локальное время шаблонов — `TIME` + IANA-часовой пояс.
- Во всех таблицах (кроме журналов и связующих) есть `created_at TIMESTAMPTZ NOT NULL DEFAULT now()` и `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()` (обновляется в приложении).
- Деньги: `INTEGER` в рублях (копейки не нужны).
- Enum: нативные PostgreSQL ENUM либо `VARCHAR` + `CHECK` (единый подход, выбрать при старте и держаться его).
- Удаление: «мягкое» через `is_active`/`archived_at` для пользователей; для остальных `ON DELETE` указан ниже.
- Telegram ID: `BIGINT` (значения превышают 2³¹).
- Расширения: `btree_gist`.

## 1. Справочники

### 1.1. `subjects`
| Поле | Тип | Описание |
|---|---|---|
| id | BIGINT PK | |
| code | VARCHAR(32) UNIQUE NOT NULL | `informatics`, `math` |
| name | VARCHAR(100) NOT NULL | «Информатика», «Математика» |
| is_active | BOOL NOT NULL DEFAULT true | |

### 1.2. `exam_types`
Типы экзаменов. На MVP ровно четыре записи.

| Поле | Тип | Описание |
|---|---|---|
| id | BIGINT PK | |
| code | VARCHAR(32) UNIQUE NOT NULL | `oge_informatics`, `oge_math`, `ege_informatics`, `ege_math_profile` |
| subject_id | FK → subjects | |
| kind | ENUM(`oge`,`ege`) NOT NULL | |
| result_kind | ENUM(`grade_2_5`,`test_100`) NOT NULL | ОГЭ → оценка 2–5, ЕГЭ → тестовый балл |
| max_primary | SMALLINT NOT NULL | Максимальный первичный балл (текущий год) |
| name | VARCHAR(100) NOT NULL | Отображаемое имя |
| config | JSONB NOT NULL DEFAULT '{}' | Особые правила (напр. `{"min_geometry": 2}` для ОГЭ математики) |
| is_active | BOOL NOT NULL DEFAULT true | |

### 1.3. `grade_scales`
Шкалы перевода по годам. Одна строка на каждый первичный балл.

| Поле | Тип | Описание |
|---|---|---|
| id | BIGINT PK | |
| exam_type_id | FK → exam_types ON DELETE CASCADE | |
| valid_year | SMALLINT NOT NULL | Год действия шкалы |
| primary_score | SMALLINT NOT NULL | Первичный балл |
| result_value | SMALLINT NOT NULL | Оценка 2–5 (ОГЭ) или тестовый балл 0–100 (ЕГЭ) |

Ограничения: `UNIQUE (exam_type_id, valid_year, primary_score)`; `CHECK primary_score >= 0`.
Используется шкала с максимальным `valid_year ≤ год даты экзамена`. Шкалы **не хардкодятся**, добавляются сидом/миграцией и обновляются ежегодно.

### 1.4. `catalog_items` (витрина для гостей)
| Поле | Тип | Описание |
|---|---|---|
| id | BIGINT PK | |
| title | VARCHAR(150) NOT NULL | |
| description | TEXT NOT NULL | |
| price_text | VARCHAR(100) NULL | Свободный текст («от 1500 ₽ за занятие») |
| sort_order | INT NOT NULL DEFAULT 0 | |
| is_published | BOOL NOT NULL DEFAULT false | |

## 2. Пользователи

### 2.1. `users`
| Поле | Тип | Описание |
|---|---|---|
| id | BIGINT PK | |
| role | ENUM(`owner`,`manager`,`student`) NOT NULL | |
| telegram_id | BIGINT NULL UNIQUE | Заполняется при принятии приглашения |
| telegram_username | VARCHAR(64) NULL | Для удобства, не для идентификации |
| display_name | VARCHAR(150) NOT NULL | Как обращаться к человеку |
| timezone | VARCHAR(64) NOT NULL DEFAULT 'Europe/Moscow' | IANA |
| is_active | BOOL NOT NULL DEFAULT true | `false` = архив |
| archived_at | TIMESTAMPTZ NULL | |
| bot_blocked | BOOL NOT NULL DEFAULT false | Пользователь заблокировал бота |
| last_seen_at | TIMESTAMPTZ NULL | |

Ограничения: `UNIQUE (telegram_id)` (NULL допускается многократно). Профиль без `telegram_id` — ожидает приглашения.

### 2.2. `student_profiles` (1:1 с users, role = student)
| Поле | Тип | Описание |
|---|---|---|
| user_id | BIGINT PK FK → users ON DELETE CASCADE | |
| teacher_id | BIGINT NOT NULL FK → users | Ведущий преподаватель (owner/manager) |
| school_class | SMALLINT NULL | Класс (9, 11, …) |
| lesson_price | INTEGER NOT NULL DEFAULT 0 CHECK (>= 0) | Текущая цена занятия, ₽ (видит только owner) |
| video_url | VARCHAR(500) NULL | Постоянная ссылка Яндекс Телемоста |
| board_url | VARCHAR(500) NULL | Постоянная ссылка на онлайн-доску |
| teacher_notes | TEXT NULL | Приватные заметки (ученик не видит) |

### 2.3. `student_subjects`
`student_id FK → users`, `subject_id FK → subjects`, PK `(student_id, subject_id)`.

### 2.4. `guardians` (задел под родителей; функционала в MVP нет)
| Поле | Тип | Описание |
|---|---|---|
| id | BIGINT PK | |
| student_id | FK → users ON DELETE CASCADE | |
| full_name | VARCHAR(150) NOT NULL | |
| relation | VARCHAR(50) NULL | мама, папа, … |
| phone | VARCHAR(32) NULL | |
| telegram_id | BIGINT NULL | |
| user_id | BIGINT NULL FK → users | Для будущей роли `parent` |

### 2.5. `auth_tokens`
Приглашения и одноразовые ссылки входа.

| Поле | Тип | Описание |
|---|---|---|
| id | BIGINT PK | |
| purpose | ENUM(`invite`,`web_login`) NOT NULL | |
| user_id | FK → users ON DELETE CASCADE | Для кого токен |
| token_hash | CHAR(64) UNIQUE NOT NULL | SHA-256 от токена; сам токен не хранится |
| created_by | BIGINT NULL FK → users | Кто создал (NULL для `web_login`) |
| expires_at | TIMESTAMPTZ NOT NULL | invite: +7 дней, web_login: +10 минут |
| used_at | TIMESTAMPTZ NULL | |
| revoked_at | TIMESTAMPTZ NULL | |

Индексы: `(user_id, purpose)`. Токен действителен, если `used_at IS NULL AND revoked_at IS NULL AND expires_at > now()`.

## 3. Расписание

### 3.1. `schedule_templates`
| Поле | Тип | Описание |
|---|---|---|
| id | BIGINT PK | |
| teacher_id | FK → users NOT NULL | |
| subject_id | FK → subjects NOT NULL | |
| weekday | SMALLINT NOT NULL CHECK (1..7) | ISO: 1 = понедельник |
| start_local_time | TIME NOT NULL | Локальное время начала |
| duration_minutes | SMALLINT NOT NULL CHECK (> 0) | По умолчанию 60 |
| timezone | VARCHAR(64) NOT NULL | Пояс, в котором задано `start_local_time` |
| starts_on | DATE NOT NULL | |
| ends_on | DATE NULL | |
| is_active | BOOL NOT NULL DEFAULT true | Пауза/отключение |
| generated_until | DATE NULL | До какой даты уже сгенерированы уроки |

### 3.2. `schedule_template_participants`
`template_id FK ON DELETE CASCADE`, `student_id FK → users`, PK `(template_id, student_id)`.

## 4. Уроки

### 4.1. `lessons`
| Поле | Тип | Описание |
|---|---|---|
| id | BIGINT PK | |
| teacher_id | FK → users NOT NULL | Кто проводит |
| subject_id | FK → subjects NOT NULL | |
| start_at | TIMESTAMPTZ NOT NULL | |
| end_at | TIMESTAMPTZ NOT NULL | |
| status | ENUM(`scheduled`,`completed`,`cancelled`) NOT NULL DEFAULT 'scheduled' | |
| template_id | FK → schedule_templates ON DELETE SET NULL NULL | Из какого шаблона создан |
| is_detached | BOOL NOT NULL DEFAULT false | `true` — изменён вручную, шаблон его не трогает |
| video_url_override | VARCHAR(500) NULL | Переопределяет ссылку из профиля |
| board_url_override | VARCHAR(500) NULL | |
| topic | VARCHAR(255) NULL | Тема занятия |
| teacher_note | TEXT NULL | Приватная заметка (ученик не видит) |
| completed_at | TIMESTAMPTZ NULL | |
| cancelled_at | TIMESTAMPTZ NULL | |
| cancelled_by | BIGINT NULL FK → users | |
| cancel_reason | VARCHAR(255) NULL | |

Ограничения:
- `CHECK (end_at > start_at)`.
- `UNIQUE (template_id, start_at)` — идемпотентность генерации.
- `EXCLUDE USING gist (teacher_id WITH =, tstzrange(start_at, end_at) WITH &&) WHERE (status <> 'cancelled')` — преподаватель не может вести два урока одновременно.

Индексы: `(start_at)`, `(teacher_id, start_at)`, `(status, start_at)`.

Перенос урока: меняются `start_at/end_at`, ставится `is_detached = true`, запись в `audit_log`, создаётся уведомление участникам.

### 4.2. `lesson_participants`
| Поле | Тип | Описание |
|---|---|---|
| lesson_id | FK → lessons ON DELETE CASCADE | |
| student_id | FK → users | |
| attendance | ENUM(`pending`,`attended`,`no_show`,`cancelled`) NOT NULL DEFAULT 'pending' | |
| is_billable | BOOL NOT NULL DEFAULT false | Засчитывается в заработок |
| price_snapshot | INTEGER NULL CHECK (>= 0) | Цена, зафиксированная при отметке |

PK `(lesson_id, student_id)`. Индекс `(student_id, lesson_id)`.

Правила цены:
- Пока урок `scheduled`, `price_snapshot IS NULL`; «ожидаемый» доход считается по текущему `student_profiles.lesson_price`.
- При отметке участника (`attended`, а также `no_show`/`cancelled` с галочкой «засчитать») в `price_snapshot` копируется текущая цена. Последующая смена цены **не влияет** на проведённые уроки.
- По умолчанию: `attended` → `is_billable = true`; `no_show` → `false` (преподаватель может включить); `cancelled` → `false` (может включить для поздней отмены).

## 5. Домашние задания

### 5.1. `homeworks` (само задание)
| Поле | Тип | Описание |
|---|---|---|
| id | BIGINT PK | |
| created_by | FK → users NOT NULL | |
| lesson_id | FK → lessons ON DELETE SET NULL NULL | Урок, к которому привязано (необязательно) |
| subject_id | FK → subjects NOT NULL | |
| kind | ENUM(`regular`,`mock_exam`) NOT NULL | |
| exam_type_id | FK → exam_types NULL | Обязательно для `mock_exam` |
| title | VARCHAR(200) NOT NULL | |
| description | TEXT NULL | Инструкции |
| max_score | SMALLINT NOT NULL CHECK (> 0) | Для `regular` = число заданий (1 задание = 1 балл). Для `mock_exam` по умолчанию `exam_types.max_primary`, можно изменить |
| due_mode | ENUM(`next_lesson`,`fixed`) NOT NULL | Как определён первоначальный дедлайн |

Ограничение: `CHECK (kind <> 'mock_exam' OR exam_type_id IS NOT NULL)`.

### 5.2. `homework_materials`
Файлы преподавателя к заданию (PDF и т. п.).
`id`, `homework_id FK ON DELETE CASCADE`, `s3_key`, `original_name`, `content_type`, `size_bytes`.

### 5.3. `homework_assignments` (выдача конкретному ученику)
| Поле | Тип | Описание |
|---|---|---|
| id | BIGINT PK | |
| homework_id | FK → homeworks ON DELETE CASCADE | |
| student_id | FK → users | |
| status | ENUM(`assigned`,`submitted`,`needs_revision`,`graded`,`expired`) NOT NULL DEFAULT 'assigned' | |
| original_due_at | TIMESTAMPTZ NOT NULL | Первоначальный дедлайн |
| due_at | TIMESTAMPTZ NOT NULL | Текущий дедлайн |
| extensions_count | SMALLINT NOT NULL DEFAULT 0 CHECK (0..2) | Количество переносов |
| submission_type | ENUM(`files`,`self_reported`) NULL | |
| submitted_at | TIMESTAMPTZ NULL | |
| score | SMALLINT NULL CHECK (>= 0) | Балл (целое) |
| graded_at | TIMESTAMPTZ NULL | |
| graded_by | FK → users NULL | |
| graded_after_expiry | BOOL NOT NULL DEFAULT false | Оценено после `expired` вручную |
| teacher_comment | TEXT NULL | |
| student_comment | TEXT NULL | Комментарий ученика при сдаче |
| expired_at | TIMESTAMPTZ NULL | |

Ограничения:
- `UNIQUE (homework_id, student_id)`.
- Бизнес-проверка (сервис): `0 <= score <= homeworks.max_score`.
- Индексы: `(student_id, status)`, `(status, due_at)`, `(homework_id)`.

Вычисляемые на лету (не хранятся):
- `is_overdue` = `now() > due_at AND status IN ('assigned','needs_revision')`.
- `score_percent` = `score * 100.0 / max_score`.
- `on_time` = `submitted_at <= original_due_at`.

Жизненный цикл статусов:
```
assigned ──(ученик сдал)──▶ submitted ──(оценка)──▶ graded
   │                            │
   │                            └─(доработка)──▶ needs_revision ──(сдал)──▶ submitted
   └──(дедлайн прошёл и extensions_count = 2)──▶ expired ──(ручная оценка)──▶ graded (graded_after_expiry = true)
```
`needs_revision` также подвержен `expired` по тем же правилам, при возврате преподаватель задаёт новый `due_at` (по умолчанию — следующее занятие).

### 5.4. `homework_extensions` (журнал переносов)
`id`, `assignment_id FK ON DELETE CASCADE`, `old_due_at`, `new_due_at`, `created_by FK → users`, `created_at`.

Правила переноса:
- Только персонал. Не более 2 переносов на выдачу (`extensions_count`).
- Новый дедлайн = начало ближайшего следующего `scheduled` урока ученика после текущего `due_at`.
- Если следующего урока нет, персонал вручную выбирает дату (считается переносом).
- Перенос возможен только в статусах `assigned`, `needs_revision` и до `expired`.

Правила `expired`:
- Условие: `now() > due_at AND extensions_count = 2 AND status IN ('assigned','needs_revision')`.
- Если переносов осталось < 2, а срок прошёл, выдача остаётся «просрочена» (вычисляемо), ученик может сдать, персонал видит её в списке и решает, переносить ли.

### 5.5. `homework_files` (файлы выдачи)
| Поле | Тип | Описание |
|---|---|---|
| id | BIGINT PK | |
| assignment_id | FK → homework_assignments ON DELETE CASCADE | |
| uploaded_by | FK → users | |
| role | ENUM(`student_solution`,`teacher_review`) NOT NULL | |
| s3_key | VARCHAR(500) NOT NULL | |
| original_name | VARCHAR(255) NOT NULL | |
| content_type | VARCHAR(100) NOT NULL | |
| size_bytes | INTEGER NOT NULL | |
| created_at | TIMESTAMPTZ | |

Лимиты (проверяются в сервисе): ≤ 10 файлов `student_solution` на выдачу, ≤ 10 МБ каждый, `image/jpeg`, `image/png`, `image/heic`, `application/pdf`.

## 6. Пробные экзамены

### 6.1. `mock_exam_results`
Единая таблица результатов пробников (из ДЗ или проведённых на уроке). Графики читают только её.

| Поле | Тип | Описание |
|---|---|---|
| id | BIGINT PK | |
| student_id | FK → users NOT NULL | |
| exam_type_id | FK → exam_types NOT NULL | |
| exam_date | DATE NOT NULL | |
| primary_score | SMALLINT NOT NULL CHECK (>= 0) | |
| max_primary | SMALLINT NOT NULL | Максимум этого варианта (снимок) |
| geometry_score | SMALLINT NULL | Только ОГЭ математика (правило «не менее 2 баллов по геометрии») |
| converted_value | SMALLINT NULL | Оценка 2–5 или тестовый балл; NULL если шкала неприменима |
| scale_year | SMALLINT NULL | Год применённой шкалы |
| assignment_id | FK → homework_assignments ON DELETE SET NULL NULL UNIQUE | Источник, если пробник был ДЗ |
| comment | TEXT NULL | |
| created_by | FK → users | |

Правила конвертации (сервис `ExamScoringService`):
1. Если `max_primary` результата ≠ `exam_types.max_primary`, конвертация не применяется (`converted_value = NULL`), в UI показывается «шкала не применима (нестандартный максимум)».
2. Иначе значение берётся из `grade_scales` по году экзамена и `primary_score`.
3. ОГЭ математика: если `geometry_score < config.min_geometry` (2), итоговая оценка — `2` независимо от суммы (при сумме ≥ 8; для сумм 0–7 и так 2). Если `geometry_score` не указан, показывается предупреждение, расчёт по сумме.
4. При оценке ДЗ типа `mock_exam` запись в `mock_exam_results` создаётся/обновляется автоматически (`exam_date` = дата оценки, либо дата урока).

Индекс: `(student_id, exam_type_id, exam_date)`.

## 7. Служебные таблицы

### 7.1. `notifications` (outbox)
| Поле | Тип | Описание |
|---|---|---|
| id | BIGINT PK | |
| user_id | FK → users NOT NULL | Получатель |
| type | VARCHAR(50) NOT NULL | См. список в `05` |
| payload | JSONB NOT NULL | Данные для шаблона (id сущностей, значения) |
| dedup_key | VARCHAR(200) NOT NULL UNIQUE | Защита от дублей |
| is_urgent | BOOL NOT NULL DEFAULT false | Игнорирует тихие часы |
| scheduled_for | TIMESTAMPTZ NOT NULL | |
| status | ENUM(`pending`,`sent`,`failed`,`skipped`) NOT NULL DEFAULT 'pending' | |
| attempts | SMALLINT NOT NULL DEFAULT 0 | |
| sent_at | TIMESTAMPTZ NULL | |
| last_error | TEXT NULL | |

Индекс: `(status, scheduled_for)`.

### 7.2. `audit_log`
| Поле | Тип | Описание |
|---|---|---|
| id | BIGINT PK | |
| actor_user_id | FK → users NULL | |
| action | VARCHAR(80) NOT NULL | `lesson.rescheduled`, `student.price_changed`, `invite.created`, … |
| entity_type | VARCHAR(50) NOT NULL | |
| entity_id | BIGINT NULL | |
| data | JSONB NOT NULL DEFAULT '{}' | Было/стало |
| created_at | TIMESTAMPTZ NOT NULL | |

Обязательно журналируются: смена цены, перенос/отмена урока, выпуск/отзыв приглашения, перепривязка Telegram, архивация, ручная оценка просроченного ДЗ, смена ролей.

## 8. Диаграмма связей (упрощённо)

```
users 1─1 student_profiles
users 1─* guardians
users *─* subjects (student_subjects)
users 1─* auth_tokens

schedule_templates *─* users (participants)
schedule_templates 1─* lessons
lessons 1─* lesson_participants *─1 users

homeworks 1─* homework_assignments *─1 users
homeworks 1─* homework_materials
homework_assignments 1─* homework_files
homework_assignments 1─* homework_extensions
homework_assignments 1─0..1 mock_exam_results
users 1─* mock_exam_results *─1 exam_types
exam_types 1─* grade_scales
users 1─* notifications
```

## 9. Сиды (начальные данные)
- `subjects`: informatics, math.
- `exam_types`: 4 записи (см. раздел 10).
- `grade_scales`: шкалы 2026 года (раздел 10).
- Первый владелец создаётся скриптом `scripts/create_owner.py` или при старте по `OWNER_TELEGRAM_ID`.

## 10. Шкалы экзаменов (2026 год)

> Источники: Письмо Рособрнадзора от 18.02.2026 № 04-44 (ОГЭ); сводные таблицы по ЕГЭ 2026 (Т—Ж, Мир вузов), т. е. вторичные источники. **Перед запуском сверить с официальными шкалами ФИПИ/Рособрнадзора.** Шкалы ЕГЭ утверждаются ежегодно после досрочного периода. Обновлять строки в `grade_scales` с новым `valid_year`.

### 10.1. ОГЭ информатика (`oge_informatics`), max первичный = 21
| Оценка | Первичные баллы |
|---|---|
| 2 | 0–4 |
| 3 | 5–10 |
| 4 | 11–16 |
| 5 | 17–21 |

> Внимание: в ранней версии документации стояли границы 5–11 / 12–16 для оценок 3/4. По письму Рособрнадзора 2026 верно: «3» = 5–10, «4» = 11–16.

### 10.2. ОГЭ математика (`oge_math`), max первичный = 31
| Оценка | Первичные баллы |
|---|---|
| 2 | 0–7 |
| 3 | 8–14 |
| 4 | 15–21 |
| 5 | 22–31 |

Условие: для оценок 3, 4, 5 необходимо **не менее 2 баллов по геометрии** (задания 15–19, 23–25), иначе выставляется «2». `exam_types.config = {"min_geometry": 2}`.

### 10.3. ЕГЭ информатика (`ege_informatics`), max первичный = 29

| Первичный | Тестовый | Первичный | Тестовый | Первичный | Тестовый |
|---|---|---|---|---|---|
| 0 | 0 | 10 | 51 | 20 | 78 |
| 1 | 7 | 11 | 54 | 21 | 80 |
| 2 | 14 | 12 | 56 | 22 | 83 |
| 3 | 20 | 13 | 59 | 23 | 85 |
| 4 | 27 | 14 | 62 | 24 | 88 |
| 5 | 34 | 15 | 64 | 25 | 90 |
| 6 | 40 | 16 | 67 | 26 | 93 |
| 7 | 43 | 17 | 70 | 27 | 95 |
| 8 | 46 | 18 | 72 | 28 | 98 |
| 9 | 48 | 19 | 75 | 29 | 100 |

Минимальный порог аттестата: 40 тестовых (6 первичных).

### 10.4. ЕГЭ математика профильная (`ege_math_profile`), max первичный = 32

| Первичный | Тестовый | Первичный | Тестовый | Первичный | Тестовый |
|---|---|---|---|---|---|
| 0 | 0 | 11 | 64 | 22 | 90 |
| 1 | 6 | 12 | 70 | 23 | 92 |
| 2 | 11 | 13 | 72 | 24 | 94 |
| 3 | 17 | 14 | 74 | 25 | 95 |
| 4 | 22 | 15 | 76 | 26 | 96 |
| 5 | 27 | 16 | 78 | 27 | 97 |
| 6 | 34 | 17 | 80 | 28 | 98 |
| 7 | 40 | 18 | 82 | 29 | 99 |
| 8 | 46 | 19 | 84 | 30 | 100 |
| 9 | 52 | 20 | 86 | 31 | 100 |
| 10 | 58 | 21 | 88 | 32 | 100 |

Минимальный порог аттестата: 5 первичных (27 тестовых).

> Пример пользователя «пробник по информатике на 27 баллов» допустим: `max_primary = 27` отличается от 29 — конвертация не применится, останется процент от максимума (см. раздел 6).

## 11. Статистические формулы (для сервиса `StatsService`)
- **Заработано за период:** `SUM(price_snapshot)` по `lesson_participants` где `is_billable = true`, урок (`lessons.status` ∈ `completed`, `cancelled`) и `lessons.start_at` в периоде.
- **Ожидается за период:** `SUM(student_profiles.lesson_price)` по участникам уроков `scheduled` в периоде.
- **Отмены:** число уроков `cancelled` в периоде (и по участникам).
- **Средний процент ДЗ (неделя):** среднее `score*100/max_score` по `graded` выдачам, сгруппированным по ISO-неделе `graded_at` (в часовом поясе ученика). `expired` без оценки не входит.
- **% в срок:** `count(on_time) / count(submitted_or_graded_or_expired)` за период.
- **Пробники:** динамика `converted_value` (или процент `primary_score/max_primary` для нестандартных максимумов).
