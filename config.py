import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def _base_dir() -> Path:
    # PyInstaller frozen: data next to executable or in _MEIPASS
    if getattr(sys, "frozen", False):
        # Prefer install directory (writable sibling of exe)
        exe_dir = Path(sys.executable).resolve().parent
        if (exe_dir / "desktop").exists() or (exe_dir / "api_server.py").exists():
            return exe_dir
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return exe_dir
    return Path(__file__).resolve().parent


BASE_DIR = _base_dir()
# User data for profiles / db when installed
_APP_DATA = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "CRMAIDesk"
_APP_DATA.mkdir(parents=True, exist_ok=True)
load_dotenv(BASE_DIR / ".env")
load_dotenv(_APP_DATA / ".env")

# --- AmoCRM ---
AMO_SUBDOMAIN = os.getenv("AMO_SUBDOMAIN", "")
AMO_CLIENT_ID = os.getenv("AMO_CLIENT_ID", "")
AMO_CLIENT_SECRET = os.getenv("AMO_CLIENT_SECRET", "")
AMO_REDIRECT_URI = os.getenv("AMO_REDIRECT_URI", "https://example.com")
AMO_REFRESH_TOKEN = os.getenv("AMO_REFRESH_TOKEN", "")
AMO_LONG_LIVED_TOKEN = os.getenv("AMO_LONG_LIVED_TOKEN", "")

# --- AI (SpaceXAI / xAI) ---
XAI_API_KEY = os.getenv("XAI_API_KEY", "")
XAI_BASE_URL = os.getenv("XAI_BASE_URL", "https://api.x.ai/v1")
XAI_MODEL = os.getenv("XAI_MODEL", "grok-4.5")

# --- Telegram delivery (optional; not used for chats/WhatsApp analysis) ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "") or os.getenv("BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Optional secret for widget/API (header X-Api-Token)
ASSISTANT_API_TOKEN = os.getenv("ASSISTANT_API_TOKEN", "")
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8090"))

# --- Runtime ---
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "180"))
ANALYZE_BATCH_SIZE = int(os.getenv("ANALYZE_BATCH_SIZE", "25"))
# Write AI notes into amoCRM deal cards (ON by default for continuous mode)
WRITE_AMO_CALL_NOTES = os.getenv("WRITE_AMO_CALL_NOTES", "1").strip() not in (
    "0",
    "false",
    "False",
    "no",
)
TIMEZONE = os.getenv("TIMEZONE", "Asia/Tashkent")

# --- Speech-to-text (clinic UZ+RU phone calls) ---
# medium recommended for Uzbek; small is faster but weaker on UZ
STT_MODEL = os.getenv("STT_MODEL", "medium")
STT_DEVICE = os.getenv("STT_DEVICE", "cpu")
STT_COMPUTE = os.getenv("STT_COMPUTE", "int8")
# Fine-tuned Uzbek Whisper (transformers) as second opinion
STT_UZ_HF_MODEL = os.getenv("STT_UZ_HF_MODEL", "OvozifyLabs/whisper-small-uz-v1")
STT_USE_UZ_HF = os.getenv("STT_USE_UZ_HF", "1").strip() not in ("0", "false", "no", "False")

# Report schedule (local time, 24h)
DAILY_REPORT_HOUR = int(os.getenv("DAILY_REPORT_HOUR", "20"))
WEEKLY_REPORT_DOW = int(os.getenv("WEEKLY_REPORT_DOW", "0"))  # 0=Mon
WEEKLY_REPORT_HOUR = int(os.getenv("WEEKLY_REPORT_HOUR", "10"))
MONTHLY_REPORT_DAY = int(os.getenv("MONTHLY_REPORT_DAY", "1"))
MONTHLY_REPORT_HOUR = int(os.getenv("MONTHLY_REPORT_HOUR", "10"))

# Writable paths always under AppData when frozen
_DATA_ROOT = _APP_DATA if getattr(sys, "frozen", False) else BASE_DIR
DB_PATH = _DATA_ROOT / "data" / "analytics.db"
REPORTS_DIR = Path.home() / "Desktop" / "AmoCRM-AI-Reports"
if getattr(sys, "frozen", False):
    REPORTS_DIR = Path.home() / "Desktop" / "CRM-AI-Reports"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


# Closed won status IDs are account-specific; 142 is default "Успешно реализовано"
# 143 is default "Закрыто и не реализовано" — can override via env
WON_STATUS_IDS = {
    int(x) for x in os.getenv("WON_STATUS_IDS", "142").split(",") if x.strip().isdigit()
}
LOST_STATUS_IDS = {
    int(x) for x in os.getenv("LOST_STATUS_IDS", "143").split(",") if x.strip().isdigit()
}

# Event types we care about
CALL_EVENT_TYPES = ("incoming_call", "outgoing_call")
CHAT_EVENT_TYPES = (
    "incoming_chat_message",
    "outgoing_chat_message",
    "entity_direct_message",
)
LEAD_EVENT_TYPES = ("lead_added", "lead_status_changed", "entity_responsible_changed")


def validate_config() -> list[str]:
    missing: list[str] = []
    if not AMO_SUBDOMAIN:
        missing.append("AMO_SUBDOMAIN")
    if not AMO_LONG_LIVED_TOKEN and not AMO_REFRESH_TOKEN:
        missing.append("AMO_LONG_LIVED_TOKEN или AMO_REFRESH_TOKEN")
    if not AMO_LONG_LIVED_TOKEN:
        if not AMO_CLIENT_ID:
            missing.append("AMO_CLIENT_ID")
        if not AMO_CLIENT_SECRET:
            missing.append("AMO_CLIENT_SECRET")
    return missing
