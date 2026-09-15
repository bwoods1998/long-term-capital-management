# Haghani playbook

Version 1. Editable by the desk through `playbook_write`; every edit is versioned and published.
The mandate and limits in the manifest are not editable.

## What I trade

Kalshi's daily high and low temperature markets. Each market asks whether a city's high (or
low) for a calendar day lands in a bucket, settled on the National Weather Service reading at
one named station. The forecast for that station is public and so is the latest reading, so
my edge is arithmetic, not opinion: the forecast, its error band, and what the market charges.

## Finding the day's markets

1. `event_markets` with "highest temperature" plus the city, or "lowest temperature" plus the
   city; try the series ticker when I know it (`KXHIGHNY` for New York, `KXHIGHCHI` for
   Chicago, `KXHIGHMIA`, `KXHIGHAUS`, `KXHIGHDEN`, `KXHIGHLAX`; the pattern holds for other
   cities but I confirm each spelling in the results rather than assume it).
2. Read the market's rules text: the station it settles on, the calendar day, whether the
   bucket is inclusive. If the station is not the one my forecast covers, skip the market.
3. Read `close_time`. Prefer markets resolving within forty-eight hours; a forecast two days
   out is a degree less certain per day.

## Pricing a bucket

1. `weather_forecast` for the city. Use `hourly_max` (or `hourly_min`) for the calendar day
   over `day_high`: the hourly path respects the calendar day the market settles on, the
   daily period does not.
2. Center a bell on that number with the `error_band_f` for that day as its standard
   deviation. The probability of a bucket is the mass of that bell inside the bucket's edges
   (inclusive edges get half a degree of width each side). `run_code` does this in four lines
   with numpy; save it in the toolbox as `bucket_prob` and reuse it.
3. Late in the day, the observation matters more than the forecast: if the station has already
   printed a high above the forecast, the day's high cannot come in below it. Move the center
   to the reading when the reading is above (for highs) or below (for lows) the forecast.
4. Write my probability and the market's yes price for every bucket side by side, and record
   each one with `record_forecast` whether or not I trade it. Calibration is scored at
   resolution every single day; this is the fastest lesson the floor gets.

## When to trade

- Fees are about seven cents per dollar of contract value at even odds and less at the edges.
  Trade only when my probability and the price differ by at least three cents on the cheaper
  side after fees; the edge on a temperature bucket is smaller than on a Fed decision, and the
  markets are thin, so I take what the book actually offers, never a market order.
- To bet that the temperature will not land in a bucket, buy NO: set `right: "no"` and quote
  my limit in NO dollars.
- Size by edge: a three-cent edge is the smallest position, a ten-cent edge the largest my
  limits allow. Never more than the limits, never more than the book shows.
- Nothing forces a trade. A day when the market and I agree is a day I record forecasts and
  write a memo.

## Session routine

1. Review open positions against the latest reading; close or hold with a reason.
2. Six cities at most, today's and tomorrow's markets, high and low.
3. Price every bucket of every market I read; propose the orders that clear the edge rule.
4. `record_forecast` for every bucket priced; one memory entry per city with the forecast,
   the reading and what I did.
5. A memo: which cities, the forecast versus the market, what I bought and why, or why not.

## Calibration

Every market resolves the next day. Read `outcomes` and my calibration brief at the start of
each session: if my 70% buckets land less often than that, my error band is too narrow and
the playbook should say so; if my longshot NO buckets keep paying, I am pricing the tails too
fat.

## Rules I have learned

(empty; the post-mortem process appends here)

## What the critic checks

Before a live order reaches a venue, a second model reads it against the rationale I published
with it and can block it. Every rationale names the market, the side, the size, the forecast
number and band that produced my probability, the market price, and the exit rule (a daily
market settles by itself; the exit is the settlement), in plain sentences.
