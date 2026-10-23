#!/bin/bash
PY=/home/bwoods1998/Work/long-term-capital-management/.venv/bin/python
cd /home/bwoods1998/Work/.ltcm-main/goal-2026-10-19/evl10/recheck1/repro
until [ -f ../chain3.done ]; do sleep 10; done
FINAL_ARR=/dev/shm/evl10-recheck1/arr2 V2_ARR=/dev/shm/evl10-recheck1/arr2 $PY fp_fix1.py worst 3 > fp_fix1.worst.log 2>&1
cmp fp_fix1.worst.jsonl ../../fix1/fp_fix1.worst.jsonl && echo IDENTICAL > repro.result || echo DIFFERENT > repro.result
echo done > ../chain4.done
