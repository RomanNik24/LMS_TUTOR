#!/usr/bin/env bash
# Запуск HTTPS-туннеля для Mini App в разработке (T1.15a, docs/PLAN_FROM_SCRATCH.md T1.16).
#
# Mini App открывается только по HTTPS, а cookie Secure не работают по http, поэтому
# локальный порт пробрасывается наружу через cloudflared quick tunnel (аккаунт не нужен).
# cloudflared — инструмент разработчика, НЕ зависимость проекта.
#
# Использование: scripts/dev_tunnel.sh [порт]   (по умолчанию 5173 — dev-сервер фронтенда)
set -euo pipefail

PORT="${1:-5173}"

if ! [[ "$PORT" =~ ^[0-9]+$ ]] || [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
  echo "Ошибка: порт должен быть числом от 1 до 65535, получено: $PORT" >&2
  exit 2
fi

if ! command -v cloudflared >/dev/null 2>&1; then
  cat >&2 <<'MSG'
Не найден cloudflared. Установите его (это инструмент разработчика, в проект не добавляется):
  Windows: winget install --id Cloudflare.cloudflared
  macOS:   brew install cloudflared
  Linux:   https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
MSG
  exit 1
fi

echo "Запускаю туннель на http://localhost:${PORT} ..."

shown=0
# cloudflared пишет журнал в stderr; адрес появляется в одной из строк
cloudflared tunnel --url "http://localhost:${PORT}" 2>&1 | while IFS= read -r line; do
  echo "$line"
  if [ "$shown" -eq 0 ]; then
    url="$(printf '%s\n' "$line" | grep -oE 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' | head -n 1 || true)"
    if [ -n "$url" ]; then
      shown=1
      cat <<MSG

==================== HTTPS-адрес туннеля ====================
${url}
=============================================================
Адрес меняется при каждом запуске. Сделайте:
  1. В .env.local поставьте PUBLIC_BASE_URL=${url}
     (бэкенд проверяет Origin изменяющих запросов именно по этому значению).
  2. Перезапустите backend (app), чтобы он прочитал новое значение.
  3. Кнопку меню бота в BotFather обновите на новый адрес вручную.
Остановить туннель: Ctrl+C.
MSG
    fi
  fi
done
