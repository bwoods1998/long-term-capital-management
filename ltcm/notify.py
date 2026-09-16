"""Trade notices: an email when real money moves, with the desk's own reasons.

The owner asked for one thing beyond the balance mails: to hear when a trade is done, what
was done, and why the desk did it. The floor already records all of that in the event log --
the intent's rationale, the risk engine's verdict, the critic's review, the exit plan, the fill
itself and later the settlement -- so this module folds those into one notice per fill and one
per settled position and hands it to the gateway, which is the only thing that can send mail.

Only live sleeves notify: a shadow fill is a score, not money. A notice that cannot be sent
(gateway down, daily notice cap reached) is retried on later ticks until it is either sent or
a day old, and never stops the tick. Nothing here decides anything; it reports.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Mapping

from .events import EventLog

MAX_LINE = 400
MAX_AGE_SECONDS = 86_400
SITE = "https://blakewoods.us/capital"


def _money(value: Any) -> str:
    try:
        return f"${Decimal(str(value)):,.2f}"
    except Exception:
        return str(value)


def _signed(value: Any) -> str:
    try:
        number = Decimal(str(value))
    except Exception:
        return str(value)
    sign = "-" if number < 0 else "+"
    return f"{sign}${abs(number):,.2f}"


def _instrument(value: Any) -> str:
    if isinstance(value, Mapping):
        return str(value.get("symbol") or value.get("ticker") or "?")
    return str(value or "?")


def post_json(url: str, token: str, body: Mapping[str, Any], *, timeout: float = 15.0) -> dict[str, Any]:
    """POST one JSON document with the gateway token. Standard library, bounded, no retries."""
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            # Cloudflare answers the stock Python user agent with a 403 (error 1010): the first
            # live fills on Sept 16, 2026 produced three refused notices before this was named.
            "User-Agent": "ltcm-floor/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - https gateway only
        payload = response.read(64_000).decode("utf-8", "replace")
    try:
        return json.loads(payload) if payload else {}
    except ValueError:
        return {}


def _strategy_note(intent: Any) -> str:
    """A strategy's order is not read by the critic: the desk deployed the code and the risk
    engine checked the order. Say so instead of "no review"."""
    session = str((intent.payload.get("session_id") if intent else "") or "")
    if ":strategy:" not in session:
        return ""
    name = session.rsplit(":strategy:", 1)[1]
    return f"not reviewed: placed by the desk's {name} strategy (code it deployed; the risk engine checked the order)"


class TradeNotifier:
    """Folds a fill or a settlement into a notice and posts it to the gateway's /v1/notify."""

    def __init__(
        self,
        log: EventLog,
        manifests: Mapping[str, Any],
        *,
        gateway_url: str | None,
        token: str | None,
        state: Callable[[], Mapping[str, Any]],
        save_state: Callable[..., Any],
        alert: Callable[[str, str], Any],
        poster: Callable[..., Mapping[str, Any]] | None = None,
        enabled: bool = True,
    ):
        self.log = log
        self.manifests = manifests
        self.gateway_url = (gateway_url or "").rstrip("/")
        self.token = token
        self.state = state
        self.save_state = save_state
        self.alert = alert
        self.poster = poster or post_json
        self.enabled = bool(enabled and self.gateway_url and self.token)

    # ------------------------------------------------------------------ folding
    def _first(self, kind: str, **match: Any) -> Any:
        for event in self.log.read(kind=kind, limit=5000, newest=True):
            if all(event.payload.get(k) == v for k, v in match.items()):
                return event
        return None

    def _desk_name(self, desk_id: str | None) -> str:
        manifest = self.manifests.get(desk_id) if desk_id else None
        return getattr(manifest, "name", None) or str(desk_id or "a desk")

    def story(self, fill: Any) -> dict[str, Any] | None:
        """Everything the owner should know about one fill, or None for a shadow fill."""
        payload = fill.payload
        if payload.get("shadow"):
            return None
        order = self._first("broker.order", order_id=payload.get("order_id"))
        intent_id = (order.payload.get("intent_id") if order else None) or payload.get("intent_id")
        intent = self._first("desk.intent", intent_id=intent_id) if intent_id else None
        desk_id = (
            payload.get("desk_id")
            or (order.payload.get("desk_id") if order else None)
            or (intent.stream.split(":", 1)[1] if intent and ":" in intent.stream else None)
        )
        decision = self._first("risk.decision", intent_id=intent_id) if intent_id else None
        review = self._first("risk.review", intent_id=intent_id) if intent_id else None
        plan = self._first("desk.exit_plan", intent_id=intent_id) if intent_id else None
        purpose = (order.payload.get("purpose") if order else None) or (intent.payload.get("purpose") if intent else None) or "entry"
        return {
            "kind": "trade",
            "desk_id": desk_id,
            "desk_name": self._desk_name(desk_id),
            "venue": _instrument_venue(payload.get("instrument")),
            "instrument": _instrument(payload.get("instrument")),
            "side": str(payload.get("side") or "?"),
            "quantity": str(payload.get("quantity") or "?"),
            "price": str(payload.get("price") or "?"),
            "fee": str(payload.get("fee") or "0"),
            "at": fill.at,
            "purpose": str(purpose),
            "exit_reason": (order.payload.get("exit_reason") if order else None),
            "rationale": str((intent.payload.get("rationale") if intent else "") or "")[:1500],
            "engine": (
                ("approved" if decision.payload.get("approved") else "refused")
                + (": " + "; ".join(str(r) for r in decision.payload.get("reasons") or []) if decision.payload.get("reasons") else "")
            ) if decision else "no engine record",
            "critic": (
                f"{review.payload.get('verdict')}: {review.payload.get('reason')}" if review
                else _strategy_note(intent) or "no review"
            ),
            "target_price": plan.payload.get("target_price") if plan else (intent.payload.get("target_price") if intent else None),
            "stop_price": plan.payload.get("stop_price") if plan else (intent.payload.get("stop_price") if intent else None),
            "time_stop_at": plan.payload.get("time_stop_at") if plan else (intent.payload.get("time_stop_at") if intent else None),
            "story_url": f"{SITE}/desk/?id={desk_id}#story-{intent_id}" if desk_id and intent_id else f"{SITE}/",
            "intent_id": intent_id,
            "fill_id": payload.get("fill_id") or fill.id,
        }

    def story_group(self, fills: list[Any]) -> dict[str, Any] | None:
        """One notice for every fill of one order in the tick: the story of the first, with the
        quantity summed, the price averaged by quantity and the fees summed."""
        facts = self.story(fills[0])
        if facts is None or len(fills) == 1:
            return facts
        quantity = Decimal(0)
        cost = Decimal(0)
        fees = Decimal(0)
        for fill in fills:
            try:
                q = Decimal(str(fill.payload.get("quantity") or 0))
                p = Decimal(str(fill.payload.get("price") or 0))
                fees += Decimal(str(fill.payload.get("fee") or 0))
            except (InvalidOperation, ValueError):
                continue
            quantity += q
            cost += q * p
        if quantity > 0:
            facts["quantity"] = format(quantity.normalize(), "f")
            facts["price"] = format((cost / quantity).quantize(Decimal("0.0001")), "f")
            facts["fee"] = format(fees, "f")
        facts["at"] = fills[-1].at
        return facts

    def settlement(self, outcome: Any) -> dict[str, Any] | None:
        payload = outcome.payload
        desk_id = outcome.stream.split(":", 1)[1] if ":" in outcome.stream else None
        manifest = self.manifests.get(desk_id) if desk_id else None
        if manifest is not None and getattr(manifest, "capital_mode", "live") != "live":
            return None
        return {
            "kind": "settled",
            "desk_id": desk_id,
            "desk_name": self._desk_name(desk_id),
            "instrument": _instrument(payload.get("instrument")),
            "market_id": str(payload.get("market_id") or ""),
            "result": str(payload.get("result") or "?"),
            "entry_price": str(payload.get("entry_price") or "?"),
            "exit_price": str(payload.get("exit_price") or "?"),
            "quantity": str(payload.get("quantity") or "?"),
            "pnl": str(payload.get("pnl") or "0"),
            "held_for_hours": str(payload.get("held_for_hours") or "?"),
            "rationale": str(payload.get("rationale_excerpt") or "")[:1500],
            "at": outcome.at,
            "story_url": f"{SITE}/desk/?id={desk_id}" if desk_id else f"{SITE}/",
            "outcome_id": outcome.id,
        }

    # ------------------------------------------------------------------ the tick
    def tick(self, at: str) -> list[str]:
        """Send what is new since the last tick. Returns the ids notified this tick."""
        if not self.enabled:
            return []
        state = dict(self.state())
        sent: list[str] = []
        done = set(state.get("notified") or [])
        floor = state.get("notify_floor")

        def news(event: Any) -> bool:
            if event.id in done or floor is None or event.at < floor:
                return False  # seen, or before the floor: the first run mails nothing old
            if _age_seconds(event.at, at) > MAX_AGE_SECONDS:
                done.add(event.id)  # too old to be news; give up quietly
                return False
            return True

        # The fills of one order in one tick are one notice: a resting quote fills in pieces,
        # and a 333-contract order filled in six on Sept 16, 2026 would have been six emails.
        pending: list[tuple[list[str], list[Any], Callable[[list[Any]], dict[str, Any] | None]]] = []
        by_order: dict[str, list[Any]] = {}
        for event in self.log.read(kind="broker.fill", limit=2000, newest=True):
            if news(event):
                by_order.setdefault(str(event.payload.get("order_id") or event.id), []).append(event)
        for events in by_order.values():
            pending.append(([e.id for e in events], events, self.story_group))
        for event in self.log.read(kind="desk.outcome", limit=2000, newest=True):
            if news(event):
                pending.append(([event.id], [event], lambda events: self.settlement(events[0])))
        pending.sort(key=lambda item: item[1][0].at)
        for event_ids, events, fold in pending:
            try:
                facts = fold(events)
            except Exception as exc:
                self.alert("warning", f"trade notice could not be folded: {type(exc).__name__}")
                done.update(event_ids)
                continue
            if facts is None:
                done.update(event_ids)
                continue
            try:
                answer = self.poster(f"{self.gateway_url}/v1/notify", self.token, facts)
            except urllib.error.HTTPError as exc:
                if exc.code == 429:
                    self.alert("warning", "trade notice held: the gateway's daily notice cap is reached")
                else:
                    self.alert("warning", f"trade notice refused: http {exc.code}")
                break
            except Exception as exc:
                self.alert("warning", f"trade notice not sent: {type(exc).__name__}")
                break
            if isinstance(answer, Mapping) and answer.get("sent") is False:
                self.alert("warning", "trade notice not sent: the gateway has no mail binding")
            done.update(event_ids)
            sent.extend(event_ids)
        if floor is None:
            state["notify_floor"] = at
        state["notified"] = sorted(done)[-500:]
        self.save_state(notified=state["notified"], notify_floor=state.get("notify_floor", at))
        return sent


def _instrument_venue(value: Any) -> str:
    if isinstance(value, Mapping):
        return str(value.get("venue") or "")
    return ""


def _age_seconds(then: str, now: str) -> float:
    from .ledger import parse_iso

    try:
        return (parse_iso(now) - parse_iso(then)).total_seconds()
    except Exception:
        return 0.0
