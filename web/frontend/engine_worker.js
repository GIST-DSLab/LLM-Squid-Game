// The squid5 engine in a module Web Worker (new Worker(url, {type: "module"})): Pyodide + the engine bundle (engine/manifest.json -> squid5-engine-<hash>.zip,
// built by web/pyodide/build_bundle.py from the repo's squid5/ and web/server/). The page never blocks on it.
//
// Messages in:  {id, op: "init", args: {pyodideUrl, manifestUrl, worker}}
//               {id, op: "call", args: {method, path, body}}     -> browser.Arena.handle (the old REST routes)
//               {id, op: "restore", args: {code, text}}          -> a room from its saved doc + replies (after a reload)
// Messages out: {type: "result", id, ok, result | error}, {type: "progress", step, pct, text},
//               {type: "persist", code, text} (the page keeps it in localStorage), {type: "warm", did, ms}
"use strict";

let PY = null;
let arena = null;
let busy = 0;
let idleTimer = null;

const post = (m) => self.postMessage(m);
const progress = (step, pct, text) => post({ type: "progress", step, pct, text });
const hex = (buf) => Array.from(new Uint8Array(buf), (b) => b.toString(16).padStart(2, "0")).join("");

// what the Python side calls back (browser.Arena hooks)
const hooks = {
  persist(code, text) { post({ type: "persist", code, text }); },
  // the game record, gzip-compressed, to the Worker (POST /api/games/<id>/record); the summary is a small ASCII header
  async upload(url, token, text, summary) {
    try {
      const gz = await new Response(new Blob([text]).stream().pipeThrough(new CompressionStream("gzip"))).arrayBuffer();
      const r = await fetch(url, {
        method: "POST", body: gz,
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/gzip", "X-Squid5-Summary": summary },
      });
      let body = null;
      try { body = await r.json(); } catch { /* empty */ }
      return { status: r.status, body };
    } catch (e) {
      return { status: 0, body: { detail: `기록을 보내지 못했습니다(네트워크): ${e && e.message ? e.message : e}` } };
    }
  },
};

async function init(cfg) {
  const t0 = performance.now();
  const ms = () => Math.round(performance.now() - t0);
  const timings = {};
  progress("pyodide", 3, "Python 런타임(Pyodide) 내려받는 중… (처음 한 번 약 10 MB, 이후 캐시)");
  let mod = null;
  for (let attempt = 1; ; attempt += 1) {  // a flaky first connection to the CDN: try three times
    try { mod = await import(cfg.pyodideUrl + "pyodide.mjs"); break; } catch (e) {
      if (attempt >= 3) throw e;
      progress("pyodide", 3, `Pyodide를 받지 못해 다시 시도합니다 (${attempt}/3)…`);
      await new Promise((r) => setTimeout(r, 1500 * attempt));
    }
  }
  PY = await mod.loadPyodide({ indexURL: cfg.pyodideUrl, stdout: () => {}, stderr: (s) => console.warn(s) });
  timings.pyodide_ms = ms();
  progress("packages", 55, "pyyaml 불러오는 중…");
  await PY.loadPackage("pyyaml", { messageCallback: () => {} });
  timings.pyyaml_ms = ms();
  progress("bundle", 65, "게임 엔진 묶음 내려받는 중…");
  const manRes = await fetch(cfg.manifestUrl, { cache: "no-cache" });
  if (!manRes.ok) throw new Error(`엔진 목록(manifest.json)을 읽지 못했습니다: HTTP ${manRes.status}`);
  const man = await manRes.json();
  const zipRes = await fetch(new URL(man.file, new URL(cfg.manifestUrl, self.location.href)));
  if (!zipRes.ok) throw new Error(`엔진 묶음(${man.file})을 받지 못했습니다: HTTP ${zipRes.status}`);
  const buf = await zipRes.arrayBuffer();
  if (hex(await crypto.subtle.digest("SHA-256", buf)) !== man.sha256) {
    throw new Error("엔진 묶음의 해시가 목록과 다릅니다(배포 중일 수 있습니다). 잠시 뒤 새로고침하세요.");
  }
  PY.unpackArchive(buf, "zip", { extractDir: "/home/pyodide/squid5" });
  timings.bundle_ms = ms();
  progress("import", 80, "엔진 불러오는 중…");
  PY.globals.set("_hooks", hooks);
  PY.globals.set("_worker", cfg.worker || "");
  PY.globals.set("_engine", JSON.stringify({ version: man.version, bundle: man.bundle, pyodide: PY.version }));
  await PY.runPythonAsync([
    "import sys, json",
    "sys.path.insert(0, '/home/pyodide/squid5')",
    "import browser",
    "arena = browser.Arena(_worker, json.loads(_engine), _hooks)",
  ].join("\n"));
  arena = PY.globals.get("arena");
  timings.import_ms = ms();
  progress("ready", 100, "준비됨");
  return { engine: man, pyodide: PY.version, timings };
}

// puzzles of the coming rounds while the page is idle (browser.Arena.warm_step never runs while a person's screen is open)
function scheduleIdle(delay) {
  clearTimeout(idleTimer);
  idleTimer = setTimeout(idle, delay ?? 400);
}
function idle() {
  if (!arena || busy) return;
  const t0 = performance.now();
  let did = null;
  try { did = arena.warm_step(); } catch (e) { console.warn("warm_step", e); return; }
  if (did != null) {
    post({ type: "warm", did: String(did), ms: Math.round(performance.now() - t0) });
    scheduleIdle(30);
  }
}

self.onmessage = async (ev) => {
  const { id, op, args } = ev.data || {};
  clearTimeout(idleTimer);
  busy += 1;
  try {
    let result;
    if (op === "init") result = await init(args);
    else if (!arena) throw new Error("엔진이 아직 준비되지 않았습니다.");
    else if (op === "call") result = JSON.parse(await arena.handle(args.method, args.path, args.body || ""));
    else if (op === "restore") result = arena.restore(args.code, args.text);
    else throw new Error(`unknown op ${op}`);
    post({ type: "result", id, ok: true, result });
  } catch (e) {
    post({ type: "result", id, ok: false, error: String((e && e.message) || e) });
  } finally {
    busy -= 1;
    scheduleIdle();
  }
};
