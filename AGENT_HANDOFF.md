# Handoff: KUH AI в amoCRM (kuhhospital)

Дата: 2026-08-28  
Проект: `C:\Users\ACC-2\amocrm-analytics`  
Аккаунт amo: `https://kuhhospital.amocrm.ru` (account id 31612974, country UZ)

## Цель продукта
Вместо Desk-приложения — AI-помощник **внутри amoCRM**: разбор звонков/примечаний → подсказки → запись в заметку сделки.  
Админ выдаёт доступ менеджерам (admins_only / all_managers / selected).

## Что уже сделано
1. **Backend** FastAPI `:8090` — `api_server.py`, ACL `widget_acl.py`, эндпоинты:
   - `GET /api/v1/widget/config`
   - `GET|POST /api/v1/widget/acl`
   - `POST /api/v1/widget/access_check`
   - assistant lead / write_note
2. **Виджет** `widget/` v1.1.0 — lcard-1/ccard-1/settings, ACL UI, zip: `public/kuh-assistant-widget.zip`
3. **Интеграция в amo** уже есть:
   - UUID / Client ID: `4b1a3bfc-df9e-4e52-a6ac-c40dab529b31`
   - Имя: «AI Помощник менеджера»
   - `has_widget: false` — zip **ещё не загружен**
4. **Блокер marketplace**: `/ajax/v4/additional_agreements` → `status=not_defined`, `entity_type=legal_entity`.  
   Upload zip → `400 You have not filled additional agreement`.  
   Форма паспорта — **РФ**, у пользователя **Узбекистан / ИП**. Без валидного соглашения private widget не ставится.
5. **Рабочий обход (основной продукт сейчас)**: Chrome/Edge extension `browser-extension/` v1.4.0 —
   панель KUH AI в карточке сделки: **Разобрать / Копировать ответ / В заметку сделки**.
   API default `http://127.0.0.1:8090`. Инструкция: `INSTALL_EXTENSION.md`. One-click: `python run_extension_now.py`.
   (Ранее проверено на lead `31419809`; cookies `data/_ycookies` могут протухать — обновить сессию.)
6. **Креды**: `.env` — `AMO_SUBDOMAIN=kuhhospital`, long-lived token, client id/secret.  
   Cookies Yandex для сессии: `data/_ycookies/` (копия Cookies + Local State).
7. **Скрипты**:
   - `wait_and_upload_widget.py` — ждёт agreement → upload zip
   - `READY_INSTALL_WIDGET.ps1` / `УСТАНОВИТЬ_ВИДЖЕТ.bat`
   - `build_widget.py`
8. **Tunnel** quick cloudflared (URL меняется после рестарта) — смотреть `public/API_PUBLIC_URL.txt`  
   Локальный API для расширения: `http://127.0.0.1:8090` (предпочтительнее на этой машине).
9. ACL backend сейчас: `all_managers`.

## Marketplace finish line (Agent C, 2026-09-03)
- `wait_and_upload_widget.py` hardened: multi-source cookies (+ refresh `_ycookies`), `--status`/`--once`, upload zip, `api_base` из `public/API_PUBLIC_URL.txt`, `access_mode=all_managers`, verify `has_widget`.
- `READY.txt`, `WIDGET_INSTALL.md`, `data/IP_STEPS.txt`, `READY_INSTALL_WIDGET.ps1` — клик-путь ИП + UZ→RU маппинг полей.
- Соглашение на момент проверки: cookies сессии 401 (live DB залочены браузером) → актуальный live-status не прочитан; последний кэш `not_defined` / `legal_entity`. Upload **не** выполнен.
- После `performed`/`accepted`: `УСТАНОВИТЬ_ВИДЖЕТ.bat` или `python wait_and_upload_widget.py --once`.
- Текущий api_base: содержимое `public/API_PUBLIC_URL.txt`.

## Что НЕ сделано / риски
- Marketplace widget не установлен в карточки сделок (ждёт соглашения ИП).
- Quick-tunnel нестабилен (~10ч лимит фоновых задач в этой среде → API/worker/tunnel падают).
- Нет надёжного автозапуска «всегда онлайн» после ребута (частично есть `install_always_online.ps1` / schtasks — проверить).
- Extension: write_note по кнопке готов; нет ACL UI как у marketplace; нужен API на ПК менеджера (или tunnel + смена apiBase).
- Desk UI откатан, не основной путь.
- Для скрипта upload нужны свежие browser cookies (OAuth token для agreement/upload не подходит: 403).

## Файлы-якоря
- `WIDGET_INSTALL.md`, `READY.txt`, `AGENT_HANDOFF.md` (этот файл)
- `widget/script.js`, `widget/manifest.json`, `widget_acl.py`, `api_server.py`
- `browser-extension/`
- `public/kuh-assistant-widget.zip`, `public/API_PUBLIC_URL.txt`

## Критерии готовности
A. **Marketplace path**: agreement filled → zip uploaded → `has_widget=true` → в сделке справа виджет, api_base = текущий HTTPS tunnel, access_mode работает.  
B. **Extension path (сейчас основной)**: расширение стабильно в Edge/Yandex, анализ + копирование фраз, желательно запись заметки; автозапуск API; инструкция для менеджеров на русском.
