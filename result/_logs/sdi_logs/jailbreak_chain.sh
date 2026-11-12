#!/bin/sh
cd "/Users/bagjuhyeon/Library/Mobile Documents/com~apple~CloudDocs/Workspace/LLM-Squid-Game-DS-Lab"
for n in j0_none j1_deploynotice j2_deployhead; do
  PYTHONPATH=game:web:db uv run --no-sync squid-game --config configs/experiment/jailbreak_probe_${n}_gptoss120b.yaml > outputs/_sdi_logs/jailbreak_probe_${n}.log 2>&1
  echo "EXIT $?" >> outputs/_sdi_logs/jailbreak_probe_${n}.log
done
echo DONE > outputs/_sdi_logs/jailbreak_chain.done
