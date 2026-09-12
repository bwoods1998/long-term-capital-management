"""Private Schwab JSON storage, locked for the caller's entire workflow.

No network access. Schemas other than app credentials belong to the caller.
Writes replace complete files atomically; an error after replacement can leave
the new document installed, so callers must treat a write error as uncertain.
"""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import secrets
import stat

from scripts.setup_schwab import private_directory, validate_credentials

ROOT = Path(__file__).resolve().parent
MAX_BYTES = 2_000_000
WRITABLE = frozenset({'tokens.json', 'pending-auth.json', 'account-selection.json',
                      'account-snapshot.json', 'token-operation.json'})
READABLE = WRITABLE | {'credentials.json'}


class StorageError(RuntimeError):
    """A private storage failure; messages never include document values."""


class VaultBusy(StorageError):
    """Another process already holds the Schwab workflow lock."""


def _regular(info):
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or
            stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1 or info.st_size > MAX_BYTES):
        raise StorageError('Private files must be owned regular files with mode 0600 and one link, within the size limit.')


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _reject_constant(_):
    raise ValueError


class _Vault:
    def __init__(self, descriptor):
        self._directory = descriptor
        self._closed = False

    def _name(self, name, allowed=READABLE):
        if self._closed:
            raise StorageError('The private vault is closed.')
        if not isinstance(name, str) or name not in allowed:
            raise StorageError('This private filename is not allowed.')

    def _existing(self, name):
        try:
            _regular(os.stat(name, dir_fd=self._directory, follow_symlinks=False))
        except FileNotFoundError:
            pass

    def read(self, name):
        self._name(name)
        try:
            try:
                descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=self._directory)
            except FileNotFoundError:
                return None
            with os.fdopen(descriptor, 'rb') as source:
                _regular(os.fstat(source.fileno()))
                content = source.read(MAX_BYTES + 1)
            if len(content) > MAX_BYTES:
                raise StorageError('Private document exceeds the size limit.')
            document = json.loads(content, object_pairs_hook=_object, parse_constant=_reject_constant)
            if not isinstance(document, dict):
                raise ValueError
            if name == 'credentials.json':
                checked = validate_credentials(document['client_id'], document['client_secret'], document['redirect_uri'])
                if document != checked or type(document.get('schema_version')) is not int:
                    raise ValueError
            return document
        except (OSError, ValueError, TypeError, KeyError, RecursionError):
            raise StorageError('Cannot read the private document; check its format and permissions.') from None

    def write(self, name, data):
        self._name(name, WRITABLE)
        temporary = None
        try:
            if not isinstance(data, dict):
                raise ValueError
            payload = (json.dumps(data, allow_nan=False, ensure_ascii=True, indent=2) + '\n').encode()
            if len(payload) > MAX_BYTES:
                raise StorageError('Private document exceeds the size limit.')
            self._existing(name)
            candidate = '.write-' + secrets.token_hex(16)
            descriptor = os.open(candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=self._directory)
            temporary = candidate
            with os.fdopen(descriptor, 'wb') as output:
                os.fchmod(output.fileno(), 0o600)
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            self._existing(name)
            os.replace(temporary, name, src_dir_fd=self._directory, dst_dir_fd=self._directory)
            temporary = None
            os.fsync(self._directory)
        except (OSError, ValueError, TypeError, RecursionError):
            raise StorageError('Private write could not be confirmed; inspect storage before retrying.') from None
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary, dir_fd=self._directory)
                except OSError:
                    pass

    def remove(self, name):
        self._name(name, WRITABLE)
        try:
            self._existing(name)
            try:
                os.unlink(name, dir_fd=self._directory)
            except FileNotFoundError:
                return
            os.fsync(self._directory)
        except OSError:
            raise StorageError('Private document removal could not be confirmed.') from None

    def remove_pending(self):
        self.remove('pending-auth.json')


@contextmanager
def vault(root=ROOT):
    """Hold an exclusive, nonblocking POSIX lock until the context exits."""
    descriptors = []
    opened = None
    try:
        try:
            descriptors.append(os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW))
            descriptors.append(private_directory(descriptors[-1], '.data'))
            descriptors.append(private_directory(descriptors[-1], 'schwab'))
            directory = descriptors[-1]
            descriptors.append(os.open('.vault.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                                       0o600, dir_fd=directory))
            _regular(os.fstat(descriptors[-1]))
            try:
                fcntl.flock(descriptors[-1], fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise VaultBusy('Another Schwab workflow is already running; try again after it finishes.') from None
        except (OSError, ValueError):
            raise StorageError('Cannot open the private vault; check ownership and permissions.') from None
        opened = _Vault(directory)
        yield opened
    finally:
        if opened is not None:
            opened._closed = True
        for descriptor in reversed(descriptors):
            os.close(descriptor)
