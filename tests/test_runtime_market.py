"""Source parsing, real-calendar boundaries and paper-adapter integration fixtures."""
from copy import deepcopy
from datetime import datetime
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest

from portfolio_runtime import PortfolioLedger, UniverseSnapshot
from portfolio_runtime.contracts import BenchmarkPoint, YAHOO_SP500TR, timestamp
from portfolio_runtime.market import (CALENDAR_SOURCE, YahooMarketData, chart_url, latest_completed_session,
                                      next_session, parse_benchmark, parse_chart, session_for_day)


SUNDAY = '2026-09-13T15:00:00Z'
MONDAY_OPEN = '2026-09-14T13:30:00Z'
MONDAY_CAPTURE = '2026-09-14T13:31:00Z'
MONDAY_CLOSE_CAPTURE = '2026-09-14T20:01:00Z'


def epoch(at):
    return int(timestamp(at).timestamp())


def fixture(ticker='AAPL', *, monday=True, close=105, events=None, closed=False):
    opens = ['2026-09-11T13:30:00Z'] + ([MONDAY_OPEN] if monday else [])
    prices = {'open': [100] * len(opens), 'high': [110] * len(opens), 'low': [95] * len(opens),
              'close': [close] * len(opens), 'volume': [1000000] * len(opens)}
    result = {'meta': {'symbol': ticker.replace('.', '-'), 'currency': 'USD', 'instrumentType': 'EQUITY',
                       'exchangeTimezoneName': 'America/New_York', 'dataGranularity': '1d',
                       'regularMarketTime': epoch(('2026-09-14T20:00:00Z' if closed else MONDAY_CAPTURE)
                                                  if monday else '2026-09-11T20:00:00Z')},
              'timestamp': [epoch(at) for at in opens], 'indicators': {'quote': [prices]}}
    if events is not None:
        result['events'] = events
    return {'chart': {'result': [result], 'error': None}}


def raw(value):
    return json.dumps(value).encode()


class Response(BytesIO):
    status = 200

    def __init__(self, body, url):
        super().__init__(body)
        self.url = url

    def geturl(self):
        return self.url


class FixtureMarket(YahooMarketData):
    def __init__(self, directory, *, now, fixtures):
        self.now, self.fixtures, self.calls = now, fixtures, []
        super().__init__(directory, clock=lambda: self.now, benchmark_enabled=False)

    def fetch(self, ticker):
        self.calls.append(ticker)
        return parse_chart(raw(self.fixtures[ticker]), ticker, captured_at=self.now)


class MarketAdapterTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def ledger(self):
        ledger = PortfolioLedger(self.path / 'paper.sqlite', created_at=SUNDAY)
        ledger.register_universe(UniverseSnapshot(snapshot_id='universe', effective_at='2026-09-11T00:00:00Z',
                                                  captured_at=SUNDAY, symbols=('AAPL', 'MSFT'), source=CALENDAR_SOURCE,
                                                  expires_at='2026-09-20T00:00:00Z'))
        return ledger

    def propose(self, ledger):
        session = next_session(SUNDAY)
        return ledger.propose('decision', decided_at=SUNDAY, targets={'AAPL': '0.1'}, universe_id='universe',
                               evidence_refs=['source-evidence'], expected_open_at=session.opens_at,
                               calendar_source=session.source)

    def test_calendar_sunday_holiday_and_strictly_next_open(self):
        self.assertEqual(next_session(SUNDAY).opens_at, MONDAY_OPEN)
        self.assertEqual(next_session(MONDAY_OPEN).opens_at, '2026-09-15T13:30:00Z')
        self.assertEqual(next_session('2026-09-04T20:01:00Z').opens_at, '2026-09-08T13:30:00Z')
        self.assertEqual(next_session('2026-07-02T20:01:00Z').opens_at, '2026-07-06T13:30:00Z')
        self.assertIsNone(session_for_day('2026-04-03'))

    def test_calendar_early_close_dst_and_year_expiry(self):
        self.assertEqual(session_for_day('2026-11-27').closes_at, '2026-11-27T18:00:00Z')
        self.assertEqual(session_for_day('2026-12-24').closes_at, '2026-12-24T18:00:00Z')
        self.assertEqual(session_for_day('2026-03-06').opens_at, '2026-03-06T14:30:00Z')
        self.assertEqual(session_for_day('2026-03-09').opens_at, '2026-03-09T13:30:00Z')
        with self.assertRaisesRegex(ValueError, '2026 only'):
            next_session('2026-12-31T21:00:00Z')
        with self.assertRaises(ValueError):
            session_for_day('2027-01-04')

    def test_latest_completed_session_does_not_use_an_incomplete_day(self):
        self.assertEqual(latest_completed_session(MONDAY_CAPTURE).closes_at, '2026-09-11T20:00:00Z')
        self.assertEqual(latest_completed_session(MONDAY_CLOSE_CAPTURE).closes_at, '2026-09-14T20:00:00Z')
        self.assertEqual(latest_completed_session('2026-11-27T18:00:00Z').closes_at, '2026-11-27T18:00:00Z')

    def test_parse_preserves_provider_source_actions_and_rounding(self):
        data = fixture()
        data['chart']['result'][0]['indicators']['quote'][0]['open'][1] = 100.123456789
        action_at = epoch(MONDAY_OPEN)
        data['chart']['result'][0]['events'] = {'dividends': {str(action_at): {'date': action_at, 'amount': 0.25}}}
        result = parse_chart(raw(data), 'AAPL', captured_at=MONDAY_CAPTURE)
        self.assertEqual(result.provider, 'Yahoo Finance')
        self.assertEqual(result.bars[-1].open, '100.12345679')
        self.assertEqual(result.actions[0]['kind'], 'dividends')
        self.assertEqual(result.actions[0]['amount'], '0.25')
        self.assertIn('events=div%2Csplits', result.source)
        self.assertEqual(result.bars[-1].corporate_actions_checked_through, MONDAY_CAPTURE)
        self.assertEqual(len(result.source_sha256), 64)

    def test_share_class_mapping_is_explicit_and_bad_symbols_cannot_form_urls(self):
        self.assertIn('/BRK-B?', chart_url('BRK.B'))
        result = parse_chart(raw(fixture('BRK.B')), 'BRK.B', captured_at=MONDAY_CAPTURE)
        self.assertEqual(result.symbol, 'BRK.B')
        self.assertEqual(result.bars[-1].symbol, 'BRK.B')
        for ticker in ('../MSFT', 'MSFT?secret=x', 'msft', 'AAPL/USD'):
            with self.assertRaises(ValueError):
                chart_url(ticker)

    def test_wrong_currency_symbol_instrument_and_granularity_fail(self):
        for field, value in (('currency', 'CAD'), ('symbol', 'MSFT'), ('instrumentType', 'ETF'),
                             ('dataGranularity', '1m'), ('exchangeTimezoneName', 'Europe/London')):
            data = fixture()
            data['chart']['result'][0]['meta'][field] = value
            with self.assertRaises(ValueError):
                parse_chart(raw(data), 'AAPL', captured_at=MONDAY_CAPTURE)

    def test_missing_partial_zero_volume_future_and_wrong_session_bars_fail(self):
        for kind in ('partial', 'volume', 'future', 'holiday', 'duplicate'):
            data = fixture()
            item = data['chart']['result'][0]
            if kind == 'partial': item['indicators']['quote'][0]['open'][0] = None
            if kind == 'volume': item['indicators']['quote'][0]['volume'][0] = 0
            if kind == 'future': item['timestamp'][1] = epoch('2026-09-15T13:30:00Z')
            if kind == 'holiday': item['timestamp'][0] = epoch('2026-09-07T13:30:00Z')
            if kind == 'duplicate': item['timestamp'][1] = item['timestamp'][0]
            with self.assertRaises(ValueError):
                parse_chart(raw(data), 'AAPL', captured_at=MONDAY_CAPTURE)

    def test_bad_corporate_action_payload_never_becomes_no_actions(self):
        action_at = epoch(MONDAY_OPEN)
        for events in ({'capitalGains': {}}, {'splits': {'wrong-key': {'date': action_at, 'numerator': 2, 'denominator': 1}}},
                       {'splits': {str(action_at): {'date': action_at, 'numerator': 2, 'denominator': 0}}},
                       {'dividends': {str(action_at): {'date': action_at, 'amount': None}}}):
            with self.assertRaises(ValueError):
                parse_chart(raw(fixture(events=events)), 'AAPL', captured_at=MONDAY_CAPTURE)

    def test_historical_visa_mapping_key_uses_explicit_date_and_allows_monday_portfolio_fill(self):
        # Exact observed Visa event: outer key Aug 12, explicit date Aug 11.
        events = {'dividends': {'1786541400': {'date': 1786455000, 'amount': 0.67}}}
        snapshot = parse_chart(raw(fixture('V', monday=False, events=events)), 'V', captured_at=SUNDAY)
        self.assertEqual(snapshot.actions[0]['effective_at'], '2026-08-11T13:30:00Z')
        self.assertEqual(snapshot.actions[0]['amount'], '0.67')
        self.assertLess(timestamp(snapshot.actions[0]['effective_at']), timestamp(SUNDAY))
        with PortfolioLedger(self.path / 'visa.sqlite', created_at=SUNDAY) as ledger:
            ledger.register_universe(UniverseSnapshot(snapshot_id='visa-universe', effective_at='2026-09-11T00:00:00Z',
                captured_at=SUNDAY, symbols=('AAPL', 'V'), source=CALENDAR_SOURCE, expires_at='2026-09-20T00:00:00Z'))
            ledger.propose('visa-decision', decided_at=SUNDAY, targets={'AAPL': '0.1', 'V': '0.04'},
                universe_id='visa-universe', evidence_refs=['saved-price-source'], expected_open_at=MONDAY_OPEN,
                calendar_source=CALENDAR_SOURCE)
            market = FixtureMarket(self.path, now=SUNDAY,
                fixtures={'AAPL': fixture(monday=False), 'V': fixture('V', monday=False, events=events)})
            quote = market.snapshot_price('V')
            self.assertEqual(quote['as_of'], '2026-09-11T20:00:00Z')
            self.assertEqual(market.fill_pending(ledger)['status'], 'waiting_for_market')
            self.assertEqual(ledger.public_state()['history'], [])
            market.now = MONDAY_CAPTURE
            market.fixtures = {'AAPL': fixture(), 'V': fixture('V', events=events)}
            self.assertEqual(market.fill_pending(ledger)['status'], 'filled')
            state = ledger.public_state()
            self.assertEqual({holding['symbol'] for holding in state['holdings']}, {'AAPL', 'V'})
            self.assertEqual(state['history'][0]['at'], MONDAY_OPEN)
            cash = state['cash']
            market.now = MONDAY_CLOSE_CAPTURE
            market.fixtures = {'AAPL': fixture(closed=True), 'V': fixture('V', closed=True, events=events)}
            self.assertEqual(market.mark_close(ledger)['status'], 'marked')
            self.assertEqual(ledger.public_state()['cash'], cash)
            self.assertFalse(any(event['kind'] == 'action_flag' for event in ledger.events()))

    def test_mismatched_action_keys_cannot_bypass_future_malformed_or_held_action_guards(self):
        future = epoch('2026-09-15T13:30:00Z')
        current = epoch(MONDAY_OPEN)
        for events in (
            {'dividends': {str(future + 86400): {'date': future, 'amount': 0.67}}},
            {'dividends': {str(current + 86400): {'date': current, 'amount': None}}},
            {'splits': {str(current + 86400): {'date': current, 'numerator': 2, 'denominator': 0}}},
        ):
            with self.assertRaises(ValueError):
                parse_chart(raw(fixture(events=events)), 'AAPL', captured_at=MONDAY_CAPTURE)
        for kind, details in (('dividends', {'amount': 0.67}), ('splits', {'numerator': 2, 'denominator': 1})):
            with self.subTest(kind=kind):
                path = self.path / ('held-' + kind + '.sqlite')
                with PortfolioLedger(path, created_at=SUNDAY) as ledger:
                    ledger.register_universe(UniverseSnapshot(snapshot_id='universe', effective_at='2026-09-11T00:00:00Z',
                        captured_at=SUNDAY, symbols=('AAPL',), source=CALENDAR_SOURCE, expires_at='2026-09-20T00:00:00Z'))
                    self.propose(ledger)
                    market = FixtureMarket(self.path, now=MONDAY_CAPTURE, fixtures={'AAPL': fixture()})
                    market.fill_pending(ledger)
                    action_at = epoch('2026-09-14T14:00:00Z')
                    market.fixtures['AAPL'] = fixture(closed=True, events={kind: {
                        str(action_at + 86400): {'date': action_at, **details}}})
                    market.now = MONDAY_CLOSE_CAPTURE
                    with self.assertRaisesRegex(ValueError, 'corporate action'):
                        market.mark_close(ledger)
                    self.assertEqual(ledger.public_state()['status'], 'suspended')
                    self.assertEqual(len(ledger.public_state()['history']), 1)

    def test_fetch_is_bounded_readonly_and_captures_exact_source_bytes(self):
        body = raw(fixture(monday=False))
        requests = []
        def opener(request, timeout):
            requests.append((request.full_url, request.get_method(), timeout))
            return Response(body, request.full_url)
        market = YahooMarketData(self.path, opener=opener, clock=lambda: SUNDAY)
        result = market.fetch('AAPL')
        self.assertEqual(requests, [(chart_url('AAPL'), 'GET', 20)])
        raw_files = [file for file in self.path.glob('*.json') if not file.name.endswith('.meta.json')]
        self.assertEqual(len(raw_files), 1)
        self.assertEqual(raw_files[0].read_bytes(), body)
        metadata = json.loads(next(self.path.glob('*.meta.json')).read_text())
        self.assertEqual(metadata['sha256'], result.source_sha256)
        self.assertEqual(metadata['provider'], 'Yahoo Finance')

    def test_fetch_rejects_redirects_and_oversized_data(self):
        market = YahooMarketData(self.path, opener=lambda request, timeout: Response(raw(fixture()), 'https://other.example/chart'),
                                 clock=lambda: MONDAY_CAPTURE)
        with self.assertRaisesRegex(ValueError, 'allowlisted'):
            market.fetch('AAPL')
        with self.assertRaises(ValueError):
            parse_chart(b' ' * 2_000_001, 'AAPL', captured_at=MONDAY_CAPTURE)

    def test_research_snapshot_retains_friday_timestamp_on_sunday(self):
        market = FixtureMarket(self.path, now=SUNDAY, fixtures={'AAPL': fixture(monday=False)})
        value = market.snapshot_price('AAPL')
        self.assertEqual(value['price_kind'], 'daily_close')
        self.assertEqual(value['as_of'], '2026-09-11T20:00:00Z')
        self.assertEqual(value['captured_at'], SUNDAY)
        self.assertFalse(value['adjusted'])

    def test_end_to_end_sunday_wait_monday_open_and_close(self):
        with self.ledger() as ledger:
            self.propose(ledger)
            market = FixtureMarket(self.path, now=SUNDAY, fixtures={'AAPL': fixture(monday=False)})
            waiting = market.fill_pending(ledger)
            self.assertEqual(waiting['status'], 'waiting_for_market')
            self.assertEqual(market.calls, [])
            self.assertEqual(market.mark_close(ledger)['status'], 'waiting_for_first_session')
            self.assertEqual(ledger.public_state()['history'], [])
            market.now, market.fixtures['AAPL'] = MONDAY_CAPTURE, fixture()
            filled = market.fill_pending(ledger)
            self.assertEqual(filled['status'], 'filled')
            self.assertEqual(filled['receipt']['execution_model'], 'next_open_fixed_slippage')
            self.assertEqual(market.fill_pending(ledger)['status'], 'no_pending_decision')
            market.now = MONDAY_CLOSE_CAPTURE
            market.fixtures['AAPL'] = fixture(closed=True)
            marked = market.mark_close(ledger)
            self.assertEqual(marked['status'], 'marked')
            state = marked['portfolio']
            self.assertEqual(state['holdings'][0]['price'], '105')
            self.assertEqual([point['at'] for point in state['history']], [MONDAY_OPEN, '2026-09-14T20:00:00Z'])
            self.assertEqual(state['performance']['benchmark']['status'], 'unavailable')
            self.assertEqual(market.mark_close(ledger)['status'], 'up_to_date')
            closing_event = [event for event in ledger.events() if event['kind'] == 'mark'][0]
            self.assertEqual(closing_event['payload']['valuation_model'], 'daily_close')
            self.assertEqual(closing_event['payload']['quotes'], [])

    def test_reported_split_suspends_existing_holding_instead_of_recording_a_loss(self):
        with self.ledger() as ledger:
            self.propose(ledger)
            market = FixtureMarket(self.path, now=MONDAY_CAPTURE, fixtures={'AAPL': fixture()})
            market.fill_pending(ledger)
            action_at = epoch('2026-09-14T14:00:00Z')
            market.fixtures['AAPL'] = fixture(closed=True, events={'splits': {str(action_at): {
                'date': action_at, 'numerator': 2, 'denominator': 1}}})
            market.now = MONDAY_CLOSE_CAPTURE
            with self.assertRaisesRegex(ValueError, 'corporate action'):
                market.mark_close(ledger)
            state = ledger.public_state()
            self.assertEqual(state['status'], 'suspended')
            self.assertIsNone(state['equity'])
            self.assertEqual(len(state['history']), 1)

    def test_old_actions_before_acquisition_do_not_claim_dividend_entitlement(self):
        action_at = epoch('2026-09-11T13:30:00Z')
        events = {'dividends': {str(action_at): {'date': action_at, 'amount': 1}}}
        with self.ledger() as ledger:
            self.propose(ledger)
            market = FixtureMarket(self.path, now=MONDAY_CAPTURE, fixtures={'AAPL': fixture(events=events)})
            market.fill_pending(ledger)
            market.now = MONDAY_CLOSE_CAPTURE
            market.fixtures['AAPL'] = fixture(events=events, closed=True)
            result = market.mark_close(ledger)
            self.assertEqual(result['status'], 'marked')
            self.assertEqual(ledger.public_state()['cash'], '90095.05')
            self.assertFalse(any(event['kind'] == 'action_flag' for event in ledger.events()))

    def test_mismatched_calendar_commitment_and_provider_missing_open_remain_pending(self):
        with self.ledger() as ledger:
            ledger.propose('decision', decided_at=SUNDAY, targets={'AAPL': '0.1'}, universe_id='universe',
                           evidence_refs=['evidence'], expected_open_at='2026-09-15T13:30:00Z', calendar_source=CALENDAR_SOURCE)
            market = FixtureMarket(self.path, now=MONDAY_CAPTURE, fixtures={'AAPL': fixture()})
            with self.assertRaisesRegex(ValueError, 'calendar'):
                market.fill_pending(ledger)
            self.assertEqual(ledger.public_state()['status'], 'pending')

    def test_fresh_http_capture_does_not_turn_an_intraday_bar_into_a_close(self):
        with self.ledger() as ledger:
            self.propose(ledger)
            market = FixtureMarket(self.path, now=MONDAY_CAPTURE, fixtures={'AAPL': fixture()})
            market.fill_pending(ledger)
            market.now = MONDAY_CLOSE_CAPTURE
            with self.assertRaisesRegex(ValueError, 'not confirmed'):
                market.mark_close(ledger)
            self.assertEqual(len(ledger.public_state()['history']), 1)

    def benchmark_fixture(self, *, closed=True):
        result = fixture(closed=closed)
        item = result['chart']['result'][0]
        item['meta'].update(symbol='^SP500TR', instrumentType='INDEX', longName='S&P 500 (TR)')
        item['indicators']['quote'][0]['volume'] = [0, 0]
        return result

    def test_benchmark_requires_exact_total_return_identity_and_uses_observed_ohlc(self):
        source = self.benchmark_fixture()
        points = parse_benchmark(raw(source), captured_at=MONDAY_CLOSE_CAPTURE)
        self.assertEqual([point.as_of for point in points][-2:], [MONDAY_OPEN, '2026-09-14T20:00:00Z'])
        self.assertEqual([point.value for point in points][-2:], ['100', '105'])
        self.assertEqual(points[-1].source, YAHOO_SP500TR)
        self.assertEqual(len(points[-1].source_sha256), 64)
        for field, value in (('symbol', '^GSPC'), ('instrumentType', 'ETF'), ('longName', 'S&P 500'), ('currency', 'EUR')):
            changed = deepcopy(source)
            changed['chart']['result'][0]['meta'][field] = value
            with self.assertRaises(ValueError):
                parse_benchmark(raw(changed), captured_at=MONDAY_CLOSE_CAPTURE)

    def test_benchmark_cannot_backfill_a_close_from_an_unfinished_bar(self):
        points = parse_benchmark(raw(self.benchmark_fixture(closed=False)), captured_at=MONDAY_CAPTURE)
        self.assertEqual(points[-1].as_of, MONDAY_OPEN)
        self.assertNotIn('2026-09-14T20:00:00Z', [point.as_of for point in points])

    def test_third_party_index_contract_requires_exact_endpoint_and_source_digest(self):
        for source, digest in ((YAHOO_SP500TR.replace('%5ESP500TR', '%5EGSPC'), 'a' * 64), (YAHOO_SP500TR, None)):
            with self.assertRaises(ValueError):
                BenchmarkPoint(as_of=MONDAY_OPEN, value='100', captured_at=MONDAY_CAPTURE,
                               source=source, source_sha256=digest)

    def test_benchmark_attaches_only_aligned_actual_portfolio_boundaries(self):
        with self.ledger() as ledger:
            self.propose(ledger)
            market = FixtureMarket(self.path, now=MONDAY_CAPTURE, fixtures={'AAPL': fixture()})
            market.fill_pending(ledger)
            market.now = MONDAY_CLOSE_CAPTURE
            market.fixtures['AAPL'] = fixture(closed=True)
            market.mark_close(ledger)
            market.benchmark_enabled = True
            market.fetch_benchmark = lambda: parse_benchmark(raw(self.benchmark_fixture()), captured_at=market.now)
            synced = market.sync_benchmark(ledger)
            self.assertEqual(synced['observations_added'], 2)
            self.assertEqual(synced['status'], 'available')
            self.assertEqual(synced['portfolio']['performance']['benchmark']['return_pct'], '5')
            self.assertEqual(market.sync_benchmark(ledger)['observations_added'], 0)
            points = [event['payload'] for event in ledger.events() if event['kind'] == 'benchmark']
            self.assertEqual([point['as_of'] for point in points], [MONDAY_OPEN, '2026-09-14T20:00:00Z'])

    def test_benchmark_feed_failure_does_not_reverse_or_duplicate_paper_execution(self):
        with self.ledger() as ledger:
            self.propose(ledger)
            market = FixtureMarket(self.path, now=MONDAY_CAPTURE, fixtures={'AAPL': fixture()})
            market.benchmark_enabled = True
            def unavailable():
                raise OSError('feed temporarily unavailable')
            market.fetch_benchmark = unavailable
            result = market.fill_pending(ledger)
            self.assertEqual(result['status'], 'filled')
            self.assertEqual(result['portfolio']['performance']['benchmark']['status'], 'unavailable')
            self.assertEqual(market.fill_pending(ledger)['status'], 'no_pending_decision')
            self.assertEqual(len([event for event in ledger.events() if event['kind'] == 'rebalance']), 1)


if __name__ == '__main__':
    unittest.main()
