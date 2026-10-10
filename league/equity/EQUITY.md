# Writing an equity program

> Owner: core (league/equity/INTERFACES.md). This is the skeleton's draft of the contract; core finalizes it with the
> engine, and every statement here is held by a test before E1 merges.

An equity program is one Python file: `NEEDS`, `PARAMS` and `decide(ctx)`. It trades long-only ETFs (and, in a later
release, stocks) with whole and fractional shares. The House runs it once a session, after the close; whatever it
asks for executes in the NEXT session, at the open or at the close. The Gym replays the same file over daily bars, and
a program sees byte-identical inputs in the Gym and on the House for the same decision day. It never sees a date or a
year.

## The file

```python
import math
import numpy as np            # math and numpy only; nothing else imports

NEEDS = {"symbols": ["SPY"], "history": 252, "max_hold_sessions": 20}
PARAMS = {"theta": 0.02, "h": 8}
STATE = {}                     # module globals persist between calls: your memory for the run

def decide(ctx):
    return [...]               # a list of intents (or [] / None)
```

The code rules are the options contract's, unchanged (`league/gym/safety.py`, `league/gym/PROGRAM.md` "Rules"):
imports `math` and `numpy` only; no `print`, `repr`, `open`, `eval`, `exec`, classes, decorators, generators, `id`,
`hash` or `type`; no attribute starting with `_`; no attribute assignment; no numpy file, memory, random or date
functions; no bare `except:`; **no year or date literal**. A decide call has 1 second; 25 errors or timeouts disqualify
the run. Be deterministic.

## NEEDS

| key | meaning | default |
|---|---|---|
| `symbols` | the symbols you trade and read, 1 to 20, from the lane's universe (SPY QQQ IWM DIA, the eleven SPDR sector ETFs, TLT, GLD; stocks in a later release) | required |
| `history` | prior sessions of daily bars in `ctx.bars` (0-504) | `252` |
| `max_hold_sessions` | the House exits any lot of yours held this many sessions, at the next open (1-60) | `20` |

## PARAMS

As the options contract: a dict of numbers, booleans, strings or short lists, bound at its declaration; each distinct
(code, PARAMS) is a separate trial. Read them as `ctx.params`.

## ctx (at the close of session t)

| field | what |
|---|---|
| `ctx.symbols` | your NEEDS symbols |
| `ctx.bars[sym]` | `open`, `high`, `low`, `close`, `volume`, `ret` arrays, oldest first, the last element session t; prices adjusted for splits and dividends AS OF t (never by a later event); volume in shares; NaN where there was no bar |
| `ctx.prices[sym]` | session t's close |
| `ctx.weekday` | 0 Monday .. 4 Friday |
| `ctx.events`, `ctx.events_next` | booleans for t and the next session: fomc, cpi, jobs, monthly_opex, quarter_end, half_day |
| `ctx.session_of_month`, `ctx.sessions_to_month_end` | 1 on the month's first session; 0 on its last |
| `ctx.positions` | your open lots: `{id, symbol, class, qty, entry, mark, value, pnl, held_sessions, at, tag}`; `at` says how the lot was filled ("open" or "close") |
| `ctx.orders` | your pending orders (usually none: everything you ask executes the next session) |
| `ctx.closed` | lots closed since your last call: `{id, symbol, qty, entry, exit, net, held_sessions, reason, tag}` |
| `ctx.rejects` | why your last intents were refused |
| `ctx.cash`, `ctx.equity`, `ctx.budget` | your sleeve's free cash, its equity, and the equity you size against (dollars) |
| `ctx.caps[sym]` | dollars you may still add to `sym` now |
| `ctx.params` | your PARAMS |

## Intents

At most 20 a call; each has exactly one of `buy`, `sell`, `cancel`:

```python
{"buy": "SPY", "share": 0.5, "at": "close", "tag": "overnight"}   # half of the sleeve's equity, at the next close
{"buy": "QQQ", "usd": 250.0}                                       # dollars; "at" defaults to "open"
{"sell": 17, "at": "open"}                                         # a whole lot, by its id
{"cancel": 3}                                                      # a pending order
```

`"at": "open"` fills at the next session's official open x (1 + half-spread) for a buy, x (1 - half-spread) for a sell;
`"at": "close"` at the next session's official close the same way. A session executes open exits, open entries, close
exits, close entries, in that order. A lot is never sold in the session it was bought (a lot bought at the close may
sell at the next open). Sells pay the SEC and TAF fees; there is no commission. An entry is sized by the House
(`league/equity/sizing.py`): your share of the sleeve, capped by the instrument's cap, the sleeve's cash, the House's
cash and the shared loss budget; under $10 it is skipped and said so in `ctx.rejects`.

## The House's exit rules (the same in the Gym)

A lot held `max_hold_sessions` sessions exits at the next open. Two sessions of failed decides in a row exit all your
lots at the next open. A program demoted or retired has its lots exit at the next open.
