#!/bin/bash
# chain_ff2.sh replaces chain_ff.sh (stopped while it was still waiting for the search): the same stages, with the G2
# simulation and the timing arithmetic run right after the search, so no more than 8 processes ever run at once.
# The final minimal fix's calibration, in order (synthetic only; 8 workers). The search was started by hand at
# 18:18:08Z (ff.search.log); this chain waits for it, then runs G2's simulation, the selection, the two fresh rounds,
# W9, life at each learner's worst fresh cell (T 200, at most three runs), the cold twins of those cells, power and the
# stresses.
cd "$(dirname "$0")"
PY=/home/bwoods1998/Work/long-term-capital-management/.venv/bin/python
while pgrep -f "calib_w9ff.py run --grid search" > /dev/null; do sleep 20; done
st() { echo "=== $1 $(date -u +%H:%M:%SZ)"; }
st g2; $PY g2_w9ff.py > g2_w9ff.out 2>&1 || echo FAILED g2
st select; $PY select_w9ff.py select > ff.select1.out 2>&1 || { echo FAILED select; exit 1; }
export W9F_CELLS="$(cat ff.selected1.json | tr -d '\n')"
st fresh1; $PY calib_w9ff.py run --grid fresh1 --reps 1000 > ff.fresh1.log 2>&1 || { echo FAILED fresh1; exit 1; }
st select2; $PY select_w9ff.py select2 > ff.select2.out 2>&1 || { echo FAILED select2; exit 1; }
export W9F_CELLS="$(cat ff.selected2.json | tr -d '\n')"
st fresh2; $PY calib_w9ff.py run --grid fresh2 --reps 1000 > ff.fresh2.log 2>&1 || { echo FAILED fresh2; exit 1; }
st w9; $PY select_w9ff.py w9 > ff.w9.out 2>&1 || { echo FAILED w9; exit 1; }
export W9F_CELLS="$(cat ff.lifecells.json)"
st life; $PY calib_w9ff.py run --grid life --reps 600 > ff.life.log 2>&1 || echo FAILED life
export W9F_CELLS="$(cat ff.coldcells.json)"
st coldref; $PY calib_w9ff.py run --grid coldref --reps 600 > ff.coldref.log 2>&1 || echo FAILED coldref
unset W9F_CELLS
st power; $PY calib_w9ff.py run --grid power --reps 200 > ff.power.log 2>&1 || echo FAILED power
st stress; $PY calib_w9ff.py run --grid stress --reps 200 > ff.stress.log 2>&1 || echo FAILED stress
for g in search fresh1 fresh2 life coldref power stress; do $PY calib_w9ff.py report --grid $g; done > ff.report.txt 2>&1
st done
