# Changelog

One entry per deploy, newest first, from the options overhaul of Sept 26, 2026 on. Earlier history is
in [archive/](archive/README.md).

Each entry: the UTC time; what was deployed (House release id and main commit, gateway version, or
site version); the pull requests it carries; the money digest and when the grant was ratified, if
it moved; what was verified on the box, and how; and the rollback floor when it changes. A merged
pull request is not an entry until it is deployed.

## Rollback floor

`20260926T084913Z-8158a11cfe3f` (main `b68b3800`, promoted 08:49:50Z Sept 26), the first House release
on the new state root: never roll back past it, because the release before it (Deploy G,
`20260926T032739Z-aaf5ac74637c`) would run the old Kalshi and Jev code on the new root. With real money
on, a rollback also has the real-book and structures guards of [docs/operations.md](docs/operations.md).

Operator changes that are not deploys (`swarm.json`, image adoptions, grant ratifications) are listed
beside the deploys of their day, marked "no deploy". The run records have the detail: to Sept 29,
`docs/runs/2026-09-26-options-swarm.md` on branch `run/options-swarm-2026-09-26`; Sept 30-Oct 2,
[docs/runs/2026-09-30-continuous-learning.md](docs/runs/2026-09-30-continuous-learning.md); from Oct 2,
[docs/runs/2026-10-02-unattended-desk.md](docs/runs/2026-10-02-unattended-desk.md). From the V3-A part 1 deploy the
House also deploys main by itself (the updater): its daily pages in [docs/runs/desk/](docs/runs/desk/README.md) count
its self-deploys and self-rollbacks, and they get entries here like any other deploy.

## Not yet deployed

The running House release is `20261002T112610Z-e11710692569` (main `e3d0111f`, 11:26Z Oct 2, below), and the box's
updater is off. Until PR #489 merges, main is ahead of it by docs, by comment-only edits (the Oct 2 pause refresh: no
behaviour change, verified by an AST comparison) and by a prune of dead files from the Kalshi era and the first run
(`scripts/jev_lab_eval/`, `scripts/{attribute_fills,repair_leg_fills,repair_no_fills,survey_kalshi}.py`,
`deploy/ltcm.service` and `league/FEEDS.md`: nothing imports or runs them, and they stay readable at tag
`archive/pre-options-2026-09-26`). Those paths are in the release bundle, and the comment edits touch modules the live
path loads, so the next House release from main deploys in the money path's window (20:05-13:25Z); the money digest
does not move. Once PR #489 merges, main's head is V3-A part 1 (below) as well, which the running release, its updater
off, does not take until the owner's deploy.

### V3-A part 1: built and integrated, waiting for the owner's deploy (`release/v3a`, PR #489)

LTCM v3's first release, the one that lets the desk run unattended
([the run record](docs/runs/2026-10-02-unattended-desk.md) has the why and the owner's six decisions). It is **not
deployed**: this is what the release contains, and its deploy's record goes at the end of this entry. It carries
WP1-WP5, WP8, WP8b and WP9 with their review fixes, the four integration lenses (ops, money, deploy, contract), the
settings migration, the fixes for the causes of the integrated head's CI failures, main (the dead-file prune above) and
this docs pass. It moves the evaluator's fingerprint and carries money-path changes, so it ships only by a planned owner
deploy outside a session.

Money digest `42c4a3af`, unchanged (the constitution is untouched, `digest()` equals `PINNED_DIGEST`): no digest
ratification. **Evidence reset 3** at the deploy: `league/live/` changes, so the execution fingerprint moves
`47587e22…` → `ba60c473…`; the Gym's image and bundle are unchanged. Every practice cohort ends, and a
(family, version) that had a cohort does not practise again: practice refills only from new versions. The forward
ladder and the credit types are not in it (below).

- **WP1, the updater and deploys** (`league/updater.py`, `league/watchdog.py`, `scripts/floor_box.py`,
  `league/config.json`, `league/ci.py`, `league/house.py`, `league/swarm/harness_runtime.py`): `auto_update` true
  (`release_train_hours` 4); before a launch the updater stops the nightly daemon once it is idle, with an `updater:`
  marker that only its writer removes (a House start removes an orphaned one); its watchdog's pid in `deploy.pid`, so
  `floor_box.py deploy` refuses beside it and the updater waits for any watchdog in flight; `push_release` clears only
  its own `incoming/<id>/`, and the updater sweeps its own stale trees; the harness observer follows a release the
  updater attested; a scrubbed watchdog environment; `python -m league.watchdog drill-rollback` and `drill-recover`.
- **WP2, the House's jobs** (`league/ops/`, new; `scripts/desk_receipts.py`): the scheduler on the House's NYSE calendar,
  the registry and the runner (one niced, bounded child at a time; retries inside the grace; missed occurrences a
  warning; public alerts scrubbed of box ids and dollar figures), receipts in `<state>/ops.sqlite` and the private
  receipts file every ten minutes, `health.json` `ops`. Jobs: `grant` (start, hourly), `budget` (after the economics,
  00:30Z), `hygiene` (02:00Z), `clock` (11:00Z), `preopen` (open − 60 min), `economics` (close + 10 min, with `p30`),
  `scoreboard` (23:30Z, public, through the gateway), `drills` (first Saturday, 15:00Z and 17:00Z); `postmortem`,
  `agenda` and `engineer` are registered and skipped while their modules are absent. A maintenance pause holds the jobs
  that write records, post or spend.
- **WP3, the budget rule** (`league/ops/budget.py`; `league/swarm/{settings,guard,models,funding}.py`; all protected):
  research dollars a day per meter from the prefunded balances (R 90 days, W 60 days, a $5 floor split 60/40
  Sail/Claude, half of the trailing 30-day realized options P&L, a no-forward-edge stop after 60 sessions from Oct 5),
  applied tighten-only to the spend knobs, fail-closed; `budget.json` private. The Sail guard's daily cap is the
  budget's: the burst trio (`guard.burst_cap_usd`, `burst_until`, `after_burst_usd_day`) and the `burst_end` funding
  cliff are gone. Claude's room is also capped by the budget's Claude dollars today; OpenAI is closed. `funding`
  notices by mail.
- **WP4, the standing grant** (`league/live_trading.py` `LiveGrant.standing`, `league/ops/grant.py`; protected):
  ratifies on a money digest moved by an owner's release change, or on a landed deposit (by its id); never enables,
  never touches a revoked grant, never above the lower of equity and the ceiling.
- **WP5, live fixes** (`league/live/step.py`, `league/live/shadow.py`): exit-only instances drop opens silently
  (`exit_only_opens_dropped`); practice reads clamped to the Gym store's window and narrowed rather than lost over the
  page cap; practice accounts capped as a Probe (`practice_sized`, practice refusals); only read-budget skips are
  practice pressure, and `live.observe_read_calls` defaults to 120 (was 40).
- **WP8 and WP8b, the gateway** (`gateway/`): `POST /v1/github/docs`; the engineer's `pr` role with lanes, `review`,
  `merge` (stopped by the kill switch), `close` and `pr/<n>/files`; `league/ci.py` `ENGINEER_LANES`; the `funding`
  notice kind; the admin log and `autonomy` in `/v1/health`; `/v1/kill` takes either token; `LOW_BALANCE_USD` 60 → 25
  and `CRITICAL_BALANCE_USD` 20 → 12. `OPTION_STRUCTURES_REAL` unchanged: the credit types were reverted on the release
  until WP7.
- **WP9, fixes and settings as code** (`league/swarm/{pool,models,settings,gate,loop}.py`, `league/swarm/policy.json`,
  `scripts/settings_migrate.py`, `scripts/verify_swarm.py`): pool rows settled against Sail's list; the balanced-to-asap
  window fallback (`sail_fallback`, the audit keeping its own model); the one-reader check by model across Sail
  profiles; the heartbeat names the families in a cycle (hygiene spares them); the `policy.json` layer
  (DEFAULTS < `config.json` < `policy.json` < `<state>/swarm.json` < `<state>/budget.json`, tighten-only), holding the
  box's research settings as of 21:00Z Oct 2 unchanged, without the private agenda and the burst keys.

**The integration changes** (the review lenses, the merge reviews and the CI-cause fixes; Oct 2-3):
- **One protected list, and a wider one.** `league/ci.py` `FORBIDDEN` is the union with the gateway's merge list: 86
  files and trees (35 on main), where the two lists differ only by `league/config.json` (tests on both sides hold them
  to that). New on it: `league/house.py`, all of `league/ops/`, `scripts/floor_box.py`, `deploy/`,
  `league/swarm/policy.json`, `league/swarm/{settings,guard,models,funding}.py`, `league/gym/`,
  `league/swarm/{gate,bands,evaluator,store,evidence,tournament}.py`, the structure core, `ltcm/data/`, `scripts/data/`
  and the harness loop's own objective. A change to any entry inside the release trees (`league/`, `ltcm/`,
  `playbooks/`, `scripts/`, `deploy/`) is the owner's deploy; the updater refuses it, and every later head with it.
  Five entries are outside those trees and never reach the box (`gateway/`, `.github/`, `CHANGELOG.md`, `docs/goals/`,
  `docs/benchmarks/`): the list holds the roles and the gateway's merge route there, the updater neither refuses nor
  ships a change to them, and a merge that changes only those is no release and holds nothing. The gateway ships only
  by wrangler, so a House change that needs a gateway change is merged after that gateway change is deployed; the
  workflows are held by the updater's pin.
- **`policy.json` is no longer delivered by the updater.** A merged change to it reaches the box by the owner's deploy,
  or the box's `swarm.json`, which wins over it, is edited instead. Research-class work that touches any protected file
  is an owner deploy.
- **The engineer's lanes.** The gateway holds the engineer to the paths the harness lanes declare: it refuses
  `league/swarm/loop.py` and `league/swarm/mechanisms.py`, so the scheduler lane admits new candidate tests only until
  an owner deploy opens them. A candidate test's name is bounded on both sides; an engineer proposal names the commit
  it was written against; the kill switch stops merges.
- **The budget rule as merged.** `p30` is the live book's own read first, and the close economics can only cut it;
  unknown stays unknown (nothing earned, and a warning); with no close summary yet each budget run warns; a missing
  `budget.json` is the floor and a stale one never loosens; the overlay also holds `population.start` to the ceiling
  and the architect's refill to its cadence; the ceiling never falls under `population.floor` + 4; OpenAI is closed;
  the paid-model line counts each model's spend on its own, on the day its hold was booked; a budget room that cannot
  be read refuses the call.
- **The funding notice** is computed at the rate the meter wants, so a throttled desk still says when a card is
  needed, and it carries the current rate beside it: the rate the rule holds the meter to now (its fixed cost plus the
  day's research budget), not a metered spend. The gateway's mail names both rates, says each runway as days above the
  meter's reserve, and says that nothing stops without a card only when the figures sent show it; otherwise it says how
  long the meter lasts at the rate it is held to now. Sail's low and critical balance mails sit under the rule's own
  floor.
- **The jobs.** A failed run is retried after 15 minutes inside its grace, at most three attempts; a job that reports
  its own failure gets a `failed` receipt; the rollback drill is requested by the `drills` job and launched by the
  updater in the House's own process; a maintenance pause holds the jobs that write, post or spend; the House box's id
  is read from the release's pin first.
- **The pre-open job's check 5** passes when the Sail guard is braked only by the budget's own daily caps with a fresh
  balance above the line. The guard names its brake's causes and the check reads the names; any other cause (a budget
  rule that could not be read among them), or none named, is a FAIL.
- **Tests.** The league's tests read an empty policy layer; the committed `policy.json` is judged in one place, by
  value and by the House's own loop; fixtures that route to Claude state the budget they need; the House is held to
  never importing `league.tests`.
- **Docs:** [the run record](docs/runs/2026-10-02-unattended-desk.md), [docs/runs/desk/](docs/runs/desk/README.md),
  operations (**Now**, **Running unattended**, the release checklist, **Roll back**), design and README.

**The deploy's record** (to be filled in at the deploy; the entry then moves under its date with the heading
"`<time>`Z, House release `<release id>` (main `<commit>`), gateway `<gateway version>`"; writing it is a docs-only
merge by hand, which changes no release, holds nothing and needs no deploy):
- the tree: main's commit, the CI run on it, the tree digest equal on both paths;
- the gateway first: its version, `/v1/health` with `admin_log` and `autonomy`, the vars read from the version;
- the House: the nightly daemon stopped idle; staged, promoted and the watch's verdict; the full `swarm.json` kept on
  the box;
- the checks: the evaluator adopted (reset 3) with trials, lineages and looks unchanged; the first `grant` receipt;
  `ops` in `health.json`; `budget.json` written or the floor in force; the updater built with no head pending;
- criterion 1 (a restart and a killed swarm) on the new release.

### On branches, not in V3-A part 1

- `v3/wp6`, the forward ladder and its benchmark (evidence v3, the owner's D2). As first specified it does not meet its
  benchmark rule. A tighter design was frozen before any confirmation run; the confirmation, under a rule
  pre-registered before it, has not been run. It changes `league/live/` and the constitution: an owner deploy and one
  more evidence reset.
- `v3/wp7`, credit types at $2,000 of equity or more and a paper proof per type (money rules v3, D3), with the
  gateway's credit list: an owner deploy and a money-digest move. With the ladder it is V3-A part 2.
- `v3/b1` (research v3), `v3/b23` (births from the mechanism library, the Train kill tests as code, the strategist's
  whole agenda), `v3/b4` (the weekly post-mortem and the monthly cost review), `v3/b5` (the engineer and the reviewer).
  Each changes a protected file as it stands (`league/swarm/settings.py`, the store, the evidence and tournament
  modules, `league/ops/`), so each is an owner deploy, not an updater release.

## 2026-10-02

### 23:30Z, autopilot (no deploy)

The owner put the project on autopilot. Production stays on `20261002T112610Z-e11710692569`; the box's updater stays
off. The live path trades every session (calibration round trips, the House live test, the incubator, the practice
league in shadow); the swarm researches at the funded floor set below.

### 17:04-21:00Z, research to a funded floor; three cohorts ended; the v3 baseline; settings as code (operator, no deploy)

- 17:04Z and 17:23Z (`swarm.json`, before-copies kept): `population.start` 96 → 16, `population.floor` 12 → 8,
  `architect.every_seconds` 1800 → 7200, `researcher.sail_usd_per_hour` 1.3 → 0.4 → 0.25, `gym.max_boxes` 6 → 2 → 1,
  `strategist.every_seconds` unset → 86400. The swarm had spent about $29 in the 24 hours to the close (Sail models
  $13.04, Sail boxes $3.78, Claude $6.67, plus data vendors pro rata); the floor is about $5 a day of Sail.
- 19:03Z (`observe.sqlite`): practice cohorts ended with an operator reason: `googl-lags-msft-ai-cloud-qqq-flat-r` v1
  and `googl-lags-msft-ai-cloud-qqq-flat--2` v83 (holdout-failed lineage, barred from the incubator) and
  `qqq-exsemis-residual-smh-flat-on-s-2` v1 (its SPXW chain read failed every live minute). Nine cohorts remain.
- 19:03Z (`swarm.sqlite`): the six Gym pool rows in state `failed` marked `terminated` (Sail had ended those boxes
  and listed none of them).
- 20:06Z: the one-cutoff economics at the 20:00Z close, the v3 baseline: realized options P&L -$40.63, input costs
  $607.88, Net -$648.51; with the open tuition lot at its conservative mark, -$772.67.
- 21:00Z: a copy of `swarm.json` became `league/swarm/policy.json` on `release/v3a` (the settings identical, without
  the private agenda and the burst keys). The box's file is unchanged.

### 14:15Z, the pause (no deploy)

- The owner paused active development and chose to keep the swarm running: production runs on
  `20261002T112610Z-e11710692569` with its `swarm.json` unchanged (the continuous-learning run record's "Oct 2:
  pause" has the settings then; `docs/operations.md`, **Now**, has the settings in effect today). Not applied: the next
  agenda (v17), a change to the architect's cadence and spend, and ending the two GOOGL-lineage practice cohorts by
  hand. Work resumed about 17:00Z on the v3 plan (above).

### 11:26Z, House release `20261002T112610Z-e11710692569` (main `e3d0111f`; PRs #484, #481)

- **The look holds** (L6(b) and L6(c), branch `gate/l6-look-holds`; `league/swarm/gate.py`, `league/swarm/evidence.py`,
  `league/swarm/store.py`, `league/swarm/settings.py`, `league/swarm/bands.py` (the House's reader),
  `league/swarm/incubator.py`, `league/CONTRACT.md`, `scripts/verify_swarm.py`, `scripts/look_holds_benchmark.py`; the
  money path as the duplicate look's: 20:05-13:25Z only, after two adversarial reviews and green CI; the House and the
  swarm deploy together). The owner approved them on Oct 2 (~02:55Z) as a tightening, on the condition of
  fixed-benchmark proof that false promotions do not rise and a report of the missed-signal cost. Every holdout look
  raises the Holm bar for every later one; the three looks since the Sept 26 reset were all long-delta programs and all
  failed, and a 2025 Validation pass has mostly measured long-market drift (the edge study). After the duplicate look,
  the experiment contract, the drift screen and the rations, and before the paid review and audit and the sealed read,
  the gate now HOLDS the look at (b) a long-delta version (pooled Train beta above zero) whose own Train drift fit has
  drift share |drift| / (|alpha| + |drift|) of at least 0.25, or (c) a version whose expected holdout power is below
  0.30: the normal approximation of the holdout line's one-sided bootstrap test at the level the look would have to
  reach under Holm, with the version's Validation all-days daily Sharpe over the holdout window's 184 sessions. Missing
  figures hold (fail-closed). A held version gets one `look_holds` row (never a `refusals` row), `gated_sha` with
  `gate_ready` cleared, `gate_outcome` "held", words with no figure for the researcher, and a private `swarm.gate` event
  `look_hold` whose `_figures` say why; no look row, no try, no review, no audit, no holdout read. On the money path a
  hold is a failed look: "held" joins `bands.BAD_OUTCOMES` (refused, failed, demoted), so the held version's execution
  tuition ends (`bands.read`) even when the hold lands after a passed review while it waits, and its program is barred
  from the incubator for good (recorded first, as a refusal's bar); without this a held program kept 1-lot real tuition
  for good and could reach an incubator lot that the failed look it replaces would have barred (reviews A1 and B1). A
  new version that clears both is looked at. Settings `gate.look_holds` `{"drift_share": 0.25, "min_power": 0.30}`, on
  by default; each key null turns its hold off, `look_holds` null both (today's gate). Tightening only: no threshold of
  the validation or holdout line, no Holm, deflated-Sharpe or forward rule moves, and on the money path a hold ends what
  a failed look ends; nothing in `league/live`, `league/gym` or `LEAGUE_FILES`, no evaluator adoption, no money digest;
  the store gains one table. The fixed benchmark (`evaluator-suite-1`, #452, development cohort, full protocol, pinned):
  the suite on the branch equals base case for case (`--compare`: comparable, no regression, no improvement; the same
  world rows), and with the holds overlaid on its recorded outcomes (`scripts/look_holds_benchmark.py`, the branch's own
  functions) false promotions stay 16 of 160 (the two memorized-table leaks the review alone stops) and 0 of 896 search
  noise lineages, and missed signals stay 23 of 40 and 269 of 384: no planted signal that reached its look would be held
  (the nearest, one dense world at power 0.297, had already failed Validation), and the drift-only negative, which the
  drift screen stops, would be held in all 8 worlds. The suite's worlds hold no long-drift program that reaches a look,
  so it shows the holds cost nothing there, not what they save. To verify after the deploy: `look_holds` rows and
  `swarm.gate` events with action `look_hold`.
- **The research canary holds half the families for 12 h; the cycle-error floor; outliers sit out** (branch
  `lanes/retention-guard-rule`; `league/swarm/harness_lanes.py`, `playbooks/harness-improvement.md`, new
  `league/tests/test_harness_canary_rules.py`). The lanestats study (Oct 1, operator-only simulation on the 24 h
  capture's per-family tallies, reproducing the base `retention()` on 24 of 24 draws) found the arms canary too thin to
  decide: the research canary (25% of families, 6 h) ended `insufficient_activity` in 93% of windows at the night pace,
  its cycle-error guard's 20% relative tolerance (a tenth of a point at about 0.5% of cycles) could not be resolved, and
  one already-broken family (53 of the capture's 70 cycle errors) decided that guard by the arm its hash fell in. Now
  the research canary holds 50% of families for 12 h; `cycle_error_rate` gets an absolute tolerance of 0.005 like its
  sibling rate guards; a unit that held >= 25% of a lower-is-better check's events in the capture (>= 20 events; an
  event count only, never seconds or dollars, `AMOUNTS`) sits out both arms, chosen before the arms exist;
  `binomial_low` (the memory lane's birth balance) no longer overflows from 1,030 births. Checks are still judged on the
  point estimate. Unchanged: every primary metric, `min_effect`, the primary alpha, every guard (none removed),
  population guards, window lanes. Re-simulated (the #481 review's simulator driving `retention()`; research at 50%/12 h
  with the floor and the exclusion, simulated together; 120 / 240 Train runs an hour; 600-3,000 windows a cell, SE 0.1-2
  points; the old canary is the base code at 25%/6 h on fresh seeds): no effect retained 3.4% / 3.7% (old 0.5% / 3.5%);
  a true 1x benefit 19.2% / 23.6% (old 1.5% / 15.0%); a 2x benefit 40.3% / 45.5% (old 2.2% / 32.8%). A 1x benefit that
  harms one guard by twice its tolerance is retained at most 8.4% / 12.3% (`zero_trade_ok_rate`; old 1.0% / 7.5%): above
  the operator's 10% at 240 an hour, below it at the night pace; the other guards at most 5.6%; with a 2x benefit the
  zero-trade harm 18.5% / 19.3%. A 50% worsening of the zero-tolerance secondary with a 1x benefit: 5.1% / 3.7%. Given
  that the primary passes with no effect, a check still fails in 36% / 33% of windows. The memory lane's 12 h rebirth
  canary: 2.0% with no effect, 6.0% at a true 1x benefit. A bootstrap guard rule (a check fails on a significant
  worsening beyond its tolerance, or when the canary cannot rule out twice it) was tried on the same windows and dropped
  because it did not beat the point estimate: it lowered the worst 2x guard harm at 240 an hour only to 10.1% (not below
  10%), retained a true 1x benefit less often (17.0% / 22.6%; the memory canary 3.3%) and failed a check more often (43%
  / 35% of no-effect windows whose primary passed). Also: the validated-family retire guard and its input closure
  (`Researcher.guarded`, `retire_guard`, `record_verdict` and the helpers they read) join the research lane's frozen
  symbols (the H1 review's finding 5), and a test checks that every frozen symbol resolves. The rule and lane hashes
  move: every registered candidate is re-captured on this release. Research-class (not on the live path). To verify
  after the deploy: `measure` + `rank` on the new release register fresh keys; the research brief's canary reads
  fraction 0.5, 43,200 s.
- **Deploy.** CI green on the combined head; the nightly forward daemon stopped idle first; staged 11:26:23Z, promoted 11:26:54Z
  over `20261002T051530Z-1aebcf26b145`, the watch's verdict PROMOTED. No evidence reset (the evaluator's execution fingerprint
  `47587e22…`, bundle and image unchanged); the money digest unchanged; the open tuition lot exit-only and the 9 practice cohorts
  intact; lineage snapshot diff 0 violations. A deliberate restart at 11:37Z restored every instance, and a killed swarm process
  recovered in 31 seconds.

### Operator changes on Oct 2 (no deploy)

- **03:00-05:26Z:** the owner chose "claims first": `architect.claimable_rows` 4 (05:26Z); `architect.cell_yield` stays null.
- **05:03Z:** `tournament.fork_top` 3 → 0 (no automatic forks of already-validated lineages; the edge study's L7).
- **00:06Z / 06:09Z / 06:51Z / 11:38Z / 11:54Z:** the architect's Claude line 5 → 0 → 5 → 0 → 5 → 0 (Claude's rebirth
  claims failed the card check; then Sail's architect calls timed out from about 07:00Z, 13 passes, no births; the
  Claude architect bore no family in any of its 4 Oct 2 passes, so the line is 0 again from 11:54Z). **11:38Z:**
  `architect.sail_effort` high → medium so the Sail fallback fits its poll window (the cause was not the effort: Sail's
  balanced queue had stopped answering; below).
- **12:28Z / 12:49Z:** `architect.sail_profile` `k3_balanced` (the default) → `pro_balanced` → `pro_asap`. Every
  architect request on Sail's balanced queue since about 07:00Z had sat unanswered until the 15-minute poll gave up
  (`provider_poll_timeout`), while the researchers on the asap queue ran on. The 12:53Z pass on `pro_asap` answered in
  42 s and bore a family; rollback: unset the key, once the balanced queue answers again.
- **12:54Z:** `architect.sail_effort` medium → high. The 13:14Z pass bore 4 of 6; the population was 21 at 13:40Z.
- **07:38-07:51Z, an operator error:** a large read-only extract on the House exhausted its memory and stalled the swarm; the
  House's supervisor restarted the swarm itself. Extracts are now batched and capped.

### 05:16Z, House release `20261002T051530Z-1aebcf26b145` (main `81ad284c`; PRs #480, #483)

- **The duplicate look** (H3a, branch `gate/h3a-no-duplicate-look`; `league/swarm/gate.py`, `league/swarm/store.py`,
  `league/CONTRACT.md`; the money path: `gate.py` and `store.py` are loaded by the live path, so it deploys 20:05-13:25Z
  only, after two adversarial reviews and green CI). Every holdout look raises the Holm bar for every later one, and the
  three looks since the Sept 26 reset covered two programs (the edge study: the two Sept 27 looks had identical Train
  and Validation results). The gate now refuses a look that would repeat an earlier one, in any family and lineage,
  before anything else is asked of the version (the experiment contract, the drift screen, the rations, the paid review
  and audit, the look): the same program (`run_sha`), or a version whose stored Validation run says the same as a looked
  version's (the Gym's own run sha, the code with its parameters merged over the defaults; or the same evaluation with
  the same outcome). Recorded as every gate refusal is (stage "duplicate look": the refusal row, the program's incubator
  bar, `gated_sha` with `gate_ready` cleared, outcome "refused"), plus a private `swarm.gate` event `duplicate_look`
  naming the earlier look; no look row, no try, no review, no holdout read; the researcher hears the earlier look's
  number, never a figure. A repeat of a look in flight in another family waits for it; a version whose own look landed
  is only closed. Before this, a gate-ready version whose `run_sha` had been looked at was skipped silently every round
  and kept `gate_ready`, and a repeat under another `run_sha` was reviewed and looked at. Tightening only: no threshold,
  Holm, deflated-Sharpe or forward rule moves; nothing in `league/live`, `league/gym` or `LEAGUE_FILES`, no evaluator
  adoption, no money digest. To verify after the deploy: `swarm.gate` events with action `duplicate_look` (expect none
  for a genuinely new version) and `refusals` rows with stage "duplicate look".
- **The cell's yield** (H2 of the Oct 1 edge study, branch `cards/h2-yield-aware`; `league/swarm/cards.py`,
  `league/swarm/architect.py`, `league/swarm/settings.py`; off by default, so the deploy changes nothing until the
  operator sets it). From 22:00Z Oct 1 the architect bore nothing for seven passes and the population fell to 13
  (floor 12). Every refusal was the card check's rebirth rule: the productive cells are full of self-refuted and drift
  rows, which `RebirthIndex` counts as mechanism verdicts, and the model's claims named rows outside the six the refusal
  listed. Two settings, in `swarm.json` with no deploy:
  - `architect.cell_yield` (null) opens a cell unless it is exhausted. Exhausted means at least `min_births` settled
    births in `lookback_days` whose Wilson 95% upper bound on drift-pass share is below `floor` (recommended, and `true`:
    30, 0.10, 7). In an open cell a card matching only self-refuted and drift rows needs no rebirth claim. Every other
    mechanism verdict still needs one, and so does every row of an exhausted cell.
  - `architect.claimable_rows` (0) lists, for each cell where a claim can be needed, the newest rows a claim may name,
    with the inputs each read.

  Unchanged: `MECHANISM_VERDICTS` and the rows indexed (the memory lane's judge), the matching, a claim's tests, both
  rebirth budgets, `card_rebirth` "refuse", the same-slice and same-idea refusals, and card completeness (lineage too
  while `cell_yield` is off). A claim made in an open cell that needed none is kept only when it holds; otherwise it is
  stripped before the card is stored (`claim_dropped` on the birth). A yield that cannot be read leaves every cell as
  before. No Validation or holdout figure reaches the request. The pass's event carries `cell_yield` (Train figures
  only). On the edge study's Oct 1 12:59Z extract, none of the 127 classified cells would be exhausted. Nothing in
  `league/live`, `league/gym` or `LEAGUE_FILES`, no evaluator adoption, no money digest. The money path: an import trace
  of the tree (`league/live/*.py`, then the modules `league/live` imports lazily:
  `league/swarm/{store,bands,gate,evaluator,settings}.py`, and the docs' lazy `league/gym` modules and the constitution)
  loads `cards.py` (through `gate`, `researcher`) and `settings.py`, never `architect.py`, and no module it did not load
  before (`cards.py` now imports `evidence.py`, already loaded), so it deploys 20:05-13:25Z only, after two adversarial
  reviews and green CI. The live path never builds a `RebirthIndex`. To switch on and verify: `docs/operations.md`,
  **The cell's yield**.

  With `cell_yield` on, an open-cell restatement on another slice is born as a fresh lineage (its own deflated-Sharpe
  N): switching it on is the owner's decision; `claimable_rows` alone changes no lineage. Fixes from the reviews: the
  yield reading is read before its error flag (E1); a non-finite `claimable_rows` is off, not an error (E2).
- **Deploy.** CI green on the combined head; the daemon stopped idle; staged 05:15:30Z, promoted 05:16:03Z. No evidence reset; the
  money digest unchanged; lineage diff 0 violations. A deliberate restart at 05:27Z restored every instance, and a killed swarm
  process recovered in 31 seconds.

## 2026-10-01

### 20:35Z, the H1 release: House release `20261001T203426Z-6fa69bfcda55` (main `665a9e8d`; PRs #475, #476, #477)

- **Contents.** No retire while the best Train version awaits validation (H1, #475); the research lane's held-out pool
  pin after the operator's rotation r8 (#476, `league/swarm/harness_lanes.py`: the research lane's hash moves, so every
  research candidate captured before it is re-captured); the architect's lenient read 2 (#477). The two items as
  merged:
  - **No retire while the best Train version awaits validation** (H1, PR #475, branch
    `b/h1-no-retire-awaiting-validation`;
    `league/swarm/researcher.py`, `league/swarm/diagnostician.py`, `league/swarm/harness_lanes.py`; the money path:
    `researcher.py` is loaded by the live path through `gate`, so it deploys 20:05-13:25Z only, after two adversarial
    reviews and green CI). On Oct 1 seven of the ten families that made a drift-passing Train version retired themselves
    before the tournament validated it, four of them holding a positive best whose 1.5x run had landed with a profit:
    `Researcher.can_retire` never asked `awaiting_validation`, which the dormancy clause and the status already honoured.
    Now a Gym family whose best Train version awaits validation (not validated, not lost at 1.5x, not failed by the drift
    screen) is not offered `retire`, a call is refused with the reason (on Sail and on Claude; the cycle's record carries
    `retire_awaiting`), the status says so in place of any offer, and the diagnostician's retire defers as it does behind
    the gate; the tournament's verdict, pass or fail, ends it, and so does a demotion. Nothing else moves: no threshold,
    `retire_min_trials`, floor, eligibility or score; the tournament's own rules and `SwarmStore.retire_gym` are
    unchanged (a store-level refusal would let a 1.5x run that never lands make a family no rule could retire). Not
    done, a follow-up: queueing the validation when a new best lands. Nothing in `league/live`, `league/gym` or
    `LEAGUE_FILES`, no evaluator adoption, no money digest. To verify after the deploy: `swarm.cycle` events carrying
    `retire_refused` with `retire_awaiting` (the version the tournament owes a verdict), and no `swarm.retired` event
    whose cause begins "Self-refuted" for a family whose `best_version` differs from its `validated_version` and sits in
    neither `robust_failed` nor `drift_failed`.
  - **Architect lenient read 2** (branch `b/architect-lenient-json-2`): a complete architect answer whose `families`
    array does not parse whole is read object by object (`recover_families`): each family decoded from its own `{`,
    the stray closers and commas between the families skipped, an object that does not decode passed over to its own
    closing brace (never entered), a card a stray `}` inside it closed early passed over too (never born truncated),
    the walk never leaving the array (anything else between two cards ends it), nothing inside a family changed beyond
    #472's trailing-comma strip; the pass's `swarm.architect` event says `recovered` (how many, why, and `passed`),
    beside #472's `lenient`. At 15:59:36Z Oct 1 a Kimi-K3 pass answered six families in 16,008 characters with a stray
    `}` after the fourth and after the fifth; the strict read failed (`Expecting ',' delimiter` at char 10,897), #472's
    trailing-comma read did not apply, the router's reader fell back to the first family card, and the pass read as 0
    proposals (population 42 against a start of 96; about $0.15 and 20 minutes of births lost). On the saved answer the
    new read recovers 6 of 6, each byte for byte (no strip ran). The parse that feeds `admit` (`read_families`,
    `recover_families`, `_from_families`, `without_trailing_commas`, `_past_object`, `_CARD`, `CARD_KEY`) joins
    `salvage_families` in the memory lane's `FROZEN_SYMBOLS` (`league/swarm/harness_lanes.py`). Research-class:
    `league/swarm/architect.py` is not loaded by the live path (verified Oct 1); nothing in `league/live`, `league/gym`
    or `LEAGUE_FILES`, no evaluator adoption, no money digest. To verify after the deploy: a `swarm.architect` event
    whose answer failed the strict read says `recovered` with `proposed` > 0.
- **Deploy.** From a clean detached checkout of `665a9e8d`, with the nightly forward daemon stopped idle (lock free
  20:34:16Z) and a lineage snapshot taken first: staged 20:34:29Z, promoted 20:35:07Z over `20261001T133355Z-67c841b645ca`.
- **No evidence reset, verified** (read-only, 20:37Z): `research_evaluator.execution` still `47587e22…`, bundle
  `gym-engine-4-e1c896f8d304`, image `sbcp_13c5a61d`; the 9 practice cohorts active; the money digest unchanged
  (`42c4a3af`), so no ratify. `real_money` true, `failures` []; the swarm restarted on the new release; the House test
  instance live and `googl-lags-msft-ai-cloud-qqq-flat@27:t` exit-only with position 14 open; no working order;
  `live.incubator` on.

### 20:33Z, operator change (no deploy): the architect back on Claude

- `claude.usd_cap` 198 → 263 and `claude.role_usd_day.architect` 0 → 5 in `swarm.json` (`set_swarm.py`, dry run then
  `--apply`), within the owner's $100 Claude balance; reviews, audits, the strategist and the diagnostician keep their
  lines.

### 20:32Z, gateway `4471596a` (main `07ab60d3`; PR #473)

- **`CLAUDE_USD` 200 → 265:** the owner topped the Anthropic account up to a $100 balance against $165.26 metered
  spent (Oct 1 about 14:35Z), so the funded total is raised by exactly that, rounded down. `npx wrangler deploy` from a
  clean detached checkout; the deployed version's `CLAUDE_USD` reads 265 and every money cap still matches the
  constitution (pre-open check 3). Rollback: `dafcfa05`.

### 16:25Z, the site (personal-site #20; version `3f6147f5`)

- The owner's ideas as small additions to the prior design (trade reasons, the swarm's profit line, the live thought
  queue, performance over time, per-trade results, the game's levels), after a code review and an honesty review.
  `npm run check && npm test` (112 pass, 0 fail, 9 skipped), then `npm run deploy`. Rollback: `6e49f120`, the prior
  page; the Worker and the data layer are unchanged, so it is safe.

### 15:22Z, operator change (no deploy): agenda v16c, two structures, the cell rebirth budget, two retirements

- **15:22:15Z, `swarm.json`** (a before-copy kept), the edge study's levers as settings after its adversarial critique:
  `architect.agenda_locked` and the fallback `architect.agenda` are agenda v16c (steering only; D2 and every kill test
  unchanged; the text stays private, sha256 `c7a46dca0707…`). The fallback it replaces (v15) carried Validation figures,
  and that route is closed. In the same write: `architect.structures` `"real"` → `["debit_vertical", "long_single"]`,
  and `architect.max_rebirths_per_cell` 3 → 6 (`max_rebirths_per_row` 2 and `card_rebirth` unchanged).
- **15:22:40Z,** the strategist's agenda section (kv `architect_agenda_section`) cleared after a backup, so the
  architect reads v16c verbatim until the strategist's next accepted section.
- **15:22:59Z, two operator retirements** (`SwarmStore.retire_gym`, source "operator"):
  `googl-lags-msft-ai-cloud-qqq-flat-r` and `googl-lags-msft-ai-cloud-qqq-flat--2`, the GOOGL lineage's two practice
  families, retired after the lineage's program failed its holdout look (09:39Z, under the 09:16Z release). The failed
  look already bars the program from the incubator. Retiring a family does not end its practice cohort: both cohorts
  kept practising (`docs/operations.md`, **Ending a cohort by hand**). The open tuition lot stays exit-only to its
  programmed exit.
- **What followed, as expected:** clearing the section woke the held families, and at 15:27Z the idle rule retired 26
  architect-born families with no Train best (population 69 → 40; start 96, floor 12). One more, a 14:43Z revival whose
  best Train version awaited validation, retired itself at 15:22:52Z: the defect the H1 release fixed at 20:35Z.
- **A pre-registered 24-hour read** runs from 15:22:15Z, scored at about 15:22Z Oct 2, with its stop rule fixed in
  advance (the run record, "The edge study").

### 14:43Z, operator change (no deploy): seven revivals for practice

- Seven of release A's drift-passing programs on real structures, revived for Train-tier practice and the incubator
  route, not D2. Each is a lineage continuation that inherits its lineage's trials and holdout looks, with its reason
  recorded; their validation verdicts stand. Since #465 (09:16Z) the harness runs each revived program exactly before
  its researcher acts.

  | Revived as | From | Inherited trials |
  |---|---|---|
  | `rate-lag-flat-index-meta-mara-r-2` | `rate-lag-flat-index-meta-mara` v33 | 227 |
  | `hardborrow-forward-squeeze-single-r` | `hardborrow-forward-squeeze-single` v7 | 77 |
  | `slv-iv-discount-momentum-single-r` | `slv-iv-discount-momentum-single` v19 | 48 |
  | `qqq-exsemis-residual-smh-flat-on-s-2` | `qqq-exsemis-residual-smh-flat-on-spx` v116 | 450 |
  | `levered-close-convergence-single-r` | `levered-close-convergence-single` v5 | 370 |
  | `market-distraction-release-call-r--3` | `market-distraction-release-call-r-2` v2 | 133 |
  | `slv-smh-staggered-coupling-single-r` | `slv-smh-staggered-coupling-single` v4 | 66 |

- **Outcome, 14:56Z:** six re-passed Train and the drift screen with their release A numbers exactly (the revival fix at
  work); `hardborrow-forward-squeeze-single-r` failed the drift screen. Those that passed joined practice at the next
  sync, for 9 practice rows.

### About 13:58Z, the site (personal-site #19; version `6e49f120`)

- The prior design restored at the owner's request: the morning's swarm-window page is reverted, and its data layer
  (the schema and the Worker) is kept, because rolling the Worker back after a window checkpoint is stored is unsafe.
  Verified: 0 differing pixels against the prior page (`420a7de`) with the day's data, and `/capital/` answers 200.

### 13:34Z, the lanes release: House release `20261001T133355Z-67c841b645ca` (main `a7542c1c`; PR #466: #449, #452, the memory judge v4, #472)

- **Contents.** Research-class: no module the live path loads changes, so it deployed in session, after the open had
  settled (never 19:30-20:00Z). Nothing under `league/gym`, `league/live`, `LEAGUE_FILES`, the constitution or the
  gateway.
  - **The harness improvement lanes** (#449): research, prompt/memory, data and execution lanes, each with a
    predeclared metric, judges run on the pinned base, private held-out pools pinned by hash only, and an adversarial
    review recorded before a candidate reaches the House
    ([playbooks/harness-improvement.md](playbooks/harness-improvement.md)).
  - **The evaluator benchmarks** (#452): the pinned suite `evaluator-suite-1`
    (`python -m league.swarm.benchmarks --suite evaluator`) scores an evaluator's false promotions and missed signals on
    known-answer cases; no threshold changes. Its results are in
    [docs/benchmarks/EVALUATOR_1.md](docs/benchmarks/EVALUATOR_1.md), including writable numpy state reachable from Gym
    programs, a channel between runs. The fix is in `league/gym`, so it waits for a planned release; until then it is a
    known limit of the evaluator's isolation.
  - **The memory judge v4** (`memory-rebirth-v4`, on the release branch). Since B', a proposal without a complete
    card is not born, so v3's synthetic proposals were all refused and the judge measured nothing. v4 cards its
    fixtures as production admits them and adds same-cell controls; it closed after four review rounds. The memory
    lane's held-out pool pin moves after the operator's private rotation r7.
  - **The architect's lenient read** (#472): a complete answer with stray trailing commas (`,}`), as Kimi-K3 wrote at
    medium effort at 11:57Z, is read again without them (outside strings); the `swarm.architect` event says `lenient`.
    On the real failed answer it recovers all 6 families.
- **Deploy.** With the nightly forward daemon stopped idle across it: staged 13:33:57Z, promoted 13:34:48Z over
  `20261001T114505Z-2d791c2ca9e7`.
- **No evidence reset, verified** (read-only, after promotion): 0 evaluator adoptions; lineage snapshots before and
  after compared 1,774 lineages and found 0 violations; the 3 practice cohorts intact; health `failures` []; the lanes
  command (`scripts/harness_improve.py lanes`) runs on the box. The money digest is unchanged (`42c4a3af`), so no
  ratify.
- **After it (operator settings, no deploy):** 13:45Z `architect.sail_effort` "medium" and `architect.max_refill` 12,
  with #472 live. The 13:59Z pass at medium proposed 12 and bore none (the card checks refused weaker cards: incomplete
  falsifications and refuted-cell rebirths), so at about 14:00Z both went back, to "high" and 6. Harness cycle 2 then
  measured the lanes on the box and ranked them on this base, registering two candidates: the research lane against
  the Train disqualification rate, and the memory lane against validation attempts per research dollar. Each touches a
  module the live path loads, so each deploys after a close and runs a canary window in which no other House release
  ships.

### 11:45Z, the architect on Sail: House release `20261001T114505Z-2d791c2ca9e7` (main `9b6d8857`; PR #470)

- **Why.** From 08:15Z every architect pass on Sail (Kimi-K3 at a hard-coded "high" effort, 32,000 output tokens) came
  back incomplete. Family cards (B') had doubled the visible answer, and the reasoning spent the whole output budget,
  so the answer was empty or cut. `ModelRouter.ask` ignored Sail's `incomplete`, so each pass read as 0 proposals,
  salvage never ran, and each empty pass erased the last card refusals. The empty passes cost $4.43 on Oct 1.
- **Contents** (#470; `league/swarm/architect.py`, `league/swarm/models.py`). `architect.sail_effort` (default
  "medium"; a value it does not know reads as the default). The Sail route also returns `truncated`,
  `incomplete_reason` and `usage`, so a cut Sail answer is salvaged like a Claude one, and the one retry stays on
  Claude only. A pass that proposed nothing no longer overwrites the card and structure refusals, and a retry no longer
  counts refusals twice. Research-class: the live path loads neither module (verified on the box); the execution
  fingerprint (`47587e22`) and the money digest (`42c4a3af`) are unchanged, so no ratify.
- **Operator stopgaps before it (no deploy):** 11:03Z `architect.every_seconds` 900 → 3600, to stop paying for empty
  passes; 11:15Z `architect.max_refill` 12 → 6, to halve the answer. A mistaken `architect.max_output_tokens` 24000 at
  10:59:44Z was restored to 32000 within a minute.
- **Deploy.** Staged 11:45:07Z, promoted 11:45:42Z over `20261001T101853Z-466bca70278a`.
- **Verified** (read-only): lineage snapshots before and after (11:44:50Z, 11:51:11Z) compared 1,772 lineages and found
  0 violations. At the 13:33Z open check, under this release, health listed no failure, the incubator's pins were dated
  Oct 1 (no eligible family), and 3 practice cohorts were active. A health read and an adoption count taken right after
  the promote are not recorded.
- **After it:** the 11:57Z pass at medium completed in 48 s but read as 0, because stray trailing commas broke the
  strict read (fixed by #472 in the 13:34Z release). At about 12:00Z `architect.sail_effort` was set to "high"; with
  `max_refill` 6, a pass completes.

### 10:19Z, the site feed: House release `20261001T101853Z-466bca70278a` (main `554b0aa8`; PR #469, which carries #463)

- **The site first** (the verified safe order is site, then House): personal-site #18 (merge `b8ad841`), Worker version
  `23d732c6`, at about 10:00Z, after `npm test` (108 pass, 9 skipped). Until the House sent the window, the site served
  the checkpoint as before. **Rollback caution:** once a window checkpoint is stored, rolling the site back past #18
  (to `420a7de`) is unsafe, because the older Worker spreads `levels` and `rationale` (PR #18's rollback note).
- **Contents.** #469 is #463 plus the House's copy of the site schema, refreshed to `b8ad841`. Money path by the goal's
  definition (the live path loads `league/swarm/public.py`), so it deployed outside 13:25-20:05Z. #463 as merged:
  - **The swarm window** (branch `b/site-rationale`): the publisher sends `levels` (each agent's level and the levels
    funnel since the reset) and `rationale` (each agent's thesis, and each real position's route, reasons, exit and
    maximum loss), pins every agent a real position names to the roster, and filters every mechanism against its
    program's parameter names. After its three reviews: a thesis, a tag, a note and a mechanism carry no number in any
    form (number words including ordinals, fractions and run-together numbers; "one" only as a pronoun; numerals of any
    script; no hidden format mark or look-alike letter; parameter names with hyphens or run together); the roster's
    mechanism and the birth news drop every sentence with a number (no entry window or threshold on the page); Tuition
    counts only families that held a tuition lot (its own branch of the funnel); a position's route is the band it was
    opened on; under the byte limit the window leaves before any agent or row, with 32 KiB left for the site's names (a
    40-character name on each of 508 rows); the window is not read while the site refuses it. After the post-fix
    verification (Oct 1, 09:30Z): an apostrophe never hides a number word ("fifty's", "'twenty-day'", typographic
    quotes), accents fold away before reading ("twénty"), a word split by a mark joins ("twen·ty"), cardinal plurals,
    multiples ("quintuple"), "couple", "unity", "a score of", "-ish"/"-odd"/"-something" and "pct"/"bps" run together
    are numbers (`number_words.json` is the case list the site tests too); and a trade's `why` on the public tape
    (`agent.trade`, live today) is filtered by the same rules and the traded program's parameter names, or empty.
    Publisher and swarm-feed files only (`league/publish.py`, `league/site_window.py`, `league/trading_profit.py`,
    `league/swarm/public.py`, `league/swarm/sitefeed.py`, `league/swarm/hook.py`): nothing in `league/live`,
    `league/gym` or `LEAGUE_FILES`, no evaluator adoption, no money digest. Site first (personal-site
    `capital/swarm-window`); an older site gets the checkpoint without the window. Two nits from the verification
    shipped as known limits: one accent case (a mark stuck to a number word) can still pass, and a fill on the netting
    book publishes an empty `why`.
- **Deploy.** With the nightly forward daemon stopped idle across it: staged 10:18:54Z, promoted 10:19:28Z over
  `20261001T091620Z-08ad59436dc2`.
- **No evidence reset, verified** (read-only): no evaluator adoption (fingerprint `47587e22`); lineage snapshots before
  and after compared 1,770 lineages and found 0 violations. The money digest is unchanged (`42c4a3af`), so no ratify.
- **The window, end to end:** at 10:29:02Z the public checkpoint (`curl -s
  'https://blakewoods.us/api/capital/checkpoint?progress=1&positions=1&practice=1&window=1'`) carried `levels` and
  `rationale`, so the site took the window; read again at 20:48Z, it still does.

### 09:16Z, the money-path release: House release `20261001T091620Z-08ad59436dc2` (main `4bc49530`; PR #468: #465, #467)

- **Contents.** Money path by the goal's definition (the live path's imports reach `researcher.py`, `gate.py`, `pool.py`
  and `settings.py`), so it deployed outside 13:25-20:05Z. Nothing under `league/gym`, `league/live`, `LEAGUE_FILES`,
  the constitution or the gateway. #463, first planned for this release, shipped on its own at 10:19Z.
  - **An operator revival runs its program exactly** (#465, `league/swarm/researcher.py`). Until now a revival never ran
    the revived program: a bare `gym_run` dropped the version's stored params, and cheap researchers rewrote the code at
    once. Now, at the start of a cycle and before any rewrite or model turn, the harness runs a living Gym family's
    latest operator-written version with its stored code and params, once per evaluator and Train span, through
    `gym_run`'s own path (the same refusals, trial count, drift screen and robustness runs). A bare `gym_run` reruns the
    latest version exactly. Audit a claim that a revival "re-validated with identical numbers" by its eval key (code sha
    and merged params), not its version number.
  - **Gate hardening** (#467; `scripts/data/nightly.py`, `league/swarm/settings.py`, `loop.py`, `pool.py`, `gate.py`).
    The nightly forward chain records the gate image each day extends (`base_checkpoint`, `holdout_roots`), and the
    swarm uses the ready file only when it extends `gym.gate_checkpoint` and covers `gym.roots`; otherwise it keeps
    `swarm.json`'s gate and alerts `gate_chain_ignored`. The nightly refuses a chain it cannot prove before it wakes a
    box. A gate box lists its holdout coverage when it starts, and the gate refuses a look up front for a missing root.
    A look that fails for missing data costs no try, writes no "gym" refusal and bars nothing, and
    `look_failed_three_times` fires at every count from three.
- **Deploy.** The nightly forward daemon stopped idle; staged 09:16:23Z, promoted 09:16:58Z over B'
  (`20261001T071033Z-95efdb353597`). Then #467's migration: `nightly.py stamp-ready`, a dry run and then `--apply`,
  stamped the ready file with its base gate and its 25 holdout roots. The effective gate checkpoint did not change, no
  ready file was ignored, and the daemon was un-stopped.
- **No evidence reset, verified** (read-only): no evaluator adoption, the evaluator unchanged; lineage snapshots before
  and after compared 1,770 lineages and found 0 violations; `real_money` true, `failures` []. The money digest is
  unchanged (`42c4a3af`), so no ratify.
- **The revival fix, in production.** Within 3 minutes the harness ran the living revivals' version 1 exactly
  (`googl-lags-msft-ai-cloud-qqq-flat-r`, v27's program, and `silver-industrial-cycle-debit-r-r`, v20's), and Train and
  the robustness runs landed. The GOOGL program then validated again under the current evaluator, passed review and
  audit, and took its sealed 2026 holdout look at 09:39:56Z, the first look since Sept 27 and the first on the 25-root
  gate. **It failed.** The gate barred the program from the incubator, and its open tuition lot stays exit-only to its
  programmed exit.

### 07:11Z, Release B': House release `20261001T071033Z-95efdb353597` (main `03c274c9`; PR #460: #446, #458, #459, #461)

- **Contents.** Swarm-side only: nothing under `league/gym`, `league/live`, `LEAGUE_FILES`, the constitution or the
  gateway, so no evidence reset. `researcher.py` and `bands.py` are in the live path's imports, so it deployed outside a
  session.
  - **Family cards** (#446; `league/swarm/cards.py`, `league/swarm/mechanism.py`). Every architect proposal carries a
    schema-checked card (hypothesis, mechanism class, inputs, holding, cost, comparison, ablation, falsification); one
    without a complete card is not born (`architect.require_card`). Cards are immutable in `family_cards`, and
    researchers see them in every brief. A rebirth in a cell a mechanism verdict refuted is refused unless it names the
    dead row, adds an input that row did not read and cites checkable evidence, within budgets
    (`architect.max_rebirths_per_row` 2, `architect.max_rebirths_per_cell` 3 in 7 days; `architect.card_rebirth` "off"
    turns it off). A blind mechanism test runs in shadow mode on a quarter of carded families and stops nothing.
  - **The final release-B nits** (#458): the incubator's reader and the swarm agree on another family's owed audit
    (fail-closed: no paid review for a program the reader would refuse), and the L1 keep holds every cohort the
    incubator could pin, beyond its cap.
  - **The architect's structure allowlist** (#459, `architect.structures`). Since release B, 47 of 78 births were
    structures real money cannot trade at this equity. With `"real"`, the gaps, birth quotas, admission, forks and seeds
    read only `allocation.real_structures` (debit verticals, long butterflies, long calls and puts, long singles), and a
    refused proposal is named in the next request. Absent or null, every type stays allowed.
  - **The retire guard** (#461; `researcher.retire_guard_days`, 14). Release B's adoption cleared every selection at
    03:51Z, and within seconds the four families holding validated versions retired themselves, citing the evaluator
    change. A researcher's `retire` is now refused while the family holds a version whose latest validation passed
    within the window. The guard also reads the adoption events, so a second adoption cannot lift it; only a failed
    validation of that version ends it.
- **Deploy.** The nightly forward daemon stopped idle; staged 07:10:34Z, promoted 07:11:09Z over Release B
  (`20261001T034829Z-d823e014ce16`); the daemon was un-stopped at 07:21:45Z. CI was green on 3.11 and 3.14.
- **No evidence reset, verified** (read-only, after promotion): `research_evaluator` unchanged (bundle
  `gym-engine-4-e1c896f8d304`, execution `47587e22…`, image `sbcp_13c5a61d`); 0 adoption events since 07:10Z; lineage
  snapshots before and after compared 1,762 lineages and found 0 violations (11 grew by new trials); `real_money` true,
  `failures` []. The money digest is unchanged (`42c4a3af`), so no ratify.
- **Switched on, 07:20Z** (`swarm.json`, no deploy): `architect.structures` `"real"`. The first pass after B' bore a
  silver-coupled vertical and a TSM long butterfly.
- **Deferred:** #462 (keep the research selection when an adoption moves only the live fingerprint), a policy change,
  because the owner's rule treats a live change as an evidence reset.
- **Found after it:** two of the 07:02Z revivals retired themselves within 15 minutes after running new versions, never
  the revived one. No more revivals until the 09:16Z release's fix (#465).

### 05:55-07:30Z, operator changes (no deploy): revivals, a manual checkpoint, the holdout gate chain re-based

- **About 05:55Z, the GOOGL family revived.** `googl-lags-msft-ai-cloud-qqq-flat` v27, whose tuition lot is open, had
  retired itself over Sept 30's evaluator change. It is revived unchanged as `googl-lags-msft-ai-cloud-qqq-flat-r`, a
  lineage continuation (123 inherited trials, no consumed look).
- **06:58Z, a manual House checkpoint** (`house-manual-20261001`, kept to Oct 31): Sail's automatic House backups had
  failed since Sept 30 05:54Z with a platform 503. They read OK again by 14:54Z.
- **07:02Z, three revivals for Train-tier practice, not D2.** Each program passed Train at 1.5x and the drift screen
  under release A; their validation verdicts stand.

  | Revived as | From | Inherited trials |
  |---|---|---|
  | `silver-industrial-cycle-debit-r-r` | `silver-industrial-cycle-debit-r` v20 | 1,117 |
  | `rate-lag-flat-index-meta-mara-r` | `rate-lag-flat-index-meta-mara` v33 | 217 |
  | `market-distraction-release-call-r--2` | `market-distraction-release-call-r-2` v2 | 120 |

  Two of them (`rate-lag-…-r`, `market-distraction-…-r--2`) retired themselves within 15 minutes without running the
  revived program: the revival defect that #465 fixed at 09:16Z.
- **07:05-07:30Z, the holdout gate chain re-based** (no data fetched, no evidence identity moved, no look consumed).
  The nightly forward chain had extended the original five-root gate image, and its ready file overrode the 25-root
  gate named in `swarm.json`. So every gate box since Sept 29 forked from a five-root holdout, and the GOOGL program's
  look had failed three times on Sept 30 with "no holdout days for GOOGL, MSFT" (infrastructure failures, not looks).
  With the daemon idle and stopped (07:05:31Z), the re-base wrote `data/images.json` and `data/nightly.json` (backups
  kept) to name the 25-root gate image. The daemon restarted at 07:06:41Z, copied the forward days onto the new chain
  (retrying through Sail transport timeouts) and published it at 07:26:13Z. Verified on an idle gate box: all 25 roots
  hold the full 2026 holdout in nbbo, underlying and open interest, plus the forward days. The program's three failed
  tries were reset to 0; the looks table still held 2 rows.

### 04:25Z, operator change (no deploy): a pre-open research burst, reverted at 13:15Z

- **`swarm.json` at 04:24:58Z:** `researcher.sail_usd_per_hour` 1.3 → 2.5, `gym.max_boxes` 6 → 8 and
  `architect.every_seconds` 1800 → 900. Release B's reset had cleared every Train best, and practice cohorts form at
  the 13:30Z open only from Train-eligible versions. Estimated cost: about $25. Train runs went from about 40 to about
  195 an hour.
- **Reverted at 13:15:00Z** by a timer, as planned, to 1.3, 6 and 1800 (verified at the 13:33Z open check). The revert
  also ended the 11:03Z stopgap (`architect.every_seconds` 3600).

### 04:01Z, operator change (no deploy): the incubator switched on

- **`live.incubator`** set to JSON `true` in `swarm.json` (a before-copy kept), outside a session, after the
  ratification and the checks below. `python3 -m league.live --root /workspace/state --incubator` read `switch.on`
  true, a zero tally and no instances.
- **Nothing trades on it yet.** A cohort is pinned only after its first look passes, and a first look needs 3 completed
  sessions and 10 program closes in the record before today. For cohorts admitted at the Oct 1 open, that is the Oct 6
  open at the earliest (sessions Oct 1, 2 and 5).
- **To switch it off:** `live.incubator` false in `swarm.json` ([docs/operations.md](docs/operations.md), "Current
  operation"). Within a minute its instances go to exits only and their working opens are cancelled.

### 03:49Z, Release B: House release `20261001T034829Z-d823e014ce16` (main `3eaf4d06`; PR #454), gateway `dafcfa05`, evidence reset 2

- **The gateway first: `dafcfa05`,** deployed at 03:48Z from the merge commit after `npm run check && npm test` (338
  tests pass).
  - It adds the research library's routes (`/v1/research/search`, `/read`, `/health`) and its KV binding `LIBRARY`
    (namespace `ltcm-gateway-library`), with `LIBRARY_DAY_UPSTREAM` "600". Its web reader now sends arXiv to the
    library.
  - The order routes are unchanged.
  - The kill switch stayed false, `/v1/health` answered 200, and the library's health read OK.
  - The rollback target is `ac2779ac`.
- **The House deploy.** Staged 03:48:34Z; promoted 03:49:07Z over Release A. The watch's verdict was PROMOTED, and the
  deploy exited 0. The rollback target (`previous`) is Release A, `20260930T200604Z-3bf48c3f8f9f`.
- **The money digest moved** `a3e2aa7c` → `42c4a3af` (`PINNED_DIGEST` `fcf8d735` → `595228a6`): the incubator's row.
  - **The grant was re-ratified** at about 03:59Z, after the PROMOTED verdict. No real entry was due before the
    13:30Z open, and ratifying after the verdict avoids a rollback-after-ratify mismatch.
  - The grant reads active on policy digest `42c4a3af`, at its third ratification, with micro and scaled entries
    allowed. Capital was read afresh: $1,246.73, the lower of equity and the ceiling.
- **Evidence reset 2, verified** (read-only, after promotion).
  - `research_evaluator`'s execution fingerprint moved (`2d3d0284` → `47587e22`). The Gym bundle
    (`gym-engine-4-e1c896f8d304`) and the image are unchanged.
  - Each of the 51 families alive at the start recorded an `evaluator_adopted` event.
  - A read-only lineage snapshot before and after the deploy compared 1,690 lineages and found 0 violations: trials,
    inherited trials and consumed holdout looks were unchanged, with 2 looks in all.
- **The B2 backfill** ran at the first swarm start, before the adoption: "incubator backfill: 1 programs barred from 14
  gate events". A failure that the gate had recorded only in its event log or its attempt counts is now a durable bar
  on its program, so B's own adoption could not erase it.
- **The live guards, verified.** `real_money` true; `failures` empty; no working order.
  - `house:rebound-live@0:h` is real, `observe` false, mode live, with no error.
  - The tuition instance is real, tuition and exits-only, with no error, and its position is open.
  - No `:i` instance exists.
  - The incubator's health block: the switch off (as deployed), the table as committed (50, 1, 4, 150, 3, 10, 0.80),
    0 verdicts, a zero tally and no weekly stop.
- **The harness observer** was re-pointed at B's base (`3eaf4d06`) and release digest. It has retained no improvement.
- **Criterion 1 under Release B.**
  - **The restart test,** 04:00:11-04:00:24Z (`floor_box.py stop`, then `start`), with the tuition position open. Both
    instances came back as above, the position was restored, real money stayed on and health listed no failure.
  - **The induced failure,** at about 04:00:31Z: the swarm process was killed with SIGKILL. The House's swarm step
    started a new one within 15 s, with a fresh heartbeat. The alive families (36) and the stored runs (77,027) were
    unchanged: nothing was lost or duplicated.
- **The freeze, in force.** `league/live` and `league/gym` now change only in a planned, deliberate release.
  - A change to either (or to `LEAGUE_FILES`, the fill model or the Gym image) moves the evaluator. Every practice
    cohort is bound to its evaluator, so such a change ends every practice cohort, and with them every incubation, for
    good. It also re-adopts selection.
  - Batch such changes into planned releases. Rollbacks and fixes for bugs that block or endanger real orders are the
    only exceptions.
- **A known skew, for a planned release.** The House runs Python 3.11 with numpy 2.4; the Gym runs Python 3.12 with
  numpy 2.5 (`requirements-gym.txt`). So a program can load and train in the Gym and still fail to load on the live
  path. The preflight (#438) flags it (`preflight_house_unloadable`). The root fix aligns the runtimes: a Gym image
  change is an evidence reset, and a House venv upgrade touches the money path, so it is scheduled, not hot-fixed.
- **The House live test.** Release B changed its order path again: the incubator's route takes its turn after the D2
  families and before the test, the test yields to an incubator refusal on its contracts as to a family's, and the
  incubator keeps $100 of room for the test's structure. `house_test.py`, the test's program, bounds and clock are
  unchanged. Releases A and B are recorded as deviations in the test's private addendum.
- **Operator steps:** [docs/operations.md](docs/operations.md), "Release B: deploy, ratify, switch on".

Release B was branch `release/b-20261001` (PR #454), merged to main as `3eaf4d06`: main `777b894f` (Release A) plus
nine reviewed pull requests and the gateway's KV binding:
- #451, the incubator's live route and money row (B1; money path);
- #444, the incubator's facts and the reader's belt, with durable bars (B2);
- #445, L1, the cohort keep, and #455, its restart safety;
- #456, L2', the incubator's keep (every check reads the record before today; the prior values are copied at the
  session day's roll);
- #447, the research library (it supersedes #428), and `aa435f9e`, its KV binding;
- #453, the evaluator-adoption fixes;
- #448, information-value allocation;
- #438, the API-misuse preflight.

- **Evidence reset 2.** B changes `league/live`, so the execution fingerprint moved. `league/gym` and `LEAGUE_FILES` did
  not change, so the Gym bundle and the image stay Release A's. At B's first start:
  - **Selection was re-adopted.** As at reset 1, every alive family's derived selection evidence was archived and
    cleared: Train bests, candidates, robustness, drift, validation and review. Runs, versions, lineage trial counts and
    consumed holdout looks stay. A validation already recorded on the same image and bundle may be judged again
    (`Tournament.recorded_validation`).
  - **Extension holds stay** (#453): only a new Gym image or bundle clears them, and neither changed.
  - **Practice restarts.** A practice cohort is bound to its evaluator, which is the bundle, the fill model and the
    execution fingerprint. So every cohort from Release A completes at B's first families pass, with the reason
    "evaluator changed; a new version needs fresh practice". A (family, version) that practised under A never practises
    again: practice after B starts from versions not yet practised.

  Evidence from before and after the reset is never compared.

#### What Release B carries

- **The incubator** (#451; `league/live/incubator.py`, `league/live/money.py`, `league/constitution.py`; money path).
  It ships switched off.
  - **The owner's terms.** Approved Sept 29, 14:51Z; the reading was settled Sept 30. A family that passes Train and
    the drift screen on its own, shows positive live practice, and passed the gate's review and audit, trades one lot
    of an approved real structure:
    - at most $50 of maximum loss a structure, fees included;
    - at most 4 structures held or working;
    - the route stops for the ISO week once its net realized loss reaches $150.
  - **The unit** is a practice cohort `(family, version)`. The incubator trades the cohort's frozen snapshot byte for
    byte, never the family's current row, as the REAL, tuition-flagged instance `<family>@<version>:i`.
  - **The first look** (pre-registered, `money.practice_ok`) is taken once per cohort. It comes at the first session
    pin at which the cohort's record before today holds at least 3 completed sessions and 10 program-closed trades
    under the running evaluator. It passes only with:
    - decision coverage of at least 0.80;
    - realized practice P&L above $0 over the program's closes;
    - above $0 over all closes;
    - above $0 over all closes plus the open mark.

    The look is recorded whether or not the switch is on, and a failed first look is final. Its verdict is saved before
    its private `first_look` ledger row, and a cohort with a recorded `first_look` row is never looked at again (its
    verdict is restored from the row). After a pass, each later session re-checks coverage and the three P&L tests on
    the longer record, and a failure ends the incubation for good. A program with no edge passes roughly a third to a
    half of the time: the weekly envelope bounds the cost, not the screen.
  - **The facts** (`bands.incubator`). The family must be:
    - alive, in the Gym band, with the version not demoted;
    - carrying a Train-and-drift pass for the version under the current evaluator and Train objective;
    - reviewed and audited by the gate on the version's run sha, under the current review contract;
    - not refused, failed or demoted by the gate on that sha;
    - not on D2's route.

    With B2 (#444), the reader also keeps its own belt (`incubator_refusal`), whatever the mark says: no row for a
    program the swarm barred (`incubator_barred`, which no adoption clears), one the gate's `review` names without a
    readable pass and a passed audit, one whose incubator review or audit failed, a refused version, a failed look, or
    a family whose verdict records cannot be read. A verdict is on the program (its run sha), so the belt reads these
    in every family that holds the same code and params, alive or retired. It also refuses a program while the gate
    owes it a bar (`incubator-bars-owed.json` beside the store; an unreadable file refuses everything).

    B2 also makes sure B's own evaluator adoption cannot erase a failure. At every swarm start, before the adoption, a
    backfill records as bars the failed reviews and audits that release B's gate left only in its event log
    (`swarm.gate` events, and third unclear answers in the attempt counts). The adoption then records, before it
    clears the selection, every failure held only in `review`, `gate_outcome` or the incubator's reviews, and every
    bar the gate owes.

    **B2 (#444) writes the facts, in this release.** The Train-and-drift mark (`train_passed`) is made by the
    tournament's hourly round for a version of an alive Gym family with an active practice cohort under the current
    evaluator: an eligible Train run, a profitable 1.5x robustness run, no demotion, a passing drift screen, and no bar
    on its program. The incubator's own review and audit are due once the cohort's practice shows at least 2 sessions,
    5 program closes and a positive program P&L, so they are ready by the first look. Both are bound to the evaluator
    they were made under, and an adoption clears them (never a bar). Neither is read by validation, the gate's holdout,
    the forward record or the bands' moves.
  - **The pins,** at the session's first families pass. At most 8 cohorts, one per family, by first-look return on risk,
    each needing:
    - the switch on and real money on;
    - a first look that passed, and a record that still passes;
    - the facts above, with the snapshot's run sha;
    - no D2 route for the family (`:r` and `:t` come first);
    - a real structure;
    - a sampled program close that one lot could open under the $50 cap.

    Every families pass checks again, and a failure sends the instance to exits only.
  - **Keep (L2').** While the switch is on, a cohort whose first look passed keeps practising past its observation
    target, to its bounded window. That is at most 8 cohorts. A failed read never ends an incubation: the last keep's
    cohorts stay kept (never pinned on the untaken check), and the next families pass takes the checks again. While
    the cohorts cannot be read, no cohort is completed at its target, for at most the day's 12 retries. The retries are
    counted durably from the start of each pass, and only for passes 5 minutes apart: a forced pass spends none. If the
    keep raises and the saved keep cannot be read, the House keeps the last keep it took, never nothing. Within a day
    the keep only grows, and a cohort kept without a verdict stays kept for the rest of the day, across a restart.
    Every first look and re-check, at the first pass or a retry, reads the record before today: the practice row keeps
    its coverage and open mark as the last session left them (`prior_*`, stamped with the day they were copied and read
    only on that day), so today's values never decide a check. A record without them, or with an older copy (a release
    that never copies them stepped the row today, as after a rollback), decides nothing on P3 or P6 (P4 and P5 still
    end it) and waits for the next session.
  - **The caps**, in the House only (`money.plan_incubator`). The gateway cannot tell routes apart, so its own caps are
    the backstop.
    - One lot of at most $50 a structure, and $50 held or working per family.
    - At most 4 structures held or working.
    - **The weekly envelope:** this week's net realized loss, plus what is held, plus what is working, plus the new
      unit, at most $150 at every open. Once the week's net realized loss reaches $150 at any close, the route is
      stopped for the rest of the ISO week, whatever a later gain does. The stop is a latch, alerted once a week.
    - 40 order legs a day, and 25% of the gateway's day cap.
    - Room is kept in the book's and the day's caps for two Probe floors ($200) and, while it can still open, the
      House live test's structure ($100).
  - **The order of a minute.** The D2 families' intents go first (`:r`, `:t`), then the incubator's, then the House live
    test's, then the calibration's. A working incubator open is cancelled ("yielded") when a D2 family's real order is
    refused on its contracts after that open was placed.
  - **Never evidence, never a promotion.** Its orders and positions are tuition-flagged. It is never:
    - a forward row (`_export_real` skips every `:i`);
    - a band move;
    - in tuition's own day and week sums.

    D2 stays the only route to Probe and Sized.
  - **Its belt.** An `:i` instance must be real, tuition-flagged, and on a House with an incubator. Anything else asking
    for a real order is refused with an error alert: "live: `<key>` is not a real tuition incubator instance and asked
    for a real order: refused". A restored `:i` instance is tuition-flagged whatever its row says.
  - **Where it shows:**
    - `health.json` `options_live.incubator`: the switch, the table, the pins and refusals, the keep, the verdict
      counts, the tally and the weekly stop;
    - each instance's `incubator` flag;
    - `python3 -m league.live --root /workspace/state --incubator`, read-only;
    - private `live.incubator` ledger rows: first looks, ends, pins, yields and the weekly stop;
    - on the site, the positions table's `source` "incubator" and a real structure's `route` "incubator"
      (personal-site #17 is live).
  - **The switch:** `live.incubator` in `swarm.json`, off by default. Only JSON `true` turns it on; any other value
    reads off and is alerted once. Off, its instances go to exits only and their working opens are cancelled within a
    minute. It is switched on outside a session, after the ratification.
  - **The cost.** Expected value is negative until a family has a real edge: at most about $650 a month on average ($750
    in a five-week month), plus residuals (broker fees above the book's estimate, a broken structure closed leg by leg).
  - **The money row** `options_money.incubator`: `max_loss_usd` 50, `contracts` 1, `max_open` 4, `week_loss_usd` 150,
    `min_sessions` 3, `min_trades` 10, `min_coverage` 0.80. The owner's terms are the loose end of each bound, so a row
    may only tighten. Setting `max_open`, `week_loss_usd` or `max_loss_usd` to 0 stops the route. That is a new digest
    and a ratification, but no evidence reset: the constitution is outside the fingerprint.
  - **Earliest possible open:** Tuesday Oct 6, at 13:30Z, for cohorts that begin practice on Oct 1 (sessions Oct 1, 2
    and 5).
- **B2, the incubator's facts** (#444; `league/swarm/incubator.py`, `league/swarm/bands.py`, `league/swarm/gate.py`):
  the Train-and-drift mark, the incubator's review and audit, the reader's belt, durable bars on the program, and the
  backfill (all under "The facts", above). Swarm side; the fingerprint does not hash it.
- **L1, the cohort keep** (#445, with #455's restart fix; `league/swarm/tournament.py`, `league/swarm/practice.py`,
  `league/swarm/researcher.py`; research side).
  - **What it spares.** A living Gym family with an active practice cohort is spared the tournament's revision,
    evaluation and idle rules, and the idle pass. The keep lasts until the cohort completes, fails or reaches its
    session window. So a family is still alive when its sample is complete and the incubator takes its first look.
  - **What it never spares:** the deflated-Sharpe rule, its researcher's or the diagnostician's own retire, the
    population floor, or the operator's gate hold.
  - **The record it reads** is the cohort's realized record before today. Until the cohort meets the sample (3 sessions
    and 10 program closes), it is kept whatever that record says. After that, it is kept only while program-closed P&L
    and all-closes P&L are both at least 0.
  - **Not kept:**
    - a cohort the House has not practised on 2 sessions while it practises others;
    - a cohort whose practice row began before it.
  - **At most `tournament.incubator_keep_max` (12) families;** 0 turns it off. Those that meet the sample come first,
    by return on risk.
  - **Its record:** one private `swarm.status` event a round (`incubator_keep`).
  - **The researcher's status line.** The keep is saved (`cohort_keep`), so a kept family's researcher is told that
    idleness is no reason to retire it. The retire tool stays offered.
  - **An unreadable record** leaves the last good keep standing for an hour, then none. A fresh swarm process whose
    first read fails takes the keep the last process saved for the rest of that hour, and does not overwrite it
    before then (the release review's restart finding; swarm side, no evidence reset).
  - **Research attention only:** no trial count, look, validation, gate, band or money rule reads it.
- **The research library** (#447, supersedes #428; `gateway/lib/library.mjs`, `league/swarm/library.py`). It is off on
  the House until `research.enabled`.
  - **The gateway** serves `GET /v1/research/search`, `/read` and `/health`: arXiv's quantitative finance,
    econometrics, statistics and machine learning on markets, posted before 2025 and nothing later. The date rule is
    code, on every answer, and the House checks every answer again. Details: [gateway/README.md](gateway/README.md),
    "The research library".
  - **Pace:** arXiv's terms (one request every 3 s, one connection; arxiv.org's crawl delay of 15 s).
    `LIBRARY_DAY_UPSTREAM` allows 600 requests to arXiv a UTC day for the whole floor; `"0"` stops them, and cache hits
    still answer.
  - **The House:**
    - the Claude researchers get a `literature` tool;
    - the architect and the strategist get a retrieved block of abstracts;
    - the strategist names the next searches;
    - Sail's profiles never see it.

    Three lines: 300 calls a day for the floor, 12 a family, 2 a research cycle. Each call is a private
    `swarm.research` event, never mirrored.
  - **The Claude researcher band is off on the box**, so only the architect's and the strategist's blocks are used when
    it is switched on.
- **The gateway's KV cache for the library** (`aa435f9e`). The binding `LIBRARY` is namespace `ltcm-gateway-library`,
  created 20:25Z Sept 30. Never delete it once a deployed version binds it: that would block `wrangler rollback` to
  those versions.
- **Evaluator adoption fixes** (#453; `league/swarm/evaluator.py`, `tournament.py`, `researcher.py`,
  `scripts/extension_hold.py`).
  - **Extension holds.** An adoption archives and clears the extension hold's records only when the Gym's image or
    bundle changes. A `league/live`-only adoption, such as B's, keeps holds and the operator's clears.
  - **Lapses.** A validation of a held version that falls below the checks ends the hold (`extension_lapsed`). A later
    validation of it that meets the checks holds it again.
  - **Idle wording.** After an adoption, the idle count restarts from `evaluator_trials`. Retirements then say "since
    the evaluator changed", no longer "since Train's span changed".
- **Information-value allocation** (#448; `league/swarm/allocation.py`, `loop.py`, `architect.py`; research side).
  - **The share.** Every living family's share of researcher turns and Gym priority is a floor (0.10, spread evenly), an
    exploration share (0.35) across mechanism classes (structure x root group), and a decision share (the rest) by its
    value.
  - **The value** is the variance of its next validation's pass or fail under an empirical-Bayes posterior, discounted
    for the depth of its idea's lineage, for exhaustion (spent looks, a drift-failed or gate-spent version, a hold
    streak) and for a structure the account cannot open for real. So a family near the line earns the most, and an old
    family at zero or below never earns a large share.
  - **The caps:** 5% a family and 30% a mechanism class, while the other classes can take the excess. Shares buy turns
    (stride scheduling, `allocation.scheduler` "stride"), and one structure family may hold at most 60% of the last 24
    hours' births (`BirthQuota`).
  - **Research attention only:** nothing on the way to validation, the gate, the bands or money reads the share.
    `allocation.mode` "bandit" in `swarm.json` restores R11-5's bandit with no deploy.
- **The preflight** (#438; `league/swarm/preflight.py`, `researcher.py`; research side). Before a Train run is spent, a
  candidate program meets small synthetic sessions in the live decider's sandbox.
  - **It refuses only market-independent misuse of the ctx API:** the same misuse at the same line on 25 consecutive
    calls across two sessions, and again on each of five other made-up markets. Everything else is advisory, and the
    run goes on to the Gym, which judges it. Of 300 programs that ran OK in the Gym, it refused none.
  - **The House's runtime.** A program that passes the static code check but does not load on the House's runtime
    (Python 3.11, numpy 2.4) is advisory, and counted (`preflight_house_unloadable`). Its Train run goes ahead, since
    the Gym (Python 3.12, numpy 2.5) may load it, but as written it can never practise or trade live.
  - A refusal costs no Gym job, version or trial. A sweep drops only the refused variants. The preflight never blocks
    on its own failure.
- **Not in B.** These ship when their reviews are clean. They change no file the fingerprint hashes, so none is a
  reset:
  - #446, family cards;
  - #449, harness lanes;
  - #452, evaluator benchmarks.

  Any change to a module the live path loads still deploys only outside the session.

## 2026-09-30

### 20:16-21:25Z, after Release A: operator changes (no deploy)

- **20:16Z, the graveyard verdict migration** (R11-1, once; `scripts/graveyard_verdicts.py --apply`). It re-headed
  1,611 lessons: DRIFT 1,046, THIN 393, EXHAUSTED 145 and STRESS 27, leaving 5 IDLE. The backup of every changed row
  is in `state/backups/`.
- **`swarm.json`:** `claude.role_effort.architect` "medium", `gym.max_boxes` 4 → 6 and `architect.max_refill` 4 → 12.
  These are the settings planned for after Release A.
- **The input capability card** is installed on the box. It is private and matches the Train image.
- **The extension hold seed was not run.** Adoption clears `validation_version` first, so its list is empty by design.
  Families are held when their engine-4 validation meets the checks.
- **Near-miss revivals** (the operator's choice from the validation line). Five families, each a lineage continuation
  that inherits its lineage's trials and holdout looks. None had a consumed look to inherit.

  | Revived as | From | Inherited trials |
  |---|---|---|
  | `silver-industrial-cycle-debit-r` | `silver-industrial-cycle-debit` v58 | 993 |
  | `etf-implied-move-ratio-follow-debi-3` | `etf-implied-move-ratio-follow-debit` v17 | 160 |
  | `second-session-assimilation-call-r` | `second-session-assimilation-call` v31 | 204 |
  | `tlt-realrate-metals-catchup-debit-r` | `tlt-realrate-metals-catchup-debit` v30 | 1,126 |
  | `market-distraction-release-call-r-2` | `market-distraction-release-call` v11 | 112 |

  Their notes ask for the validated version to be re-run unchanged under engine 4. The outcome is in the run record: the
  numbers came back identical, and the deflated-Sharpe check now fails.
- **The harness observer** has been on since 20:19Z, in observe mode (`state/harness/runtime.json`). No harness
  improvement has been retained.
- **20:42Z, architect agenda v15.** It steers only; D2 and every kill test are unchanged, and its text stays private.
- **Pull requests:** #427 and #430 closed, shipped through Release A; #428 closed, superseded by #447.

### 20:16Z, Release A: House release `20260930T200604Z-3bf48c3f8f9f` (main `777b894f`; PR #450), evidence reset 1

- **The deploy.** Staged 20:06:06Z; promoted 20:06:42Z. The ten-minute watch passed with 0 error alerts, and the
  verdict was PROMOTED at 20:16:42Z. The rollback target (`previous`) is `20260930T045038Z-cb6035693ef4`.
- **Money digest unchanged** (`a3e2aa7c`); no re-ratify.
- **Evidence reset 1, verified.**
  - The swarm recorded its evaluator (`research_evaluator`: the Gym bundle `gym-engine-4-e1c896f8d304`, the image and
    the execution fingerprint).
  - A read-only lineage snapshot before and after the deploy compared 1,585 lineages and found 0 violations:
    trials, inherited trials and consumed holdout looks were all unchanged, with 2 looks.
- **The live guards, verified.**
  - `house:rebound-live@0:h` is real, `observe` false, mode live.
  - The tuition instance `googl-lags-msft-ai-cloud-qqq-flat@27:t` came back `exit_only` by design. Adoption dropped its
    engine-3 tuition row: an engine-3 validation bundle, and a review with no `contract_sha`. Its open position is
    kept, and the program's own closes manage it. The family must qualify again under engine 4 to trade tuition again.
- **The restart test, passed.** `floor_box.py stop` at 20:19:00Z and `start` at 20:19:17Z, with that real position open.
  - Both instances came back as above.
  - The position was restored.
  - `real_money` was true, and `failures` was empty.
- **The induced-failure test, passed.** At about 20:50Z the swarm process was killed with SIGKILL.
  - The House's swarm step restarted it within 15 s, with a fresh heartbeat.
  - The alive families (15) and the runs (75,473) were unchanged: nothing was lost or duplicated.
- **The first hour (20:17-21:21Z, read-only).**
  - 0 cycle errors; House load 0.72.
  - 136 Train runs ok, 17 disqualified (11%), 8 validations.
  - Births: 7 debit verticals, 3 `long_single`, 2 `long_call`.
  - The tournament spread its shares at about 10-13% a family.
  - The population fell from 41 to the floor of 12 within 10 minutes of the deploy: researchers now retire the
    mechanisms they refuted (R11b). The architect refills up to 12 births every 20 minutes, on Kimi-K3.

Release A was branch `release/a-20260930` (PR #450), merged to main as `777b894f`:
- main `f082cf5e`, which carries #431-#436, merged Sept 30 between 05:59 and 08:27Z;
- plus six reviewed pull requests merged on the branch: #437, #443, #440, #439, #442 and #441.

- **Evidence reset 1.** The evaluator's execution fingerprint and the Gym bundle both moved:
  - the fingerprint (`league/swarm/evaluator.py`) hashes `league/gym`, `league/live` and `LEAGUE_FILES`;
  - engine 4 (#431), #436's driver, the Gym batch isolation (#440), the live guards (#437) and the decider (#443) all
    change those files.

  The release before it had no evaluator record, so Release A's first start adopted one for every alive family:
  - **Cleared, and archived in the family's state:** Train bests, candidates, robustness, drift, validation and review.
    A Candidate, Probe or Sized family whose banded evaluator no longer matches returns to the Gym. Every family was in
    the Gym.
  - **Kept:** runs, versions, lineage trial counts, refusals, notebooks and consumed holdout looks. Consumed holdout
    looks never reopen.
  - **Practice** started under the new evaluator. It needs Train runs under the new bundle, so the practice league
    started nearly empty.

  Evidence from before and after the reset is never compared.
- **The House live test.** Release A changed the test's order path: the belt it passes, and the decider child it runs
  in. The test's own program and bounds are unchanged. The change is still to be recorded as a deviation in the test's
  private addendum, with Release B's.
- **Operator steps after promotion:** [docs/operations.md](docs/operations.md), "Release A: after promotion".

#### On the release branch

- **Live guards from #427, on main** (#437; money path). Two guards:
  - `Instance.observe` is True only for a shadow, non-tuition `:o` instance. A bad value is coerced, never raised. So
    a real instance, the House live test's included, is never an observe one, restored or not.
  - A belt in `_real_intent` refuses any instance that is not real, whose observe flag is not False, or whose key is
    an observe key. It covers opens, closes and cancels alike, and raises an error alert: "live: `<key>` is not a real
    instance and asked for a real order: refused".

  Tuition and the House live test pass the belt. Calibration never takes this path. Tests:
  `league/tests/test_live_restore.py`.

  After the deploy, check:
  - `options_live.instances["house:rebound-live@0:h"].observe` is `false`;
  - every `:o` instance is `true`;
  - no "not a real instance" alert.
- **The live Decider hardened** (#443; money path).
  - **A failed network-namespace probe is retried**, not cached. Before, a probe that timed out on a busy minute was
    kept as a permanent False: every later spawn on the root House failed until a restart. Real instances would then
    be orphaned and closed after five minutes.
  - **The probe's timing:**
    - its timeout is 3-10 s, whatever is left of the minute;
    - after a failure, spawns inside 30 s are refused without probing;
    - a spawn after that probes again.
  - **Fails closed off a root House.** A `Decider` not running as root refuses to start a child. Only tests pass
    `allow_unisolated=True`; there is no switch for it.
  - **Child limits:** the child caps any file it writes at 64 MB (`RLIMIT_FSIZE`) and can start no process or thread
    (`RLIMIT_NPROC` 0).
  - **Logs:** before each spawn, the House moves a decider log of 32 MB or more to `<log>.1`.
- **Gym: one bad program no longer fails its batch** (#440; `league/gym`, money path).
  - **The incident, 14:03Z Sept 30:** one program parsed but did not compile. It raised `SyntaxError` in the batch's
    load check, and all eight families in the batch got "the Gym failed twice".
  - **Admission:** `check_program` now compiles as well as parses, so such code is refused at admission, with its line.
  - **Per-program results:**
    - any load failure in the parent is that program's `refused` result;
    - a load failure in a worker, or an exception from one program's run, is that program's `error` result, with 0
      trials;
    - the rest of the batch runs on, and its results are byte-identical to running those programs alone.
  - **Still whole-unit failures:** a `MemoryError`, a dead worker or the unit deadline.
- **Funding alerts before the Claude, OpenAI, Sail and burst cliffs** (#439; research-side, no fingerprint move).
  - A new `league/swarm/funding.py` runs on the swarm's loop. It covers four cliffs:
    - Claude's room: a runway from measured burn;
    - the Sail guard's line: a runway;
    - the gateway's OpenAI month end: calendar;
    - `guard.burst_until`: calendar, with the research cut.
  - **Tiers** are notice, warning, urgent and out.
  - **Dedupe:**
    - each tier is said once;
    - warning, urgent and out repeat every 12 h while they stand;
    - a recovery is one `funding_ok` event.
  - **Fallbacks:** every call that asked Claude and ended elsewhere is counted as a `claude_fallback` event. Only
    `no_room` is an alert.
  - **Where it shows:** alerts reach the House as `ops.alert` warnings, never errors, so they never roll a release
    back. The last assessment is in the heartbeat under `status.funding`.
  - **The site shows none of it.**
- **CI never cancelled by its own time limit** (#442).
  - The Checks `tests` job limit is 35 minutes (was 20). The Sept 30 push run on `f082cf5e` was cut off at 20 minutes,
    which the updater reads as no verdict.
  - The hourly run has its own concurrency group, so it no longer cancels a push run on the same ref.
  - CI keeps the tests' scratch on tmpfs (`/dev/shm/ltcm-tests`) when it can.
  - Faster league tests, with the same coverage:
    - the fake market prices a chain once per read;
    - the swarm tests share one Gym bundle version;
    - the hung-decider test uses a 0.75 s budget.
  - `TRUSTED_WORKFLOWS_SHA256` in `league/updater.py` moves to `9aa3c732` in the same commit: a workflow change is an
    owner deploy.
  - No fingerprint or money-digest move.
- **Public site cost** (#441; the site side is personal-site PR #17). Not the money path.
  - **Sail on its billed basis:** the Sail guard's balance meter, plus $0.46 of box billing before the meter began.
    Before, it was the Gym's booked box estimate, which runs about 70% above the bill.
  - **Claude as its own part**, `claude_usd`.
  - **Older-site fallback:** the House tries each older shape alone before both.
  - **The site:**
    - shows Net = realized options P&L since T0 minus every input cost since T0, a dash while any part is null or
      stale;
    - shows the costs by service, the practice league's block and the Incubator label.

  Either repository may deploy first.

#### From main `f082cf5e` (#431-#436, merged Sept 30)

- **Engine 4 and evaluator adoption** (#431; `league/gym` and `league/live`).
  - **Engine 4** (`gym-engine-4`) binds parameter overrides to module `PARAMS` at its declaration, before aliases and
    helper defaults capture them. `ctx.params` starts with the same values.
  - **The evaluator record:** at startup, before any worker selects, the swarm records its evaluator
    (`research_evaluator`: the data image, the Gym bundle and the execution fingerprint). A change is adopted as
    Release A's reset describes (above).
  - **Entry authority:** Candidate, Probe and Sized entry also pins the program hash and the fingerprint
    (`banded_evaluator`). An old fingerprint denies new opens, and exits go on.
  - **Worker run ids:** colliding ids across evaluator bundles keep separate results.
  - **Pre-deploy scan** (read-only, Sept 30): engine 4 loads all 106 programs, meaning the alive families, the practice
    tier and the House test's. The House test's program gives identical intents under engines 3 and 4 on synthetic
    data. Two alive programs read module `PARAMS` with overrides and will behave differently; the reset keeps their
    evidence apart.
- **Research that waits for news, and retirement that can land** (#431).
  - **Holds:** `researcher.hold_until_news` (default true) stores a hold in the family's state. Only new evidence, gate
    state, guidance, the agenda, the image or the harness release wakes it; time and restarts never schedule another
    paid call.
  - **Retirement:** a researcher may retire after `researcher.retire_min_trials` (10) counted trials or two
    validations, on either turn, down to `population.floor`.
  - **The experiment-contract check:** `gym_run` and every `gym_sweep` variant pass a static check (`check_experiment`)
    before a version or Gym job exists. Unread parameter changes and malformed overrides are refused without a trial.
  - **Graveyard format 4:** economic claims are limited to the versions tested.
  - **Grounded reviews:** the gate's reviewer and auditor read the runtime's actual contract
    (`league/gym/review_contract.py`).
- **Causal optional volume context** (#431).
  - **What reaches a strategy:** share bars reach strategy contexts only with first-observation receipts and explicit
    provenance and coverage.
  - **Finalized historical bars without those receipts stay unknown**, daily sums included: a completed-minute grid
    does not prove what was published then.
  - **Live:**
    - reuses existing stock snapshots;
    - persists first observations across restarts;
    - excludes incomplete bars and index proxy volume.
  - **Test:** a late-revision regression checks that finalized history cannot replace the first live value.
  - **Not changed:** no data purchase, production mutation, SQL or site migration, or money-rule change.
  - Actual live coverage remains to be measured after adoption.
- **Persistent practice cohorts and receipts** (#431, building on #430's code).
  - Immutable shadow snapshots survive research churn and restarts. Bounded observation windows include longer-DTE
    programs.
  - No snapshot is promoted into real money.
  - Private receipts (decision, order, quote, fill, slippage) retry across restarts.
  - Program errors reduce coverage, and open marked P&L includes fees already paid.
  - Material researcher feedback requires ten program closes over three sessions.
  - Sized's fresh-forward window starts after both the creation and the selection of its version.
  - New cohort, receipt and feedback tests use simulated quotes only. Actual multi-session practice evidence remains to
    be collected after deployment.
- **The live practice league** (#430's code, merged through #431; #430 itself stays open and is closed as superseded
  after Release A).
  - **What it is:** every alive Gym-band family with a validated version, or an eligible Train version (the
    tournament's candidate, not demoted), trades live quotes in the shadow book under the Gym's fill rules, on a
    $10,000 practice account.
  - **What it is never:** real, tuition, a forward row, or a band move. Release A's #437 guards hold this in code.
  - **Admission:** validated by validation t, then Train by Train score, under two caps:
    - `live.observe_max` (48);
    - `live.observe_roots_max` (24 distinct roots, the binding resource measured on the House Sept 29).

    `live.observe_train` and `live.observe_read_calls` are set in `swarm.json`.
  - **Pressure:** sustained pressure (3 pressed minutes of 10) sheds the lowest-priority quarter of the Train pins for
    the session. Validated pins are never shed.
  - **The practice ledger** (`observe.sqlite`): per family and version from its first live minute, kept after
    retirement. It holds:
    - realized P&L after fees (the headline);
    - forced wind-down closes, apart;
    - open positions at the engine's mark;
    - realized and marked drawdown;
    - coverage.

    `practice_summary` is read-only.
  - **Research feedback** (`league/swarm/practice.py`, `practice.feedback`):
    - the strategist's PRACTICE table;
    - the architect's PRACTICE BY CLASS lines;
    - the bandit's bonus: at most +25% of a family's share and at most 10% of all share moved. It changes the weight
      only, which nothing on the way to real money reads.
  - **The forward embargo:** a Sized move also needs the forward record after its version was written and selected. It
    is a tightening; nothing is Sized today.
  - **The site's `practice` block:** personal-site PR #17 takes it. Until that site deploys, the House posts without it
    and warns once.
  - **Unchanged:** the money digest stays `a3e2aa7c`, and D2.
  - **After the deploy, check:**
    - `options_live.observe` shows `tiers`, `roots_used` and `effective_cap`, and no `shed`;
    - `observe_reads_skipped` stays 0;
    - `observe.sqlite` `practice` rows appear from 13:31Z;
    - there is no `:o` in `live.sqlite` or in the swarm's `forward`;
    - the tournament event's `practice_bonus` values are at most 0.25.
- **R11b: honest verdicts, corrections that land, effort where it pays** (#431). These are the ROI plan's R11 code items
  (Sept 29, section (b)). Research-side only: the money digest stays `a3e2aa7c`, and Train figures only (D2).
  - **R11-1, verdicts and retirement:**
    - an idle-rule death is filed under its Train record's verdict: DRIFT, STRESS, THIN or EXHAUSTED, and IDLE only
      for the untested;
    - the digest (format 3: one reseal) and the strategist (`screen` per family) read the verdicts;
    - a family holding three cycles with an eligible run, or ten trials, is offered `retire`;
    - a researcher's retirement is SELF-REFUTED;
    - `scripts/graveyard_verdicts.py` re-heads the rows already buried (the operator's; a dry run by default).
  - **R11-2, the strategist and the class cap:**
    - known ids are masked before the strategist's content rules;
    - the prompt aims at 85% of the cap;
    - a length-only overflow up to 15% is trimmed at a sentence end;
    - `architect.max_alive_per_class` (12) caps births per mechanism class.
  - **R11-3, effort:** `claude.role_effort`. A cut architect answer keeps its complete families with one medium retry
    on Claude, never a Kimi-K3 refill.
  - **R11-5, exploitation:** the bandit exploits only old families with a positive validation mean, 15% each at most.
  - **R11-6, the Gym's zero-trade probe:** off until `researcher.probe_year` is set.
  - **R11-4's rule, the extension hold:** a validation that met six checks holds its family out of the dormancy clause
    until the operator clears it (`scripts/extension_hold.py`).

  Operator steps after the release: [docs/operations.md](docs/operations.md), "Release A: after promotion". A4 was never
  applied, so `tournament.explore_share` needs no change.
- **Two-sided singles: the `long_single` structure** (#425, merged through #431).
  - **What it is:** a family may declare `long_single`, one program that opens one `long_call` or one `long_put` at a
    time (one leg, long), the side chosen by its rule. It takes the place of a call/put twin pair.
  - **The architect:**
    - its prompt describes the side rule, and why its calls and puts balance: the drift screen charges whatever net
      exposure it holds;
    - it asks for no twins;
    - `admit` refuses a one-sided twin beside a living `long_single`, or the other side of the same idea on the same
      roots.
  - **GAPS and coverage:** in GAPS, a single option's one gap is `long_single`. The one-sided singles are no longer
    gaps, though they are still admitted. Coverage has its row.
  - **Prompts:** the researcher, reviewer, auditor and diagnostician read what its orders are.
  - **Lineage:**
    - it shares its singles' slice for lineage matching and identical-code links;
    - a `long_single` that continues one twin joins the other twin's lineage too (`link_lineages`);
    - a new lineage on a singles' slice counts the newest dead lineage of each type there (`slice_priors`,
      `prior_lineages`). Every other structure keeps its one prior.
  - **Real money:**
    - real eligibility (tuition, Probe, Sized, the site's `real_structure`) needs BOTH `long_call` and `long_put` among
      `options_money.real_types`;
    - every order keeps its own type, is checked by it at the real book and the gateway, and is sized by its own unit;
    - the live path refuses a real open of any other type from a `long_single` family.
  - **The site** shows the agent's structure as null (its schema has the eleven order types) and each position as its
    own type.
  - **Unchanged:** no Gym, verifier, D2, drift-screen, gateway or money-table change. The money digest stays
    `a3e2aa7c`.
  - **Rollback:** once a `long_single` family exists, roll forward rather than back past it. A release before it fails
    every architect pass.
- **Benchmarks and the harness controller** (#431).
  - `python -m league.swarm.benchmarks` runs synthetic statistical controls through the actual Train, Validation and
    holdout arithmetic. These are not market evidence.
  - A protected Scheduler-lane harness-improvement journal, with sandboxed comparisons
    (`playbooks/harness-improvement.md`).
    It authors and deploys nothing itself.
- **Research supervision and honest cost evidence** (#432).
  - **The harness observer:** a release-bound, read-only observer with a private policy. It is off until the operator
    writes its `runtime.json`.
  - **The input capability card:** researchers and the architect read a private card of Train-image coverage
    (`input-capabilities.json`; historical volume stays unavailable).
  - **A frozen `long_single` gate benchmark**
    ([docs/benchmarks/LONG_SINGLE_GATES_1.md](docs/benchmarks/LONG_SINGLE_GATES_1.md)).
  - **A private project-economics report**, which keeps holds, estimates and settled bills apart
    (`playbooks/project-economics.md`).
- **Historical SIP completion that keeps its gaps** (#433).
  - A durable per-root, per-day gap queue lets the scan advance past a missing root.
  - Only complete, validated minute grids replace canonical data.
  - Image readiness is bound to verified file hashes and the intended image pair
    ([docs/data-sip-completion.md](docs/data-sip-completion.md)).
  - After the deploy, the data side needs `sip-progress.sqlite` and a rescan of legacy readiness.
- **One agenda read per scheduler scan** (#434, `league/swarm/loop.py` only). Measured on synthetic populations of 7-127
  held families: 40-49% fewer SQL statements a scan, with unchanged semantics. This is not a retained harness
  improvement.
- **A finite local practice runner** (#435; `scripts/practice_run.py`, [docs/local-practice.md](docs/local-practice.md)).
  - It runs explicit replay or synthetic bundles in a mandatory bwrap sandbox, with no brokerage account and no House.
  - It never writes bands, forward evidence or feedback.
- **Gym result downloads retried** (#436, `league/gym/driver.py`).
  - A timed-out or dropped download of a finished Gym result is retried inside the driver's existing attempt limit and
    backoff, instead of requeuing the batch.
  - TLS, permanent DNS, permission and unknown failures are not retried.
  - The driver is part of the Gym bundle, so its version moves.

### Earlier on Sept 30

**16:41Z, operator change** (no deploy): the spend cut. The owner's Sept 30 answer was to cut burn to evidence, roughly
halving the $84-104 a day. `swarm.json`:
- `claude.role_usd_day.architect` 10 → 0: architect births go to Kimi-K3 on Sail;
- `researcher.stall_revisions` 12 → 10000: stall rewrites off;
- `diagnostician.enabled` unset (on) → false;
- `researcher.sail_usd_per_hour` 4 → 1.1.

The gate's review and audit and the strategist stay on Claude. The evidence and the target are in the run record
(`docs/runs/2026-09-30-continuous-learning.md`): about $2.10 an hour, about $50 a day. `live.*`, calibration and the
House live test are unchanged.

**16:07Z, operator change** (no deploy): an interim research throttle, because Train evidence from before Release B is
archived by the night's evidence resets. Backup `swarm.json.before-set-20260930T1607*`. `swarm.json`:
- `gym.max_boxes` 16 → 4;
- `gym.start_boxes` 6 → 2;
- `researcher.sail_usd_per_hour` 12 → 4;
- `architect.max_refill` 12 → 4;
- `claude.role_usd_day.architect` 25 → 10.

`live.*`, calibration and the House live test are unchanged. After Release A: `gym.max_boxes` 6 and
`architect.max_refill` 12 again.

**05:01Z, restoration fix: House release `20260930T045038Z-cb6035693ef4`** (main `87af7a62`; #429).
- Promoted 04:51:15Z; ten-minute health watch passed at 05:01:20Z.
- Real instances restore by keyword, keeping `observe` false and the saved execution mode.
- Verified on the running House: `house:rebound-live@0:h` is real, `observe: false`, mode `live`;
  supervisor and House alive, health fresh. No options or working orders before the restart.
- Money digest remains `a3e2aa7c`; the grant and accounting baseline were not changed.

## 2026-09-29

**13:44Z, R11a: House release `20260929T134303Z-8366493c614c`** (main `2f6d5109`; #424, Train from 2017).
- The first research-side release under the owner's amended D8: research releases may ship during the session when
  nothing in the money path changes.
- No file under `league/live`, the gateway or the constitution changed. The money digest is unchanged (`a3e2aa7c`).
  0 real positions and 0 working orders at deploy.
- On the box: 0 `train_span_mismatch` events, the swarm cycling (171 cycles and 63 runs in the first minutes), the
  backfill controller alive.
- `gym.train_from` stays 2020-01-02 until image T (2017-24) is built, bridged and pool-checked.
- What #424 carries:
  - **The window.** Train's window, `storelib.TRAIN_EARLIEST` and `gym.train_from` reach 2017-01-03. That is a third
    start beside 2020-01-02 and 2022-01-03; over eight years the derived split is 24 and the time limit 2400 s.
    Stage 9's `EARLY` stays the literal 2020-01-02..2021-12-31.
  - **New public tables:**
    - the 2017-2019 scheduled FOMC days (Federal Reserve meeting pages);
    - CPI and Employment Situation release days (BLS release archives);
    - the rate steps back to 2015-12-17 (the Fed's target-range changes, upper bound less 0.10, as before).
  - **First Train day.** A Gym store's first Train day is its first chain, so a 2020 image's 2019 history sessions stay
    out of Train. `images.py build gym --root-first ROOT=DATE,...` gives a root its own later first Train day, recorded
    in images.json and checked from inside. The fork prunes with the build's own data tools.
  - **A build from 2017** lists its roots and refuses unless every name (a root outside the core five) either has a
    first day on or after 2020-01-02 or is named in `--early-names` (for after its split rows are in). It refuses
    `--early-roots`.
  - **The inside check** holds every other name to 2020-01-02, and the image's first chain to its `train_from` exactly.
    `images.py verify --root-first` reads the recorded `train_from`.
  - **Nothing moves** until an image is built with `--train-from 2017-01-03` and `swarm.json` names it with
    `train_from`.
  - **On release** the Gym bundle and tables digests changed, so every program re-runs once as a new trial and each
    family is re-validated once, as with #399.

**13:36Z, operator change:** `live.observe_max` 8 → 48. **13:20Z:** `architect.max_refill` 24 → 12,
`architect.every_seconds` 600 → 900.

**06:58Z, operator change** (no deploy): the strategist switched on.
- `architect.agenda_locked` is the operator's preamble: agenda v14 without its WHERE TO LOOK directions, plus two
  new binding lessons, that widening does not create edge and that the rebound's 2024 survives every regime gate.
- `claude.roles` adds `strategist`; `claude.role_usd_day` sets architect $25 and strategist $4; `strategist.enabled`.
- Backup `swarm.json.before-strategist-20260929T065848Z`.

**06:48Z, R10: House release `20260929T064727Z-c607a8aa390e`** (main `a700c3ba`; #419).
- The architect reads the whole graveyard as a digest in its Claude context.
- The strategist writes the WHERE TO LOOK section under the locked preamble, with a validator that refuses rule,
  money, threshold, 2025 and override talk.
- 2025 Validation figures are filtered out of every graveyard view shown to models (82 of 809 lessons still carried
  them).
- The money digest is unchanged (`a3e2aa7c`). Backup `state/backups/pre-r10`.

**06:02Z, operator change** (no deploy): `claude.roles` adds `researcher`, so the bandit's top 12 families run
their research cycles on `claude-sonnet-5-5` (medium effort; line `claude.role_usd_day.researcher` $100; the
breaker and every failure fall back to the family's Sail profile). First Claude cycles at 06:02:43Z ($0.07) and
06:03:00Z ($0.04).

**05:52Z, R9: House release `20260929T055159Z-40163c0de3e9`** (main `31853932`; #417). The money digest is unchanged
(`a3e2aa7c`). Backup `state/backups/pre-r9`.

**05:51Z, gateway `ac2779ac`** (#417): the Claude route admits the House's custom tools and tool-loop turns (no
server tools, no forced tool choice); the price rows carry `geo {us: 1.1}`; overruns are counted in `/v1/health`.
`CLAUDE_USD` is still $200.

**05:29Z, gateway `8d80d2f7`** (#420): the owner added $100 to the Anthropic account (its balance then read
$140.54), so `CLAUDE_USD`, the funded total, is $200. The meter had $80.33 spent, which leaves $119.67 of room,
below the account's real balance. Operator change at the same time: `claude.usd_cap` 98 → 198 (the swarm's line
inside it, keeping $2 for the House's own calls). The owner also added $200 to Sail.

**04:53Z, operator change** (no deploy): every paid role on Claude, after R8. `claude.model`
`claude-sonnet-5-5`; `claude.roles` architect, audit, diagnostician, rewrite and review;
`claude.role_usd_day` rewrite $15 and review $5; `claude.role_model` the audit on `claude-opus-5-5`, so
the gate's two reads stay two different models; `gate.review_openai_model` and `gate.audit_openai_model`
null. With `architect.openai_model` already null, no role calls OpenAI.

**04:42Z, R8: House release `20260929T044127Z-2c265b03bc04`** (main `8074e262`; #414, #415, #416)

- #414: the graveyard is ranked by BM25 (a word's repeats saturate and long rows are discounted, so long
  lessons no longer crowd out short ones), and a new family is born with three distinct lessons.
- #415: Claude Sonnet 5.5 (`claude-sonnet-5-5`) priced in the House's hold ceilings.
- #416: Claude may also take the researcher's stall rewrite and the gate's program review (operator
  opt-in through `claude.roles`), with per-role daily lines (`claude.role_usd_day`) and per-role models
  (`claude.role_model`); the gate alerts `same_reader` when one model both reviews and audits.
- The money digest is unchanged (`a3e2aa7c`); the grant stays active. Promoted 04:42:07Z; the ten-minute
  watch passed (verdict 04:52:09Z); its files on the box match main `8074e262`.

**03:59Z, the gateway** (#415; version `7eaede72`): `claude-sonnet-5-5` added to `CLAUDE_MODELS` at its
list prices ($2 input, $2.50 five-minute cache write, $0.20 cache hit, $10 output per million tokens).
`CLAUDE_USD` unchanged at $100.

**00:17-04:00Z, operator changes** (no deploy)

- 00:17:28Z `live.house_test` on, after the test's analysis script was pinned. Its files read verified;
  no trade yet.
- 02:30Z agenda v14 (steering only: D2 and every kill test unchanged; the text stays private).
- 03:35Z operator lessons (`op-` ids) inserted into the graveyard, with a backup: 45 by 04:33Z.
- 03:40-04:00Z the owner's decisions (Claude Sonnet 5.5 throughout; only Sail and Claude topped up from
  now on; "remove any limits that would inhibit this goal"): `architect.openai_model` null (the architect
  is Claude-only), `architect.every_seconds` 600 with `max_refill` 24, `population.start` 96,
  `gym.max_boxes` 16, `researcher.sail_usd_per_hour` 12, `researcher.top_families` 12, the
  diagnostician at $60 a day, 6 a round, every 3 hours a family. The Sail guard's $32 line is unchanged.

**00:06Z, the site** (personal-site #16; version `dcd61fbc`): the positions table labels the House live
test's rows "House live test".

## 2026-09-28

**23:55Z, R7: House release `20260928T235447Z-6005f971ffc5`** (main `6c2de074`; #410, #412)

- #410: five 2020-21 stock splits in `events.SPLITS`. #412: the House live test
  (`league/live/house_test.py`, off by default).
- The money digest moved `ad9bd54c` → `a3e2aa7c`: only the test's own bounds
  (`options_money.house_test`), approved by the owner at 22:55Z. The grant was re-ratified at 23:56:41Z:
  active on `a3e2aa7c`, capital $1,473.11. Backup `state/backups/pre-r7`.
- Verified: `health.json` `options_live.house_test.files` verified; the positions table still adds up
  to Profit.

**22:20Z, the grant** (no deploy): re-ratified once the owner's deposit reached options buying power.
Capital $481.63 → $1,473.11, the lower of equity and the $5,500 ceiling; the digest unchanged.

**20:08Z, R6: House release `20260928T200729Z-5bdeb710c88b`** (main `2981566d`; #409)

- #409 carries #404 (payoff-range fills and marks), #406 (stock splits from a public table), #407 (the D3
  calibration's six hourly slots on SPY, QQQ and IWM with a 25-minute patient mid cell, the same $50
  bound) and #408 (the positions ledger; Profit includes calibration and the broker's fees).
- The money digest is unchanged (`ad9bd54c`). Verified: the positions table's rows add up to Profit.

**16:59Z, the site** (personal-site #15; version `d6e485c0`): the positions table under the chart, an
opt-in read (`GET /api/capital/checkpoint?progress=1&positions=1`).

**16:13Z, Train 2020-2024** (an operator image adoption, no deploy): the sealed 2020-24 Gym image and
`gym.train_from` "2020-01-02" in `swarm.json`; 38 families migrated, 0 failed.

**14:04Z, R5b: House release `20260928T140336Z-766c07a9691b`** (main `2e51ea71`; #405)

- The funding read left out WIRE, which Alpaca's activities filter refuses; the failed read had blocked
  every real entry at the open. The owner's exception to the trading-day freeze.
- The money digest is unchanged. Verified: at 14:06:41Z nothing blocked real entries; the first D3
  round trip followed at 14:08Z.

**06:58Z, R5: House release `20260928T065759Z-aae7108eda03`** (main `9fe54351`; #399): the Train 2020-21
code with the switch off. Verified: the pre-open checks 9/9, no span alerts.

**06:16Z, R4: House release `20260928T061526Z-971da2b2e678`** (main `7effc585`; #403, which carries #401
Gym memory, #402 the hold backoff and the idle pass, and #398 the drift screen). The money digest is
unchanged. Verified: 0 cycle errors after the restart; the pre-open checks 9/9.

**02:56Z, R3: House release `20260928T025520Z-8d5e8eec714a`** (main `e4c9fe5a`; #394, #397): mirror and
backup-box fixes, `gym_sweep`, the idle rule, stored results for identical runs, holds and the dormancy
clause, and the operator's gate hold. The money digest is unchanged (`ad9bd54c`). Sail could not
checkpoint (503), so a SQLite backup is at `state/backups/pre-r3/`.

## 2026-09-27

**13:49Z, the site** (personal-site #14; version `84fedf26`): the balance chart starts after the owner's
deposit.

**01:00Z, the refitted Gym and gate images** (no deploy): fitted on Train `trade_quote` samples only with
#387's estimator, adopted in `swarm.json`; the House restarted at 01:01-01:02Z so the Gym, the gate and
the live shadow share one fill model.

**00:30Z, R2: House release `20260927T002925Z-2bfef7a749bf`** (main `440f6de4`; #387, #390, #391, #392)

- #387 the honest fill model; #390 the live path for Monday (the observe band, long calls and puts as
  real types, the D3 calibration, the D4 money table); #391 Claude streaming; #392 `real_money` true.
- The money digest moved to `ad9bd54c`. The grant `options-swarm-20260928` was enabled at 00:30:15Z,
  capital $481.63. 00:31Z `live.observe` on (at most 8) and `live.calibration` on.
- Verified: the ten-minute watch passed (00:40Z).

## 2026-09-26: the options overhaul and the sprint's first release

**23:41Z, the gateway** (#391; version `953a9b46`): Claude streaming. A probe settled at $0.001.

**23:18Z, the gateway** (#390; version `9634002d`): `OPTION_STRUCTURES_REAL` the four debit types
(`debit_vertical,long_butterfly,long_call,long_put`) and `MAX_ORDER_EQUITY_SHARE` 0.25.

**23:00Z, R1: House release `20260926T225946Z-22b18ea9f452`** (main `5ba25909`; #378, #379, #380, #382,
#383, #386, #388, #389): the Claude route's House side (Claude-first architect and audit, the
diagnostician), the robust Train objective and D2. The money digest is unchanged (`8dba0b1f`). Verified:
the migration re-picked 34 families' bests with 0 errors; the diagnostician's first Claude calls.

**22:37Z, the gateway** (#388, main `13963028`; version `42e443bb`): the Claude route and its funded
meter, `CLAUDE_USD` 100. A probe call settled at $0.001.

**22:10Z, the site** (personal-site #13; version `5ce5265c`): progress checklists accept the D2 line.

**21:24Z, the sprint's Wave 0** (no deploy): `swarm.json` settings (population floor 44, the
architect's refill, retirement at 200 revisions or 4,000 evaluations), a calibrated Gym image and the
gate on its paired gate image.

**20:57Z, the gateway** (version `cd0588b5`): a secret change, no code (Cloudflare's source "Secret
Change"): `CLAUDE_API_KEY` was added, the owner's D7. Not in the run record.

**18:18Z, House release `20260926T181814Z-b4bc25619f84`** (main `60b34dd9`; #377, the publisher's agent
progress). The site's #11 (18:05Z, `7959f35b`) and #12 (18:16Z, `e473bcbc`) went first.

**17:56Z, House release `20260926T175520Z-f47c08cd0535`** (main `8c9216b6`; #376, researcher retirement).

**17:26Z, House release `20260926T172613Z-f62e2af878bb`** (main `7645e202`; #372, #373, #374: the Sail
research pace, the paper route's readiness, the researcher protocol).

**16:50Z, House release `20260926T164943Z-04457584301d`** (main `4472c334`; #362 the live path, #371)
and **16:49Z, the gateway** (version `20a6b706`, `OPTION_STRUCTURES_REAL` off). The money digest moved to
`8dba0b1f`; no grant was enabled. The site's #10 went first (16:42Z, `2506e646`).

**16:11Z, House release `20260926T161049Z-6a9300a67fbb`** (main `570f023c`; #365-#370).

**15:52Z, the gateway** (#368, main `647c8384`; version `e602bdb4`): the OpenAI September cap $707.

**10:55Z, House release `20260926T105515Z-b25acc7981e2`** (main `e6a020dd`; #363, the swarm's loop).

**10:22Z, House release `20260926T102142Z-e71ed057c625`** (main `310225ae`; #361, #364). The new House
started at 10:22:29Z; the swarm founded 48 families.

**08:53Z, the gateway** (#361, main `3f660144`; version `8054eecb`): `SAILBOX_ID` the new House box.

**08:49Z, the first House release on the new state root: `20260926T084913Z-8158a11cfe3f`** (main
`b68b3800`; `real_money` false). Promoted with the loop stopped. It is the rollback floor.

### Before the first House release

**Merged, not yet deployed to the House**

- 06:39:40Z #356, the plan (`docs/goals/LTCM_OPTIONS_SWARM.md`); main `46ec3433`.
- 07:21:04Z #357, the publisher's schema 2 for the options site; main `d1855afc`.
- 07:49:22Z #359, the House options-only (Wave 2a): `auto_update` false and a missing key means off;
  `floor_box.py` and `gateway_admin.py` off the legacy package; the grant `options-swarm-20260928`
  in `league/live_trading.py` with every real-money call site asking it; no Kalshi, Jev, lab,
  foundry, semantic lab, feed, campaign or pacer piece in the service or the tick; the config's dead
  keys removed; CI runs the Gym's dependencies; Merton never auto-merges. `real_money` false. Main
  `6c715d83`.
- Open: #358, the Gym (`league/gym/`), under review.

**07:21Z, the site** (`~/Work/personal-site` PR #9, schema 2; Worker version `650a8ac1`)

- Deployed, then reset with `/api/capital/reset?confirm=erase-everything` on the real record and the
  `test` and `canary` tapes. The real record's 20,000 events, 1,604 history points, 1 checkpoint and
  136 desks were cleared.
- The reset pair: `PERFORMANCE_START_AT` 2026-09-26T06:25:30.000Z, start equity $481.65, the same as
  `performance` in `league/config.json`.
- Verified: all three checkpoint routes answer 404 until the new House publishes; the page reads "AI
  agents trading options." and its HTML names no venue (re-checked read-only at 07:54Z).

**06:24-06:58Z, the old House stopped and archived** (Wave 0; no deploy)

- 06:24:56Z the old House stopped (`floor_box.py stop --reason "options overhaul"`) on release
  `20260926T032739Z-aaf5ac74637c` (Deploy G, main `a1f9a8e7`), paused for maintenance since
  03:55:56Z: 128 agents alive in 121 families, 627 dead.
- 06:25:00Z the old grant `earned-live-20260921` disabled.
- 06:25:30Z the Brokerage Account's leftovers closed: two resting crypto sells cancelled, SOL and XRP
  sold; equity $481.65, with $0.03 of LTC dust kept as a legacy holding outside P&L.
- 06:33Z git archive: tag `archive/pre-options-2026-09-26` at `89bc49a1`, 78 branch tags
  `archive/branch/<name>`, laptop-only branches bundled on the owner's machine; 14 open pull requests
  closed with a comment naming their tag.
- 06:36Z the old state moved aside to `/workspace/archive/state-pre-options-20260926` on the House
  box and a fresh, empty `/workspace/state` made; 06:54Z its tarball written (8,256,763,269 bytes,
  sha256 `e9e5c04482a3321707902dd376a9902fe260954cd76cbe204eec89be6a16256f`, `gzip -t` OK). Two
  checkpoints of the House box failed (Sail 503, 06:35Z and 07:00Z).
- 06:37-06:39Z 420 old Sail boxes terminated (agent sandboxes, lab and foundry boxes, canaries).
