# Ready installer: waits until amo additional agreement is filled, then uploads widget + configures.
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host "=== KUH AI Widget ready installer ===" -ForegroundColor Cyan

# 1) Ensure API
try {
  $h = Invoke-RestMethod "http://127.0.0.1:8090/health" -TimeoutSec 3
  Write-Host "API OK"
} catch {
  Write-Host "Starting API..."
  Start-Process -FilePath "$Root\.venv\Scripts\python.exe" -ArgumentList "-m","uvicorn","api_server:app","--host","0.0.0.0","--port","8090" -WorkingDirectory $Root -WindowStyle Hidden
  Start-Sleep -Seconds 4
}

# 2) Ensure tunnel URL file
$tunnel = ""
if (Test-Path "$Root\public\API_PUBLIC_URL.txt") {
  $tunnel = (Get-Content "$Root\public\API_PUBLIC_URL.txt" -Raw).Trim().TrimStart([char]0xFEFF)
}
if (-not $tunnel) { $tunnel = "http://127.0.0.1:8090" }
Write-Host "API Base: $tunnel"

# 3) Rebuild zip
& "$Root\.venv\Scripts\python.exe" "$Root\build_widget.py"

# 4) Open amo pages + zip folder
$zip = "$Root\public\kuh-assistant-widget.zip"
Start-Process "https://kuhhospital.amocrm.ru/amo-market/application/"
Start-Sleep -Milliseconds 600
Start-Process "https://kuhhospital.amocrm.ru/amo-market/#category-installed"
Start-Sleep -Milliseconds 400
Start-Process "explorer.exe" -ArgumentList "/select,`"$zip`""

Write-Host ""
Write-Host "НУЖЕН 1 ШАГ В AMO (обязательно) — как ИП / Узбекистан:" -ForegroundColor Yellow
Write-Host "1) В amoМаркет слева откройте 'Мое приложение'"
Write-Host "2) Нажмите 'Создать интеграцию' (или AI Помощник -> Редактировать)"
Write-Host "3) Тип: ПРИВАТНАЯ; в доп.соглашении выберите ИП / физлицо (individual)"
Write-Host "4) Заполните РФ-поля данными УЗ ИП (см. READY.txt / data\IP_STEPS.txt) и сохраните"
Write-Host "5) Скрипт сам догрузит widget.zip, выставит api_base и access_mode=all_managers"
Write-Host ""
Write-Host "Жду, пока соглашение станет performed/accepted..." -ForegroundColor Cyan
Write-Host "(Если COOKIE_ERROR: войдите в amo, закройте браузер ~5 сек, перезапустите)" -ForegroundColor DarkYellow

& "$Root\.venv\Scripts\python.exe" "$Root\wait_and_upload_widget.py" --minutes 45
$code = $LASTEXITCODE

Write-Host ""
if ($code -eq 0) {
  Write-Host "ГОТОВО. Откройте сделку — справа AI Помощник." -ForegroundColor Green
  Write-Host "В настройках виджета api_base = $tunnel"
  Start-Process "https://kuhhospital.amocrm.ru/leads/pipeline/"
} else {
  Write-Host "Пока не установлено. Заполните доп.соглашение как ИП в amo и запустите снова." -ForegroundColor Yellow
  Write-Host "Подробности: READY.txt  |  проверка: python wait_and_upload_widget.py --status"
}
exit $code
