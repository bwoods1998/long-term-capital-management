# What the first night of replays taught (Sept 19, 2026)

Written by the builder on the night the league was built, through the teacher's path, to prove
that path end to end. Everything here was measured that night.

**Crypto reversion and dip-buying lose after fees on a three-week hourly tape.** `crypto-reversion`
closed 33 trades for -2.7% (Sharpe -0.04, deflated 0.16); `crypto-dip-limit` closed 79 for -2.9%.
A taker round trip on Alpaca crypto costs 0.5% and a maker's 0.3%: a signal whose average move is
under one percent gives most of it to the venue. Before replaying a variant, work out its average
gross move per trade from your own record. If it is under twice the round-trip fee, change the
idea, not the parameters.

**Kalshi favourites were the only seeds with positive replays, and they still did not pass.**
`favorites-maker`: +8.1% over 36 trades, Sharpe 0.24, deflated 0.85 against the 0.90 line. The
record is too short, not too weak: one quiet day of hourly markets is only about 17 active blocks.
A replay that fails for lack of blocks is still a counted trial that raises the bar for the whole
family, so do not re-run the same code hoping for a longer tape. Wait for the House's multi-day
Kalshi tapes, or let the forward test on the shadow book do the work: it costs no trials.

**A record that wins every trade is held back on purpose.** The loss-rate gate assumes one loss of
everything at risk that you have not seen yet. Clean wins of +0.5% while risking 7% of the stake
need 46 in a row before the bound turns positive. Small positions against the stake get there
sooner than large ones: size is part of the evidence.

**Daily-bar equity strategies cannot be replayed yet.** A day's bar is stamped at its close, when the
market is shut, so the simulator never sees a moment when an equity order is allowed. Those seeds
are judged forward only, and their children cannot qualify until the tape steps inside the session.
