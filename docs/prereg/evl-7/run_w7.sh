#!/bin/bash
# PREREG-EVL-7's final calibration (calib_w7.py; synthetic only; 8 workers, nice). Stage A on SEARCH seeds; stage B
# (the worst cells on FRESH seeds) is launched by run_w7b.sh with the cells stage A names (select_w7.py).
cd "$(dirname "$0")"
PY=/home/bwoods1998/Work/long-term-capital-management/.venv/bin/python
run() { echo "=== $1 R=$2 chunk=$3 $(date -u +%H:%M:%SZ)"; nice -n 5 $PY calib_w7.py run --grid "$1" --reps "$2" --chunk "$3" --workers 8 ${4:+--tag $4} > "w7.${4:-$1}.log" 2>&1 || echo "FAILED $1"; }
run search 1000 50
echo "=== done $(date -u +%H:%M:%SZ)"
# 12:52Z: the machine became shared with another workflow's 8 workers (8 physical cores); the search was stopped after
# its first 20 cells (grid order 0-19, complete at 1,000 programs) and resumed for every other cell at 500 programs (the same seeds a
# full run draws for chunks 0-9; calib_w7.py --resume keeps every job already written).
run_resume() { echo "=== $1 R=$2 chunk=$3 resume $(date -u +%H:%M:%SZ)"; $PY calib_w7.py run --grid "$1" --reps "$2" --chunk "$3" --workers 8 --resume >> "w7.$1.log" 2>&1 || echo "FAILED $1"; }
