"""Sept 21, 2026 22:00:43: a 15-minute contract settled at the venue five seconds before the House
recorded it; the real book froze for one reading and the watchdog rolled back a release."""
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path

from league.book import SETTLEMENT_GRACE_SECONDS, Book
from league.fees import Fees
from league.ledger import Ledger
from league.tests.fakes import Clock, FakeBroker
from ltcm.broker import Instrument


class SettlementGrace(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clock = Clock()
        self.ledger = Ledger(Path(self.tmp.name) / 'ledger.sqlite', clock=self.clock)
        self.addCleanup(self.ledger.close)
        self.inst = Instrument('event', 'KXDOGE15M-26SEP211800-00', 'kalshi', market_id='KXDOGE15M-26SEP211800-00', right='yes')
        self.ledger.append('book.baseline', {'book': 'kalshi', 'cash': '500', 'positions': {}})
        self.ledger.append('book.stake', {'book': 'kalshi', 'usd': '25'}, agent='a')
        self.ledger.append('book.fill', {'book': 'kalshi', 'source': 'venue', 'order_id': 'o', 'intent_id': 'i',
                                         'instrument': self.inst.to_dict(), 'side': 'buy', 'quantity': '4', 'price': '.69',
                                         'cash_delta': '-2.76', 'position_delta': '4', 'fee_usd': '0', 'fee_quantity': '0',
                                         'venue_fee': '0'}, agent='a')

    def book(self, cash):
        broker = FakeBroker('kalshi', cash=cash, family='kalshi')  # the venue: position gone, settled
        broker.set_quote(self.inst, '.01', '.02')
        return Book('kalshi', broker, self.ledger, fees=Fees('kalshi'), real_money=True, clock=self.clock)

    def test_a_lost_contract_waits_for_its_settlement_row_then_freezes(self):
        book = self.book('497.24')
        result = book.reconcile()
        self.assertTrue(result.ok, result.detail)
        self.assertIn('awaiting settlement', result.detail)
        self.assertIsNone(book.frozen)
        self.clock.advance(SETTLEMENT_GRACE_SECONDS + 1)
        self.assertFalse(book.reconcile().ok)  # no settlement ever came: that is a real difference

    def test_a_won_contract_may_have_paid_before_its_row_and_is_not_booked_as_dust(self):
        book = self.book('501.24')
        result = book.reconcile()
        self.assertTrue(result.ok, result.detail)
        self.assertEqual(book.account('house').cash if 'house' in book.accounts else D(0), D(0))
        dust = [e for e in self.ledger.iter(kinds='book.fill') if e.payload.get('source') == 'dust']
        self.assertEqual(dust, [])

    def test_more_cash_than_the_contracts_could_pay_still_freezes(self):
        self.assertFalse(self.book('510').reconcile().ok)


if __name__ == '__main__':
    unittest.main()
