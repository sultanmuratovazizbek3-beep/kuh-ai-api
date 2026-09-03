# Бриф для Grok-агентов — KUH AI / amoCRM (kuhhospital)

Скопируй этот файл целиком в новый чат с Grok-агентом и укажи роль (A / B / C / или «продолжи всё»).

---

## Контекст проекта

**Путь:** `C:\Users\ACC-2\amocrm-analytics`  
**Цель:** заменить Desk-приложение на AI-помощник **внутри amoCRM**: CRM → STT/заметки → подсказки → запись в примечание сделки.  
**Аккаунт:** https://kuhhospital.amocrm.ru (id `31612974`, страна **UZ**)  
**Профиль интеграции:** Client ID `4b1a3bfc-df9e-4e52-a6ac-c40dab529b31`, имя «AI Помощник менеджера», креды в `.env` (`AMO_LONG_LIVED_TOKEN` и т.д.).

**Не трогать:** Med24 (`med24-amocrm-integration`), telegram-bot.

---

## Текущее состояние (факт)

### Работает
- Backend FastAPI `:8090` — `api_server.py`, ACL `widget_acl.py`
- Эндпоинты: `/api/v1/widget/config|acl|access_check`, assistant lead / write_note
- Виджет собран: `public/kuh-assistant-widget.zip` (manifest v1.1.0, locations lcard-1/ccard-1/settings)
- **Основной рабочий UI сейчас — браузерное расширение** `browser-extension/` (v1.4.0): панель KUH AI в карточке сделки (Разобрать / копировать / В заметку)
- Автозапуск Windows (schtasks): `KUHAI_API`, `KUHAI_Collector`, `KUHAI_TunnelRunner`, `KUHAI_Watchdog` — см. `install_always_online.ps1`
- Tunnel URL смотреть в `public/API_PUBLIC_URL.txt` (quick tunnel **меняется** после рестарта)
- Для расширения на этом ПК API: `http://127.0.0.1:8090`

### НЕ работает / блокер
- Private widget **не загружен** в amo (`has_widget: false`)
- Причина: `GET /ajax/v4/additional_agreements` → `status=not_defined`, `entity_type=legal_entity`
- Upload zip → `400 You have not filled additional agreement`
- Форма соглашения — **паспорт/поля РФ**; пользователь — **ИП Узбекистан**. Отдельной UZ-формы нет: либо маппинг UZ→RU поля, либо поддержка amo
- OAuth token **не** хватает для agreement/upload (нужны session cookies из браузера)
- Cookies: `data/_ycookies/` или live Yandex/Edge (файл Cookies часто locked, пока браузер открыт)

### Скрипты
- `wait_and_upload_widget.py` (`--once` / `--status`) — после agreement залить zip + настройки
- `УСТАНОВИТЬ_ВИДЖЕТ.bat` / `READY_INSTALL_WIDGET.ps1`
- `build_widget.py`, `run_extension_now.py`
- Документы: `AGENT_HANDOFF.md`, `READY.txt`, `WIDGET_INSTALL.md`, `INSTALL_EXTENSION.md`, `data/IP_STEPS.txt`

---

## Поручения агентам

### Агент A — Инфраструктура «всегда онлайн»
1. Проверь `http://127.0.0.1:8090/health` и задачи `KUHAI_*`.
2. Если упало — `install_always_online.ps1` или `start_always_online.bat`.
3. Следи: tunnel URL → `public/API_PUBLIC_URL.txt` + патч default в `widget/script.js` + `build_widget.py`.
4. Не убивай Med24 / telegram.
5. Отчёт: health, tunnel URL, state scheduled tasks.

### Агент B — Расширение = основной продукт
1. Держи `browser-extension/` как главный UX, пока marketplace заблокирован.
2. RU UI, анализ, копирование, запись заметки через API.
3. Актуализируй `INSTALL_EXTENSION.md` / `run_extension_now.py`.
4. Smoke: health + открыть сделку + панель видна.
5. Отчёт: как ставить менеджерам, что осталось vs виджет.

### Агент C — Marketplace-виджет (финиш после соглашения)
1. Когда пользователь сохранит доп.соглашение (ИП/UZ в поля РФ): закрыть браузер ~5с → cookies → `wait_and_upload_widget.py --once`.
2. Проверить `has_widget`, выставить settings: `api_base` из `API_PUBLIC_URL.txt`, `access_mode=all_managers`.
3. Не подставлять фейковые паспорт/ИНН.
4. Отчёт: agreement status, upload ok/fail, что указать в настройках виджета.

### Агент D — (опционально) Поддержка UZ в инструкции
Упростить UX-путь: «Мое приложение → Создать интеграцию → приватная → ИП» + таблица полей UZ→RU в `READY.txt`.

---

## Критерии Done

**Путь Extension (сейчас):** менеджер открыл сделку → KUH AI → разобрал → скопировал/записал заметку; API автозапуск после логина Windows.

**Путь Widget:** agreement `performed|accepted` → zip uploaded → `has_widget=true` → виджет в правой колонке сделки с рабочим HTTPS `api_base`.

---

## Быстрые команды

```powershell
cd C:\Users\ACC-2\amocrm-analytics
Invoke-RestMethod http://127.0.0.1:8090/health
Get-Content public\API_PUBLIC_URL.txt
Get-ScheduledTask KUHAI_* | Format-Table TaskName, State
.\.venv\Scripts\python.exe wait_and_upload_widget.py --status
.\.venv\Scripts\python.exe wait_and_upload_widget.py --once
powershell -NoProfile -ExecutionPolicy Bypass -File .\install_always_online.ps1
```

---

## Сообщение пользователю (тон)
Отвечай по-русски, коротко. Не предлагай Desk как основной UI. Честно говори про блокер agreement / РФ-форму vs UZ ИП.
