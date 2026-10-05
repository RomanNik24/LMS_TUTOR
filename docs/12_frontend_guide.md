# 12. Руководство по фронтенду (React + TypeScript)

Документ написан для разработчика, который хорошо знает Python, но почти не знает JavaScript/TypeScript, и для ИИ-агентов, которые пишут код. Здесь объяснено, **как устроен фронтенд, как в нём писать код и почему именно так**.

Связанные документы: `02` (стек), `03` (архитектура), `07` (дизайн), `08` (API), `09` (безопасность).

---

## Часть 1. Как думать о фронтенде (для питониста)

### 1.1. Что такое наше приложение
- Это **SPA** (Single Page Application): браузер один раз скачивает HTML + JavaScript, дальше страницы переключаются без перезагрузки.
- Сервер **не рисует страницы**. Он только отдаёт данные в JSON (`/api/v1/...`). Рисует их код, работающий в браузере или в Telegram WebView.
- Весь наш код после сборки превращается в обычные файлы (`frontend/dist`), которые раздаёт Nginx.
- Фронтенд **не содержит бизнес-логики и секретов** (см. `03`, принцип 7). Он показывает данные и отправляет действия пользователя.

### 1.2. Словарь соответствий

| Python-мир | Мир фронтенда | Комментарий |
|---|---|---|
| `uv` / `pyproject.toml` | `pnpm` / `package.json` | Менеджер пакетов и список зависимостей |
| `uv.lock` | `pnpm-lock.yaml` | Фиксирует версии |
| `ruff` | `ESLint` + `Prettier` | Линтер и форматер |
| `mypy` | `tsc` (компилятор TypeScript) | Проверка типов |
| `pytest` | `Vitest` | Тесты |
| `pydantic` (валидация) | `Zod` | Валидация данных форм |
| `FastAPI` (OpenAPI) | `openapi-typescript` | Из схемы API генерируются типы |
| Функция | **Компонент** | Функция, возвращающая кусок интерфейса |
| Аргументы функции | **props** | Входные данные компонента |
| Локальная переменная, меняющаяся со временем | **state** (`useState`) | При изменении интерфейс перерисуется |
| `async def` / `await` | `async` / `await` | То же самое |
| `dict` | объект `{}` | |
| `list` | массив `[]` | |
| `None` | `null` / `undefined` | В JS два «пустых» значения |
| `f"{x}"` | `` `${x}` `` | Шаблонные строки |
| `import x from y` | `import x from "y"` | Почти то же |
| `__init__.py` | `index.ts` | Файл, реэкспортирующий модуль |

### 1.3. React за 5 минут
**Компонент** — функция, которая принимает данные и возвращает описание интерфейса (JSX, похоже на HTML внутри кода):

```tsx
type LessonCardProps = {
  subject: string;
  startsAt: string; // ISO-строка времени в UTC
};

export function LessonCard({ subject, startsAt }: LessonCardProps) {
  return (
    <div className="rounded-lg border p-4">
      <h3 className="font-semibold">{subject}</h3>
      <p className="text-sm text-muted-foreground">{startsAt}</p>
    </div>
  );
}
```
Использование: `<LessonCard subject="Информатика" startsAt="2026-10-14T14:00:00Z" />`.

**Состояние (state):**

```tsx
import { useState } from "react";

export function Counter() {
  const [count, setCount] = useState(0); // [текущее значение, функция для изменения]
  return <button onClick={() => setCount(count + 1)}>Нажато: {count}</button>;
}
```
Правило: **состояние не меняют напрямую** (`count = count + 1` не сработает). Только через `setCount(...)`.

**Списки:** `items.map(...)`, у каждого элемента обязателен уникальный `key` (используем `id` из БД, а не индекс):
```tsx
{lessons.map((lesson) => (
  <LessonCard key={lesson.id} subject={lesson.subject} startsAt={lesson.start_at} />
))}
```

**Условный вывод:**
```tsx
{isLoading && <Spinner />}
{error && <ErrorMessage error={error} />}
{data && <LessonList lessons={data.items} />}
```

**Хуки** — функции с именем `useXxx`: `useState`, `useEffect`, `useMemo`, и наши собственные (`useLessons`). Правила хуков: вызывать только на верхнем уровне компонента (не внутри `if`/циклов) и только в компонентах или других хуках.

**`useEffect`** — выполнить побочное действие после отрисовки. **Мы почти не используем его для загрузки данных**: для этого есть TanStack Query (часть 4). Частая ошибка новичка — писать `fetch` внутри `useEffect`: так делать нельзя в этом проекте.

### 1.4. TypeScript за 5 минут
TypeScript = JavaScript + типы (аналог type hints, но компилятор их **строго проверяет**).

```ts
// Python: def format_price(value: int) -> str
function formatPrice(value: number): string {
  return `${value} ₽`;
}

// Python: TypedDict / dataclass
type Student = {
  id: number;
  display_name: string;
  school_class: number | null; // «int или None»
  timezone: string;
};

// Python: Literal["scheduled", "completed", "cancelled"]
type LessonStatus = "scheduled" | "completed" | "cancelled";

// Python: list[Student]
const students: Student[] = [];

// Необязательное поле: Python `x: str | None = None`
type Filters = { query?: string };
```

Правила проекта (строго):
- Режим `strict: true`. **Запрещены `any`, `// @ts-ignore`, `// @ts-nocheck`**, а `as`-приведения допустимы только с комментарием, почему это безопасно.
- Если тип неизвестен, используйте `unknown` и проверяйте (как `isinstance` в Python).
- Типы данных API **не пишутся вручную**: они приходят из `frontend/src/api/schema.d.ts` (генерируется). Свои типы пишем только для props и локальных данных.
- Не используйте сложные типовые трюки (`conditional types`, `mapped types`, дженерики с ограничениями) без необходимости. Пишите простой, явный код.
- Включена проверка `noUncheckedIndexedAccess`: `array[0]` имеет тип «элемент или `undefined`». Проверяйте перед использованием.

### 1.5. Две «пустоты»: `null` и `undefined`
- `undefined` — «значения нет» (поле не передали, элемента нет).
- `null` — «значения явно нет» (так приходит `None` из нашего API).
- Проверка обоих: `if (value == null)` (допустимо) или `value === null || value === undefined`.
- Опциональная цепочка: `student?.profile?.timezone` — вернёт `undefined`, если что-то по пути пустое (в Python пришлось бы писать несколько `if`).
- Значение по умолчанию: `value ?? "по умолчанию"`.

### 1.6. Сравнение, копирование, неизменяемость
- Сравнивайте строго: `===` и `!==`. Не используйте `==` (кроме `== null`).
- Объекты и массивы в состоянии **не изменяют**, а создают копию:
```ts
setItems([...items, newItem]);                      // добавить
setItems(items.filter((i) => i.id !== idToRemove)); // удалить
setItem({ ...item, title: "Новое название" });      // изменить поле
```
- `const` — переменную нельзя переназначить (используем по умолчанию). `let` — только если нужно переназначать. `var` не используем.

---

## Часть 2. Окружение и команды

### 2.1. Установка
1. **Node.js LTS** (актуальная LTS-версия; версия фиксируется в `frontend/.nvmrc` и в `package.json → engines`).
2. **pnpm**: `corepack enable` (идёт вместе с Node), версия фиксируется в `package.json → packageManager`.
3. Редактор: VS Code с расширениями ESLint, Prettier, Tailwind CSS IntelliSense.

### 2.2. Команды (запускаются в папке `frontend/`)

| Команда | Что делает |
|---|---|
| `pnpm install` | Установить зависимости (как `uv sync`) |
| `pnpm dev` | Dev-сервер с мгновенным обновлением (по умолчанию `http://localhost:5173`) |
| `pnpm build` | Проверка типов + сборка в `dist/` |
| `pnpm preview` | Локальный просмотр собранной версии |
| `pnpm lint` | ESLint |
| `pnpm format` | Prettier |
| `pnpm typecheck` | `tsc --noEmit` (только проверка типов) |
| `pnpm test` | Vitest (юнит и компонентные тесты) |
| `pnpm gen:api` | Сгенерировать `src/api/schema.d.ts` из `openapi.json` бэкенда |
| `pnpm e2e` | Playwright (после MVP-ядра) |

### 2.3. Как работает dev-режим
- `pnpm dev` запускает фронтенд на порту 5173. Бэкенд работает отдельно (например, на 8000).
- В `vite.config.ts` настроен **прокси**: запросы на `/api` и `/health` с 5173 пересылаются на бэкенд. Поэтому в коде везде используются относительные пути, и **CORS не нужен** ни в dev, ни в prod.
- Mini App внутри Telegram требует **HTTPS-адрес**. Для проверки в Telegram с локальной машины используется HTTPS-туннель (например, Cloudflare Tunnel или аналог) на порт 5173 и временный URL в настройках тестового бота. Для обычной разработки достаточно браузера.
- В браузере вне Telegram есть режим отладки: если в `.env.local` указан `VITE_DEV_LOGIN_TOKEN`, экран входа позволяет войти по одноразовой ссылке, которую выдал локальный бэкенд (`/web`). Эта возможность не попадает в prod-сборку.

### 2.4. Что лежит в корне `frontend/`

| Файл | Назначение |
|---|---|
| `package.json` | Зависимости, скрипты, версия Node/pnpm |
| `pnpm-lock.yaml` | Точные версии (в git, не править вручную) |
| `tsconfig.json` | Настройки TypeScript (`strict`, алиас `@/` → `src/`) |
| `vite.config.ts` | Сборка, прокси, алиасы |
| `index.html` | Единственный HTML; подключает `src/main.tsx` |
| `eslint.config.js` | Правила линтера |
| `.prettierrc` | Правила форматирования |
| `components.json` | Настройки shadcn/ui |
| `vitest.config.ts` | Тесты |
| `.env.example` | Шаблон `VITE_*` переменных |

Алиас `@/` означает папку `src/`: `import { Button } from "@/components/ui/button"`. Не используйте цепочки `../../../`.

---

## Часть 3. Структура кода

```
frontend/src/
├── main.tsx                 # Точка входа: подключает провайдеры и роутер
├── App.tsx                  # Корень: проверка входа, выбор режима
├── router.tsx               # Все маршруты
├── api/
│   ├── schema.d.ts          # ГЕНЕРИРУЕТСЯ из OpenAPI (не править)
│   ├── client.ts            # Типизированный HTTP-клиент
│   ├── errors.ts            # ApiError, разбор ошибок
│   └── queryClient.ts       # Настройки TanStack Query
├── features/                # Код, сгруппированный по возможностям
│   ├── auth/                # Вход, хук useMe, защита маршрутов
│   ├── schedule/            # Уроки (student и admin)
│   ├── homework/            # ДЗ (student и admin)
│   ├── exams/               # Пробники
│   ├── reports/             # Графики
│   ├── students/            # Управление учениками (admin)
│   ├── dashboard/           # Дашборд «Сегодня» (admin)
│   ├── finance/             # Финансы (owner)
│   ├── catalog/             # Каталог (admin)
│   └── staff/               # Сотрудники (owner)
├── components/
│   ├── ui/                  # shadcn/ui (Button, Card, Dialog …)
│   └── common/              # Наши общие: StatusBadge, EmptyState, ErrorState, PageHeader …
├── layouts/
│   ├── StudentLayout.tsx    # Нижний таб-бар (мобильный)
│   └── AdminLayout.tsx      # Боковое меню (десктоп) / нижнее (мобильный)
├── lib/
│   ├── telegram.ts          # Работа с Telegram (initData, тема, кнопки)
│   ├── datetime.ts          # Форматирование времени в поясе пользователя
│   ├── texts.ts             # ВСЕ русские тексты интерфейса
│   └── utils.ts             # Мелкие функции (cn и т. п.)
├── styles/
│   ├── globals.css          # Tailwind + подключение токенов
│   └── tokens.css           # Токены дизайна (цвета, радиусы) из 07_design.md
└── test/                    # Настройки тестов, моки MSW
```

Внутри каждой папки `features/<имя>/`:
```
features/homework/
├── api.ts                   # Хуки запросов: useAssignments, useGradeAssignment …
├── components/              # Компоненты только этой возможности
├── pages/                   # Страницы (то, что подключается в router.tsx)
├── schemas.ts               # Zod-схемы форм
└── utils.ts                 # Мелкие функции этой возможности
```

### Правила размещения
1. Страница = компонент в `pages/`, подключается в `router.tsx`. Страница **собирает** экран из компонентов и хуков, сама мало логики.
2. Компонент, нужный только одной возможности, лежит внутри неё. Нужен двум и более — переезжает в `components/common/`.
3. **Запросы к API только в `features/*/api.ts`** (через клиент из `api/client.ts`). Компоненты и страницы не вызывают `fetch` напрямую.
4. **Тексты только в `lib/texts.ts`** (не раскидывайте русские строки по компонентам).
5. **Цвета только через токены** (классы Tailwind вида `bg-primary`, `text-muted-foreground`), без hex-значений в компонентах.
6. Один компонент = один файл, имя файла = имя компонента (`LessonCard.tsx`). Хуки — `useXxx.ts`.
7. Экспорт именованный (`export function X`), а не `export default` (исключение: страницы для `React.lazy`).

---

## Часть 4. Работа с данными (API)

### 4.1. Типы из OpenAPI
1. Бэкенд описывает схемы в Pydantic → FastAPI отдаёт `/openapi.json`.
2. `pnpm gen:api` создаёт `src/api/schema.d.ts` (содержит тип `paths` — все эндпоинты с параметрами и ответами).
3. Если бэкенд изменил схему, а типы не перегенерированы, **сборка фронтенда упадёт** (CI проверяет, что файл актуален). Это защита от рассинхронизации.

### 4.2. HTTP-клиент (`api/client.ts`)
```ts
import createClient from "openapi-fetch";
import type { paths } from "./schema";

// Пути в схеме уже содержат префикс /api/v1, поэтому baseUrl пустой.
// Cookie сессии отправляются автоматически (тот же домен).
export const api = createClient<paths>({
  baseUrl: "",
  headers: { "X-Requested-With": "XMLHttpRequest" }, // защита от CSRF (см. 08)
});
```
Клиент типобезопасный: IDE подсказывает пути, параметры и поля ответа. Ошибся в названии поля, и компилятор сразу скажет.

### 4.3. Обработка ошибок (`api/errors.ts`)
Бэкенд отвечает ошибками в формате `{"error": {"code", "message", "details"}}`. Мы превращаем их в исключение `ApiError`:

```ts
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

type ErrorBody = { error?: { code?: string; message?: string } };

// Принимает результат вызова openapi-fetch, возвращает данные или бросает ApiError.
export function unwrap<T>(result: {
  data?: T;
  error?: unknown;
  response: Response;
}): T {
  if (result.error !== undefined || result.data === undefined) {
    const body = (result.error ?? {}) as ErrorBody; // тело ошибки у нас всегда такого формата
    throw new ApiError(
      result.response.status,
      body.error?.code ?? "unknown_error",
      body.error?.message ?? "Что-то пошло не так",
    );
  }
  return result.data;
}
```

### 4.4. TanStack Query: чтение данных (`features/schedule/api.ts`)
```ts
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { unwrap } from "@/api/errors";

export function useStudentLessons(from: string, to: string) {
  return useQuery({
    queryKey: ["student", "lessons", from, to], // ключ кеша: меняется параметр → новая загрузка
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/student/lessons", {
          params: { query: { from, to } },
        }),
      ),
  });
}
```
Использование на странице:
```tsx
const { data, isPending, isError, error } = useStudentLessons(from, to);

if (isPending) return <PageSkeleton />;
if (isError) return <ErrorState error={error} />;
if (data.items.length === 0) return <EmptyState title={texts.schedule.empty} />;
return <LessonList lessons={data.items} />;
```
**Каждый экран с данными обязан обрабатывать четыре состояния:** загрузка, ошибка, пусто, данные.

### 4.5. TanStack Query: изменение данных
```ts
import { useMutation, useQueryClient } from "@tanstack/react-query";

export function useGradeAssignment(assignmentId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: { score: number; comment?: string }) =>
      unwrap(
        await api.POST("/api/v1/admin/assignments/{assignment_id}/grade", {
          params: { path: { assignment_id: assignmentId } },
          body: input,
        }),
      ),
    onSuccess: async () => {
      // После оценки обновляем связанные списки
      await queryClient.invalidateQueries({ queryKey: ["admin", "assignments"] });
      await queryClient.invalidateQueries({ queryKey: ["admin", "dashboard"] });
    },
  });
}
```
Использование: `mutation.mutate({ score: 11 })`; состояния `mutation.isPending`, `mutation.error`. Во время `isPending` кнопка отключена (защита от двойного нажатия).

### 4.5.1. Соглашение об ключах кеша
`["роль", "сущность", ...параметры]`, например `["admin", "assignments", { status: "submitted" }]`. После изменения данных вызываем `invalidateQueries` для затронутых ключей.

### 4.6. Загрузка файлов
- Клиентская проверка (тип, размер ≤ 10 МБ, не более 10 файлов) нужна **только для удобства**; настоящую проверку делает сервер.
- Отправка через `FormData`, по одному файлу на запрос, чтобы показывать прогресс и ошибки по каждому файлу:
```ts
const form = new FormData();
form.append("file", file);
const response = await fetch(`/api/v1/student/homework/${assignmentId}/files`, {
  method: "POST",
  body: form,
  headers: { "X-Requested-With": "XMLHttpRequest" },
});
```
- Это единственное место, где допустим прямой `fetch` (multipart); он лежит в `features/homework/api.ts` и использует ту же обработку ошибок.
- Для просмотра файла: запросить `GET /api/v1/files/{id}/url`, открыть полученный временный URL. Ссылки не кешируются дольше TTL (10 минут).
- HEIC с iPhone принимаем: сервер сам конвертирует в JPEG.

### 4.7. Права и роли на фронтенде
- Фронтенд знает роль из `GET /me` и использует её **только для навигации и скрытия ненужных кнопок**.
- Менеджер не видит цены и финансы: сервер просто не присылает эти поля (отдельные схемы ответов). Не пытайтесь «скрыть» то, что сервер уже прислал.
- Любое действие может вернуть 403/404 — это обрабатывается как обычная ошибка.

---

## Часть 5. Вход, Telegram и маршрутизация

### 5.1. Сценарии входа
1. **Mini App (основной).** Бот открывает кнопкой `web_app` наш URL. Telegram передаёт параметры запуска в **хэш URL** (`#tgWebAppData=...`). Из них берётся `initData` и отправляется на `POST /api/v1/auth/telegram`. Сервер проверяет подпись и ставит cookie.
2. **Браузер по ссылке.** В боте `/web` выдаёт ссылку `https://<домен>/login/<token>`. Страница показывает кнопку «Войти» и по нажатию отправляет `POST /api/v1/auth/link`. (Погашение токена именно POST-запросом из кода защищает от того, что мессенджер «сожжёт» ссылку при предпросмотре.)
3. **Нет ни того, ни другого.** Экран «Откройте приложение через бота @…» с кнопкой на бота (`VITE_BOT_USERNAME`).

### 5.2. Модуль `lib/telegram.ts`
`initData` читается **один раз при старте**, до запуска роутера (роутер может изменить хэш URL):

```ts
// Читаем параметры запуска Mini App из хэша URL: #tgWebAppData=...&tgWebAppVersion=...
function readInitDataFromHash(): string | null {
  const params = new URLSearchParams(window.location.hash.slice(1));
  return params.get("tgWebAppData"); // URLSearchParams сам декодирует значение
}

// Сохраняем сразу при загрузке модуля, чтобы позже навигация не затёрла хэш
const initialInitData: string | null = readInitDataFromHash();

export function getInitData(): string | null {
  return initialInitData;
}

export function isTelegramMiniApp(): boolean {
  return initialInitData !== null && initialInitData.length > 0;
}
```
Остальное (тема, кнопка «Назад», раскрытие на весь экран, цвета шапки) берётся из `@telegram-apps/sdk-react`. **Точные имена функций SDK меняются между мажорными версиями**, поэтому при установке сверяйтесь с документацией установленной версии, а использование SDK изолируйте в `lib/telegram.ts` (остальной код SDK не импортирует). Мы намеренно не подключаем скрипт `telegram.org/js/telegram-web-app.js`, чтобы приложение не зависело от внешнего адреса, который из РФ может быть недоступен.

### 5.3. Хук `useMe` и защита маршрутов
```tsx
export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: async () => unwrap(await api.GET("/api/v1/me")),
    retry: false,        // 401 не повторяем
    staleTime: 5 * 60_000,
  });
}
```
```tsx
// features/auth/RequireRole.tsx
import { Navigate, Outlet } from "react-router-dom";

type Role = "student" | "manager" | "owner";

export function RequireRole({ allowed }: { allowed: Role[] }) {
  const { data: me, isPending } = useMe();
  if (isPending) return <FullScreenLoader />;
  if (!me) return <Navigate to="/login" replace />;
  if (!allowed.includes(me.role)) return <Navigate to="/" replace />;
  return <Outlet />;
}
```

### 5.4. Маршруты (`router.tsx`)
| Путь | Экран | Доступ |
|---|---|---|
| `/` | Редирект по роли: student → `/app/schedule`, staff → `/admin` | любой вошедший |
| `/login` | Экран входа (автовход через `initData`) | публично |
| `/login/:token` | Вход по одноразовой ссылке | публично |
| `/app/schedule`, `/app/lessons/:id` | Расписание, урок | student |
| `/app/homework`, `/app/homework/:assignmentId` | ДЗ | student |
| `/app/reports` | Графики | student |
| `/app/profile` | Профиль | student |
| `/admin` | Дашборд «Сегодня» | staff |
| `/admin/students`, `/admin/students/new`, `/admin/students/:id` | Ученики | staff |
| `/admin/schedule`, `/admin/lessons/:id`, `/admin/templates` | Расписание | staff |
| `/admin/homework`, `/admin/homework/:assignmentId` | ДЗ и проверка | staff |
| `/admin/mock-exams` | Пробники | staff |
| `/admin/catalog` | Каталог | staff |
| `/admin/finance` | Финансы | owner |
| `/admin/staff` | Сотрудники | owner |

Код админ-части загружается лениво (`React.lazy`), чтобы ученик не скачивал лишнее.

### 5.5. Telegram-специфика
- **Кнопка «Назад»:** на внутренних экранах показывается нативная BackButton Telegram и ведёт на предыдущий экран.
- **Тема:** цвета Telegram передаются в CSS-переменные; наш акцентный цвет остаётся из `07_design.md` (см. часть 7).
- **Safe area:** отступы под вырезы экрана через `env(safe-area-inset-top|bottom)`.
- **Высота экрана:** используйте `100dvh`, а не `100vh` (иначе на телефоне контент прячется под панелями).
- **Не используйте** `localStorage` для чувствительных данных. Сессия живёт в cookie, фронтенд токенов не хранит.

---

## Часть 6. Формы и валидация

Используем **react-hook-form** (управление формой) + **Zod** (правила) — аналог Pydantic.

Пример: оценка ДЗ. Максимум зависит от задания, поэтому схему создаёт функция:

```tsx
// features/homework/schemas.ts
import { z } from "zod";

export function makeGradeSchema(maxScore: number) {
  return z.object({
    score: z
      // Текст ошибки для «не число» задаётся по-разному в Zod 3 и Zod 4 — сверьтесь с документацией установленной версии
      .number({ message: "Введите число" })
      .int("Только целое число")
      .min(0, "Не меньше 0")
      .max(maxScore, `Не больше ${maxScore}`),
    comment: z.string().max(2000, "Слишком длинный комментарий").optional(),
  });
}
export type GradeFormValues = z.infer<ReturnType<typeof makeGradeSchema>>;
```
```tsx
// features/homework/components/GradeForm.tsx
import { useMemo } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

export function GradeForm({ assignmentId, maxScore }: { assignmentId: number; maxScore: number }) {
  const schema = useMemo(() => makeGradeSchema(maxScore), [maxScore]);
  const mutation = useGradeAssignment(assignmentId);
  const form = useForm<GradeFormValues>({ resolver: zodResolver(schema) });

  return (
    <form onSubmit={form.handleSubmit((values) => mutation.mutate(values))}>
      <input type="number" inputMode="numeric" {...form.register("score", { valueAsNumber: true })} />
      {form.formState.errors.score && <p>{form.formState.errors.score.message}</p>}
      <textarea {...form.register("comment")} />
      <button type="submit" disabled={mutation.isPending}>Сохранить</button>
    </form>
  );
}
```
(в реальном коде вместо голых `input`/`button` — компоненты shadcn: `Input`, `Textarea`, `Button`, `Form`.)

Правила:
- Клиентская валидация — для удобства; **окончательная проверка на сервере**. Ошибки сервера (`422 validation_error`, `400` с бизнес-кодом) показываются пользователю понятным текстом из `texts.ts`.
- Кнопки отправки блокируются на время запроса.
- Числовые поля: `inputMode="numeric"` (на телефоне покажется цифровая клавиатура).
- Поля с датой и временем: пользователь вводит локальное время в своём поясе, перед отправкой конвертируем в UTC (см. часть 8).

---

## Часть 7. Стили и дизайн

### 7.1. Tailwind CSS
Стили задаются **классами прямо в JSX**:
```tsx
<div className="flex items-center justify-between rounded-lg border bg-card p-4">
```
- **Mobile-first:** базовые классы — для телефона, а для больших экранов добавляются префиксы `md:` и `lg:`:
  `className="flex flex-col gap-2 md:flex-row md:gap-4"`.
- Не пишите произвольные значения (`w-[317px]`) без причины: используйте шкалу отступов из дизайна.
- Для условных классов используйте функцию `cn(...)` (из `lib/utils.ts`).

### 7.2. shadcn/ui
- Это не библиотека в `node_modules`, а **готовые компоненты, копируемые в проект** (`components/ui`). Их можно и нужно править под дизайн.
- Добавление компонента: `pnpm dlx shadcn@latest add button` (актуальную команду сверяйте с документацией).
- Базовые компоненты: Button, Input, Textarea, Select, Checkbox, Switch, Dialog, Sheet, Tabs, Table, Badge, Card, Calendar, Popover, Skeleton, Toast (Sonner), Form.

### 7.3. Токены дизайна
- Все цвета, радиусы, шрифты — **CSS-переменные в `styles/tokens.css`**, значения берутся из `07_design.md`.
- Tailwind и shadcn читают эти переменные, поэтому смена дизайна = правка одного файла.
- Поддержка светлой и тёмной тем: переменные переопределяются для тёмной темы. Следование теме Telegram и акцентный цвет определяются в `07_design.md`.
- **Если `07_design.md` не заполнен:** используйте нейтральные токены по умолчанию из shadcn и простой минималистичный вид. Если заполнен — следуйте только ему.

### 7.4. Адаптивность
- Ученик: мобильный интерфейс, нижний таб-бар.
- Админ: мобильный вариант + десктопный (боковое меню, таблицы). Таблицы на телефоне превращаются в карточки.
- Проверяйте экраны на ширинах 360, 390, 768, 1280 px.

### 7.5. Доступность (минимум)
- Нажимаемые элементы не меньше 44×44 px.
- У иконок-кнопок есть `aria-label`.
- Не передавайте смысл только цветом (статус — цвет + текст/иконка).
- Контраст текста проверяйте в обеих темах.

---

## Часть 8. Время и часовые пояса
- API присылает время в UTC (`2026-10-14T14:00:00Z`). Пользователь видит время **в своём поясе** (`me.timezone`).
- Не используйте `new Date().getHours()` и подобное (оно работает в поясе устройства). Форматируйте явно:

```ts
// lib/datetime.ts
export function formatTime(iso: string, timeZone: string): string {
  return new Intl.DateTimeFormat("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone,
  }).format(new Date(iso));
}

export function formatDayLabel(iso: string, timeZone: string): string {
  return new Intl.DateTimeFormat("ru-RU", {
    weekday: "long",
    day: "numeric",
    month: "long",
    timeZone,
  }).format(new Date(iso));
}
```
- Группировка уроков по дням делается по **локальной дате в поясе пользователя** (ключ вида `2026-10-14`, получаемый через `Intl.DateTimeFormat("en-CA", { timeZone })`).
- Ввод времени в формах: пользователь выбирает локальное время; для перевода в UTC используйте `date-fns` с `@date-fns/tz` (`TZDate`), а не ручную арифметику со смещениями.
- Дедлайны и «просрочено» вычисляет сервер (`is_overdue`); фронтенд не пересчитывает правила.
- Все функции работы со временем собраны в `lib/datetime.ts` и покрыты тестами (включая переход на летнее/зимнее время для не-российских поясов).

---

## Часть 9. Графики и календарь
- **Графики:** Recharts (`LineChart`, `BarChart`). Данные приходят готовыми из `/student/reports` и `/admin/students/{id}/report`: фронтенд ничего не считает, только рисует. Графики оборачиваются в `ResponsiveContainer`, имеют подписи осей, пустое состояние и доступный текстовый вывод (например, «Последний результат: 78%»).
- **Календарь:** на телефоне — список по дням (основной вид); «неделя» — горизонтальная сетка с прокруткой. Для админа на десктопе — сетка недели. Начинаем с собственной простой реализации на CSS Grid; при необходимости позже подключается готовая библиотека календаря (решение — отдельным согласованием).
- Выбор даты: компонент Calendar из shadcn.

---

## Часть 10. Состояния интерфейса и тексты

### 10.1. Обязательные состояния каждого экрана
| Состояние | Что показываем |
|---|---|
| Загрузка | Скелетоны (не пустой экран и не бесконечный спиннер) |
| Пусто | Понятный текст и, если уместно, кнопка действия («Пока нет ДЗ») |
| Ошибка | Сообщение из `texts.ts` + кнопка «Повторить» |
| Нет сети | Баннер «Нет соединения», повтор при появлении сети |
| Нет прав / не найдено | Нейтральный экран «Недоступно» |
| Идёт отправка | Блокировка кнопки + индикатор |
| Успех | Короткий тост (Sonner) |

Общие компоненты `EmptyState`, `ErrorState`, `PageSkeleton`, `StatusBadge` лежат в `components/common/` и используются везде одинаково.

### 10.2. Тексты
- Все строки интерфейса в `lib/texts.ts`, сгруппированные по возможностям (`texts.schedule.empty`). Язык — русский. Тон и формулировки — по `07_design.md`.
- Сообщения об ошибках API: словарь `код ошибки → текст` в `texts.ts`; если кода нет в словаре, показывается `error.message` от сервера или общий текст.
- Формы множественного числа: функция `plural(n, ["урок", "урока", "уроков"])`.

### 10.3. Статусы
Бейджи статусов (урок, ДЗ, присутствие) — один компонент `StatusBadge` с таблицей соответствия «статус → текст и вариант цвета». Таблица одна, другие места её не дублируют.

---

## Часть 11. Тестирование
- **Vitest + Testing Library:** тестируем поведение, а не реализацию (что видит и может сделать пользователь).
- **MSW** подменяет API в тестах (фронтенд-тесты не обращаются к реальному серверу).
- Что обязательно покрыть на MVP:
  - `lib/datetime.ts` (пояса, группировка по дням, границы суток);
  - `unwrap` и разбор ошибок;
  - `RequireRole` (редиректы по ролям);
  - формы: оценка ДЗ (границы 0 и максимум), создание урока;
  - экран ДЗ ученика: состояния (можно сдать / нельзя, `expired`, просрочено);
  - отсутствие финансовых данных в экранах ученика и менеджера (по присланным данным).
- Пример теста:
```tsx
import { render, screen } from "@testing-library/react";
import { StatusBadge } from "@/components/common/StatusBadge";

it("показывает текст статуса просроченного ДЗ", () => {
  render(<StatusBadge kind="assignment" status="expired" />);
  expect(screen.getByText("Сгорело")).toBeInTheDocument();
});
```
- **Playwright (после ядра):** сквозные сценарии «вход → сдача ДЗ → оценка» на staging или локальном стенде.
- CI: `pnpm lint`, `pnpm typecheck`, `pnpm test`, `pnpm build`, проверка актуальности `schema.d.ts`.

---

## Часть 12. Безопасность фронтенда
- Не храните секреты и токены в коде или `VITE_*` переменных (всё, что в `VITE_*`, видно любому).
- Не используйте `dangerouslySetInnerHTML`. React экранирует текст сам; пользовательский текст (комментарии, описания) выводится только как текст.
- Ссылки Телемоста и доски, введённые преподавателем, открываются только если начинаются с `https://` (проверка и на фронтенде, и на сервере); открываются с `rel="noopener noreferrer"`.
- Не логируйте в консоль `initData`, ответы с персональными данными. В Sentry фронтенда отключена отправка PII; перед отправкой события очищаются URL с токенами.
- Cookie сессии недоступны JavaScript (`HttpOnly`): XSS не сможет их украсть, но всё равно соблюдаем правила выше.
- Зависимости: обновления раз в месяц, `pnpm audit` в CI (предупреждение, не блокировка).

---

## Часть 13. Отладка
| Проблема | Что делать |
|---|---|
| Белый экран | Открыть консоль браузера (F12 → Console), прочитать ошибку |
| Ошибка типов после обновления бэкенда | Запустить `pnpm gen:api` |
| Данные «не обновляются» после действия | Не вызван `invalidateQueries` для нужного ключа |
| Бесконечные перезапросы / перерисовка | В `useEffect` меняется состояние, от которого он же зависит; или ключ запроса создаётся заново на каждый рендер |
| Предупреждение про `key` | В списке нет уникального `key={id}` |
| 401 на всех запросах | Нет cookie: проверить вход, прокси Vite, домен |
| В Telegram работает иначе, чем в браузере | Проверить в Telegram на реальном телефоне (iOS и Android), включить отладку WebView Telegram (Android: Settings → Enable WebView Debug; iOS: Safari Web Inspector), либо подключить консоль Eruda только в staging |
| Время «сдвинулось» на несколько часов | Где-то используется пояс устройства вместо `me.timezone` |

Инструменты: React DevTools и TanStack Query Devtools (подключаются только в dev).

---

## Часть 14. Чек-лист нового экрана (для людей и агентов)
1. Эндпоинты есть в `08`, схемы в бэкенде готовы, выполнен `pnpm gen:api`.
2. Хуки запросов в `features/<имя>/api.ts` с правильными ключами кеша.
3. Страница в `pages/`, маршрут в `router.tsx`, ограничение роли через `RequireRole`.
4. Обработаны все состояния: загрузка, ошибка, пусто, данные, отправка.
5. Тексты в `texts.ts`, статусы через `StatusBadge`, цвета через токены.
6. Мобильная и (для админки) десктопная версии, проверены ширины 360 и 1280 px.
7. Время форматируется через `lib/datetime.ts`.
8. Нет `any`, `ts-ignore`, `console.log`, прямых `fetch` вне `api.ts`.
9. Тесты на логику и ключевые состояния.
10. `pnpm lint && pnpm typecheck && pnpm test && pnpm build` проходят.
11. Экран соответствует `07_design.md` (если заполнен).

---

## Часть 15. План обучения (по мере работы)
Достаточно изучать по необходимости, в таком порядке:
1. Официальный учебник React (`react.dev`, раздел Learn): компоненты, props, state, списки, формы.
2. TypeScript Handbook (`typescriptlang.org/docs`): базовые типы, объекты, union, `null`/`undefined`.
3. Документация TanStack Query: `useQuery`, `useMutation`, `invalidateQueries`.
4. Tailwind CSS: основные утилиты и адаптивные префиксы.
5. shadcn/ui: установка и кастомизация компонентов.
6. React Hook Form + Zod: базовый пример формы.

Главное правило на старте: **читать и править код, который пишет агент, малыми шагами**; после каждого экрана запускать `pnpm lint && pnpm typecheck && pnpm test`, чтобы ошибки находились сразу.
