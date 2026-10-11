# Writing an equity program

> Owner: core (league/equity/INTERFACES.md). The contract between an equity program and the House. The Gym engine
> (`league/equity/engine.py`) and the House's equity book (`league/equity/live.py`) both follow it; every statement
> here is held by a test in `league/tests/test_equity_*.py`.

An equity program is one Python file: `NEEDS`, `PARAMS` and `decide(ctx)`. It trades long-only ETFs (and, in a later
release, stocks) with whole and fractional shares. The House runs it once a session, after the close; whatever it
asks for executes in the NEXT session, at the open or at the close. The Gym replays the same file over daily bars, and
a program sees byte-identical inputs in the Gym and on the House when both read the same bars for the same decision
day (three things can make the bars themselves differ: see "Where the Gym and the House may read differently"). It
never sees a date or a year.

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

What you have: Python's plain builtins (`len`, `range`, `sum`, `min`, `max`, `abs`, `round`, `sorted`, `enumerate`,
`zip`, `float`, `int`, `str`, `list`, `dict`, `set`, `tuple`, `isinstance`, the common exceptions), `math`, and numpy
as the House has it, all but its file, memory, random and date functions (`np.mean`, `np.std`, `np.nanmean`,
`np.isfinite`, `np.diff`, `np.log`, `np.argsort` and the rest). There is no pandas.

## NEEDS

| key | meaning | default |
|---|---|---|
| `symbols` | the symbols you trade and read, 1 to 20 (duplicates count once), from the lane's universe (SPY QQQ IWM DIA, the eleven SPDR sector ETFs, TLT, GLD; stocks in a later release) | required |
| `history` | prior sessions of daily bars in `ctx.bars` (0-504) | `252` |
| `max_hold_sessions` | the most sessions the House lets a lot of yours be held: it exits the lot at the open that would complete them (1-60) | `20` |

No other key is allowed. A malformed NEEDS refuses the program.

## PARAMS

As the options contract: a dict of numbers, booleans, strings or short lists, bound at its declaration; each distinct
(code, PARAMS) is a separate trial. Read them as `ctx.params`.

## ctx (at the close of session t)

| field | what |
|---|---|
| `ctx.symbols` | a tuple: your NEEDS symbols, in your order |
| `ctx.bars[sym]` | ONE OBJECT a symbol (`ctx.bars` is a dict by symbol) whose six arrays are read BY ATTRIBUTE: `ctx.bars[sym].open`, `.high`, `.low`, `.close`, `.volume`, `.ret` (never `ctx.bars[sym]["close"]`, never rows: "Reading ctx" below). Each is a read-only float64 numpy array, oldest first, the last element session t, at most `history` + 1 long and shorter while fewer sessions lie before t (a run that begins at the store's first session starts with ONE element); prices adjusted for splits and dividends AS OF t (never by a later event) and rounded to 4 decimals; volume in shares as traded; `ret` the close-to-close return (NaN first); NaN where there was no bar |
| `ctx.prices[sym]` | a float: session t's close (NaN if `sym` had no bar at t); `ctx.prices` is a dict by symbol |
| `ctx.weekday` | 0 Monday .. 4 Friday |
| `ctx.events`, `ctx.events_next` | dicts of booleans read by key (`ctx.events["fomc"]`), for t and the next session: fomc, cpi, jobs, monthly_opex, quarter_end, half_day. **fomc, cpi and jobs come from tables with a first and a last row (below): outside them the flag is False and says nothing** |
| `ctx.session_of_month`, `ctx.sessions_to_month_end` | 1 on the month's first session; 0 on its last |
| `ctx.positions` | your open lots: a LIST of DICTS (`lot["id"]`, never `lot.id`; the list is not keyed by symbol), each `{id, symbol, class, qty, entry, mark, value, pnl, held_sessions, at, tag}`; `entry` the fill a share (split-adjusted), `mark` t's close, `pnl` (mark - entry) x qty (dividends not included: they are cash), `held_sessions` the sessions since the lot's entry session (0 at the entry session's own close), `at` how the lot was filled ("open" or "close"); `mark`, `value` and `pnl` are None while the symbol has no price |
| `ctx.orders` | your pending orders, a list: always empty today (everything you ask executes, or is refused, in the next session) |
| `ctx.closed` | lots closed since your last call: a list of dicts, each `{id, symbol, qty, entry, exit, net, held_sessions, reason, tag}`; `net` dollars after fees with dividends; `reason` "program", "max_hold" or "house" |
| `ctx.rejects` | a list of strings: why your intents of the last call were refused, and any exit of yours that waits |
| `ctx.cash`, `ctx.equity` | your sleeve's free cash, and its equity (cash + lots at t's close) |
| `ctx.budget` | the sleeve equity your entries are sized on (the Gym: the run's capital E0, $1,000) |
| `ctx.caps[sym]` | a float: dollars you may still add to `sym` now: the instrument cap (50% of the sizing equity an ETF, 20% a stock) less your holding of `sym`, at most your cash; `ctx.caps` is a dict by symbol |
| `ctx.params` | your PARAMS (a copy: changing it changes nothing) |

## Intents

At most 20 a call (the rest are dropped and counted as an error); each has exactly one of `buy`, `sell`, `cancel`:

```python
{"buy": "SPY", "share": 0.5, "at": "close", "tag": "overnight"}   # half of the sleeve's equity, at the next close
{"buy": "QQQ", "usd": 250.0}                                       # dollars; "at" defaults to "open"
{"sell": 17, "at": "open"}                                         # a whole lot, by its id
{"cancel": 3}                                                      # a pending order (none exist today)
```

A buy has exactly one of `share` (0 < share <= 1) and `usd` (> 0). `tag` is any short text (64 characters kept). A
malformed intent is dropped and counted as an error (it never counts as a failed decide).

`"at": "open"` fills at the next session's official open x (1 + half-spread) for a buy, x (1 - half-spread) for a sell;
`"at": "close"` at the next session's official close the same way. Half-spreads: 1 bp SPY QQQ IWM DIA, 3 bp the other
ETFs and stocks, 5 bp TLT and GLD. A session executes open exits, open entries, close exits, close entries, in that
order. Sells pay the SEC and FINRA TAF fees (each rounded up to the cent); there is no commission.

An entry is sized by the House (`league/equity/sizing.py`, the same function in the Gym and live): your share of the
sleeve, capped by the instrument's cap, the same share of your sleeve, your sleeve's cash, the House's cash and (live)
the shared loss budget; shares are floored to 6 decimals; under $10 it is skipped. Whatever is refused is said in the
next `ctx.rejects`: a buy of a symbol outside your NEEDS, a sell of a lot that is not open, a sell of a lot bought in
the same session, a cancel, an entry sized to nothing, a session without an official price.

## Reading ctx: a worked example

A whole program that reads a rolling window the way ctx gives it. It loads and trades as written (a test runs this
block on the engine):

```python
import numpy as np

NEEDS = {"symbols": ["SPY", "QQQ"], "history": 60, "max_hold_sessions": 20}
PARAMS = {"window": 20, "share": 0.25}


def decide(ctx):
    n = int(ctx.params["window"])
    intents = []
    for sym in ctx.symbols:
        close = ctx.bars[sym].close                      # ONE object a symbol: its arrays by attribute
        lots = [lot for lot in ctx.positions if lot["symbol"] == sym]      # a lot is a dict in a list
        if len(close) <= n or not np.all(np.isfinite(close[-n - 1:])):
            continue                                     # a short or broken window: wait, never index past it
        above = close[-1] > float(np.mean(close[-n:]))   # a price against its own average: scale-free
        if above and not lots:
            intents.append({"buy": sym, "share": ctx.params["share"], "at": "open"})
        elif not above:
            intents += [{"sell": lot["id"], "at": "open"} for lot in lots]  # a lot is sold by its id
    return intents
```

Common faults. Each fails in `decide`, and 25 errors disqualify the run; the swarm refuses the ones it can see in the
source before a program is run (league/swarm/elane_review.py, the reading rule):

- **`ctx.bars[sym]["close"]` raises TypeError.** A symbol's bars are one object: write `ctx.bars[sym].close`.
- **Bars are arrays, not rows.** There is no `for bar in ctx.bars[sym]`, no `len(ctx.bars[sym])`, no
  `ctx.bars[sym][-1]`: take `close = ctx.bars[sym].close`, then `close[-1]`, `close[-20:]`, `len(close)`. An array has
  no `.iloc`, `.rolling` or `.pct_change`, and it is read-only (copy it before you change it).
- **A window can be short, and it can hold NaN.** A run's first sessions have little or no history behind them, so
  `close[-20]` raises IndexError there and `close[-20:]` is silently shorter: check `len(close)` first. `ret[0]` is
  NaN and every array is NaN where the symbol had no bar; a comparison with NaN is False, so check `np.isfinite(...)`
  or use `np.nanmean`.
- **A lot is a dict in a list.** `lot["id"]`, `lot["symbol"]`, `lot["held_sessions"]`, never `lot.id`; and
  `ctx.positions["SPY"]` raises: find a symbol's lots with a loop.
- **A lot is sold by its id.** `{"sell": lot["id"]}`; `{"sell": "SPY"}` is dropped and counted as an error.
- **An intent has exactly one of `buy`, `sell`, `cancel`, and `"at"` is `"open"` or `"close"`.**
  `{"symbol": "SPY", "side": "buy"}` and `"at": "market"` are dropped and counted as errors. No order is `[]` (or
  `None`), never `{}`: a dict is read as one intent.
- **ctx has the fields of the table above and no other, never a date.** `ctx.events` is a dict
  (`ctx.events["fomc"]`); `ctx.prices[sym]` and `ctx.caps[sym]` are floats.

## The House's exit rules (the same in the Gym)

- A lot is never sold in the session it was bought (a lot bought at the close may sell at the next open).
- A lot is held at most `max_hold_sessions`: at a decision close where its `held_sessions` + 1 reaches it, the lot
  exits at the next open (reason "max_hold"). A lot bought at a close with a maximum of 1 is sold at the next open.
- Two sessions of failed decides in a row (an exception, a timeout, a disqualified program) exit all your lots at the
  next open (reason "house").
- A program demoted or retired has its lots exit at the next open (live).

An exit you asked for in the same phase goes first (its reason is "program"). An exit without an official price
waits for the next session.

## Dividends and splits

You see prices as of t only. Your lots hold shares as traded: on an ex-dividend day the dividend is credited to your
cash for every lot you held at the previous close (`ctx.closed[...]["net"]` includes it); on a split day the lot's
shares and entry price are scaled by the split. In the Gym both are read from the vendor's two series (the step of
the adjusted-to-raw price ratio); live, from the venue's activities. The vendor rounds its adjusted prices to the cent,
so in the Gym a step of that ratio within the rounding of its two adjusted closes is no event, a dividend is credited
to within about a cent a share, and a dividend smaller than that rounding is not credited.

## Where the Gym and the House may read differently

The two builders are one function, so the same bars give the same bytes. The bars are the vendor's, and three things
about them differ between a live decision at t and the same session replayed later:

- **The adjusted prices are rounded to the cent.** `ctx.bars` holds prices as of t, built from the vendor's adjusted
  series. After a later dividend or split the vendor restates that whole series and rounds each price to the cent
  again, so the history of session t read from a later store differs from what you saw live by up to about a cent and
  a half over each of the prices involved (a few hundredths of a percent of a $100 price, more of a cheaper one).
  Session t's own close is the same in both. A condition that sits within that distance of its threshold can decide
  differently live and in replay; leave a margin, or expect the rare session where the two disagree.
- **The last volume.** Live, `volume[-1]` is the vendor's figure as read at 16:20 ET; the session's volume goes on
  counting late and after-hours prints, and the replay reads the final figure. A program that reads the last volume
  may decide differently live and in replay.
- **The event tables have a first and a last row** (`league/gym/events.py`): fomc 2017-02-01 through 2026-12-09, cpi
  2017-01-18 through 2026-09-11, jobs 2017-01-06 through 2026-09-04. Outside a table's rows its flag is False on every
  session, in the Gym and live alike: every session of 2016, and live every session after the table's last row. False
  there says nothing about the day. Do not condition on these three flags until the tables are extended;
  `monthly_opex`, `quarter_end` and `half_day` come from the calendar and hold everywhere.
