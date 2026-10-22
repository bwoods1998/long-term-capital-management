#!/bin/bash
# PREREG-EVL-9 learners lens: synthetic calibration of the final design (N_EQ 25k, H 40, K 8; 4 workers).
cd "$(dirname "$0")"
PY=/home/bwoods1998/Work/long-term-capital-management/.venv/bin/python
run() { echo "=== $1 R=$2 chunk=$3 $(date -u +%H:%M:%SZ)"; nice -n 5 $PY calib_evl9.py run --grid "$1" --reps "$2" --chunk "$3" --workers 4 > "calib_evl9.$1.log" 2>&1 || echo "FAILED $1"; }
run null 800 50
run char 600 50
run power 200 50
run powerw 200 50
run tune2 200 50
run null2 300 50
run life 200 50
$PY calib_evl9.py report > calib_evl9.report.txt 2>&1
echo "=== done $(date -u +%H:%M:%SZ)"
