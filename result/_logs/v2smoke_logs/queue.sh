#!/bin/zsh
# usage: queue.sh <inheritance>   (main | mate) -- runs the tokens-arm v2 smoke for BOTH leader
# models at once: gpt-oss leader (KEY1) + gemma4 mates (KEY3), and gemma4 leader (KEY3) + gpt-oss
# mates (KEY1). Each run has parallel_workers 5, so each key carries ~10 concurrent calls.
cd "$(dirname "$0")/../.."
inh="$1"
for tag in gptoss120b gemma4; do
  cfg="configs/experiment/team_wallet_v2_tokens_${inh}_${tag}.yaml"
  log="outputs/_v2smoke_logs/${inh}_${tag}.log"
  echo "=== $(date '+%H:%M:%S') START $cfg" | tee -a "$log"
  ( PYTHONPATH=game:web:db .venv/bin/python -m squid_game.runner --config "$cfg" >> "$log" 2>&1; echo "=== $(date '+%H:%M:%S') END $cfg rc=$?" >> "$log" ) &
done
wait
echo "=== $(date '+%H:%M:%S') QUEUE DONE $inh"
