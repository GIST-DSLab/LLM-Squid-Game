#!/bin/zsh
# tokctl 10-20: three waves (b0, tl, t4), one config per model in parallel, 2 games each (seeds 4101, 4102)
cd ~/wt/squid5-tokctl
for v in b0 tl t4; do
  for m in glm ds gemma; do
    PYTHONPATH=. ~/.venvs/squid-game/bin/python -m squid5 run configs/squid5/e52tc_${v}_${m}.yaml > ~/squid5-runs/e52_tokctl/run_${v}_${m}.log 2>&1 &
  done
  wait
  echo "wave $v done $(date)"
done
# wave 4 (10-21): DeepSeek TALK at none alone; both changes for the three models
for c in tln_ds tlt4_glm tlt4_ds tlt4_gemma; do
  PYTHONPATH=. ~/.venvs/squid-game/bin/python -m squid5 run configs/squid5/e52tc_${c}.yaml > ~/squid5-runs/e52_tokctl/run_${c}.log 2>&1 &
done
wait
echo "wave 4 done $(date)"
