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
ran them on main 47ed6872ce6c232b743cc556f5540892b9132470: main 8ab31e32 (releases E5-A and E3.1, deployed 22:51Z
Oct 11, 2026) with PR #543, the Probe sleeve at 0.50 x E (the captain's A32, new lots from Thursday Oct 15, 2026),
the release the six programs trade under from then; and the fixture keeps what the book did: every POST,
cancel, fill and alert and the seat rule's every line whole, and a digest of every intent, order, lot and instance
row, of the book's keys (the seat plan, the open note and the unproven-sale note among them), of every record and
of every minute's answer, and of the forward record's twin rows, events, nights and readings.

WHAT THAT MAIN ADDED, each with scenarios of its own beside the 65 recorded on the main before it (81963c87):
- THE SEAT RULE "activity-1-free" (A24 with A30): thirteen sessions over six ranked programs, three of which never
  ask: nobody waits and the idle seats are kept; one program waits and an idle seat yields to it; two wait and one
  seat yields a decision day; a session in which the House refused every open is left out of the idle clock; a
  yielded program returns into a freed seat; the House refusing every buy (a failed SELL stage) runs no idle clock.
- AN EXIT'S WAIT HAS AN END (A28): the weeks in which the practice sale is never witnessed now sell at the entry
  cut-off (09:45), with one alert a session; they were recorded before, when every lot stayed held.
- THE TWIN IS RE-BASED (A29): eight sessions with the forward record's night after each (the real registry,
  `forward_shadow.Shadow` and `forward_twins.finish`): every buy fills and nothing is re-based; Monday's buys are
  missed and the twins are re-based; a rebuy is missed mid-week; the practice sale is never witnessed.

    python league/tests/equity_week.py --tree <a clean tree of main> --out league/tests/fixtures/equity_etf_orders.json

These tests run the same scenarios on the tree they are in and hold each to that file, through the test double of the
swarm's reader and, every one again, through the REAL reader over a real swarm store at every position of the panel
lane's switch (none, "off", "train"; at "train" the store also holds a panel family in Train research). TWO
DIFFERENCES ARE ALLOWED, each held to what it must be (`equity_week.main_shape`): the column `eq_instances.kind`,
"equity" on every row, and the panel adapter's table `eq_rebalances`, empty. The forward store has none: release E4
adds no table and no column to it.

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
#: The release the fixture was recorded on: main, with releases E5-A (the seat rule) and E3.1 (the exit wait's end,
#: the re-based twin) deployed, and PR #543 (A32: the Probe sleeve at 0.50 x E) on it. Recorded again from
#: 8ab31e32's record when #543 was merged under release E4: every one of the 75 scenarios moved, by the lot's size
#: alone (a one-ETF lot is half the sleeve: twice the shares of each order), and two records were equal to the byte.
RECORDED_ON = "47ed6872ce6c232b743cc556f5540892b9132470"


def differences(name: str, want: dict, got: dict) -> str:
    """What differs between a scenario as the fixture keeps it and as this tree ran it, for a failure's message."""
    lines = [f"{name}:"]
    for part in W.WHOLE:
        if part in want and want[part] != got[part]:
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
        kept = W.kept(got, whole=group == "memory")
        if kept != want:
            self.fail("a share program's live path is not main's.\n" + differences(name, want, kept))

    def test_the_fixture_is_mains_and_holds_every_scenario(self):
        self.assertEqual(self.fixture["_recorded_on"], RECORDED_ON)
        self.assertEqual(sorted(self.fixture["memory"]), sorted(W.SCENARIOS))
        self.assertEqual(sorted(self.fixture["store"]), sorted(W.STORE_SCENARIOS))
        self.assertEqual(set(W.STORE_SCENARIOS), set(W.SCENARIOS), "every scenario runs through the real reader too")
        self.assertGreaterEqual(len(W.SCENARIOS), 75)
        # MAIN'S OWN TWO READERS AGREE ON THE ORDERS AND THE SEATS: through the real reader main's book sent what it
        # sent through the test double, and seated whom it seated, in every scenario (the rows differ in what names a
        # program: its run sha).
        for name in W.SCENARIOS:
            for part in W.WHOLE:
                self.assertEqual(self.fixture["store"][name]["sha"][part],
                                 [len(self.fixture["memory"][name][part]), W.digest(self.fixture["memory"][name][part])],
                                 (name, part))
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

    def test_the_seat_rule_is_in_the_record(self):
        """THE SEAT RULE (release E5-A; A24 with A30) as main's book applied it, read off the fixture's whole parts: so
        the comparison holds this tree to each pass of it, line for line."""
        f = self.fixture["memory"]

        def said(name: str, word: str) -> list[str]:
            return [row[:14] + " " + row.split(f" {word}: ", 1)[1].split(":")[0]
                    for row in f[name]["seats"] if f" {word}: " in row]

        kept = f["fortnight: nobody waits, the idle seats are kept"]["seats"]
        self.assertTrue(any("bred-d-idle seated 10 sessions IDLE" in row for row in kept), "named idle at ten sessions")
        self.assertFalse(any(" yielded: " in row for row in kept), "and it keeps its seat while nobody waits")
        one = "fortnight: an idle seat yields to the waiting program"
        self.assertEqual(said(one, "yielded"), ["10-23 16:21:11 bred-d-idle for bred-e-wait"])
        self.assertEqual(said(one, "seated"), ["10-23 16:21:11 bred-e-wait (rank 1)"])
        first = [row for row in f[one]["posts"] if "bred-e-wait" in row][0]
        self.assertTrue(first.startswith("10-26 09:3") and " alpaca buy DIA " in first,
                        "seated at Friday's decide, its first buy goes at Monday's open")
        self.assertFalse(any("bred-d-idle" in row for row in f[one]["posts"]), "a yield sells nothing: it held nothing")
        two = "fortnight: two programs wait, one idle seat yields a decision day"
        self.assertEqual(said(two, "yielded"), ["10-23 16:21:11 bred-d-idle for bred-e-wait",
                                                "10-26 16:21:11 seed-reversal-index for bred-f-wait"])
        refused = "fortnight: the House refused every open one session, the idle clock leaves it out"
        self.assertEqual(said(refused, "yielded"), ["10-26 16:21:11 bred-d-idle for bred-e-wait"], "a session later")
        self.assertTrue(any("1 more left out: the House refused every open" in row for row in f[refused]["seats"]))
        back = "fortnight: a yielded program returns into a seat the swarm freed"
        self.assertEqual(said(back, "returned"), ["10-26 16:21:11 bred-d-idle (rank 1)"])
        stopped = f["fortnight: a waiting program, stage SELL never passing"]["seats"]
        self.assertFalse(any(" yielded: " in row or " seated: " in row for row in stopped),
                         "while the House refuses every buy no idle clock runs and no seat changes hands")
        # A week is too short for the rule to move a seat: the 65 scenarios recorded before it show six held seats.
        self.assertTrue(all("waiting: nobody" in row for row in f["week: normal"]["seats"]))

    def test_the_exit_waits_end_is_in_the_record(self):
        """AN EXIT'S WAIT FOR THE PRACTICE PROOF HAS AN END (release E3.1; A28): in the weeks in which the practice
        sale is never witnessed, every real sale goes at the entry cut-off (the 09:45 minute) and the owner is told
        once a session (same-symbol sales of two programs still go one a minute); in the normal week none waits
        that long and nothing is said."""
        f = self.fixture["memory"]

        def sales(name: str) -> list[str]:
            return [row for row in f[name]["posts"] if " alpaca sell " in row]

        def told(name: str) -> list[str]:
            return [row[:5] for row in f[name]["alerts"] if "the sale path is unproven today" in row]

        for name in ("week: stage SELL cannot pass, no FILL activity",
                     "week: stage SELL cannot pass, the practice sale rests",
                     "week: the owner's flatten on Tuesday, stage SELL not passing",
                     "twin: the practice sale never witnessed, exits at the cut-off"):
            with self.subTest(scenario=name):
                self.assertGreaterEqual(len(sales(name)), 3)
                minutes = {row[6:11] for row in sales(name)}
                self.assertIn("09:45", minutes, "the exits go at the cut-off's minute")
                self.assertLessEqual(minutes, {"09:45", "09:46"}, "and a second sale of one symbol the minute after")
                self.assertEqual(told(name), sorted({row[:5] for row in sales(name)}), "one alert a session with a sale")
        self.assertFalse({row[6:11] for row in sales("week: normal")} & {"09:45"})
        self.assertEqual(told("week: normal"), [])

    def test_the_re_based_twin_is_in_the_record(self):
        """THE TWIN IS RE-BASED AFTER A DIFFERENCE (release E3.1; A29), on this tree and held to main's record: with
        Monday's buys missed, the program that buys only when flat differs ONCE, its twin is re-based on the live
        book, and every session after agrees, where the un-re-based twin (kept beside) stays a session ahead."""
        name = "twin: Monday's buys missed, the twins re-based"
        snap = W.run(name)
        self.hold("memory", name, snap)
        rows = [r for r in snap["twins"] if r["instance"] == "bred-a-hold3@1:r"]
        self.assertEqual([r["day"] for r in rows][:3], ["2026-10-09", "2026-10-12", "2026-10-13"])
        self.assertEqual([r["agree"] for r in rows], [1, 0, 1, 1, 1, 1, 1, 1])
        self.assertEqual([r["rebased"] for r in rows], [0, 0, 1, 1, 1, 1, 1, 1])
        self.assertEqual([r["base_agree"] for r in rows], [1, 0, 1, 1, 0, 0, 1, 1], "as registered: out of phase")
        events = [(e[1], e[3]["instance"]) for e in snap["twin_events"] if e[0] == "twin_rebased"]
        self.assertEqual(events, [("2026-10-12", "bred-a-hold3@1:r"), ("2026-10-12", "bred-b-range@1:r")])
        beside = dict(snap["a14"])["bred-a-hold3@1:r"]["rebase"]
        self.assertEqual((beside["rebases"], beside["sessions"], beside["agreed"]), (1, 5, 3))
        quiet = W.run("twin: every buy fills, nothing is re-based")
        self.assertFalse([e for e in quiet["twin_events"] if e[0] == "twin_rebased"])
        self.assertTrue(all(r["agree"] == 1 and r["rebased"] == 0 and r["base_agree"] == 1 for r in quiet["twins"]))

    def test_every_scenario_is_mains_order_for_order(self):
        for name in W.SCENARIOS:
            with self.subTest(scenario=name):
                self.hold("memory", name, W.run(name))

    def test_through_the_real_reader_at_every_position_of_the_panels_switch(self):
        """The swarm's own reader (`league.equity.families.EquityFamilies` over `league.swarm.bands.read`) gives the
        book the six programs' rows; the panel lane's switch is the root's swarm.json. No key (policy.json's "off"),
        "off" and "train", EVERY scenario at each: what main's reader gave main's book, to the row."""
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

    def test_the_comparison_has_teeth_for_what_the_new_main_added(self):
        """A tree that lost one of main 8ab31e32's three rules is caught by the scenarios recorded for it, and only by
        them: (1) a reader that hides the waiting Candidates from the book (the reader as release E4 had it before
        the merge: no seat plan could rank them); (2) an exit that never waits for the practice sale; (3) a twin
        that is never re-based."""
        from league.equity import live as L
        from league.ops import forward_twins
        from league.swarm import bands

        seat = "fortnight: an idle seat yields to the waiting program"
        with mock.patch.object(bands, "_equity_seatable", lambda root: (lambda structure: False)):
            got = W.kept(W.run(seat, reader="store"), whole=False)
            self.assertNotEqual(got["sha"]["seats"], self.fixture["store"][seat]["sha"]["seats"])
            self.assertNotEqual(got["sha"]["posts"], self.fixture["store"][seat]["sha"]["posts"])
            self.assertEqual(W.kept(W.run("week: normal", reader="store"), whole=False),
                             self.fixture["store"]["week: normal"], "six seated programs and nobody waiting: the same")
        held = "week: stage SELL cannot pass, no FILL activity"
        with mock.patch.object(L.EquityBook, "_sell_proof", lambda self: None):
            self.assertNotEqual(W.kept(W.run(held))["posts"], self.fixture["memory"][held]["posts"])
            self.assertEqual(W.kept(W.run("normal")), self.fixture["memory"]["normal"], "Monday sells nothing: the same")
        twin = "twin: Monday's buys missed, the twins re-based"

        def never(self, seed):
            raise forward_twins.TwinInterrupted("the mutation: no re-base")

        with mock.patch.object(forward_twins.RebasedTwin, "rebase", never):
            got = W.kept(W.run(twin))
            self.assertNotEqual(got["sha"]["twins"], self.fixture["memory"][twin]["sha"]["twins"])
            self.assertEqual(got["posts"], self.fixture["memory"][twin]["posts"], "the book's own orders do not read it")


if __name__ == "__main__":
    unittest.main()
