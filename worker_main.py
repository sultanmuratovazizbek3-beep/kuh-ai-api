"""
CRM AI Desk continuous worker.

Runs forever (detached process):
  1) Collect calls/chats from amoCRM
  2) STT (transcribe recordings)
  3) Analyze quality
  4) Write AI notes into amo deal cards
  5) Auto-assist recent leads (full coach note)

Start:
  python worker_main.py
  (or via run_crm_ai / Launch_CRM_AI_Desk)
"""

from __future__ import annotations

import os
import sys
import time
import traceback
from pathlib import Path


def root_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


ROOT = root_dir()
os.chdir(str(ROOT))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DATA = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "CRMAIDesk"
LOG_DIR = DATA / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG = LOG_DIR / "worker.log"
PID_FILE = DATA / "worker.pid"
STATUS_FILE = DATA / "worker_status.json"

# Force write notes unless explicitly disabled
os.environ.setdefault("WRITE_AMO_CALL_NOTES", "1")


def log(msg: str) -> None:
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n"
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass
    try:
        print(line, end="", flush=True)
    except Exception:
        pass


def write_status(payload: dict) -> None:
    """Honest status for /health + Dashboard."""
    import json

    data = {
        "pid": os.getpid(),
        "updated_at": int(time.time()),
        **payload,
    }
    try:
        tmp = STATUS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(STATUS_FILE)
    except Exception as e:
        log(f"status write: {e}")


def fix_stdio() -> None:
    if sys.stdout is None:
        try:
            sys.stdout = open(LOG_DIR / "worker_stdout.log", "a", encoding="utf-8")
        except Exception:
            sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        try:
            sys.stderr = open(LOG_DIR / "worker_stderr.log", "a", encoding="utf-8")
        except Exception:
            sys.stderr = open(os.devnull, "w")


def cycle() -> dict:
    from analyzer import analyze_batch
    from collector import Collector

    stats: dict = {}
    # 1 collect (fast)
    lookback = int(os.environ.get("WORKER_LOOKBACK_HOURS", "24"))
    write_status({"phase": "collect", "running": True})
    log("step collect…")
    stats["collect"] = Collector().run_once(lookback_hours=lookback)
    log(f"collect ok: {stats['collect']}")

    # 2 STT — SMALL batches so notes/analyze run every cycle (CPU STT is slow)
    try:
        from transcriber import transcribe_batch

        stt_limit = int(os.environ.get("WORKER_STT_LIMIT", "3"))
        min_dur = int(os.environ.get("WORKER_STT_MIN_DURATION", "15"))
        write_status({"phase": "stt", "running": True, "stt_limit": stt_limit})
        log(f"step stt limit={stt_limit}…")
        stt = transcribe_batch(limit=stt_limit, min_duration=min_dur)
        stats["stt"] = {
            "queued": stt.get("queued"),
            "ok": stt.get("ok"),
            "fail": stt.get("fail"),
        }
        log(f"stt ok: {stats['stt']}")
    except Exception as e:
        stats["stt"] = {"error": str(e)[:200]}
        log(f"stt error: {e}")

    # 3 analyze
    try:
        lim = int(os.environ.get("WORKER_ANALYZE_LIMIT", "15"))
        write_status({"phase": "analyze", "running": True})
        log(f"step analyze limit={lim}…")
        n = analyze_batch(limit=lim)
        stats["analyzed"] = n
        log(f"analyzed: {n}")
    except Exception as e:
        stats["analyzed"] = {"error": str(e)[:200]}
        log(f"analyze error: {e}")

    # 4 post call-analysis notes to amo (always try)
    try:
        os.environ["WRITE_AMO_CALL_NOTES"] = "1"
        from amo_notes_publisher import post_pending_notes

        lim = int(os.environ.get("WORKER_NOTES_LIMIT", "20"))
        write_status({"phase": "notes", "running": True})
        log(f"step amo notes limit={lim}…")
        stats["amo_call_notes"] = post_pending_notes(limit=lim)
        log(f"amo notes: {stats['amo_call_notes']}")
    except Exception as e:
        stats["amo_call_notes"] = {"error": str(e)[:200]}
        log(f"notes error: {e}")

    # 5 full lead assist (small batch)
    try:
        lim = int(os.environ.get("WORKER_ASSIST_LIMIT", "4"))
        log(f"step assist limit={lim}…")
        stats["assist"] = auto_assist_recent_leads(limit=lim)
        log(f"assist: {stats['assist']}")
    except Exception as e:
        stats["assist"] = {"error": str(e)[:200]}
        log(f"assist error: {e}")

    return stats


def auto_assist_recent_leads(*, limit: int = 8) -> dict:
    """
    For leads with fresh transcripts not yet assisted, run coach + write note.
    Tracks last assist in meta table / communications note timestamps.
    """
    from assistant_service import build_assistant_payload
    from storage import db, init_db

    init_db()
    now = int(time.time())
    since = now - int(os.environ.get("WORKER_ASSIST_HOURS", "72")) * 3600

    with db() as conn:
        # ensure meta table usage
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)"
            )
        except Exception:
            pass
        rows = conn.execute(
            """
            SELECT lead_id, MAX(created_at) AS mx
            FROM communications
            WHERE lead_id IS NOT NULL
              AND created_at >= ?
              AND (
                (transcript IS NOT NULL AND length(trim(transcript)) > 60
                 AND transcript NOT LIKE '[%')
                OR (recording_url IS NOT NULL AND recording_url != '')
              )
            GROUP BY lead_id
            ORDER BY mx DESC
            LIMIT ?
            """,
            (since, max(1, min(limit * 3, 40))),
        ).fetchall()
        lead_ids = [int(r["lead_id"]) for r in rows if r["lead_id"]]

    ok = fail = skip = 0
    for lid in lead_ids[:limit]:
        meta_key = f"assist_note:{lid}"
        with db() as conn:
            prev = conn.execute(
                "SELECT value FROM meta WHERE key = ?", (meta_key,)
            ).fetchone()
        # skip if assisted in last 6 hours
        if prev and prev["value"]:
            try:
                last = int(prev["value"])
                if now - last < 6 * 3600:
                    skip += 1
                    continue
            except ValueError:
                pass
        try:
            pack = build_assistant_payload(
                lead_id=lid, write_note=True, live_stt=False
            )
            if pack.get("note_written"):
                ok += 1
                with db() as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                        (meta_key, str(now)),
                    )
            elif pack.get("note_error"):
                fail += 1
                log(f"assist note fail {lid}: {pack.get('note_error')}")
            else:
                # no dialog — still mark soft skip so we don't hammer
                skip += 1
                with db() as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
                        (meta_key, str(now)),
                    )
            time.sleep(0.4)
        except Exception as e:
            fail += 1
            log(f"assist {lid}: {e}")
    return {"ok": ok, "fail": fail, "skip": skip, "candidates": len(lead_ids)}


def main() -> None:
    fix_stdio()
    log("=== Worker process start ===")
    try:
        PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    except Exception:
        pass

    try:
        from profiles import get_credentials, import_from_env

        if not get_credentials():
            import_from_env(ROOT / ".env")
            import_from_env(Path(r"C:\Users\ACC-2\amocrm-analytics\.env"))
    except Exception as e:
        log(f"CRM import: {e}")

    try:
        from storage import init_db

        init_db()
    except Exception as e:
        log(f"init_db: {e}")

    interval = int(os.environ.get("POLL_INTERVAL_SECONDS", "120"))
    first_delay = int(os.environ.get("WORKER_FIRST_DELAY", "8"))
    log(f"interval={interval}s first_delay={first_delay}s STT_LIMIT={os.environ.get('WORKER_STT_LIMIT', '3')}")
    time.sleep(first_delay)

    while True:
        t0 = time.time()
        try:
            log("=== cycle start ===")
            write_status({"phase": "start", "running": True, "last_error": None})
            stats = cycle()
            elapsed = time.time() - t0
            write_status(
                {
                    "phase": "idle",
                    "running": False,
                    "last_cycle_at": int(time.time()),
                    "last_cycle_sec": round(elapsed, 1),
                    "last_error": None,
                    "stats": stats,
                }
            )
            log(f"=== cycle done in {elapsed:.1f}s === {stats}")
        except Exception:
            err = traceback.format_exc()
            log("cycle FATAL\n" + err)
            write_status(
                {
                    "phase": "error",
                    "running": False,
                    "last_error": err[-500:],
                    "last_cycle_at": int(time.time()),
                }
            )
        elapsed = time.time() - t0
        # if cycle was long (STT), still pause a bit before next
        wait = max(45, interval - int(elapsed)) if elapsed < interval else 45
        log(f"sleep {wait}s")
        try:
            import json

            prev: dict = {}
            if STATUS_FILE.exists():
                prev = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
            prev.update(
                {
                    "phase": "sleep",
                    "running": False,
                    "sleep_sec": wait,
                    "next_cycle_in": wait,
                    "updated_at": int(time.time()),
                    "pid": os.getpid(),
                }
            )
            STATUS_FILE.write_text(
                json.dumps(prev, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass
        time.sleep(wait)


if __name__ == "__main__":
    main()
