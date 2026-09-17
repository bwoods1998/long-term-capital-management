# The exponential arena: pooled evidence, deep replays, every venue working

*Written September 17, 2026, 22:00 UTC, at the owner's direction: "set up the most ambitious possible
architectural design to allow these swarm of trading agents to recursively self improve and achieve
exponential profit as quickly as possible, making full use of Sail, Coinbase and Kalshi." Cost is not a
constraint; the owner tops up Sail and the venues.*

## What was true at 21:30 UTC

- Venue equity $908 against the $976 opening mark. Lifetime live trading P&L -$107; Sail spend $140.
- The only earning strategy was Kalshi favorites on three live Mullins desks: 36 settled, 35 wins,
  about +$10. Each live desk was sized on its **own** settlements, so a 1:13 payoff needed 43-300 of
  them per desk before its size could move off $10 a bet, while eight shadow variants of the same
  code settled the same bets and none of it counted.
- The Foundry had run 97 cycles and qualified nothing: a five-day replay gives a favorites candidate
  2-8 positions against the 60 the gate asks for.
- Coinbase held $486 in cash with every entry strategy paused (0.5% maker fees eat a 1% spread on
  BTC and ETH). Kalshi held $240 of cash idle.
- Sail balance $138 at $115 a day, throttle off since the morning: the floor stops at the $10 reserve.

## The design

The constraint is **evidence per hour**, not architecture. A recursive loop improves as fast as it
can tell a good change from luck. Every swing below multiplies settled, attributable evidence or
puts idle capital where the evidence already points.

### 1. Pooled evidence (`Strategies.family_record`)

One record per strategy per family: fills and settled outcomes of the same code on every desk the
family has ever held, summarized like a desk's own record, with `real_settled`, `desks`, and the
record split by **market group** (crypto, commodities, weather, sports, mentions, economics,
politics, or the series). `size_cap` on a live desk ramps on the pooled record once
`pooled_min_real` (5) of its settlements were real money; the family's evidence lifts a live desk
born yesterday. Every strategy run receives the pooled verdicts in `kit.context["evidence"]`, and
`kalshi_favorites` version 3 skips a group whose record has reached the gate's count and is net
negative, and places passing groups first. The shadow desks become the evidence engine of the
live desks; the code learns where the edge lives without a model call.

### 2. Deep replays

The Kalshi family replays ten days and sees 8,000 markets a window (`family_window_days`,
`family_max_markets`); the sandboxes' history cache keeps the cost to the first cycle. Sixteen
research sandboxes, 36 parameter and 10 code candidates a cycle, five-minute cycles, $300 a day.

### 3. Sail at full stretch

Twelve target variants a family (sixteen at most), three seeds an hour, 24 lab experiments a day,
the Firm Mind every half hour, 24 parallel strategy runs, learning size $20 on Kalshi. Runway is
advisory only; the owner funds Sail.

### 4. Coinbase working: `wide_quotes`

Maker quoting where the book is wide enough to pay the account's real fees: scan the venue's USD
products, quote only where the live spread clears the fee-adjusted round trip by a margin, one
tick inside the touch, at learning size, exits always quoted. Live on Hilibrand and Hilibrand III
at $25 a bet, sized up only by the evidence gate. Cash-and-carry basis on Coinbase futures waits
for the owner to enable derivatives.

## What this does not claim

None of this is alpha. It is the machinery to prove or kill an edge in hours instead of days and to
put capital on what survives. The account is $908; exponential is a slope, not a promise.
