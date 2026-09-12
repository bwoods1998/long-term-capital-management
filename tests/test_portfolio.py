import concurrent.futures
from contextlib import closing
import copy
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

import portfolio as p


class PortfolioTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'portfolio.sqlite'
        fingerprint = patch.object(p, 'credential_fingerprint', return_value='synthetic-key-fingerprint')
        fingerprint.start()
        self.addCleanup(fingerprint.stop)
        self.packet = {
            'schema_version': 1, 'id': 'example', 'symbol': 'EX', 'company': 'Example',
            'question': 'Can investment generate cash?', 'evidence_as_of': '2026-09-12',
            'sources': [{'id': 'annual', 'title': 'Annual report',
                         'url': 'https://example.com/annual', 'published_at': '2026-07-29'}],
            'facts': [{'id': 'revenue', 'label': 'Revenue', 'value': 123,
                       'unit': 'USD millions', 'period': 'FY2026', 'source_id': 'annual'}],
            'context': [{'id': 'investment', 'text': 'Investment increased.', 'source_id': 'annual'}]}
        self.answer = {
            'headline': 'Growth needs a cash flow test',
            'summary': 'Investment is rising, but the packet does not establish its incremental cash return.',
            'stance': 'watch',
            'claims': [{'text': 'Investment increased.', 'evidence_ids': ['investment']}],
            'assumptions': ['Investment can support future demand.'],
            'invalidation': ['Demand weakens while investment remains elevated.'],
            'open_questions': ['What cash return does the additional investment produce?'],
            'next_review': 'Review the next earnings release for investment and cash conversion.',
            'changes': ['Initial research view based on the supplied evidence.']}

    def reserve(self, db, packet=None):
        packet = packet or self.packet
        parent = p.current(db)
        return p.reserve(db, p.build_request(packet, p.memory(parent)), packet,
                         'PRIVATE_PREDICTION_DO_NOT_EXPORT', parent['id'] if parent else None)

    def database(self, path):
        db = p.database(path)
        self.addCleanup(db.close)
        return db

    def response(self, status='completed', answer=None, response_id='resp_test'):
        return {'id': response_id, 'status': status,
                'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(answer or self.answer)}]}],
                'usage': {'input_tokens': 1000, 'output_tokens': 300,
                          'input_tokens_details': {'cached_tokens': 100}},
                'private_account_marker': 'DO_NOT_EXPORT_PROVIDER_RESPONSE'}

    def finish(self, db, rid, answer=None):
        with patch.object(p, 'api', return_value=self.response(answer=answer)):
            p.execute(db, rid, poll_seconds=0)
        return db.execute('SELECT id FROM revisions WHERE run_id=?', (rid,)).fetchone()['id']

    def test_validation_rejects_bad_citations_numbers_extra_fields_and_overlong_text(self):
        p.validate_answer(self.answer, self.packet)
        cases = []
        answer = copy.deepcopy(self.answer)
        answer['claims'][0]['evidence_ids'] = ['made-up-source']
        cases.append(answer)
        answer = copy.deepcopy(self.answer)
        answer['summary'] = 'Revenue rose 20%.'
        cases.append(answer)
        answer = copy.deepcopy(self.answer)
        answer['summary'] = 'Revenue rose by a billion dollars.'
        cases.append(answer)
        answer = copy.deepcopy(self.answer)
        answer['account_number'] = 'PRIVATE'
        cases.append(answer)
        answer = copy.deepcopy(self.answer)
        answer['headline'] = 'x' * 121
        cases.append(answer)
        for answer in cases:
            with self.subTest(answer=answer), self.assertRaises(ValueError):
                p.validate_answer(answer, self.packet)

    def test_text_transport_retains_local_contract_and_bounded_spending(self):
        request = p.build_request(self.packet)
        self.assertEqual(request['max_output_tokens'], 16384)
        self.assertEqual(request['model'], 'deepseek-ai/DeepSeek-V4-Pro-0813')
        self.assertEqual(request['metadata']['completion_window'], 'flex')
        self.assertEqual(request['reasoning']['effort'], 'medium')
        self.assertEqual(request['text'], {'format': {'type': 'text'}})
        self.assertIn('OUTPUT SHAPE:', request['input'])
        schema = p.answer_schema({'investment', 'revenue'})['properties']
        self.assertEqual(schema['summary']['maxLength'], 600)
        self.assertEqual(schema['changes']['minItems'], 1)
        self.assertEqual(schema['claims']['maxItems'], 3)
        self.assertNotRegex('2026', schema['changes']['items']['pattern'])
        self.assertEqual(schema['claims']['items']['properties']['evidence_ids']['items']['enum'],
                         ['investment', 'revenue'])
        conservative_cost = (Decimal(p.MAX_REQUEST_BYTES) * Decimal(p.RATES['input']) +
                             Decimal(p.MAX_OUTPUT_TOKENS) * Decimal(p.RATES['output'])) / 1_000_000
        self.assertLess(conservative_cost, Decimal(p.RESERVE_CENTS) / 100)
        request['max_output_tokens'] += 1
        with self.assertRaises(ValueError):
            p.validate_envelope(request)

    def test_uncertain_request_survives_restart_with_same_body_and_key(self):
        with self.database(self.path) as db:
            rid = self.reserve(db)
            with patch.object(p, 'api', side_effect=RuntimeError('PRIVATE_PROVIDER_BODY')) as first:
                p.execute(db, rid, poll_seconds=0)
            self.assertNotIn('PRIVATE_PROVIDER_BODY', p.status(db, rid)['runs'][0]['error'])
        with self.database(self.path) as db:
            with patch.object(p, 'api', return_value=self.response()) as second:
                p.execute(db, rid, poll_seconds=0)
            self.assertEqual(first.call_args, second.call_args)
            self.assertEqual(db.execute('SELECT SUM(reserved_cents) FROM runs').fetchone()[0], p.RESERVE_CENTS)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM revisions').fetchone()[0], 1)

    def test_ambiguous_request_after_idempotency_window_is_not_retried(self):
        with self.database(self.path) as db:
            rid = self.reserve(db)
            with db:
                db.execute('UPDATE runs SET created=? WHERE id=?', (time.time() - 24 * 3600, rid))
            with patch.object(p, 'api') as api:
                result = p.execute(db, rid)
                api.assert_not_called()
            self.assertIn('23h', result['runs'][0]['error'])

    def test_key_rotation_cannot_duplicate_an_uncertain_paid_submission(self):
        with self.database(self.path) as db:
            rid = self.reserve(db)
            with patch.object(p, 'api', side_effect=RuntimeError('unknown')):
                p.execute(db, rid)
            with patch.object(p, 'credential_fingerprint', return_value='different-key'), patch.object(p, 'api') as api:
                p.execute(db, rid)
                api.assert_not_called()
            self.assertEqual(db.execute('SELECT SUM(reserved_cents) FROM runs').fetchone()[0], p.RESERVE_CENTS)

    def test_known_response_uses_get_and_incomplete_never_redrafts(self):
        with self.database(self.path) as db:
            rid = self.reserve(db)
            with db:
                db.execute('UPDATE runs SET response_id=? WHERE id=?', ('resp_known', rid))
            with patch.object(p, 'api', return_value=self.response(status='incomplete', response_id='resp_known')) as api:
                p.execute(db, rid, poll_seconds=0)
                p.execute(db, rid, poll_seconds=0)
                api.assert_called_once_with('GET', '/v1/responses/resp_known')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM revisions').fetchone()[0], 0)
            with self.assertRaises(ValueError):
                p.public_snapshot(db)

    def test_invalid_completed_response_is_not_published_or_resubmitted(self):
        answer = copy.deepcopy(self.answer)
        answer['claims'][0]['evidence_ids'] = ['bogus']
        with self.database(self.path) as db:
            rid = self.reserve(db)
            with patch.object(p, 'api', return_value=self.response(answer=answer)) as api:
                p.execute(db, rid, poll_seconds=0)
                p.execute(db, rid, poll_seconds=0)
                self.assertEqual(api.call_count, 1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM revisions').fetchone()[0], 0)
            self.assertIn('failed local thesis validation', p.status(db, rid)['runs'][0]['error'])

    def test_concurrent_budget_reservation_never_exceeds_cap(self):
        with self.database(self.path):
            pass
        def attempt(_):
            with closing(p.database(self.path)) as db, db:
                try:
                    self.reserve(db)
                    return True
                except ValueError:
                    return False
        with patch.object(p, 'BUDGET_CENTS', p.RESERVE_CENTS):
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                self.assertEqual(sum(pool.map(attempt, range(8))), 1)

    def test_only_reviewed_chain_exports_and_stale_drafts_cannot_replace_head(self):
        with self.database(self.path) as db:
            first = self.reserve(db)
            competing = self.reserve(db)
            first_revision = self.finish(db, first)
            competing_revision = self.finish(db, competing)
            with self.assertRaises(ValueError):
                p.public_snapshot(db)
            p.review(db, first_revision, 'Builder')
            with self.assertRaises(ValueError):
                p.review(db, competing_revision, 'Builder')
            initial = p.public_snapshot(db)
            self.assertEqual(len(initial['thesis']['revisions']), 1)
            packet = copy.deepcopy(self.packet)
            packet['facts'][0]['value'] = 456
            next_run = self.reserve(db, packet)
            next_revision = self.finish(db, next_run)
            # A new draft alone cannot change the public snapshot.
            self.assertEqual(p.public_snapshot(db)['thesis']['revisions'][0]['facts'][0]['value'], 123)
            p.review(db, next_revision, 'Builder')
            result = p.public_snapshot(db)
            self.assertEqual([r['facts'][0]['value'] for r in result['thesis']['revisions']], [123, 456])
            self.assertEqual(result['thesis']['revisions'][1]['parent_id'], first_revision)
            # Re-reviewing an already reviewed ancestor must not rewind the head.
            p.review(db, first_revision, 'Builder')
            self.assertEqual(p.current(db)['id'], next_revision)
            public = json.dumps(result)
            for private in ['PRIVATE_PREDICTION', 'DO_NOT_EXPORT_PROVIDER_RESPONSE', 'response_id',
                            'prediction', 'request', 'packet_sha256', 'error', 'run_id']:
                self.assertNotIn(private, public)
            self.assertEqual(result['portfolio'], {'status': 'not_connected'})
            self.assertEqual(result['costs']['billed_usd'], None)
            with patch.object(p, 'MODEL', 'another-default'), patch.object(p, 'COMPLETION_WINDOW', 'asap'):
                provenance = p.public_snapshot(db)['thesis']['revisions'][0]['research']
            self.assertEqual(provenance, {'model': 'deepseek-ai/DeepSeek-V4-Pro-0813',
                                          'completion_window': 'flex', 'reasoning_effort': 'medium'})

    def test_revision_is_immutable_and_full_prior_evidence_enters_next_request(self):
        with self.database(self.path) as db:
            rid = self.reserve(db)
            revision = self.finish(db, rid)
            p.review(db, revision, 'Builder')
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('UPDATE revisions SET answer_json=? WHERE id=?', ('{}', revision))
            memory = p.memory(p.current(db))
            self.assertEqual(memory['evidence_packet'], self.packet)
            self.assertEqual(memory['thesis'], self.answer)
            request = p.build_request(self.packet, memory)
            self.assertIn(revision, request['input'])
            self.assertLess(len(p.encoded(request).encode()), p.MAX_REQUEST_BYTES)

    def test_cost_includes_failed_runs_and_unknown_cost_is_not_zero(self):
        with self.database(self.path) as db:
            rid = self.reserve(db)
            rev = self.finish(db, rid)
            p.review(db, rev, 'Builder')
            self.assertEqual(Decimal(p.public_snapshot(db)['costs']['estimated_usd']), Decimal('0.0011902'))
            uncertain = self.reserve(db)
            with patch.object(p, 'api', side_effect=RuntimeError('unknown')):
                p.execute(db, uncertain)
            result = p.public_snapshot(db)
            self.assertIsNone(result['costs']['estimated_usd'])
            self.assertEqual(result['costs']['unknown_runs'], 1)
            self.assertEqual(result['costs']['reserved_usd'], '0.4')

    def test_malformed_or_provisional_accounting_is_unknown_not_zero(self):
        with self.database(self.path) as db:
            rid = self.reserve(db)
            for usage in [['invalid'], {'input_tokens_details': ['invalid']}]:
                response = self.response()
                response['usage'] = usage
                with db:
                    db.execute('UPDATE runs SET response=? WHERE id=?', (json.dumps(response), rid))
                self.assertIsNone(p.run_cost(p.get_run(db, rid)))
            response = self.response(status='in_progress')
            with db:
                db.execute('UPDATE runs SET response=? WHERE id=?', (json.dumps(response), rid))
            self.assertIsNone(p.run_cost(p.get_run(db, rid)))

    def test_zero_estimate_exports_plain_decimal_without_exponent(self):
        with self.database(self.path) as db:
            rid = self.reserve(db)
            rev = self.finish(db, rid)
            p.review(db, rev, 'Builder')
            response = self.response()
            response['usage'] = {'input_tokens': 0, 'output_tokens': 0}
            with db:
                db.execute('UPDATE runs SET response=? WHERE id=?', (json.dumps(response), rid))
            estimate = p.public_snapshot(db)['costs']['estimated_usd']
            self.assertNotIn('E', estimate)
            self.assertEqual(Decimal(estimate), Decimal(0))

    def test_export_is_atomic_allowlist_and_rejects_private_database_paths(self):
        with self.database(self.path) as db:
            rid = self.reserve(db)
            rev = self.finish(db, rid)
            p.review(db, rev, 'Builder')
            destination = Path(self.tmp.name) / 'public/portfolio.json'
            p.export(db, destination)
            self.assertEqual(json.loads(destination.read_text())['schema_version'], 1)
            self.assertEqual(list(destination.parent.glob('*.tmp-*')), [])
            with self.assertRaises(ValueError):
                p.export(db, Path(self.tmp.name) / '.data/leak.json')
            with self.assertRaises(ValueError):
                p.export(db, self.path)


if __name__ == '__main__':
    unittest.main()
