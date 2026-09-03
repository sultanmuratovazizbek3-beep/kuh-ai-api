# -*- coding: utf-8 -*-
"""Make Desk UI plain Russian — fix mojibake + remove English chrome."""
from pathlib import Path
import re

html_path = Path(r"C:\Users\ACC-2\amocrm-analytics\desktop\index.html")
js_path = Path(r"C:\Users\ACC-2\amocrm-analytics\desktop\app.js")

html = html_path.read_text(encoding="utf-8", errors="replace")

# --- Fix / replace shell ---
repls = [
    ("<title>CRM AI Desk</title>", "<title>Аналитика звонков</title>"),
    (
        """          <div class="brand-title">AIVEX</div>
          <div class="brand-sub">AI CRM Â· KUH Desk</div>""",
        """          <div class="brand-title">Аналитика</div>
          <div class="brand-sub">Клиника · звонки и сделки</div>""",
    ),
    (
        """          <div class="brand-title">AIVEX</div>
          <div class="brand-sub">AI CRM · KUH Desk</div>""",
        """          <div class="brand-title">Аналитика</div>
          <div class="brand-sub">Клиника · звонки и сделки</div>""",
    ),
]

for a, b in repls:
    if a in html:
        html = html.replace(a, b)

# Nav block — replace whole nav
nav_pat = re.compile(
    r'<nav class="nav" id="side-nav">.*?</nav>',
    re.S,
)
nav_new = """<nav class="nav" id="side-nav">
        <div class="nav-group">Меню</div>
        <button class="nav-item active" data-view="dashboard">
          <span class="ico">1</span><span class="nav-label">Главная</span>
        </button>
        <button class="nav-item" data-view="assistant">
          <span class="ico">2</span><span class="nav-label">Разбор звонка</span>
        </button>
        <button class="nav-item" data-view="crm">
          <span class="ico">3</span><span class="nav-label">Подключение amo</span>
        </button>
        <button class="nav-item" data-view="settings">
          <span class="ico">4</span><span class="nav-label">Настройки</span>
        </button>
      </nav>"""
html, n = nav_pat.subn(nav_new, html, count=1)
print("nav replaced", n)

# Footer
html = re.sub(
    r'<div class="how-mini">.*?</div>\s*<div class="status-active[^"]*" id="api-status">.*?</div>',
    """<div class="how-mini">
          <b>Авторабота</b>
          <span id="worker-status-text">сбор → расшифровка → анализ → заметка</span>
        </div>
        <div class="status-active pending" id="api-status">
          <span class="dot-ok"></span>
          <span id="api-status-text">Подключение…</span>
        </div>""",
    html,
    count=1,
    flags=re.S,
)

# Toolbar title defaults
html = re.sub(
    r'<div class="crumb" id="view-crumb">.*?</div>\s*<h1 id="view-title">.*?</h1>\s*<p class="muted small" id="view-sub">.*?</p>',
    """<div class="crumb" id="view-crumb">Меню</div>
          <h1 id="view-title">Главная</h1>
          <p class="muted small" id="view-sub">Цифры за период и статус автоработы</p>""",
    html,
    count=1,
    flags=re.S,
)

# Top actions — search, collect, refresh
html = html.replace(
    """          <button type="button" class="ax-search" id="btn-cmdk" title="Command Palette">
            <span>ĞŸĞ¾Ğ¸ÑĞºâ€¦</span>
            <kbd>Ctrl K</kbd>
          </button>""",
    """          <button type="button" class="ax-search" id="btn-cmdk" title="Быстрый поиск">
            <span>Найти раздел…</span>
            <kbd>Ctrl+K</kbd>
          </button>""",
)

# More generic cmdk button replace
html = re.sub(
    r'<button type="button" class="ax-search" id="btn-cmdk"[^>]*>.*?</button>',
    """<button type="button" class="ax-search" id="btn-cmdk" title="Быстрый поиск">
            <span>Найти раздел…</span>
            <kbd>Ctrl+K</kbd>
          </button>""",
    html,
    count=1,
    flags=re.S,
)

html = re.sub(
    r'<button class="btn ghost sm" id="btn-refresh"[^>]*>.*?</button>',
    '<button class="btn ghost sm" id="btn-refresh" title="Обновить экран">Обновить</button>',
    html,
    count=1,
    flags=re.S,
)
html = re.sub(
    r'<button class="btn primary sm" id="btn-collect"[^>]*>.*?</button>',
    '<button class="btn primary sm" id="btn-collect" title="Скачать новые звонки из amoCRM">Забрать звонки</button>',
    html,
    count=1,
    flags=re.S,
)

# Period chips
chips = """      <div class="period-chips" id="period-chips" hidden>
        <button type="button" class="period-chip" data-days="1">Сегодня</button>
        <button type="button" class="period-chip" data-days="2">Вчера</button>
        <button type="button" class="period-chip active" data-days="7">Неделя</button>
        <button type="button" class="period-chip" data-days="30">Месяц</button>
        <button type="button" class="period-chip" data-days="90">Квартал</button>
        <button type="button" class="period-chip" data-days="365">Год</button>
      </div>"""
html = re.sub(
    r'<div class="period-chips" id="period-chips"[^>]*>.*?</div>',
    chips,
    html,
    count=1,
    flags=re.S,
)

# Pipeline status block
html = re.sub(
    r'<div class="card pipeline-status" id="pipeline-status">.*?</div>\s*</div>\s*</div>',
    """<div class="card pipeline-status" id="pipeline-status">
          <div class="ps-left">
            <span class="ps-dot" id="ps-dot"></span>
            <div>
              <b id="ps-title">Проверка системы…</b>
              <div class="muted small" id="ps-sub">Сервер · авторабота · последний цикл</div>
            </div>
          </div>
          <div class="ps-actions">
            <button type="button" class="btn primary sm" id="btn-dash-collect">Забрать звонки</button>
            <button type="button" class="btn ghost sm" data-goto="assistant">Открыть разбор</button>
          </div>
        </div>""",
    html,
    count=1,
    flags=re.S,
)

# KPI labels / hints — replace English/semantic junk
kpi_fixes = [
    (r'id="k-calls-label">[^<]*<', 'id="k-calls-label">Звонки<'),
    (r'id="k-period-hint">[^<]*<', 'id="k-period-hint">из amoCRM за период<'),
    (r'id="k-won-ico"[^>]*>[^<]*</div>\s*<div class="kpi-label">[^<]*<', 
     'id="k-won-ico">0</div>\n              <div class="kpi-label">Успешные сделки<'),
    (r'id="k-conv-hint">[^<]*<', 'id="k-conv-hint">успех и конверсия<'),
    (r'id="k-quality-ico"[^>]*>[^<]*</div>\s*<div class="kpi-label">[^<]*<',
     'id="k-quality-ico">★</div>\n              <div class="kpi-label">Качество звонков<'),
    (r'id="k-quality-hint">[^<]*<', 'id="k-quality-hint">средняя оценка из 10<'),
    (r'id="k-chats-label">[^<]*<', 'id="k-chats-label">Чаты<'),
    (r'id="k-chats-ico"[^>]*>[\s\S]*?<div class="kpi-hint">[^<]*<',
     None),  # handle below
]
# Simpler string replacements for kpi hints that are clearly english
for eng, rus in [
    ("коммуникации · teal/blue", "из amoCRM за период"),
    ("money · orange", "успех и конверсия"),
    ("purple · /10", "средняя оценка из 10"),
    ("teal · communication", "переписки за период"),
    ("growth · green", "активные сделки"),
    ("red · без расшифровки", "есть запись, текста ещё нет"),
    (">AI · качество<", ">Качество звонков<"),
    (">Выручка / успех<", ">Успешные сделки<"),
    (">Чаты / лиды<", ">Чаты<"),
    (">Риски · ждут STT<", ">Ждут расшифровку<"),
    (">Сделок в работе<", ">Сделок в работе<"),
]:
    html = html.replace(eng, rus)

# Insights tags
html = html.replace(">AI insight<", ">Подсказка<")
html = html.replace(">Next action<", ">Что сделать<")
html = re.sub(
    r'id="ax-ins-1-t">[^<]*<',
    'id="ax-ins-1-t">Загрузка подсказок…<',
    html,
    count=1,
)
html = re.sub(
    r'id="ax-ins-1-p">[^<]*<',
    'id="ax-ins-1-p">После сбора звонков здесь появятся выводы.<',
    html,
    count=1,
)
html = re.sub(
    r'id="ax-ins-1-m">[^<]*<',
    'id="ax-ins-1-m">из ваших данных<',
    html,
    count=1,
)
html = re.sub(
    r'id="ax-ins-2-t">[^<]*<',
    'id="ax-ins-2-t">Качество звонков<',
    html,
    count=1,
)
html = re.sub(
    r'id="ax-ins-2-p">[^<]*<',
    'id="ax-ins-2-p">Сильные и слабые менеджеры появятся после расшифровки.<',
    html,
    count=1,
)
html = re.sub(
    r'id="ax-ins-2-m">[^<]*<',
    'id="ax-ins-2-m">влияет на запись клиентов<',
    html,
    count=1,
)
html = re.sub(
    r'id="ax-ins-3-t">[^<]*<',
    'id="ax-ins-3-t">Следующий шаг<',
    html,
    count=1,
)
html = re.sub(
    r'id="ax-ins-3-p">[^<]*<',
    'id="ax-ins-3-p">Откройте разбор звонка или заберите новые данные.<',
    html,
    count=1,
)
html = re.sub(
    r'id="ax-ins-3-m">[^<]*<',
    'id="ax-ins-3-m">один клик<',
    html,
    count=1,
)

# Theme titles
html = re.sub(
    r'title="[^"]*"(\s+id="theme-switch")',
    'title="Тема оформления"\\1',
    html,
)
html = html.replace('title="Command Palette"', 'title="Быстрый поиск"')
html = html.replace('aria-label="Светлая"', 'aria-label="Светлая тема"')
html = html.replace('aria-label="Тёмная"', 'aria-label="Тёмная тема"')

# Cache bust
html = re.sub(r"\?v=20260824simple\d+", "?v=20260824ru1", html)
html = re.sub(r"app\.js\?v=[^\"]+", 'app.js?v=20260824ru1', html)

html_path.write_text(html, encoding="utf-8")
print("HTML updated")

# --- JS titles / status / CMDK ---
js = js_path.read_text(encoding="utf-8")

js_repls = [
    (
        """    dashboard: [
      "Dashboard",
      "KPI · AI-инсайты · активность команды",
      "Работа",
    ],
    assistant: [
      "Сделки / разбор",
      "Оценка звонка + next best action",
      "Работа",
    ],""",
        """    dashboard: [
      "Главная",
      "Цифры за период и статус автоработы",
      "Меню",
    ],
    assistant: [
      "Разбор звонка",
      "Текст, оценка и что сказать клиенту",
      "Меню",
    ],""",
    ),
    (
        """    crm: [
      "CRM / интеграции",
      "amoCRM — источник сделок и звонков",
      "Система",
    ],
    settings: ["Настройки", "Тема, язык и API", "Система"],""",
        """    crm: [
      "Подключение amo",
      "Адрес аккаунта и токен доступа",
      "Меню",
    ],
    settings: ["Настройки", "Тема и язык подсказок", "Меню"],""",
    ),
    (
        """  const CMDK_ITEMS = [
    { label: "Dashboard", view: "dashboard", hint: "KPI" },
    { label: "Разбор звонка", view: "assistant", hint: "AI" },
    { label: "CRM", view: "crm", hint: "amo" },
    { label: "Настройки", view: "settings", hint: "тема" },
    {
      label: "Забрать данные из CRM",
      action: () => runCollect(),
      hint: "sync",
    },
  ];""",
        """  const CMDK_ITEMS = [
    { label: "Главная", view: "dashboard", hint: "цифры" },
    { label: "Разбор звонка", view: "assistant", hint: "анализ" },
    { label: "Подключение amo", view: "crm", hint: "токен" },
    { label: "Настройки", view: "settings", hint: "тема" },
    {
      label: "Забрать звонки из amo",
      action: () => runCollect(),
      hint: "обновить",
    },
  ];""",
    ),
    ('sub.textContent = "автопилот: сбор → STT → анализ → заметка";',
     'sub.textContent = "сейчас: сбор → расшифровка → анализ → заметка в amo";'),
    ('title.textContent = "Активно · автопилот";',
     'title.textContent = "Всё работает";'),
    ('title.textContent = "Нужна настройка CRM";',
     'title.textContent = "Нужно подключить amoCRM";'),
    ('title.textContent = "Воркер не запущен";',
     'title.textContent = "Авторабота не запущена";'),
    ('sub.textContent = "Перезапустите CRM AI Desk (ярлык / Launch)";',
     'sub.textContent = "Закройте и откройте программу ярлыком «CRM AI Desk»";'),
    ('stt: "Расшифровка звонков…",',
     'stt: "Расшифровка звонков…",'),
    ('collect: "Сбор из CRM…",',
     'collect: "Забираем звонки из amo…",'),
    ('notes: "Запись заметок в amo…",',
     'notes: "Пишем заметки в сделки…",'),
    ('analyze: "Анализ качества…",',
     'analyze: "Оцениваем разговоры…",'),
    ('? "Активно"',
     '? "На связи"'),
    ('ws.textContent = "Воркер не запущен — перезапустите CRM AI Desk";',
     'ws.textContent = "Авторабота не запущена — откройте программу заново";'),
    ('ws.textContent =\n            "Авто: сбор → STT → анализ → заметка · " +',
     'ws.textContent =\n            "Авторабота · " +'),
    ('toast("Сервер не отвечает — перезапустите CRM AI Desk");',
     'toast("Сервер не отвечает — закройте и откройте программу");'),
    ('toast("Забираем данные из CRM…");',
     'toast("Забираем звонки из amo…");'),
    ('toast("Готово · данные из CRM обновлены");',
     'toast("Готово · звонки обновлены");'),
    ('vs.textContent = `CRM: ${lr.provider}${',
     'vs.textContent = `Подключено: ${lr.provider}${'),
    ('"Нет сделок. Нажмите «Забрать из CRM»."',
     '"Нет сделок. Нажмите «Забрать звонки»."'),
    ("'Нет сделок. Нажмите «Забрать из CRM».'",
     "'Нет сделок. Нажмите «Забрать звонки».'"),
]

for a, b in js_repls:
    if a in js:
        js = js.replace(a, b)
        print("js ok:", a[:40].replace("\n", " "))
    else:
        print("js MISS:", a[:50].replace("\n", " "))

# Fix remaining English toast bits
js = js.replace('toast("Stats: "', 'toast("Ошибка цифр: "')
js = js.replace('toast("Leads: "', 'toast("Ошибка списка сделок: "')
js = js.replace(
    'body.innerHTML =\n      \'<tr><td colspan="4" class="muted">Нет сделок. Нажмите «Забрать из CRM».</td></tr>\';',
    'body.innerHTML =\n      \'<tr><td colspan="4" class="muted">Нет сделок. Нажмите «Забрать звонки».</td></tr>\';',
)

js_path.write_text(js, encoding="utf-8")
print("JS updated")

# verify
h2 = html_path.read_text(encoding="utf-8")
for s in ["Главная", "Разбор звонка", "Подключение amo", "Настройки", "Dashboard", "AIVEX"]:
    print(repr(s), "=>", s in h2)
