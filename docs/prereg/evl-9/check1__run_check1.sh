#!/bin/bash
# EVL-9 check #1: the runs behind the findings (4 workers at most, one grid at a time). Seeds are in each script.
cd "$(dirname "$0")"
PY=/home/bwoods1998/Work/long-term-capital-management/.venv/bin/python
$PY check1_rfeat.py run --reps 400 --chunk 50 --workers 4 --only R-cold-worst-tau1 R-H0-worst-tau1 R-HD08-worst-tau1 R-H0-worst-tau1-tauhist R-cold-worst-tau05 R-cold-base-tau1 > check1_rfeat.log2 2>&1
$PY check1_rfeat.py report > /dev/null 2>&1
$PY check1_adv.py run --reps 400 --chunk 50 --workers 4 > check1_adv.log 2>&1
$PY check1_adv.py report > /dev/null 2>&1
$PY check1_guard.py --reps 1000 --workers 4 > check1_guard.log 2>&1
echo done > run_check1.done
