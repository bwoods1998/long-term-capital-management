#!/bin/bash
PY=/home/bwoods1998/Work/long-term-capital-management/.venv/bin/python
cd /home/bwoods1998/Work/.ltcm-main/goal-2026-10-19/evl10/recheck1
until [ -f chain.done ]; do sleep 10; done
$PY fp_recheck1_stress.py 3 > fp_recheck1.stress.log 2>&1
echo done > chain2.done
