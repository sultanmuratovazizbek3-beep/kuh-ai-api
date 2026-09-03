"""Collect events, call notes, chats activity and leads from AmoCRM."""

from __future__ import annotations

import logging
import time
from typing import Any

from amocrm_client import AmoCRMClient
from config import (
    CALL_EVENT_TYPES,
    CHAT_EVENT_TYPES,
    LEAD_EVENT_TYPES,
    LOST_STATUS_IDS,
    WON_STATUS_IDS,
)
from storage import (
    get_meta,
    init_db,
    set_meta,
    upsert_communication,
    upsert_event,
    upsert_lead,
    upsert_manager,
)

logger = logging.getLogger(__name__)

# Note types in amoCRM for calls / messages
CALL_NOTE_TYPES = ["call_in", "call_out"]
TEXT_NOTE_TYPES = ["common", "sms_in", "sms_out", "extended_service_message"]


def _direction_from_type(t: str) -> str:
    if "incoming" in t or t.endswith("_in") or t == "call_in":
        return "in"
    if "outgoing" in t or t.endswith("_out") or t == "call_out":
        return "out"
    return "unknown"


def _note_text(params: dict[str, Any] | None) -> str:
    """Human text only — do NOT put recording URL into text (that broke analysis)."""
    if not params:
        return ""
    for key in ("text", "message", "service", "call_result"):
        val = params.get(key)
        if isinstance(val, str) and val.strip() and not val.strip().startswith("http"):
            # skip pure numeric call_result noise like "0 "
            if key == "call_result" and len(val.strip()) < 3:
                continue
            return val.strip()
    return ""


class Collector:
    def __init__(self, client: AmoCRMClient | None = None) -> None:
        self.client = client or AmoCRMClient()

    def sync_managers(self) -> int:
        users = self.client.get_users()
        for u in users:
            upsert_manager(u)
        logger.info("Synced %s managers", len(users))
        return len(users)

    def collect_events(self, since_ts: int, until_ts: int | None = None) -> int:
        types = list(CALL_EVENT_TYPES + CHAT_EVENT_TYPES + LEAD_EVENT_TYPES)
        new_count = 0
        for ev in self.client.iter_events(
            created_from=since_ts,
            created_to=until_ts,
            event_types=types,
        ):
            if upsert_event(ev):
                new_count += 1
            self._event_to_communication(ev)
        logger.info("Collected events: %s new since %s", new_count, since_ts)
        return new_count

    def _event_to_communication(self, ev: dict[str, Any]) -> None:
        """Register call/chat activity from events.

        Full call text comes from collect_call_notes() (bulk notes API).
        Per-note GET is skipped — wrong singular paths caused 404 storms and
        made the first sync extremely slow.
        """
        etype = ev.get("type") or ""
        created_at = ev.get("created_at") or int(time.time())
        entity_type = ev.get("entity_type")
        entity_id = ev.get("entity_id")
        manager_id = ev.get("created_by") or 0
        lead_id = entity_id if entity_type == "lead" else None

        if etype in CALL_EVENT_TYPES:
            note_id = None
            try:
                va = ev.get("value_after") or []
                if va and isinstance(va[0], dict) and "note" in va[0]:
                    note_id = va[0]["note"].get("id")
            except (IndexError, TypeError, AttributeError):
                pass

            upsert_communication(
                {
                    "id": f"event:{ev.get('id')}",
                    "kind": "call",
                    "direction": _direction_from_type(etype),
                    "entity_id": entity_id,
                    "entity_type": entity_type,
                    "manager_id": manager_id,
                    "created_at": created_at,
                    "duration": None,
                    "phone": None,
                    "text": f"[{etype}] note_id={note_id or 'n/a'}",
                    "source": "event",
                    "lead_id": lead_id,
                    "raw": ev,
                }
            )

        elif etype in CHAT_EVENT_TYPES:
            msg_id = None
            try:
                va = ev.get("value_after") or []
                if va and isinstance(va[0], dict) and "message" in va[0]:
                    msg_id = va[0]["message"].get("id")
            except (IndexError, TypeError, AttributeError):
                pass

            # Full chat body is not always available via public API;
            # we still track activity and enrich from notes when possible.
            text = f"[{etype}] message_id={msg_id or 'n/a'}"
            upsert_communication(
                {
                    "id": f"event:{ev.get('id')}",
                    "kind": "chat",
                    "direction": _direction_from_type(etype),
                    "entity_id": entity_id,
                    "entity_type": entity_type,
                    "manager_id": manager_id,
                    "created_at": created_at,
                    "duration": None,
                    "phone": None,
                    "text": text,
                    "source": "event",
                    "lead_id": lead_id,
                    "raw": ev,
                }
            )

    def collect_call_notes(self, since_ts: int, until_ts: int | None = None) -> int:
        count = 0
        for entity_type in ("leads", "contacts"):
            for note in self.client.iter_notes(
                entity_type,
                note_types=CALL_NOTE_TYPES,
                updated_from=since_ts,
                updated_to=until_ts,
            ):
                params = note.get("params") or {}
                ntype = note.get("note_type") or ""
                text = _note_text(params)
                link = (params.get("link") or "").strip() or None
                duration = params.get("duration")
                try:
                    duration = int(duration) if duration is not None else None
                except (TypeError, ValueError):
                    duration = None
                # Placeholder text only if no human text — STT will fill transcript
                if not text and link:
                    text = f"[call_recording] duration={duration or 0}s phone={params.get('phone') or ''}"
                upsert_communication(
                    {
                        "id": f"note:{entity_type}:{note.get('id')}",
                        "kind": "call",
                        "direction": _direction_from_type(ntype),
                        "entity_id": note.get("entity_id"),
                        "entity_type": entity_type.rstrip("s"),  # lead/contact
                        "manager_id": note.get("created_by")
                        or note.get("responsible_user_id")
                        or 0,
                        "created_at": note.get("created_at") or note.get("updated_at"),
                        "duration": duration,
                        "phone": params.get("phone"),
                        "text": text,
                        "source": params.get("source") or "note",
                        "lead_id": note.get("entity_id") if entity_type == "leads" else None,
                        "recording_url": link,
                        "raw": note,
                    }
                )
                count += 1
        logger.info("Collected call notes: %s", count)
        return count

    def collect_text_notes(self, since_ts: int, until_ts: int | None = None) -> int:
        """Common/SMS notes often hold chat excerpts and manager comments."""
        count = 0
        for note in self.client.iter_notes(
            "leads",
            note_types=TEXT_NOTE_TYPES,
            updated_from=since_ts,
            updated_to=until_ts,
        ):
            params = note.get("params") or {}
            text = _note_text(params)
            if not text or len(text) < 15:
                continue
            ntype = note.get("note_type") or "common"
            kind = "chat" if "sms" in ntype else "note"
            upsert_communication(
                {
                    "id": f"note:leads:{note.get('id')}",
                    "kind": kind,
                    "direction": _direction_from_type(ntype),
                    "entity_id": note.get("entity_id"),
                    "entity_type": "lead",
                    "manager_id": note.get("created_by") or 0,
                    "created_at": note.get("created_at") or note.get("updated_at"),
                    "duration": None,
                    "phone": None,
                    "text": text,
                    "source": ntype,
                    "lead_id": note.get("entity_id"),
                    "raw": note,
                }
            )
            count += 1
        logger.info("Collected text notes: %s", count)
        return count

    def collect_leads(self, since_ts: int, until_ts: int | None = None) -> int:
        count = 0
        for lead in self.client.iter_leads(
            updated_from=since_ts,
            updated_to=until_ts,
            max_pages=40,
        ):
            upsert_lead(lead, won_ids=WON_STATUS_IDS, lost_ids=LOST_STATUS_IDS)
            count += 1
        logger.info("Synced leads: %s", count)
        return count

    def run_once(self, lookback_hours: int = 48) -> dict[str, int]:
        init_db()
        now = int(time.time())
        last = get_meta("last_collect_ts")
        if last:
            since = max(int(last) - 600, now - lookback_hours * 3600)
        else:
            since = now - lookback_hours * 3600

        stats = {
            "managers": self.sync_managers(),
            "events": self.collect_events(since, now),
            "call_notes": self.collect_call_notes(since, now),
            "text_notes": self.collect_text_notes(since, now),
            "leads": self.collect_leads(since, now),
        }
        set_meta("last_collect_ts", str(now))
        logger.info("Collect finished: %s", stats)
        return stats
