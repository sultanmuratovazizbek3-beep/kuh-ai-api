import re
from pathlib import Path

import browser_cookie3
import requests
from dotenv import load_dotenv

load_dotenv()
cookie_file = Path("data/_ycookies/Cookies")
key_file = Path("data/_ycookies/Local State")
s = requests.Session()
for c in browser_cookie3.chromium(
    cookie_file=str(cookie_file), key_file=str(key_file), domain_name="amocrm.ru"
):
    s.cookies.set(c.name, c.value, domain=c.domain, path=c.path)

base = "https://kuhhospital.amocrm.ru"
html = Path("data/_widgets_page.html").read_text(encoding="utf-8")
srcs = re.findall(r'src="(/frontend/[^"]+\.js[^"]*)"', html)
srcs += re.findall(r'src="(https://[^"]+/frontend/[^"]+\.js[^"]*)"', html)
print("js count", len(srcs))

found = []
for src in srcs:
    url = src if src.startswith("http") else base + src
    try:
        txt = s.get(url, timeout=30).text
    except Exception as e:
        print("fail", url, e)
        continue
    if "additional_agreement" in txt or "is_additional_agreement_performed" in txt:
        print("HIT", url, "len", len(txt))
        Path("data/_agree_js.js").write_text(txt, encoding="utf-8")
        found.append(url)
        for m in re.finditer(r".{0,120}additional_agreement.{0,250}", txt):
            print(" --", m.group(0).replace("\n", " ")[:350])
            print("---")

# also search in inline scripts and linked css? skip
# try common market bundle names
extra = [
    "/frontend/build/marketplace.js",
    "/frontend/js/marketplace/app.js",
    "/frontend/js/settings/widgets.js",
]
for path in extra:
    url = base + path
    r = s.get(url, timeout=20)
    print("probe", path, r.status_code, len(r.text))
    if r.status_code == 200 and "additional_agreement" in r.text:
        print("EXTRA HIT", path)
        Path("data/_agree_js.js").write_text(r.text, encoding="utf-8")

print("found files", found)
