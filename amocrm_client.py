"""AmoCRM REST API v4 client for analytics."""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from config import (
    AMO_CLIENT_ID,
    AMO_CLIENT_SECRET,
    AMO_LONG_LIVED_TOKEN,
    AMO_REDIRECT_URI,
    AMO_REFRESH_TOKEN,
    AMO_SUBDOMAIN,
)

logger = logging.getLogger(__name__)


def _active_amo_settings() -> dict[str, str]:
    """Prefer active Desk CRM profile; fall back to .env / config."""
    try:
        from profiles import get_profile

        p = get_profile() or {}
        if p.get("provider", "amocrm") == "amocrm" and (
            p.get("long_lived_token") or p.get("refresh_token") or p.get("subdomain")
        ):
            sub = (p.get("subdomain") or "").strip()
            if sub.endswith(".amocrm.ru"):
                sub = sub.replace(".amocrm.ru", "")
            if sub.endswith(".kommo.com"):
                sub = sub.replace(".kommo.com", "")
            return {
                "subdomain": sub or AMO_SUBDOMAIN,
                "long_lived_token": (p.get("long_lived_token") or "").strip(),
                "client_id": (p.get("client_id") or "").strip(),
                "client_secret": (p.get("client_secret") or "").strip(),
                "refresh_token": (p.get("refresh_token") or "").strip(),
                "redirect_uri": (p.get("redirect_uri") or AMO_REDIRECT_URI or "https://example.com").strip(),
            }
    except Exception as exc:
        logger.debug("profile credentials unavailable: %s", exc)
    return {
        "subdomain": AMO_SUBDOMAIN,
        "long_lived_token": AMO_LONG_LIVED_TOKEN,
        "client_id": AMO_CLIENT_ID,
        "client_secret": AMO_CLIENT_SECRET,
        "refresh_token": AMO_REFRESH_TOKEN,
        "redirect_uri": AMO_REDIRECT_URI or "https://example.com",
    }


class AmoCRMClient:
    def __init__(self) -> None:
        cfg = _active_amo_settings()
        sub = cfg["subdomain"]
        if not sub:
            raise RuntimeError(
                "Нет AMO_SUBDOMAIN: создайте интеграцию в amoCRM и сохраните профиль в Desk → CRM"
            )
        self.base_url = f"https://{sub}.amocrm.ru"
        self._cfg = cfg
        self.access_token: str | None = None
        self.token_expires_at = 0.0

    def _token(self) -> str:
        cfg = _active_amo_settings()
        self._cfg = cfg
        sub = cfg["subdomain"]
        if sub:
            self.base_url = f"https://{sub}.amocrm.ru"
        if cfg.get("long_lived_token"):
            return cfg["long_lived_token"]
        if self.access_token and time.time() < self.token_expires_at - 60:
            return self.access_token
        if not cfg.get("refresh_token"):
            raise RuntimeError(
                "Нет токена amoCRM: укажите долгосрочный токен новой интеграции в Desk → CRM"
            )

        response = requests.post(
            f"{self.base_url}/oauth2/access_token",
            json={
                "client_id": cfg["client_id"],
                "client_secret": cfg["client_secret"],
                "grant_type": "refresh_token",
                "refresh_token": cfg["refresh_token"],
                "redirect_uri": cfg["redirect_uri"],
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        self.access_token = payload["access_token"]
        self.token_expires_at = time.time() + int(payload.get("expires_in", 86400))
        logger.info("AmoCRM access token refreshed")
        return self.access_token  # type: ignore[return-value]

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any | None = None,
        params: dict[str, Any] | None = None,
        timeout: int = 60,
    ) -> Any:
        token = self._token()
        response = requests.request(
            method,
            f"{self.base_url}{path}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=json,
            params=params,
            timeout=timeout,
        )
        if response.status_code == 204:
            return None
        if response.status_code >= 400:
            # 404 is often expected (deleted notes / wrong entity path)
            log = logger.debug if response.status_code == 404 else logger.error
            log(
                "AmoCRM %s %s -> %s: %s",
                method,
                path,
                response.status_code,
                response.text[:500],
            )
            response.raise_for_status()
        if not response.text:
            return None
        return response.json()

    def get_account(self) -> dict[str, Any]:
        return self._request("GET", "/api/v4/account") or {}

    def get_users(self, with_embed: str = "role,group", timeout: int = 60) -> list[dict[str, Any]]:
        users: list[dict[str, Any]] = []
        page = 1
        while True:
            data = self._request(
                "GET",
                "/api/v4/users",
                params={"page": page, "limit": 250, "with": with_embed},
                timeout=timeout,
            )
            if not data:
                break
            batch = data.get("_embedded", {}).get("users", [])
            if not batch:
                break
            users.extend(batch)
            if len(batch) < 250:
                break
            page += 1
        return users

    def get_user_groups(self) -> list[dict[str, Any]]:
        try:
            data = self._request("GET", "/api/v4/users/groups") or {}
        except Exception:
            return []
        embedded = data.get("_embedded") or {}
        return (
            embedded.get("groups")
            or embedded.get("user_groups")
            or embedded.get("users_groups")
            or []
        )

    def count_leads_for_user(self, user_id: int) -> int:
        """Open+closed total of leads where user is responsible. Uses X-Total-Count."""
        token = self._token()
        response = requests.get(
            f"{self.base_url}/api/v4/leads",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            params={"limit": 1, "filter[responsible_user_id]": int(user_id)},
            timeout=30,
        )
        if response.status_code >= 400:
            return 0
        header = response.headers.get("X-Total-Count") or response.headers.get(
            "x-total-count"
        )
        if header:
            try:
                return int(header)
            except (TypeError, ValueError):
                return 0
        if not response.text:
            return 0
        data = response.json()
        return len((data.get("_embedded") or {}).get("leads") or [])

    def get_pipelines(self) -> list[dict[str, Any]]:
        data = self._request("GET", "/api/v4/leads/pipelines")
        if not data:
            return []
        return data.get("_embedded", {}).get("pipelines", [])

    def iter_events(
        self,
        *,
        created_from: int,
        created_to: int | None = None,
        event_types: list[str] | None = None,
        limit: int = 100,
        max_pages: int = 50,
    ):
        """Yield event dicts between timestamps."""
        page = 1
        while page <= max_pages:
            params: dict[str, Any] = {
                "page": page,
                "limit": limit,
                "filter[created_at][from]": created_from,
            }
            if created_to is not None:
                params["filter[created_at][to]"] = created_to
            if event_types:
                for i, t in enumerate(event_types):
                    params[f"filter[type][{i}]"] = t

            data = self._request("GET", "/api/v4/events", params=params)
            if not data:
                break
            events = data.get("_embedded", {}).get("events", [])
            if not events:
                break
            for ev in events:
                yield ev
            if len(events) < limit:
                break
            page += 1

    def get_notes(
        self,
        entity_type: str,
        *,
        note_types: list[str] | None = None,
        updated_from: int | None = None,
        updated_to: int | None = None,
        page: int = 1,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"page": page, "limit": limit}
        if note_types:
            for i, t in enumerate(note_types):
                params[f"filter[note_type][{i}]"] = t
        if updated_from is not None:
            params["filter[updated_at][from]"] = updated_from
        if updated_to is not None:
            params["filter[updated_at][to]"] = updated_to
        data = self._request("GET", f"/api/v4/{entity_type}/notes", params=params)
        if not data:
            return []
        return data.get("_embedded", {}).get("notes", [])

    def iter_notes(
        self,
        entity_type: str,
        *,
        note_types: list[str] | None = None,
        updated_from: int | None = None,
        updated_to: int | None = None,
        max_pages: int = 30,
    ):
        page = 1
        while page <= max_pages:
            batch = self.get_notes(
                entity_type,
                note_types=note_types,
                updated_from=updated_from,
                updated_to=updated_to,
                page=page,
                limit=100,
            )
            if not batch:
                break
            for note in batch:
                yield note
            if len(batch) < 100:
                break
            page += 1

    @staticmethod
    def _entity_path(entity_type: str) -> str:
        """Map event entity_type (lead/contact) to API path (leads/contacts)."""
        mapping = {
            "lead": "leads",
            "leads": "leads",
            "contact": "contacts",
            "contacts": "contacts",
            "company": "companies",
            "companies": "companies",
            "customer": "customers",
            "customers": "customers",
        }
        return mapping.get(entity_type, entity_type)

    def get_note(self, entity_type: str, note_id: int) -> dict[str, Any] | None:
        path_type = self._entity_path(entity_type)
        try:
            return self._request("GET", f"/api/v4/{path_type}/notes/{note_id}")
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                return None
            raise

    def get_leads(
        self,
        *,
        updated_from: int | None = None,
        updated_to: int | None = None,
        created_from: int | None = None,
        created_to: int | None = None,
        responsible_user_id: int | None = None,
        page: int = 1,
        limit: int = 250,
        with_params: str = "contacts",
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "page": page,
            "limit": limit,
            "with": with_params,
        }
        if updated_from is not None:
            params["filter[updated_at][from]"] = updated_from
        if updated_to is not None:
            params["filter[updated_at][to]"] = updated_to
        if created_from is not None:
            params["filter[created_at][from]"] = created_from
        if created_to is not None:
            params["filter[created_at][to]"] = created_to
        if responsible_user_id is not None:
            params["filter[responsible_user_id]"] = responsible_user_id
        data = self._request("GET", "/api/v4/leads", params=params)
        if not data:
            return []
        return data.get("_embedded", {}).get("leads", [])

    def iter_leads(self, **kwargs: Any):
        page = 1
        max_pages = int(kwargs.pop("max_pages", 40))
        while page <= max_pages:
            batch = self.get_leads(page=page, **kwargs)
            if not batch:
                break
            for lead in batch:
                yield lead
            if len(batch) < 250:
                break
            page += 1

    def get_lead(self, lead_id: int) -> dict[str, Any] | None:
        return self._request(
            "GET", f"/api/v4/leads/{lead_id}", params={"with": "contacts"}
        )

    def get_talks(
        self,
        *,
        page: int = 1,
        limit: int = 100,
        only_in_work: bool = False,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"page": page, "limit": limit}
        if only_in_work:
            params["filter[only_in_work]"] = 1
        data = self._request("GET", "/api/v4/talks", params=params)
        if not data:
            return []
        return data.get("_embedded", {}).get("talks", [])

    def add_note_to_lead(self, lead_id: int, text: str) -> Any:
        """Write analysis note back into the lead card."""
        payload = [
            {
                "entity_id": lead_id,
                "note_type": "common",
                "params": {"text": text},
            }
        ]
        return self._request("POST", "/api/v4/leads/notes", json=payload)
