import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.setup_schwab import save_credentials
import schwab_storage as storage


class SchwabStorageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.directory = self.root / '.data/schwab'

    def test_private_roundtrip_and_credentials_remain_read_only(self):
        save_credentials(self.root, 'synthetic-client', 'synthetic-secret', 'https://127.0.0.1')
        original = (self.directory / 'credentials.json').read_bytes()
        with storage.vault(self.root) as vault:
            self.assertIsNone(vault.read('tokens.json'))
            self.assertEqual(vault.read('credentials.json')['client_id'], 'synthetic-client')
            for name in storage.WRITABLE:
                vault.write(name, {'value': 'synthetic-private-value'})
                self.assertEqual(vault.read(name), {'value': 'synthetic-private-value'})
                self.assertEqual(stat.S_IMODE((self.directory / name).stat().st_mode), 0o600)
            with self.assertRaises(storage.StorageError):
                vault.write('credentials.json', {'bad': 'replace'})
            with self.assertRaises(storage.StorageError):
                vault.remove('credentials.json')
            for name in ['account-snapshot.json', 'token-operation.json']:
                vault.remove(name)
                self.assertIsNone(vault.read(name))
            vault.remove_pending()
            vault.remove_pending()
            self.assertIsNone(vault.read('pending-auth.json'))
        self.assertEqual((self.directory / 'credentials.json').read_bytes(), original)
        self.assertEqual(stat.S_IMODE(self.directory.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(self.directory.parent.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((self.directory / '.vault.lock').stat().st_mode), 0o600)
        with self.assertRaises(storage.StorageError):
            vault.read('tokens.json')

    def test_write_failure_preserves_previous_file_and_cleans_temporary(self):
        with storage.vault(self.root) as vault:
            vault.write('tokens.json', {'token': 'old-synthetic-token'})
            original = (self.directory / 'tokens.json').read_bytes()
            for operation in ['replace', 'fsync']:
                with self.subTest(operation=operation), patch.object(storage.os, operation, side_effect=OSError('PRIVATE_FAILURE_DETAIL')):
                    with self.assertRaises(storage.StorageError) as failure:
                        vault.write('tokens.json', {'token': 'new-synthetic-token'})
                    self.assertNotIn('PRIVATE_FAILURE_DETAIL', str(failure.exception))
                self.assertEqual((self.directory / 'tokens.json').read_bytes(), original)
                self.assertFalse(list(self.directory.glob('.write-*')))

    def test_temporary_name_collision_never_deletes_an_existing_file(self):
        with storage.vault(self.root) as vault:
            existing = self.directory / '.write-collision'
            existing.write_text('preserve this file')
            with patch.object(storage.secrets, 'token_hex', return_value='collision'):
                with self.assertRaises(storage.StorageError):
                    vault.write('tokens.json', {'token': 'synthetic'})
            self.assertEqual(existing.read_text(), 'preserve this file')
            self.assertIsNone(vault.read('tokens.json'))

    def test_nonblocking_lock_is_held_across_workflow_and_released_after_error(self):
        child = ('import sys; from schwab_storage import vault,VaultBusy; '
                 '\ntry:\n with vault(sys.argv[1]): pass\n'
                 'except VaultBusy:\n print("busy")\n')
        with storage.vault(self.root):
            result = subprocess.run([sys.executable, '-c', child, str(self.root)],
                                    cwd=storage.ROOT, capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout.strip(), 'busy')
            with self.assertRaises(storage.VaultBusy):
                with storage.vault(self.root):
                    pass
        with self.assertRaisesRegex(RuntimeError, 'caller failure'):
            with storage.vault(self.root):
                raise RuntimeError('caller failure')
        with storage.vault(self.root) as vault:
            vault.write('tokens.json', {'ok': True})

    def test_symlink_directories_files_and_hardlinks_are_rejected(self):
        external = self.root / 'external'
        external.mkdir()
        (self.root / '.data').symlink_to(external, target_is_directory=True)
        with self.assertRaises(storage.StorageError):
            with storage.vault(self.root):
                pass
        self.assertEqual(list(external.iterdir()), [])
        (self.root / '.data').unlink()
        with storage.vault(self.root) as vault:
            target = external / 'target'
            target.write_text('{"private":"synthetic"}')
            target.chmod(0o600)
            tokens = self.directory / 'tokens.json'
            tokens.symlink_to(target)
            for operation in [lambda: vault.read('tokens.json'), lambda: vault.write('tokens.json', {})]:
                with self.assertRaises(storage.StorageError):
                    operation()
            tokens.unlink()
            os.link(target, tokens)
            with self.assertRaises(storage.StorageError):
                vault.read('tokens.json')
            with self.assertRaises(storage.StorageError):
                vault.write('tokens.json', {})
            self.assertEqual(json.loads(target.read_text()), {'private': 'synthetic'})

    def test_untrusted_names_permissions_and_oversized_documents_are_rejected(self):
        with storage.vault(self.root) as vault:
            for name in ['../credentials.json', '/tmp/tokens.json', '.vault.lock', 'snapshot.json', None]:
                with self.subTest(name=name), self.assertRaises(storage.StorageError):
                    vault.read(name)
                with self.assertRaises(storage.StorageError):
                    vault.write(name, {})
                with self.assertRaises(storage.StorageError):
                    vault.remove(name)
            vault.write('tokens.json', {'ok': True})
            target = self.directory / 'tokens.json'
            target.chmod(0o644)
            with self.assertRaises(storage.StorageError):
                vault.read('tokens.json')
            with self.assertRaises(storage.StorageError):
                vault.write('tokens.json', {})
            target.chmod(0o600)
            original = target.read_bytes()
            with self.assertRaises(storage.StorageError):
                vault.write('tokens.json', {'large': 'x' * storage.MAX_BYTES})
            self.assertEqual(target.read_bytes(), original)
            target.write_bytes(b' ' * (storage.MAX_BYTES + 1))
            with self.assertRaises(storage.StorageError):
                vault.read('tokens.json')

    def test_malformed_documents_and_unsafe_lock_file_fail_without_values(self):
        with storage.vault(self.root) as vault:
            target = self.directory / 'tokens.json'
            for body in ['PRIVATE_INVALID_JSON', '[]', '{"a":1,"a":2}', '{"amount":NaN}']:
                target.write_text(body)
                target.chmod(0o600)
                with self.assertRaises(storage.StorageError) as failure:
                    vault.read('tokens.json')
                self.assertNotIn(body, str(failure.exception))
        lock = self.directory / '.vault.lock'
        lock.chmod(0o644)
        with self.assertRaises(storage.StorageError):
            with storage.vault(self.root):
                pass


if __name__ == '__main__':
    unittest.main()
