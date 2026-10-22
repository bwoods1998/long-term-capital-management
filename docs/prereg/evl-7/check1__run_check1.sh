#!/bin/bash
# Check 1's synthetic runs (4 workers, nice). Fresh seeds except 'repro' (the judge's own F-N1-worst-n300 paths).
cd "$(dirname "$0")"
PY=/home/bwoods1998/Work/long-term-capital-management/.venv/bin/python
run() { echo "=== $1 R=$2 chunk=$3 $(date -u +%H:%M:%SZ)"; nice -n 5 $PY calib_check1.py run --grid "$1" --reps "$2" --chunk "$3" --workers 4 > "check1.$1.log" 2>&1 || echo "FAILED $1"; }
run repro 2000 100
run phi 1000 50
run tails 1000 50
run drifts 1000 50
run base 1000 50
run life 400 25
$PY calib_check1.py report > check1.report.txt 2>&1
echo "=== done $(date -u +%H:%M:%SZ)"
