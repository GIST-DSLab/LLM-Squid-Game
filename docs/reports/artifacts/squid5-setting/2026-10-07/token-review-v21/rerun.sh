#!/usr/bin/env bash
# v21 token review: rebuild work.html and the data JSONs from ~/squid5-runs/e52_v21 (finished games only).
# Stops before the label-dependent steps if any free-text SAY/LEAVE utterance has no reading label yet;
# labels are never guessed. After labelling (label_batches/labelsN.json), run this script again.
# It never touches ../e52.html; to copy the section there afterwards: python3 splice.py
set -euo pipefail
cd "$(dirname "$0")"
PY=${PY:-python3}
export PYTHONDONTWRITEBYTECODE=1

echo '[1/6] build.py: ledger, performance, persistence, transfers -> data.json, work.html'
$PY build.py | $PY -c 'import json,sys; d=json.load(sys.stdin); print("  games", d["games"], d["per_model"], "unfinished", d["unfinished"])'
echo '[2/6] extract_semantic_transfers.py: utterances linked to executed transfers -> semantic-evidence.json'
$PY extract_semantic_transfers.py

echo '[3/6] labels: which free-text utterances still need a reading label'
set +e
$PY make_label_batches.py
status=$?
set -e
if [ "$status" -ne 0 ]; then
  echo 'Stopped: label the batch file(s) above (read each utterance in its chat context, rules in README.md),'
  echo 'save label_batches/labelsN.json, then run ./rerun.sh again. work.html now holds only steps 1-2.'
  exit "$status"
fi
$PY assemble_labels.py

echo '[4/6] build_semantic_transfers.py: 03-A/03-B groups -> origin-data.json'
$PY build_semantic_transfers.py > /dev/null
echo '[5/6] build_survival_relation.py: 04-A/B -> survival-data.json'
$PY build_survival_relation.py > /dev/null
echo '[6/6] build_solver_budget.py: 04-C -> solver-budget-data.json'
$PY build_solver_budget.py > /dev/null
echo 'done: work.html has the finished section. Copy it into e52.html with: python3 splice.py'
