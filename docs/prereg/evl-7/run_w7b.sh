#!/bin/bash
# After run_w7.sh's search: select W7's worst cells (select_w7.py), re-run them on FRESH seeds at 4,000 programs each,
# then power, life (T = 200, at most three runs), the named stresses and the sensitivity cells. Synthetic only; 8 workers.
cd "$(dirname "$0")"
PY=/home/bwoods1998/Work/long-term-capital-management/.venv/bin/python
while pgrep -f run_w7.sh > /dev/null; do sleep 20; done
run() { echo "=== $1 R=$2 chunk=$3 $(date -u +%H:%M:%SZ)"; $PY calib_w7.py run --grid "$1" --reps "$2" --chunk "$3" --workers 8 ${4:+--tag $4} > "w7.${4:-$1}.log" 2>&1 || echo "FAILED $1"; }
$PY select_w7.py select > select_w7.select.out 2>&1
export W7_CELLS="$(cat w7.selected.json)" W7_SEED=202000001
run fresh 4000 50
$PY select_w7.py w7 > select_w7.w7.out 2>&1
unset W7_CELLS W7_SEED
run power 1000 50
run life 2000 50
run stress 1000 50
echo "=== done $(date -u +%H:%M:%SZ)"
