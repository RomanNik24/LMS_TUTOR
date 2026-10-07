# 08. REST API, контракты сервисов и права доступа

Фронтенд общается с бэкендом **только** через REST `/api/v1`. Бот и воркер вызывают сервисы напрямую. Источник истины по формату — Pydantic-схемы в `src/schemas/` (из них FastAPI строит OpenAPI, из OpenAPI фронтенд генерирует типы, см. `03`, раздел 14 и `12`).

## 1. Общие соглашения

| Тема | Правило |
|---|---|
| Базовый путь | `/api/v1` |
| Формат | JSON (`application/json`), загрузка файлов — `multipart/form-data` |
| Время | ISO 8601 в UTC с суффиксом `Z`, например `2026-10-14T14:00:00Z`. Даты без времени: `2026-10-14` |
| Идентификаторы | Целые числа |
| Имена полей | `snake_case` (как в Python). Фронтенд использует их как есть |
| Аутентификация | Cookie сессии (`HttpOnly`, `Secure`, `SameSite=Lax`). Токены в заголовках не передаются |
| CSRF | Изменяющие запросы (`POST/PATCH/PUT/DELETE`) обязаны иметь заголовок `X-Requested-With: XMLHttpRequest` и корректный `Origin`; иначе `403 permission_denied` (`details.reason`: `csrf_header` или `csrf_origin`) |
| Пагинация | Query `limit` (по умолчанию 50, максимум 200) и `offset`. Ответ: `{"items": [...], "total": N, "limit": L, "offset": O}` |
| Фильтры по периоду | Query `from` и `to` (даты или ISO-время), период не более 1 года |
| Версионирование | Ломающие изменения → `/api/v2`; добавление необязательных полей — без смены версии |

### Формат ошибок
```json
{ "error": { "code": "homework_extension_limit", "message": "Дедлайн уже переносили 2 раза", "details": {} } }
```
| HTTP | Когда | Примеры `code` |
|---|---|---|
| 400 | Нарушено бизнес-правило | `homework_extension_limit`, `lesson_overlap`, `score_out_of_range` |
| 401 | Нет или истекла сессия | `unauthenticated` |
| 403 | Нет прав | `permission_denied` |
| 404 | Не найдено (в том числе чужие данные ученика) | `not_found` |
| 409 | Конфликт состояния | `lesson_overlap`, `invite_already_used`, `telegram_already_linked` |
| 413 | Файл слишком большой | `file_too_large` |
| 415 | Недопустимый тип файла | `unsupported_file_type` |
| 422 | Ошибка валидации схемы (поля) | `validation_error` с `details.fields` |
| 429 | Превышен лимит запросов | `rate_limited` |
| 500 | Неожиданная ошибка | `internal_error` |

Для данных, к которым у ученика нет доступа, возвращается **404**, а не 403 (не раскрываем существование).

### Две группы эндпоинтов
- `/api/v1/student/*` — для роли `student`; схемы ответов **не содержат** цен, заметок, финансов, чужих данных.
- `/api/v1/admin/*` — для `owner` и `manager`; отдельные пометки «только owner».

## 2. Аутентификация и профиль

| Метод | Путь | Описание | Доступ |
|---|---|---|---|
| POST | `/auth/telegram` | Тело `{ "init_data": "<raw>" }`. Проверка подписи и срока (≤ 24 ч), создание сессии. Ответ: `Me` | публично, rate limit |
| POST | `/auth/link` | Тело `{ "token": "..." }`. Одноразовая ссылка входа из бота `/web`. Ответ: `Me`. Токен погашается **только POST-запросом** (защита от предпросмотра ссылок мессенджерами). Ошибки: `404 login_link_invalid` (нет/просрочен), `409 invite_already_used` (уже использован) | публично, rate limit |
| POST | `/auth/logout` | Удаляет текущую сессию на сервере и cookie. Ответ `204` | авторизован |
| GET | `/me` | Текущий пользователь: `id`, `role`, `display_name`, `timezone` | авторизован |
| PATCH | `/me` | Изменить `timezone` (IANA), `display_name` (1–150 символов); хотя бы одно поле, других полей нет (`422`) | авторизован |

## 3. Справочники (чтение)

| Метод | Путь | Описание | Доступ |
|---|---|---|---|
| GET | `/reference/subjects` | Предметы | авторизован |
| GET | `/reference/exam-types` | Типы экзаменов (код, предмет, вид, макс. балл) | авторизован |
| GET | `/catalog` | Опубликованные услуги | авторизован |

## 4. Student API (`/student/*`, роль `student`)

| Метод | Путь | Описание |
|---|---|---|
| GET | `/student/lessons?from=&to=` | Свои уроки за период (время, предмет, статус, ссылки, ДЗ-метки) |
| GET | `/student/lessons/{id}` | Карточка урока: ссылки Телемоста и доски (из профиля или переопределённые), привязанные ДЗ |
| GET | `/student/homework?status=&limit=&offset=` | Свои выдачи ДЗ. Фильтр `status`: `active`, `submitted`, `graded`, `expired` |
| GET | `/student/homework/{assignment_id}` | Карточка: описание, материалы, дедлайн, `is_overdue`, `extensions_left` (без деталей журнала), оценка, комментарий, свои файлы |
| POST | `/student/homework/{assignment_id}/files` | Загрузка одного файла решения (multipart, поле `file`). Лимиты: ≤ 10 файлов, ≤ 10 МБ, jpg/png/heic/pdf |
| DELETE | `/student/homework/{assignment_id}/files/{file_id}` | Удалить свой файл (пока ДЗ не проверено) |
| POST | `/student/homework/{assignment_id}/submit` | Сдать (после загрузки файлов). Тело: `{ "student_comment": "..." }`. Требует ≥ 1 файла |
| POST | `/student/homework/{assignment_id}/self-report` | Кнопка «Сделал» без файлов. Тело: `{ "student_comment": "..." }` |
| GET | `/student/reports?from=&to=` | Данные для графиков: средний процент ДЗ по неделям, результаты пробников, процент сданных в срок |

Ограничения (проверяет сервер): сдавать можно только в статусах `assigned`, `needs_revision` и не в `expired`; чужая выдача → 404.

## 5. Admin API (`/admin/*`, роли `owner` и `manager`)

### 5.1. Дашборд
| Метод | Путь | Описание |
|---|---|---|
| GET | `/admin/dashboard/today` | Уроки сегодня; очередь проверки; несданное к сегодняшним урокам; уроки без отметки; дедлайны в ближайшие 24 ч; для `owner` дополнительно `earned_month` и `expected_month` |

### 5.2. Ученики и приглашения
| Метод | Путь | Описание |
|---|---|---|
| GET | `/admin/students?status=active|archived&q=&limit=&offset=` | Список |
| POST | `/admin/students` | Создать профиль (имя, класс, предметы, часовой пояс, ссылки; цена только `owner`) |
| GET | `/admin/students/{id}` | Карточка. Поля `lesson_price` и финансовый блок есть **только** в ответе для `owner` |
| PATCH | `/admin/students/{id}` | Правка (цена только `owner`, изменение пишется в `audit_log`) |
| POST | `/admin/students/{id}/archive` | Архивировать |
| POST | `/admin/students/{id}/restore` | Вернуть из архива |
| POST | `/admin/students/{id}/invitations` | Создать/перевыпустить приглашение. Ответ: `{ "url": "https://t.me/<bot>?start=inv_<token>", "expires_at": "..." }` (токен показывается только в этот момент) |
| DELETE | `/admin/invitations/{id}` | Отозвать приглашение |
| POST | `/admin/students/{id}/unlink-telegram` | Снять привязку Telegram (владельцу отвязать самого себя нельзя: 400 `owner_cannot_unlink`) |
| GET | `/admin/students/{id}/report?from=&to=` | Отчёт по ученику (ДЗ, пробники, посещаемость); для `owner` + финансы ученика |

### 5.3. Сотрудники (только `owner`)
| Метод | Путь | Описание |
|---|---|---|
| GET | `/admin/staff` | Список сотрудников |
| POST | `/admin/staff` | Создать профиль сотрудника (`manager` или `owner`) |
| PATCH | `/admin/staff/{id}` | Имя, роль |
| POST | `/admin/staff/{id}/invitations` | Приглашение |
| POST | `/admin/staff/{id}/archive` | Архивировать |

### 5.4. Расписание
| Метод | Путь | Описание |
|---|---|---|
| GET | `/admin/lessons?from=&to=&student_id=&teacher_id=&status=` | Уроки |
| POST | `/admin/lessons` | Создать урок (участники, предмет, время, ссылки-переопределения). 409 `lesson_overlap` при пересечении |
| GET | `/admin/lessons/{id}` | Детали |
| PATCH | `/admin/lessons/{id}` | Тема, заметка, ссылки, участники |
| POST | `/admin/lessons/{id}/reschedule` | Тело `{ "start_at", "end_at" }`; уведомляет участников |
| POST | `/admin/lessons/{id}/cancel` | Тело `{ "reason", "billable_student_ids": [] }` |
| POST | `/admin/lessons/{id}/complete` | Тело: список `{ student_id, attendance, is_billable }`; сервер фиксирует `price_snapshot` |
| GET | `/admin/schedule-templates` | Шаблоны |
| POST | `/admin/schedule-templates` | Создать шаблон (день недели, время, длительность, участники, период) |
| PATCH | `/admin/schedule-templates/{id}` | Править (затрагивает будущие неизменённые уроки) |
| POST | `/admin/schedule-templates/{id}/deactivate` | Отключить |
| POST | `/admin/schedule-templates/generate` | Принудительно дозаполнить уроки на горизонт (идемпотентно) |

### 5.5. Домашние задания
| Метод | Путь | Описание |
|---|---|---|
| GET | `/admin/homework?limit=&offset=` | Список заданий |
| POST | `/admin/homework` | Создать задание и выдать: `kind`, `title`, `description`, `max_score`, `exam_type_id?`, `lesson_id?`, `due_mode`, `due_at?`, `student_ids[]` |
| GET | `/admin/homework/{id}` | Задание и все его выдачи |
| POST | `/admin/homework/{id}/assignees` | Добавить учеников |
| POST | `/admin/homework/{id}/materials` | Загрузить файл-материал (multipart) |
| GET | `/admin/assignments?status=&student_id=&overdue=&limit=&offset=` | Выдачи с фильтрами |
| GET | `/admin/assignments/review-queue` | Очередь проверки (статус `submitted`) |
| GET | `/admin/assignments/{id}` | Выдача: файлы ученика, журнал переносов |
| POST | `/admin/assignments/{id}/grade` | `{ "score", "comment" }`; 400 `score_out_of_range`; для `mock_exam` создаёт результат пробника |
| POST | `/admin/assignments/{id}/return` | Возврат на доработку `{ "comment", "new_due_at?" }` |
| POST | `/admin/assignments/{id}/extend` | Перенос дедлайна: без тела — на следующее занятие; `{ "due_at" }` — вручную, если следующего урока нет. 400 `homework_extension_limit` после двух переносов |
| POST | `/admin/assignments/{id}/review-files` | Файл преподавателя к проверке (multipart) |

### 5.6. Пробные экзамены
| Метод | Путь | Описание |
|---|---|---|
| GET | `/admin/mock-exams?student_id=&exam_type_id=` | Результаты |
| POST | `/admin/mock-exams` | Ввести результат без ДЗ: `student_id`, `exam_type_id`, `exam_date`, `primary_score`, `max_primary`, `geometry_score?`. Ответ включает `converted_value` и `scale_applicable` |
| PATCH | `/admin/mock-exams/{id}` | Исправить |
| DELETE | `/admin/mock-exams/{id}` | Удалить (только ручные; связанные с ДЗ правятся через оценку) |

### 5.7. Каталог услуг
| Метод | Путь | Описание |
|---|---|---|
| GET | `/admin/catalog` | Все карточки, включая неопубликованные |
| POST | `/admin/catalog` | Создать |
| PATCH | `/admin/catalog/{id}` | Править, порядок, публикация |
| DELETE | `/admin/catalog/{id}` | Удалить |

### 5.8. Финансы и статистика
| Метод | Путь | Описание | Доступ |
|---|---|---|---|
| GET | `/admin/finance/earnings?from=&to=&group_by=student|subject|week|month` | Заработано / ожидается | **owner** |
| GET | `/admin/finance/export.csv?from=&to=` | Экспорт CSV | **owner** |
| GET | `/admin/stats/cancellations?from=&to=` | Статистика отмен | staff |
| GET | `/admin/audit?limit=&offset=` | Журнал аудита | **owner** |

## 6. Файлы
| Метод | Путь | Описание |
|---|---|---|
| GET | `/files/{file_id}/url` | Presigned URL на чтение (TTL 10 минут) после проверки прав. Ответ: `{ "url": "...", "expires_in": 600 }` |

## 7. Служебные
| Метод | Путь | Описание |
|---|---|---|
| GET | `/health` (вне `/api/v1`) | Проверка БД и Redis. Ответ `{status, database, redis}`; `200` + `status=ok`, при недоступности БД или Redis — `503` + `status=degraded` и `error` у сбойного компонента |
| POST | `/telegram/webhook/{secret}` (вне `/api/v1`) | Вебхук Telegram; проверка `X-Telegram-Bot-Api-Secret-Token` |
| GET | `/openapi.json` | Схема. Публично доступна только в `local` и `staging`; на `prod` отключена или закрыта |

## 8. Матрица прав «роль × ресурс × действие»

Обозначения: ✅ разрешено, 🔒 только свои данные, ❌ запрещено.

| Ресурс | Действие | student | manager | owner |
|---|---|---|---|---|
| Профиль ученика (имя, класс, ссылки) | просмотр | 🔒 | ✅ | ✅ |
| Профиль ученика | создание, правка, архивация | ❌ | ✅ | ✅ |
| `lesson_price` | просмотр, правка | ❌ | ❌ | ✅ |
| `teacher_notes` (профиль), `teacher_note` (урок) | просмотр, правка | ❌ | ✅ | ✅ |
| Приглашения | создать, отозвать | ❌ | ✅ (для учеников) | ✅ (для всех ролей) |
| Сотрудники | создать, менять роль, архив | ❌ | ❌ | ✅ |
| Уроки | просмотр | 🔒 | ✅ | ✅ |
| Уроки | создать, перенести, отменить, отметить | ❌ | ✅ | ✅ |
| Шаблоны расписания | CRUD | ❌ | ✅ | ✅ |
| Задания | CRUD, выдача | ❌ | ✅ | ✅ |
| Выдача | просмотр | 🔒 | ✅ | ✅ |
| Выдача | сдать, «Сделал», менять свои файлы (до проверки, не `expired`) | 🔒 | ❌ | ❌ |
| Выдача | оценить, вернуть, перенести дедлайн | ❌ | ✅ | ✅ |
| Файлы выдачи | загрузка решения | 🔒 | ❌ | ❌ |
| Файлы выдачи | загрузка проверки | ❌ | ✅ | ✅ |
| Файлы выдачи | чтение | 🔒 | ✅ | ✅ |
| Пробники | просмотр | 🔒 | ✅ | ✅ |
| Пробники | ввод, правка | ❌ | ✅ | ✅ |
| Отчёты ученика | просмотр | 🔒 | ✅ | ✅ |
| Каталог (чтение) | | ✅ | ✅ | ✅ |
| Каталог | CRUD | ❌ | ✅ | ✅ |
| Финансы и заработок | просмотр, экспорт | ❌ | ❌ | ✅ |
| Статистика отмен | просмотр | ❌ | ✅ | ✅ |
| Журнал аудита | просмотр | ❌ | ❌ | ✅ |

Правила:
- **Права проверяет сервер** (в сервисах и зависимостях), а не фронтенд. Скрытая кнопка в интерфейсе безопасностью не считается.
- В ответах для ученика **никогда** нет: `lesson_price`, `price_snapshot`, `is_billable`, `teacher_notes`, `teacher_note`, сумм, данных других учеников. Для групповых уроков показывается только число участников.
- В ответах для `manager` нет `lesson_price` и финансовых блоков (отдельные схемы ответов, а не «скрытие полей на фронтенде»).
- Архивный пользователь не может войти и не получает уведомлений; его сессии удаляются.

## 9. Контракты сервисов (ориентир для реализации)

Все методы принимают `actor: CurrentUser` первым аргументом и проверяют права. Один метод = одна транзакция.

- **AuthService:** `create_invite`, `accept_invite`, `confirm_relink` (и `confirm_relink_by_hash` для бота), `revoke_invite`, `create_web_login_link`, `consume_web_login`, `validate_init_data`, `create_session`, `delete_sessions`, `unlink_telegram`.
- **StudentService / StaffService:** `create_student`, `update_student`, `archive/restore`, `list_students`, `get_student_card` (разные DTO по роли), `create_staff`, `change_role`.
- **ScheduleService:** `create_lesson`, `reschedule_lesson`, `cancel_lesson`, `complete_lesson`, `list_lessons`, `create_template`, `update_template`, `deactivate_template`, `generate_lessons(horizon_weeks)`.
- **HomeworkService:** `create_homework`, `add_assignees`, `submit_files`, `submit_self_reported`, `grade_assignment`, `return_for_revision`, `extend_deadline`, `expire_due_assignments`, `list_assignments`, `list_review_queue`.
- **ExamService:** `record_mock_result`, `convert_score`, `list_results`.
- **StatsService / DashboardService:** `get_today_dashboard`, `earnings`, `cancellations`, `student_report`, `export_csv`.
- **CatalogService:** `list_published`, CRUD.
- **NotificationService:** `enqueue`, `dispatch_due`, `build_morning_digest`.
- **FileService:** `upload_solution`, `upload_material`, `upload_review`, `get_presigned_url`.

## 10. Rate limiting

| Цель | Лимит |
|---|---|
| `/auth/telegram`, `/auth/link` | 10 запросов в минуту на IP |
| Принятие приглашения в боте | 5 попыток за 10 минут на `telegram_id` |
| Загрузка файлов | 30 файлов за 10 минут на пользователя |
| Остальной REST | 120 запросов в минуту на пользователя |

## 11. Правила развития API
1. Новый эндпоинт: сначала Pydantic-схемы, затем роутер, затем `pnpm gen:api` на фронтенде.
2. У каждого эндпоинта указаны `tags`, `summary`, модели ответов для всех кодов (иначе типы во фронтенде будут неточными).
3. Для списков всегда пагинация. Для эндпоинтов с большим ответом (экспорт) задаётся период.
4. Имена `operationId` стабильны и читаемы (`list_student_lessons`, `grade_assignment`): от них зависят имена в сгенерированных типах.
