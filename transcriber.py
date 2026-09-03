"""
Download call recordings and transcribe speech.

Clinic reality (Tashkent / KUH): mixed Uzbek + Russian on phone.
Whisper often mislabels UZ as Turkish/Farsi — we always multi-pass
UZ + RU and pick the best transcript by domain scoring.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from pathlib import Path
from typing import Any

import requests

from config import BASE_DIR, XAI_API_KEY, XAI_BASE_URL
from storage import db, init_db

logger = logging.getLogger(__name__)

AUDIO_DIR = BASE_DIR / "data" / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# Model: medium much better for UZ than small; override via env
STT_MODEL = os.getenv("STT_MODEL", "medium").strip() or "medium"
STT_DEVICE = os.getenv("STT_DEVICE", "cpu").strip() or "cpu"
STT_COMPUTE = os.getenv("STT_COMPUTE", "int8").strip() or "int8"
# Prefer UZ-specialized HF model as second opinion when available
STT_UZ_HF_MODEL = os.getenv(
    "STT_UZ_HF_MODEL", "OvozifyLabs/whisper-small-uz-v1"
).strip()
USE_UZ_HF = os.getenv("STT_USE_UZ_HF", "1").strip() not in ("0", "false", "no")

# Bias decoding toward clinic bilingual lexicon (Whisper initial_prompt)
INITIAL_PROMPT_UZ_RU = (
    "Kimyo University Hospital, klinika. "
    "Assalomu alaykum, zdravstvuyte. "
    "Qabul, yozilish, shifokor, narx, tahlil, MRT, UZI, KT. "
    "Запись, приём, врач, анализы, цена, завтра, soat. "
    "Rahmat, tushundim, kerak, bezovta qiladi."
)

KEYTERMS = [
    "МРТ", "УЗИ", "КТ", "клиника", "Kimyo", "Kimyo Hospital",
    "запись", "приём", "анализ", "врач", "эндокринолог", "терапия",
    "qabul", "shifokor", "klinika", "tahlil", "narx", "yozilish",
    "assalomu", "alaykum", "rahmat", "soat", "ertaga", "bugun",
    "og'riq", "ogriq", "bezovta", "kerak", "menejer",
]

# Markers that a transcript looks like real Uzbek (Latin)
_UZ_LATIN = (
    "assalom", "assalamu", "salom", "alaykum", "qabul", "shifokor", "klinika",
    "tahlil", "narx", "yozil", "yozib", "soat", "ertaga", "bugun", "rahmat",
    "kerak", "nima", "qanday", "qancha", "qachon", "bezovta", "og'riq", "ogriq",
    "tushun", "mayli", "ha ", " yo'q", "yoq ", "iltimos", "kuting",
    "menejer", "telefon", "ismingiz", "familiya", "pasport", "slot",
    "ertangi", "kunduzi", "ertalab", "kechqurun", "xizmat", "narxi",
    "qimmat", "arzon", "keling", "boring", "kutaman", "qo'ng'iroq",
    "qongiroq", "aloqa", "manzil", "manzilingiz", "bemor", "davolash",
    "tekshiruv", "yo'llanma", "yollanma", "homila", "qalqonsimon",
    "o'ylab", "oylab", "maslahat", "albatta", "bo'ladi", "boladi",
    "qilaman", "ayting", "aytish", "sog'liq", "soglik", "xush kelib",
    "navbat", "shikoyat", "kasallik", "dorixona", "analiz",
)

# Cyrillic Uzbek (sometimes still used)
_UZ_CYR = (
    "қабул", "шифокор", "клиника", "тахлил", "нарх", "ёзил", "соат",
    "эртага", "бугун", "рахмат", "керак", "нима", "қандай", "безовта",
    "тўғри", "йўқ", "илтимос", "кутинг", "қиммат", "арзон",
)

_RU_MARK = (
    "здравств", "добрый", "пожалуйст", "спасибо", "запись", "приём", "прием",
    "врач", "анализ", "сколько", "можно", "нужно", "хочу", "болит",
    "завтра", "сегодня", "время", "телефон", "клиник", "больниц",
    "перезвон", "понял", "поняла", "хорошо", "ладно", "минуту",
    "стоимость", "рубл", "сум ", "сумм",
)

# Bad auto-detect / garbage signals
_BAD_LANG = ("tr", "fa", "ar", "ur", "kk", "ky", "tk", "az", "hi", "zh", "ja", "ko")
_GARBAGE = (
    "subscribe", "thank you for watching", "www.", "http", "♪", "【",
    "music", "applause", "foreign", "字幕",
    "day and night we worked", "i don't know", "i do not know",
    "raised my uncle", "in brazil", "for his house",
    "i cannot do", "take care of manager",
)

# Pure IVR / hold (Kimyo PBX) — strip entirely from transcript body
_IVR_BLOCK = re.compile(
    r"(?is)"
    r"(assalomu\s+alaykum[^.!?\n]{0,120}kimyo[^.!?\n]{0,160})?"
    r"\.?\s*"
    r"здравствуйте[^.!?\n]{0,40}вы\s+позвонили\s+в\s+клинику[^.!?\n]{0,80}\.?"
    r"\s*пожалуйста,?\s*дождитесь\s+ответа\s+оператора\.?"
    r"|"
    r"вы\s+позвонили\s+в\s+клинику[^.!?\n]{0,100}\.?\s*"
    r"пожалуйста,?\s*дождитесь\s+ответа\s+оператора\.?"
    r"|"
    r"пожалуйста,?\s*оставайтесь\s+на\s+связи\.?"
    r"|"
    r"call\s+has\s+been\s+put\s+on\s+hold\.?"
    r"|"
    r"please\s+hold\s+on\s+the\s+line\.?"
)

# Whisper loop phrases often hallucinated on phone noise
_LOOP_PHRASES = (
    r"я\s+не\s+знаю",
    r"i\s+don'?t\s+know",
    r"как\s+вы\s+думаете",
    r"день\s+и\s+ночь\s+мы\s+работали",
    r"day\s+and\s+night\s+we\s+worked",
    r"я\s+не\s+могу\s+представить",
    r"алло\.?\s*алло",
    r"qizan",
    r"qeqom",
)


def _migrate() -> None:
    init_db()
    with db() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(communications)").fetchall()}
        alters = []
        if "recording_url" not in cols:
            alters.append("ALTER TABLE communications ADD COLUMN recording_url TEXT")
        if "transcript" not in cols:
            alters.append("ALTER TABLE communications ADD COLUMN transcript TEXT")
        if "transcript_status" not in cols:
            alters.append(
                "ALTER TABLE communications ADD COLUMN transcript_status TEXT DEFAULT ''"
            )
        if "transcribed_at" not in cols:
            alters.append("ALTER TABLE communications ADD COLUMN transcribed_at INTEGER")
        if "transcript_lang" not in cols:
            alters.append("ALTER TABLE communications ADD COLUMN transcript_lang TEXT")
        for sql in alters:
            conn.execute(sql)


def set_recording_url(comm_id: str, url: str | None) -> None:
    if not url:
        return
    _migrate()
    with db() as conn:
        conn.execute(
            "UPDATE communications SET recording_url = ? WHERE id = ?",
            (url, comm_id),
        )


def save_transcript(
    comm_id: str,
    text: str,
    status: str = "ok",
    lang: str | None = None,
) -> None:
    _migrate()
    with db() as conn:
        conn.execute(
            """
            UPDATE communications
            SET transcript = ?, transcript_status = ?, transcribed_at = ?,
                transcript_lang = COALESCE(?, transcript_lang),
                text = CASE
                    WHEN ? != '' AND (text IS NULL OR text LIKE '[%' OR LENGTH(TRIM(text)) < 40)
                    THEN ?
                    ELSE text
                END,
                analyzed = 0
            WHERE id = ?
            """,
            (text, status, int(time.time()), lang, text, text, comm_id),
        )


def calls_needing_transcript(
    limit: int = 20,
    min_duration: int = 12,
    *,
    force_retranscribe: bool = False,
) -> list[dict[str, Any]]:
    _migrate()
    with db() as conn:
        if force_retranscribe:
            rows = conn.execute(
                """
                SELECT * FROM communications
                WHERE kind = 'call'
                  AND recording_url IS NOT NULL
                  AND LENGTH(TRIM(recording_url)) > 8
                  AND COALESCE(duration, 0) >= ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (min_duration, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM communications
                WHERE kind = 'call'
                  AND recording_url IS NOT NULL
                  AND LENGTH(TRIM(recording_url)) > 8
                  AND COALESCE(duration, 0) >= ?
                  AND (
                        transcript IS NULL OR TRIM(transcript) = ''
                        OR transcript_status IN ('', 'pending', 'error', 'stt_failed', 'download_failed')
                        OR transcript_status LIKE 'ok:%' AND (
                            transcript_lang IN ('tr','fa','ar','ur','kk')
                            OR LENGTH(TRIM(COALESCE(transcript,''))) < 40
                        )
                      )
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (min_duration, limit),
            ).fetchall()
        return [dict(r) for r in rows]


def download_recording(url: str, comm_id: str) -> Path | None:
    """Download audio; returns local path or None."""
    if not url:
        return None
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    safe_id = re.sub(r"[^\w.-]+", "_", comm_id)[:40]
    path = AUDIO_DIR / f"{safe_id}_{digest}.mp3"
    if path.exists() and path.stat().st_size > 1000:
        return path
    try:
        r = requests.get(url, timeout=90, allow_redirects=True)
        if r.status_code != 200 or len(r.content) < 500:
            logger.warning(
                "Download failed %s status=%s size=%s",
                url[:80],
                r.status_code,
                len(r.content) if r.content else 0,
            )
            return None
        ctype = (r.headers.get("content-type") or "").lower()
        ext = ".mp3"
        if "wav" in ctype:
            ext = ".wav"
        elif "ogg" in ctype:
            ext = ".ogg"
        elif "mp4" in ctype or "m4a" in ctype:
            ext = ".m4a"
        path = AUDIO_DIR / f"{safe_id}_{digest}{ext}"
        path.write_bytes(r.content)
        logger.info("Saved recording %s (%s bytes)", path.name, len(r.content))
        return path
    except Exception as exc:
        logger.error("Download error %s: %s", url[:80], exc)
        return None


def score_transcript_quality(text: str) -> tuple[float, str]:
    """
    Score how much transcript looks like real UZ/RU clinic dialogue.
    Higher = better. Also returns guessed primary lang: uz|ru|mixed|junk.
    """
    raw = (text or "").strip()
    if not raw:
        return -100.0, "junk"
    t = raw.lower()
    score = 0.0

    # length sweet spot for phone calls
    n = len(raw)
    if n < 25:
        score -= 8
    elif n < 60:
        score -= 2
    elif n < 2000:
        score += min(6.0, n / 120.0)
    else:
        score += 6.0

    uz_hits = sum(1 for w in _UZ_LATIN if w in t) + sum(1 for w in _UZ_CYR if w in t)
    ru_hits = sum(1 for w in _RU_MARK if w in t)
    score += uz_hits * 2.2
    score += ru_hits * 1.6

    # Latin letters with Uzbek-looking digraphs
    if re.search(r"[oʻʼ''`]|g['ʻ]|o['ʻ]|sh|ch|ng", t):
        score += 1.5
    # lots of apostrophe forms common in UZ latin
    if t.count("'") + t.count("ʻ") + t.count("ʼ") >= 2:
        score += 1.0

    # Cyrillic share (RU or UZ cyr)
    cyr = len(re.findall(r"[а-яёўқғҳҳҳ]", t, flags=re.I))
    lat = len(re.findall(r"[a-z]", t, flags=re.I))
    if cyr > 20:
        score += 1.0
    if lat > 20 and uz_hits:
        score += 1.5

    # penalties
    for g in _GARBAGE:
        if g in t:
            score -= 12
    # chinese / arabic script often wrong decode
    if re.search(r"[\u0600-\u06FF\u4e00-\u9fff]", raw):
        score -= 10
    # pure turkish false friends without uz markers
    tr_only = ("merhaba", "teşekkür", "lütfen", "evet ", "hayır", "randevu")
    if any(x in t for x in tr_only) and uz_hits < 2:
        score -= 6

    # Phonetic Russian written in Latin (common when UZ pass forced on RU speech)
    phonetic_ru = (
        "zdravst", "zazdrav", "pazhal", "pozhal", "pazhaur", "dozhd", "dazhd",
        "kliniku", "zvonili", "pazwan", "operatora", "atvieta", "sus kimyo",
        "university hospital", "please wait", "your call",
    )
    phon_hits = sum(1 for p in phonetic_ru if p in t)
    if phon_hits >= 2 and cyr < 15:
        score -= 10 + phon_hits * 2  # almost certainly wrong UZ decode of RU

    # Good real Russian (Cyrillic dialogue)
    if cyr > 40 and ru_hits >= 2:
        score += 3.0
    if cyr > lat * 1.5 and lat > 10 and ru_hits >= 1:
        score += 2.0  # mostly cyrillic dialogue

    # repetition spam (whisper loop)
    words = t.split()
    if len(words) > 12:
        uniq = len(set(words))
        if uniq / max(len(words), 1) < 0.25:
            score -= 15
        elif uniq / max(len(words), 1) < 0.4:
            score -= 6
    # "я не знаю" x N is classic hallucination on phone noise
    if len(re.findall(r"я\s+не\s+знаю", t)) >= 3:
        score -= 12
    if len(re.findall(r"i\s+don'?t\s+know", t)) >= 2:
        score -= 12
    # IVR still present → not cleaned or pure hold
    if "дождитесь ответа" in t or "please hold" in t:
        score -= 8
    # long latin soup without clinic keywords
    if lat > cyr * 2 and lat > 80 and uz_hits < 2 and ru_hits < 2:
        score -= 10

    if uz_hits >= 3 and ru_hits >= 2:
        lang = "mixed"
    elif uz_hits > ru_hits and uz_hits >= 2 and phon_hits < 2:
        lang = "uz"
    elif ru_hits >= 2 or (cyr > 30 and phon_hits < 2):
        lang = "ru"
    elif uz_hits >= 1 and phon_hits < 2:
        lang = "uz"
    elif score < 0:
        lang = "junk"
    else:
        lang = "ru" if cyr >= lat else "uz"

    return score, lang


def _collapse_repetitions(text: str) -> str:
    """Remove Whisper hallucination loops (same phrase / n-gram many times)."""
    if not text:
        return text
    t = text

    # Phrase-level loops without punctuation: "Я не знаю Я не знаю …"
    for pat in _LOOP_PHRASES:
        t = re.sub(
            rf"(?i)(({pat})[\s,.\-]*){{3,}}",
            lambda m: re.search(pat, m.group(0), re.I).group(0) + " ",
            t,
        )

    # Same token 4+ times in a row
    t = re.sub(r"\b(\S+)(?:\s+\1){3,}\b", r"\1", t, flags=re.I)

    # sentence-ish split
    parts = re.split(r"(?<=[\.\!\?\n])\s+", t)
    out: list[str] = []
    prev = None
    streak = 0
    for p in parts:
        key = re.sub(r"\s+", " ", p.strip().lower())
        key = re.sub(r"[^\w\sа-яёўқғҳ]", "", key, flags=re.I)
        if not key:
            continue
        if key == prev:
            streak += 1
            if streak >= 1:  # keep only first copy of identical sentence
                continue
        else:
            streak = 0
            prev = key
        # drop pure nonsense short english hallucinations mid-ru
        if re.fullmatch(r"[a-z\s',.\-]{8,80}", p.strip()) and not re.search(
            r"(?i)(kimyo|hospital|mri|uzi|doctor|clinic|hello|yes|no|ok)",
            p,
        ):
            continue
        out.append(p.strip())

    cleaned = " ".join(x for x in out if x)

    # n-gram spam remaining
    words = cleaned.split()
    if len(words) > 24:
        for n in (10, 8, 6, 4, 3):
            if len(words) < n * 4:
                continue
            for i in range(0, min(40, len(words) - n)):
                chunk = " ".join(words[i : i + n])
                if len(chunk) < 12:
                    continue
                cnt = cleaned.lower().count(chunk.lower())
                if cnt >= 3:
                    # keep one occurrence
                    cleaned = re.sub(
                        re.escape(chunk) + r"(?:\s*" + re.escape(chunk) + r")+",
                        chunk,
                        cleaned,
                        flags=re.I,
                    )
                    break
    return cleaned or text


def _strip_ivr_boilerplate(text: str) -> str:
    """Remove clinic IVR / hold — it pollutes every Kimyo call transcript."""
    if not text:
        return text
    t = text
    # Full IVR blocks (all copies)
    t = _IVR_BLOCK.sub(" ", t)
    t = re.sub(
        r"(?i)(call has been put on hold\.?\s*|please hold on the line\.?\s*)+",
        " ",
        t,
    )
    t = re.sub(
        r"(?i)(please wait( while)? (your call is|we) (being )?(transfer|connect).{0,60})",
        " ",
        t,
    )
    # Garbled STT of same IVR (latin soup + kimyo + operator)
    t = re.sub(
        r"(?i)assalomu\s+alaykum[^.!?\n]{0,40}kimyo[^.!?\n]{0,120}"
        r"(operator|оператор|javap|jawab|kutiy|кути|imtimon|iltimon|eltimon)"
        r"[^.!?\n]{0,100}(zdravstvuyte|здравствуйте)?\.?",
        " ",
        t,
    )
    # "Assalomu… Kimyo … operator …" without punctuation (one long run)
    t = re.sub(
        r"(?i)assalomu\s+alaykum[, ]+siz\s+kimyo\s+university\s+hospital[, ].{0,80}?"
        r"(оператор|operator).{0,40}?(zdravstvuyte|здравствуйте)",
        " ",
        t,
    )
    t = re.sub(
        r"(?i)здравствуйте[^.!?\n]{0,30}вы\s+позвонили[^.!?\n]{0,100}"
        r"дождитесь[^.!?\n]{0,40}оператора\.?",
        " ",
        t,
    )
    # leftover single IVR lines
    for pat in (
        r"вы позвонили в клинику[^.!?\n]{0,100}[\.!]?",
        r"пожалуйста,? дождитесь ответа оператора[\.!]?",
        r"пожалуйста,? оставайтесь на связи[\.!]?",
        r"ваш вызов в режиме ожидания[\.!]?",
    ):
        t = re.sub(rf"(?i){pat}", " ", t)

    t = re.sub(r"\s{2,}", " ", t).strip()
    # Pure hold-only
    if len(t) < 80 and not re.search(
        r"(?i)(запис|мрт|узи|врач|цен|qabul|mrt|uzi|shifokor|лет|yosh|направлен)",
        t,
    ):
        return t
    return t


def _drop_low_value_clauses(text: str) -> str:
    """Drop clauses that are almost certainly Whisper noise on this PBX."""
    if not text:
        return text
    # Split on . ! ? and also long commas for phone speech
    parts = re.split(r"(?<=[\.\!\?])\s+|(?<=,)\s+(?=[А-ЯA-Z«\"])", text)
    keep: list[str] = []
    clinic = re.compile(
        r"(?i)(kimyo|клиник|мрт|узи|кт|анализ|врач|запис|локац|адрес|цен|"
        r"qabul|shifokor|narx|soat|yozil|assalom|здравству|алло|"
        r"лет|yosh|месяц|oy|направлен|whatsapp|телеграм|да\b|нет\b|"
        r"сколько|qancha|завтра|ertaga|сегодня)",
    )
    for p in parts:
        p = p.strip(" ,")
        if len(p) < 3:
            continue
        pl = p.lower()
        # pure garbage / whisper hallucinations (EN + RU loops)
        if re.search(
            r"(?i)(day and night|i don't know|i cannot|uncle's house|brazil|"
            r"for his house|take care of manager|raised my|"
            r"день и ночь мы работали|я не могу представить|"
            r"это 300 месяц|тридцать месяц.*как вы думаете)",
            pl,
        ):
            continue
        if re.fullmatch(r"(?i)\s*(как вы думаете[?\s.]*)+", p):
            continue
        # high latin soup with almost no clinic terms and no real UZ words
        lat = len(re.findall(r"[a-z]", pl))
        cyr = len(re.findall(r"[а-яё]", pl))
        if lat > 25 and cyr < 5 and not clinic.search(p):
            # keep if has clear uz markers
            if not re.search(r"(?i)(qabul|shifokor|assalom|rahmat|kerak|qanday|nima)", pl):
                continue
        # repeated "я не знаю" only
        if re.fullmatch(r"(?i)(\s*я\s+не\s+знаю[.\s,]*)+", p):
            continue
        keep.append(p)
    if not keep:
        return text.strip()
    # rejoin softly
    out = []
    for p in keep:
        if out and not out[-1].endswith((".", "!", "?", "…")):
            out.append(p if p[:1].islower() or p[:1].isdigit() else p)
        else:
            out.append(p)
    return " ".join(keep)


def normalize_uz_text(text: str) -> str:
    """Cleanup STT artifacts for UZ/RU clinic phone audio."""
    if not text:
        return text
    t = text
    # unify apostrophes used in Uzbek latin
    t = t.replace("`", "'").replace("ʼ", "'").replace("ʻ", "'").replace("'", "'")
    # collapse spaces
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = _strip_ivr_boilerplate(t)
    t = _collapse_repetitions(t)
    t = _drop_low_value_clauses(t)
    t = _collapse_repetitions(t)  # second pass after drops
    # common whisper mishears → clinic terms
    replacements = (
        (r"\bMRI\b", "МРТ"),
        (r"\bMRT\b", "МРТ"),
        (r"\bUZI\b", "УЗИ"),
        (r"\bУЗИ\b", "УЗИ"),
        (r"(?i)\bКТ\b", "КТ"),
        # Kimyo University Hospital (Whisper often phonetics)
        (r"(?i)ким+ье\s+уинверсити\s+хоспитал", "Kimyo University Hospital"),
        (r"(?i)ким+ь[её]\s+университи\s+хоспитал", "Kimyo University Hospital"),
        (r"(?i)kimyo\s+university\s+hospital", "Kimyo University Hospital"),
        (r"(?i)\bким+ье\b", "Kimyo"),
        (r"(?i)\bkimyo\b", "Kimyo"),
        (r"(?i)\buniversity hospital\b", "University Hospital"),
        (r"(?i)ассалом\s*алейкум", "Assalomu alaykum"),
        (r"(?i)ассаламу\s*алейкум", "Assalomu alaykum"),
        (r"(?i)\bassalamu\s+alaykum\b", "Assalomu alaykum"),
        (r"(?i)\bassalomu\s+alaykum\b", "Assalomu alaykum"),
        # colloquial RU STT typos
        (r"(?i)\bско+ко\b", "сколько"),
        (r"(?i)\bщ[ао]с\b", "сейчас"),
        (r"(?i)\bщас\b", "сейчас"),
        (r"(?i)\bчё\b", "что"),
        (r"(?i)\bналич\b", "наличку"),
        (r"(?i)\bтелеграм+а?\b", "Telegram"),
        (r"(?i)\bвотсап\b", "WhatsApp"),
        (r"(?i)\bвацап\b", "WhatsApp"),
        (r"(?i)\bкиньте\b", "скиньте"),
        # Tashkent / clinic place & product mishears
        (r"(?i)челандзарск", "Чиланзарск"),
        (r"(?i)чиланзарск", "Чиланзарск"),
        (r"(?i)алназарск", "Алмазарск"),
        (r"(?i)алмазарск", "Алмазарск"),
        (r"(?i)сабрахимск\w*\s+мост", "Сабир-Рахимовский мост"),
        (r"(?i)саберахимов\w*\s+мост", "Сабир-Рахимовский мост"),
        (r"(?i)мост\s+аберрахимов", "мост Сабир Рахимова"),
        (r"(?i)аберрахимов", "Сабир Рахимова"),
        (r"(?i)через\s+100\s*грамм", "через WhatsApp"),
        (r"(?i)автономить", "номер набрать"),
        (r"(?i)мы\s+на\s+спаме", "мы в спаме"),
        (r"(?i)у\s+нас\s+спам", "у нас спам"),
        (r"(?i)кимио[-\s]?юнверсити[-\s]?хоспитал", "Kimyo University Hospital"),
        (r"(?i)кимио", "Kimyo"),
        (r"(?i)корпросспект", "Карасувский проспект"),
        (r"(?i)галхар", "Гульхани"),
        (r"(?i)\bsus\s+Kimyo\b", "Kimyo"),
        (r"(?i)\b(yehomborok|kaliyev|intimoz|java\s*panukti)\b[,.]?\s*", ""),
    )
    for pat, rep in replacements:
        t = re.sub(pat, rep, t)
    # known garbage phrases from this clinic's IVR / hold mishears
    garbage_phrases = (
        r"гехом\s+вороффа?\s+линьи",
        r"издемон,?\s*",
        r"джава\s+пана\s+кутей",
        r"оператор\s+джава[^.!,]{0,40}",
        r"все\s+с\s+ким+ье[^.!,]{0,40}",
        r"yehomborok,?\s*kaliyev\.?",
        r"intimoz,?\s*",
        r"java\s*panukti",
    )
    for g in garbage_phrases:
        t = re.sub(g, " ", t, flags=re.I)
    t = re.sub(r"\s{2,}", " ", t)
    t = re.sub(r"\s+([,.!?])", r"\1", t)
    return t.strip()


def transcribe_xai(path: Path, language: str | None = None) -> str | None:
    """xAI STT if key present; language=None → auto."""
    if not XAI_API_KEY:
        return None
    try:
        data = [
            ("format", "true"),
            ("diarize", "true"),
            ("filler_words", "false"),
        ]
        if language:
            data.append(("language", language))
        for kt in KEYTERMS:
            data.append(("keyterm", kt))
        with path.open("rb") as f:
            files = {"file": (path.name, f, "audio/mpeg")}
            resp = requests.post(
                f"{XAI_BASE_URL.rstrip('/')}/stt",
                headers={"Authorization": f"Bearer {XAI_API_KEY}"},
                data=data,
                files=files,
                timeout=300,
            )
        if resp.status_code >= 400 and language is not None:
            # retry auto
            with path.open("rb") as f:
                files = {"file": (path.name, f, "audio/mpeg")}
                resp = requests.post(
                    f"{XAI_BASE_URL.rstrip('/')}/stt",
                    headers={"Authorization": f"Bearer {XAI_API_KEY}"},
                    data=[("diarize", "true"), ("format", "true")],
                    files=files,
                    timeout=300,
                )
        if resp.status_code >= 400:
            logger.error("xAI STT %s: %s", resp.status_code, resp.text[:300])
            return None
        payload = resp.json()
        text = (payload.get("text") or "").strip()
        words = payload.get("words") or []
        if words and any("speaker" in w for w in words):
            chunks: list[str] = []
            cur_spk = None
            buf: list[str] = []
            for w in words:
                spk = w.get("speaker")
                tok = w.get("text") or ""
                if spk != cur_spk and buf:
                    label = "Менеджер" if cur_spk in (0, "0") else f"Спикер{cur_spk}"
                    if cur_spk in (1, "1"):
                        label = "Клиент"
                    chunks.append(f"{label}: {' '.join(buf)}")
                    buf = []
                cur_spk = spk
                if tok:
                    buf.append(tok)
            if buf:
                label = "Менеджер" if cur_spk in (0, "0") else (
                    "Клиент" if cur_spk in (1, "1") else f"Спикер{cur_spk}"
                )
                chunks.append(f"{label}: {' '.join(buf)}")
            if chunks:
                text = "\n".join(chunks)
        return text or None
    except Exception as exc:
        logger.error("xAI STT failed: %s", exc)
        return None


_whisper_model = None
_whisper_model_name: str | None = None
_uz_hf_pipe = None
_uz_hf_failed = False


def _get_whisper():
    global _whisper_model, _whisper_model_name
    from faster_whisper import WhisperModel

    name = STT_MODEL
    if _whisper_model is None or _whisper_model_name != name:
        logger.info(
            "Loading faster-whisper model=%s device=%s compute=%s",
            name,
            STT_DEVICE,
            STT_COMPUTE,
        )
        try:
            _whisper_model = WhisperModel(
                name, device=STT_DEVICE, compute_type=STT_COMPUTE
            )
        except Exception as e:
            logger.warning("Failed model %s (%s), fallback to small", name, e)
            _whisper_model = WhisperModel(
                "small", device=STT_DEVICE, compute_type=STT_COMPUTE
            )
            name = "small"
        _whisper_model_name = name
        logger.info("Loaded faster-whisper %s", name)
    return _whisper_model


def _fw_transcribe(
    path: Path,
    language: str | None,
    *,
    beam_size: int = 5,
    initial_prompt: str | None = INITIAL_PROMPT_UZ_RU,
) -> tuple[str, Any]:
    model = _get_whisper()
    kwargs: dict[str, Any] = {
        "beam_size": beam_size,
        "vad_filter": True,
        "vad_parameters": dict(
            min_silence_duration_ms=450,
            speech_pad_ms=180,
            # skip long IVR hold / ring as "silence-ish"
            threshold=0.5,
        ),
        "language": language,
        "condition_on_previous_text": False,  # reduces loops on phone noise
        "word_timestamps": False,
        # temperature fallback if first pass compresses/hallucinates
        "temperature": [0.0, 0.2, 0.4],
        "compression_ratio_threshold": 2.0,  # stricter — kill loops
        "log_prob_threshold": -0.9,
        "no_speech_threshold": 0.55,
        "repetition_penalty": 1.15,
    }
    if initial_prompt:
        kwargs["initial_prompt"] = initial_prompt
    try:
        segs, info = model.transcribe(str(path), **kwargs)
    except TypeError:
        # older faster-whisper without repetition_penalty / list temperature
        kwargs.pop("repetition_penalty", None)
        kwargs["temperature"] = 0.0
        segs, info = model.transcribe(str(path), **kwargs)

    parts: list[str] = []
    for seg in segs:
        t = (seg.text or "").strip()
        if not t:
            continue
        nsp = float(getattr(seg, "no_speech_prob", 0) or 0)
        alp = float(getattr(seg, "avg_logprob", 0) or 0)
        # skip likely non-speech / hold music decode
        if nsp > 0.65 and len(t) < 80:
            continue
        if alp < -1.15 and len(t) < 40:
            continue
        # skip segment-level loops
        words = t.lower().split()
        if len(words) >= 6:
            uniq = len(set(words))
            if uniq / len(words) < 0.3:
                continue
        if re.search(
            r"(?i)(day and night we worked|i don't know|i do not know|"
            r"thank you for watching|subscribe)",
            t,
        ):
            continue
        if re.search(r"(?i)дождитесь ответа оператора|please hold on the line", t):
            continue
        parts.append(t)

    text = normalize_uz_text(" ".join(parts))
    return text, info


def _merge_best(candidates: list[tuple[str, str, Any]]) -> tuple[str, str, float, Any]:
    """
    candidates: (text, pass_name, info)
    returns best_text, lang_guess, score, info
    """
    best = ("", "junk", -999.0, None)
    for text, pass_name, info in candidates:
        if not text or len(text.strip()) < 8:
            continue
        sc, lang = score_transcript_quality(text)
        # slight bias: if pass was forced uz and looks uz — boost
        if pass_name == "uz" and lang in ("uz", "mixed"):
            sc += 1.5
        if pass_name == "ru" and lang in ("ru", "mixed"):
            sc += 1.0
        if pass_name == "uz_hf" and lang in ("uz", "mixed"):
            sc += 2.0
        logger.info(
            "STT candidate pass=%s score=%.1f lang=%s len=%s preview=%s",
            pass_name,
            sc,
            lang,
            len(text),
            text[:80].replace("\n", " "),
        )
        if sc > best[2]:
            best = (text, lang, sc, info)
    return best  # type: ignore[return-value]


def transcribe_uz_hf(path: Path) -> str | None:
    """Optional fine-tuned Uzbek Whisper (transformers)."""
    global _uz_hf_pipe, _uz_hf_failed
    if not USE_UZ_HF or _uz_hf_failed or not STT_UZ_HF_MODEL:
        return None
    try:
        if _uz_hf_pipe is None:
            import torch
            from transformers import pipeline

            device = 0 if torch.cuda.is_available() else -1
            logger.info("Loading UZ HF model %s device=%s", STT_UZ_HF_MODEL, device)
            _uz_hf_pipe = pipeline(
                "automatic-speech-recognition",
                model=STT_UZ_HF_MODEL,
                device=device,
                chunk_length_s=30,
                stride_length_s=5,
            )
        result = _uz_hf_pipe(
            str(path),
            generate_kwargs={
                "task": "transcribe",
                # don't force language — model is UZ/RU/EN
            },
            return_timestamps=False,
        )
        if isinstance(result, dict):
            text = (result.get("text") or "").strip()
        else:
            text = str(result or "").strip()
        return normalize_uz_text(text) or None
    except Exception as exc:
        logger.warning("UZ HF STT unavailable: %s", exc)
        _uz_hf_failed = True
        return None


def transcribe_local(path: Path) -> tuple[str | None, str | None]:
    """
    Multi-pass local STT optimized for UZ↔RU call-center audio.
    Returns (text, lang_guess).
    """
    try:
        from faster_whisper import WhisperModel  # noqa: F401
    except ImportError:
        logger.warning("faster-whisper not installed")
        return None, None

    candidates: list[tuple[str, str, Any]] = []
    try:
        # 1) auto detect
        text_auto, info_auto = _fw_transcribe(path, None)
        lang_auto = getattr(info_auto, "language", None)
        prob_auto = float(getattr(info_auto, "language_probability", 0) or 0)
        if text_auto:
            candidates.append((text_auto, f"auto:{lang_auto}", info_auto))
        logger.info(
            "STT auto lang=%s p=%.2f len=%s",
            lang_auto,
            prob_auto,
            len(text_auto or ""),
        )

        # 2) Always force RU — IVR/managers often Russian (Cyrillic quality)
        text_ru, info_ru = _fw_transcribe(path, "ru", beam_size=5)
        if text_ru:
            candidates.append((text_ru, "ru", info_ru))

        # 3) Force UZ when:
        #    - auto says uz / tr / kk / ky (turkic confusions)
        #    - auto low confidence
        #    - RU pass looks weak / short
        need_uz = (
            lang_auto in ("uz", "tr", "kk", "ky", "tk", "az", "fa", "ar")
            or prob_auto < 0.72
            or len(text_ru or "") < 80
            or score_transcript_quality(text_ru or "")[0] < 3
        )
        if need_uz:
            text_uz, info_uz = _fw_transcribe(path, "uz", beam_size=5)
            if text_uz:
                candidates.append((text_uz, "uz", info_uz))

        # 4) Fine-tuned UZ model when RU weak or UZ likely
        if need_uz or (lang_auto == "uz"):
            text_hf = transcribe_uz_hf(path)
            if text_hf:
                candidates.append((text_hf, "uz_hf", None))

        best_text, best_lang, best_score, _ = _merge_best(candidates)
        if not best_text:
            return None, None

        def _cyr_ratio(s: str) -> float:
            if not s:
                return 0.0
            cyr = len(re.findall(r"[а-яёА-ЯЁ]", s))
            lat = len(re.findall(r"[a-zA-Z]", s))
            return cyr / max(cyr + lat, 1)

        # Prefer strongest Cyrillic RU candidate when speech is mostly Russian
        ru_cands = [
            (t, n, i)
            for t, n, i in candidates
            if t
            and (
                n == "ru"
                or n.startswith("auto:ru")
                or _cyr_ratio(t) > 0.55
            )
        ]
        if ru_cands and (
            best_score < 4.0
            or _cyr_ratio(best_text) < 0.45
            or best_lang in ("junk", "uz")
        ):
            alt = max(
                ru_cands,
                key=lambda x: (
                    score_transcript_quality(x[0])[0],
                    _cyr_ratio(x[0]),
                    len(x[0] or ""),
                ),
            )
            sc_alt, lg_alt = score_transcript_quality(alt[0])
            # Prefer longer clean RU if scores close
            if sc_alt + 0.5 >= best_score or _cyr_ratio(alt[0]) > _cyr_ratio(
                best_text
            ) + 0.2:
                if len(alt[0]) >= max(40, int(len(best_text) * 0.6)):
                    best_text, best_lang, best_score = alt[0], lg_alt or "ru", sc_alt

        best_text = normalize_uz_text(best_text)

        logger.info(
            "Local STT winner lang=%s score=%.1f len=%s model=%s",
            best_lang,
            best_score,
            len(best_text),
            _whisper_model_name,
        )
        return best_text, best_lang
    except Exception as exc:
        logger.error("Local STT failed: %s", exc)
        return None, None


def transcribe_file(path: Path) -> tuple[str | None, str, str | None]:
    """Returns (text, backend_name, lang)."""
    # Try xAI auto then uz if weak
    if XAI_API_KEY:
        texts = []
        for lang in (None, "uz", "ru"):
            t = transcribe_xai(path, language=lang)
            if t:
                texts.append((t, f"xai:{lang or 'auto'}"))
        if texts:
            scored = []
            for t, name in texts:
                sc, lg = score_transcript_quality(t)
                scored.append((sc, t, lg, name))
            scored.sort(key=lambda x: x[0], reverse=True)
            sc, t, lg, name = scored[0]
            if sc > 0:
                return t, name, lg

    text, lang = transcribe_local(path)
    if text:
        return text, f"faster-whisper:{_whisper_model_name or STT_MODEL}", lang
    return None, "none", None


def process_call(comm: dict[str, Any], *, force: bool = False) -> dict[str, Any]:
    cid = comm["id"]
    url = comm.get("recording_url") or ""
    path = download_recording(url, cid)
    if not path:
        save_transcript(cid, "", status="download_failed")
        return {"id": cid, "ok": False, "reason": "download_failed"}
    text, backend, lang = transcribe_file(path)
    if not text:
        save_transcript(cid, "", status="stt_failed")
        return {"id": cid, "ok": False, "reason": "stt_failed", "backend": backend}
    text = normalize_uz_text(text)
    sc, lang2 = score_transcript_quality(text)
    lang_final = lang or lang2

    # Second cleanup pass if still junk-ish
    if sc < 2.0 or len(re.findall(r"я\s+не\s+знаю", text.lower())) >= 2:
        text2 = normalize_uz_text(text)
        sc2, lang3 = score_transcript_quality(text2)
        if sc2 >= sc:
            text, sc, lang_final = text2, sc2, lang3 or lang_final

    # Mark low quality but still save cleaned text (better than raw hallucination)
    if sc < -2 or len(text.strip()) < 15:
        save_transcript(cid, text, status=f"low_quality:{backend}", lang=lang_final)
        return {
            "id": cid,
            "ok": False,
            "reason": "low_quality",
            "backend": backend,
            "score": round(sc, 1),
            "chars": len(text),
            "preview": text[:200],
        }

    status = f"ok:{backend}:{lang_final}"
    if sc < 3.0:
        status = f"ok_weak:{backend}:{lang_final}"
    save_transcript(cid, text, status=status, lang=lang_final)
    return {
        "id": cid,
        "ok": True,
        "backend": backend,
        "lang": lang_final,
        "score": round(sc, 1),
        "chars": len(text),
        "preview": text[:200],
    }


def retranscribe_one(comm_id: str) -> dict[str, Any]:
    """Force re-STT a single communication by id (or note:leads: variant)."""
    _migrate()
    from urllib.parse import unquote

    cid = unquote(str(comm_id or "").strip())
    if not cid:
        return {"ok": False, "reason": "empty_id"}

    def _load(conn, key: str):
        return conn.execute(
            "SELECT * FROM communications WHERE id = ?", (key,)
        ).fetchone()

    with db() as conn:
        row = _load(conn, cid)
        if not row and cid.isdigit():
            for cand in (f"note:leads:{cid}", f"note:{cid}", f"call:{cid}"):
                row = _load(conn, cand)
                if row:
                    break
        if not row and ":" not in cid and re.fullmatch(r"\d{4,}", cid or ""):
            row = conn.execute(
                """
                SELECT * FROM communications
                WHERE id LIKE ? AND recording_url IS NOT NULL AND recording_url != ''
                ORDER BY created_at DESC LIMIT 1
                """,
                (f"%:{cid}",),
            ).fetchone()
        if not row:
            return {"ok": False, "reason": "not_found", "id": cid}
        comm = dict(row)

    # Keep previous transcript until new one succeeds (never blank the UI mid-run)
    res = process_call(comm, force=True)
    res["ok"] = bool(res.get("ok"))
    return res


def transcribe_batch(
    limit: int = 10,
    min_duration: int = 15,
    *,
    force_retranscribe: bool = False,
) -> dict[str, Any]:
    _migrate()
    items = calls_needing_transcript(
        limit=limit,
        min_duration=min_duration,
        force_retranscribe=force_retranscribe,
    )
    stats: dict[str, Any] = {
        "queued": len(items),
        "ok": 0,
        "fail": 0,
        "details": [],
        "model": STT_MODEL,
    }
    for comm in items:
        try:
            res = process_call(comm, force=force_retranscribe)
            if res.get("ok"):
                stats["ok"] += 1
            else:
                stats["fail"] += 1
            stats["details"].append(res)
        except Exception as exc:
            stats["fail"] += 1
            logger.exception("transcribe %s", comm.get("id"))
            stats["details"].append(
                {"id": comm.get("id"), "ok": False, "error": str(exc)}
            )
    logger.info(
        "Transcribe batch: %s",
        {k: stats[k] for k in ("queued", "ok", "fail", "model")},
    )
    return stats
