#!/bin/bash
# RE-CHECK 1 of PREREG-EVL-9: after the TAUS stage: fix2 (SP20's precision and power price), the decayed-edge and
# own-direction drift cells, then the two stresses; 8 workers at a time.
cd "$(dirname "$0")"
PY=/home/bwoods1998/Work/long-term-capital-management/.venv/bin/python
while pgrep -f "rc9_taus.py run" > /dev/null; do sleep 15; done
$PY rc9_fix.py fix2 > rc9.fix2.log 2>&1 || echo "FAILED fix2"
$PY rc9.py run --grid hd --workers 8 > rc9.hd.log 2>&1 || echo "FAILED hd"
$PY rc9_stress.py > rc9.stress.log 2>&1 || echo "FAILED stress"
echo "=== chain done $(date -u +%H:%M:%SZ)"
