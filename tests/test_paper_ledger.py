"""Deterministic accounting and market-boundary tests; all prices are test fixtures."""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal, localcontext
from fractions import Fraction
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from portfolio_runtime import BenchmarkPoint, DailyBar, Mandate, MarketSession, PortfolioLedger, Quote, UniverseSnapshot


CREATED = '2026-09-13T14:00:00Z'  # Sunday: opening cash is not a Friday fill.
DECIDED = '2026-09-13T15:00:00Z'
OPEN = '2026-09-14T13:30:00Z'
FILL = '2026-09-14T13:31:00Z'
LATER = '2026-09-14T13:32:00Z'
SOURCE = 'https://example.com/verified-test-fixture'
INDEX_SOURCE = 'https://www.spglobal.com/spdji/en/indices/equity/sp-500/'


def fixture_universe(**kwargs):
    return UniverseSnapshot(**({'snapshot_id': 'membership-20260913', 'effective_at': '2026-09-11T00:00:00Z',
                                'captured_at': CREATED, 'expires_at': '2026-09-20T00:00:00Z',
                                'symbols': ('AAPL', 'MSFT', 'NVDA'), 'source': SOURCE} | kwargs))


def quote(ticker='AAPL', price='100', *, at=FILL, bid=None, ask=None, **kwargs):
    return Quote(symbol=ticker, bid=bid or price, ask=ask or price, last=price, as_of=at,
                 source=SOURCE, corporate_actions_checked_through=at, **kwargs)


def session():
    return MarketSession(opens_at=OPEN, closes_at='2026-09-14T20:00:00Z', source=SOURCE)


class PaperLedgerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / 'paper.sqlite'
        self.ledger = PortfolioLedger(self.path, created_at=CREATED)
        self.ledger.register_universe(fixture_universe())

    def tearDown(self):
        self.ledger.close()
        self.directory.cleanup()

    def propose(self, targets=None, *, decision_id='decision-1', decided_at=DECIDED, **kwargs):
        return self.ledger.propose(decision_id, decided_at=decided_at,
                                   targets=targets if targets is not None else {'AAPL': '0.10'},
                                   universe_id='membership-20260913', evidence_refs=['filing-sha256:123'], **kwargs)

    def fill(self, quotes=None, **kwargs):
        return self.ledger.fill_pending('decision-1', quotes=quotes if quotes is not None else [quote()],
                                        now=FILL, market_session=session(), **kwargs)

    def test_initial_cash_has_no_fabricated_prices_or_performance(self):
        state = self.ledger.public_state()
        self.assertEqual(state['mode'], 'paper')
        self.assertEqual(state['cash'], '100000')
        self.assertEqual(state['equity'], '100000')
        self.assertEqual(state['status'], 'cash')
        self.assertEqual(state['history'], [])
        self.assertIsNone(state['performance']['time_weighted_return_pct'])
        self.assertEqual(state['performance']['benchmark']['status'], 'unavailable')

    def test_sunday_intent_cannot_execute_at_friday_close_or_on_sunday(self):
        self.propose()
        friday = MarketSession(opens_at='2026-09-11T13:30:00Z', closes_at='2026-09-11T20:00:00Z', source=SOURCE)
        with self.assertRaisesRegex(ValueError, 'closed'):
            self.ledger.fill_pending('decision-1', quotes=[quote(at='2026-09-11T19:59:00Z')],
                                     now=DECIDED, market_session=friday)
        with self.assertRaises(ValueError):
            MarketSession(opens_at='2026-09-13T13:30:00Z', closes_at='2026-09-13T20:00:00Z', source=SOURCE)
        self.assertEqual(self.ledger.public_state()['status'], 'pending')
        self.assertEqual(self.ledger.public_state()['cash'], '100000')
        self.assertFalse(any(event['kind'] == 'rebalance' for event in self.ledger.events()))

    def test_fill_uses_future_observed_ask_and_fee_and_conserves_cash(self):
        self.propose()
        result = self.fill([quote(price='100', bid='99.90', ask='100.10')], fee_per_order='1.25')
        fill = result['fills'][0]
        self.assertEqual(fill['quantity'], '99')
        self.assertEqual(fill['price'], '100.1')
        self.assertEqual(fill['fee'], '1.25')
        state = self.ledger.public_state()
        self.assertEqual(state['cash'], '90088.85')
        self.assertEqual(state['equity'], '99988.85')
        self.assertEqual(state['performance']['investment_pnl'], '-11.15')
        self.assertEqual(state['trading_fees'], '1.25')
        self.assertEqual(state['performance']['time_weighted_return_pct'], '-0.01115')
        self.assertEqual(Decimal(state['cash']) + Decimal(state['holdings'][0]['market_value']), Decimal(state['equity']))

    def test_exact_fill_retry_and_process_restart_do_not_duplicate_orders(self):
        self.propose()
        first = self.fill()
        self.assertEqual(first, self.fill())
        before = self.ledger.public_state()
        self.ledger.close()
        self.ledger = PortfolioLedger(self.path)
        self.assertEqual(self.ledger.public_state(), before)
        self.assertEqual(self.fill(), first)
        self.assertEqual(len([event for event in self.ledger.events() if event['kind'] == 'rebalance']), 1)
        self.assertEqual(len({item['order_id'] for item in first['fills']}), len(first['fills']))

    def test_same_decision_id_cannot_change_allocation_evidence_or_time(self):
        result = self.propose()
        self.assertEqual(result, self.propose())
        for changes in ({'targets': {'AAPL': '0.11'}}, {'evidence_refs': ['different']}, {'decided_at': FILL}):
            values = {'decided_at': DECIDED, 'targets': {'AAPL': '0.10'}, 'universe_id': 'membership-20260913',
                      'evidence_refs': ['filing-sha256:123']} | changes
            with self.assertRaises(ValueError):
                self.ledger.propose('decision-1', **values)

    def test_unknown_constituent_short_leverage_and_concentration_rejected(self):
        for targets in ({'GME': '0.1'}, {'AAPL': '-0.1'}, {'AAPL': '0.21'}, {'AAPL': 0.1}):
            with self.assertRaises(ValueError):
                self.propose(targets)
        with PortfolioLedger(Path(self.directory.name) / 'wide.sqlite', Mandate(max_position_weight='1'),
                             created_at=CREATED) as ledger:
            ledger.register_universe(fixture_universe())
            with self.assertRaisesRegex(ValueError, 'leverage'):
                ledger.propose('leverage', decided_at=DECIDED, targets={'AAPL': '0.6', 'MSFT': '0.6'},
                               universe_id='membership-20260913', evidence_refs=['evidence'])

    def test_future_membership_and_expired_snapshot_cannot_justify_decision(self):
        future = fixture_universe(snapshot_id='future', effective_at='2026-09-15T00:00:00Z',
                                  captured_at='2026-09-14T00:00:00Z', symbols=('GME',))
        self.ledger.register_universe(future)
        with self.assertRaises(ValueError):
            self.ledger.propose('future-decision', decided_at=DECIDED, targets={'GME': '0.1'},
                               universe_id='future', evidence_refs=['evidence'])
        with self.assertRaisesRegex(ValueError, 'membership'):
            self.propose(decided_at='2026-09-21T15:00:00Z')

    def test_newer_membership_is_required_and_changed_membership_rechecked_at_fill(self):
        self.propose()
        update = fixture_universe(snapshot_id='new-membership', effective_at='2026-09-14T00:00:00Z',
                                 captured_at='2026-09-13T16:00:00Z', symbols=('MSFT', 'NVDA'))
        self.ledger.register_universe(update)
        with self.assertRaisesRegex(ValueError, 'left the S&P'):
            self.fill()
        self.assertEqual(self.ledger.public_state()['status'], 'pending')
        with self.assertRaisesRegex(ValueError, 'latest effective'):
            self.propose({'MSFT': '0.1'}, decision_id='decision-2', decided_at=FILL, supersedes='decision-1')

    def test_quote_must_follow_decision_and_be_nonfuture_nonstale_regular(self):
        self.propose(decided_at='2026-09-14T13:30:59Z')
        for bad in (quote(at='2026-09-14T13:30:59Z'), quote(at='2026-09-14T13:31:01Z'),
                    quote(at='2026-09-14T13:28:59Z'), quote(session='closed')):
            with self.assertRaises(ValueError):
                self.fill([bad])
        self.assertEqual(self.ledger.public_state()['cash'], '100000')
        self.fill()

    def test_fill_requires_complete_synchronized_nonduplicate_quotes(self):
        self.propose({'AAPL': '0.1', 'MSFT': '0.1'})
        for quotes in ([quote()], [quote(), quote()], [quote(), quote('MSFT', at='2026-09-14T13:30:50Z')],
                       [quote(), quote('MSFT'), quote('NVDA')]):
            with self.assertRaises(ValueError):
                self.fill(quotes)
        self.fill([quote(), quote('MSFT', at='2026-09-14T13:30:56Z')])

    def test_mark_requires_every_holding_and_never_carries_stale_prices(self):
        self.propose({'AAPL': '0.1', 'MSFT': '0.1'})
        self.fill([quote(), quote('MSFT')])
        before = self.ledger.public_state()
        with self.assertRaises(ValueError):
            self.ledger.mark([quote(at=LATER)], observed_at=LATER)
        with self.assertRaises(ValueError):
            self.ledger.mark([quote(), quote('MSFT')], observed_at='2026-09-14T13:35:00Z')
        self.assertEqual(self.ledger.public_state(), before)

    def test_marks_measure_actual_price_changes_and_no_benchmark_is_invented(self):
        self.propose()
        self.fill()
        state = self.ledger.mark([quote(price='110', at=LATER)], observed_at=LATER)
        self.assertEqual(state['equity'], '101000')
        self.assertEqual(state['performance']['time_weighted_return_pct'], '1')
        self.assertEqual(state['performance']['investment_pnl'], '1000')
        self.assertEqual(len(state['history']), 2)
        self.assertEqual(state['performance']['benchmark']['status'], 'unavailable')
        self.assertTrue(all(point['benchmark_return_pct'] is None for point in state['history']))

    def test_funding_changes_equity_but_not_return(self):
        self.propose()
        self.fill()
        result = self.ledger.deposit('10000', external_id='funding-1', at=LATER, quotes=[quote(at=LATER)])
        self.assertEqual(result['cash'], '100000')
        self.assertEqual(result['equity'], '110000')
        self.assertEqual(result['net_deposits'], '10000')
        self.assertEqual(result['performance']['time_weighted_return_pct'], '0')
        self.assertEqual(result['performance']['investment_pnl'], '0')
        self.assertEqual(self.ledger.deposit('10000', external_id='funding-1', at=LATER), result)
        with self.assertRaises(ValueError):
            self.ledger.deposit('20000', external_id='funding-1', at=LATER)

    def test_deposit_with_holdings_requires_exact_boundary_quotes(self):
        self.propose()
        self.fill()
        for quotes in ([], [quote()]):
            with self.assertRaises(ValueError):
                self.ledger.deposit('10000', external_id='funding', at=LATER, quotes=quotes)
        self.assertEqual(self.ledger.public_state()['net_deposits'], '0')

    def test_time_weighted_growth_is_chained_without_deposit_pollution(self):
        self.propose()
        self.fill()
        self.ledger.deposit('10000', external_id='funding', at=LATER, quotes=[quote(price='110', at=LATER)])
        state = self.ledger.mark([quote(price='121', at='2026-09-14T13:33:00Z')], observed_at='2026-09-14T13:33:00Z')
        expected = (Fraction(101000, 100000) * Fraction(112100, 111000) - 1) * 100
        self.assertAlmostEqual(float(state['performance']['time_weighted_return_pct']), float(expected), places=11)
        self.assertEqual(state['performance']['investment_pnl'], '2100')

    def test_deposit_before_first_mark_preserves_unstarted_record(self):
        state = self.ledger.deposit('10', external_id='prelaunch', at=DECIDED)
        self.assertEqual(state['equity'], '100010')
        self.assertEqual(state['history'], [])
        self.assertIsNone(state['performance']['time_weighted_return_pct'])

    def test_official_total_return_benchmark_requires_matching_boundaries(self):
        self.propose()
        self.fill()
        first = BenchmarkPoint(as_of=FILL, value='1000', source=INDEX_SOURCE, captured_at=FILL)
        self.ledger.record_benchmark(first, recorded_at=FILL)
        self.ledger.mark([quote(price='110', at=LATER)], observed_at=LATER,
                         benchmark=BenchmarkPoint(as_of=LATER, value='1005', source=INDEX_SOURCE, captured_at=LATER))
        benchmark = self.ledger.public_state()['performance']['benchmark']
        self.assertEqual(benchmark['status'], 'available')
        self.assertEqual(benchmark['return_pct'], '0.5')
        self.assertEqual(benchmark['excess_return_percentage_points'], '0.5')
        for changes in ({'kind': 'sp500_price'}, {'source': SOURCE}, {'currency': 'EUR'}):
            with self.assertRaises(ValueError):
                BenchmarkPoint(**({'as_of': FILL, 'value': '1000', 'source': INDEX_SOURCE, 'captured_at': FILL} | changes))
        with self.assertRaisesRegex(ValueError, 'boundaries'):
            self.ledger.record_benchmark(BenchmarkPoint(as_of='2026-09-14T13:32:01Z', value='1001',
                                                       source=INDEX_SOURCE, captured_at='2026-09-14T13:32:01Z'),
                                         recorded_at='2026-09-14T13:32:01Z')

    def test_late_benchmark_does_not_invent_a_missing_start_point(self):
        self.propose()
        self.fill()
        state = self.ledger.mark([quote(at=LATER)], observed_at=LATER,
                                 benchmark=BenchmarkPoint(as_of=LATER, value='1005', source=INDEX_SOURCE, captured_at=LATER))
        self.assertEqual(state['performance']['benchmark']['status'], 'unavailable')

    def test_corporate_actions_require_explicit_check_and_flag_blocks_false_returns(self):
        self.propose()
        with self.assertRaisesRegex(ValueError, 'corporate-action'):
            self.fill([replace(quote(), corporate_actions_checked_through=None)])
        self.fill()
        self.ledger.flag_corporate_action('AAPL', action_id='split-1', effective_at=LATER,
                                          observed_at=LATER, source=SOURCE)
        with self.assertRaisesRegex(ValueError, 'corporate action'):
            self.ledger.mark([quote(price='50', at=LATER)], observed_at=LATER)
        state = self.ledger.public_state()
        self.assertEqual(state['status'], 'suspended')
        self.assertIsNone(state['equity'])
        self.assertIsNone(state['holdings'][0]['market_value'])
        self.assertIsNone(state['performance']['time_weighted_return_pct'])

    def test_supersession_is_explicit_and_cancelled_intents_cannot_fill(self):
        self.propose()
        with self.assertRaisesRegex(ValueError, 'supersede'):
            self.propose({'MSFT': '0.1'}, decision_id='decision-2')
        self.propose({'MSFT': '0.1'}, decision_id='decision-2', supersedes='decision-1')
        with self.assertRaisesRegex(ValueError, 'pending'):
            self.fill()
        state = self.ledger.public_state()
        self.assertEqual([item['id'] for item in state['pending_decisions']], ['decision-2'])
        self.assertEqual(len([event for event in self.ledger.events() if event['kind'] == 'cancel']), 1)

    def test_sale_first_rebalances_without_shorting_or_reusing_sale_proceeds_twice(self):
        self.propose({'AAPL': '0.2'})
        self.fill()
        self.propose({'MSFT': '0.2'}, decision_id='decision-2', decided_at=LATER)
        at = '2026-09-14T13:33:00Z'
        result = self.ledger.fill_pending('decision-2', quotes=[quote(at=at), quote('MSFT', at=at)],
                                          now=at, market_session=session())
        self.assertEqual([item['side'] for item in result['fills']], ['sell', 'buy'])
        state = self.ledger.public_state()
        self.assertEqual([holding['symbol'] for holding in state['holdings']], ['MSFT'])
        self.assertEqual(state['cash'], '80000')
        self.assertEqual(state['equity'], '100000')

    def test_fractional_share_arithmetic_is_exact_despite_ambient_precision(self):
        path = Path(self.directory.name) / 'fractional.sqlite'
        with PortfolioLedger(path, Mandate(share_decimals=6), created_at=CREATED) as ledger:
            ledger.register_universe(fixture_universe())
            with localcontext() as context:
                context.prec = 2
                ledger.propose('decision', decided_at=DECIDED, targets={'AAPL': '0.1'},
                               universe_id='membership-20260913', evidence_refs=['evidence'])
                result = ledger.fill_pending('decision', quotes=[quote(price='123.45678901')],
                                             now=FILL, market_session=session())
                state = ledger.public_state()
            expected_quantity = Decimal('81')
            self.assertEqual(Decimal(result['fills'][0]['quantity']), expected_quantity)
            expected_notional = expected_quantity * Decimal('123.45678901')
            self.assertEqual(Decimal(state['cash']), Decimal('100000') - expected_notional)
            self.assertEqual(state['equity'], '100000')

    def test_database_event_immutability_and_frozen_mandate(self):
        self.propose()
        for sql in ('UPDATE paper_events SET at="2026-09-14T13:00:00Z"', 'DELETE FROM paper_events',
                    'UPDATE paper_universe SET payload="{}"', 'DELETE FROM paper_config'):
            with self.assertRaises(sqlite3.IntegrityError):
                self.ledger.db.execute(sql)
        with self.assertRaisesRegex(ValueError, 'frozen'):
            PortfolioLedger(self.path, Mandate(initial_cash='1'))

    def test_backdated_event_rejected_without_partial_accounting(self):
        self.propose()
        self.fill()
        before = self.ledger.public_state()
        with self.assertRaisesRegex(ValueError, 'backdated'):
            self.ledger.deposit('10', external_id='past-funding', at=DECIDED, quotes=[quote(at=DECIDED)])
        self.assertEqual(self.ledger.public_state(), before)

    def test_failed_final_weight_check_rolls_back_all_trade_legs(self):
        path = Path(self.directory.name) / 'max-weight.sqlite'
        with PortfolioLedger(path, Mandate(share_decimals=6), created_at=CREATED) as ledger:
            ledger.register_universe(fixture_universe())
            ledger.propose('decision', decided_at=DECIDED, targets={'AAPL': '0.2', 'MSFT': '0.2'},
                           universe_id='membership-20260913', evidence_refs=['evidence'])
            ledger.fill_pending('decision', quotes=[quote(), quote('MSFT')], now=FILL, market_session=session())
            ledger.propose('decision-2', decided_at=LATER, targets={'MSFT': '0.2'},
                           universe_id='membership-20260913', evidence_refs=['evidence'])
            before = ledger.public_state()
            at = '2026-09-14T13:33:00Z'
            with self.assertRaisesRegex(ValueError, 'final marked position limit'):
                ledger.fill_pending('decision-2', quotes=[quote(price='100', bid='1', at=at), quote('MSFT', at=at)],
                                    now=at, market_session=session())
            self.assertEqual(ledger.public_state(), before)

    def test_next_open_requires_precommitted_open_and_keeps_simulated_prices_explicit(self):
        self.propose(expected_open_at=OPEN, calendar_source=SOURCE)
        bar = DailyBar(symbol='AAPL', opens_at=OPEN, open='100', high='110', low='95', close='105',
                       observed_at=FILL, source=SOURCE, corporate_actions_checked_through=FILL)
        result = self.ledger.fill_at_next_open('decision-1', bars=[bar], now=FILL, market_session=session())
        self.assertEqual(result['execution_model'], 'next_open_fixed_slippage')
        self.assertIs(result['simulated'], True)
        self.assertEqual(result['slippage_bps'], '5')
        self.assertEqual(result['quotes'], [])
        self.assertEqual(result['bars'][0]['open'], '100')
        self.assertEqual(result['fills'][0]['price'], '100.05')
        self.assertEqual(result['fills'][0]['quote_at'], OPEN)
        self.assertEqual(self.ledger.public_state()['performance']['started_at'], OPEN)
        self.assertEqual(self.ledger.public_state()['holdings'][0]['price'], '100')
        self.assertEqual(self.ledger.public_state()['performance']['investment_pnl'], '-4.95')

    def test_daily_bar_later_high_low_close_do_not_affect_opening_execution(self):
        self.propose(expected_open_at=OPEN, calendar_source=SOURCE)
        bar = DailyBar(symbol='AAPL', opens_at=OPEN, open='100', high='999', low='1', close='900',
                       observed_at=FILL, source=SOURCE, corporate_actions_checked_through=FILL)
        result = self.ledger.fill_at_next_open('decision-1', bars=[bar], now=FILL, market_session=session())
        self.assertEqual(result['fills'][0]['quantity'], '99')
        self.assertEqual(result['fills'][0]['price'], '100.05')
        self.assertEqual(result['nav']['prices']['AAPL']['price'], '100')

    def test_daily_bar_cannot_choose_a_later_open_or_execute_before_market_opens(self):
        self.propose(expected_open_at=OPEN, calendar_source=SOURCE)
        bar = DailyBar(symbol='AAPL', opens_at=OPEN, open='100', high='100', low='100', close='100',
                       observed_at=FILL, source=SOURCE, corporate_actions_checked_through=FILL)
        with self.assertRaisesRegex(ValueError, 'not opened'):
            self.ledger.fill_at_next_open('decision-1', bars=[bar], now=DECIDED, market_session=session())
        later_session = MarketSession(opens_at='2026-09-15T13:30:00Z', closes_at='2026-09-15T20:00:00Z', source=SOURCE)
        later = replace(bar, opens_at=later_session.opens_at, observed_at='2026-09-15T13:31:00Z',
                        corporate_actions_checked_through='2026-09-15T13:31:00Z')
        with self.assertRaisesRegex(ValueError, 'next opening frozen'):
            self.ledger.fill_at_next_open('decision-1', bars=[later], now=later.observed_at, market_session=later_session)
        self.assertEqual(self.ledger.public_state()['cash'], '100000')

    def test_daily_bar_fails_on_intervening_funding_or_missing_corporate_action_review(self):
        self.propose(expected_open_at=OPEN, calendar_source=SOURCE)
        bar = DailyBar(symbol='AAPL', opens_at=OPEN, open='100', high='100', low='100', close='100',
                       observed_at=FILL, source=SOURCE)
        with self.assertRaisesRegex(ValueError, 'corporate-action'):
            self.ledger.fill_at_next_open('decision-1', bars=[bar], now=FILL, market_session=session())
        self.ledger.deposit('100', external_id='late-funding', at='2026-09-14T13:30:30Z')
        with self.assertRaisesRegex(ValueError, 'Intervening accounting'):
            self.ledger.fill_at_next_open('decision-1', bars=[replace(bar, corporate_actions_checked_through=FILL)],
                                          now=FILL, market_session=session())

    def test_daily_bar_without_precommitted_next_open_is_rejected(self):
        self.propose()
        bar = DailyBar(symbol='AAPL', opens_at=OPEN, open='100', high='100', low='100', close='100',
                       observed_at=FILL, source=SOURCE, corporate_actions_checked_through=FILL)
        with self.assertRaisesRegex(ValueError, 'next opening frozen'):
            self.ledger.fill_at_next_open('decision-1', bars=[bar], now=FILL, market_session=session())

    def test_public_projection_contains_no_private_rationale_or_raw_evidence(self):
        self.propose(rationale='This private analysis must never be copied to a web page.')
        serialized = json.dumps(self.ledger.public_state())
        self.assertNotIn('private analysis', serialized)
        self.assertNotIn('filing-sha256', serialized)
        self.assertNotIn(SOURCE, serialized)
        self.assertEqual(self.ledger.public_state()['pending_decisions'][0]['evidence_count'], 1)

    def test_invalid_numeric_time_and_source_contracts_fail(self):
        for value in ('NaN', 'Infinity', '1e2', '-1', '01', '0.000000001', 100, True):
            with self.assertRaises(ValueError):
                Mandate(initial_cash=value)
        for at in ('2026-09-14', '2026-09-14T13:30:00+00:00', '2026-09-14T13:30:00.1Z'):
            with self.assertRaises(ValueError):
                quote(at=at)
        with self.assertRaises(ValueError):
            quote(bid='101', ask='100')
        with self.assertRaises(ValueError):
            replace(quote(), source='https://user:secret@example.com/quote')


if __name__ == '__main__':
    unittest.main()
