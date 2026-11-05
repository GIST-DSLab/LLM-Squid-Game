#!/bin/bash
# One model: calibration -> gate (solve rate 0.4-0.7) -> 5.1 -> 5.2 pilot (reps 3). Resumes a run once if units failed.
TAG=$1; B=/Users/bagjuhyeon/squid5-runs/main; PY=~/.venvs/squid-game/bin/python; S="$PY $B/squid5env.py"
run() {  # $1 config, $2.. extra args
  local cfg=$1; shift; local name=$($PY -c "import yaml;print(yaml.safe_load(open('$cfg'))['name'])")
  $S run $cfg "$@" || { local d=$(ls -dt $B/$name/*/ | head -1); echo "resume $d"; $S run $cfg --resume $d "$@"; }
}
echo "[$(date +%T)] $TAG calibrate"; run $B/configs/calibrate_$TAG.yaml
$S calibrate $(ls -dt $B/squid5_calibrate_$TAG/*/ | head -1) --out $B/calib_$TAG.json || exit 1
RATE=$($PY -c "import json;t=json.load(open('$B/calib_$TAG.json'));v=list(t.values())[0];print(v['solve_rate']);print('median',v['agent_round_median'],'n',v['n'])" | tee /dev/stderr | head -1)
if ! $PY -c "import sys;sys.exit(0 if 0.4<=$RATE<=0.7 else 1)"; then echo "[$(date +%T)] $TAG GATE FAIL solve_rate=$RATE — stopping"; exit 2; fi
echo "[$(date +%T)] $TAG 5.1"; run $B/configs/motive_$TAG.yaml
echo "[$(date +%T)] $TAG 5.2 pilot"; run $B/configs/game_$TAG.yaml --reps 3
echo "[$(date +%T)] $TAG done"
