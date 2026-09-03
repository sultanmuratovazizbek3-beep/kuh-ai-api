from __future__ import annotations

from typing import Type

from crm.amocrm_adapter import AmoCrmAdapter
from crm.base import CrmAdapter, CrmCredentials
from crm.bitrix24_adapter import Bitrix24Adapter

_PROVIDERS: dict[str, Type[CrmAdapter]] = {
    "amocrm": AmoCrmAdapter,
    "kommo": AmoCrmAdapter,
    "bitrix24": Bitrix24Adapter,
}


def list_providers() -> list[dict[str, str]]:
    return [
        {"id": "amocrm", "name": "amoCRM / Kommo"},
        {"id": "bitrix24", "name": "Bitrix24"},
    ]


def get_adapter(creds: CrmCredentials) -> CrmAdapter:
    key = (creds.provider or "amocrm").lower().strip()
    cls = _PROVIDERS.get(key)
    if not cls:
        raise ValueError(f"Неизвестный CRM: {key}. Доступно: {', '.join(_PROVIDERS)}")
    return cls(creds)
