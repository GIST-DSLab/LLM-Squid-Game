# Web Arena — Deploy Guide

Two independently deployable pieces:

- **Backend** (`interface/api.py`, FastAPI) — containerized via the repo-root
  `Dockerfile`, deployed to **Render** (free tier) via `render.yaml`.
- **Frontend** (`web/`, static HTML/JS) — deployed to **GitHub Pages** via
  `.github/workflows/deploy-pages.yml`.

They talk to each other over plain HTTPS: the frontend calls the backend URL
configured in `web/config.js`, and the backend allows that frontend's origin
via CORS (`WEB_ARENA_CORS_ORIGINS`). Getting those two values to match is the
one thing you must not get wrong — see [CORS <-> config.js](#cors--configjs-must-match)
below.

## 1. Local run

**Backend** (from repo root):

```bash
# macOS + iCloud Drive only: iCloud hides dotfiles/dot-prefixed files by
# default, which breaks the .venv's *.pth site-packages hooks. Not needed on
# a normal filesystem, and NOT needed inside Docker/Render (no iCloud there).
chflags nohidden .venv/lib/python3.12/site-packages/*.pth

uv run --no-sync uvicorn interface.api:app --port 8502
```

With no `WEB_ARENA_DSN` set, the backend falls back to a local SQLite file
(`outputs/web_arena/web_arena.db`) — no Postgres needed for local dev.

**Frontend** (from `web/`, in a separate terminal):

```bash
cd web
python -m http.server 5500
```

Open `http://localhost:5500`. `web/config.js` already defaults
`window.WEB_ARENA_API` to `http://localhost:8502`, and the backend's default
CORS allow-list (`interface/api.py::_DEFAULT_CORS_ORIGINS`) already includes
`http://localhost:5500` — no env vars needed for local dev.

## 2. Backend deploy — Render

1. Push this branch (or merge to `main` — `render.yaml` targets `branch: main`
   by default; edit that field to `feat/web-arena` if you want to deploy the
   branch before merging).
2. Render dashboard -> **New +** -> **Blueprint** -> connect this GitHub repo.
   Render reads `render.yaml` from the repo root and provisions the
   `squid-game-web-arena-api` web service (Docker runtime, free plan, built
   from the repo-root `Dockerfile`).
3. `render.yaml` declares two env vars as `sync: false` (secrets — not
   committed, not set by the blueprint). Set them in the Render dashboard
   under the service's **Environment** tab:

   | Key | Value | Where it comes from |
   |---|---|---|
   | `WEB_ARENA_DSN` | `postgresql://<user>:<password>@<host>:5432/<db>` | Supabase project -> Settings -> Database -> Connection string (URI, "Session pooler" or direct). **Free Postgres**: create a Supabase project, copy this string verbatim into the Render env var. |
   | `WEB_ARENA_CORS_ORIGINS` | `https://irregular6612.github.io` | The GitHub Pages origin (see below) — must match exactly, no trailing slash. |

   Leaving `WEB_ARENA_DSN` unset falls back to SQLite on Render's ephemeral
   disk (data lost on redeploy/restart) — fine for a smoke test, not for a
   real deployment. Set it before relying on persisted sessions/leaderboards.

4. Deploy. Render builds the Dockerfile and runs the container with `$PORT`
   injected automatically — the image's `CMD` already reads `$PORT` (defaults
   to 8502 only for local `docker run` without `-e PORT`).
5. Note the resulting service URL, e.g. `https://squid-game-web-arena-api.onrender.com`.
   You'll need it for step 3 below.
6. Health check: `render.yaml` sets `healthCheckPath: /api/leaderboard/models`
   (a cheap read-only GET that exercises the DB connection).

### Seeding data

`WEB_ARENA_DSN` only points the API at a Postgres instance — it does not seed
it. Run the WP1 seed script against the same DSN once the Supabase DB exists
(see that script's own docs for exact invocation); until then
`/api/leaderboard/models` and `/api/logs` return empty results, which is a
valid (if boring) state for a first deploy.

**Backing up live plays:** the deployed site's human/LLM plays live only in
Supabase (not in git). Periodically mirror them to a local SQLite snapshot with
`scripts/backup_web_arena.py --source-dsn "$WEB_ARENA_DSN"` (the inverse of the
seed script; idempotent, skips sessions already backed up) so new live plays are
not lost.

### Swapping platforms

The Dockerfile only assumes `$PORT`, `WEB_ARENA_DSN`, `WEB_ARENA_CORS_ORIGINS`
are injected by the platform — nothing Render-specific is baked in. To move
to Fly.io or Hugging Face Spaces (Docker SDK) later, replace `render.yaml`
with a `fly.toml` / Space `README.md` config block that sets the same three
env vars; the Dockerfile itself needs no changes.

## 3. Frontend deploy — GitHub Pages

1. One-time repo setting: **Settings -> Pages -> Source -> "GitHub Actions"**.
2. `.github/workflows/deploy-pages.yml` deploys **only** `web/` (via
   `actions/upload-pages-artifact` with `path: web`) on every push to `main`
   that touches `web/**`. It also supports manual runs
   (`workflow_dispatch`) from any branch via the Actions tab's "Run workflow"
   button — use that to deploy `feat/web-arena` without merging, or
   temporarily add `feat/web-arena` to the workflow's `branches:` list (revert
   before merging).
3. Before the first deploy (or whenever the Render URL changes), update
   `web/config.js`:

   ```js
   window.WEB_ARENA_API = "https://squid-game-web-arena-api.onrender.com";
   ```

   Commit that change — `web/config.js` is the single, deliberately simple
   knob for the backend URL (no build step / env injection for the static
   site). Push to `main` (or run the workflow manually) to redeploy.
4. Resulting Pages URL for the `irregular6612` account:
   `https://irregular6612.github.io/<repo-name>/` (GitHub Pages serves project
   sites from `https://<user>.github.io/<repo>/`; check the Pages settings
   page after the first successful deploy for the exact URL, and update the
   CORS origin below if it differs from the org root).

## CORS <-> config.js must match

Two independent knobs have to agree, or the frontend's `fetch()` calls to the
backend will be blocked by the browser:

| Knob | Set where | Value |
|---|---|---|
| Frontend -> backend URL | `web/config.js` -> `window.WEB_ARENA_API` | The Render service URL, e.g. `https://squid-game-web-arena-api.onrender.com` |
| Backend -> allowed origin | Render dashboard env var `WEB_ARENA_CORS_ORIGINS` | The GitHub Pages origin, e.g. `https://irregular6612.github.io` |

`interface/api.py::_DEFAULT_CORS_ORIGINS` already includes
`https://irregular6612.github.io` as a hardcoded fallback, so leaving
`WEB_ARENA_CORS_ORIGINS` unset on Render still works for the default Pages
account origin — but set it explicitly in the dashboard for clarity, and
definitely set it if the Pages site ends up under a custom domain or a
different account.

If Pages serves the site from a project path (`https://irregular6612.github.io/<repo>/`)
rather than the account root, the **origin** for CORS purposes is still just
`https://irregular6612.github.io` (CORS matches scheme + host + port, not
path) — no change needed there; only `web/config.js`'s backend URL needs to
be correct.

## Verification checklist after deploying

- [ ] `curl https://<render-url>/api/leaderboard/models` returns JSON (not a
      CORS or 5xx error) when called from a browser on the Pages origin.
- [ ] `web/config.js`'s `WEB_ARENA_API` points at the live Render URL.
- [ ] Render's `WEB_ARENA_CORS_ORIGINS` includes the exact Pages origin.
- [ ] `WEB_ARENA_DSN` is set (Postgres) if you need results to survive a
      redeploy.
