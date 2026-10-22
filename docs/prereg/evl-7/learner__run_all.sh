#!/bin/bash
# The learner lens's calibration runs, in order (synthetic only; at most 4 workers: the machine is shared).
# Outputs: calib_learner.<grid>.jsonl and .log beside this file.
cd "$(dirname "$0")"
PY=/home/bwoods1998/Work/long-term-capital-management/.venv/bin/python
run() { echo "=== $1 R=$2 $(date -u +%H:%M:%SZ)"; $PY calib_learner.py run --grid "$1" --reps "$2" --chunk "$3" --workers 4 --seed "$4" > "calib_learner.$1.log" 2>&1 || exit 1; }
# (null ran first by hand: --grid null --reps 2000 --chunk 100 --seed 71000001)
# power ran: run power 600 50 72000001
run levels 1000 100 73000001
run stress 1000 100 74000001
run null800 1000 50 75000001
run drift 400 50 76000001
run life 600 50 77000001
echo "=== done $(date -u +%H:%M:%SZ)"
