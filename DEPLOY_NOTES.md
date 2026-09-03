# KUH AI API — Render Hobby (черновик)

Статус синхрона: `data/kuh_sync_status.json`  
Деплой **не** запускать, пока Азизбек не скажет «Делай Render».

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

## Когда скажут «Делай Render»
1. `git init` (если ещё нет), убедиться что `.env` не в индексе.
2. GitHub repo + push (Public Git URL ок для Render).
3. Blueprint / сервис из `render.yaml`, env из локального `.env` только в Dashboard (не в чат).
4. Проверка: `GET https://<service>.onrender.com/health`
5. Прописать `api_base` в extension options + widget.
6. ПК: watchdog как backup localhost; cloudflared quick tunnel не основной путь.

## Cold start
Hobby free засыпает ~15 мин без трафика. Первый запрос может занять ~1 минуту.
