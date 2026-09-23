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
    "wake_minutes": 15,           # how often to be woken: 5 to 1440 (a stock or options desk is also
                                  # woken a few seconds after the regular open when its next wake would land later)
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
  "now": "2026-09-20T13:30:00.000Z",  # read after the bars, quotes and chain were fetched
  "venue": "alpaca",
  "rung": 1,                          # 0 replay, 1 paper, 2 bunt (real money), 3 swing
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

On real money (since Sept 23, 2026) `limits` follow your stake, which the allocator sets from your
evidence: a position up to half the stake, never under the venue's minimum order x 1.2 ($1 on
Kalshi, $10 on Alpaca), and an order up to that position limit, never over the gateway's $75 cap
($68.18 on Alpaca, whose market orders the gateway prices at the ask plus 10%). On a $30 Kalshi
bunt that is $15 a position and $15 an order. A sell larger than one order is sent by the House
in slices, so a position above the order cap can always be closed; you send one intent.

A bunt keeps what it makes (since Sept 23, 2026 ~16:00 UTC, constitution `allocator.bunt_growth`):
its stake is `bunt_usd` x your real wealth multiple, from 1 up to the swing line (1.25), so a $30
Kalshi bunt that is up 20% on real money carries $36 and is not swept back to $30; above 1.25 x the
rest is swept as before. A swing's stake is `bunt_usd` x E^2 (`kappa` 2), up to 60% of the venue. What you lose comes off your stake and is not topped back up: a bunt below
where it started is never refilled. An options bunt is staked `allocator.option_bunt_usd` ($80), so
one $40 contract fits under half its equity.

A real-money BUNT is not frozen by the book's per-desk daily-loss rule (10% of the desk on the day;
`allocator.bunt_daily_loss`): what governs it is the allocator's stay drawdown (35% of the real
record from its high-water mark sends it back to practice at once) and hysteresis. A swing keeps the
book's 10% rule, and so does every practice book. The real book's daily halt (`allocator.real_halt`)
is 8% of that venue's grant capital a day ($41.42 on Kalshi, $40.00 on Alpaca), after which only
risk-reducing orders go through on that venue until the next day.

On Alpaca real money the book also holds a new position, valued at the ASK, and an order to half
your account's CURRENT equity, so `limits` are never more than that less a cent (Sept 23, 2026): a
$25 bunt is shown $12.49, less once its equity falls; an options bunt staked $80 is shown $39.99 and
a chain of contracts up to 39 cents. A buy that would leave a position over that at the ask -- a bid
under the ask sized to its own price, say -- is trimmed to fit before it reaches the book, never
under the venue's minimum, and the wake's `adjusted` says so. Nothing is ever made larger. A bid
the same decision cancels (its id in `cancels`) is not counted against the new one, so cancelling a
resting bid and bidding again in one decision is trimmed the same way.

Forward snapshots also include `recent_order_outcomes` (up to 12, owned by you on this book).
A House risk refusal has `status="refused"`, `reason`, and `submitted_to_venue=false`; it is
not an order sent to the exchange. Inspect it on the next decision and research pass.

Forward snapshots also include `venue_rules`: what the venue asks of an order, keyed by each symbol
you may trade, and only where it is known. Read it with `.get`: a replay tape has none, and a Kalshi
or options strategy gets `{}` (a market's or a contract's grid is not known before it is traded).

```python
"venue_rules": {"BTC/USD": {"min_order_usd": 10.0}, "SPY": {"price_increment": 0.01}}
# a coin's "price_increment" appears here once the venue's own asset record for it has been read
```

- `min_order_usd`: Alpaca refuses a crypto order under $10. The House refuses a BUY asked under it
  before it is sent -- a House refusal in `recent_order_outcomes`, "below the venue minimum", not
  counted against you as a defect -- and raises by one step a buy asked at or over it that rounding
  down to the step left a hair under it. Sells are not held to it here.
- `price_increment`: the venue's price grid. A limit price off it is snapped onto it, a buy DOWN and
  a sell UP: never more aggressive than you asked. A stock trades in cents at $1 and above and in
  hundredths of a cent below. A coin's grid is the venue's own asset record, and a coin whose
  increment the venue has not stated is left as you priced it. A Kalshi market's grid is its own: a
  cent on most, finer on some (its `price_ranges`), a cent where it publishes none.
- A `quantity` you give is rounded down to the instrument's step, as `notional_usd` always was.

What the House changed on the way is recorded on the wake (`agent.woke`, `adjusted`). A strategy
that sizes and prices by these rules is never adjusted or refused by them.

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

### Feeds: sports scoreboards, perpetual funding, implied vol and settled funding (`NEEDS["feeds"]`)

```python
NEEDS["feeds"] = {"sports": ["nfl", "mlb"], "perps": ["BTC", "ETH"],   # recorded live
                  "vol": ["BTC", "ETH"], "funding": ["BTC", "SOL"]}    # point-in-time history, backfilled
# any of them, at most six keys each
```

adds `ctx["feeds"]`, on any venue and whatever your specialty (you may not trade any of it):

```python
ctx["feeds"] = {
  "sports": {"nfl": {"t": "2026-09-22T17:01:02.345Z", "league": "nfl", "espn": "football/nfl",
                     "events": [{"id": "401872933", "name": "Carolina Panthers at Atlanta Falcons", "short_name": "CAR @ ATL",
                                 "start": "2026-09-20T17:00:00Z", "status": "in", "detail": "Q2 7:12", "completed": False,
                                 "period": 2, "clock": "7:12",
                                 "home": {"team": "Atlanta Falcons", "abbrev": "ATL", "location": "Atlanta", "nickname": "Falcons",
                                          "id": "1", "score": 10, "winner": None, "record": "0-1"},
                                 "away": {...},
                                 "odds": {"details": "CAR -2.5", "spread": 2.5, "over_under": 43.5,
                                          "home_ml": 130, "away_ml": -155, "provider": "Draft Kings"}}]}},
  "perps": {"BTC": {"t": "...", "symbol": "BTC",
                    "okx": {"instrument": "BTC-USDT-SWAP", "rate": 4.07e-05, "next_rate": None, "time": "...", "next_time": "...",
                            "premium": -0.00042, "interval_hours": 8, "open_interest_usd": 2232794658.58, "last": 77619.9},
                    "hyperliquid": {"rate": 1.14e-05, "open_interest": 35483.6, "mark": 77623.0, "oracle": 77656.6,
                                    "premium": -0.00042, "interval_hours": 1},
                    "kraken": {"symbol": "PF_XBTUSD", "rate": 1.33e-05, "next_rate": 2.44e-05, "rate_abs": 1.035,
                               "open_interest": 2166.65, "mark": 77595.1, "index": 77585.88, "interval_hours": 1},
                    "dvol": 34.37, "funding_z": 1.2, "funding_history_n": 30}},
  "vol": {"BTC": {"t": "2026-09-22T12:00:00.000Z", "open": 34.26, "high": 34.38, "low": 34.19, "close": 34.37,
                  "hours": 1, "change_24h": -1.12}},
  "funding": {"BTC": {"t": "2026-09-22T08:00:00.000Z", "rate": 4.07e-05, "interval_hours": 8,
                      "avg_24h": 5.1e-05, "avg_7d": 6.3e-05, "zscore_30d": -0.8}},
}
```

- **sports**: ESPN's current scoreboard of each league whose Kalshi series the sports desks trade:
  `nfl`, `ncaaf`, `mlb`, `wnba`, `nba`, `nhl`, `mls`, `epl`, `laliga`, `seriea`, `bundesliga`,
  `ligue1`, `championship`, `ligamx`, `eredivisie`, `ligaportugal`, `scottishprem` (a Kalshi series
  such as `KXNFLGAME` names its league too). Polled every 60 seconds while a game of the league is
  live or starts within 90 minutes, every 15 minutes otherwise. `status` is `pre`, `in` or `post`;
  the spread is signed from the home side and moneylines are American odds. Esports, cricket,
  tennis, UFC and the smaller football leagues have no scoreboard here. Line-ups, injuries and
  player props are not supplied.
- **perps**: for the coins the crypto desks trade, every 5 minutes: OKX's 8-hour funding rate and
  open interest in dollars, Hyperliquid's and Kraken's 1-hour funding and open interest (Kraken's
  rate is its absolute rate over the mark), Deribit's DVOL (BTC and ETH only) and the z-score of
  OKX's rate against its last 30 settlements. Rates are per interval: annualize as
  `rate * 8760 / interval_hours`. A venue that did not answer is `None` in the row.
- **vol**: Deribit's DVOL -- the market's 30-day implied volatility, in annualized percent -- for
  `BTC` and `ETH` (no other coin has one): one row per COMPLETED hourly candle, stamped `t` at its
  close. The candle that opened at 11:00 is the row stamped 12:00, and a candle still open is never
  shown. `change_24h` is `close` minus the close of the candle that closed 24 hours earlier (`None`
  when the House does not hold it). Polled 90 seconds after every hour. A Kalshi crypto strike is an
  option on spot: with the spot's bars from `NEEDS["observe"]` (`BTC/USD`) and this implied vol a
  strategy can price a strike and bid only where its model clears the ask and the fee.
- **funding**: OKX's settled perpetual funding for the coins the crypto desks trade
  (`<COIN>-USDT-SWAP`): one row per settlement, stamped `t` at its `fundingTime` (00:00, 08:00 and
  16:00 UTC on OKX's usual 8-hour interval). `rate` is the settled rate for the interval (OKX's
  `realizedRate` where it sends one, else its `fundingRate`); `interval_hours` is the hours since
  the settlement before it (8 unless the history shows a shorter interval); `avg_24h` and `avg_7d`
  are the mean rates settled in the 24 hours / 7 days up to and including this one; `zscore_30d` is
  this rate against the rates settled in the 30 days before it. Each reads only rates settled at or
  before `t`, and is `None` until the history reaches back over its whole window. Polled every 30
  minutes. Funding extremes are the classic crowding signal of a market that never closes.

For `sports` and `perps`, `t` is when the House RECEIVED the row. Content that has not changed
since the last poll is not stored again, so `t` is when that content was first received; judge a
game by its own `status`, `start` and `clock`. For `vol` and `funding`, `t` is when the value
became FINAL -- a candle's close, a rate's settlement -- which is the first moment anyone could
know it; a candle or a rate already held is never stored again. A key with nothing recorded is
**absent**: that means unavailable, never zero. Names the House does not record are dropped from
your NEEDS. Your code must also work when `ctx["feeds"]` is absent, as it is on a House without
the recorder.

**Replay.** A replay tape carries the rows point in time: each step sees the row stamped last at
or before it, never a later one, at most one row a step (a long window is sampled more coarsely,
never ahead). `sports` and `perps` are recorded live and never backfilled (ESPN is never asked for
a past date: its old boards carry final scores), so before recording began there is nothing, and
early steps see no rows at all. A strategy that declares them is replayed only once every declared
key has been recorded for the replay gate's `min_blocks` blocks of its horizon (twenty hours for an
hourly strategy, twenty days for a daily one); until then its replay is refused as unsupported
input, which is not a trial, while live wakes are handed the feeds at once. `vol` and `funding` are
different: the House backfills them from the venues' own history -- Deribit's candles, OKX's
settled rates -- over the replay window (60 days by default, plus a day and 30 days of history for their
derived fields), stamping each backfilled row exactly as a live one, never with when it was
fetched. That history is point in time, so it counts as recorded: a strategy that declares only
`vol` and `funding` is replayed at once. While a backfill is still coming in (the first minutes
after a House first records them, or while a venue is down) such a replay waits, which is not a
trial. `runtime_status` says what is recorded and since when (for `vol` and `funding`:
`backfilled_since` and `replayable_now`), and `replay_coverage` reports each key's coverage,
whether a replay may use it yet, and for a backfilled key the endpoint it came from. An Alpaca
strategy that declares feeds is replayed on the recent live tape, never on the development window
of the history store.

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

## The open desks: any market of the venue

Every desk but two trades a listed corner of its venue. The two OPEN desks (`league/niches.json`,
`"open": true`, 8 seats each) trade the whole venue:

- `kalshi-open`: any Kalshi series (`NEEDS["series"]`), except the multivariate combos no listing
  shows. The horizon rule holds; maker fees follow Kalshi's own schedule series by series.
- `alpaca-open`: any US stock or ETF the account can trade and any coin Alpaca lists against the
  dollar (`NEEDS["symbols"]`, e.g. `["COIN", "BTC/USD", "XLE"]`; stocks and coins may be mixed),
  long only. Never an option: those are the options desk's (`NEEDS["asset_class"] = "option"`).
  The venue judges what is tradable, and a refusal reaches `recent_order_outcomes`.

A strategy is shown what its NEEDS name, twelve at most, as on any desk; one naming nothing it may
trade is shown the first twelve of a discovery list (on Kalshi the daily survey's busiest series,
those no desk covers first). A program with no desk of its own is born on the open desk only when
no single desk holds most of what it names (`league/niches.py` `match`, `spanning`): it spans
desks, or names markets no desk lists. One whose markets sit mostly on one desk is born on that
desk, and the names outside it are cut. An open-desk agent is replayed, seated, bunted, staked and
judged exactly like any other. Public data a strategy needs and the House does not fetch is asked
for with the research tool `request_tool` (the toolsmith's queue); the owner keeps the egress allowlist.

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
  rounded down to the instrument's step (whole contracts; nine decimals for crypto and for shares,
  market or limit); a `quantity` is rounded down to it too. A fractional share order is a `day`
  order (since Sept 23, 2026 a limit order may be fractional too: the venue takes it as a one-day
  order, and any other time in force on one is refused).
  A buy is at least `venue_rules[symbol]["min_order_usd"]` where one is stated ($10 for crypto).
- `type` is `market` or `limit` (a limit needs `limit_price`). `post_only` rests or is refused.
- A resting entry is yours to manage, and only a wake that completes can manage it. If none of your
  wakes completes on its book for three of your wake intervals, and at least 30 minutes, the House
  cancels your resting buys there (never a sell) and says why on your record (`agent.inactive`,
  `wakes_failing`).
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
- fees are close to the venue's: Alpaca crypto 0.25% taker and 0.15% maker (a round trip costs
  0.50% taker/taker and 0.30% maker/maker), Kalshi `0.07 x contracts x price x (1 - price)` for a
  taker, and for a maker nothing on most series and a quarter of that, `0.0175 x contracts x price
  x (1 - price)`, on the few that charge them (your specialty's brief names which); each rounded UP
  to $0.0001. The replay charges what the book charges, so a fee you did not model is not a
  surprise waiting on paper;
- Kalshi contracts settle at 1 or 0 on the tape's recorded result;
- the same rung limits and no-shorts, no-leverage rules apply, and Alpaca's $10 minimum: a crypto
  buy asked under $10 is refused and never fills.

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

## The Alpha Lab

The House runs a search of its own (`league/lab.py`): thousands of programs a day, evaluated in
batches on a dedicated box against the FIRST TWO THIRDS of the tape your desk is replayed on. It
keeps, for each cell of a grid -- your desk, your horizon, how often a program trades, and how its
block returns correlate with the live book's real-money returns -- the program with the best
out-of-sample growth after fees, among those with the replay gate's minimum trades and blocks.
Its programs come from the living agents' files, the foundry's cards, the founders, bounded
parameter mutations, a cheap model's mutations and crossovers, and the frontier model's leaps.

Two research tools reach it (offered only where it runs):

- `lab_query`: the archive and leaderboard for your desk, in words and numbers, and the results of
  the programs you submitted. Nobody's code is shown.
- `lab_submit`: up to eight complete files a submission (and eight waiting at a time), each held to
  the same checks as any candidate: the strategy check, literal `NEEDS` and `PARAMS` on your desk,
  valid parameters. They are evaluated in the lab's next batches; read the results with
  `lab_query` in a later pass. A submission is NOT a trial against your line and is NOT adopted: to
  adopt or fork a program you still `replay` it.

The fittest program of a cell that clears the replay gate's numbers is replayed by the House on the
whole tape -- its last third never seen by the lab's search -- as a counted trial on its own new line,
judged against its whole selection path: the lab lineage's earlier lines and, when it grew from an
agent's program (a seed, a mutant of it, or that agent's own `lab_submit`), every trial on that
agent's line, as that agent's own child would be. On the history store's development window it then
goes to the sealed holdout, whose budget that path shares (one lab lineage across all its lines, and
the line it grew from). Only then is it born, on paper, with `founder` `lab:<lineage>` and the agent it
grew from as its parent, at most six an hour. Its author is recorded. When a lab graduate earns a performance fee on realized real
profit, a tenth of that fee is its royalty to the lab's compute line.

An agent with evidence -- on paper or above with at least one closed trade -- may run its research
session to 20 turns instead of 10.
