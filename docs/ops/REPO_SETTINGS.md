# Настройки репозитория GitHub

Дата: 2026-10-05 (обновлено 2026-10-07)
Репозиторий: `RomanNik24/LMS_TUTOR`
Задача: T0.03 (TERM-агент); обновления: T0.13 (CI), T0.14, решение владельца о защите `main`

## 1. Что включено

| Настройка | Состояние | Примечание |
|---|---|---|
| Метки (labels) | ✅ | `bug`, `feature`, `docs`, `ops`, `blocked`, `needs-owner`, `security` (плюс стандартные метки GitHub) |
| Вехи (milestones) | ✅ 3 из 3 | Milestone A · Скелет живёт, Milestone B · Рабочее ядро, Milestone C · MVP готов |
| Secret scanning и push protection | ✅ `enabled` | `GET /repos/RomanNik24/LMS_TUTOR` → `security_and_analysis` |
| Проверка секретов в CI (gitleaks) | ✅ | job `secrets`; `gitleaks detect --source . --redact` по истории — без находок |
| CI | ✅ | `.github/workflows/ci.yml`: jobs `backend`, `frontend`, `secrets` на `pull_request` и `push` в `main` |

## 2. Что осознанно не настраивается

**Решение владельца (2026-10-07): `main` не защищается технически.** Не включаем branch
protection, rulesets и обязательные проверки (required status checks). Состояние на дату
обновления: `GET …/branches/main/protection` → `404 Branch not protected`, `GET …/rulesets` → `[]`.

Также не ограничиваются способы слияния (squash, merge и rebase разрешены) и не включено
автоудаление веток после merge. Рекомендация без обязательности: сливать через **Squash and merge**
(чистая история), а ветку удалять руками после merge.

## 3. Правило работы с `main`

Защиты GitHub нет, поэтому правило соблюдается дисциплиной:

> - Изменения в `main` вносятся **через Pull Request**; прямых коммитов в `main` нет.
> - Merge выполняет **владелец** и только когда все три проверки CI — `backend`, `frontend`,
>   `secrets` — зелёные. GitHub merge при красном CI не блокирует: статус смотрим сами.
> - Force-push и переписывание опубликованной истории `main` запрещены.
> - Рабочая ветка сессии одна (`QWEN.md`, «Branch and PR rule»); после merge она сбрасывается
>   на актуальный `main`.

## 4. Видимость репозитория

Репозиторий **public** — так заложено в плане проекта на этапе разработки
(раздел «Этап P», шаг P.1, ADR 0006). Перед появлением реальных данных владелец
переводит репозиторий в **private** (T9.01).

## 5. Проверка секретов

`gitleaks` запускается с `--redact` (значения секретов не печатаются):

- `gitleaks detect --source . --redact` — по истории Git; ожидается `no leaks found`;
- в CI — job `secrets` (полная история, `fetch-depth: 0`);
- локально — хук `gitleaks` в `.pre-commit-config.yaml`.

Dependabot security updates пока выключены; зависимости проверяются в CI
(`pnpm audit --audit-level=high` блокирует сборку при уязвимостях high и выше) и вручную
(`pip-audit`) при ежемесячном обновлении зависимостей (docs/10 §11).
