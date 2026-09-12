"""Prepare and run an explicitly bounded clean-VM research validation bundle.

The guest receives only a frozen allowlist of application code and public evidence.
Sail authentication stays in this local controller. Preparing a bundle is offline.
"""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener
import uuid

from lab import load_api_key, NoRedirect
from sail_tracking import _diagnostic, _write

ROOT = Path(__file__).resolve().parent
REMOTE = '/workspace/portfolio-proof'
APP_NAME = 'portfolio-offline-validation'
MAX_SECONDS = 1800
RESERVE_USD = Decimal('0.25')
FILES = ('portfolio.py', 'lab.py', 'investigator.py', 'research_sources.py', 'research_eval.py',
         'sail_tracking.py', 'scripts/sandbox_validation.py', 'data/msft-2025.json',
         'data/thesis/msft-ai-infrastructure.json', 'data/evals/research-cases.json',
         'tests/test_evidence_packet.py', 'tests/test_lab.py', 'tests/test_portfolio.py',
         'tests/test_research_tasks.py', 'tests/test_research_sources.py',
         'tests/test_research_eval.py', 'tests/test_investigator.py', 'tests/test_sail_tracking.py')
SOURCE_IDS = ('fy26-results', 'fy26-call')


class SailboxHTTPError(RuntimeError):
    def __init__(self, status_code):
        self.status_code = status_code
        super().__init__('Sailbox HTTP ' + str(status_code) + '; inspect the operation journal')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def prepare(destination):
    """Freeze exact upload bytes; never recursively copy the working directory."""
    import research_sources
    destination = Path(destination)
    if destination.exists():
        raise ValueError('Choose a new bundle directory so reviewed bytes cannot be replaced')
    destination.mkdir(parents=True, mode=0o700)
    files = {}
    for name in FILES:
        source = ROOT / name
        if source.is_symlink() or not source.is_file():
            raise ValueError('Expected a regular allowlisted application file')
        files[name] = source.read_bytes()
    for source_id in SOURCE_IDS:
        path = ROOT / '.data/research/sources' / (source_id + '.json')
        if path.is_symlink():
            raise ValueError('Frozen source cannot be a symlink')
        source = research_sources.validate_snapshot(json.loads(path.read_text()), '2026-09-12')
        files['data/sandbox-sources/' + source_id + '.json'] = (
            json.dumps(source, sort_keys=True, ensure_ascii=False) + '\n').encode()
    if sum(map(len, files.values())) > 2_000_000:
        raise ValueError('Offline bundle exceeds the reviewed size envelope')
    manifest = {'schema_version': 1, 'purpose': 'offline-research-and-recovery-validation',
                'files': [{'path': name, 'bytes': len(data), 'sha256': sha(data)}
                          for name, data in sorted(files.items())],
                'limits': {'size': 's', 'memory_gib': 2, 'disk_gib': 8, 'max_boxes': 1,
                           'max_running_seconds': MAX_SECONDS, 'reserved_usd': str(RESERVE_USD)},
                'network': {'ingress_ports': [], 'egress_policy': {'no_network': True}},
                'guest_credentials': False}
    for name, data in files.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (destination / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True, indent=2) + '\n')
    return {'bundle': str(destination.resolve()),
            'manifest_sha256': sha((destination / 'manifest.json').read_bytes()),
            'files': len(files), 'bytes': sum(map(len, files.values())), 'reserved_usd': str(RESERVE_USD)}


def validate_bundle(bundle, expected):
    bundle = Path(bundle)
    raw = (bundle / 'manifest.json').read_bytes()
    if sha(raw) != expected:
        raise ValueError('Bundle manifest differs from the reviewed artifact')
    manifest = json.loads(raw)
    allowed = set(FILES) | {'data/sandbox-sources/' + source_id + '.json' for source_id in SOURCE_IDS}
    if ({item['path'] for item in manifest['files']} != allowed or
            len(manifest['files']) != len(allowed)):
        raise ValueError('Upload manifest differs from the application/public-evidence allowlist')
    result = {'manifest.json': raw}
    for item in manifest['files']:
        path = bundle / item['path']
        if path.is_symlink() or not path.is_file():
            raise ValueError('Bundle contains a missing file or symlink')
        data = path.read_bytes()
        if sha(data) != item['sha256'] or len(data) != item['bytes']:
            raise ValueError('Frozen upload bytes changed after manifest review')
        result[item['path']] = data
    if sum(map(len, result.values())) > 2_100_000:
        raise ValueError('Upload exceeds the bundle envelope')
    return result


def api(method, route, body=None, request_id=None):
    headers = {'Authorization': 'Bearer ' + load_api_key(), 'Content-Type': 'application/json'}
    if request_id:
        headers['Idempotency-Key'] = request_id
    data = json.dumps(body, sort_keys=True).encode() if body is not None else None
    request = Request('https://sailbox-api.sailresearch.com' + route,
                      data=data, headers=headers, method=method)
    try:
        with build_opener(NoRedirect).open(request, timeout=20) as response:
            raw = response.read(2_100_000)
            return json.loads(raw) if raw else {}
    except HTTPError as error:
        raise SailboxHTTPError(error.code) from None
    except (URLError, TimeoutError, ValueError):
        raise RuntimeError('Sailbox transport result is unconfirmed; inspect the operation journal') from None


def _identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z]+_[A-Za-z0-9_-]+', value):
        raise ValueError('Unexpected Sailbox API resource identifier')
    return value


def create_body(app_id, name):
    return {'app_id': _identifier(app_id), 'name': name, 'image': {'base': 'BASE_IMAGE_DEBIAN'},
            'size': 's', 'memory_limit_gib': 2, 'state_disk_limit_gib': 8,
            'visibility': 'private', 'ingress_ports': [], 'volume_mounts': [],
            'auto_sleep': {'automatic': True, 'min_seconds_before_sleep': 30},
            # Current documentation and deployed SDK/server disagree on this field.
            # Request the same restriction through both contracts; trust readback only.
            'egress_policy': {'no_network': True}, 'network_policy': {'mode': 'no_network'}}


def validate_isolation(row):
    policy = row.get('egress_policy') or {}
    document = policy.get('document') or {}
    restrictions = []
    if row.get('network_policy') is not None:
        restrictions.append(row['network_policy'].get('mode') == 'no_network')
    if document:
        restrictions.append(document.get('no_network') is True)
    if (not restrictions or not all(restrictions) or row.get('visibility') != 'private' or
            row.get('memory_mib') != 2048 or row.get('vcpu_count') != 1 or
            row.get('state_disk_size_gib') != 8 or row.get('volume_mounts') != [] or
            row.get('ingress_ports') not in ([], None)):
        raise ValueError('Sailbox did not confirm the requested isolation and resource ceilings')


def costs(value):
    result = {}
    for key in ('estimated_total_cost_usd_nanos', 'finalized_cost_usd_nanos',
                'estimated_active_cost_usd_nanos'):
        item = value.get(key)
        if type(item) is not int or item < 0:
            raise ValueError('Missing or invalid Sailbox nanodollar accounting')
        result[key.replace('_usd_nanos', '_usd')] = format(Decimal(item) / 1_000_000_000, 'f')
    return result


def maximum_cost(rates):
    required = ('vcpu_second_usd_nanos', 'memory_gib_second_usd_nanos',
                'state_disk_gib_second_usd_nanos', 's_creation_usd_nanos')
    if not isinstance(rates, dict) or any(type(rates.get(key)) is not int or rates[key] < 0 for key in required):
        raise ValueError('Could not confirm current Sailbox prices')
    second = rates[required[0]] + 2 * rates[required[1]] + 8 * rates[required[2]]
    return Decimal(second * MAX_SECONDS + rates[required[3]]) / 1_000_000_000


def _cleanup(state):
    ids = [state['sailbox_id']] if state.get('sailbox_id') else []
    if not ids and state.get('app_id'):
        offset = 0
        while True:
            page = api('GET', '/v1/sailboxes?' + urlencode({'app': state['app_id'], 'search': state['name'],
                                                           'limit': 100, 'offset': offset}))
            rows = page.get('data', [])
            ids.extend(row['sailbox_id'] for row in rows if row.get('name') == state['name'] and
                       row.get('app_id') == state['app_id'])
            if not page.get('has_more'):
                break
            if not rows:
                raise ValueError('Sailbox reconciliation pagination did not advance')
            offset += len(rows)
    cleaned = []
    for box_id in ids:
        box_id = _identifier(box_id)
        api('POST', '/v1/sailboxes/' + box_id + '/terminate', {}, state['operations']['terminate'])
        until = time.time() + 30
        while True:
            row = api('GET', '/v1/sailboxes/' + box_id)
            if row.get('status') == 'terminated' or time.time() >= until:
                break
            time.sleep(2)
        cleaned.append({'sailbox_id': box_id, 'status': row.get('status')})
    return cleaned


def watchdog(path):
    """Independent local cleanup deadline; the guest never receives credentials."""
    path = Path(path)
    while True:
        state = json.loads(path.read_text())
        if state.get('finished'):
            return
        if time.time() >= state['deadline']:
            break
        time.sleep(min(5, max(0.1, state['deadline'] - time.time())))
    result = {'triggered': True}
    try:
        result['cleanup'] = _cleanup(state)
    except Exception as error:
        result['error'] = _diagnostic(error, 'watchdog_cleanup')
    _write(path.with_name('watchdog-result.json'), result)


def run(bundle, manifest_hash):
    import sail
    from lab import api as inference_api
    files = validate_bundle(bundle, manifest_hash)
    directory = Path(bundle).parent / (Path(bundle).name + '-run')
    if directory.exists():
        raise ValueError('This proof has an existing run journal; reconcile it before another resource create')
    prior_cost = Decimal(0)
    prior_seconds = 0
    prior_paths = list(Path(bundle).parent.glob('*-run/state.json'))
    if len(prior_paths) >= 2:
        raise ValueError('This proof session has used its two-creation limit')
    for previous_path in prior_paths:
        previous = json.loads(previous_path.read_text())
        if not previous.get('finished') or not previous.get('costs'):
            raise ValueError('Reconcile earlier proof cleanup and accounting before another resource create')
        prior_cost += Decimal(previous['costs']['estimated_total_cost_usd'])
        prior_seconds += max(0, previous.get('elapsed_seconds', previous_path.stat().st_mtime - previous['started']))
    remaining_seconds = int(MAX_SECONDS - prior_seconds)
    if remaining_seconds < 300:
        raise ValueError('Insufficient time remains in the aggregate proof allowance')
    summary = inference_api('GET', '/v2/usage/summary?range=period')
    if (summary.get('available') is not True or summary.get('balance_unavailable') is not False or
            type(summary.get('balance')) not in (int, float) or
            not Decimal(str(summary['balance'])).is_finite() or
            Decimal(str(summary['balance'])) < RESERVE_USD * 100):
        raise ValueError('Could not confirm enough Sail credit for the reserved VM allowance')
    rates = api('GET', '/v1/sailboxes/spend').get('rates')
    ceiling = maximum_cost(rates)
    if ceiling + prior_cost > RESERVE_USD:
        raise ValueError('Current Sailbox prices exceed the reserved VM allowance')
    directory.mkdir(mode=0o700)
    path = directory / 'state.json'
    proof_id = uuid.uuid4().hex
    started = time.time()
    state = {'schema_version': 1, 'manifest_sha256': manifest_hash, 'name': 'portfolio-proof-' + proof_id,
             'started': started, 'deadline': started + remaining_seconds, 'reserved_usd': str(RESERVE_USD),
             'prior_cost_usd': format(prior_cost, 'f'), 'prior_controller_seconds': prior_seconds,
             'phase': 'reserved', 'finished': False, 'steps': [],
             'rates': rates, 'configured_maximum_usd': format(ceiling, 'f'),
             'controller_sha256': sha(Path(__file__).read_bytes()),
             'operations': {name: str(uuid.uuid4()) for name in
                            ('create', 'seed', 'checkpoint', 'sleep', 'pause', 'resume', 'verify', 'terminate')}}
    _write(path, state)
    monitor = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '_watchdog', str(path)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    prior_key = os.environ.get('SAIL_API_KEY')
    os.environ['SAIL_API_KEY'] = load_api_key()
    def step(name, **details):
        state['phase'] = name
        state['steps'].append({'stage': name, 'elapsed_seconds': round(time.time() - started, 3), **details})
        state['elapsed_seconds'] = round(time.time() - started, 3)
        _write(path, state)
        print(json.dumps({'stage': name, **details}), flush=True)
        if time.time() > state['deadline']:
            raise RuntimeError('Sailbox proof reached its external cleanup deadline')
    def wait_status(wanted, limit=180):
        until = min(time.time() + limit, state['deadline'])
        while True:
            row = api('GET', '/v1/sailboxes/' + state['sailbox_id'])
            if row.get('status') in wanted:
                return row
            if time.time() > until or row.get('status') in {'error', 'terminated'}:
                raise RuntimeError('Sailbox lifecycle did not reach the expected state')
            time.sleep(3)
    try:
        app = sail.App.find(APP_NAME, mint_if_missing=True)
        state['app_id'] = app.id
        step('creating')
        created = api('POST', '/v1/sailboxes', create_body(app.id, state['name']), state['operations']['create'])
        state['sailbox_id'] = _identifier(created.get('sailbox_id'))
        step('created', sailbox_id=state['sailbox_id'])
        row = wait_status({'running'})
        validate_isolation(row)
        listeners = api('GET', '/v1/sailboxes/' + state['sailbox_id'] + '/listeners')
        if listeners.get('data') != []:
            raise ValueError('Sailbox unexpectedly exposes a listener')
        state['isolation_verified'] = {'egress': 'no_network', 'visibility': 'private',
                                       'vcpu': 1, 'memory_mib': 2048, 'disk_gib': 8,
                                       'listeners': 0, 'volumes': 0,
                                       'policy_contract': 'network_policy' if row.get('network_policy') else 'egress_policy'}
        step('isolation_verified', **state['isolation_verified'])
        # The current REST egress field is newer than the pinned SDK's create wrapper.
        # A bound SDK handle is used only for plain file and process operations.
        box = sail.Sailbox.from_id(state['sailbox_id'])
        for name, data in files.items():
            box.fs.write(REMOTE + '/' + name, data, create_parents=True, mode=0o644)
        step('uploaded', files=len(files), bytes=sum(map(len, files.values())))
        result = box.exec('python3 scripts/sandbox_validation.py seed', cwd=REMOTE, timeout=300,
                          idempotency_key=state['operations']['seed'], output_mode='tail').wait()
        if result.exit_code != 0 or result.timed_out:
            raise RuntimeError('Clean-VM offline research suite failed')
        seed_data = json.loads(box.fs.read(REMOTE + '/.proof/seed.json'))
        _write(directory / 'seed.json', seed_data)
        step('offline_suite_passed', **seed_data['tests'])
        checkpoint = api('POST', '/v1/sailboxes/' + state['sailbox_id'] + '/checkpoint',
                         {'name': 'research-state-' + proof_id, 'ttl_seconds': 300},
                         state['operations']['checkpoint'])
        # Preserve only operational checkpoint identifiers, not provider internals.
        state['checkpoint'] = {key: checkpoint[key] for key in ('checkpoint_id', 'expires_at', 'status')
                               if key in checkpoint}
        _write(path, state)
        if (checkpoint.get('sailbox_id') != state['sailbox_id'] or
                type(checkpoint.get('checkpoint_generation')) is not int or
                checkpoint['checkpoint_generation'] < 1):
            raise ValueError('Could not confirm a saved Sailbox checkpoint')
        step('checkpoint_saved')
        api('POST', '/v1/sailboxes/' + state['sailbox_id'] + '/sleep', {}, state['operations']['sleep'])
        wait_status({'sleeping'})
        step('sleep_confirmed')
        api('POST', '/v1/sailboxes/' + state['sailbox_id'] + '/pause', {}, state['operations']['pause'])
        wait_status({'paused'})
        step('pause_confirmed')
        api('POST', '/v1/sailboxes/' + state['sailbox_id'] + '/resume', {}, state['operations']['resume'])
        row = wait_status({'running'})
        validate_isolation(row)
        step('resume_confirmed')
        result = box.exec('python3 scripts/sandbox_validation.py verify', cwd=REMOTE, timeout=180,
                          idempotency_key=state['operations']['verify'], output_mode='tail').wait()
        if result.exit_code != 0 or result.timed_out:
            raise RuntimeError('Clean-VM saved-state recovery failed')
        verified = json.loads(box.fs.read(REMOTE + '/.proof/verified.json'))
        _write(directory / 'verified.json', verified)
        step('recovery_verified', reservations=verified['reservations'],
             new_submissions=verified['new_submissions'])
        state['passed'] = True
    except BaseException as error:
        state['error'] = _diagnostic(error, state['phase'])
        state['passed'] = False
        _write(path, state)
        raise RuntimeError('Sailbox proof did not complete; inspect the private operation journal') from None
    finally:
        try:
            state['cleanup'] = _cleanup(state)
            # An empty list immediately after an ambiguous create is not proof
            # that allocation cannot appear later. Keep the watchdog alive.
            state['finished'] = bool(state['cleanup']) and all(
                item['status'] == 'terminated' for item in state['cleanup'])
            if not state['cleanup'] and state['phase'] == 'reserved':
                state['finished'] = True
        except Exception as error:
            state['cleanup_error'] = _diagnostic(error, 'cleanup')
        if state.get('sailbox_id'):
            try:
                usage = api('GET', '/v1/sailboxes/spend?' + urlencode({'sailbox_id': state['sailbox_id'],
                            'from': datetime.fromtimestamp(started, timezone.utc).isoformat()}))
                state['costs'] = costs(usage)
            except Exception as error:
                state['cost_error'] = _diagnostic(error, 'cost_accounting')
        _write(path, state)
        if prior_key is None:
            os.environ.pop('SAIL_API_KEY', None)
        else:
            os.environ['SAIL_API_KEY'] = prior_key
        if state.get('finished'):
            try:
                monitor.wait(timeout=6)
            except subprocess.TimeoutExpired:
                pass
    return {'passed': state['passed'], 'journal': str(path), 'cleanup': state.get('cleanup'),
            'costs': state.get('costs'), 'manifest_sha256': manifest_hash}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('prepare').add_argument('destination', type=Path)
    command = commands.add_parser('run')
    command.add_argument('bundle', type=Path)
    command.add_argument('--manifest-sha256', required=True)
    commands.add_parser('_watchdog').add_argument('state', type=Path)
    args = parser.parse_args()
    if args.command == 'prepare':
        result = prepare(args.destination)
    elif args.command == 'run':
        result = run(args.bundle, args.manifest_sha256)
    else:
        watchdog(args.state)
        return
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, OSError) as error:
        raise SystemExit('Sailbox proof stopped: ' + type(error).__name__ +
                         '. Inspect the private journal; no raw provider diagnostics are printed.') from None
