# Install autostart for current user (no admin required)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Startup = [Environment]::GetFolderPath("Startup")

if (-not (Test-Path $Python)) {
    Write-Host "Creating venv..."
    python -m venv (Join-Path $Root ".venv")
    & $Python -m pip install -r (Join-Path $Root "requirements.txt")
}

function Write-HiddenRunner {
    param([string]$Name, [string]$ArgsLine)
    $vbs = Join-Path $Root ("start_" + $Name + ".vbs")
    $lines = @(
        'Set WshShell = CreateObject("WScript.Shell")',
        ('WshShell.CurrentDirectory = "' + $Root + '"'),
        ('WshShell.Run """' + $Python + '" ' + $ArgsLine + '", 0, False')
    )
    Set-Content -Path $vbs -Value $lines -Encoding ASCII
    $lnkPath = Join-Path $Startup ("AmoCRM-" + $Name + ".lnk")
    $w = New-Object -ComObject WScript.Shell
    $sc = $w.CreateShortcut($lnkPath)
    $sc.TargetPath = "wscript.exe"
    $sc.Arguments = ('"' + $vbs + '"')
    $sc.WorkingDirectory = $Root
    $sc.WindowStyle = 7
    $sc.Save()
    Write-Host "Startup: $lnkPath"
}

Write-HiddenRunner -Name "api" -ArgsLine "-m uvicorn api_server:app --host 0.0.0.0 --port 8090"
Write-HiddenRunner -Name "collector" -ArgsLine "main.py --no-send"

Write-Host "Starting processes now..."
Start-Process -FilePath $Python -ArgumentList "-m","uvicorn","api_server:app","--host","0.0.0.0","--port","8090" -WorkingDirectory $Root -WindowStyle Minimized
Start-Process -FilePath $Python -ArgumentList "main.py","--no-send" -WorkingDirectory $Root -WindowStyle Minimized

Write-Host "Done."
Write-Host "API: http://127.0.0.1:8090/health"
Write-Host "Widget install: open WIDGET_INSTALL.md"
