"""Offline accounting and recovery for one costly write, not a model-quality grade."""
from contextlib import closing
from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

import lab
import portfolio as p
import supercache_experiment as sc


class SupercacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'ledger.sqlite'
        self.db = p.database(self.path)
        self.addCleanup(self.db.close)
        p.set_budget_limit(self.db, 1000)
        self.spec = {'prefix': 'SYNTHETIC financial source data, no actual issuer disclosure.\n' * 200,
                     'tasks': [{'id': 'company-' + str(i), 'symbol': 'X' + str(i),
                                'question': 'Which supplied evidence informs this fictional company?'} for i in range(9)]}

    def prepare(self, spec=None):
        return sc.prepare(self.db, spec or self.spec, p.iso(time.time() + 3600))

    def response(self, identifier, phase='write', **changes):
        value = {'id': identifier, 'model': p.SUPERCACHE_MODEL, 'status': 'completed',
                 'usage': {'input_tokens': 4096, 'output_tokens': 120, 'total_tokens': 4216,
                           'input_tokens_details': {'cached_tokens': 0 if phase == 'write' else 3072}},
                 'metadata': {'supercached_input_tokens': '0' if phase == 'write' else '2048',
                              'supercache_write_input_tokens': '3072' if phase == 'write' else '0'},
                 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'PRIVATE UNREVIEWED DRAFT'}]}]}
        value.update(changes)
        return value

    def finish(self, identifier, **changes):
        state = sc.status(self.db, identifier)
        phase = next(s['phase'] for s in state['stages'] if not s['terminal'])
        def api(method, route, body=None, request_id=None, **kwargs):
            self.assertEqual(method, 'POST')
            return self.response('resp_' + request_id.replace('-', ''), phase, **changes)
        with patch.object(p, 'credential_fingerprint', return_value='b' * 64), patch.object(p, 'api', side_effect=api):
            return sc.advance(self.db, identifier)

    def test_write_is_a_disjoint_input_class_priced_once_at_100x(self):
        usage = {'input_tokens': 10000, 'input_tokens_details': {'cached_tokens': 2000}, 'output_tokens': 100}
        rates = {'input': '0.35', 'cached': '0.10', 'output': '2'}
        metadata = {'supercached_input_tokens': '1000', 'supercache_write_input_tokens': '6000'}
        expected = (Decimal(2000) * Decimal('.35') + Decimal(1000) * Decimal('.10') +
                    Decimal(1000) * Decimal('.01') + Decimal(6000) * Decimal('35') + 200) / 1_000_000
        self.assertEqual(lab.estimate_cost(usage, rates, metadata, supercache_contract='write-24h-v1'), expected)
        for contract in [None, 'read-24h-v1', 'anything']:
            with self.assertRaises(ValueError):
                lab.estimate_cost(usage, rates, metadata, supercache_contract=contract)
        for bad in [{**metadata, 'supercache_write_input_tokens': '8001'},
                    {**metadata, 'supercached_input_tokens': '2001'},
                    {**metadata, 'supercache_write_input_tokens': 6000}, {},
                    {'supercache_write_input_tokens': '6000'}]:
            with self.assertRaises(ValueError):
                lab.estimate_cost(usage, rates, bad, supercache_contract='write-24h-v1')

    def test_read_cost_and_counterfactual_are_separate_from_actual_savings(self):
        campaign = self.prepare()
        self.finish(campaign)
        result = self.finish(campaign)
        read = result['stages'][1]['measurement']
        self.assertEqual(Decimal(read['estimated_usd']), Decimal('.00072128'))
        self.assertEqual(Decimal(read['same_usage_regular_hit_usd']), Decimal('.0009056'))
        self.assertEqual(Decimal(read['same_usage_superread_miss_usd']), Decimal('.0014176'))
        self.assertGreater(Decimal(result['known_estimated_usd']),
                           sum(Decimal(s['measurement']['same_usage_regular_hit_usd'])
                               for s in result['stages'] if s['measurement']))

    def test_profiles_bound_100x_input_and_old_profiles_still_prohibit_writes(self):
        for phase, profile in p.SUPERCACHE_PROFILES.items():
            body = p.build_supercache_request(self.spec['prefix'], 'Question', phase)
            self.assertEqual(p.validate_task_envelope(body), profile)
            cost = (Decimal(p.TASK_MAX_REQUEST_BYTES) * Decimal(profile['rates']['input']) * (100 if phase == 'write' else 1)
                    + Decimal(profile['max_output_tokens']) * Decimal(profile['rates']['output'])) / 1_000_000
            self.assertLess(cost, Decimal(profile['reserve_cents']) / 100)
            for mutate in [{'max_output_tokens': 100000}, {'input': 'just a short prompt'},
                           {'prompt_cache_key': 'unbound'}, {'metadata': {**body['metadata'], 'supercached_input_tokens': '1'}}]:
                with self.assertRaises(ValueError):
                    p.validate_task_envelope({**body, **mutate})
        ordinary = p.build_task_request(p.SUPERCACHE_MODEL, 'An ordinary request')
        ordinary['metadata']['supercache_write'] = '24h'
        with self.assertRaises(ValueError):
            p.validate_task_envelope(ordinary)

    def test_prepare_freezes_declared_questions_and_creates_no_paid_reservation(self):
        with patch.object(p, 'api') as api:
            identifier = self.prepare()
            frozen = sc.protocol(self.db, identifier)
            self.spec['tasks'][0]['question'] = 'Changed afterwards'
            self.assertNotIn('Changed afterwards', p.encoded(frozen))
            self.assertEqual(len(frozen['stages']), 10)
            self.assertEqual(frozen['max_reservation_cents'], 440)
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 0)
            with self.assertRaises(ValueError):
                self.prepare()
            api.assert_not_called()
        with self.assertRaises(sqlite3.IntegrityError), self.db:
            self.db.execute('UPDATE shared_context_campaigns SET protocol=\'{}\'')

    def test_one_write_and_declared_reads_finish_without_public_draft_text(self):
        identifier = self.prepare()
        for _ in range(10):
            result = self.finish(identifier)
        self.assertEqual(result['state'], 'finished')
        self.assertEqual(result['terminal_requests'], 10)
        self.assertEqual(result['unknown_usage_requests'], 0)
        self.assertEqual(Decimal(result['gross_reserved_usd']), Decimal('4.4'))
        self.assertNotIn('PRIVATE', p.encoded(result))
        self.assertNotIn(self.spec['prefix'], p.encoded(result))
        self.assertNotIn('resp_', p.encoded(result))
        with patch.object(p, 'api') as api:
            self.assertEqual(sc.advance(self.db, identifier), result)
            api.assert_not_called()
        with self.assertRaises(sqlite3.IntegrityError), self.db:
            self.db.execute('UPDATE shared_context_steps SET result=\'{}\'')

    def test_failed_or_counterless_write_cannot_trigger_more_paid_requests(self):
        identifier = self.prepare()
        result = self.finish(identifier, metadata={})
        self.assertEqual(result['state'], 'write_unconfirmed')
        self.assertEqual(result['unknown_usage_requests'], 1)
        with patch.object(p, 'api') as api:
            sc.advance(self.db, identifier)
            api.assert_not_called()
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 1)

    def test_fresh_process_recovers_accepted_write_by_get_only_even_after_code_change(self):
        identifier = self.prepare()
        with patch.object(p, 'credential_fingerprint', return_value='b' * 64), \
                patch.object(p, 'api', return_value={'id': 'resp_waiting', 'model': p.SUPERCACHE_MODEL, 'status': 'queued'}):
            sc.advance(self.db, identifier)
        with closing(p.database(self.path)) as db, \
                patch.object(p, 'credential_fingerprint', return_value='b' * 64), \
                patch.object(sc, 'code_hashes', return_value={'changed': 'implementation'}), \
                patch.object(p, 'api', return_value=self.response('resp_waiting')) as api:
            result = sc.advance(db, identifier)
            self.assertEqual(api.call_args.args, ('GET', '/v1/responses/resp_waiting'))
            self.assertEqual(result['terminal_requests'], 1)
            with self.assertRaisesRegex(ValueError, 'Implementation'):
                sc.advance(db, identifier)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 1)

    def test_crash_after_reservation_reuses_same_logical_write_without_extra_hold(self):
        identifier = self.prepare()
        reserve = p.reserve_task
        def stop_after_reserve(*args, **kwargs):
            reserve(*args, **kwargs)
            raise KeyboardInterrupt
        with patch.object(p, 'reserve_task', side_effect=stop_after_reserve), self.assertRaises(KeyboardInterrupt):
            sc.advance(self.db, identifier)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM shared_context_steps').fetchone()[0], 0)
        before = self.db.execute('SELECT id FROM runs').fetchone()[0]
        self.finish(identifier)
        self.assertEqual(self.db.execute('SELECT id FROM runs').fetchone()[0], before)
        self.assertEqual(self.db.execute('SELECT SUM(reserved_cents) FROM runs').fetchone()[0], 350)

    def test_core_rejects_second_write_changed_prefix_and_thirteenth_read(self):
        self.spec['tasks'].extend({'id': 'extra-' + str(i), 'symbol': 'X', 'question': 'Declared extra check'} for i in range(3))
        identifier = self.prepare()
        self.finish(identifier)
        packet = p.load_packet()
        writer = p.build_supercache_request(self.spec['prefix'], 'Another write', 'write')
        with self.assertRaises(ValueError):
            p.reserve_task(self.db, writer, packet, 'another-write', 'cache_research')
        changed = p.build_supercache_request(self.spec['prefix'] + ' changed', 'Question', 'read')
        with self.assertRaises(ValueError):
            p.reserve_task(self.db, changed, packet, 'changed-prefix', 'cache_research')
        for item in self.spec['tasks']:
            reader = p.build_supercache_request(self.spec['prefix'], item['question'], 'read')
            p.reserve_task(self.db, reader, packet, f'shared-context:{identifier}:{item["id"]}', 'cache_research')
        with self.assertRaises(ValueError):
            p.reserve_task(self.db, reader, packet, 'one-too-many', 'cache_research')
        self.assertEqual(self.db.execute('SELECT SUM(reserved_cents) FROM runs').fetchone()[0], 470)

    def test_write_pricing_settles_only_with_the_frozen_opt_in_contract(self):
        identifier = self.prepare()
        self.finish(identifier)
        row = self.db.execute('SELECT * FROM runs').fetchone()
        p.activate_budget_policy(self.db, 'Synthetic owner')
        p.settle_run(self.db, row['id'])
        self.assertEqual(Decimal(p.budget_accounting(self.db)['committed_usd']), Decimal('.1081184'))
        self.assertEqual(Decimal(p.budget_accounting(self.db)['gross_historical_reserved_usd']), Decimal('3.5'))

    def test_deadline_unknown_usage_and_duplicate_question_ids_fail_closed(self):
        identifier = self.prepare()
        with patch.object(sc.time, 'time', return_value=time.time() + 7200), patch.object(p, 'api') as api:
            self.assertEqual(sc.advance(self.db, identifier)['state'], 'deadline')
            api.assert_not_called()
        invalid = deepcopy(self.spec)
        invalid['tasks'][1]['id'] = invalid['tasks'][0]['id']
        with self.assertRaisesRegex(ValueError, 'task'):
            self.prepare(invalid)

    def test_complete_result_binds_private_draft_and_undeclared_requests_are_blocked(self):
        identifier = self.prepare()
        self.finish(identifier)
        reader = p.build_supercache_request(self.spec['prefix'], 'Undeclared new research', 'read')
        with self.assertRaisesRegex(ValueError, 'declared'):
            p.reserve_task(self.db, reader, p.load_packet(), 'outside-reviewed-protocol', 'cache_research')
        row = self.db.execute('SELECT * FROM runs').fetchone()
        response = json.loads(row['response'])
        response['output'] = []
        with self.db:
            self.db.execute('UPDATE runs SET response=? WHERE id=?', (p.encoded(response), row['id']))
        with self.assertRaisesRegex(ValueError, 'outcome changed'):
            sc.status(self.db, identifier)

    def incomplete_write(self, identifier, **changes):
        usage = self.response('resp_example')['usage']
        usage['output_tokens'] = 8192
        usage['total_tokens'] = usage['input_tokens'] + 8192
        arguments = {'status': 'incomplete', 'incomplete_details': {'reason': 'max_output_tokens'},
                     'usage': usage}
        arguments.update(changes)
        return self.finish(identifier, **arguments)

    def test_output_limited_write_requires_additive_receipt_preserves_original_then_reads(self):
        identifier = self.prepare()
        state = self.incomplete_write(identifier)
        self.assertEqual(state['state'], 'write_unconfirmed')
        before = tuple(self.db.execute('SELECT protocol,sha256 FROM shared_context_campaigns').fetchone())
        original = self.db.execute('SELECT result FROM shared_context_steps').fetchone()[0]
        frozen = sc.protocol(self.db, identifier)
        first = frozen['stages'][1]
        with self.assertRaises(ValueError):
            p.reserve_task(self.db, first['request'], frozen['packet'],
                           f'shared-context:{identifier}:{first["id"]}', 'cache_research')
        with patch.object(p, 'api') as api:
            receipt = sc.authorize_incomplete_write_reads(self.db, identifier, 'Synthetic reviewer')
            self.assertEqual(receipt, sc.authorize_incomplete_write_reads(self.db, identifier, 'Same review'))
            api.assert_not_called()
        self.assertEqual(receipt['declared_read_sha256'], {s['id']:s['request_sha256'] for s in frozen['stages'][1:]})
        self.assertEqual(receipt['expires'], min(frozen['deadline'], self.db.execute('SELECT created FROM runs').fetchone()[0]+23*3600))
        for _ in range(9):
            state = self.finish(identifier)
        self.assertEqual(state['state'], 'finished')
        self.assertEqual(state['original_write_outcome'], 'write_unconfirmed')
        self.assertFalse(state['stages'][0]['measurement']['write_confirmed'])
        self.assertEqual(state['admitted_requests'], 10)
        self.assertEqual(Decimal(state['gross_reserved_usd']), Decimal('4.4'))
        self.assertEqual(before, tuple(self.db.execute('SELECT protocol,sha256 FROM shared_context_campaigns').fetchone()))
        self.assertEqual(original, self.db.execute("SELECT result FROM shared_context_steps WHERE stage_id='write'").fetchone()[0])
        for action in ['UPDATE shared_context_continuations SET receipt=\'{}\'', 'DELETE FROM shared_context_continuations']:
            with self.assertRaises(sqlite3.IntegrityError), self.db:
                self.db.execute(action)

    def test_continuation_refuses_expiry_changes_and_code_drift_but_recovers_accepted_read(self):
        identifier = self.prepare()
        self.incomplete_write(identifier)
        with patch.object(sc.time, 'time', return_value=time.time()+7200), self.assertRaises(ValueError):
            sc.authorize_incomplete_write_reads(self.db, identifier, 'Reviewer')
        sc.authorize_incomplete_write_reads(self.db, identifier, 'Reviewer')
        with patch.object(p, 'credential_fingerprint', return_value='b'*64), \
                patch.object(p, 'api', return_value={'id':'resp_read','model':p.SUPERCACHE_MODEL,'status':'queued'}):
            sc.advance(self.db, identifier)
        changed = {name:'a'*64 for name in sc.code_hashes()}
        with patch.object(p, 'supercache_implementation_hashes', return_value=changed), \
                patch.object(p, 'credential_fingerprint', return_value='b'*64), \
                patch.object(p, 'api', return_value=self.response('resp_read', 'read')) as api:
            sc.advance(self.db, identifier)
            self.assertEqual(api.call_args.args, ('GET','/v1/responses/resp_read'))
            with self.assertRaisesRegex(ValueError,'Implementation'):
                sc.advance(self.db, identifier)
            next_stage = sc.protocol(self.db,identifier)['stages'][2]
            with self.assertRaisesRegex(ValueError,'receipt'):
                p.reserve_task(self.db,next_stage['request'],p.load_packet(),f'shared-context:{identifier}:{next_stage["id"]}','cache_research')
        row = self.db.execute("SELECT * FROM runs WHERE task_key LIKE '%:write'").fetchone()
        response = json.loads(row['response']); response['usage']['output_tokens'] -= 1; response['usage']['total_tokens'] -= 1
        with self.db:
            self.db.execute('UPDATE runs SET response=? WHERE id=?',(p.encoded(response),row['id']))
        with self.assertRaises(ValueError):
            sc.advance(self.db,identifier)

    def test_continuation_rejects_unknown_usage_failed_cancelled_and_other_incomplete_reasons(self):
        variants = [{'status':'failed'}, {'status':'cancelled'}, {'metadata':{}},
                    {'incomplete_details':{'reason':'content_filter'}},
                    {'metadata':{'supercached_input_tokens':'0','supercache_write_input_tokens':'0'}}]
        for i, changes in enumerate(variants):
            with self.subTest(changes=changes), closing(p.database(Path(self.tmp.name)/f'case-{i}.sqlite')) as other:
                p.set_budget_limit(other,1000)
                old,self.db=self.db,other
                try:
                    identifier=self.prepare(); self.incomplete_write(identifier,**changes)
                    with self.assertRaises((ValueError,KeyError)):
                        sc.authorize_incomplete_write_reads(other,identifier,'Reviewer')
                    self.assertEqual(other.execute('SELECT COUNT(*) FROM shared_context_continuations').fetchone()[0],0)
                finally:
                    self.db=old


if __name__ == '__main__':
    unittest.main()
