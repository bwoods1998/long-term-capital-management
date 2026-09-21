"""Owner-funded campaigns with atomic commitments and no calendar catch-up spending.

Reservations survive timeouts, process restarts and the end of the phase. Unknown charges are
never converted to zero or expired by a timer. The policy is outside every model role's write
paths. External development/infrastructure reserves are commitments, not claimed invoice costs.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_UP
import json
import math
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any, Mapping

from .ledger import canonical
from .pacer import Pacer

UNIT = Decimal("1000000")


class CampaignClosed(ValueError):
    code = "campaign_budget_closed"


def micro(value: Any) -> int:
    amount = Decimal(str(value))
    if not amount.is_finite() or amount < 0:
        raise ValueError("money must be finite and nonnegative")
    return int((amount * UNIT).to_integral_value(rounding=ROUND_UP))


def usd(value: int) -> str:
    return format(Decimal(value) / UNIT, "f")


def load_policy() -> dict[str, Any]:
    return json.loads(Path(__file__).with_name("campaigns.json").read_text(encoding="utf-8"))


class CampaignBudget:
    def __init__(self, path: str | Path, policy: Mapping[str, Any] | None = None, *, clock=time.time):
        self.policy = dict(policy or load_policy())
        self.clock, self.lock = clock, threading.RLock()
        duration = float(self.policy["duration_hours"])
        if not math.isfinite(duration) or duration <= 0 or not self.policy["phase"]:
            raise ValueError("invalid phase duration or identity")
        self.caps = {k: micro(v) for k, v in self.policy["caps_usd"].items()}
        self.external = {k: micro(v) for k, v in self.policy.get("external_reserves_usd", {}).items()}
        if sum(self.caps.values()) != micro(self.policy["total_cap_usd"]):
            raise ValueError("phase allocation does not equal the total cap")
        if any(k not in self.caps or v > self.caps[k] for k, v in self.external.items()):
            raise ValueError("external reserve exceeds its allocation")
        for campaign in self.policy["campaigns"].values():
            if campaign["kind"] not in self.caps or micro(campaign["cap_usd"]) > self.caps[campaign["kind"]]:
                raise ValueError("invalid campaign allocation")
            if not all(str(campaign.get(k) or "").strip() for k in ("question", "baseline", "artifact", "acceptance")):
                raise ValueError("a funded campaign needs a question, baseline, artifact and acceptance check")
        self.db = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS phase(id TEXT PRIMARY KEY, policy TEXT NOT NULL, started REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS commitments(
                id TEXT PRIMARY KEY, campaign TEXT NOT NULL, kind TEXT NOT NULL,
                reserved INTEGER NOT NULL, cost INTEGER, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS meter(id TEXT PRIMARY KEY, baseline INTEGER NOT NULL, latest INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS responses(id TEXT PRIMARY KEY, commitment TEXT NOT NULL, profile TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS meter_health(id TEXT PRIMARY KEY, checked REAL NOT NULL, failed INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS burst(id TEXT PRIMARY KEY, started REAL NOT NULL, ends REAL NOT NULL,
                policy TEXT NOT NULL, first_row INTEGER NOT NULL, meters TEXT NOT NULL);
        """)
        encoded = canonical(self.policy)
        self.db.execute("INSERT OR IGNORE INTO phase VALUES(?,?,?)", (self.policy["phase"], encoded, clock()))
        phase = self.db.execute("SELECT * FROM phase WHERE id=?", (self.policy["phase"],)).fetchone()
        if phase["policy"] != encoded or self.db.execute("SELECT COUNT(*) FROM phase").fetchone()[0] != 1:
            raise CampaignClosed("campaign policy changed; explicit migration is required")
        self.started = phase["started"]
        self.ends = self.started + float(self.policy["duration_hours"]) * 3600

    def running(self) -> bool:
        burst = self.burst()
        return self.started <= self.clock() < self.ends and (not burst or burst['started'] <= self.clock() < burst['ends'])

    def burst(self) -> dict[str, Any] | None:
        with self.lock:
            row = self.db.execute('SELECT * FROM burst').fetchone()
            if row is None:
                return None
            return {**dict(row), 'policy': json.loads(row['policy']), 'meters': json.loads(row['meters'])}

    def activate_burst(self, ident: str, policy: Mapping[str, Any]) -> dict[str, Any]:
        """Explicit owner action; one immutable, incremental research allowance per phase.

        Never reset the phase, meters, original commitments or Jev backing. New commitments
        share this window across all processes. Expiry stops new paid work, not reconciliation.
        """
        from .overnight import validate
        validate(policy)
        if not ident or len(ident) > 100:
            raise ValueError('burst requires a bounded identity')
        if micro(self.policy['total_cap_usd']) + sum(micro(v) for v in policy['caps_usd'].values()) > micro('10000'):
            raise ValueError('burst exceeds the owner project envelope')
        encoded = canonical(policy)
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                old = self.burst()
                if old:
                    if old['id'] != ident or canonical(old['policy']) != encoded:
                        raise CampaignClosed('a burst already exists; cannot reset its clock or allowance')
                else:
                    if not self.running() or not all(self.ready(k) for k in policy['caps_usd']):
                        raise CampaignClosed('the phase and required meters must be healthy before activation')
                    started = self.clock()
                    ends = min(self.ends, started + float(policy['duration_hours']) * 3600)
                    rowid = self.db.execute('SELECT COALESCE(MAX(rowid),0) FROM commitments').fetchone()[0]
                    meters = dict(self.db.execute('SELECT id,latest FROM meter').fetchall())
                    self.db.execute('INSERT INTO burst VALUES(?,?,?,?,?,?)',
                                    (ident, started, ends, encoded, rowid, canonical(meters)))
                self.db.execute('COMMIT')
            except BaseException:
                self.db.execute('ROLLBACK')
                raise
        return self.burst()

    def _burst_used(self, kind: str, burst: Mapping[str, Any]) -> int:
        settled, pending = self.db.execute('SELECT COALESCE(SUM(cost),0),'
            'COALESCE(SUM(CASE WHEN cost IS NULL THEN reserved ELSE 0 END),0) '
            'FROM commitments WHERE kind=? AND rowid>?', (kind, burst['first_row'])).fetchone()
        latest = self.db.execute('SELECT latest FROM meter WHERE id=?', (kind,)).fetchone()
        measured = max(0, latest[0] - burst['meters'].get(kind, latest[0])) if latest else 0
        return max(settled, measured) + pending

    def allowance(self, kind: str) -> Decimal:
        burst = self.burst()
        return Decimal(str((burst['policy']['caps_usd'] if burst else self.policy['daily_caps_usd']).get(kind, '0')))

    def ready(self, kind: str) -> bool:
        with self.lock:
            if self.db.execute("SELECT 1 FROM commitments WHERE cost>reserved LIMIT 1").fetchone():
                return False
        if kind not in self.policy.get("meter_required", []):
            return True
        with self.lock:
            row = self.db.execute("SELECT checked,failed FROM meter_health WHERE id=?", (kind,)).fetchone()
            return bool(row and not row[1] and 0 <= self.clock() - row[0] <= 180)

    def _used(self, kind: str) -> int:
        settled, pending = self.db.execute("SELECT COALESCE(SUM(cost),0),COALESCE(SUM(CASE WHEN cost IS NULL THEN reserved ELSE 0 END),0) FROM commitments WHERE kind=?", (kind,)).fetchone()
        measured = self.db.execute("SELECT MAX(latest-baseline) FROM meter WHERE id=?", (kind,)).fetchone()[0] or 0
        # Account meter already includes settled model costs. Do not add them twice. Including
        # unresolved holds again is intentionally conservative when vendor billing arrives first.
        return self.external.get(kind, 0) + max(settled, measured) + pending

    def remaining(self, kind: str) -> Decimal:
        with self.lock:
            burst = self.burst()
            if burst:
                cap = micro(burst['policy']['caps_usd'].get(kind, '0'))
                return Decimal(max(0, cap - self._burst_used(kind, burst))) / UNIT if self.running() else Decimal(0)
            return Decimal(max(0, self.caps[kind] - self._used(kind))) / UNIT

    def reserve(self, ident: str, campaign: str, amount: Any) -> bool:
        held = micro(amount)
        rule = self.policy["campaigns"][campaign]
        kind = rule["kind"]
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                old = self.db.execute("SELECT * FROM commitments WHERE id=?", (ident,)).fetchone()
                if old:
                    if old["campaign"] != campaign or old["reserved"] != held:
                        raise CampaignClosed("request identity changed its campaign or commitment")
                    self.db.execute("COMMIT")
                    return False
                burst = self.burst()
                used = self.db.execute("SELECT COALESCE(SUM(COALESCE(cost,reserved)),0) FROM commitments WHERE campaign=?", (campaign,)).fetchone()[0]
                if not self.running() or not self.ready(kind):
                    raise CampaignClosed(f"{campaign}: released allowance is unavailable")
                if burst:
                    if held > micro(self.remaining(kind)):
                        raise CampaignClosed(f'{campaign}: burst allowance is unavailable')
                elif self._used(kind) + held > self.caps[kind] or used + held > micro(rule['cap_usd']):
                    raise CampaignClosed(f'{campaign}: released allowance is unavailable')
                daily = None if burst else self.policy.get("daily_caps_usd", {}).get(kind)
                if daily is not None and micro(self.today(kind)) + held > micro(daily):
                    raise CampaignClosed(f"{campaign}: daily allowance is unavailable")
                if self.db.execute("SELECT 1 FROM commitments WHERE cost>reserved LIMIT 1").fetchone():
                    raise CampaignClosed("a charge exceeded its reservation; pricing must be reconciled")
                extra = sum(micro(v) for v in burst['policy']['caps_usd'].values()) if burst else 0
                if sum(self._used(k) for k in self.caps) + held > micro(self.policy["total_cap_usd"]) + extra:
                    raise CampaignClosed("aggregate phase allowance is unavailable")
                self.db.execute("INSERT INTO commitments VALUES(?,?,?,?,NULL,?)", (ident, campaign, kind, held, self.clock()))
                self.db.execute("COMMIT")
                return True
            except BaseException:
                self.db.execute("ROLLBACK")
                raise

    def settle(self, ident: str, amount: Any) -> None:
        cost = micro(amount)
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                row = self.db.execute("SELECT * FROM commitments WHERE id=?", (ident,)).fetchone()
                if row is None:
                    raise CampaignClosed("settlement has no recorded commitment")
                if row["cost"] is not None and row["cost"] != cost:
                    raise CampaignClosed("a settled charge cannot silently change")
                self.db.execute("UPDATE commitments SET cost=? WHERE id=?", (cost, ident))
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise

    def observe_spend(self, kind: str, cumulative: Any) -> None:
        """Conservative vendor-account expenditure since activation; never infer it from top-ups."""
        amount = micro(cumulative)
        with self.lock:
            old = self.db.execute("SELECT latest FROM meter WHERE id=?", (kind,)).fetchone()
            if old and amount < old[0]:
                self.db.execute("INSERT INTO meter_health VALUES(?,?,1) ON CONFLICT(id) DO UPDATE SET failed=1", (kind, self.clock()))
                raise CampaignClosed("vendor expenditure decreased; reconcile the billing period before spending")
            self.db.execute("INSERT INTO meter VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET latest=MAX(latest,excluded.latest)",
                            (kind, amount, amount))
            self.db.execute("INSERT INTO meter_health VALUES(?,?,0) ON CONFLICT(id) DO UPDATE SET checked=excluded.checked", (kind, self.clock()))

    def today(self, kind: str) -> Decimal:
        midnight = int(self.clock() // 86400) * 86400
        with self.lock:
            value = self.db.execute("SELECT COALESCE(SUM(COALESCE(cost,reserved)),0) FROM commitments WHERE kind=? AND created>=?", (kind, midnight)).fetchone()[0]
        return Decimal(value) / UNIT

    def link_response(self, response: str, commitment: str, profile: str) -> None:
        with self.lock:
            old = self.db.execute("SELECT commitment,profile FROM responses WHERE id=?", (response,)).fetchone()
            if old and tuple(old) != (commitment, profile):
                raise CampaignClosed("response identity changed")
            self.db.execute("INSERT OR IGNORE INTO responses VALUES(?,?,?)", (response, commitment, profile))

    def response(self, ident: str):
        with self.lock:
            row = self.db.execute("SELECT commitment,profile FROM responses WHERE id=?", (ident,)).fetchone()
            return tuple(row) if row else None

    def response_for(self, commitment: str):
        with self.lock:
            row = self.db.execute("SELECT id FROM responses WHERE commitment=?", (commitment,)).fetchone()
            return row[0] if row else None

    def report(self) -> dict[str, Any]:
        with self.lock:
            burst = self.burst()
            extra = burst['policy']['caps_usd'] if burst else {}
            return {"phase": self.policy["phase"], "started": self.started, "ends": self.ends,
                "running": self.running(), "cap_usd": usd(micro(self.policy['total_cap_usd']) + sum(micro(v) for v in extra.values())),
                "foundation_cap_usd": self.policy['total_cap_usd'],
                "allow_new_live_capital": self.policy["allow_new_live_capital"],
                "accounts": {kind: {"cap_usd": usd(cap + micro(extra.get(kind, '0'))), "committed_usd": usd(self._used(kind)),
                    "external_reserve_usd": usd(self.external.get(kind, 0)), "remaining_usd": str(self.remaining(kind))}
                    for kind, cap in self.caps.items()},
                "meters_ready": {kind: self.ready(kind) for kind in self.caps},
                "pending_calls": self.db.execute("SELECT COUNT(*) FROM commitments WHERE cost IS NULL").fetchone()[0],
                "reservation_breaches": self.db.execute("SELECT COUNT(*) FROM commitments WHERE cost>reserved").fetchone()[0],
                "burst": ({'id': burst['id'], 'started': burst['started'], 'ends': burst['ends'],
                    'running': self.running(), 'caps_usd': burst['policy']['caps_usd'],
                    'committed_usd': {k: usd(self._burst_used(k, burst)) for k in burst['policy']['caps_usd']},
                    'remaining_usd': {k: str(self.remaining(k)) for k in burst['policy']['caps_usd']},
                    'note': 'Additional owner research allowance. Original phase and commitments are retained; expiry closes new paid work.'} if burst else None),
                "note": "Commitments include unresolved calls and external reserves; this is not a vendor invoice."}

    def close(self) -> None:
        with self.lock:
            self.db.close()


class CampaignPacer(Pacer):
    """Compatibility interface for the House; no missed-day catch-up or underspend acceleration."""
    no_catch_up = True

    def __init__(self, ledger, guard: CampaignBudget, *, clock=time.time):
        self.ledger, self.guard, self.clock = ledger, guard, clock
        self.start = datetime.fromtimestamp(guard.started, timezone.utc).date()
        self.days = max(1, int(float(guard.policy["duration_hours"]) / 24))
        self.budget = {k: Decimal(guard.caps[k] - guard.external.get(k, 0)) / UNIT for k in ("sail", "openai")}

    def running(self) -> bool:
        return self.guard.running()

    def _spend(self, kind: str) -> dict[str, Decimal]:
        return {"total": self.spent(kind), "today": self.guard.today(kind)}

    def spent(self, kind: str) -> Decimal:
        burst = self.guard.burst()
        if burst:
            with self.guard.lock:
                return Decimal(self.guard._burst_used(kind, burst)) / UNIT
        return self.budget[kind] - self.guard.remaining(kind)

    def remaining(self, kind: str) -> Decimal:
        return self.guard.remaining(kind)

    def allowance(self, kind: str) -> Decimal:
        return self.guard.allowance(kind) if self.running() else Decimal(0)

    def room(self, kind: str) -> Decimal:
        if not self.guard.ready(kind):
            return Decimal(0)
        if self.guard.burst():
            return self.remaining(kind)
        return max(Decimal(0), min(self.remaining(kind), self.allowance(kind) - self.guard.today(kind)))

    def over(self, kind: str) -> bool:
        return not self.running() or self.remaining(kind) <= 0

    def report(self) -> dict[str, Any]:
        result = {**super().report(), "campaign": self.guard.report(), "no_catch_up": True}
        burst = self.guard.burst()
        if burst:
            result['allowance_scope'] = 'entire immutable burst, not daily replenishment'
            for kind in ('sail', 'openai'):
                result[kind]['budget_usd'] = burst['policy']['caps_usd'][kind]
        return result

    def credit_pool(self, *, per_seconds=86400, **kwargs):
        burst = self.guard.burst()
        if not burst:
            return super().credit_pool(per_seconds=per_seconds, **kwargs)
        if not self.running():
            return Decimal(0)
        # This is an eight-hour envelope, not a daily allowance. Reserve half of OpenAI
        # for shared architect work and a quarter of Sail for hosting/validation.
        total = self.allowance('sail') * Decimal('.75') + self.allowance('openai') * Decimal('.5')
        duration = Decimal(str(burst['ends'] - burst['started']))
        return (total * Decimal(str(per_seconds)) / duration).quantize(Decimal('.01'))
