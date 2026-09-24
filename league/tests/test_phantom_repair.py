"""The Sept 20, 2026 phantom holding, reproduced with a fake venue: an agent's sale filled while its
record was lost, and a hand adoption wrote the sold units as a negative baseline."""
import dataclasses
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import Mock

from league.accounting import evidence_cutoffs, repair_paper_phantoms
from league.book import Book, position_key
from league.fees import Fees
from league.ledger import Ledger
from league.tests.fakes import Clock, FakeBroker
from ltcm.broker import Instrument, Order

REPAIR = {'book': 'alpaca-paper', 'agent': 'a', 'broker_order_id': 'venue-sell', 'why': 'test'}


class PhantomRepair(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clock = Clock()
        self.ledger = Ledger(Path(self.tmp.name) / 'ledger.sqlite', clock=self.clock)
        self.addCleanup(self.ledger.close)
        self.inst = Instrument('crypto', 'AVAX-USD', 'alpaca-paper', market_id='AVAX/USD')
        self.key = position_key(self.inst)
        self.ledger.append('book.baseline', {'book': 'alpaca-paper', 'cash': '1000', 'positions': {}})
        self.ledger.append('book.stake', {'book': 'alpaca-paper', 'usd': '200'}, agent='a')
        self.ledger.append('book.fill', {'book': 'alpaca-paper', 'source': 'venue', 'order_id': 'ord-buy', 'intent_id': 'in-buy',
                                         'instrument': self.inst.to_dict(), 'side': 'buy', 'quantity': '4', 'price': '10',
                                         'cash_delta': '-40', 'position_delta': '4', 'fee_usd': '0', 'fee_quantity': '0',
                                         'venue_fee': '0'}, agent='a')
        # The venue sold the 4 at 10.50 and kept its own fee; the ledger never heard.
        self.venue_cash = D('960') + D('42') - D('0.063')
        self.ledger.append('book.baseline', {'book': 'alpaca-paper', 'cash': str(self.venue_cash + 40),
                                             'positions': {self.key: '-4'}, 'note': 'adopted the venue by hand'})
        self.broker = FakeBroker('alpaca-paper', cash=str(self.venue_cash))
        self.broker.set_quote(self.inst, '10.4', '10.6')
        self.receipt = Order(id='x', intent_id='oi-lost', desk_id='', instrument=self.inst, side='sell', quantity=D(4),
                             order_type='limit', limit_price=D('10.5'), time_in_force='gtc', status='filled',
                             venue='alpaca-paper', broker_order_id='venue-sell', filled_quantity=D(4),
                             average_price=D('10.5'), fees=D('0.063'))
        self.broker.get_order = Mock(return_value=self.receipt)

    def book(self, **kw):
        return Book('alpaca-paper', self.broker, self.ledger, fees=Fees('alpaca'), real_money=kw.get('real_money', False), clock=self.clock)

    def test_the_phantom_sale_is_booked_from_the_receipt_and_the_book_still_reconciles(self):
        book = self.book()
        self.assertFalse(book.evidence_integrity('a')['ok'])
        self.assertTrue(book.reconcile().ok)  # the aggregate always reconciled: that was the trap
        self.assertEqual(repair_paper_phantoms(book, [REPAIR]), 1)
        account = book.account('a')
        self.assertEqual(account.holdings, {})
        fee = Fees('alpaca').charge(self.inst, 'sell', D(4), D('10.5')).usd
        self.assertEqual(account.cash, D(200) - 40 + 42 - fee)
        self.assertEqual(account.realized, 2 - fee)
        self.assertTrue(book.evidence_integrity('a')['ok'])
        self.assertNotIn(self.key, book.baseline_positions)
        self.assertTrue(book.reconcile().ok)
        self.assertEqual(repair_paper_phantoms(book, [REPAIR]), 0)  # once
        cutoff = evidence_cutoffs(self.ledger, 'a')['alpaca-paper']
        self.assertEqual(cutoff, self.ledger.last('book.baseline').seq)
        rebuilt = self.book()  # a restart folds to the same state
        self.assertTrue(rebuilt.evidence_integrity('a')['ok'])
        self.assertEqual(rebuilt.account('a').cash, account.cash)
        self.assertTrue(rebuilt.reconcile().ok)

    def test_the_reconciliation_runs_the_named_repair(self):
        from unittest.mock import patch
        book = self.book()
        with patch('league.accounting._repairs', return_value=[REPAIR]):
            self.assertTrue(book.reconcile().ok)
        self.assertTrue(book.evidence_integrity('a')['ok'])

    def test_anything_but_an_exact_filled_sale_is_refused(self):
        for change in ({'filled_quantity': D('3.9')}, {'side': 'buy'}, {'status': 'cancelled'}):
            receipt = dataclasses.replace(self.receipt, **change)
            self.broker.get_order = Mock(return_value=receipt)
            book = self.book()
            self.assertEqual(repair_paper_phantoms(book, [REPAIR]), 0, change)
            self.assertFalse(book.evidence_integrity('a')['ok'], change)

    def test_never_on_a_real_money_book(self):
        book = self.book(real_money=True)
        self.assertEqual(repair_paper_phantoms(book, [REPAIR]), 0)


if __name__ == '__main__':
    unittest.main()


class CutoffsFoldedOnce(unittest.TestCase):
    """Sept 24, 2026 (R6-perf): `evidence_cutoffs` read every `book.baseline` row on every call (3,194 calls in
    six ticks of a full league on a copy of the 17:27Z snapshot). The repairs are folded once a ledger, then from
    the new baseline rows only, and the cutoffs are the full read's."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.ledger = Ledger(Path(self.dir.name) / "ledger.sqlite")
        self.addCleanup(self.ledger.close)

    def as_read_before(self, agent):
        result = {}
        for entry in self.ledger.iter(kinds='book.fill_correction', agent=agent):
            result[entry.payload['book']] = entry.seq
        for entry in self.ledger.iter(kinds='book.baseline'):
            if any(r.get('agent') == agent for r in entry.payload.get('repairs') or []):
                result[entry.payload['book']] = max(result.get(entry.payload['book'], 0), entry.seq)
        return result

    def baseline(self, book, *agents):
        self.ledger.append("book.baseline", {"book": book, "cash": "0", "positions": {}, "note": "test",
                                             "repairs": [{"agent": a, "order": "o"} for a in agents]})

    def test_the_cutoffs_are_the_full_read_s_and_only_new_rows_are_read(self):
        from unittest.mock import patch

        agents = ("a", "b", "c")
        self.baseline("alpaca-paper")
        self.baseline("alpaca-paper", "a")
        self.ledger.append("book.fill_correction", {"book": "kalshi-shadow"}, agent="b")
        self.baseline("kalshi-shadow", "a", "b")
        self.assertEqual({a: evidence_cutoffs(self.ledger, a) for a in agents}, {a: self.as_read_before(a) for a in agents})
        self.ledger.append("book.fill_correction", {"book": "alpaca-paper"}, agent="a")  # after its repair: the later wins
        self.baseline("alpaca-paper", "c")
        self.ledger.append("book.fill_correction", {"book": "kalshi-shadow"}, agent="b")  # after its repair on that book
        with patch.object(self.ledger, "read", wraps=self.ledger.read) as read:
            got = {a: evidence_cutoffs(self.ledger, a) for a in agents}
        self.assertEqual(got, {a: self.as_read_before(a) for a in agents})
        baseline_reads = [c.kwargs for c in read.call_args_list if c.kwargs.get("kinds") == "book.baseline"]
        self.assertTrue(baseline_reads and all(k["after"] > 0 for k in baseline_reads), "only the baseline rows after the fold's")
