@echo off
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0READY_INSTALL_WIDGET.ps1"
pause
