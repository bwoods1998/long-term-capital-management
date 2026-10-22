#!/bin/bash
# The FINAL design's calibration (PREREG-EVL-7 part L: rank by the predicted after-cost return, LAMBDA 8,000, KAPPA 0,
# H 40, K 8, V1 level, warm-up 2,000 rows / 3 sessions). Synthetic only; at most 4 workers.
cd "$(dirname "$0")"
PY=/home/bwoods1998/Work/long-term-capital-management/.venv/bin/python
export LEARNER_FINAL='{"rank": "a", "lam": 8000.0, "kappa": 0.0}'
run() { echo "=== $1 R=$2 $(date -u +%H:%M:%SZ)"; $PY calib_learner.py run --grid "$1" --reps "$2" --chunk "$3" --workers 4 --seed "$4" > "calib_learner.$1.log" 2>&1 || echo "FAILED $1"; }
run final_null 2000 100 81000001
run final_power 600 50 82000001
run final_null800 1000 50 83000001
run final_stress 1000 100 84000001
run final_life 600 50 85000001
echo "=== done $(date -u +%H:%M:%SZ)"
