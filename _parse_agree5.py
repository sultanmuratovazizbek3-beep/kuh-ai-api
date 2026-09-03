from pathlib import Path

js = Path("data/9733.896291e28732c5aa.js").read_text(encoding="utf-8")

# find all occurrences of inn with context
idx = 0
while True:
    i = js.find("inn", idx)
    if i < 0:
        break
    print("---", i)
    print(js[max(0, i - 150) : i + 200])
    print()
    idx = i + 3
    if idx > 200000:
        break

# search for id=" patterns that look like form fields in any js
for fname in [
    "data/9733.896291e28732c5aa.js",
    "data/53948.1e5692ed0deb219c.js",
    "data/91240.27dbd07bc74c340a.js",
]:
    t = Path(fname).read_text(encoding="utf-8", errors="ignore")
    if "private_integration_company" in t or 'id=\\"inn\\"' in t or "id=\\\"inn\\\"" in t:
        print("file has company/inn markup", fname)
    # unescape common webpack string patterns for id=
    if "date_of_issue" in t and "passport" in t and "company" in t.lower():
        j = t.find("date_of_issue")
        print(fname, "around date_of_issue:")
        print(t[max(0, j - 300) : j + 300])
