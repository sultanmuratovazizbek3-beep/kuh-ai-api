"""Inspect header buttons near WEB HOOKS to find Create integration control."""

from __future__ import annotations

import json
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


def main():
    load_dotenv(ROOT / ".env")
    base = "https://kuhhospital.amocrm.ru"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(locale="ru-RU", viewport={"width": 1500, "height": 960})
        context.add_cookies(cookies())
        page = context.new_page()
        page.goto(base + "/amo-market/application/", wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(10000)
        page.screenshot(path=str(ROOT / "data" / "fb_1.png"), full_page=True)

        info = page.evaluate(
            """() => {
              const out = {webhooks:null, headerButtons:[], allButtons:[], cssContents:[]};
              // find WEB HOOKS
              const all=[...document.querySelectorAll('button, a, div, span')];
              const wh = all.find(n => /WEB\\s*HOOKS/i.test(n.innerText||''));
              if (wh) {
                const r=wh.getBoundingClientRect();
                out.webhooks={text:(wh.innerText||'').slice(0,40), x:r.x, y:r.y, w:r.width, h:r.height, tag:wh.tagName, cls:(wh.className||'').toString().slice(0,100)};
                // siblings / parent children
                const parent = wh.parentElement;
                if (parent) {
                  out.parentChildren=[...parent.children].map(n=>{
                    const rr=n.getBoundingClientRect();
                    return {tag:n.tagName, text:(n.innerText||'').replace(/\\s+/g,' ').trim().slice(0,60),
                      cls:(n.className||'').toString().slice(0,80),
                      x:Math.round(rr.x+rr.width/2), y:Math.round(rr.y+rr.height/2),
                      html:n.outerHTML.slice(0,300)};
                  });
                }
              }
              // all header-area buttons (y < 120)
              out.headerButtons=[...document.querySelectorAll('button, [role=button], .button-input, a')].map(n=>{
                const r=n.getBoundingClientRect();
                if(r.y>140 || r.width<5) return null;
                return {tag:n.tagName, text:(n.innerText||'').replace(/\\s+/g,' ').trim().slice(0,80),
                  aria:n.getAttribute('aria-label'), title:n.getAttribute('title'),
                  cls:(n.className||'').toString().slice(0,100),
                  x:Math.round(r.x+r.width/2), y:Math.round(r.y+r.height/2), w:Math.round(r.width), h:Math.round(r.height),
                  html:n.outerHTML.slice(0,250)};
              }).filter(Boolean);

              // search computed style content
              for (const n of document.querySelectorAll('*')) {
                try {
                  const before=getComputedStyle(n,'::before').content;
                  const after=getComputedStyle(n,'::after').content;
                  if ((before && before!=='none' && /созд|интегр|create/i.test(before)) ||
                      (after && after!=='none' && /созд|интегр|create/i.test(after))) {
                    const r=n.getBoundingClientRect();
                    out.cssContents.push({before, after, x:r.x, y:r.y, html:n.outerHTML.slice(0,200)});
                  }
                } catch(e) {}
              }

              // raw html search
              out.htmlHasCreate = document.documentElement.innerHTML.includes('Создать интеграцию');
              out.htmlHasCreateEscaped = document.documentElement.innerHTML.includes('Создать\\u0020интеграцию') || document.documentElement.innerHTML.includes('Создать&nbsp;интеграцию');
              // find any occurrence index
              const html=document.documentElement.innerHTML;
              const idx=html.indexOf('интеграц');
              out.snippet = idx>=0 ? html.slice(Math.max(0,idx-80), idx+80) : null;
              // count
              out.countIntegr = (html.match(/интеграц/g)||[]).length;
              return out;
            }"""
        )
        Path(ROOT / "data" / "fb_info.json").write_text(
            json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(info, ensure_ascii=False, indent=2)[:8000])

        # If we found a header button to the right of webhooks, click it
        wh = info.get("webhooks")
        clicked = None
        if wh:
            # click to the right of webhooks
            x = int(wh["x"] + wh["w"] + 80)
            y = int(wh["y"] + wh["h"] / 2)
            page.mouse.click(x, y)
            clicked = {"x": x, "y": y}
            page.wait_for_timeout(2500)
            page.screenshot(path=str(ROOT / "data" / "fb_2.png"), full_page=True)

        # Also try each header button
        for b in info.get("headerButtons") or []:
            if b["x"] > (wh["x"] if wh else 900) and b["y"] < 120:
                page.mouse.click(b["x"], b["y"])
                page.wait_for_timeout(2000)
                page.screenshot(
                    path=str(ROOT / f"data/fb_btn_{b['x']}_{b['y']}.png"), full_page=True
                )

        result = {"clicked": clicked, "modals": page.locator(".modal, .modal-list").count()}
        print(json.dumps(result, ensure_ascii=False))
        browser.close()


if __name__ == "__main__":
    main()
