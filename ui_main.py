"""Open only the desktop window (expects API already on :8090)."""

from __future__ import annotations

import os
import sys
import time
import traceback
import urllib.request
from pathlib import Path


def root_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


ROOT = root_dir()
os.chdir(str(ROOT))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "CRMAIDesk"
LOG_DIR = DATA / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG = LOG_DIR / "ui.log"
PORT = int(os.environ.get("API_PORT", "8090"))
URL = f"http://127.0.0.1:{PORT}/app/"


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n"
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def wait_api(tries: int = 60) -> bool:
    for i in range(tries):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=0.5)
            log(f"API ready after {i * 0.25:.1f}s")
            return True
        except Exception:
            time.sleep(0.25)
    return False


def main() -> None:
    log("=== UI window start ===")
    if not wait_api():
        log("API not ready")
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                0,
                f"Сервер CRM AI Desk не отвечает на порту {PORT}.\n"
                "Запустите INSTALL / Repair или Launch_CRM_AI_Desk.vbs\n"
                f"Log: {LOG_DIR}",
                "CRM AI Desk",
                0x10,
            )
        except Exception:
            pass
        return

    try:
        import webview
    except ImportError:
        log("install pywebview")
        import subprocess

        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "pywebview", "-q"]
        )
        import webview

    webview.create_window(
        title="CRM AI Desk",
        url=URL,
        width=1380,
        height=900,
        min_size=(1050, 720),
        background_color="#0b1220",
        text_select=True,
        confirm_close=False,
    )
    log(f"window {URL}")
    try:
        webview.start(debug=False, gui="edgechromium")
    except Exception:
        webview.start(debug=False)
    log("window closed")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("UI FATAL\n" + traceback.format_exc())
        raise
