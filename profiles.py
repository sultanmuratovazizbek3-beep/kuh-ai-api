"""Multi-CRM connection profiles stored as JSON (portable, per-machine)."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from crm.base import CrmCredentials

APP_NAME = "CRMAIDesk"


def app_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    p = Path(base) / APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    (p / "data").mkdir(exist_ok=True)
    (p / "logs").mkdir(exist_ok=True)
    return p


def profiles_path() -> Path:
    return app_data_dir() / "profiles.json"


def load_store() -> dict[str, Any]:
    path = profiles_path()
    if not path.exists():
        # migrate from project .env amo if present
        return {"active_id": None, "profiles": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"active_id": None, "profiles": []}


def save_store(store: dict[str, Any]) -> None:
    path = profiles_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def list_profiles() -> list[dict[str, Any]]:
    store = load_store()
    # redact secrets for UI list
    out = []
    for p in store.get("profiles") or []:
        out.append(
            {
                "id": p.get("id"),
                "label": p.get("label"),
                "provider": p.get("provider"),
                "subdomain": p.get("subdomain"),
                "webhook_url": _mask(p.get("webhook_url") or ""),
                "has_token": bool(p.get("long_lived_token") or p.get("api_token") or p.get("refresh_token") or p.get("webhook_url")),
            }
        )
    return out


def _mask(s: str) -> str:
    if len(s) < 12:
        return "***" if s else ""
    return s[:18] + "…"


def get_profile(profile_id: str | None = None) -> dict[str, Any] | None:
    store = load_store()
    pid = profile_id or store.get("active_id")
    for p in store.get("profiles") or []:
        if p.get("id") == pid:
            return p
    profiles = store.get("profiles") or []
    return profiles[0] if profiles else None


def get_credentials(profile_id: str | None = None) -> CrmCredentials | None:
    p = get_profile(profile_id)
    if not p:
        return None
    return CrmCredentials.from_dict(p)


def upsert_profile(data: dict[str, Any]) -> str:
    import uuid

    store = load_store()
    profiles: list = store.setdefault("profiles", [])
    pid = data.get("id") or str(uuid.uuid4())[:8]
    data["id"] = pid
    found = False
    for i, p in enumerate(profiles):
        if p.get("id") == pid:
            # keep secrets if blank in update
            merged = dict(p)
            for k, v in data.items():
                if v in ("", None) and k in (
                    "long_lived_token",
                    "client_secret",
                    "refresh_token",
                    "api_token",
                    "webhook_url",
                ):
                    continue
                merged[k] = v
            profiles[i] = merged
            found = True
            break
    if not found:
        profiles.append(data)
    if not store.get("active_id"):
        store["active_id"] = pid
    save_store(store)
    return pid


def set_active(profile_id: str) -> None:
    store = load_store()
    store["active_id"] = profile_id
    save_store(store)


def delete_profile(profile_id: str) -> None:
    store = load_store()
    store["profiles"] = [p for p in (store.get("profiles") or []) if p.get("id") != profile_id]
    if store.get("active_id") == profile_id:
        store["active_id"] = (store["profiles"][0]["id"] if store["profiles"] else None)
    save_store(store)


def import_from_env(env_path: Path | None = None) -> str | None:
    """One-shot import of existing .env amoCRM settings."""
    from dotenv import dotenv_values

    candidates = []
    if env_path:
        candidates.append(env_path)
    candidates.append(Path(__file__).resolve().parent / ".env")
    for p in candidates:
        if p.exists():
            vals = dotenv_values(p)
            if vals.get("AMO_SUBDOMAIN") or vals.get("AMO_LONG_LIVED_TOKEN"):
                pid = upsert_profile(
                    {
                        "provider": "amocrm",
                        "label": f"amoCRM {vals.get('AMO_SUBDOMAIN') or 'import'}",
                        "subdomain": vals.get("AMO_SUBDOMAIN") or "",
                        "long_lived_token": vals.get("AMO_LONG_LIVED_TOKEN") or "",
                        "client_id": vals.get("AMO_CLIENT_ID") or "",
                        "client_secret": vals.get("AMO_CLIENT_SECRET") or "",
                        "refresh_token": vals.get("AMO_REFRESH_TOKEN") or "",
                        "redirect_uri": vals.get("AMO_REDIRECT_URI") or "https://example.com",
                    }
                )
                set_active(pid)
                return pid
    return None
