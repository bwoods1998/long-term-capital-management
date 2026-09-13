"""A real research cycle with Sail inference and an isolated Sailbox tool worker.

The MacBook keeps the only request/budget ledger and credentials. The guest gets
an exact code/evidence bundle, executes allowlisted tools, and saves receipts.
Commands advance one saved cycle; they never approve or publish model prose.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.parse import urlencode
import uuid

import investigator
import portfolio as ledger
import research_sources as sources
import sail_sandbox as sandbox
import sail_tracking as tracking

ROOT = Path(__file__).resolve().parent
REMOTE = '/workspace/portfolio-research'
SESSION_ROOT = ROOT / '.data' / 'cloud-research'
FILES = ('research_sources.py', 'scripts/research_tools_guest.py')
MAX_SECONDS = 7200
MAX_COMPUTE_USD = Decimal('1')
QUESTION = ('Can Microsoft preserve cash after infrastructure investment as spending grows? '
            'Check the annual cash-flow arithmetic, distinguish cash spending from total commitments, '
            'and identify the next evidence that would strengthen or weaken the case.')


def _write(path, value):
    tracking._write(Path(path), value)


def _load(directory):
    path = Path(directory).resolve()
    if path.parent != SESSION_ROOT.resolve() or path.is_symlink():
        raise ValueError('Use a session inside the private cloud-research directory')
    return path, json.loads((path / 'state.json').read_text())


@contextmanager
def _lock(directory):
    fd = os.open(Path(directory) / 'controller.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('A controller is already advancing this research cycle') from None
        yield
    finally:
        os.close(fd)


@contextmanager
def _credentials():
    previous = os.environ.get('SAIL_API_KEY')
    os.environ['SAIL_API_KEY'] = sandbox.load_api_key()
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop('SAIL_API_KEY', None)
        else:
            os.environ['SAIL_API_KEY'] = previous


def prepare(name):
    if not isinstance(name, str) or not __import__('re').fullmatch(r'[a-z0-9-]{1,60}', name):
        raise ValueError('Use a short lowercase session name')
    SESSION_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory = SESSION_ROOT / name
    directory.mkdir(mode=0o700)
    bundle = directory / 'bundle'
    bundle.mkdir(mode=0o700)
    packet = ledger.load_packet()
    store = sources.SourceStore(ROOT)
    files = {filename: (ROOT / filename).read_bytes() for filename in FILES}
    files['packet.json'] = (ledger.encoded(packet) + '\n').encode()
    source_ids = sorted(item['id'] for item in packet['sources'])
    for source_id in source_ids:
        files['sources/' + source_id + '.json'] = (ledger.encoded(store.capture(source_id)) + '\n').encode()
    manifest = {'schema_version': 1, 'source_ids': source_ids,
                'files': [{'path': key, 'bytes': len(raw), 'sha256': sandbox.sha(raw)}
                          for key, raw in sorted(files.items())],
                'guest_credentials': False, 'guest_network': 'no_network',
                'question': QUESTION, 'research_turn_limit': 8,
                'max_seconds': MAX_SECONDS, 'max_compute_usd': str(MAX_COMPUTE_USD)}
    for filename, raw in files.items():
        path = bundle / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    manifest_raw = (ledger.encoded(manifest) + '\n').encode()
    (bundle / 'manifest.json').write_bytes(manifest_raw)
    state = {'schema_version': 1, 'phase': 'prepared', 'finished': False,
             'name': 'portfolio-case-' + uuid.uuid4().hex, 'steps': [], 'tool_receipts': {},
             'manifest_sha256': sandbox.sha(manifest_raw),
             'investigation_id': str(uuid.uuid4()), 'question': QUESTION,
             'credential_fingerprint': ledger.credential_fingerprint(),
             'operations': {key: str(uuid.uuid4()) for key in ('create', 'terminate')},
             'compute_allowance_usd': str(MAX_COMPUTE_USD), 'max_seconds': MAX_SECONDS}
    _write(directory / 'state.json', state)
    return {'session': str(directory), 'phase': 'prepared', 'files': len(files),
            'manifest_sha256': state['manifest_sha256'], 'question': QUESTION}


def _bundle(directory, state):
    bundle = directory / 'bundle'
    raw = (bundle / 'manifest.json').read_bytes()
    if sandbox.sha(raw) != state['manifest_sha256']:
        raise ValueError('Prepared manifest changed')
    manifest = json.loads(raw)
    expected = set(FILES) | {'packet.json'} | {'sources/' + key + '.json' for key in manifest['source_ids']}
    if {item['path'] for item in manifest['files']} != expected or len(manifest['files']) != len(expected):
        raise ValueError('Bundle differs from the public-file allowlist')
    result = {'manifest.json': raw}
    for item in manifest['files']:
        path = bundle / item['path']
        if path.is_symlink() or not path.is_file():
            raise ValueError('Invalid bundle file')
        raw = path.read_bytes()
        if sandbox.sha(raw) != item['sha256'] or len(raw) != item['bytes']:
            raise ValueError('Prepared source/code bytes changed')
        result[item['path']] = raw
    if sum(map(len, result.values())) > 500000:
        raise ValueError('Public evidence bundle exceeds its envelope')
    return result


def _record(directory, state, phase, **metrics):
    state['phase'] = phase
    state['steps'].append({'at': ledger.iso(time.time()), 'phase': phase, **metrics})
    _write(directory / 'state.json', state)


def _bound(state):
    if ledger.credential_fingerprint() != state['credential_fingerprint']:
        raise ValueError('The research cycle belongs to a different credential')
    if state.get('finished') or time.time() >= state.get('deadline', 0):
        raise ValueError('Research worker is closed or past its deadline')
    if (state.get('isolation_verified') is not True or not state.get('sailbox_id') or
            state.get('phase') not in {'ready', 'tool_completed', 'sleeping', 'resumed',
                                      'sleep_requested', 'resuming'}):
        raise ValueError('The isolated research worker has not been verified ready')
    sandbox._identifier(state['sailbox_id'])


def _wait(state, wanted, seconds=180):
    until = min(time.time() + seconds, state['deadline'])
    while True:
        row = sandbox.api('GET', '/v1/sailboxes/' + state['sailbox_id'])
        if row.get('status') in wanted:
            return row
        if time.time() >= until or row.get('status') in {'terminated', 'error'}:
            raise RuntimeError('Sailbox did not reach the expected state')
        time.sleep(2)


def create(directory):
    # All prepared sessions share the same compute envelope. Hold one global
    # admission lock until the created resource is recorded or reconciled.
    with _lock(SESSION_ROOT):
        return _create(directory)


def _create(directory):
    import sail
    directory, state = _load(directory)
    files = _bundle(directory, state)
    if state['phase'] != 'prepared':
        raise ValueError('Creation was already attempted; reconcile the saved identity before any new create')
    if ledger.credential_fingerprint() != state['credential_fingerprint']:
        raise ValueError('Prepared cycle belongs to a different credential')
    prior = Decimal('0.010')  # The two finalized, recorded isolation trials.
    for path in SESSION_ROOT.glob('*/state.json'):
        if path.parent == directory:
            continue
        other = json.loads(path.read_text())
        if other['phase'] == 'prepared':
            continue
        if not other.get('finished') or not other.get('costs'):
            raise ValueError('An earlier cloud cycle needs cleanup or cost reconciliation')
        prior += Decimal(other['costs']['estimated_total_cost_usd'])
    if prior + MAX_COMPUTE_USD > Decimal('4'):
        raise ValueError('The shared compute allocation is exhausted')
    rates = sandbox.api('GET', '/v1/sailboxes/spend').get('rates')
    keys = ('vcpu_second_usd_nanos', 'memory_gib_second_usd_nanos',
            'state_disk_gib_second_usd_nanos', 's_creation_usd_nanos')
    if not isinstance(rates, dict) or any(type(rates.get(k)) is not int or rates[k] < 0 for k in keys):
        raise ValueError('Current Sailbox prices are unavailable')
    maximum = Decimal((rates[keys[0]] + 2*rates[keys[1]] + 8*rates[keys[2]]) * MAX_SECONDS + rates[keys[3]]) / 10**9
    if maximum > MAX_COMPUTE_USD:
        raise ValueError('Current resource prices exceed the compute allowance')
    state.update({'started': time.time(), 'deadline': time.time() + MAX_SECONDS, 'rates': rates,
                  'configured_maximum_usd': str(maximum)})
    app = sail.App.find('portfolio-living-case', mint_if_missing=True)
    state['app_id'] = app.id
    _record(directory, state, 'creating')
    monitor = subprocess.Popen([sys.executable, str(ROOT / 'sail_sandbox.py'), '_watchdog',
                                str(directory / 'state.json')],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    state['watchdog_pid'] = monitor.pid
    _write(directory / 'state.json', state)
    try:
        row = sandbox.api('POST', '/v1/sailboxes', sandbox.create_body(app.id, state['name']),
                          state['operations']['create'])
        state['sailbox_id'] = sandbox._identifier(row.get('sailbox_id'))
        _record(directory, state, 'created')
        sandbox.validate_isolation(_wait(state, {'running'}))
        if sandbox.api('GET', '/v1/sailboxes/' + state['sailbox_id'] + '/listeners').get('data') != []:
            raise ValueError('Unexpected public listener')
        box = sail.Sailbox.from_id(state['sailbox_id'])
        for filename, raw in files.items():
            box.fs.write(REMOTE + '/' + filename, raw, create_parents=True, mode=0o644)
        for filename, raw in files.items():
            if box.fs.read(REMOTE + '/' + filename) != raw:
                raise ValueError('Remote upload does not match its frozen bytes')
        state['isolation_verified'] = True
        _record(directory, state, 'ready', uploaded_files=len(files))
    except BaseException:
        _record(directory, state, 'needs_attention')
        finish(directory)
        raise
    return summary(directory)


class ToolStore:
    def __init__(self, directory):
        self.directory, self.state = _load(directory)
        _bound(self.state)
        self.files = _bundle(self.directory, self.state)
        self.investigation_id = self.state['investigation_id']
        self.descriptor = {'kind': 'sailbox-tools-v1', 'manifest_sha256': self.state['manifest_sha256']}

    def capture(self, source_id, cutoff=None):
        sources.allowed_source(source_id)
        return sources.validate_snapshot(json.loads(self.files['sources/' + source_id + '.json']), cutoff)

    def _awake(self):
        _bound(self.state)
        row = sandbox.api('GET', '/v1/sailboxes/' + self.state['sailbox_id'])
        if row.get('status') in {'sleeping', 'paused'}:
            key = self.state.get('pending_resume')
            if key is None:
                key = str(uuid.uuid4())
                self.state['pending_resume'] = key
                _record(self.directory, self.state, 'resuming', operation=key)
            sandbox.api('POST', '/v1/sailboxes/' + self.state['sailbox_id'] + '/resume', {}, key)
            row = _wait(self.state, {'running'})
            self.state.pop('pending_resume', None)
            _record(self.directory, self.state, 'resumed')
        elif row.get('status') == 'running' and self.state.get('pending_resume'):
            self.state.pop('pending_resume')
            _record(self.directory, self.state, 'resumed')
        if row.get('status') != 'running':
            raise RuntimeError('Research worker is not running')
        sandbox.validate_isolation(row)

    def dispatch(self, name, args, packet, snapshots, *, cutoff, call_id):
        import sail
        if ledger.digest(packet) != ledger.digest(json.loads(self.files['packet.json'])):
            raise ValueError('Research packet differs from frozen worker evidence')
        # Local verification also checks argument/scope validity before paid exec.
        expected = sources.dispatch(name, args, packet, snapshots, cutoff=cutoff)
        key = ledger.digest({'investigation': self.state['investigation_id'], 'call_id': call_id})
        request = {'schema_version': 1, 'call_key': key, 'name': name, 'args': args, 'cutoff': cutoff,
                   'manifest_sha256': self.state['manifest_sha256']}
        directory = self.directory / 'tools'
        directory.mkdir(exist_ok=True, mode=0o700)
        path = directory / (key + '.json')
        if path.exists():
            frozen = json.loads(path.read_text())
            if frozen['request'] != request:
                raise ValueError('A repeated tool identity changed arguments')
        else:
            frozen = {'request': request, 'exec_idempotency_key': str(uuid.uuid4()), 'receipt': None}
            _write(path, frozen)
        if frozen['receipt'] is None:
            self._awake()
            box = sail.Sailbox.from_id(self.state['sailbox_id'])
            box.fs.write(REMOTE + '/requests/' + key + '.json', ledger.encoded(request).encode(),
                         create_parents=True, mode=0o644)
            result = box.exec('python3 scripts/research_tools_guest.py ' + key, cwd=REMOTE,
                              timeout=60, idempotency_key=frozen['exec_idempotency_key'], output_mode='tail').wait()
            if result.exit_code != 0 or result.timed_out:
                raise RuntimeError('Remote evidence tool did not finish; its identity is preserved')
            receipt = json.loads(box.fs.read(REMOTE + '/receipts/' + key + '.json'))
            frozen['receipt'] = receipt
            _write(path, frozen)
        receipt = frozen['receipt']
        if (set(receipt) != {'schema_version', 'call_key', 'manifest_sha256', 'request_sha256',
                            'success', 'result', 'result_sha256'} or
                receipt['schema_version'] != 1 or receipt['call_key'] != key or
                receipt['manifest_sha256'] != self.state['manifest_sha256'] or
                receipt['request_sha256'] != ledger.digest(request) or receipt['success'] is not True or
                receipt['result_sha256'] != ledger.digest(expected) or receipt['result'] != expected):
            raise ValueError('Remote evidence result failed local verification')
        self.state['tool_receipts'][key] = {'name': name, 'receipt_sha256': ledger.digest(receipt)}
        _record(self.directory, self.state, 'tool_completed', tool=name)
        return receipt['result']


def sleep(directory):
    directory, state = _load(directory)
    _bound(state)
    key = state.get('pending_sleep')
    if key is None:
        key = str(uuid.uuid4())
        state['pending_sleep'] = key
        _record(directory, state, 'sleep_requested', operation=key)
    sandbox.api('POST', '/v1/sailboxes/' + state['sailbox_id'] + '/sleep', {}, key)
    _wait(state, {'sleeping'})
    state.pop('pending_sleep', None)
    _record(directory, state, 'sleeping')
    return summary(directory)


def advance(directory):
    directory, state = _load(directory)
    _bound(state)
    store = ToolStore(directory)
    with ledger.database() as db:
        investigator.setup(db)
        if not db.execute('SELECT 1 FROM investigations WHERE id=?', (state['investigation_id'],)).fetchone():
            investigator.start(db, question=state['question'], max_turns=8,
                               deadline=state['deadline'], packet=json.loads(store.files['packet.json']),
                               investigation_id=state['investigation_id'], tool_backend=store.descriptor)
        with tracking.run('cloud-case:' + state['investigation_id'], enabled=True) as trace:
            result = investigator.advance(db, state['investigation_id'], store, poll_seconds=0)
            if result['phase'] in investigator.STOPPED:
                if result['phase'] in {'awaiting_review', 'reviewed'}:
                    trace.complete()
                else:
                    trace.fail()
        _, state = _load(directory)  # Tool worker may have appended receipts/events.
        state['research'] = result
        _write(directory / 'state.json', state)
    return result


def finish(directory):
    directory, state = _load(directory)
    # Termination/reconciliation remains allowed after the work deadline.
    if ledger.credential_fingerprint() != state['credential_fingerprint']:
        raise ValueError('Cleanup requires the original credential')
    state['cleanup'] = sandbox._cleanup(state)
    state['finished'] = bool(state['cleanup']) and all(row['status'] == 'terminated' for row in state['cleanup'])
    if state.get('sailbox_id'):
        usage = sandbox.api('GET', '/v1/sailboxes/spend?' + urlencode({
            'sailbox_id': state['sailbox_id'], 'from': datetime.fromtimestamp(state['started'], timezone.utc).isoformat()}))
        state['costs'] = sandbox.costs(usage)
    _record(directory, state, 'closed' if state['finished'] else 'cleanup_unconfirmed')
    return summary(directory)


def summary(directory):
    _, state = _load(directory)
    return {key: state.get(key) for key in ('phase', 'finished', 'research', 'costs', 'manifest_sha256')} | {
        'remote_tools': len(state['tool_receipts']),
        'sleep_observed': any(x['phase'] == 'sleeping' for x in state['steps']),
        'resume_observed': any(x['phase'] == 'resumed' for x in state['steps'])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'create', 'step', 'sleep', 'finish', 'status'))
    parser.add_argument('session')
    args = parser.parse_args()
    if args.command == 'prepare':
        result = prepare(args.session)
    elif args.command == 'status':
        result = summary(args.session)
    else:
        directory, _ = _load(args.session)
        with _lock(directory), _credentials():
            result = {'create': create, 'step': advance, 'sleep': sleep, 'finish': finish}[args.command](directory)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        raise SystemExit('Cloud research stopped: ' + type(error).__name__ +
                         '. Inspect its private journal before retrying.') from None
