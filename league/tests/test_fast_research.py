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


class CacheLayout(unittest.TestCase):
    """Sept 22, 2026: 15,044 Luna calls wrote 368M tokens to OpenAI's prompt cache and read none,
    because every turn rewrote the end of the single packet message. These pin the fix."""

    def state(self, agent='a1', standing='{"cash": 1}'):
        from league.researcher import STATE_MARKER
        return f'You are {agent}.\nYour current strategy file:\n```python\nNEEDS={{}}\n```\n' + STATE_MARKER + f'Your standing: {standing}'

    def conversation(self, agent='a1', standing='{"cash": 1}', turns=1):
        items = [{'role': 'system', 'content': 'THE GAME ' * 50}, {'role': 'user', 'content': self.state(agent, standing)}]
        for n in range(turns):
            items += [{'type': 'function_call', 'call_id': f'c{n}', 'name': 'markets_now', 'arguments': '{}'},
                      {'type': 'function_call_output', 'call_id': f'c{n}', 'output': json.dumps({'turn': n})}]
        return items

    def test_consecutive_turns_share_a_byte_identical_prefix(self):
        from league.fast_research import build_messages
        for explicit in (False, True):
            first = build_messages(self.conversation(turns=1), TOOLS, explicit=explicit)
            second = build_messages(self.conversation(turns=2), TOOLS, explicit=explicit)
            self.assertEqual([m['role'] for m in second], ['developer', 'user', 'assistant', 'user', 'assistant', 'user'])
            # Every message but the newest is byte-identical; the newest differs only by its breakpoint mark.
            self.assertEqual(json.dumps(first[:-1]), json.dumps(second[:len(first) - 1]))
            text = lambda m: m['content'] if isinstance(m['content'], str) else ''.join(b['text'] for b in m['content'])
            self.assertEqual(text(first[-1]), text(second[len(first) - 1]))

    def test_every_agent_shares_the_protocol_tools_and_rules_and_volatile_state_comes_last(self):
        from league.fast_research import build_messages
        a = build_messages(self.conversation('a1', '{"cash": 1}'), TOOLS, explicit=True)
        b = build_messages(self.conversation('b2', '{"cash": 9}'), TOOLS, explicit=True)
        self.assertEqual(json.dumps(a[0]), json.dumps(b[0]))
        self.assertIn('THE GAME', a[0]['content'][0]['text'])
        self.assertIn('"name":"replay"', a[0]['content'][0]['text'])
        # Two passes of one agent: the static block (strategy file) matches, the standing does not.
        again = build_messages(self.conversation('a1', '{"cash": 7}'), TOOLS, explicit=True)
        self.assertEqual(a[1]['content'][0], again[1]['content'][0])
        self.assertNotEqual(a[1]['content'][1], again[1]['content'][1])
        self.assertNotIn('standing', a[1]['content'][0]['text'])
        marks = sum(1 for m in a for blk in (m['content'] if isinstance(m['content'], list) else [])
                    if blk.get('prompt_cache_breakpoint'))
        self.assertLessEqual(marks, 4)

    def test_the_researcher_puts_the_strategy_before_the_standing(self):
        from league.researcher import STATE_MARKER
        agent = SimpleNamespace(id='a1', family='f', niche='n', generation=1, code='NEEDS = {}', params={'b': 1, 'a': 2})
        make = lambda standing: Researcher._state(SimpleNamespace(journal=lambda _: [], specialty=None), agent, standing)
        one, two = make({'cash': 1, 'at': '2026-09-22T01:00'}), make({'cash': 2, 'at': '2026-09-22T02:00'})
        self.assertEqual(one.split(STATE_MARKER)[0], two.split(STATE_MARKER)[0])
        self.assertLess(one.index('NEEDS = {}'), one.index('Your standing'))
        self.assertIn('{"a": 2, "b": 1}', one)


class ConverseFrontier(FakeFrontier):
    def __init__(self, usage):
        super().__init__([{'name': 'finish', 'arguments': {'summary': 'measured answer'}}] * 3)
        self.usage = usage

    def converse(self, messages, **kwargs):
        self.calls.append({'messages': messages, **kwargs})
        reply = self.replies.pop(0)
        return Answer(json.dumps(reply), Decimal('.0012'), dict(self.usage), MODEL)


class CacheMetering(FastProvider):
    usage = {'input_tokens': 20000, 'output_tokens': 50,
             'input_tokens_details': {'cached_tokens': 15000, 'cache_write_tokens': 4000}}

    def test_cached_and_written_tokens_and_the_billed_cost_reach_the_ledger(self):
        self.frontier = ConverseFrontier(self.usage)
        fast = FastResearch(self.root/'fast.sqlite', self.frontier, self.ledger, balance=lambda _: Decimal('1'),
                            cache={'layout': 'messages', 'explicit_hints': True, 'key': 'ltcm-research-v2'})
        self.call(fast)
        sent = self.frontier.calls[0]
        self.assertEqual(sent['cache'], {'prompt_cache_key': 'ltcm-research-v2', 'prompt_cache_options': {'mode': 'explicit', 'ttl': '30m'}})
        row = [e for e in self.ledger.read(kinds='provider.request')][-1].payload
        self.assertEqual(row['cost_usd'], '0.0012')
        self.assertEqual(row['cache'], {'input_tokens': 20000, 'cached_tokens': 15000, 'cache_write_tokens': 4000,
                                        'hit_rate': 0.75, 'layout': 'messages-explicit', 'key': 'ltcm-research-v2'})
        self.assertEqual(row['protocol'], 'inline_json_tool_v2')

    def test_a_turn_bought_under_the_old_layout_is_rebuilt_under_it_after_the_default_changes(self):
        self.call(key='s:0')  # the v1 packet layout, as production bought it
        self.assertEqual(self.fast.record('s:0')['layout'], 'packet')
        switched = FastResearch(self.root/'fast.sqlite', ConverseFrontier(self.usage), self.ledger, balance=lambda _: Decimal('1'),
                                cache={'layout': 'messages', 'explicit_hints': True})
        again = self.call(switched, key='s:0')  # same bytes, stored answer, no identity error and no new call
        self.assertEqual(again.function_calls[0].name, 'finish')
        self.assertEqual(switched.frontier.calls, [])

    def test_an_unknown_layout_or_unsafe_key_is_refused_at_construction(self):
        for cache in ({'layout': 'mystery'}, {'layout': 'messages', 'key': 'has spaces'}):
            with self.assertRaises(ValueError):
                FastResearch(self.root/'x.sqlite', self.frontier, self.ledger, balance=lambda _: Decimal('1'), cache=cache)
