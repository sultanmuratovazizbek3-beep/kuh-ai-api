# One clean Desk stack: kill duplicates, start API+Worker+UI once.
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "Stopping old Desk processes..."
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object {
    $_.CommandLine -and (
      $_.CommandLine -like "*amocrm-analytics*api_main*" -or
      $_.CommandLine -like "*amocrm-analytics*worker_main*" -or
      $_.CommandLine -like "*amocrm-analytics*ui_main*" -or
      $_.CommandLine -like "*amocrm-analytics*main.py*" -or
      $_.CommandLine -like "*uvicorn*api_server*" -or
      $_.CommandLine -like "*amocrm-analytics*run_crm_ai*"
    )
  } |
  ForEach-Object {
    Write-Host ("  kill PID " + $_.ProcessId)
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
  }

Start-Sleep -Seconds 2
$data = Join-Path $env:LOCALAPPDATA "CRMAIDesk"
Remove-Item (Join-Path $data "worker_status.json") -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $data "worker.pid") -Force -ErrorAction SilentlyContinue

Write-Host "Starting via Launch_CRM_AI_Desk.vbs (schtasks)..."
Start-Process -FilePath "wscript.exe" -ArgumentList "//nologo `"$Root\Launch_CRM_AI_Desk.vbs`"" -WorkingDirectory $Root
Start-Sleep -Seconds 6

Write-Host "Checking..."
try {
  $h = Invoke-RestMethod "http://127.0.0.1:8090/health" -TimeoutSec 8
  Write-Host ("health=" + $h.status + " worker=" + $h.worker + " phase=" + $h.worker_phase)
} catch {
  Write-Host ("health FAIL: " + $_.Exception.Message)
}

Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -and $_.CommandLine -like "*amocrm-analytics*" -and $_.CommandLine -match "api_main|worker_main|ui_main" } |
  ForEach-Object {
    $cmd = $_.CommandLine
    if ($cmd.Length -gt 100) { $cmd = $cmd.Substring(0, 100) }
    Write-Host ("RUN " + $_.ProcessId + " " + $cmd)
  }

Write-Host "Done. Use only shortcut: Startup\CRM AI Desk.lnk"
