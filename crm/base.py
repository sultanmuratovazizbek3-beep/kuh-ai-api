"""Abstract CRM connector — implement for each CRM vendor."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CrmCredentials:
    """Generic connection settings (fields used depend on provider)."""

    provider: str  # amocrm | bitrix24 | custom
    label: str = "Default"
    # amoCRM
    subdomain: str = ""
    long_lived_token: str = ""
    client_id: str = ""
    client_secret: str = ""
    refresh_token: str = ""
    redirect_uri: str = "https://example.com"
    # Bitrix24
    webhook_url: str = ""  # https://portal.bitrix24.ru/rest/1/xxx/
    # Common
    base_url: str = ""
    api_token: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "label": self.label,
            "subdomain": self.subdomain,
            "long_lived_token": self.long_lived_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
            "redirect_uri": self.redirect_uri,
            "webhook_url": self.webhook_url,
            "base_url": self.base_url,
            "api_token": self.api_token,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CrmCredentials":
        return cls(
            provider=str(d.get("provider") or "amocrm"),
            label=str(d.get("label") or "Default"),
            subdomain=str(d.get("subdomain") or ""),
            long_lived_token=str(d.get("long_lived_token") or ""),
            client_id=str(d.get("client_id") or ""),
            client_secret=str(d.get("client_secret") or ""),
            refresh_token=str(d.get("refresh_token") or ""),
            redirect_uri=str(d.get("redirect_uri") or "https://example.com"),
            webhook_url=str(d.get("webhook_url") or ""),
            base_url=str(d.get("base_url") or ""),
            api_token=str(d.get("api_token") or ""),
            extra=dict(d.get("extra") or {}),
        )


@dataclass
class CrmLead:
    id: str
    name: str
    responsible_name: str = ""
    responsible_id: str = ""
    status_name: str = ""
    status_id: str = ""
    price: float = 0
    updated_at: int = 0
    is_won: bool = False
    is_lost: bool = False
    url: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class CrmUser:
    id: str
    name: str
    email: str = ""


@dataclass
class CrmNote:
    id: str
    text: str
    created_at: int = 0
    kind: str = "note"
    recording_url: str = ""
    duration: int = 0
    direction: str = ""


class CrmAdapter(ABC):
    provider: str = "base"
    display_name: str = "CRM"

    def __init__(self, creds: CrmCredentials) -> None:
        self.creds = creds

    @abstractmethod
    def test_connection(self) -> dict[str, Any]:
        """Return {ok, account_name?, error?}."""

    @abstractmethod
    def list_users(self) -> list[CrmUser]:
        ...

    @abstractmethod
    def list_recent_leads(self, *, hours: int = 72, limit: int = 50) -> list[CrmLead]:
        ...

    @abstractmethod
    def get_lead(self, lead_id: str) -> CrmLead | None:
        ...

    @abstractmethod
    def get_lead_notes(self, lead_id: str, limit: int = 100) -> list[CrmNote]:
        ...

    def lead_url(self, lead_id: str) -> str:
        return ""
