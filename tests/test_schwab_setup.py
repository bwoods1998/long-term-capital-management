import json
from pathlib import Path
import stat
import tempfile
import unittest

from scripts.setup_schwab import save_credentials, validate_credentials


class SchwabSetupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_private_save_preserves_sail_and_never_overwrites(self):
        sail = self.root / '.env'
        sail.write_text('test-only-existing-sail-file\n')
        save_credentials(self.root, 'test-client', 'test-secret', 'https://127.0.0.1')
        target = self.root / '.data/schwab/credentials.json'
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(target.parent.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(target.parent.parent.stat().st_mode), 0o700)
        original = target.read_bytes()
        self.assertEqual(json.loads(original)['redirect_uri'], 'https://127.0.0.1')
        with self.assertRaises(FileExistsError):
            save_credentials(self.root, 'other-client', 'other-secret', 'https://127.0.0.1')
        self.assertEqual(target.read_bytes(), original)
        self.assertEqual(sail.read_text(), 'test-only-existing-sail-file\n')

    def test_symlink_directories_and_files_are_not_followed(self):
        external = self.root / 'external'
        external.mkdir()
        (self.root / '.data').symlink_to(external, target_is_directory=True)
        with self.assertRaises(OSError):
            save_credentials(self.root, 'test-client', 'test-secret', 'https://127.0.0.1')
        self.assertEqual(list(external.iterdir()), [])
        (self.root / '.data').unlink()
        private = self.root / '.data/schwab'
        private.mkdir(parents=True)
        existing = external / 'existing'
        existing.write_text('leave this alone')
        (private / 'credentials.json').symlink_to(existing)
        with self.assertRaises(FileExistsError):
            save_credentials(self.root, 'test-client', 'test-secret', 'https://127.0.0.1')
        self.assertEqual(existing.read_text(), 'leave this alone')

    def test_rejects_authorization_results_and_invalid_inputs_before_saving(self):
        for callback in ['https://127.0.0.1?code=private', 'https://127.0.0.1?state=',
                         'https://example.com/authorize?response_type=code&client_id=test',
                         'https://127.0.0.1#access_token=private', 'https://user:secret@example.com',
                         'https://127.0.0.1:99999', 'https://127.0.0.1\\@example.com',
                         'http://127.0.0.1', 'https://127.0.0.1\n']:
            with self.subTest(callback=callback), self.assertRaises(ValueError):
                save_credentials(self.root, 'test-client', 'test-secret', callback)
        self.assertFalse((self.root / '.data').exists())
        for secret in ['', 'embedded whitespace', 'line\nbreak', 'x' * 513]:
            with self.assertRaises(ValueError):
                validate_credentials('test-client', secret, 'https://127.0.0.1')


if __name__ == '__main__':
    unittest.main()
