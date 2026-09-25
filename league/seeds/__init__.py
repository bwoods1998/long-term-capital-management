"""The founding programs: fourteen strategy files the league starts from.

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
    {"name": "options-breakout", "family": "options-breakout", "file": "options_breakout.py",
     "why": "Leverage with the loss capped at the premium: one near-the-money call on a 20-day high above a rising 50-day mean, one put on the mirror image. Unmeasured; option buyers pay the spread and the variance premium."},
    {"name": "options-pullback", "family": "options-pullback", "file": "options_pullback.py",
     "why": "Connors' RSI(2) pullback expressed with a call: in an uptrend, two hard down days tend to be bought back within the week. Unmeasured by this firm."},
    # The structure founders of direction and events (builder S4b of the options-desk run, Sept 25, 2026): each held
    # as ONE position priced at its net value plus its collateral (`league/structures.py`), each writing its own exits.
    {"name": "options-orb", "family": "options-orb-vertical", "file": "options_orb.py",
     "why": "Intraday momentum in SPY (published: the first half hour predicts the last, Gao et al. 2018): a 0-4 day $1 debit vertical in the direction of an opening-range breakout, flat by the close."},
    {"name": "options-trend-vertical", "family": "options-trend-vertical", "file": "options_trend_vertical.py",
     "why": "Buy the pullback in a 20-day trend (published time-series momentum; Connors-style short-term pullbacks): a 3-9 day debit vertical with the trend, taking most of its width."},
    {"name": "options-reversal", "family": "options-reversal-vertical", "file": "options_reversal.py",
     "why": "Index ETFs give back part of a two-sigma day within days (published short-term reversal in index returns): a 2-7 day debit vertical against the move."},
    {"name": "options-gap-drift", "family": "options-gap-drift", "file": "options_gap_drift.py",
     "why": "Post-announcement drift (published since Ball and Brown, 1968): a single stock that gaps two sigmas on news keeps drifting its way for days; a 3-11 day vertical with the gap."},
    {"name": "options-skew", "family": "options-skew", "file": "options_skew.py",
     "why": "Put skew mean-reverts and rich skew pays its seller (published: the variance and skew risk premia): a put credit vertical when 25-delta skew is rich in an uptrend, a put debit vertical when it is cheap."},
    {"name": "options-diagonal", "family": "options-trend-diagonal", "file": "options_diagonal.py",
     "why": "Time decay is steepest in the last days: sell a 0-3 day option and own a later one at a better strike in the trend's direction, a diagonal whose loss is capped at its debit."},
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
