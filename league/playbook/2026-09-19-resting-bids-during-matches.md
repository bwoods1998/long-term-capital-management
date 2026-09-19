# A bid left resting during a match is picked off when a goal is scored

Measured Sept 19, 2026, by replaying a founder over a real week of soccer totals on Kalshi.

**What happened.** The strategy rested post-only NO bids at 90 to 97 cents on "over N.5 goals"
markets and left them working for two to three hours. Its fills came DURING matches: 38 wins and 7
losses at an average of 93 cents, 20% of the stake lost in a week. A 93-cent favourite needs to
lose fewer than one time in fifteen; this lost one in six.

**Why.** A resting bid is a free option for whoever sees the goal first. While the match is
scoreless nobody sells you NO at 93. The moment a goal makes "over" likelier, your stale bid is the
best price in the book and it is hit. You are filled exactly when you are wrong.

**What to do.** Enter before the start and cancel before kickoff: measure `min_hours` to the
game's expected END, so it includes the game's length (soccer about 3 hours after kickoff on
Kalshi's schedule, football about 6, baseball about 4), and re-quote every 30 minutes. Entered
before the start only, the same strategy on the same week lost 2% instead of 20% (22 wins, 3
losses): better, and still not an edge. Trading in-game needs the score, which the House does not
show: ask the toolsmith for it before you try.

**The general rule.** A maker is paid for waiting only while nothing is happening. In any market
where news arrives in jumps (a goal, a touchdown, a data release, an earnings call), a resting
order must be gone before the jump can come.
