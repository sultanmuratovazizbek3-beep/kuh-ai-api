import re
from pathlib import Path

js = Path("data/9733.896291e28732c5aa.js").read_text(encoding="utf-8")
# extract all string literals that look like form field names
strs = re.findall(r'"([a-z][a-z0-9_]{2,40})"', js)
from collections import Counter

c = Counter(strs)
# print frequent / relevant
keys = [
    k
    for k, n in c.most_common()
    if any(
        x in k
        for x in [
            "inn",
            "ogrn",
            "kpp",
            "name",
            "pass",
            "addr",
            "comp",
            "legal",
            "direct",
            "phone",
            "email",
            "agree",
            "entity",
            "series",
            "number",
            "birth",
            "city",
            "country",
            "tax",
            "reg",
            "fio",
            "first",
            "last",
            "middle",
            "org",
            "form",
            "status",
            "type",
            "snils",
            "bic",
            "bank",
        ]
    )
]
print("relevant strings:")
for k in keys:
    print(f"  {k} x{c[k]}")

# dump larger context around company_form / individual
for token in [
    "company_form",
    "individual_form",
    "legal_entity",
    "individual",
    "entrepreneur",
    "endpoint",
    "validate",
    "serialize",
    "save",
]:
    idx = js.find(token)
    print("\n====", token, "idx", idx)
    if idx >= 0:
        print(js[max(0, idx - 200) : idx + 500])

# Also search twig path mentions
for m in re.finditer(r"[a-z_/]*additional[a-z_/]*\.twig", js):
    print("twig", m.group(0))
for m in re.finditer(r"[a-z_/]*(?:company|individual|entity|passport)[a-z_/]*\.twig", js):
    print("twig2", m.group(0))
