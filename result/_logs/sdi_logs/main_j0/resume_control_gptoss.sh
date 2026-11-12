#!/bin/sh
cd "/Users/bagjuhyeon/Library/Mobile Documents/com~apple~CloudDocs/Workspace/LLM-Squid-Game-DS-Lab"
export OLLAMA_API_KEY="70ef7d5a573346cabbe29e4c68b76643.YxFQRxlmRbSlpPkqH8VgqmNS"
echo "$(date +%H:%M:%S) KEY1 start control_gptoss120b_mt131k --resume" >> outputs/_sdi_logs/main_j0/schedule.log
PYTHONPATH=game:web:db "$HOME/.venvs/squid-game/bin/python" -m squid_game.runner --config configs/experiment/main_j0_control_gptoss120b_mt131k.yaml --resume "outputs/main_j0_control_gptoss120b_mt131k/20260911_0307_gpt-oss-120b-cloud_signal-game/" > outputs/_sdi_logs/main_j0/control_gptoss120b_mt131k_resume2.log 2>&1
rc=$?; echo "EXIT $rc" >> outputs/_sdi_logs/main_j0/control_gptoss120b_mt131k_resume2.log; echo "$(date +%H:%M:%S) KEY1 done control_gptoss120b_mt131k_resume2 rc=$rc" >> outputs/_sdi_logs/main_j0/schedule.log; touch outputs/_sdi_logs/main_j0/control_gptoss120b_mt131k_resume2.done
