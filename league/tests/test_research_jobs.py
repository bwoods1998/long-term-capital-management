"""Crash recovery must retain paid work without repeating requests, tools or adoption."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

from league.researcher import Pass, pass_state
from league.research_jobs import ResearchJobs, ResearchPending
from league.tests.test_researcher import ResearchCase, CODE, Script
from league.tests.test_house import HouseCase, BUYER
from ltcm.provider import Provider
from ltcm.tests.test_provider import FakeTransport, call, response


def process_probe(root, first):
    """Run in a disposable process, with fake network responses and a real WAL database."""
    from league.agents import Registry
    from league.commons import Commons
    from league.economy import Economy
    from league.ledger import Ledger
    from league.researcher import Researcher
    root = Path(root)
    ledger = Ledger(root / 'ledger.sqlite')
    registry = Registry(ledger)
    agent = registry.get('probe') or registry.born(name='probe', family='test', code=CODE,
                                                 needs={'venue': 'kalshi', 'horizon': 'day'})
    economy = Economy(ledger)
    economy.grant(agent.id, '5', 'test', id='probe-endowment')
    jobs = ResearchJobs(root / 'research.sqlite')
    job = jobs.enqueue(agent.id, [agent.code_sha256], session='process-probe')
    jobs.start(job['session'], {'agent': asdict(agent), 'standing': {}})
    replies = FakeTransport(*([
        response(rid='resp_note', output=[call('library_write', '{"title":"probe","text":"a durable, measured finding with enough evidence to retain"}')]),
        response(rid='resp_paid', status='queued', usage=None),
    ] if first else [response(rid='resp_paid', output=[call('finish', '{"summary":"recovered"}')])]))
    def transport(method, route, body=None, idempotency_key=None):
        with (root / 'network.jsonl').open('a') as log:
            log.write(json.dumps({'method': method, 'route': route}) + '\n')
        return replies(method, route, body, idempotency_key)
    provider = Provider(root / 'provider.sqlite', transport=transport, sleep=lambda _: os._exit(73))
    researcher = Researcher(ledger=ledger, provider=provider, commons=Commons(ledger), economy=economy,
        rules='test rules', contract='test contract', run_replay=lambda *a: {},
        settings={'profile': 'pro_flex', 'max_turns': 6}, jobs=jobs)
    with jobs.claim(job['session']) as claimed:
        if not claimed:
            raise AssertionError('the dead process still owns the session')
        out = researcher.research(agent, {}, session=job['session'])
    print(json.dumps({'summary': out.summary, 'cost': str(out.cost_usd),
                      'balance': str(economy.balance(agent.id)), 'notes': ledger.count(kinds='library.note')}))
    provider.close()
    jobs.close()
    ledger.close()


class QueueTests(unittest.TestCase):
    def test_actual_process_exit_recovers_paid_response_and_releases_execution_lock(self):
        with tempfile.TemporaryDirectory() as root:
            worker = 'from league.tests.test_research_jobs import process_probe; import sys; process_probe(sys.argv[1], sys.argv[2]=="first")'
            first = subprocess.run([sys.executable, '-c', worker, root, 'first'], capture_output=True, text=True)
            self.assertEqual(first.returncode, 73, first.stderr)
            second = subprocess.run([sys.executable, '-c', worker, root, 'resume'], capture_output=True, text=True)
            self.assertEqual(second.returncode, 0, second.stderr)
            out = json.loads(second.stdout)
            self.assertEqual(out['summary'], 'recovered')
            self.assertEqual(out['notes'], 1)
            self.assertEqual(Decimal(out['cost']), Decimal('.002134'))
            self.assertEqual(Decimal(out['balance']), Decimal('5') - Decimal(out['cost']))
            calls = [json.loads(line) for line in (Path(root) / 'network.jsonl').read_text().splitlines()]
            self.assertEqual([c['method'] for c in calls], ['POST', 'POST', 'GET'])
            self.assertEqual(calls[-1]['route'], '/v1/responses/resp_paid')

    def test_concurrent_enqueue_and_os_execution_lock_survive_reopen(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'research.sqlite'
            jobs = ResearchJobs(path)
            with ThreadPoolExecutor(max_workers=8) as pool:
                rows = list(pool.map(lambda _: jobs.enqueue('agent', ['generation']), range(20)))
            session = rows[0]['session']
            self.assertEqual({r['session'] for r in rows}, {session})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            worker = "from league.research_jobs import ResearchJobs; import sys; j=ResearchJobs(sys.argv[1]);\nwith j.claim(sys.argv[2]) as claimed: print(claimed)\nj.close()"
            with jobs.claim(session) as claimed:
                self.assertTrue(claimed)
                done = subprocess.run([sys.executable, '-c', worker, str(path), session], capture_output=True, text=True, check=True)
                self.assertEqual(done.stdout.strip(), 'False')
            jobs.close()
            jobs = ResearchJobs(path)
            try:
                self.assertEqual(jobs.active('agent')['session'], session)
                with jobs.claim(session) as claimed:
                    self.assertTrue(claimed)
                jobs.finish(session)
                self.assertNotEqual(jobs.enqueue('agent', ['generation'])['session'], session)
            finally:
                jobs.close()


class SavedResearch(ResearchCase):
    def setUp(self):
        super().setUp()
        self.path = Path(self.dir.name) / 'research.sqlite'
        self.jobs = ResearchJobs(self.path, clock=self.clock)
        self.providers = []
        self.session = 'durable-research'
        self.jobs.enqueue(self.parent.id, [self.parent.code_sha256], session=self.session)
        self.jobs.start(self.session, {'agent': asdict(self.parent), 'standing': {}})

    def tearDown(self):
        for provider in self.providers:
            provider.close()
        self.jobs.close()
        super().tearDown()

    def fresh(self, turns=(), **kwargs):
        r = self.researcher(turns, **kwargs)
        r.jobs = self.jobs
        return r

    def reopen(self):
        self.jobs.close()
        self.jobs = ResearchJobs(self.path, clock=self.clock)

    def provider(self, transport, **kwargs):
        provider = Provider(Path(self.dir.name) / 'provider.sqlite', transport=transport,
                            clock=self.clock, floor_cap_usd_per_day='5', **kwargs)
        self.providers.append(provider)
        return provider

    def run_pass(self, researcher):
        return researcher.research(self.parent, {}, session=self.session)

    def test_restart_polls_the_accepted_response_with_the_saved_transcript(self):
        transport = FakeTransport(
            response(rid='resp_first', output=[call('library_search', '{"query":"maker"}')]),
            response(rid='resp_second', status='queued', usage=None),
        )
        def die(_):
            raise SystemExit('process exit after acceptance')
        first = self.fresh()
        first.provider = self.provider(transport, sleep=die)
        with self.assertRaises(SystemExit):
            self.run_pass(first)
        saved = self.jobs.get(self.session)['checkpoint']
        self.assertEqual(saved['turn'], 1)
        self.assertEqual(saved['stage'], 'model')
        self.assertEqual(len([x for x in saved['conversation'] if x.get('type') == 'function_call_output']), 1)
        second_body = first.provider.record(self.session + ':1')['body']
        self.reopen()
        resumed_transport = FakeTransport(response(rid='resp_second', output=[call('finish', '{"summary":"retained the evidence"}')]))
        second = self.fresh(settings={'profile': 'flash_asap', 'max_turns': 1})
        second.provider = self.provider(resumed_transport)
        out = self.run_pass(second)
        self.assertEqual(out.reason, 'finished')
        self.assertEqual(out.turns, 2)
        self.assertEqual(resumed_transport.posts, [])
        self.assertEqual([x['route'] for x in resumed_transport.calls], ['/v1/responses/resp_second'])
        self.assertEqual(second.provider.record(self.session + ':1')['body'], second_body)
        self.assertEqual(out.cost_usd, Decimal('0.002134'))
        self.assertEqual(self.economy.balance(self.parent.id), Decimal('5') - out.cost_usd)
        tools = [e.payload['tool'] for e in self.ledger.iter(kinds='agent.research', agent=self.parent.id)]
        self.assertEqual(tools.count('library_search'), 1)
        self.assertEqual(self.run_pass(second), out)  # completion itself is idempotent
        self.assertEqual(self.ledger.count(kinds='agent.research', agent=self.parent.id), len(tools))

    def test_timeout_yields_the_same_request_and_never_buys_a_replacement(self):
        transport = FakeTransport(response(rid='resp_waiting', status='queued', usage=None))
        r = self.fresh(settings={'profile': 'pro_flex', 'fast_profile': 'pro_asap'})
        r.provider = self.provider(transport, poll_timeout=0)
        with self.assertRaisesRegex(ResearchPending, 'provider_poll_timeout'):
            self.run_pass(r)
        transport.script.append(response(rid='resp_waiting', output=[call('finish', '{"summary":"done"}')]))
        self.assertEqual(self.run_pass(r).reason, 'finished')
        self.assertEqual(len(transport.posts), 1)
        self.assertEqual(len(r.provider.records()), 1)
        self.assertEqual(r.provider.records()[0]['profile'], 'pro_flex')

    def test_crash_after_charging_before_checkpoint_never_double_charges(self):
        r = self.fresh([[('finish', {'summary': 'done'})]])
        charge = self.economy.charge
        def charged_then_exit(*args, **kwargs):
            charge(*args, **kwargs)
            raise SystemExit('charged but not checkpointed')
        self.economy.charge = charged_then_exit
        with self.assertRaises(SystemExit):
            self.run_pass(r)
        self.economy.charge = charge
        self.reopen()
        resumed = self.fresh()
        out = self.run_pass(resumed)
        self.assertEqual(resumed.provider.seen, [])
        self.assertEqual(out.cost_usd, Decimal('.01'))
        self.assertEqual(self.economy.balance(self.parent.id), Decimal('4.99'))
        self.assertEqual(self.ledger.count(kinds='credit.charge', agent=self.parent.id), 1)

    def test_saved_tool_receipt_continues_remaining_calls_without_repeating_a_write(self):
        r = self.fresh([[
            ('library_write', {'title': 'evidence', 'text': 'Measured spread and fees on a recorded tape.'}),
            ('replay', {'code': CODE, 'purpose': 'one measured experiment'}),
            ('finish', {'summary': 'tested once'}),
        ]])
        save = self.jobs.save
        def saved_then_exit(session, state):
            save(session, state)
            if state['stage'] == 'tools' and state['call_index'] == 1:
                raise SystemExit('receipt committed')
        self.jobs.save = saved_then_exit
        with self.assertRaises(SystemExit):
            self.run_pass(r)
        self.reopen()
        resumed = self.fresh()
        out = self.run_pass(resumed)
        self.assertEqual(out.reason, 'finished')
        self.assertEqual(resumed.provider.seen, [])
        self.assertEqual(self.ledger.count(kinds='library.note'), 1)
        self.assertEqual(self.replays, [CODE])
        self.assertEqual(out.trials, 1)

    def test_unconfirmed_replay_is_not_repeated_and_retained_code_is_recovered(self):
        r = self.fresh([[('replay', {'code': CODE, 'purpose': 'paid experiment'})]])
        save = self.jobs.save
        def die_before_receipt(session, state):
            if state['stage'] == 'tools' and state['call_index'] == 1:
                raise SystemExit('result existed, receipt not saved')
            save(session, state)
        self.jobs.save = die_before_receipt
        with self.assertRaises(SystemExit):
            self.run_pass(r)
        self.reopen()
        resumed = self.fresh()
        out = self.run_pass(resumed)
        self.assertEqual(out.reason, 'tool outcome unconfirmed: replay')
        self.assertEqual(out.candidate['code'], CODE)
        self.assertEqual(self.replays, [CODE])
        self.assertEqual(resumed.provider.seen, [])
        self.assertEqual(self.economy.balance(self.parent.id), Decimal('4.99'))

    def test_interrupted_free_read_is_refreshed_without_rebuying_the_model(self):
        r = self.fresh([[('runtime_status', {}), ('finish', {'summary': 'read recovered'})]],
                       capabilities=lambda agent: {'revision': 'old'})
        save = self.jobs.save
        def die_before_receipt(session, state):
            if state['stage'] == 'tools' and state['call_index'] == 1:
                raise SystemExit('read happened, receipt not saved')
            save(session, state)
        self.jobs.save = die_before_receipt
        with self.assertRaises(SystemExit):
            self.run_pass(r)
        self.reopen()
        resumed = self.fresh(capabilities=lambda agent: {'revision': 'new'})
        out = self.run_pass(resumed)
        self.assertEqual(out.reason, 'finished')
        self.assertEqual(resumed.provider.seen, [])
        self.assertEqual(self.economy.balance(self.parent.id), Decimal('4.99'))
        saved = self.jobs.get(self.session)['checkpoint']
        receipts = [i for i in saved['conversation'] if i.get('type') == 'function_call_output']
        self.assertIn('new', receipts[0]['output'])
        recoveries = [e for e in self.ledger.iter(kinds='agent.research') if e.payload.get('tool') == 'refreshed_read']
        self.assertEqual(len(recoveries), 1)

    def test_shutdown_after_a_response_saves_it_before_running_any_tool(self):
        stopped = [False]
        r = self.fresh([[('journal_write', {'text': 'An expensive finding that must be preserved.'}), ('finish', {'summary': 'done'})]],
                       may_continue=lambda agent: 'shutdown' if stopped[0] else '')
        respond = r.provider.respond
        def answered(*args, **kwargs):
            result = respond(*args, **kwargs)
            stopped[0] = True
            return result
        r.provider.respond = answered
        with self.assertRaises(ResearchPending):
            self.run_pass(r)
        self.assertEqual(list(self.ledger.iter(kinds='agent.research')), [])
        self.reopen()
        resumed = self.fresh()
        self.assertEqual(self.run_pass(resumed).reason, 'finished')
        self.assertEqual(resumed.provider.seen, [])
        self.assertEqual(len([e for e in self.ledger.iter(kinds='agent.research') if e.payload.get('tool') == 'journal']), 1)

    def test_a_retired_agent_does_not_execute_a_late_model_tool(self):
        retired = [False]
        r = self.fresh([[('replay', {'code': CODE, 'purpose': 'too late'})]],
                       may_continue=lambda agent: 'retired or changed' if retired[0] else '')
        respond = r.provider.respond
        def answered(*args, **kwargs):
            result = respond(*args, **kwargs)
            retired[0] = True
            return result
        r.provider.respond = answered
        self.assertEqual(self.run_pass(r).reason, 'retired or changed')
        self.assertEqual(self.replays, [])

    def test_six_hour_old_session_does_not_keep_buying_work(self):
        r = self.fresh(may_continue=lambda agent: 'deployment')
        with self.assertRaises(ResearchPending):
            self.run_pass(r)
        self.clock.advance(21601)
        r.may_continue = None
        self.assertEqual(self.run_pass(r).reason, 'session expired after six hours')
        self.assertEqual(r.provider.seen, [])

    def test_runtime_status_reports_current_support_without_erasing_historical_notes(self):
        r = self.fresh([[('runtime_status', {}), ('finish', {'summary': 'warmup now available'})]],
                       capabilities=lambda agent: {'revision': 'new', 'warmup': 'implemented'})
        out = self.run_pass(r)
        state = self.jobs.get(self.session)['checkpoint']
        outputs = [json.loads(x['output']) for x in state['conversation'] if x.get('type') == 'function_call_output']
        self.assertEqual(outputs[0], {'revision': 'new', 'warmup': 'implemented'})
        self.assertEqual(out.reason, 'finished')

    def test_smoke_checks_and_unavailable_inputs_do_not_inflate_trial_counts(self):
        r = self.fresh([[('replay', {'code': CODE, 'purpose': 'smoke'})],
                        [('replay', {'code': CODE, 'purpose': 'missing input'})]])
        outcomes = iter([{'passed': True, 'counted_as_trial': False, 'numbers': {'note': 'smoke only'}},
                         {'passed': False, 'counted_as_trial': False, 'error': 'unsupported input'}])
        r.run_replay = lambda *args: next(outcomes)
        out = self.run_pass(r)
        self.assertEqual(out.trials, 0)
        self.assertEqual(out.calls.count('replay'), 2)
        self.assertTrue(out.candidate['passed'])


class HouseRecovery(HouseCase):
    def enabled(self, provider=None):
        self.house.close()
        self.house = self.new_house(provider=provider or Script([]))
        self.house.settings.research = True
        self.house.pacer = SimpleNamespace(may_spend=lambda kind: True, no_catch_up=True)

    def test_queued_identity_and_completed_cooldown_survive_house_restart(self):
        agent = self.seated()
        job = self.house.research_jobs.enqueue(agent.id, self.house._generation(agent.id))
        self.enabled()
        agent = self.house.registry.get(agent.id)
        self.assertTrue(self.house.research_due(agent))
        self.house._research_if_due(agent)
        self.assertEqual(self.house.research_jobs.get(job['session'])['status'], 'done')
        self.assertIn('runtime_capabilities', self.house.research_jobs.get(job['session'])['snapshot']['standing'])
        # Simulate losing house.json after a completed job: its durable completion still paces.
        self.house._state['last_research'].clear()
        self.enabled()
        self.assertFalse(self.house.research_due(self.house.registry.get(agent.id)))

    def test_retired_queued_work_is_cancelled_without_buying_a_response(self):
        agent = self.seated()
        job = self.house.research_jobs.enqueue(agent.id, self.house._generation(agent.id))
        self.house.registry.died(agent.id, 'displaced')
        self.enabled()
        self.house._cancel_retired_research()
        self.assertEqual(self.house.research_jobs.get(job['session'])['status'], 'cancelled')
        self.assertEqual(self.house.provider.seen, [])

    def test_changed_strategy_cannot_resume_the_old_conversation(self):
        agent = self.seated()
        job = self.house.research_jobs.enqueue(agent.id, self.house._generation(agent.id))
        self.house.registry.adopt(agent.id, code=BUYER+'\n# changed\n', needs=agent.needs, params=agent.params, reason='changed')
        self.enabled()
        self.house.research(self.house.registry.get(agent.id))
        self.assertEqual(self.house.research_jobs.get(job['session'])['status'], 'cancelled')
        self.assertEqual(self.house.provider.seen, [])

    def test_ready_candidate_can_be_adopted_without_buying_another_research_pass(self):
        agent = self.seated()
        job = self.house.research_jobs.enqueue(agent.id, self.house._generation(agent.id))
        self.house.research_jobs.start(job['session'], {'agent': asdict(agent), 'standing': {}})
        candidate = {'code': BUYER+'\n# measured change\n', 'needs': agent.needs, 'params': agent.params,
                     'purpose': 'measured change', 'numbers': {}, 'passed': True}
        self.house.research_jobs.ready(job['session'], pass_state(Pass(agent.id, candidate=candidate)))
        self.enabled()
        self.house.research(self.house.registry.get(agent.id))
        self.assertEqual(self.house.registry.get(agent.id).code, candidate['code'])
        self.assertEqual(self.house.provider.seen, [])
        self.assertEqual(self.house.research_jobs.get(job['session'])['status'], 'done')

    def test_uncertain_fork_commit_is_not_repeated_and_keeps_its_candidate(self):
        agent = self.seated()
        job = self.house.research_jobs.enqueue(agent.id, self.house._generation(agent.id))
        self.house.research_jobs.start(job['session'], {'agent': asdict(agent), 'standing': {}})
        candidate = {'code': BUYER+'\n# measured change\n', 'needs': agent.needs, 'params': agent.params,
                     'purpose': 'measured change', 'numbers': {}, 'passed': True}
        self.house.research_jobs.ready(job['session'], pass_state(Pass(agent.id, candidate=candidate)))
        self.house.research_jobs.applying(job['session'])
        self.enabled()
        self.house.fork = lambda *a, **k: self.fail('a possibly completed fork must not be repeated')
        self.house.research(self.house.registry.get(agent.id))
        stored = self.house.research_jobs.get(job['session'])
        self.assertEqual(stored['status'], 'done')
        self.assertEqual(stored['outcome']['candidate'], candidate)
        self.assertEqual(self.house.ledger.last('agent.research').payload['status'], 'commit_unconfirmed')
        self.assertEqual(self.house.provider.seen, [])

    def test_capability_report_distinguishes_configuration_from_measured_coverage(self):
        agent = self.seated()
        report = self.house.research_capabilities(agent)
        self.assertTrue(report['observations']['alpaca_source_configured'])
        self.assertFalse(report['observations']['kalshi_source_configured'])
        self.assertEqual(report['replay']['requested_window_days'], self.house.settings.replay_days)
        self.assertIn('not proof of coverage', report['replay']['coverage'])
        self.assertIn('Implemented', report['replay']['daily_execution_clock'])

    def test_coverage_reports_actual_data_without_a_paid_sandbox_or_trial(self):
        agent = self.seated()
        self.house.sandbox.replay = lambda *a, **k: self.fail('coverage must not execute a replay')
        before = self.house.economy.balance(agent.id)
        report = self.house.research_coverage(agent)
        self.assertFalse(report['counted_as_trial'])
        self.assertEqual(report['market_observation_steps']['first_at'], '2026-09-10T00:00:00Z')
        self.assertEqual(report['market_observation_steps']['rows'], 720)
        self.assertEqual(self.house.ledger.count(kinds='eval.trial'), 0)
        self.assertEqual(self.house.economy.balance(agent.id), before)
        self.house.niche_of = lambda agent: SimpleNamespace(replay=False)
        self.assertEqual(self.house.research_coverage(agent)['mode'], 'smoke_only')

    def test_coverage_does_not_mistake_terminal_settlement_events_for_quotes(self):
        from league.capabilities import tape_coverage
        report = tape_coverage({'steps': [
            {'t': '2026-09-19T10:00:00Z', 'markets': [{'market': 'M'}]},
            {'t': '2026-09-20T10:00:00Z', 'markets': []},
        ], 'settlements': {'M': '2026-09-20T10:00:00Z'}})
        self.assertEqual(report['market_observation_steps']['last_at'], '2026-09-19T10:00:00Z')
        self.assertEqual(report['execution_events']['last_at'], '2026-09-20T10:00:00Z')
        self.assertEqual(report['distinct_markets'], 1)

    def test_daily_coverage_separates_intraday_execution_from_daily_history(self):
        from league.capabilities import tape_coverage
        report = tape_coverage({'steps': [
            {'t': '2026-09-19T13:35:00Z', 'bars': {}, 'execution_bars': {'SPY': {'c': 100}},
             'history_bars': {'SPY': [{'t': '2026-09-19T04:00:00Z', 'c': 99}]}},
            {'t': '2026-09-19T13:40:00Z', 'bars': {}, 'execution_bars': {'SPY': {'c': 101}}},
        ]})
        self.assertEqual(report['market_observation_steps']['rows'], 2)
        self.assertEqual(report['signal_history']['SPY'], {'rows': 1, 'first_at': '2026-09-19T04:00:00Z', 'last_at': '2026-09-19T04:00:00Z'})

    def test_coverage_exposes_market_sampling_and_each_series_actual_dates(self):
        from league.capabilities import tape_coverage
        report = tape_coverage({'series': ['NFL', 'CFB'], 'meta': {'listed': 3006, 'scanned': 500, 'kept': 500}, 'steps': [
            {'t': '2026-08-02T10:00:00Z', 'markets': [{'market': 'OLD', 'series': 'NFL'}]},
            {'t': '2026-09-20T10:00:00Z', 'markets': [{'market': 'NEW', 'series': 'CFB'}]},
        ]})
        self.assertEqual(report['markets_by_series']['NFL']['last_at'], '2026-08-02T10:00:00Z')
        self.assertEqual(report['markets_by_series']['CFB']['first_at'], '2026-09-20T10:00:00Z')
        self.assertEqual(report['listing_sample'], {'listed': 3006, 'scanned': 500, 'kept': 500})
        self.assertEqual(report['requested_series'], ['NFL', 'CFB'])

    def test_architect_and_toolsmith_see_the_deployed_capabilities(self):
        from league.merton import evidence_from
        self.seated()
        for role in ('architect', 'toolsmith', 'operator', 'designer', 'teacher'):
            runtime = evidence_from(self.house)(role)['runtime_capabilities']
            self.assertIn('Implemented', runtime['implemented_replay_support']['alpaca_warmup'])
            self.assertEqual(len(runtime['revision']), 64)

    def test_pending_paid_work_is_not_hidden_by_the_new_session_credit_threshold(self):
        agent = self.seated()
        job = self.house.research_jobs.enqueue(agent.id, self.house._generation(agent.id))
        self.house.economy.charge(agent.id, self.house.economy.balance(agent.id) - Decimal('.15'), 'spent on this pass')
        self.enabled()
        self.assertTrue(self.house.research_due(self.house.registry.get(agent.id)))
        self.assertEqual(self.house.research_jobs.active(agent.id)['session'], job['session'])

    def test_progress_separates_housekeeping_worker_attempts_and_research_conclusions(self):
        from league.campaigns import CampaignBudget
        from league.phase1 import report
        from league.tests.test_phase1 import policy
        budget = CampaignBudget(self.house.root / 'campaigns.sqlite', policy(), clock=self.clock)
        try:
            for key, seconds in [('merton:follow', .006), ('merton:architect', 100), ('research:test', 400), ('niche-survey', 8)]:
                self.house.ledger.append('ops.job', {'job': key, 'key': key, 'state': 'started'})
                self.house.ledger.append('ops.job', {'job': key, 'key': key, 'state': 'finished', 'running_seconds': seconds})
            self.house.ledger.append('agent.research', {'tool': 'summary', 'session': 'complete', 'reason': 'finished', 'cost_usd': '.02', 'candidate': False})
            summary = report(self.house.root, now=self.clock())
            self.assertEqual(summary['latency']['merton']['running_seconds']['p50'], 100)
            self.assertEqual(summary['latency']['housekeeping']['finished'], 1)
            self.assertEqual(summary['latency']['survey']['finished'], 1)
            self.assertEqual(summary['research']['completed_sessions'], 1)
            self.assertEqual(Decimal(summary['research']['reported_cost_usd']), Decimal('.02'))
        finally:
            budget.close()
