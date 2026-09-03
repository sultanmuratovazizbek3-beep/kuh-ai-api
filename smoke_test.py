"""Smoke tests for CRM AI Desk — run before install."""

from __future__ import annotations

import json
import socket
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
PORT = 8090
errors: list[str] = []


def ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")
    errors.append(msg)


def test_imports() -> None:
    print("1) Imports")
    mods = [
        "config",
        "storage",
        "amocrm_client",
        "collector",
        "analyzer",
        "assistant_service",
        "api_server",
        "transcriber",
        "profiles",
        "webview",
        "fastapi",
        "uvicorn",
    ]
    for m in mods:
        try:
            __import__(m)
            ok(m)
        except Exception as e:
            fail(f"{m}: {e}")


def test_config() -> None:
    print("2) Config / CRM")
    try:
        from config import validate_config
        from profiles import get_credentials

        miss = validate_config()
        if miss:
            fail(f"missing env: {miss}")
        else:
            ok("env present")
        creds = get_credentials()
        if creds:
            ok(f"active profile: {getattr(creds, 'label', None) or getattr(creds, 'subdomain', '?')}")
        else:
            fail("no active CRM profile")
    except Exception as e:
        fail(str(e))


def test_api_live() -> None:
    print("3) Live API")
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=1):
            pass
    except OSError:
        fail(f"port {PORT} not listening — start app first or run install")
        return
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=5) as r:
            data = json.loads(r.read().decode("utf-8"))
        if data.get("status") in ("ok", "degraded"):
            ok(f"health {data.get('status')}")
        else:
            fail(f"health bad: {data}")
    except Exception as e:
        fail(f"health: {e}")
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/app/", timeout=5) as r:
            code = r.status
        if code == 200:
            ok("UI /app/ 200")
        else:
            fail(f"UI status {code}")
    except Exception as e:
        fail(f"UI: {e}")
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{PORT}/api/v1/stats?hours=24", timeout=15
        ) as r:
            data = json.loads(r.read().decode("utf-8"))
        ok(f"stats ok keys={list(data.keys())[:5]}")
    except Exception as e:
        fail(f"stats: {e}")


def main() -> int:
    print("=== CRM AI Desk smoke test ===")
    print(f"root: {ROOT}")
    test_imports()
    test_config()
    test_api_live()
    print()
    if errors:
        print(f"FAILED: {len(errors)} error(s)")
        for e in errors:
            print(" -", e)
        return 1
    print("ALL PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
