"""Post AI call coaching notes into amoCRM deal cards."""

from __future__ import annotations

import logging
import time
from typing import Any

from storage import db, init_db

logger = logging.getLogger(__name__)


def _client_class():
    from amocrm_client import AmoCRMClient

    return AmoCRMClient


def _ensure_columns() -> None:
    init_db()
    with db() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(communications)").fetchall()}
        if "note_posted_at" not in cols:
            conn.execute(
                "ALTER TABLE communications ADD COLUMN note_posted_at INTEGER"
            )
        if "note_post_error" not in cols:
            conn.execute(
                "ALTER TABLE communications ADD COLUMN note_post_error TEXT"
            )


def _clean_bilingual(text: str) -> tuple[str, str]:
    """Split packed 🇷🇺/🇺🇿 text into two plain lines."""
    raw = (text or "").strip()
    if not raw or raw == "—":
        return "—", "—"
    ru, uz = raw, ""
    if "🇷🇺" in raw or "🇺🇿" in raw:
        parts = raw.replace("\r", "").split("\n")
        ru_parts, uz_parts = [], []
        for p in parts:
            p = p.strip()
            if p.startswith("🇷🇺"):
                ru_parts.append(p.replace("🇷🇺", "").strip())
            elif p.startswith("🇺🇿"):
                uz_parts.append(p.replace("🇺🇿", "").strip())
            else:
                ru_parts.append(p)
        ru = " ".join(ru_parts).strip() or "—"
        uz = " ".join(uz_parts).strip() or "—"
    return ru, uz


def _score_label(score: float | None) -> str:
    try:
        s = float(score)
    except (TypeError, ValueError):
        return "нет оценки"
    if s >= 8:
        return "отлично"
    if s >= 6.5:
        return "хорошо"
    if s >= 5:
        return "средне"
    if s >= 3.5:
        return "слабо"
    return "плохо — нужен разбор"


def _booking_label(code: str | None) -> tuple[str, str]:
    m = {
        "booked": ("✅ Запись состоялась", "✅ Yozuv bo'ldi"),
        "promised_callback": ("📞 Обещан перезвон/слот", "📞 Qayta qo'ng'iroq/slot"),
        "no_commitment": ("⚠ Без договорённости", "⚠ Kelishuv yo'q"),
        "rejected": ("✖ Отказ клиента", "✖ Mijoz rad etdi"),
        "unclear": ("? Итог неясен", "? Natija noaniq"),
    }
    return m.get(code or "", ("? Итог неясен", "? Natija noaniq"))


def format_call_note(
    *,
    analysis: dict[str, Any],
    duration: int | None = None,
    direction: str | None = None,
    phone: str | None = None,
    comm_id: str = "",
) -> str:
    """Clear manager-facing note — RU + UZ, actionable, no jargon."""
    score = analysis.get("score")
    try:
        score_f = float(score) if score is not None else None
    except (TypeError, ValueError):
        score_f = None

    summary_ru, summary_uz = _clean_bilingual(str(analysis.get("summary") or ""))
    good_ru, good_uz = _clean_bilingual(str(analysis.get("strengths") or ""))
    bad_ru, bad_uz = _clean_bilingual(str(analysis.get("weaknesses") or ""))
    advice_ru, advice_uz = _clean_bilingual(str(analysis.get("advice") or ""))
    reply_ru, reply_uz = _clean_bilingual(str(analysis.get("suggested_reply") or ""))
    need_ru, need_uz = _clean_bilingual(str(analysis.get("client_need") or ""))

    dir_ru = {"in": "входящий", "out": "исходящий"}.get(direction or "", "звонок")
    dur = f"{int(duration)} сек." if duration else "—"
    score_txt = f"{score_f}/10" if score_f is not None else "—"
    label = _score_label(score_f)
    book_ru, book_uz = _booking_label(analysis.get("booking_result"))

    # Visual score bar for managers
    if score_f is not None:
        filled = max(0, min(10, int(round(score_f))))
        bar = "●" * filled + "○" * (10 - filled)
    else:
        bar = "—"

    lines = [
        "━━━━━━━━━━━━━━━━━━━━",
        "📞 РАЗБОР ЗВОНКА · AI-помощник",
        "Qo'ng'iroq tahlili · AI",
        "━━━━━━━━━━━━━━━━━━━━",
        "",
        f"⭐ {score_txt}  ({label})",
        f"   {bar}",
        f"Тип: {dir_ru} · {dur}",
        f"Итог: {book_ru}",
        f"Natija: {book_uz}",
    ]
    if phone:
        lines.append(f"Тел: {phone}")

    if need_ru and need_ru != "—":
        lines += [
            "",
            "——— ЧТО НУЖНО КЛИЕНТУ ———",
            f"🇷🇺 {need_ru}",
            f"🇺🇿 {need_uz}",
        ]

    lines += [
        "",
        "——— ЧТО БЫЛО ———",
        f"🇷🇺 {summary_ru}",
        f"🇺🇿 {summary_uz}",
        "",
        "——— ✅ ХОРОШО ———",
        f"🇷🇺 {good_ru}",
        f"🇺🇿 {good_uz}",
        "",
        "——— ⬆ УЛУЧШИТЬ ———",
        f"🇷🇺 {bad_ru}",
        f"🇺🇿 {bad_uz}",
        "",
        "——— 🎯 СДЕЛАТЬ ДАЛЬШЕ ———",
        f"🇷🇺 {advice_ru}",
        f"🇺🇿 {advice_uz}",
    ]

    if reply_ru and reply_ru != "—":
        lines += [
            "",
            "——— 💬 СКАЗАТЬ КЛИЕНТУ ———",
            f"🇷🇺 {reply_ru}",
        ]
        if reply_uz and reply_uz != "—":
            lines.append(f"🇺🇿 {reply_uz}")

    quote = (analysis.get("transcript_quote") or "").strip()
    if quote and len(quote) > 15:
        lines += ["", "——— ЦИТАТА ———", f"«{_snip_note(quote)}»"]

    flags = analysis.get("flags") or []
    if flags:
        nice = [f for f in flags if f not in ("has_speakers", "too_short")][:6]
        if nice:
            lines += ["", f"Метки: {', '.join(nice)}"]

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━",
        "Авто · CRM AI Desk · не диагноз",
        "━━━━━━━━━━━━━━━━━━━━",
    ]
    text = "\n".join(lines)
    if len(text) > 9500:
        text = text[:9400] + "\n…"
    return text


def _snip_note(s: str, n: int = 160) -> str:
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def pending_note_posts(limit: int = 25) -> list[dict[str, Any]]:
    """Calls with analysis + transcript, not yet posted to amo, with lead_id."""
    _ensure_columns()
    with db() as conn:
        rows = conn.execute(
            """
            SELECT c.*, a.score, a.summary, a.strengths, a.weaknesses,
                   a.advice, a.sentiment, a.flags_json, a.model
            FROM communications c
            JOIN analyses a ON a.communication_id = c.id
            WHERE c.kind = 'call'
              AND c.lead_id IS NOT NULL AND c.lead_id > 0
              AND c.analyzed = 1
              AND (c.note_posted_at IS NULL OR c.note_posted_at = 0)
              AND (
                    (c.transcript IS NOT NULL AND LENGTH(TRIM(c.transcript)) > 40)
                 OR (c.text IS NOT NULL AND LENGTH(TRIM(c.text)) > 60
                     AND c.text NOT LIKE '[%' AND c.text NOT LIKE 'phone=%')
              )
            ORDER BY c.created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def mark_posted(comm_id: str, ok: bool = True, error: str = "") -> None:
    _ensure_columns()
    with db() as conn:
        if ok:
            conn.execute(
                """
                UPDATE communications
                SET note_posted_at = ?, note_post_error = NULL
                WHERE id = ?
                """,
                (int(time.time()), comm_id),
            )
        else:
            conn.execute(
                """
                UPDATE communications
                SET note_post_error = ?
                WHERE id = ?
                """,
                ((error or "error")[:500], comm_id),
            )


def post_one(comm: dict[str, Any], client: Any | None = None) -> bool:
    lead_id = comm.get("lead_id")
    if not lead_id:
        return False
    analysis = {
        "score": comm.get("score"),
        "summary": comm.get("summary"),
        "strengths": comm.get("strengths"),
        "weaknesses": comm.get("weaknesses"),
        "advice": comm.get("advice"),
        "sentiment": comm.get("sentiment"),
        "model": comm.get("model"),
        "flags": [],
        "suggested_reply": comm.get("_suggested_reply") or comm.get("suggested_reply") or "",
        "client_need": comm.get("client_need") or "",
        "booking_result": comm.get("booking_result") or "unclear",
        "transcript_quote": comm.get("transcript_quote") or "",
    }
    try:
        import json

        flags = comm.get("flags_json")
        if flags:
            analysis["flags"] = json.loads(flags) if isinstance(flags, str) else flags
    except Exception:
        pass

    note = format_call_note(
        analysis=analysis,
        duration=comm.get("duration"),
        direction=comm.get("direction"),
        phone=comm.get("phone"),
        comm_id=str(comm.get("id") or ""),
    )
    try:
        cli = client or _client_class()()
        cli.add_note_to_lead(int(lead_id), note)
        mark_posted(str(comm["id"]), ok=True)
        logger.info("Posted AI note to lead %s for %s", lead_id, comm.get("id"))
        return True
    except Exception as e:
        logger.error("Post note fail lead=%s: %s", lead_id, e)
        mark_posted(str(comm["id"]), ok=False, error=str(e))
        return False


def post_pending_notes(limit: int = 20) -> dict[str, int]:
    """Post all pending call analyses into amoCRM deals."""
    items = pending_note_posts(limit=limit)
    ok = fail = 0
    client = None
    try:
        client = _client_class()()
    except Exception as e:
        logger.error("Amo client init: %s", e)
        return {"queued": len(items), "ok": 0, "fail": len(items)}

    for comm in items:
        if post_one(comm, client=client):
            ok += 1
        else:
            fail += 1
        time.sleep(0.25)  # gentle rate limit
    return {"queued": len(items), "ok": ok, "fail": fail}


def post_after_analysis(comm: dict[str, Any], analysis: dict[str, Any]) -> bool:
    """Call right after analyze_one for a single communication."""
    try:
        from config import WRITE_AMO_CALL_NOTES

        if not WRITE_AMO_CALL_NOTES:
            return False
    except Exception:
        pass
    if (comm.get("kind") or "") != "call":
        return False
    lead_id = comm.get("lead_id")
    if not lead_id:
        return False
    text = (comm.get("transcript") or comm.get("text") or "").strip()
    if len(text) < 40 or text.startswith("["):
        return False
    # skip if already posted
    _ensure_columns()
    with db() as conn:
        row = conn.execute(
            "SELECT note_posted_at FROM communications WHERE id = ?",
            (comm["id"],),
        ).fetchone()
        if row and row["note_posted_at"]:
            return False

    payload = dict(comm)
    payload.update(
        {
            "score": analysis.get("score"),
            "summary": analysis.get("summary"),
            "strengths": analysis.get("strengths"),
            "weaknesses": analysis.get("weaknesses"),
            "advice": analysis.get("advice"),
            "sentiment": analysis.get("sentiment"),
            "model": analysis.get("model"),
            "client_need": analysis.get("client_need") or "",
            "booking_result": analysis.get("booking_result") or "unclear",
            "transcript_quote": analysis.get("transcript_quote") or "",
            "flags_json": __import__("json").dumps(
                analysis.get("flags") or [], ensure_ascii=False
            ),
        }
    )
    if analysis.get("suggested_reply"):
        payload["_suggested_reply"] = analysis.get("suggested_reply")
    return post_one(payload)
