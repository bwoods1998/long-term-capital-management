"""The founding programs: the strategy files the league starts from (fourteen of Sept 19-20, 2026,
and the options desk's structure founders that passed the House's structure replay, Sept 25, 2026).

Each file follows `league/CONTRACT.md` and passes `league.safety.check_code`. They are data, not
modules: the House reads a seed's source with `load()` and runs it through `league.runner` or
`league.replay` like any other agent's code, so nothing here imports them.

Four trade Kalshi (three expressions of the first run's one measured edge, resting bids on
favourites above 90 cents, and one control with no measured edge), four trade Alpaca crypto and
four trade Alpaca equities. Every `why` says where the idea comes from; "published" means outside
research the league still has to confirm, not something this firm has measured.

Rows appended later may share a file: `weather_ensemble.py` is seated as four founders of the weather desk
(Sept 25, 2026), one family per group of stations.
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
    {"name": "options-gap-drift", "family": "options-gap-drift", "file": "options_gap_drift.py",
     "why": "Post-announcement drift (Ball and Brown 1968): after a 2-sigma, 3% news day BAC, T, F, AAL, RIVN and CCL kept drifting (+0.95% the next day, 21, fit window); a vertical with the move."},
    {"name": "options-condor-vrp", "family": "options-condor-vrp", "file": "options_condor_vrp.py",
     "why": "The variance risk premium (published): index options price more movement than follows. A $1-winged 0-2 day iron condor on SPY/QQQ/IWM when the implied move is rich against the realized one and the condor's expected value clears every leg's touch."},
    {"name": "options-putspread-dip", "family": "options-putspread-dip", "file": "options_putspread_dip.py",
     "why": "Sell the put skew after an intraday dip in an uptrend (published: rich index put premium, short-term reversal): a $1-wide put credit vertical, 0-4 days, bought back within a day."},
    {"name": "options-ironfly-quiet", "family": "options-ironfly-quiet", "file": "options_ironfly_quiet.py",
     "why": "Volatility clusters (published): a quiet midday tends to stay quiet while at-the-money premium decays fastest. A 0-1 day at-the-money iron butterfly with $1 wings, flat by 15:15 New York."},
    {"name": "options-strangle-cheap", "family": "options-strangle-cheap", "file": "options_strangle_cheap.py",
     "why": "The one time buying options pays (published): when implied volatility lags a burst of realized. A 2-5 day long strangle on IWM/QQQ/SPY only when the implied move is cheap against the realized one, out on a move or after a day."},
    {"name": "options-calendar-term", "family": "options-calendar-term", "file": "options_calendar_term.py",
     "why": "Term-structure mean reversion (published): when the near expiry's implied volatility is kinked above the far one's, sell the near and buy the far at one strike, closed before the near expiry."},
    {"name": "options-butterfly-pin", "family": "options-butterfly-pin", "file": "options_butterfly_pin.py",
     "why": "Pinning at heavily traded strikes on expiry days (published: Ni, Pearson and Poteshman 2005): a $1-winged long butterfly expiring today, centred on the strike that traded most in the last two hours, sold before the close."},
    {"name": "options-orb", "family": "options-orb-vertical", "file": "options_orb.py",
     "why": "Opening-range breakouts LOST from May 22 to Aug 11, 2026 on IWM, BAC, SOFI, SNAP and AAL (-0.14% to -0.44% to the close): fade them with a 0-4 day debit vertical, flat by the close; `fade` 0 is the published intraday momentum."},
    {"name": "options-trend-vertical", "family": "options-trend-vertical", "file": "options_trend_vertical.py",
     "why": "A pullback inside a rising 20-day trend was bought the next day on BAC, PFE, T and SOFI (+0.40% pooled, 62% up, fit window): a near-the-money call debit vertical, out the next day."},
    {"name": "options-reversal", "family": "options-reversal-vertical", "file": "options_reversal.py",
     "why": "Short-term reversal after a sharp drop (Nagel 2012): after a 1.5-sigma down day five stocks and IWM rose +1.88% the next day (21, fit window); a call debit vertical, out the next day."},
    {"name": "options-skew", "family": "options-skew", "file": "options_skew.py",
     "why": "Put skew against its own level: a cheap 25-delta skew on SPY, QQQ and IWM preceded rises (+0.35% to +1.28% over 3 days, fit window), so the calm is ridden with a call debit vertical; a rich-skew put credit arm is one switch away."},
    {"name": "options-diagonal", "family": "options-trend-diagonal", "file": "options_diagonal.py",
     "why": "Time decay is steepest in the last days: in a $5-60 stock's uptrend, sell a 1-4 day call and own a 5-10 day one at a lower strike, a diagonal whose loss is capped at its debit."},
    # Model versus market on sports (K1 of the Kalshi-scale run, Sept 25, 2026): ONE program,
    # `sports_consensus.py`, a row per league, so each league's founder is its own family.
    {"name": "consensus-nfl", "family": "sports-consensus-nfl", "file": "sports_consensus.py",
     "why": "Unmeasured: the sportsbook line as a second price. NFL winners, spreads and totals priced from the de-vigged DraftKings line the odds feed records, bid post-only where Kalshi is off it by more than the fee and a margin; on winners Kalshi measured within about a cent of the book (Sept 24-25), so the edge asked there is small and the bid is withdrawn when the line moves."},
    {"name": "consensus-ncaaf", "family": "sports-consensus-ncaaf", "file": "sports_consensus.py",
     "why": "Unmeasured: the sportsbook line as a second price. College-football winners, spreads and totals (the whole FBS and FCS slate) priced from the de-vigged DraftKings line, bid post-only where Kalshi's thinner, wider ladders are off it by more than the fee and a margin."},
    {"name": "consensus-mlb", "family": "sports-consensus-mlb", "file": "sports_consensus.py",
     "why": "Unmeasured: the sportsbook line as a second price. MLB winners, run lines (at the book's own run line only) and totals near the line priced from the de-vigged DraftKings prices; Kalshi's winners measured within 1.4 cents of the book on 90% of 112 readings (Sept 24-25), so this measures whether the small edges that remain pay."},
    {"name": "consensus-mls", "family": "sports-consensus-mls", "file": "sports_consensus.py",
     "why": "Unmeasured: the sportsbook line as a second price. MLS home, away and tie contracts priced from DraftKings' three-way prices with the draw, de-vigged, bid post-only where Kalshi is off them by more than the fee and a margin."},
    {"name": "consensus-ligamx", "family": "sports-consensus-ligamx", "file": "sports_consensus.py",
     "why": "Unmeasured: the sportsbook line as a second price. Liga MX home, away and tie contracts priced from DraftKings' three-way prices with the draw, de-vigged, bid post-only where Kalshi is off them by more than the fee and a margin."},
    # K3 of the Kalshi-scale run (Sept 25, 2026): one program, weather_ensemble.py, seated as four founders of the weather
    # desk, one family each (their series are disjoint: the forward-first run's C8 keys a family by its mechanism and series).
    {"name": "weather-ensemble-east", "family": "weather-ensemble-east", "file": "weather_ensemble.py",
     "why": "The foundry's first transfer: price every daily high and low bracket of New York, Miami, Philadelphia, Atlanta, Boston and Washington from the 82 GFS and ECMWF ensemble members, calibrated to Kalshi's own settlements, and rest maker bids where the fair clears the price. A proxy lost to the market mid on 16 days: unproven."},
    {"name": "weather-ensemble-central", "family": "weather-ensemble-central", "file": "weather_ensemble.py",
     "why": "The ensemble-priced weather card on Chicago, Minneapolis, Oklahoma City and New Orleans highs and lows: bias-corrected members, a kernel, the NWS forecast blended in, shrunk toward the market mid; maker entries held to settlement. Unproven."},
    {"name": "weather-ensemble-texas", "family": "weather-ensemble-texas", "file": "weather_ensemble.py",
     "why": "The ensemble-priced weather card on Austin, Houston, Dallas and San Antonio highs and lows: bias-corrected members, a kernel, the NWS forecast blended in, shrunk toward the market mid; maker entries held to settlement. Unproven."},
    {"name": "weather-ensemble-west", "family": "weather-ensemble-west", "file": "weather_ensemble.py",
     "why": "The ensemble-priced weather card on Denver, Phoenix, Los Angeles, Seattle, Las Vegas and San Francisco highs and lows: bias-corrected members (Los Angeles runs 3.6 F cool of the models), shrunk toward the market mid; maker entries. Unproven."},
    # The same idea for a sport whose sides are people (K1c, Sept 25, 2026): `sports_h2h.py`, a fight
    # found by its fighters' names. UFC is the one individual sport ESPN prices (tennis, golf, cricket
    # and F1 have boards but no line there).
    {"name": "h2h-ufc", "family": "sports-h2h-ufc", "file": "sports_h2h.py",
     "why": "Unmeasured: the sportsbook line as a second price. Each UFC fight's two contracts priced from DraftKings' de-vigged moneyline (a draw or no contest settles 50/50 on Kalshi, so the fair leans to half by the void share), the fight found by its fighters' names, never guessed; bid post-only where Kalshi is off the line by more than the fee and a margin. Measured once, on the Sept 26 card: Kalshi's mid within 1.1 cents of the line on 16 of 18 markets."},
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
