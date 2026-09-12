"""Offline integration checks using the real SDK and an in-memory HTTP server.

Every credential and response is synthetic. The default network transport is
disabled as a second guard against accidentally contacting a broker.
"""
import base64
from copy import deepcopy
import importlib.util
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit, urlencode

from scripts.setup_schwab import save_credentials
import schwab_connect as connector
import schwab_storage as storage

HAS_SDK = all(importlib.util.find_spec(name) is not None
              for name in ('schwab', 'authlib', 'httpx'))
if HAS_SDK:
    import httpx
    from authlib.integrations.httpx_client import OAuth2Client
    from authlib.oauth2.rfc6749.errors import MismatchingStateException
    from schwab import auth


@unittest.skipUnless(HAS_SDK, 'Install requirements-schwab.txt for SDK integration checks')
class SchwabSdkTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        save_credentials(self.root, 'synthetic-client', 'synthetic-secret',
                         'https://127.0.0.1')
        self.requests = []
        self.handler = None
        self.addCleanup(patch.stopall)
        patch.object(httpx.HTTPTransport, 'handle_request', side_effect=AssertionError(
            'Unexpected real network attempt')).start()
        patch.object(auth, 'OAuth2Client', side_effect=self.oauth_client).start()

    def oauth_client(self, *args, **kwargs):
        kwargs['transport'] = httpx.MockTransport(self.dispatch)
        kwargs['trust_env'] = False
        session = OAuth2Client(*args, **kwargs)
        self.addCleanup(session.close)
        return session

    def dispatch(self, request):
        self.requests.append(request)
        self.assertEqual(request.url.scheme, 'https')
        self.assertEqual(request.url.host, 'api.schwabapi.com')
        allowed = (request.method == 'POST' and request.url.path == '/v1/oauth/token') or (
            request.method == 'GET' and request.url.path in {
                '/trader/v1/accounts/accountNumbers', '/trader/v1/accounts/synthetic-hash'})
        self.assertTrue(allowed, 'A request escaped the account-only test boundary')
        self.assertIsNotNone(self.handler, 'No response fixture configured')
        return self.handler(request)

    def token_response(self, label='new'):
        return {'access_token': 'synthetic-' + label + '-access',
                'refresh_token': 'synthetic-' + label + '-refresh',
                'token_type': 'Bearer', 'expires_in': 1800}

    def save_token(self, private, credentials, expired=False):
        token = self.token_response('old')
        token['expires_at'] = time.time() + (-60 if expired else 1800)
        connector.token_writer(private, credentials)({
            'creation_timestamp': int(time.time()) - 3600, 'token': token})

    def pending_login(self, private, credentials):
        context = auth.get_auth_context(credentials['client_id'], credentials['redirect_uri'])
        private.write('pending-auth.json', {
            'schema_version': 1, 'phase': 'awaiting_callback', 'state': context.state,
            'credential_fingerprint': connector.credentials_fingerprint(credentials)})
        return context

    def callback(self, context, code='synthetic-code', state=None):
        return 'https://127.0.0.1/?' + urlencode({
            'code': code, 'state': context.state if state is None else state})

    def assert_basic_auth(self, request):
        expected = base64.b64encode(b'synthetic-client:synthetic-secret').decode()
        self.assertEqual(request.headers['Authorization'], 'Basic ' + expected)

    def test_actual_sdk_exchanges_encoded_code_once_and_preserves_registered_redirect(self):
        with storage.vault(self.root) as private:
            credentials = private.read('credentials.json')
            context = self.pending_login(private, credentials)
            authorize = urlsplit(context.authorization_url)
            self.assertEqual(authorize.scheme, 'https')
            self.assertEqual(authorize.netloc, 'api.schwabapi.com')
            self.assertEqual(authorize.path, '/v1/oauth/authorize')
            fields = parse_qs(authorize.query)
            self.assertEqual(fields['redirect_uri'], ['https://127.0.0.1'])
            self.assertEqual(fields['response_type'], ['code'])
            self.assertEqual(fields['state'], [context.state])
            self.assertGreaterEqual(len(context.state), 20)
            # One percent escape must remain literal after the SDK decodes the
            # callback query; '+' and '=' must survive its form encoding.
            original_code = 'synthetic%2Fpart+tail='
            received = self.callback(context, original_code)
            self.assertIn('synthetic%252Fpart%2Btail%3D', received)
            self.assertEqual(connector.validate_callback(
                received, credentials['redirect_uri'], context.state), received)
            for name in ('account-selection.json', 'account-snapshot.json', 'token-operation.json'):
                private.write(name, {'synthetic': 'previous authorization'})

            def respond(request):
                self.assertEqual(request.method, 'POST')
                self.assertEqual(private.read('pending-auth.json')['phase'], 'exchanging')
                form = parse_qs(request.content.decode())
                self.assertEqual(form['grant_type'], ['authorization_code'])
                self.assertEqual(form['redirect_uri'], ['https://127.0.0.1'])
                self.assertEqual(form['code'], [original_code])
                self.assert_basic_auth(request)
                return httpx.Response(200, json=self.token_response())

            self.handler = respond
            connector.exchange_callback(private, credentials, context, received)
            saved = private.read('tokens.json')['sdk_token']['token']
            self.assertEqual(saved['access_token'], 'synthetic-new-access')
            self.assertGreater(saved['expires_at'], time.time())
            self.assertEqual(len(self.requests), 1)
            for name in ('pending-auth.json', 'account-selection.json',
                         'account-snapshot.json', 'token-operation.json'):
                self.assertIsNone(private.read(name))

    def test_sdk_checks_state_before_post_even_if_caller_validation_is_bypassed(self):
        with storage.vault(self.root) as private:
            credentials = private.read('credentials.json')
            context = self.pending_login(private, credentials)
            received = self.callback(context, state='different-synthetic-state')
            with patch.object(connector, 'validate_callback', return_value=received):
                with self.assertRaises(MismatchingStateException):
                    connector.exchange_callback(private, credentials, context, received)
            self.assertEqual(self.requests, [])
            self.assertIsNone(private.read('tokens.json'))
            self.assertEqual(private.read('pending-auth.json')['phase'], 'exchanging')

    def test_uncertain_initial_exchange_preserves_pending_marker_and_existing_tokens(self):
        with storage.vault(self.root) as private:
            credentials = private.read('credentials.json')
            self.save_token(private, credentials)
            original = deepcopy(private.read('tokens.json'))
            context = self.pending_login(private, credentials)

            def timeout(request):
                raise httpx.ReadTimeout('synthetic network interruption', request=request)

            self.handler = timeout
            with self.assertRaises(httpx.ReadTimeout):
                connector.exchange_callback(private, credentials, context, self.callback(context))
            self.assertEqual(len(self.requests), 1)
            self.assertEqual(private.read('tokens.json'), original)
            self.assertEqual(private.read('pending-auth.json')['phase'], 'exchanging')
            with self.assertRaises(connector.ConnectionError):
                connector.connected_client(private, credentials)
            self.assertEqual(len(self.requests), 1)

    def test_refresh_guard_is_persisted_before_post_and_cleared_before_account_get(self):
        with storage.vault(self.root) as private:
            credentials = private.read('credentials.json')
            self.save_token(private, credentials, expired=True)
            original_creation = private.read('tokens.json')['sdk_token']['creation_timestamp']

            def respond(request):
                if request.method == 'POST':
                    marker = private.read('token-operation.json')
                    self.assertEqual(marker['kind'], 'refresh')
                    self.assertEqual(marker['phase'], 'started')
                    self.assertEqual(private.read('tokens.json')['sdk_token']['token']['access_token'],
                                     'synthetic-old-access')
                    form = parse_qs(request.content.decode())
                    self.assertEqual(form['grant_type'], ['refresh_token'])
                    self.assertEqual(form['refresh_token'], ['synthetic-old-refresh'])
                    self.assert_basic_auth(request)
                    return httpx.Response(200, json=self.token_response())
                self.assertIsNone(private.read('token-operation.json'))
                self.assertEqual(private.read('tokens.json')['sdk_token']['token']['access_token'],
                                 'synthetic-new-access')
                self.assertEqual(request.headers['Authorization'], 'Bearer synthetic-new-access')
                return httpx.Response(200, json=[])

            self.handler = respond
            client = connector.connected_client(private, credentials)
            self.assertEqual(client.get_account_numbers().status_code, 200)
            self.assertEqual([r.method for r in self.requests], ['POST', 'GET'])
            self.assertIsNone(private.read('token-operation.json'))
            self.assertEqual(private.read('tokens.json')['sdk_token']['creation_timestamp'], original_creation)

    def test_refresh_timeout_blocks_retries_and_reconnection(self):
        with storage.vault(self.root) as private:
            credentials = private.read('credentials.json')
            self.save_token(private, credentials, expired=True)
            original = deepcopy(private.read('tokens.json'))

            def timeout(request):
                self.assertIsNotNone(private.read('token-operation.json'))
                raise httpx.ReadTimeout('synthetic network interruption', request=request)

            self.handler = timeout
            client = connector.connected_client(private, credentials)
            with self.assertRaises(httpx.ReadTimeout):
                client.get_account_numbers()
            self.assertEqual(private.read('tokens.json'), original)
            self.assertIsNotNone(private.read('token-operation.json'))
            with self.assertRaises(connector.ConnectionError):
                client.get_account_numbers()
            with self.assertRaises(connector.ConnectionError):
                connector.connected_client(private, credentials)
            self.assertEqual(len(self.requests), 1)

    def test_successful_refresh_with_failed_persistence_keeps_guard_and_blocks_reconnection(self):
        with storage.vault(self.root) as private:
            credentials = private.read('credentials.json')
            self.save_token(private, credentials, expired=True)
            original = deepcopy(private.read('tokens.json'))
            real_write = private.write

            def failing_write(name, data):
                if name == 'tokens.json':
                    self.assertIsNotNone(private.read('token-operation.json'))
                    raise storage.StorageError('synthetic storage failure')
                real_write(name, data)

            self.handler = lambda request: httpx.Response(200, json=self.token_response())
            client = connector.connected_client(private, credentials)
            with patch.object(private, 'write', side_effect=failing_write):
                with self.assertRaises(storage.StorageError):
                    client.get_account_numbers()
            self.assertEqual(private.read('tokens.json'), original)
            self.assertIsNotNone(private.read('token-operation.json'))
            with self.assertRaises(connector.ConnectionError):
                connector.connected_client(private, credentials)
            with self.assertRaises(connector.ConnectionError):
                client.get_account_numbers()
            self.assertEqual(len(self.requests), 1)

    def test_available_sdk_order_and_market_data_methods_are_blocked_before_transport(self):
        with storage.vault(self.root) as private:
            credentials = private.read('credentials.json')
            self.save_token(private, credentials)
            client = connector.connected_client(private, credentials)
            for forbidden in (
                    lambda: client.place_order('synthetic-hash', {}),
                    lambda: client.cancel_order(1, 'synthetic-hash'),
                    lambda: client.get_quotes(['SYNTHETIC']),
                    lambda: client.get_accounts(),
                    lambda: client.session.get('https://example.invalid/account')):
                with self.subTest(operation=forbidden), self.assertRaises(connector.ConnectionError):
                    forbidden()
            self.assertEqual(self.requests, [])
            self.handler = lambda request: httpx.Response(200, json={})
            client.get_account('synthetic-hash', fields=[client.Account.Fields.POSITIONS])
            self.assertEqual(len(self.requests), 1)
            self.assertEqual(self.requests[0].method, 'GET')
            self.assertEqual(self.requests[0].url.query, b'fields=positions')


if __name__ == '__main__':
    unittest.main()
