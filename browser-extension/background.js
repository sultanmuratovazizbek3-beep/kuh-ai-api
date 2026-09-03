/**
 * Service worker: proxy API calls (avoids page CORS quirks).
 */
const DEFAULTS = {
  apiBase: "http://127.0.0.1:8090",
  autoRefreshSec: 120,
  startCollapsed: true,
};

chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.sync.get(DEFAULTS, (cur) => {
    chrome.storage.sync.set({ ...DEFAULTS, ...cur });
  });
});

async function getBase() {
  const { apiBase } = await chrome.storage.sync.get(DEFAULTS);
  return String(apiBase || DEFAULTS.apiBase).replace(/\/$/, "");
}

async function apiGet(path) {
  const base = await getBase();
  const r = await fetch(base + path, { method: "GET", cache: "no-store" });
  if (!r.ok) throw new Error("HTTP " + r.status);
  return r.json();
}

async function apiPost(path, body) {
  const base = await getBase();
  const r = await fetch(base + path, {
    method: "POST",
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  if (!r.ok) {
    let detail = "HTTP " + r.status;
    try {
      const j = await r.json();
      if (j && (j.detail || j.error)) detail = String(j.detail || j.error);
    } catch (_) {}
    throw new Error(detail);
  }
  return r.json();
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type === "health") {
    getBase()
      .then((base) =>
        fetch(base + "/health", { cache: "no-store" }).then((r) => r.json())
      )
      .then((data) => sendResponse({ ok: true, data }))
      .catch((e) => sendResponse({ ok: false, error: String(e.message || e) }));
    return true;
  }

  if (msg?.type === "assistLead") {
    const id = msg.leadId;
    if (!id) {
      sendResponse({ ok: false, error: "нет lead id" });
      return false;
    }
    // live_stt=false — быстрый UI; bulk STT делает worker
    // write_note=false — запись только по явной кнопке
    apiGet("/api/v1/assistant/lead/" + id + "?live_stt=false&write_note=false")
      .then((data) => sendResponse({ ok: true, data }))
      .catch((e) => sendResponse({ ok: false, error: String(e.message || e) }));
    return true;
  }

  if (msg?.type === "writeNote") {
    const id = msg.leadId;
    const text = (msg.text || "").trim();
    if (!id) {
      sendResponse({ ok: false, error: "нет lead id" });
      return false;
    }
    if (!text) {
      sendResponse({ ok: false, error: "нет текста заметки" });
      return false;
    }
    apiPost("/api/v1/assistant/write_note", { lead_id: id, text })
      .then((data) => sendResponse({ ok: true, data }))
      .catch((e) => sendResponse({ ok: false, error: String(e.message || e) }));
    return true;
  }

  if (msg?.type === "getSettings") {
    chrome.storage.sync.get(DEFAULTS, (cfg) => sendResponse({ ok: true, cfg }));
    return true;
  }

  return false;
});

// Badge health every 3 min
chrome.alarms.create("kuh-health", { periodInMinutes: 3 });
chrome.alarms.onAlarm.addListener(async (a) => {
  if (a.name !== "kuh-health") return;
  try {
    const base = await getBase();
    const r = await fetch(base + "/health", { cache: "no-store" });
    chrome.action.setBadgeText({ text: r.ok ? "" : "!" });
    chrome.action.setBadgeBackgroundColor({ color: r.ok ? "#16a34a" : "#dc2626" });
  } catch {
    chrome.action.setBadgeText({ text: "OFF" });
    chrome.action.setBadgeBackgroundColor({ color: "#dc2626" });
  }
});
