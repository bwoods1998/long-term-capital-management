import contextlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import lab
import sail_tracking as t


class FakeVoyage:
    def __init__(self):
        self.id = 'voy_test'
        self.dashboard_url = 'https://app.sailresearch.com/voyages/voy_test'
        self.status = 'running'
        self.events = []
        self.span_exits = []
        self.flush_fails = False

    def event(self, name, **kwargs):
        self.events.append((name, kwargs))

    def complete(self, **kwargs):
        self.status = 'completed'
        self.event('voyage.completed', **kwargs)

    def fail(self, **kwargs):
        self.status = 'failed'
        self.event('voyage.failed', **kwargs)

    def flush(self, **kwargs):
        if self.flush_fails:
            raise RuntimeError('PRIVATE_PROVIDER_BODY')

    def agent(self, *args, **kwargs):
        return contextlib.nullcontext()

    def span(self, *args, **kwargs):
        outer = self
        class Span:
            def __enter__(self):
                return self

            def __exit__(self, kind, error, tb):
                outer.span_exits.append(str(error))
        return Span()

    def headers(self):
        return {'X-Sail-Voyage-Id': self.id, 'X-Sail-Voyage-Span-Id': 'span_test',
                'X-Sail-Voyage-Agent-Id': 'investigator', 'Authorization': 'PRIVATE_OVERRIDE',
                'Idempotency-Key': 'PRIVATE_OVERRIDE'}


class SailTrackingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.voyage = FakeVoyage()
        self.sdk = SimpleNamespace(voyage=SimpleNamespace(
            create=MagicMock(return_value=self.voyage), attach=MagicMock(return_value=self.voyage)))
        for mocked in [patch.object(t.importlib, 'import_module', return_value=self.sdk),
                       patch.object(lab, 'load_api_key', return_value='sk_SYNTHETIC_PRIVATE_KEY')]:
            mocked.start()
            self.addCleanup(mocked.stop)

    def run_trace(self, **kwargs):
        return t.run('PRIVATE_WORKFLOW_NAME', enabled=True, state_dir=self.directory, **kwargs)

    def state(self):
        return json.loads(next(self.directory.glob('*.json')).read_text())

    def test_disabled_mode_has_no_import_key_lookup_or_files(self):
        with patch.object(t.importlib, 'import_module') as importer, patch.object(lab, 'load_api_key') as key:
            with t.run('test', state_dir=self.directory) as trace:
                with t.stage('investigate'):
                    t.event('model.finished', {'input_tokens': 20})
                    self.assertEqual(t.inference_headers(), {})
                trace.complete()
            importer.assert_not_called()
            key.assert_not_called()
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_resume_attaches_and_does_not_terminate_waiting_workflow(self):
        with self.run_trace() as trace:
            with t.stage('investigate'):
                t.event('model.pending', {'status': 'queued', 'input_tokens': 20})
                self.assertEqual(t.inference_headers()['X-Sail-Voyage-Span-Id'], 'span_test')
                self.assertNotIn('Authorization', t.inference_headers())
            self.assertTrue(trace.dashboard_url.startswith('https://app.sailresearch.com/'))
        self.assertTrue(trace.delivery_confirmed)
        self.assertEqual(self.state()['status'], 'running')
        with self.run_trace() as resumed:
            resumed.complete()
            resumed.complete()
        self.sdk.voyage.create.assert_called_once()
        self.sdk.voyage.attach.assert_called_once_with('voy_test')
        self.assertEqual(sum(name == 'voyage.completed' for name, _ in self.voyage.events), 1)
        self.assertEqual(t.inference_headers(), {})
        self.assertEqual(self.state()['status'], 'completed')
        public_to_provider = json.dumps(self.sdk.voyage.create.call_args.kwargs) + json.dumps(self.voyage.events)
        self.assertNotIn('PRIVATE_WORKFLOW_NAME', public_to_provider)
        self.assertNotIn('SYNTHETIC_PRIVATE_KEY', public_to_provider)
        self.assertEqual(next(self.directory.glob('*.json')).stat().st_mode & 0o777, 0o600)

    def test_exception_prose_never_reaches_sdk_events_or_spans(self):
        with self.assertRaisesRegex(RuntimeError, 'PRIVATE_EXCEPTION'):
            with self.run_trace():
                with t.stage('tool.read-source'):
                    raise RuntimeError('PRIVATE_EXCEPTION sk_SYNTHETIC_PRIVATE_KEY')
        emitted = json.dumps(self.voyage.events + self.voyage.span_exits)
        self.assertNotIn('PRIVATE_EXCEPTION', emitted)
        self.assertNotIn('SYNTHETIC_PRIVATE_KEY', emitted)
        self.assertEqual(self.state()['status'], 'running')
        self.assertTrue(any(name == 'workflow.interrupted' for name, _ in self.voyage.events))

    def test_interrupt_resumes_and_terminal_trace_cannot_accept_new_work(self):
        with self.assertRaises(KeyboardInterrupt):
            with self.run_trace():
                raise KeyboardInterrupt('PRIVATE_INTERRUPT')
        with self.run_trace() as trace:
            trace.complete()
        # The provider may lag behind local terminal intent on the next attach.
        self.voyage.status = 'running'
        with self.run_trace() as terminal:
            self.assertEqual(terminal.state['status'], 'completed')
            self.assertEqual(terminal.voyage_id, 'voy_test')
            with self.assertRaises(ValueError):
                t.event('model.started')
            with self.assertRaises(ValueError):
                t.inference_headers()
            with self.assertRaises(ValueError):
                with t.stage('new-work'):
                    pass
        self.assertEqual(self.state()['status'], 'completed')

    def test_event_payload_rejects_free_text_and_secrets(self):
        with self.run_trace():
            for payload in [{'prompt': 'PRIVATE_PROMPT'}, {'tool': 'sk_PRIVATE'},
                            {'model': 'a model with private prose'}, {'input_tokens': float('nan')}]:
                with self.assertRaises(ValueError):
                    t.event('model.finished', payload)

    def test_ambiguous_create_is_journaled_and_never_blindly_recreated(self):
        self.sdk.voyage.create.side_effect = RuntimeError('PRIVATE_PROVIDER_ERROR')
        for _ in range(2):
            with self.assertRaises(RuntimeError) as caught:
                with self.run_trace():
                    self.fail('Ambiguous telemetry creation must not execute work')
            self.assertNotIn('PRIVATE_PROVIDER_ERROR', str(caught.exception))
        self.sdk.voyage.create.assert_called_once()
        self.assertEqual(self.state()['status'], 'creation_unconfirmed')

    def test_identity_is_saved_before_optional_dashboard_validation(self):
        self.voyage.dashboard_url = 'https://unexpected.example/private'
        with self.assertRaises(RuntimeError):
            with self.run_trace():
                pass
        self.assertEqual(self.state()['voyage_id'], 'voy_test')
        self.assertEqual(self.state()['startup_error'],
                         {'stage': 'dashboard_validation', 'error_type': 'ValueError'})
        self.voyage.dashboard_url = 'https://app.sailresearch.com/voyages/voy_test'
        with self.run_trace():
            pass
        self.sdk.voyage.create.assert_called_once()
        self.sdk.voyage.attach.assert_called_once_with('voy_test')

    def test_startup_diagnostic_records_safe_status_and_network_category(self):
        self.sdk.voyage.create.side_effect = RuntimeError('DNS failure PRIVATE_BODY sk_PRIVATE_KEY')
        with self.assertRaises(RuntimeError):
            with self.run_trace():
                pass
        self.assertEqual(self.state()['startup_error'],
                         {'stage': 'create', 'error_type': 'RuntimeError', 'transport_category': 'dns'})
        self.assertNotIn('PRIVATE_', json.dumps(self.state()))

    def test_flush_failure_and_credential_change_preserve_local_state(self):
        self.voyage.flush_fails = True
        with self.run_trace() as trace:
            trace.complete()
        self.assertFalse(trace.delivery_confirmed)
        self.assertNotIn('PRIVATE_PROVIDER_BODY', json.dumps(self.state()))
        with patch.object(lab, 'load_api_key', return_value='sk_ROTATED'):
            with self.assertRaises(ValueError):
                with self.run_trace():
                    self.fail('Credential rotation must not change trace ownership')
        self.sdk.voyage.attach.assert_not_called()

    def test_environment_restored_and_sdk_uses_transport_credential(self):
        with patch.dict(os.environ, {'SAIL_API_KEY': 'old-key', 'SAIL_AGENT_NAME': 'PRIVATE_NAME'}):
            with self.run_trace():
                self.assertEqual(os.environ['SAIL_API_KEY'], 'sk_SYNTHETIC_PRIVATE_KEY')
                self.assertNotIn('SAIL_AGENT_NAME', os.environ)
            self.assertEqual(os.environ['SAIL_API_KEY'], 'old-key')
            self.assertEqual(os.environ['SAIL_AGENT_NAME'], 'PRIVATE_NAME')

    def test_transport_keeps_auth_idempotency_and_dynamic_trace_headers(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"id":"resp_test"}'
        opener = MagicMock()
        opener.open.return_value = response
        with self.run_trace(), t.stage('investigate'), patch.object(lab, 'build_opener', return_value=opener):
            lab.api('POST', '/v1/responses', {'model': 'synthetic'}, 'retry-uuid')
            request = opener.open.call_args.args[0]
            headers = dict(request.header_items())
            self.assertEqual(headers['Authorization'], 'Bearer sk_SYNTHETIC_PRIVATE_KEY')
            self.assertEqual(headers['Idempotency-key'], 'retry-uuid')
            self.assertEqual(headers['X-sail-voyage-id'], 'voy_test')


@unittest.skipUnless(importlib.util.find_spec('sail'), 'optional Sail SDK is not installed')
class RealSDKContractTests(unittest.TestCase):
    def test_real_sdk_records_safe_span_failures_and_correlates_without_network(self):
        import sail
        voyage = sail.voyage.Voyage(id='voy_offline', _start_background=False)
        trace = t.Trace(voyage=voyage)
        token = t._active.set(trace)
        try:
            with self.assertRaisesRegex(RuntimeError, 'PRIVATE_ORIGINAL'):
                with t.stage('investigate'):
                    headers = t.inference_headers()
                    self.assertEqual(headers['X-Sail-Voyage-Id'], 'voy_offline')
                    self.assertEqual(headers['X-Sail-Voyage-Agent-Id'], 'investigator')
                    self.assertIn('X-Sail-Voyage-Span-Id', headers)
                    t.event('model.finished', {'input_tokens': 10, 'output_tokens': 20})
                    raise RuntimeError('PRIVATE_ORIGINAL')
            events = sail.voyage._buffered_events_for_tests(voyage)
            self.assertTrue(any(item['kind'] == 'span.failed' for item in events))
            self.assertNotIn('PRIVATE_ORIGINAL', json.dumps(events))
        finally:
            t._active.reset(token)


if __name__ == '__main__':
    unittest.main()
