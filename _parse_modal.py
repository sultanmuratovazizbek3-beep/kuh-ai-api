import re
from pathlib import Path

html = Path("data/wf_modal.html").read_text(encoding="utf-8")
print("len", len(html))
for pat in [
    "input-upload-archive",
    "button-upload-archive",
    "keygen",
    "Основные",
    "Виджет",
    "Архив",
    "archive",
    "widget_code",
]:
    print(pat, html.lower().count(pat.lower()))

texts = re.findall(r">([^<>{]{2,80})<", html)
for t in texts:
    t = t.strip()
    if not t or t.startswith("&"):
        continue
    low = t.lower()
    if any(
        x in low
        for x in [
            "загруз",
            "архив",
            "виджет",
            "основ",
            "доступ",
            "ключ",
            "интегр",
            "сохран",
            "созда",
            "опис",
            "назван",
        ]
    ):
        print("TXT", t)

print("IDS", re.findall(r'id="([^"]+)"', html))
# print left menu items
for m in re.finditer(r"widget-settings__[^\"']+|nav__[^\"']+|menu__[^\"']+", html):
    pass
# dump a readable chunk around 'Доступ' / tabs
for token in ["Доступ", "Ключ", "Основ", "Загрузить архив", "Upload"]:
    i = html.find(token)
    print("token", token, i)
    if i >= 0:
        print(html[max(0, i - 200) : i + 300])
        print("---")
