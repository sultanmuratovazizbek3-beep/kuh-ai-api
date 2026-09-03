# Build CRM AI Desk distributable package for other PCs
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) { throw "venv missing: $Py" }

Write-Host "==> Installing build deps"
& $Py -m pip install -q pyinstaller pywebview fastapi uvicorn pydantic python-dotenv requests openai apscheduler

Write-Host "==> PyInstaller"
& $Py -m PyInstaller --noconfirm --clean CRMAIDesk.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$Dist = Join-Path $Root "dist\CRMAIDesk"
if (-not (Test-Path $Dist)) { throw "dist\CRMAIDesk not found" }

# Extra runtime files
Copy-Item (Join-Path $Root "START_KUH_AI.bat") $Dist -ErrorAction SilentlyContinue
@"
CRM AI Desk
===========
1. Run CRMAIDesk.exe
2. Open "Подключения CRM" and add amoCRM or Bitrix24
3. Assistant works in RU+UZ

Data: %LOCALAPPDATA%\CRMAIDesk
Reports: Desktop\CRM-AI-Reports
"@ | Set-Content (Join-Path $Dist "README.txt") -Encoding UTF8

# Installer scripts inside package
$InstallPs1 = @'
# CRM AI Desk installer (run as current user — no admin required by default)
$ErrorActionPreference = "Stop"
$Src = Split-Path -Parent $MyInvocation.MyCommand.Path
$Dest = Join-Path $env:LOCALAPPDATA "CRMAIDesk\App"
Write-Host "Installing to $Dest"
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
# copy all
Get-ChildItem $Src -Force | Where-Object { $_.Name -notin @("Install.ps1","Uninstall.ps1") } | ForEach-Object {
  Copy-Item $_.FullName $Dest -Recurse -Force
}
$Exe = Join-Path $Dest "CRMAIDesk.exe"
$W = New-Object -ComObject WScript.Shell
foreach ($d in @([Environment]::GetFolderPath("Desktop"), [Environment]::GetFolderPath("Programs"))) {
  if (-not (Test-Path $d)) { continue }
  $lnk = Join-Path $d "CRM AI Desk.lnk"
  $s = $W.CreateShortcut($lnk)
  $s.TargetPath = $Exe
  $s.WorkingDirectory = $Dest
  $s.Description = "CRM AI Desk"
  $s.Save()
  Write-Host "Shortcut: $lnk"
}
# Uninstaller
$Un = Join-Path $Dest "Uninstall.ps1"
@"
`$Dest = '$Dest'
Remove-Item (Join-Path ([Environment]::GetFolderPath('Desktop')) 'CRM AI Desk.lnk') -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path ([Environment]::GetFolderPath('Programs')) 'CRM AI Desk.lnk') -Force -ErrorAction SilentlyContinue
Remove-Item `$Dest -Recurse -Force -ErrorAction SilentlyContinue
Write-Host 'CRM AI Desk uninstalled'
pause
"@ | Set-Content $Un -Encoding UTF8

# Registry uninstall info (HKCU)
$reg = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\CRMAIDesk"
New-Item $reg -Force | Out-Null
New-ItemProperty $reg -Name "DisplayName" -Value "CRM AI Desk" -Force | Out-Null
New-ItemProperty $reg -Name "Publisher" -Value "KUH / CRM AI" -Force | Out-Null
New-ItemProperty $reg -Name "DisplayVersion" -Value "1.0.0" -Force | Out-Null
New-ItemProperty $reg -Name "InstallLocation" -Value $Dest -Force | Out-Null
New-ItemProperty $reg -Name "UninstallString" -Value "powershell.exe -ExecutionPolicy Bypass -File `"$Un`"" -Force | Out-Null

Write-Host ""
Write-Host "Installed. Launching..."
Start-Process $Exe
Write-Host "Done."
'@
Set-Content -Path (Join-Path $Dist "Install.ps1") -Value $InstallPs1 -Encoding UTF8

# Root Installer.bat for double-click
@"
@echo off
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0Install.ps1"
pause
"@ | Set-Content (Join-Path $Dist "INSTALL.bat") -Encoding ASCII

# Zip package
$Release = Join-Path $Root "release"
New-Item -ItemType Directory -Force -Path $Release | Out-Null
$Zip = Join-Path $Release "CRM-AI-Desk-Setup-1.0.0.zip"
if (Test-Path $Zip) { Remove-Item $Zip -Force }
Compress-Archive -Path (Join-Path $Dist "*") -DestinationPath $Zip -Force

# Also folder copy for portable
$Portable = Join-Path $Release "CRM-AI-Desk-Portable"
if (Test-Path $Portable) { Remove-Item $Portable -Recurse -Force }
Copy-Item $Dist $Portable -Recurse

Write-Host ""
Write-Host "========================================"
Write-Host " BUILD OK"
Write-Host " ZIP:     $Zip"
Write-Host " PORTABLE: $Portable"
Write-Host " Run INSTALL.bat inside zip on any PC"
Write-Host "========================================"
