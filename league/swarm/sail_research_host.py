"""Sail host adapters for the isolated broker; importing this module makes no calls.

An owner-private operator factory supplies separately hash-reviewed checkpoint,
model, billing, context, ancestry and terminal-bill receipts. Observed public rates
are deliberately not accepted as a guaranteed price interval. No environment key,
ordinary Provider budget, adoption, fallback or automatic POST retry is used.

Provider intents and content-addressed raw receipts live in the existing private
host journal. A lost create can discover candidates, but a name is not checkpoint
ancestry. Unknown model costs stay in the shared DailyBudget until an authoritative
original-request bill is available. The bridge never creates a new allowance.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import datetime as dt
from decimal import Decimal, ROUND_CEILING
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import stat
import time
from typing import Callable
from urllib.request import build_opener

from ..sailbox import SailboxClient, Transport as BoxTransport
from ..gym.driver import GymDriver, build_bundle
from .daily_compute import DailyAdmissionError, DailyBudget, InventoryEvidence, ResourceBound, TariffEvidence
from .research_host import HostAdapters, HostConfig, ReviewedFile
from .research_sandbox import HostContextEvidence, _host_context, _verify_artifact
from .research_state import artifact_identity
from .research_transport import (EVENT_KIND, STATE_KEY, ModelCapability, ModelPolicy,
                                 ModelReply, ResearchBroker, ResearchCapabilityError,
                                 _decode, _digest, _json)
from .store import SwarmStore

HOST_EVENT = "swarm.research_host"  # Already excluded from the House/public mirror.
_BOX = re.compile(r"sb_[0-9a-fA-F-]{8,64}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_RESPONSE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}\Z")
_NAME = re.compile(r"ltcm-research-[0-9a-f]{12}-[0-9a-f]{32}\Z")
_MAX = 24 * 1024 * 1024


def _require(condition, reason):
    if not condition:
        raise ResearchCapabilityError(reason)


def _time(value):
    _require(type(value) in (int, float) and math.isfinite(value) and value >= 0,
             "invalid Sail receipt clock")
    return float(value)


def _timestamp(value):
    _require(isinstance(value, str), "Sail created_at must be a UTC timestamp")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        _require(parsed.utcoffset() == dt.timedelta(0), "Sail timestamp must be UTC")
        return _time(parsed.timestamp())
    except ValueError as exc:
        raise ResearchCapabilityError("invalid Sail timestamp") from exc


@dataclass(frozen=True)
class SailBridgeInputs:
    """Host operator capabilities; every returned file has an independent approved hash.

    Fresh receipt resolvers may obtain newly reviewed evidence. They must never
    derive exclusivity, baseline, price coverage or checkpoint safety from a model.
    None ancestry/bill results mean unresolved, rather than approval or zero cost.
    """
    checkpoint: ReviewedFile
    models: ReviewedFile
    billing: Callable[[], ReviewedFile]
    context: Callable[[str], HostContextEvidence]
    ancestry: Callable[[str, str], ReviewedFile | None]
    bill: Callable[[str, str], ReviewedFile | None]

    def __post_init__(self):
        _require(isinstance(self.checkpoint, ReviewedFile) and isinstance(self.models, ReviewedFile)
                 and all(callable(getattr(self, name)) for name in ("billing", "context", "ancestry", "bill")),
                 "explicit independently reviewed Sail receipt sources required")


class _Bridge:
    def __init__(self, config, inputs, clock, cleanup_only=False):
        _require(isinstance(config, HostConfig) and isinstance(inputs, SailBridgeInputs),
                 "explicit isolated HostConfig and SailBridgeInputs required")
        _require(type(cleanup_only) is bool, "explicit cleanup mode required")
        self.config, self.inputs, self.clock, self.cleanup_only = config, inputs, clock, cleanup_only
        self.policy = config.research_policy
        _verify_artifact(config.spec())
        own_hash = dict(config.artifact_files).get("league/swarm/sail_research_host.py")
        _require(own_hash is not None and hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == own_hash,
                 "loaded Sail bridge source differs from the reviewed artifact manifest")
        _require(artifact_identity(self.policy.checkpoint, config.artifact_root) == config.spec().expected_evaluator,
                 "Sail bridge artifact identity differs")
        self.checkpoint = self.receipt(inputs.checkpoint)
        expected = {"schema", "scope", "checkpoint_id", "source_sailbox_id", "app_id", "image_id",
                    "source_checkpoint_generation", "resource_bound", "gym_bundle", "gym_execution",
                    "store_root", "remote_root", "python", "train_validation_only", "guest_credentials_absent",
                    "no_live_processes", "no_network", "provenance"}
        c = self.checkpoint
        _require(set(c) == expected and c["schema"] == 1 and c["scope"] == self.policy.scope
                 and c["checkpoint_id"] == self.policy.checkpoint
                 and c["gym_bundle"] == self.policy.gym_bundle and c["gym_execution"] == self.policy.execution,
                 "checkpoint receipt differs from the reviewed research artifact")
        _require(isinstance(c["source_sailbox_id"], str) and _BOX.fullmatch(c["source_sailbox_id"])
                 and isinstance(c["app_id"], str) and re.fullmatch(r"app_[A-Za-z0-9-]{8,80}", c["app_id"])
                 and isinstance(c["image_id"], str) and c["image_id"].startswith("sha256:")
                 and _SHA.fullmatch(c["image_id"][7:]) and type(c["source_checkpoint_generation"]) is int
                 and c["source_checkpoint_generation"] >= 0,
                 "authoritative checkpoint origin/app/image receipt required")
        _require(ResourceBound(**c["resource_bound"]) == self.policy.resource_bound
                 and all(c[name] is True for name in ("train_validation_only", "guest_credentials_absent",
                                                      "no_live_processes", "no_network")),
                 "reviewed checkpoint resource/data/process/credential evidence is incomplete")
        for name in ("store_root", "remote_root"):
            value = c[name]
            _require(isinstance(value, str) and re.fullmatch(r"/[A-Za-z0-9_/-]{1,160}", value)
                     and all(part not in (".", "..") for part in value.split("/"))
                     and not value.endswith("/"), "plain reviewed guest paths required")
        _require(c["store_root"] != c["remote_root"] and c["python"] in ("python3", "/usr/bin/python3"),
                 "separate approved data/code roots and Python required")
        self.profile_receipt = self.receipt(inputs.models)
        m = self.profile_receipt
        _require(set(m) == {"schema", "scope", "profiles", "provenance"} and m["schema"] == 1
                 and m["scope"] == self.policy.scope and isinstance(m["profiles"], dict) and m["profiles"],
                 "reviewed Sail model profiles required")
        self.model_policies = {}
        for name, row in m["profiles"].items():
            _require(isinstance(name, str) and _RESPONSE.fullmatch(name) and isinstance(row, dict)
                     and set(row) == {"policy", "max_request_bytes", "billable_input_ceiling", "completion_window", "agreement"},
                     "invalid reviewed Sail model profile")
            policy = ModelPolicy(**{**row["policy"], "allowed_efforts": tuple(row["policy"]["allowed_efforts"]),
                                   "allowed_tools": tuple(row["policy"]["allowed_tools"])})
            _require(type(row["max_request_bytes"]) is int and 0 < row["max_request_bytes"] <= 4*1024*1024
                     and type(row["billable_input_ceiling"]) is int
                     and row["billable_input_ceiling"] == policy.max_input_tokens
                     and row["completion_window"] in ("asap", "balanced"),
                     "whole-input billable ceiling and reviewed asap/balanced route required")
            from ltcm.provider import PROFILES
            if name in PROFILES:
                _require((policy.model, row["completion_window"]) == PROFILES[name][:2],
                         "stock Sail profile/model/completion window changed")
            self.agreement(row["agreement"], model=True)
            self.model_policies[name] = policy
        self.policy_digest = _digest({"research": asdict(self.policy),
                                     "models": {k: asdict(v) for k, v in sorted(self.model_policies.items())}})
        if not cleanup_only:
            tariff, inventory = self.fresh()
            store = self.store()
            try:
                _require(DailyBudget(store, tariff, inventory).summary()["within_cap"],
                         "existing shared ledger/current-day baseline required before Sail client construction")
            finally:
                store.close()

    def receipt(self, approved):
        _require(isinstance(approved, ReviewedFile), "independently approved receipt required")
        path = approved.path
        _require(not any(root == path or root in path.parents for root in
                         (self.config.artifact_root, self.config.state_root)),
                 "trusted Sail receipts must remain outside controller mounts")
        value = _decode(approved.read().decode("utf-8"))
        _require(isinstance(value, dict) and isinstance(value.get("provenance"), str)
                 and value["provenance"].strip(), "trusted receipt provenance required")
        return value

    def agreement(self, value, *, model=False):
        kind = "binding_maximum_billable_tokens_and_rates" if model else "binding_maximum_rates"
        _require(isinstance(value, dict) and set(value) == {"kind", "path", "sha256", "inclusive_fees_taxes", "ongoing_liability_covered"}
                 and value["kind"] == kind,
                 "observed prices cannot certify maximum billable charges")
        _require(value["inclusive_fees_taxes"] is True and value["ongoing_liability_covered"] is True,
                 "agreement must cover taxes, fees and ongoing accepted liabilities")
        approved = ReviewedFile(Path(value["path"]), value["sha256"])
        _require(not any(root == approved.path or root in approved.path.parents for root in
                         (self.config.artifact_root, self.config.state_root)), "agreement must be host private")
        approved.read()  # Its interpretation is independently reviewed, not inferred from a rate GET.

    def billing(self, *, initialization_preflight=False):
        _require(type(initialization_preflight) is bool
                 and (not initialization_preflight or self.cleanup_only),
                 "first-admission billing preflight is restricted to a passive bridge")
        b = self.receipt(self.inputs.billing())
        _require(set(b) == {"schema", "scope", "observed_at", "valid_until", "tariff", "inventory", "agreement", "provenance"}
                 and b["schema"] == 1 and b["scope"] == self.policy.scope,
                 "fresh complete Sail billing receipt required")
        now = _time(self.clock())
        _require(_time(b["observed_at"]) <= now <= _time(b["valid_until"]) <= b["observed_at"] + 300,
                 "Sail billing receipt is stale")
        self.agreement(b["agreement"])
        tariff = TariffEvidence(**b["tariff"])
        inventory = InventoryEvidence(**{**b["inventory"], "resource_ids": tuple(b["inventory"]["resource_ids"]),
                                         "model_keys": tuple(b["inventory"]["model_keys"])})
        _require(tariff.scope == inventory.scope == self.policy.scope
                 and inventory.observed_at <= now <= inventory.valid_until <= inventory.observed_at+300
                 and inventory.complete and inventory.exclusive_writer and not inventory.unknown_obligations,
                 "fresh complete exclusive billing inventory required")
        # A provider-free initializer validates billing before it creates the
        # original allowance. This explicit preflight conveys no model-only or
        # paid authority, needs the full compute day, and never opens SQLite.
        if initialization_preflight:
            _require(tariff.covers_day(int(now//86400)),
                     "first-admission preflight requires full-day compute prices")
            return tariff, inventory
        # Normal admission requires existing replay-checked history. Read it
        # without schema creation/migration; absent or corrupt history refuses.
        from . import DB_NAME
        database = self.config.broker_root/DB_NAME
        _require(database.is_file() and not database.is_symlink(),
                 "billing requires the intact original ledger")
        store = SwarmStore(self.config.broker_root, clock=self.clock, readonly=True)
        try:
            store._exec("BEGIN")
            ledger = DailyBudget(store, tariff, inventory)._load()
            _require(not ledger["resources"] or tariff.covers_day(int(now//86400)),
                     "resource history requires guaranteed full-day compute prices")
        finally:
            store.close()
        return tariff, inventory

    def context(self, digest):
        _require(digest == self.policy_digest, "Sail model/research policy digest changed")
        evidence = self.inputs.context(digest)
        value = _host_context(evidence, self.config.spec(), self.clock())
        _require(value["policy_digest"] == digest and value["broker_root"] == str(self.config.broker_root)
                 and {"path": str(self.config.adapter_file.path), "sha256": self.config.adapter_file.sha256} in value["adapters"],
                 "fresh actual host context differs from Sail bridge")
        return evidence

    def fresh(self):
        _require(not self.cleanup_only, "cleanup-only Sail adapter has no paid research authority")
        self.context(self.policy_digest)
        return self.billing()

    def store(self):
        store = SwarmStore(self.config.broker_root, clock=self.clock)
        # A FULL commit of the bridge intent flushes the preceding shared-ledger
        # reservations as well as this no-retry dispatch marker before the POST.
        store._exec("PRAGMA synchronous=FULL")
        return store

    def state(self, store):
        state = None
        for row in store._all("SELECT payload FROM events WHERE kind=? ORDER BY seq", (EVENT_KIND,)):
            state = ResearchBroker._apply(state, _decode(row["payload"]))
        cache = store._one("SELECT value FROM kv WHERE key=?", (STATE_KEY,))
        _require(state is not None and cache is not None and _json(state, _MAX) == _json(_decode(cache["value"]), _MAX)
                 and state["scope"] == self.policy.scope and state["policy_digest"] == self.policy_digest,
                 "Sail operation lacks intact original broker dispatch history")
        return state

    def resource(self, resource_id=None, *, name=None, paid=True):
        tariff, inventory = self.fresh() if paid else (self.config.tariff, self.config.inventory)
        store = self.store()
        try:
            state = self.state(store)
            if paid:
                _require(not state["closed"] and DailyBudget(store, tariff, inventory).summary()["within_cap"],
                         "Sail operation lacks shared admitted dollar room")
            _require(len(state["resources"]) == 1, "exactly one original research resource intent required")
            key, row = next(iter(state["resources"].items()))
            ledger = DailyBudget(store, tariff, inventory)._load()
            liability = ledger["resources"].get(key)
            _require(liability is not None and liability["dispatch_at"] is not None and not liability["canceled"]
                     and ResourceBound(**liability["bound"]) == self.policy.resource_bound,
                     "resource lacks the original dispatched shared-budget reservation")
            _require(name is None or row["name"] == name, "creation name escaped original broker intent")
            if resource_id is not None:
                _require(isinstance(resource_id, str) and _BOX.fullmatch(resource_id)
                         and resource_id not in self.policy.forbidden_resource_ids,
                         "unowned or production resource refused")
                observation = row["observation"]
                _require(observation is not None and observation["resource_id"] == resource_id,
                         "arbitrary resource ID/adoption refused")
            return key, row, state
        finally:
            store.close()

    def journal(self, action, key, document=None, *, exclusive=False):
        """Immutable events plus durable content hashes, all under the existing private host root."""
        store = self.store()
        try:
            with store.atomic():
                rows = [_decode(r["payload"]) for r in store._all("SELECT payload FROM events WHERE kind=? ORDER BY seq", (HOST_EVENT,))]
                found = [r for r in rows if r.get("action") == "sail_bridge_"+action and r.get("key") == key]
                _require(len(found) <= 1, "duplicate Sail bridge receipt")
                if found:
                    _require(not exclusive, "original Sail dispatch is already sent or uncertain; no retry")
                    row = found[0]
                    _require(set(row) == {"action", "key", "scope", "policy_digest", "sha256"}
                             and row["scope"] == self.policy.scope and row["policy_digest"] == self.policy_digest,
                             "Sail bridge receipt scope changed")
                    old = self.read_blob(row["sha256"])
                    _require(document is None or _digest(document) == _digest(old), "Sail bridge receipt changed")
                    return old
                if document is None:
                    return None
                digest = self.write_blob(document)
                store.event(HOST_EVENT, None, {"action": "sail_bridge_"+action, "key": key, "scope": self.policy.scope,
                                              "policy_digest": self.policy_digest, "sha256": digest})
                return document
        finally:
            store.close()

    def blobs(self):
        root = self.config.broker_root / "sail-bridge-results"
        root.mkdir(mode=0o700, exist_ok=True)
        info = root.lstat()
        _require(stat.S_ISDIR(info.st_mode) and not root.is_symlink() and info.st_uid == os.getuid()
                 and stat.S_IMODE(info.st_mode) == 0o700, "private Sail receipt directory required")
        return root

    def read_blob(self, digest):
        _require(isinstance(digest, str) and _SHA.fullmatch(digest), "invalid Sail receipt hash")
        path = self.blobs()/(digest+".json")
        info = path.lstat()
        _require(stat.S_ISREG(info.st_mode) and not path.is_symlink() and info.st_uid == os.getuid()
                 and stat.S_IMODE(info.st_mode) == 0o600 and info.st_size <= _MAX, "private Sail receipt changed")
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as handle:
            raw = handle.read(_MAX+1)
        _require(hashlib.sha256(raw).hexdigest() == digest, "Sail receipt bytes changed")
        return _decode(raw.decode())

    def write_blob(self, document):
        raw = _json(document, _MAX).encode(); digest = hashlib.sha256(raw).hexdigest()
        path = self.blobs()/(digest+".json")
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            _require(self.read_blob(digest) == document, "Sail receipt collision")
            return digest
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw); handle.flush(); os.fsync(handle.fileno())
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        return digest

    def intent(self, key, document):
        self.journal("intent", key, document, exclusive=True)

    def terminal_bill(self, key, response, model, body_sha):
        approved = self.inputs.bill(key, response)
        if approved is None:
            return None
        bill = self.receipt(approved)
        _require(set(bill) == {"schema", "scope", "request_key", "response_id", "model", "body_sha256",
                              "actual_usd", "accrued_day", "final", "provenance"}
                 and bill["schema"] == 1 and bill["scope"] == self.policy.scope and bill["request_key"] == key
                 and bill["response_id"] == response and bill["model"] == model
                 and bill["body_sha256"] == body_sha and bill["final"] is True,
                 "actual model bill is not linked to the original request")
        _require(isinstance(bill["actual_usd"], str), "exact terminal bill units required")
        try:
            amount = Decimal(bill["actual_usd"])
            _require(amount.is_finite() and amount >= 0
                     and dt.date.fromisoformat(bill["accrued_day"]).isoformat() == bill["accrued_day"],
                     "invalid authoritative terminal model bill/day")
        except (ArithmeticError, ValueError, TypeError) as exc:
            raise ResearchCapabilityError("invalid authoritative terminal model bill/day") from exc
        self.journal("bill", "model:"+key, bill)
        return bill


class SailResearchProvider:
    """Restricted facade: only original broker-created Gym IDs are operable."""
    def __init__(self, bridge, client):
        self.bridge, self.client = bridge, client

    def from_checkpoint(self, checkpoint, *, name):
        b = self.bridge
        _require(checkpoint == b.policy.checkpoint and isinstance(name, str) and _NAME.fullmatch(name),
                 "unapproved checkpoint/name refused")
        key, row, _ = b.resource(name=name)
        _require(row["observation"] is None and row["status"] == "creating", "creation intent already attached")
        b.intent("create:"+key, {"checkpoint_id": checkpoint, "name": name})
        reply = self.client.from_checkpoint(checkpoint, name=name)
        self._ancestry(reply, name)
        b.journal("result", "create:"+key, reply)
        return reply

    def _ancestry(self, reply, name):
        c = self.bridge.checkpoint
        _require(isinstance(reply, dict) and reply.get("checkpoint_id") == c["checkpoint_id"]
                 and reply.get("name") == name and reply.get("source_checkpoint_generation") == c["source_checkpoint_generation"]
                 and isinstance(reply.get("sailbox_id"), str) and _BOX.fullmatch(reply["sailbox_id"])
                 and reply["sailbox_id"] not in self.bridge.policy.forbidden_resource_ids,
                 "provider creation receipt does not prove reviewed checkpoint ancestry")

    def _observation(self, row, intent, ancestry):
        from .research_transport import ResourceObservation
        b = self.bridge; c = b.checkpoint
        self._ancestry(ancestry, intent["name"])
        _require(isinstance(row, dict) and row.get("sailbox_id") == ancestry["sailbox_id"]
                 and row.get("name") == intent["name"] and row.get("app_id") == c["app_id"]
                 and row.get("image_id") == c["image_id"] and row.get("volume_mounts") == [],
                 "Sail resource app/image/name/volume readback differs")
        _require(type(row.get("vcpu_count")) is int and row["vcpu_count"] > 0
                 and type(row.get("memory_mib")) is int and row["memory_mib"] > 0
                 and type(row.get("state_disk_size_gib")) is int and row["state_disk_size_gib"] > 0,
                 "Sail readback lacks hard resource capacities")
        bound = ResourceBound(b.policy.resource_bound.spec_id, "gym", row["vcpu_count"],
                              str(Decimal(row["memory_mib"])/1024), str(row["state_disk_size_gib"]), "0",
                              b.policy.resource_bound.creation_fee_usd,
                              "Sail hard-cap GET plus independently reviewed inclusive creation-fee maximum")
        created = _timestamp(row.get("created_at"))
        _require(intent["at"] <= created <= _time(b.clock()), "resource predates original dispatch or is from the future")
        status = "starting" if row.get("status") == "creating" else row.get("status")
        _require(status in ("running", "sleeping", "paused", "starting", "terminating", "terminated", "failed", "create_failed"),
                 "unknown Sail resource status")
        return ResourceObservation(row["sailbox_id"], row["name"], ancestry["checkpoint_id"], created, bound, status,
                                   "documented Sail GET + durable original provider ancestry receipt "+_digest(ancestry))

    def observe(self, resource_id):
        b = self.bridge
        # During initial attachment the broker still has the unbound original intent.
        key, intent, _ = b.resource(paid=False)
        ancestry = b.journal("result", "create:"+key)
        _require(ancestry is not None and ancestry.get("sailbox_id") == resource_id,
                 "observation requires durable original creation ancestry")
        if intent["observation"] is not None:
            b.resource(resource_id, paid=False)
        return self._observation(self.client.get(resource_id), intent, ancestry)

    def find_created(self, name, *, checkpoint):
        b = self.bridge
        _require(checkpoint == b.policy.checkpoint, "recovery checkpoint changed")
        key, intent, _ = b.resource(name=name, paid=False)
        _require(b.journal("intent", "create:"+key) == {"checkpoint_id": checkpoint, "name": name},
                 "recovery lacks original sent creation intent")
        matches=[]; offset=0
        for _ in range(1000):
            page = self.client.transport("GET", "/sailboxes", query={"app": b.checkpoint["app_id"], "search": name,
                                                                           "limit": 100, "offset": offset})
            _require(isinstance(page, dict) and isinstance(page.get("data"), list) and type(page.get("has_more")) is bool,
                     "incomplete Sail candidate list")
            matches.extend(r for r in page["data"] if isinstance(r, dict) and r.get("name") == name)
            if not page["has_more"]:
                break
            _require(bool(page["data"]), "Sail pagination made no progress")
            offset += len(page["data"])
        else:
            raise ResearchCapabilityError("Sail candidate search exceeded its bound")
        _require(len(matches) <= 1, "ambiguous exact-name Sail creation")
        if not matches:
            return None
        ancestry = b.journal("result", "create:"+key)
        if ancestry is None:
            approved = b.inputs.ancestry(name, checkpoint)
            if approved is None:
                return None  # Candidate is not authoritative ancestry. Keep liability.
            receipt = b.receipt(approved)
            _require(set(receipt) == {"schema", "scope", "name", "checkpoint_id", "provider_response", "provenance"}
                     and receipt["schema"] == 1 and receipt["scope"] == b.policy.scope
                     and receipt["name"] == name and receipt["checkpoint_id"] == checkpoint,
                     "reviewed recovery ancestry differs from original dispatch")
            ancestry = receipt["provider_response"]
            self._ancestry(ancestry, name)
            _require(ancestry["sailbox_id"] == matches[0].get("sailbox_id"), "ancestry names a different candidate")
            b.journal("result", "create:"+key, ancestry)
        return self._observation(self.client.get(ancestry["sailbox_id"]), intent, ancestry)

    def egress(self, resource_id):
        key, intent, _ = self.bridge.resource(paid=False)
        ancestry = self.bridge.journal("result", "create:"+key)
        _require(ancestry is not None and ancestry["sailbox_id"] == resource_id, "unowned egress read refused")
        return self.client.egress(resource_id)

    def _control(self, operation, resource_id):
        b = self.bridge
        key, row, _ = b.resource(resource_id, paid=operation == "resume")
        expected = {"resume":"resume_requested", "sleep":"sleep_requested", "terminate":"stop_requested"}[operation]
        _require(row["status"] == expected, "control lacks original broker lifecycle intent")
        store = b.store()
        try:
            markers = [(r["seq"], _decode(r["payload"])) for r in store._all(
                "SELECT seq,payload FROM events WHERE kind=? ORDER BY seq", (EVENT_KIND,))]
            marker = next((seq for seq, event in reversed(markers) if event.get("action") == "resource_state"
                           and event.get("key") == key and event.get("status") == expected), None)
            _require(marker is not None, "control lacks immutable original lifecycle event")
        finally:
            store.close()
        slot = operation+":"+key+":"+str(marker)
        b.intent(slot, {"resource_id": resource_id, "operation": operation})
        reply = getattr(self.client, operation)(resource_id)
        _require(isinstance(reply, dict) and reply.get("sailbox_id") == resource_id, "control response changed resource identity")
        b.journal("result", slot, reply)
        return reply

    def resume(self, resource_id): return self._control("resume", resource_id)
    def sleep(self, resource_id): return self._control("sleep", resource_id)
    def terminate(self, resource_id): return self._control("terminate", resource_id)

    def reconcile_model_bill(self, key):
        """Host-only, no POST: settle a later original-request invoice, never rewrite its reply.

        The immutable controller reply can still say cost unknown. DailyBudget is
        the authority and subsequently reports the linked actual bill. No guessed
        usage/rate cost, response creation-day inference, or reset is performed.
        """
        b=self.bridge; store=b.store()
        try:
            state=b.state(store); request=state["requests"].get(key)
            _require(request is not None and request["kind"]=="model" and request["result"] is not None,
                     "late bill requires original known terminal broker response")
            original=b.journal("intent", "model:"+key); reply=b.journal("result", "model:"+key)
            _require(isinstance(original,dict) and isinstance(reply,dict)
                     and reply.get("status") in ("completed","incomplete","failed","cancelled"),
                     "late bill lacks original provider terminal evidence")
            bill=b.terminal_bill(key,reply["id"],reply["model"],original["body_sha256"])
            if bill is None:
                return {"outcome_known":False,"vendor_actual":False}
            budget=DailyBudget(store,b.config.tariff,b.config.inventory)
            daily_key="model-"+hashlib.sha256((b.policy.scope+":"+key).encode()).hexdigest()
            expected=int((Decimal(bill["actual_usd"])*1000000000).to_integral_value(rounding=ROUND_CEILING))
            settlement_error=None
            with store.atomic():
                liability=budget._load()["inference"][daily_key]
                existing=liability["receipt"]
                if existing is None:
                    try:
                        budget.settle_inference(daily_key,actual_usd=bill["actual_usd"],accrued_day=bill["accrued_day"],provenance=bill["provenance"])
                    except DailyAdmissionError as exc:
                        # The nested settlement records a breach before raising.
                        # Commit it here; an escaping error would roll it back and
                        # leave later paid requests able to dispatch.
                        if expected <= liability["max_nanos"] or not budget._load()["breached"]:
                            raise
                        settlement_error=exc
                else:
                    day=(dt.date.fromisoformat(bill["accrued_day"])-dt.date(1970,1,1)).days
                    _require(existing["accrued_day"]==day and existing["actual_nanos"]==expected,
                             "late bill contradicts original settled liability")
            if settlement_error is not None:
                raise settlement_error
            return {"outcome_known":True,"vendor_actual":True,"actual_usd":bill["actual_usd"],"accrued_day":bill["accrued_day"]}
        finally:
            store.close()

    def _guest(self, resource_id):
        _, row, state = self.bridge.resource(resource_id)
        _require(row["status"] == "running" and any(r["kind"] == "gym" and r["result"] is None
                                                    for r in state["requests"].values()),
                 "guest operation lacks an original pending research evaluation")

    def upload(self, resource_id, path, content, **options):
        self._guest(resource_id)
        _require(path.startswith(self.bridge.checkpoint["remote_root"]+"/") and "/../" not in path,
                 "Gym upload escaped reviewed code root")
        return self.client.upload(resource_id, path, content, **options)

    def download(self, resource_id, path, **options):
        self._guest(resource_id)
        _require(path.startswith(self.bridge.checkpoint["remote_root"]+"/") and "/../" not in path,
                 "Gym download escaped reviewed code root")
        return self.client.download(resource_id, path, **options)

    def exec(self, resource_id, command, **options):
        self._guest(resource_id)
        return self.client.exec(resource_id, command, **options)


class _ExactGymDriver(GymDriver):
    def ensure_code(self):
        """Always install approved bytes; inherited READY markers are not code evidence."""
        q = shlex.quote
        archive = self.code_dir+".tgz"
        self._retry("upload", self.client.upload, self.box, archive, self._bundle)
        result = self._exec(f"rm -rf {q(self.code_dir)} && mkdir -p {q(self.code_dir)} && tar -xzf {q(archive)} -C {q(self.code_dir)}", timeout=300)
        _require(getattr(result, "return_code", None) == 0, "approved Gym bundle installation failed")
        return self.code_dir

    def run(self, programs, **options):
        _require(options.get("window") in ("train", "validation") and options.get("gate_reason") is None,
                 "Gate/heldout/forward Gym routes are forbidden")
        bridge = self.client.bridge
        _, _, state = bridge.resource(self.box)
        pending = [key for key, row in state["requests"].items() if row["kind"] == "gym" and row["result"] is None]
        _require(len(pending) == 1, "one original pending Gym request required")
        # Fresh original-request paths prevent inherited checkpoint results, or a
        # different request's same-program cache, from becoming a new trial.
        self.remote_root = bridge.checkpoint["remote_root"]+"/requests/"+hashlib.sha256(pending[0].encode()).hexdigest()
        self.code_dir = self.remote_root+"/code/"+self.version
        probe = self._exec("test ! -e "+shlex.quote(self.remote_root), timeout=60)
        _require(getattr(probe, "return_code", None) == 0, "existing Gym request path is unresolved; no rerun or evaluation reuse")
        return super().run(programs, **options)


class _SailModel:
    def __init__(self, bridge, profile, transport, *, monotonic=time.monotonic, sleep=time.sleep):
        self.bridge, self.profile, self.transport = bridge, profile, transport
        self.row = bridge.profile_receipt["profiles"][profile]
        self.policy = bridge.model_policies[profile]
        self.monotonic, self.sleep = monotonic, sleep

    def count(self, body):
        _require(len(_json(body).encode("utf-8")) <= self.row["max_request_bytes"], "Sail full input exceeds reviewed byte ceiling")
        return self.row["billable_input_ceiling"]

    def _wire(self, body):
        window = self.row["completion_window"]
        wire = {"model": self.policy.model, "input": body["input"], "tools": body["tools"],
                "tool_choice": body["tool_choice"], "reasoning": {"effort": body["reasoning_effort"]},
                "max_output_tokens": body["max_output_tokens"], "background": window == "balanced", "stream": False,
                "truncation": "disabled", "metadata": {"completion_window": window}}
        if body["cache_key"] is not None:
            wire["prompt_cache_key"] = body["cache_key"]
        return wire

    def _original(self, body, *, sending):
        b = self.bridge; key = body["request_key"]
        store = b.store()
        try:
            state = b.state(store); slot = state["requests"].get(key)
            _require(slot is not None and slot["kind"] == "model" and slot["fingerprint"] == _digest(body)
                     and slot["result"] is None and (not sending or not state["closed"]),
                     "model lacks the immutable original broker request")
            # Passive recovery uses the original journal and hold even after expiry/withdrawal.
            tariff, inventory = b.billing() if sending else (b.config.tariff, b.config.inventory)
            budget = DailyBudget(store, tariff, inventory)
            if sending:
                _require(budget.summary()["within_cap"], "model lacks shared admitted budget")
            daily_key = "model-"+hashlib.sha256((b.policy.scope+":"+key).encode()).hexdigest()
            held = budget._load()["inference"].get(daily_key)
            _require(held is not None and held["dispatch_at"] is not None and not held["canceled"]
                     and (not sending or held["receipt"] is None), "model lacks original dispatched reservation")
        finally:
            store.close()
        wire = self._wire(body)
        intent = {"body_sha256": _digest(body), "profile": self.profile,
                  "completion_window": self.row["completion_window"], "wire_sha256": _digest(wire)}
        return key, wire, intent

    def _observe(self, key, reply, body, *, response_id=None):
        b = self.bridge
        if isinstance(reply, dict):
            b.journal("observation", "model:"+key+":"+_digest(reply), reply)
            if response_id is None and self.row["completion_window"] == "asap":
                # Preserve the legacy one-shot raw reply, including refusals.
                # Balanced pending observations use separate immutable receipts
                # so they never occupy the eventual terminal-result slot.
                b.journal("result", "model:"+key, reply)
        seen = reply.get("id") if isinstance(reply, dict) else None
        _require(isinstance(seen, str) and _RESPONSE.fullmatch(seen), "Sail response has no original accepted handle; keep hold")
        if response_id is None:
            # Acceptance precedes model/status validation: even an invalid answer can owe money.
            b.journal("accepted", "model:"+key, {"response_id": seen, "model": reply.get("model"),
                "status": reply.get("status"), "body_sha256": _digest(body), "profile": self.profile,
                "completion_window": self.row["completion_window"], "wire_sha256": _digest(self._wire(body)),
                "observation_sha256": _digest(reply)})
        _require(response_id is None or seen == response_id, "Sail accepted response handle changed; keep original hold")
        _require(reply.get("model") == self.policy.model and reply.get("status") in
                 ("queued", "in_progress", "completed", "incomplete", "failed", "cancelled"),
                 "Sail response model/status is mismatched; keep original hold")
        return seen

    def _finish(self, key, body, reply):
        self.bridge.journal("result", "model:"+key, reply)
        bill = self.bridge.terminal_bill(key, reply["id"], self.policy.model, _digest(body))
        if bill is None:
            return ModelReply(reply)
        return ModelReply(reply, bill["actual_usd"], bill["accrued_day"], bill["provenance"])

    def _poll(self, key, body, response_id, deadline):
        # Local patience is not cancellation, an invoice or permission to release the hold.
        # A final in-flight GET may take its already bounded transport timeout.
        for _ in range(math.ceil(self.policy.timeout_seconds / 2) + 1):
            _require(_time(self.monotonic()) < deadline, "Sail accepted response remains pending; original hold retained")
            reply = self.transport("GET", "/v1/responses/"+response_id)
            self._observe(key, reply, body, response_id=response_id)
            if reply["status"] not in ("queued", "in_progress"):
                return self._finish(key, body, reply)
            remaining = deadline - _time(self.monotonic())
            _require(remaining > 0, "Sail accepted response remains pending; original hold retained")
            self.sleep(min(2, remaining))
        raise ResearchCapabilityError("Sail accepted response remains pending; original hold retained")

    def send(self, body):
        b = self.bridge; b.fresh(); self.count(body)
        _require(body["model"] == self.policy.model and body["max_output_tokens"] <= self.policy.max_output_tokens,
                 "Sail model or output ceiling changed")
        now = _time(b.clock())
        _require(self.policy.valid_from <= now and now+self.policy.timeout_seconds < self.policy.valid_until,
                 "Sail accepted-request price evidence is expired")
        key, wire, intent = self._original(body, sending=True)
        b.intent("model:"+key, intent)
        deadline = _time(self.monotonic()) + self.policy.timeout_seconds
        reply = self.transport("POST", "/v1/responses", wire,
                 idempotency_key="ltcm-isolated-"+hashlib.sha256((b.policy.scope+":"+key).encode()).hexdigest())
        response_id = self._observe(key, reply, body)
        if reply["status"] not in ("queued", "in_progress"):
            return self._finish(key, body, reply)
        _require(self.row["completion_window"] == "balanced", "foreground ASAP response is nonterminal; keep original hold")
        return self._poll(key, body, response_id, deadline)

    def recover(self, body):
        _require(self.row["completion_window"] == "balanced", "only reviewed balanced original handles are recoverable")
        key, wire, intent = self._original(body, sending=False)
        _require(self.bridge.journal("intent", "model:"+key) == intent, "original model profile/window/wire changed")
        accepted = self.bridge.journal("accepted", "model:"+key)
        _require(isinstance(accepted, dict) and set(accepted) == {"response_id", "model", "status", "observation_sha256", *intent}
                 and all(accepted[field] == value for field,value in intent.items())
                 and isinstance(accepted["response_id"], str) and _RESPONSE.fullmatch(accepted["response_id"])
                 and accepted["model"] == self.policy.model and accepted["status"] in
                 ("queued", "in_progress", "completed", "incomplete", "failed", "cancelled"),
                 "original accepted response handle is absent or mismatched; no redispatch")
        observed = self.bridge.journal("observation", "model:"+key+":"+str(accepted["observation_sha256"]))
        _require(isinstance(accepted["observation_sha256"], str) and _SHA.fullmatch(accepted["observation_sha256"])
                 and isinstance(observed, dict) and _digest(observed) == accepted["observation_sha256"]
                 and all(observed.get(field) == accepted[field if field != "id" else "response_id"]
                         for field in ("id", "model", "status")),
                 "accepted handle differs from its original durable native observation")
        reply = self.bridge.journal("result", "model:"+key)
        if reply is not None:
            self._observe(key, reply, body, response_id=accepted["response_id"])
            return self._finish(key, body, reply)
        return self._poll(key, body, accepted["response_id"], _time(self.monotonic())+self.policy.timeout_seconds)


def build_sail_host_adapters(config: HostConfig, *, inputs: SailBridgeInputs, key_source: Callable[[], str],
                             box_transport=None, inference_transport=None, clock=time.time, cleanup_only=False,
                             poll_monotonic=time.monotonic, poll_sleep=time.sleep) -> HostAdapters:
    """Called only by an explicitly reviewed private operator factory, never at import.

    Supplied transports support offline fixtures. Production defaults are the existing
    allowlisted HTTPS transports, with explicit key source and no automatic retries.
    All external facts are checked before constructing a credentialed client.
    """
    _require(callable(key_source), "explicit host-only Sail credential source required")
    bridge = _Bridge(config, inputs, clock, cleanup_only)
    if box_transport is None:
        box_transport = BoxTransport(key_source=key_source)
    provider = SailResearchProvider(bridge, SailboxClient(transport=box_transport))
    models = {}
    for name, policy in bridge.model_policies.items():
        transport = inference_transport
        if transport is None:
            from ltcm.provider import Transport, _NoRedirect
            class BoundedOpener:
                def __init__(self, maximum):
                    self.maximum = maximum
                    self.opener = build_opener(_NoRedirect)
                def open(self, request, *, timeout):
                    return self.opener.open(request, timeout=min(timeout, self.maximum))
            transport = Transport(key_source=key_source, opener=BoundedOpener(policy.timeout_seconds))
        adapter = _SailModel(bridge, name, transport, monotonic=poll_monotonic, sleep=poll_sleep)
        models[name] = ModelCapability(policy, adapter.count, adapter.send,
                                       adapter.recover if adapter.row["completion_window"] == "balanced" else None)
    def driver_factory(p, resource_id):
        _require(p is provider, "Gym provider capability changed")
        bridge.resource(resource_id)
        c = bridge.checkpoint
        driver = _ExactGymDriver(provider, resource_id, retries=1, cleanup=False, repo=config.artifact_root,
                                 remote_root=c["remote_root"], store_root=c["store_root"], python=c["python"])
        _require((driver._bundle, driver.version) == build_bundle(config.artifact_root), "Gym actual bundle differs")
        return driver
    return HostAdapters(provider, driver_factory, models, bridge.context, bridge.billing)
