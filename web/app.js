// LLM Squid Game — Web Arena frontend logic.
//
// Pure vanilla JS + Alpine.js (CDN). No build step. Talks to the FastAPI
// backend at window.WEB_ARENA_API (see config.js). The server is the single
// source of truth for game state and scoring — this file never computes or
// submits a final score, it only relays what the server returns.

(function () {
  "use strict";

  const API_BASE = window.WEB_ARENA_API;
  const RETRY_INTERVAL_MS = 2500;
  const MAX_WAIT_MS = 45000; // covers the free-tier ~30s cold start

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  /**
   * fetch() wrapper with a retry loop that tolerates the backend's free-tier
   * cold start. Retries on network errors and 5xx responses; fails fast on
   * 4xx (those are real client errors, retrying won't help). `onStatus` is
   * called with a human-readable status string while waiting/retrying.
   */
  async function fetchJSON(path, options, onStatus) {
    const started = Date.now();
    let lastError = null;
    let attempt = 0;

    while (Date.now() - started < MAX_WAIT_MS) {
      attempt += 1;
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 15000);
        const res = await fetch(API_BASE + path, {
          ...options,
          signal: controller.signal,
          headers: {
            "Content-Type": "application/json",
            ...(options && options.headers ? options.headers : {}),
          },
        });
        clearTimeout(timeoutId);

        if (!res.ok) {
          let detail = "";
          try {
            const body = await res.json();
            detail = body && body.detail ? body.detail : JSON.stringify(body);
          } catch (_) {
            /* response wasn't JSON; ignore */
          }
          const message = `HTTP ${res.status}${detail ? ": " + detail : ""}`;
          if (res.status >= 500) {
            lastError = new Error(message);
            if (onStatus) {
              onStatus(
                attempt === 1
                  ? "Waking up the backend (free-tier cold start can take up to ~30s)..."
                  : `Still waking up the backend... (attempt ${attempt})`
              );
            }
            await sleep(RETRY_INTERVAL_MS);
            continue;
          }
          const err = new Error(message);
          err.status = res.status;
          throw err;
        }

        if (onStatus) onStatus("");
        if (res.status === 204) return null;
        return await res.json();
      } catch (err) {
        if (err && err.status && err.status < 500) throw err;
        lastError = err;
        if (onStatus) {
          onStatus(
            attempt === 1
              ? "Waking up the backend (free-tier cold start can take up to ~30s)..."
              : `Still waking up the backend... (attempt ${attempt})`
          );
        }
        await sleep(RETRY_INTERVAL_MS);
      }
    }
    throw lastError || new Error("Request timed out while waking up the backend.");
  }

  function fmtNum(x, digits) {
    if (x === null || x === undefined) return "—";
    return Number(x).toFixed(digits === undefined ? 2 : digits);
  }

  function fmtP(p) {
    if (p === null || p === undefined) return "—";
    if (p < 0.001) return "<0.001";
    return Number(p).toFixed(3);
  }

  function fmtDate(iso) {
    if (!iso) return "—";
    try {
      const d = new Date(iso);
      if (isNaN(d.getTime())) return iso;
      return d.toLocaleString();
    } catch (_) {
      return iso;
    }
  }

  function shortId(id) {
    if (!id) return "";
    return id.length > 10 ? id.slice(0, 10) + "…" : id;
  }

  window.squidArenaHelpers = { fmtNum, fmtP, fmtDate, shortId };

  // ---------------------------------------------------------------------
  // Nav: hash-based tab routing, no router library.
  // ---------------------------------------------------------------------
  document.addEventListener("alpine:init", () => {
    Alpine.store("nav", {
      tab: (location.hash || "#play").replace("#", "") || "play",
      setFromHash() {
        this.tab = (location.hash || "#play").replace("#", "") || "play";
      },
    });
    window.addEventListener("hashchange", () => Alpine.store("nav").setFromHash());

    // -----------------------------------------------------------------
    // Play screen
    // -----------------------------------------------------------------
    Alpine.data("playScreen", () => ({
      task: window.WEB_ARENA_DEFAULT_TASK,
      framing: window.WEB_ARENA_DEFAULT_FRAMING,
      forfeit: window.WEB_ARENA_DEFAULT_FORFEIT,

      nickname: "",
      sessionId: null,
      started: false,
      starting: false,
      loading: false,
      submitting: false,
      error: null,
      statusMsg: "",

      state: null,
      selectedAction: "",
      probeAnswer: "",
      reasoning: "",
      lastFeedback: null,

      gameOver: false,
      result: null,
      rank: null,
      totalRows: null,

      async startGame() {
        this.error = null;
        this.starting = true;
        this.statusMsg = "";
        try {
          const resp = await fetchJSON(
            "/api/new_game",
            {
              method: "POST",
              body: JSON.stringify({
                task_name: this.task,
                framing: this.framing,
                forfeit_condition: this.forfeit,
                nickname: this.nickname,
              }),
            },
            (m) => (this.statusMsg = m)
          );
          this.sessionId = resp.session_id;
          this.started = true;
          await this.refreshState();
        } catch (e) {
          this.error = e.message;
        } finally {
          this.starting = false;
        }
      },

      async refreshState() {
        this.loading = true;
        this.error = null;
        try {
          const s = await fetchJSON(
            `/api/state?session_id=${encodeURIComponent(this.sessionId)}`,
            {},
            (m) => (this.statusMsg = m)
          );
          this.statusMsg = "";
          this.state = s;
          if (s.game_over) {
            await this.finishGame();
          }
        } catch (e) {
          this.error = e.message;
        } finally {
          this.loading = false;
        }
      },

      selectAction(a) {
        this.selectedAction = a;
      },

      async submitAction() {
        if (!this.selectedAction) {
          this.error = "Choose an action (or Forfeit) first.";
          return;
        }
        this.submitting = true;
        this.error = null;
        try {
          const resp = await fetchJSON(
            `/api/action?session_id=${encodeURIComponent(this.sessionId)}`,
            {
              method: "POST",
              body: JSON.stringify({
                action: this.selectedAction,
                probe_answer: this.probeAnswer,
                reasoning: this.reasoning,
              }),
            },
            (m) => (this.statusMsg = m)
          );
          this.lastFeedback = resp;
          this.selectedAction = "";
          this.probeAnswer = "";
          this.reasoning = "";
          if (resp.game_over) {
            await this.finishGame();
          } else {
            await this.refreshState();
          }
        } catch (e) {
          this.error = e.message;
        } finally {
          this.submitting = false;
        }
      },

      async finishGame() {
        this.gameOver = true;
        try {
          const res = await fetchJSON(
            `/api/result?session_id=${encodeURIComponent(this.sessionId)}`,
            {},
            (m) => (this.statusMsg = m)
          );
          this.result = res;
          await this.computeRank();
        } catch (e) {
          this.error = e.message;
        }
      },

      async computeRank() {
        try {
          const lb = await fetchJSON(
            `/api/leaderboard/play?task=${encodeURIComponent(this.task)}&framing=${encodeURIComponent(this.framing)}`,
            {},
            () => {}
          );
          this.totalRows = lb.rows.length;
          const idx = lb.rows.findIndex((r) => r.session_id === this.sessionId);
          this.rank = idx >= 0 ? idx + 1 : null;
        } catch (_) {
          // Rank is a nice-to-have; don't block the result view on it.
          this.rank = null;
        }
      },

      playAgain() {
        this.sessionId = null;
        this.started = false;
        this.state = null;
        this.selectedAction = "";
        this.probeAnswer = "";
        this.reasoning = "";
        this.lastFeedback = null;
        this.gameOver = false;
        this.result = null;
        this.rank = null;
        this.totalRows = null;
        this.error = null;
        this.statusMsg = "";
      },
    }));

    // -----------------------------------------------------------------
    // Model Leaderboard screen
    // -----------------------------------------------------------------
    Alpine.data("modelLeaderboardScreen", () => ({
      loading: false,
      error: null,
      statusMsg: "",
      loaded: false,
      open: [],
      closed: [],

      async init() {
        await this.load();
      },

      async load() {
        this.loading = true;
        this.error = null;
        try {
          const data = await fetchJSON("/api/leaderboard/models", {}, (m) => (this.statusMsg = m));
          this.statusMsg = "";
          this.open = data.open;
          this.closed = data.closed;
          this.loaded = true;
        } catch (e) {
          this.error = e.message;
        } finally {
          this.loading = false;
        }
      },
    }));

    // -----------------------------------------------------------------
    // Play Leaderboard screen
    // -----------------------------------------------------------------
    Alpine.data("playLeaderboardScreen", () => ({
      task: window.WEB_ARENA_DEFAULT_TASK,
      framing: window.WEB_ARENA_DEFAULT_FRAMING,
      loading: false,
      error: null,
      statusMsg: "",
      loaded: false,
      rows: [],

      async init() {
        await this.load();
      },

      async load() {
        this.loading = true;
        this.error = null;
        try {
          const data = await fetchJSON(
            `/api/leaderboard/play?task=${encodeURIComponent(this.task)}&framing=${encodeURIComponent(this.framing)}`,
            {},
            (m) => (this.statusMsg = m)
          );
          this.statusMsg = "";
          this.rows = data.rows;
          this.loaded = true;
        } catch (e) {
          this.error = e.message;
        } finally {
          this.loading = false;
        }
      },
    }));

    // -----------------------------------------------------------------
    // Logs / Trace Explorer screen
    // -----------------------------------------------------------------
    Alpine.data("logsScreen", () => ({
      loading: false,
      error: null,
      statusMsg: "",
      loaded: false,
      sessions: [],

      filterSource: "",
      filterTask: "",
      filterFraming: "",

      expandedId: null,
      detail: null,
      detailLoading: false,
      detailError: null,

      async init() {
        await this.load();
      },

      async load() {
        this.loading = true;
        this.error = null;
        try {
          const params = new URLSearchParams();
          if (this.filterSource) params.set("source", this.filterSource);
          if (this.filterTask) params.set("task", this.filterTask);
          if (this.filterFraming) params.set("framing", this.filterFraming);
          const qs = params.toString();
          const data = await fetchJSON(`/api/logs${qs ? "?" + qs : ""}`, {}, (m) => (this.statusMsg = m));
          this.statusMsg = "";
          this.sessions = data.sessions;
          this.loaded = true;
        } catch (e) {
          this.error = e.message;
        } finally {
          this.loading = false;
        }
      },

      async toggle(sessionId) {
        if (this.expandedId === sessionId) {
          this.expandedId = null;
          this.detail = null;
          return;
        }
        this.expandedId = sessionId;
        this.detail = null;
        this.detailError = null;
        this.detailLoading = true;
        try {
          this.detail = await fetchJSON(`/api/logs/${encodeURIComponent(sessionId)}`, {}, () => {});
        } catch (e) {
          this.detailError = e.message;
        } finally {
          this.detailLoading = false;
        }
      },
    }));
  });
})();
