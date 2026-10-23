#!/bin/bash
PY=/home/bwoods1998/Work/long-term-capital-management/.venv/bin/python
cd /home/bwoods1998/Work/.ltcm-main/goal-2026-10-19/evl10/fix1
for p in starve power; do
  $PY fp_fix1.py $p 3 > fp_fix1.$p.log 2>&1
done
echo done > chain2.done
