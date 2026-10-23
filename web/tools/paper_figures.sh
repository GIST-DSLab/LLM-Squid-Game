#!/usr/bin/env bash
# The paper's rule figures for the arena's rules window: the CogSci 2027 Korean TikZ sources (paper/ submodule of the
# main checkout) rendered one by one with the paper's macros, then written as PNG into web/frontend/assets/paper/.
#   bash web/tools/paper_figures.sh [paper dir]
# Needs xelatex (kotex, UnBatang / UnDotum) and pdftocairo (poppler).
set -euo pipefail
PAPER="${1:-$HOME/Library/Mobile Documents/com~apple~CloudDocs/Workspace/LLM-Squid-Game-DS-Lab/paper}"
OUT="$(cd "$(dirname "$0")/../frontend/assets/paper" && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
for f in arena_round arena_information signal_game; do
  cat > "$WORK/$f.tex" <<EOF
\documentclass[border=6pt]{standalone}
\usepackage[T1]{fontenc}
\usepackage{newtxtext,newtxmath}
\usepackage{xcolor,graphicx,amsmath,ifthen}
\usepackage{kotex}
\setmainhangulfont[Extension=.ttf,BoldFont=UnBatangBold]{UnBatang}
\setsanshangulfont[Extension=.ttf,BoldFont=UnDotumBold]{UnDotum}
\setmonohangulfont[Extension=.ttf,BoldFont=UnDotumBold]{UnDotum}
\makeatletter\def\input@path{{$PAPER/}}\makeatother
\input{cogsci2027/macros}
\begin{document}
\input{cogsci2027/ko/figures/$f}
\end{document}
EOF
  (cd "$WORK" && xelatex -interaction=nonstopmode -halt-on-error "$f.tex" > "$f.log")
  pdftocairo -png -r 200 -singlefile "$WORK/$f.pdf" "$OUT/$f"
  echo "$OUT/$f.png"
done
