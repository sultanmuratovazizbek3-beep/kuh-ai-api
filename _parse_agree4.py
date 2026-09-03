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
for path in [
    "/tmpl/settings/widgets/oauth_integration/private_integration_form_modal.twig",
    "/frontend/build/tmpl/settings/widgets/oauth_integration/private_integration_company_form.twig",
]:
    r = s.get(base + path, timeout=20)
    print(path, r.status_code, len(r.text), r.text[:120].replace("\n", " "))

# Search downloaded JS for twig-compiled field ids
js = Path("data/9733.896291e28732c5aa.js").read_text(encoding="utf-8")
# Also search larger marketplace bundle
big = Path("data/53948.1e5692ed0deb219c.js").read_text(encoding="utf-8")
huge = Path("data/91240.27dbd07bc74c340a.js")
huge_txt = huge.read_text(encoding="utf-8") if huge.exists() else ""

for label, txt in [("9733", js), ("53948", big), ("91240", huge_txt)]:
    for token in [
        "date_of_issue",
        "passport_number",
        "company_name",
        "legal_name",
        "full_name",
        "inn",
        "ogrn",
        "kpp",
        "director",
        "organization",
        "entity_name",
        "phone",
        "email",
    ]:
        if token in txt:
            print(label, "has", token)

# Try POST agreement with plausible legal entity payload
uuid = None
payloads = [
    {
        "entity_type": "legal_entity",
        "fields": {
            "name": "KUH Hospital",
            "inn": "123456789",
            "ogrn": "1234567890123",
            "kpp": "123456789",
            "address": "Tashkent",
            "phone": "+998901234567",
            "email": "support@kuhhospital.uz",
            "director": "ADMIN",
        },
    },
    {
        "entity_type": "individual",
        "fields": {
            "first_name": "Admin",
            "last_name": "KUH",
            "email": "support@kuhhospital.uz",
            "phone": "+998901234567",
            "passport_data": {"passport_series": "AA", "passport_number": "1234567"},
            "date_of_issue": "01.01.2015",
        },
    },
]

h = {
    "X-Requested-With": "XMLHttpRequest",
    "Referer": base + "/settings/widgets/",
    "Origin": base,
    "Content-Type": "application/json",
}
for i, p in enumerate(payloads):
    r = s.post(base + "/ajax/v4/additional_agreements", headers=h, json=p, timeout=30)
    print("POST", i, r.status_code, r.text[:400])

# Also try form-urlencoded
r = s.post(
    base + "/ajax/v4/additional_agreements",
    headers={**h, "Content-Type": "application/x-www-form-urlencoded"},
    data={
        "entity_type": "legal_entity",
        "fields[name]": "KUH Hospital",
        "fields[inn]": "305123456",
        "fields[phone]": "+998901234567",
        "fields[email]": "support@kuhhospital.uz",
    },
    timeout=30,
)
print("FORM", r.status_code, r.text[:400])

# Check status again
r = s.get(base + "/ajax/v4/additional_agreements", headers=h, timeout=30)
print("STATUS", r.text)
