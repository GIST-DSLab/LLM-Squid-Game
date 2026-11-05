#!/bin/zsh
# wait for glm/gemma (KEY3) to finish, then run gpt-oss both arms on KEY3 with the free slots
D=~/squid5-runs/e51_v10_refill_20260930
cd "/Users/bagjuhyeon/Library/Mobile Documents/com~apple~CloudDocs/Workspace/LLM-Squid-Game-DS-Lab"
while pgrep -f "run_ollama.py other 20 OLLAMA_API_KEY3 glm" >/dev/null; do sleep 20; done
python3 $D/run_ollama.py other 20 OLLAMA_API_KEY3 gpt-oss:120b > $D/run_ollama_k3_gptoss.log 2>&1
python3 $D/run_ollama.py self 20 OLLAMA_API_KEY3 gpt-oss:120b > $D/run_ollama_self.log 2>&1
echo chain-done >> $D/run_ollama_self.log
