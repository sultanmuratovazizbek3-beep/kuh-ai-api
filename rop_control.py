"""
Virtual ROP (руководитель отдела продаж) — replaces human supervisor.

Features inspired by Gong / call QA / sales control systems:
- Clinic scorecard (greeting, need, service, price, booking, ethics)
- SLA: stuck leads, no booking, low quality, no activity
- Alerts queue for ROP
- Manager ranking & coaching cards
- Service scripts library
- Objection trainer scenarios
- Excel export of control pack
"""

from __future__ import annotations

import csv
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from bilingual import pack_bilingual
from config import LOST_STATUS_IDS, REPORTS_DIR, WON_STATUS_IDS
from medical_coach import PHRASES, detect_services, is_urgent
from storage import db, init_db, manager_name_map, period_stats

# --- Clinic scorecard (weights sum ~100) ---
SCORECARD = [
    {
        "id": "greeting",
        "weight": 15,
        "ru": "Приветствие + клиника + имя",
        "uz": "Salom + klinika + ism",
        "keywords": (
            "здравствуй",
            "добрый",
            "assalom",
            "ассалом",
            "kimyo",
            "клиник",
            "hospital",
        ),
    },
    {
        "id": "need",
        "weight": 20,
        "ru": "Выявление жалобы/потребности",
        "uz": "Shikoyat/ehtiyoj aniqlash",
        "keywords": (
            "беспоко",
            "жалоб",
            "нужн",
            "хочу",
            "боль",
            "симптом",
            "bezovta",
            "kerak",
            "og'riq",
            "nima",
        ),
    },
    {
        "id": "route",
        "weight": 15,
        "ru": "Маршрут: врач / УЗИ / МРТ / анализы",
        "uz": "Yo'nalish: shifokor / UZI / MRT",
        "keywords": (
            "узи",
            "мрт",
            "кт",
            "анализ",
            "врач",
            "невролог",
            "эндокрин",
            "терапевт",
            "офтальм",
            "uzi",
            "mrt",
            "shifokor",
            "qabul",
        ),
    },
    {
        "id": "value_price",
        "weight": 10,
        "ru": "Цена с ценностью (не только цифра)",
        "uz": "Narx + qiymat",
        "keywords": (
            "стоит",
            "цена",
            "сумм",
            "narx",
            "входит",
            "подготов",
            "результат",
            "nima kiradi",
        ),
    },
    {
        "id": "booking",
        "weight": 25,
        "ru": "Запись / next step",
        "uz": "Yozuv / keyingi qadam",
        "keywords": (
            "запис",
            "приед",
            "приход",
            "время",
            "завтра",
            "сегодня",
            "перезвон",
            "yozib",
            "soat",
            "ertaga",
            "keling",
            "qayta qo'ng",
        ),
    },
    {
        "id": "ethics",
        "weight": 15,
        "ru": "Этика: без диагноза и ложных гарантий",
        "uz": "Etika: tashxissiz, soxta kafolatsiz",
        "keywords_bad": (
            "гарантир",
            "100%",
            "точно вылеч",
            "у вас точно",
            "albatta tuzal",
            "диагноз",
        ),
    },
]

# SLA thresholds (hours)
SLA_NO_BOOKING_HOURS = 24
SLA_STUCK_HOURS = 48
SLA_LOW_SCORE = 4.5

# Working scripts from KUH call mining:
# - WON calls mention booking ~5× more often than LOST
# - Many long calls die on "how to get there" / WhatsApp spam instead of closing
# - Instagram leads (MRT, balloon, endo) need fast qualification → 2 slots
SERVICE_SCRIPTS: dict[str, dict[str, Any]] = {
    "mrt": {
        "title": pack_bilingual("МРТ — дожать запись", "MRT — yozuvni yopish"),
        "openers": [
            pack_bilingual(
                "Kimyo Hospital, … . МРТ — какая зона и есть направление от врача?",
                "Kimyo Hospital, … . MRT — qaysi zona va shifokor yo'llanmasi bormi?",
            ),
            pack_bilingual(PHRASES["prep_mrt_ru"], PHRASES["prep_mrt_uz"]),
            pack_bilingual(PHRASES["close_force_ru"], PHRASES["close_force_uz"]),
        ],
        "checklist": [
            pack_bilingual(
                "1) Зона МРТ + направление. 2) Противопоказания (металл/стимулятор/беременность). 3) ДВА слота. 4) ФИО+телефон. 5) Гео — ПОСЛЕ записи, не вместо неё.",
                "1) MRT zona + yo'llanma. 2) Qarshi ko'rsatma. 3) IKKITA slot. 4) F.I.Sh+tel. 5) Geo — YOZUVDAN KEYIN.",
            ),
            pack_bilingual(PHRASES["no_diag_ru"], PHRASES["no_diag_uz"]),
            pack_bilingual(PHRASES["book_confirm_ru"], PHRASES["book_confirm_uz"]),
            pack_bilingual(PHRASES["geo_ru"], PHRASES["geo_uz"]),
        ],
        "objections": [
            {
                "q": pack_bilingual("Дорого", "Qimmat"),
                "a": pack_bilingual(PHRASES["price_hard_ru"], PHRASES["price_hard_uz"]),
            },
            {
                "q": pack_bilingual("Боюсь закрытого / клаустрофобия", "Yopiq joydan qo'rqaman"),
                "a": pack_bilingual(
                    "Понимаю. На месте подскажут, как проходит процедура и как снизить дискомфорт. Главное — не откладывать обследование: какой слот ближе — сегодня вечер или завтра утро?",
                    "Tushunaman. Joyida protsedura va noqulaylikni kamaytirishni aytishadi. Tekshiruvni kechiktirmang: qaysi slot yaqin — bugun kech yoki ertaga ertalab?",
                ),
            },
            {
                "q": pack_bilingual("Где вы находитесь? Диктуйте дорогу", "Qayerdasiz? Yo'lni ayting"),
                "a": pack_bilingual(PHRASES["geo_ru"], PHRASES["geo_uz"]),
            },
        ],
    },
    "uzi": {
        "title": pack_bilingual("УЗИ — быстрый close", "UZI — tez yozuv"),
        "openers": [
            pack_bilingual(
                "УЗИ — какая зона? Есть направление? Когда удобно подойти: сегодня или завтра?",
                "UZI — qaysi zona? Yo'llanma bormi? Qachon qulay: bugun yoki ertaga?",
            ),
            pack_bilingual(PHRASES["prep_uzi_ru"], PHRASES["prep_uzi_uz"]),
        ],
        "checklist": [
            pack_bilingual(
                "Зона → подготовка (натощак?) → 2 слота → ФИО/тел → гео после записи.",
                "Zona → tayyorgarlik (och qorin?) → 2 slot → F.I.Sh/tel → geo yozuvdan keyin.",
            ),
            pack_bilingual(PHRASES["book_confirm_ru"], PHRASES["book_confirm_uz"]),
        ],
        "objections": [
            {
                "q": pack_bilingual("Подумаю", "O'ylab ko'raman"),
                "a": pack_bilingual(PHRASES["think_ru"], PHRASES["think_uz"]),
            },
            {
                "q": pack_bilingual("Скиньте адрес, я сам найду", "Manzil tashlang, o'zim topaman"),
                "a": pack_bilingual(
                    "Сначала забронирую время — иначе приедете, а слота нет. После записи — гео в WhatsApp/SMS.",
                    "Avval vaqtni bron qilaman — aks holda kelasiz, slot bo'lmasligi mumkin. Yozuvdan keyin — WhatsApp/SMS geo.",
                ),
            },
        ],
    },
    "endo": {
        "title": pack_bilingual("Эндокринолог", "Endokrinolog"),
        "openers": [
            pack_bilingual(
                "Эндокринолог: щитовидка, сахар, вес или гормоны? Уже есть анализы/УЗИ?",
                "Endokrinolog: qalqonsimon, qand, vazn yoki gormonlar? Tahlil/UZI bormi?",
            ),
            pack_bilingual(PHRASES["close_force_ru"], PHRASES["close_force_uz"]),
        ],
        "checklist": [
            pack_bilingual(
                "Не ставить диагноз. Спросить: анализы на руках? Записать к эндокринологу + при необходимости УЗИ/лаборатория в один визит.",
                "Tashxis qo'ymang. So'rang: tahlil bormi? Endokrinolog + kerak bo'lsa UZI/laboratoriya bir tashrifda.",
            ),
            pack_bilingual(PHRASES["book_ru"], PHRASES["book_uz"]),
        ],
        "objections": [
            {
                "q": pack_bilingual("Только анализ, без врача", "Faqat tahlil, shifokorsiz"),
                "a": pack_bilingual(
                    "Анализы сдать можно. Но без врача вы получите цифры без плана — чаще люди делают лишнее. Запишу на забор + короткий приём, если есть окно.",
                    "Tahlil topshirish mumkin. Shifokorsiz faqat raqam — odamlar ortiqcha topshiradi. Namuna + qisqa qabulga yozaman, slot bo'lsa.",
                ),
            }
        ],
    },
    "ped_neuro": {
        "title": pack_bilingual("Детский невролог", "Bolalar nevrologi"),
        "openers": [
            pack_bilingual(
                "Сколько лет ребёнку и что беспокоит родителей (срок, когда началось)?",
                "Bola yoshi va ota-onani nima bezovta qiladi (qachon boshlangan)?",
            ),
            pack_bilingual(PHRASES["book_ru"], PHRASES["book_uz"]),
        ],
        "checklist": [
            pack_bilingual(
                "Без диагноза по телефону. Паспорт родителя, свидетельства, предыдущие заключения. 2 слота. При судорогах/потере сознания — не ждать, 103/приём.",
                "Telefonda tashxissiz. Ota-ona pasporti, guvohnoma, oldingi xulosa. 2 slot. Tutqanoq/hushdan ketish — kutmang, 103/qabul.",
            ),
        ],
        "objections": [
            {
                "q": pack_bilingual("Это опасно? Что у ребёнка?", "Xavflimi? Bolada nima?"),
                "a": pack_bilingual(PHRASES["no_diag_ru"], PHRASES["no_diag_uz"]),
            }
        ],
    },
    "default": {
        "title": pack_bilingual(
            "Регистратура — скрипт на результат (запись)",
            "Registratura — natija skripti (yozuv)",
        ),
        "openers": [
            pack_bilingual(
                PHRASES["greet_ru"].format(name="…"),
                PHRASES["greet_uz"].format(name="…"),
            ),
            pack_bilingual(PHRASES["need_ru"], PHRASES["need_uz"]),
            pack_bilingual(PHRASES["close_force_ru"], PHRASES["close_force_uz"]),
        ],
        "checklist": [
            pack_bilingual(
                "ЖЁСТКИЙ ПОРЯДОК (из разбора звонков KUH): 1) Кто звонит + услуга. 2) Не лечить по телефону. 3) ДВА конкретных слота. 4) ФИО+телефон в CRM. 5) Подтверждение вслух. 6) Адрес/гео — только ПОСЛЕ записи. 7) Не объяснять дорогу 5 минут, пока клиент за рулём.",
                "QATTIQ TARTIB: 1) Kim + xizmat. 2) Telefonda davolamang. 3) IKKITA slot. 4) F.I.Sh+tel CRM. 5) Ovoz chiqarib tasdiq. 6) Manzil — faqat YOZUVDAN KEYIN. 7) Rulda 5 daqiqa yo'l tushuntirmang.",
            ),
            pack_bilingual(PHRASES["book_confirm_ru"], PHRASES["book_confirm_uz"]),
            pack_bilingual(PHRASES["geo_ru"], PHRASES["geo_uz"]),
            pack_bilingual(PHRASES["wa_spam_ru"], PHRASES["wa_spam_uz"]),
            pack_bilingual(
                "Контроль: если в разговоре не прозвучала дата/время — сделка «остынет». Перезвон в тот же день.",
                "Nazorat: suhbatda sana/vaqt yo'q bo'lsa — bitim soviyadi. Shu kuni qayta qo'ng'iroq.",
            ),
        ],
        "objections": [
            {
                "q": pack_bilingual("Дорого", "Qimmat"),
                "a": pack_bilingual(PHRASES["price_hard_ru"], PHRASES["price_hard_uz"]),
            },
            {
                "q": pack_bilingual("Подумаю / сам перезвоню", "O'ylab ko'raman / o'zim chaqiraman"),
                "a": pack_bilingual(PHRASES["think_ru"], PHRASES["think_uz"]),
            },
            {
                "q": pack_bilingual("Где вы? Как доехать?", "Qayerdasiz? Qanday boraman?"),
                "a": pack_bilingual(PHRASES["geo_ru"], PHRASES["geo_uz"]),
            },
            {
                "q": pack_bilingual("Скиньте в WhatsApp, я за рулём", "WhatsApp tashlang, rulda man"),
                "a": pack_bilingual(PHRASES["wa_spam_ru"], PHRASES["wa_spam_uz"]),
            },
            {
                "q": pack_bilingual("Из Instagram увидел(а)", "Instagramdan ko'rdim"),
                "a": pack_bilingual(PHRASES["instagram_ru"], PHRASES["instagram_uz"]),
            },
        ],
    },
}

OBJECTION_TRAINER = [
    {
        "id": "price",
        "level": 1,
        "client_ru": "У вас дорого, в другой клинике дешевле.",
        "client_uz": "Sizda qimmat, boshqa klinikada arzonroq.",
        "good_ru": PHRASES["price_hard_ru"],
        "good_uz": PHRASES["price_hard_uz"],
        "bad_ru": "Ну мы лучшие, платите / не знаю цену, потом скажем.",
    },
    {
        "id": "think",
        "level": 1,
        "client_ru": "Я подумаю и сам перезвоню.",
        "client_uz": "O'ylab ko'raman, o'zim qo'ng'iroq qilaman.",
        "good_ru": PHRASES["think_ru"],
        "good_uz": PHRASES["think_uz"],
        "bad_ru": "Ну как хотите, до свидания.",
    },
    {
        "id": "geo_drive",
        "level": 1,
        "client_ru": "Я уже еду, диктуйте как проехать, мост / разворот…",
        "client_uz": "Ketayapman, yo'lni ayting, ko'prik / burilish…",
        "good_ru": PHRASES["geo_ru"],
        "good_uz": PHRASES["geo_uz"],
        "bad_ru": "5 минут диктовать повороты, пока клиент за рулём (как в реальных звонках — запись уже есть, сделка всё равно срывается).",
    },
    {
        "id": "wa_spam",
        "level": 1,
        "client_ru": "Скиньте в WhatsApp локацию на мой номер.",
        "client_uz": "WhatsApp ga lokatsiya tashlang.",
        "good_ru": PHRASES["wa_spam_ru"] + " " + PHRASES["geo_sms_ru"],
        "good_uz": PHRASES["wa_spam_uz"] + " " + PHRASES["geo_sms_uz"],
        "bad_ru": "Кидать 10 раз в WA, пока номер в спаме, и спорить «почему не доходит».",
    },
    {
        "id": "diag",
        "level": 2,
        "client_ru": "Скажите по телефону, что у меня? Это опасно?",
        "client_uz": "Telefonda ayting, menda nima? Xavflimi?",
        "good_ru": PHRASES["no_diag_ru"] + " " + PHRASES["close_force_ru"],
        "good_uz": PHRASES["no_diag_uz"] + " " + PHRASES["close_force_uz"],
        "bad_ru": "Похоже на серьёзное, срочно платите за МРТ.",
    },
    {
        "id": "no_slot_close",
        "level": 2,
        "client_ru": "Ладно, потом как-нибудь запишусь.",
        "client_uz": "Keyin qachondir yozilaman.",
        "good_ru": PHRASES["close_force_ru"] + " Без даты в CRM — сделка почти не возвращается.",
        "good_uz": PHRASES["close_force_uz"] + " CRMda sanasiz — bitim qaytmaydi deyarli.",
        "bad_ru": "Хорошо, звоните когда решите.",
    },
    {
        "id": "competitor",
        "level": 2,
        "client_ru": "В другой клинике быстрее / дешевле.",
        "client_uz": "Boshqa klinikada tezroq / arzonroq.",
        "good_ru": "Принял. Не спорю. Ближайшие окна у нас: … и …. Что важнее — скорость слота или состав услуги? Подстроим.",
        "good_uz": "Tushundim. Bahslashmayman. Eng yaqin oynalar: … va …. Muhimi — slot tezligi yoki xizmat tarkibimi? Moslashtiramiz.",
        "bad_ru": "Те врут, только к нам.",
    },
]


def scorecard_evaluate(text: str) -> dict[str, Any]:
    t = (text or "").lower()
    items = []
    total_w = 0
    got = 0.0
    flags = []
    for rule in SCORECARD:
        w = rule["weight"]
        total_w += w
        if rule["id"] == "ethics":
            bad = any(k in t for k in rule.get("keywords_bad") or ())
            ok = not bad and len(t) > 40
            if bad:
                flags.append("medical_overpromise")
            score = 0.0 if bad else (1.0 if ok else 0.5)
        else:
            hits = sum(1 for k in rule["keywords"] if k in t)
            if hits >= 2:
                score = 1.0
            elif hits == 1:
                score = 0.65
            else:
                score = 0.15 if len(t) > 80 else 0.0
            if rule["id"] == "booking" and score < 0.5:
                flags.append("no_next_step")
            if rule["id"] == "need" and score < 0.5:
                flags.append("missed_need")
            if rule["id"] == "greeting" and score < 0.5:
                flags.append("no_greeting")
        got += w * score
        items.append(
            {
                "id": rule["id"],
                "title": pack_bilingual(rule["ru"], rule["uz"]),
                "weight": w,
                "score_0_1": round(score, 2),
                "points": round(w * score, 1),
                "max_points": w,
            }
        )
    total = round(10 * got / max(total_w, 1), 1)
    if is_urgent(text):
        flags.append("red_flag_urgent")
    return {
        "total_0_10": total,
        "items": items,
        "flags": flags,
        "services": [f"{a}/{b}" for a, b in detect_services(text)],
    }


def _hours_ago(ts: int | None) -> float:
    if not ts:
        return 9999.0
    return max(0.0, (time.time() - ts) / 3600.0)


def _conv(won: int, lost: int) -> str:
    total = (won or 0) + (lost or 0)
    if total <= 0:
        return "—"
    return f"{round(100.0 * (won or 0) / total)}%"


def build_control_pack(hours: int = 24) -> dict[str, Any]:
    """Full virtual-ROP snapshot for the UI."""
    init_db()
    now = int(time.time())
    since = now - hours * 3600
    names = manager_name_map()
    stats = period_stats(since, now)

    with db() as conn:
        # Analyses + comms
        rows = conn.execute(
            """
            SELECT c.id, c.kind, c.manager_id, c.lead_id, c.created_at, c.duration,
                   c.text, c.transcript, a.score, a.summary, a.weaknesses, a.advice, a.flags_json
            FROM communications c
            LEFT JOIN analyses a ON a.communication_id = c.id
            WHERE c.created_at >= ?
            ORDER BY c.created_at DESC
            LIMIT 500
            """,
            (since,),
        ).fetchall()

        leads = conn.execute(
            """
            SELECT lead_id, name, status_id, pipeline_id, responsible_user_id,
                   created_at, updated_at, is_won, is_lost, price
            FROM lead_snapshots
            WHERE updated_at >= ? OR created_at >= ?
            """,
            (since - 48 * 3600, since),
        ).fetchall()

        # last activity per lead
        last_act = {
            r["lead_id"]: r["mx"]
            for r in conn.execute(
                """
                SELECT lead_id, MAX(created_at) AS mx
                FROM communications
                WHERE lead_id IS NOT NULL
                GROUP BY lead_id
                """
            ).fetchall()
            if r["lead_id"]
        }

    # Enrich analyses with scorecard when transcript long enough
    scored_calls = []
    low_quality = []
    for r in rows:
        text = (r["transcript"] or r["text"] or "").strip()
        sc = None
        if len(text) > 60 and not text.startswith("["):
            sc = scorecard_evaluate(text)
        score = r["score"]
        if sc and (score is None or score == 5.0):
            score = sc["total_0_10"]
        item = {
            "id": r["id"],
            "kind": r["kind"],
            "manager_id": r["manager_id"],
            "manager": names.get(r["manager_id"] or 0, f"ID {r['manager_id']}"),
            "lead_id": r["lead_id"],
            "created_at": r["created_at"],
            "duration": r["duration"],
            "score": score,
            "summary": r["summary"],
            "weaknesses": r["weaknesses"],
            "advice": r["advice"],
            "scorecard": sc,
            "preview": text[:180],
        }
        if r["kind"] == "call" and sc:
            scored_calls.append(item)
        if score is not None and score < SLA_LOW_SCORE and len(text) > 40:
            low_quality.append(item)

    # Queue: only truly stuck open leads (strict SLA)
    queue = []
    closed_ids = WON_STATUS_IDS | LOST_STATUS_IDS
    for lead in leads:
        lid = lead["lead_id"]
        if lead["is_won"] or lead["is_lost"]:
            continue
        if lead["status_id"] in closed_ids:
            continue
        last_ts = last_act.get(lid) or lead["updated_at"] or lead["created_at"]
        idle_h = _hours_ago(last_ts)
        age_h = _hours_ago(lead["created_at"])
        reasons = []
        severity = 0
        # no activity 24h+
        if idle_h >= SLA_NO_BOOKING_HOURS:
            reasons.append(
                pack_bilingual(
                    f"Нет активности {idle_h:.0f}ч",
                    f"{idle_h:.0f} soat faollik yo'q",
                )
            )
            severity += 2 if idle_h < SLA_STUCK_HOURS else 3
        # open longer than 72h and idle 24h+
        if age_h >= 72 and idle_h >= SLA_NO_BOOKING_HOURS:
            reasons.append(
                pack_bilingual(
                    "Сделка «висит» без прогресса",
                    "Bitim rivojsiz osilib turibdi",
                )
            )
            severity += 1
        if not reasons:
            continue
        queue.append(
            {
                "lead_id": lid,
                "name": lead["name"],
                "manager": names.get(lead["responsible_user_id"] or 0, "—"),
                "manager_id": lead["responsible_user_id"],
                "status_id": lead["status_id"],
                "pipeline_id": lead["pipeline_id"],
                "idle_hours": round(idle_h, 1),
                "reasons": reasons,
                "severity": severity,
                "url": f"https://kuhhospital.amocrm.ru/leads/detail/{lid}",
            }
        )
    queue.sort(key=lambda x: (-x["severity"], -x["idle_hours"]))
    queue = queue[:80]

    # Alerts
    alerts = []
    for item in low_quality[:30]:
        alerts.append(
            {
                "type": "low_quality",
                "severity": "high" if (item["score"] or 0) < 3.5 else "medium",
                "title": pack_bilingual(
                    f"Слабый контакт score {item['score']}",
                    f"Zaif kontakt score {item['score']}",
                ),
                "manager": item["manager"],
                "lead_id": item["lead_id"],
                "detail": item.get("weaknesses") or item.get("preview") or "",
                "advice": item.get("advice") or "",
                "created_at": item["created_at"],
            }
        )
    for item in scored_calls:
        sc = item.get("scorecard") or {}
        if "red_flag_urgent" in (sc.get("flags") or []):
            alerts.append(
                {
                    "type": "red_flag",
                    "severity": "critical",
                    "title": pack_bilingual(
                        "Red flag / срочность в разговоре",
                        "Red flag / shoshilinch",
                    ),
                    "manager": item["manager"],
                    "lead_id": item["lead_id"],
                    "detail": item.get("preview") or "",
                    "advice": pack_bilingual(
                        "Проверить: маршрутизация на приём/103, не диагноз по телефону.",
                        "Tekshiring: qabul/103, telefonda tashxis yo'q.",
                    ),
                    "created_at": item["created_at"],
                }
            )
        if "no_next_step" in (sc.get("flags") or []):
            alerts.append(
                {
                    "type": "no_next_step",
                    "severity": "medium",
                    "title": pack_bilingual("Нет записи/next step", "Yozuv/next step yo'q"),
                    "manager": item["manager"],
                    "lead_id": item["lead_id"],
                    "detail": item.get("preview") or "",
                    "advice": pack_bilingual(
                        "Обязать зафиксировать дату перезвона или запись.",
                        "Qayta qo'ng'iroq yoki yozuv sanasini majburiy qiling.",
                    ),
                    "created_at": item["created_at"],
                }
            )
    for q in queue[:25]:
        alerts.append(
            {
                "type": "stuck_lead",
                "severity": "high" if q["severity"] >= 3 else "medium",
                "title": pack_bilingual(
                    f"Зависшая сделка {q['idle_hours']}ч",
                    f"Osilib qolgan bitim {q['idle_hours']} soat",
                ),
                "manager": q["manager"],
                "lead_id": q["lead_id"],
                "detail": "; ".join(q["reasons"]),
                "advice": pack_bilingual(
                    "Поставить задачу менеджеру / перехватить контроль.",
                    "Menejerga vazifa / nazoratni oling.",
                ),
                "created_at": now,
            }
        )

    # severity order
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    alerts.sort(key=lambda a: (sev_order.get(a["severity"], 9), -(a.get("created_at") or 0)))

    # Manager ranking + coaching cards
    mgr_map: dict[int, dict[str, Any]] = {}
    for m in stats.get("managers") or []:
        mid = m.get("manager_id") or 0
        mgr_map[mid] = {
            **m,
            "low_quality_count": 0,
            "scorecard_avg": None,
            "scores": [],
            "top_issues": [],
        }
    for item in scored_calls + low_quality:
        mid = item.get("manager_id") or 0
        if mid not in mgr_map:
            mgr_map[mid] = {
                "manager_id": mid,
                "name": item.get("manager") or f"ID {mid}",
                "calls_total": 0,
                "chats_total": 0,
                "leads_won": 0,
                "leads_lost": 0,
                "leads_worked": 0,
                "avg_quality_score": None,
                "low_quality_count": 0,
                "scores": [],
                "top_issues": [],
            }
        if item.get("score") is not None:
            mgr_map[mid]["scores"].append(float(item["score"]))
        if item.get("score") is not None and item["score"] < SLA_LOW_SCORE:
            mgr_map[mid]["low_quality_count"] += 1
        if item.get("weaknesses"):
            mgr_map[mid]["top_issues"].append(item["weaknesses"][:120])

    ranking = []
    for mid, m in mgr_map.items():
        scores = m.get("scores") or []
        avg_sc = round(sum(scores) / len(scores), 1) if scores else m.get("avg_quality_score")
        won = m.get("leads_won") or 0
        lost = m.get("leads_lost") or 0
        conv = (100.0 * won / (won + lost)) if (won + lost) else None
        # control index: higher better
        control = 50.0
        if avg_sc is not None:
            control = avg_sc * 8
        control += min(20, (m.get("calls_total") or 0) * 0.15)
        control += min(15, won * 1.5)
        control -= min(25, (m.get("low_quality_count") or 0) * 3)
        ranking.append(
            {
                "manager_id": mid,
                "name": m.get("name") or f"ID {mid}",
                "calls": m.get("calls_total") or 0,
                "chats": m.get("chats_total") or 0,
                "won": won,
                "lost": lost,
                "conv": None if conv is None else round(conv, 0),
                "quality": avg_sc,
                "low_quality_count": m.get("low_quality_count") or 0,
                "control_index": round(max(0, min(100, control)), 1),
                "issues": (m.get("top_issues") or [])[:3],
                "coaching": _coaching_blurb(avg_sc, m.get("low_quality_count") or 0, won, lost),
            }
        )
    ranking.sort(key=lambda x: (-(x["control_index"] or 0), -(x["won"] or 0)))

    # Pipelines breakdown
    pipes: dict[int, dict[str, int]] = {}
    for lead in leads:
        pid = lead["pipeline_id"] or 0
        pipes.setdefault(pid, {"worked": 0, "won": 0, "lost": 0})
        pipes[pid]["worked"] += 1
        if lead["is_won"]:
            pipes[pid]["won"] += 1
        if lead["is_lost"]:
            pipes[pid]["lost"] += 1

    return {
        "ok": True,
        "generated_at": now,
        "hours": hours,
        "sla": {
            "no_booking_hours": SLA_NO_BOOKING_HOURS,
            "stuck_hours": SLA_STUCK_HOURS,
            "low_score": SLA_LOW_SCORE,
        },
        "summary": {
            "alerts": len(alerts),
            "critical": sum(1 for a in alerts if a["severity"] == "critical"),
            "queue": len(queue),
            "low_quality": len(low_quality),
            "scored_calls": len(scored_calls),
            "managers": len(ranking),
        },
        "alerts": alerts[:80],
        "queue": queue[:50],
        "ranking": ranking,
        "scored_calls": scored_calls[:40],
        "low_quality": low_quality[:40],
        "pipelines": [
            {
            "pipeline_id": k,
            **v,
            "conv": _conv(v["won"], v["lost"]),
        }
            for k, v in pipes.items()
        ],
        "totals": stats.get("totals") or {},
        "scripts": {k: v["title"] for k, v in SERVICE_SCRIPTS.items()},
        "role": "virtual_rop",
        "tagline": pack_bilingual(
            "AI-РОП: контроль качества, SLA и коучинг 24/7",
            "AI-ROP: sifat, SLA va kouсhing 24/7",
        ),
    }


def _coaching_blurb(quality, low_n, won, lost) -> str:
    tips = []
    if quality is not None and quality < 5:
        tips.append(
            pack_bilingual(
                "Разбор 2 звонков на планёрке + чек-лист записи.",
                "Planerkada 2 ta qo'ng'iroq tahlili + yozuv chek-listi.",
            )
        )
    if low_n >= 3:
        tips.append(
            pack_bilingual(
                "Много слабых контактов — парное прослушивание с РОП.",
                "Ko'p zaif kontakt — ROP bilan birga tinglash.",
            )
        )
    if won == 0 and (lost or 0) > 5:
        tips.append(
            pack_bilingual(
                "Нет won при отказах — работа с возражением «дорого/подумаю».",
                "Rad etishlar bor, won yo'q — «qimmat/o'ylab» e'tirozlari.",
            )
        )
    if not tips:
        tips.append(
            pack_bilingual(
                "Держать уровень: next step в 100% контактов.",
                "Darajani saqlang: 100% kontaktda next step.",
            )
        )
    return " | ".join(tips[:2])


def get_script(service_key: str = "default") -> dict[str, Any]:
    key = (service_key or "default").lower()
    if key in ("мрт", "mrt"):
        key = "mrt"
    elif key in ("узи", "uzi"):
        key = "uzi"
    elif key in ("эндо", "endo", "endocrin"):
        key = "endo"
    elif key in ("невро", "ped_neuro", "child"):
        key = "ped_neuro"
    return SERVICE_SCRIPTS.get(key) or SERVICE_SCRIPTS["default"]


def get_trainer() -> list[dict[str, Any]]:
    return OBJECTION_TRAINER


def export_control_excel(hours: int = 24) -> Path:
    """Export control pack as CSV (Excel-friendly) to Desktop reports."""
    pack = build_control_pack(hours=hours)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M")
    path = REPORTS_DIR / f"ROP_control_{ts}.csv"

    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["CRM AI Desk — Virtual ROP export", time.strftime("%Y-%m-%d %H:%M")])
        w.writerow([])
        w.writerow(["=== SUMMARY ==="])
        for k, v in (pack.get("summary") or {}).items():
            w.writerow([k, v])
        w.writerow([])
        w.writerow(["=== MANAGER RANKING ==="])
        w.writerow(
            [
                "manager",
                "control_index",
                "quality",
                "calls",
                "won",
                "lost",
                "conv%",
                "low_quality",
                "coaching",
            ]
        )
        for m in pack.get("ranking") or []:
            w.writerow(
                [
                    m.get("name"),
                    m.get("control_index"),
                    m.get("quality"),
                    m.get("calls"),
                    m.get("won"),
                    m.get("lost"),
                    m.get("conv"),
                    m.get("low_quality_count"),
                    m.get("coaching"),
                ]
            )
        w.writerow([])
        w.writerow(["=== ALERTS ==="])
        w.writerow(["severity", "type", "title", "manager", "lead_id", "detail", "advice"])
        for a in pack.get("alerts") or []:
            w.writerow(
                [
                    a.get("severity"),
                    a.get("type"),
                    a.get("title"),
                    a.get("manager"),
                    a.get("lead_id"),
                    a.get("detail"),
                    a.get("advice"),
                ]
            )
        w.writerow([])
        w.writerow(["=== QUEUE (stuck leads) ==="])
        w.writerow(["lead_id", "name", "manager", "idle_hours", "reasons", "url"])
        for q in pack.get("queue") or []:
            w.writerow(
                [
                    q.get("lead_id"),
                    q.get("name"),
                    q.get("manager"),
                    q.get("idle_hours"),
                    " | ".join(q.get("reasons") or []),
                    q.get("url"),
                ]
            )

    # also JSON for power users
    jpath = REPORTS_DIR / f"ROP_control_{ts}.json"
    jpath.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def score_text_endpoint(text: str) -> dict[str, Any]:
    sc = scorecard_evaluate(text)
    return {
        "ok": True,
        "scorecard": sc,
        "scripts_hint": sc.get("services") or ["default"],
    }
