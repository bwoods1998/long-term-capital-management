"""Offline daily obligations that do not rely on a maximum provider stop delay.

Every unresolved creation and every resource without completed native pause evidence
reserves its full 24-hour ceiling on each UTC day. A paused resource retains its
unsettled accrued capacity bound; only an exact native GET and a reviewed exclusive
resume-writer fence can remove future running time. Finite fence expiry is reserved
before it happens. Uncertain fees and inference requests keep their original holds.
Runtime estimates, sleep, elapsed TTLs and lost replies never prove a completed pause.

This module performs no provider operations and has no production pricing defaults.
Evidence objects are explicit trusted inputs, not verification of a provider contract.
A resource tariff must cover the whole requested UTC day. A ledger with no resource
history needs no compute price interval; inference keeps its independently admitted
charge ceiling. Future-day resource prices remain conditional until evidence exists.
All resource/model dispatchers must share this gate and
the same durable store; a copied database or an outside writer invalidates the scope.
Existing unpriced resources are refused; migration needs separate authoritative cost
evidence. Vendor costs, reporting estimates, and these upper bounds stay distinct.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
import sqlite3
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR
from fractions import Fraction
from typing import Any
from urllib.parse import quote

NANOS = 1_000_000_000
DAY_SECONDS = 86400
MAX_DAILY_NANOS = 25 * NANOS
EVENT_KIND = "swarm.daily_budget"
STATE_KEY = "daily_budget_obligations_v1"


class DailyAdmissionError(RuntimeError):
    pass


def _identity(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()


def _time(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DailyAdmissionError("invalid daily budget clock")
    try:
        if value < 0 or not math.isfinite(value):
            raise ValueError
        dt.datetime.fromtimestamp(value, dt.timezone.utc)
    except (ValueError, OverflowError, OSError) as exc:
        raise DailyAdmissionError("invalid daily budget clock") from exc
    return float(value)


def _decimal(value: Any) -> Decimal:
    # Binary floats, booleans, and implicit price estimates are not trusted money.
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise DailyAdmissionError("money and capacities need exact decimal values")
    try:
        number = Decimal(value)
        if not number.is_finite() or number < 0 or number > Decimal("1e18"):
            raise InvalidOperation
        # Keep all later multiplication/sums exact under Decimal's standard context.
        if len(number.as_tuple().digits) > 20 or number.as_tuple().exponent < -12:
            raise InvalidOperation
        return number
    except (InvalidOperation, ValueError) as exc:
        raise DailyAdmissionError("invalid nonnegative decimal value") from exc


def _nanos(value: Any) -> int:
    return int((_decimal(value) * NANOS).to_integral_value(rounding=ROUND_CEILING))


def _usd(nanos: int) -> str:
    return format(Decimal(nanos) / NANOS, "f")


def _provenance(value: Any) -> None:
    if not _identity(value):
        raise DailyAdmissionError("documented trusted provenance is required")


def _day(value: Any) -> int:
    try:
        date = dt.date.fromisoformat(value)
        if date.isoformat() != value:
            raise ValueError
        return (date - dt.date(1970, 1, 1)).days
    except (TypeError, ValueError) as exc:
        raise DailyAdmissionError("cost evidence needs an exact UTC accrual day") from exc


@dataclass(frozen=True)
class DayCostEvidence:
    """Complete pre-gate current-day settled cost upper bound; zero also needs evidence."""

    scope: str
    utc_day: str
    upper_usd: str
    provenance: str

    def __post_init__(self):
        if not _identity(self.scope) or _day(self.utc_day) < 0:
            raise DailyAdmissionError("invalid prior-cost scope or day")
        object.__setattr__(self, "upper_usd", format(_decimal(self.upper_usd), "f"))
        _provenance(self.provenance)


@dataclass(frozen=True)
class TariffEvidence:
    """Maximum rates for an explicitly certified time interval and billing scope."""

    scope: str
    vcpu_usd_hour: str
    memory_gib_usd_hour: str
    disk_gib_usd_hour: str
    volume_gib_usd_hour: str
    valid_from: float
    valid_until: float
    provenance: str

    def __post_init__(self):
        if not _identity(self.scope):
            raise DailyAdmissionError("tariff scope is required")
        for name in ("vcpu_usd_hour", "memory_gib_usd_hour", "disk_gib_usd_hour", "volume_gib_usd_hour"):
            object.__setattr__(self, name, format(_decimal(getattr(self, name)), "f"))
        if _time(self.valid_from) >= _time(self.valid_until):
            raise DailyAdmissionError("invalid tariff validity interval")
        _provenance(self.provenance)

    def covers_day(self, day: int) -> bool:
        return self.valid_from <= day * DAY_SECONDS and (day + 1) * DAY_SECONDS <= self.valid_until


@dataclass(frozen=True)
class ObservedTariffEvidence(TariffEvidence):
    """Fresh ordinary-service rates for a local admission projection, not maxima.

    The tagged journal retains this distinction across restart. Original schema1
    tariff documents remain unchanged. Old readers refuse the additional fields.
    A freshness deadline is never a future price lock or completed cancellation.
    """

    mode: str
    basis_sha256: str
    future_rate_lock: bool
    fixed_day_fee_usd: str
    prior_utc_day: str
    prior_upper_usd: str
    pending: tuple[tuple[str, str], ...]

    def __post_init__(self):
        super().__post_init__()
        if (self.mode != "observed_self_service" or self.future_rate_lock is not False
                or not isinstance(self.basis_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", self.basis_sha256) is None
                or self.valid_until > self.valid_from + 300):
            raise DailyAdmissionError("explicit fresh observed price basis without a rate lock required")
        _day(self.prior_utc_day)
        for name in ("fixed_day_fee_usd", "prior_upper_usd"):
            object.__setattr__(self, name, format(_decimal(getattr(self, name)), "f"))
        if (not isinstance(self.pending, tuple) or any(not isinstance(row, tuple) or len(row) != 2
                or not _identity(row[0]) for row in self.pending)
                or len({row[0] for row in self.pending}) != len(self.pending)):
            raise DailyAdmissionError("original bounded pending identities required")
        for _, upper in self.pending:
            _decimal(upper)

    def covers_day(self, day):
        return False  # Observed rates never certify a whole future UTC interval.


def tariff_from_document(value):
    """Read both original certified tariffs and explicitly tagged schema2 facts."""
    if isinstance(value, dict) and value.get("mode") == "observed_self_service":
        value = {**value, "pending": tuple(tuple(row) for row in value["pending"])}
        return ObservedTariffEvidence(**value)
    return TariffEvidence(**value)


def _admission_prices(tariff, at):
    if isinstance(tariff, ObservedTariffEvidence):
        return tariff.valid_from <= at <= tariff.valid_until
    return tariff.covers_day(int(at // DAY_SECONDS))


@dataclass(frozen=True)
class ResourceBound:
    """Hard resource ceilings, with separately persistent volumes represented as kind=volume."""

    spec_id: str
    kind: str
    vcpu: int
    memory_gib: str
    disk_gib: str
    volume_gib: str
    creation_fee_usd: str
    provenance: str

    def __post_init__(self):
        if not _identity(self.spec_id) or self.kind not in ("controller", "gym", "gate", "image", "volume"):
            raise DailyAdmissionError("resource identity and supported kind are required")
        if isinstance(self.vcpu, bool) or not isinstance(self.vcpu, int) or not 0 <= self.vcpu <= 65536:
            raise DailyAdmissionError("invalid vCPU ceiling")
        dimensions = [_decimal(getattr(self, field)) for field in ("memory_gib", "disk_gib", "volume_gib")]
        for field in ("memory_gib", "disk_gib", "volume_gib", "creation_fee_usd"):
            object.__setattr__(self, field, format(_decimal(getattr(self, field)), "f"))
        if self.vcpu + sum(dimensions) <= 0:
            raise DailyAdmissionError("empty resource ceiling")
        if self.kind == "volume":
            if self.vcpu or dimensions[0] or dimensions[1] or not dimensions[2]:
                raise DailyAdmissionError("volumes have only a persistent storage ceiling")
        elif dimensions[2]:
            raise DailyAdmissionError("persistent volumes need their own reservation")
        _provenance(self.provenance)

    def daily_nanos(self, tariff: TariffEvidence) -> int:
        # Round each dimension upward before summing; never round down near $25.
        return sum(_nanos(Decimal(24) * _decimal(capacity) * _decimal(rate)) for capacity, rate in (
            (self.vcpu, tariff.vcpu_usd_hour), (self.memory_gib, tariff.memory_gib_usd_hour),
            (self.disk_gib, tariff.disk_gib_usd_hour), (self.volume_gib, tariff.volume_gib_usd_hour)))


@dataclass(frozen=True)
class InventoryEvidence:
    """Complete inventory, pending obligations, and exclusive dispatch scope, verified by the caller.

    resource_ids includes volumes. model_keys includes unresolved provider requests.
    A partial provider list or an unpriced legacy bill must set the relevant flag false
    or unknown_obligations true. Names and absent rows are not proof of deletion.
    """

    scope: str
    resource_ids: tuple[str, ...]
    model_keys: tuple[str, ...]
    complete: bool
    exclusive_writer: bool
    unknown_obligations: bool
    observed_at: float
    valid_until: float
    provenance: str

    def __post_init__(self):
        if not _identity(self.scope):
            raise DailyAdmissionError("inventory scope is required")
        for name in ("resource_ids", "model_keys"):
            values = getattr(self, name)
            if not isinstance(values, tuple) or any(not _identity(v) for v in values) or len(set(values)) != len(values):
                raise DailyAdmissionError("inventory identities must be unique tuples")
        if any(not isinstance(getattr(self, name), bool) for name in ("complete", "exclusive_writer", "unknown_obligations")):
            raise DailyAdmissionError("inventory evidence flags must be boolean")
        if _time(self.observed_at) > _time(self.valid_until):
            raise DailyAdmissionError("invalid inventory evidence interval")
        _provenance(self.provenance)


@dataclass(frozen=True)
class NativePausedEvidence:
    """Trusted collector's exact native resource GET, not a pause POST acceptance.

    The caller must retain and review the authentic transport capture. Hash/route
    binding detects different bytes; it does not authenticate a fabricated capture.
    This object performs no network operation and gives no new paid allowance.
    """

    scope: str
    resource_id: str
    method: str
    url: str
    started_at: float
    received_at: float
    http_status: int
    document_json: str
    document_sha256: str
    provenance: str

    def __post_init__(self):
        if not _identity(self.scope) or not _identity(self.resource_id):
            raise DailyAdmissionError("native paused GET needs original scope and resource")
        expected = "https://sailbox-api.sailresearch.com/v1/sailboxes/" + quote(self.resource_id, safe="")
        if (self.method != "GET" or self.url != expected or isinstance(self.http_status, bool)
                or self.http_status != 200 or _time(self.started_at) > _time(self.received_at)):
            raise DailyAdmissionError("completed pause needs an exact successful native resource GET")
        if (not isinstance(self.document_json, str) or len(self.document_json.encode("utf-8")) > 1024 * 1024
                or not isinstance(self.document_sha256, str)
                or hashlib.sha256(self.document_json.encode("utf-8")).hexdigest() != self.document_sha256):
            raise DailyAdmissionError("native paused GET bytes differ from retained capture")
        document = _json(self.document_json)
        if (not isinstance(document, dict) or document.get("sailbox_id") != self.resource_id
                or document.get("status") != "paused"):
            raise DailyAdmissionError("native GET does not prove the original resource is paused")
        _native_dimensions(document)
        if not isinstance(document.get("volume_mounts"), list):
            raise DailyAdmissionError("native paused GET omits mounted storage inventory")
        _provenance(self.provenance)


@dataclass(frozen=True)
class ResumeFenceEvidence:
    """Reviewed enforcement across every explicit-resume writer and pending request.

    A local JSON declaration is insufficient production evidence. The caller must
    review actual writer privileges/controls and drain old resume requests. A finite
    review interval never promises that the native pause cannot be resumed forever.
    """

    scope: str
    resource_id: str
    fence_id: str
    writer_ids: tuple[str, ...]
    complete: bool
    exclusive_writer: bool
    pending_resume_requests: tuple[str, ...]
    effective_at: float
    valid_until: float
    enforcement_sha256: str
    provenance: str

    def __post_init__(self):
        if any(not _identity(v) for v in (self.scope, self.resource_id, self.fence_id)):
            raise DailyAdmissionError("resume fence needs original scope, resource and enforcement identity")
        for name in ("writer_ids", "pending_resume_requests"):
            values = getattr(self, name)
            if (not isinstance(values, tuple) or any(not _identity(v) for v in values)
                    or len(set(values)) != len(values)):
                raise DailyAdmissionError("resume fence writer/request identities must be unique tuples")
        if (not self.writer_ids or self.complete is not True or self.exclusive_writer is not True
                or self.pending_resume_requests or _time(self.effective_at) >= _time(self.valid_until)
                or not isinstance(self.enforcement_sha256, str)
                or re.fullmatch(r"[0-9a-f]{64}", self.enforcement_sha256) is None):
            raise DailyAdmissionError("resume writers or in-flight requests are not demonstrably fenced")
        _provenance(self.provenance)


@dataclass(frozen=True)
class NativeUsageSettlementEvidence:
    """Reviewed completed-usage allocation, not a provider API response schema.

    The host must retain the authentic completed source document and verify this
    complete resource/interval allocation against it. Hashes bind those reviewed
    bytes; a local projection or sampled spend does not authenticate finality.
    A native finalized-spend statement may support completed compute when its
    original resource and interval are fully reconciled; it is not an all-in tax
    invoice. Creation fees, volumes and other resources stay outside this line.
    """

    document_json: str
    document_sha256: str
    source_document: str
    provenance: str

    def __post_init__(self):
        if (not isinstance(self.document_json, str) or len(self.document_json.encode("utf-8")) > 1024 * 1024
                or hashlib.sha256(self.document_json.encode("utf-8")).hexdigest() != self.document_sha256):
            raise DailyAdmissionError("final native allocation differs from retained reviewed bytes")
        value = _json(self.document_json)
        _fields(value, "schema kind scope resource_id invoice_id source_document_sha256 interval_start interval_end "
                "final complete includes_creation_fees includes_volume_storage charges")
        if (type(value["schema"]) is not int or value["schema"] != 1
                or value["kind"] != "native_compute_usage_final_allocation"
                or any(not _identity(value[name]) for name in ("scope", "resource_id", "invoice_id"))
                or not isinstance(value["source_document_sha256"], str)
                or re.fullmatch(r"[0-9a-f]{64}", value["source_document_sha256"]) is None
                or value["final"] is not True or value["complete"] is not True
                or value["includes_creation_fees"] is not False or value["includes_volume_storage"] is not False
                or _time(value["interval_start"]) >= _time(value["interval_end"])):
            raise DailyAdmissionError("complete final original-resource compute allocation is required")
        if (not isinstance(self.source_document, str) or not self.source_document
                or len(self.source_document.encode("utf-8")) > 1024 * 1024
                or hashlib.sha256(self.source_document.encode("utf-8")).hexdigest() != value["source_document_sha256"]):
            raise DailyAdmissionError("native allocation differs from retained authentic source-document bytes")
        charges = value["charges"]
        if not isinstance(charges, list) or not charges or len(charges) > 36600:
            raise DailyAdmissionError("final native allocation needs explicit accrued UTC-day costs")
        days = set()
        for charge in charges:
            _fields(charge, "utc_day actual_usd")
            day = _day(charge["utc_day"])
            if (day in days or not isinstance(charge["actual_usd"], str)
                    or (day + 1) * DAY_SECONDS <= value["interval_start"]
                    or day * DAY_SECONDS >= value["interval_end"]):
                raise DailyAdmissionError("native allocation has duplicated or out-of-interval accrual days")
            _nanos(charge["actual_usd"])
            days.add(day)
        first = int(value["interval_start"] // DAY_SECONDS)
        last = (Fraction(str(value["interval_end"])) / DAY_SECONDS).__ceil__()
        if last - first > 36600 or days != set(range(first, last)):
            raise DailyAdmissionError("final native allocation omits an accrued UTC day, including explicit zero days")
        _provenance(self.provenance)


def _native_usage_prefix(state, key, evidence, tariff):
    """Bind final complete prefix and compute its still-unsettled original upper."""
    row = state["resources"].get(key)
    value = _json(evidence.document_json)
    pause = row.get("native_pause") if row else None
    if (pause is None or value["scope"] != state["scope"] or value["resource_id"] != row["resource_id"]
            or tariff.scope != state["scope"]):
        raise DailyAdmissionError("final native usage escaped the original admitted resource and scope")
    settled = row.get("native_usage")
    start = settled["settled_through"] if settled else row["dispatch_at"]
    end = row["terminal_at"] if row["terminal_at"] is not None else pause["observation"]["received_at"]
    if value["interval_start"] != start or value["interval_end"] != end:
        raise DailyAdmissionError("final native usage must cover exactly the next complete closed prefix")
    if settled and any(item["invoice_id"] == value["invoice_id"] for item in settled["settlements"]):
        raise DailyAdmissionError("final native invoice identity was already consumed for this resource")
    upper = pause["retained_usage_nanos"]
    if row["terminal_at"] is not None:
        resume = pause["resume"]
        possible_start = resume["at"] if resume else pause["fence"]["valid_until"]
        if end > possible_start:
            if not tariff.valid_from <= possible_start < end <= tariff.valid_until:
                raise DailyAdmissionError("terminal native usage has an unpriced original interval")
            earlier = TariffEvidence(**(resume["tariff"] if resume else pause["tariff"]))
            upper += _interval_nanos(ResourceBound(**row["bound"]), _higher_rates(tariff, earlier), possible_start, end)
    retired = settled["retired_upper_nanos"] if settled else 0
    if upper < retired:
        raise DailyAdmissionError("native usage settlement lost its original retained prefix")
    actual = sum(_nanos(charge["actual_usd"]) for charge in value["charges"])
    return row, value, upper, upper - retired, actual


def _native_dimensions(document):
    values = [document.get(name) for name in ("vcpu_count", "memory_mib", "state_disk_size_gib")]
    if any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in values):
        raise DailyAdmissionError("native paused GET has unknown resource ceilings")
    return values[0], Decimal(values[1]) / 1024, Decimal(values[2])


def _interval_nanos(bound, tariff, start, end):
    """Capacity upper bound, not sampled usage or an exact provider shutdown promise."""
    seconds = max(Fraction(0), Fraction(str(_time(end))) - Fraction(str(_time(start))))
    total = 0
    for capacity, rate in ((bound.vcpu, tariff.vcpu_usd_hour), (bound.memory_gib, tariff.memory_gib_usd_hour),
                           (bound.disk_gib, tariff.disk_gib_usd_hour)):
        exact = seconds * Fraction(_decimal(capacity)) * Fraction(_decimal(rate)) * NANOS / 3600
        total += (exact.numerator + exact.denominator - 1) // exact.denominator
    return total


def _higher_rates(tariff, earlier):
    # Do not let a later cheaper observation erase an unresolved earlier bill.
    return tariff_from_document({**asdict(tariff), **{
        name: format(max(_decimal(getattr(tariff, name)), _decimal(getattr(earlier, name))), "f")
        for name in ("vcpu_usd_hour", "memory_gib_usd_hour", "disk_gib_usd_hour", "volume_gib_usd_hour")}})


def _pause_fence(value):
    if not isinstance(value, dict):
        raise DailyAdmissionError("unreadable original resume fence")
    if any(not isinstance(value.get(name), (list, tuple)) for name in ("writer_ids", "pending_resume_requests")):
        raise DailyAdmissionError("unreadable original resume writer/request inventory")
    # Immutable JSON history represents tuple identities as arrays.
    value = {**value, "writer_ids": tuple(value.get("writer_ids", ())),
             "pending_resume_requests": tuple(value.get("pending_resume_requests", ()))}
    return ResumeFenceEvidence(**value)


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise DailyAdmissionError("duplicate durable obligation field")
        result[key] = value
    return result


def _json(raw: str):
    try:
        return json.loads(raw, object_pairs_hook=_pairs, parse_constant=lambda _: (_ for _ in ()).throw(
            DailyAdmissionError("nonfinite durable obligation field")))
    except (ValueError, TypeError) as exc:
        raise DailyAdmissionError("unreadable durable daily obligations") from exc


def _same(a, b):
    try:
        return json.dumps(a, sort_keys=True, allow_nan=False) == json.dumps(b, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError, OverflowError) as exc:
        raise DailyAdmissionError("unreadable durable daily obligations") from exc


def _fields(row, names):
    if not isinstance(row, dict) or set(row) != set(names.split()):
        raise DailyAdmissionError("invalid immutable daily budget receipt")


def _retain_observed_facts(state, tariff):
    resources,inference=state["resources"],state["inference"]
    held = state.setdefault("observed_pending_upper", {})
    for identity, upper in tariff.pending:
        row = resources.get(identity, inference.get(identity))
        if row is None or row["dispatch_at"] is None or row["canceled"]:
            raise DailyAdmissionError("observed epoch has no original dispatched obligation")
        held[identity] = max(held.get(identity, 0), _nanos(upper))
    rates = state.setdefault("observed_rate_max", {})
    for name in ("vcpu_usd_hour", "memory_gib_usd_hour", "disk_gib_usd_hour", "volume_gib_usd_hour"):
        rates[name] = format(max(_decimal(rates.get(name, "0")), _decimal(getattr(tariff, name))), "f")
    days = state.setdefault("observed_day_facts", {})
    original = days.setdefault(tariff.prior_utc_day, {"prior_nanos": 0, "fee_nanos": 0})
    original["prior_nanos"] = max(original["prior_nanos"], _nanos(tariff.prior_upper_usd))
    original["fee_nanos"] = max(original["fee_nanos"], _nanos(tariff.fixed_day_fee_usd))


def _apply(state, receipt):
    """Validate the immutable history through the same transitions used for writes."""
    if not isinstance(receipt, dict):
        raise DailyAdmissionError("invalid immutable daily budget receipt")
    action, at = receipt.get("action"), _time(receipt.get("at"))
    if state is None:
        _fields(receipt, "action at scope cap_nanos baseline")
        if action != "opened" or not _identity(receipt["scope"]):
            raise DailyAdmissionError("daily budget has no original scope admission")
        cap = receipt["cap_nanos"]
        if isinstance(cap, bool) or not isinstance(cap, int) or not 0 < cap <= MAX_DAILY_NANOS:
            raise DailyAdmissionError("invalid original daily budget ceiling")
        baseline = DayCostEvidence(**receipt["baseline"])
        if baseline.scope != receipt["scope"] or _day(baseline.utc_day) != int(at // DAY_SECONDS):
            raise DailyAdmissionError("prior-cost evidence does not cover initialization day and scope")
        return {"scope": receipt["scope"], "cap_nanos": cap, "last_at": at, "resources": {}, "inference": {},
                "baseline": asdict(baseline), "breached": False}
    if at < state["last_at"]:
        raise DailyAdmissionError("daily budget receipt clock rolled back")
    key = receipt.get("key")
    if not _identity(key):
        raise DailyAdmissionError("daily obligation identity is required")
    resources, inference = state["resources"], state["inference"]
    if action in ("resource_reserved", "inference_reserved"):
        if key in resources or key in inference or any(
                key in r.get("native_pause", {}).get("resumes", {}) for r in resources.values()):
            raise DailyAdmissionError("daily obligation identity was already used")
        if action == "resource_reserved":
            _fields(receipt, "action at key bound tariff")
            bound, tariff = ResourceBound(**receipt["bound"]), tariff_from_document(receipt["tariff"])
            if tariff.scope != state["scope"] or not _admission_prices(tariff, at):
                raise DailyAdmissionError("original reservation has no day tariff evidence")
            resources[key] = {"at": at, "bound": asdict(bound), "tariff": asdict(tariff), "dispatch_at": None,
                              "resource_id": None, "created_at": None, "terminal_at": None, "canceled": False}
        else:
            _fields(receipt, "action at key max_nanos provenance")
            cap = receipt["max_nanos"]
            if isinstance(cap, bool) or not isinstance(cap, int) or not 0 < cap <= MAX_DAILY_NANOS:
                raise DailyAdmissionError("invalid original inference ceiling")
            _provenance(receipt["provenance"])
            inference[key] = {"at": at, "max_nanos": cap, "provenance": receipt["provenance"],
                              "dispatch_at": None, "receipt": None, "canceled": False}
    elif action == "observed_basis":
        _fields(receipt, "action at key tariff")
        tariff = tariff_from_document(receipt["tariff"])
        if (not isinstance(tariff, ObservedTariffEvidence) or tariff.scope != state["scope"]
                or key != tariff.basis_sha256 or not _admission_prices(tariff, at)):
            raise DailyAdmissionError("invalid original-scope observed tariff epoch")
        previous = state.get("observed_basis")
        if previous and tariff.valid_from < previous["valid_from"]:
            raise DailyAdmissionError("observed tariff epoch rolled back")
        state["observed_basis"] = asdict(tariff)
        _retain_observed_facts(state, tariff)
    elif action == "observed_facts_retained":
        _fields(receipt, "action at key observation")
        observation=receipt["observation"]
        tariff=tariff_from_document(observation["tariff"])
        if (not isinstance(tariff,ObservedTariffEvidence) or tariff.scope!=state["scope"]
                or not _admission_prices(tariff,_time(observation["observed_at"]))):
            raise DailyAdmissionError("invalid retained original-scope observed facts")
        from .observed_cost_journal import encode,digest
        if digest(encode(observation))!=key:
            raise DailyAdmissionError("retained observed fact hash differs")
        refs=state.setdefault("observed_external_refs",[])
        if key in refs:raise DailyAdmissionError("observed fact was already journaled")
        refs.append(key);refs.sort()
        previous=state.get("observed_basis")
        if not previous or tariff.valid_from>=previous["valid_from"]:
            state["observed_basis"]=asdict(tariff)
        _retain_observed_facts(state,tariff)
    elif action in ("dispatched", "canceled_unsent"):
        _fields(receipt, "action at key")
        row = resources.get(key, inference.get(key))
        if row is None or row["canceled"] or row["dispatch_at"] is not None:
            raise DailyAdmissionError("daily obligation has no unused dispatch slot")
        if action == "dispatched":
            row["dispatch_at"] = at
        else:
            row["canceled"] = True
    elif action == "resource_attached":
        _fields(receipt, "action at key resource_id created_at observed_bound provenance")
        row = resources.get(key)
        resource_id, created = receipt["resource_id"], _time(receipt["created_at"])
        if (row is None or row["canceled"] or row["dispatch_at"] is None or row["resource_id"] is not None
                or not _identity(resource_id) or any(r["resource_id"] == resource_id for r in resources.values())
                or created < row["dispatch_at"] or created > at):
            raise DailyAdmissionError("resource binding has no unique admitted dispatch")
        observed, bound = ResourceBound(**receipt["observed_bound"]), ResourceBound(**row["bound"])
        if observed.spec_id != bound.spec_id or observed.kind != bound.kind or any(
                _decimal(getattr(observed, field)) > _decimal(getattr(bound, field))
                for field in ("vcpu", "memory_gib", "disk_gib", "volume_gib", "creation_fee_usd")):
            raise DailyAdmissionError("observed resource exceeds its admitted ceilings")
        _provenance(receipt["provenance"])
        row.update(resource_id=resource_id, created_at=created)
    elif action == "terminal_observed":
        _fields(receipt, "action at key resource_id observed_at status provenance")
        row = resources.get(key)
        observed = _time(receipt["observed_at"])
        if (row is None or row["resource_id"] != receipt["resource_id"] or row["resource_id"] is None
                or row["terminal_at"] is not None or observed < row["created_at"] or observed > at):
            raise DailyAdmissionError("terminal evidence has no admitted resource")
        expected = "deleted" if row["bound"]["kind"] == "volume" else "terminated"
        if receipt["status"] != expected:
            raise DailyAdmissionError("sleep, expiry, and transitional states do not terminate obligations")
        _provenance(receipt["provenance"])
        row["terminal_at"] = observed
    elif action == "native_paused":
        _fields(receipt, "action at key observation fence tariff retained_usage_nanos usage_provenance")
        row = resources.get(key)
        observation, fence = NativePausedEvidence(**receipt["observation"]), _pause_fence(receipt["fence"])
        tariff, retained = TariffEvidence(**receipt["tariff"]), receipt["retained_usage_nanos"]
        if row and "mode" in row.get("tariff", {}):
            raise DailyAdmissionError("observed resource usage needs genuine interval prices before pause savings")
        if (row is None or row["canceled"] or row["dispatch_at"] is None or row["resource_id"] is None
                or row["terminal_at"] is not None or row["bound"]["kind"] == "volume"
                or observation.scope != state["scope"] or fence.scope != state["scope"]
                or observation.resource_id != row["resource_id"] or fence.resource_id != row["resource_id"]
                or not row["created_at"] <= observation.started_at <= observation.received_at <= at
                or fence.effective_at > observation.started_at or fence.valid_until <= at
                or tariff.scope != state["scope"]):
            raise DailyAdmissionError("native paused receipt or resume fence escaped the original admission")
        bound, document = ResourceBound(**row["bound"]), _json(observation.document_json)
        actual = _native_dimensions(document)
        if any(size > _decimal(getattr(bound, name)) for size, name in
               zip(actual, ("vcpu", "memory_gib", "disk_gib"))):
            raise DailyAdmissionError("native paused resource exceeds original admitted ceilings")
        volumes = {r["resource_id"] for r in resources.values()
                   if r["bound"]["kind"] == "volume" and r["resource_id"] and r["terminal_at"] is None}
        if any(not isinstance(v, dict) or v.get("volume_id") not in volumes for v in document["volume_mounts"]):
            raise DailyAdmissionError("native paused resource has unaccounted persistent storage")
        previous = row.get("native_pause")
        if previous and previous["resume"] and previous["resume"]["dispatch_at"] is None:
            raise DailyAdmissionError("cancel the original unsent resume reservation before renewing pause evidence")
        if previous and (observation.started_at < previous["observation"]["received_at"]
                         or observation.received_at <= previous["observation"]["received_at"]):
            raise DailyAdmissionError("native paused readback precedes its original completed observation")
        start = row["dispatch_at"] if previous is None else (
            previous["resume"]["at"] if previous["resume"] else previous["fence"]["valid_until"])
        if observation.received_at > start and not tariff.valid_from <= start < observation.received_at <= tariff.valid_until:
            raise DailyAdmissionError("retained paused usage has an unpriced running interval")
        earlier = TariffEvidence(**(previous["resume"]["tariff"] if previous and previous["resume"]
                                   else previous["tariff"] if previous else row["tariff"]))
        priced = _higher_rates(tariff, earlier)
        minimum = (previous["retained_usage_nanos"] if previous else 0) + _interval_nanos(
            bound, priced, start, observation.received_at)
        if isinstance(retained, bool) or not isinstance(retained, int) or retained < minimum:
            raise DailyAdmissionError("paused accounting would erase accrued or lagging usage")
        _provenance(receipt["usage_provenance"])
        row["native_pause"] = {"observation": asdict(observation), "fence": asdict(fence),
                               "tariff": asdict(tariff), "retained_usage_nanos": retained,
                               "usage_provenance": receipt["usage_provenance"], "resume": None,
                               "resumes": previous["resumes"] if previous else {}}
    elif action == "resume_reserved":
        _fields(receipt, "action at key resume_key tariff provenance")
        row, resume_key = resources.get(key), receipt["resume_key"]
        tariff = TariffEvidence(**receipt["tariff"])
        if (row is None or row["terminal_at"] is not None or not row.get("native_pause")
                or row["native_pause"]["resume"] is not None or not _identity(resume_key)
                or resume_key in resources or resume_key in inference
                or any(resume_key in r.get("native_pause", {}).get("resumes", {}) for r in resources.values())):
            raise DailyAdmissionError("resume needs an unused identity on the original paused resource")
        if tariff.scope != state["scope"] or not tariff.covers_day(int(at // DAY_SECONDS)):
            raise DailyAdmissionError("resume has no original-scope day tariff")
        _provenance(receipt["provenance"])
        resume = {"key": resume_key, "at": at, "dispatch_at": None, "canceled": False, "tariff": asdict(tariff)}
        row["native_pause"]["resume"] = resume
        row["native_pause"]["resumes"][resume_key] = dict(resume)
    elif action in ("resume_dispatched", "resume_canceled_unsent"):
        _fields(receipt, "action at key resume_key")
        row = resources.get(key)
        pause = row.get("native_pause") if row else None
        resume = pause["resume"] if pause else None
        if (resume is None or resume["key"] != receipt["resume_key"] or resume["canceled"]
                or resume["dispatch_at"] is not None):
            raise DailyAdmissionError("resume has no matching unused original dispatch slot")
        if action == "resume_dispatched":
            resume["dispatch_at"] = at
            pause["resumes"][resume["key"]] = dict(resume)
        else:
            resume["canceled"] = True
            pause["resumes"][resume["key"]] = dict(resume)
            pause["resume"] = None
    elif action == "native_usage_settled":
        _fields(receipt, "action at key evidence tariff")
        evidence = NativeUsageSettlementEvidence(**receipt["evidence"])
        row, value, upper, pending, actual = _native_usage_prefix(
            state, key, evidence, TariffEvidence(**receipt["tariff"]))
        if value["interval_end"] > at or (actual > pending and not state["breached"]):
            raise DailyAdmissionError("final native invoice exceeds or precedes its original retained liability")
        settled = row.get("native_usage")
        records = settled["settlements"] if settled else []
        row["native_usage"] = {"settled_through": value["interval_end"], "retired_upper_nanos": upper,
                               "settlements": [*records, {"invoice_id": value["invoice_id"],
                                   "source_document_sha256": value["source_document_sha256"],
                                   "interval_start": value["interval_start"], "interval_end": value["interval_end"],
                                   "document_json": evidence.document_json, "document_sha256": evidence.document_sha256,
                                   "source_document": evidence.source_document,
                                   "provenance": evidence.provenance,
                                   "charges": [{"day": _day(c["utc_day"]), "actual_nanos": _nanos(c["actual_usd"])}
                                               for c in value["charges"]]}]}
    elif action == "inference_settled":
        _fields(receipt, "action at key accrued_day actual_nanos provenance")
        row, day, actual = inference.get(key), receipt["accrued_day"], receipt["actual_nanos"]
        if (row is None or row["canceled"] or row["dispatch_at"] is None or row["receipt"] is not None
                or isinstance(day, bool) or not isinstance(day, int)
                or not int(row["dispatch_at"] // DAY_SECONDS) <= day <= int(at // DAY_SECONDS)
                or isinstance(actual, bool) or not isinstance(actual, int) or not 0 <= actual <= row["max_nanos"]):
            raise DailyAdmissionError("inference charge has no matching upper bound and terminal charge day")
        _provenance(receipt["provenance"])
        row["receipt"] = {"accrued_day": day, "actual_nanos": actual, "provenance": receipt["provenance"]}
    elif action == "scope_breached":
        _fields(receipt, "action at key reason provenance")
        if key not in resources and key not in inference:
            raise DailyAdmissionError("breach evidence has no admitted obligation")
        _provenance(receipt["reason"])
        _provenance(receipt["provenance"])
        state["breached"] = True
    else:
        raise DailyAdmissionError("unknown immutable daily budget receipt")
    state["last_at"] = at
    return state


class DailyBudget:
    """One atomic ceiling across controllers, Gym/image resources, volumes and inference.

    Call initialize only for a freshly verified empty exclusive scope. Reserve BEFORE
    any paid operation and dispatch exactly once BEFORE its POST. A failed/lost POST
    still consumes that slot. Polling may reconcile it; creating again needs a new
    separately admitted identity. Receipt methods accept authoritative caller evidence.
    """

    def __init__(self, store, tariff: TariffEvidence, inventory: InventoryEvidence, *, daily_cap_usd="25"):
        if not isinstance(tariff, TariffEvidence) or not isinstance(inventory, InventoryEvidence):
            raise DailyAdmissionError("explicit trusted tariff and inventory evidence are required")
        self.store, self.tariff, self.inventory = store, tariff, inventory
        self.cap_nanos = int((_decimal(daily_cap_usd) * NANOS).to_integral_value(rounding=ROUND_FLOOR))
        if not 0 < self.cap_nanos <= MAX_DAILY_NANOS or tariff.scope != inventory.scope:
            raise DailyAdmissionError("invalid unified daily ceiling or mismatched scope")

    def _sqlite_load(self):
        try:
            state = None
            for raw in self.store._all("SELECT payload FROM events WHERE kind=? ORDER BY seq", (EVENT_KIND,)):
                state = _apply(state, _json(raw["payload"]))
            cached = self.store._one("SELECT value FROM kv WHERE key=?", (STATE_KEY,))
            if state is None or cached is None or not _same(_json(cached["value"]), state):
                raise DailyAdmissionError("daily obligations were lost or differ from immutable history")
            if state["scope"] != self.tariff.scope or state["cap_nanos"] != self.cap_nanos:
                raise DailyAdmissionError("durable daily scope or ceiling changed")
            return state
        except (KeyError, TypeError, ValueError, OverflowError, sqlite3.Error) as exc:
            raise DailyAdmissionError("unreadable durable daily obligations") from exc

    def _observations(self, state):
        from .observed_cost_journal import records,ObservationJournalError
        first=self.store._one("SELECT payload FROM events WHERE kind=? ORDER BY seq LIMIT 1",(EVENT_KIND,))
        opened=hashlib.sha256(first["payload"].encode()).hexdigest()
        try:
            return records(self.store.root,state["scope"],opened,required=state.get("observed_external_refs",()))
        except (OSError,ObservationJournalError) as exc:
            raise DailyAdmissionError("retained observed cost journal is missing or corrupt") from exc

    @staticmethod
    def _project_observations(state, records):
        refs=set(state.get("observed_external_refs",()))
        for key,observation in sorted(records,key=lambda row:(row[1]["observed_at"],row[0])):
            if key not in refs:
                state=_apply(state,{"action":"observed_facts_retained","at":max(state["last_at"],observation["observed_at"]),
                                    "key":key,"observation":observation})
        return state

    def _load(self):
        # Always validate the original SQLite journal/cache before projecting the
        # separately durable facts. Readers perform no synchronization writes.
        state=self._sqlite_load()
        return self._project_observations(state,self._observations(state))

    def observe_prices(self):
        """Retain validated cost increases before any cap decision/outer rollback.

        SQLite may already be in a caller transaction. This append-only file
        publication is deliberately independent; it neither commits that caller
        nor initializes, settles, reserves or dispatches any original obligation.
        """
        if not isinstance(self.tariff,ObservedTariffEvidence):return
        with self.store._lock:
            state,now=self._load(),_time(self.store.clock())
            self._check(state,now)
            tariff=asdict(self.tariff)
            first=self.store._one("SELECT payload FROM events WHERE kind=? ORDER BY seq LIMIT 1",(EVENT_KIND,))
            opened=hashlib.sha256(first["payload"].encode()).hexdigest()
            from .observed_cost_journal import append,ObservationJournalError
            def needed(records):
                before=self._project_observations(self._sqlite_load(),records)
                candidate=json.loads(json.dumps(before))
                _retain_observed_facts(candidate,self.tariff)
                return not before.get("observed_basis") or any(not _same(candidate.get(name),before.get(name)) for name in
                    ("observed_pending_upper","observed_rate_max","observed_day_facts"))
            try:append(self.store.root,state["scope"],opened,now,tariff,needed=needed)
            except (OSError,ObservationJournalError) as exc:
                raise DailyAdmissionError("observed cost facts could not be durably retained") from exc

    def sync_observed_prices(self):
        """Copy retained facts into the original SQLite journal/cache atomically.

        Losing this SQLite transaction is safe: replay still sees the immutable
        file facts. This method grants no dollar room and does not refresh facts.
        """
        with self.store.atomic():
            state=self._sqlite_load();records=self._observations(state)
            refs=set(state.get("observed_external_refs",()))
            for key,observation in sorted(records,key=lambda row:(row[1]["observed_at"],row[0])):
                if key not in refs:
                    receipt={"action":"observed_facts_retained","at":max(state["last_at"],observation["observed_at"]),
                             "key":key,"observation":observation}
                    state=_apply(state,receipt)
                    self.store.event(EVENT_KIND,None,receipt);self.store.put(STATE_KEY,state)
                    refs.add(key)
            return state

    def _check(self, state, now):
        evidence = self.inventory
        if state["breached"]:
            raise DailyAdmissionError("authoritative evidence breached the daily obligation bounds")
        if (not evidence.complete or not evidence.exclusive_writer or evidence.unknown_obligations
                or not evidence.observed_at <= now <= evidence.valid_until):
            raise DailyAdmissionError("inventory is partial, stale, shared, or has unknown obligations")
        if now < state["last_at"]:
            raise DailyAdmissionError("daily admission clock rolled back")
        observed = isinstance(self.tariff, ObservedTariffEvidence)
        if state.get("observed_basis") and not observed:
            raise DailyAdmissionError("observed journal requires its compatible accounting reader")
        if observed:
            if not _admission_prices(self.tariff, now) or _day(self.tariff.prior_utc_day) != int(now // DAY_SECONDS):
                raise DailyAdmissionError("observed tariff or original current-day cost facts are stale")
            if (_day(state["baseline"]["utc_day"]) == int(now // DAY_SECONDS)
                    and _decimal(self.tariff.prior_upper_usd) < _decimal(state["baseline"]["upper_usd"])):
                raise DailyAdmissionError("observed facts would erase original prior costs")
            pending = dict(self.tariff.pending)
            original = {key for key, row in state["inference"].items()
                        if row["dispatch_at"] is not None and not row["canceled"] and row["receipt"] is None}
            original |= {key for key, row in state["resources"].items()
                         if row["dispatch_at"] is not None and not row["canceled"]
                         and (row["terminal_at"] is None or state.get("observed_pending_upper", {}).get(key, 0))}
            if original - set(pending):
                raise DailyAdmissionError("original pending exposure is absent from fresh bounded cost facts")
            if set(pending) - original:
                raise DailyAdmissionError("fresh cost facts contain an unbound pending obligation")
        covered = {r["resource_id"] for r in state["resources"].values() if r["resource_id"] is not None}
        pending_models = {key for key, row in state["inference"].items() if not row["canceled"] and row["receipt"] is None}
        if set(evidence.resource_ids) - covered or set(evidence.model_keys) - pending_models:
            raise DailyAdmissionError("inventory contains an uncovered resource or inference obligation")
        # Compute prices do not price model holds. Inspect original history rather
        # than just current inventory: even canceled or terminal resource rows
        # retain the conservative resource-tariff gate. A first resource admission
        # independently requires full-day coverage in _apply(resource_reserved).
        if state["resources"] and not observed and not self.tariff.covers_day(int(now // DAY_SECONDS)):
            raise DailyAdmissionError("tariff evidence does not cover this full UTC day")
        if any(r.get("native_pause") and r["terminal_at"] is None
               and r["native_pause"]["resume"] is None
               and now >= r["native_pause"]["fence"]["valid_until"] for r in state["resources"].values()):
            raise DailyAdmissionError("paused resume-writer fence expired; reconcile before further paid work")

    def _write(self, state, receipt):
        if state is not None:
            state=self.sync_observed_prices()
            receipt={**receipt,"at":max(receipt["at"],state["last_at"])}
        state = _apply(state, receipt)
        self.store.event(EVENT_KIND, None, receipt)
        self.store.put(STATE_KEY, state)
        return state

    def initialize(self, prior_costs: DayCostEvidence):
        if not isinstance(prior_costs, DayCostEvidence):
            raise DailyAdmissionError("complete prior current-day cost evidence is required, including for zero")
        with self.store.atomic():
            if (self.store._one("SELECT value FROM kv WHERE key=?", (STATE_KEY,)) is not None
                    or self.store._one("SELECT seq FROM events WHERE kind=?", (EVENT_KIND,)) is not None):
                raise DailyAdmissionError("daily budget scope was already initialized")
            now = _time(self.store.clock())
            receipt = {"action": "opened", "at": now, "scope": self.tariff.scope, "cap_nanos": self.cap_nanos,
                       "baseline": asdict(prior_costs)}
            state = _apply(None, receipt)
            self._check(state, now)
            if self.inventory.resource_ids or self.inventory.model_keys:
                raise DailyAdmissionError("existing obligations need authoritative migration evidence")
            if sum(self._totals(state, int(now // DAY_SECONDS))) > self.cap_nanos:
                raise DailyAdmissionError("prior current-day costs already exceed the unified ceiling")
            self._write(None, receipt)

    def _totals(self, state, day):
        baseline = state["baseline"]
        resource_nanos = fee_nanos = inference_nanos = 0
        prior_nanos = _nanos(baseline["upper_usd"]) if _day(baseline["utc_day"]) == day else 0
        if isinstance(self.tariff, ObservedTariffEvidence) and _day(self.tariff.prior_utc_day) == day:
            prior_nanos = max(prior_nanos, _nanos(self.tariff.prior_upper_usd))
            fee_nanos += _nanos(self.tariff.fixed_day_fee_usd)
        if isinstance(self.tariff, ObservedTariffEvidence):
            date = dt.date(1970, 1, 1) + dt.timedelta(days=day)
            saved = state.get("observed_day_facts", {}).get(date.isoformat(), {})
            prior_nanos = max(prior_nanos, saved.get("prior_nanos", 0))
            fee_nanos = max(fee_nanos, saved.get("fee_nanos", 0))
            historical = state.get("observed_rate_max", {})
            pricing = tariff_from_document({**asdict(self.tariff), **{
                name: format(max(_decimal(rate), _decimal(getattr(self.tariff, name))), "f")
                for name, rate in historical.items()}})
        else:
            pricing = self.tariff
        for row in state["resources"].values():
            if row["canceled"] or int(row["at"] // DAY_SECONDS) > day:
                continue
            bound = ResourceBound(**row["bound"])
            pause = row.get("native_pause")
            if pause:
                # These unresolved native usage charges carry into every possible
                # charge day; a pause is not an invoice or debt cancellation.
                settled = row.get("native_usage")
                retired = settled["retired_upper_nanos"] if settled else 0
                resource_nanos += max(0, pause["retained_usage_nanos"] - retired)
                if settled:
                    resource_nanos += sum(c["actual_nanos"] for item in settled["settlements"]
                                          for c in item["charges"] if c["day"] == day)
                terminal_settled = settled and row["terminal_at"] is not None and settled["settled_through"] == row["terminal_at"]
                resume = pause["resume"]
                if terminal_settled:
                    pass  # Actual complete final usage is booked only to its genuine UTC accrual days.
                elif resume:
                    priced = _higher_rates(pricing, tariff_from_document(resume["tariff"]))
                    if row["terminal_at"] is None:
                        # Admit the full current day before an explicit-resume POST.
                        resource_nanos += bound.daily_nanos(pricing)
                        resource_nanos += _interval_nanos(bound, priced, resume["at"], day * DAY_SECONDS)
                    else:
                        # A terminal readback ends future compute but does not
                        # settle any usage accrued after the admitted resume.
                        resource_nanos += _interval_nanos(bound, priced, resume["at"], row["terminal_at"])
                elif row["terminal_at"] is None:
                    # Price possible running time after finite enforcement
                    # expiry now, rather than discovering the liability later.
                    end = max(_time(self.store.clock()), (day + 1) * DAY_SECONDS)
                    priced = _higher_rates(pricing, tariff_from_document(pause["tariff"]))
                    resource_nanos += _interval_nanos(bound, priced, pause["fence"]["valid_until"], end)
                else:
                    priced = _higher_rates(pricing, tariff_from_document(pause["tariff"]))
                    resource_nanos += _interval_nanos(bound, priced, pause["fence"]["valid_until"], row["terminal_at"])
            elif row["terminal_at"] is None or day <= int(row["terminal_at"] // DAY_SECONDS):
                priced = _higher_rates(pricing, tariff_from_document(row["tariff"])) if isinstance(
                    self.tariff, ObservedTariffEvidence) else self.tariff
                resource_nanos += bound.daily_nanos(priced)
            # An unconfirmed POST may create later. Its one-time fee has an unknown day.
            if row["created_at"] is None or day == int(row["created_at"] // DAY_SECONDS):
                fee_nanos += _nanos(bound.creation_fee_usd)
        for row in state["inference"].values():
            if row["canceled"] or int(row["at"] // DAY_SECONDS) > day:
                continue
            bill = row["receipt"]
            inference_nanos += row["max_nanos"] if bill is None else bill["actual_nanos"] if bill["accrued_day"] == day else 0
        if isinstance(self.tariff, ObservedTariffEvidence):
            held = dict(state.get("observed_pending_upper", {}))
            for key, upper in self.tariff.pending:
                held[key] = max(held.get(key, 0), _nanos(upper))
            for key, upper in held.items():
                row = state["inference"].get(key)
                if row and not row["canceled"] and row["receipt"] is None:
                    inference_nanos += max(0, upper - row["max_nanos"])
                row = state["resources"].get(key)
                if row and not row["canceled"]:
                    priced = _higher_rates(pricing, tariff_from_document(row["tariff"]))
                    reserved = ResourceBound(**row["bound"]).daily_nanos(priced) + _nanos(row["bound"]["creation_fee_usd"])
                    if row["terminal_at"] is None or day <= int(row["terminal_at"] // DAY_SECONDS):
                        resource_nanos += max(0, upper - reserved)
                    else:
                        resource_nanos += upper  # Terminal GET alone is not a final all-in charge allocation.
        return resource_nanos, fee_nanos, inference_nanos, prior_nanos

    def summary(self):
        with self.store.atomic():
            state, now = self._load(), _time(self.store.clock())
            self._check(state, now)
            day = int(now // DAY_SECONDS)
            resources, fees, inference, prior = self._totals(state, day)
            total = resources + fees + inference + prior
            # The following day is a conditional same-tariff projection, not proof of future prices.
            future = sum(self._totals(state, day + 1))
            result = {"utc_day": dt.datetime.fromtimestamp(day * DAY_SECONDS, dt.timezone.utc).date().isoformat(),
                    "resource_upper_nanos": resources, "creation_upper_nanos": fees, "inference_upper_nanos": inference,
                    "prior_cost_upper_nanos": prior,
                    "total_upper_nanos": total, "total_upper_usd": _usd(total), "room_nanos": max(0, self.cap_nanos - total),
                    "within_cap": total <= self.cap_nanos, "conditional_future_daily_upper_nanos": future,
                    "tariff_valid_until": self.tariff.valid_until, "vendor_actual": False}
            if isinstance(self.tariff, ObservedTariffEvidence):
                result.update(accounting_mode=self.tariff.mode, admission_total_at_observed_rates_usd=_usd(total),
                              admission_total_at_observed_rates_nanos=total,
                              price_basis_sha256=self.tariff.basis_sha256, price_basis_time=self.tariff.valid_from,
                              future_rate_lock=False, verified_all_in_ceiling=False,
                              provider_final_bill_guaranteed=False)
                # Preserve the shared numeric gate while naming the estimate honestly.
                result["total_upper_usd"] = None
                result["total_upper_nanos"] = None
                result["conditional_future_daily_upper_nanos"] = None
            return result

    def _admit(self, receipt):
        self.observe_prices()
        with self.store.atomic():
            state, now = self._load(), _time(self.store.clock())
            self._check(state, now)
            if isinstance(self.tariff, ObservedTariffEvidence) and not _same(state.get("observed_basis"), asdict(self.tariff)):
                state = self._write(state, {"action": "observed_basis", "at": now,
                                           "key": self.tariff.basis_sha256, "tariff": asdict(self.tariff)})
            receipt = {**receipt, "at": now}
            projected = _apply(json.loads(json.dumps(state)), receipt)
            if sum(self._totals(projected, int(now // DAY_SECONDS))) > self.cap_nanos:
                raise DailyAdmissionError("unified daily ceiling has no room for this obligation")
            return self._write(state, receipt)

    def reserve_resource(self, key: str, bound: ResourceBound):
        if not isinstance(bound, ResourceBound):
            raise DailyAdmissionError("explicit documented resource ceilings are required")
        return self._admit({"action": "resource_reserved", "key": key, "bound": asdict(bound),
                            "tariff": asdict(self.tariff)})["resources"][key]

    def reserve_inference(self, key: str, max_usd, *, provenance: str):
        return self._admit({"action": "inference_reserved", "key": key, "max_nanos": _nanos(max_usd),
                            "provenance": provenance})["inference"][key]

    def _transition(self, receipt, *, admission=False):
        if admission:self.observe_prices()
        with self.store.atomic():
            state, now = self._load(), _time(self.store.clock())
            if admission:
                self._check(state, now)
                if sum(self._totals(state, int(now // DAY_SECONDS))) > self.cap_nanos:
                    raise DailyAdmissionError("daily obligations already exceed the ceiling")
            elif now < state["last_at"]:
                raise DailyAdmissionError("daily reconciliation clock rolled back")
            return self._write(state, {**receipt, "at": now})

    def dispatch(self, key: str):
        """Persist the single dispatch slot before POST; never use this method as a retry."""
        self._transition({"action": "dispatched", "key": key}, admission=True)

    def cancel_unsent(self, key: str):
        self._transition({"action": "canceled_unsent", "key": key})

    def attach(self, key: str, resource_id: str, *, created_at: float, observed_bound: ResourceBound, provenance: str):
        if not isinstance(observed_bound, ResourceBound):
            raise DailyAdmissionError("actual resource ceiling evidence is required")
        # A provider readback contradicting an admitted ceiling makes its cost unknown.
        # Persist that breach before raising, so catching an exception cannot reopen paid work.
        breached = False
        with self.store.atomic():
            state, now = self._load(), _time(self.store.clock())
            if now < state["last_at"]:
                raise DailyAdmissionError("daily reconciliation clock rolled back")
            row = state["resources"].get(key)
            if row is not None:
                bound = ResourceBound(**row["bound"])
                breached = any(_decimal(getattr(observed_bound, field)) > _decimal(getattr(bound, field))
                               for field in ("vcpu", "memory_gib", "disk_gib", "volume_gib", "creation_fee_usd"))
            if breached:
                self._write(state, {"action": "scope_breached", "at": now, "key": key,
                                    "reason": "observed resource exceeds its admitted ceilings", "provenance": provenance})
            else:
                self._write(state, {"action": "resource_attached", "at": now, "key": key, "resource_id": resource_id,
                                    "created_at": created_at, "observed_bound": asdict(observed_bound), "provenance": provenance})
        if breached:
            raise DailyAdmissionError("observed resource exceeds its admitted ceilings; paid scope closed")

    def terminal_observed(self, key: str, resource_id: str, *, observed_at: float, status: str, provenance: str):
        self._transition({"action": "terminal_observed", "key": key, "resource_id": resource_id,
                          "observed_at": observed_at, "status": status, "provenance": provenance})

    def paused_observed(self, key: str, *, observation: NativePausedEvidence, fence: ResumeFenceEvidence,
                        retained_native_usage_upper_usd, usage_provenance: str):
        """Record a genuine paused GET and reviewed fence, preserving unsettled usage.

        The retained amount is the original cumulative usage upper bound, including
        any larger sampling/billing uncertainty and previously retired prefixes.
        It cannot decrease on a later pause. A separate final native settlement may
        retire a closed prefix and book its actual cost to genuine UTC accrual days.
        Reconciliation does not dispatch, settle an invoice, or open a new scope.
        """
        if not isinstance(observation, NativePausedEvidence) or not isinstance(fence, ResumeFenceEvidence):
            raise DailyAdmissionError("native paused GET and explicit resume enforcement evidence are required")
        if isinstance(self.tariff, ObservedTariffEvidence):
            raise DailyAdmissionError("fresh observed prices cannot certify the original paused usage interval; full hold retained")
        receipt = {"action": "native_paused", "key": key, "observation": asdict(observation),
                   "fence": asdict(fence), "tariff": asdict(self.tariff),
                   "retained_usage_nanos": _nanos(retained_native_usage_upper_usd),
                   "usage_provenance": usage_provenance}
        breached = False
        with self.store.atomic():
            state, now = self._load(), _time(self.store.clock())
            if now < state["last_at"]:
                raise DailyAdmissionError("daily reconciliation clock rolled back")
            row = state["resources"].get(key)
            if row is not None and observation.scope == state["scope"] and observation.resource_id == row["resource_id"]:
                document, bound = _json(observation.document_json), ResourceBound(**row["bound"])
                volumes = {r["resource_id"] for r in state["resources"].values()
                           if r["bound"]["kind"] == "volume" and r["resource_id"] and r["terminal_at"] is None}
                breached = any(size > _decimal(getattr(bound, name)) for size, name in
                               zip(_native_dimensions(document), ("vcpu", "memory_gib", "disk_gib"))) or any(
                    not isinstance(v, dict) or v.get("volume_id") not in volumes for v in document["volume_mounts"])
            if breached:
                self._write(state, {"action": "scope_breached", "at": now, "key": key,
                                    "reason": "native paused GET contradicts original resource/storage obligations",
                                    "provenance": observation.provenance})
            else:
                self._write(state, {**receipt, "at": now})
        if breached:
            raise DailyAdmissionError("native resource or storage exceeds original obligations; paid scope closed")

    def reserve_resume(self, key: str, resume_key: str, *, provenance: str):
        if isinstance(self.tariff, ObservedTariffEvidence):
            raise DailyAdmissionError("observed mode retains full resources; interval-bound pause/resume accounting remains required")
        """Reserve on the same original resource before allowing an explicit resume."""
        self._admit({"action": "resume_reserved", "key": key, "resume_key": resume_key,
                     "tariff": asdict(self.tariff), "provenance": provenance})

    def dispatch_resume(self, key: str, resume_key: str):
        """Consume exactly one resume slot before POST; a lost reply retains the hold."""
        self._transition({"action": "resume_dispatched", "key": key, "resume_key": resume_key}, admission=True)

    def cancel_resume_unsent(self, key: str, resume_key: str):
        self._transition({"action": "resume_canceled_unsent", "key": key, "resume_key": resume_key})

    def settle_native_usage(self, key: str, *, evidence: NativeUsageSettlementEvidence):
        """Host-reviewed final complete prefix only; never a sampled spend estimate.

        Reconciliation is allowed while paid dispatch is withdrawn. A greater real
        invoice durably closes the scope, preserving every original liability.
        This method does not obtain, authenticate or fabricate a native invoice.
        """
        if not isinstance(evidence, NativeUsageSettlementEvidence):
            raise DailyAdmissionError("reviewed final native usage evidence is required")
        breached = False
        with self.store.atomic():
            state, now = self._load(), _time(self.store.clock())
            if now < state["last_at"]:
                raise DailyAdmissionError("daily reconciliation clock rolled back")
            row, value, upper, pending, actual = _native_usage_prefix(state, key, evidence, self.tariff)
            if value["interval_end"] > now:
                raise DailyAdmissionError("native final allocation is ahead of original reconciliation")
            if actual > pending:
                breached = True
                self._write(state, {"action": "scope_breached", "at": now, "key": key,
                                    "reason": "final native invoice exceeds original retained compute upper; "
                                              + value["invoice_id"] + ":" + evidence.document_sha256,
                                    "provenance": evidence.provenance})
            # A genuinely final larger invoice is still booked to its actual
            # accrual days. The immutable breach keeps every paid route closed.
            self._write(state, {"action": "native_usage_settled", "at": now, "key": key,
                                "evidence": asdict(evidence), "tariff": asdict(self.tariff)})
        if breached:
            raise DailyAdmissionError("final native compute exceeds original retained bound; paid scope closed")

    def settle_inference(self, key: str, *, accrued_day: str, actual_usd, provenance: str):
        day = _day(accrued_day)
        actual, breached = _nanos(actual_usd), False
        with self.store.atomic():
            state, now = self._load(), _time(self.store.clock())
            if now < state["last_at"]:
                raise DailyAdmissionError("daily reconciliation clock rolled back")
            row = state["inference"].get(key)
            if row is not None and actual > row["max_nanos"]:
                breached = True
                self._write(state, {"action": "scope_breached", "at": now, "key": key,
                                    "reason": "authoritative inference bill exceeds its admitted maximum", "provenance": provenance})
            else:
                self._write(state, {"action": "inference_settled", "at": now, "key": key, "accrued_day": day,
                                    "actual_nanos": actual, "provenance": provenance})
        if breached:
            raise DailyAdmissionError("inference bill exceeds its admitted maximum; paid scope closed")
