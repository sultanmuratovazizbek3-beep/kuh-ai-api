from pathlib import Path

p = Path("api_server.py")
lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
out = []
for line in lines:
    if 'RedirectResponse(url="/app/"' in line and line.count("(") > line.count(")"):
        line = '        return RedirectResponse(url="/app/")\n'
    out.append(line)
p.write_text("".join(out), encoding="utf-8")
print("fixed")
for i, line in enumerate(out, 1):
    if "RedirectResponse" in line:
        print(i, line.rstrip())
