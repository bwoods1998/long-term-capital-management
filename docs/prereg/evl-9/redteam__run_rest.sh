#!/bin/bash
# The remaining rt_warm.py grids (seeds in rt_warm.py SEEDS), 3 workers; rt_skew.py runs beside on 1 (4 in all).
cd "$(dirname "$0")"
PY=/home/bwoods1998/Work/long-term-capital-management/.venv/bin/python
for g in break sel worst beta power; do
  r=400; [ $g = beta ] && r=300; [ $g = power ] && r=300
  $PY rt_warm.py run --grid $g --reps $r --chunk 50 --workers 3 --out rt_warm.$g.jsonl > rt_warm.$g.log 2>&1
done
echo done > run_rest.done
