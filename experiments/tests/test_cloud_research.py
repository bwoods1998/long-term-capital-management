"""Offline cloud-controller lifecycle and evidence tests with an in-memory fake SDK."""
from contextlib import nullcontext
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import threading
import unittest
from unittest.mock import Mock, patch

import cloud_research as cloud
import investigator
import portfolio as ledger
import research_sources as sources
from scripts import research_tools_guest as guest
import test_cloud_tools_guest as guest_fixtures

PROJECT = Path(__file__).resolve().parents[1]
RATES = {'vcpu_second_usd_nanos': 4167, 'memory_gib_second_usd_nanos': 2223,
         'state_disk_gib_second_usd_nanos': 195, 's_creation_usd_nanos': 5000000}
ISOLATED = {'status': 'running', 'egress_policy': {'document': {'no_network': True}},
            'visibility': 'private', 'memory_mib': 2048, 'vcpu_count': 1,
            'state_disk_size_gib': 8, 'volume_mounts': []}


class CloudResearchTests(unittest.TestCase):
    def setUp(self):
        self.fixture = guest_fixtures.CloudToolsGuestTests()
        self.addCleanup(self.fixture.doCleanups); self.fixture.setUp()
        self.project = self.fixture.root / 'project'
        self.project.mkdir()
        for name in cloud.FILES:
            target = self.project / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((PROJECT / name).read_bytes())
        self.sessions = self.project / '.data' / 'cloud-research'
        self.remote, self.exec_handles = {}, {}
        self.computations = 0
        self.box = SimpleNamespace(fs=SimpleNamespace(write=Mock(side_effect=self.remote_write),
                                                     read=Mock(side_effect=lambda path: self.remote[path])),
                                   exec=Mock(side_effect=self.remote_exec))
        self.sdk = SimpleNamespace(App=SimpleNamespace(find=Mock(return_value=SimpleNamespace(id='app_synthetic'))),
                                   Sailbox=SimpleNamespace(from_id=Mock(return_value=self.box)))
        self.api = Mock(side_effect=self.provider)
        for target, name, options in [
            (cloud, 'ROOT', {'new': self.project}),
            (cloud, 'SESSION_ROOT', {'new': self.sessions}),
            (cloud.ledger, 'load_packet', {'side_effect': lambda: deepcopy(self.fixture.packet)}),
            (cloud.ledger, 'credential_fingerprint', {'return_value': 'synthetic-credential-fingerprint'}),
            (sources.SourceStore, 'capture', {'side_effect': lambda key, cutoff=None: deepcopy(self.fixture.snapshots[key])}),
            (cloud.sandbox, 'api', {'new': self.api}),
            (cloud.subprocess, 'Popen', {'return_value': SimpleNamespace(pid=12345)}),
        ]:
            mocked = patch.object(target, name, **options)
            mocked.start(); self.addCleanup(mocked.stop)
        mocked = patch.dict('sys.modules', {'sail': self.sdk})
        mocked.start(); self.addCleanup(mocked.stop)
        prepared = cloud.prepare('synthetic-case')
        self.directory = Path(prepared['session'])

    def remote_write(self, path, raw, **kwargs):
        self.remote[path] = raw

    def provider(self, method, route, body=None, request_id=None):
        if method == 'GET' and route == '/v1/sailboxes/spend': return {'rates': RATES}
        if method == 'POST' and route == '/v1/sailboxes': return {'sailbox_id': 'sb_synthetic'}
        if route.endswith('/listeners'): return {'data': []}
        if method == 'GET' and route == '/v1/sailboxes/sb_synthetic': return deepcopy(ISOLATED)
        if method == 'POST' and route.endswith(('/resume', '/sleep')): return {}
        raise AssertionError('Unexpected mocked provider operation: ' + method + ' ' + route)

    def ready(self):
        _, state = cloud._load(self.directory)
        state.update(phase='ready', started=cloud.time.time(), deadline=cloud.time.time() + 3600,
                     sailbox_id='sb_synthetic', app_id='app_synthetic', isolation_verified=True)
        cloud._write(self.directory / 'state.json', state)
        for name, raw in cloud._bundle(self.directory, state).items():
            self.remote[cloud.REMOTE + '/' + name] = raw
        return state

    def remote_exec(self, command, **kwargs):
        key = kwargs['idempotency_key']
        if key not in self.exec_handles:
            self.computations += 1
            call_key = command.rsplit(' ', 1)[-1]
            request = json.loads(self.remote[cloud.REMOTE + '/requests/' + call_key + '.json'])
            result = sources.dispatch(request['name'], request['args'], self.fixture.packet,
                                      self.fixture.snapshots, cutoff=request['cutoff'])
            receipt = {'schema_version': 1, 'call_key': call_key,
                'manifest_sha256': request['manifest_sha256'], 'request_sha256': ledger.digest(request),
                'success': True, 'result': result, 'result_sha256': ledger.digest(result)}
            self.remote[cloud.REMOTE + '/receipts/' + call_key + '.json'] = json.dumps(receipt).encode()
            self.exec_handles[key] = SimpleNamespace(wait=Mock(return_value=SimpleNamespace(exit_code=0, timed_out=False)))
        return self.exec_handles[key]

    def dispatch(self, store, args=None, call_id='call_financial'):
        return store.dispatch('calculate', args or {'operation': 'subtract', 'left_id': 'cash', 'right_id': 'spend'},
            self.fixture.packet, self.fixture.snapshots, cutoff='2026-09-12', call_id=call_id)

    def test_prepare_has_no_api_and_uploads_only_frozen_public_code_and_evidence(self):
        self.api.assert_not_called(); self.sdk.App.find.assert_not_called()
        _, state = cloud._load(self.directory)
        files = cloud._bundle(self.directory, state)
        self.assertEqual(set(files), {'manifest.json', 'packet.json', *cloud.FILES,
            'sources/fy26-call.json', 'sources/fy26-results.json'})
        serialized = b''.join(files.values())
        self.assertNotIn(b'synthetic-credential-fingerprint', serialized)
        self.assertNotIn(state['operations']['create'].encode(), serialized)
        self.assertNotIn(state['investigation_id'].encode(), serialized)
        self.assertFalse(any(token in name for name in files for token in ('.env', 'sqlite', 'schwab', '.data')))

    def test_frozen_byte_change_or_added_private_file_blocks_before_create(self):
        target = self.directory / 'bundle' / 'packet.json'; original = target.read_bytes()
        target.write_bytes(original + b' ')
        with self.assertRaises(ValueError): cloud.create(self.directory)
        self.api.assert_not_called()
        target.write_bytes(original)
        path = self.directory / 'bundle' / 'manifest.json'
        manifest = json.loads(path.read_text())
        manifest['files'].append({'path': '.env', 'bytes': 1, 'sha256': 'a' * 64})
        raw = ledger.encoded(manifest).encode(); path.write_bytes(raw)
        _, state = cloud._load(self.directory); state['manifest_sha256'] = cloud.sandbox.sha(raw)
        cloud._write(self.directory / 'state.json', state)
        with self.assertRaises(ValueError): cloud.create(self.directory)
        self.api.assert_not_called()

    def test_remote_uploaded_bytes_are_read_back_before_ready(self):
        result = cloud.create(self.directory)
        self.assertEqual(result['phase'], 'ready')
        reads = {call.args[0] for call in self.box.fs.read.call_args_list}
        self.assertEqual(reads, set(self.remote))
        self.assertEqual(self.box.exec.call_count, 0)

    def test_corrupt_upload_triggers_cleanup_and_never_marks_ready(self):
        self.box.fs.write.side_effect = lambda path, raw, **kw: self.remote_write(path, raw + b'CORRUPT', **kw)
        with patch.object(cloud.sandbox, '_cleanup', return_value=[{'sailbox_id': 'sb_synthetic', 'status': 'terminated'}]), \
                patch.object(cloud, 'finish') as finish:
            with self.assertRaises(ValueError): cloud.create(self.directory)
            finish.assert_called_once_with(self.directory)
        _, state = cloud._load(self.directory)
        self.assertNotEqual(state['phase'], 'ready')

    def test_missing_isolation_or_creation_in_progress_blocks_before_inference(self):
        state = self.ready()
        for change in ({'isolation_verified': False}, {'phase': 'creating'}, {'sailbox_id': None}):
            with self.subTest(change=change):
                cloud._write(self.directory / 'state.json', {**state, **change})
                with patch.object(ledger, 'database', side_effect=AssertionError('No research ledger admission')):
                    with self.assertRaises(ValueError): cloud.advance(self.directory)
        self.api.assert_not_called()

    def test_uncertain_create_is_never_repeated(self):
        def uncertain(method, route, body=None, request_id=None):
            if method == 'POST' and route == '/v1/sailboxes': raise TimeoutError('synthetic uncertainty')
            return self.provider(method, route, body, request_id)
        self.api.side_effect = uncertain
        with patch.object(cloud, 'finish') as finish:
            with self.assertRaises(TimeoutError): cloud.create(self.directory)
            finish.assert_called_once()
        saved = cloud._load(self.directory)[1]
        with self.assertRaises(ValueError): cloud.create(self.directory)
        posts = [call for call in self.api.call_args_list if call.args[:2] == ('POST', '/v1/sailboxes')]
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0].args[3], saved['operations']['create'])

    def test_tool_recovery_uses_original_exec_key_and_identical_checked_receipt(self):
        self.ready(); store = cloud.ToolStore(self.directory)
        original = self.box.exec.side_effect
        first = True
        def timeout_once(command, **kwargs):
            nonlocal first
            handle = original(command, **kwargs)
            if first:
                first = False
                handle.wait.side_effect = [TimeoutError('Remote acceptance unknown'), SimpleNamespace(exit_code=0, timed_out=False)]
            return handle
        self.box.exec.side_effect = timeout_once
        with self.assertRaises(TimeoutError): self.dispatch(store)
        result = self.dispatch(cloud.ToolStore(self.directory))
        self.assertEqual(result['value'], '400')
        self.assertEqual(self.computations, 1)
        self.assertEqual(self.box.exec.call_args_list[0].kwargs['idempotency_key'],
                         self.box.exec.call_args_list[1].kwargs['idempotency_key'])
        self.api.reset_mock(); self.box.exec.reset_mock()
        self.assertEqual(self.dispatch(cloud.ToolStore(self.directory)), result)
        self.api.assert_not_called(); self.box.exec.assert_not_called()

    def test_same_call_changed_arguments_or_packet_never_buys_new_exec(self):
        self.ready(); store = cloud.ToolStore(self.directory); self.dispatch(store)
        count = self.box.exec.call_count
        with self.assertRaises(ValueError):
            self.dispatch(cloud.ToolStore(self.directory), {'operation': 'ratio', 'left_id': 'cash', 'right_id': 'spend'})
        packet = deepcopy(self.fixture.packet); packet['facts'][0]['value'] = 701
        with self.assertRaises(ValueError):
            store.dispatch('calculate', {'operation': 'subtract', 'left_id': 'cash', 'right_id': 'spend'},
                packet, self.fixture.snapshots, cutoff='2026-09-12', call_id='new-call')
        self.assertEqual(self.box.exec.call_count, count)

    def test_local_receipt_tamper_fails_against_deterministic_result(self):
        self.ready(); self.dispatch(cloud.ToolStore(self.directory))
        path = next((self.directory / 'tools').glob('*.json'))
        record = json.loads(path.read_text())
        record['receipt']['result']['value'] = '999'
        record['receipt']['result_sha256'] = ledger.digest(record['receipt']['result'])
        path.write_text(json.dumps(record))
        self.box.exec.reset_mock()
        with self.assertRaises(ValueError): self.dispatch(cloud.ToolStore(self.directory))
        self.box.exec.assert_not_called()

    def test_changed_credential_or_deadline_blocks_backend_before_remote_access(self):
        state = self.ready()
        with patch.object(ledger, 'credential_fingerprint', return_value='other'):
            with self.assertRaises(ValueError): cloud.ToolStore(self.directory)
        state['deadline'] = cloud.time.time() - 1; cloud._write(self.directory / 'state.json', state)
        with self.assertRaises(ValueError): cloud.ToolStore(self.directory)
        self.api.assert_not_called()

    def test_identical_evidence_in_another_session_cannot_resume_this_investigation(self):
        first_state = self.ready()
        first_store = cloud.ToolStore(self.directory)
        second = cloud.prepare('second-synthetic-case')
        self.directory = Path(second['session'])
        self.ready()
        second_store = cloud.ToolStore(self.directory)
        # The test isolates execution identity: every source/code/packet byte is
        # the same, so equal evidence is insufficient to authorize another VM.
        for name in first_store.files.keys() - {'manifest.json'}:
            self.assertEqual(first_store.files[name], second_store.files[name])
        db = ledger.database(self.project / 'binding-ledger.sqlite')
        self.addCleanup(db.close)
        identifier = investigator.start(db, packet=deepcopy(self.fixture.packet),
            investigation_id=first_state['investigation_id'], tool_backend=first_store.descriptor)
        before = investigator.get(db, identifier)
        with patch.object(ledger, 'preflight_task', side_effect=AssertionError('Wrong worker reached preflight')), \
                patch.object(ledger, 'reserve_task', side_effect=AssertionError('Wrong worker reached admission')), \
                patch.object(ledger, 'api', side_effect=AssertionError('Wrong worker reached model API')):
            with self.assertRaisesRegex(ValueError, 'frozen research tool backend'):
                investigator.advance(db, identifier, second_store)
        self.assertEqual(investigator.get(db, identifier), before)
        self.assertEqual(db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 0)
        self.box.exec.assert_not_called()

    def test_concurrent_session_creation_cannot_share_the_same_compute_admission(self):
        second = Path(cloud.prepare('concurrent-synthetic-case')['session'])
        entered, release = threading.Event(), threading.Event()
        rate_reads = []

        def paused_first_admission(method, route, body=None, request_id=None):
            if method == 'GET' and route == '/v1/sailboxes/spend':
                rate_reads.append(route)
                if len(rate_reads) == 1:
                    entered.set()
                    if not release.wait(5):
                        raise AssertionError('Test did not release first admission')
            return self.provider(method, route, body, request_id)

        self.api.side_effect = paused_first_admission
        with ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(cloud.create, self.directory)
            try:
                self.assertTrue(entered.wait(5))
                with self.assertRaises(ValueError):
                    cloud.create(second)
            finally:
                release.set()
            self.assertEqual(first.result(timeout=5)['phase'], 'ready')
        self.assertEqual(len(rate_reads), 1)
        self.assertEqual(cloud._load(second)[1]['phase'], 'prepared')
        creations = [call for call in self.api.call_args_list
                     if call.args[:2] == ('POST', '/v1/sailboxes')]
        self.assertEqual(len(creations), 1)

    def test_advance_uses_the_existing_single_local_ledger_and_binds_backend(self):
        state = self.ready()
        db = ledger.database(self.project / 'test-ledger.sqlite'); self.addCleanup(db.close)
        trace = Mock()
        with patch.object(ledger, 'database', return_value=db) as database, \
                patch.object(cloud.tracking, 'run', return_value=nullcontext(trace)), \
                patch.object(investigator, 'advance', return_value={'phase': 'research'}) as advance:
            result = cloud.advance(self.directory)
            database.assert_called_once_with()
            self.assertEqual(result, {'phase': 'research'})
            self.assertIs(advance.call_args.args[0], db)
            self.assertEqual(advance.call_args.args[1], state['investigation_id'])
        saved = investigator.get(db, state['investigation_id'])
        self.assertEqual(saved['packet'], self.fixture.packet)
        self.assertEqual(saved['tool_backend'], {'kind': 'sailbox-tools-v1', 'manifest_sha256': state['manifest_sha256']})
        self.assertEqual(db.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 0)
        self.assertFalse(any('sqlite' in name for name in self.remote))

    def test_ambiguous_resume_reuses_its_original_lifecycle_operation(self):
        self.ready()
        posts = []
        def resume_uncertain(method, route, body=None, request_id=None):
            if method == 'GET': return {**ISOLATED, 'status': 'sleeping'}
            if route.endswith('/resume'):
                posts.append(request_id); raise TimeoutError('Unknown resume')
            raise AssertionError('Unexpected operation')
        self.api.side_effect = resume_uncertain
        for _ in range(2):
            with self.assertRaises(TimeoutError): cloud.ToolStore(self.directory)._awake()
        self.assertEqual(len(posts), 2)
        self.assertEqual(posts[0], posts[1])


if __name__ == '__main__':
    unittest.main()
