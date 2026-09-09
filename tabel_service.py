"""Табель: статусы сотрудников, онлайн и 5-минутная активность в amoCRM."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from storage import db, init_db, get_meta, set_meta

logger = logging.getLogger(__name__)

ONLINE_TTL_SEC = 120
ACTIVITY_KEEP_DAYS = 62
MAX_PERIOD_DAYS = 62
BUCKET_SEC = 300
LEAD_CACHE_TTL = 600
USERS_CACHE_TTL = 60
STATUSES_META = "tabel_statuses"
ACL_ALLOWED_META = "tabel_acl_allowed"
ACL_LIST_META = "tabel_acl_list"

DEFAULT_STATUSES: list[dict[str, str]] = [
    {"code": "vacation", "name": "В отпуске", "color": "#f5a623"},
    {"code": "remote", "name": "Удалённо", "color": "#4c8bf5"},
]

_users_cache: dict[str, Any] = {"at": 0, "users": [], "groups": []}
_lead_cache: dict[str, Any] = {"at": 0, "counts": {}}


def _tz():
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo("Asia/Tashkent")
    except Exception:
        return timezone(timedelta(hours=5))


def day_bounds(days_ago: int = 0, days: int = 1) -> tuple[int, int]:
    now = datetime.now(_tz())
    start = (now - timedelta(days=days_ago)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    end = start + timedelta(days=days)
    return int(start.timestamp()), int(end.timestamp())


def period_bounds(
    period: str | None = None,
    from_ts: int | None = None,
    to_ts: int | None = None,
) -> tuple[int, int, str]:
    tz = _tz()
    now = datetime.now(tz)
    today0 = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today0 + timedelta(days=1)
    code = (period or "today").strip().lower()

    if from_ts and to_ts:
        start = int(from_ts)
        end = int(to_ts)
        if end <= start:
            end = start + 86400
        if end - start > MAX_PERIOD_DAYS * 86400:
            start = end - MAX_PERIOD_DAYS * 86400
        return start, end, "custom"

    if code == "yesterday":
        return (
            int((today0 - timedelta(days=1)).timestamp()),
            int(today0.timestamp()),
            "yesterday",
        )
    if code in ("week", "7d"):
        start = today0 - timedelta(days=today0.weekday())
        return int(start.timestamp()), int(tomorrow.timestamp()), "week"
    if code in ("month", "30d"):
        start = today0.replace(day=1)
        return int(start.timestamp()), int(tomorrow.timestamp()), "month"
    if code == "last_month":
        first = today0.replace(day=1)
        prev = (first - timedelta(days=1)).replace(day=1)
        return int(prev.timestamp()), int(first.timestamp()), "last_month"
    return int(today0.timestamp()), int(tomorrow.timestamp()), "today"


def _hours_in_range(buckets: list[int], start: int, end: int) -> float:
    n = sum(1 for b in buckets if start <= int(b) < end)
    return round(n * (BUCKET_SEC / 3600.0), 2)


def _first_last(buckets: list[int], start: int, end: int) -> tuple[int, int]:
    hit = [int(b) for b in buckets if start <= int(b) < end]
    if not hit:
        return 0, 0
    return min(hit), max(hit) + BUCKET_SEC


def _blank_work() -> dict[str, Any]:
    return {
        "calls": 0,
        "calls_in": 0,
        "calls_out": 0,
        "call_sec": 0,
        "chats": 0,
        "notes": 0,
        "leads_created": 0,
        "leads_won": 0,
        "leads_lost": 0,
        "leads_worked": 0,
        "quality": None,
    }


def _work_stats(start_ts: int, end_ts: int) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}

    def row(uid: int | None) -> dict[str, Any]:
        key = int(uid or 0)
        if key not in out:
            out[key] = _blank_work()
        return out[key]

    try:
        with db() as conn:
            for r in conn.execute(
                """
                SELECT manager_id, kind, direction, COUNT(*) AS cnt,
                       SUM(CASE WHEN duration > 0 THEN duration ELSE 0 END) AS dur
                FROM communications
                WHERE created_at >= ? AND created_at < ?
                GROUP BY manager_id, kind, direction
                """,
                (start_ts, end_ts),
            ):
                rec = row(r["manager_id"])
                kind = str(r["kind"] or "")
                direction = str(r["direction"] or "")
                cnt = int(r["cnt"] or 0)
                dur = int(r["dur"] or 0)
                if kind == "call":
                    rec["calls"] += cnt
                    rec["call_sec"] += dur
                    if direction == "in":
                        rec["calls_in"] += cnt
                    elif direction == "out":
                        rec["calls_out"] += cnt
                elif kind == "chat":
                    rec["chats"] += cnt
                else:
                    rec["notes"] += cnt

            for r in conn.execute(
                """
                SELECT responsible_user_id AS uid,
                       COUNT(*) AS worked,
                       SUM(CASE WHEN created_at >= ? AND created_at < ? THEN 1 ELSE 0 END) AS created,
                       SUM(CASE WHEN is_won = 1 AND COALESCE(closed_at, updated_at) >= ?
                                 AND COALESCE(closed_at, updated_at) < ? THEN 1 ELSE 0 END) AS won,
                       SUM(CASE WHEN is_lost = 1 AND COALESCE(closed_at, updated_at) >= ?
                                 AND COALESCE(closed_at, updated_at) < ? THEN 1 ELSE 0 END) AS lost
                FROM lead_snapshots
                WHERE updated_at >= ? AND updated_at < ?
                  AND responsible_user_id IS NOT NULL
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
                ),
            ):
                rec = row(r["uid"])
                rec["leads_worked"] = int(r["worked"] or 0)
                rec["leads_created"] = int(r["created"] or 0)
                rec["leads_won"] = int(r["won"] or 0)
                rec["leads_lost"] = int(r["lost"] or 0)

            for r in conn.execute(
                """
                SELECT c.manager_id AS uid, AVG(a.score) AS avg_score
                FROM analyses a
                JOIN communications c ON c.id = a.communication_id
                WHERE c.created_at >= ? AND c.created_at < ?
                GROUP BY c.manager_id
                """,
                (start_ts, end_ts),
            ):
                rec = row(r["uid"])
                try:
                    rec["quality"] = round(float(r["avg_score"]), 1)
                except (TypeError, ValueError):
                    rec["quality"] = None
    except Exception as exc:
        logger.debug("tabel work stats failed: %s", exc)
    return out


def _role_of_user(user: dict[str, Any]) -> str:
    embedded = user.get("_embedded") or {}
    roles = embedded.get("roles") or []
    if roles and isinstance(roles, list) and isinstance(roles[0], dict):
        return str(roles[0].get("name") or roles[0].get("short_name") or "")
    return str(user.get("role") or "")


def ensure_tables() -> None:
    init_db()
    with db() as conn:
        conn.executescript(
            """
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


def default_statuses() -> list[dict[str, str]]:
    return [dict(x) for x in DEFAULT_STATUSES]


def load_statuses() -> list[dict[str, str]]:
    ensure_tables()
    raw = get_meta(STATUSES_META)
    if not raw:
        return default_statuses()
    try:
        data = json.loads(raw)
    except Exception:
        return default_statuses()
    if not isinstance(data, list) or not data:
        return default_statuses()
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in data:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "").strip()
        name = str(item.get("name") or "").strip()
        color = str(item.get("color") or "#6b7280").strip() or "#6b7280"
        if not code or not name or code in seen:
            continue
        seen.add(code)
        out.append({"code": code, "name": name, "color": color})
    return out or default_statuses()


def save_statuses(items: list[dict[str, str]]) -> list[dict[str, str]]:
    ensure_tables()
    cleaned: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items:
        code = str(item.get("code") or "").strip()
        name = str(item.get("name") or "").strip()
        color = str(item.get("color") or "#6b7280").strip() or "#6b7280"
        if not code or not name or code in seen:
            continue
        seen.add(code)
        cleaned.append({"code": code, "name": name, "color": color})
    if not cleaned:
        cleaned = default_statuses()
    set_meta(STATUSES_META, json.dumps(cleaned, ensure_ascii=False))
    return cleaned


def load_tabel_acl() -> dict[str, str]:
    ensure_tables()
    return {
        "allowed_users": get_meta(ACL_ALLOWED_META) or "",
        "list_users": get_meta(ACL_LIST_META) or "",
    }


def save_tabel_acl(
    allowed_users: str | None = None,
    list_users: str | None = None,
) -> dict[str, str]:
    ensure_tables()
    if allowed_users is not None:
        set_meta(ACL_ALLOWED_META, str(allowed_users))
    if list_users is not None:
        set_meta(ACL_LIST_META, str(list_users))
    return load_tabel_acl()


def _slug_code(name: str) -> str:
    digest = hashlib.md5(name.strip().encode("utf-8")).hexdigest()[:8]
    return f"st_{digest}"


def add_status(name: str, color: str = "#6b7280") -> list[dict[str, str]]:
    name = (name or "").strip()
    if not name:
        raise ValueError("Название статуса пустое")
    items = load_statuses()
    for it in items:
        if it["name"].lower() == name.lower():
            return items
    items.append({"code": _slug_code(name), "name": name, "color": color or "#6b7280"})
    return save_statuses(items)


def remove_status(code: str) -> list[dict[str, str]]:
    code = (code or "").strip()
    items = [x for x in load_statuses() if x["code"] != code]
    saved = save_statuses(items)
    with db() as conn:
        conn.execute(
            "UPDATE tabel_status SET status_code = '' WHERE status_code = ?",
            (code,),
        )
    return saved


def _bucket_now(ts: int | None = None) -> int:
    t = int(ts if ts is not None else time.time())
    return t - (t % BUCKET_SEC)


def heartbeat(
    user_id: int,
    active: bool,
    buckets: list[int] | None = None,
    online_ids: list[int] | None = None,
) -> dict[str, Any]:
    ensure_tables()
    now = int(time.time())
    bucket = _bucket_now(now)
    cutoff = now - ACTIVITY_KEEP_DAYS * 86400
    incoming: list[int] = []
    for raw in buckets or []:
        try:
            b = int(raw)
        except (TypeError, ValueError):
            continue
        b = b - (b % BUCKET_SEC)
        if b >= cutoff:
            incoming.append(b)
    if active:
        incoming.append(bucket)
    incoming = list(dict.fromkeys(incoming))
    with db() as conn:
        row = conn.execute(
            "SELECT last_active FROM tabel_presence WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        last_active = int(row["last_active"] or 0) if row else 0
        if active:
            last_active = now
        conn.execute(
            """
            INSERT INTO tabel_presence(user_id, last_seen, last_active)
            VALUES(?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                last_seen = excluded.last_seen,
                last_active = excluded.last_active
            """,
            (user_id, now, last_active),
        )
        for b in incoming:
            conn.execute(
                """
                INSERT OR IGNORE INTO tabel_activity(user_id, bucket)
                VALUES(?, ?)
                """,
                (user_id, b),
            )
        if active:
            peer_ids: list[int] = []
            for raw in online_ids or []:
                try:
                    oid = int(raw)
                except (TypeError, ValueError):
                    continue
                if oid and oid not in peer_ids:
                    peer_ids.append(oid)
            for oid in peer_ids[:200]:
                conn.execute(
                    """
                    INSERT INTO tabel_presence(user_id, last_seen, last_active)
                    VALUES(?, ?, ?)
                    ON CONFLICT(user_id) DO UPDATE SET
                        last_seen = excluded.last_seen,
                        last_active = excluded.last_active
                    """,
                    (oid, now, now),
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO tabel_activity(user_id, bucket)
                    VALUES(?, ?)
                    """,
                    (oid, bucket),
                )
        conn.execute("DELETE FROM tabel_activity WHERE bucket < ?", (cutoff,))
        week_cut = now - 14 * 86400
        rows = conn.execute(
            "SELECT bucket FROM tabel_activity WHERE user_id = ? AND bucket >= ? ORDER BY bucket",
            (user_id, week_cut),
        ).fetchall()
        stored_buckets = [int(r["bucket"]) for r in rows]
    today_start, today_end = day_bounds(0, 1)
    return {
        "ok": True,
        "user_id": user_id,
        "online": True,
        "active": bool(active),
        "bucket": bucket,
        "stored": len(incoming),
        "buckets": stored_buckets,
        "hours_today": _hours_in_range(stored_buckets, today_start, today_end),
    }


def set_user_status(user_id: int, status_code: str, actor_id: int | None = None) -> dict[str, Any]:
    ensure_tables()
    code = (status_code or "").strip()
    if code:
        known = {x["code"] for x in load_statuses()}
        if code not in known:
            raise ValueError("Неизвестный статус")
    now = int(time.time())
    with db() as conn:
        conn.execute(
            """
            INSERT INTO tabel_status(user_id, status_code, updated_at, updated_by)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                status_code = excluded.status_code,
                updated_at = excluded.updated_at,
                updated_by = excluded.updated_by
            """,
            (user_id, code, now, actor_id),
        )
    return {"ok": True, "user_id": user_id, "status": code}


def _presence_maps() -> tuple[dict[int, int], dict[int, int]]:
    now = int(time.time())
    seen: dict[int, int] = {}
    active: dict[int, int] = {}
    with db() as conn:
        for row in conn.execute(
            "SELECT user_id, last_seen, last_active FROM tabel_presence"
        ):
            uid = int(row["user_id"])
            seen[uid] = int(row["last_seen"] or 0)
            active[uid] = int(row["last_active"] or 0)
    return seen, active


def _status_map() -> dict[int, str]:
    out: dict[int, str] = {}
    with db() as conn:
        for row in conn.execute("SELECT user_id, status_code FROM tabel_status"):
            out[int(row["user_id"])] = str(row["status_code"] or "")
    return out


def _activity_since(since: int) -> dict[int, list[int]]:
    out: dict[int, list[int]] = {}
    with db() as conn:
        for row in conn.execute(
            "SELECT user_id, bucket FROM tabel_activity WHERE bucket >= ? ORDER BY bucket",
            (since,),
        ):
            uid = int(row["user_id"])
            out.setdefault(uid, []).append(int(row["bucket"]))
    return out


def _lead_counts_from_snapshots() -> dict[int, int]:
    out: dict[int, int] = {}
    with db() as conn:
        try:
            rows = conn.execute(
                """
                SELECT responsible_user_id AS uid, COUNT(*) AS n
                FROM lead_snapshots
                WHERE COALESCE(is_won, 0) = 0 AND COALESCE(is_lost, 0) = 0
                  AND responsible_user_id IS NOT NULL
                GROUP BY responsible_user_id
                """
            ).fetchall()
        except Exception:
            return out
        for row in rows:
            try:
                out[int(row["uid"])] = int(row["n"] or 0)
            except (TypeError, ValueError):
                continue
    return out


def _lead_counts(client: Any, user_ids: list[int], me_id: int | None) -> dict[int, int]:
    now = time.time()
    if now - float(_lead_cache.get("at") or 0) < LEAD_CACHE_TTL:
        cached = dict(_lead_cache.get("counts") or {})
        if me_id and me_id not in cached:
            try:
                cached[int(me_id)] = int(client.count_leads_for_user(int(me_id)))
            except Exception as exc:
                logger.debug("lead count me failed: %s", exc)
        return cached

    counts = _lead_counts_from_snapshots()
    if me_id:
        try:
            counts[int(me_id)] = int(client.count_leads_for_user(int(me_id)))
        except Exception as exc:
            logger.debug("lead count me failed: %s", exc)
    if not counts and user_ids:
        # live fallback for small teams only
        sample = user_ids[:12]
        for uid in sample:
            try:
                counts[int(uid)] = int(client.count_leads_for_user(int(uid)))
            except Exception:
                counts[int(uid)] = 0
    _lead_cache["at"] = now
    _lead_cache["counts"] = counts
    return dict(counts)


def _group_of_user(user: dict[str, Any]) -> tuple[int, str]:
    gid = user.get("group_id") or user.get("group")
    gname = ""
    embedded = user.get("_embedded") or {}
    groups = embedded.get("groups") or []
    if groups and isinstance(groups, list):
        g = groups[0] if groups else {}
        if isinstance(g, dict):
            gid = g.get("id", gid)
            gname = str(g.get("name") or g.get("title") or "")
    try:
        gid_int = int(gid) if gid not in (None, "", 0, "0") else 0
    except (TypeError, ValueError):
        gid_int = 0
    return gid_int, gname


def _is_active_user(user: dict[str, Any]) -> bool:
    rights = user.get("rights") or {}
    if rights.get("is_active") is False:
        return False
    if user.get("active") is False:
        return False
    return True


def _load_directory(client: Any) -> tuple[list[dict[str, Any]], dict[int, str]]:
    now = time.time()
    if now - float(_users_cache.get("at") or 0) < USERS_CACHE_TTL:
        return list(_users_cache["users"]), dict(_users_cache["groups"])

    try:
        users = client.get_users(with_embed="role,group", timeout=6)
    except Exception as exc:
        logger.warning("get_users failed: %s", exc)
        return list(_users_cache.get("users") or []), dict(_users_cache.get("groups") or {})
    groups_list = []
    try:
        groups_list = client.get_user_groups()
    except Exception as exc:
        logger.debug("user groups failed: %s", exc)
    group_names: dict[int, str] = {}
    for g in groups_list or []:
        try:
            gid = int(g.get("id"))
        except (TypeError, ValueError):
            continue
        group_names[gid] = str(g.get("name") or g.get("title") or f"Группа {gid}")
    for u in users:
        gid, gname = _group_of_user(u)
        if gid and gname and gid not in group_names:
            group_names[gid] = gname
    _users_cache["at"] = now
    _users_cache["users"] = users
    _users_cache["groups"] = group_names
    return users, group_names


def build_state(
    me_id: int | None = None,
    period: str | None = "today",
    from_ts: int | None = None,
    to_ts: int | None = None,
) -> dict[str, Any]:
    ensure_tables()
    users: list[dict[str, Any]] = []
    group_names: dict[int, str] = {}
    try:
        from amocrm_client import AmoCRMClient

        client = AmoCRMClient()
        users, group_names = _load_directory(client)
    except Exception as exc:
        logger.warning("amo directory unavailable: %s", exc)
        client = None
    seen, last_active = _presence_maps()
    statuses = _status_map()
    catalog = load_statuses()
    since = int(time.time()) - ACTIVITY_KEEP_DAYS * 86400
    activity = _activity_since(since)
    now = int(time.time())
    today_start, today_end = day_bounds(0, 1)
    week_start, _week_end = day_bounds(6, 7)
    p_start, p_end, p_code = period_bounds(period, from_ts, to_ts)
    work_today = _work_stats(today_start, today_end)
    work_week = _work_stats(week_start, today_end)
    work_period = _work_stats(p_start, p_end)

    active_users = [u for u in users if _is_active_user(u)]
    ids = []
    for u in active_users:
        try:
            ids.append(int(u["id"]))
        except (TypeError, ValueError, KeyError):
            continue
    lead_counts: dict[int, int] = {}
    try:
        lead_counts = _lead_counts_from_snapshots()
    except Exception as exc:
        logger.debug("lead counts failed: %s", exc)

    packed: list[dict[str, Any]] = []
    for u in active_users:
        try:
            uid = int(u["id"])
        except (TypeError, ValueError, KeyError):
            continue
        gid, gname = _group_of_user(u)
        if gid and not gname:
            gname = group_names.get(gid) or ""
        online = (now - int(seen.get(uid) or 0)) <= ONLINE_TTL_SEC
        buckets = activity.get(uid) or []
        first_ts, last_ts = _first_last(buckets, p_start, p_end)
        packed.append(
            {
                "id": uid,
                "name": u.get("name") or f"User {uid}",
                "email": u.get("email") or u.get("login") or "",
                "phone": u.get("phone") or "",
                "role": _role_of_user(u),
                "is_admin": bool((u.get("rights") or {}).get("is_admin")),
                "group_id": gid or 0,
                "group_name": gname or ("Без группы" if not gid else f"Группа {gid}"),
                "online": online,
                "status": statuses.get(uid) or "",
                "leads": int(lead_counts.get(uid) or 0),
                "last_seen": int(seen.get(uid) or 0),
                "last_active": int(last_active.get(uid) or 0),
                "buckets": buckets,
                "hours_today": _hours_in_range(buckets, today_start, today_end),
                "hours_week": _hours_in_range(buckets, week_start, today_end),
                "hours_period": _hours_in_range(buckets, p_start, p_end),
                "first_active_today": first_ts,
                "last_active_today": last_ts,
                "today": work_today.get(uid) or _blank_work(),
                "week": work_week.get(uid) or _blank_work(),
                "period": work_period.get(uid) or _blank_work(),
            }
        )

    have = {int(x["id"]) for x in packed}
    extra_ids = set(seen) | set(activity) | set(statuses)
    if me_id:
        extra_ids.add(int(me_id))
    for uid in extra_ids:
        if uid in have:
            continue
        buckets = activity.get(uid) or []
        first_ts, last_ts = _first_last(buckets, p_start, p_end)
        packed.append(
            {
                "id": uid,
                "name": f"User {uid}",
                "email": "",
                "phone": "",
                "role": "",
                "is_admin": False,
                "group_id": 0,
                "group_name": "Без группы",
                "online": (now - int(seen.get(uid) or 0)) <= ONLINE_TTL_SEC,
                "status": statuses.get(uid) or "",
                "leads": int(lead_counts.get(uid) or 0),
                "last_seen": int(seen.get(uid) or 0),
                "last_active": int(last_active.get(uid) or 0),
                "buckets": buckets,
                "hours_today": _hours_in_range(buckets, today_start, today_end),
                "hours_week": _hours_in_range(buckets, week_start, today_end),
                "hours_period": _hours_in_range(buckets, p_start, p_end),
                "first_active_today": first_ts,
                "last_active_today": last_ts,
                "today": work_today.get(uid) or _blank_work(),
                "week": work_week.get(uid) or _blank_work(),
                "period": work_period.get(uid) or _blank_work(),
            }
        )

    packed.sort(key=lambda x: ((x.get("group_name") or ""), (x.get("name") or "").lower()))
    groups_out = [
        {"id": gid, "name": name}
        for gid, name in sorted(group_names.items(), key=lambda kv: kv[1].lower())
    ]
    if any(x["group_id"] in (0, None) for x in packed):
        groups_out.append({"id": 0, "name": "Без группы"})

    me = None
    if me_id:
        me = next((x for x in packed if x["id"] == int(me_id)), None)
        if me is None:
            me = {"id": int(me_id), "name": "", "email": "", "online": False, "status": "", "leads": 0}

    summary = {
        "total": len(packed),
        "online": sum(1 for x in packed if x.get("online")),
        "idle_today": sum(1 for x in packed if not x.get("hours_period")),
        "hours_today": round(sum(float(x.get("hours_today") or 0) for x in packed), 1),
        "hours_week": round(sum(float(x.get("hours_week") or 0) for x in packed), 1),
        "hours_period": round(sum(float(x.get("hours_period") or 0) for x in packed), 1),
        "vacation": sum(1 for x in packed if x.get("status") == "vacation"),
        "remote": sum(1 for x in packed if x.get("status") == "remote"),
        "calls_today": sum(int((x.get("period") or {}).get("calls") or 0) for x in packed),
        "leads_created_today": sum(
            int((x.get("period") or {}).get("leads_created") or 0) for x in packed
        ),
    }

    return {
        "ok": True,
        "ts": now,
        "tz": "Asia/Tashkent",
        "day_start": today_start,
        "week_start": week_start,
        "period": p_code,
        "period_start": p_start,
        "period_end": p_end,
        "online_ttl": ONLINE_TTL_SEC,
        "bucket_sec": BUCKET_SEC,
        "statuses": catalog,
        "groups": groups_out,
        "users": packed,
        "me": me,
        "summary": summary,
    }


def activity_snapshot(
    me_id: int | None = None,
    period: str | None = "today",
    from_ts: int | None = None,
    to_ts: int | None = None,
) -> dict[str, Any]:
    """Hours from local DB only — never calls amoCRM."""
    ensure_tables()
    seen, last_active = _presence_maps()
    since = int(time.time()) - ACTIVITY_KEEP_DAYS * 86400
    activity = _activity_since(since)
    now = int(time.time())
    today_start, today_end = day_bounds(0, 1)
    week_start, _week_end = day_bounds(6, 7)
    p_start, p_end, p_code = period_bounds(period, from_ts, to_ts)
    packed: list[dict[str, Any]] = []
    ids = set(activity) | set(seen)
    if me_id:
        ids.add(int(me_id))
    for uid in ids:
        buckets = activity.get(uid) or []
        first_ts, last_ts = _first_last(buckets, p_start, p_end)
        packed.append(
            {
                "id": int(uid),
                "name": f"User {uid}",
                "email": "",
                "phone": "",
                "role": "",
                "is_admin": False,
                "group_id": 0,
                "group_name": "Без группы",
                "online": (now - int(seen.get(uid) or 0)) <= ONLINE_TTL_SEC,
                "status": "",
                "leads": 0,
                "last_seen": int(seen.get(uid) or 0),
                "last_active": int(last_active.get(uid) or 0),
                "buckets": buckets,
                "hours_today": _hours_in_range(buckets, today_start, today_end),
                "hours_week": _hours_in_range(buckets, week_start, today_end),
                "hours_period": _hours_in_range(buckets, p_start, p_end),
                "first_active_today": first_ts,
                "last_active_today": last_ts,
                "today": {},
                "week": {},
                "period": {},
            }
        )
    me = next((x for x in packed if me_id and x["id"] == int(me_id)), None)
    return {
        "ok": True,
        "ts": now,
        "tz": "Asia/Tashkent",
        "day_start": today_start,
        "week_start": week_start,
        "period": p_code,
        "period_start": p_start,
        "period_end": p_end,
        "online_ttl": ONLINE_TTL_SEC,
        "bucket_sec": BUCKET_SEC,
        "statuses": load_statuses(),
        "groups": [{"id": 0, "name": "Без группы"}] if packed else [],
        "users": packed,
        "me": me,
        "summary": {
            "total": len(packed),
            "online": sum(1 for x in packed if x.get("online")),
            "hours_today": round(sum(float(x.get("hours_today") or 0) for x in packed), 1),
            "hours_week": round(sum(float(x.get("hours_week") or 0) for x in packed), 1),
            "hours_period": round(sum(float(x.get("hours_period") or 0) for x in packed), 1),
        },
    }
