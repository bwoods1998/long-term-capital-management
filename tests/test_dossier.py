"""Offline dossier contracts using synthetic evidence and a mocked provider."""
from contextlib import closing
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import dossier as d
import portfolio as p
import research_sources as sources


class DossierTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'portfolio.sqlite'
        self.db = p.database(self.path)
        self.addCleanup(self.db.close)
        p.set_budget_limit(self.db, 9500)
        self.now = d.datetime.fromisoformat('2026-09-13T03:30:00+00:00').timestamp()
        self.calls = []
        self.response_status = 'completed'
        self.snapshots = {}
        for source_id in sources.SOURCE_REGISTRY:
            text = ('Synthetic source: FY2026 in USD millions. Reported amounts 700 and 31.125. ' * 36)
            self.snapshots[source_id] = {**sources.allowed_source(source_id), 'text': text,
                'fetched_at': p.iso(self.now - 60), 'sha256': hashlib.sha256(text.encode()).hexdigest()}
        self.library = d.passage_library(self.snapshots)
        self.results_ids = [key for key in self.library if key.startswith('fy26-results:')]
        self.call_ids = [key for key in self.library if key.startswith('fy26-call:')]
        self.rubric = {'tasks': {}, 'expected': {},
            'sources': {key: {field: value[field] for field in ('sha256', 'published_at', 'fetched_at', 'url')}
                        for key, value in self.snapshots.items()},
            'source_spans': {key: {'span_sha256': hashlib.sha256(value['text'].encode()).hexdigest()}
                             for key, value in self.library.items()}}
        for theme in d.THEMES:
            evidence = self.results_ids if theme == 'cashflow' else self.call_ids
            self.rubric['tasks'][theme] = {
                'instruction': 'Reconcile the synthetic amounts with all supporting passages.',
                'metrics': [{'id': theme + '-sum', 'unit': 'USD millions', 'period': 'FY2026'}]}
            self.rubric['expected'][theme + '-sum'] = {'value': '731.125', 'unit': 'USD millions',
                'period': 'FY2026', 'required_evidence_groups': [[evidence[0]], [evidence[1]]]}
        for target, name, options in [
            (d.time, 'time', {'side_effect': lambda: self.now}),
            (p, 'credential_fingerprint', {'return_value': 'synthetic-fingerprint'}),
            (p, 'api', {'side_effect': self.api}),
            (p, 'preflight_task', {'return_value': None}),
            (sources.SourceStore, 'capture', {'side_effect': AssertionError('No source network or cache access')}),
        ]:
            mocked = patch.object(target, name, **options)
            mocked.start()
            self.addCleanup(mocked.stop)

    def create(self):
        return d.create(self.db, snapshots=self.snapshots, rubric=self.rubric)

    def report(self, theme='cashflow'):
        ids = self.results_ids if theme == 'cashflow' else self.call_ids
        return {'headline': 'Synthetic numerical bridge',
            'metrics': [{'id': theme + '-sum', 'value': '731.125', 'unit': 'USD millions',
                         'period': 'FY2026', 'evidence_ids': ids}],
            'claims': [{'text': 'The synthetic bridge includes both reported amounts.', 'evidence_ids': ids}],
            'caveats': ['Synthetic evidence does not establish real investment returns.'],
            'next_tests': ['Review the meaning of the source rows.']}

    def response(self, report, identifier='synthetic-response'):
        return {'id': identifier, 'status': 'completed', 'output': [{'type': 'message', 'content': [
            {'type': 'output_text', 'text': json.dumps(report)}]}],
            'usage': {'input_tokens': 1000, 'output_tokens': 200,
                      'input_tokens_details': {'cached_tokens': 0}}}

    def api(self, method, route, body=None, request_id=None, **kwargs):
        self.calls.append((method, route, request_id))
        response = self.response(self.report(), 'resp_' + request_id if method == 'POST' else route.rsplit('/', 1)[-1])
        response['status'] = self.response_status
        if self.response_status != 'completed':
            response['output'] = []
        return response

    def test_create_freezes_protocol_without_spending_and_rejects_duplicate_creation(self):
        identifier = self.create()
        frozen = d.protocol(self.db, identifier)
        self.assertEqual(frozen['max_reservation_cents'], 640)
        self.assertEqual(len(frozen['stages']), 12)
        self.snapshots['fy26-results']['text'] = 'Later source drift'
        self.rubric['expected']['cashflow-sum']['value'] = '99'
        self.assertEqual(d.protocol(self.db, identifier), frozen)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 0)
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.create()
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("UPDATE dossiers SET sha256='corrupt'")
        self.db.rollback()

    def test_expected_answers_are_withheld_from_initial_and_reconciliation_requests(self):
        frozen = d.protocol(self.db, self.create())
        parents = {'cashflow-pro': {'report': self.report(), 'grade': d.grade(self.report(), self.rubric, 'cashflow')}}
        # Parent model output may contain a correct answer; use an incorrect one
        # to prove the hidden expected value is not copied into the next prompt.
        parents['cashflow-pro']['report']['metrics'][0]['value'] = '730'
        for stage in (frozen['stages'][0], frozen['stages'][6]):
            with self.subTest(stage=stage['id']):
                body, _ = d.request(stage, frozen, {} if stage['kind'] == 'analyst' else parents)
                prompt = p.encoded(body)
                self.assertNotIn('731.125', prompt)
                self.assertNotIn('required_evidence_groups', prompt)
                self.assertNotIn('"expected"', prompt)
                self.assertIn('cashflow-sum', prompt)
                self.assertEqual(body['max_output_tokens'], 32768)

    def test_grading_checks_numeric_unit_period_and_every_source_group(self):
        valid = self.report()
        self.assertEqual(d.grade(valid, self.rubric, 'cashflow')['passed'], 1)
        for field, value, error in [('value', '731.126', 'value'), ('unit', 'USD', 'unit'),
                                    ('period', 'FY2025', 'period'),
                                    ('evidence_ids', [self.results_ids[0]], 'source_coverage')]:
            with self.subTest(error=error):
                changed = deepcopy(valid)
                changed['metrics'][0][field] = value
                result = d.grade(changed, self.rubric, 'cashflow')
                self.assertEqual(result['passed'], 0)
                self.assertEqual(result['checks']['cashflow-sum']['errors'], [error])
        equivalent = deepcopy(valid)
        equivalent['metrics'][0]['value'] = '731.1250'
        self.assertEqual(d.grade(equivalent, self.rubric, 'cashflow')['passed'], 1)
        valid['metrics'] = []
        self.assertEqual(d.grade(valid, self.rubric, 'cashflow')['checks']['cashflow-sum']['errors'], ['missing'])

    def test_accepted_request_crash_resumes_exact_id_body_and_allowance(self):
        identifier = self.create()
        self.response_status = 'queued'
        original = p.execute
        def crash(*args, **kwargs):
            original(*args, **kwargs)
            raise KeyboardInterrupt
        with patch.object(p, 'execute', side_effect=crash), self.assertRaises(KeyboardInterrupt):
            d.advance(self.db, identifier)
        before = dict(self.db.execute('SELECT id,request,response_id,reserved_cents FROM runs').fetchone())
        self.assertTrue(before['response_id'])
        self.assertEqual(len(self.calls), 1)
        self.response_status = 'completed'
        with patch.object(d, 'request', side_effect=AssertionError('Recovery must use saved request')), \
                patch.object(d.Path, 'read_bytes', return_value=b'implementation changed after acceptance'):
            with closing(p.database(self.path)) as fresh:
                result = d.advance(fresh, identifier)
        self.assertEqual(self.calls[1], ('GET', '/v1/responses/' + before['response_id'], None))
        self.assertEqual(result['grade'], {'passed': 1, 'total': 1})
        self.assertEqual(dict(self.db.execute('SELECT id,request,response_id,reserved_cents FROM runs').fetchone()), before)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 1)

    def test_crash_after_reservation_before_mapping_reuses_original_run(self):
        identifier = self.create()
        original = p.reserve_task
        def crash(*args, **kwargs):
            original(*args, **kwargs)
            raise KeyboardInterrupt
        with patch.object(p, 'reserve_task', side_effect=crash), self.assertRaises(KeyboardInterrupt):
            d.advance(self.db, identifier)
        before = dict(self.db.execute('SELECT id,request,reserved_cents FROM runs').fetchone())
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM dossier_steps').fetchone()[0], 0)
        self.assertEqual(self.calls, [])
        status = d.status(self.db, identifier)
        self.assertEqual(status['unattached_reservations'], 1)
        self.assertEqual(status['held_usd'], '0.2')
        self.assertEqual(status['known_estimated_usd'], '0')
        self.assertEqual(status['unknown_usage_count'], 1)
        self.assertEqual(status['steps'], [])
        d.advance(self.db, identifier)
        self.assertEqual(dict(self.db.execute('SELECT id,request,reserved_cents FROM runs').fetchone()), before)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 1)
        self.assertEqual(d.status(self.db, identifier)['unattached_reservations'], 0)

    def test_new_requests_reject_implementation_drift_and_wrong_saved_stage_identity(self):
        identifier = self.create()
        with patch.object(d.Path, 'read_bytes', return_value=b'changed implementation'):
            with self.assertRaisesRegex(ValueError, 'implementation changed'):
                d.advance(self.db, identifier)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 0)
        frozen = d.protocol(self.db, identifier)
        stage = frozen['stages'][0]
        body, _ = d.request(stage, frozen, {})
        wrong = p.reserve_task(self.db, body=body, packet=frozen['packet'],
                               task_key='dossier:unrelated:cashflow-pro', purpose='investigate')
        with self.db:
            self.db.execute('INSERT INTO dossier_steps VALUES(?,?,?,?,NULL)',
                            (identifier, stage['id'], wrong, p.digest(body)))
        with self.assertRaisesRegex(ValueError, 'frozen dossier stage'):
            d.advance(self.db, identifier)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 1)

    def test_source_and_passage_hash_mismatch_blocks_creation_before_reservation(self):
        for fault in ('source', 'passage'):
            with self.subTest(fault=fault):
                rubric = deepcopy(self.rubric)
                if fault == 'source':
                    rubric['sources']['fy26-results']['sha256'] = '0' * 64
                else:
                    rubric['source_spans'][self.results_ids[0]]['span_sha256'] = '0' * 64
                with self.assertRaises(ValueError):
                    d.create(self.db, snapshots=self.snapshots, rubric=rubric)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM dossiers').fetchone()[0], 0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 0)
        self.assertEqual(self.calls, [])

    def test_reconciliation_receives_review_spans_but_later_stages_only_parent_citations(self):
        frozen = d.protocol(self.db, self.create())
        review_span, parent_span = self.results_ids[0], self.call_ids[0]
        frozen['rubric']['source_spans'] = {review_span: frozen['rubric']['source_spans'][review_span]}
        candidate = self.report()
        for item in candidate['metrics'] + candidate['claims']:
            item['evidence_ids'] = [parent_span]
        parents = {'earlier-stage': {'report': candidate}}
        reconciliation = next(stage for stage in frozen['stages'] if stage['kind'] == 'reconcile')
        self.assertEqual(set(d._sources_for(reconciliation, frozen, parents)), {review_span, parent_span})
        for kind in ('synthesis', 'critic', 'revision'):
            stage = next(stage for stage in frozen['stages'] if stage['kind'] == kind)
            self.assertEqual(set(d._sources_for(stage, frozen, parents)), {parent_span})

    def test_deadline_and_insufficient_allowance_prevent_admission(self):
        p.set_budget_limit(self.db, 639)
        with self.assertRaisesRegex(ValueError, 'entire dossier'):
            self.create()
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM dossiers').fetchone()[0], 0)
        p.set_budget_limit(self.db, 640)
        identifier = self.create()
        self.now = d.protocol(self.db, identifier)['deadline']
        self.assertEqual(d.advance(self.db, identifier)['state'], 'deadline')
        self.assertEqual(self.calls, [])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 0)

    def test_completed_step_result_cannot_be_replaced_or_deleted(self):
        identifier = self.create()
        d.advance(self.db, identifier)
        row = tuple(self.db.execute('SELECT * FROM dossier_steps').fetchone())
        held = self.db.execute('SELECT SUM(reserved_cents) FROM runs').fetchone()[0]
        for statement in ("UPDATE dossier_steps SET result='{}'", 'DELETE FROM dossier_steps'):
            with self.assertRaises(sqlite3.IntegrityError):
                self.db.execute(statement)
            self.db.rollback()
        self.assertEqual(tuple(self.db.execute('SELECT * FROM dossier_steps').fetchone()), row)
        self.assertEqual(self.db.execute('SELECT SUM(reserved_cents) FROM runs').fetchone()[0], held)
        self.assertIsNone(p.current(self.db))

    def test_report_rejects_unknown_empty_or_excess_citations_and_nonfinite_values(self):
        self.assertEqual(d.parse_report(self.response(self.report()), self.library), self.report())
        for target in ('metrics', 'claims'):
            for citations in ([], ['not-supplied:0:1'], [self.results_ids[0]] * 13):
                with self.subTest(target=target, citations=len(citations)):
                    report = self.report()
                    report[target][0]['evidence_ids'] = citations
                    with self.assertRaises(ValueError):
                        d.parse_report(self.response(report), self.library)
        for value in ('NaN', 'Infinity', '1000000000000001', '7.31125e2', '+731.125', '0731.125'):
            report = self.report()
            report['metrics'][0]['value'] = value
            with self.assertRaises(ValueError):
                d.parse_report(self.response(report), self.library)


if __name__ == '__main__':
    unittest.main()
