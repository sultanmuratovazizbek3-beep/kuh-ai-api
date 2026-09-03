"""Analyze communications from REAL transcripts (RU/UZ). AI + strong heuristics."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from bilingual import UZ, pack_bilingual
from config import ANALYZE_BATCH_SIZE, XAI_API_KEY, XAI_BASE_URL, XAI_MODEL
from storage import save_analysis, unanalyzed_communications

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Сен тиббий клиника (Kimyo Hospital / KUH) учун катта РОП / sales coachсан.
Менежер ва мижоз ўртасидаги ЧИН суҳбатни (телефон транскрипт ёки матн) таҳлил қил.

Тил: жавобни МАЖБУРИЙ икки тилда бер — русский + o'zbek (lotin).
Қуйидаги JSON форматни қатъий сақла (markdown йўқ):

{
  "score": 0-10,
  "summary_ru": "2-3 предложения: что произошло в звонке",
  "summary_uz": "2-3 jumla: qo'ng'iroqda nima bo'ldi",
  "strengths_ru": "сильные стороны через ;",
  "strengths_uz": "kuchli tomonlar ; orqali",
  "weaknesses_ru": "слабые стороны через ;",
  "weaknesses_uz": "zaif tomonlar ; orqali",
  "advice_ru": "конкретные советы менеджеру, 2-4 пункта",
  "advice_uz": "menejerga aniq maslahatlar, 2-4 band",
  "sentiment": "positive|neutral|negative|mixed",
  "flags": ["no_greeting","missed_need","no_next_step","price_only","rude","good_booking","empathy","upsell_missed","medical_overpromise","long_silence","script_ok"],
  "client_need_ru": "что нужно клиенту",
  "client_need_uz": "mijozga nima kerak",
  "booking_result": "booked|promised_callback|no_commitment|rejected|unclear",
  "suggested_reply_ru": "готовый следующий ответ/реплика менеджера",
  "suggested_reply_uz": "menejerning keyingi javobi"
}

Критерии оценки (строго):
1) Приветствие + название клиники + имя
2) Выявление жалобы/цели (открытые вопросы), НЕ диагноз
3) Маршрутизация: врач / УЗИ / МРТ / КТ / анализы
4) Цена с ценностью; подготовка к исследованию
5) Работа с возражениями («дорого», «подумаю»)
6) Чёткий next step: запись / дата-время / задача CRM
7) Тон: тёплый, уважительный (RU/UZ)
8) Не обещать «100% вылечим»; red flags (грудь, одышка, кровотечение) → приём/103

Если это ТРАНСКРИПТ звонка — опирайся на реальные реплики, цитируй коротко.
Клиника: Kimyo University Hospital (KUH), Ташкент.
"""


def _parse_json_response(content: str) -> dict[str, Any] | None:
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


def _normalize_result(parsed: dict[str, Any], model: str) -> dict[str, Any]:
    score = float(parsed.get("score", 5))
    score = max(0.0, min(10.0, score))
    summary = pack_bilingual(
        str(parsed.get("summary_ru") or parsed.get("summary") or ""),
        str(parsed.get("summary_uz") or ""),
    )
    strengths = pack_bilingual(
        str(parsed.get("strengths_ru") or parsed.get("strengths") or ""),
        str(parsed.get("strengths_uz") or ""),
    )
    weaknesses = pack_bilingual(
        str(parsed.get("weaknesses_ru") or parsed.get("weaknesses") or ""),
        str(parsed.get("weaknesses_uz") or ""),
    )
    advice = pack_bilingual(
        str(parsed.get("advice_ru") or parsed.get("advice") or ""),
        str(parsed.get("advice_uz") or ""),
    )
    flags = parsed.get("flags") or []
    if isinstance(flags, str):
        flags = [flags]
    return {
        "score": round(score, 1),
        "summary": summary,
        "strengths": strengths or "—",
        "weaknesses": weaknesses or "—",
        "advice": advice or "—",
        "sentiment": str(parsed.get("sentiment") or "neutral"),
        "flags": flags,
        "client_need": pack_bilingual(
            str(parsed.get("client_need_ru") or ""),
            str(parsed.get("client_need_uz") or ""),
        ),
        "booking_result": parsed.get("booking_result") or "unclear",
        "suggested_reply": pack_bilingual(
            str(parsed.get("suggested_reply_ru") or ""),
            str(parsed.get("suggested_reply_uz") or ""),
        ),
        "model": model,
    }


def _snip(text: str, max_len: int = 140) -> str:
    s = re.sub(r"\s+", " ", (text or "").strip())
    if len(s) <= max_len:
        return s
    return s[: max_len - 1].rsplit(" ", 1)[0] + "…"


def _extract_client_need(t: str, services: list[tuple[str, str]]) -> tuple[str, str]:
    """Infer what the patient wants from keywords + services."""
    bits_ru: list[str] = []
    bits_uz: list[str] = []
    if services:
        bits_ru.append(", ".join(s[0] for s in services[:3]))
        bits_uz.append(", ".join(s[1] for s in services[:3]))
    complaint_map = (
        (("боль", "болит", "og'riq", "ogriq", "og'riy"), "боль/дискомфорт", "og'riq/noqulaylik"),
        (("голов", "bosh og", "bosh ogriq", "bosh og'riq"), "голова", "bosh"),
        (("живот", "qorin"), "живот", "qorin"),
        (("беремен", "homila"), "беременность", "homiladorlik"),
        (("щитовид", "qalqonsimon", "тирео"), "щитовидка", "qalqonsimon"),
        (("сахар", "диабет", "qand"), "сахар/диабет", "qand/diabet"),
        (("давлен", "гипертон", "bosim"), "давление", "bosim"),
        (("ребён", "ребенок", "дет", "bola", "bolam"), "ребёнок", "bola"),
        (("анализ", "tahlil", "кровь", "qon"), "анализы", "tahlillar"),
        (("запис", "yozil", "qabul"), "запись на приём", "qabulga yozuv"),
    )
    for keys, ru, uz in complaint_map:
        if any(k in t for k in keys):
            if ru not in bits_ru:
                bits_ru.append(ru)
            if uz not in bits_uz:
                bits_uz.append(uz)
    if not bits_ru:
        return "потребность не прояснена", "ehtiyoj aniqlanmagan"
    return ", ".join(bits_ru[:4]), ", ".join(bits_uz[:4])


def _detect_booking(t: str) -> tuple[str, bool]:
    booked = any(
        w in t
        for w in (
            "записал", "записала", "запишем", "запишу", "записали вас",
            "вы записаны", "вас записали", "записать вас",
            "жду вас", "ждём вас", "ждем вас", "подтверждаю запись",
            "на завтра в", "на сегодня в", "в 10:", "в 11:", "в 12:",
            "yozib qo'ydim", "yozib qoldim", "yozib qo'yaman", "siz yozildingiz",
            "kutaman", "soat ",
        )
    )
    promised = any(
        w in t
        for w in (
            "перезвон", "свяжемся", "перезвоню", "завтра", "через час",
            "qayta qo'ng", "qayta qong", "bog'lanaman", "ertaga",
        )
    )
    rejected = any(
        w in t
        for w in (
            "не надо", "не нужно", "отказ", "не буду", "не интересно",
            "kerak emas", "yo'q rahmat", "kerakmas",
        )
    )
    if booked:
        return "booked", True
    if rejected and not booked:
        return "rejected", False
    if promised:
        return "promised_callback", True
    if any(w in t for w in ("запис", "yozib", "yozil", "slot", "время", "soat", "прием", "приём", "qabul")):
        return "promised_callback", True
    return "no_commitment", False


def _build_smart_summary(
    kind: str,
    text: str,
    t: str,
    need_ru: str,
    need_uz: str,
    booking: str,
    score: float,
    flags: list[str],
    services: list[tuple[str, str]],
) -> tuple[str, str]:
    """Human-readable summary instead of 'N chars'."""
    n = len(text or "")
    kind_ru = {"call": "звонок", "chat": "чат", "note": "заметка", "sms": "SMS"}.get(kind, kind)
    kind_uz = {"call": "qo'ng'iroq", "chat": "chat", "note": "izoh", "sms": "SMS"}.get(kind, kind)

    booking_ru = {
        "booked": "запись состоялась",
        "promised_callback": "обещан перезвон/слот",
        "no_commitment": "без договорённости",
        "rejected": "клиент отказался",
        "unclear": "итог неясен",
    }.get(booking, booking)
    booking_uz = {
        "booked": "yozuv bo'ldi",
        "promised_callback": "qayta qo'ng'iroq/slot va'da",
        "no_commitment": "kelishuv yo'q",
        "rejected": "mijoz rad etdi",
        "unclear": "natija noaniq",
    }.get(booking, booking)

    parts_ru = [f"{kind_ru.capitalize()}: клиенту нужно — {need_ru}."]
    parts_uz = [f"{kind_uz.capitalize()}: mijozga kerak — {need_uz}."]
    if services:
        parts_ru.append(f"Услуги в разговоре: {', '.join(s[0] for s in services[:3])}.")
        parts_uz.append(f"Suhbatdagi xizmatlar: {', '.join(s[1] for s in services[:3])}.")
    parts_ru.append(f"Итог: {booking_ru}.")
    parts_uz.append(f"Natija: {booking_uz}.")

    if "red_flag_urgent" in flags or "urgent" in flags:
        parts_ru.append("⚠ Возможны red-flag симптомы — приоритет безопасности.")
        parts_uz.append("⚠ Red-flag belgilar bo'lishi mumkin — xavfsizlik birinchi.")
    if "rude" in flags:
        parts_ru.append("Тон/конфликт — нужен разбор с менеджером.")
        parts_uz.append("Ohang/konflikt — menejer bilan tahlil kerak.")
    if "no_next_step" in flags:
        parts_ru.append("Нет чёткого next step — риск потери пациента.")
        parts_uz.append("Aniq next step yo'q — bemorni yo'qotish xavfi.")
    if n < 80:
        parts_ru.append("Мало текста для глубокого NLP.")
        parts_uz.append("Chuqur tahlil uchun matn kam.")
    elif n > 400:
        parts_ru.append(f"Развёрнутый диалог (~{n} симв.).")
        parts_uz.append(f"Batafsil suhbat (~{n} belgi).")

    if score >= 7.5:
        parts_ru.append("Качество диалога высокое.")
        parts_uz.append("Suhbat sifati yuqori.")
    elif score <= 4.0:
        parts_ru.append("Качество слабое — коучинг.")
        parts_uz.append("Sifat past — coaching kerak.")

    return " ".join(parts_ru), " ".join(parts_uz)


def _suggested_reply_for(
    t: str,
    need_ru: str,
    booking: str,
    services: list[tuple[str, str]],
    flags: list[str],
) -> tuple[str, str]:
    from medical_coach import PHRASES

    if "red_flag_urgent" in flags or "urgent" in flags:
        return PHRASES["urgent_ru"], PHRASES["urgent_uz"]
    if booking == "booked":
        return (
            "Отлично, вы записаны. Если планы изменятся — перезвоните, перенесём. До встречи!",
            "Ajoyib, yozildingiz. Reja o'zgarsa — qo'ng'iroq qiling, ko'chiramiz. Ko'rishguncha!",
        )
    if any(w in t for w in ("дорого", "qimmat", "дешев")):
        return PHRASES["price_ru"], PHRASES["price_uz"]
    if any(w in t for w in ("подумаю", "o'ylab", "o'ylab ko'raman")):
        return PHRASES["think_ru"], PHRASES["think_uz"]
    if services and any(s[0] == "МРТ" for s in services):
        return PHRASES["prep_mrt_ru"], PHRASES["prep_mrt_uz"]
    if services and any(s[0] == "УЗИ" for s in services):
        return PHRASES["prep_uzi_ru"], PHRASES["prep_uzi_uz"]
    if "missed_need" in flags or "не прояснена" in need_ru:
        return PHRASES["need_ru"], PHRASES["need_uz"]
    return PHRASES["book_ru"], PHRASES["book_uz"]


def _heuristic_analyze(text: str, kind: str) -> dict[str, Any]:
    """Smart bilingual rules when AI unavailable — works on real transcripts."""
    from medical_coach import detect_services, is_urgent

    raw = text or ""
    t = raw.lower()
    score = 5.0
    strengths_ru: list[str] = []
    strengths_uz: list[str] = []
    weak_ru: list[str] = []
    weak_uz: list[str] = []
    flags: list[str] = []

    services = detect_services(raw)
    urgent = is_urgent(raw)

    # --- Greeting / clinic brand ---
    greetings = (
        "здравствуй", "добрый", "добро пожаловать", "привет",
        "assalom", "ассалом", "salom", "kimyo", "клиник", "hospital",
        "меня зовут", "mening ismim",
    )
    has_greeting = any(g in t for g in greetings)
    if has_greeting:
        score += 0.9
        strengths_ru.append("приветствие / представление клиники")
        strengths_uz.append("salomlashish / klinikani tanishtirish")
    else:
        score -= 0.7
        weak_ru.append("нет явного приветствия + клиника + имя")
        weak_uz.append(UZ["no_greeting"])
        flags.append("no_greeting")

    # --- Need discovery ---
    need_words = (
        "нужн", "хочу", "боль", "болит", "запис", "услуг", "прием", "приём", "мрт", "узи",
        "анализ", "жалоб", "беспоко", "симптом", "narx", "og'riq", "ogriq", "yozil", "qabul",
        "tahlil", "shikoyat", "kerak", "хотел", "подскаж", "можно ли", "сколько",
        "направл", "yo'llanma", "tekshiruv", "bosh", "bezovta",
    )
    open_q = any(
        w in t
        for w in (
            "что беспоко", "что случил", "как давно", "какой результат",
            "nima bezovta", "qachondan", "qanday yordam", "чем могу",
            "подскажите", "расскажите",
        )
    )
    need_hit = any(w in t for w in need_words) or bool(services)
    if need_hit:
        score += 0.8
        strengths_ru.append("обсуждается потребность/услуга")
        strengths_uz.append("ehtiyoj / xizmat muhokama qilingan")
        if open_q:
            score += 0.35
            strengths_ru.append("есть открытые вопросы")
            strengths_uz.append("ochiq savollar bor")
            flags.append("open_questions")
    else:
        score -= 0.7
        weak_ru.append("потребность не прояснена")
        weak_uz.append(UZ["no_need"])
        flags.append("missed_need")

    if services:
        score += 0.4
        svc = ", ".join(s[0] for s in services[:3])
        strengths_ru.append(f"маршрутизация: {svc}")
        strengths_uz.append(f"yo'nalish: {', '.join(s[1] for s in services[:3])}")
        flags.append("service_routed")

    # --- Booking / next step ---
    booking, has_next = _detect_booking(t)
    if has_next:
        score += 1.2 if booking == "booked" else 0.9
        strengths_ru.append(
            "запись подтверждена" if booking == "booked" else "есть следующий шаг"
        )
        strengths_uz.append(
            "yozuv tasdiqlangan" if booking == "booked" else UZ["booking"]
        )
        flags.append("good_booking")
    else:
        score -= 1.1
        weak_ru.append("нет чёткого следующего шага (запись/перезвон)")
        weak_uz.append(UZ["no_next"])
        flags.append("no_next_step")
    if booking == "rejected":
        flags.append("client_rejected")
        weak_ru.append("клиент отказался — нужна recovery-стратегия")
        weak_uz.append("mijoz rad etdi — recovery strategiya kerak")

    # --- Empathy / tone ---
    if any(w in t for w in ("извините", "понимаю", "сочувствую", "tushunaman", "afsus", "албатта", "albatta")):
        score += 0.45
        strengths_ru.append("эмпатия / поддержка")
        strengths_uz.append("empatiya / qo'llab-quvvatlash")
        flags.append("empathy")

    # --- Ethics ---
    if any(w in t for w in ("гарантир", "100%", "точно вылеч", "albatta tuzal", "у вас точно")):
        score -= 1.3
        weak_ru.append("медобещание / намёк на диагноз без врача")
        weak_uz.append("shifokorsiz va'da / tashxis ishorasi")
        flags.append("medical_overpromise")

    if any(w in t for w in ("дурак", "не звоните", "отстань", "ahmoq", "заткн", "идиот")):
        score -= 2.5
        flags.append("rude")
        weak_ru.append("грубость / конфликт")
        weak_uz.append("qo'pollik / konflikt")

    # --- Price value ---
    price_talk = any(w in t for w in ("сколько стоит", "narxi", "цена", "сумма", "стоит", "qancha"))
    value_talk = any(w in t for w in ("входит", "подготов", "результат", "nima kiradi", "foyda", "план"))
    if price_talk and not value_talk:
        score -= 0.55
        flags.append("price_only")
        weak_ru.append("цена без ценности услуги")
        weak_uz.append("narx bor, qiymat tushuntirilmagan")
    elif price_talk and value_talk:
        score += 0.35
        strengths_ru.append("цена + что входит")
        strengths_uz.append("narx + nima kiradi")
        flags.append("value_price")

    # --- Objection handling ---
    objection_hit = any(w in t for w in ("дорого", "qimmat", "подумаю", "o'ylab", "в другой", "дешевле", "boshqa klinika"))
    handle_obj = any(
        w in t
        for w in (
            "понимаю", "сравн", "что входит", "брон", "перезвон", "tushunaman",
            "solishtir", "nima kiradi",
        )
    )
    if objection_hit:
        if handle_obj:
            score += 0.5
            strengths_ru.append("отработано возражение")
            strengths_uz.append("e'tiroz ishlangan")
            flags.append("objection_handled")
        else:
            score -= 0.45
            weak_ru.append("возражение без отработки")
            weak_uz.append("e'tiroz ishlanmagan")
            flags.append("objection_missed")

    # --- Length / structure ---
    nlen = len(raw)
    if kind == "call" and nlen < 60:
        score -= 0.9
        flags.append("too_short")
        weak_ru.append("слишком короткая фиксация / мало речи")
        weak_uz.append(UZ["short_call"])
    elif nlen > 250:
        score += 0.35
        strengths_ru.append("развёрнутый диалог/транскрипт")
        strengths_uz.append("batafsil suhbat/transkript")

    # Dialogue markers (STT often has speakers)
    if any(m in t for m in ("менеджер", "клиент", "оператор", "пациент", "manager:", "client:")):
        score += 0.2
        flags.append("has_speakers")

    # --- Urgent ---
    if urgent:
        flags.append("red_flag_urgent")
        if any(w in t for w in ("103", "скорая", "приёмное", "приемное", "shoshilinch", "tez yordam")):
            score += 0.4
            strengths_ru.append("red flag → маршрутизация в приём/103")
            strengths_uz.append("red flag → qabul/103 yo'naltirish")
        else:
            score -= 0.8
            weak_ru.append("возможны острые симптомы — не эскалировано")
            weak_uz.append("o'tkir belgilar mumkin — eskalatsiya yo'q")
            flags.append("urgent_not_escalated")

    # Confirm details
    if any(w in t for w in ("фио", "ф.и.о", "паспорт", "телефон", "номер", "ismingiz", "telefon")):
        score += 0.25
        strengths_ru.append("сверка контактов/ФИО")
        strengths_uz.append("aloqa/F.I.Sh tekshiruvi")

    score = max(0.0, min(10.0, score))
    sentiment = "neutral"
    if score >= 7.5 or booking == "booked":
        sentiment = "positive"
    if score <= 4.0 or booking == "rejected" or "rude" in flags:
        sentiment = "negative"
    if "red_flag_urgent" in flags:
        sentiment = "mixed"

    need_ru, need_uz = _extract_client_need(t, services)
    if "missed_need" in flags:
        need_ru, need_uz = "не выявлена", "aniqlanmagan"

    advice_ru: list[str] = []
    advice_uz: list[str] = []
    if "red_flag_urgent" in flags:
        advice_ru.append("СРОЧНО: не консультировать по телефону — приём / 103 при угрозе жизни.")
        advice_uz.append("SHOSHILINCH: telefonda maslahat bermang — qabul / 103.")
    if "no_next_step" in flags:
        advice_ru.append("Закройте звонок next step: запись / дата перезвона / задача в CRM.")
        advice_uz.append("Suhbatni next step bilan yoping: yozuv / qayta qo'ng'iroq / CRM vazifa.")
    if "missed_need" in flags:
        advice_ru.append("Открытые вопросы: «Что беспокоит?» «Как давно?» «Какой результат нужен?»")
        advice_uz.append("Ochiq savollar: nima bezovta? qachondan? qanday natija kerak?")
    if "no_greeting" in flags:
        advice_ru.append("Старт: приветствие + Kimyo Hospital + ваше имя.")
        advice_uz.append("Start: salom + Kimyo Hospital + ismingiz.")
    if "price_only" in flags:
        advice_ru.append("После цены — что входит, подготовка, зачем врачу нужен результат.")
        advice_uz.append("Narxdan keyin — nima kiradi, tayyorgarlik, natija nima uchun kerak.")
    if "objection_missed" in flags:
        advice_ru.append("Отработайте «дорого/подумаю»: ценность + мягкий hold-слот + время перезвона.")
        advice_uz.append("«Qimmat/o'ylab» ni ishlang: qiymat + hold-slot + qayta qo'ng'iroq vaqti.")
    if "medical_overpromise" in flags:
        advice_ru.append("Не обещайте диагноз/100% лечение — только маршрут к врачу.")
        advice_uz.append("Tashxis/100% davolash va'da qilmang — faqat shifokorga yo'nalish.")
    if booking == "booked":
        advice_ru.append("Подтвердите SMS/заметку в CRM: дата, услуга, ФИО, телефон.")
        advice_uz.append("CRM/SMS tasdiq: sana, xizmat, F.I.Sh, telefon.")
    if not advice_ru:
        advice_ru.append("Зафиксируйте договорённость в сделке и поставьте follow-up, если не пришёл.")
        advice_uz.append("Kelishuvni bitimga yozing va kelmasa follow-up qo'ying.")

    sum_ru, sum_uz = _build_smart_summary(
        kind, raw, t, need_ru, need_uz, booking, score, flags, services
    )
    rep_ru, rep_uz = _suggested_reply_for(t, need_ru, booking, services, flags)

    # Short quote from transcript for manager
    quote = ""
    for line in raw.splitlines():
        line = line.strip()
        if len(line) > 25 and not line.startswith("["):
            quote = _snip(line, 120)
            break
    if not quote and nlen > 40:
        quote = _snip(raw, 120)

    return {
        "score": round(score, 1),
        "summary": pack_bilingual(sum_ru, sum_uz),
        "strengths": pack_bilingual(
            "; ".join(strengths_ru) or "—",
            "; ".join(strengths_uz) or "—",
        ),
        "weaknesses": pack_bilingual(
            "; ".join(weak_ru) or "—",
            "; ".join(weak_uz) or "—",
        ),
        "advice": pack_bilingual(
            " ".join(f"{i+1}) {a}" for i, a in enumerate(advice_ru[:5])),
            " ".join(f"{i+1}) {a}" for i, a in enumerate(advice_uz[:5])),
        ),
        "sentiment": sentiment,
        "flags": flags,
        "client_need": pack_bilingual(need_ru, need_uz),
        "booking_result": booking,
        "suggested_reply": pack_bilingual(rep_ru, rep_uz),
        "transcript_quote": quote,
        "services": [f"{a}" for a, _ in services],
        "model": "heuristic-v4",
    }


def _ai_analyze(text: str, kind: str, meta: str) -> dict[str, Any] | None:
    if not XAI_API_KEY or not (text or "").strip():
        return None
    try:
        from openai import OpenAI

        client = OpenAI(api_key=XAI_API_KEY, base_url=XAI_BASE_URL)
        user_msg = (
            f"Тип: {kind}\nМета: {meta}\n\n"
            f"ТРАНСКРИПТ / ТЕКСТ (до 12000 симв):\n{(text or '')[:12000]}"
        )
        try:
            resp = client.responses.create(
                model=XAI_MODEL,
                input=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
            )
            content = getattr(resp, "output_text", None) or ""
        except Exception:
            chat = client.chat.completions.create(
                model=XAI_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.25,
            )
            content = chat.choices[0].message.content or ""

        parsed = _parse_json_response(content)
        if not parsed:
            logger.warning("AI returned non-JSON")
            return None
        return _normalize_result(parsed, XAI_MODEL)
    except Exception as exc:
        logger.error("AI analyze failed: %s", exc)
        return None


def analyze_one(comm: dict[str, Any]) -> dict[str, Any]:
    # Prefer full transcript over stub text
    text = (comm.get("transcript") or comm.get("text") or "").strip()
    kind = comm.get("kind") or "note"
    meta = (
        f"id={comm.get('id')} lead={comm.get('lead_id')} "
        f"manager={comm.get('manager_id')} direction={comm.get('direction')} "
        f"duration={comm.get('duration')} recording={bool(comm.get('recording_url'))}"
    )
    result = _ai_analyze(text, kind, meta) or _heuristic_analyze(text, kind)
    # Blend clinic scorecard (virtual ROP) when real text exists
    try:
        from rop_control import scorecard_evaluate

        if len(text) > 60 and not text.startswith("["):
            sc = scorecard_evaluate(text)
            # weighted blend: keep AI/heuristic but pull toward scorecard
            result["score"] = round(
                0.55 * float(result["score"]) + 0.45 * float(sc["total_0_10"]), 1
            )
            flags = list(result.get("flags") or [])
            for f in sc.get("flags") or []:
                if f not in flags:
                    flags.append(f)
            result["flags"] = flags
            result["model"] = str(result.get("model") or "") + "+scorecard"
    except Exception:
        pass
    save_analysis(
        comm["id"],
        score=float(result["score"]),
        summary=str(result.get("summary") or ""),
        strengths=str(result.get("strengths") or ""),
        weaknesses=str(result.get("weaknesses") or ""),
        advice=str(result.get("advice") or ""),
        sentiment=str(result.get("sentiment") or "neutral"),
        flags=list(result.get("flags") or []),
        model=str(result.get("model") or "unknown"),
    )
    # Write coaching note into amoCRM deal card
    try:
        from amo_notes_publisher import post_after_analysis

        post_after_analysis(comm, result)
    except Exception:
        pass
    return result


def analyze_batch(limit: int | None = None) -> int:
    limit = limit or ANALYZE_BATCH_SIZE
    items = unanalyzed_communications(limit=limit)
    done = 0
    for comm in items:
        text = (comm.get("transcript") or comm.get("text") or "").strip()
        # Skip pure technical stubs only if no transcript
        stub_prefixes = (
            "[incoming_chat_message]",
            "[outgoing_chat_message]",
            "[entity_direct_message]",
            "[incoming_call]",
            "[outgoing_call]",
        )
        if (
            text.startswith(stub_prefixes)
            and not (comm.get("transcript") or "").strip()
            and ("message_id=" in text or "note_id=" in text)
        ):
            save_analysis(
                comm["id"],
                score=5.0,
                summary=pack_bilingual(
                    "Событие зафиксировано; ждём запись звонка/текст.",
                    "Hodisa qayd etildi; yozuv/matn kutilmoqda.",
                ),
                strengths=pack_bilingual("есть активность", "faollik bor"),
                weaknesses=pack_bilingual(
                    "нет тела разговора для NLP",
                    "suhbat matni yo'q",
                ),
                advice=pack_bilingual(
                    "Система скачает запись и сделает транскрипт автоматически.",
                    "Tizim yozuvni yuklab, avtomatik transkript qiladi.",
                ),
                sentiment="neutral",
                flags=["no_text_body"],
                model="stub",
            )
            done += 1
            continue
        analyze_one(comm)
        done += 1
    logger.info("Analyzed %s communications", done)
    return done
