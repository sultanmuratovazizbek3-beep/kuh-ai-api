import re
from pathlib import Path

js = Path("data/9733.896291e28732c5aa.js").read_text(encoding="utf-8")

# Find all name="..." patterns escaped in strings
for pat in [
    r'name=\\"([a-zA-Z0-9_]+)\\"',
    r"name='([a-zA-Z0-9_]+)'",
    r'name=\"([a-zA-Z0-9_]+)\"',
    r"\[name=\\\"([a-zA-Z0-9_]+)\\\"\]",
    r"\[name=\"([a-zA-Z0-9_]+)\"\]",
]:
    found = sorted(set(re.findall(pat, js)))
    if found:
        print(pat, found)

# Print a large slice of the PrivateIntegrationAgreement class area
idx = js.find("private_integration_company_form")
print("\nBIG SLICE:\n")
print(js[idx : idx + 8000])
