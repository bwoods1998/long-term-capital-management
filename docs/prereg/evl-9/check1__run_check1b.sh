#!/bin/bash
# EVL-9 check #1, second batch (after run_check1.sh): the masked-r fix, paired by seed index with the first batch, and
# the 300-session life of the r-column learner.
cd "$(dirname "$0")"
until [ -f run_check1.done ]; do sleep 20; done
PY=/home/bwoods1998/Work/long-term-capital-management/.venv/bin/python
$PY check1_rfeat.py run --reps 400 --chunk 50 --workers 4 --only RM-cold-worst-tau1 RM-H0-worst-tau1-tauhist > check1_rfeat.log3 2>&1
$PY check1_rfeat.py run --reps 200 --chunk 50 --workers 4 --only R-H0-worst-tau1-tauhist-T300 RM-H0-worst-tau1-tauhist-T300 > check1_rfeat.log4 2>&1
$PY check1_rfeat.py report > /dev/null 2>&1
echo done > run_check1b.done
