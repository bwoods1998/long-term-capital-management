#!/bin/bash
PY=/home/bwoods1998/Work/long-term-capital-management/.venv/bin/python
cd /home/bwoods1998/Work/.ltcm-main/goal-2026-10-19/evl10/check1
for p in shift sparse calm r2sparse; do
  $PY fp_check1.py $p 4 > fp_check1.$p.log 2>&1
done
echo done > chain.done
