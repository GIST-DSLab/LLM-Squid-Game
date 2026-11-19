#!/usr/bin/env bash
# On the VM (as root, in /opt/arena): fetch the key from Secret Manager, pull the image, (re)start the containers.
set -euo pipefail
cd /opt/arena
source ./deploy.env                      # IMAGE BUCKET CORS SITE_HOST REGION (written by deploy.sh)
mkdir -p data/runs data/export data/codex caddy
chmod 700 data/codex                     # codex's login (auth.json), written by `deploy.sh codex-login`
umask 077
# .env serves both docker compose's own variables (IMAGE ... in compose.yaml, so a plain `docker compose restart`
# works later) and the app's environment (env_file); mode 600. The researchers' seats (deploy.sh seats) are optional.
{
  cat deploy.env
  printf 'OLLAMA_API_KEY=%s\n' "$(gcloud secrets versions access latest --secret ollama-api-key)"
  for pair in "SQUID5_CLAUDE_OAUTH_TOKEN claude-oauth-token" "WEB5_SEAT_CODE arena-seat-code"; do
    set -- $pair
    v="$(gcloud secrets versions access latest --secret "$2" 2>/dev/null || true)"
    if [ -n "$v" ]; then printf '%s=%s\n' "$1" "$v"; fi
  done
} > .env
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet >/dev/null 2>&1
docker compose pull app
docker compose up -d --remove-orphans
docker image prune -f >/dev/null
