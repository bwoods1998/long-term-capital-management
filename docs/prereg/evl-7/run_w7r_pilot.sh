#!/bin/bash
# The final fix round, stage 0 (synthetic only; 8 workers): are the price and dollar-volume LEVELS a channel once they
# are built from the issuer's own returns? EVL-LRN-O1 (D 54, r1 / r5 / r20 deleted) at the worst corner, pools 300 and
# 800, the levels static (the lens's) against built from own returns; 1,000 programs a cell, seeds 500,000,001 +.
cd "$(dirname "$0")"
PY=/home/bwoods1998/Work/long-term-capital-management/.venv/bin/python
echo "=== pilot $(date -u +%H:%M:%SZ)"
$PY calib_w7r.py run --grid pilot --reps 1000 --chunk 50 --workers 8 > w7r.pilot.log 2>&1 || echo "FAILED pilot"
$PY calib_w7r.py report --only pilot > w7r.pilot.report.txt 2>&1
echo "=== done $(date -u +%H:%M:%SZ)"
