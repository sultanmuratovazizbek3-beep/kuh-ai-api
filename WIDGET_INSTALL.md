# Установка виджета «AI Помощник» в AmoCRM

Виджет появляется **в правой колонке карточки сделки** (и контакта):
анализ истории + подсказки менеджеру в реальном времени.

Telegram / WhatsApp **не используются**.

Интеграция уже создана в аккаунте `kuhhospital`:

| Параметр | Значение |
|----------|----------|
| UUID / Client ID | `4b1a3bfc-df9e-4e52-a6ac-c40dab529b31` |
| Имя | AI Помощник менеджера |
| Zip | `public\kuh-assistant-widget.zip` |

---

## 0. Блокер: доп.соглашение (ИП / Узбекистан)

Загрузка private `widget.zip` невозможна, пока
`GET /ajax/v4/additional_agreements` не вернёт `status=performed` или `accepted`.

Сейчас типичный ответ: `status=not_defined`, `entity_type=legal_entity`.

### Точный клик-путь

1. Откройте https://kuhhospital.amocrm.ru/amo-market/application/
2. Слева: **«Мое приложение»**
3. **«Создать интеграцию»** (или откройте уже созданную «AI Помощник менеджера» → редактировать)
4. Тип: **приватная** интеграция / загрузка виджета
5. В доп.соглашении выберите **ИП / физлицо (individual)**, не юрлицо
6. Заполните поля (маппинг УЗ→RU ниже) → **Сохранить / Подтвердить**
7. Запустите `УСТАНОВИТЬ_ВИДЖЕТ.bat` или `wait_and_upload_widget.py`

### UZ → RU: маппинг полей формы ИП

Форма amo — российская. Для ИП Узбекистана вписывайте **свои реальные** данные:

| Поле формы amo | Что писать (УЗ ИП) |
|----------------|--------------------|
| ФИО (`full_name`) | ФИО как в паспорте УЗ |
| Серия паспорта (`passport_series`, max ~5) | Серия УЗ паспорта (`AA`/`AB`…). Плейсхолдер `00 00` — РФ; при ошибке валидации попробуйте `AA` |
| Номер паспорта (`passport_number`, max 10) | Номер УЗ паспорта |
| Дата выдачи (`date_of_issue`) | `ДД.ММ.ГГГГ` |
| Кем выдан (`issued_by`) | Орган выдачи УЗ |
| Адрес регистрации (`address`) | Адрес регистрации в УЗ |
| ИНН / TIN (`TIN`, до 12 цифр) | **СТИР / ИНН ИП** Узбекистана (цифры). ПИНФЛ 14 цифр не влезает — только СТИР |
| Телефон (`phone`) | `+998…` |
| E-mail (`email`) | Рабочий email |

Не выдумывайте паспорт/ИНН — amo отвечает `Invalid data`, плюс юридические риски.

После сохранения статуса `performed`/`accepted` скрипт сам зальёт zip.

Проверка статуса:

```powershell
.\.venv\Scripts\python.exe wait_and_upload_widget.py --status
```

---

## 1. Запустить backend

```powershell
cd C:\Users\ACC-2\amocrm-analytics
.\start_all.bat
```

или:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api_server:app --host 0.0.0.0 --port 8090
.\.venv\Scripts\python.exe main.py --no-send
```

Проверка: http://127.0.0.1:8090/health

---

## 2. HTTPS-адрес для виджета (обязательно)

AmoCRM открыт по HTTPS → backend должен быть доступен по **https://...**

### Вариант A — Cloudflare Tunnel (рекомендуется)

```powershell
.\bin\cloudflared.exe tunnel --url http://127.0.0.1:8090
```

или `.\start_tunnel.bat`. Актуальный URL пишется в:

```
public\API_PUBLIC_URL.txt
```

Это и есть **API Base** для настроек виджета (без `/` в конце).

### Вариант B — ngrok

```powershell
ngrok http 8090
```

---

## 3. Собрать zip виджета

```powershell
.\.venv\Scripts\python.exe build_widget.py
```

Файл: `public\kuh-assistant-widget.zip`  
Также: http://127.0.0.1:8090/widget/package.zip

---

## 4. Загрузить в AmoCRM (после соглашения)

Автоматически (предпочтительно):

```powershell
.\УСТАНОВИТЬ_ВИДЖЕТ.bat
# или
.\.venv\Scripts\python.exe wait_and_upload_widget.py
# если соглашение уже сохранено:
.\.venv\Scripts\python.exe wait_and_upload_widget.py --once
```

Вручную:

1. Войти **админом** → **амоМаркет** / **Настройки → Интеграции**
2. Открыть **AI Помощник менеджера**
3. Загрузить `public\kuh-assistant-widget.zip`
4. В настройках указать:

| Поле | Значение |
|------|----------|
| URL API помощника (`api_base`) | содержимое `public\API_PUBLIC_URL.txt` |
| Секретный токен | можно пусто |
| Автообновление сек. | `90` (или `0` чтобы выключить) |
| `access_mode` | `all_managers` |

Прямая ссылка:

```
https://kuhhospital.amocrm.ru/settings/widgets/
```

---

## 4.1. Доступ менеджеров (панель админа)

По умолчанию виджет видят **только администраторы** аккаунта.

В настройках виджета админ видит панель **«Кто может пользоваться»**:

| Режим | Кто видит виджет |
|-------|------------------|
| `admins_only` | только админы (по умолчанию) |
| `all_managers` | все менеджеры аккаунта |
| `selected` | выбранные пользователи |

Кнопка **«Сохранить доступ»** пишет режим в настройки виджета и синхронизирует с backend (`/api/v1/widget/acl`).

Менеджер без доступа видит в карточке сделки сообщение **«Нет доступа»**.

Скрипт установки выставляет `all_managers` автоматически.

---

## 5. Как пользоваться менеджеру

1. Открыть **сделку**
2. Справа панель **AI Помощник**
3. Кнопка **Анализировать** — разбор примечаний/звонков
4. Блоки: оценка /10, что сделать сейчас, готовые ответы, вопросы клиенту, возражения, риски
5. **В примечание** — сохранить разбор в карточку сделки
6. Автообновление каждые N секунд (если включено)

---

## 6. Автозапуск Windows

```powershell
powershell -ExecutionPolicy Bypass -File C:\Users\ACC-2\amocrm-analytics\install_autostart.ps1
```

Создаёт задачи при входе:

- `AmoCRM-Analytics-Collector`
- `AmoCRM-Analytics-API`

Не забудьте отдельно держать cloudflared/ngrok, если API снаружи.

---

## 7. Опционально: AI-ключ

В `.env`:

```env
XAI_API_KEY=xai-...
XAI_MODEL=grok-4.5
```

Без ключа виджет всё равно работает на **эвристиках** (хуже, но полезно).

---

## 8. Проверка API вручную

```powershell
# разбор сделки 123
curl http://127.0.0.1:8090/api/v1/assistant/lead/123
```

---

## Troubleshooting

| Проблема | Что делать |
|----------|------------|
| `You have not filled additional agreement` | Заполнить доп.соглашение как **ИП** (раздел 0) |
| `COOKIE_ERROR` / 401 у скрипта | Войти в amo в Yandex/Edge, закрыть браузер ~5 сек, перезапустить скрипт |
| «Укажите URL API» | Заполнить `api_base` из `public\API_PUBLIC_URL.txt` |
| CORS / blocked | Использовать HTTPS tunnel |
| Пустая история | В сделке нет примечаний; или нет прав API |
| 401 AmoCRM backend | Проверить `AMO_LONG_LIVED_TOKEN` / refresh в `.env` |
| Виджет не в правой колонке | locations `lcard-1` — переустановить zip |
| Туннель сменился | Обновить `api_base` в настройках виджета |

### Обходной путь (уже работает)

Пока marketplace-zip не загружен — используйте Chrome/Edge extension `browser-extension/`
(панель KUH AI в карточке сделки, API `http://127.0.0.1:8090`).
