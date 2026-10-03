# The unattended desk (LTCM v3): October 2, 2026

This continues the options swarm's run from T0 `2026-09-26T06:23:14Z` and its financial reset; neither resets. The
previous record is [the continuous-learning run](2026-09-30-continuous-learning.md) (Sept 30-Oct 2). The goal is **not
achieved**. All times are UTC. Private details (account figures, prices, strikes, programs, parameters, operator tools)
stay in the operator's goal folder.

**State at the end of Oct 2: v3 is built on branches and not deployed. The project runs on autopilot on the Oct 2
release, with research cut to a funded floor.**

## Why v3

On Oct 2 the owner asked for a deep dive into why the project showed no progress, and for a swarm that runs with no
human in the loop. A read of the repository and the operator records and a 20-minute watch of the swarm in session
gave a plain answer: the machine ran continuously and honestly, and it was a treadmill. Since the Sept 26 reset the
swarm had born and retired more than 2,300 families and counted more than 100,000 trials; it had made 3 holdout looks
and passed none, and no family had ever become a Candidate. In the watch, the researchers' notes were about the
harness, not about markets, and real money did only what the House itself scheduled. The causes, ranked:

1. **The verifier was built for a fund.** At one contract a structure, a sealed-holdout pass needs a net edge per
   structure larger than the documented retail options premia carry after one-lot costs. A real edge would pass a look
   rarely, the first qualified family was weeks to months away, and at Probe size it would earn far less a day than
   research cost. No engineering on those rules changes that arithmetic.
2. **Research made noise, not knowledge.** The cheapest model rewrote each family's program dozens of times an hour,
   families refuted themselves in about an hour (the median), and the Validation passes so far had mostly measured
   long-market drift. The graveyard's lessons were barely read.
3. **The owner was the control plane.** The in-box updater existed and was switched off. Every deploy, ratification,
   settings change, agenda, cohort end, economics report and top-up was a command from the owner's laptop: 37 distinct
   human steps, 23 of them with no automatic path at all.
4. **The cost base could not close at this capital.** The fixed costs (market data, ThetaData, the boxes) were a large
   monthly share of a small account before any research, and the design's "compute drops to its floor when the forward
   record does not pay for it" was written nowhere in code.
5. **The sealed holdout taxed the loop.** The 2026 holdout is not sealed against the models' own memory, and every look
   raises the bar for every later look. The one judge no model has seen, the forward record on live quotes, was "never
   evidence" and was capped by a one-vCPU House.
6. **Fragility needed hands:** Sail queue stalls, failed Gym boxes, an out-of-memory House, session times hard-coded in
   UTC that move on Nov 1, three funding meters to watch, a vendor renewal.

The v3 answer: a desk that costs almost nothing while it has no forward edge, spends more only out of what it earned,
deploys and repairs itself inside walls the owner keeps, judges programs on the forward record, and reports itself
every day.

The counts behind it, at the watch: 2,370 families born and 2,349 retired in the six days since the Sept 26 reset
(mean life about 3 hours); 105,273 trials; 3 holdout looks, 0 passes; 0 Candidates ever.

## The owner's decisions (Oct 2, about 17:00)

- **D1, capital:** stays as it is. The desk never deposits; capital is the owner's transfer.
- **D2, evidence:** yes to the forward ladder (practice shadow, then Probe, then Sized, under a pre-registered
  multiple-testing control) as the way to real money once it is benchmarked; the 2026 holdout becomes a free pre-filter.
- **D3, structures:** yes to defined-risk short premium (credit verticals, iron condors, iron butterflies) on real money
  at $2,000 of equity or more, in one deploy with the gateway's list and the grant.
- **D4, funding:** research is funded by a rule on trailing realized options profit, inside the prefunded meters, with a
  small floor.
- **D5, autonomy:** self-deploy with walls: the in-box updater on, the engineer's research-class pull requests merged on
  green CI and an automated adversarial review, protected paths still the owner's own deploy, and a standing grant.
- **D6, data:** ThetaData Options Standard is kept until the ladder is live, then decided on the numbers.

## The plan, by phase

| Phase | What | State at A1 |
|---|---|---|
| 0 | Stop the treadmill: research to the floor, stale cohorts ended, a baseline economics | done Oct 2 (below) |
| 1 | The autonomy core: self-deploy, the operator's scripts as House jobs, funding without hands, the standing grant, calendar-driven times, monthly failure drills | **A1** |
| 2 | Research v3: fewer, stronger researchers; hypotheses from documented premia; the strategist owns the agenda; credit types in the Gym and the shadow book | built on branches, not deployed |
| 3 | Evidence v3: the forward ladder, benchmarked before it binds | built, does not bind; a confirmation study decides |
| 4 | Recursive harness improvement: an engineer, an automated reviewer, the updater's canary, retain or revert by a predeclared metric | the gateway's walls in A1; the engineer built, not deployed |
| 5 | The economics autopilot: the daily page, the budget rule, the weekly post-mortem | the page and the budget in A1; the post-mortem built, not deployed |

The plan's measure of done, in plain words: 30 consecutive days in which no command from the owner's machine touched
production, with self-deployed releases and at least one self-rollback; research that followed realized profit both
ways with no top-up asked for; at least one program promoted to real money by the forward ladder, or the daily page
saying honestly that none qualified, with the counts; harness changes retained end to end with no human step; and a
one-cutoff economics with Net positive, or the desk throttled to its floor by its own rule and saying why. A deploy, a
backtest, practice profits or a finished checklist are not done.

## Before A1: the floor and the baseline (Oct 2 afternoon; no deploy)

- **17:04 and 17:23, research to the floor** (`swarm.json`, before-copies kept): `population.start` 96 → 16,
  `population.floor` 12 → 8, `architect.every_seconds` 1800 → 7200, `researcher.sail_usd_per_hour` 1.3 → 0.25,
  `gym.max_boxes` 6 → 1, `strategist.every_seconds` unset → 86400. Calibration, the House live test, the incubator and
  the practice league kept running.
- **19:03, the operator's last sweeps by hand** (practice only, no real money): three practice cohorts ended (the two
  GOOGL-lineage cohorts, whose programs failed their holdout look and are barred from the incubator, and one whose SPXW
  chain read failed every minute), and six Gym pool rows stuck at `failed` were marked `terminated` (Sail listed none of
  their boxes).
- **Settings as code:** the research settings, from a copy of the box's `swarm.json` taken at 21:00, went into the
  repository's `league/swarm/policy.json` unchanged, without the private agenda text and without the retired burst keys.
- **The baseline**, at the Oct 2 close (20:00 cutoff, one cutoff for everything): realized options P&L −$40.63 (the
  House's calibration round trips and regulatory fees; no strategy route closed a trade), input costs $607.88, so **Net
  since the Sept 26 reset is −$648.51**. One tuition lot is still open and is not in the realized figure; at
  conservative marks it is a further loss.

## What A1 ships

V3-A was split on Oct 2 to move faster. Part 1 (A1) is everything that must be the owner's own deploy for the desk to
run unattended and that is reviewed: the House's jobs, the budget rule, the standing grant, the updater switched on with
its walls hardened, the live-path fixes and the gateway. Part 2 (the forward ladder and the credit types) ships later,
in its own owner deploy, only once it meets its bars (below).

### The House's own jobs (`league/ops/`)

The operator's daily scripts became jobs on the House's own clock. The schedule reads the House's NYSE calendar
(`ltcm.data.us_equity_session`), so "an hour before the open" follows daylight saving and early closes; the fixed UTC
times sit outside every session in both seasons. Each due job runs as one child process at a time (`python -m
league.ops run <job>`): niced to 19, its address space capped at what it starts with plus 500 MB, its CPU time and wall
time bounded, with a scrubbed environment. Every occurrence gets one receipt row in `<state>/ops.sqlite` (`ok`,
`failed`, `missed` or `skipped`); a failed run is retried inside its grace (at most three attempts), and a missed one is
a House warning. `health.json` carries an `ops` block (today's jobs: due, late, failed, missed, running).

| Job | When | What it does |
|---|---|---|
| `grant` | at each House start, and hourly | the standing grant (below) |
| `budget` | after the close economics, and daily at 00:30 | the budget rule (below) and its funding notices |
| `hygiene` | daily at 02:00, never within 30 minutes of a session | ends practice cohorts of programs barred from the incubator, settles dead Gym pool rows against Sail, runs the tournament's idle rule (never below the floor), reports stale live instances |
| `clock` | daily at 11:00 | Alpaca's clock and calendar against the House's calendar for the next 10 sessions; a mismatch is a warning |
| `preopen` | trading days, an hour before the open | the operator's nine pre-open checks, read-only; each FAIL is a House warning |
| `economics` | trading days, ten minutes after the close | the one-cutoff close economics (realized options P&L, every input cost, open lots at conservative marks, Net, and the trailing 30-day realized P&L the budget reads); private |
| `scoreboard` | daily at 23:30 | the desk's public page (below) |
| `drills` | the first Saturday of each month, 15:00 and 17:00 | a test funding notice, a failed Sail read, a gateway outage, a killed swarm, and the rollback drill; each must recover without a human |
| `postmortem`, `agenda`, `engineer` | weekly; daily; daily | registry entries only: their modules are not in A1, so each occurrence is a `skipped` receipt that says so |

### The budget rule (`league/ops/budget.py`, protected)

Research spends from a rule, not from settings. For each meter (Sail and Claude) the rule reads the balance, the fixed
cost a day (Sail: the House box's and the data box's own billing) and a reserve that is never spent, and computes:

- what the balance sustains for **R = 90 days** above the reserve and the fixed cost, capped by a **floor of $5 a day**
  for both meters together (60% Sail, 40% Claude);
- plus **half of the trailing 30-day realized options P&L**, when it is positive, shared by need. Marks never fund
  research;
- never more than keeps the meter above **W = 60 days** of runway (the card line).

After 60 sessions from Oct 5 with no promotion to Probe, the profit share stops ("no forward edge; research at floor")
until a promotion. Unknown is never money: an unreadable balance gives its meter no research, and an unreadable profit
earns nothing. The result (`<state>/budget.json`, private) is applied **only to tighten**: it caps the researcher's Sail
pace, the Gym boxes, every Claude role's daily line and the population ceiling, and slows the architect. A missing
budget is the floor, a stale one never loosens, and a rule that cannot run spends nothing. The Sail guard's daily cap is
now the budget's, so the research burst and its three settings are gone. When a meter's runway falls under 60 days the
House mails the owner one `funding` notice with the amount that restores 90 days, at most once a week a meter. The rule
moves no money and raises no cap: the owner pays. OpenAI is not a meter of the rule, so the overlay closes it.

### Settings as code

The research settings now live in the repository, in `league/swarm/policy.json`: a reviewed pull request changes them,
and the updater deploys them. The layers, each over the last: the code's defaults, `league/config.json`, `policy.json`,
the box's `<state>/swarm.json`, and last the budget, tighten-only. `swarm.json` keeps the owner's switches (`enabled`,
`live`) and the private agenda text, which a public repository must not hold.

### The standing grant

The owner used to ratify the grant by hand after every deploy that moved the money digest and after every deposit. The
`grant` job (`league/ops/grant.py` and `LiveGrant.standing` in `league/live_trading.py`, both protected) now ratifies
it in exactly those two cases: the money digest moved and an owner's release change is on the deploy record since the
last ratification, or a deposit landed (told by its id). Capital stays the lower of equity and the owner's ceiling. It
never creates, enables or re-enables a grant, never raises the ceiling without the owner's deploy, and refuses, changing
nothing, when anything is unreadable. `--disable` stays the owner's stop. A1 does not change the money rules, so the
money digest stays `42c4a3af` and this deploy needs no ratification for it (the job's first run may still answer an
earlier deposit once more, at the same capital rule: its record of seen deposits starts empty).

### Self-deploy, inside walls

`league/config.json` turns `auto_update` on. Every half hour the House reads main's head and deploys that exact commit
only when every wall holds: GitHub's Checks workflow passed on that exact commit (every required job); no file the
running release protects changes (`league/ci.py` FORBIDDEN, now also `league/ops/{budget,grant,drills}.py`) and the
workflows are the pinned ones; the running release's own content checks pass; `real_money` does not change; at most one
release every four hours, none from 12:55 to 20:05 on a trading day (13:55-21:05 in winter) or within 30 minutes of a
House start; then the watchdog's canary, promotion, ten-minute watch and automatic rollback. A1 adds:

- the nightly forward daemon is stopped while it is idle before the launch, with a marker (`updater:<release>`) that is
  removed only by whoever wrote it, and a House start removes an orphaned one;
- one deploy at a time: the updater writes `deploy.pid`, so the owner's `floor_box.py deploy` refuses beside it, and
  the updater waits for any watchdog in flight;
- the harness observer follows a release the updater deployed (its attested commit); an owner deploy still needs its
  policy re-pointed by hand;
- the rollback drill, `python -m league.watchdog drill-rollback`: a copy of the running release carrying `DRILL_BREAK`
  is deployed, the House it starts raises an error every tick, and the watch must roll it back by itself. It refuses in
  the session window and beside another deploy, and the House it leaves recovers it if the drill's own process dies.

A merge to main that touches only `docs/` changes no release: the release trees are `league/`, `ltcm/`, `scripts/`,
`deploy/` and `playbooks/`.

### The live-path fixes (evidence reset 3)

`league/live/` changes, so the evaluator's execution fingerprint moves (`47587e22…` → `ba60c473…`): at its first start
the swarm archives every family's derived selection evidence and the practice cohorts complete, as at Release B. Trials,
lineages and consumed holdout looks are kept; the Gym's image and bundle do not change. The fixes:

- **Exit-only instances** drop their program's opens silently before the order path (counted as
  `exit_only_opens_dropped`), instead of a refusal every 30 minutes.
- **Practice reads are clamped to what the Gym's store holds**: 40 strikes a side for SPXW and 25 for other roots, at
  most 14 days to expiry (45 for SPY and QQQ). A chain over the page cap is read again narrower rather than lost (the
  SPXW read had failed every minute).
- **Practice accounts hold what a Probe may**, scaled to their shadow capital: at most three structures open or working,
  each open sized to the Probe's share of capital, the whole account within the Probe's family cap. An open over its
  size is resized; one with no room is a recorded practice refusal, never a program error. (One practice program had
  held 33 shadow positions.)
- **An honest shed:** only a practice read skipped for the read budget counts as pressure, and the budget is 120 calls a
  minute (it was 40), room for 24 roots at the page cap.

### The gateway

- `POST /v1/github/docs`: one page committed to main under `docs/runs/desk/<date>.md` (64 KB at most, six a New York
  day, no credential-shaped text).
- The engineer's routes: `POST /v1/github/pr` with role `engineer` (a lane, its own files only, two a day),
  `POST /v1/github/review` (an automated reviewer's verdict on an exact commit), `POST /v1/github/merge` (a squash merge
  only of an `engineer/<lane>/` branch, on green checks on that exact commit, with a recorded approve, no protected
  path, every file inside its lane, two a day; the kill switch stops merges), and read and close routes. Nothing calls
  them yet (the engineer is parked).
- A `funding` notice kind on `/v1/notify`; an admin log (every kill, unkill and admin-token call) in `/v1/health`; the
  kill switch now engages with either token; Sail's low and critical balance mails at $25 and $12, under the budget
  rule's own floor, so the rule's notice is the one that asks for a card.

### Smaller fixes

- Gym pool rows settle against Sail's own list, so a `failed` row no longer sits for days.
- A one-shot model call on Sail's balanced queue that times out is asked again on the asap queue, and that queue's
  calls go straight there for an hour (on Oct 2 the architect bore nothing for six hours while the balanced queue was
  silent). The gate's audit keeps its own model on the fallback, so the review and the audit stay two different readers.

## What is parked, and why

Built or building on branches, **not deployed**:

- **The forward ladder** (`v3/wp6`): practice shadow, then Probe, then Sized, on the forward record under a
  pre-registered control, with its benchmark. It does not bind (see below). A confirmation study is running on
  `v3/wp6b`.
- **Credit types at $2,000 of equity or more, and a paper proof per type** (`v3/wp7`). The gateway's list of real types
  stays the four debit types in A1, equal to the constitution's.
- **Research v3** (`v3/b1`): researchers on Claude Sonnet 5.5, each cycle a sweep of variants with a mandatory placebo
  row, and a per-family ledger of what was tried and why it failed.
- **Births v3 and the strategist's whole agenda** (`v3/b23`): families only from a curated library of documented premia,
  the Train kill tests as code, and the agenda written by the strategist alone.
- **The weekly post-mortem** (`v3/b4`) and **the engineer and reviewer loop** (`v3/b5`).

The research-class branches ship through the updater once they are reviewed and merged. The ladder and the credit types
change `league/live/` and the constitution, so they are an owner deploy, with one more evidence reset. Until the ladder
binds, A1 keeps the sealed-holdout gate, the look rules and execution tuition exactly as they were: D2 retires them only
with the ladder.

**The ladder's benchmark, honestly.** Synthetic forward streams with known answers (no edge, a cost-erased edge,
drift only, a fading edge, planted edges, and mixed desks) were played through the practice ledger and the new rules,
and through the sealed-look design on the same worlds. On the development cohort (30 replications a world) the ladder
as specified did better where the sealed look is weakest: it promoted about 3-4% of fading and cost-erased programs,
where the sealed look promoted about a fifth to a quarter, and in the mixed desk it missed far fewer real edges (about
36% against 62%). But it promoted about 4-8% of pure-noise, skewed-null and drift-only programs, where the sealed look
promoted almost none. The rule written before the build was that the ladder binds only when its false promotions are at
or below the sealed look's on the same worlds. It does not meet that, so when it ships it ships with `binding` false: it
records what it would promote and promotes nothing. These are development figures, not the verdict. Before any
confirmation run, the captain pre-registered when the ladder may bind: a design chosen on the development cohort must
then pass, on a fresh-seed confirmation cohort with at least 30 replications of every world, (1) a false-promotion rate
of at most 1.0% in every negative world, not significantly above the sealed look's there (one-sided Fisher exact test,
p ≥ 0.05); (2) pooled false promotions at or below the sealed look's; and (3) missed signals in the mixed desk at or
below the sealed look's. If no design passes, `binding` stays false and the daily page says so with the counts.

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

## The walls

What the desk may not do by itself. The release, merge, money and public-text walls are code; the rest are rules every
change is reviewed against.

- **The owner's deploy only:** the files `league/ci.py` lists as FORBIDDEN: the constitution (the money rules), the
  ledger and the book, `league/live/` and the grant, the watchdog, the updater and `ci.py` itself, the gateway and the
  workflows, and from A1 the budget rule, the standing grant and the drills. The updater refuses any main head that
  changes one of them. The gateway's merge route refuses a wider list for the engineer: those, plus `league/gym/`, the
  swarm's gate, bands, evaluator, settings and store, `ltcm/data/`, `scripts/data/`, `deploy/` and `league/config.json`.
- **Money:** no deposit, transfer or borrowing; no cap above funded money. The budget only tightens; the grant only
  ratifies on an owner's deploy or a landed deposit, never above the lower of equity and the owner's ceiling. The kill
  switch engages with either token and releases only with the owner's.
- **Releases:** exact-commit CI, the release train, the session hold, one deploy at a time, canary and automatic
  rollback; a head rolled back twice is never tried again.
- **Merges** (when the engineer ships): `engineer/` branches only, inside their lane's files, green checks on the exact
  commit, a recorded approve, two a day, none while the kill switch is on.
- **Public text:** the daily page is built from an allowlist of figures and refused if it names equity, a balance, a
  quote, a strike, a contract, a parameter, program text, or a Validation or holdout figure.
- **The site** is the owner's; nothing here changes it or its data contracts.

## How the desk reports itself

- **Every day at 23:30**, the House commits a public page to [`docs/runs/desk/`](desk/README.md) through the gateway:
  the running release; self-deploys, self-rollbacks, owner deploys and drills; realized options P&L since the reset and
  over 30 days; input costs by service; Net; open lots at conservative marks; the budget's state and the next card date
  per meter; the ladder's counts; the day's jobs.
- **Every ten minutes**, the House rewrites a private receipts file, which the owner reads without touching the box
  (`scripts/desk_receipts.py`, a Files API read; never an exec).
- **By mail**, through the gateway: a `funding` notice when a meter's runway falls under 60 days, and the existing
  `live_stop` notice when a real-money stop trips.
- `/v1/health` on the gateway shows the admin log and the desk's docs commits and merges.

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

## The deploy

A1 is the owner's deploy, outside the session: the gateway first (the running House never calls its new routes, and
the new House tolerates them absent), then the House with the nightly daemon stopped, then the checks in
[operations](../operations.md) ("Now: V3-A part 1"). The box keeps its full `swarm.json` until the release after A1, so
that a rollback finds the settings it needs.
The release id, times and checks are recorded in the [CHANGELOG](../../CHANGELOG.md) entry "V3-A part 1".

## Scoreboard (Oct 2 close)

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
| Real money through evidence | none: no program has passed the holdout (3 looks, 0 passes) and the forward ladder does not bind |
| The House's own real orders | D3 calibration round trips (23 closed by the Oct 2 close); one exit-only tuition lot open; the House live test, no round trip yet; the incubator, no lot |
| Research | at a funded floor; under A1 the budget rule's floor: no realized profit to share, and the meters' balances bound it further |
| Evidence resets | 2 (Release A, Release B); A1 is the third when it deploys |

No program trades real money through evidence yet, and Net is negative. The goal remains unmet.

## Next

- **The first night under A1:** the `grant` receipt at start (no digest ratification due), the `budget` job at 00:30 (its
  `budget.json` at the floor), `hygiene` at 02:00, `clock` at 11:00.
- **Saturday Oct 3 is the first Saturday of the month**, so the monthly drills are due at 15:00 and 17:00: a test
  funding mail to the owner, a killed swarm that must come back, and the rollback drill (two House restarts).
- **The first daily page** at 23:30 on Oct 3. It has no close economics until the House's own `economics` job runs at a
  close (the first is Monday Oct 5's).
- **Monday Oct 5:** the `preopen` job an hour before the open; the first session on the new evaluator; the no-forward-edge
  count starts.
- **The ladder's confirmation study,** then the research-class branches through review and the updater.
