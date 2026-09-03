@echo off
cd /d "%~dp0"
if not exist .venv (
  python -m venv .venv
  call .venv\Scripts\activate.bat
  pip install -r requirements.txt
) else (
  call .venv\Scripts\activate.bat
)
python build_widget.py
start "AmoCRM-API" cmd /k "cd /d %~dp0 && .venv\Scripts\python.exe -m uvicorn api_server:app --host 0.0.0.0 --port 8090"
timeout /t 2 /nobreak >nul
start "AmoCRM-Collector" cmd /k "cd /d %~dp0 && .venv\Scripts\python.exe main.py --no-send"
echo.
echo API:   http://127.0.0.1:8090/health
echo Widget zip: public\kuh-assistant-widget.zip
echo See WIDGET_INSTALL.md
