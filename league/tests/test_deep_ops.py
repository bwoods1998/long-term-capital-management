"""THE DEEP KEY'S HOUSE JOBS (release R1; league/ops/deep_report.py, registry.py): report-only S3 looks in idle hours
with the verdicts sealed in the ledger and counts to the captain (births see nothing: the job's receipt names no
pass); D2 judged: both keys in every look, and with the reserve sealed no look at all; one version's error of the
House's never stops the next and spends no look; the wall's room; a damaged ledger fails closed; the current versions
as the item-8 census reads them, with their seat and source; the registry rows; the contamination probe's deep eras
(a sealed era's cell keeps no DVAL figure beyond the reading's) and the strong-recall reading.

Synthetic stores and invented versions only (league/tests/deep_fakes.py)."""

from __future__ import annotations

import datetime as dt
import json
import os
import unittest
from pathlib import Path
from unittest import mock

from league.deep import config, gate
from league.equity.runner import RunFailed, RunLost
from league.ops import contam_probe, deep_report, registry
from league.ops.context import Context
from league.tests import deep_fakes as F

NIGHT = dt.datetime(2026, 10, 26, 7, 10, tzinfo=dt.timezone.utc).timestamp()     # a Monday, 03:10 in New York
SESSION = dt.datetime(2026, 10, 26, 15, 0, tzinfo=dt.timezone.utc).timestamp()   # 11:00 in New York


def contamination(route: str, *, m: float, p: float, readable: bool = True) -> dict:
    cell = {"n": 40, "correct": 30, "ties": 0, "skipped": 0, "periods": 12, "symbols": 4, "acc": 0.75, "base": 0.6,
            "m": m, "lo": 0.6, "hi": 0.85, "p_perm": p, "readable": readable, "recalled": p <= 0.05}
    return {"version": "contam-1", "history": [],
            "routes": {route: {"at": "2026-10-24T00:10:00Z", "cells": {"S1": {"2001-08": cell, "2025": dict(cell)}}}}}


class StrongRecall(unittest.TestCase):
    def test_the_reading(self):
        self.assertTrue(deep_report.strong_recall(contamination("r", m=0.2, p=0.005), "r"))
        self.assertFalse(deep_report.strong_recall(contamination("r", m=0.2, p=0.02), "r"))
        self.assertFalse(deep_report.strong_recall(contamination("r", m=0.1, p=0.001), "r"))
        self.assertFalse(deep_report.strong_recall(contamination("r", m=0.3, p=0.001, readable=False), "r"))
        self.assertIsNone(deep_report.strong_recall(contamination("r", m=0.3, p=0.001), "other"))
        self.assertIsNone(deep_report.strong_recall(contamination("r", m=0.3, p=0.001), None))
        doc = contamination("r", m=0.3, p=0.001)
        del doc["routes"]["r"]["cells"]["S1"]["2001-08"]
        self.assertIsNone(deep_report.strong_recall(doc, "r"), "a 2025 cell is not the deep era's")
        self.assertEqual(deep_report.PROBE_FILE, contam_probe.FILE)


class TheProbesDeepEras(unittest.TestCase):
    UNIVERSE = {"SPY": "etf", "QQQ": "etf", "XLK": "etf", "XLRE": "etf", "AAPL": "stock"}

    def test_the_deep_cells_are_s1_s2_s4_on_the_deep_calendar_and_funds(self):
        asked = contam_probe.deep_questions(self.UNIVERSE, per_cell=24)
        cells = {(q["stratum"], q["era"]) for q in asked}
        self.assertEqual(cells, {(s, e) for s in ("S1", "S2", "S4") for e in contam_probe.DEEP_ERAS})
        self.assertFalse({q["symbol"] for q in asked} & {"AAPL", "XLRE"})
        months = contam_probe.periods("S1", "2001-08")
        self.assertEqual(months[0][0], "2001-04")
        self.assertEqual(months[0][1], "2001-03-30", "the last session before April 2001")
        self.assertEqual(months[-1][0], "2008-12")
        sept = next(m for m in months if m[0] == "2001-09")
        self.assertEqual(sept[2], "2001-09-28")
        weeks = contam_probe.periods("S4", "2001-08")
        self.assertNotIn("2001-09-14", [w[0] for w in weeks], "the closed week of 2001-09-11 ends on no session")
        self.assertEqual(contam_probe.periods("S1", "2010-15")[0], ("2010-01", "2009-12-31", "2010-01-29"))

    def test_without_a_deep_store_e3s_questions_are_unchanged(self):
        asked = contam_probe.questions(self.UNIVERSE, per_cell=24)
        self.assertFalse({q["era"] for q in asked} & set(contam_probe.DEEP_ERAS))
        self.assertEqual(list(contam_probe.ERAS), ["2016-24", "2025", "2026H1"])
        self.assertEqual(contam_probe.periods("S1", "2016-24")[0][0], "2016-02", "E3's calendar still starts in 2016")

    def test_the_deep_truth_reads_the_deep_store(self):
        root = F.tmpdir(self)
        deep = F.deep_store(root / "equity-deep", ("SPY", "QQQ"))
        from league.deep import blocks

        cap = gate.mint_deep_gate_capability(deep, contam_probe.DEEP_GATE_REASON)
        truth = contam_probe._DeepTruth(blocks.DeepStore(deep, gate=cap))
        q = next(q for q in contam_probe.deep_questions({"SPY": "etf", "QQQ": "etf"}, per_cell=24)
                 if q["era"] == "2001-08" and q["stratum"] == "S2")
        self.assertIn(contam_probe.truth(truth, q), ("more", "less", "tie"))
        from league.equity.store import MissingData

        with self.assertRaises(MissingData):  # a store opened without the gate: the run ends as for a store rewritten
            contam_probe._DeepTruth(blocks.DeepStore(deep)).deep_close("SPY", "2005-01-03")


class CurrentVersions(unittest.TestCase):
    """The population as the item-8 census reads it (history-1017/census/eligibility_census.py `current_versions`)."""

    def test_seated_families_their_banded_version_gym_families_next_validation_and_latest(self):
        self.assertEqual(deep_report.version_numbers({"band": "probe", "state": {"banded_version": 3}}, 9), [3])
        self.assertEqual(deep_report.version_numbers({"band": "probe", "state": {}}, 9), [])
        gym = {"band": "gym", "best_version": 4, "state": {"elane_e2": {"passed_version": 6}}}
        self.assertEqual(deep_report.version_numbers(gym, 9), [6, 9])
        self.assertEqual(deep_report.version_numbers({"band": "gym", "best_version": 4, "state": {}}, 4), [4])
        self.assertEqual(deep_report.version_numbers({"band": "gym", "state": {"best_train_version": 2}}, 5), [2, 5])

    def test_the_store_reading(self):
        class Store:
            def families(self, *, alive=None, lanes=None):
                return [{"id": "a", "band": "gym", "best_version": 1, "structure": "etf",
                         "spec": {"lane": "equity", "agenda": "trend", "route": "sail:r"}, "state": {}},
                        {"id": "p", "band": "gym", "structure": "panel", "spec": {"lane": "equity"}, "state": {}}]

            def latest_version(self, fid):
                return {"n": 2}

            def version(self, fid, n):
                return {"n": n, "code": F.blind_program(("SPY", "XLK")), "params": {}}

        rows = deep_report.current_versions(Store())
        self.assertEqual([(r["fid"], r["n"]) for r in rows], [("a", 1), ("a", 2)], "no panel family")
        self.assertEqual(rows[0]["route"], "sail:r")
        self.assertEqual(rows[0]["cell"], "equity/trend/index+sectors")
        self.assertEqual((rows[0]["seated"], rows[0]["source"]), (False, "born"))

    def test_the_seat_and_the_source(self):
        self.assertEqual(deep_report.source_of({"origin": "seed", "spec": {}}), "seed")
        self.assertEqual(deep_report.source_of({"origin": "born", "spec": {"seeded": True}}), "seed")
        self.assertEqual(deep_report.source_of({"origin": "fork", "lineage": "seed-reversal-index", "spec": {}}), "seed",
                         "a family of a seed's lineage carries its mechanism")
        self.assertEqual(deep_report.source_of({"origin": "born", "lineage": "f12", "spec": {}}), "born")

    def test_a_family_with_no_route(self):
        row = {"fid": "s", "n": 1, "code": "x", "params": {}, "cell": "c", "route": None}
        seed = deep_report._version({**row, "source": "seed"}, {"routes": {}})
        self.assertEqual((seed.strong_recall, seed.route_known, seed.source), (False, True, "seed"),
                         "a captain's seed has no generator's recall to read: measured, not waiting forever")
        born = deep_report._version({**row, "source": "born"}, {"routes": {}})
        self.assertEqual((born.strong_recall, born.route_known), (None, False), "the gate refuses it")


class Report(unittest.TestCase):
    def setUp(self):
        self.root = F.tmpdir(self)
        (self.root / "swarm.json").write_text(json.dumps({"elane": {"deep": {"mode": "report", "looks_per_run": 3}}}))
        (self.root / "swarm.sqlite").write_bytes(b"")
        F.deep_store(self.root / config.STORE_DIR, ("SPY", "QQQ", "IWM"))
        F.equity_store(self.root / "equity-daily", ("SPY", "QQQ", "IWM"))
        (self.root / contam_probe.FILE).write_text(json.dumps(contamination("r", m=0.0, p=0.5)))
        self.rows = [{"fid": f"f{i}", "n": 1, "code": F.blind_program(("SPY", "QQQ", "IWM")[: 2 + i % 2], look=24 + i),
                      "params": {}, "cell": f"equity/momentum/c{i}", "route": "r"} for i in range(4)]
        self.ctx_last = None

    def ctx(self, when=NIGHT):
        return Context("deep_report", root=self.root, due_at=when, clock=lambda: when, config={}, settings_value={})

    def run_job(self, when=NIGHT, rows=None, runs=None, clock=None):
        self.ctx_last = self.ctx(when)
        kw = {"clock": clock} if clock is not None else {}
        with mock.patch("league.ops.deep_report.current_versions", return_value=rows or self.rows), \
                mock.patch("league.ops.equity_deep.complete", return_value=True):
            return deep_report.report_run(self.ctx_last, runs=runs or F.InlineRuns(self.root / "equity-daily"),
                                          worlds=1500, **kw)

    def ledger(self):
        return gate.Ledger(self.root / config.STORE_DIR)

    def test_report_mode_looks_on_both_keys_seals_the_verdicts_and_reports_counts(self):
        out = self.run_job()
        self.assertEqual(out["looked"], 3, "looks_per_run")
        self.assertEqual(out["statuses"], {"looked": 3})
        self.assertNotIn("passed", json.dumps(out), "the receipt names no pass")
        ledger = self.ledger()
        self.assertEqual(len(ledger.real()), 3)
        for row in ledger.real():
            self.assertTrue(all(isinstance(row["verdict"][k], bool) for k in ("passed", "deep", "recent")),
                            "D2 judged: every look read both keys")
        report = json.loads((self.root / config.STORE_DIR / config.REPORT).read_text())
        self.assertEqual((report["looked"], report["mode"], report["screen"], report["ledger"]), (3, "report", "S3", "ok"))
        self.assertNotIn("recent_pending", report)
        again = self.run_job()
        self.assertEqual(again["looked"], 1, "the fourth version; no version is looked at twice")
        self.assertEqual(len(self.ledger().real()), 4)

    def test_with_the_reserve_sealed_no_look_is_made(self):
        self.assertEqual(config.cfg({"elane": {"deep": {}}})["reserve"], "judged", "D2 is decided: judged")
        policy = json.loads((Path(deep_report.__file__).resolve().parents[1] / "swarm" / "policy.json").read_text())
        self.assertEqual(policy["elane"]["deep"]["reserve"], "judged")
        (self.root / "swarm.json").write_text(json.dumps({"elane": {"deep": {"mode": "report", "reserve": "sealed"}}}))
        runs = F.InlineRuns(self.root / "equity-daily")
        out = self.run_job(runs=runs)
        self.assertEqual(out["status"], "skipped")
        self.assertIn("both keys or not at all", out["why"])
        self.assertEqual((runs.calls, self.ledger().looks), ([], []), "no DVAL, no reserve, nothing spent")

    def failing_runs(self, code, error, *, where="segments"):
        runs = F.InlineRuns(self.root / "equity-daily")
        real_segments, real_on_store = runs.segments, runs.on_store

        def segments(c, params):
            if where == "segments" and c == code:
                raise error
            return real_segments(c, params)

        def on_store(root, c, params, start, end, k):
            if where == "dval" and c == code and ("deep-A-" in str(root) or "deep-B-" in str(root)):
                raise error
            return real_on_store(root, c, params, start, end, k)

        runs.segments, runs.on_store = segments, on_store
        return runs

    def test_one_failing_version_never_stops_the_next_and_spends_no_look(self):
        bad = self.rows[0]["code"]
        key = gate.version_key(bad, {})
        for night in (1, 2, 3):
            out = self.run_job(runs=self.failing_runs(bad, RunFailed("the decider child failed the run: OSError")))
            ledger = self.ledger()
            self.assertEqual(out["house_errors"], 1, night)
            self.assertIsNone(ledger.row(key), "its look is not spent")
            self.assertEqual(ledger.errors[key]["count"], night)
            self.assertEqual(ledger.errors[key]["error"], "RunFailed", "the error's class, never its text")
            self.assertTrue(any("not spent" in a["text"] and a["level"] == "warning" for a in self.ctx_last.alerts))
            if night == 1:
                self.assertEqual(out["looked"], 3, "the later versions were looked at")
        self.assertIn(key, ledger.refused, "three errors under one identity: refused, no look spent")
        self.assertTrue(ledger.refused[key]["why"].startswith("the House could not run its look 3 times"))
        self.assertEqual(json.loads((self.root / config.STORE_DIR / config.REPORT).read_text())["house_errors"],
                         {"versions": 1, "refused": 1})
        self.assertEqual(self.run_job()["house_errors"], 0, "a refused version is not tried again")

    def test_a_data_error_inside_the_look_spends_nothing(self):
        bad = self.rows[0]["code"]
        out = self.run_job(runs=self.failing_runs(bad, ValueError("no price"), where="dval"))
        self.assertEqual((out["house_errors"], out["looked"]), (1, 3))
        self.assertIsNone(self.ledger().row(gate.version_key(bad, {})))
        self.assertEqual(os.listdir(self.root / config.STORE_DIR / config.SEALED_DIR / config.LOOKS_DIR), [])
        out = self.run_job()
        self.assertEqual(out["looked"], 1, "owed: the version's look is still its own")

    def test_a_sealed_run_that_does_not_return_is_warned_and_owed_once(self):
        bad = self.rows[0]["code"]
        out = self.run_job(runs=self.failing_runs(bad, RunLost("the decider did not answer in time"), where="dval"))
        self.assertEqual(out["statuses"].get("lost"), 1)
        self.assertTrue(any("owed once more" in a["text"] for a in self.ctx_last.alerts))
        self.assertEqual(self.ledger().row(gate.version_key(bad, {}))["attempts"], 1)

    def test_no_version_is_begun_without_room_on_the_wall(self):
        ticks = iter([0.0, config.JOB_WALL_S - config.LOOK_ROOM_S + 1.0])
        out = self.run_job(clock=lambda: next(ticks, 10_000.0))
        self.assertEqual((out["looked"], out.get("stopped")), (0, "time"))
        self.assertEqual(self.ledger().looks, [])
        self.assertEqual(registry.by_name()["deep_report"].wall, config.JOB_WALL_S)

    def test_a_damaged_ledger_fails_closed(self):
        path = self.root / config.STORE_DIR / config.LEDGER
        path.write_text("{broken")
        runs = F.InlineRuns(self.root / "equity-daily")
        out = self.run_job(runs=runs)
        self.assertEqual(out["status"], "failed")
        self.assertEqual(runs.calls, [])
        self.assertEqual(path.read_text(), "{broken", "nothing written over it")
        self.assertTrue(any("damaged" in a["text"] for a in self.ctx_last.alerts))
        report = json.loads((self.root / config.STORE_DIR / config.REPORT).read_text())
        self.assertEqual(report["ledger"], "damaged")

    def test_a_seed_with_no_route_is_looked_at_and_any_other_route_less_version_refused(self):
        rows = [{**self.rows[0], "route": None, "source": "seed", "seated": True},
                {**self.rows[1], "route": None, "source": "born"}]
        out = self.run_job(rows=rows)
        self.assertEqual(out["statuses"], {"looked": 1, "refused": 1})
        report = json.loads((self.root / config.STORE_DIR / config.REPORT).read_text())
        self.assertEqual((report["by_source"]["seed"]["looked"], report["by_seat"]["seated"]["looked"]), (1, 1))
        self.assertIn("no route is named: its 2001-08 recall cannot be read", report["refused"])

    def test_it_runs_in_report_mode_in_idle_hours_with_a_deep_store_only(self):
        self.assertEqual(self.run_job(SESSION)["status"], "skipped")
        (self.root / "swarm.json").write_text(json.dumps({"elane": {"deep": {"mode": "off"}}}))
        self.assertIn("mode is off", self.run_job()["why"])
        (self.root / "swarm.json").write_text(json.dumps({"elane": {"deep": {"mode": "report"}}}))
        out = deep_report.report_run(self.ctx(), runs=F.InlineRuns(self.root / "equity-daily"), worlds=1500)
        self.assertIn("not complete", out["why"], "a store missing funds and spans is not the deep store")

    def test_the_registry_rows(self):
        jobs = registry.by_name()
        self.assertEqual(jobs["equity_deep"].module, "league.ops.equity_deep")
        self.assertEqual(jobs["deep_report"].module, "league.ops.deep_report")
        self.assertFalse(jobs["deep_report"].in_pause)
        self.assertNotIn("deep_census", jobs, "the eligibility census is the captain's scratch script")
        for name in ("equity_deep", "deep_report"):
            self.assertEqual(jobs[name].owner, "deep key")
        self.assertEqual([t.kind for t in jobs["equity_deep"].triggers], ["daily"], "no at-start fetch")


from league.tests import test_contam_probe as TP  # noqa: E402  (the probe's own harness, reused)


class TheProbeWithADeepStore(TP.Jobs):
    """The probe's run with the deep store there: E3's cells, then the deep eras' (S1, S2, S4), scored on the deep
    store's truths; a route published without them is due at once; without the store the run is E3's."""

    def deep_truth(self):
        from league.deep import blocks

        deep = F.deep_store(self.root / config.STORE_DIR, ("SPY", "QQQ", "XLK", "TLT"),
                            inception={"TLT": dt.date(2002, 7, 30)})
        cap = gate.mint_deep_gate_capability(deep, contam_probe.DEEP_GATE_REASON)
        return contam_probe._DeepTruth(blocks.DeepStore(deep, gate=cap))

    def run_probe(self, deep):
        ctx = Context("contam_probe", root=self.root, due_at=self.clock(), clock=self.clock, config={}, settings_value={})
        settings = TP.settings(usd_run=6.0)
        settings["elane"]["e2"]["routes"] = ["sail:pro_asap"]  # one route: "due" is that route's alone
        return contam_probe.Probe(ctx, store=self.store, settings=settings, router=self.router,
                                  equity=self.equity(3), symbols=TP.UNIVERSE, clock=lambda: 0.0, deep=deep).run()

    def test_the_deep_eras_are_asked_after_e3s_and_published_with_them(self):
        out = self.run_probe(self.deep_truth())
        self.assertTrue(out["finished"], out)
        row = json.loads((self.root / contam_probe.FILE).read_text())["routes"]["sail:pro_asap"]
        for stratum in ("S1", "S2", "S4"):
            self.assertEqual(set(row["cells"][stratum]), {*contam_probe.ERAS, *contam_probe.DEEP_ERAS})
            for era in contam_probe.DEEP_ERAS:
                keys = contam_probe.SEALED_CELL_KEYS if era in contam_probe.SEALED_ERAS else contam_probe.CELL_KEYS
                self.assertEqual(set(row["cells"][stratum][era]), set(keys))
                self.assertGreater(row["cells"][stratum][era]["n"], 0, "the deep store gave truths")
        self.assertEqual(contam_probe.SEALED_ERAS, ("2001-08",))
        for name in ("acc", "base", "lo", "hi", "correct", "ties"):   # the review of Oct 17: no DVAL figure beyond
            self.assertNotIn(name, contam_probe.SEALED_CELL_KEYS)
        self.assertTrue({"m", "p_perm", "readable"} <= set(contam_probe.SEALED_CELL_KEYS), "what strong_recall reads")
        doc = json.loads((self.root / contam_probe.FILE).read_text())
        for entry in doc["history"]:
            for stratum, eras in entry["cells"].items():
                if "2001-08" in eras:
                    self.assertEqual(set(eras["2001-08"]), set(contam_probe.SEALED_CELL_KEYS), "the history too")
        self.assertEqual(set(row["cells"]["S3"]), set(contam_probe.ERAS), "the stocks have no deep cell")
        self.assertIn(deep_report.strong_recall({"routes": {"sail:pro_asap": row}}, "sail:pro_asap"), (True, False))

    def test_a_route_published_without_the_deep_eras_is_due_at_once(self):
        first = self.run_probe(None)
        self.assertTrue(first["finished"])
        self.assertEqual(self.run_probe(None)["status"], "skipped", "E3's probe: not due for 28 days")
        again = self.run_probe(self.deep_truth())
        self.assertTrue(again["finished"], again)


if __name__ == "__main__":
    unittest.main()
