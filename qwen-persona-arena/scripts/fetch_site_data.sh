#!/usr/bin/env bash
# Site data for persona_arena.library (search / show / controls). Not committed: ~29 MB and the site updates it.
# personas.yaml already pins its neurons, so the server and probe run without it.
#   bash scripts/fetch_site_data.sh
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)/data/qwen-neurons"
mkdir -p "$DIR"
for f in library atlas combos combos3 summary; do
  curl -fsSL "https://neuronpersonas.com/data/qwen/$f.json" -o "$DIR/$f.json"
done
ls -l "$DIR"
