"""Send reports to Telegram (optional)."""

from __future__ import annotations

import logging
from pathlib import Path

import requests

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from storage import mark_report_sent

logger = logging.getLogger(__name__)


def _split_message(text: str, limit: int = 4000) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    buf: list[str] = []
    size = 0
    for line in text.splitlines(keepends=True):
        if size + len(line) > limit and buf:
            parts.append("".join(buf))
            buf = [line]
            size = len(line)
        else:
            buf.append(line)
            size += len(line)
    if buf:
        parts.append("".join(buf))
    return parts


def send_telegram_text(text: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.info("Telegram not configured — skip send")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    ok = True
    for i, part in enumerate(_split_message(text)):
        # Telegram Markdown is picky; send as plain text
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": part,
            "disable_web_page_preview": True,
        }
        try:
            r = requests.post(url, json=payload, timeout=30)
            if r.status_code != 200:
                logger.error("Telegram error: %s %s", r.status_code, r.text[:300])
                ok = False
        except Exception as exc:
            logger.error("Telegram send failed: %s", exc)
            ok = False
    return ok


def send_telegram_document(path: Path, caption: str = "") -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    try:
        with path.open("rb") as f:
            r = requests.post(
                url,
                data={"chat_id": TELEGRAM_CHAT_ID, "caption": caption[:1000]},
                files={"document": (path.name, f)},
                timeout=60,
            )
        if r.status_code != 200:
            logger.error("Telegram document error: %s", r.text[:300])
            return False
        return True
    except Exception as exc:
        logger.error("Telegram document failed: %s", exc)
        return False


def deliver_report(report_id: int, path: Path, markdown: str, title: str) -> None:
    # Short summary first
    header = f"📊 {title}\n\n"
    # Take first ~3500 chars of report body for message
    body = markdown
    if len(body) > 3500:
        body = body[:3500] + "\n\n… (полный отчёт во вложении)"
    sent = send_telegram_text(header + body)
    send_telegram_document(path, caption=title)
    if sent:
        mark_report_sent(report_id)
        logger.info("Report %s delivered to Telegram", report_id)
    else:
        logger.info("Report %s saved to %s (Telegram off or failed)", report_id, path)
