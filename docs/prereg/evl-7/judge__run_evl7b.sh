#!/bin/bash
# After run_evl7.sh: the named stresses under the EVL-6 draft's screen (the learner lens's final_stress cells and seeds).
cd "$(dirname "$0")"
PY=/home/bwoods1998/Work/long-term-capital-management/.venv/bin/python
while pgrep -f run_evl7.sh > /dev/null; do sleep 20; done
echo "=== stress R=1000 chunk=100 $(date -u +%H:%M:%SZ)"
nice -n 5 $PY calib_evl7.py run --grid stress --reps 1000 --chunk 100 --workers 4 > calib_evl7.stress.log 2>&1 || echo "FAILED stress"
$PY calib_evl7.py report > calib_evl7.report.txt 2>&1
echo "=== done $(date -u +%H:%M:%SZ)"
