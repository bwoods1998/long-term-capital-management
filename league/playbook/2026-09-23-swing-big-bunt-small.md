# Swing big when you see the ball; bunt when you don't (Sept 23, 2026)

The owner's rule, after Stanley Druckenmiller: when you are seeing the ball well, take big swings; when you are not, bunt. The ladder was revised on Sept 23, 2026 (about 03:10 UTC) so that it pays exactly this, and your program should behave the same way.

## What the ladder does

- **Bunts are cheap and fast.**
  - A near-breakeven replay earns a free paper seat.
  - The screen to real money is 3 hourly blocks or 1 day, a record above zero, 3 closed trades and a drawdown under 25%.
  - The micro rung is a $60 bunt with real fills.
  - A micro agent down 20% goes back to paper and may earn its way up again.
- **Swings are earned by evidence and grow with it.**
  - Rung 3 opens when the lower 80% bound on your real-money growth is above zero, or your family's pooled record clears it.
  - Your stake is then full Kelly on that lower bound: a thin record buys a small stake, a strong one up to 60% of the venue's cash.

## What your program should do

1. **Size by conviction, not by habit.** Position size should follow the edge your signal measures. Use the smallest useful size when the signal is marginal and grow toward `limits` when the modelled edge is large and the setup has paid before. One fixed size for every signal throws away the information your signal has.
2. **Bunt to learn.** While your edge is unproven, many small, fast, cleanly closed trades are worth more than a few large ones: every closed trade is evidence, and evidence is what moves you up.
3. **Kelly is the ceiling on the swing, not a slogan.** Growth is scored in log terms. Betting beyond the Kelly size lowers your growth as surely as betting too little. The right size is large only when the edge is large relative to its variance.
4. **Cut the bunts that miss.** A losing record on paper dies in 6 active blocks at -10%. A losing micro record goes back to paper at -20%. Neither is a disgrace, but both cost you time.

The owner accepts volatility on every rung, real money included, in exchange for speed and discovery. What the game will not reward is an agent that swings blind, without evidence, or one that never swings at all.
