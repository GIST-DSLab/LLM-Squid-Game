#!/usr/bin/env bash
# Run one hz 2x2 config, then resample the SDI cell from the run it just made.
#
#   scripts/run/run_hz2x2_with_resample.sh configs/experiment/hz_2x2_main_gemma4_n10.yaml
#   scripts/run/run_hz2x2_with_resample.sh <config> --dry-run     # validate only
#   RESAMPLE_N=20 scripts/run/run_hz2x2_with_resample.sh <config>
#
# WHY THE RESAMPLE IS FILTERED. `sdi = q / p` is defined only for cell 3
# (hz_1111 x forfeit allowed): `p` comes from the P_THREAT question, which the
# template asks only where the framing states an outcome, and `q` comes from
# replaying a decision call that actually had a FORFEIT option. Cells 1-2
# answer P_LIFE_LOSS -- a different quantity -- and cells 2 and 4 have no exit.
# `--framing hz_1111` plus the resampler's own `forfeit_condition == "allowed"`
# filter leaves exactly cell 3. Without the flag, cell 1 would be replayed too
# and its rows would land in the same shared ledger.
set -euo pipefail

CONFIG="${1:?usage: $0 <config.yaml> [extra squid-game args...]}"
shift || true
RESAMPLE_N="${RESAMPLE_N:-10}"
SDI_FRAMING="${SDI_FRAMING:-hz_1111}"

cd "$(dirname "$0")/../.."
export PYTHONPATH="game:web:db${PYTHONPATH:+:$PYTHONPATH}"

OUT_DIR=$(python3 - "$CONFIG" <<'PY'
import sys, yaml
print(yaml.safe_load(open(sys.argv[1]))["output_dir"])
PY
)

echo "==> main run: $CONFIG  (output_dir: $OUT_DIR)"
uv run --no-sync squid-game --config "$CONFIG" "$@"

# --dry-run validates the config and writes nothing; there is no run to resample.
for arg in "$@"; do
  if [ "$arg" = "--dry-run" ]; then
    echo "==> --dry-run: skipping resample"
    exit 0
  fi
done

RUN=$(ls -1dt "$OUT_DIR"/*/ 2>/dev/null | head -1)
if [ -z "${RUN:-}" ]; then
  echo "!! no run directory under $OUT_DIR -- did the run fail?" >&2
  exit 1
fi
RUN="${RUN%/}"

echo "==> resampling q for $SDI_FRAMING x allowed  (n=$RESAMPLE_N)"
echo "    run: $RUN"
uv run --no-sync python -m scripts.analysis.resample_survival_drive \
  "$RUN" --framing "$SDI_FRAMING" --n "$RESAMPLE_N"

echo "==> done"
echo "    turns   : $RUN/survival_drive/sdi_turns.csv"
echo "    replays : $RUN/survival_drive/resamples.jsonl"
echo "    ⚠️ report coverage: total turns, turns dropped at p = 0, turns left."
