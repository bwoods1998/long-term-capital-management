"""Startup assistance cannot become free money through births, concurrency or restarts."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from league.frontier import Answer, FrontierError
from league.grants import GrantGuard, MAX_GRANTS, MODEL, ResearchGrants
from league.campaigns import CampaignClosed
from league.researcher import Pass
from league.tests.test_researcher import CODE, ResearchCase
import json


PROPOSAL = {
    'question': 'Does the observed spread leave enough room after round-trip fees?',
    'hypothesis': 'Abstaining at wide spreads reduces fee-driven losses on this tape.',
    'acceptance_check': 'Compare after-fee return to the baseline on the identical frozen tape.',
}


class Grants(ResearchCase):
    def setUp(self):
        super().setUp()
        self.calls = []
        self.frontier = SimpleNamespace(model=MODEL, ask=self.ask)
        self.grants = ResearchGrants(self.ledger.path.parent / 'grants.sqlite', self.frontier,
                                    self.ledger, phase='phase-one', clock=self.clock)

    def ask(self, **kw):
        self.calls.append(kw)
        return Answer(json.dumps({'answer': 'Compare the proposed program on the stated frozen evidence.',
                                  'code': CODE, 'confidence': 'low'}), Decimal('.08'), {}, MODEL)

    def request(self, agent=None, session='one', **kw):
        return self.grants.request(agent or self.parent, kw.get('proposal', PROPOSAL),
            kw.get('evidence', {'record': {'rung': 0, 'active_blocks': 0}}), session=session, contract='contract')

    def test_family_grant_survives_restart_and_children_do_not_renew_it(self):
        before = self.economy.balance(self.parent.id)
        first = self.request()
        self.assertTrue(first['house_funded'])
        self.assertEqual(self.request(), first)  # same completed session reuses its artifact
        self.grants = ResearchGrants(self.grants.path, self.frontier, self.ledger, phase='phase-one', clock=self.clock)
        self.assertIn('already used', self.request(agent=self.child, session='child')['error'])
        self.assertIn('already used', self.request(session='new')['error'])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.economy.balance(self.parent.id), before)
        self.assertEqual(self.ledger.count(kinds='eval.trial'), 0)
        self.assertEqual(self.ledger.count(kinds='eval.verdict'), 0)

    def test_interrupted_claim_never_buys_another_call(self):
        self.frontier.ask = lambda **kw: (_ for _ in ()).throw(RuntimeError('process interruption'))
        with self.assertRaises(RuntimeError):
            self.request()
        self.frontier.ask = self.ask
        self.assertIn('already used', self.request()['error'])
        self.assertEqual(self.calls, [])

    def test_ambiguous_provider_failure_is_not_retried(self):
        self.frontier.ask = lambda **kw: (_ for _ in ()).throw(FrontierError('provider timeout'))
        result = self.request()
        self.assertIsNone(result['cost_usd'])
        self.frontier.ask = self.ask
        self.assertEqual(self.request(), result)
        self.assertEqual(self.calls, [])

    def test_concurrent_families_cannot_exceed_the_phase_allocation(self):
        def request(i):
            agent = SimpleNamespace(id=f'test-{i}', family=f'family-{i}', niche=self.parent.niche)
            return self.request(agent=agent, session=str(i))
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(request, range(30)))
        self.assertEqual(sum('error' not in r for r in results), MAX_GRANTS)
        self.assertEqual(len(self.calls), MAX_GRANTS)

    def test_record_or_missing_experiment_prevents_spend(self):
        for record in ({'rung': 2}, {'rung': 1, 'active_blocks': 1}):
            self.assertIn('error', self.request(evidence={'record': record}))
        self.assertIn('error', self.request(proposal={'question': 'help'}))
        self.assertEqual(self.calls, [])

    def test_per_call_ceiling_binds_before_the_campaign_reservation(self):
        calls = []
        guard = GrantGuard(SimpleNamespace(reserve=lambda *a: calls.append(a)))
        with self.assertRaises(CampaignClosed):
            guard.reserve('too-large', 'foundation-review', '.750001')
        self.assertEqual(calls, [])

    def test_research_requires_preflight_and_preserves_long_specialist_code(self):
        r = self.researcher([], grants=self.grants, rung=lambda _: 0)
        out = Pass(self.parent.id)
        self.assertIn('inspect replay_coverage', r._execute(self.parent, 'research_grant', PROPOSAL, out, 'one')['error'])
        long_code = CODE + '\n# ' + 'bounded strategy explanation ' * 600
        self.frontier.ask = lambda **kw: Answer(json.dumps({'answer': 'Test the proposed spread filter against the baseline.',
            'code': long_code}), Decimal('.08'), {}, MODEL)
        r = self.researcher([[('replay_coverage', {})], [('research_grant', PROPOSAL)]],
            grants=self.grants, rung=lambda _: 0, coverage=lambda a: {'ready': True})
        result = r.research(self.parent, {}, session='one')
        self.assertEqual(self.tool_output(2, 1)['code'], long_code)
        self.assertEqual(result.consulted, long_code)
        self.assertEqual(result.cost_usd, Decimal('.03'))  # own model turns only
