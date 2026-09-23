"""Phase-one acceptance checks: no hidden budget release, reproducible evidence, honest clocks."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from league.campaigns import CampaignBudget, CampaignClosed, CampaignPacer
from league.experiments import Archive, ArtifactError, Experiments, reproduce, reproduce_evaluation
from league.evaluator import Evaluator
from league.frontier import Frontier, FrontierError
from league.funded import FundedTransport
from league.ledger import Ledger, canonical
from league.recordings import Recorder
from league.replay import run_replay
from league.tapes import AlpacaData, parse_time
from league.tests.test_frontier import FakeOpener, ok
from league.tests.test_replay import alpaca_tape, kalshi_tape, market, script as scripted, event, MKT, t_at
from ltcm.provider import BudgetExceeded, Provider


def policy():
    return {'phase': 'test', 'duration_hours': 48, 'total_cap_usd': '10',
            'caps_usd': {'sail': '5', 'openai': '5'}, 'daily_caps_usd': {'sail': '5', 'openai': '5'},
            'external_reserves_usd': {}, 'allow_new_live_capital': False,
            'campaigns': {name: {'kind': kind, 'cap_usd': '5', 'question': 'q', 'baseline': 'b',
                               'artifact': 'a', 'acceptance': 'c'} for name, kind in
                          [('baseline-research', 'sail'), ('foundation-review', 'openai')]}}


class PhaseCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = [1800000000.0]
        self.clock = lambda: self.now[0]

    def budget(self, rules=None):
        guard = CampaignBudget(self.root / 'campaigns.sqlite', rules or policy(), clock=self.clock)
        self.addCleanup(guard.close)
        return guard


class EngineeringBacklogReport(PhaseCase):
    def test_report_recovers_legacy_advice_and_preserves_unresolved_work(self):
        from league.phase1 import report
        self.budget()
        ledger = Ledger(self.root / 'ledger.sqlite', clock=self.clock)
        self.addCleanup(ledger.close)
        recorder = Recorder(self.root / 'recordings.sqlite')
        self.addCleanup(recorder.close)
        ledger.append('tool.request', {'name': 'feed'}, id='req')
        ledger.append('tool.fulfilled', {'request': 'req', 'status': 'answered',
                                        'outcome': 'cannot be a pure tool: missing observations'})
        before = ledger.count()
        row = report(self.root, now=self.clock())['tool_requests']
        self.assertEqual(row['by_status'], {'blocked': 1})
        self.assertEqual(row['blocked'][0]['id'], 'req')
        self.assertEqual(ledger.count(), before)
        ledger.append('tool.fulfilled', {'request': 'req', 'status': 'deployed', 'outcome': 'verified'})
        self.assertEqual(report(self.root, now=self.clock())['tool_requests']['blocked'], [])


class CampaignTests(PhaseCase):
    def test_concurrent_connections_cannot_overspend(self):
        guards = [self.budget(), self.budget()]
        def attempt(i):
            try:
                guards[i % 2].reserve(str(i), 'baseline-research', 1)
                return True
            except CampaignClosed:
                return False
        with ThreadPoolExecutor(max_workers=10) as pool:
            self.assertEqual(sum(pool.map(attempt, range(30))), 5)
        self.assertEqual(guards[0].remaining('sail'), 0)

    def test_restart_timeout_and_deadline_do_not_release_holds(self):
        guard = self.budget()
        guard.reserve('pending', 'baseline-research', 3)
        restarted = self.budget()
        self.assertEqual(restarted.remaining('sail'), 2)
        self.assertEqual(restarted.started, guard.started)
        self.now[0] += 48 * 3600 + 1
        restarted.reserve('pending', 'baseline-research', 3)  # reconcile the existing call
        with self.assertRaises(CampaignClosed):
            restarted.reserve('new', 'baseline-research', 1)
        restarted.settle('pending', '0.4')
        restarted.settle('pending', '0.4')
        self.assertEqual(restarted.remaining('sail'), Decimal('4.6'))
        self.assertFalse(restarted.running())

    def test_daily_admission_and_external_reserve(self):
        rules = policy()
        rules['external_reserves_usd'] = {'openai': '4'}
        rules['daily_caps_usd']['sail'] = '1'
        guard = self.budget(rules)
        with self.assertRaises(CampaignClosed):
            guard.reserve('o', 'foundation-review', '1.01')
        guard.reserve('s', 'baseline-research', 1)
        with self.assertRaises(CampaignClosed):
            guard.reserve('s2', 'baseline-research', '.01')
        self.now[0] += 86400
        guard.reserve('s2', 'baseline-research', 1)

    def test_identity_changes_or_overcharge_stop_new_spending(self):
        guard = self.budget()
        guard.reserve('r', 'baseline-research', 1)
        with self.assertRaises(CampaignClosed):
            guard.reserve('r', 'baseline-research', 2)
        guard.settle('r', 2)
        with self.assertRaises(CampaignClosed):
            guard.reserve('next', 'foundation-review', '.01')
        with self.assertRaises(CampaignClosed):
            guard.settle('r', 0)

    def test_vendor_meter_counts_hosting_once_and_requires_fresh_read(self):
        rules = policy()
        rules['meter_required'] = ['sail']
        guard = self.budget(rules)
        with self.assertRaises(CampaignClosed):
            guard.reserve('r', 'baseline-research', 1)
        guard.observe_spend('sail', 200)
        guard.reserve('r', 'baseline-research', 1)
        guard.settle('r', '.5')
        guard.observe_spend('sail', 202)
        self.assertEqual(guard.remaining('sail'), 3)  # vendor includes that model call
        self.now[0] += 181
        self.assertFalse(guard.ready('sail'))
        with self.assertRaises(CampaignClosed):
            guard.observe_spend('sail', 1)  # a reset is not a refund
        guard.observe_spend('sail', 203)
        self.assertFalse(guard.ready('sail'))  # reset requires explicit reconciliation

    def test_unused_budget_never_accelerates(self):
        guard = self.budget()
        pacer = CampaignPacer(None, guard, clock=self.clock)
        before = pacer.allowance('sail')
        self.now[0] += 86400
        self.assertEqual(pacer.allowance('sail'), before)
        self.assertTrue(pacer.report()['no_catch_up'])

    def test_frontier_denied_before_network_and_bad_cost_keeps_hold(self):
        guard = self.budget()
        opener = FakeOpener(ok(cost=None))
        model = Frontier('https://example.test', lambda: 'token', opener=opener, spend_guard=guard)
        model.ask(system='s', user='u', agent='test')
        self.assertEqual(guard.report()['pending_calls'], 1)
        self.now[0] += 48 * 3600 + 1
        with self.assertRaises(FrontierError):
            model.ask(system='s', user='u', agent='test')
        self.assertEqual(len(opener.calls), 1)

    def test_supported_openai_models_reserve_their_ceiling_and_settle_at_the_gateways_cost(self):
        # Until Sept 23, 2026 a verified call settled at max(the gateway's cost, every token at the
        # ceiling); the gateway now prices cache and long-context premiums itself, and its metered
        # cost is the settlement. The ceiling still sizes the hold.
        guard = self.budget()
        for model, rate_in, rate_out in [('gpt-5.6-luna', '.50', '1.80'),
                                         ('gpt-5.6-terra', '5', '18'), ('gpt-5.6-sol', '10', '30')]:
            with self.subTest(model=model):
                before = guard.remaining('openai')
                usage = {'input_tokens': 1000, 'output_tokens': 2000}
                opener = FakeOpener(ok(cost='0.001', model=model, usage=usage))
                Frontier('https://example.test', lambda: 'token', model=model, opener=opener,
                         spend_guard=guard).ask(system='s', user='u', agent='test')
                bound = (1000 * Decimal(rate_in) + 2000 * Decimal(rate_out)) / 1000000
                self.assertEqual(before - guard.remaining('openai'), Decimal('0.001'))
                self.assertLess(Decimal('0.001'), bound)
        self.assertEqual(guard.report()['pending_calls'], 0)
        opener = FakeOpener()
        with self.assertRaisesRegex(FrontierError, 'no verified price'):
            Frontier('https://example.test', lambda: 'token', model='unpriced', opener=opener,
                     spend_guard=guard).ask(system='s', user='u', agent='test')
        self.assertEqual(opener.calls, [])

    def test_sail_detached_settlement_survives_restart(self):
        guard = self.budget()
        calls = []
        completed = [False]
        def transport(method, route, body=None, key=None):
            calls.append((method, route))
            if 'usage/summary' in route:
                return {'available': True, 'period_spend': 200}
            if method == 'POST' or not completed[0]:
                return {'id': 'resp_one', 'status': 'queued'}
            return {'id': 'resp_one', 'status': 'completed', 'model': 'deepseek-ai/DeepSeek-V4-Pro-0813', 'usage': {'input_tokens': 100, 'output_tokens': 20}}
        wrapper = FundedTransport(transport, guard, clock=self.clock)
        provider = Provider(self.root / 'provider.sqlite')
        self.addCleanup(provider.close)
        body = provider.build_body('pro_flex', [{'role': 'user', 'content': 'hello'}], max_output_tokens=64)
        wrapper('POST', '/v1/responses', body, 'key')
        held = guard.remaining('sail')
        wrapper('POST', '/v1/responses', body, 'key')
        self.assertEqual(guard.remaining('sail'), held)
        self.now[0] += 48 * 3600 + 1
        completed[0] = True
        restarted = FundedTransport(transport, self.budget(), clock=self.clock)
        restarted('GET', '/v1/responses/resp_one')
        self.assertEqual(guard.report()['pending_calls'], 0)
        with self.assertRaises(BudgetExceeded):
            restarted('POST', '/v1/responses', body, 'new')
        self.assertEqual(sum(m == 'POST' for m, _ in calls), 1)

    def test_unknown_post_is_not_sent_again_after_restart(self):
        guard = self.budget()
        calls = []
        def transport(method, route, body=None, key=None):
            if method == 'GET':
                return {'available': True, 'period_spend': 200}
            calls.append(route)
            raise OSError('lost response')
        provider = Provider(self.root / 'provider.sqlite')
        self.addCleanup(provider.close)
        body = provider.build_body('pro_flex', [{'role':'user', 'content':'hello'}], max_output_tokens=64)
        with self.assertRaises(OSError):
            FundedTransport(transport, guard, clock=self.clock)('POST', '/v1/responses', body, 'key')
        with self.assertRaises(BudgetExceeded):
            FundedTransport(transport, self.budget(), clock=self.clock)('POST', '/v1/responses', body, 'key')
        self.assertEqual(len(calls), 1)
        self.assertEqual(guard.report()['pending_calls'], 1)


class ArtifactTests(PhaseCase):
    def test_content_identity_corruption_and_no_partial_publish(self):
        archive = Archive(self.root / 'archive', max_artifact_bytes=1000)
        data = {'unicode': 'α', 'rows': [3, 2, 1]}
        ident = archive.put(data)
        self.assertEqual(ident, hashlib.sha256(canonical(data).encode()).hexdigest())
        self.assertEqual(archive.put(data), ident)
        self.assertEqual(archive.get(ident), data)
        with self.assertRaises(ArtifactError):
            archive.put({'huge': 'x' * 2000})
        self.assertEqual(list(archive.root.glob('.artifact-*')), [])
        archive.path(ident).write_bytes(gzip.compress(b'{}'))
        with self.assertRaises(ArtifactError):
            archive.get(ident)
        with self.assertRaises(ArtifactError):
            archive.put(data)
        with self.assertRaises(ArtifactError):
            archive.get('../../secret')

    def test_archived_evaluator_reproduces_exact_result_and_records_attempt(self):
        ledger = Ledger(self.root / 'ledger.sqlite', clock=self.clock)
        self.addCleanup(ledger.close)
        records = Experiments(self.root / 'experiments', ledger, clock=self.clock)
        code, tape = scripted(), alpaca_tape([100, 101, 99])
        limits = {'max_position_usd': 100, 'max_order_usd': 75}
        result = run_replay(code, {}, tape, stake=200, limits=limits)
        attempt = records.begin(agent='test', family='family', lineage=['test'], code=code, params={},
                                needs={}, tape=tape, query='same-query', stake=200, limits=limits)
        self.assertEqual(ledger.count(kinds='experiment.started'), 1)
        finished = records.finish(attempt, result)
        self.assertEqual(canonical(reproduce(records.archive, finished['manifest'])), canonical(result))
        tape['steps'][0]['bars']['BTC/USD']['c'] = 88
        changed = records.begin(agent='test', family='family', lineage=['test'], code=code, params={},
                                needs={}, tape=tape, query='same-query', stake=200, limits=limits)
        self.assertNotEqual(changed['tape'], attempt['tape'])
        self.assertEqual(ledger.count(kinds='experiment.finished'), 1)  # interrupted attempt is visible

    def test_recorder_has_observation_times_digest_and_bounded_retention(self):
        recorder = Recorder(self.root / 'recordings.sqlite', clock=self.clock, max_bytes=200, retention_seconds=10)
        self.addCleanup(recorder.close)
        recorder.record('quotes:A', {'bid': 10}, started=self.now[0] - 1)
        row = recorder.db.execute('SELECT started,received,digest,payload FROM snapshots').fetchone()
        self.assertEqual(row[:2], (self.now[0] - 1, self.now[0]))
        raw = gzip.decompress(row[3])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), row[2])
        self.assertEqual(json.loads(raw), {'bid': 10})
        self.now[0] += 11
        recorder.record('quotes:A', {'bid': 11}, started=self.now[0])
        self.assertEqual(recorder.stats()['evicted'], 1)
        for i in range(20):
            recorder.record('quotes:A', {'bid': i}, started=self.now[0])
        self.assertLessEqual(recorder.stats()['compressed_bytes'], 200)

    def test_selection_verdict_reproduces_with_frozen_prior_trials(self):
        ledger = Ledger(self.root / 'ledger.sqlite', clock=self.clock)
        self.addCleanup(ledger.close)
        archive = Archive(self.root / 'experiments')
        ledger.append('eval.trial', {'family':'f', 'sharpe':.2}, agent='ancestor')
        result = run_replay(scripted(), {}, alpaca_tape([100, 110, 90]))
        verdict = Evaluator(ledger, archive=archive).record_trial('candidate', 'f', result, tape_id='t',
                                                               promote=False, lineage=['ancestor', 'candidate'])
        ident = verdict.numbers['evaluation_artifact']
        stored = archive.get(ident)
        self.assertEqual(stored['prior_trial_sharpes'], [.2])
        self.assertEqual(canonical(reproduce_evaluation(archive, ident)), canonical(stored['verdict']))


class ClockTests(unittest.TestCase):
    def test_daily_history_uses_intraday_execution_and_no_future_bar(self):
        class Data(AlpacaData):
            def _closed_bars(self, symbols, timeframe, start_ts, end_ts, now):
                times = ['2026-09-09T04:00:00Z', '2026-09-10T04:00:00Z', '2026-09-11T04:00:00Z'] if timeframe == '1Day' else ['2026-09-10T13:35:00Z', '2026-09-10T19:45:00Z']
                return {'SPY': [{'t': t, 'o': 100+i, 'h': 100+i, 'l': 100+i, 'c': 100+i, 'v': 1} for i,t in enumerate(times) if start_ts <= parse_time(t) <= end_ts]}
        tape = Data(None, clock=lambda: parse_time('2026-09-12T00:00:00Z')).tape(['SPY'], '1Day',
            start='2026-09-10T00:00:00Z', end='2026-09-11T00:00:00Z', warmup_bars=200)
        self.assertEqual(tape['execution_timeframe'], '5Min')
        code = scripted(symbols=['SPY'], limit=200).replace('"5Min"', '"1Day"')
        result = run_replay(code, {}, tape, audit=True)
        self.assertTrue(result['ok'], result)
        log = result['final_memory']['log']
        self.assertEqual(len(log), 2)
        self.assertEqual(log[0]['bars']['SPY'], [2, '2026-09-10T04:00:00Z', 101])
        self.assertEqual(log[0]['quotes']['SPY']['bid'], 100 * .9999)
        self.assertEqual(log[-1]['bars']['SPY'], log[0]['bars']['SPY'])

    def test_daily_availability_follows_new_york_dst(self):
        for opened, closed in [('2026-03-08T05:00:00Z', '2026-03-09T04:00:00Z'),
                               ('2026-11-01T04:00:00Z', '2026-11-02T05:00:00Z')]:
            row = {'t': opened, 'o': 1, 'h': 1, 'l': 1, 'c': 1, 'v': 1}
            self.assertEqual(AlpacaData._bar(row, 86400, daily_equity=True)[1]['t'], closed)

    def test_future_warmup_and_wrong_timeframe_are_rejected(self):
        tape = alpaca_tape([100, 100])
        tape['warmup_bars'] = {'BTC/USD': [{'t': t_at(100), 'c': 900}]}
        self.assertFalse(run_replay(scripted(), {}, tape)['ok'])
        del tape['warmup_bars']
        tape['timeframe'] = '1Day'
        self.assertIn('unsupported input', run_replay(scripted(), {}, tape)['error'])

    def test_cash_waits_for_actual_settlement_and_unknown_stays_locked(self):
        tape = kalshi_tape([[market(.5,.51, close=5)], [], [], [market(.5,.51, ticker='OTHER',close=60)]], {MKT:'yes'})
        tape['settlements'] = {MKT: t_at(15)}
        params = {'plan': {'0': [event('buy', 10)]}}
        result = run_replay(scripted(venue='kalshi'), params, tape, audit=True)
        self.assertTrue(result['ok'], result)
        log = result['final_memory']['log']
        self.assertLess(log[1]['cash'], 200)
        self.assertEqual(log[2]['cash'], log[1]['cash'])
        self.assertAlmostEqual(log[3]['cash'] - log[2]['cash'], 10)
        self.assertEqual(result['trades'], 1)
        tape['settlements'] = {}
        missing = run_replay(scripted(venue='kalshi'), params, tape, audit=True)
        self.assertEqual(missing['unresolved'], 1)
        self.assertEqual(missing['open_positions'], 1)
        self.assertEqual(missing['trades'], 0)
        self.assertEqual(missing['final_memory']['log'][-1]['cash'], log[1]['cash'])

    def test_hours_to_resolve_reaches_strategy_but_result_does_not(self):
        tape = kalshi_tape([[market(.5,.51, hours_to_resolve=7)]], {MKT:'yes'})
        code = 'NEEDS={"venue":"kalshi","horizon":"hour"}\nPARAMS={}\ndef decide(ctx):\n return {"memory":{"row":ctx["markets"][0]}}'
        result = run_replay(code, {}, tape, audit=True)
        self.assertEqual(result['final_memory']['row']['hours_to_resolve'], 7)
        self.assertNotIn('result', result['final_memory']['row'])
