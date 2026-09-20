# The strategy contract

A strategy is one Python file. It is the unit the league selects on. The same file runs in three
places and must behave the same in all of them: the replay simulator (rung 0), the forward paper
test (rung 1) and real trading (rungs 2 and 3).

## The file

```python
NEEDS = {
    "venue": "alpaca",            # "alpaca" or "kalshi": the venue family this strategy trades
    "horizon": "hour",            # "hour" or "day": how its results are blocked for the statistics
    "style": "reversion",         # free text: with venue and horizon it names the agent's niche
    "symbols": ["BTC/USD"],       # alpaca: what to be shown. Crypto "BTC/USD", equities "SPY"
    "bars": {"timeframe": "5Min", "limit": 120},   # alpaca: 1Min 5Min 15Min 1Hour 1Day, limit <= 500
    "series": ["KXBTCD"],         # kalshi: the series whose open markets to be shown
    "max_hours_to_close": 24,     # kalshi: only markets closing within this many hours
    "wake_minutes": 15,           # how often to be woken: 5 to 1440
}
PARAMS = {"lookback": 24, "z_entry": 2.0}          # defaults; a mutation changes these first

def decide(ctx):
    ...
    return {"intents": [...], "cancels": [...], "thought": "one or two plain sentences", "memory": {...}}
```

Only these imports are allowed: `bisect collections datetime decimal fractions functools heapq
itertools json math random re statistics time typing zoneinfo`. No files, no network, no
attribute assignment, no underscore attributes, no `eval`/`exec`/`open`/`getattr` tricks
(`league/safety.py` is the check). `decide` must return within 5 seconds.

## What `decide` is given

`ctx` is plain JSON data. Money and prices are floats here (the House converts what comes back to
exact decimals).

```python
ctx = {
  "now": "2026-09-20T13:30:00.000Z",
  "venue": "alpaca",
  "rung": 1,                          # 0 replay, 1 paper, 2 micro-real, 3 scaled
  "params": {...},                    # PARAMS with this agent's mutations applied
  "memory": {...},                    # whatever the last decide returned as "memory" (<= 8 KB JSON)
  "cash": 173.20, "equity": 201.35,   # this agent's own account on this book
  "limits": {"max_position_usd": 100.0, "max_order_usd": 75.0},
  "fees": {"crypto_taker": 0.0025, "crypto_maker": 0.0015, "kalshi_taker_rate": 0.07},
  "positions": [{"symbol": "BTC/USD", "quantity": 0.0003, "average_cost": 81010.2, "mark": 81200.0,
                 "opened_at": "...", "reason": "..."}],            # kalshi: "market" and "leg" instead of "symbol"
  "open_orders": [{"order_id": "ord-...", "symbol": "BTC/USD", "side": "buy", "quantity": 0.0003,
                   "limit_price": 80000.0, "filled": 0.0, "submitted_at": "..."}],
  # alpaca
  "bars": {"BTC/USD": [{"t": "...", "o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0, "v": 1.0}, ...]},  # oldest first, all closed
  "quotes": {"BTC/USD": {"bid": 81000.0, "ask": 81020.0}},
  # kalshi
  "markets": [{"market": "KXBTCD-26SEP2017-T80999.99", "series": "KXBTCD", "title": "...",
               "yes_bid": 0.91, "yes_ask": 0.93, "close_time": "...", "hours_to_close": 0.6, "hours_to_resolve": 0.7,
               "volume_24h": 12000, "open_interest": 3400, "strike": 80999.99}],
}
```

## What you may watch but not trade

`NEEDS["observe"] = {"symbols": ["BTC/USD"], "series": ["KXBTCD"]}` (up to six of each) asks the
House for instruments on EITHER venue, whatever your own is. They arrive as `ctx["observed"]`
(`bars` and `quotes` for symbols, `markets` for series), live and on the replay tape alike, and an
order in any of them is refused here and by the House. That is how a Kalshi strategy reads the
spot price its contracts settle against, or an Alpaca one reads a coin it does not trade.

On a Kalshi **replay** tape the watched symbols arrive as `observed["bars"]` only -- there are no
recorded quotes for them -- at five-minute bars for an hourly tape and fifteen for a daily one,
and each step sees only the bars stamped at or before it. Watched series are not cut to your own
horizon: you may read a market you could not enter. (Until Sept 20, 2026 a Kalshi tape carried no
bars at all, so a strategy conditioned on its underlier could be written but never tested. If your
journal or the library says otherwise, they are out of date; measure it yourself.)

`hours_to_close` is when trading is expected to stop and `hours_to_resolve` when the contract is
expected to pay. For a game the two are the same (it closes when a winner is declared, near its
scheduled end, whatever later close it lists); a weather market stops trading the evening before
it is paid. **The horizon rule:** the House refuses a Kalshi entry expected to pay more than 12
hours out for an `hour` strategy or 48 for a `day` strategy, and closes any crypto position held
longer than 48 hours. Equities are not bounded. Exits are never refused.

## What `decide` returns

```python
{"intents": [
    {"symbol": "BTC/USD", "side": "buy", "notional_usd": 20, "type": "market", "reason": "why"},
    {"symbol": "SPY", "side": "buy", "quantity": 1, "type": "limit", "limit_price": 650.10, "reason": "why"},
    {"market": "KXBTCD-...", "leg": "yes", "side": "buy", "quantity": 5, "type": "limit",
     "limit_price": 0.92, "post_only": True, "reason": "why"},
 ],
 "cancels": ["ord-..."],
 "thought": "what it saw and why it acted or did not",
 "memory": {...}}
```

- `side` is `buy` or `sell`. There are no shorts: a sell closes or trims a holding. On Kalshi,
  betting against a market is buying its `no` leg.
- Give `quantity` or `notional_usd`, not both. `notional_usd` is converted at the touch and
  rounded down to the instrument's step (whole contracts, whole shares for a limit order,
  nine decimals for crypto and fractional market orders).
- `type` is `market` or `limit` (a limit needs `limit_price`). `post_only` rests or is refused.
- Every intent needs a `reason`: it is published next to the trade.
- At most 8 intents and 20 cancels per decision. Anything malformed is dropped and reported back.

## How replay scores it

The simulator (`league/replay.py`) walks a recorded tape step by step. At each step it builds
`ctx` from data at or before that moment only, calls `decide`, and fills conservatively:

- a market order fills at the touch of the same step (buy at the ask, sell at the bid), as a taker;
- a limit order that crosses the touch fills at the touch as a taker, or is refused if `post_only`;
- a resting limit order fills at its own price, as a maker, only when a later step's range trades
  strictly through it (`low < price` for a buy, `high > price` for a sell);
- fees are close to the venue's: Alpaca crypto 0.25% taker and 0.15% maker, Kalshi
  `0.07 x contracts x price x (1 - price)` rounded UP to the cent for a taker, and for a maker
  nothing on most series and that same formula on the few that charge them (your specialty's brief
  names which). The replay charges what the book charges, so a fee you did not model is not a
  surprise waiting on paper;
- Kalshi contracts settle at 1 or 0 on the tape's recorded result;
- the same rung limits and no-shorts, no-leverage rules apply.

The result is the per-block series of after-cost log growth of the account. Every replay ever run
is recorded as a trial and counted against your own LINE -- yourself, your parent, your parent's
parent, never your cousins -- when the deflated Sharpe ratio is computed: grinding many variants
down one line raises the bar for every later one on it.
