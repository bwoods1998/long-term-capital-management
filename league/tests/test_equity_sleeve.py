"""THE PROBE SLEEVE AT 0.66 (the captain's amendment A20, Oct 11, 2026: `equity_money.probe.sleeve_share` and its bound,
league/constitution.py): what the equity lane holds at the money table in force. Every entry here is sized by the one
real sizing function (`league/equity/sizing.py` `size_entry`) on the facts the book states to it (`league/equity/live.py`
`EquityBook._size`), by hand: three seats, first come; a one-ETF program's lot is half its sleeve, 0.33 x E; and every
owner line still binds, BY NAME: an ETF at most 0.50 x E across all programs ("instrument"), at most 1.00 x E invested
("invested"), the House-wide cash reserve ("cash"), and the shared loss budget's room over the ETF weight ("budget"). A
Sized program keeps the Probe sleeve (`league/equity/bands.py` `sized_sleeve_share`). Invented figures only (an E, a
price of $100 a share, losses already in the budget); standard library only."""

import unittest
from decimal import Decimal as D

from league.constitution import CONSTITUTION, EQUITY_MONEY_BOUNDS
from league.equity.bands import EquityRecord, sized_sleeve_share, sized_up
from league.equity.sizing import Sized, SizingInputs, size_entry
from league.live import money as M

TABLE = M.Table.from_constitution()
EQ = TABLE.equity
ZERO = D(0)
WEIGHT = EQ.open_risk_weight["etf"]


class Lane:
    """An equity lane by hand. Programs buy at their limit and are filled whole at it (no slippage, no fee, no mark
    move), each entry sized by the real `size_entry` on the facts `EquityBook._size` states: the sleeve is
    `probe.sleeve_share` x E (or the share passed, a Sized program's), its free cash the sleeve less the program's own
    lots, the account's holding of the symbol every program's, the invested sum every lot, the available cash the
    account's cash less the reserve (`money.available_cash`), and the budget's room the lower of the window's and the
    total's less the open risk at the ETF weight (`EquityBook._budget_room`). `cash` is the account's cash before any
    lot (above E when the grant's capital, not the account, sets E); `window_loss` and `total_loss` are realized Probe
    losses already in the shared budget."""

    def __init__(self, E: str, cash: str, *, window_loss: str = "0", total_loss: str | None = None):
        self.E, self.cash = D(E), D(cash)
        self.window_loss = D(window_loss)
        self.total_loss = self.window_loss if total_loss is None else D(total_loss)
        self.lots: dict[tuple[str, str], D] = {}

    @property
    def invested(self) -> D:
        return sum(self.lots.values(), ZERO)

    def held(self, symbol: str) -> D:
        return sum((usd for (_, s), usd in self.lots.items() if s == symbol), ZERO)

    def facts(self, program: str, symbol: str, *, share: str = "0.5", limit: str = "100.00",
              sleeve_share: D | None = None) -> SizingInputs:
        sleeve = (EQ.probe_sleeve_share if sleeve_share is None else sleeve_share) * self.E
        own = sum((usd for (p, _), usd in self.lots.items() if p == program), ZERO)
        cash = self.cash - self.invested
        at_risk = WEIGHT * self.invested
        return SizingInputs(
            symbol=symbol, klass="etf", share=D(share), usd=None, limit_price=D(limit), E=self.E, sleeve_equity=sleeve,
            sleeve_free_cash=max(ZERO, sleeve - own), sleeve_symbol_value=self.lots.get((program, symbol), ZERO),
            position_share=EQ.position_share["etf"], account_symbol_value=self.held(symbol), invested_now=self.invested,
            invested_share=EQ.invested_share,
            available_cash=M.available_cash({"cash": str(cash), "short_market_value": "0"}, working_buys_worst=ZERO,
                                            reserved=ZERO, reserve_usd=EQ.cash_reserve),
            cash=cash, any_short=False,
            budget_room=min(TABLE.probe_loss_budget - self.window_loss - at_risk,
                            TABLE.probe_loss_total - self.total_loss - at_risk),
            weight=WEIGHT, min_order_usd=EQ.min_order_usd)

    def buy(self, program: str, symbol: str, **kw) -> Sized:
        out = size_entry(self.facts(program, symbol, **kw))
        if out.usd > 0:
            self.lots[(program, symbol)] = self.lots.get((program, symbol), ZERO) + out.usd
        return out


def record(returns, *, pnl="50", bh_pnl="20", probe_sessions=10):
    returns = tuple(returns)
    return EquityRecord(n=len(returns), returns=returns, pnl=D(pnl), bh_pnl=D(bh_pnl), probe_sessions=probe_sessions,
                        realized_net=D(pnl))


class TheTableInForce(unittest.TestCase):
    def test_the_sleeve_the_seats_and_the_owners_lines(self):
        """A20 moved ONE row and its bound. The owner's lines it is sized inside are read here as they stand."""
        self.assertEqual((EQ.probe_sleeve_share, EQ.probe_max_programs), (D("0.66"), 3))
        self.assertEqual(EQUITY_MONEY_BOUNDS["probe.sleeve_share"], ("0", "0.66"))
        self.assertEqual((EQ.position_share["etf"], EQ.invested_share, EQ.cash_reserve, WEIGHT, EQ.min_order_usd),
                         (D("0.50"), D("1.00"), D("50"), D("0.20"), D("10")))
        self.assertEqual((TABLE.probe_loss_budget, TABLE.probe_loss_window, TABLE.probe_loss_total), (D("400"), 20, D("800")))
        self.assertNotIn("loss_budget_usd", CONSTITUTION["equity_money"]["probe"], "no second budget")
        # A one-ETF program's lot: the sleeve's own 50% rule (`size_entry`'s "sleeve_cap"), a third of E.
        self.assertEqual(EQ.probe_sleeve_share * EQ.position_share["etf"], D("0.33"))
        # Three sleeves ask for more than the account holds: the invested cap, not the sleeves, bounds the lane.
        self.assertGreater(EQ.probe_max_programs * EQ.probe_sleeve_share, EQ.invested_share)

    def test_a_one_etf_programs_lot_is_a_third_of_e(self):
        lane = Lane("1000", "1500")
        out = lane.buy("a", "SPY")                                      # the seeds' intent: half of the sleeve
        self.assertEqual((out.usd, out.qty, out.binding), (D("330"), D("3.3"), "intent"))
        whole = Lane("1000", "1500").buy("a", "SPY", share="1")         # the whole sleeve asked: the sleeve's 50% rule
        self.assertEqual((whole.usd, whole.binding), (D("330"), "sleeve_cap"))
        self.assertIn("SPY may hold $330.00 more in this program's sleeve (0.50 x $660.00", whole.reason)
        again = lane.buy("a", "SPY")                                    # and no second lot of the same ETF
        self.assertEqual((again.usd, again.binding), (ZERO, "sleeve_cap"))
        self.assertEqual(lane.held("SPY"), D("0.33") * lane.E)


class ThreeSeats(unittest.TestCase):
    """(a) Three one-ETF programs at the Probe sleeve hold 0.33 x E each, and the lane is never above 1.00 x E."""

    def test_three_lots_of_a_third_of_e_and_the_invested_cap_holds(self):
        lane = Lane("1000", "1500")                                     # E is the grant's capital: cash is not what binds
        for program, symbol in (("a", "SPY"), ("b", "QQQ"), ("c", "IWM")):
            out = lane.buy(program, symbol)
            self.assertEqual((out.usd, out.binding), (D("0.33") * lane.E, "intent"), (program, out))
        self.assertEqual(lane.invested, D("0.99") * lane.E)
        self.assertEqual(WEIGHT * lane.invested, D("0.198") * lane.E, "its open risk in the shared budget")
        # A fourth entry (a seated program's second ETF: its sleeve has the room) is CUT by the invested cap, by name.
        fourth = lane.buy("a", "DIA")
        self.assertEqual((fourth.usd, fourth.binding), (D("10"), "invested"))
        self.assertIn("cut from $330.00: the invested cap leaves $10.00 (1.00 x E $1000.00, less $990.00", fourth.reason)
        self.assertEqual(lane.invested, EQ.invested_share * lane.E)
        # And the next is REFUSED by it, by name: nothing is ever held above 1.00 x E.
        for program, symbol in (("b", "DIA"), ("c", "XLK"), ("a", "XLE")):
            fifth = lane.buy(program, symbol)
            self.assertEqual((fifth.usd, fifth.qty, fifth.binding), (ZERO, ZERO, "invested"), (program, fifth))
            self.assertTrue(fifth.reason.startswith("refused: the invested cap leaves $0.00"), fifth.reason)
        self.assertEqual(lane.invested, EQ.invested_share * lane.E)

    def test_a_remainder_under_the_minimum_order_is_skipped_and_names_the_invested_cap(self):
        lane = Lane("900", "1500")
        for program, symbol in (("a", "SPY"), ("b", "QQQ"), ("c", "IWM")):
            self.assertEqual(lane.buy(program, symbol).usd, D("297"))   # 0.33 x $900
        fourth = lane.buy("a", "DIA")                                   # the cap leaves $9.00: under the $10 minimum
        self.assertEqual((fourth.usd, fourth.binding), (ZERO, "min_order"))
        self.assertIn("the invested cap leaves $9.00", fourth.reason)
        self.assertLessEqual(lane.invested, EQ.invested_share * lane.E)

    def test_when_the_account_is_all_the_capital_the_cash_reserve_cuts_the_last_lot(self):
        """E is the lower of the account's equity and the grant's capital. When it is the account's own cash, the
        House-wide cash rule (the $50 reserve, A8.1) binds before the invested cap: the third lot is cut, by name."""
        lane = Lane("1000", "1000")
        self.assertEqual([lane.buy(p, s).binding for p, s in (("a", "SPY"), ("b", "QQQ"))], ["intent", "intent"])
        third = lane.buy("c", "IWM")
        self.assertEqual((third.usd, third.binding), (D("290"), "cash"))        # 1000 - 660 - the $50 reserve
        self.assertEqual(lane.invested, lane.E - EQ.cash_reserve)
        fourth = lane.buy("a", "DIA")
        self.assertEqual((fourth.usd, fourth.binding), (ZERO, "cash"))
        self.assertTrue(fourth.reason.startswith("refused: the House-wide available cash is $0.00"), fourth.reason)

    def test_no_order_of_entries_takes_the_lane_past_its_caps(self):
        """Every order of twelve asks (three programs, four ETFs, half a sleeve and a whole one): never above 1.00 x E
        invested, 0.50 x E in one ETF, half a sleeve in one ETF, a whole sleeve a program, or cash under the reserve."""
        import itertools

        asks = [(p, s) for p in ("a", "b", "c") for s in ("SPY", "QQQ", "IWM", "DIA")]
        for start in range(len(asks)):
            for share, cash in itertools.product(("0.5", "1"), ("1000", "1500")):
                lane = Lane("1000", cash)
                for program, symbol in asks[start:] + asks[:start]:
                    lane.buy(program, symbol, share=share)
                self.assertLessEqual(lane.invested, EQ.invested_share * lane.E)
                self.assertGreaterEqual(lane.cash - lane.invested, EQ.cash_reserve)
                sleeve = EQ.probe_sleeve_share * lane.E
                for symbol in ("SPY", "QQQ", "IWM", "DIA"):
                    self.assertLessEqual(lane.held(symbol), EQ.position_share["etf"] * lane.E)
                for program in ("a", "b", "c"):
                    own = [usd for (p, _), usd in lane.lots.items() if p == program]
                    self.assertLessEqual(sum(own, ZERO), sleeve)
                    self.assertTrue(all(usd <= EQ.position_share["etf"] * sleeve for usd in own))
                self.assertLessEqual(WEIGHT * lane.invested, TABLE.probe_loss_budget)


class OneEtf(unittest.TestCase):
    """(b) Two programs in the SAME ETF are held to 0.50 x E together by the instrument cap, by name."""

    def test_two_programs_in_one_etf_hold_half_of_e_together(self):
        lane = Lane("1000", "1500")
        first = lane.buy("a", "SPY")
        self.assertEqual((first.usd, first.binding), (D("330"), "intent"))
        second = lane.buy("b", "SPY")                                   # 0.50 x 1000 - 330, not its own 330
        self.assertEqual((second.usd, second.binding), (D("170"), "instrument"))
        self.assertIn("SPY may hold $170.00 more on the account (0.50 x E $1000.00, less $330.00 held and working across "
                      "all programs)", second.reason)
        self.assertEqual(lane.held("SPY"), EQ.position_share["etf"] * lane.E)
        third = lane.buy("c", "SPY")
        self.assertEqual((third.usd, third.binding), (ZERO, "instrument"))
        self.assertTrue(third.reason.startswith("refused: SPY may hold $0.00 more on the account"), third.reason)
        self.assertEqual(lane.held("SPY"), D("0.50") * lane.E, "never above the owner's 50%")
        # The instrument's cap is one ETF's: the third program's other ETF is sized whole.
        other = lane.buy("c", "QQQ")
        self.assertEqual((other.usd, other.binding), (D("330"), "intent"))

    def test_whole_sleeves_asked_change_nothing(self):
        lane = Lane("1000", "1500")
        self.assertEqual([(o.usd, o.binding) for o in (lane.buy("a", "SPY", share="1"), lane.buy("b", "SPY", share="1"),
                                                       lane.buy("c", "SPY", share="1"))],
                         [(D("330"), "sleeve_cap"), (D("170"), "instrument"), (ZERO, "instrument")])


class TheBudget(unittest.TestCase):
    """(c) The shared loss budget still cuts an entry when its room over the ETF weight (0.20) is the smaller."""

    def test_a_window_that_has_lost_cuts_the_lot_by_name(self):
        lane = Lane("1000", "1500", window_loss="370")                  # $30 of the $400 window left
        out = lane.buy("a", "SPY")
        self.assertEqual((out.usd, out.binding), (D("150"), "budget"))  # 30 / 0.20, under the lot's 330
        self.assertIn("cut from $330.00: the shared loss budget has $30.00 of room, $150.00 of etf at weight 0.20",
                      out.reason)
        self.assertEqual(WEIGHT * lane.invested, D("30"), "the lot's open risk is the room it was cut to")
        again = lane.buy("b", "QQQ")
        self.assertEqual((again.usd, again.binding), (ZERO, "budget"))
        self.assertTrue(again.reason.startswith("refused: the shared loss budget has $0.00 of room"), again.reason)

    def test_the_totals_room_cuts_when_it_is_the_lower(self):
        lane = Lane("1000", "1500", window_loss="0", total_loss="790")  # $10 of the $800 total left
        out = lane.buy("a", "SPY")
        self.assertEqual((out.usd, out.binding), (D("50"), "budget"))   # 10 / 0.20
        untouched = Lane("1000", "1500", window_loss="100", total_loss="100").buy("a", "SPY")
        self.assertEqual((untouched.usd, untouched.binding), (D("330"), "intent"), "room over the weight above the lot")

    def test_from_e_2000_the_budget_and_not_the_invested_cap_bounds_the_lane(self):
        """The window's $400 over the ETF weight is $2,000 of ETFs: at a larger E the third lot is cut by the budget
        and the lane stops there, under 1.00 x E, its open risk never above the window."""
        lane = Lane("3000", "4000")
        self.assertEqual([(o.usd, o.binding) for o in (lane.buy("a", "SPY"), lane.buy("b", "QQQ"))],
                         [(D("990"), "intent"), (D("990"), "intent")])
        third = lane.buy("c", "IWM")
        self.assertEqual((third.usd, third.binding), (D("20"), "budget"))       # (400 - 0.20 x 1980) / 0.20
        self.assertEqual(lane.invested, TABLE.probe_loss_budget / WEIGHT)
        self.assertLess(lane.invested, EQ.invested_share * lane.E)
        self.assertEqual(WEIGHT * lane.invested, TABLE.probe_loss_budget)
        fourth = lane.buy("a", "DIA")
        self.assertEqual((fourth.usd, fourth.binding), (ZERO, "budget"))
        # Under E = $2,000 the invested cap comes first (the lane's open risk is at most 0.20 x E, under the window).
        small = Lane("1000", "1500")
        for program, symbol in (("a", "SPY"), ("b", "QQQ"), ("c", "IWM"), ("a", "DIA"), ("b", "DIA")):
            self.assertNotEqual(small.buy(program, symbol).binding, "budget")
        self.assertEqual(WEIGHT * small.invested, D("0.20") * small.E)
        self.assertLess(WEIGHT * small.invested, TABLE.probe_loss_budget)


class ASizedProgram(unittest.TestCase):
    """(d) A Sized program's sleeve is never below the Probe's 0.66: with the Sized cap (0.50) under it, it IS the
    Probe's, so a Sized program's lot is a Probe's lot."""

    GOOD = tuple(0.004 + (0.006 if i % 2 == 0 else -0.006) for i in range(24))

    def test_its_sleeve_is_the_probes_and_so_is_its_lot(self):
        self.assertTrue(sized_up(record(self.GOOD), EQ)[0], "a record that meets every leg of the sizing-up rule")
        for returns in (self.GOOD, tuple(0.0025 + (0.03 if i % 2 == 0 else -0.03) for i in range(400)),
                        tuple(-0.01 + (0.02 if i % 2 == 0 else -0.02) for i in range(40)), (0.01,), ()):
            share = sized_sleeve_share(record(returns), EQ)
            self.assertGreaterEqual(share, EQ.probe_sleeve_share, returns[:2])
            self.assertEqual(share, D("0.66"), returns[:2])
            out = Lane("1000", "1500").buy("s", "SPY", sleeve_share=share)
            self.assertEqual((out.usd, out.binding), (D("330"), "intent"), returns[:2])

    def test_the_owners_lines_bind_a_sized_program_as_they_bind_a_probe(self):
        share = sized_sleeve_share(record(self.GOOD), EQ)
        lane = Lane("1000", "1500")
        lane.buy("p", "SPY")                                            # a Probe program holds SPY
        out = lane.buy("s", "SPY", sleeve_share=share)                  # the Sized one is cut by the same instrument cap
        self.assertEqual((out.usd, out.binding), (D("170"), "instrument"))
        self.assertEqual(lane.held("SPY"), D("0.50") * lane.E)


if __name__ == "__main__":
    unittest.main()
