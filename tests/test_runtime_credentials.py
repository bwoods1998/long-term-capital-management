"""Private credential and transport boundaries; only synthetic test keys."""
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from portfolio_runtime import control, credentials


class CredentialTests(unittest.TestCase):
    def test_existing_private_key_contract_and_ambiguous_files(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(credentials, 'ROOT', Path(directory)):
            path = Path(directory) / '.env'
            for content in ('', 'OTHER=value\n', 'SAIL_API_KEY=\n', 'SAIL_API_KEY=one\nSAIL_API_KEY=two\n'):
                path.write_text(content); path.chmod(0o600)
                with self.assertRaises(ValueError): credentials.load_api_key()
            path.write_text('SAIL_API_KEY=synthetic-key\n'); path.chmod(0o600)
            self.assertEqual(credentials.load_api_key(), 'synthetic-key')
            path.chmod(0o644)
            with self.assertRaises(ValueError): credentials.load_api_key()
            path.unlink(); target = Path(directory) / 'actual'; target.write_text('SAIL_API_KEY=synthetic-key\n'); target.chmod(0o600)
            path.symlink_to(target)
            with self.assertRaises(ValueError): credentials.load_api_key()

    def test_control_requests_exact_host_with_private_auth_and_same_key(self):
        response = BytesIO(b'{"id":"box-test"}')
        opener = Mock(); opener.open.return_value.__enter__ = lambda unused: response
        opener.open.return_value.__exit__ = lambda *unused: None
        with patch.object(control, 'load_api_key', return_value='synthetic-key'), patch.object(control, 'build_opener', return_value=opener):
            self.assertEqual(control.api('POST', '/v1/sailboxes', {'name': 'test'}, 'same-request'), {'id': 'box-test'})
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, 'https://sailbox-api.sailresearch.com/v1/sailboxes')
        self.assertEqual(request.get_header('Authorization'), 'Bearer synthetic-key')
        self.assertEqual(request.get_header('Idempotency-key'), 'same-request')
        self.assertEqual(opener.open.call_args.kwargs, {'timeout': 20})

    def test_control_errors_never_include_secret_provider_body_and_no_redirect(self):
        error = HTTPError('https://sailbox-api.sailresearch.com/v1/sailboxes', 403, 'synthetic-secret', {}, BytesIO(b'private body'))
        opener = Mock(); opener.open.side_effect = error
        with patch.object(control, 'load_api_key', return_value='synthetic-key'), patch.object(control, 'build_opener', return_value=opener):
            with self.assertRaises(control.SailboxHTTPError) as caught: control.api('GET', '/v1/sailboxes')
        self.assertEqual(caught.exception.status_code, 403)
        self.assertNotIn('synthetic', str(caught.exception))
        self.assertNotIn('private', str(caught.exception))
        self.assertIsNone(credentials.NoRedirect().redirect_request(None, None, 302, None, {}, 'https://elsewhere.test'))
        with self.assertRaises(ValueError): control.api('GET', '//external.example/path')


if __name__ == '__main__':
    unittest.main()
