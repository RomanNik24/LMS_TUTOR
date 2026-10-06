# Запуск HTTPS-туннеля для Mini App в разработке (T1.15a, Windows PowerShell).
#
# Mini App открывается только по HTTPS, а cookie Secure не работают по http, поэтому
# локальный порт пробрасывается наружу через cloudflared quick tunnel (аккаунт не нужен).
# cloudflared - инструмент разработчика, НЕ зависимость проекта.
#
# Использование: .\scripts\dev_tunnel.ps1 [-Port 5173]   (по умолчанию 5173 - dev-сервер фронтенда)
param(
    [ValidateRange(1, 65535)]
    [int]$Port = 5173
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    Write-Error @"
Не найден cloudflared. Установите его (инструмент разработчика, в проект не добавляется):
  winget install --id Cloudflare.cloudflared
"@
    exit 1
}

Write-Host "Запускаю туннель на http://localhost:$Port ..."

$script:shown = $false
# cloudflared пишет журнал в stderr; склеиваем потоки и ищем адрес в строках
& cloudflared tunnel --url "http://localhost:$Port" 2>&1 | ForEach-Object {
    $line = $_.ToString()
    Write-Host $line
    if (-not $script:shown -and $line -match 'https://[a-zA-Z0-9-]+\.trycloudflare\.com') {
        $script:shown = $true
        $url = $Matches[0]
        Write-Host ""
        Write-Host "==================== HTTPS-адрес туннеля ===================="
        Write-Host $url
        Write-Host "============================================================="
        Write-Host "Адрес меняется при каждом запуске. Сделайте:"
        Write-Host "  1. В .env.local поставьте PUBLIC_BASE_URL=$url"
        Write-Host "     (бэкенд проверяет Origin изменяющих запросов именно по этому значению)."
        Write-Host "  2. Перезапустите backend (app), чтобы он прочитал новое значение."
        Write-Host "  3. Кнопку меню бота в BotFather обновите на новый адрес вручную."
        Write-Host "Остановить туннель: Ctrl+C."
    }
}
