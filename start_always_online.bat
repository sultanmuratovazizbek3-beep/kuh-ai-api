@echo off
cd /d "%~dp0"
if not exist .venv (
  python -m venv .venv
  call .venv\Scripts\activate.bat
  pip install -r requirements.txt
) else (
  call .venv\Scripts\activate.bat
)

if not exist data mkdir data
if not exist public mkdir public

echo Starting API on :8090 ...
start "KUH-AI-API" /min cmd /c "cd /d %~dp0 && .venv\Scripts\python.exe -m uvicorn api_server:app --host 0.0.0.0 --port 8090"

timeout /t 2 /nobreak >nul

echo Starting collector+STT+analyze ...
start "KUH-AI-Collector" /min cmd /c "cd /d %~dp0 && .venv\Scripts\python.exe main.py --no-send"

echo Starting Cloudflare tunnel runner ...
start "KUH-AI-Tunnel" /min wscript.exe "%~dp0start_tunnel_hidden.vbs"

echo Starting watchdog (auto-restart) ...
start "KUH-AI-Watchdog" /min powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0watchdog.ps1"

echo ONLINE: http://127.0.0.1:8090/health
echo Tunnel URL file: %~dp0public\API_PUBLIC_URL.txt
echo Extension: %~dp0browser-extension
if /I "%1"=="nopause" exit /b 0
pause
