@echo off
cd /d "%~dp0"
echo Opening Chrome extensions page...
echo Load unpacked -^> folder: browser-extension
echo.
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" "chrome://extensions" "https://kuhhospital.amocrm.ru/"
timeout /t 1 >nul
explorer "%~dp0browser-extension"
echo.
echo 1) Enable Developer mode
echo 2) Load unpacked
echo 3) Select the opened browser-extension folder
pause
