#!/bin/bash
# The rest of PREREG-EVL-7's final calibration, after run_w7.sh's stop (see its last lines): the search resumed at 500
# programs a cell; select_w7.py names the worst cells; those cells on FRESH seeds at 4,000 programs each; then power,
# life (T = 200, at most three runs) and the named stresses. Synthetic only; 8 workers.
cd "$(dirname "$0")"
PY=/home/bwoods1998/Work/long-term-capital-management/.venv/bin/python
run() { echo "=== $1 R=$2 chunk=$3 $(date -u +%H:%M:%SZ)"; $PY calib_w7.py run --grid "$1" --reps "$2" --chunk "$3" --workers 8 ${4:+--tag $4} > "w7.${4:-$1}.log" 2>&1 || echo "FAILED $1"; }
echo "=== search R=500 chunk=50 resume $(date -u +%H:%M:%SZ)"
$PY calib_w7.py run --grid search --reps 500 --chunk 50 --workers 8 --resume >> w7.search.log 2>&1 || echo "FAILED search"
$PY select_w7.py select > select_w7.select.out 2>&1
export W7_CELLS="$(cat w7.selected.json)" W7_SEED=202000001
run fresh 4000 50
$PY select_w7.py w7 > select_w7.w7.out 2>&1
unset W7_CELLS W7_SEED
run power 1000 50
run life 2000 50
run stress 1000 50
$PY calib_w7.py report > w7.report.txt 2>&1
echo "=== done $(date -u +%H:%M:%SZ)"
# 14:01Z: the search completed; the fresh stage FAILED at once (the search's workers had recorded no cell spec, so
# w7.selected.json held nulls: aborted/w7.fresh.failed.log) and the power stage was stopped a minute in
# (aborted/w7.power.*, discarded). select_w7.py now rebuilds the specs from the grid; run_w7e.sh runs the rest.
