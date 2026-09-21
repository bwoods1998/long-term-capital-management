"""Provider replacement must preserve tool receipts, budgets and request identity."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import threading
import unittest
from types import SimpleNamespace

from league.fast_research import FastResearch, MODEL, PROFILE, ResearchRouter
from league.commons import Commons
from league.frontier import Answer
from league.ledger import Ledger
from league.research_jobs import ResearchJobs
from league.researcher import Researcher, TOOLS
from league.tests.test_researcher import ResearchCase, Script
from ltcm.provider import ProviderError


class FakeFrontier:
    model = MODEL

    def __init__(self, replies=None):
        self.replies = list(replies or [{'name': 'finish', 'arguments': {'summary': 'measured answer'}}])
        self.calls = []

    def ask(self, **kwargs):
        self.calls.append(kwargs)
        reply = self.replies.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return Answer(json.dumps(reply), Decimal('.002'), {'input_tokens': 1000, 'output_tokens': 200}, MODEL)


class FastProvider(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger = Ledger(self.root/'ledger.sqlite')
        self.frontier = FakeFrontier()
        self.fast = self.make()

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def make(self, balance='1'):
        return FastResearch(self.root/'fast.sqlite', self.frontier, self.ledger, balance=lambda _: Decimal(balance))

    def call(self, fast=None, items=None, key='session:0'):
        return (fast or self.fast).respond(PROFILE, items or [{'role':'user','content':'test'}],
            tools=TOOLS, desk_id='agent', session_id='session', request_key=key)

    def test_paid_response_survives_reopen_without_another_call(self):
        a = self.call()
        b = self.call(self.make())
        self.assertEqual(len(self.frontier.calls), 1)
        self.assertEqual(a, b)
        self.assertEqual(a.function_calls[0].name, 'finish')
        self.assertEqual((self.root/'fast.sqlite').stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.ledger.count(kinds='provider.request'), 1)

    def test_changed_body_cannot_reuse_an_old_request(self):
        self.call()
        with self.assertRaisesRegex(ProviderError, 'identity_changed'):
            self.call(items=[{'role':'user','content':'changed'}])
        self.assertEqual(len(self.frontier.calls), 1)

    def test_unknown_network_outcome_is_not_rebought_after_restart(self):
        self.frontier.replies = [TimeoutError()]
        with self.assertRaisesRegex(ProviderError, 'unconfirmed'):
            self.call()
        with self.assertRaisesRegex(ProviderError, 'unconfirmed'):
            self.call(self.make())
        self.assertEqual(len(self.frontier.calls), 1)
        row = self.ledger.last('provider.request').payload
        self.assertIsNone(row['cost_usd'])
        self.assertGreater(Decimal(row['held_usd']), 0)

    def test_insufficient_credit_refuses_before_the_paid_call(self):
        with self.assertRaisesRegex(ProviderError, 'credit_reservation'):
            self.call(self.make(balance='.00001'))
        self.assertEqual(self.frontier.calls, [])
        self.assertIsNone(self.fast.record('session:0'))

    def test_concurrent_callers_cannot_pay_twice(self):
        entered, release = threading.Event(), threading.Event()
        original = self.frontier.ask
        def slow(**kwargs):
            entered.set()
            self.assertTrue(release.wait(5))
            return original(**kwargs)
        self.frontier.ask = slow
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(self.call)
            self.assertTrue(entered.wait(5))
            try:
                with self.assertRaisesRegex(ProviderError, 'in_progress'):
                    self.call(self.make())
            finally:
                release.set()
            self.assertEqual(first.result().function_calls[0].name, 'finish')
        self.assertEqual(len(self.frontier.calls), 1)

    def test_invalid_envelopes_never_become_tools(self):
        for text in ['not JSON', json.dumps({'name':'shell','arguments':{'cmd':'run'}}),
                     json.dumps({'name':'replay','arguments':{'code':3,'purpose':'x'}}),
                     json.dumps({'name':'finish','arguments':{}}),
                     json.dumps({'name':'finish','arguments':{'summary':'x'},'extra':1})]:
            with self.subTest(text=text):
                answer = {'text': text, 'cost_usd': '.01', 'model': MODEL,
                          'usage': {'input_tokens': 100, 'output_tokens': 20}, 'status':'completed'}
                response = FastResearch.response('test', answer, TOOLS)
                self.assertEqual(response.function_calls, [])
                self.assertEqual(response.cost_usd, Decimal('.01'))

    def test_incomplete_response_never_executes_even_valid_json(self):
        answer = {'text':json.dumps({'name':'finish','arguments':{'summary':'x'}}), 'cost_usd':'.01',
                  'model':MODEL, 'usage':{'input_tokens':100,'output_tokens':20}, 'status':'incomplete'}
        self.assertEqual(FastResearch.response('test', answer, TOOLS).function_calls, [])
        for field, value in [('model','unpriced'), ('usage',{}), ('cost_usd','NaN'), ('cost_verified',False)]:
            with self.subTest(field=field), self.assertRaisesRegex(ProviderError, 'accounting_unverified'):
                FastResearch.response('test', {**answer, field:value}, TOOLS)

    def test_invalid_route_cannot_silently_select_a_population(self):
        for route in [{'enabled':'false'}, {'enabled':True,'fraction':float('nan'),'cohort':'x'},
                      {'enabled':True,'fraction':2,'cohort':'x'}, {'enabled':True,'fraction':.5,'cohort':''}]:
            with self.subTest(route=route), self.assertRaises(ValueError):
                ResearchRouter(None, None, route)


class FastResearchLoop(ResearchCase):
    def test_whole_tool_loop_receives_feedback_and_charges_once_on_resume(self):
        jobs = ResearchJobs(Path(self.dir.name)/'jobs.sqlite', clock=self.clock)
        self.addCleanup(jobs.close)
        job = jobs.enqueue(self.parent.id, ['test'])
        jobs.start(job['session'], {})
        frontier = FakeFrontier([
            {'name':'journal_write','arguments':{'text':'This measured result is retained for the next experiment.'}},
            {'name':'finish','arguments':{'summary':'The experiment has a retained result.'}},
        ])
        fast = FastResearch(Path(self.dir.name)/'fast.sqlite', frontier, self.ledger,
                            balance=self.economy.balance, clock=self.clock)
        sail = Script([])
        sail.record = lambda key: None
        router = ResearchRouter(sail, fast, {'enabled':True,'fraction':1,'cohort':'test'})
        researcher = Researcher(ledger=self.ledger, provider=router, commons=Commons(self.ledger), economy=self.economy,
            rules='rules', contract='contract', run_replay=lambda *a: {}, settings={'profile':'pro_flex'}, jobs=jobs,
            clock=self.clock)
        before = self.economy.balance(self.parent.id)
        result = researcher.research(self.parent, {}, session=job['session'])
        self.assertEqual(result.reason, 'finished')
        self.assertEqual(result.cost_usd, Decimal('.004'))
        packet = json.loads(frontier.calls[1]['user'])
        receipts = [i for i in packet['conversation'] if i.get('type') == 'function_call_output']
        self.assertTrue(json.loads(receipts[0]['output'])['saved'])
        router.routes['enabled'] = False
        resumed = researcher.research(self.parent, {}, session=job['session'])
        self.assertEqual(resumed, result)
        self.assertEqual(len(frontier.calls), 2)
        self.assertEqual(before-self.economy.balance(self.parent.id), Decimal('.004'))
        self.assertEqual(jobs.get(job['session'])['checkpoint']['profile'], PROFILE)

    def test_disabled_router_preserves_the_existing_sail_route(self):
        sail = Script([])
        router = ResearchRouter(sail, None, {'enabled':False})
        settings = {'profile':'pro_flex','max_output_tokens':32000}
        self.assertEqual(router.settings_for(self.parent, settings), settings)
        response = router.respond('pro_flex', [], desk_id='x')
        self.assertEqual(response.function_calls[0].name, 'finish')
