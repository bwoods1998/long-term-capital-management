#!/bin/bash
# PREREG-EVL-7 re-check #1 runner (synthetic only). Order: the registered feature set first, then W7 rebuilt, then controls.
set -u
cd "$(dirname "$0")"
PY=/home/bwoods1998/Work/long-term-capital-management/.venv/bin/python
$PY rc1.py run --grid rfeat --reps 4000 --chunk 50 --workers 8 > rc1.rfeat.log 2>&1
$PY rc1.py run --grid w7 --reps 4000 --chunk 50 --workers 8 > rc1.w7.log 2>&1
$PY rc1.py run --grid rctl --reps 2000 --chunk 50 --workers 8 > rc1.rctl.log 2>&1
$PY rc1.py run --grid rmore --reps 1000 --chunk 50 --workers 8 > rc1.rmore.log 2>&1
$PY rc1.py run --grid rbase --reps 1000 --chunk 50 --workers 8 > rc1.rbase.log 2>&1
$PY rc1.py report > rc1.report.txt 2>&1
echo done > run_rc1.done
