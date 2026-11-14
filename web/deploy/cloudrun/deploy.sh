#!/usr/bin/env bash
# The web5 arena API on Google Cloud: Cloud Run (one always-on instance), Cloud SQL Postgres (events), Cloud Storage
# (finished run dirs), Secret Manager (keys). Replaces Render (web/deploy/render.yaml). See README.md here.
#
#   PROJECT=<gcp project id> bash web/deploy/cloudrun/deploy.sh setup    # once: APIs, bucket, database, secrets, account
#   PROJECT=<gcp project id> bash web/deploy/cloudrun/deploy.sh deploy   # build the image and (re)deploy the service
#   PROJECT=<gcp project id> bash web/deploy/cloudrun/deploy.sh url      # the service URL (for web/frontend/config.js)
#
# Run from the repo root. Keys are read from the environment only (OLLAMA_API_KEY); nothing is read from .env.
set -euo pipefail
: "${PROJECT:?set PROJECT to the Google Cloud project id}"
REGION="${REGION:-asia-northeast3}"            # Seoul
SERVICE="${SERVICE:-squid5-arena}"
REPO="${REPO:-web5}"                           # Artifact Registry repository
SQL="${SQL:-arena-pg}"                         # Cloud SQL instance
SQL_TIER="${SQL_TIER:-db-f1-micro}"            # smallest shared-core tier
DB="${DB:-arena}"; DB_USER="${DB_USER:-arena}"
BUCKET="${BUCKET:-${PROJECT}-arena-runs}"
SA="${SERVICE}-sa@${PROJECT}.iam.gserviceaccount.com"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${REPO}/${SERVICE}:$(git rev-parse --short HEAD)"
CORS="${CORS:-https://gist-dslab.github.io}"
g() { gcloud --project "$PROJECT" "$@"; }

setup() {
  g services enable run.googleapis.com sqladmin.googleapis.com secretmanager.googleapis.com \
    artifactregistry.googleapis.com cloudbuild.googleapis.com storage.googleapis.com
  g artifacts repositories describe "$REPO" --location "$REGION" >/dev/null 2>&1 ||
    g artifacts repositories create "$REPO" --repository-format docker --location "$REGION"
  # finished run dirs; versioning keeps an overwritten or deleted object recoverable
  g storage buckets describe "gs://$BUCKET" >/dev/null 2>&1 ||
    g storage buckets create "gs://$BUCKET" --location "$REGION" --uniform-bucket-level-access --public-access-prevention
  g storage buckets update "gs://$BUCKET" --versioning
  # the database: daily backups with point-in-time recovery
  g sql instances describe "$SQL" >/dev/null 2>&1 ||
    g sql instances create "$SQL" --database-version POSTGRES_16 --edition ENTERPRISE --tier "$SQL_TIER" \
      --region "$REGION" --storage-size 10 --storage-auto-increase --backup-start-time 18:00 \
      --enable-point-in-time-recovery --retained-backups-count 14
  g sql databases describe "$DB" --instance "$SQL" >/dev/null 2>&1 || g sql databases create "$DB" --instance "$SQL"
  if ! g secrets describe web5-dsn >/dev/null 2>&1; then
    local pw; pw="$(openssl rand -hex 24)"
    g sql users create "$DB_USER" --instance "$SQL" --password "$pw"
    # psycopg reaches the instance through the Cloud Run Unix socket /cloudsql/<connection name>
    printf 'postgresql://%s:%s@/%s?host=/cloudsql/%s:%s:%s' "$DB_USER" "$pw" "$DB" "$PROJECT" "$REGION" "$SQL" |
      g secrets create web5-dsn --data-file=-
  fi
  if ! g secrets describe ollama-api-key >/dev/null 2>&1; then
    : "${OLLAMA_API_KEY:?export OLLAMA_API_KEY (a key made for this site) for the first setup}"
    printf '%s' "$OLLAMA_API_KEY" | g secrets create ollama-api-key --data-file=-
  fi
  # the service's own account: database client, bucket writer, the two secrets
  g iam service-accounts describe "$SA" >/dev/null 2>&1 ||
    g iam service-accounts create "${SERVICE}-sa" --display-name "web5 arena (Cloud Run)"
  g projects add-iam-policy-binding "$PROJECT" --member "serviceAccount:$SA" --role roles/cloudsql.client --condition None >/dev/null
  g storage buckets add-iam-policy-binding "gs://$BUCKET" --member "serviceAccount:$SA" --role roles/storage.objectCreator >/dev/null
  for s in web5-dsn ollama-api-key; do
    g secrets add-iam-policy-binding "$s" --member "serviceAccount:$SA" --role roles/secretmanager.secretAccessor >/dev/null
  done
  echo "setup done: bucket gs://$BUCKET, database $SQL/$DB, service account $SA"
}

deploy() {
  g builds submit --config web/deploy/cloudrun/cloudbuild.yaml --substitutions "_IMAGE=$IMAGE" .
  # One instance, always on, CPU always allocated: rooms live in this process's memory and play in background threads
  # (web/server/app.py rooms, engine.Room thread), so a second instance or a throttled CPU would break running games.
  g run deploy "$SERVICE" --image "$IMAGE" --region "$REGION" --service-account "$SA" \
    --min-instances 1 --max-instances 1 --no-cpu-throttling --cpu 1 --memory 1Gi --timeout 3600 --concurrency 80 \
    --session-affinity --allow-unauthenticated --port 8600 \
    --add-cloudsql-instances "$PROJECT:$REGION:$SQL" \
    --set-secrets "WEB5_DSN=web5-dsn:latest,OLLAMA_API_KEY=ollama-api-key:latest" \
    --set-env-vars "^@^WEB5_GCS_BUCKET=$BUCKET@WEB5_CORS_ORIGINS=$CORS@WEB5_PUBLIC=1@WEB5_MODELS=gpt-oss:120b@WEB5_MAX_MODEL_ROOMS=2@WEB5_ROOMS_PER_IP_HOUR=4@WEB5_DAILY_TOKENS=3000000"
  url
}

url() { g run services describe "$SERVICE" --region "$REGION" --format 'value(status.url)'; }

"${1:-deploy}"
