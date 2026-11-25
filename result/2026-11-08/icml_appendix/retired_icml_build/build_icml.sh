#!/usr/bin/env bash
# Build the CogSci body plus the ICML appendix without touching the original sources.
#   bash icml2027/build_icml.sh          # review copy (body + ICML appendix) and full copy
# main_icml.tex is regenerated from ../main.tex each time, replacing only the content \input.
# Output: icml2027/dist/ko_icml_{review,full}_<DATE>.pdf
set -euo pipefail
cd "$(dirname "$0")/.."
DATE="$(date +%F)"
mkdir -p icml2027/build icml2027/dist
# The universal TeX Live biber fails to self-extract its arm64 slice here; use a thinned copy.
BIBER=icml2027/build/biber_arm64
[ -x "$BIBER" ] || lipo -thin arm64 "$(readlink -f "$(command -v biber)")" -output "$BIBER"
# The ICML appendix cites extra works from its own bib file, so ../references.bib stays as the original paper has it.
sed -e 's#\\input{cogsci2027/\\paperLang/content}#\\input{icml2027/\\paperLang/content_icml}#' \
    -e 's#^\(  \\addbibresource{references.bib}\)$#\1\n  \\addbibresource{icml2027/references_icml.bib}#' main.tex > icml2027/main_icml.tex
grep -q 'icml2027/\\paperLang/content_icml' icml2027/main_icml.tex
grep -q 'icml2027/references_icml.bib' icml2027/main_icml.tex
for kind in review full; do
  flag=false; [ "$kind" = full ] && flag=true
  job="ko_icml_${kind}"
  latexmk -e "\$biber='$BIBER %O %S'" -xelatex -interaction=nonstopmode -halt-on-error -outdir=icml2027/build -jobname="$job" \
    -usepretex="\\def\\paperVenue{cogsci}\\def\\paperLang{ko}\\newif\\ificmlFull\\icmlFull$flag" icml2027/main_icml.tex >/dev/null
  cp "icml2027/build/$job.pdf" "icml2027/dist/${job}_${DATE}.pdf"
  echo "built icml2027/dist/${job}_${DATE}.pdf"
done
