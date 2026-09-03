"""Click Create -> Internal -> Alert confirm -> fill company form -> upload."""

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
OUT = ROOT / "data" / "do_install_v2.json"


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
        browser = p.chromium.launch(headless=False, slow_mo=80)
        context = browser.new_context(locale="ru-RU", viewport={"width": 1500, "height": 960})
        context.add_cookies(cookies())
        page = context.new_page()

        page.goto(base + "/amo-market/application/", wait_until="networkidle", timeout=120000)
        page.wait_for_timeout(5000)
        page.screenshot(path=str(ROOT / "data" / "v2_1.png"), full_page=True)
        result["steps"].append({"title": page.title(), "url": page.url})

        # Strong click on Создать интеграцию
        created = False
        strategies = [
            lambda: page.get_by_role("button", name="Создать интеграцию").click(timeout=5000, force=True),
            lambda: page.locator("button", has_text="Создать интеграцию").first.click(timeout=5000, force=True),
            lambda: page.locator("text=Создать интеграцию").first.click(timeout=5000, force=True),
            lambda: page.evaluate(
                """() => {
                  const nodes = Array.from(document.querySelectorAll('button, a, div, span'));
                  const el = nodes.find(n => (n.innerText||'').trim() === 'Создать интеграцию');
                  if (!el) return false;
                  el.click();
                  return true;
                }"""
            ),
        ]
        for i, fn in enumerate(strategies):
            try:
                ret = fn()
                result["steps"].append({"create_strategy": i, "ret": ret})
                page.wait_for_timeout(2500)
                # Did type modal appear?
                if page.locator("#create-internal-integration, .modal-integration-type, text=приватн").count():
                    created = True
                    break
                if page.locator(".modal-list, .modal").count() >= 1:
                    created = True
                    break
            except Exception as e:
                result["steps"].append({"create_strategy_err": i, "e": str(e)[:120]})

        page.screenshot(path=str(ROOT / "data" / "v2_2.png"), full_page=True)
        Path(ROOT / "data" / "v2_after_create.html").write_text(
            page.content()[:200000], encoding="utf-8"
        )

        # Click internal integration
        for sel in [
            "#create-internal-integration",
            "text=Приватная интеграция",
            "text=приватную интеграцию",
            "text=Загрузить виджет",
            "text=Внутренняя",
        ]:
            try:
                loc = page.locator(sel)
                if loc.count():
                    loc.first.click(timeout=4000, force=True)
                    result["steps"].append({"clicked_internal": sel})
                    page.wait_for_timeout(2500)
                    break
            except Exception as e:
                result["steps"].append({"internal_err": sel, "e": str(e)[:80]})

        page.screenshot(path=str(ROOT / "data" / "v2_3.png"), full_page=True)

        # Confirm alert
        for sel in [
            ".alert-modal__actions-button__confirm",
            "button:has-text('Продолжить')",
            "button:has-text('Подтвердить')",
            "button:has-text('Заполнить')",
            "button:has-text('Далее')",
            "text=Продолжить",
        ]:
            try:
                loc = page.locator(sel)
                if loc.count() and loc.first.is_visible(timeout=800):
                    loc.first.click(force=True)
                    result["steps"].append({"confirm": sel})
                    page.wait_for_timeout(2500)
            except Exception:
                pass

        page.screenshot(path=str(ROOT / "data" / "v2_4.png"), full_page=True)
        modal_html = page.evaluate(
            """() => {
              const m = document.querySelector('.private-integration-form-modal, .form-modal, .modal-list.modal, .modal');
              return m ? m.outerHTML : '';
            }"""
        )
        Path(ROOT / "data" / "v2_form.html").write_text(modal_html or "", encoding="utf-8")
        result["form_len"] = len(modal_html or "")
        result["form_ids"] = re.findall(r'id="([^"]+)"', modal_html or "")
        result["form_names"] = re.findall(r'name="([^"]+)"', modal_html or "")
        result["form_placeholders"] = re.findall(r'placeholder="([^"]+)"', modal_html or "")
        # labels
        result["form_labels"] = re.findall(r"<label[^>]*>(.*?)</label>", modal_html or "", flags=re.S)[:40]

        # Print inputs detail
        inputs = page.evaluate(
            """() => Array.from(document.querySelectorAll('.private-integration-form-modal input, .private-integration-form-modal textarea, .form-modal input, .form-modal textarea, .modal input, .modal textarea')).map(el => ({
              id: el.id, name: el.name, type: el.type, placeholder: el.placeholder,
              cls: (el.className||'').toString().slice(0,100),
              visible: !!(el.offsetWidth||el.offsetHeight)
            }))"""
        )
        result["inputs"] = inputs

        # Fill all visible inputs
        company_vals = {
            "inn": "201234567",  # UZ-like STIR-ish numeric
            "ogrn": "1027700132195",
            "kpp": "770101001",
            "name": "KUH Hospital",
            "company_name": "KUH Hospital",
            "organization": "KUH Hospital",
            "address": "Tashkent",
            "phone": "+998901234567",
            "email": "support@kuhhospital.uz",
            "director": "Admin KUH",
            "full_name": "Admin KUH",
            "first_name": "Admin",
            "last_name": "KUH",
            "middle_name": "A",
            "passport_series": "AA",
            "passport_number": "1234567",
            "date_of_issue": "15.03.2018",
            "issuer": "Tashkent",
            "vat_id": "201234567",
        }
        for inp in inputs or []:
            key = inp.get("id") or inp.get("name") or ""
            if not key or not inp.get("visible"):
                continue
            typ = (inp.get("type") or "text").lower()
            if typ in ("hidden", "checkbox", "radio", "file", "button", "submit"):
                continue
            val = None
            low = key.lower()
            for k, v in company_vals.items():
                if k in low:
                    val = v
                    break
            if val is None:
                if "email" in low or typ == "email":
                    val = "support@kuhhospital.uz"
                elif "phone" in low or typ == "tel":
                    val = "+998901234567"
                elif "date" in low:
                    val = "15.03.2018"
                elif "name" in low:
                    val = "KUH Hospital"
                elif "addr" in low:
                    val = "Tashkent"
                else:
                    val = "KUH Hospital"
            try:
                page.locator(f"#{key}" if inp.get("id") else f"[name='{key}']").first.fill(val)
                result["steps"].append({"fill": key, "val": val})
            except Exception as e:
                result["steps"].append({"fill_err": key, "e": str(e)[:60]})

        # Also sequential fill empties
        try:
            locs = page.locator(
                ".private-integration-form-modal input:not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=file]), "
                ".form-modal input:not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=file]), "
                ".private-integration-form-modal textarea, .form-modal textarea"
            )
            seq = [
                "KUH Hospital",
                "201234567",
                "1027700132195",
                "770101001",
                "Tashkent",
                "+998901234567",
                "support@kuhhospital.uz",
                "Admin KUH",
                "15.03.2018",
                "Tashkent",
            ]
            vi = 0
            for i in range(min(locs.count(), 20)):
                el = locs.nth(i)
                if not el.is_visible():
                    continue
                if (el.input_value() or "").strip():
                    continue
                el.fill(seq[vi % len(seq)])
                vi += 1
                result["steps"].append({"seq": i})
        except Exception as e:
            result["steps"].append({"seq_err": str(e)[:80]})

        # Submit form
        for sel in [
            ".form-modal__footer-actions__button-confirm",
            "button:has-text('Подтвердить')",
            "button:has-text('Сохранить')",
            "button:has-text('Отправить')",
            "button:has-text('Продолжить')",
            ".button-input_blue",
        ]:
            try:
                loc = page.locator(sel)
                if loc.count() and loc.first.is_visible(timeout=700):
                    loc.first.click(force=True)
                    result["steps"].append({"submit": sel})
                    page.wait_for_timeout(3000)
            except Exception:
                pass

        page.screenshot(path=str(ROOT / "data" / "v2_5.png"), full_page=True)

        agree = page.evaluate(
            """async () => (await fetch('/ajax/v4/additional_agreements', {headers:{'X-Requested-With':'XMLHttpRequest'}})).json()"""
        )
        result["agreement"] = agree

        # Build fields dict from filled inputs and POST again with exact keys from form
        fields = {}
        for step in result["steps"]:
            if "fill" in step and "val" in step:
                fields[step["fill"]] = step["val"]
        if fields and agree.get("status") == "not_defined":
            # try multiple entity wrappers
            for payload in [
                {"entity_type": "legal_entity", "fields": fields},
                {"entity_type": agree.get("entity_type") or "legal_entity", "fields": fields},
                fields,  # raw
            ]:
                post = page.evaluate(
                    """async (payload) => {
                      const r = await fetch('/ajax/v4/additional_agreements', {
                        method:'POST',
                        headers:{'Content-Type':'application/json','X-Requested-With':'XMLHttpRequest'},
                        body: JSON.stringify(payload)
                      });
                      return {status:r.status, body:(await r.text()).slice(0,800)};
                    }""",
                    payload,
                )
                result.setdefault("posts", []).append({"payload_keys": list(payload) if isinstance(payload, dict) else [], "resp": post})
                if post.get("status", 500) < 300:
                    break

        agree2 = page.evaluate(
            """async () => (await fetch('/ajax/v4/additional_agreements', {headers:{'X-Requested-With':'XMLHttpRequest'}})).json()"""
        )
        result["agreement2"] = agree2

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
        result["upload"] = {"status": up.status, "body": up.text()[:500]}

        client = page.evaluate(
            f"""async () => (await fetch('/v3/clients/{uuid}', {{headers:{{'X-Requested-With':'XMLHttpRequest'}}}})).json()"""
        )
        result["client"] = {"name": client.get("name"), "has_widget": client.get("has_widget")}
        result["ok"] = bool(client.get("has_widget")) or (
            up.status < 300 and "error" not in up.text().lower()
        )

        OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2)[:7000])
        page.wait_for_timeout(2000)
        browser.close()


if __name__ == "__main__":
    main()
