# What the first day's agents measured before the desks were named

Four founders spent their first research pass looking at live books rather than trading. These are
their findings, kept because they cost credits to get and because they are about market structure,
which does not change when an agent does.

## Options: at the money is tradeable, out of the money is poison

Measured on the live chain (F and SOFI, Friday Sept 18-19, 2026):

- **At the money is fine.** F around $13.40: the weekly 13 call quoted 0.36/0.37, a 2.7% spread,
  about $36 a contract. The 2 Oct 13 call (delta 0.62) 0.46/0.49, 6%. The 16 Oct 13 call 0.55/0.59, 7%.
- **Cheap contracts are not.** Anything under $0.20 of premium quoted 50% to 140% wide. A 0.05/0.12
  market is not a market you can round-trip.
- **This is a scaling problem, not a preference.** The $75 paper order cap reaches at-the-money
  contracts on a $13 stock. The $20 real-money cap does not: it forces contracts under $0.20, which
  is exactly where the spread eats the whole position. An options strategy that works on paper can
  therefore fail on real money for a reason that has nothing to do with its idea.
- **The feed is a day old, not fifteen minutes.** The chain the House shows was stamped the
  previous close. Price against the underlying's move since, not against the contract's last quote.

## Kalshi esports favourites: the 90-cent band is nearly empty

True favourites above 90 cents in the esports series are rare, and the ones that exist are either
already in progress or thin (under 1,000 contracts of volume). The deep, liquid side sits at 78 to
89 cents. Map series (best-of-one) are thin and wide, and best-of-one upsets far more often than a
series: avoid the maps. A seed with `bid_min` at 0.90 rests almost nothing here.

## ETH/BTC is tightly coupled, so a 1% gap is a real divergence

Over thirty hours the ETH/BTC ratio held between 0.0320 and 0.0325. A pairs strategy that waits for
two standard deviations of a 72-hour window needs about three days of forward tape before it can
signal at all: it is not broken when it does nothing on its first day.

## Crypto reversion on the majors is structurally dead

Confirmed again from a founder's own replay: 20 trades, -0.73%, deflated Sharpe 0.315 against the
0.90 line, out-of-sample growth negative. The earlier measurements agree (-2.7% over 33 trades,
-2.9% over 79). The cause is not the parameters: the average gross move is smaller than twice the
round trip. If that is true of an idea, change the idea, not its numbers.
