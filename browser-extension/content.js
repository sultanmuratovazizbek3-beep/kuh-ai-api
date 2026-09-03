/**
 * KUH AI — content script for AmoCRM
 * Collapsed pill by default; analyze / copy / write note to deal.
 */
(function () {
  "use strict";
  if (window.__KUH_AI_CHROME__) return;
  window.__KUH_AI_CHROME__ = true;

  const STORAGE_KEY = "kuhCollapsed";
  let collapsed = true;
  let lastPayload = null;
  let refreshTimer = null;
  let lastLead = null;
  let inFlight = false;
  let noteInFlight = false;
  let autoSec = 120;

  const i18n = {
    title: "KUH AI · помощник",
    pill: "KUH AI",
    analyze: "Разобрать",
    copy: "Копировать ответ",
    note: "В заметку сделки",
    collapse: "Свернуть",
    expand: "Развернуть",
    summary: "Суть",
    service: "Услуга",
    now: "Сделать сейчас",
    phrases: "Готовые ответы (клик = копировать)",
    questions: "Вопросы клиенту",
    objections: "Возражения",
    risks: "Риски",
    donot: "Не делать",
    openDeal: "Откройте карточку сделки",
    loading: "Анализ…",
    writing: "Запись в сделку…",
    offline: "API offline · start_always_online.bat",
    copied: "Скопировано ✓",
    noteOk: "Примечание записано в сделку ✓",
    noteNeedAnalyze: "Сначала нажмите «Разобрать»",
    noText: "Нет текста для копирования",
    urgent: "⚠ Red flag — срочный приём / 103 · безопасность прежде всего",
  };

  function leadId() {
    const m = (location.pathname + location.href).match(/\/leads\/detail\/(\d+)/i);
    return m ? parseInt(m[1], 10) : null;
  }

  function isDeal() {
    return !!leadId();
  }

  function scoreClass(s) {
    s = parseFloat(s);
    if (s >= 7.5) return "g";
    if (s >= 5) return "m";
    return "b";
  }

  function send(msg) {
    return new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage(msg, (resp) => {
          if (chrome.runtime.lastError) {
            resolve({ ok: false, error: chrome.runtime.lastError.message });
            return;
          }
          resolve(resp || { ok: false, error: "empty" });
        });
      } catch (e) {
        resolve({ ok: false, error: String(e.message || e) });
      }
    });
  }

  function loadCollapsed(cb) {
    try {
      chrome.storage.local.get({ [STORAGE_KEY]: null }, (local) => {
        if (local[STORAGE_KEY] !== null && local[STORAGE_KEY] !== undefined) {
          collapsed = !!local[STORAGE_KEY];
          cb();
          return;
        }
        chrome.storage.sync.get({ startCollapsed: true }, (sync) => {
          collapsed = sync.startCollapsed !== false;
          cb();
        });
      });
    } catch (_) {
      collapsed = true;
      cb();
    }
  }

  function saveCollapsed() {
    try {
      chrome.storage.local.set({ [STORAGE_KEY]: collapsed });
    } catch (_) {}
  }

  function ensureHost() {
    let host = document.getElementById("kuh-ai-host");
    if (host) return host;

    host = document.createElement("div");
    host.id = "kuh-ai-host";
    host.innerHTML = `
      <div id="kuh-ai-panel" role="dialog" aria-label="KUH AI">
        <div class="kuh-hd">
          <b>${i18n.title}</b>
          <button type="button" id="kuh-ai-refresh" title="${i18n.analyze}">↻</button>
          <button type="button" id="kuh-ai-min" title="${i18n.collapse}">−</button>
        </div>
        <div class="kuh-bd">
          <div class="kuh-row">
            <span class="kuh-score m" id="kuh-sc">—/10</span>
            <span class="kuh-meta" id="kuh-lead">…</span>
          </div>
          <div class="kuh-st" id="kuh-st"></div>
          <div class="kuh-actions">
            <button class="kuh-btn p" type="button" id="kuh-go">${i18n.analyze}</button>
            <button class="kuh-btn" type="button" id="kuh-cp">${i18n.copy}</button>
          </div>
          <div class="kuh-actions">
            <button class="kuh-btn note" type="button" id="kuh-note" disabled>${i18n.note}</button>
          </div>
          <div class="kuh-urgent" id="kuh-urgent">${i18n.urgent}</div>
          <div class="kuh-blk">
            <h4>${i18n.summary}</h4>
            <div class="kuh-pre" id="kuh-sum">—</div>
            <div class="kuh-meta" style="margin-top:4px">${i18n.service}: <span id="kuh-svc">—</span></div>
          </div>
          <div class="kuh-blk"><h4>${i18n.now}</h4><ul id="kuh-next"></ul></div>
          <div class="kuh-blk"><h4>${i18n.phrases}</h4><div id="kuh-rep"></div></div>
          <div class="kuh-blk"><h4>${i18n.questions}</h4><ul id="kuh-q"></ul></div>
          <div class="kuh-blk"><h4>${i18n.objections}</h4><ul id="kuh-obj"></ul></div>
          <div class="kuh-blk"><h4>${i18n.risks}</h4><ul id="kuh-risk"></ul>
            <h4 style="margin-top:8px">${i18n.donot}</h4><ul id="kuh-donot"></ul></div>
        </div>
      </div>
      <button type="button" id="kuh-ai-toggle" title="${i18n.expand}">
        <span class="kuh-dot" id="kuh-dot"></span>
        <span>${i18n.pill}</span>
      </button>
    `;
    document.documentElement.appendChild(host);

    document.getElementById("kuh-ai-toggle").onclick = () => setCollapsed(!collapsed);
    document.getElementById("kuh-ai-min").onclick = () => setCollapsed(true);
    document.getElementById("kuh-go").onclick = () => analyze(true);
    document.getElementById("kuh-ai-refresh").onclick = () => analyze(true);
    document.getElementById("kuh-cp").onclick = copyBest;
    document.getElementById("kuh-note").onclick = writeNote;
    host.addEventListener("click", (e) => {
      const t = e.target.closest(".kuh-rep");
      if (!t) return;
      copyText(t.innerText);
      setStatus(i18n.copied, "ok");
    });

    applyCollapsed();
    return host;
  }

  function setCollapsed(v) {
    collapsed = !!v;
    saveCollapsed();
    applyCollapsed();
    if (!collapsed && isDeal() && !lastPayload) analyze(false);
  }

  function applyCollapsed() {
    const host = document.getElementById("kuh-ai-host");
    if (!host) return;
    host.classList.toggle("kuh-collapsed", collapsed);
    const btn = document.getElementById("kuh-ai-toggle");
    if (btn) btn.title = collapsed ? i18n.expand : i18n.collapse;
  }

  function setStatus(msg, kind) {
    const el = document.getElementById("kuh-st");
    if (!el) return;
    el.className = "kuh-st" + (kind ? " " + kind : "");
    el.textContent = msg || "";
  }

  function fillList(id, arr) {
    const ul = document.getElementById(id);
    if (!ul) return;
    ul.innerHTML = "";
    (arr || []).forEach((x) => {
      const li = document.createElement("li");
      li.textContent = x;
      ul.appendChild(li);
    });
    if (!(arr && arr.length)) {
      const li = document.createElement("li");
      li.textContent = "—";
      ul.appendChild(li);
    }
  }

  function copyText(t) {
    if (!t) return;
    if (navigator.clipboard?.writeText) navigator.clipboard.writeText(t);
    else {
      const ta = document.createElement("textarea");
      ta.value = t;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
    }
  }

  function copyBest() {
    const t = lastPayload?.coach?.suggested_replies?.[0];
    if (!t) return setStatus(i18n.noText, "err");
    copyText(t);
    setStatus(i18n.copied, "ok");
  }

  async function writeNote() {
    const id = leadId();
    if (!id) return setStatus(i18n.openDeal, "err");
    const text = (lastPayload?.note_markdown || "").trim();
    if (!text) return setStatus(i18n.noteNeedAnalyze, "err");
    if (noteInFlight) return;

    noteInFlight = true;
    const btn = document.getElementById("kuh-note");
    if (btn) btn.disabled = true;
    setStatus(i18n.writing);

    const resp = await send({ type: "writeNote", leadId: id, text });
    noteInFlight = false;
    if (btn) btn.disabled = false;

    if (!resp?.ok) {
      setStatus("Не удалось записать: " + (resp?.error || ""), "err");
      return;
    }
    setStatus(i18n.noteOk, "ok");
  }

  function render(data) {
    lastPayload = data;
    const coach = data.coach || {};
    const quality = data.quality || {};
    const lead = data.lead || {};
    const score = coach.score != null ? coach.score : quality.score;

    const sc = document.getElementById("kuh-sc");
    sc.textContent = (score != null ? score : "—") + "/10";
    sc.className = "kuh-score " + scoreClass(score);

    document.getElementById("kuh-lead").textContent =
      (lead.name || "#" + (lead.id || "")) +
      (lead.responsible_name ? " · " + lead.responsible_name : "");

    document.getElementById("kuh-sum").textContent =
      coach.summary || quality.summary || "—";
    document.getElementById("kuh-svc").textContent =
      coach.service_hint || lead.status_name || "—";

    fillList("kuh-next", coach.next_steps);
    fillList("kuh-q", coach.questions_to_ask);
    fillList("kuh-risk", coach.risks);
    fillList("kuh-donot", coach.do_not);

    const rep = document.getElementById("kuh-rep");
    rep.innerHTML = "";
    (coach.suggested_replies || []).forEach((r) => {
      const d = document.createElement("div");
      d.className = "kuh-rep";
      d.textContent = r;
      rep.appendChild(d);
    });
    if (!(coach.suggested_replies || []).length) {
      rep.innerHTML = '<div class="kuh-meta">—</div>';
    }

    const obj = document.getElementById("kuh-obj");
    obj.innerHTML = "";
    (coach.objections || []).forEach((o) => {
      const li = document.createElement("li");
      li.innerHTML =
        "<b>" +
        escapeHtml(o.objection || "") +
        ":</b> " +
        escapeHtml(o.answer || "");
      obj.appendChild(li);
    });

    const urg = document.getElementById("kuh-urgent");
    const blob = (
      (coach.risks || []).join(" ") +
      " " +
      (coach.stage_hint || "") +
      " " +
      (coach.summary || "")
    ).toLowerCase();
    urg.classList.toggle(
      "on",
      /срочн|shoshilinch|103|острое|red flag|xavfsizlik/.test(blob)
    );

    const st = data.stats || {};
    setStatus(
      "OK · " +
        (coach.model || quality.model || "") +
        " · звонки/заметки: " +
        (st.transcripts || st.notes || 0),
      "ok"
    );

    const noteBtn = document.getElementById("kuh-note");
    if (noteBtn) noteBtn.disabled = !(data.note_markdown || "").trim();

    const dot = document.getElementById("kuh-dot");
    if (dot) dot.classList.remove("off");
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  async function analyze(force) {
    ensureHost();
    const id = leadId();
    if (!id) {
      setStatus(i18n.openDeal, "err");
      return;
    }
    if (inFlight) return;
    if (!force && lastLead === id && lastPayload) return;

    inFlight = true;
    lastLead = id;
    const btn = document.getElementById("kuh-go");
    const noteBtn = document.getElementById("kuh-note");
    if (btn) btn.disabled = true;
    if (noteBtn) noteBtn.disabled = true;
    setStatus(i18n.loading);

    const resp = await send({ type: "assistLead", leadId: id });
    inFlight = false;
    if (btn) btn.disabled = false;

    if (!resp?.ok) {
      setStatus(i18n.offline + " · " + (resp?.error || ""), "err");
      const dot = document.getElementById("kuh-dot");
      if (dot) dot.classList.add("off");
      return;
    }
    render(resp.data);
  }

  function scheduleRefresh() {
    if (refreshTimer) clearInterval(refreshTimer);
    if (autoSec <= 0) return;
    refreshTimer = setInterval(() => {
      if (!isDeal() || collapsed || document.hidden) return;
      analyze(true);
    }, autoSec * 1000);
  }

  function boot() {
    ensureHost();
    if (!isDeal()) {
      setStatus(i18n.openDeal);
      lastLead = null;
      return;
    }
    if (!collapsed) analyze(false);
  }

  let href = location.href;
  setInterval(() => {
    if (location.href !== href) {
      href = location.href;
      lastPayload = null;
      lastLead = null;
      boot();
    }
  }, 900);

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && isDeal() && !collapsed) analyze(false);
  });

  send({ type: "getSettings" }).then((r) => {
    if (r?.ok && r.cfg?.autoRefreshSec != null) {
      autoSec = parseInt(r.cfg.autoRefreshSec, 10) || 0;
    }
    scheduleRefresh();
  });

  loadCollapsed(() => {
    ensureHost();
    applyCollapsed();
    boot();
  });
})();
