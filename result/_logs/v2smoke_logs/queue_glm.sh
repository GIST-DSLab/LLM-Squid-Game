#!/bin/zsh
# glm-5.3-flash leader (KEY2) with gpt-oss mates (KEY1): main and mate runs together.
cd "$(dirname "$0")/../.."
for inh in main mate; do
  cfg="configs/experiment/team_wallet_v2_tokens_${inh}_glm53flash.yaml"
  log="outputs/_v2smoke_logs/${inh}_glm53flash.log"
  echo "=== $(date '+%H:%M:%S') START $cfg" | tee -a "$log"
  ( PYTHONPATH=game:web:db .venv/bin/python -m squid_game.runner --config "$cfg" >> "$log" 2>&1; echo "=== $(date '+%H:%M:%S') END $cfg rc=$?" >> "$log" ) &
done
wait
echo "=== $(date '+%H:%M:%S') GLM DONE"
