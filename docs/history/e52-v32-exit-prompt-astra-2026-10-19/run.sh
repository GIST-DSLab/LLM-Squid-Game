#!/bin/zsh
D=${0:A:h}; W=~/wt/squid5-e52
P="$(cat $D/brief.md)

# 이번 차례
당신은 GPT-6 Astra다. 저장소 루트는 현재 작업 디렉터리다. 의견을 정하고, 동의하는 항목만 구현하고, 테스트를 돌리고, astra.md를 써라."
print -r -- "$P" | codex exec -m gpt-6-astra -c model_reasoning_effort=high -s workspace-write --skip-git-repo-check -C $W --add-dir ~/squid5-runs -o $D/astra_final.md - > $D/astra.log 2>&1
echo "exit $?"
