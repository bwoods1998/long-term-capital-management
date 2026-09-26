# Event capital and faster execution feedback — September 21, 2026

The first funded live agent exposed a mismatch in the learning loop. Huang VI had a $25
Kalshi stake and saw $10 order/position limits. Its 15:04:11 UTC XRP intent had about $9 of
principal. The House refused it before submission: 30% of its own stake was $7.50; the
25% shared settlement cohort cap was $6.25. A third, tighter cap was hidden behind the
first per-market refusal: 10% of allocated live equity was only $2.50. The owner had
already authorized $517.75 for Kalshi, but unallocated reserve did not count.

This was not a rule that divides by invested positions and makes every first position
100% concentrated. Small entries were possible. It was a capital-basis mismatch, incomplete
agent-facing limits, and missing feedback about pre-submission refusals.

## Existing funded capital, not a new allocation

For an explicit venue authorization, event concentration now uses:

```
pnl = sum(marked agent/House equity - internal stake)
event capital = max(0, min(authorized venue dollars + min(pnl, 0), baseline cash + pnl))
```

All ledger accounts count, including retired/swept accounts and House fees. Internal stakes
are loans, not deposits. The budget cannot increase with a new deposit or a profit; booked
losses reduce it. Baseline owner positions supply no capital. Without an explicit venue
envelope, the legacy allocated-equity basis remains. Missing funded baseline or exhausted
authorized capital refuses new event entries. Reducing exits remain available.

At the untouched $517.75 grant this means $51.775 shared principal per market and $129.4375
per settlement cohort. Huang's own 30% concentration cap is still $7.50; its stake is still
$25. A $9 entry still fails. The strategy receives the effective $7.50 upper bound so it can
choose an admissible size. This change increases shared concentration capacity relative to
the bootstrap implementation, within the already authorized venue envelope. Daily-loss
denominators, cash/fee checks, order caps, promotion tests and capital allocation do not change.

Existing holdings, both legs, working buys and accepted earlier intents in the same batch
consume shared capacity. The snapshot's per-market headroom is advisory; all rules run
again at submission. No order is automatically resized, submitted or replayed by this fix.

## Feedback and time to the next experiment

- Both the strategy snapshot and research standing receive owned `book.refused` outcomes
  alongside venue order outcomes, bounded to the last 12. Refusals are explicitly marked as
  not submitted to a venue. Other agents' or books' outcomes do not leak into that feedback.
- A new current-book refusal makes research due after at least 60 seconds since the last
  completed pass. Existing durable jobs, earned credits and provider budget still gate work.
  A refusal already covered by a completed pass does not retrigger research by itself.
- The legacy catch-up pacing branch can no longer lengthen a configured sub-hour research
  interval to one hour. The active campaign disables that legacy catch-up branch already;
  this is a regression prevention, not a claim that it caused today's observed throughput.
  The currently stored accelerated research policy is 15 minutes, not 10 minutes.
- During the accelerated game, five newly completed non-overlapping exposures or five new
  active blocks after the last audit can earn a new audit before the usual 24-hour cooldown.
  The deterministic screen must still qualify the agent and the fresh audit must approve it.
  The same evidence cannot be reused to request repeated audits. Provider-error backoff
  and the auditor's credit floor remain. The eligibility rule is shown in research standing.

These changes shorten specific feedback delays. They do not make turnover, model spend,
repeated historical replays or paper profits evidence of a live trading edge.

## Validation

Disposable fake-venue checks cover the first-agent case, per-agent caps, loss persistence
across sweep/restart, later deposits, funding and profit bounds, shared resting orders,
same-batch correlated reservations, zero capital, exits and the unchanged daily-loss stop.
Snapshot checks cover the published limits and research preview. Research checks cover
current-book ownership, provider budget refusal, duplicate feedback, fast cadence and a new
audit only after a fresh complete evidence batch. Full CI also exercises promotion, scaling,
demotion, tuition and the external gateway; no verification trade is sent to a real venue.
