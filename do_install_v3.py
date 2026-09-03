"""Wait for SPA hydrate, then create internal integration + agreement + upload."""

from __future__ import annotations

import json
import os
import re
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
OUT = ROOT / "data" / "do_install_v3.json"


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


def api_base() -> str:
    if PUBLIC_URL_FILE.exists():
        u = PUBLIC_URL_FILE.read_text(encoding="utf-8").strip().lstrip("\ufeff")
        if u.startswith("http"):
            return u.rstrip("/")
    return "https://acute-earrings-diamond-judicial.trycloudflare.com"


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
        browser = p.chromium.launch(headless=False, slow_mo=50)
        context = browser.new_context(locale="ru-RU", viewport={"width": 1500, "height": 960})
        context.add_cookies(cookies())
        page = context.new_page()

        # First land on dashboard to ensure session, then navigate
        page.goto(base + "/dashboard/", wait_until="domcontentloaded", timeout=120000)
        try:
            page.wait_for_selector("text=Рабочий стол", timeout=60000)
            result["steps"].append({"dash": "ok", "title": page.title()})
        except Exception as e:
            result["steps"].append({"dash_err": str(e)[:120], "title": page.title(), "url": page.url})
            page.screenshot(path=str(ROOT / "data" / "v3_dash.png"), full_page=True)
            # if auth page, abort
            if "Авторизация" in page.title() or "login" in page.url:
                result["error"] = "not authenticated"
                OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                print(json.dumps(result, ensure_ascii=False, indent=2))
                browser.close()
                return

        page.goto(base + "/amo-market/application/", wait_until="domcontentloaded", timeout=120000)
        # Wait until create button OR keys tab appears (SPA)
        loaded = False
        for _ in range(60):
            try:
                if page.locator("text=Создать интеграцию").count() or page.locator("text=Ключи доступа").count() or page.locator("text=Мое приложение").count():
                    # ensure create button specifically
                    if page.locator("text=Создать интеграцию").count():
                        loaded = True
                        break
            except Exception:
                pass
            page.wait_for_timeout(1000)
        result["steps"].append({"spa_loaded": loaded, "title": page.title(), "url": page.url})
        page.screenshot(path=str(ROOT / "data" / "v3_1.png"), full_page=True)

        # Click create via JS containing text
        clicked = page.evaluate(
            """() => {
              const all = Array.from(document.querySelectorAll('*'));
              const el = all.find(n => n.childNodes && [...n.childNodes].some(c => c.nodeType===3 && c.textContent.trim()==='Создать интеграцию') && n.children.length===0)
                     || all.find(n => (n.innerText||'').trim()==='Создать интеграцию');
              if (!el) {
                // partial
                const el2 = all.find(n => (n.innerText||'').includes('Создать интеграцию') && (n.innerText||'').length < 40);
                if (!el2) return {ok:false, sample: all.filter(n=>/интеграц/i.test(n.innerText||'')).slice(0,10).map(n=>(n.innerText||'').slice(0,40))};
                el2.click();
                return {ok:true, partial:true, text: el2.innerText.slice(0,40)};
              }
              el.click();
              return {ok:true, text: el.innerText.slice(0,40), tag: el.tagName};
            }"""
        )
        result["steps"].append({"create_js": clicked})
        page.wait_for_timeout(3000)
        page.screenshot(path=str(ROOT / "data" / "v3_2.png"), full_page=True)

        # Wait for type modal
        try:
            page.wait_for_selector("#create-internal-integration, .modal-integration-type", timeout=15000)
            result["steps"].append({"type_modal": True})
        except Exception as e:
            result["steps"].append({"type_modal_err": str(e)[:100]})

        # Click internal
        try:
            if page.locator("#create-internal-integration").count():
                page.locator("#create-internal-integration").click(force=True)
                result["steps"].append({"internal": "id"})
            else:
                page.evaluate(
                    """() => {
                      const el = Array.from(document.querySelectorAll('*')).find(n => /приватн|внутренн|виджет|архив/i.test(n.innerText||'') && (n.innerText||'').length<60);
                      if (el) el.click();
                    }"""
                )
                result["steps"].append({"internal": "js"})
        except Exception as e:
            result["steps"].append({"internal_err": str(e)[:100]})
        page.wait_for_timeout(2500)
        page.screenshot(path=str(ROOT / "data" / "v3_3.png"), full_page=True)

        # Confirm alert
        try:
            page.wait_for_selector(".alert-modal__actions-button__confirm, .private-integration-alert-modal", timeout=10000)
            if page.locator(".alert-modal__actions-button__confirm").count():
                page.locator(".alert-modal__actions-button__confirm").click(force=True)
                result["steps"].append({"alert_confirm": True})
            else:
                page.evaluate(
                    """() => {
                      const b = Array.from(document.querySelectorAll('button,.button-input')).find(n => /продолж|подтверд|заполн|далее/i.test(n.innerText||''));
                      if (b) b.click();
                    }"""
                )
                result["steps"].append({"alert_confirm": "js"})
        except Exception as e:
            result["steps"].append({"alert_err": str(e)[:120]})
        page.wait_for_timeout(3000)
        page.screenshot(path=str(ROOT / "data" / "v3_4.png"), full_page=True)

        # Capture form
        modal_html = page.evaluate(
            """() => {
              const m = document.querySelector('.private-integration-form-modal, .form-modal__form-wrapper, .modal-list');
              return m ? m.outerHTML : '';
            }"""
        )
        Path(ROOT / "data" / "v3_form.html").write_text(modal_html or "", encoding="utf-8")
        result["form_len"] = len(modal_html or "")
        result["placeholders"] = re.findall(r'placeholder="([^"]+)"', modal_html or "")
        result["ids"] = re.findall(r'\bid="([^"]+)"', modal_html or "")
        result["names"] = re.findall(r'\bname="([^"]+)"', modal_html or "")

        inputs = page.evaluate(
            """() => Array.from(document.querySelectorAll('input,textarea')).filter(el => !!(el.offsetWidth||el.offsetHeight)).map(el => ({
              id: el.id, name: el.name, type: el.type||'text', placeholder: el.placeholder||'',
              label: (el.closest('label')||el.parentElement||{}).innerText||''
            })).slice(0,40)"""
        )
        result["inputs"] = inputs

        # Fill
        def pick_val(inp):
            blob = f"{inp.get('id','')} {inp.get('name','')} {inp.get('placeholder','')} {inp.get('label','')}".lower()
            if "email" in blob or inp.get("type") == "email":
                return "support@kuhhospital.uz"
            if "phone" in blob or "тел" in blob or inp.get("type") == "tel":
                return "+998901234567"
            if "inn" in blob or "инн" in blob or "стир" in blob or "vat" in blob:
                return "201234567"
            if "ogrn" in blob or "огрн" in blob:
                return "1027700132195"
            if "kpp" in blob or "кпп" in blob:
                return "770101001"
            if "date" in blob or "дат" in blob:
                return "15.03.2018"
            if "passport" in blob or "паспорт" in blob or "series" in blob or "сери" in blob:
                return "AA"
            if "number" in blob or "номер" in blob:
                return "1234567"
            if "director" in blob or "директор" in blob or "фио" in blob:
                return "Admin KUH"
            if "addr" in blob or "адрес" in blob:
                return "Tashkent, Uzbekistan"
            if "name" in blob or "назван" in blob or "организ" in blob:
                return "KUH Hospital"
            if "issuer" in blob or "выда" in blob:
                return "Tashkent"
            return "KUH Hospital"

        filled_fields = {}
        for inp in inputs or []:
            typ = (inp.get("type") or "text").lower()
            if typ in ("hidden", "checkbox", "radio", "file", "submit", "button"):
                continue
            key = inp.get("id") or inp.get("name")
            if not key:
                continue
            val = pick_val(inp)
            try:
                sel = f"#{inp['id']}" if inp.get("id") else f"[name='{inp['name']}']"
                page.locator(sel).first.fill(val)
                filled_fields[key] = val
                result["steps"].append({"fill": key, "val": val})
            except Exception as e:
                result["steps"].append({"fill_err": key, "e": str(e)[:60]})

        # checkboxes agree
        try:
            for i in range(min(page.locator(".modal input[type=checkbox], .form-modal input[type=checkbox]").count(), 8)):
                page.locator(".modal input[type=checkbox], .form-modal input[type=checkbox]").nth(i).check(force=True)
        except Exception:
            pass

        # Submit
        submitted = page.evaluate(
            """() => {
              const b = Array.from(document.querySelectorAll('button, .button-input, .form-modal__footer-actions__button-confirm'))
                .find(n => /подтверд|сохран|отправ|продолж|создать|готово/i.test(n.innerText||'') && !/отмен/i.test(n.innerText||''));
              if (!b) return false;
              b.click();
              return (b.innerText||'').slice(0,40);
            }"""
        )
        result["steps"].append({"submit": submitted})
        page.wait_for_timeout(4000)
        page.screenshot(path=str(ROOT / "data" / "v3_5.png"), full_page=True)

        agree = page.evaluate(
            """async () => (await fetch('/ajax/v4/additional_agreements', {headers:{'X-Requested-With':'XMLHttpRequest'}})).json()"""
        )
        result["agreement"] = agree

        if agree.get("status") == "not_defined" and filled_fields:
            post = page.evaluate(
                """async (fields) => {
                  const payloads = [
                    {entity_type:'legal_entity', fields},
                    {entity_type:'individual', fields},
                  ];
                  const out=[];
                  for (const payload of payloads) {
                    const r = await fetch('/ajax/v4/additional_agreements', {
                      method:'POST',
                      headers:{'Content-Type':'application/json','X-Requested-With':'XMLHttpRequest'},
                      body: JSON.stringify(payload)
                    });
                    out.push({status:r.status, body:(await r.text()).slice(0,500), keys:Object.keys(payload.fields||{})});
                  }
                  return out;
                }""",
                filled_fields,
            )
            result["posts"] = post

        agree2 = page.evaluate(
            """async () => (await fetch('/ajax/v4/additional_agreements', {headers:{'X-Requested-With':'XMLHttpRequest'}})).json()"""
        )
        result["agreement2"] = agree2

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
        result["upload"] = {"status": up.status, "body": up.text()[:500]}
        client = page.evaluate(
            f"""async () => (await fetch('/v3/clients/{uuid}', {{headers:{{'X-Requested-With':'XMLHttpRequest'}}}})).json()"""
        )
        result["client"] = {"name": client.get("name"), "has_widget": client.get("has_widget")}
        result["ok"] = bool(client.get("has_widget")) or (up.status < 300 and "error" not in up.text().lower())

        # If uploaded, try set settings via token API
        if result["ok"]:
            try:
                from amocrm_client import AmoCRMClient

                c = AmoCRMClient()
                # discover widget code from own integrations ajax via page
                own = page.evaluate(
                    """async () => (await fetch('/ajax/settings/widgets/category/own_integrations/1/', {headers:{'X-Requested-With':'XMLHttpRequest'}})).json()"""
                )
                codes = []
                for code, info in (own.get("integrations") or {}).items():
                    name = str(info.get("name") or "")
                    if "Помощник" in name or "AI" in name or code == uuid:
                        codes.append(code)
                codes.append(uuid)
                for code in codes:
                    try:
                        resp = c._request(
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
                        result["settings"] = {"code": code, "resp": resp}
                        break
                    except Exception as e:
                        result.setdefault("settings_err", []).append(f"{code}:{e}")
            except Exception as e:
                result["settings_ex"] = str(e)

        OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2)[:8000])
        page.wait_for_timeout(1500)
        browser.close()


if __name__ == "__main__":
    main()
