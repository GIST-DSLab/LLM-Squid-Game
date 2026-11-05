#!/bin/sh
cd "/Users/bagjuhyeon/Library/Mobile Documents/com~apple~CloudDocs/Workspace/LLM-Squid-Game-DS-Lab"
# wait for the first gpt-oss pilot to finish before taking the key's concurrency
while pgrep -f "survival_prompt_threat_pilot_gptoss120b.yaml" >/dev/null; do sleep 10; done
for n in ownprize_gptoss120b none_gptoss120b gemma4 glm53flash; do
  PYTHONPATH=game:web:db uv run --no-sync squid-game --config configs/experiment/survival_prompt_threat_pilot_$n.yaml > outputs/_sdi_logs/survival_prompt_threat_pilot_$n.log 2>&1
  echo "EXIT $?" >> outputs/_sdi_logs/survival_prompt_threat_pilot_$n.log
done
echo CHAIN_DONE > outputs/_sdi_logs/pilot_chain.done
