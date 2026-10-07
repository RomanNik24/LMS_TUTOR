# Smoke этапа 4: файлы домашних заданий, Nginx, S3 (T4.14)

Прогон на ПК разработчика, стек `full`, запросы через Nginx `http://127.0.0.1:8080`, хранилище MinIO.
Версия main: `c037c7e` (feat(frontend): add admin and student homework screens (#56)); PR #55 и #56 влиты.
В документе нет секретов, значений cookie и токенов приглашений.

## Как получены сессии

Как в `docs/ops/SMOKE_STAGE3.md`: `initData` подписывается внутри контейнера `app` токеном бота из настроек (токен не выводится),
приглашения принимаются через `AuthService.accept_invite`. Все POST/DELETE шли с `Origin: <PUBLIC_BASE_URL>` и `X-Requested-With: XMLHttpRequest`.
Тестовые данные: менеджер `SMOKE-T414 manager` (user_id 17), «Аня T414» (18, assignment 1), «Борис T414» (19, assignment 2); обычное ДЗ `kind=regular`, `max_score=13`.
Тестовые файлы лежали в отдельной пустой папке, скрипты в другой: JPEG, PNG, HEIC (сгенерирован через pillow-heif), PDF 60 КБ, PDF 9,9 МБ (10 380 902 байта),
PDF 10 МБ + 1 байт, PDF 13 МБ, `fake.jpg` (начало `MZ…`), пустой файл. Ключи объектов смотрелись через `list_objects_v2` из контейнера `app`.

## Результаты

| № | Проверка | Запрос | Результат | PASS/FAIL |
|---|---|---|---|---|
| 0.1 | Подготовка: main, `pnpm install --frozen-lockfile`, `uv sync --frozen`, `up -d --build`, все сервисы healthy | — | main `c037c7e`; 5 сервисов healthy | PASS |
| 0.2 | `alembic current`, `alembic check` | — | `c4d2e5f7a8b9 (head)`, `No new upgrade operations detected` | PASS |
| 0.3 | Менеджер, два ученика, приглашения, вход; ДЗ обоим | `POST /admin/staff`, `/admin/students`, `…/invitations`, `POST /admin/homework` | 201, вход 200 | PASS |
| 1.1 | Загрузка JPEG | `POST /student/homework/1/files` | 201, `image/jpeg` | PASS |
| 1.2 | Загрузка PNG | то же | 201, хранится как `image/jpeg` | PASS |
| 1.3 | Загрузка HEIC | то же | 201, хранится как `image/jpeg` | PASS |
| 1.4 | Загрузка PDF | то же | 201, `application/pdf` | PASS |
| 1.5 | Файл 9,9 МБ | то же | 201 | PASS |
| 1.6 | Файл 10 МБ + 1 байт | то же | 413 `file_too_large` | PASS |
| 1.7 | `.jpg` с содержимым `MZ…` | то же | 415 `unsupported_file_type` | PASS |
| 1.8 | Пустой файл | то же | 422 `empty_file` | PASS |
| 1.9 | 11-й файл решения (10 уже загружено) | то же | 400 `files_limit` | PASS |
| 1.10 | В ответах загрузки нет `s3_key` | поиск по телу ответов 1.1–1.5 и карточкам | не найдено | PASS |
| 2.1 | Файл около 10 МБ проходит через Nginx | файлы 1.5 и 1.6 | 9,9 МБ → 201; 10 МБ + 1 → 413 JSON `file_too_large` от приложения, не от Nginx | PASS |
| 2.2 | Файл 13 МБ отклоняет Nginx | `POST /student/homework/1/files` | 413, HTML-страница Nginx | PASS |
| 2.3 | Ключи в MinIO | `list_objects_v2`, префикс `homework/` | вид `homework/1/<32 hex>.<jpg\|pdf>`, исходных имён нет; после неудачных загрузок лишних объектов нет | PASS |
| 2.4 | Удаление файла | `DELETE /student/homework/1/files/10` | 204; объект исчез из MinIO (10 → 9), `GET /files/10/url` → 404 | PASS |
| 3.1 | Борис запрашивает файл Ани | `GET /files/1/url` | 404 `file_not_found` | PASS |
| 3.2 | Борис загружает в выдачу Ани | `POST /student/homework/1/files` | 404 `assignment_not_found` | PASS |
| 3.3 | Борис удаляет файл Ани | `DELETE /student/homework/1/files/2` | 404 `assignment_not_found` | PASS |
| 3.4 | Борис сдаёт работу Ани | `POST /student/homework/1/submit` | 404 `assignment_not_found` | PASS |
| 3.5 | Аня получает свою ссылку | `GET /files/1/url` | 200, `expires_in=600` | PASS |
| 3.6 | Ссылка открывается и отдаёт файл (Host = `minio:9000`, через `curl --resolve`) | GET по ссылке | 200, `image/jpeg`, 206 919 байт (как объект в MinIO) | PASS |
| 3.7 | Ссылка в том виде, в каком её выдал API, открывается с хоста | GET по ссылке | хост ссылки `http://minio:9000` недоступен с хоста (000); подмена на `127.0.0.1:9000` ломает подпись (403) | FAIL (см. «Проблемы») |
| 3.8 | Ссылка истекает | та же ссылка через 616 с | 403 `AccessDenied`, `Request has expired` | PASS |
| 3.9 | Менеджер видит файлы ученика и получает ссылки | `GET /admin/assignments/1`, `GET /files/1/url` | 200, в карточке 10 файлов, `s3_key` нет; ссылка открывается (через `--resolve`) → 200 | PASS |
| 4.1 | Rate limit загрузки | 31-я загрузка одного пользователя за 10 минут (маленькие невалидные файлы) | первые 30 попыток дали 404/415, 31-я → 429 `rate_limited` (Борис делал 1 попытку в 3.2 + 29 в цикле, 30-й запрос цикла = 31-я попытка → 429) | PASS |
| 5.1 | Аня сдаёт работу | `POST /student/homework/1/submit` | 200, `status=submitted`, `on_time=true`, `files_count=9` | PASS |
| 5.2 | Очередь проверки | `GET /admin/assignments/review-queue` | 200, выдача 1 в очереди | PASS |
| 5.3 | Файл проверки | `POST /admin/assignments/1/review-files` | 201, `role=teacher_review` | PASS |
| 5.4 | Оценка выше максимума | `POST /admin/assignments/1/grade` `score=14` | 400 `score_out_of_range` | PASS |
| 5.5 | Оценка 11 из 13 | `POST /admin/assignments/1/grade` `score=11` | 200, `status=graded`, `score_percent=85` | PASS |
| 5.6 | Аня видит результат | `GET /student/homework/1` | 200, `score=11`, `teacher_comment`, файл проверки, `extensions_left=2`; журнала переносов и `s3_key` нет | PASS |
| 5.7 | Борис: «Сделал», возврат на доработку | `POST …/2/self-report`, `POST /admin/assignments/2/return` | 200 `submitted`; 200 `needs_revision` | PASS |
| 5.8 | Два переноса срока | `POST /admin/assignments/2/extend` (дата вручную) | 200 (`extensions_left` 1), 200 (`extensions_left` 0) | PASS |
| 5.9 | Третий перенос | то же | 400 `homework_extension_limit` | PASS |
| 6.1 | `uv run python scripts/check.py` | — | 7 из 8: ruff, mypy, pytest, lint, typecheck, build — PASS; `pnpm test --run` — FAIL | FAIL |
| 6.2 | `pnpm gen:api`, `git status` | — | `schema.d.ts` не изменился | PASS |

Итого: PASS 36, FAIL 2 (3.7, 6.1). Не проверено: см. «Проблемы».

## Проблемы

1. **Подписанные ссылки ведут на внутренний адрес Docker (3.7).** `S3_PUBLIC_ENDPOINT` пуст, а `S3_ENDPOINT` в контейнере `app` равен `http://minio:9000`, поэтому ссылка `GET /files/{id}/url` имеет вид `http://minio:9000/lms-files/homework/…`. С хоста и тем более с телефона она не открывается; замена хоста на `127.0.0.1:9000` ломает подпись (403). Открыть удалось только с `curl --resolve minio:9000:127.0.0.1`. Для телефона нужен публичный адрес (туннель на порт 9000 или проксирование через Nginx) и `S3_PUBLIC_ENDPOINT`. Решается отдельно.
2. **Падает `pnpm test --run` (6.1).** Тест `src/features/homework/student/studentHomework.test.tsx` «загрузка отправляет multipart и обновляет карточку; ошибка 415 показывается» (строка 266): `findByText(texts.errors.unsupported_file_type)` не находит текст «Подходят только jpg, png, heic и pdf.» за таймаут. Воспроизводится стабильно, в том числе при запуске файла отдельно (дважды). В DOM после неудачной загрузки есть абзац с классом `text-destructive`, но его текст в логе обрезан. Остальные шаги `check.py` проходят (pytest 156 с, без ошибок, `S3`-тесты на moto зелёные). Код не менялся.
3. **Не проверено:** загрузка и просмотр файлов с телефона и через публичный туннель (см. п. 1); реальный iPhone-HEIC (использован сгенерированный); экран проверки и кнопки во фронтенде в браузере; поведение истёкшего ДЗ с файлами; удаление файла после сдачи (в тесте файл удалялся до сдачи).
4. **Замечание:** в 4.1 лимит посчитан с учётом одной предыдущей попытки Бориса (3.2); в чистом окне 31-я попытка подряд даёт 429 так же.
5. **Тестовые данные оставлены в базе** (`SMOKE-T414`, «Аня T414», «Борис T414», выдачи 1 и 2, 10 объектов в MinIO под `homework/1/`).
