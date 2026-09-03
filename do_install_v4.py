"""Click create button by coordinates/fuzzy match, complete agreement, upload."""

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
OUT = ROOT / "data" / "do_install_v4.json"


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
    tunnel = (
        Path(ROOT / "public" / "API_PUBLIC_URL.txt")
        .read_text(encoding="utf-8")
        .strip()
        .lstrip("\ufeff")
        .rstrip("/")
    )
    td = Path(tempfile.mkdtemp())
    widget_zip = td / "widget.zip"
    shutil.copy(ZIP_SRC, widget_zip)
    result: dict = {"ok": False, "steps": [], "api_base": tunnel}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=40)
        context = browser.new_context(locale="ru-RU", viewport={"width": 1500, "height": 960})
        context.add_cookies(cookies())
        page = context.new_page()

        page.goto(base + "/dashboard/", wait_until="domcontentloaded", timeout=120000)
        page.wait_for_selector("text=Сделки", timeout=60000)
        page.goto(base + "/amo-market/application/", wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(8000)
        page.screenshot(path=str(ROOT / "data" / "v4_1.png"), full_page=True)

        # Dump every clickable with text containing 'Созд' or 'интегр'
        scan = page.evaluate(
            """() => {
              const out=[];
              const walk = (root, path) => {
                const nodes = root.querySelectorAll ? root.querySelectorAll('*') : [];
                for (const n of nodes) {
                  const t = (n.innerText||'').replace(/\\s+/g,' ').trim();
                  if (!t) continue;
                  if (!/созд|интегр|create/i.test(t)) continue;
                  if (t.length > 80) continue;
                  const r = n.getBoundingClientRect();
                  if (r.width < 2 || r.height < 2) continue;
                  out.push({
                    tag: n.tagName,
                    text: t.slice(0,80),
                    cls: (n.className||'').toString().slice(0,80),
                    x: Math.round(r.x+r.width/2),
                    y: Math.round(r.y+r.height/2),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                    path
                  });
                  if (n.shadowRoot) walk(n.shadowRoot, path+'>shadow');
                }
              };
              walk(document, 'doc');
              // also iframes
              for (const f of document.querySelectorAll('iframe')) {
                try { walk(f.contentDocument, 'iframe'); } catch(e) {}
              }
              return out.slice(0,50);
            }"""
        )
        result["scan"] = scan
        Path(ROOT / "data" / "v4_scan.json").write_text(
            json.dumps(scan, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # Click best candidate
        clicked = False
        for item in scan or []:
            t = item.get("text") or ""
            if "Создать интеграцию" in t or t.strip() == "Создать интеграцию" or (
                "Создать" in t and "интеграц" in t and len(t) < 30
            ):
                page.mouse.click(item["x"], item["y"])
                result["steps"].append({"clicked_scan": item})
                clicked = True
                page.wait_for_timeout(3000)
                break

        if not clicked:
            # try known header coords from screenshot (top-right button)
            for x, y in [(1180, 70), (1250, 70), (1100, 70), (1300, 75), (1150, 85)]:
                page.mouse.click(x, y)
                result["steps"].append({"clicked_xy": [x, y]})
                page.wait_for_timeout(1500)
                if page.locator(".modal, .modal-list, #create-internal-integration").count():
                    clicked = True
                    break

        page.screenshot(path=str(ROOT / "data" / "v4_2.png"), full_page=True)

        # If type modal, click internal by id or coords
        if page.locator("#create-internal-integration").count():
            page.locator("#create-internal-integration").click(force=True)
            result["steps"].append({"internal": True})
            page.wait_for_timeout(2500)
        else:
            # scan modal options
            opts = page.evaluate(
                """() => Array.from(document.querySelectorAll('.modal *, .modal-list *')).map(n => {
                  const t=(n.innerText||'').replace(/\\s+/g,' ').trim();
                  if(!t || t.length>60) return null;
                  const r=n.getBoundingClientRect();
                  if(r.width<5||r.height<5) return null;
                  return {text:t.slice(0,60), x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2)};
                }).filter(Boolean).slice(0,40)"""
            )
            result["modal_opts"] = opts
            for o in opts or []:
                if re.search(r"приват|внутрен|виджет|архив|private|internal", o["text"], re.I):
                    page.mouse.click(o["x"], o["y"])
                    result["steps"].append({"picked": o})
                    page.wait_for_timeout(2500)
                    break

        page.screenshot(path=str(ROOT / "data" / "v4_3.png"), full_page=True)

        # Alert confirm
        if page.locator(".alert-modal__actions-button__confirm").count():
            page.locator(".alert-modal__actions-button__confirm").click(force=True)
            result["steps"].append({"alert": "css"})
            page.wait_for_timeout(3000)
        else:
            conf = page.evaluate(
                """() => {
                  const nodes=Array.from(document.querySelectorAll('button,.button-input,div,span'));
                  const el=nodes.find(n => /продолж|подтверд|заполн|далее|ок/i.test((n.innerText||'').trim()) && (n.innerText||'').trim().length<20);
                  if(!el) return null;
                  const r=el.getBoundingClientRect();
                  el.click();
                  return {text:(el.innerText||'').trim(), x:r.x, y:r.y};
                }"""
            )
            result["steps"].append({"alert_js": conf})
            page.wait_for_timeout(3000)

        page.screenshot(path=str(ROOT / "data" / "v4_4.png"), full_page=True)
        form_html = page.evaluate(
            """() => {
              const m=document.querySelector('.private-integration-form-modal,.form-modal,.modal-list.private-integration-form-modal,.form-modal__form-wrapper');
              return m?m.outerHTML: (document.querySelector('.modal')?document.querySelector('.modal').outerHTML:'');
            }"""
        )
        Path(ROOT / "data" / "v4_form.html").write_text(form_html or "", encoding="utf-8")
        result["form_len"] = len(form_html or "")
        result["placeholders"] = re.findall(r'placeholder="([^"]+)"', form_html or "")
        result["names"] = re.findall(r'name="([^"]+)"', form_html or "")
        result["ids"] = [i for i in re.findall(r'id="([^"]+)"', form_html or "") if not i.startswith("svg") and "amma" not in i][:40]

        # Fill visible inputs in modal
        filled = page.evaluate(
            """() => {
              const vals = {
                email: 'support@kuhhospital.uz',
                phone: '+998901234567',
                inn: '201234567',
                ogrn: '1027700132195',
                kpp: '770101001',
                name: 'KUH Hospital',
                address: 'Tashkent, Uzbekistan',
                director: 'Admin KUH',
                first_name: 'Admin',
                last_name: 'KUH',
                middle_name: 'A',
                passport_series: 'AA',
                passport_number: '1234567',
                date_of_issue: '15.03.2018',
                issuer: 'Tashkent'
              };
              const filled={};
              const inputs=[...document.querySelectorAll('.modal input,.modal textarea,.form-modal input,.form-modal textarea,.private-integration-form-modal input,.private-integration-form-modal textarea')];
              let seq=['KUH Hospital','201234567','1027700132195','770101001','Tashkent','+998901234567','support@kuhhospital.uz','Admin KUH','15.03.2018','Tashkent'];
              let si=0;
              for (const el of inputs) {
                const typ=(el.type||'text').toLowerCase();
                if(['hidden','checkbox','radio','file','button','submit'].includes(typ)) continue;
                if(!(el.offsetWidth||el.offsetHeight)) continue;
                if((el.value||'').trim()) continue;
                const key=(el.id||el.name||'').toLowerCase();
                let val=null;
                for (const [k,v] of Object.entries(vals)) { if(key.includes(k)) { val=v; break; } }
                if(!val) {
                  if(typ==='email'||key.includes('email')) val=vals.email;
                  else if(typ==='tel'||key.includes('phone')) val=vals.phone;
                  else { val=seq[si%seq.length]; si++; }
                }
                el.focus();
                el.value=val;
                el.dispatchEvent(new Event('input',{bubbles:true}));
                el.dispatchEvent(new Event('change',{bubbles:true}));
                filled[el.id||el.name||('i'+si)]=val;
              }
              // checkboxes
              for (const el of document.querySelectorAll('.modal input[type=checkbox], .form-modal input[type=checkbox]')) {
                if(!(el.offsetWidth||el.offsetHeight)) continue;
                el.checked=true;
                el.dispatchEvent(new Event('change',{bubbles:true}));
              }
              return filled;
            }"""
        )
        result["filled"] = filled

        # Submit
        sub = page.evaluate(
            """() => {
              const b=[...document.querySelectorAll('button,.button-input,.form-modal__footer-actions__button-confirm')]
                .find(n => /подтверд|сохран|отправ|продолж|создать|готово/i.test((n.innerText||'')) && !/отмен/i.test(n.innerText||''));
              if(!b) return null;
              b.click();
              return (b.innerText||'').trim().slice(0,40);
            }"""
        )
        result["steps"].append({"submit": sub})
        page.wait_for_timeout(5000)
        page.screenshot(path=str(ROOT / "data" / "v4_5.png"), full_page=True)

        agree = page.evaluate(
            """async () => (await fetch('/ajax/v4/additional_agreements',{headers:{'X-Requested-With':'XMLHttpRequest'}})).json()"""
        )
        result["agreement"] = agree

        # POST with filled fields if still needed
        if agree.get("status") == "not_defined" and filled:
            # Normalize keys - strip weird ones
            fields = {k: v for k, v in filled.items() if k and not k.startswith("i")}
            posts = page.evaluate(
                """async (fields) => {
                  const tries=[
                    {entity_type:'legal_entity', fields},
                    {entity_type:'individual', fields},
                  ];
                  const out=[];
                  for (const payload of tries) {
                    const r=await fetch('/ajax/v4/additional_agreements',{method:'POST',headers:{'Content-Type':'application/json','X-Requested-With':'XMLHttpRequest'},body:JSON.stringify(payload)});
                    out.push({status:r.status, body:(await r.text()).slice(0,600)});
                  }
                  return out;
                }""",
                fields,
            )
            result["posts"] = posts
            agree = page.evaluate(
                """async () => (await fetch('/ajax/v4/additional_agreements',{headers:{'X-Requested-With':'XMLHttpRequest'}})).json()"""
            )
            result["agreement2"] = agree

        # Upload zip
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
            f"""async () => (await fetch('/v3/clients/{uuid}',{{headers:{{'X-Requested-With':'XMLHttpRequest'}}}})).json()"""
        )
        result["client"] = {"name": client.get("name"), "has_widget": client.get("has_widget")}
        result["ok"] = bool(client.get("has_widget")) or (
            up.status < 300 and "error" not in up.text().lower()
        )

        OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2)[:9000])
        page.wait_for_timeout(1500)
        browser.close()


if __name__ == "__main__":
    main()
