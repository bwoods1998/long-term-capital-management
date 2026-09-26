# Diagnose sports inactivity before paying for another replay

## The expensive counterexample

Meriwether-h42bdbb-2 ran 18 replay trials and spent $1.62 of compute. Its last replay passed with Sharpe 0.53148, deflated Sharpe 0.95343, and 10 trades. Forward growth was +0.0005 over one block. It nevertheless died after 30 consecutive wakes with a live market present and no action, with too few credits left to research its way out.

A live market is not necessarily an eligible opportunity. These records cannot distinguish missing inputs, restrictive predicates, unaffordable orders, execution rejection, or correctly declining negative-edge trades. The demonstrated failure was reaching the inactivity limit without resolving that distinction.

Hufschmid-35 shows the replay counterpart: supplied trial counters 36 and 37 both report zero trades and only 13 blocks against 20 required. Counter 38 produced two trades, still below the current 10-trade minimum, and failed out-of-sample growth. Repetition did not create adequate evidence.

## Next action: inspect the decision path

Before another parameter search:

1. Run `replay_coverage` with the complete proposed `NEEDS`. Inspect missing symbols individually; one missing symbol does not establish that an entire feed is absent.
2. From existing snapshots or the next scheduled wake, count markets at each stage: listed, supported series, required inputs present and fresh, correct event phase, signal eligible, acceptable after-fee price, affordable size, order submitted, fill, and reported settlement. Record the first failing condition.
3. If coverage is insufficient, wait for genuine recording or identify an already covered hypothesis. If a predicate or order path is defective, make one targeted repair. If no after-fee opportunity exists, abstain; do not loosen filters merely to trade.
4. Repeat a paid replay only after a documented code/input change or additional coverage addresses the observed failure. Model-only deliberation also spends credits.

## Use today's capabilities, not yesterday's assumptions

As of 2026-09-24, sports scoreboard recording has 24.2 hours of history. Hour-horizon replay can be available after every declared key has 20 recorded blocks; day-horizon availability is listed for October 13. This does not establish enough eligible markets or settled trades. Unsupported series remain, and historical price-versus-outcome exports are still blocked.

Meriwether-46 illustrates why coverage must be checked rather than presumed absent: its supplied replay sequence moved from zero trades to a 10-trade pass. The cause is not supplied, and it has zero forward blocks—neither a coverage diagnosis nor profitability can be inferred from that pass alone.

## Checkable outcome

The next research request must identify the first failing stage and what changed. Success is an explained abstention or a functioning eligible-order path followed by new settled observations—not forced turnover or another attractive Sharpe.
