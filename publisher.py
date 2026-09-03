"""Publish reports to Desktop only — NEVER write into AmoCRM deals.

1) Desktop\\AmoCRM-AI-Reports\\LATEST.html  (always the newest)
2) Desktop\\AmoCRM-AI-Reports\\archive\\...
3) Optional: open LATEST.html in browser
"""

from __future__ import annotations

import html
import logging
import os
import time
import webbrowser
from pathlib import Path
from typing import Any

from config import BASE_DIR, TIMEZONE

logger = logging.getLogger(__name__)

DESKTOP = Path(os.path.expanduser("~")) / "Desktop"
OUTBOX = DESKTOP / "AmoCRM-AI-Reports"
ARCHIVE = OUTBOX / "archive"
INBOX_MARKER = OUTBOX / "ОТКРОЙ_МЕНЯ.html"


def _ensure_dirs() -> None:
    OUTBOX.mkdir(parents=True, exist_ok=True)
    ARCHIVE.mkdir(parents=True, exist_ok=True)


def markdown_to_simple_html(md: str, title: str) -> str:
    """Minimal MD→HTML (tables + headers + lists)."""
    lines = md.splitlines()
    body: list[str] = []
    in_table = False
    in_ul = False

    def close_ul() -> None:
        nonlocal in_ul
        if in_ul:
            body.append("</ul>")
            in_ul = False

    def close_table() -> None:
        nonlocal in_table
        if in_table:
            body.append("</tbody></table>")
            in_table = False

    for line in lines:
        s = line.rstrip()
        if s.startswith("|") and "|" in s[1:]:
            close_ul()
            cells = [c.strip() for c in s.strip("|").split("|")]
            if all(set(c) <= set("-: ") for c in cells):
                continue  # separator
            if not in_table:
                body.append(
                    '<table border="1" cellpadding="6" cellspacing="0" '
                    'style="border-collapse:collapse;width:100%;font-size:14px">'
                    "<tbody>"
                )
                in_table = True
                body.append(
                    "<tr>"
                    + "".join(
                        f'<th style="background:#eef2ff;text-align:left">{html.escape(c)}</th>'
                        for c in cells
                    )
                    + "</tr>"
                )
            else:
                body.append(
                    "<tr>"
                    + "".join(f"<td>{html.escape(c)}</td>" for c in cells)
                    + "</tr>"
                )
            continue
        close_table()
        if s.startswith("# "):
            close_ul()
            body.append(f"<h1>{html.escape(s[2:])}</h1>")
        elif s.startswith("## "):
            close_ul()
            body.append(f"<h2>{html.escape(s[3:])}</h2>")
        elif s.startswith("### "):
            close_ul()
            body.append(f"<h3>{html.escape(s[4:])}</h3>")
        elif s.startswith("- "):
            if not in_ul:
                body.append("<ul>")
                in_ul = True
            body.append(f"<li>{html.escape(s[2:])}</li>")
        elif s.strip() == "---":
            close_ul()
            body.append("<hr>")
        elif s.strip() == "":
            close_ul()
            body.append("<br>")
        else:
            close_ul()
            # bold **x**
            t = html.escape(s)
            t = t.replace("**", "")
            body.append(f"<p>{t}</p>")
    close_ul()
    close_table()

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{html.escape(title)}</title>
<style>
  body {{ font-family: Segoe UI, system-ui, sans-serif; margin: 24px; max-width: 980px;
         color: #1f2937; background: #f8fafc; }}
  .card {{ background: #fff; border-radius: 12px; padding: 20px 24px;
           box-shadow: 0 1px 3px rgba(0,0,0,.08); }}
  h1 {{ margin-top: 0; color: #0f172a; }}
  h2 {{ color: #1e3a8a; border-bottom: 1px solid #e2e8f0; padding-bottom: 6px; }}
  table {{ margin: 12px 0 20px; background: #fff; }}
  tr:nth-child(even) td {{ background: #f8fafc; }}
  .meta {{ color: #64748b; font-size: 13px; margin-bottom: 16px; }}
  .badge {{ display:inline-block; background:#2563eb; color:#fff; padding:4px 10px;
            border-radius:999px; font-size:12px; font-weight:600; }}
</style>
</head>
<body>
<div class="card">
  <div class="badge">AmoCRM AI · auto</div>
  <div class="meta">Обновлено автоматически · TZ {html.escape(TIMEZONE)} · не ищите файлы — этот LATEST.html всегда свежий</div>
  {''.join(body)}
</div>
</body>
</html>
"""


def publish_files(period: str, title: str, markdown: str, report_id: int) -> Path:
    _ensure_dirs()
    safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in f"{period}_{report_id}")
    arch = ARCHIVE / f"{safe}.md"
    arch.write_text(markdown, encoding="utf-8")
    (ARCHIVE / f"{safe}.html").write_text(
        markdown_to_simple_html(markdown, title), encoding="utf-8"
    )

    latest_md = OUTBOX / "LATEST.md"
    latest_html = OUTBOX / "LATEST.html"
    latest_md.write_text(markdown, encoding="utf-8")
    latest_html.write_text(markdown_to_simple_html(markdown, title), encoding="utf-8")

    # Always-visible pointer
    INBOX_MARKER.write_text(
        markdown_to_simple_html(
            f"# Отчёты AmoCRM AI\n\nОткройте **LATEST.html** в этой же папке.\n\n"
            f"Последний: **{title}**\n\n"
            f"Папка: `{OUTBOX}`\n",
            "AmoCRM AI Reports",
        ),
        encoding="utf-8",
    )

    # Shortcut note in project
    (BASE_DIR / "reports" / "LATEST.md").write_text(markdown, encoding="utf-8")
    logger.info("Published to Desktop: %s", latest_html)
    return latest_html


def publish_report(
    *,
    period: str,
    title: str,
    markdown: str,
    report_id: int,
    open_browser: bool = True,
    push_amocrm: bool = False,  # never write reports into CRM deals
) -> dict[str, Any]:
    path = publish_files(period, title, markdown, report_id)
    if open_browser:
        try:
            webbrowser.open(path.as_uri())
        except Exception:
            pass
    return {
        "desktop_html": str(path),
        "desktop_folder": str(OUTBOX),
        "amocrm_url": None,
        "ts": int(time.time()),
    }
