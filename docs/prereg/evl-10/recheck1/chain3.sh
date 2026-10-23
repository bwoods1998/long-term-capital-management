#!/bin/bash
PY=/home/bwoods1998/Work/long-term-capital-management/.venv/bin/python
cd /home/bwoods1998/Work/.ltcm-main/goal-2026-10-19/evl10/recheck1
until [ -f chain2.done ]; do sleep 10; done
$PY fp_recheck1_nvk2.py 3 > fp_recheck1.nvk2.log 2>&1
echo done > chain3.done
