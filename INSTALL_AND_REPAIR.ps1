# CRM AI Desk — clean install / repair for this PC
# Run: powershell -ExecutionPolicy Bypass -File INSTALL_AND_REPAIR.ps1

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host "=== CRM AI Desk INSTALL / REPAIR ===" -ForegroundColor Cyan
Write-Host "Root: $Root"

# 1) Stop old processes
Write-Host "`n[1/7] Stop old processes..." -ForegroundColor Yellow
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -match 'run_crm_ai|api_main|ui_main|uvicorn' } |
  ForEach-Object {
    Write-Host "  kill PID $($_.ProcessId)"
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
  }
Get-NetTCPConnection -LocalPort 8090 -State Listen -ErrorAction SilentlyContinue |
  ForEach-Object {
    Write-Host "  free port 8090 PID $($_.OwningProcess)"
    Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
  }
Start-Sleep -Seconds 1

# 2) Venv + deps
Write-Host "`n[2/7] Virtualenv + packages..." -ForegroundColor Yellow
$py = Join-Path $Root ".venv\Scripts\python.exe"
$pyw = Join-Path $Root ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $py)) {
  Write-Host "  creating .venv"
  py -3 -m venv .venv
  if (-not (Test-Path $py)) { python -m venv .venv }
}
if (-not (Test-Path $py)) {
  Write-Host "ERROR: no python venv" -ForegroundColor Red
  exit 1
}
& $py -m pip install --upgrade pip -q
& $py -m pip install -r requirements.txt -q
& $py -m pip install "pywebview>=5.0" "fastapi>=0.110" "uvicorn>=0.27" -q
Write-Host "  packages OK"

# 3) Ensure .env
Write-Host "`n[3/7] Config..." -ForegroundColor Yellow
$envFile = Join-Path $Root ".env"
if (-not (Test-Path $envFile)) {
  Write-Host "  WARNING: .env missing" -ForegroundColor Red
} else {
  Write-Host "  .env present"
}
if (-not (Select-String -Path $envFile -Pattern "WRITE_AMO_CALL_NOTES" -Quiet -ErrorAction SilentlyContinue)) {
  Add-Content $envFile "`nWRITE_AMO_CALL_NOTES=0"
}
if (-not (Select-String -Path $envFile -Pattern "STT_MODEL" -Quiet -ErrorAction SilentlyContinue)) {
  Add-Content $envFile "`nSTT_MODEL=medium`nSTT_USE_UZ_HF=0"
}

# 4) AppData folder
Write-Host "`n[4/7] AppData..." -ForegroundColor Yellow
$data = Join-Path $env:LOCALAPPDATA "CRMAIDesk"
New-Item -ItemType Directory -Force -Path (Join-Path $data "logs") | Out-Null
Write-Host "  $data"

# 5) Smoke imports
Write-Host "`n[5/7] Smoke imports..." -ForegroundColor Yellow
& $py smoke_test.py
$smoke1 = $LASTEXITCODE

# 6) Start app + live smoke
Write-Host "`n[6/7] Start application..." -ForegroundColor Yellow
$launcher = Join-Path $Root "run_crm_ai.py"
Start-Process -FilePath $pyw -ArgumentList $launcher -WorkingDirectory $Root
$ok = $false
for ($i = 1; $i -le 40; $i++) {
  try {
    $r = Invoke-WebRequest "http://127.0.0.1:8090/health" -UseBasicParsing -TimeoutSec 2
    if ($r.StatusCode -eq 200) {
      Write-Host "  health OK ($i)" -ForegroundColor Green
      Write-Host "  $($r.Content)"
      $ok = $true
      break
    }
  } catch {
    Write-Host "  wait $i..."
  }
  Start-Sleep -Seconds 0.5
}
if (-not $ok) {
  Write-Host "ERROR: health failed" -ForegroundColor Red
  Write-Host "See: $data\logs\app.log and api.log"
  exit 2
}

& $py smoke_test.py
$smoke2 = $LASTEXITCODE

# 7) Desktop shortcut
Write-Host "`n[7/7] Desktop shortcut..." -ForegroundColor Yellow
$vbs = Join-Path $Root "Launch_CRM_AI_Desk.vbs"
$w = New-Object -ComObject WScript.Shell
foreach ($desk in @(
  [Environment]::GetFolderPath("Desktop"),
  "$env:USERPROFILE\Desktop",
  "$env:USERPROFILE\OneDrive\Desktop",
  "C:\Users\ACC-2\Desktop",
  "C:\Users\ACC-2\OneDrive\Desktop"
) | Select-Object -Unique) {
  if (-not (Test-Path $desk)) { continue }
  $lnk = Join-Path $desk "CRM AI Desk.lnk"
  $sc = $w.CreateShortcut($lnk)
  $sc.TargetPath = "wscript.exe"
  $sc.Arguments = "//nologo `"$vbs`""
  $sc.WorkingDirectory = $Root
  $sc.WindowStyle = 7
  $sc.Description = "CRM AI Desk desktop app"
  $sc.IconLocation = "$env:SystemRoot\System32\shell32.dll,14"
  $sc.Save()
  Write-Host "  $lnk" -ForegroundColor Green
}

Write-Host "`n=== DONE ===" -ForegroundColor Green
Write-Host "Open shortcut: CRM AI Desk"
Write-Host "Logs: $data\logs"
if ($smoke2 -ne 0) {
  Write-Host "Smoke had warnings (see above)" -ForegroundColor Yellow
  exit 3
}
exit 0
