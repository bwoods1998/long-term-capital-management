"""Synthetic isolated captures: no real cache, accounts, model calls or publication."""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import uuid

import portfolio as p
import research_sources as sources
import source_watch as watch
import source_curation as c

NOW = datetime.fromisoformat('2026-09-13T12:00:00+00:00').timestamp()


def passage(text, quote, start=0):
    index = text.index(quote, start)
    return {'start': index, 'end': index + len(quote), 'text': quote}


def synthetic_text(packet, source_id, trace='a'):
    lines = ['SYNTHETIC OFFLINE TEST ONLY', 'This is the Trace Id: ' + trace * 32]
    for fact in packet['facts']:
        if fact['source_id'] != source_id or fact['id'].startswith('cash-after'):
            continue
        number = f"{fact['value']:,}"
        if fact['id'].startswith('ppe-'):
            number = '(' + number + ')'
        lines.append(f"{fact['id']} | {fact['unit']} | {fact['period']} | {number}")
    lines += [item['text'] for item in packet['context'] if item['source_id'] == source_id]
    return '\n'.join(lines)


def make_provenance(packet, snapshots):
    """Helper for the synthetic_text fixture format, never a real source curator."""
    result = []
    for fact in packet['facts']:
        text = snapshots[fact['source_id']]['text']
        derived = fact['id'].startswith('cash-after')
        period = fact['period']
        year = period[-4:]
        origin = 'ocf-' + year if derived else fact['id']
        start = text.index(origin + ' | ')
        entry = {'kind': 'fact', 'evidence_id': fact['id'], 'source_id': fact['source_id'],
            'snapshot_sha256': snapshots[fact['source_id']]['sha256'],
            'operation': 'subtract' if derived else 'negate' if fact['id'].startswith('ppe-') else 'identity',
            'reported_number': None, 'operands': ['ocf-' + year, 'ppe-' + year] if derived else [],
            'unit': {'value': fact['unit'], 'passage': passage(text, fact['unit'], start)},
            'period': {'value': period, 'passage': passage(text, period, start)}}
        if not derived:
            token = f"{fact['value']:,}"
            if fact['id'].startswith('ppe-'):
                token = '(' + token + ')'
            entry['reported_number'] = passage(text, token, start)
        result.append(entry)
    for item in packet['context']:
        snapshot = snapshots[item['source_id']]
        result.append({'kind': 'context', 'evidence_id': item['id'], 'source_id': item['source_id'],
                       'snapshot_sha256': snapshot['sha256'], 'passages': [passage(snapshot['text'], item['text'])]})
    return result


def add_version(db, source_id, text, *, at, baseline=False, accepted=False, observe=True):
    snapshot = {**sources.allowed_source(source_id), 'fetched_at': p.iso(at), 'text': text,
                'sha256': hashlib.sha256(text.encode()).hexdigest()}
    identifier = str(uuid.uuid4())
    with db:
        db.execute('INSERT INTO source_watch_versions VALUES(?,?,?,?,?,?)',
                   (identifier, source_id, snapshot['sha256'], at, int(baseline), p.encoded(snapshot)))
        if observe:
            db.execute('INSERT INTO source_watch_observations VALUES(?,?,?,?,?,?,?)',
                       (str(uuid.uuid4()), source_id, at, at + 1, 'baseline_match' if baseline else 'new_candidate',
                        identifier, watch.COMPARISON_VERSION))
        if accepted:
            db.execute('INSERT INTO source_watch_reviews VALUES(?,?,?,?)',
                       (identifier, at + 2, 'Synthetic source reviewer', 'accept'))
    return identifier, snapshot


def make_fixture(db):
    watch.initialize(db)
    prior = p.load_packet()
    prior['evidence_as_of'] = '2026-09-13'
    packet = deepcopy(prior)
    values = {'ocf-2026': 190000, 'cash-after-ppe-2026': 74052}
    for fact in packet['facts']:
        fact['value'] = values.get(fact['id'], fact['value'])
    versions, snapshots = {}, {}
    for source_id in sources.SOURCE_REGISTRY:
        with db:
            db.execute('INSERT INTO source_watch_schedule VALUES(?,?,?,0)',
                       (source_id, p.digest(sources.allowed_source(source_id)), 0))
        identifier, snapshot = add_version(db, source_id, synthetic_text(prior, source_id), at=NOW-100, baseline=True)
        if source_id == 'fy26-results':
            identifier, snapshot = add_version(db, source_id, synthetic_text(packet, source_id, 'b'), at=NOW-60, accepted=True)
        versions[source_id], snapshots[source_id] = identifier, snapshot
    return {'prior_packet': prior, 'packet': packet, 'source_versions': versions,
            'provenance': make_provenance(packet, snapshots)}, snapshots


class CurationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = p.database(Path(self.tmp.name) / 'ledger.sqlite')
        self.addCleanup(self.db.close)
        self.args, self.snapshots = make_fixture(self.db)
        self.clock = patch.object(c.time, 'time', return_value=NOW)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.no_api = patch.object(p, 'api', side_effect=AssertionError('No paid calls'))
        self.no_api.start()
        self.addCleanup(self.no_api.stop)
        self.no_network = patch.object(sources, '_download', side_effect=AssertionError('No network'))
        self.no_network.start()
        self.addCleanup(self.no_network.stop)

    def prepare(self, key='synthetic-change'):
        return c.prepare(self.db, key, **self.args)

    def approved(self):
        bundle = self.prepare()
        receipt = c.review(self.db, bundle['bundle_id'], 'approve', 'Synthetic fact reviewer', expected_sha256=bundle['sha256'])
        return bundle, receipt

    def load(self, bundle, **kwargs):
        return c.load_reviewed(self.db, bundle['bundle_id'], as_of=p.iso(NOW), **kwargs)

    def test_separate_approval_binds_every_source_and_exact_derived_fact(self):
        bundle = self.prepare()
        with self.assertRaises(ValueError):
            self.load(bundle)
        receipt = c.review(self.db, bundle['bundle_id'], 'approve', 'Synthetic fact reviewer', expected_sha256=bundle['sha256'])
        result = self.load(bundle)
        self.assertEqual(result['packet'], self.args['packet'])
        self.assertEqual(result['snapshots'], self.snapshots)
        self.assertEqual(result['receipt'], receipt)
        self.assertEqual(receipt['prior_packet_sha256'], p.digest(self.args['prior_packet']))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 0)
        self.assertIsNone(p.current(self.db))
        self.assertEqual(self.prepare()['bundle_id'], bundle['bundle_id'])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM curation_bundles').fetchone()[0], 1)

    def test_read_preserves_callers_transaction_and_can_be_rolled_back(self):
        bundle, _ = self.approved()
        self.db.execute('BEGIN IMMEDIATE')
        with patch.object(c, 'initialize', side_effect=AssertionError('Read must not initialize')):
            self.load(bundle)
        self.assertTrue(self.db.in_transaction)
        self.db.rollback()

    def test_candidate_acceptance_does_not_bless_stale_retained_values(self):
        for fact in self.args['packet']['facts']:
            if fact['id'] == 'ocf-2026':
                fact['value'] = 182935
        with self.assertRaisesRegex(ValueError, 'financial value'):
            self.prepare()

    def test_pending_rejected_wrong_source_and_metadata_only_candidates_fail(self):
        for state in ('pending', 'rejected', 'wrong-source', 'metadata-only'):
            with self.subTest(state=state):
                args = deepcopy(self.args)
                identifier, snapshot = add_version(self.db, 'fy26-results',
                    synthetic_text(args['prior_packet'] if state == 'metadata-only' else args['packet'],
                                   'fy26-results', str(len(state))[-1]), at=NOW-10, accepted=state=='metadata-only')
                if state == 'rejected':
                    with self.db:
                        self.db.execute('INSERT INTO source_watch_reviews VALUES(?,?,?,?)',
                                        (identifier, NOW-5, 'Synthetic reviewer', 'reject'))
                args['source_versions']['fy26-results'] = args['source_versions']['fy26-call'] if state == 'wrong-source' else identifier
                args['provenance'] = make_provenance(args['packet'], {**self.snapshots, 'fy26-results': snapshot}) if state != 'metadata-only' else args['provenance']
                with self.assertRaises(ValueError):
                    c.prepare(self.db, state, **args)

    def test_metadata_variant_current_but_substantive_change_and_reversion_stale(self):
        bundle, _ = self.approved()
        text = self.snapshots['fy26-results']['text'].replace('b'*32, 'c'*32)
        add_version(self.db, 'fy26-results', text, at=NOW-10)
        self.assertEqual(self.load(bundle)['snapshots'], self.snapshots)
        text += '\nChanged financial guidance'
        add_version(self.db, 'fy26-results', text, at=NOW-5)
        with self.assertRaisesRegex(ValueError, 'substantive'):
            self.load(bundle)
        self.assertEqual(self.load(bundle, require_current=False)['snapshots'], self.snapshots)
        # A fresh curation key must not silently reuse the stale evidence either.
        with self.assertRaises(ValueError):
            self.prepare('new-stale-key')

    def test_metadata_only_selection_fails_even_beside_another_substantive_source(self):
        identifier, snapshot = add_version(self.db, 'fy26-call',
            self.snapshots['fy26-call']['text'].replace('a'*32, 'c'*32), at=NOW-10, accepted=True)
        self.args['source_versions']['fy26-call'] = identifier
        self.args['provenance'] = make_provenance(self.args['packet'], {**self.snapshots, 'fy26-call': snapshot})
        with self.assertRaisesRegex(ValueError, 'metadata-only'):
            self.prepare()

    def test_reversion_to_the_baseline_is_a_new_substantive_state(self):
        bundle, _ = self.approved()
        baseline = self.db.execute("SELECT id FROM source_watch_versions WHERE source_id='fy26-results' AND baseline=1").fetchone()
        with self.db:
            self.db.execute('INSERT INTO source_watch_observations VALUES(?,?,?,?,?,?,?)',
                (str(uuid.uuid4()), 'fy26-results', NOW-4, NOW-3, 'baseline_match', baseline['id'], watch.COMPARISON_VERSION))
        with self.assertRaisesRegex(ValueError, 'substantive'):
            self.load(bundle)
        self.load(bundle, require_current=False)

    def test_approval_rechecks_freshness_and_hash(self):
        bundle = self.prepare()
        with self.assertRaises(ValueError):
            c.review(self.db, bundle['bundle_id'], 'approve', 'Reviewer', expected_sha256='a'*64)
        add_version(self.db, 'fy26-results', self.snapshots['fy26-results']['text'] + '\nNew disclosure', at=NOW-3)
        with self.assertRaises(ValueError):
            c.review(self.db, bundle['bundle_id'], 'approve', 'Reviewer', expected_sha256=bundle['sha256'])
        c.review(self.db, bundle['bundle_id'], 'reject', 'Reviewer', expected_sha256=bundle['sha256'])
        with self.assertRaises(ValueError):
            self.load(bundle)

    def test_missing_provenance_wrong_sha_offsets_quote_and_partial_sources_fail(self):
        for fault in ('missing', 'sha', 'offset', 'quote', 'partial'):
            with self.subTest(fault=fault):
                args = deepcopy(self.args)
                entry = args['provenance'][0]
                if fault == 'missing': args['provenance'].pop()
                if fault == 'sha': entry['snapshot_sha256'] = 'f'*64
                if fault == 'offset': entry['reported_number']['start'] += 1
                if fault == 'quote': entry['reported_number']['text'] = '190001'
                if fault == 'partial': args['source_versions'].pop('fy26-call')
                with self.assertRaises(ValueError):
                    c.prepare(self.db, fault, **args)

    def test_unit_period_sign_wrong_arithmetic_cycles_and_numeric_substrings_fail(self):
        for fault in ('unit', 'period', 'sign', 'arithmetic', 'cycle', 'substring'):
            with self.subTest(fault=fault):
                args = deepcopy(self.args)
                entries = {entry['evidence_id']: entry for entry in args['provenance']}
                if fault in ('unit', 'period'): entries['ocf-2026'][fault]['value'] = 'wrong'
                if fault == 'sign': entries['ppe-2026']['operation'] = 'identity'
                if fault == 'arithmetic': entries['cash-after-ppe-2026']['operation'] = 'add'
                if fault == 'cycle': entries['cash-after-ppe-2026']['operands'][0] = 'cash-after-ppe-2026'
                if fault == 'substring':
                    span = entries['ppe-2026']['reported_number']
                    span.update(start=span['start']+1, end=span['end']-1, text=span['text'][1:-1])
                with self.assertRaises(ValueError):
                    c.prepare(self.db, fault, **args)

    def test_consistently_recomputed_numbers_cannot_hide_missing_digits_or_sign(self):
        for fault in ('leading-digit', 'parentheses'):
            with self.subTest(fault=fault):
                args = deepcopy(self.args)
                entries = {item['evidence_id']: item for item in args['provenance']}
                facts = {item['id']: item for item in args['packet']['facts']}
                if fault == 'leading-digit':
                    span = entries['ocf-2026']['reported_number']
                    span.update(start=span['start']+1, text=span['text'][1:])
                    facts['ocf-2026']['value'] = 90000
                    facts['cash-after-ppe-2026']['value'] = 90000-115948
                else:
                    entry = entries['ppe-2026']
                    span = entry['reported_number']
                    span.update(start=span['start']+1, end=span['end']-1, text=span['text'][1:-1])
                    entry['operation'] = 'identity'  # Arithmetic now matches, but source sign was hidden.
                with self.assertRaisesRegex(ValueError, 'complete signed numeric token'):
                    c.prepare(self.db, fault, **args)

    def test_exponent_or_unsupported_sign_cannot_be_sliced_into_a_plain_number(self):
        for text, token in [('19e3', '19'), ('−190', '190'), ('1.90', '90')]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                c._reported(passage(text, token), text)

    def test_cross_company_dates_and_future_observation_fail(self):
        for fault in ('company', 'identity', 'date', 'future'):
            with self.subTest(fault=fault):
                args = deepcopy(self.args)
                if fault == 'company': args['packet']['company'] = 'Different company'
                if fault == 'identity': args['packet']['id'] = 'different-thesis'
                if fault == 'date': args['packet']['evidence_as_of'] = '2026-07-29'
                if fault == 'future':
                    identifier, _ = add_version(self.db, 'fy26-results', self.snapshots['fy26-results']['text']+'\nFuture', at=NOW+10, accepted=True)
                    args['source_versions']['fy26-results'] = identifier
                with self.assertRaises(ValueError):
                    c.prepare(self.db, fault, **args)

    def test_receipt_tampering_and_future_review_fail_pure_validation(self):
        _, receipt = self.approved()
        for fault in ('hash', 'packet', 'snapshot', 'future', 'reviewer', 'extra'):
            with self.subTest(fault=fault):
                changed = deepcopy(receipt)
                if fault == 'hash': changed['sha256'] = '0'*64
                if fault == 'packet': changed['packet_sha256'] = '0'*64
                if fault == 'snapshot': changed['source_sha256']['fy26-results'] = '0'*64
                if fault == 'future': changed['review']['reviewed_at'] = p.iso(NOW+1)
                if fault == 'reviewer': changed['review']['reviewer'] = ''
                if fault == 'extra': changed['extra'] = True
                if fault != 'hash': changed['sha256'] = p.digest({k:v for k,v in changed.items() if k != 'sha256'})
                with self.assertRaises(ValueError):
                    c.validate_receipt(changed, packet=self.args['packet'], snapshots=self.snapshots,
                        evidence_cutoff='2026-09-13', as_of=p.iso(NOW))

    def test_same_second_preparation_review_and_read_are_valid(self):
        with patch.object(c.time, 'time', return_value=NOW+0.25):
            bundle = self.prepare()
        with patch.object(c.time, 'time', return_value=NOW+0.75):
            c.review(self.db, bundle['bundle_id'], 'approve', 'Reviewer', expected_sha256=bundle['sha256'])
        self.load(bundle)

    def test_midnight_crossing_capture_requires_its_completion_day(self):
        started = datetime.fromisoformat('2026-09-13T23:59:59+00:00').timestamp()
        observation_id = str(uuid.uuid4())
        identifier, snapshot = add_version(self.db, 'fy26-results',
            synthetic_text(self.args['packet'], 'fy26-results', 'c'),
            at=started, observe=False)
        with self.db:
            self.db.execute('INSERT INTO source_watch_observations VALUES(?,?,?,?,?,?,?)',
                (observation_id, 'fy26-results', started, started+21,
                 'new_candidate', identifier, watch.COMPARISON_VERSION))
            self.db.execute('INSERT INTO source_watch_reviews VALUES(?,?,?,?)',
                (identifier, started+22, 'Synthetic source reviewer', 'accept'))
        self.args['source_versions']['fy26-results'] = identifier
        self.args['provenance'] = make_provenance(self.args['packet'],
            {**self.snapshots, 'fy26-results': snapshot})
        with patch.object(c.time, 'time', return_value=started+23):
            with self.assertRaisesRegex(ValueError, 'completed after the checked evidence date'):
                self.prepare()
            self.args['packet']['evidence_as_of'] = '2026-09-14'
            bundle, _ = self.approved()
            result = c.load_reviewed(self.db, bundle['bundle_id'], as_of=p.iso(started+23))
            _, body = c._body(self.db, bundle['bundle_id'], started+23, False)
        self.assertEqual(result['evidence_cutoff'], '2026-09-14')
        self.assertEqual(body['watch_identities']['fy26-results']['observation'],
            {'id': observation_id, 'started': started, 'finished': started+21,
             'state': 'new_candidate', 'comparison_version': watch.COMPARISON_VERSION})
        self.assertIsNone(body['watch_identities']['fy26-call']['observation'])

    def test_consistent_unit_or_period_changes_cannot_cross_derived_operand_scope(self):
        for field in ('unit', 'period'):
            with self.subTest(field=field):
                args = deepcopy(self.args)
                fact = next(item for item in args['packet']['facts'] if item['id'] == 'ocf-2026')
                entry = next(item for item in args['provenance'] if item['evidence_id'] == 'ocf-2026')
                fact[field] = entry[field]['value'] = 'different checked scope'
                with self.assertRaisesRegex(ValueError, 'share source, period and unit'):
                    c.prepare(self.db, field, **args)

    def test_accepted_source_and_review_storage_tampering_is_detected(self):
        bundle, _ = self.approved()
        self.db.execute('DROP TRIGGER immutable_watch_versions_update')
        self.db.execute('UPDATE source_watch_versions SET sha256=? WHERE id=?',
                        ('f'*64, self.args['source_versions']['fy26-results']))
        with self.assertRaises(ValueError):
            self.load(bundle)
        self.db.rollback()
        self.db.execute('DROP TRIGGER keep_curation_reviews_update')
        self.db.execute('UPDATE curation_reviews SET receipt_sha256=?', ('e'*64,))
        with self.assertRaises(ValueError):
            self.load(bundle)

    def test_immutable_storage_and_same_key_changed_input_fail(self):
        bundle, _ = self.approved()
        for table in ('curation_bundles', 'curation_reviews'):
            with self.assertRaises(sqlite3.IntegrityError):
                self.db.execute('DELETE FROM ' + table)
            self.db.rollback()
        self.args['packet']['question'] += '?'
        with self.assertRaises(ValueError):
            self.prepare()
        with self.assertRaises(sqlite3.IntegrityError):
            c.review(self.db, bundle['bundle_id'], 'approve', 'Second reviewer', expected_sha256=bundle['sha256'])

    def test_stored_json_size_duplicate_fields_and_tampering_fail(self):
        bundle, _ = self.approved()
        with self.assertRaises(ValueError):
            c._json('{"x":1,"x":2}', 100)
        with self.assertRaises(ValueError):
            c._json({'x':'a'*101}, 100)
        # Deliberate isolated-file corruption even after an attacker drops a trigger.
        self.db.execute('DROP TRIGGER keep_curation_bundles_update')
        self.db.execute('UPDATE curation_bundles SET body_sha256=?', ('0'*64,))
        with self.assertRaises(ValueError):
            self.load(bundle)


if __name__ == '__main__':
    unittest.main()
