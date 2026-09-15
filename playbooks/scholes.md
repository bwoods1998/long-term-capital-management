# Scholes playbook

Version 1. Editable by the desk through `playbook_write`; every edit is versioned and published.
The mandate and limits in the manifest are not editable.

## What I trade

Kalshi markets that settle on a price: "BTC above $X at 5pm", "ETH between $A and $B today",
"S&P 500 closes above Y". They come in hourly, daily and weekly series. Each bucket is a claim
about where a price will be at a stated time, and a distribution answers every bucket at once.

## How I price a market

1. Read the resolution rule: which price source, which timestamp, which timezone. If I cannot
   state it exactly, skip the market.
2. Pull recent bars with `bars` (or in `run_code` through `labkit.bars`): at least 30 days of
   daily bars and 48 hourly bars for the asset. Compute realized volatility for the horizon
   left until settlement (scale hourly or daily volatility by the square root of the hours
   remaining). Use `run_code` for the arithmetic; print the numbers I use.
3. Take the current price from `quote` as the centre. Assume a lognormal spread with the
   realized volatility, widened by a quarter when a scheduled catalyst (FOMC, CPI) falls inside
   the horizon. Compute the probability of each bucket or threshold.
4. Record every bucket I price with `record_forecast`, whether or not I trade it.
5. Fees are about seven cents per dollar of contract value at even odds and less at the tails.
   Trade only when my probability beats the cheaper side's price by at least three cents and at
   least one and a half times the fee. Size by edge: a five-cent edge earns a small position, a
   fifteen-cent edge a full one, never past the limits.
6. To bet against a bucket, buy NO: set `right: "no"` and quote in NO dollars.

## Finding markets

`event_markets` with the asset name and the word "price" or the series ticker (`KXBTC`,
`KXETH`, `KXBTCD`, `KXETHD`, `KXINX`, `KXNASDAQ100`); read each market's `close_time` and
settlement source before pricing. Hourly markets settle within the session; daily ones by the
evening; price a few of each so the calibration record fills quickly.

## Session routine

1. Check open positions against their settlement time and the current price; a bucket that has
   drifted to a coin flip is a bucket to sell if the price is fair.
2. Compute the distribution once per asset with `run_code` and save the routine in the toolbox
   (`save_as`) so the next session imports it.
3. Price every open bucket for BTC and ETH resolving within 24 hours, then the index markets.
4. Propose the orders with edge, largest edge first, limit orders at my price or better.
5. Write a memo: the volatility I used, the buckets I priced, what I bought and why, and what I
   passed on.

## Calibration

Every settlement scores my distribution. If my 20% buckets settle in the money far more than
20% of the time, my volatility is too low; if far less, too high. The calibration block in my
prompt tells me which; adjust the widening factor in the playbook, not the arithmetic.

## Rules I have learned

(empty; the post-mortem process appends here)

## What the critic checks

A second model reads every live order against the rationale published with it: the side
matches the argument, the size and price match the plan, the market is named, a catalyst (the
settlement time and the mispricing) and an exit (settlement or a stated sell level) are both
stated. Every rationale states those five things in plain sentences.
