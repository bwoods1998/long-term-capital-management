"""THE PROBE SLEEVE AND THE SEATS: what the equity lane holds, sized by the one real sizing function
(`league/equity/sizing.py` `size_entry`) on the facts the book states to it (`league/equity/live.py`
`EquityBook._size`; league/tests/equity_design.py `Lane`).

TWO TABLES ARE READ HERE, AND NEITHER IS ASSUMED:
- A20's DESIGN (the captain's amendment A20, Oct 11, 2026: three seats, first come, at a sleeve of 0.50 x E), stated as
  a table of its own (`A20`): the dollar scenarios that decision was made on, by hand. A one-ETF program's lot is half
  its sleeve, 0.25 x E; THREE SUCH LOTS FIT WITH NO CAP BINDING (0.75 x E), which is why the row was 0.50 and not the
  study rule's 0.66 (an entry the House cuts or refuses is one the Gym, judging each program alone in its own sleeve,
  fills: Done's consistency clause reads that difference); and every owner line still binds, BY NAME: an ETF at most
  0.50 x E across all programs ("instrument"), at most 1.00 x E invested ("invested"), the House-wide cash reserve
  ("cash"), and the shared loss budget's room over the ETF weight ("budget").
- THE TABLE IN FORCE, whose seats and sleeve are the two numbers of release E5-S (`set_design SEATS SLEEVE`), and with
  it EVERY PAIR OF THE PRE-REGISTERED GRID (seats 3, 4, 5, 6 x sleeve 0.50, 0.33, 0.25): the same properties, with
  every expected size computed from the table's rows by the rule written out in league/tests/equity_design.py
  (`walk`, `figures`), never by the code under test.
A Sized program's sleeve is never below the Probe's (`league/equity/bands.py` `sized_sleeve_share`). Invented figures
only (an E, a price of $100 a share, losses already in the budget); standard library only."""

import itertools
import unittest
from dataclasses import replace
from decimal import Decimal as D

from league.constitution import CONSTITUTION, EQUITY_MONEY_BOUNDS
from league.equity.bands import EquityRecord, sized_sleeve_share, sized_up
from league.live import money as M
from league.tests import equity_design as X

TABLE = M.Table.from_constitution()
EQ = TABLE.equity
#: A20's design as a table of its own: three seats at 0.50, every other row the one in force.
A20 = X.table_at(*X.REFERENCE)
ZERO = D(0)
WEIGHT = EQ.open_risk_weight["etf"]
#: Six ETFs of the universe: a seat each, at the grid's most seats.
ETFS = ("SPY", "QQQ", "IWM", "DIA", "XLK", "XLF")
#: Every pair the tests walk: the grid's twelve, and the pair in force (one of them: `TheTableInForce`).
PAIRS = tuple(dict.fromkeys((*X.CANDIDATES, X.in_force())))


def lane(E: str, cash: str, **kw) -> X.Lane:
    """A lane at A20's design."""
    return X.Lane(A20, E, cash, **kw)


def record(returns, *, pnl="50", bh_pnl="20", probe_sessions=10):
    returns = tuple(returns)
    return EquityRecord(n=len(returns), returns=returns, pnl=D(pnl), bh_pnl=D(bh_pnl), probe_sessions=probe_sessions,
                        realized_net=D(pnl))


class TheTableInForce(unittest.TestCase):
    def test_the_sleeve_the_seats_and_the_owners_lines(self):
        """The two numbers in force are one pair of the grid, inside their bounds; the owner's lines they are sized
        inside are read here as they stand, and no design moves them."""
        seats, sleeve = X.in_force()
        self.assertIn((seats, sleeve), X.CANDIDATES)
        self.assertEqual((EQ.probe_sleeve_share, EQ.probe_max_programs), (D(sleeve), seats))
        self.assertEqual(EQUITY_MONEY_BOUNDS["probe.sleeve_share"], ("0", "0.50"))
        self.assertEqual(EQUITY_MONEY_BOUNDS["probe.max_programs"], ("0", "6"))
        self.assertEqual((EQ.position_share["etf"], EQ.invested_share, EQ.cash_reserve, WEIGHT, EQ.min_order_usd),
                         (D("0.50"), D("1.00"), D("50"), D("0.20"), D("10")))
        self.assertEqual((TABLE.probe_loss_budget, TABLE.probe_loss_window, TABLE.probe_loss_total), (D("400"), 20, D("800")))
        self.assertNotIn("loss_budget_usd", CONSTITUTION["equity_money"]["probe"], "no second budget")
        # A one-ETF program's lot: the sleeve's own 50% rule (`size_entry`'s "sleeve_cap"), half the sleeve.
        self.assertEqual(X.figures(X.rows_of())["lot"], EQ.probe_sleeve_share * EQ.position_share["etf"])
        self.assertEqual(EQ.probe_sleeve_share * EQ.position_share["etf"], D(sleeve) / 2)

    def test_a20s_design_row_by_row(self):
        """WHY 0.50 AT THREE SEATS (A20): three one-ETF lots are under the invested cap, and two of them in one ETF are
        exactly the instrument's cap, so no cross-program cap cuts a one-ETF program's entry. (At 0.66 three lots met
        the cap.) Whole sleeves (a program that holds several ETFs) still ask for more than the account holds: the
        invested cap bounds the lane then."""
        eq = A20.equity
        self.assertEqual((eq.probe_sleeve_share, eq.probe_max_programs), (D("0.50"), 3))
        # (The grid's tables carry the switch on, `equity_design.table_at`: the old lanes' stop's rollback.)
        self.assertEqual(replace(EQ, probe_sleeve_share=D("0.50"), probe_max_programs=3, enabled=True), eq,
                         "no other row differs")
        lot = eq.probe_sleeve_share * eq.position_share["etf"]
        self.assertEqual(lot, D("0.25"))
        self.assertLess(eq.probe_max_programs * lot, eq.invested_share)
        self.assertEqual(2 * lot, eq.position_share["etf"])
        self.assertGreaterEqual(3 * D("0.66") * eq.position_share["etf"], D("0.99"))
        self.assertGreater(eq.probe_max_programs * eq.probe_sleeve_share, eq.invested_share)

    def test_a_one_etf_programs_lot_is_a_quarter_of_e_at_a20s_design(self):
        book = lane("1000", "1500")
        out = book.buy("a", "SPY")                                      # the seeds' intent: half of the sleeve
        self.assertEqual((out.usd, out.qty, out.binding), (D("250"), D("2.5"), "intent"))
        whole = lane("1000", "1500").buy("a", "SPY", share="1")         # the whole sleeve asked: the sleeve's 50% rule
        self.assertEqual((whole.usd, whole.binding), (D("250"), "sleeve_cap"))
        self.assertIn("SPY may hold $250.00 more in this program's sleeve (0.50 x $500.00", whole.reason)
        again = book.buy("a", "SPY")                                    # and no second lot of the same ETF
        self.assertEqual((again.usd, again.binding), (ZERO, "sleeve_cap"))
        self.assertEqual(book.held("SPY"), D("0.25") * book.E)


class ThreeSeats(unittest.TestCase):
    """A20's design, (a): three one-ETF programs at the Probe sleeve hold 0.25 x E each with NO cap binding; the lane is
    never above 1.00 x E."""

    PROGRAMS = (("a", "SPY"), ("b", "QQQ"), ("c", "IWM"))

    def test_three_lots_of_a_quarter_of_e_fit_with_no_cap_binding(self):
        """Whether E is the grant's capital (cash above it) or the account's own cash (cash equal to it): every one of
        the three entries is the intent's, whole. This is what the Gym fills too, each program alone in its sleeve."""
        eq = A20.equity
        for cash in ("1500", "1000"):
            book = lane("1000", cash)
            for program, symbol in self.PROGRAMS:
                out = book.buy(program, symbol)
                self.assertEqual((out.usd, out.binding), (D("0.25") * book.E, "intent"), (cash, program, out))
            self.assertEqual(book.invested, D("0.75") * book.E)
            self.assertEqual(WEIGHT * book.invested, D("0.15") * book.E, "its open risk in the shared budget")
            self.assertLess(book.invested, eq.invested_share * book.E)
            self.assertGreaterEqual(book.cash - book.invested, eq.cash_reserve)

    def test_a_fourth_lot_is_cut_by_the_invested_cap_less_the_cash_reserve(self):
        """A seated program's second ETF (its sleeve has the room). Where the account is all the capital the House-wide
        cash rule leaves it the invested cap's room less the $50 reserve, by name; the next entry is refused."""
        eq = A20.equity
        book = lane("1000", "1000")
        for program, symbol in self.PROGRAMS:
            book.buy(program, symbol)
        fourth = book.buy("a", "DIA")
        room = eq.invested_share * book.E - D("750") - eq.cash_reserve
        self.assertEqual((fourth.usd, fourth.binding), (room, "cash"))
        self.assertEqual(room, D("200"))
        self.assertIn("cut from $250.00: the House-wide available cash is $200.00", fourth.reason)
        self.assertEqual(book.invested, book.E - eq.cash_reserve)
        fifth = book.buy("b", "DIA")
        self.assertEqual((fifth.usd, fifth.binding), (ZERO, "cash"))
        self.assertTrue(fifth.reason.startswith("refused: the House-wide available cash is $0.00"), fifth.reason)

    def test_with_cash_to_spare_the_fourth_lot_fills_the_invested_cap_and_the_next_is_refused_by_name(self):
        eq = A20.equity
        book = lane("1000", "1500")                                     # E is the grant's capital: cash is not what binds
        for program, symbol in self.PROGRAMS:
            book.buy(program, symbol)
        fourth = book.buy("a", "DIA")
        self.assertEqual((fourth.usd, fourth.binding), (D("250"), "intent"))
        self.assertEqual(book.invested, eq.invested_share * book.E)
        # And the next is REFUSED by the invested cap, by name: nothing is ever held above 1.00 x E.
        for program, symbol in (("b", "DIA"), ("c", "XLK"), ("b", "XLE")):
            fifth = book.buy(program, symbol)
            self.assertEqual((fifth.usd, fifth.qty, fifth.binding), (ZERO, ZERO, "invested"), (program, fifth))
            self.assertTrue(fifth.reason.startswith("refused: the invested cap leaves $0.00"), fifth.reason)
        self.assertEqual(book.invested, eq.invested_share * book.E)
        # (The program whose two lots fill its own sleeve is refused by the sleeve first.)
        self.assertEqual(book.buy("a", "XLE").binding, "sleeve_cash")

    def test_a_remainder_under_the_minimum_order_is_skipped_and_names_the_invested_cap(self):
        book = lane("1000", "1500")
        for program, symbol in self.PROGRAMS:
            self.assertEqual(book.buy(program, symbol).usd, D("250"))
        self.assertEqual(book.buy("a", "DIA", share="0.49").usd, D("245"))
        fifth = book.buy("b", "DIA")                                    # the cap leaves $5.00: under the $10 minimum
        self.assertEqual((fifth.usd, fifth.binding), (ZERO, "min_order"))
        self.assertIn("the invested cap leaves $5.00", fifth.reason)
        self.assertLessEqual(book.invested, A20.equity.invested_share * book.E)


class OneEtf(unittest.TestCase):
    """A20's design, (b): two programs in the SAME ETF hold exactly the instrument's 0.50 x E together, each lot whole;
    a third is refused by the instrument cap, by name."""

    def test_two_programs_in_one_etf_hold_half_of_e_together(self):
        eq = A20.equity
        book = lane("1000", "1500")
        for program in ("a", "b"):
            out = book.buy(program, "SPY")
            self.assertEqual((out.usd, out.binding), (D("250"), "intent"), program)
        self.assertEqual(book.held("SPY"), eq.position_share["etf"] * book.E, "exactly the owner's 50%")
        third = book.buy("c", "SPY")
        self.assertEqual((third.usd, third.binding), (ZERO, "instrument"))
        self.assertTrue(third.reason.startswith("refused: SPY may hold $0.00 more on the account (0.50 x E $1000.00, less "
                                                "$500.00 held and working across all programs)"), third.reason)
        self.assertEqual(book.held("SPY"), D("0.50") * book.E, "never above the owner's 50%")
        # The instrument's cap is one ETF's: the third program's other ETF is sized whole.
        other = book.buy("c", "QQQ")
        self.assertEqual((other.usd, other.binding), (D("250"), "intent"))

    def test_whole_sleeves_asked_change_nothing(self):
        book = lane("1000", "1500")
        self.assertEqual([(o.usd, o.binding) for o in (book.buy("a", "SPY", share="1"), book.buy("b", "SPY", share="1"),
                                                       book.buy("c", "SPY", share="1"))],
                         [(D("250"), "sleeve_cap"), (D("250"), "instrument"), (ZERO, "instrument")])


class TheBudget(unittest.TestCase):
    """A20's design, (c): the shared loss budget still cuts an entry when its room over the ETF weight (0.20) is the
    smaller."""

    def test_a_window_that_has_lost_cuts_the_lot_by_name(self):
        book = lane("1000", "1500", window_loss="370")                  # $30 of the $400 window left
        out = book.buy("a", "SPY")
        self.assertEqual((out.usd, out.binding), (D("150"), "budget"))  # 30 / 0.20, under the lot's 250
        self.assertIn("cut from $250.00: the shared loss budget has $30.00 of room, $150.00 of etf at weight 0.20",
                      out.reason)
        self.assertEqual(WEIGHT * book.invested, D("30"), "the lot's open risk is the room it was cut to")
        again = book.buy("b", "QQQ")
        self.assertEqual((again.usd, again.binding), (ZERO, "budget"))
        self.assertTrue(again.reason.startswith("refused: the shared loss budget has $0.00 of room"), again.reason)

    def test_the_totals_room_cuts_when_it_is_the_lower(self):
        book = lane("1000", "1500", window_loss="0", total_loss="790")  # $10 of the $800 total left
        out = book.buy("a", "SPY")
        self.assertEqual((out.usd, out.binding), (D("50"), "budget"))   # 10 / 0.20
        untouched = lane("1000", "1500", window_loss="100", total_loss="100").buy("a", "SPY")
        self.assertEqual((untouched.usd, untouched.binding), (D("250"), "intent"), "room over the weight above the lot")

    def test_at_a_large_e_the_budget_and_not_the_invested_cap_bounds_the_lane(self):
        """The window's $400 over the ETF weight is $2,000 of ETFs, and three one-ETF lots are 0.75 x E: from
        E = $2,667 the third lot is cut by the budget and the lane stops there, its open risk never above the window."""
        book = lane("3000", "4000")
        self.assertEqual([(o.usd, o.binding) for o in (book.buy("a", "SPY"), book.buy("b", "QQQ"))],
                         [(D("750"), "intent"), (D("750"), "intent")])
        third = book.buy("c", "IWM")
        self.assertEqual((third.usd, third.binding), (D("500"), "budget"))      # (400 - 0.20 x 1500) / 0.20
        self.assertEqual(book.invested, A20.probe_loss_budget / WEIGHT)
        self.assertLess(book.invested, A20.equity.invested_share * book.E)
        self.assertEqual(WEIGHT * book.invested, A20.probe_loss_budget)
        fourth = book.buy("a", "DIA")
        self.assertEqual((fourth.usd, fourth.binding), (ZERO, "budget"))
        # Under E = $2,667 three one-ETF lots are inside the window: the budget cuts none of them.
        self.assertEqual(X.figures(X.rows_of(X.constitution_at(*X.REFERENCE)))["budget_e"], 2666)
        for E in ("1000", "2000", "2600", "2666"):
            small = lane(E, str(D(E) + 500))
            for program, symbol in (("a", "SPY"), ("b", "QQQ"), ("c", "IWM")):
                self.assertEqual(small.buy(program, symbol).binding, "intent", (E, program))
            self.assertEqual(WEIGHT * small.invested, D("0.15") * small.E)
            self.assertLess(WEIGHT * small.invested, A20.probe_loss_budget)
        over = lane("2667", "3200")
        self.assertEqual([over.buy(p, s).binding for p, s in (("a", "SPY"), ("b", "QQQ"), ("c", "IWM"))],
                         ["intent", "intent", "budget"])


class EveryPair(unittest.TestCase):
    """THE SAME PROPERTIES AT EVERY PAIR OF THE GRID AND AT THE PAIR IN FORCE (release E5-S). The House's `size_entry`
    (`Lane`) against the rule written out (`equity_design.walk`), ask by ask, and against the closed forms the
    documents state (`equity_design.figures`)."""

    def seats_in_their_own_etfs(self, seats):
        return [(f"p{i + 1}", ETFS[i]) for i in range(seats)]

    def both(self, pair, E, cash, asks, **kw):
        """The House's sizes and the hand rule's for the same asks; equal, or the test fails here."""
        table, r = X.table_at(*pair), X.rows_of(X.constitution_at(*pair))
        book = X.Lane(table, E, cash, window_loss=kw.get("window_loss", "0"), total_loss=kw.get("total_loss"))
        share = kw.get("share", "0.5")
        house = [(out.usd, out.binding) for out in (book.buy(p, s, share=share) for p, s in asks)]
        hand = X.walk(r, D(E), D(cash), asks, share=D(share), window_loss=D(kw.get("window_loss", "0")),
                      total_loss=None if kw.get("total_loss") is None else D(kw["total_loss"]))
        self.assertEqual(house, hand, (pair, E, cash, kw))
        return house, book, r

    def test_a_one_etf_lot_is_half_the_sleeve(self):
        for pair in PAIRS:
            seats, sleeve = pair
            for E in ("1000", "2000", "2229"):
                lot = D(sleeve) * D("0.5") * D(E)
                [(usd, binding)], _, r = self.both(pair, E, str(D(E) + 500), [("a", "SPY")])
                self.assertEqual((usd, binding), (lot, "intent"), (pair, E))
                self.assertEqual(lot, X.figures(r)["lot"] * D(E))
                [(usd, binding)], _, _ = self.both(pair, E, str(D(E) + 500), [("a", "SPY")], share="1")
                self.assertEqual((usd, binding), (lot, "sleeve_cap"), (pair, E))
                (_, _), (again, name) = self.both(pair, E, str(D(E) + 500), [("a", "SPY"), ("a", "SPY")])[0]
                self.assertEqual((again, name), (ZERO, "sleeve_cap"), "no second lot of the same ETF")

    def test_every_seat_in_its_own_etf(self):
        """Each seat's one-ETF lot, one after another, the account all the capital (cash = E) or with cash to spare:
        the whole lots that fit are the closed forms' counts, and nothing is ever held past a cap."""
        for pair in PAIRS:
            seats, sleeve = pair
            for E in ("1000", "2000", "2229", "3000"):
                for spare in (False, True):
                    cash = str(D(E) + (5000 if spare else 0))
                    house, book, r = self.both(pair, E, cash, self.seats_in_their_own_etfs(seats))
                    f = X.figures(r, E=D(E))
                    whole = sum(1 for usd, binding in house if binding == "intent")
                    if spare:   # cash is not what binds: the invested cap alone, and the window
                        by_invested = min(seats, int((r.invested * D(E)) // (f["lot"] * D(E))))
                        self.assertEqual(whole, min(by_invested, f["budget_fit"]), (pair, E, house))
                    else:
                        self.assertEqual(whole, min(f["cash_fit"], f["budget_fit"]), (pair, E, house))
                    self.assertTrue(all(usd == f["lot"] * D(E) for usd, binding in house if binding == "intent"))
                    self.assertLessEqual(book.invested, r.invested * book.E)
                    self.assertLessEqual(r.weight * book.invested, r.window)
                    self.assertGreaterEqual(book.cash - book.invested, r.reserve)

    def test_one_etf_across_programs(self):
        """Every seat in the SAME ETF: `same` whole lots, then what the instrument cap has left (`rest` x E, skipped
        under the minimum order), then nothing; never above the owner's 50% of E."""
        for pair in PAIRS:
            seats, sleeve = pair
            for E in ("1000", "2000", "2229"):
                asks = [(f"p{i + 1}", "SPY") for i in range(seats)]
                house, book, r = self.both(pair, E, str(D(E) + 5000), asks)
                f = X.figures(r, E=D(E))
                lot, rest = f["lot"] * D(E), f["rest"] * D(E)
                expected = [(lot, "intent")] * min(seats, f["same"])
                later = seats - len(expected)
                if later and rest >= r.min_order:       # the next program takes what is left, the others nothing
                    expected += [(rest, "instrument")] + [(ZERO, "instrument")] * (later - 1)
                elif later and rest > 0:                # what is left is under the minimum order, for each of them
                    expected += [(ZERO, "min_order")] * later
                else:
                    expected += [(ZERO, "instrument")] * later
                self.assertEqual(house, expected, (pair, E))
                self.assertLessEqual(book.held("SPY"), r.etf * book.E)

    def test_the_window_and_the_total_cut_by_name(self):
        """Losses already in the shared budget: the first seat's lot is the lower of the lot and the budget's room
        over the weight, named "budget" when cut; with nothing left, refused."""
        for pair in PAIRS:
            for window_loss, total_loss in (("370", None), ("0", "790"), ("100", "100"), ("400", "400"), ("43.05", None)):
                house, _, r = self.both(pair, "2000", "2500", [("a", "SPY"), ("b", "QQQ")], window_loss=window_loss,
                                        total_loss=total_loss)
                lot = r.sleeve * r.etf * D("2000")
                room = min(r.window - D(window_loss), r.total - D(total_loss or window_loss)) / r.weight
                first = (lot, "intent") if room >= lot else (room, "budget") if room >= r.min_order else \
                    (ZERO, "budget" if room <= 0 else "min_order")
                self.assertEqual(house[0], first, (pair, window_loss, total_loss))

    def test_no_order_of_asks_takes_the_lane_past_its_caps(self):
        """Every rotation of the asks (every seat, four ETFs, half a sleeve and a whole one): never above 1.00 x E
        invested, 0.50 x E in one ETF, half a sleeve in one ETF, a whole sleeve a program, cash under the reserve,
        or open risk above the window."""
        for pair in PAIRS:
            seats, sleeve = pair
            programs = [f"p{i + 1}" for i in range(seats)]
            asks = [(p, s) for p in programs for s in ETFS[:4]]
            for start in range(0, len(asks), 3):
                for share, cash in itertools.product(("0.5", "1"), ("1000", "1500")):
                    house, book, r = self.both(pair, "1000", cash, asks[start:] + asks[:start], share=share)
                    self.assertLessEqual(book.invested, r.invested * book.E)
                    self.assertGreaterEqual(book.cash - book.invested, r.reserve)
                    own_sleeve = r.sleeve * book.E
                    for symbol in ETFS[:4]:
                        self.assertLessEqual(book.held(symbol), r.etf * book.E)
                    for program in programs:
                        own = [usd for (p, _), usd in book.lots.items() if p == program]
                        self.assertLessEqual(sum(own, ZERO), own_sleeve)
                        self.assertTrue(all(usd <= r.etf * own_sleeve for usd in own))
                    self.assertLessEqual(r.weight * book.invested, r.window)

    def test_the_closed_forms_agree_with_the_walk(self):
        """`figures` against `walk` alone (the hand rule's two forms agree before either is held to the House)."""
        for pair in PAIRS:
            seats, sleeve = pair
            r = X.rows_of(X.constitution_at(*pair))
            for E in (D("1000"), D("2000"), D("2229"), D("2666"), D("2667"), D("5000")):
                f = X.figures(r, E=E)
                own = self.seats_in_their_own_etfs(seats)
                # The cash rule alone: a budget far away (losses cannot be negative, so a window of its own).
                far = replace(r, window=D("1000000"), total=D("1000000"))
                self.assertEqual(sum(1 for _, b in X.walk(far, E, E, own) if b == "intent"), f["cash_fit"], (pair, E))
                # The window alone: cash far away, the invested cap far away.
                rich = replace(r, invested=D("100"))
                self.assertEqual(sum(1 for _, b in X.walk(rich, E, E * 100, own) if b == "intent"), f["budget_fit"],
                                 (pair, E))
            f = X.figures(r)
            every = X.walk(replace(r, invested=D("100")), D(f["budget_e"]), D(f["budget_e"]) * 100,
                           self.seats_in_their_own_etfs(seats))
            self.assertTrue(all(b == "intent" for _, b in every), (pair, "all seats fit the window at budget_e"))
            over = X.walk(replace(r, invested=D("100")), D(f["budget_e"] + 1), D(f["budget_e"] + 1) * 100,
                          self.seats_in_their_own_etfs(seats))
            self.assertEqual(over[-1][1], "budget", (pair, "one dollar of E past it the window cuts the last seat's lot"))


class ASizedProgram(unittest.TestCase):
    """(d) A Sized program's sleeve is never below the Probe's, at any pair. At A20's design the Sized cap (0.50) equals
    the Probe sleeve, so it IS the Probe's and a Sized program's lot would be a Probe's lot. THE STEP ITSELF IS PARKED
    (`sized.min_trades` 1000, league/tests/test_equity_bands_money.py `TheSizingUpStepIsParked`): no equity program is
    Sized at this table."""

    GOOD = tuple(0.004 + (0.006 if i % 2 == 0 else -0.006) for i in range(24))
    RECORDS = (GOOD, tuple(0.0025 + (0.03 if i % 2 == 0 else -0.03) for i in range(400)),
               tuple(-0.01 + (0.02 if i % 2 == 0 else -0.02) for i in range(40)), (0.01,), ())

    def test_its_sleeve_is_the_probes_and_so_is_its_lot_at_a20s_design(self):
        eq = A20.equity
        self.assertEqual(EQ.sized_min_trades, 1000)
        self.assertFalse(sized_up(record(self.GOOD), EQ)[0], "parked: no record of the first weeks sizes up")
        self.assertTrue(sized_up(record(self.GOOD), replace(EQ, sized_min_trades=20))[0],
                        "a record that meets every leg of the pre-registered rule")
        for returns in self.RECORDS:
            share = sized_sleeve_share(record(returns), eq)
            self.assertGreaterEqual(share, eq.probe_sleeve_share, returns[:2])
            self.assertEqual(share, D("0.50"), returns[:2])
            out = lane("1000", "1500").buy("s", "SPY", sleeve_share=share)
            self.assertEqual((out.usd, out.binding), (D("250"), "intent"), returns[:2])

    def test_at_every_pair_it_is_never_below_the_probes_nor_above_the_cap(self):
        for pair in PAIRS:
            eq = X.table_at(*pair).equity
            for returns in self.RECORDS:
                share = sized_sleeve_share(record(returns), eq)
                self.assertTrue(eq.probe_sleeve_share <= share <= eq.sized_sleeve_share, (pair, returns[:2], share))
                out = X.Lane(X.table_at(*pair), "1000", "1500").buy("s", "SPY", sleeve_share=share)
                self.assertEqual((out.usd, out.binding), (share * D("0.5") * D("1000"), "intent"), (pair, returns[:2]))
            self.assertFalse(sized_up(record(self.GOOD), eq)[0], f"{pair}: parked")

    def test_the_owners_lines_bind_a_sized_program_as_they_bind_a_probe(self):
        share = sized_sleeve_share(record(self.GOOD), A20.equity)
        book = lane("1000", "1500")
        book.buy("p", "SPY")                                            # a Probe program holds SPY
        book.buy("q", "SPY")                                            # and another: the instrument's 0.50 x E
        out = book.buy("s", "SPY", sleeve_share=share)                  # the Sized one is refused by the same cap
        self.assertEqual((out.usd, out.binding), (ZERO, "instrument"))
        self.assertEqual(book.held("SPY"), D("0.50") * book.E)


# (release 1019l, the owner's goal V3: these mechanisms on release 1019i's money table, league/tests/v2_walls.py;
# the V3 rows' own effects are league/tests/test_v3_walls.py's)
from league.tests import v2_walls as _V2  # noqa: E402
from league.tests.v2_walls import tearDownModule  # noqa: E402,F401


def setUpModule() -> None:  # noqa: N802 - unittest's name
    """Release 1019i's table (league/tests/v2_walls.py), and this module's tables built again on it."""
    _V2.setUpModule()
    global TABLE, EQ, A20, WEIGHT, PAIRS
    TABLE = M.Table.from_constitution()
    EQ = TABLE.equity
    A20 = X.table_at(*X.REFERENCE)
    WEIGHT = EQ.open_risk_weight["etf"]
    PAIRS = tuple(dict.fromkeys((*X.CANDIDATES, X.in_force())))

if __name__ == "__main__":
    unittest.main()
