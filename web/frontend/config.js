// squid5 web5 frontend config. The one knob for the backend.
// The game engine runs in this browser (Pyodide in a Web Worker: engine.js, engine_worker.js, engine/ bundle). The only
// server is a thin Cloudflare Worker (web/cloudflare, FREE plan): model calls for model seats (it holds the Ollama key),
// game-record uploads and the survey. Set WORKER_URL after `wrangler deploy` (it prints https://squid5-api.<sub>.workers.dev).
(function () {
  const WORKER_URL = "https://squid5-api.REPLACE-ME.workers.dev";  // <- the deployed Worker (no trailing slash)
  const local = ["localhost", "127.0.0.1"].includes(location.hostname);
  // Local: `wrangler dev` on 8788 (web/cloudflare/README.md); a ?worker= query overrides (tests, previews).
  const q = new URLSearchParams(location.search).get("worker");
  const url = q || (local ? `http://${location.hostname}:8788` : WORKER_URL);
  window.WEB5_WORKER = /REPLACE-ME/.test(url) ? "" : url;  // "" = no Worker: bot games only, not recorded
  window.WEB5_API = window.WEB5_WORKER;  // probe.js posts the survey here (/api/probe)
})();
// The game logs, model comparison and leaderboard are a static copy (monitor/, built by tools/monitor/build_static.py in
// the Pages workflow) everywhere but the old local monitor server (tools/monitor/serve.py, web/server/app.py on 8600).
window.WEB5_STATIC = location.port !== "8600";
window.WEB5_LINK = (path) => path;
window.WEB5_API_LINK = (path) => path;
