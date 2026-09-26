"""Research lifecycle and shared Sail commitments. No execution/money-band authority.

The first daily period is Monday 13:30Z-midnight ($5.25); later UTC days are at most $12.
All paid work shares the same SQLite admission transaction. Maintenance is protected *inside*
that allowance. Unknown maintenance bounds pause paid post-burst work, never waive a cap.
The existing Sail meter and safety guard remain additional checks. No funding is changed here.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import shlex
import time
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from .evidence import one_record
from .store import SwarmStore, dumps

KINDS = ("sail_model", "gym_box", "data_box")
MAINTENANCE = ("nightly", "forward", "architect")
ET = ZoneInfo("America/New_York")


class BudgetDeferred(RuntimeError):
    """No new paid dispatch. An existing uncertain commitment is never discarded."""


def number(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("boolean amount")
    out = float(value)
    if not math.isfinite(out) or out < 0:
        raise ValueError("invalid amount")
    return out


def capacity(row: Mapping[str, Any], rate: float = .6) -> dict[str, Any]:
    """Validate actual Sail GET dimensions against the recorded capacity/rate bound."""
    keys = ("vcpu_count", "memory_mib", "state_disk_size_gib")
    limits = (8, 32768, 256)
    if any(type(row.get(k)) is not int or not 0 < row[k] <= limit for k, limit in zip(keys, limits)):
        raise BudgetDeferred("Sail capacity is unknown or exceeds 8cpu/32GiB/256GiB")
    hourly = (row[keys[0]] * 4167 + row[keys[1]] / 1024 * 2222 + row[keys[2]] * 194) * 3600 / 1e9
    if hourly > number(rate):
        raise BudgetDeferred("Sail capacity exceeds the reserved hourly rate")
    return {**{k: row[k] for k in keys}, "capacity_usd_hour": hourly}


class BoundedClient:
    """RPC deadlines plus OS process-group timeouts; HTTP failure never proves cancellation.

    Owners clean up with the raw client, confirm sleeping/terminal state, and retain the
    commitment if confirmation fails. A 120-second tail is reserved for transport/cleanup.
    """
    def __init__(self, client, deadline, *, clock=time.time):
        self.client, self.deadline, self.clock = client, deadline, clock

    def __getattr__(self, name):
        fn = getattr(self.client, name)
        if name not in ("exec", "resume", "from_checkpoint", "upload", "download", "checkpoint"):
            return fn

        def call(*args, **kwargs):
            end = self.deadline()
            if end is None:
                return fn(*args, **kwargs)
            remaining = int(end - self.clock() - 120)
            if remaining < 15:
                raise BudgetDeferred("paid box deadline reached; cleanup required")
            kwargs["timeout"] = min(int(kwargs.get("timeout", 300)), remaining)
            if name == "exec":
                if kwargs.get("background"):
                    raise BudgetDeferred("unbounded background work is not admitted after the burst")
                command = args[1]
                command = command if isinstance(command, str) else shlex.join(command)
                command = (f"timeout --signal=TERM --kill-after=10 {max(1, kwargs['timeout'] - 10)} "
                           f"sh -c {shlex.quote(command)}")
                args = (args[0], command, *args[2:])
            return fn(*args, **kwargs)
        return call


class Lifecycle:
    def __init__(self, store: SwarmStore, settings: Mapping[str, Any], *, clock=None):
        self.store, self.settings = store, settings
        self.clock = clock or store.clock

    @property
    def cfg(self):
        return self.settings.get("lifecycle", {})

    def boundary(self) -> float:
        saved = self.store.get("lifecycle_boundary")
        if saved is not None:
            return float(saved)
        end = dt.datetime.fromisoformat(str(self.settings.get("guard", {}).get(
            "burst_until", "2026-09-28T13:30:00Z")).replace("Z", "+00:00")).timestamp()
        with self.store.atomic():
            if self.store.get("lifecycle_boundary") is None:
                self.store.put("lifecycle_boundary", end)
        return float(self.store.get("lifecycle_boundary"))

    def burst(self) -> bool:
        return self.clock() < self.boundary()

    def period(self) -> dict[str, Any]:
        now, end = self.clock(), self.boundary()
        if now < end:
            return {"id": "burst", "start": float(self.store.get("burst_started_at", now)), "end": end,
                    "cap": number(self.settings.get("guard", {}).get("burst_cap_usd", 350)), "fraction": 1.0}
        midnight = now - now % 86400
        start = max(midnight, end)
        fraction = (midnight + 86400 - start) / 86400
        cap = min(12.0, number(self.settings.get("guard", {}).get("after_burst_usd_day", 12))) * fraction
        return {"id": str(int(start)), "start": start, "end": midnight + 86400, "cap": cap, "fraction": fraction}

    def completed_days(self) -> list[str]:
        """The canonical data calendar; unreadable calendars produce no purported observations."""
        data = json.loads((self.store.root / "data/calendar.json").read_text())
        exceptions = data["exceptions"]
        if not isinstance(exceptions, dict):
            raise ValueError("invalid canonical calendar")
        now = dt.datetime.fromtimestamp(self.clock(), ET)
        day, out = now.date(), []
        for _ in range(100):
            hours = exceptions.get(day.isoformat(), [570, 960])
            if day.weekday() < 5 and hours is not None:
                if (not isinstance(hours, list) or len(hours) != 2 or
                        any(type(n) is not int for n in hours) or not 0 <= hours[0] < hours[1] < 1440):
                    raise ValueError("invalid calendar session")
                close = dt.datetime.combine(day, dt.time(), ET) + dt.timedelta(minutes=hours[1])
                if close <= now:
                    out.append(day.isoformat())
                    if len(out) == 20:
                        return out
            day -= dt.timedelta(days=1)
        raise ValueError("calendar has fewer than 20 completed sessions")

    def evidence(self) -> dict[str, Any]:
        try:
            days = self.completed_days()
        except (OSError, ValueError, TypeError, KeyError):
            return {"status": "insufficient", "reason": "canonical calendar unavailable"}
        ready = self.settings.get("forward", {}).get("ready") or {}
        families = self.store.families()
        current = [f for f in families if not f.get("retired_at") and f["band"] in ("candidate", "probe", "sized")]
        for fam in current:
            state = fam.get("state") or {}
            receipt = state.get("forward_replay") or {}
            target = receipt.get("target") or {}
            version = state.get("banded_version")
            if (not version or receipt.get("version") != version or target.get("day") != days[0]
                    or ready.get("day") != days[0] or not target.get("checkpoint")
                    or target.get("checkpoint") != ready.get("gate_checkpoint") or not target.get("bundle")
                    or target.get("bundle") != self.settings.get("forward", {}).get("current_bundle")
                    or target.get("checkpoint") != self.settings.get("gym", {}).get("gate_checkpoint")):
                return {"status": "insufficient", "reason": "latest version-bound forward replay incomplete", "day": days[0]}
        returns, observed = [], set()
        for fam in families:  # losses of retired/demoted versions stay in the compute record
            rows = self.store.forward(fam["id"])
            versions = {r.get("version") for r in rows if r.get("version") is not None}
            for version in versions:
                if self.store.version(fam["id"], version) is None:
                    return {"status": "insufficient", "reason": "forward version missing"}
                for row in one_record(rows, version=version):
                    if row.get("day") not in days:
                        continue
                    try:
                        pnl, maximum = float(row["pnl"]), float(row["max_loss"])
                        if not math.isfinite(pnl) or not math.isfinite(maximum) or maximum <= 0:
                            raise ValueError("invalid forward return")
                    except (ValueError, TypeError, KeyError):
                        return {"status": "insufficient", "reason": "invalid forward return"}
                    returns.append(pnl / maximum)
                    observed.add(row["day"])
        result = {"observations": len(returns), "sessions": len(observed), "day": days[0], "window_sessions": 20}
        if len(returns) < 20 or len(observed) < 5:
            return {**result, "status": "insufficient", "reason": "need 20 closed returns across 5 sessions"}
        mean = sum(returns) / len(returns)
        return {**result, "status": "positive" if mean > 0 else "flat" if mean == 0 else "negative", "mean_rom": mean}

    def refresh(self) -> dict[str, Any]:
        with self.store.atomic():
            previous = self.store.get("lifecycle") or {}
            period = self.period()
            if self.burst():
                state = {"mode": "burst", "period": period, "cohort": None, "evidence": {"status": "not_due"}}
            else:
                evidence = self.evidence()
                mode = ("floor" if evidence["status"] in ("flat", "negative") else
                        "steady" if evidence["status"] == "positive" else
                        "floor" if previous.get("mode") == "floor" else "steady")
                alive = self.store.families(alive=True)
                limit = min(16, max(0, int(self.cfg.get("research_families", 16))))
                alive_ids = {f["id"] for f in alive}
                cohort = [f for f in previous.get("cohort") or [] if f in alive_ids][:limit]
                if previous.get("period", {}).get("id") != period["id"]:
                    cohort = []  # once a day the updated bandit can select dormant families too
                ranked = sorted(alive, key=lambda f: (-float(f.get("weight") or 0), f["id"]))
                new = [f for f in ranked if int(f.get("validations") or 0) < 2]
                for fam in new[:min(len(new), math.ceil(limit * .25))] + ranked:
                    if len(cohort) < limit and fam["id"] not in cohort:
                        cohort.append(fam["id"])
                state = {"mode": mode, "period": period, "cohort": cohort, "evidence": evidence}
            self.store.put("lifecycle", state)
            if previous.get("mode") != state["mode"] or previous.get("period", {}).get("id") != period["id"]:
                self.store.event("swarm.status", None, {"action": "lifecycle", **state})
            return state

    def research_allowed(self, family: str | None = None) -> bool:
        if self.burst():
            return True
        state = self.store.get("lifecycle") or {}
        return (state.get("mode") == "steady" and state.get("period", {}).get("id") == self.period()["id"]
                and (family is None or family in (state.get("cohort") or [])))


class SailBudget(Lifecycle):
    """Shared process-safe reservations, with conservative carry across periods and uncertain dispatches.

    Tagged spend rows remain the economic ledger. This separate admission ledger retains unsettled
    holds and actual charges; old untagged rows and the account meter are conservative backstops.
    """
    def _maintenance(self) -> dict[str, float]:
        raw = self.cfg.get("maintenance_usd") or {}
        if not str(self.cfg.get("maintenance_basis") or "").strip():
            raise BudgetDeferred("maintenance cost bounds have not been verified")
        try:
            return {k: number(raw[k]) for k in MAINTENANCE}
        except (TypeError, ValueError, KeyError):
            raise BudgetDeferred("maintenance cost bounds are missing or invalid") from None

    def status(self) -> dict[str, Any]:
        with self.store.atomic():
            p = self.period()
            charges = self.store._all("SELECT bucket, SUM(usd) usd FROM sail_charges WHERE period=? GROUP BY bucket", (p["id"],))
            held = self.store._all("SELECT bucket, SUM(MAX(0,reserved-accounted)) usd FROM sail_commitments "
                                   "WHERE state='open' GROUP BY bucket")
            by_bucket = {b: sum(float(r["usd"]) for r in charges + held if r["bucket"] == b)
                         for b in ("research",) + MAINTENANCE}
            legacy = self.store._one("SELECT COALESCE(SUM(usd),0) usd FROM spend WHERE epoch>=? AND kind IN (?,?,?) "
                                    "AND json_extract(detail,'$.budget_key') IS NULL", (p["start"], *KINDS))["usd"]
            meter = self.store.get("lifecycle_meter") or {}
            metered = float(meter.get("spent") or 0) if meter.get("period") == p["id"] else 0.0
            actual = max(0.0, float(legacy)) + sum(float(r["usd"]) for r in charges)
            pending = sum(float(r["usd"]) for r in held)
            house = max(4.0, number(self.cfg.get("house_usd_day", 4)), number(
                self.settings.get("guard", {}).get("house_burn_usd_day", 1))) * p["fraction"]
            buffer = number(self.cfg.get("uncertainty_usd", .5)) * p["fraction"]
            used = max(actual, metered) + pending + (0 if self.burst() else house + buffer)
            error, maintenance = None, {}
            if not self.burst():
                try:
                    maintenance = self._maintenance()
                except BudgetDeferred as exc:
                    error = str(exc)
            done = self.store.get("maintenance_done") or {}
            protected = {k: max(0., v - by_bucket[k]) if done.get(k) != p["id"] else 0.0 for k, v in maintenance.items()}
            room = max(0.0, p["cap"] - used)
            return {"period": p, "used_usd": used, "actual_usd": actual, "metered_usd": metered,
                    "held_usd": pending, "room_usd": room, "research_room_usd": 0.0 if error else max(0., room - sum(protected.values())),
                    "maintenance": maintenance, "protected": protected, "buckets": by_bucket,
                    "reason": error, "basis": str(self.cfg.get("maintenance_basis") or "")}

    def _safe(self):
        guard = self.store.get("guard") or {}
        if guard.get("braked", True) or self.clock() - float(guard.get("last_ok") or 0) >= float(
                self.settings.get("guard", {}).get("stale_seconds", 600)):
            raise BudgetDeferred("Sail safety guard is braked or stale")

    def reserve(self, key: str, usd: float, *, kind: str, bucket: str = "research", detail=None) -> dict[str, Any]:
        amount = number(usd)
        if bucket not in ("research",) + MAINTENANCE:
            raise ValueError("unknown Sail budget bucket")
        with self.store.atomic():
            prior = self.store._one("SELECT * FROM sail_commitments WHERE key=?", (key,))
            if prior and prior["state"] != "released":
                if prior["bucket"] != bucket or prior["kind"] != kind or float(prior["reserved"]) != amount:
                    raise BudgetDeferred("commitment identity changed")
                return prior  # recovery/polling a paid request creates no new admission
            if not self.burst():
                self._safe()
                status = self.status()
                if status["reason"]:
                    raise BudgetDeferred(status["reason"])
                if bucket == "research" and not self.research_allowed():
                    raise BudgetDeferred("research lifecycle is paused")
                room = status["research_room_usd"] if bucket == "research" else min(
                    status["room_usd"], max(0., status["maintenance"][bucket] - status["buckets"][bucket]))
                if amount > room + 1e-9:
                    raise BudgetDeferred(f"Sail budget defers {bucket}: ${amount:.6f} needed, ${room:.6f} available")
            now = self.clock()
            self.store._exec("INSERT INTO sail_commitments(key,kind,bucket,reserved,accounted,state,created,updated,detail) "
                             "VALUES(?,?,?,?,0,'open',?,?,?) ON CONFLICT(key) DO UPDATE SET reserved=excluded.reserved, "
                             "accounted=0,state='open',created=excluded.created,updated=excluded.updated,detail=excluded.detail",
                             (key, kind, bucket, amount, now, now, dumps(detail or {})))
            return self.store._one("SELECT * FROM sail_commitments WHERE key=?", (key,))

    def charge(self, key: str, usd: float, *, final: bool = False, released: bool = False) -> None:
        """Cumulative confirmed charge. Unknown outcomes keep their open reservation. Never infer $0."""
        amount = number(usd)
        with self.store.atomic():
            row = self.store._one("SELECT * FROM sail_commitments WHERE key=?", (key,))
            if row is None:
                return  # pre-upgrade work is still covered by the untagged ledger/meter
            if row["state"] in ("settled", "released"):
                return
            delta = max(0.0, amount - float(row["accounted"]))
            p = self.period()
            self.store._exec("INSERT INTO sail_charges(period,key,bucket,usd) VALUES(?,?,?,?) ON CONFLICT(period,key) "
                             "DO UPDATE SET usd=usd+excluded.usd", (p["id"], key, row["bucket"], delta))
            self.store._exec("UPDATE sail_commitments SET accounted=?,state=?,updated=? WHERE key=?",
                             (max(amount, float(row["accounted"])), "released" if released else "settled" if final else "open",
                              self.clock(), key))

    def finish_maintenance(self, bucket: str) -> None:
        with self.store.atomic():
            done = self.store.get("maintenance_done") or {}
            done[bucket] = self.period()["id"]
            self.store.put("maintenance_done", done)

    def meter(self, balance: float | None) -> None:
        """The full fall across a boundary is charged to the new period; no overlap is forgiven."""
        if balance is None:
            return
        with self.store.atomic():
            p = self.period()
            previous = self.store.get("lifecycle_meter") or {}
            spent = float(previous.get("spent") or 0) if previous.get("period") == p["id"] else 0.0
            last = previous.get("balance")
            if last is None:
                last = self.store.get("metered_last_balance")
            if last is not None:
                spent += max(0., float(last) - balance)
            self.store.put("lifecycle_meter", {"period": p["id"], "spent": spent, "balance": balance, "at": self.clock()})
