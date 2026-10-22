#!/bin/bash
# After run_w7c.sh's search (see its last lines): the selected worst cells on FRESH seeds at 4,000 programs each; W7;
# power; life (T = 200, at most three runs); the named stresses; the sensitivities (sens_w7.py, 2,000 each, fresh seeds
# 206,000,001 +); the screen's validation; the reports. Synthetic only; 8 workers.
cd "$(dirname "$0")"
PY=/home/bwoods1998/Work/long-term-capital-management/.venv/bin/python
run() { echo "=== $1 R=$2 chunk=$3 $(date -u +%H:%M:%SZ)"; $PY calib_w7.py run --grid "$1" --reps "$2" --chunk "$3" --workers 8 ${4:+--tag $4} > "w7.${4:-$1}.log" 2>&1 || echo "FAILED $1"; }
export W7_CELLS="$(cat w7.selected.json)" W7_SEED=202000001
run fresh 4000 50
$PY select_w7.py w7 > select_w7.w7.out 2>&1 || echo "FAILED w7"
export W7_CELLS="$($PY sens_w7.py)" W7_SEED=206000001
run sens 2000 50
unset W7_CELLS W7_SEED
run power 1000 50
run life 2000 50
run stress 1000 50
echo "=== validate $(date -u +%H:%M:%SZ)"
$PY calib_w7.py validate > validate_w7.out 2>&1 || echo "FAILED validate"
$PY calib_w7.py report > w7.report.txt 2>&1
$PY ev_w7.py > ev_w7.out 2>&1 || echo "FAILED ev"
echo "=== done $(date -u +%H:%M:%SZ)"
