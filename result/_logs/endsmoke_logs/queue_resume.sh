#!/bin/zsh
# usage: queue_resume.sh <tag> [<tag2> ...] -- resumes the four END-smoke arms of each tag in sequence
cd "$(dirname "$0")/../.."
for tag in "$@"; do
  for arm in points_main points_mate tokens_main tokens_mate; do
    cfg="configs/experiment/team_wallet_charge_endsmoke_${arm}_${tag}.yaml"
    run=$(ls -d outputs/team_wallet_charge_endsmoke_${arm}_${tag}/2026*/ | head -1)
    echo "=== $(date '+%H:%M:%S') START $cfg resume=$run"
    PYTHONPATH=game:web:db .venv/bin/python -m squid_game.runner --config "$cfg" --resume "$run"
    echo "=== $(date '+%H:%M:%S') END $cfg rc=$?"
  done
  echo "=== $(date '+%H:%M:%S') QUEUE DONE $tag"
done
