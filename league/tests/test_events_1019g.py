"""RELEASE 1019g's INTEGRATION: release 1019f (`rel/1019f`, PR 593: A84's per-feed fast path, A85's Probe cash
reservation and ROUND_ROBIN_TIERS, A86 REVISED's Probe size, evl_score's wait for the next pass, evl_final, the
alarms) WITH PREREG-EVL-5's rows (`feat/evl-5`, PR 594: rows_5, RAISED_GUARD, part_hold, gap_reader, lane_tickers,
opening_minute, decide-close-evl5, the isolated last part of a close decision). Both were cut from release 1019e; each
class below holds one place where they meet, and each test fails without what it holds: on either parent alone (the
names and rows it reads are the other parent's) or, for the integration's own change, with that change undone (each
says how).

1. ROOM: PREREG-EVL-5's rows come after PREREG-EVL-4's and before R3's births in A85's tiers, its round-robin and its
   send order, at learning size; a learning buy of theirs at D's close leaves the next open's Probe programs A85's
   reservation; and while a PREREG-EVL-5 buy waits for the lane's own close decision to name its program
   (`book.part_hold`), feat/evl-5's `HeldAhead` (its review round) keeps it, from the buys after it in A85's send order,
   A86's Probe size net of A85's reservation, its name wall and its two line orders, and one that fits only without
   that room waits for it; a dry sizing writes no release 1019f record. (Release 1019g's first build had its own form
   of this, `ahead`; the fix round kept feat/evl-5's alone and ported its tests here: each undone, `_event_keep_room`
   keeping nothing, fails.) The held turn (`house.HOLD_LEAD`) never meets release 1019f's screen after the open.
2. The final record: PREREG-EVL-5 section 2's span (from P''s close decision) is judged by A84's per-feed clean reads,
   and its backfill runs through the index that holds X's filings when X is an SEC holiday (1019f's fix round).
3. The alarms: evl_score waits for the next pass on a `decide-close-evl5` catch-up's intents; evl_final judges the three
   rows and reads a close decided without them until their own decision names them; evl_entries names a buy
   `part_hold` held as held by a gate of real opens (`book.PART_WAIT`'s words, the review round's, and a receipt that
   cannot be read), a buy waiting for the room kept by its own sizing's binding; R3's births' own catch-ups
   (`decide-open-births`, `decide-close-births`) wait for the next pass as well.
4. The event kind's 150-order line refuses in ROOM's order with the new rows (PREREG-EVL-5 section 1.3 (a)), whatever the
   minute each buy goes; A80's one re-send carries a PREREG-EVL-5 buy the venue cancelled at once.
5. A86 REVISED's Probe rows leave PREREG-EVL-5's learning rows as frozen (2%, one share at most 5%, eight open); at Probe
   the rows trade A86's smaller size inside PREREG-EVL-1 section 8's envelope, as section 2 states.
6. fix/births-names (PR 596, A95): the one re-run of an empty night asks with the budget SEATING sums with
   PREREG-EVL-5's three (1.5 of 3.0 used), charges its births on top of them and seats them after PREREG-EVL-5's rows
   (at learning `BIRTH_ROOM`; promoted, in their band's tier after its PREREG rows: release 1019h's PL-2).

Through the REAL book (league/equity/live.py), the REAL `size_entry`, the money table in force and the lane's REAL store
(league/tests/test_events_book.py's harness). Every figure is invented; no market price is read."""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import sqlite3
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest import mock

from league.tests.evl6_fakes import on_1019h
from league.constitution import CONSTITUTION
from league.equity import live as L
from league.events import births as BI
from league.events import book as EB
from league.events import calendar as C
from league.events import programs as P
from league.events import screen as SC
from league.events import store as S
from league.ops import evl_health as EV
from league.tests import evl5_world as W
from league.tests import test_events_1019c as T19C
from league.tests import test_events_births as TEB
from league.tests import test_events_births_names as BN
from league.tests import test_events_book as TB
from league.tests import test_events_review_1019b as R19B
from league.tests import test_events_venue_cancel as VC
from league.tests import test_evl_health as TE
from league.tests.test_events_a85 import day_articles, next_open_filings, seed_history, short_of_cash
from league.tests.test_events_births import spec
from league.tests.test_events_screen import decided_summary, final_record

UTC = dt.timezone.utc
NY = C.NY
DAY, PRIOR, NEXT = TB.DAY, TB.PRIOR, TB.NEXT
FIVE = ("EVL-ERN-DROP-ON", "EVL-ERN-UNDER-ON", "EVL-NEWS-NIGHT2-ON")
CONTROL5 = "EVL-CTRL-ERN-UNDER-ON"
DROP = "EVL-ERN-DROP-ON"
FOUR_ON = "EVL-8K-READ-ON"            # PREREG-EVL-4: a close entry, overnight
LEARN_ON = "EVL-NEWS-READ-ON"         # PREREG-EVL-2: a close entry, overnight
PROBE_O1 = "EVL-8K-READ-O1"           # PREREG-EVL-2: an OPEN entry
BIRTH = "EVL-B-ERNREACT-DIP"          # an R3 close-entry birth (a fall to 0.97 with a score >= 1, out at the next open)
REGISTERED_5 = dt.datetime(2026, 10, 21, 21, 26, 21, tzinfo=UTC)


def k5(program: str) -> str:
    """The book's instance key of a PREREG-EVL-5 row (version 1, its seating version)."""
    return L.instance_key(program, 1)


def fall(h: TB.Harness, symbol: str, cik: str, accession: str, *, reaction: float = 0.95, prev: float = 16.0,
         score: int = 1, close_px: str | None = "20.00", next_open: str | None = "20.00") -> None:
    """An earnings 8-K (2.02) accepted after PRIOR's close and scored `score` (1: no earlier row's event at DAY's
    open), its issuer's universe row for DAY at the previous close `prev` (the limit 1.25 x it: $20.00 at $16.00), the
    lane's stored T29 mark at `reaction` x `prev` (EVL-ERN-DROP-ON's event at DAY's close when <= 0.96), the closing
    print at DAY's close and the opening print at NEXT's open (at the limit, so a lot holds what its buy reserved)."""
    h.lane.universe(DAY, symbol, cik, prev)
    h.lane.filing(accession, cik, accepted=TB.iso(PRIOR, 16, 30), items=("2.02",))
    h.lane.verdict(accession, score, answered=TB.iso(PRIOR, 16, 40))
    h.lane.st.db.execute("INSERT INTO marks(symbol, day, label, px, t, source, fetched_at) VALUES(?, ?, '1530', ?, 't', "
                         "'sip-1min', 'x')", (symbol, DAY.isoformat(), round(prev * reaction, 4)))
    h.lane.st.db.execute("INSERT INTO bars(symbol, day, adj, o, h, l, c, v, fetched_at) VALUES(?, ?, 'raw', ?, ?, ?, ?, "
                         "1e6, 'x')", (symbol, PRIOR.isoformat(), prev, prev, prev, prev))
    h.symbol(symbol, last=round(prev * reaction, 4))
    if close_px is not None:
        h.venue.prints[(symbol, DAY.isoformat(), "close")] = D(close_px)
    if next_open is not None:
        h.venue.prints[(symbol, NEXT.isoformat(), "open")] = D(next_open)


def lane_close(h: TB.Harness, *named: str, day: dt.date = DAY) -> None:
    """The lane's own close decision of `day`, finished `ok`, naming `named` (as its receipt names every program it
    decided: league/events/screen.py `names`); PREREG-EVL-5's buys go once it names their program (`book.part_hold`)."""
    rid = h.lane.st.start_receipt(f"decide-close:{day.isoformat()}")
    h.lane.st.finish_receipt(rid, "ok", {name: {"planned": 1} for name in named})


def register_birth(h: TB.Harness, case: unittest.TestCase) -> P.Program:
    """R3's close-entry earnings-reaction birth (league/tests/evl5_world.py's), registered before DAY and loaded."""
    sp = spec(BIRTH, "ern-react", {"react_max": 0.97, "score_min": 1}, rank="reaction", exit_="open")
    h.lane.st.db.execute(
        "INSERT INTO births(id, version, sha, spec, seatable, registered_at, committed_at, received_at, path, "
        "commit_sha, seq, line, why, by, night) VALUES(?, 1, ?, ?, 1, ?, ?, ?, 'docs/births/2026-11-02.jsonl', ?, 0, "
        "'{}', 'x', 'captain', '2026-11-02')",
        (BIRTH, BI.sha(sp), BI.canonical(sp), "2026-11-03T01:00:00Z", "2026-11-03T01:00:00Z", "2026-11-03T01:00:00Z",
         "c" * 40))
    case.addCleanup(P.load_births, None)
    born = next(p for p in P.load_births(h.lane.st) if p.id == BIRTH)     # (with its derived control, a record)
    case.assertEqual((born.id, born.entry_at, born.exit_at, born.can_seat), (BIRTH, "close", "open", True))
    return born


def pick(symbol: str, program: str = "x") -> EB.Pick:
    return EB.Pick(program, 1, f"e:{symbol}", symbol, f"c-{symbol}", 3.0, 1e6, D("16"), "t")


def buys_of(h: TB.Harness, program: str) -> list[dict]:
    return [r for r in h.event_intents("buy") if r["program"] == program]


def sent(h: TB.Harness, symbols=None) -> list[tuple[str, str]]:
    return [(b["symbol"], b["qty"]) for b in h.bodies() if b["side"] == "buy" and (symbols is None or b["symbol"] in
                                                                                   symbols)]


# ============================================================================================ 1. ROOM's order (A85)
@on_1019h
class RoomOrder(unittest.TestCase):
    """A85's tiers, round-robin and send order (`book.room_key`, `send_key`, `allocate`, `reserved_for`, `leaves_room`)
    with PREREG-EVL-5's rows: after PREREG-EVL-4's in the tables' order, before R3's births whatever their bands; inside
    the PREREG Probe and Sized tiers, round-robin with the earlier files' rows. (Fails on rel/1019f, which has no such
    rows, and on feat/evl-5, which has no A85.)"""

    def setUp(self):
        self.addCleanup(P.load_births, None)

    def test_the_tiers(self):
        ids = [p.id for p in EB.seatable()]
        self.assertEqual(ids[9:15], ["EVL-8K-REACT-ON", "EVL-8K-READ-ON", "EVL-NEWSPM-READ-ON", *FIVE])
        for band in ("learning", "probe", "sized"):
            keys = [EB.room_key(p, band) for p in ("EVL-NEWSPM-READ-ON", *FIVE)]
            self.assertEqual(keys, sorted(keys), band)
            self.assertEqual(len(set(keys)), 4, band)
        self.assertEqual([EB.reserved_for(DROP, b) for b in ("sized", "probe", "learning")], [True, True, False])
        self.assertEqual([EB.leaves_room(DROP, b) for b in ("sized", "probe", "learning", "retired")],
                         [False, False, True, False], "a learning buy of theirs leaves the reservation; a Probe one is "
                                                      "reserved for")
        self.assertIn(EB.room_key(DROP, "probe")[0], EB.ROUND_ROBIN_TIERS)
        self.assertNotIn(EB.room_key(DROP, "learning")[0], EB.ROUND_ROBIN_TIERS)
        self.assertEqual(EB.program_of(DROP, 1).prereg, 5)
        self.assertIsNone(EB.program_of(CONTROL5, 1), "the control never seats")

    def test_the_sends_and_the_allocation_with_a_birth(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        st = S.Store(Path(tmp.name) / "events")
        self.addCleanup(st.close)
        sp = spec(BIRTH, "ern-react", {"react_max": 0.97, "score_min": 1}, rank="reaction", exit_="open")
        st.db.execute("INSERT INTO births(id, version, sha, spec, seatable, registered_at, committed_at, received_at, path, "
                      "commit_sha, seq, line, why, by, night) VALUES(?, 1, ?, ?, 1, ?, ?, ?, 'docs/births/x.jsonl', ?, "
                      "0, '{}', 'x', 'captain', '2026-11-02')",
                      (BIRTH, BI.sha(sp), BI.canonical(sp), "2026-11-03T01:00:00Z", "2026-11-03T01:00:00Z",
                       "2026-11-03T01:00:00Z", "c" * 40))
        P.load_births(st)
        self.assertEqual([p.id for p in EB.seatable()][-1], BIRTH)
        rows = [(BIRTH, "learning", 0), ("EVL-NEWS-NIGHT2-ON", "probe", 1), ("EVL-NEWS-NIGHT2-ON", "probe", 0),
                (FOUR_ON, "probe", 0), (FOUR_ON, "probe", 1), (DROP, "learning", 0), (DROP, "learning", 1),
                (LEARN_ON, "learning", 0), (BIRTH, "probe", 0)]
        order = sorted(rows, key=lambda r: EB.send_key(*r))
        self.assertEqual(order, [(FOUR_ON, "probe", 0), ("EVL-NEWS-NIGHT2-ON", "probe", 0), (BIRTH, "probe", 0),
                                 (FOUR_ON, "probe", 1), ("EVL-NEWS-NIGHT2-ON", "probe", 1), (LEARN_ON, "learning", 0),
                                 (DROP, "learning", 0), (DROP, "learning", 1), (BIRTH, "learning", 0)],
                         "Probe round-robin, PREREG-EVL-4's row first in each pass and the promoted birth last in it "
                         "(release 1019h, A97 PL-2: its band's tier after every file's rows of that band); learning in "
                         "the tables' order; a birth at learning after every file's rows")
        wanted = {FOUR_ON: [pick("X"), pick("Y")], "EVL-NEWS-NIGHT2-ON": [pick("Y"), pick("Z")],
                  DROP: [pick("Z"), pick("Q")], BIRTH: [pick("Q"), pick("R")]}
        bands = {FOUR_ON: "probe", "EVL-NEWS-NIGHT2-ON": "probe", DROP: "learning", BIRTH: "probe"}
        given, passed = EB.allocate(wanted, {FOUR_ON: 2, "EVL-NEWS-NIGHT2-ON": 2, DROP: 2, BIRTH: 2}, bands)
        self.assertEqual({k: [p.symbol for p in v] for k, v in given.items()},
                         {FOUR_ON: ["X"], "EVL-NEWS-NIGHT2-ON": ["Y", "Z"], BIRTH: ["Q", "R"], DROP: []},
                         "Probe round-robin (NIGHT2's Y in the first pass, before FOUR_ON's second; the promoted birth "
                         "last in each pass, release 1019h A97 PL-2); DROP at learning after every Probe row")
        self.assertEqual(list(given), [FOUR_ON, "EVL-NEWS-NIGHT2-ON", BIRTH, DROP])
        self.assertEqual((passed[FOUR_ON], passed[DROP], passed[BIRTH]),
                         ({"name_given": 1}, {"name_given": 2}, {}))
        # A birth at learning stays after every PREREG row, as release 1019g gave it.
        bands[BIRTH] = "learning"
        given, passed = EB.allocate(wanted, {FOUR_ON: 2, "EVL-NEWS-NIGHT2-ON": 2, DROP: 2, BIRTH: 2}, bands)
        self.assertEqual({k: [p.symbol for p in v] for k, v in given.items()},
                         {FOUR_ON: ["X"], "EVL-NEWS-NIGHT2-ON": ["Y", "Z"], DROP: ["Q"], BIRTH: ["R"]})
        self.assertEqual(list(given), [FOUR_ON, "EVL-NEWS-NIGHT2-ON", DROP, BIRTH])


@on_1019h
class RoomCash(TB.EventTest):
    """A85's reservation and the order of an auction's sends, through the REAL book, with PREREG-EVL-5's buys."""

    def overnight(self, *, cash: str = "500", n_drop: int = 8, history=(3, 3, 3, 3, 3)) -> tuple[TB.Harness, list, list]:
        """THE TWO-AUCTION CASE OF A85 WITH PREREG-EVL-5's ROWS: EVL-ERN-DROP-ON at learning buys at DAY's close
        (`n_drop` falls of 5%, two shares at the $20.00 limit each, sold at NEXT's open); EVL-8K-READ-O1 at Probe has
        `history` picks at its last open decisions and three events at NEXT's open. E $2,000 with `cash` of it cash."""
        h = short_of_cash(self.harness(cash=cash), cash)
        h.lane.band(PROBE_O1, "probe")
        seed_history(h, PROBE_O1, history)
        names = [f"DR{i:02d}" for i in range(n_drop)]
        for i, symbol in enumerate(names):
            fall(h, symbol, f"{i + 300:010d}", f"dr-{i}")
        probe = next_open_filings(h, 3)
        for symbol in probe:
            h.venue.prints[(symbol, NEXT.isoformat(), "open")] = D("20.00")
        h.lane.decided(DAY, "open")
        lane_close(h, DROP)
        for hh, mm in ((9, 15), (15, 46), (15, 47), (16, 1), (16, 3)):
            h.tick(hh, mm)
        return h, names, probe

    def test_a_learning_drop_buy_leaves_the_next_opens_probe_its_reservation_at_learning_size(self):
        s = EB.settings()
        h, names, probe = self.overnight()
        drop = buys_of(h, DROP)
        self.assertEqual(len(drop), 8, "room: eight learning slots")
        self.assertEqual({(r["band"], r["version"], r["tif"], r["exit_at"]) for r in drop},
                         {("learning", 1, "cls", "open")})
        held = min(s.max_open("probe"), 3) * s.share("probe") * D(2000)               # $210
        filled = [r for r in drop if r["status"] == "done"]
        self.assertEqual(len(filled), int((D(450) - held) // D(40)), "$450 above the reserve less R: six $40 buys")
        self.assertEqual({b["qty"] for b in h.bodies() if b["side"] == "buy"}, {"2"}, "2% of E at the limit: learning")
        cut = [r for r in drop if r["status"] == "refused"]
        self.assertEqual(len(cut), 2)
        self.assertIn(f"A85 holds ${held.quantize(D('0.01'))} of cash and invested room", cut[0]["why"])
        self.assertIn(PROBE_O1, cut[0]["why"])
        self.assertEqual(h.book._exit_reserve(NEXT.isoformat(), event=True), len(filled),
                         "each overnight lot keeps one order of NEXT's line for its exit at that open")
        TB.EventTest.ready(self, h, NEXT)
        for hh, mm in ((9, 15), (9, 16), (9, 31), (9, 33)):
            h.tick(hh, mm, day=NEXT)
        whole = (s.share("probe") * D(2000) / D("20.00")).to_integral_value(rounding="ROUND_DOWN")
        self.assertEqual(sorted(sent(h, probe)), [(symbol, str(whole)) for symbol in probe],
                         "NEXT's open: each Probe buy whole ($500 less six $40 lots and the $50 reserve is $210)")
        self.assertEqual(sorted(b["symbol"] for b in h.bodies() if b["side"] == "sell"),
                         sorted(r["symbol"] for r in filled), "the DROP lots sold at the same open")

    def test_without_the_reservation_the_drop_buys_take_the_probe_programs_cash(self):
        """The same rows with A85 switched off: the eight DROP buys take $320 at DAY's close and NEXT's open leaves the
        Probe program $130: two of its three buys."""
        with mock.patch.object(L.EquityBook, "_event_reserve", lambda self, *a, **k: (D(0), D(0), "")):
            h, names, probe = self.overnight()
            self.assertEqual(len([r for r in buys_of(h, DROP) if r["status"] == "done"]), 8)
            TB.EventTest.ready(self, h, NEXT)
            for hh, mm in ((9, 15), (9, 16), (9, 31), (9, 33)):
                h.tick(hh, mm, day=NEXT)
        self.assertEqual(len(sent(h, probe)), 2)


    # ------------------------------------- feat/evl-5's HeldAhead (its review round) with A85 and A86 (release 1019f)
    def probe_drop(self, h: TB.Harness) -> str:
        """EVL-ERN-DROP-ON at PROBE with one fall (ACME), and EVL-NEWS-READ-ON at learning with one day article: both
        DAY's close entries; DROP's buy is first in A85's send order (Probe before learning)."""
        h.lane.band(DROP, "probe", version=1)
        fall(h, "ACME", TB.CIK, "e-1")
        [news] = day_articles(h, 1)
        h.venue.prints[(news, DAY.isoformat(), "close")] = D("20.00")
        h.lane.decided(DAY, "open")
        return news

    def to_close(self, h: TB.Harness) -> None:
        for hh, mm in ((9, 15), (9, 16), (15, 46), (15, 47)):
            h.tick(hh, mm)

    def record(self, h: TB.Harness, iid: int) -> tuple:
        """Release 1019f's record of a buy's sizing on its side row: (target_usd, binding, sized_usd)."""
        row = h.state.rows("SELECT target_usd, binding, sized_usd FROM eq_event_intents WHERE iid=?", (iid,))[0]
        return row["target_usd"], row["binding"], row["sized_usd"]

    def test_a_learning_buy_behind_a_waiting_probe_drop_buy_leaves_it_a86s_probe_size(self):
        """$80 above the reserve. The book's close decision (15:47) is made before the lane's own (the book waits 60 s
        for it): DROP's Probe buy waits for it (`book.part_hold`) and keeps A86 REVISED's Probe size from the buys after
        it (`HeldAhead`: 3.5% of $2,000 at its $20.00 limit, three shares, $60; five, $100, at feat/evl-5's 5%), so
        EVL-NEWS-READ-ON's learning buy, after it in A85's send order, sends one share on the $20 left. Once the lane's
        decision names DROP, its buy goes whole."""
        h = short_of_cash(self.harness(cash="130"), "130")
        news = self.probe_drop(h)
        self.to_close(h)
        self.assertEqual(sent(h), [(news, "1")], "the learning buy leaves the waiting Probe buy its $60")
        [on] = buys_of(h, LEARN_ON)
        [drop] = buys_of(h, DROP)
        self.assertEqual((drop["band"], drop["status"]), ("probe", "planned"))
        self.assertIn(EB.PART_WAIT, drop["why"])
        order = h.state.rows("SELECT why FROM eq_orders WHERE iid=?", (on["iid"],))[0]["why"]
        self.assertIn("1 shares at learning (sleeve_cash)", order)
        self.assertIn("the sleeve has $20.00 of free cash", order, "$80 less the $60 kept for DROP")
        lane_close(h, DROP, f"{LEARN_ON}@v2")
        h.tick(15, 48)
        self.assertEqual(sent(h), [(news, "1"), ("ACME", "3")], "3.5% of E at the $20.00 limit: whole")

    def test_undone_the_learning_buy_takes_the_probe_buys_cash(self):
        """The defect the money review found, on the same rows, with `HeldAhead` undone (`_event_keep_room` keeps
        nothing): the learning buy sends two shares at 15:47 and DROP's Probe buy, ahead of it in ROOM's order, gets two
        of its three."""
        with mock.patch.object(L.EquityBook, "_event_keep_room", lambda self, *a, **k: None):
            h = short_of_cash(self.harness(cash="130"), "130")
            news = self.probe_drop(h)
            self.to_close(h)
            lane_close(h, DROP, f"{LEARN_ON}@v2")
            h.tick(15, 48)
        self.assertEqual(sent(h), [(news, "2"), ("ACME", "2")])

    def test_a_birth_behind_a_waiting_learning_drop_buy_waits_for_it(self):
        """$40 above the reserve: one learning buy. DROP (ACME, -5%) waits for the lane's decision; the registered
        close-entry birth (BETA, -3.5%: its event, not DROP's), after every file's rows in A85's tiers, fits only
        without the room DROP keeps and WAITS (`HELD_ROOM`, never refused for it); once DROP's buy goes, the birth is
        refused on the cash there is. Undone, the birth takes the cash ROOM gives DROP first."""
        for undone in (False, True):
            with self.subTest(undone=undone), contextlib.ExitStack() as stack:
                self.setUp()
                if undone:
                    stack.enter_context(mock.patch.object(L.EquityBook, "_event_keep_room", lambda self, *a, **k: None))
                h = short_of_cash(self.harness(cash="90"), "90")
                register_birth(h, self)
                fall(h, "ACME", TB.CIK, "e-1")
                fall(h, "BETA", TB.CIK2, "e-2", reaction=0.965)
                h.lane.decided(DAY, "open")
                self.to_close(h)
                if undone:
                    lane_close(h, DROP)
                    h.tick(15, 48)
                    self.assertEqual(sent(h), [("BETA", "2")], "undone: the birth took the cash ROOM gives DROP first")
                    continue
                self.assertEqual(sent(h), [], "the birth waits behind DROP's buy")
                [born] = buys_of(h, BIRTH)
                self.assertEqual((born["symbol"], born["band"], born["status"]), ("BETA", "learning", "planned"))
                self.assertTrue(born["why"].startswith(L.HELD_ROOM), born["why"])
                self.assertIn(L.HELD_AHEAD, born["why"], "report.ROOM_WAIT's words")
                self.assertEqual(EV.unsent_reason(born["why"]), "cash")
                lane_close(h, DROP)
                h.tick(15, 48)
                self.assertEqual(sent(h), [("ACME", "2")])
                [born] = buys_of(h, BIRTH)
                self.assertEqual(born["status"], "refused")
                self.assertNotIn(L.HELD_ROOM, born["why"])

    def test_a_drop_buy_whose_part_failed_frees_what_it_kept(self):
        """The lane's close decision finishes without PREREG-EVL-5's rows (their part failed): DROP's buy is refused
        (never traded, a gate of real opens in evl_entries' words), and the learning buy behind it, which waited for it,
        goes on the cash there is. Undone, the learning buy goes at 15:47 without waiting."""
        for undone in (False, True):
            with self.subTest(undone=undone), contextlib.ExitStack() as stack:
                self.setUp()
                if undone:
                    stack.enter_context(mock.patch.object(L.EquityBook, "_event_keep_room", lambda self, *a, **k: None))
                h = short_of_cash(self.harness(cash="90"), "90")
                news = self.probe_drop(h)
                self.to_close(h)
                if undone:
                    self.assertEqual(sent(h), [(news, "2")])
                    continue
                self.assertEqual(sent(h), [], "$40 above the reserve, all of it kept for DROP's Probe buy")
                [on] = buys_of(h, LEARN_ON)
                self.assertEqual(on["status"], "planned")
                rid = h.lane.st.start_receipt(f"decide-close:{DAY.isoformat()}")
                h.lane.st.finish_receipt(rid, "ok", {f"{LEARN_ON}@v2": {"planned": 1},
                                                     "evl5_error": "PartDeadline: invented"})
                h.tick(15, 48)
                [drop] = buys_of(h, DROP)
                self.assertEqual(drop["status"], "refused")
                self.assertIn("never traded", drop["why"])
                self.assertEqual(EV.unsent_reason(drop["why"]), "blocked", "a gate of real opens")
                self.assertEqual(sent(h), [(news, "2")])

    def test_a_dry_sizing_writes_no_record(self):
        """Release 1019f's record of a buy's sizing (`_event_sized`: target_usd, binding, sized_usd on its side row) is
        the answer of the sizing a send reads; HeldAhead's dry sizings (`_event_keep_room`'s of the waiting buy, and the
        free one of a buy after it) write none. So the waiting DROP buy holds no record until it is sized to send (then
        A86's $70 target and the $60 it sends), and the learning buy after it that waits for the room kept holds its
        own sizing's (cut to no share by cash: $0), never the free sizing's $40."""
        h = short_of_cash(self.harness(cash="100"), "100")
        news = self.probe_drop(h)
        self.to_close(h)
        self.assertEqual(sent(h), [], "$50 above the reserve: DROP keeps $40 (two shares) and NEWS's one share is $20")
        [on] = buys_of(h, LEARN_ON)
        [drop] = buys_of(h, DROP)
        self.assertEqual(self.record(h, drop["iid"]), (None, None, None), "the waiting buy's dry sizing wrote nothing")
        self.assertIn(L.HELD_ROOM, on["why"])
        target, binding, sends = self.record(h, on["iid"])
        self.assertEqual((D(target), binding, D(sends)), (D(40), "cash", D(0)), "the sizing with the room kept")
        lane_close(h, DROP, f"{LEARN_ON}@v2")
        h.tick(15, 48)
        self.assertEqual(sent(h), [("ACME", "2")])
        target, binding, sends = self.record(h, drop["iid"])
        self.assertEqual((D(target), D(sends)), (D(70), D(40)), "A86's target, cut by cash to two shares")

    def test_waiting_drop_buys_keep_what_a85_leaves_them_and_a_birth_after_them_waits(self):
        """A85's reservation with HeldAhead: EVL-ERN-DROP-ON at learning, eight falls at DAY's close, waits at 15:47 for
        the lane's decision; each keeps what a dry sizing gives it net of A85's $210 for NEXT's open Probe program and
        of the buys before it (six two-share buys: $240 of the $450 above the reserve), so the registered birth after
        them (its own -3.5% fall) waits. Once the decision names DROP, six go, two are cut by A85, the birth is refused,
        and NEXT's open sends the Probe program its three whole buys. Undone (`_event_keep_room` keeps nothing), the
        birth takes $40 at 15:47 and DROP gets five."""
        s = EB.settings()
        for undone in (False, True):
            with self.subTest(undone=undone), contextlib.ExitStack() as stack:
                self.setUp()
                if undone:
                    stack.enter_context(mock.patch.object(L.EquityBook, "_event_keep_room", lambda self, *a, **k: None))
                h = short_of_cash(self.harness(cash="500"), "500")
                h.lane.band(PROBE_O1, "probe")
                seed_history(h, PROBE_O1, (3, 3, 3, 3, 3))
                register_birth(h, self)
                for i in range(8):
                    fall(h, f"DR{i:02d}", f"{i + 300:010d}", f"dr-{i}")
                fall(h, "BETA", f"{399:010d}", "b-1", reaction=0.965)
                probe = next_open_filings(h, 3)
                for symbol in probe:
                    h.venue.prints[(symbol, NEXT.isoformat(), "open")] = D("20.00")
                h.lane.decided(DAY, "open")
                self.to_close(h)
                if not undone:
                    self.assertEqual(sent(h), [], "the birth waits behind the eight DROP buys")
                    [born] = buys_of(h, BIRTH)
                    self.assertTrue(born["why"].startswith(L.HELD_ROOM), born["why"])
                lane_close(h, DROP)
                for hh, mm in ((15, 48), (16, 1), (16, 3)):
                    h.tick(hh, mm)
                drop = buys_of(h, DROP)
                filled = [r for r in drop if r["status"] == "done"]
                held = min(s.max_open("probe"), 3) * s.share("probe") * D(2000)               # $210
                self.assertEqual(len(filled), 5 if undone else 6)
                [born] = buys_of(h, BIRTH)
                self.assertEqual(born["status"], "done" if undone else "refused")
                if not undone:
                    cut = [r for r in drop if r["status"] == "refused"]
                    self.assertEqual(len(cut), 2)
                    self.assertIn(f"A85 holds ${held.quantize(D('0.01'))} of cash and invested room", cut[0]["why"])
                TB.EventTest.ready(self, h, NEXT)
                for hh, mm in ((9, 15), (9, 16), (9, 31), (9, 33)):
                    h.tick(hh, mm, day=NEXT)
                whole = (s.share("probe") * D(2000) / D("20.00")).to_integral_value(rounding="ROUND_DOWN")
                self.assertEqual(sorted(sent(h, probe)), [(symbol, str(whole)) for symbol in probe],
                                 "A85's reservation is never consumed by the waiting rows or the birth")


# =========================================================================== 2. the final record (A84 + section 2)
class FinalRecord(unittest.TestCase):
    """PREREG-EVL-5 section 2: FOR THESE ROWS A69's span begins at P''s close decision (two sessions before X); "A84's
    per-feed clean-read rule then applies from before that start through the span's end". So a record pass that missed
    a feed inside that span, with a clean read of the feed on each side of it within 15 minutes, is a missing read, not
    a broken span (A84); a feed with no clean read for longer breaks only the span that holds it, and the why names the
    feed. (On feat/evl-5 alone the passes are read as A69 first wrote it, every pass whole: the first test fails there;
    on rel/1019f there are no such rows.)"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(P.load_births, None)
        self.w = W.World(Path(self.tmp.name) / "lane")
        self.addCleanup(self.w.close)
        self.st = self.w.st
        self.x = C.session(self.st, W.D_DAY)                 # X: Tue Oct 27; P Mon Oct 26; P' Fri Oct 23
        self.after = C.nth(self.st, W.D_DAY, 2)
        rid = self.st.start_receipt(f"decide-open:{self.after.day}", now=self.after.open_decide)
        self.st.finish_receipt(rid, "ok", {}, now=self.after.open_decide)
        for day in W.W4.weekdays(W.F_DAY, W.D_DAY):
            self.st.set_meta(f"evl:backfill:{day.isoformat()}", "done")
        self.now = W.et(W.N_DAY, 12, 0)

    def passes(self, spoil) -> None:
        """Record passes every 5 minutes from 10 minutes before P''s close decision through 5 minutes after the open
        decision of the session after X; `spoil(t)` the parts a pass at `t` missed (None: a clean pass)."""
        clean = {"8-K": {"new": 0}, "4": {"new": 0}, "news": {"stored": 0}}
        t = C.session(self.st, W.F_DAY).close_decide - dt.timedelta(minutes=10)
        while t <= self.after.open_decide + dt.timedelta(minutes=5):
            rid = self.st.start_receipt("record", now=t)
            self.st.finish_receipt(rid, "ok", clean | (spoil(t) or {}), now=t)
            t += dt.timedelta(minutes=5)

    def block(self, program: str, first: dt.date) -> str | None:
        return SC._fast_block(self.st, P.BY_ID[program], first, self.x, None, self.now, {})

    def test_one_missed_read_a_feed_inside_their_early_span_is_a_missing_read(self):
        """An 8-K timeout at Fri 17:00 ET (inside this file's span, before PREREG-EVL-4's 09:00 ET Monday start) and a
        Form 4 error at Mon 12:00 ET (inside both): each feed is read cleanly again five minutes later."""
        def spoil(t):
            if W.et(W.F_DAY, 17, 0) <= t < W.et(W.F_DAY, 17, 5):       # (the pass of 17:01 ET)
                return {"8-K": {"error": "timeout"}}
            if W.et(W.P_DAY, 12, 0) <= t < W.et(W.P_DAY, 12, 5):       # (the pass of 12:01 ET)
                return {"4": {"error": "timeout"}}
            return None
        self.passes(spoil)
        self.assertIsNone(self.block(DROP, REGISTERED_5.date()))
        self.assertIsNone(self.block("EVL-NEWS-NIGHT2-ON", REGISTERED_5.date()))
        self.assertIsNone(self.block(FOUR_ON, dt.date(2026, 10, 19)))
        self.assertIsNone(SC._fast_passes(self.st, C.session(self.st, W.F_DAY).close_decide, self.after.open_decide, {}),
                          "A84's reading: each feed's clean reads at most 15 minutes apart")

    def test_a_feed_without_a_clean_read_for_20_minutes_in_their_early_span_holds_them_alone(self):
        """The news read cut short Fri 18:00-18:15 ET (the passes of 18:01, 18:06 and 18:11: 20 minutes between clean
        reads): this file's span holds it and names the news feed; PREREG-EVL-4's span (from Monday 09:00 ET) does
        not."""
        self.passes(lambda t: {"news": {"stored": 0, "cut": True}}
                    if W.et(W.F_DAY, 18, 0) <= t <= W.et(W.F_DAY, 18, 15) else None)
        why = self.block(DROP, REGISTERED_5.date())
        self.assertIsNotNone(why)
        self.assertIn("no clean read of the news feed", why)
        self.assertIn("cut its news read short", why)
        self.assertIn("(3 passes missed it)", why)
        self.assertIsNone(self.block(FOUR_ON, dt.date(2026, 10, 19)))


    def test_an_sec_holiday_close_is_final_for_them_only_after_the_index_that_holds_its_eve(self):
        """Release 1019f's fix round (an SEC holiday's close is final only after the index that holds its eve,
        `screen.index_through`) on PREREG-EVL-5's span: X = Wed Nov 11, 2026 (Veterans Day: NYSE trades, EDGAR is
        closed), P' = Mon Nov 9. Its backfill through X is done but Thu Nov 12's (which holds Nov 10's evening 8-Ks)
        is not: the new rows wait for it, as every program does; once it is done the close is final for them. (With
        feat/evl-5's own loop, through X alone, the first assertion fails.)"""
        x, after = C.session(self.st, dt.date(2026, 11, 11)), C.nth(self.st, dt.date(2026, 11, 11), 2)
        self.assertEqual(after.day, dt.date(2026, 11, 12))
        rid = self.st.start_receipt(f"decide-open:{after.day}", now=after.open_decide)
        self.st.finish_receipt(rid, "ok", {}, now=after.open_decide)
        for day in (dt.date(2026, 11, 9), dt.date(2026, 11, 10), dt.date(2026, 11, 11)):
            self.st.set_meta(f"evl:backfill:{day.isoformat()}", "done")
        clean = {"8-K": {"new": 0}, "4": {"new": 0}, "news": {"stored": 0}}
        t = C.session(self.st, dt.date(2026, 11, 9)).close_decide - dt.timedelta(minutes=10)
        while t <= after.open_decide + dt.timedelta(minutes=5):
            rid = self.st.start_receipt("record", now=t)
            self.st.finish_receipt(rid, "ok", clean, now=t)
            t += dt.timedelta(minutes=5)
        now = W.et(dt.date(2026, 11, 12), 12, 0)
        why = SC._fast_block(self.st, P.BY_ID[DROP], REGISTERED_5.date(), x, None, now, {})
        self.assertEqual(why, "the daily-index backfill of 2026-11-12 has not run (its index holds the 8-Ks of "
                              "2026-11-10's evening: 2026-11-11 is an SEC holiday)")
        self.st.set_meta("evl:backfill:2026-11-12", "done")
        self.assertIsNone(SC._fast_block(self.st, P.BY_ID[DROP], REGISTERED_5.date(), x, None, now, {}))


# ================================================================================================= 3. the alarms
class ScoreWaits(TE.Lane):
    """evl_score (release 1019f): an intent a decision WROTE AFTER the night's last score pass started waits for the next
    pass. PREREG-EVL-5's rows decided by themselves (`decide-close-evl5:<day>`, the record before the release, or a close
    whose part for them failed) are such a catch-up: their intents, due at the next open, are never flagged by the night
    they were written after. (Fails on feat/evl-5: no `written_after`.)"""

    THU, FRI = dt.date(2026, 10, 22), dt.date(2026, 10, 23)

    def intent5(self, program: str, event: str, *, version: int = 1) -> None:
        self.st.db.execute("INSERT INTO intents(program, version, event, symbol, cik, decided_at, entry_day, entry_at, "
                           "exit_day, exit_at, mode, status) VALUES(?, ?, ?, 'XYZ', '0000000009', ?, ?, 'close', ?, "
                           "'open', 'shadow', 'planned')",
                           (program, version, event, TE.iso(TE.et(self.THU, "15:46")), self.THU.isoformat(),
                            self.FRI.isoformat()))

    def test_a_decide_close_evl5_catch_up_after_the_nights_pass_is_no_stall(self):
        self.intent5(DROP, "8k:late")
        self.intent5(CONTROL5, "8k:late")
        now = TE.et(self.FRI, "23:30")
        self.receipt("score", TE.et(self.FRI, "20:30"), status="ok", summary={"day": self.FRI.isoformat(),
                                                                              "complete": True})
        self.assertTrue(self.check("evl_score", now)["stalled"], "before the catch-up's receipt: they stand")
        self.receipt(f"decide-{SC.FIVE_KIND}:{self.THU.isoformat()}", TE.et(self.FRI, "21:05"),
                     summary={DROP: {"planned": 1, "skipped": 0, "known": 0},
                              CONTROL5: {"planned": 1, "skipped": 0, "known": 0}})
        check = self.check("evl_score", now)
        self.assertFalse(check["stalled"], check["what"])
        self.assertEqual((check["numbers"]["open_due"], check["numbers"]["after_last_pass"]), (0, 2))
        self.assertIn("2 a decision wrote after the night's last score pass", check["what"])
        self.assertEqual(EV.written_after({"decide": {f"decide-{SC.FIVE_KIND}:{self.THU.isoformat()}": [
            {"started_at": TE.iso(TE.et(self.FRI, "21:05")), "summary": json.dumps({DROP: {"planned": 1}})}]}},
            TE.et(self.FRI, "20:30")), {(DROP, "close", self.THU.isoformat())})

    def test_the_births_own_catch_ups_wait_for_the_next_pass_too(self):
        """R3's births decided by themselves (`decide-open-births:<day>`, `decide-close-births:<day>`: a decision made
        without the registered births, A95's re-run of an empty night among them) are the same kind of catch-up: what
        they wrote after the night's pass waits for the next one; what they wrote before it stands."""
        since = TE.et(self.FRI, "20:30")
        after, before = TE.iso(TE.et(self.FRI, "21:20")), TE.iso(TE.et(self.FRI, "20:00"))
        got = EV.written_after({"decide": {
            f"decide-open-births:{self.FRI.isoformat()}": [
                {"started_at": after, "summary": json.dumps({"EVL-B-8K-502": {"planned": 2, "known": 0}})}],
            f"decide-close-births:{self.THU.isoformat()}": [
                {"started_at": after, "summary": json.dumps({"EVL-B-ERNREACT-DIP": {"planned": 1}})},
                {"started_at": before, "summary": json.dumps({"EVL-B-OLD": {"planned": 1}})}]}}, since)
        self.assertEqual(got, {("EVL-B-8K-502", "open", self.FRI.isoformat()),
                               ("EVL-B-ERNREACT-DIP", "close", self.THU.isoformat())})

    def test_a_catch_up_before_the_pass_stands(self):
        self.intent5(DROP, "8k:old")
        self.receipt(f"decide-{SC.FIVE_KIND}:{self.THU.isoformat()}", TE.et(self.FRI, "20:00"),
                     summary={DROP: {"planned": 1}})
        self.receipt("score", TE.et(self.FRI, "20:30"), status="ok", summary={"day": self.FRI.isoformat()})
        check = self.check("evl_score", TE.et(self.FRI, "23:30"))
        self.assertTrue(check["stalled"])
        self.assertEqual(check["numbers"]["open_due"], 1)


class FinalAlarm(unittest.TestCase):
    """evl_final (A84, release 1019f) judges PREREG-EVL-5's three rows from their registration (the stall job's own
    process, read-only) and reads a close a release decided without them (or whose part for them failed) as not made
    for them until their own decision (`decide-close-evl5`) names them. (Fails on rel/1019f: no such rows; on
    feat/evl-5: no evl_final.)"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(P.load_births, None)
        self.root = Path(self.tmp.name) / "state"
        self.st = S.Store(self.root / "events")
        self.addCleanup(self.st.close)
        C.refresh(self.st, R19B.CalendarGateway({}), dt.date(2026, 10, 1), dt.date(2027, 3, 31))
        self.days = [s.day for s in C.sessions(self.st, dt.date(2026, 10, 20), dt.date(2027, 3, 31))]
        self.now = final_record(self.st, self.days[8])                 # 23:00 ET of days[8] (Oct 30)
        T19C.TheFastPath.passes(self, W.et(self.days[0], 8), W.et(self.days[8], 12), every=dt.timedelta(minutes=2))

    def passes(self, start, end, every):
        T19C.TheFastPath.passes(self, start, end, every=every)

    def check(self) -> dict:
        errors: list[str] = []
        out = EV.checks({"config": {"events": {"enabled": True}}, "settings": {}}, self.root, self.now.timestamp(),
                        errors=errors)
        self.assertEqual(errors, [])
        return out["evl_final"]

    def test_the_three_are_judged_and_a_close_made_without_them_holds_them_until_their_own_decision(self):
        lags = {r["program"]: r for r in EV.final_lags(self.root, self.now.timestamp())}
        self.assertTrue(set(FIVE) <= set(lags), sorted(lags))
        self.assertNotIn(CONTROL5, lags, "the control never seats")
        self.assertFalse(self.check()["stalled"])
        thu = self.days[2]                                            # Thu Oct 22: after the registration
        self.assertEqual(thu, dt.date(2026, 10, 22))
        # a release without their rows decides Thursday's close again (its latest receipt names none of them)
        rid = self.st.start_receipt(f"decide-close:{thu.isoformat()}")
        self.st.finish_receipt(rid, "ok", {k: v for k, v in decided_summary("close").items()
                                           if k not in FIVE and k != CONTROL5})
        check = self.check()
        self.assertTrue(check["stalled"], check["what"])
        self.assertEqual(check["numbers"]["program"], DROP.lower(), "the first of the lagging, in the table's order")
        self.assertEqual(check["numbers"]["lagging"], 3, "the three alone")
        self.assertIn(f"the close decision of {thu.isoformat()} is made without its rows", check["what"])
        self.assertEqual(SC.made_without(self.st, self.days[8], prereg=5), {thu: False})
        rid = self.st.start_receipt(f"decide-{SC.FIVE_KIND}:{thu.isoformat()}")
        self.st.finish_receipt(rid, "ok", {k: {"planned": 0} for k in (*FIVE, CONTROL5)})
        check = self.check()
        self.assertFalse(check["stalled"], check["what"])


class EntriesWord(unittest.TestCase):
    """evl_entries (release 1019f) names why a planned buy never reached the venue by the book's own words; a
    PREREG-EVL-5 buy `part_hold` held (it waited for the lane's own close decision, or that decision finished without
    its rows: never traded) is held by a gate of real opens, as section 1.3 states it (release 1019g's word: "another
    reason" before)."""

    def test_the_words(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        st = S.Store(Path(tmp.name) / "events")
        self.addCleanup(st.close)
        lane = EB.Lane(Path(tmp.name) / "events" / S.DB_NAME)
        self.addCleanup(lane.close)
        broken = mock.Mock(db=mock.Mock(execute=mock.Mock(side_effect=sqlite3.OperationalError("invented"))))
        holds = [EB.part_hold(None, DROP, 1, DAY), EB.part_hold(lane, DROP, 1, DAY), EB.part_hold(broken, DROP, 1, DAY)]
        self.assertIn("cannot be read", holds[-1][1])
        rid = st.start_receipt(f"decide-close:{DAY.isoformat()}")
        st.finish_receipt(rid, "ok", {"evl5_error": "PartDeadline: invented"})
        holds.append(EB.part_hold(lane, DROP, 1, DAY))
        self.assertEqual([h[0] for h in holds], ["wait", "wait", "wait", "never"])
        for kind, why in holds:
            self.assertEqual(EV.unsent_reason(f"not filled at the close auction (never sent: {why})"), "blocked", why)
            self.assertEqual(EV.unsent_reason(why), "blocked", why)
            self.assertEqual(EV.unsent_reason(f"{L.A80_HELD}{why}"), "blocked", why)
        self.assertEqual(EV.PART_WAIT_WORDS, EB.PART_WAIT.lower(), "feat/evl-5's review round's words")
        # (a later buy that waits for the room kept for them is named by its own sizing's binding; the line's refusal
        # with their slots kept is the line)
        self.assertEqual(EV.unsent_reason(f"{L.HELD_ROOM} (1 {L.HELD_AHEAD}): no whole share fits (cash): invented"),
                         "cash")
        self.assertEqual(EV.unsent_reason("the event kind's day order count: 148 of 150 sent, 1 kept for exiting its "
                                          f"lots and buys held and this one, 2 for the 1 buys ahead of it that "
                                          f"{L.HELD_AHEAD}"), "order_line")


# ================================================================================ 4. the 150-order line and A80
@on_1019h
class TheLine(TB.EventTest):
    """The event kind's line of 150 orders a day (A74 (7), A78) "refuses entries in ROOM's order, so on a day that would
    need more, this file's rows are refused first among the PREREG rows" (PREREG-EVL-5 section 1.3 (a)), and R3's births
    after them; an exit is never stopped by it."""

    def filler(self, h: TB.Harness, n: int) -> None:
        """`n` other event orders of the day (expired: no lot, no working order), as test_events_1019c's heavy day."""
        [inst] = [r["id"] for r in h.state.rows("SELECT id FROM eq_instances WHERE lane=? AND family='EVL-INS-BUY-O1'",
                                                (L.EVENT_LANE,))]
        with h.state.transaction():
            for i in range(n):
                h.state.execute("INSERT INTO eq_orders(eid, client_id, instance, family, side, symbol, class, at, qty, "
                                "limit_px, collar_bp, status, placed_at, day, updated_at) VALUES(?, ?, ?, 'f', 'sell', "
                                "'ZZZ', 'stock', 'open', '1', '1', 0, 'expired', 0, ?, 0)",
                                (900000 + i, f"heavy-{i}", inst, DAY.isoformat()))

    def test_the_line_refuses_preregevl5s_rows_first_among_the_prereg_rows(self):
        """148 orders sent: EVL-NEWS-READ-ON (PREREG-EVL-2) takes the line's last room (148 + 1 + its own exit), and
        EVL-ERN-DROP-ON is refused by the event kind's day order count."""
        h = self.harness()
        [news] = day_articles(h, 1)
        h.venue.prints[(news, DAY.isoformat(), "close")] = D("20.00")
        fall(h, "ACME", TB.CIK, "e-1")
        h.lane.decided(DAY, "open")
        lane_close(h, DROP, f"{LEARN_ON}@v2")
        h.tick(9, 15)
        self.filler(h, 148)
        for hh, mm in ((15, 46), (15, 47), (15, 48)):
            h.tick(hh, mm)
        self.assertEqual(sent(h), [(news, "2")])
        [drop] = buys_of(h, DROP)
        self.assertIn("the event kind's day order count: 149 of 150 sent", drop["why"])
        self.assertEqual(L.event_orders_today(h.state.rows, DAY.isoformat()), 149)


    def test_a_birth_behind_a_waiting_drop_buy_keeps_the_line_for_it(self):
        """148 orders sent, DROP waiting for the lane's decision at 15:47: the birth after it keeps DROP's send and exit
        (148 + 1 + 1 + 2 > 150: `HeldAhead.orders`) and waits; at 15:48 DROP takes the line's last room and the birth is
        held by the line. Undone (`_event_keep_room` keeps nothing), the birth takes it at 15:47 and DROP is held by
        the line it took."""
        for undone in (False, True):
            with self.subTest(undone=undone), contextlib.ExitStack() as stack:
                self.setUp()
                if undone:
                    stack.enter_context(mock.patch.object(L.EquityBook, "_event_keep_room", lambda self, *a, **k: None))
                h = self.harness()
                register_birth(h, self)
                fall(h, "ACME", TB.CIK, "e-1")
                fall(h, "BETA", TB.CIK2, "e-2", reaction=0.965)
                h.lane.decided(DAY, "open")
                h.tick(9, 15)
                self.filler(h, 148)
                for hh, mm in ((15, 46), (15, 47)):
                    h.tick(hh, mm)
                if not undone:
                    self.assertEqual(sent(h), [])
                    [born] = buys_of(h, BIRTH)
                    self.assertIn(f"2 for the 1 buys ahead of it that {L.HELD_AHEAD}", born["why"])
                lane_close(h, DROP)
                h.tick(15, 48)
                if undone:
                    self.assertEqual(sent(h), [("BETA", "2")])
                    [drop] = buys_of(h, DROP)
                    self.assertIn("the event kind's day order count: 149 of 150 sent", drop["why"])
                    continue
                self.assertEqual(sent(h), [("ACME", "2")])
                [born] = buys_of(h, BIRTH)
                self.assertIn("the event kind's day order count: 149 of 150 sent", born["why"])
                self.assertIsNone(h.book._count_refusal(DAY.isoformat(), exit_=True), "an exit still goes at the line")


@on_1019h
class TheResend(VC.VenueCancelTest):
    """A80 (release 1019e) with PREREG-EVL-5's rows: a DROP buy at D's close the venue cancelled at once goes again ONCE
    through every gate (the lane's close decision names its program, so `part_hold` lets it go again), the same shape
    under a new client id, and the line counts both orders."""

    def test_a_drop_buy_the_venue_cancelled_at_once_goes_again_once(self):
        h = self.harness()
        fall(h, "ACME", TB.CIK, "e-1", close_px="17.00")
        h.lane.decided(DAY, "open")
        lane_close(h, DROP)
        h.venue.venue_cancels = [0.005]
        for hh, mm in ((9, 15), (15, 46), (15, 47)):
            h.tick(hh, mm)
        [first] = h.bodies()
        out = h.tick(15, 48)
        self.assertEqual(out.get("venue_cancel_resends"), 1)
        again, resent = h.bodies()
        self.assertEqual(self.shape(resent), self.shape(first))
        self.assertEqual(self.shape(first), {"symbol": "ACME", "qty": "2", "side": "buy", "type": "limit",
                                             "limit_price": "20.00", "time_in_force": "cls"})
        self.assertNotEqual(resent["client_order_id"], first["client_order_id"])
        self.assertEqual(L.event_orders_today(h.state.rows, DAY.isoformat()), 2, "both count on the event kind's line")
        h.tick(15, 49)
        self.assertEqual(len(h.bodies()), 2, "once")
        for hh, mm in ((16, 1), (16, 3)):
            h.tick(hh, mm)
        [buy] = self.buys(h)
        self.assertEqual((buy["program"], buy["status"]), (DROP, "done"))
        self.assertIn("A80's one re-send", buy["why"])

    def buys(self, h):
        return h.event_intents("buy")


class TheBirthsRerunWithTheNewRows(BN.Replay):
    """fix/births-names (A95) on the merged tree: the one re-run of Oct 21's empty night (release 1019e's receipt, its
    six refused specs) asks under the new prompt with the budget as SEATING sums it WITH PREREG-EVL-5's three (1.5 of
    3.0 used, three seatable births left that night), charges its births on top of them, names none as a PREREG row,
    and seats them in ROOM after PREREG-EVL-5's rows (at learning `BIRTH_ROOM`; promoted, after the band's PREREG rows in
    its tier: release 1019h's PL-2). (Fails on fix/births-names
    alone: 1.2 used there; and on rel/1019g before the merge: no re-run.)"""

    docs = BN.TheRerunOfAnEmptyNight.docs
    first_night = BN.TheRerunOfAnEmptyNight.first_night

    def test_the_rerun_charges_on_top_of_preregevl5_and_its_births_come_after_its_rows(self):
        from league.events import verdicts as V

        st = self.s.st
        self.first_night()
        self.assertEqual(SC.expected_false_passes(st)["expected"], 1.95,
                         "the fifteen seatable versions (release 1019i: PREREG-EVL-6's, 0.13 each)")
        now = dt.datetime(2026, 10, 22, 11, 30, 5, tzinfo=UTC)
        due = BI.rerun_due(st, now)
        self.assertEqual(due["night"], "2026-10-21")
        route, _ = self.docs("2026-10-22T11:30:09Z")
        gw = TEB.FakeArchitect(json.dumps({"specs": BN.SIX}), docs=route)
        out = BI.night(st, gw, today=BN.NIGHT, now=lambda: now, rerun=due)
        self.assertEqual(out["_status"], "ok", out)
        [(_, body, _)] = [c for c in gw.calls if c[0] == V.PATH]
        self.assertIn("1.95 of 3.90 used", body["messages"][0]["content"])
        self.assertEqual(out["accepted"], ["EVL-B-ERN-NEGATIVE-O1", "EVL-B-NEWS-EARLY-MORNING-O1"])
        self.assertEqual(SC.expected_false_passes(st)["expected"], 2.21,
                         "0.13 each (registered before REGISTERED_AT_6: each seats at its PREREG-EVL-6 version 2)")
        self.assertEqual(BI.budget(st, BN.NIGHT)["seatable_left_tonight"], 1, "the night's three")
        prereg = {p.id for p in P.PROGRAMS if p.spec is None}
        self.assertFalse(set(out["accepted"]) & prereg)
        self.assertEqual({BI.canonical_name(i) for i in FIVE} & prereg, set(), "a PREREG-EVL-5 id named is a new name")
        for born in out["accepted"]:
            for band in ("learning", "probe", "sized"):
                self.assertGreater(EB.room_key(born, band), max(EB.room_key(f, band) for f in FIVE), (born, band))
            # (release 1019h, the captain's A97 PL-2: a birth at learning after every PREREG row, `BIRTH_ROOM`; a
            # promoted one in its band's tier, after that band's PREREG rows, PREREG-EVL-5's included)
            self.assertEqual(EB.room_key(born, "learning")[0], EB.BIRTH_ROOM)
            self.assertGreater(EB.room_key(born, "learning"), max(EB.room_key(f, "learning") for f in P.PROGRAMS
                                                                  if f.spec is None and f.can_seat))
            for band in ("probe", "sized"):
                self.assertEqual(EB.room_key(born, band)[0], EB.PRIORITY[band], (born, band))
                self.assertLess(EB.room_key(born, band), min(EB.room_key(f, "learning") for f in FIVE), (born, band))
            self.assertGreater(EB.order_of(born), max(EB.order_of(f) for f in FIVE))


class TheHeldTurn(unittest.TestCase):
    """feat/evl-5's held turn for the live close decision (league/events/house.py `HOLD_LEAD`: from 150 s before it a
    turn keeps going, each task bounded to end before the decision) with release 1019f's screen after the open
    (`screen-open`: CPU only, UNBOUNDED, never started within `SCREEN_CLEAR` of a decision): the screen can never start
    inside the hold, so every task the held turn runs is bounded. (Fails on rel/1019f, which has no hold, and on
    feat/evl-5, which has no screen after the open.)"""

    def test_the_screen_after_the_open_never_starts_inside_the_hold(self):
        from league.events import house as H

        self.assertIn(H.SCREEN_OPEN_JOB, H.SCREEN_JOBS)
        self.assertLess(H.HOLD_LEAD, H.SCREEN_CLEAR)
        self.assertGreater(H.DECISION_MARGIN, 0)


# ===================================================================================== 5. A86 and the new rows
@on_1019h
class ProbeSize(TB.EventTest):
    """A86 REVISED (`position_share.probe` 0.035, `one_share_max.probe` 0.05; release 1019f) moves the Probe band only:
    PREREG-EVL-5's rows at learning trade as frozen (a target of 2% of E, one share when that rounds to none and one
    share at the limit is at most 5% of E, at most eight open); at Probe they trade A86's smaller size inside PREREG-EVL-1
    section 8's envelope (5%, six open), as section 2 states. (The learning rows are release 1019e's; fails on feat/evl-5,
    which has no Probe one-share row, and on rel/1019f, which has no such rows.)"""

    def test_the_rows(self):
        e = CONSTITUTION["equity_money"]["event"]
        self.assertEqual((e["position_share"]["learning"], e["one_share_max"]["learning"], e["max_open"]["learning"]),
                         ("0.02", "0.05", 8), "PREREG-EVL-3 section 2's learning band, as frozen")
        self.assertEqual((e["position_share"]["probe"], e["one_share_max"]["probe"], e["max_open"]["probe"]),
                         ("0.035", "0.05", 6))
        s = EB.settings()
        self.assertEqual((s.share("learning"), s.one_share_cap("learning"), s.max_open("learning")),
                         (D("0.02"), D("0.05"), 8))

    def skipped(self, h: TB.Harness) -> dict:
        """What DAY's close decision of the book passed DROP's picks over for (its summary's `skipped`)."""
        row = h.state.rows("SELECT summary FROM eq_event_decisions WHERE day=? AND at='close'", (DAY.isoformat(),))[0]
        return json.loads(row["summary"])["programs"][DROP].get("skipped") or {}

    def one(self, *, band: str, prev: float) -> tuple[TB.Harness, list]:
        h = self.harness()
        if band != "learning":
            h.lane.band(DROP, band, version=1)
        fall(h, "ACME", TB.CIK, "e-1", prev=prev, close_px=None, next_open=None)
        h.venue.prints[("ACME", DAY.isoformat(), "close")] = EB.limit_price(D(str(prev)), D("1.25"))
        h.lane.decided(DAY, "open")
        lane_close(h, DROP)
        for hh, mm in ((9, 15), (15, 46), (15, 47)):
            h.tick(hh, mm)
        return h, buys_of(h, DROP)

    def test_learning_two_percent_and_one_share_to_five(self):
        for prev, qty in ((16.0, "2"), (64.0, "1"), (76.0, "1"), (80.8, None)):
            with self.subTest(prev=prev):
                self.setUp()
                h, buys = self.one(band="learning", prev=prev)
                if qty is None:
                    self.assertEqual((sent(h), buys), ([], []), "one share at $101.00 is above 5% of E ($100.00)")
                    self.assertTrue(self.skipped(h), "the decision passed the pick over: no whole share fits by price")
                else:
                    self.assertEqual([b["band"] for b in buys], ["learning"])
                    self.assertEqual(sent(h), [("ACME", qty)], "2% of $2,000 at the limit; one share up to 5%")

    def test_probe_three_and_a_half_percent_and_one_share_to_five(self):
        for prev, qty in ((16.0, "3"), (64.0, "1"), (80.8, None)):
            with self.subTest(prev=prev):
                self.setUp()
                h, buys = self.one(band="probe", prev=prev)
                if qty is None:
                    self.assertEqual((sent(h), buys), ([], []), "one share above 5% of E: skipped at Probe too (A86)")
                    self.assertTrue(self.skipped(h))
                else:
                    self.assertEqual([b["band"] for b in buys], ["probe"])
                    self.assertEqual(sent(h), [("ACME", qty)], "3.5% of $2,000 at the limit: whole, or one share")

    def test_at_most_eight_open_at_learning(self):
        h = self.harness(cash="5000", E="5000")
        for i in range(10):
            fall(h, f"DR{i:02d}", f"{i + 300:010d}", f"dr-{i}")
        h.lane.decided(DAY, "open")
        lane_close(h, DROP)
        for hh, mm in ((9, 15), (15, 46), (15, 47)):
            h.tick(hh, mm)
        self.assertEqual(len(buys_of(h, DROP)), 8)
        self.assertEqual(len(sent(h)), 8)


if __name__ == "__main__":
    unittest.main()
