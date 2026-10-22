#!/bin/bash
# Replaces the tail of run_all.sh (null800, drift, life on the first design) with the ranking grid; the final design's
# grids follow by hand once the ranking grid has chosen it. Synthetic only, 4 workers.
cd "$(dirname "$0")"
PY=/home/bwoods1998/Work/long-term-capital-management/.venv/bin/python
until grep -q "=== null800" run_all.log; do sleep 5; done
kill 3802866 3800611 2>/dev/null
sleep 1
for p in $(pgrep -f "calib_learner.py run --grid null800"); do kill $p; done
sleep 3
echo "=== rank $(date -u +%H:%M:%SZ)"; $PY calib_learner.py run --grid rank --reps 600 --chunk 50 --workers 4 --seed 78000001 > calib_learner.rank.log 2>&1
echo "=== rank done $(date -u +%H:%M:%SZ)"
