"""Owner-funded campaigns with atomic commitments and no calendar catch-up spending.

Reservations survive timeouts, process restarts and the end of the phase. Unknown charges are
never converted to zero or expired by a timer -- with one exception, on a provider with an account
meter: a hold older than the meter's lag is absorbed into the meter, which already counts whatever
the vendor charged (`absorb_stale`). Sail's meter is its account balance (`observe_balance`);
OpenAI's, since Sept 24, 2026, is the gateway's frontier month (`observe_month`). The policy is
outside every model role's write paths. External development/infrastructure reserves are
commitments, not claimed invoice costs.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, ROUND_UP
import json
import math
from pathlib import Path
import re
import sqlite3
import threading
import time
from typing import Any, Callable, Mapping

from .ledger import canonical
from .pacer import Pacer

UNIT = Decimal("1000000")
#: A provider's billing month as the gateway names it (`/v1/health` `frontier.month`).
MONTH = re.compile(r"\d{4}-(0[1-9]|1[0-2])")


def month_start(month: str) -> float:
    """The first instant of a UTC calendar month "YYYY-MM", in epoch seconds."""
    return datetime(int(month[:4]), int(month[5:7]), 1, tzinfo=timezone.utc).timestamp()


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
    #: The commitments each provider's account meter records, by identity prefix (Sept 24, 2026).
    #: Sail's balance falls for every Sail charge, sandboxes and hosting included: all of them.
    #: OpenAI's meter is the gateway's frontier month, which counts only the calls made through
    #: `POST /v1/frontier/responses`; the House files those as `frontier:<hex>` (league/frontier.py).
    #: Jev's retained backing (`external-pilot:typesafe:*`, $20 on Sept 24) is OpenAI-kind money the
    #: gateway reports apart (`/v1/health` `typesafe`): it is never absorbed into the month, and a
    #: cost settled on it is added to the line beside the meter, never hidden inside
    #: `max(settled, measured)`.
    METER_COVERS = {"sail": "", "openai": "frontier:"}
    #: A reservation asks a registered reader (`meter_reader`) for a new reading once the last one is
    #: this old, so a reading is never 180 s stale (`ready`) merely because a tick ran long.
    METER_READ_SECONDS = 60
    #: A meter reading older than this is no reading: the kind's reservations are refused (`ready`),
    #: and a monthly meter's own line no longer bounds what is left (`_provider_left`).
    METER_FRESH_SECONDS = 180

    def __init__(self, path: str | Path, policy: Mapping[str, Any] | None = None, *, clock=time.time):
        self.policy = dict(policy or load_policy())
        self.clock, self.lock = clock, threading.RLock()
        self._readers: dict[str, Callable[[], Any]] = {}
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
            CREATE TABLE IF NOT EXISTS gateway_bonus(id TEXT PRIMARY KEY, amount INTEGER NOT NULL, at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS meter_month(id TEXT PRIMARY KEY, month TEXT NOT NULL, high INTEGER NOT NULL,
                carried INTEGER NOT NULL, settled_high INTEGER, settled_carried INTEGER NOT NULL,
                covers_from REAL NOT NULL, anchor_at REAL, anchor_row INTEGER, anchor_settled INTEGER, at REAL NOT NULL,
                cap INTEGER, spent INTEGER, reading_row INTEGER, base INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS phase_amendments(id TEXT NOT NULL, at REAL NOT NULL, old_policy TEXT NOT NULL,
                new_policy TEXT NOT NULL, why TEXT NOT NULL);
        """)
        # The gateway's own line and the meter's base (Sept 24, 2026 review) joined `meter_month` after
        # its first build: a store that build created gains them here, and reads them as unknown.
        columns = lambda: {r[1] for r in self.db.execute("PRAGMA table_info(meter_month)")}  # noqa: E731
        for name, decl in (("cap", "INTEGER"), ("spent", "INTEGER"), ("reading_row", "INTEGER"),
                           ("base", "INTEGER NOT NULL DEFAULT 0")):
            if name not in columns():
                try:
                    self.db.execute(f"ALTER TABLE meter_month ADD COLUMN {name} {decl}")
                except sqlite3.OperationalError:
                    if name not in columns():  # another process added it first
                        self.db.close()
                        raise
        encoded = canonical(self.policy)
        self.db.execute("INSERT OR IGNORE INTO phase VALUES(?,?,?)", (self.policy["phase"], encoded, clock()))
        phase = self.db.execute("SELECT * FROM phase WHERE id=?", (self.policy["phase"],)).fetchone()
        try:
            if self.db.execute("SELECT COUNT(*) FROM phase").fetchone()[0] != 1:
                raise CampaignClosed("campaign policy changed; explicit migration is required")
            if phase["policy"] != encoded:
                self._amend(phase["policy"], encoded)
        except BaseException:
            self.db.close()  # a refused phase is never opened, and its connection is not left behind
            raise
        self.started = phase["started"]
        self.ends = self.started + float(self.policy["duration_hours"]) * 3600

    def _amend(self, pinned: str, encoded: str) -> None:
        """The one policy change a deploy may make to a running phase without the owner: a provider
        becomes metered (`meter_required` gains a kind, nothing else changes). That only adds a rule
        -- the kind's reservations then need a fresh meter reading, and its holds older than the
        meter's lag may be absorbed into it (`absorb_stale`). The phase keeps its pinned policy, so a
        rollback to the release before still opens it; the amendment is recorded once in
        `phase_amendments`, the pinned policy and the running one side by side. Every other change
        still refuses.

        Sept 24, 2026: OpenAI joined Sail, metered by the gateway's frontier month. Without this, the
        new `campaigns.json` would have refused to open the live phase and the House would not start;
        rewriting the pinned policy instead would have done the same to a rollback."""
        old, new = json.loads(pinned), json.loads(encoded)
        before, after = list(old.get("meter_required") or []), list(new.get("meter_required") or [])
        added = [kind for kind in after if kind not in before]
        rest = lambda policy: canonical({k: v for k, v in policy.items() if k != "meter_required"})  # noqa: E731
        if (rest(old) != rest(new) or not added or any(kind not in after for kind in before)
                or any(kind not in new.get("caps_usd", {}) for kind in added)):
            raise CampaignClosed("campaign policy changed; explicit migration is required")
        why = (f"metered: {', '.join(added)}. Its reservations need a fresh meter reading and its holds older "
               f"than the meter's lag may be absorbed into it; nothing else in the policy changed.")
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                if not self.db.execute("SELECT 1 FROM phase_amendments WHERE id=? AND new_policy=?",
                                       (new["phase"], encoded)).fetchone():
                    self.db.execute("INSERT INTO phase_amendments VALUES(?,?,?,?,?)",
                                    (new["phase"], self.clock(), pinned, encoded, why))
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise

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
            bonus = {'openai': self.gateway_bonus('openai')}
            if added or any(bonus.values()):
                policy['caps_usd'] = {k: usd(micro(v) + int(added.get(k) or 0) + bonus.get(k, 0)) for k, v in policy['caps_usd'].items()}
            return {**dict(row), 'policy': policy, 'meters': json.loads(row['meters']),
                    'topups_usd': {k: usd(v) for k, v in added.items()},
                    'gateway_bonus_usd': {k: usd(v) for k, v in bonus.items()}}

    #: A mirrored gateway raise older than this no longer raises the House's line.
    GATEWAY_BONUS_SECONDS = 1800

    def gateway_bonus(self, kind: str) -> int:
        """What the gateway's profit indexing adds to `kind`'s month now, in micro-dollars, as last
        mirrored (`mirror_gateway_bonus`); 0 when never mirrored or not mirrored recently."""
        with self.lock:
            row = self.db.execute('SELECT amount, at FROM gateway_bonus WHERE id=?', (kind,)).fetchone()
        if row is None or not 0 <= self.clock() - float(row[1]) <= self.GATEWAY_BONUS_SECONDS:
            return 0
        return int(row[0])

    def mirror_gateway_bonus(self, kind: str, amount: Any) -> None:
        """Profit-indexed compute (Sept 23, 2026). The gateway raises its OpenAI month by a share of
        the verified profit on the real accounts, which it reads itself (gateway/lib/equity.mjs), and
        reports the raise in `/v1/health` (`frontier.cap_usd` less `frontier.base_cap_usd`). The
        burst's OpenAI line is raised by exactly that raise and never more, so compute that profit
        bought can be spent; it falls when the raise falls, and lapses when the gateway has not been
        read for `GATEWAY_BONUS_SECONDS`. Spend already committed is never reset."""
        if kind != 'openai':
            raise ValueError('only the OpenAI month is indexed to profit')
        value = min(micro(amount), micro('1000'))
        with self.lock:
            row = self.db.execute('SELECT amount, at FROM gateway_bonus WHERE id=?', (kind,)).fetchone()
            if row is not None and int(row[0]) == value and 0 <= self.clock() - float(row[1]) < 300:
                return  # unchanged and fresh: the stamp is renewed every five minutes, not every read
            self.db.execute('INSERT INTO gateway_bonus VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET amount=excluded.amount, at=excluded.at',
                            (kind, value, self.clock()))

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

    def _sums(self, kind: str, after_row: int = 0) -> tuple[int, int, int, int]:
        """Over the commitments after `after_row`: (the settled costs `kind`'s meter records too,
        the settled costs of calls it would record but made before it covers (`covers_from`),
        the settled costs it never records, the holds still pending).

        A line is max(the first, measured) + the other three. Only the first may hide inside the
        meter: `max(settled, measured)` counts a cost once only if the meter counts every call in
        `settled`, and a monthly meter whose coverage began after some of them (its first month
        after the burst's calls, or a month it could not close) does not."""
        prefix = self.METER_COVERS.get(kind, "")
        month = self.db.execute("SELECT covers_from FROM meter_month WHERE id=?", (kind,)).fetchone()
        since = float(month[0]) if month else 0.0  # every `created` is epoch seconds (-inf scans 2.4x slower)
        inside, before, other, pending = self.db.execute(
            "SELECT COALESCE(SUM(CASE WHEN substr(id,1,?)=? AND created>=? THEN cost END),0),"
            "COALESCE(SUM(CASE WHEN substr(id,1,?)=? AND created<? THEN cost END),0),"
            "COALESCE(SUM(CASE WHEN substr(id,1,?)=? THEN NULL ELSE cost END),0),"
            "COALESCE(SUM(CASE WHEN cost IS NULL THEN reserved ELSE 0 END),0) "
            "FROM commitments WHERE kind=? AND rowid>?",
            (len(prefix), prefix, since, len(prefix), prefix, since, len(prefix), prefix, kind, after_row)).fetchone()
        return int(inside), int(before), int(other), int(pending)

    def _measured(self, kind: str, burst: Mapping[str, Any] | None) -> int:
        """What `kind`'s meter has counted since the burst's baseline (since the meter began, with no
        burst). Sail's baseline is its reading at the burst's activation. OpenAI had no meter then
        (Sept 21, 2026): its baseline is the meter's own, the zero of the first gateway month it read
        (`observe_month`), which began before every burst call that month covers. It counts that
        month's calls made before the burst too, so it can only overcount; a meter with neither
        counts nothing.

        A monthly meter never counts from before `covers_from`: when a month the gateway could not
        close moved it forward, what the meter carried until then (`meter_month.base`) is left out,
        because the House's settled costs of those calls are added apart (`_sums` `before`). Counting
        both read that month twice (the Sept 24, 2026 review: $10 of September became $20)."""
        row = self.db.execute('SELECT baseline, latest FROM meter WHERE id=?', (kind,)).fetchone()
        if row is None:
            return 0
        baseline = burst['meters'].get(kind) if burst else row['baseline']
        month = self.db.execute('SELECT base FROM meter_month WHERE id=?', (kind,)).fetchone()
        if baseline is None:
            baseline = row['baseline'] if month else row['latest']
        if month is not None:
            baseline = max(int(baseline), int(month['base'] or 0))
        return max(0, int(row['latest']) - int(baseline))

    def _line(self, kind: str, burst: Mapping[str, Any]) -> dict[str, int]:
        """`kind`'s burst line in micro-dollars: its cap, its parts (`_sums`, `_measured`) and what they
        use, max(settled, measured) + before + unmetered + pending. One scan of the commitments."""
        inside, before, other, pending = self._sums(kind, burst['first_row'])
        measured = self._measured(kind, burst)
        return {'cap': micro(burst['policy']['caps_usd'].get(kind, '0')), 'settled': inside, 'measured': measured,
                'before': before, 'unmetered': other, 'pending': pending,
                'used': max(inside, measured) + before + other + pending}

    def _burst_used(self, kind: str, burst: Mapping[str, Any]) -> int:
        return self._line(kind, burst)['used']

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
            return bool(row and not row[1] and 0 <= self.clock() - row[0] <= self.METER_FRESH_SECONDS)

    def _used(self, kind: str) -> int:
        settled, before, other, pending = self._sums(kind)
        measured = self._measured(kind, None)
        # Account meter already includes settled model costs. Do not add them twice. Including
        # unresolved holds again is intentionally conservative when vendor billing arrives first.
        # A settled cost the meter does not record (Jev's beside OpenAI's month, or a call made
        # before a monthly meter covers) is added apart (`_sums`).
        return self.external.get(kind, 0) + max(settled, measured) + before + other + pending

    def remaining(self, kind: str) -> Decimal:
        """What `kind` may still commit: the House's own line, and never more than the provider's own
        monthly line has left while that line has a fresh reading (`_provider_left`)."""
        with self.lock:
            burst = self.burst()
            if burst:
                cap = micro(burst['policy']['caps_usd'].get(kind, '0'))
                line = max(0, cap - self._burst_used(kind, burst)) if self.running() else 0
            else:
                line = max(0, self.caps[kind] - self._used(kind))
            left = self._provider_left(kind)
            return Decimal(line if left is None else min(line, left)) / UNIT

    def _provider_left(self, kind: str) -> int | None:
        """What `kind`'s provider line has left now, in micro-dollars: its monthly cap less its spend at
        the last fresh reading (the gateway's frontier month for OpenAI: `/v1/health` `frontier.cap_usd`
        less `frontier.spent_usd`), less what the House has committed on that line since the reading
        (its settled costs, and the holds of calls that may reach it since). None without a reading
        younger than `METER_FRESH_SECONDS`: the House's own line stands alone then, and a metered
        kind's reservations are refused anyway (`ready`).

        Why (Sept 24, 2026 review): the House's OpenAI line is raised by owner top-ups and settles at
        the House's own prices, and with the phantom holds absorbed it read about $70-79 above the
        gateway's month, which is aligned to what the owner funded. Every reader of `remaining` --
        reservations, the pacer, the agents' credit pool, the tier, health -- would have planned on
        money that was never funded. The month itself only refuses at its cap (402); this is the
        House never reading more than that. History is not rewritten: no top-up is lowered and no
        settled row changes, so the line comes back the moment the gateway cannot be read."""
        row = self.db.execute("SELECT cap, spent, reading_row, at FROM meter_month WHERE id=?", (kind,)).fetchone()
        if row is None or row["cap"] is None or row["spent"] is None:
            return None
        if not 0 <= self.clock() - float(row["at"]) <= self.METER_FRESH_SECONDS:
            return None
        prefix = self.METER_COVERS.get(kind, "")
        since = self.db.execute(
            "SELECT COALESCE(SUM(COALESCE(cost, reserved)),0) FROM commitments WHERE kind=? AND rowid>? AND substr(id,1,?)=?",
            (kind, int(row["reading_row"] or 0), len(prefix), prefix)).fetchone()[0]
        return max(0, int(row["cap"]) - int(row["spent"]) - int(since))

    def meter_reader(self, kind: str, read: Callable[[], Any]) -> None:
        """How `kind`'s meter is read, for a reservation that finds the last reading a minute old.

        The House reads OpenAI's meter, the gateway's frontier month, on every tick (`FrontierMonth`,
        league/frontier.py). A reservation made by a background job while one tick runs long would
        otherwise meet a reading over 180 s old and be refused (`ready`); Sail's transport reads its
        own balance before each reservation for the same reason (league/funded.py)."""
        self._readers[kind] = read

    def _freshen(self, kind: str) -> None:
        read = self._readers.get(kind)
        if read is None:
            return
        with self.lock:
            row = self.db.execute("SELECT checked FROM meter_health WHERE id=?", (kind,)).fetchone()
        if row is not None and 0 <= self.clock() - float(row[0]) < self.METER_READ_SECONDS:
            return
        try:
            read()  # outside the lock: it may wait on the network, and it feeds this object
        except Exception:  # noqa: BLE001 - an unread meter refuses below, as it would have anyway
            pass

    def reserve(self, ident: str, campaign: str, amount: Any) -> bool:
        held = micro(amount)
        rule = self.policy["campaigns"][campaign]
        kind = rule["kind"]
        self._freshen(kind)
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

    def observe_month(self, kind: str, month: str, spent: Any, *, settled: Any = None, cap: Any = None,
                      previous: Mapping[str, Any] | None = None, evidence: Mapping[str, Any] | None = None) -> bool:
        """One reading of a provider's MONTHLY meter, the gateway's frontier month for OpenAI
        (`/v1/health` `frontier`: `month`, `spent_usd`, `settled_usd`, `cap_usd`, `previous`). Sept 24, 2026.

        `cap` is the month's cap in force. With `spent`, it is what the month itself has left, and while
        the reading is fresh the House's line never reads above that (`remaining`, `_provider_left`).

        The month's `spent_usd` is not monotone: a call is reserved at its worst case and settled at
        what it cost, so the month falls whenever a call settles below its worst case, and it starts
        at zero on the 1st. Fed to `observe_spend` it would latch the meter failed within a minute.
        So the meter is fed a cumulative figure that never falls: the month's highest reading plus
        the finals of the months before it (`carried`). A final is the gateway's own (`previous`),
        or, when the gateway cannot report it, the House's last reading of that month -- and then the
        charges of that month's last minutes are unknown, so the months before stop being covered
        (`covers_from` moves to the new month) and the check below starts again. A highest reading
        can include calls in flight at their worst case, so the figure can only overcount.

        The meter's baseline is zero at the start of the first month read (`covers_from`): every
        gateway call since then is inside the figure, including every hold the House made that
        month, so a hold may be absorbed into it (`absorb_stale`) only if it was made since then.
        That month began before the burst's calls it covers, so it also counts that month's earlier
        calls: again only an overcount.

        "The meter must dominate the settled sum" is checked from an ANCHOR, not from the burst's
        start: the House booked OpenAI calls at its ceiling prices until Sept 23, 2026, so its
        settled sum since the burst ($495.35 on Sept 24) was above the gateway's whole September
        ($402.96) and could never be dominated. At the first reading that carries the gateway's
        `settled_usd` (spent less the holds of calls still unanswered), the anchor records that figure
        and the last commitment's row; after it, the House settles every answered call at the
        gateway's own metered cost, so the gateway's settled figure must grow by at least what the
        House settles on rows after the anchor. The anchor is taken again in each new month.
        `meter_reconciliations` keeps the meter's start, its anchors and every month it closes.

        Returns False, changing nothing, for a reading of a month older than one already read. A
        reading the meter cannot take raises ValueError. Neither refreshes `meter_health`, so a
        gateway that cannot be read stops the kind's reservations after 180 s (`ready`); nothing
        here latches."""
        if not isinstance(month, str) or not MONTH.fullmatch(month):
            raise ValueError("a meter month is YYYY-MM")
        try:
            high_now = micro(spent)
            settled_now = None if settled is None else micro(settled)
            cap_now = None if cap is None else micro(cap)
            final = None
            if previous:
                name = previous.get("month")
                if not isinstance(name, str) or not MONTH.fullmatch(name) or name >= month:
                    raise ValueError("the previous month must be an earlier YYYY-MM")
                final = (name, micro(previous.get("spent_usd")),
                         None if previous.get("settled_usd") is None else micro(previous.get("settled_usd")))
        except (ArithmeticError, TypeError, AttributeError) as exc:
            raise ValueError(f"an unreadable meter reading ({type(exc).__name__})") from None
        now = self.clock()
        extra = dict(evidence or {})
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                row = self.db.execute("SELECT * FROM meter_month WHERE id=?", (kind,)).fetchone()
                notes: list[tuple[str, dict[str, Any]]] = []
                if row is None:
                    if self.db.execute("SELECT 1 FROM meter WHERE id=?", (kind,)).fetchone():
                        raise ValueError(f"{kind} already has an account meter; a monthly one cannot replace it")
                    state = {"month": month, "high": high_now, "carried": 0, "settled_high": settled_now,
                             "settled_carried": 0, "covers_from": month_start(month),
                             "anchor_at": None, "anchor_row": None, "anchor_settled": None, "base": 0}
                    self.db.execute("INSERT INTO meter VALUES(?,?,?)", (kind, 0, high_now))
                    burst = self.burst()
                    inside, before, other, pending = self._sums(kind, int(burst["first_row"]) if burst else 0)
                    notes.append(("month-meter", {
                        "cause": "the provider is metered by the gateway's month from here on; the meter counts from the month's start",
                        "month": month, "spent_micro_usd": high_now, "settled_micro_usd": settled_now,
                        "covers_from": state["covers_from"], "house_burst_settled_micro_usd": inside + before,
                        "house_burst_unmetered_settled_micro_usd": other, "house_burst_pending_micro_usd": pending, **extra}))
                elif month < row["month"]:
                    self.db.execute("COMMIT")
                    return False
                elif month == row["month"]:
                    state = dict(row)
                    state["high"] = max(int(row["high"]), high_now)
                    if settled_now is not None:
                        state["settled_high"] = max(int(row["settled_high"] or 0), settled_now)
                else:
                    state = dict(row)
                    closed = final is not None and final[0] == row["month"]
                    old_high = max(int(row["high"]), final[1]) if closed else int(row["high"])
                    old_settled = int(row["settled_high"] or 0)
                    if closed and final[2] is not None:
                        old_settled = max(old_settled, final[2])
                    state["carried"] = int(row["carried"]) + old_high
                    state["settled_carried"] = int(row["settled_carried"]) + old_settled
                    if final is not None and row["month"] < final[0]:
                        # A month the House never read: its final is counted, the months between are not.
                        state["carried"] += final[1]
                        state["settled_carried"] += final[2] or 0
                    if not closed:
                        # The months before are no longer covered, and what the meter carried for them
                        # is left out of what it measures from here (`_measured`): the House's own
                        # settled costs of those calls are added apart (`_sums` `before`).
                        state["covers_from"] = month_start(month)
                        state["base"] = state["carried"]
                    # The check starts again in every new month: a call in flight across midnight is
                    # refused its settle by the gateway (its month has ended) while the House may still
                    # settle it, which would set the two sides apart for good.
                    state["anchor_at"] = state["anchor_row"] = state["anchor_settled"] = None
                    state.update(month=month, high=high_now, settled_high=settled_now)
                    notes.append((f"rollover:{row['month']}:{month}", {
                        "cause": "a new month: the last one's final is carried", "from": row["month"], "to": month,
                        "high_micro_usd": int(row["high"]), "final_reported": closed,
                        "final_micro_usd": old_high, "carried_micro_usd": state["carried"],
                        "covers_from": state["covers_from"]}))
                # What the month itself has left at this reading, and the last commitment it can have
                # seen: the House reserves before it calls the gateway, so a later row is not in it.
                last_row = int(self.db.execute("SELECT COALESCE(MAX(rowid),0) FROM commitments").fetchone()[0])
                state.update(cap=cap_now, spent=high_now, reading_row=last_row)
                if state["anchor_at"] is None and state["settled_high"] is not None:
                    state["anchor_at"] = now
                    state["anchor_row"] = last_row
                    state["anchor_settled"] = int(state["settled_carried"]) + int(state["settled_high"])
                    inside, before, other, pending = self._sums(kind)
                    notes.append(("anchor", {
                        "cause": "from here the gateway's settled figure must grow by at least what the House settles on later rows",
                        "month": month, "row": state["anchor_row"], "gateway_settled_micro_usd": state["anchor_settled"],
                        "house_settled_micro_usd": inside + before, "house_unmetered_settled_micro_usd": other,
                        "house_pending_micro_usd": pending}))
                state.update(id=kind, at=now)
                columns = ("id", "month", "high", "carried", "settled_high", "settled_carried", "covers_from", "anchor_at",
                           "anchor_row", "anchor_settled", "at", "cap", "spent", "reading_row", "base")
                self.db.execute(
                    f"INSERT INTO meter_month({','.join(columns)}) VALUES({','.join('?' * len(columns))}) "
                    "ON CONFLICT(id) DO UPDATE SET " + ", ".join(f"{c}=excluded.{c}" for c in columns[1:]),
                    tuple(state.get(c) if c != "base" else int(state.get("base") or 0) for c in columns))
                self.db.execute("UPDATE meter SET latest=MAX(latest, ?) WHERE id=?", (int(state["carried"]) + int(state["high"]), kind))
                self.db.execute("INSERT INTO meter_health VALUES(?,?,0) ON CONFLICT(id) DO UPDATE SET checked=excluded.checked",
                                (kind, now))
                for name, record in notes:
                    self.db.execute("INSERT OR IGNORE INTO meter_reconciliations VALUES(?,?,?,?)",
                                    (f"{kind}:{name}:{int(now)}", kind, now, canonical(record)))
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
        return True

    def month_meter(self, kind: str) -> dict[str, Any] | None:
        """The monthly meter's state (`observe_month`), in dollars; None when `kind` has none."""
        with self.lock:
            row = self.db.execute("SELECT * FROM meter_month WHERE id=?", (kind,)).fetchone()
        if row is None:
            return None
        settled = None if row["settled_high"] is None and not row["settled_carried"] else \
            int(row["settled_carried"]) + int(row["settled_high"] or 0)
        return {"month": row["month"], "high_usd": usd(row["high"]), "carried_usd": usd(row["carried"]),
                "total_usd": usd(int(row["carried"]) + int(row["high"])),
                "settled_total_usd": None if settled is None else usd(settled),
                # The month's own line at the last reading: its cap in force and its spend then.
                "cap_usd": None if row["cap"] is None else usd(row["cap"]),
                "spent_usd": None if row["spent"] is None else usd(row["spent"]),
                "base_usd": usd(int(row["base"] or 0)),
                "covers_from": row["covers_from"], "read_at": row["at"],
                "anchor": None if row["anchor_at"] is None else
                {"at": row["anchor_at"], "row": row["anchor_row"], "settled_usd": usd(row["anchor_settled"])}}

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
        left while the account held $116.

        OpenAI's holds (Sept 24, 2026) are absorbed into the gateway's month instead, by
        `_absorb_into_month`: only the calls that month records (`METER_COVERS`), only those made
        since the meter covers (`covers_from`), and only while the gateway's settled figure has grown
        by at least what the House settled since the meter's anchor (`observe_month`)."""
        if kind not in self.policy.get("meter_required", []):
            raise ValueError(f"{kind} has no account meter to absorb holds into")
        cutoff = self.clock() - float(older_than_seconds)
        with self.lock:
            if not self.ready(kind):
                return {"absorbed": 0, "usd": "0", "why": "the meter is not healthy"}
            if self.db.execute("SELECT 1 FROM meter_month WHERE id=?", (kind,)).fetchone():
                return self._absorb_into_month(kind, cutoff, dict(evidence or {}))
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

    def _absorb_into_month(self, kind: str, cutoff: float, evidence: dict[str, Any]) -> dict[str, Any]:
        """Release OpenAI holds into the gateway's month (Sept 24, 2026); the caller holds the lock.

        Why their charge is already counted: the House reserves a call's worst case here, then asks
        the gateway, which reserves the same worst case on its month before it calls the provider
        and settles there at what the provider reports -- or keeps the whole worst case when the
        call timed out, failed or came back unreadable, or when the gateway itself died mid-call.
        When the House's own request dies (its 600 s read, a restart, a dropped connection) nothing
        settles the hold here, but the month has already counted the call. A call that never reached
        the gateway was never billed. So a hold made while the month covers, older than any call's
        life, counts its call a second time; absorbing it leaves the month (`_measured`) counting it
        once. The check before any release -- the gateway's settled figure has grown by at least
        what the House settled on rows after the anchor, and something has settled since -- is
        what shows the month is still counting the House's calls."""
        now = self.clock()
        prefix = self.METER_COVERS.get(kind, "")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            month = self.db.execute("SELECT * FROM meter_month WHERE id=?", (kind,)).fetchone()
            if month["anchor_at"] is None:
                self.db.execute("COMMIT")
                return {"absorbed": 0, "usd": "0", "retry": True,
                        "why": "the gateway reports no settled figure to check its month against yet"}
            since = int(self.db.execute(
                "SELECT COALESCE(SUM(cost),0) FROM commitments WHERE kind=? AND rowid>? AND substr(id,1,?)=? AND cost IS NOT NULL",
                (kind, int(month["anchor_row"]), len(prefix), prefix)).fetchone()[0])
            growth = int(month["settled_carried"]) + int(month["settled_high"] or 0) - int(month["anchor_settled"])
            check = {"anchor_at": month["anchor_at"], "anchor_row": int(month["anchor_row"]),
                     "house_settled_since_micro_usd": since, "gateway_settled_growth_micro_usd": growth}
            shown = {"since_anchor_usd": usd(since), "gateway_growth_usd": usd(max(growth, 0)), "anchor_at": month["anchor_at"]}
            if since <= 0:
                self.db.execute("COMMIT")
                return {"absorbed": 0, "usd": "0", "retry": True, "check": shown,
                        "why": "no call has settled since the meter's anchor, so there is nothing yet to check the month against"}
            if growth < since:
                self.db.execute("COMMIT")
                return {"absorbed": 0, "usd": "0", "check": shown,
                        "why": "the gateway's settled figure has grown less than what the House settled since the anchor"}
            burst = self.burst()
            covered, before, other, pending = self._sums(kind, int(burst["first_row"]) if burst else 0)
            measured = self._measured(kind, burst) if burst else 0
            rows = self.db.execute(
                "SELECT c.id, c.reserved, c.created FROM commitments c LEFT JOIN responses r ON r.commitment = c.id "
                "WHERE c.kind=? AND c.cost IS NULL AND c.created < ? AND c.created >= ? AND substr(c.id,1,?)=? AND r.id IS NULL",
                (kind, cutoff, float(month["covers_from"]), len(prefix), prefix)).fetchall()
            record = {"cause": "a hold with no answer, older than any call's life, whose call the gateway's month already counts",
                      "meter": "the gateway's frontier month", "month": month["month"],
                      "meter_total_micro_usd": int(month["carried"]) + int(month["high"]),
                      "covers_from": float(month["covers_from"]), "measured_micro_usd": measured,
                      "settled_micro_usd": covered, "settled_before_meter_micro_usd": before,
                      "unmetered_settled_micro_usd": other, "check": check, **evidence}
            for ident, reserved, created in rows:
                self.db.execute("UPDATE commitments SET cost=0 WHERE id=? AND cost IS NULL", (ident,))
                self.db.execute("INSERT OR IGNORE INTO cost_reconciliations VALUES(?,?,?,?)",
                                (f"absorbed:{ident}", ident,
                                 canonical({**record, "reserved_micro_usd": int(reserved), "created": float(created)}), now))
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        return {"absorbed": len(rows), "usd": usd(sum(int(r[1]) for r in rows)), "measured_usd": usd(measured),
                "settled_usd": usd(covered), "check": shown}

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
            # Each burst line once (one scan a kind), shared by the accounts, the burst and the meters,
            # and bounded by the provider's own month as `remaining` is (`_provider_left`).
            lines = {k: self._line(k, burst) for k in extra} if burst else {}
            running = self.running()
            bound = {k: self._provider_left(k) for k in lines}
            house = {k: max(0, v['cap'] - v['used']) if running else 0 for k, v in lines.items()}
            left = {k: str(Decimal(v if bound[k] is None else min(v, bound[k])) / UNIT) for k, v in house.items()}
            return {"phase": self.policy["phase"], "started": self.started, "ends": self.ends,
                "running": self.running(), "cap_usd": usd(micro(self.policy['total_cap_usd']) + sum(micro(v) for v in extra.values())),
                "foundation_cap_usd": self.policy['total_cap_usd'],
                "allow_new_live_capital": self.policy["allow_new_live_capital"],
                "live_pilot": self.live_pilot(),
                "live_trading": self.live_trading(),
                "effective_research_deadline": (None if self.live_trading() and self.live_trading()['active']
                                                else min(self.ends, burst['ends']) if burst else self.ends),
                "accounts": {kind: {"cap_usd": usd(cap + micro(extra.get(kind, '0'))), "committed_usd": usd(self._used(kind)),
                    "external_reserve_usd": usd(self.external.get(kind, 0)),
                    "remaining_usd": left[kind] if kind in left else str(self.remaining(kind))}
                    for kind, cap in self.caps.items()},
                "meters_ready": {kind: self.ready(kind) for kind in self.caps},
                "meters": {kind: self._meter_report(kind, lines.get(kind), left.get(kind), house.get(kind), bound.get(kind))
                           for kind in self.policy.get("meter_required", [])},
                "pending_calls": self.db.execute("SELECT COUNT(*) FROM commitments WHERE cost IS NULL").fetchone()[0],
                "reservation_breaches": self.db.execute("SELECT COUNT(*) FROM commitments WHERE cost>reserved").fetchone()[0],
                "burst": ({'id': burst['id'], 'started': burst['started'], 'ends': burst['ends'],
                    'running': burst['started'] <= self.clock() < min(self.ends, burst['ends']), 'caps_usd': burst['policy']['caps_usd'],
                    'committed_usd': {k: usd(v['used']) for k, v in lines.items()},
                    'remaining_usd': left,
                    'note': 'Additional owner research allowance. Original phase and commitments are retained; expiry closes new paid work.'} if burst else None),
                "note": "Commitments include unresolved calls and external reserves; this is not a vendor invoice."}

    def _meter_report(self, kind: str, line: Mapping[str, int] | None, left: str | None,
                      house: int | None = None, bound: int | None = None) -> dict[str, Any]:
        """One metered provider in `health.json` `campaign.meters`: whether its meter is fresh, and
        the arithmetic of its burst line: house_line = cap - max(settled, measured) - before_meter -
        unmetered settled - pending (`_sums`; Sept 24, 2026), and remaining = the smaller of that and
        what the provider's own month has left at a fresh reading (`provider_left_usd`, null without
        one; `_provider_left`)."""
        health = self.db.execute("SELECT checked, failed FROM meter_health WHERE id=?", (kind,)).fetchone()
        out: dict[str, Any] = {"ready": self.ready(kind), "checked_at": health["checked"] if health else None,
                               "failed": bool(health["failed"]) if health else False}
        if line is not None:
            out["line"] = {"cap_usd": usd(line["cap"]), "settled_usd": usd(line["settled"]),
                           "measured_usd": usd(line["measured"]), "before_meter_usd": usd(line["before"]),
                           "unmetered_settled_usd": usd(line["unmetered"]), "pending_usd": usd(line["pending"]),
                           "house_line_usd": None if house is None else usd(house),
                           "provider_left_usd": None if bound is None else usd(bound),
                           "remaining_usd": left}
        month = self.month_meter(kind)
        if month is not None:
            out["month"] = month
        return out

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
