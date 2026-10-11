# Release E4 "breadth": the contract between its packages

Release E4 adds the PANEL lane: programs that pick 5 to 12 names out of the day's S&P 500 members by a symmetric
cross-sectional rule, see salted slots with no ticker and no date, and are judged on their daily RESIDUAL against
matched placebo portfolios by the screen XS1. This file is what every package builds against. Step 0 created every
new module as an importable stub with its public names, the shared dataclasses and constants, and the one table's DDL;
`league/tests/test_e4_stubs.py` holds them still. A stub's body raises `NotImplementedError` until its owner lands it.

Base: commit 0e8bbaa7 (E1's share lane and E2's births, integrated). E1 and E2 were still receiving review fixes when
this was written: build against what the base has, and anchor every patch by statement, never by line.

**Authority, in order.** The captain's amendments (A1-A22) and his rulings on this build (section 3); the pinned
pre-registration XSCREEN-1, revision 2 (sha256 c46aec17..., pinned 2026-10-11 03:03:08Z), WHERE IT SPEAKS (section 4),
with its study's implementer's rule (HOUSE-RULE-XS1) and receipt; the build spec E4-SPEC revision 2; the roadmap; the
design. The spec and the pre-registration were revised in parallel without seeing each other. Where they disagree on
the program contract and inputs, the residual and its cells, the stress leg, the House exit law, the gate, the
lineage rule or the forward checkpoints, THE PRE-REGISTRATION WINS, and the stubs already say what it says. Where
the spec names existing code and the code differs, THE CODE WINS (section 5).

**THE STUDY IS DONE** (2026-10-11 07:00Z): XS1 is ADOPTED by its own mechanical rule, at rung R0. Its receipt
(`equity_screen_xs_1.json`, sha256 98acbb83ffec165dcd4e831a6d5f123b99a6bc5c4ca3acb114e75782555e52e3) is copied
VERBATIM to `docs/benchmarks/equity_screen_xs_1.json` and pinned in policy.json `elane.screens.equity_xs` BY THE
INTEGRATOR, in one commit, so the tree never holds a receipt without its pin. The captain may later replace it with
a rebuilt receipt at another c_XS: READ EVERY THRESHOLD FROM THE RECEIPT AT RUNTIME, NEVER WRITE ONE IN CODE OR IN A
TEST (a test that needs a figure reads the file, or the fake). Until the pin lands, a screen with no pinned receipt
refuses every program. The captain's amendment A22 came with the study's review: section 4a.

**Rules for every package.** The repository is public: no market data, no price or return of a real year, no census
figure, no per-program outcome, no membership history (the point-in-time table lives on the House only; the one
committed list is the dateless tradable union). Tests use `league.xs.synth` and `league.equity.synth` stores and
fixtures marked fake. No push, no pull request, no deploy; no contact with the House, Sail, Alpaca, the gateway or a
broker; no secret or env file read. Edit NOTHING under `league/live/`, `league/gym/`, `gateway/`, in the 4
`LEAGUE_FILES`, or in an evidence module of league/equity (`evaluator.EQUITY_EVIDENCE`). Edit an existing file only
through your own patch file (section 2). Standard library and numpy only; nothing may depend on a numpy routine whose
stream differs by version. `league/xs/` stays FLAT. Every statistic uses `math.fsum` (the CI runs Python 3.11 and
3.14 and the built-in `sum` is not the same sum on both); every new test passes on both. One test process at a time.

## 1. The package split: who owns which file

Each file has ONE owner. NEW files in **bold**. Eight packages are built now: A, B, C (C0 is its first commit and
merges first), D, E, G, H and I. Package F (the screen's study XSCREEN-1) is a separate team's private work and is not
in this build. Package J (the forward twin) waits for release E3: it is OWED (section 3).

| key | owns (new files) | existing files it changes at integration (through `league/swarm/e4_patches/<key>.md`) |
|---|---|---|
| A data | **`scripts/panel_probe.py`** (step -1's coverage probe: BUILT at Step 0, A owns it from here), **`league/ops/equity_universe.py`**, **`league/ops/equity_panel.py`**; tests **`league/tests/test_panel_probe.py`** (written at Step 0), **`test_equity_universe.py`**, **`test_equity_panel.py`** | `league/ops/registry.py` (the six job rows) |
| B costs and counts | **`league/ops/equity_spreads.py`**, **`league/ops/equity_neff.py`**, **`league/ops/french.py`**; tests **`test_equity_spreads.py`**, **`test_equity_neff.py`**, **`test_french.py`** | `league/ops/funnel.py` (independent asset-years), `league/ops/twins.py` (a panel lot's half-spread); after release E3 and never before: `league/ops/contam_probe.py` |
| C xs core | C0, merged first and alone: **`league/xs/config.py`** whole and **`league/xs/store.py`**'s writer (`write_panel`, the layout, the 2020 refusal) with **`test_xs_store.py`**'s writer tests. Then the rest of `store.py`, **`ctx.py`**, **`program.py`**, **`synth.py`**, **`XS.md`** (the contract shown to authors), `league/xs/__init__.py`; tests **`test_xs_ctx.py`**, **`test_xs_program.py`**, **`test_xs_seal.py`** | none |
| D xs engine | **`league/xs/engine.py`**, **`results.py`**, **`placebo.py`**, **`runner.py`**, `league/xs/child.py` (the A13 stub, now written); tests **`test_xs_engine.py`**, **`test_xs_placebo.py`**, **`test_xs_runner.py`**, **`test_xs_i6.py`** | `league/tests/test_equity_decider.py` (the panel kind now serves five ops) |
| E xs screen | **`league/xs/screen.py`**, **`league/xs/identity.py`**, **`league/xs/style.py`** (A22: the style reading and its rule); fixtures **`league/tests/fixtures/equity_screen_xs_fake.json`** (shaped as the real receipt: `screen.RECEIPT_KEYS`) and **`league/tests/fixtures/xs1_conformance_c.json`** (A22 (4): the ninth vector, by hand); tests **`test_xs_screen.py`**, **`test_xs_identity.py`**, **`test_xs_style.py`** | `league/swarm/evaluator.py` (`adopt_xs`; `adopt_equity` skips panel families) |
| G swarm | **`league/swarm/elane_xs.py`**, **`league/ops/xs_zero_edge.py`**, **`league/swarm/E4.md`**; tests **`test_elane_xs.py`**, **`test_elane_xs_bar.py`**, **`test_elane_xs_seal.py`**, **`test_xs_zero_edge.py`** | `league/swarm/store.py`, `bands.py`, `elane.py`, `cards.py`, `dlane.py` (one structure literal), `elane_births.py`, `elane_train.py`, `elane_seal.py`, `elane_yield.py`, `settings.py`, `policy.json`, `loop.py` |
| H live | **`league/xs/book.py`**; tests **`test_xs_book.py`**, **`test_equity_book_panel.py`** | `league/equity/kinds.py` (`BOOKS`, `book_for`, `kind_of`), `league/equity/live.py` (B1-B15 less B7 and B12, ONE patch), `league/ops/dlane_report.py` (a panel close's lines) |
| I money and universe | **`scripts/gen_universe.py`**; tests **`league/tests/test_gen_universe.py`** | R-E4a: `league/ci.py` and `league/tests/test_ci.py` (protected paths; `stock_agreement` names at most 10 tickers a side), `docs/operations.md`, `CHANGELOG.md`. R-E4b, THE UNIVERSE (moves the money digest; deployed separately): `league/constitution.py`, `league/tests/test_equity_money.py`, `league/ops/preopen.py`, and the gateway's `gateway/lib/caps.mjs` and `gateway/test/stock-buys.test.mjs` AS A PATCH FILE in the captain's scratch, never an edit of `gateway/` |
| J forward (OWED) | **`league/ops/forward_xs.py`** (a stub exists); tests **`test_forward_xs.py`**, **`test_forward_xs_twin.py`** | E3's seven forward modules, after E3 is merged |
| the integrator | `league/xs/E4_INTERFACES.md` (this file), `league/tests/test_e4_stubs.py`, `league/swarm/e4_patches/README.md`, the study's fixtures `league/tests/fixtures/xs1_conformance.json` and `xs1_conformance_inputs.npz` (read by D and E, edited by no one), `docs/benchmarks/equity_screen_xs_1.json` (the receipt, verbatim) | applies every patch file, in `README.md`'s order; then fills policy.json's `elane.screens.equity_xs` from the receipt (`screen.PIN_SOURCES`) in the commit that lands the receipt; `league/tests/test_equity_isolation.py` (the A13 slot test, changed at Step 0: the package is flat and keeps its child) |

Files no package edits: `league/live/**`, `league/gym/**`, `gateway/**`, the evidence modules of league/equity,
`league/equity/INTERFACES.md`, `docs/benchmarks/equity_screen_2.json`, `league/ops/equity_data.py`, anything under
`<state>`. `docs/benchmarks/equity_screen_xs_1.json` is the study's receipt: the integrator lands it, no package
writes or edits it.

No path is in two rows. A package that needs a change to a file it does not own asks its owner (a line in its
report), or the integrator when the file is a shared shape of section 6.

**Merge order on green CI: C0, A, B, C, D, E, G, H, then I.** C0 first because A is built on it; A second because its
coverage verdict is the fact the release rests on. Package I's constitution change is ONE separate commit, marked
"UNIVERSE (moves the money digest; deployed separately)", made LAST by the integrator.

## 2. Patches to existing files

A change to a file that existed before E4 is written by its E4 author into that author's OWN file
`league/swarm/e4_patches/<key>.md`, as an exact unified diff against the integration head with the test that holds
it, and applied by the integrator in the order of `league/swarm/e4_patches/README.md` (which lists all eighteen).
Seven authors appending to one file from seven worktrees would conflict at every merge; one file an author cannot.

## 3. The captain's rulings on this build (binding)

1. **Package F is not built here.** A separate team ran XSCREEN-1 from the pinned pre-registration; it is done
   (above). `league/xs/screen.py` is written from the pre-registration and the study's implementer's rule and reads
   its thresholds from the receipt at runtime. Tests use a fake receipt, and A SCREEN WITH NO PINNED RECEIPT REFUSES
   EVERY PROGRAM. THE STUDY'S CONFORMANCE VECTORS ARE IN THE TREE (section 9): `test_xs_screen.TheStudyVectors` and
   `test_xs_placebo.TheStudyVectors` reproduce all eight, and package E adds a ninth by hand (A22 (4)). The study's
   reference code is private and is not committed; neither implementation is rewritten to fit the other.
2. **Package J waits for release E3.** Its stub is kept, and the rule stands exactly as the spec has it: WHILE J IS
   NOT MERGED, OR ITS NIGHTLY RUN HAS NOT WRITTEN THE MARKER (`league.xs.book.TWINS_FILE`), `elane.panel.mode` "live"
   READS AS "gate" (`elane_xs.live_ready`). J is owed: patches 17 and 18 with it.
3. **Package I is built, and no builder edits `gateway/`.** Its gateway changes are a patch file with their tests'
   expected results; its constitution change is one separate commit made last.
4. **A17 is granted.** For a panel program, a hold-day fetch failure of a held name is an alarm and never counts
   toward A8.5's two-failed-decides exit; a failed decide on a rebalance day still counts.
   `league.xs.book.HOLD_DAY_FAILS_EXIT` is False.
5. **Step -1's probe is built at Step 0** (`scripts/panel_probe.py`): read-only, its only request a bars GET through
   the House's own gateway client, counts and coverage shares out, never a price. So it does NOT use the web reader:
   the spell file is a local path, and the facts that need the reader, quotes or assets (the spec's facts 2, 3 and 4)
   are stated "not probed" in its receipt. Package A's jobs verify them.

## 4. Where the pinned pre-registration overrides the spec

The stubs' docstrings are already written to these. Each line: the spec's text, what binds instead, where it lives.

| the spec said | what binds (the pre-registration's section) | where |
|---|---|---|
| D4: eligible = member at t, a valid bar, 60 valid closes of 253 | **U(d)** (3.1): member on d, d + 1 AND d + 2; a valid close on d and d - 1; the class of the month; the three characteristics exist (so 253 sessions of history). The House adds tradable and unmasked (narrower) | `store.PanelBars.elig0`, `ctx.Derived.elig`, `config.MEMBER_AHEAD` |
| D6: beta and sector need 60 valid days; sector = the highest correlation of raw returns | **at least 200 valid returns** (3.2); sector = the fund whose MARKET-RESIDUAL returns correlate most with the name's; the funds in the order XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV, XLY, XLRE, XLC | `config.MIN_VALID`, `config.FUNDS`, `ctx.derive` |
| D6: nested terciles, mt = 3 for a missing momentum | **the cells of 3.3**: (beta groups, momentum groups) by the sector's eligible count ((3, 3) from 45, (2, 2) from 20, (1, 2) from 10, (1, 1) from 5), a pooled "small" cell for sectors under 5; a name with no momentum is not eligible. Cell id = 100 x sector + 10 x beta group + momentum group; small = 9999 | `config.RUNGS`, `SMALL_CELL`, `CELL_SECTOR`, `CELL_BETA`; `ctx.Derived.bg`, `mg`, `cell` |
| D7: the ctx carries normalised open, high, low, close arrays, `rvol`, event flags | **the contract C1**: `ret`, `oret`, `iret`, `range`, `rel_volume` (6 decimals), `sector`, `beta` (2 decimals), the same five for the market; `weekday`, `session_of_month`, `sessions_left_in_month`, `last_session_of_week`. NO price array, NO event flag, no size or liquidity handle. The spec's DITHER stays, underneath (it only adds noise: narrower, never wider), AS PACKAGE C BUILT IT (section 8, points 18-21): on the ADJUSTED price's own cent grid, with no as-of product | `ctx.XsCtx.__slots__`, `ctx.FIELDS`, `config.DITHER_HALF`, `BETA_PLACES` |
| D10: top-ups at a 25% shortfall; orders past 24 dropped one by one | **THE KEEP RULE** (C3): a held name in the target is kept, no trade and no resize; a name not held is bought as ONE lot of w x E0; at most 12 buys and 12 sells, and a target that needs more is REFUSED WHOLE (a hold) | `engine.plan_orders`, `config.MAX_BUYS`, `MAX_SELLS` |
| D11: the Gym sleeve is $500; a name's half-spread is at least 1 bp | **E0 = $1,000** (C3, C8: E1's `SLEEVE_USD`; the stress leg charges the smaller live sleeve's fee instead); **never under 3 bp a fill** (C5) | `config.XS_SLEEVE_USD`, `HS_FLOOR_BP` |
| D12: a vanished name whose spell ended by a deal takes no haircut | **one exit law** (C6, 3.5, 5.5): a name out of U at any close is sold at the next open; a name whose bars end exits at its last close x (1 - 0.30), for the lot, its counterparts and its cell's members ALIKE. How a spell ended is counted beside, and sets no price | `engine` (module docstring), `config.VANISH_*`, `store.PanelBars.exit` |
| D13: x = the cash book's return minus a sector basket's dollars | **the residual of 3.4**: E1's constant-weight accounting on E0; x = r - B, B the cost-free mean of each lot's CELL (fixed at its decision, the exit law applied to every member); the stress residual **x15 = x - 0.5 s - f**; the universe excess **u** (4.6: one cell, all of U) | `placebo.residual`, `placebo.SERIES`, `results.DAILY`, `config.STRESS_*` |
| D14: 1,000 placebos, one generator a placebo, a draw by `floor(u x m)` | **the law of 3.5**: one `default_rng(seed)` a run; per decision and cell one `rng.random((draws, len(C)))`, keys of members the draw holds raised by 2, the smallest keys win; **999 draws**; the look's seed from sha256("XS1\|receipt sha\|code sha\|placebo"); p_plac = (1 + count) / 1000 | `placebo.run`, `look_seed`, `DRAWS` |
| 9.1: pass = pre-check AND sum x > 0 AND t >= c_used AND p_plac <= 0.10; the floor is `floor_s2` at L 194 and 251 | **the gate of 4.3-4.4**: pre-check AND sum_H x > 1e-12 AND **sum_H x15 > 1e-12** AND t_H >= c_used AND **p_plac <= 0.12** (count <= 119 of 999); c_used = max(c_XS, c_p + 0.05); the own floor at **L 194 only**, cells: both pools together (each at least 251), each pool of at least 550 alone | `screen` (module docstring), `screen.PLACEBO_COUNT_MAX`, `MIN_POOL_*` |
| 8.4: the look's run is the holdout's, as E1's | **one run from Validation's first session through the holdout** (4.1); the series is cut in two | `runner.Isolated.look`, `store.WINDOWS`, `screen.split` |
| 9.2: `ReceiptXS(... n_placebo, strata, c_XS_floor, c_XS_margin ...)`, alpha at most 0.10, at least 1,000 placebos | **the receipt of 10.1**: `c_XS`, `c_margin`, `alpha_plac` 0.12, `placebo_draws` 999, the rung (R0, or R1 when the ladder fell back; R2 and R3 are never adopted), the flags and the screen's flags, the sentence | `screen.ReceiptXS`, `RECEIPT_KEYS`, `PIN_KEYS`, `elane_xs.SCREEN_NULLS` |
| D22: the same lineage = a 0.7 correlation of the Train x with a program looked at, or the template; E1's retry rule | **4.6**: the template, or 0.7 or more in the residual x OR in the universe excess u, against a program looked at OR refused at the pre-check; **no Validation-only retry**; an XS1 lineage takes no S2 look and the reverse | `screen.same_lineage`, `retry_permitted`, `elane_xs.same_lineage`, `TRAIN_U_KEY`, `PRECHECK_KEY` |
| 9.1 (4): the sentence's fields | **the sentence of 10.2**, its placeholders {c_used}, {c_p}, {own_fp}, {n_cell}, {basket}, {label}, {flags} | `screen.BESIDE_FIELDS`, `screen.beside_line` |
| 10.6: a panel row's forward route | **the checkpoints of section 11**: 20, 60, 120 and 250 forward sessions; pass = t_n >= c_FX AND sum x > 0 AND sum x15 > 0 AND the placebo rank <= alpha_f (0.12 fresh, 0.03 after an XS1 look) | `screen.CHECKPOINTS`, `ALPHA_F`; package J (owed) |

**The receipt as built** agrees with the stubs: its keys are `screen.RECEIPT_KEYS` and two more (`eligibility`,
`beside_calibrated_reading`: the loader lets a receipt carry more, and refuses one that lacks a key); its sentence's
placeholders are `screen.BESIDE_FIELDS`; its policy pin is `screen.PIN_KEYS` (`validation_tries` and `holdout_looks`
among them, each read from the place `screen.PIN_SOURCES` names); the cell id is 100 x sector + 10 x beta group +
momentum group, 9999 for the pooled cell (`config.CELL_SECTOR`, `CELL_BETA`, `SMALL_CELL`); the floor's cells are
named "both", "D" and "C" (`screen.FLOOR_CELLS`). On the House's two Train segments (754 and 753 sessions) all three
floor cells exist; the study's worlds had the first two.

**The duties the pre-registration gives the House** (package G keeps them; `elane_xs`'s module docstring):
1. keep BOTH Train series (the residual x and the universe excess u, by session) of every program that reaches the
   pre-check, passed or refused: `elane_xs.TRAIN_X_KEY`, `TRAIN_U_KEY`, with `PRECHECK_KEY`;
2. count the XS1 looks of each agenda cell: `elane_xs.cell_looks`;
3. state beside EVERY live panel trade the sentence its receipt fixes: recorded with the look
   (`elane_xs.LOOK_KEY`), handed out by `elane_xs.beside_line`, printed by package H's report patch.

**What the pre-registration leaves to this build** (its DR6), so the spec stands: the Train bar equity-xs-v1 (it now
reads the residual of 3.4 and ranks against `placebo.stat` under `placebo.train_seed`), the spreads job, the universe
deploy, the switch, sizing and the live rules by close date. And the spec's STANDING TARGET (a buy live could not make
is planned again each close until the next called decision): the pre-registration is silent on it; it is kept, and
such a buy is a lot with its own decision day and cell.

## 4a. The captain's A22: what the House holds before any real money on an XS1 pass (binding)

From the study's review. The receipt is pinned as built; these four are HOUSE rules, and the contract carries them.

| A22 | the rule | who builds what |
|---|---|---|
| (1) | **A STYLE-OPEN PROGRAM TAKES NO LIVE SEAT ON AN XS1 PASS ALONE.** The House computes each panel program's loadings on size, beta, 12-1 momentum and volatility from its Train holdings and marks it style-open by one fixed, tested rule (`league/xs/style.py`: a lot's rank among the day's eligible names at its decision close; a program's loading is the mean over its Train lots weighted by dollars and by the sessions each lot was HELD (the review's fix: by entry weight alone a tilted core held long beside a churned counter-tilt read not open); style-open when any |loading| is at least `style.TILT`, or when fewer than `style.MIN_LOTS` lots could be read). A style-open passer is RECORDED AND SHADOWED, NEVER SEATED: it takes no band and no proof | E: `style.py` whole and `test_xs_style.py` (the rule on hand-built holdings: a uniform picker is not open, a top-third and a bottom-third picker of each characteristic are, a tilted core held sixty sessions beside a weekly counter-tilted satellite is, too few lots is, a malformed reading is). D: `engine.run(..., style=True)` and `runner.Isolated.train(..., style=True)` put `style.block(bars, log)` in the result: one call. G: `score` asks the seen spans' full-universe k 1.0 runs for it and keeps `style.style_open(style.pooled(blocks))` in the Train record (`elane_xs.STYLE_FIELD`); `look` seats a passer only when `style.seat_refusal(elane_xs.style_of(fam))` is None, else records the pass with `seat` "style-open" and gives no band. H: the report's panel lines name every recorded style-open passer and why (patch 13) |
| (2) | **At most 2 XS1 looks an agenda cell** until a forward verdict exists in that cell (`elane_xs.MAX_CELL_LOOKS`, `look_room`). No forward verdict can exist before the forward route is measured, so the cap is flat in this release. A look the cap holds back is not spent | G |
| (3) | **The equity code review (no embedded return table, no calendar recognition) and the contamination probe run BEFORE a panel look.** The review's rubric for a panel program is `elane_xs.REVIEW_XS` (G's patch 7). The probe is release E3's (`league/ops/contam_probe.py`) with the panel strata P4-P6 of patch 18: `elane_xs.probed` holds a look back until the route that wrote the program has a published result with those strata. SO NO PANEL LOOK RUNS UNTIL RELEASE E3 AND PATCH 18 ARE MERGED AND THE PROBE HAS RUN ONCE (stated in section 8) | G (`probed`, the rubric); B (patch 18, after E3) |
| (4) | **A conformance vector for the 2022-24 floor cell alone**, beside the study's eight | E (`league/tests/fixtures/xs1_conformance_c.json`, by hand; `test_xs_screen` holds `floor` to it) |

PENDING with the captain at integration: whether the House runs at the receipt as registered or at a rebuilt one with
a higher c_XS. Nothing in the build depends on the answer: every threshold is read from the pinned receipt.

## 5. Where the code at the base differs from the spec's words (the code wins)

- `league.swarm.elane.card_errors(card, structure, symbols, settings)` takes four arguments;
  `elane_xs.card_errors(card, settings)` takes two (G's dispatch adapts).
- `league.swarm.elane.same_lineage(store, fam, lane, template, train)` returns the FAMILY ID it matches or None, and
  fails closed with `LineageUnread`. `elane_xs.same_lineage` does the same (the spec said bool).
- `elane.mode` is a SETTING (`elane.MODES` = ("off", "gate"); the reader is `elane.on(settings)`). The effective panel
  mode is `elane_xs.mode`.
- E2's `cell_of(lane, agenda, symbols)` and `e2_family(fam)` live in `league/swarm/elane_train.py` (with `train_map`,
  `closed_cells` and `refuted_rows`), not in `elane_births.py`; `league/swarm/cards.py` has another `cell_of(key)`.
- `CodeRefused` is `league.gym.safety`'s (E1's `program` imports it); `NeedsRefused` is `league.equity.program`'s.
- `set_swarm.py` is the captain's own tool, not a file of the repository: a switch is a value in `<state>/swarm.json`
  over policy.json.
- `league.swarm.elane_train.restart_check(decider, code, params, *, name, streams, every, first)` resets by SESSION
  (`BAR` `state_every` 20, `state_first` 7). The panel's `elane_xs.state_check` resets by CALL (after 3, 10, 13, 20...).
- `league.swarm.bands.equity_seating(fams, seats)` has no `seatable` keyword yet (G's patch 2 adds it);
  `bands.seating` has one.
- `league.swarm.evaluator` already has `EQUITY_SELECTION_KEYS` and `EQUITY_EVIDENCE_EXTRA = ("synth",)`: the xs lists
  mirror them (`identity.XS_EVIDENCE_EXTRA`; E's `XS_SELECTION_KEYS`).
- `league.swarm.elane_seal.SEALED_KEYS` is a frozenset (G's patch 8 unions `elane_xs.SEALED`: EIGHT keys, the spec's
  six plus `elane_xs_train_u` and `elane_xs_precheck`).
- `league.equity.runner.RUN_BUDGET_SECONDS` is 1200; the panel's own is 600. E1's `Isolated` takes no `nice`.
- `league.equity.store`'s window `LOOK` is the HOLDOUT alone; the panel's "look" window starts at Validation's first
  session (section 4). The gate mark's constant is `GATE_MARK`.
- `league.equity.screen.floor_s2` reads L 194 and 251 over `S2_SETS` (the second pool alone, both together); its
  enumeration `_exact_cell` is private. The panel's floor has L 194 only and a first-pool-alone cell, so it is NOT
  `floor_s2` as it stands: package E either calls `_exact_cell` (a private E1 name: then pin it by name in
  `test_xs_identity.py` beside the three of `identity.XS_PRIVATE_E1`, and say so in its report) or writes the
  enumeration inside `league/xs/screen.py`. Either way `test_xs_screen.py` holds it to a brute-force tuple loop.
- `league.ops.equity_data.fetch(gateway, symbols, start, end, *, adjustment, timeframe)` has no `asof`:
  `equity_panel.fetch_asof` pages for itself.
- THE VENDOR'S CENTS. At this base E1's morning audit compares as-of prices on a four-decimal grid
  (`league.equity.live.VENDOR_HALF_STEP`). E1 gained the shared helper `league.equity.config.rounding_bound` AFTER this
  base (its commit 547206fa, with `engine.ratio_tolerance`). So league/xs carries ITS OWN copy, same name and figures:
  `league.xs.config.rounding_bound`, `ADJUSTED_HALF_STEP`, `ROUNDING_GUARD` (built, not a stub). Use it for every
  as-of price, split and dividend reading; the integrator makes it a re-export once E1's is in the base. A live ctx is
  not byte-identical to a later store's by assumption: the I6 tests build both sides under one vintage, and the
  nightly I6 measures the real thing.
- E3's modules (`elane_folds`, `forward_*`, `fill_minutes`, `contam_probe`) do not exist at this base: import them
  inside the function that needs them, and handle their absence (`elane_xs.assign` answers None without them).
- THE TABLES. The spec's section 4.3 has ONE new table, `eq_rebalances` in live.sqlite (`league.xs.book.SCHEMA`),
  and one new column, `eq_instances.kind`. Release E4 creates no table in forward.sqlite and no memory table:
  package J (owed) writes E3's own `fwd_` tables through E3's modules.
- `league/tests/test_equity_isolation.py` held league/xs to exactly two files ("nothing else until the panel lane is
  built"). It now holds that the package still has its `__init__` and its child, stays flat, and that no module of
  it names league.live or league.swarm.
- The integration branch moved one commit past the base while this was written (an E2 budget fix in the swarm's
  loop), and E1's branch three (the vendor's cents; the seeds' look order; the data job's audit): G's and H's anchors
  are by statement for that reason.

## 6. The shared shapes, and where each lives

| name | module (owner) | read by |
|---|---|---|
| the lane's constants; `rounding_bound`; `quiet`, `rebalance_session`, `decision_due`, `next_session` | `league/xs/config.py` (C, in C0) | every package |
| `PanelBars`, `Slice`, `PanelStore`, `Universe`, `write_panel`, `ids_for`, the layout; ADDED BY C: `valid_bars` (D4's valid bar), `coverage` (D19's block: A's `equity_panel.coverage` may be this function), `write_universe` (the universe directory's one writer: the salt written once, the manifest last), `write_panel`'s keywords `masked`, `coverage`, `vanished`, `full_at`, `revisions`, `hs_share`, `live_from`, `i6` (the manifest's other facts; each has a fail-closed default), `PanelStore.class_out(day)`, `.elig0_row(day, aids)` (a LIVE day's `Columns.elig0`), `.tradable_aids(day)`, `.live_from`, `.universe()`, `.train(..., aids=)`, `Universe.member`, `.masked`, `.left`, `.exit`, `.class_aids`, `.has` | `league/xs/store.py` (C; `write_panel` in C0) | A (writes through it), D, G, H, J |
| `XsCtx`, `Fields`, `Inputs`, `Derived`, `derive`, `build`, `ctx_bytes`; ADDED BY C: `characteristics` and `cells` (the pre-registration's 3.2 and 3.3 on plain arrays: the vector CH is held on them), `group_counts`, `dither`, `lot_dither`, `fetch_sessions`, and `build(inputs, derived=None)` (the engine hands the `Derived` it already holds) | `league/xs/ctx.py` (C) | D (engine, child, placebo), H, A (the nightly I6) |
| `Needs`, `parse_needs`, `load_program`, `normalize_target` | `league/xs/program.py` (C) | D, G, J |
| `synthetic_panel` (ADDED: `raw_places`, `masked`, `live_from`), `planted_panel`, `cent_panel`, `same_ctx_cases` (each case also carries `aids`, `run_key`, `slice`, `straddles`), `bar_rows` | `league/xs/synth.py` (C) | every package's tests |
| `EngineConfig`, `plan_orders`, `Log`, `run` | `league/xs/engine.py` (D) | the child (D), H (the same `plan_orders` live) |
| the result record, `DAILY`, `view`, `pooled`, `t_stat` | `league/xs/results.py` (D) | E, G, J |
| `residual`, `run`, `p_value`, `stat`, `look_seed`, `train_seed` | `league/xs/placebo.py` (D) | E (the look), G (the Train bar's rank) |
| `Isolated`, `Run`, `state_stream`, the run failures (E1's own classes) | `league/xs/runner.py` (D) | G, J, `xs_zero_edge` |
| `child.handle`: ops "load", "drop", "decide", "needs", "run" | `league/xs/child.py` (D) | the decider; H (the decide answer: `hold`, `target`, `at`, `orders`, `rejects`, `ineligible`, `stats`, `ctx_sha`, `failed`) |
| `ReceiptXS`, `pinned_receipt`, `series`, `split`, `precheck`, `floor`, `verdict`, `same_lineage`, `beside_line` | `league/xs/screen.py` (E) | G |
| `CHARACTERISTICS`, `TILT`, `MIN_LOTS`, `block`, `pooled`, `style_open`, `seat_refusal` (A22) | `league/xs/style.py` (E) | D (`engine.run` calls `block`), G (`score`, `look`), H (the report) |
| `xs_fingerprint`, `xs_identity`, the lists | `league/xs/identity.py` (E) | G (`bands._xs_sha`), E's `adopt_xs`, J |
| `SCHEMA` (`eq_rebalances`), `INSTANCE_KIND_DDL`, `Columns`, `Fetched`, `kept`, the twin marker's name | `league/xs/book.py` (H) | A (the nightly I6 reads the kept fetch and the table, read-only), G (`live_ready` reads the marker), J |
| the lane's settings, keys and names; `mode`, `live_ready`, `is_panel`, `seatable`, `validate`, `look`; A22's `MAX_CELL_LOOKS`, `look_room`, `probed`, `style_of`, `REVIEW_XS` | `league/swarm/elane_xs.py` (G) | G's patches; H's report (`beside_line`, `style_of`) |
| the universe files, `tradable`, the panel manifest's `coverage`, `verdict`, `hs_share`, `i6`, `live_from` | `league/ops/equity_universe.py`, `equity_panel.py` (A) | C's `Universe` and `PanelStore` read them; G's `mode`; I (tradable.json) |
| spreads.json, neff.json | `league/ops/equity_spreads.py`, `equity_neff.py` (B) | A (`hs_table`), B's funnel patch |

THE TABLE (live.sqlite; created by `EquityBook.__init__` from `league.xs.book.SCHEMA` beside E1's own): one
`eq_rebalances` row an instance and decision session; `eq_instances` gains `kind TEXT NOT NULL DEFAULT 'equity'` by a
guarded ALTER. The swarm store gains no table: family-state keys `elane_xs` (the Train record) and the eight sealed
keys of `elane_xs.SEALED`; kv `xs_evaluator`, `elane_xs_cpu`, `elane_xs_zero_edge`, `elane_xs_alerts`.

## 7. What must not move, and what is off

- E4 moves NEITHER the equity identity NOR the options execution fingerprint (A13): nothing of E4 enters league/equity's
  evidence import closure; the panel has its own identity inside league/xs (`identity.xs_fingerprint`).
  `league/xs/book.py` and `identity.py` are plumbing. H's patch to `league/equity/live.py` and `kinds.py` is plumbing.
- The money digest moves ONLY by package I's universe commit, alone, marked, deployed separately.
- Live trading of baskets is real money: every wall of E1 holds (long only, cash only, a stock at most 20% of equity,
  the shared loss budget with stocks weighing 0.40, the kill switch and the stops, never a forced or hand-placed
  trade). The panel reaches the venue only through E1's EquityBook.
- With every E4 switch off (`elane.panel.mode` "off", as policy.json ships it) nothing of E4 runs, spends or trades:
  no birth, no run, no fetch of the live path, and no data job (each answers `skipped` before its first gateway
  call: `league.ops.equity_universe.lane_off`, section 11; the jobs read only when they run).

## 8. Open points, for the captain and the integrator

Each is a place the two texts had to be reconciled at Step 0; the stub says which way it went.
1. **E0 is $1,000, not $500** (`config.XS_SLEEVE_USD`), because the pre-registered accounting and stress leg are on
   E1's Gym sleeve. Cost: a small live lot's cent fees are charged by the stress leg, not by the plain t.
2. **A name's half-spread is never under 3 bp** (`config.HS_FLOOR_BP`; the spec said 1): the registered contract
   costs every fill 3 bp and may be made narrower, never wider. Cost: up to 2 bp a side over what a liquid name pays.
3. **The standing target is kept** though the registered contract does not describe it (section 4's last paragraph).
4. **The deal exit's no-haircut rule is gone** (the registered exit law is one haircut for all). With membership read
   two sessions ahead a deal's name leaves U, and is sold, before its bars end, so the case is rare.
5. **Membership is read two sessions ahead** (`config.MEMBER_AHEAD`). The Gym reads it from the store; live knows only
   the changes the universe job has read by the decision. A change learnt late is a live-versus-Gym gap the nightly I6
   shows.
6. **Entry validity peeks one session ahead in the Gym** (a buy needs a valid close the session after its fill:
   the pre-registration's 5.3, "data validity, never a return"); live cannot. Package D counts such refusals.
7. **A program's ctx carries no event flag** (FOMC, CPI, jobs), unlike an E1 program's: the registered contract's
   calendar is four counts. G's brief and E2's review rubric for a panel program must not offer them.
8. **The cell id's formula** is now the study's own (its implementer's rule, section 2): settled.
9. **`screen.RECEIPT_KEYS`** is the pre-registration's table and the real receipt carries every key of it: settled.
10. **"Asset id" in the pre-registration's orderings is the COLUMN ORDER on the House.** Its ties (beta, then asset
    id), a cell's member list (ascending asset id) and a cell's lots (weight descending, asset id ascending) name the
    study's asset id, a ticker's rank. The decider child holds no aid, by the seal: its member columns are in
    ascending SALTED id, and that order stands for it everywhere. The law of a draw is the same (uniform over the
    cell); the stream differs from an aid-ordered one, and is as fixed before the look (the run key and the seed
    are). A conformance fixture hands its columns in the study's order, so the two implementations still agree.
11. **Seal X1's clause "every price array's last column is 1.0" no longer applies** (the ctx has no price array). Its
    adversary still does: the lattice search, continued fractions and the dither-range bound are run on the five
    scale-free fields, and must recover every close with the dither switched off and none with it on.

12. **The style rule's two figures are Step 0's** (`style.TILT` 1/3, `style.MIN_LOTS` 40), fixed before any panel
    program exists and calibrated by no study: A22 asks for "a fixed, tested rule" and names none. THE RULE IS
    HOLDINGS-BASED AND DIRECTION-BLIND. Its cost: a momentum or a low-volatility program is style-open by
    construction and is seated only by the forward route. A direction-aware rule would open a program only on a tilt
    whose measured no-skill pass rate (the receipt's `style_known_rate`, one figure a tilt and direction) is above
    the owner's wall; on the receipt as built that would leave the highest-momentum and the lowest-beta tilts
    seatable. It was NOT taken: the amendment names no direction, one study's point rates are noisy, and the error
    here only withholds a seat. The captain may refix the rule before mode "live"; it is one module and its test.
13. **No panel look until release E3 and its panel probe strata are merged** (A22 (3), `elane_xs.probed`): mode
    "gate" scores Validation and keeps both Train series, and every look waits. If the captain reads A22 (3) as "when
    the probe exists", `probed` is the one function to loosen.
14. **A style-open passer has no band**, so it is in no roster and no seat queue; it reaches the forward record as
    every scored version does (package J, owed). Until J lands it is recorded and NOT shadowed: said in the report.
15. **The conformance inputs are a 1.1 MB binary fixture** (five synthetic price sets in float64, bit for bit): the
    study's vectors carry no input price (its review's defect 4), and regenerating them needs the study's private
    generator and numpy's stream.
16. **A style-open program still takes its look** (A22 says "passer"), though the pass cannot seat it. That look
    spends one of its cell's two (A22 (2)) and, by the pre-registration's section 11, lowers the program's own
    forward bar from 0.12 to 0.03. The captain may prefer that a program read style-open on Train takes NO XS1 look
    and declares the forward route fresh: it would be one condition in `elane_xs.look` (wait, nothing spent).
17. **The Probe sleeve moved after the spec's feasibility table** (the captain's A20: 0.50 x E in all, three seats).
    E4-SPEC 0 and 10.4 computed a basket in a 0.25 x E sleeve. No stub carries the figure: package H recomputes
    10.4's table with E1's `size_entry` at the constitution's values in force and states it in its report.

18. **THE DITHER SITS ON THE ADJUSTED PRICE'S OWN CENT GRID, AND NO AS-OF PRODUCT IS FORMED** (package C; league/xs/
    ctx.py's module docstring). E4-SPEC D7 moves each bar's RAW price by half a raw cent and carries it through the
    as-of factor. The vendor rounds adjustment=all to the cent, so the grid a ratio of two history prices keeps is the
    adjusted price's, and half a raw cent covers only part of an adjusted cent wherever a later dividend or split has
    shrunk the adjusted price: `test_xs_seal.TheLevelCannotBeSearched` shows the lattice search finding the level
    within 1% on a 4-for-1 split history dithered D7's way. So each adjusted price is moved by half a cent of its
    own grid (never less noise), every field is a plain ratio of dithered adjusted prices (the as-of factor and its
    4-decimal rounding cancel), and a bar's fields are the same numbers in every ctx of a run. `derive` reads the
    adjusted closes directly for the same reason. `league.equity.ctx.as_of` is not imported; `_factor_row` names the
    market's row at t and the row a held lot of a halted name is marked at.
19. **`rel_volume` is narrower than the registered field**: the volume is put on the total-return basis (x raw close /
    adjusted close: a split leaves no step that would date a session) and moved by a relative dither of at most half
    a percent (a share count is a lattice too, and an exact count names a stock and a day); NaN for the oldest 62 of
    a decision's 253 sessions and with fewer than 32 valid bars among its 63.
20. **`ctx.cash`, `ctx.equity` and `ctx.budget` are rounded to the cent, and `ctx.equity` is the cash plus the lots
    marked at their dithered closes** (with one lot held, an exact equity series is that lot's exact marks). The
    engine and the book go on passing the sleeve's true figures in `Inputs`.
21. **What the dither does not close, stated**: on the LIVE path a fetch made after the vendor restates a name's
    history (an ex-date) shows its bars under another vintage, each moved by the vendor's own cent rounding. A
    program that kept the earlier view in STATE could read the scale of those moves and bound the adjusted level to
    about 5% an ex-date. It does not exist in any run on the store (one vintage: Train, Validation, the look, the
    forward twin), only where nothing is hindsight. The review's rubric ("any search for a price level") is the
    guard; the captain may prefer a second one.
22. **The class of the month is chosen among the pair's classes that are index members at the month's first
    session** (E4-SPEC D4 does not say whose volume is compared when one class is no member): every other aid of the
    pair is out for that month, a class that joins mid-month too; a pair with no member that day has no choice.
23. **A slice's look-back, and a live fetch's sessions (`ctx.fetch_sessions`), stay inside one span of
    `config.SPANS`**: the row before 2021-01-04 in the store is 2019-12-31, and no look-back or return crosses the
    reserve (E4-SPEC D1: a segment's first decision holds 252 sessions).
24. **A target that names a held slot which has left `ctx.ids` is malformed** (E4-SPEC D10: every id is in
    `ctx.ids`): XS.md tells the author to leave such a slot out (the House sells it at the next open). The engine
    counts it as the program's error, never as a failed decide.

## 9. Tests

    mkdir -p /dev/shm/eqe4-<key> && TMPDIR=/dev/shm/eqe4-<key> \
      /home/bwoods1998/Work/long-term-capital-management/.venv/bin/python -m unittest <modules>

Python 3.14 with numpy 2.5 there; Python 3.11 with numpy 2.4 is `~/Work/ltcm-v3/.venv311/bin/python` (the CI's other
leg: every new test passes on both). The seals each package owes are named in E4-SPEC section 14 (X1-X17); the
pre-registration's own tests T2 (the hand-checked vector of its 3.6), T5 (the placebo law and the exit law), T8 (119
passes and 120 fails) and T15 (u is the one-cell residual) are D's and E's to reproduce on synthetic panels.

**The study's conformance vectors** (synthetic inputs; no market data; `test_e4_stubs.TheStudysVectors` holds the two
files to each other):
- `league/tests/fixtures/xs1_conformance.json`: the study's file, byte for byte (sha256 386995d8...). Vectors "V1
  pass", "V2 fail", "V3 pre-check", "V4 stress", "V5 own floor", "V6 ineligible" (each: `inputs`, `lots`, `placebos`,
  `series`, `floor`, `look`), "CH" (characteristics on a 253-session window and the cells of 100 names: literal
  inputs) and "H" (the hand vector: literal inputs). Validation is sessions 0..249, the holdout 250..443; the
  vectors' screen bar is `k_XS` in the file and their placebo seed is `inputs.placebo_seed` (the receipt's sha taken
  as 64 zeros and the code's as 64 f's).
- `league/tests/fixtures/xs1_conformance_inputs.npz` (numpy `load`): key `manifest` (JSON bytes: per vector its
  `world`, the vector whose prices it reads) and, per vector tag `V1`..`V6`, arrays `<tag>/<name>`: `O`, `C` (444 x
  24 total-return opens and closes, NaN invalid), `U` (the eligible set), `entry_ok`, `sector`, `beta`, `momb` (the
  GIVEN characteristics: momentum at decision d is `momb[d // 21]`); the holdings log as of the look: `lot_name`
  (the column), `lot_weight`, `lot_d`, `lot_e`, `lot_ea` (0 open, 1 close), `lot_q` (-1: none yet), `lot_qa` (-1
  none), `lot_cell`, and each lot's cell members `member[member_start[i]:member_start[i + 1]]` with
  `member_leave` (the session at whose open the member leaves, -1 never); the Train pools `pool_d_x`, `pool_d_w`,
  `pool_c_x`, `pool_c_w` (absent where the vector has none); and the plain reference's answers: `r`, `B`, `x`, `x15`,
  `s`, `f`, `w`, `exits`, `invested` (sessions 0..443), `u` (the universe excess: the same residual with one cell,
  every name of U at the lot's decision that passes entry validity), `placebo_t_H` (the 999 placebo t's on the
  holdout, NaN undefined), `pos_draw_0`, `pos_draw_998` (each lot's counterpart position in its member list).
- WHO REPRODUCES WHAT. D (`test_xs_placebo.TheStudyVectors`): from `O`, `C` and the lots, the series (every integer
  exactly, floats to 1e-12), `u`, the counterpart positions of draws 0 and 998 and their sum over all draws, the
  placebo t's to 1e-9, vector H; and CH through `ctx.derive`'s arithmetic (C's functions, D's or C's test). E
  (`test_xs_screen.TheStudyVectors`): from the pools, the floor (T, k_cell, HO[0], HO[k_used], kappa_H, k_p, k_used,
  own_fp); from the series and the placebo t's, the pre-check, the look's legs, the grid index, the placebo count and
  the verdict; whether a look was spent; and its own ninth vector. The names 0..23 are the columns, in that order.
- THE VECTORS RUN UNDER THEIR OWN BAR: a receipt whose c_XS is the vector file's `k_XS` / 100, never the pinned
  receipt's, so a rebuilt receipt at another c_XS moves no vector.

## 10. As integrated (Oct 11, 2026; `feat/equity-e4`; nothing pushed, nothing deployed)

**What is in the tree.** C0 and packages A, B, C, D, E, G, H and I, each merged with `--no-ff` in section 2's order;
then `feat/equity-e2-int` at 5ad1f01e (it carries `feat/equity-e1` at 05f83d9e and `feat/equity-e2` at 04ca26c9: E1's
and E2's review and verification fixes, the vendor's cents, the Probe sleeve A20, the sizing-up step parked); then
every patch file of `league/swarm/e4_patches/`, in its README's order; then the receipt and its pin; then what
integration itself found. The base's sentence "the code wins" held: three hunks met E1's and E2's newer text
(`elane.look`'s seed order, `elane_train.review_step`'s audit reader, the book's cents-aware audit) and were taken
with a three-way apply, both sides kept.

**The ids.** E1's own fixes moved all three ids after this contract's base (0e8bbaa7): the options execution
fingerprint, the equity identity and the money digest of `feat/equity-e2-int` 5ad1f01e are not 0e8bbaa7's. NO COMMIT
OF E4 MOVES ONE: every commit before the merge of 5ad1f01e carries 0e8bbaa7's three, and the merge and every commit
after it carry 5ad1f01e's three. The xs identity is new (no band exists under an older one). The universe commit
(R-E4b), the only commit of this release that moves a digest, is NOT in this tree (below).

**What integration changed beyond the patch files** (each with its test):
- THE SEAT OF A SEATED PANEL PROGRAM (a fault, found by the end-to-end test). Package G's seat rule gave a panel
  CANDIDATE no row while the lane's effective mode is under "live"; nothing held a family already at Probe, so a
  seated program went on buying after the mode was put down, the nightly I6 failed or the twin marker went stale.
  Now: `bands._read_equity` gives a panel family in a running band a row only while the lane is live;
  `elane_xs.seat_word` and `bands.equity_seat_withdrawn` give E1's `families.standing` the store's word
  ("demoted" ONLY when the captain's switch is down; "held" when the switch is up and a store-side leg failed: the
  review's fix, E4-SPEC 17, its opens stop and its exits go on, nothing retired or sold, `families.HELD`; "unknown"
  when the lane cannot be READ, so a file caught mid-write retires nobody); and the book asks for the row at every
  SEND of a non-equity kind's entry (`live._seat_block`), so an entry planned on a live evening is held the next
  morning. `elane_xs.mode` and `live_ready` answer as before (a live leg
  that cannot be read still reads "gate"): each is the never-raising reading of a core (`_mode_why`, `_live_legs`),
  and `seat_word` alone reads the legs with the one that raises. The family's band in the store is not moved (it
  keeps its roster seat; when the lane is live again the same instance runs again).
  `league/equity/families.py` is a fifth E1 file E4 touches, beside H's four. Tests:
  `test_e4_integration.TheSeatOfASeatedPanelProgram`, `test_e4_e2e` step 9.
- THE VENDOR'S CENTS ARE ONE BOUND: `league.xs.config.rounding_bound`, `ADJUSTED_HALF_STEP` and `ROUNDING_GUARD` are
  re-exports of E1's (section 5's promise); `xs.engine.split_of` calls E1's tolerance-aware `split_factor`.
- `league/ops/stall.py`: patch 1b (G's proposal: the two SQL scopes) and a third literal E2's patch 14 brought after
  the base (the awaiting list): `stall.EQUITY_STRUCTURES`, held equal to the store's.
- `league/ops/preopen.py`: the gateway's class list reads the constitution's `EQUITY_CLASSES` (G's structure seal met
  it once package I's patch stopped its skip). `test_dlane_report_panel`: H's test of an unreadable style rule makes
  the rule unreadable itself, and a passer with no style verdict reads "style-open: unmeasured" (its own test).
- policy.json ships `elane.panel.mode` "off" (the spec's shipped value); `elane.screens.equity_xs` is
  `screen.pin(RECEIPT_PATH)` of the receipt at sha256 98acbb83, written whole.

**The seams no package could test alone, now held** (`league/tests/test_e4_integration.py`, beside the end-to-end
test): package B's spreads and N_eff jobs on package C's real store, and package A's and the twins' readers of their
files; package H's live columns on package C's real universe (the live eligibility IS the store's, the class of the
month included, which the nightly I6 leaves out; a held name that left the index keeps its column); the nightly I6
(A) on a fake venue's bars and on the bars a live decision kept (H); with `elane.panel.mode` "off" and every other
condition held, nothing is born, run, spent or seated.

**Owed, and what each holds back.**
- PACKAGE J (the forward registry row, the nightly shadow twin, the marker): after release E3. Until its marker is
  written, mode "live" reads as "gate": no panel program is seated (`test_e4_integration.TheLaneStopsWhereItsRuleSays`).
- PATCH 18 (package B, E3's `league/ops/contam_probe.py`: strata P4-P6). Until the probe publishes a route's panel
  strata, every panel look waits, nothing spent (A22 (3); the same test).
- THE UNIVERSE COMMIT (R-E4b; package I's generator is built and tested): it needs the House's
  `universe/tradable.json`, which exists only after R-E4a's `equity_universe` job has run and passed its audit, and
  the owner's `git apply` of the gateway half (`gateway-universe.patch` in the captain's scratch: `gateway/` is not
  edited by this release). It is ONE commit, of `league/constitution.py` and `gateway/lib/caps.mjs` alone.
- The gateway's merge list (`gateway/lib/protected.mjs` MERGE_FORBIDDEN) owes seven entries (E2's five,
  `league/swarm/elane_xs.py`, `scripts/gen_universe.py`); they wait in `league/ci.py` `PENDING_GATEWAY`.

**For release E3's integrator** (whichever of E3 and E4 merges second regenerates its diffs on the other's head):
`registry.py` (E4's six rows are last: E3's go before them), `funnel.py` (E4's `asset_years` block and E3's
`forward_record` stand side by side), `dlane_report.py`, `elane_train.py`, `elane_births.py`, `elane_seal.py`,
policy.json, `ci.py` and the docs are edited by both. `elane_folds.born` must skip `elane_xs.is_panel` families (a
panel family's hidden year is `elane_xs.assign`'s, over six years); `equity_neff.funnel_rows` reads E3's
`forward-report.json` `cey.hist_iy` and says "default" when the key is not there.

**Decisions the builders made that the captain should confirm** (each is in its package's report; the code and this
file say the same):
1. The Probe sleeve: at 0.50 x E (A20) a five-name basket alone fills the loss window. FIXED AT THE REVIEW (spec-2):
   E1's sizing cut the fifth name; the decision's budget is now the sleeve scaled so the whole basket fits
   (`live._panel_budget`: five lots of $200 at $2,229, held by `test_e4_e2e` and
   `test_equity_book_panel.TheWholeBasketIsScaledToTheRoom`). What is left for the captain: a full basket uses the
   whole window (first come), and a panel sleeve of its own would leave room beside it (a money row).
2. The vanish leg (D): at a name's third session with no valid close its leg is -0.30, no cost, for the lot, its
   counterparts and its cell's members, when the House could not have sold it since it left the eligible set.
3. The dither (C; open point 18): on the ADJUSTED price's own cent grid, not the raw price's as the spec worded it.
4. A17 one step on (H): a hold day that was asked successfully does not reset the failed-decide count either.
5. `i6.equal` is the bars' verdict within the vendor's cents (A); `bytes_equal` is reported beside it.
6. The French label stays "unmeasured" until a route to the library exists, so every XS1 verdict carries the screen
   flag "style-open"; the SEAT rule reads the House's own holdings-based loadings (`league/xs/style.py`), not the flag.
7. First-night budgets of the data jobs are estimates (A: about 570 asset calls and 900-1,000 bar calls; a peak of
   about 0.5 GB for the first whole fetch), to be read off the House's first receipts.
8. THE UNIVERSE'S AGE: `elane_xs.live_ready` reads the manifest's `universe_at`, which no job writes yet; it falls
   back to `live_from` and so fails closed `universe_max_age_days` (400) after the FIRST universe deploy, whatever was
   regenerated since. Before the first yearly regeneration the panel job must write `universe_at` (the first session
   it read the list now in force), or the lane stops there.
9. `equity_panel` has one trigger, `after("equity_universe")`: a night the universe job fails or is skipped, the
   panel's bars and the nightly I6 do not run either (A's open issue 5); the I6's age is not yet a leg of `live_ready`.
10. THE SPREADS' SHARE CANNOT HOLD 0.90 FOR LONG, BY CONSTRUCTION (seen when package B's job first ran against
    package C's real store at integration; a rule-level reading, no market figure). A name is sampled on a Train-era
    sample day only while it is an index member that day (8 days a Train year, the last of them in 2024), and
    `hs_share` counts today's members with 8 samples at both fill points. So every name that joined the index after
    the first weeks of 2024 has under 8 and is charged the universe's default figure: `hs_share` starts near the
    line and falls by the index's turnover each year, and under `spreads_min_share` (0.90) the mode reads "train"
    (no Validation, no look). Two ways out, neither taken here: the setting (its bound is [0.5, 1.0]), or sampling a
    name's Train-era days whether or not it was a member then (a spec change for package B).

## 11. The review's fixes (Oct 11, 2026; `feat/equity-e4`; nothing pushed, nothing deployed)

Nineteen findings in three lenses (evidence, live, spec), each confirmed against the code and fixed at its root with a
test that failed before; none rejected, none deferred. What CHANGED IN THIS CONTRACT's shapes and rules:

| what | before | now | where |
|---|---|---|---|
| the seat of a SEATED panel program | any leg of the lane not live: "demoted" (retired, lots sold) | "demoted" only on the captain's switch; a failed store-side leg is "held": opens stop, exits go on, nothing retired (`families.HELD`); "unknown" as before | `elane_xs.seat_word`, `bands.equity_seat_withdrawn`, `families.standing`, `live._sync_instances` |
| `live_ready`'s legs | all read from the last manifest | first: the store is FRESH by the clock (`fetched_through` the last closed session or the one before; the twin marker likewise); `elane_xs.CLOCK`, `now=` | `elane_xs._live_legs` |
| the nightly I6 | False on a late bar, a member the decision's columns lacked, a row with no kept fetch | False only on a price that differs; `late`, `absent` counted; a row that read bars and has no kept fetch is `live[instance] = None`; rows without `bars_sha` are no rows of it | `equity_panel.i6_check` |
| the Gym's sizing | a per-run cash book (a loss shrank the next lot) | CONSTANT-WEIGHT on entry notionals against E0 (C3, C8); ONE narrowing: the open lots' entry weights never pass 1.00; `ctx.cash` is the free room, `ctx.equity` that plus the lots at their marks | `engine._committed`, `_room` |
| a live panel sleeve | E1's reading at the marks | the same constant-weight book (`book.committed`, `sleeve_room`); every wall of the account still at its marks | `live._size`, `_panel_job` |
| a live decision's budget | the sleeve | the sleeve SCALED so the whole basket fits the loss budget's room and the invested cap (`equity.rebalance` says `scaled`) | `live._panel_budget` |
| the style loading (A22 (1)) | sum of w x rank over lots | sum of w x h x rank, h the sessions held | `style.block` |
| `ctx.range` | (h' - l') / c', each price dithered in cents | the body (as `iret` states it) + the true wicks over the close + `config.WICK_DITHER` x a draw: never under the body | `ctx._fields` |
| a lot's `tag` in a live ctx | the House's "xs" | the Gym's word ("" or "ineligible") | `book._ctx_tag` |
| `rows_to_arrays` | raised on a bar of a day that is no session | drops and counts it (`count`), as `Grid.place` | `ctx.rows_to_arrays`, `book.fetch` meta `dropped` |
| `book.columns` | a held symbol the universe does not know: refused | `renamed={now: bought under}` finds a lot's column across a ticker change | `book.columns`, `live._panel_renamed` |
| a morning mismatch on a rebalance row | its buys cancelled | void whole: its program's sells too | `live._panel_mismatch` |
| the look's floor | reused from an earlier attempt when it fit the receipt | computed from the segments each attempt runs | `elane_xs.look` |
| the data jobs | ran whatever the mode; `equity_universe` at start, `equity_panel` after it | skipped while `elane.panel.mode` is "off" (`equity_universe.lane_off`); daily 01:40Z and 01:55Z, each its own trigger; a wall detector around all six (`watched`) | `league/ops/registry.py`, the six jobs |
| `coverage_min` | read from ops.json by the job; the lane's key read by nothing | the lane's own key (`equity_panel.coverage_floor`, `elane_xs.map_notes(root, settings)`) | |
| the lane's state | the reason the mode read lower reached nothing | `elane_xs.status`, `health` (four alarms), `bands.roster(...)["seatless_why"]`, the heartbeat's `equity.panel`, the report's `equity.panel_lane` | |

Open after the fixes, stated: a held lot's `ret` against its slot's path still scatters with one over the price (the
reviewer's weaker channel); a name whose ADJUSTED price is under about $2 is coarse in every field (the store could
mask such bars: not built); a full basket at this account's size uses the whole loss window (a panel sleeve of its
own is a money row); the equity roster with `seatless_why` is in the dlane report only while the lane's switch is up.
