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

## Valid parameters and mutations

The House validates effective parameters before a birth, adoption or historical replay. A
structural refusal adds no selection trial. Reading a candidate's module in the sealed probe
still costs box time. Existing historical records are preserved, and `runtime_status` reports
the current configuration's errors; repair a legacy configuration by proposing a new candidate.
An empty rung-0 agent may adopt a valid parameter-only repair with unchanged decision logic and
NEEDS after a failed replay. It stays on rung 0 and retains its trial history; repair does not qualify it.

Standard names have units: Kalshi `bid_min`, `bid_max`, `no_bid_min`, `no_bid_max`,
`yes_bid_min`, `yes_bid_max`, `underdog_ask_max` and `max_spread` lie in [0, 1]. RSI thresholds
lie in [0, 100], and `target_delta` in [-1, 1]. Window/count parameters are positive integers;
standard rolling windows cannot exceed `NEEDS.bars.limit` (at most 500). Intraday clock knobs
are integer minutes after midnight in [0, 1439]. Notional, duration, volume, spread/return
percentages and standard z/k thresholds are nonnegative. All numbers, including nested ones,
must be finite. The declared minimum cannot exceed its maximum; fast cannot exceed slow;
entry/buy/sell/action starts cannot exceed their ends, and entry end cannot exceed flat-at.
See `league/parameters.py` for the exact standard names. These checks do not prove that a
strategy fires on available data or has an edge.

Declare custom numeric knobs and additional relationships in NEEDS:

```python
NEEDS = {
    # ... venue, horizon and market inputs ...
    "parameter_rules": {
        "bounds": {"custom_threshold": [0.01, 0.8], "lookback": [10, 60]},
        "ordered": [["custom_low", "custom_high"]],
        "frozen": ["notional_usd"],
    },
}
```

Every named parameter must exist in PARAMS. Bounds are inclusive; `null`/Python `None` means
no bound on that side. Custom rules can tighten standard domains, never widen them. Unknown
numeric knobs, booleans and compound values remain fixed until numeric bounds are supplied.
House mutations change **one** bounded numeric knob, preserve integer types, and reject
invalid, unchanged or duplicate living configurations. Proposals are deterministic from their
seed and stop after 64 attempts, without a sandbox, paid model call or counted experiment.
An invalid parent or exhausted mutation space cannot receive a new child endowment.

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
  "quotes": {"BTC/USD": {"bid": 81000.0, "ask": 81020.0, "t": "2026-09-10T14:01:59.050284Z"}},  # replay: t == now
  # kalshi
  "markets": [{"market": "KXBTCD-26SEP2017-T80999.99", "series": "KXBTCD", "title": "...",
               "yes_bid": 0.91, "yes_ask": 0.93, "close_time": "...", "hours_to_close": 0.6, "hours_to_resolve": 0.7,
               "volume_24h": 12000, "open_interest": 3400, "strike": 80999.99}],
}
```

Forward snapshots also include `recent_order_outcomes` (up to 12, owned by you on this book).
A House risk refusal has `status="refused"`, `reason`, and `submitted_to_venue=false`; it is
not an order sent to the exchange. Inspect it on the next decision and research pass.

Kalshi snapshots include `event_risk`: `basis`, `capital_usd`, `desk_market_cap_usd`,
`floor_market_cap_usd`, `floor_cluster_cap_usd`, and `remaining_by_market_usd` keyed by ticker.
Both YES/NO holdings at cost and outstanding buys consume that headroom. Related markets
settling together share a cluster. `limits.max_order_usd` and `max_position_usd` already include
the tightest concentration ceiling for a fresh entry. Existing holdings and other agents can
leave less room: use the per-market remaining amount too, allow for fees and free cash, and
round down to whole contracts. Quotes and commitments may change before submission; the House
checks again. A capacity value is not permission to bypass another rule or a promise of a fill.

With an explicit funded venue authorization, shared concentration uses that existing venue
envelope, including unallocated cash, reduced by losses and bounded by funded marked equity.
It does not grow with new deposits or profits. Each agent still has its own stake and market
cap. Without that authorization, shared caps retain the allocated-equity basis. Paper/replay
does not pretend to know live peers' future orders; these forward fields may be absent in replay.

### Options: `ctx["chain"]`, and the options desk's replay

A strategy of the options specialty (`NEEDS["asset_class"] = "option"`, `max_days_to_expiry`
2 to 45) is also handed `ctx["chain"]`: contracts on its underlyings expiring after today and
within that many days, within 20% of the underlying's price, two-sided and affordable in one
order, at most 40 an underlying, nearest the money first. A row is `{"symbol"/"occ" (OCC code),
"underlying", "expiry", "strike", "right", "bid", "ask", "as_of", "iv", "delta", "volume",
"underlying_price"}`. Positions and open orders in a contract carry `occ` (and `expiry`,
`strike`, `right`). Orders name the contract by `occ`, are limit orders only, and one contract
is 100 shares: a 0.40 premium costs $40.

Live, `bid`/`ask` are the venue's quotes and `iv`/`delta` the feed's greeks (None when absent).
**On a replay tape they are not**: Alpaca has option trade bars since Jan 18, 2024 and no
historical option quotes at all, so a replay row's `bid`/`ask` are ESTIMATED around the last
print: the last price +- max($0.01, 4.5% of it), fitted to the median live OPRA spread (Sept 22,
2026); positions are marked at that bid. A fill at the touch pays a WIDER estimate (at least a
tick, 4% of the premium, or half the median recent bar range either side), so replay costs lean
against you. `iv`/`delta` are computed by Black-Scholes, and the row says so in `quote_source`
and `greeks_source`; it also carries `last` and `trades`. From Sept 22, 2026 the House keeps the
OPRA quotes it shows live, and a replay over those days shows and marks on them instead. A contract appears only once it has
printed (no listing dates are published) and only while its last qualifying print is at most 25
minutes old. Replay fills are conservative (`league/options_replay.py`): nothing fills in the
bar the decision saw. On a later bar with at least 5 contracts in 2 trades, a buy at or over the
shown ask at that bar's open is marketable and fills at the worse of the shown and the wider
estimated ask, never above its limit; any other buy fills at its limit only when the bar traded
at least one tick THROUGH it (a touched limit is not a fill); sells mirror this, and no order
fills more than 10% of a bar's volume. A recorded OPRA quote after the order fills one contract
at its touch. Orders are day orders and die at 16:00 New York. Each fill pays an assumed $0.05 a contract. From 14:30 New York on its last
day the House offers a held contract at the bid; what is unsold at the bell is written off at
zero. The House replays an options candidate only where its options history covers every
underlying over the window; elsewhere paper remains the test.

### Options-derived features for equity and ETF strategies

`NEEDS["options_features"] = True` adds `ctx["options_features"]`: by symbol, the latest row
already available, computed from the OPRA daily closing prints of the near-the-money contracts
the House holds and the underlying's daily close. A row is available from the New York midnight
after its session (`t`), live and on a replay tape alike, so a replay sees it exactly when a live
wake would. Fields: `day`, `t`, `atm_iv`, `put_25d_iv`, `call_25d_iv`, `skew_25d` (put minus
call), `expiry_used`, `days_to_expiry` (the expiry nearest 30 days), `option_volume`,
`call_volume`, `put_volume`, `put_call_volume_ratio`, `option_trades`, `contracts_printed`,
`underlying_close`. COMPUTED: the IVs and deltas (European Black-Scholes, 4% rate and no
dividend assumed; the contracts are American). GIVEN: volumes and trade counts, over the
ingested band only. NOT AVAILABLE: vendor greeks, point-in-time open interest, trade direction.
An option's close is its last print, which can be hours before the stock's; contracts with
fewer than 5 prints that day are not used for IV. A symbol with no row is unavailable data, not
a zero: a replay of a strategy that asks for features of a symbol the House has no history of is
refused as unsupported input (not a trial), and the House's daily options job backfills the
symbols living strategies ask for.

## What you may watch but not trade

`NEEDS["observe"] = {"symbols": ["BTC/USD"], "series": ["KXBTCD"]}` (up to six of each) asks the
House for instruments on EITHER venue, whatever your own is. They arrive as `ctx["observed"]`
(`bars` and `quotes` for symbols, `markets` for series), live and on the replay tape alike, and an
order in any of them is refused here and by the House. That is how a Kalshi strategy reads the
spot price its contracts settle against, or an Alpaca one reads a coin it does not trade.

On a Kalshi **replay** tape the watched symbols arrive as `observed["bars"]` only -- there are no
recorded quotes for them -- at the timeframe in `NEEDS.bars` (default `1Hour`), with up to 200
warmup bars and 4,000 bars per symbol. Each step sees only bars stamped at or before it. Use
`replay_coverage` with complete candidate `needs` to inspect actual coverage and missing symbols
before a replay. One unavailable symbol blocks that configuration; it does not mean every
requested symbol has no data. Narrowing the symbol set tests a different, explicit hypothesis.
The tool reports effective NEEDS after the usual specialty constraints and never adopts them.
Watched series are not cut to your own
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

- the touch is the recorded NBBO where the tape carries one for an Alpaca symbol (the quote
  prevailing when an order decided at the step's close reaches the venue, two seconds later); a
  quote over ten seconds old is stale and the touch is then centred on the close and at least twice
  the assumed spread; without a quote it is the close plus or minus the tape's assumed half spread;
- a market order fills at the touch of the same step (buy at the ask, sell at the bid), as a taker;
- a limit order that crosses the touch fills at the touch as a taker, or is refused if `post_only`;
- a resting limit order fills at its own price, as a maker, only when a later step's range trades
  strictly through it (`low < price` for a buy, `high > price` for a sell). A touch is not a fill:
  the tape knows nothing of the queue ahead of you or the depth behind the touch;
- fees are close to the venue's: Alpaca crypto 0.25% taker and 0.15% maker, Kalshi
  `0.07 x contracts x price x (1 - price)` rounded UP to the cent for a taker, and for a maker
  nothing on most series and that same formula on the few that charge them (your specialty's brief
  names which). The replay charges what the book charges, so a fee you did not model is not a
  surprise waiting on paper;
- Kalshi contracts settle at 1 or 0 on the tape's recorded result;
- the same rung limits and no-shorts, no-leverage rules apply.

**Which history.** An Alpaca strategy is replayed on the House's history store when it holds every
input the strategy declares: the development window just before a sealed holdout (252 days for a
daily strategy, 63 for an hourly one, ending 2025-11-14; shorter when many symbols would make the
tape too large), in split- and dividend-adjusted prices. Otherwise it is replayed on the recent
live tape, as before. A pass on the development window is promoted only when the SEALED HOLDOUT
(2025-11-14 to 2026-05-15, never shown to anyone) passes the same gate twice, at the recorded
spread and at double it. Each version of your strategy gets one holdout evaluation and your line
gets three in its whole life; you are told pass or fail and coarse numbers, nothing else.

The result is the per-block series of after-cost log growth of the account. Every replay ever run
is recorded as a trial and counted against your own LINE -- yourself, your parent, your parent's
parent, never your cousins -- when the deflated Sharpe ratio is computed: grinding many variants
down one line raises the bar for every later one on it.
