# E3 build interfaces: release E3 "record and measure", the contract between its five packages

Branch `feat/equity-e3` (worktree `~/Work/ltcm-v3/eqe3`), cut from `feat/equity-e2-int` at 5a6906ff: release E1 (the
share lane) and release E2 (the swarm breeds share programs) merged, E2's patches applied. This file is step 0's: every
package builds against it and changes it only through the integrator. The stubs it names exist on the branch now
(bodies raise `NotImplementedError("<package>: <file> <name>")`; their docstrings say what each must do), so every
package imports every other package's names from day one. `league/tests/test_e3_skeleton.py` holds the imports, the
signatures and the columns through the build.

**Authority, in order.** The captain's amendments (A1-A16), the E3 spec (E3-SPEC.md revision 2, private scratch), the
roadmap, the designs. Where the spec and the code at the base disagree, THE CODE WINS: section 4 lists each case and
what the stubs do about it. Two facts were found after the spec was written and bind it: section 3.

**What E3 is.** It records clean evidence and measures it. It moves no money, gates nothing, shows no generator
anything new and writes no verdict. It moves no execution fingerprint, no equity identity (A13: nothing of E3 enters
the evidence import closure) and no money digest.

**Hard rules for every package.** The repository is public: commit no market data, no price or return of a real year,
no census or Phase A figure, no per-program outcome. Tests use `league.equity.synth` stores and fixtures marked fake.
No push, PR or deploy; no contact with the House, Sail, Alpaca, the gateway or a broker; no secret or env file read.
Edit NOTHING under `league/equity/`, `league/live/`, `league/gym/`, `gateway/`, in `league/constitution.py` or in the
four `LEAGUE_FILES`. Edit an existing file only where section 1 names you its owner. Standard library and numpy only.
Every new test passes on Python 3.11 AND 3.14 (CI runs both), one process at a time:

    mkdir -p /dev/shm/eqe3-<key> && TMPDIR=/dev/shm/eqe3-<key> \
      ~/Work/long-term-capital-management/.venv/bin/python -m unittest <modules>      # 3.14
    TMPDIR=/dev/shm/eqe3-<key> ~/Work/ltcm-v3/.venv311/bin/python -m unittest <modules>  # 3.11, with numpy

Match the surrounding code: its idioms, naming, docstring density and fail-closed style. Never skip or weaken a test.

---

## 1. Ownership map

One owner a file. NEW files in **bold** (each exists as a stub; the tests are the owner's to create). "Patches" are
the existing files a package edits, alone, at integration, exactly as the spec's section 11 writes them (11.1-11.10;
every anchor was checked against the base: section 5).

| key | owns (new) | patches (existing files, at integration) | tests it creates |
|---|---|---|---|
| A registry and wiring | **`league/ops/forward_db.py`**, **`forward_register.py`**, **`forward_controls.py`**, **`docs/benchmarks/release_receipts.json`** | `league/ops/registry.py` (11.1), `league/swarm/policy.json` (11.2), `league/ci.py` (11.3), `league/tests/test_ci.py` (11.3), `league/tests/test_ops_int_ops.py` (11.1), `docs/operations.md` (11.10), `CHANGELOG.md` (11.10) | **`test_forward_db.py`**, **`test_forward_register.py`**, **`test_forward_controls.py`**, **`test_e3_identities.py`** (T10), **`test_e3_seal_imports.py`** (T1) |
| B shadow | **`league/ops/forward_shadow.py`**, **`forward_audit.py`** | none | **`test_forward_shadow.py`** (T6), **`test_forward_audit.py`** |
| C meters, report, receipts | **`league/ops/forward_stats.py`**, **`forward_report.py`**, **`release_receipts.py`** | `league/ops/funnel.py` (11.4), `league/ops/dlane_report.py` (11.5), `league/ops/stall.py` (11.6), `league/tests/test_dlane_report_equity.py` (11.5(e): one assertion added) | **`test_forward_stats.py`**, **`test_forward_report.py`** (T8), **`test_release_receipts.py`**, **`test_dlane_report_a14.py`** |
| D fills and twins | **`league/ops/fill_minutes.py`**, **`forward_twins.py`** | none | **`test_fill_minutes.py`**, **`test_forward_twins.py`**, **`test_forward_a14.py`** |
| E memory tables and probe | **`league/swarm/elane_folds.py`**, **`elane_effects.py`**, **`elane_memory.py`**, **`league/ops/contam_probe.py`** | `league/swarm/elane_train.py` (11.7), `league/swarm/elane_births.py` (11.8), `league/swarm/elane_seal.py` (11.9) | **`test_elane_folds.py`** (T4), **`test_elane_effects.py`**, **`test_elane_memory.py`** (T9), **`test_elane_memory_seal.py`** (T2, T3, T5), **`test_contam_probe.py`** (T7) |
| step 0 and integration (the integrator) | `league/ops/E3_INTERFACES.md` (this file), `league/tests/test_e3_skeleton.py`; after the five: **`league/tests/test_e3_end_to_end.py`** (T11: the real modules together, no fake) | none | |

All tests live in `league/tests/`. No package edits `league/ops/equity_data.py`, `twins.py`, `league/swarm/elane.py`,
`elane_yield.py`, `hook.py`, `settings.py`, `evaluator.py`, `loop.py`, `store.py`, `league/ledger.py`, or anything in
the hard rules. A cross-package call uses the stubs' names only; a test that needs another package's behaviour uses a
fake and says so in its docstring (T11 is the one test with none).

**Import rules (the seal by construction; T1, `test_e3_seal_imports.TheForwardRecordIsOpsOnly`).**
- `league/swarm/**`, `league/equity/**`, `league/live/**` and `league/gym/**` import no E3 ops module (`forward_db`,
  `forward_register`, `forward_controls`, `forward_shadow`, `forward_audit`, `forward_stats`, `forward_report`,
  `forward_twins`, `fill_minutes`, `contam_probe`, `release_receipts`) and never name `forward.sqlite`,
  `forward-report.json`, `equity-fill-minutes`, `contamination.json` or a `fwd_` table. The two sealed memory tables
  are named only in `elane_memory.py`, `elane_seal.py` and `league/ops/`. The three swarm stubs already keep to this.
- E3's ops modules may import `league.equity` (config, store, program, ctx, engine, results, runner, screen,
  schedule: read only), `league.live.decider` (the `Decider` class), `league.swarm` (`store`, `settings`,
  `evaluator`, `gate.run_sha`, `elane`, `elane_train`, `elane_seal`, `elane_yield`, `elane_memory.counts`,
  `models.build_router`) and `league.ops` (`guard`, `context`, `schedule`, `twins`, `funnel`, `equity_data`).
- `elane_folds`, `elane_effects`, `elane_memory` import `league.equity` (config, results, screen, store) and, INSIDE
  FUNCTIONS only, `league.swarm.elane_train` and `elane_seal` (`elane_train` and `elane_births` import the three at the
  top; nothing else does).
- The swarm process never opens the forward store. The ops jobs open the swarm store read-only (`SwarmStore(root,
  readonly=True)` or `guard.read`), except `contam_probe`, which books its dollars.

## 2. What exists now

| complete from step 0 (data, not behaviour) | where |
|---|---|
| the forward store's DDL, with its append-only triggers | `forward_db.SCHEMA` (`TABLES`, `APPEND_ONLY`, `WRITERS`: who writes which table) |
| the memory tables' DDL and triggers; the receipts' | `elane_memory.SCHEMA` (`TABLES`, `SEALED_TABLES`); `release_receipts.SCHEMA` |
| the pre-registered constants (the spec's section 4) and the forward screen's pinned shape | `forward_db`: `CHECKPOINTS` ... `E3_ALPHA_F`, `FGS`, `FGS_SHA`, `GENESIS`, `HASHED` |
| the settings' defaults and bounds (section 5) | `forward_db.DEFAULTS`, `BOUNDS`; `contam_probe.DEFAULTS`, `BOUNDS`; `elane_folds.MODES`, `FALLBACK` |
| the vocabularies | `forward_db.MODES`, `REASONS`, `TAGS`, `EVENT_KINDS` (kind -> package), `ONCE_KINDS`, `KV_KEYS`, `CAUSES`; `forward_report.ALARMS`, `SECTION_KEYS`, `FUNNEL_KEYS`; `forward_twins.A14_KEYS` and its three key lists |
| the shared dataclasses | `forward_db.Program`, `forward_db.ShadowRun` (frozen) |
| the bars hash of a decision (section 3) | `forward_db.bars_hash(inputs)`: implemented and tested; no package changes it |

Everything else is a stub. B, C and D test on an in-memory database made from `forward_db.SCHEMA`
(`sqlite3.connect(":memory:")`, `row_factory = sqlite3.Row`, `executescript(SCHEMA)`), writing the rows a test needs
with SQL and faking the `forward_db` functions A has not landed yet, to the semantics the stubs' docstrings state. A
lands `forward_db.py` first: every other package calls it.

A package may add private helpers and constants of its own freely. A name another package calls (every function in a
stub's `__all__`) keeps its signature; `test_e3_skeleton.SIGNATURES` and `COLUMNS` are the pins.

## 3. Two facts found after the spec was written (binding)

**Fact 1: a shadow decision does not always read the bars the live one read.** The vendor rounds adjustment=all
prices to cents, so as-of prices and ctx are not byte-identical between a live decision and a later store, and on a
rare decision day an intent can flip for that cause alone. So the forward shadow and the twins RECORD THE BARS HASH
each shadow decision used, and an intent disagreement is DATA (counted, with its cause when the bars differ), never
an error. What step 0 fixed for it:
- `forward_db.bars_hash(inputs) -> str`: 16 hex characters of the sha256 of `ctx.ctx_bytes` over ONLY the `symbols`,
  `bars` and `prices` that `ctx.build(inputs)` gives (the as-of history a program reads at that close). The book
  (positions, cash, caps, params) and the calendar fields do not enter it. `inputs` is a `league.equity.ctx.Inputs`
  from `ctx.inputs_from_bars`, `elane_train.state_inputs` or `ctx.inputs_from_fetch`.
- `fwd_days.bars` (B): the bars hash of the decision a day's orders came from (the Gym's inputs at the close of the
  session before it). NULL on a control's row (a control reads no bar). A `restated` event's payload says whether a
  bars hash on or before that day moved (`"bars": "moved" | "same"`). About 17 bytes a row on top of the spec's
  measured 85.
- `fwd_twins.shadow_bars`, `live_bars`, `cause` (D): the twin decision's hash, the live decision's (NULL when not
  known), and on a row with `agree` 0 one of `forward_db.CAUSES`: "bars" (both known, they differ), "program" (they
  are equal), "unknown" (the live one is not known). `forward_twins.shadow_bars`, `live_bars` and `cause` are D's
  stubs for it. The live decision's bars are in the book's `eq_bars` only until the next session's decide fetches the
  adjusted series again, so D takes that hash the night of the decision and keeps it in a `live_bars` event (once an
  (instance, day); the kind is in `forward_db.EVENT_KINDS`).
- A14's pre-registered rule is NOT changed: a session whose intents differ counts as not agreed whatever its cause.
  `a14_reading`'s `intents` object gains `disagreed` and `causes` ({cause: sessions}) beside the share, and the
  report's `fills.intents` shows the same counts. Nothing raises, alarms as an error, or drops a row for a
  disagreement.

**Fact 2: Python 3.11 and 3.14.** The built-in `sum` is not exact on 3.11 (it is compensated from 3.12 on), so a
statistic summed with it gives other last digits on the two CI jobs. EVERY statistic sums and averages with
`math.fsum`. Where a numpy reduction is used, a test compares within a stated tolerance, never to the last digit.

## 4. Where the spec and the code at the base differ (the code wins)

Every existing name the spec calls was checked against 5a6906ff. Signatures match except as said here.

1. **`swarm.elane` is already a skipped mirror kind.** `hook.SKIPPED_KINDS` holds it at the base (E2's patch 11), so
   the spec's 8.3 note for E2's owner is done: E's "scored" event draws no House warning. Its payload values of
   `pass` in use are "births", "train", "refuted" and "stalled"; "scored" is free.
2. **A NEEDS history of 0 and the first decision (B, D).** E1's engine and `elane_train.state_inputs` decide from the
   slice's index `max(first - 1, 0)`. With the spec's `history=needs.history` a history-0 program has no session
   before `first_day` in its slice, so its first decision would fall at `first_day`'s close, a session later than D2
   says and than the live book decides, and a twin would have no decision at `d_first`. `Shadow.slice` therefore
   takes `history=max(needs.history, 1)`. The ctx is unchanged: `ctx.inputs_from_bars` reads NEEDS' history, not the
   slice's. B holds this with a test.
3. **The engine's result statuses (B).** A result is "ok", "disqualified", "no_data" or "error". `fwd_days.status`
   holds the first two only. "error" (`results.failed`) is the child's failure, read as `runner.Isolated` reads it
   (`RunFailed`); "no_data" (a NEEDS symbol with no bar in the run) is the data's (`data_failed`, no row).
4. **The store's "forward" window starts before the forward days (B, C).** `config.WINDOWS["forward"]` begins
   2026-09-26; D1's forward days begin at `t0()` (the session after `config.LOOK_CAP`). "Forward day" in E3 always
   means D1's: a run's `start` is `first_day(p) >= t0()`, and "the store's last five forward days" and the meters' days
   are counted from `t0()`, never from the window's first session.
5. **`schedule.moments(day)` is None for a day that is not a session**; `next_session` and `previous_session` raise
   `ValueError` past 15 days. Guard every `.close_at`, `.bars_at` and `.open_send` read.
6. **Times in the swarm store are ISO text to the second** (`events.at`, `SwarmStore.now()`); `eq_instances.created_at`
   and everything in the forward store are epoch REAL. D2's T is the scored event's `at` parsed
   (`league.ops.schedule.epoch`); `mem_seen.at` and `mem_contrib.at` are ISO text, so `funnel_rows` compares them as
   text against `schedule.iso(start)` and `iso(end)`.
7. **A release's name (C).** `ctx.release` is the release's DIRECTORY; `funnel.release_start(base, release)` takes its
   name. `release_receipts.step(root, base, release_dir, now=)` passes `Path(release_dir).name`, as the scoreboard
   does, and reads the declarations under `release_dir`.
8. **The probe's ledger rows (E).** `elane_yield.book(..., purpose="probe")` is accepted, and a purpose that
   function does not name is counted under the row's `usd_research` (there is no probe column). The row's key
   `probe:<route>` keeps the dollars apart from the birth routes'. `elane_yield.report` sets apart only `review:`
   rows, so a `probe:` row is listed among its `routes` with no births (operator only; `choose` reads its candidates
   alone, so the route choice and T2 are untouched). No package edits `elane_yield.py`; listed for a later release.
9. **T1 and the word `forward_stats` (A).** `league/live/money.py` has a function of that name (called by
   `league/live/step.py` and `league/swarm/progress.py`). T1's module rule is an import check by AST
   (`league.ops.<module>`), never a string scan for a module's bare name; the string scan is for the five store and
   file names only. The base is clean of all five and of both sealed table names.
10. **Python 3.11 with numpy** is `~/Work/ltcm-v3/.venv311/bin/python`; the bare 3.11 install has no numpy, which
    `league.equity` needs.
11. **No gateway change is needed.** `equity_data.regular_session_check` already pages `timeframe=1Min` on the bars
    route D reads (`equity_data.BARS`); whether the answer carries `vw` 45 minutes after the close is the spec's House
    fact 2 (else the hlc3 fallback runs and `fwd_fillgap.field` says so).
12. **A verdict's `bar_passed` (A).** The record's verdict (`elane_train.compact`) has no `bar_passed` key except on
    a version the review refused (`review_failed` sets it True with `passed` False), which is exactly what the spec's
    fallback `verdict.get("bar_passed") or verdict["passed"]` needs. A STATE failure keeps its figures (`pnl_10` not
    None) with `passed` False: it is judged on the bar and registers as "train_fail".
13. **Two run shas.** `fwd_registry.run_sha` and `eq_instances.run_sha` are both the swarm's `gate.run_sha(version)`
    (the code sha with the version's params), which is what D compares. E1's `EquityProgram.run_sha` (the code sha
    with the MERGED params) is another value: never compare the two.

Readings step 0 fixed where the spec was silent (each is in its stub's docstring): `forward_db.events(..., since=)`
takes an epoch and returns the rows with `at >= since`, each a dict with its `payload` parsed; `tags` lists each
tag's rows by `at`; `elane_memory.ingest(..., now=)` is the rows' ISO `at`; `forward_controls.cost_free` passes
`universe=list(bars.symbols)` (the benchmark does not enter r); `release_receipts.declarations` returns the kept
declarations and `step` names a dropped one in its `errors`; `contam_probe.ERAS` gives "2025" the Validation
window's two ends.

Names added by step 0 beyond the spec's section 7, all data or the bars hash's: in `forward_db` `LANES`,
`CONTROL_ROUTE`, `CONTROL_ALPHA_F`, `TAGS`, `EVENT_KINDS`, `ONCE_KINDS`, `KV_KEYS`, `CAUSES`, `BARS_HEX`, `TABLES`,
`APPEND_ONLY`, `WRITERS`, `APPEND_ONLY_ERROR`, `bars_hash`; in `forward_shadow` `NightFailed`; in `forward_report`
`STALE_HOURS`, `SECTION_KEYS`, `FUNNEL_KEYS`, `ALARMS`, `RC_PAIRS`; in `release_receipts` `DIRECTIONS`, `KINDS`,
`SCHEMA`, `APPEND_ONLY_ERROR`; in `fill_minutes` `VERSION`, `SOURCE`, `SETTLE_SECONDS`, `LIVELIKE_FIELDS`; in
`forward_twins` `UNREADABLE`, the four `A14_*` key lists, `TwinInterrupted`, `shadow_bars`, `live_bars`, `cause`; in
`contam_probe` `RECALL_MONTHS`, `READABLE_ANSWERED`, `READABLE_PERIODS`, `ALPHA`, `HISTORY`, `MODES`, `DEFAULTS`,
`BOUNDS`, `cfg`, `mode`; in `elane_effects` `STATUSES`; in `elane_memory` `TABLES`, `KIND_OWN`, `APPEND_ONLY_ERROR`.
`forward_shadow.CANARY` and `contam_probe.SYSTEM` hold working texts their owners may reword (the canary is a
template: `CANARY.format(symbol=...)`; it loads through `league.equity.program.load_program`).

## 5. The patch anchors, checked at the base

Each anchor of the spec's section 11 names a statement that exists at 5a6906ff, under that spelling:

| patch | anchor at the base |
|---|---|
| 11.1 A | `registry.JOBS` ends with the `dlane` Job; `test_ops_int_ops.test_the_registry_marks_what_runs_in_a_pause` pins the `in_pause` set (twelve names) and the `paid` set (three). The longest wall is 3,600 s; the grant's grace is 4,200 s |
| 11.2 A | `policy.json` `"elane"` ends with `"e2"`; `settings.DEFAULTS["elane"]` is `{"mode": "off"}`, so `policy_shape` checks no new key |
| 11.3 A | `ci.PENDING_GATEWAY` holds E2's five paths; `test_ci.py` pins the tuple and a guarded-path list. `league/ops/` and `docs/benchmarks/` are already FORBIDDEN |
| 11.4 C | `funnel.window` ends `return out`, with `out["errors"]` a dict |
| 11.5 C | `dlane_report.equity_yield` exists; `meter` has `at = reading(counted[:k], ...)`, `fin`, `whys`, `item7` and the checkpoint object (`at["items"]` holds "3" and "4"); `report` assigns `out["alarms"]` once, with `root`, `now` and `settings` in scope; `LOOSENED` is a tuple of {rule, was, now, cost}; `TIGHTENED` a tuple of strings; `test_dlane_report_equity.py` asserts "not computed yet" in `pre["status"]` |
| 11.6 C | `stall.run` has `write_json(root / STATE_FILE, ...)` before its return; `_get(ctx, name)` reads `base` and `release` |
| 11.7 E | `elane_train` imports `elane_review, elane_seal, elane_yield`; `EquityResearcher.score` uses `TRAIN_SPANS` exactly twice (the run loop and the `outside_years` check), has `rec = _update(self.store, fid, put)` on the non-rescore path and `house_failure(fam, n, why, kind=)`; `brief` has `lines.append(bar_text())` |
| 11.8 E | `EquityPass.birth` has `spec = {...}`, then `cited = ...`, then its `try:`; `row` is a mapping |
| 11.9 E | `elane_seal.SEALED_COLUMNS` and `__all__` |
| 11.10 A | `docs/operations.md` has the paragraph "Pre-registered before the first equity close"; `CHANGELOG.md` has "Not yet deployed" |

## 6. Who calls whom (the cross-package calls, by stub name)

- **Swarm.** `EquityPass.birth` -> E `elane_folds.birth_fields` (guarded; `FALLBACK` on a raise). `EquityResearcher.score`
  -> E `elane_folds.seen_spans(elane_folds.hidden_year(fam))` (guarded) -> E1 `Isolated.train` once a seen span and k
  -> E2's `combine`, `train_score`, `restart_check`, `add_run` (unchanged, on the seen runs) -> the record -> the event
  `swarm.elane` `{"pass": "scored"}` -> E `elane_memory.ingest` -> E1 `Isolated.train` over the hidden span at each k
  -> the memory tables.
- **Ops, nightly.** D `fill_minutes.run`; B `forward_shadow.run` -> `Shadow.preflight` -> A `forward_register.sync` ->
  A `forward_db.engine_id` -> D `forward_twins.begin` -> `Shadow.controls` (A `forward_controls`) -> `Shadow.finals`
  -> each due program (`Shadow.run_program`, `Shadow.write`, C `forward_stats.t_stat` and `p_one_sided`, D
  `forward_twins.on_run`) -> the retry -> D `forward_twins.finish` (twin runs through B's `Shadow.run_from`,
  `Shadow.official`); C `forward_report.run`; B `forward_audit.run`.
- **Ops, other.** Hourly: A `forward_register.run`. The dlane job: `meter` -> C's `a14_of` -> D
  `forward_twins.a14_reading`; `report` -> C `forward_report.read_section`, `.alarms`. The funnel: C
  `forward_report.funnel_rows` (E `elane_memory.counts`' tables). The stall job: C `release_receipts.step`. Saturday
  00:10Z: E `contam_probe.run`.

Each D call from B's night sits in its own try/except (a twins failure never loses a shadow day), and nothing C adds
to `meter`, `report`, `funnel.window` or `stall.run` may raise (the spec's 11.4-11.6 guards).
