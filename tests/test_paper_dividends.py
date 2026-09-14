"""Cash-dividend rights, atomic valuation and source evidence; offline fixtures only."""
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest

from portfolio_runtime import PortfolioLedger, UniverseSnapshot, DailyBar
from portfolio_runtime.market import session_for_day, CALENDAR_SOURCE, parse_chart
from portfolio_runtime.outcomes import OutcomeJournal
from test_paper_ledger import quote, fixture_universe, CREATED, DECIDED, FILL, session
from test_runtime_market import FixtureMarket, fixture, epoch, raw

EX = '2026-09-15T13:30:00Z'
CLOSE = '2026-09-15T20:00:00Z'
CAPTURE = '2026-09-15T20:01:00Z'
SOURCE = 'https://example.com/sourced-cash-dividend'


def dividend(**changes):
    return dict(symbol='AAPL', effective_at=EX, amount='1', reference_close='100',
                source=SOURCE, source_sha256='d'*64, captured_at=CAPTURE) | changes


def tuesday_fixture(*, amount=1, price=99):
    value = fixture(closed=True, close=100)
    row = value['chart']['result'][0]
    row['timestamp'].append(epoch(EX))
    row['meta']['regularMarketTime'] = epoch(CLOSE)
    for key, values in row['indicators']['quote'][0].items():
        values.append(1000000 if key == 'volume' else price)
    row['events'] = {'dividends': {str(epoch(EX)): {'date': epoch(EX), 'amount': amount}}}
    return value


class DividendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.ledger = PortfolioLedger(self.root/'paper.sqlite', created_at=CREATED)
        self.ledger.register_universe(fixture_universe())
        self.ledger.propose('first', decided_at=DECIDED, targets={'AAPL':'0.1'},
                            universe_id='membership-20260913', evidence_refs=['dated-source'])
        self.ledger.fill_pending('first', quotes=[quote()], now=FILL, market_session=session())

    def tearDown(self):
        self.ledger.close()
        self.temp.cleanup()

    def mark(self, *, at=CAPTURE, price='99', observations=None, mark_id=None):
        return self.ledger.mark([quote(price=price, at=at)], observed_at=at,
                               dividends=observations if observations is not None else [dividend(captured_at=at)],
                               mark_id=mark_id)

    def assert_consistent(self, state):
        total = Decimal(state['cash']) + Decimal(state['dividend_receivable'])
        total += sum(Decimal(h['market_value']) for h in state['holdings'])
        self.assertEqual(total, Decimal(state['equity']))
        self.assertEqual(state['equity'], state['history'][-1]['equity'])

    def test_ex_date_receivable_offsets_price_drop_without_cash_or_deposit(self):
        state = self.mark()
        self.assertEqual(state['cash'], '90000')
        self.assertEqual(state['dividend_receivable'], '100')
        self.assertEqual(state['equity'], '100000')
        self.assertEqual(state['net_deposits'], '0')
        self.assertEqual(state['performance']['time_weighted_return_pct'], '0')
        self.assertEqual(state['performance']['investment_pnl'], '0')
        self.assert_consistent(state)
        event = self.ledger.events()[-1]
        self.assertEqual(event['kind'], 'mark')
        self.assertEqual(event['payload']['dividends'][0]['shares'], '100')
        self.assertEqual(event['payload']['nav']['equity'], '100000')

    def test_same_mark_replay_restart_and_later_marks_do_not_duplicate_entitlement(self):
        first = self.mark(mark_id='dividend-close')
        count = len(self.ledger.events())
        self.assertEqual(self.mark(mark_id='dividend-close'), first)
        self.assertEqual(len(self.ledger.events()), count)
        self.ledger.close()
        self.ledger = PortfolioLedger(self.root/'paper.sqlite')
        self.assertEqual(self.ledger.public_state(), first)
        state = self.mark(at='2026-09-16T20:01:00Z')
        self.assertEqual(state['dividend_receivable'], '100')
        self.assertEqual(sum(len(e['payload'].get('dividends', [])) for e in self.ledger.events()), 1)

    def test_transaction_failure_after_entitlement_leaves_no_receivable_or_nav(self):
        before, events = self.ledger.public_state(), self.ledger.events()
        original = self.ledger._append
        def fail(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError('simulated interruption after append')
        self.ledger._append = fail
        with self.assertRaisesRegex(RuntimeError, 'interruption'):
            self.mark()
        self.ledger._append = original
        self.assertEqual(self.ledger.public_state(), before)
        self.assertEqual(self.ledger.events(), events)
        self.assert_consistent(self.mark())

    def test_ex_date_purchase_has_no_entitlement_and_sale_after_preserves_rights(self):
        # Existing Monday lot is sold at Tuesday's ex-date opening, before any
        # closing mark. The receivable is committed alongside the sale.
        self.ledger.propose('sell', decided_at='2026-09-14T20:02:00Z', targets={},
                            universe_id='membership-20260913', evidence_refs=['dated-source'])
        at = '2026-09-15T13:31:00Z'
        result = self.ledger.fill_pending('sell', quotes=[quote(price='99', at=at)], now=at,
            market_session=session_for_day('2026-09-15'), dividends=[dividend(captured_at=at)])
        state = self.ledger.public_state()
        self.assertEqual(state['cash'], '99900')
        self.assertEqual(state['dividend_receivable'], '100')
        self.assertEqual(state['holdings'], [])
        self.assert_consistent(state)
        # Reacquisition later on the ex-date cannot enlarge that entitlement.
        self.ledger.propose('buy-back', decided_at='2026-09-15T13:32:00Z', targets={'AAPL':'0.1'},
                            universe_id='membership-20260913', evidence_refs=['dated-source'])
        at = '2026-09-15T13:33:00Z'
        self.ledger.fill_pending('buy-back', quotes=[quote(price='99', at=at)], now=at,
            market_session=session_for_day('2026-09-15'), dividends=[dividend(captured_at=at)])
        self.assertEqual(self.mark()['dividend_receivable'], '100')
        # A dividend on the same opening as the first purchase gives no rights.
        other = dividend(effective_at='2026-09-14T13:30:00Z', amount='0.5')
        self.assertEqual(self.mark(at='2026-09-16T20:01:00Z', observations=[other])['dividend_receivable'], '100')
        self.assertEqual(self.ledger.events()[-1]['payload']['dividends'][0]['shares'], '0')

    def test_missed_marks_use_historical_lots_not_current_shares(self):
        self.ledger.propose('reduce', decided_at='2026-09-15T13:32:00Z', targets={'AAPL':'0.05'},
                            universe_id='membership-20260913', evidence_refs=['dated-source'])
        at = '2026-09-15T13:33:00Z'
        self.ledger.fill_pending('reduce', quotes=[quote(price='99', at=at)], now=at,
                                market_session=session_for_day('2026-09-15'))
        self.assertLess(Decimal(self.ledger.public_state()['holdings'][0]['quantity']), Decimal(100))
        state = self.mark(at='2026-09-17T20:01:00Z')
        self.assertEqual(state['dividend_receivable'], '100')
        self.assert_consistent(state)

    def test_only_sourced_payable_date_moves_receivable_to_cash_and_return_is_neutral(self):
        before = self.mark()
        payment = dict(payable_at='2026-09-17T00:00:00Z', source=SOURCE,
                       source_sha256='b'*64, captured_at=CAPTURE)
        state = self.mark(at='2026-09-16T20:01:00Z', observations=[dividend(payment=payment)])
        self.assertEqual(state['cash'], before['cash'])
        paid = self.mark(at='2026-09-17T20:01:00Z', observations=[dividend(payment=payment)])
        self.assertEqual(paid['cash'], '90100')
        self.assertEqual(paid['dividend_receivable'], '0')
        self.assertEqual(paid['equity'], before['equity'])
        self.assertEqual(paid['performance']['time_weighted_return_pct'], '0')
        self.assertEqual(paid['net_deposits'], '0')
        self.assert_consistent(paid)
        self.assertEqual(self.mark(at='2026-09-18T20:01:00Z', observations=[dividend(payment=payment)])['cash'], '90100')

    def test_changed_amount_ambiguous_date_large_distribution_bad_payment_fail_atomically(self):
        self.mark()
        before = self.ledger.public_state()
        invalid = [dividend(amount='2'), dividend(effective_at='2026-09-15T14:00:00Z'),
                   dividend(amount='25'), dividend(source_sha256='x'*64),
                   dividend(payment={'payable_at':'2026-09-15T00:00:00Z', 'source':SOURCE,
                                     'source_sha256':'b'*64, 'captured_at':CAPTURE}),
                   dividend(payment={'payable_at':'2026-09-16T00:00:00Z'})]
        for observation in invalid:
            with self.subTest(observation=observation):
                with self.assertRaises(ValueError):
                    self.mark(at='2026-09-16T20:01:00Z', observations=[observation])
                self.assertEqual(self.ledger.public_state(), before)

    def test_market_adapter_accrues_and_outcome_feedback_uses_atomic_marked_equity(self):
        market = FixtureMarket(self.root/'market', now=CAPTURE, fixtures={'AAPL':tuesday_fixture()})
        state = market.mark_close(self.ledger)['portfolio']
        self.assertEqual(state['dividend_receivable'], '100')
        self.assertEqual(state['equity'], '100000')
        self.assertEqual(state['as_of'], CLOSE)
        journal = OutcomeJournal(self.root/'outcomes.sqlite')
        self.assertEqual(journal.observe(self.ledger, observed_at=CAPTURE)['receipts_added'], 1)
        outcome = journal.context(cutoff=CAPTURE)[0]
        self.assertEqual(Decimal(outcome['portfolio_return_pct']), Decimal(0))
        self.assertEqual(journal.context(cutoff='2026-09-15T19:00:00Z'), [])
        self.assert_consistent(state)

    def test_market_large_distribution_still_suspends(self):
        market = FixtureMarket(self.root/'market', now=CAPTURE, fixtures={'AAPL':tuesday_fixture(amount=25, price=75)})
        with self.assertRaisesRegex(ValueError, 'corporate action'):
            market.mark_close(self.ledger)
        self.assertEqual(self.ledger.public_state()['status'], 'suspended')
        self.assertEqual(self.ledger.public_state()['dividend_receivable'], '0')

    def test_late_report_after_full_sale_is_discovered_for_cash_only_account(self):
        self.ledger.propose('sold', decided_at='2026-09-15T13:32:00Z', targets={},
                            universe_id='membership-20260913', evidence_refs=['dated-source'])
        at = '2026-09-15T13:33:00Z'
        # The provider had not yet reported the ex-date event at sale time.
        self.ledger.fill_pending('sold', quotes=[quote(price='99', at=at)], now=at,
                                market_session=session_for_day('2026-09-15'))
        self.assertEqual(self.ledger.public_state()['holdings'], [])
        market = FixtureMarket(self.root/'market', now=CAPTURE, fixtures={'AAPL':tuesday_fixture()})
        state = market.mark_close(self.ledger)['portfolio']
        self.assertEqual(market.calls, ['AAPL'])
        self.assertEqual(state['cash'], '99900')
        self.assertEqual(state['dividend_receivable'], '100')
        self.assertEqual(state['equity'], '100000')
        self.assert_consistent(state)

    def test_fill_replay_rejects_changed_or_removed_dividend_evidence(self):
        self.ledger.propose('sale-retry', decided_at='2026-09-14T20:02:00Z', targets={},
                            universe_id='membership-20260913', evidence_refs=['dated-source'])
        at = '2026-09-15T13:31:00Z'
        kwargs = dict(quotes=[quote(price='99', at=at)], now=at,
                      market_session=session_for_day('2026-09-15'), dividends=[dividend(captured_at=at)])
        first = self.ledger.fill_pending('sale-retry', **kwargs)
        self.assertEqual(self.ledger.fill_pending('sale-retry', **kwargs), first)
        before = self.ledger.public_state()
        for changed in ([], [dividend(captured_at=at, amount='2')]):
            with self.assertRaisesRegex(ValueError, 'different dividend evidence'):
                self.ledger.fill_pending('sale-retry', **(kwargs | {'dividends':changed}))
            self.assertEqual(self.ledger.public_state(), before)

    def test_unpaid_rights_are_never_spendable_during_full_allocation(self):
        self.mark()
        symbols = ('AAPL','MSFT','NVDA','AMZN','GOOGL','META')
        self.ledger.register_universe(fixture_universe(snapshot_id='new-membership', symbols=symbols,
                                                      captured_at='2026-09-16T12:00:00Z'))
        self.ledger.propose('invest', decided_at='2026-09-16T12:30:00Z', targets={s:'0.16666666' for s in symbols},
                            universe_id='new-membership', evidence_refs=['dated-source'])
        at = '2026-09-16T13:31:00Z'
        self.ledger.fill_pending('invest', quotes=[quote(s, price='1', at=at) for s in symbols],
            now=at, market_session=session_for_day('2026-09-16'))
        state = self.ledger.public_state()
        self.assertEqual(state['dividend_receivable'], '100')
        self.assertGreaterEqual(Decimal(state['cash']), 0)
        self.assert_consistent(state)
        self.assertEqual(sum(Decimal(h['market_value']) for h in state['holdings']), Decimal('90100')-Decimal(state['cash']))


if __name__ == '__main__':
    unittest.main()
