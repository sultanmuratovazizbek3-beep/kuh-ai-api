$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$Py = Join-Path $Root ".venv\Scripts\python.exe"
$Zip = Join-Path $Root "release\CRM-AI-Desk-Setup-1.0.0.zip"
if (-not (Test-Path $Zip)) { powershell -ExecutionPolicy Bypass -File (Join-Path $Root "build_release.ps1") }
$Payload = Join-Path $Root "build_payload\payload"
New-Item -ItemType Directory -Force -Path $Payload | Out-Null
Copy-Item $Zip (Join-Path $Payload "app.zip") -Force
$zipAbs = (Resolve-Path (Join-Path $Payload "app.zip")).Path
& $Py -m PyInstaller --noconfirm --clean --onefile --windowed --name "Setup-CRM-AI-Desk" --add-data "$zipAbs;payload" --distpath (Join-Path $Root "release") --workpath (Join-Path $Root "build\setup_bootstrap") --specpath (Join-Path $Root "build\setup_bootstrap") (Join-Path $Root "setup_bootstrap.py")
$Setup = Join-Path $Root "release\Setup-CRM-AI-Desk.exe"
foreach ($d in @("$env:USERPROFILE\Desktop", "$env:USERPROFILE\OneDrive\Desktop")) {
  if (Test-Path $d) { Copy-Item $Setup (Join-Path $d "Setup-CRM-AI-Desk.exe") -Force }
}
Write-Host "DONE $Setup"
