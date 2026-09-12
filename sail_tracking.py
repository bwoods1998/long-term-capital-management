"""Optional, resumable Voyage telemetry for the existing private research harness.

No SDK import or network I/O occurs unless run(..., enabled=True) is entered.
Only workflow hashes, bounded identifiers and numeric metrics enter trace events.
Prompts and responses reach Sail through the existing inference transport only.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import fcntl
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import re
from urllib.parse import urlparse
import uuid

ROOT = Path(__file__).resolve().parent
_active = ContextVar('portfolio_voyage', default=None)
_HEADERS = {'X-Sail-Voyage-Id', 'X-Sail-Voyage-Span-Id', 'X-Sail-Voyage-Agent-Id'}
_TERMINAL = {'completed', 'failed', 'cancelled'}
_COUNTERS = {'step', 'round', 'turn', 'count', 'attempt', 'tool_count', 'source_count',
             'input_tokens', 'output_tokens', 'cached_tokens', 'reasoning_tokens',
             'duration_seconds', 'elapsed_seconds', 'reserved_cents', 'estimated_usd',
             'score', 'passed', 'failed', 'completed', 'accepted', 'bytes', 'evidence_count',
             'before_bytes', 'after_bytes', 'passage_count'}
_LABELS = {'model', 'tool', 'stage', 'status', 'purpose', 'response_id', 'run_id'}


def _label(value, limit=120):
    if (not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:/-]*', value)
            or len(value) > limit or value.startswith(('sk_', 'sk-', 'Bearer'))):
        raise ValueError('Telemetry labels must be bounded identifiers, never prose or credentials')
    return value


def _metrics(payload):
    if payload is None:
        return {}
    if not isinstance(payload, dict) or set(payload) - (_COUNTERS | _LABELS):
        raise ValueError('Telemetry accepts only approved identifiers and numeric metrics')
    result = {}
    for key, value in payload.items():
        if key in _COUNTERS:
            if type(value) not in (bool, int, float) or not math.isfinite(value) or abs(value) > 10**12:
                raise ValueError('Invalid telemetry metric')
            result[key] = value
        else:
            result[key] = _label(value)
    return result


def _write(path, state):
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as file:
        json.dump(state, file, sort_keys=True, allow_nan=False)
        file.write('\n')
        file.flush()
        os.fsync(file.fileno())
    temporary.replace(path)


def _dashboard(value):
    if value is None:
        return None
    parsed = urlparse(value)
    if (parsed.scheme != 'https' or parsed.netloc != 'app.sailresearch.com' or
            parsed.username or parsed.password or parsed.query or parsed.fragment):
        raise ValueError('Unexpected Voyage dashboard URL')
    return value


def _diagnostic(error, stage):
    """Classify startup failures without serializing exception/provider text."""
    result = {'stage': stage, 'error_type': type(error).__name__[:80]}
    status = getattr(error, 'status_code', None)
    if type(status) is int and 100 <= status <= 599:
        result['http_status'] = status
    message = str(error).lower()
    for category, markers in [('dns', ('dns', 'name resolution', 'resolve host', 'name or service not known')),
                              ('timeout', ('timed out', 'timeout')),
                              ('connect', ('connection refused', 'connect error', 'network unreachable'))]:
        if any(marker in message for marker in markers):
            result['transport_category'] = category
            break
    return result


class Trace:
    def __init__(self, voyage=None, path=None, state=None):
        self.voyage = voyage
        self.path = path
        self.state = state or {}
        self.delivery_confirmed = False

    @property
    def dashboard_url(self):
        return self.state.get('dashboard_url')

    @property
    def voyage_id(self):
        return self.state.get('voyage_id')

    def _terminal(self, status):
        if self.voyage is None or self.state.get('status') in _TERMINAL:
            return
        if status == 'completed':
            self.voyage.complete(message='Research workflow completed')
        else:
            self.voyage.fail(error_type='research_workflow_failed', message='Inspect private local workflow status')
        self.state['status'] = status
        _write(self.path, self.state)

    def complete(self):
        self._terminal('completed')

    def fail(self):
        self._terminal('failed')

    def flush(self):
        if self.voyage is None:
            return
        try:
            self.voyage.flush(timeout=10)
            self.delivery_confirmed = True
        except Exception:
            # Delivery failures must not expose raw provider errors or rerun paid work.
            self.delivery_confirmed = False
        self.state['delivery_confirmed'] = self.delivery_confirmed
        _write(self.path, self.state)


@contextmanager
def run(workflow_id, *, enabled=False, state_dir=None):
    """Create/attach one private trace; normal waiting exits remain resumable.

Call the yielded trace.complete()/fail() only when the workflow is terminal.
Creation is journaled before I/O; an ambiguous create is never retried blindly.
One controller per workflow is enforced locally for the lifetime of the context.
"""
    if not enabled:
        token = _active.set(None)
        try:
            yield Trace()
        finally:
            _active.reset(token)
        return
    if not isinstance(workflow_id, str) or not 1 <= len(workflow_id) <= 256:
        raise ValueError('Expected a bounded workflow identifier')
    if _active.get() is not None:
        raise ValueError('Nested Voyage controllers are not supported')
    from lab import load_api_key
    key = load_api_key()
    workflow_hash = hashlib.sha256(workflow_id.encode()).hexdigest()
    fingerprint = hashlib.sha256(key.encode()).hexdigest()
    directory = Path(state_dir) if state_dir is not None else ROOT / '.data/voyages'
    if directory.is_symlink():
        raise ValueError('Private Voyage state must not be a symlink')
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / (workflow_hash + '.json')
    lock_path = directory / (workflow_hash + '.lock')
    if path.is_symlink() or lock_path.is_symlink():
        raise ValueError('Private Voyage state must not be a symlink')
    lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lock_fd, 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another controller is recording this workflow') from None
        # SDK auth must use the same .env credential as our idempotent inference client.
        # The synchronous CLI owns this temporary environment for its invocation.
        overrides = {'SAIL_API_KEY': key, 'SAIL_VOYAGE_DEBUG': '0',
                     'SAIL_AGENT_ID': None, 'SAIL_AGENT_NAME': None, 'SAIL_AGENT_ROLE': None}
        previous = {name: os.environ.get(name) for name in overrides}
        for name, value in overrides.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        try:
            try:
                sail = importlib.import_module('sail')
            except ImportError:
                raise RuntimeError('Voyage telemetry requires: pip install -r requirements-sail.txt') from None
            state = json.loads(path.read_text()) if path.exists() else None
            if state is not None:
                if (state.get('schema_version') != 1 or state.get('workflow_sha256') != workflow_hash or
                        state.get('key_fingerprint') != fingerprint):
                    raise ValueError('Voyage state or credential changed; reconcile the private trace')
                if not state.get('voyage_id'):
                    raise RuntimeError('Voyage creation is unconfirmed; reconcile the dashboard before any new create')
            else:
                state = {'schema_version': 1, 'workflow_sha256': workflow_hash,
                         'key_fingerprint': fingerprint, 'status': 'creation_unconfirmed'}
                _write(path, state)
            startup_stage = 'attach' if state.get('voyage_id') else 'create'
            try:
                if state.get('voyage_id'):
                    voyage = sail.voyage.attach(_label(state['voyage_id']))
                else:
                    voyage = sail.voyage.create(name='portfolio-investigator', version=1,
                                                metadata={'workflow_sha256': workflow_hash})
                # Preserve the returned handle BEFORE optional URL/header validation.
                startup_stage = 'persist_identity'
                if isinstance(voyage.id, str) and 1 <= len(voyage.id) <= 256:
                    state['voyage_id'] = voyage.id
                    _write(path, state)
                startup_stage = 'identity_validation'
                _label(voyage.id)
                # Local terminal intent survives a lagging provider status on attach.
                status = state.get('status')
                if status not in _TERMINAL:
                    status = getattr(voyage, 'status', None) or 'running'
                startup_stage = 'dashboard_validation'
                state.update(dashboard_url=_dashboard(voyage.dashboard_url), status=status)
                state.pop('startup_error', None)
                _write(path, state)
            except Exception as error:
                state['startup_error'] = _diagnostic(error, startup_stage)
                _write(path, state)
                raise RuntimeError('Voyage startup could not be confirmed; inspect the private trace journal') from None
            trace = Trace(voyage, path, state)
            token = _active.set(trace)
            try:
                if state['status'] not in _TERMINAL:
                    event('workflow.resumed')
                yield trace
            except BaseException:
                # An interrupted invocation is not a terminal durable workflow.
                # Only the caller knows when saved work is completed or failed.
                if trace.state['status'] not in _TERMINAL:
                    event('workflow.interrupted')
                raise
            finally:
                trace.flush()
                _active.reset(token)
        finally:
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


def event(name, payload=None, **metrics):
    trace = _active.get()
    if trace is None or trace.voyage is None:
        return
    _require_running(trace)
    _label(name, 80)
    safe = _metrics(payload)
    safe.update(_metrics(metrics))
    trace.voyage.event(name, payload=safe)


@contextmanager
def stage(name, *, agent='Investigator', payload=None):
    """Named agent/span attribution without forwarding exception prose to Sail."""
    trace = _active.get()
    if trace is None or trace.voyage is None:
        yield
        return
    _require_running(trace)
    _label(name, 80)
    _label(agent, 80)
    with trace.voyage.agent(agent):
        span = trace.voyage.span(name, payload=_metrics(payload))
        span.__enter__()
        try:
            yield
        except BaseException:
            safe_error = RuntimeError('Research stage failed; inspect private local status')
            span.__exit__(RuntimeError, safe_error, None)
            raise
        else:
            span.__exit__(None, None, None)


def inference_headers():
    """Compute current attribution per HTTP request; never modify auth or retry keys."""
    trace = _active.get()
    if trace is None or trace.voyage is None:
        return {}
    _require_running(trace)
    supplied = trace.voyage.headers()
    return {name: _label(value, 160) for name, value in supplied.items() if name in _HEADERS}


def _require_running(trace):
    if trace.state.get('status') in _TERMINAL:
        raise ValueError('Terminal Voyage is available for inspection only')
