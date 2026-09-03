"""Push AI assistant notes into active lead cards in AmoCRM."""

from __future__ import annotations

import logging
import time

from amocrm_client import AmoCRMClient
from assistant_service import build_assistant_payload
from storage import db, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("push")


def top_leads(limit: int = 12) -> list[int]:
    init_db()
    with db() as conn:
        rows = conn.execute(
            """
            SELECT lead_id, COUNT(*) AS n
            FROM communications
            WHERE lead_id IS NOT NULL AND lead_id > 0
              AND created_at >= ?
            GROUP BY lead_id
            ORDER BY n DESC, MAX(created_at) DESC
            LIMIT ?
            """,
            (int(time.time()) - 3 * 86400, limit),
        ).fetchall()
        ids = [int(r["lead_id"]) for r in rows]
        if len(ids) < limit:
            extra = conn.execute(
                """
                SELECT lead_id FROM lead_snapshots
                WHERE is_lost = 0 AND is_won = 0
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            for r in extra:
                lid = int(r["lead_id"])
                if lid not in ids:
                    ids.append(lid)
                if len(ids) >= limit:
                    break
        return ids[:limit]


def main() -> None:
    client = AmoCRMClient()
    leads = top_leads(12)
    logger.info("Pushing assistant notes to %s leads: %s", len(leads), leads)
    ok = 0
    results = []
    for lid in leads:
        try:
            data = build_assistant_payload(
                lead_id=lid, client=client, write_note=False  # never spam deal notes
            )
            coach = data.get("coach") or {}
            lead = data.get("lead") or {}
            results.append(
                {
                    "lead_id": lid,
                    "name": lead.get("name"),
                    "manager": lead.get("responsible_name"),
                    "status": lead.get("status_name") or lead.get("status_id"),
                    "score": coach.get("score"),
                    "summary": coach.get("summary"),
                    "next_steps": (coach.get("next_steps") or [])[:3],
                    "url": f"https://kuhhospital.amocrm.ru/leads/detail/{lid}",
                }
            )
            ok += 1
            logger.info(
                "OK lead=%s score=%s manager=%s",
                lid,
                coach.get("score"),
                lead.get("responsible_name"),
            )
            time.sleep(0.35)
        except Exception as exc:
            logger.error("FAIL lead=%s: %s", lid, exc)
            results.append({"lead_id": lid, "error": str(exc)})

    out = __import__("pathlib").Path(__file__).resolve().parent / "reports" / "PUSH_RESULT.md"
    lines = [
        "# Результат: AI-разбор записан в AmoCRM",
        "",
        f"_Успешно: {ok}/{len(leads)}_",
        "",
        "| Lead | Менеджер | Score | Статус | Ссылка |",
        "|------|----------|-------|--------|--------|",
    ]
    for r in results:
        if r.get("error"):
            lines.append(f"| {r['lead_id']} | — | — | ERROR | {r['error'][:40]} |")
            continue
        lines.append(
            f"| {r.get('name') or r['lead_id']} | {r.get('manager') or '—'} | "
            f"{r.get('score')} | {r.get('status')} | [открыть]({r['url']}) |"
        )
        lines.append("")
        lines.append(f"**{r.get('name') or r['lead_id']}** — {r.get('summary')}")
        for s in r.get("next_steps") or []:
            lines.append(f"- {s}")
        lines.append("")

    out.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Wrote %s", out)
    print(f"DONE {ok}/{len(leads)} -> {out}")


if __name__ == "__main__":
    main()
