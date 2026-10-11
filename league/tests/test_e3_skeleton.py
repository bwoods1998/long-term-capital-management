"""Release E3's step 0 (league/ops/E3_INTERFACES.md): the skeleton five packages build against. Every new module
imports and holds every public name of its contract under the contract's signature; the forward store's DDL, the
memory tables' and the receipts' create (twice: idempotent) with exactly the contract's columns; the shared constants
and dataclasses are complete; and the one shared function that is complete from step 0, the bars hash of a decision,
reads the as-of bars and nothing else of a decision. What a stub does once built is its owner's test; this file holds
only what must stay true through the build. A package that needs a signature or a column changed goes through the
integrator, who changes it here. Every store, program and number here is synthetic."""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import importlib
import inspect
import sqlite3
import tempfile
import unittest

from league.equity import results
from league.ops import forward_db, release_receipts
from league.swarm import elane_folds, elane_memory

#: package -> its new modules (league/ops/E3_INTERFACES.md, the ownership map).
MODULES = {
    "A": ("league.ops.forward_db", "league.ops.forward_register", "league.ops.forward_controls"),
    "B": ("league.ops.forward_shadow", "league.ops.forward_audit"),
    "C": ("league.ops.forward_stats", "league.ops.forward_report", "league.ops.release_receipts"),
    "D": ("league.ops.fill_minutes", "league.ops.forward_twins"),
    "E": ("league.swarm.elane_folds", "league.swarm.elane_effects", "league.swarm.elane_memory",
          "league.ops.contam_probe"),
}
#: The House jobs' modules: each has `run(ctx)` (league/ops/registry.py imports "league.ops." + the job's name).
JOBS = ("forward_register", "fill_minutes", "forward_shadow", "forward_report", "forward_audit", "contam_probe")

#: THE CONTRACT'S SIGNATURES: parameter names in order, "*" before the keyword-only ones, "=" after one with a default.
SIGNATURES = {
    "league.ops.forward_db.bars_hash": "(inputs)",
    "league.ops.forward_db.cfg": "(settings)",
    "league.ops.forward_db.mode": "(settings)",
    "league.ops.forward_db.t0": "()",
    "league.ops.forward_db.first_close": "(created_at)",
    "league.ops.forward_db.first_day": "(first_close)",
    "league.ops.forward_db.fwd_engine": "()",
    "league.ops.forward_db.open_db": "(root, *, readonly=)",
    "league.ops.forward_db.row_hash": "(prev_hash, row)",
    "league.ops.forward_db.append_registry": "(db, row)",
    "league.ops.forward_db.verify_chain": "(db)",
    "league.ops.forward_db.head": "(db)",
    "league.ops.forward_db.event": "(db, kind, *, pid=, day=, payload=, at, once=)",
    "league.ops.forward_db.events": "(db, kind, *, pid=, since=)",
    "league.ops.forward_db.kv_get": "(db, key, default=)",
    "league.ops.forward_db.kv_put": "(db, key, value)",
    "league.ops.forward_db.kv_first": "(db, key, value)",
    "league.ops.forward_db.engine_id": "(db, label, *, at)",
    "league.ops.forward_db.engine_now": "(db)",
    "league.ops.forward_db.engine_label": "(db, id)",
    "league.ops.forward_db.programs": "(db, *, reasons=, active=, code=)",   # `code` False: a listing (the review's fix)
    "league.ops.forward_db.active": "(db, pid)",
    "league.ops.forward_db.suspect": "(db, pid)",
    "league.ops.forward_db.program": "(db, key)",
    "league.ops.forward_db.tags": "(db, pid)",
    "league.ops.forward_db.tag": "(db, pid, tag, value=, *, at)",
    "league.ops.forward_db.counted_days": "(db, pid, *, engine=)",
    "league.ops.forward_db.stored_days": "(db, pid, *, engine=)",
    "league.ops.forward_register.run": "(ctx)",
    "league.ops.forward_register.sync": "(root, db, *, now, settings)",
    "league.ops.forward_register.scored_versions": "(store)",
    "league.ops.forward_register.seed_versions": "(store)",
    "league.ops.forward_register.live_instances": "(live_path)",
    "league.ops.forward_register.resume": "(db, key, *, why, at)",
    "league.ops.forward_controls.group_symbols": "(group, universe)",
    "league.ops.forward_controls.u": "(group, n, i, j)",
    "league.ops.forward_controls.spec": "(group, n, symbols)",
    "league.ops.forward_controls.control_lots": "(spec, sessions, *, k=)",
    "league.ops.forward_controls.cost_free": "(lots0, bars, *, capital)",
    "league.ops.forward_shadow.quiet": "(now)",
    "league.ops.forward_shadow.run": "(ctx)",
    "league.ops.forward_shadow.Shadow": "(self, root, db, *, decider, settings, clock=, fresh=)",
    "league.ops.forward_shadow.Shadow.preflight": "(self)",
    "league.ops.forward_shadow.Shadow.due": "(self)",
    "league.ops.forward_shadow.Shadow.slice": "(self, program, *, first_day=)",
    "league.ops.forward_shadow.Shadow.run_from": "(self, program, first_day, *, k=)",
    "league.ops.forward_shadow.Shadow.official": "(self, symbol, day, at)",
    "league.ops.forward_shadow.Shadow.run_program": "(self, program)",
    "league.ops.forward_shadow.Shadow.write": "(self, run, result15)",
    "league.ops.forward_shadow.Shadow.controls": "(self)",
    "league.ops.forward_shadow.Shadow.finals": "(self)",
    "league.ops.forward_shadow.Shadow.night": "(self)",
    "league.ops.forward_audit.run": "(ctx)",
    "league.ops.forward_stats.excess": "(r, w, b)",
    "league.ops.forward_stats.t_stat": "(x)",
    "league.ops.forward_stats.p_one_sided": "(t, n)",
    "league.ops.forward_stats.pairwise_corr": "(X)",
    "league.ops.forward_stats.neff": "(X, *, min_days=)",
    "league.ops.forward_stats.bh": "(pvalues, q=)",
    "league.ops.forward_stats.by": "(pvalues, q=)",
    "league.ops.forward_stats.independent_years": "(by_year)",
    "league.ops.forward_stats.replay_multiple": "(sim_py, hist_iy, cey_total)",
    "league.ops.forward_stats.rc_read": "(a, b)",
    "league.ops.forward_report.run": "(ctx)",
    "league.ops.forward_report.meters": "(root, db, *, now, settings)",
    "league.ops.forward_report.representatives": "(db, day)",
    "league.ops.forward_report.population": "(db, day)",
    "league.ops.forward_report.sim_program_years": "(root, db, day)",
    "league.ops.forward_report.hist_independent_years": "(root, symbols)",
    "league.ops.forward_report.rc_pairs": "(db, day)",
    "league.ops.forward_report.section": "(root, *, now, settings)",
    "league.ops.forward_report.read_section": "(root)",
    "league.ops.forward_report.funnel_rows": "(root, start, end)",
    "league.ops.forward_report.alarms": "(root, *, now, settings=)",
    "league.ops.release_receipts.declarations": "(release_dir)",
    "league.ops.release_receipts.metric": "(window, path)",
    "league.ops.release_receipts.step": "(root, base, release_dir, *, now)",
    "league.ops.release_receipts.rows": "(root)",
    "league.ops.fill_minutes.windows": "(day)",
    "league.ops.fill_minutes.fetch_minutes": "(gateway, symbols, start, end)",
    "league.ops.fill_minutes.write_day": "(root, day, bars, *, fetched_at)",
    "league.ops.fill_minutes.read_day": "(root, day)",
    "league.ops.fill_minutes.bar_start": "(day, at)",
    "league.ops.fill_minutes.livelike": "(root, day, symbol, at)",
    "league.ops.fill_minutes.run": "(ctx)",
    "league.ops.forward_twins.begin": "(root, db, shadow, *, now)",
    "league.ops.forward_twins.on_run": "(db, run, *, now, settings)",
    "league.ops.forward_twins.finish": "(root, db, shadow, *, now)",
    "league.ops.forward_twins.livelike_series": "(run, drift)",
    "league.ops.forward_twins.lot_gap": "(lot, twin, livelike_entry, livelike_exit)",
    "league.ops.forward_twins.d_first": "(instance_row)",
    "league.ops.forward_twins.keys_of": "(intents, *, needs, held)",
    "league.ops.forward_twins.shadow_intents": "(decider, run)",
    "league.ops.forward_twins.shadow_bars": "(run)",
    "league.ops.forward_twins.live_bars": "(live_path, instance, day, *, needs)",
    "league.ops.forward_twins.cause": "(agreed, live, shadow)",
    "league.ops.forward_twins.split_sessions": "(run)",
    "league.ops.forward_twins.live_intents": "(live_path, instance, *, needs)",
    "league.ops.forward_twins.agree": "(live, shadow)",
    "league.ops.forward_twins.participation": "(live_lots, twin_lots)",
    "league.ops.forward_twins.a14_reading": "(root, counted)",
    "league.swarm.elane_folds.mode": "(settings)",
    "league.swarm.elane_folds.cell_hash": "(cell)",
    "league.swarm.elane_folds.assign": "(store, cell)",
    "league.swarm.elane_folds.birth_fields": "(store, settings, *, lane, agenda, symbols, expected_oof=)",
    "league.swarm.elane_folds.hidden_year": "(fam)",
    "league.swarm.elane_folds.seen_spans": "(hidden)",
    "league.swarm.elane_folds.hidden_span": "(hidden)",
    "league.swarm.elane_effects.nw_se": "(x, lag=)",
    "league.swarm.elane_effects.contribution": "(run, *, k)",
    "league.swarm.elane_effects.horizon": "(lots)",
    "league.swarm.elane_effects.costs": "(seen10, seen15)",
    "league.swarm.elane_memory.ensure": "(store)",
    "league.swarm.elane_memory.ingest": "(store, fam, version, *, runner, code, params, seen, verdict, settings, now=)",
    "league.swarm.elane_memory.counts": "(db)",
    "league.ops.contam_probe.cfg": "(settings)",
    "league.ops.contam_probe.mode": "(settings)",
    "league.ops.contam_probe.grid": "(symbols, stratum, era, *, per_cell)",
    "league.ops.contam_probe.questions": "(symbols, *, per_cell)",
    "league.ops.contam_probe.recall_questions": "()",
    "league.ops.contam_probe.qset": "(questions)",
    "league.ops.contam_probe.truth": "(store, question)",
    "league.ops.contam_probe.prompt": "(batch)",
    "league.ops.contam_probe.parse": "(text, batch)",
    "league.ops.contam_probe.wilson": "(k, n)",
    "league.ops.contam_probe.perm_p": "(answers, truths, periods, *, seed)",
    "league.ops.contam_probe.score": "(questions, answers, truths)",
    "league.ops.contam_probe.due": "(doc, routes, *, now, every_days)",
    "league.ops.contam_probe.run": "(ctx)",
}

#: THE CONTRACT'S COLUMNS, in order (the spec's DDL; `fwd_days.bars` and `fwd_twins.live_bars`, `shadow_bars` and
#: `cause` are the bars hash's, found after the spec).
COLUMNS = {
    "fwd_kv": ("key", "value"),
    "fwd_engines": ("id", "label", "at"),
    "fwd_registry": ("pid", "key", "family", "version", "lane", "reason", "ugroup", "lineage", "code", "params",
                     "needs", "program_sha", "run_sha", "author", "created_at", "evidence", "first_close",
                     "first_day", "registered_at", "route", "alpha_f", "prev_hash", "row_hash"),
    "fwd_tags": ("pid", "tag", "value", "at"),
    "fwd_days": ("pid", "day", "engine", "r", "w", "b", "r15", "r0", "entries", "exits", "status", "at", "bars"),
    "fwd_ll": ("pid", "day", "engine", "r_ll", "at"),
    "fwd_checks": ("pid", "n", "day", "engine", "t_r", "sum_r", "sum_r15", "t_x", "mean_w", "p_x", "t_x0", "p_x0",
                   "final", "at"),
    "fwd_events": ("seq", "at", "kind", "pid", "day", "payload"),
    "fwd_runs": ("run", "job", "through", "engine", "started", "finished", "seconds", "programs", "sessions",
                 "errors", "stale", "budget_hit", "head"),
    "fwd_cey": ("day", "n_w", "members", "neff", "neff_raw", "cey_day", "cey_total", "sim_py", "hist_iy",
                "replay_multiple", "at"),
    "fwd_meter": ("day", "m", "bh", "by_", "min_p", "controls_m", "controls_bh", "controls_by", "controls_p10", "at"),
    "fwd_groups": ("day", "grp", "n", "mean_x", "mean_r", "mean_w", "mean_x0", "ugroups"),
    "fwd_fillgap": ("day", "symbol", "at", "official", "livelike", "drift_bp", "bar", "field"),
    "fwd_lotgap": ("lid", "instance", "pid", "symbol", "opened_day", "exit_day", "entry_at", "exit_at", "model_bp",
                   "entry_slip_bp", "exit_slip_bp", "timing_entry_bp", "timing_exit_bp", "exec_entry_bp",
                   "exec_exit_bp", "side_gap_bp", "twin_gap_bp", "at"),
    "fwd_twins": ("instance", "day", "pid", "live_keys", "shadow_keys", "agree", "why", "at", "live_bars",
                  "shadow_bars", "cause"),
    "fwd_part": ("instance", "through", "pid", "matched", "missed", "extra", "at"),
    "mem_seen": ("family", "version", "cell", "horizon", "hidden_year", "gid", "bar_passed", "fails", "drift_share",
                 "gross_bp", "cost_bp", "rt_per_year", "seen_sha", "at"),
    "mem_contrib": ("family", "version", "cell", "kind", "year", "symset", "k", "status", "n_days", "n_lots",
                    "exp_mean", "e_ann", "se_ann", "t_x", "series_sha", "run_sha", "at"),
    "mem_series": ("sha", "days", "x", "w"),
    "l3_receipts": ("seq", "id", "kind", "release", "metric", "direction", "min_delta", "window_hours", "deployed_at",
                    "value", "sd", "verdict", "at"),
}
#: Tables stored WITHOUT ROWID (the measured row sizes depend on it).
WITHOUT_ROWID = ("fwd_days", "fwd_ll", "fwd_checks")


def shape(fn) -> str:
    """A function's parameters as `SIGNATURES` writes them."""
    out, star = [], False
    for p in inspect.signature(fn).parameters.values():
        if p.kind is p.KEYWORD_ONLY and not star:
            out.append("*")
            star = True
        out.append(p.name + ("=" if p.default is not p.empty else ""))
    return "(" + ", ".join(out) + ")"


def resolve(path: str):
    """The object a dotted `SIGNATURES` key names: a module's function, a class (its `__init__`) or a class's method."""
    parts = path.split(".")
    obj = importlib.import_module(".".join(parts[:3]))
    for name in parts[3:]:
        obj = getattr(obj, name)
    return obj.__init__ if inspect.isclass(obj) else obj


def database(case: unittest.TestCase, *schemas: str) -> sqlite3.Connection:
    """An in-memory database made from the schemas, each run twice (idempotent); closed with the test."""
    db = sqlite3.connect(":memory:")
    case.addCleanup(db.close)
    db.row_factory = sqlite3.Row
    for schema in schemas:
        db.executescript(schema)
        db.executescript(schema)
    return db


def tables(db: sqlite3.Connection, prefix: str) -> set[str]:
    return {r["name"] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE ?",
                                          (prefix + "%",))}


class EveryStubImports(unittest.TestCase):
    def test_every_module_imports_and_holds_its_public_names(self):
        for package, names in MODULES.items():
            for name in names:
                module = importlib.import_module(name)
                self.assertRegex(module.__doc__ or "", rf"Owner: {package}\b", f"{name} names its owner")
                self.assertTrue(module.__all__, name)
                for public in module.__all__:
                    self.assertTrue(hasattr(module, public), f"{name}.{public}")

    def test_every_callable_of_the_contract_has_its_signature(self):
        # Nothing of the contract is missing or reshaped. A package may ADD names of its own (a helper, a constant); a
        # name another package calls keeps the shape written here.
        for path, expected in SIGNATURES.items():
            self.assertEqual(shape(resolve(path)), expected, path)
        modules = {name for names in MODULES.values() for name in names}
        self.assertEqual({".".join(path.split(".")[:3]) for path in SIGNATURES}, modules)
        for path in SIGNATURES:
            module, name = ".".join(path.split(".")[:3]), path.split(".")[3]
            self.assertIn(name, importlib.import_module(module).__all__, path)

    def test_every_job_module_has_run(self):
        for job in JOBS:
            module = importlib.import_module(f"league.ops.{job}")
            self.assertEqual(shape(module.run), "(ctx)", job)

    def test_the_exceptions_the_packages_share(self):
        from league.ops.forward_shadow import NightFailed
        from league.ops.forward_twins import TwinInterrupted

        self.assertTrue(issubclass(NightFailed, RuntimeError))
        self.assertTrue(issubclass(TwinInterrupted, RuntimeError))


class TheDDLCreates(unittest.TestCase):
    def test_the_forward_store(self):
        db = database(self, forward_db.SCHEMA)
        self.assertEqual(tables(db, "fwd_"), set(forward_db.TABLES))
        self.assertEqual(set(forward_db.WRITERS), set(forward_db.TABLES))
        for table in forward_db.TABLES:
            self.assertEqual(tuple(r["name"] for r in db.execute(f"PRAGMA table_info({table})")), COLUMNS[table], table)
            sql = db.execute("SELECT sql FROM sqlite_master WHERE name=?", (table,)).fetchone()["sql"]
            self.assertEqual("WITHOUT ROWID" in sql, table in WITHOUT_ROWID, table)
        self.assertEqual([r["name"] for r in db.execute("SELECT name FROM sqlite_master WHERE type='index' AND name "
                                                        "NOT LIKE 'sqlite_%'")], ["fwd_events_kind"])
        triggers = {r["name"] for r in db.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        self.assertEqual(triggers, {f"{t}_no_{verb}" for t in forward_db.APPEND_ONLY for verb in ("update", "delete")})
        self.assertEqual(set(forward_db.TABLES) - set(forward_db.APPEND_ONLY), {"fwd_kv"})

    def test_the_forward_store_is_append_only_but_for_its_kv(self):
        db = database(self, forward_db.SCHEMA)
        db.execute("INSERT INTO fwd_kv(key, value) VALUES('k', '1')")
        db.execute("UPDATE fwd_kv SET value='2' WHERE key='k'")
        db.execute("DELETE FROM fwd_kv WHERE key='k'")
        db.execute("INSERT INTO fwd_events(at, kind) VALUES(1.0, 'prereg')")
        db.execute("INSERT INTO fwd_days(pid, day, engine, r, w, b, entries, exits, status, at) "
                   "VALUES(1, '2026-10-12', 1, 0.0, 0.0, 0.0, 0, 0, 'ok', 1.0)")
        for table in ("fwd_events", "fwd_days"):
            for statement in (f"UPDATE {table} SET at=2.0", f"DELETE FROM {table}"):
                with self.assertRaises(sqlite3.DatabaseError) as raised:
                    db.execute(statement)
                self.assertIn(forward_db.APPEND_ONLY_ERROR, str(raised.exception))
        self.assertIsNone(db.execute("SELECT bars FROM fwd_days").fetchone()["bars"], "a control's row reads no bar")

    def test_a_twin_rows_cause_is_one_of_the_causes(self):
        db = database(self, forward_db.SCHEMA)
        row = "INSERT INTO fwd_twins(instance, day, pid, live_keys, shadow_keys, agree, at, live_bars, shadow_bars, " \
              "cause) VALUES(?, '2026-10-12', 1, '[]', '[]', ?, 1.0, ?, ?, ?)"
        db.execute(row, ("a@1:r", 1, "ab", "ab", None))
        for i, cause in enumerate(forward_db.CAUSES):
            db.execute(row, (f"b{i}@1:r", 0, None, "ab", cause))
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute(row, ("c@1:r", 0, "ab", "cd", "error"))
        self.assertEqual(forward_db.CAUSES, ("bars", "program", "unknown"))

    def test_the_memory_tables(self):
        db = database(self, elane_memory.SCHEMA)
        self.assertEqual(tables(db, "mem_"), set(elane_memory.TABLES))
        self.assertLess(set(elane_memory.SEALED_TABLES), set(elane_memory.TABLES))
        for table in elane_memory.TABLES:
            self.assertEqual(tuple(r["name"] for r in db.execute(f"PRAGMA table_info({table})")), COLUMNS[table], table)
        db.execute("INSERT INTO mem_series(sha, days, x, w) VALUES('s', x'00', x'00', x'00')")
        db.execute("INSERT INTO mem_seen(family, version, cell, gid, bar_passed, fails, seen_sha, at) "
                   "VALUES('fake-family', 1, 'equity / other / index', 'g0', 0, '[]', 's', '2026-10-12T00:00:00Z')")
        for table in ("mem_series", "mem_seen"):
            for statement in (f"UPDATE {table} SET rowid=rowid", f"DELETE FROM {table}"):
                with self.assertRaises(sqlite3.DatabaseError) as raised:
                    db.execute(statement)
                self.assertIn(elane_memory.APPEND_ONLY_ERROR, str(raised.exception))
        with self.assertRaises(sqlite3.IntegrityError):   # a contribution is "own" or "transfer", "ok" or "disqualified"
            db.execute("INSERT INTO mem_contrib(family, version, cell, kind, year, symset, k, status, n_days, n_lots, "
                       "exp_mean, series_sha, run_sha, at) VALUES('fake-family', 1, 'c', 'other', 2016, 'own', 1.0, "
                       "'ok', 1, 0, 0.0, 's', 'r', '2026-10-12T00:00:00Z')")

    def test_the_receipts_store(self):
        db = database(self, release_receipts.SCHEMA)
        self.assertEqual(tuple(r["name"] for r in db.execute("PRAGMA table_info(l3_receipts)")), COLUMNS["l3_receipts"])
        row = "INSERT INTO l3_receipts(id, kind, release, metric, direction, min_delta, window_hours, deployed_at, at) " \
              "VALUES('fake', ?, 'E3', 'forward_record.program_sessions', 'up', 1, 168, 1.0, 2.0)"
        db.execute(row, ("declared",))
        db.execute(row, ("read",))
        with self.assertRaises(sqlite3.IntegrityError):   # one declaration and one read an id
            db.execute(row, ("read",))
        with self.assertRaises(sqlite3.DatabaseError) as raised:
            db.execute("DELETE FROM l3_receipts")
        self.assertIn(release_receipts.APPEND_ONLY_ERROR, str(raised.exception))

    def test_the_stores_share_one_database_without_a_clash(self):
        # The memory tables live in the swarm store, the forward tables and the receipts in their own files: no name
        # of one is a name of another.
        names = [*forward_db.TABLES, *elane_memory.TABLES, "l3_receipts"]
        self.assertEqual(len(names), len(set(names)))
        database(self, forward_db.SCHEMA, elane_memory.SCHEMA, release_receipts.SCHEMA)


class TheSharedConstants(unittest.TestCase):
    def test_the_forward_screens_shape_is_pinned(self):
        self.assertEqual(forward_db.FGS_SHA, hashlib.sha256(results.canonical(forward_db.FGS).encode()).hexdigest())
        self.assertEqual(forward_db.FGS["version"], "fgs-prereg-1")
        self.assertEqual(tuple(forward_db.FGS["n"]), forward_db.CHECKPOINTS)
        self.assertEqual(forward_db.FGS["then_every"], forward_db.CHECKPOINT_EVERY)
        self.assertEqual(forward_db.FGS["alpha_e3_rows"], forward_db.E3_ALPHA_F)
        self.assertEqual((forward_db.E3_ROUTE, forward_db.E3_ALPHA_F), ("S2", "0.03"))
        self.assertEqual((forward_db.CONTROL_ROUTE, forward_db.CONTROL_ALPHA_F), ("none", "0"))
        self.assertEqual(forward_db.GENESIS, hashlib.sha256(b"ltcm-forward-registry-1").hexdigest())

    def test_the_pre_registered_numbers(self):
        f = forward_db
        self.assertEqual((f.CHECKPOINTS, f.CHECKPOINT_EVERY, f.FWD_SERIES, f.FILL_VERSION, f.TOL),
                         ((20, 60, 120, 250), 250, "fwd-1", "livelike-1", 1e-6))
        self.assertEqual((f.NEFF_WINDOW, f.NEFF_MIN_DAYS, f.NEFF_PROVISIONAL, f.Q), (60, 10, 20, 0.10))
        self.assertEqual((f.RC_READS, f.RC_MIN_GROUP, f.SUSPECT_NIGHTS, f.DQ_NIGHTS), ((60, 120, 250), 5, 3, 3))
        self.assertEqual((f.A14_GAP_BP, f.A14_AGREE), (15.0, 0.95))

    def test_the_hashed_columns_are_registry_columns(self):
        self.assertLess(set(forward_db.HASHED), set(COLUMNS["fwd_registry"]))
        self.assertEqual(set(COLUMNS["fwd_registry"]) - set(forward_db.HASHED), {"code", "prev_hash", "row_hash"})
        self.assertTrue({"route", "alpha_f"} <= set(forward_db.HASHED))

    def test_the_vocabularies(self):
        self.assertEqual(forward_db.MODES, ("off", "record"))
        self.assertEqual(forward_db.REASONS, ("train_pass", "train_fail", "seed", "live", "control"))
        self.assertTrue(set(forward_db.ONCE_KINDS) <= set(forward_db.EVENT_KINDS))
        self.assertEqual(set(forward_db.EVENT_KINDS.values()), {"A", "B", "C", "D"})
        self.assertEqual([k for k, owner in forward_db.EVENT_KINDS.items() if owner == "C"], ["meter_partial"])
        self.assertEqual(set(forward_db.WRITERS.values()), {"A", "B", "C", "D", "all"})
        self.assertTrue({"stopped", "resumed", "suspect", "live"} <= set(forward_db.TAGS))

    def test_the_settings_defaults_sit_inside_their_bounds(self):
        from league.ops import contam_probe

        for module in (forward_db, contam_probe):
            self.assertEqual(module.DEFAULTS["mode"], "off", "the code default of every E3 switch is off")
            for key, (low, high) in module.BOUNDS.items():
                self.assertTrue(low <= module.DEFAULTS[key] <= high, key)
        self.assertEqual(set(forward_db.DEFAULTS) - set(forward_db.BOUNDS), {"mode", "fill_minutes", "twins"})
        self.assertEqual(elane_folds.MODES, ("off", "record"))
        self.assertEqual(elane_folds.FALLBACK, {"hidden_year": None, "gid": elane_folds.GID0, "expected_oof": None})

    def test_the_work_years_are_the_train_years_and_never_the_reserve(self):
        from league.swarm import elane_train

        self.assertEqual(elane_folds.WORK_YEARS, elane_train.TRAIN_YEARS)
        self.assertEqual(elane_folds.RESERVE_YEARS, elane_train.RESERVE_YEARS)
        self.assertFalse(set(elane_folds.WORK_YEARS) & set(elane_folds.RESERVE_YEARS))

    def test_the_shared_dataclasses(self):
        self.assertEqual([f.name for f in dataclasses.fields(forward_db.Program)],
                         ["pid", "key", "family", "version", "lane", "reason", "ugroup", "lineage", "code", "params",
                          "needs", "program_sha", "run_sha", "created_at", "first_close", "first_day", "route",
                          "alpha_f"])
        self.assertEqual([f.name for f in dataclasses.fields(forward_db.ShadowRun)],
                         ["program", "result", "bars", "series"])
        program = forward_db.Program(1, "fake-family@1", "fake-family", 1, "equity", "train_fail", "index",
                                     "equity:fake-family", "NEEDS = {}", {}, {"symbols": ["SPY"], "history": 1}, "sha",
                                     "run", 0.0, dt.date(2026, 10, 9), dt.date(2026, 10, 12), "S2", "0.03")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            program.reason = "train_pass"  # type: ignore[misc]
        with self.assertRaises(dataclasses.FrozenInstanceError):
            forward_db.ShadowRun(program, {}, None, None).result = {}  # type: ignore[misc]


class TheBarsHashOfADecision(unittest.TestCase):
    """`forward_db.bars_hash`, the one function complete from step 0: the forward shadow and the twins must agree on it
    byte for byte. A synthetic store (league/equity/synth.py); no market data."""

    @classmethod
    def setUpClass(cls):
        from league.equity import ctx, synth
        from league.equity.program import Needs
        from league.equity.store import EquityStore

        cls.ctx = ctx
        cls.tmp = tempfile.TemporaryDirectory()
        root = synth.synthetic_store(cls.tmp.name + "/store", symbols=("SPY", "QQQ"), start=dt.date(2025, 1, 2),
                                     end=dt.date(2025, 3, 31))
        cls.needs = Needs(("SPY", "QQQ"), 5, 20)
        cls.bars = EquityStore(root).bars(cls.needs.symbols, "validation", history=cls.needs.history)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def inputs(self, t: int, bars=None, **book):
        book = {"cash": 1000.0, "equity": 1000.0, "budget": 1000.0, "caps": {}, "params": {}, **book}
        return self.ctx.inputs_from_bars(self.bars if bars is None else bars, t, needs=self.needs, **book)

    def test_it_is_short_hex_and_the_same_every_time(self):
        first = forward_db.bars_hash(self.inputs(20))
        self.assertRegex(first, r"^[0-9a-f]{%d}$" % forward_db.BARS_HEX)
        self.assertEqual(first, forward_db.bars_hash(self.inputs(20)))
        self.assertNotEqual(first, forward_db.bars_hash(self.inputs(21)), "another decision day reads other bars")

    def test_the_book_does_not_enter_it(self):
        lot = self.ctx.lot_row(lid=1, symbol="SPY", klass="etf", qty=1.0, entry=100.0, mark=101.0, held_sessions=2,
                               at="open")
        self.assertEqual(forward_db.bars_hash(self.inputs(20)),
                         forward_db.bars_hash(self.inputs(20, positions=[lot], cash=1.0, equity=102.0, budget=5.0,
                                                          caps={"SPY": 3.0}, params={"theta": 0.5},
                                                          rejects=["a refusal"])))

    def test_an_adjusted_price_a_cent_away_moves_it(self):
        # What the vendor's rounding does to a later store: one adjusted close of the look-back, a cent away.
        moved = {s: a.copy() for s, a in self.bars.adj.items()}
        moved["QQQ"][18, 3] += 0.01
        other = dataclasses.replace(self.bars, adj=moved)
        self.assertNotEqual(forward_db.bars_hash(self.inputs(20)), forward_db.bars_hash(self.inputs(20, bars=other)))
        # A session outside the decision's look-back (history 5: sessions 15..20) is not read.
        early = {s: a.copy() for s, a in self.bars.adj.items()}
        early["QQQ"][3, 3] += 0.01
        self.assertEqual(forward_db.bars_hash(self.inputs(20)),
                         forward_db.bars_hash(self.inputs(20, bars=dataclasses.replace(self.bars, adj=early))))


if __name__ == "__main__":
    unittest.main()
