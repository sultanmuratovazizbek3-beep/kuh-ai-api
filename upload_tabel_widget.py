"""Upload public/widget.zip to private Табель integrations and set api_base."""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from pathlib import Path

from wait_and_upload_widget import _headers, client_info, session

ROOT = Path(__file__).resolve().parent
ZIP_SRC = ROOT / "public" / "widget.zip"
BASE = "https://kuhhospital.amocrm.ru"
OUT = ROOT / "data" / "tabel_upload_now.json"

TARGETS = [
    {
        "uuid": "56801ecd-4368-49ea-9dfa-9414b1ffe8af",
        "code": "hmnza15vi7ye7fwrwls1rrpps4ijyqr82t2xhpa",
        "label": "hmnza",
    },
    {
        "uuid": "777f986d-4b88-4d62-b0d2-ddd3c64ad299",
        "code": "kxt5r1ijpypie3mtamgswocx2kahqljunapz0wg",
        "label": "kxt",
    },
]


def api_base() -> str:
    p = ROOT / "public" / "API_PUBLIC_URL.txt"
    if p.exists():
        u = p.read_text(encoding="utf-8").strip().lstrip("\ufeff")
        if u.startswith("http"):
            return u.rstrip("/")
    return "http://127.0.0.1:8090"


def upload_widget(s, uuid: str):
    td = Path(tempfile.mkdtemp())
    wzip = td / "widget.zip"
    shutil.copy(ZIP_SRC, wzip)
    url = f"{BASE}/ajax/widgets/{uuid}/widget/upload/?fileapi{int(time.time() * 1000)}"
    with open(wzip, "rb") as f:
        return s.post(
            url,
            headers=_headers(),
            files={"widget": ("widget.zip", f, "application/x-zip-compressed")},
            data={"_widget": "widget.zip"},
            timeout=120,
        )


def try_install(s, code: str, settings: dict) -> dict:
    r = s.post(
        f"{BASE}/api/v4/widgets/{code}",
        headers={**_headers(), "Content-Type": "application/json"},
        json=settings,
        timeout=30,
    )
    out = {"http": r.status_code, "body": r.text[:500]}
    try:
        out["json"] = r.json()
    except Exception:
        pass
    return out


def main() -> None:
    if not ZIP_SRC.exists():
        raise SystemExit(f"no zip {ZIP_SRC}")
    tunnel = api_base()
    print("zip", ZIP_SRC, ZIP_SRC.stat().st_size, flush=True)
    print("api_base", tunnel, flush=True)
    s, src = session()
    print("session", src, flush=True)
    report = {"api_base": tunnel, "session": src, "uploads": {}, "installs": {}}
    for t in TARGETS:
        allowed = ""
        token = ""
        listed = ""
        try:
            info = client_info(s, t["uuid"])
            settings_now = (info.get("settings") or info.get("widget_settings") or {}) if isinstance(info, dict) else {}
            if isinstance(settings_now, dict):
                allowed = str(settings_now.get("allowed_users") or "")
                token = str(settings_now.get("api_token") or "")
                listed = str(settings_now.get("list_users") or "")
        except Exception:
            pass
        settings = {"api_base": tunnel}
        if token:
            settings["api_token"] = token
        if allowed:
            settings["allowed_users"] = allowed
        if listed:
            settings["list_users"] = listed
        up = upload_widget(s, t["uuid"])
        client = client_info(s, t["uuid"])
        inst = try_install(s, t["code"], settings)
        rec = {
            "upload_http": up.status_code,
            "upload_body": up.text[:300],
            "has_widget": client.get("has_widget"),
            "name": client.get("name"),
            "install_http": inst.get("http"),
            "install_body": inst.get("body"),
        }
        report["uploads"][t["label"]] = rec
        print(t["label"], rec, flush=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", OUT, flush=True)


if __name__ == "__main__":
    main()
