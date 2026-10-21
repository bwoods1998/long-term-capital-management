# E1 build interfaces: the equity lane's contract between its seven packages

Branch `feat/equity-e1` (worktree `~/Work/ltcm-v3/eqe1`), from `origin/main` a48623e7 (the gateway's stock code, PR
#532, is on it). This file is the skeleton's: every package builds against it and changes it only through the
captain. The stubs it names exist on the branch now (bodies raise `NotImplementedError("<package>: <file> <name>")`;
their docstrings say what each must do), so every package imports every other package's names from day one.

**Sources, in order of authority.** The captain's amendments A1-A16 and A20 (a later one over an earlier: A11, the S2
screen, over A9's gate; A10 over A6 and A8.7; A12's look cap over A9 D6; A20's Probe sleeve over A5's; A8, the design
review's 13 decisions, over any brief),
then the design (DESIGN.md), then the package briefs. Where a brief and an amendment differ, this file follows the
amendment and says so (section 13). THE HOUSE'S SHARE SCREEN IS S2 (A11: sscreen2-1010, receipt 2, pinned for both
lanes; section 9). S1+F1, the pinned sscreen-1010 pre-registration with A9's fixes F1, D3, D5, D6, stays in code as
receipt 1's screen, pinned by no lane; A9's D3 (the lineage), its D5 pools as S2's sets restate them, and the
no-feedback rule carry over.

**Hard rules for every package.** No private figure is committed: no census or market result, no price or return from
any real year, no Phase A number, no price scale from the census; rule-level simulation figures are allowed. No
market data file is committed. No push, PR, deploy, or contact with the House, Sail, Alpaca, the gateway or a broker;
no secret or env file read. `gateway/` is read only (`gateway/lib/caps.mjs`, `gateway/wrangler.jsonc`). Tests run one process at a time:

    mkdir -p /dev/shm/eqe1-<key> && TMPDIR=/dev/shm/eqe1-<key> \
      /home/bwoods1998/Work/long-term-capital-management/.venv/bin/python -m unittest <modules>

Bulky scratch goes under `~/Work/.ltcm-main/scratch/eqe1/`. Match the surrounding code: its idioms, naming, docstring
density, Decimal money and fail-closed style. Commit messages end with the two attribution lines the task gives.

---

## 1. Ownership map

Each file has exactly ONE owner, except the two shared files of section 1.1, owned per function. A package edits only
its own files (and its own functions of a shared file). A test file is owned by the package that creates it.

| key | owns (new files in **bold**) |
|---|---|
| skeleton | `league/equity/INTERFACES.md` (this file; changed only through the captain) |
| core | **`league/equity/__init__.py`**, **`config.py`**, **`store.py`**, **`program.py`**, **`ctx.py`**, **`engine.py`**, **`results.py`**, **`runner.py`**, **`synth.py`**, **`EQUITY.md`**; `league/swarm/evaluator.py` (equity identity, adoption mirrored, and `adopt` skipping equity families); tests **`league/tests/test_equity_store.py`**, **`test_equity_program.py`**, **`test_equity_ctx.py`**, **`test_equity_engine.py`**, **`test_equity_runner.py`**, **`test_equity_identity.py`** |
| book | **`league/equity/live.py`**, **`schedule.py`**, **`actions.py`**, **`families.py`**; tests **`league/tests/test_equity_book.py`**, **`test_equity_schedule.py`**, **`test_equity_actions.py`**, **`test_equity_families.py`** |
| hooks | **`league/live/equity_hook.py`**, **`league/equity/kinds.py`**, **`league/equity/child.py`**; `league/live/step.py`, `league/live/real.py`, `league/live/decider.py`, `league/live/paper.py`, `league/live/venue.py`; tests **`league/tests/test_equity_hooks.py`**, **`test_equity_decider.py`**, **`test_equity_i6.py`**, **`test_equity_isolation.py`**, **`test_equity_paper.py`** |
| money | `league/constitution.py`, `league/ci.py`, `league/live/money.py` (all but `band_for`), **`league/equity/sizing.py`**, `league/equity/bands.py` (money's functions), `league/ops/preopen.py`; tests **`league/tests/test_equity_money.py`**, **`test_equity_sizing.py`**, **`test_equity_bands_money.py`**, and the pins in `league/tests/test_ci.py` and `league/tests/test_constitution.py` |
| swarm | **`league/swarm/elane.py`**, `league/swarm/policy.json`, `league/swarm/settings.py`, `league/swarm/seeds.py`, `league/swarm/cards.py`, `league/swarm/gate.py`, `league/swarm/tournament.py`, `league/swarm/bands.py`, `league/swarm/store.py` (the `lanes` filter of `families`), `league/swarm/loop.py`,
`league/swarm/dlane.py` (lane scoping only, A8.12), `league/equity/bands.py` (swarm's functions), `league/live/money.py` (`band_for` only); tests **`league/tests/test_elane.py`**, **`test_elane_seeds.py`**, **`test_elane_gate.py`** |
| screen | **`league/equity/screen.py`**; tests **`league/tests/test_equity_screen.py`**, fixture **`league/tests/fixtures/equity_screen_fake.json`** (a fake receipt, tests only) |
| ops | **`league/ops/equity_data.py`**, `league/ops/registry.py`, `league/ops/dlane_report.py`, `league/ops/twins.py`, `league/ops/funnel.py`, `scripts/floor_box.py`, `docs/operations.md`, `CHANGELOG.md`; tests **`league/tests/test_equity_data.py`**, **`test_equity_twins.py`**, **`test_dlane_report_equity.py`**, **`test_floor_box_equity.py`** |

### 1.1 The two shared files (owned per function)

| file | money owns | swarm owns |
|---|---|---|
| `league/live/money.py` | `Table` (its new `equity` field and `from_constitution` filling it), `EquityTable`, `Exposure` (its new `equity_open_risk`, `equity_invested`), `available_cash`, everything else in the file | `band_for` only: one first statement, `if equity_hook.is_equity_row(row): return equity_hook.band_for(row)` |
| `league/equity/bands.py` | `EquityRecord`, `sized_up`, `sized_sleeve_share`, `edm1` | `next_band`, `band_for_row` |

Each edits only its own functions; neither reorders the file.

### 1.2 Files no package edits

`gateway/**` (read only), `league/gym/**` (the equity lane imports it, never edits it: it is inside the options
fingerprint), `league/live/families.py` (unchanged: the options reader keeps reading `bands.read(root)`, which leaves
equity lanes out by default; the equity reader is `league/equity/families.py`), `league/live/state.py` (the book
creates its own tables), `docs/benchmarks/equity_screen_1.json` (the captain writes it from the screen study's result;
no package writes it).

---

## 2. Boundaries (A8.8, I5)

1. **league/live reaches league.equity through exactly two modules**: `league/live/equity_hook.py` (any league.equity
   import) and `league/live/decider.py` (it imports `league.equity.kinds` only). `test_equity_isolation.py` (hooks)
   asserts this over every `league/live/*.py` by AST, and that `league/live/step.py` contains the text
   `.equity.tick(` exactly once, inside `OptionsLive.minute`.
2. **Evidence modules of league/equity** (`__init__`, `config`, `store`, `program`, `ctx`, `engine`, `results`,
   `runner`, `synth`, `sizing`, `screen`, `child`: `league.swarm.evaluator.EQUITY_EVIDENCE`, the captain's A13) and the
   kind table `kinds` import nothing of `league.live` and nothing of `league.swarm`. They may import `league.gym`
   modules listed in `league.swarm.evaluator.EQUITY_GYM_FILES` (core keeps the list equal to the imports;
   `test_equity_identity.py` holds it) and `league/__init__.py`, `league/safety.py`, `league/structure_core.py`,
   `league/stats.py` (the 4 `LEAGUE_FILES`).
3. **Plumbing modules of league/equity** (`live`, `schedule`, `actions`, `families`, `bands`, and since A13 `kinds`)
   may import `league.live.state`, `league.live.venue`, `league.live.money`, `league.live.real` (its constants and
   `probe_figures`, the shared budget's reader),
   `league.swarm.bands`, `league.swarm.store`, `ltcm.data`. `bands` imports nothing of league.live (it reads the
   money table by attribute); `kinds` imports nothing of either (the child reads it).
4. **The equity fingerprint** (`league.swarm.evaluator.equity_fingerprint`, core; AS AMENDED BY A13): sha256 over the
   EVIDENCE modules only (`EQUITY_EVIDENCE`: `league/equity/<name>.py` for each, never this file or EQUITY.md: as
   `execution_fingerprint`, documentation never resets evidence), the 4 `LEAGUE_FILES`, `EQUITY_GYM_FILES` and, since
   the review's fixes (section 14), `EQUITY_CALENDAR_FILES` (`ltcm/__init__.py`, `ltcm/broker.py`,
   `ltcm/data/__init__.py`: the NYSE calendar the store and the ctx read, what the evidence imports outside league/),
   path and bytes, in path order. `EQUITY_EVIDENCE` is the import closure, inside league/equity, of the runner, the child, the
   screen and the engine, plus `synth` (which the four never import; it imports nothing outside the closure):
   `test_equity_identity.py` holds the list equal to that closure, so a new evidence module cannot hide. THE PLUMBING
   IS OUT (`live`, `actions`, `schedule`, `families`, `bands`, `kinds`): a plumbing fix moves no identity and retires
   no live equity lineage; that live and Gym agree is policed by the I6 ctx test and the twins. It never includes
   league/live or league/xs. A change to league/live moves the OPTIONS fingerprint only; a change to an evidence module
   of league/equity moves the EQUITY fingerprint only. E1 moves the options fingerprint once (its hooks and the stubs
   in money.py and decider.py).
4a. **The panel kind's slot** (A13): `kinds.KINDS["panel"]` = `"league.xs.child"`, `kinds.RUNTIME` carries
   `"league/xs/"`, and `league/xs/__init__.py` and `league/xs/child.py` exist as stubs (`handle` refuses every op). A
   later release builds the cross-sectional lane inside league/xs/, with no edit of league/live and none of an
   evidence module here. league/xs imports nothing of `league.live` or `league.swarm`, league/live never names it
   (`test_equity_isolation.py`), and league/ci.py protects it (`PENDING_GATEWAY`, with `ltcm/broker.py`: every file of
   the decider child's sealed runtime is `FORBIDDEN`, `test_ci.py`).
5. **Options consumers skip equity families** (swarm, core). ONE MECHANISM: `SwarmStore.families(*, alive=None,
   lanes=None)` (swarm, league/swarm/store.py): `lanes` None returns the options lanes only (a family whose spec's
   `lane` is "beta" or "equity" is left out), so the researcher's selection, the tournament's Gym validation, forks,
   the learning game, the incubator, the diagnostician, idle retirement, the always-in G1 check and every other
   existing caller skip equity families with no edit of their own; `lanes=LANES` returns the equity families only
   (elane, the tournament's and the gate's equity dispatch); `lanes="all"` everything (reports). `bands.read(root)`,
   `observe` and `incubator` likewise (equity rows only with `lanes=LANES`). `evaluator.adopt` (core) iterates the
   default and so never touches an equity family; `adopt_equity` handles them. The swarm audits the raw-SQL readers of
   `families` (league/swarm/game.py's alive ceiling, cards.py's graveyard reads, ...) and scopes the ones that would
   act on an equity family. Look and Validation outcomes of equity families never reach generators or the
   diagnostician (A9 D3). Helper: `elane.lane_of(store, fam)` is not None.

---

## 3. Conventions

- Money and share quantities: `decimal.Decimal` in code, **Decimal strings** in SQLite and JSON (`"0.123456"`), never
  floats; dollars unless named; shares up to 6 decimals sent (`config.QTY_PLACES`; the venue takes 9).
- Prices and returns inside the engine, ctx and screen: float64 numpy (a program's world), rounded to 4 decimals at
  the ctx; the cash book converts with `Decimal(str(x))`.
- Days: ISO `YYYY-MM-DD` strings (New York session days) in rows and JSON; `int32` ordinals since 1970-01-01 in arrays
  (`league.gym.day.ordinal`). Times: epoch seconds (UTC) in rows; schedule offsets in seconds from the session's open
  or close (New York).
- Lanes: `league.equity.LANES` = ("beta", "equity"). Classes: "etf", "stock". Fill points: `"at": "open" | "close"`.
- Instances: `<family>@<version>:r` (the real evidence route, as the options book's), kept in `eq_instances`, never in
  the options `instances` table.
- Client ids: `lq-<nonce>-<eid>-<family slug>` (`league.equity.CLIENT_PREFIX`; the state's nonce first, as the book
  builds them: section 5.2).
- Every refusal names its cause; every unreadable input refuses opens and never blocks exits.

---

## 4. core

### 4.1 `league/equity/__init__.py`
`EQUITY_ENGINE_VERSION = "equity-engine-1"`, `EQUITY_STORE_VERSION = "equity-store-v1"`, `BETA`, `EQUITY`, `LANES`,
`CLIENT_PREFIX = "lq-"` (written; no behaviour).

### 4.2 `league/equity/config.py`
Constants (written): `UNIVERSE` {symbol: class} = the gateway's `STOCK_UNIVERSE` exactly; `INDEX_ETFS`;
`HALF_SPREAD_BP` (1 bp SPY QQQ IWM DIA, 3 bp other ETFs and stocks, 5 bp TLT GLD); `K_BASE` 1.0, `K_STRESS` 1.5;
`SEC_FEE_PER_MILLION` "27.80", `TAF_PER_SHARE` "0.000166", `TAF_MAX` "8.30"; `POSITION_SHARE` {"etf": "0.50",
"stock": "0.20"}; `SLEEVE_USD` "1000" (the Gym's E0); `MAX_SYMBOLS` 20, `MAX_HISTORY` 504, `MAX_INTENTS` 20,
`MIN_HOLD_SESSIONS` 1, `DEFAULT_MAX_HOLD` 20, `MAX_HOLD_CAP` 60, `FAILED_DECIDES_EXIT` 2, `QTY_PLACES` 6; `WINDOWS`
(Train 2016-01-04..2024-12-31, Validation 2025-01-02..2025-12-31, holdout 2026-01-02..2026-09-25, forward
2026-09-26..), `SEALED`; `LOOK_FIRST` 2026-01-02 and `LOOK_CAP` 2026-10-09 (A12, integration; A9 D6 had 2026-12-31: the one look reads LOOK_FIRST
through min(the last close before the look, LOOK_CAP), the store's holdout and forward days);
`TRAIN_ERA_SEGMENTS` ((2016-01-04, 2019-12-31), (2022-01-03, 2024-12-31)).
Functions: `class_of(symbol) -> str | None`; `half_spread(symbol) -> float` (fraction); `sell_fees(proceeds: Decimal,
shares: Decimal) -> Decimal` (SEC + TAF, each rounded UP to the cent, TAF capped).

### 4.3 `league/equity/store.py`
- Layout of `<state>/equity-daily/` (numpy only, atomic, manifest last): `VERSION`; `calendar.npz` {days int32, early
  bool}; `bars/<SYMBOL>.npz` {days int32, raw_o, raw_h, raw_l, raw_c, raw_v, all_o, all_h, all_l, all_c float64};
  `manifest.json` {version, fetched_through, symbols {SYM: {class, sha256, first, last, rows}}, calendar_sha256,
  source "alpaca-sip-1Day" | "synthetic", audit}; `GATE` (the House's store only).
- `EquityGateCapability` (cannot be constructed), `mint_equity_gate_capability(store_root, reason) ->
  EquityGateCapability` (needs the `GATE` mark and a reason; StoreRefused otherwise), `StoreRefused`, `MissingData`.
- `window_of(day) -> "train" | "validation" | "holdout" | "forward" | "pre" | "gap"`.
- `Bars` (frozen): `days` int32 (n,), `early` bool (n,), `first` int (the run's first session index; before it
  history only), `symbols` tuple, `raw[sym]` float64 (n, 5) o h l c v, `adj[sym]` float64 (n, 4) o h l c, `window`,
  `data_version`; `n` property.
- `EquityStore(root, *, gate=None)`: `gate` (bool), `manifest()`, `symbols() -> {sym: class}`,
  `sessions(window=None) -> [date]`, `bars(symbols, window, *, history, start=None, end=None) -> Bars`,
  `span(symbols, first, last, *, history) -> Bars` (Train only), `data_version(symbols, days) -> str` (24 hex).
- `nyse_sessions(start, end) -> [(date, early: bool)]`: `ltcm.data.us_equity_session` from 2022 (that calendar starts
  in 2022: `CALENDAR_MIN_YEAR`), the same rules computed here for 2016-2021 (no Juneteenth before 2022; the 2018-12-05
  closure). The store's calendar, `synth`, and the data job's audit read this one.
- `write_store(root, *, calendar: [(date, early)], series: {sym: {"days": [date], "raw_o".."raw_v", "all_o".."all_c":
  [float]}}, classes: {sym: class}, fetched_through: date, source: str, gate: bool, audit=None) -> manifest dict`.
  ops' `equity_data.run` and `synth` both write through it.

### 4.4 `league/equity/program.py`
- `NEEDS = {"symbols": [1-20 of config.UNIVERSE], "history": 0-504 (default 252), "max_hold_sessions": 1-60
  (default 20)}`; `Needs(symbols, history, max_hold_sessions)` with `as_dict()`; `parse_needs(raw) -> Needs`
  (`NeedsRefused`, a `CodeRefused`).
- `load_program(code, *, name="program", params=None) -> EquityProgram` (`league.gym.safety.check_program`
  unchanged; PARAMS bound at the declaration and merged as `league.gym.runtime` does);
  `EquityProgram(name, code, needs, params, sha, run_sha)` with `start(*, timeout=1.0, max_errors=25,
  budget_seconds=None) -> EquityRunner`.
- `EquityRunner.decide(ctx) -> [intent]` ([] on error, timeout, disqualified), `stats() -> {calls, errors, timeouts,
  seconds, messages, disqualified}`.
- **Intents** (`normalize_intents(raw, on_error=None)`): at most 20; exactly one of:
  - `{"buy": SYM, "share": (0, 1] | "usd": > 0, "at": "open" | "close" (default "open"), "tag": str}`;
  - `{"sell": <lot id int>, "at": "open" | "close", "tag": str}` (a whole lot);
  - `{"cancel": <order id int>}`.

### 4.5 `league/equity/ctx.py` (I6: the Gym's and the live path's one constructor)
- `Ctx` attributes: `symbols`, `bars` {sym: `SymbolBars`(open, high, low, close, volume, ret: read-only float64,
  oldest first, last = session t; as-of prices `all_s x raw_t / all_t` rounded to 4 dp; volume raw; ret of the as-of
  closes, NaN first)}, `prices` {sym: t's close}, `weekday` (0-4), `events`, `events_next` (`league.gym.events.flags_for`:
  fomc, cpi, jobs, monthly_opex, quarter_end, half_day), `session_of_month` (1-based), `sessions_to_month_end`
  (0 on the last), `positions` [`lot_row`], `orders` [{id, side, symbol, at, usd, tag}], `closed` [`closed_row`],
  `rejects` [str], `cash`, `equity`, `budget` (floats, dollars, the sleeve's), `caps` {sym: dollars}, `params`.
- `lot_row(*, lid, symbol, klass, qty, entry, mark, held_sessions, at, tag="") -> {id, symbol, class, qty, entry, mark,
  value, pnl, held_sessions, at, tag}`; `closed_row(*, lid, symbol, qty, entry, exit, net, held_sessions, reason,
  tag="") -> {id, symbol, qty, entry, exit, net, held_sessions, reason, tag}` (reason "program" | "max_hold" |
  "house").
- `Inputs` (frozen; pickled to the child): symbols, history, days (int32), raw {sym: (n,5)}, adj {sym: (n,4)},
  trading_days (int32), early (bool), positions, orders, closed, rejects, cash, equity, budget, caps, params.
- `build(inputs) -> Ctx`; `as_of(adj_col, raw_t, adj_t) -> ndarray`;
  `inputs_from_bars(bars, t, *, needs, positions=(), orders=(), closed=(), rejects=(), cash, equity, budget, caps,
  params) -> Inputs` (the Gym; never a row after t);
  `inputs_from_fetch(raw_rows, all_rows, *, day, needs, ..., params) -> Inputs` (live: Alpaca 1Day rows
  {t, o, h, l, c, v} per symbol through `day`; ValueError when t's bar is missing or the series disagree);
  `ctx_bytes(ctx) -> bytes` (canonical; the I6 equality and the decision's provenance sha).
- **The I6 helper** the hooks package's test uses: build a store with `synth.synthetic_store`, then for 20 random
  sessions t compare `ctx_bytes(build(inputs_from_bars(bars, t, ...)))` with `ctx_bytes(build(inputs_from_fetch(rows
  made from the same bars through t, ...)))`. core's own test proves the as-of identity (a store written later, after
  a split and a dividend, gives the same ctx at t within rounding).
- **What I6 does not say** (the rehearsal on real bars, section 15.4): the vendor rounds its adjustment=all prices to
  the cent and restates the series at every later event, so a live decision's ctx does not reproduce byte for byte
  from a later store; the as-of prices differ by up to `config.rounding_bound` of the adjusted prices they are built
  from. `ctx.events`' fomc, cpi and jobs are False outside their tables' rows (league/gym/events.py), in both builders.

### 4.6 `league/equity/engine.py`
- `EngineConfig(capital=config.SLEEVE_USD, k=1.0, timeout=1.0, max_errors=25, budget_seconds=900.0)` (frozen).
- `fill_price(official: float, side: "buy" | "sell", hs: float, k: float) -> float` = official x (1 +/- k x hs): the
  engine's, the book's and the twins' one fill function.
- `official(bars, symbol, index, at) -> float | None` (raw open or close at a session index).
- `run(program, bars, *, cfg) -> result`; `run_isolated(...)` (an exception becomes `results.failed`).
- **The session (A2)**: decide after the close of t on `build(inputs_from_bars(bars, t, ...))`; in t+1: (1) open
  exits, (2) open entries, (3) close exits, (4) close entries. Entries sized by `league.equity.sizing.size_entry`
  (`budget_room` None, `available_cash` = the sleeve's free cash, E = capital). Fees `config.sell_fees`. Min hold 1
  session (a close-bought lot may sell at the next open). House exit rules identical live (A8.5): `max_hold_sessions`
  -> next open ("max_hold"); 2 sessions of failed decides -> every lot at the next open ("house"). Sleeve cash >= 0
  after every fill, asserted. Dividends from the all/raw ratio's step on the ex-date; splits scale shares.
- Tests (DESIGN 11): golden P&L on synthetic series (fees, half-spreads, dividends through the ratio), no look-ahead
  (fuzzing rows after t changes no decision at t), as-of identity, cash >= 0, min hold, determinism, open AND close
  fills.

### 4.7 `league/equity/results.py`
- Result keys: run_id, program, program_sha, run_sha, params, window, symbols, engine, data_version, capital (Decimal
  string), k, trials (1), status ("ok" | "disqualified" | "no_data"; "error" from `failed`), needs, summary, by_year,
  trades, entry_days, exposure, bh, mte, daily ([day, pnl, equity, exposure]), lots, runtime, result_sha, start, end.
- `summary`: trades, days, days_traded, pnl, fees, dividends, mean_net_return, sd_net_return, t_trade, win_rate,
  sharpe_daily, t_daily, max_drawdown, exposure_mean, turnover, mte.
- `lots` (the screen's input; House-only): {lid, symbol, class, weight (entry notional / capital), qty, entry_day,
  entry_at, entry_px, exit_day, exit_at, exit_px, fees, div, hs, reason, held_sessions}.
- `sha(value)`, `summarize`, `by_year`, `buy_and_hold`, `mte`, `view(result, window)` ("train" all; "validation" no
  trades, dates, daily, lots; "holdout" / "forward" the gate's inputs; "gate" status only), `failed(program, why)`.
- `validation_r_sd` for EDM1 = `summary.sd_net_return` of the version's 1.0x Validation run (swarm records it).

### 4.8 `league/equity/runner.py` (A3: on the House, in the decider child)
- `run_bars(code, params, bars, *, name="program", k=1.0, capital=None) -> result` (in-process; the child's).
- `Run(result, bars)` (frozen); `RunFailed`; `RUN_BUDGET_SECONDS` 1200.
- `Isolated(decider, store_root, *, budget_seconds=RUN_BUDGET_SECONDS)`: `needs(code, params, *, name) -> dict`,
  `train(code, params, *, name, start=None, end=None, k=1.0) -> Run`, `validation(code, params, *, name, k=1.0) ->
  Run`, `look(code, params, *, name, gate, k=1.0) -> Run` (`LOOK_FIRST` through min(the last close before the
  look, `LOOK_CAP`), A9 D6; `gate` an `EquityGateCapability`), `segments(code, params, *, name) -> [Run]` (one per
  `TRAIN_ERA_SEGMENTS`: the floor's IND22 and IND1622 pools).
- The parent slices the store (with the capability for `look`) and sends `decider.kind("equity", "run", {"code",
  "params", "name", "bars": Bars, "k", "capital"}, budget_seconds=...)`; the child (hooks' `child.handle`) calls
  `run_bars`. NEEDS come first through `decider.kind("equity", "needs", {...})`, so the parent never executes a
  program.

### 4.9 `league/equity/synth.py`
`synthetic_store(root, *, symbols=("SPY","QQQ","IWM","DIA"), start=2016-01-04, end=2026-10-09, seed=7, drift=0.0,
vol=0.18, splits=None, dividends=None, gate=False, gaps=None) -> Path`; `constant_store(root, *, symbol="SPY",
start=2025-01-02, sessions=20, price=100.0, step=0.0, gate=False) -> Path`. Every package's tests use these.

### 4.10 `league/swarm/evaluator.py` (core's edits; stubs present)
`EQUITY_KEY = "equity_evaluator"`, `EQUITY_GYM_FILES` (core keeps it equal to league/equity's league.gym imports),
`equity_fingerprint(repo=None) -> str`, `equity_identity() -> {"equity": sha, "engine": EQUITY_ENGINE_VERSION}`,
`adopt_equity(store, expected) -> {adopted, families, previous, current}` (mirrors `adopt` for equity-lane families
only), and `adopt` skips equity-lane families (I5). Called at the swarm process start beside `adopt` (swarm wires the
call in `loop.py`).

### 4.11 Additions made while building core (additive; nothing above changes meaning)
- **store**: `LOOK = "look"`, a window name `bars()` and `sessions()` accept: the one sealed look's span,
  `LOOK_FIRST` .. min(the store's `fetched_through`, `LOOK_CAP`), opened only with the capability (A9 D6; the holdout
  and forward windows alone cannot express it). A look's `Bars.window` and result `window` are "look";
  `results.view(result, "look")` is the holdout view. Also `FIRST_YEAR` (2016: `nyse_sessions` refuses earlier days),
  `ordinal`, `from_ordinal`, `as_date`, `Bars.day(i)`, `EquityStore.fetched_through`. A capability minted for one
  store root opens no other. Every file read is checked against the manifest's sha256 (MissingData on a mismatch), and
  npz files are byte-reproducible, so the same data has the same `data_version`.
- **config**: `DEFAULT_HISTORY` 252, `MIN_ORDER_USD` "10" (the Gym's `min_order_usd`), `CENT`, and the two hold
  predicates the book must use too: `may_sell(entry_session, session)` (min hold) and `max_hold_due(held_sessions,
  max_hold_sessions)`: `held_sessions` at a decision close = sessions since the lot's entry session (0 at the entry
  session's own close); due when `held_sessions` + 1 reaches `max_hold_sessions` -> exit at the next open, so a lot is
  held at most `max_hold_sessions` (integration: the engine and the book disagreed by one session; the book's reading
  was kept).
- **program**: `NeedsRefused` subclasses `league.gym.runtime.NeedsRefused` (still a `CodeRefused`);
  `EquityRunner.last_failed` (the last decide raised, timed out or the runner is disqualified; a malformed intent is
  an error but never a failed decide: A8.5's count reads this).
- **ctx**: `calendar_around(day) -> (trading_days, early)` (t's month and the next session's month from
  `store.nyse_sessions`: both builders read it). The as-of factor is session t's closes (a symbol with no bar at t
  takes its last bar's; `prices[sym]` NaN). Byte equality holds for the same arrays (I6); a store fetched after a later
  split or dividend agrees within the vendor's 4-decimal rounding (scaled by the split), not to the byte.
- **engine**: decisions run at the close of the session before the run's first through the one before its last;
  `split_factor`, `RATIO_TOLERANCE`, `SPLIT_MIN_STEP`, `SPLIT_RESIDUAL`, `SPLIT_TERMS` (dividends and splits read from
  the all/raw close ratio's step); a result also carries `actions` (the dividends and splits booked on held lots),
  `reason` when disqualified, and `summary.account_pnl`, `summary.open_lots`. Lots open at the run's end are in `lots`
  with reason "open". ctx.caps in the Gym = max(0, min(position share x E0 - own marked value, cash)).
- **results**: `canonical`, `basket_returns`, `excess_returns(trades, closes, days, opens=None)`, and `mte(trades,
  closes, *, days=(), opens=None)` (a lot's time-matched window runs between its own fill points, open or close).
- **runner**: `ProgramRefused(CodeRefused)` (the child refused the program; `league.live.decider.ProgramRefused` is
  out of an evidence module's reach), `KIND = "equity"`, `NEEDS_BUDGET_SECONDS`; the parent re-parses the child's
  NEEDS before it slices.
- **synth**: `synthetic_store(..., as_of=None)` (the fetch day: bars through it, adjustment=all with its events only);
  THE I6 HELPER: `bar_rows(bars, symbol, t, *, adjustment) -> [{t, o, h, l, c, v}]` and `same_ctx_cases(store_root, *,
  symbols, history, count=20, seed=0, window="validation", gate=None, ...) -> [{day, index, needs, gym, raw_rows,
  all_rows, common}]`: build the live ctx with `ctx.inputs_from_fetch(case["raw_rows"], case["all_rows"],
  day=case["day"], needs=case["needs"], **case["common"])` (or the book's path) and compare `ctx_bytes` with
  `build(case["gym"])`.
- **evaluator**: `is_equity_family(fam)` (spec `lane` in `LANES`), `equity_band_current(state, expected)`,
  `EQUITY_SELECTION_KEYS`; `adopt_equity` reads `store.families(alive=True, lanes=LANES)` (a store without the swarm's
  `lanes` keyword: every alive family, filtered by `is_equity_family`), keeps `elane_try` and `elane_look` (spent
  stays spent), clears `EQUITY_SELECTION_KEYS` with `SELECTION_KEYS`, and records the family's `equity_evaluator`.

---

## 5. book

### 5.1 Tables (`league/equity/live.py` `SCHEMA`, created by `EquityBook.__init__` through `LiveState.execute`)

```sql
CREATE TABLE IF NOT EXISTS eq_lots (
    lid INTEGER PRIMARY KEY, instance TEXT NOT NULL, family TEXT NOT NULL, version INTEGER NOT NULL,
    lane TEXT NOT NULL,                 -- beta | equity
    symbol TEXT NOT NULL, class TEXT NOT NULL,          -- etf | stock
    qty TEXT NOT NULL,                  -- Decimal string: shares held now (after splits)
    opened_qty TEXT NOT NULL,           -- shares bought
    entry_px TEXT NOT NULL,             -- average fill a share (split-adjusted)
    entry_notional TEXT NOT NULL,       -- dollars paid, fees excluded
    entry_at TEXT NOT NULL,             -- open | close
    fees TEXT NOT NULL DEFAULT '0',     -- dollars booked on the lot (SEC + TAF on its sale)
    div TEXT NOT NULL DEFAULT '0',      -- dollars of dividends credited (withholding negative)
    mark TEXT, marked_at REAL,          -- last mark a share; open risk uses entry_px when null
    opened_at REAL NOT NULL, opened_day TEXT NOT NULL,
    status TEXT NOT NULL,               -- open | closing | closed
    exit_px TEXT, exit_at TEXT, exit_day TEXT, closed_at REAL,
    cash TEXT NOT NULL DEFAULT '0',     -- net cash: -entry_notional + proceeds - fees + div
    reason TEXT,                        -- program | max_hold | house | demoted | retired | flatten | forced
    probe INTEGER NOT NULL DEFAULT 0,   -- 1: opened at Probe (counts in the shared loss budget)
    tag TEXT, iid INTEGER, info TEXT NOT NULL DEFAULT '{}');
CREATE INDEX IF NOT EXISTS eq_lots_status ON eq_lots(status);
CREATE TABLE IF NOT EXISTS eq_orders (
    eid INTEGER PRIMARY KEY, client_id TEXT UNIQUE NOT NULL,     -- lq-<eid>-<family>
    venue_id TEXT, instance TEXT NOT NULL, family TEXT NOT NULL, lid INTEGER, iid INTEGER,
    side TEXT NOT NULL,                 -- buy | sell
    symbol TEXT NOT NULL, class TEXT NOT NULL,
    at TEXT NOT NULL,                   -- open | close (its window)
    qty TEXT NOT NULL, limit_px TEXT NOT NULL, collar_bp INTEGER NOT NULL,
    status TEXT NOT NULL,               -- pending | working | unknown | filled | canceled | expired | rejected | lost | missed | refused
    placed_at REAL NOT NULL, day TEXT NOT NULL,
    filled_qty TEXT NOT NULL DEFAULT '0', avg_px TEXT, fees_est TEXT NOT NULL DEFAULT '0',
    replaces INTEGER,                   -- the eid this one replaces (cancel then resend, A8.4)
    probe INTEGER NOT NULL DEFAULT 0, why TEXT, answer TEXT, updated_at REAL NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS eq_orders_status ON eq_orders(status);
CREATE TABLE IF NOT EXISTS eq_fills (
    fid INTEGER PRIMARY KEY AUTOINCREMENT, eid INTEGER NOT NULL, lid INTEGER, venue_fill_id TEXT,
    qty TEXT NOT NULL, px TEXT NOT NULL, fees TEXT NOT NULL DEFAULT '0', at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS eq_intents (
    iid INTEGER PRIMARY KEY, instance TEXT NOT NULL, family TEXT NOT NULL, version INTEGER NOT NULL,
    decided_day TEXT NOT NULL, exec_day TEXT NOT NULL,
    at TEXT NOT NULL,                   -- open | close
    kind TEXT NOT NULL,                 -- buy | sell | cancel | house_exit
    symbol TEXT, lid INTEGER, share TEXT, usd TEXT, tag TEXT,
    status TEXT NOT NULL,               -- planned | sent | done | missed | refused | canceled
    why TEXT, ctx_sha TEXT, bars_sha TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS eq_intents_exec ON eq_intents(exec_day, status);
CREATE TABLE IF NOT EXISTS eq_bars (
    day TEXT NOT NULL, symbol TEXT NOT NULL, adjustment TEXT NOT NULL,   -- raw | all
    o TEXT, h TEXT, l TEXT, c TEXT, v TEXT, fetched_at REAL NOT NULL,
    sha TEXT NOT NULL,                  -- sha256 of the arrays the decision used (A8.11)
    audit TEXT,                         -- null | ok | mismatch (the morning re-fetch)
    PRIMARY KEY (day, symbol, adjustment));
CREATE TABLE IF NOT EXISTS eq_activities (
    id TEXT PRIMARY KEY, type TEXT NOT NULL, symbol TEXT, day TEXT, qty TEXT, net TEXT,
    booked TEXT NOT NULL,               -- JSON of the booking (actions.Booking)
    at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS eq_exports (lid INTEGER PRIMARY KEY, exported_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS eq_instances (
    id TEXT PRIMARY KEY, family TEXT NOT NULL, version INTEGER NOT NULL, lane TEXT NOT NULL, run_sha TEXT NOT NULL,
    code TEXT NOT NULL, params TEXT NOT NULL, band TEXT NOT NULL, seeded INTEGER NOT NULL DEFAULT 0,
    max_hold INTEGER NOT NULL, failed_decides INTEGER NOT NULL DEFAULT 0, last_decided_day TEXT,
    created_at REAL NOT NULL, retired_at REAL, why TEXT);
```

Key-values the book keeps in `kv` (live.sqlite): `eq_recon` {frozen, bad, good, problems, at}; `eq_freeze` {why, at}
(an unexplained corporate action, A8.10); `eq_activities_cursor`; `eq_decide` {day, status: done | failed | idle, at,
why} (the last decision day handled: A8.5's catch-up decide runs while it is behind the last close); book, as built:
`eq_synced` (the day the instances were last synced), `eq_decision` {day, start, end, symbols, shas, audit, mismatch}
(A8.11's provenance and the morning audit's verdict), `eq_bars_audit` {day: {symbols, at}} (the twin note),
`eq_sticky` {instance: why} (EDM1 demotions), `eq_band_since` {instance: {band, day}}, `eq_activity_refused` (watched
activity types the venue refused), `eq_preopen_activities`. The book reads the hooks' share-event ledger `shares`.

### 5.2 `league/equity/live.py`
- Constants: `WORKING`, `TERMINAL`, `LOT_OPEN`/`LOT_CLOSING`/`LOT_CLOSED`, `REAL_SUFFIX` ":r", `SHARE_TOLERANCE`
  1e-9, `CLIENT_PREFIX`; `client_id(eid, family, *, nonce="") -> "lq-<eid>-<slug>"` (<= 48 chars; book, additive: the
  book passes `LiveState.nonce`, so its ids are `lq-<nonce>-<eid>-<slug>`, as the options book's `lv-<nonce>-...`: a
  rolled-back state never repeats an id the venue has seen).
- Row functions (pure over `rows(sql, params) -> [dict]`, so the hooks and a restart read the same numbers; a state
  without `eq_lots` reads as empty): `probe_figures(rows, *, weights) -> ProbeFigures(programs: int, closes:
  ((ny_day | None, Decimal net cash), ...), open_risk: Decimal)` (ONE slot a program, A8.6; open risk = weight x mark
  value of open ":r" lots, entry price when unmarked, plus weight x remaining x limit of working ":r" buys);
  `expected_shares_rows(rows) -> {sym: Decimal}` (open lots + filled part of working buys, less the filled part of
  working sells not yet booked); `working_buys_worst(rows) -> Decimal`; `orders_today(rows, day) -> int`;
  `invested(rows) -> Decimal`. A program is a family (its versions' lots share one slot).
- `EquityBook(state, account, market, table, families, *, decider, stock_proof=None, sizing_equity=None,
  options_book=None, root=None, clock=None, record=None, alert=None)`:
  - `tick(now, *, account_row, positions, open_orders, real_block, killed) -> dict` (never raises);
  - `frozen` (str), `expected_shares() -> {sym: Decimal}`, `busy() -> set[str]`, `health() -> dict`,
    `flatten(why) -> int` (the rollback's first step: every open lot queued to exit through the normal path);
    `reconcile(positions, now=None) -> [problems]` (one reading; book, additive).
- Calls it makes: `league.equity.sizing.size_entry` (money), `league.live.money.available_cash` (money) with
  `working_buys_worst` = its own and `reserved` = the options book's `reserved()` (its working opens' maximum loss with
  fees and buffer: at least their worst cost, so no option buy is counted twice), `table.equity` (money's `EquityTable`),
  `league.equity.bands.next_band` (swarm) with `sized_up` / `edm1` (money) through it, `decider.kind("equity",
  "decide", {"jobs": [{"key": instance, "inputs": ctx.Inputs}]})` (hooks), `ctx.inputs_from_fetch` (core),
  `stock_proof.passed()` / `stock_proof.step(now, market=...)` (hooks), `families.read/add_forward/set_band/
  confirm_band` (own), `options_book.busy()`, `.exit_reserve()`, `.count_today(day)` (A8.3), `.reserved()` and
  `.exposure(...).book_loss` (the options open maximum loss in the invested cap, A1); `decider.kind_load("equity", key,
  {code, params, name, timeout, max_errors})` before a decide (its answer's `needs`; a `params` in it, the merged
  PARAMS, is used for the ctx when present) and `decider.kind_drop` at a retirement.
- **Decide (16:30)**: per live instance (its band "probe" or "sized" in `families.read()`, roster seat held), the
  16:20 bars (raw and all through t, `MarketData.bars(..., adjustment=...)`), `eq_bars` rows written with the arrays'
  sha, `Inputs` built, one "decide" kind request for every instance, intents validated and recorded in `eq_intents`
  with `exec_day` = `schedule.next_session(t)`, plus the House exits (max hold, demoted/retired/band-dropped, 2 failed
  decides) as `kind` "house_exit". A missed decide (restart) runs as a catch-up for the last close.
- **Pre-open (09:25)** and **the windows** as `schedule` and the module docstring say. Every open: `real_block(opening=
  True)` is None, `table.equity.enabled`, `stock_proof.buy_passed()` and not `stock_proof.sell_failed()` (A10.1,
  integration), not `frozen`, the program's band and seat, the loss budget's room (`budget_room` = the lower of the
  window's and the total's room, from `league.live.real.probe_figures` with the equity rows unioned in),
  `size_entry` > 0. Exits wait only on `killed()`, the min hold and `stock_proof.sell_passed()` (A10.1), the last
  only while `now < schedule.Moments.entry_until` (A28: the wait ends the minute open entries end).
- **Exports**: a closed lot -> `families.add_forward(family, "real", [{"id": "eq-<lid>", "version", "day" (exit day),
  "opened_day", "symbol", "class", "lane", "pnl" (net cash, float), "max_loss" (entry notional, float: so generic
  readers' pnl / max_loss is the net return on notional), "notional", "fees", "div", "return", "hold_sessions",
  "entry_at", "exit_at", "probe", "twin_key": "eq:<lid>"}])`, then `eq_exports`.
- Tests (DESIGN 11 EquityBook list + these): write before send, unknown then lookup, restart recovery mid-window
  (open and close), fractional partial fills, FIFO between two instances on one symbol, DIV and SPLIT booking,
  Decimal reconcile with assignment shares, one working order per symbol across both books, exits first then entries
  on post-fill cash, collar escalation and cut-offs, close-window repricing to 15:59:30 then missed, cancel then
  resend after a terminal state (a fill after the cancel), kill / stop / freeze block opens not exits, the day order
  cap, A8.5's exit rules.

### 5.3 `league/equity/schedule.py`
`DEFAULTS` (seconds): preopen_before_open_s 300, open_send_after_open_s 30, exit_wait_s 120, entry_until_after_open_s
900, exit_until_before_close_s 300, close_send_before_close_s 300, close_until_before_close_s 30, open_reprice_s 60,
close_reprice_s 30, bars_after_close_s 1200, decide_after_close_s 1800, audit_before_open_s 3600 (the constitution's
`equity_money.order_path` carries the ones in force, same keys). `PHASES`. `Moments(day, open_at, close_at, early,
preopen, open_send, entry_until, exit_until, close_send, close_until, bars_at, decide_at, audit_at)`; `moments(day,
offsets=None) -> Moments | None`; `next_session(day) -> date`; `phase(now, offsets=None) -> (phase, day)`. Half days by
offset. Book, additive: `audit_at` (open - `audit_before_open_s`), `offsets_of`, `is_session`, `previous_session`,
`sessions_between(first, last)` (sessions in (first, last]: a lot's held sessions), `ny_day`.

### 5.4 `league/equity/actions.py`
`DIVIDENDS` (DIV, DIVCGL, DIVCGS, DIVROC, DIVNRA, DIVTW), `ACTIONS` (SSP, SSO, REORG, NC, MA), `TYPES`;
`Booking(kind, symbol, day, per_lot {lid: {div, qty, entry_px, cash}}, why)`; `book_activity(activity, lots) ->
Booking` (pure; kind "freeze" for any other type touching a held symbol, A8.10). Book, additive: `Booking.unattributed`,
`.new_symbol`, `.as_dict()`; kinds also "spinoff" and "none"; `CASH_IN_LIEU` ("CIL") and `WATCH` (types read one by
one, best effort, beside `TYPES`).

### 5.5 `league/equity/families.py`
`EquityFamilies(root)` and `MemoryEquityFamilies(rows=())`: `read(family=None) -> [row]`, `forward_rows(family)`,
`add_forward(family, source, trades) -> int`, `set_band(family, band, reason)`, `confirm_band(expected, band,
reason) -> bool`; `validation_r_sd(state, version) -> float | None`. A row is `league.swarm.bands.read(root,
lanes=LANES)`'s (section 8.3) plus `validation_r_sd`. Book, additive: `last_error` ("" when the last `read` could read
the store: the book never retires an instance on an unreadable read) and `twins()` (the swarm store's `equity_twins`).

---

## 6. hooks

### 6.1 `league/live/equity_hook.py` (stubs present; thin forwards, fail closed)
`CLIENT_PREFIX`, `LANES`; `build_book(live) -> EquityBook | None`; `is_equity_client_id(cid) -> bool`;
`is_equity_row(row) -> bool`; `expected_shares(book) -> {sym: Decimal}` (raises when unreadable: the caller treats
every share as unexplained); `frozen(book) -> str`; `busy(book) -> set`; `probe_figures(rows, *, table) ->
ProbeFigures`; `working_buys_worst(rows) -> Decimal`; `orders_today(rows, day) -> int`; `invested(rows) -> Decimal`;
`open_risk(rows, *, table) -> Decimal`; `band_for(row) -> (band, why)`; `flux(book, rows, now) -> set[str]` (busy, or
an equity order changed in the last `FLUX_S`; raises when unreadable); `shares_taken(book, symbol, qty, px, *, why) ->
Decimal` (`Unreadable.shares_taken` raises).

### 6.2 Edits to league/live (keep them as small as possible; they move the options fingerprint once)
- **step.py**
  - `OptionsLive.__init__`: `self.equity = equity_hook.build_book(self)` after `self.book`.
  - `minute()`: exactly one `self.equity.tick(now, account_row=self.account_row, positions=<the minute's positions or
    None>, open_orders=<the minute's open orders or None>, real_block=self.real_block, killed=self._killed)` on every
    branch (closed, before the open, session, after the close), after the options path's own reads, in its own
    try/except (an equity failure never ends the options minute); its summary in `out["equity"]`.
  - `real_block`: also returns `f"equity reconciliation: {why}"` while `equity_hook.frozen(self.equity)`.
  - `_activities`: each OPASN / OPEXC books +/-100 x contracts on its underlying in the SHARE-EVENT LEDGER, kv
    `shares` {symbol: signed Decimal string} (A8.2; today it is never written).
  - `_close_shares` (A8.2, A8 wins over the brief's marketable limit and freeze): per us_equity symbol,
    unattributed = account qty - `expected_shares(...)[sym]` (lots + filled part of working orders, read in the same
    pass). A SHORT account qty is covered at once by exactly the account's short (market; whole shares first, the
    fraction at the next reading); lots it swallowed are marked (kv `lots_swallowed`) and closed in the equity book
    once proved gone. A LONG unattributed excess is sold after TWO consecutive readings (kv `unattributed_seen`
    {symbol: qty string}), market as today, with an alarm; on a symbol the equity book holds, only the part the
    share-event ledger explains (kv `unexplained_shares` for the rest, never sold). An account qty
    below what the equity book owns is a mismatch for reconciliation, never an order. Lots the equity book owns are
    never touched. A symbol with a working order in either book is skipped that minute. The ledger moves when an
    `lv-shares-` order fills.
  - `_stock_held` and `_resolve_latch` count only unattributed shares, so held equity lots never block entries.
  - `health()`: `"equity": self.equity.health()`; `"shares"` (the ledger, the House's share orders, a refused
    order's run, unexplained shares and swallowed lots).
  - `minute()` gives the equity book its minute when the options pass raises (the exception is raised again after
    it); `_equity_minute_spent` skips it only on hung account reads late in the minute (10 s or more in failed reads
    and the pass ended past second 45: summary `equity.skipped`, one warning a run); `_close_shares_safe`: a failure
    in the share handling never ends the options pass.
- **real.py**
  - `ingest`: skips client ids `equity_hook.is_equity_client_id` (as `lv-shares-`): never foreign.
  - `reconcile`: us_equity rows compare `expected = equity_hook.expected_shares(...) + shares ledger` as Decimal with a
    1e-9 tolerance (new keyword `equity_shares: Mapping[str, Decimal] | None`); `reconcile(..., equity_flux=())`:
    us_equity symbols in flux (`equity_hook.flux`) are not judged that reading.
  - `probe_tally`, `probe_realized`, `probe_figures`: union the equity rows (`equity_hook.probe_figures(rows,
    table=...)`): open_n += programs; at_risk += open_risk; the closes join the window's worst net stretch and the
    total by their NY day. Signatures gain `table` where they lack it (keyword, defaulting to the table in force).
  - The options reservation (A8.1, DESIGN 4a's row reinstated): reserve against min(`options_buying_power`,
    `money.available_cash(account, working_buys_worst=<both books>, reserved=<working reservations>,
    reserve_usd=table.equity.cash_reserve)`); cash < 0 refuses every open in both lanes and alarms.
  - `count_refusal` and the day count read both books (`equity_hook.orders_today`, A8.3).
  - `RealBook.exposure` fills `equity_open_risk` and `equity_invested`.
- **decider.py** (stubs present on `_Base`): `kind_load(kind, key, payload, *, budget_seconds=None) -> dict`,
  `kind_drop(kind, key, *, budget_seconds=10.0)`, `kind(kind, op, payload, *, budget_seconds=None) -> dict`. Message
  `("kind", kind, op, payload)`; the child's `_handle` answers `league.equity.kinds.module_for(kind).handle(op,
  payload, state)` with `state` kept per kind in the child; `Decider._ask` reloads remembered kind loads after a
  restart, as for options programs; `InlineDecider` the same in-process. The same isolation (uid 65534, netns, rlimits,
  empty env). decider.py imports `league.equity.kinds` only.
- **paper.py** (A8.7 as staged by A10.1, integration): `StockPaperProof(state, account, *, record=None, clock=None,
  alert=None)`, attempt row kv `paper_proof_stock`, stage records `paper_proof_stock_buy` and `paper_proof_stock_sell`:
  `step(now, *, market, window) -> dict` (`window` the book's `schedule.Moments` of the day: the proof trades in the
  book's OPEN window), `buy_passed()`, `sell_passed()`, `sell_failed() -> str`, `passed()` (both), `status() -> dict`.
  On `alpaca-paper`: stage BUY buys a fractional SPY marketable limit from the open window's first send to the entry
  cut-off and passes on its fill, its lot row and the reconciled position (gates every real equity BUY); stage SELL
  sells it in the next session's open window, first, and passes on the whole sale, the FILL activities and the
  position back at its baseline (gates every real equity SALE, AND THE WAIT HAS AN END, A28: `EquityBook._work_exit`
  holds an exit on `_sell_proof()` only while `now < m.entry_until`, the comparison `_work_entry` ends open entries
  on; from that minute every exit kind goes through the normal path, and `_sell_unproven(today)` tells the owner once
  a session: one error alert "the sale path is unproven today ..." with the stage's own reason (`_sell_stage_says`:
  `sell_failed()`, else `status()`'s status and why), one `equity.alert` record, kv `eq_sell_unproven` {day, why,
  at}; a close-window sale is past the cut-off by construction and never waits on the stage; stage BUY gates every
  real buy with no end); a SELL stage that ends its window unpassed is "failed" (an alarm with the owner's step; new
  real buys stop until it passes). Checked only by the equity book
  (options entries never wait on it). Client ids `lq-pp-...` (never `lv-`). `StockPaperProof` never waits for the
  options route's proofs (no `after`); `_idle` minutes read nothing of the practice account. An order the venue does
  not show by its client id after `STOCK_LOST_AFTER_TRIES` (4) lookups or `STOCK_LOST_AFTER_S` (600) seconds is lost
  (the book's `LOST_AFTER_TRIES`, `LOST_AFTER_S`; a test holds them equal): its record is {status "lost", terminal,
  lost, lost_at, lookups}, nothing owned, one warning through `alert`; a lost buy returns the row to "waiting", a lost
  sale goes again only while the position still reconciles; lost orders stay in the row's `orders` for
  `STOCK_LOST_WATCH_DAYS` (3) and are looked up again in every minute the proof works (`_found`: found again is one
  warning, `found` in the record, the attempt resumed at its last order or the stray's fills counted and the stray
  cancelled). The options `PaperProof` is unchanged.
- **venue.py**: `MarketData.bars(symbols, *, timeframe, start, end=None, adjustment="raw")` (the book reads "all" too).

### 6.3 `league/equity/kinds.py`, `league/equity/child.py` (stubs present)
`KINDS = {"equity": "league.equity.child", "panel": "league.xs.child"}` (A13: "panel" is a slot whose module refuses
every op), `module_for(kind) -> module`. `child.handle(op, payload, state) -> dict`
with ops `load` {key, code, params, name, timeout, max_errors} -> {ok, needs, sha, run_sha, params} (integration:
`params` the merged PARAMS the book builds the live ctx with, as the engine does: I6); `drop` {key}; `decide`
{jobs: [{key, inputs}]} -> {ok, results: {key: {intents, stats, ctx_sha}}}; `needs` {code, params, name} -> {ok,
needs, sha, run_sha}; `run` {code, params, name, bars, k, capital} -> {ok, result}. Refused program: {ok: False,
refused: True, error}. `decide` results carry `failed` (the runner's `last_failed`; True also beside `missing` and
`error`) and `why` when failed.

### 6.4 Tests
Each hook (`_close_shares` sells only the unattributed excess and never an owned lot; the two-reading rule; ingest
ignores `lq-`; reconcile accepts held lots and assignment shares; probe_tally applies 20% / 40% in the window and the
total with one slot a program; the reservation obeys the cash rule; count_refusal reads both books; real_block blocks
on the equity freeze); the decider kind (isolation, restart reload, deadline); the I6 test (20 random days, byte for
byte, core's helper); the isolation CI test (section 2.1); the stock paper proof.

### 6.5 Additive names, as built (hooks)
Nothing above changes; these are added beside it.
- `equity_hook`: `SHARE_TOLERANCE` (== `league.equity.live.SHARE_TOLERANCE`, a test holds it), `UNREADABLE`,
  `Unreadable(why)` (the book `build_book` returns when it cannot build one, or the table has no equity block, while
  live.sqlite holds an open lot or a working equity order: `frozen` names why, `expected_shares` and `busy` raise,
  `tick` does nothing), `health(book)`. `build_book` returns None (the lane does not run) when the table has no equity
  block and nothing is held. The row readers answer the empty figure, without importing league.equity's row functions,
  for a state with no `eq_lots` / `eq_orders` table. With a table that has no equity block, `probe_figures` weighs
  every class at 1 (fail closed).
- step.py: `_close_shares` covers exactly the account's short; a refused share order is alarmed (kv
  `shares_refused`); with the equity book unreadable it covers to flat and sells no long share. kv `shares_orders` {client id: {symbol, side, qty,
  filled, at}} (the House's `lv-shares-` orders, read back by client id each reading and before each reconciliation;
  a fill moves the ledger toward zero, never past it, and only when the order's side reduces it). The owner's
  `--clear-assignment` clears the ledger with the latch. `real_block` also refuses while the account row's `cash` is
  below zero (alerted once until it clears).
- real.py: `RealBook.free_to_reserve(account) -> (free: float, bound: str)` (the A8.1 reservation; a table without
  the equity block keeps `options_buying_power` alone); `RealBook.house_count(day)` (both books' count; `count_today`
  stays the options book's own, which the equity book reads); `probe_tally(..., table=None)` and
  `probe_realized(..., table=None)` (None: the table in force). `reconcile`'s share mismatch reads "SYM: <held> shares
  held, <want> expected (equity lots <x>, assignment shares <y>)", or "SYM: no shares held, ...".
- decider.py: `RUNTIME_FILES`, `runtime_files(repo=REPO)` (the root House's read-only child runtime: the options files
  plus league/equity/kinds.py `RUNTIME`); `kind()` refuses op "load" / "drop" (ValueError: use `kind_load` /
  `kind_drop`, which a restart replays); its deadline is `batch_deadline` of the jobs for "decide", else
  `budget_seconds` (30 s when None), so a 1200 s isolated run is not cut at `MAX_BATCH_SECONDS`.
- kinds.py: `RUNTIME` (what every kind's child may import: the 4 `LEAGUE_FILES`, league/gym/*.py, league/equity/*.py,
  league/xs/*.py (A13's panel slot) and the calendar's three `ltcm` files; a kind module that imports more names it
  here) and `runtime_files(repo)`.
- paper.py: `STOCK_KEY`; `StockPaperProof.step` reads `market.stocks(["SPY"])`; its witnesses are `buy_witness`,
  `hold_witness`, `sell_witness`, `activity_witness`, `recon_witness`; one attempt a session.
- venue.py: `BAR_ADJUSTMENTS` ("raw", "all").
- league/live/__main__.py (book, a pure addition): `--flatten-equity WHY`, `--clear-equity-freeze WHY`,
  `EQUITY_FLATTEN`, `EQUITY_CLEAR_FREEZE`, `equity_ask(why)`, and the status's `equity` block {freeze, reconciliation,
  pending_owner_actions}.

---

## 7. money

### 7.1 The constitution's `equity_money` block (league/constitution.py; `PINNED_DIGEST` re-pinned; the money digest
moves and the standing grant re-ratifies at the House's start)

```python
"equity_money": {
    "enabled": True,                        # A10.2 (integration): the switch ships on; False is the stop (CON-only)
    "universe": {"etf": ["SPY", "QQQ", "IWM", "DIA", "XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU",
                         "XLV", "XLY", "TLT", "GLD"],
                 "stock": ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "BRK.B", "JPM", "V", "UNH", "XOM", "JNJ",
                           "PG", "MA", "HD", "AVGO", "LLY", "COST"]},     # == gateway STOCK_UNIVERSE (league.ci)
    "position_share": {"etf": "0.50", "stock": "0.20"},
    "invested_share": "1.00",               # A1: cash only by choice; equity long + open equity buys + options open max loss <= E
    "cash_reserve_usd": "50",               # A8.1: above the gateway's $25 floor
    "open_risk_weight": {"etf": "0.20", "stock": "0.40"},
    "probe": {"sleeve_share": <the sleeve>, "max_programs": <the seats>, "min_order_usd": "10"},  # A5; section 17
    "sized": {"min_trades": 1000, "confidence": "0.80", "kelly_fraction": "0.25", "sleeve_share": "0.50",
              "beat_bh": True, "min_probe_sessions": 5},   # min_trades: 20 as pre-registered; PARKED at 1000 (section 16)
    "demotion": {"rule": "edm1", "min_trades": 10, "z": "1.645", "program_loss_usd": "-300", "twin_gap_bp": "15",
                 "twin_min_closes": 5},
    "holds": {"min_hold_sessions": 1, "default_max_hold_sessions": 20, "max_hold_sessions": 60,
              "failed_decides_exit": 2},                                                      # A8.5
    "order_path": {"entry_collar_bp": {"etf": 10, "stock": 25}, "max_collar_bp": {"etf": 50, "stock": 100},
                   "max_orders_day": 60,                                                      # A8.3
                   "preopen_before_open_s": 300, "open_send_after_open_s": 30, "exit_wait_s": 120,
                   "entry_until_after_open_s": 900, "exit_until_before_close_s": 300,
                   "close_send_before_close_s": 300, "close_until_before_close_s": 30,       # A2: 15:55:00 .. 15:59:30
                   "open_reprice_s": 60, "close_reprice_s": 30, "bars_after_close_s": 1200,
                   "decide_after_close_s": 1800, "audit_before_open_s": 3600},
},
```

Its comment says: THE LOSS BUDGET IS SHARED by both lanes: `options_money.probe.loss_budget_usd` ($400 net in any
rolling 20 sessions) and `loss_total_usd` ($800 net in total) bound every agent program's Probe opens, options and
equity, read by one `probe_tally`; a one-ETF program holds half its Probe sleeve, and the options Probe
lane keeps $400 less its realized loss less 0.20 x the equity lots; where whole sleeves ask for more than the account
holds, the invested cap (1.00 x E, 0.20 x E of open risk) bounds the lane (A8.6, stated in docs and the dlane
report). The figures at the seats and the sleeve in force are section 17's design block (at A20's design, section
16: three one-ETF lots of 0.25 x E, 0.75 x E of ETFs and 0.15 x E of open risk, with no cross-program cap binding).
`EQUITY_MONEY_BOUNDS` (beside `OPTIONS_MONEY_BOUNDS`) with each
row's owner's line at its loose end (tighten only): position_share.etf (0, 0.50], .stock (0, 0.20]; invested_share
(0, 1.00]; cash_reserve_usd [50, 200]; open_risk_weight.etf [0.20, 1.00], .stock [0.40, 1.00]; probe.sleeve_share
[0, 0.50] (A20: [0, 0.25] before it), max_programs [0, 6] (section 17: [0, 3] before it), min_order_usd [10, 100]; sized.min_trades [20, 1000], confidence [0.80, 0.99],
kelly_fraction [0.125, 0.25], sleeve_share [0, 0.50], min_probe_sessions [5, 60], beat_bh exactly True;
demotion.rule exactly "edm1", min_trades [1, 10], z [0, 1.645], program_loss_usd [-300, -25], twin_gap_bp [1, 15],
twin_min_closes [1, 5]; holds.min_hold_sessions [1, 1], default_max_hold_sessions [1, 60], max_hold_sessions [1, 60],
failed_decides_exit [1, 2]; order_path collars [1, 50] / [1, 100], max_orders_day [0, 60], offsets within the
session. `equity_money_problems(constitution=None) -> [str]` (in league/constitution.py beside
`options_money_problems`, which `Table.from_constitution` already imports from there; the brief said ci.py: this
follows the surrounding code, and ci.py calls it). Also: the universe's symbols and classes equal
`league.equity.config.UNIVERSE`, and position_share <= `config.POSITION_SHARE` (a test, money's).

### 7.2 `league/ci.py`
- `check_structures` (or a new `check_equity`, run by `check`) calls `equity_money_problems` and
  `gateway_stock_problems(root, table) -> [str]`: read from the files as `gateway_structures` reads
  `OPTION_STRUCTURES_REAL`: `gateway/lib/caps.mjs` `STOCK_UNIVERSE` (the frozen object's `SYM: 'class'` pairs) equals
  `equity_money.universe`; `gateway/wrangler.jsonc` `"STOCK_BUYS_REAL"` set once on its own line; `equity_money.enabled`
  True requires it "on" (A8: the gateway is deployed with it "on" while the House's `enabled` False is the switch, so
  "on" with `enabled` False passes); `position_share` <= `STOCK_ETF_EQUITY_SHARE` / `STOCK_SINGLE_EQUITY_SHARE`.
- FORBIDDEN gains `league/equity/` and `league/swarm/elane.py` (league/ops/ and league/live/ already cover the rest).
  The gateway's `MERGE_FORBIDDEN` cannot change in E1 (gateway/ is read only), so a new
  `PENDING_GATEWAY: tuple[str, ...] = ("league/equity/", "league/swarm/elane.py")` names them, and `test_ci.py`'s
  one-list test allows exactly `PENDING_GATEWAY` in `FORBIDDEN - gateway` (a gateway follow-up adds them there).

### 7.3 `league/live/money.py` (stubs present)
`Table.equity: EquityTable | None` (filled by `from_constitution` from `equity_money`); `EquityTable` (fields in the
stub; `from_constitution(constitution=None)`); `Exposure.equity_open_risk`, `Exposure.equity_invested` (Decimal,
default 0); `available_cash(account, *, working_buys_worst, reserved, reserve_usd) -> Decimal` = cash -
|short_market_value| - working buys' worst cost (both books) - working reservations - reserve (not clamped).
`invested_room(table, equity, exposure) -> Decimal | None`, `invested_refusal(table, equity, exposure, loss) -> str |
None` (A1 on the options side: equity lots and working equity buys + the options book's open maximum loss + the new
open at most `invested_share` x E).

### 7.4 `league/equity/sizing.py` (stub present)
`SizingInputs` (fields in the stub), `Sized(usd, qty, binding, reason)`, `size_entry(x) -> Sized`; bindings "intent",
"instrument", "sleeve_cap", "sleeve_cash", "invested", "cash", "budget", "min_order", "cash_negative", "short_held".
The book passes the live figures; the engine passes E = capital, `budget_room` None, `available_cash` = sleeve cash.

### 7.5 `league/equity/bands.py` (money's functions; stubs present)
`EquityRecord(n, returns, pnl, bh_pnl, probe_sessions, realized_net, twin_gaps_bp=(), validation_r_sd=None)`;
`sized_up(record, table) -> (bool, why)`; `sized_sleeve_share(record, table) -> Decimal`; `edm1(record, table) -> str
| None`. `table` is an `EquityTable` (attributes `sized_min_trades`, `sized_confidence`, `sized_kelly_fraction`,
`sized_sleeve_share`, `sized_beat_bh`, `sized_min_probe_sessions`, `probe_sleeve_share`, `demotion_min_trades`,
`demotion_z`, `program_loss_usd`, `twin_gap_bp`, `twin_min_closes`).

### 7.6 `league/ops/preopen.py`
Checks (each a `Check` row, `checks()` gains them): account cash >= 0; no short us_equity; equity reconciled (the
book's `health()["frozen"]` empty); gateway universe == constitution (`gateway_stock_problems` from the release's
files); multiplier and the PDT flag (`pattern_day_trader`, `daytrade_count`) reported (`info`), never a bar.

### 7.7 Tests
Bounds (each row in, at its line, past it refused), the digest moves and the grant re-ratifies (`test_ci`,
`test_constitution` patterns), the gateway agreement (a universe or switch that disagrees is refused), sizing table
cases (each binding), sizing-up and EDM1 cases.

---

## 8. swarm

### 8.1 `league/swarm/policy.json` "elane" block (and `settings.DEFAULTS["elane"] = {"mode": "off"}`, so the policy
layer's shape holds it to an object)

```json
"elane": {
  "mode": "off",
  "universe": ["SPY", "QQQ", "IWM", "DIA"],
  "structures": ["etf"],
  "birth_share": 0.0,
  "roster": 3,
  "screens": {
    "beta": {"name": "S1", "receipt_sha256": null, "c_R": null, "c_X": null, "fp_cap": null, "owner_wall": null,
             "retry": false, "r4": {}, "beside": null},
    "equity": {"name": "S1", "receipt_sha256": null, "c_R": null, "c_X": null, "fp_cap": null, "owner_wall": null,
               "retry": false, "r4": {}, "beside": null}
  },
  "val_tries": 1,
  "looks_per_lineage": 1,
  "program_loss_usd": -300
}
```

E1 merges with "off" (the rollback); the switch-on (ON) sets "gate". THE INTEGRATOR (A9) copied the receipt
`~/Work/.ltcm-main/scratch/eqlane-1010/equity_screen_1.json` VERBATIM to `docs/benchmarks/equity_screen_1.json` and
pinned it here: `receipt_sha256` (the file's bytes), `c_R`, `c_X`, `fp_cap`, `owner_wall`, `retry`
(`R3_retry_permitted`), `r4` (`R4_flags`), `beside` (`stated_beside_every_live_trade`). AS MERGED (A11) both lanes'
blocks pin RECEIPT 2 instead (`docs/benchmarks/equity_screen_2.json`, copied verbatim the same way): `"name": "S2",
"screen": "S2"`, `receipt_sha256`, `c_R` 0.0, `c_H_floor` 0.95, `c_H_margin` 0.05, `c_X`, `fp_cap`, `owner_wall`,
`retry`, `r4`, `beside`; receipt 1's file stays, pinned by no lane. Swarm tests hold each pinned sha to its screen's
file and each block to the file's figures, and `roster` == `equity_money.probe.max_programs`; at the look a receipt
file at hand whose bytes are not the pinned sha256 refuses the screen (`elane._receipt`; no such file reaches the
House box, where CI's pin of the exact commit stands for it). With no pinned receipt every equity look is refused.

### 8.2 `league/swarm/elane.py` (stubs present)
`MODES`, `STRUCTURES`, `LABELS` {"beta": "MARKET BETA", "equity": "EQUITY"}, `BETA_NOTE`, `SEEDED_NOTE`, `SEEDS_KEY`
"elane_seeds", `TRY_KEY` "elane_try", `DEFAULTS`; `cfg(settings)`, `on(settings)`, `lane_of(store, fam)`,
`label(lane)`, `card_errors(card, structure, symbols, settings)`, `lineage_key(lane, key)` (A8.12),
`screen_effective(settings, lane, *, policy=None)`, `try_open(store, fam, n, settings)`, `lineage_spent(store, fam,
settings)`, `roster_seats(root)`, `isolated_runner(root) -> runner.Isolated`, `validate(tournament, fam, version)`,
`look(gate, fam, version, sha) -> bool | None`, `birth_seeds(store, settings) -> [fid]`, `seeded(store, fid)`,
`view(fam, *, lane)`. Added by swarm (additive): `next_try(store, fam, settings) -> int | None` (the version the
tournament's equity round validates now), `lineage_tries(store, fid)`, `card_lane(card)`, `candidate(fam, store)`,
`reviewed(state, sha)`, `same_lineage(store, fam, lane, template, train)`, and the state keys `LOOK_KEY`, `FLOOR_KEY`,
`TRAIN_R_KEY`, `TEMPLATE_KEY`, `VALIDATION_KEY`, `VERDICTS_KEY` ("elane_verdicts" {str(n): {entered, at, stale}}),
`SIGMA_KEY` ("validation_r_sd_by_version"). The tournament and the gate take an injected runner as `equity_runner`.

### 8.3 Edits
- **bands.py**: `read(root, *, family=None, lanes=None)`: `lanes` None is the options lanes only (equity-lane families
  never reach the options path: no OptionsLive instance, no observe row, no incubator row); `lanes=LANES` returns the
  equity rows only, each with `lane`, `symbols`, `seeded` (and, added by swarm: `label`, `seat` "probe" | "seated" |
  "sized", `validation_version`, `validation_r_sd_by_version`, `beside`; a waiting Candidate has no row, so every
  Candidate row holds a seat: the book passes `seat_free=True` for it); an equity row's band currency is checked against the
  equity identity (`banded_evaluator` {"engine": EQUITY_ENGINE_VERSION, "equity_sha256", "run_sha"}), not the
  options one. `waiting()` / `seating`: equity Candidates take `elane.roster` seats apart from `dlane.roster`.
  `observe` and `incubator` never return an equity family.
- **store.py**: `SwarmStore.families(*, alive=None, lanes=None)` (section 2.5): None the options lanes only,
  `LANES` the equity families only, "all" everything; a family's lane is its spec's `lane`. `add_family` admits an
  equity structure ("etf" | "stock") exactly with an equity lane in the spec (the options readers tell the lanes apart by
  the structure column: `store.OPTIONS_ONLY_SQL`); lineages are lane-scoped (identical code links only inside a lane,
  `link_lineages` never joins an equity lineage to an options one, a fork stays in its parent's lane).
- **cards.py**: cards declare `lane`, `structure` ("etf" | "stock") and `symbols`; `validate` admits an equity card
  through `elane.card_errors`; the graveyard is lane-scoped (a REFUTED row binds only its own lane's cards; keys
  through `elane.lineage_key`).
- **gate.py**: an equity family's look goes to `elane.look` (on the House, `EquityGateCapability`, the lane's pinned
  screen: S2 under A11; a screen with no pinned receipt refuses: no look spent); the look event records lane, the
  screen that judged it ("S2"; "S1" under receipt 1), receipt, c_H (S2: c_H,used, with c_pF1; S1: with c_used) and the
  beside line.
- **tournament.py**: Validation dispatches by lane (equity -> `elane.validate`, run through the isolated runner on the
  House); `lane_forks` False for equity; one try a lineage (`elane.try_open`). `Tournament.equity_round` is called by
  the loop's equity rounds (section 14), never by `Tournament.run`.
- **settings.py**: the `elane` overlay (DEFAULTS block).
- **seeds.py**: `EQUITY_SEEDS` (three specs) and `equity_program_for(spec) -> (code, params)`, the programs written
  under the EQUITY.md contract (math and numpy only, no date):
  - `seed-overnight-spy`: NEEDS {"symbols": ["SPY"], "history": 2, "max_hold_sessions": 2}; each decision: sell the
    lot bought at the last close at the next open, and buy SPY at the next close (`"at": "close"`); PARAMS {"share":
    0.5};
  - `seed-overnight-qqq`: the same on QQQ, buying at the next close only when QQQ's close t < close t-1;
  - `seed-reversal-index`: NEEDS {"symbols": ["SPY", "QQQ", "IWM", "DIA"], "history": 2, "max_hold_sessions": 10};
    PARAMS {"theta": 0.02, "h": 8, "share": 0.25}: buy a symbol at the next open after a close at least theta below its
    prior close, exit at the open h sessions later.
  Each card names its published prior (Cliff, Cooper and Gulen 2008; Lou, Polk and Skouras 2019; Connors and Alvarez
  2008) and no figure.
- **loop.py**: `elane.birth_seeds` once a pass while the lane is on; `evaluator.adopt_equity` at start; THE EQUITY
  ROUNDS on their own thread (`equity_due`, `equity_rounds`: section 14).
- **dlane.py**: lane scoping only (A8.12): the always-in roots, `birth_spent` and the lineage links never join an
  equity family to an options lineage.
- **league/live/money.py** `band_for`: its first statement forwards an equity row to `equity_hook.band_for`.
- **league/equity/bands.py** (swarm's functions): `next_band(row, record, table, *, seat_free, sticky=None) ->
  (band, why)`; `band_for_row(row) -> (band, why)`.

### 8.4 Family state keys
`elane_try` {version, at, first, precheck, entered, retry_sha (A9 D3: the retry version's hash, recorded at the
first try)}; `elane_look` {version, at, verdict (screen.verdict), beside}; `banded_evaluator` for equity (above);
`validation_r_sd_by_version` {str(n): float} (the 1.0x Validation run's `summary.sd_net_return`); `elane_floor`
{version: screen.floor result}; `elane_train_r` (the looked version's Train daily r by session, House-only, for
`screen.same_lineage`; never in a view, never committed). Store kv: `elane_seeds` {seed id: fid}, `equity_evaluator`
(core's `EQUITY_KEY`).

### 8.5 Tests
Card admission, the lane graveyard, one try and one look per lineage (and R3's retry only when the receipt permits
and the first try failed its pre-check), A9 D3's same lineage (correlation >= 0.7 or the same template), receipt
refusal, roster seats apart from dlane's, seeded births (once each), options consumers skipping equity families
(generators and the diagnostician never read an equity look or Validation outcome), `bands.read` default excluding
equity rows.

---

## 9. screen (A9: the share screen as adopted)

**THE HOUSE SCREEN IS S2 (A11, landed):** the captain's A11 (final 23:30Z: receipt equity_screen_2.json, spec
sscreen2-1010/HOUSE-RULE.md). S2's code is in `league/equity/screen.py` beside S1's (below), its receipt is copied
verbatim to `docs/benchmarks/equity_screen_2.json` (sha256 45634dfc...) and both lanes' blocks of policy.json pin it
(`"name"` and `"screen"` "S2", `c_R` 0.0, `c_H_floor` 0.95, `c_H_margin` 0.05, `c_X` 0.85, `fp_cap` 0.12). The swarm's
look runs `floor(segments, receipt=)`, keeps a version's floor only while `floor_fits` the pinned receipt, passes an S1
floor of the same series as `s1_floor=` (S1-X's rate beside the S2 line) and records the screen that judged it
(league/swarm/elane.py). What follows describes S1+F1, which stays as receipt 1's screen, pinned by no lane.

`league/equity/screen.py` (stub present, already A9's): `SCREEN` "S1", `C_GRID_STEP` 0.01, `C_GRID_MAX` 5.00,
`H_LENGTHS` (194, 251), `V_LENGTH` 250, `WORLDS` 20,000, `MIN_POOL` 300, `WORLD_SETS` {"IND22": 3, "IND1622": 5},
`ACTIVITY_ROUND_TRIPS` 20, `ACTIVITY_INVESTED_DAYS` 120, `SAME_LINEAGE_CORR` 0.7, `RECEIPT_PATH`, `DEVIATIONS` (the A2
close-fill legs); `ScreenRefused`; `Receipt(receipt_sha256, c_R, c_X, fp_cap, owner_wall, retry, r4, beside, fp)`;
`Series(days, r, w, b, exits, invested)`; `receipt_sha256(path)`, `pinned_receipt(block) -> Receipt | None`,
`load_receipt(path, *, pinned_sha256) -> Receipt`, `series(lots, bars, *, universe, capital, first=None, last=None)
-> Series`, `excess(s)`, `precheck(v, *, variant="R")`, `pooled_t(v, h)`, `holdout_t(h)`, `look(v, h, *, c, c_H,
variant="R")`, `floor(segments, *, fp_cap) -> {eligible, why, c_p, c_H, sets, own_fp, drift_kept, worlds, seeds}`,
`label(v, h, *, c_X)`, `verdict(v, h, *, receipt, program_floor)`, `beside_line(result, receipt)`,
`retry_permitted(receipt, *, first_precheck_failed)`, `same_lineage(train_r, other_train_r, *, same_template=False)`,
`r4_flags(receipt, archetype=None)`.

Additions by the screen package (additive; every call above is unchanged):
- `floor(...)` also returns `fp_cap` and `curves` {set: {"194" | "251": {"R_N0", "R_N1", "X": pass counts on the c grid}}}
  (JSON, about 10 KB, House-only like the rest of `elane_floor`), so `verdict` reads the program's own FP and drift-kept
  rate at c_used and its S1-X FP at c_X without a second run; `fp_at(program_floor, key, c) -> float | None` reads them.
- `verdict(...)` also returns `why` (the first failed condition), `c_X`, `n`, `look`, `windows` and `fp_cap`; it fails
  closed (passed False) on a floor run at another fp_cap than the receipt's, and on windows outside the calibrated ones
  (V: calendar 2025's 250 sessions; H: 194..251 sessions inside `LOOK_FIRST`..`LOOK_CAP`).
- `retry_permitted(receipt, *, first_precheck_failed, tries=1, looks=0, retry_sha=None, recorded_sha=None)`: never a
  third try or a retry after a look; when either hash is given, the retry must be the version hashed at the first try.
- `look_permitted(looks, *, precheck_passed) -> bool`: one look a lineage, only after a passed pre-check.
- `Receipt.owner_wall` is None when a policy block names none (the docstring's required fields are unchanged).
- A close ENTRY counts 0 in w_t at its session (A2 extension: it holds no part of t's session; its half-spread is t's
  cost); a close exit counts as held through, as the pre-registration's forced close exit.

THE RULE (the receipt's `rule`, `precheck`, `look`, `floor`, `windows`, `lineage`): step 0 the floor on the program's
own Train-era series: c_p and c_H (F1: the holdout-only t's 12% point, with sum_H > 0), each the smallest c on
0.00..5.00 with the pass share <= fp_cap at BOTH L = 194 and 251, the maximum over IND22 and IND1622 where the program
has that history (D5); ineligible with no 300-session pool or a threshold above 5.00; c_used = max(c_R, c_p). Step 1
the pre-check on Validation. Step 2 after the one look: pooled t >= c_used, sum_H > 0 and t_H >= c_H. The holdout is
2026-01-02 .. min(the last close before the look, `config.LOOK_CAP`) (D6 said 2026-12-31; A12 made it 2026-10-09: the
194 calibrated sessions). S1-X labels alpha or beta (c_X, no floor, no
guard). Beside every live trade: the receipt's template filled (c_used, c_H, own FP, drift-kept rate from the
program's own floor run, S1-X label and FP, the contamination sentence). Lineage (D3): one look; R3's Validation-only
retry only after a FAILED pre-check (its version hashed at the first try); same lineage by Train correlation >= 0.7 or
the same template.

The receipt file is the study's (`docs/benchmarks/equity_screen_1.json`, copied verbatim by the integrator; keys
`name`, `study`, `rule`, `fp_cap`, `owner_wall`, `c_R`, `c_X`, `precheck`, `look`, `floor`, `windows`, `lineage`,
`fp_zero_edge_at_cR`, `power_at_cR`, `binding_R`, `R3_retry_permitted`, `R4_flags`, `stated_beside_every_live_trade`,
`note`, `sha256` (its inputs' shas)); `load_receipt` reads it, `pinned_receipt` reads policy.json's copy. Tests use only
`league/tests/fixtures/equity_screen_fake.json` (marked fake, the same keys); the study itself is never run here.

Call chain (swarm's `elane.look`): `pinned_receipt` (None: refuse) -> `Isolated.segments` -> `series` each -> `floor`
(ineligible: refuse, no look spent) -> c_used = max(c_R, c_p) -> the recorded Validation `Run` -> `series` ->
`precheck` -> `Isolated.look` -> `series` -> `verdict` -> `beside_line`.

Tests: the accounting on golden synthetic series (open and close fills, fees), the pre-check, the look (with the F1
guard), the floor on a synthetic store (both world sets, ineligibility), refusal without a receipt, one try and one
look per lineage (R3), `same_lineage`, the beside-every-trade line.

**S2 (amendment A11) exists beside S1** (spec sscreen2-1010/HOUSE-RULE.md). S1 and receipt 1
are unchanged and keep working. S2 is new code, not a settings switch: the look is the pre-check AND sum_H > 1e-12 AND
t_H >= c_H,used = max(c_H_floor, c_pF1 + c_H_margin) in integer grid steps, c_R = 0 (the pooled t is reported, never a
bar), c_pF1 by EXACT enumeration of holdout starts over IND22-NO and IND1622-NO at L 194 and 251; S1-X unchanged; the
holdout capped at 2026-10-09 (A12, `S2_LOOK_CAP`, with `config.LOOK_CAP` if earlier). Names: `SCREEN_S2` "S2",
`RECEIPT_PATH_S2`, `S2_SETS`, `S2_MIN`, `S2_LOOK_CAP`, `RECEIPT_KEYS_S2`, `BESIDE_FIELDS_S2`;
`ReceiptS2(receipt_sha256, c_R, c_H_floor, c_H_margin, c_X, fp_cap, owner_wall, retry, r4, beside, fp)`;
`pinned_receipt_s2(block)`, `load_receipt_s2(path, *, pinned_sha256)`, `floor_s2(segments, *, receipt) -> {screen
"S2", eligible, why, method "exact", c_pF1, c_H_used, fp_cap, c_H_floor, c_H_margin, sets, own_fp, holdout_only,
drift_kept, cells}`, `look_s2(v, h, *, c_H)`, `verdict_s2(v, h, *, receipt, program_floor, s1_floor=None)`,
`beside_line_s2(result, receipt)`; and for routing `screen_of(pin)`, `receipt_path(pin)`,
`floor_fits(program_floor, receipt)`.

ROUTING: the pinned block's `screen` (or `name`) picks the screen, and every public entry point routes on the receipt it
is handed: `pinned_receipt` (an "S2" block gives a `ReceiptS2`), `load_receipt(..., screen="S2")` (S1's default still
refuses receipt 2), `floor(segments, receipt=)`, `verdict(..., s1_floor=None)` and `beside_line` (receipt 2's
template). `floor(segments, fp_cap=)` with no receipt is S1's, so the swarm's look passes `receipt=` and keys its
cached floor with `floor_fits` (league/swarm/elane.py `look`; S1's `fp_cap=` call is only `_s1x_floor`'s, for S1-X's
rate). The study's receipt is copied VERBATIM to `docs/benchmarks/equity_screen_2.json` and pinned in policy.json
`elane.screens.<lane>` with `"name": "S2"` and `"screen": "S2"` (HOUSE-RULE section 9's block: receipt_sha256, c_R
0.0, c_H_floor, c_H_margin, c_X, fp_cap, owner_wall, retry, r4, beside, each copied from the receipt). The screen's own
tests use only league/tests/fixtures/equity_screen_2_fake.json (marked fake) and synthetic pools; the committed
receipts are judged only through the repository's pin (`test_the_committed_pin`, league/tests/test_elane.py).

---

## 10. ops

- **`league/ops/equity_data.py`** (stub present): `FIRST_DAY` "2016-01-04", `STORE_DIR`, `BARS`, `MAX_PAGES`,
  `SPLIT_JUMP`, `REGULAR_DAYS` 20, `REGULAR_TOLERANCE`; `fetch(gateway, symbols, start, end, *, adjustment,
  timeframe="1Day") -> {sym: [rows]}`; `regular_session_check(gateway, symbol, days) -> {verdict, days, mismatches}`;
  `audit(calendar, raw, adj, *, regular=None) -> {passed, checks}`; `run(ctx) -> dict`, writing through
  `league.equity.store.write_store(..., gate=True)`. The audit's calendar is `store.nyse_sessions` (2016+).
- **registry.py**: `Job("equity_data", "league.ops.equity_data", (S.at_start(), S.daily(<after the close, UTC>)),
  grace=..., in_pause=True, owner="equity lane", what=...)`, as `direction`.
- **dlane_report.py**: `read_book` also reads `eq_lots`; a close is one lot fully closed with net cash incl. fees and
  dividends, counted from 2026-10-10 (earlier closes beside), on `done_screen` (":r") and `done_all`; beside every close
  and checkpoint the BETA or EQUITY label, the same-risk buy-and-hold over the same sessions, MTE, the screen's FP
  (`screen.beside_line`), "profit from market direction"; Done WITH and WITHOUT the three seeded programs (A8.12); the
  A8.6 statement about the options Probe lane's window room. The Done rule is unchanged.
- **twins.py**: `equity_twin(lot, bars, *, k=1.0) -> {"key": "eq:<lid>", "status": "priced" | "no_bar" |
  "unpriceable", "final": bool, "live_return", "twin_return", "gap_bp" (a side), "entry_official", "exit_official",
  "judged_at"}` in closed form from the House's own official opens and closes (`eq_bars`, raw) with
  `league.equity.engine.fill_price` (open and close fills per A2), `config.sell_fees` and the lot's dividends; records
  under the swarm store kv `equity_twins`, final once judged. EDM1's twin leg and the Done rule's consistency read it.
  As built (ops, additive): `equity_twin(lot, bars, *, k=1.0, settled=True, at=None)`: `bars` is {ISO day: the
  symbol's `eq_bars` raw row}; `settled` (the exit day is `EQUITY_SETTLE_SESSIONS` 2 sessions past) makes a missing bar
  a final "no_bar" and an unaudited one final as it is (noted); a priced twin is otherwise final once both bars'
  `audit` is "ok" or "mismatch" (a mismatch is a `note`). `gap_bp` = (live net return - twin net return) / 2 x 10,000:
  NEGATIVE when the real fills did worse, so EDM1's "more than 15 bp a side" reads the magnitude (money). The record
  also carries `twin` {pnl, max_loss (its cost), r, ...}, `live`, `bh` {usd, return} (the cost-free same-risk
  buy-and-hold over the same sessions), `entry_slip_bp`, `exit_slip_bp`, `final`. The round is a House job,
  `equity_twins` (`league.ops.twins.run`; at the start, 01:15Z, open - 40 min), the only writer of kv `equity_twins`.
  The Done meter reads an equity lot's fees as posted only when the book marks the lot `info.fee_basis` "broker" (book:
  set it once the venue's SEC/TAF fees for the lot are booked; until then a checkpoint holding it stays provisional).
  The Done meters count from Oct 10, 2026 (the goal; `dlane_report.DONE_FROM`), every lane, earlier closes beside.
  The screen's line beside a trade (S2's under A11) is read from the passed look's `looks.detail` (`beside`, `screen`,
  and the verdict's figures at the top level or under `verdict`), else the family state's `elane_look` of that version
  (swarm, elane.py `look`).
- **funnel.py**: equity counts (births by lane, Validation tries, looks, passes, Probe programs, closes).
- **scripts/floor_box.py** (A8.9): `deploy` and `rollback` refuse a release that lacks `EQUITY_BOOK_MARKERS =
  (("league/equity/live.py", "class EquityBook"),)` while the box's live.sqlite has an `eq_lots` row with status
  "open" (read-only guard snippet, as the real-book guard); `--force-equity-risk` is the documented emergency path.
- **docs/operations.md**: the equity lane (switches: `equity_money.enabled`, `elane.mode`, `STOCK_BUYS_REAL`; the
  schedule; the rollback that flattens first: `elane.mode` off, then `enabled` False (exits only), then
  `EquityBook.flatten`, only then floor_box, with A8.9's guard; the stock paper proof; the cash-only choice (A1); the
  shared budget's consequence for the options Probe lane, A8.6), and the gateway's stock route as the House sees it
  (the "gateway README note on the House side": written here, since gateway/ is read only). **CHANGELOG.md** under
  "Not yet deployed".
- Tests: the data audit (synthetic: a gap, an insane bar, a split, a missing volume, the regular-session check), the
  Done meter with equity rows, twins, the floor_box guard.

---

## 11. The flows (who calls whom)

1. **Data**: ops `equity_data.run` -> gateway bars (raw, all) -> `equity_data.audit` -> core `store.write_store`.
2. **Birth**: swarm `loop` -> `elane.birth_seeds` -> `seeds.equity_program_for` -> store family (lane "beta").
3. **Validation**: swarm `loop.equity_rounds` -> `tournament.equity_round` -> `elane.validate` -> core
   `runner.Isolated.validation` -> hooks
   `decider.kind("equity", "run")` -> hooks `child.handle` -> core `runner.run_bars` -> `engine.run`; then screen
   `series` + `precheck`; swarm records `elane_try`, `validation_r_sd_by_version`.
4. **Look**: swarm `loop.equity_rounds` -> `gate.equity_round` -> `elane.look` -> screen `pinned_receipt` -> core
   `Isolated.segments` -> screen `series`,
   `floor` -> core `store.mint_equity_gate_capability` -> `Isolated.look` -> screen `series`, `verdict`,
   `beside_line` -> family to Candidate.
5. **Seat and band**: book `EquityBook` (16:30) -> book `families.read` (swarm `bands.read(lanes=LANES)`, seating) ->
   swarm `bands.next_band` (money `edm1`, `sized_up`) -> book `families.set_band`.
6. **Decide (16:20-16:30)**: book `schedule` -> `MarketData.bars` (hooks' adjustment) -> core
   `ctx.inputs_from_fetch` -> hooks `decider.kind("equity", "decide")` -> `child.handle` -> core `ctx.build`,
   `EquityRunner.decide` -> book `eq_intents`.
7. **Send (09:30:30 and 15:55)**: book -> `real_block`, `killed` (hooks, step.py) -> money `available_cash`,
   `sizing.size_entry` -> `Account.submit` (`lq-` client id) -> fills -> `eq_lots`.
8. **Every minute**: hooks `step.minute` -> `self.equity.tick(...)`; `_close_shares` and `reconcile` read
   `equity_hook.expected_shares`; `probe_tally` reads `equity_hook.probe_figures`.
9. **Close and Done**: book export -> forward record; ops `twins.equity_twin`, `dlane_report` Done meter.

## 12. Integration notes

- Merge order (each on CI green): core, money, screen, book, hooks, swarm, ops (later ones may lean on earlier names;
  every name already exists as a stub, so order affects only cross-package tests).
- A cross-package test that needs another package's implementation states so in its docstring and is expected to
  fail until that package lands; no package implements another's stub to make its tests pass (use a fake or a
  `MemoryEquityFamilies`-style double).
- The money digest (`PINNED_DIGEST`) is re-pinned once, by money; any later constitution change goes through money.
- A10.2 (applied at integration): `equity_money.enabled` ships True (one money-digest move with the block:
  7e41909a, full digest e909eb10, since A20's sleeve of 0.50 and the parked sizing-up step, section 16; ad8c761b
  and 65b0e025 with the sleeve at 0.25 and sizing up at 20 closes; the digests at the seats and the sleeve in force:
  section 17); `elane.mode` deploys "off" and the captain sets "gate" after the deploy is verified;
  receipt 2 is pinned for both lanes (A11: the S2 screen; receipt 1, A9's, stays in the repository, unused); nothing
  trades until a program passes its look AND the stock proof's BUY stage passes.

## 13. Where the briefs disagreed, and what this file follows

| point | brief or design said | this file follows |
|---|---|---|
| `_close_shares` | hooks brief: a marketable limit for assignment excess; freeze and never sell an unexplained excess | A8.2: a short covered at once (market) by exactly the account's short (the review: the gateway admits no larger buy; a lot it swallowed is closed as `forced`, never bought back); long unattributed sold after two consecutive readings (market) with an alarm, on a held symbol only the part the ledger explains; owned lots never touched |
| options reservation | DESIGN 4a moved it to a cash wall; A1 dropped that | A8.1 reinstates it: min(`options_buying_power`, House-wide available cash) |
| screens | DESIGN's EB and EQ, c_B, FP <= 10% | A7 as amended by A9: S1-R gates (c_used = max(c_R, c_p), and t_H >= c_H), S1-X labels |
| who writes `docs/benchmarks/equity_screen_1.json` | swarm brief: "which the screen package writes" | A9: the integrator copies the study's receipt verbatim and pins it in policy.json; the screen package reads it (screen.py) and tests with a fake fixture |
| the floor's worlds | screen brief: IND22, IND13 as the fallback, 2016-19 + 2022-24 stated as a deviation | A9 D5: the maximum over IND22 and IND1622 (the adopted rule, not a deviation); ineligible with no 300-session pool or a threshold above 5.00; plus c_H (F1) |
| the holdout | the store's holdout window (to 2026-09-25) | A9 D6 as amended by A12: 2026-01-02 .. min(the last close before the look, 2026-10-09), the 194 calibrated sessions (D6 had 2026-12-31) |
| a lineage | one try and one look per lineage | A9 D3: plus same lineage by Train correlation >= 0.7 or the same template; R3's retry only after a failed pre-check, hashed at the first try |
| where Validation runs | swarm brief: "in-process on the House" | A3: on the House, the program inside the decider-isolated child (`runner.Isolated`); never in the swarm process itself (it holds credentials) |
| Gym boxes, `driver.py` | DESIGN 6a: a bundle to Gym boxes | A3: none in E1 |
| `equity_money_problems` | money brief: in league/ci.py | league/constitution.py beside `options_money_problems` (the surrounding code), called by ci.py |
| protected lists | swarm brief: add elane.py to the lists the repo keeps | ci.py FORBIDDEN gains it and league/equity/; the gateway's list is read only in E1, so `PENDING_GATEWAY` names the difference |
| "a gateway README note on the House side" | ops brief | docs/operations.md (gateway/ is read only) |
| equity band rules | money brief and swarm brief both name league/equity/bands.py | one file, owned per function (section 1.1) |
| "families.py carries lane, structure and validation_r_sd" | swarm brief | `bands.read(root, lanes=LANES)` rows carry lane, structure, symbols, seeded (swarm); league/equity/families.py adds `validation_r_sd` (book); league/live/families.py is unchanged |
| `elane.roster` | swarm brief: in the policy.json block | in policy.json (the seats: section 17), with swarm.json over it, read failing closed as `dlane.roster` |
| probe sleeve, invested share, cash reserve | DESIGN 5: 0.30, 0.90, $25 | A5: 0.25 and max 3 programs, then A20 (Oct 11, 2026): the sleeve 0.50, three programs still (section 16), then the two set together (section 17); A1: "1.00"; A8.1: "50" |
| sizing caps Gym vs live | DESIGN: the same caps | `size_entry` applies the account cap AND the same share of the sleeve (`sleeve_cap`), so a live position is never a larger share of its sleeve than the Gym allows |
| ltcm.data's NYSE calendar | the data job's audit "NYSE calendar has no gap" from 2016 | that calendar starts in 2022; `store.nyse_sessions` computes 2016-2021 by the same rules (core) |

## 14. The review's fixes on the swarm, evidence and ops side (Oct 10, 2026; as built, additive unless it says so)

What the adversarial review of the E1 branch changed in the contract above. Where a line above and this section
differ, this section is the code.

- **The equity rounds have their own home** (swarm; CHANGES section 8.3 and flows 3 and 4). `league/swarm/loop.py`
  `Swarm.equity_due()` (the lane on and `elane.ROUND_SECONDS`, 300, since the store's kv `elane.ROUND_KEY`
  "elane_round_at"; never the guard, never `gym_ready`) and `Swarm.equity_rounds()` (on the round thread "equity":
  `Tournament.equity_round()`, then `Gate.equity_round(out)`; never raises) -> {validated {family: entered}, retired,
  errors, looked, held}. `validated` holds real verdicts only; a verdict carrying `error` or `refused` (no Validation
  was made, no try spent) is under `validation_errors` {family: the error | "refused: why"}, present when any (the
  verification's fix). `Tournament.run` and `Gate.run` no longer call the equity steps, and the hourly
  `swarm.tournament` row carries no `equity` key. The heartbeat's status carries `equity` {mode, round_at, and the
  last round's `validation_errors` when it left any (`Swarm.equity_unmade`)}.
- **The order of a round** (swarm): `elane.round_order(store, fams) -> [fam]`: by the second of birth, then by id,
  the seeds as one block in `seeds.EQUITY_SEEDS`' declared order (section 15.4 says which). Both equity rounds walk it.
- **Retirement causes** (swarm): `elane.SAME_LINEAGE`, `elane.FLOOR_INELIGIBLE`, `elane.REFUSED_BEFORE_LOOK`,
  `elane.REFUSED_CAUSES` {refusal stage: cause}: what `lineage_spent` answers for a version the gate refused before
  its look. `SPENT_TRY` and `SPENT_LOOK` are unchanged.
- **The lineage** (swarm, core): `evaluator.EQUITY_SELECTION_KEYS` is ("validation_r_sd_by_version", "elane_floor"):
  an adoption keeps `elane_train_r` and `elane_template` with `elane_look` (CHANGES section 4.11's list). `elane.same_lineage`
  raises `elane.LineageUnread(family)` for a looked-at family (or a living one with a look in flight) that keeps no
  Train series; `look` writes it again from that family's looked version (`Isolated.segments`) or waits.
- **The look and its runs** (swarm, core): `runner.RunLost(RunFailed)`: the child took the "run" whole and no answer
  came back (`Isolated._run`, by the decider's two failures of a taken request, `runner.SENT_NOT_ANSWERED`: it did not
  answer in time, it exited; every other failure, an answer that is not a result included, stays `RunFailed`). `elane.look` reads each
  run's status: a Train-era run not "ok" or "no_data" refuses the floor; "no_data" is passed to `screen.floor` as
  None; a holdout run that ended "disqualified" is a look spent and failed (its `detail` and verdict carry `status`
  and `why`); a `RunLost` at the sealed look is owed once, then spent and failed (`elane.LOOK_SENDS` 2, the family
  state's `elane.LOST_KEY` "elane_look_lost" {sha, count, at}; a `swarm.status` alert "equity_look_lost" each time).
- **The evidence child is deterministic** (swarm; hooks' file by a pure addition): `league.live.decider.Decider.hash_seed`
  (class attribute, None: the child starts exactly as before; an int: started without -E with PYTHONHASHSEED set, the
  same explicit environment otherwise). `elane.isolated_runner` sets `elane.EVIDENCE_HASH_SEED` (0) on its own child.
  The House's live decider is not pinned.
- **The ration** (swarm): `elane.next_try` first returns a tried version whose `elane_verdicts` entry is stale (the
  lowest first, while `try_open` allows it), then the candidate, then R3's retry. `elane_try.retry_sha` is recorded at
  the family's first recorded try and kept by every later Validation, None included.
- **Family state keys** (ADDS to section 8.4): `elane_look` also carries `activity` ({validation, train [per span],
  ratio}: the invested-day shares, House-only, never a condition); `elane_look_lost` (above).
- **The identity** (core): `evaluator.EQUITY_CALENDAR_FILES` (section 2.4). `EQUITY_EVIDENCE` is unchanged.
- **The store's slice** (core; CHANGES section 4.3's `bars`): `EquityStore.bars` and `span` put `history` + 1 sessions
  before the run's first (what the store holds), so `Bars.first` is `history` + 1 and the engine's first decision
  (the close of session `first` - 1) reads `history` + 1 rows, as a live decision does (I6 at the first decision).
- **The seeds** (swarm): each `EQUITY_SEEDS` spec and family record carries `provenance`; `elane.view`'s notes carry
  it for a seeded family.
- **ops**: `dlane_report.a14_consistency(counted) -> dict | None` ({closes, priced, unpriced, mean_gap_bp, bound_bp,
  fill_gap_ok, intents, consistent, why}; `A14_GAP_BP` 15.0, `A14_AGREEMENT` 0.95): a reading that holds an equity
  close carries it as `a14`, its item 4 is never True while the intents half has no reader, and it does not hold.
  `EquityScreens.of` returns `s1x` and `lane_label` (no `label`). `zero_edge(settings, *, equity_closes=0)` adds
  `applies_to`, `equity_closes`, `equity_note` (`ZERO_EDGE_EQUITY_NOTE`) when any is counted (since A50, Oct 16, 2026,
  on its `beside` block, the options rules' figure; docs/operations.md); `equity_beside` carries `zero_edge_note`. `funnel.equity_counts` reads Validation verdicts from the `swarm.status` events with action
  "elane_validation".

## 15. The review's fixes on the order path, the daily step and the hooks, and the rehearsal's (Oct 11, 2026; as built, additive unless it says so)

What the rest of the adversarial review and the rehearsal on real data changed in the contract above. Where a line
above and this section differ, this section is the code.

### 15.1 The order path (book; league/equity/live.py, league/equity/schedule.py, league/live/__main__.py)
- **Key-values** (ADDS to 5.1): `owner_equity_flatten` and `owner_equity_clear_freeze` {why, at, by}: written only by
  the owner's command (league/live/__main__.py), read first every minute and deleted by the book (`EquityBook._owner`).
  `eq_orders.answer` also carries `tick` (the minute's `now` the order was sent in; a re-price is aged from it in
  whole House minutes, `live.house_minute(t)` = the wall minute a pass started in, since two minute starts are 60 s
  apart give or take milliseconds; an order without it is aged in seconds from `placed_at`, exactly) and
  `retry` (true on a gateway refusal whose cap is in `RETRY_CAPS`); `eq_lots.info.exit_unread_told` (the day the
  owner was told).
- **Constants** (ADDS to 5.2): `OWNER_FLATTEN`, `OWNER_CLEAR_FREEZE`, `RETRY_CAPS` (positions, orders, equity,
  stock_close), `CLOSE_EXIT_WAIT_S` 60; `Order.again` (a refusal that is sent again: the House's rate or a
  `RETRY_CAPS` answer).
- **Calls**: `_send(..., tick=, until=) -> Order | None`: nothing is written or POSTed at or after `until` by the
  wall clock. `_end_stale`: an order the venue still shows working on a later New York day than its own is
  cancelled at the first minute that sees it. `_intent_lot`: a buy fill whose order and intent name no lot joins the
  open lot that intent already opened (one buy intent is one lot).
- **The windows** (CHANGES 5.2's and the module docstring's): the send times are effective, not nominal: the open
  window's first send is the 09:31 minute's and the close window's the 15:55 minute's, one re-price a minute at most;
  nothing is POSTed at or after a cut-off by the wall clock (09:45:00 an open entry; 15:59:30 every exit and every
  close entry). In the close window the entries wait for the window's exits to fill, or `CLOSE_EXIT_WAIT_S`, as the
  open window waits `exit_wait_s`; in either window an entry sized to nothing is not final while an exit may still
  fill (`_exits_due`): it is sized again each minute and recorded missed at its cut-off. When an exit is still
  unfilled after the wait, an entry that is cut but not to nothing goes at the smaller size. (The book's own kind,
  a share program: unchanged by release E4, and held to main's orders by `league/tests/test_equity_etf_orders.py`.
  An instance of the panel kind waits instead while an exit of its own program is working: `_cut_waits`, the panel
  kind's rule B8, league/xs/E4_INTERFACES.md section 17.)
- **The gateway's unread readings**: a refusal whose cap is in `RETRY_CAPS` is sent again next minute until the
  window's cut-off; it never ends an entry, never counts toward the three refusals that carry an exit, and widens no
  collar. A `403 {cap}` verdict is unchanged.

### 15.2 The daily step (book; league/equity/live.py, league/equity/families.py, league/equity/child.py, league/swarm/bands.py)
- **Key-values** (CHANGES 5.1): `eq_decide` {day, status: done | failed | idle, at, why, instances, seated_at}:
  `instances` names every instance asked for the day (decided, or its own decide failed); a record without it is
  closed to the seating pass. `eq_failed` {instance: the last decision day a failed decide was counted for it}.
  `eq_decision` also carries `volume` (symbols whose volume alone read differently). `eq_bars_audit` {day: {symbols,
  volume, at}}. `eq_instances.last_decided_day`: the last session the program was asked, including a session its own
  decide failed.
- **Decide** (ADDS to 5.2): THE SEATING PASS (`_seat_step`): once the day's decision is recorded, every minute until
  one minute before the next session's close window, a Candidate holding a seat goes to Probe, gets its instance and
  is decided for the same close on the same bars; nothing else moves in that pass. An instance is asked once a
  session. A failed decide is counted once a session, whatever failed (the House could not ask; the program's own
  decide failed; the morning audit found a price mismatch); a program the House could not ask is asked again every 10
  minutes until the next session's pre-open; one whose own decide failed has spent the session. A House exit rule
  that is due goes at the next OPEN even when the program planned its own `at: close` sale of that lot (that sale is
  recorded refused). `_record_of(family, version, row, *, refetch=False)`: only the daily band sync passes True.
- **The bars and the audit**: the day's fetch includes the symbol of every lot open, opened or closed that session,
  with no live program too. `_bars_verdict(...) -> "ok" | "volume" | "mismatch"`: raw open, high, low and close
  exactly, the as-of prices within `config.rounding_bound` (`_as_of_equal`), a volume-only difference a note. Each
  audited symbol's rows are marked on its own verdict; a day fetched again keeps its mark while its prices are
  unchanged (the volume is no part of it).
- **5.5** (CHANGES): `EquityFamilies.read` reads strictly (`bands.read(..., strict=True)`): a missing store, a failed
  read and a missing equity identity land in `last_error`. `standing(family, version) -> (code, why)`: the store's
  own word on one family; code is "retired" | "demoted" (`GONE`: the book retires on these alone) | "live" |
  "unknown". `MemoryEquityFamilies.hidden`: families `read` leaves out although they run.
- **8.3** (ADDS): `bands.read(root, *, family=None, lanes=None, strict=False)`: `strict` raises `EquityUnreadable`
  where the equity read answers [] for a store it could not read. `equity_proof_current(state, version) -> bool |
  None`.

### 15.3 The hooks (league/live)
- **EquityBook** (ADDS to 5.2; hooks' pure addition to the book's file): `shares_taken(symbol, qty, px, *, why) ->
  Decimal`: lots an assignment swallowed closed as `forced`, oldest first, at `px` or the lot's mark; never an order.
- The names of 6.1, 6.2, 6.5 and 7.3 are corrected in place above (`flux`, `shares_taken`, `equity_flux`,
  `_equity_minute_spent`, `invested_room`, the cover's size, the stock proof's wait).
- **The shared test venue** (league/tests/live_fakes.py `Venue.stock_refusal`): on the real account it refuses what
  the gateway refuses (a sale of more than held, a buy larger than the short on a symbol held short, a market buy
  that opens), so the gateway's rule is held in every live test.

### 15.4 The rehearsal on real data
- **4.2** (ADDS; core): `config.ADJUSTED_HALF_STEP` 0.005, `config.ROUNDING_GUARD` 1.5, `config.rounding_bound(*adjusted)
  -> float` (the largest relative move the vendor's cent rounding of these adjustment=all prices explains in a ratio
  or product built from them; ValueError for no price or one that is not a positive finite number). ONE bound for
  the engine and the book.
- **4.6** (CHANGES; core): `engine.ratio_tolerance(adj_prev, adj_now) -> float` (`RATIO_TOLERANCE`, or the rounding
  bound of the two adjusted closes when that is more); `split_factor(step, tolerance=RATIO_TOLERANCE)`. A ratio step
  inside its tolerance is no event, a split's factor may lie its tolerance above 1, and a dividend is what remains
  below 1 by more than it.
- **10** (CHANGES; ops): `equity_data.regular_session_check` -> {verdict, days, compared, mismatches, extended_days,
  mismatch_days}: the session's minutes run through the closing minute, the open is judged against the 09:30
  minute's range and the close against the closing minute's, the volume is not compared; `STRAY_DAYS_MAX` 2 ("extended"
  only above it, "regular" with at most that many stray days and none extended; no allowance on a reading shorter than
  `REGULAR_DAYS`). `audit`'s volume check passes a flat bar of volume 0 and lists it (`zero` {symbol: [days]}). A
  failed audit's receipt carries `problems` {check: the first `RECEIPT_PROBLEMS` (5) texts, every decimal figure
  masked}.
- **The seeds' order** (swarm; CHANGES section 14's): `seeds.EQUITY_SEEDS` is seed-overnight-qqq,
  seed-reversal-index, seed-overnight-spy, the declared order of the looks (the captain's decision before any
  Validation or look, from Train-era figures only, amendment A18; the two overnight seeds share a template and are
  one lineage). `elane.round_order` walks the seeds as one block in that order,
  standing where the first of them was born. WITHIN A LINEAGE THE ORDER IS STRICT (amendment A18; the verification's
  fix): each spec's `lineage` declares the lineage its seed is in ("overnight" for the two overnight seeds,
  "reversal"; read by the wait alone, no part of `equity_family_spec`). `elane.seed_owed(store, fam, settings) ->
  str | None` (why a seed has no verdict yet; None once it is retired, was looked at, or failed its Validation
  pre-check with no retry owed), `elane.seed_ahead(store, fam, settings) -> str | None` (the first seed declared
  before `fam` in its own declared lineage that is alive without a verdict) and `elane.seed_wait(store, fam,
  settings) -> str | None` (the seed `fam`'s look waits for; NO TIMEOUT; family state `elane.SEED_WAIT_KEY`
  "elane_seed_wait" {for, why, since, at, waited, asks, alerted}, `waited` counting only asks at most
  `SEED_WAIT_GAP_SECONDS` 600 apart; a `swarm.status` alert "equity_seed_waits" {ahead, why, minutes, repeat} once
  `waited` reaches `SEED_WAIT_SECONDS` 1800 and again every `SEED_WAIT_REPEAT_SECONDS` 86400 while it lasts;
  "equity_seed_wait_over" with `alert` false when a warned wait ends). `elane.look` asks it at its last step before
  the sealed run (the look waits: `gate_outcome` "waiting"; an order that cannot be read is a `look_failed` at stage
  "seed order" for a seed, nothing spent); `elane.seed_waits_over(store, settings) -> [family]` closes the waits that
  ended without being asked again (`Gate.equity_round` calls it last). `Swarm.equity_rounds`' answer carries `waits`
  {family: the seed it waits for} when any waits.

## 16. The Probe sleeve at 0.50 x E (the captain's A20, Oct 11, 2026; money; CHANGES 7.1, as built)

One row of 7.1's block and its bound, and nothing else of the contract. Where a line above and this section differ,
this section is the code; where this section and section 17 differ (the seats and the sleeve in force), section 17
is. (The study's rule picked 0.66 and the branch first carried it; the study's review adopted
it with a fallback to 0.50, which the captain took: at 0.66 the House cuts or refuses entries the Gym fills, and
Done's consistency clause, A14, reads that difference. docs/operations.md says it in full.)

- **7.1** (CHANGES; money): `equity_money.probe.sleeve_share` "0.25" -> "0.50";
  `EQUITY_MONEY_BOUNDS["probe.sleeve_share"]` ("0", "0.25") -> ("0", "0.50"). `probe.max_programs` 3 and first-come
  seating are unchanged. THE SIZING-UP STEP IS PARKED with it: `equity_money.sized.min_trades` 20 -> 1000 (inside
  its bound ("20", "1000"), a tightening), so `sized_up` answers False for every record under 1000 real closes and
  no equity program is Sized: every equity close keeps its Probe mark and stays in `probe_figures`' closes (a Sized
  lot's would not). The rule is as pre-registered; the row is switched back only with a change that counts Sized
  closes in the budget. `PINNED_DIGEST` is re-pinned: money digest 7e41909a, full digest
  e909eb10 (the stop, `enabled` False: 23f17a14; the sleeve's rollback, "0.25" with the step still parked:
  3a7c52d5; both rows back, the block as the branch carried it before A20: ad8c761b). No evidence
  module of league/equity changes: the equity identity does not move. `league/live/money.py`'s comment on
  `EquityTable.probe_sleeve_share` is corrected to the row in force (a comment only; the file is in the options
  execution fingerprint, which E1 moves once anyway).
- **7.4** (unchanged code; what it now yields): `size_entry`'s "sleeve_cap" holds a program's position in one ETF to
  `position_share.etf` (0.50) of its sleeve, so a one-ETF program's lot is 0.25 x E (0.125 x E before). THREE SUCH
  LOTS FIT WITH NO CAP BINDING (0.75 x E). The owner's lines bind as before, by name: "instrument" (an ETF at most
  0.50 x E across all programs: two programs in one ETF hold exactly 0.50 x E together, a third is refused),
  "invested" (at most 1.00 x E: a fourth lot fills it and the next entry is refused), "cash" (the $50 reserve: it
  cuts that fourth lot when E is the account's own equity), "budget" (the shared loss budget's room over the ETF
  weight 0.20: from E = $2,667 it cuts the third one-ETF lot).
- **7.5** (unchanged code; what it now yields): `sized_sleeve_share` is max(`probe_sleeve_share`, min(quarter Kelly
  on the lower bound, `sized_sleeve_share`)), floored to four places. `sized.sleeve_share` stays "0.50", now EQUAL to
  the Probe sleeve, so the answer is 0.50 for every record: a Sized program would keep the Probe sleeve and size
  nothing up. A lot bought while Sized would carry no Probe mark (`eq_lots.probe` 0: its close joins neither
  `probe_figures`' closes nor the record's `realized_net`); its open value still counts as open risk.
- **10** (CHANGES; ops): `dlane_report.options_probe_room(equity_usd, constitution=None)` takes the LOWER of the
  sleeves (`max_programs` x `sleeve_share`) and `invested_share` as the lane's largest share of E, and never reads its
  open risk in dollars above the window's budget. ADDS to its answer: `invested_share` (str | None),
  `invested_share_of_e` (float), `bound` ("sleeves" | "invested_cap" | "budget"). At the table in force three whole
  sleeves ask for 1.50 x E, so `open_risk_share_of_e` is 0.20 and `bound` "invested_cap" (the lane's most; three
  one-ETF lots hold 0.15 x E of it). `EQUITY_PROBE_NOTE` carries both figures.
- **The gateway** (read only, unchanged): one order and one ETF's position of 0.25 x E are under
  `STOCK_ETF_EQUITY_SHARE` (0.5 of the account's equity, which E is never above); the lane at 1.00 x E is inside its
  book line on a multiplier of 1; `STOCK_DAY_EQUITY_MULTIPLE` (4x equity of buys a day, a cancelled one too) admits
  sixteen sends of such a lot a day: three entries can each climb the collar's ladder of five sends
  (`league/tests/test_ci.py`).
- **Tests** (money): `league/tests/test_equity_sleeve.py` (new: the lane by hand through the real `size_entry` at
  the table in force: three lots with no cap binding, the fourth against the invested cap and the cash reserve, one
  ETF and the instrument cap, the budget, a Sized program's sleeve); the pins moved in `test_constitution`,
  `test_equity_money`, `test_equity_bands_money`, `test_ci`, `test_dlane_report_equity`, `test_equity_e2e`,
  `test_live_long_single`. The book's harness (`test_equity_book.equity_table`) keeps an INVENTED table (a sleeve of
  0.25 x E, a stubbed Sized share), and says so: its scenarios are built by hand on that sleeve's dollars and test
  the book's plumbing, not the table.

## 17. The seats and the sleeve are two numbers (release E5-S, Oct 11, 2026; money and swarm; CHANGES 7.1, 8.3, 10, as built)

`equity_money.probe.max_programs` (the seats) and `probe.sleeve_share` are set TOGETHER, by one mechanical step, and no
code, test or document names the pair in force outside the places that step writes. Where a line above and this
section differ, this section is the code.

<!-- equity-design:begin -->
THE DESIGN IN FORCE: 6 seats (`probe.max_programs`, `elane.roster`), a Probe sleeve of 0.25 x E
(`probe.sleeve_share`). A one-ETF program's lot is `position_share.etf` (0.50) of its sleeve: 0.125 x E.
A lot in every seat asks for 0.75 x E of ETFs; the lane holds at most 0.75 x E of them, 0.15 x E of
open risk at weight 0.20. One ETF across programs (the instrument cap, 0.50 x E): 4 whole lots fit; the
next program's lot of it is 0.00 x E. At E = $2,000, the account all cash and nothing realized: 6 of
6 whole lots fit under the invested cap (1.00 x E) and the $50 cash reserve alone, and
6 of 6 in the $400 window alone; the window alone holds all 6 up to E = $2,666.
Whole sleeves (programs that hold several ETFs) ask for 1.50 x E; the lane holds at most 1.00 x E,
0.20 x E of open risk. The options Probe lane keeps $400 less the window's realized loss less 0.20 x
the equity lots: $400 - 0.15 x E against the one-ETF lots above. The gateway's day line (4x
equity of buys a day, a cancelled one too) admits 32 sends of such a lot: 6 entries can each climb the
collar's ladder of 5 sends. A Sized sleeve (the step is parked) would be between 0.25 x E and
0.50 x E.
Money digest `055e5313`, full digest `a8d4cbd9` (`PINNED_DIGEST`); the rollback, `set_design 3 0.50`, is `8581de70` / `c9515d5f`.
<!-- equity-design:end -->

- **`set_design SEATS SLEEVE`** (the captain's tool; not a module of the tree) rewrites exactly: the two rows of
  7.1's block; `elane.roster` in league/swarm/policy.json and `DEFAULTS["roster"]` in league/swarm/elane.py (the
  seats are written in three places: `league/tests/test_elane.py` holds them equal, and the default is also the
  bound of a `swarm.json` setting, which may only lower it); `PINNED_DIGEST`; and the four design blocks (this one,
  the constitution's `probe` comment between `# <equity-design>` and `# </equity-design>`, docs/operations.md and
  CHANGELOG.md between `<!-- equity-design:begin -->` and `<!-- equity-design:end -->`). Run again with the same
  pair it changes nothing; `set_design 3 0.50` restores A20's seats and sleeve (on release E5-S alone that was E1's
  money digest, 7e41909a, exactly; since release E5-A's seat block, section 18, it is the pair's pin with that
  block, and 7e41909a with the block left out). It
  refuses, changing nothing, a pair outside THE GRID below (the tests pin each of its pairs' digests and hold the
  tree to one of them) and a design block whose words are not the tree's own; a block whose figures alone are stale
  it rewrites. `sized.sleeve_share` is NOT moved: the Sized sleeve's floor is the Probe's in `sized_sleeve_share`
  itself, and no Probe sleeve inside its bound is above 0.50, so the row is never under the Probe's at any pair
  (7.5 below).
- **7.1** (CHANGES; money): `EQUITY_MONEY_BOUNDS["probe.max_programs"]` ("0", "3") -> ("0", "6"); the sleeve's bound
  stays ("0", "0.50"). The bounds are not part of the constitution's digests: a pair alone moves them. The
  constitution's `probe` comment keeps A20's record and says what the two numbers are, why, and their cost.
- **THE GRID** (the pre-registered study EQDONE-3: seats 3, 4, 5, 6 x sleeve 0.50, 0.33, 0.25): each pair's money
  digest and full digest are pinned in `league/tests/equity_design.py` `DIGESTS`; `test_constitution` holds the tree
  to the pin of its own pair and every pair's copy of the constitution to its own.
- **7.4** (unchanged code): `size_entry` is not edited (it is evidence code; the equity identity does not move). What
  it yields at each pair is the design block's arithmetic: a one-ETF lot is half the sleeve; the whole lots that
  fit under the instrument cap, under the invested cap with the cash reserve, and in the window, are counts of the
  pair; past them the entry is cut or refused BY NAME, as at any sleeve.
- **7.5** (unchanged code): `sized_sleeve_share` is max(`probe_sleeve_share`, min(quarter Kelly on the lower bound,
  `sized_sleeve_share`)): the Probe's own share where the Probe sleeve is 0.50, between the Probe's and 0.50 under a
  smaller one. The step is parked at any pair (`sized.min_trades` 1000).
- **5 (the book; unchanged code, now tested)**: at a deploy that moves the pair, (a) a Candidate that waited for a
  seat is seated at the first band sync (`bands.read(lanes=LANES)` shows it once `elane.roster_seats` has room,
  first come; `_sync_instances`, in the seating pass or the day's decision, moves it to Probe while
  `live_n < probe_max_programs`), and nothing else moves; (b) a planned buy is sized at its send
  (`_work_entry` -> `_size`: `_sleeve_share(inst) x E` of the table in force), a `share` intent to that share of
  the sleeve in force, a `usd` intent cut to its caps; (c) no lot is sold for a size (`_house_exits` knows the hold,
  the failed decides and a retired or demoted program only), and seats moved down unseat nobody (a Probe row keeps
  its seat: `next_band`, `seating`).
- **8.3** (CHANGES; swarm): `elane.DEFAULTS["roster"]` and policy.json's `elane.roster` are the seats in force; the
  docstrings no longer name a count. `roster_seats(root)` is unchanged: `swarm.json`'s value, at most the default.
- **10** (CHANGES; ops): `dlane_report.equity_probe_note(constitution=None) -> str` builds A8.6's statement from the
  rows (`EQUITY_PROBE_SENTENCE`; `EQUITY_PROBE_BARE` when a row cannot be read); `EQUITY_PROBE_NOTE` is the
  statement at the constitution in force; `options_probe_room(...)["statement"]` is the statement of the
  constitution it was given. Its words changed: "N one-ETF programs ask for a lot of L x E each, of which the lane
  holds at most H x E, R x E of open risk" (true at a pair whose lots do not all fit under the invested cap).
- **The gateway** (read only, unchanged): at every pair a one-ETF lot is under `STOCK_ETF_EQUITY_SHARE` and the lane
  at 1.00 x E is inside the book line on a multiplier of 1. `STOCK_DAY_EQUITY_MULTIPLE` (4x equity of buys a day, a
  cancelled one too; a ceiling in the gateway's code) admits the block's count of sends of one lot; a pair with
  more seats than the block's count of whole ladders fits its ordinary day (one send an entry) and not a day every
  entry climbs the collar's whole ladder (`league/tests/test_ci.py` `DAY_LINE`, `WHOLE_LADDERS`): the gateway then
  refuses the sends past its line (`stock_day`), that entry is missed, nothing is sold.
- **Not edited, and stale by a comment**: league/live/money.py's comments on `EquityTable.probe_sleeve_share`
  ("0.50") and `probe_max_programs` ("3 (A5) == elane.roster") name A20's design. The file is inside the options
  execution fingerprint, which this release must not move, so the two comments stand until a release that moves
  that fingerprint for its own reasons; the code beside them reads the rows.
- **Tests**: `league/tests/equity_design.py` (the rule written out by hand, the closed forms, the grid, its digests,
  the design blocks), `test_equity_design.py` (new: every pair at a stated E through `size_entry`, the blocks held
  to the rows, the deploy's cases through the real book and the real swarm store), `test_equity_sleeve.py`
  (A20's scenarios at A20's design as a table of its own; every pair against the hand rule), and the tests that
  named the pair, which now read it: `test_constitution`, `test_ci`, `test_elane`, `test_equity_money`,
  `test_equity_bands_money`, `test_dlane_report_equity`, `test_equity_e2e`, `test_live_long_single`.

## 18. The seat rule (release E5-A, Oct 11, 2026; the captain's A24 with A30; money, swarm and book; CHANGES 5.5, 7.1, 8.3, 8.4, 10, as built)

Who takes a free equity seat, and when an idle seat yields. Where a line above and this section differ, this section
is the code. "First come" above describes the rollback value. THE RULE IN FORCE IS A24 AS A30 AMENDED IT before it
went live (20:47Z Oct 11, from the release's independent check): free seats first is A24's reading; the idle clock
does not run in a session in which the House refused every open; a lost buy is not flat while the book may still
take it back. Stated and accepted by A30, not changed: a daily quarter-sleeve slice buys rank and immunity from the
idle rule.

- **7.1** (CHANGES; money): `equity_money.probe.seat` = {`rule`, `k_floor`, `idle_sessions`}, in force
  {"activity-1-free", "0.25", 10}. `EQUITY_MONEY_CHOICES["probe.seat.rule"]` = ("activity-1-free", "first-come");
  `EQUITY_MONEY_BOUNDS`: `probe.seat.k_floor` ("0.25", "0.25"), `probe.seat.idle_sessions` ("10", "60"), a whole
  count. A table without the block is refused (`equity_money_problems`). The block is attached to the `probe` dict
  under the table's literal, because `set_design` rewrites the `probe` row by its exact line. It is a money rule:
  the money digest and `PINNED_DIGEST` moved once with it, and every pair of section 17's grid with them
  (league/tests/equity_design.py `DIGESTS`; `DIGESTS_E5S` keeps the pins before the block). `EquityTable`
  (league/live/money.py, inside the options execution fingerprint) is NOT edited and carries nothing of the block.
- **The reader and the pure rule** (league/equity/bands.py; owner: swarm; no clock, no I/O):
  - `seat_settings(constitution=None) -> SeatSettings(rule, k_floor, idle_sessions)`; `.first_come`. A block that
    is absent or cannot be read is `SEAT_FALLBACK` ("first-come").
  - `close_days(lots, *, floor) -> int`: the days on which the lots that closed (`exit_day`) have `weight`s summing
    to at least `floor` - `K_TOLERANCE` (0.0005). Decimal sums. It reads those two fields and nothing else.
  - `seat_counts(validation_result, train_results, *, floor) -> {"floor", "validation": {"close_days", "sessions"},
    "train": {"close_days", "sessions"}}`; a "no_data" Train-era run adds nothing; any other run not "ok" raises.
  - `seat_k(activity) -> Fraction | None`: min(Validation close days, Train-era close days x 250 / Train-era
    sessions); None when the counts cannot be read.
  - `SeatFacts(family, k, passed_at, flagged, seeded, seat_day, seated_sessions, quiet_sessions, flat)`;
    `seat_key`, `seat_order` (not flagged, a readable K, the higher K, the earlier pass, the id); `seat_idle(facts,
    settings)`; `seat_yielder(idle)` (the lowest K, the latest seated, the latest pass, the higher id).
  - `seat_plan(holders, waiting, *, seats, settings, late=False, yielded_today=False) -> {"idle", "yields", "for",
    "queue", "seat"}`: the plan of one band sync. FREE SEATS FIRST (A30 (1): A24's reading); then one idle seat
    yields for the best-ranked unflagged program that would still wait. The study's simulator ran the idle test
    before the seating, so its measured gain of the rule is the gain under that slower order.
    league/tests/fixtures/equity_seat_vectors.json holds 31 vectors of it. `SeatFacts.seated_sessions` and
    `quiet_sessions` are the book's counts, which leave out the sessions in which the House refused every open.
- **The seal** (swarm, league/swarm/elane_seal.py): `elane_seat` is in `SEALED_KEYS`. No generator reads the two
  counts, the gate's events that carry them or the book's plan (league/tests/test_equity_seats_seal.py: two worlds
  that differ only in K give every generator the same bytes).
- **8.4** (CHANGES; swarm, league/swarm/elane.py): the family state's `elane_seat` (`SEAT_KEY`) = {version, run_sha,
  floor, validation {close_days, sessions}, train {close_days, sessions}, at, source "look" | "backfill",
  validation_run "look" | "stored" | "rerun"}, written ONCE. `look` writes it with the look, from the recorded
  Validation run and the Train-era runs it already made (it keeps the `Run`s of `Isolated.segments` for this).
  `seat_backfill(gate) -> [family]` (called at the end of `Gate.equity_round`, league/swarm/gate.py) writes it
  for a Candidate, Probe or Sized family that has none: the Validation count from the stored run whose
  `result_sha` is `elane_validation.result_sha` (`SwarmStore.run_result`), else `Isolated.validation` again; the
  Train-era count from `Isolated.segments` again. No gate capability, no `Isolated.look`, no sealed window; a
  failure is one House warning and is tried again after `SEAT_RETRY_SECONDS`. `seat_recorded`, `seat_activity`
  read it. An equity identity adoption keeps the key (it is not in `EQUITY_SELECTION_KEYS`).
- **8.3** (CHANGES; swarm, league/swarm/bands.py): `read(root, lanes=LANES, queued=True)` (and `_read_equity`):
  every passed Candidate that could hold a seat has a row; a Candidate's `seat` is "queue"; every row carries
  `passed_at` (`banded_at`) and `seat_activity` (`elane.seat_activity`: the two counts, or None). The default read
  is unchanged, key for key. `seat_plan(root)` reads the book's kv `eq_seat` from live.sqlite, read only;
  `roster(root, lanes=LANES)` adds `rule`, `plan` and `order` (its own lists stay by pass time and say so).
- **5.5** (CHANGES; book, league/equity/families.py): `EquityFamilies._rows` asks `queued=True` unless the rule is
  "first-come" (then the call is release E5-S's, argument for argument); `seats() -> int` is `elane.roster_seats`,
  0 when closed or unreadable. `MemoryEquityFamilies(rows, seats=None)`: `seats()` None means the table's count.
- **5.5** (CHANGES; book, league/equity/live.py): `_sync_instances` under "first-come" is release E5-S's band sync
  (two additions that a state of release E5-S never meets: a yielded instance whose band is live again is brought
  back in the seating pass too, and a seated program's idle flag is dropped from the plan).
  Otherwise `_seat_bands`: the holders judged as before (EDM1, sizing up); EDM1 over waiting programs with a
  record (kv `eq_sticky`); `bands.seat_plan` on `_seat_facts` (`_flat`, `_last_ask`, the seat's first session from
  `eq_band_since`, both counts less `_refused_days`); `_yield`; the queue walked with fall-through (EDM1 at a
  seating: sticky, `waiting_demoted`, the warning, the flag dropped, out of the waiting list). The seating pass
  (`late`) fills free seats only, and revives a yielded instance that returns. The plan is kv `eq_seat`
  (`SEAT_KEY`): {rule, seats, idle_sessions, day, holders [.. seated_sessions, quiet_sessions, left_out ..],
  waiting, idle, sticky, passed, yield_day, left_out [{day, why}], last, order}; `seats()` and `health()["seats"]`
  return it. Ledger kind `equity.seat` (private): {action "seated" | "yielded" | "returned" | "passed_over" |
  "waiting_demoted", family, version, day, rank, for, seeded, rule, why}.
  - `_flat(key)` (A30 (3)): no lot open or closing, no intent planned or sent, and no order that may still fill:
    status in `WORKING` at any age, or "lost" with its `day` within `LOST_HOLDS_SEAT_DAYS` (4) of the wall clock's
    New York day. `_sync_orders` takes a lost order back for `LOST_TAKE_BACK_DAYS` (3: the constant both read), so
    the seat rule's window is the wider by a day. A lot is booked only by `_absorb` of a buy, and `_absorb` runs
    only on those orders: a program that reads flat has no order through which a lot could still be booked to it.
  - `_open_note(window, m, real_block, killed, out)` (A30 (2)), called by `_windows` at each minute in which it
    works a window's entries ("open": once the open's exits filled or `exit_wait_s` passed, while now <
    `entry_until`; "close": once the close's exits filled or `CLOSE_EXIT_WAIT_S` passed, while now <
    `close_until`), entries or none, only while the rule is not "first-come": it asks
    `_open_block(real_block, OPEN_PROBE, killed)` (an
    instance that is live by construction: the answer is the House's alone) and keeps kv `eq_open_note`
    (`OPEN_NOTE_KEY`): {day: {window: {"clear": true} | {"clear": false, "why"}}}; clear is kept once seen; a
    day all of whose windows are clear is dropped the day after, a refused one is kept `OPEN_NOTE_KEEP_DAYS`.
    `_refused_days() -> {day: why}`: the sessions with a window looked at and never clear. `_counted(first, last,
    refused) -> (counted, left out)` is `schedule.sessions_between` less those in (first, last].
  - `eq_band_since[key]` = {band, day} and, for a seat taken at or after the next session's `open_send` (the
    seating pass during a session, a decision caught up after a restart), `seat`: that session, from which the
    idle test counts (`day` stays the decision day; a mark without `seat` counts from `day`).
  - The plan's `left_out[].why` is `_reason_head`: the window and the House's words up to their first colon or
    bracket; the whole words stay in `eq_open_note`.
  - `_yield(...)`: refuses inside another transaction; one state transaction that finds the instance flat again,
    retires it with why "yielded: ...", writes the flag, the plan's memory and the mark, and LAST calls
    `confirm_band(row, "candidate", why)`; False rolls the transaction back (`_NoYield`). A commit that fails after
    the swarm took the band calls `_unyield` (`confirm_band({**row, band: "candidate"}, <the seat's band>, ...)`;
    an error alert when that fails). `row`, `since`, `flags` and `memory` change only after the commit.
  - `_house_exits`: a lot of an instance whose `why` starts with "yielded" (which `_flat` makes impossible) exits
    by the rule for a retired program, with an `equity.alert` record and an ERROR alert.
  `_open_block`, `_record_intents`, `_size` and the order path's own decisions are not edited (`_sync_orders`
  reads its three days from `LOST_TAKE_BACK_DAYS`).
- **10** (CHANGES; ops, league/ops/dlane_report.py): `read_book` adds `seat_plan`; `equity_seats(root, book, seeded)`
  is the report's `equity.seats` ({rule, seats, as_of, holders, seeded_seats, seeded_statement, waiting,
  idle_flagged, left_out, last_change, order, why, preregistered}); `A24_SEAT_RULE`, `A24_SEAT_COSTS`,
  `A30_SEAT_AMENDMENT` (`SEAT_RULE["amended"]`), `SEAT_RULE`; `PREREGISTERED["seat_rule"]` says A24 replaced A14's
  forward seat sentence (which stays as registered) and that A30 amended A24 before it went live.
- **Costs and limits** (A24's, A30's, and the build's): closes concentrate in frequent traders; a daily slice of a
  quarter sleeve buys rank and immunity from the idle rule (A30: stated and accepted, not changed; no guard in the
  pipeline refuses it); a slow, non-idle incumbent keeps its seat; a sale is not an ask, so a program that held
  one lot longer than the idle clock is idle at the first decision after it is flat. A buy the House itself
  refuses is still not an ask, but the session it was refused in is left out of the clock (A30 (2)). NOT COVERED,
  stated: a session the House did not look at in either entry window (it was not running) has no note and counts;
  so does every session under "first-come". Outranking is NOT adopted. The seat rule's own trouble (a row or a
  day it cannot read) is an `equity.error` "seats", moves no further seat and never stops the day's decision.
- **Rollback**: `probe.seat.rule` "first-come", one owner deploy, one money-digest move.
- **Tests**: league/tests/test_equity_seats.py; league/tests/test_equity_seats_a30.py (A30 and the independent
  check's findings, each on the real book); league/tests/test_equity_seats_seal.py (K reaches no generator);
  league/tests/equity_seat_sequence.py and fixtures/equity_seat_first_come.json (the week recorded on release
  E5-S); the changed pins in test_constitution, test_equity_money, test_live_long_single, test_equity_design,
  test_equity_families and test_equity_book.

## 19. The panel sleeve and the panel seats (release E4 step two, Oct 14, 2026; money, swarm and book; CHANGES 7.1, 8.3, 8.4, 10, as built)

A panel program (structure "panel": release E4's basket of index members) never takes, holds or yields one of the
`probe` seats above, and never sizes from the Probe sleeve. Until the pre-registered study EQDONE-5 rules, one seat
at 0.10 x E.

- **7.1** (CHANGES; money): `equity_money.panel` = {`seats`: 1, `sleeve_share`: "0.10"}, added below the table's
  literal (as the seat rule's block: `set_design` rewrites the `probe` row by its exact line).
  `EQUITY_MONEY_BOUNDS`: `panel.seats` ("0", "2"), a whole count (`_EQUITY_COUNTS`), and `panel.sleeve_share` ("0",
  "0.25"); `equity_money_problems` refuses a `panel.sleeve_share` above `probe.sleeve_share`. The money digest and
  `PINNED_DIGEST` moved once with it, and every pair of section 17's grid with them (league/tests/equity_design.py
  `DIGESTS`; `DIGESTS_E5A` keeps the pins before the row, `without_panel`). `EquityTable` (league/live/money.py,
  inside the options execution fingerprint) is NOT edited and carries nothing of the row.
- **The reader** (league/equity/bands.py): `panel_settings(constitution=None) -> PanelSettings(seats,
  sleeve_share)`; a row that is absent, outside its bounds or above the Probe sleeve is `PANEL_FALLBACK` (0 seats,
  no sleeve: fail closed).
- **8.3, 8.4** (CHANGES; book, league/equity/live.py): `_sleeve_share(inst)` is `panel_settings().sleeve_share` for
  an instance of another kind than the book's own, in every band. THE TWO POOLS: `_pools(rows)` splits a band
  sync's rows by kind (`POOL_ETF`: the book's own kind; `POOL_PANEL`: any other), and `_seat_bands` and the
  "first-come" branch run once a pool, over that pool's rows, its seats (`_pool_seats`: `_seat_count` for the ETF
  pool, `_panel_seat_count` for the panel's, the lower of the row and `families.panel_seats()`) and its plan
  (`_pool_plan`, `_put_plan`: the ETF pool's is `eq_seat` itself, to the key; the panel pool's is its key
  `SEAT_PANEL` "panel", written only once a panel row was ever seen). `_held_seats(pool, rows)`: the panel pool's
  alive instances with no row in the read keep their seats (the plan's `held_seats`). A seat record of the panel
  pool carries `pool` "panel"; an ETF one is main's. The day's line of the panel pool is `out["panel_seats"]`.
- **The swarm** (league/swarm/bands.py): `equity_seating(fams, seats, *, seatable, panel_seats=0)` seats a pool at
  a time; `panel_pool_seats(root)` is the lower of the row and `elane_xs.panel_seats(root)` (`elane.panel.seats`,
  0 to 2, default 2: it may only lower the row); `roster` adds `panel_seats`. league/equity/families.py:
  `EquityFamilies.panel_seats()`, `MemoryEquityFamilies(panel_seats=None)`. RELEASE U (the captain's A34): a panel
  Candidate holds a seat of the pool ONLY when the swarm seated it on a FWD1-R forward pass
  (league/swarm/elane_xs.py `forward_seats`, `forward_seated`); `equity_seating` leaves any other seatless, so the book
  never sees a row of one.
- **10** (CHANGES; ops, league/ops/dlane_report.py): `equity_panel_note(constitution=None)` (`EQUITY_PANEL_SENTENCE`,
  `EQUITY_PANEL_BARE`, `EQUITY_PANEL_NOTE`); `equity_seats` adds `panel` {statement, rule, seats, as_of, holders,
  waiting, held_seats} when the book's plan holds the panel pool's.
- **Costs**: one more program on real money at once; a basket's lots closed at one open are one market move, so
  Done counts a panel program's lots closed on one date as one close (league/ops/dlane_report.py `done_counts`, the
  lots beside); the window is one and first come.
- **Rollback**: `panel.seats` 0, one owner deploy, one money-digest move (nobody is unseated; no lot is sold).
- **Tests**: league/tests/test_equity_panel_seats.py (the row, a basket sized from it, the ETF programs' orders and
  seats order for order beside a panel Candidate, Probe and Sized program, the pool, the held seat, the swarm's
  reader, the report); the changed pins in test_equity_money, test_equity_design and test_constitution;
  test_equity_book_panel reads its own table's Probe sleeve as the panel row (its module docstring).

## 20. The event kind (release R2, Oct 2026; the owner's goal as re-set at 05:15Z Oct 19, 2026, PREREG-EVL-3 section 2 with PREREG-EVL-1 section 8 and PREREG-EVL-2; money, book, hooks and ops; CHANGES 5.1, 5.2, 5.3, 6.3, 7.1, 7.2, 10, as built)

Version 2 of each pre-registered event program (a seatable row of league/events/programs.py; never a swarm family,
never program code; version 1 never trades) trades real money through this book from its first event, at the band the
event lane's store gives it. Its rules live in the adapter league/events/book.py; the book meets them with E1's order
path.

- **7.1** (CHANGES; money): `equity_money.position_share.stock` "0.20" -> "0.10" (the goal's 10% a name; the gateway's
  `STOCK_SINGLE_EQUITY_SHARE` "0.1" with it, `league.ci`), and `equity_money.event` = {`enabled` True, `position_share`
  {learning "0.02", probe "0.05", sized "0.10"}, `one_share_max` {learning "0.05"}, `max_open` {learning 8, probe 6,
  sized 8}, `per_name_share` "0.10", `limit_ratio` "1.25", `open_risk` {floor "0.10", z "1.65", sigma_sessions 60},
  `order_path` {the six auction offsets, `EVENT_ORDER_OFFSETS`}}, added below the table's literal. `EQUITY_MONEY_BOUNDS`
  gains the `event.*` rows (the pre-registered value at each loose end; the moments the rules fix exact),
  `EQUITY_MONEY_CHOICES` `event.enabled`, `EQUITY_MONEY_ABOVE_LOW` `event.per_name_share` and `event.limit_ratio`;
  `equity_money_problems` checks the block only when it is there (a table without it, R2's rollback, is valid and opens
  no event buy) and orders learning <= Probe <= Sized <= the name's wall, the one-share cap under the wall, each
  auction's sends after its decision. `equity_money.enabled` STAYS False: the old lanes are exits only. `EquityTable`
  (league/live/money.py, inside the options execution fingerprint) is NOT edited and reads nothing of the block; its
  reader is `book.settings(constitution=None) -> Settings` (`FALLBACK`, off with no share, when the block is absent or
  out of bounds). Promotion, Sized, demotion and retirement are the LANE's rules, not rows here.
- **7.2** (CHANGES; league/ci.py): `PENDING_GATEWAY` gains league/events/book.py and league/events/proof.py (money
  movers behind the owner's wall; the gateway's `MERGE_FORBIDDEN` names them in its next follow-up).
- **6.3** (CHANGES; hooks): league/equity/kinds.py `BOOKS["event"] = "league.events.book"`, and `kind_of` reads a
  family row's structure "event" as the event kind. NO `KINDS["event"]` row and no child: an event program has no
  code to load, so the decider is never asked for it (`_ensure_loaded` answers False for an event instance), and
  league/events/ is no runtime path of the decider child.
- **5.3** (CHANGES; book, league/equity/schedule.py): `EVENT_DEFAULTS`, `EventMoments(day, open_at, close_at,
  open_decide, open_send, open_until, close_decide, close_send, close_until)`, `event_moments(day, offsets=None) ->
  EventMoments | None` (None on a day with no session): 09:15 / 09:16-09:27 ET and close - 14 / - 13 to - 11 minutes.
- **5.1** (CHANGES; book, tables): `eq_orders` gains `tif` ("day"; "opg" | "cls" for an auction order) and `otype`
  ("limit"; "market" for an event sale), migrated in place; `book.SCHEMA` adds `eq_event_programs` (one row a version 2
  program: its band as last read from the lane, since, why), `eq_event_intents` (one row an event intent, keyed by
  `eq_intents.iid`: program, version, event, side, band, tif, otype, symbol, cik, day, at, rank_key, adv20, prev_close,
  limit_px, sigma, hold, weight, exit_day, exit_at, lid, rung, decided_at) and `eq_event_decisions` (one row a session
  and auction: counts only; `sale_to_later` {skipped program: {selling program: n}} when the sale gate skipped an
  earlier row's pick because a later row's lot sells the name at that auction: PREREG-EVL-4 section 1.3's count,
  `_event_sale_takers`, also in the decision's `equity.event_decide` record; `band_sync` `first` | `moved`
  when the decision ran the band sync, release 1019f: section 23). kv `eq_event_synced`, `eq_event_band_mark`, `eq_event_list` {day, sha, count, at}, `eq_event_off_said`,
  `paper_proof_auction`, `paper_proof_auction_buy`, `paper_proof_auction_sell`. A lot's `info.evl` (program, version,
  event, cik, band, weight, sigma, prev_close, limit), `info.evl_exit` {day, at, rung, first, zero} and `info.evl_fills`
  (what was written back).
- **5.2** (CHANGES; book, league/equity/live.py): `Order.tif`, `Order.otype`, `Order.auction`; `order_body` carries
  `type` and `time_in_force` and drops `limit_price` for a market order; `_send(..., tif="day", otype="limit")`.
  `Instance.live` for the event kind is `EVENT_LIVE_BANDS` (learning, probe, sized). The tick's step "events"
  (`_event_step`: the auction proof, `_event_finish`, `_event_decide` at each decision, `_event_send` in each window,
  `_event_fills` every minute). EVERY DISPATCH THAT READ "every kind but the book's own is the panel" now names the
  panel (`PANEL_KIND`), and the old lanes' windows leave an event intent out (`_not_event`); an event lot never wakes,
  waits or joins the 16:30 decide, is never a swarm family's (no forward record export) and is never sold by the
  House's rules for the old lanes (`_house_exits` skips it); it may sell in the session it was bought (the minimum hold
  is the old lanes'). `_open_block` asks an event instance the kind's switch and the auction proof
  (`_event_open_block`) and its band (`_event_seat_block`) in place of `equity_money.enabled` and the SPY day-order
  proof. `_event_sync` reads the bands from the lane (`book.bands`) once a session (and again at the close decision when
  the lane's band mark moved: section 23); `_event_send` orders the buys by
  ROOM (`book.room_key`). `_size_event` calls `size_entry` with `usd` = the band's `position_share` x E (E the
  `last_equity` of the account, never above the sizing equity), `position_share` = `per_name_share` (the name's
  book-wide value as `account_symbol_value`), `weight` = the lot's own; whole shares; one share by `size_entry` at
  `usd` = the limit, at learning only when the limit is at most `one_share_max.learning` x E. `probe_figures` weighs an
  open event lot by `event_lot_weight` (its `info.evl.weight`; 0.40 from the ladder's first rung or when unreadable; 1
  once at 0) and a working event buy by its side row's weight, and counts every closed event lot in `closes` whatever
  its band. `_event_fills` writes each event lot's buy (once its buy ended) and sale (once closed; again when its fees
  move) into the lane's `real_fills` through `book.write_fills`.
- **The adapter** (league/events/book.py; standard library only; plumbing, in no identity): `settings`, `seatable()`,
  `program_of(program, version)`, `order_of`, `room_key(program, band)`, `Lane` (read-only), `open_lane(root)`,
  `decided(lane, day, at)`, `eligible(lane, day)` and `universe_rows(lane, day)` (the live rule's eligible rows only,
  `LIVE_ROWS`: release 1019b's second review), `lane_bands(lane)`, `bands(lane, s=None) -> [Band] | None`,
  `picks(lane, program, day, *, decided_at, reaction=None, held=None)` (PREREG-EVL-4 section 1.3: for
  `NEXT_OPEN_GUARD`'s programs an issuer's one event is not bought when `next_open_event(lane, row, session,
  decided_at)` says it is EVL-8K-READ-O1's at the next open), `rows_for` (PREREG-EVL-4's rows by `rows_4(lane, day,
  decided_at)`: the rows stored before the decision, EXCLUDED and the F8K(D) skip read from them), `held_recently`,
  `allocate(picks, rooms,
  band_of, skip) -> ({program: picks given}, {program: {why passed over: n}})` (the auction's slots in ROOM's order,
  each program its own ranked picks whose name no earlier program was given, until its room is full; the book's skip
  is `EquityBook._event_gate`: no whole share by price, or the name sold at the same auction), `one_name_an_auction(picks,
  band_of)` (`allocate` with no room limit), `reaction_reader`, `limit_price`, `sigma`, `weight`, `exit_plan(program,
  day) -> (day, "open" | "close")`,
  `publish(client, day, symbols)`, `FillWriter(path)`, `write_fills(root, rows) -> int | None` (the rows new or
  changed); constants `LANE` "event", `TAG`, `EXIT_TAG` "evl_exit", `LATE_TAG` "evl_late", `REAL_VERSION` 2 (PREREG-EVL-1's
  and -2's seating version; no gate since PREREG-EVL-4, whose ids seat at version 1), `NEXT_OPEN_GUARD`, `BANDS`,
  `LIVE_BANDS`, `DEFAULT_BAND` "learning", `PRIORITY`, `LADDER_CLOSES` 5, `ZERO_AFTER` 20, `ISSUER_GAP_SESSIONS` 5,
  `STRICT_WEIGHT` 0.40, `FILLS_TABLE`, `FILL_COLUMNS`. THE LANE'S OWN MODULES IT USES (release 1019b; no stand-in in
  the book or its tests): league/events/programs.py `SEATING`, `BY_KEY` and `Program.can_seat` (`seatable()` is
  `SEATING`, every version that can seat: version 2 of the nine, version 1 of PREREG-EVL-4's three, in the tables'
  order; `program_of` reads `BY_KEY` and `can_seat`); league/events/bands.py `bands(store)` (the band reader:
  {(program, version): band} for every seating version, no row = learning; the book reads each row's `since` and `why`
  beside) and `record_fill(store, ...)` (the fill write-back, one row a (program, version, event, side), a write again
  changing only its fee), on a `FillWriter` (the existing store file only, a 5 s busy timeout); the store's tables
  `bands(program, version, band, since, why)` and `real_fills(program, version, event, side, qty, price, fee,
  filled_at, band)` as league/events/store.py's schema makes them. league/tests/test_events_book.py `TheRealLane` runs
  the lane's own decision (edgar, run, programs) into a real store and the book on it.
- **The auction paper proof** (league/events/proof.py): `AuctionProof(state, account, market, *, clock, record,
  alert)`: `step(now, moments)`, `buy_passed()`, `sell_failed()`, `passed()`, `status()`; built by the book on the
  stock proof's practice account (`_auction_proof`).
- **10** (CHANGES; ops): league/ops/twins.py `event_twin(lot, marks, *, settled, at)` and `read_event_marks(root,
  lots)`: an event lot's record in kv `equity_twins` (`kind` "event"; `entry_gap_bp`, `exit_gap_bp` against the event
  lane's own auction prints, positive when the real fill was worse; `gap_bp` in E1's sense); `equity_round` judges an
  event lot so. The swarm's readers leave event programs out: league/ops/forward_register.py `live_instances`,
  league/ops/forward_twins.py `read_book`, league/ops/forward_report.py FW7 and FW9, league/ops/dlane_report.py
  `equity_closes`.
- **Identities**: money `f4fc39ff` -> `285fa7af`, constitution `34bbe7a5` -> `fd38e4e1`; the options execution
  fingerprint, the equity identity, the xs identity and the gate contract do not move.
- **Rollback**: `event.enabled` False (one owner deploy, one money-digest move: `25f5eb21` / `8a6a2160`); no lot is sold
  by it.
- **Tests**: league/tests/test_events_book.py (the rows, the bands from the lane, the picks, ROOM, the day through the
  real book and the real `size_entry`: order bodies, learning / Probe sizes and the one-share rule with its caps, the
  10% wall, eight open at learning, the kill switch, the kind's switch, the proof and the gateway stopping buys never
  sales, exits at the close and at the next open, the ladder and the 0 after 20 sessions, the old lanes and version 1
  never buying beside an event buy, the eligible list, the budget's weights, the fills written back, the twins, the
  readers left out, the auction proof's stages); the changed pins in test_constitution, test_ci, test_e3_identities,
  test_e4_e2e, test_equity_money, test_equity_opens_off, test_equity_design, test_equity_seats and
  test_equity_book_panel; league/tests/equity_week.py's golden ETF week normalizes R2's new columns and tables (no ETF
  order moves).

## 21. The event kind's own day order count (release 1019c, Oct 2026; under the owner's goal of Oct 19, 2026; money and book, as built)

- **The row** (money; league/constitution.py): `equity_money.event.max_orders_day` 150, a whole count in [0, 300] (the
  gateway's day line's own loose end); `equity_money_problems` also holds it under `options_money.gateway.
  max_day_orders` in force (300) and, with `order_path.max_orders_day` (60, the old lanes'), under the House-wide line,
  `options_money.order_path.max_orders_day` (250). 150 = 2 x the sum of `max_open` over the live bands (44), at least
  150 (nine programs at learning hold at most 72 lots: a buy and a sale each in one day, 144 orders). With PREREG-EVL-4's
  three (release 1019d) twelve programs at learning could need 2 x 12 x 8 = 192; THE LINE STAYS 150 (A78, the reading
  that trades less; the House-wide line leaves it at most 190): on a day that needs more, ENTRIES stop in ROOM's order
  (`_event_send` sends the buys in `room_key` order after the sales), so PREREG-EVL-4's rows, the last in the tables'
  order within a band, are refused first; an exit is never stopped by it.
- **The reader**: league/events/book.py `Settings.max_orders_day` (`FALLBACK` 0). league/live/money.py `EquityTable`
  (inside the options execution fingerprint) does not read it.
- **The count** (book; league/equity/live.py): `event_orders_today(rows, day)` counts the orders of an event instance
  (`eq_instances.lane` "event") as `orders_today` counts every lane's; `orders_today` stays every lane's together (the
  House-wide count's equity part, league/live/real.py `house_count`). `_count_refusal(day, exit_=False,
  event_line=s.max_orders_day)` for an event entry: the event kind's orders plus one plus its own exit plus
  `_exit_reserve(day, event=True)` (one order for each event lot not yet sold that day, and one for each event buy
  still working, `eq_orders` joined to `eq_event_intents`, whose planned exit is that day: an auction buy is no lot
  until its cross) within the line; an old lane's entry (`event_line` None): the old lanes' orders plus one plus
  `_exit_reserve(day, event=False)` (two for each of their lots) within `order_path.max_orders_day`; an exit meets no
  lane's line; every order meets the House-wide count, and EVERY ENTRY meets it with room left for the options book's
  `exit_reserve()` AND `_exit_reserve(day)` (both lanes) and, for an event entry, its own exit (the money review of
  release 1019c: a lane's line bounds that lane's day only; without the exits' room at the House-wide line the open
  window's buys, about 2 x 150 event orders with their sales, could reach it and the close's sales be refused there).
- **Identities**: money `285fa7af` -> `055e5313`, constitution `fd38e4e1` -> `a8d4cbd9`; the options execution
  fingerprint, the equity identity, the xs identity and the gate contract do not move.
- **Rollback**: `event.enabled` False (money `1b7a5c22`, constitution `50e951c9`), or release 1019b's House.
- **Tests**: league/tests/test_events_1019c.py `TheEventKindsOwnDayCount` (40 open-entry learning lots and a Probe
  close entry on one day all send; each lane meets its own line and the House-wide one; the open window's buys keep
  their close sales' room: 75 buys and all 75 sales, the line's 150 (before the money review: 150 buys, then 50 of
  their sales refused at the House-wide line); with 120 options orders, 65 buys and all 65 sales, the House-wide line
  exactly full (before: 130 buys and all 130 sales refused); the row, its bounds and its digests);
  league/tests/equity_design.py `DIGESTS` regenerated, release 1019b's kept as `DIGESTS_R2`.

## 23. The close decision reads the bands again when the lane's band history moved (release 1019f, Oct 2026; after section 22, release 1019e's A80; book, as built)

- **Why**: the audit of the live House ("bands move a session late"): the lane's screen now runs its looks after the
  open decision too (league/events/house.py `_screen_open`, docs/events.md **The screen after the open**), so a look the
  open made final moves its program's band that morning; the book read the bands once a session, at its first decision,
  so a close-entry program traded learning at that day's close although PREREG-EVL-3 section 2 gives Probe "from the
  first decision after a passed look". No rule moves.
- **The adapter** (league/events/book.py; plumbing, in no identity): `band_mark(lane) -> int | None`, the newest
  `band_history` id (every `bands.set_band` writes a row: a look's Probe or retirement, the night's review); 0 with no
  lane, no such table or no row; None when the table is there and cannot be read.
- **The book** (league/equity/live.py; plumbing, outside the equity identity): `EVENT_BAND_MARK` = kv
  `eq_event_band_mark`, written by `_event_sync` beside `eq_event_synced` with the mark it read BEFORE the bands (a move
  written between the two reads is read at the next decision); `_event_bands_due(day, at, adapter, lane) -> "first" |
  "moved" | None`: "first" when `eq_event_synced` is another day (the session's first decision, as before), "moved" at
  THE CLOSE DECISION when the lane's mark differs from the kept one or cannot be read (fail closed: `_event_sync` then
  says whether the bands can be read; unreadable, no buy is planned that decision), else None. `_event_decide` runs the
  sync when it is due and writes `band_sync` in the decision's summary. The open decision is always a session's first;
  a band moved after the close decision is read at the next session's first. A re-sync is the same `_event_sync`: the
  rows of `eq_event_programs`, the instances' bands, the `equity.band` records and the band alerts, so `_event_seat_block`
  and ROOM (`book.room_key`) at that close read the new band, and its buys are sized at it (`s.share(inst.band)`).
- **Identities**: none moves (money `055e5313`, constitution `a8d4cbd9`, the options execution fingerprint `b60410ad`,
  the equity identity `78022ca6`, the gate contract `397b22b7`).
- **Tests**: league/tests/test_events_1019f.py `TheCloseDecisionReadsTheBandsAgain` (the lane's screen at 10:00 ET of
  DAY writes EVL-ERN-REACT-ON v2's look 1 as of Oct 30 and its Probe move; the 15:46 ET close decision gives ACME to it
  at Probe's 5 shares, `band_sync` "moved", where without the move the earlier row EVL-ERN-REACT-C1 takes it at
  learning's 2 and the bands are read once; an unreadable mark reads them again; the next session's open is its first)
  and `TheBandMark`.
