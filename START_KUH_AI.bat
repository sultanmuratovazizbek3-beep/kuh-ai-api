@echo off
cd /d "%~dp0"
if exist "%~dp0Launch_CRM_AI_Desk.vbs" (
  wscript //nologo "%~dp0Launch_CRM_AI_Desk.vbs"
  exit /b 0
)
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" run_crm_ai.py
) else (
  start "" ".venv\Scripts\python.exe" run_crm_ai.py
)
