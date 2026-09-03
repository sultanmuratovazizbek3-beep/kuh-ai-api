"""Bitrix24 adapter (incoming webhook REST)."""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urljoin

import requests

from crm.base import CrmAdapter, CrmCredentials, CrmLead, CrmNote, CrmUser


class Bitrix24Adapter(CrmAdapter):
    provider = "bitrix24"
    display_name = "Bitrix24"

    def __init__(self, creds: CrmCredentials) -> None:
        super().__init__(creds)
        wh = (creds.webhook_url or creds.base_url or "").strip()
        if wh and not wh.endswith("/"):
            wh += "/"
        self.webhook = wh

    def _call(self, method: str, params: dict | None = None) -> Any:
        if not self.webhook:
            raise RuntimeError("Укажите webhook_url Bitrix24")
        url = urljoin(self.webhook, method + ".json")
        r = requests.post(url, json=params or {}, timeout=45)
        r.raise_for_status()
        data = r.json()
        if data.get("error"):
            raise RuntimeError(f"{data.get('error')}: {data.get('error_description')}")
        return data.get("result")

    def test_connection(self) -> dict[str, Any]:
        try:
            app = self._call("app.info") or {}
            profile = self._call("profile") or {}
            return {
                "ok": True,
                "account_name": profile.get("NAME")
                or app.get("CODE")
                or "Bitrix24",
                "id": profile.get("ID"),
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def list_users(self) -> list[CrmUser]:
        result = self._call("user.get", {"ACTIVE": True}) or []
        if isinstance(result, dict):
            result = list(result.values()) if result else []
        users = []
        for u in result:
            name = " ".join(
                x
                for x in [u.get("NAME") or "", u.get("LAST_NAME") or ""]
                if x
            ).strip() or f"User {u.get('ID')}"
            users.append(
                CrmUser(
                    id=str(u.get("ID")),
                    name=name,
                    email=u.get("EMAIL") or "",
                )
            )
        return users

    def list_recent_leads(self, *, hours: int = 72, limit: int = 50) -> list[CrmLead]:
        users = {u.id: u.name for u in self.list_users()}
        # Bitrix deals (crm.deal.list) as "leads" for sales pipeline
        since = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - hours * 3600))
        result = (
            self._call(
                "crm.deal.list",
                {
                    "order": {"DATE_MODIFY": "DESC"},
                    "filter": {">=DATE_MODIFY": since},
                    "select": [
                        "ID",
                        "TITLE",
                        "STAGE_ID",
                        "OPPORTUNITY",
                        "ASSIGNED_BY_ID",
                        "DATE_MODIFY",
                        "CLOSED",
                    ],
                    "start": 0,
                },
            )
            or []
        )
        out: list[CrmLead] = []
        for d in result[:limit]:
            out.append(self._map_deal(d, users))
        return out

    def get_lead(self, lead_id: str) -> CrmLead | None:
        users = {u.id: u.name for u in self.list_users()}
        d = self._call("crm.deal.get", {"id": lead_id})
        if not d:
            return None
        return self._map_deal(d, users)

    def get_lead_notes(self, lead_id: str, limit: int = 100) -> list[CrmNote]:
        # Timeline comments
        try:
            result = (
                self._call(
                    "crm.timeline.comment.list",
                    {
                        "filter": {
                            "ENTITY_ID": lead_id,
                            "ENTITY_TYPE": "deal",
                        },
                        "order": {"ID": "DESC"},
                    },
                )
                or []
            )
        except Exception:
            result = []
        out: list[CrmNote] = []
        for n in result[:limit]:
            out.append(
                CrmNote(
                    id=str(n.get("ID")),
                    text=str(n.get("COMMENT") or ""),
                    created_at=0,
                    kind="note",
                )
            )
        return out

    def lead_url(self, lead_id: str) -> str:
        # Best-effort: derive portal from webhook
        # https://domain.bitrix24.ru/rest/1/xxx/ → https://domain.bitrix24.ru/crm/deal/details/ID/
        portal = self.webhook
        for marker in ("/rest/",):
            if marker in portal:
                portal = portal.split(marker)[0]
                break
        return f"{portal}/crm/deal/details/{lead_id}/"

    def _map_deal(self, d: dict[str, Any], users: dict[str, str]) -> CrmLead:
        lid = str(d.get("ID"))
        rid = str(d.get("ASSIGNED_BY_ID") or "")
        stage = str(d.get("STAGE_ID") or "")
        closed = str(d.get("CLOSED") or "N").upper() == "Y"
        is_won = "WON" in stage.upper() or stage.endswith(":WON")
        is_lost = "LOSE" in stage.upper() or stage.endswith(":LOSE")
        return CrmLead(
            id=lid,
            name=d.get("TITLE") or f"Deal #{lid}",
            responsible_name=users.get(rid, rid or "—"),
            responsible_id=rid,
            status_id=stage,
            status_name=stage,
            price=float(d.get("OPPORTUNITY") or 0),
            updated_at=int(time.time()),
            is_won=is_won or (closed and is_won),
            is_lost=is_lost,
            url=self.lead_url(lid),
            raw=d,
        )
