# Настройки репозитория GitHub

Дата: 2026-10-05
Репозиторий: `RomanNik24/LMS_TUTOR`
Задача: T0.03 (TERM-агент)

## 1. Что включено

| Настройка | Состояние | Как сделано |
|---|---|---|
| Метки (labels) | ✅ 7 из 7 | `bug`, `feature`, `docs`, `ops`, `blocked`, `needs-owner`, `security` — описания на русском |
| Вехи (milestones) | ✅ 3 из 3 | Milestone A · Скелет живёт, Milestone B · Рабочее ядро, Milestone C · MVP готов |
| Проверка секретов (gitleaks) | ✅ установлен, репозиторий чист | `gitleaks detect --no-git` — находок в файлах проекта нет; `gitleaks detect` по истории — `no leaks found` (3 коммита) |

Примечание к метке `bug`: она была в списке меток GitHub по умолчанию, поэтому её
описание и цвет обновлены, а не созданы заново. Остальные шесть меток созданы.

## 2. Что не удалось включить

Все перечисленные ниже настройки требуют прав **администратора** репозитория.
У аккаунта `Nikolnik24`, от которого выполнялась настройка, есть только права
**write** (уровень collaborator), поэтому GitHub отклонил запросы с `404 Not Found`.

| Настройка | Требуемое действие владельца |
|---|---|
| Разрешить **только squash merge** | `Settings → General → Pull Requests`: снять `Allow merge commits` и `Allow rebase merging`, оставить `Allow squash merging` |
| Автоудаление head-веток после merge | `Settings → General → Pull Requests → Automatically delete head branches` → включить |
| Dependabot alerts | `Settings → Code security and analysis → Dependabot alerts` → включить |
| Secret scanning | `Settings → Code security and analysis → Secret scanning` → включить |
| Защита `main` (только PR, запрет force-push) | `Settings → Branches → Add rule` / Rulesets: обязательный PR, запрет force push. Обязательные проверки CI пока **не включать** — CI ещё нет |

Текущее состояние (по умолчанию GitHub): squash `true`, merge `true`, rebase `true`,
автоудаление `false`. То есть **до ручной правки владельцем слить можно любым способом**.

## 3. Правило работы с `main`

> Изменения в `main` вносятся **только через Pull Request**.
> Merge выполняет **владелец** и только при зелёном CI.
> Force-push и переписывание опубликованной истории запрещены.

## 4. Видимость репозитория

Репозиторий **public** — так заложено в плане проекта на этапе разработки
(раздел «Этап P», шаг P.1). Перед появлением реальных данных владелец
переводит репозиторий в **private**.

## 5. Проверка секретов

`gitleaks` установлен через winget (версия 8.30.1).

Результат `gitleaks detect --no-git --redact`: 2 срабатывания, оба — ложные,
находки внутри `.venv/Lib/site-packages/sqlalchemy/...` (сторонний код зависимости).
Каталог `.venv` исключён правилами репозитория и в Git не попадает.
Ни одного секрета в файлах проекта и в истории Git не обнаружено.
