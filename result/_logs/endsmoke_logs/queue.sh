#!/bin/zsh
# usage: queue.sh <tag>   (tag = gptoss120b | gemma4) -- runs the four END-smoke arms in sequence
cd "$(dirname "$0")/../.."
tag="$1"
for arm in points_main points_mate tokens_main tokens_mate; do
  cfg="configs/experiment/team_wallet_charge_endsmoke_${arm}_${tag}.yaml"
  echo "=== $(date '+%H:%M:%S') START $cfg" 
  PYTHONPATH=game:web:db .venv/bin/python -m squid_game.runner --config "$cfg"
  echo "=== $(date '+%H:%M:%S') END $cfg rc=$?"
done
echo "=== $(date '+%H:%M:%S') QUEUE DONE $tag"
