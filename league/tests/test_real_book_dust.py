"""H4 of the forward-first run (Sept 25, 2026): a real book never freezes on cents it can explain,
and never un-freezes on cents it cannot.

The evidence, read on the House box and the real Alpaca account (GET only):

- 02:38:59Z-04:03:42Z Sept 25: the real Alpaca book read "cash differs by 0.0149", "0.0168" and
  then "0.0108" (cash_venue 465.627638403755211532 against 465.61688803) every five minutes, frozen,
  with no fill and no fee in those hours. The book adds back the cash behind each resting crypto bid
  at `remaining x limit` to eighteen places; Alpaca holds each at that notional rounded half-up to
  the cent. Every reading booked the sum of those sub-cent errors as dust, and when four of the eight
  bids resting at 02:26Z were cancelled or replaced over the next passes, the error booked on them
  (-0.01075037) was left standing. With the holds rounded as the venue rounds them, the account's
  cash is unchanged across all 339 pairs of consecutive readings between Sept 24 00:00Z and 04:26Z
  Sept 25 with no fill between them (465.63 since 18:52Z Sept 24).
- 04:11:50Z Sept 25, 1.2 s after the House restarted: the same +0.0108 was booked as dust and the
  book reconciled. `_fold` had counted every venue fill the book ever had (12) as "since the last
  reconciliation", so the first reading of the new process allowed $0.12 (and $0.12 of limit-fill
  fee slack). The same thing un-froze the Sept 24 option freeze (-0.0324) at 18:45:22Z, 1.0 s after a
  restart. On the real Kalshi book (139 fills) the first reading after a restart allowed $1.39.
- 18:19:57Z Sept 24: a one-contract AAL call buy on the real account. Its OCC clearing fee ($0.03,
  listed 11 s later) and $0.03 of ORF and CAT fees (listed at 20:35Z and 00:31Z) left the cash at the
  fill; the book froze on -0.0308, then -0.0324, until the restart above.
"""

import json
import unittest
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from unittest.mock import patch

from ltcm.broker import Instrument

from league.book import REAL_BOOK_DUST_BOUNDS, UNLISTED_FEE_HOURS, Book, Limits, real_book_dust_usd
from league.constitution import CONSTITUTION
from league.fees import Fees
from league.ledger import HOUSE, now_iso
from league.tests.fakes import FakeBroker
from league.tests.fakes import OpenGrant
from league.tests.test_book import BookCase
from league.venues import instrument_for
from league.watchdog import HouseHealth

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

    def test_the_transition_allows_its_own_sign_only(self):
        """The ledger stands 0.0131 BELOW the venue after the old reading. Before, the transition was
        allowed either way: a real 3.5-cent shortfall nothing explains read -0.0219 against a tolerance
        of 0.0231 and was booked as plain dust, with no alert."""
        self.rest("haghani-62", STAYED)
        self.rest("haghani-63", CANCELLED)
        self.assertTrue(self.book.reconcile().ok)
        self.old_reading()
        self.book = self.new_book()
        self.broker.cash -= D("0.035")
        result = self.book.reconcile()
        self.assertFalse(result.ok, f"booked {result.dust_booked} as dust")
        self.assertIn("cash differs by -0.0219", result.detail)

    def test_no_listing_is_booked_against_the_transition(self):
        """Bids whose old rounding left the ledger 0.0134 ABOVE the venue: the first H4 reading reads
        -0.0134, which is that rounding, not a fee. Before, the stale CAT $0.01 was booked against it (as
        live at 02:20:33Z Sept 25 against -0.0147) and only the rest taken back as dust."""
        bids = [(SOL, "0.1", "116.0449"), (SOL, "0.1", "116.0448"), (SOL, "0.1", "116.0447")]
        self.rest("haghani-62", bids)
        self.assertTrue(self.book.reconcile().ok)
        error = sum((D(q) * D(p) - (D(q) * D(p)).quantize(D("0.01"), rounding=ROUND_HALF_UP) for _, q, p in bids), D(0))
        self.assertEqual(error, D("0.01344"))
        self.ledger.append("book.fill", {"book": "alpaca", "source": "dust", "instrument": None, "quantity": "0", "price": "0",
                                         "fee_usd": "0", "cash_delta": str(error), "position_delta": "0", "real_money": True}, agent=HOUSE)
        self.ledger.append("book.reconciled", {"book": "alpaca", "ok": True, "cash_diff": "0.00000000", "position_diffs": {},
                                               "dust_booked": "0", "detail": "", "real_money": True})
        self.book = self.new_book()
        self.broker.fee_activities = lambda since=None: [
            {"id": "20260924::cat", "usd": D("0.01"), "date": "2026-09-24", "description": "CAT fee for proceed of 2 trades"}]
        result = self.book.reconcile()
        self.assertEqual((result.ok, result.dust_booked), (True, -error), result.detail)
        self.assertEqual([e for e in self.ledger.iter(kinds="book.fill") if e.payload.get("source") == "venue-fee"], [])

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


class RealOptions(RealAlpaca):
    """The real Alpaca account of 18:19:57Z Sept 24, 2026, before its first option buy."""

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


class RealOptionFeesTest(RealOptions):
    """The Sept 24 freeze: an option's fees on the real account, taken at the fill and listed later."""

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


class ReviewedTest(RealOptions):
    """What the adversarial review of H4 found (Sept 25, 2026), each case failing on the builder's head
    2c9114d: a fee listing already paid as real dust that later explains an unrelated shortfall, an old
    fill's dust that outlives its room, and the dust alert of a fill before a promotion that rolled the
    release back."""

    def twenty(self, occ="AAL261002C00020000"):
        """A 20-contract option buy: room for $0.44 of the regulators' fees."""
        option = instrument_for("alpaca", {"occ": occ})
        self.broker.clock_iso = now_iso(self.clock)
        self.broker.set_quote(option, "0.02", "0.02")  # marked at the price paid: no daily loss to refuse the next
        outcome = self.buy("20", "0.02", option)
        self.assertEqual(outcome.status, "filled", outcome.detail)

    def list_fees(self, *rows):
        self.broker.fee_activities = lambda since=None: [dict(row) for row in rows]

    def venue_fees(self):
        return [e.payload for e in self.ledger.iter(kinds="book.fill") if e.payload.get("source") == "venue-fee"]

    def test_a_listing_paid_as_dust_at_the_fill_explains_no_later_shortfall(self):
        """The ORF cents leave the cash at the fill and are booked as dust; their listing that evening
        moves no cash. Before: 6 h later that listing, never booked by id, took an unexplained $0.31
        real shortfall to zero -- ok, no alert, no freeze."""
        self.twenty()
        self.broker.cash -= D("0.31")  # ORF on 20 contracts, taken at the fill
        result = self.book.reconcile()
        self.assertEqual((result.ok, result.dust_booked), (True, D("-0.31")), result.detail)
        self.list_fees({"id": "20260924::orf", "usd": D("0.31"), "date": "2026-09-24", "description": "ORF fee for proceed of 20 contracts"})
        self.assertTrue(self.book.reconcile().ok)
        self.book = self.new_book()  # a restart remembers what the dust paid
        self.clock.advance(UNLISTED_FEE_HOURS * 3600 + 60)
        self.broker.cash -= D("0.31")  # a real loss nothing explains, every position agreeing
        result = self.book.reconcile()
        self.assertFalse(result.ok, "an unexplained real shortfall was booked as a fee already paid as dust")
        self.assertIn("cash differs by -0.3100", result.detail)
        # The listing is marked paid, at no cash: it can explain nothing again.
        self.assertEqual([(p["cash_delta"], p["fee_usd"], p["covered_usd"]) for p in self.venue_fees()], [("0", "0", "0.31")])
        self.assertIn("real-book dust", self.venue_fees()[0]["detail"])

    def test_a_days_listing_over_the_key_hides_nothing(self):
        """Three fills' ORF dusted at each fill, listed as one $0.92 activity: a later $0.92 shortfall
        (over the $0.50 key) booked silently as that listing before."""
        for occ in ("AAL261002C00020000", "AAL261002C00021000", "AAL261002C00022000"):
            self.twenty(occ)
            self.broker.cash -= D("0.31")
            self.assertTrue(self.book.reconcile().ok)
        self.list_fees({"id": "20260924::orf", "usd": D("0.92"), "date": "2026-09-24", "description": "ORF fee for proceed of 60 contracts"})
        self.assertTrue(self.book.reconcile().ok)
        self.clock.advance(UNLISTED_FEE_HOURS * 3600 + 60)
        self.broker.cash -= D("0.92")
        result = self.book.reconcile()
        self.assertFalse(result.ok)
        self.assertIn("cash differs by -0.9200", result.detail)

    def test_the_next_fills_cents_are_its_own_dust_not_yesterdays_listing(self):
        """Sept 24's ORF $0.03 was paid at the fill; the next option buy's own cents are dust on its own
        room, with its alert, and not labelled as that listing (which left this fill's room unspent)."""
        self.assertEqual(self.buy().status, "filled")
        self.broker.cash -= D("0.03")
        self.assertTrue(self.book.reconcile().ok)
        self.list_fees({"id": "20260924::orf", "usd": D("0.03"), "date": "2026-09-24", "description": "ORF fee for proceed of 2 contracts"})
        self.assertTrue(self.book.reconcile().ok)
        self.clock.advance(20 * 3600)
        self.broker.clock_iso = now_iso(self.clock)
        later = instrument_for("alpaca", {"occ": "AAL261009C00015000"})
        self.broker.set_quote(later, "0.16", "0.16")
        self.assertEqual(self.buy("1", "0.16", later).status, "filled")
        self.broker.cash -= D("0.03")
        result = self.book.reconcile()
        self.assertEqual((result.ok, result.dust_booked), (True, D("-0.03")), result.detail)
        self.assertEqual([(p["cash_delta"], p["covered_usd"]) for p in self.venue_fees()], [("0", "0.03")])
        self.assertEqual(len(self.alerts()), 2)

    def test_a_stale_listing_that_takes_a_fills_cents_pays_that_fills_listing(self):
        """The live ledger's Sept 24 ORF $0.03: its cash left at the 18:19Z fill and was absorbed before
        H4, so the listing stands unbooked. At the next option fill it takes $0.03 of that fill's cents
        (the rest is dust): the fill's own listings are then paid by both. Before, the dust alone paid
        $0.29 of the day's $0.31 ORF listing, which stood unpaid and later took an unexplained $0.31
        real shortfall to zero: the pool of stale listings grew from $0.03 to a day's fees."""
        self.list_fees({"id": "20260924::orf", "usd": D("0.03"), "date": "2026-09-24", "description": "ORF fee for proceed of 2 contracts"})
        self.twenty()
        self.broker.cash -= D("0.32")  # ORF $0.31 and CAT $0.01 on 20 contracts, taken at the fill
        result = self.book.reconcile()
        self.assertEqual((result.ok, result.dust_booked), (True, D("-0.29")), result.detail)
        self.assertEqual([(p["cash_delta"], p["unlisted_fees_usd"]) for p in self.venue_fees()], [("-0.03", "0.03")])
        self.list_fees({"id": "20260924::orf", "usd": D("0.03"), "date": "2026-09-24", "description": "ORF fee for proceed of 2 contracts"},
                       {"id": "20260925::orf", "usd": D("0.31"), "date": "2026-09-25", "description": "ORF fee for proceed of 20 contracts"},
                       {"id": "20260925::cat", "usd": D("0.01"), "date": "2026-09-25", "description": "CAT fee for proceed of 1 trades"})
        self.clock.advance(UNLISTED_FEE_HOURS * 3600 + 60)
        self.broker.cash -= D("0.31")
        result = self.book.reconcile()
        self.assertFalse(result.ok, "the day's ORF listing, paid at the fill, took an unexplained shortfall")
        self.assertEqual([(p["cash_delta"], p.get("covered_usd")) for p in self.venue_fees()], [("-0.03", None), ("0", "0.31"), ("0", "0.01")])

    def test_a_listing_whose_cash_leaves_when_it_is_listed_is_still_booked(self):
        """A fee the dust never paid (the paper account's overnight TAF, say) books against its own
        shortfall as before, dust or no dust earlier: only what the dust paid is marked."""
        self.assertEqual(self.buy().status, "filled")
        self.broker.cash -= D("0.03")
        self.assertTrue(self.book.reconcile().ok)  # $0.03 paid as dust
        self.clock.advance(UNLISTED_FEE_HOURS * 3600 + 60)
        self.list_fees({"id": "20260924::taf", "usd": D("0.05"), "date": "2026-09-24", "description": "OPT TAF fee for proceed of 11 contracts"})
        self.broker.cash -= D("0.05")  # taken when listed
        result = self.book.reconcile()
        self.assertTrue(result.ok, result.detail)
        self.assertEqual([(p["cash_delta"], p["fee_usd"], p.get("covered_usd")) for p in self.venue_fees()], [("-0.05", "0.05", None)])

    def test_an_old_fills_dust_ages_out_with_that_fills_room(self):
        """Fill A's room lapsed 6 h after it while the dust booked on it did not, and ate fill B's room:
        B's own $0.16 froze the book (10 contracts each, 6 h apart)."""
        a = instrument_for("alpaca", {"occ": "AAL261002C00020000"})
        self.broker.set_quote(a, "0.02", "0.02")
        self.assertEqual(self.buy("10", "0.02", a).status, "filled")  # A: room $0.24
        self.clock.advance(300)
        self.broker.cash -= D("0.17")
        self.assertTrue(self.book.reconcile().ok)
        self.clock.advance(UNLISTED_FEE_HOURS * 3600 - 400)
        self.broker.clock_iso = now_iso(self.clock)
        b = instrument_for("alpaca", {"occ": "AAL261002C00021000"})
        self.broker.set_quote(b, "0.02", "0.02")
        self.assertEqual(self.buy("10", "0.02", b).status, "filled")  # B: room $0.24 of its own
        self.clock.advance(130)  # A has lapsed
        self.broker.cash -= D("0.16")
        result = self.book.reconcile()
        self.assertTrue(result.ok, result.detail)  # before: "cash differs by -0.1600" and a freeze
        self.assertEqual(result.dust_booked, D("-0.16"))
        self.book = self.new_book()  # and a restart folds the same room
        self.assertEqual(self.book._unlisted_room()[0], D("0.08"))

    def write_health(self):
        root = Path(self.dir.name)
        (root / "health.json").write_text(json.dumps({"at": now_iso(self.clock), "living": 10, "ledger_seq": self.ledger.head()[0],
                                                      "books": {"alpaca": {"frozen": self.book.frozen}}}))
        return root

    def watch_readings(self, watch):
        readings = []
        for _ in range(4):
            self.clock.advance(30)
            self.write_health()
            readings.append(watch())
        return readings

    def test_the_dust_of_a_fill_before_the_promotion_is_inherited_by_the_watch(self):
        """A real option fill in the minutes between the old House's last reading and the promotion:
        the new House books its cents as dust with an error alert, and the watch rolled the release
        back on it ("1 error alert(s) since seq N ... alpaca: -0.0300 of cash booked as dust"). The
        venue took the fee at the fill, before the promotion: the alert's `began_at` says so."""
        self.assertTrue(self.book.reconcile().ok)  # the old House's last clean reading
        self.assertEqual(self.buy().status, "filled")  # a fill it never read
        fill_at = [e.at for e in self.ledger.iter(kinds="book.fill") if e.payload.get("source") == "venue"][-1]
        self.broker.cash -= D("0.03")
        self.clock.advance(60)
        watch = HouseHealth(self.write_health(), clock=self.clock, restart_within=None)
        self.assertTrue(watch().ok)  # the reading just before the promotion
        self.ledger.append("ops.started", {"release": "h4"})
        self.clock.advance(31)
        self.book = self.new_book()  # the new House
        result = self.book.reconcile()
        self.assertEqual((result.ok, result.dust_booked), (True, D("-0.03")), result.detail)
        self.assertEqual(self.alerts()[-1]["began_at"], fill_at)
        readings = self.watch_readings(watch)
        self.assertEqual([r.reasons for r in readings if not r.ok], [])
        self.assertEqual((readings[-1].detail["error_alerts"], readings[-1].detail.get("inherited_alerts")), (0, 1))

    def test_cents_after_a_clean_reading_still_count_in_the_watch(self):
        """A shortfall that appears after the fill was read clean is not the fill's cents taken at the
        fill: its alert carries no `began_at`, and the watch still counts it."""
        self.assertEqual(self.buy().status, "filled")
        self.clock.advance(60)
        self.assertTrue(self.book.reconcile().ok)  # the old House read the fill clean
        self.clock.advance(60)
        watch = HouseHealth(self.write_health(), clock=self.clock, restart_within=None)
        self.assertTrue(watch().ok)
        self.ledger.append("ops.started", {"release": "h4"})
        self.clock.advance(31)
        self.book = self.new_book()
        self.broker.cash -= D("0.03")
        self.assertTrue(self.book.reconcile().ok)  # still dust on the fill's room, with its alert
        self.assertNotIn("began_at", self.alerts()[-1])
        readings = self.watch_readings(watch)
        self.assertTrue(any("error alert" in reason for r in readings for reason in r.reasons), [r.reasons for r in readings])


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
                          grant=OpenGrant(), settings=Settings(mark_every_seconds=0, research=False, real_money=True))
            try:
                self.assertTrue(house.books["alpaca"].real_money)
                self.assertEqual({name: book.fees.option_clearing for name, book in house.books.items()}, {"alpaca-paper": True, "alpaca": True})
            finally:
                house.close(wait=None)


if __name__ == "__main__":
    unittest.main()
