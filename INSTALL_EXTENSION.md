# KUH AI — установка расширения (Edge)

Marketplace-виджет amoCRM заблокирован (доп. соглашение РФ).  
**Рабочий путь:** распакованное расширение `browser-extension/` + локальный API.

API: `http://127.0.0.1:8090`

---

## 1. API должен быть онлайн

Проверка: откройте http://127.0.0.1:8090/health → `"status":"ok"`

Если нет — Watchdog обычно поднимает API. На этой машине задачи `KUHAI_API` / `KUHAI_Collector` должны оставаться **Disabled**; работают Watchdog + TunnelRunner.

Ручной запасной старт (только если health мёртв):

```
C:\Users\ACC-2\amocrm-analytics\start_always_online.bat
```

---

## 2. Edge: Load unpacked

Папка:

```
C:\Users\ACC-2\amocrm-analytics\browser-extension
```

1. `edge://extensions`
2. Включить **Режим разработчика**
3. **Загрузить распакованное расширение** → выбрать папку выше
4. Закрепить иконку **KUH AI**
5. Настройки расширения: URL API = `http://127.0.0.1:8090`

После обновления кода: ↻ **Обновить** у расширения, затем F5 на вкладке amoCRM.

Chrome: то же на `chrome://extensions`.

---

## 3. Пользование

1. https://kuhhospital.amocrm.ru → любая сделка `/leads/detail/...`
2. Кнопка **KUH AI** справа внизу → **Разобрать**
3. Клик по фразе / **Копировать ответ** → в буфер
4. **В заметку сделки** — только по явному клику (не автоматически)

---

## ⚠ Marketplace

Не ставить zip marketplace-виджет, пока доп. соглашение РФ не заполнено.  
Сейчас источник правды — **браузерное расширение**, не интеграции amo.

Быстрый Edge с расширением (опционально):

```powershell
cd C:\Users\ACC-2\amocrm-analytics
python run_extension_now.py
```
