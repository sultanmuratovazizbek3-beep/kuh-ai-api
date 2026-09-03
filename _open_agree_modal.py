"""Open additional agreement modal via Playwright + page JS hooks."""

from __future__ import annotations

import json
import time
from pathlib import Path

import browser_cookie3
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
COOKIE_DIR = ROOT / "data" / "_ycookies"


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
    base = "https://kuhhospital.amocrm.ru"
    result = {"steps": []}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(locale="ru-RU", viewport={"width": 1460, "height": 940})
        context.add_cookies(cookies())
        page = context.new_page()
        page.goto(base + "/amo-market/", wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(4000)

        # Try to require and open private integration alert/form
        opened = page.evaluate(
            """() => new Promise((resolve) => {
              const out = {tried: [], ok: false};
              if (typeof window.require !== 'function') {
                resolve({...out, err: 'no require'});
                return;
              }
              // Discover module ids containing private_integration
              try {
                const mods = Object.keys(window.require.s ? window.require.s.contexts._.defined : {})
                  .filter(k => /private_integration|additional_agreement/i.test(k));
                out.mods = mods.slice(0, 30);
              } catch(e) { out.mod_err = String(e); }

              const candidates = [
                '../build/transpiled/interface/account/development/private_integration_form',
                'interface/account/development/private_integration_form',
                'lib/interface/account/development/private_integration_form',
              ];
              let left = candidates.length;
              candidates.forEach((id) => {
                out.tried.push(id);
                try {
                  window.require([id], function(Mod) {
                    try {
                      const View = (Mod && (Mod.default || Mod));
                      // try alert modal first via parent marketplace methods if any
                      out.loaded = id;
                      out.ok = true;
                      // Attempt to instantiate form modal with legal_entity
                      try {
                        const v = new View({
                          account_type: 'legal_entity',
                          onModalClose: function(){},
                        });
                        out.instantiated = true;
                      } catch(e) {
                        out.inst_err = String(e).slice(0,200);
                      }
                    } catch(e) {
                      out.load_err = String(e).slice(0,200);
                    }
                    if (--left === 0) resolve(out);
                  }, function(err) {
                    out.fail = out.fail || [];
                    out.fail.push(id);
                    if (--left === 0) resolve(out);
                  });
                } catch(e) {
                  out.catch = String(e);
                  if (--left === 0) resolve(out);
                }
              });
              setTimeout(() => resolve(out), 5000);
            })"""
        )
        result["open"] = opened
        page.wait_for_timeout(2000)
        page.screenshot(path=str(ROOT / "data" / "oa_1.png"), full_page=True)

        # Also try clicking sidebar Мое приложение via role/text softer
        try:
            page.locator("text=Мое приложение").click(timeout=3000)
            page.wait_for_timeout(2500)
            result["steps"].append({"clicked_aside": True, "url": page.url})
        except Exception as e:
            # href based
            try:
                page.locator('a[href*="application"]').first.click(timeout=3000)
                page.wait_for_timeout(2500)
                result["steps"].append({"clicked_href": True, "url": page.url})
            except Exception as e2:
                result["steps"].append({"aside_err": str(e)[:80], "href_err": str(e2)[:80]})

        page.screenshot(path=str(ROOT / "data" / "oa_2.png"), full_page=True)

        # Click create
        try:
            page.get_by_role("button", name="Создать интеграцию").click(timeout=4000)
            result["steps"].append({"create_btn": True})
            page.wait_for_timeout(2500)
        except Exception as e:
            try:
                page.locator("text=Создать интеграцию").click(timeout=4000)
                result["steps"].append({"create_txt": True})
                page.wait_for_timeout(2500)
            except Exception as e2:
                result["steps"].append({"create_err": str(e2)[:120]})

        page.screenshot(path=str(ROOT / "data" / "oa_3.png"), full_page=True)

        # In type chooser pick private/internal
        for label in ["Приватная", "Виджет", "Загрузить архив", "Свой виджет", "internal"]:
            try:
                loc = page.get_by_text(label, exact=False)
                if loc.count() and loc.first.is_visible(timeout=500):
                    loc.first.click()
                    result["steps"].append({"pick": label})
                    page.wait_for_timeout(1000)
            except Exception:
                pass

        # Dump any modal
        fields = page.evaluate(
            """() => Array.from(document.querySelectorAll('.modal input, .modal textarea, .modal button, .form-modal input, .form-modal button, .modal-list input, .modal-list button')).slice(0,60).map(el => ({
              tag: el.tagName, type: el.type||'', id: el.id, name: el.name,
              text: (el.innerText||'').slice(0,60), placeholder: el.placeholder||'',
              visible: !!(el.offsetWidth||el.offsetHeight)
            }))"""
        )
        result["fields"] = fields
        html = page.evaluate(
            """() => {
              const m = document.querySelector('.modal, .form-modal, .private-integration-form-modal, .modal-list');
              return m ? m.outerHTML.slice(0, 25000) : '';
            }"""
        )
        Path(ROOT / "data" / "oa_modal.html").write_text(html or "", encoding="utf-8")
        page.screenshot(path=str(ROOT / "data" / "oa_4.png"), full_page=True)

        Path(ROOT / "data" / "oa_result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(result, ensure_ascii=False, indent=2)[:5000])
        page.wait_for_timeout(1500)
        browser.close()


if __name__ == "__main__":
    main()
