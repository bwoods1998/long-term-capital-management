"""The broker gateway: the only path from a desk's intention to a venue.

A desk can never reach a broker. It emits an `OrderIntent`; the gateway assembles a `RiskContext`
from the desk's sub-ledger, the venue's quote and capabilities, the floor's aggregate book and the
kill switch, runs the deterministic `RiskEngine`, publishes the decision, and only then submits.

Every step is an event, and every event id is derived from something durable (the intent id, the
order id and its status, the fill id) so a crash between the submission and the log never
duplicates an order and never loses one.

Three failure modes are handled explicitly, because they are the ones that lose money:

* `RejectedOrder` -- the venue said no. A terminal `broker.order` records why.
* `VenueUnavailable` -- nothing was sent. A terminal `broker.order` records the failure so the
  deferred intent can be released rather than hidden forever.
* `UnknownOutcome` -- the venue may or may not hold the order. The order is written with status
  `unknown`, the desk is blocked from proposing anything else, and only `reconcile()` can clear
  it. Retrying blindly here is how one order becomes two.

`desk.intent` and `broker.order` events are written private ("deferred") so nobody can trade ahead
of the floor. `release_deferred_events()` names the ones whose order has reached a terminal state;
the publisher sends exactly those.

One model call stands between the engine and a live venue. When a desk trading real money passes
every deterministic rule, `critic.LiveOrderCritic` reads the intent against the desk's own words
and can `block` it (a second `risk.decision`, no submission). It fails open by construction: a
provider error, a timeout or an unusable answer is an `ops.alert` and the order proceeds on the
engine alone. Shadow desks never reach it: no money is at stake, so there is nothing to protect.

**Shadow routing.** A desk whose capital mode is `shadow` proposes exactly as a live desk does --
same intent, same risk engine, same decision event -- and the approved order is then routed to the
`shadow` book instead of to a venue. Nothing is sent anywhere. The order, its fills and the mark
that follows are recorded with `shadow: true` in their payloads and on the `broker:shadow` stream,
while the instrument keeps the real venue it would have traded on, so the fill is priced and
charged exactly as the real one would have been.
"""

from __future__ import annotations

import dataclasses
import hashlib
import re
import threading
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping

from .broker import (
    TERMINAL_STATUSES,
    Broker,
    Fill,
    Instrument,
    Order,
    OrderIntent,
    RejectedOrder,
    UnknownOutcome,
    VenueUnavailable,
    money,
    text,
)
from .committee import capital_mode, promoted_desks
from .events import Event, EventLog, canonical, now_iso
from .ledger import DeskLedger, floor_totals, iso_time, parse_iso, position_walk
from .manifest import DeskManifest
from .risk import Breaker, Decision, RiskContext, RiskEngine

ZERO = Decimal(0)
ONE = Decimal(1)

#: How far behind its cursor a fill sweep reads again. Fills are not ingested in the order they
#: are stamped (a shadow fill carries its book's clock, a worker's sweep can run before the tick's),
#: so a sweep that asked only for fills after the newest one it saw skipped older ones for good
#: (Sept 16, 2026 audit). `_seen_fills` keeps the overlap from writing anything twice.
FILL_LOOKBACK_SECONDS = 600


def _stamp_minus(stamp: "str | None", seconds: int) -> "str | None":
    """`stamp` moved `seconds` earlier, in the log's shape; unreadable stamps are kept."""
    if stamp is None:
        return None
    try:
        from datetime import timedelta

        return iso_time(parse_iso(stamp) - timedelta(seconds=seconds))
    except Exception:
        return stamp

#: The routing key of the scoring book. A shadow desk's orders go here and no further.
SHADOW_VENUE = "shadow"

#: Asset classes whose orders depend on a regular-hours session.
SESSION_CLASSES = ("equity", "option")

#: The log's (and the site's) timestamp shape. A venue that reports anything else keeps its own
#: stamp inside the payload while the event carries one the publisher will accept.
AT_FORMAT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


def _stamp(value: Any, fallback: str) -> str:
    return value if isinstance(value, str) and AT_FORMAT.match(value) else fallback


def _log_stamp(value: Any, fallback: str) -> str:
    """A venue timestamp rewritten into the log's millisecond shape, else `fallback`.

    `_stamp` only accepts a stamp that is already in the log's shape; the venues emit
    seconds-precision ISO, so a settlement's own time needs converting rather than discarding.
    """
    if isinstance(value, str) and AT_FORMAT.match(value):
        return value
    try:
        return iso_time(parse_iso(str(value)))
    except Exception:
        return fallback


def _max_stamp(current: "str | None", candidate: str) -> str:
    """The later of two ISO stamps; a cursor never moves backwards."""
    return candidate if current is None or candidate > current else current


def _key_of(instrument: Any) -> str | None:
    """The `Instrument.key` of a logged instrument dict, or None when it cannot be read."""
    if not isinstance(instrument, Mapping):
        return None
    try:
        return Instrument.from_dict(dict(instrument)).key
    except Exception:
        return None


def _seconds_between(start: "str | None", end: str) -> float:
    """Seconds from `start` to `end` (ISO instants); a missing or unreadable start is far past."""
    if not start:
        return float("inf")
    try:
        from datetime import datetime, timezone

        def parse(text: str) -> datetime:
            text = text.replace("Z", "+00:00")
            return datetime.fromisoformat(text).astimezone(timezone.utc)

        return (parse(end) - parse(start)).total_seconds()
    except (TypeError, ValueError):
        return float("inf")


def _hours_between(start: "str | None", end: str) -> str | None:
    """Hours from `start` to `end` to one decimal, or None when the open is unknown."""
    if not start:
        return None
    try:
        seconds = (parse_iso(end) - parse_iso(start)).total_seconds()
    except Exception:
        return None
    return format(
        (Decimal(int(round(seconds))) / Decimal(3600)).quantize(Decimal("0.1")), "f"
    )


class GatewayError(RuntimeError):
    """The gateway refused to act. Never raised for a risk rejection, which is a decision."""


class DeskBlocked(GatewayError):
    """The desk has an unresolved order of unknown status and must reconcile first."""


def _fees(value: Decimal) -> Decimal:
    """A fee share to the hundred-millionth of a dollar: a third of a cent is not 28 digits."""
    return value.quantize(Decimal("0.00000001")).normalize() if value else ZERO


def _short(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


class Gateway:
    """Risk-checked, idempotent routing between desks and venues."""

    def __init__(
        self,
        log: EventLog,
        risk_engine: RiskEngine,
        brokers: Mapping[str, Broker],
        ledgers: Mapping[str, DeskLedger],
        data: Any = None,
        manifests: Mapping[str, DeskManifest] | Iterable[DeskManifest] | None = None,
        clock=time.time,
        kill_switch_path: str | Path | None = None,
        floor_max_daily_loss_pct: Any = "0.02",
        critic: Any = None,
        event_rules: Mapping[str, Any] | None = None,
    ):
        self.log = log
        self.risk_engine = risk_engine
        #: `critic.LiveOrderCritic` or None. Consulted only for desks on live capital.
        self.critic = critic
        self.brokers = dict(brokers)
        self.ledgers = dict(ledgers)
        self.data = data
        if manifests is None:
            self.manifests: dict[str, DeskManifest] = {}
        elif isinstance(manifests, Mapping):
            self.manifests = dict(manifests)
        else:
            self.manifests = {m.id: m for m in manifests}
        self.clock = clock
        self.kill_switch_path = Path(kill_switch_path) if kill_switch_path else None
        self.floor_max_daily_loss_pct = money(floor_max_daily_loss_pct)
        #: Firm-wide event rules for the risk context: min_event_price, max_event_market_pct,
        #: max_event_market_floor_pct (`risk.rule_event_longshot`, `risk.rule_event_market_cap`).
        self.event_rules = {k: money(v) for k, v in dict(event_rules or {}).items()
                            if k in ("min_event_price", "max_event_market_pct", "max_event_market_floor_pct") and v is not None}
        # Concurrency (Sept 16, 2026 audit). Strategy workers, sessions, feed threads and the tick
        # all call the gateway at once. `_book_lock` guards the in-memory book below (orders, the
        # venue and intent maps, decisions, seen fills, blocked desks, the scan cursor, what is in
        # flight) and is held over memory and the local log only, never over a venue call. A
        # desk's lock makes one proposal's check-and-reserve atomic against another's; a venue's
        # ingest lock does the same for fetch-attribute-append-cursor. Lock order, outermost
        # first: desk or ingest lock -> `_book_lock` -> a DeskLedger's lock -> the EventLog's.
        self._book_lock = threading.RLock()
        self._desk_locks: dict[str, threading.Lock] = {}
        self._ingest_locks: dict[str, threading.Lock] = {}
        #: desk_id -> intent_id -> what an approved order not yet recorded and swept commits:
        #: side, instrument key, quantity, notional. `risk_context` counts it.
        self._inflight: dict[str, dict[str, dict[str, Any]]] = {}
        #: venue -> submissions whose venue order id is not known yet. A fill on that venue the
        #: floor cannot place may be theirs, so it waits for the next sweep.
        self._submitting: dict[str, int] = {}
        #: True when the owner (the service) rewrites `manifests` itself as promotions land. The
        #: capital mode is then read from the manifest, which moves only once the sleeve is set
        #: up, and a desk whose logged mode differs is mid-move and proposes nothing until it has.
        self.manifests_carry_mode = False
        #: desk_id -> order_id that could not be confirmed.
        self.blocked_desks: dict[str, str] = {}
        #: True once a reconciliation found a difference the humans have not cleared.
        self.reconciliation_mismatch = False
        self._orders: dict[str, dict[str, Any]] = {}
        self._intent_orders: dict[str, str] = {}
        #: The venue's id for each order -> the floor's. A swept fill names the venue's id and
        #: nothing else; without this map it belonged to no desk (Sept 16, 2026: seven live
        #: Kalshi positions that no ledger held).
        self._venue_orders: dict[str, str] = {}
        self._unattributed: set[str] = set()
        self._fill_cursor: dict[str, str | None] = {}
        self._settlement_cursor: dict[str, str | None] = {}
        self._seen_fills: set[str] = set()
        self._scan_seq = 0
        self._decisions: dict[str, bool] = {}
        # leap: exits. `exits.ExitBook` when the floor enforces exit plans; the service sets it.
        self.exits: Any = None
        self._load()

    # ------------------------------------------------------------------ log folding
    def _load(self) -> None:
        """Rebuild the order book and the deferred-release view from the log."""
        with self._book_lock:
            self._load_locked()

    def _load_locked(self) -> None:
        while True:
            batch = self.log.read(after=self._scan_seq, limit=2000)
            if not batch:
                return
            for event in batch:
                if not isinstance(event.seq, int) or event.seq <= self._scan_seq:
                    continue
                self._scan_seq = event.seq
                if event.kind == "broker.order":
                    self._absorb_order_event(event)
                elif event.kind == "risk.decision":
                    intent_id = event.payload.get("intent_id")
                    if isinstance(intent_id, str):
                        # Last decision wins: the critic can write a second, blocking decision
                        # after the engine approved, and that one is the one that stands.
                        self._decisions[intent_id] = bool(event.payload.get("approved"))
                elif event.kind == "broker.fill":
                    fill_id = event.payload.get("fill_id") or event.payload.get("id")
                    if isinstance(fill_id, str):
                        self._seen_fills.add(fill_id)
            if len(batch) < 2000:
                return

    def _absorb_order_event(self, event: Event) -> None:
        payload = event.payload
        order_id = payload.get("order_id")
        if not isinstance(order_id, str):
            return
        row = self._orders.setdefault(order_id, {"order_id": order_id})
        # A polled order row comes back from the venue without the desk, the intent or the
        # purpose (the venue never knew them). An empty value never erases a known one: for
        # twelve hours on Sept 16, 2026 every poll blanked `desk_id`, so the desks' own resting
        # orders vanished from `open_orders`, strategies re-quoted every run, and venue fills
        # went unattributed.
        row.update({k: v for k, v in payload.items() if v is not None and not (v == "" and row.get(k))})
        row["status"] = payload.get("status", row.get("status", "new"))
        intent_id = payload.get("intent_id")
        if isinstance(intent_id, str):
            self._intent_orders[intent_id] = order_id
        venue_order_id = payload.get("venue_order_id")
        if isinstance(venue_order_id, str) and venue_order_id:
            self._venue_orders[venue_order_id] = order_id
        desk_id = payload.get("desk_id")
        if row["status"] == "unknown" and isinstance(desk_id, str):
            self.blocked_desks.setdefault(desk_id, order_id)
        elif isinstance(desk_id, str):
            self._unblock(desk_id, order_id)

    def _unblock(self, desk_id: str, order_id: str) -> None:
        """The order no longer blocks its desk. Another order of the desk still unknown does:
        two proposals that both ended unknown kept one id, and the other was never reconciled."""
        with self._book_lock:
            if self.blocked_desks.get(desk_id) != order_id:
                return
            for other_id, row in self._orders.items():
                if other_id != order_id and row.get("desk_id") == desk_id and row.get("status") == "unknown":
                    self.blocked_desks[desk_id] = other_id
                    return
            self.blocked_desks.pop(desk_id, None)

    def _rows(self) -> list[dict[str, Any]]:
        """A copy of every order row, taken under the book lock: the book is never iterated
        live while other threads insert into it."""
        with self._book_lock:
            return [dict(row) for row in self._orders.values()]

    # ------------------------------------------------------------------ environment
    def now(self) -> str:
        return now_iso(self.clock)

    def kill_switch_engaged(self) -> bool:
        return bool(self.kill_switch_path and self.kill_switch_path.exists())

    def market_open(self, instrument: Instrument, at: str) -> bool | None:
        """True/False for session-bound asset classes, None when the question does not apply."""
        if instrument.asset_class not in SESSION_CLASSES:
            return None
        if self.data is None:
            return None
        try:
            session = self.data.session(at[:10])
        except Exception:
            return None
        if session is None:
            return False
        try:
            moment = parse_iso(at)
            return parse_iso(session.open_at) <= moment < parse_iso(session.close_at)
        except (TypeError, ValueError):
            return None

    def _adv_usd(self, instrument: Instrument) -> Decimal | None:
        if self.data is None:
            return None
        try:
            value = self.data.adv_usd(instrument)
        except Exception:
            return None
        return None if value is None else money(value)

    def _quote(self, instrument: Instrument, desk_id: str | None = None):
        """The reference price for an instrument, from the book that would fill it.

        A shadow desk's order is priced by its own book, which reads the same market data the
        live venue would be quoted from, so a scored fill and a real one are comparable.
        """
        routed = (
            self.brokers.get(self.route(desk_id, instrument.venue))
            if desk_id is not None
            else None
        )
        for source in (routed, self.brokers.get(instrument.venue), self.data):
            if source is None:
                continue
            try:
                quote = source.quote(instrument)
            except Exception:
                continue
            if quote is not None:
                return quote
        return None

    def _capabilities(self, venue: str) -> set[str]:
        broker = self.brokers.get(venue)
        if broker is None:
            return set()
        try:
            return set(broker.capabilities())
        except Exception:
            return set()

    def orders_today(self, desk_id: str, day: str) -> int:
        """Distinct orders the desk has sent today, from the log rather than memory."""
        seen: set[str] = set()
        for row in self._rows():
            if row.get("desk_id") != desk_id:
                continue
            stamp = row.get("submitted_at") or row.get("at") or ""
            if stamp[:10] == day:
                seen.add(row["order_id"])
        return len(seen)

    # ------------------------------------------------------------------ risk context
    def risk_context(self, intent: OrderIntent, now: Any = None, *, venue: str | None = None) -> RiskContext:
        self._load()
        at = iso_time(now) if now is not None else self.now()
        manifest = self.manifests.get(intent.desk_id)
        if manifest is None:
            raise GatewayError(f"no manifest for desk {intent.desk_id}")
        if self.ledgers.get(intent.desk_id) is None:
            raise GatewayError(f"no ledger for desk {intent.desk_id}")
        # Only live sleeves are the floor's money, so only they can trip the floor's loss limit.
        floor = floor_totals(self.ledgers, at, include=self.live_ids())
        venue = venue or self.route(intent.desk_id, intent.instrument.venue)
        return RiskContext(
            manifest=manifest,
            quote=self._quote(intent.instrument, intent.desk_id),
            now=at,
            floor_equity=floor["equity"],
            floor_daily_pnl=floor["daily_pnl"],
            floor_max_daily_loss_pct=self.floor_max_daily_loss_pct,
            kill_switch=self.kill_switch_engaged(),
            market_open=self.market_open(intent.instrument, at),
            adv_usd=self._adv_usd(intent.instrument),
            venue_capabilities=self._capabilities(venue),
            **self.event_rules,
            **self._book_fields(intent, at),
        )

    def _book_fields(self, intent: OrderIntent, at: str) -> dict[str, Any]:
        """The parts of the risk context the desk's own book decides: its ledger, what its
        resting orders commit, and what its other proposals in flight will commit. Read again
        under the desk's lock just before a proposal reserves, so two proposals of one desk
        never both spend the same cash or sell the same position (Sept 16, 2026 audit: $150 at
        the venue on a $100 desk, 200 sold of 100 held)."""
        desk_id = intent.desk_id
        ledger = self.ledgers.get(desk_id)
        if ledger is None:
            raise GatewayError(f"no ledger for desk {desk_id}")
        state = ledger.state(at)
        with self._book_lock:
            self._load_locked()
            flying = {
                intent_id: dict(entry)
                for intent_id, entry in (self._inflight.get(desk_id) or {}).items()
                if intent_id != intent.id
            }
            rows = [
                dict(row)
                for row in self._orders.values()
                if row.get("desk_id") == desk_id and row.get("intent_id") not in flying and row.get("intent_id") != intent.id
            ]
        # Cash already committed to the desk's resting buys is not free to spend again: ten
        # resting bids that each pass the cash rule alone can fill together (audit, Sept 16).
        committed = ZERO
        # Likewise a position already offered by a working sell is not there to sell twice.
        selling: dict[str, Decimal] = {}
        # And what resting buys on one Kalshi market already put at risk there, either leg.
        event_buys: dict[str, Decimal] = {}
        open_orders = 0
        orders_today = 0
        for row in rows:
            stamp = row.get("submitted_at") or row.get("at") or ""
            if stamp[:10] == at[:10]:
                orders_today += 1
            if row.get("status") in TERMINAL_STATUSES:
                continue
            open_orders += 1
            try:
                remaining = max(ZERO, money(row.get("quantity") or 0) - money(row.get("filled_quantity") or 0))
                if row.get("side") == "buy":
                    price = money(row.get("limit_price") or 0)
                    ins = row.get("instrument") or {}
                    cost = remaining * price * money(ins.get("multiplier") or 1)
                    committed += cost
                    if ins.get("asset_class") == "event":
                        market = ins.get("market_id") or ins.get("symbol")
                        if market:
                            event_buys[market] = event_buys.get(market, ZERO) + cost
                elif row.get("side") == "sell":
                    key = _key_of(row.get("instrument"))
                    if key is not None:
                        selling[key] = selling.get(key, ZERO) + remaining
            except Exception:
                continue
        for entry in flying.values():
            open_orders += 1
            orders_today += 1
            if entry["side"] == "buy":
                committed += entry["notional"]
                if entry.get("market"):
                    event_buys[entry["market"]] = event_buys.get(entry["market"], ZERO) + entry["notional"]
            else:
                selling[entry["key"]] = selling.get(entry["key"], ZERO) + entry["quantity"]
        return {
            "desk_equity": state.equity,
            "desk_cash": state.cash - committed,
            "positions": state.positions,
            "desk_daily_pnl": state.daily_pnl,
            "desk_orders_today": orders_today,
            "open_orders": open_orders,
            "working_sells": selling,
            "working_event_buys": event_buys,
        }

    def _desk_lock(self, desk_id: str) -> threading.Lock:
        with self._book_lock:
            lock = self._desk_locks.get(desk_id)
            if lock is None:
                lock = self._desk_locks[desk_id] = threading.Lock()
            return lock

    def _mode_moving(self, desk_id: str) -> bool:
        """True while a promotion or a demotion is logged but the owner has not moved the
        desk's manifest yet: its sleeve is not set up, so nothing it proposes can be sized or
        routed truthfully."""
        if not self.manifests_carry_mode:
            return False
        manifest = self.manifests.get(desk_id)
        if manifest is None:
            return False
        try:
            return capital_mode(manifest, promoted_desks(self.log)) != manifest.capital_mode
        except Exception:
            return True

    def inflight(self, desk_id: str) -> int:
        """Approved proposals of this desk not yet recorded and swept."""
        with self._book_lock:
            return len(self._inflight.get(desk_id) or {})

    def settle_inflight(self, desk_id: str, timeout: float = 30.0) -> bool:
        """Wait (holding no lock while waiting) until the desk has nothing in flight; True if so.
        The desk's lock is taken once first, so a check-and-reserve under way is counted."""
        with self._desk_lock(desk_id):
            pass
        deadline = time.monotonic() + timeout
        while self.inflight(desk_id):
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.05)
        return True

    # ------------------------------------------------------------------ the decision
    def _refusal(self, intent: OrderIntent, at: str, reason: str) -> Decision:
        return Decision(
            intent_id=intent.id,
            desk_id=intent.desk_id,
            approved=False,
            reasons=(reason,),
            reference_price=None,
            notional=None,
            checked_at=at,
        )

    def _blocked_outcome(self, intent: OrderIntent, at: str, blocked: str) -> dict[str, Any]:
        decision = self._refusal(intent, at, f"desk blocked: order {blocked} has an unknown outcome; reconcile first")
        self._record_intent(intent, at)
        self._record_decision(decision)
        return self._outcome(intent, decision, None, [], blocked=True)

    def propose(self, intent: OrderIntent, now: Any = None) -> dict[str, Any]:
        """Check one intent and, when it passes, send it. Returns the outcome as plain data."""
        at = iso_time(now) if now is not None else self.now()
        blocked = self.blocked_desks.get(intent.desk_id)
        if blocked:
            return self._blocked_outcome(intent, at, blocked)

        # The capital mode is read once, and the risk context, the critic and the route all use
        # that one answer: a promotion landing mid-proposal once checked an order against the
        # shadow book and sent it to the real venue (Sept 16, 2026 audit).
        live = self.live_desk(intent.desk_id)
        venue = intent.instrument.venue if live else SHADOW_VENUE
        ctx = self.risk_context(intent, at, venue=venue)
        reserved = False
        with self._desk_lock(intent.desk_id):
            blocked = self.blocked_desks.get(intent.desk_id)
            # Moving: logged but not yet applied, or applied since `live` was read above.
            moving = not blocked and (self._mode_moving(intent.desk_id) or self.live_desk(intent.desk_id) != live)
            if not blocked and not moving:
                ctx = dataclasses.replace(ctx, **self._book_fields(intent, at))
                decision = self.risk_engine.check(intent, ctx)
                if decision.approved:
                    self._reserve(intent, decision)
                    reserved = True
        if blocked:
            return self._blocked_outcome(intent, at, blocked)
        if moving:
            decision = self._refusal(intent, at, "the desk's capital mode is changing; propose again once its sleeve is set up")
        try:
            self._record_intent(intent, at)
            self._record_decision(decision)
            if not decision.approved:
                return self._outcome(intent, decision, None, [])

            review = self.review(intent, decision, ctx, at, live=live)
            if review is not None and review.blocked:
                blocked_decision = Decision(
                    intent_id=intent.id,
                    desk_id=intent.desk_id,
                    approved=False,
                    reasons=(f"critic: {review.reason}",),
                    reference_price=decision.reference_price,
                    notional=decision.notional,
                    checked_at=at,
                )
                self._record_decision(blocked_decision)
                return self._outcome(intent, blocked_decision, None, [])

            order_row, fills = self._submit(intent, at, venue=venue)
        finally:
            if reserved:
                self._release(intent)
        if intent.has_exit_plan and self.exits is not None:  # leap: exits
            try:
                self.exits.record_for(intent, order_row, at)
            except Exception as exc:  # a plan that cannot be written must not lose the fill
                self._alert("warning", f"exit plan for {intent.id} not recorded: {type(exc).__name__}", at)
        return self._outcome(intent, decision, order_row, fills)

    def _reserve(self, intent: OrderIntent, decision: Decision) -> None:
        notional = decision.notional if decision.notional is not None else ZERO
        with self._book_lock:
            self._inflight.setdefault(intent.desk_id, {})[intent.id] = {
                "side": intent.side,
                "key": intent.instrument.key,
                "quantity": money(intent.quantity),
                "notional": money(notional),
                "market": (intent.instrument.market_id or intent.instrument.symbol) if intent.instrument.asset_class == "event" else None,
            }

    def _release(self, intent: OrderIntent) -> None:
        with self._desk_lock(intent.desk_id):
            with self._book_lock:
                flying = self._inflight.get(intent.desk_id) or {}
                flying.pop(intent.id, None)
                if not flying:
                    self._inflight.pop(intent.desk_id, None)

    # ------------------------------------------------------------------ the second pair of eyes
    def live_desk(self, desk_id: str) -> bool:
        """True when this desk is trading real money, promotions included."""
        manifest = self.manifests.get(desk_id)
        if manifest is None:
            return False
        if self.manifests_carry_mode:
            return manifest.live
        try:
            return capital_mode(manifest, promoted_desks(self.log)) == "live"
        except Exception:  # pragma: no cover - a log read that fails is not a licence to trade
            return manifest.live

    def shadow_desk(self, desk_id: str) -> bool:
        """True when this desk's orders are scored rather than sent."""
        return not self.live_desk(desk_id)

    def live_ids(self) -> set[str]:
        """Every desk on real capital. The floor's book is the sum of these and nothing else."""
        return {desk_id for desk_id in list(self.ledgers) if self.live_desk(desk_id)}

    def route(self, desk_id: str, venue: str) -> str:
        """Where an approved order actually goes: the venue, or the shadow book.

        A desk the committee has not promoted never reaches a broker, whatever venue its
        instrument names. This is the single place that decision is made.
        """
        return venue if self.live_desk(desk_id) else SHADOW_VENUE

    def review(
        self, intent: OrderIntent, decision: Decision, ctx: RiskContext, at: str, *, live: bool | None = None
    ) -> Any | None:
        """Ask the critic about one approved live order. None when it does not apply.

        Fails open on purpose: anything other than a clean `block` lets the order through, and
        every failure to get a verdict is an `ops.alert`. A verdict, either way, is published as
        `risk.review`.
        """
        if live is None:
            live = self.live_desk(intent.desk_id)
        if self.critic is None or not live:
            return None
        if intent.purpose == "exit":
            # leap: exits. An exit reduces exposure the desk already took; the critic's
            # question -- does the thesis justify the risk -- was answered at entry.
            return None
        try:
            memo = self.log.last(ctx.manifest.stream, "desk.memo")
            review = self.critic.review(
                intent=intent,
                manifest=ctx.manifest,
                decision=decision,
                positions=ctx.positions,
                memo=(memo.payload.get("text") if memo is not None else None),
            )
        except Exception as exc:  # pragma: no cover - the critic catches its own failures
            self._alert("warning", f"critic failed for {intent.id}: {type(exc).__name__}", at)
            return None
        if review.verdict not in ("approve", "block"):
            # No verdict, so nothing to publish: the site's `risk.review` contract admits only
            # `approve` and `block`, and one malformed row rejects the whole batch. The alert is
            # the record that the second pair of eyes was shut.
            self._alert(
                "warning",
                f"critic gave no verdict on {intent.id} ({review.reason}); "
                "the order proceeds on the deterministic engine",
                at,
            )
            return None
        payload = review.payload(intent.id, intent.desk_id)
        self.log.append(
            "risk",
            "risk.review",
            payload,
            id=f"review:{intent.id}:{_short(canonical(payload))}",
            at=at,
        )
        return review

    def _outcome(
        self,
        intent: OrderIntent,
        decision: Decision,
        order_row: dict[str, Any] | None,
        fills: list[dict[str, Any]],
        *,
        blocked: bool = False,
    ) -> dict[str, Any]:
        return {
            "intent_id": intent.id,
            "desk_id": intent.desk_id,
            "approved": decision.approved,
            "reasons": list(decision.reasons),
            "decision": decision.to_dict(),
            "order": order_row,
            "order_id": None if order_row is None else order_row.get("order_id"),
            "status": None if order_row is None else order_row.get("status"),
            "fills": fills,
            "blocked": blocked,
        }

    def _record_intent(self, intent: OrderIntent, at: str) -> Event:
        manifest = self.manifests.get(intent.desk_id)
        stream = manifest.stream if manifest else f"desk:{intent.desk_id}"
        payload = {
            "intent_id": intent.id,
            "desk_id": intent.desk_id,
            "instrument": intent.instrument.to_dict(),
            "side": intent.side,
            "quantity": text(intent.quantity),
            "order_type": intent.order_type,
            "limit_price": text(intent.limit_price),
            "time_in_force": intent.time_in_force,
            "rationale": intent.rationale,
            "session_id": intent.session_id,
            "created_at": intent.created_at,
            # leap: exits. The plan stated with the entry, and what an exit closes.
            "target_price": text(intent.target_price),
            "stop_price": text(intent.stop_price),
            "time_stop_at": intent.time_stop_at,
            "purpose": intent.purpose,
            "exit_reason": intent.exit_reason,
            "exit_of": intent.exit_of,
        }
        if intent.expires_at is not None:
            # When the venue cancels the entry if it has not filled, so the tape can be checked
            # against the venue's own order. Absent otherwise, so earlier intents keep their body.
            payload["expires_at"] = intent.expires_at
        return self.log.append(stream, "desk.intent", payload, id=f"intent:{intent.id}", at=at)

    def _record_decision(self, decision: Decision) -> Event:
        payload = decision.to_dict()
        payload["desk_id"] = decision.desk_id
        event_id = f"risk:{decision.intent_id}:{_short(canonical(payload))}"
        with self._book_lock:
            self._decisions[decision.intent_id] = decision.approved
        return self.log.append("risk", "risk.decision", payload, id=event_id, at=decision.checked_at)

    # ------------------------------------------------------------------ submission
    def _submit(self, intent: OrderIntent, at: str, *, venue: str | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        venue = venue or self.route(intent.desk_id, intent.instrument.venue)
        broker = self.brokers.get(venue)
        if broker is None:
            row = self._record_order(
                Order.from_intent(intent, venue=venue),
                status="rejected",
                at=at,
                reason=f"no broker configured for venue {venue}",
            )
            return row, []
        # Until the venue answers, a fill on this venue may be this order's with no way to say
        # so: the sweep leaves such a fill for later instead of writing it as nobody's.
        with self._book_lock:
            self._submitting[venue] = self._submitting.get(venue, 0) + 1
        try:
            order = broker.submit(intent)
        except RejectedOrder as exc:
            self._done_submitting(venue)
            row = self._record_order(
                Order.from_intent(intent, venue=venue), status="rejected", at=at, reason=str(exc)
            )
            return row, []
        except VenueUnavailable as exc:
            self._done_submitting(venue)
            row = self._record_order(
                Order.from_intent(intent, venue=venue),
                status="rejected",
                at=at,
                reason=f"venue unavailable: {exc}",
            )
            self._alert("warning", f"{venue} unavailable for {intent.id}: {exc}", at)
            return row, []
        except UnknownOutcome as exc:
            self._done_submitting(venue)
            order = Order.from_intent(intent, venue=venue)
            order.status = "unknown"
            row = self._record_order(order, status="unknown", at=at, reason=str(exc))
            self.blocked_desks[intent.desk_id] = order.id
            self._alert(
                "critical",
                f"unknown outcome for order {order.id} on {venue}: {exc}; desk {intent.desk_id} blocked",
                at,
            )
            return row, []
        except Exception as exc:
            self._done_submitting(venue)
            # Anything else after the request went out (a 2xx with a body the adapter could
            # not read, a parse error) is an unknown outcome too: the venue may hold the order.
            # Record it, block the desk, say so. Never let it vanish into a traceback.
            order = Order.from_intent(intent, venue=venue)
            order.status = "unknown"
            row = self._record_order(order, status="unknown", at=at, reason=f"{type(exc).__name__}: {exc}"[:300])
            self.blocked_desks[intent.desk_id] = order.id
            self._alert(
                "critical",
                f"unreadable answer for order {order.id} on {venue}: {type(exc).__name__}; desk {intent.desk_id} blocked",
                at,
            )
            return row, []
        except BaseException:
            self._done_submitting(venue)
            raise

        row = self._record_order(order, status=order.status, at=at, submitting=venue)
        # Refresh first, then sweep fills: an order that executed inline (an IOC, a marketable
        # limit) shows its fill only once the venue has recorded it.
        row = self._refresh(order.id, venue, at) or row
        fills = self.ingest_fills(venue)
        return row, [f for f in fills if f.get("order_id") == order.id]

    def _done_submitting(self, venue: str) -> None:
        with self._book_lock:
            left = self._submitting.get(venue, 0) - 1
            if left > 0:
                self._submitting[venue] = left
            else:
                self._submitting.pop(venue, None)

    def _refresh(self, order_id: str, venue: str, at: str) -> dict[str, Any] | None:
        """Re-read one order from the venue and record any status change."""
        broker = self.brokers.get(venue)
        if broker is None:
            return None
        try:
            fresh = broker.get_order(order_id)
        except Exception:
            return None
        if fresh is None:
            return None
        return self._record_order(fresh, status=fresh.status, at=at, reason=fresh.reason)

    def _record_order(
        self, order: Order, *, status: str, at: str, reason: str | None = None, submitting: str | None = None
    ) -> dict[str, Any]:
        with self._book_lock:
            try:
                known = dict(self._orders.get(order.id) or {})
                # The row (desk, intent) and the venue's id go into the book before the event is
                # written, in one step with the end of the submission: a fill another thread swept
                # in between was written with no desk, marked seen, and dropped by every ledger
                # (Sept 16, 2026 audit: 25 of 288 fills).
                row = self._orders.setdefault(order.id, {"order_id": order.id})
                for key, value in (("desk_id", order.desk_id), ("intent_id", order.intent_id), ("venue", order.venue)):
                    if value and not row.get(key):
                        row[key] = value
                if order.broker_order_id:
                    self._venue_orders[str(order.broker_order_id)] = order.id
            finally:
                if submitting is not None:
                    self._done_submitting(submitting)
        payload: dict[str, Any] = {
            "order_id": order.id,
            "intent_id": order.intent_id or known.get("intent_id"),
            "desk_id": order.desk_id or known.get("desk_id") or "",
            "venue": order.venue,
            "instrument": order.instrument.to_dict(),
            "side": order.side,
            "quantity": text(order.quantity),
            "order_type": order.order_type,
            "limit_price": text(order.limit_price),
            "status": status,
            "filled_quantity": text(order.filled_quantity),
            "average_price": text(order.average_price),
            "fees": text(order.fees),
            "submitted_at": order.submitted_at or at,
            "updated_at": order.updated_at or at,
            "reason": reason or order.reason,
            "venue_order_id": order.broker_order_id or None,
        }
        if order.venue == SHADOW_VENUE:
            # Nothing was sent. The row says so on its face, wherever it is read.
            payload["shadow"] = True
        # leap: exits. What the order was for, and whether the venue holds a bracket for it.
        payload["purpose"] = order.purpose or known.get("purpose") or "entry"
        if payload["purpose"] == "exit":
            payload["exit_reason"] = order.exit_reason or known.get("exit_reason")
            payload["exit_of"] = order.exit_of or known.get("exit_of")
        bracket = order._raw.get("bracket") if isinstance(order._raw, dict) else None
        if isinstance(bracket, bool):
            payload["bracket"] = bracket
        # One event per distinct state of the order. The state is the payload less its clock:
        # a poll that finds the same status and fill with a new `updated_at` is the same event,
        # and one that finds a new average price or fee at the same fill count is a new one
        # (an id keyed on status and fill alone refused it as "different content" on Sept 16).
        stable = {k: v for k, v in payload.items() if k not in ("updated_at",)}
        digest = hashlib.sha256(canonical(stable).encode("utf-8")).hexdigest()[:12]
        event_id = f"order:{order.id}:{status}:{text(order.filled_quantity)}:{digest}"
        already = None
        getter = getattr(self.log, "get", None)
        if callable(getter):
            try:
                already = getter(event_id)
            except Exception:
                already = None
        if already is None:
            self.log.append(
                f"broker:{order.venue}", "broker.order", payload, id=event_id, at=at
            )
        with self._book_lock:
            row = self._orders.setdefault(order.id, {"order_id": order.id})
            row.update({k: v for k, v in payload.items() if v is not None})
            row["status"] = status
            row["reason"] = payload["reason"]
            self._intent_orders[order.intent_id] = order.id
            if status == "unknown":
                self.blocked_desks.setdefault(order.desk_id, order.id)
            else:
                self._unblock(order.desk_id, order.id)
            return dict(row)

    # ------------------------------------------------------------------ fills
    def ingest_fills(self, venue: str) -> list[dict[str, Any]]:
        """Pull new fills from one venue and write them to the log. Idempotent on fill id.

        Every thread sweeps (workers after a submission, the tick's poll, cancels), so the sweep
        of one venue is serialized from attribution to cursor, reads back `FILL_LOOKBACK_SECONDS`
        behind its cursor, and never writes a fill it cannot place while a submission on the
        venue is still waiting for its order id. The venue is asked outside every lock."""
        from .events import EventConflict

        broker = self.brokers.get(venue)
        if broker is None:
            return []
        try:
            fills = broker.fills(since=_stamp_minus(self._fill_cursor.get(venue), FILL_LOOKBACK_SECONDS))
        except Exception:
            return []
        written: list[tuple[dict[str, Any], Any]] = []
        with self._ingest_lock(venue):
            cursor = self._fill_cursor.get(venue)
            held_back: str | None = None
            for fill in sorted(fills, key=lambda f: (f.at, f.id)):
                if cursor is None or fill.at > cursor:
                    cursor = fill.at
                with self._book_lock:
                    if fill.id in self._seen_fills:
                        continue
                    extra = self._attribution(fill)
                    fill = self._on_order_leg(fill, extra)
                    if not fill.desk_id and "desk_id" not in (extra or {}) and self._submitting.get(venue):
                        # Perhaps the order a worker is still waiting on: leave it, and the cursor
                        # before it, for the next sweep.
                        held_back = fill.at if held_back is None or fill.at < held_back else held_back
                        continue
                if extra is not None and "order_id" not in extra and extra.get("venue_order_id"):
                    self._say_unattributed(str(extra["venue_order_id"]))
                before = self._position_before(fill, extra)
                try:
                    payload = self._record_fill(venue, fill, extra)
                except EventConflict:
                    # Already on the tape under the same id (another sweep wrote it first).
                    with self._book_lock:
                        self._seen_fills.add(fill.id)
                    continue
                written.append((payload, before))
            if held_back is not None and (cursor is None or held_back < cursor):
                cursor = held_back
            self._fill_cursor[venue] = cursor
        for payload, before in written:
            self._score_reduction(payload, before)
        return [payload for payload, _ in written]

    def _ingest_lock(self, venue: str) -> threading.Lock:
        with self._book_lock:
            lock = self._ingest_locks.get(venue)
            if lock is None:
                lock = self._ingest_locks[venue] = threading.Lock()
            return lock

    def _position_before(self, fill: Fill, extra: "Mapping[str, Any] | None") -> Any:
        """The desk's position in the fill's instrument before this fill is folded; None when
        there is nothing to score. Event contracts included: until Sept 16, 2026 a Kalshi leg sold
        before settlement (a stop, a target, a desk's own exit) left no outcome at all, so every
        score of an event trade counted only the positions held to the end."""
        desk_id = fill.desk_id or str((extra or {}).get("desk_id") or "")
        ledger = self.ledgers.get(desk_id)
        if ledger is None:
            return None
        try:
            return ledger.state(self.now()).positions.get(fill.instrument.key)
        except Exception:
            return None

    def _score_reduction(self, payload: Mapping[str, Any], before: Any) -> Event | None:
        """leap: exits -- a spot position leaves the ledger by a sell, never by a settlement, so
        the sell is where its result is scored: entry at the ledger's average cost, exit at the
        fill. Until Sept 16, 2026 only event contracts wrote `desk.outcome`, so no crypto
        strategy ever had a settled record and none could earn a bigger size or a promotion.
        An event leg sold before its market settles is scored the same way (`result: "sold"`).

        `pnl` is net of the sell's own fee, as it always was; `entry_fees` is the closed
        quantity's share of the fees its opening fills paid, so a reader nets both."""
        try:
            if before is None or payload.get("side") != "sell" or money(before.quantity) <= 0:
                return None
            desk_id = str(payload.get("desk_id") or "")
            quantity = min(money(payload.get("quantity") or 0), money(before.quantity))
            price = money(payload.get("price") or 0)
            fee = money(payload.get("fee") or 0)
            if not desk_id or quantity <= 0:
                return None
            instrument = before.instrument
            entry = money(before.average_cost)
            pnl = (price - entry) * quantity * instrument.multiplier - fee
            at = _stamp(payload.get("at"), self.now())
            fill_id = str(payload.get("fill_id") or "")
            opened_at, entry_fees = self._open_of(desk_id, instrument.key, fill_id=fill_id or None)
            rationale = self._rationale_of(desk_id, instrument.key, opening_side="buy")
            manifest = self.manifests.get(desk_id)
            stream = manifest.stream if manifest else f"desk:{desk_id}"
            body = {
                "instrument": instrument.key,
                "market_id": instrument.market_id or instrument.symbol,
                "result": "sold",
                "entry_price": text(entry),
                "exit_price": text(price),
                "quantity": text(quantity),
                "pnl": text(pnl),
                "held_for_hours": _hours_between(opened_at, at),
                "opened_at": opened_at,
                "entry_fees": text(_fees(entry_fees)),
                "rationale_excerpt": rationale,
                "fill_id": fill_id,
                # Whether real money was at stake when it closed: a later demotion must not
                # turn a real result into practice on the public record.
                "real_money": self.live_desk(desk_id),
            }
            return self.log.append(
                stream, "desk.outcome", body, id=f"outcome:{desk_id}:{_short(str(payload.get('fill_id') or at))}", at=at
            )
        except Exception:
            return None

    def _attribution(self, fill: Fill) -> dict[str, Any] | None:
        """The desk, intent and floor order id a venue fill belongs to, from the venue's order
        id. A fill the floor cannot place is recorded as it came (`ingest_fills` says so once)."""
        if fill.desk_id:
            return None  # the shadow book names its desk
        venue_id = str(fill.order_id or "")
        with self._book_lock:
            ours = self._venue_orders.get(venue_id) or (venue_id if venue_id in self._orders else None)
            row = dict(self._orders.get(ours) or {}) if ours is not None else {}
        if ours is None:
            return {"venue_order_id": venue_id} if venue_id else None
        extra: dict[str, Any] = {"order_id": ours, "venue_order_id": venue_id}
        if row.get("desk_id"):
            extra["desk_id"] = row["desk_id"]
        if row.get("intent_id"):
            extra["intent_id"] = row["intent_id"]
        return extra

    def _on_order_leg(self, fill: Fill, extra: "Mapping[str, Any] | None") -> Fill:
        """The fill on the leg its order traded. Kalshi reports a sale of YES as a purchase of NO
        at the complement: the floor's stop that sold 34 YES of a Warsh market at 15 cents came
        back as 34 NO bought at 85 (Sept 17, 2026), so the ledger held both legs, the venue
        (which nets them) held neither, and the exit book re-sent the stop every few minutes.
        The two trades are the same money; the order's own leg is the one its ledger holds."""
        if not extra or not extra.get("order_id") or fill.instrument.asset_class != "event":
            return fill
        with self._book_lock:
            row = dict(self._orders.get(extra["order_id"]) or {})
        ins = row.get("instrument") or {}
        if ins.get("asset_class") != "event":
            return fill
        want = str(ins.get("right") or "yes").lower()
        have = str(fill.instrument.right or "yes").lower()
        market = str(ins.get("market_id") or ins.get("symbol") or "").upper()
        mine = str(fill.instrument.market_id or fill.instrument.symbol or "").upper()
        if want == have or (market and mine and market != mine):
            return fill
        return dataclasses.replace(
            fill,
            instrument=dataclasses.replace(fill.instrument, right=want),
            side="sell" if fill.side == "buy" else "buy",
            price=ONE - fill.price,
        )

    def _say_unattributed(self, venue_id: str) -> None:
        """A fill the floor cannot place is recorded as it came, and said once."""
        with self._book_lock:
            if venue_id in self._unattributed:
                return
            self._unattributed.add(venue_id)
        self._alert("warning", f"fill for an order the floor did not place: {venue_id[:24]}", self.now())

    def _record_fill(
        self, venue: str, fill: Fill, extra: "Mapping[str, Any] | None" = None
    ) -> dict[str, Any]:
        payload = dict(fill.to_dict())
        payload["fill_id"] = fill.id
        payload["venue"] = venue
        if venue == SHADOW_VENUE:
            payload["shadow"] = True
        if extra:
            payload.update(dict(extra))
        self.log.append(
            f"broker:{venue}",
            "broker.fill",
            payload,
            id=f"fill:{venue}:{fill.id}",
            at=_stamp(fill.at, self.now()),
        )
        with self._book_lock:
            self._seen_fills.add(fill.id)
        return payload

    # ------------------------------------------------------------------ settlement
    def poll_settlements(self, venue: str = "kalshi", now: Any = None) -> list[dict[str, Any]]:
        """Close every desk position on a market this venue has settled, and score it publicly.

        A settled binary contract is worth $1.00 or $0.00 per YES contract -- the complement on
        the NO leg -- and the venue pays it without a trade. No fill is ever reported, so
        `ingest_fills` cannot see it and the position would otherwise sit in the desk's book
        forever at its last mark. This is the only path by which an event position leaves a
        ledger, and the only input the `event_resolution` trigger and the post-mortem have.

        Two writes per closed position, both idempotent on their ids:

        * a `broker.fill` at the settlement value with no fee, timed at the venue's settled
          time, which is what actually moves cash and flattens the position; and
        * a public `desk.outcome`, the scored record: entry, exit, size, P&L, how long it was
          held and the sentence the desk gave when it opened the trade.

        The venue's own `GET /portfolio/positions` is the guard: a settlement whose market the
        venue still shows as open is left for the next poll rather than written into a ledger
        that `reconcile()` would then find disagrees with the venue.
        """
        broker = self.brokers.get(venue)
        reader = getattr(broker, "settlements", None)
        if broker is None or reader is None:
            return []
        self._load()
        at = iso_time(now) if now is not None else self.now()
        cursor = self._settlement_cursor.get(venue)
        try:
            rows = list(reader(since=cursor))
        except Exception:
            # A settlement sweep is never load-bearing for an order; it retries next tick.
            return []
        if not rows:
            return []
        try:
            open_tickers = {
                str(p.instrument.market_id or p.instrument.symbol or "").upper()
                for p in broker.positions()
                if p.quantity != 0
            }
        except Exception:
            # Without the venue's own book there is nothing to check the close against, and
            # closing blind is how a ledger and a venue drift apart.
            self._alert("warning", f"{venue} positions unavailable; settlements deferred", at)
            return []

        written: list[dict[str, Any]] = []
        for row in sorted(rows, key=lambda r: (str(r.get("settled_time") or ""), str(r.get("ticker") or ""))):
            ticker = str(row.get("ticker") or "").strip().upper()
            settled_at = _log_stamp(row.get("settled_time"), at)
            result = str(row.get("result") or "").strip().lower()
            if not ticker:
                continue
            if result not in ("yes", "no"):
                # Scalar and voided markets have no winning leg to score. Say so once and move
                # the cursor past it; a human decides what a void was worth.
                self._alert("warning", f"{venue} {ticker}: settled with no yes/no result", at)
                cursor = _max_stamp(cursor, settled_at)
                continue
            holders = self._holders_of(ticker)
            if holders and ticker in open_tickers and any(
                position.instrument.venue == venue and self.live_desk(desk_id)
                for desk_id, position in holders
            ):
                self._alert(
                    "warning",
                    f"{venue} {ticker}: settled while the venue still shows a position; deferred",
                    at,
                )
                break  # the cursor stays put so this row comes back on the next poll
            payout_yes = ONE if result == "yes" else ZERO
            for desk_id, position in holders:
                written.extend(
                    self._settle_position(
                        venue,
                        desk_id,
                        position,
                        ticker=ticker,
                        result=result,
                        payout_yes=payout_yes,
                        settled_at=settled_at,
                        suffix=len(holders) > 1,
                    )
                )
            # One outcome per desk per market, so a desk holding both legs is scored once per
            # leg but woken once: `due_sessions` reads the stream, not the count.
            self._settle_shadow(ticker, payout_yes, holders, settled_at)
            cursor = _max_stamp(cursor, settled_at)
        self._settlement_cursor[venue] = cursor
        return written

    def settle_finalized_markets(self, venue: str = "kalshi", now: Any = None, *, limit: int = 10, grace_seconds: int = 180) -> list[dict[str, Any]]:
        """Close positions on event markets the venue has finalized but that the account's own
        settlements feed will never name: markets only shadow desks held.

        `poll_settlements` reads `GET /portfolio/settlements`, which lists the account's
        settlements, so a market the live account never traded never appears there, and on
        Sept 16, 2026 three shadow lottery tickets on the 05:00 buckets sat unsettled while
        the exit engine tried to sell them into a closed book. This sweep reads the market
        itself: past its close by `grace_seconds`, `finalized` or `settled` with a yes/no
        result, and not among the venue's own open positions."""
        at = iso_time(now) if now is not None else self.now()
        source = None
        getter = getattr(self.data, "_source", None) or getattr(self.data, "source", None)
        if callable(getter):
            try:
                source = getter("event")
            except Exception:
                source = None
        if source is None or not hasattr(source, "market"):
            return []
        broker = self.brokers.get(venue)
        open_tickers: set[str] = set()
        if broker is not None:
            try:
                open_tickers = {
                    str(p.instrument.market_id or p.instrument.symbol or "").upper()
                    for p in broker.positions()
                    if p.quantity != 0
                }
            except Exception:
                return []  # without the venue's book, closing blind is how ledgers drift
        held: dict[str, list[tuple[str, Any]]] = {}
        for desk_id, ledger in sorted(self.ledgers.items()):
            for position in ledger.state(at).positions.values():
                instrument = position.instrument
                if instrument.asset_class != "event" or position.quantity == 0 or instrument.venue != venue:
                    continue
                ticker = str(instrument.market_id or instrument.symbol or "").upper()
                if ticker and ticker not in open_tickers:
                    held.setdefault(ticker, []).append((desk_id, position))
        written: list[dict[str, Any]] = []
        checked = 0
        for ticker in sorted(held):
            if checked >= limit:
                break
            checked += 1
            try:
                row = source.market(ticker)
            except Exception:
                continue
            if not isinstance(row, Mapping):
                continue
            status = str(row.get("status") or "").lower()
            result = str(row.get("result") or "").lower()
            close_time = _log_stamp(row.get("expiration_time") or row.get("close_time"), at)
            if status not in ("finalized", "settled") or result not in ("yes", "no"):
                continue
            if _seconds_between(close_time, at) < grace_seconds:
                continue
            payout_yes = ONE if result == "yes" else ZERO
            holders = held[ticker]
            for desk_id, position in holders:
                written.extend(
                    self._settle_position(
                        venue, desk_id, position, ticker=ticker, result=result,
                        payout_yes=payout_yes, settled_at=close_time, suffix=len(holders) > 1,
                    )
                )
            self._settle_shadow(ticker, payout_yes, holders, close_time)
        return written

    def _holders_of(self, ticker: str) -> list[tuple[str, Any]]:
        """(desk_id, position) for every desk holding that event market, whatever the leg."""
        found: list[tuple[str, Any]] = []
        for desk_id, ledger in sorted(self.ledgers.items()):
            for position in ledger.state(self.now()).positions.values():
                instrument = position.instrument
                if instrument.asset_class != "event" or position.quantity == 0:
                    continue
                if str(instrument.market_id or instrument.symbol or "").upper() != ticker:
                    continue
                found.append((desk_id, position))
        return found

    def _settle_position(
        self,
        venue: str,
        desk_id: str,
        position: Any,
        *,
        ticker: str,
        result: str,
        payout_yes: Decimal,
        settled_at: str,
        suffix: bool,
    ) -> list[dict[str, Any]]:
        """One desk's close on one settled market: the fill that pays it, then the score."""
        instrument = position.instrument
        leg = str(instrument.right or "yes").lower()
        exit_price = (ONE - payout_yes) if leg == "no" else payout_yes
        quantity = money(position.quantity)
        side = "sell" if quantity > 0 else "buy"
        fill_id = f"settlement:{ticker}:{settled_at}"
        if suffix:
            # Two positions closing on one settlement -- two desks, or one desk holding both
            # legs -- cannot share a fill id. A single position, which is the floor today,
            # keeps the plain id the runbook names.
            fill_id += f":{desk_id}:{_short(instrument.key)}"
        if fill_id in self._seen_fills:
            return []
        fill = Fill(
            id=fill_id,
            order_id="",
            desk_id=desk_id,
            instrument=instrument,
            side=side,
            quantity=abs(quantity),
            price=exit_price,
            fee=ZERO,
            at=settled_at,
        )
        # A shadow desk's settlement is a shadow fill: it never goes to the tape as the venue's.
        record_venue = venue if self.live_desk(desk_id) else SHADOW_VENUE
        payload = self._record_fill(record_venue, fill, {"settlement": True, "result": result})
        self._record_outcome(
            desk_id,
            position,
            ticker=ticker,
            result=result,
            exit_price=exit_price,
            settled_at=settled_at,
            fill_id=fill_id,
        )
        return [payload]

    def _record_outcome(
        self,
        desk_id: str,
        position: Any,
        *,
        ticker: str,
        result: str,
        exit_price: Decimal,
        settled_at: str,
        fill_id: str | None = None,
    ) -> Event:
        """The public score for one resolved position: what was thought, and what happened.
        `pnl` is the settlement's (it pays no fee); `entry_fees` is what the opening fills paid."""
        instrument = position.instrument
        quantity = money(position.quantity)
        entry = money(position.average_cost)
        pnl = (exit_price - entry) * quantity * instrument.multiplier
        opened_at, entry_fees = self._open_of(desk_id, instrument.key, fill_id=fill_id)
        rationale = self._rationale_of(desk_id, instrument.key, opening_side="buy" if quantity > 0 else "sell")
        manifest = self.manifests.get(desk_id)
        stream = manifest.stream if manifest else f"desk:{desk_id}"
        payload = {
            "instrument": instrument.key,
            "market_id": ticker,
            "result": result,
            "entry_price": text(entry),
            "exit_price": text(exit_price),
            "quantity": text(abs(quantity)),
            "pnl": text(pnl),
            "held_for_hours": _hours_between(opened_at, settled_at),
            "opened_at": opened_at,
            "entry_fees": text(_fees(entry_fees)),
            "rationale_excerpt": rationale,
            "real_money": self.live_desk(desk_id),
        }
        return self.log.append(
            stream,
            "desk.outcome",
            payload,
            # A desk can hold both legs of one market, so the instrument decides the id: the
            # payload names the leg in full, and this keeps two scores from being one event.
            id=f"outcome:{desk_id}:{ticker}:{settled_at}:{_short(instrument.key)}",
            at=settled_at,
        )

    def entry_of(self, desk_id: str, key: str) -> tuple[str | None, str]:
        """When this desk's position in the instrument opened, and the sentence it gave. Public
        for the positions board (leap: exits)."""
        return self._entry_of(desk_id, key)

    def _entry_of(self, desk_id: str, key: str) -> tuple[str | None, str]:
        """When the desk's position in the contract opened, and the sentence it gave for doing so."""
        opened_at, _ = self._open_of(desk_id, key)
        return opened_at, self._rationale_of(desk_id, key)

    def _open_of(self, desk_id: str, key: str, *, fill_id: str | None = None) -> tuple[str | None, Decimal]:
        """When the position opened -- the first fill after the desk was last flat in the
        instrument, not the first fill ever (two one-hour round trips four days apart were
        scored as 1 and 97 hours held until Sept 16, 2026) -- and, for the reducing fill
        `fill_id`, the closed quantity's share of its opening fills' fees. Without `fill_id`
        (or when it is not on the tape): the position as the newest fill left it, and no fees."""
        rows = []
        for event in self.log.read(kind="broker.fill", limit=10_000, newest=True):
            payload = event.payload
            if payload.get("desk_id") != desk_id or _key_of(payload.get("instrument")) != key:
                continue
            rows.append({**payload, "at": event.at})
        last: dict[str, Any] | None = None
        for row in position_walk(rows):
            if fill_id is not None and row["fill_id"] == fill_id:
                return row["opened_at"], row["entry_fees"]
            last = row
        return (last["opened_at"] if last is not None else None), ZERO

    def _rationale_of(self, desk_id: str, key: str, *, opening_side: str | None = None) -> str:
        """The sentence the desk gave for its newest entry in the contract. An exit's intent is
        not an entry (the exit engine's "Floor exit of ..." had labelled every stopped-out
        strategy position discretionary), nor is an intent on the closing side when the opening
        side is known."""
        rationale = ""
        manifest = self.manifests.get(desk_id)
        stream = manifest.stream if manifest else f"desk:{desk_id}"
        self._load()
        for event in self.log.read(stream=stream, kind="desk.intent", limit=10_000, newest=True):
            payload = event.payload
            if _key_of(payload.get("instrument")) != key:
                continue
            if payload.get("purpose") == "exit":
                continue
            if opening_side is not None and payload.get("side") not in (None, opening_side):
                continue
            if self._decisions.get(payload.get("intent_id")) is False:
                continue  # refused by the engine or the critic: it never opened anything
            said = payload.get("rationale")
            if isinstance(said, str) and said.strip():
                rationale = said.strip()[:400]
        return rationale

    def _settle_shadow(
        self, ticker: str, payout_yes: Decimal, holders: Iterable[tuple[str, Any]], settled_at: str
    ) -> None:
        """Mirror the close into the shadow book, so the score and the ledger agree.

        The book writes its own settlement fills under the `settlement` desk id, which no desk
        ledger folds, so the position closes in both places and the notional cash moves once.
        """
        desks = {desk_id for desk_id, _ in holders if self.shadow_desk(desk_id)}
        if not desks:
            return
        broker = self.brokers.get(SHADOW_VENUE)
        settle = getattr(broker, "settle_event", None)
        if settle is None:
            return
        try:
            settle(ticker, payout_yes, now=settled_at)
        except Exception as exc:
            self._alert("warning", f"shadow settlement of {ticker} failed: {exc}", settled_at)

    # ------------------------------------------------------------------ lifecycle
    def poll_orders(self, now: Any = None) -> list[dict[str, Any]]:
        """Refresh every non-terminal order and record fills. Returns the rows that changed."""
        self._load()
        at = iso_time(now) if now is not None else self.now()
        changed: list[dict[str, Any]] = []
        rows = self._rows()
        venues = {
            row.get("venue")
            for row in rows
            if row.get("status") not in TERMINAL_STATUSES and row.get("venue")
        }
        for order_id, row in sorted((row["order_id"], row) for row in rows):
            if row.get("status") in TERMINAL_STATUSES or row.get("status") == "unknown":
                continue
            venue = row.get("venue")
            if not venue:
                continue
            before = row.get("status"), row.get("filled_quantity")
            fresh = self._refresh(order_id, venue, at)
            if fresh is not None and (fresh.get("status"), fresh.get("filled_quantity")) != before:
                changed.append(fresh)
        # The fill sweep runs after the refresh, for every venue that had a resting order when
        # the poll began: a fill that lands between the two would otherwise wait for the next
        # order on that venue, and a quoting strategy would re-bid against a position it
        # already holds (Sept 16, 2026 audit).
        for venue in sorted(v for v in venues if v):
            self.ingest_fills(venue)
        return changed

    def cancel(self, desk_id: str, order_id: str, now: Any = None) -> dict[str, Any]:
        """Cancel one of the desk's own orders."""
        self._load()
        at = iso_time(now) if now is not None else self.now()
        with self._book_lock:
            row = dict(self._orders[order_id]) if order_id in self._orders else None
        if row is None:
            raise GatewayError(f"unknown order {order_id}")
        if row.get("desk_id") != desk_id:
            raise GatewayError(f"order {order_id} does not belong to desk {desk_id}")
        if row.get("status") in TERMINAL_STATUSES:
            return dict(row)
        venue = row.get("venue")
        broker = self.brokers.get(venue)
        if broker is None:
            raise GatewayError(f"no broker configured for venue {venue}")
        try:
            order = broker.cancel(order_id)
        except RejectedOrder as exc:
            return self._refresh(order_id, venue, at) or {**row, "reason": str(exc)}
        except UnknownOutcome as exc:
            self.blocked_desks[desk_id] = order_id
            self._alert("critical", f"cancel of {order_id} unconfirmed: {exc}", at)
            raise DeskBlocked(str(exc)) from exc
        self.ingest_fills(venue)
        return self._record_order(order, status=order.status, at=at, reason=order.reason)

    # ------------------------------------------------------------------ reconciliation
    def reconcile(self, venue: str, now: Any = None) -> dict[str, Any]:
        """Compare the venue's positions with the sum of the desk sub-ledgers on that venue."""
        self._load()
        at = iso_time(now) if now is not None else self.now()
        broker = self.brokers.get(venue)
        if broker is None:
            raise GatewayError(f"no broker configured for venue {venue}")

        # Resolve anything the gateway could not confirm before comparing books: every order
        # still unknown, not only the one each desk's block names (two concurrent submissions
        # that both ended unknown left one of them unreconciled for good).
        with self._book_lock:
            unresolved = sorted(
                {(str(row.get("desk_id") or ""), order_id) for order_id, row in self._orders.items() if row.get("status") == "unknown"}
                | set(self.blocked_desks.items())
            )
            rows = {order_id: dict(self._orders.get(order_id) or {}) for _, order_id in unresolved}
        for desk_id, order_id in unresolved:
            row = rows.get(order_id) or {}
            if row.get("venue") != venue:
                continue
            try:
                broker.get_order(order_id)
            except (RejectedOrder, LookupError) as exc:
                # The venue answered and has no such order: it was never placed.
                self._record_order(
                    self._order_from_row(row),
                    status="rejected",
                    at=at,
                    reason=f"unresolved after reconciliation; venue has no such order ({exc})"[:300],
                )
                self._unblock(desk_id, order_id)
                continue
            except Exception:
                continue  # the venue did not answer: the desk stays blocked until it does
            fresh = self._refresh(order_id, venue, at)
            if fresh is not None and fresh.get("status") not in ("unknown", None):
                self._unblock(desk_id, order_id)  # resolved to a real status
        self.ingest_fills(venue)

        try:
            venue_positions = broker.positions()
        except Exception as exc:
            raise GatewayError(f"{venue} positions unavailable: {exc}") from exc
        # An event position is compared on the YES scale per market: the venue reports one
        # signed YES quantity per market (long 20 NO is -20), the ledger holds a leg. Compared
        # by instrument key, the two never met and every live position read as matched.
        def scale(position: Position) -> tuple[str, Decimal]:
            instrument = position.instrument
            if instrument.asset_class == "event":
                key = f"event:{instrument.market_id or instrument.symbol}:{instrument.venue}"
                quantity = money(position.quantity)
                return key, (-quantity if str(instrument.right or "").lower() == "no" else quantity)
            return instrument.key, money(position.quantity)

        theirs: dict[str, Decimal] = {}
        for position in venue_positions:
            if position.quantity == 0:
                continue
            key, quantity = scale(position)
            theirs[key] = theirs.get(key, ZERO) + quantity
        ours: dict[str, Decimal] = {}
        for desk_id, ledger in list(self.ledgers.items()):
            manifest = self.manifests.get(desk_id)
            shadow = self.shadow_desk(desk_id)
            if venue == SHADOW_VENUE:
                # The shadow book is reconciled against the shadow desks, and nothing else.
                if not shadow:
                    continue
            elif shadow:
                # A shadow book holds nothing a venue could confirm. Comparing the two would
                # invent a mismatch and halt the floor over a position nobody owns.
                continue
            elif manifest is not None and venue not in manifest.venues:
                continue
            for key, position in ledger.state(at).positions.items():
                if position.quantity == 0:
                    continue
                # A shadow position names the venue it would have traded on, so the book it
                # belongs to is decided by the desk, not by the instrument.
                if venue != SHADOW_VENUE and position.instrument.venue != venue:
                    continue
                scaled_key, quantity = scale(position)
                ours[scaled_key] = ours.get(scaled_key, ZERO) + quantity

        mismatches = []
        for key in sorted(set(theirs) | set(ours)):
            mine, yours = ours.get(key, ZERO), theirs.get(key, ZERO)
            if mine != yours:
                mismatches.append(
                    {"instrument": key, "ledger": text(mine), "venue": text(yours)}
                )
        matches = len(set(theirs) | set(ours)) - len(mismatches)
        payload = {
            "venue": venue,
            "matches": matches,
            "mismatches": mismatches,
            "as_of": at,
        }
        self.log.append(
            f"broker:{venue}", "broker.reconciled", payload, id=f"recon:{venue}:{at}", at=at
        )
        if mismatches:
            self.reconciliation_mismatch = True
            self.breaker(
                Breaker(
                    "floor",
                    "reconciliation",
                    f"{venue}: {len(mismatches)} instrument(s) differ from the ledger",
                    "halt_new_orders",
                ),
                at,
            )
        else:
            self.reconciliation_mismatch = False
        return payload

    def _order_from_row(self, row: Mapping[str, Any]) -> Order:
        return Order(
            id=row["order_id"],
            intent_id=row.get("intent_id", ""),
            desk_id=row.get("desk_id", ""),
            instrument=Instrument.from_dict(row["instrument"]),
            side=row.get("side", "buy"),
            quantity=money(row.get("quantity", "0")),
            order_type=row.get("order_type", "market"),
            limit_price=money(row["limit_price"]) if row.get("limit_price") else None,
            time_in_force=row.get("time_in_force", "day"),
            status="new",
            venue=row.get("venue", ""),
        )

    # ------------------------------------------------------------------ publication
    def release_deferred_events(self) -> list[str]:
        """Ids of deferred events that may now be published, oldest first.

        A `broker.order` is releasable once that order is terminal. A `desk.intent` is releasable
        once its order is terminal, or immediately once the engine or the critic rejected it:
        there is no order to trade ahead of.
        """
        self._load()
        released: dict[str, int] = {}
        for event in self.log.read(kind="desk.intent", limit=10_000, newest=True):
            if event.public:
                continue
            intent_id = event.payload.get("intent_id")
            order_id = self._intent_orders.get(intent_id)
            if order_id is None:
                if self._decisions.get(intent_id) is False:
                    released[event.id] = event.seq
                continue
            if (self._orders.get(order_id) or {}).get("status") in TERMINAL_STATUSES:
                released[event.id] = event.seq
        for event in self.log.read(kind="broker.order", limit=10_000, newest=True):
            if event.public:
                continue
            order_id = event.payload.get("order_id")
            if (self._orders.get(order_id) or {}).get("status") in TERMINAL_STATUSES:
                released[event.id] = event.seq
        return [event_id for event_id, _ in sorted(released.items(), key=lambda kv: kv[1])]

    # ------------------------------------------------------------------ alerts
    def breaker(self, breaker: Breaker, at: str | None = None) -> Event:
        at = at or self.now()
        return self.log.append(
            "risk",
            "risk.breaker",
            breaker.to_dict(),
            id=f"breaker:{breaker.scope}:{breaker.rule}:{at[:10]}:{_short(breaker.detail)}",
            at=at,
        )

    def _alert(self, level: str, message: str, at: str) -> Event:
        return self.log.append(
            "ops",
            "ops.alert",
            {"level": level, "text": message},
            id=f"alert:{at}:{_short(message)}",
            at=at,
        )

    # ------------------------------------------------------------------ reads
    def orders(self, desk_id: str | None = None) -> list[dict[str, Any]]:
        self._load()
        rows = self._rows()
        if desk_id is not None:
            rows = [r for r in rows if r.get("desk_id") == desk_id]
        return sorted(rows, key=lambda r: (r.get("submitted_at") or "", r["order_id"]))

    def order_for_intent(self, intent_id: str) -> dict[str, Any] | None:
        """A copy of the order row the intent became, or None."""
        self._load()
        with self._book_lock:
            order_id = self._intent_orders.get(intent_id)
            row = self._orders.get(order_id) if order_id is not None else None
            return dict(row) if row is not None else None

    def open_orders(self, desk_id: str | None = None) -> list[dict[str, Any]]:
        return [r for r in self.orders(desk_id) if r.get("status") not in TERMINAL_STATUSES]
