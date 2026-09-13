"""Isolated CLI checks: no actual source approval, secrets, network or paid work."""
from contextlib import closing, redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import portfolio as p
import research_sources as sources
import source_curation as c
from scripts import curate_sources as cli
from test_source_curation import NOW, add_version, make_fixture


class CurationCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'ledger.sqlite'
        self.db = p.database(self.path)
        self.addCleanup(self.db.close)
        self.inputs, self.snapshots = make_fixture(self.db)
        self.input_path = Path(self.tmp.name) / 'input.json'
        self.input_path.write_text(json.dumps(self.inputs), encoding='utf-8')
        for owner, name in ((p, 'api'), (p, 'load_api_key'), (sources, '_download')):
            guard = patch.object(owner, name, side_effect=AssertionError('No external operation'))
            guard.start()
            self.addCleanup(guard.stop)
        clock = patch.object(cli.time, 'time', return_value=NOW)
        self.clock = clock.start()
        self.addCleanup(clock.stop)

    def run_cli(self, *args, failure=False, database=None):
        output, errors = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(errors):
            argv = ['--database', str(database or self.path), *map(str, args)]
            if failure:
                with self.assertRaises(SystemExit) as stopped:
                    cli.main(argv)
                self.assertEqual(stopped.exception.code, 1)
            else:
                cli.main(argv)
        if failure:
            self.assertEqual(output.getvalue(), '')
            self.assertEqual(errors.getvalue(), 'Curation command failed. Check the local input, saved digest, source decisions, and ledger integrity.\n')
            return errors.getvalue()
        self.assertEqual(errors.getvalue(), '')
        return json.loads(output.getvalue())

    def prepare(self):
        return self.run_cli('prepare', 'synthetic-change', '--input', self.input_path)

    def approve(self, bundle):
        return self.run_cli('review', bundle['bundle_id'], 'approve', '--sha256', bundle['sha256'],
                            '--reviewer', 'Synthetic fact reviewer')

    def original_tables(self):
        tables = [row['name'] for row in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")
                  if not row['name'].startswith('curation_')]
        return {table: [tuple(row) for row in self.db.execute('SELECT * FROM ' + table)] for table in tables}

    def test_prepare_inspect_review_are_separate_and_preserve_other_records(self):
        before = self.original_tables()
        with patch.object(p, 'database', side_effect=AssertionError('CLI must not initialize the research ledger')):
            bundle = self.prepare()
            inspected = self.run_cli('inspect', bundle['bundle_id'])
            self.assertEqual(inspected['saved_state'], 'pending_review')
            self.assertFalse(inspected['source_check']['approved_and_current'])
            self.assertEqual(inspected['packet'], self.inputs['packet'])
            self.assertEqual(inspected['prior_packet'], self.inputs['prior_packet'])
            self.assertEqual(inspected['provenance'], self.inputs['provenance'])
            self.assertEqual(inspected['sha256'], bundle['sha256'])
            self.assertEqual(inspected['hashes']['packet'], p.digest(self.inputs['packet']))
            self.assertTrue(any(item['source_review'] for item in inspected['sources']))
            self.assertNotIn('SYNTHETIC OFFLINE TEST ONLY', json.dumps(inspected))
            self.assertNotIn('b' * 32, json.dumps(inspected))
            for source in inspected['sources']:
                self.assertIn('published_at', source)
                self.assertIn('fetched_at', source)
                self.assertIn('first_observed_at', source)
                self.assertEqual(source['observation_finished_at'],
                                 None if source['baseline'] else p.iso(NOW - 59))
                self.assertNotIn('text', source)
            receipt = self.approve(bundle)
            approved = self.run_cli('inspect', bundle['bundle_id'])
            self.assertEqual(approved['saved_state'], 'approved')
            self.assertTrue(approved['source_check']['approved_and_current'])
            self.assertEqual(approved['hashes']['review_receipt'], receipt['sha256'])
        self.assertEqual(before, self.original_tables())

    def test_status_without_curation_tables_does_not_create_schema_or_files(self):
        before = self.path.read_bytes()
        files = set(Path(self.tmp.name).iterdir())
        with patch.object(c, 'initialize', side_effect=AssertionError('Read must not initialize')):
            self.assertEqual(self.run_cli('status')['bundles'], [])
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(files, set(Path(self.tmp.name).iterdir()))
        self.assertIsNone(self.db.execute("SELECT name FROM sqlite_master WHERE name='curation_bundles'").fetchone())

    def test_source_metadata_includes_baseline_ids_without_text_reviewers_or_approval(self):
        before = self.path.read_bytes()
        with patch.object(c, 'initialize', side_effect=AssertionError('Read must not initialize')):
            result = self.run_cli('sources')
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(result['scope'], 'source_metadata_only')
        selected = {source['id']: source for source in result['sources']}
        self.assertEqual(set(selected), set(self.inputs['source_versions']))
        for source_id, version_id in self.inputs['source_versions'].items():
            self.assertIn(version_id, [item['version_id'] for item in selected[source_id]['versions']])
            self.assertEqual(sum(item['baseline'] for item in selected[source_id]['versions']), 1)
        self.assertEqual(selected['fy26-results']['versions'][1]['saved_source_decision'], 'accept')
        serialized = json.dumps(result)
        for excluded in ('Synthetic source reviewer', 'SYNTHETIC OFFLINE TEST ONLY', 'approved_and_current'):
            self.assertNotIn(excluded, serialized)

    def test_source_list_bounds_output_and_keeps_baseline_with_newest_versions(self):
        new_id, _ = add_version(self.db, 'fy26-results',
            self.snapshots['fy26-results']['text'] + '\nAnother observed version', at=NOW - 10)
        with patch.object(cli, 'MAX_SOURCE_VERSIONS', 2):
            result = self.run_cli('sources')
        selected = next(source for source in result['sources'] if source['id'] == 'fy26-results')
        self.assertEqual(len(selected['versions']), 2)
        self.assertTrue(selected['versions'][0]['baseline'])
        self.assertEqual(selected['versions'][1]['version_id'], new_id)
        self.assertEqual(selected['omitted_versions'], 1)

    def test_inspect_and_status_use_query_only_existing_connections(self):
        bundle = self.prepare()
        self.approve(bundle)
        before = self.path.read_bytes()
        with closing(cli.connect(self.path, readonly=True)) as reader:
            self.assertEqual(reader.execute('PRAGMA query_only').fetchone()[0], 1)
            with patch.object(c, 'initialize', side_effect=AssertionError('Read must not initialize')):
                cli.inspect(reader, bundle['bundle_id'], now=NOW)
                result = cli.status(reader, now=NOW)
            self.assertEqual(len(result['bundles']), 1)
            self.assertEqual(reader.total_changes, 0)
            with self.assertRaises(sqlite3.OperationalError):
                reader.execute('CREATE TABLE forbidden(value)')
        self.assertEqual(before, self.path.read_bytes())

    def test_missing_or_symlinked_database_is_not_created_or_opened(self):
        missing = Path(self.tmp.name) / 'missing.sqlite'
        linked = Path(self.tmp.name) / 'linked.sqlite'
        linked.symlink_to(self.path)
        for database in (missing, linked):
            self.run_cli('status', failure=True, database=database)
            self.run_cli('prepare', 'anything', '--input', self.input_path, failure=True, database=database)
        self.assertFalse(missing.exists())

    def test_wrong_digest_and_repeated_decisions_never_change_review(self):
        bundle = self.prepare()
        self.run_cli('review', bundle['bundle_id'], 'approve', '--sha256', '0' * 64,
                     '--reviewer', 'Synthetic reviewer', failure=True)
        self.assertEqual(self.run_cli('inspect', bundle['bundle_id'])['saved_state'], 'pending_review')
        self.approve(bundle)
        before = self.path.read_bytes()
        self.run_cli('review', bundle['bundle_id'], 'reject', '--sha256', bundle['sha256'],
                     '--reviewer', 'Different reviewer', failure=True)
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(self.run_cli('inspect', bundle['bundle_id'])['saved_state'], 'approved')

    def test_rejected_bundle_remains_inspectable_without_approval(self):
        bundle = self.prepare()
        self.run_cli('review', bundle['bundle_id'], 'reject', '--sha256', bundle['sha256'],
                     '--reviewer', 'Synthetic reviewer')
        inspected = self.run_cli('inspect', bundle['bundle_id'])
        self.assertEqual(inspected['saved_state'], 'rejected')
        self.assertEqual(inspected['review']['decision'], 'reject')
        self.assertFalse(inspected['source_check']['approved_and_current'])

    def test_stale_sources_do_not_erase_saved_approval_and_trace_noise_is_current(self):
        bundle = self.prepare()
        self.approve(bundle)
        text = self.snapshots['fy26-results']['text'].replace('b' * 32, 'c' * 32)
        add_version(self.db, 'fy26-results', text, at=NOW + 10)
        self.clock.return_value = NOW + 20
        self.assertTrue(self.run_cli('inspect', bundle['bundle_id'])['source_check']['approved_and_current'])
        add_version(self.db, 'fy26-results', text + '\nNew financial disclosure', at=NOW + 30)
        self.clock.return_value = NOW + 40
        result = self.run_cli('inspect', bundle['bundle_id'])
        self.assertEqual(result['saved_state'], 'approved')
        self.assertEqual(result['source_check']['freshness'], 'not_current_or_invalid')
        self.assertFalse(result['source_check']['approved_and_current'])
        self.assertEqual(self.run_cli('status')['bundles'][0]['saved_state'], 'approved')

    def test_prepare_same_key_is_idempotent_and_changed_input_collides(self):
        bundle = self.prepare()
        self.assertEqual(self.prepare(), bundle)
        altered = deepcopy(self.inputs)
        altered['packet']['question'] += '?'
        self.input_path.write_text(json.dumps(altered), encoding='utf-8')
        self.run_cli('prepare', 'synthetic-change', '--input', self.input_path, failure=True)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM curation_bundles').fetchone()[0], 1)

    def test_strict_json_rejects_duplicate_fields_extra_missing_and_nonfinite(self):
        for text in ('{"packet":{},"packet":{}}', '{"prior_packet":{"x":1,"x":2}}',
                     '{"x":NaN}', '{"x":1e9999}', '[]', '{"extra":1}',
                     json.dumps({**self.inputs, 'extra': 1}),
                     json.dumps({key: value for key, value in self.inputs.items() if key != 'provenance'})):
            with self.subTest(text=text[:50]):
                self.input_path.write_text(text, encoding='utf-8')
                self.run_cli('prepare', 'invalid', '--input', self.input_path, failure=True)
        self.assertIsNone(self.db.execute("SELECT name FROM sqlite_master WHERE name='curation_bundles'").fetchone())

    def test_input_symlink_directory_fifo_oversize_and_invalid_utf8_fail(self):
        linked = Path(self.tmp.name) / 'linked.json'
        linked.symlink_to(self.input_path)
        fifo = Path(self.tmp.name) / 'pipe.json'
        os.mkfifo(fifo)
        for path in (linked, Path(self.tmp.name), fifo):
            self.run_cli('prepare', 'invalid', '--input', path, failure=True)
        self.input_path.write_bytes(b' ' * (cli.MAX_INPUT_BYTES + 1))
        self.run_cli('prepare', 'invalid', '--input', self.input_path, failure=True)
        self.input_path.write_bytes(b'\xff')
        self.run_cli('prepare', 'invalid', '--input', self.input_path, failure=True)

    def test_corrupted_rejected_receipt_fails_instead_of_reporting_a_valid_decision(self):
        bundle = self.prepare()
        self.run_cli('review', bundle['bundle_id'], 'reject', '--sha256', bundle['sha256'],
                     '--reviewer', 'Synthetic reviewer')
        with self.db:
            self.db.execute('DROP TRIGGER keep_curation_reviews_update')
            self.db.execute("UPDATE curation_reviews SET receipt_sha256=?", ('0' * 64,))
        self.run_cli('inspect', bundle['bundle_id'], failure=True)
        self.run_cli('status', failure=True)

    def test_errors_do_not_print_private_exception_details(self):
        with patch.object(c, 'prepare', side_effect=ValueError('PRIVATE SOURCE BODY OR CREDENTIAL')):
            error = self.run_cli('prepare', 'invalid', '--input', self.input_path, failure=True)
        self.assertNotIn('PRIVATE', error)

    def test_script_launches_from_another_directory_for_read_only_status(self):
        result = subprocess.run([sys.executable, str(cli.ROOT / 'scripts/curate_sources.py'),
                                 '--database', str(self.path), 'status'], cwd=self.tmp.name,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['bundles'], [])


if __name__ == '__main__':
    unittest.main()
