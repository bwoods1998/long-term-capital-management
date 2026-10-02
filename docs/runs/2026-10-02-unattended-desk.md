# The unattended desk (LTCM v3) — October 2, 2026

This continues T0 `2026-09-26T06:23:14Z` and the financial basis of the Sept 26 reset (06:25:30Z); neither resets. The
previous record is [the continuous-learning run](2026-09-30-continuous-learning.md). The goal is **not achieved**:
release V3-A is built and integrated on `release/v3a` and **not yet deployed**. Until it is, production runs as the
Oct 2 pause left it ([operations](../operations.md), "Paused").

**The owner's goal:** a swarm of options trading agents that learns and profits on his brokerage account, to the point
where there is no human in the loop and it can run for good. v3 is the plan for the "no human in the loop" half: a desk
that costs little when it has nothing, spends more only out of what it earned, deploys and repairs itself, and tells the
truth about its record every day.

## Why v3

A deep read of the repository, the operator's records and the running House on Oct 2 (and a 20-minute watch of the
swarm in the session) found four structural reasons for the lack of progress. None of them is a bug; each is the
design meeting the account it runs on.

1. **The verifier was built for a fund and is applied to a small account.** The sealed-holdout look, corrected for every
   earlier look, needs a daily t-statistic that only a dense, large net edge reaches at one contract a structure. The
   retail-feasible options premia that the literature documents net far less than that after one-lot costs. A real edge
   would pass a look rarely, and when it did it would earn a few dollars a day at Probe. Engineering on the current rules
   does not change that arithmetic.
2. **The research loop makes noise, not knowledge.** The cheapest model rewrites programs dozens of times an hour per
   family; families refute themselves within hours; Train rank barely predicts Validation, and the Validation passes so
   far were long-market drift. The graveyard is large and mostly unread. Agent time is real, but much of it re-discovers
   that cheap out-of-the-money debit spreads expire worthless.
3. **The human is the control plane.** The watchdog restarts boxes and sends mail; it cannot fund, deploy, ratify,
   write the agenda, end a cohort, re-base the gate, write the economics or decide anything. The in-box updater that
   would deploy `main` by itself exists and was switched off. The Oct 2 inventory counted 37 distinct human steps the
   system depends on, most with no automatic path at all.
4. **The cost base cannot close at this capital.** Market data, the history vendor, the House box and the data box are
   fixed costs; research on top of them ran far above anything the options book could earn. "Compute drops to the floor
   when the forward record is flat" was written in the design and nowhere in the code.

Two more findings feed the plan: the 2026 holdout is not sealed against the models' own training (their data runs past
its start), and every look raises the bar for every later look, so the gate's throughput falls toward zero by design;
meanwhile the one clean judge, the forward record on live quotes, was "never evidence" and capped by a 1-vCPU box.

## The owner's six decisions (Oct 2)

- **D1 Capital:** stays as it is. The desk never deposits; the owner decides the capital.
- **D2 Evidence:** yes to the forward ladder: promotion to real money from the forward practice record under a
  pre-registered multiple-testing control; the 2026 holdout becomes a free pre-filter.
- **D3 Structures:** defined-risk short premium (credit verticals, iron condors, iron butterflies) opens for real money
  at $2,000 of equity and above, in one deploy with the gateway's list and a re-ratified grant.
- **D4 Funding:** research is funded by a rule on realized profit, inside the prefunded meters (Sail and Claude).
- **D5 Autonomy:** self-deploy with walls: the in-box updater on, a standing grant, protected paths still the owner's
  own deploy.
- **D6 Data vendor:** keep the current history plan until the ladder is live, then decide on the scoreboard's numbers.

## The build plan, by phase

| Phase | What | Class | State |
|---|---|---|---|
| 0 | Stop the treadmill: research settings to the floor, the stale practice cohorts ended, the live nuisances fixed, a baseline close economics | operator one-offs | settings floor applied Oct 2; the rest folded into V3-A's jobs and fixes |
| 1 | The autonomy core: self-deploy, House jobs in place of operator scripts, funding without hands, the standing grant, time and venue hardening, monthly failure drills | protected and research-class | **V3-A** (built, not yet deployed) |
| 2 | Research v3: fewer, stronger researchers; hypotheses from documented premia; the strategist owns the agenda; credit types in the Gym and the shadow book | research-class | after V3-A, through the updater |
| 3 | Evidence v3, the forward ladder: Practice → Probe → Sized on the forward record, its benchmark before it binds; the one planned evidence reset | protected (moves the fingerprint) | **landing in V3-A** (WP6, being integrated) |
| 4 | Recursive harness improvement: an engineer agent, an automated adversarial review, the updater's canary, retain or revert by a predeclared metric | research-class (the gateway's walls ship in V3-A) | after V3-A |
| 5 | The economics autopilot and the record: the daily scoreboard, the weekly post-mortem, the budget rule in force | ops jobs | the scoreboard and the budget in V3-A; the post-mortem after |

Every protected-path change is an owner deploy from the laptop, so V3-A carries all of them at once, ahead of the
30-day unattended clock; research-class work then ships through the updater during the clock. Any change to
`league/live/` or `league/gym/` moves the evaluator's fingerprint, so V3-A is also the one planned evidence reset of
v3 (practice cohorts restart on the new fingerprint; trials, lineages and consumed looks are kept).

### V3-A's work packages

- **WP1, the updater and deploys** (protected). `auto_update` on (`release_train_hours` stays 4). Before launching a
  deploy the updater stops the nightly daemon with a marked `nightly.stop` (`updater:<release>`) and waits, bounded and
  across ticks, for its lock; it removes only its own marker after the verdict, and a House start clears an orphaned
  one. Its watchdog's pid goes into `deploy.pid`, so the owner's `floor_box.py deploy` refuses while an updater deploy
  is in flight, and `push_release` clears only its own `incoming/<id>/`. The harness observer follows updater releases.
  The watchdog's launch environment is scrubbed. `python -m league.watchdog drill-rollback` proves the automatic
  rollback on demand. `ci.FORBIDDEN` gains `league/ops/{budget,drills,grant}.py`.
- **WP2, the House's jobs** (`league/ops/`). A calendar-aware scheduler on the House's NYSE calendar (DST-proof), a
  registry, a runner that starts at most one job at a time as a niced, memory- and CPU-bounded child, receipts in
  `<state>/ops.sqlite`, a missed job as a warning, and a private daily receipts file the operator reads without exec.
  Jobs: `preopen`, `economics`, `scoreboard`, `hygiene`, `clock`, plus `budget`, `grant` and `drills` from WP1/3/4.
- **WP3, the budget rule** (protected, below).
- **WP4, the standing grant** (protected, below).
- **WP5, live-path fixes** (protected; moves the fingerprint). An exit-only instance's open intents are dropped before
  the order path (counted, not refused every half hour); observe chain reads clamped to what the Gym store holds per
  root, so a chain over the page cap reads its clamped window instead of failing the root; practice positions capped
  as a Probe's (open structures per family, max loss per structure, family total) so a shadow book cannot pile up
  dozens of positions; an honest shed and a wider observe read budget (`live.observe_read_calls` 120) so 24 roots fit.
- **WP6, the forward ladder** (protected; moves the fingerprint). **Landing in V3-A, being integrated: the captain
  confirms after it merges.** Below.
- **WP7, money rules v3** (protected). **Landing in V3-A, being integrated: the captain confirms after it merges.** The
  constitution's real types gain `credit_vertical`, `iron_condor` and `iron_butterfly`, opened for real only at
  `credit_min_equity_usd` ($2,000) of equity, at the House and at the gateway; defined-risk only (no naked short leg),
  no in-the-money short leg at entry on an American-style root; a paper proof round trip per new type before its first
  real open. The gateway's `OPTION_STRUCTURES_REAL` gains the same types in the same deploy (`league/ci.py` holds the
  two lists equal).
- **WP8, the gateway** (protected). The desk's docs route, the engineer's review and merge routes, `funding` notices,
  and an admin log (below).
- **WP8b, the engineer's lanes.** `engineer/<lane>/<slug>-<hash>` branches may change only their lane's files (and add
  new `league/tests/test_harness_candidate_*.py` tests), in `league/ci.py` and the gateway alike.
- **WP9, fixes and settings as code.** Failed Gym pool rows settled against Sail's list; a Sail window fallback (a
  one-shot call stalled on a balanced queue retries once on the mapped asap profile); `league/swarm/policy.json`, the
  research settings as reviewed code (below).

### The forward ladder (WP6, landing in V3-A)

Train (the Gym, 2020-2024) → Validation (2025, its line unchanged) → **pre-filter** (the 2026 holdout as a free read:
no look row, no Holm correction, no look budget; it must not be negative) → **Practice** (shadow on live quotes, an
immutable version, every session recorded) → **Probe** (real, the money table's sizes) → **Sized** (real, quarter-Kelly
on the forward lower bound).

- Every practice entrant is a trial of its lineage and of the desk (an `entrants` table).
- **Probe** on the practice record alone: at least 20 sessions and 30 program closes (House-forced closes excluded); a
  day-block bootstrap one-sided 95% lower bound on mean P&L per dollar of maximum loss above zero; positive in at least
  3 of 4 equal sub-windows; a drift control (P&L net of the entry delta times the underlying's move must also be
  positive on average); Benjamini-Hochberg at q = 0.10 across every practice entrant of the trailing 90 days (an
  entrant without a full record counts with p = 1); and the pre-filter read non-negative. Each judgement is a
  `ladder_decisions` row (the practice receipt), and a promoted real instance runs exactly the practised version.
- **Sized** on the Probe's real fills: at least 20 real trades, mean above zero, 80% lower bound above zero, at least 5
  whole sessions. **Demotion:** a forward record negative over 20 trades, or a 20-session lower bound below zero.
- A ladder cohort runs until promoted, failed or 60 sessions; the old 3-session, 10-close completion no longer ends it.
  Tuition lots stop; the incubator stays as it is and never counts as ladder evidence.
- **The benchmark before it binds:** synthetic forward streams (absent, cost-erased, drift-only, fading, planted dense
  and sparse edges) through the practice ledger and the new rules, against the sealed-look design on the same worlds.
  The constitution's `options_money.ladder.binding` turns on only if the ladder's false promotions are at or below the
  sealed design's; until then the ladder judges and records ("would promote") and promotes nothing. The binding
  value at deploy is the captain's to confirm.

## The walls

What the desk may never do, whatever its agents or its updater decide:

- **Never** a deposit, transfer or borrowing; a cap above funded money; a secret change; releasing the drawdown stop or
  the kill switch; a naked short option; a forced or hand-placed trade; contaminated evaluation; a hidden cost;
  cherry-picked reporting.
- **The protected paths change only by the owner's own deploy.** Two walls, each in code:
  - *The updater* refuses any head of `main` that changes a file its running release's `league/ci.py` lists as
    FORBIDDEN: the money table (`league/constitution.py`), the grant (`league/live_trading.py`), the live path
    (`league/live/`), the ledger and the book, the evaluator, the statistics, the updater, the watchdog and `ci.py`
    itself, the gateway, the workflows, and from V3-A the budget rule, the standing grant's job and the drills
    (`league/ops/{budget,grant,drills}.py`). It also refuses a `config.json` that moves more than its operating dials,
    and any change to `real_money`.
  - *The gateway's merge route*, the only way the engineer's pull requests merge, refuses that list plus the evaluator's
    identity and its data (`league/gym/`, `league/swarm/{gate,bands,evaluator,settings,store}.py`, `ltcm/data/`,
    `scripts/data/`), `deploy/` and `league/config.json`.
- **The budget only ever tightens.** Research is computed from realized profit only; marks never fund research; nothing
  in the rule tops anything up, raises a cap or moves money. The owner pays; the desk asks only when a prefund is short.
- **The standing grant never loosens.** It ratifies only after an owner deploy that moved the money digest or after a
  deposit landed; never above the lower of equity and the owner's ceiling, never a revoked grant. `--disable` stays the
  owner's stop.
- **The site is the owner's:** no commit, no deploy, no contract change from here.

## How it is observed

The House writes a private receipts file every ten minutes; the operator reads it through the Sail Files API with
`scripts/desk_receipts.py` (a GET of one file, never an exec). The public record is the daily scoreboard below.
[Operations](../operations.md) ("LTCM v3: release V3-A") has the jobs, the settings layers, the deploy classes and the
drill.

## Scoreboard

From V3-A's deploy, the House's `scoreboard` job (daily 23:30 UTC) commits one public-safe page a day to
[`docs/runs/desk/`](desk/README.md) as `<YYYY-MM-DD>.md`, through the gateway's docs route: the running release,
self-deploys and self-rollbacks, real closes and realized options P&L (since T0 and trailing 30 days), input costs by
service since T0, the one Net, open lots at conservative marks, the budget's state and the next card action date per
meter, the ladder's counts, and the day's jobs. It never carries account equity or balances, quotes, contract symbols,
strikes, parameters, program text, or Validation or holdout figures; a page that fails the filter is not posted.

No daily page has been posted yet: V3-A is not deployed.
