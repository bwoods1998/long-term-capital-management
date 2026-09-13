"""Regression checks for bounded, restartable private research calls."""
import concurrent.futures
from contextlib import closing
import copy
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import portfolio as p


class ResearchTaskTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'research.sqlite'
        self.packet = p.load_packet()
        self.model = 'deepseek-ai/DeepSeek-V4-Flash-0731'
        self.body = p.build_task_request(self.model, 'Inspect the supplied evidence.')

    def reserve(self, db, task_key='workflow:investigate:0', **changes):
        args = dict(body=self.body, packet=self.packet, task_key=task_key, purpose='investigate')
        args.update(changes)
        return p.reserve_task(db, **args)

    def test_profiles_bound_worst_case_uncached_cost(self):
        for model, profile in p.TASK_PROFILES.items():
            with self.subTest(model=model):
                body = p.build_task_request(model, 'Evidence')
                self.assertEqual(p.validate_task_envelope(body), profile)
                cost = (Decimal(p.TASK_MAX_REQUEST_BYTES) * Decimal(profile['rates']['input']) +
                        Decimal(profile['max_output_tokens']) * Decimal(profile['rates']['output'])) / 1_000_000
                self.assertLess(cost, Decimal(profile['reserve_cents']) / 100)

    def test_dossier_profiles_raise_only_labeled_output_limit_within_existing_allowance(self):
        originals = copy.deepcopy(p.TASK_PROFILES)
        for model, profile in p.DOSSIER_PROFILES.items():
            with self.subTest(model=model):
                request = p.build_dossier_request(model, 'Checked financial evidence')
                self.assertEqual(p.validate_task_envelope(request), profile)
                self.assertEqual(request['max_output_tokens'], 32768)
                self.assertEqual(request['metadata'], {'completion_window': profile['completion_window'], 'dossier': 'v1'})
                bound = (Decimal(p.TASK_MAX_REQUEST_BYTES) * Decimal(profile['rates']['input']) +
                         Decimal(32768) * Decimal(profile['rates']['output'])) / 1_000_000
                self.assertLess(bound, Decimal(profile['reserve_cents']) / 100)
                for name, value in originals[model].items():
                    if name != 'max_output_tokens':
                        self.assertEqual(profile[name], value)
                ordinary = p.build_task_request(model, 'Checked financial evidence')
                self.assertEqual(ordinary['max_output_tokens'], originals[model]['max_output_tokens'])
                for invalid in [{**ordinary, 'max_output_tokens': 32768},
                                {**request, 'metadata': {'completion_window': profile['completion_window'], 'dossier': 'v2'}},
                                {**request, 'metadata': {**request['metadata'], 'policy_probe': 'v1'}},
                                {**request, 'tools': []}, {**request, 'prompt_cache_key': 'extra'},
                                {**request, 'input': 'x'*p.TASK_MAX_REQUEST_BYTES},
                                {**request, 'max_output_tokens': 32769}]:
                    with self.assertRaises(ValueError):
                        p.validate_task_envelope(invalid)
        self.assertEqual(p.TASK_PROFILES, originals)
        for model in ('deepseek-ai/DeepSeek-V4-Flash-0731', 'moonshotai/Kimi-K2.6'):
            with self.assertRaises(ValueError):
                p.build_dossier_request(model, 'Evidence')

    def test_dossier_reservations_keep_stable_request_rates_and_private_purposes(self):
        with closing(p.database(self.path)) as db:
            p.set_budget_limit(db, 500)
            for index, (model, profile) in enumerate(p.DOSSIER_PROFILES.items()):
                body = p.build_dossier_request(model, [{'role': 'user', 'content': 'Checked evidence'}])
                for purpose in ('investigate', 'critique'):
                    key = f'dossier:{index}:{purpose}'
                    rid = p.reserve_task(db, body, self.packet, key, purpose)
                    self.assertEqual(p.reserve_task(db, body, self.packet, key, purpose), rid)
                    row = p.get_run(db, rid)
                    self.assertEqual(row['request'], p.encoded(body))
                    self.assertEqual(row['reserved_cents'], profile['reserve_cents'])
                    self.assertEqual(json.loads(row['rates']), profile['rates'])
                for purpose in ('thesis', 'evaluation', 'replay', 'robustness', 'policy_probe'):
                    with self.assertRaises(ValueError):
                        p.reserve_task(db, body, self.packet, f'rejected:{index}:{purpose}', purpose)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 4)
            self.assertEqual(db.execute('SELECT SUM(reserved_cents) FROM runs').fetchone()[0], 240)

    def test_request_owns_history_and_tools_and_rejects_unbounded_options(self):
        history = [{'role': 'user', 'content': 'Source evidence'}]
        tools = [{'type': 'function', 'name': 'read_source', 'parameters': {'type': 'object'}}]
        body = p.build_task_request(self.model, history, tools)
        history[0]['content'] = 'Changed later'
        tools[0]['name'] = 'changed_later'
        self.assertEqual(body['input'][0]['content'], 'Source evidence')
        self.assertEqual(body['tools'][0]['name'], 'read_source')
        cases = []
        for field, value in [('max_output_tokens', 1000000), ('background', True),
                             ('previous_response_id', 'resp_private'), ('input', 'x' * 100000)]:
            changed = copy.deepcopy(body)
            changed[field] = value
            cases.append(changed)
        changed = copy.deepcopy(body)
        changed['tools'] = [{'type': 'web_search'}]
        cases.append(changed)
        changed = copy.deepcopy(body)
        changed['tools'] *= 2
        cases.append(changed)
        for changed in cases:
            with self.subTest(changed=list(changed)), self.assertRaises(ValueError):
                p.validate_task_envelope(changed)

    def test_policy_probe_rates_envelope_and_purpose_are_bound(self):
        with closing(p.database(self.path)) as db:
            for window, profile in p.POLICY_PROBE_PROFILES.items():
                body = p.build_task_request(p.POLICY_PROBE_MODEL, 'Frozen matched question')
                body['metadata'] = {'completion_window': window, 'policy_probe': 'v1'}
                body['prompt_cache_key'] = 'policy-' + 'a' * 64
                self.assertEqual(p.validate_task_envelope(body), profile)
                bound = (Decimal(p.POLICY_PROBE_MAX_REQUEST_BYTES) * Decimal(profile['rates']['input']) +
                         Decimal(profile['max_output_tokens']) * Decimal(profile['rates']['output'])) / 1_000_000
                self.assertLess(bound, Decimal(profile['reserve_cents']) / 100)
                rid = p.reserve_task(db, body, self.packet, 'probe:' + window, 'policy_probe')
                row = p.get_run(db, rid)
                self.assertEqual(json.loads(row['rates']), profile['rates'])
                self.assertEqual(row['reserved_cents'], 20)
                for purpose in ('thesis', 'investigate', 'evaluation'):
                    with self.assertRaises(ValueError):
                        p.reserve_task(db, body, self.packet, 'wrong:' + purpose, purpose)
                for changes in [{'metadata': {'completion_window': window, 'policy_probe': 'v2'}},
                                {'metadata': {**body['metadata'], 'supercache_write': '24h'}},
                                {'prompt_cache_key': 'unbounded'}, {'tools': []},
                                {'background': False}, {'input': 'x' * 48000}]:
                    with self.subTest(changes=list(changes)), self.assertRaises(ValueError):
                        p.validate_task_envelope({**body, **changes})
            with self.assertRaises(ValueError):
                self.reserve(db, task_key='wrong:ordinary', purpose='policy_probe')

    def test_replacement_probe_preserves_its_own_model_window_and_rates(self):
        with closing(p.database(self.path)) as db:
            for window, profile in p.POLICY_PROBE_REPLACEMENT_PROFILES.items():
                body = p.build_task_request(p.POLICY_PROBE_REPLACEMENT_MODEL, 'Replacement protocol question')
                body['metadata'] = {'completion_window': window, 'policy_probe': 'v2'}
                body['prompt_cache_key'] = 'policy-' + 'b' * 64
                self.assertEqual(p.validate_task_envelope(body), profile)
                rid = p.reserve_task(db, body, self.packet, 'replacement:' + window, 'policy_probe')
                self.assertEqual(json.loads(p.get_run(db, rid)['rates']), profile['rates'])
                bound = (Decimal(p.POLICY_PROBE_MAX_REQUEST_BYTES) * Decimal(profile['rates']['input']) +
                         Decimal(profile['max_output_tokens']) * Decimal(profile['rates']['output'])) / 1_000_000
                self.assertLess(bound, Decimal('.20'))
                for changed in [{**body, 'model': p.POLICY_PROBE_MODEL},
                                {**body, 'metadata': {'completion_window': window, 'policy_probe': 'v1'}},
                                {**body, 'metadata': {'completion_window': 'asap', 'policy_probe': 'v2'}}]:
                    with self.assertRaises(ValueError):
                        p.validate_task_envelope(changed)

    def test_task_reservation_is_idempotent_and_collisions_fail(self):
        with closing(p.database(self.path)) as db:
            first = self.reserve(db)
        with closing(p.database(self.path)) as db:
            self.assertEqual(first, self.reserve(db))
            self.assertEqual(db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 1)
            changed_packet = copy.deepcopy(self.packet)
            changed_packet['context'][0]['text'] += ' Changed.'
            for changes in [{'body': p.build_task_request(self.model, 'Changed prompt')},
                            {'packet': changed_packet}, {'purpose': 'critique'}]:
                with self.assertRaisesRegex(ValueError, 'collision'):
                    self.reserve(db, **changes)

    def test_concurrent_shared_budget_caps_legacy_and_new_tasks(self):
        with closing(p.database(self.path)) as db:
            p.set_budget_limit(db, p.RESERVE_CENTS + 10)
            p.reserve(db, p.build_request(self.packet), self.packet, 'Legacy reservation')
        def attempt(number):
            with closing(p.database(self.path)) as db:
                try:
                    self.reserve(db, task_key='parallel:' + str(number))
                    return 1
                except ValueError:
                    return 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(attempt, range(8))), 1)
        with closing(p.database(self.path)) as db:
            self.assertEqual(p.budget_limit(db), p.RESERVE_CENTS + 10)
            with self.assertRaises(ValueError):
                p.set_budget_limit(db, 0)
            p.set_budget_limit(db, 100)
            self.assertEqual(db.execute('SELECT SUM(reserved_cents) FROM runs').fetchone()[0], 30)

    def test_completed_non_thesis_output_never_creates_revision(self):
        with closing(p.database(self.path)) as db:
            rid = self.reserve(db)
            response = {'id': 'resp_task', 'status': 'completed',
                        'output': [{'type': 'function_call', 'name': 'read_source', 'arguments': '{}'}],
                        'usage': {'input_tokens': 100, 'output_tokens': 100}}
            with patch.object(p, 'credential_fingerprint', return_value='synthetic'), \
                    patch.object(p, 'api', return_value=response) as api:
                result = p.execute(db, rid, poll_seconds=0)
                p.execute(db, rid, poll_seconds=0)
                self.assertEqual(api.call_count, 1)
            self.assertEqual(result['runs'][0]['purpose'], 'investigate')
            self.assertEqual(result['runs'][0]['status'], 'completed')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM revisions').fetchone()[0], 0)
            with self.assertRaises(ValueError):
                p.public_snapshot(db)

    def test_exact_model_names_and_only_documented_aliases_are_accepted(self):
        models = [('deepseek-ai/DeepSeek-V4-Pro-0813', 'deepseek/deepseek-v4-pro-0813'),
                  ('deepseek-ai/DeepSeek-V4-Flash-0731', 'deepseek/deepseek-v4-flash-0731'),
                  ('moonshotai/Kimi-K3', 'moonshotai/Kimi-K3'),
                  ('moonshotai/Kimi-K2.6', 'moonshotai/Kimi-K2.6')]
        with closing(p.database(self.path)) as db:
            p.set_budget_limit(db, 1000)
            for index, (requested, reported) in enumerate(models):
                with self.subTest(model=requested):
                    rid = self.reserve(db, task_key=f'model:{index}', body=p.build_task_request(requested, 'Evidence'))
                    response = {'id': f'resp_model_{index}', 'model': reported, 'status': 'completed',
                                'output': [], 'usage': {'input_tokens': 10, 'output_tokens': 10}}
                    with patch.object(p, 'credential_fingerprint', return_value='synthetic'), \
                            patch.object(p, 'api', return_value=response):
                        p.execute(db, rid, poll_seconds=0)
                    self.assertEqual(json.loads(p.get_run(db, rid)['response'])['model'], reported)
                    self.assertIsNotNone(p.run_cost(p.get_run(db, rid)))
            self.assertEqual(db.execute('SELECT COUNT(*) FROM revisions').fetchone()[0], 0)

    def test_even_a_valid_thesis_answer_from_replay_cannot_enter_thesis_history(self):
        answer = {'headline': 'Cash measures have limited scope',
                  'summary': 'The cash remainder is a company-wide measure.', 'stance': 'watch',
                  'claims': [{'text': 'Cash after property spending is not an AI-only return.',
                              'evidence_ids': ['calculation-scope']}],
                  'assumptions': ['The supplied definition remains applicable.'],
                  'invalidation': ['A changed definition would require reconsideration.'],
                  'open_questions': ['What is the narrower investment return?'],
                  'next_review': 'Next evidence release', 'changes': ['Initial synthetic research view.']}
        p.validate_answer(answer, self.packet)
        with closing(p.database(self.path)) as db:
            rid = self.reserve(db, task_key='trajectory:synthetic:0', purpose='replay')
            response = {'id': 'resp_replay', 'status': 'completed',
                        'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(answer)}]}],
                        'usage': {'input_tokens': 100, 'output_tokens': 100}}
            with patch.object(p, 'credential_fingerprint', return_value='synthetic'), patch.object(p, 'api', return_value=response):
                p.execute(db, rid, poll_seconds=0)
            self.assertEqual(p.get_run(db, rid)['purpose'], 'replay')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM revisions').fetchone()[0], 0)

    def test_profile_rates_are_saved_and_preflight_uses_fractional_cents(self):
        with closing(p.database(self.path)) as db:
            rid = self.reserve(db)
            expected = json.loads(p.get_run(db, rid)['rates'])
            with patch.dict(p.TASK_PROFILES[self.model]['rates'], {'input': '99'}):
                self.assertEqual(json.loads(p.get_run(db, rid)['rates']), expected)
        summary = {'available': True, 'has_metronome_customer': True,
                   'balance_unavailable': False, 'balance': 9.99}
        with patch.object(p, 'api', side_effect=[{'data': [{'id': self.model}]}, summary]):
            with self.assertRaises(ValueError):
                p.preflight_task(self.model)
        summary['balance'] = 10
        with patch.object(p, 'api', side_effect=[{'data': [{'id': self.model}]}, summary]):
            p.preflight_task(self.model)


if __name__ == '__main__':
    unittest.main()
