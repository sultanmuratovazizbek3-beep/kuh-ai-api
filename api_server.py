"""
HTTP API for AmoCRM widget + health.

  uvicorn api_server:app --host 0.0.0.0 --port 8090

Endpoints used by the right-panel widget in the lead card.
Telegram / messengers are not used here.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from amocrm_client import AmoCRMClient
from analyzer import analyze_batch
from assistant_service import analyze_free_text, build_assistant_payload
from collector import Collector
from config import ASSISTANT_API_TOKEN, BASE_DIR, validate_config
from report_generator import generate_report
from storage import init_db, period_stats
from widget_acl import load_acl, save_acl, user_allowed

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("amocrm-api")

app = FastAPI(title="AmoCRM Analytics Assistant", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WIDGET_DIR = BASE_DIR / "widget"
PUBLIC_DIR = BASE_DIR / "public"
DESKTOP_UI_DIR = BASE_DIR / "desktop"
_collector_lock = threading.Lock()
_collector_state: dict[str, Any] = {
    "enabled": False,
    "last_ok": 0,
    "last_error": "",
    "running": False,
}


class AnalyzeBody(BaseModel):
    text: str = Field(..., min_length=1)
    kind: str = "chat"
    lead_id: int | None = None


class LeadAssistBody(BaseModel):
    lead_id: int
    notes: list[dict[str, Any]] | None = None
    write_note: bool = False


class WriteNoteBody(BaseModel):
    lead_id: int
    text: str = Field(..., min_length=1)
    user_id: int | None = None
    is_admin: bool = False


class WidgetAclBody(BaseModel):
    access_mode: str = "admins_only"
    allowed_user_ids: list[int] = Field(default_factory=list)


class WidgetAccessCheckBody(BaseModel):
    user_id: int | None = None
    is_admin: bool = False


def _check_api_token(
    x_api_token: str | None = None,
    authorization: str | None = None,
) -> None:
    """If ASSISTANT_API_TOKEN is set, require matching header."""
    expected = (ASSISTANT_API_TOKEN or "").strip()
    if not expected:
        return
    got = (x_api_token or "").strip()
    if not got and authorization:
        auth = authorization.strip()
        if auth.lower().startswith("bearer "):
            got = auth[7:].strip()
    if got != expected:
        raise HTTPException(status_code=401, detail="Invalid API token")


def _cloud_collector_enabled() -> bool:
    return os.getenv("ENABLE_CLOUD_COLLECTOR", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _run_cloud_collect_once() -> None:
    from collector import Collector

    with _collector_lock:
        _collector_state["running"] = True
    try:
        Collector().run_once(lookback_hours=6)
        with _collector_lock:
            _collector_state["last_ok"] = int(time.time())
            _collector_state["last_error"] = ""
    except Exception as exc:
        logger.exception("cloud collector failed")
        with _collector_lock:
            _collector_state["last_error"] = str(exc)[:300]
    finally:
        with _collector_lock:
            _collector_state["running"] = False


def _start_cloud_collector() -> None:
    interval = max(60, int(os.getenv("CLOUD_COLLECT_INTERVAL", "180")))

    def loop() -> None:
        time.sleep(8)
        while True:
            _run_cloud_collect_once()
            time.sleep(interval)

    threading.Thread(target=loop, name="cloud-collector", daemon=True).start()
    with _collector_lock:
        _collector_state["enabled"] = True
    logger.info("Cloud collector started, interval=%ss", interval)


@app.on_event("startup")
def _startup() -> None:
    init_db()
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("API started")
    if _cloud_collector_enabled():
        _start_cloud_collector()


@app.get("/health")
def health() -> dict[str, Any]:
    missing = validate_config()
    worker = False
    try:
        pid_path = (
            Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
            / "CRMAIDesk"
            / "worker.pid"
        )
        if os.name == "nt" and pid_path.exists():
            pid = int(pid_path.read_text(encoding="utf-8").strip())
            import ctypes

            h = ctypes.windll.kernel32.OpenProcess(0x100000, False, pid)  # type: ignore
            if h:
                ctypes.windll.kernel32.CloseHandle(h)  # type: ignore
                worker = True
    except Exception:
        worker = False
    with _collector_lock:
        collector = dict(_collector_state)
    if collector.get("enabled"):
        worker = worker or bool(collector.get("last_ok") or collector.get("running"))
    return {
        "status": "ok" if not missing else "degraded",
        "missing_config": missing,
        "ts": int(time.time()),
        "worker": worker,
        "collector": collector,
        "write_amo_notes": True,
    }



@app.get("/api/v1/ping")
def ping() -> dict[str, str]:
    return {"pong": "ok"}


@app.get("/api/v1/widget/config")
def widget_config() -> dict[str, Any]:
    """Public-ish config for the amo widget (no secrets)."""
    acl = load_acl()
    return {
        "ok": True,
        "access_mode": acl.get("access_mode"),
        "allowed_user_ids": acl.get("allowed_user_ids") or [],
        "updated_at": acl.get("updated_at") or 0,
        "token_required": bool((ASSISTANT_API_TOKEN or "").strip()),
    }


@app.get("/api/v1/widget/acl")
def widget_acl_get(
    x_api_token: str | None = Header(default=None, alias="X-Api-Token"),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_api_token(x_api_token, authorization)
    acl = load_acl()
    return {"ok": True, **acl}


@app.post("/api/v1/widget/acl")
def widget_acl_set(
    body: WidgetAclBody,
    x_api_token: str | None = Header(default=None, alias="X-Api-Token"),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_api_token(x_api_token, authorization)
    saved = save_acl(
        access_mode=body.access_mode,
        allowed_user_ids=body.allowed_user_ids,
    )
    return {"ok": True, **saved}


@app.post("/api/v1/widget/access_check")
def widget_access_check(body: WidgetAccessCheckBody) -> dict[str, Any]:
    """Widget asks: may this amo user use the helper?"""
    allowed = user_allowed(
        user_id=body.user_id,
        is_admin=bool(body.is_admin),
    )
    acl = load_acl()
    return {
        "ok": True,
        "allowed": allowed,
        "access_mode": acl.get("access_mode"),
        "is_admin": bool(body.is_admin),
        "user_id": body.user_id,
    }


@app.post("/api/v1/assistant/lead")
def assist_lead(
    body: LeadAssistBody,
    x_api_token: str | None = Header(default=None, alias="X-Api-Token"),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_api_token(x_api_token, authorization)
    try:
        return build_assistant_payload(
            lead_id=body.lead_id,
            notes_payload=body.notes,
            write_note=body.write_note,
            live_stt=True,
        )
    except Exception as exc:
        logger.exception("assist_lead failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/v1/assistant/lead/{lead_id}")
def assist_lead_get(
    lead_id: int, write_note: bool = True, live_stt: bool = True
) -> dict[str, Any]:
    try:
        return build_assistant_payload(
            lead_id=lead_id, write_note=write_note, live_stt=live_stt
        )
    except Exception as exc:
        logger.exception("assist_lead_get failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/v1/assistant/analyze")
def assist_analyze(body: AnalyzeBody) -> dict[str, Any]:
    return analyze_free_text(body.text, body.kind)


@app.post("/api/v1/assistant/write_note")
def write_note(
    body: WriteNoteBody,
    x_api_token: str | None = Header(default=None, alias="X-Api-Token"),
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_api_token(x_api_token, authorization)
    if body.user_id is not None or body.is_admin:
        if not user_allowed(user_id=body.user_id, is_admin=bool(body.is_admin)):
            raise HTTPException(status_code=403, detail="Нет доступа к виджету")
    try:
        client = AmoCRMClient()
        client.add_note_to_lead(body.lead_id, body.text)
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/v1/collect")
def collect_now(hours: int = 6) -> dict[str, Any]:
    stats = Collector().run_once(lookback_hours=hours)
    analyzed = analyze_batch()
    stats["analyzed"] = analyzed
    return {"ok": True, "stats": stats}


@app.post("/api/v1/stt/batch")
def stt_batch(
    limit: int = 8,
    min_duration: int = 10,
    force: bool = False,
) -> dict[str, Any]:
    """Transcribe call recordings (UZ+RU multi-pass). force=1 re-runs existing."""
    try:
        from transcriber import transcribe_batch

        result = transcribe_batch(
            limit=max(1, min(limit, 30)),
            min_duration=max(5, min_duration),
            force_retranscribe=force,
        )
        # re-analyze newly transcribed
        n = analyze_batch(limit=max(5, result.get("ok", 0) + 5))
        result["analyzed"] = n
        return {"ok": True, **result}
    except Exception as e:
        logger.exception("stt_batch failed")
        raise HTTPException(500, str(e)) from e


@app.post("/api/v1/stt/one")
def stt_one(comm_id: str) -> dict[str, Any]:
    """Force re-transcribe a single call recording (can take 1–5 min)."""
    try:
        from transcriber import retranscribe_one

        result = retranscribe_one(comm_id)
        if not result.get("ok") and result.get("reason") == "not_found":
            raise HTTPException(404, f"communication not found: {comm_id}")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("stt_one failed")
        raise HTTPException(500, str(e)) from e


@app.get("/api/v1/report/{period}")
def report_now(period: str) -> dict[str, Any]:
    if period not in ("day", "week", "month"):
        raise HTTPException(400, "period must be day|week|month")
    report_id, path, md = generate_report(period)
    return {
        "ok": True,
        "report_id": report_id,
        "path": str(path),
        "markdown": md[:5000],
    }


def _period_bounds(
    hours: int | None = None,
    from_ts: int | None = None,
    to_ts: int | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> tuple[int, int]:
    """Resolve dashboard period: explicit dates/ts or trailing hours."""
    import datetime as _dt

    now = int(time.time())
    end = now
    start = now - max(1, int(hours or 168)) * 3600

    def _parse_day(s: str, end_of_day: bool = False) -> int | None:
        s = (s or "").strip()
        if not s:
            return None
        try:
            d = _dt.datetime.strptime(s[:10], "%Y-%m-%d")
            if end_of_day:
                d = d.replace(hour=23, minute=59, second=59)
            return int(d.timestamp())
        except ValueError:
            return None

    if from_ts and from_ts > 0:
        start = int(from_ts)
    elif from_date:
        p = _parse_day(from_date, end_of_day=False)
        if p is not None:
            start = p
    if to_ts and to_ts > 0:
        end = int(to_ts)
    elif to_date:
        p = _parse_day(to_date, end_of_day=True)
        if p is not None:
            end = p

    if end <= start:
        end = start + 86400
    # cap 366 days
    if end - start > 366 * 86400:
        start = end - 366 * 86400
    return start, end


@app.get("/api/v1/stats")
def stats(
    hours: int = 24,
    from_ts: int | None = None,
    to_ts: int | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict[str, Any]:
    start, end = _period_bounds(hours, from_ts, to_ts, from_date, to_date)
    return {
        "ok": True,
        "stats": period_stats(start, end),
        "start": start,
        "end": end,
        "hours": max(1, int(round((end - start) / 3600))),
    }


@app.get("/api/v1/dashboard")
def dashboard(
    hours: int = 168,
    from_ts: int | None = None,
    to_ts: int | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict[str, Any]:
    """Dashboard pack: KPIs, tops, working tips (KUH playbook)."""
    from storage import db, init_db

    init_db()
    start, end = _period_bounds(hours, from_ts, to_ts, from_date, to_date)
    hours = max(1, int(round((end - start) / 3600)))
    pack = period_stats(start, end)
    totals = pack.get("totals") or {}
    managers = list(pack.get("managers") or [])

    def active(m: dict) -> bool:
        return (
            (m.get("calls_total") or 0)
            + (m.get("chats_total") or 0)
            + (m.get("leads_worked") or 0)
            + (m.get("analyses_count") or 0)
        ) > 0

    mgrs = [m for m in managers if active(m) and (m.get("name") or "").strip()]

    def conv_rate(m: dict) -> float | None:
        w, l = m.get("leads_won") or 0, m.get("leads_lost") or 0
        if w + l <= 0:
            return None
        return round(100.0 * w / (w + l), 1)

    for m in mgrs:
        m["conversion"] = conv_rate(m)

    with_q = [m for m in mgrs if m.get("avg_quality_score") is not None]
    with_calls = [m for m in mgrs if (m.get("calls_total") or 0) > 0]
    with_won = [m for m in mgrs if (m.get("leads_won") or 0) > 0]
    with_conv = [
        m for m in mgrs if m.get("conversion") is not None and (m.get("leads_won") or 0) + (m.get("leads_lost") or 0) >= 3
    ]

    tops = {
        "quality_best": sorted(
            with_q, key=lambda x: (-(x.get("avg_quality_score") or 0), -(x.get("analyses_count") or 0))
        )[:5],
        "quality_weak": sorted(
            with_q, key=lambda x: ((x.get("avg_quality_score") or 99), -(x.get("analyses_count") or 0))
        )[:5],
        "calls_most": sorted(with_calls, key=lambda x: -(x.get("calls_total") or 0))[:5],
        "won_most": sorted(with_won, key=lambda x: -(x.get("leads_won") or 0))[:5],
        "conversion_best": sorted(
            with_conv, key=lambda x: (-(x.get("conversion") or 0), -(x.get("leads_won") or 0))
        )[:5],
        "chats_most": sorted(
            [m for m in mgrs if (m.get("chats_total") or 0) > 0],
            key=lambda x: -(x.get("chats_total") or 0),
        )[:5],
    }

    # Extra department KPIs
    with db() as conn:
        tr_ready = conn.execute(
            """
            SELECT COUNT(*) AS n FROM communications
            WHERE created_at >= ? AND created_at < ?
              AND transcript IS NOT NULL AND length(trim(transcript)) > 40
              AND transcript NOT LIKE '[%'
            """,
            (start, end),
        ).fetchone()
        rec_pending = conn.execute(
            """
            SELECT COUNT(*) AS n FROM communications
            WHERE kind = 'call'
              AND created_at >= ? AND created_at < ?
              AND recording_url IS NOT NULL AND recording_url != ''
              AND (transcript IS NULL OR length(trim(coalesce(transcript,''))) < 20)
            """,
            (start, end),
        ).fetchone()
        avg_q = conn.execute(
            """
            SELECT AVG(a.score) AS s, COUNT(*) AS n
            FROM analyses a
            JOIN communications c ON c.id = a.communication_id
            WHERE c.created_at >= ? AND c.created_at < ?
            """,
            (start, end),
        ).fetchone()
        avg_dur = conn.execute(
            """
            SELECT AVG(duration) AS d FROM communications
            WHERE kind='call' AND duration > 5
              AND created_at >= ? AND created_at < ?
            """,
            (start, end),
        ).fetchone()

    won = totals.get("leads_won") or 0
    lost = totals.get("leads_lost") or 0
    extra = {
        "avg_quality": round(float(avg_q["s"]), 2) if avg_q and avg_q["s"] is not None else None,
        "analyses": int(avg_q["n"] or 0) if avg_q else 0,
        "transcripts_ready": int(tr_ready["n"] or 0) if tr_ready else 0,
        "calls_pending_stt": int(rec_pending["n"] or 0) if rec_pending else 0,
        "avg_call_sec": int(round(float(avg_dur["d"]))) if avg_dur and avg_dur["d"] else None,
        "conversion_pct": round(100.0 * won / (won + lost), 1) if (won + lost) else None,
    }

    # Working tips — always useful, not fluff
    tips = [
        {
            "tag": "Запись",
            "title": "Два слота вслух",
            "text": "«Сегодня после 15:00 или завтра до 12:00 — что берём?» Без даты в CRM сделка почти не возвращается.",
        },
        {
            "tag": "Гео",
            "title": "Адрес — после записи",
            "text": "Не диктовать дорогу 5 минут, пока клиент за рулём. Сначала слот → потом гео/SMS.",
        },
        {
            "tag": "WhatsApp",
            "title": "Спам-фильтр",
            "text": "Корп. WhatsApp часто не доходит. Клиент пишет первым «Kimyo» — или шлите SMS-ссылку.",
        },
        {
            "tag": "Цена",
            "title": "Сумма + что входит",
            "text": "Не спорить «мы лучше». Назвать ориентир, состав, закрыть слотом.",
        },
        {
            "tag": "Подумаю",
            "title": "Hold 2 часа",
            "text": "Слот без оплаты + ваш перезвон во времени. Не «звоните сами, когда решите».",
        },
        {
            "tag": "Этика",
            "title": "Без диагноза по телефону",
            "text": "Маршрут и запись. Диагноз и «100% вылечим» — только врач на приёме / 103 при угрозе.",
        },
    ]
    # Dynamic tips from weak managers / pending STT
    if extra.get("calls_pending_stt", 0) >= 20:
        tips.insert(
            0,
            {
                "tag": "STT",
                "title": f"Ждут расшифровки: {extra['calls_pending_stt']}",
                "text": "Много звонков с записью без текста. В разборе — «Расшифровать», или прогоните пакет STT.",
            },
        )
    if tops["quality_weak"]:
        weak_names = ", ".join(
            (m.get("name") or "—") for m in tops["quality_weak"][:3]
        )
        tips.append(
            {
                "tag": "РОП",
                "title": "Кому помочь с качеством",
                "text": f"{weak_names} — разбор 1-на-1: запись, 2 слота, без «навигации» до фиксации.",
            }
        )
    if tops["quality_best"]:
        best = tops["quality_best"][0]
        tips.append(
            {
                "tag": "Эталон",
                "title": f"Ориентир: {best.get('name') or '—'}",
                "text": f"Ср. качество {best.get('avg_quality_score')}, успехов {best.get('leads_won') or 0}. Разберите 2–3 их звонка как образец.",
            }
        )

    def slim(m: dict) -> dict:
        return {
            "name": m.get("name"),
            "calls": m.get("calls_total") or 0,
            "chats": m.get("chats_total") or 0,
            "won": m.get("leads_won") or 0,
            "lost": m.get("leads_lost") or 0,
            "quality": m.get("avg_quality_score"),
            "conversion": m.get("conversion"),
            "analyses": m.get("analyses_count") or 0,
        }

    tops_slim = {k: [slim(x) for x in v] for k, v in tops.items()}

    return {
        "ok": True,
        "hours": hours,
        "start": start,
        "end": end,
        "totals": totals,
        "extra": extra,
        "tops": tops_slim,
        "tips": tips,
        "managers": [slim(m) for m in sorted(
            mgrs,
            key=lambda x: (
                -(x.get("avg_quality_score") or 0),
                -(x.get("calls_total") or 0),
            ),
        )[:20]],
    }


@app.get("/api/v1/charts")
def charts(
    hours: int = 168,
    from_ts: int | None = None,
    to_ts: int | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> dict[str, Any]:
    """Time-series for dashboard charts (calls, chats, quality, won)."""
    from storage import db, init_db

    init_db()
    start, end = _period_bounds(hours, from_ts, to_ts, from_date, to_date)
    hours = max(1, int(round((end - start) / 3600)))
    day = 86400
    labels: list[str] = []
    calls: list[int] = []
    chats: list[int] = []
    quality: list[float | None] = []
    won: list[int] = []
    lost: list[int] = []

    with db() as conn:
        # pre-aggregate by day buckets
        comm = conn.execute(
            """
            SELECT CAST((created_at - ?) / ? AS INTEGER) AS bucket,
                   kind, COUNT(*) AS cnt
            FROM communications
            WHERE created_at >= ? AND created_at < ?
            GROUP BY bucket, kind
            """,
            (start, day, start, end),
        ).fetchall()
        ana = conn.execute(
            """
            SELECT CAST((c.created_at - ?) / ? AS INTEGER) AS bucket,
                   AVG(a.score) AS avg_score, COUNT(*) AS n
            FROM analyses a
            JOIN communications c ON c.id = a.communication_id
            WHERE c.created_at >= ? AND c.created_at < ?
            GROUP BY bucket
            """,
            (start, day, start, end),
        ).fetchall()
        leads = conn.execute(
            """
            SELECT CAST((COALESCE(closed_at, updated_at) - ?) / ? AS INTEGER) AS bucket,
                   SUM(CASE WHEN is_won = 1 THEN 1 ELSE 0 END) AS won,
                   SUM(CASE WHEN is_lost = 1 THEN 1 ELSE 0 END) AS lost
            FROM lead_snapshots
            WHERE COALESCE(closed_at, updated_at) >= ? AND COALESCE(closed_at, updated_at) < ?
            GROUP BY bucket
            """,
            (start, day, start, end),
        ).fetchall()

    n_days = max(1, (end - start + day - 1) // day)
    by_comm: dict[int, dict[str, int]] = {}
    for r in comm:
        b = int(r["bucket"] or 0)
        by_comm.setdefault(b, {"call": 0, "chat": 0, "note": 0})
        k = r["kind"] or "note"
        if k == "call":
            by_comm[b]["call"] += int(r["cnt"] or 0)
        elif k in ("chat", "sms"):
            by_comm[b]["chat"] += int(r["cnt"] or 0)
        else:
            by_comm[b]["note"] += int(r["cnt"] or 0)
    by_q = {int(r["bucket"] or 0): float(r["avg_score"]) for r in ana if r["avg_score"] is not None}
    by_l = {
        int(r["bucket"] or 0): (int(r["won"] or 0), int(r["lost"] or 0)) for r in leads
    }

    import datetime as _dt

    for b in range(n_days):
        ts = start + b * day
        labels.append(
            _dt.datetime.fromtimestamp(ts).strftime("%d.%m")
        )
        c = by_comm.get(b, {})
        calls.append(int(c.get("call") or 0))
        chats.append(int(c.get("chat") or 0))
        quality.append(round(by_q[b], 2) if b in by_q else None)
        w, l = by_l.get(b, (0, 0))
        won.append(w)
        lost.append(l)

    # manager quality bars
    pack = period_stats(start, end)
    mgrs = []
    for m in pack.get("managers") or []:
        if (m.get("calls_total") or 0) + (m.get("chats_total") or 0) <= 0:
            continue
        mgrs.append(
            {
                "name": m.get("name") or "—",
                "calls": m.get("calls_total") or 0,
                "chats": m.get("chats_total") or 0,
                "quality": m.get("avg_quality_score"),
                "won": m.get("leads_won") or 0,
            }
        )
    mgrs.sort(key=lambda x: -(x["calls"] + x["chats"]))

    return {
        "ok": True,
        "hours": hours,
        "labels": labels,
        "series": {
            "calls": calls,
            "chats": chats,
            "quality": quality,
            "won": won,
            "lost": lost,
        },
        "managers": mgrs[:12],
        "totals": (pack.get("totals") or {}),
    }


def _resolve_comm_audio_row(conn, comm_id: str):
    """Find communications row by exact id or note:leads: / trailing-digit variants."""
    from urllib.parse import unquote

    cid = unquote(str(comm_id or "").strip())
    if not cid:
        return None
    row = conn.execute(
        "SELECT id, recording_url FROM communications WHERE id = ?",
        (cid,),
    ).fetchone()
    if row and (row["recording_url"] or "").strip():
        return row
    # bare numeric note id from amo → local collector id
    digits = cid
    if ":" in cid:
        tail = cid.rsplit(":", 1)[-1]
        if tail.isdigit():
            digits = tail
    if digits.isdigit():
        for cand in (
            f"note:leads:{digits}",
            f"note:{digits}",
            f"call:{digits}",
            digits,
        ):
            row = conn.execute(
                "SELECT id, recording_url FROM communications WHERE id = ?",
                (cand,),
            ).fetchone()
            if row and (row["recording_url"] or "").strip():
                return row
        row = conn.execute(
            """
            SELECT id, recording_url FROM communications
            WHERE id LIKE ? AND recording_url IS NOT NULL AND recording_url != ''
            ORDER BY created_at DESC LIMIT 1
            """,
            (f"%:{digits}",),
        ).fetchone()
        if row:
            return row
    # last resort: exact row even without recording (caller will 404)
    return conn.execute(
        "SELECT id, recording_url FROM communications WHERE id = ?",
        (cid,),
    ).fetchone()


@app.get("/api/v1/audio/{comm_id:path}")
def stream_audio(comm_id: str):
    """Stream call recording: serve local cache or download from CRM URL."""
    from fastapi.responses import FileResponse
    from storage import db, init_db
    from transcriber import download_recording

    init_db()
    with db() as conn:
        row = _resolve_comm_audio_row(conn, comm_id)
    if not row:
        raise HTTPException(404, "communication not found")
    url = (row["recording_url"] or "").strip()
    if not url:
        raise HTTPException(404, "no recording_url")

    path = download_recording(url, str(row["id"]))
    if not path or not path.exists():
        # proxy redirect if download failed but URL is public https
        if url.startswith("https://"):
            from fastapi.responses import RedirectResponse

            return RedirectResponse(url=url)
        raise HTTPException(404, "audio unavailable")

    media = "audio/mpeg"
    suf = path.suffix.lower()
    if suf == ".wav":
        media = "audio/wav"
    elif suf == ".ogg":
        media = "audio/ogg"
    elif suf in (".m4a", ".mp4"):
        media = "audio/mp4"
    return FileResponse(
        path,
        media_type=media,
        filename=path.name,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@app.get("/api/v1/leads/{lead_id}/conversation")
def lead_conversation(lead_id: int) -> dict[str, Any]:
    """Calls + chats for a lead with full transcript and audio links."""
    try:
        from assistant_service import build_assistant_payload

        pack = build_assistant_payload(
            lead_id=lead_id, write_note=False, live_stt=False
        )
        return {
            "ok": True,
            "lead": pack.get("lead"),
            "stats": pack.get("stats"),
            "conversation": pack.get("conversation") or [],
            "history_preview": pack.get("history_preview") or [],
        }
    except Exception as e:
        logger.exception("conversation")
        raise HTTPException(500, str(e)) from e


@app.get("/api/v1/leads/recent")
def leads_recent(limit: int = 40, hours: int = 72) -> dict[str, Any]:
    """Recent active leads for desktop app."""
    from storage import db, manager_name_map

    init_db()
    names = manager_name_map()
    since = int(time.time()) - max(1, hours) * 3600
    with db() as conn:
        rows = conn.execute(
            """
            SELECT lead_id, name, price, status_id, pipeline_id, responsible_user_id,
                   created_at, updated_at, is_won, is_lost
            FROM lead_snapshots
            WHERE updated_at >= ? OR created_at >= ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (since, since, min(limit, 100)),
        ).fetchall()
        # transcript / call / recording counts
        media: dict[Any, dict[str, int]] = {}
        try:
            for r in conn.execute(
                """
                SELECT lead_id,
                       SUM(CASE WHEN transcript IS NOT NULL
                                 AND LENGTH(TRIM(transcript)) > 10
                            THEN 1 ELSE 0 END) AS transcripts,
                       SUM(CASE WHEN kind = 'call' THEN 1 ELSE 0 END) AS calls,
                       SUM(CASE WHEN recording_url IS NOT NULL
                                 AND recording_url != ''
                            THEN 1 ELSE 0 END) AS recordings
                FROM communications
                WHERE lead_id IS NOT NULL
                GROUP BY lead_id
                """
            ).fetchall():
                media[r["lead_id"]] = {
                    "transcripts": int(r["transcripts"] or 0),
                    "calls": int(r["calls"] or 0),
                    "recordings": int(r["recordings"] or 0),
                }
        except Exception:
            pass

    items = []
    for r in rows:
        rid = r["lead_id"]
        m = media.get(rid, {})
        items.append(
            {
                "id": rid,
                "name": r["name"] or f"#{rid}",
                "price": r["price"],
                "status_id": r["status_id"],
                "pipeline_id": r["pipeline_id"],
                "responsible_user_id": r["responsible_user_id"],
                "responsible_name": names.get(r["responsible_user_id"] or 0, "—"),
                "updated_at": r["updated_at"],
                "is_won": bool(r["is_won"]),
                "is_lost": bool(r["is_lost"]),
                "transcripts": m.get("transcripts", 0),
                "calls": m.get("calls", 0),
                "recordings": m.get("recordings", 0),
                "url": f"https://kuhhospital.amocrm.ru/leads/detail/{rid}",
            }
        )
    # Prefer leads that already have audio/transcripts at top of useful filters
    return {"ok": True, "leads": items, "source": "cache"}


@app.get("/api/v1/managers")
def managers_list() -> dict[str, Any]:
    from storage import list_managers

    init_db()
    return {
        "ok": True,
        "managers": [
            {"id": m["id"], "name": m["name"], "email": m.get("email")}
            for m in list_managers(active_only=True)
        ],
    }


# ---------- Multi-CRM profiles ----------


class ProfileBody(BaseModel):
    id: str | None = None
    provider: str = "amocrm"
    label: str = "Default"
    subdomain: str = ""
    long_lived_token: str = ""
    client_id: str = ""
    client_secret: str = ""
    refresh_token: str = ""
    redirect_uri: str = "https://example.com"
    webhook_url: str = ""
    base_url: str = ""
    api_token: str = ""
    set_active: bool = True


@app.get("/api/v1/crm/providers")
def crm_providers() -> dict[str, Any]:
    from crm.registry import list_providers

    return {"ok": True, "providers": list_providers()}


@app.get("/api/v1/crm/profiles")
def crm_profiles() -> dict[str, Any]:
    from profiles import get_profile, list_profiles, load_store

    store = load_store()
    return {
        "ok": True,
        "active_id": store.get("active_id"),
        "profiles": list_profiles(),
        "active": get_profile(),
    }


@app.post("/api/v1/crm/profiles")
def crm_profiles_save(body: ProfileBody) -> dict[str, Any]:
    from profiles import set_active, upsert_profile

    pid = upsert_profile(body.model_dump())
    if body.set_active:
        set_active(pid)
    return {"ok": True, "id": pid}


@app.post("/api/v1/crm/profiles/{profile_id}/activate")
def crm_profile_activate(profile_id: str) -> dict[str, Any]:
    from profiles import get_profile, set_active

    set_active(profile_id)
    # Keep process + AppData .env in sync so collector/worker pick up keys
    try:
        import os
        from pathlib import Path

        p = get_profile(profile_id) or {}
        if p.get("subdomain"):
            os.environ["AMO_SUBDOMAIN"] = str(p["subdomain"])
        if p.get("long_lived_token"):
            os.environ["AMO_LONG_LIVED_TOKEN"] = str(p["long_lived_token"])
        if p.get("client_id"):
            os.environ["AMO_CLIENT_ID"] = str(p["client_id"])
        if p.get("client_secret"):
            os.environ["AMO_CLIENT_SECRET"] = str(p["client_secret"])
        if p.get("refresh_token"):
            os.environ["AMO_REFRESH_TOKEN"] = str(p["refresh_token"])
        app_env = (
            Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
            / "CRMAIDesk"
            / ".env"
        )
        lines = [
            f"AMO_SUBDOMAIN={p.get('subdomain') or ''}",
            f"AMO_CLIENT_ID={p.get('client_id') or ''}",
            f"AMO_CLIENT_SECRET={p.get('client_secret') or ''}",
            f"AMO_REDIRECT_URI={p.get('redirect_uri') or 'https://example.com'}",
            f"AMO_REFRESH_TOKEN={p.get('refresh_token') or ''}",
            f"AMO_LONG_LIVED_TOKEN={p.get('long_lived_token') or ''}",
            "WRITE_AMO_CALL_NOTES=1",
        ]
        app_env.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:
        pass
    return {"ok": True, "active_id": profile_id}


@app.delete("/api/v1/crm/profiles/{profile_id}")
def crm_profile_delete(profile_id: str) -> dict[str, Any]:
    from profiles import delete_profile

    delete_profile(profile_id)
    return {"ok": True}


@app.post("/api/v1/crm/test")
def crm_test(body: ProfileBody) -> dict[str, Any]:
    from crm.base import CrmCredentials
    from crm.registry import get_adapter

    try:
        adapter = get_adapter(CrmCredentials.from_dict(body.model_dump()))
        return {"ok": True, "result": adapter.test_connection()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _local_lead_media_counts(lead_ids: list[Any]) -> dict[str, dict[str, int]]:
    """transcript / call / recording counts from local DB for CRM lead list."""
    from storage import db, init_db

    init_db()
    out: dict[str, dict[str, int]] = {}
    ids: list[int] = []
    for lid in lead_ids:
        try:
            ids.append(int(lid))
        except (TypeError, ValueError):
            continue
    if not ids:
        return out
    placeholders = ",".join("?" * len(ids))
    with db() as conn:
        rows = conn.execute(
            f"""
            SELECT lead_id,
                   SUM(CASE WHEN transcript IS NOT NULL AND length(transcript) > 10
                            THEN 1 ELSE 0 END) AS transcripts,
                   SUM(CASE WHEN kind = 'call' THEN 1 ELSE 0 END) AS calls,
                   SUM(CASE WHEN recording_url IS NOT NULL AND recording_url != ''
                            THEN 1 ELSE 0 END) AS recordings
            FROM communications
            WHERE lead_id IN ({placeholders})
            GROUP BY lead_id
            """,
            ids,
        ).fetchall()
    for r in rows:
        out[str(r["lead_id"])] = {
            "transcripts": int(r["transcripts"] or 0),
            "calls": int(r["calls"] or 0),
            "recordings": int(r["recordings"] or 0),
        }
    return out


@app.get("/api/v1/crm/leads")
def crm_leads(hours: int = 72, limit: int = 40) -> dict[str, Any]:
    """Leads from active CRM profile (multi-CRM)."""
    from crm.registry import get_adapter
    from profiles import get_credentials, import_from_env

    creds = get_credentials()
    if not creds:
        import_from_env()
        creds = get_credentials()
    if not creds:
        # fallback to local SQLite cache
        return leads_recent(limit=limit, hours=hours)
    try:
        adapter = get_adapter(creds)
        leads = adapter.list_recent_leads(hours=hours, limit=limit)
        media = _local_lead_media_counts([x.id for x in leads])
        packed = []
        for x in leads:
            m = media.get(str(x.id), {})
            packed.append(
                {
                    "id": x.id,
                    "name": x.name,
                    "price": x.price,
                    "status_id": x.status_id,
                    "status_name": x.status_name,
                    "responsible_user_id": x.responsible_id,
                    "responsible_name": x.responsible_name,
                    "updated_at": x.updated_at,
                    "is_won": x.is_won,
                    "is_lost": x.is_lost,
                    "transcripts": m.get("transcripts", 0),
                    "calls": m.get("calls", 0),
                    "recordings": m.get("recordings", 0),
                    "url": x.url,
                }
            )
        return {
            "ok": True,
            "provider": creds.provider,
            "label": creds.label,
            "leads": packed,
        }
    except Exception as e:
        logger.exception("crm_leads failed")
        # fallback cache
        try:
            cached = leads_recent(limit=limit, hours=hours)
            cached["warning"] = str(e)
            return cached
        except Exception:
            raise HTTPException(500, str(e)) from e


# ---------- Virtual ROP (AI supervisor) ----------


class ScoreTextBody(BaseModel):
    text: str = Field(..., min_length=1)


@app.get("/api/v1/rop/control")
def rop_control(hours: int = 24) -> dict[str, Any]:
    """Full virtual-ROP control pack: alerts, queue, ranking, scorecards."""
    try:
        from rop_control import build_control_pack

        return build_control_pack(hours=max(1, min(hours, 168)))
    except Exception as e:
        logger.exception("rop_control failed")
        raise HTTPException(500, str(e)) from e


@app.get("/api/v1/rop/scripts")
def rop_scripts(service: str = "default") -> dict[str, Any]:
    from rop_control import SERVICE_SCRIPTS, get_script

    return {
        "ok": True,
        "service": service,
        "script": get_script(service),
        "catalog": {k: v.get("title") for k, v in SERVICE_SCRIPTS.items()},
    }


@app.get("/api/v1/rop/trainer")
def rop_trainer() -> dict[str, Any]:
    from rop_control import get_trainer

    return {"ok": True, "scenarios": get_trainer()}


@app.post("/api/v1/rop/scorecard")
def rop_scorecard(body: ScoreTextBody) -> dict[str, Any]:
    from rop_control import score_text_endpoint

    return score_text_endpoint(body.text)


@app.get("/api/v1/rop/export")
def rop_export(hours: int = 24) -> dict[str, Any]:
    from rop_control import export_control_excel

    path = export_control_excel(hours=max(1, min(hours, 168)))
    return {
        "ok": True,
        "path": str(path),
        "folder": str(path.parent),
        "filename": path.name,
    }


@app.get("/api/v1/crm/assist/{lead_id}")
def crm_assist(lead_id: str, write_note: bool = True) -> dict[str, Any]:
    """Assistant for active CRM lead. write_note=1 (default) posts AI advice into amo deal."""
    from assistant_service import build_assistant_payload
    from crm.registry import get_adapter
    from profiles import get_credentials, import_from_env

    creds = get_credentials()
    if not creds:
        import_from_env()
        creds = get_credentials()

    # amoCRM path with full STT/history when possible
    if not creds or creds.provider in ("amocrm", "kommo", ""):
        try:
            return build_assistant_payload(
                lead_id=int(lead_id),
                write_note=bool(write_note),
                live_stt=False,
            )
        except Exception as e:
            if not creds:
                raise HTTPException(500, str(e)) from e

    # Generic CRM: notes → bilingual coach
    from assistant_service import _ai_coach, _heuristic_coach

    assert creds is not None
    adapter = get_adapter(creds)
    lead = adapter.get_lead(lead_id)
    notes = adapter.get_lead_notes(lead_id)
    history_parts = []
    for n in reversed(notes):
        t = (n.text or "").strip()
        if t:
            history_parts.append(f"[{n.kind}] {t[:2000]}")
    history = "\n\n".join(history_parts)
    meta = f"crm={creds.provider}; lead={lead_id}; name={lead.name if lead else ''}"
    from assistant_service import _format_note

    coach = _ai_coach(history, meta) if history else None
    if not coach:
        coach = _heuristic_coach(history, {"name": lead.name if lead else lead_id})
    quality = {
        "score": coach.get("score"),
        "summary": coach.get("summary"),
        "model": coach.get("model"),
    }
    note_text = _format_note(coach, quality)
    note_written = False
    note_error = None
    if write_note:
        try:
            # generic adapters may not have note write — try amo client for amocrm-like
            if creds.provider in ("amocrm", "kommo"):
                AmoCRMClient().add_note_to_lead(int(lead_id), note_text)
                note_written = True
            elif hasattr(adapter, "add_note"):
                adapter.add_note(lead_id, note_text)
                note_written = True
        except Exception as e:
            note_error = str(e)[:240]
            logger.warning("crm_assist write_note failed: %s", e)
    return {
        "ok": True,
        "provider": creds.provider,
        "lead": {
            "id": lead_id,
            "name": lead.name if lead else lead_id,
            "responsible_name": lead.responsible_name if lead else "",
            "status_name": lead.status_name if lead else "",
            "price": lead.price if lead else 0,
            "url": lead.url if lead else "",
        },
        "stats": {"notes": len(notes), "calls": sum(1 for n in notes if n.kind == "call"), "transcripts": 0},
        "history_preview": [
            {"kind": n.kind, "text": (n.text or "")[:200], "has_recording": bool(n.recording_url)}
            for n in notes[:10]
        ],
        "coach": coach,
        "quality": quality,
        "note_markdown": note_text,
        "note_written": note_written,
        "note_error": note_error,
    }


@app.post("/webhook/amocrm")
async def amocrm_webhook(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        payload = await request.json()
    else:
        form = await request.form()
        payload = dict(form)
    logger.info("Webhook keys=%s", list(payload.keys())[:15] if isinstance(payload, dict) else type(payload))
    try:
        stats = Collector().run_once(lookback_hours=6)
        analyzed = analyze_batch(limit=8)
        return {"ok": True, "stats": stats, "analyzed": analyzed}
    except Exception as exc:
        logger.exception("webhook failed")
        return {"ok": False, "error": str(exc)}


# Serve widget zip / public assets
if PUBLIC_DIR.exists():
    app.mount("/public", StaticFiles(directory=str(PUBLIC_DIR)), name="public")

# Desktop UI over HTTP (avoids file:// offline issues in WebView)
if DESKTOP_UI_DIR.exists():
    # No browser/WebView cache for UI assets during iteration
    class NoCacheStatic(StaticFiles):
        def is_not_modified(self, *args, **kwargs) -> bool:  # type: ignore[override]
            return False

        async def get_response(self, path, scope):
            resp = await super().get_response(path, scope)
            resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            resp.headers["Pragma"] = "no-cache"
            return resp

    app.mount(
        "/app",
        NoCacheStatic(directory=str(DESKTOP_UI_DIR), html=True),
        name="desktop_ui",
    )


@app.get("/")
def root_redirect():
    from fastapi.responses import RedirectResponse

    if DESKTOP_UI_DIR.exists():
        return RedirectResponse(url="/app/")
    return {"ok": True, "docs": "/docs"}


# ---------- Табель (employee timesheet widget) ----------


class TabelHeartbeatBody(BaseModel):
    user_id: int
    active: bool = False
    buckets: list[int] = Field(default_factory=list)


class TabelStatusBody(BaseModel):
    user_id: int
    status: str = ""
    actor_id: int | None = None


class TabelStatusCatalogBody(BaseModel):
    name: str = Field(..., min_length=1)
    color: str = "#6b7280"


class TabelAclBody(BaseModel):
    allowed_users: str | None = None
    list_users: str | None = None


@app.get("/api/v1/tabel/acl")
def tabel_acl_get() -> dict[str, Any]:
    from tabel_service import load_tabel_acl

    return {"ok": True, **load_tabel_acl()}


@app.post("/api/v1/tabel/acl")
def tabel_acl_set(body: TabelAclBody) -> dict[str, Any]:
    from tabel_service import save_tabel_acl

    saved = save_tabel_acl(
        allowed_users=body.allowed_users,
        list_users=body.list_users,
    )
    return {"ok": True, **saved}


@app.get("/api/v1/tabel/state")
def tabel_state(
    user_id: int | None = None,
    period: str = "today",
    from_ts: int | None = None,
    to_ts: int | None = None,
) -> dict[str, Any]:
    from tabel_service import build_state

    try:
        return build_state(
            me_id=user_id,
            period=period,
            from_ts=from_ts,
            to_ts=to_ts,
        )
    except Exception as exc:
        logger.exception("tabel_state failed, falling back to activity snapshot")
        from tabel_service import activity_snapshot

        return activity_snapshot(
            me_id=user_id,
            period=period,
            from_ts=from_ts,
            to_ts=to_ts,
        )


@app.get("/api/v1/tabel/activity")
def tabel_activity(
    user_id: int | None = None,
    period: str = "today",
    from_ts: int | None = None,
    to_ts: int | None = None,
) -> dict[str, Any]:
    from tabel_service import activity_snapshot

    return activity_snapshot(
        me_id=user_id,
        period=period,
        from_ts=from_ts,
        to_ts=to_ts,
    )


@app.post("/api/v1/tabel/heartbeat")
def tabel_heartbeat(body: TabelHeartbeatBody) -> dict[str, Any]:
    from tabel_service import heartbeat

    try:
        return heartbeat(
            user_id=int(body.user_id),
            active=bool(body.active),
            buckets=list(body.buckets or []),
        )
    except Exception as exc:
        logger.exception("tabel_heartbeat failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/v1/tabel/status")
def tabel_set_status(body: TabelStatusBody) -> dict[str, Any]:
    from tabel_service import set_user_status

    try:
        return set_user_status(
            user_id=int(body.user_id),
            status_code=body.status or "",
            actor_id=body.actor_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("tabel_set_status failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/v1/tabel/statuses")
def tabel_statuses_get() -> dict[str, Any]:
    from tabel_service import load_statuses

    return {"ok": True, "statuses": load_statuses()}


@app.post("/api/v1/tabel/statuses")
def tabel_statuses_add(body: TabelStatusCatalogBody) -> dict[str, Any]:
    from tabel_service import add_status

    try:
        items = add_status(body.name, body.color)
        return {"ok": True, "statuses": items}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/v1/tabel/statuses/{code}")
def tabel_statuses_delete(code: str) -> dict[str, Any]:
    from tabel_service import remove_status

    items = remove_status(code)
    return {"ok": True, "statuses": items}


@app.get("/widget/package.zip")
def download_widget_zip():
    zip_path = PUBLIC_DIR / "kuh-assistant-widget.zip"
    if not zip_path.exists():
        raise HTTPException(404, "Widget zip not built yet. Run: python build_widget.py")
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename="kuh-assistant-widget.zip",
    )


@app.get("/widget/tabel.zip")
def download_tabel_widget_zip():
    zip_path = PUBLIC_DIR / "tabel-widget.zip"
    if not zip_path.exists():
        raise HTTPException(404, "Widget zip not built yet. Run: python build_tabel_widget.py")
    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename="tabel-widget.zip",
    )
