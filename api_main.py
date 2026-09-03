"""Start only the local API server (no UI). Used by reliable launcher."""

from __future__ import annotations

import os
import sys
import traceback
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
LOG = LOG_DIR / "api.log"
PORT = int(os.environ.get("API_PORT", "8090"))


def log(msg: str) -> None:
    import time

    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n"
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def fix_stdio() -> None:
    if sys.stdout is None:
        try:
            sys.stdout = open(LOG_DIR / "api_stdout.log", "a", encoding="utf-8")
        except Exception:
            sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        try:
            sys.stderr = open(LOG_DIR / "api_stderr.log", "a", encoding="utf-8")
        except Exception:
            sys.stderr = open(os.devnull, "w")


def main() -> None:
    fix_stdio()
    log("=== API process start ===")
    try:
        from profiles import get_credentials, import_from_env

        if not get_credentials():
            import_from_env(ROOT / ".env")
            import_from_env(Path(r"C:\Users\ACC-2\amocrm-analytics\.env"))
    except Exception as e:
        log(f"CRM import: {e}")

    try:
        import uvicorn
        from api_server import app

        log_config = {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                }
            },
            "handlers": {
                "default": {
                    "class": "logging.FileHandler",
                    "filename": str(LOG_DIR / "uvicorn.log"),
                    "formatter": "default",
                    "encoding": "utf-8",
                }
            },
            "loggers": {
                "uvicorn": {"handlers": ["default"], "level": "INFO"},
                "uvicorn.error": {"handlers": ["default"], "level": "INFO"},
                "uvicorn.access": {"handlers": ["default"], "level": "WARNING"},
            },
        }
        log(f"uvicorn bind 127.0.0.1:{PORT}")
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=PORT,
            log_level="info",
            access_log=False,
            log_config=log_config,
        )
    except Exception:
        log("API FATAL\n" + traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
