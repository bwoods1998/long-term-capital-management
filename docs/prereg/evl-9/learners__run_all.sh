#!/bin/bash
# PREREG-EVL-9 learners lens: synthetic calibration (4 workers). Seeds are fixed inside calib_evl9.py's grids.
cd "$(dirname "$0")"
PY=/home/bwoods1998/Work/long-term-capital-management/.venv/bin/python
run() { echo "=== $1 R=$2 chunk=$3 $(date -u +%H:%M:%SZ)"; nice -n 5 $PY calib_evl9.py run --grid "$1" --reps "$2" --chunk "$3" --workers 4 > "calib_evl9.$1.log" 2>&1 || echo "FAILED $1"; }
run tune 300 50   # the only grid of this script that ran (05:30-05:49Z); the rest: run_rest3.sh, run_phi.sh
run null 1000 50
run char 1000 50
run power 400 50
run life 300 50
run powerw 400 50
$PY calib_evl9.py report > calib_evl9.report.txt 2>&1
echo "=== done $(date -u +%H:%M:%SZ)"
