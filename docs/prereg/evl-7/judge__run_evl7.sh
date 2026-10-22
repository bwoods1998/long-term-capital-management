#!/bin/bash
# The judge's re-calibration of PREREG-EVL-7's learners under PREREG-EVL-6's draft screen (synthetic only; 4 workers).
# Seeds and chunks follow evl7/learner/run_final.sh, so each cell's paths are the ones its L12 / E840 figures used.
cd "$(dirname "$0")"
PY=/home/bwoods1998/Work/long-term-capital-management/.venv/bin/python
run() { echo "=== $1 R=$2 chunk=$3 $(date -u +%H:%M:%SZ)"; nice -n 5 $PY calib_evl7.py run --grid "$1" --reps "$2" --chunk "$3" --workers 4 > "calib_evl7.$1.log" 2>&1 || echo "FAILED $1"; }
run null 2000 100
run life 600 50
run power 600 50
run null800 1000 50
run d57 600 50
$PY calib_evl7.py report > calib_evl7.report.txt 2>&1
echo "=== done $(date -u +%H:%M:%SZ)"
