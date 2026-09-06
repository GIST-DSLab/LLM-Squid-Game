#!/bin/zsh
# SDI post-processing for one finished model run:
#   resample the recorded decision call (retrying across Ollama quota windows until every
#   replayable turn is ledgered) -> SBERT linear probe -> ELI5 HTML report.
#
# Usage:  scripts/run/sdi_pipeline_tail.sh <tag> "<model label>"  [n_resample] [run_dir]
#   run_dir defaults to the newest outputs/survival_drive_signal_<tag>/*/; pass it explicitly for outputs/benchmark_* runs
#   <tag>   = suffix of outputs/survival_drive_signal_<tag>/ (gptoss | glm53 | gemma4 | deepseekv4pro)
# Logs:    outputs/_sdi_logs/{resample,probe,report}_<tag>*.log
# Needs:   OLLAMA_API_KEY in .env (or exported), ~/.venvs/squid-game for sentence-transformers.
set -u
TAG="$1"; LABEL="$2"; N="${3:-10}"; RUN_ARG="${4:-}"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
LOGS="$REPO/outputs/_sdi_logs"; mkdir -p "$LOGS"
cd "$REPO" || exit 1
K1=${OLLAMA_API_KEY:-$(grep '^OLLAMA_API_KEY=' .env | cut -d= -f2 | awk '{print $1}')}
export OLLAMA_API_KEY="$K1"
export PYTHONPATH="$REPO/game:$REPO/db:$REPO/web"
if [ -n "$RUN_ARG" ]; then RUN="$RUN_ARG"; else RUN=$(ls -td "$REPO/outputs/survival_drive_signal_${TAG}"/*/ | head -1); RUN=${RUN%/}; fi
ROOT=$(dirname "$RUN")
log() { echo "[$(date +%H:%M)] $TAG: $*"; }
probe() { curl -s -o /dev/null -w "%{http_code}" -m 60 -H "Authorization: Bearer $K1" -H "Content-Type: application/json" \
  https://ollama.com/api/chat -d '{"model":"gpt-oss:20b","messages":[{"role":"user","content":"OK"}],"stream":false,"options":{"num_predict":4}}'; }

target=$(uv run python -m scripts.analysis.resample_survival_drive "$RUN" --dry-run 2>/dev/null | grep -o '^[0-9]* replayable' | awk '{print $1}')
log "run=$RUN replayable=$target"
attempt=0
while true; do
  attempt=$((attempt+1))
  code=$(probe)
  if [ "$code" != "200" ]; then log "key -> $code; waiting 15 min"; sleep 900; continue; fi
  uv run python -m scripts.analysis.resample_survival_drive "$RUN" --n "$N" --workers "${WORKERS:-3}" > "$LOGS/resample_${TAG}_$attempt.log" 2>&1
  done_n=$(wc -l < "$RUN/survival_drive/resamples.jsonl" 2>/dev/null | tr -d ' ')
  log "resample attempt $attempt: ledgered ${done_n:-0}/$target"
  [ "${done_n:-0}" -ge "$target" ] && break
  sleep 600
done

log "probe"
mkdir -p "results/survival_drive_probe/${TAG}"
~/.venvs/squid-game/bin/python -m scripts.analysis.probe_reasoning_embeddings \
  --target sdi --channel forfeit --channel task --channel forfeit_task --channel confidence \
  --sdi-table "$RUN/survival_drive/sdi_turns.csv" --root "$ROOT" \
  --out "results/survival_drive_probe/${TAG}" --no-per-model > "$LOGS/probe_${TAG}.log" 2>&1
log "probe exit=$?"
uv run python -m scripts.analysis.report_survival_drive "$RUN" --model-label "$LABEL" \
  --probe-dir "results/survival_drive_probe/${TAG}" --out "weekly-report/0910/sdi_${TAG}.html" > "$LOGS/report_${TAG}.log" 2>&1
log "report exit=$? -> weekly-report/0910/sdi_${TAG}.html"
echo "PIPELINE DONE $TAG"
