"""amoCRM / Kommo adapter."""

from __future__ import annotations

import time
from typing import Any

import requests

from crm.base import CrmAdapter, CrmCredentials, CrmLead, CrmNote, CrmUser


class AmoCrmAdapter(CrmAdapter):
    provider = "amocrm"
    display_name = "amoCRM / Kommo"

    def __init__(self, creds: CrmCredentials) -> None:
        super().__init__(creds)
        sub = creds.subdomain.strip()
        if sub.endswith(".amocrm.ru"):
            sub = sub.replace(".amocrm.ru", "")
        if sub.endswith(".kommo.com"):
            sub = sub.replace(".kommo.com", "")
        self.subdomain = sub
        domain = creds.extra.get("domain") or "amocrm.ru"
        self.base_url = creds.base_url or f"https://{sub}.{domain}"
        self._token = creds.long_lived_token or creds.api_token
        self._access: str | None = None
        self._exp = 0.0

    def _auth_header(self) -> dict[str, str]:
        token = self._token
        if not token and self.creds.refresh_token:
            token = self._refresh()
        if not token:
            raise RuntimeError("Нет токена amoCRM (long_lived_token / refresh)")
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def _refresh(self) -> str:
        if self._access and time.time() < self._exp - 60:
            return self._access
        r = requests.post(
            f"{self.base_url}/oauth2/access_token",
            json={
                "client_id": self.creds.client_id,
                "client_secret": self.creds.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": self.creds.refresh_token,
                "redirect_uri": self.creds.redirect_uri,
            },
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        self._access = data["access_token"]
        self._exp = time.time() + int(data.get("expires_in", 86400))
        return self._access

    def _get(self, path: str, params: dict | None = None) -> Any:
        r = requests.get(
            f"{self.base_url}{path}",
            headers=self._auth_header(),
            params=params,
            timeout=45,
        )
        if r.status_code == 204:
            return None
        r.raise_for_status()
        if not r.text:
            return None
        return r.json()

    def test_connection(self) -> dict[str, Any]:
        try:
            acc = self._get("/api/v4/account") or {}
            return {
                "ok": True,
                "account_name": acc.get("name") or self.subdomain,
                "id": acc.get("id"),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def list_users(self) -> list[CrmUser]:
        users: list[CrmUser] = []
        page = 1
        while page <= 10:
            data = self._get("/api/v4/users", {"page": page, "limit": 250})
            batch = (data or {}).get("_embedded", {}).get("users") or []
            if not batch:
                break
            for u in batch:
                users.append(
                    CrmUser(
                        id=str(u.get("id")),
                        name=u.get("name") or f"User {u.get('id')}",
                        email=u.get("email") or "",
                    )
                )
            if len(batch) < 250:
                break
            page += 1
        return users

    def list_recent_leads(self, *, hours: int = 72, limit: int = 50) -> list[CrmLead]:
        since = int(time.time()) - hours * 3600
        users = {u.id: u.name for u in self.list_users()}
        out: list[CrmLead] = []
        page = 1
        while page <= 20 and len(out) < limit:
            data = self._get(
                "/api/v4/leads",
                {
                    "page": page,
                    "limit": min(250, limit),
                    "filter[updated_at][from]": since,
                    "with": "contacts",
                },
            )
            batch = (data or {}).get("_embedded", {}).get("leads") or []
            if not batch:
                break
            for lead in batch:
                out.append(self._map_lead(lead, users))
                if len(out) >= limit:
                    break
            if len(batch) < 250:
                break
            page += 1
        return out

    def get_lead(self, lead_id: str) -> CrmLead | None:
        try:
            data = self._get(f"/api/v4/leads/{lead_id}", {"with": "contacts"})
        except Exception:
            return None
        if not data:
            return None
        users = {u.id: u.name for u in self.list_users()}
        return self._map_lead(data, users)

    def get_lead_notes(self, lead_id: str, limit: int = 100) -> list[CrmNote]:
        try:
            data = self._get(
                f"/api/v4/leads/{lead_id}/notes",
                {"limit": min(limit, 250), "page": 1},
            )
        except Exception:
            return []
        notes = (data or {}).get("_embedded", {}).get("notes") or []
        out: list[CrmNote] = []
        for n in notes:
            params = n.get("params") or {}
            text = params.get("text") or ""
            ntype = n.get("note_type") or "common"
            kind = "call" if "call" in ntype else "note"
            out.append(
                CrmNote(
                    id=str(n.get("id")),
                    text=text if isinstance(text, str) else "",
                    created_at=int(n.get("created_at") or 0),
                    kind=kind,
                    recording_url=str(params.get("link") or ""),
                    duration=int(params.get("duration") or 0),
                    direction="in"
                    if ntype.endswith("_in")
                    else ("out" if ntype.endswith("_out") else ""),
                )
            )
        return out

    def lead_url(self, lead_id: str) -> str:
        return f"{self.base_url}/leads/detail/{lead_id}"

    def _map_lead(self, lead: dict[str, Any], users: dict[str, str]) -> CrmLead:
        lid = str(lead.get("id"))
        rid = str(lead.get("responsible_user_id") or "")
        status_id = str(lead.get("status_id") or "")
        # default amo won/lost
        is_won = status_id == "142"
        is_lost = status_id == "143"
        return CrmLead(
            id=lid,
            name=lead.get("name") or f"#{lid}",
            responsible_name=users.get(rid, rid or "—"),
            responsible_id=rid,
            status_id=status_id,
            status_name=status_id,
            price=float(lead.get("price") or 0),
            updated_at=int(lead.get("updated_at") or 0),
            is_won=is_won,
            is_lost=is_lost,
            url=self.lead_url(lid),
            raw=lead,
        )
