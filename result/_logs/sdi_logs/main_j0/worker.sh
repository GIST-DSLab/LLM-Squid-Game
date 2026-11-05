#!/bin/sh
# usage: worker.sh <label> <api-key-value> [pinned-first-slug]
cd "/Users/bagjuhyeon/Library/Mobile Documents/com~apple~CloudDocs/Workspace/LLM-Squid-Game-DS-Lab"
Q=outputs/_sdi_logs/main_j0; LABEL=$1; export OLLAMA_API_KEY="$2"; PIN=$3
run_one() {
  s=$1; echo "$(date +%H:%M:%S) $LABEL start $s" >> $Q/schedule.log
  PYTHONPATH=game:web:db "$HOME/.venvs/squid-game/bin/python" -m squid_game.runner --config configs/experiment/main_j0_$s.yaml > $Q/$s.log 2>&1
  rc=$?; echo "EXIT $rc" >> $Q/$s.log; echo "$(date +%H:%M:%S) $LABEL done $s rc=$rc" >> $Q/schedule.log; touch $Q/$s.done
}
[ -n "$PIN" ] && run_one "$PIN"
while :; do
  # atomic pop via mkdir lock
  until mkdir $Q/.lock 2>/dev/null; do sleep 1; done
  s=$(head -1 $Q/queue.txt); [ -n "$s" ] && sed -i '' '1d' $Q/queue.txt
  rmdir $Q/.lock
  [ -z "$s" ] && break
  run_one "$s"
done
echo "$(date +%H:%M:%S) $LABEL idle" >> $Q/schedule.log
