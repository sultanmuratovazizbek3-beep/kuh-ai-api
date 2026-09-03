@echo off
cd /d "%~dp0"
if not exist bin\cloudflared.exe (
  echo cloudflared missing
  exit /b 1
)
echo Starting Cloudflare tunnel -> http://127.0.0.1:8090
bin\cloudflared.exe tunnel --url http://127.0.0.1:8090
