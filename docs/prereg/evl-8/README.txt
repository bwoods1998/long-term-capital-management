PREREG-EVL-8's FIX ROUND calibration (workflow wf_36aa484c-852, script goal-2026-10-19/workflows/evl8_fix.js sha256
b95ee789...; the captain's decisions F1-F13). SYNTHETIC ONLY: nothing here read the lane, the House, the gateway or any
run record. Every figure of ../PREREG-EVL-8.md sections 0, 3.3, 4.6, 6 and 12 is printed by report8f.py into
report8f.txt from the outputs below. Python: the repo's .venv (numpy 2.5.3), at most 8 workers. chain8.sh is the order.

px_final8.py      THE PX SEATS under PREREG-EVL-6 AS FROZEN (its calib_final.py record and search_final.py rule evaluation,
                  imported unchanged) on the PX designer's generator (../price/px_calib.py, reproduced exactly with no
                  addition on: `selftest`) with the frozen grid's day shapes, day-following counts and the money knife;
                  CAP 4 (F4). Phases: search (1,590 plausible cells x 1,000, seeds 171,000,001+), fresh (the near-worst
                  cells x 4,000, 172,000,001+), confirm (the chosen look's 16 worst x 4,000, 173,000,001+), base, stress,
                  power, money (check 1's money-population attack), shared (two ON seats sharing the drift), sens.
                  Each writes px8f.<phase>.jsonl (one row a cell: every candidate first look's rates), .index.jsonl, .log.
px_select8.py     F1's protocol (plan / choose / confirm-plan): px8f.fresh.cells.jsonl, px8f.choose.json (CHOSEN: 22, the
                  frozen first look; fresh worst 0.1190), px8f.confirm.cells.jsonl. Written before any fresh run.
px_demotion8.py   F3: PREREG-EVL-6 section 3's frozen demotion for a Probe stay of a PX seat (14 buys a session at Probe,
                  8 at Sized), +40 / +60 / 0 / -15 bp: px_demotion8.json, px_demotion8.out (seeds 178,000,001+).
calib_meta_f8.py  check 1's copy of the META designer's simulator (../check1/calib_meta_c1.py) with the frozen grid's day
                  shapes added (diff in its header).
meta_final8.py    THE META-LEARNERS under PREREG-EVL-6 as frozen, in runs, to 720 sessions, CAP 8 (and 4 beside):
                  meta8f.{null,stress,power}.jsonl (seeds 179,000,001+ / 179,500,001+ / 179,800,001+).
placebo8f.py      the placebo audit and the canary under the final PX screen (seeds 179,900,001+): placebo8f_F22.out.json.
timing8.py        F7's timing table and the request load, arithmetic on release 1019h's constants read from git: timing8.out.
budget8.py        F12's arithmetic on PREREG-EVL-6's frozen basis: budget8.out.
report8f.py       every table: report8f.txt.
copy8.sh          stages the record flat in ../../prereg/evl-8/ with SHA256SUMS.
scratch_arrays/   empty (calib_final.py's import creates the directory its own runs would use).

THE FINAL FIX (the same workflow's Final step, from 16:17Z Oct 22; the two re-checks' findings; SYNTHETIC ONLY). chain8b.sh
is the order:
calib_meta_b8.py  calib_meta_f8.py with ONE knob, Cell.beta_day (re-check 1's: an issuer's day-shock loading
                  clip(1 + beta_day x its volatility z, 0.2, 2.5)); beta_day 0 draws exactly as before (meta_life8.py
                  selftest -> meta8l.selftest.out).
meta_life8.py     THE META-LEARNERS PER RUN TO THE RUN'S END: the same learner and screen (meta_final8.screen_runs,
                  imported unchanged), T 2,500 (the worst cells 4,000), beta_day 0.3 plausible / 0.5 stress, seeds from
                  182,000,001: meta8l.life.jsonl, .index.jsonl, .log (phase main); meta8l.ext.jsonl, .index.jsonl, .log
                  (phase ext: the plausible cells still open at 2,500, again to 4,000 on their own seeds).
px_shared8day.py  re-check 1's rc_shared.py with paths moved here, seeds from 183,000,001: px8f.sharedday.jsonl, .log.
px_demotion8.s184.json / .out   px_demotion8.py (unchanged) --only '40bp|' --R 4000 --seed0 184000000.
timing8b.py       the timing table on release 1019h's cadence (DATA_INTERVAL, the read-timeout cap, the book's minute
                  ticks, the late passes): timing8b.out (supersedes timing8.out's close and open arithmetic; its
                  request rows stand).
budget8b.py       the charges and the budget with the META charge read from meta8l.life.jsonl: budget8b.out
                  (supersedes budget8.out).
report8f.py       extended with the final fix's three tables.
PREREG-EVL-8.fixround-98dd0eaf.md  the fix round's text (sha256 98dd0eaf...) as re-checked, recovered from the 09:00 PDT /home snapshot; the final step edited ../PREREG-EVL-8.md from it.
