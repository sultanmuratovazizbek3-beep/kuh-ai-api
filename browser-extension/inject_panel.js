/* KUH AI panel — can be injected via CDP or bookmarklet */
(function () {
  if (window.__KUH_AI_V3__) return;
  window.__KUH_AI_V3__ = true;

  var API = "http://127.0.0.1:8090";

  function leadId() {
    var m = (location.pathname + " " + location.href).match(/leads\/detail\/(\d+)/i);
    return m ? parseInt(m[1], 10) : null;
  }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function css() {
    if (document.getElementById("kuh-ai-style-v3")) return;
    var s = document.createElement("style");
    s.id = "kuh-ai-style-v3";
    s.textContent =
      "#kuh-ai-fab{position:fixed!important;bottom:28px!important;right:28px!important;z-index:2147483647!important;" +
      "background:#2563eb!important;color:#fff!important;border:0!important;border-radius:999px!important;" +
      "padding:14px 20px!important;font:800 14px/1 system-ui,sans-serif!important;cursor:pointer!important;" +
      "box-shadow:0 10px 30px rgba(37,99,235,.55)!important}" +
      "#kuh-ai-root{position:fixed!important;top:70px!important;right:16px!important;width:370px!important;" +
      "max-height:calc(100vh - 90px)!important;z-index:2147483646!important;display:flex!important;flex-direction:column!important;" +
      "background:#fff!important;color:#0f172a!important;border:2px solid #2563eb!important;border-radius:14px!important;" +
      "box-shadow:0 18px 50px rgba(0,0,0,.4)!important;font:12px/1.4 system-ui,sans-serif!important;overflow:hidden!important}" +
      "#kuh-ai-root .hd{background:linear-gradient(135deg,#1d4ed8,#0ea5e9)!important;color:#fff!important;padding:10px 12px!important;" +
      "display:flex!important;align-items:center!important;gap:8px!important;font-weight:800!important}" +
      "#kuh-ai-root .bd{padding:10px 12px!important;overflow:auto!important;flex:1!important;background:#fff!important}" +
      "#kuh-ai-root .btn{border:1px solid #e2e8f0!important;background:#f8fafc!important;border-radius:8px!important;" +
      "padding:8px!important;cursor:pointer!important;font-weight:700!important;flex:1!important}" +
      "#kuh-ai-root .btn.p{background:#2563eb!important;color:#fff!important;border-color:#2563eb!important}" +
      "#kuh-ai-root .btn.note{background:#0f766e!important;color:#fff!important;border-color:#0f766e!important}" +
      "#kuh-ai-root .btn:disabled{opacity:.55!important;cursor:wait!important}" +
      "#kuh-ai-root .blk{border:1px solid #e2e8f0!important;border-radius:8px!important;padding:8px!important;margin:8px 0!important}" +
      "#kuh-ai-root .rep{background:#eff6ff!important;border-left:3px solid #2563eb!important;padding:6px 8px!important;" +
      "margin:5px 0!important;cursor:pointer!important;white-space:pre-wrap!important;border-radius:0 6px 6px 0!important}" +
      "#kuh-ai-root .sc{display:inline-block!important;padding:4px 10px!important;border-radius:999px!important;color:#fff!important;font-weight:800!important}" +
      "#kuh-ai-root .g{background:#16a34a!important}#kuh-ai-root .m{background:#d97706!important}#kuh-ai-root .b{background:#dc2626!important}" +
      "#kuh-ai-root ul{margin:4px 0 0 16px!important;padding:0!important}#kuh-ai-root li{margin:3px 0!important;white-space:pre-wrap!important}";
    document.documentElement.appendChild(s);
  }

  function ensureUi() {
    css();
    if (!document.getElementById("kuh-ai-fab")) {
      var fab = document.createElement("button");
      fab.id = "kuh-ai-fab";
      fab.type = "button";
      fab.textContent = "KUH AI";
      fab.onclick = function () {
        var r = ensurePanel();
        r.style.display = "flex";
        analyze();
      };
      document.documentElement.appendChild(fab);
    }
    return ensurePanel();
  }

  function ensurePanel() {
    var root = document.getElementById("kuh-ai-root");
    if (root) return root;
    root = document.createElement("div");
    root.id = "kuh-ai-root";
    root.innerHTML =
      '<div class="hd"><span style="flex:1">KUH AI · помощник</span>' +
      '<button type="button" id="kuh-ai-x" style="border:0;background:rgba(255,255,255,.25);color:#fff;border-radius:6px;padding:4px 8px;cursor:pointer">X</button></div>' +
      '<div class="bd">' +
      '<div style="display:flex;gap:8px;align-items:center;margin-bottom:8px"><span class="sc m" id="kuh-sc">—/10</span>' +
      '<span id="kuh-lead" style="color:#64748b">…</span></div>' +
      '<div id="kuh-st" style="color:#64748b;font-size:11px;margin-bottom:8px">Готов</div>' +
      '<div style="display:flex;gap:6px;margin-bottom:6px"><button class="btn p" id="kuh-go" type="button">Разобрать</button>' +
      '<button class="btn" id="kuh-cp" type="button">Копировать ответ</button></div>' +
      '<div style="display:flex;gap:6px;margin-bottom:8px"><button class="btn note" id="kuh-note" type="button">В заметку сделки</button></div>' +
      '<div class="blk"><b>Суть</b><div id="kuh-sum" style="white-space:pre-wrap;margin-top:4px">—</div>' +
      '<div style="color:#64748b;margin-top:4px">Услуга: <span id="kuh-svc">—</span></div></div>' +
      '<div class="blk"><b>Сделать сейчас</b><ul id="kuh-next"></ul></div>' +
      '<div class="blk"><b>Готовые ответы (клик = копировать)</b><div id="kuh-rep"></div></div>' +
      '<div class="blk"><b>Вопросы клиенту</b><ul id="kuh-q"></ul></div>' +
      '<div class="blk"><b>Возражения</b><ul id="kuh-obj"></ul></div>' +
      '<div class="blk"><b>Риски</b><ul id="kuh-risk"></ul><b>Не делать</b><ul id="kuh-donot"></ul></div>' +
      "</div>";
    document.documentElement.appendChild(root);
    document.getElementById("kuh-ai-x").onclick = function () {
      root.style.display = "none";
    };
    document.getElementById("kuh-go").onclick = analyze;
    document.getElementById("kuh-cp").onclick = copyBest;
    document.getElementById("kuh-note").onclick = writeNote;
    root.addEventListener("click", function (e) {
      var t = e.target.closest(".rep");
      if (!t) return;
      copy(t.innerText);
      st("Скопировано ✓");
    });
    return root;
  }

  function st(m) {
    var el = document.getElementById("kuh-st");
    if (el) el.textContent = m || "";
  }

  function fill(id, arr) {
    var ul = document.getElementById(id);
    if (!ul) return;
    ul.innerHTML = "";
    (arr || []).forEach(function (x) {
      var li = document.createElement("li");
      li.textContent = x;
      ul.appendChild(li);
    });
    if (!(arr && arr.length)) {
      var li = document.createElement("li");
      li.textContent = "—";
      ul.appendChild(li);
    }
  }

  var last = null;

  function render(data) {
    last = data;
    var c = data.coach || {};
    var q = data.quality || {};
    var lead = data.lead || {};
    var score = c.score != null ? c.score : q.score;
    var sc = document.getElementById("kuh-sc");
    sc.textContent = (score != null ? score : "—") + "/10";
    sc.className = "sc " + (score >= 7.5 ? "g" : score >= 5 ? "m" : "b");
    document.getElementById("kuh-lead").textContent =
      (lead.name || "#" + (lead.id || "")) +
      (lead.responsible_name ? " · " + lead.responsible_name : "");
    document.getElementById("kuh-sum").textContent = c.summary || q.summary || "—";
    document.getElementById("kuh-svc").textContent =
      c.service_hint || lead.status_name || "—";
    fill("kuh-next", c.next_steps);
    fill("kuh-q", c.questions_to_ask);
    fill("kuh-risk", c.risks);
    fill("kuh-donot", c.do_not);
    var rep = document.getElementById("kuh-rep");
    rep.innerHTML = "";
    (c.suggested_replies || []).forEach(function (r) {
      var d = document.createElement("div");
      d.className = "rep";
      d.textContent = r;
      rep.appendChild(d);
    });
    if (!(c.suggested_replies || []).length) {
      rep.innerHTML = '<div style="color:#64748b">—</div>';
    }
    var obj = document.getElementById("kuh-obj");
    obj.innerHTML = "";
    (c.objections || []).forEach(function (o) {
      var li = document.createElement("li");
      li.innerHTML = "<b>" + esc(o.objection || "") + ":</b> " + esc(o.answer || "");
      obj.appendChild(li);
    });
    var noteBtn = document.getElementById("kuh-note");
    if (noteBtn) noteBtn.disabled = !(data.note_markdown || "").trim();
    st("OK · " + (c.model || q.model || "") + " · сделка " + (lead.id || ""));
  }

  function copy(t) {
    if (!t) return;
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(t);
    else {
      var ta = document.createElement("textarea");
      ta.value = t;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
    }
  }

  function copyBest() {
    var t = last && last.coach && last.coach.suggested_replies && last.coach.suggested_replies[0];
    if (!t) return st("Нет текста для копирования");
    copy(t);
    st("Ответ скопирован ✓");
  }

  function writeNote() {
    var id = leadId();
    if (!id) return st("Откройте карточку сделки");
    var text = last && last.note_markdown ? String(last.note_markdown).trim() : "";
    if (!text) return st("Сначала нажмите «Разобрать»");
    var btn = document.getElementById("kuh-note");
    if (btn) btn.disabled = true;
    st("Запись в сделку…");
    fetch(API + "/api/v1/assistant/write_note", {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lead_id: id, text: text }),
    })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function () {
        st("Примечание записано в сделку ✓");
      })
      .catch(function (e) {
        st("Не удалось записать: " + e.message);
      })
      .finally(function () {
        if (btn) btn.disabled = !(last && last.note_markdown);
      });
  }

  function analyze() {
    ensureUi();
    var id = leadId();
    if (!id) return st("Откройте сделку /leads/detail/ID");
    st("Анализирую #" + id + "…");
    var btn = document.getElementById("kuh-go");
    var noteBtn = document.getElementById("kuh-note");
    if (btn) btn.disabled = true;
    if (noteBtn) noteBtn.disabled = true;
    fetch(API + "/api/v1/assistant/lead/" + id + "?live_stt=false&write_note=false", {
      method: "GET",
      cache: "no-store",
    })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(render)
      .catch(function (e) {
        st("API offline: " + e.message + " · http://127.0.0.1:8090/health");
      })
      .finally(function () {
        if (btn) btn.disabled = false;
      });
  }

  function boot() {
    if (!/leads\/detail\/\d+/i.test(location.href)) {
      var r = document.getElementById("kuh-ai-root");
      if (r) r.style.display = "none";
      ensureUi();
      if (!/leads\/detail\/\d+/i.test(location.href)) {
        var fab = document.getElementById("kuh-ai-fab");
        if (fab) fab.style.opacity = "0.7";
        return;
      }
    }
    ensureUi();
    document.getElementById("kuh-ai-root").style.display = "flex";
    analyze();
  }

  var href = location.href;
  setInterval(function () {
    if (location.href !== href) {
      href = location.href;
      boot();
    }
  }, 800);

  boot();
  setTimeout(boot, 2000);
})();
