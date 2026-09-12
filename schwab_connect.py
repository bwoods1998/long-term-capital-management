"""Owner-only Schwab authorization and private account observations.

No order routes, public exports, background retries, or automatic authorization.
The optional community SDK owns OAuth request encoding and token refresh.
"""
import argparse
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import getpass
import hashlib
import hmac
import json
import logging
import math
from pathlib import Path
import re
import secrets
import sys
import time
from urllib.parse import parse_qs, parse_qsl, urlsplit
import warnings
import webbrowser

from schwab_storage import StorageError, vault

ROOT = Path(__file__).resolve().parent
RESTART = 'Run login --restart in your terminal when ready to complete fresh authorization.'
ACCOUNT_HASH = re.compile(r'[A-Za-z0-9_-]{1,128}\Z')
ACCOUNT_NUMBER = re.compile(r'[0-9]{4,32}\Z')


class ConnectionError(RuntimeError):
    """A message safe to display without exposing provider data."""


@contextmanager
def quiet_sdk():
    # The community client's debug logs include raw account responses.
    previous = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        yield
    finally:
        logging.disable(previous)


def sdk_auth():
    try:
        from authlib.deprecate import AuthlibDeprecationWarning
        with warnings.catch_warnings():
            # The pinned integration is tested with httpx. This upstream
            # migration notice is for maintainers, not the owner login prompt.
            warnings.filterwarnings(
                'ignore', message=r'The httpx module is deprecated; please use httpx2 instead\.',
                category=AuthlibDeprecationWarning)
            from schwab import auth
    except ImportError:
        raise ConnectionError('Install requirements-schwab.txt in .venv, then use .venv/bin/python.') from None
    return auth


def credentials_fingerprint(credentials):
    payload = json.dumps(credentials, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(payload).hexdigest()


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 < value < 253402300799


def validate_token(metadata):
    if not isinstance(metadata, dict) or not _number(metadata.get('creation_timestamp')):
        raise ConnectionError('The token response could not be validated. ' + RESTART)
    token = metadata.get('token')
    if (not isinstance(token, dict) or
            not all(isinstance(token.get(key), str) and 0 < len(token[key]) <= 32768
                    and not any(c.isspace() for c in token[key])
                    for key in ('access_token', 'refresh_token')) or
            not isinstance(token.get('token_type'), str) or token['token_type'].lower() != 'bearer' or
            not _number(token.get('expires_at')) or not _number(token.get('expires_in'))):
        raise ConnectionError('The token response could not be validated. ' + RESTART)
    return metadata


def token_writer(private, credentials):
    def write(metadata, *args, **kwargs):
        validate_token(metadata)
        private.write('tokens.json', {
            'schema_version': 1,
            'credential_fingerprint': credentials_fingerprint(credentials),
            'sdk_token': metadata,
        })
    return write


def _load_token(private, credentials):
    record = private.read('tokens.json')
    if record is None:
        raise ConnectionError('No saved authorization. Run login in your terminal first.')
    if (record.get('schema_version') != 1 or
            record.get('credential_fingerprint') != credentials_fingerprint(credentials)):
        raise ConnectionError('Saved tokens do not match this app configuration. ' + RESTART)
    return validate_token(record.get('sdk_token'))


def _require_ready(private):
    if private.read('pending-auth.json') is not None or private.read('token-operation.json') is not None:
        raise ConnectionError('An authorization or token refresh was not confirmed. ' + RESTART)


def validate_callback(received_url, redirect_uri, expected_state):
    """Validate before any exchange; leave encoded authorization codes untouched."""
    message = 'Callback rejected. Copy the complete URL from this login into the hidden prompt.'
    if (not isinstance(received_url, str) or not 1 <= len(received_url) <= 16384 or
            not received_url.isascii() or '\\' in received_url or
            any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in received_url)):
        raise ConnectionError(message)
    try:
        received, registered = urlsplit(received_url), urlsplit(redirect_uri)
        # A browser may insert '/' for the empty root path. This acceptance rule
        # never changes the registered redirect_uri sent to the token endpoint.
        if (received.scheme != 'https' or received.netloc != registered.netloc or
                (received.path or '/') != (registered.path or '/') or
                received.username is not None or received.password is not None or received.fragment):
            raise ValueError
        query = parse_qs(received.query, keep_blank_values=True, max_num_fields=32, errors='strict')
        if any(len(values) != 1 for values in query.values()) or 'error' in query:
            raise ValueError
        if not query.get('code', [''])[0] or not query.get('state', [''])[0]:
            raise ValueError
        if not hmac.compare_digest(query['state'][0].encode(), expected_state.encode()):
            raise ValueError
        for key, values in parse_qs(registered.query, keep_blank_values=True).items():
            if query.get(key) != values:
                raise ValueError
    except (ValueError, UnicodeError):
        raise ConnectionError(message) from None
    return received_url


def exchange_callback(private, credentials, auth_context, received_url):
    validated = validate_callback(received_url, credentials['redirect_uri'], auth_context.state)
    pending = private.read('pending-auth.json')
    if (pending is None or pending.get('phase') != 'awaiting_callback' or
            pending.get('state') != auth_context.state or
            pending.get('credential_fingerprint') != credentials_fingerprint(credentials)):
        raise ConnectionError('This callback does not belong to the pending login. ' + RESTART)
    private.write('pending-auth.json', {**pending, 'phase': 'exchanging'})
    saved = False
    write = token_writer(private, credentials)

    def confirmed_write(metadata, *args, **kwargs):
        nonlocal saved
        write(metadata, *args, **kwargs)
        saved = True

    with quiet_sdk():
        client = sdk_auth().client_from_received_url(
            credentials['client_id'], credentials['client_secret'], auth_context,
            validated, confirmed_write)
        client.session.close()
    if not saved:
        raise ConnectionError('Token persistence was not confirmed. ' + RESTART)
    # New consent may authorize a different set of accounts. The pending marker
    # stays until cleanup completes, including any uncertain previous refresh.
    for name in ('account-selection.json', 'account-snapshot.json', 'token-operation.json'):
        private.remove(name)
    private.remove_pending()


def _allow_request(request):
    """An HTTP-level allowlist also blocks unused SDK trading methods."""
    url = request.url
    if url.scheme != 'https' or url.host != 'api.schwabapi.com' or url.port not in (None, 443):
        raise ConnectionError('Unsupported brokerage request blocked.')
    if request.method == 'POST' and url.path == '/v1/oauth/token':
        fields = parse_qs(request.content.decode('ascii'), keep_blank_values=True)
        if fields.get('grant_type') == ['refresh_token'] and not url.query:
            return
    if request.method == 'GET':
        if url.path == '/trader/v1/accounts/accountNumbers' and not url.query:
            return
        if (url.path.startswith('/trader/v1/accounts/') and
                ACCOUNT_HASH.fullmatch(url.path.removeprefix('/trader/v1/accounts/')) and
                parse_qsl(url.query.decode('ascii')) == [('fields', 'positions')]):
            return
    raise ConnectionError('Unsupported brokerage request blocked.')


def connected_client(private, credentials):
    _require_ready(private)
    metadata = _load_token(private, credentials)
    write = token_writer(private, credentials)
    writes = 0

    def confirmed_write(token, *args, **kwargs):
        nonlocal writes
        write(token, *args, **kwargs)
        writes += 1

    with quiet_sdk():
        client = sdk_auth().client_from_access_functions(
            credentials['client_id'], credentials['client_secret'],
            lambda: deepcopy(metadata), confirmed_write)
    client.set_timeout(30)
    client.session.follow_redirects = False

    def guarded_request(request):
        _allow_request(request)
        if request.method == 'GET':
            # Authlib may hold a new token in memory even when disk persistence
            # failed. Block reuse of that client as well as new client creation.
            _require_ready(private)

    client.session.event_hooks['request'].append(guarded_request)
    refresh = client.session.refresh_token

    def guarded_refresh(*args, **kwargs):
        _require_ready(private)
        private.write('token-operation.json', {
            'schema_version': 1, 'kind': 'refresh', 'phase': 'started', 'started_at': timestamp(),
        })
        previous_writes = writes
        with quiet_sdk():
            result = refresh(*args, **kwargs)
        if writes != previous_writes + 1:
            raise ConnectionError('Refresh persistence was not confirmed. ' + RESTART)
        private.remove('token-operation.json')
        return result

    client.session.refresh_token = guarded_refresh
    return client


def _credentials(private):
    credentials = private.read('credentials.json')
    if credentials is None:
        raise ConnectionError('Run python3 scripts/setup_schwab.py in your terminal first.')
    return credentials


def status(private):
    credentials = private.read('credentials.json')
    print('App credentials: ' + ('saved privately' if credentials else 'not configured'))
    attention = (private.read('pending-auth.json') is not None or
                 private.read('token-operation.json') is not None)
    if attention:
        print('Authorization: needs attention. ' + RESTART)
    elif credentials and private.read('tokens.json'):
        token = _load_token(private, credentials)['token']
        expires = datetime.fromtimestamp(token['expires_at'], timezone.utc).isoformat(timespec='seconds')
        print('Access token: ' + ('expired' if token['expires_at'] <= time.time() else 'stored') +
              '; expiry ' + expires)
    else:
        print('Authorization: not connected')
    print('Private snapshot: ' + ('saved' if private.read('account-snapshot.json') else 'none'))
    print('Local status only; no request made to Schwab.')


def login(private, restart=False):
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise ConnectionError('Run login directly in your own terminal.')
    credentials = _credentials(private)
    if not restart and any(private.read(name) is not None
                           for name in ('tokens.json', 'pending-auth.json', 'token-operation.json')):
        raise ConnectionError('Saved or pending authorization already exists. ' + RESTART)
    with quiet_sdk():
        context = sdk_auth().get_auth_context(
            credentials['client_id'], credentials['redirect_uri'], state=secrets.token_urlsafe(32))
    private.write('pending-auth.json', {
        'schema_version': 1, 'phase': 'awaiting_callback', 'created_at': timestamp(),
        'state': context.state, 'credential_fingerprint': credentials_fingerprint(credentials),
    })
    print('Complete Schwab login and account consent in your browser.')
    print('The final localhost page may fail to load. Copy its full address into the hidden prompt.')
    if not webbrowser.open(context.authorization_url, new=2):
        print('Open this authorization link in your browser:')
        print(context.authorization_url)
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        received = getpass.getpass('Full callback URL (hidden): ')
    exchange_callback(private, credentials, context, received)
    print('Authorization saved privately. Next: .venv/bin/python schwab_connect.py snapshot')


def _response_json(response):
    if response.status_code in (401, 403):
        raise ConnectionError('Schwab declined account access. Review app permissions. ' + RESTART)
    if response.status_code != 200:
        raise ConnectionError('Schwab did not return a successful account response. No snapshot saved.')
    if len(response.content) > 750_000:
        raise ConnectionError('Account response exceeds the private snapshot limit.')
    try:
        def reject_constant(_):
            raise ValueError

        return json.loads(response.text, parse_constant=reject_constant)
    except (ValueError, RecursionError):
        raise ConnectionError('Schwab returned an unreadable account response.') from None


def _accounts(response):
    accounts = _response_json(response)
    if not isinstance(accounts, list) or not 1 <= len(accounts) <= 100:
        raise ConnectionError('No usable authorized account list was returned.')
    numbers, hashes = set(), set()
    for account in accounts:
        if (not isinstance(account, dict) or
                not isinstance(account.get('accountNumber'), str) or
                not ACCOUNT_NUMBER.fullmatch(account['accountNumber']) or
                not isinstance(account.get('hashValue'), str) or
                not ACCOUNT_HASH.fullmatch(account['hashValue']) or
                account['accountNumber'] in numbers or account['hashValue'] in hashes):
            raise ConnectionError('The authorized account list has an unexpected format.')
        numbers.add(account['accountNumber'])
        hashes.add(account['hashValue'])
    return accounts


def snapshot(private, select_account=False):
    credentials = _credentials(private)
    client = connected_client(private, credentials)
    try:
        with quiet_sdk():
            accounts = _accounts(client.get_account_numbers())
        selection = private.read('account-selection.json')
        if selection and not select_account:
            selected = next((account for account in accounts
                             if account['hashValue'] == selection.get('hash_value') and
                             account['accountNumber'] == selection.get('account_number')), None)
            if selected is None:
                raise ConnectionError('The selected account is no longer available. Run snapshot --select-account.')
        else:
            if not sys.stdin.isatty() or not sys.stdout.isatty():
                raise ConnectionError('Run snapshot in your own terminal to select an account.')
            for index, account in enumerate(accounts, 1):
                print(f"{index}. Account ending {account['accountNumber'][-4:]}")
            choice = input(f'Choose 1–{len(accounts)}: ').strip()
            if not choice.isascii() or not choice.isdecimal() or not 1 <= int(choice) <= len(accounts):
                raise ConnectionError('No valid account selected. No snapshot saved.')
            selected = accounts[int(choice) - 1]
        with quiet_sdk():
            response = client.get_account(selected['hashValue'], fields=[client.Account.Fields.POSITIONS])
            document = _response_json(response)
        account = document.get('securitiesAccount') if isinstance(document, dict) else None
        if (not isinstance(account, dict) or account.get('accountNumber') != selected['accountNumber'] or
                not isinstance(account.get('currentBalances'), dict) or
                not isinstance(account.get('positions', []), list)):
            raise ConnectionError('The account response did not match the selected account or expected format.')
        private.write('account-snapshot.json', {
            'schema_version': 1, 'observed_at': timestamp(), 'reconciled': False,
            # Retain the original numeric spelling for later Decimal accounting.
            'response_body': response.text,
        })
        private.write('account-selection.json', {
            'schema_version': 1, 'account_number': selected['accountNumber'],
            'hash_value': selected['hashValue'],
        })
        print(f"Private snapshot saved: {len(account.get('positions', []))} positions. Reconciliation is next.")
        print('No account data published; no orders submitted.')
    finally:
        client.session.close()


def main(argv=None, root=ROOT):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('status', help='Inspect local connection metadata without network access')
    login_parser = commands.add_parser('login', help='Authorize in your browser and hidden terminal prompt')
    login_parser.add_argument('--restart', action='store_true', help='Explicitly start fresh authorization')
    snapshot_parser = commands.add_parser('snapshot', help='Read one selected account privately')
    snapshot_parser.add_argument('--select-account', action='store_true', help='Choose an account again')
    args = parser.parse_args(argv)
    try:
        with vault(root) as private:
            if args.command == 'status':
                status(private)
            elif args.command == 'login':
                login(private, args.restart)
            else:
                snapshot(private, args.select_account)
        return 0
    except (ConnectionError, StorageError) as error:
        print(str(error), file=sys.stderr)
    except (EOFError, KeyboardInterrupt, getpass.GetPassWarning):
        print('Stopped. Inspect status before trying again; pending authorization is preserved.', file=sys.stderr)
    except Exception:
        # HTTP exceptions can contain token URLs or provider response bodies.
        print('Schwab operation could not be confirmed. Run status for the next step; '
              'private state was retained. No automatic retry was made.', file=sys.stderr)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
