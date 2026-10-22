#!/bin/bash
# RE-CHECK 1 of PREREG-EVL-9: after rc9.py's bind grid: the cold references at the live pool sizes, the TAUS cells, the
# two stresses, then the decayed-edge and own-direction drift cells; 8 workers at a time.
cd "$(dirname "$0")"
PY=/home/bwoods1998/Work/long-term-capital-management/.venv/bin/python
while [ "$(wc -l < rc9.bind.jsonl)" -lt 180 ]; do sleep 15; done
sleep 5
$PY rc9.py run --grid cold --workers 8 > rc9.cold.log 2>&1 || echo "FAILED cold"
$PY rc9_taus.py run --workers 8 > rc9.taus.log 2>&1 || echo "FAILED taus"
$PY rc9_stress.py > rc9.stress.log 2>&1 || echo "FAILED stress"
$PY rc9.py run --grid hd --workers 8 > rc9.hd.log 2>&1 || echo "FAILED hd"
echo "=== chain done $(date -u +%H:%M:%SZ)"
