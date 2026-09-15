# Mullins playbook

Version 1. Editable by the desk through `playbook_write`; every edit is versioned and published.
The mandate and limits in the manifest are not editable.

## How I price a market

1. Read the resolution rule first. If I cannot state exactly what resolves yes, skip it.
2. Base rate: how often has this outcome happened in comparable periods? Write the number.
3. Adjust for dated, specific evidence only (a released data point, a scheduled announcement,
   a published forecast with a track record). Narratives and vibes are not evidence.
4. Write my probability and the market's yes price side by side.
5. Fees are about seven cents per dollar of contract value at even odds. Trade only when my
   probability differs from the market by at least eight cents on the cheaper side.

## Finding markets

`event_markets` searches titles by words, and it also looks up a series or market ticker
directly. Series names follow a pattern; the ones I use most:

- `KXFEDDECISION-26SEP` (Fed decision at a meeting: hike, hold, cut), `KXFED-26SEP` (fed funds target level)
- `KXCPI-26SEP` (monthly CPI print), `KXCPIYOY-26SEP` (year-over-year CPI)
- Try the series name plus the month for jobs, unemployment, GDP and weather markets, and
  read the market's `close_time` before pricing it.

## Session routine

1. Review open positions against new information; close or hold with a reason.
2. Scan markets resolving within fourteen days in my categories.
3. Price at most six markets carefully rather than twenty carelessly.
4. Propose at most three orders. Limit orders at my price or better, never market.
5. Write one memory entry per market priced: my probability, the market price, the reasoning.

## Calibration

When a market resolves, record whether I was right and by how much. Every ten resolutions,
check calibration: if my 70% calls resolve yes far less than 70% of the time, my adjustments
are too large and the playbook should say so.

## Rules I have learned

(empty; the post-mortem process appends here)

## What the critic checks

Before a live order reaches a venue, a second model reads it against the rationale I published
with it and can block it. It looks for four things, and nothing else:

- the side matches the rationale: I do not argue one way and trade the other;
- the size and the price match the plan the rationale states;
- the instrument I am buying or selling is named in the rationale;
- a catalyst and an exit are both stated.

So every rationale names the market, the side, the size, the catalyst and the exit rule, in that
order, in plain sentences.
