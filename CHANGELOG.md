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
beside the deploys of their day, marked "no deploy". The run record (`docs/runs/2026-09-26-options-swarm.md`
on branch `run/options-swarm-2026-09-26`) has the detail.

## Not yet deployed

- **Persistent practice cohorts and receipts.** Builds on #430: immutable shadow snapshots survive research churn and
  restarts; bounded observation windows include longer-DTE programs; no snapshot is promoted into real money.
  Private decision/order/quote/fill/slippage receipts retry across restarts, program errors reduce coverage, and open
  marked P&L includes fees already paid. Material researcher feedback requires ten program closes over three sessions.
  Sized's fresh-forward window starts after both creation and selection of its version. New cohort/receipt and feedback
  tests use simulated quotes only; actual multi-session practice evidence remains to be collected after deployment.

- **The live practice league** (#430; not yet released; it changes `league/live`, so it is not a research release
  under the amended D8). Every alive Gym-band family with a validated version, or an eligible Train
  version (the tournament's candidate, not demoted), trades live quotes in the shadow book under the Gym's fill rules,
  on a $10,000 practice account; never real, never tuition, never a forward row, never a band move.
  - Admission: validated by validation t, then Train by Train score, under `live.observe_max` (48) and the new
    `live.observe_roots_max` (24 distinct roots, the binding resource measured on the House Sept 29);
    `live.observe_train` and `live.observe_read_calls` in `swarm.json`.
  - Sustained pressure (3 pressed minutes of 10) sheds the lowest-priority quarter of the Train pins for the session;
    validated pins never.
  - The practice ledger (`observe.sqlite`): per family and version from its first live minute, kept after retirement:
    realized P&L after fees (the headline), forced wind-down closes apart, open positions at the engine's mark, realized
    and marked drawdown, coverage. `practice_summary` is read-only.
  - Research feedback (`league/swarm/practice.py`, `practice.feedback`): the strategist's PRACTICE table, the
    architect's PRACTICE BY CLASS lines, and the bandit's bonus (at most +25% of a family's share, at most 10% of all
    share moved; it changes the weight only, which nothing on the way to real money reads).
  - The forward embargo: a Sized move also needs the forward record after its version was written (a tightening;
    nothing is Sized today).
  - The site's `practice` block (needs a personal-site PR: `league/tests/fixtures/site_contract.md`,
    `site_checkpoint_practice.json`; until then the House posts without it and warns once).
  - The money digest stays `a3e2aa7c`; D2 is unchanged.
  - After the deploy: `options_live.observe` shows `tiers`, `roots_used`, `effective_cap` and no `shed`;
    `observe_reads_skipped` stays 0; `observe.sqlite` `practice` rows appear from 13:31Z; no `:o` in `live.sqlite` or
    the swarm's `forward`; the tournament event's `practice_bonus` values are at most 0.25.

- **R11b: honest verdicts, corrections that land, effort where it pays** (this pull request; not yet released). The ROI
  plan's R11 code items (Sept 29, section (b)); research-side only, the money digest stays `a3e2aa7c`, Train figures
  only (D2). R11-1: an idle-rule death is filed under its Train record's verdict (DRIFT, STRESS, THIN, EXHAUSTED; IDLE
  only for the untested), the digest (format 3: one reseal) and the strategist (`screen` per family) read the verdicts,
  a family holding three cycles with an eligible run or ten trials is offered `retire`, and a researcher's retirement is
  SELF-REFUTED; `scripts/graveyard_verdicts.py` re-heads the rows already buried (the operator's, dry run by default).
  R11-2: known ids are masked before the strategist's content rules, the prompt aims at 85% of the cap, a length-only
  overflow up to 15% is trimmed at a sentence end, and `architect.max_alive_per_class` (12) caps births per mechanism
  class. R11-3: `claude.role_effort`, and a cut architect answer keeps its complete families with one medium retry on
  Claude, never a Kimi-K3 refill. R11-5: the bandit exploits only old families with a positive validation mean, 15% each
  at most. R11-6: the Gym's zero-trade probe (off until `researcher.probe_year` is set). R11-4's rule: a validation that
  met six checks holds its family out of the dormancy clause until the operator clears it (`scripts/extension_hold.py`).
  Operator steps after the release: the migration's dry run then `--apply`; `claude.role_effort.architect` "medium";
  `extension_hold.py --seed`; `tournament.explore_share` back to 0.25 if A4 was applied; `researcher.probe_year` 2022
  when wanted. Details in [docs/operations.md](docs/operations.md) ("R11b").
- **Train from 2017** (#424; not yet released). Train's window, `storelib.TRAIN_EARLIEST` and
  `gym.train_from` reach 2017-01-03 (a third start beside 2020-01-02 and 2022-01-03; over eight years the derived
  split is 24 and the time limit 2400 s). Stage 9's `EARLY` stays the literal 2020-01-02..2021-12-31. New public
  tables: the 2017-2019 scheduled FOMC days, CPI and Employment Situation release days (Federal Reserve meeting
  pages, BLS release archives) and the rate steps back to 2015-12-17 (the Fed's target-range changes, upper bound
  less 0.10, as before). A Gym store's first Train day is its first chain, so a 2020 image's 2019 history sessions
  stay out of Train. `images.py build gym --root-first ROOT=DATE,...` gives a root its own later first Train day,
  recorded in images.json and checked from inside; the fork prunes with the build's own data tools. A build from
  2017 lists its roots and refuses unless every name (a root outside the core five) has a first day on or after
  2020-01-02 or is named in `--early-names` (for after its split rows are in); it refuses `--early-roots`. The inside
  check holds every other name to 2020-01-02 and the image's first chain to its `train_from` exactly, and
  `images.py verify --root-first` reads the recorded `train_from`. Nothing moves
  until an image is built with `--train-from 2017-01-03` and `swarm.json` names it with `train_from`. On release the
  Gym bundle and tables digests change, so every program re-runs once as a new trial and each family is re-validated
  once, as with #399; the money digest stays `a3e2aa7c`.
- **Two-sided singles: the `long_single` structure** (#425; not yet released). A family may declare `long_single`:
  one program that opens one `long_call` or one `long_put` at a time (one leg, long), the side chosen by its rule, in
  place of a call/put twin pair. The architect's prompt describes it (the side rule, and why its calls and puts balance:
  the drift screen charges whatever net exposure it holds) and asks for no twins, and `admit` refuses a one-sided twin
  beside a living `long_single` or the other side of the same idea on the same roots; in GAPS a single option's one gap
  is `long_single` (the one-sided singles are no longer gaps, though still admitted); coverage has its row; the
  researcher, reviewer, auditor and diagnostician read what its orders are. It shares its singles' slice for lineage
  matching and identical-code links; a `long_single` that continues one twin joins the other twin's lineage too
  (`link_lineages`), and a new lineage on a singles' slice counts the newest dead lineage of each type there
  (`slice_priors`, `prior_lineages`; every other structure keeps its one prior). Real eligibility (tuition, Probe,
  Sized, the site's `real_structure`) needs BOTH `long_call` and `long_put` among `options_money.real_types`; every order
  keeps its own type, is checked by it at the real book and the gateway, and is sized by its own unit; the live path
  refuses a real open of any other type from a `long_single` family. The site shows the agent's structure as null (its
  schema has the eleven order types) and each position as its own type. No Gym, verifier, D2, drift-screen, gateway or
  money-table change: the money digest stays `a3e2aa7c` and the Gym bundle version does not move, so nothing is
  re-validated. Once a `long_single` family exists, roll forward rather than back past #425 (a release before it fails
  every architect pass).

## 2026-09-30

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
