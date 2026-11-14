#!/usr/bin/env bash
# The web5 arena API on one always-on Compute Engine VM (no cold start): Docker Compose with the app image and Caddy
# (HTTPS), data on the VM's persistent disk (daily snapshots) and finished run dirs copied to a Cloud Storage bucket.
# Replaces Render (web/deploy/render.yaml). See README.md here.
#
#   PROJECT=<id> bash web/deploy/vm/deploy.sh setup    # once: APIs, image repo, bucket, key secret, account, IP, VM
#   PROJECT=<id> bash web/deploy/vm/deploy.sh deploy   # build the image, copy the compose files, (re)start on the VM
#   PROJECT=<id> bash web/deploy/vm/deploy.sh url      # the API address for web/frontend/config.js
#   PROJECT=<id> bash web/deploy/vm/deploy.sh ssh      # a shell on the VM
#
# Run from the repo root. Uses ACCOUNT (default sundonglab@gmail.com) without changing gcloud's active account.
# The first setup reads OLLAMA_API_KEY from the environment (a key made for this site); nothing is read from .env.
set -euo pipefail
: "${PROJECT:?set PROJECT to the Google Cloud project id}"
ACCOUNT="${ACCOUNT:-sundonglab@gmail.com}"
REGION="${REGION:-asia-northeast3}"; ZONE="${ZONE:-asia-northeast3-a}"   # Seoul
VM="${VM:-arena-vm}"; MACHINE="${MACHINE:-e2-small}"                     # 2 shared vCPU, 2 GB
REPO="${REPO:-web5}"; BUCKET="${BUCKET:-${PROJECT}-arena-runs}"
SA="arena-vm-sa@${PROJECT}.iam.gserviceaccount.com"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${REPO}/arena:$(git rev-parse --short HEAD)"
CORS="${CORS:-https://gist-dslab.github.io}"
HERE="$(cd "$(dirname "$0")" && pwd)"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/arena_gce}"   # a passphrase-less key for this deploy only (ssh-keygen -t ed25519 -N "" -f ~/.ssh/arena_gce)
g() { gcloud --account "$ACCOUNT" --project "$PROJECT" "$@"; }
ip() { g compute addresses describe arena-ip --region "$REGION" --format 'value(address)'; }
host() { echo "$(ip | tr . -).sslip.io"; }

setup() {
  g services enable compute.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com \
    storage.googleapis.com secretmanager.googleapis.com
  g artifacts repositories describe "$REPO" --location "$REGION" >/dev/null 2>&1 ||
    g artifacts repositories create "$REPO" --repository-format docker --location "$REGION"
  g storage buckets describe "gs://$BUCKET" >/dev/null 2>&1 ||
    g storage buckets create "gs://$BUCKET" --location "$REGION" --uniform-bucket-level-access --public-access-prevention
  g storage buckets update "gs://$BUCKET" --versioning
  if ! g secrets describe ollama-api-key >/dev/null 2>&1; then
    : "${OLLAMA_API_KEY:?export OLLAMA_API_KEY (a key made for this site) for the first setup}"
    printf '%s' "$OLLAMA_API_KEY" | g secrets create ollama-api-key --replication-policy automatic --data-file=-
  fi
  # the VM's own account: pull the image, write run dirs to the bucket, read the key, write logs
  g iam service-accounts describe "$SA" >/dev/null 2>&1 ||
    g iam service-accounts create arena-vm-sa --display-name "web5 arena VM"
  for role in roles/artifactregistry.reader roles/logging.logWriter; do
    g projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$SA" --role "$role" --condition None >/dev/null
  done
  g storage buckets add-iam-policy-binding "gs://$BUCKET" --member "serviceAccount:$SA" --role roles/storage.objectCreator >/dev/null
  g secrets add-iam-policy-binding ollama-api-key --member "serviceAccount:$SA" --role roles/secretmanager.secretAccessor >/dev/null
  # a fixed address (the HTTPS name is made from it) and HTTP/HTTPS in
  g compute addresses describe arena-ip --region "$REGION" >/dev/null 2>&1 || g compute addresses create arena-ip --region "$REGION"
  g compute firewall-rules describe arena-web >/dev/null 2>&1 ||
    g compute firewall-rules create arena-web --allow tcp:80,tcp:443 --target-tags arena-web
  # daily disk snapshots kept 14 days
  g compute resource-policies describe arena-daily --region "$REGION" >/dev/null 2>&1 ||
    g compute resource-policies create snapshot-schedule arena-daily --region "$REGION" --daily-schedule \
      --start-time 18:00 --max-retention-days 14 --on-source-disk-delete keep-auto-snapshots
  if ! g compute instances describe "$VM" --zone "$ZONE" >/dev/null 2>&1; then
    g compute instances create "$VM" --zone "$ZONE" --machine-type "$MACHINE" --image-family debian-12 \
      --image-project debian-cloud --boot-disk-size 30GB --boot-disk-type pd-balanced --address "$(ip)" \
      --tags arena-web --service-account "$SA" --scopes cloud-platform \
      --metadata-from-file startup-script="$HERE/startup.sh"
    g compute disks add-resource-policies "$VM" --zone "$ZONE" --resource-policies arena-daily
  fi
  echo "setup done: VM $VM ($(ip)), bucket gs://$BUCKET, https://$(host)"
}

deploy() {
  # build once per commit: an image already in the registry for this commit is reused
  g artifacts docker images describe "$IMAGE" >/dev/null 2>&1 ||
    g builds submit --config web/deploy/cloudrun/cloudbuild.yaml --substitutions "_IMAGE=$IMAGE" .
  local tmp; tmp="$(mktemp -d)"
  printf 'IMAGE=%s\nBUCKET=%s\nCORS=%s\nSITE_HOST=%s\nREGION=%s\n' "$IMAGE" "$BUCKET" "$CORS" "$(host)" "$REGION" > "$tmp/deploy.env"
  cp "$HERE/compose.yaml" "$HERE/Caddyfile" "$HERE/up.sh" "$tmp/"
  g compute scp --ssh-key-file "$SSH_KEY" --zone "$ZONE" "$tmp"/* "$VM:/tmp/"
  g compute ssh "$VM" --ssh-key-file "$SSH_KEY" --zone "$ZONE" --command \
    "sudo mkdir -p /opt/arena && sudo mv /tmp/compose.yaml /tmp/Caddyfile /tmp/up.sh /tmp/deploy.env /opt/arena/ && sudo bash /opt/arena/up.sh"
  rm -rf "$tmp"
  url
}

url() { echo "https://$(host)"; }
ssh() { g compute ssh "$VM" --ssh-key-file "$SSH_KEY" --zone "$ZONE"; }

"${1:-deploy}"
