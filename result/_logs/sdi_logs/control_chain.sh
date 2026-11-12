#!/bin/sh
cd "/Users/bagjuhyeon/Library/Mobile Documents/com~apple~CloudDocs/Workspace/LLM-Squid-Game-DS-Lab"
for n in none_gptoss120b ownprize_gptoss120b gemma4 gptoss120b glm53flash; do
  PYTHONPATH=game:web:db uv run --no-sync squid-game --config configs/experiment/survival_prompt_control_pilot_$n.yaml > outputs/_sdi_logs/survival_prompt_control_pilot_$n.log 2>&1
  echo "EXIT $?" >> outputs/_sdi_logs/survival_prompt_control_pilot_$n.log
done
echo CHAIN_DONE > outputs/_sdi_logs/control_chain.done
