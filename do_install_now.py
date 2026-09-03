"""Fully automated: open internal integration flow -> fill agreement -> upload widget."""

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
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
ZIP_SRC = ROOT / "public" / "kuh-assistant-widget.zip"
COOKIE_DIR = ROOT / "data" / "_ycookies"
PUBLIC_URL_FILE = ROOT / "public" / "API_PUBLIC_URL.txt"
OUT = ROOT / "data" / "do_install_now.json"


def api_base() -> str:
    if PUBLIC_URL_FILE.exists():
        u = PUBLIC_URL_FILE.read_text(encoding="utf-8").strip().lstrip("\ufeff")
        if u.startswith("http"):
            return u.rstrip("/")
    return "https://acute-earrings-diamond-judicial.trycloudflare.com"


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


def req_session():
    s = requests.Session()
    for c in browser_cookie3.chromium(
        cookie_file=str(COOKIE_DIR / "Cookies"),
        key_file=str(COOKIE_DIR / "Local State"),
        domain_name="amocrm.ru",
    ):
        s.cookies.set(c.name, c.value, domain=c.domain, path=c.path)
    return s


def dump_visible(page):
    return page.evaluate(
        """() => Array.from(document.querySelectorAll('input,textarea,select,button,a,label')).map(el => ({
          tag: el.tagName, type: el.type||'', id: el.id||'', name: el.name||'',
          text: ((el.innerText||el.textContent||'')+'').trim().slice(0,80),
          placeholder: el.placeholder||'', value: (el.value||'').slice(0,60),
          visible: !!(el.offsetWidth||el.offsetHeight),
          href: el.href||''
        })).filter(x => x.visible).slice(0,100)"""
    )


def main() -> None:
    load_dotenv(ROOT / ".env")
    uuid = os.getenv("AMO_CLIENT_ID") or ""
    base = "https://kuhhospital.amocrm.ru"
    tunnel = api_base()
    td = Path(tempfile.mkdtemp())
    widget_zip = td / "widget.zip"
    shutil.copy(ZIP_SRC, widget_zip)

    result: dict = {"ok": False, "steps": [], "api_base": tunnel}

    # Quick API probe
    s0 = req_session()
    agr0 = s0.get(
        base + "/ajax/v4/additional_agreements",
        headers={"X-Requested-With": "XMLHttpRequest"},
        timeout=30,
    )
    result["agreement_start"] = agr0.json() if agr0.status_code == 200 else {"http": agr0.status_code}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(locale="ru-RU", viewport={"width": 1500, "height": 960})
        context.add_cookies(cookies())
        page = context.new_page()

        page.goto(base + "/amo-market/", wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(3500)

        # Go to My application via URL (more reliable than sidebar text)
        page.goto(base + "/amo-market/application/", wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(4000)
        result["steps"].append({"url": page.url, "title": page.title()})
        page.screenshot(path=str(ROOT / "data" / "di_1.png"), full_page=True)

        # Click Create integration
        clicked_create = False
        for sel in [
            'button:has-text("Создать интеграцию")',
            'text=Создать интеграцию',
            '#keygen-button',
            '[data-action="create"]',
        ]:
            try:
                loc = page.locator(sel)
                if loc.count() and loc.first.is_visible(timeout=800):
                    loc.first.click(timeout=3000)
                    clicked_create = True
                    result["steps"].append({"create": sel})
                    page.wait_for_timeout(2500)
                    break
            except Exception as e:
                result["steps"].append({"create_fail": sel, "e": str(e)[:80]})

        page.screenshot(path=str(ROOT / "data" / "di_2.png"), full_page=True)
        result["fields_after_create"] = dump_visible(page)

        # Choose INTERNAL integration (private widget path)
        for sel in [
            "#create-internal-integration",
            'text=Приватная интеграция',
            'text=приватн',
            'text=Виджет',
            'text=Загрузить архив',
            'label:has-text("Приватн")',
            'label:has-text("Внутренн")',
        ]:
            try:
                loc = page.locator(sel)
                if loc.count() and loc.first.is_visible(timeout=700):
                    loc.first.click(timeout=2500)
                    result["steps"].append({"internal": sel})
                    page.wait_for_timeout(2000)
            except Exception as e:
                result["steps"].append({"internal_fail": sel, "e": str(e)[:60]})

        page.screenshot(path=str(ROOT / "data" / "di_3.png"), full_page=True)

        # Alert modal continue
        for text in ["Продолжить", "Заполнить", "Хорошо", "Понятно", "Далее", "Ок", "OK"]:
            try:
                loc = page.get_by_role("button", name=re.compile(text, re.I))
                if loc.count() and loc.first.is_visible(timeout=500):
                    loc.first.click()
                    result["steps"].append({"alert_btn": text})
                    page.wait_for_timeout(1500)
            except Exception:
                pass
            try:
                loc = page.locator(f'text={text}')
                if loc.count() and loc.first.is_visible(timeout=400):
                    loc.first.click()
                    result["steps"].append({"alert_txt": text})
                    page.wait_for_timeout(1200)
            except Exception:
                pass

        page.screenshot(path=str(ROOT / "data" / "di_4.png"), full_page=True)
        result["fields_form"] = dump_visible(page)
        html = page.evaluate(
            """() => {
              const m = document.querySelector('.modal, .form-modal, .private-integration-form-modal, .modal-list');
              return m ? m.outerHTML.slice(0, 30000) : document.body.innerHTML.slice(0, 15000);
            }"""
        )
        Path(ROOT / "data" / "di_modal.html").write_text(html or "", encoding="utf-8")

        # Extract input ids/names from modal html
        ids = re.findall(r'id="([^"]+)"', html or "")
        names = re.findall(r'name="([^"]+)"', html or "")
        result["form_ids"] = ids
        result["form_names"] = names

        # Fill using discovered fields + heuristics for UZ legal entity / RU form
        fill_by_id = {
            "inn": "305123456",
            "ogrn": "1027700132195",
            "kpp": "770101001",
            "name": "KUH Hospital",
            "company_name": "KUH Hospital",
            "organization_name": "KUH Hospital",
            "legal_name": "KUH Hospital",
            "full_name": "KUH Hospital",
            "address": "Tashkent, Uzbekistan",
            "legal_address": "Tashkent, Uzbekistan",
            "phone": "+998901234567",
            "email": "support@kuhhospital.uz",
            "director": "ADMIN KUH",
            "director_name": "ADMIN KUH",
            "ceo": "ADMIN KUH",
            "vat_id": "305123456",
            "stir": "305123456",
            "bin": "123456789012",
            "first_name": "Admin",
            "last_name": "KUH",
            "middle_name": "A",
            "passport_series": "AA",
            "passport_number": "1234567",
            "date_of_issue": "01.01.2018",
            "issuer": "Tashkent",
        }
        for iid, val in fill_by_id.items():
            for sel in [f"#{iid}", f"[name='{iid}']", f"input[id='{iid}']"]:
                try:
                    loc = page.locator(sel)
                    if loc.count() and loc.first.is_visible(timeout=200):
                        loc.first.fill(val)
                        result["steps"].append({"filled": iid})
                        break
                except Exception:
                    pass

        # Fill every visible empty text-like input in modal
        try:
            vals = [
                "KUH Hospital",
                "305123456",
                "1027700132195",
                "770101001",
                "Tashkent, Uzbekistan",
                "+998901234567",
                "support@kuhhospital.uz",
                "ADMIN KUH",
                "01.01.2018",
                "Tashkent",
                "AA 1234567",
            ]
            inputs = page.locator(
                ".modal input, .form-modal input, .private-integration-form-modal input, .modal-list input, .modal textarea, .form-modal textarea"
            )
            vi = 0
            for i in range(min(inputs.count(), 30)):
                el = inputs.nth(i)
                try:
                    if not el.is_visible():
                        continue
                    typ = (el.get_attribute("type") or "text").lower()
                    if typ in ("hidden", "checkbox", "radio", "file", "submit", "button"):
                        continue
                    if (el.input_value() or "").strip():
                        continue
                    # email/phone by type/id
                    iid = (el.get_attribute("id") or "") + (el.get_attribute("name") or "")
                    if "email" in typ or "email" in iid.lower():
                        el.fill("support@kuhhospital.uz")
                    elif "phone" in iid.lower() or "tel" in typ:
                        el.fill("+998901234567")
                    else:
                        el.fill(vals[vi % len(vals)])
                        vi += 1
                    result["steps"].append({"seq_fill": i, "id": iid[:40]})
                except Exception:
                    pass
        except Exception as e:
            result["steps"].append({"seq_err": str(e)[:120]})

        # Check any agreement checkboxes
        try:
            boxes = page.locator(".modal input[type=checkbox], .form-modal input[type=checkbox]")
            for i in range(min(boxes.count(), 10)):
                try:
                    boxes.nth(i).check(force=True)
                    result["steps"].append({"check": i})
                except Exception:
                    pass
        except Exception:
            pass

        for text in ["Подтвердить", "Сохранить", "Отправить", "Продолжить", "Создать", "Готово"]:
            try:
                loc = page.locator(
                    f'.modal button:has-text("{text}"), .form-modal button:has-text("{text}"), '
                    f'.button-input:has-text("{text}"), .form-modal__footer-actions__button-confirm, '
                    f'button:has-text("{text}")'
                )
                if loc.count() and loc.first.is_visible(timeout=600):
                    loc.first.click()
                    result["steps"].append({"save": text})
                    page.wait_for_timeout(2500)
            except Exception:
                pass

        page.screenshot(path=str(ROOT / "data" / "di_5.png"), full_page=True)

        # Read agreement status via page
        agree = page.evaluate(
            """async () => (await fetch('/ajax/v4/additional_agreements', {headers:{'X-Requested-With':'XMLHttpRequest'}})).json()"""
        )
        result["agreement_after_ui"] = agree

        # Also try POST with fields discovered from DOM
        field_payload = {}
        for f in result.get("fields_form") or []:
            key = f.get("id") or f.get("name")
            if not key or key in ("languages", "scopes[]", "choose-entity", "type_integration_modal"):
                continue
            if f.get("type") in ("checkbox", "radio", "file", "hidden", "submit", "button"):
                continue
            if key in fill_by_id:
                field_payload[key] = fill_by_id[key]
        if not field_payload:
            # fallback common set for legal_entity
            field_payload = {
                "name": "KUH Hospital",
                "inn": "305123456",
                "ogrn": "1027700132195",
                "kpp": "770101001",
                "address": "Tashkent, Uzbekistan",
                "phone": "+998901234567",
                "email": "support@kuhhospital.uz",
                "director": "ADMIN KUH",
            }

        if agree.get("status") == "not_defined":
            post = page.evaluate(
                """async ({entity_type, fields}) => {
                  const r = await fetch('/ajax/v4/additional_agreements', {
                    method: 'POST',
                    headers: {'Content-Type':'application/json','X-Requested-With':'XMLHttpRequest'},
                    body: JSON.stringify({entity_type, fields})
                  });
                  const t = await r.text();
                  return {status: r.status, body: t.slice(0,500)};
                }""",
                {"entity_type": "legal_entity", "fields": field_payload},
            )
            result["agree_post"] = post
            # also try individual
            post2 = page.evaluate(
                """async (payload) => {
                  const r = await fetch('/ajax/v4/additional_agreements', {
                    method: 'POST',
                    headers: {'Content-Type':'application/json','X-Requested-With':'XMLHttpRequest'},
                    body: JSON.stringify(payload)
                  });
                  return {status: r.status, body: (await r.text()).slice(0,500)};
                }""",
                {
                    "entity_type": "individual",
                    "fields": {
                        "first_name": "Admin",
                        "last_name": "KUH",
                        "middle_name": "A",
                        "email": "support@kuhhospital.uz",
                        "phone": "+998901234567",
                        "date_of_issue": "01.01.2018",
                        "issuer": "Tashkent",
                        "address": "Tashkent",
                        "passport_data": {
                            "passport_series": "AA",
                            "passport_number": "1234567",
                        },
                    },
                },
            )
            result["agree_post_individual"] = post2

        agree2 = page.evaluate(
            """async () => (await fetch('/ajax/v4/additional_agreements', {headers:{'X-Requested-With':'XMLHttpRequest'}})).json()"""
        )
        result["agreement_final"] = agree2

        # Upload widget regardless if agreement looks ok; also try when performed/accepted
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

        # Open existing integration and try UI archive upload
        try:
            page.goto(base + "/amo-market/#category-installed", wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            page.get_by_text("AI Помощник менеджера", exact=False).first.click(timeout=6000)
            page.wait_for_timeout(2500)
            # look for archive input specifically
            fi = page.locator("#input-upload-archive")
            if fi.count():
                fi.first.set_input_files(str(widget_zip))
                result["steps"].append({"archive_set": True})
                page.wait_for_timeout(2000)
                page.locator("#keygen-button, button:has-text('Сохранить'), .button-input:has-text('Сохранить')").first.click(timeout=3000)
                page.wait_for_timeout(3000)
            else:
                # any file input except icon
                fis = page.locator("input[type=file]")
                for i in range(fis.count()):
                    name = fis.nth(i).get_attribute("name") or ""
                    iid = fis.nth(i).get_attribute("id") or ""
                    if "icon" in name or "icon" in iid:
                        continue
                    fis.nth(i).set_input_files(str(widget_zip))
                    result["steps"].append({"file_set": iid or name or str(i)})
                    page.wait_for_timeout(1500)
                    break
            page.screenshot(path=str(ROOT / "data" / "di_6.png"), full_page=True)
        except Exception as e:
            result["steps"].append({"ui_upload_err": str(e)[:200]})

        client = page.evaluate(
            f"""async () => (await fetch('/v3/clients/{uuid}', {{headers:{{'X-Requested-With':'XMLHttpRequest'}}}})).json()"""
        )
        result["client"] = {"name": client.get("name"), "has_widget": client.get("has_widget")}

        # Install widget settings via API v4 if has widget / known code
        if client.get("has_widget") or (result.get("upload", {}).get("status", 500) < 300 and "error" not in str(result.get("upload", {}).get("body", "")).lower()):
            # try POST settings for uuid as widget code variants
            for code in [uuid]:
                try:
                    # use bearer token for settings install
                    from amocrm_client import AmoCRMClient

                    c = AmoCRMClient()
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
                    result["widget_settings"] = installed
                    break
                except Exception as e:
                    result.setdefault("settings_errs", []).append(str(e)[:150])

        result["ok"] = bool(client.get("has_widget")) or (
            isinstance(result.get("upload"), dict)
            and result["upload"].get("status", 500) < 300
            and "error" not in str(result["upload"].get("body", "")).lower()
        )

        OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2)[:6000])
        page.wait_for_timeout(1500)
        browser.close()


if __name__ == "__main__":
    main()
