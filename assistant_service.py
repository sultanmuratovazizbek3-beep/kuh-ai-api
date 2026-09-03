"""Lead assistant: real transcripts + bilingual RU/UZ coaching."""

from __future__ import annotations

import logging
import re
from typing import Any

from amocrm_client import AmoCRMClient
from analyzer import _ai_analyze, _heuristic_analyze
from bilingual import UZ, pack_bilingual
from config import LOST_STATUS_IDS, WON_STATUS_IDS, XAI_API_KEY, XAI_BASE_URL, XAI_MODEL
from medical_coach import MEDICAL_SYSTEM_RU_UZ, PHRASES, detect_services, is_urgent
from storage import db, init_db, list_managers, manager_name_map, upsert_lead

logger = logging.getLogger(__name__)

COACH_SYSTEM = MEDICAL_SYSTEM_RU_UZ + """

Ответ СТРОГО JSON без markdown:
{
  "score": 0-10,
  "summary_ru": "что происходит с пациентом/сделкой",
  "summary_uz": "bemor/bitim bilan nima bo'lyapti",
  "stage_hint_ru": "этап",
  "stage_hint_uz": "bosqich",
  "risks_ru": ["..."],
  "risks_uz": ["..."],
  "next_steps_ru": ["что сделать СЕЙЧАС"],
  "next_steps_uz": ["HOZIR nima qilish"],
  "suggested_replies_ru": ["фраза пациенту 1", "фраза 2"],
  "suggested_replies_uz": ["bemorga ibora 1", "ibora 2"],
  "questions_to_ask_ru": ["..."],
  "questions_to_ask_uz": ["..."],
  "objections": [
    {"objection_ru":"...", "objection_uz":"...", "answer_ru":"...", "answer_uz":"..."}
  ],
  "do_not_ru": ["..."],
  "do_not_uz": ["..."],
  "service_hint_ru": "услуга/врач",
  "service_hint_uz": "xizmat/shifokor",
  "quality": {
    "strengths_ru": "...", "strengths_uz": "...",
    "weaknesses_ru": "...", "weaknesses_uz": "..."
  },
  "transcript_quotes_ru": ["цитата"],
  "transcript_quotes_uz": ["iqtibos"]
}
"""


def _join_texts(items: list[dict[str, Any]], limit: int = 15) -> str:
    chunks: list[str] = []
    for it in items[:limit]:
        kind = it.get("kind") or it.get("note_type") or "note"
        direction = it.get("direction") or ""
        ts = it.get("created_at") or ""
        text = (it.get("transcript") or it.get("text") or "").strip()
        if not text or text.startswith("[call_recording]") or text.startswith("["):
            continue
        chunks.append(f"[{kind} {direction} @ {ts}]\n{text[:3500]}")
    return "\n\n---\n\n".join(chunks)


def _parse_coach_json(content: str) -> dict[str, Any] | None:
    import json

    content = (content or "").strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", content)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None


def _bi_list(ru: list | None, uz: list | None) -> list[str]:
    ru = ru or []
    uz = uz or []
    out = []
    for i in range(max(len(ru), len(uz))):
        a = str(ru[i]) if i < len(ru) else ""
        b = str(uz[i]) if i < len(uz) else ""
        out.append(pack_bilingual(a, b))
    return out


def _normalize_coach(parsed: dict[str, Any], model: str) -> dict[str, Any]:
    q = parsed.get("quality") or {}
    objections = []
    for o in parsed.get("objections") or []:
        if not isinstance(o, dict):
            continue
        objections.append(
            {
                "objection": pack_bilingual(
                    str(o.get("objection_ru") or o.get("objection") or ""),
                    str(o.get("objection_uz") or ""),
                ),
                "answer": pack_bilingual(
                    str(o.get("answer_ru") or o.get("answer") or ""),
                    str(o.get("answer_uz") or ""),
                ),
            }
        )
    return {
        "score": float(parsed.get("score", 5)),
        "summary": pack_bilingual(
            str(parsed.get("summary_ru") or parsed.get("summary") or ""),
            str(parsed.get("summary_uz") or ""),
        ),
        "stage_hint": pack_bilingual(
            str(parsed.get("stage_hint_ru") or parsed.get("stage_hint") or ""),
            str(parsed.get("stage_hint_uz") or ""),
        ),
        "risks": _bi_list(parsed.get("risks_ru") or parsed.get("risks"), parsed.get("risks_uz")),
        "next_steps": _bi_list(
            parsed.get("next_steps_ru") or parsed.get("next_steps"),
            parsed.get("next_steps_uz"),
        ),
        "suggested_replies": _bi_list(
            parsed.get("suggested_replies_ru") or parsed.get("suggested_replies"),
            parsed.get("suggested_replies_uz"),
        ),
        "questions_to_ask": _bi_list(
            parsed.get("questions_to_ask_ru") or parsed.get("questions_to_ask"),
            parsed.get("questions_to_ask_uz"),
        ),
        "objections": objections,
        "do_not": _bi_list(parsed.get("do_not_ru") or parsed.get("do_not"), parsed.get("do_not_uz")),
        "quality": {
            "strengths": pack_bilingual(
                str(q.get("strengths_ru") or q.get("strengths") or ""),
                str(q.get("strengths_uz") or ""),
            ),
            "weaknesses": pack_bilingual(
                str(q.get("weaknesses_ru") or q.get("weaknesses") or ""),
                str(q.get("weaknesses_uz") or ""),
            ),
        },
        "service_hint": pack_bilingual(
            str(parsed.get("service_hint_ru") or ""),
            str(parsed.get("service_hint_uz") or ""),
        ),
        "transcript_quotes": _bi_list(
            parsed.get("transcript_quotes_ru"), parsed.get("transcript_quotes_uz")
        ),
        "model": model,
    }


def _heuristic_coach(text: str, lead: dict[str, Any] | None) -> dict[str, Any]:
    from medical_coach import detect_objections

    base = _heuristic_analyze(text or "нет текста", "call" if len(text or "") > 80 else "note")
    t = (text or "").lower()
    name = (lead or {}).get("name") or "сделка"
    services = detect_services(text or "")
    urgent = is_urgent(text or "")
    objections_found = detect_objections(text or "")
    booking = base.get("booking_result") or "unclear"
    flags = list(base.get("flags") or [])

    # Real KUH patterns from call mining
    loc_talk = bool(
        re.search(r"локац|адрес|как доех|мост|район|навигатор|где вы|manzil|qayerda", t)
    )
    wa_mess = bool(re.search(r"whatsapp|ватсап|телеграм|telegram|spam|спам", t))
    driving = bool(re.search(r"за рул|еду|рулем|rulda|ketayap", t))
    no_slot_words = not bool(
        re.search(
            r"запис\w* на|запишу|записаны|сегодня в|завтра в|yozib|soat \d|ertaga soat",
            t,
        )
    )
    ivr_heavy = bool(
        re.search(r"дождитесь ответа|оставайтесь на связи|on hold|please hold", t)
    )

    next_ru, next_uz = [], []
    if urgent:
        next_ru.append("СРОЧНО: не консультировать — приём / 103. Не продавать «обследование вместо скорой».")
        next_uz.append("SHOSHILINCH: maslahat bermang — qabul / 103. «Tekshiruv o'rniga tezkor» sotmang.")
        score_boost = -1.0 if base["score"] > 3 else 0
    else:
        score_boost = 0

    # Priority actions that actually move conversion
    if booking != "booked" and no_slot_words:
        next_ru.append(
            "Главный рычаг: назвать ДВА слота вслух («сегодня 15:00 / завтра 10:00») и ждать выбор. Без даты в CRM сделка почти не возвращается."
        )
        next_uz.append(
            "Asosiy: IKKITA slotni ovoz chiqarib ayting va tanlovni kuting. CRMda sanasiz bitim qaytmaydi."
        )
    if loc_talk or driving:
        next_ru.append(
            "Не диктовать дорогу 5 минут. Сначала запись → потом гео/SMS. За рулём — только «напишите Kimyo в WhatsApp / пришлю точку»."
        )
        next_uz.append(
            "5 daqiqa yo'l aytmang. Avval yozuv → keyin geo/SMS. Rulda — faqat «WhatsApp ga Kimyo yozing»."
        )
    if wa_mess:
        next_ru.append(
            "WhatsApp с корпоративного часто в спаме: клиент пишет первым «Kimyo», либо SMS-ссылка на карту."
        )
        next_uz.append(
            "Korporativ WhatsApp spam bo'ladi: mijoz birinchi «Kimyo» yozadi yoki SMS-xarita."
        )
    if booking == "booked":
        next_ru.append("CRM: дата+услуга+ФИО+тел; SMS-напоминание за 2ч; гео после подтверждения.")
        next_uz.append("CRM: sana+xizmat+F.I.Sh+tel; 2 soat oldin SMS; geo tasdiqdan keyin.")
    elif services:
        svc_ru = ", ".join(s[0] for s in services)
        svc_uz = ", ".join(s[1] for s in services)
        next_ru.append(f"Дожать запись: {svc_ru} — 2 слота + подтверждение вслух.")
        next_uz.append(f"Yozuv: {svc_uz} — 2 slot + ovozchiqarib tasdiq.")
    elif "missed_need" in flags:
        next_ru.append("1 вопрос: «Приём / УЗИ / МРТ / анализы?» → маршрут → 2 слота. Не болтать впустую.")
        next_uz.append("1 savol: «Qabul / UZI / MRT / tahlil?» → yo'nalish → 2 slot.")

    if "price" in objections_found or any(
        w in t for w in ("цен", "narx", "сколько", "сумм", "qimmat", "дорог")
    ):
        next_ru.append("Цена: сумма + что входит + закрыть слотом. Не спорить «мы лучше».")
        next_uz.append("Narx: summa + nima kiradi + slot. «Biz yaxshiroq» deb tortishmang.")
    if "think" in objections_found or "подумаю" in t or "o'ylab" in t:
        next_ru.append("«Подумаю»: hold 2ч + ВАШ перезвон во времени. Не «звоните сами».")
        next_uz.append("«O'ylab»: 2 soat hold + SIZNING qayta chaqiruv. «O'zingiz chaqiring» demang.")
    if "competitor" in objections_found:
        next_ru.append("Конкурент: не спорить — скорость слота vs состав услуги, 2 окна.")
        next_uz.append("Raqib: bahslashmang — slot tezligi vs tarkib, 2 oyna.")
    if ivr_heavy and len(t) < 500:
        next_ru.append("Много гудков/IVR: взять трубку раньше, сразу имя+вопрос по услуге.")
        next_uz.append("Ko'p IVR: tezroq oling, darhol ism+xizmat savoli.")

    next_ru.append("CRM-задача на сегодня: если не записан — 1 перезвон + SMS с номером клиники.")
    next_uz.append("Bugungi CRM vazifa: yozilmagan bo'lsa — 1 qayta chaqiruv + klinika raqami SMS.")

    # Ready-to-say lines (copy-paste), context-first
    replies_ru: list[str] = []
    replies_uz: list[str] = []
    if urgent:
        replies_ru.append(PHRASES["urgent_ru"])
        replies_uz.append(PHRASES["urgent_uz"])
    if loc_talk or driving or wa_mess:
        replies_ru.append(PHRASES["geo_ru"])
        replies_uz.append(PHRASES["geo_uz"])
        replies_ru.append(PHRASES["wa_spam_ru"])
        replies_uz.append(PHRASES["wa_spam_uz"])
    if booking != "booked":
        replies_ru.append(PHRASES["close_force_ru"])
        replies_uz.append(PHRASES["close_force_uz"])
        replies_ru.append(PHRASES["book_ru"])
        replies_uz.append(PHRASES["book_uz"])
    else:
        replies_ru.append(PHRASES["book_confirm_ru"])
        replies_uz.append(PHRASES["book_confirm_uz"])
        replies_ru.append(PHRASES["geo_ru"])
        replies_uz.append(PHRASES["geo_uz"])
    if any(s[0] == "МРТ" for s in services) or "мрт" in t or "mrt" in t:
        replies_ru.insert(0, PHRASES["prep_mrt_ru"])
        replies_uz.insert(0, PHRASES["prep_mrt_uz"])
    if any(s[0] == "УЗИ" for s in services) or "узи" in t or "uzi" in t:
        replies_ru.insert(0, PHRASES["prep_uzi_ru"])
        replies_uz.insert(0, PHRASES["prep_uzi_uz"])
    if "price" in objections_found or any(w in t for w in ("дорого", "qimmat", "сколько стоит")):
        replies_ru.append(PHRASES["price_hard_ru"])
        replies_uz.append(PHRASES["price_hard_uz"])
    if "think" in objections_found or "подумаю" in t:
        replies_ru.append(PHRASES["think_ru"])
        replies_uz.append(PHRASES["think_uz"])
    if re.search(r"instagram|инста", t):
        replies_ru.append(PHRASES["instagram_ru"])
        replies_uz.append(PHRASES["instagram_uz"])
    # fallback openers if still empty
    if not replies_ru:
        replies_ru = [
            PHRASES["greet_ru"].format(name="…"),
            PHRASES["need_ru"],
            PHRASES["close_force_ru"],
        ]
        replies_uz = [
            PHRASES["greet_uz"].format(name="…"),
            PHRASES["need_uz"],
            PHRASES["close_force_uz"],
        ]

    risks_ru, risks_uz = [], []
    if urgent:
        risks_ru.append("Острое — не «продавать слот», а безопасность.")
        risks_uz.append("O'tkir — slot sotish emas, xavfsizlik.")
    if booking != "booked" and no_slot_words:
        risks_ru.append("В разговоре нет даты/времени записи — главный предиктор потери (по вашим звонкам).")
        risks_uz.append("Suhbatda yozuv sanasi yo'q — yo'qotishning asosiy belgisi.")
    if loc_talk and booking == "booked":
        risks_ru.append("Запись есть, но клиент «теряется» на дороге — без гео/SMS не доедет.")
        risks_uz.append("Yozuv bor, yo'lda adashadi — geosiz kelmasligi mumkin.")
    if loc_talk and booking != "booked":
        risks_ru.append("Говорите про дорогу ДО записи — классическая утечка времени.")
        risks_uz.append("Yozuvdan OLDIN yo'l haqida gap — vaqt isrofi.")
    if wa_mess:
        risks_ru.append("WhatsApp spam-фильтр: исходящие с клиники часто не доходят.")
        risks_uz.append("WhatsApp spam: klinikadan chiquvchi yetmasligi mumkin.")
    if len(text or "") < 80:
        risks_ru.append("Мало текста — не угадывать услугу, задать 1 уточняющий вопрос.")
        risks_uz.append("Matn kam — xizmatni taxmin qilmang, 1 aniqlovchi savol.")
    if "no_next_step" in flags:
        risks_ru.append("Нет next step в CRM — follow-up сегодня.")
        risks_uz.append("CRM next step yo'q — bugun follow-up.")
    if "objection_missed" in flags:
        risks_ru.append("Возражение без ответа — дожать цену/страх/«подумаю».")
        risks_uz.append("E'tiroz javobsiz — narx/qo'rquv/«o'ylab» ni yoping.")
    if "medical_overpromise" in flags:
        risks_ru.append("Этика: не диагноз и не «100% вылечим» по телефону.")
        risks_uz.append("Etika: telefonda tashxis va «100% tuzatamiz» yo'q.")
    if booking == "rejected":
        risks_ru.append("Отказ: причина в CRM + перезвон через 1–2 дня с новым слотом.")
        risks_uz.append("Rad: sabab CRM + 1–2 kundan yangi slot bilan chaqiruv.")

    score = max(0.0, min(10.0, float(base["score"]) + score_boost))
    if urgent:
        score = min(score, 5.5)
    if booking != "booked" and no_slot_words and len(t) > 200:
        score = min(score, 5.0)  # long talk without close
    if loc_talk and booking != "booked":
        score = min(score, 4.5)

    # Stage from booking + content
    if urgent:
        stage_ru, stage_uz = "urgent / маршрутизация", "shoshilinch / yo'naltirish"
    elif booking == "booked":
        stage_ru, stage_uz = "запись есть → довести до визита", "yozuv bor → tashrifgacha yetkazish"
    elif booking == "promised_callback":
        stage_ru, stage_uz = "ждём перезвон (ваш, не «сам»)", "qayta chaqiruv (sizniki)"
    elif loc_talk and booking != "booked":
        stage_ru, stage_uz = "застряли на адресе — вернуть к слоту", "manzilda tiqilib — slotga qaytish"
    elif "missed_need" in flags:
        stage_ru, stage_uz = "не ясна услуга", "xizmat noaniq"
    else:
        stage_ru, stage_uz = "дожать запись сегодня", "bugun yozuvni yopish"

    svc_hint = pack_bilingual(
        ", ".join(s[0] for s in services) if services else "уточнить направление",
        ", ".join(s[1] for s in services) if services else "yo'nalishni aniqlash",
    )

    # Only questions that unlock booking
    q_ru = [
        "Приём, УЗИ, МРТ или анализы — что нужно?",
        "Есть направление / старые заключения?",
        "Сегодня после 15:00 или завтра до 12:00 — что берём?",
    ]
    q_uz = [
        "Qabul, UZI, MRT yoki tahlil — nima kerak?",
        "Yo'llanma / oldingi xulosa bormi?",
        "Bugun 15:00 dan keyin yoki ertaga 12:00 gacha — qaysi?",
    ]
    if any(s[0] == "МРТ" for s in services) or "мрт" in t:
        q_ru.append("Металл, стимулятор, беременность, сильный страх закрытого — есть?")
        q_uz.append("Metall, stimulyator, homiladorlik, yopiq joy qo'rquvi — bormi?")
    elif any(s[0] == "УЗИ" for s in services) or "узи" in t:
        q_ru.append("Какая зона УЗИ? Натощак получится (если брюшная)?")
        q_uz.append("UZI zonasi? Och qorin (qorin bo'lsa) qulaymi?")

    obj_list = [
        {
            "objection": pack_bilingual("Дорого", "Qimmat"),
            "answer": pack_bilingual(PHRASES["price_hard_ru"], PHRASES["price_hard_uz"]),
        },
        {
            "objection": pack_bilingual("Подумаю / сам перезвоню", "O'ylab / o'zim chaqiraman"),
            "answer": pack_bilingual(PHRASES["think_ru"], PHRASES["think_uz"]),
        },
        {
            "objection": pack_bilingual("Где вы / как доехать", "Qayerda / qanday boraman"),
            "answer": pack_bilingual(PHRASES["geo_ru"], PHRASES["geo_uz"]),
        },
        {
            "objection": pack_bilingual("Скиньте WhatsApp, я за рулём", "WhatsApp, rulda man"),
            "answer": pack_bilingual(PHRASES["wa_spam_ru"], PHRASES["wa_spam_uz"]),
        },
        {
            "objection": pack_bilingual("Диагноз по телефону", "Telefonda tashxis"),
            "answer": pack_bilingual(PHRASES["no_diag_ru"], PHRASES["no_diag_uz"]),
        },
    ]
    if "competitor" in objections_found:
        obj_list.append(
            {
                "objection": pack_bilingual(
                    "В другой клинике дешевле/быстрее",
                    "Boshqa klinikada arzonroq/tezroq",
                ),
                "answer": pack_bilingual(
                    "Не спорю. Ближайшие окна: … и …. Что важнее — скорость слота или состав? Подстроим.",
                    "Bahslashmayman. Eng yaqin oynalar: … va …. Muhimi — slot tezligi yoki tarkib? Moslashtiramiz.",
                ),
            }
        )

    quotes = []
    q = (base.get("transcript_quote") or "").strip()
    if q:
        quotes = [pack_bilingual(q, q)]

    # Concrete summary for managers (not fluff)
    bits_ru = []
    bits_uz = []
    if services:
        bits_ru.append("услуга: " + ", ".join(s[0] for s in services))
        bits_uz.append("xizmat: " + ", ".join(s[1] for s in services))
    if booking == "booked":
        bits_ru.append("запись вроде есть — проверить CRM и гео")
        bits_uz.append("yozuv bor — CRM va geo tekshir")
    elif no_slot_words:
        bits_ru.append("даты записи в разговоре нет — главный риск потери")
        bits_uz.append("yozuv sanasi yo'q — asosiy yo'qotish xavfi")
    if loc_talk:
        bits_ru.append("много про дорогу/локацию")
        bits_uz.append("yo'l/lokatsiya ko'p")
    if wa_mess:
        bits_ru.append("WhatsApp/Telegram упирается в доставку")
        bits_uz.append("WhatsApp/Telegram yetkazish muammosi")
    summary = base.get("summary") or pack_bilingual(
        f"«{name}»: " + ("; ".join(bits_ru) if bits_ru else (base.get("client_need") or "мало данных")),
        f"«{name}»: " + ("; ".join(bits_uz) if bits_uz else "ma'lumot kam"),
    )

    return {
        "score": round(score, 1),
        "summary": summary,
        "stage_hint": pack_bilingual(stage_ru, stage_uz),
        "risks": _bi_list(
            risks_ru or ["Контроль скорости ответа и записи."],
            risks_uz or ["Javob va yozuv tezligini nazorat qiling."],
        ),
        "next_steps": _bi_list(next_ru, next_uz),
        "suggested_replies": _bi_list(replies_ru[:6], replies_uz[:6]),
        "questions_to_ask": _bi_list(q_ru, q_uz),
        "objections": obj_list,
        "do_not": _bi_list(
            [
                "Не ставить диагноз по телефону",
                "Не обещать 100% лечение",
                "Не игнорировать red flags",
                "Не уходить без даты записи/перезвона",
            ],
            [
                "Telefonda tashxis qo'ymang",
                "100% davolash va'da qilmang",
                "Red flaglarni e'tiborsiz qoldirmang",
                "Yozuv/qayta qo'ng'iroqsiz qoldirmang",
            ],
        ),
        "quality": {
            "strengths": base.get("strengths") or "—",
            "weaknesses": base.get("weaknesses") or "—",
        },
        "service_hint": svc_hint,
        "client_need": base.get("client_need") or "—",
        "booking_result": booking,
        "flags": flags,
        "transcript_quotes": quotes,
        "model": "medical-heuristic-v4",
    }


def _ai_coach(text: str, meta: str) -> dict[str, Any] | None:
    if not XAI_API_KEY or not (text or "").strip():
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=XAI_API_KEY, base_url=XAI_BASE_URL)
        user_msg = f"{meta}\n\nИстория/транскрипты:\n{text[:10000]}"
        try:
            resp = client.responses.create(
                model=XAI_MODEL,
                input=[
                    {"role": "system", "content": COACH_SYSTEM},
                    {"role": "user", "content": user_msg},
                ],
            )
            content = getattr(resp, "output_text", None) or ""
        except Exception:
            chat = client.chat.completions.create(
                model=XAI_MODEL,
                messages=[
                    {"role": "system", "content": COACH_SYSTEM},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.3,
            )
            content = chat.choices[0].message.content or ""
        parsed = _parse_coach_json(content)
        if not parsed:
            return None
        return _normalize_coach(parsed, XAI_MODEL)
    except Exception as exc:
        logger.error("AI coach failed: %s", exc)
        return None


def fetch_lead_notes(client: AmoCRMClient, lead_id: int) -> list[dict[str, Any]]:
    try:
        data = client._request(
            "GET",
            f"/api/v4/leads/{lead_id}/notes",
            params={"limit": 100, "page": 1},
        )
        if data:
            return data.get("_embedded", {}).get("notes", []) or []
    except Exception as exc:
        logger.warning("Lead notes fetch failed: %s", exc)
    return []


def fetch_lead_talks(client: AmoCRMClient, lead_id: int) -> list[dict[str, Any]]:
    """Talks/chats linked to lead (WhatsApp/IG/Telegram). Message body often not in REST."""
    try:
        data = client._request(
            "GET",
            "/api/v4/talks",
            params={
                "filter[entity_id]": lead_id,
                "filter[entity_type]": "lead",
                "limit": 50,
            },
        )
        if data:
            return data.get("_embedded", {}).get("talks", []) or []
    except Exception as exc:
        logger.warning("Lead talks fetch failed: %s", exc)
    return []


def talks_to_items(talks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for t in talks or []:
        origin = (t.get("origin") or "chat").replace("_", " ")
        status = t.get("status") or ""
        chat_id = t.get("chat_id") or ""
        tid = t.get("talk_id") or t.get("id")
        text = (
            f"Беседа {origin}"
            + (f" · статус: {status}" if status else "")
            + (f" · chat_id: {chat_id}" if chat_id else "")
            + ". Текст сообщений Instagram/WhatsApp amo отдаёт не всегда — "
            "откройте карточку в amoCRM, если нужен полный чат."
        )
        items.append(
            {
                "id": f"talk:{tid}",
                "kind": "chat",
                "note_type": "talk",
                "direction": "",
                "created_at": t.get("updated_at") or t.get("created_at"),
                "text": text,
                "transcript": None,
                "duration": None,
                "phone": None,
                "recording_url": None,
                "origin": origin,
                "is_meta": True,
            }
        )
    return items


def notes_to_items(notes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = []
    for n in notes:
        params = n.get("params") or {}
        text = params.get("text") or ""
        if not text or (isinstance(text, str) and text.strip().startswith("http")):
            text = ""
        ntype = n.get("note_type") or "common"
        direction = (
            "in"
            if ntype.endswith("_in") or "incoming" in ntype
            else ("out" if ntype.endswith("_out") or "outgoing" in ntype else "")
        )
        kind = "call" if "call" in ntype else ("sms" if "sms" in ntype else "note")
        # service messages / attachments
        if not text and params.get("uniq"):
            text = f"[{ntype}] service event"
        items.append(
            {
                "id": n.get("id"),
                "kind": kind,
                "note_type": ntype,
                "direction": direction,
                "created_at": n.get("created_at"),
                "created_by": n.get("created_by"),
                "text": text,
                "transcript": None,
                "duration": params.get("duration"),
                "phone": params.get("phone"),
                "recording_url": params.get("link"),
            }
        )
    items.sort(key=lambda x: x.get("created_at") or 0, reverse=True)
    return items


def _is_stub_text(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    if t.startswith("["):
        return True
    if t.startswith("Беседа ") and "chat_id" in t:
        return True
    # bare UUID placeholders sometimes stored as "text"
    if re.fullmatch(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
        t,
    ):
        return True
    return False


def _is_call_recording_stub(text: str) -> bool:
    t = (text or "").strip().lower()
    return t.startswith("[call_recording]") or "call_recording" in t


def _has_real_dialog(items: list[dict[str, Any]]) -> bool:
    for i in items:
        tr = (i.get("transcript") or "").strip()
        tx = (i.get("text") or "").strip()
        if tr and not _is_stub_text(tr):
            return True
        if tx and not _is_stub_text(tx) and len(tx) > 12:
            return True
        # recording alone is not "dialog text" yet — still no analysis body
    return False


def local_comms_for_lead(lead_id: int, limit: int = 40) -> list[dict[str, Any]]:
    init_db()
    with db() as conn:
        try:
            rows = conn.execute(
                """
                SELECT id, kind, direction, manager_id, created_at, duration, phone,
                       text, transcript, recording_url, source
                FROM communications
                WHERE lead_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (lead_id, limit),
            ).fetchall()
        except Exception:
            rows = conn.execute(
                """
                SELECT id, kind, direction, manager_id, created_at, duration, phone, text, source
                FROM communications
                WHERE lead_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (lead_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]


def _comm_norm_key(it: dict[str, Any]) -> str:
    """Normalize remote note id / local note:leads:id into one merge key."""
    cid = str(it.get("id") or "").strip()
    if not cid:
        return (
            f"anon:{it.get('created_at')}:{it.get('kind')}:"
            f"{it.get('phone') or ''}:{it.get('duration') or ''}"
        )
    m = re.search(r"(?:^|:)(\d{4,})$", cid)
    if m:
        return m.group(1)
    # events without trailing digits: keep full id
    return cid


def _prefer_storage_id(a: str, b: str) -> str:
    """Prefer local SQLite-style ids (note:leads:…) for audio streaming."""
    for cand in (a, b):
        if cand and str(cand).startswith("note:"):
            return str(cand)
    return str(a or b or "")


def _merge_comm_item(base: dict[str, Any], other: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    tr_b = (out.get("transcript") or "").strip()
    tr_o = (other.get("transcript") or "").strip()
    if tr_o and (not tr_b or len(tr_o) > len(tr_b)):
        out["transcript"] = other["transcript"]
    if other.get("recording_url") and not out.get("recording_url"):
        out["recording_url"] = other["recording_url"]
    tx_b = (out.get("text") or "").strip()
    tx_o = (other.get("text") or "").strip()
    if tx_o and (not tx_b or len(tx_o) > len(tx_b)):
        out["text"] = other["text"]
    if other.get("kind") == "call" or out.get("kind") == "call":
        if other.get("kind") == "call" or not out.get("kind"):
            out["kind"] = "call"
    out["id"] = _prefer_storage_id(str(out.get("id") or ""), str(other.get("id") or ""))
    for f in ("duration", "direction", "phone", "created_at", "manager_id", "source"):
        if (out.get(f) in (None, "", "unknown")) and other.get(f) not in (None, ""):
            out[f] = other[f]
    return out


def merge_remote_and_local(
    remote_items: list[dict[str, Any]], local_items: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Merge CRM notes + local DB rows; one entry per call/note."""
    by_key: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    # Local first so preferred note: ids stick; remote enriches text/links
    for it in list(local_items or []) + list(remote_items or []):
        key = _comm_norm_key(it)
        if key not in by_key:
            by_key[key] = dict(it)
            order.append(key)
        else:
            by_key[key] = _merge_comm_item(by_key[key], it)
    items = [by_key[k] for k in order]
    items.sort(key=lambda x: x.get("created_at") or 0, reverse=True)
    return items


def _audio_path_for(it: dict[str, Any]) -> str | None:
    if not it.get("recording_url"):
        return None
    cid = str(it.get("id") or "").strip()
    if cid.startswith("note:"):
        return f"/api/v1/audio/{cid}"
    m = re.search(r"(?:^|:)(\d{4,})$", cid)
    if m:
        # collector stores notes as note:leads:{id}
        return f"/api/v1/audio/note:leads:{m.group(1)}"
    if cid:
        return f"/api/v1/audio/{cid}"
    return None


def _status_name_map(client: AmoCRMClient) -> dict[int, str]:
    out: dict[int, str] = {}
    try:
        for p in client.get_pipelines():
            for s in (p.get("_embedded") or {}).get("statuses") or []:
                if s.get("id") is not None:
                    out[int(s["id"])] = str(s.get("name") or s["id"])
    except Exception:
        pass
    return out


def _plain_for_amo(v: Any) -> str:
    """Flatten bilingual packs for amoCRM note (readable, no emoji flags if possible)."""
    if v is None:
        return ""
    if isinstance(v, dict):
        ru = str(v.get("ru") or "").strip()
        uz = str(v.get("uz") or "").strip()
        if ru and uz and ru != uz:
            return f"{ru}\n({uz})"
        return ru or uz
    s = str(v).strip()
    if not s or s == "—":
        return ""
    # unpack 🇷🇺 / 🇺🇿 packs
    ru_m = re.search(r"🇷🇺\s*([^\n🇺🇿]+)", s)
    uz_m = re.search(r"🇺🇿\s*([^\n🇷🇺]+)", s)
    if ru_m or uz_m:
        ru = (ru_m.group(1).strip() if ru_m else "")
        uz = (uz_m.group(1).strip() if uz_m else "")
        if ru and uz and ru != uz:
            return f"{ru}\n({uz})"
        return ru or uz
    return s


def _format_note(coach: dict[str, Any], quality: dict[str, Any]) -> str:
    """Compact practical note for amoCRM deal card."""
    score = coach.get("score", quality.get("score"))
    score_s = "—" if score is None else f"{score}/10"
    flags = list(coach.get("flags") or quality.get("flags") or [])
    no_dialog = "no_dialog" in flags or coach.get("model") == "no-dialog"

    lines = [
        "AI-разбор (CRM AI Desk)",
        f"Оценка: {score_s}"
        + (" · нет текста разговора" if no_dialog else ""),
    ]
    stage = _plain_for_amo(coach.get("stage_hint"))
    svc = _plain_for_amo(coach.get("service_hint"))
    if svc:
        lines.append(f"Услуга: {svc}")
    if stage:
        lines.append(f"Этап: {stage}")

    summary = _plain_for_amo(coach.get("summary") or quality.get("summary"))
    if summary:
        lines += ["", "Суть:", summary]

    steps = coach.get("next_steps") or []
    if steps:
        lines += ["", "Сделать сейчас:"]
        for s in steps[:5]:
            p = _plain_for_amo(s)
            if p:
                lines.append(f"• {p}")

    replies = coach.get("suggested_replies") or []
    if replies:
        lines += ["", "Что сказать клиенту:"]
        for r in replies[:3]:
            p = _plain_for_amo(r)
            if p:
                # first line only for compact CRM note
                first = p.split("\n")[0].strip()
                lines.append(f"«{first}»")

    risks = coach.get("risks") or []
    if risks:
        lines += ["", "Риски:"]
        for r in risks[:3]:
            p = _plain_for_amo(r)
            if p:
                lines.append(f"• {p.split(chr(10))[0]}")

    lines += ["", "— CRM AI Desk · не диагноз, только маршрутизация/запись"]
    return "\n".join(lines)


def build_assistant_payload(
    *,
    lead_id: int,
    client: AmoCRMClient | None = None,
    notes_payload: list[dict[str, Any]] | None = None,
    write_note: bool = False,
    live_stt: bool = False,
) -> dict[str, Any]:
    init_db()
    client = client or AmoCRMClient()
    lead = client.get_lead(lead_id) or {}
    if lead:
        upsert_lead(lead, won_ids=WON_STATUS_IDS, lost_ids=LOST_STATUS_IDS)

    if notes_payload is not None:
        items = notes_payload
    else:
        remote_notes = fetch_lead_notes(client, lead_id)
        items = notes_to_items(remote_notes)

    local = local_comms_for_lead(lead_id, limit=80)
    items = merge_remote_and_local(items, local)
    # Instagram / WA talks (meta if message body unavailable via REST)
    try:
        talks = fetch_lead_talks(client, lead_id)
        talk_items = talks_to_items(talks)
        if talk_items:
            items = merge_remote_and_local(items, talk_items)
    except Exception as exc:
        logger.warning("talks enrich skip: %s", exc)

    # Live STT only when explicitly requested (widget). Bulk STT = main worker.
    if live_stt:
        try:
            from transcriber import process_call

            for it in items[:3]:
                if it.get("kind") != "call":
                    continue
                if (it.get("transcript") or "").strip():
                    continue
                url = (it.get("recording_url") or "").strip()
                if not url.startswith("https://"):
                    continue
                dur = int(it.get("duration") or 0)
                if dur and dur < 12:
                    continue
                cid = f"live:{lead_id}:{it.get('id')}"
                res = process_call({"id": cid, "recording_url": url, "duration": dur})
                if res.get("ok"):
                    from storage import db as _db

                    with _db() as conn:
                        row = conn.execute(
                            "SELECT transcript FROM communications WHERE id=?", (cid,)
                        ).fetchone()
                        if row and row["transcript"]:
                            it["transcript"] = row["transcript"]
                break
        except Exception as exc:
            logger.warning("Live STT skip: %s", exc)

    chrono = sorted(items, key=lambda x: x.get("created_at") or 0)
    history = _join_texts(chrono, limit=20)
    has_dialog = bool(history.strip()) and _has_real_dialog(items)

    names = manager_name_map()
    status_names = _status_name_map(client)
    resp_id = lead.get("responsible_user_id")
    status_id = lead.get("status_id")
    status_label = status_names.get(status_id, str(status_id))
    meta = (
        f"lead_id={lead_id}; name={lead.get('name')}; "
        f"status={status_label}; pipeline={lead.get('pipeline_id')}; "
        f"responsible={names.get(resp_id or 0, resp_id)}; "
        f"history_chars={len(history)}; has_dialog={has_dialog}"
    )

    if has_dialog:
        coach = _ai_coach(history, meta) if history.strip() else None
        if not coach:
            coach = _heuristic_coach(history, lead)
        latest_text = history[:4000]
        quality = _ai_analyze(latest_text, "call", meta) or _heuristic_analyze(
            latest_text, "call"
        )
    else:
        # Honest empty-dialog report (not a fake 2.5/10 "analysis")
        n_calls = sum(1 for i in items if i.get("kind") == "call")
        n_chats = sum(
            1 for i in items if i.get("kind") in ("chat", "sms") or i.get("note_type") == "talk"
        )
        n_notes = sum(1 for i in items if i.get("kind") == "note")
        coach = {
            "score": None,
            "summary": pack_bilingual(
                "Нет текста разговора для анализа: нет записи звонка и нет расшифровки. "
                f"В CRM: звонков-событий {n_calls}, чатов/бесед {n_chats}, заметок {n_notes}. "
                "Оценка не ставится — это не «плохой звонок», а отсутствие данных. "
                "Нажмите «Забрать из CRM» для сделок с телефонией или откройте чат в amoCRM.",
                "Tahlil uchun suhbat matni yo'q: qo'ng'iroq yozuvi va transkript yo'q. "
                f"CRM: chaqiruv {n_calls}, chat {n_chats}, izoh {n_notes}. "
                "Baholanmaydi — yomon suhbat emas, ma'lumot yo'q.",
            ),
            "stage_hint": pack_bilingual(
                status_label or "без текста",
                status_label or "matnsiz",
            ),
            "service_hint": pack_bilingual(
                "уточнить после контакта",
                "aloqadan keyin aniqlash",
            ),
            "strengths": pack_bilingual(
                "Данных разговора нет — сильные стороны оценить нельзя.",
                "Suhbat ma'lumoti yo'q — kuchli tomonlarni baholab bo'lmaydi.",
            ),
            "weaknesses": pack_bilingual(
                "Нет транскрипта/записи. Анализ по Instagram/WhatsApp без текста API неполный.",
                "Transkript/yozuv yo'q. Instagram/WhatsApp matnsiz API tahlili to'liq emas.",
            ),
            "next_steps": [
                pack_bilingual(
                    "Откройте сделку в amoCRM и прочитайте чат глазами, если клиент писал в Instagram/WA.",
                    "Agar mijoz Instagram/WA da yozgan bo'lsa, amoCRM da chatni oching.",
                ),
                pack_bilingual(
                    "Позвоните клиенту и после звонка нажмите «Забрать из CRM» — появится запись и текст.",
                    "Mijozga qo'ng'iroq qiling, keyin «CRM dan olish» — yozuv va matn paydo bo'ladi.",
                ),
                pack_bilingual(
                    "Для разбора с текстом: в фильтре слева выберите «Есть транскрипт».",
                    "Matnli tahlil uchun chap filtrda «Transkript bor» ni tanlang.",
                ),
            ],
            "questions_to_ask": [
                pack_bilingual(
                    "Что беспокоит и какая услуга нужна (МРТ / УЗИ / приём)?",
                    "Nima bezovta va qaysi xizmat kerak (MRT / UZI / qabul)?",
                ),
                pack_bilingual(
                    "Когда удобно подойти и есть ли направление?",
                    "Qachon kelish qulay va yo'llanma bormi?",
                ),
            ],
            "suggested_replies": [
                pack_bilingual(
                    "Здравствуйте! Клиника Kimyo University Hospital. Чем могу помочь? "
                    "(шаблон — разговора в системе ещё нет)",
                    "Assalomu alaykum! Kimyo University Hospital klinikasi. Qanday yordam bera olaman? "
                    "(shablon — tizimda suhbat yo'q)",
                ),
            ],
            "objections": [],
            "risks": [
                pack_bilingual(
                    "Сделка без зафиксированного диалога — легко «потерять» клиента.",
                    "Suhbatsiz bitim — mijozni yo'qotish oson.",
                )
            ],
            "do_not": [
                pack_bilingual(
                    "Не ставьте диагноз и не обещайте точную цену без данных.",
                    "Ma'lumotsiz tashxis va aniq narx va'da qilmang.",
                )
            ],
            "model": "no-dialog",
            "flags": ["no_dialog", "no_text_body"],
            "is_template": True,
        }
        quality = {
            "score": None,
            "summary": coach["summary"],
            "strengths": coach["strengths"],
            "weaknesses": coach["weaknesses"],
            "advice": coach["next_steps"][0] if coach["next_steps"] else "—",
            "sentiment": "unknown",
            "flags": ["no_dialog", "no_text_body"],
            "model": "no-dialog",
        }

    if status_label and has_dialog:
        coach["stage_hint"] = pack_bilingual(
            f"{status_label}",
            f"{status_label}",
        ) + (" · " + coach["stage_hint"] if coach.get("stage_hint") else "")

    note_text = _format_note(coach, quality)
    note_written = False
    note_error: str | None = None
    if write_note and lead_id:
        try:
            client.add_note_to_lead(int(lead_id), note_text)
            note_written = True
            logger.info("Wrote AI note to amo lead %s (%s chars)", lead_id, len(note_text))
        except Exception as exc:
            note_error = str(exc)[:240]
            logger.warning("Could not write note to lead %s: %s", lead_id, exc)

    has_transcript = any(
        (i.get("transcript") or "").strip()
        and not _is_stub_text(i.get("transcript") or "")
        for i in items
    )

    # Full conversation items for UI: audio + transcript + chat meta
    conversation: list[dict[str, Any]] = []
    for i in items:
        raw_text = (i.get("text") or "").strip()
        tr = (i.get("transcript") or "").strip()
        if tr and _is_stub_text(tr):
            tr = ""
        rec_url = (i.get("recording_url") or "").strip()
        rec = rec_url.startswith("http")
        kind = i.get("kind") or "note"
        pending_stt = bool(
            kind == "call"
            and rec
            and not tr
            and (not raw_text or _is_stub_text(raw_text) or _is_call_recording_stub(raw_text))
        )
        is_meta = bool(i.get("is_meta")) or (
            kind in ("chat", "note")
            and _is_stub_text(raw_text)
            and not rec
            and not tr
        )
        # keep meta talks so UI can explain Instagram chats
        if not rec and not tr and not raw_text and not is_meta:
            continue
        if (
            kind == "note"
            and not rec
            and not tr
            and len(raw_text) < 8
            and not is_meta
        ):
            continue
        # skip pure event duplicates without duration/url when we have better call notes
        if (
            str(i.get("id") or "").startswith("event:")
            and kind == "call"
            and not rec
            and not tr
        ):
            # keep only if no other call items — added later via filter
            pass

        display_text = tr or raw_text
        if pending_stt:
            display_text = (
                "Запись звонка есть в телефонии, текст ещё не расшифрован. "
                "Нажмите «Расшифровать» — займёт 1–3 минуты."
            )
        elif _is_call_recording_stub(raw_text) and not tr:
            display_text = (
                "Звонок зафиксирован, но ссылка на запись или текст отсутствуют. "
                "Нажмите «Забрать из CRM» или откройте сделку в amo."
            )
        elif is_meta:
            display_text = raw_text
        elif _is_stub_text(raw_text) and not tr:
            if "chat" in (kind or ""):
                display_text = (
                    "Сообщение в чате (тело текста amo API не отдал). "
                    "Откройте чат в amoCRM."
                )
            elif kind == "call":
                display_text = (
                    "Факт звонка в CRM, но без файла записи и без текста. "
                    "Часто так бывает у коротких/сбойных вызовов."
                )
            else:
                display_text = "Событие CRM без текста содержимого."

        cid = str(i.get("id") or "")
        conversation.append(
            {
                "id": cid,
                "kind": kind,
                "direction": i.get("direction") or "",
                "created_at": i.get("created_at"),
                "duration": i.get("duration"),
                "phone": i.get("phone"),
                "text": display_text,
                "transcript": tr,
                "has_recording": rec,
                "audio_url": _audio_path_for(i) if rec else None,
                "is_meta": is_meta,
                "is_stub": _is_stub_text(raw_text) and not tr and not pending_stt,
                "pending_stt": pending_stt,
                "origin": i.get("origin") or "",
            }
        )
        if len(conversation) >= 40:
            break
    # Prefer real transcripts, then pending STT with audio, then rest
    conversation.sort(
        key=lambda x: (
            0 if (x.get("transcript") or "").strip() else 1,
            0 if x.get("pending_stt") else 1,
            0 if x.get("has_recording") else 1,
            0 if x.get("kind") == "call" else 1,
            0 if not x.get("is_meta") else 2,
            -(x.get("created_at") or 0),
        )
    )

    return {
        "ok": True,
        "has_dialog": has_dialog,
        "lead": {
            "id": lead_id,
            "name": lead.get("name"),
            "price": lead.get("price"),
            "status_id": lead.get("status_id"),
            "status_name": status_label,
            "pipeline_id": lead.get("pipeline_id"),
            "responsible_user_id": lead.get("responsible_user_id"),
            "responsible_name": names.get(resp_id or 0),
            "is_won": lead.get("status_id") in WON_STATUS_IDS,
            "is_lost": lead.get("status_id") in LOST_STATUS_IDS,
        },
        "stats": {
            "notes": sum(1 for i in items if i.get("kind") == "note"),
            "calls": sum(1 for i in items if i.get("kind") == "call"),
            "messages": sum(
                1
                for i in items
                if i.get("kind") in ("chat", "sms") or i.get("note_type") == "talk"
            ),
            "has_transcript": has_transcript,
            "transcripts": sum(
                1
                for i in items
                if (i.get("transcript") or "").strip()
                and not _is_stub_text(i.get("transcript") or "")
            ),
            "recordings": sum(1 for i in items if i.get("recording_url")),
            "has_dialog": has_dialog,
        },
        "history_preview": [
            {
                "kind": i.get("kind"),
                "direction": i.get("direction"),
                "created_at": i.get("created_at"),
                "text": ((i.get("transcript") or i.get("text") or "")[:220]),
                "has_recording": bool(i.get("recording_url")),
                "id": i.get("id"),
                "is_stub": _is_stub_text(i.get("transcript") or i.get("text") or ""),
            }
            for i in items[:15]
        ],
        "conversation": conversation,
        "coach": coach,
        "quality": quality,
        "note_markdown": note_text,
        "note_written": note_written,
        "note_error": note_error,
        "managers": [{"id": m["id"], "name": m["name"]} for m in list_managers()],
    }


def analyze_free_text(text: str, kind: str = "chat") -> dict[str, Any]:
    result = _ai_analyze(text, kind, "widget-live") or _heuristic_analyze(text, kind)
    coach = _ai_coach(text, f"live {kind}") or _heuristic_coach(text, None)
    return {"ok": True, "quality": result, "coach": coach}
