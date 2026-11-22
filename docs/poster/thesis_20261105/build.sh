#!/usr/bin/env bash
# Builds poster/poster.tex into poster/dist/poster-MMDD.pdf (32 x 48 in; MMDD = build date).
#
# 1. The two TikZ arena figures (figures/cogsci_arena_round.tex, cogsci_signal_game.tex)
#    are rendered with pdfLaTeX + cjk-ko through figs/standalone_fig.tex, because the
#    poster itself runs under XeLaTeX with system fonts and the figures were drawn for
#    the pdfLaTeX thesis build.
# 2. The poster runs under XeLaTeX (fontspec: Apple SD Gothic Neo + Chakra Petch).
#
# ./build.sh            -> dist/poster-MMDD.pdf
# ./build.sh tracksuit  -> dist/poster-tracksuit-MMDD.pdf (robots drawn as tracksuit contestants,
#                          sprites and scene sources in figs/tracksuit/)
set -euo pipefail
VARIANT="${1:-}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD="$ROOT/build"
DIST="$ROOT/dist"
mkdir -p "$BUILD" "$DIST"

cd "$ROOT/figs"
# Both figures are rendered at thesis scale (no font rescaling).
# The poster uses the dark variants (_dark: white and black swapped for the dark background).
for fig in cogsci_arena_round cogsci_signal_game; do
  pdflatex -interaction=nonstopmode -output-directory="$BUILD" -jobname="${fig}_dark" \
    "\def\sgdark{}\def\sgfig{$fig}\input{standalone_fig.tex}" >/dev/null
done
# Regenerate data figures from the containing paper repository; fail if unavailable.
"$HOME/.venvs/squid-game/bin/python" "$ROOT/figs/poster_figures.py" --paper "$ROOT/../.."
"$HOME/.venvs/squid-game/bin/python" "$ROOT/figs/poster_exit_reasons.py"
"$HOME/.venvs/squid-game/bin/python" "$ROOT/figs/poster_board.py"

JOB=poster
SRC=poster.tex
if [ "$VARIANT" = tracksuit ]; then
  # Tracksuit scenes: 02 arena (dark) and 06 quotes under pdfLaTeX, from figs/tracksuit.
  cd "$ROOT/figs/tracksuit"
  mkdir -p build
  pdflatex -interaction=nonstopmode -output-directory=build -jobname=arena_tracksuit_dark \
    "\def\sgdark{}\def\sgfigdir{}\def\sgfig{arena_round_tracksuit}\input{standalone_tracksuit.tex}" >/dev/null
  pdflatex -interaction=nonstopmode -output-directory=build quotes_tracksuit.tex >/dev/null
  JOB=poster-tracksuit
  SRC='\def\sgtracksuit{}\input{poster.tex}'
elif [ -n "$VARIANT" ]; then
  echo "unknown variant: $VARIANT (use: tracksuit)" >&2; exit 1
fi

cd "$ROOT"
xelatex -interaction=nonstopmode -output-directory="$BUILD" -jobname="$JOB" "$SRC" >/dev/null || {
  grep -E "^!" -A3 "$BUILD/$JOB.log" | head -40; exit 1; }
xelatex -interaction=nonstopmode -output-directory="$BUILD" -jobname="$JOB" "$SRC" >/dev/null

# 비교하기 쉽게 빌드한 날짜(MMDD)를 이름에 붙인다. 같은 날 다시 빌드하면 그날 파일을 덮어쓴다.
OUT="$DIST/$JOB-$(date +%m%d).pdf"
cp "$BUILD/$JOB.pdf" "$OUT"
echo "poster/dist/$(basename "$OUT")  pages=$(pdfinfo "$OUT" | awk '/^Pages/{print $2}')  $(pdfinfo "$OUT" | grep 'Page size')"
awk 'BEGIN {n=0} tolower($0) ~ /overfull/ {n++} END {print "overfull boxes: " n}' "$BUILD/$JOB.log"
