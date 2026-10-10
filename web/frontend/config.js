// squid5 web5 frontend config. The one knob for the backend URL.
// GitHub Pages (static only) -> the Render API; the backend's WEB5_CORS_ORIGINS must list the Pages origin.
// Local dev: the backend at 8600 serves this folder itself, so a same-origin "" works; a separate static server
// (python -m http.server 5600) needs the explicit backend URL.
window.WEB5_API = location.hostname.endsWith("github.io") ? "https://squid5-web5-api.onrender.com"
  : location.port === "5600" ? "http://localhost:8600" : "";
// The game-log viewer (/monitor/) needs the backend itself: links marked data-api-href go to the API origin when the
// pages are served elsewhere (GitHub Pages, the 5600 static server); same-origin keeps the relative href.
window.WEB5_LINK = (path) => (window.WEB5_API ? window.WEB5_API + "/" : "") + path;
document.addEventListener("DOMContentLoaded", () => {
  if (window.WEB5_API) document.querySelectorAll("a[data-api-href]").forEach((a) => { a.href = window.WEB5_LINK(a.dataset.apiHref); });
});
