"""Conservative 1M billing bounds; synthetic authority and HTTP fixtures only."""
from dataclasses import replace
import json
from pathlib import Path
import unittest
from unittest import mock

from ltcm import provider
from league.swarm.research_controller import explicit_settings
from league.swarm.research_transport import ModelCapability, ModelPolicy, ResearchCapabilityError
from league.tests import test_research_transport as broker_fixtures
from league.tests import test_sail_research_host as sail_fixtures


class InputReservations(unittest.TestCase):
    def test_conservative_1m_input_bound_is_distinct_from_unchanged_output_ceiling(self):
        for limit in (1000000, 1048576):
            policy = ModelPolicy('deepseek-ai/DeepSeek-V4-Flash-0731', '0.09', '0.18', '0', limit, 1000000,
                                 1, 2, 'SYNTHETIC structure only; no actual billing authority')
            self.assertEqual(policy.max_input_tokens, limit)
        for input_limit, output_limit in ((1048577, 8000), (True, 8000), (0, 8000), (1048576.0, 8000),
                                         (1048576, 1000001), (1048576, True), (1048576, 0)):
            with self.subTest(input=input_limit, output=output_limit), self.assertRaises(ResearchCapabilityError):
                ModelPolicy('deepseek-ai/DeepSeek-V4-Flash-0731', '0.09', '0.18', '0', input_limit, output_limit,
                            1, 2, 'SYNTHETIC structure only')

    def test_actual_configured_models_roles_efforts_and_outputs_need_no_substitution(self):
        root = Path(__file__).resolve().parents[2]
        settings = explicit_settings(json.loads((root/'league/config.json').read_text()),
                                     json.loads((root/'league/swarm/policy.json').read_text()),
                                     checkpoint='sbcp_synthetic', roots=('SPY',))
        research, architect = settings['researcher'], settings['architect']
        roles = ((research['profile'], research['reasoning_effort'], research['max_output_tokens']),
                 (research['long_profile'], research['reasoning_effort'], research['max_output_tokens']),
                 (research['rewrite_profile'], 'medium', 12000),
                 (research['top_rewrite_profile'], 'medium', 12000),
                 (architect['sail_profile'], architect['sail_effort'], architect['max_output_tokens']))
        self.assertEqual(roles, (('flash_asap', 'minimal', 8000), ('flash41_asap', 'minimal', 8000),
                                 ('pro_asap', 'medium', 12000), ('k3_balanced', 'medium', 12000),
                                 ('pro_asap', 'high', 32000)))
        profiles_before = dict(provider.PROFILES)
        for profile, effort, output in roles:
            model, window, inp, _, out = provider.PROFILES[profile]
            policy = ModelPolicy(model, inp, out, '0', 1048576, output, 1, 2,
                                 'SYNTHETIC structural policy; published rate is not inclusive authority',
                                 allowed_efforts=(effort,))
            self.assertEqual((policy.model, policy.allowed_efforts, policy.max_output_tokens), (model, (effort,), output))
            self.assertEqual(provider.window_of(profile), window)
        self.assertEqual(provider.PROFILES, profiles_before)

    def test_whole_window_reserves_dollars_for_small_payload_and_keeps_original_cache(self):
        f = broker_fixtures.ResearchTransport('runTest'); f.setUp(); self.addCleanup(f.doCleanups)
        f.reply = replace(f.reply, actual_usd=None, accrued_day=None, provenance=None)
        policy = replace(f.model_policy, model=provider.model_of('flash_asap'), input_usd_million='0.09',
                         output_usd_million='0.18', max_input_tokens=1048576, max_output_tokens=8000,
                         allowed_efforts=('minimal',))
        capability = ModelCapability(policy, lambda body: 1048576, f.send)
        broker = f.make_broker(capability=capability)
        payload = {'profile':'reviewed', 'items':[{'role':'user','content':'short research prompt'}],
                   'key':'whole-window', 'effort':'minimal', 'tools':[broker_fixtures.TOOL]}
        result = f.call('evaluate', payload, broker=broker)
        hold = next(iter(f.budget._load()['inference'].values()))
        self.assertEqual(hold['max_nanos'], 95811840)
        self.assertIsNone(hold['receipt'])
        self.assertIsNone(result['cost_usd'])
        self.assertEqual(f.model_calls[0]['input'], payload['items'])
        self.assertEqual(f.model_calls[0]['tools'], [broker_fixtures.TOOL])
        self.assertEqual(f.call('evaluate', payload, broker=broker), result)
        self.assertEqual(len(f.model_calls), 1)

    def test_count_above_reviewed_profile_or_output_over_profile_never_dispatches(self):
        f = broker_fixtures.ResearchTransport('runTest'); f.setUp(); self.addCleanup(f.doCleanups)
        policy = replace(f.model_policy, max_input_tokens=1048576)
        broker = f.make_broker(capability=ModelCapability(policy, lambda body: 1048577, f.send))
        with self.assertRaises(ResearchCapabilityError):
            f.call('evaluate', {'profile':'reviewed','items':[{'role':'user','content':'x'}],'key':'over-input'}, broker=broker)
        broker = f.make_broker(capability=ModelCapability(policy, lambda body: 1048576, f.send))
        with self.assertRaises(ResearchCapabilityError):
            f.call('evaluate', {'profile':'reviewed','items':[{'role':'user','content':'x'}],'key':'over-output',
                                'max_output':policy.max_output_tokens+1}, broker=broker)
        self.assertEqual(f.model_calls, [])
        self.assertEqual(f.budget._load()['inference'], {})

    def test_actual_sail_bridge_reserves_whole_window_but_sends_original_text_and_output_options(self):
        f = sail_fixtures.SailResearchHost('runTest')
        self.addCleanup(f.doCleanups)
        original_policy = sail_fixtures.ModelPolicy
        original_build = f.build
        def policy(*args, **kwargs):
            return replace(original_policy(*args, **kwargs), model=provider.model_of('flash_asap'),
                           input_usd_million='0.09', output_usd_million='0.18', max_input_tokens=1048576,
                           max_output_tokens=8000, allowed_efforts=('minimal',))
        def build():
            # The fixture's policy and whole-input receipt must describe the
            # same original limit before _Bridge validates either document.
            f.models['profiles']['reviewed']['billable_input_ceiling'] = 1048576
            f.inputs = replace(f.inputs, models=f.rewrite('original-whole-window-models.json', f.models))
            return original_build()
        f.build = build
        # Bind the reviewed model before the fixture opens its original scope;
        # an existing ledger cannot be reset or rebound to a different policy.
        with mock.patch.object(sail_fixtures, 'ModelPolicy', side_effect=policy):
            f.setUp()
        f.peer()
        f.broker.evaluate('reviewed', [{'role':'user','content':'hello'}], key='native-window', effort='minimal')
        wire = f.posts('/v1/responses')[0][2]
        self.assertEqual(wire['model'], provider.model_of('flash_asap'))
        self.assertEqual(wire['input'], [{'role':'user','content':'hello'}])
        self.assertEqual(wire['max_output_tokens'], 8000)
        self.assertEqual(wire['reasoning'], {'effort':'minimal'})
        self.assertNotIn('raw_prompt_tokens', wire)
        self.assertEqual(wire['truncation'], 'disabled')
        self.assertEqual(next(iter(f.budget._load()['inference'].values()))['max_nanos'], 95811840)


if __name__ == '__main__':
    unittest.main()
