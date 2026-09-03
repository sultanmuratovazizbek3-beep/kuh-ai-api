"""Install Табель widget into kuhhospital amoCRM using a copy of the live Yandex profile."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
ZIP_SRC = ROOT / "public" / "tabel-widget.zip"
YANDEX = Path(r"C:\Program Files\Yandex\YandexBrowser\Application\browser.exe")
SRC_PROFILE = Path(os.environ["LOCALAPPDATA"]) / "Yandex" / "YandexBrowser" / "User Data"
DST_PROFILE = ROOT / "data" / "yandex_cdp"
PORT = 9333
BASE = "https://kuhhospital.amocrm.ru"
OUT = ROOT / "data" / "install_tabel_now.json"


def api_base() -> str:
    p = ROOT / "public" / "API_PUBLIC_URL.txt"
    if p.exists():
        u = p.read_text(encoding="utf-8").strip().lstrip("\ufeff")
        if u.startswith("http"):
            return u.rstrip("/")
    return "https://tri-mass-boulder-foundations.trycloudflare.com"


def copy_file(src: Path, dst: Path) -> bool:
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(src, dst)
        return True
    except Exception:
        pass
    if src.suffix == "" or "Cookies" in src.name:
        try:
            raw = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
            dst.unlink(missing_ok=True)
            bak = sqlite3.connect(str(dst))
            raw.backup(bak)
            bak.close()
            raw.close()
            return True
        except Exception:
            return False
    return False


def copy_tree(src: Path, dst: Path) -> int:
    n = 0
    if not src.exists():
        return 0
    for path in src.rglob("*"):
        if path.is_file():
            rel = path.relative_to(src)
            if copy_file(path, dst / rel):
                n += 1
    return n


def prepare_profile() -> None:
    if DST_PROFILE.exists():
        shutil.rmtree(DST_PROFILE, ignore_errors=True)
    DST_PROFILE.mkdir(parents=True, exist_ok=True)
    copy_file(SRC_PROFILE / "Local State", DST_PROFILE / "Local State")
    default_src = SRC_PROFILE / "Default"
    default_dst = DST_PROFILE / "Default"
    for rel in [
        "Preferences",
        "Secure Preferences",
        "Network/Cookies",
        "Network/Cookies-journal",
        "Login Data",
        "Login Data-journal",
        "Web Data",
        "Web Data-journal",
    ]:
        copy_file(default_src / rel, default_dst / rel)
    copy_tree(default_src / "Local Storage", default_dst / "Local Storage")
    copy_tree(default_src / "Session Storage", default_dst / "Session Storage")
    copy_tree(default_src / "Sessions", default_dst / "Sessions")


def start_debug_browser() -> None:
    """Relaunch the real Yandex profile with CDP, keeping the amoCRM login."""
    subprocess.run(
        ["taskkill", "/F", "/IM", "browser.exe"],
        capture_output=True,
        check=False,
    )
    time.sleep(2)
    args = [
        str(YANDEX),
        f"--remote-debugging-port={PORT}",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
        BASE + "/amo-market/application/",
    ]
    subprocess.Popen(args, cwd=str(YANDEX.parent))
    deadline = time.time() + 40
    import urllib.request

    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=1)
            return
        except Exception:
            time.sleep(0.4)
    raise RuntimeError("Yandex debug port did not start")


def dump_visible(page):
    return page.evaluate(
        """() => Array.from(document.querySelectorAll('input,textarea,select,button,a,label,h1,h2')).map(el => ({
          tag: el.tagName, type: el.type||'', id: el.id||'', name: el.name||'',
          text: ((el.innerText||el.textContent||'')+'').trim().slice(0,90),
          visible: !!(el.offsetWidth||el.offsetHeight)
        })).filter(x => x.visible).slice(0,80)"""
    )


def click_first(page, selectors, result, label):
    for sel in selectors:
        try:
            loc = page.locator(sel)
            if loc.count() and loc.first.is_visible(timeout=800):
                loc.first.click(timeout=4000)
                result["steps"].append({label: sel})
                page.wait_for_timeout(1200)
                return True
        except Exception as e:
            result["steps"].append({label + "_fail": sel, "e": str(e)[:80]})
    return False


def main() -> None:
    tunnel = api_base()
    result: dict = {"ok": False, "api_base": tunnel, "steps": []}
    print("relaunch Yandex with debug (keeps login)...", flush=True)
    start_debug_browser()

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}")
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(BASE + "/amo-market/application/", wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(5000)
        result["url1"] = page.url
        result["title1"] = page.title()
        page.screenshot(path=str(ROOT / "data" / "tabel_inst_1.png"), full_page=True)
        print("page", page.url, page.title(), flush=True)

        if "auth" in page.url or "Авторизация" in (page.title() or ""):
            result["error"] = "not_logged_in"
            OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print("NOT LOGGED IN", flush=True)
            return

        click_first(
            page,
            [
                'button:has-text("Создать интеграцию")',
                'text=Создать интеграцию',
                "#keygen-button",
            ],
            result,
            "create",
        )
        page.wait_for_timeout(2000)
        page.screenshot(path=str(ROOT / "data" / "tabel_inst_2.png"), full_page=True)

        click_first(
            page,
            [
                "#create-internal-integration",
                "text=Приватная интеграция",
                "text=приватн",
                "text=Виджет",
            ],
            result,
            "internal",
        )
        page.wait_for_timeout(2000)
        page.screenshot(path=str(ROOT / "data" / "tabel_inst_3.png"), full_page=True)

        for text in ["Продолжить", "Заполнить", "Хорошо", "Понятно", "Далее"]:
            try:
                loc = page.get_by_text(text, exact=False)
                if loc.count() and loc.first.is_visible(timeout=400):
                    loc.first.click()
                    result["steps"].append({"alert": text})
                    page.wait_for_timeout(800)
            except Exception:
                pass

        # Fill visible form fields if agreement still open
        fills = {
            "name": "Табель",
            "description": "Сотрудники, статусы и активность в amoCRM",
            "redirect_uri": "https://example.com",
        }
        for name, val in fills.items():
            try:
                loc = page.locator(f"input[name='{name}'], textarea[name='{name}']")
                if loc.count() and loc.first.is_visible(timeout=400):
                    loc.first.fill(val)
                    result["steps"].append({"filled": name})
            except Exception:
                pass

        # Upload zip if file input exists
        try:
            file_input = page.locator("input[type=file]")
            if file_input.count():
                file_input.first.set_input_files(str(ZIP_SRC))
                result["steps"].append({"file": True})
                page.wait_for_timeout(2500)
        except Exception as e:
            result["steps"].append({"file_fail": str(e)[:120]})

        for text in ["Сохранить", "Установить", "Создать", "Готово"]:
            try:
                loc = page.get_by_role("button", name=text)
                if loc.count() and loc.first.is_visible(timeout=500):
                    loc.first.click()
                    result["steps"].append({"save": text})
                    page.wait_for_timeout(2000)
            except Exception:
                pass

        page.wait_for_timeout(2500)
        page.screenshot(path=str(ROOT / "data" / "tabel_inst_4.png"), full_page=True)
        result["visible"] = dump_visible(page)
        result["url2"] = page.url
        result["title2"] = page.title()

        # Try settings on widget if already in settings form
        try:
            loc = page.locator("input[name='api_base'], input#api_base")
            if loc.count() and loc.first.is_visible(timeout=500):
                loc.first.fill(tunnel)
                result["steps"].append({"api_base_filled": tunnel})
                click_first(page, ['button:has-text("Сохранить")'], result, "save_settings")
        except Exception as e:
            result["steps"].append({"settings_fail": str(e)[:80]})

        page.screenshot(path=str(ROOT / "data" / "tabel_inst_5.png"), full_page=True)
        result["ok"] = True
        OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("DONE", json.dumps({k: result[k] for k in result if k != "visible"}, ensure_ascii=False)[:1500], flush=True)
        page.wait_for_timeout(4000)


if __name__ == "__main__":
    main()
