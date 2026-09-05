#!/bin/zsh
# Run the SDI 22-cell design for several models one after another, each through sdi_driver.sh
# (quota-aware online run) and its tail (resample -> probe -> HTML). A model starts only after the
# previous pipeline has written "PIPELINE DONE <tag>" -- Ollama Cloud quota is shared, so running two
# models at once only makes both wait.
#
# Usage: scripts/run/sdi_chain.sh [<wait_tag>] <tag>=<config>:<label> [<tag>=<config>:<label> ...]
#   <wait_tag>: an optional tag whose pipeline must finish first (e.g. gptossgrid), given as WAIT=<tag>
# Logs: outputs/_sdi_logs/chain.log
set -u
REPO="$(cd "$(dirname "$0")/../.." && pwd)"; cd "$REPO" || exit 1
LOGS="$REPO/outputs/_sdi_logs"; mkdir -p "$LOGS"
log() { echo "[$(date +%m-%d\ %H:%M)] $*" | tee -a "$LOGS/chain.log"; }
wait_done() { while ! grep -q "PIPELINE DONE $1" "$LOGS/pipeline_$1.log" 2>/dev/null; do sleep 300; done; }
if [[ "${1:-}" == WAIT=* ]]; then
  for w in ${(s:,:)${1#WAIT=}}; do log "waiting for pipeline $w"; wait_done "$w"; log "$w done"; done; shift
fi
for spec in "$@"; do
  tag=${spec%%=*}
  log "starting driver for $tag"
  "$REPO/scripts/run/sdi_driver.sh" "$spec" >> "$LOGS/driver_$tag.out" 2>&1
  log "driver for $tag exited; waiting for its pipeline"
  wait_done "$tag"
  log "pipeline $tag done"
done
log "CHAIN DONE"
