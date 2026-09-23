"""Owner-funded campaigns with atomic commitments and no calendar catch-up spending.

Reservations survive timeouts, process restarts and the end of the phase. Unknown charges are
never converted to zero or expired by a timer -- with one exception, on a provider with an account
meter: a hold older than the meter's lag is absorbed into the meter, which already counts whatever
the vendor charged (`absorb_stale`). The policy is outside every model role's write paths.
External development/infrastructure reserves are commitments, not claimed invoice costs.
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
            CREATE TABLE IF NOT EXISTS live_pilot(id TEXT PRIMARY KEY, started REAL NOT NULL,
                ends REAL NOT NULL, policy TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS live_trading(id TEXT PRIMARY KEY, started REAL NOT NULL,
                policy TEXT NOT NULL, revoked REAL);
            CREATE TABLE IF NOT EXISTS live_ratifications(id TEXT NOT NULL, at REAL NOT NULL,
                old_policy TEXT NOT NULL, new_policy TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS topups(id TEXT PRIMARY KEY, at REAL NOT NULL, kind TEXT NOT NULL,
                amount INTEGER NOT NULL, note TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS meter_balance(id TEXT PRIMARY KEY, last INTEGER NOT NULL, at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS meter_reconciliations(id TEXT PRIMARY KEY, kind TEXT NOT NULL, at REAL NOT NULL,
                evidence TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS cost_reconciliations(id TEXT PRIMARY KEY, commitment TEXT NOT NULL,
                evidence TEXT NOT NULL, at REAL NOT NULL);
        """)
        encoded = canonical(self.policy)
        self.db.execute("INSERT OR IGNORE INTO phase VALUES(?,?,?)", (self.policy["phase"], encoded, clock()))
        phase = self.db.execute("SELECT * FROM phase WHERE id=?", (self.policy["phase"],)).fetchone()
        if phase["policy"] != encoded or self.db.execute("SELECT COUNT(*) FROM phase").fetchone()[0] != 1:
            raise CampaignClosed("campaign policy changed; explicit migration is required")
        self.started = phase["started"]
        self.ends = self.started + float(self.policy["duration_hours"]) * 3600

    def running(self) -> bool:
        live = self.live_trading()
        if live and live['active']:
            return True  # Explicit owner grant: existing dollars remain bounded, without a timer.
        burst = self.burst()
        return self.started <= self.clock() < self.ends and (not burst or burst['started'] <= self.clock() < burst['ends'])

    def live_trading(self) -> dict[str, Any] | None:
        # A grant pins the rules that govern real money (`constitution.money_digest`); a legacy
        # grant pinned the whole constitution and holds only while its money rules are unchanged.
        with self.lock:
            row = self.db.execute('SELECT * FROM live_trading').fetchone()
            if row is None:
                return None
            value = {**dict(row), 'policy': json.loads(row['policy']), 'mode': 'persistent', 'ends': None}
            from .live_trading import policy
            value['active'] = (value['revoked'] is None and value['started'] <= self.clock()
                               and _grant_matches(value['policy'], policy(value['policy']['venue_capital_usd'])))
            return value

    def live_authorization(self) -> dict[str, Any] | None:
        # Even a revoked grant retains its capital accounting; disabling cannot erase losses.
        return self.live_trading() or self.live_pilot()

    def ratify_live_trading(self, ident: str) -> dict[str, Any]:
        """Account-owner action: keep an existing grant under revised MONEY rules. The same identity,
        the same capital allocation (never more), re-pinned to the current `money_digest`; the old
        policy is kept in `live_ratifications`. A revoked grant stays revoked."""
        from .live_trading import policy
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                row = self.db.execute('SELECT * FROM live_trading').fetchone()
                if row is None or row['id'] != ident:
                    raise CampaignClosed('no live grant with that identity to ratify')
                if row['revoked'] is not None:
                    raise CampaignClosed('a revoked grant cannot be ratified')
                old = json.loads(row['policy'])
                new = canonical(policy(old['venue_capital_usd']))
                if new != row['policy']:
                    self.db.execute('INSERT INTO live_ratifications VALUES(?,?,?,?)', (ident, self.clock(), row['policy'], new))
                    self.db.execute('UPDATE live_trading SET policy=? WHERE id=?', (new, ident))
                self.db.execute('COMMIT')
            except BaseException:
                self.db.execute('ROLLBACK')
                raise
        return self.live_trading()

    def activate_live_trading(self, ident: str, venue_capital: Mapping[str, Any]) -> dict[str, Any]:
        """Account-owner action. Persistent ladder access; no provider or capital replenishment."""
        from .live_trading import policy
        if not isinstance(ident, str) or not ident.strip() or len(ident) > 100:
            raise ValueError('live trading requires a bounded identity')
        encoded = canonical(policy(venue_capital))
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                old = self.live_trading()
                if old:
                    if old['id'] != ident or canonical(old['policy']) != encoded:
                        raise CampaignClosed('live trading already has a capital allocation; it cannot reset')
                else:
                    if self.live_pilot():
                        raise CampaignClosed('an existing pilot requires an explicit capital migration')
                    burst = self.burst()
                    if not burst or not all(self.ready(k) for k in ('sail', 'openai')):
                        raise CampaignClosed('an existing funded burst and healthy provider meters are required')
                    if any(self._burst_used(k, burst) >= micro(burst['policy']['caps_usd'][k]) for k in ('sail', 'openai')):
                        raise CampaignClosed('unused Sail and OpenAI allowance is required for execution and audits')
                    self.db.execute('INSERT INTO live_trading VALUES(?,?,?,NULL)', (ident, self.clock(), encoded))
                self.db.execute('COMMIT')
            except BaseException:
                self.db.execute('ROLLBACK')
                raise
        return self.live_trading()

    def revoke_live_trading(self) -> None:
        with self.lock:
            self.db.execute('UPDATE live_trading SET revoked=COALESCE(revoked,?)', (self.clock(),))

    def burst(self) -> dict[str, Any] | None:
        """The funded burst, its caps raised by every owner top-up (`top_up`). The stored policy
        row never changes; spend already committed is never reset."""
        with self.lock:
            row = self.db.execute('SELECT * FROM burst').fetchone()
            if row is None:
                return None
            policy = json.loads(row['policy'])
            added = dict(self.db.execute('SELECT kind, SUM(amount) FROM topups GROUP BY kind').fetchall())
            if added:
                policy['caps_usd'] = {k: usd(micro(v) + int(added.get(k) or 0)) for k, v in policy['caps_usd'].items()}
            return {**dict(row), 'policy': policy, 'meters': json.loads(row['meters']),
                    'topups_usd': {k: usd(v) for k, v in added.items()}}

    def topped_up(self, kind: str, month: str) -> Decimal:
        """What the owner recorded adding at `kind`'s provider during the UTC calendar month
        `month` ("YYYY-MM"). The Sail meter raises its monthly line by it: on Sept 21, 2026 the
        owner's $100 Sail top-up raised the burst's ceiling but left the account meter's $100 line
        where it was, and the whole floor would have stopped with his new credit unspent."""
        with self.lock:
            rows = self.db.execute('SELECT at, amount FROM topups WHERE kind=?', (kind,)).fetchall()
        total = sum(int(amount) for at, amount in rows if time.strftime('%Y-%m', time.gmtime(float(at))) == month)
        return Decimal(total) / UNIT

    def top_up(self, ident: str, kind: str, amount: Any, note: str) -> dict[str, Any]:
        """Account-owner action: the owner added money at the provider, and the burst may spend it.
        Append-only and idempotent by identity; it raises a ceiling and resets nothing."""
        value = micro(amount)
        if kind not in ('sail', 'openai') or not 0 < value <= micro('1000'):
            raise ValueError('a top-up is Sail or OpenAI, more than $0 and at most $1,000')
        if not ident or len(ident) > 100 or not str(note).strip():
            raise ValueError('a top-up needs an identity and a note')
        with self.lock:
            if self.burst() is None:
                raise CampaignClosed('there is no funded burst to top up')
            self.db.execute('BEGIN IMMEDIATE')
            try:
                old = self.db.execute('SELECT kind, amount FROM topups WHERE id=?', (ident,)).fetchone()
                if old and (old[0], old[1]) != (kind, value):
                    raise CampaignClosed('that top-up identity already names a different amount')
                if not old:
                    self.db.execute('INSERT INTO topups VALUES(?,?,?,?,?)', (ident, self.clock(), kind, value, str(note)[:300]))
                self.db.execute('COMMIT')
            except BaseException:
                self.db.execute('ROLLBACK')
                raise
        return self.burst()

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
                    if old['id'] != ident or self.db.execute('SELECT policy FROM burst').fetchone()[0] != encoded:
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

    def live_pilot(self) -> dict[str, Any] | None:
        with self.lock:
            row = self.db.execute('SELECT * FROM live_pilot').fetchone()
            if row is None:
                return None
            value = {**dict(row), 'policy': json.loads(row['policy'])}
            from .live_pilot import policy
            value['active'] = (value['policy'] == policy() and self.running()
                               and value['started'] <= self.clock() < value['ends'])
            return value

    def activate_live_pilot(self, ident: str) -> dict[str, Any]:
        """One explicit account-owner activation; never implied by a research budget.

        The original phase, provider holds and deadline remain untouched. This grants only the
        existing audited micro entry and evidence-based scaling inside one bounded experiment.
        It cannot renew itself after expiry.
        """
        from .live_pilot import policy
        from .constitution import CONSTITUTION
        if not isinstance(ident, str) or not ident.strip() or len(ident) > 100:
            raise ValueError('live pilot requires a bounded identity')
        if Decimal(CONSTITUTION['rungs']['2']['stake_usd']) != Decimal(policy()['stake_usd']):
            raise ValueError('the live pilot requires the existing $25 micro stake')
        encoded = canonical(policy())
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                if self.live_trading():
                    raise CampaignClosed('persistent live trading cannot be replaced by a timed pilot')
                old = self.live_pilot()
                if old:
                    if old['id'] != ident or canonical(old['policy']) != encoded:
                        raise CampaignClosed('a live pilot already exists; its risk or deadline cannot reset')
                else:
                    burst = self.burst()
                    if not burst or not self.running() or not all(self.ready(k) for k in ('sail', 'openai')):
                        raise CampaignClosed('a healthy funded research burst is required')
                    if self.remaining('openai') <= 0:
                        raise CampaignClosed('fresh promotion audits need funded OpenAI allowance')
                    self.db.execute('INSERT INTO live_pilot VALUES(?,?,?,?)',
                                    (ident, self.clock(), min(self.ends, burst['ends']), encoded))
                self.db.execute('COMMIT')
            except BaseException:
                self.db.execute('ROLLBACK')
                raise
        return self.live_pilot()

    def allows_live(self, target_rung: int) -> bool:
        if target_rung not in (2, 3):
            return False
        live = self.live_trading()
        if live:
            return live['active'] and target_rung <= live['policy']['max_rung']
        if self.policy['allow_new_live_capital']:
            return True
        pilot = self.live_pilot()
        return bool(pilot and pilot['active'] and target_rung <= pilot['policy']['max_rung'])

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

    def observe_balance(self, kind: str, balance: Any, *, evidence: Mapping[str, Any] | None = None) -> Decimal:
        """Vendor-account expenditure from the account BALANCE: every decrease is spend; an
        increase (a top-up, a refund) is never credited back, so a top-up cannot hide spend and
        the meter can never run backwards. Returns the spend this reading added.

        Why not the usage summary's `range=period` figure, which `observe_spend` was fed: on this
        account it is not a billing period at all but a ROLLING seven-day window
        (`effective_range: "7d"`, `plan_limited: true`). It falls whenever older spend rolls off
        faster than new spend arrives, and at 16:47:39Z Sept 22, 2026 it did -- the first run's
        Sept 15 spend aged out -- so `observe_spend` latched the meter failed and the whole floor
        (research, Merton, audits, births) stopped on a vendor window, with $73 of Sail allowance
        unspent. The balance is exact, includes sandboxes and hosting like the old feed, and moves
        down only when the account is charged.

        The first balance reading continues the existing meter where it stands (its `latest` is
        kept, so nothing already measured is forgotten), and a latch the old feed set is cleared
        then, once, with the evidence kept in `meter_reconciliations`. After that the balance
        feed cannot latch: an unavailable balance just leaves the meter unread (`ready` goes false
        after 180 s), which stops paid work until the vendor answers again."""
        amount = micro(balance)
        now = self.clock()
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                row = self.db.execute("SELECT last FROM meter_balance WHERE id=?", (kind,)).fetchone()
                meter = self.db.execute("SELECT baseline, latest FROM meter WHERE id=?", (kind,)).fetchone()
                added = 0
                if row is None:
                    if meter is None:
                        self.db.execute("INSERT INTO meter VALUES(?,?,?)", (kind, 0, 0))
                    self.db.execute("INSERT INTO meter_balance VALUES(?,?,?)", (kind, amount, now))
                    health = self.db.execute("SELECT failed FROM meter_health WHERE id=?", (kind,)).fetchone()
                    if health and health["failed"]:
                        record = {"cause": "the usage summary's period figure is a rolling window, not a cumulative meter",
                                  "meter_before": {"baseline": meter["baseline"], "latest": meter["latest"]} if meter else None,
                                  "balance_micro_usd": amount, "vendor": dict(evidence or {})}
                        self.db.execute("INSERT INTO meter_reconciliations VALUES(?,?,?,?)",
                                        (f"{kind}:balance-feed:{int(now)}", kind, now, canonical(record)))
                        self.db.execute("UPDATE meter_health SET failed=0 WHERE id=?", (kind,))
                else:
                    added = max(0, int(row["last"]) - amount)
                    if added:
                        self.db.execute("UPDATE meter SET latest=latest+? WHERE id=?", (added, kind))
                    self.db.execute("UPDATE meter_balance SET last=?, at=? WHERE id=?", (amount, now, kind))
                self.db.execute("INSERT INTO meter_health VALUES(?,?,0) ON CONFLICT(id) DO UPDATE SET checked=excluded.checked",
                                (kind, now))
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
        return Decimal(added) / UNIT

    def absorb_stale(self, kind: str, *, older_than_seconds: float, evidence: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Release the holds of a METERED provider that are older than the meter's lag, and settle
        them against the meter: their charge, if the vendor made one, is already inside the account
        meter, which `_burst_used` counts as `max(settled, measured)`. Each release is kept with its
        evidence in `cost_reconciliations`; nothing is released while the meter is unhealthy or
        below what has been settled (the meter must dominate for the charge to be counted).

        Measured Sept 22, 2026 23:50Z: 329 Sail holds ($60.59) were pending since the burst began,
        none with a linked response -- requests whose POST was never confirmed (restarts, timeouts).
        The balance meter had measured $59.65 of Sail spend against $55.14 settled, so every real
        charge was already counted once, and the holds counted it again: the campaign read $54.76
        left while the account held $116."""
        if kind not in self.policy.get("meter_required", []):
            raise ValueError(f"{kind} has no account meter to absorb holds into")
        cutoff = self.clock() - float(older_than_seconds)
        with self.lock:
            if not self.ready(kind):
                return {"absorbed": 0, "usd": "0", "why": "the meter is not healthy"}
            self.db.execute("BEGIN IMMEDIATE")
            try:
                burst = self.burst()
                first = int(burst["first_row"]) if burst else 0
                settled = self.db.execute("SELECT COALESCE(SUM(cost),0) FROM commitments WHERE kind=? AND rowid>?", (kind, first)).fetchone()[0]
                latest = self.db.execute("SELECT latest FROM meter WHERE id=?", (kind,)).fetchone()
                baseline = (burst["meters"].get(kind) if burst else None)
                measured = max(0, latest[0] - (baseline if baseline is not None else latest[0])) if latest else 0
                if measured < settled:
                    self.db.execute("COMMIT")
                    return {"absorbed": 0, "usd": "0", "why": "the meter has not caught up with settled costs"}
                rows = self.db.execute(
                    "SELECT c.id, c.reserved FROM commitments c LEFT JOIN responses r ON r.commitment = c.id "
                    "WHERE c.kind=? AND c.cost IS NULL AND c.created < ? AND r.id IS NULL", (kind, cutoff)).fetchall()
                record = {"cause": "a hold older than the meter's lag, with no response to settle it from",
                          "measured_micro_usd": measured, "settled_micro_usd": settled, **dict(evidence or {})}
                for ident, reserved in rows:
                    self.db.execute("UPDATE commitments SET cost=0 WHERE id=? AND cost IS NULL", (ident,))
                    self.db.execute("INSERT OR IGNORE INTO cost_reconciliations VALUES(?,?,?,?)",
                                    (f"absorbed:{ident}", ident, canonical({**record, "reserved_micro_usd": reserved}), self.clock()))
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
        return {"absorbed": len(rows), "usd": usd(sum(int(r[1]) for r in rows)), "measured_usd": usd(measured), "settled_usd": usd(settled)}

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
                "live_pilot": self.live_pilot(),
                "live_trading": self.live_trading(),
                "effective_research_deadline": (None if self.live_trading() and self.live_trading()['active']
                                                else min(self.ends, burst['ends']) if burst else self.ends),
                "accounts": {kind: {"cap_usd": usd(cap + micro(extra.get(kind, '0'))), "committed_usd": usd(self._used(kind)),
                    "external_reserve_usd": usd(self.external.get(kind, 0)), "remaining_usd": str(self.remaining(kind))}
                    for kind, cap in self.caps.items()},
                "meters_ready": {kind: self.ready(kind) for kind in self.caps},
                "pending_calls": self.db.execute("SELECT COUNT(*) FROM commitments WHERE cost IS NULL").fetchone()[0],
                "reservation_breaches": self.db.execute("SELECT COUNT(*) FROM commitments WHERE cost>reserved").fetchone()[0],
                "burst": ({'id': burst['id'], 'started': burst['started'], 'ends': burst['ends'],
                    'running': burst['started'] <= self.clock() < min(self.ends, burst['ends']), 'caps_usd': burst['policy']['caps_usd'],
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
        live = self.guard.live_trading()
        allowance = self.remaining if live and live['active'] else self.allowance
        total = allowance('sail') * Decimal('.75') + allowance('openai') * Decimal('.5')
        duration = Decimal(str(burst['ends'] - burst['started']))
        return (total * Decimal(str(per_seconds)) / duration).quantize(Decimal('.01'))


def _grant_matches(stored: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    if stored == expected:
        return True
    from .constitution import LEGACY_GRANT_DIGESTS
    legacy = LEGACY_GRANT_DIGESTS.get(stored.get('constitution_digest'))
    return (legacy is not None and legacy == expected.get('constitution_digest')
            and {**stored, 'constitution_digest': legacy} == dict(expected))
