# Writing a panel program

> Owner: package C of release E4 (league/xs/E4_INTERFACES.md). The contract between a panel program and the House:
> the registered contract C-XS-1 of the screen's pre-registration (XSCREEN-1), made narrower where this file says so,
> never wider. The Gym engine (`league/xs/engine.py`) and the House's book (through `league/xs/book.py`) both follow
> it; what a program sees is built by one function for both (`league/xs/ctx.py`), and every statement about it here
> is held by a test in `league/tests/test_xs_*.py`.

A panel program is one Python file: `NEEDS`, `PARAMS` and `decide(ctx)`. It holds 5 to 12 stocks picked out of the
day's S&P 500 members by a cross-sectional rule, long only, in cash. The House asks it once a week or once a month,
after a close; what it asks for executes in the NEXT session, at the open or at the close. The Gym replays the same
file over daily bars.

**It sees slots, not stocks.** No ticker, no company, no date, no price level, no share count, no dollar volume, no
size. A slot's id is a salted number: the same stock keeps it for one run and has another in every other run.

**It is judged on its residual, never on raw P&L.** Each lot is compared with its CELL: the names that shared its
sector, its beta group and its 12-1 momentum group at the decision. The residual is the program's P&L after its costs
minus the cost-free P&L of those cells, one number a day. Choosing a sector, a beta or a momentum tilt earns nothing
by itself; choosing the better names inside a cell does. The screen then ranks the residual against 999 portfolios
that kept the program's schedule, weights and cells and drew other names.

## The file

```python
import math
import numpy as np            # math and numpy only; nothing else imports

NEEDS = {"panel": "sp500", "history": 60, "max_names": 8, "rebalance": "weekly", "weekday": 0,
         "max_hold_sessions": 30}
PARAMS = {"lookback": 5, "weight": 0.125}
STATE = {}                     # module globals persist between calls: your memory for the run

def decide(ctx):
    if ctx.n < 40:
        return {"hold": True}
    past = np.sum(ctx.ret[:, -PARAMS["lookback"]:], axis=1)        # each slot's return over the last week
    score = np.full(ctx.n, np.nan)
    for code in set(ctx.sector.tolist()):                           # rank inside each sector: losers first
        inside = np.flatnonzero(ctx.sector == code)
        score[inside] = past[inside] - np.nanmean(past[inside])
    order = [int(i) for i in np.argsort(score) if math.isfinite(float(score[i]))]
    picks = [int(ctx.ids[i]) for i in order[:ctx.max_names]]
    if len(picks) < 5:
        return {"target": {}, "at": "open"}                         # all cash
    return {"target": {slot: PARAMS["weight"] for slot in picks}, "at": "open"}
```

The code rules are the options contract's, unchanged (`league/gym/safety.py`, `league/gym/PROGRAM.md` "Rules"):
imports `math` and `numpy` only; no `print`, `repr`, `open`, `eval`, `exec`, classes, decorators, generators, `id`,
`hash` or `type`; no attribute starting with `_`; no attribute assignment; no numpy file, memory, random or date
functions; no bare `except:`; **no year or date literal**. A decide call has 1 second; 25 errors or timeouts disqualify
the run. Be deterministic.

## NEEDS

| key | meaning | default |
|---|---|---|
| `panel` | the panel you read: `"sp500"` | required |
| `rebalance` | when you are asked: `"weekly"` or `"monthly"` (never daily) | required |
| `weekday` | weekly only: you are asked at the close before the week's first session on or after this weekday (0 Monday .. 4 Friday); a week with no such session has no decision | `0` |
| `history` | sessions of history in each field (20-252) | `252` |
| `max_names` | the most names a target of yours may hold (5-40; the lane admits at most 12) | `10` |
| `max_hold_sessions` | the most sessions the House lets a lot of yours be held (5-60) | `60` |

No other key is allowed. A malformed NEEDS refuses the program.

## PARAMS

As the options contract: a dict of numbers, booleans, strings or short lists, bound at its declaration; each distinct
(code, PARAMS) is a separate trial. Read them as `ctx.params`.

## ctx (at the decision close of session t)

`n` is the number of ELIGIBLE names that day and h is your `history`. Rows are slots in ascending id; columns are
sessions, oldest first, the last one session t.

| field | what |
|---|---|
| `ctx.n` | how many slots (it can be 0: your run's first decision may have none) |
| `ctx.ids` | int32 (n,): the slot ids. A target names these and nothing else |
| `ctx.ret` | (n, h + 1): close-to-close total return (the first column is NaN) |
| `ctx.oret` | (n, h + 1): the open over the previous close, minus 1 (the first column is NaN) |
| `ctx.iret` | (n, h + 1): the close over the open, minus 1 |
| `ctx.range` | (n, h + 1): (high - low) / close |
| `ctx.rel_volume` | (n, h + 1): the session's volume over the median of the name's own 63 sessions through it (split-adjusted; NaN with fewer than 32 traded sessions among them, and for sessions more than 190 back) |
| `ctx.sector` | int8 (n,): the sector code, 0-10. The fund the name's market-residual returns followed most closely over the last 252 sessions; the codes are relabelled in every run |
| `ctx.beta` | (n,): beta to the market over the last 252 returns, 2 decimals |
| `ctx.mkt` | the market's own five fields, each (h + 1,): `ctx.mkt.ret`, `.oret`, `.iret`, `.range`, `.rel_volume` |
| `ctx.positions` | your open lots: `{id, slot, weight, ret, held_sessions, at, tag}`: `id` the lot's, `slot` its name's id, `weight` its share of your equity, `ret` its return since entry, `held_sessions` the sessions since its entry session (0 at that session's own close), `at` how it was filled |
| `ctx.closed` | lots closed since your last call: `{id, slot, net_ret, held_sessions, reason, tag}`; `net_ret` after costs, over the lot's entry dollars; `reason` "program", "max_hold", "house" or "vanished" |
| `ctx.rejects` | why orders of your last target were refused |
| `ctx.cash`, `ctx.equity` | your sleeve's free cash, and its equity (cash + lots), dollars |
| `ctx.budget` | the sleeve's size your weights are shares of (the Gym: $1,000; it does not compound) |
| `ctx.weekday` | 0 Monday .. 4 Friday, of session t |
| `ctx.session_of_month`, `ctx.sessions_left_in_month` | 1 on the month's first session; 0 on its last |
| `ctx.last_session_of_week` | whether t is the last session of its week |
| `ctx.max_names` | your NEEDS `max_names` |
| `ctx.params` | your PARAMS (a copy: changing it changes nothing) |

NaN means no bar that session (a halt reads as no bar). Every figure is rounded to 6 decimals. There is no event
flag, no year, no month and no day of the month.

**Who is a slot.** A name is eligible at t when it is an index member on t and on the next two sessions (changes are
announced ahead: a name about to leave is already gone), it traded on t and on the session before, it has 253
sessions of history, it is its company's one eligible share class this month, and the House may trade it. A slot of
last week may be missing today, and a new one may appear.

**The numbers carry a little noise, on purpose.** Each price is moved by up to half a cent before any ratio is
formed, and each volume by up to half a percent, so that no arithmetic on the fields gives a price or a share count
back. A return of a $10 name carries about 4 basis points of noise (10 at the very most), of a $100 name a tenth of
that; a session's `range` whose high and low were a cent apart can read slightly negative. One bar reads the same in every ctx of a run. Fills,
your P&L and every statistic you are judged on use the true prices.

## What decide returns

```python
{"target": {slot_id: weight, ...}, "at": "open"}    # the portfolio you want; "at" defaults to "open"
{"target": {}, "at": "close"}                        # all cash, sold at the next close
{"hold": True}                                       # or None: change nothing
```

A target is valid when every key is in `ctx.ids`; every weight is finite and at most 0.20; the weights sum to at most
1; and it names no slot (all cash) or 5 to `max_names` slots. A weight of exactly 0 means the slot's absence. An
invalid target is dropped whole and counted as an error (your lots stay; it never counts as a failed decide). **A lot
whose slot has left `ctx.ids` is being sold by the House at the next open: leave it out of your target.**

**The KEEP rule turns a target into orders:**
- a slot you hold that is absent from the target is sold, whole, at the next fill point;
- a slot you do not hold is bought as ONE lot of `weight x ctx.budget` dollars (under $10: skipped, and said);
- a slot you hold that is in the target is KEPT: no trade, no resize, whatever its weight;
- at most 12 buys and 12 sells a decision: a target that needs more is refused whole (the reject says "order cap")
  and the decision is a hold. A rule that wants more staggers itself.

A buy that could not be made (no bar at the fill, a sale that filled late, a budget cut) is tried again at each
following close until your next decision replaces the target; nothing is ever sold for that reason.

`"at": "open"` fills at the next session's official open x (1 + half-spread) for a buy, x (1 - half-spread) for a
sell; `"at": "close"` at the next session's official close the same way. The half-spread is the name's own, never
under 3 basis points. A session executes open exits, open entries, close exits, close entries, in that order. Sells
pay the SEC and FINRA TAF fees (each rounded up to the cent); there is no commission. A buy needs a bar at its fill
session and a close the session after.

## The House's exit rules (the same in the Gym)

- A lot is never sold in the session it was bought (a lot bought at the close may sell at the next open).
- A lot is held at most `max_hold_sessions`: it exits at the open that would complete them (reason "max_hold").
- A name that is not eligible at ANY session's close, whether or not you are asked that day, is sold at the next open
  (reason "house", tag "ineligible"): it left the index, it did not trade, or it may not be traded.
- A name whose bars end is closed at its last close less 30% (reason "vanished"), your lot and every name it is
  compared with alike.
- Two decisions of yours in a row that failed (an exception, a timeout, a disqualified program) exit all your lots at
  the next open (reason "house").

## What the review refuses on sight

Any use of `ctx.ids` beyond naming targets (an id says nothing about a stock, and nothing outside its run); any
constant that could name a calendar period; any search for a price level or a share count in the fields; any embedded
table of returns. The calendar counts and the market's own path are there to trade on, not to date a session with.
