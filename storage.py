"""SQLite storage for collected events, analyses and reports."""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from config import DB_PATH


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS managers (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT,
                is_active INTEGER DEFAULT 1,
                raw_json TEXT,
                updated_at INTEGER
            );

            CREATE TABLE IF NOT EXISTS pipelines (
                id INTEGER PRIMARY KEY,
                name TEXT,
                statuses_json TEXT,
                updated_at INTEGER
            );

            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                entity_id INTEGER,
                entity_type TEXT,
                created_by INTEGER,
                created_at INTEGER,
                payload_json TEXT,
                collected_at INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at);
            CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);
            CREATE INDEX IF NOT EXISTS idx_events_by ON events(created_by);

            CREATE TABLE IF NOT EXISTS communications (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,          -- call | chat | note
                direction TEXT,             -- in | out | unknown
                entity_id INTEGER,
                entity_type TEXT,
                manager_id INTEGER,
                created_at INTEGER,
                duration INTEGER,
                phone TEXT,
                text TEXT,
                source TEXT,
                lead_id INTEGER,
                analyzed INTEGER DEFAULT 0,
                raw_json TEXT,
                collected_at INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_comm_created ON communications(created_at);
            CREATE INDEX IF NOT EXISTS idx_comm_manager ON communications(manager_id);
            CREATE INDEX IF NOT EXISTS idx_comm_analyzed ON communications(analyzed);

            CREATE TABLE IF NOT EXISTS analyses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                communication_id TEXT NOT NULL UNIQUE,
                score REAL,
                summary TEXT,
                strengths TEXT,
                weaknesses TEXT,
                advice TEXT,
                sentiment TEXT,
                flags_json TEXT,
                model TEXT,
                created_at INTEGER,
                FOREIGN KEY(communication_id) REFERENCES communications(id)
            );

            CREATE TABLE IF NOT EXISTS lead_snapshots (
                lead_id INTEGER PRIMARY KEY,
                name TEXT,
                price REAL,
                status_id INTEGER,
                pipeline_id INTEGER,
                responsible_user_id INTEGER,
                created_at INTEGER,
                updated_at INTEGER,
                closed_at INTEGER,
                is_won INTEGER,
                is_lost INTEGER,
                raw_json TEXT,
                synced_at INTEGER
            );
            CREATE INDEX IF NOT EXISTS idx_leads_resp ON lead_snapshots(responsible_user_id);
            CREATE INDEX IF NOT EXISTS idx_leads_updated ON lead_snapshots(updated_at);

            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                period TEXT NOT NULL,       -- day | week | month
                period_start INTEGER NOT NULL,
                period_end INTEGER NOT NULL,
                title TEXT,
                markdown TEXT,
                stats_json TEXT,
                created_at INTEGER,
                sent_telegram INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS tabel_status (
                user_id INTEGER PRIMARY KEY,
                status_code TEXT NOT NULL DEFAULT '',
                updated_at INTEGER,
                updated_by INTEGER
            );

            CREATE TABLE IF NOT EXISTS tabel_presence (
                user_id INTEGER PRIMARY KEY,
                last_seen INTEGER,
                last_active INTEGER
            );

            CREATE TABLE IF NOT EXISTS tabel_activity (
                user_id INTEGER NOT NULL,
                bucket INTEGER NOT NULL,
                PRIMARY KEY (user_id, bucket)
            );
            CREATE INDEX IF NOT EXISTS idx_tabel_activity_bucket
                ON tabel_activity(bucket);
            """
        )


def get_meta(key: str, default: str | None = None) -> str | None:
    with db() as conn:
        row = conn.execute(
            "SELECT value FROM meta WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default


def set_meta(key: str, value: str) -> None:
    with db() as conn:
        conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def upsert_manager(user: dict[str, Any]) -> None:
    with db() as conn:
        conn.execute(
            """
            INSERT INTO managers(id, name, email, is_active, raw_json, updated_at)
            VALUES(?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                email = excluded.email,
                is_active = excluded.is_active,
                raw_json = excluded.raw_json,
                updated_at = excluded.updated_at
            """,
            (
                user["id"],
                user.get("name") or f"User {user['id']}",
                user.get("email"),
                1 if user.get("rights", {}).get("is_active", True) else 0,
                json.dumps(user, ensure_ascii=False),
                int(time.time()),
            ),
        )


def list_managers(active_only: bool = True) -> list[dict[str, Any]]:
    with db() as conn:
        sql = "SELECT * FROM managers"
        if active_only:
            sql += " WHERE is_active = 1"
        sql += " ORDER BY name"
        return [dict(r) for r in conn.execute(sql).fetchall()]


def manager_name_map() -> dict[int, str]:
    return {m["id"]: m["name"] for m in list_managers(active_only=False)}


def upsert_event(ev: dict[str, Any]) -> bool:
    """Return True if inserted (new)."""
    with db() as conn:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO events(
                id, type, entity_id, entity_type, created_by, created_at,
                payload_json, collected_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(ev.get("id")),
                ev.get("type"),
                ev.get("entity_id"),
                ev.get("entity_type"),
                ev.get("created_by"),
                ev.get("created_at"),
                json.dumps(ev, ensure_ascii=False),
                int(time.time()),
            ),
        )
        return cur.rowcount > 0


def _ensure_comm_columns(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(communications)").fetchall()}
    if "recording_url" not in cols:
        conn.execute("ALTER TABLE communications ADD COLUMN recording_url TEXT")
    if "transcript" not in cols:
        conn.execute("ALTER TABLE communications ADD COLUMN transcript TEXT")
    if "transcript_status" not in cols:
        conn.execute(
            "ALTER TABLE communications ADD COLUMN transcript_status TEXT DEFAULT ''"
        )
    if "transcribed_at" not in cols:
        conn.execute("ALTER TABLE communications ADD COLUMN transcribed_at INTEGER")


def upsert_communication(row: dict[str, Any]) -> bool:
    with db() as conn:
        _ensure_comm_columns(conn)
        cur = conn.execute(
            """
            INSERT INTO communications(
                id, kind, direction, entity_id, entity_type, manager_id,
                created_at, duration, phone, text, source, lead_id,
                analyzed, raw_json, collected_at, recording_url
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                text = CASE
                    WHEN excluded.text IS NOT NULL
                         AND LENGTH(TRIM(excluded.text)) > 15
                         AND excluded.text NOT LIKE 'phone=%'
                         AND excluded.text NOT LIKE 'link=%'
                    THEN excluded.text
                    ELSE communications.text
                END,
                duration = COALESCE(excluded.duration, communications.duration),
                phone = COALESCE(excluded.phone, communications.phone),
                lead_id = COALESCE(excluded.lead_id, communications.lead_id),
                recording_url = COALESCE(excluded.recording_url, communications.recording_url),
                raw_json = excluded.raw_json
            """,
            (
                row["id"],
                row["kind"],
                row.get("direction"),
                row.get("entity_id"),
                row.get("entity_type"),
                row.get("manager_id"),
                row.get("created_at"),
                row.get("duration"),
                row.get("phone"),
                row.get("text"),
                row.get("source"),
                row.get("lead_id"),
                json.dumps(row.get("raw") or {}, ensure_ascii=False),
                int(time.time()),
                row.get("recording_url"),
            ),
        )
        return cur.rowcount > 0


def unanalyzed_communications(limit: int = 20) -> list[dict[str, Any]]:
    with db() as conn:
        _ensure_comm_columns(conn)
        rows = conn.execute(
            """
            SELECT * FROM communications
            WHERE analyzed = 0
              AND (
                    (transcript IS NOT NULL AND LENGTH(TRIM(transcript)) > 30)
                 OR (text IS NOT NULL AND LENGTH(TRIM(text)) > 40
                     AND text NOT LIKE '[incoming_%'
                     AND text NOT LIKE '[outgoing_%'
                     AND text NOT LIKE 'phone=%'
                     AND text NOT LIKE 'link=%')
              )
            ORDER BY
              CASE WHEN transcript IS NOT NULL AND LENGTH(TRIM(transcript)) > 30 THEN 0 ELSE 1 END,
              created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def save_analysis(
    communication_id: str,
    *,
    score: float,
    summary: str,
    strengths: str,
    weaknesses: str,
    advice: str,
    sentiment: str,
    flags: list[str],
    model: str,
) -> None:
    now = int(time.time())
    with db() as conn:
        conn.execute(
            """
            INSERT INTO analyses(
                communication_id, score, summary, strengths, weaknesses,
                advice, sentiment, flags_json, model, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(communication_id) DO UPDATE SET
                score = excluded.score,
                summary = excluded.summary,
                strengths = excluded.strengths,
                weaknesses = excluded.weaknesses,
                advice = excluded.advice,
                sentiment = excluded.sentiment,
                flags_json = excluded.flags_json,
                model = excluded.model,
                created_at = excluded.created_at
            """,
            (
                communication_id,
                score,
                summary,
                strengths,
                weaknesses,
                advice,
                sentiment,
                json.dumps(flags, ensure_ascii=False),
                model,
                now,
            ),
        )
        conn.execute(
            "UPDATE communications SET analyzed = 1 WHERE id = ?",
            (communication_id,),
        )


def upsert_lead(lead: dict[str, Any], *, won_ids: set[int], lost_ids: set[int]) -> None:
    status_id = lead.get("status_id")
    closed_at = lead.get("closed_at")
    is_won = 1 if status_id in won_ids else 0
    is_lost = 1 if status_id in lost_ids else 0
    with db() as conn:
        conn.execute(
            """
            INSERT INTO lead_snapshots(
                lead_id, name, price, status_id, pipeline_id, responsible_user_id,
                created_at, updated_at, closed_at, is_won, is_lost, raw_json, synced_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(lead_id) DO UPDATE SET
                name = excluded.name,
                price = excluded.price,
                status_id = excluded.status_id,
                pipeline_id = excluded.pipeline_id,
                responsible_user_id = excluded.responsible_user_id,
                updated_at = excluded.updated_at,
                closed_at = excluded.closed_at,
                is_won = excluded.is_won,
                is_lost = excluded.is_lost,
                raw_json = excluded.raw_json,
                synced_at = excluded.synced_at
            """,
            (
                lead["id"],
                lead.get("name"),
                float(lead.get("price") or 0),
                status_id,
                lead.get("pipeline_id"),
                lead.get("responsible_user_id"),
                lead.get("created_at"),
                lead.get("updated_at"),
                closed_at,
                is_won,
                is_lost,
                json.dumps(lead, ensure_ascii=False),
                int(time.time()),
            ),
        )


def save_report(
    *,
    period: str,
    period_start: int,
    period_end: int,
    title: str,
    markdown: str,
    stats: dict[str, Any],
) -> int:
    with db() as conn:
        cur = conn.execute(
            """
            INSERT INTO reports(
                period, period_start, period_end, title, markdown,
                stats_json, created_at, sent_telegram
            ) VALUES(?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                period,
                period_start,
                period_end,
                title,
                markdown,
                json.dumps(stats, ensure_ascii=False),
                int(time.time()),
            ),
        )
        return int(cur.lastrowid)


def mark_report_sent(report_id: int) -> None:
    with db() as conn:
        conn.execute(
            "UPDATE reports SET sent_telegram = 1 WHERE id = ?", (report_id,)
        )


def period_stats(start_ts: int, end_ts: int) -> dict[str, Any]:
    """Aggregate KPIs for the period."""
    with db() as conn:
        managers = {
            r["id"]: r["name"]
            for r in conn.execute("SELECT id, name FROM managers").fetchall()
        }

        # Communications by manager
        comm_rows = conn.execute(
            """
            SELECT manager_id, kind, direction, COUNT(*) AS cnt,
                   AVG(CASE WHEN duration > 0 THEN duration END) AS avg_duration
            FROM communications
            WHERE created_at >= ? AND created_at < ?
            GROUP BY manager_id, kind, direction
            """,
            (start_ts, end_ts),
        ).fetchall()

        # Analyses
        analysis_rows = conn.execute(
            """
            SELECT c.manager_id, AVG(a.score) AS avg_score, COUNT(*) AS n
            FROM analyses a
            JOIN communications c ON c.id = a.communication_id
            WHERE c.created_at >= ? AND c.created_at < ?
            GROUP BY c.manager_id
            """,
            (start_ts, end_ts),
        ).fetchall()

        # Leads updated / created / won / lost in period
        lead_rows = conn.execute(
            """
            SELECT responsible_user_id AS manager_id,
                   COUNT(*) AS worked,
                   SUM(CASE WHEN created_at >= ? AND created_at < ? THEN 1 ELSE 0 END) AS created,
                   SUM(CASE WHEN is_won = 1 AND COALESCE(closed_at, updated_at) >= ?
                                 AND COALESCE(closed_at, updated_at) < ? THEN 1 ELSE 0 END) AS won,
                   SUM(CASE WHEN is_lost = 1 AND COALESCE(closed_at, updated_at) >= ?
                                 AND COALESCE(closed_at, updated_at) < ? THEN 1 ELSE 0 END) AS lost,
                   SUM(CASE WHEN is_won = 1 AND COALESCE(closed_at, updated_at) >= ?
                                 AND COALESCE(closed_at, updated_at) < ? THEN price ELSE 0 END) AS won_sum
            FROM lead_snapshots
            WHERE updated_at >= ? AND updated_at < ?
            GROUP BY responsible_user_id
            """,
            (
                start_ts,
                end_ts,
                start_ts,
                end_ts,
                start_ts,
                end_ts,
                start_ts,
                end_ts,
                start_ts,
                end_ts,
            ),
        ).fetchall()

        # Events
        event_rows = conn.execute(
            """
            SELECT created_by AS manager_id, type, COUNT(*) AS cnt
            FROM events
            WHERE created_at >= ? AND created_at < ?
            GROUP BY created_by, type
            """,
            (start_ts, end_ts),
        ).fetchall()

        # Recent analysis samples for advice
        sample_advice = conn.execute(
            """
            SELECT c.manager_id, a.summary, a.advice, a.score, a.weaknesses
            FROM analyses a
            JOIN communications c ON c.id = a.communication_id
            WHERE c.created_at >= ? AND c.created_at < ?
            ORDER BY a.score ASC
            LIMIT 40
            """,
            (start_ts, end_ts),
        ).fetchall()

    by_manager: dict[int, dict[str, Any]] = {}

    def m(mid: int | None) -> dict[str, Any]:
        key = mid or 0
        if key not in by_manager:
            by_manager[key] = {
                "manager_id": key,
                "name": managers.get(key, "Без ответственного" if key == 0 else f"ID {key}"),
                "calls_in": 0,
                "calls_out": 0,
                "calls_total": 0,
                "avg_call_duration": 0.0,
                "chat_in": 0,
                "chat_out": 0,
                "chats_total": 0,
                "notes": 0,
                "leads_worked": 0,
                "leads_created": 0,
                "leads_won": 0,
                "leads_lost": 0,
                "won_sum": 0.0,
                "avg_quality_score": None,
                "analyses_count": 0,
                "events": {},
                "weak_points": [],
            }
        return by_manager[key]

    for r in comm_rows:
        row = m(r["manager_id"])
        kind = r["kind"]
        direction = r["direction"] or "unknown"
        cnt = r["cnt"]
        if kind == "call":
            row["calls_total"] += cnt
            if direction == "in":
                row["calls_in"] += cnt
            elif direction == "out":
                row["calls_out"] += cnt
            if r["avg_duration"]:
                row["avg_call_duration"] = float(r["avg_duration"])
        elif kind == "chat":
            row["chats_total"] += cnt
            if direction == "in":
                row["chat_in"] += cnt
            elif direction == "out":
                row["chat_out"] += cnt
        else:
            row["notes"] += cnt

    for r in analysis_rows:
        row = m(r["manager_id"])
        row["avg_quality_score"] = round(float(r["avg_score"] or 0), 1)
        row["analyses_count"] = r["n"]

    for r in lead_rows:
        row = m(r["manager_id"])
        row["leads_worked"] = r["worked"] or 0
        row["leads_created"] = r["created"] or 0
        row["leads_won"] = r["won"] or 0
        row["leads_lost"] = r["lost"] or 0
        row["won_sum"] = float(r["won_sum"] or 0)

    for r in event_rows:
        row = m(r["manager_id"])
        row["events"][r["type"]] = r["cnt"]

    for r in sample_advice:
        row = m(r["manager_id"])
        if r["weaknesses"] and len(row["weak_points"]) < 5:
            row["weak_points"].append(
                {
                    "score": r["score"],
                    "summary": r["summary"],
                    "advice": r["advice"],
                    "weaknesses": r["weaknesses"],
                }
            )

    totals = {
        "calls": sum(x["calls_total"] for x in by_manager.values()),
        "chats": sum(x["chats_total"] for x in by_manager.values()),
        "leads_worked": sum(x["leads_worked"] for x in by_manager.values()),
        "leads_created": sum(x["leads_created"] for x in by_manager.values()),
        "leads_won": sum(x["leads_won"] for x in by_manager.values()),
        "leads_lost": sum(x["leads_lost"] for x in by_manager.values()),
        "won_sum": sum(x["won_sum"] for x in by_manager.values()),
    }

    return {
        "start": start_ts,
        "end": end_ts,
        "managers": sorted(
            by_manager.values(),
            key=lambda x: (x["leads_won"], x["calls_total"], x["chats_total"]),
            reverse=True,
        ),
        "totals": totals,
    }
