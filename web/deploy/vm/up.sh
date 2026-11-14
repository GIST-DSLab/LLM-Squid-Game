#!/usr/bin/env bash
# On the VM (as root, in /opt/arena): fetch the key from Secret Manager, pull the image, (re)start the containers.
set -euo pipefail
cd /opt/arena
source ./deploy.env                      # IMAGE BUCKET CORS SITE_HOST REGION (written by deploy.sh)
mkdir -p data/runs data/export caddy
umask 077
printf 'OLLAMA_API_KEY=%s\n' "$(gcloud secrets versions access latest --secret ollama-api-key)" > .env
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet >/dev/null 2>&1
export IMAGE BUCKET CORS SITE_HOST
docker compose pull app
docker compose up -d --remove-orphans
docker image prune -f >/dev/null
