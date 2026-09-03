"""Trigger private-integration agreement modal and capture/fill fields."""

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
OUT = ROOT / "data" / "widget_install_result4.json"


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
            item = {
                "name": c.name,
                "value": c.value,
                "domain": d,
                "path": "/",
                "secure": True,
            }
            uniq[(item["name"], item["domain"])] = item
    return list(uniq.values())


def dump_fields(page):
    return page.evaluate(
        """() => Array.from(document.querySelectorAll('input,textarea,select,button')).map(el => ({
          tag: el.tagName, type: el.type||'', id: el.id||'', name: el.name||'',
          value: (el.value||'').slice(0,80),
          text: (el.innerText||'').slice(0,80),
          placeholder: el.placeholder||'',
          visible: !!(el.offsetWidth||el.offsetHeight),
          cls: (el.className||'').toString().slice(0,100)
        })).filter(x => x.visible).slice(0,80)"""
    )


def main() -> None:
    load_dotenv(ROOT / ".env")
    uuid = os.getenv("AMO_CLIENT_ID") or ""
    base = "https://kuhhospital.amocrm.ru"
    td = Path(tempfile.mkdtemp())
    widget_zip = td / "widget.zip"
    shutil.copy(ZIP_SRC, widget_zip)

    result: dict = {"ok": False, "steps": []}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(locale="ru-RU", viewport={"width": 1440, "height": 920})
        context.add_cookies(cookies())
        page = context.new_page()

        page.goto(base + "/amo-market/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)

        # Click left "Мое приложение"
        try:
            page.locator('text="Мое приложение"').first.click(timeout=5000)
            page.wait_for_timeout(2500)
            result["steps"].append({"nav": "Мое приложение", "url": page.url})
        except Exception as e:
            result["steps"].append({"nav_err": str(e)[:120]})

        page.screenshot(path=str(ROOT / "data" / "w4_app.png"), full_page=True)

        # Click Создать интеграцию
        try:
            page.locator('text="Создать интеграцию"').first.click(timeout=5000)
            page.wait_for_timeout(2500)
            result["steps"].append({"click": "Создать интеграцию"})
        except Exception as e:
            result["steps"].append({"create_err": str(e)[:120]})

        page.screenshot(path=str(ROOT / "data" / "w4_create.png"), full_page=True)
        result["fields_create"] = dump_fields(page)
        Path(ROOT / "data" / "w4_create_fields.json").write_text(
            json.dumps(result["fields_create"], ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # Choose private / internal type if radios appear
        for value in ["internal", "private", "widget", "legal_entity"]:
            loc = page.locator(f'input[value="{value}"]')
            try:
                if loc.count():
                    loc.first.check(force=True)
                    result["steps"].append({"radio": value})
                    page.wait_for_timeout(500)
            except Exception:
                pass

        # Click texts related to private widget
        for text in [
            "Приватная интеграция",
            "приватную",
            "Виджет",
            "Загрузить виджет",
            "Свой виджет",
            "Внутренняя",
            "Продолжить",
            "Далее",
            "Создать",
        ]:
            loc = page.get_by_text(text, exact=False)
            try:
                if loc.count() and loc.first.is_visible(timeout=400):
                    loc.first.click(timeout=1500)
                    result["steps"].append({"txt": text})
                    page.wait_for_timeout(1200)
            except Exception:
                pass

        page.screenshot(path=str(ROOT / "data" / "w4_type.png"), full_page=True)
        result["fields_type"] = dump_fields(page)

        # Alert modal buttons
        for text in ["Продолжить", "Заполнить", "Ок", "Хорошо", "Далее", "Создать интеграцию"]:
            loc = page.get_by_text(text, exact=False)
            try:
                if loc.count() and loc.first.is_visible(timeout=400):
                    loc.first.click(timeout=1500)
                    result["steps"].append({"alert": text})
                    page.wait_for_timeout(1500)
            except Exception:
                pass

        page.screenshot(path=str(ROOT / "data" / "w4_alert.png"), full_page=True)
        result["fields_alert"] = dump_fields(page)
        Path(ROOT / "data" / "w4_alert_fields.json").write_text(
            json.dumps(result["fields_alert"], ensure_ascii=False, indent=2), encoding="utf-8"
        )
        try:
            html = page.evaluate(
                """() => {
                  const m = document.querySelector('.modal, .form-modal, .private-integration-form-modal, .modal-list');
                  return m ? m.outerHTML : '';
                }"""
            )
            Path(ROOT / "data" / "w4_modal.html").write_text(html or "", encoding="utf-8")
            result["steps"].append({"modal_html": len(html or "")})
        except Exception as e:
            result["steps"].append({"html_err": str(e)})

        # Fill whatever form appeared
        id_values = {
            "inn": "305123456",
            "ogrn": "1027700132195",
            "kpp": "770101001",
            "name": "KUH Hospital",
            "company_name": "KUH Hospital",
            "organization_name": "ООО КУХ ХОСПИТАЛ",
            "legal_name": "ООО КУХ ХОСПИТАЛ",
            "address": "г. Ташкент",
            "legal_address": "г. Ташкент",
            "phone": "+998901234567",
            "email": "support@kuhhospital.uz",
            "director": "ADMIN KUH",
            "director_name": "ADMIN KUH",
            "full_name": "ADMIN KUH",
            "first_name": "ADMIN",
            "last_name": "KUH",
            "middle_name": "A",
            "passport_series": "AA",
            "passport_number": "1234567",
            "date_of_issue": "01.01.2018",
            "issuer": "Tashkent",
        }
        for iid, val in id_values.items():
            loc = page.locator(f"#{iid}, [name='{iid}']")
            try:
                if loc.count() and loc.first.is_visible(timeout=200):
                    loc.first.fill(val)
                    result["steps"].append({"filled": iid})
            except Exception:
                pass

        # sequential fill empty visible inputs in modal
        try:
            vals = [
                "ООО КУХ ХОСПИТАЛ",
                "305123456",
                "1027700132195",
                "770101001",
                "г. Ташкент",
                "+998901234567",
                "support@kuhhospital.uz",
                "ADMIN KUH",
                "01.01.2018",
                "Tashkent",
            ]
            inputs = page.locator(".modal input, .form-modal input, .modal-list input, .modal textarea")
            vi = 0
            for i in range(min(inputs.count(), 30)):
                el = inputs.nth(i)
                try:
                    if not el.is_visible():
                        continue
                    typ = (el.get_attribute("type") or "text").lower()
                    if typ in ("checkbox", "radio", "hidden", "file", "submit", "button"):
                        continue
                    if (el.input_value() or "").strip():
                        continue
                    el.fill(vals[vi % len(vals)])
                    vi += 1
                    result["steps"].append({"seq": i, "typ": typ})
                except Exception:
                    pass
        except Exception as e:
            result["steps"].append({"seq_err": str(e)})

        for text in ["Подтвердить", "Сохранить", "Отправить", "Продолжить", "Готово"]:
            loc = page.locator(
                f'button:has-text("{text}"), .button-input:has-text("{text}"), .form-modal__footer-actions__button-confirm'
            )
            try:
                if loc.count() and loc.first.is_visible(timeout=500):
                    loc.first.click()
                    result["steps"].append({"save": text})
                    page.wait_for_timeout(2500)
            except Exception:
                pass

        page.screenshot(path=str(ROOT / "data" / "w4_filled.png"), full_page=True)

        agree = page.evaluate(
            """async () => {
              const r = await fetch('/ajax/v4/additional_agreements', {headers:{'X-Requested-With':'XMLHttpRequest'}});
              return await r.json();
            }"""
        )
        result["agreement"] = agree

        # Upload
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

        # Open existing integration and upload via UI file input
        try:
            page.goto(base + "/amo-market/#category-installed", wait_until="domcontentloaded")
            page.wait_for_timeout(2500)
            page.get_by_text("AI Помощник менеджера", exact=False).first.click(timeout=5000)
            page.wait_for_timeout(2500)
            page.screenshot(path=str(ROOT / "data" / "w4_integration.png"), full_page=True)
            result["fields_integration"] = dump_fields(page)
            fi = page.locator("#input-upload-archive, input[type=file]")
            if fi.count():
                fi.first.set_input_files(str(widget_zip))
                result["steps"].append({"file_uploaded_ui": True})
                page.wait_for_timeout(2000)
                for text in ["Сохранить", "Загрузить", "Upload integration", "Установить"]:
                    b = page.locator(f'#keygen-button, button:has-text("{text}"), .button-input:has-text("{text}")')
                    if b.count() and b.first.is_visible(timeout=500):
                        b.first.click()
                        result["steps"].append({"ui_save": text})
                        page.wait_for_timeout(3000)
                        break
            page.screenshot(path=str(ROOT / "data" / "w4_after_upload.png"), full_page=True)
        except Exception as e:
            result["steps"].append({"integration_err": str(e)[:200]})

        client = page.evaluate(
            f"""async () => {{
              const r = await fetch('/v3/clients/{uuid}', {{headers:{{'X-Requested-With':'XMLHttpRequest'}}}});
              return await r.json();
            }}"""
        )
        result["client"] = {"name": client.get("name"), "has_widget": client.get("has_widget")}
        result["agreement_after"] = page.evaluate(
            """async () => {
              const r = await fetch('/ajax/v4/additional_agreements', {headers:{'X-Requested-With':'XMLHttpRequest'}});
              return await r.json();
            }"""
        )
        result["ok"] = bool(client.get("has_widget"))
        OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2)[:5000])
        browser.close()


if __name__ == "__main__":
    main()
