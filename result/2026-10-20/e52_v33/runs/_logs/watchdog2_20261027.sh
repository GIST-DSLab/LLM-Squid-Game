#!/bin/bash
# watchdog2 <group-name> <process pattern> <events files...>: at the first unit_error in any of the files, stop that group's runs (researcher, 10-27).
name=$1; pat=$2; shift 2
while true; do
  for f in "$@"; do
    if [ -f "$f" ] && grep -q '"unit_error"' "$f"; then
      echo "$(date '+%F %T') [$name] unit_error in $f: $(grep -h '"unit_error"' "$f" | head -1 | cut -c1-400)"
      pkill -f "$pat"
      echo "$(date '+%F %T') [$name] stopped runs matching: $pat"
      exit 0
    fi
  done
  pgrep -f "$pat" >/dev/null || { echo "$(date '+%F %T') [$name] all runs finished without unit_error"; exit 0; }
  sleep 20
done
