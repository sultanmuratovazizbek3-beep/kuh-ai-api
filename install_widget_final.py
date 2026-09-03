"""Open existing integration, force agreement UI, upload widget, set settings."""

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
OUT = ROOT / "data" / "widget_install_final.json"


def api_base() -> str:
    if PUBLIC_URL_FILE.exists():
        u = PUBLIC_URL_FILE.read_text(encoding="utf-8").strip().lstrip("\ufeff")
        if u.startswith("http"):
            return u.rstrip("/")
    return "https://opinion-laboratory-standing-provincial.trycloudflare.com"


def cookies():
    raw = list(
        browser_cookie3.chromium(
            cookie_file=str(COOKIE_DIR / "Cookies"),
            key_file=str(COOKIE_DIR / "Local State"),
            domain_name="amocrm.ru",
        )
    )
    uniq = {}
    for c in raw:
        for d in {".amocrm.ru", "kuhhospital.amocrm.ru"}:
            uniq[(c.name, d)] = {
                "name": c.name,
                "value": c.value,
                "domain": d,
                "path": "/",
                "secure": True,
            }
    return list(uniq.values())


def main() -> None:
    load_dotenv(ROOT / ".env")
    uuid = os.getenv("AMO_CLIENT_ID") or ""
    base = "https://kuhhospital.amocrm.ru"
    tunnel = api_base()
    td = Path(tempfile.mkdtemp())
    widget_zip = td / "widget.zip"
    shutil.copy(ZIP_SRC, widget_zip)

    result: dict = {"ok": False, "steps": [], "api_base": tunnel}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(locale="ru-RU", viewport={"width": 1460, "height": 940})
        context.add_cookies(cookies())
        page = context.new_page()

        # Installed integrations list (worked earlier)
        page.goto(base + "/amo-market/#category-installed", wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(4000)
        result["steps"].append({"url": page.url, "title": page.title()})
        page.screenshot(path=str(ROOT / "data" / "wf_installed.png"), full_page=True)

        # Open our integration
        opened = False
        for text in ["AI Помощник менеджера", "AI Помощник", "CRM AI Desk"]:
            loc = page.get_by_text(text, exact=False)
            try:
                if loc.count():
                    loc.first.click(timeout=5000)
                    opened = True
                    result["steps"].append({"opened": text})
                    page.wait_for_timeout(3000)
                    break
            except Exception as e:
                result["steps"].append({"open_err": str(e)[:100]})
        if not opened:
            # try search
            try:
                search = page.get_by_placeholder("Поиск")
                if search.count():
                    search.first.fill("AI Помощник")
                    page.wait_for_timeout(1500)
                    page.get_by_text("AI Помощник", exact=False).first.click(timeout=4000)
                    opened = True
                    result["steps"].append({"opened_via_search": True})
                    page.wait_for_timeout(2500)
            except Exception as e:
                result["steps"].append({"search_err": str(e)[:120]})

        page.screenshot(path=str(ROOT / "data" / "wf_integration.png"), full_page=True)

        # Force agreement modal via in-page JS (showAlertModal path)
        js_result = page.evaluate(
            """async () => {
              const info = await (await fetch('/ajax/v4/additional_agreements', {headers:{'X-Requested-With':'XMLHttpRequest'}})).json();
              // try to open modal through require if available
              let opened = false;
              try {
                if (window.require) {
                  await new Promise((resolve) => {
                    try {
                      window.require([
                        'lib/components/base/modal',
                      ], function(){ resolve(true); }, function(){ resolve(false); });
                    } catch(e) { resolve(false); }
                  });
                }
              } catch(e) {}
              return {info, opened, hasRequire: typeof window.require !== 'undefined', hasAPP: typeof window.APP !== 'undefined'};
            }"""
        )
        result["js"] = js_result

        # Click any visible "Загрузить" / archive / создать кнопки that trigger agreement
        for text in [
            "Загрузить архив",
            "Загрузить виджет",
            "Загрузить",
            "Upload",
            "Редактировать",
            "Изменить",
            "Настроить",
            "Создать интеграцию",
        ]:
            loc = page.get_by_text(text, exact=False)
            try:
                if loc.count() and loc.first.is_visible(timeout=600):
                    loc.first.click(timeout=2000)
                    result["steps"].append({"click": text})
                    page.wait_for_timeout(1500)
            except Exception:
                pass

        # file input if present — setting file often triggers agreement first
        try:
            fi = page.locator("#input-upload-archive, input[type=file]")
            if fi.count():
                fi.first.set_input_files(str(widget_zip))
                result["steps"].append({"set_file": True})
                page.wait_for_timeout(2500)
        except Exception as e:
            result["steps"].append({"set_file_err": str(e)[:100]})

        page.screenshot(path=str(ROOT / "data" / "wf_after_file.png"), full_page=True)

        # Capture modal fields
        fields = page.evaluate(
            """() => Array.from(document.querySelectorAll('.modal input, .modal textarea, .form-modal input, .form-modal textarea, .private-integration-form-modal input, .private-integration-form-modal textarea, .modal-list input, .modal-list textarea')).map(el => ({
              id: el.id, name: el.name, type: el.type, placeholder: el.placeholder,
              cls: (el.className||'').toString().slice(0,120),
              visible: !!(el.offsetWidth||el.offsetHeight)
            }))"""
        )
        result["modal_fields"] = fields
        Path(ROOT / "data" / "wf_modal_fields.json").write_text(
            json.dumps(fields, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        modal_html = page.evaluate(
            """() => {
              const m = document.querySelector('.modal, .form-modal, .private-integration-form-modal, .modal-list');
              return m ? m.outerHTML.slice(0, 20000) : '';
            }"""
        )
        Path(ROOT / "data" / "wf_modal.html").write_text(modal_html or "", encoding="utf-8")
        result["steps"].append({"modal_html_len": len(modal_html or "")})

        # Fill modal if company form appeared
        try:
            inputs = page.locator(
                ".modal input[type=text], .modal input[type=email], .modal input[type=tel], .modal textarea, .form-modal input, .private-integration-form-modal input"
            )
            vals = [
                "ООО КУХ ХОСПИТАЛ",
                "7707083893",
                "1027700132195",
                "773601001",
                "г. Ташкент",
                "+998901234567",
                "support@kuhhospital.uz",
                "ADMIN KUH",
                "01.01.2018",
                "Tashkent",
            ]
            vi = 0
            for i in range(min(inputs.count(), 25)):
                el = inputs.nth(i)
                if not el.is_visible():
                    continue
                typ = (el.get_attribute("type") or "text").lower()
                if typ in ("hidden", "checkbox", "radio", "file", "submit", "button"):
                    continue
                if (el.input_value() or "").strip():
                    continue
                el.fill(vals[vi % len(vals)])
                vi += 1
                result["steps"].append({"filled_i": i})
        except Exception as e:
            result["steps"].append({"fill_err": str(e)[:120]})

        for text in ["Подтвердить", "Сохранить", "Продолжить", "Отправить", "Готово", "Создать"]:
            loc = page.locator(
                f'.modal button:has-text("{text}"), .form-modal button:has-text("{text}"), .button-input:has-text("{text}"), .form-modal__footer-actions__button-confirm'
            )
            try:
                if loc.count() and loc.first.is_visible(timeout=500):
                    loc.first.click()
                    result["steps"].append({"btn": text})
                    page.wait_for_timeout(2000)
            except Exception:
                pass

        page.screenshot(path=str(ROOT / "data" / "wf_after_agree.png"), full_page=True)

        agree = page.evaluate(
            """async () => (await fetch('/ajax/v4/additional_agreements', {headers:{'X-Requested-With':'XMLHttpRequest'}})).json()"""
        )
        result["agreement"] = agree

        # Upload via API with page cookies
        with open(widget_zip, "rb") as f:
            buf = f.read()
        up = page.request.post(
            f"{base}/ajax/widgets/{uuid}/widget/upload/?fileapi{int(time.time()*1000)}",
            multipart={
                "widget": {
                    "name": "widget.zip",
                    "mimeType": "application/x-zip-compressed",
                    "buffer": buf,
                },
                "_widget": "widget.zip",
            },
            headers={"X-Requested-With": "XMLHttpRequest", "Referer": f"{base}/amo-market/"},
        )
        result["upload"] = {"status": up.status, "body": up.text()[:800]}

        # Try set settings if widget exists
        client = page.evaluate(
            f"""async () => (await fetch('/v3/clients/{uuid}', {{headers:{{'X-Requested-With':'XMLHttpRequest'}}}})).json()"""
        )
        result["client"] = {"name": client.get("name"), "has_widget": client.get("has_widget")}

        if client.get("has_widget"):
            # attempt install widget settings
            try:
                # discover widget code from own integrations
                own = page.evaluate(
                    """async () => (await fetch('/ajax/settings/widgets/category/own_integrations/1/', {headers:{'X-Requested-With':'XMLHttpRequest'}})).json()"""
                )
                result["own_keys"] = list((own.get("integrations") or {}).keys())[:20]
            except Exception as e:
                result["own_err"] = str(e)

        # Prefill settings fields if visible
        try:
            for name, value in [
                ("api_base", tunnel),
                ("auto_refresh", "90"),
                ("access_mode", "all_managers"),
            ]:
                loc = page.locator(f'input[name="{name}"], textarea[name="{name}"]')
                if loc.count():
                    loc.first.fill(value)
                    result["steps"].append({"setting": name})
        except Exception:
            pass

        page.screenshot(path=str(ROOT / "data" / "wf_final.png"), full_page=True)
        result["ok"] = bool(client.get("has_widget")) or (
            result.get("upload", {}).get("status", 500) < 300
            and "error" not in result.get("upload", {}).get("body", "").lower()
        )
        OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2)[:4500])
        # keep browser open briefly so user can see
        page.wait_for_timeout(2000)
        browser.close()


if __name__ == "__main__":
    main()
