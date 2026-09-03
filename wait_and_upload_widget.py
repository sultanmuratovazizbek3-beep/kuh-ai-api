"""Poll additional_agreements until filled, then upload widget.zip and configure.

Usage:
  python wait_and_upload_widget.py           # wait up to 45 min
  python wait_and_upload_widget.py --once    # single check + upload if ready
  python wait_and_upload_widget.py --status  # print agreement status only
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

import browser_cookie3
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
ZIP_SRC = ROOT / "public" / "kuh-assistant-widget.zip"
COOKIE_DIR = ROOT / "data" / "_ycookies"
PUBLIC_URL_FILE = ROOT / "public" / "API_PUBLIC_URL.txt"
OUT = ROOT / "data" / "wait_upload_result.json"
AGREE_CACHE = ROOT / "data" / "_additional_agreements.json"
INTEGRATION_UUID = "4b1a3bfc-df9e-4e52-a6ac-c40dab529b31"
BASE = "https://kuhhospital.amocrm.ru"
OK_STATUSES = ("performed", "accepted")


def api_base() -> str:
    if PUBLIC_URL_FILE.exists():
        u = PUBLIC_URL_FILE.read_text(encoding="utf-8").strip().lstrip("\ufeff")
        if u.startswith("http"):
            return u.rstrip("/")
    return "http://127.0.0.1:8090"


def _cookie_candidates() -> list[tuple[str, Path, Path]]:
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    return [
        (
            "yandex_live",
            local / "Yandex" / "YandexBrowser" / "User Data" / "Default" / "Network" / "Cookies",
            local / "Yandex" / "YandexBrowser" / "User Data" / "Local State",
        ),
        (
            "edge_live",
            local / "Microsoft" / "Edge" / "User Data" / "Default" / "Network" / "Cookies",
            local / "Microsoft" / "Edge" / "User Data" / "Local State",
        ),
        (
            "chrome_live",
            local / "Google" / "Chrome" / "User Data" / "Default" / "Network" / "Cookies",
            local / "Google" / "Chrome" / "User Data" / "Local State",
        ),
        (
            "ycookies_saved",
            COOKIE_DIR / "Cookies",
            COOKIE_DIR / "Local State",
        ),
        (
            "yandex_cdp",
            ROOT / "data" / "yandex_cdp" / "Default" / "Network" / "Cookies",
            ROOT / "data" / "yandex_cdp" / "Local State",
        ),
        (
            "edge_ext",
            ROOT / "data" / "edge_ext_profile" / "Default" / "Network" / "Cookies",
            ROOT / "data" / "edge_ext_profile" / "Local State",
        ),
    ]


def _copy_cookie_pair(cookie_file: Path, key_file: Path, dest_dir: Path) -> tuple[Path, Path]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    c_dst = dest_dir / "Cookies"
    k_dst = dest_dir / "Local State"
    # Prefer plain copy; fall back to win32 shared read when DB is locked.
    try:
        shutil.copy2(cookie_file, c_dst)
    except Exception:
        import win32con
        import win32file

        handle = win32file.CreateFile(
            str(cookie_file),
            win32con.GENERIC_READ,
            win32con.FILE_SHARE_READ
            | win32con.FILE_SHARE_WRITE
            | win32con.FILE_SHARE_DELETE,
            None,
            win32con.OPEN_EXISTING,
            win32con.FILE_ATTRIBUTE_NORMAL,
            None,
        )
        try:
            chunks: list[bytes] = []
            while True:
                _, chunk = win32file.ReadFile(handle, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            c_dst.write_bytes(b"".join(chunks))
        finally:
            handle.Close()
    shutil.copy2(key_file, k_dst)
    return c_dst, k_dst


def _refresh_saved_cookies(cookie_file: Path, key_file: Path) -> None:
    COOKIE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(cookie_file, COOKIE_DIR / "Cookies")
        shutil.copy2(key_file, COOKIE_DIR / "Local State")
    except Exception:
        pass


def session(refresh_saved: bool = True) -> tuple[requests.Session, str]:
    """Build amoCRM session from the first working cookie source."""
    last_err: Exception | None = None
    td_root = ROOT / "data" / "_cookie_tmp"
    td_root.mkdir(parents=True, exist_ok=True)

    for name, cookie_file, key_file in _cookie_candidates():
        if not cookie_file.exists() or not key_file.exists():
            continue
        try:
            work = td_root / name
            if work.exists():
                shutil.rmtree(work, ignore_errors=True)
            c_dst, k_dst = _copy_cookie_pair(cookie_file, key_file, work)
            raw = list(
                browser_cookie3.chromium(
                    cookie_file=str(c_dst),
                    key_file=str(k_dst),
                    domain_name="amocrm.ru",
                )
            )
            if not raw:
                continue
            s = requests.Session()
            for c in raw:
                s.cookies.set(c.name, c.value, domain=c.domain, path=c.path)
            # Probe auth quickly
            r = s.get(
                BASE + "/ajax/v4/additional_agreements",
                headers=_headers(),
                timeout=20,
            )
            if r.status_code == 401:
                last_err = RuntimeError(f"{name}: 401 Unauthorized")
                continue
            if refresh_saved and name != "ycookies_saved":
                _refresh_saved_cookies(c_dst, k_dst)
            return s, name
        except Exception as e:
            last_err = e
            continue

    # session.json fallback (often stale)
    sj = COOKIE_DIR / "session.json"
    if sj.exists():
        try:
            data = json.loads(sj.read_text(encoding="utf-8"))
            s = requests.Session()
            for k, v in data.items():
                s.cookies.set(k, str(v), domain=".amocrm.ru", path="/")
                s.cookies.set(k, str(v), domain="kuhhospital.amocrm.ru", path="/")
            r = s.get(
                BASE + "/ajax/v4/additional_agreements",
                headers=_headers(),
                timeout=20,
            )
            if r.status_code != 401:
                return s, "session.json"
            last_err = RuntimeError("session.json: 401 Unauthorized")
        except Exception as e:
            last_err = e

    raise RuntimeError(
        "Нет рабочей сессии amoCRM (cookies). "
        "Войдите в https://kuhhospital.amocrm.ru в Yandex/Edge, "
        "затем закройте браузер на 5 сек и перезапустите скрипт. "
        f"last_err={last_err}"
    )


def _headers() -> dict[str, str]:
    return {
        "X-Requested-With": "XMLHttpRequest",
        "Referer": BASE + "/amo-market/",
        "Origin": BASE,
    }


def get_agreement(s: requests.Session) -> dict:
    r = s.get(BASE + "/ajax/v4/additional_agreements", headers=_headers(), timeout=20)
    if r.status_code != 200:
        return {"status": f"http_{r.status_code}", "raw": r.text[:300]}
    data = r.json()
    AGREE_CACHE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return data


def upload_widget(s: requests.Session, uuid: str) -> requests.Response:
    if not ZIP_SRC.exists():
        raise FileNotFoundError(f"Нет zip: {ZIP_SRC}")
    td = Path(tempfile.mkdtemp())
    wzip = td / "widget.zip"
    shutil.copy(ZIP_SRC, wzip)
    url = f"{BASE}/ajax/widgets/{uuid}/widget/upload/?fileapi{int(time.time() * 1000)}"
    with open(wzip, "rb") as f:
        return s.post(
            url,
            headers=_headers(),
            files={
                "widget": (
                    "widget.zip",
                    f,
                    "application/x-zip-compressed",
                )
            },
            data={"_widget": "widget.zip"},
            timeout=120,
        )


def client_info(s: requests.Session, uuid: str) -> dict:
    r = s.get(f"{BASE}/v3/clients/{uuid}", headers=_headers(), timeout=30)
    if r.status_code != 200:
        return {"error": r.status_code, "body": r.text[:300]}
    return r.json()


def set_backend_acl() -> bool:
    try:
        r = requests.post(
            "http://127.0.0.1:8090/api/v1/widget/acl",
            json={"access_mode": "all_managers", "allowed_user_ids": []},
            timeout=10,
        )
        return r.status_code < 300
    except Exception:
        return False


def set_widget_settings(s: requests.Session, uuid: str, tunnel: str) -> object:
    payload = {
        "api_base": tunnel,
        "api_token": "",
        "auto_refresh": "90",
        "access_mode": "all_managers",
        "allowed_user_ids": "",
    }
    codes = [uuid]
    try:
        own = s.get(
            BASE + "/ajax/settings/widgets/category/own_integrations/1/",
            headers=_headers(),
            timeout=30,
        ).json()
        for code, info in (own.get("integrations") or {}).items():
            name = str(info.get("name") or "")
            if "Помощник" in name or "AI" in name:
                codes.insert(0, code)
    except Exception:
        pass

    # Prefer OAuth client if available
    try:
        from amocrm_client import AmoCRMClient

        c = AmoCRMClient()
        for code in codes:
            try:
                return {"code": code, "result": c._request("POST", f"/api/v4/widgets/{code}", json=payload)}
            except Exception as e:
                last = e
                continue
    except Exception as e:
        last = e

    # Cookie session fallback
    for code in codes:
        try:
            r = s.post(
                f"{BASE}/api/v4/widgets/{code}",
                headers={**_headers(), "Content-Type": "application/json"},
                json=payload,
                timeout=30,
            )
            if r.status_code < 300:
                return {"code": code, "result": r.json() if r.text else {"ok": True}}
            last = RuntimeError(f"{code}: {r.status_code} {r.text[:200]}")
        except Exception as e:
            last = e
    return {"error": str(last)}


def do_upload_and_configure(s: requests.Session, agreement: dict) -> dict:
    load_dotenv(ROOT / ".env")
    uuid = os.getenv("AMO_CLIENT_ID") or INTEGRATION_UUID
    tunnel = api_base()
    print("Agreement OK — uploading widget.zip ...", flush=True)
    up = upload_widget(s, uuid)
    print("UPLOAD", up.status_code, up.text[:400], flush=True)
    client = client_info(s, uuid)
    has_widget = bool(client.get("has_widget"))
    print(
        "client has_widget=",
        has_widget,
        "name=",
        client.get("name"),
        flush=True,
    )
    acl_ok = set_backend_acl()
    print("backend ACL all_managers=", acl_ok, flush=True)
    settings_ok = set_widget_settings(s, uuid, tunnel)
    print("settings", settings_ok, flush=True)

    # Re-verify has_widget after upload
    client2 = client_info(s, uuid)
    has_widget = bool(client2.get("has_widget")) or has_widget

    out = {
        "ok": has_widget
        or (up.status_code < 300 and "error" not in up.text.lower()),
        "upload_status": up.status_code,
        "upload_body": up.text[:500],
        "has_widget": has_widget,
        "client_name": client2.get("name") or client.get("name"),
        "api_base": tunnel,
        "access_mode": "all_managers",
        "settings": settings_ok,
        "acl_ok": acl_ok,
        "agreement": agreement,
        "uuid": uuid,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("DONE", json.dumps(out, ensure_ascii=False), flush=True)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Wait for amo agreement and upload widget")
    parser.add_argument("--once", action="store_true", help="Single check; upload if ready")
    parser.add_argument("--status", action="store_true", help="Print agreement status only")
    parser.add_argument(
        "--minutes",
        type=int,
        default=45,
        help="Max wait minutes (default 45)",
    )
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    print("api_base:", api_base(), flush=True)
    print("zip:", ZIP_SRC, "exists=", ZIP_SRC.exists(), flush=True)

    try:
        s, src = session()
        print("cookies_source:", src, flush=True)
    except Exception as e:
        print("COOKIE_ERROR", e, flush=True)
        OUT.write_text(
            json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        raise SystemExit(2)

    if args.status:
        data = get_agreement(s)
        print(json.dumps(data, ensure_ascii=False, indent=2), flush=True)
        return

    print("Waiting for additional agreement (IP/individual or legal_entity)...", flush=True)
    deadline = time.time() + (0 if args.once else args.minutes * 60)
    last = None
    while True:
        try:
            # Refresh cookies periodically in case user re-logged in
            try:
                s, src = session()
            except Exception:
                pass
            data = get_agreement(s)
            st = data.get("status")
            if st != last:
                print(
                    f"agreement status: {st} entity={data.get('entity_type')} src={src}",
                    flush=True,
                )
                last = st
            if st in OK_STATUSES:
                out = do_upload_and_configure(s, data)
                raise SystemExit(0 if out.get("ok") else 3)
            if args.once or time.time() >= deadline:
                break
        except SystemExit:
            raise
        except Exception as e:
            print("wait err", e, flush=True)
        if args.once:
            break
        time.sleep(5)

    msg = "TIMEOUT — agreement not completed" if not args.once else "NOT_READY — agreement not performed/accepted"
    print(msg, flush=True)
    print(
        "Заполните доп.соглашение как ИП (Мое приложение → Создать интеграцию → приватная → ИП). "
        "См. READY.txt / WIDGET_INSTALL.md",
        flush=True,
    )
    raise SystemExit(1)


if __name__ == "__main__":
    main()
