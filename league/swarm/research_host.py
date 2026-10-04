"""Explicit host launch for isolated research; no stock loop or credential factory.

The reviewed host adapter owns credentials and supplies scoped provider, GymDriver,
model and fresh host-context capabilities. Only the captured Bubblewrap controller
receives the authenticated Unix socket. An existing shared DailyBudget ledger is
required: startup never creates a second allowance or discards old obligations.

CLI cleanup is a separate host action against the one immutable broker-journal
resource. A lost creation remains unresolved; runtime termination is not an invoice.
No operation launches anything at import or accepts a controller-supplied provider ID.
"""

from __future__ import annotations

import argparse
import datetime as dt
import errno
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import signal
import socket
import stat
import threading
import time
from dataclasses import dataclass, fields
from typing import Callable, Mapping

from .daily_compute import DailyBudget, InventoryEvidence, ResourceBound, TariffEvidence
from .research_ipc import BrokerServer, create_listener
from .research_sandbox import (HostContextEvidence, SandboxSpec, _host_context, _verify_artifact,
                               launch_sandbox)
from .research_state import ArtifactIdentity, artifact_identity, assert_isolated_state
from .research_transport import (ModelCapability, ResearchBroker, ResearchPolicy,
                                 EVENT_KIND as BROKER_EVENT, STATE_KEY as BROKER_STATE)
from .store import SwarmStore

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_HEAD = re.compile(r"[0-9a-f]{40}\Z")
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,79}\Z")
_CHECKS = frozenset(("python311", "python314", "gateway", "content"))


class ResearchHostError(RuntimeError):
    pass


def _require(condition, reason):
    if not condition:
        raise ResearchHostError(reason)


def _clock(value):
    _require(type(value) in (int, float) and math.isfinite(value) and value >= 0, "invalid host clock")
    return float(value)


def _plain(path, *, directory=False):
    _require(isinstance(path, Path) and path.is_absolute() and path.resolve() == path,
             "plain absolute host path required")
    _require(not any(part.is_symlink() for part in (path, *path.parents)), "symlinked host path refused")
    if directory:
        info = path.stat()
        _require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700,
                 "owner-only host directory required")
    return path


def _json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, "duplicate host configuration field")
            result[key] = value
        return result
    try:
        return json.loads(raw, object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ResearchHostError("nonfinite host configuration")))
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise ResearchHostError("unreadable host configuration") from exc


@dataclass(frozen=True)
class ReviewedFile:
    path: Path
    sha256: str

    def read(self):
        _require(isinstance(self.sha256, str) and _SHA.fullmatch(self.sha256), "approved host file SHA256 required")
        path = _plain(self.path)
        info = path.stat()
        _require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and not stat.S_IMODE(info.st_mode) & 0o077,
                 "reviewed host input must be owner-only")
        raw = path.read_bytes()
        _require(len(raw) <= 4*1024*1024 and hashlib.sha256(raw).hexdigest() == self.sha256,
                 "reviewed host input changed or exceeds its bound")
        return raw


@dataclass(frozen=True)
class HostConfig:
    head: str
    artifact_root: Path
    artifact_files: tuple[tuple[str, str], ...]
    state_root: Path
    broker_root: Path
    socket_name: str
    config_relative: str
    policy_relative: str
    research_policy: ResearchPolicy
    tariff: TariffEvidence
    inventory: InventoryEvidence
    deployment_receipt: ReviewedFile
    adapter_file: ReviewedFile
    adapter_factory: str = "build_host_adapters"

    def __post_init__(self):
        _require(isinstance(self.head, str) and _HEAD.fullmatch(self.head), "exact reviewed source head required")
        _require(isinstance(self.socket_name, str) and re.fullmatch(r"[a-z0-9_-]{1,40}\.sock", self.socket_name),
                 "fixed private socket basename required")
        _require(isinstance(self.adapter_factory, str) and _NAME.fullmatch(self.adapter_factory), "reviewed adapter factory name required")
        _require(isinstance(self.research_policy, ResearchPolicy) and isinstance(self.tariff, TariffEvidence)
                 and isinstance(self.inventory, InventoryEvidence)
                 and self.research_policy.scope == self.tariff.scope == self.inventory.scope,
                 "one explicit shared research and billing scope required")
        _require(isinstance(self.deployment_receipt, ReviewedFile) and isinstance(self.adapter_file, ReviewedFile),
                 "hash-reviewed host deployment and adapter inputs required")
        for path in (self.state_root, self.broker_root):
            _plain(path, directory=True)
        _plain(self.artifact_root)
        roots = (self.artifact_root, self.state_root, self.broker_root)
        _require(not any(a == b or a in b.parents or b in a.parents for i, a in enumerate(roots) for b in roots[i+1:]),
                 "controller artifact/state and host ledger must be disjoint")
        self.spec()  # Validate the complete mount/configuration schema without launching.

    def spec(self):
        identity = ArtifactIdentity(self.research_policy.checkpoint, self.research_policy.gym_bundle,
                                    self.research_policy.execution)
        return SandboxSpec(self.research_policy.scope, self.artifact_root, self.artifact_files, self.state_root,
                           self.broker_root/self.socket_name, os.getuid(), self.research_policy.checkpoint,
                           self.research_policy.roots, self.config_relative, self.policy_relative, identity)


@dataclass(frozen=True)
class HostAdapters:
    provider: object
    driver_factory: Callable
    models: Mapping[str, ModelCapability]
    context: Callable[[str], HostContextEvidence]
    billing: Callable[[], tuple[TariffEvidence, InventoryEvidence]]

    def __post_init__(self):
        _require(callable(self.driver_factory) and callable(self.context) and callable(self.billing) and isinstance(self.models, Mapping),
                 "explicit reviewed provider/driver/model/context adapters required")


def deployment_window(now, *, calendar=None):
    """Fail closed on calendar errors; actual 90-minute lead and five-minute close pad."""
    now = _clock(now)
    if calendar is None:
        from ltcm.data import us_equity_session
        calendar = us_equity_session
    try:
        day = dt.datetime.fromtimestamp(now, dt.timezone.utc).date()
        session = calendar(day)
        if session is None:
            return None
        from ltcm.data import to_datetime
        opened, closed = to_datetime(session.open_at).timestamp(), to_datetime(session.close_at).timestamp()
        _require(_clock(opened) < _clock(closed), "invalid host session boundary")
        return {"starts": opened-90*60, "closes": closed+5*60} if opened-90*60 <= now < closed+5*60 else None
    except Exception as exc:
        raise ResearchHostError("host deployment calendar is unavailable") from exc


def deployment_preflight(config: HostConfig, now, *, calendar=None):
    """Read only: exact artifact, CI, rollback and runbook evidence; no account calls."""
    now = _clock(now)
    spec = config.spec()
    _require("league/CONTRACT.md" in dict(spec.artifact_files), "stock research contract must be in the reviewed artifact")
    artifact_sha = _verify_artifact(spec)
    _require(artifact_identity(spec.image, spec.artifact_root) == spec.expected_evaluator,
             "host artifact differs from its evaluator identity")
    value = _json(config.deployment_receipt.read())
    _require(isinstance(value, dict) and set(value) == {"schema", "head", "artifact_sha256", "observed_at", "valid_until",
                                                       "checks", "rollback", "runbook", "provenance"}
             and type(value["schema"]) is int and value["schema"] == 1,
             "complete deployment receipt required")
    _require(value["head"] == config.head and value["artifact_sha256"] == artifact_sha,
             "CI/rollback receipt is for another source head or artifact")
    _require(_clock(value["observed_at"]) <= now <= _clock(value["valid_until"]) <= value["observed_at"]+86400,
             "deployment evidence expired")
    checks = value["checks"]
    _require(isinstance(checks, dict) and set(checks) == _CHECKS and all(
        isinstance(check, dict) and set(check) == {"head", "conclusion", "receipt_sha256"}
        and check["head"] == config.head and check["conclusion"] == "success"
        and isinstance(check["receipt_sha256"], str) and _SHA.fullmatch(check["receipt_sha256"])
        for check in checks.values()), "exact-head gateway, both Python and content CI must pass")
    rollback = value["rollback"]
    _require(isinstance(rollback, dict) and set(rollback) == {"head", "artifact_sha256", "stopped_scoped_controller", "obligations_preserved", "receipt_sha256"}
             and rollback["head"] == config.head and rollback["artifact_sha256"] == artifact_sha
             and rollback["stopped_scoped_controller"] is True and rollback["obligations_preserved"] is True
             and isinstance(rollback["receipt_sha256"], str) and _SHA.fullmatch(rollback["receipt_sha256"]),
             "exact-artifact scoped rollback rehearsal required")
    runbook = value["runbook"]
    _require(isinstance(runbook, dict) and set(runbook) == {"path", "sha256", "checks_passed"} and runbook["checks_passed"] is True,
             "runbook checks must hold")
    ReviewedFile(Path(runbook["path"]), runbook["sha256"]).read()
    _require(isinstance(value["provenance"], str) and value["provenance"].strip(), "trusted deployment provenance required")
    _require(deployment_window(now, calendar=calendar) is None, "inside US session or its 90-minute deployment blackout")
    assert_isolated_state(spec.state_root, runtime_scope=spec.scope, expected_evaluator=spec.expected_evaluator,
                          artifact_root=spec.artifact_root)
    return {"head": config.head, "artifact_sha256": artifact_sha, "runbook_sha256": runbook["sha256"]}


def load_adapters(config):
    """Execute only explicitly hash-reviewed host bytes, outside the controller mount."""
    raw = config.adapter_file.read()
    path = config.adapter_file.path
    spec = config.spec()
    _require(not any(path == root or root in path.parents for root in (spec.artifact_root, spec.state_root)),
             "credential-bearing adapter cannot be controller mounted")
    module_name = "_ltcm_reviewed_host_"+hashlib.sha256(raw).hexdigest()
    module_spec = importlib.util.spec_from_loader(module_name, loader=None, origin=str(path))
    module = importlib.util.module_from_spec(module_spec)
    # Execute the verified bytes themselves: a path swap cannot substitute unreviewed code.
    exec(compile(raw, str(path), "exec"), module.__dict__)
    factory = getattr(module, config.adapter_factory, None)
    _require(callable(factory), "reviewed host adapter factory is unavailable")
    result = factory(config)
    _require(isinstance(result, HostAdapters), "factory must supply scoped host adapters")
    return result


class HostRuntime:
    """Own one captured controller and one socket; preserve all uncertain liabilities."""

    def __init__(self, config: HostConfig, adapters: HostAdapters, *, clock=time.time, calendar=None):
        _require(isinstance(config, HostConfig) and isinstance(adapters, HostAdapters), "explicit host configuration/adapters required")
        self.config, self.adapters, self.clock, self.calendar = config, adapters, clock, calendar
        self.store = self.budget = self.broker = self.listener = self.process = None
        self.stop = threading.Event()
        self._socket_identity = None
        self._server = None
        self._drainers = []
        self._output = {}
        self._peer_receipts = {}
        self._owner_fd = None
        self._reviewed_context = None

    def _claim_owner(self):
        path = self.config.broker_root/"research-host.lock"
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(descriptor)
            _require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o600,
                     "private host lifecycle lock required")
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            os.close(descriptor)
            raise
        self._owner_fd = descriptor

    @staticmethod
    def _birth(pid):
        _require(type(pid) is int and pid > 0, "invalid captured host PID")
        try:
            raw = (Path("/proc")/str(pid)/"stat").read_text()
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise ResearchHostError("captured host process evidence unavailable") from exc
        values = raw[raw.rfind(")")+2:].split()
        _require(len(values) >= 20, "captured host process receipt malformed")
        return int(values[19])

    def _recover_socket(self):
        """Recover only our dead host's exact refused socket, under the lifecycle lock."""
        path = self.config.spec().broker_socket
        if not path.exists() and not path.is_symlink():
            return
        info = path.lstat()
        receipt = self.store._one("SELECT payload FROM events WHERE kind='swarm.research_host' AND "
                                 "json_extract(payload,'$.action')='socket_bound' ORDER BY seq DESC LIMIT 1")
        _require(receipt is not None, "occupied socket has no immutable host owner receipt")
        value = _json(receipt["payload"])
        _require(set(value) == {"action", "pid", "birth", "dev", "ino", "ctime_ns", "scope", "at"}
                 and value["scope"] == self.config.research_policy.scope
                 and all(type(value[name]) is int and value[name] > 0 for name in ("pid", "birth", "dev", "ino", "ctime_ns"))
                 and stat.S_ISSOCK(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o600
                 and (info.st_dev, info.st_ino, info.st_ctime_ns) == (value["dev"], value["ino"], value["ctime_ns"]),
                 "occupied socket differs from captured owner")
        _require(self._birth(value["pid"]) != value["birth"], "captured host process is still alive")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.2)
            try:
                probe.connect(str(path))
            except OSError as exc:
                _require(exc.errno == errno.ECONNREFUSED, "occupied socket liveness is uncertain")
            else:
                raise ResearchHostError("occupied socket still has a listener")
        current = path.lstat()
        _require((current.st_dev, current.st_ino, current.st_ctime_ns) == (info.st_dev, info.st_ino, info.st_ctime_ns),
                 "occupied socket changed during recovery")
        path.unlink()
        self.store.event("swarm.research_host", None, {"action": "stale_socket_recovered", "scope": value["scope"]})

    def _drain(self):
        for name in ("stdout", "stderr"):
            pipe = getattr(self.process.process, name, None)
            if pipe is None:
                continue
            self._output[name] = bytearray()
            def read(pipe=pipe, name=name):
                try:
                    while True:
                        piece = pipe.read(4096)
                        if not piece:
                            break
                        self._output[name].extend(piece)
                        del self._output[name][:-65536]
                except (OSError, ValueError):
                    pass  # Shutdown closes captured pipes; output never crosses the socket.
            thread = threading.Thread(target=read, daemon=True, name="research-host-"+name)
            thread.start()
            self._drainers.append(thread)

    def _billing(self):
        observed = self.adapters.billing()
        _require(isinstance(observed, tuple) and len(observed) == 2 and isinstance(observed[0], TariffEvidence)
                 and isinstance(observed[1], InventoryEvidence)
                 and observed[0].scope == observed[1].scope == self.config.research_policy.scope,
                 "fresh authoritative shared billing scope required")
        with self.store.atomic():
            self.budget.tariff, self.budget.inventory = observed
            _require(self.budget.summary()["within_cap"], "fresh shared billing obligations exceed their ceiling")

    def _build_broker(self, *, admission=True):
        self.store = SwarmStore(self.config.broker_root, clock=self.clock)
        self.budget = DailyBudget(self.store, self.config.tariff, self.config.inventory)
        if admission:
            self._billing()  # Never initialize or replace a shared ledger implicitly.
        else:
            self.budget._load()  # Stale prices/breaches cannot prevent scoped cleanup.
        def verifier(peer, **facts):
            _require(self.process is not None, "captured live sandbox required")
            self._billing()
            proof = self.process.verify_peer(peer, self.adapters.context(self.broker.policy_digest))
            _require(proof.broker_root == str(self.config.broker_root) and proof.policy_digest == facts["policy_digest"],
                     "fresh host context differs from shared broker authority")
            _require(self._reviewed_context == (proof.runbook_sha256, proof.adapters_sha256),
                     "fresh host context differs from reviewed launch runbook or adapters")
            previous = self._peer_receipts.get(peer.pid)
            if previous is None or proof.observed_at-previous >= 5:
                self.store.event("swarm.research_host", None, {"action": "peer_verified", "pid": peer.pid,
                    "observed_at": proof.observed_at, "valid_until": proof.valid_until,
                    "mounts_sha256": proof.mounts_sha256, "network_sha256": proof.network_sha256,
                    "runbook_sha256": proof.runbook_sha256, "adapters_sha256": proof.adapters_sha256,
                    "policy_digest": proof.policy_digest})
                self._peer_receipts[peer.pid] = proof.observed_at
            return proof
        self.broker = ResearchBroker(self.store, self.budget, self.config.research_policy,
                                    artifact_root=self.config.artifact_root, provider=self.adapters.provider,
                                    driver_factory=self.adapters.driver_factory, model_adapters=self.adapters.models,
                                    verify_isolation=verifier)

    def start(self):
        _require(self.store is None and not self.stop.is_set(), "host runtime is already started or closed")
        deployment = deployment_preflight(self.config, self.clock(), calendar=self.calendar)
        try:
            self._claim_owner()
            self._build_broker()
            context = self.adapters.context(self.broker.policy_digest)
            value = _host_context(context, self.config.spec(), self.clock())
            _require(value["broker_root"] == str(self.config.broker_root)
                     and value["policy_digest"] == self.broker.policy_digest
                     and value["runbook"]["sha256"] == deployment["runbook_sha256"]
                     and {"path": str(self.config.adapter_file.path), "sha256": self.config.adapter_file.sha256} in value["adapters"],
                     "reviewed host context differs from launch evidence")
            self._reviewed_context = value["runbook"]["sha256"], value["adapters_sha256"]
            self._recover_socket()
            self.listener = create_listener(self.config.spec().broker_socket)
            info = self.config.spec().broker_socket.stat()
            self._socket_identity = (info.st_dev, info.st_ino, info.st_ctime_ns)
            self.store.event("swarm.research_host", None, {"action": "socket_bound", "pid": os.getpid(),
                "birth": self._birth(os.getpid()), "dev": info.st_dev, "ino": info.st_ino,
                "ctime_ns": info.st_ctime_ns, "scope": self.config.research_policy.scope, "at": self.clock()})
            self.listener.settimeout(0.2)
            self._server = BrokerServer(self.broker, controller_uid=os.getuid())
            deployment_preflight(self.config, self.clock(), calendar=self.calendar)  # Recheck immediately before launch.
            self.process = launch_sandbox(self.config.spec())
            self._drain()
            self.store.event("swarm.research_host", None, {"action": "launched", **deployment})
            return self
        except BaseException:
            self.shutdown()
            raise

    def serve(self, *, max_seconds=None):
        _require(self.listener is not None and self.process is not None, "host runtime has not launched")
        _require(max_seconds is None or type(max_seconds) in (int, float) and math.isfinite(max_seconds) and max_seconds > 0,
                 "invalid host service duration")
        deadline = None if max_seconds is None else time.monotonic()+max_seconds
        while not self.stop.is_set() and self.process.process.poll() is None:
            if deadline is not None and time.monotonic() >= deadline:
                break
            try:
                self._server.serve_once(self.listener, timeout=30)
            except socket.timeout:
                continue
            except Exception as exc:
                # Malformed or unrelated peers never reach paid admission; keep details private.
                self.store.event("swarm.research_host", None, {"action": "connection_refused", "reason": type(exc).__name__})
        return self.process.process.poll()

    def shutdown(self):
        self.stop.set()
        if self.process is not None:
            self.process.close()
            self.process = None
        for thread in self._drainers:
            thread.join(1)
        self._drainers.clear()
        if self.listener is not None:
            self.listener.close()
            self.listener = None
        path = self.config.spec().broker_socket
        if self._socket_identity is not None:
            try:
                info = path.lstat()
                if stat.S_ISSOCK(info.st_mode) and (info.st_dev, info.st_ino, info.st_ctime_ns) == self._socket_identity:
                    path.unlink()
            except FileNotFoundError:
                pass
            self._socket_identity = None
        if self.store is not None:
            self.store.close()
            self.store = None
        if self._owner_fd is not None:
            os.close(self._owner_fd)
            self._owner_fd = None

    def cleanup_owned(self):
        """Explicit host-only stop: journal scope, no fabricated controller proof or IDs."""
        _require(self.store is None and not self.stop.is_set(), "cleanup requires a separate host lifecycle")
        try:
            self._claim_owner()
            self._build_broker(admission=False)
            resource = self.broker._resource()
            if resource is None:
                return {"status": "absent", "vendor_actual": False}
            key, row = resource
            if row["observation"] is None:
                return {"status": "unresolved_creation", "runtime_stopped": False, "vendor_actual": False}
            if row["status"] == "terminated":
                return {"status": "terminated", "runtime_stopped": True, "vendor_actual": False}
            resource_id = row["observation"]["resource_id"]
            self.broker._validate_observation(self.adapters.provider.observe(resource_id), row, stopping=True)
            with self.store.atomic():
                self.broker._record("resource_state", key=key, status="stop_requested")
            response = self.adapters.provider.terminate(resource_id)
            matching = isinstance(response, Mapping) and response.get("sailbox_id") == resource_id
            status = response.get("status") if matching else "unknown"
            if status == "terminated":
                with self.store.atomic():
                    self.budget.terminal_observed(key, resource_id, observed_at=self.clock(), status="terminated",
                                                 provenance="matching reviewed host-only scoped cleanup response")
                    self.broker._record("resource_state", key=key, status="terminated")
            return {"status": status, "runtime_stopped": status == "terminated", "vendor_actual": False}
        finally:
            self.shutdown()


def load_config(reviewed: ReviewedFile):
    document = _json(reviewed.read())
    names = {field.name for field in fields(HostConfig)}
    _require(isinstance(document, dict) and set(document) == names, "exact host configuration schema required")
    for name in ("artifact_root", "state_root", "broker_root"):
        document[name] = Path(document[name])
    document["artifact_files"] = tuple(tuple(item) for item in document["artifact_files"])
    for name in ("deployment_receipt", "adapter_file"):
        row = document[name]
        _require(isinstance(row, dict) and set(row) == {"path", "sha256"}, "exact reviewed host file reference required")
        document[name] = ReviewedFile(Path(row["path"]), row["sha256"])
    policy = dict(document["research_policy"])
    policy["resource_bound"] = ResourceBound(**policy["resource_bound"])
    for name in ("roots", "forbidden_resource_ids"):
        if name in policy:
            policy[name] = tuple(policy[name])
    document["research_policy"] = ResearchPolicy(**policy)
    document["tariff"] = TariffEvidence(**document["tariff"])
    inventory = dict(document["inventory"])
    for name in ("resource_ids", "model_keys"):
        inventory[name] = tuple(inventory[name])
    document["inventory"] = InventoryEvidence(**inventory)
    return HostConfig(**document)


def host_status(config: HostConfig, *, clock=time.time):
    """Coherent read-only ledger/reply audit; never imports credential adapters."""
    store = SwarmStore(config.broker_root, clock=clock, readonly=True)
    try:
        with store._lock:
            store._db.execute("BEGIN")
            budget = DailyBudget(store, config.tariff, config.inventory)
            state = budget._load()
            result = {"scope": config.research_policy.scope, "vendor_actual": False,
                      "resource_obligations": len(state["resources"]), "model_obligations": len(state["inference"]),
                      "physical_peer_verified": False, "adapters_loaded": False}
            observed = store._one("SELECT payload FROM events WHERE kind='swarm.research_host' AND "
                                 "json_extract(payload,'$.action')='peer_verified' ORDER BY seq DESC LIMIT 1")
            if observed is not None:
                result["last_peer_receipt"] = {**_json(observed["payload"]), "historical_only": True}
            broker_state = None
            for row in store._all("SELECT payload FROM events WHERE kind=? ORDER BY seq", (BROKER_EVENT,)):
                broker_state = ResearchBroker._apply(broker_state, _json(row["payload"]))
            cached = store._one("SELECT value FROM kv WHERE key=?", (BROKER_STATE,))
            _require((broker_state is None and cached is None) or (broker_state is not None and cached is not None
                     and broker_state == _json(cached["value"])), "broker journal differs from immutable history")
            if broker_state is not None:
                _require(broker_state["scope"] == config.research_policy.scope, "broker journal scope differs")
                reader = ResearchBroker.__new__(ResearchBroker)
                reader.store, reader._verified_blobs = store, {}
                for request in broker_state["requests"].values():
                    if request["result"] is not None:
                        reader._read_reply(request["result"], decode=False)
                result.update(broker_closed=broker_state["closed"], unresolved_requests=sum(
                    request["result"] is None for request in broker_state["requests"].values()))
            try:
                result["daily_budget"] = budget.summary()
                result["billing_admission"] = result["daily_budget"]["within_cap"]
            except Exception as exc:
                result.update(billing_admission=False, reason=type(exc).__name__)
            return result
    finally:
        store.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("check", "status", "serve", "cleanup"))
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--config-sha256", required=True)
    args = parser.parse_args(argv)
    runtime = None
    try:
        config = load_config(ReviewedFile(args.config, args.config_sha256))
        if args.operation == "status":
            print(json.dumps(host_status(config), sort_keys=True))
            return 0
        if args.operation == "check":
            config.adapter_file.read()  # Verify reviewed bytes without executing credentials/factory code.
            report = {"deployment": deployment_preflight(config, time.time()), "ledger": host_status(config)}
            print(json.dumps(report, sort_keys=True))
            return 0 if report["ledger"]["billing_admission"] else 2
        if args.operation == "serve":
            deployment_preflight(config, time.time())  # Even credential factory execution waits for launch gates.
        adapters = load_adapters(config)
        runtime = HostRuntime(config, adapters)
        if args.operation == "cleanup":
            report = runtime.cleanup_owned()
            print(json.dumps(report, sort_keys=True))
            return 0 if report["status"] in ("absent", "terminated") else 2
        for signum in (signal.SIGINT, signal.SIGTERM):
            signal.signal(signum, lambda *_: runtime.stop.set())
        runtime.start()
        return runtime.serve() or 0
    except Exception as exc:
        print(json.dumps({"status": "refused_or_uncertain", "reason": type(exc).__name__}))
        return 2
    finally:
        if runtime is not None:
            runtime.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["HostConfig", "HostAdapters", "HostRuntime", "ReviewedFile", "ResearchHostError",
           "deployment_preflight", "deployment_window", "load_config", "load_adapters", "host_status", "main"]
