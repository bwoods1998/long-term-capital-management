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
import hashlib
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
        """Send what is new since the last tick. Returns the ids notified this tick.

        A cursor on the log (`notify_seq`) marks what is handled, so a tick reads only the events
        written since the last one. Until Sept 16, 2026 it re-read the day's fills and outcomes
        every tick and remembered 500 handled ids trimmed in alphabetical order, which dropped the
        venue fills behind the shadow ones: each tick re-folded a day of real fills at five log
        reads apiece and held the floor's tick for three minutes. Shadow fills and shadow
        outcomes are passed over before any folding."""
        if not self.enabled:
            return []
        state = dict(self.state())
        latest = int(self.log.latest_seq())
        cursor = state.get("notify_seq")
        if cursor is None:
            # The first run, or a state written before the cursor: mail nothing old.
            self.save_state(notify_seq=latest, notify_floor=state.get("notify_floor") or at)
            return []
        cursor = int(cursor)
        sent: list[str] = []
        delivered = list(state.get("notify_delivered") or [])
        delivered_set = set(delivered)
        pending: list[tuple[list[Any], Callable[[list[Any]], dict[str, Any] | None]]] = []
        by_order: dict[str, list[Any]] = {}
        highest = cursor
        for kind in ("broker.fill", "desk.outcome"):
            after = cursor
            while True:
                # Nothing past `latest`: the cursor moves to it, so a later event read now would
                # be mailed again next tick.
                batch = [e for e in self.log.read(kind=kind, after=after, limit=2000) if e.seq <= latest]
                for event in batch:
                    after = event.seq
                    if event.id in delivered_set:
                        continue
                    if _age_seconds(event.at, at) > MAX_AGE_SECONDS:
                        continue  # too old to be news
                    if kind == "broker.fill":
                        if event.payload.get("shadow"):
                            continue  # a score, not money
                        by_order.setdefault(str(event.payload.get("order_id") or event.id), []).append(event)
                    else:
                        if event.payload.get("real_money") is False:
                            continue
                        pending.append(([event], lambda events: self.settlement(events[0])))
                if len(batch) < 2000:
                    break
        for events in by_order.values():
            pending.append((events, self.story_group))
        pending.sort(key=lambda item: item[0][0].seq)
        failed_at: int | None = None
        for events, fold in pending:
            try:
                facts = fold(events)
            except Exception as exc:
                self.alert("warning", f"trade notice could not be folded: {type(exc).__name__}")
                continue
            if facts is None:
                continue
            facts["notice_id"] = "notice:" + hashlib.sha256("|".join(sorted(e.id for e in events)).encode()).hexdigest()
            try:
                answer = self.poster(f"{self.gateway_url}/v1/notify", self.token, facts)
            except urllib.error.HTTPError as exc:
                if exc.code == 429:
                    self.alert("warning", "trade notice held: the gateway's daily notice cap is reached")
                else:
                    self.alert("warning", f"trade notice refused: http {exc.code}")
                failed_at = events[0].seq
                break
            except Exception as exc:
                self.alert("warning", f"trade notice not sent: {type(exc).__name__}")
                failed_at = events[0].seq
                break
            if isinstance(answer, Mapping) and answer.get("sent") is False:
                self.alert("warning", "trade notice not sent: the gateway has no mail binding")
                failed_at = events[0].seq
                break
            sent.extend(e.id for e in events)
            delivered.extend(e.id for e in events)
            # A grouped order can contain fills after a later failed notice's sequence. Keep
            # the successfully delivered ids as well as the cursor so retries don't remail it.
            self.save_state(notify_delivered=delivered[-2000:])
        # Everything up to the log's end is handled, unless a notice failed: then the cursor stops
        # just before it, and the next tick tries it again (the ones before it are not re-sent,
        # because the cursor only ever covers what was folded or sent).
        highest = latest if failed_at is None else max(cursor, failed_at - 1)
        self.save_state(notify_seq=highest, notify_floor=state.get("notify_floor") or at,
                        notify_checked_at=at, notify_failed_seq=failed_at,
                        notify_sent_total=int(state.get("notify_sent_total") or 0) + len(sent),
                        notify_last_sent_at=at if sent else state.get("notify_last_sent_at"))
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
