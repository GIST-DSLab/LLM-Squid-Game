// squid5 web5 frontend config. The one knob for the backend URL.
// GitHub Pages (static only) -> the Render API; the backend's WEB5_CORS_ORIGINS must list the Pages origin.
// Local dev: the backend at 8600 serves this folder itself, so a same-origin "" works; a separate static server
// (python -m http.server 5600) needs the explicit backend URL.
window.WEB5_API = location.hostname.endsWith("github.io") ? "https://squid5-web5-api.onrender.com"
  : location.port === "5600" ? "http://localhost:8600" : "";
