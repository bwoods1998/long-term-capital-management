"""Synthetic cloud-tool bundles and backend binding; no provider or network calls."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import investigator as agent
import portfolio as ledger
import research_sources as sources
from scripts import research_tools_guest as guest
import test_investigator as fixtures

ROOT = Path(__file__).resolve().parents[1]


class CloudToolsGuestTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.packet = ledger.load_packet()
        self.packet['id'] = 'synthetic-cloud-case'
        self.packet['facts'] = [
            {'id': 'cash', 'label': 'Operating cash flow', 'value': 700, 'unit': 'USD millions',
             'period': 'FY2026', 'source_id': 'fy26-results'},
            {'id': 'spend', 'label': 'Cash property spending', 'value': 300, 'unit': 'USD millions',
             'period': 'FY2026', 'source_id': 'fy26-results'},
        ]
        self.snapshots = {}
        text = 'Synthetic FY2026 cash flow is 700 and cash property spending is 300, in USD millions. '
        for name in sources.SOURCE_REGISTRY:
            self.snapshots[name] = {**sources.allowed_source(name), 'fetched_at': '2026-09-12T20:00:00Z',
                'text': text * 30, 'sha256': hashlib.sha256((text * 30).encode()).hexdigest()}
        files = {'packet.json': json.dumps(self.packet).encode(),
                 **{'sources/' + name + '.json': json.dumps(value).encode()
                    for name, value in self.snapshots.items()},
                 'research_sources.py': (ROOT / 'research_sources.py').read_bytes(),
                 'scripts/research_tools_guest.py': (ROOT / 'scripts/research_tools_guest.py').read_bytes()}
        self.manifest = {'schema_version': 1, 'source_ids': sorted(self.snapshots), 'files': []}
        for name, raw in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            self.manifest['files'].append({'path': name, 'bytes': len(raw),
                                          'sha256': hashlib.sha256(raw).hexdigest()})
        self.freeze_manifest()
        mocked = patch.object(sources, '_download', side_effect=AssertionError('No network'))
        mocked.start(); self.addCleanup(mocked.stop)

    def freeze_manifest(self):
        raw = json.dumps(self.manifest, sort_keys=True).encode()
        (self.root / 'manifest.json').write_bytes(raw)
        self.manifest_sha = hashlib.sha256(raw).hexdigest()

    def request(self, name='calculate', args=None, key='a' * 64):
        return {'schema_version': 1, 'call_key': key, 'name': name,
            'args': args if args is not None else {'operation': 'subtract', 'left_id': 'cash', 'right_id': 'spend'},
            'cutoff': '2026-09-12', 'manifest_sha256': self.manifest_sha}

    def receipt_path(self, request):
        return self.root / 'receipts' / (request['call_key'] + '.json')

    def test_calculation_preserves_exact_units_period_and_frozen_operand_provenance(self):
        result = guest.execute(self.root, self.request())
        self.assertTrue(result['success'])
        self.assertEqual({k: result['result'][k] for k in ('value', 'unit', 'period')},
                         {'value': '400', 'unit': 'USD millions', 'period': 'FY2026'})
        self.assertEqual([v['evidence_id'] for v in result['result']['provenance']], ['cash', 'spend'])
        self.assertTrue(all(v['sha256'] == self.snapshots['fy26-results']['sha256']
                            for v in result['result']['provenance']))
        self.assertEqual(result['result_sha256'], guest.digest(result['result']))

    def test_source_citations_are_exact_slices_of_frozen_text(self):
        result = guest.execute(self.root, self.request('read_source',
            {'source_id': 'fy26-call', 'query': 'cash property spending'}))
        self.assertTrue(result['success'])
        self.assertTrue(result['result']['passages'])
        source = self.snapshots['fy26-call']
        for passage in result['result']['passages']:
            self.assertEqual(passage['text'], source['text'][passage['start']:passage['end']])
            self.assertEqual(passage['passage_id'],
                f"p:{source['sha256'][:24]}:{passage['start']}:{passage['end']}")

    def test_unregistered_network_and_shell_requests_return_sanitized_failures(self):
        attacks = [('shell', {'command': 'PRIVATE_ATTACK'}),
                   ('exec', {'command': 'PRIVATE_ATTACK'}),
                   ('web_search', {'url': 'https://example.com/PRIVATE_ATTACK'}),
                   ('read_source', {'source_id': 'https://localhost/PRIVATE_ATTACK', 'query': 'cash'})]
        with patch('subprocess.run', side_effect=AssertionError('No shell')), \
                patch('os.system', side_effect=AssertionError('No shell')):
            for index, (name, args) in enumerate(attacks):
                receipt = guest.execute(self.root, self.request(name, args, hashlib.sha256(str(index).encode()).hexdigest()))
                self.assertFalse(receipt['success'])
                self.assertNotIn('PRIVATE_ATTACK', json.dumps(receipt))

    def test_identical_call_returns_same_receipt_without_dispatch_or_rewrite(self):
        request = self.request()
        first = guest.execute(self.root, request)
        path = self.receipt_path(request)
        before = (path.read_bytes(), path.stat().st_mtime_ns)
        with patch.object(sources, 'dispatch', side_effect=AssertionError('No repeated execution')):
            second = guest.execute(self.root, deepcopy(request))
        self.assertEqual(first, second)
        self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), before)

    def test_same_call_with_changed_arguments_fails_without_overwriting_receipt(self):
        request = self.request(); guest.execute(self.root, request)
        path = self.receipt_path(request); before = path.read_bytes()
        request['args']['operation'] = 'ratio'
        with patch.object(sources, 'dispatch', side_effect=AssertionError('No conflicting execution')):
            with self.assertRaises(ValueError):
                guest.execute(self.root, request)
        self.assertEqual(path.read_bytes(), before)

    def test_new_python_process_recovers_persisted_receipt_without_dispatch(self):
        request = self.request(); first = guest.execute(self.root, request)
        program = ('import json,sys; from pathlib import Path; from unittest.mock import patch; '
                   'from scripts import research_tools_guest as g; '
                   'p=patch.object(g.sources,"dispatch",side_effect=AssertionError("No rerun")); p.start(); '
                   'print(json.dumps(g.execute(Path(sys.argv[1]),json.load(sys.stdin)),sort_keys=True))')
        result = subprocess.run([sys.executable, '-c', program, str(self.root)],
            input=json.dumps(request), text=True, capture_output=True, cwd=ROOT, timeout=10, check=True)
        self.assertEqual(json.loads(result.stdout), first)

    def test_manifest_identity_and_frozen_file_tamper_fail_even_with_saved_receipt(self):
        request = self.request(); guest.execute(self.root, request)
        manifest = self.root / 'manifest.json'; original = manifest.read_bytes()
        manifest.write_bytes(original + b' ')
        with self.assertRaises(ValueError): guest.execute(self.root, request)
        manifest.write_bytes(original)
        (self.root / 'packet.json').write_text('{}')
        with self.assertRaises(ValueError): guest.execute(self.root, request)

    def test_consumed_evidence_must_be_listed_in_manifest(self):
        for omitted in ('packet.json', 'sources/fy26-call.json'):
            with self.subTest(omitted=omitted):
                original = deepcopy(self.manifest)
                self.manifest['files'] = [x for x in self.manifest['files'] if x['path'] != omitted]
                self.freeze_manifest()
                with self.assertRaises(ValueError):
                    guest.execute(self.root, self.request(key=hashlib.sha256(omitted.encode()).hexdigest()))
                self.manifest = original; self.freeze_manifest()

    def test_receipt_identity_and_success_cannot_be_changed_independently(self):
        request = self.request(); first = guest.execute(self.root, request)
        path = self.receipt_path(request)
        for field, value in [('call_key', 'b' * 64), ('manifest_sha256', 'c' * 64),
                             ('schema_version', 2), ('success', 'true')]:
            with self.subTest(field=field):
                changed = {**first, field: value}; path.write_text(json.dumps(changed))
                with self.assertRaises(ValueError): guest.execute(self.root, request)
        path.write_text(json.dumps(first))
        self.assertEqual(guest.execute(self.root, request), first)

    def test_future_source_cutoff_and_symlinked_sources_are_rejected(self):
        request = self.request(); request['cutoff'] = '2026-07-28'
        with self.assertRaises(ValueError): guest.execute(self.root, request)
        folder = self.root / 'sources'; moved = self.root / 'elsewhere'
        folder.rename(moved); folder.symlink_to(moved, target_is_directory=True)
        with self.assertRaises(ValueError): guest.execute(self.root, self.request())


class CloudBackendBindingTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.InvestigatorTests()
        self.addCleanup(self.fixture.doCleanups); self.fixture.setUp()
        self.db = self.fixture.db
        self.descriptor = {'kind': 'sailbox-tools-v1', 'manifest_sha256': 'a' * 64}
        self.identifier = agent.start(self.db, tool_backend=self.descriptor)

    def test_cloud_bound_run_cannot_advance_with_default_or_wrong_store_before_paid_api(self):
        before = agent.get(self.db, self.identifier)
        for store in (None, self.fixture, Mock(descriptor={**self.descriptor, 'manifest_sha256': 'b' * 64})):
            with self.subTest(store=type(store).__name__), \
                    patch.object(ledger, 'preflight_task', side_effect=AssertionError('No preflight')), \
                    patch.object(ledger, 'reserve_task', side_effect=AssertionError('No admission')), \
                    patch.object(ledger, 'api', side_effect=AssertionError('No paid API')):
                with self.assertRaisesRegex(ValueError, 'frozen research tool backend'):
                    agent.advance(self.db, self.identifier, store)
        self.assertEqual(agent.get(self.db, self.identifier), before)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 0)

    def test_correct_backend_receives_frozen_packet_snapshots_cutoff_and_call_identity(self):
        state = agent.get(self.db, self.identifier)
        store = Mock(descriptor=deepcopy(self.descriptor))
        store.capture.side_effect = self.fixture.capture
        store.dispatch.side_effect = lambda name, args, packet, snapshots, **kw: sources.dispatch(
            name, args, packet, snapshots, cutoff=kw['cutoff'])
        args = {'source_id': 'fy26-call', 'query': 'lease classification'}
        result = agent._tool(state, {'name': 'read_source', 'arguments': json.dumps(args),
                                     'call_id': 'call_frozen_source'}, store)
        self.assertTrue(result['passages'])
        store.capture.assert_called_once_with('fy26-call', cutoff=state['cutoff'])
        store.dispatch.assert_called_once_with('read_source', args, state['packet'], state['snapshots'],
                                              cutoff=state['cutoff'], call_id='call_frozen_source')
        self.assertEqual(set(state['passages']), {x['passage_id'] for x in result['passages']})
        self.assertEqual(self.fixture.calls, [])


if __name__ == '__main__':
    unittest.main()
