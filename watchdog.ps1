# Keep API + collector + tunnel always online. Prefer Scheduled Task / Startup.
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Log = Join-Path $Root "data\watchdog.log"
$TunnelVbs = Join-Path $Root "start_tunnel_hidden.vbs"

function Write-Log($msg) {
  $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
  Add-Content -Path $Log -Value $line -Encoding UTF8
}

function Test-Api {
  try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:8090/health" -UseBasicParsing -TimeoutSec 5
    return ($r.StatusCode -eq 200)
  } catch { return $false }
}

function Get-AmoPython {
  Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object {
      $_.CommandLine -and
      ($_.CommandLine -like "*amocrm-analytics*") -and
      ($_.CommandLine -notlike "*med24*") -and
      ($_.CommandLine -notlike "*kuh-telegram-bot*") -and
      ($_.CommandLine -notlike "*telegram-bot*")
    }
}

function Get-ApiServerProcs {
  # api_server:app is unique to this project; cmdline may omit the folder path
  Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object {
      $_.CommandLine -and
      $_.CommandLine -like "*uvicorn*api_server*" -and
      $_.CommandLine -notlike "*med24*" -and
      $_.CommandLine -notlike "*kuh-telegram-bot*"
    }
}

function Get-PortOwner([int]$Port) {
  $lines = netstat -ano | Select-String ":$Port\s+.*LISTENING"
  foreach ($line in $lines) {
    if ($line.Line -match "\s(\d+)\s*$") { return [int]$Matches[1] }
  }
  return $null
}

function Ensure-Uvicorn {
  # On Windows, .venv\Scripts\python.exe often spawns base Python312 as child — keep both.
  $owner = Get-PortOwner 8090
  $procs = @(Get-ApiServerProcs)
  if ($owner) {
    $ownerProc = $procs | Where-Object { $_.ProcessId -eq $owner } | Select-Object -First 1
    if ($ownerProc -and $ownerProc.CommandLine -like "*--host 0.0.0.0*") {
      $keep = @($owner, $ownerProc.ParentProcessId)
      foreach ($p in $procs) {
        if ($keep -notcontains $p.ProcessId) {
          Write-Log ("Stopping duplicate uvicorn pid=" + $p.ProcessId)
          Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        }
      }
      return
    }
  }
  Write-Log "Starting uvicorn (venv, 0.0.0.0:8090)"
  $procs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
  Start-Sleep -Seconds 1
  Start-Process -FilePath $Python -ArgumentList "-m","uvicorn","api_server:app","--host","0.0.0.0","--port","8090" -WorkingDirectory $Root -WindowStyle Hidden
}

function Get-CollectorProcs {
  # --no-send is unique to this collector; Med24/TG do not use it
  Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object {
      $_.CommandLine -and
      $_.CommandLine -like "*main.py*" -and
      $_.CommandLine -like "*--no-send*" -and
      $_.CommandLine -notlike "*med24*" -and
      $_.CommandLine -notlike "*kuh-telegram-bot*"
    }
}

function Ensure-Collector {
  # Keep venv launcher + its base-python child; drop extra collector trees.
  $procs = @(Get-CollectorProcs)
  if ($procs.Count -eq 0) {
    Write-Log "Starting collector main.py --no-send (venv)"
    Start-Process -FilePath $Python -ArgumentList "main.py","--no-send" -WorkingDirectory $Root -WindowStyle Hidden
    return
  }
  $venvRoots = @($procs | Where-Object { $_.CommandLine -like "*amocrm-analytics\.venv\Scripts\python.exe*" })
  if ($venvRoots.Count -gt 0) {
    $keep = New-Object System.Collections.Generic.List[int]
    foreach ($root in $venvRoots) {
      [void]$keep.Add($root.ProcessId)
      foreach ($c in $procs) {
        if ($c.ParentProcessId -eq $root.ProcessId) { [void]$keep.Add($c.ProcessId) }
      }
    }
    # Prefer a single tree: first venv root + children
    $primary = $venvRoots[0].ProcessId
    $keepPrimary = @($procs | Where-Object {
      $_.ProcessId -eq $primary -or $_.ParentProcessId -eq $primary
    } | ForEach-Object { $_.ProcessId })
    foreach ($p in $procs) {
      if ($keepPrimary -notcontains $p.ProcessId) {
        Write-Log ("Stopping duplicate collector pid=" + $p.ProcessId)
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
      }
    }
    return
  }
  Write-Log "Starting collector main.py --no-send (venv)"
  $procs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
  Start-Sleep -Seconds 1
  Start-Process -FilePath $Python -ArgumentList "main.py","--no-send" -WorkingDirectory $Root -WindowStyle Hidden
}

function Ensure-TunnelRunner {
  $runner = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object {
      $_.CommandLine -and (
        $_.CommandLine -like "*tunnel_runner.ps1*" -or
        ($_.Name -eq "powershell.exe" -and $_.CommandLine -like "*amocrm-analytics*tunnel_runner*")
      )
    }
  if ($runner) { return }

  $cf = Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*tunnel*--url*127.0.0.1:8090*" }
  # Bare cloudflared without runner: restart via runner so URL file stays updated
  if ($cf) {
    Write-Log "Bare cloudflared without tunnel_runner - restarting via runner"
    $cf | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 1
  } else {
    Write-Log "Tunnel runner not detected - starting"
  }
  if (Test-Path $TunnelVbs) {
    Start-Process -FilePath "wscript.exe" -ArgumentList ('"' + $TunnelVbs + '"') -WindowStyle Hidden -ErrorAction SilentlyContinue
  } else {
    Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoProfile","-ExecutionPolicy","Bypass","-File",(Join-Path $Root "tunnel_runner.ps1")) -WorkingDirectory $Root -WindowStyle Hidden
  }
}

New-Item -ItemType Directory -Force -Path (Join-Path $Root "data") | Out-Null
if (-not (Test-Path $Python)) {
  Write-Log "ERROR: missing $Python"
  exit 1
}

Write-Log "Watchdog started"
while ($true) {
  try {
    if (-not (Test-Api)) {
      Write-Log "API down - restart uvicorn"
      Get-ApiServerProcs | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
      Get-AmoPython | Where-Object { $_.CommandLine -like "*api_main.py*" } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
      Start-Sleep -Seconds 1
      Start-Process -FilePath $Python -ArgumentList "-m","uvicorn","api_server:app","--host","0.0.0.0","--port","8090" -WorkingDirectory $Root -WindowStyle Hidden
      Start-Sleep -Seconds 3
    } else {
      Ensure-Uvicorn
    }
    Ensure-Collector
    Ensure-TunnelRunner
  } catch {
    Write-Log ("Error: " + $_.Exception.Message)
  }
  Start-Sleep -Seconds 45
}
