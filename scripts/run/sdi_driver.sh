#!/bin/zsh
# Drive one or more SDI model runs to completion across Ollama Cloud quota windows, then
# hand each finished run to scripts/run/sdi_pipeline_tail.sh (resample -> probe -> HTML).
#
# Usage:  scripts/run/sdi_driver.sh <tag>=<config.yaml>:<label> [<tag>=<config>:<label> ...]
#   the run root is read from each config's output_dir (works for outputs/survival_drive_* and outputs/benchmark_*)
#   e.g.  scripts/run/sdi_driver.sh \
#           gptoss=configs/experiment/survival_drive_signal_gptoss_n10.yaml:"gpt-oss:120b — 5셀×10반복×20턴" \
#           glm53=configs/experiment/survival_drive_signal_glm53_n5.yaml:"glm-5.3 — 5셀×5반복×15턴"
# Loop:   probe key (gpt-oss:20b, 4 tokens) every 15 min -> when 200, start/resume every incomplete
#         run with --resume (or a fresh run when no output dir exists) -> wait until the runs exit
#         (quota hit or finished) -> start the tail for every run that reached its season target.
# Logs:   outputs/_sdi_logs/main_<tag>.log, driver.log
set -u
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
LOGS="$REPO/outputs/_sdi_logs"; mkdir -p "$LOGS"
cd "$REPO" || exit 1
K1=${OLLAMA_API_KEY:-$(grep '^OLLAMA_API_KEY=' .env | cut -d= -f2 | awk '{print $1}')}
export OLLAMA_API_KEY="$K1"
export PYTHONPATH="$REPO/game:$REPO/db:$REPO/web"
typeset -A CFG LABEL TOTAL OUT
for spec in "$@"; do
  tag=${spec%%=*}; rest=${spec#*=}; cfg=${rest%%:*}; label=${rest#*:}
  CFG[$tag]="$cfg"; LABEL[$tag]="$label"
  reps=$(grep '^num_repetitions:' "$cfg" | awk '{print $2}')
  cells=$(grep -c '^- framing:' "$cfg")
  TOTAL[$tag]=$((reps * cells))
  OUT[$tag]=$(grep '^output_dir:' "$cfg" | awk '{print $2}')
  # A config may pin an alternate task ladder directory (e.g. configs/tasks_hard10) with a
  # `# task_config_dir: <dir>` header line; export it so squid-game (and --resume) pick it up.
  tcd=$(grep -m1 '^# task_config_dir:' "$cfg" | awk '{print $3}')
  if [ -n "$tcd" ]; then export SQUID_GAME_TASK_CONFIG_DIR="$REPO/$tcd"; echo "[driver] $tag: SQUID_GAME_TASK_CONFIG_DIR=$SQUID_GAME_TASK_CONFIG_DIR"; fi
done
rundir() { local d; d=$(ls -td "$REPO/${OUT[$1]}"/*/ 2>/dev/null | head -1); echo "${d%/}"; }
seasons_done() { local d; d=$(rundir "$1"); [ -n "$d" ] && wc -l < "$d/season_results.jsonl" 2>/dev/null | tr -d ' ' || echo 0; }
probe() { curl -s -o /dev/null -w "%{http_code}" -m 60 -H "Authorization: Bearer $K1" -H "Content-Type: application/json" \
  https://ollama.com/api/chat -d '{"model":"gpt-oss:20b","messages":[{"role":"user","content":"OK"}],"stream":false,"options":{"num_predict":4}}'; }
log() { echo "[$(date +%H:%M)] $*" | tee -a "$LOGS/driver.log"; }

while true; do
  for t in ${(k)CFG}; do
    if [ "$(seasons_done $t)" -ge "${TOTAL[$t]}" ] && [ ! -f "$LOGS/tail_started_$t" ]; then
      touch "$LOGS/tail_started_$t"
      (nohup "$REPO/scripts/run/sdi_pipeline_tail.sh" "$t" "${LABEL[$t]}" 10 "$(rundir $t)" > "$LOGS/pipeline_$t.log" 2>&1 &)
      log "$t: online complete ($(seasons_done $t)/${TOTAL[$t]}) — tail started"
    fi
  done
  pending=()
  for t in ${(k)CFG}; do [ "$(seasons_done $t)" -lt "${TOTAL[$t]}" ] && pending+=($t); done
  if [ ${#pending[@]} -eq 0 ]; then log "all online runs complete"; break; fi
  code=$(probe); log "key probe -> $code (pending: ${pending[*]})"
  if [ "$code" != "200" ]; then sleep 900; continue; fi
  for t in $pending; do
    d=$(rundir $t)
    if [ -n "$d" ]; then
      (nohup uv run squid-game --config "${CFG[$t]}" --resume "$d" > "$LOGS/main_$t.log" 2>&1 &)
      log "$t: resumed from $(seasons_done $t)/${TOTAL[$t]}"
    else
      (nohup uv run squid-game --config "${CFG[$t]}" > "$LOGS/main_$t.log" 2>&1 &)
      log "$t: started fresh"
    fi
    sleep 3
  done
  sleep 120
  # wait only for THIS driver's runs (another driver may be running a different config concurrently)
  mine() { local c=0; for t in ${(k)CFG}; do c=$((c + $(ps aux | grep "[s]quid-game --config ${CFG[$t]}" | grep -c python))); done; echo $c; }
  while [ "$(mine)" -gt 0 ]; do sleep 120; done
  log "runs exited: $(for t in ${(k)CFG}; do printf '%s=%s ' $t $(seasons_done $t); done)"
  sleep 60
done
log "DRIVER DONE"
