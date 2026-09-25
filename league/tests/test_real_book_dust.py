"""H4 of the forward-first run (Sept 25, 2026): a real book never freezes on cents it can explain,
and never un-freezes on cents it cannot.

The evidence, read on the House box and the real Alpaca account (GET only):

- 02:38:59Z-04:03:42Z Sept 25: the real Alpaca book read "cash differs by 0.0149", "0.0168" and
  then "0.0108" (cash_venue 465.627638403755211532 against 465.61688803) every five minutes, frozen,
  with no fill and no fee in those hours. The book adds back the cash behind each resting crypto bid
  at `remaining x limit` to eighteen places; Alpaca holds each at that notional rounded half-up to
  the cent. Every reading booked the sum of those sub-cent errors as dust, and when four of eight
  bids were cancelled in one pass the error they took with them (-0.01075037) was left standing.
  With the holds rounded as the venue rounds them, every reading of 339 between Sept 24 00:00Z and
  04:26Z Sept 25 with no fill between reads the account's cash unchanged (465.63 since 18:52Z Sept 24).
- 04:11:50Z Sept 25, 1.2 s after the House restarted: the same +0.0108 was booked as dust and the
  book reconciled. `_fold` had counted every venue fill the book ever had (12) as "since the last
  reconciliation", so the first reading of the new process allowed $0.12 (and $0.12 of limit-fill
  fee slack). The same thing un-froze the Sept 24 option freeze (-0.0324) at 18:45:22Z, 1.0 s after a
  restart. On the real Kalshi book (139 fills) the first reading after a restart allowed $1.39.
- 18:19:57Z Sept 24: a one-contract AAL call buy on the real account. Its OCC clearing fee ($0.03,
  listed 11 s later) and $0.03 of ORF and CAT fees (listed at 20:35Z and 00:31Z) left the cash at the
  fill; the book froze on -0.0308, then -0.0324, until the restart above.
"""

import unittest
from decimal import ROUND_HALF_UP, Decimal
from unittest.mock import patch

from ltcm.broker import Instrument

from league.book import REAL_BOOK_DUST_BOUNDS, UNLISTED_FEE_HOURS, Book, Limits, real_book_dust_usd
from league.constitution import CONSTITUTION
from league.fees import Fees
from league.ledger import HOUSE, now_iso
from league.tests.fakes import FakeBroker
from league.tests.test_book import BookCase
from league.venues import instrument_for

D = Decimal
SOL = Instrument("crypto", "SOL-USD", "alpaca", market_id="SOL/USD")
XRP = Instrument("crypto", "XRP-USD", "alpaca", market_id="XRP/USD")
BTC = Instrument("crypto", "BTC-USD", "alpaca", market_id="BTC/USD")
#: The eight crypto bids resting on the real Alpaca account at 02:26Z Sept 25, 2026, as the venue
#: holds them (quantity, limit). The first four rested all night; the last four were cancelled by 02:49Z.
STAYED = [(SOL, "0.106315968", "116.0544365"), (SOL, "0.106378448", "115.987157142"),
          (XRP, "8.109862995", "1.515966438"), (XRP, "8.023898239", "1.517514854")]
CANCELLED = [(SOL, "0.107269653", "116.491025"), (XRP, "8.161663976", "1.526060499"),
             (SOL, "0.106604572", "116.299934999"), (XRP, "7.965209020", "1.5191064")]
#: 18:19:57Z Sept 24, 2026, when the real account's first option filled.
SEPT_24_OPTION_FILL = 1790273997.0


class RealAlpaca(BookCase):
    venue = "alpaca"
    real = True
    cash = "465.63"  # the real account's cash with its holds, Sept 24 18:52Z to Sept 25 04:37Z

    def new_book(self):
        # Every Alpaca book pays the OCC clearing fee at an option's fill (the House's own wiring: `InTheHouse` below).
        return Book(self.venue, self.broker, self.ledger, fees=Fees(self.family, option_clearing=True), real_money=True, clock=self.clock)

    def dust(self):
        return [e for e in self.ledger.iter(kinds="book.fill") if e.payload.get("source") == "dust" and e.payload.get("book") == self.venue]

    def alerts(self):
        return [e.payload for e in self.ledger.iter(kinds="ops.alert")]


class RestingBids(RealAlpaca):
    def setUp(self):
        super().setUp()
        self.broker.reserve_open_buys = True
        self.broker.set_quote(SOL, "115.50", "117.00")
        self.broker.set_quote(XRP, "1.50", "1.53")
        self.broker.set_quote(BTC, "80000", "80010")
        self.assertTrue(self.book.reconcile().ok)
        for agent in ("haghani-62", "haghani-63"):
            self.book.limits[agent] = Limits(D("500"), D("75"))
            self.book.stake(agent, "200")
        # A book that has traded (the real one had twelve fills): one that never has re-reads its
        # baseline on a difference instead of freezing (`Book.reconcile`).
        self.assertEqual(self.book.submit([self.intent("haghani-62", BTC, "buy", "0.0002")])[0].status, "filled")
        self.assertTrue(self.book.reconcile().ok)

    def rest(self, agent, bids):
        ids = []
        for instrument, quantity, limit in bids:
            outcome = self.book.submit([self.intent(agent, instrument, "buy", quantity, order_type="limit", limit_price=limit)])[0]
            self.assertEqual(outcome.status, "resting", outcome.detail)
            ids.append(outcome.order_id)
        return ids


class HoldRoundingTest(RestingBids):
    """The Sept 25 freeze: the book's own add-back of resting bids, not the venue's money."""

    def test_bids_that_come_and_go_leave_the_venue_reading_to_the_cent(self):
        self.rest("haghani-62", STAYED)
        # Before: this reading was -0.00236160 (the four bids' rounding), booked as dust.
        result = self.book.reconcile()
        self.assertEqual((result.ok, result.cash_diff, result.dust_booked), (True, D(0), D(0)), result.detail)
        cancelled = self.rest("haghani-63", CANCELLED)
        # Before: -0.01075037 more, a freeze (live, the bids came two at a time and each reading booked its part).
        result = self.book.reconcile()
        self.assertEqual((result.ok, result.cash_diff, result.dust_booked), (True, D(0), D(0)), result.detail)
        for order_id in cancelled:
            self.book.cancel("haghani-63", order_id)
        # Before: +0.01075037, "cash differs by 0.0108": live 465.627638403755211532 against 465.61688803, 02:49-04:11Z.
        result = self.book.reconcile()
        self.assertEqual((result.ok, result.cash_diff, result.dust_booked), (True, D(0), D(0)), result.detail)
        self.assertEqual(result.cash_venue, D("465.63") - D("16.002"))  # the account's cash with its holds, less the coins
        self.assertEqual(self.dust(), [])
        self.assertIsNone(self.book.frozen)


class TransitionTest(RestingBids):
    """The restart that ships H4: the last reading before it added the bids back unrounded and booked
    their sub-cent errors as dust (the book's cash then stood 0.01311197 from the venue's for 02:26-02:33Z
    Sept 25, eight bids resting). The first clean reading after it allows exactly that error, once."""

    def old_reading(self):
        """What the release before H4 wrote at its last clean reading: the eight bids' rounding booked
        as dust, and a `book.reconciled` row without `holds`."""
        error = sum((D(q) * D(p) - (D(q) * D(p)).quantize(D("0.01"), rounding=ROUND_HALF_UP) for _, q, p in STAYED + CANCELLED), D(0))
        self.assertEqual(error.quantize(D("0.00000001")), D("-0.01311197"))
        self.ledger.append("book.fill", {"book": "alpaca", "source": "dust", "instrument": None, "quantity": "0", "price": "0",
                                         "fee_usd": "0", "cash_delta": str(error.quantize(D("0.00000001"))), "position_delta": "0",
                                         "real_money": True}, agent=HOUSE)
        self.ledger.append("book.reconciled", {"book": "alpaca", "ok": True, "cash_venue": "465.616888026820363984",
                                               "cash_expected": "465.61688803", "cash_diff": "0.00000000", "position_diffs": {},
                                               "dust_booked": "0", "detail": "", "real_money": True})  # the live row of 02:32:04Z

    def test_the_first_clean_reading_after_the_restart_takes_the_old_readings_rounding_back(self):
        self.rest("haghani-62", STAYED)
        self.rest("haghani-63", CANCELLED)
        self.assertTrue(self.book.reconcile().ok)
        self.old_reading()
        self.book = self.new_book()  # the restart into H4
        result = self.book.reconcile()
        self.assertTrue(result.ok, result.detail)  # before the transition: "cash differs by 0.0131", and a rollback
        self.assertEqual(result.dust_booked, D("0.01311197"))
        self.assertEqual(sum((D(e.payload["cash_delta"]) for e in self.dust()), D(0)), D(0))  # the old dust, taken back
        self.broker.cash -= D("0.0131")  # and only once: the next reading has its cent a fill, no more
        self.assertFalse(self.book.reconcile().ok)

    def test_a_reading_at_the_cent_leaves_nothing_to_take_back(self):
        self.rest("haghani-62", STAYED)
        self.assertTrue(self.book.reconcile().ok)
        self.book = self.new_book()
        self.broker.cash += D("0.0131")
        self.assertFalse(self.book.reconcile().ok)


class RestartTest(RealAlpaca):
    """04:11:50Z Sept 25: a restart must not widen the tolerance to every fill the book ever had."""

    cash = "1000"

    def setUp(self):
        super().setUp()
        self.broker.set_quote(BTC, "80000", "80010")
        self.assertTrue(self.book.reconcile().ok)
        self.seat("a1", usd="400", position="400")

    def round_trips(self, n):
        for _ in range(n):
            self.assertEqual(self.book.submit([self.intent("a1", BTC, "buy", "0.0002")])[0].status, "filled")
            held = self.book.account("a1").holdings[BTC.key].quantity
            self.assertEqual(self.book.submit([self.intent("a1", BTC, "sell", str(held))])[0].status, "filled")

    def test_a_restart_does_not_book_what_no_fill_since_the_last_clean_reading_explains(self):
        self.round_trips(6)  # twelve venue fills, as on the real Alpaca book on Sept 25
        self.assertTrue(self.book.reconcile().ok)
        self.broker.cash += D("0.01075037")
        result = self.book.reconcile()
        self.assertFalse(result.ok)
        self.assertIn("cash differs by 0.0108", result.detail)
        self.book = self.new_book()  # the House restarts
        result = self.book.reconcile()
        # Before: ok, with 0.01075037 booked as dust (the fold had counted all twelve fills: $0.12).
        self.assertFalse(result.ok, "a restart un-froze the book")
        self.assertIn("cash differs by 0.0108", self.book.frozen)
        self.assertEqual([e for e in self.dust() if e.payload["cash_delta"] == "0.01075037"], [])

    def test_fills_since_the_last_clean_reading_still_count_after_a_restart(self):
        self.round_trips(2)
        self.assertTrue(self.book.reconcile().ok)
        self.round_trips(2)  # four fills the process never reconciled
        self.broker.cash -= D("0.035")  # four fills' rounding, allowed a cent each
        self.book = self.new_book()
        result = self.book.reconcile()
        self.assertTrue(result.ok, result.detail)
        self.assertEqual(result.dust_booked, D("-0.035"))


class RealOptionFeesTest(RealAlpaca):
    """The Sept 24 freeze: an option's fees on the real account, taken at the fill and listed later."""

    cash = "499.73"

    def setUp(self):
        super().setUp()
        self.clock.now = SEPT_24_OPTION_FILL
        self.broker.clock_iso = now_iso(self.clock)
        self.broker.fees = Fees("alpaca", option_clearing=True)  # the real account takes the OCC fee at the fill
        self.call = instrument_for("alpaca", {"occ": "AAL261002C00014000"})
        self.broker.set_quote(self.call, "0.18", "0.19")
        self.broker.set_quote(BTC, "80000", "80010")
        self.assertTrue(self.book.reconcile().ok)
        self.book.limits["krasker-14"] = Limits(D("100"), D("75"), asset_classes=("option", "crypto"))
        self.book.stake("krasker-14", "200")

    def buy(self, contracts="1", price="0.19", instrument=None):
        return self.book.submit([self.intent("krasker-14", instrument or self.call, "buy", contracts, order_type="limit",
                                             limit_price=price)])[0]

    def test_the_real_fill_pays_the_occ_fee_and_the_regulators_cents_are_dust_with_an_alert(self):
        self.assertEqual(self.buy().status, "filled")
        fill = [e.payload for e in self.ledger.iter(kinds="book.fill") if e.payload.get("source") == "venue"][-1]
        self.assertEqual((fill["fee_usd"], fill["cash_delta"]), ("0.03", "-19.03000000"))  # the OCC fee, at the fill
        self.assertEqual(self.book.account("krasker-14").cash, D("180.97"))
        self.broker.cash -= D("0.03")  # ORF and CAT, taken at the fill too (listed at 20:35Z and 00:31Z)
        result = self.book.reconcile()
        # Before: "cash differs by -0.0300" and a freeze, until a restart's fold booked it (18:45:22Z).
        self.assertTrue(result.ok, result.detail)
        self.assertIsNone(self.book.frozen)
        self.assertEqual(result.dust_booked, D("-0.03"))
        self.assertIn("regulatory fees", result.explained)
        dust = self.dust()
        self.assertEqual([(e.agent, e.payload["cash_delta"], e.payload["unlisted_fees_usd"]) for e in dust], [(HOUSE, "-0.03000000", "0.03000000")])
        self.assertIn("real book", dust[0].payload["detail"])
        self.assertIn("allocator.real_book_dust_usd", dust[0].payload["detail"])
        alerts = self.alerts()
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["level"], "error")
        self.assertTrue(alerts[0]["text"].startswith("alpaca: "), alerts[0]["text"])
        self.assertIn("-0.0300", alerts[0]["text"])
        self.assertIn("regulatory fees", alerts[0]["text"])
        self.assertIn("not a freeze", alerts[0]["text"])
        self.assertEqual(self.book.account("krasker-14").cash, D("180.97"))  # the House's cents, never the agent's record
        entry = self.buy("1", "0.16", instrument_for("alpaca", {"occ": "AAL261009C00015000"}))
        self.assertNotIn("frozen", entry.detail)
        # The next evening's listing moves no cash and books nothing: the OCC row was paid at the fill,
        # and with no shortfall the ORF row explains nothing.
        self.broker.fee_activities = lambda since=None: [
            {"id": "20260924::occ", "usd": D("0.03"), "date": "2026-09-24", "description": "OCC Clearing Fee"},
            {"id": "20260924::orf", "usd": D("0.03"), "date": "2026-09-24", "description": "ORF fee for proceed of 2 contracts"}]
        result = self.book.reconcile()
        self.assertTrue(result.ok, result.detail)
        self.assertEqual([e for e in self.ledger.iter(kinds="book.fill") if e.payload.get("source") == "venue-fee"], [])

    def test_the_dust_never_enters_an_agents_record_or_its_family(self):
        from league.families import TradeTape

        self.assertEqual(self.buy().status, "filled")
        self.broker.cash -= D("0.03")
        self.assertTrue(self.book.reconcile().ok)
        tape = TradeTape()
        tape.refresh(self.ledger)
        self.assertNotIn(HOUSE, tape.rows)
        self.assertEqual([row.payload.get("source") for row in tape.rows["krasker-14"] if row.kind == "book.fill"], ["venue"])
        account = self.book.account("krasker-14")
        self.assertEqual((account.cash, account.fees, account.realized), (D("180.97"), D("0.03"), D(0)))

    def test_cents_beside_a_position_difference_still_freeze(self):
        self.assertEqual(self.buy().status, "filled")
        self.broker.cash -= D("0.03")
        inst, held = self.broker.held[self.call.key]
        self.broker.held[self.call.key] = (inst, held + 1)  # a contract no fill explains
        result = self.book.reconcile()
        self.assertFalse(result.ok)
        self.assertIn("positions differ", result.detail)
        self.assertEqual((self.dust(), self.alerts()), ([], []))

    def test_cents_beside_an_order_in_doubt_still_freeze(self):
        self.assertEqual(self.buy().status, "filled")
        self.broker.lose_next_submit = True
        self.book.submit([self.intent("krasker-14", BTC, "buy", "0.0002")])
        self.broker.cash -= D("0.03")
        result = self.book.reconcile()
        self.assertFalse(result.ok)
        self.assertIn("outcome is unknown", result.detail)
        self.assertEqual(self.alerts(), [])

    def test_the_key_is_the_line_both_ways(self):
        """20 contracts leave room for $0.44 of the regulators' fees; a $0.30 shortfall is dust under a
        $0.50 key and a freeze under a $0.25 one."""
        cheap = instrument_for("alpaca", {"occ": "AAL261002C00020000"})
        self.broker.set_quote(cheap, "0.01", "0.02")
        self.assertEqual(self.buy("20", "0.02", cheap).status, "filled")
        self.broker.cash -= D("0.30")
        with patch.dict(CONSTITUTION["allocator"], {"real_book_dust_usd": "0.25"}):
            result = self.book.reconcile()
            self.assertFalse(result.ok)
            self.assertIn("cash differs by -0.3000", self.book.frozen)
        result = self.book.reconcile()  # the constitution's own $0.50
        self.assertTrue(result.ok, result.detail)
        self.assertEqual(result.dust_booked, D("-0.30"))

    def test_more_than_the_fees_can_be_freezes_under_the_key(self):
        self.assertEqual(self.buy().status, "filled")  # room for $0.06 on one contract
        self.broker.cash -= D("0.08")
        result = self.book.reconcile()
        self.assertFalse(result.ok)
        self.assertEqual(self.alerts(), [])

    def test_no_option_or_stock_fill_no_explanation(self):
        """Cents after crypto fills only (whose fees the book models at the fill) are not explained."""
        self.assertEqual(self.book.submit([self.intent("krasker-14", BTC, "buy", "0.0002")])[0].status, "filled")
        self.assertTrue(self.book.reconcile().ok)
        self.broker.cash -= D("0.03")
        self.assertFalse(self.book.reconcile().ok)
        self.assertEqual(self.dust(), [])

    def test_the_room_is_spent_once_and_a_restart_remembers_it(self):
        self.assertEqual(self.buy().status, "filled")  # $0.06 of room
        self.broker.cash -= D("0.03")
        self.assertTrue(self.book.reconcile().ok)
        self.broker.cash -= D("0.025")
        self.book = self.new_book()
        self.assertTrue(self.book.reconcile().ok)  # $0.025 of the $0.03 left
        self.broker.cash -= D("0.02")
        self.book = self.new_book()
        result = self.book.reconcile()
        self.assertFalse(result.ok)  # $0.005 left
        self.assertIn("cash differs by -0.0200", result.detail)

    def test_a_key_out_of_its_bounds_allows_nothing(self):
        """Absent or out of bounds, the key allows nothing: a real book freezes as it did before."""
        self.assertEqual(self.buy().status, "filled")
        self.broker.cash -= D("0.03")
        with patch.dict(CONSTITUTION["allocator"], {"real_book_dust_usd": "2.00"}):
            result = self.book.reconcile()
        self.assertFalse(result.ok)
        self.assertEqual((self.dust(), self.alerts()), ([], []))

    def test_the_room_lapses(self):
        self.assertEqual(self.buy().status, "filled")
        self.assertTrue(self.book.reconcile().ok)
        self.clock.advance(UNLISTED_FEE_HOURS * 3600 + 60)
        self.broker.cash -= D("0.03")
        self.assertFalse(self.book.reconcile().ok)


class KeyTest(unittest.TestCase):
    def test_the_constitution_sets_fifty_cents_inside_its_bounds(self):
        self.assertEqual(CONSTITUTION["allocator"]["real_book_dust_usd"], "0.50")
        self.assertEqual(REAL_BOOK_DUST_BOUNDS, (D("0.25"), D("1.00")))
        self.assertEqual(real_book_dust_usd(), D("0.50"))

    def test_a_key_outside_its_bounds_or_unreadable_is_no_key(self):
        for value, expected in (("0.25", D("0.25")), ("1.00", D("1.00")), (0.5, D("0.5")), ("0.24", None), ("1.01", None),
                                ("5", None), ("-0.5", None), ("half", None), (True, None)):
            with self.subTest(value=value), patch.dict(CONSTITUTION["allocator"], {"real_book_dust_usd": value}):
                self.assertEqual(real_book_dust_usd(), expected)
        kept = {k: v for k, v in CONSTITUTION["allocator"].items() if k != "real_book_dust_usd"}
        with patch.dict(CONSTITUTION["allocator"], kept, clear=True):
            self.assertIsNone(real_book_dust_usd())


class InTheHouse(unittest.TestCase):
    def test_every_alpaca_book_pays_the_occ_fee_at_the_fill(self):
        import tempfile
        from pathlib import Path

        from league.house import House, Settings
        from league.tests.fakes import Clock
        from league.tests.test_house import FakeAlpacaData
        from league.tests.test_ladder import InProcessSandbox

        with tempfile.TemporaryDirectory() as root:
            house = House(Path(root) / "house", brokers={"alpaca-paper": FakeBroker("alpaca-paper"), "alpaca": FakeBroker("alpaca", cash="500")},
                          sandbox=InProcessSandbox(), alpaca_data=FakeAlpacaData(), clock=Clock(),
                          settings=Settings(mark_every_seconds=0, research=False, real_money=True))
            try:
                self.assertTrue(house.books["alpaca"].real_money)
                self.assertEqual({name: book.fees.option_clearing for name, book in house.books.items()}, {"alpaca-paper": True, "alpaca": True})
            finally:
                house.close(wait=None)


if __name__ == "__main__":
    unittest.main()
