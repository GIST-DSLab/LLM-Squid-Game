#!/bin/zsh
# usage: run.sh   (GPT-6 Astra designs the v8 NPC event blocks; read-only on the worktree)
D=${0:A:h}; W=~/wt/squid5-e52
P="$(cat $D/brief.md)

# 이번 차례
당신은 ASTRA 설계 검토자다. 저장소 루트는 현재 작업 디렉터리다. 자료를 읽고 형식대로 써라."
print -r -- "$P" | codex exec -m gpt-6-astra -c model_reasoning_effort=high -s read-only --skip-git-repo-check -C $W -o $D/astra.md - > $D/astra.log 2>&1
echo "exit $?"
