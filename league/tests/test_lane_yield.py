"""RESEARCH DOLLARS BY MEASURED YIELD (Oct 15, 2026; league/ops/lane_yield.py): the dlane report's `lane_yield`
section. Each spend row goes to one research group by its own request key or family, the shared pools are divided by
their stated rules (the harness never), the counts are the funnel's and the forward registry's, and the section never
fails the report. Every figure is invented."""

from __future__ import annotations

import datetime as dt
import sqlite3
import tempfile
import unittest
from pathlib import Path

from league.live.state import LiveState
from league.ops import dlane_report as R
from league.ops import guard
from league.ops import lane_yield as Y
from league.swarm.store import SwarmStore

NOW = dt.datetime(2026, 10, 20, 16, 0, tzinfo=dt.timezone.utc).timestamp()
GATE = {"dlane": {"mode": "gate"}}


def funnel_window(**rows) -> dict:
    """A funnel window with the four lanes' rows (the report's own shape), each overridden by `rows`."""
    def row(**over):
        base = {"births": 0, "gym_runs": {"train": 0, "validation": 0, "holdout": 0, "forward": 0, "probe": 0,
                                          "mechanism": 0},
                "validations": {"judged": 0, "passed": 0}, "looks": {"taken": 0, "passed": 0, "by_screen": {}},
                "band_moves": {"candidate": 0, "probe": 0, "sized": 0},
                "real_closes": {":r": 0, ":t": 0, ":i": 0, "other": 0},
                "real_opens": {":r": 0, ":t": 0, ":i": 0, "other": 0}}
        base.update(over)
        return base
    return {lane: row(**rows.get(lane, {})) for lane in ("alpha", "direction", "beta", "equity")}


class Store(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = NOW - 3600.0
        self.store = SwarmStore(self.root, clock=lambda: self.now)
        self.addCleanup(self.store.close)
        self.live = LiveState(self.root / "live.sqlite")
        self.addCleanup(self.live.close)
        self.store.add_family({"id": "opt-a", "mechanism": "an options mechanism sentence long enough for the store",
                               "structure": "long_single", "roots": ["SPY"]}, origin="architect")
        self.store.add_family({"id": "dir-a", "mechanism": "a direction mechanism sentence long enough for the store",
                               "structure": "long_single", "roots": ["SPY"], "lane": "direction"}, origin="architect")
        self.store.add_family({"id": "eq-a", "mechanism": "an equity mechanism sentence long enough for the store",
                               "structure": "etf", "roots": ["XLK"], "symbols": ["XLK"], "lane": "equity"},
                              origin="architect")
        self.store.add_family({"id": "pan-a", "mechanism": "a published cross-sectional prior long enough for the store",
                               "structure": "stock", "roots": ["AAPL"], "lane": "equity"}, origin="architect")
        self.store._db.execute("UPDATE families SET structure='panel' WHERE id='pan-a'")
        self.lanes = R.Lanes(self.store)

    def families(self) -> Y.Families:
        return Y.Families(self.store, self.lanes.of)

    def spend(self, kind: str, usd: float, key: str | None = None, family: str | None = None, **detail) -> None:
        if key is not None:
            detail["key"] = key
        self.store.add_spend(kind, usd, family=family, detail=detail)


class TheRowsGoWhereTheyAreOwned(Store):
    def test_each_row_by_its_own_key_or_family(self):
        f = self.families()
        cases = [
            (("gym_box", None, {"box": "b1"}), ("pool", "gym_boxes")),
            (("sail_model", None, {"key": "swarm:elane:births:1"}), ("pool", "equity_births")),
            (("sail_model", "eq-a", {"key": "swarm:elane:train:eq-a:1"}), ("group", "equity_lanes")),
            (("sail_model", "eq-a", {"hold": "swarm:elane:review:eq-a:1:0"}), ("group", "equity_lanes")),
            (("sail_model", "pan-a", {"key": "swarm:elane:xs:train:pan-a:1"}), ("group", "panel")),
            (("sail_model", "pan-a", {"settles": "swarm:elane:audit:pan-a:1:0"}), ("group", "panel")),
            (("sail_model", None, {"key": "swarm:architect:1"}), ("pool", "options_architect")),
            (("claude", None, {"key": "swarm:strategist:1"}), ("pool", "options_strategist")),
            (("sail_model", "opt-a", {"key": "swarm-opt-a:cycle"}), ("group", "alpha")),
            (("claude", "dir-a", {"key": "swarm:dlane:dir-a:review:1:0"}), ("group", "direction")),
            (("claude", None, {"key": "engineer:42"}), ("pool", "harness")),
            (("sail_model", "gone", {"key": "x"}), ("pool", "harness")),
            (("openai", None, {}), ("pool", "harness")),
        ]
        for (kind, family, detail), want in cases:
            self.assertEqual(Y.classify(kind, family, detail, f), want, (kind, family, detail))

    def test_the_route_is_the_rows_kind_and_profile(self):
        self.assertEqual(Y.route_of("sail_model", '{"profile": "pro_asap"}'), "sail:pro_asap")
        self.assertEqual(Y.route_of("sail_model", "{}"), "sail_model")
        self.assertEqual(Y.route_of("gym_box", '{"box": "b"}'), "gym_box")
        self.assertEqual(Y.route_of("claude", "not json"), "claude")

    def test_the_constants_are_the_codes_own(self):
        from league.equity import LANES
        from league.swarm import dlane, elane_xs
        from league.ops import forward_screen

        self.assertEqual(Y.EQUITY_LANES, tuple(LANES))
        self.assertEqual(Y.OPTIONS, (dlane.ALPHA, dlane.DIRECTION))
        self.assertEqual(Y.PANEL_STRUCTURE, elane_xs.STRUCTURE)
        self.assertEqual(Y.FORWARD_DB, forward_screen.forward_db.DB)


class TheDollarsAndTheirYield(Store):
    def setUp(self):
        super().setUp()
        self.spend("gym_box", 6.0, box="b1")
        self.spend("sail_model", 3.0, "swarm:architect:1", profile="pro_asap")
        self.spend("claude", 1.0, "swarm:strategist:1")
        self.spend("sail_model", 0.5, "swarm:elane:births:1", profile="pro_asap")
        self.spend("sail_model", 0.25, "swarm:elane:train:eq-a:1", family="eq-a", profile="k3")
        self.spend("sail_model", 0.25, "swarm:elane:xs:train:pan-a:1", family="pan-a", profile="pro_asap")
        self.spend("sail_model", 2.0, "swarm-opt-a:cycle", family="opt-a", profile="flash_asap")
        self.spend("claude", 0.75, "engineer:9")
        self.now = NOW
        self.window = funnel_window(alpha={"births": 30, "gym_runs": {"train": 900, "validation": 0}},
                                    direction={"births": 10, "gym_runs": {"train": 300, "validation": 0},
                                               "looks": {"taken": 2, "passed": 1, "by_screen": {}},
                                               "band_moves": {"candidate": 1, "probe": 1, "sized": 0}},
                                    equity={"births": 6, "gym_runs": {"train": 40, "validation": 4},
                                            "looks": {"taken": 3, "passed": 1, "by_screen": {}},
                                            "band_moves": {"candidate": 1, "probe": 1, "sized": 0}})
        self.store.event("swarm.born", "pan-a", {"lane": "equity", "structure": "panel"})
        self.store.event("swarm.born", "pan-a", {"lane": "equity", "structure": "panel"})

    def test_every_dollar_is_in_a_group_or_a_named_pool_and_the_pools_divide_by_their_rules(self):
        out = Y.window(self.store, self.families(), self.window, root=self.root, now=NOW, hours=24.0)
        g = out["groups"]
        self.assertAlmostEqual(out["usd_total"], 13.75)
        # The Gym's boxes by Gym evaluations (900:300), the architect and the strategist by births (30:10).
        self.assertAlmostEqual(out["pools"]["gym_boxes"]["to"]["alpha"], 4.5)
        self.assertAlmostEqual(out["pools"]["gym_boxes"]["to"]["direction"], 1.5)
        self.assertAlmostEqual(out["pools"]["options_architect"]["to"]["alpha"], 2.25)
        self.assertAlmostEqual(out["pools"]["options_strategist"]["to"]["direction"], 0.25)
        # E2's births pass by the window's equity births: 4 share programs (6 less the 2 panel births) to 2 panels.
        self.assertAlmostEqual(out["pools"]["equity_births"]["to"]["equity_lanes"], 0.5 * 4 / 6, places=4)
        self.assertAlmostEqual(out["pools"]["equity_births"]["to"]["panel"], 0.5 * 2 / 6, places=4)
        # The harness is said beside and carried by no group.
        self.assertIsNone(out["pools"]["harness"]["to"])
        self.assertAlmostEqual(out["unallocated_usd"], 0.75)
        self.assertAlmostEqual(sum(v["usd"] for v in g.values()) + out["unallocated_usd"], out["usd_total"])
        self.assertAlmostEqual(g["alpha"]["usd"], 2.0 + 4.5 + 2.25 + 0.75)
        self.assertAlmostEqual(g["alpha"]["usd_direct"], 2.0)
        self.assertAlmostEqual(g["equity_lanes"]["usd"], 0.25 + 0.5 * 4 / 6, places=4)
        self.assertEqual(g["equity_lanes"]["by_route"], {"sail:k3": 0.25})
        self.assertEqual(g["panel"]["counts"]["births"], 2)
        self.assertEqual(g["equity_lanes"]["counts"]["births"], 4)
        self.assertEqual(g["direction"]["counts"]["looks_passed"], 1)
        self.assertEqual(g["alpha"]["counts"]["gym_runs"], 900)
        self.assertAlmostEqual(out["usd_options_lanes"], 13.75 - 0.75 - g["equity_lanes"]["usd"] - g["panel"]["usd"])

    def test_per_dollar_and_dollars_per_with_none_where_a_side_is_zero(self):
        out = Y.window(self.store, self.families(), self.window, root=self.root, now=NOW, hours=24.0)
        eq = out["groups"]["equity_lanes"]
        usd = eq["usd"]
        self.assertAlmostEqual(eq["per_usd"]["looks_passed"], 1 / usd, places=3)
        self.assertAlmostEqual(eq["usd_per"]["to_probe"], usd, places=4)
        self.assertIsNone(out["groups"]["alpha"]["usd_per"]["looks_passed"], "no pass: no dollars a pass")
        self.assertEqual(out["groups"]["alpha"]["per_usd"]["looks_passed"], 0.0)
        per, each = Y.per_dollar({"births": 3}, 0.0)
        self.assertEqual((per["births"], each["births"]), (None, None))

    def test_a_pool_with_nothing_to_divide_by_stays_unallocated(self):
        out = Y.window(self.store, self.families(), funnel_window(), root=self.root, now=NOW, hours=24.0)
        self.assertIsNone(out["pools"]["gym_boxes"]["to"])
        self.assertIsNone(out["pools"]["options_architect"]["to"])
        self.assertAlmostEqual(out["unallocated_usd"], 6.0 + 3.0 + 1.0 + 0.75)
        # E2's births pass by the window's equity births: here the two panel births alone.
        self.assertAlmostEqual(out["pools"]["equity_births"]["to"]["panel"], 0.5)

    def test_a_births_pass_with_no_equity_birth_goes_to_the_share_programs(self):
        counts = Y.yields(funnel_window(), 0, {})
        money = Y.allocate({"groups": {}, "pools": {"equity_births": 0.5}}, counts)
        self.assertEqual(money["pools"]["equity_births"]["to"], {"equity_lanes": 0.5})

    def test_the_window_reads_only_its_own_rows(self):
        self.now = NOW - 3 * 86400.0
        self.spend("gym_box", 100.0, box="old")
        out = Y.window(self.store, self.families(), self.window, root=self.root, now=NOW, hours=24.0)
        self.assertAlmostEqual(out["usd_total"], 13.75)


class TheForwardSupply(Store):
    def registry(self, rows):
        db = sqlite3.connect(self.root / Y.FORWARD_DB)
        db.execute("CREATE TABLE fwd_registry (pid INTEGER PRIMARY KEY, lineage TEXT, ugroup TEXT, reason TEXT, "
                   "registered_at REAL)")
        db.executemany("INSERT INTO fwd_registry(pid, lineage, ugroup, reason, registered_at) VALUES(?,?,?,?,?)", rows)
        db.commit()
        db.close()

    def test_programs_and_first_registered_lineages_in_the_window_by_group(self):
        old, new = NOW - 3 * 86400.0, NOW - 3600.0
        self.registry([(1, "equity:L1", "index", "train_pass", old), (2, "equity:L1", "index", "train_fail", new),
                       (3, "equity:L2", "sectors", "train_pass", new), (4, "equity:L3", "sectors", "train_fail", new),
                       (5, "equity:P1", "panel:sp500", "train_pass", new), (6, "control:index:1", "index", "control", new)])
        with guard.readonly():
            out = Y.forward_supply(self.root, NOW - 86400.0)
        self.assertEqual(out["equity_lanes"], {"registered": 3, "lineages": 2}, "L1 was first registered before")
        self.assertEqual(out["panel"], {"registered": 1, "lineages": 1})

    def test_no_record_yet_and_an_unreadable_one_are_said(self):
        self.assertEqual(Y.forward_supply(self.root, 0.0), {"missing": True})
        (self.root / Y.FORWARD_DB).write_text("not a database")
        self.assertIn("error", Y.forward_supply(self.root, 0.0))
        self.assertIn("error", Y.forward_supply(None, 0.0))

    def test_the_counts_reach_the_equity_groups(self):
        self.registry([(1, "equity:L2", "sectors", "train_pass", NOW - 60.0)])
        out = Y.window(self.store, self.families(), funnel_window(), root=self.root, now=NOW, hours=24.0)
        self.assertEqual(out["groups"]["equity_lanes"]["counts"]["forward_lineages"], 1)
        self.assertEqual(out["groups"]["panel"]["counts"]["forward_registered"], 0)
        self.assertIsNone(out["forward"])


class TheSectionNeverFailsTheReport(Store):
    def test_a_window_that_cannot_be_read_is_said_and_the_other_reads(self):
        class Broken(dict):
            def get(self, key, default=None):
                if key == "7d":
                    raise RuntimeError("boom")
                return super().get(key, default)

        out = Y.section(self.store, self.lanes.of, Broken({"24h": funnel_window()}), root=self.root, now=NOW,
                        windows={"24h": 24.0, "7d": 168.0})
        self.assertIn("error", out["windows"]["7d"])
        self.assertIn("groups", out["windows"]["24h"])
        self.assertEqual(set(out["allocation"]), set(Y.POOLS))

    def test_the_report_carries_it_read_only_over_its_own_windows(self):
        self.spend("gym_box", 2.0, box="b1")
        self.now = NOW
        with guard.readonly():               # a writable SQLite open inside raises
            out = R.report(self.root, settings=GATE, now=NOW, count_from=R.inception())
        section = out["lane_yield"]
        self.assertEqual(set(section["windows"]), set(R.WINDOWS))
        self.assertAlmostEqual(section["windows"]["24h"]["usd_total"], 2.0)
        self.assertEqual(section["windows"]["7d"]["groups"]["alpha"]["counts"]["births"],
                         out["funnel"]["7d"]["alpha"]["births"])

    def test_a_section_that_raises_is_an_error_entry_never_a_failed_report(self):
        from unittest import mock

        with mock.patch.object(Y, "section", side_effect=RuntimeError("boom")):
            out = R.report(self.root, settings=GATE, now=NOW, count_from=R.inception())
        self.assertEqual(out["lane_yield"], {"error": "RuntimeError"})
        self.assertIn("funnel", out)


if __name__ == "__main__":
    unittest.main()
