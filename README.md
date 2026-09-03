# AmoCRM Analytics + AI Помощник в карточке

Система для **KUH / amoCRM**:

1. **Сбор и отчёты** — звонки, события, лиды, day/week/month по менеджерам  
2. **Виджет в AmoCRM** — правая колонка в сделке: анализ + подсказки менеджеру  
3. **API** — backend для виджета  

**Не трогаем** Telegram/WhatsApp-интеграции и тексты мессенджеров (по запросу).

---

## Быстрый старт

```powershell
cd C:\Users\ACC-2\amocrm-analytics
.\start_all.bat
```

| Что | URL / путь |
|-----|------------|
| Health | http://127.0.0.1:8090/health |
| API lead | http://127.0.0.1:8090/api/v1/assistant/lead/{id} |
| Zip виджета | `public\kuh-assistant-widget.zip` |
| Установка виджета | **[WIDGET_INSTALL.md](WIDGET_INSTALL.md)** |

---

## Виджет в AmoCRM (главное для менеджеров)

В **правой колонке карточки сделки**:

- Оценка диалога /10  
- Суть ситуации  
- **Что сделать сейчас**  
- **Готовые ответы** (клик → копировать)  
- Вопросы клиенту, возражения, риски  
- «В примечание» — сохранить разбор в сделку  
- Автообновление раз в ~90 сек  

Инструкция загрузки zip: **WIDGET_INSTALL.md**  
Нужен HTTPS-туннель (`cloudflared tunnel --url http://127.0.0.1:8090`) на backend.

---

## Отчёты по менеджерам

```powershell
python main.py --once
python main.py --report day
python main.py --report week
python main.py --report month
python main.py --no-send   # постоянный poll + расписание (без Telegram)
```

Файлы: `reports\*.md`

---

## Структура

```
amocrm-analytics/
  api_server.py          # FastAPI + webhook
  assistant_service.py   # AI-коуч для карточки
  main.py                # collector + scheduler отчётов
  collector.py / analyzer.py / report_generator.py
  widget/                # исходники виджета amoCRM
  public/*.zip           # готовый zip для загрузки
  data/analytics.db
  reports/
```

---

## .env

Токены amoCRM — только из **своей** интеграции Desk (не Med24). См. `SETUP.md`. Полезное:

```env
XAI_API_KEY=          # AI (console.x.ai) — иначе эвристики
XAI_MODEL=grok-4.5
WON_STATUS_IDS=142
LOST_STATUS_IDS=143
TIMEZONE=Asia/Tashkent
```

---

## Автозапуск Windows

```powershell
powershell -ExecutionPolicy Bypass -File .\install_autostart.ps1
```

---

## Ограничения

- Полные тексты **чатов мессенджеров** через Events API часто недоступны (только message_id).  
- Виджет берёт **примечания сделки** (звонки, common notes) — это основной материал для подсказок.  
- Для «умного» AI нужен `XAI_API_KEY`.  
