"""Host-side capabilities for isolated Train/Validation research, with no credential factory.

Only the authenticated Unix server may expose ``handle`` to a controller. Provider,
GymDriver, tokenizer, price evidence and isolation verification are explicitly
injected trusted host adapters. This module never loads an environment, constructs
an account client, accepts a URL/command/resource ID from a controller or selects
a live, Gate or forward route. A synthetic verifier is not physical isolation proof.

The host-private journal and the single DailyBudget share one store. Paid intents
commit before dispatch; uncertain outcomes keep their slot and liability through
restart. Cached terminal replies are readable without redispatch. Runtime stops
never release current-day or unpriced vendor costs.
"""

from __future__ import annotations

import datetime as dt
import copy
import hashlib
import json
import math
import os
import re
import stat
import threading
import uuid
from dataclasses import asdict, dataclass, fields
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .daily_compute import DailyBudget, ResourceBound, NANOS

EVENT_KIND = "swarm.research_broker"
STATE_KEY = "research_broker_v1"
REQUEST_LIMIT = 4 * 1024 * 1024
RESULT_LIMIT = 24 * 1024 * 1024
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$")
_BOX = re.compile(r"^sb_[0-9a-fA-F-]{8,64}$")
_CHECKPOINT = re.compile(r"^sbcp_[0-9a-fA-F-]{8,64}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_MODEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}(?:/[A-Za-z0-9][A-Za-z0-9_.-]{0,119})?\Z")
_ROOT = re.compile(r"^[A-Z][A-Z0-9.]{0,9}$")
ISOLATION_FACTS = frozenset((
    "broker_private_ledger", "controller_credentials_absent", "production_mounts_absent",
    "controller_network_only_broker", "kernel_peer_authenticated", "train_validation_data_only",
    "gym_credentials_absent", "single_daily_authority", "reviewed_runbook", "reviewed_host_adapters",
))
NAMESPACE_FACTS = frozenset(("user_namespace", "pid_namespace", "mount_namespace", "network_namespace", "host_proc_absent"))


class ResearchCapabilityError(RuntimeError):
    """Refused or uncertain work; this exception never authorizes redispatch."""


class _ReplyIntegrityError(ResearchCapabilityError):
    """The IPC boundary must commit a closed capability after transaction unwind."""


def _require(ok: bool, reason: str):
    if not ok:
        raise ResearchCapabilityError(reason)


def _json(value: Any, limit=REQUEST_LIMIT) -> str:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        raise ResearchCapabilityError("finite JSON is required") from exc
    _require(len(encoded) <= limit, "capability payload exceeds its bound")
    return encoded


def _pairs(items):
    out = {}
    for key, value in items:
        _require(key not in out, "duplicate durable broker field")
        out[key] = value
    return out


def _decode(raw):
    try:
        return json.loads(raw, object_pairs_hook=_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ResearchCapabilityError("nonfinite broker state")))
    except (ValueError, TypeError, RecursionError) as exc:
        raise ResearchCapabilityError("unreadable broker journal") from exc


def _digest(value):
    return hashlib.sha256(_json(value).encode("ascii")).hexdigest()


def _identity(value):
    return isinstance(value, str) and bool(_ID.fullmatch(value))


def _time(value):
    _require(isinstance(value, (int, float)) and not isinstance(value, bool), "invalid capability clock")
    _require(math.isfinite(value) and value >= 0, "invalid capability clock")
    return float(value)


def _date(value):
    try:
        parsed = dt.date.fromisoformat(value)
        _require(parsed.isoformat() == value, "an exact ISO date is required")
        return parsed
    except (ValueError, TypeError) as exc:
        raise ResearchCapabilityError("an exact ISO date is required") from exc


def _money(value):
    _require(isinstance(value, (str, int, Decimal)) and not isinstance(value, bool), "exact host price evidence is required")
    try:
        number = Decimal(value)
        _require(number.is_finite() and number >= 0 and number <= Decimal("1000000"), "invalid host price evidence")
        _require(len(number.as_tuple().digits) <= 20 and number.as_tuple().exponent >= -12, "overprecise host price evidence")
        return number
    except (InvalidOperation, ValueError) as exc:
        raise ResearchCapabilityError("invalid host price evidence") from exc


@dataclass(frozen=True)
class PeerIdentity:
    pid: int
    uid: int
    gid: int

    def __post_init__(self):
        _require(all(type(v) is int and v >= 0 for v in (self.pid, self.uid, self.gid)) and self.pid > 0,
                 "kernel peer identity is required")


@dataclass(frozen=True)
class IsolationProof:
    """Fresh host-verifier observation of the real peer; never accepted over IPC."""

    scope: str
    peer: PeerIdentity
    broker_uid: int
    broker_root: str
    policy_digest: str
    mode: str
    observed_at: float
    valid_until: float
    runbook_sha256: str
    mounts_sha256: str
    network_sha256: str
    adapters_sha256: str
    facts: tuple[str, ...]
    provenance: str


@dataclass(frozen=True)
class ResearchPolicy:
    scope: str
    checkpoint: str
    gym_bundle: str
    resource_bound: ResourceBound
    roots: tuple[str, ...]
    execution: str
    train_first: str = "2020-01-02"
    train_last: str = "2024-12-31"
    validation_first: str = "2025-01-02"
    validation_last: str = "2025-12-31"
    workers: int = 1
    timeout_seconds: int = 900
    capital: str = "10000"
    max_split: int = 16
    forbidden_resource_ids: tuple[str, ...] = ()

    def __post_init__(self):
        _require(_identity(self.scope) and isinstance(self.checkpoint, str) and bool(_CHECKPOINT.fullmatch(self.checkpoint)), "invalid research scope/checkpoint")
        _require(_identity(self.gym_bundle) and isinstance(self.resource_bound, ResourceBound) and self.resource_bound.kind == "gym",
                 "reviewed Gym bundle and hard Gym resource ceilings are required")
        _require(isinstance(self.execution, str) and bool(_SHA.fullmatch(self.execution)), "reviewed execution SHA256 is required")
        _require(isinstance(self.roots, tuple) and bool(self.roots) and len(set(self.roots)) == len(self.roots)
                 and all(isinstance(r, str) and _ROOT.fullmatch(r) for r in self.roots), "invalid approved roots")
        _require(_date("2017-01-03") <= _date(self.train_first) <= _date(self.train_last) <= _date("2024-12-31"), "Train range escaped development data")
        _require((self.validation_first, self.validation_last) == ("2025-01-02", "2025-12-31"), "Validation must be the reviewed whole window")
        _require(type(self.workers) is int and 1 <= self.workers <= self.resource_bound.vcpu, "workers exceed admitted CPU ceiling")
        _require(type(self.timeout_seconds) is int and 1 <= self.timeout_seconds <= 86400 and type(self.max_split) is int and 1 <= self.max_split <= 128,
                 "invalid host execution limits")
        _require(_money(self.capital) > 0, "invalid simulated capital")
        _require(_money(str(float(self.capital))) == _money(self.capital), "simulated capital changes at the driver's numeric boundary")
        _require(isinstance(self.forbidden_resource_ids, tuple) and all(isinstance(v, str) and _BOX.fullmatch(v) for v in self.forbidden_resource_ids),
                 "invalid production resource exclusion")


@dataclass(frozen=True)
class ResearchJob:
    family: str
    version: int | None
    code: str
    params: dict[str, Any]
    window: str
    roots: tuple[str, ...]
    stress: float = 1.0
    purpose: str = "train"
    detail: str = "full"
    split: int = 1
    start: str | None = None
    end: str | None = None


@dataclass(frozen=True)
class ResourceObservation:
    """Authoritative host adapter readback, not controller supplied metadata."""

    resource_id: str
    name: str
    checkpoint: str
    created_at: float
    bound: ResourceBound
    status: str
    provenance: str


@dataclass(frozen=True)
class ModelPolicy:
    model: str
    input_usd_million: str
    output_usd_million: str
    fixed_usd: str
    max_input_tokens: int
    max_output_tokens: int
    valid_from: float
    valid_until: float
    provenance: str
    allowed_efforts: tuple[str, ...] = ("low",)
    allowed_tools: tuple[dict[str, Any], ...] = ()
    timeout_seconds: int = 300

    def __post_init__(self):
        _require(isinstance(self.model, str) and bool(_MODEL.fullmatch(self.model))
                 and isinstance(self.provenance, str) and bool(self.provenance.strip()), "documented host model policy is required")
        for value in (self.input_usd_million, self.output_usd_million, self.fixed_usd):
            _money(value)
        _require(all(type(v) is int and 0 < v <= 1000000 for v in (self.max_input_tokens, self.max_output_tokens)), "invalid host token ceilings")
        _require(_time(self.valid_from) < _time(self.valid_until), "invalid host price interval")
        _require(isinstance(self.allowed_efforts, tuple) and bool(self.allowed_efforts)
                 and all(v in ("none", "minimal", "low", "medium", "high") for v in self.allowed_efforts), "invalid reviewed model efforts")
        _require(isinstance(self.allowed_tools, tuple) and all(isinstance(t, dict) and t.get("type") == "function"
                 for t in self.allowed_tools), "reviewed local function tools are required")
        _json(self.allowed_tools)
        _require(type(self.timeout_seconds) is int and 1 <= self.timeout_seconds <= 3600, "invalid model timeout")


@dataclass(frozen=True)
class ModelReply:
    result: dict[str, Any]
    actual_usd: str | None = None
    accrued_day: str | None = None
    provenance: str | None = None


@dataclass(frozen=True)
class ModelCapability:
    policy: ModelPolicy
    count_tokens: Callable[[Mapping[str, Any]], int]
    send: Callable[[Mapping[str, Any]], ModelReply]


class ResearchBroker:
    """Credential-holding host object; the controller must only receive an IPC client."""

    def __init__(self, store, budget: DailyBudget, policy: ResearchPolicy, *, provider,
                 artifact_root: Path | str, driver_factory: Callable, model_adapters: Mapping[str, ModelCapability], verify_isolation: Callable):
        _require(isinstance(budget, DailyBudget) and budget.store is store and isinstance(policy, ResearchPolicy)
                 and budget.tariff.scope == policy.scope, "one host-private store and shared dollar authority are required")
        _require(callable(driver_factory) and callable(verify_isolation) and isinstance(model_adapters, Mapping), "explicit reviewed host adapters are required")
        _require(all(_identity(k) and isinstance(v, ModelCapability) and callable(v.count_tokens) and callable(v.send)
                     and isinstance(v.policy, ModelPolicy) for k, v in model_adapters.items()), "invalid host model capabilities")
        self.store, self.budget, self.policy = store, budget, copy.deepcopy(policy)
        self._provider, self._driver_factory = provider, driver_factory
        self._models = {k: ModelCapability(copy.deepcopy(v.policy), v.count_tokens, v.send) for k, v in model_adapters.items()}
        self._verify = verify_isolation
        self._peer = threading.local()
        self._lock = threading.RLock()
        self._driver = None
        self._verified_blobs = {}
        self._artifact_root = Path(artifact_root).resolve()
        self._artifact_bundle = self._artifact()
        self.policy_digest = _digest({"research": asdict(policy), "models": {k: asdict(v.policy) for k, v in sorted(self._models.items())}})

    def _artifact(self):
        """Read actual reviewed bytes without evaluator's process-global fingerprint cache."""
        from ..gym.driver import LEAGUE_FILES, build_bundle
        try:
            bundle, version = build_bundle(self._artifact_root)
            files = {self._artifact_root / name for name in LEAGUE_FILES}
            for name in ("gym", "live"):
                files.update((self._artifact_root / "league" / name).rglob("*.py"))
            digest = hashlib.sha256()
            for path in sorted(files):
                digest.update(path.relative_to(self._artifact_root).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
        except (OSError, ValueError) as exc:
            raise ResearchCapabilityError("reviewed host artifact is unreadable") from exc
        _require(version == self.policy.gym_bundle and digest.hexdigest() == self.policy.execution,
                 "actual host artifact differs from reviewed evaluator identity")
        return bundle

    def _evaluation(self):
        return {"image": self.policy.checkpoint, "bundle": self.policy.gym_bundle, "execution": self.policy.execution,
                "roots": list(self.policy.roots), "train_first": self.policy.train_first, "train_last": self.policy.train_last,
                "validation_first": self.policy.validation_first, "validation_last": self.policy.validation_last,
                "capital": format(_money(self.policy.capital).normalize(), "f"), "workers": self.policy.workers,
                "max_split": self.policy.max_split}

    def _reply_directory(self, *, create=False):
        path = self.store.root / "research-broker-results"
        try:
            if create:
                path.mkdir(mode=0o700, exist_ok=True)
            info = path.lstat()
            _require(stat.S_ISDIR(info.st_mode) and not path.is_symlink() and info.st_uid == os.geteuid()
                     and stat.S_IMODE(info.st_mode) == 0o700, "host-private reply directory is required")
        except OSError as exc:
            raise ResearchCapabilityError("host-private reply directory is unavailable") from exc
        return path

    @staticmethod
    def _reply_reference(reference):
        _require(isinstance(reference, dict) and set(reference) == {"sha256", "bytes"}
                 and isinstance(reference["sha256"], str) and _SHA.fullmatch(reference["sha256"])
                 and type(reference["bytes"]) is int and 0 < reference["bytes"] <= RESULT_LIMIT,
                 "invalid immutable terminal reply reference")
        return reference

    @staticmethod
    def _stamp(info):
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_uid, info.st_mode)

    def _read_reply(self, reference, *, decode=True):
        reference = self._reply_reference(reference)
        path = self._reply_directory() / (reference["sha256"] + ".json")
        try:
            info = path.lstat()
            _require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid() and stat.S_IMODE(info.st_mode) == 0o600
                     and info.st_size == reference["bytes"], "terminal reply file type, owner, permissions or size differs")
            stamp = self._stamp(info)
            # Private, immutable files are rehashed after any kernel metadata change,
            # and once per process after restart. Cache lookups always read the hash.
            if not decode and self._verified_blobs.get(reference["sha256"]) == stamp:
                return None
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(descriptor, "rb") as handle:
                before = os.fstat(handle.fileno())
                _require(self._stamp(before) == stamp, "terminal reply changed while opening")
                raw = handle.read(RESULT_LIMIT+1)
                _require(self._stamp(os.fstat(handle.fileno())) == stamp, "terminal reply changed while reading")
            _require(len(raw) == reference["bytes"] and hashlib.sha256(raw).hexdigest() == reference["sha256"],
                     "terminal reply bytes do not match their immutable receipt")
            result = _decode(raw)
            _require(isinstance(result, dict), "terminal reply is not a result object")
            self._verified_blobs[reference["sha256"]] = stamp
            return result if decode else None
        except (OSError, UnicodeError) as exc:
            raise ResearchCapabilityError("terminal reply is missing or unreadable") from exc

    def _write_reply(self, result):
        raw = _json(result, RESULT_LIMIT).encode("ascii")
        reference = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
        directory = self._reply_directory(create=True)
        destination = directory / (reference["sha256"] + ".json")
        temporary = directory / (".reply-"+uuid.uuid4().hex)
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, destination, follow_symlinks=False)
            except FileExistsError:
                pass  # The existing content must still prove the exact immutable receipt.
            temporary.unlink()
            descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            self._read_reply(reference, decode=False)
        except (OSError, ResearchCapabilityError) as exc:
            raise _ReplyIntegrityError("terminal reply could not be made durable") from exc
        finally:
            temporary.unlink(missing_ok=True)
        return reference

    def _closed_reply(self, reason):
        # Only capability work closes; all DailyBudget commitments remain intact.
        with self.store.atomic():
            state = self._load()
            if state is not None and not state["closed"]:
                self._record("closed", reason=reason)

    def _result(self, reference):
        try:
            return self._read_reply(reference)
        except ResearchCapabilityError as exc:
            raise _ReplyIntegrityError("immutable terminal reply is missing or changed") from exc

    def authorize_peer(self, pid: int, uid: int, gid: int):
        self._peer.identity = PeerIdentity(pid, uid, gid)

    def _scope(self):
        peer = getattr(self._peer, "identity", None)
        _require(isinstance(peer, PeerIdentity), "authenticated kernel peer is required")
        started_at = _time(self.store.clock())
        proof = self._verify(peer, scope=self.policy.scope, broker_root=str(self.store.root.resolve()), policy_digest=self.policy_digest)
        now = _time(self.store.clock())
        _require(now >= started_at, "capability clock rolled back during host verification")
        _require(isinstance(proof, IsolationProof) and proof.peer == peer and proof.scope == self.policy.scope
                 and proof.broker_uid == os.geteuid() and proof.broker_root == str(self.store.root.resolve())
                 and proof.policy_digest == self.policy_digest, "host isolation observation differs from this runtime")
        _require(_time(proof.observed_at) <= now <= _time(proof.valid_until) <= proof.observed_at + 300,
                 "host isolation observation is stale")
        _require(proof.mode in ("distinct_uid", "namespaces") and isinstance(proof.facts, tuple)
                 and ISOLATION_FACTS <= set(proof.facts), "host isolation observations are incomplete")
        _require((proof.mode == "distinct_uid" and peer.uid != proof.broker_uid)
                 or (proof.mode == "namespaces" and NAMESPACE_FACTS <= set(proof.facts)), "peer lacks verified UID or namespace confinement")
        _require(all(isinstance(v, str) and _SHA.fullmatch(v) for v in
                     (proof.runbook_sha256, proof.mounts_sha256, proof.network_sha256, proof.adapters_sha256))
                 and isinstance(proof.provenance, str) and bool(proof.provenance.strip()), "host isolation receipts are required")
        return proof

    @staticmethod
    def _apply(state, receipt):
        _require(isinstance(receipt, dict), "invalid broker receipt")
        action, now = receipt.get("action"), _time(receipt.get("at"))
        if state is None:
            _require(set(receipt) == {"action", "at", "scope", "policy_digest"} and action == "opened", "broker has no original scope")
            return {"scope": receipt["scope"], "policy_digest": receipt["policy_digest"], "last_at": now,
                    "resources": {}, "requests": {}, "closed": False}
        _require(now >= state["last_at"], "broker journal clock rolled back")
        if action == "resource_started":
            _require(set(receipt) == {"action", "at", "key", "name"} and _identity(receipt["key"])
                     and receipt["key"] not in state["resources"], "duplicate resource dispatch intent")
            state["resources"][receipt["key"]] = {"name": receipt["name"], "at": now, "observation": None, "status": "creating"}
        elif action == "resource_attached":
            _require(set(receipt) == {"action", "at", "key", "observation"} and receipt["key"] in state["resources"], "resource attachment lacks intent")
            row = state["resources"][receipt["key"]]
            _require(row["observation"] is None, "resource was already bound")
            row.update(observation=receipt["observation"], status=receipt["observation"]["status"])
        elif action == "resource_state":
            _require(set(receipt) == {"action", "at", "key", "status"} and receipt["key"] in state["resources"], "resource state lacks intent")
            state["resources"][receipt["key"]]["status"] = receipt["status"]
        elif action == "request_started":
            _require(set(receipt) == {"action", "at", "key", "kind", "fingerprint"} and _identity(receipt["key"])
                     and receipt["kind"] in ("gym", "model") and receipt["key"] not in state["requests"], "duplicate paid request intent")
            state["requests"][receipt["key"]] = {"kind": receipt["kind"], "fingerprint": receipt["fingerprint"], "result": None}
        elif action == "request_finished":
            _require(set(receipt) == {"action", "at", "key", "result"} and receipt["key"] in state["requests"], "terminal result lacks intent")
            row = state["requests"][receipt["key"]]
            _require(row["result"] is None, "result was already terminal")
            row["result"] = ResearchBroker._reply_reference(receipt["result"])
        elif action == "closed":
            _require(set(receipt) == {"action", "at", "reason"}, "invalid closed-scope receipt")
            state["closed"] = True
        else:
            raise ResearchCapabilityError("unknown broker receipt")
        state["last_at"] = now
        return state

    def _load(self):
        state = None
        for row in self.store._all("SELECT payload FROM events WHERE kind=? ORDER BY seq", (EVENT_KIND,)):
            state = self._apply(state, _decode(row["payload"]))
        cache = self.store._one("SELECT value FROM kv WHERE key=?", (STATE_KEY,))
        _require((state is None and cache is None) or (state is not None and cache is not None
                 and _json(state, RESULT_LIMIT) == _json(_decode(cache["value"]), RESULT_LIMIT)), "broker commitments were lost or changed")
        if state is not None:
            _require(state["scope"] == self.policy.scope and state["policy_digest"] == self.policy_digest, "broker scope or reviewed policy changed")
        return state

    def _record(self, action, **details):
        state = self._load()
        receipt = {"action": action, "at": _time(self.store.clock()), **details}
        state = self._apply(state, receipt)
        self.store.event(EVENT_KIND, None, receipt)
        self.store.put(STATE_KEY, state)
        return state

    def open_runtime(self):
        proof = self._scope()
        _require(self._artifact() == self._artifact_bundle, "reviewed host bundle changed")
        bad_reply = None
        with self.store.atomic():
            summary = self.budget.summary()
            _require(summary["within_cap"], "current daily obligations exceed their ceiling")
            state = self._load()
            if state is None:
                state = self._record("opened", scope=self.policy.scope, policy_digest=self.policy_digest)
            _require(not state["closed"], "broker scope has unresolved safety evidence")
            try:
                for request in state["requests"].values():
                    if request["result"] is not None:
                        self._read_reply(request["result"], decode=False)
            except ResearchCapabilityError as exc:
                self._record("closed", reason="immutable terminal reply is missing or changed")
                bad_reply = exc
        if bad_reply is not None:
            raise _ReplyIntegrityError("immutable terminal reply is missing or changed") from bad_reply
        return {"scope": self.policy.scope, "policy_digest": self.policy_digest, "daily_budget": summary,
                "evaluation": self._evaluation(),
                "isolation_receipt": {"mode": proof.mode, "observed_at": proof.observed_at, "valid_until": proof.valid_until,
                                      "runbook_sha256": proof.runbook_sha256, "mounts_sha256": proof.mounts_sha256,
                                      "network_sha256": proof.network_sha256, "adapters_sha256": proof.adapters_sha256}}

    def summary(self):
        return self.open_runtime()

    def cached_result(self, key: str, *, kind: str = "model"):
        _require(_identity(key) and kind in ("model", "gym"), "invalid cached research result identity")
        with self.store.atomic():
            state = self._load()
            row = state["requests"].get(key) if state else None
            _require(row is None or row["kind"] == kind, "cached request kind differs")
            if not row or row["result"] is None:
                return None
            result = self._result(row["result"])
            return self._model_cost_view(key, result) if kind == "model" else result

    def _model_cost_view(self, key, result):
        """Expose the original reservation, including for older immutable replies.

        Cache recovery does not reprice, settle, admit or rewrite the original reply.
        A later invoice belongs to the budget ledger; it does not change what was
        known when this terminal response was captured.
        """
        daily_key = "model-" + hashlib.sha256((self.policy.scope + ":" + key).encode()).hexdigest()
        state = self.budget._load()
        hold = state["inference"].get(daily_key) if state else None
        _require(hold is not None and hold["dispatch_at"] is not None and not hold["canceled"],
                 "cached model response has no original dispatched reservation")
        upper = Decimal(hold["max_nanos"]) / NANOS
        if "cost_upper_usd" in result:
            _require(_money(result["cost_upper_usd"]) == upper, "model response changed its original reservation")
        status = "unknown" if result.get("cost_usd") is None else "vendor_actual"
        _require(result.get("cost_status", status) == status, "model response changed its cost evidence status")
        return {**result, "cost_upper_usd": result.get("cost_upper_usd", format(upper, "f")), "cost_status": status}

    def _prior_request(self, key, kind, fingerprint):
        _require(_identity(key), "invalid research request identity")
        with self.store.atomic():
            state = self._load()
            row = state["requests"].get(key) if state else None
            if row:
                _require(row["kind"] == kind and row["fingerprint"] == fingerprint, "request key was reused for different work")
                _require(row["result"] is not None, "previous request outcome is unresolved; no redispatch")
                result = self._result(row["result"])
                return self._model_cost_view(key, result) if kind == "model" else result
        return None

    def _resource(self):
        with self.store.atomic():
            state = self._load()
            rows = list(state["resources"].items()) if state else []
            _require(len(rows) <= 1, "single-resource capability history differs")
            return rows[0] if rows else None

    def _close_scope(self, key, reason):
        with self.store.atomic():
            if self._load()["closed"]:
                return
            self.budget._transition({"action": "scope_breached", "key": key, "reason": reason,
                                     "provenance": "trusted broker readback contradicts its reviewed capability"})
            self._record("closed", reason=reason)

    def _validate_observation(self, observation, row, *, stopping=False):
        _require(isinstance(observation, ResourceObservation) and isinstance(observation.resource_id, str)
                 and _BOX.fullmatch(observation.resource_id) and observation.resource_id not in self.policy.forbidden_resource_ids,
                 "resource identity is malformed or production-owned")
        _require(observation.name == row["name"] and observation.checkpoint == self.policy.checkpoint
                 and row["at"] <= _time(observation.created_at) <= _time(self.store.clock())
                 and isinstance(observation.bound, ResourceBound) and observation.bound.spec_id == self.policy.resource_bound.spec_id
                 and observation.bound.kind == "gym" and isinstance(observation.provenance, str) and bool(observation.provenance.strip()),
                 "resource readback does not prove the approved creation")
        if row["observation"]:
            _require(observation.resource_id == row["observation"]["resource_id"], "owned resource identity changed")
        _require(observation.status in ("running", "sleeping", "paused", "starting", "terminating", "terminated", "failed", "create_failed"),
                 "unknown resource runtime state")
        if any(_money(getattr(observation.bound, field)) > _money(getattr(self.policy.resource_bound, field))
               for field in ("vcpu", "memory_gib", "disk_gib", "volume_gib", "creation_fee_usd")):
            self._close_scope(self._resource()[0], "resource readback exceeds the admitted hard ceilings")
            if not stopping:
                raise ResearchCapabilityError("resource exceeded its admitted hard ceilings")
        return observation

    def _sealed(self, resource_id):
        document = self._provider.egress(resource_id)
        if isinstance(document, Mapping) and isinstance(document.get("document"), Mapping):
            document = document["document"]
        if not (isinstance(document, Mapping) and document.get("no_network") is True
                and not document.get("allowlist") and not document.get("allowed_hosts")):
            self._close_scope(self._resource()[0], "Gym guest is not proven no_network")
            raise ResearchCapabilityError("Gym guest is not proven no_network")

    def _attach(self, key, row, observation):
        observation = self._validate_observation(observation, row)
        self._sealed(observation.resource_id)
        with self.store.atomic():
            self.budget.attach(key, observation.resource_id, created_at=observation.created_at,
                               observed_bound=observation.bound, provenance=observation.provenance)
            self._record("resource_attached", key=key, observation=asdict(observation))
        return observation

    def recover_gym(self):
        self._scope()
        with self._lock:
            resource = self._resource()
            if resource is None:
                return {"status": "absent"}
            key, row = resource
            if row["observation"] is None:
                lookup = getattr(self._provider, "find_created", None)
                _require(callable(lookup), "pending creation needs an exact-name host observer")
                observation = lookup(row["name"], checkpoint=self.policy.checkpoint)
                if observation is None:
                    return {"status": "creating", "outcome_known": False}
                observation = self._attach(key, row, observation)
            else:
                observation = self._validate_observation(self._provider.observe(row["observation"]["resource_id"]), row)
                self._sealed(observation.resource_id)
            if observation.status == "terminated" and row["status"] != "terminated":
                with self.store.atomic():
                    self.budget.terminal_observed(key, observation.resource_id, observed_at=self.store.clock(), status="terminated", provenance=observation.provenance)
                    self._record("resource_state", key=key, status="terminated")
            elif observation.status in ("running", "sleeping") and row["status"] not in ("stop_requested", "terminated"):
                with self.store.atomic():
                    self._record("resource_state", key=key, status=observation.status)
            return {"status": observation.status, "outcome_known": True, "gym_image": self.policy.checkpoint, "gym_bundle": self.policy.gym_bundle}

    def _ensure_gym(self):
        self.open_runtime()
        resource = self._resource()
        if resource is None:
            key = "resource-" + uuid.uuid4().hex
            name = "ltcm-research-" + hashlib.sha256(self.policy.scope.encode()).hexdigest()[:12] + "-" + uuid.uuid4().hex
            with self.store.atomic():
                self.open_runtime()
                _require(self._resource() is None, "another broker already admitted the single resource; recover its intent")
                self.budget.reserve_resource(key, self.policy.resource_bound)
                self.budget.dispatch(key)
                self._record("resource_started", key=key, name=name)
            # The durable slot survives every exception/lost response. This POST is never retried here.
            response = self._provider.from_checkpoint(self.policy.checkpoint, name=name)
            resource_id = response.get("sailbox_id") if isinstance(response, Mapping) else None
            _require(isinstance(resource_id, str) and _BOX.fullmatch(resource_id)
                     and resource_id not in self.policy.forbidden_resource_ids, "creation returned no admissible resource ID")
            row = self._resource()[1]
            self._attach(key, row, self._provider.observe(resource_id))
            resource = self._resource()
        key, row = resource
        _require(row["observation"] is not None, "creation outcome unresolved; recover only, never create again")
        _require(row["status"] not in ("resume_requested", "sleep_requested", "stop_requested", "terminated", "failed", "create_failed"),
                 "resource lifecycle is unresolved or ended")
        resource_id = row["observation"]["resource_id"]
        observation = self._validate_observation(self._provider.observe(resource_id), row)
        self._sealed(resource_id)
        if observation.status == "sleeping":
            with self.store.atomic():
                self.open_runtime()  # full 24-hour obligation covers this resume on the current UTC day
                self._record("resource_state", key=key, status="resume_requested")
            self._provider.resume(resource_id)
            observation = self._validate_observation(self._provider.observe(resource_id), row)
            self._sealed(resource_id)
            _require(observation.status == "running", "resume outcome unresolved; no repeated resume")
            with self.store.atomic():
                self._record("resource_state", key=key, status="running")
        _require(observation.status == "running", "Gym resource is not confirmed running")
        self.open_runtime()  # no driver/setup work after a midnight/admission boundary without a current check
        if self._driver is None:
            driver = self._driver_factory(self._provider, resource_id)
            _require(getattr(driver, "version", None) == self.policy.gym_bundle
                     and getattr(driver, "_bundle", None) == self._artifact_bundle, "GymDriver bundle differs from reviewed host artifact")
            _require(type(getattr(driver, "retries", None)) is int and driver.retries == 1,
                     "uncertain Gym commands must not be automatically redispatched")
            self._driver = driver
        _require(self._driver.version == self.policy.gym_bundle and self._driver._bundle == self._artifact_bundle,
                 "active GymDriver artifact changed")
        return self._driver

    def _job(self, job):
        if isinstance(job, Mapping):
            allowed = {f.name for f in fields(ResearchJob)}
            _require(set(job) <= allowed and {"family", "version", "code", "params", "window", "roots"} <= set(job), "unknown or missing research job fields")
            job = ResearchJob(**{**job, "roots": tuple(job["roots"]) if isinstance(job["roots"], list) else job["roots"]})
        _require(isinstance(job, ResearchJob) and _identity(job.family) and (job.version is None or type(job.version) is int and job.version >= 1), "invalid research family/version")
        _require(isinstance(job.code, str) and isinstance(job.params, dict), "program and JSON parameters are required")
        _json(job.params)
        from ..gym.safety import check_program
        check_program(job.code)
        _require(job.window in ("train", "validation") and job.purpose in ({"train", "probe", "mechanism", "robustness"} if job.window == "train" else {"validation"}),
                 "Gate/holdout/forward purposes are forbidden")
        _require(isinstance(job.roots, tuple) and bool(job.roots) and len(set(job.roots)) == len(job.roots)
                 and all(r in self.policy.roots for r in job.roots), "root escaped the approved data")
        _require(isinstance(job.stress, (int, float)) and not isinstance(job.stress, bool) and math.isfinite(job.stress) and 0 <= job.stress <= 10,
                 "invalid research stress")
        _require(job.detail in ("full", "summary") and type(job.split) is int and 1 <= job.split <= self.policy.max_split, "invalid reviewed run options")
        if job.window == "validation":
            _require(job.start is None and job.end is None, "Validation is the whole reviewed window")
        else:
            first = self.policy.train_first if job.start is None else job.start
            last = self.policy.train_last if job.end is None else job.end
            _require(_date(self.policy.train_first) <= _date(first) <= _date(last) <= _date(self.policy.train_last), "job dates escaped Train")
            job = ResearchJob(**{**asdict(job), "roots": job.roots, "start": first, "end": last})
        return job

    def _gym_idle(self):
        state = self._load()
        _require(state is None or not any(request["kind"] == "gym" and request["result"] is None
                                        for request in state["requests"].values()),
                 "owned Gym has an unresolved evaluation; original terminal evidence is required")

    def run_gym(self, job: ResearchJob | Mapping, *, key: str):
        job = self._job(job)
        fingerprint = _digest(asdict(job))
        prior = self._prior_request(key, "gym", fingerprint)
        if prior is not None:
            return prior
        with self._lock:
            with self.store.atomic():
                self._gym_idle()  # No resume/setup before an unresolved original job is accounted for.
            driver = self._ensure_gym()
            with self.store.atomic():
                self.open_runtime()
                prior = self._prior_request(key, "gym", fingerprint)
                if prior is not None:
                    return prior
                self._gym_idle()
                self._record("request_started", key=key, kind="gym", fingerprint=fingerprint)
            result = driver.run({"research": (job.code, job.params)}, window=job.window, roots=job.roots, workers=self.policy.workers,
                                split=job.split, stress=job.stress, capital=float(self.policy.capital), detail=job.detail,
                                start=job.start, end=job.end, gate_reason=None, timeout=self.policy.timeout_seconds)
            _require(isinstance(result, Mapping), "Gym returned no terminal document")
            records = result.get("results")
            _require(isinstance(records, list) and len(records) == 1 and isinstance(records[0], Mapping), "Gym returned no single evaluation receipt")
            receipt = records[0]
            _require(receipt.get("window") == job.window and isinstance(receipt.get("roots"), (list, tuple))
                     and set(receipt["roots"]) == set(job.roots) and receipt.get("stress") == job.stress
                     and isinstance(receipt.get("run_id"), str) and bool(receipt["run_id"].strip())
                     and type(receipt.get("trials")) is int and receipt["trials"] >= 0, "Gym evaluation receipt differs from the reviewed job")
            result = {**result, "gym_image": self.policy.checkpoint, "gym_bundle": self.policy.gym_bundle,
                      "gym_execution": self.policy.execution,
                      "execution": {"capital": format(_money(self.policy.capital).normalize(), "f"), "workers": self.policy.workers,
                                    "split": job.split, "window": job.window, "start": job.start, "end": job.end,
                                    "roots": list(job.roots), "stress": job.stress}}
            reference = self._write_reply(result)
            with self.store.atomic():
                self._record("request_finished", key=key, result=reference)
            return result

    def evaluate(self, profile, items, *, key, tools=None, tool_choice="auto", effort="low", max_output=None, cache_key=None):
        _require(isinstance(profile, str) and profile in self._models and isinstance(items, (list, tuple)) and bool(items), "unapproved model profile or input")
        capability = self._models[profile]
        policy = capability.policy
        output = policy.max_output_tokens if max_output is None else max_output
        _require(type(output) is int and 1 <= output <= policy.max_output_tokens and effort in policy.allowed_efforts
                 and tool_choice in ("auto", "none", "required") and (cache_key is None or _identity(cache_key)), "model options escaped host policy")
        _require(tools is None or isinstance(tools, (list, tuple)), "tools must be reviewed definitions")
        selected_tools = list(tools or ())
        approved = {_digest(t) for t in policy.allowed_tools}
        _require(all(isinstance(t, Mapping) and _digest(t) in approved for t in selected_tools), "unreviewed model tool definition")
        for item in items:
            _require(isinstance(item, Mapping), "text-only model input records are required")
            kind = item.get("type")
            if kind in (None, "message"):
                _require(set(item) <= {"type", "role", "content", "id", "status"}
                         and item.get("role") in ("system", "developer", "user", "assistant"), "unsupported model message fields")
                content = item.get("content")
                _require(isinstance(content, str) or (isinstance(content, list) and all(
                    isinstance(v, Mapping) and set(v) <= {"type", "text", "annotations"}
                    and v.get("type") in ("input_text", "output_text") and isinstance(v.get("text"), str) for v in content)),
                    "model media, URLs and provider fetch requests are forbidden")
            elif kind == "function_call":
                _require(set(item) <= {"type", "call_id", "name", "arguments", "id", "status"}
                         and isinstance(item.get("arguments"), str), "unsupported model tool history")
            elif kind == "function_call_output":
                _require(set(item) <= {"type", "call_id", "output", "id", "status"} and "output" in item, "unsupported tool-output history")
            elif kind == "reasoning":
                _require(set(item) <= {"type", "id", "summary", "encrypted_content", "status"}
                         and isinstance(item.get("summary"), list) and all(isinstance(v, Mapping)
                         and set(v) == {"type", "text"} and v["type"] == "summary_text" and isinstance(v["text"], str)
                         for v in item["summary"]), "unsupported reasoning history")
            else:
                raise ResearchCapabilityError("unsupported model input capability")
        body = {"model": policy.model, "input": list(items), "tools": selected_tools, "tool_choice": tool_choice,
                "reasoning_effort": effort, "max_output_tokens": output, "cache_key": cache_key, "request_key": key,
                "timeout_seconds": policy.timeout_seconds}
        _json(body)
        fingerprint = _digest(body)
        prior = self._prior_request(key, "model", fingerprint)
        if prior is not None:
            return prior
        tokens = capability.count_tokens(body)
        _require(type(tokens) is int and 0 < tokens <= policy.max_input_tokens, "full model payload exceeds its host input ceiling")
        ceiling = (_money(policy.input_usd_million) * tokens + _money(policy.output_usd_million) * output) / Decimal(1000000) + _money(policy.fixed_usd)
        ceiling = ceiling.quantize(Decimal("0.000000001"), rounding=ROUND_CEILING)
        _require(ceiling > 0, "host model bill ceiling must be positive")
        self.open_runtime()
        now = _time(self.store.clock())
        _require(policy.valid_from <= now < policy.valid_until, "host model price evidence is stale")
        daily_key = "model-" + hashlib.sha256((self.policy.scope + ":" + key).encode()).hexdigest()
        with self.store.atomic():
            prior = self._prior_request(key, "model", fingerprint)
            if prior is not None:
                return prior
            self.open_runtime()
            _require(policy.valid_from <= _time(self.store.clock()) < policy.valid_until, "host model price evidence expired before dispatch")
            self.budget.reserve_inference(daily_key, format(ceiling, "f"), provenance=policy.provenance)
            self.budget.dispatch(daily_key)
            self._record("request_started", key=key, kind="model", fingerprint=fingerprint)
        reply = capability.send(body)  # no automatic retry, fallback or model-supplied price/cost authority
        _require(isinstance(reply, ModelReply) and isinstance(reply.result, dict)
                 and reply.result.get("status") in ("completed", "succeeded", "incomplete", "failed", "cancelled"), "model response is not known terminal")
        public = {field: reply.result[field] for field in ("id", "status", "output", "usage", "model", "incomplete_details",
                                                        "created_at", "completed_at", "object") if field in reply.result}
        result = {**public, "profile": profile, "request_key": key, "cost_usd": None, "accrued_day": None,
                  "cost_status": "unknown"}
        if reply.actual_usd is not None:
            _money(reply.actual_usd)
            _date(reply.accrued_day)
            _require(isinstance(reply.provenance, str) and bool(reply.provenance.strip()), "authoritative model cost provenance is required")
            self.budget.settle_inference(daily_key, actual_usd=reply.actual_usd, accrued_day=reply.accrued_day, provenance=reply.provenance)
            result.update(cost_usd=format(_money(reply.actual_usd), "f"), accrued_day=reply.accrued_day,
                          cost_status="vendor_actual")
        result = self._model_cost_view(key, result)
        reference = self._write_reply(result)
        with self.store.atomic():
            self._record("request_finished", key=key, result=reference)
        return result

    def _stop(self, operation):
        self._scope()
        with self._lock:
            resource = self._resource()
            if resource is None:
                return {"status": "absent"}
            key, row = resource
            _require(row["observation"] is not None, "unbound creation must be recovered before scoped control")
            resource_id = row["observation"]["resource_id"]
            if row["status"] == "terminated":
                return {"status": "terminated", "runtime_stopped": True, "vendor_actual": False}
            self._validate_observation(self._provider.observe(resource_id), row, stopping=True)
            with self.store.atomic():
                self._record("resource_state", key=key, status="sleep_requested" if operation == "sleep" else "stop_requested")
            response = getattr(self._provider, operation)(resource_id)
            matching = isinstance(response, Mapping) and response.get("sailbox_id") == resource_id
            status = response.get("status") if matching else "unknown"
            if status == "terminated":
                with self.store.atomic():
                    self.budget.terminal_observed(key, resource_id, observed_at=self.store.clock(), status="terminated", provenance="matching host control response")
                    self._record("resource_state", key=key, status="terminated")
            elif operation == "sleep" and status == "sleeping":
                with self.store.atomic():
                    self._record("resource_state", key=key, status="sleeping")
            return {"status": status, "runtime_stopped": status in ("terminated", "sleeping"), "vendor_actual": False}

    def sleep_gym(self):
        return self._stop("sleep")

    def stop_gym(self):
        return self._stop("terminate")

    def handle(self, operation: str, payload: Mapping):
        """Exact high-level IPC schema; authentication must happen before this method."""
        try:
            _require(isinstance(operation, str) and isinstance(payload, Mapping), "invalid capability request")
            _json(payload)
            if operation in ("open_runtime", "summary", "recover_gym", "sleep_gym", "stop_gym"):
                _require(not payload, "operation accepts no controller resource or scope arguments")
                return getattr(self, operation)()
            if operation == "cached_result":
                _require(set(payload) <= {"key", "kind"} and "key" in payload, "invalid cached-result fields")
                return self.cached_result(**payload)
            if operation == "run_gym":
                _require(set(payload) == {"job", "key"}, "invalid Gym capability fields")
                return self.run_gym(**payload)
            if operation == "evaluate":
                _require({"profile", "items", "key"} <= set(payload) <= {"profile", "items", "key", "tools", "tool_choice", "effort", "max_output", "cache_key"},
                         "invalid model capability fields")
                return self.evaluate(**payload)
            raise ResearchCapabilityError("unknown capability operation")
        except _ReplyIntegrityError:
            self._closed_reply("immutable terminal reply is missing or changed")
            raise
        finally:
            self._peer.identity = None


__all__ = ["ResearchBroker", "ResearchCapabilityError", "ResearchPolicy", "ResearchJob", "PeerIdentity", "IsolationProof",
           "ResourceObservation", "ModelPolicy", "ModelCapability", "ModelReply", "ISOLATION_FACTS", "NAMESPACE_FACTS"]
