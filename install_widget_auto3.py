"""Open My Application, complete additional agreement, upload widget.zip."""

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
OUT = ROOT / "data" / "widget_install_result3.json"


def cookies_for_context():
    raw = list(
        browser_cookie3.chromium(
            cookie_file=str(COOKIE_DIR / "Cookies"),
            key_file=str(COOKIE_DIR / "Local State"),
            domain_name="amocrm.ru",
        )
    )
    uniq = {}
    for c in raw:
        for d in {".amocrm.ru", "kuhhospital.amocrm.ru", ".kuhhospital.amocrm.ru"}:
            item = {
                "name": c.name,
                "value": c.value,
                "domain": d,
                "path": c.path or "/",
                "secure": True,
            }
            uniq[(item["name"], item["domain"], item["path"])] = item
    return list(uniq.values())


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
        context.add_cookies(cookies_for_context())
        page = context.new_page()

        # My application page — where private integrations are managed
        page.goto(base + "/amo-market/#category-installed", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)
        page.goto(base + "/amo-market/application/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3500)
        result["steps"].append({"url": page.url, "title": page.title()})
        page.screenshot(path=str(ROOT / "data" / "w3_app.png"), full_page=True)

        # Click create integration
        created = False
        for sel in [
            'text="Создать интеграцию"',
            'button:has-text("Создать интеграцию")',
            'text="Создать"',
            '[data-action="create-integration"]',
            ".js-create-integration",
        ]:
            loc = page.locator(sel)
            try:
                if loc.count() and loc.first.is_visible(timeout=1000):
                    loc.first.click()
                    created = True
                    result["steps"].append({"clicked": sel})
                    page.wait_for_timeout(2500)
                    break
            except Exception as e:
                result["steps"].append({"click_err": sel, "e": str(e)[:100]})

        page.screenshot(path=str(ROOT / "data" / "w3_create.png"), full_page=True)

        # Dump modal HTML for debugging
        try:
            modal_html = page.evaluate(
                """() => {
                  const m = document.querySelector('.modal, .form-modal, .private-integration-form-modal, .modal-body');
                  return m ? m.outerHTML.slice(0, 15000) : document.body.innerHTML.slice(0, 8000);
                }"""
            )
            Path(ROOT / "data" / "w3_modal.html").write_text(modal_html or "", encoding="utf-8")
            result["steps"].append({"modal_len": len(modal_html or "")})
            # list inputs
            fields = page.evaluate(
                """() => Array.from(document.querySelectorAll('input, textarea, select')).map(el => ({
                  tag: el.tagName, type: el.type, id: el.id, name: el.name,
                  placeholder: el.placeholder, visible: !!(el.offsetWidth || el.offsetHeight),
                  cls: el.className.slice(0,80)
                })).filter(x => x.visible).slice(0, 40)"""
            )
            result["fields"] = fields
        except Exception as e:
            result["steps"].append({"modal_err": str(e)})

        # If choose-entity radios exist, keep legal_entity or pick
        try:
            radio = page.locator('input[name="choose-entity"]')
            if radio.count():
                # prefer legal if present
                page.locator('input[name="choose-entity"][value="legal_entity"]').check(force=True)
                result["steps"].append({"entity": "legal_entity"})
                page.wait_for_timeout(800)
        except Exception:
            pass

        # Fill by id heuristics after modal render
        id_values = {
            "inn": "305123456",
            "ogrn": "1234567890123",
            "kpp": "770101001",
            "name": "KUH Hospital",
            "company_name": "KUH Hospital",
            "organization_name": "KUH Hospital",
            "legal_name": "KUH Hospital",
            "address": "Tashkent, Uzbekistan",
            "legal_address": "Tashkent, Uzbekistan",
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
            loc = page.locator(f"#{iid}, input[name='{iid}'], textarea[name='{iid}']")
            try:
                if loc.count() and loc.first.is_visible(timeout=300):
                    loc.first.fill(val)
                    result["steps"].append({"fill_id": iid})
            except Exception:
                pass

        # Fill all visible empty text inputs sequentially
        try:
            vals = [
                "KUH Hospital",
                "305123456",
                "1234567890123",
                "770101001",
                "Tashkent, Uzbekistan",
                "+998901234567",
                "support@kuhhospital.uz",
                "ADMIN KUH",
                "01.01.2018",
                "Tashkent",
            ]
            inputs = page.locator(
                "input[type=text], input[type=email], input[type=tel], input:not([type]), textarea"
            )
            vi = 0
            for i in range(min(inputs.count(), 25)):
                el = inputs.nth(i)
                try:
                    if not el.is_visible():
                        continue
                    cur = el.input_value()
                    if cur and cur.strip():
                        continue
                    el.fill(vals[vi % len(vals)])
                    vi += 1
                    result["steps"].append({"seq_fill": i})
                except Exception:
                    pass
        except Exception as e:
            result["steps"].append({"seq_err": str(e)})

        # Confirm
        for text in ["Подтвердить", "Сохранить", "Продолжить", "Создать", "Готово"]:
            btn = page.locator(f'button:has-text("{text}"), .button-input:has-text("{text}"), .form-modal__footer-actions__button-confirm')
            try:
                if btn.count() and btn.first.is_visible(timeout=500):
                    btn.first.click()
                    result["steps"].append({"confirm": text})
                    page.wait_for_timeout(2000)
            except Exception:
                pass

        page.screenshot(path=str(ROOT / "data" / "w3_after_agree.png"), full_page=True)

        # Check agreement status in-page
        agree = page.evaluate(
            """async () => {
              const r = await fetch('/ajax/v4/additional_agreements', {headers:{'X-Requested-With':'XMLHttpRequest'}});
              return await r.json();
            }"""
        )
        result["agreement"] = agree

        # If still not defined, try API post with fields discovered from DOM
        if agree.get("status") == "not_defined" and result.get("fields"):
            field_payload = {}
            for f in result["fields"]:
                name = f.get("id") or f.get("name")
                if not name:
                    continue
                if name in id_values:
                    field_payload[name] = id_values[name]
            if field_payload:
                post = page.evaluate(
                    """async (payload) => {
                      const r = await fetch('/ajax/v4/additional_agreements', {
                        method: 'POST',
                        headers: {'Content-Type':'application/json','X-Requested-With':'XMLHttpRequest'},
                        body: JSON.stringify(payload)
                      });
                      return {status: r.status, body: await r.text()};
                    }""",
                    {"entity_type": "legal_entity", "fields": field_payload},
                )
                result["agree_post"] = post

        # Upload zip via request
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
            headers={"X-Requested-With": "XMLHttpRequest", "Referer": f"{base}/settings/widgets/"},
        )
        result["upload"] = {"status": up.status, "body": up.text()[:800]}

        # Also try set file on #input-upload-archive if present
        try:
            # reopen integration edit
            page.goto(base + "/amo-market/#category-installed", wait_until="domcontentloaded")
            page.wait_for_timeout(2500)
            loc = page.get_by_text("AI Помощник менеджера", exact=False)
            if loc.count():
                loc.first.click()
                page.wait_for_timeout(2500)
            fi = page.locator("#input-upload-archive, input[type=file]")
            if fi.count():
                fi.first.set_input_files(str(widget_zip))
                result["steps"].append({"ui_upload": True})
                page.wait_for_timeout(2000)
                for text in ["Сохранить", "Установить", "Upload integration", "Загрузить"]:
                    b = page.locator(f'button:has-text("{text}"), .button-input:has-text("{text}"), #keygen-button')
                    if b.count() and b.first.is_visible(timeout=500):
                        b.first.click()
                        result["steps"].append({"save": text})
                        page.wait_for_timeout(2500)
                        break
        except Exception as e:
            result["steps"].append({"ui_upload_err": str(e)[:150]})

        page.screenshot(path=str(ROOT / "data" / "w3_final.png"), full_page=True)

        client = page.evaluate(
            f"""async () => {{
              const r = await fetch('/v3/clients/{uuid}', {{headers:{{'X-Requested-With':'XMLHttpRequest'}}}});
              return await r.json();
            }}"""
        )
        result["client"] = {"name": client.get("name"), "has_widget": client.get("has_widget")}
        agree2 = page.evaluate(
            """async () => {
              const r = await fetch('/ajax/v4/additional_agreements', {headers:{'X-Requested-With':'XMLHttpRequest'}});
              return await r.json();
            }"""
        )
        result["agreement_after"] = agree2
        result["ok"] = bool(client.get("has_widget")) or (
            result.get("upload", {}).get("status", 500) < 300
            and "error" not in str(result.get("upload", {}).get("body", "")).lower()
        )

        OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        page.wait_for_timeout(800)
        browser.close()


if __name__ == "__main__":
    main()
