"""Calibration: every probability a desk states, scored when the market resolves.

A forecaster who cannot see their own calibration cannot improve it. This module keeps the
record the post-mortem reads and the site charts:

* A desk states a probability with the `record_forecast` tool, whether or not it trades. The
  statement is a public `desk.forecast` event on the desk's stream; the probability is always
  for the YES outcome of the named market, whatever leg the desk would buy.
* A market resolves. The floor learns that from its own settlement path (`desk.outcome`, or a
  settlement `broker.fill`) when a desk held the market, and from the venue itself, through a
  resolver the service supplies, when none did -- the honest case, because most forecasts are
  made about markets the desk declined to trade. Each resolution is written once as a private
  `lab.resolution` event so the venue is asked once, and only the scored record leaves the box.
* Scoring is the Brier score, `(probability - outcome)^2`, where the outcome is 1 for YES and
  0 for NO; 0 is perfect, 0.25 is a coin flip, and a confident wrong call costs up to 1. The
  reliability table groups forecasts into deciles of stated probability and compares the mean
  forecast in each with the share that resolved YES: a calibrated desk's rows lie on the
  diagonal.
* Once a day, one public `lab.calibration` event per scope -- each desk with forecasts, each
  family, each generation of a family, and the floor -- with deterministic ids, so a missed
  tick republishes nothing twice.

Everything here is arithmetic on the event log. Standard library only.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from typing import Any, Callable, Iterable, Mapping

from .events import Event, EventLog, now_iso
from .ledger import iso_time, parse_iso

FORECAST_KIND = "desk.forecast"
RESOLUTION_KIND = "lab.resolution"
CALIBRATION_KIND = "lab.calibration"
SCOPES = ("desk", "family", "generation", "floor")
BINS = 10
PLACES = Decimal("0.0001")
ZERO = Decimal(0)
ONE = Decimal(1)
MAX_REASONING = 600
MAX_MARKET = 80
#: A forecast with no stated resolution date is asked about after this many days.
DEFAULT_RESOLVE_AFTER_DAYS = 1

Resolver = Callable[[str, str], "Resolution | Mapping[str, Any] | None"]


class CalibrationError(ValueError):
    """A forecast that cannot be recorded as written."""


def normalize_probability(value: Any) -> Decimal:
    """A probability as a Decimal in [0, 1]; `62%` and `0.62` are the same number."""
    if isinstance(value, bool) or value is None:
        raise CalibrationError("probability must be a number between 0 and 1")
    raw = str(value).strip()
    try:
        number = Decimal(raw[:-1].strip()) / 100 if raw.endswith("%") else Decimal(raw)
    except InvalidOperation:
        raise CalibrationError(f"probability {value!r} is not a number") from None
    if not number.is_finite() or number < 0 or number > 1:
        raise CalibrationError("probability must be between 0 and 1")
    return number.quantize(PLACES, rounding=ROUND_HALF_EVEN)


def market_key(venue: Any, market: Any) -> tuple[str, str]:
    return (str(venue or "").strip().lower(), str(market or "").strip().upper())


def bin_of(probability: Decimal) -> int:
    """Decile index of a probability: 0.0-0.1 is bin 0, and 1.0 sits in the top bin."""
    return min(BINS - 1, int(probability * BINS))


def bin_label(index: int) -> str:
    low = Decimal(index) / BINS
    high = Decimal(index + 1) / BINS
    return f"{low:.1f}-{high:.1f}"


def venue_of_instrument_key(key: Any, default: str = "kalshi") -> str:
    """`event:CPI:kalshi:yes:CPI-26SEP` -> `kalshi`. The key format is `Instrument.key`."""
    parts = str(key or "").split(":")
    return parts[2].lower() if len(parts) >= 3 and parts[2] else default


@dataclass(frozen=True)
class Forecast:
    event_id: str
    desk_id: str
    session_id: str | None
    market: str
    venue: str
    probability: Decimal
    market_price: Decimal | None
    side: str | None
    resolves_at: str | None
    reasoning: str
    at: str

    @property
    def key(self) -> tuple[str, str]:
        return market_key(self.venue, self.market)


@dataclass(frozen=True)
class Resolution:
    market: str
    venue: str
    result: str  # "yes" | "no"
    settled_at: str
    source: str

    @property
    def key(self) -> tuple[str, str]:
        return market_key(self.venue, self.market)

    @property
    def outcome(self) -> Decimal:
        return ONE if self.result == "yes" else ZERO


@dataclass(frozen=True)
class Scored:
    forecast: Forecast
    resolution: Resolution

    @property
    def brier(self) -> Decimal:
        return ((self.forecast.probability - self.resolution.outcome) ** 2).quantize(PLACES)


def _stream_desk(stream: str) -> str | None:
    return stream[len("desk:") :] if stream.startswith("desk:") else None


class CalibrationLedger:
    """The forecast record folded from the log, and the writers that extend it."""

    def __init__(
        self,
        log: EventLog,
        manifests: Mapping[str, Any] | None = None,
        *,
        clock: Callable[[], float] = time.time,
    ):
        self.log = log
        self.manifests = manifests if manifests is not None else {}
        self.clock = clock

    def now(self) -> str:
        return now_iso(self.clock)

    # ------------------------------------------------------------------ writers
    def record_forecast(
        self,
        *,
        desk_id: str,
        stream: str,
        session_id: str | None,
        market: Any,
        venue: Any,
        probability: Any,
        market_price: Any = None,
        side: Any = None,
        resolves_at: Any = None,
        reasoning: Any = "",
        at: str | None = None,
    ) -> Event:
        """Append one `desk.forecast`. The id is the desk, the market and the moment."""
        ticker = str(market or "").strip().upper()
        if not ticker or len(ticker) > MAX_MARKET:
            raise CalibrationError("market must name a contract, at most 80 characters")
        venue_name = str(venue or "").strip().lower()
        if not venue_name:
            raise CalibrationError("venue is required")
        stated = normalize_probability(probability)
        price = None
        if market_price not in (None, ""):
            price = normalize_probability(market_price)
        leg = None
        if side not in (None, ""):
            leg = str(side).strip().lower()
            if leg not in ("yes", "no"):
                raise CalibrationError("side must be yes or no")
        due = None
        if resolves_at not in (None, ""):
            try:
                due = iso_time(parse_iso(str(resolves_at)))
            except Exception:
                raise CalibrationError("resolves_at must be an ISO-8601 time") from None
        stamp = at or self.now()
        payload = {
            "session_id": session_id,
            "market": ticker,
            "venue": venue_name,
            "probability": format(stated, "f"),
            "market_price": None if price is None else format(price, "f"),
            "side": leg,
            "resolves_at": due,
            "reasoning": str(reasoning or "").strip()[:MAX_REASONING],
        }
        return self.log.append(
            stream, FORECAST_KIND, payload, id=f"forecast:{desk_id}:{ticker}:{stamp}", at=stamp
        )

    def record_resolution(
        self, *, market: Any, venue: Any, result: Any, settled_at: Any, source: str = "venue"
    ) -> Event | None:
        """Write the private fact that a market resolved. Idempotent on the market."""
        venue_name, ticker = market_key(venue, market)
        verdict = str(result or "").strip().lower()
        if verdict not in ("yes", "no") or not ticker or not venue_name:
            return None
        stamp = self.now()
        if settled_at:
            try:
                stamp = iso_time(parse_iso(str(settled_at)))
            except Exception:
                stamp = self.now()
        payload = {
            "market": ticker,
            "venue": venue_name,
            "result": verdict,
            "settled_at": stamp,
            "source": str(source)[:40],
        }
        return self.log.append(
            "lab", RESOLUTION_KIND, payload, id=f"resolution:{venue_name}:{ticker}", at=stamp
        )

    # ------------------------------------------------------------------ readers
    def forecasts(self) -> list[Forecast]:
        out: list[Forecast] = []
        for event in self.log.read(kind=FORECAST_KIND, limit=10_000):
            p = event.payload
            desk_id = _stream_desk(event.stream)
            if desk_id is None:
                continue
            try:
                probability = normalize_probability(p.get("probability"))
            except CalibrationError:
                continue
            price = None
            if p.get("market_price") not in (None, ""):
                try:
                    price = normalize_probability(p.get("market_price"))
                except CalibrationError:
                    price = None
            out.append(
                Forecast(
                    event_id=event.id,
                    desk_id=desk_id,
                    session_id=p.get("session_id") if isinstance(p.get("session_id"), str) else None,
                    market=str(p.get("market") or "").upper(),
                    venue=str(p.get("venue") or "").lower(),
                    probability=probability,
                    market_price=price,
                    side=p.get("side") if p.get("side") in ("yes", "no") else None,
                    resolves_at=p.get("resolves_at") if isinstance(p.get("resolves_at"), str) else None,
                    reasoning=str(p.get("reasoning") or ""),
                    at=event.at,
                )
            )
        return out

    def resolutions(self) -> dict[tuple[str, str], Resolution]:
        """Every market the floor knows the result of, keyed by (venue, market).

        Three sources, in order of authority: the recorded `lab.resolution` facts, the public
        `desk.outcome` scores, and settlement fills. The earliest settled time wins a tie.
        """
        found: dict[tuple[str, str], Resolution] = {}

        def keep(resolution: Resolution) -> None:
            current = found.get(resolution.key)
            if current is None or resolution.settled_at < current.settled_at:
                found[resolution.key] = resolution

        for event in self.log.read(kind=RESOLUTION_KIND, limit=10_000):
            p = event.payload
            if p.get("result") in ("yes", "no"):
                keep(
                    Resolution(
                        market=str(p.get("market") or "").upper(),
                        venue=str(p.get("venue") or "").lower(),
                        result=str(p["result"]),
                        settled_at=str(p.get("settled_at") or event.at),
                        source=str(p.get("source") or "recorded"),
                    )
                )
        for event in self.log.read(kind="desk.outcome", limit=10_000):
            p = event.payload
            result = str(p.get("result") or "").strip().lower()
            market = str(p.get("market_id") or "").strip().upper()
            if result in ("yes", "no") and market:
                keep(
                    Resolution(
                        market=market,
                        venue=venue_of_instrument_key(p.get("instrument")),
                        result=result,
                        settled_at=event.at,
                        source="outcome",
                    )
                )
        for event in self.log.read(kind="broker.fill", limit=10_000):
            p = event.payload
            if not p.get("settlement"):
                continue
            result = str(p.get("result") or "").strip().lower()
            instrument = p.get("instrument") if isinstance(p.get("instrument"), dict) else {}
            market = str(instrument.get("market_id") or "").strip().upper()
            venue = str(p.get("venue") or instrument.get("venue") or "").lower()
            if venue == "shadow":
                venue = str(instrument.get("venue") or "kalshi").lower()
            if result in ("yes", "no") and market:
                keep(
                    Resolution(
                        market=market,
                        venue=venue or "kalshi",
                        result=result,
                        settled_at=str(p.get("at") or event.at),
                        source="settlement",
                    )
                )
        return found

    def scored(self, at: str | None = None) -> list[Scored]:
        """Forecasts joined with their resolutions, forecast order. Unresolved ones are absent,
        as is any forecast made after the market resolved: a call made with the answer known
        is not a forecast."""
        stamp = at or self.now()
        resolutions = self.resolutions()
        out: list[Scored] = []
        for forecast in self.forecasts():
            if forecast.at > stamp:
                continue
            resolution = resolutions.get(forecast.key)
            if resolution is None or resolution.settled_at > stamp:
                continue
            if forecast.at > resolution.settled_at:
                continue
            out.append(Scored(forecast, resolution))
        return out

    def unresolved(self, at: str | None = None) -> list[Forecast]:
        stamp = at or self.now()
        resolutions = self.resolutions()
        return [f for f in self.forecasts() if f.at <= stamp and f.key not in resolutions]

    # ------------------------------------------------------------------ resolving
    def due_markets(
        self, at: str | None = None, *, wait_days: int = DEFAULT_RESOLVE_AFTER_DAYS
    ) -> list[tuple[str, str]]:
        """Markets with an unresolved forecast that is old enough to ask about.

        A forecast that named its resolution time is due once that time has passed; one that
        did not is due `wait_days` after it was made. Each market appears once, oldest first.
        """
        stamp = at or self.now()
        moment = parse_iso(stamp)
        due: dict[tuple[str, str], str] = {}
        for forecast in self.unresolved(stamp):
            if forecast.resolves_at:
                ready = forecast.resolves_at <= stamp
            else:
                ready = (moment - parse_iso(forecast.at)).total_seconds() >= wait_days * 86400
            if ready and (forecast.key not in due or forecast.at < due[forecast.key]):
                due[forecast.key] = forecast.at
        return [key for key, _ in sorted(due.items(), key=lambda kv: (kv[1], kv[0]))]

    def resolve(
        self, at: str | None = None, resolver: Resolver | None = None, *, limit: int = 20
    ) -> list[Resolution]:
        """Ask the resolver about due markets, at most `limit` of them, and record answers.

        The resolver takes `(venue, market)` and returns a `Resolution`, a mapping with
        `result` and optionally `settled_at` and `source`, or None when the market is still
        open. A resolver failure on one market never stops the others.
        """
        if resolver is None:
            return []
        recorded: list[Resolution] = []
        for venue, market in self.due_markets(at)[: max(0, int(limit))]:
            try:
                answer = resolver(venue, market)
            except Exception:
                continue
            if answer is None:
                continue
            if isinstance(answer, Resolution):
                result, settled_at, source = answer.result, answer.settled_at, answer.source
            elif isinstance(answer, Mapping):
                result = answer.get("result")
                settled_at = answer.get("settled_at") or at or self.now()
                source = str(answer.get("source") or "venue")
            else:
                continue
            event = self.record_resolution(
                market=market, venue=venue, result=result, settled_at=settled_at, source=source
            )
            if event is not None:
                p = event.payload
                recorded.append(
                    Resolution(p["market"], p["venue"], p["result"], p["settled_at"], p["source"])
                )
        return recorded

    # ------------------------------------------------------------------ summaries
    def _members(self, scope: str, desk_id: str | None, family: str | None, generation: int | None):
        if scope == "desk":
            return None if desk_id is None else {desk_id}
        if scope == "floor":
            return None
        members = set()
        for manifest_id, manifest in self.manifests.items():
            if getattr(manifest, "family", None) != family:
                continue
            if scope == "generation" and int(getattr(manifest, "generation", 0) or 0) != generation:
                continue
            members.add(manifest_id)
        return members

    def summary(
        self,
        scope: str = "floor",
        *,
        desk_id: str | None = None,
        family: str | None = None,
        generation: int | None = None,
        at: str | None = None,
        since: str | None = None,
    ) -> dict[str, Any]:
        """The calibration of one scope: count, Brier, reliability deciles and the worst bin."""
        if scope not in SCOPES:
            raise ValueError(f"unknown scope {scope!r}")
        stamp = at or self.now()
        members = self._members(scope, desk_id, family, generation)
        rows = [
            row
            for row in self.scored(stamp)
            if (members is None or row.forecast.desk_id in members)
            and (since is None or row.forecast.at >= since)
            and not (scope == "desk" and members is None)
        ]
        bins: dict[int, list[Scored]] = {}
        for row in rows:
            bins.setdefault(bin_of(row.forecast.probability), []).append(row)
        reliability = []
        worst: dict[str, Any] | None = None
        for index in sorted(bins):
            group = bins[index]
            n = Decimal(len(group))
            forecast_mean = (sum((r.forecast.probability for r in group), ZERO) / n).quantize(PLACES)
            outcome_rate = (sum((r.resolution.outcome for r in group), ZERO) / n).quantize(PLACES)
            entry = {
                "bin": bin_label(index),
                "forecast_mean": format(forecast_mean, "f"),
                "outcome_rate": format(outcome_rate, "f"),
                "n": len(group),
            }
            reliability.append(entry)
            gap = abs(forecast_mean - outcome_rate)
            if worst is None or gap > worst["_gap"]:
                worst = {**entry, "_gap": gap}
        n = len(rows)
        brier = (
            (sum((r.brier for r in rows), ZERO) / Decimal(n)).quantize(PLACES) if n else None
        )
        first = min((r.forecast.at for r in rows), default=None)
        return {
            "scope": scope,
            "desk_id": desk_id if scope == "desk" else None,
            "family": family if scope in ("family", "generation") else None,
            "generation": generation if scope == "generation" else None,
            "n": n,
            "brier": None if brier is None else format(brier, "f"),
            "reliability": reliability,
            "worst_bin": None if worst is None else {k: v for k, v in worst.items() if k != "_gap"},
            "as_of": stamp,
            "since": since or first,
        }

    def summaries(self, at: str | None = None) -> list[dict[str, Any]]:
        """One summary per scope that has at least one scored forecast."""
        stamp = at or self.now()
        rows = self.scored(stamp)
        if not rows:
            return []
        out: list[dict[str, Any]] = []
        desks = sorted({r.forecast.desk_id for r in rows})
        for desk_id in desks:
            out.append(self.summary("desk", desk_id=desk_id, at=stamp))
        families: dict[str, set[int]] = {}
        for desk_id in desks:
            manifest = self.manifests.get(desk_id)
            if manifest is None:
                continue
            families.setdefault(str(manifest.family), set()).add(int(manifest.generation))
        for family in sorted(families):
            row = self.summary("family", family=family, at=stamp)
            if row["n"]:
                out.append(row)
            for generation in sorted(families[family]):
                row = self.summary("generation", family=family, generation=generation, at=stamp)
                if row["n"]:
                    out.append(row)
        out.append(self.summary("floor", at=stamp))
        return [row for row in out if row["n"]]

    def publish_daily(self, now: Any = None, *, day: str | None = None) -> list[Event]:
        """One public `lab.calibration` per scope for a finished UTC day. Idempotent.

        `day` defaults to the UTC day before `now`, like `ResultsLedger.publish_daily`: the
        first tick after midnight writes yesterday's records and later ticks find them taken.
        The record is cumulative -- everything scored up to the end of that day -- because a
        calibration is a running judgment, not a daily count.
        """
        end = iso_time(now) if now is not None else self.now()
        date = str(day) if day else _shift_day(end, -1)
        stop = min(f"{date}T23:59:59.999Z", end)
        events: list[Event] = []
        for row in self.summaries(stop):
            key = {
                "desk": row["desk_id"],
                "family": row["family"],
                "generation": f"{row['family']}:g{row['generation']}",
                "floor": "floor",
            }[row["scope"]]
            event_id = f"calibration:{date}:{row['scope']}:{key}"
            existing = self.log.get(event_id)
            if existing is not None:
                events.append(existing)
                continue
            payload = {k: v for k, v in row.items() if k != "worst_bin"}
            events.append(self.log.append("lab", CALIBRATION_KIND, payload, id=event_id, at=stop))
        return events

    def brief(self, desk_id: str, at: str | None = None) -> str:
        """The two sentences a post-mortem needs. Empty when the desk has scored nothing."""
        row = self.summary("desk", desk_id=desk_id, at=at)
        if not row["n"]:
            pending = [f for f in self.unresolved(at) if f.desk_id == desk_id]
            if pending:
                return (
                    f"Calibration: {len(pending)} forecast{'s' if len(pending) != 1 else ''} "
                    "recorded, none resolved yet."
                )
            return ""
        worst = row["worst_bin"] or {}
        pending = len([f for f in self.unresolved(at) if f.desk_id == desk_id])
        parts = [
            f"Calibration: {row['n']} forecast{'s' if row['n'] != 1 else ''} scored, "
            f"Brier {row['brier']} (0 is perfect, 0.25 is a coin flip).",
        ]
        if worst:
            parts.append(
                f"Worst decile {worst['bin']}: you said {worst['forecast_mean']} on average and "
                f"{worst['outcome_rate']} resolved yes (n={worst['n']})."
            )
        if pending:
            parts.append(f"{pending} more await{'s' if pending == 1 else ''} resolution.")
        return " ".join(parts)


def _shift_day(stamp: str, days: int) -> str:
    from datetime import timedelta

    return (parse_iso(stamp) + timedelta(days=days)).strftime("%Y-%m-%d")


__all__ = [
    "BINS",
    "CALIBRATION_KIND",
    "CalibrationError",
    "CalibrationLedger",
    "FORECAST_KIND",
    "Forecast",
    "RESOLUTION_KIND",
    "Resolution",
    "SCOPES",
    "Scored",
    "bin_label",
    "bin_of",
    "market_key",
    "normalize_probability",
]
