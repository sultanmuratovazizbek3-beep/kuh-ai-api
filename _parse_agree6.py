from pathlib import Path

js = Path("data/53948.1e5692ed0deb219c.js").read_text(encoding="utf-8")
# find getAdditionalAgreementAndOpenWindow usages / callers
token = "getAdditionalAgreementAndOpenWindow"
idx = 0
while True:
    i = js.find(token, idx)
    if i < 0:
        break
    print("====", i)
    print(js[max(0, i - 400) : i + 600])
    print()
    idx = i + len(token)

# Also in 9733
js2 = Path("data/9733.896291e28732c5aa.js").read_text(encoding="utf-8")
idx = 0
while True:
    i = js2.find("additional_agreement", idx)
    if i < 0:
        break
    print("9733====", i)
    print(js2[max(0, i - 200) : i + 400])
    print()
    idx = i + 20
    if idx > 500000:
        break
