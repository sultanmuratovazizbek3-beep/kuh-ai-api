"""
Optional webhook receiver for near-real-time AmoCRM events.

In AmoCRM: Settings → Integrations → Webhooks
  URL: https://YOUR_HOST/webhook/amocrm
  Events: note, lead status, talk, etc.

Run:
  uvicorn webhook_server:app --host 0.0.0.0 --port 8088
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request

from analyzer import analyze_batch
from collector import Collector
from storage import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("amocrm-webhook")

app = FastAPI(title="AmoCRM Analytics Webhooks")


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/webhook/amocrm")
async def amocrm_webhook(request: Request) -> dict[str, Any]:
    """Accept form or JSON webhooks from AmoCRM and trigger a light sync."""
    content_type = request.headers.get("content-type", "")
    payload: Any
    if "application/json" in content_type:
        payload = await request.json()
    else:
        form = await request.form()
        payload = dict(form)

    logger.info("Webhook received keys=%s", list(payload.keys())[:20] if isinstance(payload, dict) else type(payload))

    # Lightweight resync of recent data
    try:
        stats = Collector().run_once(lookback_hours=6)
        analyzed = analyze_batch(limit=5)
        return {"ok": True, "stats": stats, "analyzed": analyzed}
    except Exception as exc:
        logger.exception("Webhook processing failed")
        return {"ok": False, "error": str(exc)}
