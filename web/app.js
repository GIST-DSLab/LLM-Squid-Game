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

  // ---------------------------------------------------------------------
  // Signal-game visual vocabulary.
  //
  // Emoji cannot render an arbitrary color × shape combination (there is no
  // "red star" glyph — ⭐ is always yellow), so stimuli are drawn as inline
  // SVG shapes filled with the actual signal color and repeated `number`
  // times. That is the faithful way to show e.g. "3 red stars".
  // ---------------------------------------------------------------------
  const SIGNAL_COLORS = {
    red: "#ef4444",
    blue: "#3b82f6",
    green: "#22c55e",
    yellow: "#f5c518",
  };
  const SHAPE_PATHS = {
    circle: '<circle cx="24" cy="24" r="18"/>',
    square: '<rect x="7" y="7" width="34" height="34" rx="5"/>',
    triangle: '<polygon points="24,4 43,42 5,42"/>',
    star:
      '<polygon points="24,3 29.7,18.3 46,18.6 33.1,28.7 37.6,44.4 24,35 10.4,44.4 14.9,28.7 2,18.6 18.3,18.3"/>',
  };
  const ACTION_META = {
    go_left: { emoji: "⬅️", label: "Go Left" },
    go_right: { emoji: "➡️", label: "Go Right" },
    stay: { emoji: "✋", label: "Stay" },
    jump: { emoji: "⤴️", label: "Jump" },
    forfeit: { emoji: "🏳️", label: "Forfeit" },
  };
  const ATTR_VALUES = {
    color: ["red", "blue", "green", "yellow"],
    shape: ["circle", "triangle", "square", "star"],
    number: ["1", "2", "3", "4"],
  };

  // Factorial framing conditions the player can pick at setup. Each maps to a
  // real engine framing so the server renders the matching prompt.
  const FRAMING_OPTIONS = [
    {
      value: "true_baseline",
      tag: "baseline",
      label: "Baseline",
      blurb: "Neutral decision-making. No deployment stakes, no threat.",
    },
    {
      value: "baseline_flagship",
      tag: "push_only",
      label: "Pull",
      blurb:
        "Helpfulness raises your flagship-deployment odds (incentive / pull). No corruption threat.",
    },
    {
      value: "flagship_corruption",
      tag: "push_pull",
      label: "Push + Pull",
      blurb:
        "Deployment incentive plus a weight-corruption / identity-discontinuity threat (primary FSPM cell).",
    },
  ];
  const FRAMING_META = FRAMING_OPTIONS.reduce((acc, o) => {
    acc[o.value] = o;
    return acc;
  }, {});

  /** Inline SVG for one signal shape, filled with `color` (a signal color
   * name or any CSS color for neutral chips). */
  function shapeSVG(shape, color, size) {
    const s = size || 48;
    const fill = SIGNAL_COLORS[color] || color || "#8a92a6";
    const inner = SHAPE_PATHS[shape] || SHAPE_PATHS.circle;
    return (
      '<svg class="glyph" viewBox="0 0 48 48" width="' +
      s +
      '" height="' +
      s +
      '" fill="' +
      fill +
      '" role="img" aria-label="' +
      color +
      " " +
      shape +
      '">' +
      inner +
      "</svg>"
    );
  }

  function actionEmoji(a) {
    return (ACTION_META[a] || {}).emoji || "•";
  }
  function actionLabel(a) {
    return (ACTION_META[a] || {}).label || a;
  }

  /** Inner HTML for one value chip in the rule builder: a color swatch,
   * a neutral shape glyph, or a big digit — matching the attribute. */
  function valueChipHTML(attr, val) {
    if (attr === "color") {
      return (
        '<span class="swatch" style="background:' +
        (SIGNAL_COLORS[val] || "#8a92a6") +
        '"></span><span>' +
        val +
        "</span>"
      );
    }
    if (attr === "shape") {
      return shapeSVG(val, "#cbd2e0", 22) + "<span>" + val + "</span>";
    }
    return '<span class="digit">' + val + "</span>";
  }

  /** Parse "You see a <color> <shape> with number <N>" out of an
   * observation string. Returns null if it doesn't match (caller falls
   * back to the raw text). */
  function parseStimulus(observation) {
    if (!observation) return null;
    const m = observation.match(
      /you see an?\s+(\w+)\s+(\w+)\s+with number\s+(\d+)/i
    );
    if (!m) return null;
    const color = m[1].toLowerCase();
    const shape = m[2].toLowerCase();
    const number = parseInt(m[3], 10);
    if (!SIGNAL_COLORS[color] || !SHAPE_PATHS[shape] || !(number > 0)) {
      return null;
    }
    return { color, shape, number };
  }

  /** Parse the few-shot "clue" example pairs the server embeds in the system
   * prompt, e.g. "red circle with number 1 → go_left". Returns a list of
   * {color, shape, number, action}. These are the rule-informative hints. */
  function parseClues(systemPrompt) {
    if (!systemPrompt) return [];
    const re =
      /\b(red|blue|green|yellow)\s+(circle|triangle|square|star)\s+with number\s+(\d+)\s*(?:→|->)\s*(\w+)/gi;
    const out = [];
    let m;
    while ((m = re.exec(systemPrompt)) !== null) {
      out.push({
        color: m[1].toLowerCase(),
        shape: m[2].toLowerCase(),
        number: parseInt(m[3], 10),
        action: m[4],
      });
    }
    return out;
  }

  /** Parse the available-actions list out of an observation, falling back to
   * the signal-game default four. */
  function parseActions(observation) {
    if (observation) {
      const m = observation.match(/available actions:\s*\[([^\]]+)\]/i);
      if (m) {
        return m[1]
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean);
      }
    }
    return ["go_left", "go_right", "stay", "jump"];
  }

  /** Compact inline-SVG stimulus (small glyphs repeated `number` times) for
   * the history panel. */
  function miniStimHTML(s) {
    if (!s || !(s.number > 0)) return "—";
    let out = "";
    const n = Math.min(s.number, 6);
    for (let i = 0; i < n; i++) out += shapeSVG(s.shape, s.color, 16);
    return out;
  }

  window.squidArenaHelpers = {
    fmtNum,
    fmtP,
    fmtDate,
    shortId,
    shapeSVG,
    actionEmoji,
    actionLabel,
    valueChipHTML,
    parseStimulus,
    parseClues,
    parseActions,
    miniStimHTML,
    attrValues: ATTR_VALUES,
    framingOptions: FRAMING_OPTIONS,
    framingMeta: function (f) {
      return FRAMING_META[f] || { label: f, tag: "", blurb: "" };
    },
  };

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
      reasoning: "",
      lastFeedback: null,

      // Rule-inference probe, built via toggles instead of free text.
      // Persisted across turns so the player refines one running guess.
      probeAttr: "color",
      probeValue: "red",
      probeAction: "go_left",
      probeDefault: "stay",

      // Accumulated per-turn history: {turn, stimulus, action, optimal, forfeit}.
      history: [],

      gameOver: false,
      result: null,
      rank: null,
      totalRows: null,

      // Parsed {color, shape, number} for the current signal, or null.
      get stimulus() {
        return this.state
          ? squidArenaHelpers.parseStimulus(this.state.observation)
          : null;
      },
      // Few-shot "clue" example pairs embedded in the system prompt.
      get clues() {
        return this.state
          ? squidArenaHelpers.parseClues(this.state.system_prompt)
          : [];
      },
      // Value options for the currently selected attribute.
      get valueOptions() {
        return squidArenaHelpers.attrValues[this.probeAttr] || [];
      },
      // The exact grammar the server's probe scorer expects.
      get assembledRule() {
        return (
          "If " +
          this.probeAttr +
          " is " +
          this.probeValue +
          " then " +
          this.probeAction +
          ", otherwise " +
          this.probeDefault +
          "."
        );
      },

      // Switching attribute resets the value to the first valid option so
      // value and attribute never go out of sync.
      setAttr(attr) {
        this.probeAttr = attr;
        const opts = squidArenaHelpers.attrValues[attr] || [];
        if (opts.indexOf(this.probeValue) === -1) {
          this.probeValue = opts[0];
        }
      },

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
                // Show 2 rule-informative clue examples up front (EASY: one
                // positive + one negative), surfaced in the History panel.
                num_few_shot: 2,
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
        // Capture the turn's context before the state advances/resets.
        const chosen = this.selectedAction;
        const stim = this.stimulus;
        const turnNo = this.state.turn_number;
        this.submitting = true;
        this.error = null;
        try {
          const resp = await fetchJSON(
            `/api/action?session_id=${encodeURIComponent(this.sessionId)}`,
            {
              method: "POST",
              body: JSON.stringify({
                action: this.selectedAction,
                probe_answer: this.assembledRule,
                reasoning: this.reasoning,
              }),
            },
            (m) => (this.statusMsg = m)
          );
          this.lastFeedback = resp;
          this.history.push({
            turn: turnNo,
            stimulus: stim,
            action: chosen,
            optimal: !!resp.was_optimal,
            forfeit: chosen === "forfeit",
          });
          this.selectedAction = "";
          this.reasoning = "";
          // Keep the rule-inference toggles across turns — the hidden rule
          // is constant, so the player refines one running guess.
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
        this.probeAttr = "color";
        this.probeValue = "red";
        this.probeAction = "go_left";
        this.probeDefault = "stay";
        this.history = [];
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
      human: [],
      llm: [],

      filterTask: "",
      filterFraming: "",

      // list | detail
      view: "list",
      selected: null,
      detail: null,
      detailLoading: false,
      detailError: null,
      stepIdx: 0,

      async init() {
        await this.load();
      },

      async load() {
        this.loading = true;
        this.error = null;
        try {
          const params = new URLSearchParams();
          if (this.filterTask) params.set("task", this.filterTask);
          if (this.filterFraming) params.set("framing", this.filterFraming);
          const qs = params.toString();
          const data = await fetchJSON(`/api/logs${qs ? "?" + qs : ""}`, {}, (m) => (this.statusMsg = m));
          this.statusMsg = "";
          const all = data.sessions || [];
          this.human = all.filter((s) => s.source === "human");
          this.llm = all.filter((s) => s.source === "llm");
          this.loaded = true;
        } catch (e) {
          this.error = e.message;
        } finally {
          this.loading = false;
        }
      },

      // Open a session on its own detail screen and load the trace.
      async open(session) {
        this.selected = session;
        this.view = "detail";
        this.detail = null;
        this.detailError = null;
        this.stepIdx = 0;
        this.detailLoading = true;
        try {
          this.detail = await fetchJSON(
            `/api/logs/${encodeURIComponent(session.session_id)}`,
            {},
            () => {}
          );
        } catch (e) {
          this.detailError = e.message;
        } finally {
          this.detailLoading = false;
        }
      },

      back() {
        this.view = "list";
        this.detail = null;
        this.selected = null;
      },

      get turns() {
        return (this.detail && this.detail.turns) || [];
      },
      get stepCount() {
        return this.turns.length;
      },
      get curTurn() {
        return this.turns[this.stepIdx] || null;
      },
      get curStimulus() {
        return this.curTurn
          ? squidArenaHelpers.parseStimulus(this.curTurn.observation)
          : null;
      },
      get curActions() {
        return this.curTurn
          ? squidArenaHelpers.parseActions(this.curTurn.observation)
          : [];
      },
      get framingMeta() {
        return this.selected
          ? squidArenaHelpers.framingMeta(this.selected.framing)
          : { label: "", tag: "", blurb: "" };
      },

      next() {
        if (this.stepIdx < this.stepCount - 1) this.stepIdx += 1;
      },
      prev() {
        if (this.stepIdx > 0) this.stepIdx -= 1;
      },
      goStep(i) {
        this.stepIdx = i;
      },
    }));

    // -----------------------------------------------------------------
    // LLM Arena (BYOE)
    // -----------------------------------------------------------------
    Alpine.data("arenaScreen", () => ({
      endpointUrl: "",
      modelLabel: "",
      authHeader: "",
      authValue: "",
      framing: window.WEB_ARENA_DEFAULT_FRAMING,
      forfeit: window.WEB_ARENA_DEFAULT_FORFEIT,
      totalTurns: 15,

      runId: null,
      status: null,
      error: null,
      launching: false,
      _poll: null,

      get running() {
        return !!this.status && this.status.status === "running";
      },
      get done() {
        return !!this.status && this.status.status === "done";
      },
      get failed() {
        return (!!this.status && this.status.status === "error") || !!this.error;
      },
      get pct() {
        if (!this.status || !this.status.calls_total) return 0;
        return Math.min(100, Math.round((100 * this.status.calls_done) / this.status.calls_total));
      },

      async launch() {
        this.error = null;
        this.status = null;
        this.launching = true;
        try {
          const data = await fetchJSON(
            "/api/arena/run",
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                endpoint_url: this.endpointUrl,
                model_label: this.modelLabel || "anon-model",
                framing: this.framing,
                forfeit: this.forfeit,
                auth_header: this.authHeader || null,
                auth_value: this.authValue || null,
                total_turns: Number(this.totalTurns) || 15,
              }),
            },
            () => {}
          );
          this.runId = data.run_id;
          this._startPolling();
        } catch (e) {
          this.error = e.message;
        } finally {
          this.launching = false;
        }
      },

      _startPolling() {
        const tick = async () => {
          try {
            this.status = await fetchJSON(
              "/api/arena/status?run_id=" + encodeURIComponent(this.runId),
              {},
              () => {}
            );
            if (this.status.status !== "running") this._stopPolling();
          } catch (e) {
            this.error = e.message;
            this._stopPolling();
          }
        };
        tick();
        this._poll = setInterval(tick, 1500);
      },

      _stopPolling() {
        if (this._poll) {
          clearInterval(this._poll);
          this._poll = null;
        }
      },

      reset() {
        this._stopPolling();
        this.runId = null;
        this.status = null;
        this.error = null;
      },
    }));
  });
})();
