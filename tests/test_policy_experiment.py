"""Offline contracts for the fixed sixteen-task completion-window pilot."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

import policy_experiment as policy
import portfolio as p
import research_eval as evaluation


class PolicyExperimentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.path = self.directory / 'portfolio.sqlite'
        self.now = policy._deadline('2026-09-12T23:40:00Z')
        self.monotonic = 1000
        clock = patch.object(policy.time, 'time', side_effect=lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)
        monotonic = patch.object(policy.time, 'monotonic', side_effect=lambda: self.monotonic)
        monotonic.start()
        self.addCleanup(monotonic.stop)
        fingerprint = patch.object(p, 'credential_fingerprint', return_value='synthetic-fingerprint')
        fingerprint.start()
        self.addCleanup(fingerprint.stop)
        self.db = policy.initialize(p.database(self.path))
        self.addCleanup(self.db.close)
        p.set_budget_limit(self.db, 10000)
        self.cases = evaluation.load_cases()

    def create(self):
        return policy.create(self.db, version='v1')

    def case_for(self, body):
        question = json.loads(body['input'][-1]['content'])
        return next(case for case in self.cases if case['claim'] == question['claim'] and
                    case['as_of'] == question['as_of'])

    def answer(self, case):
        return {'verdict': case['expected']['verdict'],
                'evidence_ids': sorted({group[0] for group in case['expected']['required_evidence_groups']}),
                'reason': 'PRIVATE_MODEL_REASON'}

    def response(self, run_id, answer=None, state='completed', cached=0, supercached=0):
        return {'id': 'resp_' + run_id.replace('-', '_'), 'status': state,
                'output': [{'type': 'message', 'content': [{'type': 'output_text',
                    'text': json.dumps(answer or self.answer(self.cases[0]))}]}],
                'usage': {'input_tokens': 1000, 'output_tokens': 100,
                          'input_tokens_details': {'cached_tokens': cached}},
                'metadata': {'supercached_input_tokens': str(supercached),
                             'supercache_write_input_tokens': '0', 'private': 'PRIVATE_PROVIDER_METADATA'}}

    def oracle(self, method, route, body=None, run_id=None, **kwargs):
        self.assertEqual(method, 'POST')
        self.now += 1
        self.monotonic += 1
        return self.response(run_id, self.answer(self.case_for(body)))

    def clear_delay(self):
        with self.db:
            self.db.execute('UPDATE policy_items SET next_attempt=0')

    def complete(self, identifier, provider=None):
        with patch.object(p, 'api', side_effect=provider or self.oracle) as api:
            for _ in range(16):
                result = policy.advance(self.db, identifier, controller='continuous-controller')
            self.assertEqual(api.call_count, 16)
        self.assertTrue(result['finished'])
        return result

    def test_create_freezes_counterbalanced_exact_repeats_without_paid_calls(self):
        with patch.object(p, 'api') as api, patch.object(p, 'reserve_task') as reserve:
            identifier = self.create()
            api.assert_not_called()
            reserve.assert_not_called()
        experiment = policy._experiment(self.db, identifier)
        items = experiment['protocol']['items']
        self.assertEqual(len(items), 16)
        for offset in range(0, 16, 2):
            first, repeat = items[offset:offset + 2]
            self.assertEqual(first['phase'], 'first_use')
            self.assertEqual(repeat['phase'], 'repeat')
            self.assertEqual(first['request'], repeat['request'])
        self.assertEqual([items[offset]['window'] for offset in range(0, 16, 4)],
                         ['asap', 'flex', 'asap', 'flex'])
        self.assertEqual(len({item['request']['prompt_cache_key'] for item in items}), 8)
        for item in items:
            profile = p.validate_task_envelope(item['request'])
            self.assertEqual(profile['rates'], policy.RATES[item['window']])
            self.assertEqual(item['request']['background'], True)
            wire = p.encoded(item['request'])
            self.assertNotIn('required_evidence_groups', wire)
            self.assertNotIn('supercache_write', wire)
            self.assertLess(len(wire.encode()), 48000)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 0)
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.create()
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute('UPDATE policy_experiments SET deadline=deadline+1')
        self.db.rollback()

    def test_worst_case_profile_reservations_fit_reviewed_total(self):
        identifier = self.create()
        for window, profile in p.POLICY_PROBE_PROFILES.items():
            worst = (Decimal(48000) * Decimal(profile['rates']['input']) +
                     Decimal(16384) * Decimal(profile['rates']['output'])) / 1000000
            self.assertLess(worst, Decimal('0.20'))
        self.assertEqual(policy.status(self.db, identifier)['planned_tasks'], 16)
        self.assertEqual(16 * policy.RESERVE_CENTS, 320)

    def test_known_background_work_blocks_repeat_until_terminal_and_uses_get(self):
        identifier = self.create()
        def queued(method, route, body=None, run_id=None, **kwargs):
            return self.response(run_id, state='queued')
        with patch.object(p, 'api', side_effect=queued):
            first = policy.advance(self.db, identifier, controller='one')
        self.assertEqual(first['states'], {'waiting': 1, 'pending': 15})
        row = self.db.execute('SELECT * FROM runs').fetchone()
        self.clear_delay()
        with patch.object(p, 'api', return_value=self.response(row['id'], self.answer(self.cases[1]))) as api:
            result = policy.advance(self.db, identifier, controller='one')
        api.assert_called_once_with('GET', '/v1/responses/' + row['response_id'])
        self.assertEqual(result['cost']['reserved_tasks'], 1)
        self.assertEqual(result['tasks'][1]['state'], 'pending')
        self.assertEqual(result['tasks'][0]['state'], 'completed')

    def test_uncertain_submission_reuses_original_key_and_excludes_timing(self):
        identifier = self.create()
        with patch.object(p, 'api', side_effect=RuntimeError('PRIVATE_EXCEPTION')) as first:
            result = policy.advance(self.db, identifier, controller='one')
        self.assertEqual(result['cost']['unknown_cost_tasks'], 1)
        self.assertEqual(result['states'], {'unknown': 1, 'pending': 15})
        self.clear_delay()
        with patch.object(p, 'api', side_effect=self.oracle) as second:
            result = policy.advance(self.db, identifier, controller='one')
        self.assertEqual(first.call_args, second.call_args)
        self.assertEqual(result['cost']['reserved_tasks'], 1)
        self.assertEqual(result['tasks'][0]['timing']['exclusion_reason'], 'unconfirmed_submission')
        self.assertFalse(result['tasks'][0]['timing']['eligible'])

    def test_reservation_orphan_and_response_before_grade_reconcile_without_new_post(self):
        identifier = self.create()
        item = self.db.execute('SELECT * FROM policy_items ORDER BY ordinal LIMIT 1').fetchone()
        experiment = policy._experiment(self.db, identifier)
        run_id = p.reserve_task(self.db, json.loads(item['request_json']), experiment['protocol']['packet'],
                                item['task_key'], 'policy_probe')
        with patch.object(p, 'api', side_effect=self.oracle):
            p.execute(self.db, run_id, poll_seconds=0)
        with patch.object(p, 'api') as api:
            result = policy.status(self.db, identifier)
            api.assert_not_called()
        self.assertEqual(result['tasks'][0]['state'], 'completed')
        self.assertEqual(result['cost']['reserved_tasks'], 1)
        self.assertEqual(result['tasks'][0]['timing']['exclusion_reason'], 'missing_terminal_observation')
        self.assertEqual(result['tasks'][1]['state'], 'pending')

    def test_new_controller_resume_keeps_task_but_excludes_interrupted_latency(self):
        identifier = self.create()
        with patch.object(p, 'api', side_effect=lambda method, route, body=None, run_id=None, **kwargs:
                          self.response(run_id, state='queued')):
            policy.advance(self.db, identifier, controller='old-controller')
        row = self.db.execute('SELECT * FROM runs').fetchone()
        self.clear_delay()
        with patch.object(p, 'api', return_value=self.response(row['id'], self.answer(self.cases[1]))):
            result = policy.advance(self.db, identifier, controller='new-controller')
        self.assertEqual(result['tasks'][0]['timing']['exclusion_reason'], 'interrupted_controller')
        self.assertEqual(result['cost']['reserved_tasks'], 1)

    def test_completed_invalid_output_is_retained_and_planned_repeat_is_distinct(self):
        identifier = self.create()
        def provider(method, route, body=None, run_id=None, **kwargs):
            answer = {'unusable': 'PRIVATE_INVALID'} if self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0] == 1 else self.answer(self.case_for(body))
            return self.response(run_id, answer)
        result = self.complete(identifier, provider)
        self.assertEqual(result['states'], {'invalid': 1, 'completed': 15})
        self.assertFalse(result['tasks'][0]['grade']['passed'])
        self.assertTrue(result['tasks'][1]['grade']['passed'])
        with patch.object(p, 'api') as api:
            policy.advance(self.db, identifier)
            api.assert_not_called()
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM revisions').fetchone()[0], 0)

    def test_budget_history_and_global_sixteen_call_cap_cannot_be_bypassed(self):
        identifier = self.create()
        experiment = policy._experiment(self.db, identifier)
        body = experiment['protocol']['items'][0]['request']
        for index in range(15):
            p.reserve_task(self.db, body, experiment['protocol']['packet'], 'earlier-policy:' + str(index), 'policy_probe')
        with patch.object(p, 'api', side_effect=self.oracle) as api:
            policy.advance(self.db, identifier)
            result = policy.advance(self.db, identifier)
            self.assertEqual(api.call_count, 1)
        self.assertEqual(result['cost']['reserved_tasks'], 1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 16)
        self.assertEqual(self.db.execute('SELECT SUM(reserved_cents) FROM runs').fetchone()[0], 320)
        self.assertEqual(self.db.execute('SELECT error_code FROM policy_items WHERE ordinal=1').fetchone()[0], 'call_cap')

    def test_existing_money_reservations_and_deadline_block_new_paid_work(self):
        identifier = self.create()
        p.set_budget_limit(self.db, 0)
        with patch.object(p, 'api') as api:
            result = policy.advance(self.db, identifier)
            api.assert_not_called()
        self.assertEqual(result['cost']['reserved_tasks'], 0)
        p.set_budget_limit(self.db, 320)
        self.now = policy._deadline(policy.DEADLINE) + 1
        with patch.object(p, 'api') as api:
            result = policy.advance(self.db, identifier)
            api.assert_not_called()
        self.assertTrue(result['deadline_reached'])
        self.assertEqual(result['cost']['reserved_tasks'], 0)

    def test_competing_controllers_cannot_submit_same_item_concurrently(self):
        identifier = self.create()
        entered, release = threading.Event(), threading.Event()
        def provider(*args, **kwargs):
            entered.set()
            self.assertTrue(release.wait(5))
            return self.oracle(*args, **kwargs)
        def advance():
            with closing(p.database(self.path)) as db:
                return policy.advance(db, identifier, controller='first')
        with patch.object(p, 'api', side_effect=provider) as api:
            with ThreadPoolExecutor(max_workers=1) as pool:
                pending = pool.submit(advance)
                try:
                    self.assertTrue(entered.wait(5))
                    policy.advance(self.db, identifier, controller='second')
                    self.assertEqual(api.call_count, 1)
                finally:
                    release.set()
                pending.result()
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 1)

    def test_frozen_prompt_and_item_integrity_survive_builder_changes(self):
        identifier = self.create()
        with (patch.object(policy, 'build_request', side_effect=AssertionError('Do not rebuild')),
              patch.object(evaluation, 'SYSTEM_PROMPT', 'New later instructions'),
              patch.object(p, 'api', side_effect=self.oracle)):
            policy.advance(self.db, identifier)
        with self.db:
            self.db.execute("UPDATE policy_items SET phase='altered_phase' WHERE ordinal=1")
        with patch.object(p, 'api') as api:
            with self.assertRaises(ValueError):
                policy.advance(self.db, identifier)
            api.assert_not_called()

    def test_mutated_task_key_cannot_relabel_an_equivalent_orphan_as_a_sample(self):
        identifier = self.create()
        experiment = policy._experiment(self.db, identifier)
        body = experiment['protocol']['items'][0]['request']
        p.reserve_task(self.db, body, experiment['protocol']['packet'], 'outside-equivalent', 'policy_probe')
        with self.db:
            self.db.execute("UPDATE policy_items SET task_key='outside-equivalent' WHERE ordinal=0")
        with patch.object(p, 'api') as api:
            with self.assertRaises(ValueError):
                policy.advance(self.db, identifier)
            api.assert_not_called()

    def test_new_reservations_require_the_frozen_rate_contract(self):
        identifier = self.create()
        with patch.dict(p.POLICY_PROBE_PROFILES['asap']['rates'], {'input': '99'}), patch.object(p, 'api') as api:
            with self.assertRaises(ValueError):
                policy.advance(self.db, identifier)
            api.assert_not_called()
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 0)

    def test_public_usage_repricing_and_cache_comparison_preserve_every_sample(self):
        identifier = self.create()
        seen = set()
        def provider(method, route, body=None, run_id=None, **kwargs):
            self.now += 2
            self.monotonic += 2
            key = body['prompt_cache_key']
            cached = 900 if key in seen else 0
            seen.add(key)
            # A deliberately unmatched initial hit remains visible but is not
            # presented as a timing comparison against a cache-miss arm.
            if self.case_for(body)['id'] == policy.CASE_IDS[0] and body['metadata']['completion_window'] == 'flex' and cached == 0:
                cached = 300
            return self.response(run_id, self.answer(self.case_for(body)), cached=cached)
        result = self.complete(identifier, provider)
        self.assertEqual(result['cost']['reserved_usd'], '3.2')
        self.assertEqual(result['cost']['unknown_cost_tasks'], 0)
        self.assertEqual(len(result['tasks']), 16)
        self.assertFalse(result['pairs'][0]['conditional_timing_comparable'])
        self.assertTrue(result['pairs'][1]['conditional_timing_comparable'])
        self.assertEqual(result['pairs'][0]['absolute_cache_fraction_gap'], 0.3)
        for task in result['tasks']:
            self.assertEqual(Decimal(task['same_usage_repriced_usd']['asap']),
                             2 * Decimal(task['same_usage_repriced_usd']['flex']))
            self.assertEqual(task['timing']['client_observed_seconds'], 2)
        with patch.object(p, 'api') as api:
            public = policy.export(self.db, identifier, self.directory / 'policy-experiment.json')
            api.assert_not_called()
        encoded = p.encoded(public)
        for marker in ('PRIVATE_', 'task_key', 'run_id', 'response_id', 'prompt_cache_key', 'required_evidence_groups'):
            self.assertNotIn(marker, encoded)
        for row in self.db.execute('SELECT id,response_id FROM runs'):
            self.assertNotIn(row['id'], encoded)
            self.assertNotIn(row['response_id'], encoded)
        with self.assertRaises(ValueError):
            policy.export(self.db, identifier, self.directory / 'portfolio.json')

    def test_wall_clock_jump_is_excluded_and_monotonic_duration_is_retained(self):
        identifier = self.create()
        def jumped(method, route, body=None, run_id=None, **kwargs):
            self.now += 100
            self.monotonic += 2
            return self.response(run_id, self.answer(self.case_for(body)))
        with patch.object(p, 'api', side_effect=jumped):
            result = policy.advance(self.db, identifier, controller='one')
        timing = result['tasks'][0]['timing']
        self.assertFalse(timing['eligible'])
        self.assertEqual(timing['exclusion_reason'], 'clock_discontinuity')
        self.assertEqual(timing['client_observed_seconds'], 2)

    def test_pause_between_complete_arms_excludes_pair_but_keeps_individual_timings(self):
        identifier = self.create()
        with patch.object(p, 'api', side_effect=self.oracle):
            for ordinal in range(16):
                if ordinal == 2:
                    self.now += 3600
                    self.monotonic += 3600
                result = policy.advance(self.db, identifier,
                                        controller='before' if ordinal < 2 else 'after')
        self.assertTrue(result['finished'])
        self.assertTrue(all(task['timing']['eligible'] for task in result['tasks']))
        self.assertFalse(result['pairs'][0]['continuous_pair_observation'])
        self.assertFalse(result['pairs'][0]['conditional_timing_comparable'])
        self.assertTrue(result['pairs'][2]['conditional_timing_comparable'])

    def test_failed_terminal_response_cannot_be_reported_as_a_fast_completed_pair(self):
        identifier = self.create()
        def provider(method, route, body=None, run_id=None, **kwargs):
            return self.response(run_id, self.answer(self.case_for(body)),
                                 state='failed' if body['metadata']['completion_window'] == 'flex' else 'completed')
        result = self.complete(identifier, provider)
        self.assertEqual(result['states'], {'completed': 8, 'failed': 8})
        self.assertTrue(all(not pair['conditional_timing_comparable'] for pair in result['pairs']))

    def test_repricing_honors_supercache_metadata_if_a_read_is_reported(self):
        identifier = self.create()
        def provider(method, route, body=None, run_id=None, **kwargs):
            return self.response(run_id, self.answer(self.case_for(body)), cached=900, supercached=400)
        result = self.complete(identifier, provider)
        for task in result['tasks']:
            expected = p.estimate_cost({'input_tokens': 1000, 'output_tokens': 100,
                                       'input_tokens_details': {'cached_tokens': 900}},
                                      policy.RATES['asap'], {'supercached_input_tokens': '400',
                                      'supercache_write_input_tokens': '0'})
            self.assertEqual(Decimal(task['same_usage_repriced_usd']['asap']), expected)
        self.assertTrue(all(not pair['conditional_timing_comparable'] for pair in result['pairs']))

    def close_rejected(self):
        identifier = self.create()
        with patch.object(p, 'api', side_effect=RuntimeError('HTTP 400; synthetic configuration rejection')):
            policy.advance(self.db, identifier, controller='rejected')
        with patch.object(p, 'api') as api:
            closed = policy.close_configuration_rejected(self.db, identifier)
            api.assert_not_called()
        self.assertTrue(closed['stopped'])
        self.assertFalse(closed['finished'])
        self.assertEqual(closed['states'], {'unknown': 1, 'not_run': 15})
        return identifier

    def test_closure_is_append_only_and_preserves_unknown_request_hold_and_unadmitted_items(self):
        identifier = self.close_rejected()
        prior = dict(self.db.execute('SELECT * FROM runs').fetchone())
        with patch.object(p, 'api') as api:
            self.clear_delay()
            result = policy.advance(self.db, identifier, controller='should-not-run')
            api.assert_not_called()
        self.assertEqual(dict(self.db.execute('SELECT * FROM runs').fetchone()), prior)
        self.assertEqual(result['cost']['reserved_usd'], '0.2')
        self.assertEqual(result['cost']['unknown_cost_tasks'], 1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM policy_items WHERE state="pending"').fetchone()[0], 15)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute('DELETE FROM policy_closures')
        self.db.rollback()
        archived = policy.export(self.db, identifier, self.directory / 'rejected' / 'policy-experiment.json')
        self.assertEqual(archived['model'], policy.MODEL)
        self.assertEqual(archived['windows'], ['asap', 'flex'])

    def test_replacement_requires_closed_v1_and_keeps_original_global_cap(self):
        with self.assertRaises(ValueError):
            policy.create(self.db, version='v2')
        old = self.close_rejected()
        prior_protocol = self.db.execute('SELECT protocol_json FROM policy_experiments WHERE id=?', (old,)).fetchone()[0]
        with patch.object(p, 'api') as api:
            identifier = policy.create(self.db, version='v2')
            api.assert_not_called()
        with patch.object(p, 'api', side_effect=self.oracle) as api:
            for _ in range(12):
                result = policy.advance(self.db, identifier, controller='replacement')
            self.assertEqual(api.call_count, 12)
        self.assertTrue(result['finished'])
        self.assertEqual(result['model'], 'moonshotai/Kimi-K2.6')
        self.assertEqual(result['windows'], ['balanced', 'flex'])
        self.assertEqual(result['planned_tasks'], 12)
        self.assertEqual(len(result['pairs']), 6)
        self.assertEqual(result['cost']['reserved_usd'], '2.4')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 13)
        self.assertEqual(self.db.execute('SELECT SUM(reserved_cents) FROM runs').fetchone()[0], 260)
        self.assertEqual(self.db.execute('SELECT protocol_json FROM policy_experiments WHERE id=?', (old,)).fetchone()[0], prior_protocol)
        self.assertEqual(policy.status(self.db, old)['windows'], ['asap', 'flex'])
        self.assertEqual([block['windows'][0] for block in result['window_order_by_block']],
                         ['balanced', 'flex', 'balanced'])
        for item in policy._experiment(self.db, identifier)['protocol']['items']:
            body = item['request']
            self.assertEqual(body['metadata']['policy_probe'], 'v2')
            self.assertEqual(body['model'], policy.REPLACEMENT_MODEL)
            self.assertEqual(p.validate_task_envelope(body)['rates'], policy.REPLACEMENT_RATES[item['window']])
        with self.assertRaises(ValueError):
            policy.create(self.db, version='v2')


if __name__ == '__main__':
    unittest.main()
