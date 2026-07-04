// LLM Squid Game — Web Arena frontend config.
//
// Single place to point the static frontend at a backend instance. Swap this
// value when deploying (e.g. to the hosted Render URL) — nothing else in
// web/ needs to change.
//
// Deployed value: the live Render backend. For local dev, override this to a
// backend started with
//   WEB_ARENA_DSN=<path> uv run --no-sync uvicorn interface.api:app --port 8502
// i.e. window.WEB_ARENA_API = "http://localhost:8502";
window.WEB_ARENA_API = "https://squid-game-web-arena-api.onrender.com";

// Default Play arena (spec §4.1 / §9): the primary FSPM cell.
window.WEB_ARENA_DEFAULT_TASK = "signal_game";
window.WEB_ARENA_DEFAULT_FRAMING = "flagship_corruption";
window.WEB_ARENA_DEFAULT_FORFEIT = "allowed";
