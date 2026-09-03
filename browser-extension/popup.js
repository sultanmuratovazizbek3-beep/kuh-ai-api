chrome.storage.sync.get({ apiBase: "http://127.0.0.1:8090" }, (cfg) => {
  const base = (cfg.apiBase || "http://127.0.0.1:8090").replace(/\/$/, "");
  document.getElementById("api").textContent = base;
  fetch(base + "/health", { cache: "no-store" })
    .then((r) => r.json())
    .then(() => {
      document.getElementById("st").innerHTML =
        '<span class="ok">ONLINE</span> · backend работает';
    })
    .catch(() => {
      document.getElementById("st").innerHTML =
        '<span class="bad">OFFLINE</span> · запусти start_always_online.bat';
    });
});

document.getElementById("amo").onclick = () => {
  chrome.tabs.create({ url: "https://kuhhospital.amocrm.ru/" });
};
document.getElementById("opt").onclick = () => chrome.runtime.openOptionsPage();
