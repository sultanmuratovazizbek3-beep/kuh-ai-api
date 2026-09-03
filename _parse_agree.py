import re
from pathlib import Path

# Prefer the modal JS that has endpoint
candidates = list(Path("data").glob("*agree*")) + [
    Path("data/_agree_js.js"),
]
# re-download both hits if needed
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

urls = [
    "https://statix.amocrm.ru/frontend/build/9733.896291e28732c5aa.js",
    "https://statix.amocrm.ru/frontend/build/53948.1e5692ed0deb219c.js",
]
for url in urls:
    txt = s.get(url, timeout=30).text
    name = "data/" + url.split("/")[-1]
    Path(name).write_text(txt, encoding="utf-8")
    print("saved", name, len(txt))
    # field-like tokens near form
    fields = sorted(
        set(
            re.findall(
                r"(?:name|key|field|param)[^a-zA-Z0-9]{1,6}([a-z_]{3,40})",
                txt,
            )
        )
    )
    interesting = [
        f
        for f in fields
        if any(
            x in f
            for x in [
                "inn",
                "ogrn",
                "name",
                "pass",
                "address",
                "company",
                "entity",
                "agree",
                "phone",
                "email",
                "director",
                "kpp",
                "series",
                "number",
                "birth",
                "snils",
            ]
        )
    ]
    print("interesting", interesting[:60])
    for m in re.finditer(r".{0,60}ajax/v4/additional_agreements.{0,200}", txt):
        print("EP", m.group(0).replace("\n", " ")[:350])
    for m in re.finditer(r".{0,40}(inn|ogrn|kpp|company_name|legal_name|director).{0,80}", txt, re.I):
        print("F", m.group(0).replace("\n", " ")[:200])
