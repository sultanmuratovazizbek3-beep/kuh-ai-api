"""
Inject KUH AI panel into Yandex/Chrome AmoCRM tabs via Chrome DevTools Protocol.
Works even when browser extensions fail.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INJECT = (ROOT / "browser-extension" / "inject_panel.js").read_text(encoding="utf-8")
BROWSER = Path(r"C:\Program Files\Yandex\YandexBrowser\Application\browser.exe")
PORT = 9333
USER_DATA = Path.home() / "AppData/Local/Yandex/YandexBrowser/User Data"


def http_get(url: str, timeout: float = 5.0):
    req = urllib.request.Request(url, headers={"User-Agent": "kuh-cdp"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def list_tabs():
    return http_get(f"http://127.0.0.1:{PORT}/json")


def browser_running_debug() -> bool:
    try:
        http_get(f"http://127.0.0.1:{PORT}/json/version", timeout=2)
        return True
    except Exception:
        return False


def start_browser(url: str = "https://kuhhospital.amocrm.ru/") -> None:
    # Prefer same profile so user stays logged in
    args = [
        str(BROWSER),
        f"--remote-debugging-port={PORT}",
        "--remote-allow-origins=*",
        "--no-first-run",
        url,
    ]
    subprocess.Popen(args, cwd=str(BROWSER.parent))
    for _ in range(30):
        if browser_running_debug():
            return
        time.sleep(0.5)
    raise RuntimeError("Browser debug port not up")


def inject_into_ws(ws_url: str, expression: str) -> dict:
    try:
        import websocket  # type: ignore
    except ImportError:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "websocket-client", "-q"]
        )
        import websocket  # type: ignore

    ws = websocket.create_connection(ws_url, timeout=10)
    try:
        # enable runtime
        ws.send(json.dumps({"id": 1, "method": "Runtime.enable"}))
        ws.recv()
        # inject on every new document in this target
        ws.send(
            json.dumps(
                {
                    "id": 2,
                    "method": "Page.addScriptToEvaluateOnNewDocument",
                    "params": {"source": expression},
                }
            )
        )
        ws.recv()
        # run now
        ws.send(
            json.dumps(
                {
                    "id": 3,
                    "method": "Runtime.evaluate",
                    "params": {
                        "expression": expression,
                        "awaitPromise": False,
                        "userGesture": True,
                    },
                }
            )
        )
        raw = ws.recv()
        return json.loads(raw)
    finally:
        ws.close()


def inject_all_amocrm() -> list[dict]:
    results = []
    tabs = list_tabs()
    for t in tabs:
        url = t.get("url") or ""
        ws = t.get("webSocketDebuggerUrl")
        if not ws:
            continue
        if "amocrm" not in url and "kommo" not in url:
            # still inject into blank/new if title suggests amo? skip
            if not url.startswith("http"):
                continue
            if "amocrm" not in url:
                continue
        try:
            res = inject_into_ws(ws, INJECT)
            results.append({"url": url, "ok": True, "title": t.get("title"), "res": res})
            print(f"OK inject: {t.get('title')} | {url[:80]}")
        except Exception as e:
            results.append({"url": url, "ok": False, "error": str(e)})
            print(f"FAIL {url[:60]}: {e}")
    return results


def main() -> None:
    open_url = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "https://kuhhospital.amocrm.ru/leads/detail/31260797"
    )

    if not browser_running_debug():
        print(f"Starting Yandex with remote debugging on {PORT}…")
        # Close non-debug instances so profile locks free
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", "browser.exe"],
                capture_output=True,
                check=False,
            )
            time.sleep(2)
        except Exception:
            pass
        start_browser(open_url)
        time.sleep(3)
    else:
        print("Debug port already open")

    # open target page via new tab if needed
    try:
        # New tab
        urllib.request.urlopen(
            f"http://127.0.0.1:{PORT}/json/new?{urllib.parse.quote(open_url, safe='')}",
            timeout=5,
        )
    except Exception:
        pass

    time.sleep(2)
    results = inject_all_amocrm()
    amo = [r for r in results if r.get("ok")]
    print(f"Injected into {len(amo)} AmoCRM tab(s)")
    if not amo:
        print("No AmoCRM tabs found yet — open a deal and re-run:")
        print(f"  {sys.executable} cdp_inject.py")
        # keep trying a few seconds
        for i in range(8):
            time.sleep(1.5)
            results = inject_all_amocrm()
            amo = [r for r in results if r.get("ok")]
            if amo:
                print(f"Injected after wait: {len(amo)}")
                break

    # Watch loop: re-inject periodically for SPA navigation
    if "--watch" in sys.argv:
        print("Watch mode: reinject every 8s (Ctrl+C to stop)")
        while True:
            try:
                inject_all_amocrm()
            except Exception as e:
                print("watch error", e)
            time.sleep(8)


if __name__ == "__main__":
    import urllib.parse

    main()
