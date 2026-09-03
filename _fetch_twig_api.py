import json
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
h = {"X-Requested-With": "XMLHttpRequest", "Referer": base + "/amo-market/"}

# Common amo twig batch endpoints
paths = [
    "/tmpl/settings/widgets/oauth_integration/private_integration_company_form.twig",
    "/tmpl/settings/widgets/oauth_integration/private_integration_person_form.twig",
    "/tmpl/settings/widgets/oauth_integration/private_integration_form_modal.twig",
    "/tmpl/settings/widgets/oauth_integration/private_integration_alert_modal.twig",
]

attempts = [
    ("GET", "/ajax/twigs/", {"paths[]": paths[0]}),
    ("POST", "/ajax/twigs/", {"paths": paths}),
    ("GET", "/ajax/v2/twigs/", {"path": paths[0]}),
    ("POST", "/ajax/v1/system/twigs", {"paths": paths}),
    ("GET", "/ajax/system/twigs", {"path": paths[0]}),
]

# Discover from page scripts references to twigs ajax
html = Path("data/_widgets_page.html").read_text(encoding="utf-8", errors="ignore")
for m in re.finditer(r".{0,30}twig.{0,60}", html, flags=re.I):
    t = m.group(0)
    if "ajax" in t.lower():
        print("HTML", t)

js = Path("data/53948.1e5692ed0deb219c.js").read_text(encoding="utf-8")
for m in re.finditer(r".{0,40}/ajax/[^\"']*twig[^\"']*.{0,40}", js, flags=re.I):
    print("JS", m.group(0))

# Try loading via twig endpoint used by old amo
for method, url, data in attempts:
    try:
        if method == "GET":
            r = s.get(base + url, params=data, headers=h, timeout=20)
        else:
            r = s.post(base + url, json=data, headers={**h, "Content-Type": "application/json"}, timeout=20)
        print(method, url, r.status_code, r.text[:120].replace("\n", " "))
    except Exception as e:
        print(method, url, "ERR", e)

# Try opening alert modal content by evaluating? skip
# Probe POST agreement with nested structure from model.toJSON typical amo forms
# Many RU company forms use:
candidates = [
    {
        "entity_type": "legal_entity",
        "fields": {
            "name": "KUH Hospital",
            "full_name": "KUH Hospital",
            "inn": "7707083893",
            "ogrn": "1027700132195",
            "kpp": "773601001",
            "address": "Tashkent",
            "phone": "998901234567",
            "email": "support@kuhhospital.uz",
            "ceo": "Admin",
            "general_director": "Admin",
        },
    },
    {
        "entity_type": "legal_entity",
        "fields": {
            "company_name": "KUH Hospital",
            "tax_number": "305123456",
            "registration_number": "123",
            "address": "Tashkent",
            "phone": "+998901234567",
            "email": "support@kuhhospital.uz",
            "representative_name": "Admin KUH",
        },
    },
    {
        "entity_type": "individual",
        "fields": {
            "first_name": "Admin",
            "last_name": "KUH",
            "middle_name": "A",
            "email": "support@kuhhospital.uz",
            "phone": "+998901234567",
            "date_of_issue": "01.01.2018",
            "passport_data": {"passport_series": "AA", "passport_number": "1234567"},
            "issuer": "IIB",
            "birth_date": "01.01.1990",
            "address": "Tashkent",
        },
    },
]

for i, payload in enumerate(candidates):
    r = s.post(
        base + "/ajax/v4/additional_agreements",
        headers={**h, "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    print("CAND", i, r.status_code, r.text[:300])

print("STATUS", s.get(base + "/ajax/v4/additional_agreements", headers=h, timeout=20).text)
