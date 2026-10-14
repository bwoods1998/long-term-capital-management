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
[docs/runs/2026-10-02-unattended-desk.md](docs/runs/2026-10-02-unattended-desk.md). From the V3-A part 1 deploy
(Oct 3, below) the House also deploys main by itself (the updater): its daily pages in
[docs/runs/desk/](docs/runs/desk/README.md) count its self-deploys and self-rollbacks, and they get entries here like
any other deploy.

## Not yet deployed

The running House release is `20261011T225041Z-65fa6d3946ea` (main `8ab31e32`, releases E5-A and E3.1, 22:51Z
Oct 11), the gateway is `9c0651a3` (20:25:11Z Oct 11), and the box's updater is on. What is built and not deployed is
on branches.

### Release E4 step two: what a panel look and a panel seat need that can be built before XS1-R rules, on `feat/equity-e4-step2` (unreleased; on step one `6f99652d` with #543 merged, `47ed6872`: the Probe sleeve 0.50 x E; THE MONEY DIGEST MOVES ONCE, in its marked commit; no fingerprint moves)

- **The A31 look hold.** `elane.panel.look_rule` (policy.json "hold"): no XS1 look before study XS1-R rules. A
  look waits, nothing spent, even with its receipt, permit, review and room present, and says "A31: no XS1 look
  before XS1-R rules"; "xs1" is XS1 as built; a value the tree does not implement holds; Validation is not held.
  The heartbeat's `equity.panel.look` and the direction report's `panel_lane.look` say why.
- **The panel money row and the panel seat pool** (`equity_money.panel` {"seats": 1, "sleeve_share": "0.10"};
  bounds 0-2 and 0-0.25, never above the Probe sleeve). A panel program holds a seat of a pool of its own and a
  sleeve of its own: the six ETF seats, their plan, the idle test and K are untouched, and the ETF programs'
  orders are the same order for order with a panel Candidate, Probe and Sized program in the book. A program held
  on a failed leg keeps its seat. Money digest `5b95d73e` -> `de5ed74e`, constitution `4ef472e1` -> `111ede85`
  (the grant re-ratifies at the House's start). league/live/money.py is not edited (it is inside the options
  execution fingerprint): the row is read by league/equity/bands.py `panel_settings`, as the seat rule's block is.
- **The clock and quiet rule in Validation and the look** (the ship check's open item): every run of the try (2025
  at k 1.0 and 1.5), the two Train segments and the sealed run goes through `steady`, `may_run` asked before each.
  The House's clock spends nothing (owed after a backoff; `elane_xs_clock` at the third); timeouts that repeat as a
  program's spend the try as SLOW and the look as spent and failed. The look's seed and draws are unchanged.
- **K for a basket**: the seat rule's rank of a panel program, from its own runs (Train-era close days per 250
  sessions of the seen spans' 1.0x runs, kept sealed by the bar; the Validation close days of the try's 2025 k 1.0
  run), written as `elane_seat` beside an entered try and ranked inside the panel pool only. Never printed.
- **The close dates beside every checkpoint** (A14_BESIDE_DONE, "not computed yet" until now): each Done
  checkpoint carries `close_dates` {closes, dates, date_t, unpriced} over its counted closes, all programs, the
  closes of one date summed (a basket's eight lots sold at one open are one date). Beside, never a rule.
- **The panel twin's re-base (A29 as registered)**, before any panel twin row exists: after a differing decision
  session the twin's book is the live basket as it stood (`forward_xs.panel_seed`, `PanelChain`; the Gym engine's
  account driven from ops in `league.xs.book.TwinAccount`; engine.py not edited); A29's two columns written for
  panel rows, the un-re-based shadow beside; one missed buy counts once. A14's bounds, keys and pooling unchanged.
- **The live-book proof recorded again on main `47ed6872`** (#543's sleeve): every scenario moved by the lot's size
  alone; step one needs the same record once #543 is merged into it.

### Release E4, "breadth": the point-in-time S&P 500 panel under the screen XS1, on `feat/equity-e4` (unreleased; merged with main `8ab31e32dc77a730d6d3397c222f530294dec632`, the running release: main's releases through E5-A and E3.1 are under it, on `feat/equity-e4-m3`; ONE release in TWO STEPS, each an owner deploy: step one is the whole tree, no digest move, ships switched off and may be set to "train"; step two the universe with the money row of a panel sleeve, one money-digest move, deployed separately)

- **What it adds** (`league/xs/E4_INTERFACES.md`, `league/swarm/E4.md`): programs that pick 5 to 12 names out of the
  day's S&P 500 members by a symmetric cross-sectional rule, see salted slots with no ticker, no date and no price
  level, and are judged on their daily RESIDUAL against matched placebo portfolios by the screen XS1 (the study
  XSCREEN-1's receipt, rebuilt at the captain's bar: `docs/benchmarks/equity_screen_xs_1.json`, pinned in
  policy.json; every threshold read from it at runtime). The data jobs (membership, the panel's bars with their
  coverage audit, spreads, N_eff), the panel
  package `league/xs/` with its own evidence identity, the Train bar equity-xs-v1 with its weekly zero-edge column,
  the one Validation try and the one look, and the live adapter through E1's EquityBook (a rebalance the book can
  execute, a standing target that retries a missed buy, the bars a decision read kept and audited).
- **Ships off, and step one stops at "train".** policy.json `elane.panel.mode` "off": no birth, no run, no fetch of
  the live path, no model question, no data job. The ladder is "train", "gate", "live", each the captain's settings
  change and each falling back to the one before. STEP ONE is this whole tree deployed with the switch able to reach
  "train": the data jobs, panel births in the equity pass, the Train bar with its zero-edge column, and the forward
  shadow of every scored panel version (package J, below), so that information accrues from the first night. Above
  "train" the tree holds itself back whatever the setting: **no panel look runs until E3's contamination probe has
  published the panel strata for the route that wrote the program and written the look permit** (the captain's A22;
  package B's patch to the probe: built and not yet handed to the House's job, below), and **mode "live" reads as
  "gate"** until the universe deploy is in force and the forward twin's marker is written, and while that marker is
  behind.
- **Before any real money on an XS1 pass** (A22): a style-open program takes no live seat on a pass alone (recorded
  and shadowed, never seated); at most 2 XS1 looks an agenda cell; the equity code review and the contamination probe
  before a look; a ninth conformance vector beside the study's eight.
- **The live rules read a panel program by close DATE** (pre-registered before mode "live"; word for word in
  docs/operations.md): one observation a close date for EDM1, for sizing up and for the twin-gap leg. E1's rules are
  unchanged as functions and as numbers; the cost, stated: EDM1's statistical leg cannot act before the 10th close
  date, and until then the -$300 program line, the $400 window and the stops bound a panel program's loss.
- **R-E4a moves no identity and no digest:** nothing under `league/live/` or `league/gym/` and no evidence module of
  `league/equity/` changes; the constitution is untouched. The xs identity is adopted for the first time.
- **R-E4b, THE UNIVERSE (one commit, deployed separately):** `equity_money.universe.stock` grows from E1's 18 names to
  the panel's tradable union (every symbol that was an index member in the 36 months before the generation day and is
  tradable and fractionable; sorted; no date), written by `scripts/gen_universe.py` with the same list at the gateway
  (`gateway/lib/caps.mjs`). `digest()` and `money_digest()` move ONCE (the figures are in that commit's entry: they
  are the list's) and the standing grant re-ratifies at the House's start. No bound, share, weight, seat or cap
  changes; `league/equity/config.py` `UNIVERSE` stays E1's 35 and inside it. The gateway deploys first; both deploys
  go between two pre-opens. Regenerated about once a year.
- **CI:** `league/swarm/elane_xs.py` and `scripts/gen_universe.py` are FORBIDDEN (`PENDING_GATEWAY` until the
  gateway's merge list names them: a gateway follow-up; E2's five and E3's three are in that list already, so the
  two wait alone); the comparison of the gateway's stock list
  with the constitution's names at most 10 tickers a side and counts the rest; the pre-open's check 5 counts the
  options population by the store's own guard (a panel family is its own lane's), and its check 10 holds the panel
  lane ready while a panel program is live.
- **Integrated Oct 11 (R-E4a; nothing deployed):** eight packages (A data, B costs and counts, C the xs core, D the
  engine, E the screen and the identity, G the swarm's lane, H the book's panel path, I the universe generator, CI
  and docs) merged over E1 and E2 with their review fixes (`feat/equity-e2-int` 5ad1f01e), every patch to E1's and
  E2's files applied, XS1's receipt landed verbatim with its pin (the registered receipt; the captain's A23 has
  since replaced it: below). E4's own commits move NO id: the options execution
  fingerprint, the equity identity and the money digest are the E1/E2 head's on every one of them (E1's own fixes
  moved all three before E4 was merged onto them: the vendor's cents, the Probe sleeve A20). **One fault found and
  fixed at integration:** a panel program ALREADY SEATED went on buying after the lane's mode was put down, the
  nightly I6 failed or its shadow twin stopped (the seat rule read Candidates only). Now a seated panel family has a
  row only while the lane is live, its planned entries are held at the send, and the book retires it on the lane's
  own word; a switch file caught mid-write retires nobody. The xs rounding bound is E1's own, re-exported.
- **What step two still needs, plainly** (each holds real money back by design; none of it is in this tree):
  1. **The universe commit** (R-E4b, above). It needs the House's own `tradable.json`, which the `equity_universe`
     job writes only once the lane has been at "train": step two cannot be cut before step one has run.
  2. **The money row for a panel sleeve**: a constitution row and the lines of the book that read it, not built.
     Without it a panel program takes the Probe sleeve and one of its seats: at the design in force since release
     E5-S (six seats, 0.25 x E) a five-name basket is five names of $111.45 at about $2,229, $222.90 of open risk
     where a one-ETF lot is $55.73, so a basket beside five invested ETF programs asks for more than the $400
     window: whichever buys later is scaled or refused (the basket is scaled to the room and trades whole from
     flat; once the room is short a partial rotation's new name is refused at the send and the program holds a
     name fewer than its Gym twin: pinned as built, at A20's design where a basket alone met the window). Decided
     and deployed with the universe, so the grant re-ratifies once.
  3. **The gateway patch**, three parts, each a patch file for the owner (no builder edits `gateway/`): the static
     half of the universe (`gateway/lib/caps.mjs` and its tests made ready for a generated list; it changes no
     list), the generated list itself (`gen_universe.py --gateway-patch`), and the merge list's follow-up for the
     lane's two protected paths (`gateway/lib/protected.mjs`; until then they wait in `PENDING_GATEWAY`).
  4. **The owner's deploy**: the gateway first, then the House, between two pre-opens; `digest()` and
     `money_digest()` move once and the standing grant re-ratifies at the House's start.
  5. **A panel program under the seat rule, and its re-based twin** (new with main's releases E5-A and E3.1; "The
     merge with main `8ab31e32`", below): which rank K a basket has (the panel's look writes none of K's counts, so
     a panel Candidate would rank behind every program whose counts can be read), whether a panel program held on
     a failed leg keeps one of the six seats while it has no row, and the re-base of the panel twin (not built).
     None of it can be reached in step one.
  And before any LOOK, which moves no money and no digest: the hand-over of the probe's panel plan to the House's
  job (patch 18 is built and not wired, below; one allowance in E3's seal test, the captain's ruling). Until it is
  given every panel look waits.
- **Package J, the forward twin (Oct 11; nothing deployed; the three ids are main's on both Pythons; no identity
  moves: `league/ops/forward_xs.py` is plumbing).** A scored panel version is registered in E3's forward record
  (hash-chained with its NEEDS, route "XS1" and alpha 0.03) and recomputed whole on its own forward days each
  PANEL NIGHT: the new job `forward_xs`, E3's own night on the panel store, after each `equity_panel` (not a ride on
  `forward_shadow`: the panel store is a session behind at 22:35Z and the lane's twin marker must be through the
  store's last session by the next close). One run a program a night at 1.0x: the row's stress column holds the
  pre-registered stress residual of that run, and E3's excess of the row is the residual against the matched
  cells. Rows lag one session and twins two (the engine opens no lot on a slice's last session and reads
  membership two sessions ahead: shown on the real engine). The panel night spends what E3's night left of the
  one budget, and all its runs read one open of the panel store (opened once a run, the ops child's address-space
  cap was met at the third run: measured at the real panel's size). The twin of a live panel instance runs under
  the instance's own id as run key and is compared by weights; A14 then reads a basket's sessions as any
  program's. The marker (`xs-twins.json`: instance ids and days only) is what the lane reads before mode "live".
  Alarms FX1 (the marker behind), FX2 (a rebalance session that disagrees), FX3 (panel programs stale two nights
  running); the twin's residual and the rebalance sessions agreed stand beside a live panel program in the
  direction report. PATCHES TO E3's FILES, each a few lines: `forward_db` (the panel's route in the chain),
  `forward_register` (the panel's reader beside its own; nights by job), `forward_shadow` (its queue leaves panel
  programs out; the label; the job's name), `forward_twins`, `forward_audit`, `forward_report` (the panel's own
  groups; nights by job; the FX rows). E3's import seal admits the new module and holds it as it holds E3's own.
  COSTS, stated: once a panel program is registered the engine label gains the xs fingerprint (one `engine_moved`,
  every program's forward history written again under the new label; again at every later change to an xs
  evidence module) and a day's meters wait for its panel rows (the second morning after the day, where they were
  written the same evening). NOT BUILT: `fill_minutes` fetches no panel
  symbol; the forward route's own verdict; panel controls. With `elane.panel.mode` "off" none of it runs or writes.
- **The probe's panel strata P4-P6 and the look permit (package B's patch 18; Oct 11; BUILT, NOT WIRED; nothing
  deployed; no id moves).** Release E3's probe can be handed a plan of three more strata
  (`contam_probe.probe(ctx, panel=contam_xs.plan)`; the plan is the new `league/ops/contam_xs.py`): a member against
  its sector's fund by month and by week, and the House panel factors by month, asked after E3's own cells while
  `elane.panel.mode` is not "off", inside the SAME dollars a run (`elane.contam.usd_run`, E2's day line: nothing
  raised; about 70% more questions, so a route's probe takes that many more Saturdays). Prompts are names and the
  calendar only and every word is the probe's; truth comes from the panel store through its own windows (2025 and
  2026 through the sealed "look" window alone; never a period of 2016, 2020 or 2021); the result keeps E3's shape
  and E3's own cells byte for byte. After each publish the plan writes `<state>/xs-look-permit.json` (two words a
  cell, no figure), which is what `elane_xs.probed` reads. **The House's job (`contam_probe.run`) hands no plan
  yet:** two of E3's seal tests leave no import between the probe and the plan's module, neither was changed for
  it, and the two lines that hand the plan over need one allowance in E3's seal test, the captain's to give (the patch is
  in the captain's scratch). Until then the House's probe is E3's to the byte and every panel look waits.
- **The ship pass (Oct 11; nothing deployed; the three ids are main's on both Pythons, the xs identity moves).**
  MERGED: main's E2.2 and E3 (`7d2d3c84`); E3's six jobs then E4's six in the registry, the forward record's counts
  beside the asset-years in the funnel. WHAT THE MERGE MADE TRUE: a panel family is born with a hidden year (E3's
  folds record in the committed policy), and E3's count of a cell's births holds no panel family; a scored panel
  version was neither registered nor refused by E3's registry (package J registers it: above); three of E3's seal
  tests failed on the lane and the LANE changed, no seal: it imports no memory module (the fold's switch, hash and genome id
  are spelled in `elane_xs`, held equal by a test), and the swarm reads a LOOK PERMIT
  (`<state>/xs-look-permit.json`: two words a stratum and era, written by the probe's job) where it read the
  contamination probe's own file. FIXED: **the live panel fetch placed no bar** (`rows_to_arrays` refused the Decimal prices the
  House's venue client hands; every fake venue handed floats, which is why the whole live week passed: the fakes
  now decode as the client does). **The spreads' share fell with the index's turnover for ever** (it counted
  today's members; a name that joined after 2024 can never be sampled): it is the share of the Train eras'
  member-days whose name has its own figure. The coverage probe's five defects from its first run on the House,
  and a sixth (a refused request was retried and counted an error). BOUNDED FOR THE BOX'S ONE CORE: no panel run
  works while the market is open (a run's wall is the whole session, 09:25 to 16:35 ET), and the spreads job's
  grace is three hours (with six it could hold the one ops child past a pre-open). STATED, NOT CHANGED: the send
  after a window loss (above); every budget of the lane on the box is an estimate until its first receipts.
- **The receipt at the captain's bar (A23; Oct 11; nothing deployed; the three ids are main's on both Pythons, the
  xs identity moves and no panel band exists under it).** THE HOUSE RUNS XS1 AT
  c_XS 1.38, NOT THE REGISTERED 1.30. WHY: 1.38 is the registered rule's own answer once the finite-pool bias the
  study measured is added to every real-signal cell (the registered receipt's
  `cost_of_rule.c_XS_with_finite_pool_bias`), and a known bias left out of a bar is a loosened rule. WHAT MOVED:
  `docs/benchmarks/equity_screen_xs_1.json` is the study's receipt rebuilt at 1.38 by the study's own report and
  receipt builder from its saved run (sha256 `f7ce98b1...`; the registered receipt `98acbb83...` stays the study's
  result, and the new file names it under `house_bar`); policy.json's pin of it (`receipt_sha256`, `c_XS`, the
  sentence); the conformance vectors, computed again at the new bar by the study's vector builder, with their
  inputs file and the two by-hand vectors; a CI test that holds the vectors' bar to the pin's; two docstrings of
  `league/xs`. No line that judges, sizes or trades changed, and A22's four rules are as they were. THE COST, from
  the two receipts' own `power` rows: at a planted net residual edge of +10% a year the full gate's power falls by
  0.39 to 2.59 points over the eight archetypes' `XH|N0-S|e10` rows (X7 52.87% to 50.28%, X1 44.33% to 41.91%, X8
  67.58% to 65.56%, X6 33.86% to 33.47%); over the 48 calibration rows the holdout-only power falls by 0.29 to
  2.64 points (median 1.93). WHAT IT BUYS: the largest zero-edge rate of a calibration cell 10.02%
  (11.15%), its largest 95% bound 13.11% (14.82%), and no bootstrap seed of twenty at the owner's 15% wall (2 at
  1.30). STATED: every false-positive, bound, family-wise, bias and power row is read at 1.38 from the
  simulations the study saved; the two report-only arms (takeovers and collapses; no-skill style tilts) had been
  saved at the study's bar only and were run again at 1.38 by the study's own command, after the same command at
  1.30 gave the saved results again; they decide nothing. A receipt at another bar lands the same way
  (docs/operations.md, **The screen XS1**).
- **The merge of the three (Oct 11; nothing deployed; the three ids are main's on both Pythons; the xs identity is
  the one the receipt's words gave).** Package J, patch 18 and the receipt at the captain's bar were built side by
  side on the ship pass's head and are merged in that order, every line of each kept; main had not moved past
  `7d2d3c84`. WHAT THE MERGE ITSELF CHANGED: the two contracts, where each package had added a section 13 (in
  `league/xs/E4_INTERFACES.md` package J keeps 13, patch 18 is 14 and the receipt is 15; in
  `league/ops/E3_INTERFACES.md` package J keeps 13 and patch 18 is 14); and ONE TEST where two packages met:
  patch 18's `test_contam_xs.TheWiring` held that E3's import list names nothing of the panel, and package J's
  seal change put its own module (`league.ops.forward_xs`) on that list for the forward modules. The test now
  holds that the list names that one module and that the probe imports none of it. The merge edited no seal test.
  Neither package J nor patch 18 changed a file under `league/xs` but the contract, so the xs identity is the
  receipt branch's; no panel band exists under it.
- **The review's fixes (Oct 11; nineteen findings, three lenses; nothing deployed; no id but the xs identity
  moves, and no panel band exists under it).** LIVE SAFETY: a seated panel program is liquidated only by the
  captain's switch: a store-side leg that fails with the switch at "live" (the nightly I6, the twin marker, a stale
  store, the universe, the spreads) holds its opens and nothing else ("held": the spec's "its opens stop, exits go
  on"; before, one restated bar among 515 columns sold the basket two opens later). The nightly I6 is False on a
  price that differs and on nothing the live book itself tolerates (a bar served late, a member learnt after the
  decision and a decision with no kept fetch are counts and a warning). A panel fetch that raises is a decide the
  House could not make after the grace, never "still being read" for ever; a row the venue serves on no session is
  dropped and counted as the nightly job does. A rebalance whose bars differ in the morning is void whole (its
  program's sells with its buys). The lane's readiness reads the store's freshness by the clock, the panel job has
  its own nightly trigger, and it fits the ops child's memory at the real panel's size (384 MB of 527 where it
  failed at 25 names ex-dividend). The seating pass never fetches the panel inside a session; a failed decide it
  counts exits the lots at the next open; a ticker change inside a held lot keeps its column. EVIDENCE: the panel's
  sleeve is a constant-weight book in the Gym and live alike (the pre-registration's C3 and C8: a 5 x 0.20 target
  opens five lots of 0.20 after a loss); the style loading is of what a program HELD (dollars times sessions), not
  what it bought; `range` is the body plus the wicks under a relative dither, so no statistic of it ranks the slots
  by price; the look's floor is computed from the segments each attempt runs; a live program is told the Gym's tag
  of a lot. MONEY, PLAINLY: at about $2,229 and the rows in force a five-name basket was NOT tradable as five whole
  names (four of $222.90 and a fifth cut to $108.40); the decision's budget is now the sleeve scaled so the whole
  basket fits the account's room (five of $200.00), and a full basket then uses the whole $400 window. SWITCHES:
  with `elane.panel.mode` "off" no data job runs either, and none starts with the House; `coverage_min` is the
  lane's own key; the lane's effective mode and the leg that holds it are in the heartbeat and the report, with
  the alarms that had no detector.
- **The ship check's fixes (Oct 11; nothing deployed; the three ids are main's `81963c87` on both Pythons; the xs
  identity is unchanged, 2f0083bc...).** MERGED: main's releases E5-S (six seats at a Probe sleeve of 0.25 x E)
  and E2.4 (the equity lanes' alarms), every line of both kept; E5-S's design grid is read with E1's universe put
  back, so its pins hold before the universe deploy and after it; the lane alarms read share programs only (a
  panel family keeps its own record and its own alarms). **A SHARE PROGRAM'S LIVE PATH IS MAIN'S, ORDER FOR
  ORDER, at every position of the panel switch:** the spec's decision 27 (B8: a buy cut by a cap waits while an
  exit of its own program works) was written for every instance, and six ETF programs hold real-money seats under
  E1's rule; B8 is now the panel kind's alone. Proved by a recorded comparison
  (`league/tests/test_equity_etf_orders.py`, its harness `league/tests/equity_week.py`, its fixture recorded on
  main `81963c87`): the lane's first Monday the normal way, every way a buy can miss, the week and its failing
  weeks, programs that sell and buy in one window, 65 scenarios, and every one again through the real swarm reader
  with the switch absent, "off" and at "train"; every POST, cancel, fill, alert, intent, order, lot, instance row,
  record and minute's answer equals main's. Two differences are allowed and held: the column `eq_instances.kind`
  and the empty table `eq_rebalances` (main's book trades the same weeks on a state that holds them). With B8 as
  the spec wrote it five scenarios differ. FIXED: **the zero-edge job could not finish one program inside the ops
  child's 500 MB** (a store opened a run, every run kept whole): a judgment reads one store, keeps results and
  lets slices go, and the restart check cuts a slice again when it reads it; three judgments at the real panel's
  size peak about 80 MB under the cap, held by a test under the child's own limit (the real job run whole on the
  desk: 57 MB under it; not measured on the box), and the swarm's judgments use the same code. **A decide is limited by WALL time and the box stood still for longer:** in the Train judgment,
  the zero-edge job and the forward night a run whose runtime shows a decide timeout is made again, three times at
  most, and never read; timeouts in every run that repeat as a program's do are the program's (`SLOW`, with the
  measured seconds, which its author reads), and those that do not are the House's (nothing scored, a backoff, one
  alert). The fix at the root is in `league/gym/runtime.py`, inside the equity identity: a release of its own;
  Validation and the look do not ask the rule yet (before any look). **`equity_spreads`' CPU row** is 900 s (300
  was under a night of its backfill at the cost a call measured on the box). The data jobs pace their venue calls
  (0.4 s before each; 30 s then 65 s after a 429). `forward_xs` skips where E3's own job skips (it failed on an
  evening the House's daily store held no forward day). The look's own reading of the lane's mode has its test,
  and E3's seal lets five modules import package J's, the five that dispatch to it.
- **The merge with main `8ab31e32` (Oct 11; main's releases E5-A and E3.1, deployed 22:51Z; nothing of E4
  deployed; the options execution fingerprint, the equity identity, the money digest and the constitution digest
  are main's on both Pythons; the xs identity is unchanged, 2f0083bc...).** MERGED, every line of both kept: the
  seat rule "activity-1-free", the exit wait's end and the re-based twin, under the panel lane. Ten files met. In
  the live book (`league/equity/live.py`) the share path is main's code path: the seat rule's band sync, the
  open note, the exit wait's end and the lost order's take-back are untouched, and what E4 changed stays behind
  an instance's kind. The swarm's reader takes main's `queued` read and E4's panel rules together (a panel
  Candidate is seatless while its lane is not live, so it has no row for the seat plan either); the roster and the
  `dlane` report carry both sides' keys; `league/ops/E3_INTERFACES.md` keeps main's section 13 (release E3.1) and
  E4's two sections are 14 and 15; `league/constitution.py` is main's to the byte. **A SHARE PROGRAM'S LIVE PATH
  IS MAIN'S, ORDER FOR ORDER, PROVED AGAIN ON THAT MAIN:** the fixture was recorded again on a detached clone of
  `8ab31e32` (two records equal to the byte), 75 scenarios. The 65 of before: on main itself the weeks in which
  stage SELL cannot pass now sell at the 09:45 cut-off, and every scenario's keys hold the seat plan and the open
  note. Ten that the new main makes possible: the seat rule over thirteen sessions (nobody waits and the idle
  seats are kept; an idle seat yields to the waiting program; two wait and one seat yields a decision day; a
  session in which the House refused every open is left out of the idle clock; a yielded program returns into a
  freed seat; no idle clock while the House refuses every buy), and the forward record's nights beside the book
  over eight sessions (nothing re-based; Monday's buys missed and the twins re-based; a rebuy missed mid-week; the
  practice sale never witnessed). Every POST, cancel, fill, alert and line of the seat rule, whole, and every
  intent, order, lot, instance row, key of the book, record, minute's answer, twin row, twin event, night's
  receipt and A14 reading, by digest, equals main's, through the test double and through the real swarm reader
  with the switch absent, "off" and at "train". The two differences allowed are the two of before (the column
  `eq_instances.kind`, the empty table `eq_rebalances`); the forward store has none. A reader that hides the
  waiting Candidates, an exit that never waits and a twin that is never re-based are each caught by the scenarios
  recorded for them. **WHAT MAIN'S THREE RULES DO FOR A PANEL PROGRAM** (decided here; `league/swarm/E4.md`
  section 7; `league/tests/test_equity_panel_on_main.py`): (1) in step one a panel family never enters the seat
  plan, never counts against the six seats, never holds or yields a seat: the book builds its plan from the
  reader's rows alone, and the reader gives a panel family none at any setting of the switch (held with a panel
  family forced into the Candidate, Probe and Sized bands, where step one makes none; under the "first-come"
  rollback the swarm's roster counts the Probe band as the store holds it, and step one puts no panel family in a
  band); (2) the exit wait's end covers a basket's exits like any other, the program's sale and the House's exit
  of a name that left the eligible set alike; the basket's buy of that open waits with its own sales (B8) and the
  cut-off records it missed, the standing target planning it again; (3) the re-base is NOT BUILT for the panel
  twin: a panel instance is twinned by the panel night, compared with the twin as registered every session, with
  NULL in A29's two columns and no re-base event. **ONE FORWARD-STORE MIGRATION:** E4 adds no table and no column
  to forward.sqlite (`forward_db.SCHEMA` is main's to the byte), so the migration is main's alone; a store built
  by `8ab31e32` and one built by `8ed4e72e` (with a panel program's registry row and twin rows) both open under
  the merged tree with no row rewritten, two writers at once included
  (`league/tests/test_forward_store_two_builds.py`; the same run once on stores each sha's own code built).
- Operations: [docs/operations.md](docs/operations.md), "The panel lane" (the switch, the screen, A22, the live rules,
  the universe deploy and its rollback, the alarms).

### 22:51Z Oct 11, 2026: releases E5-A and E3.1, the seat rule, the exit wait's end and the re-based twin (#542), House `20261011T225041Z-65fa6d3946ea`, main `8ab31e32`; gateway unchanged `9c0651a3`

One owner deploy of both: CI green on the exact head; no order in flight at 22:50:28Z; promoted 22:51:33Z, the
watchdog clean (rollback `20261011T202519Z-50def634e716`), nightly back and the updater repointed 23:02Z. Verified
23:02Z: health clean, real money on; execution fingerprint `b60410ad` and gate contract `397b22b772b3` unchanged;
money `6c0bc42b` -> `11a1dc0c` and constitution `c3c061b0` -> `00c2bf6f` on purpose (the seat rule's block), the
grant re-ratified at House start.

- Seen on the House after: the seat plan read "activity-1-free" with six seats held and nobody waiting; the three
  buys planned for Monday's open stood.

### Release E5-A: the seat rule of the share lane ("activity-1-free"; the captain's A24 with A30), on `feat/equity-e5a-seat-rule` (DEPLOYED 22:51Z Oct 11; one owner deploy with release E3.1 below, from `release/e31-e5a`, on top of releases E5-S and E2.4; THE MONEY DIGEST MOVES, the grant re-ratifies; no fingerprint moves)

- **What it is.** Who takes a free seat was first come. It is now the seat rule the captain registered at 13:42Z
  Oct 11, before the first live share close and before any program waited, as amended by A30 at 20:47Z the same
  day, before the rule was live: `equity_money.probe.seat` = {`rule`
  "activity-1-free", `k_floor` "0.25", `idle_sessions` 10}, a row of the money table with its bounds and choices.
  A FREE seat goes to the best-ranked waiting passed program. The rank K is the smaller of the program's Validation
  close days and its Train-era close days per 250 sessions, a day counted only when the lots closed on it sum to a
  quarter of the sleeve (less 0.0005, the engine's rounding); ties go to the earlier look pass, then the family
  id. K reads no P&L and no sealed window, and no public text prints it (a rank position only).
- **The idle seat.** A seated program that is flat and has had no buy reach the venue, and none cut or refused by
  the loss budget, for ten sessions of its seat is idle. It keeps its seat while no unflagged program is left
  waiting, and yields at once when one is (one yield a decision day). A buy refused by the instrument cap, the
  invested cap or cash does not count as asked. The yielded program waits flagged, behind every unflagged one,
  and returns only into a free seat, by the same rank, with no new look.
- **A30, from the release's independent check (the rule in force is A24 with A30).** (1) FREE SEATS FIRST is A24's
  reading: a free seat is filled before the idle test, and an idle seat yields only for an unflagged program that
  would still wait; the study's simulator ran the idle test first, so its gain of the rule was measured under
  that slower order. (2) THE IDLE CLOCK DOES NOT RUN WHILE THE HOUSE REFUSES EVERY OPEN: a session with an entry
  window in which the House looked and never once would have opened (paused, the kill switch, a stop, a freeze,
  the grant not ratified, the paper proof's BUY stage not passed: what `_open_block` answers before it looks at
  the instance) is left out of every program's seated sessions and of its sessions since its last asked buy.
  The book keeps the note itself, every minute of the two entry windows, from the House's own answer (kv
  `eq_open_note`); nothing a program writes reaches it. Before, a ten-session pause handed the most active
  programs' seats to the slowest waiting ones. (3) A LOST BUY IS NOT FLAT: an order given up as lost keeps its
  program from being read flat for as long as the order path may still take it back (three days), and a day more.
  Stated and accepted, not changed: a daily quarter-sleeve slice buys rank and immunity from the idle rule.
- **The check's blocker, and the question it is one case of.** A buy whose answer was lost and which the book gave
  up as lost did not keep its program from yielding; when the venue showed the order filled afterwards, the lot
  was booked to the yielded program and the House sold it at the next open. Fixed at the root (A30 (3)), with the
  check's probe as a test. The wider question, whether ANY lot can be booked to a program after it yielded, is
  answered in code and asked of the order path itself: a lot is booked only by a buy's fill, a fill only when the
  order path reads the venue's row of an order, and it reads only orders pending, working or unknown and lost
  ones inside their take-back; `_flat` is false for exactly those (league/tests/test_equity_seats_a30.py writes an
  order in every status the book has, on each side and at each age, lets the venue show it filled and runs the
  House's minute: whenever a fill is booked the program was not flat). A lot of a yielded program, should one
  ever exist, is an ERROR alert and never silent.
- **The check's minors.** EDM1 naming a waiting program at its seating writes the `waiting_demoted` record and
  the warning, drops its flag and takes it out of the plan at once. The yield's two writes cannot be split: the
  swarm's write is last inside the live state's transaction, and a commit that fails after it moves the band
  back. `elane_seat` is in the seal's key list, with a two-worlds test on K. A stale idle flag is dropped whenever
  its family's band is live at a sync, under either rule, and under "first-come" a yielded program's return is no
  longer a decision late. A seat taken in the seating pass once a session's open has begun counts from the session
  after (chosen: the idle test names nobody before ten whole sessions; the mark's own day is unchanged).
- **What it never does.** No trading program is stopped: OUTRANKING IS NOT ADOPTED, and the table does not allow
  it as a value. No lot is sold, no exit is planned and no order is cancelled by the seat rule; a yield retires an
  instance only inside the one state transaction that found it flat. `size_entry` and every owner line are
  untouched (the base's cap tests run unchanged).
- **Also in it.** EDM1 covers a waiting program that has a real record (sticky: it does not return). A seating
  that does not take falls through to the next waiting program in the same sync. Seeded and bred programs follow
  the same rule, and the `dlane` report says which seats the seeds hold (`equity.seats`).
- **Where it lives.** The row and its bounds: league/constitution.py. Its reader and the pure rule (`seat_settings`,
  `seat_counts`, `seat_k`, `seat_order`, `seat_idle`, `seat_plan`): league/equity/bands.py. The book applies it and
  is the one source of the plan (league/equity/live.py `_seat_bands`, kv `eq_seat`, `health.json` `equity.seats`);
  the swarm's reader shows the book every waiting Candidate (`bands.read(..., queued=True)`) and its roster reports
  the book's plan. K's two counts are written beside the look, once (league/swarm/elane.py `elane_seat`), and for
  a program that passed before the release by `elane.seat_backfill` in the gate's equity round, from unsealed runs
  only. league/live/money.py is not edited: `EquityTable` does not read the block.
- **Its costs, as A24 states them.** Closes concentrate in frequent traders, so Done reached this way is weaker
  evidence of skill; a daily slice of a quarter sleeve can buy rank (and, A30 adds, immunity from the idle rule:
  nothing in the pipeline refuses it); a slow, non-idle incumbent keeps its seat. Not covered by A30 (2), stated: a
  session the House did not look at in either entry window (it was not running) counts for the idle clock.
- **Against the study's simulator** (EQDONE-3, whose seat logic was the reference): the rule built is the rule
  simulated, with these differences, each resolved toward A24. (1) Free seats are filled before any idle yield: the
  simulator yielded and re-seated an idle program in one sync when a seat was free, restarting its clock. (2) A
  buy counts as asked when its order reached the venue, filled or not; the simulator's orders always fill. (3) K
  is compared as an exact fraction and a close day's weights are summed in decimal; the simulator used floats.
  (4) The seating pass fills a free seat between two decisions; the simulator seats once a day. (5) A seating
  that does not take falls through; the simulator's always takes. (6) A program without its two counts ranks
  last until the backfill writes them; the simulator knows every K. (7) The swarm's roster can lower the seats.
- **Identities.** The money digest moves once, with the block: the pair in force is in the design block of release
  E5-S below, and every pair of the grid moved with it (`DIGESTS` in league/tests/equity_design.py, regenerated
  by the tree's own digest functions; each pair with the block left out is still release E5-S's pin,
  `DIGESTS_E5S`). The options execution fingerprint (`b60410ad`) and the equity identity (`78022ca6`) are release
  E5-S's: no file of league/live, league/gym or the equity evidence modules is edited.
- **At the deploy.** Nobody is unseated; each seat keeps its own day and the idle clock counts from it; the open
  note starts with the release. The grant re-ratifies at the House's start. The swarm's next equity round writes
  K's counts for every passed program.
- **Rollback**, one owner deploy: `equity_money.probe.seat.rule` "first-come" (one money-digest move; the grant
  re-ratifies; nobody is unseated). Under it the band sync and the swarm's read are release E5-S's line for line:
  league/tests/test_equity_seats.py holds a week recorded on release E5-S to it, entry for entry. No open note is
  kept under it.
- **Merged with main** (release E2.4, the equity lanes' alarms, and release E5-S as deployed): no line of either
  is changed here.

### Release E3.1: an exit's wait for the practice proof has an end, and the twin is re-based after a difference, on `feat/equity-e31-exits-twin` (DEPLOYED 22:51Z Oct 11; one owner deploy with release E5-A above, from `release/e31-e5a`, on main `81963c87`; no identity moves of its own: the options execution fingerprint, the equity identity, the money digest and the constitution digest are main's; no evidence reset)

Two rules the captain registered at 20:13Z Oct 11, 2026, from the rehearsal of the first real-money share session,
**both before the first real share order** (and A29 before any twin row existed). Plumbing only: `league/equity/live.py`
and `league/ops/forward_db.py`, `forward_twins.py`, `forward_report.py`; no file of `league/live`, `league/gym`, the
equity evidence modules, the constitution or the gateway is edited.

- **A28, an exit's wait for the practice proof has an end** (amends A10.1). Until now every real sale (a program's
  own, the maximum-hold exit, the owner's flatten) waited for the stock paper proof's SELL stage with no end: if the
  practice sale could not be witnessed, real lots stayed held for days and new buys stopped. From this release the
  wait ends at the open window's entry cut-off (`schedule.Moments.entry_until`, the open + 900 s, the minute the
  book stops trying open entries): after it every exit goes through the normal path, with one error alert a session
  saying the sale path is unproven and naming the stage's own reason (kv `eq_sell_unproven`). A close-window sale
  is past the cut-off by construction and never waits on the stage. Unchanged: stage BUY gates every real buy with
  no end; a failed SELL stage stops new buys; the minimum hold, the kill switch and the stops. **Why:** an exit must
  never be blocked; a proof exists to stop new risk, not to trap old risk. **Its cost, as the captain stated it:** a
  real sale can go through a path the practice account did not prove that day. The proof's own alarm still says
  "Real equity lots stay held" (`league/live/paper.py` is inside the options fingerprint and is not edited for a
  sentence); docs/operations.md says which words stand.
- **A29, the twin is re-based after a difference, so a miss counts once** (amends how A14's intent agreement is
  computed, never its bounds). A14 compared each live session's intents with a replay twin that never misses a
  fill; the rehearsal measured that ONE missed buy of a program that buys only when flat leaves it a session behind
  its twin for good (about half its sessions differ from then on), and that one such program fails the pooled 95%
  bound for every program at the checkpoint. From this release a session whose intent keys differ is counted as
  differing, exactly as registered; THEN the twin's book is set to the live book as it stands after that session
  (its lots, and what it had planned for the next session, read from `live.sqlite` read-only), so the sessions after
  it are compared from the same state. A re-based twin that differs again counts again and is re-based again. The
  95% bound, the 15 bp gap bound, the keys and the pooling do not move, and on a path with no difference the rows
  are byte for byte the rows of the release before (their sha256, taken on main `e36c7e39`, is pinned in the
  tests). The un-re-based shadow of every program (its forward record from registration) is still written every
  night, unchanged, and the reports say beside each instance how many times its twin was re-based and the
  un-re-based twin's own agreement (`fills.rebase`, each checkpoint's `a14.rebase`). **Why:** the clause asks
  whether live execution matches replay; the number of sessions on which it did not is that measure. **Its cost, as
  the captain stated it:** a program can run for weeks on other days than its unconditional replay and still read
  consistent after the one counted difference; the forward record beside it says so.
- **The store.** `forward.sqlite`'s `fwd_twins` gains two nullable columns (`rebased`, `base_agree`) and the forward
  log one event kind (`twin_rebased`). A store made before them is migrated at its next writable open with `ALTER
  TABLE ... ADD COLUMN`: no row is rewritten, the append-only triggers stand, and an older row reads no re-base.
  Rows written before this release stand as written; a stored differing session re-bases the twin for the sessions
  not yet written. No setting, job or alarm changes.
- **How the re-based twin is made.** The engine's own account (`league.equity.engine._Account`), driven from ops
  with the seeded lots bought by the engine in their own entry sessions and every decide asked of the night's
  decider child; one instance of the program asked every session in order, so only the book is set. No program
  text runs in the job's process and nothing of the engine is re-implemented.
- **Measured on the rehearsal's harness** (the real book on a fake venue with invented prices, the real forward
  stack). The week: a week in which the proof passes is order for order the week it was; with the practice account
  listing no FILL activity, or the practice sale resting, Tuesday's sales and Thursday's maximum-hold exit go at
  the cut-off, and a flatten queued before the open is out by the cut-off's next minute (before: every lot still
  held on Friday). The thirty sessions
  of the program that buys when flat: every buy filled, 28 of 28 sessions agree and nothing is re-based; Monday's
  buy missed, one differing session, one re-base, then agreement (28 of 29; as registered 15 of 29); a later rebuy
  missed once, the same (28 of 29; as registered 21 of 29).
- **Roll back:** the previous House release. It ignores `eq_sell_unproven`, the two columns and the event (its
  inserts name their columns), and its nights compare every session with the un-re-based twin again.


### 20:25Z Oct 11, 2026: release E2.4, the equity lanes' own alarms (#540), House `20261011T202519Z-50def634e716`, main `81963c87`; gateway `9c0651a3`

Gateway first (`9c0651a3`, 456/456; rollback `f9528af2`): its notice list names the four equity causes. Then the owner
deploy: CI green on the exact head; no order in flight at 20:25:10Z; promoted, the watchdog clean (rollback
`20261011T190534Z-dc7e047c9530`), nightly back 20:36Z, updater repointed. Verified 20:36Z: health clean, real money on;
execution fingerprint `b60410ad`, constitution `c3c061b0`, money `6c0bc42b` and gate contract `397b22b772b3` unchanged.

- Seen on the House after: the 20:50Z stall run carried the four checks, each "Not judged" for its own reason, with
  no error and no owner step.
- No deploy (`swarm.json`), 21:25Z: `elane.birth_share` 0.5 -> 0. The idea space on four index funds was spent on the
  lanes' first day: the last two equity passes proposed six families each and the graveyard refused all twelve, and
  no family was left in research. The barren-births cause would have become an owner's step six hours after the
  last birth; the decision it asks for was already made (the universe stays four index funds under a raw-P&L
  screen; breadth is the panel), so the equity births are off until a panel lane is at "train". The options lanes
  got their earlier room back (`gym.max_boxes` 2 -> 3, `architect.every_seconds` 10800 -> 5400).

### Release E2.4: the equity lanes alarm on their own stalls, their research funnel, and an architect kept inside the universe and told in closed words, on `feat/equity-e24-health` (DEPLOYED 20:25Z Oct 11; a gateway deploy FIRST, then an owner deploy on main's E3; no identity moves; no setting changes)

In the equity lanes' first hours (Oct 11) most scored versions were disqualified by one misreading of the contract,
families were retired for it, the lanes were starved at their pace, one births pass was cut short and another bore
nothing because every proposal named symbols outside the universe. No alarm fired: the stall job watched the options
lanes. The captain found each fault by hand. Release E2.2 fixed the misreading and the pace; this release tells the
owner when the lanes next go wrong.

- **Deploy order: the gateway first.** `gateway/lib/email.mjs` `STALL_CAUSES` gains the four causes' words (the
  release's one change under `gateway/`, with its test). The House names the four in `stall.CAUSES`, and a notice
  naming a cause the gateway does not word is refused whole (a 400: nothing of it is mailed), so the gateway is
  deployed before the House release, as for the causes of Oct 10.
- **Four stall causes of the equity lanes' own** (`league/ops/elane_health.py`, a new module the `stall` job calls
  once; read-only), each with its sentence, numbers, what the floor does by itself and the owner's step:
  - `elane_dq`: more than half of the versions scored in the last 6 h (6 at least) could not be judged for a fault of
    their own program (disqualified, refused at load, failed by the decider child), in at least two families. With
    fewer than 6 in the 6 h it judges the last 6 scored since the running release started, and before the sixth
    version it stands once 4 of two families could not be judged. Once it stood under a release it holds until
    versions scored after it stood are judged by the bar in two families, or the release changes. It names the
    first error's class only when one class is more than half of the disqualifications (else the classes that tie)
    and, for a class it names, the reading rule's sentence for it or what the class most often is. The owner's
    step: fix the text the generators read, in a release.
  - `elane_births`: the last 3 equity passes that asked a model bore no family. It names how, the commonest refusals
    in the House's own closed words and the symbols `elane.universe` does not hold. The owner's step after 6 h with
    no birth, when a setting clears it (the universe, the structures, the output limit); at once when every route
    refused the request for a setting, which the pass's event now names.
  - `elane_idle`: A BROKEN LANE ONLY, judged first by the lane's own record. BY ITS ANSWERS, idle or not: more
    than half of the program questions the Train rounds asked in the last 6 h (8 at least; fewer in the 6 h: the
    last 8 asked since the running release started; before the eighth: 5 lost) were LOST TO A FAULT, the answer E2
    paid for holding no program or no route answering for 3 h while the lanes kept asking; the owner's step names
    the routes, each one of `elane.e2.routes`. BY ITS FAILURES, once idle: work is owed and no version was scored
    for 3 h (a clock kept per release, less the time the swarm was down), and the record since shows two rounds
    that raised, two Train steps failed on the House's side or two step errors. Either stands whatever E2's lines
    hold, with that kind's owner step, says the line second when E2 is also held, and HOLDS once it stood under a
    release until a version is scored after it, the release changes or no work is owed. Else, idle, it stands only
    when no hold of E2's was seen in those 3 h (the lane may ask a model and still scores nothing).
    STARVATION BY A SETTING IS NO STANDING CAUSE: a lane held by its
    own hourly pace, its day's dollars or the House's Sail day reads judged clear, never stands and never mails,
    and its sentence and numbers say what the setting cost (the Train steps due, taken and skipped by reason;
    whether E2 is held now; the lever). The cost: a lane starved by a setting is read in the receipt and the
    research funnel (`train_steps`), not in the mail.
  - `elane_refused`: more than half of the programs written in the last 6 h (8 at least) were refused before a run by
    one static rule. With fewer than 8 in the 6 h it judges the last 8 written since the running release started,
    and before the eighth it stands once 5 were refused by one rule. It names the rule and its commonest sentence.
    The owner's step: teach the rule, in a release.
- **Judged only when there is something to judge:** the lanes on (`elane.mode`, `elane.birth_share`), the floor not
  paused, E2's dollars not set to zero, an equity family or pass on record, and enough evidence SINCE THE RUNNING
  RELEASE FIRST STARTED (kept in `stall.json`, `elane`: a release that fixes a fault is a new release; a restart of
  the same one resets nothing, and neither the idle clock nor when `elane_dq` stood, which are kept under it). Else
  "Not judged", with the reason; and lanes that could not be READ (the settings, one of E2's readers, the store, the
  lane's own reading of its hold) are an `errors` entry naming the class at every run and one House warning every
  12 h, so the alarm never switches itself off in silence.
- **Raised by the stall job's own machinery**, under their own names: standing in `stall.json`, one House warning
  every 12 h, the notice at the job's pace (an owner step at once and every 12 h, the rest every 24 h), cleared when
  it no longer holds, on the daily page's standing causes, and counted by Done's item 7 like any owner step waiting.
- **Each is an entry of its own in the mail,** under the gateway's words for it ("most equity versions could not be
  judged", "the equity passes bear no family", "the equity lanes are idle or starved", "most equity programs
  refused before a run by one rule") and keyed by its own name: an equity owner step is mailed at once whatever the
  swarm's own alerts told, and theirs whatever these told. Nothing rides `swarm_alerts`. (The gateway's words for
  `elane_idle` still say "idle or starved": the gateway is not changed again, and a starved lane no longer reaches
  the mail under them.) A House warning keeps an owner step whole inside its 900 characters.
- **No text a program or a model wrote reaches a notice, a warning or a standing check's sentence:** a
  disqualification is told by its class and line, a refusal by its rule and this module's words for its sentence, a
  refused proposal by its class and the symbols of the code's own universe. (The receipt's examples name families by
  their ids.)
- **The research funnel** (`league/ops/funnel.py` `equity.research`; the `scoreboard` job's private receipt carries
  the funnel's equity block, `equity`; `python3 -m league.ops.elane_health --state DIR` on the box): equity passes
  and families born, proposals refused by reason class, programs refused before a run by rule, the Train rounds'
  steps taken and skipped by reason, versions scored, disqualified and failed by code, bar passes, review refusals
  and passes, families retired, E2's model dollars. The daily page prints no equity row, as before.
- **The architect is not led outside the universe, and is told in closed words.** The equity request's
  contract-in-brief named the costs of "the other ETFs", TLT and GLD whatever `elane.universe` held; it now names the
  half-spread of each group the universe holds, in its own symbols, and says a proposal naming any other symbol is
  refused whole; while the universe holds no sector ETF, one sentence after THE AGENDA says to read "sector ETFs" as
  THE UNIVERSE's own symbols. The last pass's refusals are said by class, in the House's one sentence a class with
  the House's own values, the proposal named by its place in the answer (its lane and agenda key when valid): never
  a lane, structure, agenda or symbol as the model spelled it, and never its slug (the House's slug rule keeps a
  model's words). The request used to show each refusal's own text and the slug to a reader that may be another
  route's model.
- **The lanes' output settings are held to the provider's own limit.** `ltcm/provider.py` names the limit it already
  enforced (`MAX_OUTPUT_TOKENS`), and `elane.e2.births_max_output_tokens` and `train_max_output_tokens` are bounded by
  it, read from it (they were bounded at 64,000: on Oct 11 a setting inside that bound failed every route of one
  births pass). A births pass every route refuses for a setting says which in its event.
- **Settings:** none added to `swarm.json`, none changed. One owner's switch in `ops.json`:
  `{"stall": {"elane": false}}` stops the four from being judged. What changes at the deploy without a setting: the
  four causes are judged and told, Done's item 7 counts their owner steps, the `scoreboard` job's receipt gains
  `equity`, `stall.json` gains `elane`, the equity request's wording above, and a `swarm.json` value of either output
  setting above the provider's limit reads as its default (24,000 and 12,000).
- **An alarm never loosens a judge:** no screen, bar, budget, seat, money rule, graveyard or refusal rule changes, no
  program is read, parsed or run by the alarm, and nothing under `league/live/`, `league/gym/`, `league/equity/*.py`
  or `league/constitution.py` is touched: the execution fingerprint, the equity identity and the money digest are
  main's.
- **After its independent check (Oct 11; one blocker, three majors, seven minors, each fixed with a test; and the
  output settings' bound, found by the captain the same day):**
  the day's dollars spent is no stall (the cause stood every evening on a healthy lane; the rule that judged
  starvation by work lost, added then, is removed by the ruling below); the four causes are worded by the gateway
  and each keys its own mail (carried in `swarm_alerts`, they and the swarm's own alerts held back each other's mail
  for up to 12 h); a reader that fails is an `errors` entry (all four read "Not judged" in silence); the architect is told a
  barren pass in closed words; `elane_dq` needs two families, does not lapse at its window's edge, names a class
  only when one is most, stands at four that could not be judged, and says in its step what the class most often
  is; evidence counts from the running release's first start, not from every restart; the starved lane's lever says
  which line binds; with no family left, barren passes come before what the families now gone left behind. The
  check's two replays are tests on an invented House where the real equity pass, Train round and stall job run.
- **After its second independent check (Oct 11; two majors, both in `elane_idle`, and five minors) and the captain's
  ruling on it:** `elane_idle` alarms on a BROKEN lane only. A lane whose every Train run failed on the House's
  side read "STARVED, not broken" at every run whenever E2 was also at its pace, and the owner's step never came:
  BROKEN is now judged first, by the lane's own record. And the starved-by-work-lost rule of the first fix counted
  only the steps of rounds that started (no round starts while E2 is held), so it stood for one cost ratio only,
  flapped and mailed daily where it did: it is REMOVED, with every standing or mailing of a lane held by a setting;
  its counts stay, in the check's sentence and numbers and in the funnel. The minors: `elane_refused` judges the
  last 8 written and stands early at 5 by one rule (it lapsed to "Not judged" at a slow pace with nothing fixed);
  unreadable lanes are a House warning every 12 h (the receipt's `errors` reached no one); `elane_dq` holds once it
  stood (it cleared and stood again as its window slid); the idle clock is kept per release less the time the
  swarm was down (a broken lane restarted inside 3 h was never judged idle); a House warning no longer cuts an
  owner step, the budget's floor is said before the lever's command, the idle hours say "at least" when the
  lookback bounds them, and the design notes call the replay a replay. The second check's probes are tests: the
  broken lane at its pace, the slow reading-rule world and a lane of one family whose hold flaps (no step of its is
  ever skipped: the job's own reading of the hold, kept from run to run, is what says it is held) on the invented
  House, the restarts and the unreadable readers on the stall job. `gateway/` is not touched by this round.
- **After its third independent check (Oct 11; one major and one minor, both in `elane_idle`) and the captain's
  ruling on it:** an answer E2 paid for that holds no program it can score ("the answer held no program": a
  programless, an unreadable or a cut-short answer) and a question no route answered are WORK LOST TO A FAULT, not
  to a setting. In the check's break every Train answer was paid for and held no program: under any hold of E2's
  the four causes stood at none of 61 runs in thirty hours, `elane_idle` said "STARVED BY A SETTING, not broken ...
  programs were refused before a run (see elane_refused)" and `elane_refused` said none was; with no hold it stood
  as information, with no owner step. Now `elane_idle` stands BROKEN BY ITS ANSWERS when more than half of the lane's
  program questions over the window are lost and there are enough of them (`ANSWERS_HOURS` 6, `ANSWERS_MIN` 8,
  `ANSWERS_SHARE` a half, `ANSWERS_EARLY` 5: the window and its reasons are `elane_refused`'s), whatever E2's lines
  hold and whether or not the lane still scores a version now and then, with an owner step that names the routes
  in closed words (each one of `elane.e2.routes`). It is `elane_idle`'s BROKEN and not `elane_refused`'s family
  because that is what reads truest: a lane that pays for answers and gets no program cannot do its work, no rule
  refused anything, and the gateway words `elane_refused` "by one rule". A question no route answered counts only
  once none has answered for 3 h while the lanes kept asking (a route's bad hour heals by itself, and is most of a
  slow lane's window while it lasts). One answer in ten raises nothing. Lost answers too few to be most are said
  in the receipt with how many it takes, and a held lane that has any no longer says "not broken". The minor: a
  BROKEN lane's owner step lapsed to "STARVED BY A SETTING, not broken" with nothing fixed once a hold of E2's
  outlasted the 12 h of events the check reads (21 hours of a day under the Sail guard in the check's replay, the
  reminder stopped): once a BROKEN kind stood under a release it HOLDS (`stall.json` `elane.broken`) until a
  version is scored after it stood, the release changes or no work is owed. Not changed by this round: programs
  refused before a run by several static rules with none most stay `elane_refused`'s to read (it stands on one
  rule only), and stand on nothing in a held lane; nor are a stop before any version was judged and the same
  program sent again lost to a fault (answers the lane could read, the generator's own, each in its author's next
  brief). The third check's break and its Sail-guard day are tests on the
  invented House, with a healthy lane that loses one answer in ten. `gateway/` is not touched by this round, nor
  `league/ops/registry.py` or `funnel.py`; of `league/ops/stall.py`, one sentence of its docstring (what a broken
  lane is).
- **Merged with main** (Oct 11; main at `7d2d3c84`: release E3 as deployed). Six files touched by both, each merged
  mechanically, every line of E3 and of this release kept; `league/ops/stall.py` keeps E3's release receipts and its
  receipt's keys (the four are among its `checks`), `league/ops/funnel.py` an import and one call,
  `league/ops/registry.py` the stall job's description. `league/ops/dlane_report.py` is untouched: item 7 reads the
  receipts' checks.
- Tests: `league/tests/test_elane_health.py` (the closed words held to the code that writes the records by running
  it: the equity pass's admission, the static rules, a disqualification's record, a real pass and Train rounds; the
  notice held to the gateway's cause list and its cuts; hostile text in every field of a barren pass; the three
  checks' replays, `league/tests/elane_e24_house.py`) and `gateway/test/stall-notice.test.mjs`. Operations:
  [docs/operations.md](docs/operations.md), "The equity lanes' own alarms" and "The stall alarm and the funnel".

### 19:06Z Oct 11, 2026: release E5-S, six seats at a Probe sleeve of 0.25 x E (#541), House `20261011T190534Z-dc7e047c9530`, main `e36c7e39`

Owner deploy only; the gateway is unchanged (`f9528af2`). CI green on the exact head; no order in flight at 19:05:19Z;
promoted 19:06:21Z (rollback `20261011T143700Z-c8e41ae6e37f`; the money rollback is the pair "3 0.50"), nightly back
19:16Z, updater repointed. Verified 19:16Z: health clean, real money on; money `7e41909a` -> `6c0bc42b` and
constitution `e909eb10` -> `c3c061b0` (the grant holds the new digest); execution fingerprint `b60410ad` and gate
contract `397b22b772b3` unchanged; no evidence reset.

- Why this pair: the share lanes' first day bred programs that passed sealed looks faster than seats freed, and the
  owner asked for Done as soon as possible. A pre-registered study put more seats at a smaller lot as a SPEED BET,
  not a better chance: the same dollars at risk, the thirtieth real close sooner, about level at twelve weeks and
  worse if the first counted close is a loss (the smaller lot is slower out of that hole). Its review advised
  keeping three seats until that close was known; the captain shipped six for the owner's stated aim and says so.
- Seen on the House after: the two waiting programs and one that passed during the deploy were seated at the first
  band sync, first come; all six seats are held (two seeded, four bred); three buys are planned for Monday's open.
- No deploy (`swarm.json`): 13:24Z `elane.e2.train_per_round` 3 -> 5, 15:57Z -> 4; 14:01Z
  `births_max_output_tokens` 32000 (a value over the provider's limit had made one births pass fail on every route);
  14:57Z `elane.e2.routes` without the route whose answers came back cut short.

### Release E5-S: the seats and the sleeve of the share lane are two numbers, on `feat/equity-e5s-seats` (DEPLOYED 19:06Z Oct 11 at six seats and a sleeve of 0.25; an owner deploy on main `7d2d3c84`; THE MONEY DIGEST MOVES with the pair, the grant re-ratifies; no fingerprint moves, no evidence reset)

- **What it is.** `equity_money.probe.max_programs` (the seats) and `probe.sleeve_share` are set together by one
  mechanical step, `set_design SEATS SLEEVE` (the captain's tool, kept beside the build's record, not in the tree).
  It rewrites the two rows, `elane.roster` (league/swarm/policy.json and the default in league/swarm/elane.py),
  `PINNED_DIGEST`, and the design blocks of four documents (below, the constitution's `probe` comment,
  docs/operations.md and league/equity/INTERFACES.md section 17), and nothing else; run again it changes nothing.
  The seats' bound goes from three to six (`EQUITY_MONEY_BOUNDS["probe.max_programs"]`, Claude's decision under goal
  item 4, its cost in the constitution's comment); the sleeve's bound stays 0.50; `sized.sleeve_share` stays 0.50
  at every pair (the Sized sleeve's floor is the Probe's in the code itself; the step stays parked).
- **The pair in force**, in rule arithmetic of the two numbers:

<!-- equity-design:begin -->
THE DESIGN IN FORCE: 6 seats (`probe.max_programs`, `elane.roster`), a Probe sleeve of 0.50 x E
(`probe.sleeve_share`). A one-ETF program's lot is `position_share.etf` (0.50) of its sleeve: 0.25 x E.
A lot in every seat asks for 1.50 x E of ETFs; the lane holds at most 1.00 x E of them, 0.20 x E of
open risk at weight 0.20. One ETF across programs (the instrument cap, 0.50 x E): 2 whole lots fit; the
next program's lot of it is 0.00 x E. At E = $2,000, the account all cash and nothing realized: 3 of
6 whole lots fit under the invested cap (1.00 x E) and the $50 cash reserve alone, and
4 of 6 in the $400 window alone; the window alone holds all 6 up to E = $1,333.
Whole sleeves (programs that hold several ETFs) ask for 3.00 x E; the lane holds at most 1.00 x E,
0.20 x E of open risk. The options Probe lane keeps $400 less the window's realized loss less 0.20 x
the equity lots: $400 - 0.20 x E against the one-ETF lots above. The gateway's day line (4x
equity of buys a day, a cancelled one too) admits 16 sends of such a lot: 3 entries can each climb the
collar's ladder of 5 sends. A Sized sleeve (the step is parked) would be between 0.50 x E and
0.50 x E.
Money digest `de5ed74e`, full digest `111ede85` (`PINNED_DIGEST`); the rollback, `set_design 3 0.50`, is `46b933a9` / `d9cf3149`.
<!-- equity-design:end -->

- **Whose choice.** The captain's, before Monday's open, from the verdict of the pre-registered study EQDONE-3 over
  seats 3, 4, 5, 6 x sleeve 0.50, 0.33, 0.25. The build left a working pair in the tree; the branch is not a
  release until the verdict's pair is set by the same step. Why the two move together: Done reads 30 real
  closes whose P&L sums above zero, more programs trading at once make closes sooner, and a smaller lot a program
  keeps the same shared loss budget over them. Its cost: more programs, the screen's false positives among them, on
  real money at once; the same spread and fees per dollar on a lot that earns a loss back more slowly; closes made
  sooner by long-only index ETFs are weak evidence of skill. It buys closes, not edge.
- **No owner line moves.** An ETF at most 0.50 x E across all programs, at most 1.00 x E invested, the cash reserve,
  the shared loss budget ($400 net in any rolling 20 sessions, $800 net in total), the program's -$300 line, the
  stops and the kill switch, the stock proof's gates: `size_entry` and the book apply each at every pair
  (`league/tests/test_equity_design.py`, `test_equity_sleeve.py`: every pair of the grid through the House's own
  sizing function). A seat only decides who may open: no lot is ever sold because a number changed.
- **At the deploy.** A Candidate waiting for a seat is seated at the first band sync, first come, and asked for the
  same close; a buy already planned is sized at its send under the sleeve in force; a lot larger than a smaller
  sleeve keeps its own exits, and its program's next entries are held to the sleeve in force; seats moved down
  unseat nobody. All of it is the code as it was, now tested through the real book and the real swarm store.
- **What a pair can make bind** (docs/operations.md, **The seats and the sleeve**): cut or refused entries where the
  seats' lots do not all fit (the Gym fills them; A14 reads the difference); the day's 60 equity orders, sized for
  three programs, on a day most orders are re-priced; the gateway's day line on a day every entry climbs its whole
  ladder, at the pairs `league/tests/test_ci.py` names. None sells anything.
- **Identities.** The options execution fingerprint (`b60410ad`) and the equity identity (`78022ca6`) are main's: no
  file of league/live, league/gym or the equity evidence modules is edited (league/live/money.py's two comments on
  the table's rows stay as A20 wrote them for that reason). The money digest and `PINNED_DIGEST` are the pair's, in
  the block above; every pair of the grid is pinned in `league/tests/equity_design.py`, and `set_design 3 0.50` is
  the rollback of the pair, one owner deploy. On this release alone it was E1's `7e41909a` / `e909eb10` again, to
  the last hex; with release E5-A's seat block in the table the pair's digests are the ones the block above
  states (and still E1's with that block left out).
- **Also changed.** `league/ops/dlane_report.py`: A8.6's statement is built from the rows (`equity_probe_note`), no
  longer a sentence with A20's figures in it. The gateway is not edited.
### 14:37Z Oct 11, 2026: release E3, record and measure (#539), House `20261011T143700Z-c8e41ae6e37f`, main `7d2d3c84`; gateway `f9528af2`

Gateway first (`f9528af2`, 14:36:49Z): its merge list gains E3's three swarm modules, a tightening. Then the owner
deploy, 14:37Z. Verified 14:48Z: health clean; the execution fingerprint, the equity identity and the money digest
unchanged, so no grant ratification and no band reset; seats 3 of 3.

- `forward_shadow` skipped ("no forward day in the store yet"): the registry's first forward day is 2026-10-13.

### 11:44Z Oct 11, 2026: release E2.2, the equity lanes read ctx as it is given (#538), House `20261011T114321Z-af12ca87b92f`, main `87f9fd0c`; gateway `0c093de7`

Gateway first (`0c093de7`, 455/455; rollback `8a349b8e`): its merge list gains E2's five swarm modules, a tightening.
Then the owner deploy: CI green on the exact head; no order in flight at 11:43:17Z; promoted 11:44:05Z (rollback
`20261011T082429Z-ee10331072db`), nightly back 11:54Z, updater repointed. Verified 11:54Z: health clean, real money
on, execution fingerprint `b60410ad`, constitution `e909eb10`, money `7e41909a`, gate contract `397b22b772b3`, all
unchanged, so no grant ratification and no band reset; the two seeded programs keep their Probe seats.

- Why it shipped alone: it was built to ship with the START check (E2.1) in one release; E2.1's independent check
  was still running, and came back not ready an hour later. E2.1 is not deployed.
- The release's own check found that the reading rule let through bars read "as a dict, else as rows" behind a
  type check; fixed before the deploy (the last commit of #538), with the contract's list of exception names.
- No deploy (`swarm.json`): 11:54Z `elane.e2.pace_share` 0.5 -> 1.5 and `elane.e2.usd_day` 12; 12:42Z by measured
  yield per dollar `pace_share` 2.0, `usd_day` 16, `gym.max_boxes` 3 -> 2, `architect.every_seconds` 5400 -> 10800.
- Seen on the House after: every version the researchers wrote under the new contract ran (none disqualified by
  the misreading); the first bred family passed the Train bar 12:26Z, its Validation 12:28Z, and took its one
  sealed look 12:28:51Z under S2, which it did not pass.

### 08:25Z Oct 11, 2026: release E2, the swarm breeds share programs (#536), House `20261011T082429Z-ee10331072db`, main `5ad1f01e`

Owner deploy only (the gateway's merge list for E2's modules followed with E2.2, above): CI green on the exact head;
no order in flight at 08:24:18Z; promoted 08:25:13Z (rollback `20261011T071808Z-351f760913c3`), nightly back
08:35Z, updater repointed. Verified 08:35Z: health clean, real money on, the four ids unchanged from E1's. It shipped
switched off.

- No deploy (`swarm.json`): 08:36Z equity births on: `elane.birth_share` 0.5, `elane.e2.pace_share` 0.5,
  `births_every_seconds` 1800, `min_per_pass` 3, `max_alive` 48; the options lanes made small: `gym.max_boxes` 7 ->
  3, `architect.every_seconds` 1800 -> 5400.
- Seen in the first hour: most scored versions were disqualified by one misreading of the contract (a symbol's
  bars read by key), and the lanes were held to about $4 a day by the pace bound. Both are E2.2's reason.

### 07:18Z Oct 11, 2026: release E1, the share lane (#535), House `20261011T071808Z-351f760913c3`, main `05f83d9e`; gateway `8a349b8e`

Gateway first (`8a349b8e`, 455/455; rollback `95e7a8d0`): its merge list gains `league/equity/`,
`league/swarm/elane.py`, `league/xs/` and `ltcm/broker.py`. Then the owner deploy: CI green on the exact head; no
order in flight at 07:17:57Z; promoted 07:18:52Z (rollback `20261010T214125Z-d4667186f969`, allowed only while no
equity lot is open), nightly back 07:29Z, updater repointed. Verified 07:29Z: health clean, real money on;
execution fingerprint `31a7e921` -> `b60410ad`, money `fdf2ac7c` -> `7e41909a` (the grant ratified on it
07:19:26Z), constitution `e909eb10`, gate contract `397b22b772b3` unchanged; the `equity_data` job ran and its
audit passed; the equity tables exist; the stage BUY practice proof waits for an open window.

- No deploy (`swarm.json`): 07:29:55Z `elane.mode` "gate".
- The three seeded programs took their looks in the registered order (decision A18): `seed-overnight-qqq` and
  `seed-reversal-index` passed under S2 and hold Probe seats; `seed-overnight-spy` was refused its look as the
  same lineage as the first. No share order was owed for Monday's open.

### Release E3, record and measure: the forward record, the fill measurements, the hidden year and the contamination probe, on `feat/equity-e3` (DEPLOYED 14:37Z Oct 11; the gateway's merge list, then an owner deploy on main's E2.2; no identity moves; records only)

- **What it adds** (`league/ops/E3_INTERFACES.md`): a hash-chained registry of every equity version judged on the Train
  bar, passed or failed, with each seed, each live instance and 50 skill-free controls a universe group
  (`<state>/forward.sqlite`, append-only); a nightly recompute of each on its own forward days in the job's own
  decider child, with checkpoints at 20, 60, 120 and 250 sessions; the send-minute bars, the live-like re-price and
  the fill gap of every closed live lot; live and shadow intents compared session by session; one hidden Train year a
  new family, its out-of-fold run kept in sealed tables; a weekly contamination probe of the model routes; release
  receipts read back after a deploy; and the report (`<state>/forward-report.json`, a `forward_record` section and
  alarms in the `dlane` report, counts in the funnel).
- **It records and measures only.** No money moves, nothing is gated, no generator is shown anything new and no
  forward verdict is written. Forward days begin the session after the look cap (2026-10-12).
- **Pre-registered:** every program row carries its forward route and alpha (S2, 0.03) inside the hash chain and the
  forward screen's shape is pinned in the store at its creation, so no rule can be chosen after the outcomes it judges.
- **Two readings change, both stated.** Done's "live fills consistent with their replay" (A14) is computed: the size of
  the mean fill gap within 15 bp a side, either way, and the intents agreeing on 95% of the counted sessions; unmeasured,
  it does not hold (a tightening). A family born with a hidden year is judged on six Train years, not seven, each
  stretch its own run (a loosening of the Train bar; the share screen's false-positive rate per program is unchanged).
- **Six House jobs** (`league/ops/registry.py`): `forward_register` (hourly), `fill_minutes`, `forward_shadow`,
  `forward_report`, `forward_audit` (all five run in a pause) and `contam_probe` (Saturdays, paid, at most $3 a run
  and never more than what is left of the equity lanes' research day).
- **Switches:** policy.json ships `elane.forward.mode`, `elane.memory.mode` and `elane.contam.mode` at "record"
  (an unrecorded forward day is lost for good); swarm.json "off" is the rollback of each. With the forward mode off
  A14 is unmeasured, so no Done checkpoint holding an equity close can hold; a family already born with a hidden year
  keeps it whatever the memory mode.
- **No identity moves:** nothing under `league/live/`, `league/gym/`, `league/equity/` or `league/constitution.py`
  changes, no decider kind is added and nothing of E3 enters the equity evidence's import closure. The three new swarm
  modules are in `league/ci.py` `FORBIDDEN` and in the gateway's merge list (`gateway/lib/protected.mjs`
  `MERGE_FORBIDDEN`: the release's one change under `gateway/`, so the gateway deploys first, as for E2's five);
  `PENDING_GATEWAY` is empty. Read with the repository's own functions at the
  integration: the execution fingerprint, the equity identity and the money digest are equal on the E1/E2 tree it is
  built on (`feat/equity-e2-int` at `5ad1f01e`) and on its head. (All three moved between `5a6906ff`, where the
  packages were cut, and `5ad1f01e`: E1's and E2's own review fixes, theirs to state at their deploy.)
- **Integrated** (five packages, then `feat/equity-e2-int` at `5ad1f01e`, which holds `feat/equity-e1` at `05f83d9e`
  and `feat/equity-e2` at `04ca26c9`): the six jobs, the three policy blocks at "record", the three walled paths, the
  funnel's counts, the report's section and alarms, the Done meter's A14 on E1's own reader (a checkpoint's reading is
  handed the forward record's A14 and holds only when both say yes), the stall job's receipt read and E2's three
  hooks. **Fixed at the integration:** E1's store now hands a slice its history + 1 sessions itself, so the shadow
  asked for one session too many and its official prices read None (the timing table and every live-like re-price
  would have been empty); the declared receipts lay under `docs/`, which never reaches the House (no receipt would
  ever have been declared or read, in silence): they are `league/ops/release_receipts.json`, with a guard test; alarm
  FW3 mailed a warning on every routine ex-day: its level is now its cause (info when every restatement read bars the
  vendor has since moved; a warning when the recompute itself moved).
- **One test of the whole:** `league/tests/test_e3_end_to_end.py`, the real modules together from a Train scoring to a
  Done checkpoint that carries A14, the generators' views byte for byte unchanged; and with the three modes off every
  job a skipped receipt that touches no gateway, model or decider child.
- Operations: [docs/operations.md](docs/operations.md), "The forward record" (what is recorded, the switches and what
  each does not reach, A14 as coded, the hidden year, the stop rules and their undo, the alarms, the facts to verify
  on the House).
- **After its review (Oct 11; twelve findings, all fixed on the branch, each with a test):** the hidden run has a
  decider child of its own, started for one version and closed after it (a program's memory outlives a run wherever
  its interpreter does, and the swarm's one evidence child runs the family's next version: the blocker); a hidden
  year the family's record already holds (a code rollback judged it on all seven years) is void and leaves no
  out-of-fold row; a probe's request key is asked once (the router answers a repeated key from the provider's stored
  row at its original cost, blanked after an hour); the stop rules count a program's own attempted nights, a hung
  run keeps its retry and loses the queue's head; every step of the night reads its deadline; a day's meters wait
  for the rows a budget-cut night left out; the any-edge meter shows no count over fewer than five lineages; each
  alarm follows its own switch (RR, CP and MM are raised with the forward record off); CP1 counts from a route's
  last completed probe; a capped program's grid checkpoint is a grid row; a revived live instance keeps its
  retirement and gets a twin of its own; the meters and the night's queue fit the ops child's address space at the
  settings' bounds. Four event kinds are new (`run_behind`, `twin_retired`, `twin_revived`, `meter_partial`); no
  table or column is. `league/ops/E3_INTERFACES.md` section 11 lists each fix against the spec.
- **After its verification (Oct 11; an independent verifier: no blocker and no major left; one minor finding,
  fixed with a test that failed before):** one program that never got a row again (a holder of a halted symbol, a
  program that hangs every night) was awaited by every later day's meters, so each came three sessions late and was
  marked partial, for good, and FW5, which reads no partial day, read nothing from then on. Only an absence the
  next nights can fill is awaited now: one that began that day, or one of fewer than three sessions running of a
  program that is neither suspect nor behind in the queue; a day is marked partial, and left out of FW5, only for
  those; a control whose data failed is awaited the same way. No table, column or event kind is new.
- **Merged with main (Oct 11; main at `87f9fd0c`: releases E1, E2 and E2.2).** Every line of E2.2 (below) and of E3
  is kept. Resolved by hand: `league/ci.py` and `league/tests/test_ci.py` (E2's five modules are in `FORBIDDEN`'s
  own list as main has them, E3's three beside them), the import line of `league/swarm/elane_births.py` (both
  `elane_folds` and `elane_review`) and one pin of `league/tests/test_e3_identities.py`. The three ids read on the
  merged tree are main's, on Python 3.11 and 3.14. `league/ops/E3_INTERFACES.md` section 12.

### Release E2, integrated on E1: the swarm breeds share programs for the BETA and EQUITY lanes, on `feat/equity-e2-int` (DEPLOYED 08:25Z Oct 11; an owner deploy with or after E1; no identity moves; ships switched off)

- **What it adds** (`league/swarm/ELANE_E2.md`): the architect's equity pass (families with their first program, on
  the model route chosen by measured yield per dollar), the Train bar equity-v1 on the Train years 2016-19 and 2022-24
  with its STATE restart check (A15; 2020-21 is the reserve and no run touches it), a minimal equity researcher, the
  equity review (a static level rule and two paid readers) before a version may be its lineage's one Validation try,
  the seal that keeps every Validation, look and holdout outcome from every generator (A9 D3), the Train map, and the
  operator's yield-per-dollar record in the `dlane` report (`equity_yield`). After Train a family is E1's: Validation,
  one sealed look by the pinned share screen S2 (A11), Probe.
- **Ships off.** policy.json keeps `elane.mode` "off" and `elane.birth_share` 0 and gains the `elane.e2` block (every
  value the code's default). With either switch off nothing in E2 acts (a test on E1's real loop). The captain's first
  switch-on, after the deploy and with no deploy of its own: `elane.birth_share` 0.25 and `elane.e2.usd_day` 8.0 in
  swarm.json. Equity births are counted apart from options births.
- **In E1's files** (`league/swarm/ELANE_E2_PATCHES.md`, the record): the loop's two rounds; the options birth quota,
  population floor, stall facts and pre-open check counting the options lanes only; `visible_graveyard` dropping
  equity rows; the tournament validating an E2 family only with its Train pass and review; the five E2 modules
  FORBIDDEN (`league/ci.py` `PENDING_GATEWAY` until the gateway's merge list names them: a gateway follow-up, made
  Oct 11, 2026, which left `PENDING_GATEWAY` empty).
- **Fixed at the integration:** the equity architect was told the share screen S1 judges (it is S2); with the lanes on
  and the share at zero the equity Train round ran empty every ten minutes (it now waits for a family of its own).
- **Fixed after the integration's review** (three reviewers, Oct 10-11; `league/swarm/ELANE_E2_PATCHES.md` lists each
  with what was done). The blockers and majors: E2's Sail dollars landed on the options researchers' hourly pace and
  nothing paced E2 (at the first switch values E2's day was the whole pace): E2's dollars are now a share of the Sail
  model line, `elane.e2.pace_share` 0.25, counted apart, with its own hourly pace and a day the budget tightens;
  pre-open check 6 failed once any equity family held a live band (E1's line: it reads the options lanes now); a bred
  program could size on its own profit since the run began, which lifts a zero-edge program's pass rate at the share
  screen (the level rule refuses run-start dependence, and the rubric names it); an equity identity adoption let a
  re-bred near-copy take a second look (E1 fixed it, carried). The rest: every continued lineage checked at birth, the
  level rule's missed shapes, no memory in an object of numpy's, a LOAD refusal's reason shown and a
  disqualification's own words never, the audit's second model under a stalled Sail window, a timed-out call booked
  and ending its question, routes sampled on birth requests, the Validation alarm and Done's item 7 reading the
  options lanes with the equity lanes beside, an alert for a standing failure of the House's, no idle Train round,
  and the reserve's wording at E1's `history` + 1 slice.
- **Fixed after the verification** (an independent verifier, Oct 11: no blocker and no major left). Its finding: a
  bred program with no memory could still lock in a profit, by rebuilding the run's capital from its own lots (a
  lot's `qty` times its `entry` or `exit`, its `value` less its `pnl`, `exit` times `qty` less `net`) and holding the
  sleeve's cash or equity against it; a program that stops once ahead passes the share screen far more often than
  the screen's false-positive line says. The level rule now reads a lot's `qty` and what a lot cost as the run's
  anchor, in every spelling it can follow, and refuses the run's dollars written into a lot's `tag`; the run's
  dollars mixed with a price, a log, a cross-symbol ratio or a count stay the run's dollars (the lock with a price
  added to and taken from each side read as a ratio of two prices and passed); a lot's own return, a hold count and a
  size from `ctx.budget` pass as before. **What the static rule still cannot see** is said
  plainly in `league/swarm/ELANE_E2.md`: above all a lot's weight in the sleeve set against its own return, which
  passes the static rule and the restart check, so the two paid readers are the only guard there; their rubric names
  the pattern and ends on the rule (a rule whose trading depends on how far the run is ahead or behind is refused,
  whatever its spelling). Also: the review reads its dollar hold again before the audit; and the documents say
  plainly that the equity lanes' research spend is `elane.e2.pace_share` of the researchers' hourly pace (about a
  quarter at the shipped 0.25), that `elane.e2.usd_day` is only a cap above it, and that the captain sets the share
  with the settings tool at switch-on. (Release E2.2, below, makes that pace E2's own: the share's bound is 0 to 4
  lines, no longer at most half the line, and the House's Sail day bounds E2 in its place.)
- **No identity moves by E2:** it changes nothing under `league/live/`, `league/gym/`, `league/equity/` or
  `league/constitution.py`. The options execution fingerprint and the money digest are the ones E1 ships, and no
  evidence is reset by E2. (E1's own review fixes, merged here, move the equity evidence identity before its first
  look: the section below.)
- Operations: [docs/operations.md](docs/operations.md), "The equity lanes' births" (switch on, read, stop, the budget,
  the yield record).

### Release E2.2: the equity lanes read ctx as it is given, and their pace is their own, on `feat/equity-e22-yield` (DEPLOYED 11:44Z Oct 11; an owner deploy; no identity moves; the shipped settings are unchanged)

Two things seen in the equity births' first hour on the House, each fixed in E2's own modules and documents.

- **The generators misread the program contract.** `league/equity/EQUITY.md` said `ctx.bars[sym]` carries "arrays";
  it is ONE object whose six arrays are read by attribute (`ctx.bars[sym].close`). The first programs the equity
  researcher wrote mostly read it by key or as rows, every decide raised a TypeError, the version was disqualified
  (each costs model dollars and one of its family's scored versions), and its author was told the error's class and
  line only. Three layers (`league/swarm/ELANE_E2.md`, "Release E2.2"):
  - **The texts.** EQUITY.md says what each field of ctx is (read off `league/equity/ctx.py`), what a program has
    (plain builtins, `math`, numpy, no pandas), and gains "Reading ctx": a worked rolling-window program and the
    common faults (bars by key, bars as rows, a short or NaN window, a lot by attribute, a sell by a symbol, a
    malformed intent, an empty dict returned for no order). One sentence and two lines of it are in the equity
    architect's lanes block and the equity researcher's system prompt. No outcome and no figure is in them.
  - **A static pre-check, THE READING RULE** (`league/swarm/elane_review.py` `reading_refusals`, first of the static
    rules in `elane_train.check_code`): the misreadings that can be seen in the source are refused before a version
    is stored or run, each with its line and what to write instead. It follows a name only while every binding gives
    it one kind of value and never refuses on a guess. A refusal costs one of the family's write attempts, never one
    of its scored versions. After the release's independent check (three shapes it let through that E1 then
    disqualified): a check of a bar's type excuses a misreading only beside a sound read of the bar, so a helper
    that reads bars "as a dict, else as rows" is refused, and so is `ctx.bars.get(sym, [])` measured or indexed. The
    contract now lists the exception names a program has (there is no `AttributeError` or `NameError`) and says
    that a price or a dollar amount held against a constant is refused.
  - **The disqualification's brief.** E1's run result does carry the exception's text, and E2 keeps it out of every
    record and brief on purpose (a program chooses that text and reads reserve bars as look-back). The author is now
    shown the line of its own file the first error was raised at and what is wrong there (what the reading rule sees
    on that line, else one fixed sentence a class of error), worked out when the brief is written, so the versions
    already disqualified get it too. The House's own sentence about a malformed return is named in the record.
- **The equity lanes were starved.** E2's model spend was held to `elane.e2.pace_share` of the Sail model line, at
  most half of it: at the ceiling at most $0.17 an hour, $4 a day, so the lanes stood still for most of each hour
  while most of the day's Sail research dollars went unspent (the line is the model share of a day planned around Gym
  boxes; an equity Train run needs none). **The pace is now E2's own:** `pace_share` is held to 0 to 4 lines (shipped
  0.25, unchanged), `elane.e2.usd_day` stays the day's cap (shipped 8.0, held to 0 to 100), and what bounds E2 beyond
  the two is the House's Sail day: E2 reads the Sail guard's own record and, fresh before each model call, the
  swarm's Sail spend of the day, and stops a dollar before the line where the guard holds new research (its cap less
  the gate's reserve, and the day's even pace), so the dollar that reaches the guard's line is never E2's and
  the day's total never passes the guard's cap on its account. (The release's independent check, stated: at a high
  pace busy options lanes then reach the line themselves late in the UTC day and all new research waits for midnight,
  one to two and a half hours at four lines; and at the floor budget with the options lanes at the day's even pace
  E2 asks nothing all day, where it asked a little before.) The options researchers keep at least half their line
  whatever E2's pace (`elane_yield.usd_hour`, the loop's reading, is `min(pace_share, 0.5)` of the line: unchanged, a
  share above one would have paused every researcher).
- **What the captain sets** (no deploy of its own, read on the next loop pass): BOTH `elane.e2.pace_share` and
  `elane.e2.usd_day`, since E2's day is the smaller of `usd_day` and a day at its pace:
  `python3 set_swarm.py elane.e2.pace_share=<lines> elane.e2.usd_day=<dollars> --apply`. Left alone, nothing changes
  for a share of a half or less at the ceiling budget (at the floor, see the check's note above).
- **Open, for the captain** (`league/swarm/ELANE_E2_PATCHES.md`, the last section): the heartbeat's
  `researcher_pace.equity` block shows the line's share as E2's limit, so above a share of a half it reads "paused"
  while E2 is under its own pace (a patch for `league/swarm/loop.py`, not applied; E2's pace is in the `dlane`
  report's `equity_yield`); and `allocation.plan_usd_per_hour`, if ever set, counts E2's dollars.
- **No identity moves:** only E2's five modules, their tests, the documents, `league/equity/EQUITY.md` (a document no
  identity hashes) and a comment in `league/swarm/settings.py` change. The options execution fingerprint, the equity
  evidence identity and the money digest are the ones main carries.
- Tests: `league/tests/test_elane_e2_reading.py` (every shape the rule refuses is run on E1's real isolated runner and
  is disqualified there; the contract's worked example is taken out of the document, loads, trades and holds the
  restart check; the rule's tables are held to E1's own definitions) and `league/tests/test_elane_e2_yield2.py` (a
  day at four lines against the real Sail guard a minute at a time, and the real loop at the guard's line).

### Release E1, the verification's last fixes, on `feat/equity-e1` (DEPLOYED 07:18Z Oct 11; an owner deploy with the rest of E1)

Two independent verifiers read E1 after the review's and the rehearsal's fixes and found no blocker and no major.
What they did find is fixed here, each with a test that failed before.

- **The seeds' look order is strict within a lineage** (`league/swarm/elane.py` `seed_wait`, `seed_owed`,
  `league/swarm/seeds.py` `lineage`; amendment A18). The rehearsal's fix held a later seed for 30 minutes at most,
  once, on a clock that ran even while no look could be taken; after it ran out, one sealed run of the earlier seed
  the House could not make handed the lineage's one look to the later seed for good. Now each seed declares its
  lineage (the two overnight seeds are one; the reversal seed is its own), and a seed's look is never taken while a
  seed declared before it in the same lineage is alive without a verdict: it waits until the earlier one has been
  looked at (D3 then refuses the later one), has failed its Validation pre-check with no retry owed, or is retired.
  There is no timeout. The wait is asked at the look's last step before the sealed run, so its clock counts only the
  rounds in which the later seed's own look was otherwise ready; 30 counted minutes raise one House warning naming
  both seeds and why the earlier one has no verdict yet (again at most daily), cleared when the wait ends. Seeds of
  different lineages never wait on each other, and other families are untouched. **Changed for the operator: a hold
  on the earlier seed now holds the later seed of its lineage too; retire the earlier seed to give the look to the
  later one.** Swarm-side only: neither fingerprint moves.
- **A lost practice order no longer sticks the stock paper proof** (`league/live/paper.py` `StockPaperProof`). When
  the one stage-BUY (or stage-SELL) POST was answered unknown and the practice account never showed the order, the
  attempt stayed `buy_sent` for good: no new order, no alert, and so no real equity buy, ever. The proof now has the
  equity book's own rule for an order not found by its client id (four lookups or ten minutes): it is lost, terminal,
  nothing owned, one warning. A lost buy returns to waiting and the next open window tries again on a baseline read
  then; a lost sale goes again only while the practice account still holds the lot. A lost order is looked for again
  for three days, first of all before a new buy: one that surfaces with a fill is the practice lot it is (the attempt
  resumes at it, or its fill is counted in the attempt that had begun), so it cannot corrupt the next attempt's
  reconciliation. The options `PaperProof` is byte for byte as it was. `league/live` is hashed: **the options
  execution fingerprint moves**, as it already does once with E1 (no further cost: one adoption at the E1 deploy).
- **A Validation the House could not make is not a failed pre-check** (`league/swarm/loop.py`
  `Swarm.equity_rounds`). The round's line mapped every verdict to "entered or not", so a Validation that could not
  be made at all (the evidence child could not start: no run, no try spent) read `validated: false`, `errors: {}`,
  exactly like a failed pre-check. Such a verdict, and a refused one, is now under `validation_errors`
  {family: error} in the round's log line and in the heartbeat's `status.equity`; `validated` holds real verdicts
  only. A report only: no rule and no fingerprint moves.
- **A re-price goes every minute, whatever the milliseconds** (`league/equity/live.py` `_reprice_due`,
  `house_minute`; ops-10, which the review's fix left half done). Two House minute starts are 60 seconds apart give
  or take the milliseconds each pass started late, so "60 seconds old" was false for every minute that started a
  hair earlier in its minute than the last, and the open window re-priced every second minute again. An order that
  carries its minute's stamp is now aged in whole House minutes; one without it is aged from its POST in seconds,
  exactly, as before. `league/equity/live.py` is plumbing: neither identity moves.
- **The public wording** (this file's rehearsal entry below, `docs/operations.md`, `league/ops/equity_data.py`,
  `league/swarm/seeds.py`, `league/equity/INTERFACES.md`, three tests' docstrings). The rehearsal's commits had
  written counts read from the vendor's data, and two findings about the seeds on real Train data, into this public
  repository. They are reworded to what each rule IS and why (the daily bar's close is the closing cross; a flat bar
  of volume 0 is a session without a trade; the vendor rounds its adjusted prices to the cent; the seeds' declared
  order is the captain's decision, made before any Validation or look from Train-era figures only, amendment A18;
  the two overnight seeds share a template and are one lineage). A test holds the wording
  (`league/tests/test_equity_rehearsal.py` `ThePublicWording`). Comments, docstrings and docs only: no code and no
  fingerprint moves.

### Release E1, the Probe sleeve at 0.50 x E (the captain's A20), on `feat/equity-e1` (merged from `feat/equity-e1-sleeve`, then set to the row the study's review adopted; DEPLOYED 07:18Z Oct 11; an owner deploy with the rest of E1; the money digest E1 deploys is `7e41909a`, one move with the block; no evidence reset)

- **The rule.** `equity_money.probe.sleeve_share` "0.25" -> "0.50" and its bound
  (`EQUITY_MONEY_BOUNDS["probe.sleeve_share"]`) ("0", "0.25") -> ("0", "0.50"), in `league/constitution.py`. Three
  seats and first-come seating are unchanged. A program's position in one ETF is at most half its sleeve, so a
  one-ETF program's lot goes from 0.125 x E to 0.25 x E. No other row moves.
- **Its source.** A pre-registered study (EQDONE-2: its design and decision rule pinned before any code or figure)
  and that study's review, both finished before the first live equity trade and before the result of the options
  lane's next close was known. Done reads the sum of the realized P&L of every agent program's closes since Oct 10,
  both lanes together, so a losing close early in that sum has to be earned back by the lots that follow, and a lot
  of an eighth of E earns too little to do it.
- **Why 0.50 and not the study rule's 0.66.** The pre-registered rule over first-come designs picked 0.66, and the
  sleeve branch carried it (`512c6d84`, merged here). The study's review adopted it with a fallback to 0.50 if
  entries the House refuses or cuts make live trading differ from the replay that Done's consistency clause reads
  (A14). They do: at 0.66 three one-ETF lots meet the invested cap and the cash reserve, so some entries are cut or
  refused live that the Gym, which judges each program alone in its own sleeve, fills. At 0.50 no cross-program cap
  binds for three one-ETF programs. The captain took the fallback.
- **Its cost, plainly.** Against 0.66: a smaller rise in the chance of Done. Against 0.25: about twice the dollar
  swings, losses as much as gains, and twice the spread and fees paid at zero edge. **The larger lot buys variance
  and exposure to the market's direction, not edge and not a higher expected profit.** It was fixed before Monday's
  option result was known and before the first live share trade.
- **What it is: a loosening of ONE row**, decided by the captain (Claude) under goal item 4 and reported with its
  cost, **bounded by the owner's caps and loss budget, none of which moved.** `size_entry` applies each to every entry
  at any sleeve and names the one that binds: an ETF at most 0.50 x E across all programs, at most 1.00 x E invested
  (the options' open maximum loss included), the $50 cash reserve, and the shared loss budget ($400 net in any rolling
  20 sessions, $800 net in total); the kill switch, the daily stop and the drawdown stop stand.
- **The risk, stated** (`docs/operations.md`, under the equity money rules): the lane is long only and cash only;
  the stops do not bound its loss (a tripped stop blocks entries and sells nothing); the $400 window with open risk
  counted at 20%, the $800 total, EDM1 and the program's -$300 line do. The option-sign note: by the study's own
  table, if Monday's option closes at or above zero the smaller lot would have been the better row; one row was
  shipped, and this is its stated price.
- **What follows from it, stated where the old arithmetic stood:**
  - three one-ETF programs hold a lot of 0.25 x E each: 0.75 x E of ETFs, 0.15 x E of open risk, no cap binding. The
    options Probe lane keeps $400 less its realized loss less 0.20 x the equity lots ($400 - 0.15 x E then: $100 at
    E = $2,000, nothing from E = $2,667). Programs that hold several ETFs can fill whole sleeves; three of those ask
    for 1.50 x E, and the invested cap (1.00 x E, 0.20 x E of open risk) bounds the lane then;
  - **a Sized program would size nothing up.** `sized.sleeve_share` (0.50) was left as pre-registered and equals the
    Probe sleeve, and `sized_sleeve_share` is max(the Probe's share, min(quarter Kelly, the cap)): 0.50 x E whatever
    the record. The step is parked (next bullet);
  - against the gateway (read, not changed): one order and one ETF's position of 0.25 x E are under its 50% of
    equity; the lane at 1.00 x E is at its book line on a multiplier of 1, under it by the House's cash reserve; its
    day line (4x equity of buys, a cancelled one too) admits sixteen sends of such a lot a day, where it admitted 32
    of the old lot, so three entries can each climb the collar's whole ladder of five sends, and a sixth send of
    each would meet `stock_day` and end refused.
- **The sizing-up step is parked**: `equity_money.sized.min_trades` 20 -> 1000 (inside its bound, a tightening; the
  captain's decision on the study's review). The owner's loss budget ($400 net in any rolling 20 sessions, $800 net
  in total) covers all real money, and E1 as built leaves a Sized program's closes outside the Probe window, the
  total and the -$300 line; with the Probe sleeve equal to the Sized cap (0.50) the step would size nothing up
  anyway. With 1000 no equity program is Sized, so every equity close stays inside the loss budget's tallies. The
  sizing-up RULE stays pre-registered as written; the row is switched back only together with a change that counts
  Sized closes in the budget.
- Fixed with it: the `dlane` report's `equity.options_probe_room` multiplied the seats by the sleeve (`league/ops/dlane_report.py`),
  which reads more than the invested cap allows once three sleeves pass 1.00 x E. It now takes the lower of the
  sleeves and the invested cap, never reads the lane's open risk above the window, and names what set the figure
  (`bound`: "sleeves", "invested_cap" or "budget"; `invested_share`, `invested_share_of_e` beside it). Its statement
  and the docs carry the arithmetic of the row in force, the three one-ETF lots' 0.15 x E beside the lane's most.
- **Identities.** Money digest `7e41909a` (it was `ad8c761b` on the branch with the sleeve at 0.25 and sizing up
  at 20 closes, never deployed), full digest `e909eb10` (`PINNED_DIGEST`); the stop, `enabled` False, is
  `23f17a14`. The standing grant re-ratifies at the House's start on the owner's deploy, once, with the rest of E1.
  The equity identity does not move. The options execution fingerprint moves with `league/live/money.py`'s two
  corrected comments (`probe_sleeve_share` was annotated "0.25", `sized_min_trades` 20), as it already does once with
  E1. **Rollback of the sleeve**, one owner deploy: `sleeve_share` "0.25" (the bound may stay; the sizing-up step
  stays parked), `PINNED_DIGEST` re-pinned; the digest is then `3a7c52d5` and the grant re-ratifies; lots
  already held are not resized.
- Proof: `league/tests/test_equity_sleeve.py` (three one-ETF lots of 0.25 x E with no cap binding, whether E is the
  grant's capital or the account's own cash; a fourth lot cut by the invested cap less the cash reserve, and the
  next refused by name; two programs in one ETF holding exactly the instrument's 0.50 x E, a third refused by it;
  the budget cutting an entry when its room over 0.20 is the smaller; a Sized program's sleeve never below the
  Probe's). Tests that pinned the old value pin the new: `test_constitution` (the row, the digests, the bound at
  0.50 and refused at 0.51), `test_equity_money` (the table, the grant's re-ratification on the new digest, and on
  the rollback's), `test_equity_bands_money` (the Sized sleeve's arithmetic kept on a table whose Probe sleeve is
  under the cap, and the table in force), `test_ci` (0.51 and the study rule's 0.66 refused by CI; the lot against
  the gateway's files), `test_dlane_report_equity`, `test_equity_e2e` (the real book's lot is a quarter of E),
  `test_live_long_single` (the digest). The park: `test_equity_bands_money` `TheSizingUpStepIsParked` (the rule as
  pre-registered is held on its own 20 closes; at the table in force 999 winning closes are still Probe) and
  `test_equity_fx_daily` `TheSizingUpStepIsParked` (the real book: 999 winning real closes, no band move, every
  close in the Probe tallies and in the shared budget's net figure).

### Release E1, the rehearsal on real data: the data job, the vendor's cents, the seeds' order, on `feat/equity-e1` (DEPLOYED 07:18Z Oct 11; an owner deploy with the rest of E1; the equity identity moves before its first look; no money-digest move)

Before the first deploy, E1's data job, its audit, the store, the three seeds' Train runs and the screen's floor were
run once on the House box against real SIP bars (a temporary copy; nothing live touched; no Validation and no look),
and an independent check read the result. **As written E1 would not have traded: the data job failed its own audit on
real data, so no store was ever written.** Ten defects; every blocker and major is fixed with a test
(`league/tests/test_equity_rehearsal.py`, `league/tests/test_equity_data.py`).

- **The data job's audit reads real bars as they are** (`league/ops/equity_data.py`; blockers). Two checks were wrong
  about real data; these correct them and loosen no evidence. The rules and their reasons only: no count and no
  price read from the vendor's data is written here.
  - *volume*: a flat bar of volume 0 is a session without a trade (the venue carries the last price), and the history
    holds such bars. The check refused them, and history never changes, so every run failed. A flat bar of volume 0
    now passes and is listed; any other missing volume still fails.
  - *the regular session*: the rule ended the session before the closing minute, where the closing cross prints, and
    compared the volume. The daily bar's open is the opening cross (inside the 09:30 minute's range), its close is
    the closing cross (inside the closing minute's range), and its volume counts prints the minute bars leave out,
    so "regular" was unreachable, and a close-set high or low read as "extended", which fails the audit. The
    corrected rule reads the open against the 09:30 minute, the close against the closing minute, the high and low
    between the extreme before the closing minute and the extreme with it, and no volume; "extended" only above 2
    such days of 20. A bar truly built from extended hours still fails.
  - a failed audit's receipt now lists the first five problems of each failed check, every decimal figure masked.
- **The vendor rounds its adjusted prices to the cent**, so the all/raw ratio jitters with no event at all. One bound
  (`league/equity/config.py` `rounding_bound`) serves the two places that read it:
  - *the Gym engine* (major; `league/equity/engine.py` `ratio_tolerance`): with a fixed 2e-5 bound the engine read the
    jitter as dividends (cash credited, one-sided) and as anomalies. With the price-aware tolerance only a step the
    rounding of its two adjusted closes cannot explain is an event.
  - *the split reader* (major; `split_factor`): the rounding pushed a true factor's residual above the fixed bound,
    and the search then took a neighbouring fraction with the rest as a dividend. The factor may now lie its step's
    tolerance above 1.
  - *the book's morning audit* (major; `league/equity/live.py` `_as_of_equal`): on an ex-dividend morning the vendor
    has restated the whole adjusted series, each price rounded to the cent again; compared to a millionth, every such
    morning read as a price mismatch, which cancels the decision's buys and counts a failed decide. With the bound an
    ex-dividend morning reads the same as-of prices, and a close that truly moved is still caught. Raw prices stay
    exact.
  - `engine.py` and `config.py` are evidence modules: **the equity identity moves**, which is free before the first
    look and would retire every looked lineage after it. `EQUITY_EVIDENCE` is unchanged.
- **The volume is no part of a day's audit mark** (`league/equity/live.py`; blocker, with the review's evidence-1):
  the next day's fetch always reads a later volume for a session, and the store's upsert took that for a changed row
  and cleared the day's morning audit, which the twins then report as never audited. Predicted from the code and the
  vendor's documentation, not observed: the first Monday settles it.
- **The seeds' looks go in the declared order, and the order is decided** (major; `league/swarm/seeds.py`,
  `league/swarm/elane.py` `round_order`, `seed_wait`). The two overnight seeds share a template and are one lineage,
  so only one is ever looked at (D3), and which one was left to the store's order. The captain decided it before any
  Validation or look, from Train-era figures only (amendment A18): `seed-overnight-qqq`, `seed-reversal-index`,
  `seed-overnight-spy`. QQQ's overnight seed spends the lineage's one look; SPY's is then refused as the same lineage
  and retired with that reason. A seed's look also waits while a seed declared before it in its lineage has no
  verdict (strict, with no timeout: the verification's fixes above). **Stated cost: SPY's every-close seed is not
  expected to trade; the seeds that can pass buy only after a down close.**
- **Stated, not built** (minors; the captain's decisions): a live decision's ctx does not reproduce byte for byte
  from a later store, because of the same rounding (a program whose condition sits within that rounding of its
  threshold can decide differently in a later replay; A14's intent-agreement reading polices it; as-of prices from
  raw bars and per-event factors are owed before E2). The FOMC, CPI and jobs tables start in 2017 and the CPI and
  jobs tables end in September 2026: `ctx.events` says nothing outside them, the same live and in the Gym, said in
  `league/equity/EQUITY.md`; the tables are extended with verified dates before any event-conditioned program is
  born.
- The review's fixes that met here: the daily fixer's as-of comparison assumed a four-decimal grid (the vendor's grid
  is the cent); the swarm fixer's seed order (SPY first) is replaced by the declared one; the look round's "one
  family's error never stops the others" holds, with the seeds' wait beside it.

### Release E1, the review's fixes on the order path, the book's daily step and the options book's hooks, on `feat/equity-e1` (merged from `feat/equity-e1-fx-orders`, `-fx-daily`, `-fx-hooks`; DEPLOYED 07:18Z Oct 11; an owner deploy with the rest of E1; no money-digest move)

The other 38 of the review's 56 findings, both blockers among them. Each is fixed with a test that failed before
(`league/tests/test_equity_fx_orders.py`, `test_equity_fx_daily.py`, `test_equity_fx_hooks.py`).

- **The cover is exactly the account's short** (blocker; `league/live/step.py` `_close_shares`): an assignment netted
  against a program's fractional lot made the House send a cover larger than the short, which the gateway refuses on
  the real account, so the short would have stood. The cover is the account's short (whole shares first, the fraction
  at the next reading); the lot the short swallowed is never bought back: the equity book closes it as `forced`
  (`EquityBook.shares_taken`) once the cover has filled or a reading finds the short closed outside the House. A
  refused `lv-shares-` order is an error alert at once and hourly, and a refused cover mails the owner. The shared
  test venue now refuses what the gateway refuses, so the rule is held in every live test.
- **The two books' reconciliations no longer race** (`equity_hook.flux`, `RealBook.reconcile(equity_flux=)`): a sale
  filled over two minutes froze the options book ("shares held, 0 expected"). The options book does not judge a
  symbol whose equity order is working or changed in the last two minutes; a settled symbol is judged again.
- **Unexplained shares on a held symbol are never sold** (a split not yet booked): only the part an assignment or
  exercise explains is; the rest is an error alert and reconciliation's freeze.
- **The minute**: an options pass that raises still gives the equity book its minute; the equity minute is skipped
  only when the account reads hung late in the minute; an idle stock proof reads nothing of the practice account;
  stage BUY never waits for the options route's proofs. **A1's invested rule binds option opens too**
  (`money.invested_room`).
- **Owner commands for the equity lane**: `python3 -m league.live --flatten-equity "<why>"` (the rollback's step 3;
  `EquityBook.flatten` had no caller) and `--clear-equity-freeze "<why>"` (`eq_freeze` could never be cleared); the
  equity book reads them each minute and records who and why.
- **The close window keeps A2's order**: close entries wait for the window's exits (60 s at most), and an entry sized
  to nothing waits while an exit may still fill instead of ending refused (a whole-sleeve rotation at the close now
  ends holding the new symbol).
- **One buy intent is one lot**: a fill found by the re-price cancel's lookup no longer leaves the replacement to
  open a second lot.
- **Re-prices go every minute** (they went every second minute at the open), nothing is POSTed at or after a window's
  cut-off by the wall clock, and an order resting at the venue past its own session is cancelled before the next
  open.
- **The gateway's unread readings** (424 positions, 424 orders, 503 equity, 409 stock_close) are sent again next
  minute; they no longer end an entry or carry an exit to the next session.
- **One unreadable read of the swarm store retires nobody** (`bands.read(strict=True)`, `EquityFamilies.standing`):
  a single failed read at the daily sync retired every instance for good and sold its lots. Retirement is on the
  store's own word only, every retirement is an alert, and a wrongly retired instance runs again.
- **The seating pass**: a program that passes its look after the day's decision is seated and decided for the same
  close, so a Sunday look buys at Monday's 15:55 ET close (it was Tuesday's).
- **An instance is asked once a session and its failed decide counted once; a program's own failed decide counts**
  toward the two-failed-decides exit as in the Gym (`league/equity/child.py` answers `failed`: an evidence module,
  the equity identity moves). A House exit due at the open replaces the program's close sale of that lot.
- **The day's bars and the morning audit**: the bars of held lots are read with no live program; the audit cancels
  buys on a price mismatch only, notes a volume difference and marks each symbol on its own verdict; the sizing-up
  rule's buy-and-hold is priced on one adjustment basis.

### Release E1, the review's fixes on the swarm, evidence, ops and docs side, on `feat/equity-e1` (merged from `feat/equity-e1-fx-swarm`; DEPLOYED 07:18Z Oct 11; an owner deploy with the rest of E1; the equity identity moves before its first look; no money-digest move)

The adversarial review of `feat/equity-e1` (five reviewers, Oct 10) found 56 defects; these are the 18 on the swarm,
evidence, ops and docs side (the order path's, the daily step's and the live hooks' are the entry above).

- **The equity rounds run on their own** (`league/swarm/loop.py` `equity_rounds`, every `elane.ROUND_SECONDS`, 300 s).
  The equity Validation ran only inside the hourly tournament after the options Validation, and the look only inside
  the options gate round, both started only while the research guard allows and the options Gym is ready. A3 says an
  equity run needs no Gym box, yet under the brake, with the Gym down or after an options Validation that raised, the
  seeds were born and never judged. The two equity steps now run on one thread of their own (Validation, then the
  look, so a version validated in a round is looked at in the same round), outside the branch that holds the options
  rounds; `Tournament.run` and `Gate.run` no longer call them. The heartbeat carries `status.equity`.
- **The seeds' looks follow the seed list** (`elane.round_order`): they ran in (born second, id) order, so in the ids'
  alphabet (QQQ's overnight seed before SPY's) or by a clock tick, and under D3 the later of two seeds of one lineage
  is refused with no look. Now the seed list's own order (which order the list declares was decided after the
  rehearsal: QQQ's overnight seed, the index reversal, then SPY's; the entry above). A version refused at the gate
  before its look retires for what happened (`elane.SAME_LINEAGE`, `FLOOR_INELIGIBLE`), no longer as "used its one
  Validation try".
- **A look's lineage record survives an equity identity adoption**: `adopt_equity` cleared `elane_train_r`, the Train
  series D3's correlation test reads, for families already looked at, so after any identity move a re-coded copy of a
  looked-at program got its own sealed look. The series now stays with the look; `same_lineage` fails closed (a
  looked-at program with no series has it written again from its looked version's Train-era runs, else the look waits).
- **The look reads each run's status**: a holdout run its own errors ended ("disqualified") was judged on its partial
  series and could pass. It is now a look spent and failed; a Train-era run that ended so refuses the floor; a span
  with no data is no history, the screen's own rule.
- **A sealed run is sent at most twice** (`elane.LOOK_SENDS`; `league/equity/runner.py` `RunLost`): a look whose run
  did not return was owed again without limit. One the child took whole and did not answer (it ran past its budget
  or exited) is owed once, then the look is spent and failed, with a House warning each time; every other failure (the
  store, a child that could not start or did not take the request, an answer that is not a result) is the House's and
  counts against nobody. **The
  evidence child's hash seed is pinned** (`Decider.hash_seed`, 0 for the swarm's equity child, as the options Gym's
  PYTHONHASHSEED=0): a program that iterates a set of strings no longer differs from one start of the child to the next.
- **A tried version whose verdict went stale is validated again** (`elane.next_try`), whichever version the family's
  candidate is by then: a validated v1 with a later v2 after an adoption, and R3's retry after the store's daily write,
  waited for good. R3's retry hash is recorded once, at the lineage's first try, and kept (None included).
- **The calendar is in the equity identity** (`evaluator.EQUITY_CALENDAR_FILES`: `ltcm/__init__.py`,
  `ltcm/broker.py`, `ltcm/data/__init__.py`): the NYSE calendar the store and the ctx read was in the evidence's import
  closure and not hashed. A CI test holds the list to what the evidence imports outside league/. **From E1 on a byte
  changed in one of those three moves the equity identity.**
- **The Gym's first decision reads its whole window** (`league/equity/store.py` `_slice`: `history` + 1 sessions
  before the run's first): it read one row fewer than a live decision, so a program reading its oldest row raised
  there in the Gym and ran live.
- **The seeds say where they came from**: the source and each program's header said "Written before any data was
  seen", untrue for seed-reversal-index, whose theta and h are the cell a pre-registered census selected on earlier
  history. The overnight seeds are "written from a published prior"; the reversal seed says how its parameters were
  chosen and that no 2020, 2021, 2025 or 2026 session was used. No figure.
- **The Done meter beside equity closes** (`league/ops/dlane_report.py`): item 4 of a reading that holds an equity
  close is read by A14 (`a14_consistency`), never by the options replay gap, whose 0.10 of the maximum loss is a
  thousand basis points of a long lot. The fill-gap half is computed (a mean past 15 bp a side fails it); the
  intents-agreement half has no reader yet, so item 4 of such a reading is not read and **no Done is declared on equity
  closes until it lands**. P(Done | zero edge) says it is the options rules' figure only when an equity close is
  counted. The screen's row beside a trade carries S1-X's label as `s1x` and the lane's as `lane_label` (one `label`
  read the lane's where S1-X's was meant). The funnel's equity Validation counts read the verdicts' own events (they
  read the hourly tournament row, which never held an equity family: always zero).
- Recorded for E2's review, never a condition of the look: each look keeps the share of sessions its program was
  invested on in Validation and on each Train-era span (`elane._invested_shares`). The screen's floor is the program's
  own Train-era behaviour, so a program sparser there lowers its own threshold (never below the receipt's floor); the
  rule that would refuse on it needs a pre-registered factor and is not written.
- Docs: `docs/operations.md` "The equity lane": the rounds, the order of the looks, what a look does with a run that
  went wrong, the sizing-up rule and EDM1 as pre-registered (sigma's order and the sleeve floor included), the equity
  freeze and the owner's two commands, the morning audit's real consequences, the Sunday-to-Monday timeline, the
  client ids.
- Proof: `league/tests/test_equity_fx_swarm.py` (46 tests, each naming its finding; 44 fail on `feat/equity-e1` as it
  was, and two are guards that hold on both).
  Existing tests changed where they held the defect: `test_equity_identity` (the adoption cleared the series; the
  fingerprint's file list), `test_equity_store` and `test_equity_runner` (the slice's `first`), `test_dlane_report_equity`
  (the funnel's fixture, A14's status words, the row's `label`).

### Release E1, ready for review: S2 is the gate, the equity identity covers evidence only, the Done text pre-registered, on `feat/equity-e1` (DEPLOYED 07:18Z Oct 11; an owner deploy with the rest of E1; no further money-digest move)

- **S2 is the House's share screen** (the captain's A11). Both lanes' blocks of policy.json pin receipt 2
  (`docs/benchmarks/equity_screen_2.json`, the study's receipt copied verbatim, sha256 `45634dfc...`), and every look
  runs S2's code (`league/equity/screen.py` `floor_s2`, `verdict_s2`, merged from `feat/equity-e1-s2`). The gate:
  Validation's pre-check, then the one sealed look passes when the holdout's P&L is above zero and its holdout-only
  daily t is at least c_H,used = max(the c_H floor 0.95, the program's own exact floor c_pF1 + the margin 0.05). **c_R
  is 0**: the pooled t is reported, never a bar. The look cap is 2026-10-09 (A12: the 194 calibrated sessions).
  Measured (the receipt): the false-positive rate at zero edge is at most 7.51% over the 336 measured cells, none above
  the 12% cap. **The stated cost: more zero-edge programs pass than under S1+F1** (1.3 to 7.3 times as many on the
  study's worlds), so a pass is weaker evidence of edge; the live record and EDM1 carry that. S1+F1 stays in code and
  in the repository as receipt 1's screen; no lane pins it.
- Fixed with it (`league/swarm/elane.py` `look`): the look ran S1's floor whatever the receipt, which S2's verdict
  refuses AFTER the look, so the first S2 look would have been spent on a certain failure. The floor is now the pinned
  receipt's (`screen.floor(segments, receipt=)`), kept for a version only while `screen.floor_fits` it, and a floor
  that does not fit spends no look. The look and its events record the screen that judged them ("S2": c_H,used and
  c_pF1), an S1 floor of the same Train-era series fills S1-X's rate beside the S2 line, and the Done report's row
  beside an equity trade names that screen.
- The receipt's bytes at the look: where the pinned screen's receipt file is at hand, `elane._receipt` reads it under
  the pinned sha256 and compares its figures with the block's; a mismatch refuses the screen (the look waits, nothing
  is spent). `docs/benchmarks/` never reaches the House box, where CI's pin of the exact commit stands for it.
- A12 at the look: it waits while the daily store ends before 2026-10-09 (`elane._holdout_gap`): a shorter holdout
  fails the verdict's windows and would have spent the lineage's one look.
- **The equity identity covers the evidence modules only** (A13): `evaluator.equity_fingerprint` hashes
  `EQUITY_EVIDENCE` (league/equity's `__init__`, `config`, `store`, `program`, `ctx`, `engine`, `results`, `runner`,
  `synth`, `sizing`, `screen`, `child`), the four shared league files and the Gym modules they import (and, since the
  review's fixes above, the calendar's three `ltcm` files). The plumbing
  (`live`, `actions`, `schedule`, `families`, `bands`, `kinds`) is out, so a plumbing fix no longer sends every live
  equity band back to the Gym; the I6 ctx test and the twins police that live and Gym agree. A CI test holds the list
  to the import closure of the runner, the child, the screen and the engine (plus `synth`). **The panel kind's slot**:
  `kinds.KINDS["panel"]` = `league.xs.child`, the child's runtime carries `league/xs/`, and `league/xs/child.py`
  refuses every op until the cross-sectional lane is built there.
- **Pre-registered before the first equity close** (A14; text first, its fill-gap half read since the review's fixes
  above; `docs/operations.md` and every `dlane` report's `done.preregistered`): Done's "live fills consistent with
  their replay" is the mean fill gap against the
  official-price model at most 15 bp a side AND live and shadow intents agreeing on at least 95% of the counted
  sessions, read at each Done checkpoint; Done is reported beside the number of distinct close dates and a
  date-clustered t; the forward seat rule is written and inactive (an incumbent with fewer than 5 real closes is never
  unseated, except by EDM1). The Done rule itself is unchanged.
- Protected: `league/ci.py` `PENDING_GATEWAY` gains `league/xs/` and `ltcm/broker.py`, so every file of the decider
  child's sealed runtime is behind the updater's wall (`test_ci` holds `decider.runtime_files()` to it).
- STILL OPEN, a gateway follow-up (gateway/ is read only in E1): `MERGE_FORBIDDEN` lacks `league/equity/`,
  `league/swarm/elane.py`, `league/xs/` and `ltcm/broker.py`, and `gateway/test/merge.test.mjs` still reads the
  decider's old in-function runtime tuple and finds league/live importing an unprotected `league/equity/`, so the
  gateway CI job fails on this branch until that follow-up lands with it.
- Proof: `test_equity_screen` (S2's conformance vectors, brute force, routing; the vectors at the committed receipt's
  floor and margin), `test_elane` (the pin is receipt 2's bytes and figures, both lanes; a receipt file that is not
  the pin's refuses), `test_elane_gate` (the floor by the receipt and its fit, an S2 look's record, the store's last
  day), `test_equity_e2e` (a seeded program passes its look under the committed receipt 2), `test_equity_identity`,
  `test_equity_isolation`, `test_equity_decider` (A13), `test_dlane_report_equity` (A14, an S2 row), `test_ci`.

### Release E1, the equity lane: ops, data, twins and the Done meter, on `feat/equity-e1` (DEPLOYED 07:18Z Oct 11; an owner deploy with the rest of E1)

- **The data job** `equity_data` (`league/ops/equity_data.py`, registered at the House's start and daily 22:30Z, in a
  pause too): Alpaca SIP daily bars of the equity universe through the gateway's bars route, adjustment=raw and
  adjustment=all, from 2016-01-04 to the last closed session, audited (the NYSE calendar with no gap, sane bars, every
  raw/all ratio jump a split the raw close shows, volumes, and the design's fact 1: the 1Day bar against SPY's 1Min bars on
  20 sessions, "regular", "extended" (a stop) or "unverified" (written, warned)), then written atomically through
  `league.equity.store.write_store` to `<state>/equity-daily/` with the GATE mark. A failed fetch or audit writes
  nothing. The data never leaves the House.
- **The equity twins** (`league/ops/twins.py` `equity_twin`, the `equity_twins` job at the start, 01:15Z and 40 minutes
  before each open): each closed equity lot's twin in closed form from the House's own official opens and closes
  (`eq_bars`) with the engine's fill function (open and close fills, A2), the same fees, dividends and split; "priced",
  "no_bar" or "unpriceable", final once judged; the gap in bp a side, each fill's slippage against its official price
  and the same-risk buy-and-hold, in the swarm store's kv `equity_twins`.
- **The Done meter** (`league/ops/dlane_report.py`): counted from Oct 10, 2026 as the goal says (`DONE_FROM`, 00:00 New
  York; every earlier agent close reported beside in `done.earlier`, never counted; a frozen reading is carried only from
  a report that counted from the same instant); the rule itself unchanged. An equity close is one EquityBook lot fully
  closed with its net cash (fees and dividends), on `:r`, matched to its own twin (no nightly fallback: no twin is a
  replay not landed); beside every close and checkpoint its lane's label (MARKET BETA or EQUITY), the buy-and-hold, MTE,
  the screen's line recorded at the look (S2's, above) and "profit from market direction"; Done also read without the three seeded
  programs (`done.without_seeded`, A8.12); the equity trades' screen lines in `fp_beside_trades.equity_trades`; the
  `equity` section with A8.6's statement that the options Probe lane is effectively off while the equity sleeves are
  full. The funnel counts the equity lanes apart (`league/ops/funnel.py` `equity`; the daily page's table is unchanged).
- **The rollback guard** (A8.9, `scripts/floor_box.py`): `deploy` and `rollback` refuse a release without the EquityBook
  while the box's `live.sqlite` holds an equity lot or works an equity order (`EQUITY_BOOK_MARKERS`,
  `EQUITY_GUARD_SNIPPET`, read-only); `--force-equity-risk` is the emergency path.
- Docs: `docs/operations.md` "The equity lane" (the switches, the cash-only choice and the house-wide cash rule, the
  shared budget's consequence, the schedule, the stock paper proof, the flatten-first rollback, and the gateway's stock
  route as the House sees it). Proof: `test_equity_data`, `test_equity_twins`, `test_dlane_report_equity`,
  `test_floor_box_equity`; `test_dlane_report`'s fixtures now count from the rule's inception explicitly.

### Release E1 integrated: the seven packages agree, receipt 1 pinned (since replaced by receipt 2: S2, above), the staged stock proof, the switch on, on `feat/equity-e1` (DEPLOYED 07:18Z Oct 11; an owner deploy; the options execution fingerprint moves once, the money digest moves, a new equity identity)

- The integration of the seven E1 packages (core, money, screen, book, hooks, swarm, ops) and `origin/main`. What the
  packages had built against each other's stubs now meets: `league/tests/test_equity_e2e.py` runs a seeded program from
  its birth through Validation (the decider's "equity" kind), the look under the pinned receipt, the band decision,
  a live session (the 16:30 decide, Monday's 15:55 close-window buy sized by `size_entry` on the House-wide cash and the
  shared budget, Tuesday's open sale), the morning audits, the twin and the Done meter, against a fake venue.
- Fixed where they met: the decider child's sealed runtime lacked the engine's NYSE calendar (`ltcm/data`), so every
  Validation run and look would have failed in the root House's child (`league/equity/kinds.py` `RUNTIME`); the child's
  load answer now carries the program's merged PARAMS, which the live ctx needs to equal the Gym's (I6: the seeds read
  `ctx.params` and would have failed every live decide); the book read `decider.kind_load`'s answer as refused (it
  carries no "ok": a refusal raises), so no live program would have loaded; none of the book's `equity.*` ledger kinds
  was registered (league/ledger.py `KINDS`: the ledger refused them and the book swallowed it); the stock proof started
  only once the options route's paper proofs had passed (removed by the review: stage BUY goes in the first open
  window and never waits for the options route's proofs, A10.1);
  `league/runner.py` gives back the SIGALRM handler it takes (it left its own in place, so the Gym runtime's timeout
  raised the wrong exception after it in one process); the maximum hold is one rule (`config.max_hold_due`: a lot is
  held at most `max_hold_sessions`; the engine and the book disagreed by a session) and seed-reversal-index exits at
  the open h sessions after its entry; a day's bars fetched again keep their morning audit while unchanged (the twins
  need both days audited); the book posts the broker's REG and TAF fees to closed lots (`info.fee_basis`), which the Done
  meter's finality waits for.
- The captain's amendments applied at integration: A9, the study's receipt copied verbatim to
  `docs/benchmarks/equity_screen_1.json` (sha256 `6fb84bd5...`) and pinned in policy.json for both lanes (receipt 1,
  the S1+F1 screen: no lane pins it any more, A11 above; the file and its code stay); A10.1, the
  stock paper proof staged in the equity book's OPEN window (`paper_proof_stock_buy` gates real buys,
  `paper_proof_stock_sell` real sales, the practice sale first, a failed SELL stage alarms and stops new buys);
  A10.2, `equity_money.enabled` ships True (money digest `fdf2ac7c` -> `7e41909a`, full digest -> `e909eb10`; the stop,
  `enabled` False, is `23f17a14`: the figures since the Probe sleeve moved to 0.50 and the sizing-up step was parked,
  A20, at the top of this section; with the sleeve at 0.25 and sizing up at 20 closes they were `ad8c761b`,
  `65b0e025` and `ea97607c`); A8.1, the calibration's reservation reads the House-wide cash rule
  (`RealBook.free_to_reserve`); A8.12, the options learning game never arms an equity family and its population
  ceiling counts the options lanes, and an equity look never counts in an options lane's leakage alarm.
- Also applied: A12, `config.LOOK_CAP` 2026-10-09 (every look reads the 194 calibrated holdout sessions); A16,
  `evaluator.adopt_equity` marks a family's recorded equity Validation verdicts stale, so a family validated but not yet
  looked at is validated again under a new equity identity instead of waiting forever (no try or look spent).
- Landed since (the section above): the S2 screen with its receipt's copy and pin (A11), the equity identity over the
  evidence modules only with the panel kind's slot (A13), and the Done consistency text (A14). Still open: the
  gateway's `MERGE_FORBIDDEN` follow-up (above).

### 22:20Z Oct 10, 2026: the stock path's races (#534), gateway `95e7a8d0`, main `3177bb14`

Gateway deploy only (455/455; rollback `e3f310ee`); the House unchanged.

### A stock buy's fill between reads is never lost, a lagging sale is never sold twice, and a definite answer lets a hold go, on `fix/gateway-stock-read-order` (DEPLOYED 22:20Z Oct 10, gateway `95e7a8d0`; a gateway deploy; no House change)

- The design review of Oct 10, 2026: `realStockBuy` read the account, then the open orders, then the positions, so a buy
  that filled between the first two reads was counted nowhere, and the Gate's ledger let an answered buy go after 5 s
  though the venue's account and positions can lag an order's status longer. Now the open orders are read first, then
  the positions, then the account (a fill in between counts twice, never not at all; every read still fails closed), and
  the Gate holds each admitted buy `STOCK_LEDGER_HOLD_MS` (60 s) after its answer (unanswered, two minutes from
  admission), netted against the open order that lists it by `client_order_id`, so it counts once, the larger of the two.
  Docs: `gateway/README.md`, `docs/operations.md`. Proof: `gateway/test/stock-buys.test.mjs` (449 of 449 in the gateway).
- The same review's close-lag risk: the Gate let a stock close go 5 s after its answer, so a filled sale the venue's
  positions did not show yet left its shares free to sell again: a short sale. A close now reads the open orders, then the
  positions (free to take: the lower of `qty_available` and the position less the open orders on its side,
  `caps.closeAvailable`; `424 orders` when they cannot be read), and is held `STOCK_LEDGER_HOLD_MS` after its answer (two
  minutes with none). From the oldest close held, the closes since count as the larger of what they ask and how far what
  is free has fallen since it was admitted, so a close the venue shows counts once and one it does not still counts; past
  what is left is `409 stock_close`. Covers have the mirror rule. Proof: `gateway/test/stock-buys.test.mjs`,
  `gateway/test/router.test.mjs` (453 of 453 in the gateway).
- So the House's cancel-then-resend still works (it re-prices every 30 s in the close window), a held buy or close is let
  go early on a definite answer: a submit refused with a 4xx other than 408 counts nothing from then, and each check reads
  by `client_order_id` (`GET v2/orders:by_client_order_id`, read-only, at most 10) the held orders the open orders do not
  list; one `canceled`, `expired` or `rejected` counts only what it filled, learned once. A failed read, a 5xx, a 408 or
  no answer keeps the whole hold; `filled` keeps it as before. The Durable Object gains `stockAsk` (read-only). Proof:
  `gateway/test/stock-buys.test.mjs` (455 of 455 in the gateway).

### 21:42Z Oct 10, 2026: the no-captain automations (#533), House `20261010T214125Z-d4667186f969`, main `ac6d008b`; gateway `e3f310ee`

Gateway first (`e3f310ee`, 446/446; rollback `3cc811b0`), then the owner deploy: no order in flight at 21:41:13Z;
promoted 21:42:18Z (rollback `main-380b280c0c65`, the updater's release of main `a927b4f1` with #531), nightly back
21:52:54Z, updater repointed. Verified 21:53:50Z: health clean, real money on, execution fingerprint `31a7e921`,
constitution `0adb4f0e`, money `fdf2ac7c`, gate contract `397b22b772b3` unchanged; `budget_refresh` ran at the start;
the `stall` receipt carries `birth_yield`, `swarm_alerts` and `underspend`.

### 21:18Z Oct 10, 2026: real stock and ETF buys at the gateway (#532), gateway `3cc811b0`, main `a48623e7`

Gateway deploy only (446/446; rollback `507b6118`); the House unchanged and verified (health clean, ids unchanged).
`STOCK_BUYS_REAL` is on; no House code sends a stock buy until the equity lane's release and its constitution switch.

### The always-in card's ablation (#531) reached the House through the updater

The updater deployed main `a927b4f1` as `main-380b280c0c65` about 20:05Z Oct 10 (#531 changes `league/swarm/cards.py`
only); the grant re-ratified on money `fdf2ac7c` at 20:05:31Z.

### Real stock and ETF buys at the gateway, on `feat/gateway-stock-opens` (DEPLOYED 21:18Z Oct 10; a gateway deploy; no House change)

- The owner's goal of Oct 10, 2026 (ETFs, stocks and options with real money). While `STOCK_BUYS_REAL` is `on` (set so
  in `gateway/wrangler.jsonc`), the real account admits a LONG-ONLY buy of `STOCK_UNIVERSE` (17 ETFs: SPY QQQ IWM DIA,
  the eleven SPDR sectors, TLT GLD; 18 large US stocks): a `limit` `day` order sized in shares (fractional allowed, no
  `notional`), metered at `qty x limit_price`. Caps, judged in the Gate against a fresh reading of the account, its open
  orders and its positions made by the gateway itself: the order and the symbol's position (held + resting buys + buys
  in flight) at most 50% of equity for an ETF and 20% for a stock (`stock_order`, `stock_position`); every long position
  (options included) + resting stock buys + buys in flight + this order at most equity x min(2, the account's
  multiplier) (`stock_total`); never above buying power (`buying_power`). The shares and the multiple are ceilings in
  code (`STOCK_ETF_EQUITY_SHARE`, `STOCK_SINGLE_EQUITY_SHARE`, `STOCK_MAX_EQUITY_MULTIPLE` can only lower them). Every
  read fails closed (`503 equity`, `424 orders`, `424 positions`); a buy is an open for the day's order counts and the
  kill switch stops it; it never spends the options' opening maximum loss. Sales stay closes of shares held long and a
  buy of a symbol held short stays a cover, at most the short: no short sale. The practice account is unchanged.
  `/v1/health` gains `stock_buys`. No House code sends a real stock buy yet. Docs: `docs/operations.md` (top section and
  **Switches**), `gateway/README.md`. Proof: `gateway/test/stock-buys.test.mjs` (24 tests; 437 of 437 in the gateway).
- The branch's review, fixed on the branch: (1) MAJOR: every real stock order reads the positions fresh, never the
  per-isolate cache (from it a "cover" of a short already gone went past every stock cap, and a sale of shares already
  sold was a short sale), and the Gate serializes stock closes in the buys' in-flight ledger (`reserveStockClose`): a
  second close of the same shares is `409 stock_close`. (2) MAJOR: the book cap is a margin line, long options counted at
  the margin multiple (Reg T overnight: `stocks / m + options <= equity`), and buying power is the lower of
  `buying_power` and `regt_buying_power` (a margin account without the latter is `503 equity`): on pattern-day-trader
  margin the old gross cap and intraday buying power admitted a book past the overnight 2x. (3) A day cap on stock buys,
  `STOCK_DAY_EQUITY_MULTIPLE` (a ceiling of 4x equity, `403 stock_day`), a gateway backstop under the House's stops.
  (4) The House sells every stock position at market (`league/live/step.py` `_close_shares`): the House release that
  first sends a buy must limit that to assignment and exercise shares (`docs/operations.md`). (5) Tests for buys in
  flight against the book and buying power, the admit side of every boundary, one micro-dollar over, and `"0"` end to
  end. 446 of 446 in the gateway.

### The no-captain automations, on `feat/no-captain` (DEPLOYED 21:42Z Oct 10; a gateway deploy, then an owner deploy; no evidence reset)

From the audit of every hand intervention from Oct 7 15:44Z to Oct 10 19:40Z (59 in about 76 hours), the four that
recur without a captain and cost DONE-RULE item 7 ("research runs 24/7 at budget with no captain") the most:

- `league/ops/budget.py`: THE TOP-UP RAISE. A later run of the day whose reading would set more than the day's figure
  raises it (raise-only, never above the ceiling, from the reading as it stands; `raised_from`, `raised_at`), so a
  top-up no longer waits for the next 00:30Z run, and the run after the close no longer puts a stale figure back.
  `refresh` and the new job `budget_refresh` (`league/ops/budget_refresh.py`, `league/ops/registry.py`: hourly at :35
  and at each House start) write `budget.json` only to raise a meter or set a day's first figure; with no usable file
  (none, another rule's, stale) it runs the full job, so a deploy that changes the rule is read at once.
- `league/ops/stall.py`: the births JAM (no birth for 6 h while 4 passes wanted births) is the owner's step at once,
  naming the main way the passes bore nothing and its lever; the new `birth_yield` cause (INFO) reads the architect's
  yield over 3 h (born at most 1 of 4 asking passes, or 80% of proposals refused by the card checks, or 2 dry hours) with
  the refusals by kind, the incomplete cards' top fields and the rebirth rows; `swarm_alerts` mails the swarm's own
  alerts (owner steps for `reader_cut`, `agenda_guard`, `gate_coverage` and the other setting-or-fix kinds); `underspend`
  (INFO) reads each meter's booked research against what its day's figure buys by now and names the settings that bind
  research (`settings_binds`: caps under the budget's knobs, the class cap under the direction lane's `max_alive`, an
  architect Claude line under one call's hold, values under the code's defaults).
- `gateway/lib/email.mjs`: the words for `birth_yield`, `swarm_alerts` and `underspend` (deploy the gateway first: an
  unknown cause makes the stall notice a 400).
- The review of the build: a raise is never bought by a fallback reading (the day's figure keeps the fixed cost and
  reserve it was set on, `fixed_usd_day`, `reserve_usd`, and every raise, `set_usd_day`, `raises`, which `underspend`
  prices hour by hour); `swarm_alerts` reads each owner kind's condition from the swarm's settings and store
  (`alert_states`: a fix clears it at the next run, an unfixed one-shot alert stands past its 12 hours, an alert from
  before midnight fails no next day); the jam is the owner's step only for kinds a setting or an agenda clears (failed
  calls heal by themselves); `underspend` paces Sail only, stands on a conflict only while it binds (the release's own
  class-cap pair once a direction card meets it) and names drift against the release's `policy.json`, not the code's
  defaults; a new stall cause needing nothing is mailed at once (`stall.json` `mail.told`; the gateway keys such a
  notice `stall:info:<causes>`, `gateway/lib/email.mjs` and `gateway/lib/gate.mjs`).
- Tests: `league/tests/test_ops_budget.py` (the raise, the fallback that raises nothing, the refresh end to end, its
  registration), `league/tests/test_ops_stall.py` (`NoCaptain`: each cause reproduces an Oct 9-10 intervention; the
  alert before midnight, the one-shot alerts, the jam of failed calls, the brake, the real settings read;
  `Telling`: a new cause mailed at once), `league/tests/test_ops_int_ops.py` (the job runs in a pause),
  `gateway/test/stall-notice.test.mjs` (the key on the causes).

### An always-in card's ablation is dropped, on `fix/always-in-ablation` (DEPLOYED by the updater about 20:05Z Oct 10; no evidence reset)

- `league/swarm/cards.py` `validate`: the architect's card template asks every card for an `ablation` switch, so its
  always-in cards (declared inputs exactly `["clock"]`) arrived with one and were refused ("has no gate to switch off").
  Such a card's ablation is now stored as the default (the same card and sha as one that declared none);
  `dlane.card_errors` itself still refuses one. G1 on Train still holds the program to the clock alone.

### 18:00Z Oct 10, 2026: the always-in direction card v2 (#529), House `20261010T180000Z-1db67896f607`, main `92518185`

Owner deploy (no gateway change): no order in flight at 17:59:54Z; promoted (rollback `20261010T062000Z-1767910d2115`),
nightly back 18:11:06Z, updater repointed. Verified: health clean, real money on, execution fingerprint `31a7e921`, money
`fdf2ac7c`, constitution `0adb4f0e` unchanged; the grant holds. Agenda v21.5 in `swarm.json` at 18:11:07Z (an always-in
card lists inputs `["clock"]`, says "always-in, no gate", and has no ablation). #528, its first cut, was closed unshipped
after its review.

### The always-in card, on `fix/always-in-v2` (DEPLOYED 18:00Z Oct 10; no evidence reset)

- A direction card whose declared inputs are exactly `["clock"]` is always-in: its card says "always-in" or "no gate"
  and has no ablation; it is bound only by the always-in direction rows on its roots (`cards.RebirthIndex.check`'s
  direction path; alpha cards, legacy rows and gated direction cards as on main); its birth joins every always-in
  lineage on its roots and no gated one (one Validation try a root, claimed by a living member); it trades only the
  roots it was born on and never forks; and it is checked on Train (G1: entries on 90% of its flat sessions, or of all
  of them for a ladder, its risk within 3x and its hold within 2x of their medians, or its version due for Validation
  is never validated and it retires, after the ration). The architect's prompt, BIRTH CELLS and closed-pass check say
  it. A LOOSENED row in the `dlane` report states the cost. Docs: `docs/operations.md`. Proof: `test_dlane_always_in`.

### 06:20Z Oct 10, 2026: the spent-lineage refusal (#526), House `20261010T062000Z-1767910d2115`, main `dd196cad`

Owner deploy (no gateway change) after the 06:00Z nightly: no order in flight at 06:19:51Z; promoted (rollback
`20261010T053556Z-6803e7940d24`), nightly back 06:31:04Z, updater repointed. Verified on the box: health clean, real money
on, execution fingerprint `31a7e921`, money `fdf2ac7c` and constitution `0adb4f0e` unchanged from the release below.

### 05:36Z Oct 10, 2026: the Probe total at $800 and the program line at -$300 (#525), House `20261010T053556Z-6803e7940d24`, main `d93a091e`

Owner deploy (no gateway change): no order in flight at 05:35:44Z; promoted 05:36:40Z (rollback
`20261010T033512Z-df7078e102a6`), nightly back 05:46:55Z, updater repointed. Verified: money digest `0310779c` ->
`fdf2ac7c`, constitution `ca89ff8a` -> `0adb4f0e`, execution fingerprint `31a7e921` unchanged (no evidence reset), and
the standing grant RATIFIED on `fdf2ac7c` at 05:37:13Z. The entries below describe both; they are now live.

### The Probe total at $800 and the program line at -$300, on `feat/probe-total-800` (DEPLOYED 05:36Z Oct 10; money digest `0310779c` -> `fdf2ac7c`; no evidence reset)

- **Why** (PREREG-T, Claude's decision pre-registered privately on Oct 10, 2026 under the Probe roster R5 already live;
  the owner's goal as re-set on Oct 9, item 4: "Probe loss budget: $400 net in any rolling 20 sessions and $800 net in
  total"): the measured gain in Done at the owner's ceiling. The operator's simulation (three paired arms; cross-fit,
  fixed 2-, 3- and 5-session holds standing in for the House's pool, roster 5, arrivals; index beta minus option costs,
  not alpha): P(Done) at 12 weeks 4.6% -> 5.5% (paired +0.92 points, SE 0.15), at 24 weeks 11.6% -> 14.4%; P(Done |
  zero edge) 2.2% -> 2.7% at 12 weeks, 6.9% -> 9.0% at 24.
- **The rule:** `options_money.probe.loss_total_usd` "400" -> "800", the owner's ceiling (`league/constitution.py`);
  `dlane.program_loss_usd` -200 -> -300 and `dlane.done_zero_edge_p` 0.024 -> 0.027 (`league/swarm/policy.json` and
  `league/swarm/dlane.py` `DEFAULTS`; the line's bound in `dlane.cfg` is its default, -300 to -25, tighten only;
  `dlane.ZERO_EDGES` labels 0.024 and 0.027, `dlane.ZERO_EDGE` is 0.027). Unchanged: the rolling $400 in any 20
  sessions, the 10% cap, `open_per_family` 3, `max_open` 8, DM1, the kill switch, the daily stop and the drawdown stop;
  open Probe risk stays at or under $400.
- **Cost** (two loosenings, each a row in the `dlane` report's `LOOSENED` header): P(the agents' running real net, the
  Probe/Sized route and the incubator together, below -$400 within 12 weeks) 17.8% -> 36.8%, below -$600 0.6% -> 4.4%;
  the 12-week net's 5th percentile -$396 -> -$679; P(the 60% drawdown stop trips by 24 weeks) 21% -> 48%; mean 12-week
  net +$22 -> +$25, median -$327 -> -$231. Most of it is the total's; the line's own step over the $800 total alone:
  35.8% -> 36.8%, 4.1% -> 4.4%, 46% -> 48%, zero-edge Done 2.5% -> 2.7%, for P(Done) 5.3% -> 5.5% (+0.24 points, SE
  0.12: 2.06 paired SE, just past PREREG-T's 2). One program may spend $100 more of the shared total before it is
  retired.
- **Roster 5 only:** the pair was measured at `dlane.roster` 5 alone (at no roster the operator's grid found the $800
  total almost all cost). The roster moves by `swarm.json` with no deploy, so a roster rollback or another count needs
  the pair's rollback too, or a new measurement first; the `dlane` report's new PT1 warns while they run apart
  (`dlane_report.pt1_alarms`).
- **The report:** P(Done | zero edge) keeps both figures labelled: 0.027 with PREREG-T's horizon, holds and source,
  0.024 with A1.2's, and any other figure is "not one this code names" (it no longer calls 0.027 A1.2's pin).
- **Identities:** money digest `0310779c` -> `fdf2ac7c`; constitution digest `ca89ff8a` -> `0adb4f0e`; the execution
  fingerprint (`31a7e921`), the Gym bundle and the gate contract (`397b22b772b3`) unchanged (nothing in `league/live/`
  or `league/gym/`). The standing grant re-ratifies on `fdf2ac7c` at the House's start on the owner's deploy (the
  updater alone never does); no real entry until it has. Known stale: `league/live/money.py`'s docstring still says
  "$400 as set on Oct 9" for `probe.loss_total_usd` (the code reads the constitution); its words wait for the next
  `league/live` release, since editing them alone would move the fingerprint.
- **Rollback** (one owner deploy): `loss_total_usd` "400" (`PINNED_DIGEST` back to `ca89ff8a`);
  `dlane.program_loss_usd` -200 and `dlane.done_zero_edge_p` 0.024 in `policy.json` and in `dlane.py` `DEFAULTS` (the
  bound follows); `ZERO_EDGE = ZERO_EDGES[0.024]`; the tests that pin the $800 rules with them. The money digest goes
  back to `0310779c`, re-ratified the same way; no fingerprint move.
- **Proof.** `test_constitution`, `test_ld_release` (the two-envelope tests on the $800 in force and on L-D's $400,
  `AS_SET`), `test_standing_grant` (`TheProbeTotal800`: the owner's deploy re-ratifies, the updater never does, the
  rollback is L-D's digest), `test_dlane` (the bound follows the default), `test_dlane_report` (the line at -300, the
  header's two rows with their own costs, both zero-edge labels, PT1), `test_dlane_ld_joins`, `test_fast_lane_v2`,
  `test_live_long_single`. Operator's page: **The Probe total at $800 and the program line at -$300** at the top of
  `docs/operations.md`.

### The ration at birth, on `fix/spent-lineage-birth` (DEPLOYED 06:20Z Oct 10; no evidence reset; no setting)

- **Why** (measured on the House, Oct 10, 2026): about half of the direction lane's births died 15-60 minutes after
  birth on the tournament's `dlane.SPENT_TRY` without ever taking a try. The architect resolved a parent on the slice
  (a declared parent, a dead family of the same idea, a living twin) and, for a `long_single`, linked its twins'
  lineages, so the family joined a connected lineage whose one direction Validation try was already spent. Right for the
  false-positive accounting, but each such birth wasted research money, Gym runs and a population slot, and the
  architect never learned why.
- **The rule** (`league/swarm/dlane.py` `birth_spent`, `spent_birth_text`; `league/swarm/architect.py` `admit`): before
  `add_family`, a direction card's birth reads the lineage it would join (the parent's and every twin's it links: the
  set `lineage_tries` and `lineage_looks` read after the birth). When its tries reach `val_tries` or its looks reach
  `looks_per_lineage` (in flight too), the card is refused and recorded with the card refusals: the next request names
  the lineage that holds the try and the version that spent it ("propose a mechanism-level new idea on another slice or
  a new mechanism"), and the pass's event counts it (`card_refused.spent_lineage`). No lineage is linked for a refused
  card. `SwarmStore.looks_over` is `lineage_looks` over a lineage set.
- **The review's answers:** a CLAIMED try refuses too: a living Gym-band member of that lineage born earlier in the same
  pass (`Architect.pass_born`, a truncated answer's retry included), or one whose best awaits Validation
  (`researcher.awaiting_validation`, passed in: `dlane.py` still imports no researcher), counts against `val_tries`
  ("whose one Validation try is claimed (<family>, born in the same pass)" / "(<family> v<n> awaits Validation)"). The
  refusal names the lineage that holds the try (a `long_single`'s twin, not its parent). `looks_over` joins
  `harness_lanes.SEALED_READS` (a protected file). The LANES prompt is unchanged on purpose (its golden digests); the
  card refusal is the channel.
- **Unchanged:** alpha cards, the lane off, births with no parent, the tournament's retirement rule and the one-try,
  one-look accounting. Nothing in `league/live/`, `league/gym/` or `league/constitution.py`: the execution fingerprint,
  money digest and constitution digest are main's. Not handled: a living member of an earlier pass with no best yet,
  and a lineage joined after birth by identical code (`_link_code`); the tournament retires those losers as before.
- **Rollback:** revert the commit.
- **Proof.** `league/tests/test_dlane_spent_birth.py` (a spent lineage refused, named and fed back; a twin's spent try
  refused and the twin's lineage named; a second card of one idea in one pass, and across a retry, refused; a living
  member awaiting Validation claims the try; `birth_spent` agrees with `lineage_spent` after the birth on each lineage
  shape; a fresh idea, a lineage with its try left, an alpha card and the lane off are born);
  `test_swarm_harness_lanes` (`looks_over` is a sealed read).

### 03:36Z Oct 10, 2026: the Probe roster (#523), House `20261010T033512Z-df7078e102a6`, main `9e2cf9fc`; `dlane.roster` 5 at 03:48Z

Owner deploy (no gateway change): no order in flight at 03:35:03Z; nightly stopped, deployed, promoted 03:36:06Z (rollback
`20261009T225656Z-01beacbc792b`), nightly back 03:46:16Z, updater repointed to `9e2cf9fc`. Verified on the box: health
clean, real money on, execution fingerprint `31a7e921`, money `0310779c`, constitution `ca89ff8a` and gate contract
`397b22b772b3` unchanged. `dlane.roster` 5 set in `swarm.json` at 03:48Z (no deploy): the box reads 5 seats, one Probe
family seated, none waiting. Rollback of the rule: `dlane.roster` 0.

- **Why** (REDESIGN-1010, Oct 10, 2026; the operator's private grid and its confirmatory run): Done needs >= 30 real
  closes with >= 5 from each of >= 2 programs, while every program that passes its look trades at once from one shared
  Probe envelope. At the measured rate of direction verdicts, the envelope's 8 slots spread one or two closes over each
  of many programs, so the ">= 5 from each of >= 2" clause fails even for a strong edge. A roster seats a few programs,
  which then earn the closes that can show an edge.
- **The rule** (`league/swarm/bands.py` `seating`, `waiting`, `roster`; `dlane.roster` in `swarm.json`, read there
  alone): every Probe family holds a seat and is never hidden; a Candidate that cannot trade real money (the money
  table's real types) or has no `banded_at` holds none and is shown; the other Candidates queue, fresh ones by
  `banded_at`, then ones back from Probe by when they came back; the first `seats - Probe` hold a seat and the rest
  WAIT (no `bands.read` row, so no shadow or real instance and no money-table band move). Sized is outside. A setting
  that cannot be read, or is not a whole number, keeps the last good value, else gives no new seat (fails closed).
- **Pre-open check 6** lists waiting Candidates as by design, not as families missing a band row.
- **Rollback:** `dlane.roster` 0 or removed (a setting; no deploy; it releases the queue at the next families pass).
  Nothing in `league/live/`, `league/gym/` or `league/constitution.py`: the execution fingerprint, money digest and
  constitution digest are main's.
- **Review.** An adversarial review (3 lenses, each finding verified) confirmed 13 findings on the first cut; this
  version answers them: fail-closed settings, real-type seats, demoted families queue for a seat, pre-open check 6, an
  exact `seated` list, a cheaper one-family read, the docs' wording, and the tests below.
- **Proof.** `league/tests/test_swarm_roster.py` (15 tests): the pure rule; `bands.read` hiding and re-seating,
  one-family reads; a demotion through the store; a Probe family never hidden; Sized outside; non-real structures
  seatless; malformed and unreadable settings; the cap at 50; the dlane report's `roster`; pre-open check 6.

### Deployed Oct 9, 2026 (the entries below were written before their deploys; each is now live)

- 10:36Z release D-1 + D-1b (the direction lane on D2): `20261009T103632Z-1edfe38272fb`.
- 12:44Z the direction lane's graveyard (#519): `20261009T124422Z-c5baa58fd45e`, main `d70e00c3`.
- 16:17Z the direction lane's Train map (#520): `20261009T161659Z-95b21ceb53ea`, main `a3c54fa5`.
- 17:03Z the budget split (#521): `20261009T170259Z-404fe99d6c9c`, main `cf96b72c`, gateway `f8061e0f`.
- 22:57Z the weekend fixes (#522): `20261009T225656Z-01beacbc792b`, main `e24a5d6a`, gateway `507b6118` (rollback
  `f8061e0f`); fingerprint `31a7e921`, money `0310779c`, constitution `ca89ff8a`, gate contract `397b22b772b3`, all
  unchanged; health clean, real money on.

### The weekend fixes, integrated, on `release/weekend-fixes` (unreleased; a gateway deploy FIRST, then one owner deploy on main `cf96b72c`; no evidence reset)

`wfix/swarm`, `wfix/ops` and `wfix/replay` (the three entries below) merged one at a time on main `cf96b72c`.
Operator's page: **The weekend fixes, integrated** at the top of `docs/operations.md`. Nothing in `league/live/`,
`league/gym/` or `league/constitution.py`: the execution fingerprint (`31a7e921`), the money digest (`0310779c`), the
constitution digest (`ca89ff8a`) and the gate contract (`397b22b772b3`) are main's, checked at the head.
- **The finality join** (`league/ops/dlane_report.py` `finality`, `meter`, `report`): a close whose per-close twin is
  final has its replay landed whatever the nightly has replayed; with `forward.twins` on, a close with no final twin is
  `pending_twin` and the reading is not final (no A8); with it off, the nightly's landing as before. A1.1's "replay
  untested" why now says a close matched "a replay (a twin or the nightly)".
- **The review's five fixes** (Oct 10, 2026; `league/ops/` only):
  - `dlane_report.Research247`: a UTC day with no `stall` receipt is not held ("no stall receipt"), as a day with no
    `budget` receipt is not: item 7's "no owner step waiting" no longer passes on no evidence.
  - `stall.py` `done`: reads the report's FINAL holding checkpoints (frozen) instead of the once-said A8, and stands for
    each until a notice carrying it is SENT (`stall.json` `done_told`): a House start or a refused notice no longer
    loses a Done claim.
  - `dlane_report.lane_off`: with `dlane.mode` "off" the job still holds the program loss line (A1.3 retires a due
    program, whatever its lane; PL1 a House warning, the figures in the receipt) and writes no report.
  - `registry.py`: the `dlane` job also runs 30 minutes before each open, after the overnight expiry reconciliation (pid
    14's landed at 01:11Z; from Nov 1 that hour is past 01:30Z), so a program an expiry carried past the line is retired
    before the next session.
  - `stall.py`: with the lane off neither `dlane` nor `done` reads the report the lane last wrote (its K5 and A8 were
    mailed at every run for good).
- **Proof.** `test_close_twins` (`test_finality_reads_a_final_twin_as_the_landed_replay`,
  `test_with_the_twins_on_a_reading_is_final_only_once_every_close_has_a_final_twin`); `test_dlane_report`'s two
  nightly-finality tests run with the twins off (`NIGHTLY`). The review's: `test_dlane_report`
  (`test_a_day_no_stall_receipt_read_is_not_a_day_with_no_owner_step_waiting`,
  `test_with_the_lane_off_the_line_still_holds_and_no_report_is_written`, the registry's pre-open trigger, the stall
  job reading a real report's final checkpoints) and `test_ops_stall`
  (`test_an_untold_done_claim_stands_until_a_notice_is_sent`, `test_with_the_lane_off_its_last_report_is_not_read`).
  Both full suites (Python 3.11 and 3.14) at the head.
- **Rollback.** The previous House release and gateway version (its stall job ignores `stall.json`'s `done_told`).

### The swarm-side readiness fixes, on `wfix/swarm` (unreleased; an owner deploy on main `cf96b72c`; no evidence reset)

Four fixes from the operator's readiness audit of Oct 9 (M2, M3, M5, m3). Operator's page: **The swarm-side readiness
fixes** at the top of `docs/operations.md`. Nothing in `league/live/`, `league/gym/` or `league/constitution.py`: the
execution fingerprint (`31a7e921`), the money digest (`0310779c`) and the gate contract (`397b22b772b3`) do not move,
so no Probe program leaves Probe, no family is reviewed again and no ratification is needed. An owner deploy:
`league/swarm/gate.py`, `tournament.py`, `dlane.py`, `settings.py` and `league/ops/` are FORBIDDEN to the updater.
- **A cut answer is no answer (M2,** `league/swarm/gate.py` `AnswerCut`, `Gate._cut_check`, `gate.cut_tries_day` 6**).**
  A review or audit, the gate's or the incubator's, that Sail returns `incomplete` at max_output_tokens is a
  `review_error` / `audit_error` with `cut` true. No attempt is counted and nothing is barred. It is asked again next
  round on a new model-call key (`:cut<k>`; the Provider dedupes on the key). At most 6 cut answers a version, a stage
  and a UTC day; the sixth raises the owner's `reader_cut` alert, and the stage waits for the next UTC day. On Oct 9
  three cut answers in a row refused dir-qqq-ivlow-3d-call v38, a direction lineage's one try, to a token cap.
- **The ration before the cohort keep (M3,** `league/swarm/tournament.py` `_why`**).** A direction family whose
  lineage spent its one try or look retires even while the cohort keep holds it, which frees its population slot. At
  20:12Z Oct 9 the keep held 8 such families. Its cost: the retired program loses the incubator route. It is listed in
  the dlane report's `tightened`. The alpha lane and the lane-off rollback keep the keep's order exactly.
- **A D2 entry counts (M5,** `tournament.py` `_verdict`, `researcher.record_verdict`, `league/ops/funnel.py`,
  `scoreboard.py`, `dlane_report.py`**).** A direction verdict records `entered` and the lane's `screen` in its
  `swarm.tournament` row and its `validation_verdicts`; `passed` stays the line. The daily funnel gains
  `validations.entered` and `by_screen`, and the public page gains one row only when a window has a pre-check entry.
  The dlane report's direction funnel gains `entered`. A3's gate-wait leg counts entered versions (the verdict's
  `entered`, or `dlane_try.entered` for older entries) and never a refused one. Until now eqp-realcalm-drift-call v17
  (at Probe) counted as a failed Validation everywhere. An alpha verdict's row and record are unchanged, key for key.
- **R3 needs a 1.0x profit (m3,** `league/swarm/dlane.py` `robust_verdict`**).** R3 read `pnl_15 >= 0.5 x pnl_10`
  alone, always true for a 1.0x loss once P1 holds: eqp-term-contango-pool-call v6 (1.0x -$1,778.21, 1.5x +$143.23)
  passed and spent its lineage's try. A 1.0x P&L at or below zero now fails R3. It is a tightening, listed in the dlane
  report's `tightened`. The researcher's brief text is unchanged: the Train map's golden pins it.
- **Proof.** `test_swarm_gate_cut` (cut reviews, audits and incubator reviews; the new keys; the day's cap and its
  alert; a complete unclear answer still counts), `test_dlane_gate_entries` (the verdict row and record, alpha key for
  key, the lane off; the funnel and the page row; the dlane funnel; A3 with entries, older tries and a refusal),
  `test_dlane` (`test_r3_needs_a_profit_at_10x`), `test_dlane_d1b` (`test_the_ration_comes_before_the_cohort_keep`,
  replacing the test that the keep spares the ration) and `test_ops_stall` (the funnel's two new keys).
- **Rollback.** The previous House release. Its code ignores the new verdict keys and the `*_cut:*` kv rows. The
  families M3 retired stay retired.

### The weekend fixes, ops side, on `wfix/ops` (unreleased; a gateway deploy FIRST, then an owner deploy on main `cf96b72c`; no evidence reset)

The readiness audit of Oct 9 (`scratch/ready-1009/FIXLIST.md`: M6, M7, M8, M9, M12, m11) and the pinned amendment
DONE-RULE-A1 (sha256 `333bad06...`: A1.1-A1.4). Operator's page: **The weekend fixes, ops side** at the top of
`docs/operations.md`. Nothing in `league/live/`, `league/gym/` or `league/constitution.py`: the execution fingerprint
(`31a7e921`), the money digest (`0310779c`), the constitution digest (`ca89ff8a`) and the gate contract (`397b22b7`)
do not move, so no ratification and no Probe program leaves its band.
- **The stall alarm** (`league/ops/stall.py`, `gateway/lib/email.mjs`): four causes, `dlane` (the lane's warning alarms;
  K5 the owner's step), `done` (A8, told at once), `preopen` (a pre-open FAIL) and `forward` (a late ready file, a
  nightly error 6 h, a nightly stop 2 h); `owner_deploy` waits 45 minutes and is skipped while a deploy is in flight.
- **The Done meter** (`league/ops/dlane_report.py`): consistency must be measured on 2 programs (A1.1); item 7 read per
  UTC day from the swarm store and the `budget` and `stall` receipts, the operator's edits listed (M7); a reading is
  final only once its replays landed and its broker fees posted, then frozen, and A8 fires only on a final one (A1.4,
  M8); Net after costs from the close economics beside each meter (M9); P(Done | zero edge) 0.024 with its horizon and
  source (A1.2; `policy.json` 0.13 -> 0.024).
- **The program loss line** (A1.3; `league/swarm/dlane.py` `program_loss_usd`, `policy.json` -200): each Probe row
  carries its program's realized Probe net and when DM1 can first fire (17 trades at the live sigma); the `dlane` job
  retires swarm-side a program whose realized Probe net is at or below -$200 (exits go on; alarm PL1).
- **The report's m11:** exact closes for the buy-and-hold or a why, finished sessions only in the `direction` job's
  file, real opens in the funnel, E0's basis said as it is.

### The per-close fill replay, on `wfix/replay` (unreleased; an owner deploy on main `cf96b72c`; no evidence reset)

The readiness audit of Oct 9, blocker B1 (c). Operator's page: **The per-close fill replay** at the top of
`docs/operations.md`. Every real close of an agent program gets its own replay twin: the real trade's own orders (its
contracts, the open's decision minute, limit, size and time in force, each close order the venue received), replayed by
a fixed Gym program on the gate image with the Gym's own engine and fill model, one gate job a close over the trade's own
sessions. Done item 4 then compares each close with its own twin instead of a nightly replay that may not trade the day
the real program did (pid 41 has no nightly match: v17's replay holds Oct 8 to Oct 12).
- **New:** `league/ops/twins.py` (the puppet program, the plan from the live book read-only, the verdict, the round);
  `league/swarm/loop.py` runs it as its own round after the nightly forward; `league/swarm/settings.py`
  `forward.twins` {max_jobs 12, attempts 3}, null or false is off. Records in the swarm store's kv `close_twins`.
- **The report:** `league/ops/dlane_report.py` `replay_gap` matches a close with a priced twin to it, never matches a
  close with a final unpriced twin (no_fill, no_contract, unpriceable) to the nightly replay instead, and falls back to
  the nightly (version, day) match only for a close with no record; with no record the figures are D5's key for key.
  `replay_twins` lists every counted close with its verdict, both returns on maximum loss, the gap and both exits.
- **Walls.** Nothing in `league/live/`, `league/gym/` or `league/constitution.py`: the execution fingerprint
  (`31a7e921`), the money digest (`0310779c`) and the gate contract sha (`397b22b772b3`) do not move (checked at the
  branch head). No band, forward record, trial count or money moves; a twin is not a research run.
- **Proof.** `league/tests/test_close_twins.py`: the plan on the live book's own shapes (pid 14's and pid 41's), the
  puppet through the real batch runner on a synthetic gate store (the exact contract among decoys, the Gym's expiry
  close, a program close on its day and minute, a vertical left to expire, the model's no-fill, a contract missing at the
  minute, an image without the entry day), the round (one gate job a close, no run row, only once the image holds the
  exit day, never a House route, retries per ready day, the switch), the loop's round, and the report's matching.
- **Rollback.** The previous House release: it never reads `close_twins`.

### The budget split and the graveyard's report row, on `fix/budget-split-sail` (unreleased; an owner deploy on main `d70e00c3`; no evidence reset)

Two operator decisions of Oct 9 (about 16:00Z). Operator's page: **The budget split** at the top of
`docs/operations.md`. Base: main `d70e00c3` (release L-D, D-1, D-1b and the graveyard); PR #520 (the direction Train
map) was still open and is not in it. Nothing in `league/live/`, `league/gym/` or `league/constitution.py`: the
execution fingerprint (`31a7e921`), the money digest (`0310779c`) and the constitution digest (`ca89ff8a`) do not
move, so no ratification. An owner deploy: `league/ops/` and `league/swarm/policy.json` are FORBIDDEN to the updater.
- **The split** (`league/ops/budget.py` `SPLIT`): Sail 0.6 / Claude 0.4 -> Sail 0.8 / Claude 0.2. THE OWNER'S CEILING
  stays $25 a day: Sail $20 and Claude $5 (was $15 and $10). Why, measured read-only on the House's swarm store (Oct 7
  19:30Z to Oct 9 15:37Z): DeepSeek V4 Flash researched as well as Claude Sonnet 5.5 at 38x lower model cost per Train
  run and 3.3x (95% CI 2.2-5.1) more families reaching the Train bar per research dollar; Claude's researchers had no
  Validation pass (0 of 3); the first real Probe trade (eqp-realcalm-drift-call v17, 14:26Z Oct 9) was written entirely
  by Flash. The operator turned the Claude research band off in `swarm.json` (`researcher.claude_top` 0,
  `claude.role_usd_day` researcher 0, architect 0), leaving Claude the gate's review and audit and the strategist
  (about $2 a day or less, estimated), so the unused Claude share moves to Sail (Gym boxes and Flash research).
- **Derived in the same release:** the floor $4 Sail / $1 Claude (was $3 / $2); at the ceiling 7 Gym boxes and $0.33 an
  hour of Sail model pace (was 5 and $0.25), every Claude line at most $5, Sail's gate reserve $2.00 (was $1.50),
  Claude's room $5 for the audit, $3.70 for the review and $3.05 for every other role (was $10, $8.70, $8.05).
  `policy.json`: `gym.max_boxes` 5 -> 7 and `researcher.sail_usd_per_hour` 0.25 -> 0.34 (so the policy lets Sail's $20
  reach its knobs), `claude.role_usd_day.strategist` 6 -> 3 (its line leaves the gate's holds inside $5). The engineer:
  `usd_day` $4 -> $3 and an attempt's cap $3 -> $2 (review $1), so an attempt and its review fit a day.
- **Its cost.** Sail drains faster: about $21 a day with its fixed cost at the ceiling (from about $16), so for the
  same balance the owner's two-day funding notice comes sooner. Claude's line is $5, of which the gate's holds keep
  $1.95: the strategist, the post-mortem and the engineer share at most $3.05. At the floor Claude's $1 is under the
  gate's holds, so the review (and the audit, unless its hold is at most $1) runs on its Sail model with the gate's
  "not the plan's reviewer" alert; at the old $2 one review and one audit fitted. The engineer's attempt is a third
  smaller. The box's `swarm.json` wins over `policy.json`: where it sets `gym.max_boxes` or
  `researcher.sail_usd_per_hour` (last recorded Oct 8: 2 and 0.5) those still cap Sail's spend under the $20.
- **The day's figure.** RULE_VERSION and the schema stay 2: an old `budget.json` is read held to the new shares, so
  Claude is at most $5 at once and Sail keeps the day's figure (at most $15) until the next UTC day's first budget run
  (00:30Z) sets up to $20.
- **The `dlane` report's header** (`league/ops/dlane_report.py` `LOOSENED`, the owner's goal of Oct 9, item 5) adds the
  direction graveyard rule (PR #519, deployed 12:44Z Oct 9) with its cost: more direction births may retry ideas
  similar to dead alpha ones; each lineage still gets one Validation try and one look, at D2's measured
  false-positive rate of 10.4% per program. The Train map (PR #520) is not listed: it is not in this base.
- **Proof.** `test_ops_budget` (the ceiling $20 / $5, the floor $4 / $1 and its Claude dollar under the gate's holds,
  the taper day by day, the day's figure, the two-day lead, Claude's room by stage), `test_swarm_settings_policy` (the
  committed policy reaches the $20's knobs; the paid-model lines), `test_ops_jobs` (pre-open check 5 at the $4 floor),
  `test_ops_engineer` (the $3 line, the $2 attempt) and `test_dlane_report` (the new header row). Examples that tapered
  under the old shares were moved to balances that taper under the new ones. `test_swarm_frontier_routing` and
  `test_swarm_graveyard_digest`, which do not judge the budget, lift Claude's share in their fixtures: $5 less the
  gate's holds is under the post-mortem's 64,000-token OpenAI hold (about $4.90; OpenAI is closed by the budget in
  production anyway).
- **Rollback.** The previous House release: its code reads this release's `budget.json` held to the old shares.

### The direction lane's Train map, on `feat/dlane-trainmap` (unreleased; an owner deploy, gateway first; no evidence reset)

Births aim at the call shapes that pass direction-v2 on the Train years, instead of searching for them. After the first
direction program reached real money (2.4 h after D-1b), 7 of the 8 other direction families had no eligible version,
mostly on E1. Operator's page: **The Train map** in the Release D-1 section of `docs/operations.md`.
- **The map** (`league/swarm/dlane_map.json`, new, protected). It comes from the operator's census of SPY, QQQ, IWM and
  one-on-each-root call cells, scored by the House's own `dlane.train_score` and `robust_verdict` (main `d70e00c3`) on
  2022-24 data only, one lot at natural prices: 30 of 3,136 cells pass. Every passer is a 0.20-delta call held 2-5
  sessions, in the market all three Train years. The file is reduced to what agents may see: each shape in words, its
  S_D to one decimal, the unit's verdict as a word, and three lessons. Its header carries the label, `built_at`,
  `inputs_sha256`, `source_sha256`, and the commit, `dlane.py` sha and bar settings it was scored under. There is no
  dollar figure, price level, price ratio, per-year P&L or year outside 2022-24.
- **Who sees it** (`league/swarm/dlane.py` `train_map`, `train_map_text`, `train_map_brief`, `map_on`,
  `map_text_problems`). The architect's LANES block gets every passing shape (one line each, at most 30), the lessons,
  and "aim at these shapes and vary the gate, the hold or the root". A direction researcher's brief gets the lessons and
  the 5 best passing shapes on its roots. Both carry the label "in-sample: Train years 2022-24, from the operator's
  census at one-lot natural prices; the screen decides". A shortfall request's opening line points at it.
- **The reader** is cached and never raises. A missing, malformed or unsafe file (a refused year, a `$`, a figure, a
  wrong label or objective, one bad row) reads as no map.
- **The switch:** `league/swarm/policy.json` `dlane.train_map` true. swarm.json false hides it at once, and the code's
  default is false. Off, and with `dlane.mode` "off", every text is main `d70e00c3`'s byte for byte, and so is the
  alpha lane (golden digests computed on that commit).
- **Its cost** (a reported loosening: agents now read an operator study's Train-year figures): births aim at
  in-sample winners. The screen's false-positive rate per program is unchanged, but more programs reach the screen, so
  there are more false passes in count. The `dlane` report's header lists it (`league/ops/dlane_report.py`
  `LOOSENED`), together with the graveyard row deferred to this owner deploy.
- **Walls:** `league/ci.py` FORBIDDEN and the gateway's `protected.mjs` gain `league/swarm/dlane_map.json`, as for
  `dlane.py`. The gateway needs `npx wrangler@4.129.1 deploy` first; until then the deployed merge route does not
  refuse an edit to the map, but the updater does. The execution fingerprint (`31a7e921`), the money digest
  (`0310779c`) and the constitution digest (`ca89ff8a`) do not move.
- **Proof.** `test_dlane_trainmap` covers the switch, the reader's refusals, the secrecy of every text (no
  dollar-looking or price-looking digit run, no year but 2022-24, no provenance hash), each lesson's claims about the
  passers against the file's rows, length bounds, the alpha and rollback goldens, the report row and the wall. The
  operator's private figures are never in the repo: the tests read them from the file `LTCM_PRIVATE_FIGURES` names
  (skipped without it). `test_dlane`'s committed-settings test gains `train_map`.
- **Rollback.** swarm.json `dlane.train_map` false (instant), or `floor_box.py rollback`.

### The direction lane's graveyard, on `fix/dlane-graveyard` (unreleased; an updater release on top of D-1, live since 10:37Z Oct 9 as main `2b60d94a`; no evidence reset)

The operator's decision after the House's architect pass of 11:32Z Oct 9, **a reported loosening**. Operator's page:
**The graveyard** in the Release D-1 section of `docs/operations.md`. Swarm-side only (`league/swarm/cards.py`,
`league/swarm/architect.py`, tests, docs): no `league/live/`, `league/gym/`, `league/constitution.py` or other
protected path, so the updater ships it. The execution fingerprint (`31a7e921`), the money digest (`0310779c`) and the
constitution digest (`ca89ff8a`) do not move.
- **What was wrong.** Live D-1 refused direction cards on alpha graveyard rows: low-iv-drift-call and
  calm-trend-drift-call were refused because their mechanism text reads as the trend_momentum cell, which holds dead
  alpha rows (the refusal: 15 rows, 7 that need a claim, the newest persistent-ceiling-rejection-put, REFUTED). Those
  verdicts judged timing edges against drift under the alpha rules. They say nothing about a direction program, which
  direction-v2 judges as labelled beta, under the lane's own multiplicity control (one Validation try and one look per
  lineage, D2's false-positive rate measured per program).
- **The rule.** While `dlane.mode` is not "off", a DIRECTION card is bound only by the graveyard rows of DIRECTION
  families. A row's lane is read the way D-1 stores it: the family's spec `lane`, else its card's `lane`, else its
  `card_sha`'s card for a fork. A family with no lane is alpha. DRIFT rows still never bind a direction card. A
  direction family's REFUTED, MECHANISM or other verdict row still needs the full rebirth claim with its budgets. A
  claim a direction card makes on an alpha row is checked as one on a DRIFT row: a rebirth only when it holds, otherwise
  dropped. Alpha cards are unchanged: every row binds them.
- **The architect's view.** The LANES block and the BIRTH CELLS header say what binds a direction card. Each cell line a
  direction card may land in counts the rows that bind one, so no alpha row reads as closing a direction cell. `closed`
  (no paid pass without a cell) follows the same rule. A direction birth's `swarm.born` card carries `alpha_rows`.
- **Its cost.** More direction births may retry ideas similar to dead alpha ones. Each such lineage still gets one
  Validation try and one holdout look, at D2's measured false-positive rate of 10.4% per program (mixed worlds). The
  `dlane` report's loosened-rules header (`league/ops/`, an owner-deploy path) lists it from the budget split (above).
- **Proof.** `test_dlane_graveyard`: a direction card in a cell of alpha REFUTED and MECHANISM rows only is admitted
  (the live example among them); a direction family's REFUTED row still needs a claim; alpha cards' verdicts and every
  reading with `dlane.mode` "off" equal main `2b60d94a`'s on a fixture store (golden digests computed on that commit).
- **Rollback.** Revert the commit (`dlane.mode` "off" rolls back the whole lane).
- **Known, not changed:** with `architect.max_rebirths_per_cell` 0, a claim that passes every other test raises
  `KeyError` in `RebirthIndex._claim` (it reads `cell_births[cell]` for a cell with no rebirth yet). No deployed
  setting reaches it (policy.json sets 12).

### Release D-1b, the direction lane on D2, on `release/dlane-d1` (unreleased; in D-1's owner deploy; no evidence reset)

On top of D-1, same branch, same deploy. It switches the direction lane to the D2 screen and meets the owner's goal of
Oct 9: item 4, a pre-registered screen whose measured false-positive rate is at most 15% per program, stated beside
every Probe trade; and item 3, "Tell me 2 days before Sail or Claude runs out". It is Claude's decision DSCREEN-ADOPT,
**a reported loosening**. Operator's page: **Release D-1b** at the top of `docs/operations.md`. Swarm-side and ops
only: no `league/live/`, `league/gym/` or `league/constitution.py` change. The execution fingerprint (`31a7e921`), the
money digest (`0310779c`) and the constitution digest (`ca89ff8a`) stay release L-D's (deployed 09:04Z Oct 9, below).
- **D2 on** (`policy.json` `dlane.screen` "D2"; receipt `docs/benchmarks/direction_screen_2.json`, sha `c3605947`,
  pinned in `dlane.screens.D2` with c 1.00 and the lane's figures; CI holds the sha and every figure to the receipt).
  - The rule: on Validation, 50+ trades on 25+ entry days and a mean entry-day return above zero; after the one look,
    the pooled entry-day t over Validation and the holdout at least 1.00 and the holdout's P&L above zero.
  - The statistic is DSCREEN-2's own on exact figures (to 3e-15). On the Gym's rounded summaries the gate judges its
    lower bound over the rounding, so no pass comes from rounding.
  - The rollback is swarm.json `dlane.screen` "S-C", at once. The alpha lane is untouched.
- **Its cost, measured** (the receipt): the lane's false-positive rate per program at zero edge goes from S-C's 1.41% to
  10.37% on mixed worlds (9.57-11.16%) and 12.39% on 2022-24 worlds (upper bound 13.29%). All cells reach 13.37% and
  14.11% (upper bounds 14.08% and 15.01%). Power at +10% goes from 3.22% to 19.95%. D2 was adopted after it failed the
  operator's own 12% adoption rule: a post-hoc loosening, listed in every `dlane` report's header.
- **Calls only:** `dlane.structures` ["long_single"] (no direction debit vertical, no put), and D2 runs only while the
  lane is calls only. New Train bar C1: a direction program whose Train trades hold a put or a short leg fails it.
- **One Validation try and one holdout look per direction lineage** (`dlane.val_tries`, `looks_per_lineage`, fixed at
  1), so a lineage's false-positive rate is the program's.
  - The tournament guards the try (`dlane.try_open`; one lineage member a round; `spent_lane` and `waiting_lane`, which
    the stall alarm reads). As a backstop, a late second try never reaches the gate.
  - The gate's ration is 1 for a direction lineage. A lineage that has used either without a pass still in play
    retires (`dlane.lineage_spent`), and a direction family never forks once its lineage has tried.
  - The alpha lane keeps its counts.
- **The false-positive rate beside every trade** (operator-facing only): each direction look's line and event carry
  `screen`, `fp_lane_mixed`, `fp_lane_2224` and `receipt`. The fast lane's band rows carry `fp`. The `dlane` report's
  new `fp_beside_trades` lists every real Probe trade and every agent real close with its program's screen, its rates
  and the contamination statement.
- **The meter warning:** the `budget` job's `funding` notice now goes when research on a meter runs out within 2 days
  at its current burn (`out_in_days`, `burn_usd_day` in `budget.json`; at the ceiling the same 7-day card line). It
  goes at most once a day per meter (it was once a week), under a per-day notice id. The channel and the facts' names
  are unchanged.
- **The review's fixes** (Oct 9, on the D-1b build):
  - *The try is always judged.* A direction lineage's first Validation try is judged even when the researcher moved the
    candidate on while its job was out (it was dropped as stale, spent the try and retired the family unjudged). A try
    with no verdict, or whose verdict in the gate is on another Gym image, is validated again as that version
    (`dlane.try_owed`). A family whose own try has no verdict is not retired.
  - *The screen at the result.* A direction look that entered by D2's pre-check alone and lands after the rollback to
    S-C fails closed (`gate.PRECHECK_UNDER_LINE`); the look's marker records how the version entered.
  - *The calls-only code check* (`dlane.calls_only_code`): a direction program whose text names a put, a short leg or
    any open but `long_call` is refused by the researcher before any version, never validated by the tournament
    (`calls_refused`), refused by the gate ("calls only") and failed by the incubator's review. Still open: a type built
    at run time from other pieces, and no live-side calls-only guard: release L-D shipped without it, the live path
    still admits a `long_put` for a `long_single` family, and the guard waits for the next `league/live` release (a
    fingerprint move, rule F0).
  - *The burn in the mail.* A notice fired by the burn states the burn as the mail's "now" figures and the day research
    runs out at it as the add-by date, so it never says "Nothing stops" while research runs out within 2 days.
  - *A screen beside Probe trades only.* The `dlane` report states a look's screen only beside a `:r` trade opened at or
    after that look; tuition and incubator closes state none.

### Release D-1, the direction lane, on `release/dlane-d1` (unreleased; an owner deploy after release L-D; no evidence reset)

A DIRECTION research lane beside the unchanged ALPHA lane, in which profit from the index's direction counts, reported
beside the same-risk buy-and-hold and never called alpha: it is leveraged index beta minus option costs, and an
always-in call program can pass its bar. Claude's decisions under the owner's goal of Oct 7 (items 4 and 5), after the
plan of Oct 9 and its critic. Operator's page: **Release D-1, the direction lane** at the top of `docs/operations.md`;
the design is in `docs/design.md`. Swarm-side only: no `league/live/`, `league/gym/` or `league/constitution.py` change,
so the execution fingerprint (`31a7e921`), the money digest (`0310779c`) and the constitution digest (`ca89ff8a`) stay
release L-D's: no evidence reset, no evaluator adoption, no re-ratification.
- **The lane's core** (`league/swarm/dlane.py`, new, protected: `league/ci.py` FORBIDDEN and the gateway's
  `protected.mjs`, so the gateway is deployed first): settings and bounds (`policy.json` "dlane", mode "gate"; the code's
  default "off" is the rollback), the lane, the Train bar direction-v2 (E1, E3, E4, E5 at 1.0x; P1, R2, R3 at 1.5x; E2,
  R1 and the mechanism test reported only), the live unit (today's closes and equity; "unknown" passes), the incubator's
  direction mark, the screen (S-C for direction; S-B for alpha byte for byte; D2 refused until a receipt is pinned), the
  direction leakage alarm (10 looks, over 60%), K5, the birth quota, the agents' text and the pinned Done rule's
  constants.
- **Cards, architect, allocation, strategist:** `card.lane` and the `equity_premium` class; graveyard DRIFT rows do not
  bind a direction card; the architect's LANES block, `DirectionQuota` (direction about half of births while behind, at
  most 60%) and the `lane_only` request after 12 h without a direction birth; the strategist's inputs per lane.
- **Researcher:** a direction family is scored by direction-v2 and demoted on a failed 1.5x rule; its brief, status and
  views carry the lane's text; the ROLE prompt is lane-aware.
- **Game, gate, evidence, incubator, tournament:** no hidden look for a direction lineage (`dlane.arm_fraction` 0) and
  direction kept out of the game's R1(b) and R2; the look's screen per lane, recorded on each look event (lane, screen,
  receipt); the leakage alarm per lane; the incubator's direction mark (refused while the lane is not "gate"); the
  tournament writes `validation_r_sd` beside `typical_max_loss_usd` for L-D's DM1.
- **The `dlane` job and report** (`league/ops/dlane_report.py`, new; at the House's start and daily 01:30Z; in a pause
  too; operator-only; read-only but for K5's kv; no site data contract change): `<state>/dlane-report.json` with the
  funnel per lane (24 h, 7 d), the Probe envelope (release L-D's two envelopes read from the constitution through
  `money.Table`, the window's and the total's figures under GROSS and NET, the binding room), THE DONE METER of the
  pinned rule (DONE-RULE sha256 `0d007696...`: `done_screen` `:r`, `done_all` `:r`+`:t`+`:i`; 30 closes, 5 from each of
  2 programs, net > 0 after fees, consistency over 5+ matched closes, read only at the 30th close and every 10th; beside
  it P(Done | zero edge) 0.13, the same-risk buy-and-hold delta-matched and in dollars at risk, the screen's
  world-conditional false-positive rate, every loosened rule with its cost and the contamination statement), the account
  and the research costs, the contamination meters per lane, and alarms A1-A9 and K5 as House alerts. K5 is automated:
  at a direction realized net at or below -$600 the job sets the kv `dlane_k5` and the lane reads "shadow" until the
  operator clears it; the job's next run records the clear and re-arms K5 at -$600 below the net at clearing (kv
  `dlane_k5_base`). `league/ops/fast_lane.py`'s rows gain `lane` while the lane is on; the learning game's report says
  what the lane changed mid-experiment.
- **The agenda guard** (D9): the swarm warns the House at its start, and whenever it changes, when `swarm.json`'s locked
  preamble or fallback agenda is over 4,000 characters, not ASCII or names a hidden year; the new operator tool
  `scripts/agenda_install.py` (check, apply) refuses such a text and installs a good one with a before-copy, an atomic
  replace and the strategist's section cleared.
- **Every loosened rule, with its cost** (the operator's measurements): beat-your-exposure for alpha only; direction-v2
  in place of the worst year (more null programs reach Validation; the false-positive rate per program screened is
  unchanged); no hidden look (the lane's false-positive rate at zero edge 0.02% -> 0.70%); S-C (the lane 0.70% -> 1.41%,
  2.22% when both windows rose; power at +10% 1.68% -> 3.22%); the direction leakage alarm at 60% (a leak trips later);
  the incubator's direction mark (with no edge about -$36 a week, at most $150 a week, never evidence); DRIFT rows not
  binding direction cards; **the birth quota: alpha births fall from about 73 to about 36 a day mid-way through the
  learning game's T0 experiment, and the ROLE prompt change reaches alpha researchers too (a shared prefix), so "alpha
  golden" holds for code paths only**; the unit at 10% of equity rather than MONEY's $75 (Probe-stage Done 6.3% against
  7.8%, P(net <= -$360 in 8 weeks) 0.35 against 0.27); **K5's clear: `dlane.k5_clear` true disarms K5 while it stays
  set** (the report warns every run until it is taken out).
- **The review's fixes (Oct 9, before any deploy):** with the lane off, the one leakage alarm counts only the looks the
  alpha line judged (direction looks judged on S-C never stop the alpha lane; a code rollback to the release before
  counts every look, so `docs/operations.md` says to check the pooled pass share first); a direction family never takes
  its lineage's game or control arm (born under a control-arm parent, a game lineage's member from before T0, or left in
  a lineage an alpha family was given an arm in); K5's clear is durable and re-arms from the net at clearing; the
  direction quota reserves no more births than the room left under `architect.max_alive_per_class` in the lane's classes
  (`long_single x etf`, `debit_vertical x etf`), and class-capped direction cards are named apart (`lane_class_capped`);
  no agent text carries a figure priced at today's closes or the account's equity (E5 is its verdict and a scale-free
  hint: this overrides HARNESS 6's `scale` in the view on secrecy grounds); the brief's vertical guidance is a lane rule
  with no Train provenance. Joins from the integration: the public checklist's `gate_paused` reads the family's own
  lane's alarm, and a direction parent's fork carries `lane` in its `swarm.born`.
- **Joins with release L-D** (main `40c39435` merged into `release/dlane-d1` after L-D's deploy): the `dlane` report's
  Probe envelope reads L-D's rolling budget from the constitution (`real.probe_figures` told each basis; alarm A4 reads
  the binding envelope's room, A5 names `probe.demotion`); the tournament's `validation_r_sd` keys are the ones
  `league/live/families.py` reads, tested end to end (`test_dlane_ld_joins`).
- **Owner steps, in order** (docs/operations.md): L-D deployed and verified (done 09:04Z Oct 9); CI green on main's
  head; the gateway (`protected.mjs`) deployed; `floor_box.py deploy` in the money path's window with no order in
  flight; verify (no fingerprint or digest move, `lane_births` on the first pass, the `dlane` report written); install
  agenda v21 with `scripts/agenda_install.py`. Rollback: `dlane.mode` "off" in `swarm.json` (read every loop, no
  restart; every path as before D-1), agenda v19.1 back with the same tool, then `floor_box.py rollback` if the code
  must go.

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

## 2026-10-09

### 09:04Z, release L-D, the Probe budget read NET and rolling: House release `20261009T090334Z-cdbf1864a573` (main `40c39435`; PR #517), money digest `1665c385` -> `0310779c`, evidence reset 5

Owner deploy. PR #517's Checks green on the exact head `5a37227e`, merged as main `40c39435` (tree-identical to it);
main's Checks green 09:03Z. No order in flight at 09:03:25Z (the House live test's QQQ position open, carried); the
nightly stopped, `floor_box.py deploy`, PROMOTED 09:04:19Z (previous `20261009T025942Z-376c84971b5e`), the nightly
back 09:14:32Z. Verified on the box: real money on, no failures; the Probe row as built (`max_open` 8, `loss_basis`
"net", `demotion` "dm1", `loss_budget_usd` 400, `loss_window_sessions` 20, `loss_total_usd` 400); constitution
`ca89ff8a`, money `0310779c`, the standing grant re-ratified `1665c385` -> `0310779c` at the House's start; the
execution fingerprint `31a7e921` and the evaluator adopted (the Gym bundle `gym-engine-4-e1c896f8d304` unchanged);
the practice cohorts completed (0 active: 40 complete, 5 failed), as planned. Local full suites green on 3.11 and
3.14 (7,698 + 2,005). As built:

The one planned evidence reset of Oct 9 (the plan of Oct 9, "L: Release L-D", and its critic). Claude's decisions under
the owner's goal of Oct 7, item 4 (Probe sizing up to 10% of equity a position, a Probe loss budget up to $400 in total)
and item 5 (every loosened rule reported with its cost), and, for the budget's two figures (L9), the owner's goal as he
re-set it on Oct 9 (about 06:20Z), item 4: "Probe loss budget: $400 net in any rolling 20 sessions and $800 net in
total (realized Probe losses net of Probe gains, plus the maximum loss of everything open)". The 10% is unchanged.
Operator's page: **Release L-D** at the top of `docs/operations.md`.
- **L1, the budget read NET** (`options_money.probe.loss_basis` "net"; allowed exactly "gross" and "net"). THE PROBE LOSS
  BUDGET's realized part is max(0, -(the summed cash of every closed position a Probe family opened)) from inception, in
  place of GROSS (`real.probe_tally`, now told the basis by `money.Table`; the envelope: realized + every real
  position's open maximum loss + the new open <= $400, two envelopes since L9). A Probe gain offsets Probe losses; a
  Sized gain never does.
  It reverses the fast lane review's deliberate GROSS choice of Oct 7. The refusal, the House warning and the fast lane
  report's `realized_basis` name the basis in force. Cost (MONEY, U10%-M3, no edge, 8 weeks): P(net <= -$360) 0.19 ->
  0.27, mean net -$8 -> -$14 (as traded -$45 -> -$64); Done 0.3% -> 2.6% (+5% edge, averaged over holds). Its main
  effect (the critic, B2, 12 weeks): gross Probe losses pass $400 on 46-72% of paths by hold (p95 $1,318-2,088), the
  Probe's realized drawdown passes $400 on 32-48% (worst $2,385), net Probe < -$400 on at most 0.5-2.5%; under GROSS all
  stay at or under about $440. NET is the loosest of GROSS / a high-water mark / NET (12-week Done at zero edge, 3
  programs, 3-session holds: 0.5% / 3.3% / 12.9%).
- **L2, 8 Probe slots** (`probe.max_open` 3 -> 8, bound 0-3 -> 0-8). The $400 envelope, not the count, bounds open Probe
  risk (three $129 units fit, eight $50 ones). Cost: P(net <= -$360) 0.30 -> 0.35, P(net < -$400) 2.1% (through Sized,
  outside the budget); Done 3.3% -> 6.3%. **The Probe room** the incubator, the House live test and the calibration keep
  is now min(`max_open` x 10% x E, $400) (`money.probe_room`; the critic, B1: 8 x 10% x E, $1,031.47 at E $1,289.34,
  would refuse every incubator open); at 3 slots it is fast lane v2's at any E up to $1,333.33.
- **L3, DM1 demotion** (`probe.demotion` "dm1"; allowed exactly "dm0" and "dm1"). For Probe and Sized families, D5's loss
  leg and the forward-negative demotion are off; demoted (sticky, exits only) at 10+ real trades whose returns on
  maximum loss sum below -1.645 x sigma x sqrt(n), sigma the banded version's Validation sd (read from the swarm's state
  by `league/live/families.py` `validation_r_sd`; its writer ships with release D-1), else the forward record's sd, else
  2.0. The replay-gap leg and the real_bad hold are kept; a Candidate keeps every "dm0" check; the live state keeps
  the version DM1 demoted (`dm1_demoted`), held at Candidate whatever sigma or the rule reads later. The band, the open's refusal and the admission read one rule. Every Probe or Sized family,
  alpha too. Cost (the critic, 4,000 bootstrap paths): fires within 30 closes 6.5-13% at zero edge, 14-22% at -0.10,
  29-36% at -0.25 (D5: 77/83/90%): the $400 envelope, not demotion, mostly stops a losing program. MONEY: P(net <=
  -$360) 0.27 -> 0.30; Done 2.6% -> 3.3%.
- **L9, THE ROLLING PROBE BUDGET** (the owner's goal of Oct 9, item 4). `probe.loss_budget_usd` ($400) is now over the
  last `probe.loss_window_sessions` (20) New York sessions, today included (the repo's NYSE calendar,
  `ltcm.data.us_equity_session`; `real.probe_window_start`), beside the new `probe.loss_total_usd` from inception, set
  to $400: the owner's $400 a window is a wall, read as its worst net stretch, and his $800 in total a ceiling (the
  operator's decision of Oct 9, after the budget simulation's worst-stretch run); each realized figure read by
  `loss_basis` (`real.probe_realized`, `real.probe_figures`). Under "net" the window's figure is its WORST NET STRETCH
  (the review of L-D: with the window's plain net a gain that aged out left more than $400 net in a later 20-session
  window, every open having passed), so a Probe gain offsets only the losses closed before it there and the $400 holds
  over every 20-session window as an outcome; the total is the net from inception. A Probe open must fit BOTH
  envelopes, each with every real position's open maximum loss and the open (`money.plan_open`); the refusal names the
  one that binds; exits go on. The House warning and the fast lane report (`realized_total_usd`, `total_budget_usd`,
  `window_sessions`, `window_start`, `binding`) show both figures with the basis. Bounds: window 20-2000 sessions (a
  longer window is never looser), total $0-800 (raising it to $800 later is CON-only: a money-digest move, no
  fingerprint move). Cost, as set: the worst net Probe loss from inception stays $400, and the window adds a second
  wall; a bad stretch that ages out of the window frees no room in the total. Measured (budget simulation, Oct 9,
  worst-stretch variants, seed 202610097, post-hoc, as traded, holds 2 / 3 / 5): P(Done) 6.0 / 3.3 / 1.0% at 12 weeks
  and 11.1 / 8.7 / 5.9% at 24, P(net Probe < -$400 within 12 weeks) 0.9-2.1%, P(the 60% drawdown stop by 24 weeks)
  3.0-8.3%; with an $800 total 7.0 / 3.7 / 1.1%, 14.0 / 10.9 / 7.2%, 37.6-39.2% and 41-46%; with the $400 total and no
  window 10.0 / 7.6 / 4.5%, 11.0 / 9.0 / 7.6%, 1.3-2.8% and 8.2-13.0% (the table is in `docs/operations.md`).
- **L5, the marketable natural limit `{"natural": k}`, dropped** (the operator's decision, Oct 9 about 07:40Z). It
  changed `league/gym/legs.py` and `league/gym/PROGRAM.md`, which moved the Gym bundle (`gym-engine-4-e1c896f8d304` ->
  `gym-engine-4-460b332db232`), so at the adoption no stored Train or Validation result would have been reused (every
  one re-run on the 2 Gym boxes the direction lane shipping that day needs) and the 2017-19 extension holds would have
  been cleared; `{"price": v}` already lets a program pay through. It waits for a planned Gym release (rule F0).
- **Not done: the narrower fingerprint** (the critic, N8): `league/live/money.py` stays hashed, because the practice
  book's caps read `money.Table` and the incubator's first-look rule lives there.
- **Identities.** Constitution digest `5698a2f9` -> `ca89ff8a`; money digest `1665c385` -> `0310779c` (the standing
  grant re-ratifies at the House's start on the owner's deploy); the execution fingerprint `b4c34031` -> `31a7e921`
  (league/live changed): the evaluator adoption re-derives every family's bests, and every active practice cohort is
  completed ("evaluator changed"), the 10 still active of the 12 admitted Oct 8 among them (their incubator first looks
  were expected about Nov 4-10). No family is banded. The Gym bundle does not move (`gym-engine-4-e1c896f8d304`,
  production's), so, as at fast lane v2, the re-derivation reuses recorded Train and Validation results and the
  extension holds stand.
- **Rollback.** CON-only: `loss_basis` "gross", `max_open` 3, `demotion` "dm0", `loss_total_usd` "400" (the value in
  force), `loss_window_sessions` 2000 (money digest `320899d6`, constitution `c9d8ef5b`), one owner deploy and no fingerprint
  move; each value runs fast lane v2's rule, decision for decision (`league/tests/test_ld_release.py`, against a frozen
  copy of `ccfa48d5`'s code; the 2000-session window holds every close since the fast lane). `floor_box.py rollback`
  moves the fingerprint again and, after D-1, drops D-1.

### 03:00Z, the cohort keep blocks every retire: House release `20261009T025942Z-376c84971b5e` (main `ccfa48d5`; PR #516)

While the saved incubator keep holds a family, its researcher's retire is not offered (the guard `cohort_keep`), the
mechanism test's retirement is deferred and the diagnostician's retire defers: after T0 researchers had self-refuted
three of the twelve cohorts' families, and the incubator pins only a living family's cohort. Swarm-side only: the
execution fingerprint `b4c34031` and the money digest `1665c385` are unchanged. Local full suites green on 3.11 and 3.14
(7,642 + 2,005), main's Checks green on the exact head; no open order at 02:59Z (the House test's QQQ position only,
market closed); PROMOTED 03:00:25Z; previous `20261008T225723Z-dea5c1d54c52`.

## 2026-10-08

### 22:58Z, the incubator unblock, the incubator cap and the contract's natural limit: House release `20261008T225723Z-dea5c1d54c52` (main `a5ff6f9e`; PRs #513, #514, #515), money digest `da5c7542` -> `1665c385`

Owner deploy. Main's Checks green on the exact head (gateway, 3.11, 3.14); local full suites green on both Pythons (7,639
+ 2,005). No order in flight at 22:57Z (the House test's QQQ position only, market closed); PROMOTED 22:58:10Z; previous
`20261008T190618Z-96ea9c702b14`. The `grant` job ratified on `1665c385` (trigger `digest`); `health.json` reads the
incubator table's `max_loss_usd` "75". The execution fingerprint `b4c34031` is unchanged: the twelve practice cohorts
carried over, under the 30-session window.
- **#513** (`league/CONTRACT.md`): "natural" is priced at the decision minute and rests when the market moves the
  program's way; to pay through, send `{"price": v}`.
- **#514, the incubator unblock**: the incubator's mark evaluates the drift screen itself at its defaults while the
  tournament's screen is off; a practice cohort's window is 30 sessions (`live.observe_max_sessions`, `practice.py`
  `COHORT_WINDOW`); the swarm loop queues Train and 1.5x re-runs for active cohort versions without a current mark.
- **#515, the incubator cap**, as built:

One money row moves: `options_money.incubator.max_loss_usd` "50" -> "75" (its bound in `OPTIONS_MONEY_BOUNDS` $0-50 ->
$0-75), Claude's decision under the owner's goal of Oct 7 (item 4 allows up to 10% of equity at risk per Probe position,
about $129 at E = $1,288; item 5 asks every loosened rule reported with its cost). Everything else is as it was:
`week_loss_usd` $150, `max_open` 4, `contracts` 1, the practice rule (3 sessions, 10 program closes, 0.80 coverage), the
Probe, tuition, calibration, the House test and the gateway's caps. Operator's page: **The incubator cap** in
`docs/operations.md`.
- **Why.** The Oct 8 incubator audit found the $50 unit cap refuses most one-lot units of the single-name cohorts, so a
  cohort that passes its first look often can never open ("could never open") or opens only its cheapest trades. Share
  of one-lot units (maximum loss plus open and close fees) at or under $50 -> $75 in the active cohorts' Gym Train
  trades: semis-lead-smallcap 4% -> 71%, smci-mara 40% -> 71%, opening-range 40% -> 62%, china-tech 55% -> 77%,
  peer-skew 50% -> 71%, index-corr 83% -> 98%, earnings-gap 10% -> 17%, megacap 0% -> 3%, semis-supply 2% -> 2%.
- **Cost (a loosening).** The row is two caps: a structure's maximum loss with fees, and a family's held and working,
  each $50 -> $75. The week's bound is unchanged ($150 net realized loss plus residuals; about $650 a month on average,
  $750 in a five-week month), and at most two $75 units are open at once (three $50 ones before). What rises is how
  much of that envelope a pass uses: replayed on the 10 live cohorts' eligible Train runs with the practice caps and the
  route's caps, with no edge after costs (-8% of maximum loss a trade), the expected real loss per first-look pass goes
  from about $0.40 to $2.45 at today's practice windows, from $2.22 to $25.53 at 30-session windows and from $5.52 to
  $26.59 at 40-session windows (maximum loss sent per pass $53 -> $145 and $71 -> $164); the worst simulated pass grows
  from -$272 to -$419 over 30 sessions and from -$310 to -$424 over 40 (several weeks, each inside $150). With zero edge
  the means are noise around $0. Alone it opens nothing: on this tree no cohort holds a Train-and-drift mark (the
  drift screen is off), and in the audit's replay 11 of 12 cohorts never reach the first look's 10 program closes
  inside today's windows.
- **Identities.** Constitution digest `5edc8956` -> `5698a2f9`; money digest `da5c7542` -> `1665c385`; the execution
  fingerprint `b4c34031` is unchanged (no `league/gym`, `league/live` or base-file change), so practice cohorts and
  bands carry over: no evidence reset. The updater never deploys it (the constitution is protected), and merging it
  holds the updater's later heads until the owner deploys main's head: deploy it right after the merge. The owner's
  deploy (`floor_box.py deploy`) writes the deploy row, and at the House's start the standing grant re-ratifies on
  `1665c385` by itself (`league/ops/grant.py`, `LiveGrant.standing`: a moved digest with an owner's deploy on record;
  `league/tests/test_standing_grant.py` `TheIncubatorCap`); verify the `grant` job's receipt says `ratified` with
  trigger `digest`, else `python3 scripts/live_trading.py --ratify` on the box. `health.json`
  `options_live.incubator.table.max_loss_usd` then reads "75". A rollback across it (`floor_box.py rollback`, an
  owner's release change) re-ratifies on `da5c7542` the same way.

### 22:17Z, the learning game's T0 (no deploy)

After the M0b retro's GO (c +0.44 [0.15, 0.68]), the operator's `t0_apply.py apply gate` at 22:17:02Z: `swarm.json`'s
`gym.train_from` deleted (the policy's 2022-01-03 applies), `game.mode` "gate", agenda v19 locked, the 2022 input card
installed (backups `swarm.json.before-t0-20261008T221702Z`, `input-capabilities.json.before-t0-*`). kv `game_t0`
"2026-10-08T22:17:18Z". The twelve practice cohorts carried over.

### 19:07-19:18Z, the learning game v1 (dormant until T0): House release `20261008T190618Z-96ea9c702b14` (main `7b71cb1a`; PR #512), gateway `8072b5b1`

Owner deploy. Main's Checks green on the exact head (gateway, 3.11, 3.14); local full suites green (2,005 + 7,619). No
order or position open at 19:06Z; PROMOTED 19:07:43Z; previous `20261008T124025Z-a9686c7cfcfd`. Money digest `da5c7542`
and the execution fingerprint unchanged. Gateway `8072b5b1-13af-4cf2-a47e-fd40b5b76b27` at 19:18Z (rollback `f63dd354`;
412/412): `protected.mjs` lists `league/swarm/game.py`. As built:

From T0 no agent sees 2020 or 2021 again; those two years, scored privately at 1.5x the half-spread and net of each
program's own exposure's drift, decide which programs reproduce and which reach Validation. Researchers keep working on
Train 2022-2024. `league/swarm/game.py` (new, protected) holds the rules; the build spec of Oct 8 holds their numbers.
- **Arms.** New core-five families split by their lineage's hash: half the game arm, half a concurrent control on the
  same seen years with the same hidden measurements as records. Families alive at T0, or born with another root, are
  legacy (today's rules). A family's first arm is kept (`game_arms`): a change of roots, a setting or the game switched
  off never moves it. Births are core-five only once the game has started.
- **Gate mode, game arm.** The look ladder (best by Train score, +0.5 over the last looked score, a profitable 1.5x seen
  run, 4 looks); a SELECT PASS (F >= 1.28) reads the CONFIRM year once (2 a family, 3 a lineage); only a CONFIRMED
  version goes to Validation, 2 tries; its Validation t never steers its compute; children of the top SELECT decile
  with a structural directive (a rotation of 12 that favours pricing, the structure's shape and a regime filter, which
  carried a half-found edge to unseen years in the Oct 8 planted-edge arena, over an input swap, an exit rewrite or a
  flip, which broke it) or a donor's execution (the child joins its signal parent's lineage only); three
  retirement reasons first; the dormancy clause spares such a family only while a CONFIRMED version awaits Validation
  or a look is out.
- **Blindness.** The architect and the strategist never read a game-arm family; every graveyard reader drops game-arm
  rows and those of families born before T0 and retired since the 2020-21 switch, and keeps dropping them with the game
  off once a T0 exists; a family's own views count no trial or mechanism verdict of a child the game bore beside it; the
  readers' research shares are renormalized over what they read; the strategist's section may not name 2020 or 2021;
  the input card reads "span_mismatch" under a 2022 Train until it is re-audited; a game retirement's public cause is
  one set of words for all three rules; the public site shows no game child. `league/CONTRACT.md` is unchanged.
- **Settings** (`league/swarm/policy.json`): `gym.train_from` "2022-01-03", `gym.allow_earlier_image` true,
  `practice.feedback` false, and the `game` block (`enabled` true, `mode` "gate", `arm_fraction` 0.5, and the rest as
  the spec's section 5; `game.cfg` bounds each). The House's `swarm.json` pins `gym.train_from` "2020-01-02": the
  operator changes it at T0 (docs/operations.md, **The learning game v1**, has the T0 steps and the rollback).
- **The span switch is the one evidence reset:** at the next start every living family's best is chosen again over
  2022-2024 (`migrate_objective`) and its robustness starts over; a recorded validation of the same version on the same
  Gym is reused.
- **Measurement.** The House's new `game` job (daily 00:00Z, read-only) and `scripts/game_report.py` write the
  operator-only report `<state>/game/report-<day>.json` (R1-R6, family-cluster bootstrap, the pre-registered
  decisions; D1 by lineage; the leak scan reads what researchers were shown).
- **After its review (Oct 8):** the ladder's triggers are a state (`game.recheck`); a program the Gym ends on the hidden
  years is a landed look; a failed look bars its program (no unbounded control looks); a hidden run is split in 8 as
  the retro ran it; a shadow PASS is read at the first gate round; the candidate is the newest CONFIRMED version not yet
  judged and the tries count CONFIRMED versions only; a start after T0 under a 2020 span voids the epoch and the next
  seen start writes a new T0; the ops' stall check owes a game family no Validation before a CONFIRM and counts the
  game's children as births; `harness_lanes` seals `game.py` and freezes the architect's and strategist's filters.
- **Owner steps, in order** (docs/operations.md, **The learning game v1**): merge and deploy; redeploy the gateway
  (`protected.mjs` gains `game.py`; it may wait a few days); let the release clear its watch; stop the swarm
  (`swarm.stop`); delete `gym.train_from` from the House's `swarm.json` (do not pin 2022: a rollback must fall back to
  2020 by itself); clear the 2020-24 words from the agendas and the strategist's section; re-audit the input card over
  2022; start the swarm. Before or with any code rollback, restore the before-copy of `swarm.json`: the previous
  release refuses every Train job under a 2022 span on the 2020 image.
- **What does not move:** nothing in `league/gym/`, `league/live/`, `league/constitution.py`, `league/swarm/settings.py`
  or the store: the execution fingerprint and the money digest are unchanged, no evaluator adoption, and Validation, the
  gate, the holdout look and Probe sizing are as they were. Control and legacy families, and every family with the game
  off, play main's round byte for byte (`league/tests/test_game.py` `Golden`, against `ab64c68b`).

### 12:40Z, even pacing: House release `20261008T124025Z-a9686c7cfcfd` (main `ab64c68b`; PR #510)

The guard holds new research while today's Sail research runs ahead of the day's budget pro rata plus `guard.pace_slack`
(0.05 of a day; `guard.pace_day` true). On Oct 8 the day's $13.91 was at its line by about noon UTC and new research
held to midnight; pacing spreads the dollars over 24 hours. A hold, never a brake: validation, the gate and the
nightly forward go on, and the stall job's braked hours (brake events) are unchanged. CI green on the exact head
`f4c0a2ef`; no order in flight; PROMOTED 12:41:07Z; previous `20261008T105752Z-eb1ce3d588a9`. Digests unchanged.
Operator, no deploy: `gym.max_boxes` 2 and `researcher.sail_usd_per_hour` 0.5 again (the 06:30Z values 1 and 0.2 were
a stopgap before pacing).

### 10:58Z, the gate's contract: House release `20261008T105752Z-eb1ce3d588a9` (main `8a058384`; PR #509)

The gate's paid readers were told ChainView has no `iv`, `delta`, `gamma`, `theta` or `vega` (league/gym/review_contract.py
lists `__slots__` only), so a delta-selecting program that ran and validated in the Gym got unclear verdicts as a
"verified contract defect" and was refused after three (`highbeta-skew-reprice-single` v15, Oct 7). `gate.gate_contract()`
adds every public property of `Ctx`, `UnderlyingView` and `ChainView` with one fact and its own hash; the gate's prompts
and keys, its restamped review and audit receipts, and the bands' and incubator's checks use it. Built in league/swarm,
so the execution fingerprint (`b4c34031`) and the digests do not move: no evidence reset, no ratification. Past
refusals stand. CI green on the exact head `531e27d9`; no order in flight; PROMOTED 10:58:34Z.

## 2026-10-07

### 19:12-19:24Z, fast lane v2 and the self-running release: gateway `f63dd354`, House release `20261007T191231Z-2cfea1c1f73c` (main `cd58fc8f`; PRs #506, #507), money digest `42c4a3af` -> `da5c7542`, evidence reset 4

Owner deploy in the US session under the owner's goal of Oct 7 (item 1: deploy any time when CI is green on the exact head and rollback is ready; a live-execution change first confirms no order is in flight).
- **CI:** green on the exact head `bf355f55` (gateway, tests 3.11 and 3.14); local full suites green on both Pythons (7,521 league tests); gateway 412/412.
- **Gateway first:** `f63dd354-253a-46d5-90a6-35ca07a49adf` at 19:12Z (rollback `e95a2d4a-a79a-4a68-97f6-914e6af2cace`); kill switch false after.
- **House:** no order in flight at 19:11:57Z; nightly stopped (operator:oct7) while idle; `floor_box.py deploy` PROMOTED 19:13:47Z (canary and ten-minute watch); previous `20261007T160204Z-31d63e37434e`. The standing grant RATIFIED itself at 19:14:20Z on money digest `da5c7542` (the `grant` job, release-triggered). `real_money` true, health failures []. The new jobs ran: `direction` (23 symbols), `fast_lane`, `stall`. Nightly unstopped; harness observer re-pointed to `cd58fc8f`.
- **PR #506** (`league/CONTRACT.md`): the researchers' contract now says real money opens four types and is on.

#### Fast lane v2

The owner's goal of Oct 7, item 4: a program trades at Probe size as soon as it passes a pre-registered screen whose
false-positive rate is measured. Based on PR #505 (the House's release `20261007T160204Z`). The screen (t 1.65, 2 of 4
quarters, N = 1, one flat holdout look at p <= 0.10 a program), direction counts (`policy.json`: the drift screen's
refusal and the look holds off; the `direction` job and `scripts/fast_lane_report.py` report the drift fit and the
same-risk buy-and-hold), a one-structure Probe within 10% of E, at most 3 Probe positions, a $400 Probe loss budget,
same-minute entry and D5 demotion by live results. **The money digest moves** `42c4a3af` -> `da5c7542` (constitution
`595228a6` -> `5edc8956`): the standing grant re-ratifies at the House's start on the owner's deploy. **An evidence
reset**: league/live changes, so the execution fingerprint moves `ba60c473` -> `b4c34031`; no family is banded. The
benchmark is [docs/benchmarks/FAST_LANE_SCREEN_1.md](docs/benchmarks/FAST_LANE_SCREEN_1.md); the deploy's steps and the
stated consequences are in [docs/operations.md](docs/operations.md) ("Fast lane v2").

Its review's fixes (Oct 7): the Probe loss budget counts realized Probe losses GROSS, from positions a Probe family
opened (marked at the order), so a Sized gain or a Probe gain never refills it, and a lost open counts until it is
found (it had netted every `:r` close, Sized included); tuition sends one structure only within the Probe's cap, and
its reach (real 1-lots before the look, up to $300 a week) is stated; C3 keeps its trigger (a Sized family at a
Probe-sized stake under the Probe's limits); the practice caps and the grant's $100 smallest stake stay as they were; a
program a paid review or audit failed is closed unpaid after the deploy's adoption (`Gate.paid_verdict`); the
`direction` job's failure is a failed receipt, and at a House start the grant runs first (same-instant jobs in the
registry's order); a new `fast_lane` job writes the report daily, read-only, with contamination measured (head against
tail per look, pooled, and live against holdout); the adaptive-search ceiling (20-38% for a persistent no-edge lineage
with 3 looks) and the benchmark's history are stated.

#### The self-running release: the improvers

The House's weekly post-mortem (`v3/b4`) and the engineer with its reviewer (`v3/b5`), ported onto `research/restart-1007`
(budget rule v2). The post-mortem: Saturdays 14:00Z, at most $1 a week of Claude, a private report and a public page
under `docs/runs/desk/`. The engineer: on by `policy.json` `engineer.enabled`, at most $4 a UTC day of Claude, one
candidate in flight, research-class only (the modules the live path loads are held, by the House and by the gateway's
`ENGINEER_HELD`), merges only through the gateway's walls (green CI, a recorded review, two a day, no protected path),
closes its own superseded and unmerged pull requests through `POST /v1/github/close`, authors at most once a UTC day,
main's head as its base after an owner deploy of it.
Both are under `league/ops/`, so both are an owner deploy. Off without a deploy: the box's `swarm.json`
`{"engineer": {"enabled": false}}`; ops.json `{"jobs": {"postmortem": {"enabled": false}}}`. Detail: operations,
**The improvers**.

#### The self-running release: the stall alarm and the funnel

The owner's goal of Oct 7, items 3 and 6. A new House job `stall` (`league/ops/stall.py`, every 30 minutes at :20 and
:50, read-only, a maintenance pause included) names a stall by its cause: no birth in 12 h under the population
ceiling, fewer than 10 Gym runs in 6 h, no Validation verdict in 24 h while a family is owed one, the Sail guard braked
12 of 24 h, a meter under 3 days of research at the ceiling, main and the running release differing in what only the
owner deploys, a pause left on 6 h, a refused grant, or the kill switch on. One `stall` mail lists every cause (the
numbers, how long, what the House is doing, the owner steps first or that nothing needs the owner): at once and every
12 h while one needs the owner, else at most once a day; each cause is also a House warning every 12 h; it never acts.
The daily page gains the Funnel table (last 24 h and since the release: `league/ops/funnel.py`). The job runner counts
a job or trigger a release adds from the deploy (`first_seen`), so `stall` and the engineer's :40 are never reported
`missed` for the days before. The gateway composes the new `stall` kind on `/v1/notify` and dedupes it by its owner
causes for 12 h (`stall:info` 24 h) inside the day's cap: deploy the gateway first (an older gateway answers 400, which
the job records and warns of).
Owner deploy (`league/ops/`); off without one: ops.json `{"jobs": {"stall": {"enabled": false}}}`. Detail: operations,
**The stall alarm and the funnel**.

### 16:02-16:14Z, the research restart: House release `20261007T160204Z-31d63e37434e` (main `ab6c0c6a`; PR #505)

Budget rule version 2 (the owner's $25 a day ceiling, Sail 0.6 / Claude 0.4, one 5-day runway term) and the F1 research fixes on V3-A. Money digest `42c4a3af`, constitution `595228a6` and the execution fingerprint unchanged: no ratification, no evidence reset. CI green on the exact head `763f9e57`; no order in flight; PROMOTED 16:03:30Z; budget job run by hand at 16:14Z (research $25.00 a day: Sail $15, Claude $10).

### Operator changes, no deploy (`swarm.json`, Oct 7-8)

- 15:44Z `live.calibration` false (the House's calibration round trips: about $12 a session for data no code reads).
- 15:53Z `tournament.drift_screen` false; `architect.cell_yield` true; `architect.max_rebirths_per_cell` 12; agenda v17.
- 16:13Z `gym.max_boxes` 5, `tournament.retire_revisions` 100, `claude.role_usd_day.diagnostician` 0, `researcher.sail_usd_per_hour` 1.0, `architect.every_seconds` 1800.
- 18:44Z agenda v18 (the edge census's STOP and TARGET cells); 19:35Z `researcher.claude_top` 3, `claude.role_usd_day.researcher` 4, `strategist` 2 (a Claude researcher A/B).
- 19:27Z four near-miss validated programs revived (`operator-revive`); two looked and failed, one retired, one validated.
- 22:00Z and Oct 8 06:30Z pacing for 24/7 inside the Sail line: `gym.max_boxes` 2 then 1, `researcher.sail_usd_per_hour` 0.5 then 0.2.

## 2026-10-03

### 08:49Z, V3-A part 1: House release `20261003T084912Z-be16b05904ff` (main `266e6861`; PR #489), gateway `e95a2d4a`, evidence reset 3

LTCM v3's first release, the one that lets the desk run unattended
([the run record](docs/runs/2026-10-02-unattended-desk.md) has the why and the owner's six decisions). It is **live**:
the owner's deploy on Saturday Oct 3, outside a session, promoted 08:49:56Z. This entry says what the release contains
and ends with the deploy's record. It carries
WP1-WP5, WP8, WP8b and WP9 with their review fixes, the four integration lenses (ops, money, deploy, contract), the
settings migration, the fixes for the causes of the integrated head's CI failures, the canary fix the rollback
rehearsal called for (the entry below), main and the docs pass. It moves the evaluator's fingerprint and carries
money-path changes, so it shipped by a planned owner deploy outside a session.

Money digest `42c4a3af`, unchanged (the constitution is untouched, `digest()` equals `PINNED_DIGEST`): no digest
ratification. **Evidence reset 3** at the deploy: `league/live/` changes, so the execution fingerprint moved
`47587e22…` → `ba60c473…`; the Gym's image and bundle are unchanged. Every practice cohort ended (nine), and a
(family, version) that had a cohort does not practise again: practice refills only from new versions. The forward
ladder and the credit types are not in it (**Not yet deployed**, above).

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
- **From main** (ahead of the release before by docs and by two changes inside the release bundle, both of Oct 2):
  comment-only edits (the Oct 2 pause refresh: no behaviour change, verified by an AST comparison) and a prune of dead
  files from the Kalshi era and the first run (`scripts/jev_lab_eval/`,
  `scripts/{attribute_fills,repair_leg_fills,repair_no_fills,survey_kalshi}.py`, `deploy/ltcm.service` and
  `league/FEEDS.md`: nothing imports or runs them, and they stay readable at tag `archive/pre-options-2026-09-26`).
  The comment edits touch modules the live path loads, so they shipped in the money path's window.
- **The canary fix** (`league/house.py` `_expedition_notices`, commit `0c8e8107`; three tests in
  `league/tests/test_pacer.py`): the calendar ending the old League's expedition is a warning, not an error; a budget
  spent before its last day is still an error. Without it no release could pass its canary from 00:00Z Oct 3 (the
  entry below has the finding).
- **Docs:** [the run record](docs/runs/2026-10-02-unattended-desk.md), [docs/runs/desk/](docs/runs/desk/README.md),
  operations (**Now**, **Running unattended**, the release checklist, **Roll back**), design and README.

**The deploy's record** (Oct 3, UTC; writing it is a docs-only merge by hand, which changes no release, holds nothing
and needs no deploy). The order followed: the rollback rehearsed on production first (the entry below), CI green on
the exact head, the merge, the gateway with its own rollback rehearsed, the House, the checks, criterion 1.
- **The tree.** CI green on the exact head `0c8e8107` (run 37109800144, 08:44:41Z: the `gateway`, `tests (3.11)` and
  `tests (3.14)` jobs). PR #489 merged at 08:45:39Z as the merge commit `266e6861`, whose whole tree equals the tested
  head's; CI on the merge commit passed too (push run 37110781254).
  - On that commit: the tree `floor_box.py` packs (941 files, bundle `be16b05904ff`) and the updater's unpack of the
    commit have one tree digest (`d817cbf1…`); `digest()` equals `PINNED_DIGEST`; the money digest is `42c4a3af`; the
    execution fingerprint is `ba60c473…`; `auto_update` is true.
  - The settings: the box's `swarm.json` at 08:45Z was JSON-equal to the copy `policy.json` was cut from, and the
    dry-run migration changed exactly the four expected keys.
- **The gateway first: `e95a2d4a`,** deployed at 08:46Z from the merge commit with `npx wrangler@4.129.1 deploy`, after
  404 of 404 tests on Node 26 and on Node 24. The version serves 100%.
  - `/v1/health` answers ok with `autonomy` and `admin_log` present; the kill switch stayed false and the caps are
    unchanged.
  - Read from the deployed version: `OPTION_STRUCTURES_REAL` is the four debit types, `LOW_BALANCE_USD` 25,
    `CRITICAL_BALANCE_USD` 12.
  - Its own rollback was rehearsed at 08:47-08:48Z: back to `4471596a` (16 keys in `/v1/health`), then to `e95a2d4a`
    again (18 keys). The rollback target is `4471596a`.
  - The old House ran healthy on the new gateway before its own deploy (`failures` [], 9 instances).
- **The House.** The nightly daemon was stopped while idle (`nightly.stop`, the lock free). `floor_box.py deploy` from
  the deploy checkout at the merge commit: the canary passed, the release was promoted at 08:49:56Z, the ten-minute
  watch was clean, the verdict was PROMOTED and the deploy exited 0. The rollback target (`previous`) is
  `20261002T112610Z-e11710692569`. `nightly.stop` was removed and the daemon came back; the harness observer was
  re-pointed to the merge commit and its tree digest. The full `swarm.json` stays on the box, untouched.
- **The checks** (09:00-09:01Z, read-only).
  - Health: the new release id, `real_money` true, `failures` [], nothing in `stopped_because`, the session closed (a
    Saturday); an `ops` block with one job due and one ok, none failed or missed (the runner installed at 08:50:29Z).
  - The standing grant: its start receipt is ok. It ratified once, on its first look, with the trigger `deposit`:
    deposits that landed before the last pin, seen for the first time by the job's new record of deposits (the one
    extra ratification [operations](docs/operations.md), "The standing grant", says a first run may make). The digest
    is `42c4a3af` and the capital is the account's equity, under the ceiling. The looks after it answer `none`, and
    `blocked` reads null.
  - Evidence reset 3: `research_evaluator.execution` is `ba60c473…`, the head's; 13 `evaluator_adopted` events at
    08:50:34Z, one per alive family; all nine practice cohorts `complete: evaluator changed`.
  - The jobs: a registry of 11; `scripts/desk_receipts.py` reads `latest.json` through the Files API with no exec.
  - The budget: no `budget.json` until the first run at 00:30Z, so the floor is in force ($3 a day of Sail research,
    $2 of Claude). The knobs are applied: the researchers' Sail pace $0.05 an hour, the population's ceiling and start
    12, the architect every 14,400 s, OpenAI's cap 0. The Sail guard's cap comes from the budget, and it is not braked.
  - The updater: built; its first look came at the first tick, with no alert and no deploy row; the train is 4 hours
    and its hold reads "no release within 30 minutes of a start".
  - The operator's pre-open check, told the new release and gateway: 9 of 10 PASS. The one FAIL was named before the
    run: check 6 (bands), "observe rows 0", because the evidence reset cleared every family's selection.
- **Criterion 1 on the new release** (09:01-09:02Z).
  - `floor_box.py stop` (the loop quiesced in 5 s), then `start`: health fresh on the new release, `real_money` true,
    `failures` [], `ops` present, a new `grant` receipt, and the swarm's heartbeat fresh 16 s after the start.
  - The swarm process killed: a new one, recovered in 16 s, with 13 families alive and the same count of runs before
    and after.
  - After a restart outside the session, `options_live.blocked` reads "the account could not be read this minute"
    until the live path's next quiet pass: off-session it reads the account every 15 minutes. It cleared at 09:14Z. The
    release before behaved the same.
  - The tuition instance is still exit-only.
- **By itself from here.** The `grant` job hourly at :05; `scoreboard` at 23:30Z (the first daily page, a docs commit
  to main through the gateway); `budget` at 00:30Z (the first `budget.json`, then the `funding` notices); `hygiene` at
  02:00Z. The first drills are due the same day, at 15:00Z and 17:00Z: two test `funding` mails, a failed Sail read,
  a gateway outage, a killed swarm, and the rollback drill (a broken copy promoted and rolled back by the watch: two
  House restarts). Until Monday's close each budget run raises one warning, "no close economics summary yet".
- **What it does not do yet.** Practice is empty until new versions qualify on the new evaluator or the ladder release
  lands. The forward ladder (its design frozen, its confirmation not yet run) and research v3 are not in this release.

### 08:23-08:41Z, the rollback rehearsal: House release `20261003T082921Z-f313be66cb82` (main `d0a2d01b` plus one fix), promoted 08:30Z and rolled back

Before V3-A part 1 shipped, the way back was rehearsed on production: deploy main as it stood, watch it, roll it back.
Main then was `d0a2d01b`, ahead of the running release by docs, comment-only edits and the dead-file prune. The
rehearsal found that no release could land at all.

- **08:23Z, the blocker.** `floor_box.py deploy` of main `d0a2d01b` alone was refused by the canary (exit 2, production
  untouched): "2 error alert(s) ... The expedition's Sail spending has stopped: day 14 is over".
  - The old League's fourteen-day expedition (the constitution's `budgets.expedition`, from Sept 19) ended at 00:00Z
    Oct 3.
  - A canary is a fresh House with nothing told yet, so it tells the run's scheduled end on its first tick. It told it
    as an error, and the watchdog refuses any unmarked error in a canary.
  - So from 00:00Z Oct 3 every canary was refused and no release of any kind could land: not V3-A, not a re-deploy of
    a rollback target, not an updater release, not the rollback drill.
- **The fix** (commit `0c8e8107`, `league/house.py` `_expedition_notices`): the calendar ending the run is a warning; a
  budget spent before its last day is still an error. Its three tests (`league/tests/test_pacer.py`: the notice's level
  in both cases, and a fresh House after the expedition reading healthy to the watchdog) fail on the old code with the
  refusal's own words. It reached main in PR #489.
- **08:28-08:41Z, the rehearsal, on main plus that one fix** (a local cherry-pick onto `d0a2d01b`, not pushed: the
  running release's money digest `42c4a3af` and execution fingerprint `47587e22…`, so no evidence reset, and
  `auto_update` false; 209 tests of the pacer, the watchdog and the House pass on Python 3.11 and 3.14).
  - The nightly daemon was stopped while idle; the lock was free 20 s later.
  - `floor_box.py deploy`: release `20261003T082921Z-f313be66cb82`, the canary passed, promoted at 08:30:04Z, the
    ten-minute watch clean, PROMOTED and exit 0 at 08:40Z, with `previous` the Oct 2 release.
  - `floor_box.py rollback --reason "rehearsal before V3-A"`, with no force flag: the real-book guard passed (the
    previous release manages the real book) and the rollback exited 0 in 4 s.
- **The restored release, verified at 08:41Z:** `current` was `20261002T112610Z-e11710692569` and `previous` empty;
  health was fresh on it, `real_money` true, `failures` []; the research evaluator was unchanged (no adoption event)
  and the same nine practice cohorts were active; there was no new grant ratification; `swarm.json` and the harness
  observer's runtime file were unchanged; `nightly.stop` was removed; a `deploy` at `e3d0111f` answered "nothing to
  deploy"; the operator's pre-open check was 9 of 9 PASS.
- **A side effect to know:** each swarm restart lifts the families' holds. In the cycles after the rehearsal's two
  restarts three families retired themselves (self-refuted by their researchers, 08:30Z and 08:41Z), which left 13
  alive.

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
