"""Conditional compute commitments, separate from estimated spend and vendor invoices.

An owner-supplied bound must cover the checkpoint, tariff, all fixed charges, creation delay,
and guaranteed termination delay. Sail's published periodic TTL enforcement supplies no finite
delay guarantee, so no bound is supplied by default. Expiration never confirms termination.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import sqlite3
from dataclasses import asdict, dataclass
from typing import Any, Mapping


class ComputeAdmissionError(RuntimeError):
    pass


def _number(value: Any, *, positive: bool = False) -> bool:
    try:
        return (not isinstance(value, bool) and isinstance(value, (int, float))
                and math.isfinite(value) and (value > 0 if positive else value >= 0))
    except (ValueError, OverflowError):
        return False


def valid_timestamp(value: Any) -> bool:
    if not _number(value):
        return False
    try:
        dt.datetime.fromtimestamp(value, dt.timezone.utc)
        return True
    except (ValueError, OverflowError, OSError):
        return False


def _clock(value: Any) -> float:
    if not valid_timestamp(value):
        raise ComputeAdmissionError("invalid compute clock")
    return float(value)


def _identity(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()


def _pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ComputeAdmissionError("duplicate commitment field")
        value[key] = item
    return value


def _json(raw: str) -> Any:
    try:
        return json.loads(raw, object_pairs_hook=_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ComputeAdmissionError("nonfinite commitment field")))
    except (TypeError, ValueError) as exc:
        raise ComputeAdmissionError("unreadable compute commitments") from exc


def _same(left: Any, right: Any) -> bool:
    try:
        return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(right, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ComputeAdmissionError("unreadable immutable commitment fields") from exc


def _history(store) -> list[dict[str, Any]]:
    try:
        receipts = [_json(row["payload"]) for row in
                    store._all("SELECT payload FROM events WHERE kind='swarm.pool' ORDER BY seq")]
    except sqlite3.Error as exc:
        raise ComputeAdmissionError("unreadable immutable compute history") from exc
    if any(not isinstance(row, dict) for row in receipts):
        raise ComputeAdmissionError("unreadable immutable compute history")
    return receipts


@dataclass(frozen=True)
class ComputeBound:
    checkpoint: str
    max_usd_hour: float
    fixed_usd: float
    max_lifetime_seconds: int
    max_creation_delay_seconds: float
    max_stop_delay_seconds: float
    valid_until: float
    provenance: str

    def __post_init__(self):
        if not _identity(self.checkpoint) or not isinstance(self.provenance, str) or not self.provenance.strip():
            raise ComputeAdmissionError("compute bound needs a checkpoint and documented provenance")
        value = self.max_lifetime_seconds
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 4294967295:
            raise ComputeAdmissionError("compute lifetime must be an integer from 1 to 4294967295")
        for name in ("max_usd_hour", "fixed_usd", "max_creation_delay_seconds", "max_stop_delay_seconds", "valid_until"):
            value = getattr(self, name)
            if not _number(value):
                raise ComputeAdmissionError(f"invalid compute bound {name}")
        if self.max_usd_hour <= 0:
            raise ComputeAdmissionError("compute tariff bound must be positive")
        try:
            dt.datetime.fromtimestamp(self.valid_until, dt.timezone.utc)
        except (ValueError, OverflowError, OSError) as exc:
            raise ComputeAdmissionError("unrepresentable compute bound validity") from exc
        if not _number(self.seconds, positive=True) or not _number(self.usd, positive=True):
            raise ComputeAdmissionError("unrepresentable compute obligation")

    @property
    def seconds(self) -> float:
        return self.max_creation_delay_seconds + self.max_lifetime_seconds + self.max_stop_delay_seconds

    @property
    def usd(self) -> float:
        return self.fixed_usd + self.seconds * self.max_usd_hour / 3600.0


def bound_for(settings: Mapping[str, Any], checkpoint: str) -> ComputeBound:
    """Explicit trusted input; configuration alone does not establish a provider guarantee."""
    if not isinstance(settings, Mapping) or not isinstance(settings.get("gym"), Mapping) or not _identity(checkpoint):
        raise ComputeAdmissionError("malformed compute configuration")
    rows = settings["gym"].get("compute_bounds")
    value = rows.get(checkpoint) if isinstance(rows, Mapping) else None
    try:
        bound = value if isinstance(value, ComputeBound) else ComputeBound(**value) if isinstance(value, Mapping) else None
    except (TypeError, ValueError, OverflowError) as exc:
        raise ComputeAdmissionError("malformed compute bound") from exc
    if bound is None or bound.checkpoint != checkpoint:
        raise ComputeAdmissionError("no documented compute cost and lifetime bound for this checkpoint")
    estimate = settings.get("gym", {}).get("box_usd_hour", 0.20)
    if not _number(estimate, positive=True) or estimate > bound.max_usd_hour:
        raise ComputeAdmissionError("workload estimate is invalid or exceeds the compute tariff bound")
    return bound


def _holds(store, history=None) -> dict[str, Any]:
    row = store._one("SELECT value FROM kv WHERE key='compute_holds'")
    if row is None and store._one("SELECT value FROM kv WHERE key='compute_holds_initialized'") is not None:
        raise ComputeAdmissionError("durable compute commitments were lost")
    value = _json(row["value"]) if row is not None else {}
    if not isinstance(value, dict):
        raise ComputeAdmissionError("unreadable compute commitments")
    history = _history(store) if history is None else history
    plans, attachments, stopped, dispatched, canceled = {}, {}, {}, set(), set()
    for receipt in history:
        action, key = receipt.get("action"), receipt.get("key")
        if action not in ("compute_reserved", "compute_dispatched", "compute_attached", "compute_runtime_stopped", "compute_canceled_unsent"):
            continue
        if not _identity(key) or (action != "compute_reserved" and key not in plans):
            raise ComputeAdmissionError("compute history has no original admission")
        if action == "compute_reserved":
            if key in plans:
                raise ComputeAdmissionError("duplicate compute admission history")
            plans[key] = receipt
        elif action == "compute_dispatched":
            if key in canceled:
                raise ComputeAdmissionError("a canceled commitment was dispatched")
            dispatched.add(key)
        elif action == "compute_attached":
            box = receipt.get("box")
            if not _identity(box) or key in canceled or attachments.get(key, box) != box or any(
                    other != key and value == box for other, value in attachments.items()):
                raise ComputeAdmissionError("compute history lost its unique resource binding")
            attachments[key] = box
            dispatched.add(key)
        elif action == "compute_runtime_stopped":
            if receipt.get("box") != attachments.get(key) or not valid_timestamp(receipt.get("observed_at")):
                raise ComputeAdmissionError("terminal observation has no bound resource")
            stopped[key] = receipt["observed_at"]
        elif action == "compute_canceled_unsent":
            if key in dispatched or receipt.get("provider_dispatched") is not False:
                raise ComputeAdmissionError("cannot release a potentially dispatched commitment")
            canceled.add(key)
    if set(value) != set(plans):
        raise ComputeAdmissionError("compute commitments differ from the immutable admission history")
    for key, row in value.items():
        if not isinstance(row, Mapping):
            raise ComputeAdmissionError("unreadable compute commitment")
        plan = plans[key]
        try:
            bound = ComputeBound(**plan["bound"])
            at = _clock(plan["at"])
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise ComputeAdmissionError("invalid original compute admission") from exc
        if plan.get("kind") not in ("gym", "gate") or plan.get("checkpoint") != bound.checkpoint or any(
                not _number(plan.get(field), positive=True) or plan[field] != expected for field, expected in (
                    ("work_until", at + bound.max_lifetime_seconds), ("must_stop_by", at + bound.seconds), ("hold_usd", bound.usd))):
            raise ComputeAdmissionError("invalid original compute obligation")
        if (plan["must_stop_by"] > bound.valid_until
                or plan["must_stop_by"] > math.floor(at / 86400) * 86400 + 86400
                or (key in stopped and stopped[key] < at)):
            raise ComputeAdmissionError("original compute contract does not cover its lifecycle")
        fields = ("at", "checkpoint", "kind", "work_until", "must_stop_by", "hold_usd", "bound")
        if any(not _same(row.get(field), plan.get(field)) for field in fields):
            raise ComputeAdmissionError("compute commitment lost its original admitted bound")
        if row.get("box_id") != attachments.get(key) or not isinstance(row.get("confirmed_stopped"), bool) or not isinstance(row.get("billing_reconciled"), bool):
            raise ComputeAdmissionError("compute commitment lost its lifecycle evidence")
        unsent = key in canceled
        if (row["confirmed_stopped"] != (unsent or key in stopped)
                or (key in stopped and row.get("stopped_observed_at") != stopped[key])
                or row["billing_reconciled"] != unsent
                or (unsent and row.get("never_dispatched") is not True)):
            raise ComputeAdmissionError("billing release or terminal state has no authoritative evidence")
    return value


def _legacy(store, history=None) -> dict[str, Any]:
    raw = store._one("SELECT value FROM kv WHERE key='compute_unpriced_legacy'")
    if raw is None and store._one("SELECT value FROM kv WHERE key='compute_unpriced_legacy_initialized'") is not None:
        raise ComputeAdmissionError("legacy billing commitments were lost")
    rows = _json(raw["value"]) if raw is not None else {}
    if not isinstance(rows, dict):
        raise ComputeAdmissionError("unreadable legacy billing commitments")
    admissions = {}
    for receipt in _history(store) if history is None else history:
        if receipt.get("action") == "compute_unpriced_legacy":
            box = receipt.get("box")
            if (not _identity(box) or box in admissions or not valid_timestamp(receipt.get("at"))
                    or receipt.get("usd") is not None or receipt.get("runtime_stopped") is not False
                    or receipt.get("billing_reconciled") is not False or not _identity(receipt.get("reason"))):
                raise ComputeAdmissionError("invalid original legacy billing obligation")
            admissions[box] = receipt
    if set(rows) != set(admissions):
        raise ComputeAdmissionError("legacy commitments differ from the immutable history")
    for box, row in rows.items():
        if (not isinstance(row, dict) or row.get("at") != admissions[box]["at"] or row.get("usd") is not None
                or row.get("reason") != admissions[box].get("reason") or not isinstance(row.get("runtime_stopped"), bool)
                or row.get("billing_reconciled") is not False):
            raise ComputeAdmissionError("legacy billing release has no authoritative invoice evidence")
    return rows


def _charged(store, box_id: str) -> float:
    """Replay bookings with the same arithmetic and insertion order as ``book``.

    SQLite's compensated SUM can differ from repeated binary-float addition by one ULP.
    Exact replay avoids both that false corruption alarm and a tolerance that could hide
    a changed charge. Validate each row so aggregation cannot cancel or mask a bad cost.
    """
    total = 0.0
    for row in store._all("SELECT usd FROM spend WHERE kind='gym_box' "
                          "AND json_extract(detail, '$.box')=? ORDER BY seq", (box_id,)):
        if not _number(row["usd"]):
            raise ComputeAdmissionError("invalid recorded compute charge")
        total += row["usd"]
    if not _number(total):
        raise ComputeAdmissionError("unrepresentable recorded compute charges")
    return total


def remaining(store, *, since: float | None = None, now: float | None = None) -> float:
    """Unspent commitments in the requested day; malformed or breached obligations close admission."""
    total = 0.0
    try:
        now = _clock(store.clock() if now is None else now)
        if since is not None and (not valid_timestamp(since) or since > now):
            return math.inf
        history = _history(store)
        holds = _holds(store, history)
        if _legacy(store, history):
            return math.inf
        covered = {row.get("box_id") for row in holds.values() if isinstance(row, Mapping)}
        if any(row["id"] not in covered for row in store.boxes(live=False)):
            return math.inf  # a legacy/uncovered resource may still bill; no invented liability price
        pending_row = store._one("SELECT value FROM kv WHERE key='forking'")
        pending = _json(pending_row["value"]) if pending_row is not None else {}
        if not isinstance(pending, Mapping) or any(name not in holds for name in pending):
            return math.inf
        for key, row in holds.items():
            if not isinstance(row, Mapping):
                return math.inf
            values = [row.get(k) for k in ("at", "must_stop_by", "hold_usd", "booked_usd")]
            if any(not _number(v) for v in values):
                return math.inf
            at, deadline, held, booked = values
            if row.get("box_id") is not None:
                charged = _charged(store, row["box_id"])
                if booked != charged:
                    return math.inf
            elif booked != 0:
                return math.inf
            if not isinstance(row.get("confirmed_stopped"), bool) or not isinstance(row.get("billing_reconciled"), bool):
                return math.inf
            if row["billing_reconciled"]:
                if not row["confirmed_stopped"] or row.get("never_dispatched") is not True or row.get("box_id") is not None or booked != 0:
                    return math.inf
            if (booked > held or now < at or row.get("breached")
                    or (row.get("stopped_observed_at") is not None and row["stopped_observed_at"] > deadline)
                    or (not row["confirmed_stopped"] and now >= deadline)):
                return math.inf
            if row["billing_reconciled"]:
                continue
            if since is None or at >= since:
                total += max(0.0, held - booked)
        return total if math.isfinite(total) else math.inf
    except (ComputeAdmissionError, TypeError, ValueError, OverflowError, KeyError, sqlite3.Error):
        return math.inf


def reserve(store, settings: Mapping[str, Any], key: str, bound: ComputeBound, *, kind: str, now: float) -> dict[str, Any]:
    """Reserve the entire possible obligation before POST; model admissions share this transaction."""
    from ..ops import budget as B

    now = _clock(now)
    if not _identity(key) or kind not in ("gym", "gate") or not isinstance(bound, ComputeBound):
        raise ComputeAdmissionError("invalid compute admission identity, kind or bound")
    bound = ComputeBound(**asdict(bound))
    with store.atomic():
        observed = _clock(store.clock())
        if observed < now:
            raise ComputeAdmissionError("compute admission clock is invalid or rolled back")
        now = observed
        midnight = math.floor(now / 86400.0) * 86400.0
        deadline = now + bound.seconds
        amount = bound.usd
        if not math.isfinite(deadline) or not math.isfinite(amount) or deadline > bound.valid_until:
            raise ComputeAdmissionError("compute bound does not cover this obligation")
        if deadline > midnight + 86400.0:
            raise ComputeAdmissionError("compute obligation crosses UTC midnight without a future-day reservation")
        rows = _holds(store)
        if key in rows:
            raise ComputeAdmissionError("compute admission identity was already used")
        caps = B.sail_caps(settings, getattr(store, "root", None), now)
        if getattr(store, "root", None) is not None:
            current = B.sail_caps({"guard": settings.get("guard", {})}, store.root, now)
            caps = {**caps, "research": min(caps["research"], current["research"]),
                    "read": caps["read"] and current["read"]}
        kept = B.gate_reserve(caps["research"]) if kind == "gym" else 0.0
        spent = store.spent(B.SAIL_KINDS, since=midnight)
        committed = remaining(store, since=midnight, now=now)
        if not _number(spent) or not _number(committed) or not _number(caps["research"]) or caps["read"] is not True or amount > caps["research"] - kept - spent - committed:
            raise ComputeAdmissionError("Sail budget has no room for this bounded compute obligation")
        row = {"at": now, "checkpoint": bound.checkpoint, "kind": kind, "box_id": None,
               "work_until": now + bound.max_lifetime_seconds, "must_stop_by": deadline,
               "hold_usd": amount, "booked_usd": 0.0, "bound": asdict(bound),
               "confirmed_stopped": False, "billing_reconciled": False, "vendor_actual": False}
        rows[key] = row
        store.put("compute_holds_initialized", True)
        store.put("compute_holds", rows)
        store.event("swarm.pool", None, {"action": "compute_reserved", "key": key, **row})
        return row


def cancel_unsent(store, key: str) -> None:
    """Only the caller before any POST may certify that this request never reached the provider."""
    with store.atomic():
        rows = _holds(store)
        row = rows[key]
        if row.get("box_id") is not None or any(r.get("action") == "compute_dispatched" and r.get("key") == key for r in _history(store)):
            raise ComputeAdmissionError("cannot cancel a dispatched compute obligation")
        row.update(confirmed_stopped=True, billing_reconciled=True, never_dispatched=True)
        store.put("compute_holds", rows)
        store.event("swarm.pool", None, {"action": "compute_canceled_unsent", "key": key, "provider_dispatched": False})


def mark_dispatched(store, key: str) -> int:
    """Durable intent before POST: a lost create response cannot be certified as unsent."""
    with store.atomic():
        row = _holds(store).get(key)
        if row is None or row["confirmed_stopped"] or row.get("box_id") is not None or any(
                r.get("key") == key and r.get("action") == "compute_dispatched" for r in _history(store)):
            raise ComputeAdmissionError("compute dispatch has no active admission")
        now = _clock(store.clock())
        if now < row["at"]:
            raise ComputeAdmissionError("compute dispatch clock rolled back")
        lifetime = math.floor(row["work_until"] - now)
        if lifetime < 1:
            raise ComputeAdmissionError("compute lifetime expired before dispatch")
        store.event("swarm.pool", None, {"action": "compute_dispatched", "key": key})
        return lifetime


def attach(store, key: str, box_id: str) -> None:
    with store.atomic():
        rows = _holds(store)
        if not _identity(box_id) or key not in rows or rows[key]["confirmed_stopped"] or rows[key].get("box_id") not in (None, box_id) or any(
                other != key and row.get("box_id") == box_id for other, row in rows.items()):
            raise ComputeAdmissionError("compute commitment cannot be attached to this box")
        rows[key]["box_id"] = box_id
        store.put("compute_holds", rows)
        store.event("swarm.pool", None, {"action": "compute_attached", "key": key, "box": box_id})


def runnable(store, box_id: str, *, now: float, seconds: float) -> bool:
    if not _identity(box_id) or not _number(seconds, positive=True):
        return False
    try:
        if not math.isfinite(remaining(store, now=now)):
            return False
        return any(row.get("box_id") == box_id and not row["confirmed_stopped"] and not row.get("breached")
                   and isinstance(row.get("work_until"), (int, float)) and math.isfinite(row["work_until"])
                   and now + seconds <= row["work_until"] for row in _holds(store).values())
    except (ComputeAdmissionError, TypeError, ValueError, OverflowError):
        return False


def book(store, box_id: str, usd: float) -> None:
    """Estimated rows consume part of the commitment, rather than counting it twice."""
    if not _identity(box_id) or not _number(usd):
        raise ComputeAdmissionError("invalid compute booking")
    with store.atomic():
        rows = _holds(store)
        for row in rows.values():
            if row.get("box_id") == box_id:
                if not _number(row.get("booked_usd")):
                    raise ComputeAdmissionError("unreadable booked commitment")
                row["booked_usd"] += usd
                if row["booked_usd"] > row["hold_usd"]:
                    row["breached"] = True
                store.put("compute_holds", rows)
                return
        mark_uncovered(store, box_id)


def mark_uncovered(store, box_id: str) -> None:
    """An uncovered legacy bill has no invented amount, even after its runtime ends."""
    with store.atomic():
        if not _identity(box_id):
            raise ComputeAdmissionError("invalid legacy resource identity")
        if any(row.get("box_id") == box_id for row in _holds(store).values()):
            return
        rows = _legacy(store)
        if box_id not in rows:
            rows[box_id] = {"at": _clock(store.clock()), "usd": None, "runtime_stopped": False,
                            "billing_reconciled": False, "reason": "resource has no defensible original compute commitment"}
            store.put("compute_unpriced_legacy", rows)
            store.put("compute_unpriced_legacy_initialized", True)
            store.event("swarm.pool", None, {"action": "compute_unpriced_legacy", "box": box_id, **rows[box_id]})


def confirm_stopped(store, box_id: str, *, now: float) -> None:
    """Terminal observation closes runtime uncertainty; it supplies no vendor bill or refund."""
    now = _clock(now)
    if not _identity(box_id):
        raise ComputeAdmissionError("invalid terminal resource identity")
    with store.atomic():
        rows = _holds(store)
        for key, row in rows.items():
            if row.get("box_id") == box_id:
                if now < row.get("stopped_observed_at", row["at"]):
                    raise ComputeAdmissionError("terminal observation clock rolled back")
                if row["confirmed_stopped"]:
                    continue  # a repeated inventory read is not a later stop or new contract breach
                row.update(confirmed_stopped=True, stopped_observed_at=now)
                if now > row["must_stop_by"]:
                    row["breached"] = True
                store.event("swarm.pool", None, {"action": "compute_runtime_stopped", "key": key,
                                                  "box": box_id, "observed_at": now})
        store.put("compute_holds", rows)
        unknown = _legacy(store)
        if box_id in unknown:
            row = unknown[box_id]
            if now < row.get("stopped_observed_at", row["at"]):
                raise ComputeAdmissionError("legacy terminal observation clock rolled back")
            if not row["runtime_stopped"]:
                row.update(runtime_stopped=True, stopped_observed_at=now)
                store.put("compute_unpriced_legacy", unknown)
