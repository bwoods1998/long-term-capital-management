"""The real first-fill defect reproduced with sanitized receipts and no network calls."""
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import Mock, patch

from league.accounting import repair_legacy_kalshi_fills
from league.book import Book
from league.episodes import completed
from league.evaluator import Evaluator
from league.fees import Fees
from league.ledger import Ledger
from league.tests.fakes import Clock, FakeBroker
from ltcm.broker import Instrument, Order, VenueUnavailable


class ReceiptAccountingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clock = Clock()
        self.ledger = Ledger(Path(self.tmp.name) / 'ledger.sqlite', clock=self.clock)
        self.addCleanup(self.ledger.close)
        self.inst = Instrument('event', 'KXDOGE15M-26SEP211215-15', 'kalshi',
                               market_id='KXDOGE15M-26SEP211215-15', right='yes')
        self.broker = FakeBroker('kalshi', cash='494.3267', family='kalshi')
        self.broker.held[self.inst.key] = (self.inst, D(10))
        self.broker.set_quote(self.inst, '.54', '.56')
        self.ledger.append('book.baseline', {'book': 'kalshi', 'cash': '500', 'positions': {}})
        self.ledger.append('book.stake', {'book': 'kalshi', 'usd': '25'}, agent='a')
        self.base = {'book': 'kalshi', 'order_id': 'ord-one', 'broker_order_id': 'venue-one',
                     'instrument': self.inst.to_dict(), 'side': 'buy', 'quantity': '10', 'order_type': 'market',
                     'status': 'filled', 'shares': [{'agent': 'a', 'intent_id': 'in-one', 'quantity': '10'}]}
        self.ledger.append('book.order', self.base)
        self.old = self.ledger.append('book.fill', {'book': 'kalshi', 'source': 'venue', 'order_id': 'ord-one',
            'intent_id': 'in-one', 'instrument': self.inst.to_dict(), 'side': 'buy', 'quantity': '10',
            'price': '.0055', 'cash_delta': '-.055', 'position_delta': '10', 'fee_usd': '0',
            'fee_quantity': '0', 'venue_fee': '0'}, agent='a')
        self.receipt = Order(id='ord-one', intent_id='oi-one', desk_id='', instrument=self.inst, side='buy',
                             quantity=D(10), order_type='limit', limit_price=D('.67'), time_in_force='gtc',
                             status='filled', venue='kalshi', broker_order_id='venue-one',
                             filled_quantity=D(10), average_price=D('.55'), fees=D('.1733'))
        self.receipt._raw = {'receipt_accounting': True}
        self.broker.get_order = Mock(return_value=self.receipt)
        self.book = self.rebuild()

    def rebuild(self):
        return Book('kalshi', self.broker, self.ledger, fees=Fees('kalshi'), real_money=True, clock=self.clock)

    def test_receipt_repairs_cash_fee_cost_and_reconciles_without_any_trade(self):
        before_head = self.ledger.head()
        self.assertEqual(self.book.account('a').cash, D('24.945'))
        self.assertTrue(self.book.reconcile().ok)
        account = self.book.account('a')
        self.assertEqual(account.cash, D('19.3267'))
        self.assertEqual(account.fees, D('.1733'))
        self.assertEqual(account.holdings[self.inst.key].cost, D('5.6733'))
        self.assertEqual(account.holdings[self.inst.key].quantity, D(10))
        self.assertEqual(account.staked, D(25))
        self.assertEqual(self.book.baseline_cash, D(500))
        self.assertEqual(self.book.orders['ord-one'].notional, D('5.5'))
        self.assertEqual(self.book.orders['ord-one'].fees_seen, D('.1733'))
        correction = self.ledger.last('book.fill_correction', agent='a')
        self.assertEqual(correction.payload['original_fill_id'], self.old.id)
        self.assertEqual(D(correction.payload['cash_delta']), D('-5.6183'))
        self.assertEqual(self.ledger.last('book.fill', agent='a').payload, self.old.payload)
        self.assertEqual(self.broker.submitted, [])
        self.assertEqual(self.broker.cancelled, [])
        self.assertGreater(self.ledger.head()[0], before_head[0])
        self.ledger.verify()
        self.book = self.rebuild()
        self.assertTrue(self.book.reconcile().ok)
        self.assertEqual(self.book.account('a').cash, D('19.3267'))
        self.assertEqual(self.ledger.count(kinds='book.fill_correction'), 1)
        self.broker.get_order.assert_called_once_with('venue-one')

    def test_settlement_before_repair_corrects_realized_loss_and_not_quantity(self):
        self.book.settle(self.inst.market_id, 'no')
        self.broker.held.clear()
        self.assertEqual(self.book.account('a').realized, D('-.055'))
        self.assertTrue(self.book.reconcile().ok)
        self.assertEqual(self.book.account('a').realized, D('-5.6733'))
        self.assertEqual(self.book.account('a').holdings, {})
        self.assertEqual(self.rebuild().account('a').realized, D('-5.6733'))
        self.assertEqual(completed(self.ledger, 'a', 'kalshi'), [])
        self.assertEqual(Evaluator(self.ledger).trade_returns('a', 'kalshi'), ([], 1.0))

    def test_partial_sale_before_repair_splits_cost_between_open_and_realized(self):
        p = {'book': 'kalshi', 'source': 'cross', 'instrument': self.inst.to_dict(), 'side': 'sell',
             'quantity': '4', 'price': '.5', 'cash_delta': '2', 'position_delta': '-4', 'fee_usd': '0'}
        e = self.ledger.append('book.fill', p, agent='a'); self.book._apply(e.kind, e.agent, e.payload, e.at)
        self.assertEqual(repair_legacy_kalshi_fills(self.book), 1)
        account = self.book.account('a')
        self.assertEqual(account.cash, D('21.3267'))
        self.assertEqual(account.realized, D('2') - D('5.6733') * D('.4'))
        self.assertEqual(account.holdings[self.inst.key].cost, D('5.6733') * D('.6'))
        self.assertEqual(account.holdings[self.inst.key].quantity, D(6))
        self.assertEqual(self.rebuild().account('a').realized, account.realized)

    def test_unavailable_or_unproven_receipt_keeps_the_cash_mismatch(self):
        self.broker.get_order.side_effect = VenueUnavailable('offline')
        self.assertFalse(self.book.reconcile().ok)
        self.assertEqual(self.ledger.count(kinds='book.fill_correction'), 0)
        self.broker.get_order.side_effect = None
        self.receipt._raw = {}
        self.assertFalse(self.book.reconcile().ok)
        self.assertEqual(self.ledger.count(kinds='book.fill_correction'), 0)

    def test_wrong_identity_quantity_or_not_the_known_unit_error_is_never_repaired(self):
        for field, wrong in [('broker_order_id', 'other'), ('filled_quantity', D(9)), ('average_price', D('.56'))]:
            with self.subTest(field=field):
                old = getattr(self.receipt, field)
                setattr(self.receipt, field, wrong)
                self.book._receipt_checked.clear()
                self.assertEqual(repair_legacy_kalshi_fills(self.book), 0)
                setattr(self.receipt, field, old)
        self.assertEqual(self.book.account('a').cash, D('24.945'))

    def test_multiple_partial_allocations_cannot_be_reconstructed_from_an_average(self):
        row = {**self.old.payload, 'quantity': '1', 'position_delta': '1', 'cash_delta': '-.0055'}
        self.ledger.append('book.fill', row, agent='a')
        self.book = self.rebuild()
        self.assertEqual(repair_legacy_kalshi_fills(self.book), 0)
        self.broker.get_order.assert_not_called()

    def test_committed_correction_survives_a_crash_before_in_memory_application(self):
        with patch.object(self.book, '_apply', side_effect=RuntimeError('process stopped')):
            with self.assertRaises(RuntimeError):
                repair_legacy_kalshi_fills(self.book)
        rebuilt = self.rebuild()
        self.assertTrue(rebuilt.reconcile().ok)
        self.assertEqual(rebuilt.account('a').cash, D('19.3267'))
        self.assertEqual(self.ledger.count(kinds='book.fill_correction'), 1)

    def test_dirty_marks_are_excluded_and_new_blocks_start_from_corrected_equity(self):
        ev = Evaluator(self.ledger)
        dirty = self.ledger.append('book.mark', {'book': 'kalshi', 'equity': '30', 'cash': '24.945'}, agent='a')
        self.ledger.append('eval.block', {'book': 'kalshi', 'key': 'old', 'first_mark_seq': dirty.seq,
            'last_mark_seq': dirty.seq, 'end_equity': 30, 'log_growth': .2, 'active': True}, agent='a')
        self.assertTrue(self.book.reconcile().ok)
        self.assertEqual(ev.blocks('a', book='kalshi'), [])
        for stamp in ('2026-09-21T16:30:00Z', '2026-09-21T17:01:00Z'):
            self.ledger.append('book.mark', {'book': 'kalshi', 'equity': '19.3267', 'cash': '19.3267',
                'staked': '25', 'holdings': 0}, agent='a', at=stamp)
        self.assertEqual(ev.observe('a', 'kalshi', 'hour'), 1)
        row = ev.blocks('a', book='kalshi')[0]
        self.assertEqual(row['start_equity'], 19.3267)
        self.assertEqual(row['log_growth'], 0)

    def test_fresh_exposures_use_corrected_cash_and_the_dirty_cycle_stays_excluded(self):
        self.assertTrue(self.book.reconcile().ok)
        self.clock.advance(60)
        self.book.settle(self.inst.market_id, 'no')
        self.assertEqual(completed(self.ledger, 'a', 'kalshi'), [])
        for side, cash, qty in [('buy', '-5', '10'), ('sell', '6', '-10')]:
            self.clock.advance(60)
            self.ledger.append('book.fill', {'book': 'kalshi', 'source': 'venue', 'instrument': self.inst.to_dict(),
                'side': side, 'quantity': '10', 'cash_delta': cash, 'position_delta': qty,
                'flat': side == 'sell'}, agent='a')
        rows = completed(self.ledger, 'a', 'kalshi')
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]['return'], 1 / 19.3267)

    def test_old_block_look_does_not_force_new_evidence_to_catch_up_to_dirty_counts(self):
        ev = Evaluator(self.ledger)
        ev.seat('a', 2, 'test live')
        self.ledger.append('eval.verdict', {'decision': 'look', 'rung': 2, 'active_blocks': 100,
            'tested_death': True, 'tested_promotion': True}, agent='a')
        self.assertTrue(self.book.reconcile().ok)
        correction = self.ledger.last('book.fill_correction', agent='a')
        for i in range(35):
            mark = self.ledger.append('book.mark', {'book': 'kalshi', 'equity': '25'}, agent='a')
            self.ledger.append('eval.block', {'book': 'kalshi', 'key': str(i), 'first_mark_seq': mark.seq,
                'last_mark_seq': mark.seq, 'active': True, 'exposure': .3, 'log_growth': 0.0001}, agent='a')
        ev.judge('a', 'kalshi')
        looks = [e for e in self.ledger.iter(kinds='eval.verdict', agent='a') if e.payload.get('decision') == 'look']
        self.assertEqual(len(looks), 2)
        self.assertGreater(looks[-1].seq, correction.seq)


class FreshAttributionTests(unittest.TestCase):
    def test_polled_sell_receipts_use_the_agents_leg_not_the_opposite_directional_cost(self):
        from ltcm.tests.test_adapters_kalshi import make, intent, TICKER, YES, NO
        for instrument, outcome, book_side, receipt_cost, expected in (
                (YES, 'no', 'ask', '7.5', '2.5'), (NO, 'yes', 'bid', '2.5', '7.5')):
            with self.subTest(leg=instrument.right), tempfile.TemporaryDirectory() as directory:
                ledger = Ledger(Path(directory) / 'ledger.sqlite'); self.addCleanup(ledger.close)
                broker = FakeBroker('kalshi', cash='500', family='kalshi')
                book = Book('kalshi', broker, ledger, fees=Fees('kalshi'), real_money=True)
                book.venue_cash = D(500); book.stake('a', '25')
                buy = {'book': 'kalshi', 'instrument': instrument.to_dict(), 'source': 'cross',
                       'side': 'buy', 'quantity': '10', 'price': '.4', 'cash_delta': '-4',
                       'position_delta': '10', 'fee_usd': '0'}
                e = ledger.append('book.fill', buy, agent='a'); book._apply(e.kind, e.agent, e.payload, e.at)
                request = intent(instrument=instrument, side='sell', quantity='10')
                adapter, _, _ = make(order_api='v2')
                receipt = adapter.parse_order({'order_id': 's1', 'client_order_id': request.id,
                    'ticker': TICKER, 'outcome_side': outcome, 'book_side': book_side, 'status': 'executed',
                    'initial_count_fp': '10.00', 'fill_count_fp': '10.00', 'remaining_count_fp': '0.00',
                    'taker_fill_cost_dollars': receipt_cost, 'maker_fill_cost_dollars': '0',
                    'taker_fees_dollars': '.13', 'maker_fees_dollars': '0'})
                base = {'book': 'kalshi', 'order_id': receipt.id, 'broker_order_id': 's1',
                        'instrument': instrument.to_dict(), 'side': 'sell', 'quantity': '10',
                        'order_type': 'market', 'status': 'accepted',
                        'shares': [{'agent': 'a', 'intent_id': request.id, 'quantity': '10'}]}
                e = ledger.append('book.order', base); book._apply(e.kind, e.agent, e.payload, e.at)
                book._attribute(book.orders[receipt.id], receipt, '2026-09-21T16:06:50Z')
                self.assertEqual(book.account('a').cash, D(21) + D(expected) - D('.13'))
                self.assertEqual(book.account('a').realized, D(expected) - D('.13') - D(4))
                self.assertEqual(book.account('a').holdings, {})
                self.assertEqual(broker.submitted, [])

    def test_complete_and_incomplete_acknowledgements_converge_to_one_exact_receipt(self):
        from ltcm.tests.test_adapters_kalshi import make, intent, TICKER
        for missing in (None, 'average_fill_price', 'average_fee_paid'):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as directory:
                ledger = Ledger(Path(directory) / 'ledger.sqlite')
                self.addCleanup(ledger.close)
                broker = FakeBroker('kalshi', cash='500', family='kalshi')
                book = Book('kalshi', broker, ledger, fees=Fees('kalshi'), real_money=True)
                book.venue_cash = D(500)
                book.stake('a', '25')
                adapter, _, _ = make(order_api='v2')
                request = intent(quantity='10')
                ack = {'order_id': 'k1', 'fill_count': '10.00', 'remaining_count': '0.00',
                       'average_fill_price': '.5500', 'average_fee_paid': '.017330'}
                if missing:
                    del ack[missing]
                parsed = adapter.parse_order(ack, intent=request, v2_create=True)
                base = {'book': 'kalshi', 'order_id': parsed.id, 'broker_order_id': 'k1',
                        'instrument': request.instrument.to_dict(), 'side': 'buy', 'quantity': '10',
                        'order_type': 'market', 'status': 'accepted',
                        'shares': [{'agent': 'a', 'intent_id': request.id, 'quantity': '10'}]}
                e = ledger.append('book.order', base); book._apply(e.kind, e.agent, e.payload, e.at)
                working = book.orders[parsed.id]
                book._attribute(working, parsed, '2026-09-21T16:06:49Z')
                if missing:
                    self.assertTrue(working.open)
                    self.assertEqual(ledger.count(kinds='book.fill'), 0)
                receipt = adapter.parse_order({'order_id': 'k1', 'client_order_id': request.id,
                    'ticker': TICKER, 'outcome_side': 'yes', 'book_side': 'bid', 'status': 'executed',
                    'initial_count_fp': '10.00', 'fill_count_fp': '10.00', 'remaining_count_fp': '0.00',
                    'yes_price_dollars': '.67', 'taker_fill_cost_dollars': '5.5', 'maker_fill_cost_dollars': '0',
                    'taker_fees_dollars': '.1733', 'maker_fees_dollars': '0'})
                book._attribute(working, receipt, '2026-09-21T16:06:50Z')
                book._attribute(working, receipt, '2026-09-21T16:06:51Z')
                self.assertFalse(working.open)
                self.assertEqual(ledger.count(kinds='book.fill'), 1)
                self.assertEqual(book.account('a').cash, D('19.3267'))
                self.assertEqual(book.account('a').fees, D('.1733'))
                self.assertEqual(book.account('a').holdings[request.instrument.key].quantity, D(10))
                self.assertEqual(ledger.last('book.fill', agent='a').payload['venue_accounting_version'], 2)
                self.assertEqual(broker.submitted, [])


if __name__ == '__main__':
    unittest.main()
