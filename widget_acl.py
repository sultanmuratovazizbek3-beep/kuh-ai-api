"""Widget access control (who may use AI helper in amoCRM)."""

from __future__ import annotations

import json
from typing import Any

from storage import db, init_db

META_KEY = "widget_acl"
MODES = ("admins_only", "all_managers", "selected")


def _ensure() -> None:
    init_db()
    with db() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)"
        )


def default_acl() -> dict[str, Any]:
    return {
        "access_mode": "admins_only",
        "allowed_user_ids": [],
        "updated_at": 0,
    }


def load_acl() -> dict[str, Any]:
    _ensure()
    with db() as conn:
        row = conn.execute(
            "SELECT value FROM meta WHERE key = ?", (META_KEY,)
        ).fetchone()
    if not row or not row["value"]:
        return default_acl()
    try:
        data = json.loads(row["value"])
    except Exception:
        return default_acl()
    mode = str(data.get("access_mode") or "admins_only")
    if mode not in MODES:
        mode = "admins_only"
    ids: list[int] = []
    for x in data.get("allowed_user_ids") or []:
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            continue
    return {
        "access_mode": mode,
        "allowed_user_ids": ids,
        "updated_at": int(data.get("updated_at") or 0),
    }


def save_acl(
    *,
    access_mode: str,
    allowed_user_ids: list[int] | None = None,
) -> dict[str, Any]:
    import time

    _ensure()
    mode = access_mode if access_mode in MODES else "admins_only"
    ids = []
    for x in allowed_user_ids or []:
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            continue
    # unique preserve order
    seen: set[int] = set()
    uniq: list[int] = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            uniq.append(i)
    payload = {
        "access_mode": mode,
        "allowed_user_ids": uniq,
        "updated_at": int(time.time()),
    }
    with db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
            (META_KEY, json.dumps(payload, ensure_ascii=False)),
        )
    return payload


def user_allowed(
    *,
    user_id: int | None,
    is_admin: bool,
    acl: dict[str, Any] | None = None,
) -> bool:
    """Server-side check (optional). Admins always allowed."""
    if is_admin:
        return True
    a = acl or load_acl()
    mode = a.get("access_mode") or "admins_only"
    if mode == "admins_only":
        return False
    if mode == "all_managers":
        return user_id is not None and int(user_id) > 0
    if mode == "selected":
        if user_id is None:
            return False
        return int(user_id) in set(a.get("allowed_user_ids") or [])
    return False
