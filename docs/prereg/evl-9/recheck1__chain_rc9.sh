#!/bin/bash
# RE-CHECK 1 of PREREG-EVL-9: after rc9.py's bind grid, the TAUS cells then the two stresses; 8 workers at a time.
cd "$(dirname "$0")"
PY=/home/bwoods1998/Work/long-term-capital-management/.venv/bin/python
while pgrep -f "rc9.py run --grid bind" > /dev/null; do sleep 15; done
$PY rc9_taus.py run --workers 8 > rc9.taus.log 2>&1 || echo "FAILED taus"
$PY rc9_stress.py > rc9.stress.log 2>&1 || echo "FAILED stress"
$PY rc9.py run --grid hd --workers 8 > rc9.hd.log 2>&1 || echo "FAILED hd"
echo "=== chain done $(date -u +%H:%M:%SZ)"
