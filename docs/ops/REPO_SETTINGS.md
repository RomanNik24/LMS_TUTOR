# Настройки репозитория GitHub

Дата: 2026-10-05 (обновлено 2026-10-06)
Репозиторий: `RomanNik24/LMS_TUTOR`
Задача: T0.03 (TERM-агент); обновления: T0.13 (CI), T0.14 (обязательные проверки `main`)

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
| Защита `main` (только PR, обязательные проверки CI, запрет force-push) | Включить владельцу: `Settings → Branches → Add rule` / Rulesets → обязательный PR, **required status checks `backend`, `frontend`, `secrets`**, запрет force push |

Текущее состояние (по умолчанию GitHub): squash `true`, merge `true`, rebase `true`,
автоудаление `false`. То есть **до ручной правки владельцем слить можно любым способом**.

## 2.1. CI и обязательные проверки `main` (состояние на T0.13/T0.14)

Workflow **существует**: `.github/workflows/ci.yml` (задача T0.13).
Три job-проверки с короткими именами (они и станут required checks):
`backend`, `frontend`, `secrets`. Запускается на `pull_request` и `push` в `main`;
на последних запусках все три job — `success` (пример: run `37447082864`,
push «fix: restore root gitignore rules», 2026-10-06).

Проверено 2026-10-06 (T0.14):
- `GET /repos/RomanNik24/LMS_TUTOR/branches/main/protection` → **`404 Not Found`** — branch protection не настроена;
- `GET /repos/RomanNik24/LMS_TUTOR/rulesets` → **пустой массив** — rulesets не настроены;
- права учётки `Nikolnik24`: `admin: false`, `maintain: false`, `push: true` — включить защиту `main` нельзя.

**Вывод:** обязательные проверки `backend`/`frontend`/`secrets` в GitHub **не включены**.
Это технически невозможно сделать с текущих прав. Ничего не обходилось и не ломалось;
включение остаётся за владельцем (ручная правка в настройках выше).

## 3. Правило работы с `main`

> Изменения в `main` вносятся **только через Pull Request**.
> Merge выполняет **владелец** и только при зелёном CI.
> Force-push и переписывание опубликованной истории запрещены.
>
> **Ручное правило (до включения защиты GitHub владельцем):**
> merge в `main` допустим ТОЛЬКО если все три проверки CI —
> `backend`, `frontend`, `secrets` — зелёные. GitHub технически не блокирует
> merge (защита не настроена, см. §2.1) — правило соблюдается вручную.

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
