# The unattended desk (v3) — October 2, 2026

The run record for LTCM v3: a swarm of options-trading agents meant to research around the clock, promote programs to
real money on forward evidence under a pre-registered control, size by that evidence, pay for its research out of
realized profit, deploy and repair itself, and need no human step. This record starts on Oct 2, 2026; the previous one
is [2026-09-30-continuous-learning.md](2026-09-30-continuous-learning.md).

**State at the end of Oct 2: v3 is built on branches and not deployed. The project runs on autopilot on the Oct 2
release, with research cut to a funded floor.**

## Why v3

A deep dive and a 20-minute watch of the running House on Oct 2 found a machine that runs continuously and honestly
and does not move toward money:

- **The verifier was built for a fund and applied to a small account.** One contract per structure; a sealed-holdout
  pass after the Holm correction needs a net edge per structure that no documented retail options premium has at one
  lot. Expected time to a qualified family was months, and it would then earn a few dollars a day.
- **The research loop produced noise.** In the six days since the Sept 26 reset, 2,370 families were born and 2,349
  retired (mean life about 3 hours); 105,273 trials; 3 holdout looks, 0 passes; 0 Candidates ever. Researchers spent
  their notes fighting the program API and grinding parameters.
- **The human was the control plane.** Every deploy, grant ratification, settings change, agenda, revival, retirement
  sweep, cohort end, gate re-base, economics report and post-mortem was a command from the operator's laptop (37
  distinct human steps, 23 with no automatic path).
- **The cost base could not close at this capital**, and the 2026 holdout is not sealed against the models' own
  training data, while forward shadow trading on live quotes (the one clean judge) was "never evidence".

## The owner's decisions

- **D1 capital:** stays where it is (about $1,300).
- **D2 evidence:** a forward ladder (practice shadow, then Probe, then Sized) under a pre-registered multiple-testing
  control replaces the sealed-holdout look as the gate to real money; the holdout becomes a free pre-filter.
- **D3 structures:** defined-risk short premium (credit verticals, iron condors, iron butterflies) opens for real money
  at $2,000 of equity or more.
- **D4 funding:** research is paid for by a rule on trailing realized profit, inside the prefunded Sail and Claude
  meters; the desk never asks for a top-up while a meter has 60 days of runway.
- **D5 autonomy:** the in-box updater deploys main behind its walls; the engineer's research-class pull requests merge
  on green CI plus an automated adversarial review; protected paths stay the owner's deploy; the grant re-ratifies
  itself after an owner deploy.
- **D6 data:** the options data vendor stays until the ladder is live.

## The plan, by phase

| Phase | What | State |
|---|---|---|
| 0 | Stop the treadmill: research to a funded floor, end dead practice cohorts, fix live nuisances, a baseline | Done on the box (operator, Oct 2 evening); the code fixes are in V3-A |
| 1 | The autonomy core: House jobs for every operator script, the budget rule, the standing grant, self-deploy, failure drills | Built (V3-A, not deployed) |
| 2 | Research v3: fewer, stronger researchers; hypotheses from documented premia; the strategist writes the agenda | Built (parked) |
| 3 | Evidence v3: the forward ladder, benchmarked before it binds | Built and benchmarked; does not bind yet (below) |
| 4 | Recursive harness improvement: an engineer, a reviewer and the updater | Built (parked) |
| 5 | The economics autopilot and a daily public scoreboard | Built in V3-A (not deployed) |

## What was built on Oct 2

All of it is on branches; none of it is on main or on the House.

- **V3-A** (integration branch `release/v3a`, draft PR #489):
  - `league/ops/`: the House's own jobs on its NYSE calendar (pre-open checks, the close economics, a daily public
    scoreboard committed through the gateway, hygiene, a market-clock check, the standing grant, the budget rule,
    monthly failure drills), run in a niced, memory-capped child with receipts, and private daily receipts the
    operator reads through Sail's file API without running anything on the box.
  - The budget rule: research dollars a day from trailing-30-day realized options profit, inside the prefunded meters
    (a 90-day target runway, a 60-day card line), applied tighten-only to the spend knobs, failing closed.
  - The standing grant, updater hardening (`auto_update` on), the protected-path list widened to the budget's
    enforcers, the evaluator's identity and the route to real money.
  - Live-path fixes: exit-only instances stop asking to open, practice chain reads clamped to what the Gym holds,
    practice position caps that mirror Probe, an honest practice shed.
  - The gateway: a docs route (one dated page a day under `docs/runs/desk/`), review and merge routes for the
    engineer's lane-confined branches, a funding notice, an admin log.
  - Settings as code: a repo `policy.json` layer between the defaults and the box's `swarm.json`.
- **Parked:** the forward ladder (`v3/wp6`, `v3/wp6b`), credit types at $2,000 and paper proofs per type (`v3/wp7`),
  researchers v3 with sweeps, a mandatory placebo row and a per-family ledger (`v3/b1`), births v3 from a curated
  mechanism library and the strategist's whole agenda (`v3/b23`), the weekly post-mortem (`v3/b4`), the engineer and
  reviewer (`v3/b5`).

## The forward ladder's benchmark (development cohort)

The ladder was benchmarked against the sealed-look design on synthetic worlds before it may bind (30 replications a
world; 16 practice slots over 160 forward sessions):

- On **memorized and cost-erased edges** (a program whose edge shows in replay and is gone forward), the ladder
  promoted 3-4% of entrants; the sealed look 21-27%.
- On **real (planted) edges**, the ladder missed far fewer: in the mixed desk 36% of the positives against 62%.
- On **pure noise, a skewed null (frequent small wins, rare large losses) and drift-only programs**, the ladder as
  specified promoted 4-8% of entrants; the sealed look about 0.1%. The cause is judging every cohort at every session
  from its 20th to its 60th.

So the ladder ships with `binding: false` (it would record "would promote" receipts and promote nothing). Before any
confirmation run, the rule for when it may bind was pre-registered: on a fresh-seed confirmation cohort, every negative
world at or under 1.0% false promotions and not significantly above the sealed look (one-sided Fisher test), pooled
false promotions at or under the sealed look's, and fewer missed signals in the mixed desk. A tighter design (judgements
at fixed checkpoints with a lower false-discovery rate and a bound on drift-adjusted returns) is being chosen on the
development cohort; the development figures are never the verdict.

## Why v3 waits

When the owner asked for an autopilot on the evening of Oct 2, V3-A was integrated but not finished: two review-fix
branches still conflicted with the integration fixes, and no CI run had completed on the final head. Shipping about ten
thousand lines of new operations and money-path code just before an unattended stretch is the wrong risk, so production
stays on the proven Oct 2 release and v3 waits for a session that can finish, test and watch it.

## Autopilot (from Oct 3)

- Production: House release `20261002T112610Z-e11710692569`, gateway `4471596a`; the updater off.
- Research at a funded floor (since 17:04-17:23Z Oct 2): 16 families at the start, floor 8, one Gym box, the Sail
  researchers at $0.25 an hour, the architect every two hours, the strategist once a day. About $5 a day of Sail; Sail's
  balance lasts about three weeks before the guard's brake.
- Trading every New York session: calibration round trips, the House live test, the incubator, and the practice league
  in shadow. The one tuition lot exits before its Oct 7 expiry cutoff.
- The settings in effect and how to resume: [operations](../operations.md) ("Autopilot").

## Scoreboard

| Measure | Value |
|---|---|
| Release running | `20261002T112610Z-e11710692569` (main `e3d0111f`), gateway `4471596a` |
| Realized options P&L since the Sept 26 reset, at the Oct 2 close | -$40.63 (calibration -$38.76; regulatory fees -$1.87; strategy routes $0) |
| Input costs since the reset, at the Oct 2 close | $607.88 |
| Net, at the Oct 2 close | **-$648.51** (-$772.67 with the open tuition lot at its conservative mark) |
| Families alive | 16 |
| Holdout looks | 3, 0 passed |
| Programs promoted by forward evidence | 0 (the ladder is not deployed) |
| Retained harness improvements | 0 |
| v3 | built on branches, not deployed |

No program trades real money through evidence yet, and Net is negative. The goal remains unmet.
