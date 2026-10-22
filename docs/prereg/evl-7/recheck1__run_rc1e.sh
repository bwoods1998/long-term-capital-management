#!/bin/bash
# Later stages, re-prioritized after rmore showed pool 800 at 0.199 (replaces three queued runners stopped before they
# ran anything): pool 800, the fixes, the learner's knife edge, a learnable family drift. Synthetic only.
set -u
cd "$(dirname "$0")"
PY=/home/bwoods1998/Work/long-term-capital-management/.venv/bin/python
until [ -f run_rc1.done ]; do sleep 15; done
$PY rc1.py run --grid r800 --reps 1000 --chunk 50 --workers 8 > rc1.r800.log 2>&1
$PY rc1.py run --grid fix --reps 1000 --chunk 50 --workers 8 > rc1.fix.log 2>&1
$PY rc1.py run --grid knife --reps 1000 --chunk 50 --workers 8 > rc1.knife.log 2>&1
$PY rc1.py run --grid fam --reps 1000 --chunk 50 --workers 8 > rc1.fam.log 2>&1
$PY rc1.py report > rc1.report.txt 2>&1
echo done > run_rc1e.done
