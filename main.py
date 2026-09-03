"""
AmoCRM Analytics — calls STT + bilingual coach + auto reports.

  python main.py --once
  python main.py --transcribe 15
  python main.py --report day
  python main.py
"""

from __future__ import annotations

import argparse
import logging
import sys

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from analyzer import analyze_batch
from collector import Collector
from config import (
    DAILY_REPORT_HOUR,
    MONTHLY_REPORT_DAY,
    MONTHLY_REPORT_HOUR,
    POLL_INTERVAL_SECONDS,
    REPORTS_DIR,
    TIMEZONE,
    WEEKLY_REPORT_DOW,
    WEEKLY_REPORT_HOUR,
    validate_config,
)
from report_generator import generate_report
from storage import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("amocrm-analytics")


def cycle(lookback_hours: int = 48, transcribe_limit: int = 15) -> dict:
    collector = Collector()
    stats = collector.run_once(lookback_hours=lookback_hours)

    # 1) Listen to call recordings → transcript
    try:
        from transcriber import transcribe_batch

        stt = transcribe_batch(limit=transcribe_limit, min_duration=10)
        stats["stt"] = {k: stt[k] for k in ("queued", "ok", "fail")}
    except Exception as exc:
        logger.warning("STT batch failed: %s", exc)
        stats["stt"] = {"error": str(exc)}

    # 2) Analyze + auto-note into amoCRM deal
    analyzed = analyze_batch(limit=25)
    stats["analyzed"] = analyzed
    try:
        from amo_notes_publisher import post_pending_notes

        stats["amo_notes"] = post_pending_notes(limit=20)
    except Exception as exc:
        logger.warning("amo notes: %s", exc)
        stats["amo_notes"] = {"error": str(exc)}
    logger.info("Cycle done: %s", stats)
    return stats


def run_report(period: str, open_browser: bool = True) -> None:
    report_id, path, md = generate_report(
        period, publish=True, open_browser=open_browser
    )
    logger.info("Generated %s report id=%s -> %s", period, report_id, path)
    logger.info("Also on Desktop: AmoCRM-AI-Reports\\LATEST.html")


def main() -> None:
    parser = argparse.ArgumentParser(description="AmoCRM Analytics")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--report", choices=["day", "week", "month"])
    parser.add_argument("--backfill", type=int, metavar="HOURS")
    parser.add_argument(
        "--transcribe",
        type=int,
        metavar="N",
        help="Only transcribe N call recordings and exit",
    )
    parser.add_argument(
        "--no-send",
        action="store_true",
        help="(compat) continuous mode without Telegram",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open LATEST.html after report",
    )
    args = parser.parse_args()

    missing = validate_config()
    if missing:
        logger.error("Missing env: %s", ", ".join(missing))
        sys.exit(1)

    init_db()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    if args.transcribe is not None:
        from transcriber import transcribe_batch

        # ensure recent call notes exist
        Collector().collect_call_notes(
            int(__import__("time").time()) - 7 * 86400
        )
        print(transcribe_batch(limit=args.transcribe, min_duration=12))
        return

    if args.backfill:
        cycle(lookback_hours=args.backfill, transcribe_limit=12)
        return

    if args.report:
        # light collect + a few STTs only — full STT is continuous worker job
        cycle(
            lookback_hours=24 * 8 if args.report != "month" else 24 * 32,
            transcribe_limit=2,
        )
        run_report(args.report, open_browser=not args.no_browser)
        return

    if args.once:
        cycle()
        return

    logger.info(
        "Starting analytics (poll %ss, STT+analyze, tz=%s)",
        POLL_INTERVAL_SECONDS,
        TIMEZONE,
    )
    cycle()

    scheduler = BlockingScheduler(timezone=TIMEZONE)
    scheduler.add_job(
        cycle,
        IntervalTrigger(seconds=POLL_INTERVAL_SECONDS),
        id="collect_stt_analyze",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        lambda: run_report("day", open_browser=False),
        CronTrigger(hour=DAILY_REPORT_HOUR, minute=0),
        id="daily_report",
    )
    scheduler.add_job(
        lambda: run_report("week", open_browser=False),
        CronTrigger(day_of_week=WEEKLY_REPORT_DOW, hour=WEEKLY_REPORT_HOUR, minute=0),
        id="weekly_report",
    )
    scheduler.add_job(
        lambda: run_report("month", open_browser=False),
        CronTrigger(day=MONTHLY_REPORT_DAY, hour=MONTHLY_REPORT_HOUR, minute=5),
        id="monthly_report",
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Stopped")


if __name__ == "__main__":
    main()
