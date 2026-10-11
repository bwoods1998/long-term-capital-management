"""THE SEATED SHARE PROGRAMS TRADE AS ON MAIN, ORDER FOR ORDER (the captain's ruling at release E4's ship check).

Release E4 put the panel kind into the live equity book (league/equity/live.py, package H), and one of its rules, the
spec's decision 27 (B8: a buy cut by a cap waits while an exit of its own program is working), was written for EVERY
instance. Six share programs hold real-money seats under release E1's entry rule. The ruling: with the panel lane
switched off and with it at "train", what the book does for a share program is what main's book does, order for order;
B8 is the panel kind's alone.

THE PROOF IS A RECORDED COMPARISON. league/tests/equity_week.py runs the REAL book, schedule, sizing, stock proof and
decider kind over a fake venue and invented prices: the first Monday of the lane the normal way, every way the
rehearsal of that Monday found a buy can miss, the week and its failing weeks, and programs that sell and buy in one
window (where B8 held a cut buy back: the five scenarios that differed on the tree before the ruling). Its recorder
ran them on main 81963c876f908bb877ca8dee99bb3d661234110f, the release the seats were taken under, and the fixture
keeps what the book did: every POST, cancel, fill and alert whole, and a digest of every intent, order, lot and
instance row, of the book's keys, of every record and of every minute's answer.

    python league/tests/equity_week.py --tree <a clean tree of main> --out league/tests/fixtures/equity_etf_orders.json

These tests run the same scenarios on the tree they are in and hold each to that file, through the test double of the
swarm's reader and through the REAL reader over a real swarm store at every position of the panel lane's switch (none,
"off", "train"; at "train" the store also holds a panel family in Train research). TWO DIFFERENCES ARE ALLOWED, each
held to what it must be (`equity_week.main_shape`): the column `eq_instances.kind`, "equity" on every row, and the
panel adapter's table `eq_rebalances`, empty.

A LATER CHANGE OF THE SHARE PROGRAMS' PATH FAILS HERE. When it is meant (a release of main that changes the book),
record the fixture again on that release's clean tree and say in the commit which scenarios moved and why."""

from __future__ import annotations

import difflib
import json
import os
import unittest
from pathlib import Path
from unittest import mock

try:
    import numpy  # noqa: F401 - the panel adapter the book imports at its start needs it
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

from league.tests import equity_week as W

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "equity_etf_orders.json"
#: The release the fixture was recorded on: main, with releases E5-S (six seats) and E2.4 deployed.
RECORDED_ON = "81963c876f908bb877ca8dee99bb3d661234110f"


def differences(name: str, want: dict, got: dict) -> str:
    """What differs between a scenario as the fixture keeps it and as this tree ran it, for a failure's message."""
    lines = [f"{name}:"]
    for part in W.WHOLE:
        if want[part] != got[part]:
            lines.append(f"  {part} (main -, this tree +):")
            lines.extend("    " + row for row in difflib.unified_diff(want[part], got[part], lineterm="", n=1)
                         if not row.startswith(("---", "+++")))
    for part in sorted(set(want["sha"]) | set(got["sha"])):
        a, b = want["sha"].get(part), got["sha"].get(part)
        if a != b:
            lines.append(f"  {part}: {a[0] if a else 'no'} rows on main, {b[0] if b else 'no'} on this tree"
                         + ("" if a and b and a[0] != b[0] else " (the rows differ)"))
    return "\n".join(lines)


@unittest.skipUnless(HAVE, "numpy not installed")
class TheSeatedShareProgramsTradeAsOnMain(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def hold(self, group: str, name: str, got: dict) -> None:
        want = self.fixture[group][name]
        kept = W.kept(got)
        if kept != want:
            self.fail("a share program's live path is not main's.\n" + differences(name, want, kept))

    def test_the_fixture_is_mains_and_holds_every_scenario(self):
        self.assertEqual(self.fixture["_recorded_on"], RECORDED_ON)
        self.assertEqual(sorted(self.fixture["memory"]), sorted(W.SCENARIOS))
        self.assertEqual(sorted(self.fixture["store"]), sorted(W.STORE_SCENARIOS))
        self.assertTrue(set(W.STORE_SCENARIOS) <= set(W.SCENARIOS))
        # It is a record of TRADING: the normal Monday's three buys after the practice buy, and a week of sales.
        normal = self.fixture["memory"]["normal"]
        self.assertEqual([row.split()[2:5] for row in normal["posts"]],
                         [["paper", "buy", "SPY"], ["alpaca", "buy", "QQQ"], ["alpaca", "buy", "SPY"],
                          ["alpaca", "buy", "QQQ"]])
        self.assertEqual(len(normal["fills"]), 4)
        week = self.fixture["memory"]["week: normal"]
        self.assertGreater(len([row for row in week["posts"] if " alpaca sell " in row]), 5)
        self.assertEqual(week["sha"]["instances"][0], 6, "six seated programs")
        # No scenario is a copy of another by accident: the ones that change something leave another record.
        seen = {json.dumps(kept, sort_keys=True) for kept in self.fixture["memory"].values()}
        self.assertGreater(len(seen), len(W.SCENARIOS) - 6)

    def test_every_scenario_is_mains_order_for_order(self):
        for name in W.SCENARIOS:
            with self.subTest(scenario=name):
                self.hold("memory", name, W.run(name))

    def test_through_the_real_reader_at_every_position_of_the_panels_switch(self):
        """The swarm's own reader (`league.equity.families.EquityFamilies` over `league.swarm.bands.read`) gives the
        book the six programs' rows; the panel lane's switch is the root's swarm.json. No key (policy.json's "off"),
        "off" and "train": the same orders as main's reader gave main's book."""
        for name in W.STORE_SCENARIOS:
            for panel in W.SWITCHES:
                with self.subTest(scenario=name, panel=panel or "no key"):
                    self.hold("store", name, W.run(name, reader="store", panel=panel))

    def test_at_train_the_swarm_holds_a_panel_family_the_book_never_sees(self):
        """What "train" means in the comparison above: the switch reads "train" from the root's settings, the store
        holds a panel family in Train research beside the six seated ETF families, and the reader gives the book the
        six and nothing of the panel (so the book made no panel instance: `main_shape` refuses a snapshot with one)."""
        import tempfile

        from league.equity import LANES
        from league.swarm import bands, elane_xs
        from league.swarm import settings as settings_mod
        from league.swarm.store import SwarmStore

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clock = W.Clock(W.at(W.FRIDAY, 16, 0))
            families = W.store_families(root, W.six_programs(), clock, "train")
            self.addCleanup(lambda: families._store is not None and families._store.close())
            self.assertEqual(elane_xs.cfg(settings_mod.load(root))["mode"], "train")
            store = SwarmStore(root, clock=clock)
            self.addCleanup(store.close)
            panel = [f for f in store.families(lanes="all") if f["structure"] == "panel"]
            self.assertEqual([(f["id"], f["band"]) for f in panel], [("xs-in-train", "gym")])
            rows = families.read()
            self.assertEqual(families.last_error, "")
            self.assertEqual(sorted(r["family"] for r in rows), sorted(p["family"] for p in W.six_programs()))
            self.assertEqual({r["structure"] for r in rows}, {"etf"})
            self.assertEqual([r["family"] for r in bands.read(root, lanes=LANES) if r["structure"] == "panel"], [])

    def test_two_runs_of_one_tree_are_equal_and_no_path_or_drawn_id_is_kept(self):
        a, b = W.run("week: normal"), W.run("week: normal")
        self.assertEqual(a, b)
        text = json.dumps(a)
        self.assertNotIn(os.environ.get("TMPDIR") or "/tmp", text)
        self.assertNotIn("equity-week-", text, "the scenario's own folder")

    def test_the_two_additions_of_e4_are_held_to_what_they_must_be(self):
        snap = W.run("normal")
        self.assertEqual({row[W.E4_COLUMN] for row in snap["instances"]}, {"equity"})
        self.assertIn(W.E4_TABLE, snap["tables"])
        self.assertEqual(snap["rebalances"], [])
        shaped = W.main_shape(snap)
        self.assertNotIn(W.E4_TABLE, shaped["tables"])
        self.assertFalse(any(W.E4_COLUMN in row for row in shaped["instances"]))
        self.assertEqual(W.main_shape(shaped), shaped, "main's own snapshot is returned as it is")
        with self.assertRaises(ValueError):
            W.main_shape({**snap, "instances": [{**snap["instances"][0], W.E4_COLUMN: "panel"}]})
        with self.assertRaises(ValueError):
            W.main_shape({**snap, "rebalances": [{"rid": 1}]})

    def test_the_comparison_has_teeth_b8_for_every_instance_is_caught(self):
        """The rule as the spec's decision 27 wrote it (a cut buy of ANY instance waits for its own program's exits)
        is the change this file exists to catch: with the gate opened for the book's own kind
        (`EquityBook._cut_waits`), the weeks in which a program's buy is cut while its own sale works are no longer
        main's, and the others still are."""
        from league.equity import live as L

        moved = ("week: a rolling program while stage SELL cannot pass",
                 "week: a rotating program while stage SELL cannot pass",
                 "week: a rotating program's sales rest five minutes at every open",
                 "week: a rotating program's sales rest two minutes at every close",
                 "week: a rolling and a rotating program, sales resting five minutes")
        with mock.patch.object(L.EquityBook, "_cut_waits", staticmethod(lambda inst: True)):
            for name in moved:
                with self.subTest(scenario=name):
                    got, want = W.kept(W.run(name)), self.fixture["memory"][name]
                    self.assertNotEqual(got["posts"], want["posts"], "B8 for a share program changes its orders")
                    self.assertNotEqual(got["sha"]["intents"], want["sha"]["intents"])
            for name in ("normal", "week: normal", "week: a program rotates between ETFs at every open"):
                with self.subTest(scenario=name):
                    self.assertEqual(W.kept(W.run(name)), self.fixture["memory"][name],
                                     "no buy is cut while its own program's exit works: B8 has nothing to hold")


if __name__ == "__main__":
    unittest.main()
