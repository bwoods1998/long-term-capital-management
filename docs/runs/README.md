# Run records and lab reports

## Current league

Every record of the league rebuilt on September 19 and 20, 2026, newest first. Each record is
dated and kept as history once it is finished; the [project README](../../README.md) and
[operations](../operations.md) carry the state as it now stands.

- [Dynamism II, September 23](2026-09-23-dynamism-ii.md): a 15-minute watch found no promotion from paper to real money in 24 hours and fifteen merged repairs never born; what shipped: repairs seated, the audit after promotion, the settled lane, a budget that follows the owner's real spend, and the foundry on fast markets.
- [Overnight rebuild, September 22](2026-09-22-overnight-rebuild.md): the eight-hour rebuild of the learning loop (hypothesis foundry, repair engineer, research gate, deep Alpaca replay with a sealed holdout, attested self-deploys), its before and after measurements, the dynamism revision (#123) and the state at the 21:10Z deadline.
- [Model routing, prompt caching and economics, September 22](2026-09-22-model-routing-experiment.md): Luna's prompt cache (nothing read in 15,044 calls, then 97% of a follow-on turn), batch inference, the balanced and Flash tier experiment, task-aware routing, research traces, `scripts/economics.py` and a tick-latency diagnosis.
- [Critical fixes, September 22](2026-09-22-critical-fixes.md): the 03:55Z review: the Sail meter's monthly line, the audit reserve reading the wrong meter, empty consultations, Merton-written code beside the House's secrets, the gateway under-counting Kalshi NO buys, and the expiring agent image.
- [The eight-hour watch, September 21](2026-09-21-eight-hour-watch.md): the owner's mandate to change the game where it slowed self-improvement: the replay and paper-death revisions, the fast lane and learning surge on the money rules (the grant ratified for the same capital), the turbo layer, and Jev as a research instrument.
- [Live hour, September 21 UTC](2026-09-21-live-hour.md): owner activation confirmed, continued research funding, weekday market access, paper-account investigation, and the first live execution and settlement (a $5.6733 loss) with the receipt defect it exposed.
- [Persistent earned live trading, September 21 UTC](2026-09-21-persistent-live-trading.md): replaces the timed pilot with owner-activated ladder access and existing venue cash; budgets and losses are retained.
- [Game gate audit, September 21 UTC](2026-09-21-game-gate-audit.md): reachable evidence gates, aggressive resource rewards, replacement and bounded live learning.
- [Evening watch, September 20 Pacific](2026-09-20-evening-watch.md): two-hour observations and the eight-hour accelerated run.
- [Foundation progress, September 20](2026-09-20-foundation-progress.md): deployed campaign,
  research recovery, model grants, replay proof and Jev integration.
- [Model comparison, September 20](2026-09-20-model-routing.md): what the paid coding pilots measured.
- [The watch, September 20](2026-09-20-the-watch.md): twenty hours of watching the new floor, the
  faults where it reported health while doing less or nothing, and their repairs.
- [Overnight build, September 19 to 20](2026-09-20-overnight-build.md): the build of the league,
  every decision and its reason, the step log and what was verified live.
- [Jev probe data](data/2026-09-20-typesafe-probe.json): frozen sanitized cases and measured responses.
- [Game gate controls](data/2026-09-21-game-gate-controls.json): the reproducible 96-agent
  synthetic controls behind the gate audit.

The live league's read-only progress command is `python -m league.phase1 --root /workspace/state`
on the House. Its [phase documentation](../phase-one.md) explains the counts and cost treatment.

## Historical first-run reports

The commands below describe the retired chat-desk runtime, not the current league.

Two kinds of file live in this directory.

- **Run records** (`2026-09-15-ltcm-launch.md`, `2026-09-15-sail-native-launch.md`) are written
  by hand at a hand-off: what was running, what was verified live, what is deliberately off.
- **Lab reports** (`<date>-lab-report.md`) are generated. They are the floor's own scoreboard:
  what each desk did, what it cost, what it earned, and which model earned it.

The point of the lab report is that the **architecture** can be argued about on numbers instead of
impressions. A desk is a hypothesis (this mandate, this model, this cadence, this budget); the
report is the experiment's result. Nothing in it is a forecast and nothing in it is a backtest --
every number comes from events the floor already wrote.

```sh
python3 -m ltcm report                        # the last 7 days, as JSON
python3 -m ltcm report --days 30 --markdown   # a month, as the table report
python3 -m ltcm report --days 7 --markdown --write docs/runs/
```

`--write DIR` saves `DIR/<date>-lab-report.md` and does nothing else. It never commits, never
publishes and never touches the event log. Keep the ones you acted on; the rest can be
regenerated from the log at any time, because the log is the only input.

The floor also publishes a short public version of the same numbers once a day: a `lab.result`
event on the `lab` stream, id `lab:daily:<date>`, carrying a flat `metrics` block and a
one-sentence `verdict`. That event is the permanent record. A markdown report is a convenience.

## What each metric means

`ResultsLedger` (`ltcm/analytics.py`) folds the event log over a window and produces four
rollups: the **floor**, each **desk**, each **family** (the mandate: `earnings`, `filings`,
`kalshi`, `crypto`) and each **model profile** (`pro_flex`, `oss_asap`, ...). Every rollup carries
the same metrics, so a number means the same thing wherever you read it.

### Work

| Metric | What it counts | Read it when |
|---|---|---|
| `sessions` | `desk.session_started` events in the window | Cadence changes: did the desk actually run as often as its manifest says? |
| `turns` / `turns_per_session` | Model turns the desk loop took (`desk.session_ended.requests`) | A desk hitting `max_turns` every session is either under-prompted or over-mandated. |
| `tool_calls` / `tool_calls_per_session` | `desk.tool_call` events | Research effort. Many tool calls and no decisions is a desk that reads and never acts. |
| `seconds_to_first_order` | Mean seconds from a session's start to its first `desk.intent` | Latency that matters on an event desk: a market that moves in ten minutes is gone by minute twelve. |
| `sessions_with_order` | Sessions that produced at least one intent | With `sessions`, the share of sessions that ended in a decision. |

### Cost

| Metric | What it counts | Read it when |
|---|---|---|
| `sail_cost_usd` | Sum of `provider.request.cost_usd` -- the private cost records | Budget decisions. This is the real inference bill, not an estimate. |
| `requests` | `provider.request` events | Cost per request tells you whether a profile is being used for the work it is priced for. |
| `overhead_cost_usd` (floor) | Floor spend that belongs to no desk: the committee's memo, a spawned playbook, the rate-card check | If overhead approaches desk spend, the machinery costs more than the trading. |
| `cost_per_decision_usd` | Inference divided by fills | The single most comparable number across desks. A desk at $2 a decision needs to be twice as right as one at $1. |
| `desk_cost_usd` (profiles) | What the desks attributed to a profile spent, on every profile they used | A desk's critic runs on a different, cheaper model; this is the whole bill, `sail_cost_usd` is only what this profile was paid. |

### Results

| Metric | What it counts | Read it when |
|---|---|---|
| `decisions` | `broker.fill` events for the desk | The denominator of everything. A desk with no fills has produced no evidence, whatever its equity says. |
| `closed_trades` | Round trips: `desk.outcome` events for event contracts, plus closes derived from fills by average cost for everything else | Only closed trades are scored. An open position is an opinion. |
| `win_rate` | Closed trades with P&L above zero, over closed trades | Alongside `avg_pnl_usd`, never alone: a 30% hit rate with a 5:1 payoff is a good desk. |
| `avg_pnl_usd` | Closed P&L over closed trades | Size of the edge per decision. |
| `closed_pnl_usd` | Sum of closed-trade P&L, gross of fees | The trading result. |
| `fees_usd` | Venue fees on the window's fills | On Kalshi and crypto this is a large share of a small edge. |
| `realized_pnl_usd` / `hypothetical_pnl_usd` | The same closed P&L, split by capital mode: live desks are money, shadow desks are a score | Never add them together. A shadow desk's profit is not in any account. |
| `net_pnl_usd` | `closed_pnl_usd` less fees less inference | What the architecture actually earned. This is the north-star number. |
| `pnl_per_inference_dollar` | Closed P&L after fees, per dollar of inference | Did the model pay for itself? Below 1.0 it did not. |
| `max_drawdown_pct` | Worst peak-to-trough fall of marked equity inside the window, net of capital the committee moved in or out | Pain. The ledger's own `max_drawdown_pct` is the desk's all-time number on the flow-neutral growth index; this one is the window's. |
| `equity_usd` | The desk's last `ledger.mark` in the window | Context, not a result: allocations move it too. |

### Judgement

| Metric | What it counts | Read it when |
|---|---|---|
| `brier` / `brier_n` | Mean squared error of the probability the desk *stated in its own rationale* against what happened (1 for a market that resolved yes, 0 for no) | Only event-contract desks, and only trades whose rationale carried `probability: 0.xx` or `p=0.xx`. A desk that states no number is not scored; `brier_n` says how many were. 0.25 is a coin flip; below 0.18 is a real forecaster. |
| `critic_block_rate` | `risk.review` verdicts of `block` over all reviews | The second model's opinion of the first. Near zero means the critic is decoration; above about 15% means the desk is proposing orders its own rationale does not support. |
| `risk_rejection_rate` | `risk.decision` events with `approved: false`, over all of them, excluding the critic's own block | The deterministic engine's opinion. A desk that is rejected constantly has a mandate or a size limit it does not understand. |
| `playbook_versions` | `desk.playbook_updated` events | Is the desk still learning? Zero over a month means the post-mortem is not doing anything. |
| `postmortems` | `desk.postmortem` events | The cadence's own health check. |

Undefined ratios are **absent** (`null` in JSON, `--` in the tables), never zero: a desk with no
closed trades has no win rate, and printing `0` would read as "never wins".

## How to read a week of them

Put seven reports side by side, or run one `--days 7`. Then ask four questions, in this order.

**1. Which model?** Compare desks in the *same family* on different profiles -- that is what
`evolve.mutate` breeds them for. The comparison is `cost_per_decision_usd` against
`pnl_per_inference_dollar` and `brier`, not raw P&L: a desk that made more money on ten times the
inference has not proved anything. A cheap profile that holds its hit rate is the finding worth
acting on; move a sibling onto it and let the next report judge. Beware of two traps: a profile
compared over fewer than ~20 closed trades is noise, and a profile that looks expensive may be
carrying the critic's bill (`desk_cost_usd` versus `sail_cost_usd` on the profiles table).

**2. Which cadence?** Read `sessions`, `sessions_with_order` and `seconds_to_first_order`
together. A desk that runs three times a day and orders once a week is paying for six sessions of
reading per decision -- cut the cadence, not the budget, and watch `cost_per_decision_usd` fall
without `closed_pnl_usd` following it. A desk whose `seconds_to_first_order` is climbing is
spending its session on research that arrives after the opportunity.

**3. Which budget?** The floor's `sail_cost_usd` against its `net_pnl_usd` is the only budget
argument that matters. Inside that, `overhead_cost_usd` says what the committee, the critic and
the evolution loop cost to run: machinery that costs more than the desks earn is machinery to
simplify. Raise a desk's daily cap only when its `pnl_per_inference_dollar` is comfortably above
1 and its sessions are ending on `max_turns` rather than on `end_session`.

**4. Which desks to retire?** A desk earns its place with `net_pnl_usd` above zero over a month,
a `max_drawdown_pct` inside its mandate, and evidence that it is learning (`playbook_versions`,
`postmortems`). A desk with a good `win_rate` and a negative `net_pnl_usd` is being eaten by fees
or inference; fix the cost before retiring the idea. A desk with `decisions` near zero over a
month is not a bad desk -- it is not a desk at all, and the mandate is what needs changing. The
evolution loop already retires the worst shadow variant in a family on the same evidence
(`evolve.select`); the report is how a human checks that the loop is retiring the right one.

Two standing cautions:

- **Small numbers lie.** Under about 20 closed trades, `win_rate` and `brier` are anecdotes. Let
  the window grow rather than the conclusion.
- **Shadow is not money.** `hypothetical_pnl_usd` is what a desk *would* have made at the real
  venue's prices and fees. It is the right number for deciding a promotion and the wrong number
  for anything else.

## The public record

Each UTC day gets exactly one `lab.result`:

```json
{
  "hypothesis_id": "daily-2026-09-15",
  "metrics": {"floor.net_pnl_usd": "58.7520", "desk.mullins.win_rate": "0.6667", "...": "..."},
  "verdict": "Mullins 3 outcomes, 66.7% hit, +$29.65 net of $0.27 inference; Hilibrand 0 trades"
}
```

`metrics` is deliberately flat (`floor.*`, `desk.<id>.*`, `profile.<name>.*`) and every value is a
string, so a reader a year from now needs no schema. The block is capped at 20 KB: on a crowded
day the least useful per-desk detail is dropped first, then the quietest desks, and
`metrics.truncated` says so. The record is written once per day and never edited -- a correction
is the next day's record, like every other event on this floor.
