#!/bin/bash
# NOTE: this chain stopped after the base grid (its shell was reaped); run_rest.sh, then brk2 / worst2 / worst3 by hand (rt_warm.py run --grid G --reps R --chunk 50), produced the rest.
# rt_warm.py grids, seeds inside rt_warm.py (SEEDS); 4 workers at most.
cd "$(dirname "$0")"
PY=/home/bwoods1998/Work/long-term-capital-management/.venv/bin/python
for g in base brk sel beta power; do
  gg=$g; [ $g = brk ] && gg=break
  $PY rt_warm.py run --grid $gg --reps 400 --chunk 50 --workers 4 --out rt_warm.$gg.jsonl > rt_warm.$gg.log 2>&1
done
echo done > run_all.done
