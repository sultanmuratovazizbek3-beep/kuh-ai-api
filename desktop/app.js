/* KUH Desktop UI */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];

const state = {
  api: localStorage.getItem("kuh_api") || "http://127.0.0.1:8090",
  leads: [],
  selectedId: null,
  panelCollapsed: false,
  lastAssist: null,
};

function toast(msg) {
  const el = $("#toast-g");
  el.textContent = msg;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 2400);
}

async function api(path, opts = {}) {
  const url = state.api.replace(/\/$/, "") + path;
  const r = await fetch(url, {
    cache: "no-store",
    ...opts,
    headers: {
      "Content-Type": "application/json",
      ...(opts.headers || {}),
    },
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

function setApiStatus(ok, text) {
  const pill = $("#api-status");
  pill.classList.remove("ok", "bad");
  pill.classList.add(ok ? "ok" : "bad");
  $("#api-status-text").textContent = text;
}

function switchView(name) {
  $$(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  $$(".view").forEach((v) => v.classList.toggle("active", v.id === "view-" + name));
  const titles = {
    dashboard: ["Обзор / Umumiy", "Сводка отдела и активность"],
    assistant: ["Помощник / Yordamchi", "Разбор сделки · RU + UZ · сворачивается"],
    reports: ["Отчёты / Hisobotlar", "Desktop only · в CRM не пишем"],
    crm: ["Подключения CRM", "amoCRM · Bitrix24 · несколько профилей"],
    settings: ["Настройки", "API и параметры"],
  };
  const t = titles[name] || ["", ""];
  $("#view-title").textContent = t[0];
  $("#view-sub").textContent = t[1];
}

function conv(w, l) {
  const t = (w || 0) + (l || 0);
  if (!t) return "—";
  return Math.round((100 * w) / t) + "%";
}

function fmtTime(ts) {
  if (!ts) return "";
  try {
    return new Date(ts * 1000).toLocaleString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

function renderManagers(stats) {
  const body = $("#mgr-body");
  body.innerHTML = "";
  const managers = (stats?.managers || []).filter(
    (m) => m.calls_total + m.chats_total + m.leads_worked > 0
  );
  managers.slice(0, 12).forEach((m) => {
    const tr = document.createElement("tr");
    const q = m.avg_quality_score != null ? m.avg_quality_score + "/10" : "—";
    tr.innerHTML = `
      <td><b>${escapeHtml(m.name)}</b></td>
      <td>${m.calls_total || 0}</td>
      <td>${m.leads_won || 0}</td>
      <td>${conv(m.leads_won, m.leads_lost)}</td>
      <td>${q}</td>`;
    body.appendChild(tr);
  });
  if (!managers.length) {
    body.innerHTML = `<tr><td colspan="5" class="muted">Нет данных — нажмите «Синхронизация»</td></tr>`;
  }
}

function leadTag(l) {
  if (l.is_won) return '<span class="tag won">WON</span>';
  if (l.is_lost) return '<span class="tag lost">LOST</span>';
  return `<span class="tag">${l.transcripts ? "🎙 " + l.transcripts : "·"}</span>`;
}

function renderLeadList(target, leads, onClick) {
  const el = $(target);
  el.innerHTML = "";
  leads.forEach((l) => {
    const div = document.createElement("div");
    div.className = "lead-item" + (state.selectedId === l.id ? " active" : "");
    div.innerHTML = `
      <div>
        <div class="name">${escapeHtml(l.name || "#" + l.id)}</div>
        <div class="sub">${escapeHtml(l.responsible_name || "—")} · ${fmtTime(l.updated_at)} · #${l.id}</div>
      </div>
      ${leadTag(l)}`;
    div.onclick = () => onClick(l);
    el.appendChild(div);
  });
  if (!leads.length) {
    el.innerHTML = `<div class="muted small" style="padding:12px">Нет сделок в кэше</div>`;
  }
}

function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function fillUl(id, arr) {
  const ul = $(id);
  ul.innerHTML = "";
  (arr || []).forEach((x) => {
    const li = document.createElement("li");
    li.textContent = x;
    ul.appendChild(li);
  });
  if (!(arr || []).length) {
    const li = document.createElement("li");
    li.textContent = "—";
    ul.appendChild(li);
  }
}

function scoreClass(s) {
  s = parseFloat(s);
  if (s >= 7.5) return "g";
  if (s >= 5) return "m";
  return "b";
}

function renderAssist(data) {
  state.lastAssist = data;
  $("#assist-empty").classList.add("hidden");
  $("#assist-panel").classList.remove("hidden");
  applyPanelCollapse();

  const coach = data.coach || {};
  const quality = data.quality || {};
  const lead = data.lead || {};
  const score = coach.score != null ? coach.score : quality.score;

  $("#a-title").textContent = lead.name || "Сделка #" + (lead.id || "");
  $("#a-meta").textContent =
    (lead.responsible_name || "—") +
    " · status " +
    (lead.status_name || lead.status_id || "—") +
    " · #" +
    (lead.id || "");

  const sc = $("#a-score");
  sc.textContent = (score != null ? score : "—") + "/10";
  sc.className = "score-ring " + scoreClass(score);
  $("#a-model").textContent = coach.model || quality.model || "";
  $("#a-svc").textContent = coach.service_hint || "—";
  $("#a-stage").textContent = coach.stage_hint || "—";
  $("#a-summary").textContent = coach.summary || quality.summary || "—";

  fillUl("#a-next", coach.next_steps);
  fillUl("#a-questions", coach.questions_to_ask);
  fillUl("#a-risks", coach.risks);
  fillUl("#a-donot", coach.do_not);

  const rep = $("#a-replies");
  rep.innerHTML = "";
  (coach.suggested_replies || []).forEach((r) => {
    const d = document.createElement("div");
    d.className = "reply";
    d.textContent = r;
    d.onclick = () => {
      navigator.clipboard?.writeText(r);
      toast("Скопировано / Nusxa olindi");
    };
    rep.appendChild(d);
  });

  const obj = $("#a-obj");
  obj.innerHTML = "";
  (coach.objections || []).forEach((o) => {
    const li = document.createElement("li");
    li.innerHTML = `<b>${escapeHtml(o.objection || "")}:</b> ${escapeHtml(o.answer || "")}`;
    obj.appendChild(li);
  });

  const blob = (
    (coach.risks || []).join(" ") +
    " " +
    (coach.stage_hint || "") +
    " " +
    (coach.summary || "")
  ).toLowerCase();
  $("#a-urgent").classList.toggle(
    "hidden",
    !/срочн|shoshilinch|103|острое|red flag|xavfsizlik/.test(blob)
  );

  $("#btn-open-amo").onclick = () => {
    const url = `https://kuhhospital.amocrm.ru/leads/detail/${lead.id}`;
    window.open(url, "_blank");
  };
}

function applyPanelCollapse() {
  const collapsed = state.panelCollapsed;
  $("#assist-body").classList.toggle("hidden", collapsed);
  $("#assist-collapsed").classList.toggle("hidden", !collapsed);
  $("#btn-collapse-panel").textContent = collapsed ? "+" : "−";
}

async function loadDashboard() {
  try {
    const health = await api("/health");
    setApiStatus(true, health.status === "ok" ? "API online" : "API degraded");
  } catch {
    setApiStatus(false, "API offline");
    return;
  }

  try {
    const st = await api("/api/v1/stats?hours=24");
    const t = st.stats?.totals || {};
    $("#k-calls").textContent = t.calls ?? "0";
    $("#k-chats").textContent = t.chats ?? "0";
    $("#k-leads").textContent = t.leads_worked ?? "0";
    $("#k-won").textContent = `${t.leads_won ?? 0} · ${conv(t.leads_won, t.leads_lost)}`;
    renderManagers(st.stats);
  } catch (e) {
    toast("Stats: " + e.message);
  }

  try {
    let lr;
    try {
      lr = await api("/api/v1/crm/leads?limit=40&hours=96");
    } catch {
      lr = await api("/api/v1/leads/recent?limit=40&hours=96");
    }
    state.leads = lr.leads || [];
    if (lr.provider) {
      $("#view-sub").textContent =
        `CRM: ${lr.provider}${lr.label ? " · " + lr.label : ""} · активность`;
    }
    renderLeadList("#lead-list", state.leads.slice(0, 15), (l) => {
      state.selectedId = l.id;
      switchView("assistant");
      selectLead(l.id);
    });
    renderAssistLeads(state.leads);
  } catch (e) {
    toast("Leads: " + e.message);
  }
}

function renderAssistLeads(leads) {
  const q = ($("#lead-search").value || "").toLowerCase().trim();
  const filtered = !q
    ? leads
    : leads.filter(
        (l) =>
          String(l.id).includes(q) ||
          (l.name || "").toLowerCase().includes(q) ||
          (l.responsible_name || "").toLowerCase().includes(q)
      );
  renderLeadList("#assist-leads", filtered, (l) => selectLead(l.id));
}

async function selectLead(id) {
  state.selectedId = id;
  state.panelCollapsed = false;
  renderAssistLeads(state.leads);
  $("#manual-lead").value = id;
  await analyzeLead(id);
}

async function analyzeLead(id) {
  const btn = $("#btn-analyze");
  if (btn) btn.disabled = true;
  toast("Анализ #" + id + "…");
  try {
    let data;
    try {
      data = await api(`/api/v1/crm/assist/${id}`);
    } catch {
      data = await api(
        `/api/v1/assistant/lead/${id}?live_stt=false&write_note=false`
      );
    }
    renderAssist(data);
    toast("Готово · " + (data.coach?.model || data.provider || ""));
  } catch (e) {
    toast("Ошибка: " + e.message);
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function runCollect() {
  toast("Синхронизация AmoCRM…");
  try {
    await api("/api/v1/collect?hours=24", { method: "POST" });
    toast("Синхронизация завершена");
    await loadDashboard();
  } catch (e) {
    toast("Sync error: " + e.message);
  }
}

async function runReport(period) {
  $("#report-box").textContent = "Генерация " + period + "…";
  try {
    const data = await api("/api/v1/report/" + period);
    $("#report-box").textContent = data.markdown || JSON.stringify(data, null, 2);
    toast("Отчёт → Desktop\\AmoCRM-AI-Reports");
  } catch (e) {
    $("#report-box").textContent = "Ошибка: " + e.message;
  }
}

async function loadProfiles() {
  try {
    const data = await api("/api/v1/crm/profiles");
    const box = $("#crm-profiles");
    if (!box) return;
    box.innerHTML = "";
    const list = data.profiles || [];
    if (!list.length) {
      box.innerHTML =
        '<div class="muted small" style="padding:12px">Нет подключений. Добавьте CRM справа.</div>';
      return;
    }
    list.forEach((p) => {
      const active = data.active_id === p.id;
      const div = document.createElement("div");
      div.className = "lead-item" + (active ? " active" : "");
      div.innerHTML = `
        <div>
          <div class="name">${escapeHtml(p.label || p.id)} ${active ? "· ACTIVE" : ""}</div>
          <div class="sub">${escapeHtml(p.provider)} · ${escapeHtml(p.subdomain || p.webhook_url || "")}</div>
        </div>
        <span class="tag">${p.has_token ? "OK" : "?"}</span>`;
      div.onclick = async () => {
        await api(`/api/v1/crm/profiles/${p.id}/activate`, { method: "POST" });
        toast("Активен: " + (p.label || p.id));
        await loadProfiles();
        await loadDashboard();
      };
      box.appendChild(div);
    });
  } catch (e) {
    toast("Profiles: " + e.message);
  }
}

function crmFormPayload() {
  const provider = $("#crm-provider").value;
  return {
    provider,
    label: $("#crm-label").value || provider,
    subdomain: $("#crm-subdomain").value || "",
    long_lived_token: $("#crm-token").value || "",
    client_id: $("#crm-client-id").value || "",
    client_secret: $("#crm-client-secret").value || "",
    refresh_token: $("#crm-refresh").value || "",
    webhook_url: $("#crm-webhook").value || "",
    set_active: true,
  };
}

function wire() {
  $$(".nav-item").forEach((b) =>
    b.addEventListener("click", () => {
      switchView(b.dataset.view);
      if (b.dataset.view === "crm") loadProfiles();
    })
  );
  const prov = $("#crm-provider");
  if (prov) {
    prov.onchange = () => {
      const bitrix = prov.value === "bitrix24";
      $("#fields-amocrm").classList.toggle("hidden", bitrix);
      $("#fields-bitrix").classList.toggle("hidden", !bitrix);
    };
  }
  $("#btn-reload-profiles")?.addEventListener("click", loadProfiles);
  $("#btn-crm-test")?.addEventListener("click", async () => {
    $("#crm-test-result").textContent = "Проверка…";
    try {
      const res = await api("/api/v1/crm/test", {
        method: "POST",
        body: JSON.stringify(crmFormPayload()),
      });
      if (res.ok && res.result?.ok) {
        $("#crm-test-result").textContent =
          "OK · " + (res.result.account_name || "connected");
      } else {
        $("#crm-test-result").textContent =
          "Ошибка: " + (res.error || res.result?.error || "fail");
      }
    } catch (e) {
      $("#crm-test-result").textContent = "Ошибка: " + e.message;
    }
  });
  $("#btn-crm-save")?.addEventListener("click", async () => {
    try {
      const res = await api("/api/v1/crm/profiles", {
        method: "POST",
        body: JSON.stringify(crmFormPayload()),
      });
      toast("CRM сохранена · id " + res.id);
      await loadProfiles();
      await loadDashboard();
    } catch (e) {
      toast("Save error: " + e.message);
    }
  });
  $("#btn-refresh").onclick = () => loadDashboard();
  $("#btn-collect").onclick = () => runCollect();
  $("#lead-search").oninput = () => renderAssistLeads(state.leads);
  $("#btn-load-lead").onclick = () => {
    const id = parseInt($("#manual-lead").value, 10);
    if (id) selectLead(id);
  };
  $("#btn-analyze").onclick = () => {
    if (state.selectedId) analyzeLead(state.selectedId);
  };
  $("#btn-collapse-panel").onclick = () => {
    state.panelCollapsed = !state.panelCollapsed;
    applyPanelCollapse();
  };
  $("#btn-expand-panel").onclick = () => {
    state.panelCollapsed = false;
    applyPanelCollapse();
  };
  $$("[data-report]").forEach((b) =>
    b.addEventListener("click", () => runReport(b.dataset.report))
  );
  $("#cfg-api").value = state.api;
  $("#btn-save-cfg").onclick = () => {
    state.api = $("#cfg-api").value.trim().replace(/\/$/, "");
    localStorage.setItem("kuh_api", state.api);
    toast("Сохранено");
    loadDashboard();
  };
}

wire();
loadDashboard();
setInterval(() => {
  if (document.visibilityState === "visible") loadDashboard();
}, 120000);
