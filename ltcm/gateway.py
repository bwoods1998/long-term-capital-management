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

import hashlib
import re
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
from .ledger import DeskLedger, floor_totals, iso_time, parse_iso
from .manifest import DeskManifest
from .risk import Breaker, Decision, RiskContext, RiskEngine

ZERO = Decimal(0)
ONE = Decimal(1)

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
        #: desk_id -> order_id that could not be confirmed.
        self.blocked_desks: dict[str, str] = {}
        #: True once a reconciliation found a difference the humans have not cleared.
        self.reconciliation_mismatch = False
        self._orders: dict[str, dict[str, Any]] = {}
        self._intent_orders: dict[str, str] = {}
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
        while True:
            batch = self.log.read(after=self._scan_seq, limit=2000)
            if not batch:
                return
            for event in batch:
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
        row.update({k: v for k, v in payload.items() if v is not None})
        row["status"] = payload.get("status", row.get("status", "new"))
        intent_id = payload.get("intent_id")
        if isinstance(intent_id, str):
            self._intent_orders[intent_id] = order_id
        desk_id = payload.get("desk_id")
        if row["status"] == "unknown" and isinstance(desk_id, str):
            self.blocked_desks.setdefault(desk_id, order_id)
        elif isinstance(desk_id, str) and self.blocked_desks.get(desk_id) == order_id:
            self.blocked_desks.pop(desk_id, None)

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
        for row in self._orders.values():
            if row.get("desk_id") != desk_id:
                continue
            stamp = row.get("submitted_at") or row.get("at") or ""
            if stamp[:10] == day:
                seen.add(row["order_id"])
        return len(seen)

    # ------------------------------------------------------------------ risk context
    def risk_context(self, intent: OrderIntent, now: Any = None) -> RiskContext:
        self._load()
        at = iso_time(now) if now is not None else self.now()
        manifest = self.manifests.get(intent.desk_id)
        if manifest is None:
            raise GatewayError(f"no manifest for desk {intent.desk_id}")
        ledger = self.ledgers.get(intent.desk_id)
        if ledger is None:
            raise GatewayError(f"no ledger for desk {intent.desk_id}")
        state = ledger.state(at)
        # Only live sleeves are the floor's money, so only they can trip the floor's loss limit.
        floor = floor_totals(self.ledgers, at, include=self.live_ids())
        return RiskContext(
            manifest=manifest,
            desk_equity=state.equity,
            desk_cash=state.cash,
            positions=state.positions,
            quote=self._quote(intent.instrument, intent.desk_id),
            now=at,
            desk_daily_pnl=state.daily_pnl,
            desk_orders_today=self.orders_today(intent.desk_id, at[:10]),
            floor_equity=floor["equity"],
            floor_daily_pnl=floor["daily_pnl"],
            floor_max_daily_loss_pct=self.floor_max_daily_loss_pct,
            kill_switch=self.kill_switch_engaged(),
            market_open=self.market_open(intent.instrument, at),
            adv_usd=self._adv_usd(intent.instrument),
            open_orders=sum(
                1
                for row in self._orders.values()
                if row.get("desk_id") == intent.desk_id
                and row.get("status") not in TERMINAL_STATUSES
            ),
            venue_capabilities=self._capabilities(
                self.route(intent.desk_id, intent.instrument.venue)
            ),
        )

    # ------------------------------------------------------------------ the decision
    def propose(self, intent: OrderIntent, now: Any = None) -> dict[str, Any]:
        """Check one intent and, when it passes, send it. Returns the outcome as plain data."""
        at = iso_time(now) if now is not None else self.now()
        blocked = self.blocked_desks.get(intent.desk_id)
        if blocked:
            reasons = (f"desk blocked: order {blocked} has an unknown outcome; reconcile first",)
            decision = Decision(
                intent_id=intent.id,
                desk_id=intent.desk_id,
                approved=False,
                reasons=reasons,
                reference_price=None,
                notional=None,
                checked_at=at,
            )
            self._record_intent(intent, at)
            self._record_decision(decision)
            return self._outcome(intent, decision, None, [], blocked=True)

        ctx = self.risk_context(intent, at)
        decision = self.risk_engine.check(intent, ctx)
        self._record_intent(intent, at)
        self._record_decision(decision)
        if not decision.approved:
            return self._outcome(intent, decision, None, [])

        review = self.review(intent, decision, ctx, at)
        if review is not None and review.blocked:
            blocked = Decision(
                intent_id=intent.id,
                desk_id=intent.desk_id,
                approved=False,
                reasons=(f"critic: {review.reason}",),
                reference_price=decision.reference_price,
                notional=decision.notional,
                checked_at=at,
            )
            self._record_decision(blocked)
            return self._outcome(intent, blocked, None, [])

        order_row, fills = self._submit(intent, at)
        if intent.has_exit_plan and self.exits is not None:  # leap: exits
            try:
                self.exits.record_for(intent, order_row, at)
            except Exception as exc:  # a plan that cannot be written must not lose the fill
                self._alert("warning", f"exit plan for {intent.id} not recorded: {type(exc).__name__}", at)
        return self._outcome(intent, decision, order_row, fills)

    # ------------------------------------------------------------------ the second pair of eyes
    def live_desk(self, desk_id: str) -> bool:
        """True when this desk is trading real money, promotions included."""
        manifest = self.manifests.get(desk_id)
        if manifest is None:
            return False
        try:
            return capital_mode(manifest, promoted_desks(self.log)) == "live"
        except Exception:  # pragma: no cover - a log read that fails is not a licence to trade
            return manifest.live

    def shadow_desk(self, desk_id: str) -> bool:
        """True when this desk's orders are scored rather than sent."""
        return not self.live_desk(desk_id)

    def live_ids(self) -> set[str]:
        """Every desk on real capital. The floor's book is the sum of these and nothing else."""
        return {desk_id for desk_id in self.ledgers if self.live_desk(desk_id)}

    def route(self, desk_id: str, venue: str) -> str:
        """Where an approved order actually goes: the venue, or the shadow book.

        A desk the committee has not promoted never reaches a broker, whatever venue its
        instrument names. This is the single place that decision is made.
        """
        return venue if self.live_desk(desk_id) else SHADOW_VENUE

    def review(
        self, intent: OrderIntent, decision: Decision, ctx: RiskContext, at: str
    ) -> Any | None:
        """Ask the critic about one approved live order. None when it does not apply.

        Fails open on purpose: anything other than a clean `block` lets the order through, and
        every failure to get a verdict is an `ops.alert`. A verdict, either way, is published as
        `risk.review`.
        """
        if self.critic is None or not self.live_desk(intent.desk_id):
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
        return self.log.append(stream, "desk.intent", payload, id=f"intent:{intent.id}", at=at)

    def _record_decision(self, decision: Decision) -> Event:
        payload = decision.to_dict()
        payload["desk_id"] = decision.desk_id
        event_id = f"risk:{decision.intent_id}:{_short(canonical(payload))}"
        self._decisions[decision.intent_id] = decision.approved
        return self.log.append("risk", "risk.decision", payload, id=event_id, at=decision.checked_at)

    # ------------------------------------------------------------------ submission
    def _submit(self, intent: OrderIntent, at: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        venue = self.route(intent.desk_id, intent.instrument.venue)
        broker = self.brokers.get(venue)
        if broker is None:
            row = self._record_order(
                Order.from_intent(intent, venue=venue),
                status="rejected",
                at=at,
                reason=f"no broker configured for venue {venue}",
            )
            return row, []
        try:
            order = broker.submit(intent)
        except RejectedOrder as exc:
            row = self._record_order(
                Order.from_intent(intent, venue=venue), status="rejected", at=at, reason=str(exc)
            )
            return row, []
        except VenueUnavailable as exc:
            row = self._record_order(
                Order.from_intent(intent, venue=venue),
                status="rejected",
                at=at,
                reason=f"venue unavailable: {exc}",
            )
            self._alert("warning", f"{venue} unavailable for {intent.id}: {exc}", at)
            return row, []
        except UnknownOutcome as exc:
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

        row = self._record_order(order, status=order.status, at=at)
        fills = self.ingest_fills(venue)
        row = self._refresh(order.id, venue, at) or row
        return row, [f for f in fills if f.get("order_id") == order.id]

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
        self, order: Order, *, status: str, at: str, reason: str | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "order_id": order.id,
            "intent_id": order.intent_id,
            "desk_id": order.desk_id,
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
        }
        if order.venue == SHADOW_VENUE:
            # Nothing was sent. The row says so on its face, wherever it is read.
            payload["shadow"] = True
        # leap: exits. What the order was for, and whether the venue holds a bracket for it.
        payload["purpose"] = order.purpose or "entry"
        if order.purpose == "exit":
            payload["exit_reason"] = order.exit_reason
            payload["exit_of"] = order.exit_of
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
        row = self._orders.setdefault(order.id, {"order_id": order.id})
        row.update({k: v for k, v in payload.items() if v is not None})
        row["status"] = status
        row["reason"] = payload["reason"]
        self._intent_orders[order.intent_id] = order.id
        if status == "unknown":
            self.blocked_desks.setdefault(order.desk_id, order.id)
        elif self.blocked_desks.get(order.desk_id) == order.id:
            self.blocked_desks.pop(order.desk_id, None)
        return dict(row)

    # ------------------------------------------------------------------ fills
    def ingest_fills(self, venue: str) -> list[dict[str, Any]]:
        """Pull new fills from one venue and write them to the log. Idempotent on fill id."""
        broker = self.brokers.get(venue)
        if broker is None:
            return []
        try:
            fills = broker.fills(since=self._fill_cursor.get(venue))
        except Exception:
            return []
        written: list[dict[str, Any]] = []
        cursor = self._fill_cursor.get(venue)
        for fill in sorted(fills, key=lambda f: (f.at, f.id)):
            if cursor is None or fill.at > cursor:
                cursor = fill.at
            if fill.id in self._seen_fills:
                continue
            written.append(self._record_fill(venue, fill))
        self._fill_cursor[venue] = cursor
        return written

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
        payload = self._record_fill(venue, fill, {"settlement": True, "result": result})
        self._record_outcome(
            desk_id,
            position,
            ticker=ticker,
            result=result,
            exit_price=exit_price,
            settled_at=settled_at,
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
    ) -> Event:
        """The public score for one resolved position: what was thought, and what happened."""
        instrument = position.instrument
        quantity = money(position.quantity)
        entry = money(position.average_cost)
        pnl = (exit_price - entry) * quantity * instrument.multiplier
        opened_at, rationale = self._entry_of(desk_id, instrument.key)
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
            "rationale_excerpt": rationale,
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
        """When this desk first traded the instrument, and the sentence it gave. Public for the
        positions board (leap: exits)."""
        return self._entry_of(desk_id, key)

    def _entry_of(self, desk_id: str, key: str) -> tuple[str | None, str]:
        """When this desk first traded the contract, and the sentence it gave for doing so."""
        opened_at: str | None = None
        for event in self.log.read(kind="broker.fill", limit=10_000):
            payload = event.payload
            if payload.get("desk_id") != desk_id or _key_of(payload.get("instrument")) != key:
                continue
            if opened_at is None or event.at < opened_at:
                opened_at = event.at
        rationale = ""
        manifest = self.manifests.get(desk_id)
        stream = manifest.stream if manifest else f"desk:{desk_id}"
        for event in self.log.read(stream=stream, kind="desk.intent", limit=10_000):
            if _key_of(event.payload.get("instrument")) != key:
                continue
            said = event.payload.get("rationale")
            if isinstance(said, str) and said.strip():
                rationale = said.strip()[:400]
        return opened_at, rationale

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
        venues = {
            row.get("venue")
            for row in self._orders.values()
            if row.get("status") not in TERMINAL_STATUSES and row.get("venue")
        }
        for venue in sorted(v for v in venues if v):
            self.ingest_fills(venue)
        for order_id, row in sorted(self._orders.items()):
            if row.get("status") in TERMINAL_STATUSES or row.get("status") == "unknown":
                continue
            venue = row.get("venue")
            if not venue:
                continue
            before = row.get("status"), row.get("filled_quantity")
            fresh = self._refresh(order_id, venue, at)
            if fresh is not None and (fresh.get("status"), fresh.get("filled_quantity")) != before:
                changed.append(fresh)
        return changed

    def cancel(self, desk_id: str, order_id: str, now: Any = None) -> dict[str, Any]:
        """Cancel one of the desk's own orders."""
        self._load()
        at = iso_time(now) if now is not None else self.now()
        row = self._orders.get(order_id)
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

        # Resolve anything the gateway could not confirm before comparing books.
        for desk_id, order_id in list(self.blocked_desks.items()):
            row = self._orders.get(order_id) or {}
            if row.get("venue") != venue:
                continue
            fresh = self._refresh(order_id, venue, at)
            if fresh is None or fresh.get("status") == "unknown":
                # The venue still cannot say. Treat the order as never placed and unblock only
                # once the position comparison below agrees.
                self._record_order(
                    self._order_from_row(row),
                    status="rejected",
                    at=at,
                    reason="unresolved after reconciliation; venue has no such order",
                )
            self.blocked_desks.pop(desk_id, None)
        self.ingest_fills(venue)

        try:
            venue_positions = broker.positions()
        except Exception as exc:
            raise GatewayError(f"{venue} positions unavailable: {exc}") from exc
        theirs = {p.instrument.key: money(p.quantity) for p in venue_positions if p.quantity != 0}
        ours: dict[str, Decimal] = {}
        for desk_id, ledger in self.ledgers.items():
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
                ours[key] = ours.get(key, ZERO) + position.quantity

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
        for event in self.log.read(kind="desk.intent", limit=10_000):
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
        for event in self.log.read(kind="broker.order", limit=10_000):
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
        rows = [dict(r) for r in self._orders.values()]
        if desk_id is not None:
            rows = [r for r in rows if r.get("desk_id") == desk_id]
        return sorted(rows, key=lambda r: (r.get("submitted_at") or "", r["order_id"]))

    def open_orders(self, desk_id: str | None = None) -> list[dict[str, Any]]:
        return [r for r in self.orders(desk_id) if r.get("status") not in TERMINAL_STATUSES]
