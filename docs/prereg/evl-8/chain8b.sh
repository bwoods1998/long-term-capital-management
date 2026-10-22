#!/bin/bash
# The FINAL FIX's calibration order (8 workers at most at a time): the meta-learners to the run's end (main phase, then
# the extension of the plausible cells still open at 2,500 sessions to 4,000), then the two PX seats sharing every
# day-level shock, then the PX demotion's 40 bp corners on a third seed set.
cd "$(dirname "$0")"
PY=/home/bwoods1998/Work/long-term-capital-management/.venv/bin/python
$PY meta_life8.py selftest > meta8l.selftest.out 2>&1
# (the main phase, `meta_life8.py run --phase main --workers 8 > meta8l.life.log`, was started first, at 09:27 PDT)
while pgrep -f "meta_life8.py run" > /dev/null; do sleep 20; done
$PY meta_life8.py run --phase ext --workers 8 > meta8l.ext.log 2>&1
$PY px_shared8day.py 183000001 4000 > px8f.sharedday.log 2>&1
$PY px_demotion8.py --pass-start 22 --workers 8 --only "40bp|" --R 4000 --seed0 184000000 --out px_demotion8.s184.json > px_demotion8.s184.out 2>&1
echo done > chain8b.done
