#!/bin/bash
# The final fix round (re-check 1's blocker): E1's protocol re-run ON THE REGISTERED COLUMNS (r1 / r5 / r20 and the
# two levels deleted; EVL-LRN-ON's dmove built from the issuer's own simulated returns). Synthetic only; 8 workers.
# Stages (calib_w7r.py, select_w7r.py): the search (42 cells, 400 programs each, seeds 501e6 +); the selection (the top
# of each (lag, pool) group, then the 3-point band, at most 6 cells); those cells on fresh seeds (502e6 +, 4,000 each);
# W7; life (T = 200, at most three runs, 1,000 programs at each lag's worst fresh cell, 504e6 +); re-check 1's family
# drift at the corner (1,000, 507e6 +); power (500, 503e6 +); the other named stresses (500, 505e6 +); the base model
# (2,000, 506e6 +); the reports.
cd "$(dirname "$0")"
PY=/home/bwoods1998/Work/long-term-capital-management/.venv/bin/python
run() { echo "=== $1 R=$2 $(date -u +%H:%M:%SZ)"; $PY calib_w7r.py run --grid "$1" --reps "$2" --chunk 50 --workers 8 $3 > "w7r.$1.log" 2>&1 || { echo "FAILED $1 $(date -u +%H:%M:%SZ)"; exit 1; }; }
# the first attempt (17:22Z) failed at the counts-follow-the-day cell at pool 800 (aborted_w7r/): the search resumes
# with the same cells and seeds, that cell skipped
mv w7r.search.log w7r.search.first.log
run search 400 --resume
$PY select_w7r.py select > select_w7r.select.out 2>&1 || echo "FAILED select"
export W7R_CELLS="$(cat w7r.selected.json)" W7R_SEED=502000001
run fresh 4000
$PY select_w7r.py w7 > select_w7r.w7.out 2>&1 || echo "FAILED w7"
export W7R_CELLS="$($PY select_w7r.py top life)"
run life 1000
unset W7R_CELLS W7R_SEED
run fam 1000
run power 500
run stress 500
run sens 2000
$PY calib_w7r.py report > w7r.report.txt 2>&1
$PY table_w7r.py > table_w7r.md 2>&1 || echo "FAILED table"
$PY ev_w7r.py > ev_w7r.out 2>&1 || echo "FAILED ev"
echo "=== done $(date -u +%H:%M:%SZ)"
