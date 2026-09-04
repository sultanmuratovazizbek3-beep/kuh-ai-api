# KUH AI API — Render Hobby

Живой URL: `https://kuh-ai-api.onrender.com`  
Табель и API больше не зависят от этого компьютера.

## Scope
- Cloud: только FastAPI `api_server:app` (assistant / widget / заметки).
- Не на free-образе: `faster-whisper`, `pywebview`, тяжёлый STT.
- Не трогать: Med24 (`med24-amocrm-integration`), telegram-bot.

## Файлы черновика
- `Dockerfile` — Python 3.11-slim, `uvicorn api_server:app`, порт `$PORT`
- `render.yaml` — plan `free`, region `frankfurt`, health `/health`
- `requirements-cloud.txt` — без Whisper
- `.env.example` — только имена ключей
- `.gitignore` — `.env`, cookies, venv
- `.dockerignore` — `.env`, cookies, venv, тяжёлые папки

## Проверка
1. `GET https://kuh-ai-api.onrender.com/health` — `status=ok`, `missing_config=[]`.
2. Виджет Табель: `api_base=https://kuh-ai-api.onrender.com`.
3. ПК больше не нужен. Watchdog/cloudflared — только запасной путь.

## Cold start
Hobby free засыпает ~15 мин без трафика. Keep-alive: `.github/workflows/keep-alive.yml` каждые 10 мин. Первый запрос после сна может занять ~1 минуту.
