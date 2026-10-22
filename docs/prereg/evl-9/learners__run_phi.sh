#!/bin/bash
# PREREG-EVL-9 learners lens: the day-momentum 0.20 null cells (A107's widened grid), 600 paths each, 4 workers.
cd "$(dirname "$0")"
PY=/home/bwoods1998/Work/long-term-capital-management/.venv/bin/python
nice -n 5 $PY calib_evl9.py run --grid phi --reps 600 --chunk 50 --workers 4 > calib_evl9.phi.log 2>&1
$PY calib_evl9.py report > calib_evl9.report.txt 2>&1
