"""The results ledger: what the architecture earned, folded out of the event log.

Every other module in this package decides something. This one only *counts*, so the floor can be
judged on numbers instead of impressions: how many sessions a desk ran, how many turns and tool
calls each one took, what Sail charged for them, how many decisions came out the other end, how
many of those were right, what they made, and how much of that survives the inference bill.

Nothing here reads a broker, a provider or a manifest file. The event log is the whole input:

* `desk.session_started` / `desk.session_ended` -- sessions, turns and the desk's own cost count.
* `desk.tool_call` -- work per session.
* `desk.intent` -- the rationale (which is where a stated probability lives) and the clock from
  the start of a session to its first order.
* `provider.request` -- the money. These are **private** events; the numbers folded out of them
  are aggregates and are safe to publish, the prompts and response ids never leave the box.
* `broker.fill` -- decisions, fees, and (for everything that is not an event contract) closed
  trades derived by average cost, exactly the way `DeskLedger` derives realized P&L.
* `desk.outcome` -- the scored record of a settled event contract: entry, exit, P&L and the
  sentence the desk gave when it opened the trade.
* `ledger.mark` -- the equity series the window's drawdown is measured on.
* `risk.decision` / `risk.review` -- what the deterministic engine and the critic refused.
* `desk.playbook_updated` / `desk.postmortem` -- whether the desk is still learning.

Three rollups come out: per desk, per **family** (the mandate: `earnings`, `filings`, `kalshi`,
`crypto`) and per **model profile** (`pro_flex`, `oss_asap`, ...), because the architectural
questions the owner actually asks are "which model earns its keep", "which mandate is worth
capital" and "which desk should be retired", and those are three different groupings of the same
events.

Money is `Decimal` inside and a string at the edge, like everywhere else in this package. A ratio
that is not defined (a win rate with no closed trades) is `None`, never a fabricated zero.

    results = ResultsLedger(log, manifests)
    report = results.report(7)
    print(markdown(report))

`ResultsLedger.publish_daily(log, now)` writes one public `lab.result` per UTC day so the site --
and the owner, a month later -- can read the same numbers without this module.
"""

from __future__ import annotations

import copy

import datetime as _dt
import re
import time
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from typing import Any, Callable, Iterable, Mapping

from .broker import money
from .events import Event, EventLog, canonical, now_iso
from .ledger import iso_time, parse_iso

ZERO = Decimal(0)
ONE = Decimal(1)

DEFAULT_WINDOW_DAYS = 7

#: Site rules, copied here so a `lab.result` is born publishable instead of being repaired by the
#: publisher: no angle brackets, nothing longer than 8000 characters, and -- our own cap -- a
#: metrics block small enough that a human can read a day's numbers in one screen.
MAX_STRING = 8000
MAX_METRICS_BYTES = 20_000
#: The site accepts at most this many keys in any one object (capital/schema.js MAX_PAYLOAD_KEYS).
MAX_METRICS_KEYS = 100

MONEY_PLACES = Decimal("0.0001")
RATIO_PLACES = Decimal("0.0001")
RATE_PLACES = Decimal("0.01")

#: `probability: 0.62`, `prob = 0.62`, `p=0.62`, `probability: 62%`. A desk that states its number
#: any other way is simply not scored for calibration: a guessed parse is worse than no Brier.
PROBABILITY = re.compile(
    r"\b(?:probability|prob|p)\s*[:=]\s*(\d{1,3}(?:\.\d+)?\s*%|\d{0,3}\.\d+|[01])(?!\d)",
    re.IGNORECASE,
)

#: Kinds the fold cares about. Everything else in the log is skipped without being parsed.
COUNTED_KINDS = frozenset(
    {
        "desk.session_started",
        "desk.session_ended",
        "desk.tool_call",
        "desk.intent",
        "desk.outcome",
        "desk.postmortem",
        "desk.playbook_updated",
        "provider.request",
        "broker.fill",
        "ledger.mark",
        "committee.allocation",
        "risk.decision",
        "risk.review",
        "evolution.promoted",
        "evolution.spawned",
    }
)

__all__ = [
    "ResultsLedger",
    "markdown",
    "metrics_block",
    "parse_probability",
    "verdict_for",
    "DEFAULT_WINDOW_DAYS",
]


# --------------------------------------------------------------------------- small helpers

def _q(value: Decimal, places: Decimal = MONEY_PLACES) -> Decimal:
    try:
        return value.quantize(places, rounding=ROUND_HALF_EVEN)
    except (InvalidOperation, ValueError):  # pragma: no cover - guarded by finite Decimals
        return value


def _usd(value: Decimal) -> str:
    return format(_q(value), "f")


def _num(value: Decimal, places: Decimal = RATIO_PLACES) -> str:
    return format(_q(value, places), "f")


def _div(numerator: Decimal, denominator: Decimal, places: Decimal = RATIO_PLACES) -> str | None:
    """A ratio, or None when it is not defined. Never a zero standing in for "no data"."""
    if denominator is None or denominator == 0:
        return None
    return format(_q(numerator / denominator, places), "f")


def _safe(value: str, limit: int = MAX_STRING) -> str:
    """One string the site will accept: no angle bracket, nothing over the length cap."""
    cleaned = str(value).replace("<", "‹")
    if len(cleaned) > limit:
        cleaned = cleaned[: limit - 1] + "…"
    return cleaned


def _shift_days(stamp: str, days: int) -> str:
    return iso_time(parse_iso(stamp) + _dt.timedelta(days=days))


def _key_of(instrument: Any) -> str:
    """The instrument key, from a payload dict, without building an `Instrument`.

    A malformed instrument must not abort a report, and `Instrument.from_dict` raises on one.
    """
    if not isinstance(instrument, Mapping):
        return str(instrument)
    parts = [
        str(instrument.get("asset_class") or ""),
        str(instrument.get("symbol") or ""),
        str(instrument.get("venue") or ""),
    ]
    for key in ("expiry", "strike", "right", "market_id"):
        value = instrument.get(key)
        if value:
            parts.append(str(value))
    return ":".join(parts)


def parse_probability(rationale: Any) -> Decimal | None:
    """The probability a desk stated in its own words, or None when it stated none.

    Reads `probability: 0.62`, `prob = 0.62`, `p=0.62` and `probability: 62%`. Anything outside
    0..1 is treated as absent: a desk that writes `p = 1.4` has not given a probability.
    """
    if not isinstance(rationale, str) or not rationale:
        return None
    match = PROBABILITY.search(rationale)
    if match is None:
        return None
    raw = match.group(1).strip()
    try:
        if raw.endswith("%"):
            value = Decimal(raw[:-1].strip()) / 100
        else:
            value = Decimal(raw)
    except InvalidOperation:
        return None
    if not value.is_finite() or value < 0 or value > 1:
        return None
    return value


def _dollars(value: Decimal) -> str:
    """A signed dollar amount for a human sentence: `+$3.10`, `-$0.0042`, `$0.41`."""
    places = Decimal("0.01") if abs(value) >= Decimal("0.01") or value == 0 else Decimal("0.0001")
    body = format(abs(_q(value, places)), "f")
    sign = "-" if value < 0 else ""
    return f"{sign}${body}"


def _signed(value: Decimal) -> str:
    return ("+" if value >= 0 else "") + _dollars(value)


def _percent(value: Decimal) -> str:
    """`0.75` -> `75`, `0.6667` -> `66.7`. For sentences, not tables."""
    pct = _q(value * 100, Decimal("0.1"))
    whole = pct.to_integral_value()
    return format(whole if pct == whole else pct, "f")


def _drawdown(marks: list[tuple[str, Decimal]], flows: list[tuple[str, Decimal]]) -> Decimal:
    """Worst peak-to-trough fall of marked equity inside the window, net of capital flows.

    The committee moving money into a desk is not a gain and moving it out is not a loss, so the
    running total of flows since the window opened is subtracted before the peak is taken. This
    is the window's drawdown; `DeskLedger.max_drawdown_pct` remains the desk's all-time number on
    the flow-neutral growth index.
    """
    if not marks:
        return ZERO
    ordered = sorted(marks, key=lambda row: row[0])
    moves = sorted(flows, key=lambda row: row[0])
    index = 0
    flowed = ZERO
    peak: Decimal | None = None
    worst = ZERO
    for at, equity in ordered:
        while index < len(moves) and moves[index][0] <= at:
            flowed += moves[index][1]
            index += 1
        value = equity - flowed
        if peak is None or value > peak:
            peak = value
        if peak is not None and peak > 0:
            fall = (peak - value) / peak
            if fall > worst:
                worst = fall
    return worst


# --------------------------------------------------------------------------- the fold

class _Roll:
    """Everything the fold knows about one desk. Raw numbers; rendering happens later."""

    def __init__(self, desk_id: str):
        self.desk_id = desk_id
        self.is_desk = False
        self.sessions: dict[str, dict[str, Any]] = {}
        self.tool_calls = 0
        self.reported_turns: dict[str, int] = {}
        self.provider_turns: dict[str, int] = {}
        self.requests = 0
        self.cost = ZERO
        self.profile_requests: dict[str, int] = {}
        self.profile_cost: dict[str, Decimal] = {}
        self.decisions = 0
        self.fees = ZERO
        self.closes: list[dict[str, Any]] = []
        self.brier_sum = ZERO
        self.brier_n = 0
        self.marks: list[tuple[str, Decimal]] = []
        self.flows: list[tuple[str, Decimal]] = []
        self.equity: Decimal | None = None
        self.reviews = 0
        self.blocks = 0
        self.checks = 0
        self.rejections = 0
        self.playbooks = 0
        self.playbook_version: str | None = None
        self.postmortems = 0
        self.shadow_fills = 0
        self.live_fills = 0
        self.positions: dict[str, tuple[Decimal, Decimal]] = {}
        self.rationales: dict[str, str] = {}
        self.family: str | None = None

    # -- sessions ---------------------------------------------------------
    def session(self, session_id: str) -> dict[str, Any]:
        row = self.sessions.get(session_id)
        if row is None:
            row = self.sessions[session_id] = {"started_at": None, "first_order_at": None}
        return row

    @property
    def turns(self) -> int:
        """Model turns the desk loop took, per session.

        `desk.session_ended.requests` is the desk's own count and is authoritative. A session
        still running at the window's edge has no `session_ended`, so the provider's own request
        count stands in; the critic's request rides on the desk's session id, which is why the
        desk's number wins whenever it exists.
        """
        total = 0
        for session_id in self.sessions:
            reported = self.reported_turns.get(session_id)
            total += reported if reported is not None else self.provider_turns.get(session_id, 0)
        return total


class ResultsLedger:
    """Folds the event log into per-desk, per-family and per-profile results for any window.

    `manifests` is optional: with it the report knows every desk's name, family, model profile and
    capital mode even when the desk did nothing in the window (a silent desk is a result). Without
    it the roster is discovered from the log itself.
    """

    def __init__(
        self,
        log: EventLog,
        manifests: Mapping[str, Any] | None = None,
        *,
        clock: Callable[[], float] = time.time,
    ):
        self.log = log
        self.manifests = dict(manifests or {})
        self.clock = clock

    # ------------------------------------------------------------------ public API
    #: A trailing-window report is reused for this long by every reader on the same tape
    #: (the checkpoint, the fitness policy, the lab): the fold walks the whole tape.
    REPORT_CACHE_SECONDS = 300.0
    _report_cache: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}

    def report(self, window_days: int = DEFAULT_WINDOW_DAYS, now: Any = None) -> dict[str, Any]:
        """Every metric for the trailing `window_days`, as plain dicts of strings. Shared for
        `REPORT_CACHE_SECONDS` per tape and window (a copy; callers may edit their own)."""
        end = iso_time(now) if now is not None else now_iso(self.clock)
        days = max(1, int(window_days))
        key = (str(getattr(self.log, "path", id(self.log))), days, tuple(sorted(self.manifests)))
        hit = ResultsLedger._report_cache.get(key)
        if hit is not None and time.monotonic() - hit[0] < ResultsLedger.REPORT_CACHE_SECONDS:
            return copy.deepcopy(hit[1])
        report = self.between(_shift_days(end, -days), end, window_days=days)
        ResultsLedger._report_cache[key] = (time.monotonic(), copy.deepcopy(report))
        return report

    def between(self, start: str, end: str, *, window_days: int | None = None) -> dict[str, Any]:
        """The same report over an explicit `[start, end]` window of log timestamps."""
        rolls, totals = self._fold(start, end)
        meta = self._meta(rolls, totals)
        desks: dict[str, dict[str, Any]] = {}
        raws: dict[str, dict[str, Any]] = {}
        for desk_id in sorted(rolls):
            roll = rolls[desk_id]
            known = desk_id in self.manifests
            if not (roll.is_desk or known):
                # Not a desk: the shadow book's own `settlement` fills and the committee's model
                # requests both name an id that never ran a session.
                continue
            raw = self._numbers(roll, meta[desk_id])
            if not known and not _active(raw):
                continue  # a desk that existed but did nothing in this window
            raws[desk_id] = raw
            desks[desk_id] = self._render(raw, meta[desk_id])

        members: dict[str, list[str]] = {}
        for desk_id in raws:
            members.setdefault(meta[desk_id]["family"], []).append(desk_id)
        families: dict[str, dict[str, Any]] = {}
        for family, ids in members.items():
            row = self._render(_merge(raws[i] for i in ids), {"family": family}, kind="family")
            row["desks"] = sorted(ids)
            families[family] = row

        profiles = self._profiles(rolls, raws, meta, totals)
        by_generation = self._generations(rolls, raws)  # leap: lab
        merged = _merge(raws.values())
        floor = self._render(merged, {}, kind="floor")
        # The floor's cost is every request the floor paid for, not only the ones a desk made:
        # the committee's memo and a spawned playbook are part of what the architecture costs.
        cost = totals["cost"]
        trading = merged["closed_pnl"] - merged["fees"]
        floor.update(
            {
                "desks": len(raws),
                "live_desks": sum(1 for d in raws if meta[d]["mode"] == "live"),
                "shadow_desks": sum(1 for d in raws if meta[d]["mode"] == "shadow"),
                "families": len(families),
                "sail_cost_usd": _usd(cost),
                "desk_sail_cost_usd": _usd(totals["desk_cost"]),
                "overhead_cost_usd": _usd(cost - totals["desk_cost"]),
                "requests": totals["requests"],
                "net_pnl_usd": _usd(trading - cost),
                "cost_per_decision_usd": _div(cost, Decimal(merged["decisions"]), MONEY_PLACES),
                "pnl_per_inference_dollar": _div(trading, cost, MONEY_PLACES),
            }
        )
        span = max(1, (parse_iso(end) - parse_iso(start)).days)
        return {
            "generated_at": end,
            "window_days": int(window_days if window_days is not None else span),
            "window": {"start": start, "end": end},
            "floor": floor,
            "desks": desks,
            "families": dict(sorted(families.items())),
            "profiles": profiles,
            "by_generation": by_generation,  # leap: lab
        }

    def _generations(
        self, rolls: Mapping[str, _Roll], raws: Mapping[str, Mapping[str, Any]]
    ) -> list[dict[str, Any]]:
        """leap: lab -- the improvement curve's rows: one per generation, across families.

        Generation comes from the manifest; a desk the roster no longer describes is left out
        rather than guessed at. `cost_adjusted_excess_pct` is the generation's net P&L after
        fees and inference over the capital it was working, in percentage points, where the
        capital is the sum of each desk's latest allocation inside the window (its last
        `committee.allocation` flow) and, failing that, its equity. It is the generation-level
        cousin of the gate's number, not the same arithmetic: the gate is time-weighted and
        benchmark-relative; this is a window's dollars over a window's capital, which is what a
        curve across generations can honestly compare.
        """
        groups: dict[int, list[str]] = {}
        for desk_id in raws:
            manifest = self.manifests.get(desk_id)
            if manifest is None:
                continue
            try:
                generation = int(getattr(manifest, "generation", 0) or 0)
            except (TypeError, ValueError):
                continue
            if generation > 0:
                groups.setdefault(generation, []).append(desk_id)
        rows: list[dict[str, Any]] = []
        for generation in sorted(groups):
            ids = sorted(groups[generation])
            merged = _merge(raws[i] for i in ids)
            cost = merged["cost"]
            trading = merged["closed_pnl"] - merged["fees"]
            capital = ZERO
            for desk_id in ids:
                roll = rolls[desk_id]
                if roll.flows:
                    capital += roll.flows[-1][1]
                elif roll.equity is not None:
                    capital += roll.equity
            if capital <= 0:
                continue  # no capital worked, no return to plot: the curve has no point here
            net = trading - cost
            brier = _div(merged["brier_sum"], Decimal(merged["brier_n"]))
            rows.append(
                {
                    "generation": generation,
                    "desks": len(ids),
                    "decisions": int(merged["decisions"]),
                    "cost_usd": _usd(cost),
                    "pnl_usd": _usd(trading),
                    "cost_adjusted_excess_pct": _div(net * 100, capital),
                    "brier": brier,
                    "pnl_per_inference_usd": _div(trading, cost, MONEY_PLACES) or "0.0000",
                }
            )
        return rows

    # ------------------------------------------------------------------ the fold
    def _fold(self, start: str, end: str) -> tuple[dict[str, _Roll], dict[str, Any]]:
        rolls: dict[str, _Roll] = {}
        totals = {"cost": ZERO, "desk_cost": ZERO, "requests": 0}
        targets: dict[str, Decimal] = {}
        promoted: dict[str, str] = {}
        shadow_flags: dict[str, bool] = {}

        def roll_for(desk_id: str) -> _Roll:
            roll = rolls.get(desk_id)
            if roll is None:
                roll = rolls[desk_id] = _Roll(desk_id)
            return roll

        for desk_id in self.manifests:
            roll_for(desk_id).is_desk = True

        walker = getattr(self.log, "iter_kinds", None)
        events = walker(COUNTED_KINDS) if callable(walker) else self.log.iter_all()
        for event in events:
            kind = event.kind
            if kind not in COUNTED_KINDS:
                continue
            at = event.at
            if at > end:
                continue
            desk_id = _desk_of(event)

            # Allocations and fills are folded from the beginning of the log: a flow tells the
            # drawdown what was capital rather than profit, and an average cost is only right if
            # every earlier fill was seen.
            if kind == "committee.allocation":
                for name, value in (event.payload.get("allocations") or {}).items():
                    try:
                        target = money(value)
                    except (TypeError, ValueError):
                        continue
                    flow = target - targets.get(name, ZERO)
                    targets[name] = target
                    if flow != 0 and start <= at <= end:
                        roll_for(name).flows.append((at, flow))
                for name, flag in (event.payload.get("shadow") or {}).items():
                    shadow_flags[name] = bool(flag)
                continue
            if kind == "broker.fill":
                if desk_id:
                    self._fill(roll_for(desk_id), event.payload, at, start, end)
                continue
            if kind == "evolution.promoted":
                to = event.payload.get("to")
                to = "shadow" if to == "paper" else to
                if isinstance(desk_id, str) and to in ("shadow", "live"):
                    promoted[desk_id] = to
                continue
            if kind == "evolution.spawned":
                family = event.payload.get("family")
                if isinstance(desk_id, str) and isinstance(family, str):
                    roll_for(desk_id).family = family
                continue
            if kind == "desk.intent":
                # Rationales are kept whatever their date: the intent that opened a trade closing
                # inside the window is usually older than the window.
                if desk_id:
                    roll = roll_for(desk_id)
                    if event.stream.startswith("desk:"):
                        roll.is_desk = True
                    said = event.payload.get("rationale")
                    if isinstance(said, str) and said.strip():
                        roll.rationales[_key_of(event.payload.get("instrument"))] = said
                    session_id = event.payload.get("session_id")
                    if isinstance(session_id, str) and start <= at <= end:
                        row = roll.session(session_id)
                        if row["first_order_at"] is None or at < row["first_order_at"]:
                            row["first_order_at"] = at
                continue

            if desk_id is None:
                continue
            if event.stream.startswith("desk:") or event.stream.startswith("ledger:"):
                roll_for(desk_id).is_desk = True
            if at < start:
                continue
            roll = roll_for(desk_id)

            if kind == "desk.session_started":
                session_id = event.payload.get("session_id")
                if isinstance(session_id, str):
                    row = roll.session(session_id)
                    if row["started_at"] is None or at < row["started_at"]:
                        row["started_at"] = at
            elif kind == "desk.session_ended":
                session_id = event.payload.get("session_id")
                if isinstance(session_id, str):
                    roll.session(session_id)
                    try:
                        roll.reported_turns[session_id] = int(event.payload.get("requests") or 0)
                    except (TypeError, ValueError):
                        pass
            elif kind == "desk.tool_call":
                roll.tool_calls += 1
            elif kind == "provider.request":
                roll.requests += 1
                totals["requests"] += 1
                profile = str(event.payload.get("profile") or "unknown")
                roll.profile_requests[profile] = roll.profile_requests.get(profile, 0) + 1
                cost = _cost_of(event.payload)
                roll.cost += cost
                roll.profile_cost[profile] = roll.profile_cost.get(profile, ZERO) + cost
                totals["cost"] += cost
                session_id = event.payload.get("session_id")
                if isinstance(session_id, str):
                    roll.provider_turns[session_id] = roll.provider_turns.get(session_id, 0) + 1
            elif kind == "desk.outcome":
                self._outcome(roll, event.payload, at)
            elif kind == "desk.postmortem":
                roll.postmortems += 1
            elif kind == "desk.playbook_updated":
                roll.playbooks += 1
                version = event.payload.get("version")
                if version is not None:
                    roll.playbook_version = str(version)
            elif kind == "ledger.mark":
                try:
                    equity = money(event.payload.get("equity"))
                except (TypeError, ValueError):
                    continue
                roll.marks.append((at, equity))
                roll.equity = equity
            elif kind == "risk.decision":
                reasons = event.payload.get("reasons") or []
                critic = any(str(r).startswith("critic:") for r in reasons)
                if critic:
                    # The critic's block is already counted as a review; counting it again here
                    # would make one refusal look like two.
                    continue
                roll.checks += 1
                if event.payload.get("approved") is False:
                    roll.rejections += 1
            elif kind == "risk.review":
                roll.reviews += 1
                if event.payload.get("verdict") == "block":
                    roll.blocks += 1

        for desk_id, roll in rolls.items():
            if roll.is_desk or desk_id in self.manifests:
                totals["desk_cost"] += roll.cost
        totals["promoted"] = promoted
        totals["shadow_flags"] = shadow_flags
        return rolls, totals

    def _fill(
        self, roll: _Roll, payload: Mapping[str, Any], at: str, start: str, end: str
    ) -> None:
        """Fold one fill: a decision inside the window, and a closed trade when it reduces."""
        instrument = payload.get("instrument")
        try:
            quantity = money(payload["quantity"])
            price = money(payload["price"])
            fee = money(payload.get("fee", "0"))
            multiplier = money((instrument or {}).get("multiplier", "1"))
        except (KeyError, TypeError, ValueError):
            return
        side = payload.get("side")
        if side not in ("buy", "sell") or quantity <= 0 or price < 0:
            return
        key = _key_of(instrument)
        asset_class = str((instrument or {}).get("asset_class") or "")
        inside = start <= at <= end
        if inside:
            roll.decisions += 1
            roll.fees += fee
            if payload.get("shadow"):
                roll.shadow_fills += 1
            else:
                roll.live_fills += 1

        signed = quantity if side == "buy" else -quantity
        held, average = roll.positions.get(key, (ZERO, ZERO))
        if held == 0:
            roll.positions[key] = (signed, price)
            return
        if (held > 0) == (signed > 0):
            after = held + signed
            roll.positions[key] = (after, (held * average + signed * price) / after)
            return
        closing = min(abs(signed), abs(held))
        direction = ONE if held > 0 else -ONE
        pnl = closing * (price - average) * direction * multiplier
        after = held + signed
        if after == 0:
            roll.positions.pop(key, None)
        elif (after > 0) != (held > 0):
            roll.positions[key] = (after, price)
        else:
            roll.positions[key] = (after, average)
        # An event contract is scored by its `desk.outcome`, which the settlement writes next to
        # the settling fill. Counting the fill too would double every Kalshi trade.
        if inside and asset_class != "event":
            roll.closes.append({"at": at, "pnl": pnl, "source": "fill"})

    def _outcome(self, roll: _Roll, payload: Mapping[str, Any], at: str) -> None:
        try:
            pnl = money(payload.get("pnl", "0"))
        except (TypeError, ValueError):
            return
        roll.closes.append({"at": at, "pnl": pnl, "source": "outcome"})
        result = str(payload.get("result") or "").strip().lower()
        if result not in ("yes", "no"):
            return
        said = payload.get("rationale_excerpt")
        probability = parse_probability(said)
        if probability is None:
            probability = parse_probability(roll.rationales.get(str(payload.get("instrument") or "")))
        if probability is None:
            return  # no stated probability, no calibration score: silence is not a forecast
        actual = ONE if result == "yes" else ZERO
        roll.brier_sum += (probability - actual) ** 2
        roll.brier_n += 1

    # ------------------------------------------------------------------ rollups
    def _meta(
        self, rolls: Mapping[str, _Roll], totals: Mapping[str, Any]
    ) -> dict[str, dict[str, Any]]:
        """Name, family, capital mode and model profile for every desk in the fold.

        A promotion is an event, so `evolution.promoted` outranks the manifest, exactly as in
        `committee.capital_mode`. Without a manifest the log still says enough: the committee's
        allocation flags a shadow sleeve, and a shadow desk's fills carry `shadow: true`.
        """
        promoted = totals.get("promoted") or {}
        shadow_flags = totals.get("shadow_flags") or {}
        out: dict[str, dict[str, Any]] = {}
        for desk_id, roll in rolls.items():
            manifest = self.manifests.get(desk_id)
            family = (
                getattr(manifest, "family", None)
                or roll.family
                or desk_id.split("-", 1)[0]
            )
            profile = getattr(getattr(manifest, "model", None), "profile", None)
            if not profile and roll.profile_requests:
                profile = max(sorted(roll.profile_requests), key=roll.profile_requests.get)
            mode = (
                promoted.get(desk_id)
                or getattr(manifest, "capital_mode", None)
                or ("shadow" if shadow_flags.get(desk_id) else None)
                or ("shadow" if roll.shadow_fills and not roll.live_fills else None)
            )
            out[desk_id] = {
                "desk_id": desk_id,
                "name": getattr(manifest, "name", None) or desk_id.replace("-", " ").title(),
                "family": str(family),
                "mode": mode or "live",
                "profile": profile,
            }
        return out

    def _numbers(self, roll: _Roll, meta: Mapping[str, Any]) -> dict[str, Any]:
        """Raw, summable numbers for one desk. Rendering and division happen in `_render`."""
        closed = [row["pnl"] for row in roll.closes]
        closed_pnl = sum(closed, ZERO)
        wins = sum(1 for value in closed if value > 0)
        shadow = meta.get("mode") == "shadow"
        seconds = _first_order_seconds(roll)
        return {
            "sessions": len(roll.sessions),
            "turns": roll.turns,
            "tool_calls": roll.tool_calls,
            "requests": roll.requests,
            "cost": roll.cost,
            "decisions": roll.decisions,
            "fees": roll.fees,
            "closed_trades": len(closed),
            "wins": wins,
            "closed_pnl": closed_pnl,
            "realized_pnl": ZERO if shadow else closed_pnl,
            "hypothetical_pnl": closed_pnl if shadow else ZERO,
            "brier_sum": roll.brier_sum,
            "brier_n": roll.brier_n,
            "reviews": roll.reviews,
            "blocks": roll.blocks,
            "checks": roll.checks,
            "rejections": roll.rejections,
            "playbook_versions": roll.playbooks,
            "playbook_version": roll.playbook_version,
            "postmortems": roll.postmortems,
            "first_order_seconds": sum(seconds, ZERO),
            "sessions_with_order": len(seconds),
            "max_drawdown": _drawdown(roll.marks, roll.flows),
            "equity": roll.equity,
        }

    def _render(
        self, raw: Mapping[str, Any], meta: Mapping[str, Any], *, kind: str = "desk"
    ) -> dict[str, Any]:
        """One rollup as plain data: ints stay ints, every money and ratio is a string."""
        cost = raw["cost"]
        decisions = Decimal(raw["decisions"])
        closed = Decimal(raw["closed_trades"])
        sessions = Decimal(raw["sessions"])
        trading = raw["closed_pnl"] - raw["fees"]
        row: dict[str, Any] = {
            "sessions": raw["sessions"],
            "turns": raw["turns"],
            "turns_per_session": _div(Decimal(raw["turns"]), sessions, RATE_PLACES),
            "tool_calls": raw["tool_calls"],
            "tool_calls_per_session": _div(Decimal(raw["tool_calls"]), sessions, RATE_PLACES),
            "requests": raw["requests"],
            "sail_cost_usd": _usd(cost),
            "decisions": raw["decisions"],
            "fees_usd": _usd(raw["fees"]),
            "closed_trades": raw["closed_trades"],
            "wins": raw["wins"],
            "win_rate": _div(Decimal(raw["wins"]), closed),
            "avg_pnl_usd": _div(raw["closed_pnl"], closed, MONEY_PLACES),
            "closed_pnl_usd": _usd(raw["closed_pnl"]),
            "realized_pnl_usd": _usd(raw["realized_pnl"]),
            "hypothetical_pnl_usd": _usd(raw["hypothetical_pnl"]),
            "net_pnl_usd": _usd(trading - cost),
            "cost_per_decision_usd": _div(cost, decisions, MONEY_PLACES),
            "pnl_per_inference_dollar": _div(trading, cost, MONEY_PLACES),
            "max_drawdown_pct": _num(raw["max_drawdown"]),
            "brier": _div(raw["brier_sum"], Decimal(raw["brier_n"])),
            "brier_n": raw["brier_n"],
            "critic_reviews": raw["reviews"],
            "critic_blocks": raw["blocks"],
            "critic_block_rate": _div(Decimal(raw["blocks"]), Decimal(raw["reviews"])),
            "risk_decisions": raw["checks"],
            "risk_rejections": raw["rejections"],
            "risk_rejection_rate": _div(Decimal(raw["rejections"]), Decimal(raw["checks"])),
            "playbook_versions": raw["playbook_versions"],
            "postmortems": raw["postmortems"],
            "sessions_with_order": raw["sessions_with_order"],
            "seconds_to_first_order": _div(
                raw["first_order_seconds"], Decimal(raw["sessions_with_order"]), RATE_PLACES
            ),
        }
        if kind == "desk":
            row.update(
                {
                    "desk_id": meta.get("desk_id"),
                    "name": meta.get("name"),
                    "family": meta.get("family"),
                    "mode": meta.get("mode"),
                    "profile": meta.get("profile"),
                    "playbook_version": raw.get("playbook_version"),
                    "equity_usd": None if raw.get("equity") is None else _usd(raw["equity"]),
                }
            )
        elif kind == "family":
            row["family"] = meta.get("family")
        return row

    def _profiles(
        self,
        rolls: Mapping[str, _Roll],
        raws: Mapping[str, Mapping[str, Any]],
        meta: Mapping[str, Mapping[str, Any]],
        totals: Mapping[str, Any],
    ) -> dict[str, dict[str, Any]]:
        """Per-model-profile aggregates across desks.

        Two things are counted, and they are not the same thing. `requests` and `sail_cost_usd`
        are exact: every `provider.request` is charged to the profile that served it, including
        the critic's and the committee's. The desk-level results underneath are *attributed*: a
        desk's whole window is credited to the profile its manifest names (or, without a
        manifest, the profile that served most of its requests), because a decision cannot be
        split across the models that argued about it.
        """
        exact_requests: dict[str, int] = {}
        exact_cost: dict[str, Decimal] = {}
        for roll in rolls.values():
            for profile, count in roll.profile_requests.items():
                exact_requests[profile] = exact_requests.get(profile, 0) + count
            for profile, value in roll.profile_cost.items():
                exact_cost[profile] = exact_cost.get(profile, ZERO) + value

        attributed: dict[str, list[str]] = {}
        for desk_id in raws:
            profile = meta[desk_id].get("profile")
            if profile:
                attributed.setdefault(str(profile), []).append(desk_id)

        out: dict[str, dict[str, Any]] = {}
        for profile in sorted(set(exact_requests) | set(attributed)):
            desks = sorted(attributed.get(profile, []))
            row = self._render(_merge(raws[desk_id] for desk_id in desks), {}, kind="profile")
            row.update(
                {
                    "profile": profile,
                    "desks": desks,
                    # `desk_cost_usd` is everything the attributed desks spent, on every profile
                    # (their critic calls included). `sail_cost_usd` is what this profile itself
                    # was paid, by anyone. The per-decision numbers use the first.
                    "desk_cost_usd": row["sail_cost_usd"],
                    "requests": exact_requests.get(profile, 0),
                    "sail_cost_usd": _usd(exact_cost.get(profile, ZERO)),
                    "cost_per_request_usd": _div(
                        exact_cost.get(profile, ZERO),
                        Decimal(exact_requests.get(profile, 0)),
                        MONEY_PLACES,
                    ),
                }
            )
            out[profile] = row
        return out

    # ------------------------------------------------------------------ the public record
    @classmethod
    def publish_daily(
        cls,
        log: EventLog,
        now: Any = None,
        *,
        manifests: Mapping[str, Any] | None = None,
        day: str | None = None,
    ) -> Event | None:
        """Append one public `lab.result` for a complete UTC day. Idempotent on `lab:daily:<date>`.

        `day` defaults to the UTC day *before* `now`, so the record always covers a day that has
        finished and the caller needs no schedule of its own: a tick can call this on every pass,
        the first call after midnight writes yesterday's record, and every later call that day
        finds the id taken and does nothing.

        Returns the event (new or already stored), or None when the day had no activity at all --
        a floor that was switched off publishes silence rather than a row of zeroes.
        """
        end = iso_time(now) if now is not None else now_iso()
        date = str(day) if day else _shift_days(end, -1)[:10]
        event_id = f"lab:daily:{date}"
        existing = log.get(event_id)
        if existing is not None:
            return existing
        results = cls(log, manifests)
        start = f"{date}T00:00:00.000Z"
        stop = f"{date}T23:59:59.999Z"
        report = results.between(start, min(stop, end), window_days=1)
        floor = report["floor"]
        if not (
            floor["sessions"]
            or floor["requests"]
            or floor["decisions"]
            or floor["closed_trades"]
        ):
            return None
        payload = {
            "hypothesis_id": f"daily-{date}",
            "metrics": metrics_block(report),
            "verdict": verdict_for(report),
        }
        return log.append("lab", "lab.result", payload, id=event_id, at=min(stop, end))


def _active(raw: Mapping[str, Any]) -> bool:
    """Did this desk do anything at all inside the window?"""
    return any(
        int(raw.get(key) or 0)
        for key in (
            "sessions", "requests", "decisions", "closed_trades", "postmortems",
            "playbook_versions", "checks", "reviews",
        )
    )


def _desk_of(event: Event) -> str | None:
    stream = event.stream
    if stream.startswith("desk:"):
        return stream[len("desk:") :]
    if stream.startswith("ledger:"):
        return stream[len("ledger:") :]
    value = event.payload.get("desk_id")
    return value if isinstance(value, str) and value else None


def _cost_of(payload: Mapping[str, Any]) -> Decimal:
    value = payload.get("cost_usd")
    if value is None:
        return ZERO
    try:
        return money(value)
    except (TypeError, ValueError):
        return ZERO


def _first_order_seconds(roll: _Roll) -> list[Decimal]:
    """Seconds from each session's start to its first order intent, for sessions that ordered."""
    out: list[Decimal] = []
    for row in roll.sessions.values():
        started, first = row.get("started_at"), row.get("first_order_at")
        if not started or not first or first < started:
            continue
        delta = (parse_iso(first) - parse_iso(started)).total_seconds()
        out.append(Decimal(str(round(delta, 3))))
    return out


_SUM_KEYS = (
    "sessions", "turns", "tool_calls", "requests", "decisions", "closed_trades", "wins",
    "brier_n", "reviews", "blocks", "checks", "rejections", "playbook_versions", "postmortems",
    "sessions_with_order",
)
_SUM_MONEY = (
    "cost", "fees", "closed_pnl", "realized_pnl", "hypothetical_pnl", "brier_sum",
    "first_order_seconds",
)


def _merge(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Add up desk-level raw numbers. Drawdown is the worst of them, not the sum."""
    out: dict[str, Any] = {key: 0 for key in _SUM_KEYS}
    out.update({key: ZERO for key in _SUM_MONEY})
    out["max_drawdown"] = ZERO
    out["equity"] = None
    equity = ZERO
    seen_equity = False
    for row in rows:
        for key in _SUM_KEYS:
            out[key] += int(row.get(key) or 0)
        for key in _SUM_MONEY:
            out[key] += row.get(key) or ZERO
        if row.get("max_drawdown", ZERO) > out["max_drawdown"]:
            out["max_drawdown"] = row["max_drawdown"]
        if row.get("equity") is not None:
            equity += row["equity"]
            seen_equity = True
    if seen_equity:
        out["equity"] = equity
    return out


# --------------------------------------------------------------------------- the lab record

#: What goes into a published `lab.result`, in the order a human reads it. Everything else in the
#: report stays local: the event is a record, not a database.
FLOOR_METRICS = (
    "sessions", "turns", "tool_calls", "requests", "sail_cost_usd", "overhead_cost_usd",
    "decisions", "closed_trades", "wins", "win_rate", "avg_pnl_usd", "closed_pnl_usd",
    "realized_pnl_usd", "hypothetical_pnl_usd", "fees_usd", "net_pnl_usd",
    "cost_per_decision_usd", "pnl_per_inference_dollar", "max_drawdown_pct", "brier", "brier_n",
    "critic_block_rate", "risk_rejection_rate", "playbook_versions", "postmortems",
    "seconds_to_first_order", "desks", "live_desks", "shadow_desks",
)
DESK_METRICS = (
    "family", "mode", "profile", "sessions", "turns_per_session", "tool_calls_per_session",
    "sail_cost_usd", "decisions", "closed_trades", "win_rate", "avg_pnl_usd", "closed_pnl_usd",
    "realized_pnl_usd", "hypothetical_pnl_usd", "net_pnl_usd", "cost_per_decision_usd",
    "pnl_per_inference_dollar", "max_drawdown_pct", "brier", "critic_block_rate",
    "risk_rejection_rate", "playbook_versions", "postmortems", "seconds_to_first_order",
)
#: Dropped first, from the least valuable end, when a busy day would not otherwise fit.
DESK_OPTIONAL = (
    "seconds_to_first_order", "tool_calls_per_session", "turns_per_session", "postmortems",
    "playbook_versions", "risk_rejection_rate", "critic_block_rate", "brier",
    "max_drawdown_pct", "hypothetical_pnl_usd", "realized_pnl_usd", "avg_pnl_usd",
)
PROFILE_METRICS = (
    "requests", "sail_cost_usd", "cost_per_request_usd", "decisions", "closed_trades",
    "win_rate", "closed_pnl_usd", "net_pnl_usd", "cost_per_decision_usd",
    "pnl_per_inference_dollar",
)


def metrics_block(
    report: Mapping[str, Any], limit: int = MAX_METRICS_BYTES, max_keys: int = MAX_METRICS_KEYS
) -> dict[str, Any]:
    """The report as `{window, floor, profiles{name}, desks{id}, by_generation[]}` of strings,
    small enough to publish.

    Grouped so that no one object carries more keys than the site accepts however many desks the
    day had (one flat map overflowed at thirteen desks), and so that a `lab.result` from a year
    ago reads without a schema: `metrics.desks.mullins.win_rate`. Undefined ratios are left out
    rather than published as zero. `by_generation`, the improvement curve's rows, is the one list
    in the block, per the floor contract. A day that had to shed detail says `truncated: "true"`.
    """
    out: dict[str, Any] = {
        "window": {
            "start": _safe(str(report["window"]["start"])),
            "end": _safe(str(report["window"]["end"])),
            "days": _safe(str(report["window_days"])),
        },
        "floor": {},
        "profiles": {},
        "desks": {},
    }
    floor = report["floor"]
    for key in FLOOR_METRICS:
        _put(out["floor"], key, floor.get(key))
    for profile, row in report["profiles"].items():
        block: dict[str, str] = {}
        for key in PROFILE_METRICS:
            _put(block, key, row.get(key))
        if block:
            out["profiles"][_safe(str(profile), 80)] = block
    for desk_id, row in report["desks"].items():
        block = {}
        for key in DESK_METRICS:
            _put(block, key, row.get(key))
        if block:
            out["desks"][_safe(str(desk_id), 80)] = block

    def size() -> int:
        return len(canonical(out).encode("utf-8"))

    def quietest_desk() -> str:
        return min(
            out["desks"],
            key=lambda d: (int((report["desks"].get(d) or {}).get("decisions") or 0), d),
        )

    # leap: lab -- the improvement curve rides the daily result as rows, per the floor contract:
    # the one value in the block that is not a string. It is the first thing shed when a busy
    # day would not fit, because the desk numbers are what a year-old record is read for.
    curve = [dict(row) for row in (report.get("by_generation") or [])]
    if curve:
        out["by_generation"] = curve
        if size() > limit:
            out.pop("by_generation", None)
            out["truncated"] = "true"
    # More desks or profiles than the site takes keys in one object: quietest desks go first.
    while len(out["desks"]) > max_keys:
        out["desks"].pop(quietest_desk())
        out["truncated"] = "true"
    while len(out["profiles"]) > max_keys:
        out["profiles"].pop(sorted(out["profiles"])[-1])
        out["truncated"] = "true"
    for optional in DESK_OPTIONAL:  # shed detail before the block can overflow the site's cap
        if size() <= limit:
            break
        for block in out["desks"].values():
            block.pop(optional, None)
        out["truncated"] = "true"
    for profile in sorted(out["profiles"]):  # then the model breakdown
        if size() <= limit:
            break
        out["profiles"].pop(profile, None)
        out["truncated"] = "true"
    while size() > limit and out["desks"]:
        # Still too big: drop whole desks, quietest first, and say so.
        out["desks"].pop(quietest_desk())
        out["truncated"] = "true"
    for group in ("profiles", "desks"):
        if not out[group]:
            out.pop(group)
    return out


def _put(out: dict[str, str], key: str, value: Any) -> None:
    if value is None or value == "":
        return
    out[_safe(key, 80)] = _safe(str(value))


def verdict_for(report: Mapping[str, Any]) -> str:
    """One line a human can read without opening the metrics block."""
    desks = report["desks"]
    if not desks:
        return "no desks in the window"
    ordered = sorted(
        desks.items(),
        key=lambda row: (-int(row[1].get("closed_trades") or 0), row[0]),
    )
    parts: list[str] = []
    for desk_id, row in ordered[:6]:
        name = str(row.get("name") or desk_id)
        closed = int(row.get("closed_trades") or 0)
        if not closed:
            parts.append(f"{name} {int(row.get('decisions') or 0)} trades")
            continue
        hit = row.get("win_rate")
        hit_text = "" if hit is None else f", {_percent(Decimal(hit))}% hit"
        pnl = Decimal(row.get("closed_pnl_usd") or "0") - Decimal(row.get("fees_usd") or "0")
        cost = Decimal(row.get("sail_cost_usd") or "0")
        parts.append(
            f"{name} {closed} outcome{'' if closed == 1 else 's'}{hit_text}, "
            f"{_signed(pnl)} net of {_dollars(cost)} inference"
        )
    if len(ordered) > 6:
        parts.append(f"{len(ordered) - 6} more desks")
    return _safe("; ".join(parts), 900)


# --------------------------------------------------------------------------- markdown

def _cell(value: Any) -> str:
    if value is None or value == "":
        return "--"
    return str(value).replace("|", "/")


def _usd_cell(value: Any) -> str:
    """`$0.4100`, or `--` when the number does not exist. Never `$--`."""
    return "--" if value is None or value == "" else f"${_cell(value)}"


def _pct_cell(value: Any) -> str:
    if value is None or value == "":
        return "--"
    try:
        return f"{_num(Decimal(str(value)) * 100, Decimal('0.1'))}%"
    except (InvalidOperation, ValueError):  # pragma: no cover - values are rendered Decimals
        return _cell(value)


def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    out.extend("| " + " | ".join(row) + " |" for row in rows)
    return out


def markdown(report: Mapping[str, Any]) -> str:
    """A compact, table-based lab report. Markdown only: no angle brackets, no HTML."""
    floor = report["floor"]
    window = report["window"]
    lines = [
        f"# Lab report -- {window['end'][:10]}",
        "",
        f"Window: {window['start'][:16].replace('T', ' ')}Z to "
        f"{window['end'][:16].replace('T', ' ')}Z ({report['window_days']} day"
        f"{'' if report['window_days'] == 1 else 's'}), "
        f"{floor['desks']} desks ({floor['live_desks']} live, {floor['shadow_desks']} shadow).",
        "",
        "## Floor",
        "",
    ]
    lines.extend(
        _table(
            ["metric", "value", "metric", "value"],
            [
                ["sessions", _cell(floor["sessions"]), "decisions", _cell(floor["decisions"])],
                [
                    "turns / session",
                    _cell(floor["turns_per_session"]),
                    "closed trades",
                    _cell(floor["closed_trades"]),
                ],
                [
                    "tool calls / session",
                    _cell(floor["tool_calls_per_session"]),
                    "win rate",
                    _pct_cell(floor["win_rate"]),
                ],
                [
                    "Sail cost",
                    _usd_cell(floor["sail_cost_usd"]),
                    "realized P&L",
                    _usd_cell(floor["realized_pnl_usd"]),
                ],
                [
                    "overhead cost",
                    _usd_cell(floor["overhead_cost_usd"]),
                    "hypothetical P&L",
                    _usd_cell(floor["hypothetical_pnl_usd"]),
                ],
                [
                    "cost / decision",
                    _usd_cell(floor["cost_per_decision_usd"]),
                    "net of fees and inference",
                    _usd_cell(floor["net_pnl_usd"]),
                ],
                [
                    "P&L / inference $",
                    _cell(floor["pnl_per_inference_dollar"]),
                    "max drawdown",
                    _pct_cell(floor["max_drawdown_pct"]),
                ],
                [
                    "critic block rate",
                    _pct_cell(floor["critic_block_rate"]),
                    "risk rejection rate",
                    _pct_cell(floor["risk_rejection_rate"]),
                ],
                [
                    "Brier",
                    f"{_cell(floor['brier'])} (n={floor['brier_n']})",
                    "seconds to first order",
                    _cell(floor["seconds_to_first_order"]),
                ],
                [
                    "playbook versions",
                    _cell(floor["playbook_versions"]),
                    "post-mortems",
                    _cell(floor["postmortems"]),
                ],
            ],
        )
    )

    # Two tables rather than one of twenty columns: what each desk did, then what came of it.
    lines += ["", "## Desks: work and cost", ""]
    lines.extend(
        _table(
            [
                "desk", "family", "mode", "profile", "sess", "turns/s", "tools/s",
                "1st order s", "dec", "cost", "$/dec",
            ],
            [
                [
                    _cell(row.get("name") or desk_id),
                    _cell(row.get("family")),
                    _cell(row.get("mode")),
                    _cell(row.get("profile")),
                    _cell(row["sessions"]),
                    _cell(row["turns_per_session"]),
                    _cell(row["tool_calls_per_session"]),
                    _cell(row["seconds_to_first_order"]),
                    _cell(row["decisions"]),
                    _cell(row["sail_cost_usd"]),
                    _cell(row["cost_per_decision_usd"]),
                ]
                for desk_id, row in report["desks"].items()
            ],
        )
    )

    lines += ["", "## Desks: results", ""]
    lines.extend(
        _table(
            [
                "desk", "closed", "hit", "avg P&L", "P&L", "net", "P&L/$", "DD", "Brier",
                "blocked", "rejected", "books", "PMs",
            ],
            [
                [
                    _cell(row.get("name") or desk_id),
                    _cell(row["closed_trades"]),
                    _pct_cell(row["win_rate"]),
                    _cell(row["avg_pnl_usd"]),
                    _cell(row["closed_pnl_usd"]),
                    _cell(row["net_pnl_usd"]),
                    _cell(row["pnl_per_inference_dollar"]),
                    _pct_cell(row["max_drawdown_pct"]),
                    _cell(row["brier"]),
                    _pct_cell(row["critic_block_rate"]),
                    _pct_cell(row["risk_rejection_rate"]),
                    _cell(row["playbook_versions"]),
                    _cell(row["postmortems"]),
                ]
                for desk_id, row in report["desks"].items()
            ],
        )
    )

    lines += ["", "## Families", ""]
    lines.extend(
        _table(
            ["family", "desks", "sess", "dec", "closed", "hit", "P&L", "cost", "P&L/$", "DD"],
            [
                [
                    _cell(family),
                    _cell(len(row.get("desks") or [])),
                    _cell(row["sessions"]),
                    _cell(row["decisions"]),
                    _cell(row["closed_trades"]),
                    _pct_cell(row["win_rate"]),
                    _cell(row["closed_pnl_usd"]),
                    _cell(row["sail_cost_usd"]),
                    _cell(row["pnl_per_inference_dollar"]),
                    _pct_cell(row["max_drawdown_pct"]),
                ]
                for family, row in report["families"].items()
            ],
        )
    )

    lines += ["", "## Model profiles", ""]
    lines.extend(
        _table(
            [
                "profile", "desks", "requests", "cost", "$/request", "desk cost", "dec",
                "closed", "hit", "P&L", "$/dec", "P&L/$",
            ],
            [
                [
                    _cell(profile),
                    _cell(", ".join(row.get("desks") or []) or "--"),
                    _cell(row["requests"]),
                    _cell(row["sail_cost_usd"]),
                    _cell(row["cost_per_request_usd"]),
                    _cell(row["desk_cost_usd"]),
                    _cell(row["decisions"]),
                    _cell(row["closed_trades"]),
                    _pct_cell(row["win_rate"]),
                    _cell(row["closed_pnl_usd"]),
                    _cell(row["cost_per_decision_usd"]),
                    _cell(row["pnl_per_inference_dollar"]),
                ]
                for profile, row in report["profiles"].items()
            ],
        )
    )

    lines += [
        "",
        "## Verdict",
        "",
        verdict_for(report),
        "",
        "Money is US dollars. `P&L` is closed trades gross of fees; `net` is the same number "
        "less fees and less what the model cost. `$/dec` is inference per decision and `P&L/$` "
        "is P&L after fees per dollar of inference. A profile's `cost` is what it was paid, "
        "`desk cost` what the desks it runs spent on every profile, and the per-decision "
        "columns use the second. A `--` is a ratio with no denominator, not a zero. Shadow "
        "desks are hypothetical: nothing there is money.",
        "",
        f"Generated {report['generated_at']} by `python3 -m ltcm report --days "
        f"{report['window_days']}`. See `docs/runs/README.md` for how to read a week of these.",
        "",
    ]
    return "\n".join(lines)


ResultsLedger.markdown = staticmethod(markdown)
