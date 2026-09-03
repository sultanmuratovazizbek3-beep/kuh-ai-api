import re
from pathlib import Path

import browser_cookie3
import requests
from dotenv import load_dotenv

load_dotenv()
s = requests.Session()
for c in browser_cookie3.chromium(
    cookie_file="data/_ycookies/Cookies",
    key_file="data/_ycookies/Local State",
    domain_name="amocrm.ru",
):
    s.cookies.set(c.name, c.value, domain=c.domain, path=c.path)

base = "https://kuhhospital.amocrm.ru"
# try template endpoints
candidates = [
    "/ajax/twig/settings/widgets/oauth_integration/private_integration_company_form",
    "/ajax/get_templates/",
    "/twig/settings/widgets/oauth_integration/private_integration_company_form.twig",
    "/frontend/js/twig/settings/widgets/oauth_integration/private_integration_company_form.twig",
]
# search page for how twig loads
html = Path("data/_widgets_page.html").read_text(encoding="utf-8", errors="ignore")
for m in re.finditer(r".{0,40}twig.{0,80}", html, flags=re.I):
    sstr = m.group(0).replace("\n", " ")
    if "private_integration" in sstr or "tmpl" in sstr:
        print(sstr[:150])

# Search in 9733 for twig loader URL pattern
js = Path("data/9733.896291e28732c5aa.js").read_text(encoding="utf-8")
for m in re.finditer(r".{0,50}tmpl/.{0,80}", js):
    print("TMPL", m.group(0)[:140])

# Try POST/GET common amo template API
for path in candidates:
    r = s.get(base + path, timeout=15)
    print("GET", path, r.status_code, r.text[:80].replace("\n", " "))

# Maybe templates come from statix
for url in [
    "https://statix.amocrm.ru/frontend/tmpl/settings/widgets/oauth_integration/private_integration_company_form.twig",
    "https://statix.amocrm.ru/tmpl/settings/widgets/oauth_integration/private_integration_company_form.twig",
]:
    r = s.get(url, timeout=15)
    print("STATIX", url, r.status_code, len(r.text), r.text[:100].replace("\n", " "))
