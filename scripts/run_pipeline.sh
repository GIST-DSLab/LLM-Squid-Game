#!/bin/bash
# Sequential experiment pipeline with battery guard.
# Monitors current qwen4b run, then auto-starts qwen9b.
#
# Usage: nohup bash scripts/run_pipeline.sh > outputs/pipeline.log 2>&1 &

set -euo pipefail
cd "$(dirname "$0")/.."

BATTERY_MIN=20
CHECK_INTERVAL=60
LOGFILE="outputs/pipeline.log"

# ── helpers ──────────────────────────────────────────────
get_battery() { pmset -g batt | grep -Eo '[0-9]+%' | tr -d '%'; }
is_charging() { pmset -g batt | grep -q 'AC Power'; }

battery_ok() {
    if is_charging; then return 0; fi
    [ "$(get_battery)" -gt "$BATTERY_MIN" ]
}

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# Wait for a PID, checking battery every CHECK_INTERVAL seconds.
# Kills the PID and exits if battery is critical.
wait_with_battery_guard() {
    local pid=$1
    while kill -0 "$pid" 2>/dev/null; do
        sleep "$CHECK_INTERVAL"
        if ! battery_ok; then
            log "⚠️  Battery $(get_battery)% <= ${BATTERY_MIN}%. Stopping PID $pid..."
            kill "$pid" 2>/dev/null; wait "$pid" 2>/dev/null
            log "Pipeline paused due to low battery. Plug in and re-run."
            exit 1
        fi
    done
    wait "$pid" 2>/dev/null
}

# ── Step 1: Wait for current qwen4b resume to finish ────
QWEN4B_PID=$(pgrep -of "resume_experiment.*qwen4b" 2>/dev/null || true)

if [ -n "$QWEN4B_PID" ]; then
    log "═══ Step 1: Qwen 3.5:4b already running (PID $QWEN4B_PID). Monitoring... ═══"
    DONE=$(wc -l < outputs/20260319_2242_qwen3.5-4b_signal-game/season_results.jsonl)
    log "  Current progress: ${DONE}/160"
    wait_with_battery_guard "$QWEN4B_PID"
    DONE=$(wc -l < outputs/20260319_2242_qwen3.5-4b_signal-game/season_results.jsonl)
    log "═══ Qwen 3.5:4b complete (${DONE} seasons). ═══"
else
    DONE=$(wc -l < outputs/20260319_2242_qwen3.5-4b_signal-game/season_results.jsonl 2>/dev/null || echo 0)
    if [ "$DONE" -ge 160 ]; then
        log "═══ Qwen 3.5:4b already done (${DONE}/160). Skipping. ═══"
    else
        log "═══ Step 1: Resuming Qwen 3.5:4b (${DONE}/160)... ═══"
        uv run python scripts/resume_experiment.py \
            configs/experiment/qwen4b_4x2_n20.yaml \
            outputs/20260319_2242_qwen3.5-4b_signal-game &
        wait_with_battery_guard $!
        DONE=$(wc -l < outputs/20260319_2242_qwen3.5-4b_signal-game/season_results.jsonl)
        log "═══ Qwen 3.5:4b complete (${DONE} seasons). ═══"
    fi
fi

# ── Step 2: Run qwen9b ──────────────────────────────────
log ""
log "═══ Step 2: Starting Qwen 3.5:9b (160 runs)... ═══"

if ! battery_ok; then
    log "⚠️  Battery too low to start qwen9b. Plug in and re-run."
    exit 1
fi

# Use resume script so it can be re-run safely if interrupted.
uv run python scripts/resume_experiment.py \
    configs/experiment/qwen9b_4x2_n20.yaml &
wait_with_battery_guard $!

DONE9B=$(ls outputs/*qwen3.5-9b*/season_results.jsonl 2>/dev/null | xargs wc -l 2>/dev/null | tail -1 | awk '{print $1}')
log "═══ Qwen 3.5:9b complete (${DONE9B:-0} seasons). ═══"
log "═══ Pipeline finished! ═══"
