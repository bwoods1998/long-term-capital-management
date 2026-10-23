#!/bin/bash
PY=/home/bwoods1998/Work/long-term-capital-management/.venv/bin/python
cd /home/bwoods1998/Work/.ltcm-main/goal-2026-10-19/evl10/recheck1
for p in surface nulls sens power; do
  $PY fp_recheck1.py $p 3 > fp_recheck1.$p.log 2>&1
done
echo done > chain.done
