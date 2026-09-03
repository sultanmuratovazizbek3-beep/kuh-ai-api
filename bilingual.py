"""Helpers for RU + UZ bilingual report/assistant text."""

from __future__ import annotations

from typing import Any


def pack_bilingual(ru: str, uz: str) -> str:
    ru = (ru or "").strip()
    uz = (uz or "").strip()
    if ru and uz:
        return f"🇷🇺 {ru}\n🇺🇿 {uz}"
    return ru or uz or "—"


def ensure_bilingual_fields(obj: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    """
    If model returned only Russian in field X, leave as is.
    Prefer fields: summary_ru/summary_uz or nested bilingual.
    """
    out = dict(obj)
    for f in fields:
        ru = out.get(f"{f}_ru") or out.get(f)
        uz = out.get(f"{f}_uz")
        if isinstance(ru, str) and isinstance(uz, str) and uz.strip():
            out[f] = pack_bilingual(ru, uz)
        elif isinstance(ru, list) and isinstance(uz, list):
            # parallel lists
            merged = []
            for i in range(max(len(ru), len(uz))):
                a = ru[i] if i < len(ru) else ""
                b = uz[i] if i < len(uz) else ""
                merged.append(pack_bilingual(str(a), str(b)))
            out[f] = merged
    return out


# Common UZ phrases for offline heuristic coach
UZ = {
    "greet": "Assalomu alaykum! Kimyo Hospital klinikasi. Sizga qanday yordam bera olaman?",
    "need": "Nima bezovta qilyapti va qachon qabulga yozilish qulay?",
    "slots": "Yaqin kunlardagi bo'sh vaqtlarni taklif qila olaman — ertalab yoki kunduzi qulaymi?",
    "price": "Narx haqida tushunaman. Tashxis shifokorga aniq reja tuzishga yordam beradi. Nima kirishini aytib beraman.",
    "next": "Keyingi qadam: yozuv / qayta qo'ng'iroq sanasi / CRM vazifasi.",
    "no_greeting": "Aniq salomlashish yo'q",
    "no_need": "Ehtiyoj aniqlanmagan",
    "no_next": "Aniq keyingi qadam yo'q",
    "short_call": "Juda qisqa qayd / suhbat",
    "empathy": "Empatiya bor",
    "booking": "Yozuv / keyingi qadam bor",
}
