"""Auto-install private amoCRM widget using Yandex browser session cookies."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path

import browser_cookie3
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
ZIP_SRC = ROOT / "public" / "kuh-assistant-widget.zip"
COOKIE_DIR = ROOT / "data" / "_ycookies"
PUBLIC_URL_FILE = ROOT / "public" / "API_PUBLIC_URL.txt"


def load_session() -> requests.Session:
    load_dotenv(ROOT / ".env")
    cookie_file = COOKIE_DIR / "Cookies"
    key_file = COOKIE_DIR / "Local State"
    if not cookie_file.exists() or not key_file.exists():
        raise RuntimeError("No saved Yandex cookies. Copy them first.")
    s = requests.Session()
    for c in browser_cookie3.chromium(
        cookie_file=str(cookie_file),
        key_file=str(key_file),
        domain_name="amocrm.ru",
    ):
        s.cookies.set(c.name, c.value, domain=c.domain, path=c.path)
    return s


def api_base() -> str:
    if PUBLIC_URL_FILE.exists():
        u = PUBLIC_URL_FILE.read_text(encoding="utf-8").strip().lstrip("\ufeff")
        if u.startswith("http"):
            return u.rstrip("/")
    return "https://opinion-laboratory-standing-provincial.trycloudflare.com"


def playwright_install_and_configure() -> dict:
    from playwright.sync_api import sync_playwright

    load_dotenv(ROOT / ".env")
    uuid = os.getenv("AMO_CLIENT_ID") or ""
    subdomain = os.getenv("AMO_SUBDOMAIN") or "kuhhospital"
    base = f"https://{subdomain}.amocrm.ru"
    tunnel = api_base()

    # Prepare widget.zip named exactly widget.zip
    td = Path(tempfile.mkdtemp())
    widget_zip = td / "widget.zip"
    shutil.copy(ZIP_SRC, widget_zip)

    cookie_file = COOKIE_DIR / "Cookies"
    key_file = COOKIE_DIR / "Local State"
    raw_cookies = list(
        browser_cookie3.chromium(
            cookie_file=str(cookie_file),
            key_file=str(key_file),
            domain_name="amocrm.ru",
        )
    )

    result: dict = {"ok": False, "steps": []}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(locale="ru-RU", viewport={"width": 1400, "height": 900})
        # inject cookies
        pw_cookies = []
        for c in raw_cookies:
            item = {
                "name": c.name,
                "value": c.value,
                "domain": c.domain.lstrip(".") if c.domain else ".amocrm.ru",
                "path": c.path or "/",
                "httpOnly": bool(getattr(c, "secure", False) and False),
                "secure": True if "amocrm" in (c.domain or "") else bool(getattr(c, "secure", False)),
            }
            # playwright wants domain without leading issues
            if not item["domain"].startswith("."):
                # keep as is
                pass
            pw_cookies.append(item)
        # fix domains for playwright
        fixed = []
        for c in pw_cookies:
            dom = c["domain"]
            if not dom.startswith(".") and "amocrm" in dom:
                # ok
                pass
            fixed.append(
                {
                    "name": c["name"],
                    "value": c["value"],
                    "domain": dom if dom.startswith(".") else dom,
                    "path": c["path"],
                    "secure": True,
                }
            )
        context.add_cookies(fixed)
        page = context.new_page()

        page.goto(f"{base}/settings/widgets/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2500)
        result["steps"].append({"url": page.url, "title": page.title()})
        page.screenshot(path=str(ROOT / "data" / "widget_install_1.png"), full_page=True)

        # If redirected to login — fail clearly
        if "login" in page.url or "amo.crm" in page.url and "/oauth" in page.url:
            result["error"] = f"Not logged in, url={page.url}"
            browser.close()
            return result

        # Try accept additional agreement modal if present
        for sel in [
            "text=Дополнительное соглашение",
            "text=дополнительное соглашение",
            "text=Принимаю",
            "text=Согласен",
            "text=Продолжить",
            '[data-test="additional-agreement"]',
            "input[name='is_additional_agreement_performed']",
        ]:
            loc = page.locator(sel)
            try:
                if loc.count() and loc.first.is_visible(timeout=800):
                    if sel.startswith("input"):
                        loc.first.check(force=True)
                    else:
                        loc.first.click(timeout=2000)
                    result["steps"].append({"clicked": sel})
                    page.wait_for_timeout(500)
            except Exception:
                pass

        # Checkboxes near agreement
        try:
            boxes = page.locator("input[type=checkbox]")
            for i in range(min(boxes.count(), 12)):
                box = boxes.nth(i)
                try:
                    if box.is_visible():
                        box.check(force=True)
                except Exception:
                    pass
        except Exception:
            pass

        # Open our integration by name
        for text in ["AI Помощник менеджера", "CRM AI Desk Analytics", "AI Помощник"]:
            loc = page.locator(f"text={text}")
            try:
                if loc.count():
                    loc.first.click(timeout=3000)
                    result["steps"].append({"opened": text})
                    page.wait_for_timeout(2000)
                    break
            except Exception:
                pass

        page.screenshot(path=str(ROOT / "data" / "widget_install_2.png"), full_page=True)

        # Look for file input and set zip
        uploaded = False
        file_inputs = page.locator('input[type="file"]')
        try:
            n = file_inputs.count()
            result["steps"].append({"file_inputs": n})
            if n:
                file_inputs.first.set_input_files(str(widget_zip))
                uploaded = True
                result["steps"].append({"uploaded_via": "file_input"})
                page.wait_for_timeout(3000)
        except Exception as e:
            result["steps"].append({"file_input_error": str(e)})

        # Also try upload via page.request (same storage state)
        if not uploaded:
            try:
                # Accept agreement via request context
                page.request.post(
                    f"{base}/ajax/settings/widgets/additional_agreement",
                    form={"is_additional_agreement_performed": "Y"},
                    headers={"X-Requested-With": "XMLHttpRequest"},
                )
                with open(widget_zip, "rb") as f:
                    resp = page.request.post(
                        f"{base}/ajax/widgets/{uuid}/widget/upload/?fileapi{int(time.time()*1000)}",
                        multipart={
                            "widget": {
                                "name": "widget.zip",
                                "mimeType": "application/x-zip-compressed",
                                "buffer": f.read(),
                            },
                            "_widget": "widget.zip",
                        },
                        headers={"X-Requested-With": "XMLHttpRequest", "Referer": f"{base}/settings/widgets/"},
                    )
                result["steps"].append({"api_upload_status": resp.status, "body": resp.text()[:500]})
                uploaded = resp.status < 300 and "error" not in resp.text().lower()
            except Exception as e:
                result["steps"].append({"api_upload_error": str(e)})

        # Save / install settings if fields visible
        for label, value in [
            ("api_base", tunnel),
            ("URL API", tunnel),
            ("access_mode", "all_managers"),
            ("auto_refresh", "90"),
        ]:
            try:
                inp = page.locator(f'input[name*="{label}"], textarea[name*="{label}"]')
                if inp.count():
                    inp.first.fill(value)
                    result["steps"].append({"filled": label})
            except Exception:
                pass

        # Click save/install buttons
        for text in ["Сохранить", "Установить", "Сохранить изменения", "Готово"]:
            loc = page.locator(f'button:has-text("{text}"), .button:has-text("{text}"), [type=submit]:has-text("{text}")')
            try:
                if loc.count() and loc.first.is_visible(timeout=500):
                    loc.first.click()
                    result["steps"].append({"clicked_btn": text})
                    page.wait_for_timeout(1500)
            except Exception:
                pass

        page.screenshot(path=str(ROOT / "data" / "widget_install_3.png"), full_page=True)

        # Verify client has_widget
        try:
            s = load_session()
            info = s.get(
                f"{base}/v3/clients/{uuid}",
                headers={"X-Requested-With": "XMLHttpRequest"},
                timeout=30,
            ).json()
            result["has_widget"] = info.get("has_widget")
            result["client_name"] = info.get("name")
        except Exception as e:
            result["verify_error"] = str(e)

        # Configure widget settings via API if installed
        try:
            # list widgets and find ours
            s = load_session()
            w = s.get(
                f"{base}/api/v4/widgets",
                params={"limit": 50},
                headers={"X-Requested-With": "XMLHttpRequest", "Authorization": f"Bearer {os.getenv('AMO_LONG_LIVED_TOKEN')}"},
                timeout=30,
            )
            # use token client
            from amocrm_client import AmoCRMClient

            c = AmoCRMClient()
            data = c._request("GET", "/api/v4/widgets", params={"limit": 250})
            widgets = (data or {}).get("_embedded", {}).get("widgets", [])
            # after upload, widget code often equals client uuid or generated
            ours = [x for x in widgets if str(x.get("code", "")).startswith(uuid[:8]) or "помощник" in str(x.get("name") or "").lower()]
            result["matched_widgets"] = [
                {"code": x.get("code"), "name": x.get("name"), "active": x.get("is_active")} for x in ours[:5]
            ]
            # install settings for uuid-coded widget
            for code in [uuid, *[x.get("code") for x in ours]]:
                if not code:
                    continue
                try:
                    installed = c._request(
                        "POST",
                        f"/api/v4/widgets/{code}",
                        json={
                            "api_base": tunnel,
                            "api_token": "",
                            "auto_refresh": "90",
                            "access_mode": "all_managers",
                            "allowed_user_ids": "",
                        },
                    )
                    result["installed_settings"] = {"code": code, "resp": installed}
                    break
                except Exception as e:
                    result.setdefault("install_errors", []).append(f"{code}: {e}")
        except Exception as e:
            result["settings_error"] = str(e)

        result["ok"] = bool(result.get("has_widget")) or uploaded
        result["api_base"] = tunnel
        page.wait_for_timeout(1500)
        browser.close()
    return result


def main() -> None:
    # Also try pure-requests agreement discovery from page scripts
    s = load_session()
    load_dotenv(ROOT / ".env")
    uuid = os.getenv("AMO_CLIENT_ID") or ""
    base = f"https://{os.getenv('AMO_SUBDOMAIN') or 'kuhhospital'}.amocrm.ru"

    # Dump JS mentions
    page = s.get(f"{base}/settings/widgets/", timeout=60).text
    Path(ROOT / "data" / "_widgets_page.html").write_text(page, encoding="utf-8")
    for pat in [
        r".{0,80}is_additional_agreement_performed.{0,120}",
        r".{0,60}additional_agreement.{0,120}",
    ]:
        ms = re.findall(pat, page, flags=re.I)
        print("matches", len(ms))
        for m in ms[:5]:
            print(" ", m.replace("\n", " ")[:200])

    print("Running Playwright installer...")
    out = playwright_install_and_configure()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    Path(ROOT / "data" / "widget_install_result.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
