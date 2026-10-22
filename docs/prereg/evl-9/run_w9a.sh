#!/bin/bash
# PREREG-EVL-9 final calibration, stage A: the SEARCH seeds (401,000,001 +), the POWER seeds (403,000,001 +) and the
# STRESS seeds (405,000,001 +), 200 programs a cell, one pool of 8 workers. Synthetic only.
cd "$(dirname "$0")"
PY=/home/bwoods1998/Work/long-term-capital-management/.venv/bin/python
echo "=== stage A $(date -u +%H:%M:%SZ)"
$PY calib_w9.py multi --only search:200 power:200 stress:200 --chunk 50 --workers 8 > w9.stageA.log 2>&1 || echo "FAILED A"
echo "=== done $(date -u +%H:%M:%SZ)"
