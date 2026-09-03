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
    var observer = null;
    var expanded = {};
    var collapsedGroups = {};
    var qSearch = "";
    var qStatus = "";
    var qSort = "name";

    function settings() {
      return self.get_settings() || {};
    }

    function apiBase() {
      var base = (settings().api_base || "").trim().replace(/\/$/, "");
      if (!base) {
        base = "https://acute-earrings-diamond-judicial.trycloudflare.com";
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

    function managersMap() {
      try {
        if (typeof APP !== "undefined" && APP.constant) {
          return APP.constant("managers") || {};
        }
      } catch (e) {}
      return {};
    }

    function injectCss() {
      if (document.getElementById("kuh-tabel-css")) return;
      var code = (settings().widget_code || "").replace(/[^\w\-]/g, "");
      if (!code) return;
      var href =
        "/widgets/" +
        code +
        "/style.css?v=" +
        (self.get_version ? self.get_version() : "12");
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
        ? '<img src="' + esc(photo) + '" alt="">'
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

    function modalHtml() {
      return (
        '<div class="kuh-tabel-overlay" id="kuh-tabel-overlay">' +
        '<div class="kuh-tabel-modal">' +
        '<div class="kuh-tabel-head"><div class="kuh-tabel-title">Табель</div>' +
        '<button type="button" class="kuh-tabel-close" id="kuh-tabel-close">×</button></div>' +
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
        "</div></div>"
      );
    }

    function paint() {
      if (!$("#kuh-tabel-overlay").length) return;
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
      var uid = parseInt((currentUser() || {}).id, 10) || 0;
      return api("/api/v1/tabel/state?user_id=" + uid)
        .done(function (data) {
          state = data;
          paint();
        })
        .fail(function (xhr) {
          $("#kuh-tabel-err").text(
            "Не удалось загрузить табель. Проверьте URL API в настройках виджета."
          );
          $("#kuh-tabel-body").html(
            '<div class="kuh-tabel-empty">Нет данных (' +
              (xhr.status || "?") +
              ")</div>"
          );
        });
    }

    function closeModal() {
      $("#kuh-tabel-overlay").remove();
    }

    function openModal() {
      if (!userHasAccess()) return;
      closeModal();
      $("body").append(modalHtml());
      $("#kuh-tabel-body").html(
        '<div class="kuh-tabel-loading">Загрузка сотрудников…</div>'
      );
      loadState();
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
          api("/api/v1/tabel/status", {
            method: "POST",
            body: { user_id: uid, status: code, actor_id: actor },
          }).done(function () {
            loadState();
          });
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
      if (!userHasAccess()) return;
      if ($("#kuh-tabel-menu-item").length) return;
      var $logout = $("body")
        .find("a, button, span, div, li")
        .filter(function () {
          var t = $(this)
            .clone()
            .children()
            .remove()
            .end()
            .text()
            .replace(/\s+/g, " ")
            .trim();
          return (
            t === "Выйти" ||
            t === "Выход" ||
            t === "Log out" ||
            t === "Sign out"
          );
        })
        .first();
      if (!$logout.length) return;
      var $box = $logout.closest(
        'ul, nav, [role="menu"], [class*="menu"], [class*="dropdown"], [class*="popup"], [class*="Popover"], [class*="list"]'
      );
      if (!$box.length) $box = $logout.parent();
      if ($box.find("#kuh-tabel-menu-item").length) return;
      var $btn = $(
        '<div id="kuh-tabel-menu-item" class="kuh-tabel-menu-item">Табель</div>'
      );
      $logout.before($btn);
    }

    function injectFab() {
      if (!userHasAccess()) return;
      if ($("#kuh-tabel-fab").length) return;
      var $btn = $(
        '<button type="button" class="kuh-tabel-fab" id="kuh-tabel-fab"><span class="kuh-tabel-fab-dot"></span>Табель</button>'
      );
      $("body").append($btn);
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
        api("/api/v1/tabel/heartbeat", {
          method: "POST",
          body: { user_id: uid, active: active },
        }).fail(function () {});
      }
      ping();
      heartbeatTimer = setInterval(ping, 25000);
    }

    function startOnce() {
      if (started) return;
      started = true;
      injectCss();
      if (!userHasAccess()) return;
      bindModal();
      injectFab();
      startTracker();
      $(document).on(
        "click.kuhtabelopen",
        "#kuh-tabel-fab, #kuh-tabel-menu-item",
        function (e) {
          e.preventDefault();
          e.stopPropagation();
          openModal();
        }
      );
      observer = new MutationObserver(function () {
        injectMenuItem();
      });
      observer.observe(document.body, { childList: true, subtree: true });
      injectMenuItem();
    }

    this.callbacks = {
      render: function () {
        return true;
      },
      init: function () {
        startOnce();
        return true;
      },
      bind_actions: function () {
        startOnce();
        return true;
      },
      settings: function () {
        return true;
      },
      onSave: function () {
        return true;
      },
      destroy: function () {
        if (heartbeatTimer) clearInterval(heartbeatTimer);
        heartbeatTimer = null;
        if (observer) observer.disconnect();
        observer = null;
        $(document).off(".kuhtabel").off(".kuhtabelact").off(".kuhtabelopen");
        started = false;
        return true;
      },
    };
    return this;
  };
  return CustomWidget;
});
