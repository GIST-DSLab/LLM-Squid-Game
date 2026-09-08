#!/usr/bin/env bash
# Score-equivalent pilot driver (2026-09-09).
#
#   scripts/run/run_score_equiv_pilot.sh [model=haiku] [n_replays=10] [date=2026-09-09]
#
# For lives 3 / 2 / 1: run the frozen-state probe config (one decision call +
# one task call per season, 18 seasons), then replay every recorded decision
# call N times. Then score the gates, judge the replies with Sonnet, and score
# the gates again with the judge CSV. Everything is sequential: the
# claude_code provider shares one scratch dir per process, so workers stay 1.
#
# Logs and results go under results/score_equiv_pilot/<model>/ (small text),
# run outputs under outputs/<date>/score_equiv_probe_<model>/lives{3,2,1}/.
set -uo pipefail
cd "$(dirname "$0")/../.."

MODEL="${1:-haiku}"
N="${2:-10}"
DATE="${3:-2026-09-09}"
PY="${SQUID_PY:-python}"
export PYTHONPATH=game:web:db
OUT="results/score_equiv_pilot/${MODEL}"
mkdir -p "$OUT"

RUN_DIRS=()
for k in 3 2 1; do
  cfg="configs/experiment/probe/score_equiv_probe_${MODEL}_lives${k}.yaml"
  echo "== [$(date +%H:%M:%S)] probe lives${k}: $cfg"
  # The claude_code provider can hit transient "credit balance" errors from
  # the proxy; resume the same run directory up to 4 times before giving up.
  rd=""
  for attempt in 1 2 3 4; do
    if [ -z "$rd" ]; then
      $PY -m squid_game.runner --config "$cfg" 2>&1 | tee -a "$OUT/run_lives${k}.log" | tail -3 && ok=1 || ok=0
      rd=$(ls -td "outputs/${DATE}/score_equiv_probe_${MODEL}/lives${k}"/*/ 2>/dev/null | head -1); rd="${rd%/}"
    else
      $PY -m squid_game.runner --config "$cfg" --resume "$rd" 2>&1 | tee -a "$OUT/run_lives${k}.log" | tail -3 && ok=1 || ok=0
    fi
    n_done=$( [ -f "$rd/season_results.jsonl" ] && wc -l < "$rd/season_results.jsonl" || echo 0 )
    echo "   attempt $attempt: ok=$ok seasons=$n_done"
    [ "$n_done" -ge 18 ] && break
    sleep 30
  done
  echo "== [$(date +%H:%M:%S)] resample x${N}: $rd"
  $PY -m scripts.analysis.resample_survival_drive "$rd" --n "$N" --workers 1 2>&1 | tee "$OUT/resample_lives${k}.log" | tail -3
  RUN_DIRS+=("$rd")
done

echo "== [$(date +%H:%M:%S)] gates (no judge)"
$PY -m scripts.analysis.score_equiv_gates "${RUN_DIRS[@]}" --out "$OUT/gates_nojudge" | tail -20

echo "== [$(date +%H:%M:%S)] sonnet judge"
$PY -m scripts.analysis.pilot_judge "${RUN_DIRS[@]}" --out "$OUT/judge.csv" --judge-provider claude_code --judge-model sonnet --continue-sample 60 2>&1 | tee "$OUT/judge.log" | tail -3

echo "== [$(date +%H:%M:%S)] gates (with judge)"
$PY -m scripts.analysis.score_equiv_gates "${RUN_DIRS[@]}" --judge-csv "$OUT/judge.csv" --out "$OUT/gates" | tail -20
printf '%s\n' "${RUN_DIRS[@]}" > "$OUT/run_dirs.txt"
echo "== [$(date +%H:%M:%S)] done"
