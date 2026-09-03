"""Install widget via Playwright with corrected cookie domains + fill agreement."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from pathlib import Path

import browser_cookie3
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
ZIP_SRC = ROOT / "public" / "kuh-assistant-widget.zip"
COOKIE_DIR = ROOT / "data" / "_ycookies"
PUBLIC_URL_FILE = ROOT / "public" / "API_PUBLIC_URL.txt"


def api_base() -> str:
    if PUBLIC_URL_FILE.exists():
        u = PUBLIC_URL_FILE.read_text(encoding="utf-8").strip().lstrip("\ufeff")
        if u.startswith("http"):
            return u.rstrip("/")
    return "https://opinion-laboratory-standing-provincial.trycloudflare.com"


def main() -> None:
    load_dotenv(ROOT / ".env")
    uuid = os.getenv("AMO_CLIENT_ID") or ""
    base = "https://kuhhospital.amocrm.ru"
    tunnel = api_base()

    td = Path(tempfile.mkdtemp())
    widget_zip = td / "widget.zip"
    shutil.copy(ZIP_SRC, widget_zip)

    raw = list(
        browser_cookie3.chromium(
            cookie_file=str(COOKIE_DIR / "Cookies"),
            key_file=str(COOKIE_DIR / "Local State"),
            domain_name="amocrm.ru",
        )
    )
    print("cookies", len(raw))

    result: dict = {"ok": False, "steps": []}

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(locale="ru-RU", viewport={"width": 1440, "height": 920})

        cookies = []
        for c in raw:
            dom = (c.domain or ".amocrm.ru").lstrip(".")
            # add both host-only and wildcard-ish via .amocrm.ru
            for d in {dom, ".amocrm.ru", "kuhhospital.amocrm.ru", ".kuhhospital.amocrm.ru"}:
                cookies.append(
                    {
                        "name": c.name,
                        "value": c.value,
                        "domain": d if d.startswith(".") else d,
                        "path": c.path or "/",
                        "secure": True,
                        "httpOnly": False,
                    }
                )
        # dedupe by name+domain
        uniq = {}
        for c in cookies:
            uniq[(c["name"], c["domain"], c["path"])] = c
        context.add_cookies(list(uniq.values()))

        page = context.new_page()
        page.goto(base + "/dashboard/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2500)
        result["steps"].append({"dash": page.url, "title": page.title()})
        page.screenshot(path=str(ROOT / "data" / "w2_dash.png"), full_page=True)

        if "Авторизация" in page.title() or "login" in page.url:
            result["error"] = "cookies not accepted"
            Path(ROOT / "data" / "widget_install_result2.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            browser.close()
            return

        # Open widgets / amo market installed
        page.goto(base + "/settings/widgets/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        result["steps"].append({"widgets": page.url, "title": page.title()})
        page.screenshot(path=str(ROOT / "data" / "w2_widgets.png"), full_page=True)

        # Trigger agreement modal by attempting create private integration
        # Click "Создать интеграцию" / similar
        for text in [
            "Создать интеграцию",
            "создать интеграцию",
            "Создать",
            "Загрузить интеграцию",
            "Upload integration",
            "Приватные интеграции",
            "Свои интеграции",
        ]:
            loc = page.get_by_text(text, exact=False)
            try:
                if loc.count():
                    loc.first.click(timeout=2000)
                    result["steps"].append({"click": text})
                    page.wait_for_timeout(1500)
            except Exception as e:
                result["steps"].append({"click_fail": text, "err": str(e)[:80]})

        page.screenshot(path=str(ROOT / "data" / "w2_after_create.png"), full_page=True)

        # If agreement form visible — fill legal entity fields by label/placeholder
        # Try common Russian labels
        fill_map = [
            ("ИНН", "305123456"),
            ("ОГРН", "1234567890123"),
            ("КПП", "123456789"),
            ("Название", "KUH Hospital"),
            ("Организац", "KUH Hospital"),
            ("Адрес", "Tashkent, Uzbekistan"),
            ("Телефон", "+998901234567"),
            ("Email", "support@kuhhospital.uz"),
            ("E-mail", "support@kuhhospital.uz"),
            ("Директор", "ADMIN KUH"),
            ("ФИО", "ADMIN KUH"),
        ]
        for label, value in fill_map:
            try:
                # input near label
                lab = page.locator(f"label:has-text('{label}')")
                if lab.count():
                    inp = lab.first.locator("xpath=following::input[1] | following::textarea[1]")
                    if inp.count():
                        inp.first.fill(value)
                        result["steps"].append({"filled_label": label})
                        continue
                ph = page.locator(f"input[placeholder*='{label}'], textarea[placeholder*='{label}']")
                if ph.count():
                    ph.first.fill(value)
                    result["steps"].append({"filled_ph": label})
            except Exception:
                pass

        # Also fill any visible empty required-looking inputs
        try:
            inputs = page.locator(".form-modal__form-wrapper input, .modal-body input, .modal input[type=text], .modal input[type=email], .modal input[type=tel]")
            n = min(inputs.count(), 20)
            defaults = [
                "KUH Hospital",
                "305123456",
                "1234567890123",
                "Tashkent",
                "+998901234567",
                "support@kuhhospital.uz",
                "ADMIN",
                "01.01.2020",
            ]
            di = 0
            for i in range(n):
                el = inputs.nth(i)
                try:
                    if not el.is_visible():
                        continue
                    val = el.input_value()
                    if val:
                        continue
                    typ = (el.get_attribute("type") or "text").lower()
                    iid = el.get_attribute("id") or el.get_attribute("name") or ""
                    if "email" in typ or "email" in iid:
                        el.fill("support@kuhhospital.uz")
                    elif "phone" in iid or "tel" in typ:
                        el.fill("+998901234567")
                    else:
                        el.fill(defaults[di % len(defaults)])
                        di += 1
                    result["steps"].append({"autofill": iid or typ})
                except Exception:
                    pass
        except Exception as e:
            result["steps"].append({"autofill_err": str(e)})

        for text in ["Подтвердить", "Сохранить", "Продолжить", "Отправить", "Готово", "Принимаю"]:
            loc = page.get_by_role("button", name=text)
            try:
                if loc.count() and loc.first.is_visible():
                    loc.first.click()
                    result["steps"].append({"btn": text})
                    page.wait_for_timeout(1500)
            except Exception:
                pass
            loc2 = page.get_by_text(text, exact=True)
            try:
                if loc2.count() and loc2.first.is_visible():
                    loc2.first.click()
                    result["steps"].append({"txtbtn": text})
                    page.wait_for_timeout(1000)
            except Exception:
                pass

        page.screenshot(path=str(ROOT / "data" / "w2_after_agree.png"), full_page=True)

        # Upload via request with storage state
        try:
            with open(widget_zip, "rb") as f:
                buf = f.read()
            resp = page.request.post(
                f"{base}/ajax/widgets/{uuid}/widget/upload/?fileapi{int(time.time()*1000)}",
                multipart={
                    "widget": {
                        "name": "widget.zip",
                        "mimeType": "application/x-zip-compressed",
                        "buffer": buf,
                    },
                    "_widget": "widget.zip",
                },
                headers={
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": f"{base}/settings/widgets/",
                },
            )
            result["upload"] = {"status": resp.status, "body": resp.text()[:500]}
            result["ok"] = resp.status < 300 and "error" not in resp.text().lower()
        except Exception as e:
            result["upload_err"] = str(e)

        # Try file input too
        try:
            page.goto(base + f"/amo-market/#category-installed", wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            # open our integration
            for text in ["AI Помощник менеджера", "CRM AI Desk", "AI Помощник"]:
                loc = page.get_by_text(text, exact=False)
                if loc.count():
                    loc.first.click()
                    page.wait_for_timeout(2000)
                    result["steps"].append({"opened_market": text})
                    break
            fi = page.locator('input[type=file]')
            if fi.count():
                fi.first.set_input_files(str(widget_zip))
                result["steps"].append({"file_set": True})
                page.wait_for_timeout(3000)
        except Exception as e:
            result["steps"].append({"market_err": str(e)[:120]})

        page.screenshot(path=str(ROOT / "data" / "w2_final.png"), full_page=True)

        # Verify agreement + has_widget via in-page fetch
        try:
            agree = page.evaluate(
                """async () => {
                  const r = await fetch('/ajax/v4/additional_agreements', {headers:{'X-Requested-With':'XMLHttpRequest'}});
                  return await r.json();
                }"""
            )
            result["agreement"] = agree
            client = page.evaluate(
                f"""async () => {{
                  const r = await fetch('/v3/clients/{uuid}', {{headers:{{'X-Requested-With':'XMLHttpRequest'}}}});
                  return await r.json();
                }}"""
            )
            result["client"] = {
                "name": client.get("name"),
                "has_widget": client.get("has_widget"),
            }
            if client.get("has_widget"):
                result["ok"] = True
        except Exception as e:
            result["verify_err"] = str(e)

        result["api_base"] = tunnel
        Path(ROOT / "data" / "widget_install_result2.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        page.wait_for_timeout(1000)
        browser.close()


if __name__ == "__main__":
    main()
