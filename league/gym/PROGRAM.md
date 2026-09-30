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
`print`, `repr`, `open`, `eval`, `exec`, classes, decorators, generators, `id`, `hash` or `type`; no
attribute starting with `_`; no attribute assignment (keep state in dicts); no numpy file, memory,
random or date functions (`np.load`, `np.save`, `np.random`, `np.datetime64`, `.tofile`, `.base`,
`.flags`, ...); no bare `except:`, no `BaseException`, no `return`/`break`/`continue` inside `finally`;
**no year or date literal** (an integer 2019-2030, a YYYYMMDD integer, a string holding a year or an
ISO date). The arrays you are handed are read-only.
A decide call has 1 second, a run's calls 900 seconds in all; 25 errors or timeouts disqualify the
run. Be deterministic: same inputs, same outputs.

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
`ctx.params`. The runtime also binds the merged values to `PARAMS` **at its declaration**, before
subsequent aliases, derived module values or helper-function defaults are evaluated. Thus
`p = PARAMS` and `def helper(p=PARAMS)` see the requested variant too. Declare PARAMS exactly once
with a simple top-level assignment; do not rebind or shadow it, or mutate it in the module body.
Keep changing run memory in STATE. Every `program.start()` executes a fresh module: state persists
between decisions within that run, including across its sessions, but never across independent runs.
Both default and override lists are copied so one runner cannot mutate the next runner's parameters.

The research interface checks literal PARAMS and NEEDS before replay, and refuses a changed override
when static analysis proves its key is never read. Dynamic parameter access remains inconclusive,
not a refusal. An accepted check does not prove the parameter changes behavior, a signal is useful,
or a strategy trades; no-trade results remain valid observations to diagnose.

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
days to expiry present). A root with no data now is absent from `ctx.chains` (and `ctx.chain` is None
when the first root has none): check before you read.

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
All listed types are valid Gym research choices; single long calls and puts have no lesser status
than spreads. The current production adapter allows five spread types (verticals, condors, iron
butterflies, long butterflies); that implementation limit does not define Alpaca's full capability.
Covered calls and cash-secured puts require inventory/collateral support that this interface does
not yet implement. Paper and production adapters must be verified separately; research support
alone does not enable either route.

A leg: `side` long/short, `right` "C"/"P", `ratio` (1, or 2 for a butterfly's body), `dte` (the nearest
quoted expiry at or after it), and exactly one selector: `id` (a contract from `ctx.chain.id`),
`strike` (nearest), `delta` (nearest |delta|), `moneyness` (strike nearest spot x (1 + m)), `atm`
(k strikes from the money, + up), or `rel` + `offset` (the strike nearest another leg's strike +
offset dollars; same expiry unless `dte` is given; `rel` is that leg's position in `legs`).
Size: `qty`, or `max_loss` dollars (the most whole structures whose maximum loss plus fees fits).

**Close** a position: `{"close": position_id, "limit": "natural", "qty": 1 (default all), "tif": ...}`.
**Cancel** a working order: `{"cancel": order_id}`. Up to 12 intents a call, 60 orders a day.

## How orders fill (honestly)

An order meets the quotes of the minute AFTER your decision, and every chance in a fill is drawn by
(contract, minute), never by you:

- **Natural** (long legs at the ask, short legs at the bid), or any limit at or through it, always
  fills, at the natural, up to the quoted size (the smallest leg's size over its ratio); the rest
  keeps taking the natural as size appears. It pays every leg's whole half-spread, in and out.
- **Patient pricing is modelled, and it is often cheaper than the natural.** A limit short of the
  natural (`{"mid": k}`: k ticks from the mid toward the natural; `"mid"`; `{"price": v}`) works for
  its `tif` minutes (`"day"` by default). Each minute it has not filled, it fills AT ITS LIMIT if
  the natural has come through it, and otherwise with the fill model's probability for that minute:
  how often Train's recorded trades printed at or through that distance from the mid on a quoted
  contract-minute like yours (the same root, days to expiry, moneyness, time of day), a point
  estimate pooled toward coarser cells where data is thin. A multi-leg package gets the LOWEST of
  its legs' rates, each leg at its own strike and expiry, from complex-order prints and never above
  that leg's single-leg rate. A passive fill takes at most the contracts Train's fills at that
  distance typically found (one structure where unknown), and in one minute all your orders on a
  contract share that liquidity: the rest keeps working. It never fills on a minute after which the
  mid holds still or moves your way (a passive fill is someone else's good trade). **Not modelled,
  so natural only:** a structure with any leg 8 or more days to expiry (the trade sample stops at 7
  days; back months fill at or through the natural until they are sampled), a root the sample never
  covered, and a leg further from the money than the sample reached often enough (far wings: a
  package with such a leg fills only at or through the natural too).
  So a limit a tick or two inside the natural, or at the mid, with a `tif` of 10-30 minutes can save
  much of the half-spread on entries and exits; what it costs is the fills you miss (the market
  leaves without you) and the adverse selection of the ones you get. Your results' `fills` show what
  your prices got: fill rate, the share filled at the natural, slippage from the mid in half-spreads.
- A limit off the tick rounds to your own side of the book, so `"mid"` on a one-tick single leg is
  the touch (the bid for a buy, the ask for a sale): the touch fills only in minutes when Train's
  prints there traded through the whole displayed queue ahead of you. A limit behind the touch
  fills only when the market comes through it.

A package never trades outside what it can be worth at expiry (a debit vertical 0 to its width, a credit
vertical or condor minus its widest wing to 0): when a leg's quote blows out (an index leg in the money
quoted with no bid and a far ask, an FOMC minute, the last minutes of an expiry) and the legs' touches add up to a price
outside that range, that minute is no market: an open at or below the package's least (a vertical for 0.00) or above
its most, or a close that would receive more than its most, fills nothing that minute whatever its limit (it keeps
working; arriving then, it is judged by the natural it was decided on), and a close that would receive less than its
least fills at that least, so a close never loses more than the maximum loss (an equity-root expiry close held back to
the cutoff is exercised into shares instead, and an overnight gap can exceed it). The account's mark is the last mid
inside the range; an exit at a stale mark, or a window end over the most, leaves at the last natural the package
traded at, with fees. Calendars and diagonals have no such bound.
A long wing with no bid is closed at zero. Fees: OCC, ORF, CAT on every contract, TAF and the SEC fee
($20.60 a million of premium) on sells, $0.50 plus exchange fees on index options. Buying power: an open reserves (maximum loss + fees) x 1.1; a credit position holds its
collateral. A debit at or over a bounded structure's width is refused. The gate also runs you at 1.5x
the half-spread (passive fills pay the extra half-spread too and fill HALF as often, and a limit that is
passive at the real quotes stays passive): an edge that lives inside the spread, or only in patient
fills, fails.

## The venue's clock

Options trade 09:30-16:00 ET (13:00 on a half day). On a contract expiring today: no new opening order
from 15:00; no closing order from 15:10 (15:25 SPY/QQQ). From 10 minutes before that cutoff
(`expiry_close`) the House closes an expiring equity position at the natural when a leg expiring today
is in the money or out of it by 1% of the strike or less, and an expiring long call or put whatever
its moneyness while it has a bid; your own close is refused from then. What only gets that close
later is liquidated at the natural from 15:30; one whose every expiring leg stays further out of the
money (a long call or put: with no bid) is left to expire at its intrinsic value (normally zero, no
fee). Equity options are physically settled: a short leg left
in the money becomes shares, marked to the next session's first price. XSP and SPXW are cash-settled
at the close at intrinsic value (the recorded settlement where the store has one, else the 16:00
index level), never liquidated; hold them to expiry if you like; no calendars there. An expiry on a
day the run did not replay settles all the same. At the end of a run everything open is closed at
the natural; at an inner boundary of a split Train run it is valued at the mid with no fee
(`split_mark`). Validation, holdout and forward runs are never split. A stock split is another
matter: a name's listed contracts change at a split, so on its eve (from the Gym's table of public
splits, never from prices) everything open on that name is closed at the natural of the session's last
quoted minute (`stock_split`; leg by leg, at a leg's last quote or else its intrinsic value, when no
minute quotes them all: `stock_split_legs`), and an opening order on it that would be held across the
split (a leg expiring after the eve) is not placed. The underlying's history is the price as traded,
not split-adjusted: a split shows in it as a gap.

## What a run tells you

`summary` (trades, days_traded, P&L, P&L per dollar of maximum loss, `t_daily` (the t of the DAILY
return on maximum loss: the statistic the validation line tests; five lots on one day are one day's
evidence), win rate, profit factor, Sharpe on daily P&L with its skew and kurtosis, drawdown,
turnover, fees, quarters positive, the median maximum loss of one structure), `fills` (fill rate,
fills at the natural, slippage, rejects and why), `breakdown` by weekday, time of day, DTE, realized
and implied vol tercile, quarter, type, root and exit reason, and on Train the `worst` trades with
their context and every trade. A validation run shows the statistics and breakdowns only (no trades,
no dates, no daily series) plus its 1.5x-stress twin. Every run is one trial and is counted: many
runs that each look good by chance are how a search fools itself, so the gate deflates for them.
