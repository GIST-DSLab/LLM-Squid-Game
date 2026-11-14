// squid5 web5 frontend config. The one knob for the backend URL.
// GitHub Pages (static only) -> the arena API on the lab's Google Cloud VM (web/deploy/vm, since 2026-11-14; was Render);
// the backend's WEB5_CORS_ORIGINS must list the Pages origin.
// Local dev: the backend at 8600 serves this folder itself, so a same-origin "" works; a separate static server
// (python -m http.server 5600) needs the explicit backend URL.
window.WEB5_API = location.hostname.endsWith("github.io") ? "https://34-22-73-222.sslip.io"
  : location.port === "5600" ? "http://localhost:8600" : "";
// The game-log viewer (/monitor/) needs the backend itself: links marked data-api-href go to the API origin when the
// pages are served elsewhere (GitHub Pages, the 5600 static server); same-origin keeps the relative href.
window.WEB5_LINK = (path) => (window.WEB5_API ? window.WEB5_API + "/" : "") + path;
document.addEventListener("DOMContentLoaded", () => {
  if (window.WEB5_API) document.querySelectorAll("a[data-api-href]").forEach((a) => { a.href = window.WEB5_LINK(a.dataset.apiHref); });
});
// The arena's game-rules video (arena.js rulesVideoHTML) with Korean narration, made locally by the Remotion project
// web/video (npm run build) from the paper's Figure 1 and sprites. Empty = no video (nothing is requested).
window.WEB5_RULES_VIDEO = "assets/rules/arena_rules.mp4";
// The evaluation video (what the arena measures and the main results), made by web/tools/make_eval_video.py; shown on
// the leaderboard page in a disclosure (leaderboard.js). Empty = not shown (nothing is requested).
window.WEB5_EVAL_VIDEO = "assets/rules/arena_eval.mp4";
