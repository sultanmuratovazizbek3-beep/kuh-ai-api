# Install durable always-online stack (Scheduled Tasks + Startup).
# Starts: uvicorn api_server :8090, main.py --no-send, tunnel_runner, watchdog.
# Does NOT touch Med24 / telegram-bot processes.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Startup = [Environment]::GetFolderPath("Startup")
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Pwsh = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"

if (-not (Test-Path $Python)) {
  Write-Host "Creating venv..."
  python -m venv (Join-Path $Root ".venv")
  & $Python -m pip install -r (Join-Path $Root "requirements.txt")
}

# Hidden launcher VBS for Startup folder (manual/backup path)
$vbs = Join-Path $Root "start_online_hidden.vbs"
$bat = Join-Path $Root "start_always_online.bat"
@(
  'Set WshShell = CreateObject("WScript.Shell")',
  ('WshShell.CurrentDirectory = "' + $Root + '"'),
  ('WshShell.Run "cmd /c \"' + $bat + '\" nopause", 0, False')
) | Set-Content -Path $vbs -Encoding ASCII

$lnk = Join-Path $Startup "KUH-AI-AlwaysOnline.lnk"
$w = New-Object -ComObject WScript.Shell
$sc = $w.CreateShortcut($lnk)
$sc.TargetPath = "wscript.exe"
$sc.Arguments = ('"' + $vbs + '"')
$sc.WorkingDirectory = $Root
$sc.WindowStyle = 7
$sc.Save()
Write-Host "Startup: $lnk"

foreach ($old in @(
  "AmoCRM-api.lnk",
  "AmoCRM-collector.lnk",
  "AmoCRM-tunnel.lnk",
  "CRM AI Desk.lnk"
)) {
  $p = Join-Path $Startup $old
  if (Test-Path $p) {
    $bak = $p + ".bak_disabled"
    Move-Item -Path $p -Destination $bak -Force -ErrorAction SilentlyContinue
    Write-Host "Disabled Startup shortcut: $old"
  }
}

function Register-KuhTask {
  param(
    [string]$Name,
    [string]$Execute,
    [string]$Arguments,
    [string]$WorkDir
  )
  $existing = Get-ScheduledTask -TaskName $Name -ErrorAction SilentlyContinue
  if ($existing) {
    Unregister-ScheduledTask -TaskName $Name -Confirm:$false -ErrorAction SilentlyContinue
  }

  $action = New-ScheduledTaskAction -Execute $Execute -Argument $Arguments -WorkingDirectory $WorkDir
  $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
  $settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 999 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew
  $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
  Register-ScheduledTask -TaskName $Name -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
  Write-Host "ScheduledTask: $Name"
}

# Durable long-running tasks (Task Scheduler, unlimited runtime, auto-restart)
Register-KuhTask -Name "KUHAI_API" -Execute $Python `
  -Arguments "-m uvicorn api_server:app --host 0.0.0.0 --port 8090" -WorkDir $Root
Register-KuhTask -Name "KUHAI_Collector" -Execute $Python `
  -Arguments "main.py --no-send" -WorkDir $Root
Register-KuhTask -Name "KUHAI_TunnelRunner" -Execute $Pwsh `
  -Arguments ("-NoProfile -ExecutionPolicy Bypass -File `"$Root\tunnel_runner.ps1`"") -WorkDir $Root
Register-KuhTask -Name "KUHAI_Watchdog" -Execute $Pwsh `
  -Arguments ("-NoProfile -ExecutionPolicy Bypass -File `"$Root\watchdog.ps1`"") -WorkDir $Root

# Remove old ensure task if present (caused duplicate supervisors)
Unregister-ScheduledTask -TaskName "KUHAI_EnsureOnline" -Confirm:$false -ErrorAction SilentlyContinue

Write-Host "Launching via schtasks (escape Job Object)..."
foreach ($tn in @("KUHAI_API","KUHAI_Collector","KUHAI_TunnelRunner","KUHAI_Watchdog")) {
  schtasks /Run /TN $tn | Out-Null
  Start-Sleep -Seconds 1
}

Write-Host "Waiting for API health..."
$ok = $false
for ($i = 0; $i -lt 20; $i++) {
  Start-Sleep -Seconds 2
  try {
    $h = Invoke-RestMethod "http://127.0.0.1:8090/health" -TimeoutSec 3
    if ($h.status -eq "ok") { $ok = $true; break }
  } catch {}
}
if ($ok) { Write-Host "API OK: http://127.0.0.1:8090/health" }
else { Write-Host "API not ready yet - check in a few seconds: http://127.0.0.1:8090/health" }

Write-Host "Tunnel URL file: $Root\public\API_PUBLIC_URL.txt"
Write-Host "Extension folder: $Root\browser-extension"
Write-Host "Done."
