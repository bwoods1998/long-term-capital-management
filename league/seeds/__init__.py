"""The founding population: twelve strategy files the league starts from.

Each file follows `league/CONTRACT.md` and passes `league.safety.check_code`. They are data, not
modules: the House reads a seed's source with `load()` and runs it through `league.runner` or
`league.replay` like any other agent's code, so nothing here imports them.

Four trade Kalshi (three expressions of the first run's one measured edge, resting bids on
favourites above 90 cents, and one control with no measured edge), four trade Alpaca crypto and
four trade Alpaca equities. Every `why` says where the idea comes from; "published" means outside
research the league still has to confirm, not something this firm has measured.
"""

from __future__ import annotations

from pathlib import Path

SEEDS: list[dict] = [
    {"name": "favorites-maker", "family": "kalshi-favorites", "file": "favorites_maker.py",
     "why": "The first run's one measured edge: resting maker bids on favourites above 90 cents made +2.15 cents a contract out of sample; here on the hourly crypto strikes, its weakest group."},
    {"name": "favorites-no", "family": "kalshi-favorites", "file": "favorites_no.py",
     "why": "The same edge on the NO leg: when YES asks 10 cents or less NO is the favourite, NO beat YES at most prices in 72M trades, and buyers of 10-cent contracts lost 0.9 to 6.7 cents."},
    {"name": "favorites-daily", "family": "kalshi-favorites", "file": "favorites_daily.py",
     "why": "The same edge on daily weather and commodity markets, the two groups where favourites were measured positive (crypto favourites were negative on a small sample)."},
    {"name": "hourly-quotes", "family": "kalshi-quotes", "file": "hourly_quotes.py",
     "why": "A control: Kalshi makers earn about 1.1% overall, but the first run measured no edge for two-sided quoting of the hourly BTC strikes; the league may kill it."},
    {"name": "crypto-reversion", "family": "crypto-reversion", "file": "crypto_reversion.py",
     "why": "Hourly closes two standard deviations under their 24-hour mean tend to snap back; unproven in the first run, so it only trades when the mean is 1% away, beyond the 0.5% taker round trip."},
    {"name": "crypto-trend", "family": "crypto-trend", "file": "crypto_trend.py",
     "why": "A 48-hour breakout with a 24-over-96-hour trend filter: trades rarely and aims at moves of several percent, which is what a 0.5% round-trip fee allows."},
    {"name": "crypto-dip-limit", "family": "crypto-reversion", "file": "crypto_dip_limit.py",
     "why": "Reversion with resting limits on both sides (buy two average ranges under the 8-hour mean, sell at the mean), paying the 0.15% maker fee instead of the 0.25% taker fee."},
    {"name": "crypto-pairs", "family": "crypto-pairs", "file": "crypto_pairs.py",
     "why": "The ETH/BTC ratio is steadier than either coin: hold whichever is two standard deviations cheap against the other until the ratio returns to its 72-hour mean (long only, no shorts allowed)."},
    {"name": "equity-overnight", "family": "equity-overnight", "file": "equity_overnight.py",
     "why": "The overnight-drift anomaly (published): most of the US index's historical return accrued between the close and the next open, and ETFs trade commission-free."},
    {"name": "equity-trend", "family": "equity-trend", "file": "equity_trend.py",
     "why": "Cross-asset momentum with a trend filter (published): hold the ETF with the best 60-day return among those above their 100-day mean, else cash."},
    {"name": "equity-rsi2", "family": "equity-reversion", "file": "equity_rsi2.py",
     "why": "Connors' RSI(2) pullback (published): in an uptrend, index ETFs that fall hard for two days tend to bounce within a week."},
    {"name": "equity-vwap", "family": "equity-intraday", "file": "equity_vwap.py",
     "why": "Intraday prices are pulled toward the session VWAP that large orders are benchmarked to: buy 0.4% under it, sell at it, flat by 15:50; a desk heuristic on trial."},
]

_HERE = Path(__file__).resolve().parent
_BY_NAME = {row["name"]: row for row in SEEDS}


def load(name: str) -> str:
    """The source text of the seed called `name` (its `name` in SEEDS, e.g. "favorites-maker")."""
    row = _BY_NAME.get(name)
    if row is None:
        raise KeyError(f"no seed named {name!r}; the seeds are {', '.join(sorted(_BY_NAME))}")
    return (_HERE / row["file"]).read_text(encoding="utf-8")


def all_seeds() -> list[dict]:
    """A copy of every SEEDS row with its source added under "code"."""
    return [{**row, "code": load(row["name"])} for row in SEEDS]
