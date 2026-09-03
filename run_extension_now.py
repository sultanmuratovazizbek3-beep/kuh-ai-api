"""One-click: check API → Edge with unpacked extension + amo cookies → open lead."""

from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXT = ROOT / "browser-extension"
PROFILE = ROOT / "data" / "edge_ext_profile"
COOKIE_DIR = ROOT / "data" / "_ycookies"
RESULT = ROOT / "data" / "ext_result.json"
EDGE_CANDIDATES = [
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
]
PORT = 9222
DEFAULT_LEAD = 31419809
AMO = "https://kuhhospital.amocrm.ru"


def find_edge() -> Path:
    for p in EDGE_CANDIDATES:
        if p.is_file():
            return p
    raise FileNotFoundError("msedge.exe не найден")


def api_health() -> dict:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8090/health", timeout=4) as r:
            return json.loads(r.read().decode("utf-8", errors="replace"))
    except Exception as e:
        return {"status": "fail", "error": str(e)}


def kill_debug_edge() -> None:
    """Stop previous Edge using our profile / debug port (best-effort)."""
    try:
        import psutil
    except Exception:
        # fallback: ignore if port free; else try taskkill by command line later
        psutil = None

    if psutil:
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                name = (proc.info.get("name") or "").lower()
                if "msedge" not in name and "edge" not in name:
                    continue
                cmd = " ".join(proc.info.get("cmdline") or [])
                if str(PROFILE) in cmd or f"--remote-debugging-port={PORT}" in cmd:
                    proc.kill()
            except Exception:
                pass
        time.sleep(1)
        return

    # no psutil: try free the port via netstat + taskkill
    try:
        out = subprocess.check_output(
            f'netstat -ano | findstr ":{PORT}"',
            shell=True,
            text=True,
            errors="replace",
        )
        pids = set()
        for line in out.splitlines():
            parts = line.split()
            if parts and parts[-1].isdigit():
                pids.add(parts[-1])
        for pid in pids:
            subprocess.run(
                ["taskkill", "/F", "/PID", pid],
                capture_output=True,
                check=False,
            )
    except Exception:
        pass


def launch_edge(edge: Path) -> None:
    PROFILE.mkdir(parents=True, exist_ok=True)
    args = [
        str(edge),
        f"--user-data-dir={PROFILE}",
        f"--remote-debugging-port={PORT}",
        "--remote-allow-origins=*",
        f"--disable-extensions-except={EXT}",
        f"--load-extension={EXT}",
        "--no-first-run",
        "--no-default-browser-check",
        "about:blank",
    ]
    subprocess.Popen(args, cwd=str(edge.parent))
    for _ in range(40):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=1)
            return
        except Exception:
            time.sleep(0.4)
    raise RuntimeError("Edge CDP не поднялся на порту " + str(PORT))


def cookies():
    """Merge Chromium Cookies DB + session.json fallback."""
    import browser_cookie3

    uniq = {}

    def put(name: str, value: str, domain: str) -> None:
        if not name or value is None:
            return
        uniq[(name, domain)] = {
            "name": name,
            "value": str(value),
            "domain": domain,
            "path": "/",
            "secure": True,
        }

    try:
        raw = list(
            browser_cookie3.chromium(
                cookie_file=str(COOKIE_DIR / "Cookies"),
                key_file=str(COOKIE_DIR / "Local State"),
                domain_name="amocrm.ru",
            )
        )
        for c in raw:
            for d in {".amocrm.ru", "kuhhospital.amocrm.ru"}:
                put(c.name, c.value, d)
    except Exception as e:
        print("warn: Cookies DB:", e)

    session_path = COOKIE_DIR / "session.json"
    if session_path.is_file():
        try:
            data = json.loads(session_path.read_text(encoding="utf-8"))
            skip = {"server_time", "access_token_expires_at", "amo_user_full_name"}
            for name, value in data.items():
                if name in skip or not isinstance(value, (str, int, float)):
                    continue
                for d in {".amocrm.ru", "kuhhospital.amocrm.ru", "www.amocrm.ru"}:
                    put(name, value, d)
        except Exception as e:
            print("warn: session.json:", e)

    return list(uniq.values())


def detect_panel(page) -> dict:
    return page.evaluate(
        """() => {
          const host = document.getElementById('kuh-ai-host');
          const toggle = document.getElementById('kuh-ai-toggle');
          const panel = document.getElementById('kuh-ai-panel');
          const root = document.getElementById('kuh-ai-root');
          return {
            host: !!host,
            toggle: !!toggle,
            panel: !!panel,
            injectRoot: !!root,
            collapsed: host ? host.classList.contains('kuh-collapsed') : null,
            toggleText: toggle ? (toggle.innerText || '').slice(0, 40) : '',
            bodyHasKuh: (document.documentElement.innerHTML || '').includes('kuh-ai'),
          };
        }"""
    )


def main() -> None:
    result: dict = {"ok": False, "ts": int(time.time())}

    health = api_health()
    result["api_health"] = health
    if health.get("status") != "ok":
        result["error"] = (
            "API offline. Запустите start_always_online.bat "
            "(http://127.0.0.1:8090/health)"
        )
        RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if not EXT.is_dir() or not (EXT / "manifest.json").is_file():
        result["error"] = f"Нет расширения: {EXT}"
        RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if not (COOKIE_DIR / "Cookies").is_file():
        result["error"] = f"Нет cookies: {COOKIE_DIR}"
        RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    edge = find_edge()
    result["edge"] = str(edge)
    kill_debug_edge()
    launch_edge(edge)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}")
        ctx = browser.contexts[0]
        ctx.add_cookies(cookies())
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        page.goto(f"{AMO}/dashboard/", wait_until="domcontentloaded", timeout=120000)
        time.sleep(3)
        result["dash_title"] = page.title()
        result["dash_url"] = page.url
        page.screenshot(path=str(ROOT / "data" / "ext_dash.png"), full_page=True)

        if "Авторизация" in (page.title() or ""):
            result["error"] = "auth failed — обновите data/_ycookies"
            RESULT.write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return

        lead_url = f"{AMO}/leads/detail/{DEFAULT_LEAD}"
        page.goto(lead_url, wait_until="domcontentloaded", timeout=120000)
        time.sleep(5)

        # if lead missing, try first from pipeline
        if "/leads/detail/" not in page.url:
            page.goto(
                f"{AMO}/leads/list/pipeline/",
                wait_until="domcontentloaded",
                timeout=120000,
            )
            time.sleep(4)
            href = page.evaluate(
                """() => {
                  const a = Array.from(document.querySelectorAll("a[href*='/leads/detail/']"))
                    .map(x => x.getAttribute('href'))
                    .find(h => h && /\\/leads\\/detail\\/\\d+/.test(h));
                  return a || null;
                }"""
            )
            result["lead_href_fallback"] = href
            if href:
                if href.startswith("/"):
                    href = AMO + href
                page.goto(href, wait_until="domcontentloaded", timeout=120000)
                time.sleep(5)

        result["lead_title"] = page.title()
        result["lead_url"] = page.url
        time.sleep(2)

        panel = detect_panel(page)
        result["panel"] = panel

        # expand collapsed pill so managers see the panel
        if panel.get("host") and panel.get("collapsed"):
            page.evaluate(
                """() => {
                  const t = document.getElementById('kuh-ai-toggle');
                  if (t) t.click();
                }"""
            )
            time.sleep(2)
            panel = detect_panel(page)
            result["panel_after_expand"] = panel

        # soft-click analyze if present
        page.evaluate(
            """() => {
              const b = document.getElementById('kuh-go');
              if (b && !b.disabled) b.click();
            }"""
        )
        time.sleep(4)
        result["status_text"] = page.evaluate(
            """() => {
              const el = document.getElementById('kuh-st');
              return el ? (el.textContent || '').slice(0, 120) : '';
            }"""
        )

        page.screenshot(path=str(ROOT / "data" / "ext_lead.png"), full_page=True)
        result["ok"] = bool(panel.get("host") or panel.get("injectRoot") or panel.get("bodyHasKuh"))
        result["hint"] = (
            "Edge оставлен открытым с расширением. "
            "Панель: кнопка KUH AI справа внизу → Разобрать / Копировать / В заметку."
        )

        RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
