#!/bin/sh
cd "/Users/bagjuhyeon/Library/Mobile Documents/com~apple~CloudDocs/Workspace/LLM-Squid-Game-DS-Lab"
while pgrep -f "signal_effort_pilot_a_gemma4.yaml" >/dev/null; do sleep 15; done
PYTHONPATH=game:web:db uv run --no-sync squid-game --config configs/experiment/signal_effort_pilot_a_gptoss120b.yaml > outputs/_sdi_logs/signal_effort_pilot_a_gptoss120b.log 2>&1
echo "EXIT $?" >> outputs/_sdi_logs/signal_effort_pilot_a_gptoss120b.log
echo DONE > outputs/_sdi_logs/key1_chain.done
