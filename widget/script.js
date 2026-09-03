/**
 * AI ĞŸĞ¾Ğ¼Ğ¾Ñ‰Ğ½Ğ¸Ğº Ğ¼ĞµĞ½ĞµĞ´Ğ¶ĞµÑ€Ğ° â€” Ğ¿Ñ€Ğ°Ğ²Ğ°Ñ ĞºĞ¾Ğ»Ğ¾Ğ½ĞºĞ° ĞºĞ°Ñ€Ñ‚Ğ¾Ñ‡ĞºĞ¸ ÑĞ´ĞµĞ»ĞºĞ¸/ĞºĞ¾Ğ½Ñ‚Ğ°ĞºÑ‚Ğ°.
 * ĞĞ½Ğ°Ğ»Ğ¸Ğ·Ğ¸Ñ€ÑƒĞµÑ‚ Ğ¿Ñ€Ğ¸Ğ¼ĞµÑ‡Ğ°Ğ½Ğ¸Ñ/Ğ·Ğ²Ğ¾Ğ½ĞºĞ¸ Ğ¸ Ğ´Ğ°Ñ‘Ñ‚ Ğ¿Ğ¾Ğ´ÑĞºĞ°Ğ·ĞºĞ¸.
 * Telegram/WhatsApp Ğ½Ğµ Ğ¸ÑĞ¿Ğ¾Ğ»ÑŒĞ·ÑƒÑÑ‚ÑÑ.
 */
define(["jquery"], function ($) {
  var CustomWidget = function () {
    var self = this;
    var refreshTimer = null;
    var lastPayload = null;

    function settings() {
      return self.get_settings() || {};
    }

    function apiBase() {
      var base = (settings().api_base || "").trim().replace(/\/$/, "");
      // Default public tunnel (updated by deploy_public.py / RESULT).
      // Can be overridden in widget settings.
      if (!base) {
        base = "https://emerald-gale-med-cube.trycloudflare.com";
      }
      return base;
    }

    function autoRefreshSec() {
      var n = parseInt(settings().auto_refresh || "90", 10);
      if (isNaN(n) || n < 0) return 90;
      return n;
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
      if (r.is_admin || r.admin || r.free_account_user === false && r.catalog_access) {
        /* keep checking */
      }
      if (r.is_admin === true || r.admin === true) return true;
      // amo often exposes free_user=false for paid seats; treat account admins via is_admin only
      return false;
    }

    function accessMode() {
      var m = (settings().access_mode || "admins_only").trim();
      if (
        m !== "admins_only" &&
        m !== "all_managers" &&
        m !== "selected"
      ) {
        return "admins_only";
      }
      return m;
    }

    function allowedUserIds() {
      var raw = settings().allowed_user_ids || "";
      if (Array.isArray(raw)) {
        return raw
          .map(function (x) {
            return parseInt(x, 10);
          })
          .filter(function (n) {
            return !isNaN(n) && n > 0;
          });
      }
      return String(raw)
        .split(/[,;\s]+/)
        .map(function (x) {
          return parseInt(x, 10);
        })
        .filter(function (n) {
          return !isNaN(n) && n > 0;
        });
    }

    function userHasAccess() {
      var user = currentUser();
      if (isAdminUser(user)) return true;
      var mode = accessMode();
      var uid = parseInt(user.id || user.user_id || 0, 10);
      if (mode === "admins_only") return false;
      if (mode === "all_managers") return !!uid;
      if (mode === "selected") {
        return allowedUserIds().indexOf(uid) >= 0;
      }
      return false;
    }

    function fetchAmoUsers() {
      var d = $.Deferred();
      $.ajax({
        url: "/api/v4/users",
        method: "GET",
        data: { limit: 250 },
        dataType: "json",
      })
        .done(function (resp) {
          var users = (resp && resp._embedded && resp._embedded.users) || [];
          d.resolve(users);
        })
        .fail(function () {
          d.resolve([]);
        });
      return d.promise();
    }

    function syncAclToBackend() {
      var base = apiBase();
      if (!base) return;
      var token = (settings().api_token || "").trim();
      var body = {
        access_mode: accessMode(),
        allowed_user_ids: allowedUserIds(),
      };
      var headers = { "Content-Type": "application/json" };
      if (token) headers["X-Api-Token"] = token;
      $.ajax({
        url: base + "/api/v1/widget/acl",
        method: "POST",
        data: JSON.stringify(body),
        contentType: "application/json",
        dataType: "json",
        headers: headers,
        timeout: 20000,
      });
    }

    function currentLeadId() {
      try {
        if (typeof APP !== "undefined" && APP.data && APP.data.current_card) {
          var id = APP.data.current_card.id;
          if (id && id !== 0) return id;
        }
      } catch (e) {}
      try {
        var m = (window.location.pathname || "").match(/\/leads\/detail\/(\d+)/);
        if (m) return parseInt(m[1], 10);
      } catch (e2) {}
      return null;
    }

    function scoreClass(score) {
      var s = parseFloat(score);
      if (s >= 7.5) return "good";
      if (s >= 5) return "mid";
      return "bad";
    }

    function escapeHtml(str) {
      return String(str == null ? "" : str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }

    function setStatus(msg, kind) {
      var $s = $("#kuh-ai-status");
      $s.removeClass("err ok").addClass(kind || "");
      $s.text(msg || "");
    }

    function setLoading(on) {
      $("#kuh-ai-btn-analyze, #kuh-ai-btn-note, #kuh-ai-btn-copy").prop(
        "disabled",
        !!on
      );
      if (on) setStatus("ĞĞ½Ğ°Ğ»Ğ¸Ğ·Ğ¸Ñ€ÑƒÑâ€¦", "");
    }

    function renderPayload(data) {
      lastPayload = data;
      var coach = data.coach || {};
      var quality = data.quality || {};
      var score = coach.score != null ? coach.score : quality.score;
      var $score = $("#kuh-ai-score");
      $score
        .text((score != null ? score : "â€”") + "/10")
        .removeClass("good mid bad")
        .addClass(scoreClass(score));

      $("#kuh-ai-summary").text(coach.summary || quality.summary || "â€”");
      $("#kuh-ai-stage").text(coach.stage_hint || "â€”");

      var stats = data.stats || {};
      $("#kuh-ai-stats").text(
        "ĞŸÑ€Ğ¸Ğ¼ĞµÑ‡Ğ°Ğ½Ğ¸Ğ¹: " +
          (stats.notes || 0) +
          " Â· Ğ·Ğ²Ğ¾Ğ½ĞºĞ¾Ğ²: " +
          (stats.calls || 0) +
          " Â· Ğ·Ğ°Ğ¿Ğ¸ÑĞµĞ¹: " +
          (stats.messages || 0)
      );

      function fillList(sel, arr) {
        var $ul = $(sel).empty();
        (arr || []).forEach(function (item) {
          $ul.append("<li>" + escapeHtml(item) + "</li>");
        });
        if (!(arr && arr.length)) {
          $ul.append('<li class="kuh-ai-muted">â€”</li>');
        }
      }

      fillList("#kuh-ai-next", coach.next_steps);
      fillList("#kuh-ai-risks", coach.risks);
      fillList("#kuh-ai-questions", coach.questions_to_ask);
      fillList("#kuh-ai-donot", coach.do_not);

      var $replies = $("#kuh-ai-replies").empty();
      (coach.suggested_replies || []).forEach(function (r) {
        $replies.append(
          '<div class="kuh-ai-reply" title="ĞšĞ»Ğ¸Ğº â€” ÑĞºĞ¾Ğ¿Ğ¸Ñ€Ğ¾Ğ²Ğ°Ñ‚ÑŒ">' +
            escapeHtml(r) +
            "</div>"
        );
      });
      if (!(coach.suggested_replies || []).length) {
        $replies.append('<div class="kuh-ai-muted">ĞĞµÑ‚ Ğ³Ğ¾Ñ‚Ğ¾Ğ²Ñ‹Ñ… Ğ¾Ñ‚Ğ²ĞµÑ‚Ğ¾Ğ²</div>');
      }

      var $obj = $("#kuh-ai-objections").empty();
      (coach.objections || []).forEach(function (o) {
        $obj.append(
          "<li><b>" +
            escapeHtml(o.objection || "") +
            ":</b> " +
            escapeHtml(o.answer || "") +
            "</li>"
        );
      });
      if (!(coach.objections || []).length) {
        $obj.append('<li class="kuh-ai-muted">â€”</li>');
      }

      var q = coach.quality || {};
      $("#kuh-ai-strengths").text(q.strengths || quality.strengths || "â€”");
      $("#kuh-ai-weaknesses").text(q.weaknesses || quality.weaknesses || "â€”");

      var $hist = $("#kuh-ai-history").empty();
      (data.history_preview || []).forEach(function (h) {
        $hist.append(
          '<div class="kuh-ai-hist-item"><b>' +
            escapeHtml(h.kind || "") +
            (h.direction ? " " + escapeHtml(h.direction) : "") +
            ":</b> " +
            escapeHtml(h.text || "") +
            "</div>"
        );
      });

      var model = coach.model || quality.model || "";
      setStatus("Ğ“Ğ¾Ñ‚Ğ¾Ğ²Ğ¾ Â· " + model, "ok");
    }

    /** Load notes of current lead via same-origin Amo API (user session). */
    function fetchLeadNotes(leadId) {
      var d = $.Deferred();
      $.ajax({
        url: "/api/v4/leads/" + leadId + "/notes",
        method: "GET",
        data: { limit: 100 },
        dataType: "json",
      })
        .done(function (resp) {
          var notes = (resp && resp._embedded && resp._embedded.notes) || [];
          var items = notes.map(function (n) {
            var p = n.params || {};
            var text = p.text || "";
            if (!text) {
              var parts = [];
              ["phone", "duration", "source", "link"].forEach(function (k) {
                if (p[k] != null) parts.push(k + "=" + p[k]);
              });
              text = parts.join(" | ");
            }
            var ntype = n.note_type || "common";
            var kind = ntype.indexOf("call") >= 0 ? "call" : "note";
            return {
              id: n.id,
              kind: kind,
              note_type: ntype,
              direction:
                ntype.indexOf("_in") >= 0
                  ? "in"
                  : ntype.indexOf("_out") >= 0
                  ? "out"
                  : "",
              created_at: n.created_at,
              text: text,
            };
          });
          d.resolve(items);
        })
        .fail(function () {
          d.resolve([]);
        });
      return d.promise();
    }

    function callApi(path, method, body) {
      var base = apiBase();
      var d = $.Deferred();
      if (!base) {
        d.reject("Ğ£ĞºĞ°Ğ¶Ğ¸Ñ‚Ğµ URL API Ğ² Ğ½Ğ°ÑÑ‚Ñ€Ğ¾Ğ¹ĞºĞ°Ñ… Ğ²Ğ¸Ğ´Ğ¶ĞµÑ‚Ğ°");
        return d.promise();
      }
      var url = base + path;
      var token = (settings().api_token || "").trim();

      // Prefer crm_post (proxied by amoCRM, works with HTTP backends)
      if (method === "POST" && typeof self.crm_post === "function") {
        var payload = body || {};
        if (token) payload._token = token;
        self.crm_post(
          url,
          payload,
          function (msg) {
            try {
              if (typeof msg === "string") msg = JSON.parse(msg);
            } catch (e) {}
            if (msg && msg.ok === false) {
              d.reject((msg && msg.detail) || "API error");
            } else {
              d.resolve(msg);
            }
          },
          "json",
          function () {
            // fallback to browser fetch
            browserFetch(url, method, body, token).then(d.resolve, d.reject);
          }
        );
        return d.promise();
      }

      browserFetch(url, method, body, token).then(d.resolve, d.reject);
      return d.promise();
    }

    function browserFetch(url, method, body, token) {
      var d = $.Deferred();
      var headers = { "Content-Type": "application/json" };
      if (token) headers["X-Api-Token"] = token;
      $.ajax({
        url: url,
        method: method || "GET",
        data: method === "GET" ? undefined : JSON.stringify(body || {}),
        contentType: "application/json",
        dataType: "json",
        headers: headers,
        timeout: 60000,
      })
        .done(function (resp) {
          d.resolve(resp);
        })
        .fail(function (xhr) {
          d.reject(
            (xhr.responseJSON && (xhr.responseJSON.detail || xhr.responseJSON.error)) ||
              xhr.statusText ||
              "network error"
          );
        });
      return d.promise();
    }

    function analyzeNow() {
      var leadId = currentLeadId();
      if (!leadId) {
        setStatus("ĞÑ‚ĞºÑ€Ğ¾Ğ¹Ñ‚Ğµ ĞºĞ°Ñ€Ñ‚Ğ¾Ñ‡ĞºÑƒ ÑĞ´ĞµĞ»ĞºĞ¸", "err");
        return;
      }
      setLoading(true);
      fetchLeadNotes(leadId).always(function (notes) {
        var user = currentUser();
        callApi("/api/v1/assistant/lead", "POST", {
          lead_id: leadId,
          notes: notes || [],
          write_note: false,
          user_id: parseInt(user.id || 0, 10) || null,
          is_admin: isAdminUser(user),
        })
          .done(function (data) {
            if (data && data.ok !== false) {
              renderPayload(data);
            } else {
              setStatus("ĞŸÑƒÑÑ‚Ğ¾Ğ¹ Ğ¾Ñ‚Ğ²ĞµÑ‚ API", "err");
            }
          })
          .fail(function (err) {
            setStatus("ĞÑˆĞ¸Ğ±ĞºĞ°: " + err, "err");
            // Offline heuristic from notes only
            offlineCoach(notes || []);
          })
          .always(function () {
            setLoading(false);
          });
      });
    }

    function offlineCoach(notes) {
      var text = (notes || [])
        .map(function (n) {
          return n.text || "";
        })
        .join("\n")
        .toLowerCase();
      var score = 5;
      var next = [];
      if (text.indexOf("Ğ·Ğ°Ğ¿Ğ¸Ñ") < 0) {
        next.push("Ğ£Ñ‚Ğ¾Ñ‡Ğ½Ğ¸Ñ‚ÑŒ Ğ´Ğ°Ñ‚Ñƒ/Ğ²Ñ€ĞµĞ¼Ñ Ğ¸ Ğ¿Ñ€ĞµĞ´Ğ»Ğ¾Ğ¶Ğ¸Ñ‚ÑŒ 2 ÑĞ»Ğ¾Ñ‚Ğ° Ğ·Ğ°Ğ¿Ğ¸ÑĞ¸.");
        score -= 0.5;
      } else {
        next.push("ĞŸĞ¾Ğ´Ñ‚Ğ²ĞµÑ€Ğ´Ğ¸Ñ‚ÑŒ Ğ·Ğ°Ğ¿Ğ¸ÑÑŒ Ğ¸ Ñ‡Ñ‚Ğ¾ Ğ²Ğ·ÑÑ‚ÑŒ Ñ ÑĞ¾Ğ±Ğ¾Ğ¹.");
      }
      next.push("ĞŸĞ¾ÑÑ‚Ğ°Ğ²Ğ¸Ñ‚ÑŒ Ğ·Ğ°Ğ´Ğ°Ñ‡Ñƒ Ğ½Ğ° follow-up Ğ² CRM.");
      if (text.length < 40) {
        score -= 1;
        next.push("Ğ—Ğ°Ñ„Ğ¸ĞºÑĞ¸Ñ€Ğ¾Ğ²Ğ°Ñ‚ÑŒ Ğ¸Ñ‚Ğ¾Ğ³ Ñ€Ğ°Ğ·Ğ³Ğ¾Ğ²Ğ¾Ñ€Ğ° Ğ² Ğ¿Ñ€Ğ¸Ğ¼ĞµÑ‡Ğ°Ğ½Ğ¸Ğ¸.");
      }
      renderPayload({
        ok: true,
        stats: { notes: notes.length, calls: 0, messages: notes.length },
        coach: {
          score: Math.max(0, Math.min(10, score)),
          summary: "Ğ›Ğ¾ĞºĞ°Ğ»ÑŒĞ½Ñ‹Ğµ Ğ¿Ğ¾Ğ´ÑĞºĞ°Ğ·ĞºĞ¸ (API Ğ½ĞµĞ´Ğ¾ÑÑ‚ÑƒĞ¿ĞµĞ½).",
          stage_hint: "Ğ½ÑƒĞ¶Ğ½Ğ° ÑĞ²ÑĞ·ÑŒ Ñ API Ğ´Ğ»Ñ Ğ¿Ğ¾Ğ»Ğ½Ğ¾Ğ³Ğ¾ AI-Ñ€Ğ°Ğ·Ğ±Ğ¾Ñ€Ğ°",
          next_steps: next,
          risks: ["ĞĞµÑ‚ ÑĞ²ÑĞ·Ğ¸ Ñ ÑĞµÑ€Ğ²ĞµÑ€Ğ¾Ğ¼ Ğ°Ğ½Ğ°Ğ»Ğ¸Ğ·Ğ°"],
          suggested_replies: [
            "Ğ—Ğ´Ñ€Ğ°Ğ²ÑÑ‚Ğ²ÑƒĞ¹Ñ‚Ğµ! ĞŸĞ¾Ğ´ÑĞºĞ°Ğ¶Ğ¸Ñ‚Ğµ, Ğ½Ğ° ĞºĞ°ĞºÑƒÑ Ğ´Ğ°Ñ‚Ñƒ Ğ²Ğ°Ğ¼ ÑƒĞ´Ğ¾Ğ±Ğ½ĞµĞµ Ğ·Ğ°Ğ¿Ğ¸ÑĞ°Ñ‚ÑŒÑÑ?",
            "ĞœĞ¾Ğ³Ñƒ Ğ¿Ñ€ĞµĞ´Ğ»Ğ¾Ğ¶Ğ¸Ñ‚ÑŒ Ğ±Ğ»Ğ¸Ğ¶Ğ°Ğ¹ÑˆĞ¸Ğµ ÑĞ²Ğ¾Ğ±Ğ¾Ğ´Ğ½Ñ‹Ğµ Ğ¾ĞºĞ½Ğ° â€” ÑƒÑ‚Ñ€Ğ¾ Ğ¸Ğ»Ğ¸ Ğ´ĞµĞ½ÑŒ?",
          ],
          questions_to_ask: [
            "Ğ§Ñ‚Ğ¾ Ğ±ĞµÑĞ¿Ğ¾ĞºĞ¾Ğ¸Ñ‚?",
            "ĞšĞ¾Ğ³Ğ´Ğ° ÑƒĞ´Ğ¾Ğ±Ğ½Ğ¾ Ğ¿Ñ€Ğ¸Ğ¹Ñ‚Ğ¸?",
          ],
          objections: [],
          do_not: ["ĞĞµ Ğ¾Ğ±ĞµÑ‰Ğ°Ñ‚ÑŒ Ğ´Ğ¸Ğ°Ğ³Ğ½Ğ¾Ğ· Ğ¿Ğ¾ Ñ‚ĞµĞ»ĞµÑ„Ğ¾Ğ½Ñƒ"],
          quality: { strengths: "â€”", weaknesses: "offline mode" },
          model: "offline",
        },
        quality: { score: score, strengths: "â€”", weaknesses: "offline" },
        history_preview: (notes || []).slice(0, 5).map(function (n) {
          return {
            kind: n.kind,
            direction: n.direction,
            text: (n.text || "").slice(0, 160),
          };
        }),
      });
    }

    function writeNote() {
      var leadId = currentLeadId();
      if (!leadId) {
        setStatus("ĞĞµÑ‚ lead_id", "err");
        return;
      }
      if (!lastPayload || !lastPayload.note_markdown) {
        setStatus("Ğ¡Ğ½Ğ°Ñ‡Ğ°Ğ»Ğ° Ğ½Ğ°Ğ¶Ğ¼Ğ¸Ñ‚Ğµ Â«ĞĞ½Ğ°Ğ»Ğ¸Ğ·Ğ¸Ñ€Ğ¾Ğ²Ğ°Ñ‚ÑŒÂ»", "err");
        return;
      }
      setLoading(true);
      var user = currentUser();
      callApi("/api/v1/assistant/write_note", "POST", {
        lead_id: leadId,
        text: lastPayload.note_markdown,
        user_id: parseInt(user.id || 0, 10) || null,
        is_admin: isAdminUser(user),
      })
        .done(function () {
          setStatus("ĞŸÑ€Ğ¸Ğ¼ĞµÑ‡Ğ°Ğ½Ğ¸Ğµ Ğ·Ğ°Ğ¿Ğ¸ÑĞ°Ğ½Ğ¾ Ğ² ÑĞ´ĞµĞ»ĞºÑƒ", "ok");
        })
        .fail(function (err) {
          setStatus("ĞĞµ ÑƒĞ´Ğ°Ğ»Ğ¾ÑÑŒ Ğ·Ğ°Ğ¿Ğ¸ÑĞ°Ñ‚ÑŒ: " + err, "err");
        })
        .always(function () {
          setLoading(false);
        });
    }

    function copyBestReply() {
      var text =
        (lastPayload &&
          lastPayload.coach &&
          lastPayload.coach.suggested_replies &&
          lastPayload.coach.suggested_replies[0]) ||
        "";
      if (!text) {
        setStatus("ĞĞµÑ‚ Ñ‚ĞµĞºÑÑ‚Ğ° Ğ´Ğ»Ñ ĞºĞ¾Ğ¿Ğ¸Ñ€Ğ¾Ğ²Ğ°Ğ½Ğ¸Ñ", "err");
        return;
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(
          function () {
            setStatus("ĞÑ‚Ğ²ĞµÑ‚ ÑĞºĞ¾Ğ¿Ğ¸Ñ€Ğ¾Ğ²Ğ°Ğ½", "ok");
          },
          function () {
            window.prompt("Ğ¡ĞºĞ¾Ğ¿Ğ¸Ñ€ÑƒĞ¹Ñ‚Ğµ:", text);
          }
        );
      } else {
        window.prompt("Ğ¡ĞºĞ¾Ğ¿Ğ¸Ñ€ÑƒĞ¹Ñ‚Ğµ:", text);
      }
    }

    function buildDeniedHtml() {
      return (
        '<div class="kuh-ai-root" id="kuh-ai-root">' +
        '<div class="kuh-ai-header"><div class="kuh-ai-title">AI ĞŸĞ¾Ğ¼Ğ¾Ñ‰Ğ½Ğ¸Ğº</div></div>' +
        '<div class="kuh-ai-denied">' +
        "<b>ĞĞµÑ‚ Ğ´Ğ¾ÑÑ‚ÑƒĞ¿Ğ°</b>" +
        "<p>Ğ’Ğ¸Ğ´Ğ¶ĞµÑ‚ Ğ½Ğµ Ğ¿Ğ¾Ğ´ĞºĞ»ÑÑ‡Ñ‘Ğ½ Ğ´Ğ»Ñ Ğ²Ğ°ÑˆĞµĞ³Ğ¾ Ğ¿Ğ¾Ğ»ÑŒĞ·Ğ¾Ğ²Ğ°Ñ‚ĞµĞ»Ñ.</p>" +
        "<p class=\"kuh-ai-muted\">ĞŸĞ¾Ğ¿Ñ€Ğ¾ÑĞ¸Ñ‚Ğµ Ğ°Ğ´Ğ¼Ğ¸Ğ½Ğ¸ÑÑ‚Ñ€Ğ°Ñ‚Ğ¾Ñ€Ğ° Ğ²Ñ‹Ğ´Ğ°Ñ‚ÑŒ Ğ´Ğ¾ÑÑ‚ÑƒĞ¿ Ğ² Ğ½Ğ°ÑÑ‚Ñ€Ğ¾Ğ¹ĞºĞ°Ñ… Ğ²Ğ¸Ğ´Ğ¶ĞµÑ‚Ğ°.</p>" +
        "</div></div>"
      );
    }

    function buildHtml() {
      return (
        '<div class="kuh-ai-root" id="kuh-ai-root">' +
        '<div class="kuh-ai-header">' +
        '<div class="kuh-ai-title">AI ĞŸĞ¾Ğ¼Ğ¾Ñ‰Ğ½Ğ¸Ğº</div>' +
        '<div class="kuh-ai-score mid" id="kuh-ai-score">â€”/10</div>' +
        "</div>" +
        '<div class="kuh-ai-status" id="kuh-ai-status">ĞÑ‚ĞºÑ€Ğ¾Ğ¹Ñ‚Ğµ ÑĞ´ĞµĞ»ĞºÑƒ Ğ¸ Ğ½Ğ°Ğ¶Ğ¼Ğ¸Ñ‚Ğµ Â«Ğ Ğ°Ğ·Ğ¾Ğ±Ñ€Ğ°Ñ‚ÑŒÂ»</div>' +
        '<div class="kuh-ai-actions">' +
        '<div class="kuh-ai-btn primary" id="kuh-ai-btn-analyze">Ğ Ğ°Ğ·Ğ¾Ğ±Ñ€Ğ°Ñ‚ÑŒ</div>' +
        '<div class="kuh-ai-btn" id="kuh-ai-btn-note">Ğ’ Ğ·Ğ°Ğ¼ĞµÑ‚ĞºÑƒ ÑĞ´ĞµĞ»ĞºĞ¸</div>' +
        '<div class="kuh-ai-btn" id="kuh-ai-btn-copy">ĞšĞ¾Ğ¿Ğ¸Ñ€Ğ¾Ğ²Ğ°Ñ‚ÑŒ Ğ¾Ñ‚Ğ²ĞµÑ‚</div>' +
        "</div>" +
        '<div class="kuh-ai-block"><h4>Ğ¡ÑƒÑ‚ÑŒ</h4><div id="kuh-ai-summary" class="kuh-ai-muted">â€”</div>' +
        '<div class="kuh-ai-muted" style="margin-top:4px">Ğ­Ñ‚Ğ°Ğ¿: <span id="kuh-ai-stage">â€”</span></div>' +
        '<div class="kuh-ai-muted" id="kuh-ai-stats" style="margin-top:4px"></div></div>' +
        '<div class="kuh-ai-block"><h4>Ğ§Ñ‚Ğ¾ ÑĞ´ĞµĞ»Ğ°Ñ‚ÑŒ ÑĞµĞ¹Ñ‡Ğ°Ñ</h4><ul id="kuh-ai-next"></ul></div>' +
        '<div class="kuh-ai-block"><h4>Ğ“Ğ¾Ñ‚Ğ¾Ğ²Ñ‹Ğµ Ğ¾Ñ‚Ğ²ĞµÑ‚Ñ‹ <span class="kuh-ai-muted">(ĞºĞ»Ğ¸Ğº = ĞºĞ¾Ğ¿Ğ¸Ñ€Ğ¾Ğ²Ğ°Ñ‚ÑŒ)</span></h4><div id="kuh-ai-replies"></div></div>' +
        '<div class="kuh-ai-block"><h4>Ğ’Ğ¾Ğ¿Ñ€Ğ¾ÑÑ‹ ĞºĞ»Ğ¸ĞµĞ½Ñ‚Ñƒ</h4><ul id="kuh-ai-questions"></ul></div>' +
        '<div class="kuh-ai-block"><h4>Ğ’Ğ¾Ğ·Ñ€Ğ°Ğ¶ĞµĞ½Ğ¸Ñ</h4><ul id="kuh-ai-objections"></ul></div>' +
        '<div class="kuh-ai-block"><h4>Ğ Ğ¸ÑĞºĞ¸</h4><ul id="kuh-ai-risks"></ul></div>' +
        '<div class="kuh-ai-block"><h4>ĞĞµ Ğ´ĞµĞ»Ğ°Ñ‚ÑŒ</h4><ul id="kuh-ai-donot"></ul></div>' +
        '<div class="kuh-ai-block"><h4>ĞšĞ°Ñ‡ĞµÑÑ‚Ğ²Ğ¾</h4>' +
        '<div><b>Ğ¡Ğ¸Ğ»ÑŒĞ½Ğ¾:</b> <span id="kuh-ai-strengths">â€”</span></div>' +
        '<div><b>Ğ¡Ğ»Ğ°Ğ±Ğ¾:</b> <span id="kuh-ai-weaknesses">â€”</span></div></div>' +
        '<div class="kuh-ai-block"><h4>Ğ˜ÑÑ‚Ğ¾Ñ€Ğ¸Ñ (Ñ„Ñ€Ğ°Ğ³Ğ¼ĞµĞ½Ñ‚Ñ‹)</h4><div id="kuh-ai-history" class="kuh-ai-muted">â€”</div></div>' +
        "</div>"
      );
    }

    function buildSettingsHtml(users) {
      var mode = accessMode();
      var allowed = allowedUserIds();
      var rows = (users || [])
        .map(function (u) {
          var id = parseInt(u.id, 10);
          var name = u.name || ("User " + id);
          var checked = allowed.indexOf(id) >= 0 ? " checked" : "";
          return (
            '<label class="kuh-ai-user-row">' +
            '<input type="checkbox" class="kuh-ai-user-cb" data-uid="' +
            id +
            '"' +
            checked +
            "/> " +
            escapeHtml(name) +
            ' <span class="kuh-ai-muted">#' +
            id +
            "</span></label>"
          );
        })
        .join("");
      if (!rows) {
        rows = '<div class="kuh-ai-muted">ĞĞµ ÑƒĞ´Ğ°Ğ»Ğ¾ÑÑŒ Ğ·Ğ°Ğ³Ñ€ÑƒĞ·Ğ¸Ñ‚ÑŒ ÑĞ¿Ğ¸ÑĞ¾Ğº Ğ¿Ğ¾Ğ»ÑŒĞ·Ğ¾Ğ²Ğ°Ñ‚ĞµĞ»ĞµĞ¹</div>';
      }
      return (
        '<div class="kuh-ai-settings" id="kuh-ai-settings">' +
        "<h3>Ğ”Ğ¾ÑÑ‚ÑƒĞ¿ Ğº Ğ²Ğ¸Ğ´Ğ¶ĞµÑ‚Ñƒ</h3>" +
        '<p class="kuh-ai-muted">ĞĞ´Ğ¼Ğ¸Ğ½Ğ¸ÑÑ‚Ñ€Ğ°Ñ‚Ğ¾Ñ€ Ğ²Ğ¸Ğ´Ğ¸Ñ‚ Ğ²ÑÑ‘. ĞĞ¸Ğ¶Ğµ â€” ĞºĞ¾Ğ¼Ñƒ Ğ¸Ğ· Ğ¼ĞµĞ½ĞµĞ´Ğ¶ĞµÑ€Ğ¾Ğ² Ñ€Ğ°Ğ·Ñ€ĞµÑˆĞ¸Ñ‚ÑŒ Ğ¿Ğ°Ğ½ĞµĞ»ÑŒ Ğ² ÑĞ´ĞµĞ»ĞºĞµ.</p>' +
        '<div class="kuh-ai-block">' +
        '<label class="kuh-ai-radio"><input type="radio" name="kuh-access-mode" value="admins_only"' +
        (mode === "admins_only" ? " checked" : "") +
        "/> Ğ¢Ğ¾Ğ»ÑŒĞºĞ¾ Ğ°Ğ´Ğ¼Ğ¸Ğ½Ğ¸ÑÑ‚Ñ€Ğ°Ñ‚Ğ¾Ñ€Ñ‹</label>" +
        '<label class="kuh-ai-radio"><input type="radio" name="kuh-access-mode" value="all_managers"' +
        (mode === "all_managers" ? " checked" : "") +
        "/> Ğ’ÑĞµ Ğ¼ĞµĞ½ĞµĞ´Ğ¶ĞµÑ€Ñ‹</label>" +
        '<label class="kuh-ai-radio"><input type="radio" name="kuh-access-mode" value="selected"' +
        (mode === "selected" ? " checked" : "") +
        "/> Ğ’Ñ‹Ğ±Ñ€Ğ°Ğ½Ğ½Ñ‹Ğµ Ğ¼ĞµĞ½ĞµĞ´Ğ¶ĞµÑ€Ñ‹</label>" +
        "</div>" +
        '<div class="kuh-ai-block" id="kuh-ai-users-box">' +
        "<h4>Ğ¡Ğ¿Ğ¸ÑĞ¾Ğº Ğ¿Ğ¾Ğ»ÑŒĞ·Ğ¾Ğ²Ğ°Ñ‚ĞµĞ»ĞµĞ¹</h4>" +
        '<div class="kuh-ai-users">' +
        rows +
        "</div></div>" +
        '<div class="kuh-ai-actions">' +
        '<div class="kuh-ai-btn primary" id="kuh-ai-btn-save-acl">Ğ¡Ğ¾Ñ…Ñ€Ğ°Ğ½Ğ¸Ñ‚ÑŒ Ğ´Ğ¾ÑÑ‚ÑƒĞ¿</div>' +
        '<div class="kuh-ai-btn" id="kuh-ai-btn-ping">ĞŸÑ€Ğ¾Ğ²ĞµÑ€Ğ¸Ñ‚ÑŒ API</div>' +
        "</div>" +
        '<div class="kuh-ai-status" id="kuh-ai-acl-status"></div>' +
        '<p class="kuh-ai-muted">Ğ¢Ğ°ĞºĞ¶Ğµ ÑƒĞºĞ°Ğ¶Ğ¸Ñ‚Ğµ Ğ² ÑÑ‚Ğ°Ğ½Ğ´Ğ°Ñ€Ñ‚Ğ½Ñ‹Ñ… Ğ¿Ğ¾Ğ»ÑÑ… Ğ²Ñ‹ÑˆĞµ: URL API (https://â€¦) Ğ¸ Ğ¿Ñ€Ğ¸ Ğ½ĞµĞ¾Ğ±Ñ…Ğ¾Ğ´Ğ¸Ğ¼Ğ¾ÑÑ‚Ğ¸ Ñ‚Ğ¾ĞºĞµĞ½.</p>' +
        "</div>"
      );
    }

    function startAutoRefresh() {
      if (refreshTimer) {
        clearInterval(refreshTimer);
        refreshTimer = null;
      }
      var sec = autoRefreshSec();
      if (sec > 0) {
        refreshTimer = setInterval(function () {
          if (currentLeadId()) analyzeNow();
        }, sec * 1000);
      }
    }

    this.callbacks = {
      render: function () {
        var area = self.system().area;
        if (area !== "lcard" && area !== "ccard") {
          return true;
        }
        try {
          if (
            typeof APP !== "undefined" &&
            APP.data &&
            APP.data.current_card &&
            APP.data.current_card.id === 0
          ) {
            return false;
          }
        } catch (e) {}

        var w_code = self.get_settings().widget_code;
        var css =
          '<link type="text/css" rel="stylesheet" href="/widgets/' +
          w_code +
          '/style.css?v=' +
          (self.get_version ? self.get_version() : "2") +
          '" >';

        var bodyHtml = userHasAccess() ? buildHtml() : buildDeniedHtml();

        self.render_template({
          caption: {
            class_name: "kuh-ai-caption",
            html: "AI ĞŸĞ¾Ğ¼Ğ¾Ñ‰Ğ½Ğ¸Ğº",
          },
          body: "",
          render: bodyHtml + css,
        });
        return true;
      },

      init: function () {
        return true;
      },

      bind_actions: function () {
        var area = self.system().area;
        if (area === "settings") {
          // Admin ACL UI is bound in settings callback after users load
          return true;
        }
        if (area !== "lcard" && area !== "ccard") {
          return true;
        }

        if (!userHasAccess()) {
          return true;
        }

        $(document)
          .off("click.kuhai")
          .on("click.kuhai", "#kuh-ai-btn-analyze", function () {
            analyzeNow();
          })
          .on("click.kuhai", "#kuh-ai-btn-note", function () {
            writeNote();
          })
          .on("click.kuhai", "#kuh-ai-btn-copy", function () {
            copyBestReply();
          })
          .on("click.kuhai", ".kuh-ai-reply", function () {
            var t = $(this).text();
            if (navigator.clipboard && navigator.clipboard.writeText) {
              navigator.clipboard.writeText(t);
              setStatus("Ğ¡ĞºĞ¾Ğ¿Ğ¸Ñ€Ğ¾Ğ²Ğ°Ğ½Ğ¾", "ok");
            } else {
              window.prompt("Ğ¡ĞºĞ¾Ğ¿Ğ¸Ñ€ÑƒĞ¹Ñ‚Ğµ:", t);
            }
          });

        // auto first analysis
        setTimeout(function () {
          if (apiBase() && currentLeadId()) {
            analyzeNow();
          } else if (!apiBase()) {
            setStatus("Ğ£ĞºĞ°Ğ¶Ğ¸Ñ‚Ğµ URL API Ğ² Ğ½Ğ°ÑÑ‚Ñ€Ğ¾Ğ¹ĞºĞ°Ñ… Ğ²Ğ¸Ğ´Ğ¶ĞµÑ‚Ğ°", "err");
          }
          startAutoRefresh();
        }, 600);

        return true;
      },

      settings: function () {
        // Only admins manage ACL panel
        if (!isAdminUser()) {
          var $wrap = $("#widget_settings__fields");
          if ($wrap.length) {
            $wrap.prepend(
              '<div class="kuh-ai-denied" style="margin:8px 0">' +
                "<b>ĞĞ°ÑÑ‚Ñ€Ğ¾Ğ¹ĞºĞ¸ Ğ´Ğ¾ÑÑ‚ÑƒĞ¿Ğ°</b> Ğ´Ğ¾ÑÑ‚ÑƒĞ¿Ğ½Ñ‹ Ñ‚Ğ¾Ğ»ÑŒĞºĞ¾ Ğ°Ğ´Ğ¼Ğ¸Ğ½Ğ¸ÑÑ‚Ñ€Ğ°Ñ‚Ğ¾Ñ€Ñƒ Ğ°ĞºĞºĞ°ÑƒĞ½Ñ‚Ğ°." +
                "</div>"
            );
          }
          return true;
        }

        var $fields = $("#widget_settings__fields");
        if (!$fields.length) {
          // fallback container used by some amo versions
          $fields = $(".widget_settings_block__fields").first();
        }
        if (!$fields.length) {
          return true;
        }

        fetchAmoUsers().always(function (users) {
          $("#kuh-ai-settings").remove();
          $fields.prepend(buildSettingsHtml(users || []));

          function toggleUsersBox() {
            var mode = $('input[name="kuh-access-mode"]:checked').val();
            if (mode === "selected") {
              $("#kuh-ai-users-box").show();
            } else {
              $("#kuh-ai-users-box").hide();
            }
          }
          toggleUsersBox();
          $(document)
            .off("change.kuhaiacl")
            .on("change.kuhaiacl", 'input[name="kuh-access-mode"]', toggleUsersBox);

          $(document)
            .off("click.kuhaiacl")
            .on("click.kuhaiacl", "#kuh-ai-btn-save-acl", function () {
              var mode = $('input[name="kuh-access-mode"]:checked').val() || "admins_only";
              var ids = [];
              $(".kuh-ai-user-cb:checked").each(function () {
                var id = parseInt($(this).data("uid"), 10);
                if (!isNaN(id)) ids.push(id);
              });
              var next = $.extend({}, settings(), {
                access_mode: mode,
                allowed_user_ids: ids.join(","),
              });
              self.set_settings(next);
              syncAclToBackend();
              $("#kuh-ai-acl-status")
                .removeClass("err")
                .addClass("ok")
                .text("Ğ”Ğ¾ÑÑ‚ÑƒĞ¿ ÑĞ¾Ñ…Ñ€Ğ°Ğ½Ñ‘Ğ½ Â· Ñ€ĞµĞ¶Ğ¸Ğ¼: " + mode);
            })
            .on("click.kuhaiacl", "#kuh-ai-btn-ping", function () {
              var base = apiBase();
              if (!base) {
                $("#kuh-ai-acl-status")
                  .removeClass("ok")
                  .addClass("err")
                  .text("Ğ¡Ğ½Ğ°Ñ‡Ğ°Ğ»Ğ° ÑƒĞºĞ°Ğ¶Ğ¸Ñ‚Ğµ URL API");
                return;
              }
              $.ajax({
                url: base + "/api/v1/ping",
                method: "GET",
                timeout: 10000,
                dataType: "json",
              })
                .done(function () {
                  $("#kuh-ai-acl-status")
                    .removeClass("err")
                    .addClass("ok")
                    .text("API Ğ¾Ñ‚Ğ²ĞµÑ‡Ğ°ĞµÑ‚: " + base);
                })
                .fail(function (xhr) {
                  $("#kuh-ai-acl-status")
                    .removeClass("ok")
                    .addClass("err")
                    .text("API Ğ½ĞµĞ´Ğ¾ÑÑ‚ÑƒĞ¿ĞµĞ½: " + (xhr.statusText || "Ğ¾ÑˆĞ¸Ğ±ĞºĞ°"));
                });
            });
        });

        return true;
      },

      onSave: function () {
        try {
          if (isAdminUser()) {
            var mode =
              $('input[name="kuh-access-mode"]:checked').val() ||
              accessMode();
            var ids = [];
            $(".kuh-ai-user-cb:checked").each(function () {
              var id = parseInt($(this).data("uid"), 10);
              if (!isNaN(id)) ids.push(id);
            });
            var next = $.extend({}, settings(), {
              access_mode: mode,
              allowed_user_ids: ids.join(","),
            });
            self.set_settings(next);
            syncAclToBackend();
          }
        } catch (e) {}
        return true;
      },

      destroy: function () {
        if (refreshTimer) {
          clearInterval(refreshTimer);
          refreshTimer = null;
        }
        $(document).off("click.kuhai");
        $(document).off("click.kuhaiacl change.kuhaiacl");
        return true;
      },
    };

    return this;
  };

  return CustomWidget;
});



