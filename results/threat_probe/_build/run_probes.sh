#!/bin/sh
# usage: run_probes.sh <slug>   (slug = gptoss | glm53flash | glm53)
set -e
cd "/Users/bagjuhyeon/Library/Mobile Documents/com~apple~CloudDocs/Workspace/LLM-Squid-Game-DS-Lab"
SP="/private/tmp/claude-501/-Users-bagjuhyeon-Library-Mobile-Documents-com-apple-CloudDocs-Workspace-LLM-Squid-Game-DS-Lab/4fddd72a-5407-4e25-bddc-f901ea90609c/scratchpad"
SLUG=$1
ROOT=outputs/lives_threat_5x2_$SLUG
RUN=$(ls -d $ROOT/*_signal-game | head -1)
OUT=results/threat_probe/${SLUG}_5x2_n3
mkdir -p "$OUT"
export PYTHONPATH="$PWD:$PWD/game:$PWD/db"
PY=$HOME/.venvs/squid-game/bin/python
$PY "$SP/describe.py" "$RUN" $OUT/descriptives > $OUT/describe.log 2>&1 || echo "describe failed"
$PY "$SP/probe5.py" effort "$RUN" --out $OUT/ladder5/effort > $OUT/effort.log 2>&1 || echo "effort failed"
$PY "$SP/probe5.py" motive --runs "$RUN" --out $OUT/ladder5/motive > $OUT/motive5.log 2>&1 || echo "motive5 failed"
$PY scripts/analysis/probe_threat_motive.py --runs "$RUN" --out $OUT/ladder4/motive > $OUT/motive4.log 2>&1 || echo "motive4 failed"
$PY "$SP/probe5.py" embeddings --root $ROOT --target threat_level --channel task --channel forfeit --out $OUT/ladder5/embeddings > $OUT/emb5.log 2>&1 || echo "emb5 failed"
$PY scripts/analysis/probe_reasoning_embeddings.py --root $ROOT --target threat_level --channel task --channel forfeit --out $OUT/ladder4/embeddings > $OUT/emb4.log 2>&1 || echo "emb4 failed"
echo "probes done for $SLUG -> $OUT"
