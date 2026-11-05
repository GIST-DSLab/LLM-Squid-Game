#!/bin/bash
# one round: reviewer turn on the previous design, then measure the new design (and its hold arm if it has one)
# usage: step.sh <k> <fable|astra> <prev version>
cd "$(dirname "$0")"
python3 turn.py "$1" "$2" "$3" > "turn$1.log" 2>&1 || { echo "TURN FAILED"; tail -5 "turn$1.log"; exit 1; }
cat "turn$1.log"
python3 check.py "designs/d$1.json" > "checks_d$1.log" 2>&1 || { echo "CHECK FAILED"; tail -5 "checks_d$1.log"; exit 1; }
if grep -q '"control_arm"' "designs/d$1.json"; then
  python3 check.py "designs/d$1.json" --arm hold > "checks_d$1_hold.log" 2>&1 || echo "HOLD CHECK FAILED"
fi
sed -n '/# Measured/,$p' "checks_d$1.log" | grep -v "^- cues" | cut -c1-400
echo "=== HOLD ARM ==="; sed -n '/# Measured/,$p' "checks_d$1_hold.log" 2>/dev/null | grep -v "^- cues" | cut -c1-300
echo "ROUND DONE"
