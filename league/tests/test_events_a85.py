"""THE CAPTAIN'S A85 (Oct 21, 2026, recorded before the first Probe auction): CASH AT THE AUCTION BINDS PROBE, and its
reading, through the REAL book (league/equity/live.py), the REAL `size_entry` and the real money table in force, on
test_events_book's in-memory auction venue and invented lane store. No figure here is a market's.

The defect (two lenses of a read-only audit of the live House): the book is 1x cash and every buy holds its limit
(1.25 x the previous close); a lot sold in an auction still holds its cash in that same auction; so learning lots bought
at one auction (the overnight rows' close buys) take the NEXT auction's cash from the Probe and Sized programs, and
ROOM's order (Sized > Probe > learning) holds only inside one auction (A83 (2)(b)); and inside one auction the sends go
in the tables' order, so the last Probe row in the tables gets the cash the earlier rows left.

Held here: (1) A LEARNING BUY LEAVES THE NEXT AUCTION ITS ROOM (`EquityBook._event_reserve`, `book.reservation`): the
cash, the invested room and the loss budget a learning buy sizes on are less R, the sum over the live Probe and Sized
programs whose entry is the other auction of min(their room there, the median of their real-money picks at their last
5 decisions) x share(band) x E (x the median open-risk weight of their buys for the budget), less what this auction's
event sales give back by then; (2) R is 0, and learning sizes exactly as before, while no program of the other auction
is at Probe or Sized (a Probe program of the SAME auction is ROOM's already); (3) ROUND-ROBIN inside Sized and inside
Probe, at the decision (`book.allocate`) and at the send (`book.send_key`); learning keeps the tables' order."""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal as D
from unittest import mock

from league.constitution import CONSTITUTION
from league.equity import live as L
from league.equity import schedule as ES
from league.events import book as EB
from league.tests import test_events_book as TB
from league.tests.test_events_book import CIK, DAY, NEXT, PRIOR, EventTest, earnings, iso, key

PROBE_O1 = "EVL-8K-READ-O1"          # an OPEN entry (exits at the same session's close)
LEARN_ON = "EVL-NEWS-READ-ON"        # a CLOSE entry, overnight (exits at the next session's open)


def short_of_cash(h: TB.Harness, cash: str) -> TB.Harness:
    """The account at E $2,000 with only `cash` of it in cash: the rest an invented value held outside the event book
    (the account's equity and last equity carry it; no position, no lot), so E stays $2,000 while the cash binds."""
    base, outside = h.venue.account, D(2000) - D(cash)

    def account() -> dict:
        row = base()
        for k in ("equity", "last_equity"):
            row[k] = str(D(row[k]) + outside)
        return row
    h.venue.account = account
    return h


def pick(symbol: str, program: str = "x") -> EB.Pick:
    return EB.Pick(program, 2, f"8k:{symbol}", symbol, f"c-{symbol}", 3.0, 1e6, D("16"), "t")


def seed_history(h: TB.Harness, program: str, counts, *, at: str = "open", before: dt.date = DAY,
                 weights: dict | None = None) -> list[dt.date]:
    """`program`'s real-money picks at its last decisions of `at` as the book's own decisions record them
    (`eq_event_decisions` summaries, the latest first: `counts[0]` the session before `before`), with a buy of the
    weight `weights[i]` planned at decision i when given. Returns the sessions, the latest first."""
    days, d = [], before
    for n in counts:
        d = ES.previous_session(d)
        days.append(d)
        summary = {"exits": 0, "lane": True, "enabled": True, "bands": True,
                   "programs": {program: {"picks": n, "room": 6} if n is not None else {"picks": None, "room": 0}}}
        h.state.upsert("eq_event_decisions", {"day": d.isoformat(), "at": at, "decided_at": "x", "status": "done",
                                              "summary": json.dumps(summary), "created_at": 0.0}, "day, at")
    for i, w in (weights or {}).items():
        h.state.upsert("eq_event_intents", {
            "iid": 900000 + i, "program": program, "version": 2, "event": f"8k:seed-{i}", "side": "buy", "band": "learning",
            "tif": "opg" if at == "open" else "cls", "otype": "limit", "symbol": f"S{i}", "cik": None,
            "day": days[i].isoformat(), "at": at, "rank_key": None, "adv20": None, "prev_close": "16", "limit_px": "20.00",
            "sigma": None, "hold": 1, "weight": str(w), "exit_day": None, "exit_at": None, "lid": None, "rung": 0,
            "decided_at": "x", "why": None, "created_at": 0.0}, "iid")
    return days


def day_articles(h: TB.Harness, n: int, *, day: dt.date = DAY, prev_close: float = 16.0) -> list[str]:
    """`n` invented day-session articles of `day`, each naming its own listed issuer, scored 2 before the close's
    decision: EVL-NEWS-READ-ON's events at `day`'s close (limit $20.00 at a $16.00 previous close: two whole shares at
    learning's 2% of $2,000)."""
    names = []
    for i in range(n):
        symbol = f"ON{i:02d}"
        h.lane.universe(day, symbol, f"{i + 500:010d}", prev_close)
        h.lane.article(f"d-{i}", symbol, knowable=iso(day, 11, i))
        h.lane.verdict(f"d-{i}", 2, answered=iso(day, 11, 30), news=True)
        h.symbol(symbol, last=20.0)                       # (marked at the print: no mark loss moves E)
        names.append(symbol)
    return names


def next_open_filings(h: TB.Harness, n: int, *, day: dt.date = NEXT, after: dt.date = DAY, prefix: str = "PR",
                      first: int = 700) -> list[str]:
    """`n` invented 8.01 filings accepted after `after`'s close, scored 3: EVL-8K-READ-O1's events at `day`'s open (a
    $20.00 limit: five whole shares at Probe's 5% of $2,000)."""
    names = []
    for i in range(n):
        symbol = f"{prefix}{i:02d}"
        accession, cik = f"p-{day.isoformat()}-{i}", f"{i + first:010d}"
        h.lane.filing(accession, cik, accepted=iso(after, 16, 30 + i), items=("8.01",))
        h.lane.verdict(accession, 3, answered=iso(after, 17, 30))
        h.lane.universe(day, symbol, cik, 16.0)
        h.symbol(symbol, last=20.0)
        names.append(symbol)
    return names


class AtPreregProbeShare(EventTest):
    """Release 1019f's integration: these figures were worked at PREREG-EVL-1's 5% Probe share (`TB.at_prereg_probe_share`);
    the table in force (A86 REVISED's 3.5%) is held by `TheReservationInForce` below."""

    def setUp(self):
        super().setUp()
        TB.at_prereg_probe_share(self)


class TheRoundRobin(AtPreregProbeShare):
    def test_inside_probe_one_pick_a_program_a_pass_and_learning_keeps_the_tables_order(self):
        a, b = "EVL-ERN-READ-O1", "EVL-8K-READ-O1"                 # the tables' order: a before b
        l1, l2 = "EVL-NEWS-READ-O1", "EVL-INS-BUY-O1"
        wanted = {a: [pick("X"), pick("Y")], b: [pick("Y"), pick("Z")], l1: [pick("P"), pick("Q")], l2: [pick("Q")]}
        bands = {a: "probe", b: "probe", l1: "learning", l2: "learning"}
        given, passed = EB.allocate(wanted, {a: 2, b: 2, l1: 2, l2: 2}, bands)
        self.assertEqual({k: [p.symbol for p in v] for k, v in given.items()},
                         {a: ["X"], b: ["Y", "Z"], l1: ["P", "Q"], l2: []},
                         "Probe round-robin: b's first pick Y is given in the first pass before a's second; learning "
                         "in the tables' order: l1 takes Q before l2 is asked")
        self.assertEqual((passed[a], passed[b], passed[l2]), ({"name_given": 1}, {}, {"name_given": 1}))
        self.assertEqual(list(given), [a, b, l1, l2], "ROOM's order")
        # The tables' order (before A85) would have given a both of its names and b only Z.
        old = {k: [p.symbol for p in v] for k, v in EB.allocate(wanted, {a: 2, b: 2}, {a: "learning", b: "learning"})[0]
               .items() if k in (a, b)}
        self.assertEqual(old, {a: ["X", "Y"], b: ["Z"]}, "the same two at learning: the tables' order")

    def test_sized_goes_before_probe_each_round_robin_and_room_and_skips_still_bind(self):
        s1, s2, p1 = "EVL-ERN-REACT-C1", "EVL-NEWS-READ-O1", "EVL-ERN-READ-O1"
        wanted = {p1: [pick("A"), pick("B")], s2: [pick("A"), pick("C"), pick("D")], s1: [pick("C"), pick("E")]}
        skip = lambda program, p: "one_share" if p.symbol == "E" else None  # noqa: E731
        given, passed = EB.allocate(wanted, {s1: 2, s2: 2, p1: 1}, {s1: "sized", s2: "sized", p1: "probe"}, skip)
        self.assertEqual({k: [p.symbol for p in v] for k, v in given.items()},
                         {s1: ["C"], s2: ["A", "D"], p1: ["B"]},
                         "Sized first, one a program a pass (s1 C, s2 A; then s1's E skipped, s2's C given away: D); "
                         "then Probe to its room of one")
        self.assertEqual((passed[s1], passed[s2], passed[p1]), ({"one_share": 1}, {"name_given": 1}, {"name_given": 1}))
        self.assertEqual(list(given), [s1, s2, p1])

    def test_the_sends_go_round_robin_inside_probe_and_sized_and_in_the_tables_order_at_learning(self):
        a, b = "EVL-ERN-READ-O1", "EVL-8K-READ-O1"
        rows = [(a, "probe", 0), (a, "probe", 1), (b, "probe", 0), (b, "probe", 1), (a, "learning", 0),
                (a, "learning", 1), (b, "learning", 0), (b, "sized", 3)]
        order = sorted(rows, key=lambda r: EB.send_key(*r))
        self.assertEqual(order, [(b, "sized", 3), (a, "probe", 0), (b, "probe", 0), (a, "probe", 1), (b, "probe", 1),
                                 (a, "learning", 0), (a, "learning", 1), (b, "learning", 0)])
        self.assertEqual(EB.send_key(a, "learning", 5), EB.send_key(a, "learning", 0), "learning: no pass")

    def test_cash_short_inside_one_auction_goes_one_buy_a_probe_program(self):
        """Two Probe programs of the open, two picks each, cash for two Probe buys: one each (the tables' order of the
        sends would have given the earlier row both)."""
        h = short_of_cash(self.harness(cash="250"), "250")     # $200 available above the $50 reserve: two $100 buys
        earnings(h.lane, "a-1", CIK, "ACME", score=3)                     # EVL-ERN-READ-O1's two (2.02)
        earnings(h.lane, "a-2", "0000000002", "BETA", score=2)
        earnings(h.lane, "o-1", "0000000003", "OTHR", score=3, items=("8.01",))   # EVL-8K-READ-O1's two
        earnings(h.lane, "o-2", "0000000004", "OTHS", score=2, items=("8.01",))
        h.lane.band("EVL-ERN-READ-O1", "probe")
        h.lane.band("EVL-8K-READ-O1", "probe")
        self.ready(h)
        for symbol in ("ACME", "BETA", "OTHR", "OTHS"):
            h.symbol(symbol, last=17.0)
        h.tick(9, 15)
        self.assertEqual(len(h.event_intents("buy")), 4)
        h.tick(9, 16)
        sent = [(b["symbol"], b["qty"]) for b in h.bodies()]
        self.assertEqual(sent, [("ACME", "5"), ("OTHR", "5")], "each Probe program's first pick, in the tables' order")
        refused = {r["symbol"]: r["status"] for r in h.event_intents("buy") if r["symbol"] in ("BETA", "OTHS")}
        self.assertEqual(refused, {"BETA": "refused", "OTHS": "refused"}, "no cash left for either second pick")


class TheReservation(AtPreregProbeShare):
    def overnight(self, *, band: str | None, cash: str = "550", n_on: int = 8, history=(3, 3, 3, 3, 3)):
        """THE TWO-AUCTION CASE: EVL-NEWS-READ-ON at learning buys at DAY's close (n_on picks, $40 each at their limit);
        EVL-8K-READ-O1 at `band` (None: learning) has `history` picks at its last open decisions and three events at
        NEXT's open. The prints are the limits, so a lot holds exactly what its buy reserved."""
        h = short_of_cash(self.harness(cash=cash), cash)
        if band is not None:
            h.lane.band(PROBE_O1, band)
        seed_history(h, PROBE_O1, history)
        names = day_articles(h, n_on)
        for symbol in names:
            h.venue.prints[(symbol, DAY.isoformat(), "close")] = D("20.00")
            h.venue.prints[(symbol, NEXT.isoformat(), "open")] = D("20.00")
        probe = next_open_filings(h, 3)
        for symbol in probe:
            h.venue.prints[(symbol, NEXT.isoformat(), "open")] = D("20.00")
        self.ready(h)
        for hh, mm in ((15, 46), (15, 47), (16, 1), (16, 3)):
            h.tick(hh, mm)
        return h, names, probe

    def test_learning_close_buys_leave_the_next_opens_probe_its_room(self):
        h, names, probe = self.overnight(band="probe")
        on = [r for r in h.event_intents("buy") if r["program"] == LEARN_ON]
        self.assertEqual(len(on), 8, "room: all eight planned (the decision gives slots, the send sizes cash)")
        filled = [r for r in on if r["status"] == "done"]
        self.assertEqual(len(filled), 5, "$500 available less R = min(6, median 3) x 5% x $2,000 = $300: five $40 buys")
        cut = [r for r in on if r["status"] == "refused"]
        self.assertEqual(len(cut), 3)
        self.assertIn("A85 holds $300.00 of cash and invested room", cut[0]["why"])
        self.assertIn(PROBE_O1, cut[0]["why"])
        self.ready(h, NEXT)
        for hh, mm in ((9, 15), (9, 16), (9, 31), (9, 33)):
            h.tick(hh, mm, day=NEXT)
        bought = sorted((b["symbol"], b["qty"]) for b in h.bodies() if b["side"] == "buy" and b["symbol"] in probe)
        self.assertEqual(bought, [(symbol, "5") for symbol in probe],
                         "NEXT's open: $550 less the five $40 lots and the $50 reserve is $300, the Probe program's "
                         "three $100 buys whole")
        self.assertEqual(sorted(b["symbol"] for b in h.bodies() if b["side"] == "sell"),
                         sorted(r["symbol"] for r in filled), "the overnight lots sold at the same open")

    def test_before_a85_the_same_close_took_the_probe_programs_cash(self):
        """The defect, measured on the same rows: with no reservation (the reading switched off) the eight learning buys
        take $320 at DAY's close and NEXT's open leaves the Probe program $180: one whole buy, then a cut one."""
        with mock.patch.object(L.EquityBook, "_event_reserve", lambda self, *a, **k: (D(0), D(0), "")):
            h, names, probe = self.overnight(band="probe")
            self.assertEqual(len([r for r in h.event_intents("buy") if r["program"] == LEARN_ON and r["status"] == "done"]), 8)
            self.ready(h, NEXT)
            for hh, mm in ((9, 15), (9, 16), (9, 31), (9, 33)):
                h.tick(hh, mm, day=NEXT)
        bought = [(b["symbol"], b["qty"]) for b in h.bodies() if b["side"] == "buy" and b["symbol"] in probe]
        self.assertEqual(bought, [(probe[0], "5"), (probe[1], "4")], "$180 available: $100, then $80, then nothing")

    def test_with_no_program_at_probe_r_is_zero_and_learning_sizes_as_today(self):
        for band in (None, "retired"):
            with self.subTest(band=band):
                self.setUp()
                h, names, _ = self.overnight(band=band)
                on = [r for r in h.event_intents("buy") if r["program"] == LEARN_ON]
                self.assertEqual(sorted((r["symbol"], r["status"]) for r in on), [(s, "done") for s in names])
                self.assertEqual({b["qty"] for b in h.bodies() if b["side"] == "buy"}, {"2"}, "2% of E: two shares each")
                self.assertFalse(any("A85" in str(r["why"] or "") for r in h.event_intents()), "no reservation said")
                inst = h.book._instance(key(LEARN_ON))
                self.assertEqual(h.book._event_reserve(inst, DAY.isoformat(), "close", EB.settings(), D(2000)),
                                 (D(0), D(0), ""))

    def test_a_probe_program_of_the_same_auction_reserves_nothing_and_a_probe_buy_is_never_held(self):
        h = self.harness()
        h.lane.band("EVL-ERN-REACT-C1", "probe")          # a CLOSE entry: ROOM's already at DAY's close
        h.lane.band(PROBE_O1, "probe")
        seed_history(h, "EVL-ERN-REACT-C1", (4, 4, 4, 4, 4), at="close")
        seed_history(h, PROBE_O1, (2, 2, 2, 2, 2))
        self.ready(h)
        h.tick(9, 15)                                     # (the instances made at the first decision)
        s = EB.settings()
        learn = h.book._instance(key(LEARN_ON))
        cash, risk, note = h.book._event_reserve(learn, DAY.isoformat(), "close", s, D(2000))
        self.assertEqual((cash, risk), (D("200.00"), D("80.0000")),
                         "the open's EVL-8K-READ-O1 alone: 2 x 5% x $2,000, at the strict 0.40 (no buy weights yet)")
        self.assertNotIn("EVL-ERN-REACT-C1", note)
        probe = h.book._instance(key(PROBE_O1))
        self.assertEqual(h.book._event_reserve(probe, DAY.isoformat(), "close", s, D(2000)), (D(0), D(0), ""),
                         "a Probe buy keeps ROOM's own order")
        o1 = h.book._instance(key("EVL-ERN-READ-O1"))
        self.assertEqual(h.book._event_reserve(o1, DAY.isoformat(), "open", s, D(2000))[:2], (D("400.00"), D("160.0000")),
                         "a learning OPEN buy leaves the close's EVL-ERN-REACT-C1 its 4 x $100")

    def test_r_reads_the_median_of_five_decisions_the_room_and_the_buys_weights(self):
        h = self.harness()
        h.lane.band(PROBE_O1, "probe")
        # The latest first: 1, (a decision that read no picks: passed over), 5, 2, 4, 9; then 9, older than five.
        seed_history(h, PROBE_O1, (1, None, 5, 2, 4, 9, 9), weights={0: "0.10", 2: "0.30", 3: "0.20"})
        self.ready(h)
        h.tick(15, 46)                                    # (the instances made at DAY's close: no open decision of DAY)
        s = EB.settings()
        learn = h.book._instance(key(LEARN_ON))
        cash, risk, _ = h.book._event_reserve(learn, DAY.isoformat(), "close", s, D(2000))
        self.assertEqual((cash, risk), (D("400.00"), D("80.0000")),
                         "median(1, 5, 2, 4, 9) = 4 buys of $100; the median weight of its buys there, 0.20")
        self.assertEqual(EB.reservation([{"band": "probe", "room": 2, "picks": [4, 4], "weights": []}], s, D(2000)),
                         (D("200.00"), D("80.0000")), "never above its room; the strict 0.40 with no weight read")
        self.assertEqual(EB.reservation([{"band": "probe", "room": 6, "picks": [], "weights": []}], s, D(2000))[0],
                         D("600.00"), "no decision yet: its whole room")
        self.assertEqual(EB.reservation([{"band": "sized", "room": 8, "picks": [3, 2], "weights": ["0.1"]}], s, D(2000)),
                         (D("500.000"), D("50.0000")), "Sized: 2.5 x 10% x $2,000")
        self.assertEqual(EB.reservation([{"band": "learning", "room": 8, "picks": [3], "weights": []}], s, D(2000)),
                         (D(0), D(0)), "learning reserves nothing")

    def test_the_cash_this_auctions_sales_give_back_is_counted(self):
        """DAY's open: the Probe program buys three $100 lots, sold at DAY's close. Those sales give its $300 back by
        NEXT's open, so the learning close buys are not held at all (cash $200 above the reserve: five $40 buys), and
        NEXT's open still has the Probe program's $300."""
        h = short_of_cash(self.harness(cash="550"), "550")
        h.lane.band(PROBE_O1, "probe")
        seed_history(h, PROBE_O1, (3, 3, 3, 3))
        today = next_open_filings(h, 3, day=DAY, after=PRIOR, prefix="TD", first=800)
        for symbol in today:
            h.venue.prints[(symbol, DAY.isoformat(), "open")] = D("20.00")
            h.venue.prints[(symbol, DAY.isoformat(), "close")] = D("20.00")
            h.symbol(symbol, last=20.0)
        names = day_articles(h, 8)
        for symbol in names:
            h.venue.prints[(symbol, DAY.isoformat(), "close")] = D("20.00")
            h.venue.prints[(symbol, NEXT.isoformat(), "open")] = D("20.00")
        nxt = next_open_filings(h, 3)
        for symbol in nxt:
            h.venue.prints[(symbol, NEXT.isoformat(), "open")] = D("20.00")
        self.ready(h)
        h.day(DAY, upto=(9, 33))
        self.assertEqual(len([lot for lot in h.lots(open_only=True) if lot.family == PROBE_O1]), 3)
        h.tick(15, 46)
        learn = h.book._instance(key(LEARN_ON))
        self.assertEqual(h.book._event_selling(key(PROBE_O1), DAY.isoformat(), "close"), 3)
        self.assertEqual(h.book._event_reserve(learn, DAY.isoformat(), "close", EB.settings(), D(2000))[:2],
                         (D(0), D(0)), "R $300 less the $300 its own lots sold at this close give back")
        for hh, mm in ((15, 47), (16, 1), (16, 3)):
            h.tick(hh, mm)
        on = [r for r in h.event_intents("buy") if r["program"] == LEARN_ON]
        self.assertEqual(len([r for r in on if r["status"] == "done"]), 5, "the cash there was: $250 less the $50 reserve")
        self.ready(h, NEXT)
        for hh, mm in ((9, 15), (9, 16), (9, 31)):
            h.tick(hh, mm, day=NEXT)
        bought = sorted((b["symbol"], b["qty"]) for b in h.bodies() if b["side"] == "buy" and b["symbol"] in nxt)
        self.assertEqual(bought, [(symbol, "5") for symbol in nxt], "NEXT's open: the Probe program's three, whole")

    def test_the_loss_budget_is_held_too_and_no_wall_moves(self):
        """With the budget the binding wall, the learning buy's budget room is less R x the weight; the walls' rows are
        the constitution's own."""
        h, names, _ = self.overnight(band="probe", cash="5000", n_on=0)
        self.assertEqual(CONSTITUTION["equity_money"]["event"]["max_open"], {"learning": 8, "probe": 6, "sized": 8})
        s = EB.settings()
        learn = h.book._instance(key(LEARN_ON))
        cash, risk, note = h.book._event_reserve(learn, DAY.isoformat(), "close", s, D(2000))
        self.assertEqual((cash, risk), (D("300.00"), D("120.0000")), "3 x $100, at the strict 0.40")
        self.assertIn("$120.00 of the loss budget", note)
        intent = L.Intent(1, key(LEARN_ON), LEARN_ON, 2, DAY.isoformat(), DAY.isoformat(), "close", "buy", "planned",
                          symbol="ONXX")
        h.symbol("ONXX", last=16.0)
        side = {"at": "close", "weight": "0.10", "limit_px": "20.00"}
        h.clock.set(TB.at(DAY, 15, 47))
        with mock.patch.object(L.EquityBook, "_budget_room", lambda self, day: D("124")):
            got = h.book._size_event(intent, learn, side, D("20.00"), DAY.isoformat(), s)
        self.assertEqual(got[0], D(2), "$124 less $120 is $4 of budget: $40 at weight 0.10, two shares")
        self.assertIn("A85 holds", got[1])
        with mock.patch.object(L.EquityBook, "_budget_room", lambda self, day: D("122")):
            got = h.book._size_event(intent, learn, side, D("20.00"), DAY.isoformat(), s)
        self.assertEqual(got[0], D(1), "$2 of budget: $20 at weight 0.10, one share")
        with mock.patch.object(L.EquityBook, "_budget_room", lambda self, day: D("120")):
            got = h.book._size_event(intent, learn, side, D("20.00"), DAY.isoformat(), s)
        self.assertEqual(got[0], D(0), "no budget left above the reservation: skipped, the shadow keeps the event")


if __name__ == "__main__":
    import unittest

    unittest.main()


class TheReservationInForce(EventTest):
    """A85 ON THE TABLE IN FORCE (release 1019f's integration: the captain's A86 REVISED, Probe 3.5% of E with at most 6
    open): the same two auctions as `TheReservation.overnight`, every figure read from `book.settings()`."""

    overnight = TheReservation.overnight

    def test_learning_close_buys_leave_the_next_opens_probe_its_room_at_its_share_in_force(self):
        s = EB.settings()
        self.assertEqual((s.share("probe"), s.max_open("probe")), (D("0.035"), 6), "A86 REVISED")
        h, names, probe = self.overnight(band="probe")
        held = min(s.max_open("probe"), 3) * s.share("probe") * D(2000)          # min(6, median 3) x 3.5% x E = $210
        learning = 2 * D("20.00")                                                 # two shares at the $20.00 limit
        on = [r for r in h.event_intents("buy") if r["program"] == LEARN_ON]
        filled = [r for r in on if r["status"] == "done"]
        self.assertEqual(len(filled), int((D(500) - held) // learning), "$500 available less R, $40 a learning buy")
        cut = [r for r in on if r["status"] == "refused"]
        self.assertEqual(len(cut), len(on) - len(filled))
        self.assertIn(f"A85 holds ${held.quantize(D('0.01'))} of cash and invested room", cut[0]["why"])
        self.ready(h, NEXT)
        for hh, mm in ((9, 15), (9, 16), (9, 31), (9, 33)):
            h.tick(hh, mm, day=NEXT)
        whole = (s.share("probe") * D(2000) / D("20.00")).to_integral_value(rounding="ROUND_DOWN")
        bought = sorted((b["symbol"], b["qty"]) for b in h.bodies() if b["side"] == "buy" and b["symbol"] in probe)
        self.assertEqual(bought, [(symbol, str(whole)) for symbol in probe], "NEXT's open: each Probe buy whole")
