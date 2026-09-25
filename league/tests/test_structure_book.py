"""A book whose venue holds a structure's LEGS (the Alpaca practice account; Sept 25, 2026, Track P).

The book holds each level-3 structure as ONE instrument priced at S = net value + collateral K
(`league/structures.py`); the venue (`LegsBroker`, which fills and holds as the Alpaca adapter reports)
holds one net position a contract, a short leg negative, and on a margin account ADDS a credit to cash.
These tests pin what the book does at that boundary: reconciliation exact to the cent with a credit
structure open (the collateral offset), legs of several structures netted at the venue, a restart with a
structure open, the per-leg fee, the netting refusal, the time rule, and a broken structure (a leg gone,
a short no structure explains) closed at once with an error alert. Single contracts and stocks are
unchanged.
"""

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from ltcm.broker import Instrument, Order, Position, Quote, money

from league import structures
from league.book import BREAK_AFTER, BREAK_SOURCE, Book, Intent, Limits, position_key
from league.fees import Fees
from league.ledger import HOUSE, Ledger
from league.tests.fakes import Clock, FakeBroker, iso, without_real_entry_rules

D = Decimal
V = "alpaca-paper"
#: Friday Sept 25, 2026, 15:00Z: 11:00 New York, inside the session.
SESSION = 1790348400.0


def occ(strike, right="C", expiry="260928"):
    return f"SPY{expiry}{right}{int(D(str(strike)) * 1000):08d}"


def contract(strike, right="C", expiry="260928"):
    return structures.Leg(Instrument("option", "SPY", V, multiplier="100", expiry=f"20{expiry[:2]}-{expiry[2:4]}-{expiry[4:]}",
                                     strike=str(strike), right="call" if right == "C" else "put"), 1).instrument


def held(kind, legs):
    return structures.instrument(structures.classify(kind, [structures._leg_from(V, row) for row in legs]), V)


def leg(strike, role, right="C", ratio=None, expiry="260928"):
    row = {"occ": occ(strike, right, expiry), "role": role}
    if ratio:
        row["ratio"] = ratio
    return row


CONDOR = held("iron_condor", [leg(580, "long", "P"), leg(581, "short", "P"), leg(590, "short", "C"), leg(591, "long", "C")])
PUT_CREDIT = held("credit_vertical", [leg(580, "long", "P"), leg(581, "short", "P")])
CALL_DEBIT = held("debit_vertical", [leg(585, "long"), leg(586, "short")])


class LegsBroker(FakeBroker):
    """A venue account that holds a structure's LEGS, as Alpaca does. An order on a held structure is
    one multi-leg order that fills every leg at once when its limit meets the structure's touch: to
    open, long legs at the ask and short legs at the bid (the reverse to close); cash moves by what
    each leg paid or received (a credit ADDS to cash, a margin account) less the venue's fee on every
    leg's contracts; positions are one net quantity a contract, a short negative. It reports the
    order back as ONE fill of the held instrument at S = K + sum(sign x ratio x leg price), which is
    what `AlpacaBroker.parse_order` reports."""

    def __init__(self, *args, option_clearing=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.caps |= {"structure_legs", "mleg"}
        self.fees = Fees(self.fees.family, option_clearing=option_clearing)
        self.answers: list[dict] = []

    def leg_quote(self, strike, right, bid, ask, expiry="260928"):
        self.set_quote(contract(strike, right, expiry), bid, ask)

    def quote(self, instrument):
        if not structures.is_structure(instrument):
            return super().quote(instrument)
        spec = structures.spec_of(instrument)
        touches = {l.occ: self.quotes.get(l.instrument.key, (None, None)) for l in spec.legs}
        bid, ask = structures.quote(spec, touches)
        return Quote(instrument, bid, ask, None, self.clock_iso, "fake:structure", delayed=False)

    def submit(self, intent):
        if not structures.is_structure(intent.instrument):
            return super().submit(intent)
        self.submitted.append(intent)
        order = Order.from_intent(intent, venue=self.venue)
        if order.id in self.orders:
            return self.orders[order.id]
        self._n += 1
        order.broker_order_id = f"venue-{self._n}"
        order.status = "accepted"
        self.orders[order.id] = order
        bid, ask = self.quote(intent.instrument).bid, self.quote(intent.instrument).ask
        if (intent.side == "buy" and ask is not None and intent.limit_price >= ask) or (
                intent.side == "sell" and bid is not None and intent.limit_price <= bid):
            self.fill_structure(order, intent.quantity)
        return order

    def fill_structure(self, order, quantity, legs=None):
        """Fill `quantity` structures on `legs` (every leg by default: pass fewer to break one)."""
        spec = structures.spec_of(order.instrument)
        opening = order.side == "buy"
        value = spec.collateral
        for part in spec.legs:
            bid, ask = self.quotes[part.instrument.key]
            buys = (part.sign > 0) == opening
            price = ask if buys else bid
            value += part.sign * part.ratio * price
            if legs is not None and part.occ not in legs:
                continue
            contracts = quantity * part.ratio
            fee = self.fees.charge(part.instrument, "buy" if buys else "sell", contracts, price).usd
            self.cash += (-contracts if buys else contracts) * price * 100 - fee
            inst, now = self.held.get(part.instrument.key, (part.instrument, D(0)))
            self.held[part.instrument.key] = (inst, now + (contracts if buys else -contracts))
        before = order.filled_quantity
        order.filled_quantity = before + quantity
        order.average_price = ((order.average_price or D(0)) * before + value * quantity) / order.filled_quantity
        order.status = "filled" if order.filled_quantity >= order.quantity else "partially_filled"

    def positions(self):
        return [Position(inst, qty, D(0)) for inst, qty in self.held.values() if qty != 0]

    def drain_structure_answers(self):
        out, self.answers = self.answers, []
        return out


class StructureBookCase(unittest.TestCase):
    option_clearing = False

    def setUp(self):
        self._rules = without_real_entry_rules()
        self._rules.start()
        self.addCleanup(self._rules.stop)
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.clock = Clock(SESSION)
        self.ledger = Ledger(Path(self.dir.name) / "ledger.sqlite", clock=self.clock)
        self.addCleanup(self.ledger.close)
        self.broker = LegsBroker(V, cash="98000", option_clearing=self.option_clearing)
        self.broker.clock_iso = iso(self.clock)
        self.book = self.new_book()
        self.n = 0
        # A $1-wide SPY condor: 580/581 puts, 590/591 calls.
        self.broker.leg_quote(580, "P", "0.09", "0.11")
        self.broker.leg_quote(581, "P", "0.29", "0.31")
        self.broker.leg_quote(590, "C", "0.34", "0.36")
        self.broker.leg_quote(591, "C", "0.11", "0.13")
        self.broker.leg_quote(585, "C", "2.00", "2.04")
        self.broker.leg_quote(586, "C", "1.50", "1.54")
        self.book.reconcile()

    def new_book(self):
        return Book(V, self.broker, self.ledger, fees=Fees("alpaca", option_clearing=self.option_clearing), real_money=False,
                    clock=self.clock)

    def seat(self, agent, usd="200", position="100", order="75"):
        self.book.limits[agent] = Limits(D(position), D(order), asset_classes=("equity", "option"))
        self.book.stake(agent, usd)

    def intent(self, agent, instrument, side, quantity, limit):
        self.n += 1
        return Intent.new(agent=agent, instrument=instrument, side=side, quantity=quantity, order_type="limit", limit_price=limit,
                          time_in_force="day", reason=f"test {self.n}", created_at=iso(self.clock), nonce=str(self.n))

    def trade(self, agent, instrument, side, quantity, limit):
        outcome = self.book.submit([self.intent(agent, instrument, side, quantity, limit)])[0]
        return outcome

    def alerts(self):
        return [e.payload for e in self.ledger.iter(kinds="ops.alert")]


class Reconciliation(StructureBookCase):
    def test_a_credit_structure_open_on_a_margin_account_reconciles_to_the_cent(self):
        self.seat("a1")
        cash_before = self.broker.cash
        outcome = self.trade("a1", CONDOR, "buy", "1", "0.62")
        self.assertEqual(outcome.status, "filled", outcome.detail)
        # Opened at the touch: long legs at the ask, short at the bid: a 0.64 - 0.40 = 0.36 credit... K 1 + 0.11 + 0.13 - 0.29 - 0.34 = 0.61
        holding = self.book.account("a1").holdings[CONDOR.key]
        self.assertEqual((holding.quantity, holding.cost), (D(1), D("61")))
        self.assertEqual(self.broker.cash - cash_before, D("39"))  # the venue ADDED the $39 credit
        result = self.book.reconcile()
        self.assertTrue(result.ok, result.detail)
        self.assertEqual(result.cash_diff, D(0))
        self.assertEqual(result.position_diffs, {})
        # Closed at the touch: bid_S = 1 + 0.09 + 0.11 - 0.31 - 0.36 = 0.53: realized (0.53 - 0.61) x 100.
        outcome = self.trade("a1", CONDOR, "sell", "1", "0.53")
        self.assertEqual(outcome.status, "filled", outcome.detail)
        sale = [e.payload for e in self.ledger.iter(kinds="book.fill") if e.payload.get("side") == "sell" and e.agent == "a1"][-1]
        self.assertEqual((D(sale["realized"]), sale["flat"]), (D("-8"), True))  # ONE closed trade
        result = self.book.reconcile()
        self.assertTrue(result.ok, result.detail)
        self.assertEqual(result.cash_diff, D(0))
        self.assertEqual({k: v for k, (i, v) in self.broker.held.items() if v}, {})

    def test_a_debit_structure_reconciles_and_its_legs_never_show_as_positions(self):
        self.seat("a1")
        self.assertEqual(self.trade("a1", CALL_DEBIT, "buy", "1", "0.54").status, "filled")
        result = self.book.reconcile()
        self.assertTrue(result.ok, result.detail)
        self.assertEqual(self.book.account("a1").holdings[CALL_DEBIT.key].cost, D("54"))

    def test_two_structures_sharing_a_short_leg_net_at_the_venue_and_reconcile(self):
        self.seat("a1")
        self.seat("a2")
        self.broker.leg_quote(581, "P", "0.40", "0.42")  # a 0.29 credit on the 580/581 put vertical: $71 at risk
        self.assertEqual(self.trade("a1", CONDOR, "buy", "1", "0.52").status, "filled")
        self.assertEqual(self.trade("a2", PUT_CREDIT, "buy", "1", "0.72").status, "filled")
        self.assertEqual(self.broker.held[contract(581, "P").key][1], D(-2))  # one net position a contract
        result = self.book.reconcile()
        self.assertTrue(result.ok, result.detail)
        self.assertEqual(result.cash_diff, D(0))

    def test_a_restart_with_a_structure_open_reconciles_without_a_freeze(self):
        self.seat("a1")
        self.trade("a1", CONDOR, "buy", "1", "0.62")
        self.assertTrue(self.book.reconcile().ok)
        restarted = self.new_book()
        self.assertEqual(restarted.account("a1").holdings[CONDOR.key].quantity, D(1))
        result = restarted.reconcile()
        self.assertTrue(result.ok, result.detail)
        self.assertIsNone(restarted.frozen)

    def test_a_single_contract_and_a_stock_are_unchanged(self):
        self.seat("a1")
        spy = Instrument("equity", "SPY", V)
        self.broker.set_quote(spy, "600.00", "600.02")
        call = contract(600, "C")
        self.broker.set_quote(call, "0.50", "0.52")
        self.assertEqual(self.trade("a1", call, "buy", "1", "0.52").status, "filled")
        self.assertEqual(self.book.submit([Intent.new(agent="a1", instrument=spy, side="buy", quantity="0.05", reason="t",
                                                       created_at=iso(self.clock))])[0].status, "filled")
        self.assertTrue(self.book.reconcile().ok)
        self.assertEqual(self.broker.submitted[-2].instrument.market_id, None)


class Fees_(StructureBookCase):
    option_clearing = True

    def test_every_leg_pays_the_venues_fee_on_its_own_contracts(self):
        self.seat("a1")
        self.trade("a1", CONDOR, "buy", "1", "0.62")
        fill = [e.payload for e in self.ledger.iter(kinds="book.fill") if e.agent == "a1"][-1]
        self.assertEqual(D(fill["fee_usd"]), D("0.12"))  # four legs, $0.03 each (0.025 rounded up a fill)
        self.assertTrue(self.book.reconcile().ok)


class Entries(StructureBookCase):
    def test_an_entry_the_venue_would_net_against_an_opposite_leg_is_refused(self):
        self.seat("a1")
        self.seat("a2")
        self.broker.leg_quote(581, "P", "0.40", "0.42")
        self.assertEqual(self.trade("a1", CONDOR, "buy", "1", "0.52").status, "filled")  # short the 581 put
        long_581 = contract(581, "P")
        outcome = self.trade("a2", long_581, "buy", "1", "0.42")
        self.assertEqual(outcome.status, "refused")
        self.assertIn("one net position a contract", outcome.detail)
        # The same side is no conflict: a second short 581 put nets to -2 and each closes as its own.
        self.assertEqual(self.trade("a2", PUT_CREDIT, "buy", "1", "0.72").status, "filled")

    def test_a_structure_expiring_today_is_entered_only_until_1430_new_york(self):
        today = held("iron_condor", [leg(580, "long", "P", expiry="260925"), leg(581, "short", "P", expiry="260925"),
                                     leg(590, "short", "C", expiry="260925"), leg(591, "long", "C", expiry="260925")])
        for strike, right, bid, ask in ((580, "P", "0.09", "0.11"), (581, "P", "0.29", "0.31"), (590, "C", "0.34", "0.36"),
                                        (591, "C", "0.11", "0.13")):
            self.broker.leg_quote(strike, right, bid, ask, expiry="260925")
        self.seat("a1")
        self.assertEqual(self.trade("a1", today, "buy", "1", "0.62").status, "filled")  # 11:00 New York
        self.clock.now = SESSION + 3.5 * 3600  # 14:30 New York
        self.broker.clock_iso = iso(self.clock)
        outcome = self.trade("a1", today, "buy", "1", "0.62")
        self.assertEqual(outcome.status, "refused")
        self.assertIn("until 14:30 New York", outcome.detail)


class Broken(StructureBookCase):
    """A structure the venue no longer holds whole is closed at once; nothing is ever adopted short."""

    def open_condor(self):
        self.seat("a1")
        self.assertEqual(self.trade("a1", CONDOR, "buy", "1", "0.62").status, "filled")
        self.assertTrue(self.book.reconcile().ok)

    def house(self):
        return {k: h.quantity for k, h in self.book.account(HOUSE).holdings.items() if h.instrument.asset_class == "option"}

    def test_a_long_leg_gone_breaks_the_structure_and_the_house_closes_the_rest_shorts_first(self):
        self.open_condor()
        self.broker.held.pop(contract(580, "P").key)  # the long put exercised away: the short 581 put is naked
        first = self.book.reconcile()
        self.assertFalse(first.ok)  # one reading may be a fill in flight: nothing is done yet
        self.assertIn(CONDOR.key, self.book.account("a1").holdings)
        self.assertEqual(BREAK_AFTER, 2)
        second = self.book.reconcile()
        self.assertTrue(second.ok, second.detail)  # the House row took the difference: no freeze
        self.assertNotIn(CONDOR.key, self.book.account("a1").holdings)
        settle = [e.payload for e in self.ledger.iter(kinds="book.settle")][-1]
        self.assertEqual((settle["result"], D(settle["pnl"])), ("broken", D("-61")))  # its whole cost, never flattered
        alert = [a for a in self.alerts() if a.get("structure_break")][-1]
        self.assertEqual(alert["level"], "error")
        # The House's buy-backs of both short legs went out as exits (the adapter's buy_to_close), at the ask.
        buys = [i for i in self.broker.submitted if i.side == "buy" and not structures.is_structure(i.instrument)]
        self.assertEqual(sorted((i.instrument.strike, i.instrument.right, i.purpose, i.limit_price) for i in buys),
                         [(D(581), "put", "exit", D("0.31")), (D(590), "call", "exit", D("0.36"))])
        self.assertFalse([i for i in self.broker.submitted if i.side == "sell" and not structures.is_structure(i.instrument)])
        self.assertTrue(self.book.reconcile().ok)
        # Once no short is left, the long call is sold at the bid.
        sells = [i for i in self.broker.submitted if i.side == "sell" and not structures.is_structure(i.instrument)]
        self.assertEqual([(i.instrument.strike, i.limit_price) for i in sells], [(D(591), D("0.11"))])
        final = self.book.reconcile()
        self.assertTrue(final.ok, final.detail)
        self.assertEqual(self.house(), {})
        self.assertEqual({k: v for k, (i, v) in self.broker.held.items() if v}, {})
        self.assertEqual(final.cash_diff, D(0))

    def test_a_short_no_structure_explains_is_bought_back_and_never_adopted(self):
        self.open_condor()
        stray = contract(575, "P")
        self.broker.leg_quote(575, "P", "0.04", "0.06")
        self.broker.held[stray.key] = (stray, D(-1))  # a leg an uneven fill left, on a contract no structure holds
        self.broker.cash += D("4")
        self.assertFalse(self.book.reconcile().ok)
        self.book.reconcile()
        self.assertIn(CONDOR.key, self.book.account("a1").holdings)  # the condor is whole and stays
        self.assertNotIn(position_key(stray), self.book.baseline_positions)  # never adopted short
        self.assertFalse(any("adopted" in e.payload["note"] for e in self.ledger.iter(kinds="book.baseline")))
        buys = [i for i in self.broker.submitted if i.side == "buy" and not structures.is_structure(i.instrument)]
        self.assertEqual([(i.instrument.strike, i.purpose, i.limit_price) for i in buys], [(D(575), "exit", D("0.06"))])
        final = self.book.reconcile()
        self.assertTrue(final.ok, final.detail)
        self.assertNotIn(stray.key, {k: v for k, (i, v) in self.broker.held.items() if v})
        self.assertEqual(self.house(), {})

    def test_a_short_beyond_a_structures_leg_closes_the_whole_structure(self):
        self.open_condor()
        extra = contract(581, "P")
        inst, qty = self.broker.held[extra.key]
        self.broker.held[extra.key] = (inst, qty - 1)  # -2 where the one condor explains -1: the owner's rule closes it all
        self.broker.cash += D("29")  # what selling it brought in, which no fill the book saw explains
        self.assertFalse(self.book.reconcile().ok)
        second = self.book.reconcile()
        self.assertEqual((second.position_diffs, second.cash_diff), ({}, D(29)))  # every contract agrees; the cash waits
        self.assertNotIn(CONDOR.key, self.book.account("a1").holdings)
        buys = [i for i in self.broker.submitted if i.side == "buy" and not structures.is_structure(i.instrument)]
        self.assertEqual(sorted((i.instrument.strike, i.quantity) for i in buys), [(D(581), D(2)), (D(590), D(1))])
        self.book.reconcile()  # the longs next, at the bid; the $29 is the practice book's to adopt as cash
        final = self.book.reconcile()
        self.assertTrue(final.ok, final.detail)
        self.assertFalse([k for k, v in self.book.baseline_positions.items() if v < 0])
        self.assertEqual(self.house(), {})
        self.assertEqual({k: v for k, (i, v) in self.broker.held.items() if v}, {})

    def test_nothing_is_done_while_an_order_on_the_contract_is_open(self):
        self.open_condor()
        resting = self.trade("a1", CONDOR, "sell", "1", "0.58")  # rests: the bid is 0.53
        self.assertEqual(resting.status, "resting")
        self.broker.held.pop(contract(580, "P").key)
        for _ in range(3):
            self.assertFalse(self.book.reconcile().ok)
        self.assertIn(CONDOR.key, self.book.account("a1").holdings)
        self.assertFalse([a for a in self.alerts() if a.get("structure_break")])

    def test_outside_the_session_the_house_waits_to_close(self):
        self.open_condor()
        self.broker.held.pop(contract(580, "P").key)
        self.clock.now = SESSION + 8 * 3600  # 23:00Z
        self.broker.clock_iso = iso(self.clock)
        self.book.reconcile()
        self.assertTrue(self.book.reconcile().ok)
        self.assertFalse([i for i in self.broker.submitted if not structures.is_structure(i.instrument)])
        self.assertEqual(self.house()[contract(581, "P").key], D(-1))  # held on the House row, to be bought back

    def test_an_expired_structure_is_broken_and_its_rest_closed(self):
        self.open_condor()
        for key in list(self.broker.held):
            self.broker.held.pop(key)  # expired worthless: the venue shows none of its legs
        self.clock.now = SESSION + 4 * 86400  # Tuesday Sept 29, 15:00Z: the day after its expiry
        self.broker.clock_iso = iso(self.clock)
        self.assertEqual(self.book.expire_options(), 1)
        self.assertNotIn(CONDOR.key, self.book.account("a1").holdings)
        self.book.reconcile()
        final = self.book.reconcile()
        self.assertTrue(final.ok, final.detail)
        self.assertEqual(self.house(), {})


class VenueAnswers(StructureBookCase):
    def test_the_venues_answers_are_written_for_the_owner(self):
        self.broker.answers = [{"stage": "submit", "structure": "iron_condor", "venue": V, "detail": {"answer": {"status": "new"}}},
                               {"stage": "uneven", "structure": "iron_condor", "venue": V, "detail": {}}]
        self.book.reconcile()
        rows = [a for a in self.alerts() if a.get("structure_answer")]
        self.assertEqual([(a["level"], a["structure_answer"]["stage"]) for a in rows], [("info", "submit"), ("error", "uneven")])


if __name__ == "__main__":
    unittest.main()
