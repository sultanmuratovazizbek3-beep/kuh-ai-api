# Adds Cloudflare quick-tunnel to autostart (hidden), same pattern as install_autostart.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Startup = [Environment]::GetFolderPath("Startup")
$Runner = Join-Path $Root "tunnel_runner.ps1"

$vbs = Join-Path $Root "start_tunnel_hidden.vbs"
$lines = @(
    'Set WshShell = CreateObject("WScript.Shell")',
    ('WshShell.CurrentDirectory = "' + $Root + '"'),
    ('WshShell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -File " & Chr(34) & "' + $Runner + '" & Chr(34), 0, False')
)
Set-Content -Path $vbs -Value $lines -Encoding ASCII

$lnkPath = Join-Path $Startup "AmoCRM-tunnel.lnk"
$w = New-Object -ComObject WScript.Shell
$sc = $w.CreateShortcut($lnkPath)
$sc.TargetPath = "wscript.exe"
$sc.Arguments = ('"' + $vbs + '"')
$sc.WorkingDirectory = $Root
$sc.WindowStyle = 7
$sc.Save()
Write-Host "Startup: $lnkPath"

# start it now too, in background
Start-Process -FilePath "wscript.exe" -ArgumentList ('"' + $vbs + '"') -WindowStyle Hidden
Write-Host "Tunnel runner started."
Write-Host "Public URL file: $Root\public\API_PUBLIC_URL.txt"
