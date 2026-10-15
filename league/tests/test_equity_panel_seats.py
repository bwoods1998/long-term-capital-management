"""THE PANEL MONEY ROW AND THE PANEL SEAT POOL (release E4 step two; league/constitution.py `equity_money.panel`).

A panel program (structure "panel", league/xs) holds a seat of its own: the constitution's `equity_money.panel.seats`
(one, in a pool beside the ETF programs' `probe.max_programs`) at a sleeve of its own, `panel.sleeve_share` x E (0.10,
never above the Probe's). What is held here:

- THE ROW as the book and the swarm read it (league/equity/bands.py `panel_settings`): the row in force; a row that is
  absent, outside its bounds or above the Probe sleeve reads as no panel seat and no sleeve (fail closed).
- A PANEL INSTANCE IS SIZED FROM THE ROW: an eight-name basket at an invented E is eight lots of an eighth of 0.10 x E
  (and never of the Probe sleeve: the mutant that reads the Probe row is caught).
- THE ETF PROGRAMS TRADE AS BEFORE, ORDER FOR ORDER, with a panel Candidate, Probe and Sized program given to the book
  (league/tests/equity_week.py's scenarios through the test double of the reader, the panel rows beside the ETF
  ones): every POST, cancel and fill, every ETF intent, order, lot and instance row, the ETF seat plan and every ETF
  seat record are the same as with no panel row at all, under the seat rule in force and under its rollback
  "first-come" (and the run with no panel row is main's own record: league/tests/test_equity_etf_orders.py). The
  mutant that drops the kind partition is caught.
- A PANEL PROGRAM NEVER TAKES OR YIELDS AN ETF SEAT; a second panel Candidate waits for the pool's one seat; a panel
  program HELD ON A FAILED LEG keeps its seat and nobody is seated into it, before or after the leg recovers, also
  when the read shows no panel row at all (the real reader's case); THE SWARM'S `elane.panel.seats` 0 closes the pool
  on the book's side, and a reader that cannot say it seats nobody new.
- A HELD BASKET NEVER STOPS AN EXIT: the equity book's day count stops entries only (the review's blocker: twelve
  basket lots and three ETF lots whose sales each need their third collar rung are all sold in the session).

Every program, price and figure is invented."""

from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest import mock

try:
    import numpy  # noqa: F401 - the panel adapter the book imports at its start needs it
    HAVE = True
except ImportError:  # pragma: no cover
    HAVE = False

from league import constitution as C
from league.equity import bands as B
from league.equity import live as L

REPO = Path(__file__).resolve().parents[2]


class TheRow(unittest.TestCase):
    def test_the_row_in_force(self):
        self.assertEqual(C.CONSTITUTION["equity_money"]["panel"], {"seats": 1, "sleeve_share": "0.10"})
        self.assertEqual(B.panel_settings(), B.PanelSettings(1, D("0.10")))
        self.assertEqual((C.EQUITY_MONEY_BOUNDS["panel.seats"], C.EQUITY_MONEY_BOUNDS["panel.sleeve_share"]),
                         (("0", "2"), ("0", "0.25")))
        self.assertIn("panel.seats", C._EQUITY_COUNTS)
        self.assertEqual(C.equity_money_problems(), [])

    def test_a_row_that_cannot_be_read_seats_nobody_and_sizes_nothing(self):
        def at(**row):
            c = copy.deepcopy(C.CONSTITUTION)
            c["equity_money"]["panel"] = {**c["equity_money"]["panel"], **row}
            return c

        absent = copy.deepcopy(C.CONSTITUTION)
        del absent["equity_money"]["panel"]
        for bad in (absent, at(seats=3), at(seats=-1), at(seats=True), at(seats=1.0), at(sleeve_share="0.26"),
                    at(sleeve_share="nan"), at(sleeve_share="x"), at(sleeve_share=None)):
            self.assertEqual(B.panel_settings(bad), B.PANEL_FALLBACK)
        low = copy.deepcopy(C.CONSTITUTION)
        low["equity_money"]["probe"]["sleeve_share"] = "0.05"
        self.assertEqual(B.panel_settings(low), B.PANEL_FALLBACK, "never above the Probe sleeve")
        self.assertEqual(B.panel_settings(at(seats=2, sleeve_share="0.25")), B.PanelSettings(2, D("0.25")))
        self.assertEqual(B.PANEL_FALLBACK, B.PanelSettings(0, D(0)))

    def test_the_row_moved_every_pairs_digests_once_and_nothing_else(self):
        from league.tests import equity_design as X

        for pair in X.CANDIDATES:
            at = X.constitution_at(*pair)
            self.assertEqual((C.money_digest(at), C.digest(at)), X.DIGESTS[pair], pair)
            bare = X.without_panel(at)
            self.assertEqual((C.money_digest(bare), C.digest(bare)), X.DIGESTS_E5A[pair], f"{pair}: E5-A's, less the row")
        self.assertEqual(set(X.DIGESTS.values()) & set(X.DIGESTS_E5A.values()), set(), "every pin moved with the row")
        self.assertEqual((C.money_digest(), C.PINNED_DIGEST), X.DIGESTS[X.in_force()])

    def test_set_designs_line_is_the_probe_row_alone(self):
        """`set_design` rewrites the `probe` row's one line: the panel row is a block of its own below the table (as
        the seat rule's is), so a design change never touches it."""
        text = (REPO / "league" / "constitution.py").read_text(encoding="utf-8")
        probe = [line for line in text.splitlines() if line.strip().startswith('"probe": {"sleeve_share"')]
        self.assertEqual(len(probe), 1)
        self.assertNotIn("panel", probe[0])
        self.assertEqual(text.count('CONSTITUTION["equity_money"]["panel"] = {"seats": 1, "sleeve_share": "0.10"}'), 1)


def _book_panel():
    from league.tests import test_equity_book_panel as P

    return P


@unittest.skipUnless(HAVE, "numpy not installed")
class APanelInstanceIsSizedFromTheRow(unittest.TestCase):
    """The book's panel path (league/tests/test_equity_book_panel.py's harness) with the ROW IN FORCE: E invented at
    $2,000, a target of eight names at an eighth each. The sleeve is 0.10 x E = $200; eight lots of $25.00."""

    E = "2000"
    NAMES8 = tuple(f"N0{i:02d}" for i in range(10, 18))

    def setUp(self):
        P = _book_panel()
        self.P = P
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR"))
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.universe = P.XB.Universe.make(self.root / P.STORE_DIR, P.NAMES)
        self.addCleanup(P.XB.UNIVERSES.pop, str(self.root / P.STORE_DIR), None)
        patch = P.XB.fixtures()
        patch.__enter__()
        self.addCleanup(patch.__exit__, None, None, None)
        self.h = P.Harness(self.root, E=self.E, probe_sleeve_share=D("0.50"))
        self.addCleanup(self.h.state.close)
        self.h.child.plans[P.KEY] = {"symbols": {s: 0.125 for s in self.NAMES8}, "at": "open"}

    def test_eight_lots_of_an_eighth_of_the_panel_sleeve(self):
        h = self.h
        self.assertEqual(h.book._sleeve_share(h.instance_now()), D("0.10"), "the row's, not the Probe sleeve (0.50)")
        h.decide(self.P.FRIDAY)
        row = h.rebalance(self.P.FRIDAY)
        self.assertEqual((row["budget"], row["n_buys"]), ("200.00", 8), "0.10 x $2,000, the basket whole")
        self.assertEqual(sorted(i.usd for i in h.panel_intents()), [D("25.00")] * 8)

    def test_an_etf_programs_sleeve_is_the_probes_still(self):
        inst = L.Instance("seed-a@1:r", "seed-a", 1, "beta", "r1", "x", {}, "probe", True, 20, created_at=0.0)
        self.assertEqual(self.h.book._sleeve_share(inst), D("0.50"), "the harness's own Probe sleeve")

    def test_the_mutant_that_reads_the_probe_row_for_a_panel_instance_is_caught(self):
        h = self.h
        real = L.EquityBook._sleeve_share

        def probe_row(book, inst):
            return real(book, L.replace(inst, kind=L.EQUITY_KIND))

        with mock.patch.object(L.EquityBook, "_sleeve_share", probe_row):
            h.decide(self.P.FRIDAY)
        self.assertNotEqual(sorted(i.usd for i in h.panel_intents()), [D("25.00")] * 8)


@unittest.skipUnless(HAVE, "numpy not installed")
class AHeldBasketNeverStopsAnExit(unittest.TestCase):
    """THE REVIEW'S BLOCKER (review-live, step two): the equity book's day count (A8.3, 60 sends and cancels) once
    stopped exits. A held twelve-name basket (0.10 x E at an invented E of $2,000: twelve lots of $16.66) and three
    one-ETF lots exit at one open on which every sale needs its THIRD collar rung (the bid falls 60 bp after each of
    its first two sends): fifteen lots, a send and a cancel a rung each, climb the ladder together, 75 orders. Every
    exit is done in the session, the three ETF sales among them (A28: an exit must never be blocked); before the fix
    the count ran out at the third rung and eight sales were carried to Tuesday, the three ETF lots' among them."""

    NAMES12 = tuple(f"N0{i:02d}" for i in range(10, 22))

    def setUp(self):
        P = _book_panel()
        self.P = P
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR"))
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        P.XB.Universe.make(self.root / P.STORE_DIR, P.NAMES)
        self.addCleanup(P.XB.UNIVERSES.pop, str(self.root / P.STORE_DIR), None)
        patch = P.XB.fixtures()
        patch.__enter__()
        self.addCleanup(patch.__exit__, None, None, None)
        self.h = P.Harness(self.root, E="2000", probe_sleeve_share=D("0.50"))
        self.addCleanup(self.h.state.close)

    def test_every_exit_of_a_fast_open_is_done_in_the_session(self):
        P, h = self.P, self.h
        baskets = [h.seed(s, "16.66") for s in self.NAMES12]
        etf = []
        for i, sym in enumerate(("SPY", "QQQ", "IWM")):
            inst = h.instance(f"lot-{i}-{sym.lower()}")
            etf.append(h.lot(inst, sym, "0.8", str(sum(h.market.quote(sym)) / 2), opened=P.FRIDAY))
        for lot in baskets:
            h.intent(h.inst, "sell", lid=lot.lid, tag="xs")
        for lot in etf:
            h.intent(h.book._instance(lot.instance), "house_exit", lid=lot.lid, tag="max_hold")
        drops: dict[str, int] = {}

        def falls(body):
            if body["side"] != "sell" or drops.get(body["symbol"], 0) >= 2:
                return
            drops[body["symbol"]] = drops.get(body["symbol"], 0) + 1
            bid, ask = h.market.quote(body["symbol"])
            h.market.quotes[body["symbol"]] = (bid * D("0.994"), ask * D("0.994"))

        h.venue.on_submit = falls
        h.run(P.MONDAY, (9, 31), (9, 32), (9, 33), (9, 34), (9, 35))
        day = P.MONDAY.isoformat()
        self.assertGreater(L.orders_today(h.state.rows, day), 60, "the exits went past the equity count")
        self.assertEqual({h.book._lot(lot.lid).status for lot in etf}, {"closed"}, "every ETF exit is done")
        self.assertEqual({h.book._lot(lot.lid).status for lot in baskets}, {"closed"}, "and every basket exit")
        self.assertEqual([i for i in h.intents() if i.kind != "buy" and i.status != "done"], [])
        self.assertEqual(sorted(b["symbol"] for b in h.venue.sent if b["side"] == "sell"),
                         sorted([*self.NAMES12, "SPY", "QQQ", "IWM"] * 3), "each sale filled at its third rung")
        self.assertFalse([e for e in h.events if e[0] == "equity.carried"], "nothing carried to Tuesday")


@unittest.skipUnless(HAVE, "numpy not installed")
class TheEtfProgramsTradeAsBeforeWithPanelProgramsInTheBook(unittest.TestCase):
    """THE ETF POOL IS MAIN'S, ORDER FOR ORDER (the module docstring). `etf_part` keeps of a snapshot what an ETF
    program did and was told; it is held equal between a run with no panel row and a run whose reader also gives the
    book a panel program in the Candidate, the Probe and the Sized band."""

    maxDiff = None
    PANELS = ("candidate", "probe", "sized")
    SCENARIOS = ("normal", "two Candidates take their seats at Friday's decide",
                 "fortnight: an idle seat yields to the waiting program",
                 "fortnight: two programs wait, one idle seat yields a decision day",
                 "fortnight: nobody waits, the idle seats are kept")

    @staticmethod
    def etf_part(snap: dict) -> dict:
        """What an ETF program did and was told: every POST, cancel and fill; its intent, order, lot and instance
        rows; the seat lines and the plan of the ETF pool; every record and alert, less what names a panel program
        (a record of every instance, the day's decide, keeps its ETF entries). An intent's `bars_sha` is left out: it
        is the sha of the 16:20 fetch, which names every instance's symbols (a panel lot's among them), not of what
        an ETF program reads."""
        def etf(row) -> bool:
            return "xs-row-" not in json.dumps(row)

        def scrub(value):
            if isinstance(value, dict):
                return {k: scrub(v) for k, v in value.items() if "xs-row-" not in str(k)}
            if isinstance(value, list):
                return [scrub(v) for v in value if etf(v) or isinstance(v, (dict, list))]
            return value

        plan = json.loads(snap["kv"].get("eq_seat") or "null")
        if isinstance(plan, dict):
            plan.pop(L.SEAT_PANEL, None)
        rows = {part: [r for r in snap[part] if etf(r)] for part in ("intents", "orders", "lots", "instances")}
        rows["intents"] = [{k: v for k, v in r.items() if k != "bars_sha"} for r in rows["intents"]]
        return {
            "posts": snap["posts"], "cancels": snap["cancels"], "fills": snap["fills"], **rows,
            "seats": [line for line in snap["seats"] if etf(line)], "eq_seat": plan,
            "records": [scrub(r) for r in snap["records"] if etf(r) or r[1] == "equity.decide"],
            "alerts": [a for a in snap["alerts"] if etf(a)],
        }

    def compare(self, name: str, **kw) -> dict:
        from league.tests import equity_week as W

        plain = W.run(name, **kw)
        mixed = W.run(name, panels=self.PANELS, **kw)
        self.assertEqual(self.etf_part(mixed), self.etf_part(plain), name)
        return mixed

    def test_under_the_seat_rule_in_force(self):
        for name in self.SCENARIOS:
            with self.subTest(scenario=name):
                mixed = self.compare(name)
                plan = json.loads(mixed["kv"]["eq_seat"])
                named = json.dumps({k: v for k, v in plan.items() if k != L.SEAT_PANEL})
                self.assertNotIn("xs-row-", named, "the ETF plan names no panel program")
                panel = plan[L.SEAT_PANEL]
                self.assertEqual(panel["seats"], 1)
                self.assertEqual(sorted(h["family"] for h in panel["holders"]), ["xs-row-probe", "xs-row-sized"])
                self.assertEqual([w["family"] for w in panel["waiting"]], ["xs-row-candidate"],
                                 "a full pool: the panel Candidate waits, with a K above every ETF program's")

    def test_under_the_rollback_first_come(self):
        from league.tests.equity_design import seat_rule

        with seat_rule("first-come"):
            for name in ("normal", "two Candidates take their seats at Friday's decide",
                         "fortnight: an idle seat yields to the waiting program"):
                with self.subTest(scenario=name):
                    mixed = self.compare(name)
                    panel = json.loads(mixed["kv"]["eq_seat"])[L.SEAT_PANEL]
                    self.assertEqual(sorted(h["family"] for h in panel["holders"]), ["xs-row-probe", "xs-row-sized"])

    def test_the_mutant_that_drops_the_kind_partition_is_caught(self):
        from league.tests import equity_week as W

        name = "two Candidates take their seats at Friday's decide"
        plain = self.etf_part(W.run(name))
        with mock.patch.object(L.EquityBook, "_pools", lambda book, rows: [(L.POOL_ETF, rows)]):
            mixed = self.etf_part(W.run(name, panels=self.PANELS))
        self.assertNotEqual(mixed["posts"], plain["posts"], "a panel program in the ETF pool costs an ETF seat")


@unittest.skipUnless(HAVE, "numpy not installed")
class ThePanelPool(unittest.TestCase):
    """The panel pool at a band sync, on the book's own rows (the test double of the reader): a second panel
    Candidate waits; a panel program held on a failed leg keeps its seat."""

    def setUp(self):
        from league.tests import equity_week as W

        self.W = W
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR"))
        self.addCleanup(self.tmp.cleanup)

    def house(self, panels: tuple[str, ...], *, ids: tuple[str, ...] = (), k: tuple = ()):
        W = self.W
        rows = W.ranked_programs(0) + W.panel_rows(panels)
        for i, (row, fid) in enumerate(zip([r for r in rows if r["structure"] == "panel"], ids)):
            row["family"] = fid
            if i < len(k):
                row["seat_activity"] = W.activity(*k[i])
        house = W.House(Path(self.tmp.name) / f"h{len(os.listdir(self.tmp.name))}", rows)
        self.addCleanup(house.close)
        W.invented_week(house.market, through=W.FORTNIGHT_END)
        return house

    def decide(self, house, day=None):
        W = self.W
        day = day or W.FRIDAY
        house.tick(day, 16, 21)
        return house.tick(day, 16, 31)

    def seated(self, house):
        return sorted(r["family"] for r in house.families.read() if r["band"] in ("probe", "sized"))

    def test_a_second_panel_candidate_waits(self):
        house = self.house(("candidate", "candidate"), ids=("xs-a", "xs-b"))
        self.decide(house)
        plan = json.loads(json.dumps(house.book.seats()))
        self.assertEqual([h["family"] for h in plan[L.SEAT_PANEL]["holders"]], ["xs-a"], "the earlier id, at one K")
        self.assertEqual([w["family"] for w in plan[L.SEAT_PANEL]["waiting"]], ["xs-b"])
        self.assertEqual(len(plan["holders"]), 6, "the six ETF seats as they were")
        self.assertNotIn("xs-", json.dumps({k: v for k, v in plan.items() if k != L.SEAT_PANEL}))

    def test_the_panel_pool_ranks_by_k_inside_itself(self):
        """K FOR A BASKET ranks the waiting panel programs inside the panel pool only: the higher K takes the one seat
        though its id sorts later (both passed at the same time); the ETF programs' plan is untouched."""
        house = self.house(("candidate", "candidate"), ids=("xs-a", "xs-b"), k=((5, 40), (60, 400)))
        self.decide(house)
        plan = house.book.seats()
        self.assertEqual(([h["family"] for h in plan[L.SEAT_PANEL]["holders"]],
                          [w["family"] for w in plan[L.SEAT_PANEL]["waiting"]]), (["xs-b"], ["xs-a"]))
        self.assertEqual(len(plan["holders"]), 6)

    def test_a_panel_program_never_takes_or_yields_an_etf_seat(self):
        """The fortnight in which an idle ETF seat yields to the waiting ETF program: with a panel Candidate of the
        highest K waiting beside it, the yielded seat still goes to the ETF program, and the panel Candidate is seated
        into the panel pool alone."""
        W = self.W
        with_panel = W.run("fortnight: an idle seat yields to the waiting program", panels=("candidate",))
        plain = W.run("fortnight: an idle seat yields to the waiting program")
        said = [line for line in with_panel["seats"] if "xs-row-" not in line]
        self.assertEqual(said, plain["seats"])
        self.assertTrue(any("yielded: bred-d-idle for bred-e-wait" in line for line in said))
        plan = json.loads(with_panel["kv"]["eq_seat"])
        self.assertEqual([h["family"] for h in plan[L.SEAT_PANEL]["holders"]], ["xs-row-candidate"])
        self.assertFalse([r for r in with_panel["records"] if r[1] == "equity.seat" and "xs-row-" in json.dumps(r)
                          and r[2].get("pool") != "panel"], "every seat record of a panel program names its pool")

    def test_a_panel_program_held_on_a_failed_leg_keeps_its_seat(self):
        house = self.house(("probe", "candidate"), ids=("xs-held", "xs-next"))
        self.decide(house)
        held = house.book._instance("xs-held@1:r")
        self.assertIsNotNone(held)
        self.assertIsNone(held.retired_at)
        # The leg fails: the reader holds the program's opens (no row, `families.HELD`), and the double shows the
        # waiting Candidate still (the real reader shows no panel row at all then: every leg is the lane's).
        house.families.held["xs-held"] = "the panel lane is not ready: the nightly I6 did not hold"
        for day in (self.W.MONDAY, self.W.TUESDAY):
            house.tick(day, 8, 31)
            self.decide(house, day)
            self.assertIsNone(house.book._instance("xs-held@1:r").retired_at, "nothing is retired on a failed leg")
            self.assertEqual(self.seated(house), sorted(r["family"] for r in self.W.ranked_programs(0)),
                             "nobody is seated into the held program's seat")
            self.assertIsNone(house.book._instance("xs-next@1:r"))
            plan = house.book.seats()[L.SEAT_PANEL]
            self.assertEqual(plan["held_seats"], ["xs-held"])
        house.families.held.clear()                                              # the leg recovers
        day = self.W.sessions_from(self.W.TUESDAY, 2)[1]
        house.tick(day, 8, 31)
        self.decide(house, day)
        self.assertIn("xs-held", self.seated(house))
        self.assertNotIn("xs-next", self.seated(house), "and after it, the pool is full")
        plan = house.book.seats()[L.SEAT_PANEL]
        self.assertEqual(([h["family"] for h in plan["holders"]], [w["family"] for w in plan["waiting"]]),
                         (["xs-held"], ["xs-next"]))
        self.assertNotIn("held_seats", plan)

    def test_the_swarms_setting_closes_the_pool_on_the_books_side(self):
        """`elane.panel.seats` 0 as the reader answers it (`families.panel_seats()`): a waiting panel Candidate takes
        no seat, under the seat rule in force and under the rollback "first-come"; when the swarm opens the pool again
        it is seated at the next sync. (The review's SEAT-2: a book that ignored the setting seated it.)"""
        from league.tests.equity_design import seat_rule

        for rule in ("activity-1-free", "first-come"):
            with self.subTest(rule=rule), seat_rule(rule):
                house = self.house(("candidate",), ids=("xs-a",))
                house.families.panel_roster = 0
                self.assertEqual(house.book._panel_seat_count(), 0)
                self.decide(house)
                self.assertIsNone(house.book._instance("xs-a@1:r"), "no instance: no seat")
                self.assertNotIn("xs-a", self.seated(house))
                self.assertEqual(house.book.seats()[L.SEAT_PANEL]["seats"], 0)
                house.families.panel_roster = None                         # the swarm's word is gone: the row's 1
                house.tick(self.W.MONDAY, 8, 31)
                self.decide(house, self.W.MONDAY)
                self.assertIn("xs-a", self.seated(house))

    def test_a_held_program_keeps_its_seat_when_the_read_shows_no_panel_row_at_all(self):
        """THE REAL READER'S CASE: while a leg of the panel lane fails, the read shows NO panel row (every leg is the
        lane's), so the panel pool runs on its plan alone (`_pools`' plan clause): the held program's seat is said
        held, and when the leg recovers the plan says so. (The review's SEAT-5: a pool dropped once its rows were gone
        never said the held seat.)"""
        house = self.house(("probe",), ids=("xs-held",))
        self.decide(house)
        self.assertIsNotNone(house.book._instance("xs-held@1:r"))
        house.families.held["xs-held"] = "the panel lane is not ready: the nightly I6 did not hold"
        self.assertEqual([r for r in house.families.read() if r.get("structure") == "panel"], [], "no panel row")
        house.tick(self.W.MONDAY, 8, 31)
        self.decide(house, self.W.MONDAY)
        self.assertIsNone(house.book._instance("xs-held@1:r").retired_at)
        plan = house.book.seats()[L.SEAT_PANEL]
        self.assertEqual((plan["held_seats"], plan["holders"]), (["xs-held"], []))
        house.families.held.clear()
        day = self.W.sessions_from(self.W.MONDAY, 2)[1]
        house.tick(day, 8, 31)
        self.decide(house, day)
        plan = house.book.seats()[L.SEAT_PANEL]
        self.assertEqual([h["family"] for h in plan["holders"]], ["xs-held"])
        self.assertNotIn("held_seats", plan)

    def test_the_etf_pools_write_keeps_the_panel_pools_plan(self):
        """`_put_plan`: the ETF pool's plan is `SEAT_KEY` itself and the panel pool's stays inside it as it stands; the
        panel pool's write touches nothing of the ETF pool's. (The review's SEAT-7.)"""
        house = self.house(("probe",), ids=("xs-a",))
        self.decide(house)
        before = house.book.seats()
        panel = before[L.SEAT_PANEL]
        house.book._put_plan(L.POOL_ETF, {**{k: v for k, v in before.items() if k != L.SEAT_PANEL}, "day": "x"})
        after = house.book.seats()
        self.assertEqual((after[L.SEAT_PANEL], after["day"]), (panel, "x"))
        house.book._put_plan(L.POOL_PANEL, {**panel, "day": "y", L.SEAT_PANEL: "never nested"})
        again = house.book.seats()
        self.assertEqual({k: v for k, v in again.items() if k != L.SEAT_PANEL},
                         {k: v for k, v in after.items() if k != L.SEAT_PANEL})
        self.assertEqual((again[L.SEAT_PANEL]["day"], L.SEAT_PANEL in again[L.SEAT_PANEL]), ("y", False))


class TheRealReadersPanelSeats(unittest.TestCase):
    """league/equity/families.py `EquityFamilies.panel_seats`: the swarm's `elane.panel.seats`, and 0 when it cannot be
    read (fail closed: no new panel seat). (The review's SEAT-8: a reader that failed open seated past the setting.)"""

    def test_a_read_that_raises_is_no_panel_seat(self):
        from league.equity.families import EquityFamilies
        from league.swarm import elane_xs

        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as tmp:
            reader = EquityFamilies(tmp)
            self.assertEqual(reader.panel_seats(), elane_xs.panel_seats(Path(tmp)))
            with mock.patch.object(elane_xs, "panel_seats", side_effect=RuntimeError("swarm.json could not be read")):
                self.assertEqual(reader.panel_seats(), 0)
            with mock.patch.object(elane_xs, "panel_seats", return_value=-3):
                self.assertEqual(reader.panel_seats(), 0)
            book = L.EquityBook.__new__(L.EquityBook)
            book.families = reader
            with mock.patch.object(elane_xs, "panel_seats", side_effect=RuntimeError("swarm.json could not be read")):
                self.assertEqual(book._panel_seat_count(), 0, "the book seats nobody new on it")
            book.families = mock.Mock(panel_seats=mock.Mock(side_effect=RuntimeError("no word")))
            self.assertEqual(book._panel_seat_count(), 0, "a reader that raises: no seat")


class TheReportSaysThePanelPool(unittest.TestCase):
    """league/ops/dlane_report.py: the panel statement at the rows in force, and the panel pool's plan beside the ETF
    pool's (which is as before)."""

    def test_the_statement_at_the_rows_in_force(self):
        from league.ops import dlane_report as R
        from league.tests import equity_design as X

        note = R.equity_panel_note()
        seats = X.in_force()[0]                         # the ETF pool's seats in force (6 at A32, 12 at EQDONE-7's pair)
        for words in (f"one of 1 panel seat(s) of its own, never one of the {seats} ETF seats, at a sleeve of 0.10 x E",
                      "0.04 x E of open risk at the stock weight (0.40), in the same $400 window, first come",
                      "one market move"):
            self.assertIn(words, note)
        self.assertEqual(note, R.EQUITY_PANEL_NOTE)
        bare = copy.deepcopy(C.CONSTITUTION)
        del bare["equity_money"]["panel"]
        self.assertEqual(R.equity_panel_note(bare), R.EQUITY_PANEL_BARE)

    def test_the_panel_pools_plan_beside_the_etf_pools(self):
        from league.ops import dlane_report as R

        etf = {"rule": "activity-1-free", "seats": 6, "day": "2026-10-16", "holders": [
            {"family": "bred-a", "version": 1, "band": "probe", "since": "2026-10-09", "seated_sessions": 5}],
            "waiting": [], "idle": {}, "left_out": [], "last": None, "order": "the book's plan"}
        plain = R.equity_seats(None, {"seat_plan": etf}, [])
        self.assertNotIn("panel", plain, "a plan with no panel pool reads as before")
        pool = {"rule": "activity-1-free", "seats": 1, "day": "2026-10-16", "held_seats": ["xs-a"], "waiting": [
            {"family": "xs-b", "rank": 1, "seeded": False, "flagged": False, "ranked": True}], "holders": [
            {"family": "xs-a", "version": 2, "band": "probe", "since": "2026-10-12", "seated_sessions": 3, "idle": False}]}
        both = R.equity_seats(None, {"seat_plan": {**etf, "panel": pool}}, [])
        self.assertEqual({k: v for k, v in both.items() if k != "panel"}, plain)
        self.assertEqual(both["panel"]["holders"], [{"family": "xs-a", "version": 2, "band": "probe",
                                                     "since": "2026-10-12", "seated_sessions": 3, "idle": False}])
        self.assertEqual((both["panel"]["waiting"], both["panel"]["held_seats"], both["panel"]["seats"]),
                         ([{"family": "xs-b", "rank": 1}], ["xs-a"], 1))
        self.assertEqual(both["panel"]["statement"], R.EQUITY_PANEL_NOTE)


@unittest.skipUnless(HAVE, "numpy not installed")
class TheSwarmsReaderSeatsByPool(unittest.TestCase):
    """league/swarm/bands.py `equity_seating`: the ETF pool's answer is main's whatever the panel families' bands."""

    def fam(self, fid, band, structure="etf", at=1.0, forward=True):
        """A roster input. A PANEL family holds its band on a FWD1-R forward pass seated through the panel pool
        (`forward`; the captain's A34, release U: the only panel seat), unless `forward` is False (a band a historical
        look made, or one written by hand)."""
        state = {"banded_at": at}
        if structure == "panel" and forward:
            state.update(banded_version=1, elane_forward={"eligible": True, "seated": True, "type": "PANEL", "case": "N",
                                                          "version": 1, "cell": f"cell-{fid}"})
        return {"id": fid, "band": band, "structure": structure, "band_since": None, "state": state}

    def test_a_panel_probe_costs_no_etf_seat_and_the_panel_pool_has_its_own(self):
        from league.swarm import bands, elane_xs

        etf = [self.fam(f"e{i}", "probe") for i in range(5)] + [self.fam("e-wait", "candidate", at=2.0)]
        panel = [self.fam("p-probe", "probe", "panel"), self.fam("p-a", "candidate", "panel", at=3.0),
                 self.fam("p-b", "candidate", "panel", at=4.0),
                 self.fam("p-look", "candidate", "panel", at=2.5, forward=False)]   # first in the queue, if it could
        alone = bands.equity_seating(etf, 6, seatable=lambda s: True)
        both = bands.equity_seating(etf + panel, 6, seatable=lambda s: True, panel_seats=2)
        self.assertEqual(alone["seated"], ["e-wait"])
        self.assertEqual(both["seated"], ["e-wait", "p-a"])
        self.assertEqual(both["waiting"], ["p-b"])
        self.assertEqual(both["seatless"], ["p-look"], "A34: a panel Candidate with no forward seat holds none")
        self.assertEqual(both["probe"], sorted([f"e{i}" for i in range(5)] + ["p-probe"]))
        closed = bands.equity_seating(etf + panel, 6, seatable=lambda s: True, panel_seats=0)
        self.assertEqual((closed["seated"], closed["waiting"]), (["e-wait"], ["p-a", "p-b"]), "0: no new panel seat")
        with mock.patch.object(elane_xs, "A34_FORWARD_ONLY", False):   # the route as built: the look's Candidate queues
            built = bands.equity_seating(etf + panel, 6, seatable=lambda s: True, panel_seats=2)
        self.assertEqual((built["seated"], built["waiting"]), (["e-wait", "p-look"], ["p-a", "p-b"]))

    def test_the_swarms_setting_may_only_lower_the_row(self):
        from league.swarm import bands, elane_xs

        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as tmp:
            root = Path(tmp)
            self.assertEqual(bands.panel_pool_seats(root), 1, "the policy's 2 leaves the row's 1")
            (root / "swarm.json").write_text(json.dumps({"elane": {"panel": {"seats": 0}}}))
            self.assertEqual((elane_xs.panel_seats(root), bands.panel_pool_seats(root)), (0, 0))
            (root / "swarm.json").write_text(json.dumps({"elane": {"panel": {"seats": 3}}}))
            self.assertEqual(bands.panel_pool_seats(root), 1, "outside its bound: the default, and never above the row")
        self.assertEqual(elane_xs.BOUNDS["seats"], (0, 2))


if __name__ == "__main__":
    unittest.main()
