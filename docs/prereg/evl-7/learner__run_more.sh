#!/bin/bash
# After run_all.sh: the ranking/hurdle power grid and the final design's null grid (synthetic only, 4 workers).
cd "$(dirname "$0")"
PY=/home/bwoods1998/Work/long-term-capital-management/.venv/bin/python
while kill -0 3800611 2>/dev/null; do sleep 10; done
echo "=== rank $(date -u +%H:%M:%SZ)"; $PY calib_learner.py run --grid rank --reps 600 --chunk 50 --workers 4 --seed 78000001 > calib_learner.rank.log 2>&1
echo "=== ranknull $(date -u +%H:%M:%SZ)"; $PY calib_learner.py run --grid ranknull --reps 2000 --chunk 100 --workers 4 --seed 79000001 > calib_learner.ranknull.log 2>&1
echo "=== done $(date -u +%H:%M:%SZ)"
