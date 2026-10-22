#!/bin/bash
# RE-CHECK 1 of PREREG-EVL-9: after the hd stage: the levels-deleted cells, then the two stresses; 8 workers at a time.
cd "$(dirname "$0")"
PY=/home/bwoods1998/Work/long-term-capital-management/.venv/bin/python
while pgrep -f "rc9.py run --grid hd" > /dev/null; do sleep 15; done
$PY rc9_nolev.py > rc9.nolev.log 2>&1 || echo "FAILED nolev"
$PY rc9_stress.py > rc9.stress.log 2>&1 || echo "FAILED stress"
echo "=== chain done $(date -u +%H:%M:%SZ)"
