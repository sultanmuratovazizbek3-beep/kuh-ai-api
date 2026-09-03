"""Generate day / week / month reports by managers."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from config import REPORTS_DIR, TIMEZONE, XAI_API_KEY, XAI_BASE_URL, XAI_MODEL
from storage import period_stats, save_report

logger = logging.getLogger(__name__)


def _tz() -> ZoneInfo:
    try:
        return ZoneInfo(TIMEZONE)
    except Exception:
        return ZoneInfo("UTC")


def _period_bounds(period: str, ref: datetime | None = None) -> tuple[int, int, str]:
    """Return (start_ts, end_ts, human_label) for day|week|month."""
    tz = _tz()
    now = ref or datetime.now(tz)
    if period == "day":
        # previous full day if before report hour intent; use "today so far" when forced
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        # for scheduled evening report — report current day; for morning — yesterday
        if now.hour < 6:
            start = start - timedelta(days=1)
        end = start + timedelta(days=1)
        label = start.strftime("%d.%m.%Y")
    elif period == "week":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start = start - timedelta(days=start.weekday())  # Monday
        # completed week: if Mon morning, take previous week
        if now.weekday() == 0 and now.hour < 12:
            start = start - timedelta(days=7)
        end = start + timedelta(days=7)
        label = f"{start.strftime('%d.%m')}–{(end - timedelta(days=1)).strftime('%d.%m.%Y')}"
    elif period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if now.day <= 2 and now.hour < 12:
            # first days of month → previous month
            start = (start - timedelta(days=1)).replace(day=1)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
        label = start.strftime("%m.%Y")
    else:
        raise ValueError(f"Unknown period: {period}")
    return int(start.timestamp()), int(end.timestamp()), label


def _conv_rate(won: int, lost: int) -> str:
    total = won + lost
    if total <= 0:
        return "—"
    return f"{100.0 * won / total:.0f}%"


def _format_money(v: float) -> str:
    if v >= 1_000_000:
        return f"{v/1_000_000:.1f}M"
    if v >= 1_000:
        return f"{v/1_000:.0f}K"
    return f"{v:.0f}"


def _ai_team_advice(stats: dict[str, Any], period_label: str) -> str:
    if not XAI_API_KEY:
        return _fallback_team_advice(stats)

    managers_brief = []
    for m in stats["managers"][:15]:
        managers_brief.append(
            {
                "name": m["name"],
                "calls": m["calls_total"],
                "chats": m["chats_total"],
                "worked": m["leads_worked"],
                "won": m["leads_won"],
                "lost": m["leads_lost"],
                "quality": m["avg_quality_score"],
                "weak": [w.get("weaknesses") for w in m.get("weak_points", [])[:2]],
            }
        )
    try:
        from openai import OpenAI
        import json

        client = OpenAI(api_key=XAI_API_KEY, base_url=XAI_BASE_URL)
        prompt = (
            f"Период: {period_label}. Итоги отдела продаж клиники (JSON):\n"
            f"{json.dumps({'totals': stats['totals'], 'managers': managers_brief}, ensure_ascii=False)}\n\n"
            "Напиши по-русски короткий блок для руководителя:\n"
            "1) Главный вывод (2-3 предложения)\n"
            "2) Топ-3 проблемы\n"
            "3) Топ-3 действия на следующий период\n"
            "4) Кому персональный коучинг и почему\n"
            "Без воды, конкретно, markdown."
        )
        try:
            resp = client.responses.create(
                model=XAI_MODEL,
                input=prompt,
            )
            text = getattr(resp, "output_text", None) or ""
        except Exception:
            chat = client.chat.completions.create(
                model=XAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.4,
            )
            text = chat.choices[0].message.content or ""
        return text.strip() or _fallback_team_advice(stats)
    except Exception as exc:
        logger.warning("Team AI advice failed: %s", exc)
        return _fallback_team_advice(stats)


def _fallback_team_advice(stats: dict[str, Any]) -> str:
    totals = stats["totals"]
    managers = stats["managers"]
    lines = ["### Выводы и советы (авто)\n"]

    if not managers:
        lines.append("За период нет данных по менеджерам. Проверьте доступ API и период.")
        return "\n".join(lines)

    best = max(managers, key=lambda m: (m["leads_won"], m["calls_total"]))
    worst_q = [
        m
        for m in managers
        if m.get("avg_quality_score") is not None and m["analyses_count"] > 0
    ]
    if worst_q:
        low = min(worst_q, key=lambda m: m["avg_quality_score"] or 0)
        lines.append(
            f"- Лидер по закрытиям: **{best['name']}** "
            f"({best['leads_won']} won, {best['calls_total']} звонков)."
        )
        lines.append(
            f"- Низкое качество коммуникаций: **{low['name']}** "
            f"(score {low['avg_quality_score']}/10) — нужен разбор звонков."
        )

    if totals["leads_won"] == 0 and totals["leads_worked"] > 0:
        lines.append(
            "- **0 успешных закрытий** при активной работе — проверить этапы воронки, "
            "WON_STATUS_IDS и причины отказа."
        )

    no_next = sum(
        1
        for m in managers
        for w in m.get("weak_points", [])
        if "next" in (w.get("weaknesses") or "").lower()
        or "шаг" in (w.get("weaknesses") or "").lower()
    )
    if no_next:
        lines.append(
            "- Часто нет next step: внедрить обязательную задачу/запись после каждого контакта."
        )

    lines.append(
        "- На планёрке: 2 лучших и 2 худших звонка, чек-лист «приветствие → потребность → оффер → запись»."
    )
    lines.append(
        "- Контроль SLA ответа в чатах и доля исходящих follow-up звонков."
    )
    return "\n".join(lines)


def build_markdown(period: str, stats: dict[str, Any], label: str) -> str:
    titles = {
        "day": "Дневной / Kunlik",
        "week": "Недельный / Haftalik",
        "month": "Месячный / Oylik",
    }
    title = f"{titles.get(period, period)} отчёт по менеджерам / menejerlar hisoboti — {label}"
    totals = stats["totals"]
    managers = stats["managers"]

    lines = [
        f"# {title}",
        "",
        f"_Сформировано / Yaratildi: {datetime.now(_tz()).strftime('%d.%m.%Y %H:%M')} ({TIMEZONE})_",
        "",
        "## Сводка отдела / Bo'lim xulosasi",
        "",
        f"| Метрика / Metrika | Значение / Qiymat |",
        f"|---------|----------|",
        f"| Звонки / Qo'ng'iroqlar | {totals['calls']} |",
        f"| Сообщения/чаты / Xabarlar | {totals['chats']} |",
        f"| Лиды в работе / Ishlangan lidlar | {totals['leads_worked']} |",
        f"| Новые лиды / Yangi | {totals['leads_created']} |",
        f"| Успешно / Muvaffaqiyatli | {totals['leads_won']} |",
        f"| Отказы / Rad | {totals['leads_lost']} |",
        f"| Конверсия / Konversiya | {_conv_rate(totals['leads_won'], totals['leads_lost'])} |",
        f"| Сумма успешных / Summa | {_format_money(totals['won_sum'])} |",
        "",
        "## По менеджерам / Menejerlar bo'yicha",
        "",
        "| Менеджер | Звонки (in/out) | Чаты | Лиды | Won | Lost | Conv | Quality |",
        "|----------|-----------------|------|------|-----|------|------|---------|",
    ]

    for m in managers:
        if (
            m["calls_total"]
            + m["chats_total"]
            + m["leads_worked"]
            + m["leads_created"]
            == 0
        ):
            continue
        q = (
            f"{m['avg_quality_score']}/10"
            if m["avg_quality_score"] is not None
            else "—"
        )
        lines.append(
            f"| {m['name']} "
            f"| {m['calls_total']} ({m['calls_in']}/{m['calls_out']}) "
            f"| {m['chats_total']} "
            f"| {m['leads_worked']} "
            f"| {m['leads_won']} "
            f"| {m['leads_lost']} "
            f"| {_conv_rate(m['leads_won'], m['leads_lost'])} "
            f"| {q} |"
        )

    lines += ["", "## Персональные замечания / Shaxsiy izohlar", ""]
    for m in managers:
        if not m.get("weak_points"):
            continue
        lines.append(f"### {m['name']}")
        for w in m["weak_points"][:3]:
            lines.append(f"- **Score {w.get('score')}**: {w.get('summary') or '—'}")
            if w.get("weaknesses"):
                lines.append(f"  - Слабо / Zaif: {w['weaknesses']}")
            if w.get("advice"):
                lines.append(f"  - Совет / Maslahat: {w['advice']}")
        lines.append("")

    lines.append("## Рекомендации для РОП / ROP uchun tavsiyalar")
    lines.append("")
    lines.append(_ai_team_advice(stats, label))
    lines.append("")
    lines.append("---")
    lines.append(
        "_Источник: AmoCRM + транскрипты звонков (onlinePBX/itgrix) + AI. "
        "Отчёт также: Desktop\\\\AmoCRM-AI-Reports\\\\LATEST.html_"
    )
    return "\n".join(lines)


def generate_report(
    period: str,
    ref: datetime | None = None,
    *,
    publish: bool = True,
    open_browser: bool = True,
) -> tuple[int, Path, str]:
    start, end, label = _period_bounds(period, ref)
    stats = period_stats(start, end)
    md = build_markdown(period, stats, label)
    titles = {
        "day": "Дневной / Kunlik",
        "week": "Недельный / Haftalik",
        "month": "Месячный / Oylik",
    }
    title = f"{titles.get(period, period)} отчёт — {label}"

    report_id = save_report(
        period=period,
        period_start=start,
        period_end=end,
        title=title,
        markdown=md,
        stats=stats,
    )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    fname = f"{period}_{label.replace('–', '-').replace('.', '-')}_{report_id}.md"
    fname = "".join(c if c.isalnum() or c in "-_." else "_" for c in fname)
    path = REPORTS_DIR / fname
    path.write_text(md, encoding="utf-8")
    logger.info("Report saved: %s (id=%s)", path, report_id)

    if publish:
        try:
            from publisher import publish_report

            info = publish_report(
                period=period,
                title=title,
                markdown=md,
                report_id=report_id,
                open_browser=open_browser,
                push_amocrm=False,
            )
            logger.info("Published: %s", info)
        except Exception as exc:
            logger.warning("Publish failed: %s", exc)

    return report_id, path, md
