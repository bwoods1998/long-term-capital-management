# Public game ladder

The personal site's `/capital/` page replaces its generation-return chart with the current
earned ladder: 0 Replay, 1 Paper, 2 Live, 3 Scaled. One dot represents one agent; hover, focus,
or tap reveals its name, tier, reported trading P&L and compute credits. Empty tiers remain
visible. Retirement is separate from demotion and from a negative P&L.

`Publisher._desk` publishes these additive fields in the existing, validated
`desks[].gate.evidence` object:

- `rung`: integer 0–3, from the evaluator. The browser never infers it from mode or P&L.
- `accounting_ok`: false when that book's attribution evidence is contaminated. The ladder
  suppresses profit/loss coloring and reports "Accounting under review" for that agent.
- `lifecycle`: `born_at`, `died_at` and `cause` from the registry; `last_move` is null or
  `{id, at, decision, from_rung, to_rung, reason}` from the last recorded promotion/demotion.
  Initial seating, an audit approval and a passed replay are not promotion events.

The roster contains every living agent plus the eight latest deaths; the public exits count
is explicitly recent, not all time. The checkpoint records survive activity-tape turnover.
Existing `lab.progress` events from `component=league` supply live movement notifications and
additional history through exact `league_news` lifecycle templates. No event is rewritten or
backfilled, and no publisher or browser call executes an agent or places an order.

The browser polls checkpoints every 30 seconds, refreshes on lifecycle messages, and consumes
the existing WebSocket/polling feed. An event may reach the page before the next checkpoint:
the message appears immediately, but the agent's position changes only when the roster agrees.
The last known ladder is marked stale after the existing 15-minute checkpoint threshold.
Old publisher fixtures without rung evidence are displayed as unranked. A recent move receives
an arrow for one hour and one arrival animation per visit; reduced-motion preferences disable
the animation. Symbol labels accompany colors and every agent is a keyboard-accessible button.

Verification: `league.tests.test_publish` exercises initial seating, promotion, demotion,
death and invalid accounting with fake brokers. The site's tests exercise record parsing,
checkpoint/event lag, missing evidence, socket updates, deduplication, retained selection,
stale/empty states, and the actual runtime publication fixtures. Browser checks use a captured
public checkpoint at desktop, 390px and 320px widths, without brokerage access.
