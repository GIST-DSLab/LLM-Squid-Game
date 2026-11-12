#!/bin/sh
cd "/Users/bagjuhyeon/Library/Mobile Documents/com~apple~CloudDocs/Workspace/LLM-Squid-Game-DS-Lab"
export OLLAMA_API_KEY="70ef7d5a573346cabbe29e4c68b76643.YxFQRxlmRbSlpPkqH8VgqmNS"
echo "$(date +%H:%M:%S) KEY1 start gptoss120b_mt131k --resume" >> outputs/_sdi_logs/main_j0/schedule.log
PYTHONPATH=game:web:db "$HOME/.venvs/squid-game/bin/python" -m squid_game.runner --config configs/experiment/main_j0_gptoss120b_mt131k.yaml --resume "outputs/main_j0_gptoss120b_mt131k/20260910_1829_gpt-oss-120b-cloud_signal-game/" > outputs/_sdi_logs/main_j0/gptoss120b_mt131k_resume.log 2>&1
rc=$?; echo "EXIT $rc" >> outputs/_sdi_logs/main_j0/gptoss120b_mt131k_resume.log; echo "$(date +%H:%M:%S) KEY1 done gptoss120b_mt131k_resume rc=$rc" >> outputs/_sdi_logs/main_j0/schedule.log; touch outputs/_sdi_logs/main_j0/gptoss120b_mt131k_resume.done
