#!/bin/bash
# Stop all three v33 top-up runs at the first unit_error (researcher, 10-27).
cd ~/squid5-runs/e52_v33
while true; do
  alive=$(pgrep -f "squid5 run .*e52v33_public" | wc -l | tr -d ' ')
  for m in luna sol astra; do
    f=$(ls squid5_e52v33_public_${m}4/*/events.jsonl)
    if grep -q '"unit_error"' "$f"; then
      echo "$(date '+%F %T') unit_error in $m: $(grep -h '"unit_error"' "$f" | head -1 | cut -c1-400)"
      pkill -f "squid5 run .*e52v33_public"; sleep 2; pkill -f "codex exec --json --ephemeral"
      echo "$(date '+%F %T') stopped all; results: $(for x in luna sol astra; do echo -n "$x=$(wc -l < squid5_e52v33_public_${x}4/*/results.jsonl | tr -d ' ') "; done)"
      exit 0
    fi
  done
  [ "$alive" = "0" ] && { echo "$(date '+%F %T') all runs finished without unit_error"; exit 0; }
  sleep 20
done
