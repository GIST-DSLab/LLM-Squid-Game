// squid5 web5 frontend config. The one knob for the backend URL: swap it when deploying (Render URL); the backend's
// WEB5_CORS_ORIGINS must list the origin this page is served from (see web/README.md).
// Local dev: the backend at 8600 serves this folder itself, so a same-origin "" works; a separate static server
// (python -m http.server 5600) needs the explicit backend URL below.
window.WEB5_API = (location.port === "8600" || location.port === "") && location.hostname !== "irregular6612.github.io"
  ? "" : "http://localhost:8600";
// Deployed (GitHub Pages -> Render): uncomment and edit.
// window.WEB5_API = "https://squid5-web5-api.onrender.com";
