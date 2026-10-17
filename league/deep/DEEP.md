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
  "contamination-probe", by the gate's look and the probe alone: a test holds the list), only inside a look, only into
  a temporary store inside the sealed tree (`sealed/.looks/deep-<segment>-p<pid>-*`, 0700) removed after it, on
  failure too. A look's process killed inside it (the ops runner's wall SIGKILL, a CPU or memory limit, a box restart)
  runs no `finally`: what it left is SWEPT (`blocks.sweep`: its process is gone, or it is two hours old) before the next
  temporary store is made, and first thing in every `deep_report`, `equity_deep` and contamination-probe run; a test
  kills a child mid-look and watches each of them sweep it. No look is begun with less than 20 minutes of
  `deep_report`'s wall left.
- TRAIN-D (2010-15) reads its open span alone; it never opens `sealed/`.
- A failed data audit writes nothing (`league/ops/equity_deep.py`): the calendar against the pinned fixture, OHLC
  sanity, every vendor factor step on a listed event, Tiingo against SIP on 2016-19, stale closes and zero volumes, and
  NO missing session of a DVAL fund in `dval` or `traind` (a look-back gap in `history` is kept and unscores segment
  A for that fund: no look is spent on a gap). A failed audit leaves `audit-failed.json` (counts and verdicts), and no
  request is made again until the job setting `refetch` asks. Until the audit, DVAL is staged in
  `.staging/sealed/dval/` (0700, the `DEEP_GATE` mark). A run stops at the first answer that will not change tonight
  (503 "setup": no `TIINGO_TOKEN`; a refusal) and after three failures in a row.
- The gateway serves the DVAL window to the House's runtime token alone (`lib/tiingo.mjs` `refusal`, the `caller`):
  the router admits no other caller at the route, and this wall holds if that ever widens. `TIINGO_TOKEN` is one of
  the secrets no desk commit may carry (`lib/desk.mjs`).
- Outputs are verdicts and counts. The ledger keeps booleans; the report counts; no DVAL figure, curve or decimal
  leaves the House, and nothing derived from vendor data is committed. The two fixtures are dates only. The
  contamination probe's 2001-08 cells keep n, skipped, periods, symbols, m, p_perm, readable and recalled only (never
  acc, base, lo, hi, correct or ties).
- The look ledger FAILS CLOSED: a file that is there and does not parse, or is of another version, refuses every look
  and is never written over (`ledger.json.prev` is the file before its last save); `deep_report` returns failed.
- The French job drops 2001-2008 like the reserve, and rewrites its stored files without them.

## S3

- **Deep key**: x2, the per-symbol drift-free timing excess (`stat.py`), at k 2.0: t >= c_D on the full DVAL series
  (1,944) and on the masked one (1,709: PREREG-H's nine windows out, one-sided), and the k 3.0 sum above zero.
  c_D = max(receipt 1.02, own floor + 0.05).
- **Recent key**: S2's r at k 1.0 pooled over R + V + H (the reserve 2020-21, 2025, the 194 holdout sessions), raw
  (the S2 variant), with sum_H > 0. c_R = max(receipt 1.20, own floor + 0.05). The receipt computed its recent null at
  k 2.0 with the true drift removed; under N0 the null rate does not depend on k, so c_R holds at k 1.0.
- **D2 is decided: the reserve IS judged, inside S3 beside the deep key, never alone** (the captain's A58, by the
  owner's delegation). `elane.deep.reserve` is "judged" (policy.json and the code's default): every real look reads
  BOTH keys, the deep key first. "sealed" is the switch back, and then NO look is made at all (no DVAL, no reserve):
  a version is judged on both keys or not at all.
- **How the reserve stays sealed until the look.** Its bars sit in the House's equity store, in the Train window, which
  asks no capability for them: the swarm's own seal keeps every reserve session unrun (league/swarm/elane_seal.py).
  Here the one call that runs a reserve session is `HouseRuns.recent` (league/ops/deep_report.py), made only by
  `gate._recent_key`, which only `gate.look` calls, for a real look (never a canary), and only after (1) every
  eligibility rule held, (2) both own floors and bars were computed from open data only (the Train-era runs and the
  relabeled TRAIN-D run; R's dates enter the recent floor's CRASH set as positions, never as bars), (3) the ledger row
  was written (the look is spent) and (4) the deep key's DVAL runs finished. The R, V and H arrays live in memory in
  that call; `screen3.recent_key` returns booleans; the ledger keeps booleans. Tests pin the order and the callers
  (league/tests/test_deep_gate.py `TheReserveStaysSealed`). The relabeled DVAL segments' pseudo-dates reach into
  2020-21, but they carry DVAL bars, not the reserve's.
- **Pass = both.** The receipt (`docs/benchmarks/equity_screen_3.json`: history-1017 item 5's synthetic receipt,
  copied verbatim, its code pinned before its one run, gates G1-G8 passed): zero-edge FP 14.8% deep alone, 11.8%
  recent alone, 1.7% joint; worst no-edge-now 10.3% (deep-remembered), inside PREREG-H's 15%/12%/2.5%/12%.
- **Own floors** (`screen3.py`, the receipt's `floor`): the program's own sessions on TRAIN (2016-19, 2022-24) and
  TRAIN-D, each run from its first decision + 2; null N0 per key; worlds of the key's geometry by a stationary block
  bootstrap (mean block 120), 20,000 in each of BASE and CRASH (the mask's positions, and R's 2020-02-20..03-23, filled
  from the pool's top-5% stress sessions); the key as judged in every world; the floor holds in both sets.
- **Eligibility** (pre-look, no look spent): ETF only (DVAL's 15); not a strong-recall route (contam_probe's 2001-08
  cells; unmeasured: the look waits; read before any run, so a wait costs none; a family with no route: a captain's
  seed or its lineage is measured as not strong-recall, any other is refused); calendar-blind by both checks; at most
  50 round trips a year and 25% close-to-next-open lots (Train-era runs); 2001-04 the liquid core only, the other
  SPDRs from 2005 when their stale-close audit is clean; no segment where a NEEDS fund has a data gap; at least 750
  scored DVAL sessions after inception and look-back (the first decision holds history + 1 bars, the engine's ctx: at
  history 504 segment B scores 1,006). REPORT-ONLY beside it, the LEVEL TEST: the behavioural store again at 2.5x the
  prices and 0.4x the volumes; a program whose entries or exits move reads levels (which tell 2001-08 apart) and is
  counted, never refused (PREREG-H names no such rule).
- **Looks** (`gate.py`): one a version (a report-only look IS the look), three a mechanism cell, 150 before an erosion
  review; in each block of ten looks one random-timing canary at the receipt's seeded slot, mirroring the version
  looked at before it (per symbol an on/off Markov chain matched to its Train-era round trips, holds and weights,
  written into the program: it reads no price and no date), judged on the deep key alone; S3 halts when the canaries'
  deep-key passes exceed the central 95% band at 15%. Beside the halt, REPORT-ONLY, an alarm at the band of the
  receipt's own synthetic canary rate (0.78%): the 15% halt sees gross breakage only.
- **What spends a look**: a begun look whose sealed run the program's own errors ended is spent and failed; one whose
  sealed run was sent and not answered (`RunLost`), or whose process was killed, is owed once more, then spent and
  failed; ANY OTHER ERROR IS THE HOUSE'S and spends nothing (the attempt is withdrawn). One version's error never stops
  the next: `deep_report` guards each look, records the error's class in the ledger, warns the House, goes on, and
  after three errors under one deep identity refuses the version (no look spent) until a release moves the identity.
- **The report** (`report.json`, counts and words): eligible, looked, passed, each key's passes against the receipt's
  zero-edge prediction, failed, the canaries (halt and alarm), the refusals by rule, the House's errors, the budget, BY
  SEAT (a seated version's recent key re-reads the windows S2 seated it on) and BY SOURCE (a captain's seed carries a
  mechanism published with DVAL in its discovery sample), the level readers, and the receipt's unstated limits
  (`config.LIMITS`: the canary halt's blindness, x2's t in units of x2's sd, the seated bias, levels, sources), each
  for a re-pinned receipt builder or a PREREG amendment before H-lite.

Where PREREG-H leaves a choice, `config.READINGS` states the one made.

## Switching it on (R1's deploy: after checkpoint 15 is final, rel/1023a and POOL1 P1 settled; never in a freeze)

1. The owner's D1: `npx wrangler secret put TIINGO_TOKEN`, then the gateway deploy.
2. The House deploy: league/swarm/policy.json ships `elane.deep` {"mode": "report", "reserve": "judged" (D2, decided
   in A58), "looks_per_run": 2}; `"mode": "off"` in `<state>/swarm.json` is the switch back (`deep_report` looks at
   nothing until step 3 has written a complete deep store), and `"reserve": "sealed"` stops every look.
3. `equity_deep` fetches daily at 06:40Z (no at-start trigger) until the store is complete: 60 requests (16 ETFs x 4
   spans, none before a fund's launch), one every 75 s, 40 a run, so two nights; then it skips. Its receipt is the
   audit's counts.
4. `deep_report` looks nightly at 07:10Z, `elane.deep.looks_per_run` (2) a night, both keys each; its room on the wall
   is the job setting `look_room_s` (1,200 s); `<state>/equity-deep/report.json`.
5. The eligibility census (history-1017 item 8, the captain's read-only scratch script
   `census/eligibility_census.py --window`, counts only): under 10 eligible current versions, H-lite is parked.

The contamination probe asks the two deep eras (S1, S2, S4) from the first Saturday the store is complete.

## Not in R1

TRAIN-D for births (R1b: `elane_train.py`, `elane_folds.py`), S3 gating seats (H-lite: the money digest moves),
true-date calendars and event rows (H-full).
