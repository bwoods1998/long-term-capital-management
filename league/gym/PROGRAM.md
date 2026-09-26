# Writing a Gym program

A program is one Python file: `NEEDS`, `PARAMS` and `decide(ctx)`. The Gym replays it over recorded
one-minute option quotes (NBBO with sizes); the House runs the same file on live quotes. It never sees
a date or a year. Examples: `league/gym/examples/condor_vrp.py`, `putspread_dip.py`.

## The file

```python
import math
import numpy as np            # math and numpy only; nothing else imports

NEEDS = {"roots": ["SPY"], "dte": [0, 2], "band": 0.04, "cadence": 5, "history": 10}
PARAMS = {"entry_delta": 0.15, "width": 1.0, "risk_usd": 150.0}
STATE = {}                     # module globals persist between calls: your memory for the run

def decide(ctx):
    return [...]               # a list of intents (or [] / None)
```

Rules (a program that breaks one is refused before it runs): imports `math` and `numpy` only; no
`print`, `open`, `eval`, `exec`, classes, decorators, generators, `id`, `hash` or `type`; no attribute
starting with `_`; no attribute assignment (keep state in dicts); no numpy file, memory, random or date
functions (`np.load`, `np.save`, `np.random`, `np.datetime64`, `.tofile`, `.base`, ...); **no year or
date literal** (an integer 2019-2030, a YYYYMMDD integer, a string holding a year or an ISO date).
A decide call has 1 second; 25 errors or timeouts disqualify the run. Be deterministic: same inputs,
same outputs.

## NEEDS

| key | meaning | default |
|---|---|---|
| `roots` | option roots to trade: SPY, QQQ, IWM, XSP, SPXW, single names in the store | required |
| `dte` | `[min, max]` calendar days to expiry of the chain you are shown (0-60) | `[0, 7]` |
| `band` | strikes within +-band of spot, a fraction (0.002-0.30) | `0.05` |
| `cadence` | minutes between decide calls (1-30) | `5` |
| `history` | prior sessions of daily bars in `ctx.under` (0-60) | `10` |
| `start`, `end` | first and last decision minute (minutes since midnight ET) | `571`, `958` |

Smaller slices and slower cadences run faster. Legs you open may lie outside the slice.

## PARAMS

A dict of numbers, booleans, strings or short lists. A run may override any of them (same type), so a
parameter sweep needs no new code; each distinct (code, PARAMS) is a separate trial. Read them as
`ctx.params`.

## ctx

Time: `ctx.minute` (minutes since midnight ET; 570 = 09:30), `ctx.open_minute`, `ctx.close_minute`
(960, or 780 on a half day), `ctx.minutes_to_close`, `ctx.weekday` (0 Monday .. 4 Friday).
Events (booleans for today and the next session): `ctx.events`, `ctx.events_next`, keys `fomc`, `cpi`,
`jobs`, `monthly_opex`, `quarter_end`, `half_day`.

Chain: `ctx.chains[root]` (and `ctx.chain` for the first root). numpy arrays, one entry per contract
with a two-sided quote now, sorted by expiry, strike, call before put:
`id` (name the contract in a leg as `{"id": ...}`), `dte`, `strike`, `is_call`, `bid`, `ask`, `mid`,
`spread`, `bid_size`, `ask_size`, `oi`; computed on first read (Black-Scholes on the mid): `iv`,
`delta`, `gamma`, `theta` (a calendar day), `vega` (a vol point). Also `spot`, `n`, `expiries` (the
days to expiry present). A root with no data now is absent from `ctx.chains`.

Underlying: `ctx.underlyings[root]` (and `ctx.under`): `price` now, `prices` (today's one-minute
prices from the open to now), `open`, `high`, `low` (today so far), `prior_close`, and the prior
sessions oldest first: `closes`, `opens`, `highs`, `lows`.

Account: `ctx.positions` (list of dicts: `id`, `type`, `root`, `qty`, `legs` [each `id` (-1 when not
in today's chain), `dte`, `strike`, `is_call`, `side`, `ratio`], `entry`, `mark`, `natural`, `pnl`,
`max_loss`, `credit`, `held_minutes`, `held_days`, `tag`), `ctx.orders` (working orders: `id`, `kind`
open/close, `type`, `qty`, `filled`, `limit`, `age_minutes`, `position`, `tag`), `ctx.closed`
(positions closed since your last call: `id`, `pnl`, `reason`, `tag`), `ctx.rejects` (why your last
intents were refused), `ctx.cash`, `ctx.equity`, `ctx.budget` (your capital), `ctx.buying_power`.
Rules: `ctx.rules[root]` (cutoff minutes, `types` allowed, `kind` equity/index, ticks). `ctx.params`.

## Value: one signed number

A structure's **value** a share = sum over legs of side x ratio x price (long +1, short -1). A debit
structure has a positive value, a credit structure a negative one. An open PAYS its value; a close
RECEIVES it. `entry`, `mark` (at the mid now), `natural` (closing now at the touch), every limit and
every exit are values, and a trade's P&L is (exit - entry) x 100 x qty - fees. Selling a condor for a
0.40 credit is entry -0.40; buying it back for 0.10 is exit -0.10: P&L +30 a condor before fees.

## Intents

**Open** a structure:

```python
{"open": "iron_condor", "root": "SPY",
 "legs": [{"side": "long",  "right": "P", "rel": 1, "offset": -1.0},
          {"side": "short", "right": "P", "dte": 0, "delta": 0.15},
          {"side": "short", "right": "C", "dte": 0, "delta": 0.15},
          {"side": "long",  "right": "C", "rel": 2, "offset": 1.0}],
 "max_loss": 150.0,            # or "qty": 1
 "limit": "natural",           # or "mid", {"mid": k}, {"price": value}
 "tif": 10,                    # minutes to work; "day" (default) or "ioc"
 "tag": "vrp", "note": "iv 0.18 vs realized 0.12"}
```

Types: `long_call`, `long_put`, `debit_vertical`, `credit_vertical`, `iron_condor`, `iron_butterfly`,
`long_butterfly` (body `"ratio": 2`), `long_straddle`, `long_strangle`, `calendar`, `diagonal`
(equity roots only; the short leg expires first). Every structure is defined-risk; no naked short.
Real money trades only the first five multi-leg types that close in one order (verticals, condors,
iron butterflies, long butterflies) until others are proven.

A leg: `side` long/short, `right` "C"/"P", `ratio` (1, or 2 for a butterfly's body), `dte` (the nearest
quoted expiry at or after it), and exactly one selector: `id` (a contract from `ctx.chain.id`),
`strike` (nearest), `delta` (nearest |delta|), `moneyness` (strike nearest spot x (1 + m)), `atm`
(k strikes from the money, + up), or `rel` + `offset` (the strike nearest another leg's strike +
offset dollars; same expiry unless `dte` is given; `rel` is that leg's position in `legs`).
Size: `qty`, or `max_loss` dollars (the most whole structures whose maximum loss plus fees fits).

**Close** a position: `{"close": position_id, "limit": "natural", "qty": 1 (default all), "tif": ...}`.
**Cancel** a working order: `{"cancel": order_id}`. Up to 12 intents a call, 60 orders a day.

## How orders fill (honestly)

An order meets the quotes of the minute AFTER your decision. A limit at or through the natural price
(long legs at the ask, short legs at the bid) fills at the natural, up to the quoted size (the
smallest leg's size over its ratio); the rest keeps working. A limit better than the natural works
until its tif: it fills at its limit when the natural comes through it, and otherwise only with the
fill model's calibrated probability for that distance from the mid (none at all until the model is
calibrated: assume mid orders do not fill). Draws are keyed by contract and minute, not by you.
Fees: OCC, ORF, CAT on every contract, TAF and SEC on sells, $0.50 plus exchange fees on index
options. Buying power: an open reserves (maximum loss + fees) x 1.1; a credit position holds its
collateral. The gate also runs you at 1.5x the half-spread: an edge that lives inside the spread fails.

## The venue's clock

Options trade 09:30-16:00 ET (13:00 on a half day). On a contract expiring today: no new opening order
from 15:00; no closing order from 15:10 (15:25 SPY/QQQ); from 15:30 whatever remains of an equity
position is liquidated at the natural. Equity options are physically settled: a short leg left in the
money becomes shares, marked to the next session's first price. XSP and SPXW are cash-settled at the
close (hold them to expiry if you like; no calendars there). At the end of a run everything open is
closed at the natural.

## What a run tells you

`summary` (trades, P&L, P&L per dollar of maximum loss, its t statistic, win rate, profit factor,
Sharpe on daily P&L, drawdown, turnover, fees, quarters positive), `fills` (fill rate, fills at the
natural, slippage, rejects and why), `breakdown` by weekday, time of day, DTE, realized and implied vol
tercile, quarter, type, root and exit reason, the `worst` trades with their context, and on Train
every trade. Every run is one trial and is counted: many runs that each look good by chance are how
a search fools itself, so the gate deflates for them.
