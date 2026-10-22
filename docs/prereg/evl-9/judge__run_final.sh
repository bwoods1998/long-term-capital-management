#!/bin/bash
# The EVL-9 judge's runs of calib_evl9_final.py (seeds in its grid()); 4 workers at most, one grid at a time.
cd "$(dirname "$0")"
PY=/home/bwoods1998/Work/long-term-capital-management/.venv/bin/python
$PY calib_evl9_final.py run --grid null --reps 1000 --chunk 50 --workers 4 > calib_evl9_final.null.log 2>&1
$PY calib_evl9_final.py run --grid char --reps 1000 --chunk 50 --workers 4 > calib_evl9_final.char.log 2>&1
$PY calib_evl9_final.py run --grid power --reps 400 --chunk 50 --workers 4 > calib_evl9_final.power.log 2>&1
$PY calib_evl9_final.py run --grid life --reps 400 --chunk 50 --workers 4 > calib_evl9_final.life.log 2>&1
# Run by hand afterwards, 3 workers, beside `rt_skew_final.py 1500` on one (4 in all):
#   $PY calib_evl9_final.py run --grid stress --reps 1000 --chunk 50 --workers 3 > calib_evl9_final.stress.log 2>&1
$PY calib_evl9_final.py report > /dev/null 2>&1
echo done > run_final.done
