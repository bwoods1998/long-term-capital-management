# Kalshi at scale — September 25, 2026

Execution record for the owner's goal of Sept 25, 2026: execute
[the Kalshi-scale plan](../goals/LTCM_KALSHI_SCALE.md) autonomously, with no deadline, beside the
forward-first run ([its record](2026-09-25-forward-first.md) on `run/forward-first-2026-09-25`) and the
options run ([its record](2026-09-25-options-desk.md) on `run/options-desk-2026-09-25`), until its Done
list holds.

## The clock

- **T0:** 2026-09-25T06:05:01Z (the session's first `date -u` after reading the plan).
- **No deadline.** The run ends when the plan's Done list holds. A context reset does not end it.
- **Windows:** Friday's US session 13:30-20:00Z has no deploy (13:25-20:05Z). The weekend has no stock or
  options session; its deploy windows are the hours when no game a real Kalshi family holds is in play
  (Friday's MLB slate runs to about 03:00-05:00Z Saturday). Saturday 15:00Z is K1's acceptance line
  (founders seated on every league with a slate). The watch runs every 30 minutes from Saturday 15:00Z to
  Sunday 23:59Z; the report is at Monday Sept 28 13:00Z.
- **Progress notes:** a scoreboard reading and a short state note at Saturday's close, Sunday's close and
  Monday 13:00Z, and a line at every deploy.

## The owner's message (Sept 25, 2026, at T0)

- The /goal text is the plan's last section; the session received the "Method" line with words run
  together ("builders in workmoney code, verify on thebox in each window ... report at Monday 13:00Z
  wireport's numbers and mynext decisions"). **Read as** the plan's own copy: builders in worktrees,
  adversarial review of money code, verify on the box in each window, watch the weekend every 30
  minutes, fix bugs with tests, report at Monday 13:00Z with the scoreboard, the scale report's numbers
  and the owner's next decisions.
- **Authority:** the forward-first plan's "Authorized" list applied to this run's workstreams, plus this
  plan's money table (K5's new grant version, built and merged switched off, ratified only by the owner;
  `allocator.max_event_share` 0.25-0.35 for a PROVEN sports family). The owner's standing approval to add
  any data host that meets I2's rule to the box allowlist and `LEAGUE_HOSTS`, and to deploy the gateway's
  `web_fetch` route with its tests green. Nothing in "Not authorized": no deposits, no transfers, no cap
  raises, no test or forced trades, no network for a strategy box, no keyed or login host, no credential
  sent to a fetched host. No owner steps.

## The first hour's decisions

1. **The plan to main.** PR #301 (docs only: a release tree holds `league/`, `ltcm/`, `scripts/`,
   `playbooks/`, `deploy/`, so the updater ships nothing for it, as the forward-first run measured at
   04:44Z).
2. **The floor at T0 (06:03-06:10Z, read-only).** Release `20260925T040816Z-532b1cd9b20c` (H1's
   stop-then-deploy of #294 at 04:09Z); no book frozen; the Kalshi envelope $546.83 with $109.23
   committed (20%); throttle off (floor P&L +$10.75). Shards: 0 $346.52, 1 $0.00, 2 $68.08, 3 $76.98
   (floor $20, day cap $200, nothing moved in 24 h); football's game series sit on shard 0, MLB's on 3.
3. **Where the weekend's Kalshi money is (public API, 06:08Z).** College football: KXNCAAFGAME 240
   events listed ($2.27 M traded in 24 h), KXNCAAFSPREAD 113 events ($1.31 M), KXNCAAFTOTAL 114
   ($0.74 M), median spread 2-3 cents. NFL: KXNFLGAME 31 events ($1.20 M), KXNFLSPREAD and
   KXNFLTOTAL 16 each ($0.57 M, $0.32 M), spreads 1 cent. MLB: KXMLBGAME 43 events ($0.24 M),
   KXMLBTOTAL 13 ($0.07 M), KXMLBSPREAD 13 ($0.01 M).
4. **What the odds recorder holds (feeds.sqlite, 06:07Z).** `odds` has recorded since 08:35Z Sept 24, a
   league every 30 minutes, games starting within 36 hours, at most 16 a league; ONE provider (Draft
   Kings) per game, de-vigged, with ESPN's predictor for football. Two gaps for K1: ESPN's default
   college-football scoreboard is its featured board (18 games recorded for this weekend, against
   Kalshi's 113 spread events), and the 16-game cap cuts Saturday's slate further. The soccer boards
   were last stored Sept 23 (to check).
5. **How a founder gets a seat.** `House.found()` seats a niche's founder rows at rung 1 without a
   replay, but it runs only below `min_population` or from the CLI (a second House on the ledger: not an
   option). The league sits at its 128 ceiling. K1 needs a House hook that seats this run's founder rows
   into a full league through `_displaceable`, as the options run's `options_desk.seat_founders` does for
   its desk; a founder reading the live `odds` feed on a day-horizon desk could not be replayed for 20
   days, so practice is its test and the record says so.
6. **Deploy windows.** Forward-first's Deploy A is 08:00-09:30Z today and its Deploy B moved to
   Saturday's quiet window (about 05:00-15:00Z); the options run's Deploy V is 10:00-12:25Z today and
   its Deploy G follows B. This run's first House deploy (K1) therefore goes in Friday's gap after the
   session: from 20:10Z until the first pitch of an MLB game the proven family holds (about 22:00Z;
   CHC-BOS game 2 starts 22:05Z), its exact start written below first.

## Coordination with the other two runs

This run follows the options plan's "Coordination" section across three runs, as all three records now
say: before each merge and deploy it reads the other two records (current waves, file owners, announced
deploys); it edits no file another run's current wave owns; one deploy at a time across the three, none
13:25-20:05Z on a trading day, none while a real Kalshi family's game is in play (except a rollback), never
inside another release's canary or watch, never within 30 minutes of another run's announced deploy; after
any promotion that leaves the grant inactive it ratifies `earned-live-20260921` only if every changed money
rule is a row of one of the three plans' tables, else rolls back and records why. Whichever run deploys the
gateway second rebases on the first and re-runs the gateway tests. Messages to another run are lines here
plus a comment on its open PR.

**A fourth run (the owner's message, about 06:30Z):** `docs/goals/LTCM_JEV_SENSES.md` (branch
`goal/jev-2026-09-25`). It owns only the Jev files (`league/jev.py`, `sensors.py`, `triage.py`,
`hypothesis_memory.py`, `exposure.py`, `semantic_lab.py`, `jev_features.py`, `scripts/jev_lab_eval/`,
`gateway/lib/typesafe.mjs`, `config.json`'s `jev` block) and lands small hooks into `research_gate.py`,
`feeds.py` and `lab.py` only after the waves that own those files merge; it changes no money rule. From
now on: one deploy at a time across FOUR runs, and any gateway deploy rebases on the other runs' gateway
changes (the options run's multi-leg route, the Jev run's `typesafe.mjs`) and re-runs every gateway test.
This run's `feeds.py` changes merge with Deploy K1; the Jev run's hook follows them.

**This run's current wave, file owners and deploys (kept current):**

| Wave | State | Files owned |
|---|---|---|
| 1 (Deploy K1, Friday after 20:05Z) | building | K1: `league/feeds.py` (the `odds` and `sports` recorders), `ltcm/data/sports.py`, a new model-versus-market seed `league/seeds/sports_consensus.py` with one `SEEDS` row appended at the END of `league/seeds/__init__.py`, the `kalshi-sports` row of `league/niches.json` (founder rows), a new `league/kalshi_founders.py` and ONE call line in `house.py`'s births pass right after the options run's `options_desk.seat_founders(self)`; K2/K3/K4: new read-only scripts (`scripts/kalshi_capacity.py`, `scripts/kalshi_watch.py`); I1: `league/researcher.py` (the `web_fetch` tool beside `web_search`) and the gateway's `web_fetch` route (new `gateway/lib/fetch.mjs`, its line in the router, `gateway/test/`) |
| 2 (after forward-first's Deploy B) | building on a branch, merged after B | K5: `league/live_trading.py`, `league/grants.py`, `scripts/live_trading.py` (`--scale-report`); I2: new recorders in a new module registered from `league/feeds.py`, `LEAGUE_HOSTS` |

- **Not touched by this run:** the allocator, the families' proof, the seat market's rules, the lab, the
  foundry brief, `book.py`, `constitution.py` (K5's grant version lives in `grants.py`), the options desk,
  the `alpaca-options` row.
- **Announced deploys:** **Deploy K1** (House; no money-digest change) Friday Sept 25 between 20:10Z and
  the first pitch of a game the proven MLB family holds (about 22:00Z), its exact start written here first.
  A **gateway deploy** of `web_fetch` (no money rule) in the same Friday gap or Saturday's quiet window
  after forward-first's Deploy B and the options run's Deploy G, rebased on the options run's gateway
  change. **Deploy K2** (House: I2's recorders and the research tool) in a weekend quiet window after B and
  G, its start written here first.

## Checklist

| # | Item | State |
|---|---|---|
| 0.1 | T0 recorded and committed | done |
| 0.2 | Plan merged to main | PR #301 |
| 0.3 | First-hour decisions | done 06:20Z (above) |
| 0.4 | The scoreboard at T0 | done (below) |

## The scoreboard at T0

Read-only on the box at 06:03-06:15Z Sept 25 (`allocator-board.json` at 06:03:51Z, `health.json`,
`feeds.sqlite`, the ledger).

| # | Metric | Reading at T0 | Target by Monday 13:00Z |
|---|---|---|---|
| 1 | Kalshi real settled P&L over the weekend | not begun; lifetime real Kalshi +$34.69 on 127 settlements: sports-central-over-under +$30.75 (3), sports-central-run-under +$23.45 (13), weather-favorites +$10.22 (22), crypto-strikes-lab-955dae +$6.87 (27), prices-favorites +$3.87 (5), crypto-strikes-lab-1b9d16 +$0.40 (9); the 15-minute crypto families and vol-shock −$40.86 | positive, with the families that earned it named |
| 2 | Kalshi families proven; their summed capacity a day | 1 of 28: sports-central-run-under (n 26, bound +0.092; real n 12, bound +0.093), $31.70 a day at $6.00 (fill 1.0, 19.3 markets a day) | ≥ 3; ≥ $100 |
| 3 | Kalshi committed / envelope | $109.23 / $546.83 (20%); on the proven family $16.62 (meriwether-h2d625d's bunt) | ≥ 50% on proven families |
| 4 | Weekend hours with no live Kalshi desk | unmeasured; real Kalshi agents: 1 bunt (sports run-under), 6 probes (2 crypto strikes, 3 weather favourites, 1 sports over-under at stake $0) | 0 |
| 5 | Model-versus-market sports founders seated; leagues covered | 0; MLB only (the run-under family's totals) | one per league with a slate; NFL, NCAAF, MLB |
| 6 | The sports family's swing | 12 real independent settlements; look at 15 (10 under forward-first's M1, in its Deploy B); days_to_swing 0.51 | reached, or the count |
| 7 | The scale report | none | prints committed, capacity used and the tranche per venue |
| 8 | Data hosts recorded; research web reads a day; agent data requests answered | 25 hosts in `LEAGUE_HOSTS`; research has `web_search` only (0 fetches); 211 `tool.request` rows lifetime (118 `tool.fulfilled`, 121 `tool.blocked`), the newest 05:23:54Z | ≥ 45 hosts recorded; `web_fetch` in use; every request of the run answered |

## Progress notes

## Watch log

## Report
