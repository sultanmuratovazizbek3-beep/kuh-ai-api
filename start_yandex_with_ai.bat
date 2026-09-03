@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  python -m venv .venv
  .venv\Scripts\python.exe -m pip install -r requirements.txt websocket-client -q
) else (
  .venv\Scripts\python.exe -m pip install websocket-client -q >nul 2>&1
)

REM ensure API up
start "KUH-AI-API" /min cmd /c "cd /d %~dp0 && .venv\Scripts\python.exe -m uvicorn api_server:app --host 0.0.0.0 --port 8090"
timeout /t 2 /nobreak >nul

REM inject panel into AmoCRM via CDP (reliable on Yandex)
start "KUH-AI-Inject" cmd /c "cd /d %~dp0 && .venv\Scripts\python.exe cdp_inject.py --watch"
echo.
echo Yandex starting with AI panel injection...
echo Open deal card - blue button KUH AI bottom-right.
echo.
