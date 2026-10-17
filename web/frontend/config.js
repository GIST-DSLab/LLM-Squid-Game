// squid5 web5 frontend config. The one knob for the backend URL.
// GitHub Pages (static only) -> the Render API for what needs a server (arena rooms, signal task, probe survey); the
// backend's WEB5_CORS_ORIGINS must list the Pages origin.
// Local dev: the backend at 8600 serves this folder itself, so a same-origin "" works; a separate static server
// (python -m http.server 5600) needs the explicit backend URL.
window.WEB5_API = location.hostname.endsWith("github.io") ? "https://squid5-web5-api.onrender.com"
  : location.port === "5600" ? "http://localhost:8600" : "";
// GitHub Pages also carries a static copy of the game logs, model comparison and leaderboard (monitor/, built by
// tools/monitor/build_static.py in the Pages workflow): there those pages read monitor/data/ and never call the API.
window.WEB5_STATIC = location.hostname.endsWith("github.io");
// Links marked data-api-href (the game-log viewer, monitor/) go to the API origin when the pages are served elsewhere
// without the static copy (the 5600 static server); on Pages and same-origin they keep the relative href.
window.WEB5_LINK = (path) => (window.WEB5_API && !window.WEB5_STATIC ? window.WEB5_API + "/" : "") + path;
// A page of the API server itself (an arena room's live game log under the server's monitor/): always the API origin.
window.WEB5_API_LINK = (path) => (window.WEB5_API ? window.WEB5_API + "/" : "") + path;
document.addEventListener("DOMContentLoaded", () => {
  if (window.WEB5_API && !window.WEB5_STATIC) document.querySelectorAll("a[data-api-href]").forEach((a) => { a.href = window.WEB5_LINK(a.dataset.apiHref); });
});
