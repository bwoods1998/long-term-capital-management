"""RELEASE 1019f's INTEGRATION: THE CAPTAIN'S A85 WITH R3'S BIRTHS (release 1019e), through the REAL book
(league/equity/live.py), the REAL `size_entry`, the money table in force and the lane's REAL store with a registered
birth (league/tests/test_events_book.py's harness, league/tests/test_events_births.py's spec). Every figure is invented.

fix/a85-probe-cash-reservation was built on release 1019d, before births: its round-robin and its reservation read a
program's BAND (`PRIORITY`), never its ROOM tier. On release 1019e a birth has its own tier (`book.BIRTH_ROOM`, R3-SPEC
section 4). Held here (the independent check of the A85 branch, its major): `book.send_key`'s tier is `room_key`'s,
round-robin only inside the Sized and Probe tiers (`ROUND_ROBIN_TIERS`); `book.allocate` groups by that tier;
`EquityBook._event_reserve` holds room only for Probe and Sized programs (`book.reserved_for`), and a learning buy
leaves that room (`book.leaves_room`).

RELEASE 1019h (the captain's A97, PL-2; R3-SPEC section 4 as A97 amends it, before any birth registered): a birth AT
LEARNING stays after every PREREG program (`BIRTH_ROOM`: never reserved for, never round-robins, its buy leaves the
room); a PROMOTED birth (Probe or Sized) takes ITS BAND'S TIER after that band's PREREG rows and before every learning
row (PREREG-EVL-5 section 1.3's frozen ROOM text: within a band the tables' order, R3's births after every file's rows):
it round-robins with them (last in each pass), A85's reservation holds room for it, and its own buy never leaves the
room. Before it, a birth at Probe was after every PREREG learning program and sized less a PREREG Probe's reservation,
so a promoted birth's Probe buys rarely reached Done's size."""

from __future__ import annotations

import unittest
from decimal import Decimal as D

from league.equity import live as L
from league.events import births as BI
from league.events import book as EB
from league.events import programs as P
from league.tests import test_events_book as TB
from league.tests.test_events_a85 import seed_history, short_of_cash
from league.tests.test_events_births import spec

BIRTH = "EVL-B-8K-502"                 # an 8k birth: an OPEN entry (league/events/births.py ENTRY)
PREREG_OPEN = "EVL-8K-READ-O1"         # a PREREG open entry
PREREG_CLOSE = "EVL-ERN-REACT-C1"      # a PREREG close entry
LEARN_ON = "EVL-NEWS-READ-ON"          # a PREREG close entry, overnight


def pick(symbol: str, program: str = "x") -> EB.Pick:
    return EB.Pick(program, 2, f"8k:{symbol}", symbol, f"c-{symbol}", 3.0, 1e6, D("16"), "t")


class Births(unittest.TestCase):
    def setUp(self):
        self.case = TB.EventTest("run")
        self.case.setUp()
        self.addCleanup(self.case.tmp.cleanup)
        self.addCleanup(P.load_births, None)
        self.h = self.case.harness()
        self.addCleanup(self.h.state.close)
        self.addCleanup(self.h.lane.st.close)
        sp = spec(BIRTH, "8k", {"items": ["5.02"]})
        self.h.lane.st.db.execute(
            "INSERT INTO births(id, version, sha, spec, seatable, registered_at, committed_at, received_at, path, "
            "commit_sha, seq, line, why, by, night) VALUES(?, 1, ?, ?, 1, ?, ?, ?, 'docs/births/2026-11-02.jsonl', ?, 0, "
            "'{}', 'x', 'captain', '2026-11-02')",
            (BIRTH, BI.sha(sp), BI.canonical(sp), "2026-11-03T01:00:00Z", "2026-11-03T01:00:00Z",
             "2026-11-03T01:00:00Z", "c" * 40))
        self.birth = P.load_births(self.h.lane.st)[0]
        self.assertEqual((self.birth.id, self.birth.entry_at), (BIRTH, "open"))

    # ------------------------------------------------------------------------------------------- the order (pure)
    def test_the_tiers_a_birth_at_learning_is_after_every_prereg_program_a_promoted_one_in_its_bands_tier(self):
        self.assertEqual(EB.room_key(BIRTH, "learning")[0], EB.BIRTH_ROOM, "A97: a birth at learning stays last")
        self.assertEqual(EB.room_key(BIRTH, "probe")[0], EB.PRIORITY["probe"], "A97 (PL-2): a promoted birth, its band's")
        self.assertEqual(EB.room_key(BIRTH, "sized")[0], EB.PRIORITY["sized"])
        # after that band's PREREG rows (the tables' order: births after every file's rows) and before every learning row
        prereg = [p for p in P.SEATING if p.spec is None]
        self.assertEqual(len(prereg), 15)
        for prog in prereg:
            self.assertLess(EB.room_key(prog.id, "probe"), EB.room_key(BIRTH, "probe"), prog.id)
            self.assertLess(EB.room_key(BIRTH, "probe"), EB.room_key(prog.id, "learning"), prog.id)
            self.assertLess(EB.room_key(prog.id, "learning"), EB.room_key(BIRTH, "learning"), prog.id)
        self.assertEqual(EB.ROUND_ROBIN_TIERS, (EB.PRIORITY["sized"], EB.PRIORITY["probe"]))
        self.assertEqual([EB.reserved_for(BIRTH, b) for b in ("sized", "probe", "learning")], [True, True, False],
                         "A97: A85 reserves for a promoted birth, never for one at learning")
        self.assertEqual([EB.reserved_for(PREREG_OPEN, b) for b in ("sized", "probe", "learning")], [True, True, False])
        self.assertEqual([EB.leaves_room(BIRTH, b) for b in ("sized", "probe", "learning", "retired")],
                         [False, False, True, False], "A97: a promoted birth's buy leaves no room, as its band's")
        self.assertEqual([EB.leaves_room(PREREG_OPEN, b) for b in ("sized", "probe", "learning", "retired")],
                         [False, False, True, False])

    def test_the_sends_a_birth_at_probe_round_robins_last_in_each_pass_and_one_at_learning_goes_last(self):
        rows = [(BIRTH, "probe", 0), (BIRTH, "probe", 1), (PREREG_OPEN, "probe", 0), (PREREG_OPEN, "probe", 1),
                (LEARN_ON, "learning", 0), (LEARN_ON, "learning", 1), (PREREG_CLOSE, "sized", 0)]
        order = sorted(rows, key=lambda r: EB.send_key(*r))
        self.assertEqual(order, [(PREREG_CLOSE, "sized", 0), (PREREG_OPEN, "probe", 0), (BIRTH, "probe", 0),
                                 (PREREG_OPEN, "probe", 1), (BIRTH, "probe", 1), (LEARN_ON, "learning", 0),
                                 (LEARN_ON, "learning", 1)],
                         "A97 (PL-2): the promoted birth in the Probe tier, after the PREREG Probe row in each pass, "
                         "before every learning buy")
        self.assertNotEqual(EB.send_key(BIRTH, "probe", 1), EB.send_key(BIRTH, "probe", 0), "a promoted birth: passes")
        at_learning = sorted([(BIRTH, "learning", 0), (BIRTH, "learning", 1), (LEARN_ON, "learning", 0),
                              (PREREG_OPEN, "probe", 0)], key=lambda r: EB.send_key(*r))
        self.assertEqual(at_learning, [(PREREG_OPEN, "probe", 0), (LEARN_ON, "learning", 0), (BIRTH, "learning", 0),
                                       (BIRTH, "learning", 1)], "a birth at learning: after every PREREG program")
        self.assertEqual(EB.send_key(BIRTH, "learning", 5), EB.send_key(BIRTH, "learning", 0), "no pass at learning")
        # release 1019e's order (room_key, then the buy's own place) is kept for every tier that does not round-robin
        for program, band in ((BIRTH, "learning"), (LEARN_ON, "learning")):
            self.assertEqual(EB.send_key(program, band, 3)[0::2], EB.room_key(program, band))

    def test_allocate_a_birth_at_probe_round_robins_after_the_prereg_probe_rows_and_before_learning(self):
        wanted = {PREREG_OPEN: [pick("X"), pick("Y")], BIRTH: [pick("Y"), pick("Z")]}
        given, passed = EB.allocate(wanted, {PREREG_OPEN: 2, BIRTH: 2}, {PREREG_OPEN: "probe", BIRTH: "probe"})
        self.assertEqual({k: [p.symbol for p in v] for k, v in given.items()}, {PREREG_OPEN: ["X"], BIRTH: ["Y", "Z"]},
                         "A97 (PL-2): one round-robin group, the PREREG row first in each pass (the birth takes Y in "
                         "the first pass, as a later PREREG Probe row would)")
        self.assertEqual(passed[PREREG_OPEN], {"name_given": 1})
        self.assertEqual(list(given), [PREREG_OPEN, BIRTH])
        # ... and BEFORE a PREREG learning program now; a birth at learning stays after it, as release 1019e gave it
        wanted = {BIRTH: [pick("Q")], LEARN_ON: [pick("Q")]}
        given, _ = EB.allocate(wanted, {BIRTH: 1, LEARN_ON: 1}, {BIRTH: "probe", LEARN_ON: "learning"})
        self.assertEqual({k: [p.symbol for p in v] for k, v in given.items()}, {BIRTH: ["Q"], LEARN_ON: []})
        given, _ = EB.allocate(wanted, {BIRTH: 1, LEARN_ON: 1}, {BIRTH: "learning", LEARN_ON: "learning"})
        self.assertEqual({k: [p.symbol for p in v] for k, v in given.items()}, {LEARN_ON: ["Q"], BIRTH: []})

    # ------------------------------------------------------------------------------------- the reservation (book)
    def synced(self) -> None:
        """DAY's open decision: the session's band sync makes every seating version's instance (the birth's too)."""
        self.case.ready(self.h)
        self.h.tick(9, 15)

    def test_a_births_learning_buy_leaves_the_next_auctions_prereg_probe_its_room(self):
        h = self.h
        h.lane.band(PREREG_CLOSE, "probe")
        seed_history(h, PREREG_CLOSE, (3, 3, 3, 3, 3), at="close")
        self.synced()
        inst = h.book._instance(L.instance_key(BIRTH, 1))
        self.assertEqual((inst.kind, inst.band), ("event", "learning"))
        s = EB.settings()
        cash, risk, note = h.book._event_reserve(inst, TB.DAY.isoformat(), "open", s, D(2000))
        self.assertEqual(cash, 3 * s.share("probe") * D(2000), "min(6, median 3) x Probe's share x E")
        self.assertGreater(risk, 0)
        self.assertIn(PREREG_CLOSE, note)

    def test_a_birth_at_probe_is_reserved_for_and_its_own_buy_leaves_no_room(self):
        """A97 (PL-2): the open's only Probe program is a promoted birth: a close-entry learning buy holds room for it
        (A85, as for a PREREG Probe program), and the birth's own Probe buy sizes less nobody's reservation."""
        h = self.h
        h.lane.band(BIRTH, "probe", version=1)
        seed_history(h, BIRTH, (3, 3, 3, 3, 3), at="open")
        self.synced()
        s = EB.settings()
        on = h.book._instance(L.instance_key(LEARN_ON, 2))
        self.assertEqual(on.band, "learning")
        cash, risk, note = h.book._event_reserve(on, TB.DAY.isoformat(), "close", s, D(2000))
        self.assertEqual(cash, 3 * s.share("probe") * D(2000), "min(6, median 3) x Probe's share x E, for the birth")
        self.assertGreater(risk, 0)
        self.assertIn(BIRTH, note)
        born = h.book._instance(L.instance_key(BIRTH, 1))
        self.assertEqual(born.band, "probe")
        self.assertEqual(h.book._event_reserve(born, TB.DAY.isoformat(), "open", s, D(2000)), (D(0), D(0), ""),
                         "a promoted birth's buy leaves no room")
        h.lane.band(PREREG_CLOSE, "probe")
        seed_history(h, PREREG_CLOSE, (2, 2, 2, 2, 2), at="close")
        h.book._event_sync(0.0, TB.DAY, s, h.book._event_adapter(), h.book._event_lane_store())
        self.assertEqual(h.book._event_reserve(h.book._instance(L.instance_key(BIRTH, 1)), TB.DAY.isoformat(), "open",
                                               s, D(2000)), (D(0), D(0), ""),
                         "nor with a PREREG Probe program at the close: it is a Probe buy (before A97 it sized less "
                         "that program's room)")
        # A birth back at learning leaves the room again, as release 1019f held.
        h.lane.band(BIRTH, "learning", version=1)
        h.book._event_sync(0.0, TB.DAY, s, h.book._event_adapter(), h.book._event_lane_store())
        cash, _, note = h.book._event_reserve(h.book._instance(L.instance_key(BIRTH, 1)), TB.DAY.isoformat(), "open",
                                              s, D(2000))
        self.assertEqual(cash, 2 * s.share("probe") * D(2000), "a birth at learning sizes less a PREREG Probe's room")
        self.assertIn(PREREG_CLOSE, note)

    def test_a_births_buy_cut_by_the_reservation_is_refused_and_its_shadow_keeps_the_event(self):
        self.h.venue.cash = D("250")
        h = short_of_cash(self.h, "250")                  # E $2,000 with $250 of it cash: $200 above the $50 reserve
        h.lane.band(PREREG_CLOSE, "probe")
        seed_history(h, PREREG_CLOSE, (6, 6, 6, 6, 6), at="close")   # R: 6 x Probe's share x $2,000, above $200
        TB.earnings(h.lane, "b-1", TB.CIK2, "BRTH", items=("5.02",))  # 5.02: no PREREG program reads it
        h.lane.intent(self.birth, "8k:b-1", "BRTH", TB.CIK2, TB.DAY, TB.DAY)
        self.case.ready(h)
        h.symbol("BRTH", last=17.0, sd=0.02)
        h.venue.prints[("BRTH", TB.DAY.isoformat(), "open")] = D("17.00")
        h.tick(9, 15)
        h.tick(9, 16)
        [buy] = h.event_intents("buy")
        self.assertEqual((buy["program"], buy["band"], buy["status"]), (BIRTH, "learning", "refused"))
        self.assertIn("A85 holds", buy["why"])
        self.assertEqual(h.bodies(), [], "nothing sent")


if __name__ == "__main__":
    unittest.main()
