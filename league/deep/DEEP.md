# The deep key (release R1, "deep-report")

The history-expansion plan (the captain's A58; `history-1017/HISTORY-PLAN.md` in the captain's scratch) seals
2001-04-09..2008-12-31 as a deep key, **DVAL**, and judges it beside a recent key: **S3, the two-key screen**. Its
pinned pre-registration is **PREREG-H** (sha256 `6ca65b3e...`, pinned 2026-10-17T19:12:02Z, before any of this code
was written). R1 is report-only: every eligible ETF version gets its one S3 look, the verdicts are sealed, the
captain reads counts, and **births see nothing**. Nothing seats on S3 until H-lite.

## No identity moves

A program never sees a date. So a deep segment's bars are written session for session onto the first N Train
sessions from 2016-01-04 (`relabel.py`) and the **unchanged** equity engine runs them. Nothing of league/equity,
league/gym, league/live or ltcm/ changes: the equity identity `78022ca6` and the options execution fingerprint
`b60410ad` are byte-identical (`config.LEGACY_IDS`; `league/tests/test_deep_identity.py`). Calendar and event
readers would read scrambled dates there, so they are not eligible (`blind.py`: an AST scan and a behavioural test on
two labelings of one synthetic store). league/deep has its own identity (`identity.py`, the league/xs pattern), on
every ledger row.

## The seal

- DVAL never touches the desktop. The House fetches it through the gateway's Tiingo route
  (`GET /v1/tiingo/daily/<SYM>/prices`: 16 ETFs, 1999-01-04..2019-12-31 only, the adjusted columns dropped) into
  `<state>/equity-deep/sealed/` (0700, the `DEEP_GATE` mark). The token is the owner's gateway secret (D1).
- Sealed blocks open only with a `DeepGateCapability` (unconstructible; minted on the marked store for "s3-look" or
  "contamination-probe"), only inside a look, only into a temporary store removed after it, on failure too.
- TRAIN-D (2010-15) reads its open span alone; it never opens `sealed/`.
- A failed data audit writes nothing (`league/ops/equity_deep.py`): the calendar against the pinned fixture, OHLC
  sanity, every vendor factor step on a listed event, Tiingo against SIP on 2016-19, stale closes and zero volumes.
- Outputs are verdicts and counts. The ledger keeps booleans; the report counts; no DVAL figure, curve or decimal
  leaves the House, and nothing derived from vendor data is committed. The two fixtures are dates only.
- The French job drops 2001-2008 like the reserve, and rewrites its stored files without them.

## S3

- **Deep key**: x2, the per-symbol drift-free timing excess (`stat.py`), at k 2.0: t >= c_D on the full DVAL series
  (1,944) and on the masked one (1,709: PREREG-H's nine windows out, one-sided), and the k 3.0 sum above zero.
  c_D = max(receipt 1.02, own floor + 0.05).
- **Recent key**: S2's r at k 1.0 pooled over R + V + H (the reserve 2020-21, 2025, the 194 holdout sessions), with
  sum_H > 0. c_R = max(receipt 1.20, own floor + 0.05). The receipt calibrates it with the reserve in it, so while the
  owner's D2 is not "judged" (`elane.deep.reserve` "sealed") a look reads the deep key only and its recent key is
  PENDING; it is read once, when D2 is "judged" (DVAL is not read again).
- **Pass = both.** The receipt (`docs/benchmarks/equity_screen_3.json`: history-1017 item 5's synthetic receipt,
  copied verbatim, its code pinned before its one run, gates G1-G8 passed): zero-edge FP 14.8% deep alone, 11.8%
  recent alone, 1.7% joint; worst no-edge-now 10.3% (deep-remembered), inside PREREG-H's 15%/12%/2.5%/12%.
- **Own floors** (`screen3.py`, the receipt's `floor`): the program's own sessions on TRAIN (2016-19, 2022-24) and
  TRAIN-D, each run from its first decision + 2; null N0 per key; worlds of the key's geometry by a stationary block
  bootstrap (mean block 120), 20,000 in each of BASE and CRASH (the mask's positions, and R's 2020-02-20..03-23, filled
  from the pool's top-5% stress sessions); the key as judged in every world; the floor holds in both sets.
- **Eligibility** (pre-look, no look spent): ETF only (DVAL's 15); calendar-blind by both checks; at most 50 round
  trips a year and 25% close-to-next-open lots (Train-era runs); 2001-04 the liquid core only, the other SPDRs from
  2005 when their stale-close audit is clean; at least 750 scored DVAL sessions after inception and look-back; not a
  strong-recall route (contam_probe's 2001-08 cells; unmeasured: the look waits).
- **Looks** (`gate.py`): one a version (a report-only look IS the look), three a mechanism cell, 150 before an erosion
  review; in each block of ten looks one random-timing canary at the receipt's seeded slot, mirroring the version
  looked at before it (per symbol an on/off Markov chain matched to its Train-era round trips, holds and weights,
  written into the program: it reads no price and no date), judged on the deep key alone; S3 halts when the canaries'
  deep-key passes exceed the central 95% band at 15%.

Where PREREG-H leaves a choice, `config.READINGS` states the one made.

## Switching it on (R1's deploy: after checkpoint 15 is final, rel/1023a and POOL1 P1 settled; never in a freeze)

1. The owner's D1: `npx wrangler secret put TIINGO_TOKEN`, then the gateway deploy.
2. The House deploy: league/swarm/policy.json ships `elane.deep` {"mode": "report", "reserve": "sealed" (until D2),
   "looks_per_run": 2}; `"mode": "off"` in `<state>/swarm.json` is the switch back (`deep_report` looks at nothing
   until step 3 has written a complete deep store).
3. `equity_deep` fetches daily at 06:40Z (no at-start trigger) until the store is complete: 60 requests (16 ETFs x 4
   spans, none before a fund's launch), one every 75 s, 40 a run, so two nights; then it skips. Its receipt is the
   audit's counts.
4. `deep_report` looks nightly at 07:10Z, `elane.deep.looks_per_run` (2) a night; `<state>/equity-deep/report.json`.
5. The eligibility census (history-1017 item 8, the captain's read-only scratch script
   `census/eligibility_census.py --window`, counts only): under 10 eligible current versions, H-lite is parked.
6. The owner's D2: `elane.deep.reserve` "judged" reads every pending recent key (R + V + H) once.

The contamination probe asks the two deep eras (S1, S2, S4) from the first Saturday the store is complete.

## Not in R1

TRAIN-D for births (R1b: `elane_train.py`, `elane_folds.py`), S3 gating seats (H-lite: the money digest moves),
true-date calendars and event rows (H-full).
