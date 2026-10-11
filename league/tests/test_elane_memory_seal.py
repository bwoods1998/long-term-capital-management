"""Release E3, THE SEALS OF THE EQUITY MEMORY (league/swarm/elane_folds.py, elane_memory.py; league/swarm/elane_seal.py):

T2 `GeneratorsReadNothingNew`: two House states that differ only in what E3 records (the forward store, the fill
minutes, the forward report, the probe's file, the release receipts, the live book's lots and intents, E1's try and
look, the look rows and every memory row) give the architect's equity request, the researcher's brief and the route
choice byte for byte the same.

T3 `TheHiddenYearNeverReachesItsFamily`: on E1's own runner, two synthetic stores that differ only inside a family's
hidden year give the same record (its restart check's counts included), brief, Train map, seen facts, route choice and
stored runs; only the two sealed tables differ. Repeated on an invented runner for each of the seven years (each end
of a span and its middle).

T5 `TheReserveStaysSealed`: no E3 swarm module runs, slices or scores a 2020-21 session; two markets that differ only
in the reserve give byte-identical memory tables and views; E2's own seal tests pass unchanged with the memory
recording.

`TheWiring`: E3's patches to E2's files as the spec's section 11 writes them (the seen spans in `score`, the scored
event, the guarded ingest, the brief's note, the hidden year stamped at birth).

The tests of the wired flow need those patches (`WIRED`): on a builder's own branch, which edits no existing file,
they are skipped and say so; they run at integration. Every family, program, price and number here is invented."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from league.swarm import elane, elane_effects, elane_folds, elane_memory, elane_seal, elane_train, elane_yield
from league.swarm.architect import Architect
from league.swarm.elane_births import EquityPass, EquityQuota
from league.swarm.elane_train import STATE_KEY, EquityResearcher
from league.tests import elane_e2_fakes as fx
from league.tests import elane_e3_fakes as e3

K = (1.0, 1.5)
#: What only E3's stores hold in the two House states of T2 (none may reach a generator).
E3_WORDS = ("SENTINEL-E3", "0.7391", "-0.2684", "9417.53", "fwd-sentinel")


def reviewing_router() -> fx.FakeRouter:
    """A scripted router whose equity review and audit pass (two models), and whose every other answer is empty."""
    return fx.FakeRouter(lambda call: fx.review_answer("pass", model=call["sail_profile"]) if fx.is_review(call)
                         else fx.answer([]))


def views(store, clock, settings, router=None, runner=None) -> dict:
    """What the three equity generators read: the architect's request (system and user), each E2 family's brief, the
    route choice over six turns, and the Train map."""
    router = router or fx.FakeRouter()
    system, user = EquityPass(Architect(store, router, settings, clock=clock)).request(
        EquityQuota(store, settings, now=clock()))
    researcher = EquityResearcher(store, router, settings, runner=runner or fx.FakeRunner(), clock=clock)
    routes = elane_yield.routes(settings, router)
    fams = [f for f in elane_seal.equity_families(store) if elane_train.e2_family(f)]
    return {"system": system, "user": user, "briefs": {f["id"]: researcher.brief(f) for f in fams},
            "choice": [elane_yield.choose(store, settings, routes, turn=t, train_key=STATE_KEY)[0].key for t in range(6)],
            "map": elane_train.train_map_text(store, settings)}


class GeneratorsReadNothingNew(unittest.TestCase):
    """T2. The swarm's own state (families, programs, E2's Train records, the route ledger) is one; what differs is
    everything release E3 records and everything it reads that a generator may not."""

    def setUp(self):
        self.settings = e3.settings()

    def house(self, variant: str):
        clock = fx.Clock()
        store = fx.new_store(self, clock)
        root = Path(store.root)
        verdict = {"passed": True, "fails": [], "score": 1.93, "pnl_10": 180.0, "pnl_15": 120.0,
                   "years": {"2016": {"trades": 60, "days_traded": 30, "pnl": 20.0, "t": 0.6, "active": True}}}
        e3.hidden_family(store, "won", 2018, lane="equity", agenda="reversal", symbols=("QQQ",), code=fx.program("QQQ"))
        store.set_state("won", **{STATE_KEY: {"status": "passed", "passed_version": 1, "versions": {"1": verdict}}})
        e3.hidden_family(store, "busy", 2023, code=fx.program())
        store.set_state("busy", **{STATE_KEY: {"status": "researching", "versions": {
            "1": {"passed": False, "fails": ["P1"], "pnl_10": 30.0, "pnl_15": -2.0}}}})
        e3.hidden_family(store, "old", None, lane="equity", agenda="trend", symbols=("IWM",), code=fx.program("IWM"))
        seed = store.add_family({"id": "seed-overnight-spy", "mechanism": "The captain's seed: SPY overnight, every "
                                 "session.", "structure": "etf", "roots": ["SPY"], "lane": "beta"}, origin="seed")
        store.put(elane.SEEDS_KEY, {"seed-overnight-spy": seed["id"]})
        elane_yield.book(store, "sail:pro_asap", usd=0.4, known=True, purpose="births", answered=True, now=clock())
        elane_yield.book_births(store, "sail:pro_asap", 3)
        if variant == "bare":   # a House E3 never ran on: no file of it, no memory table
            return store, clock
        flip = variant == "b"
        figure = -0.2684 if flip else 0.7391
        word = "SENTINEL-E3-B" if flip else "SENTINEL-E3-A"
        # The forward store (league/ops/forward_db.py's schema; any rows).
        from league.ops import forward_db, release_receipts

        db = sqlite3.connect(root / "forward.sqlite")
        db.executescript(forward_db.SCHEMA)
        for pid, fid in enumerate(("won", "busy", "old"), 1):
            for i in range(5 if flip else 2):
                db.execute("INSERT INTO fwd_days(pid, day, engine, r, w, b, entries, exits, status, at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                           (pid, f"2026-10-{12 + i}", 1, figure * (i + 1), 0.5, figure / 2, i, i, "ok", 1.0))
            db.execute("INSERT INTO fwd_checks(pid, n, day, engine, t_r, sum_r, mean_w, p_x, at) VALUES(?,?,?,?,?,?,?,?,?)",
                       (pid, 20, "2026-11-06", 1, figure * 3, figure, 0.4, 0.01 if flip else 0.9, 2.0))
            db.execute("INSERT INTO fwd_tags(pid, tag, value, at) VALUES(?,?,?,?)",
                       (pid, "look_fail" if flip else "look_pass", "", 3.0))
            db.execute("INSERT INTO fwd_events(at, kind, pid, day, payload) VALUES(?,?,?,?,?)",
                       (4.0, "restated", pid, "2026-10-12", json.dumps({"why": word, "fid": fid})))
        db.commit()
        db.close()
        # The fill minutes, the forward report, the probe's file, the release receipts.
        minutes = root / "equity-fill-minutes" / "2026" / "2026-10-12.json"
        minutes.parent.mkdir(parents=True)
        minutes.write_text(json.dumps({"version": 1, "day": "2026-10-12", "bars": {"SPY": [[1, 9417.53, 2, 3, 4, 5, figure, 6]]}}))
        (root / "forward-report.json").write_text(json.dumps({"at": "2026-10-13T12:55:00Z", "mode": "record",
                                                              "meter": {"bh": 7 if flip else 0, "min_p": figure},
                                                              "alarms": [{"id": "FW3", "text": word}]}))
        (root / "contamination.json").write_text(json.dumps({"version": "contam-1", "routes": {"sail:pro_asap": {
            "at": "2026-10-10T00:10:00Z", "cells": {"S1": {"2025": {"acc": figure, "recalled": flip}}}}}, "history": []}))
        db = sqlite3.connect(root / "release-receipts.sqlite")
        db.executescript(release_receipts.SCHEMA)
        db.execute("INSERT INTO l3_receipts(id, kind, release, metric, direction, min_delta, window_hours, deployed_at, "
                   "value, verdict, at) VALUES('E3-oof', 'read', 'E3', 'forward_record.oof_rows', 'up', 1, 168, 1.0, ?, ?, 2.0)",
                   (figure, "wrong_way" if flip else "moved"))
        db.commit()
        db.close()
        # The live book: a closed lot's P&L and the recorded intents.
        from league.equity import live

        db = sqlite3.connect(root / "live.sqlite")
        db.executescript(live.SCHEMA)
        db.execute("INSERT INTO eq_lots(lid, instance, family, version, lane, symbol, class, qty, opened_qty, entry_px, "
                   "entry_notional, entry_at, opened_at, opened_day, status, exit_px, exit_at, exit_day, closed_at, cash) "
                   "VALUES(1, 'won@1:r', 'won', 1, 'equity', 'QQQ', 'etf', '1', '1', '400', '400', 'close', 1.0, "
                   "'2026-10-12', 'closed', ?, 'open', '2026-10-13', 2.0, ?)",
                   ("380.00" if flip else "9417.53", "-20.00" if flip else "9017.53"))
        for iid in range(1, (6 if flip else 3)):
            db.execute("INSERT INTO eq_intents(iid, instance, family, version, decided_day, exec_day, at, kind, symbol, "
                       "status, why, created_at, updated_at) VALUES(?, 'won@1:r', 'won', 1, '2026-10-12', '2026-10-13', "
                       "'open', ?, 'QQQ', 'done', ?, 1.0, 1.0)", (iid, "sell" if flip else "buy", word))
        db.commit()
        db.close()
        # E1's try and look, the look rows (what E2's own seal already holds; here beside E3's).
        for fid in ("won", seed["id"]):
            store.set_state(fid, elane_try={"version": 1, "entered": not flip, "precheck": {"passed": not flip, "t": figure}},
                            elane_look={"version": 1, "verdict": {"passed": not flip, "t": figure}, "beside": word})
            store.add_look(fid, 1, f"sha-{fid}", passed=not flip, p_value=abs(figure), detail={"why": word})
        # Every memory row.
        elane_memory.ensure(store)
        for fid, hidden in (("won", 2018), ("busy", 2023), ("old", None)):
            store._exec("INSERT INTO mem_seen(family, version, cell, horizon, hidden_year, gid, bar_passed, fails, "
                        "drift_share, gross_bp, cost_bp, rt_per_year, seen_sha, at) VALUES(?,1,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (fid, word, "days_11_plus" if flip else "days_1_3", hidden, "g0", int(flip), json.dumps([word]),
                         figure, figure * 10, figure * 3, 9417.53 if flip else 12.0, word, "2026-10-12T00:00:00Z"))
            if hidden is None:
                continue
            for k in K:
                sha = f"{word}-{fid}-{k}"
                store._exec("INSERT INTO mem_series(sha, days, x, w) VALUES(?,?,?,?)",
                            (sha, b"\x01\x02" * (3 if flip else 9), word.encode(), b"\x00" * 8))
                store._exec("INSERT INTO mem_contrib(family, version, cell, kind, year, symset, k, status, n_days, n_lots, "
                            "exp_mean, e_ann, se_ann, t_x, series_sha, run_sha, at) VALUES(?,1,?,'own',?,'own',?,?,?,?,?,?,?,?,?,?,?)",
                            (fid, word, hidden, k, "disqualified" if flip else "ok", 251, 9 if flip else 251, abs(figure),
                             figure, abs(figure) / 4, figure * 9, sha, word, "2026-10-12T00:00:00Z"))
        return store, clock

    def reads(self, variant: str) -> dict:
        store, clock = self.house(variant)
        return views(store, clock, self.settings)

    def test_the_architect_the_researcher_and_the_route_chooser_read_the_same_bytes(self):
        a, b, bare = self.reads("a"), self.reads("b"), self.reads("bare")
        for key in a:
            self.assertEqual(json.dumps(a[key], sort_keys=True), json.dumps(b[key], sort_keys=True),
                             f"{key} differs with what E3 recorded")
            self.assertEqual(json.dumps(a[key], sort_keys=True), json.dumps(bare[key], sort_keys=True),
                             f"{key} differs between a House E3 recorded on and one it never ran on")
        self.assertIn("won", a["user"])
        self.assertEqual(sorted(a["briefs"]), ["busy", "old", "won"], "really read")

    def test_no_word_of_what_e3_recorded_reaches_a_generator(self):
        for variant in ("a", "b"):
            text = json.dumps(self.reads(variant), sort_keys=True)
            for word in E3_WORDS:
                self.assertNotIn(word, text, f"{variant}: a generator read {word}")

    def test_the_two_states_really_differ_in_every_store(self):
        (a, _), (b, _) = self.house("a"), self.house("b")
        for name in elane_memory.TABLES:
            self.assertTrue(e3.table(a, name))
            self.assertNotEqual(e3.table(a, name), e3.table(b, name), name)
        for name in ("forward.sqlite", "release-receipts.sqlite", "live.sqlite", "forward-report.json",
                     "contamination.json", "equity-fill-minutes/2026/2026-10-12.json"):
            self.assertNotEqual(Path(a.root, name).read_bytes(), Path(b.root, name).read_bytes(), name)
        self.assertNotEqual(a.looks(), b.looks())

    def test_the_brief_says_a_year_is_held_out_and_names_none(self):
        briefs = self.reads("a")["briefs"]
        self.assertNotIn(elane_folds.BRIEF_NOTE, briefs["old"], "a family with no hidden year reads seven years")
        if e3.WIRED:
            for fid in ("won", "busy"):
                self.assertEqual(briefs[fid].count(elane_folds.BRIEF_NOTE), 1, fid)
        for fid, text in briefs.items():
            self.assertNotIn("hidden_year", text)
            self.assertNotIn("gid", text.split("YOUR NEWEST PROGRAM")[0])

    @unittest.skipUnless(e3.WIRED, e3.NOT_WIRED)
    def test_the_sealed_tables_are_named_by_the_seal(self):
        self.assertEqual(elane_seal.SEALED_TABLES, frozenset(elane_memory.SEALED_TABLES))
        self.assertIn("SEALED_TABLES", elane_seal.__all__)


@unittest.skipUnless(e3.WIRED, e3.NOT_WIRED)
class TheHiddenYearNeverReachesItsFamily(unittest.TestCase):
    """T3 on E1's own runner (`Isolated` on an `InlineDecider`), through E2's own `EquityResearcher.score`."""

    YEAR = 2018
    #: The keys of a stored result that name the store's files or the wall clock (they move with a refetch of any year
    #: and carry no figure).
    FILE_KEYS = ("run_id", "data_version", "result_sha", "seconds")

    @classmethod
    def setUpClass(cls):
        from league.equity import synth

        cls.tmp = tempfile.TemporaryDirectory()
        # An invented market that pays the overnight hold every year, so the fixture's program meets Y1-R1 and the bar
        # reaches its restart check; and the same market with other opens inside the hidden year (the year's last
        # `history` sessions and every close as they were).
        cls.plain = synth.synthetic_store(Path(cls.tmp.name) / "plain" / elane.STORE_DIR, symbols=("SPY",),
                                          end=dt.date(2024, 12, 31), seed=5, drift=0.8, vol=0.04)
        cls.moved = e3.moved_store(cls.plain, Path(cls.tmp.name) / "moved" / elane.STORE_DIR, year=cls.YEAR,
                                   keep_last=e3.CARRIES_HISTORY)
        cls.worlds = {}

    @classmethod
    def tearDownClass(cls):
        for world in cls.worlds.values():
            world["store"].close()
        cls.tmp.cleanup()

    def runner(self, root):
        from league.equity.runner import Isolated
        from league.live.decider import InlineDecider

        return Isolated(InlineDecider(), root)

    def world(self, name: str) -> dict:
        """One House on one market: the family born with the hidden year, its v1 scored by E2's researcher."""
        if name not in self.worlds:
            from league.swarm.store import SwarmStore

            clock = fx.Clock()
            store = SwarmStore(tempfile.mkdtemp(dir=self.tmp.name), clock=clock)
            router = reviewing_router()
            runner = self.runner(self.plain if name == "plain" else self.moved)
            fam = e3.hidden_family(store, "carries", self.YEAR, code=e3.CARRIES)
            settings = e3.settings()
            out = EquityResearcher(store, router, settings, runner=runner, clock=clock).score(fam, store.version("carries", 1))
            self.worlds[name] = {"store": store, "clock": clock, "settings": settings, "runner": runner, "out": out,
                                 "router": router}
        return self.worlds[name]

    def stored_runs(self, store) -> list:
        rows = store._all("SELECT * FROM runs WHERE family='carries' ORDER BY stress, rowid")
        out = []
        for row in rows:
            result = store.run_result(row["run_id"])
            self.assertIsNotNone(result, "the full result is kept")
            runtime = {k: v for k, v in (result.get("runtime") or {}).items() if k != "decide_seconds"}
            out.append({"row": {k: v for k, v in row.items() if k not in ("run_id", "path")},
                        "result": {**{k: v for k, v in result.items() if k not in self.FILE_KEYS}, "runtime": runtime}})
        return out

    def test_the_two_markets_really_differ_and_only_inside_the_hidden_year(self):
        from league.equity.store import EquityStore

        a = EquityStore(self.plain).bars(("SPY",), "train", history=0)
        b = EquityStore(self.moved).bars(("SPY",), "train", history=0)
        year = [i for i in range(a.n) if a.day(i).year == self.YEAR]
        changed = [i for i in range(a.n) if not (a.raw["SPY"][i] == b.raw["SPY"][i]).all()
                   or not (a.adj["SPY"][i] == b.adj["SPY"][i]).all()]
        self.assertEqual(changed, year[:-e3.CARRIES_HISTORY], "the year's sessions before its last `history`, no other")
        self.assertTrue((a.raw["SPY"][:, 3] == b.raw["SPY"][:, 3]).all() and (a.adj["SPY"][:, 3] == b.adj["SPY"][:, 3]).all(),
                        "the same closes everywhere")

    def test_a_whole_span_run_would_carry_the_hidden_year_into_the_seen_years(self):
        """What E3 does NOT do, and why: one run over the whole span on the two markets. The fixture's program sizes
        from the sleeve's cash and keeps a STATE flag a hidden-year bar sets, so the year AFTER the hidden one has
        other lots, P&L and exposure. (The years before it are the same.)"""
        first, last = elane_train.TRAIN_SPANS[0]
        whole = {name: self.runner(root).train(e3.CARRIES, {}, name="carries", start=first, end=last, k=1.0).result
                 for name, root in (("plain", self.plain), ("moved", self.moved))}
        rows = {name: result["by_year"] for name, result in whole.items()}
        for year in ("2016", "2017"):   # before the year: the program's own daily rows are the same ...
            for key in ("trades", "days_traded", "pnl", "t_daily", "exposure_mean"):
                self.assertEqual(rows["plain"][year][key], rows["moved"][year][key], (year, key))
            # ... and still the buy-and-hold beside moves: E1 holds it at the WHOLE run's mean exposure.
            self.assertNotEqual(rows["plain"][year]["bh_pnl"], rows["moved"][year]["bh_pnl"], year)
        # The lot bought at the last close before the year is sold inside it: its net sits in the year BEFORE.
        before = str(self.YEAR - 1)
        self.assertEqual(rows["plain"]["2016"]["trade_pnl"], rows["moved"]["2016"]["trade_pnl"])
        self.assertNotEqual(rows["plain"][before]["trade_pnl"], rows["moved"][before]["trade_pnl"])
        after = str(self.YEAR + 1)
        for key in ("pnl", "exposure_mean", "t_daily"):
            self.assertNotEqual(rows["plain"][after][key], rows["moved"][after][key], key)
        self.assertNotEqual(whole["plain"]["summary"]["max_drawdown"], whole["moved"]["summary"]["max_drawdown"])

    def test_the_program_trades_on_both_sides_of_the_year_and_meets_the_whole_bar(self):
        for name in ("plain", "moved"):
            w = self.world(name)
            rec = elane_train.record_of(w["store"].family("carries"))
            v1 = rec["versions"]["1"]
            self.assertEqual((v1["passed"], v1["fails"], rec["passed_version"]), (True, [], 1), w["out"])
            self.assertEqual(sorted(v1["years"]), [str(y) for y in elane_folds.WORK_YEARS if y != self.YEAR],
                             "six seen years, never the hidden one")
            for year in (str(self.YEAR - 1), str(self.YEAR + 1)):
                self.assertGreater(v1["years"][year]["trades"], 200, "it trades on both sides of the hidden year")
            self.assertEqual((v1["state"]["matched"], v1["state"]["first_miss"]), (v1["state"]["sessions"], None),
                             "the STATE flag is never set in a seen run, so the restart check holds")

    def test_everything_the_family_can_read_is_byte_for_byte_the_same(self):
        a, b = self.world("plain"), self.world("moved")
        kept = {}
        for name, w in (("plain", a), ("moved", b)):
            store = w["store"]
            kept[name] = {
                "record": store.family("carries")["state"][STATE_KEY],
                "state": store.family("carries")["state"],
                "views": views(store, w["clock"], w["settings"], router=reviewing_router(), runner=w["runner"]),
                "mem_seen": e3.table(store, "mem_seen"),
                "runs": self.stored_runs(store),
                "events": [(e["kind"], e["family"], e["payload"]) for e in store.events_after(0)],
                "notes": store.notebook("carries"),
                "family": {k: v for k, v in store.family("carries").items()},
                "out": w["out"],
            }
        for key in kept["plain"]:
            self.assertEqual(json.dumps(kept["plain"][key], sort_keys=True, default=str),
                             json.dumps(kept["moved"][key], sort_keys=True, default=str),
                             f"{key} differs with the hidden year's market")
        record = kept["plain"]["record"]
        self.assertIn("first_miss", record["versions"]["1"]["state"])
        self.assertEqual(len(kept["plain"]["runs"]), 2 * len(elane_folds.seen_spans(self.YEAR)), "one stored run a seen span and k")
        self.assertEqual(len(kept["plain"]["mem_seen"]), 1)
        self.assertIn(elane_folds.BRIEF_NOTE, kept["plain"]["views"]["briefs"]["carries"])
        scored = [p for kind, _, p in kept["plain"]["events"] if kind == "swarm.elane" and p.get("pass") == "scored"]
        self.assertEqual(len(scored), 1)

    def test_only_the_sealed_tables_differ(self):
        a, b = self.world("plain")["store"], self.world("moved")["store"]
        for name in elane_memory.SEALED_TABLES:
            rows_a, rows_b = e3.table(a, name), e3.table(b, name)
            self.assertEqual((len(rows_a), len(rows_b)), (2, 2), name)
            self.assertNotEqual(rows_a, rows_b, f"{name} holds the hidden year's own figures")
        for row_a, row_b in zip(e3.table(a, "mem_contrib"), e3.table(b, "mem_contrib")):
            self.assertEqual((row_a["year"], row_a["k"], row_a["status"], row_a["n_days"]),
                             (row_b["year"], row_b["k"], row_b["status"], row_b["n_days"]))
            self.assertNotEqual(row_a["series_sha"], row_b["series_sha"])
            self.assertNotAlmostEqual(row_a["e_ann"], row_b["e_ann"], places=3)
        less = (*elane_memory.SEALED_TABLES, "runs")
        dump_a, dump_b = e3.dump(a, less=less), e3.dump(b, less=less)
        self.assertEqual(json.dumps(dump_a, sort_keys=True, default=str), json.dumps(dump_b, sort_keys=True, default=str),
                         "every other table of the swarm store, row for row (the stored runs but for their file hashes)")

    def test_no_stored_run_and_no_record_holds_a_day_of_the_hidden_year(self):
        for name in ("plain", "moved"):
            store = self.world(name)["store"]
            text = json.dumps([self.stored_runs(store), store.family("carries")["state"],
                               [e["payload"] for e in store.events_after(0)]], default=str)
            self.assertNotIn(f"{self.YEAR}-", text, "no day of the hidden year")
            self.assertNotIn(f'"{self.YEAR}"', text, "no by-year key of the hidden year")


@unittest.skipUnless(e3.WIRED, e3.NOT_WIRED)
class TheHiddenYearOnAnInventedRunner(unittest.TestCase):
    """T3 repeated on an invented runner (as E2's reserve test) for a hidden year at each end of a span and in its
    middle: every one of the seven. Two invented markets differ in the hidden year's rows alone."""

    A = {"pnl": 8642.97, "trades": 7531, "days_traded": 6421, "t_daily": -3.217, "weight": 0.47}
    B = {"pnl": -9753.31, "trades": 3, "days_traded": 2, "t_daily": 4.139, "weight": 0.11}
    WORDS = ("8642.97", "7531", "6421", "-3.217", "9753.31", "4.139")

    def setUp(self):
        patcher = mock.patch.object(elane_train, "state_inputs", fx.state_inputs)   # the invented ctx stream (E2's fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.settings = e3.settings(train_budget=1)

    def world(self, year: int, figures: dict) -> dict:
        clock = fx.Clock()
        store = fx.new_store(self, clock)
        runner = e3.InventedMarket({year: figures}, hidden=year)
        router = reviewing_router()
        e3.hidden_family(store, "earns", year, code=fx.program())
        e3.hidden_family(store, "loses", year, lane="equity", agenda="reversal", code=fx.program() + "\n# fails at the stress\n",
                         mechanism="Invented reversal idea that loses at the stress on the index.")
        EquityResearcher(store, router, self.settings, runner=runner, clock=clock).run()
        seen = {fid: [{k: r.get(k) for k in ("version", "window", "stress", "status", "summary", "purpose")}
                      for r in store.runs(fid, window="train")] for fid in ("earns", "loses")}
        return {"store": store, "runner": runner,
                "reads": {"records": {fid: store.family(fid)["state"].get(STATE_KEY) for fid in ("earns", "loses")},
                          "runs": seen, "views": views(store, clock, self.settings, router=reviewing_router(), runner=runner),
                          "refuted": elane_train.refuted_rows(store), "ledger": elane_yield.ledger(store),
                          "graveyard": store._all("SELECT family, lesson FROM graveyard"),
                          "mem_seen": e3.table(store, "mem_seen"),
                          "events": [(e["kind"], e["family"], e["payload"]) for e in store.events_after(0)]}}

    def test_each_of_the_seven_years_at_a_spans_ends_and_in_its_middle(self):
        where = {2016: "the start of the first span", 2019: "its end", 2022: "the start of the second", 2024: "its end",
                 2017: "the middle", 2018: "the middle", 2023: "the middle"}
        self.assertEqual(sorted(where), sorted(elane_folds.WORK_YEARS))
        for year in elane_folds.WORK_YEARS:
            a, b = self.world(year, self.A), self.world(year, self.B)
            for key in a["reads"]:
                self.assertEqual(json.dumps(a["reads"][key], sort_keys=True, default=str),
                                 json.dumps(b["reads"][key], sort_keys=True, default=str),
                                 f"{year} ({where[year]}): {key} differs with the hidden year's figures")
            text = json.dumps(a["reads"], sort_keys=True, default=str) + json.dumps(b["reads"], sort_keys=True, default=str)
            for word in self.WORDS:
                self.assertNotIn(word, text, f"{year}: a figure of the hidden year reached something the family reads")
            spans = elane_folds.seen_spans(year)
            hidden = elane_folds.hidden_span(year)
            per_family = [(k, *span) for k in K for span in spans] + [(k, *hidden) for k in K]
            self.assertEqual(a["runner"].calls, per_family * 2, f"{year}: the seen spans at each k, then the hidden run")
            records = a["reads"]["records"]
            self.assertEqual((records["earns"]["status"], records["earns"]["passed_version"]), ("passed", 1), year)
            self.assertEqual(records["loses"]["versions"]["1"]["fails"], ["P1", "R1"])
            for fid in ("earns", "loses"):
                self.assertEqual(sorted(records[fid]["versions"]["1"]["years"]),
                                 [str(y) for y in elane_folds.WORK_YEARS if y != year])
                self.assertEqual(len(a["reads"]["runs"][fid]), 2 * len(spans), "the seen runs are stored, the hidden never")
            # Only the sealed tables hold the year's own figures.
            for name in elane_memory.SEALED_TABLES:
                rows_a, rows_b = e3.table(a["store"], name), e3.table(b["store"], name)
                self.assertTrue(rows_a and rows_b, f"{year}: {name}")
                self.assertNotEqual(rows_a, rows_b, f"{year}: {name}")
            contrib = e3.table(a["store"], "mem_contrib")
            self.assertEqual({(r["family"], r["year"], r["k"]) for r in contrib},
                             {(fid, year, k) for fid in ("earns", "loses") for k in K})
            # A series is stored once under its own sha (the two families' invented lots are the same at each k).
            self.assertEqual({r["sha"] for r in e3.table(a["store"], "mem_series")}, {r["series_sha"] for r in contrib})
            self.assertEqual(len({r["series_sha"] for r in contrib}), 2)

    def test_a_runner_that_leaks_a_hidden_row_into_a_seen_run_is_refused_whole(self):
        year = 2018
        clock = fx.Clock()
        store = fx.new_store(self, clock)
        runner = e3.InventedMarket({year: self.A}, hidden=year)
        real = runner.train

        def leaky(code, params, *, name, start, end, k):
            run = real(code, params, name=name, start=start, end=end, k=k)
            if end.year == year - 1:   # the stretch before the hidden year carries one of its rows
                run.result["by_year"][str(year)] = {k_: v for k_, v in runner.rows[year].items() if k_ != "weight"}
            return run
        runner.train = leaky
        e3.hidden_family(store, "earns", year, code=fx.program())
        EquityResearcher(store, reviewing_router(), self.settings, runner=runner, clock=clock).run()
        rec = elane_train.record_of(store.family("earns"))
        self.assertEqual((rec["versions"], rec["infra"]["kind"]), ({}, "window"), "judged on nothing")
        self.assertEqual(store.runs("earns", window="train"), [])
        self.assertEqual(e3.table(store, "mem_seen"), [], "nothing ingested: nothing was scored")
        self.assertNotIn((1.0, *elane_folds.hidden_span(year)), runner.calls, "and no hidden run")
        self.assertNotIn("8642.97", json.dumps(store.family("earns")["state"]))


class TheReserveStaysSealed(unittest.TestCase):
    """T5."""

    RESERVE = {"a": {"pnl": 8642.97, "trades": 7531, "days_traded": 6421, "t_daily": -3.217, "weight": 0.47},
               "b": {"pnl": -9753.31, "trades": 3, "days_traded": 2, "t_daily": 4.139, "weight": 0.11}}
    WORDS = ("8642.97", "7531", "6421", "-3.217", "9753.31", "4.139")

    def test_the_work_years_hold_neither_reserve_year_and_no_span_holds_a_reserve_session(self):
        from league.equity.store import nyse_sessions

        self.assertFalse(set(elane_folds.WORK_YEARS) & {2020, 2021})
        self.assertEqual(elane_folds.RESERVE_YEARS, (2020, 2021))
        for year in elane_folds.WORK_YEARS:
            for first, last in (*elane_folds.seen_spans(year), elane_folds.hidden_span(year)):
                self.assertFalse({d.year for d, _ in nyse_sessions(first, last)} & {2020, 2021}, (year, first, last))
        for first, last in elane_folds.seen_spans(None):
            self.assertFalse({d.year for d, _ in nyse_sessions(first, last)} & {2020, 2021})

    def test_no_e3_swarm_module_takes_a_reserve_year(self):
        for year in (2020, 2021):
            with self.assertRaises(ValueError):
                elane_folds.seen_spans(year)
            with self.assertRaises(ValueError):
                elane_folds.hidden_span(year)
            self.assertIsNone(elane_folds.hidden_year({"spec": {"hidden_year": year}}),
                              "a spec naming a reserve year is read as no hidden year: seven Train years, no hidden run")
            # A run of a reserve year (which nothing here asks for) is scored by nothing.
            market = e3.InventedMarket()
            run = market.train(fx.program(), {}, name="p", start=dt.date(year, 1, 1), end=dt.date(year, 12, 31), k=1.0)
            with self.assertRaises(ValueError):
                elane_effects.contribution(run, k=1.0)

    def test_the_ingest_of_a_family_whose_spec_names_a_reserve_year_runs_nothing(self):
        clock = fx.Clock()
        store = fx.new_store(self, clock)
        market = e3.InventedMarket()
        fam = e3.hidden_family(store, "odd", 2020, code=fx.program())
        seen = {k: [market.train(fx.program(), {}, name="odd", start=first, end=last, k=k)
                    for first, last in elane_folds.seen_spans(elane_folds.hidden_year(fam))] for k in K}
        verdict = elane_train.train_score(elane_train.combine([r.result for r in seen[1.0]]),
                                          elane_train.combine([r.result for r in seen[1.5]]))
        market.calls.clear()
        out = elane_memory.ingest(store, fam, 1, runner=market, code=fx.program(), params={}, seen=seen, verdict=verdict,
                                  settings=e3.settings())
        self.assertEqual((out, market.calls), ({"seen": 1, "contrib": 0, "hidden_year": None}, []))

    @unittest.skipUnless(e3.WIRED, e3.NOT_WIRED)
    def test_two_markets_that_differ_only_in_the_reserve_give_the_same_memory_and_the_same_views(self):
        patcher = mock.patch.object(elane_train, "state_inputs", fx.state_inputs)
        patcher.start()
        self.addCleanup(patcher.stop)
        settings = e3.settings(train_budget=1)
        kept = {}
        for name, reserve in self.RESERVE.items():
            clock = fx.Clock()
            store = fx.new_store(self, clock)
            runner = e3.InventedMarket({2020: reserve, 2021: reserve})
            e3.hidden_family(store, "first", 2019, code=fx.program())
            e3.hidden_family(store, "second", 2022, lane="equity", agenda="reversal", code=fx.program(),
                             mechanism="Invented reversal idea beside the reserve, on the index.")
            e3.hidden_family(store, "seven", None, lane="equity", agenda="trend", code=fx.program(),
                             mechanism="Invented trend idea with no hidden year, on the index.")
            EquityResearcher(store, reviewing_router(), settings, runner=runner, clock=clock).run()
            kept[name] = {"memory": {table: e3.table(store, table) for table in elane_memory.TABLES},
                          "views": views(store, clock, settings, router=reviewing_router(), runner=runner),
                          "records": {fid: store.family(fid)["state"].get(STATE_KEY) for fid in ("first", "second", "seven")},
                          "calls": runner.calls}
        a, b = kept["a"], kept["b"]
        self.assertEqual(a["memory"], b["memory"], "the three memory tables, row for row and byte for byte")
        for key in ("views", "records", "calls"):
            self.assertEqual(json.dumps(a[key], sort_keys=True, default=str), json.dumps(b[key], sort_keys=True, default=str), key)
        self.assertEqual((len(a["memory"]["mem_seen"]), len(a["memory"]["mem_contrib"])), (3, 4), "really recorded")
        self.assertEqual({(r["family"], r["year"]) for r in a["memory"]["mem_contrib"]}, {("first", 2019), ("second", 2022)})
        from league.equity.store import nyse_sessions

        train = {d for first, last in elane_train.TRAIN_SPANS for d, _ in nyse_sessions(first, last)}
        for _, start, end in a["calls"]:
            asked = {d for d, _ in nyse_sessions(start, end)}
            self.assertTrue(asked and asked <= train, "every session E3 asks the runner for is a Train-span session")
            self.assertFalse({d.year for d in asked} & {2020, 2021})
        text = json.dumps({k: v for k, v in a.items() if k != "memory"}, sort_keys=True, default=str) + repr(a["memory"])
        for word in self.WORDS:
            self.assertNotIn(word, text)
        self.assertNotRegex(json.dumps(a["views"]), r"\b202[01]\b")

    @unittest.skipUnless(e3.WIRED, e3.NOT_WIRED)
    def test_e2s_own_seal_tests_pass_unchanged_with_the_memory_recording(self):
        """E2's seal (league/tests/test_elane_e2_seal.py), its file as it is, with `elane.memory.mode` read as "record"
        throughout: the ingest runs beside every score and E2's seal holds as it did."""
        from league.tests import test_elane_e2_seal

        suite = unittest.defaultTestLoader.loadTestsFromModule(test_elane_e2_seal)
        self.assertGreater(suite.countTestCases(), 5)
        ingests = []
        real = elane_memory.ingest

        def recording(*args, **kwargs):
            out = real(*args, **kwargs)
            ingests.append(out)
            return out
        with mock.patch.object(elane_folds, "mode", lambda settings: "record"), \
                mock.patch.object(elane_memory, "ingest", recording):
            result = unittest.TestResult()
            suite.run(result)
        self.assertEqual((result.failures, result.errors), ([], []))
        self.assertEqual(result.testsRun, suite.countTestCases())
        self.assertTrue(ingests and all(o["hidden_year"] is None for o in ingests), "E2's families read seven years")
        self.assertTrue(any(o["seen"] == 1 for o in ingests), "and their seen facts were recorded beside")


@unittest.skipUnless(e3.WIRED, e3.NOT_WIRED)
class TheWiring(unittest.TestCase):
    """E3's patches to league/swarm/elane_train.py (11.7) and league/swarm/elane_births.py (11.8), on an invented
    runner."""

    def setUp(self):
        patcher = mock.patch.object(elane_train, "state_inputs", fx.state_inputs)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.clock = fx.Clock()
        self.store = fx.new_store(self, self.clock)
        self.settings = e3.settings()
        self.runner = e3.InventedMarket()

    def researcher(self, settings=None) -> EquityResearcher:
        return EquityResearcher(self.store, reviewing_router(), settings or self.settings, runner=self.runner,
                                clock=self.clock)

    def events(self, kind: str) -> list[dict]:
        return [e["payload"] for e in self.store.events_after(0) if e["kind"] == kind]

    def test_a_family_with_no_hidden_year_is_scored_exactly_as_before(self):
        fam = e3.hidden_family(self.store, "seven", None, code=fx.program())
        self.researcher().score(fam, self.store.version("seven", 1))
        self.assertEqual(self.runner.calls, [(k, *span) for k in K for span in elane_train.TRAIN_SPANS],
                         "the two Train spans at each k, and no hidden run")
        v1 = elane_train.record_of(self.store.family("seven"))["versions"]["1"]
        self.assertEqual(sorted(v1["years"]), [str(y) for y in elane_train.TRAIN_YEARS])
        self.assertEqual([(r["hidden_year"], r["bar_passed"]) for r in e3.table(self.store, "mem_seen")], [(None, 1)])
        self.assertEqual(e3.table(self.store, "mem_contrib"), [])
        self.assertNotIn(elane_folds.BRIEF_NOTE, self.researcher().brief(self.store.family("seven")))

    def test_the_scored_event_is_e2s_own_kind_once_a_scored_version(self):
        from league.swarm import hook

        fam = e3.hidden_family(self.store, "h", 2018, code=fx.program())
        self.researcher().score(fam, self.store.version("h", 1))
        scored = [p for p in self.events("swarm.elane") if p.get("pass") == "scored"]
        version = self.store.version("h", 1)
        self.assertEqual(scored, [{"pass": "scored", "version": 1, "sha": version["sha"], "bar_passed": True, "fails": [],
                                   "objective": elane_train.OBJECTIVE, "judged": True}])
        self.assertIn("swarm.elane", hook.SKIPPED_KINDS, "no new kind for the House mirror to drop")
        # A program judged on nothing is scored too (the registry leaves it out by `judged`).
        self.runner.hidden_status = "ok"
        dq = e3.hidden_family(self.store, "dq", 2018, lane="equity", agenda="reversal", code=fx.program("QQQ"),
                              symbols=("QQQ",), mechanism="Invented reversal idea whose program is disqualified.")
        real = self.runner.train

        def disqualified(code, params, **kw):
            run = real(code, params, **kw)
            run.result.update(status="disqualified", reason="25 errors")
            return run
        with mock.patch.object(self.runner, "train", disqualified):
            self.researcher().score(dq, self.store.version("dq", 1))
        last = [p for p in self.events("swarm.elane") if p.get("pass") == "scored"][-1]
        self.assertEqual((last["bar_passed"], last["fails"], last["judged"]), (False, ["DQ"], False))
        self.assertEqual([r["family"] for r in e3.table(self.store, "mem_seen")], ["h"], "no figure, no memory row")

    def test_a_rescore_writes_no_second_event_and_runs_no_hidden_run(self):
        from league.swarm import evaluator

        ident = {"now": {"equity": "a" * 64, "engine": "equity-engine-1"}}
        with mock.patch.object(evaluator, "equity_identity", lambda: dict(ident["now"])):
            fam = e3.hidden_family(self.store, "h", 2023, code=fx.program())
            researcher = self.researcher()
            researcher.score(fam, self.store.version("h", 1))
            before = {name: e3.table(self.store, name) for name in elane_memory.TABLES}
            ident["now"] = {"equity": "b" * 64, "engine": "equity-engine-1"}
            self.runner.calls.clear()
            out = researcher.step(self.store.family("h"))
        self.assertEqual(out.get("rescored"), "kept", out)
        self.assertEqual(self.runner.calls, [(k, *span) for k in K for span in elane_folds.seen_spans(2023)],
                         "a stale pass is judged again on its SEEN spans, and its hidden year is not run again")
        self.assertEqual(len([p for p in self.events("swarm.elane") if p.get("pass") == "scored"]), 1)
        self.assertEqual({name: e3.table(self.store, name) for name in elane_memory.TABLES}, before)

    def test_a_hidden_year_is_honoured_with_the_mode_off_and_nothing_is_ingested(self):
        fam = e3.hidden_family(self.store, "h", 2016, code=fx.program())
        self.researcher(e3.settings("off")).score(fam, self.store.version("h", 1))
        self.assertEqual(self.runner.calls, [(k, *span) for k in K for span in elane_folds.seen_spans(2016)],
                         "its bar does not move under it; no hidden run")
        v1 = elane_train.record_of(self.store.family("h"))["versions"]["1"]
        self.assertEqual(sorted(v1["years"]), ["2017", "2018", "2019", "2022", "2023", "2024"])
        self.assertEqual(self.store._all("SELECT name FROM sqlite_master WHERE name LIKE 'mem%'"), [])
        self.assertIn(elane_folds.BRIEF_NOTE, self.researcher(e3.settings("off")).brief(self.store.family("h")))

    def test_seen_spans_that_cannot_be_read_score_nothing_and_say_so(self):
        fam = e3.hidden_family(self.store, "h", 2018, code=fx.program())
        with mock.patch.object(elane_folds, "seen_spans", side_effect=RuntimeError("an invented defect")):
            out = self.researcher().score(fam, self.store.version("h", 1))
        self.assertEqual((out["house"], self.runner.calls), ("store", []), "the House's: no run, nothing scored")
        rec = elane_train.record_of(self.store.family("h"))
        self.assertEqual((rec["versions"], rec["infra"]["kind"]), ({}, "store"))
        alerts = [p for p in self.events("swarm.status") if p.get("alert")]
        self.assertEqual([(p["action"], p["version"]) for p in alerts], [("elane_memory", 1)])
        self.assertIn("RuntimeError", alerts[0]["text"])
        self.assertGreater(rec["infra"]["next_at"], self.clock(), "E2's backoff moves the family out of the queue's head")
        # The defect fixed, the same version is scored.
        self.clock.advance(elane_train.BACKOFF_MAX + 1)
        self.researcher().run()
        self.assertIn("1", elane_train.record_of(self.store.family("h"))["versions"])

    def test_an_ingest_that_fails_leaves_the_verdict_standing_and_says_so(self):
        fam = e3.hidden_family(self.store, "h", 2018, code=fx.program())
        self.runner.hidden, self.runner.fails = 2018, fx.RunFailed("the decider child failed the hidden run")
        out = self.researcher().score(fam, self.store.version("h", 1))
        rec = elane_train.record_of(self.store.family("h"))
        self.assertEqual((out["passed"], rec["passed_version"], rec["versions"]["1"]["passed"]), (True, 1, True))
        alerts = [p for p in self.events("swarm.status") if p.get("alert")]
        self.assertEqual([(p["action"], p["version"]) for p in alerts], [("elane_memory", 1)])
        self.assertIn("the memory ingest failed (RunFailed)", alerts[0]["text"])
        self.assertEqual(len(e3.table(self.store, "mem_seen")), 1, "the seen facts stand")
        self.assertEqual(e3.table(self.store, "mem_contrib"), [])
        self.assertEqual(len(self.store.runs("h", window="train")), 2 * len(elane_folds.seen_spans(2018)))

    def births(self, settings, n: int = 3, forecast: float | None = None) -> list[dict]:
        rows = [fx.proposal(f"born-{i}", lane="beta", agenda="overnight", symbols=("SPY",), code=fx.program(),
                            mechanism=f"Invented overnight idea number {i}: index holders are paid for risk they cannot trade.",
                            **({"expected_oof": forecast} if i == 0 and forecast is not None else {})) for i in range(n)]
        answers = [fx.answer(rows)]
        router = fx.FakeRouter(lambda call: answers.pop(0) if answers else fx.answer([]))
        for i in range(60):
            self.store.event("swarm.born", f"opt-{i}", {"structure": "debit_vertical", "roots": ["SPY"]})
        out = Architect(self.store, router, settings, clock=self.clock).equity_pass()
        return [self.store.family(fid) for fid in out["born"]]

    def test_a_birth_is_stamped_with_its_hidden_year_its_genome_and_the_reserved_forecast(self):
        with mock.patch("league.swarm.architect.same_idea", lambda a, b: False):
            fams = self.births(self.settings, forecast=0.2)
        self.assertEqual(len(fams), 3, self.store.get("elane_e2_last"))
        cell = ("beta", "overnight", "index")
        start = elane_folds.WORK_YEARS.index(elane_folds.WORK_YEARS[elane_folds.cell_hash(cell) % 7])
        self.assertEqual([f["spec"]["hidden_year"] for f in fams],
                         [elane_folds.WORK_YEARS[(start + i) % 7] for i in range(3)], "the cell's rotation, birth by birth")
        self.assertEqual([(f["spec"]["gid"], f["spec"]["expected_oof"]) for f in fams], [("g0", 0.2), ("g0", None), ("g0", None)])
        for fam in fams:
            self.assertEqual(elane_folds.hidden_year(fam), fam["spec"]["hidden_year"])
            facts = elane_seal.train_facts(fam, STATE_KEY)
            self.assertFalse({"hidden_year", "gid", "expected_oof"} & set(facts), "no generator reads the spec's new keys")

    def test_a_birth_with_the_mode_off_or_a_stamp_that_fails_reads_seven_years(self):
        with mock.patch("league.swarm.architect.same_idea", lambda a, b: False):
            (off,) = self.births(e3.settings("off"), n=1)
        self.assertEqual({k: off["spec"][k] for k in elane_folds.FALLBACK}, elane_folds.FALLBACK)
        self.assertEqual([p for p in self.events("swarm.status") if p.get("alert")], [])
        store2 = fx.new_store(self, self.clock)
        self.store = store2
        with mock.patch("league.swarm.architect.same_idea", lambda a, b: False), \
                mock.patch.object(elane_folds, "birth_fields", side_effect=RuntimeError("an invented defect")):
            (fam,) = self.births(self.settings, n=1)
        self.assertEqual({k: fam["spec"][k] for k in elane_folds.FALLBACK}, elane_folds.FALLBACK, "the birth goes on")
        alerts = [p for p in self.events("swarm.status") if p.get("alert")]
        self.assertEqual([p["action"] for p in alerts], ["elane_memory"])
        self.assertIn("a birth got no hidden year (RuntimeError)", alerts[0]["text"])
        self.assertEqual(elane_folds.seen_spans(elane_folds.hidden_year(fam)), elane_train.TRAIN_SPANS)


class TheSwitchAndTheWiringLandTogether(unittest.TestCase):
    def test_a_policy_that_records_the_memory_ships_with_the_wired_flow(self):
        """policy.json's `elane.memory.mode` "record" (release E3's patch 11.2) on a tree without the patches to E2's
        files would record nothing and skip this file's wired tests in silence: the two land together or this fails."""
        from league.swarm import settings as settings_mod

        layer, status = settings_mod.read_policy()
        self.assertEqual(status["state"], "ok", status)
        if elane_folds.mode(layer) == "record":
            self.assertTrue(e3.WIRED, e3.NOT_WIRED)
            self.assertEqual(elane_seal.SEALED_TABLES, frozenset(elane_memory.SEALED_TABLES))
        else:
            self.assertEqual(elane_folds.mode(layer), "off")


if __name__ == "__main__":
    unittest.main()
