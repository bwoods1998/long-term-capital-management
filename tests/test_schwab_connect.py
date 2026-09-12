"""Offline owner workflow and privacy boundaries; no optional SDK required."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import schwab_connect as connect
from schwab_storage import vault
from scripts.setup_schwab import save_credentials, validate_credentials


class ConnectorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.credentials = validate_credentials('test-client', 'test-secret', 'https://127.0.0.1')
        save_credentials(self.root, 'test-client', 'test-secret', 'https://127.0.0.1')

    def metadata(self):
        return {'creation_timestamp': time.time(), 'token': {
            'access_token': 'private-access', 'refresh_token': 'private-refresh',
            'token_type': 'Bearer', 'expires_in': 1800, 'expires_at': time.time() + 1800,
        }}

    def response(self, document, status_code=200):
        body = json.dumps(document)
        return SimpleNamespace(status_code=status_code, text=body, content=body.encode())

    def fake_client(self, accounts=None, document=None):
        accounts = accounts or [{'accountNumber': '12345678', 'hashValue': 'first-hash'},
                                {'accountNumber': '87654321', 'hashValue': 'second-hash'}]
        document = document or {'securitiesAccount': {
            'accountNumber': '87654321', 'currentBalances': {'cashBalance': 1000.25}, 'positions': [],
        }}
        return SimpleNamespace(
            get_account_numbers=Mock(return_value=self.response(accounts)),
            get_account=Mock(return_value=self.response(document)), session=SimpleNamespace(close=Mock()),
            Account=SimpleNamespace(Fields=SimpleNamespace(POSITIONS='positions')))

    def test_status_is_local_and_does_not_display_private_values(self):
        with vault(self.root) as private:
            connect.token_writer(private, self.credentials)(self.metadata())
        output = io.StringIO()
        with patch.object(connect, 'sdk_auth', side_effect=AssertionError('No SDK in status')), redirect_stdout(output):
            self.assertEqual(connect.main(['status'], self.root), 0)
        self.assertIn('Local status only', output.getvalue())
        for secret in ('test-client', 'test-secret', 'private-access', 'private-refresh'):
            self.assertNotIn(secret, output.getvalue())

    def test_callback_rejects_wrong_origin_path_state_or_duplicates(self):
        base = 'https://127.0.0.1'
        bad_urls = [
            'http://127.0.0.1/?code=abc&state=expected',
            'https://127.0.0.1:443/?code=abc&state=expected',
            'https://127.0.0.1.evil/?code=abc&state=expected',
            'https://evil@127.0.0.1/?code=abc&state=expected',
            'https://127.0.0.1/wrong?code=abc&state=expected',
            'https://127.0.0.1/?code=abc&state=other',
            'https://127.0.0.1/?code=abc&state=expected&state=expected',
            'https://127.0.0.1/?code=abc&code=def&state=expected',
            'https://127.0.0.1/?code=abc&state=expected#error=denied',
            'https://127.0.0.1/?code=abc&state=expected&error=denied',
            'https://127.0.0.1/?code=&state=expected',
            'https://127.0.0.1/?code=abc&state=expected\n',
        ]
        for url in bad_urls:
            with self.subTest(url=url), self.assertRaises(connect.ConnectionError):
                connect.validate_callback(url, base, 'expected')
        accepted = base + '/?code=abc%2525%2B&state=expected'
        self.assertEqual(connect.validate_callback(accepted, base, 'expected'), accepted)

    def test_registered_query_is_preserved(self):
        redirect = 'https://127.0.0.1/callback?owner=one'
        url = redirect + '&code=abc&state=expected'
        self.assertEqual(connect.validate_callback(url, redirect, 'expected'), url)
        with self.assertRaises(connect.ConnectionError):
            connect.validate_callback(url.replace('owner=one', 'owner=two'), redirect, 'expected')

    def test_changed_app_and_pending_operations_block_client_creation(self):
        with vault(self.root) as private, patch.object(connect, 'sdk_auth') as sdk:
            connect.token_writer(private, self.credentials)(self.metadata())
            with self.assertRaises(connect.ConnectionError):
                connect.connected_client(private, {**self.credentials, 'client_secret': 'different'})
            for name in ('pending-auth.json', 'token-operation.json'):
                private.write(name, {'phase': 'uncertain'})
                with self.assertRaises(connect.ConnectionError):
                    connect.connected_client(private, self.credentials)
                private.remove(name)
            sdk.assert_not_called()

    def test_invalid_token_is_not_saved(self):
        with vault(self.root) as private:
            for key, value in [('refresh_token', ''), ('expires_at', float('nan')),
                               ('expires_in', 0), ('token_type', 'other')]:
                metadata = self.metadata()
                metadata['token'][key] = value
                with self.subTest(key=key), self.assertRaises(connect.ConnectionError):
                    connect.token_writer(private, self.credentials)(metadata)
                self.assertIsNone(private.read('tokens.json'))

    def test_login_requires_owner_terminal_and_explicit_restart(self):
        with vault(self.root) as private, patch.object(connect, 'sdk_auth') as sdk:
            with patch('sys.stdin.isatty', return_value=False), self.assertRaises(connect.ConnectionError):
                connect.login(private)
            connect.token_writer(private, self.credentials)(self.metadata())
            with patch('sys.stdin.isatty', return_value=True), patch('sys.stdout.isatty', return_value=True):
                with self.assertRaises(connect.ConnectionError):
                    connect.login(private)
            sdk.assert_not_called()

    def test_login_records_pending_before_browser_and_keeps_interruption(self):
        context = SimpleNamespace(state='random-state', authorization_url='https://provider.invalid/authorize')
        sdk = SimpleNamespace(get_auth_context=Mock(return_value=context))
        with vault(self.root) as private:
            def opening(url, **kwargs):
                self.assertEqual(private.read('pending-auth.json')['state'], 'random-state')
                return True

            with patch.object(connect, 'sdk_auth', return_value=sdk), \
                    patch('sys.stdin.isatty', return_value=True), patch('sys.stdout.isatty', return_value=True), \
                    patch.object(connect.webbrowser, 'open', side_effect=opening), \
                    patch.object(connect.getpass, 'getpass', side_effect=KeyboardInterrupt), \
                    redirect_stdout(io.StringIO()), self.assertRaises(KeyboardInterrupt):
                # redirect_stdout replaces isatty, so use an explicit TTY-like buffer.
                with patch('sys.stdout.isatty', return_value=True):
                    connect.login(private)
            self.assertEqual(private.read('pending-auth.json')['phase'], 'awaiting_callback')
            self.assertIsNone(private.read('tokens.json'))

    def test_snapshot_reads_only_selected_account_and_preserves_source_numbers(self):
        client = self.fake_client()
        output = io.StringIO()
        with vault(self.root) as private, patch.object(connect, 'connected_client', return_value=client), \
                patch('sys.stdin.isatty', return_value=True), redirect_stdout(output), \
                patch('sys.stdout.isatty', return_value=True), patch('builtins.input', return_value='2'):
            connect.snapshot(private)
            saved = private.read('account-snapshot.json')
            self.assertFalse(saved['reconciled'])
            self.assertEqual(saved['response_body'], client.get_account.return_value.text)
            self.assertEqual(private.read('account-selection.json')['hash_value'], 'second-hash')
        client.get_account.assert_called_once_with('second-hash', fields=['positions'])
        client.session.close.assert_called_once()
        for value in ('12345678', '87654321', 'first-hash', 'second-hash', '1000.25'):
            self.assertNotIn(value, output.getvalue())
        self.assertIn('ending 4321', output.getvalue())

    def test_lost_selection_never_silently_switches_accounts(self):
        client = self.fake_client()
        with vault(self.root) as private, patch.object(connect, 'connected_client', return_value=client):
            private.write('account-selection.json', {'account_number': '99999999', 'hash_value': 'revoked'})
            with self.assertRaisesRegex(connect.ConnectionError, '--select-account'):
                connect.snapshot(private)
            self.assertIsNone(private.read('account-snapshot.json'))
        client.get_account.assert_not_called()
        client.session.close.assert_called_once()

    def test_account_mismatch_or_http_failure_keeps_previous_snapshot(self):
        for response in (self.response({'securitiesAccount': {'accountNumber': 'wrong'}}),
                         self.response({'private': 'sensitive-data'}, 401),
                         self.response({'private': 'sensitive-data'}, 500)):
            client = self.fake_client()
            client.get_account.return_value = response
            with vault(self.root) as private, patch.object(connect, 'connected_client', return_value=client):
                private.write('account-selection.json', {'account_number': '87654321', 'hash_value': 'second-hash'})
                private.write('account-snapshot.json', {'previous': True})
                with self.assertRaises(connect.ConnectionError) as error:
                    connect.snapshot(private)
                self.assertNotIn('sensitive-data', str(error.exception))
                self.assertEqual(private.read('account-snapshot.json'), {'previous': True})

    def test_cli_hides_unexpected_provider_errors(self):
        stderr = io.StringIO()
        with patch.object(connect, 'snapshot', side_effect=RuntimeError('token=PRIVATE_SECRET')), redirect_stderr(stderr):
            self.assertEqual(connect.main(['snapshot'], self.root), 1)
        self.assertNotIn('PRIVATE_SECRET', stderr.getvalue())
        self.assertIn('could not be confirmed', stderr.getvalue())


if __name__ == '__main__':
    unittest.main()
