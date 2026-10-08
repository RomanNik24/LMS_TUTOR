# Инструменты разработчика (локально)

Скрипты ниже работают только в разработке и в проект как зависимости не входят.

## Тестовый ученик и ссылка-приглашение (`scripts/dev_create_student.py`)

Создаёт ученика с профилем и выпускает одноразовую ссылку-приглашение (7 дней):

```bash
uv run python scripts/dev_create_student.py --name "Аня" --timezone Europe/Moscow
```

- Нужен владелец: сначала `uv run python scripts/create_owner.py`.
- Имя бота берётся из `--bot-username`; если не задано, запрашивается у Telegram
  (`getMe`, нужен `BOT_TOKEN` в `.env.local`). Токен в вывод не попадает.
- При `APP_ENV=prod` скрипт отказывается работать (код возврата 2).
- Откройте ссылку **со второго Telegram-аккаунта**: бот привяжет его к ученику.
  Повторное открытие той же ссылки покажет «ссылка уже использована».

## Демо-данные (`scripts/seed_demo.py`)

До 100 учеников с профилями, уроками (прошедшими, сегодняшними, будущими), ДЗ в разных статусах и
результатами пробников — для проверки производительности и показа. Нужны владелец
(`scripts/create_owner.py`) и справочники (`scripts/seed_reference.py`).

```bash
uv run python scripts/seed_demo.py --students 100   # создать (повторный запуск без --purge откажется)
uv run python scripts/seed_demo.py --purge          # удалить все демо-данные одной командой
```

Признаки демо-данных: ученик — `telegram_username` вида `demo_001` без `telegram_id`; урок —
тема «Демо-урок»; ДЗ — название начинается с «Демо: ». Настоящие записи под эти признаки не
попадают и `--purge` их не трогает. Уведомления и сообщения в Telegram не создаются. При
`APP_ENV=prod` скрипт отказывается работать.

## HTTPS-туннель для Mini App (`scripts/dev_tunnel.sh`, `scripts/dev_tunnel.ps1`)

Mini App открывается только по HTTPS, а cookie `Secure` не работают по `http`.
Скрипт запускает `cloudflared` quick tunnel (аккаунт не нужен) и печатает адрес:

```bash
scripts/dev_tunnel.sh 5173          # Linux / macOS / Git Bash
.\scripts\dev_tunnel.ps1 -Port 5173 # Windows PowerShell
```

Порт по умолчанию — 5173 (dev-сервер фронтенда `pnpm dev`; Vite проксирует `/api` на backend).
Для полного стека (`docker compose --profile full`, README) укажите порт Nginx: `scripts/dev_tunnel.sh 8080`.
Установка `cloudflared` (Windows): `winget install --id Cloudflare.cloudflared`.

Адрес меняется при каждом запуске, поэтому после старта туннеля:

1. В `.env.local` поставьте `PUBLIC_BASE_URL=<адрес туннеля>` — backend проверяет
   `Origin` изменяющих запросов именно по этому значению (иначе вход вернёт 403).
2. Перезапустите backend, чтобы он прочитал новое значение.
3. Кнопку меню бота в BotFather обновите на новый адрес вручную.

Без туннеля фронтенд можно открывать на `http://localhost:5173`, но тогда
`PUBLIC_BASE_URL=http://localhost:5173`, а кнопка `web_app` в боте не появится
(Telegram принимает только HTTPS).

## Частая ошибка: `/web` открывает `{"error":{"code":"not_found"…}}`

Ссылка входа строится как `PUBLIC_BASE_URL/login/<токен>`. Если в `.env.local` стоит адрес
backend (`http://127.0.0.1:8000`), она откроется на API, где такого маршрута нет. Поставьте
в `PUBLIC_BASE_URL` адрес фронтенда (`http://localhost:5173` или адрес туннеля) и перезапустите backend.
