"""Offline daily obligations that do not rely on a maximum provider stop delay.

Every unresolved creation and every nonterminated resource reserves its full 24-hour
ceiling on each UTC day, indefinitely. An uncertain creation fee and an unresolved
inference request also carry into every possible future charge day. Runtime estimates,
sleep, elapsed TTLs, lost replies, and missing inventory rows never release a hold.

This module performs no provider operations and has no production pricing defaults.
Evidence objects are explicit trusted inputs, not verification of a provider contract.
A tariff must cover the whole requested UTC day. Future-day prices remain conditional
until such evidence exists. All resource/model dispatchers must share this gate and
the same durable store; a copied database or an outside writer invalidates the scope.
Existing unpriced resources are refused; migration needs separate authoritative cost
evidence. Vendor costs, reporting estimates, and these upper bounds stay distinct.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import sqlite3
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR
from typing import Any

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
        if key in resources or key in inference:
            raise DailyAdmissionError("daily obligation identity was already used")
        if action == "resource_reserved":
            _fields(receipt, "action at key bound tariff")
            bound, tariff = ResourceBound(**receipt["bound"]), TariffEvidence(**receipt["tariff"])
            if tariff.scope != state["scope"] or not tariff.covers_day(int(at // DAY_SECONDS)):
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

    def _load(self):
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

    def _check(self, state, now):
        evidence = self.inventory
        if state["breached"]:
            raise DailyAdmissionError("authoritative evidence breached the daily obligation bounds")
        if (not evidence.complete or not evidence.exclusive_writer or evidence.unknown_obligations
                or not evidence.observed_at <= now <= evidence.valid_until):
            raise DailyAdmissionError("inventory is partial, stale, shared, or has unknown obligations")
        if now < state["last_at"]:
            raise DailyAdmissionError("daily admission clock rolled back")
        covered = {r["resource_id"] for r in state["resources"].values() if r["resource_id"] is not None}
        pending_models = {key for key, row in state["inference"].items() if not row["canceled"] and row["receipt"] is None}
        if set(evidence.resource_ids) - covered or set(evidence.model_keys) - pending_models:
            raise DailyAdmissionError("inventory contains an uncovered resource or inference obligation")
        if not self.tariff.covers_day(int(now // DAY_SECONDS)):
            raise DailyAdmissionError("tariff evidence does not cover this full UTC day")

    def _write(self, state, receipt):
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
        for row in state["resources"].values():
            if row["canceled"] or int(row["at"] // DAY_SECONDS) > day:
                continue
            bound = ResourceBound(**row["bound"])
            if row["terminal_at"] is None or day <= int(row["terminal_at"] // DAY_SECONDS):
                resource_nanos += bound.daily_nanos(self.tariff)
            # An unconfirmed POST may create later. Its one-time fee has an unknown day.
            if row["created_at"] is None or day == int(row["created_at"] // DAY_SECONDS):
                fee_nanos += _nanos(bound.creation_fee_usd)
        for row in state["inference"].values():
            if row["canceled"] or int(row["at"] // DAY_SECONDS) > day:
                continue
            bill = row["receipt"]
            inference_nanos += row["max_nanos"] if bill is None else bill["actual_nanos"] if bill["accrued_day"] == day else 0
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
            return {"utc_day": dt.datetime.fromtimestamp(day * DAY_SECONDS, dt.timezone.utc).date().isoformat(),
                    "resource_upper_nanos": resources, "creation_upper_nanos": fees, "inference_upper_nanos": inference,
                    "prior_cost_upper_nanos": prior,
                    "total_upper_nanos": total, "total_upper_usd": _usd(total), "room_nanos": max(0, self.cap_nanos - total),
                    "within_cap": total <= self.cap_nanos, "conditional_future_daily_upper_nanos": future,
                    "tariff_valid_until": self.tariff.valid_until, "vendor_actual": False}

    def _admit(self, receipt):
        with self.store.atomic():
            state, now = self._load(), _time(self.store.clock())
            self._check(state, now)
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
