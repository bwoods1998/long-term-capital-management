#!/bin/bash
# The order the fix round's calibration ran in (8 workers at most at a time).
cd "$(dirname "$0")"
PY=/home/bwoods1998/Work/long-term-capital-management/.venv/bin/python
until [ -s px8f.search.jsonl ]; do sleep 20; done
$PY px_select8.py plan > px_select8.plan.log 2>&1
$PY px_final8.py run --phase fresh --cells px8f.fresh.cells.jsonl --workers 8 > px8f.fresh.log 2>&1
$PY px_select8.py choose > px_select8.choose.log 2>&1
F=$($PY -c "import json; print(json.load(open('px8f.choose.json'))['chosen_first_look'])")
echo "chosen first look $F" >> chain8.log
$PY px_select8.py confirm-plan > px_select8.confirm.log 2>&1
$PY px_final8.py run --phase confirm --cells px8f.confirm.cells.jsonl --workers 8 > px8f.confirm.log 2>&1
for ph in base stress power money shared sens; do
  $PY px_final8.py run --phase $ph --workers 8 > px8f.$ph.log 2>&1
done
$PY px_demotion8.py --pass-start $F --workers 8 --out px_demotion8.json > px_demotion8.out 2>&1
$PY placebo8f.py 2000 $F > placebo8f.log 2>&1
for g in null stress power; do
  $PY meta_final8.py run --grid $g --reps 600 --workers 8 > meta8f.$g.log 2>&1
done
echo done > chain8.done
