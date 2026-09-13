"""Synthetic handoff through the real curator and queue; inference is always mocked."""
from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import investigator as inv
import portfolio as p
import research_queue as queue
import research_sources as sources
import source_curation as curation
import test_source_curation as fixture


class CurationQueueTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / '.data/portfolio.sqlite'
        self.db = queue.initialize(p.database(self.path))
        self.addCleanup(self.db.close)
        p.set_budget_limit(self.db, 9100)
        self.args, self.snapshots = fixture.make_fixture(self.db)
        self.now = fixture.NOW
        self.calls = []
        self.queued = False
        for target, name, options in [
            (queue.time, 'time', {'side_effect': lambda: self.now}),
            (p, 'preflight_task', {'return_value': None}),
            (p, 'credential_fingerprint', {'return_value': 'synthetic-fingerprint'}),
            (p, 'api', {'side_effect': self.api}),
            (sources, '_download', {'side_effect': AssertionError('No network in synthetic test')}),
            (sources.SourceStore, '_read', {'side_effect': AssertionError('No baseline-cache fallback')}),
            (sources.SourceStore, 'capture', {'side_effect': AssertionError('Only selected frozen snapshots')}),
        ]:
            item = patch.object(target, name, **options)
            item.start()
            self.addCleanup(item.stop)

    def prepare(self):
        return curation.prepare(self.db, 'synthetic-financial-change', **self.args)

    def approve(self, bundle):
        return curation.review(self.db, bundle['bundle_id'], 'approve', 'Synthetic fact reviewer',
                               expected_sha256=bundle['sha256'])

    def enqueue(self, bundle, key='changed-source-job'):
        result = queue.enqueue(self.db, key, inv.QUESTION, bundle_id=bundle['bundle_id'],
                               due=fixture.NOW, deadline=fixture.NOW + 21600, root=self.root)
        self.investigation_id = next(item['investigation_id'] for item in result['jobs']
                                     if item['job_key'] == key)
        return result

    def tick(self, db=None):
        self.now += 65
        return queue.advance(db if db is not None else self.db)

    def api(self, method, route, body=None, request_id=None, **kwargs):
        self.calls.append((method, route, request_id, deepcopy(body)))
        identifier = 'resp_' + request_id if method == 'POST' else route.rsplit('/', 1)[-1]
        response = {'id': identifier, 'status': 'completed', 'output': [],
                    'usage': {'input_tokens': 1000, 'output_tokens': 200,
                              'input_tokens_details': {'cached_tokens': 0}}}
        if self.queued:
            response['status'] = 'queued'
            return response
        state = inv.get(self.db, self.investigation_id)
        if state['phase'] == 'research' and state['turn'] == 0:
            calls = [
                ('read_source', {'source_id': 'fy26-results', 'query': 'ocf-2026'}),
                ('calculate', {'operation': 'subtract', 'left_id': 'ocf-2026', 'right_id': 'ppe-2026'}),
                ('save_hypothesis', {'statement': 'The synthetic cash measure changed.',
                                     'invalidation': 'A revised source could alter this calculation.'}),
            ]
            response['output'] = [{'type': 'function_call', 'call_id': f'call_{index}',
                                   'name': name, 'arguments': json.dumps(arguments)}
                                  for index, (name, arguments) in enumerate(calls)]
        else:
            if state['phase'] == 'critique':
                output = {'verdict': 'pass', 'summary': 'The synthetic calculation has the stated scope.', 'issues': []}
            else:
                output = {'headline': 'Synthetic cash measure changed',
                    'summary': 'Synthetic operating cash exceeds cash property purchases.',
                    'claims': [{'text': 'Synthetic operating cash increased in the checked source.',
                                'evidence_ids': [next(iter(state['passages']))]}],
                    'changes': ['A separately checked source update changed the synthetic amount.'],
                    'open_questions': ['Would a later source change the measure?'],
                    'invalidation': ['A corrected disclosure could change the calculation.'],
                    'change_assessment': 'new_evidence'}
            response['output'] = [{'type': 'message', 'content': [
                {'type': 'output_text', 'text': json.dumps(output)}]}]
        return response

    def test_reviewed_change_survives_creation_crash_and_accepted_id_recovery_without_publication(self):
        bundle = self.prepare()
        with self.assertRaisesRegex(ValueError, 'separate curation approval'):
            self.enqueue(bundle)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_queue_jobs').fetchone()[0], 0)
        receipt = self.approve(bundle)
        result = self.enqueue(bundle)
        self.assertEqual(result['jobs'][0]['curation_bundle_id'], bundle['bundle_id'])
        self.assertEqual(self.calls, [])
        row, data = queue._get(self.db, 'changed-source-job')
        self.assertEqual(data['schema_version'], 2)
        self.assertEqual(data['packet'], self.args['packet'])
        self.assertEqual(data['snapshots'], self.snapshots)
        self.assertEqual(data['curation_receipt'], receipt)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 0)
        self.assertFalse((self.root / '.data/research/sources').exists())

        original = inv.start
        def interrupted(*args, **kwargs):
            original(*args, **kwargs)
            raise KeyboardInterrupt
        with patch.object(inv, 'start', side_effect=interrupted), self.assertRaises(KeyboardInterrupt):
            self.tick()
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM investigations').fetchone()[0], 1)
        self.assertEqual(self.calls, [])

        self.queued = True
        self.tick()
        accepted = dict(self.db.execute('SELECT id,response_id,request FROM runs').fetchone())
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0][0], 'POST')
        self.assertEqual(inv.get(self.db, self.investigation_id)['snapshots'], self.snapshots)
        self.queued = False
        with closing(p.database(self.path)) as fresh:
            self.tick(fresh)
        self.assertEqual(self.calls[1][:3], ('GET', '/v1/responses/' + accepted['response_id'], None))
        self.assertEqual(dict(self.db.execute('SELECT id,response_id,request FROM runs').fetchone()), accepted)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM investigations').fetchone()[0], 1)
        state = inv.get(self.db, self.investigation_id)
        self.assertEqual(state['snapshots'], data['snapshots'])
        self.assertIn('190,000', ''.join(item['text'] for item in state['passages'].values()))
        calculations = [item['result'] for item in state['tool_results'] if item['name'] == 'calculate']
        self.assertEqual(calculations[0]['value'], '74052')
        self.tick()
        finished = self.tick()
        self.assertEqual(finished['jobs'][0]['state'], 'awaiting_review')
        self.assertEqual(finished['jobs'][0]['model_calls'], 3)
        calls = len(self.calls)
        self.tick()
        self.assertEqual(len(self.calls), calls)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM investigation_reviews').fetchone()[0], 0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM revisions').fetchone()[0], 0)
        self.assertEqual(inv.public_snapshot(self.db)['investigations'], [])
        self.assertFalse((self.root / 'public').exists())
        self.assertEqual(p.budget_limit(self.db), 9100)
        self.assertEqual(queue._get(self.db, 'changed-source-job')[0]['input_json'], row['input_json'])

    def test_new_substantive_capture_blocks_new_job_but_existing_job_replays_frozen_bundle(self):
        bundle = self.prepare()
        self.approve(bundle)
        self.enqueue(bundle)
        before = dict(queue._get(self.db, 'changed-source-job')[0])
        self.now += 3600
        fixture.add_version(self.db, 'fy26-results', self.snapshots['fy26-results']['text'] +
                            '\nA later substantive synthetic disclosure.', at=self.now - 5)
        with self.assertRaisesRegex(ValueError, 'substantive'):
            self.enqueue(bundle, 'new-stale-job')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_queue_jobs').fetchone()[0], 1)
        with patch.object(curation, 'load_reviewed', side_effect=AssertionError('Frozen jobs do not reload curation')):
            self.enqueue(bundle)
            self.assertEqual(dict(queue._get(self.db, 'changed-source-job')[0]), before)
            self.tick()
        state = inv.get(self.db, self.investigation_id)
        self.assertEqual(state['snapshots'], self.snapshots)
        self.assertNotIn('later substantive', state['snapshots']['fy26-results']['text'])
        self.assertEqual(len(self.calls), 1)
        with self.assertRaisesRegex(ValueError, 'collision'):
            queue.enqueue(self.db, 'changed-source-job', 'A different question', bundle_id=bundle['bundle_id'],
                          due=fixture.NOW, deadline=fixture.NOW + 21600, root=self.root)

    def test_freshness_check_holds_writer_lock_and_failed_admission_rolls_back_atomically(self):
        bundle = self.prepare()
        self.approve(bundle)
        approval = tuple(self.db.execute('SELECT * FROM curation_reviews').fetchone())
        self.db.execute('''CREATE TEMP TRIGGER fail_synthetic_queue_insert
            BEFORE INSERT ON research_queue_jobs BEGIN SELECT RAISE(ABORT,'synthetic crash'); END''')
        original = curation.load_reviewed
        checked = []
        def verify_transaction(db, *args, **kwargs):
            self.assertTrue(db.in_transaction)
            result = original(db, *args, **kwargs)
            self.assertTrue(db.in_transaction)
            with closing(sqlite3.connect(self.path, timeout=0)) as competitor:
                with self.assertRaisesRegex(sqlite3.OperationalError, 'locked'):
                    competitor.execute('UPDATE source_watch_schedule SET next_check=next_check+1')
                competitor.rollback()
            checked.append(True)
            return result
        with patch.object(curation, 'load_reviewed', side_effect=verify_transaction), \
                self.assertRaisesRegex(sqlite3.IntegrityError, 'synthetic crash'):
            self.enqueue(bundle)
        self.assertEqual(checked, [True])
        self.assertFalse(self.db.in_transaction)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_queue_jobs').fetchone()[0], 0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_queue_events').fetchone()[0], 0)
        self.assertEqual(tuple(self.db.execute('SELECT * FROM curation_reviews').fetchone()), approval)
        self.assertEqual(self.calls, [])
        self.db.execute('DROP TRIGGER fail_synthetic_queue_insert')
        self.enqueue(bundle)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_queue_jobs').fetchone()[0], 1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM research_queue_events').fetchone()[0], 1)


if __name__ == '__main__':
    unittest.main()
