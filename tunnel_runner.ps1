# Keeps Cloudflare quick tunnel alive for local API :8090.
# Writes public\API_PUBLIC_URL.txt and optionally patches widget default api_base.
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Cloudflared = Join-Path $Root "bin\cloudflared.exe"
$UrlFile = Join-Path $Root "public\API_PUBLIC_URL.txt"
$Log = Join-Path $Root "data\tunnel.log"
$WidgetScript = Join-Path $Root "widget\script.js"
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$BuildWidget = Join-Path $Root "build_widget.py"

function Write-Log($msg) {
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Add-Content -Path $Log -Value $line -Encoding UTF8
}

function Update-WidgetDefaultUrl([string]$Url) {
    if (-not (Test-Path $WidgetScript)) { return }
    try {
        $js = Get-Content -Path $WidgetScript -Raw -Encoding UTF8
        $pattern = 'base\s*=\s*"https://[a-z0-9-]+\.trycloudflare\.com"'
        $replacement = 'base = "' + $Url + '"'
        if ($js -match $pattern) {
            $newJs = [regex]::Replace($js, $pattern, $replacement, 1)
            if ($newJs -ne $js) {
                Set-Content -Path $WidgetScript -Value $newJs -Encoding UTF8 -NoNewline
                Write-Log ("Patched widget default api_base -> " + $Url)
                if ((Test-Path $Python) -and (Test-Path $BuildWidget)) {
                    & $Python $BuildWidget 2>> $Log | Out-Null
                    Write-Log "Rebuilt public\kuh-assistant-widget.zip"
                }
            }
        }
    } catch {
        Write-Log ("Widget patch error: " + $_.Exception.Message)
    }
}

New-Item -ItemType Directory -Force -Path (Split-Path $UrlFile) | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $Log) | Out-Null

if (-not (Test-Path $Cloudflared)) {
    Write-Log "cloudflared missing: $Cloudflared"
    exit 1
}

Write-Log "tunnel_runner started"

while ($true) {
    # Drop stale direct cloudflared instances we do not own (same quick-tunnel args).
    Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" -ErrorAction SilentlyContinue |
      Where-Object { $_.CommandLine -like "*tunnel*--url*127.0.0.1:8090*" } |
      ForEach-Object {
          Write-Log ("Stopping stray cloudflared pid=" + $_.ProcessId)
          Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
      }
    Start-Sleep -Seconds 1

    $stdoutFile = Join-Path $Root "data\tunnel_stdout.log"
    if (Test-Path $stdoutFile) { Remove-Item $stdoutFile -Force -ErrorAction SilentlyContinue }

    $proc = Start-Process -FilePath $Cloudflared `
        -ArgumentList "tunnel","--url","http://127.0.0.1:8090" `
        -RedirectStandardError $stdoutFile `
        -WorkingDirectory $Root -WindowStyle Hidden -PassThru

    Write-Log ("Started cloudflared pid=" + $proc.Id)

    $found = $false
    for ($i = 0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 1
        if (Test-Path $stdoutFile) {
            $content = Get-Content $stdoutFile -Raw -ErrorAction SilentlyContinue
            if ($content -match "https://[a-z0-9-]+\.trycloudflare\.com") {
                $url = $Matches[0]
                $prev = ""
                if (Test-Path $UrlFile) { $prev = (Get-Content $UrlFile -Raw -ErrorAction SilentlyContinue).Trim() }
                Set-Content -Path $UrlFile -Value $url -Encoding ASCII
                Write-Log ("New tunnel URL: " + $url)
                if ($url -ne $prev) { Update-WidgetDefaultUrl $url }
                $found = $true
                break
            }
        }
        if ($proc.HasExited) { break }
    }
    if (-not $found) {
        Write-Log "Could not detect tunnel URL in time"
    }

    if (-not $proc.HasExited) { $proc.WaitForExit() }
    Write-Log ("cloudflared exited, restarting in 3s")
    Start-Sleep -Seconds 3
}
