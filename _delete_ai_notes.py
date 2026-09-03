"""
Remove AI coaching notes from amoCRM deal cards.

amoCRM public API v4 does NOT support DELETE for notes (HTTP 405).
We clear note text via PATCH so managers no longer see AI content.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from amocrm_client import AmoCRMClient
from storage import db, init_db

MARKERS = (
    "РАЗБОР ЗВОНКА",
    "CRM AI Desk",
    "Qo'ng'iroq tahlili",
    "AI-помощник",
    "AI-yordamchi",
    "AI-разбор",
    "Авто · CRM AI Desk",
    "Автоматически · CRM AI Desk",
    "heuristic-v",
    "medical-heuristic",
    "Baholash:",
    "AI qo'ng'iroq",
    "[удалено]",  # re-clean if partial
)


def is_ai_note(text: str) -> bool:
    t = text or ""
    if t.strip() in ("", "—", "·", ".", "[удалено]"):
        return False  # already empty / not AI content of interest for re-scan skip
    return any(m in t for m in MARKERS)


def main() -> None:
    client = AmoCRMClient()
    init_db()

    with db() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT lead_id FROM communications
            WHERE lead_id IS NOT NULL AND lead_id > 0
              AND (
                (note_posted_at IS NOT NULL AND note_posted_at > 0)
                OR note_post_error LIKE 'cleared%'
                OR note_post_error LIKE '%post%'
              )
            """
        ).fetchall()
        # also any lead that ever had call analysis with lead_id
        rows2 = conn.execute(
            """
            SELECT DISTINCT lead_id FROM communications
            WHERE kind='call' AND lead_id IS NOT NULL AND lead_id > 0
              AND analyzed = 1
            """
        ).fetchall()

    lead_ids = {int(r["lead_id"]) for r in rows} | {int(r["lead_id"]) for r in rows2}

    now = int(time.time())
    since = now - 21 * 86400
    print("Scanning global common notes for AI markers…")
    try:
        page = 1
        while page <= 50:
            batch = client.get_notes(
                "leads",
                note_types=["common"],
                updated_from=since,
                page=page,
                limit=100,
            )
            if not batch:
                break
            for n in batch:
                text = (n.get("params") or {}).get("text") or ""
                if is_ai_note(text) and n.get("entity_id"):
                    lead_ids.add(int(n["entity_id"]))
            if len(batch) < 100:
                break
            page += 1
            time.sleep(0.08)
    except Exception as e:
        print(f"Global scan warn: {e}")

    all_leads = sorted(lead_ids)
    print(f"Leads to check: {len(all_leads)}")

    to_clear: list[dict] = []
    for i, lid in enumerate(all_leads):
        try:
            notes: list = []
            page = 1
            while page <= 5:
                data = client._request(
                    "GET",
                    f"/api/v4/leads/{lid}/notes",
                    params={"limit": 100, "page": page},
                )
                batch = (data or {}).get("_embedded", {}).get("notes", []) or []
                if not batch:
                    break
                notes.extend(batch)
                if len(batch) < 100:
                    break
                page += 1
            for n in notes:
                text = (n.get("params") or {}).get("text") or ""
                if is_ai_note(text):
                    to_clear.append(
                        {
                            "lead_id": lid,
                            "note_id": int(n["id"]),
                            "note_type": n.get("note_type") or "common",
                            "preview": text[:60].replace("\n", " "),
                        }
                    )
        except Exception as e:
            print(f"  err lead {lid}: {e}")
        if (i + 1) % 15 == 0:
            print(f"  scanned {i + 1}/{len(all_leads)}, found {len(to_clear)}")
        time.sleep(0.06)

    print(f"AI notes to clear: {len(to_clear)}")
    for item in to_clear[:12]:
        print(f"  lead={item['lead_id']} note={item['note_id']} | {item['preview']}")

    if not to_clear:
        print("Nothing to clear.")
        _clear_local_flags()
        return

    ok = fail = 0
    batch_size = 10
    for i in range(0, len(to_clear), batch_size):
        chunk = to_clear[i : i + batch_size]
        payload = [
            {
                "id": x["note_id"],
                "entity_id": x["lead_id"],
                "note_type": x["note_type"],
                "params": {"text": "·"},  # minimal — API may reject empty
            }
            for x in chunk
        ]
        try:
            client._request("PATCH", "/api/v4/leads/notes", json=payload)
            ok += len(chunk)
            print(f"  cleared batch {i // batch_size + 1}: {len(chunk)}")
        except Exception as e:
            print(f"  batch fail: {e} — one by one")
            for x in chunk:
                try:
                    client._request(
                        "PATCH",
                        "/api/v4/leads/notes",
                        json=[
                            {
                                "id": x["note_id"],
                                "entity_id": x["lead_id"],
                                "note_type": x["note_type"],
                                "params": {"text": "·"},
                            }
                        ],
                    )
                    ok += 1
                except Exception as e2:
                    fail += 1
                    print(f"    fail note {x['note_id']}: {e2}")
                time.sleep(0.05)
        time.sleep(0.15)

    print(f"DONE cleared_ok={ok} fail={fail}")
    print(
        "Note: amoCRM API cannot hard-delete notes; text was wiped so AI content is gone."
    )
    _clear_local_flags()


def _clear_local_flags() -> None:
    init_db()
    with db() as conn:
        cur = conn.execute(
            """
            UPDATE communications
            SET note_posted_at = NULL,
                note_post_error = 'user_requested_clear'
            WHERE note_posted_at IS NOT NULL AND note_posted_at > 0
               OR note_post_error LIKE 'cleared%'
            """
        )
        print(f"Local flags updated: {cur.rowcount} rows")


if __name__ == "__main__":
    main()
