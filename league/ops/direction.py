"""The `direction` job (at start and daily 01:00Z; FAST LANE V2, Oct 7, 2026, D2: "Profit from market direction counts,
reported beside the same-risk buy-and-hold").

Since fast lane v2 no program is refused or held for market drift: a program whose profit is the market's direction can
pass the screen and trade at Probe. So every screen result and every band row carries, beside it and never as a bar,
(1) the drift fit (beta, alpha_usd, drift_usd, share) and (2) the SAME-RISK BUY-AND-HOLD: a long position in the
program's own roots held every session of the window, sized to the program's own daily P&L standard deviation (same
risk = the same daily volatility). Nothing in the tournament, the gate, the bands or the money table reads these figures
(`league/tests/test_fast_lane_v2.py` pins that); `scripts/fast_lane_report.py` prints them for the captain's funnel.

THE JOB (`run`): the swarm's Gym roots (`league.swarm.settings.load`), the index roots through `PROXY` (XSP and SPXW have
no stock bars: SPY stands in), their daily split-adjusted SIP closes from 2024-12-31 to today through the gateway
(`/v1/alpaca/v2/stocks/bars`, GET only, paginated; the route is already allowed, `gateway/lib/caps.mjs`), written
atomically to `<state>/direction-closes.json`. A gateway error writes nothing and answers {"ok": false, "why"}.

THE ARITHMETIC (standard library only; the report script and the tests call it):
- `market_returns(closes, roots, days)`: each day's equal-weighted close-to-close return of the roots' symbols (after
  the proxy), each from its own previous close; None for a day no symbol has.
- `same_risk_bh(sd_program, market)`: over the days with a market return r_t (mean mu_B, standard deviation sigma_B),
  usd = sum_t (sigma_P / sigma_B) r_t = n sigma_P mu_B / sigma_B.
- `daily_fit(pnl_by_day, market)`: on the paired days, beta = cov(P, r) / var(r) (dollars per 1.00 of root return),
  drift_usd = beta sum r, alpha_usd = sum P - drift_usd, share = |drift| / (|alpha| + |drift|); basis "daily-close", for
  the windows with a daily series (the holdout, live).
- `train_fit(store, fam, n)`: the Gym's own Train fit over held hours (`evidence.drift_lean`), basis "train-held-hours".
sigma_P per window: Validation (a summary only) (pnl / days) / sharpe_daily of the 1.0x summary; the holdout the
standard deviation of the result's daily P&L (every session, zeros included); live the real P&L per session since
`live_promoted_at`, zeros included.
"""
from __future__ import annotations

import json
import math
import statistics
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from zoneinfo import ZoneInfo

FILE = "direction-closes.json"
SCHEMA = 1
#: Index roots with no stock bars: the ETF that stands in for them.
PROXY = {"XSP": "SPY", "SPXW": "SPY"}
FIRST_DAY = "2024-12-31"  # the close before Validation's first session (2025-01-02)
BARS = "/v1/alpaca/v2/stocks/bars"
#: Pages of bars at most (a guard against a cursor that never ends): 25 roots x ~450 days is two or three.
MAX_PAGES = 50
NEW_YORK = ZoneInfo("America/New_York")


def symbols_of(roots: Iterable[Any]) -> tuple[list[str], dict[str, str]]:
    """(the stock symbols the roots read, {index root: its proxy} for the roots that need one)."""
    roots = [str(r).upper() for r in roots or () if str(r).strip()]
    proxy = {r: PROXY[r] for r in roots if r in PROXY}
    return sorted({PROXY.get(r, r) for r in roots}), proxy


# ------------------------------------------------------------------------------------------------- the job
def fetch(gateway: Any, symbols: Sequence[str], start: str, end: str) -> dict[str, dict[str, float]]:
    """{symbol: {YYYY-MM-DD: close}} of the daily split-adjusted SIP bars, every page."""
    closes: dict[str, dict[str, float]] = {s: {} for s in symbols}
    token = None
    for _ in range(MAX_PAGES):
        params = {"symbols": ",".join(symbols), "timeframe": "1Day", "start": start, "end": end, "adjustment": "split",
                  "feed": "sip", "limit": 10000}
        if token:
            params["page_token"] = token
        answer = gateway.get(BARS, params) or {}
        bars = answer.get("bars") if isinstance(answer, Mapping) else None
        if not isinstance(bars, Mapping):
            raise ValueError("the bars answer has no bars")
        for symbol, rows in bars.items():
            for row in rows or ():
                day, close = str((row or {}).get("t") or "")[:10], row.get("c") if isinstance(row, Mapping) else None
                if len(day) == 10 and isinstance(close, (int, float)) and math.isfinite(float(close)) and close > 0:
                    closes.setdefault(str(symbol), {})[day] = float(close)
        token = answer.get("next_page_token")
        if not token:
            return closes
    raise ValueError(f"the bars did not end within {MAX_PAGES} pages")


def run(ctx: Any) -> dict[str, Any]:
    from ..swarm import settings as swarm_settings
    from .context import write_json

    roots = (swarm_settings.load(ctx.root).get("gym") or {}).get("roots") or []
    symbols, proxy = symbols_of(roots)
    if not symbols:
        return {"ok": False, "why": "the swarm names no Gym roots"}
    today = datetime.fromtimestamp(ctx.now(), NEW_YORK).date().isoformat()
    try:
        closes = fetch(ctx.gateway, symbols, FIRST_DAY, today)
    except Exception as exc:  # noqa: BLE001 - a gateway error writes nothing
        return {"ok": False, "why": f"{type(exc).__name__}: {str(exc)[:200]}"}
    doc = {"schema": SCHEMA, "at": datetime.fromtimestamp(ctx.now(), NEW_YORK).isoformat(), "feed": "sip",
           "adjustment": "split", "proxy": proxy, "closes": {s: dict(sorted(v.items())) for s, v in sorted(closes.items())}}
    write_json(Path(ctx.root) / FILE, doc)
    return {"ok": True, "symbols": len(symbols), "days": max((len(v) for v in closes.values()), default=0),
            "empty": sorted(s for s, v in closes.items() if not v)}


# ------------------------------------------------------------------------------------------- the arithmetic
def load_closes(path: str | Path) -> dict[str, dict[str, float]]:
    """The file's closes ({} when it is absent or unreadable)."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    closes = doc.get("closes") if isinstance(doc, Mapping) else None
    return {str(s): {str(d): float(c) for d, c in rows.items()} for s, rows in (closes or {}).items()
            if isinstance(rows, Mapping)}


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(float(value)) else None


def market_returns(closes: Mapping[str, Mapping[str, float]], roots: Iterable[Any], days: Iterable[str]) -> dict[str, Any]:
    """{"by_day": {day: the equal-weighted close-to-close return of the roots' symbols, or None}, "roots", "symbols",
    "proxy"}: each symbol's return from its own previous close."""
    symbols, proxy = symbols_of(roots)
    returns: dict[str, dict[str, float]] = {}
    for symbol in symbols:
        series = sorted((d, c) for d, c in (closes.get(symbol) or {}).items() if _num(c) is not None and c > 0)
        returns[symbol] = {d: c / prev - 1.0 for (_, prev), (d, c) in zip(series, series[1:])}
    by_day: dict[str, float | None] = {}
    for day in days:
        values = [returns[s][day] for s in symbols if day in returns[s]]
        by_day[str(day)] = sum(values) / len(values) if values else None
    return {"by_day": by_day, "roots": sorted({str(r).upper() for r in roots or ()}), "symbols": symbols, "proxy": proxy}


def same_risk_bh(sd_program: Any, market: Mapping[str, Any]) -> dict[str, Any]:
    """THE SAME-RISK BUY-AND-HOLD (the module docstring): {usd, market_sharpe_daily, sd_program, days, missing_days,
    roots, proxy}, or {usd: None, why}."""
    by_day = dict(market.get("by_day") or {})
    known = [r for r in by_day.values() if _num(r) is not None]
    sd = _num(sd_program)
    if not by_day or not known:
        return {"usd": None, "why": "no market closes for these days (the direction job's file is absent or empty)"}
    if sd is None or sd <= 0:
        return {"usd": None, "why": "the program's daily P&L has no standard deviation"}
    if len(known) < 2:
        return {"usd": None, "why": "fewer than two days with a market return"}
    mu, sigma = statistics.fmean(known), statistics.stdev(known)
    if sigma <= 0:
        return {"usd": None, "why": "the market's returns do not vary"}
    return {"usd": round(len(known) * sd * mu / sigma, 2), "market_sharpe_daily": mu / sigma, "sd_program": sd,
            "days": len(known), "missing_days": len(by_day) - len(known), "roots": list(market.get("roots") or []),
            "proxy": dict(market.get("proxy") or {})}


def daily_fit(pnl_by_day: Mapping[str, Any], market: Mapping[str, Any]) -> dict[str, Any]:
    """The drift fit on daily closes (the module docstring): {beta, alpha_usd, drift_usd, share, days, basis}, or
    {beta: None, why, basis}."""
    by_day = market.get("by_day") or {}
    pairs = [(float(p), float(by_day[d])) for d, p in pnl_by_day.items()
             if _num(p) is not None and _num(by_day.get(d)) is not None]
    if len(pairs) < 2:
        return {"beta": None, "why": "fewer than two days with both a P&L and a market return", "basis": "daily-close"}
    ps, rs = [p for p, _ in pairs], [r for _, r in pairs]
    mp, mr = statistics.fmean(ps), statistics.fmean(rs)
    var = sum((r - mr) ** 2 for r in rs)
    if var <= 0:
        return {"beta": None, "why": "the market's returns do not vary", "basis": "daily-close"}
    beta = sum((p - mp) * (r - mr) for p, r in pairs) / var
    drift = beta * sum(rs)
    alpha = sum(ps) - drift
    whole = abs(alpha) + abs(drift)
    return {"beta": beta, "alpha_usd": alpha, "drift_usd": drift, "share": abs(drift) / whole if whole > 0 else None,
            "days": len(pairs), "basis": "daily-close"}


def train_fit(store: Any, fam: Mapping[str, Any], n: Any) -> dict[str, Any]:
    """The Gym's own Train drift fit over held hours (`evidence.drift_lean` on `researcher.version_drift`)."""
    from ..swarm import evidence
    from ..swarm.researcher import running_span, version_drift

    lean = evidence.drift_lean(version_drift(store, fam, n), first_year=int(running_span(store)[:4]))
    return {**{k: lean.get(k) for k in ("beta", "alpha_usd", "drift_usd", "share", "known", "why")},
            "basis": "train-held-hours"}


def sessions(first: str, last: str) -> list[str]:
    """The NYSE sessions from `first` to `last` (ISO days, both included)."""
    from ltcm.data import us_equity_session

    out, day, end = [], date.fromisoformat(first), date.fromisoformat(last)
    while day <= end:
        if us_equity_session(day) is not None:
            out.append(day.isoformat())
        day += timedelta(days=1)
    return out


__all__ = ["run", "fetch", "load_closes", "market_returns", "same_risk_bh", "daily_fit", "train_fit", "sessions",
           "symbols_of", "PROXY", "FILE"]
