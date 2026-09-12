"""Save Schwab app credentials locally. No network access or authorization attempt."""
import getpass
import json
import os
from pathlib import Path
import stat
import sys
from urllib.parse import parse_qs, urlsplit
import warnings


ROOT = Path(__file__).resolve().parents[1]


def validate_credentials(client_id, client_secret, redirect_uri):
    for value in (client_id, client_secret):
        if (not isinstance(value, str) or not 1 <= len(value) <= 512 or
                not value.isascii() or not value.isprintable() or
                any(character.isspace() for character in value)):
            raise ValueError('Enter the app client ID and secret without whitespace.')
    if (not isinstance(redirect_uri, str) or not 1 <= len(redirect_uri) <= 2048 or
            not redirect_uri.isascii() or '\\' in redirect_uri or
            any(character.isspace() or ord(character) < 32 for character in redirect_uri)):
        raise ValueError('Enter the registered HTTPS callback URL, not an authorization result.')
    try:
        url = urlsplit(redirect_uri)
        port = url.port
        if (url.scheme != 'https' or not url.hostname or url.username is not None or
                url.password is not None or url.fragment or (port is not None and port < 1) or
                {'code', 'state', 'error', 'access_token', 'refresh_token', 'response_type',
                 'client_id', 'code_challenge', 'code_challenge_method'} & set(parse_qs(url.query, keep_blank_values=True))):
            raise ValueError
    except ValueError:
        raise ValueError('Enter the registered HTTPS callback URL, not an authorization result.') from None
    return {'schema_version': 1, 'client_id': client_id, 'client_secret': client_secret,
            'redirect_uri': redirect_uri}


def private_directory(parent_fd, name):
    try:
        os.mkdir(name, mode=0o700, dir_fd=parent_fd)
    except FileExistsError:
        pass
    descriptor = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
    try:
        info = os.fstat(descriptor)
        if info.st_uid != os.getuid():
            raise ValueError('The private directory must belong to the current user.')
        if stat.S_IMODE(info.st_mode) != 0o700:
            os.fchmod(descriptor, 0o700)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def save_credentials(root, client_id, client_secret, redirect_uri):
    document = validate_credentials(client_id, client_secret, redirect_uri)
    descriptors = []
    try:
        descriptors.append(os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW))
        descriptors.append(private_directory(descriptors[-1], '.data'))
        descriptors.append(private_directory(descriptors[-1], 'schwab'))
        directory = descriptors[-1]
        # Exclusive creation prevents replacement of existing credentials or symlinks.
        descriptor = os.open('credentials.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory)
        try:
            with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
                os.fchmod(output.fileno(), 0o600)
                json.dump(document, output, indent=2)
                output.write('\n')
                output.flush()
                os.fsync(output.fileno())
            os.fsync(directory)
        except BaseException:
            os.unlink('credentials.json', dir_fd=directory)
            raise
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def main():
    if not sys.stdin.isatty():
        raise SystemExit('Run this command directly in your own terminal.')
    target = ROOT / '.data/schwab/credentials.json'
    if target.exists() or target.is_symlink():
        raise SystemExit('Schwab credentials already exist; left unchanged.')
    callback = input('Registered callback URL [https://127.0.0.1]: ').strip() or 'https://127.0.0.1'
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        client_id = getpass.getpass('Schwab Accounts and Trading client ID (hidden): ')
        client_secret = getpass.getpass('Schwab client secret (hidden): ')
    save_credentials(ROOT, client_id, client_secret, callback)
    print('Saved privately to .data/schwab/credentials.json. No network requests made.')
    print('This saves app credentials only; the brokerage account is not connected yet.')


if __name__ == '__main__':
    try:
        main()
    except (EOFError, KeyboardInterrupt, getpass.GetPassWarning):
        raise SystemExit('\nSetup stopped; credentials were not saved.') from None
    except FileExistsError:
        raise SystemExit('Schwab credentials already exist; left unchanged.') from None
    except ValueError as error:
        raise SystemExit(str(error)) from None
    except OSError:
        raise SystemExit('Cannot save credentials. Check private directory ownership and permissions.') from None
