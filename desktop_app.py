"""
KUH AI — desktop application (Windows).
Beautiful local UI + AmoCRM analytics backend. No browser extensions.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DESKTOP_UI = ROOT / "desktop"
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"
API_HOST = "127.0.0.1"
API_PORT = 8090


def _py() -> str:
    return str(VENV_PY if VENV_PY.exists() else sys.executable)


def port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.8):
            return True
    except OSError:
        return False


def ensure_api() -> subprocess.Popen | None:
    if port_open(API_HOST, API_PORT):
        return None
    cmd = [
        _py(),
        "-m",
        "uvicorn",
        "api_server:app",
        "--host",
        "0.0.0.0",
        "--port",
        str(API_PORT),
    ]
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(40):
        if port_open(API_HOST, API_PORT):
            return proc
        time.sleep(0.25)
    return proc


def start_collector_bg() -> None:
    """Optional light collector in background (non-blocking)."""

    def _run():
        try:
            subprocess.Popen(
                [_py(), "main.py", "--once"],
                cwd=str(ROOT),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True).start()


def main() -> None:
    ui = DESKTOP_UI / "index.html"
    if not ui.exists():
        print("UI missing:", ui)
        sys.exit(1)

    api_proc = ensure_api()
    start_collector_bg()

    try:
        import webview
    except ImportError:
        print("Installing pywebview…")
        subprocess.check_call([_py(), "-m", "pip", "install", "pywebview", "-q"])
        import webview

    # Import env profile once so first launch works out of the box
    try:
        from profiles import get_credentials, import_from_env

        if not get_credentials():
            import_from_env()
    except Exception:
        pass

    # Prefer HTTP UI so fetch() to API never fails (file:// often shows API offline)
    url = f"http://{API_HOST}:{API_PORT}/app/"
    # wait until /app/ responds
    for _ in range(40):
        try:
            import urllib.request

            urllib.request.urlopen(url, timeout=0.5)
            break
        except Exception:
            time.sleep(0.25)

    window = webview.create_window(
        title="CRM AI Desk · Multi-CRM assistant (RU/UZ)",
        url=url,
        width=1320,
        height=860,
        min_size=(1000, 680),
        background_color="#0b1220",
        text_select=True,
    )

    webview.start(debug=False)

    # cleanup only if we started API in this process and user wants — keep API running for other tools
    _ = api_proc


if __name__ == "__main__":
    main()
