"""The night desk: a cheap watch that never sleeps and wakes a desk only when it matters.

A desk's cadence is a handful of sessions a day. Between them the floor marks books and polls
orders, and nothing thinks. This module gives every desk a watch: on each pass it looks, at no
model cost, for the things a human desk would be paged for -- a held market moving, a coin
moving, a fill landing, a new market opening in a series the desk follows, a headline naming
what it holds -- and when one appears it spends one turn of a flash model on the question
"is this worth a full session?". A `wake` starts a session with trigger `watch:<kind>`; an
`ignore` is published too, with the one-line reason, so the tape shows the watch working.

Costs are charged to the desk. A desk is woken at most once per cooldown, never while it is
already in session, never when the floor has stopped for credit, and -- for a live desk -- only
when its venue is one the floor can actually send an order to. Shadow desks are woken on the
same terms: their record is the evidence the promotion gates read, and a watch that only
served the live sleeves would starve the race.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping

from .broker import money, text
from .committee import capital_mode, promoted_desks
from .ledger import iso_time

ZERO = Decimal(0)
TRIGGER_KINDS = ("price_move", "fill", "new_market", "headline")
DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": True,
    "profile": "flash_asap",
    "reasoning_effort": "low",
    "max_output_tokens": 300,
    "cooldown_seconds": 1800,
    "check_seconds": 60,
    "lookback_seconds": 3600,
    "event_move_dollars": "0.08",
    "crypto_move_pct": "0.03",
    "equity_move_pct": "0.03",
    "headline": True,
    "headline_check_seconds": 600,
}

INSTRUCTIONS = """You are the night watch for one trading desk on the Long Term Capital Management floor.
The desk is not in session. Something happened. Your one job: decide whether it justifies
waking the desk for a full session, which costs real money and a few minutes of the model's
time. Wake it when the event could change a position it holds or open an opportunity inside
its mandate that will not wait for the next scheduled session. Ignore routine noise, moves the
desk's stated stops and targets already cover, and anything outside the mandate.
Reply with exactly one line of JSON and nothing else:
{"decision": "wake" or "ignore", "reason": "<one sentence, published>"}"""


def _parse(stamp: str) -> datetime:
    moment = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _seconds_between(start: str, end: str) -> float:
    return (_parse(end) - _parse(start)).total_seconds()


def parse_decision(output: Any) -> tuple[str, str] | None:
    """`(decision, reason)` from the model's line, or None when it said neither."""
    if not isinstance(output, str) or not output.strip():
        return None
    body = output.strip()
    match = re.search(r"\{.*\}", body, re.S)
    if match:
        try:
            data = json.loads(match.group(0))
        except ValueError:
            data = None
        if isinstance(data, dict):
            decision = str(data.get("decision") or "").strip().lower()
            reason = str(data.get("reason") or "").strip()
            if decision in ("wake", "ignore"):
                return decision, reason[:500] or "no reason given"
    lowered = body.lower()
    if "wake" in lowered and "ignore" not in lowered:
        return "wake", body[:500]
    if "ignore" in lowered and "wake" not in lowered:
        return "ignore", body[:500]
    return None


@dataclass(frozen=True)
class Trigger:
    kind: str
    detail: str
    key: str | None = None  # the instrument key it concerns, when it concerns one


class NightWatch:
    """One watch for the whole floor; `tick` looks at every desk."""

    def __init__(self, service: Any, config: Mapping[str, Any] | None = None):
        self.service = service
        self.config = {**DEFAULT_CONFIG, **dict(config or {})}
        self._last_check: str | None = None
        self._last_headline_check: dict[str, str] = {}
        self._last_wake: dict[str, str] = {}
        self._fill_seq = int(service.log.latest_seq())
        self._known_markets: dict[str, set[str]] = {}
        self._known_headlines: dict[str, set[str]] = {}
        self._restore_cooldowns()

    # ------------------------------------------------------------------ state
    def _restore_cooldowns(self) -> None:
        """After a restart the log still knows when each desk was last woken."""
        for event in self.service.log.read(kind="desk.watch", limit=10_000):
            if event.payload.get("decision") != "wake":
                continue
            desk_id = event.stream.split(":", 1)[1] if ":" in event.stream else event.stream
            if self._last_wake.get(desk_id, "") < event.at:
                self._last_wake[desk_id] = event.at

    @property
    def enabled(self) -> bool:
        return bool(self.config.get("enabled", True))

    def in_session(self, desk_id: str) -> bool:
        for thread in getattr(self.service, "_sessions", []):
            if thread.is_alive() and thread.name.startswith(f"session-{desk_id}-"):
                return True
        return False

    def eligible(self, manifest: Any, at: str, *, allow_shadow: bool) -> bool:
        desk_id = manifest.id
        if self.in_session(desk_id):
            return False
        last = self._last_wake.get(desk_id)
        if last is not None and _seconds_between(last, at) < int(self.config["cooldown_seconds"]):
            return False
        mode = capital_mode(manifest, promoted_desks(self.service.log))
        if mode == "live":
            enabled = set(self.service.config.get("live_venues") or ())
            return manifest.market_venue in enabled
        return allow_shadow

    # ------------------------------------------------------------------ looking
    def positions_of(self, desk_id: str, at: str) -> dict[str, Any]:
        ledger = self.service.ledgers.get(desk_id)
        if ledger is None:
            return {}
        try:
            positions = ledger.state(at).positions
        except Exception:
            return {}
        return {key: p for key, p in positions.items() if getattr(p, "quantity", ZERO) != 0}

    def _price_then(self, desk_id: str, key: str, at: str) -> Decimal | None:
        """The mark the ledger wrote for this position about a lookback ago."""
        lookback = int(self.config["lookback_seconds"])
        stream = f"ledger:{desk_id}"
        chosen: Decimal | None = None
        for event in self.service.log.read(stream=stream, kind="ledger.mark", limit=2000):
            as_of = event.payload.get("as_of") or event.at
            try:
                age = _seconds_between(as_of, at)
            except ValueError:
                continue
            if age < lookback:
                continue
            for row in event.payload.get("positions") or []:
                instrument = row.get("instrument") or {}
                row_key = f"{instrument.get('asset_class')}:{instrument.get('symbol')}:{instrument.get('venue')}"
                if row_key != key and _key_of(instrument) != key:
                    continue
                price = row.get("price") or row.get("mark")
                if price is not None:
                    try:
                        chosen = money(price)
                    except (ValueError, ArithmeticError, TypeError):
                        pass
        return chosen

    def _price_now(self, position: Any) -> Decimal | None:
        try:
            found = self.service.quote(position.instrument)
        except Exception:
            found = None
        if found is not None:
            price = getattr(found, "mid", None) or getattr(found, "last", None)
            if price is not None and price > 0:
                return money(price)
        mark = getattr(position, "mark", None)
        return money(mark) if mark is not None and mark > 0 else None

    def price_moves(self, desk_id: str, positions: Mapping[str, Any], at: str) -> list[Trigger]:
        found: list[Trigger] = []
        for key, position in sorted(positions.items()):
            now_price = self._price_now(position)
            then_price = self._price_then(desk_id, key, at)
            if now_price is None or then_price is None or then_price <= 0:
                continue
            asset = position.instrument.asset_class
            if asset == "event":
                moved = abs(now_price - then_price)
                threshold = money(self.config["event_move_dollars"])
                if moved >= threshold:
                    found.append(Trigger(
                        "price_move",
                        f"{position.instrument.symbol} moved {text(moved)} (from {text(then_price)} to {text(now_price)}) in the last hour",
                        key,
                    ))
            else:
                pct = abs(now_price / then_price - 1)
                threshold = money(self.config["crypto_move_pct" if asset == "crypto" else "equity_move_pct"])
                if pct >= threshold:
                    found.append(Trigger(
                        "price_move",
                        f"{position.instrument.symbol} moved {pct * 100:.2f}% (from {text(then_price)} to {text(now_price)}) in the last hour",
                        key,
                    ))
        return found

    def fills(self, desk_id: str, seen_after: int) -> list[Trigger]:
        found: list[Trigger] = []
        for event in self.service.log.read(kind="broker.fill", after=seen_after, limit=2000):
            payload = event.payload
            if payload.get("desk_id") != desk_id:
                continue
            instrument = payload.get("instrument") or {}
            found.append(Trigger(
                "fill",
                f"fill: {payload.get('side')} {payload.get('quantity')} {instrument.get('symbol')} at {payload.get('price')}"
                + (" (shadow)" if payload.get("shadow") else ""),
                _key_of(instrument),
            ))
        return found

    def new_markets(self, manifest: Any, positions: Mapping[str, Any]) -> list[Trigger]:
        if "event" not in manifest.instruments.asset_classes:
            return []
        series = set()
        for position in positions.values():
            if position.instrument.asset_class != "event":
                continue
            ticker = str(position.instrument.market_id or position.instrument.symbol or "")
            if ticker:
                series.add(ticker.split("-")[0].upper())
        for event in self.service.log.read(stream=manifest.stream, kind="desk.forecast", limit=500):
            market = str(event.payload.get("market") or "")
            if market:
                series.add(market.split("-")[0].upper())
        if not series:
            return []
        source = self.service.source("event")
        if source is None:
            return []
        try:
            rows = self.service.event_index(source)
        except Exception:
            return []
        known = self._known_markets.setdefault(manifest.id, set())
        first_pass = not known
        found: list[Trigger] = []
        for row in rows:
            ticker = str(row.get("ticker") or "")
            if not ticker or str(row.get("series_ticker") or ticker.split("-")[0]).upper() not in series:
                continue
            if ticker in known:
                continue
            known.add(ticker)
            if not first_pass:
                found.append(Trigger("new_market", f"new market {ticker}: {str(row.get('title') or '')[:160]}", None))
        return found

    def headlines(self, manifest: Any, positions: Mapping[str, Any], at: str) -> list[Trigger]:
        if not self.config.get("headline", True) or not positions:
            return []
        last = self._last_headline_check.get(manifest.id)
        if last is not None and _seconds_between(last, at) < int(self.config["headline_check_seconds"]):
            return []
        self._last_headline_check[manifest.id] = at
        source = self.service.source("news")
        if source is None:
            return []
        reader = getattr(source, "search", None) or getattr(source, "headlines", None)
        if reader is None:
            return []
        known = self._known_headlines.setdefault(manifest.id, set())
        first_pass = not known
        found: list[Trigger] = []
        for key, position in sorted(positions.items()):
            symbol = str(position.instrument.symbol or "")
            try:
                rows = list(reader(symbol, limit=5))
            except Exception:
                continue
            for row in rows:
                title = str((row or {}).get("title") or (row or {}).get("headline") or "").strip()
                if not title or title in known:
                    continue
                known.add(title)
                if not first_pass:
                    found.append(Trigger("headline", f"headline for {symbol}: {title[:200]}", key))
        return found

    def triggers_for(self, manifest: Any, at: str, *, fills_after: int) -> list[Trigger]:
        positions = self.positions_of(manifest.id, at)
        found: list[Trigger] = []
        found.extend(self.fills(manifest.id, fills_after))
        found.extend(self.price_moves(manifest.id, positions, at))
        found.extend(self.new_markets(manifest, positions))
        found.extend(self.headlines(manifest, positions, at))
        return found

    # ------------------------------------------------------------------ deciding
    def packet(self, manifest: Any, trigger: Trigger, positions: Mapping[str, Any]) -> str:
        book = [
            f"- {p.instrument.symbol} ({p.instrument.asset_class}): {text(p.quantity)} at {text(p.average_cost)}, mark {text(p.mark)}"
            for p in positions.values()
        ] or ["(flat)"]
        return "\n".join(
            [
                f"Desk: {manifest.name} ({manifest.id})",
                f"Persona: {manifest.persona[:600]}",
                f"Mandate: {manifest.mandate[:900]}",
                "Book:",
                *book,
                f"Event ({trigger.kind}): {trigger.detail}",
            ]
        )

    def decide(self, manifest: Any, trigger: Trigger, positions: Mapping[str, Any], at: str) -> tuple[str, str, Decimal]:
        provider = self.service.provider
        if provider is None:
            return "ignore", "no model provider configured; the watch cannot judge", ZERO
        stamp = at[:16].replace(":", "").replace("-", "")
        try:
            response = provider.respond(
                str(self.config["profile"]),
                [
                    {"role": "system", "content": INSTRUCTIONS},
                    {"role": "user", "content": self.packet(manifest, trigger, positions)},
                ],
                tools=None,
                desk_id=manifest.id,
                session_id=None,
                request_key=f"watch:{manifest.id}:{trigger.kind}:{stamp}",
                reasoning_effort=str(self.config["reasoning_effort"]),
                max_output_tokens=int(self.config["max_output_tokens"]),
                desk_cap_usd_per_day=manifest.budget_usd_per_day,
            )
        except Exception as exc:
            code = getattr(exc, "code", None) or type(exc).__name__
            return "ignore", f"the watch could not ask the model ({code})", ZERO
        cost = getattr(response, "cost_usd", None)
        cost = money(cost) if cost is not None else ZERO
        parsed = parse_decision(getattr(response, "output_text", None))
        if parsed is None:
            return "ignore", "the watch model gave no usable verdict", cost
        decision, reason = parsed
        return decision, reason, cost

    # ------------------------------------------------------------------ the pass
    def expected_session_id(self, desk_id: str, trigger_name: str) -> str:
        stamp = time.strftime("%Y%m%d-%H%M", time.gmtime(self.service.clock()))
        return f"{desk_id}:{stamp}:{trigger_name}"

    def tick(self, at: str | None = None, *, allow_shadow: bool = True) -> list[dict[str, Any]]:
        at = iso_time(at) if at is not None else self.service.now()
        if not self.enabled:
            return []
        if self._last_check is not None and _seconds_between(self._last_check, at) < int(self.config["check_seconds"]):
            return []
        self._last_check = at
        fills_after = self._fill_seq
        self._fill_seq = int(self.service.log.latest_seq())
        decisions: list[dict[str, Any]] = []
        for desk_id, manifest in sorted(self.service.active_manifests().items()):
            try:
                if not self.eligible(manifest, at, allow_shadow=allow_shadow):
                    continue
                triggers = self.triggers_for(manifest, at, fills_after=fills_after)
            except Exception as exc:
                self.service.alert("warning", f"night watch on {desk_id} failed: {type(exc).__name__}: {exc}")
                continue
            if not triggers:
                continue
            trigger = triggers[0]
            positions = self.positions_of(desk_id, at)
            decision, reason, cost = self.decide(manifest, trigger, positions, at)
            session_id = None
            if decision == "wake":
                trigger_name = f"watch:{trigger.kind}"
                session_id = self.expected_session_id(desk_id, trigger_name)
                self._last_wake[desk_id] = at
                self.service.start_sessions([(manifest, trigger_name)])
            payload = {
                "trigger": trigger.kind,
                "detail": trigger.detail[:300],
                "decision": decision,
                "reason": reason[:500],
                "cost_usd": text(cost),
                "session_id": session_id,
            }
            self.service.log.append(
                manifest.stream, "desk.watch", payload, id=f"watch:{desk_id}:{trigger.kind}:{at}", at=at
            )
            decisions.append({"desk_id": desk_id, **payload})
        return decisions

    def summary(self, at: str | None = None) -> dict[str, Any]:
        """The checkpoint's `watch` block: what the night desk did today."""
        at = iso_time(at) if at is not None else self.service.now()
        day = at[:10]
        triggers = wakes = 0
        cost = ZERO
        last: str | None = None
        for event in self.service.log.read(kind="desk.watch", limit=10_000):
            if not event.at.startswith(day):
                continue
            triggers += 1
            if event.payload.get("decision") == "wake":
                wakes += 1
            try:
                cost += money(event.payload.get("cost_usd") or 0)
            except (ValueError, ArithmeticError, TypeError):
                pass
            if last is None or event.at > last:
                last = event.at
        return {
            "triggers_today": triggers,
            "wakes_today": wakes,
            "last_trigger_at": last,
            "cost_today_usd": text(cost),
        }


def _key_of(instrument: Mapping[str, Any] | None) -> str | None:
    if not isinstance(instrument, Mapping):
        return None
    try:
        from .broker import Instrument

        return Instrument.from_dict(dict(instrument)).key
    except Exception:
        return None


__all__ = ["DEFAULT_CONFIG", "INSTRUCTIONS", "NightWatch", "TRIGGER_KINDS", "Trigger", "parse_decision"]
