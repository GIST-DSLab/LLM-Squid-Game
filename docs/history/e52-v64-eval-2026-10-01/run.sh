#!/bin/zsh
# usage: run.sh astra|fable
D=${0:A:h}; W=~/wt/squid5-e52; who=$1
P="$(cat $D/brief.md)

# 이번 차례
당신은 ${who:u} 검토자다. 저장소 루트는 현재 작업 디렉터리다. 자료를 읽고 형식대로 평가를 써라."
if [[ $who == astra ]]; then
  print -r -- "$P" | codex exec -m gpt-6-astra -c model_reasoning_effort=high -s read-only --skip-git-repo-check -C $W -o $D/astra.md - > $D/astra.log 2>&1
else
  cd $W && print -r -- "$P" | env -u ANTHROPIC_API_KEY claude -p --model claude-fable-5-1 --effort high --output-format text --allowedTools Read,Grep,Glob > $D/fable.md 2> $D/fable.log
fi
echo "exit $?"
