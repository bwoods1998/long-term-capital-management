"""Exit plans: the stop, the target and the time stop a desk states with an entry, kept by the floor.

Before this module the risk engine could refuse a new order but could not close an old one: a
desk's "invalidation at 74,000, out by Friday" was a sentence in a memo, and nothing happened
when 74,000 printed on a Saturday night. Now the plan rides on the intent itself
(`OrderIntent.target_price`, `stop_price`, `time_stop_at`), is published as `desk.exit_plan`
the moment the entry order is accepted, and `ExitBook.tick` reads the live mark against it on
every tick of the floor, whether or not the desk is in session.

* A venue with native brackets (Coinbase, `attached_order_configuration`) holds the target and
  the stop itself; the plan says so with `venue_native: true` and the floor enforces only the
  time stop for it. Coinbase's stop is a stop-limit with a five percent cushion the floor cannot
  change, so a gap through it is a gap the venue does not protect against -- the plan still
  carries the stop, so the board shows what was asked for.
* Everywhere else (Kalshi, the shadow books) the floor is the bracket: when the mark reaches the
  stop or the target, or the clock reaches the time stop, an exposure-reducing market order goes
  through `Gateway.propose` with `purpose="exit"`, which the engine allows on its notional rule
  and the critic does not review.

One exit per plan per reason: the exit intent's id is derived from the entry it closes and the
reason, so a trigger the floor notices on ten ticks is one order at the venue. A refusal (kill
switch, venue down) is retried on a slow cadence with the same id, never as a second order.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Mapping

from .broker import TERMINAL_STATUSES, Instrument, OrderIntent, money, text
from .events import EventLog, now_iso
from .ledger import iso_time

ZERO = Decimal(0)
#: Venues whose order API attaches a take-profit and a stop to the entry itself.
NATIVE_BRACKET_VENUES = frozenset({"coinbase"})
EXIT_REASON_ORDER = ("stop", "target", "time_stop")


def _parse(stamp: str) -> datetime:
    value = str(stamp).replace("Z", "+00:00")
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _seconds_between(start: str, end: str) -> float:
    return (_parse(end) - _parse(start)).total_seconds()


@dataclass(frozen=True)
class ExitPlan:
    """What the floor will do about one filled entry, in the desk's own numbers."""

    intent_id: str
    desk_id: str
    instrument: Instrument
    entry_side: str
    quantity: Decimal
    target_price: Decimal | None
    stop_price: Decimal | None
    time_stop_at: str | None
    venue_native: bool
    order_ids: tuple[str, ...]
    created_at: str

    @classmethod
    def from_intent(
        cls,
        intent: OrderIntent,
        *,
        venue_native: bool = False,
        order_ids: tuple[str, ...] = (),
        created_at: str | None = None,
    ) -> "ExitPlan":
        return cls(
            intent_id=intent.id,
            desk_id=intent.desk_id,
            instrument=intent.instrument,
            entry_side=intent.side,
            quantity=money(intent.quantity),
            target_price=intent.target_price,
            stop_price=intent.stop_price,
            time_stop_at=intent.time_stop_at,
            venue_native=bool(venue_native),
            order_ids=tuple(order_ids),
            created_at=created_at or intent.created_at,
        )

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any], *, desk_id: str, created_at: str) -> "ExitPlan":
        return cls(
            intent_id=str(payload["intent_id"]),
            desk_id=desk_id,
            instrument=Instrument.from_dict(dict(payload["instrument"])),
            entry_side=str(payload.get("entry_side") or "buy"),
            quantity=money(payload.get("quantity") or 0),
            target_price=money(payload["target_price"]) if payload.get("target_price") is not None else None,
            stop_price=money(payload["stop_price"]) if payload.get("stop_price") is not None else None,
            time_stop_at=payload.get("time_stop_at"),
            venue_native=bool(payload.get("venue_native")),
            order_ids=tuple(str(o) for o in (payload.get("order_ids") or [])),
            created_at=created_at,
        )

    @property
    def exit_side(self) -> str:
        return "sell" if self.entry_side == "buy" else "buy"

    @property
    def has_levels(self) -> bool:
        return self.target_price is not None or self.stop_price is not None

    def to_payload(self) -> dict[str, Any]:
        """The `desk.exit_plan` payload, exactly the contract's keys plus the two the floor
        needs to rebuild the plan after a restart (`entry_side`, `quantity`)."""
        return {
            "intent_id": self.intent_id,
            "instrument": self.instrument.to_dict(),
            "target_price": text(self.target_price),
            "stop_price": text(self.stop_price),
            "time_stop_at": self.time_stop_at,
            "venue_native": self.venue_native,
            "order_ids": list(self.order_ids),
            "entry_side": self.entry_side,
            "quantity": text(self.quantity),
        }

    def due(self, mark: Decimal | None, at: str) -> str | None:
        """The reason an exit is due now, or None. The stop is checked before the target, so a
        mark that somehow satisfies both (a stale quote straddling them) protects first. A
        venue-native plan leaves the levels to the venue and reports only the time stop."""
        if not self.venue_native and mark is not None and mark > 0:
            if self.entry_side == "buy":
                if self.stop_price is not None and mark <= self.stop_price:
                    return "stop"
                if self.target_price is not None and mark >= self.target_price:
                    return "target"
            else:
                if self.stop_price is not None and mark >= self.stop_price:
                    return "stop"
                if self.target_price is not None and mark <= self.target_price:
                    return "target"
        if self.time_stop_at is not None and self.instrument.asset_class != "event":
            # An event contract is paid at settlement; a time stop would sell it into the spread
            # minutes before the venue pays it in full. Stops and targets still apply.
            try:
                if _seconds_between(self.time_stop_at, at) >= 0:
                    return "time_stop"
            except ValueError:
                return None
        return None


class ExitBook:
    """Every open plan on the floor, and the enforcement of each against the live mark."""

    def __init__(
        self,
        log: EventLog,
        gateway: Any,
        ledgers: Mapping[str, Any],
        manifests: Mapping[str, Any],
        *,
        quote: Callable[[Instrument], Any],
        clock: Callable[[], float],
        check_seconds: int = 60,
        retry_seconds: int = 300,
        quote_parallelism: int = 1,
        alert: Callable[[str, str], None] | None = None,
    ):
        self.log = log
        self.gateway = gateway
        self.ledgers = ledgers
        self.manifests = manifests
        self.quote = quote
        self.clock = clock
        self.check_seconds = int(check_seconds)
        self.retry_seconds = int(retry_seconds)
        self.quote_parallelism = max(1, min(16, int(quote_parallelism)))
        self._fold_lock = threading.RLock()
        self.alert = alert or (lambda level, message: None)
        self._plans: dict[str, ExitPlan] = {}
        self._closed: set[str] = set()
        self._attempts: dict[tuple[str, str], str] = {}
        self._scan_seq = 0
        self._last_check: str | None = None

    # ------------------------------------------------------------------ folding
    def now(self) -> str:
        return now_iso(self.clock)

    def _stream_of(self, desk_id: str) -> str:
        manifest = self.manifests.get(desk_id)
        stream = getattr(manifest, "stream", None)
        return stream if isinstance(stream, str) else f"desk:{desk_id}"

    def _fold(self) -> None:
        """Rebuild the open plans from the log, once per new event batch."""
        with self._fold_lock:
            self._fold_locked()

    def _fold_locked(self) -> None:
        while True:
            batch = self.log.read(after=self._scan_seq, limit=2000)
            if not batch:
                return
            for event in batch:
                if not isinstance(event.seq, int) or event.seq <= self._scan_seq:
                    continue
                self._scan_seq = event.seq
                if event.kind == "desk.exit_plan":
                    desk_id = event.stream.split(":", 1)[1] if ":" in event.stream else event.stream
                    try:
                        plan = ExitPlan.from_payload(event.payload, desk_id=desk_id, created_at=event.at)
                    except (KeyError, ValueError, TypeError, ArithmeticError):
                        continue
                    self._plans[plan.intent_id] = plan
                elif event.kind == "broker.order":
                    # A filled exit closes its plan for good. Anything short of filled (a
                    # rejection, an IOC that missed) leaves the plan open for another try.
                    payload = event.payload
                    if payload.get("purpose") == "exit" and payload.get("status") == "filled":
                        closes = payload.get("exit_of")
                        if isinstance(closes, str):
                            self._closed.add(closes)

    def plans(self) -> dict[str, ExitPlan]:
        """Open plans by entry intent id."""
        with self._fold_lock:
            self._fold_locked()
            return {k: v for k, v in self._plans.items() if k not in self._closed}

    def plan_for_position(self, desk_id: str, key: str) -> ExitPlan | None:
        """The newest open plan this desk holds on that instrument, for the positions board."""
        found = [
            plan for plan in self.plans().values()
            if plan.desk_id == desk_id and plan.instrument.key == key
        ]
        if not found:
            return None
        return max(found, key=lambda plan: (plan.created_at, plan.intent_id))

    def exit_orders(self, plan: ExitPlan) -> list[dict[str, Any]]:
        """Exit orders the floor filed for this plan and that are still working."""
        rows: list[dict[str, Any]] = []
        for row in self.gateway.orders(plan.desk_id):
            if row.get("exit_of") != plan.intent_id or row.get("status") in TERMINAL_STATUSES:
                continue
            price = row.get("limit_price") or row.get("average_price")
            rows.append(
                {
                    "id": str(row.get("order_id")),
                    "kind": str(row.get("exit_reason") or "desk"),
                    "price": text(money(price)) if price is not None else None,
                }
            )
        return rows[:8]

    # ------------------------------------------------------------------ recording
    def record_for(self, intent: OrderIntent, order_row: Mapping[str, Any] | None, at: str | None = None) -> ExitPlan | None:
        """Publish the plan for an entry the venue accepted. Idempotent on the intent id."""
        if not intent.has_exit_plan or order_row is None:
            return None
        if order_row.get("status") in ("rejected", "cancelled", "expired", "unknown"):
            return None
        stamp = at or self.now()
        venue = str(order_row.get("venue") or intent.instrument.venue)
        bracket = order_row.get("bracket")
        venue_native = bool(bracket) if isinstance(bracket, bool) else False
        if venue in NATIVE_BRACKET_VENUES and not isinstance(bracket, bool):
            # The adapter says whether the bracket went; an older order row without the flag
            # is treated as bare so the floor keeps the stop itself. Safer than assuming.
            venue_native = False
        plan = ExitPlan.from_intent(intent, venue_native=venue_native, created_at=stamp)
        self.log.append(
            self._stream_of(intent.desk_id),
            "desk.exit_plan",
            plan.to_payload(),
            id=f"exitplan:{intent.id}",
            at=stamp,
        )
        with self._fold_lock:
            self._plans[intent.id] = plan
        return plan

    # ------------------------------------------------------------------ enforcement
    def _mark(self, plan: ExitPlan, position: Any, quotes: Mapping[str, Any] | None = None) -> Decimal | None:
        """The price the exit would get: the quote's reference for the exit side, else the
        ledger's own mark."""
        try:
            found = self.quote(plan.instrument) if quotes is None else quotes.get(plan.instrument.key)
        except Exception:
            found = None
        if found is not None:
            reference = getattr(found, "reference", None)
            price = reference(plan.exit_side) if callable(reference) else None
            if price is None:
                price = getattr(found, "mid", None) or getattr(found, "last", None)
            if price is not None and price > 0:
                return money(price)
        mark = getattr(position, "mark", None)
        return money(mark) if mark is not None and mark > 0 else None

    def tick(self, at: str | None = None) -> list[dict[str, Any]]:
        """Check every open plan against the mark and the clock; file what is due."""
        at = iso_time(at) if at is not None else self.now()
        if self._last_check is not None and _seconds_between(self._last_check, at) < self.check_seconds:
            return []
        self._last_check = at
        outcomes: list[dict[str, Any]] = []
        plans = self.plans()
        quotes = None
        if self.quote_parallelism > 1:
            instruments = {}
            books = {}
            for plan in plans.values():
                ledger = self.ledgers.get(plan.desk_id)
                if ledger is None:
                    continue
                # Sept 18, 2026: 586 plans, 70 cached prices, and a quote by HTTPS for every
                # one of them held the tick for seven minutes. A plan with only a time stop
                # needs the clock, not a quote; its mark is the ledger's own.
                if plan.stop_price is None and plan.target_price is None:
                    continue
                try:
                    if plan.desk_id not in books:
                        books[plan.desk_id] = ledger.state(at).positions
                    if plan.instrument.key in books[plan.desk_id]:
                        instruments[plan.instrument.key] = plan.instrument
                except Exception:
                    continue
            def fetch(item):
                key, instrument = item
                try:
                    return key, self.quote(instrument)
                except Exception:
                    return key, None
            with ThreadPoolExecutor(max_workers=self.quote_parallelism, thread_name_prefix="exit-quote") as pool:
                quotes = dict(pool.map(fetch, instruments.items()))
        for intent_id, plan in sorted(plans.items()):
            ledger = self.ledgers.get(plan.desk_id)
            if ledger is None:
                continue
            try:
                positions = ledger.state(at).positions
            except Exception:
                continue
            position = positions.get(plan.instrument.key)
            held = getattr(position, "quantity", ZERO) if position is not None else ZERO
            same_way = (held > 0) if plan.entry_side == "buy" else (held < 0)
            if position is None or held == 0 or not same_way:
                if self._entry_working(intent_id):
                    continue  # the entry still rests: the plan waits for its fill
                self._closed.add(intent_id)  # the position is gone; the plan is moot
                continue
            reason = plan.due(self._mark(plan, position, quotes), at)
            if reason is None:
                continue
            key = (intent_id, reason)
            last = self._attempts.get(key)
            if last is not None and _seconds_between(last, at) < self.retry_seconds:
                continue
            self._attempts[key] = at
            outcomes.append(self._file_exit(plan, reason, min(plan.quantity, abs(held)), at, held=held))
        return outcomes

    def _entry_working(self, intent_id: str) -> bool:
        """True while the plan's entry order is still working at the venue. A resting maker
        entry is flat until it fills; closing its plan then (Sept 16, 2026 audit) left the
        position it later opened with no stop at all."""
        finder = getattr(self.gateway, "order_for_intent", None)
        if not callable(finder):
            return False
        try:
            row = finder(intent_id)
        except Exception:
            return False
        return row is not None and row.get("status") not in TERMINAL_STATUSES

    def _cancel_working_sells(self, plan: ExitPlan, quantity: Decimal, held: Decimal, at: str) -> None:
        """Cancel the desk's own resting sells of this instrument when they offer what the exit
        must sell. The gateway counts a working sell against the position it offers (two sells
        of one position at once sold it twice, Sept 16, 2026 audit), so a stop filed next to a
        resting offer would be refused as a short; the exit replaces the offer instead."""
        reader = getattr(self.gateway, "open_orders", None)
        canceller = getattr(self.gateway, "cancel", None)
        if plan.exit_side != "sell" or not callable(reader) or not callable(canceller):
            return
        try:
            rows = list(reader(plan.desk_id))
        except Exception:
            return
        working = []
        for row in rows:
            if row.get("side") != "sell" or row.get("purpose") == "exit":
                continue
            instrument = row.get("instrument")
            try:
                key = Instrument.from_dict(dict(instrument)).key if isinstance(instrument, Mapping) else None
                remaining = money(row.get("quantity") or 0) - money(row.get("filled_quantity") or 0)
            except Exception:
                continue
            if key == plan.instrument.key and remaining > 0:
                working.append((row, remaining))
        if abs(held) - sum((r for _, r in working), ZERO) >= quantity:
            return  # the offers leave enough for the exit; they stay
        for row, _ in working:
            try:
                canceller(plan.desk_id, str(row.get("order_id")), at)
            except Exception as exc:
                self.alert("warning", f"exit of {plan.intent_id} could not cancel working order {row.get('order_id')}: {type(exc).__name__}")

    def _file_exit(self, plan: ExitPlan, reason: str, quantity: Decimal, at: str, *, held: Decimal | None = None) -> dict[str, Any]:
        if plan.venue_native and reason == "time_stop":
            self._release_venue_bracket(plan, at)
        self._cancel_working_sells(plan, quantity, quantity if held is None else held, at)
        level = {
            "stop": plan.stop_price,
            "target": plan.target_price,
            "time_stop": None,
        }.get(reason)
        why = {
            "stop": f"the mark reached the stop at {text(level)}",
            "target": f"the mark reached the target at {text(level)}",
            "time_stop": f"the holding period ended at {plan.time_stop_at}",
        }[reason]
        intent = OrderIntent.new(
            desk_id=plan.desk_id,
            instrument=plan.instrument,
            side=plan.exit_side,
            quantity=quantity,
            order_type="market",
            time_in_force="ioc",
            rationale=f"Floor exit of {plan.intent_id}: {why}. The plan was stated by the desk with its entry.",
            created_at=at,
            session_id=None,
            nonce=f"exit:{reason}",
            purpose="exit",
            exit_reason=reason,
            exit_of=plan.intent_id,
        )
        # A retry (this process or the next one) must send the very same intent: the log holds
        # the first one under `intent:<id>`, and a second body under the same id is a conflict.
        recorded = self.log.get(f"intent:{intent.id}")
        if recorded is not None:
            data = dict(recorded.payload)
            data["id"] = data.pop("intent_id", intent.id)
            try:
                intent = OrderIntent.from_dict(data)
            except (KeyError, ValueError, TypeError, ArithmeticError):
                pass
        try:
            result = self.gateway.propose(intent, at)
        except Exception as exc:
            self.alert("warning", f"exit {reason} for {plan.intent_id} failed: {type(exc).__name__}: {exc}")
            return {"intent_id": plan.intent_id, "reason": reason, "approved": False, "error": type(exc).__name__}
        # The engine's approval is not the venue's acceptance: an order the venue rejected, or
        # whose outcome is unknown, leaves the plan open for the slow retry.
        status = result.get("status")
        approved = bool(result.get("approved")) and status not in ("rejected", "unknown", None)
        if not approved:
            reasons = "; ".join(str(r) for r in (result.get("reasons") or [])) or (
                str((result.get("order") or {}).get("reason") or status or "refused")
            )
            self.alert("warning", f"exit {reason} for {plan.intent_id} refused: {reasons}")
        return {
            "intent_id": plan.intent_id,
            "exit_intent_id": intent.id,
            "reason": reason,
            "approved": approved,
            "status": status,
            "order_id": result.get("order_id"),
        }

    def _release_venue_bracket(self, plan: ExitPlan, at: str) -> None:
        """Cancel the venue's resting bracket before the floor sells the position at market.

        UNVERIFIED against a live account: whether Coinbase reserves the base asset for an
        attached take-profit/stop-loss so that a separate market sell would fail. The safe
        order of operations is to cancel first, so that is what the floor does; a venue that
        exposes no open-orders read is left alone and the market exit is sent regardless.
        """
        broker = self.gateway.brokers.get(plan.instrument.venue)
        reader = getattr(broker, "open_orders", None)
        canceller = getattr(broker, "cancel", None)
        if broker is None or reader is None or canceller is None:
            return
        try:
            resting = reader()
        except Exception:
            return
        for order in resting:
            instrument = getattr(order, "instrument", None)
            if instrument is None or instrument.key != plan.instrument.key:
                continue
            order_id = getattr(order, "id", None) or getattr(order, "broker_order_id", None)
            if not order_id:
                continue
            try:
                canceller(order_id)
            except Exception as exc:
                self.alert("warning", f"bracket cancel for {plan.intent_id} failed: {type(exc).__name__}")


__all__ = ["EXIT_REASON_ORDER", "ExitBook", "ExitPlan", "NATIVE_BRACKET_VENUES"]
