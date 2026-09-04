/**
 * Табель — сотрудники, статусы, онлайн, часы и детальная карточка.
 */
define(["jquery"], function ($) {
  var CustomWidget = function () {
    var self = this;
    var started = false;
    var state = null;
    var lastInputAt = 0;
    var heartbeatTimer = null;
    var onlineTimer = null;
    var observer = null;
    var expanded = {};
    var collapsedGroups = {};
    var qSearch = "";
    var qStatus = "";
    var qSort = "name";
    var EMBEDDED_CSS = ".kuh-tabel-menu-item {\n  display: flex;\n  align-items: center;\n  gap: 8px;\n  padding: 10px 14px;\n  cursor: pointer;\n  font-size: 14px;\n  color: #313942;\n  border-radius: 6px;\n  user-select: none;\n}\n.kuh-tabel-menu-item:hover {\n  background: #f2f4f7;\n}\n\n.kuh-tabel-fab {\n  position: fixed;\n  left: 72px;\n  bottom: 16px;\n  z-index: 12000;\n  display: flex;\n  align-items: center;\n  gap: 6px;\n  height: 32px;\n  padding: 0 10px;\n  border: 0;\n  border-radius: 16px;\n  background: #313942;\n  color: #fff;\n  font-size: 12px;\n  font-weight: 600;\n  cursor: pointer;\n  box-shadow: 0 4px 14px rgba(15, 23, 42, 0.28);\n}\n.kuh-tabel-fab:hover { background: #1f2730; }\n.kuh-tabel-fab-dot {\n  width: 8px;\n  height: 8px;\n  border-radius: 50%;\n  background: #7ed321;\n}\n\n.kuh-tabel-page {\n  font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, \"PT Sans\", sans-serif;\n  color: #313942;\n  background: #fff;\n  min-height: calc(100vh - 80px);\n  padding: 8px 8px 24px;\n}\n.kuh-tabel-page .kuh-tabel-modal {\n  width: 100%;\n  max-height: none;\n  box-shadow: none;\n  border-radius: 0;\n}\n\n.kuh-tabel-overlay {\n  position: fixed;\n  inset: 0;\n  z-index: 13000;\n  background: rgba(20, 28, 40, 0.45);\n  display: flex;\n  align-items: flex-start;\n  justify-content: center;\n  padding: 48px 16px 24px;\n  font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, \"PT Sans\", sans-serif;\n  color: #313942;\n}\n.kuh-tabel-modal {\n  width: min(1140px, 100%);\n  max-height: calc(100vh - 48px);\n  background: #fff;\n  border-radius: 10px;\n  box-shadow: 0 16px 48px rgba(15, 23, 42, 0.28);\n  display: flex;\n  flex-direction: column;\n  overflow: hidden;\n}\n.kuh-tabel-head {\n  display: flex;\n  align-items: center;\n  justify-content: space-between;\n  padding: 14px 18px 12px;\n  border-bottom: 1px solid #e8eaed;\n}\n.kuh-tabel-title {\n  font-size: 18px;\n  font-weight: 700;\n  letter-spacing: 0.01em;\n}\n.kuh-tabel-close {\n  width: 32px;\n  height: 32px;\n  border: 0;\n  background: transparent;\n  border-radius: 6px;\n  font-size: 22px;\n  line-height: 1;\n  cursor: pointer;\n  color: #8b95a1;\n}\n.kuh-tabel-close:hover { background: #f2f4f7; color: #313942; }\n\n.kuh-tabel-me {\n  display: flex;\n  align-items: center;\n  gap: 12px;\n  padding: 14px 18px 10px;\n}\n.kuh-tabel-avatar {\n  position: relative;\n  width: 44px;\n  height: 44px;\n  border-radius: 50%;\n  background: #dbe4f0;\n  color: #3d4a5c;\n  display: flex;\n  align-items: center;\n  justify-content: center;\n  font-weight: 700;\n  font-size: 14px;\n  flex-shrink: 0;\n  overflow: hidden;\n  text-transform: uppercase;\n}\n.kuh-tabel-avatar img {\n  width: 100%;\n  height: 100%;\n  object-fit: cover;\n}\n.kuh-tabel-dot {\n  position: absolute;\n  right: -1px;\n  bottom: -1px;\n  width: 12px;\n  height: 12px;\n  border-radius: 50%;\n  background: #c5ccd6;\n  border: 2px solid #fff;\n}\n.kuh-tabel-dot.on { background: #2ecc71; }\n.kuh-tabel-me-main { min-width: 0; flex: 1; }\n.kuh-tabel-name {\n  font-weight: 700;\n  font-size: 15px;\n  white-space: nowrap;\n  overflow: hidden;\n  text-overflow: ellipsis;\n}\n.kuh-tabel-meta {\n  font-size: 12px;\n  color: #8b95a1;\n  margin-top: 2px;\n}\n.kuh-tabel-me-right {\n  display: flex;\n  align-items: center;\n  gap: 10px;\n  flex-shrink: 0;\n}\n.kuh-tabel-leads {\n  font-size: 12px;\n  color: #5c6773;\n  background: #f4f6f8;\n  border-radius: 12px;\n  padding: 4px 8px;\n  white-space: nowrap;\n}\n\n.kuh-tabel-summary {\n  display: grid;\n  grid-template-columns: repeat(6, minmax(0, 1fr));\n  gap: 8px;\n  padding: 0 18px 10px;\n}\n.kuh-tabel-kpi {\n  background: #f4f6f8;\n  border-radius: 8px;\n  padding: 8px 10px;\n  min-width: 0;\n}\n.kuh-tabel-kpi b {\n  display: block;\n  font-size: 16px;\n  font-weight: 700;\n  color: #1f2933;\n  line-height: 1.2;\n}\n.kuh-tabel-kpi span {\n  font-size: 11px;\n  color: #8b95a1;\n}\n.kuh-tabel-kpi.on b { color: #159947; }\n.kuh-tabel-kpi.warn b { color: #d97706; }\n\n.kuh-tabel-toolbar {\n  display: flex;\n  gap: 8px;\n  padding: 4px 18px 12px;\n  flex-wrap: wrap;\n}\n.kuh-tabel-search,\n.kuh-tabel-filter,\n.kuh-tabel-select {\n  height: 34px;\n  border: 1px solid #d5d8de;\n  border-radius: 6px;\n  padding: 0 10px;\n  font-size: 13px;\n  background: #fff;\n  color: #313942;\n  outline: none;\n}\n.kuh-tabel-search:focus,\n.kuh-tabel-filter:focus,\n.kuh-tabel-select:focus {\n  border-color: #4c8bf5;\n  box-shadow: 0 0 0 3px rgba(76, 139, 245, 0.15);\n}\n.kuh-tabel-search { flex: 1; min-width: 160px; }\n.kuh-tabel-filter { min-width: 160px; }\n\n.kuh-tabel-body {\n  overflow: auto;\n  padding: 0 10px 16px;\n  min-height: 220px;\n}\n.kuh-tabel-group {\n  margin: 10px 8px 4px;\n  font-size: 12px;\n  font-weight: 700;\n  color: #8b95a1;\n  text-transform: uppercase;\n  letter-spacing: 0.04em;\n  cursor: pointer;\n  user-select: none;\n  display: flex;\n  align-items: center;\n  gap: 6px;\n}\n.kuh-tabel-group:hover { color: #5c6773; }\n.kuh-tabel-card {\n  border: 1px solid transparent;\n  border-radius: 10px;\n  margin: 0 4px 4px;\n}\n.kuh-tabel-card.open {\n  border-color: #d9e4f5;\n  background: #fbfcff;\n  margin-bottom: 8px;\n}\n.kuh-tabel-row {\n  display: grid;\n  grid-template-columns: 44px minmax(150px, 1.1fr) 92px minmax(200px, 1.5fr) 138px 28px;\n  gap: 10px;\n  align-items: center;\n  padding: 8px 8px;\n  border-radius: 8px;\n  cursor: pointer;\n}\n.kuh-tabel-row:hover { background: #f7f8fa; }\n.kuh-tabel-row.is-me { background: #f3f7ff; }\n.kuh-tabel-user-cell { min-width: 0; }\n.kuh-tabel-hours-cell {\n  font-size: 13px;\n  font-weight: 700;\n  color: #313942;\n  white-space: nowrap;\n}\n.kuh-tabel-hours-cell small {\n  display: block;\n  font-size: 10px;\n  font-weight: 500;\n  color: #8b95a1;\n}\n.kuh-tabel-chevron {\n  width: 28px;\n  height: 28px;\n  border: 0;\n  background: transparent;\n  color: #8b95a1;\n  font-size: 16px;\n  cursor: pointer;\n  border-radius: 6px;\n}\n.kuh-tabel-chevron:hover { background: #eef2f6; color: #313942; }\n.kuh-tabel-email {\n  font-size: 12px;\n  color: #8b95a1;\n  white-space: nowrap;\n  overflow: hidden;\n  text-overflow: ellipsis;\n}\n.kuh-tabel-empty {\n  padding: 40px 16px;\n  text-align: center;\n  color: #8b95a1;\n}\n\n.kuh-tabel-bar-wrap { min-width: 0; }\n.kuh-tabel-bar {\n  position: relative;\n  height: 12px;\n  background: #eef1f6;\n  border-radius: 6px;\n  overflow: hidden;\n}\n.kuh-tabel-seg {\n  position: absolute;\n  top: 0;\n  bottom: 0;\n  background: #7ed321;\n  border-radius: 2px;\n}\n.kuh-tabel-hours {\n  display: flex;\n  justify-content: space-between;\n  font-size: 10px;\n  color: #b0b7c1;\n  margin-top: 3px;\n  padding: 0 1px;\n}\n.kuh-tabel-expand {\n  padding: 4px 12px 14px 54px;\n}\n.kuh-tabel-stats {\n  display: grid;\n  grid-template-columns: repeat(6, minmax(0, 1fr));\n  gap: 6px;\n  margin-bottom: 10px;\n}\n.kuh-tabel-stat {\n  background: #fff;\n  border: 1px solid #e8eaed;\n  border-radius: 8px;\n  padding: 7px 8px;\n}\n.kuh-tabel-stat b {\n  display: block;\n  font-size: 14px;\n  line-height: 1.2;\n}\n.kuh-tabel-stat span {\n  font-size: 10px;\n  color: #8b95a1;\n}\n.kuh-tabel-dayline {\n  display: grid;\n  grid-template-columns: 72px 1fr 52px;\n  gap: 8px;\n  align-items: center;\n  margin-bottom: 6px;\n}\n.kuh-tabel-day-label {\n  font-size: 11px;\n  color: #8b95a1;\n}\n.kuh-tabel-day-h {\n  font-size: 11px;\n  font-weight: 700;\n  text-align: right;\n  color: #5c6773;\n}\n.kuh-tabel-copy {\n  border: 0;\n  background: transparent;\n  color: #4c8bf5;\n  font-size: 12px;\n  cursor: pointer;\n  padding: 0;\n}\n.kuh-tabel-copy:hover { text-decoration: underline; }\n.kuh-tabel-contacts {\n  display: flex;\n  gap: 12px;\n  flex-wrap: wrap;\n  font-size: 12px;\n  color: #5c6773;\n  margin-top: 8px;\n}\n\n.kuh-tabel-badge {\n  display: inline-flex;\n  align-items: center;\n  height: 22px;\n  padding: 0 8px;\n  border-radius: 11px;\n  font-size: 11px;\n  font-weight: 600;\n  background: #eef1f6;\n  color: #5c6773;\n  white-space: nowrap;\n}\n.kuh-tabel-foot {\n  border-top: 1px solid #e8eaed;\n  padding: 10px 18px 14px;\n  display: flex;\n  gap: 8px;\n  align-items: center;\n  flex-wrap: wrap;\n}\n.kuh-tabel-hint {\n  margin-left: auto;\n  font-size: 11px;\n  color: #8b95a1;\n}\n.kuh-tabel-add {\n  height: 32px;\n  padding: 0 10px;\n  border: 0;\n  border-radius: 6px;\n  background: #4c8bf5;\n  color: #fff;\n  font-size: 12px;\n  font-weight: 600;\n  cursor: pointer;\n}\n.kuh-tabel-add:hover { background: #3b7de3; }\n.kuh-tabel-ghost {\n  height: 32px;\n  padding: 0 10px;\n  border: 1px solid #d5d8de;\n  border-radius: 6px;\n  background: #fff;\n  font-size: 12px;\n  cursor: pointer;\n}\n.kuh-tabel-loading {\n  padding: 28px;\n  text-align: center;\n  color: #8b95a1;\n}\n.kuh-tabel-err { color: #e74c3c; font-size: 12px; padding: 0 18px 8px; }\n\n.kuh-acl {\n  margin: 8px 0 16px;\n  background: #fff;\n  border: 1px solid #e6eaef;\n  border-radius: 12px;\n  overflow: hidden;\n  font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, sans-serif;\n  color: #313942;\n}\n.kuh-acl-head {\n  display: flex;\n  align-items: center;\n  justify-content: space-between;\n  gap: 12px;\n  padding: 14px 16px;\n  background: linear-gradient(180deg, #f7fafc 0%, #fff 100%);\n  border-bottom: 1px solid #eef1f5;\n}\n.kuh-acl-head h3 {\n  margin: 0;\n  font-size: 15px;\n  font-weight: 700;\n}\n.kuh-acl-head p {\n  margin: 4px 0 0;\n  font-size: 12px;\n  color: #8b95a1;\n}\n.kuh-acl-count {\n  font-size: 12px;\n  color: #5c6773;\n  background: #f4f6f8;\n  border-radius: 12px;\n  padding: 4px 10px;\n  white-space: nowrap;\n}\n.kuh-acl-master {\n  display: flex;\n  align-items: center;\n  justify-content: space-between;\n  padding: 12px 16px;\n  background: #f4fbf6;\n  border-bottom: 1px solid #e8f5ec;\n}\n.kuh-acl-master b { font-size: 13px; }\n.kuh-acl-search {\n  margin: 10px 16px 6px;\n  width: calc(100% - 32px);\n  height: 34px;\n  border: 1px solid #d5d8de;\n  border-radius: 8px;\n  padding: 0 12px;\n  font-size: 13px;\n  box-sizing: border-box;\n}\n.kuh-acl-list { max-height: 360px; overflow: auto; padding: 4px 8px 12px; }\n.kuh-acl-g {\n  font-size: 11px;\n  font-weight: 700;\n  color: #8b95a1;\n  text-transform: uppercase;\n  letter-spacing: .04em;\n  padding: 10px 8px 4px;\n}\n.kuh-acl-row {\n  display: flex;\n  align-items: center;\n  gap: 10px;\n  padding: 8px;\n  border-radius: 10px;\n}\n.kuh-acl-row:hover { background: #f7f8fa; }\n.kuh-acl-row.is-off { opacity: .55; }\n.kuh-acl-name { flex: 1; min-width: 0; font-size: 13px; font-weight: 600; }\n.kuh-acl-name small {\n  display: block;\n  font-weight: 500;\n  color: #8b95a1;\n  font-size: 11px;\n}\n.kuh-sw {\n  position: relative;\n  width: 44px;\n  height: 24px;\n  flex-shrink: 0;\n}\n.kuh-sw input {\n  opacity: 0;\n  width: 0;\n  height: 0;\n  position: absolute;\n}\n.kuh-sw i {\n  position: absolute;\n  inset: 0;\n  background: #c5ccd6;\n  border-radius: 12px;\n  transition: background .2s;\n  cursor: pointer;\n}\n.kuh-sw i:before {\n  content: \"\";\n  position: absolute;\n  height: 18px;\n  width: 18px;\n  left: 3px;\n  top: 3px;\n  background: #fff;\n  border-radius: 50%;\n  box-shadow: 0 1px 3px rgba(15,23,42,.2);\n  transition: transform .2s;\n}\n.kuh-sw input:checked + i { background: #22c55e; }\n.kuh-sw input:checked + i:before { transform: translateX(20px); }\n.kuh-sw input:disabled + i { opacity: .7; cursor: default; }\n\n@media (max-width: 920px) {\n  .kuh-tabel-summary,\n  .kuh-tabel-stats {\n    grid-template-columns: repeat(3, minmax(0, 1fr));\n  }\n  .kuh-tabel-row {\n    grid-template-columns: 44px 1fr 28px;\n  }\n  .kuh-tabel-hours-cell,\n  .kuh-tabel-bar-wrap,\n  .kuh-tabel-row > .kuh-tabel-select {\n    grid-column: 2;\n  }\n  .kuh-tabel-expand { padding-left: 8px; }\n}\n\n\n/* Left rail item next to amo\u041c\u0430\u0440\u043a\u0435\u0442 / \u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438 */\n.kuh-tabel-sidebar {\n  display: flex;\n  flex-direction: column;\n  align-items: center;\n  justify-content: center;\n  gap: 4px;\n  width: 64px;\n  padding: 10px 4px 8px;\n  margin: 0 auto;\n  cursor: pointer;\n  user-select: none;\n  color: #c5c9ce;\n  box-sizing: border-box;\n}\n.kuh-tabel-sidebar:hover { color: #fff; }\n.kuh-tabel-sidebar-icon {\n  width: 28px;\n  height: 28px;\n  border-radius: 50%;\n  border: 1.5px solid #8b939c;\n  display: flex;\n  align-items: center;\n  justify-content: center;\n  position: relative;\n  box-sizing: border-box;\n}\n.kuh-tabel-sidebar-dot {\n  width: 10px;\n  height: 10px;\n  border-radius: 50%;\n  background: #7ed321;\n  box-shadow: 0 0 0 2px rgba(126, 211, 33, 0.25);\n}\n.kuh-tabel-sidebar-label {\n  font-size: 10px;\n  line-height: 1.1;\n  font-weight: 600;\n  text-align: center;\n  max-width: 64px;\n}\n.kuh-tabel-sidebar--dock {\n  position: fixed;\n  left: 0;\n  bottom: 88px;\n  z-index: 12000;\n  width: 68px;\n}\n\n\n/* critical containment */\n.kuh-tabel-avatar,\n.kuh-tabel-avatar img {\n  max-width: 56px !important;\n  max-height: 56px !important;\n}\n.kuh-tabel-overlay {\n  isolation: isolate;\n  overflow: auto;\n}\n.kuh-tabel-overlay img {\n  max-width: 96px !important;\n  max-height: 96px !important;\n}\n"; // <TABEL_CSS>

    function settings() {
      return self.get_settings() || {};
    }

    function apiBase() {
      var base = (settings().api_base || "").trim().replace(/\/$/, "");
      if (!base) {
        base = "https://kuh-ai-api.onrender.com";
      }
      return base;
    }

    function apiToken() {
      return (settings().api_token || "").trim();
    }

    function currentUser() {
      var u = {};
      try {
        if (typeof APP !== "undefined" && typeof APP.constant === "function") {
          u = APP.constant("user") || {};
        }
      } catch (e) {}
      try {
        if ((!u || !u.id) && typeof AMOCRM !== "undefined" && AMOCRM.constant) {
          u = AMOCRM.constant("user") || u;
        }
      } catch (e2) {}
      return u || {};
    }

    function isAdminUser(user) {
      user = user || currentUser();
      if (!user) return false;
      if (user.is_admin === true || user.is_admin === "Y" || user.is_admin === 1) {
        return true;
      }
      var r = user.rights || {};
      return r.is_admin === true || r.admin === true || r.is_admin === "Y";
    }

    function allowedUserIds() {
      var raw = settings().allowed_users;
      var ids = [];
      function push(v) {
        var n = parseInt(v, 10);
        if (n && ids.indexOf(n) === -1) ids.push(n);
      }
      if (!raw) return ids;
      if (typeof raw === "string") {
        raw.split(/[,;\s]+/).forEach(push);
        return ids;
      }
      if (typeof raw === "object") {
        Object.keys(raw).forEach(function (k) {
          var item = raw[k];
          if (item === true || item === "1" || item === 1 || item === "true") {
            push(k);
            return;
          }
          if (item && typeof item === "object") {
            if (
              item.checked === "1" ||
              item.checked === 1 ||
              item.checked === true ||
              item.id
            ) {
              push(item.id || k);
            }
          }
        });
      }
      return ids;
    }

    function userHasAccess() {
      var ids = allowedUserIds();
      if (!ids.length) return true;
      var id = parseInt((currentUser() || {}).id, 10);
      return ids.indexOf(id) !== -1;
    }

    function amoConstant(name) {
      try {
        if (typeof APP !== "undefined" && APP.constant) {
          var a = APP.constant(name);
          if (a) return a;
        }
      } catch (e0) {}
      try {
        if (typeof AMOCRM !== "undefined" && AMOCRM.constant) {
          var b = AMOCRM.constant(name);
          if (b) return b;
        }
      } catch (e1) {}
      return {};
    }

    function managersMap() {
      return amoConstant("managers") || {};
    }

    function amoOnlineMap() {
      var out = {};
      var sdk = null;
      try {
        sdk =
          (typeof APP !== "undefined" && APP.sdk) ||
          (typeof AMOCRM !== "undefined" && AMOCRM.sdk) ||
          null;
      } catch (e0) {}
      if (!sdk || typeof sdk.showUserStatus !== "function") return out;
      try {
        var all = sdk.showUserStatus();
        if (all && typeof all === "object" && !Array.isArray(all)) {
          Object.keys(all).forEach(function (k) {
            var item = all[k];
            var oid = parseInt((item && item.id) || k, 10);
            var on =
              item === true ||
              (item && (item.online === true || item.online === "Y" || item.online === 1));
            if (oid) out[oid] = !!on;
          });
        }
      } catch (e1) {}
      try {
        var ids = sdk.showUserStatus("online");
        if (Array.isArray(ids)) {
          ids.forEach(function (id) {
            var n = parseInt(id, 10);
            if (n) out[n] = true;
          });
        }
      } catch (e2) {}
      return out;
    }

    function applyAmoOnline() {
      if (!state || !state.users) return;
      var map = amoOnlineMap();
      var meId = parseInt((currentUser() || {}).id, 10) || 0;
      if (meId) map[meId] = true;
      state.users.forEach(function (u) {
        u.online = !!map[u.id];
      });
      if (state.me) state.me.online = !!map[state.me.id] || state.me.id === meId;
      if (state.summary) {
        state.summary.online = state.users.filter(function (u) {
          return u.online;
        }).length;
      }
    }

    function localStatuses() {
      try {
        return JSON.parse(localStorage.getItem("kuh_tabel_status") || "{}");
      } catch (e) {
        return {};
      }
    }

    function saveLocalStatus(uid, code) {
      var all = localStatuses();
      all[String(uid)] = code || "";
      try {
        localStorage.setItem("kuh_tabel_status", JSON.stringify(all));
      } catch (e2) {}
    }

    function localBuckets() {
      try {
        return JSON.parse(localStorage.getItem("kuh_tabel_buckets") || "{}");
      } catch (e) {
        return {};
      }
    }

    function saveLocalBucket(uid) {
      var all = localBuckets();
      var key = String(uid);
      var list = all[key] || [];
      var b = Math.floor(Date.now() / 1000 / 300) * 300;
      if (list.indexOf(b) === -1) list.push(b);
      var cut = Math.floor(Date.now() / 1000) - 14 * 86400;
      all[key] = list.filter(function (x) {
        return x >= cut;
      });
      try {
        localStorage.setItem("kuh_tabel_buckets", JSON.stringify(all));
      } catch (e3) {}
    }

    function hoursFromBuckets(buckets, start, end) {
      var n = 0;
      (buckets || []).forEach(function (x) {
        if (x >= start && x < end) n += 1;
      });
      return Math.round(((n * 5) / 60) * 100) / 100;
    }

    function defaultCatalog() {
      return [
        { code: "vacation", name: "В отпуске", color: "#f5a623" },
        { code: "remote", name: "Удалённо", color: "#4c8bf5" },
        { code: "sick", name: "Больничный", color: "#e74c3c" },
      ];
    }

    function buildLocalState() {
      var managers = amoConstant("managers") || {};
      var groups = amoConstant("groups") || {};
      var sts = localStatuses();
      var bucks = localBuckets();
      var me = currentUser() || {};
      var meId = parseInt(me.id, 10) || 0;
      var list = [];
      if (Array.isArray(managers)) list = managers;
      else {
        Object.keys(managers).forEach(function (k) {
          if (managers[k] && typeof managers[k] === "object") {
            list.push(managers[k]);
          }
        });
      }
      var onlineMap = amoOnlineMap();
      if (meId) onlineMap[meId] = true;
      var day0 = new Date();
      day0.setHours(0, 0, 0, 0);
      var t0 = Math.floor(day0.getTime() / 1000);
      var t1 = t0 + 86400;
      var w0 = t0 - 6 * 86400;
      var users = [];
      list.forEach(function (m) {
        if (!m) return;
        var id = parseInt(m.id || m.user_id, 10);
        if (!id) return;
        if (m.active === false || m.active === "N" || m.is_active === false) {
          return;
        }
        var gid = parseInt(m.group_id || m.group || 0, 10) || 0;
        var gobj = groups[gid] || groups[String(gid)] || {};
        var gname = gobj.name || gobj.title || m.group_name || "";
        var buckets = bucks[String(id)] || [];
        users.push({
          id: id,
          name: m.title || m.option || m.name || "User " + id,
          email: m.login || m.email || "",
          phone: m.phone || "",
          role: m.role || "",
          photo: m.photo || m.avatar || "",
          is_admin: m.is_admin === "Y" || m.is_admin === true,
          group_id: gid,
          group_name: gname || "Без группы",
          online: !!onlineMap[id],
          status: sts[String(id)] || "",
          leads: parseInt(m.leads || m.leads_count || 0, 10) || 0,
          last_seen: id === meId ? Math.floor(Date.now() / 1000) : 0,
          last_active: 0,
          buckets: buckets,
          hours_today: hoursFromBuckets(buckets, t0, t1),
          hours_week: hoursFromBuckets(buckets, w0, t1),
          first_active_today: 0,
          last_active_today: 0,
          today: {},
          week: {},
        });
      });
      users.sort(function (a, b) {
        return (a.name || "").localeCompare(b.name || "", "ru");
      });
      var meUser =
        users.filter(function (u) {
          return u.id === meId;
        })[0] || {
          id: meId,
          name: me.name || me.title || "Вы",
          email: me.login || me.email || "",
          online: true,
          status: sts[String(meId)] || "",
          leads: 0,
          hours_today: 0,
          hours_week: 0,
          buckets: bucks[String(meId)] || [],
        };
      return {
        ok: true,
        statuses: defaultCatalog(),
        users: users,
        me: meUser,
        summary: {
          total: users.length,
          online: users.filter(function (u) {
            return u.online;
          }).length,
          idle_today: users.filter(function (u) {
            return !u.hours_today;
          }).length,
          hours_today: users.reduce(function (s, u) {
            return s + (u.hours_today || 0);
          }, 0),
          hours_week: users.reduce(function (s, u) {
            return s + (u.hours_week || 0);
          }, 0),
          vacation: users.filter(function (u) {
            return u.status === "vacation";
          }).length,
          remote: users.filter(function (u) {
            return u.status === "remote";
          }).length,
          calls_today: 0,
          leads_created_today: 0,
        },
      };
    }

    function mergeApiState(remote) {
      var local = state && state.users && state.users.length ? state : buildLocalState();
      if (!remote) {
        state = local;
        return;
      }
      var map = {};
      var amoOn = amoOnlineMap();
      (local.users || []).forEach(function (u) {
        map[u.id] = u;
      });
      (remote.users || []).forEach(function (u) {
        var prev = map[u.id] || {};
        map[u.id] = $.extend({}, prev, u, {
          photo: u.photo || prev.photo,
          name: u.name || prev.name,
          email: u.email || prev.email,
          group_name: u.group_name || prev.group_name,
          online: !!(u.online || prev.online || amoOn[u.id]),
        });
      });
      var users = [];
      Object.keys(map).forEach(function (k) {
        users.push(map[k]);
      });
      state = $.extend({}, local, remote, {
        users: users,
        me: remote.me || local.me,
        statuses: remote.statuses && remote.statuses.length ? remote.statuses : local.statuses,
        summary: remote.summary || local.summary,
      });
    }


    function injectCss() {
      if (!document.getElementById("kuh-tabel-css-inline")) {
        var st = document.createElement("style");
        st.id = "kuh-tabel-css-inline";
        st.textContent = EMBEDDED_CSS || "";
        document.head.appendChild(st);
      }
      if (document.getElementById("kuh-tabel-css")) return;
      var code = "";
      try {
        code = (settings().widget_code || "").toString();
      } catch (e0) {}
      if (!code) {
        try {
          code = (self.params && self.params.widget_code) || "";
        } catch (e1) {}
      }
      if (!code) {
        try {
          code = (self.get_settings() || {}).widget_code || "";
        } catch (e2) {}
      }
      code = String(code || "").replace(/[^\w\-]/g, "");
      if (!code) return;
      var href =
        "/widgets/" +
        code +
        "/style.css?v=" +
        (self.get_version ? self.get_version() : "131");
      var link = document.createElement("link");
      link.id = "kuh-tabel-css";
      link.rel = "stylesheet";
      link.href = href;
      document.head.appendChild(link);
    }

    function api(path, opts) {
      opts = opts || {};
      var headers = { "Content-Type": "application/json" };
      var tok = apiToken();
      if (tok) headers["X-Api-Token"] = tok;
      return $.ajax({
        url: apiBase() + path,
        method: opts.method || "GET",
        data: opts.body ? JSON.stringify(opts.body) : undefined,
        headers: headers,
        timeout: 20000,
      });
    }

    function initials(name) {
      var parts = String(name || "")
        .trim()
        .split(/\s+/);
      if (!parts[0]) return "?";
      var a = parts[0].charAt(0);
      var b = parts.length > 1 ? parts[1].charAt(0) : parts[0].charAt(1) || "";
      return (a + b).toUpperCase();
    }

    function avatarColor(id) {
      var palette = ["#7aa2d4", "#8fbf7a", "#d4a15a", "#c989b0", "#7ec4c4", "#c9a27a"];
      return palette[Math.abs(parseInt(id, 10) || 0) % palette.length];
    }

    function esc(s) {
      return String(s == null ? "" : s)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }

    function photoOf(user) {
      var m = managersMap()[user.id] || managersMap()[String(user.id)] || {};
      return m.photo || m.avatar || user.photo || "";
    }

    function displayName(user) {
      var m = managersMap()[user.id] || managersMap()[String(user.id)] || {};
      return user.name || m.title || m.option || m.name || "Сотрудник";
    }

    function statusByCode(code) {
      var list = (state && state.statuses) || [];
      for (var i = 0; i < list.length; i++) {
        if (list[i].code === code) return list[i];
      }
      return null;
    }

    function pad2(n) {
      return (n < 10 ? "0" : "") + n;
    }

    function minToHm(m) {
      m = Math.max(0, Math.min(24 * 60, m));
      return pad2(Math.floor(m / 60)) + ":" + pad2(m % 60);
    }

    function fmtHours(h) {
      h = Number(h) || 0;
      if (h <= 0) return "0ч";
      var hours = Math.floor(h);
      var mins = Math.round((h - hours) * 60);
      if (mins === 60) {
        hours += 1;
        mins = 0;
      }
      if (!hours) return mins + "м";
      if (!mins) return hours + "ч";
      return hours + "ч " + mins + "м";
    }

    function fmtTime(ts) {
      if (!ts) return "—";
      var d = new Date(ts * 1000);
      return pad2(d.getHours()) + ":" + pad2(d.getMinutes());
    }

    function fmtAgo(ts) {
      if (!ts) return "не был в системе";
      var sec = Math.max(0, Math.floor(Date.now() / 1000 - ts));
      if (sec < 60) return "только что";
      if (sec < 3600) return Math.floor(sec / 60) + " мин назад";
      if (sec < 86400) return Math.floor(sec / 3600) + " ч назад";
      return Math.floor(sec / 86400) + " дн назад";
    }

    function fmtCallDur(sec) {
      sec = Number(sec) || 0;
      if (sec <= 0) return "";
      if (sec < 60) return sec + "с";
      return Math.round(sec / 60) + " мин";
    }

    function rangesForDay(buckets, dayStart) {
      var slots = {};
      var dayEnd = dayStart + 86400000;
      (buckets || []).forEach(function (ts) {
        var ms = ts * 1000;
        if (ms < dayStart || ms >= dayEnd) return;
        var d = new Date(ms);
        var min = d.getHours() * 60 + d.getMinutes();
        min = Math.floor(min / 5) * 5;
        slots[min] = true;
      });
      var keys = Object.keys(slots)
        .map(function (x) {
          return parseInt(x, 10);
        })
        .sort(function (a, b) {
          return a - b;
        });
      var ranges = [];
      var i = 0;
      while (i < keys.length) {
        var from = keys[i];
        var to = from + 5;
        while (i + 1 < keys.length && keys[i + 1] === to) {
          i += 1;
          to += 5;
        }
        ranges.push({ from: from, to: to });
        i += 1;
      }
      return ranges;
    }

    function hoursForDay(buckets, dayStart) {
      var ranges = rangesForDay(buckets, dayStart);
      var mins = 0;
      ranges.forEach(function (r) {
        mins += r.to - r.from;
      });
      return mins / 60;
    }

    function barHtml(buckets, dayStart) {
      var ranges = rangesForDay(buckets, dayStart);
      var segs = ranges
        .map(function (r) {
          var left = (r.from / 1440) * 100;
          var width = Math.max(((r.to - r.from) / 1440) * 100, 0.4);
          var title = minToHm(r.from) + "–" + minToHm(r.to);
          return (
            '<i class="kuh-tabel-seg" title="' +
            title +
            '" style="left:' +
            left.toFixed(3) +
            "%;width:" +
            width.toFixed(3) +
            '%"></i>'
          );
        })
        .join("");
      return '<div class="kuh-tabel-bar">' + segs + "</div>";
    }

    function hoursHtml() {
      return (
        '<div class="kuh-tabel-hours"><span>0</span><span>6</span><span>12</span><span>18</span><span>24</span></div>'
      );
    }

    function startOfToday() {
      var d = new Date();
      d.setHours(0, 0, 0, 0);
      return d.getTime();
    }

    function avatarHtml(user, extraClass) {
      var photo = photoOf(user);
      var inner = photo
        ? '<img src="' + esc(photo) + '" alt="" width="44" height="44" style="width:44px;height:44px;object-fit:cover;display:block">'
        : esc(initials(displayName(user)));
      return (
        '<div class="kuh-tabel-avatar ' +
        (extraClass || "") +
        '" style="background:' +
        avatarColor(user.id) +
        '">' +
        inner +
        '<span class="kuh-tabel-dot' +
        (user.online ? " on" : "") +
        '"></span></div>'
      );
    }

    function statusSelectHtml(user) {
      var list = (state && state.statuses) || [];
      var opts =
        '<option value="">Без статуса</option>' +
        list
          .map(function (s) {
            var sel = user.status === s.code ? " selected" : "";
            return (
              '<option value="' +
              esc(s.code) +
              '"' +
              sel +
              ">" +
              esc(s.name) +
              "</option>"
            );
          })
          .join("");
      return (
        '<select class="kuh-tabel-select kuh-tabel-status-pick" data-user="' +
        user.id +
        '">' +
        opts +
        "</select>"
      );
    }

    function badgeHtml(user) {
      var st = statusByCode(user.status);
      if (!st) return "";
      return (
        '<span class="kuh-tabel-badge" style="background:' +
        esc(st.color) +
        "22;color:" +
        esc(st.color) +
        '">' +
        esc(st.name) +
        "</span>"
      );
    }

    function dayLabel(offset) {
      var d = new Date(startOfToday() - offset * 86400000);
      if (offset === 0) return "Сегодня";
      if (offset === 1) return "Вчера";
      return d.toLocaleDateString("ru-RU", {
        weekday: "short",
        day: "2-digit",
        month: "2-digit",
      });
    }

    function statBox(value, label) {
      return (
        '<div class="kuh-tabel-stat"><b>' +
        esc(String(value)) +
        "</b><span>" +
        esc(label) +
        "</span></div>"
      );
    }

    function expandHtml(user) {
      if (!expanded[user.id]) return "";
      var t = user.today || {};
      var w = user.week || {};
      var callDur = fmtCallDur(t.call_sec);
      var quality =
        t.quality != null ? t.quality : w.quality != null ? w.quality : "—";
      var rows = [];
      var i;
      for (i = 0; i < 7; i++) {
        var start = startOfToday() - i * 86400000;
        var h = hoursForDay(user.buckets, start);
        rows.push(
          '<div class="kuh-tabel-dayline"><div class="kuh-tabel-day-label">' +
            dayLabel(i) +
            "</div><div>" +
            barHtml(user.buckets, start) +
            hoursHtml() +
            '</div><div class="kuh-tabel-day-h">' +
            fmtHours(h) +
            "</div></div>"
        );
      }
      var contacts =
        '<div class="kuh-tabel-contacts">' +
        (user.email
          ? '<span>' +
            esc(user.email) +
            ' <button type="button" class="kuh-tabel-copy" data-copy="' +
            esc(user.email) +
            '">копировать</button></span>'
          : "") +
        (user.phone ? "<span>" + esc(user.phone) + "</span>" : "") +
        (user.role ? "<span>" + esc(user.role) + "</span>" : "") +
        "<span>был: " +
        fmtAgo(user.last_active || user.last_seen) +
        "</span></div>";
      return (
        '<div class="kuh-tabel-expand">' +
        '<div class="kuh-tabel-stats">' +
        statBox(fmtHours(user.hours_today), "сегодня в CRM") +
        statBox(fmtHours(user.hours_week), "за 7 дней") +
        statBox(fmtTime(user.first_active_today), "первый заход") +
        statBox(fmtTime(user.last_active_today), "последняя активность") +
        statBox(
          (t.calls || 0) + (callDur ? " · " + callDur : ""),
          "звонки сегодня"
        ) +
        statBox(quality, "качество диалогов") +
        statBox(t.chats || 0, "чаты сегодня") +
        statBox(t.notes || 0, "заметки сегодня") +
        statBox(t.leads_created || 0, "создано сделок") +
        statBox(t.leads_won || 0, "выиграно сегодня") +
        statBox(t.leads_lost || 0, "проиграно") +
        statBox(user.leads || 0, "открытых сделок") +
        "</div>" +
        "<div>" +
        rows.join("") +
        "</div>" +
        contacts +
        "</div>"
      );
    }

    function filterUsers(users) {
      var q = qSearch.trim().toLowerCase();
      return (users || []).filter(function (u) {
        if (q) {
          var blob = (
            displayName(u) +
            " " +
            (u.email || "") +
            " " +
            (u.role || "")
          ).toLowerCase();
          if (blob.indexOf(q) === -1) return false;
        }
        if (qStatus === "online") return !!u.online;
        if (qStatus === "idle") return !u.hours_today;
        if (qStatus && qStatus !== "all") return u.status === qStatus;
        return true;
      });
    }

    function sortUsers(users) {
      var list = users.slice();
      list.sort(function (a, b) {
        if (qSort === "hours") {
          return (b.hours_today || 0) - (a.hours_today || 0);
        }
        if (qSort === "week") {
          return (b.hours_week || 0) - (a.hours_week || 0);
        }
        if (qSort === "online") {
          if (!!a.online !== !!b.online) return a.online ? -1 : 1;
          return (b.last_active || 0) - (a.last_active || 0);
        }
        if (qSort === "leads") {
          return (b.leads || 0) - (a.leads || 0);
        }
        return displayName(a).localeCompare(displayName(b), "ru");
      });
      return list;
    }

    function groupUsers(users) {
      var map = {};
      var order = [];
      users.forEach(function (u) {
        var key = String(u.group_id || 0);
        if (!map[key]) {
          map[key] = {
            id: u.group_id || 0,
            name: u.group_name || "Без группы",
            users: [],
          };
          order.push(key);
        }
        map[key].users.push(u);
      });
      return order.map(function (k) {
        return map[k];
      });
    }

    function userRowHtml(user, meId) {
      var today = startOfToday();
      var open = !!expanded[user.id];
      return (
        '<div class="kuh-tabel-card' +
        (open ? " open" : "") +
        '" data-card="' +
        user.id +
        '">' +
        '<div class="kuh-tabel-row' +
        (user.id === meId ? " is-me" : "") +
        '" data-expand="' +
        user.id +
        '">' +
        avatarHtml(user) +
        '<div class="kuh-tabel-user-cell"><div class="kuh-tabel-name">' +
        esc(displayName(user)) +
        " " +
        badgeHtml(user) +
        '</div><div class="kuh-tabel-meta">' +
        (user.online ? "онлайн" : fmtAgo(user.last_seen)) +
        (user.role ? " · " + esc(user.role) : "") +
        "</div></div>" +
        '<div class="kuh-tabel-hours-cell">' +
        fmtHours(user.hours_today) +
        "<small>неделя " +
        fmtHours(user.hours_week) +
        "</small></div>" +
        '<div class="kuh-tabel-bar-wrap">' +
        barHtml(user.buckets, today) +
        hoursHtml() +
        "</div>" +
        statusSelectHtml(user) +
        '<button type="button" class="kuh-tabel-chevron" data-expand="' +
        user.id +
        '" aria-label="Развернуть">' +
        (open ? "▾" : "▸") +
        "</button></div>" +
        expandHtml(user) +
        "</div>"
      );
    }

    function filterOptionsHtml() {
      var list = (state && state.statuses) || [];
      return (
        '<option value="all">Все статусы</option>' +
        '<option value="online"' +
        (qStatus === "online" ? " selected" : "") +
        ">Онлайн</option>" +
        '<option value="idle"' +
        (qStatus === "idle" ? " selected" : "") +
        ">Без активности сегодня</option>" +
        list
          .map(function (s) {
            return (
              '<option value="' +
              esc(s.code) +
              '"' +
              (qStatus === s.code ? " selected" : "") +
              ">" +
              esc(s.name) +
              "</option>"
            );
          })
          .join("")
      );
    }

    function sortOptionsHtml() {
      var opts = [
        ["name", "По имени"],
        ["hours", "По часам сегодня"],
        ["week", "По часам за неделю"],
        ["online", "Сначала онлайн"],
        ["leads", "По числу сделок"],
      ];
      return opts
        .map(function (p) {
          return (
            '<option value="' +
            p[0] +
            '"' +
            (qSort === p[0] ? " selected" : "") +
            ">" +
            p[1] +
            "</option>"
          );
        })
        .join("");
    }

    function summaryHtml() {
      var s = (state && state.summary) || {};
      return (
        '<div class="kuh-tabel-summary">' +
        '<div class="kuh-tabel-kpi"><b>' +
        (s.total || 0) +
        "</b><span>сотрудников</span></div>" +
        '<div class="kuh-tabel-kpi on"><b>' +
        (s.online || 0) +
        "</b><span>онлайн сейчас</span></div>" +
        '<div class="kuh-tabel-kpi warn"><b>' +
        (s.idle_today || 0) +
        "</b><span>без активности</span></div>" +
        '<div class="kuh-tabel-kpi"><b>' +
        fmtHours(s.hours_today) +
        "</b><span>часов команды сегодня</span></div>" +
        '<div class="kuh-tabel-kpi"><b>' +
        (s.calls_today || 0) +
        "</b><span>звонков сегодня</span></div>" +
        '<div class="kuh-tabel-kpi"><b>' +
        (s.leads_created_today || 0) +
        "</b><span>новых сделок</span></div>" +
        "</div>"
      );
    }

    function renderBody() {
      if (!state) {
        return '<div class="kuh-tabel-loading">Загрузка сотрудников…</div>';
      }
      var meId = parseInt((currentUser() || {}).id, 10);
      var users = sortUsers(filterUsers(state.users || []));
      if (!users.length) {
        return '<div class="kuh-tabel-empty">Никого не найдено</div>';
      }
      var groups = groupUsers(users);
      return groups
        .map(function (g) {
          var collapsed = !!collapsedGroups[g.id];
          var head =
            '<div class="kuh-tabel-group" data-group="' +
            g.id +
            '">' +
            (collapsed ? "▸ " : "▾ ") +
            esc(g.name) +
            " · " +
            g.users.length +
            "</div>";
          if (collapsed) return head;
          return (
            head +
            g.users
              .map(function (u) {
                return userRowHtml(u, meId);
              })
              .join("")
          );
        })
        .join("");
    }

    function meBlock() {
      var meId = parseInt((currentUser() || {}).id, 10);
      var me =
        (state && state.me) ||
        ((state && state.users) || []).filter(function (u) {
          return u.id === meId;
        })[0] ||
        {
          id: meId,
          name: (currentUser() || {}).name || "Вы",
          email: (currentUser() || {}).login || (currentUser() || {}).email || "",
          online: true,
          status: "",
          leads: 0,
          hours_today: 0,
          hours_week: 0,
          buckets: [],
        };
      return (
        '<div class="kuh-tabel-me">' +
        avatarHtml(me) +
        '<div class="kuh-tabel-me-main"><div class="kuh-tabel-name">' +
        esc(displayName(me)) +
        '</div><div class="kuh-tabel-meta">' +
        esc(me.email || "") +
        " · сегодня " +
        fmtHours(me.hours_today) +
        " · неделя " +
        fmtHours(me.hours_week) +
        "</div></div>" +
        '<div class="kuh-tabel-me-right"><span class="kuh-tabel-leads">' +
        (me.leads || 0) +
        " сделок</span>" +
        statusSelectHtml(me) +
        "</div></div>"
      );
    }

    function adminFoot() {
      var hint =
        "Клик по сотруднику — карточка: часы, звонки, сделки и 7 дней. Наведи на зелёный кусок — время.";
      if (!isAdminUser()) {
        return (
          '<div class="kuh-tabel-foot"><span class="kuh-tabel-hint">' +
          hint +
          "</span></div>"
        );
      }
      var chips = ((state && state.statuses) || [])
        .map(function (s) {
          return (
            '<span class="kuh-tabel-badge" data-del="' +
            esc(s.code) +
            '" title="Удалить" style="cursor:pointer;background:' +
            esc(s.color) +
            "22;color:" +
            esc(s.color) +
            '">' +
            esc(s.name) +
            " ×</span>"
          );
        })
        .join("");
      return (
        '<div class="kuh-tabel-foot">' +
        chips +
        '<input class="kuh-tabel-search" id="kuh-tabel-new-status" placeholder="Новый статус" style="flex:0 0 160px;height:32px">' +
        '<button type="button" class="kuh-tabel-add" id="kuh-tabel-add-status">Добавить</button>' +
        '<span class="kuh-tabel-hint">' +
        hint +
        "</span></div>"
      );
    }

    function innerShellHtml(withClose) {
      return (
        '<div class="kuh-tabel-modal">' +
        '<div class="kuh-tabel-head"><div class="kuh-tabel-title">Табель</div>' +
        (withClose
          ? '<button type="button" class="kuh-tabel-close" id="kuh-tabel-close">×</button>'
          : "") +
        "</div>" +
        '<div id="kuh-tabel-me-slot"></div>' +
        '<div id="kuh-tabel-summary-slot"></div>' +
        '<div class="kuh-tabel-toolbar">' +
        '<input class="kuh-tabel-search" id="kuh-tabel-search" placeholder="Найти сотрудника, email, роль">' +
        '<select class="kuh-tabel-filter" id="kuh-tabel-filter"></select>' +
        '<select class="kuh-tabel-filter" id="kuh-tabel-sort"></select>' +
        '<button type="button" class="kuh-tabel-ghost" id="kuh-tabel-expand-all">Развернуть всех</button>' +
        "</div>" +
        '<div class="kuh-tabel-err" id="kuh-tabel-err"></div>' +
        '<div class="kuh-tabel-body" id="kuh-tabel-body"></div>' +
        '<div id="kuh-tabel-foot-slot"></div>' +
        "</div>"
      );
    }

    function modalHtml() {
      return (
        '<div class="kuh-tabel-overlay" id="kuh-tabel-overlay">' +
        innerShellHtml(true) +
        "</div>"
      );
    }

    function pageHtml() {
      return (
        '<div class="kuh-tabel-page" id="kuh-tabel-page-root">' +
        innerShellHtml(false) +
        "</div>"
      );
    }

    function paint() {
      if (!$("#kuh-tabel-overlay, #kuh-tabel-page-root").length) return;
      applyAmoOnline();
      $("#kuh-tabel-me-slot").html(state ? meBlock() : "");
      $("#kuh-tabel-summary-slot").html(state ? summaryHtml() : "");
      $("#kuh-tabel-filter").html(filterOptionsHtml());
      $("#kuh-tabel-sort").html(sortOptionsHtml());
      $("#kuh-tabel-search").val(qSearch);
      $("#kuh-tabel-filter").val(qStatus || "all");
      $("#kuh-tabel-sort").val(qSort || "name");
      $("#kuh-tabel-body").html(renderBody());
      $("#kuh-tabel-foot-slot").html(adminFoot());
    }

    function loadState() {
      state = buildLocalState();
      paint();
      var uid = parseInt((currentUser() || {}).id, 10) || 0;
      return api("/api/v1/tabel/state?user_id=" + uid)
        .done(function (data) {
          mergeApiState(data);
          paint();
        })
        .fail(function () {
          paint();
        });
    }

    function closeModal() {
      $("#kuh-tabel-overlay").remove();
    }

    function openModal() {
      if (!userHasAccess()) return;
      injectCss();
      closeModal();
      $("body").append(modalHtml());
      state = buildLocalState();
      paint();
      loadState();
      if (onlineTimer) clearInterval(onlineTimer);
      onlineTimer = setInterval(function () {
        if ($("#kuh-tabel-overlay, #kuh-tabel-page-root").length) {
          applyAmoOnline();
          paint();
        }
      }, 10000);
    }

    function toggleExpand(id) {
      if (!id) return;
      expanded[id] = !expanded[id];
      $("#kuh-tabel-body").html(renderBody());
    }

    function bindModal() {
      $(document)
        .off(".kuhtabel")
        .on("click.kuhtabel", "#kuh-tabel-close, #kuh-tabel-overlay", function (e) {
          if (e.target === this) closeModal();
        })
        .on("click.kuhtabel", ".kuh-tabel-modal", function (e) {
          e.stopPropagation();
        })
        .on("input.kuhtabel", "#kuh-tabel-search", function () {
          qSearch = $(this).val() || "";
          $("#kuh-tabel-body").html(renderBody());
        })
        .on("change.kuhtabel", "#kuh-tabel-filter", function () {
          qStatus = $(this).val() || "all";
          $("#kuh-tabel-body").html(renderBody());
        })
        .on("change.kuhtabel", "#kuh-tabel-sort", function () {
          qSort = $(this).val() || "name";
          $("#kuh-tabel-body").html(renderBody());
        })
        .on("click.kuhtabel", "#kuh-tabel-expand-all", function () {
          var users = (state && state.users) || [];
          var allOpen = users.length && users.every(function (u) {
            return expanded[u.id];
          });
          users.forEach(function (u) {
            expanded[u.id] = !allOpen;
          });
          $(this).text(allOpen ? "Развернуть всех" : "Свернуть всех");
          $("#kuh-tabel-body").html(renderBody());
        })
        .on("click.kuhtabel", ".kuh-tabel-group", function () {
          var gid = $(this).attr("data-group");
          collapsedGroups[gid] = !collapsedGroups[gid];
          $("#kuh-tabel-body").html(renderBody());
        })
        .on("click.kuhtabel", "[data-expand]", function (e) {
          if ($(e.target).closest("select, button.kuh-tabel-copy, a").length) {
            return;
          }
          e.preventDefault();
          e.stopPropagation();
          toggleExpand(parseInt($(this).attr("data-expand"), 10));
        })
        .on("click.kuhtabel", ".kuh-tabel-copy", function (e) {
          e.preventDefault();
          e.stopPropagation();
          var t = $(this).attr("data-copy") || "";
          if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(t);
            $(this).text("скопировано");
          }
        })
        .on("change.kuhtabel", ".kuh-tabel-status-pick", function (e) {
          e.stopPropagation();
          var uid = parseInt($(this).attr("data-user"), 10);
          var code = $(this).val() || "";
          var actor = parseInt((currentUser() || {}).id, 10) || uid;
          saveLocalStatus(uid, code);
          if (state && state.users) {
            state.users.forEach(function (u) {
              if (u.id === uid) u.status = code;
            });
            if (state.me && state.me.id === uid) state.me.status = code;
          }
          paint();
          api("/api/v1/tabel/status", {
            method: "POST",
            body: { user_id: uid, status: code, actor_id: actor },
          }).fail(function () {});
        })
        .on("click.kuhtabel", "#kuh-tabel-add-status", function () {
          var name = ($("#kuh-tabel-new-status").val() || "").trim();
          if (!name) return;
          api("/api/v1/tabel/statuses", {
            method: "POST",
            body: { name: name, color: "#6b7280" },
          }).done(function () {
            loadState();
          });
        })
        .on("click.kuhtabel", ".kuh-tabel-badge[data-del]", function () {
          var code = $(this).attr("data-del");
          if (!code) return;
          api("/api/v1/tabel/statuses/" + encodeURIComponent(code), {
            method: "DELETE",
          }).done(function () {
            loadState();
          });
        })
        .on("keydown.kuhtabel", function (e) {
          if (e.key === "Escape") closeModal();
        });
    }


    function injectMenuItem() {
      /* no logout menu entry */
      return;
    }

    function injectSidebarItem() {
      if (!userHasAccess()) return;
      var existing = document.getElementById("kuh-tabel-sidebar");
      if (existing) {
        if (!existing.classList.contains("kuh-tabel-sidebar--dock")) {
          existing.classList.add("kuh-tabel-sidebar--dock");
        }
        if (existing.parentNode !== document.body) {
          document.body.appendChild(existing);
        }
        return;
      }

      injectCss();

      var LABEL_SETTINGS = "\u041d\u0430\u0441\u0442\u0440\u043e\u0439\u043a\u0438";
      var LABEL_AMOMARKET = "amo\u041c\u0430\u0440\u043a\u0435\u0442";
      var LABEL_TABEL = "\u0422\u0430\u0431\u0435\u043b\u044c";

      var anchor = null;
      var nodes = document.querySelectorAll("a, button, div, li, span");
      for (var i = 0; i < nodes.length; i++) {
        var el = nodes[i];
        var href = ((el.getAttribute && el.getAttribute("href")) || "").toLowerCase();
        var t = (el.textContent || "").replace(/\s+/g, " ").trim();
        var byText =
          t === LABEL_SETTINGS ||
          t === "Settings" ||
          t === LABEL_AMOMARKET ||
          t === "amoMarket";
        var byHref =
          href.indexOf("settings") !== -1 || href.indexOf("amo-market") !== -1;
        if (byText || byHref) {
          anchor = el;
          if (
            t === LABEL_SETTINGS ||
            t === "Settings" ||
            href.indexOf("settings") !== -1
          ) {
            break;
          }
        }
      }

      var item = document.createElement("div");
      item.id = "kuh-tabel-sidebar";
      item.className = "kuh-tabel-sidebar kuh-tabel-sidebar--dock";
      item.setAttribute("role", "button");
      item.setAttribute("tabindex", "0");
      item.setAttribute("title", LABEL_TABEL);
      item.style.cssText =
        "position:fixed!important;left:0!important;bottom:88px!important;z-index:12000!important;" +
        "width:68px!important;display:flex;flex-direction:column;align-items:center;justify-content:center;" +
        "gap:4px;padding:10px 4px 8px;margin:0;cursor:pointer;user-select:none;color:#c5c9ce;" +
        "box-sizing:border-box;background:transparent;";
      item.innerHTML =
        '<div class="kuh-tabel-sidebar-icon" style="width:28px;height:28px;border-radius:50%;border:1.5px solid #8b939c;display:flex;align-items:center;justify-content:center;box-sizing:border-box;">' +
        '<span class="kuh-tabel-sidebar-dot" style="width:10px;height:10px;border-radius:50%;background:#7ed321;box-shadow:0 0 0 2px rgba(126,211,33,.25);"></span></div>' +
        '<div class="kuh-tabel-sidebar-label" style="font-size:10px;line-height:1.1;font-weight:600;text-align:center;max-width:64px;">' +
        LABEL_TABEL +
        "</div>";

      /* Prefer insert near Settings / amoMarket when found; always keep docked body fallback */
      var placed = false;
      if (anchor) {
        try {
          var cell =
            (anchor.closest &&
              anchor.closest(
                'a, button, li, [class*="nav"], [class*="menu"], [class*="aside"], [class*="sidebar"], [class*="Sidebar"]'
              )) ||
            anchor.parentNode;
          if (cell && cell.parentNode) {
            var href2 = (
              (anchor.getAttribute && anchor.getAttribute("href")) ||
              ""
            ).toLowerCase();
            var label = (anchor.textContent || "").replace(/\s+/g, " ").trim();
            var isSettings =
              label === LABEL_SETTINGS ||
              label === "Settings" ||
              href2.indexOf("settings") !== -1;
            if (isSettings) {
              cell.parentNode.insertBefore(item, cell);
            } else {
              if (cell.nextSibling) {
                cell.parentNode.insertBefore(item, cell.nextSibling);
              } else {
                cell.parentNode.appendChild(item);
              }
            }
            placed = document.getElementById("kuh-tabel-sidebar") !== null;
          }
        } catch (e1) {
          placed = false;
        }
      }

      /* Always append docked button on body as fallback (moves if already placed elsewhere) */
      if (!placed || item.parentNode !== document.body) {
        document.body.appendChild(item);
      }
    }

    function injectFab() {
      injectSidebarItem();
    }

    function startTracker() {
      if (heartbeatTimer) return;
      function mark() {
        lastInputAt = Date.now();
      }
      $(document).on("mousedown.kuhtabelact keydown.kuhtabelact", mark);
      lastInputAt = Date.now();
      function ping() {
        if (!userHasAccess()) return;
        var uid = parseInt((currentUser() || {}).id, 10);
        if (!uid) return;
        var active = Date.now() - lastInputAt < 5 * 60 * 1000;
        if (active) saveLocalBucket(uid);
        api("/api/v1/tabel/heartbeat", {
          method: "POST",
          body: { user_id: uid, active: active },
        }).fail(function () {});
      }
      ping();
      heartbeatTimer = setInterval(ping, 25000);
    }


    function startOnce() {
      if (started) {
        injectSidebarItem();
        return;
      }
      started = true;
      try {
        $("#kuh-tabel-fab, #kuh-tabel-menu-item").remove();
      } catch (e) {}
      injectCss();
      if (!userHasAccess()) return;
      bindModal();
      injectSidebarItem();
      startTracker();
      $(document)
        .off("click.kuhtabelopen")
        .on(
          "click.kuhtabelopen",
          "#kuh-tabel-sidebar, #kuh-tabel-fab, #kuh-tabel-menu-item",
          function (e) {
            e.preventDefault();
            e.stopPropagation();
            openModal();
          }
        );
      if (!observer) {
        observer = new MutationObserver(function () {
          injectSidebarItem();
        });
        observer.observe(document.body, { childList: true, subtree: true });
      }
      /* retry a few times — left rail mounts async */
      setTimeout(injectSidebarItem, 500);
      setTimeout(injectSidebarItem, 1500);
      setTimeout(injectSidebarItem, 4000);
    }

    function allowedInput() {
      var code = "";
      try {
        code = (settings().widget_code || "").toString();
      } catch (e) {}
      var $inp = $('input[name="allowed_users"], textarea[name="allowed_users"]');
      if (code) {
        var $byId = $("#" + code + "_allowed_users");
        if ($byId.length) $inp = $inp.add($byId);
      }
      return $inp.first();
    }

    function hideNativeAllowedField() {
      var $inp = $(
        'input[name="allowed_users"], textarea[name="allowed_users"]'
      );
      $inp.each(function () {
        var $el = $(this);
        $el.css({ position: "absolute", left: "-9999px", height: 0, opacity: 0 });
        $el
          .closest(
            ".widget_settings_block__item_field, .widget_settings_block__item, .widget_settings_block, tr, .form-group, .item"
          )
          .find("label")
          .filter(function () {
            return /пользовател|allowed/i.test($(this).text());
          })
          .hide();
      });
    }

    function writeAllowedUsers(val) {
      var $inp = allowedInput();
      if ($inp.length) {
        $inp.val(val).trigger("change").trigger("input");
      }
    }

    function settingsUsers() {
      var local = buildLocalState();
      return local.users || [];
    }

    function aclPanelHtml() {
      var users = settingsUsers();
      var selected = allowedUserIds();
      var allOn = !selected.length;
      var groups = {};
      var order = [];
      users.forEach(function (u) {
        var g = u.group_name || "Без группы";
        if (!groups[g]) {
          groups[g] = [];
          order.push(g);
        }
        groups[g].push(u);
      });
      var onCount = allOn
        ? users.length
        : users.filter(function (u) {
            return selected.indexOf(u.id) !== -1;
          }).length;
      var rows = order
        .map(function (g) {
          return (
            '<div class="kuh-acl-g">' +
            esc(g) +
            " · " +
            groups[g].length +
            "</div>" +
            groups[g]
              .map(function (u) {
                var on = allOn || selected.indexOf(u.id) !== -1;
                return (
                  '<div class="kuh-acl-row' +
                  (on ? "" : " is-off") +
                  '" data-acl-row="' +
                  u.id +
                  '">' +
                  avatarHtml(u) +
                  '<div class="kuh-acl-name">' +
                  esc(u.name) +
                  "<small>" +
                  esc(u.email || (u.online ? "онлайн" : "")) +
                  "</small></div>" +
                  '<label class="kuh-sw"><input type="checkbox" class="kuh-acl-one" data-user="' +
                  u.id +
                  '"' +
                  (on ? " checked" : "") +
                  (allOn ? " disabled" : "") +
                  "><i></i></label></div>"
                );
              })
              .join("")
          );
        })
        .join("");
      return (
        '<div class="kuh-acl" id="kuh-tabel-acl">' +
        '<div class="kuh-acl-head"><div><h3>Кто видит табель</h3>' +
        "<p>Включите ползунок — менеджер увидит кнопку и окно табеля в amoCRM.</p></div>" +
        '<span class="kuh-acl-count" id="kuh-acl-count">Включено ' +
        onCount +
        " из " +
        users.length +
        "</span></div>" +
        '<div class="kuh-acl-master"><div><b>Все сотрудники</b><div class="kuh-tabel-meta">Новые пользователи тоже получат доступ</div></div>' +
        '<label class="kuh-sw"><input type="checkbox" id="kuh-acl-all"' +
        (allOn ? " checked" : "") +
        "><i></i></label></div>" +
        '<input class="kuh-acl-search" id="kuh-acl-search" placeholder="Найти менеджера">' +
        '<div class="kuh-acl-list" id="kuh-acl-list">' +
        (rows || '<div class="kuh-tabel-empty">Нет сотрудников в аккаунте</div>') +
        "</div></div>"
      );
    }

    function syncAclFromUi() {
      var all = $("#kuh-acl-all").is(":checked");
      var ids = [];
      $(".kuh-acl-one").each(function () {
        var on = all || $(this).is(":checked");
        var id = parseInt($(this).attr("data-user"), 10);
        $(this).prop("disabled", all);
        $(this).prop("checked", on);
        $(this).closest(".kuh-acl-row").toggleClass("is-off", !on);
        if (on && id) ids.push(id);
      });
      var n = $(".kuh-acl-one").length;
      $("#kuh-acl-count").text("Включено " + (all ? n : ids.length) + " из " + n);
      writeAllowedUsers(all ? "" : ids.join(","));
    }

    function mountSettingsPanel() {
      injectCss();
      hideNativeAllowedField();
      var $fields = $("#widget_settings__fields");
      if (!$fields.length) {
        $fields = $(".widget_settings_block__fields, .widget_settings_block").first();
      }
      if (!$fields.length) return false;
      if (!$("#kuh-tabel-acl").length) {
        $fields.prepend(aclPanelHtml());
      }
      $(document)
        .off(".kuhacl")
        .on("change.kuhacl", "#kuh-acl-all, .kuh-acl-one", function () {
          if (this.id === "kuh-acl-all" && $(this).is(":checked")) {
            $(".kuh-acl-one").prop("checked", true);
          }
          syncAclFromUi();
        })
        .on("input.kuhacl", "#kuh-acl-search", function () {
          var q = ($(this).val() || "").toLowerCase();
          $("#kuh-acl-list .kuh-acl-row").each(function () {
            var t = ($(this).text() || "").toLowerCase();
            $(this).toggle(!q || t.indexOf(q) !== -1);
          });
        });
      syncAclFromUi();
      return true;
    }

    this.callbacks = {
      render: function () {
        var area = "";
        try {
          area = (self.system() || {}).area || "";
        } catch (e0) {}
        if (area === "widget_page") {
          injectCss();
        }
        return true;
      },
      init: function () {
        startOnce();
        return true;
      },
      bind_actions: function () {
        startOnce();
        var area = "";
        try {
          area = (self.system() || {}).area || "";
        } catch (e2) {}
        if (area === "widget_page") {
          setTimeout(function () {
            openModal();
          }, 80);
        }
        if (area === "settings") {
          setTimeout(mountSettingsPanel, 300);
        }
        return true;
      },
      settings: function () {
        injectCss();
        var tries = 0;
        var t = setInterval(function () {
          tries += 1;
          if (mountSettingsPanel() || tries > 20) clearInterval(t);
        }, 200);
        return true;
      },
      onSave: function () {
        try {
          syncAclFromUi();
        } catch (e) {}
        return true;
      },
      destroy: function () {
        if (heartbeatTimer) clearInterval(heartbeatTimer);
        heartbeatTimer = null;
        if (onlineTimer) clearInterval(onlineTimer);
        onlineTimer = null;
        if (observer) observer.disconnect();
        observer = null;
        $(document).off(".kuhtabel").off(".kuhtabelact").off(".kuhtabelopen").off(".kuhacl");
        started = false;
        return true;
      },
    };
    return this;
  };
  return CustomWidget;
});
