const DEFAULTS = {
  apiBase: "http://127.0.0.1:8090",
  autoRefreshSec: 120,
  startCollapsed: true,
};

chrome.storage.sync.get(DEFAULTS, (cfg) => {
  document.getElementById("apiBase").value = cfg.apiBase || DEFAULTS.apiBase;
  document.getElementById("autoRefreshSec").value =
    cfg.autoRefreshSec ?? DEFAULTS.autoRefreshSec;
  document.getElementById("startCollapsed").checked = cfg.startCollapsed !== false;
});

document.getElementById("save").onclick = () => {
  const apiBase = document.getElementById("apiBase").value.trim().replace(/\/$/, "");
  const autoRefreshSec =
    parseInt(document.getElementById("autoRefreshSec").value, 10) || 0;
  const startCollapsed = document.getElementById("startCollapsed").checked;
  chrome.storage.sync.set({ apiBase, autoRefreshSec, startCollapsed }, () => {
    if (startCollapsed) {
      chrome.storage.local.set({ kuhCollapsed: true });
    }
    document.getElementById("msg").textContent = "Сохранено";
  });
};
