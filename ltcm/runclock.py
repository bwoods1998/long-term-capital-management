"""The run clock: how long the desks have been working, what it has cost, what it has earned.

The one question a visitor asks first is "how long has this been running, and is it paying for
itself?" This folds the answer from things the floor already records: the first session on the
tape is the start; sessions and decisions are counted from their own events; the loop's
availability is the share of five-minute floor marks that actually landed in the last seven
days; model spend comes from the provider's own request ledger; the box's cost is either Sail's
own number for the period (when the usage API answers) or a plain estimate from the configured
daily rate, labelled as such by being the only nullable-by-design field.

`pnl_per_sail_dollar` is the number the owner watches: realized and unrealized profit on the
live sleeves divided by every dollar sent to Sail. Nothing here is a forecast.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Any, Callable, Iterable, Mapping

ZERO = Decimal(0)
CENTS = Decimal("0.01")
PCT = Decimal("0.1")
MARK_INTERVAL_SECONDS = 300


def _iso(value: str) -> datetime:
    text = str(value).replace("Z", "+00:00")
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def _money(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return ZERO


def fold(
    at: str,
    *,
    session_starts: Iterable[str],
    decisions: int,
    marks: Iterable[str],
    live_pnl_usd: Any,
    model_spend_today_usd: Any,
    model_spend_total_usd: Any,
    infra_spend_total_usd: Any | None,
    uptime_seconds: int | None,
    models_used: Iterable[str],
    mark_interval_seconds: int = MARK_INTERVAL_SECONDS,
) -> dict[str, Any]:
    """The contract's `run` block from plain inputs. Pure; tested without a floor."""
    now = _iso(at)
    starts = sorted(str(s) for s in session_starts)
    started_at = starts[0] if starts else at
    today = at[:10]
    sessions_today = sum(1 for s in starts if s[:10] == today)

    week_ago = now - timedelta(days=7)
    started = _iso(started_at)
    window_start = max(week_ago, started)
    window_seconds = max(0.0, (now - window_start).total_seconds())
    expected = window_seconds / float(mark_interval_seconds)
    landed = sum(1 for m in marks if _iso(str(m)) >= window_start)
    availability: Decimal | None
    if expected < 1:
        availability = None
    else:
        availability = min(Decimal(100), (Decimal(landed) / Decimal(str(expected)) * 100)).quantize(PCT, rounding=ROUND_DOWN)

    model_total = _money(model_spend_total_usd)
    infra_total = None if infra_spend_total_usd is None else _money(infra_spend_total_usd)
    sail_total = model_total + (infra_total or ZERO)
    pnl = _money(live_pnl_usd)
    per_dollar: Decimal | None = None
    if sail_total > ZERO:
        per_dollar = (pnl / sail_total).quantize(CENTS, rounding=ROUND_DOWN)

    return {
        "started_at": started_at,
        "uptime_seconds": int(uptime_seconds or 0),
        "availability_7d_pct": None if availability is None else str(availability),
        "sessions_total": len(starts),
        "sessions_today": sessions_today,
        "decisions_total": int(decisions),
        "sail_model_spend_today_usd": str(_money(model_spend_today_usd).quantize(CENTS, rounding=ROUND_DOWN)),
        "sail_model_spend_total_usd": str(model_total.quantize(CENTS, rounding=ROUND_DOWN)),
        "sail_infra_spend_total_usd": None if infra_total is None else str(infra_total.quantize(CENTS, rounding=ROUND_DOWN)),
        "sail_spend_total_usd": str(sail_total.quantize(CENTS, rounding=ROUND_DOWN)),
        "pnl_total_usd": str(pnl.quantize(CENTS, rounding=ROUND_DOWN)),
        "pnl_per_sail_dollar": None if per_dollar is None else str(per_dollar),
        "models_used": sorted({str(m) for m in models_used if m})[:8],
    }


def infra_estimate(started_at: str, at: str, usd_per_day: Any) -> Decimal:
    """The box's cost as the configured daily rate over the run so far, when Sail's own number
    is not at hand. Labelled an estimate by the caller, never presented as a bill."""
    seconds = max(0.0, (_iso(at) - _iso(started_at)).total_seconds())
    return (_money(usd_per_day) * Decimal(str(seconds)) / Decimal(86400)).quantize(CENTS, rounding=ROUND_DOWN)


class RunClock:
    """Folds the run block from the floor's components. Every read is guarded: a component
    that cannot answer leaves its field at a safe default rather than stopping a checkpoint."""

    def __init__(
        self,
        log: Any,
        *,
        provider: Any = None,
        live_pnl: Callable[[str], Any] | None = None,
        uptime: Callable[[], int | None] | None = None,
        models_used: Callable[[], Iterable[str]] | None = None,
        infra_usd_per_day: Any = "0.30",
        sail_usage: Callable[[], Mapping[str, Any] | None] | None = None,
        mark_interval_seconds: int = MARK_INTERVAL_SECONDS,
    ):
        self.log = log
        self.provider = provider
        self.live_pnl = live_pnl
        self.uptime = uptime
        self.models_used = models_used
        self.infra_usd_per_day = infra_usd_per_day
        self.sail_usage = sail_usage
        self.mark_interval_seconds = int(mark_interval_seconds)

    def _events(self, kind: str, limit: int) -> list[Any]:
        try:
            return list(self.log.read(kind=kind, limit=limit))
        except Exception:
            return []

    def read(self, at: str) -> dict[str, Any]:
        starts = [e.at for e in self._events("desk.session_started", 100_000)]
        marks = [e.at for e in self._events("floor.mark", 5_000)]
        decisions = len(self._events("risk.decision", 100_000))
        spend_today = ZERO
        spend_total = ZERO
        if self.provider is not None:
            try:
                spend_today = _money(self.provider.spent_today())
            except Exception:
                spend_today = ZERO
            trailing = getattr(self.provider, "spent_since", None)
            if callable(trailing):
                try:
                    spend_total = _money(trailing(24.0 * 3660))  # ten years: everything
                except Exception:
                    spend_total = ZERO
        pnl = ZERO
        if self.live_pnl is not None:
            try:
                pnl = _money(self.live_pnl(at))
            except Exception:
                pnl = ZERO
        uptime = None
        if self.uptime is not None:
            try:
                uptime = self.uptime()
            except Exception:
                uptime = None
        models: Iterable[str] = ()
        if self.models_used is not None:
            try:
                models = list(self.models_used())
            except Exception:
                models = ()
        infra: Decimal | None = None
        if self.sail_usage is not None:
            try:
                usage = self.sail_usage()
                if isinstance(usage, Mapping) and usage.get("infra_spend_usd") is not None:
                    infra = _money(usage["infra_spend_usd"])
            except Exception:
                infra = None
        if infra is None:
            started_at = min(starts) if starts else at
            infra = infra_estimate(started_at, at, self.infra_usd_per_day)
        return fold(
            at,
            session_starts=starts,
            decisions=decisions,
            marks=marks,
            live_pnl_usd=pnl,
            model_spend_today_usd=spend_today,
            model_spend_total_usd=spend_total,
            infra_spend_total_usd=infra,
            uptime_seconds=uptime,
            models_used=models,
            mark_interval_seconds=self.mark_interval_seconds,
        )
