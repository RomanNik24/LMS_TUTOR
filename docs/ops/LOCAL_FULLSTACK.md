# Локальный полный прогон и webhook бота (T1.18)

Прогон стека `full` (postgres, redis, minio, app, nginx) на ПК разработчика с бота в режиме webhook через HTTPS-туннель.
В документе нет секретов и полного адреса туннеля: адрес записан как `https://<туннель>`.

## Окружение

| Компонент | Версия |
|---|---|
| ОС | Windows 11 Home Single Language 10.0.26300 |
| Docker Compose | v5.5.1 |
| Docker Engine | 29.8.0 |
| Туннель | cloudflared quick tunnel (аккаунт не нужен) |

## Запуск стека full

```powershell
docker compose --env-file .env.local --profile full up -d --build
docker compose --env-file .env.local --profile full ps
```

Перед запуском на хосте не должно быть backend на порту 8000 и второго polling-процесса бота.
Все пять сервисов должны быть в статусе healthy. Миграции и сиды выполняются внутри контейнера `app`
(`alembic upgrade head`, `scripts/seed_reference.py`, `scripts/create_owner.py`).

## Порядок шагов

1. Обновить `main`: `git fetch origin && git switch main && git pull --ff-only`.
2. Убедиться, что стек `full` запущен и healthy (см. выше).
3. Поднять туннель на Nginx: `.\scripts\dev_tunnel.ps1 -Port 8080`. Скрипт напечатает адрес `https://<туннель>`.
4. Проверить доступность `api.telegram.org` без токена: `curl -I https://api.telegram.org`.
   Прокси (`TELEGRAM_PROXY_URL`, `TELEGRAM_API_BASE`) настраивать только при проблемах.
5. В `.env.local` задать (значения секретов не менять и не печатать):
   ```
   BOT_MODE=webhook
   WEBHOOK_URL=https://<туннель>/telegram/webhook
   PUBLIC_BASE_URL=https://<туннель>
   ```
   `WEBHOOK_SECRET` должен быть непустым. Затем пересоздать app (без `down -v`):
   ```powershell
   docker compose --env-file .env.local --profile full up -d --force-recreate app
   ```
6. Проверить регистрацию вебхука через `getWebhookInfo`. Токен читается из `.env.local` внутри команды и не выводится.
   В выводе допустимы только поля `url` (последний сегмент пути замаскирован), `has_custom_certificate`,
   `pending_update_count`, `last_error_date`, `last_error_message`, `allowed_updates`.
7. Проверить ответы через туннель, логи nginx и app.
8. Вручную проверить бота в Telegram: `/start`, `/help`, `/web`.

## Результаты проверок

| Проверка | Результат | Доказательство |
|---|---|---|
| Хост без backend на :8000 | PASS | На порту 8000 слушает только проброс Docker к контейнеру app |
| Стек full | PASS | postgres, redis, minio, app, nginx: healthy |
| `api.telegram.org` с ПК (п.4) | PASS | `HTTP/1.1 302`, прокси не нужны |
| `getWebhookInfo`: url (п.6) | PASS | `https://<туннель>/telegram/webhook/***` |
| `getWebhookInfo`: ошибки (п.6) | PASS | `last_error_date` и `last_error_message` пусты, `has_custom_certificate=False` |
| `getWebhookInfo`: allowed_updates (п.6) | PASS | `message, callback_query, my_chat_member` |
| `GET https://<туннель>/health` (п.7) | PASS | 200 `{"status":"ok","database":"ok","redis":"ok"}` |
| `POST https://<туннель>/telegram/webhook/wrong` (п.7) | PASS | 404 |
| Лог nginx (п.7) | PASS | Путь вебхука замаскирован: `/telegram/webhook/***` |
| Лог app (п.7) | PASS | Нет traceback'ов, токена и секретов |
| Бот отвечает на `/start`, `/help`, `/web` (п.8) | PASS | Подтверждено вручную в Telegram |
| `getWebhookInfo` после ответов бота (п.8) | PASS | `pending_update_count=0`, `last_error_message` пусто |

## Замечания

- Адрес quick tunnel меняется при каждом перезапуске `cloudflared`. После этого нужно обновить `PUBLIC_BASE_URL` и
  `WEBHOOK_URL` в `.env.local`, пересоздать `app` и вручную поменять адрес кнопки меню бота в BotFather.
- Один токен нельзя одновременно использовать локально в polling и в webhook: локальный polling снимет вебхук (ADR 0009).
  Для возврата к polling поставить `BOT_MODE=polling` и пересоздать `app`.
- `docker compose down -v` удаляет тома с данными, в этом прогоне не использовался.


## Пересборка стека и ошибка 502 (исправлено в T3.11)

Раньше после `docker compose up -d --build` nginx отдавал 502, пока его не перезапустят: он разрешал имя
`app` один раз при старте и держал старый IP контейнера. Теперь адрес backend задан переменной
(`snippets/proxy-app.conf`) и в `conf.d/default.conf` указан резолвер Docker `127.0.0.11` (кеш 5 секунд):
nginx сам находит новый контейнер. Перезапускать nginx после пересборки app не нужно. Если 502 всё же
остаётся дольше нескольких секунд, смотрите `docker compose logs app`: backend не поднялся.
