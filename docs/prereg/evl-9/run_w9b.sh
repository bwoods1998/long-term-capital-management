#!/bin/bash
# PREREG-EVL-9 final calibration, stage B (after run_w9a.sh): select the worst warm cells on the SEARCH seeds
# (select_w9.py select), re-run them on FRESH seeds (402,000,001 +) at 2,000 programs each and the reference cells
# (402,500,001 +, 600 each: the cold twins, the base model and the CHAR20 stress), compute W9 (select_w9.py w9), run the worst warm cell of each learner over
# 200 sessions with at most three runs (LIFE, 404,000,001 +, 600 programs), then the report and the tables.
# Synthetic only; 8 workers.
cd "$(dirname "$0")"
PY=/home/bwoods1998/Work/long-term-capital-management/.venv/bin/python
echo "=== select $(date -u +%H:%M:%SZ)"
$PY select_w9.py select > select_w9.select.out 2>&1 || echo "FAILED select"
echo "=== fresh $(date -u +%H:%M:%SZ)"
W9_CELLS="$(cat w9.selected.json)" W9_SEED=402000001 $PY calib_w9.py run --grid fresh --reps 2000 --chunk 50 --workers 8 \
  --tag fresh > w9.fresh.log 2>&1 || echo "FAILED fresh"
echo "=== freshref $(date -u +%H:%M:%SZ)"
W9_CELLS="$(cat w9.refs.json)" W9_SEED=402500001 $PY calib_w9.py run --grid fresh --reps 600 --chunk 50 --workers 8 \
  --tag freshref > w9.freshref.log 2>&1 || echo "FAILED freshref"
$PY select_w9.py w9 > select_w9.w9.out 2>&1 || echo "FAILED w9"
echo "=== life $(date -u +%H:%M:%SZ)"
W9_CELLS="$($PY -c "
import json
best = {}
for c in json.load(open('w9.selected.json')):
    best.setdefault(c['learner'], c)
print(json.dumps(list(best.values())))
")" $PY calib_w9.py run --grid life --reps 600 --chunk 50 --workers 8 > w9.life.log 2>&1 || echo "FAILED life"
$PY calib_w9.py report > w9.report.txt 2>&1
$PY table_w9.py > /dev/null 2>&1 || echo "FAILED table"
echo "=== done $(date -u +%H:%M:%SZ)"
