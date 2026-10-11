# E3 build interfaces: release E3 "record and measure", the contract between its five packages

Branch `feat/equity-e3` (worktree `~/Work/ltcm-v3/eqe3`), cut from `feat/equity-e2-int` at 5a6906ff: release E1 (the
share lane) and release E2 (the swarm breeds share programs) merged, E2's patches applied. INTEGRATED since (section
10): the five packages, `feat/equity-e2-int` at 5ad1f01e and every patch of section 5; where a section below speaks of
the base as it stood at step 0, section 10 says what moved. MERGED WITH MAIN since (section 12: releases E1, E2 and
E2.2 at 87f9fd0c, the gateway's merge list, the verification's one fix). This file is step 0's: every
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
| A registry and wiring | **`league/ops/forward_db.py`**, **`forward_register.py`**, **`forward_controls.py`**, **`league/ops/release_receipts.json`** (the declared receipts: under league/, which the House box's release carries; docs/ is not uploaded) | `league/ops/registry.py` (11.1), `league/swarm/policy.json` (11.2), `league/ci.py` (11.3), `league/tests/test_ci.py` (11.3), `league/tests/test_ops_int_ops.py` (11.1), `docs/operations.md` (11.10), `CHANGELOG.md` (11.10) | **`test_forward_db.py`**, **`test_forward_register.py`**, **`test_forward_controls.py`**, **`test_e3_identities.py`** (T10), **`test_e3_seal_imports.py`** (T1) |
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
  top; nothing else does). `elane_memory` alone also imports, inside its one function `hidden_runner`,
  `league.equity.runner` and `league.live.decider`: the hidden run's own decider child (section 11, seals-1), started
  as `league/swarm/elane.py` `isolated_runner` starts the evidence child. T1 holds the two imports to that function.
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
  bars hash on or before that day moved (`"bars": "moved" | "same"`). PACKAGE B's FINDING: the same cents rounding
  moves nearly every stored day of every holder past `TOL` on each ex-day (the vendor rescales the whole adjusted
  history), so `restated` is ONE event a program and cause, not one a day: `day` is the first restated day, the
  payload counts `days`, `first`, `last`, `moved` and `same`, and `"bars"` is "same" when any restated day has no
  moved bars behind it (the notable case), else "moved" (the routine ex-day one); on a control's event, which has
  no decision to compare, it is "none" with `moved` and `same` 0. The hash is about 17 bytes a row on top of the
  spec's measured 85.
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
   takes `history=needs.history + 1` (package B's finding, on E1's own builders: `ctx.inputs_from_bars` reads the
   NEEDS history + 1 sessions ending at the decision WHEN THE SLICE HOLDS THEM, and a slice with `history` sessions
   holds one fewer at the first decision, index `first - 1`; the live book's `ctx.inputs_from_fetch` always reads
   history + 1. With one more session the first decision's ctx is byte for byte the live one's, so a program that
   waits for its full history does not decide a session late in the shadow only, and a twin's bars hash at
   `d_first` can equal the live decision's; every later decision is unchanged). B holds this with a test.
   AT THE INTEGRATION (section 10): E1's review took this into the store itself (`EquityStore.bars(history=h)` now
   hands h + 1 sessions before a run's first), so `Shadow.slice` asks for `history=needs.history` and adds nothing;
   the slice still carries NEEDS history + 1 sessions, and the same test holds it.
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
14. **Which bars the morning audit found different (B; measured on E1's own book).** AT STEP 0'S BASE E1's `_audit`
    wrote "mismatch" on EVERY `eq_bars` row of the decision's day when any one symbol differed (since E1's review
    each audited symbol's rows carry its own verdict, "ok" or "mismatch": section 10), and that evening's fetch sets
    a row whose values changed (the symbol that did differ) back to unaudited, then and now. The book's kv `eq_bars_audit` ({day:
    {"symbols", "at"}}, its last 30 failed audits) names the symbols that differed. `forward_audit` marks a day
    the note names for THOSE symbols and reads the rows only for a day the note does not name, so a program whose
    bars were right keeps its day and a morning that was missed is made up later. The shadow's night reads the book
    the same way before it reads any checkpoint (`Shadow.marks`; the receipt's `marks`), so the checkpoint of record
    never counts a day whose mark the 09:05 job missed.
15. **A label that returns (B).** Every reader takes the newest engine id (`forward_db.engine_now`) as the current
    series. A label that already has a row which is not the newest (a rollback of an evidence module) would be
    written under its old id while every meter read a series nobody writes. The shadow opens a NEW series for it,
    `<label>~<the id it follows>` in `fwd_engines`, with one `engine_moved` event: tonight's engine id is always
    `engine_now`, and `engine_label` of such an id carries the suffix.
16. **`fwd_runs.programs` (B)** counts the programs whose run completed THAT NIGHT, whichever start of the job ran
    them (the DDL's comment), as `run_failed`'s `completed` does; `sessions`, `errors`, `stale` and `seconds` are the
    start's own. A second start of a night therefore never writes `programs` 0 beside a `run_failed` event.
17. **The shadow's receipt and its one warning (B).** Beside the spec's keys the receipt holds `finals`, `register`
    (the sync's counts), `marks` (item 14) and `house`: the programs left without rows by a failure of the House's
    own (in `errors`); `controls` holds `checks`, `restated`, `errors` and `data_failed` too. The job raises ONE
    `ctx.alert("warning")` a night for what leaves no event (`forward_shadow.house_failures`): `house`, the controls
    left without rows by anything but the data, and each step that raised (the sync, the audit marks, the controls,
    the final checkpoints, the twins).
    A `restated` event is one a program and cause (section 3): FW3 counts restatements, and their days are the
    payloads' `days`; `"bars": "moved"` is the routine ex-day one, `"same"` the one worth a warning.

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

## 7. What package D's build added (fills and twins; additive: no signature or column above changed)

- **What D reads of B's `Shadow`.** `store` (its `symbols()`), `through`, `official`, `run_from`, and the constructor's
  `decider` and `settings` UNDER THOSE NAMES (read with `getattr`: with no `settings` attribute D loads the swarm's
  settings itself; with no `decider` every twin is one `twin_interrupted` event a night and no row).
- **A retired instance (D12; `forward_twins.UNREADABLE` is now `("split", "retired")`).** The book retires or demotes
  an instance inside a session's decide step, before it asks the program, so from that session (`d_retired`: `d_first`'s
  rule on `retired_at`) no live decision exists, while D13's range runs through the session before the instance's last
  counted exit (the House's exit at the next open). Those sessions get a row with `agree` NULL and `why` "retired":
  shown, counted in `unreadable`, left out of every share, never `missing` (so a checkpoint can be final). The row
  keeps both key lists, so `Counter(live_keys) == Counter(shadow_keys)` can still be read from it. Once a retired
  instance's rows are written through the session before its last lot closed it has no twin run again, and its
  participation counts entries through its retirement only.
- **A revived instance (section 11, spec-2).** E1's book brings a retired instance back under the same key with
  `retired_at` cleared. `finish` keeps each retirement the night the book shows it (a `twin_retired` event, `day` the
  retirement session, once an (instance, session)) and starts a new run for an instance found running after one (a
  `twin_revived` event, `day` the session it ran again: the book's kv `eq_band_since[<instance>].day` when that is
  after the retirement, else the decision session of the night that first sees it). Each run is read as D12 reads an
  instance: its twin is D3's run started flat at the session after its first decision, the sessions from its
  retirement to the one before it ran again are "retired", and `fwd_part` is the current run's. `read_book` also
  returns `since`.
- **`a14_reading` reads `d_first(I)` as the day of the instance's first `fwd_twins` row** (the rows are written in day
  order from `d_first`); an instance with no row yet has every session from the one before its first counted lot's
  entry `missing`. It opens the forward store through `forward_db.open_db(root, readonly=True)` and the swarm store's
  kv read-only, and any raise of either is "unmeasured" (holds False, final False), never an error of the Done meter.
- **The forward mode "off" (or settings that cannot be read) is off for every D entry point**: `begin`, `on_run` and
  `finish` write nothing and `fill_minutes.run` is skipped, whatever `fill_minutes` and `twins` say.
- **A child that fails a twin's run** (`RunFailed`, `DeciderError`) is the House's, as an interrupted decide is: one
  `twin_interrupted` event (once an (instance, night)), no row, tried again the next night. A data error of the run
  is counted in `finish`'s receipt (`failed`, `errors`) and costs no other instance its rows.
- **A minutes file is written once**, so `fill_minutes.run` writes none for a day whose answer lacks the send-minute
  bar of `equity_data.CALENDAR_SYMBOL` in either window (a failed receipt: retried inside its grace, then by the
  backfill); and a closed lot's `fwd_lotgap` row waits while the minutes job may still fetch a missing file of its
  entry or exit day (the last `BACKFILL_SESSIONS` forward days), then is written with what there is. A day that is
  not ready never holds up the days after it: the run writes every ready day of its backfill and fails at its end
  (`day`: the first it left; `unready`: how many).
- **The engine id of a re-price.** `on_run` files a run's `fwd_ll` rows under the id of the newest `fwd_days` row of
  the run's last day (what B's `write` just wrote), and under `forward_db.engine_now` only when there is none. FOR
  THE INTEGRATOR, not D's to fix: B writes a night under `engine_id(fwd_engine())`, while `engine_now` (A's
  `counted_days` default, C's meters) is the LARGEST id. They are the same id until an engine label COMES BACK (a
  rollback restores an equity fingerprint that already has its id while a newer id exists). SETTLED by package B
  (section 4, item 15): a label that returns is written as a NEW series, `<label>~<the id it follows>`, so tonight's
  engine id is always `forward_db.engine_now` and no reader reads an abandoned series.
- **Names added**: in `fill_minutes` `FILL_POINTS`, `STAMP`, `LOOKBACK_DAYS`, `livelike_of`, `inside`, `path_of`,
  `days_on_disk`, `due_days`; in `forward_twins` `LIVE_DB`, `SWARM_DB`, `KIND`, `DECIDE_TIMEOUT`, `DECIDE_MAX_ERRORS`,
  `REAL_SUFFIX`, `RUN_FAILURES`, `FINISH_KEYS`, `d_retired`, `registry_key`, `read_book`, `twin_records`.

## 8. Package A as built (the forward store, the registry's job, the control draw; additive)

Nothing of step 0's contract changed shape: every name of `test_e3_skeleton.SIGNATURES` keeps its signature and every
column of `COLUMNS` its place. What the other packages should know of `forward_db`, `forward_register` and
`forward_controls` as they landed:

1. **`forward_db.SCHEMA` now starts with `PRAGMA recursive_triggers=ON;`.** SQLite's REPLACE (`INSERT OR REPLACE`,
   `REPLACE INTO`) deletes the row it conflicts with WITHOUT firing a delete trigger unless recursive triggers are on,
   so with the spec's triggers alone a replace overwrote a row of an append-only table in silence. Every connection
   that runs the schema (a writable `open_db`, a package's in-memory test database) now refuses a replace with
   `APPEND_ONLY_ERROR`. "First write stands" is `INSERT` (IntegrityError on a known key) or `INSERT OR IGNORE`,
   never OR REPLACE.
2. **Transactions.** `open_db` returns a connection in sqlite3's default transaction mode, exactly what
   `sqlite3.connect(":memory:")` gives a test. Each write of `forward_db` (`event`, `tag`, `append_registry`,
   `kv_put`, `kv_first`, `engine_id`) is its own transaction and commits before it returns, UNLESS the caller already
   holds one, which it joins. `with forward_db.transaction(db):` (NEW) makes several writes one transaction; a plain
   `with db:` begins nothing by itself. A row a job writes with `db.execute(...)` is the job's to commit: on an
   in-memory test database a missing commit does not show.
3. **`event` is strict.** A kind outside `EVENT_KINDS` is a ValueError, and so is a kind of `ONCE_KINDS` written
   without `once`. The payload is stored as `results.canonical` (floats to six places, NaN as null); `day` may be a
   date. `once` is matched on (kind, pid, day), `pid` and `day` None included.
4. **`append_registry` refuses, before anything is written** (ValueError): a row outside (`E3_ROUTE`, `E3_ALPHA_F`) /
   (`CONTROL_ROUTE`, `CONTROL_ALPHA_F`); a control or a program carrying the other's lane, route, alpha, family or
   version; a `program_sha` that is not sha256 of `code`; an evidence that is neither "event:<seq>" nor "registry";
   evidence "registry" with `created_at` before `registered_at`; a `first_close` before
   `forward_db.first_close(created_at)` or a `first_day` that is not `first_day(first_close)`. A test that needs a
   registry row either builds a D2-consistent one (see `league/tests/test_forward_db.py` `registry_row`) or writes it
   with SQL.
5. **The stop rules read the night from the event.** `forward_register` counts a `run_disqualified` or `run_failed`
   event toward a night by the event's `day` (the night's `through`, ISO), else by its `once` key when that is an
   ISO day. The nights themselves are the distinct `fwd_runs.through`; a night counts toward "suspect" only when a
   row of it has `programs >= 1`; "after a resume" is `fwd_runs.finished` later than the resumed tag. B writes
   `through`, `programs` and `finished` on every `fwd_runs` row. **The nights counted are the program's own
   attempted nights** (section 11, live-1): those it has one of the two events for, and those a run of it completed
   (its `fwd_days` row for the night's day written no later than that night's `finished`).
6. **PARAMS are stored exact.** `fwd_registry.params` is the swarm's own encoding (`league.swarm.store.dumps`), not
   `results.canonical`, which rounds floats to six places: the shadow would have run other parameters than the row's
   `run_sha` names. `gate.run_sha({"sha": program_sha, "params": Program.params})` is the row's `run_sha`. `needs`
   and a control's `code` are `results.canonical`.
7. **Tags carry the registry's sighting.** A tag's `at` is the run of `sync` that first saw the fact (within the
   hour), not the fact's own time; values are "" but for "live" (the instance id), "stopped" ("cap:<night>" |
   "disqualified:<night>"), "suspect" (the night) and "resumed" ("<at>|<why>"). A live instance whose `run_sha`
   differs from its key's registry row is NOT tagged live (a `register_skipped` event, cause "live_sha").
8. **Added public names:** `forward_db.transaction`, `forward_db.last_stored_day(db, pid)`;
   `forward_register.identity_watch`, `instance_key`, `CAUSES`, `SWARM_DB`, `LIVE_DB`, `SCORED_KIND`, `SCORED_PASS`.
   `forward_register.resume` returns False, with nothing written, for a program that is not stopped.
   `scored_versions` rows carry `key`, `needs`, `ugroup` and `params_text`, and `created_at` None with evidence
   "registry" (the time is `sync`'s `now`).
9. **`control_lots`** counts a slot's lots from 1 (`lid` 1, 1001, 2001, 3001 are the slots' first); the last session
   of `sessions` decides nothing (its entry day does not exist yet). `cost_free` refuses lots not drawn at `k=0.0`.
10. **T1 (`test_e3_seal_imports`) reads the real sources at integration.** An E3 ops module importing a league module
    outside section 1's list, a memory module importing the swarm at its top, or an ops job opening `SwarmStore`
    without `readonly=True` (the probe excepted) fails there by name.
11. **T10 (`test_e3_identities` `TheWiringIsWhole`)** holds the spec's 11.1-11.3 together: all three applied, or none.
12. **The declared receipts** are `league/ops/release_receipts.json` (`release_receipts.DECLARATIONS`), not the
    spec's `docs/benchmarks/release_receipts.json`: the House's release carries `league`, `ltcm`, `playbooks`,
    `scripts` and `deploy` only (`scripts/floor_box.py` `UPLOAD_TREES`, `league/updater.py` `TREES`), so a file under
    `docs/` is never at hand there and no receipt would ever have been declared or read, in silence. Still behind the
    wall (`league/ops/`). `test_e3_identities.TheDeclaredReceipts` holds the file to the spec's 7.6 text (each metric
    is `forward_record.<a key of forward_report.FUNNEL_KEYS>`, read after 168 h) and its path to a tree the deploy
    carries (`test_the_declarations_reach_the_house`).
13. **The stop rules' events are the shadow's own shape**: `day` = the night (`through`), `once` = "night". A night
    whose `run_disqualified` or `run_failed` event is older than the pid's latest "resumed" tag is an old night,
    whenever its `fwd_runs` row landed. Pids follow the order the programs came to exist (the scored event's time;
    a version with no event after those of the same run).
14. **A run that could not read the swarm store writes no tag** (a "live" tag neither) and registers no live
    instance; the next run that reads both the swarm store and the book does. The stop rules and the chain check
    still run (they read the forward store alone), and the job's receipt is `failed` so the runner starts it again
    inside its grace.

## 9. What package E's build added (the memory tables and the probe; additive: no signature or column above changed)

Every signature of `test_e3_skeleton.SIGNATURES` stands. What other packages and the integrator read beside it:

- **The patches 11.7-11.9 land together with `elane.memory.mode` "record" in policy.json (11.2).**
  `league/tests/test_elane_memory_seal.py` runs the wired flow only when `elane_train` imports `elane_memory` and
  `elane_births` imports `elane_folds` (`league/tests/elane_e3_fakes.py` `WIRED`); a tree whose policy says "record"
  without them fails `TheSwitchAndTheWiringLandTogether`. No test of that file may read "skipped" after integration.
- **THE LISTING RULE (D14 as built; the spec is silent on a symbol listed after 2016).** E1's engine ends a run
  "no_data" when a NEEDS symbol has no bar in it, and E2 reads that as the House's failure (nothing scored, backoff for
  ever). A whole Train span always holds a bar of such a symbol (XLC's first is in 2018); a stretch the cut leaves may
  hold none (2016-17 once 2018 is hidden). So `elane_folds.birth_fields` draws the hidden year by D14's formula over
  the RUNNABLE years alone, `R[(k_c + h(cell)) % len(R)]`: a year is runnable when each of its seen spans and its own
  span hold a bar of every symbol, by the House store's MANIFEST (`bar_years`: each symbol's first and last bar day;
  no bar is sliced, no reserve session read). With all seven runnable (every symbol of today's `elane.universe`) that
  is D14's formula exactly; no runnable year is no hidden year; no equity store under the swarm's root is the formula
  alone; a store that is there and cannot be read raises into 11.8's guard (`FALLBACK` and the MM1 alert).
- **The memory tables (C, the integrator).** `elane_memory.SCHEMA` carries a THIRD trigger a table
  (`<table>_first_write`, keys in `elane_memory.KEYS`): an insert of a key already written is dropped, whatever its
  conflict clause (SQLite fires no DELETE trigger for the row an `INSERT OR REPLACE` displaces unless
  `recursive_triggers` is on; A closes the forward store's own with that pragma). `mem_seen.at` and `mem_contrib.at`
  are the swarm store's ISO text; `mem_seen.fails` is a JSON list; `seen_sha` is `elane_memory.seen_sha(verdict)` (the
  Train figures as `elane_train.compact` shapes them, without `at` and `identity`); `mem_contrib.run_sha` is the
  hidden run's own (E1's `EquityProgram.run_sha`), never `gate.run_sha`; `elane_memory.counts(db)["by_year"]` has
  string keys. A series is stored once under its sha (two contributions may share one). A hidden run already recorded
  at a k is not run again.
- **The probe's dollars (the integrator; E2's owner).** AS BUILT, and needed on E2's branch as it stands after the
  base: (1) a run's BOUND is min(`elane.contam.usd_run`, `elane_yield.room` when it starts), and a run is skipped only
  when that room is zero (the spec's "skipped while room < usd_run" skips every run once E2's day line is under
  `usd_run`, which it is where E2 holds its day to a share of the swarm's Sail model line); (2) every request key
  begins `contam_probe.KEY_PREFIX` ("swarm:elane:probe", then the route, `probe_n`, the run and the batch's hash),
  the equity lanes' mark in the swarm's spend rows, so the swarm's meters count the probe as E2's and the options
  researchers' hourly pace does not read it as theirs. The ledger rows are "probe:<route>" (a window fallback's
  answer on the row of the profile that gave it).
- **A probe's request key is asked once (the review's fix; the spec's 7.10, 8.2 and 12.1 said a resumed probe
  "re-reads its answered batches at $0").** It does not: on the real router a repeated key is answered from the
  Provider's stored row WITH THAT ROW'S ORIGINAL COST (ltcm/provider.py `_response_from_row`), and
  `ModelRouter.compact` blanks the stored response of a settled call after an hour, so a week later the text is
  empty. AS BUILT: `KEY = f"{KEY_PREFIX}:{route.key}:{probe_n}:{attempt}:{h}"`, `attempt` = the route's `attempts`
  counter (its runs; written with `attempted_at` before any call; never truncated), so no run sends a key an earlier
  run sent. A resumed probe keeps its SCORED CELLS; a cell a stop cut is asked again whole under the next run's keys
  and paid for again. A cell is begun only when its batches at `partial.batch_usd` (the dearest batch the probe has
  paid for) fit the run's bound and E2's day; a key `elane_yield.booked_for` already finds in the swarm's spend rows
  is not asked ("stopped": "error"); an answer with no text is booked, ends the run ("stopped": "error") and is never
  scored. The file's route row gains `attempts`, `first_attempted_at` (written once: CP1's clock for a route no
  probe ever finished on) and `partial.batch_usd`. `test_contam_probe.OnTheRealRouter` holds this on the real
  `ModelRouter` and `Provider` with a `compact()` between two runs.
- **The probe's file (C: `contamination`, CP1, CP2).** `at` and `attempted_at` are ISO text (`schedule.iso`; read them
  with `schedule.epoch`). A published route also carries `newly_recalled` (the "stratum/era" cells recalled now and not
  in its result before) and a partial `model`; `contam_probe.read(root)` gives the file as the job keeps it;
  `IDLE_ALARM` (3) is CP2's bound and `JUDGED_ERAS` the eras CP1 reads. The job itself raises CP2 (warning, when
  `idle` reaches the bound) and CP1 (info, a 2025 or 2026H1 cell newly recalled) through `ctx.alert`, their texts ids,
  counts and names only. Its receipt: {route, probe, usd, bound, finished, cells, asked, stopped ("usd" | "time" |
  "error" | "data" | "fallback" | None)}, and `error` beside the last three.
- **One route, one model.** An answer the router's own Sail window fallback gave on another profile is scored by
  nothing: the run ends ("stopped": "fallback"), the route adds no cell and CP2 names it at the third such attempt.
- **What the spec left open, as built.** The probe's universe is `equity_data.universe()` (the store's symbols, so S3
  has its stocks); S2 is every ETF but SPY; a period belongs to the era its last session falls in and runs from the
  last session before it, so January 2016 and 2016's first week are in no grid; a cell's "answered" share is over all
  its questions; `parse` reads the array with the most usable answers of those a reply holds, and of a reply cut at
  its output bound the whole entries before the cut.
- **Names added**: in `elane_folds` `born`, `bar_years`, `runnable`; in `elane_effects` `t_stat`, `YEAR_SESSIONS`,
  `MIN_EXPOSURE`, `MIN_SD`; in `elane_memory` `KEYS`, `seen_sha`; in `contam_probe` `KEY_PREFIX`, `ARRAY_STARTS`,
  `AGAINST`, `WORDS`, `RECALL_ERA`, `IDLE_ALARM`, `JUDGED_ERAS`, `CELL_KEYS`, `RECALL_KEYS`, `MAX_OUTPUT`, `EFFORT`,
  `periods`, `stratum_symbols`, `read`, `Probe`; and the test helper `league/tests/elane_e3_fakes.py`.

## 10. The integration (what landed with the five packages, and what moved under them)

- **What this tree carries.** Step 0 (550144d8) with packages A (7f3f29eb), B (5e1fb0e0), C (48c216d3), D (c181bcb8)
  and E (cce2b5d7) merged, then `feat/equity-e2-int` at 5ad1f01e (which holds `feat/equity-e1` at 05f83d9e and
  `feat/equity-e2` at 04ca26c9: 83 commits of E1's and E2's review fixes past step 0's base). Every patch of section
  5 is applied: 11.1-11.3 and 11.10 (A's, its diffs for the moved base), 11.4-11.6 (C's, its edit set for a tree that
  carries E1's own A14 reader; `league/tests/test_forward_patches.py` now holds the real files to every added line),
  11.7-11.9 (E's one commit). No stub is left: `test_e3_skeleton` still holds every signature and column.
- **THE BASE MOVED, and three things followed.**
  1. *The slice* (section 4, item 2): E1's store hands `history` + 1 sessions before a run's first by itself.
     `Shadow.slice` asks for NEEDS' own history; `Shadow.official` reads its slice's one run session at `bars.first`
     (it expected a slice of exactly one session, found the look-back session beside it and answered None for every
     symbol: the timing table and every live-like re-price would have been empty). Package D's fake of the shadow follows. A store that went back to
     `history` sessions fails `test_forward_shadow.NoDayBeforeItsCodeExisted` by name.
  2. *The audit rows* (item 14): E1 now marks each audited symbol's rows on its own verdict. `forward_audit` still
     reads the book's note first, because the evening fetch still resets the guilty raw row; its test on E1's real
     book holds both facts.
  3. *A14 in the Done meter* (11.5): E1 landed `a14_consistency` in `dlane_report.reading` (the fill-gap half, item
     4 forced False "until the intents half's reader lands"). As integrated: `meter` hands each checkpoint's reading
     the forward record's A14 (`reading(..., a14=a14_of(...))`); `a14_consistency(counted, forward)` then returns
     that reading with E1's own fill-gap keys beside it and holds only when BOTH say yes; the running figures (never
     a Done reading) are handed none and stay "not read". Item 4 of a checkpoint is the pinned rule's own measure AND
     A14. Two of E1's tests that pinned "no reader yet" follow (`test_dlane_report_equity`, `test_equity_fx_swarm`).
- **The three ids, read with the repository's own functions** (`evaluator.execution_fingerprint`,
  `evaluator.equity_identity`, `constitution.money_digest`). Equal at 5a6906ff and on that tree with the five
  packages merged; equal at `feat/equity-e2-int` 5ad1f01e and at this branch's head. Between 5a6906ff and 5ad1f01e
  all three moved, by E1's and E2's own commits (`league/live`, `league/equity`, the constitution's money table):
  release E3 moved none, and T10 (`test_e3_identities`) holds that no E3 path lies in any of the hashed sets.
- **FW3's level is its cause** (`forward_report._restated`; the spec's 12.3 says "warning"). The vendor restates a
  symbol's adjusted history at every ex-day, rounded to cents (section 3, fact 1), so a routine ex-day of a held
  symbol restated nearly every stored day of every holder and FW3 would have mailed a warning most weeks. It is
  "info" when every restatement read bars that have moved since or is a control's (`bars` "none"), and "warning"
  when one read the same bars or is a program's with no bars hash.
- **T11** is `league/tests/test_e3_end_to_end.py` (`TheWholeNight`): E2's researcher on E1's runner -> the scored
  event -> the registry's job -> 22 nights of the shadow job in its own decider instance -> the minutes job against
  a synthetic venue -> the report job, the funnel -> E1's own twin round, the fill-gap parts and the intents' twin
  rows (one disagreement on bars a cent away: counted with its cause) -> the Done meter's 30-close checkpoint
  carrying A14 as `a14_reading` reads it -> the generators' views byte for byte unchanged and no row of the swarm
  store written by an E3 job. `WithEveryModeOff`: the three switches off, every job a skipped receipt that touches
  no gateway, model route or decider child. These tests read an EMPTY policy (league/tests/__init__.py): a fixture
  that wants the record on says so in its swarm.json.
- **What a test fixture must know** (found building T11): `forward_report.read_section` reads staleness from the
  wall clock, not from a `now` (its signature has none), so a fixture dated in the future is never stale;
  `fill_minutes.run` asks for `equity_data.universe()` (35 symbols) and is ready when the calendar symbol's
  send-minute bar is in both windows; the shadow job's child is `forward_shadow._decider(root)` (the one seam a test
  swaps for an `InlineDecider`); a live book's `eq_bars` rows need their morning audit ("ok") before E1's twin of a
  lot is final, else it waits two sessions.
- **Left open, for the captain** (each stated in docs/operations.md): `elane.contam.usd_run` (at 3.0 a probe may take
  the equity lanes' whole Saturday of research dollars: section 9); the listing rule of the hidden year (section 9);
  a retired instance's sessions read "retired", unreadable (section 7); `suspect` is tagged each night after the
  third (section 8's stop rules); the House facts of the spec's section 15, none of which blocks the deploy.

## 11. The review's fixes (twelve findings, after the integration; what each changed against the spec)

Every fix has a test that fails on the integration's head (57eba7c1) and passes here; where a test needs a name the
fix introduces, it errors there, and the old behaviour itself is shown by the reviewers' scripts or by a script run on
the old tree (kept privately with the build's notes, never committed).

| finding | what changed | against the spec |
|---|---|---|
| seals-1 (blocker) | `elane_memory.hidden_runner`: the hidden runs of one version are made on E1's `Isolated` over the same store on a NEW decider child (the seen child's class, limits, interpreter and hash seed; log `HIDDEN_LOG`), closed when they are in. A runner that is not E1's `Isolated` on E1's decider must offer `hidden_runner()` itself (the tests' invented markets), else `HiddenRunRefused` and no out-of-fold row. `test_elane_memory_seal.TheHiddenYearNeverReachesALaterVersion` scores two versions on a real child a House | 7.9 handed `ingest` "E1's `Isolated`" and ran the hidden span on it; D14's "what still reaches a seen run" did not name the child's own memory. Section 1's import rule gains the two imports above. NOT FIXED HERE, AND SAID TO E1'S AND E2'S OWNERS: the same child runs Train, Validation and the sealed look, and E2's memory rule lets a call's result expose a class-level array (`league/gym` is not E3's to edit) |
| seals-2 | a probe's request key carries the route's run (`attempts`): no run repeats a key. A cut cell is asked again whole and paid; a cell is begun only when the run can pay for it; a key already booked is not asked; an answer with no text is booked, ends the run and is not scored (section 9) | 7.10, 8.2 and 12.1's "a resumed probe re-reads its answered batches at $0" was false on the real router |
| seals-3 | `forward_report.METER_MIN` (5): the report shows `m` always and `bh`, `by_`, `reading`, `unreliable` only at the floor (None and "too few lineages to read" under it); `funnel_rows`' `bh` and `by` are 0 under it. `fwd_meter` keeps the whole row | D8 and 12.2 gave the meter no floor; section 9's "shown to no one" did |
| live-1 | the stop rules count the pid's own attempted nights (item 5); `Shadow.night` keeps back `RETRY_RUNS` x `run_budget_seconds` a listed program; `Shadow.due` puts a program whose last attempt failed twice behind its class; `run_behind` (B, once a (pid, night)) is that order's mark on a night nobody else completed | 7.2's "on each of the last N nights" was read by the calendar; 7.3's retry ran "while the budget allows", which on a binding night was never |
| live-2 | `elane_memory.seen_hidden`: a family whose record (or verdict in hand) holds a `years` row of its hidden year gets no hidden run and no `mem_contrib` row from then on; its `mem_seen.hidden_year` is NULL from that version; one `swarm.status` "elane_memory" alert a family | the spec's rollback text covered the switches, not a code rollback |
| live-3 | `forward_report.meters` writes a day once no active registered program owed it lacks its row, or after `METER_WAIT_NIGHTS` (3) later nights, then with one `meter_partial` event (C). The receipt's `waiting` names the day. FW5 reads no partial day | 7.5 wrote every day up to the last `fwd_runs.through` at once |
| live-4 | `Shadow.late()` (the night's deadline) is read by the timing table, each control and each instance's twin run (`finish` reads `shadow.late` when the shadow has one); what is not started is `deferred` in the receipt (`controls.deferred`, `twins.begin.deferred`, `FINISH_KEYS` gains "deferred") | 7.3 named the deadline for the due loop only |
| live-5 | `forward_stats._participation` sums the pairs `BLOCK_ROWS` rows at a time (the same exact sums); `forward_db.programs(..., code=False)` is a listing read from the cursor a row at a time, used by `Shadow.due` and the audit marks; `Shadow._whole` loads the program a run is made of and refuses a text that is not its sha's | 5's bound of 3,000 members did not fit the job's address space; 7.1's `programs` signature gains `code` |
| spec-1 | `Shadow.finals` writes `final` 0 when the stopped program's counted days are a grid count, 1 off the grid | D4: a final checkpoint is for a program stopped OFF the grid |
| spec-2 | the bullet "A revived instance" of section 7; `twin_retired`, `twin_revived` (D) | D12 knew one run an instance |
| spec-3 | CP1 reads the configured routes (`elane_yield.cfg(settings)["routes"]`) and the file's, from a route's last completed probe, else the earlier of the file's `first_attempted_at` (the probe writes it once) and the report's `contamination.first_seen` | 12.3's "a route unprobed for 45 days" was read off the file's rows by their last attempt |
| spec-4 | `forward_report.raised`: FW1-FW8 follow `elane.forward.mode`, CP1 and CP2 `elane.contam.mode`, RR and MM none. With the forward mode off `run` writes `OFF_KEYS` ({"at", "mode": "off", "memory", "contamination", "receipts", "alarms"}) and `alarms` returns the file's rows by their switches | 3.3 and 7.5 wrote {"at", "mode": "off", "alarms": []} and returned [], which silenced RR, CP and MM against 12.3 and section 10 |

**Event kinds added:** `run_behind` (B), `twin_retired`, `twin_revived` (D), `meter_partial` (C; `EVENT_KINDS`' owners
are now A, B, C, D), all in `ONCE_KINDS`. **No table or column was added**; the probe's file gained `attempts`,
`first_attempted_at` and `partial.batch_usd`, the report `meter.floor`, `contamination.first_seen` and the route
rows' `first_attempted_at` and `attempts`. **Names added:** `elane_memory.HIDDEN_LOG`, `HiddenRunRefused`,
`hidden_runner`, `seen_hidden`; `forward_shadow.RETRY_RUNS`, `Shadow.late`, `Shadow.deadline`;
`forward_stats.BLOCK_ROWS`; `forward_report.METER_MIN`, `METER_WAIT_NIGHTS`, `METER_UNREAD`, `OFF_KEYS`, `raised`.

## 12. The merge with main, the gateway's list and the verification's fix (Oct 11, 2026)

- **What this tree carries now.** The branch at 45ea8143 (sections 10 and 11) merged with main at 87f9fd0c, which
  holds releases E1, E2 and E2.2 as deployed and E2's gateway follow-up (a11bd338). Every line of both sides is kept.
  Three hunks were resolved by hand: `league/ci.py` and `league/tests/test_ci.py` (E2's five modules in `FORBIDDEN`'s
  own list, as main has them) and the import line of `league/swarm/elane_births.py` (`elane_folds` and
  `elane_review`); one pin followed (`test_e3_identities.TheWiringIsWhole.test_the_three_paths_behind_the_wall`).
  E2.2 also changed `league/swarm/elane_train.py` and docs/operations.md, which this release patches (11.7, 11.10):
  those merged without a conflict, and E2.2's own tests and this release's pass on the merged tree.
- **The three ids** (section 10) are main's on the merged tree, read with the same functions on Python 3.11 and
  3.14: release E2.2 moved none, and neither does anything below.
- **The gateway's merge list (11.3, as shipped).** The three swarm modules are in `ci.FORBIDDEN`'s own list and in
  `gateway/lib/protected.mjs` `MERGE_FORBIDDEN`, as E2's five are since a11bd338; `ci.PENDING_GATEWAY` is `()`.
  That list is the ONE change under `gateway/` in this release (the hard rule above bound the five packages; this is
  the release's gateway follow-up, made with it). `test_ci` holds the two lists to each other from the league's
  side, `gateway/test/merge.test.mjs` from the gateway's, and `test_e3_identities` reads the gateway's file for the
  three. The gateway deploys before the House.
- **The verification's one finding (minor; `forward_report._awaited`, live-3's rule completed).** Section 11's live-3
  awaited every active program without its row, so ONE program that never got a row again (a holder of a halted
  symbol, the shadow's STATED LIMIT; a program that hangs every night) made every later day's meters
  `METER_WAIT_NIGHTS` sessions late and `meter_partial` for good, and FW5, which reads no partial day, read nothing
  from then on. As fixed: a program without its row for a day is awaited when its absence began that day (it has
  its row, under any engine, for the session before, which it was owed too), whatever the cause; or when it has been
  without one for fewer than `METER_WAIT_NIGHTS` owed sessions running and is neither suspect
  (`forward_db.suspect`) nor behind in the queue (`forward_report._behind`: a `run_failed` or `run_behind` event
  newer than every row of its own, as `Shadow._behind` reads it; a test holds the two to each other). A day is
  marked partial, and left out of FW5, only for a row still awaited when its wait ends. A control without its row
  is awaited by the same rule when its data failed (a `data_failed` event of its own for that night or a later
  one); a control was never awaited before, and a late vendor bar left the day's control group short of it for
  good. What a standing absentee still costs: the first one or two days of its absence wait their three nights and
  are partial; FW2 goes on naming it. **Names added:** `forward_report._behind`. No table, column, event kind,
  setting or receipt key changed.

## 13. Release E3.1: two rules registered before the first real share order (the captain's A28 and A29, Oct 11, 2026)

Both come from the rehearsal of the first real-money session, and both were registered (20:13Z Oct 11, 2026) before
any real share order or twin row existed.

**A28, AN EXIT'S WAIT FOR THE PRACTICE PROOF HAS AN END** (the EquityBook's rule, not this record's: league/equity/
live.py `_work_exit`, `_sell_proof`, `_sell_unproven`; league/equity/INTERFACES.md; it is here because the forward
record measures what it prevents). Every real sale waited for the stock paper proof's SELL stage with no end: if the
practice sale could not be witnessed, real lots stayed held for days (a program's sale, the maximum-hold exit, the
owner's flatten) and new buys stopped. THE RULE: the wait ends at the open window's entry cut-off
(`schedule.Moments.entry_until`, the open + 900 s); after it every exit goes through the normal path, with one
error alert a session saying the sale path is unproven. UNCHANGED: stage BUY gates every real buy with no end; a
failed SELL stage stops new buys; the minimum hold, the kill switch and the stops. **Why:** an exit must never be
blocked; a proof exists to stop new risk, not to trap old risk. **The cost, as the captain stated it:** a real sale
can go through a path the practice account did not prove that day. For this record: a sale held past its session
left the live lot where its twin was flat, and every session after it differed.

**A29, THE TWIN IS RE-BASED AFTER A DIFFERENCE, SO A MISS COUNTS ONCE.** It amends how D12's intent agreement is
COMPUTED. A14's bounds (`forward_db.A14_AGREE` 0.95, `A14_GAP_BP` 15), the keys (`keys_of`), what a row's registered
columns hold and the pooling (`a14_reading`'s rule) do not move: on a path with no difference the rows are byte for
byte the rows of the release before (`league/tests/test_forward_rebase.py` pins their sha256, taken on that
release's tree), and a differing session's own row is that release's row too.

- **The rule.** A session whose keys differ is written as differing, as registered (whatever its cause). THEN the
  twin's book is set to the live book as it stands after that session, and the sessions after it are compared from
  the same state. A re-based twin that differs again counts again and is re-based again. **Why:** the registered
  twin never misses a fill, so ONE missed buy of a program that buys only when flat left the live book a session
  behind it for good (about half its sessions differing from then on), and one such program failed the pooled bound
  for every program at the checkpoint: one execution failure counted many times. **The cost, as the captain stated
  it:** a program can run for weeks on other days than its unconditional replay and still read consistent after the
  one counted difference; the un-re-based figures beside it say so.
- **The live book after session d** (`forward_twins.live_seed(book, instance, after)`, from `read_book`'s rows of
  live.sqlite; read-only; no status and no column the book rewrites later): `lots` = the instance's `eq_lots` rows
  with `opened_day` <= d and no `exit_day` at or before d, each with the `size` its own buy asked (the `eq_intents`
  row whose `lid` is the lot's, else the lot's `iid`: `share` or `usd`; None when no buy of the book names it);
  `buys` and `sells` = its `eq_intents` rows of kind "buy" and "sell" with `decided_day` = d and `exec_day` =
  `next_session(d)` (a buy with no size and a sell of a lot not held are left out, as the Gym never executes them);
  `exits` = its kind "house_exit" rows with `exec_day` = `next_session(d)` and `decided_day` <= d. `read_book` reads
  them in its one pass: `eq_lots.iid`, `tag`; `eq_intents.exec_day`, `share`, `usd`, `tag`; and `exits` {instance:
  its "house_exit" rows}.
- **The re-based twin** (`forward_twins.RebasedTwin(decider, run)`; `rebase(seed) -> {"held", "unheld"}`,
  `step(day) -> (keys, bars hash) | None`, `close()`). It is E1's own engine account (`league.equity.engine._Account`
  on the twin run's bars, capital and half-spread multiple: nothing of the engine is re-implemented in ops, and no
  equity evidence module is edited). (1) Each seeded lot is bought by the engine in its own entry session, at its
  fill point, for the size its buy asked, and carried to d's close through the engine's sessions (corporate actions
  and marks; no decide, no exit rule): the replay's lot on the Gym sleeve, so no dollar of the live account enters
  it. (2) The planned intents are the account's own for `next_session(d)`: the program's buys and sells, the House's
  exits (a reason other than "program" or "max_hold" reads "house", as the book's `_ctx_reason`), and the engine's
  maximum-hold rule on the seeded lots. (3) From then on the account runs as `engine.run` does. The engine's runner
  is the `RebasedTwin` itself: each decide is asked of the night's decider child on `ctx.inputs_from_bars` of the
  account's own state (no program text runs in the job's process). ONLY THE BOOK IS SET: one instance of the program
  (key `REBASED_KEY` + the registry key), loaded once and asked every session in order: the un-re-based run's own
  decisions through the first differing session, the account's after it. NEVER A SILENT RELOAD (`_answer`, the
  check `_twin` makes: `TwinInterrupted`). A lot the Gym cannot hold as the live book does (no size, no official
  price, sized to nothing, outside NEEDS or the bars) is `unheld` and not held.
- **The night** (`finish`, per run of an instance): the un-re-based twin run and its decides are made whole, as
  before. Sessions are then read in day order. A differing session re-bases the twin for the next one when that
  one is not written yet, or when the re-base is on record (its event), so a later night makes the same twin. ROWS
  FROM BEFORE THIS RELEASE: the latest stored differing session re-bases the twin for the sessions not yet written
  (the twin goes through the stored sessions after it in order); an earlier one, whose next session was written
  against the un-re-based twin, re-based nothing then and re-bases nothing now. What is gathered is written before each re-base (one transaction
  a stretch, the night's `fwd_part` row with the first), so a re-base that cannot be made tonight (`twin_interrupted`,
  as before) never costs the rows before it. A retired session re-bases nothing. THE SPLIT RULE stands for sessions
  compared with the twin run; a session compared with a re-based twin is read (its inputs hold a lot's quantity as
  it was at each close). `fwd_part` is read against the un-re-based twin run, as before.
- **The store** (`forward_db`): `fwd_twins` gains `rebased INTEGER` (the instance's re-bases before that session,
  counted from its `twin_rebased` events; 0 for the twin as registered) and `base_agree INTEGER` (1 | 0 | NULL: the
  same session against the UN-RE-BASED twin run; NULL when that comparison is unreadable). `ADDED_COLUMNS` lists
  them and `_migrate` (in a writable `open_db`) adds each to a store made before it with `ALTER TABLE ... ADD
  COLUMN`: the declaration changes, no row is rewritten, the append-only triggers stand; an older row reads NULL
  there (`rebased` NULL is 0, and its un-re-based answer is its `agree`). `has_column(db, table, column)` is the
  reader's question on a store nobody has opened for writing yet (`a14_reading` and the report ask it and read
  NULL). Event kind `twin_rebased` (D; in `ONCE_KINDS`, once an (instance, session); `day` the differing session;
  payload `instance`, `held` [[symbol, entry day, fill point]], `unheld`, `planned` {buys, sells, exits}, `why`),
  written the night the re-based twin is first compared. The twin's book is stored nowhere.
- **The readings, beside and never in a rule.** `a14_reading` returns `rebase` (`A14_REBASE_KEYS`: `rebases`,
  `sessions`, `agreed`, `share`, `by_instance` [`A14_REBASE_INSTANCE_KEYS`]): over the counted sessions, the
  re-bases (the rise of `rebased` across them) and the un-re-based twin runs' own agreement; `A14_KEYS` gains that
  one key, and `gap`, `intents`, `by_instance`, `holds`, `final` and `why` are computed as before. The forward
  report's `fills` gains `rebase` in the same shape (one row a live instance), which the `dlane` report carries in
  `forward_record`. `finish`'s receipt gains `rebased` (`FINISH_KEYS`).
- **Names added:** `forward_db.ADDED_COLUMNS`, `has_column`; `forward_twins.live_seed`, `RebasedTwin`,
  `REBASED_KEY`, `CTX_REASONS`, `A14_REBASE_KEYS`, `A14_REBASE_INSTANCE_KEYS`. No setting, no job, no alarm and no
  identity changed (the options execution fingerprint, the equity identity and both digests are main's).
- **Its tests' live books** (`test_forward_twins.live_path`) are their own decisions' doing: the engine account
  deciding through the program, with a session's entries or exits taken away. A book that holds a lot no decision
  of its own bought (`mirror` with a skipped decide) cannot be followed by a twin set to it, and differs once more.
