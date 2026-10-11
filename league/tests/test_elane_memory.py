"""Release E3, THE EQUITY MEMORY's tables (league/swarm/elane_memory.py): the ingest of a scored version (the seen
facts; the hidden year's own runs into the sealed tables; once; nothing with the mode off, for a version the bar did
not judge, or without a hidden year; no stored run for the hidden run), what it does when the House fails a hidden
run, the counts ops reads, and seal T9, `AppendOnly`: UPDATE and DELETE abort on the three tables and the first write
of a key stands. The runner is an invented market's (league/tests/elane_e3_fakes.py); every family, program and number
here is invented."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import struct
import unittest
from unittest import mock

from league.equity import results
from league.ops import guard
from league.swarm import elane_effects, elane_folds, elane_memory, elane_train
from league.tests import elane_e2_fakes as fx
from league.tests import elane_e3_fakes as e3

K = (1.0, 1.5)


class Base(unittest.TestCase):
    def setUp(self):
        self.clock = fx.Clock()
        self.store = fx.new_store(self, self.clock)
        self.settings = e3.settings()
        self.code = fx.program()

    def scored(self, slug: str, hidden: int | None, market: e3.InventedMarket | None = None, **kw):
        """A family and its version as `EquityResearcher.score` leaves them before the ingest: the seen runs made (one
        a seen span and k), the bar's verdict on them, the record written."""
        market = market if market is not None else e3.InventedMarket()
        fam = e3.hidden_family(self.store, slug, hidden, code=self.code, **kw)
        seen = {k: [market.train(self.code, {}, name=slug, start=first, end=last, k=k)
                    for first, last in elane_folds.seen_spans(hidden)] for k in K}
        verdict = elane_train.train_score(elane_train.combine([r.result for r in seen[1.0]]),
                                          elane_train.combine([r.result for r in seen[1.5]]))
        self.store.set_state(fam["id"], **{elane_train.STATE_KEY: {
            "status": "researching", "versions": {"1": elane_train.compact(verdict, at=self.store.now())}}})
        market.calls.clear()
        return self.store.family(fam["id"]), seen, verdict, market

    def ingest(self, fam, seen, verdict, market, **kw):
        kw.setdefault("settings", self.settings)
        return elane_memory.ingest(self.store, fam, 1, runner=market, code=self.code, params={}, seen=seen,
                                   verdict=verdict, **kw)

    def rows(self, name: str) -> list[dict]:
        return e3.table(self.store, name)


class TheIngest(Base):
    def test_a_hidden_year_familys_version_leaves_its_seen_facts_and_its_out_of_fold_rows(self):
        fam, seen, verdict, market = self.scored("h-2018", 2018)
        self.assertEqual(sorted(verdict["years"]), ["2016", "2017", "2019", "2022", "2023", "2024"])
        out = self.ingest(fam, seen, verdict, market, now="2026-10-12T21:00:00Z")
        self.assertEqual(out, {"seen": 1, "contrib": 2, "hidden_year": 2018})
        self.assertEqual(market.calls, [(k, *elane_folds.hidden_span(2018)) for k in K],
                         "THE HIDDEN RUN: one more run at each k over the hidden span, and no other")
        (row,) = self.rows("mem_seen")
        cost = elane_effects.costs([r.result for r in seen[1.0]], [r.result for r in seen[1.5]])
        self.assertEqual(
            {k: row[k] for k in ("family", "version", "cell", "horizon", "hidden_year", "gid", "bar_passed", "fails", "at")},
            {"family": "h-2018", "version": 1, "cell": "beta / overnight / index", "horizon": "days_1_3",
             "hidden_year": 2018, "gid": "g0", "bar_passed": 1, "fails": "[]", "at": "2026-10-12T21:00:00Z"})
        self.assertEqual(row["drift_share"], verdict["beside"]["drift_share"])
        self.assertAlmostEqual(row["gross_bp"], cost["gross_bp"], places=9)
        self.assertAlmostEqual(row["cost_bp"], cost["cost_bp"], places=9)
        self.assertAlmostEqual(row["rt_per_year"], 1.0, places=12, msg="the invented market closes one lot a seen year")
        self.assertEqual(row["seen_sha"], elane_memory.seen_sha(verdict))
        contrib = self.rows("mem_contrib")
        self.assertEqual([(r["family"], r["version"], r["kind"], r["symset"], r["year"], r["k"], r["status"]) for r in contrib],
                         [("h-2018", 1, "own", "own", 2018, k, "ok") for k in K])
        for r, run in zip(contrib, market.runs[-2:]):
            want = elane_effects.contribution(run, k=r["k"])
            for key in ("n_days", "n_lots", "exp_mean", "e_ann", "se_ann", "t_x", "series_sha", "run_sha"):
                self.assertEqual(r[key], want[key], key)
            self.assertEqual((r["cell"], r["at"], r["n_days"], r["n_lots"]),
                             ("beta / overnight / index", "2026-10-12T21:00:00Z", 5, 1))
        series = {r["sha"]: r for r in self.rows("mem_series")}
        self.assertEqual(set(series), {r["series_sha"] for r in contrib})
        for sha, r in series.items():
            self.assertEqual(sha, hashlib.sha256(r["days"] + r["x"] + r["w"]).hexdigest())
            self.assertEqual({d // 365 + 1970 for d in struct.unpack("<5i", r["days"])}, {2018},
                             "its days are the hidden year's sessions (int32 little-endian ordinals)")
            self.assertEqual((len(r["x"]), len(r["w"])), (20, 20), "float32, four bytes a session")

    def test_it_writes_once(self):
        fam, seen, verdict, market = self.scored("once", 2023)
        self.assertEqual(self.ingest(fam, seen, verdict, market), {"seen": 1, "contrib": 2, "hidden_year": 2023})
        before = {name: self.rows(name) for name in elane_memory.TABLES}
        calls = list(market.calls)
        self.clock.advance(3600)
        other = {**verdict, "passed": False, "fails": ["STATE"], "pnl_10": -5.0}
        for v in (verdict, other):   # a second ingest, and one after a rescore gave other figures: nothing changes
            self.assertEqual(self.ingest(fam, seen, v, market), {"seen": 0, "contrib": 0, "hidden_year": 2023})
        self.assertEqual({name: self.rows(name) for name in elane_memory.TABLES}, before)
        self.assertEqual(market.calls, calls, "a hidden run already recorded is not run again")

    def test_nothing_with_the_mode_off(self):
        fam, seen, verdict, market = self.scored("off", 2018)
        for settings in (e3.settings("off"), {}, None, {"elane": {"memory": {"mode": "shadow"}}}):
            self.assertEqual(self.ingest(fam, seen, verdict, market, settings=settings),
                             {"seen": 0, "contrib": 0, "hidden_year": None})
        self.assertEqual(market.calls, [], "no hidden run")
        names = self.store._all("SELECT name FROM sqlite_master WHERE name LIKE 'mem%'")
        self.assertEqual(names, [], "not even the tables")

    def test_nothing_for_a_version_the_bar_did_not_judge(self):
        fam, seen, _, market = self.scored("unjudged", 2018)
        for verdict in (elane_train.program_fault("DQ", "its own errors"), elane_train.program_fault("LOAD", "refused"),
                        elane_train.program_fault("RUN", "the child failed"),
                        elane_train.train_score({"window": "validation"}, {}), {}, None):
            self.assertEqual(self.ingest(fam, seen, verdict, market), {"seen": 0, "contrib": 0, "hidden_year": None})
        self.assertEqual(market.calls, [])
        self.assertEqual(self.rows("mem_seen"), [])

    def test_a_version_that_failed_state_was_judged_on_the_bar(self):
        fam, seen, verdict, market = self.scored("state", 2018)
        failed = elane_train.with_state(verdict, {"sessions": 100, "matched": 40, "held": False})
        self.assertEqual((failed["fails"], failed["passed"]), (["STATE"], False))
        self.assertEqual(self.ingest(fam, seen, failed, market), {"seen": 1, "contrib": 2, "hidden_year": 2018})
        (row,) = self.rows("mem_seen")
        self.assertEqual((row["bar_passed"], json.loads(row["fails"])), (0, ["STATE"]))

    def test_no_contribution_without_a_hidden_year(self):
        fam, seen, verdict, market = self.scored("seven", None)
        self.assertEqual(sorted(verdict["years"]), [str(y) for y in elane_train.TRAIN_YEARS], "seven Train years")
        self.assertEqual(self.ingest(fam, seen, verdict, market), {"seen": 1, "contrib": 0, "hidden_year": None})
        self.assertEqual(market.calls, [], "no hidden run for a family with no hidden year")
        (row,) = self.rows("mem_seen")
        self.assertEqual((row["hidden_year"], row["rt_per_year"]), (None, 1.0))
        self.assertEqual((self.rows("mem_contrib"), self.rows("mem_series")), ([], []))

    def test_the_hidden_run_is_stored_nowhere_else(self):
        fam, seen, verdict, market = self.scored("sealed", 2022)
        self.store.event("swarm.elane", fam["id"], {"pass": "scored", "version": 1})
        elane_memory.ensure(self.store)
        before = e3.dump(self.store, less=elane_memory.TABLES)
        with mock.patch.object(type(self.store), "add_run", side_effect=AssertionError("stored")) as add_run:
            self.ingest(fam, seen, verdict, market)
        add_run.assert_not_called()
        self.assertEqual(self.store.runs(fam["id"]), [], "no `runs` row for the hidden run")
        self.assertEqual(e3.dump(self.store, less=elane_memory.TABLES), before,
                         "the record, the family's trial count, the events and the kv are as they were")
        self.assertEqual(list(self.store.runs_dir.iterdir()), [])
        self.assertNotIn("2022", json.dumps(self.store.family(fam["id"])["state"]))

    def test_a_disqualified_hidden_year_is_recorded_with_its_status(self):
        fam, seen, verdict, market = self.scored("dq", 2019)
        market.hidden_status = "disqualified"
        self.assertEqual(self.ingest(fam, seen, verdict, market), {"seen": 1, "contrib": 2, "hidden_year": 2019})
        self.assertEqual([r["status"] for r in self.rows("mem_contrib")], ["disqualified", "disqualified"])

    def test_a_hidden_run_the_house_failed_leaves_the_seen_facts_and_raises(self):
        fam, seen, verdict, market = self.scored("failed", 2018)
        market.fails = fx.RunFailed("the decider child failed the run")
        with self.assertRaises(fx.RunFailed):
            self.ingest(fam, seen, verdict, market)
        self.assertEqual(len(self.rows("mem_seen")), 1, "the seen facts stand")
        self.assertEqual((self.rows("mem_contrib"), self.rows("mem_series")), ([], []))
        for status in ("no_data", "error"):   # a run that ended on the House's side: nothing written, raised to the guard
            market.fails, market.hidden_status = None, status
            with self.assertRaises(ValueError):
                self.ingest(fam, seen, verdict, market)
            self.assertEqual(self.rows("mem_contrib"), [])
        # Nothing calls it again in E3; were it called once the House is sound, it fills what is missing and no more.
        market.hidden_status = "ok"
        self.assertEqual(self.ingest(fam, seen, verdict, market), {"seen": 0, "contrib": 2, "hidden_year": 2018})

    def test_a_hidden_run_that_answers_another_years_sessions_is_refused(self):
        fam, seen, verdict, market = self.scored("moved", 2018)
        real = market.train

        def wrong_year(code, params, *, name, start, end, k):
            return real(code, params, name=name, start=start.replace(year=2019), end=end.replace(year=2019), k=k)
        with mock.patch.object(market, "train", wrong_year), self.assertRaises(ValueError):
            self.ingest(fam, seen, verdict, market)
        self.assertEqual(self.rows("mem_contrib"), [])

    def test_the_seen_sha_is_of_the_train_figures_alone(self):
        fam, seen, verdict, market = self.scored("sha", 2018)
        kept = elane_train.compact(verdict, at="2026-10-12T21:00:00Z", ident={"equity": "a" * 64})
        figures = {k: v for k, v in kept.items() if k not in ("at", "identity")}
        self.assertEqual(elane_memory.seen_sha(verdict), results.sha(figures))
        self.assertEqual(sorted(figures), ["active_years", "beside", "fails", "objective", "passed", "pnl_10", "pnl_15",
                                           "ratio", "score", "summary", "years"])
        self.assertNotIn("2018", json.dumps(figures), "seen years only, by construction")
        self.assertNotEqual(elane_memory.seen_sha({**verdict, "pnl_10": verdict["pnl_10"] + 1.0}), results.sha(figures))
        with_state = elane_train.with_state(verdict, {"sessions": 10, "matched": 10, "held": True})
        self.assertNotEqual(elane_memory.seen_sha(with_state), elane_memory.seen_sha(verdict), "the restart check's counts")

    def test_a_malformed_spec_or_seen_map_still_records_what_it_can(self):
        fam, seen, verdict, market = self.scored("odd", 2018)
        fam = {**fam, "spec": {**fam["spec"], "gid": 7}}
        out = elane_memory.ingest(self.store, fam, 1, runner=market, code=self.code, params={}, seen=None, verdict=verdict,
                                  settings=self.settings)
        self.assertEqual(out, {"seen": 1, "contrib": 2, "hidden_year": 2018})
        (row,) = self.rows("mem_seen")
        self.assertEqual((row["gid"], row["horizon"], row["gross_bp"], row["cost_bp"], row["rt_per_year"]),
                         ("g0", None, None, None, None))


class TheTables(Base):
    def test_ensure_is_idempotent_and_creates_the_schema_whole(self):
        elane_memory.ensure(self.store)
        elane_memory.ensure(self.store)
        made = {r["name"] for r in self.store._all("SELECT name FROM sqlite_master WHERE name LIKE 'mem%'")}
        self.assertEqual(made, {*elane_memory.TABLES,
                                *(f"{t}_{name}" for t in elane_memory.TABLES
                                  for name in ("no_update", "no_delete", "first_write"))})
        self.assertEqual(elane_memory.SEALED_TABLES, ("mem_contrib", "mem_series"))
        self.assertEqual(set(elane_memory.KEYS), set(elane_memory.TABLES))
        for table, key in elane_memory.KEYS.items():   # each first-write key is the table's primary key
            pk = sorted((r["pk"], r["name"]) for r in self.store._all(f"PRAGMA table_info({table})") if r["pk"])
            self.assertEqual(tuple(name for _, name in pk), key, table)

    def test_ensure_never_commits_a_transaction_its_caller_holds(self):
        with self.assertRaises(RuntimeError):
            with self.store.atomic():
                self.store.put("held", 1)
                elane_memory.ensure(self.store)
                raise RuntimeError("the caller rolls back")
        self.assertIsNone(self.store.get("held"), "the caller's write was rolled back, not committed by the DDL")
        self.assertEqual(self.store._all("SELECT name FROM sqlite_master WHERE name LIKE 'mem%'"), [])
        elane_memory.ensure(self.store)
        self.assertEqual(self.rows("mem_seen"), [])

    def test_the_counts_ops_reads(self):
        self.assertEqual(guard.read(self.store.path, elane_memory.counts),
                         {"seen": 0, "contrib": 0, "families": 0, "by_year": {}}, "no table yet: zeros")
        for slug, hidden in (("a", 2018), ("b", 2018), ("c", 2023), ("d", None)):
            fam, seen, verdict, market = self.scored(slug, hidden, mechanism=f"Invented idea {slug} on the index, overnight.")
            self.ingest(fam, seen, verdict, market)
        got = guard.read(self.store.path, elane_memory.counts)
        self.assertEqual(got, {"seen": 4, "contrib": 6, "families": 3, "by_year": {"2018": 4, "2023": 2}})
        self.assertEqual(json.loads(json.dumps(got)), got, "counts only, JSON as it stands")


class AppendOnly(Base):
    """T9 on the swarm store's own connection, with real rows in the three tables."""

    def setUp(self):
        super().setUp()
        fam, seen, verdict, market = self.scored("kept", 2018)
        self.ingest(fam, seen, verdict, market)
        self.before = {name: self.rows(name) for name in elane_memory.TABLES}
        self.assertTrue(all(self.before.values()))

    def test_update_and_delete_abort_on_the_three_tables(self):
        for table in elane_memory.TABLES:
            column = {"mem_seen": "bar_passed", "mem_contrib": "e_ann", "mem_series": "x"}[table]
            for statement in (f"UPDATE {table} SET {column}=0", f"UPDATE {table} SET rowid=rowid", f"DELETE FROM {table}",
                              f"DELETE FROM {table} WHERE 1=0 OR rowid>=0"):
                with self.assertRaises(sqlite3.DatabaseError, msg=statement) as raised:
                    self.store._exec(statement)
                self.assertIn(elane_memory.APPEND_ONLY_ERROR, str(raised.exception))
        self.assertEqual({name: self.rows(name) for name in elane_memory.TABLES}, self.before)

    def test_the_first_write_of_a_key_stands_whatever_the_insert_says(self):
        """SQLite fires no DELETE trigger for the row an INSERT OR REPLACE displaces, so the two triggers alone would
        let a REPLACE overwrite a row: the first-write trigger drops any insert of a key already written."""
        seen = "(family, version, cell, gid, bar_passed, fails, seen_sha, at) VALUES('kept', 1, 'x', 'g9', 0, '[9]', 's', 't')"
        contrib = ("(family, version, cell, kind, year, symset, k, status, n_days, n_lots, exp_mean, series_sha, run_sha, at) "
                   "VALUES('kept', 1, 'x', 'own', 2018, 'own', 1.0, 'ok', 1, 0, 0.9, 's', 'r', 't')")
        sha = self.before["mem_series"][0]["sha"]
        for verb in ("INSERT OR REPLACE", "REPLACE", "INSERT OR IGNORE", "INSERT"):
            self.store._exec(f"{verb} INTO mem_seen{seen}")
            self.store._exec(f"{verb} INTO mem_contrib{contrib}")
            self.store._exec(f"{verb} INTO mem_series(sha, days, x, w) VALUES(?, x'00', x'00', x'00')", (sha,))
        self.store._exec(f"INSERT INTO mem_seen{seen} ON CONFLICT(family, version) DO UPDATE SET bar_passed=0")
        self.assertEqual({name: self.rows(name) for name in elane_memory.TABLES}, self.before)
        # A new key is still written (the tables append).
        self.store._exec("INSERT INTO mem_series(sha, days, x, w) VALUES('new', x'00', x'00', x'00')")
        self.assertEqual(len(self.rows("mem_series")), len(self.before["mem_series"]) + 1)

    def test_the_schema_holds_on_any_connection(self):
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.executescript(elane_memory.SCHEMA)
        db.executescript(elane_memory.SCHEMA)
        db.execute("INSERT INTO mem_series(sha, days, x, w) VALUES('a', x'01', x'01', x'01')")
        db.execute("INSERT OR REPLACE INTO mem_series(sha, days, x, w) VALUES('a', x'09', x'09', x'09')")
        self.assertEqual(db.execute("SELECT hex(days) FROM mem_series").fetchall(), [("01",)])
        for statement in ("UPDATE mem_series SET days=x'07'", "DELETE FROM mem_series"):
            with self.assertRaises(sqlite3.DatabaseError):
                db.execute(statement)


if __name__ == "__main__":
    unittest.main()
