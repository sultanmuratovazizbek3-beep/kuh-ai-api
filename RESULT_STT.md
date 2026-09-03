# Улучшения: прослушивание звонков + RU/UZ + авто-отчёты

## 1. Теперь реально слушаем звонки

- Скачиваем записи из `params.link` (onlinePBX HTTPS / itgrix LAN)
- Транскрипция: **faster-whisper** (локально) или xAI STT при `XAI_API_KEY`
- Текст кладётся в `communications.transcript` и идёт в анализ

Проверено: **5/5** записей расшифрованы (RU/UZ речь).

```powershell
python main.py --transcribe 10
```

## 2. Анализ и помощник — двуязычные (🇷🇺 + 🇺🇿)

Все советы, next step, возражения, отчёты — на **русском и узбекском (lotin)**.

Пример примечания в сделке:
- Оценка / Baholash: 8.1/10
- Следующие шаги / Keyingi qadamlar
- Можно ответить / Javob variantlari

Сделки с разбором по **транскрипту**:
- https://kuhhospital.amocrm.ru/leads/detail/31259767 (8.1)
- https://kuhhospital.amocrm.ru/leads/detail/31259729 (8.1)
- https://kuhhospital.amocrm.ru/leads/detail/31259663 (8.1)
- https://kuhhospital.amocrm.ru/leads/detail/31259429 (4.3)
- https://kuhhospital.amocrm.ru/leads/detail/31259299 (5.7)

## 3. Отчёты — не искать, открывать одно место

| Куда | Путь |
|------|------|
| **Всегда свежий HTML** | `Desktop\AmoCRM-AI-Reports\LATEST.html` |
| Markdown | `Desktop\AmoCRM-AI-Reports\LATEST.md` |
| Архив | `Desktop\AmoCRM-AI-Reports\archive\` |
| **Сделка в AmoCRM** | https://kuhhospital.amocrm.ru/leads/detail/31260101 |

Ежедневно в 20:00 (и week/month по расписанию) отчёт:
1. Пишется в Desktop LATEST
2. Добавляется примечанием в сделку «AI Отчёты KUH»

## 4. Качество vs XAI_API_KEY

Сейчас без ключа xAI:
- STT = faster-whisper (работает)
- Разбор = heuristic-v2 bilingual (лучше старого, но слабее Grok)

Для «умного» разбора по смыслу реплик добавьте в `.env`:
```
XAI_API_KEY=xai-...
```
и перезапустите API/collector.

## 5. Команды

```powershell
cd C:\Users\ACC-2\amocrm-analytics
python main.py --transcribe 15   # послушать ещё звонки
python main.py --once            # collect + STT + analyze
python main.py --report day      # отчёт → Desktop + Amo
python main.py                   # постоянно
```
