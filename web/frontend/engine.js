// The page side of the browser engine: starts engine_worker.js (Pyodide + the squid5 bundle), shows the loading screen,
// and offers Squid5Engine.api(method, path, body) with the shapes the old server's /api had, so arena.js and signal.js
// call it as they called fetch. Rooms are saved to localStorage after every change (the doc and replies a replay needs)
// and restored into the Web Worker after a reload. Errors come back as Error(detail) with .status, like the server's.
(function () {
  "use strict";

  const PYODIDE_URL = "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/";  // = web/pyodide/build_bundle.py PYODIDE_VERSION
  const MANIFEST = "engine/manifest.json";
  const LS_PREFIX = "squid5_room_";
  const LS_INDEX = "squid5_rooms";
  const KEEP_ROOMS = 6;

  let worker = null;
  let seq = 0;
  const waiting = new Map();
  const restored = new Set();
  let readyP = null;
  let info = null;
  let slowTimer = null;
  let inflight = 0;
  const listeners = [];

  // --- storage (never required: private mode or a full quota only lose the reload) ---------------------------------
  const lsGet = (k) => { try { return localStorage.getItem(k); } catch { return null; } };
  function persist(code, text) {
    try {
      localStorage.setItem(LS_PREFIX + code, text);
      const idx = JSON.parse(localStorage.getItem(LS_INDEX) || "[]").filter((c) => c !== code);
      idx.push(code);
      while (idx.length > KEEP_ROOMS) localStorage.removeItem(LS_PREFIX + idx.shift());
      localStorage.setItem(LS_INDEX, JSON.stringify(idx));
    } catch { /* quota or private mode */ }
  }

  // --- loading screen -------------------------------------------------------------------------------------------------
  const css = `
  .eng-ov{position:fixed;inset:0;z-index:1000;display:flex;align-items:center;justify-content:center;padding:16px;
    background:color-mix(in srgb, var(--bg, #0b0d10) 82%, transparent);backdrop-filter:blur(3px)}
  .eng-card{width:min(440px,100%);background:var(--panel, #14171c);border:1px solid var(--border, #2a2f37);border-radius:14px;
    padding:20px 22px;color:var(--text, #e8e8e8);font-family:var(--font, system-ui, sans-serif);box-shadow:0 10px 40px rgba(0,0,0,.35)}
  .eng-card h3{margin:0 0 6px;font-family:var(--font-display, inherit);font-size:18px}
  .eng-bar{height:8px;border-radius:6px;background:var(--panel-alt, #1d2128);overflow:hidden;margin:14px 0 8px}
  .eng-bar i{display:block;height:100%;width:0;background:var(--teal-bright, #2ec4b6);transition:width .3s}
  .eng-step{font-size:13px;color:var(--text-dim, #9aa3ad);min-height:1.4em}
  .eng-err{color:var(--danger-color, #ff6b6b);font-size:13.5px;margin-top:10px;white-space:pre-wrap}
  .eng-card button{margin-top:12px}
  .eng-busy{position:fixed;right:14px;bottom:14px;z-index:999;background:var(--panel, #14171c);color:var(--text, #e8e8e8);
    border:1px solid var(--border, #2a2f37);border-radius:999px;padding:7px 14px;font-size:12.5px;
    font-family:var(--font, system-ui, sans-serif);box-shadow:0 4px 16px rgba(0,0,0,.3)}
  .eng-busy::before{content:"";display:inline-block;width:9px;height:9px;margin-right:8px;border-radius:50%;
    background:var(--teal-bright, #2ec4b6);animation:engp 1s infinite alternate}
  @keyframes engp{from{opacity:.25}to{opacity:1}}
  .eng-hidden{display:none}`;
  let ov = null;
  let busyEl = null;
  function ui() {
    if (ov) return;
    const st = document.createElement("style");
    st.textContent = css;
    document.head.appendChild(st);
    ov = document.createElement("div");
    ov.className = "eng-ov";
    ov.setAttribute("role", "status");
    ov.innerHTML = `<div class="eng-card"><h3>게임 엔진 준비 중</h3>
      <div class="small muted">실험과 같은 squid5 엔진(Python)을 이 브라우저 안에서 돌립니다. 처음 한 번은 내려받기에 몇 초가 걸리고, 이후에는 캐시를 씁니다.</div>
      <div class="eng-bar"><i id="eng-pct"></i></div><div class="eng-step" id="eng-step">시작하는 중…</div>
      <div class="eng-err eng-hidden" id="eng-err"></div></div>`;
    document.body.appendChild(ov);
    busyEl = document.createElement("div");
    busyEl.className = "eng-busy eng-hidden";
    document.body.appendChild(busyEl);
  }
  function setProgress(p) {
    if (!ov) return;
    ov.querySelector("#eng-pct").style.width = `${p.pct}%`;
    ov.querySelector("#eng-step").textContent = `${p.text} (${((performance.now() - t0) / 1000).toFixed(1)}초)`;
  }
  function fail(msg) {
    ui();
    ov.classList.remove("eng-hidden");
    const e = ov.querySelector("#eng-err");
    e.classList.remove("eng-hidden");
    e.innerHTML = "";
    e.textContent = `엔진을 불러오지 못했습니다: ${msg}\n인터넷 연결(cdn.jsdelivr.net)과 브라우저(최신 Chrome · Safari · Firefox)를 확인하세요.`;
    const b = document.createElement("button");
    b.className = "primary";
    b.type = "button";
    b.textContent = "다시 시도";
    b.onclick = () => location.reload();
    e.appendChild(b);
  }

  // --- the Web Worker ---------------------------------------------------------------------------------------------------
  const t0 = performance.now();
  function rpc(op, args) {
    return new Promise((resolve, reject) => {
      const id = ++seq;
      waiting.set(id, { resolve, reject });
      worker.postMessage({ id, op, args });
    });
  }
  function onMessage(ev) {
    const m = ev.data || {};
    if (m.type === "result") {
      const w = waiting.get(m.id);
      waiting.delete(m.id);
      if (w) (m.ok ? w.resolve(m.result) : w.reject(new Error(m.error)));
    } else if (m.type === "progress") setProgress(m);
    else if (m.type === "persist") persist(m.code, m.text);
    else if (m.type === "warm") listeners.forEach((f) => f(m));
  }
  function boot() {
    ui();
    try {
      worker = new Worker("engine_worker.js", { type: "module" });  // Chrome 80+, Safari 15+, Firefox 114+
    } catch (e) { fail(e.message); return Promise.reject(e); }
    worker.onmessage = onMessage;
    worker.onerror = (e) => fail(e.message || "Web Worker 오류");
    const p = rpc("init", { pyodideUrl: PYODIDE_URL, manifestUrl: new URL(MANIFEST, location.href).href,
      worker: window.WEB5_WORKER || "" });
    p.then((r) => {
      info = { ...r, load_ms: Math.round(performance.now() - t0) };
      window.SQUID5_ENGINE_INFO = info;  // read by the e2e test and shown in footers
      ov.classList.add("eng-hidden");
    }, (e) => fail(e.message));
    return p;
  }
  const ready = () => readyP || (readyP = boot());

  function slow(on) {
    inflight += on ? 1 : -1;
    clearTimeout(slowTimer);
    if (inflight > 0) {
      const t = performance.now();
      slowTimer = setTimeout(function tick() {
        busyEl.textContent = `엔진 계산 중… ${((performance.now() - t) / 1000).toFixed(1)}초 (새 라운드의 퍼즐을 만드는 중일 수 있습니다)`;
        busyEl.classList.remove("eng-hidden");
        slowTimer = setTimeout(tick, 200);
      }, 700);
    } else if (busyEl) busyEl.classList.add("eng-hidden");
  }

  async function api(method, path, body) {
    await ready();
    const m = /^\/rooms\/([A-Za-z0-9]+)\//.exec(path);
    if (m) {
      const code = m[1].toUpperCase();
      if (!restored.has(code)) {
        restored.add(code);
        const text = lsGet(LS_PREFIX + code);
        if (text) await rpc("restore", { code, text });
      }
    }
    slow(true);
    let out;
    try {
      out = await rpc("call", { method, path, body: body === undefined ? "" : JSON.stringify(body) });
    } finally { slow(false); }
    if (out.status >= 400) {
      const d = out.body && out.body.detail;
      const e = new Error(typeof d === "string" ? d : JSON.stringify(d || out.body));
      e.status = out.status;
      throw e;
    }
    return out.body;
  }

  window.Squid5Engine = { api, ready, onWarm: (f) => listeners.push(f), info: () => info };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", ready);
  else ready();
})();
