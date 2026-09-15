# Long Term Capital Management runtime

`ltcm` is the second-generation runtime of this repository: a roster of autonomous
portfolio-manager **desks** that research, argue and trade across several venues, a deterministic
**risk engine** between every desk and every broker, a second-model **critic** on every real-money
order, a rules-based **committee** (the agent is called Meriwether) that allocates capital by track
record, an **evolution** loop that breeds and retires desk variants on forward results, and a
**publisher** that streams every thought, tool call, memo, order, fill and mark to the public site.

There is no paper trading here. A desk is either **live** -- its orders go to a real venue and its
losses are the owner's -- or **shadow**: it runs full sessions, proposes orders through the same
risk engine, and its proposals are scored against real market prices as hypothetical trades, but
nothing is ever sent and no notional balance is presented as the floor's equity. A shadow desk
competes to take over a live sleeve, and Meriwether's gates decide when it does.

Design rules, inherited from the first generation and kept on purpose:

- **Standard library only.** `sqlite3`, `urllib`, `decimal`, `hashlib`, `json`, `threading`.
  Tests are `unittest`. No async framework, no ORM, no third-party HTTP client.
- **Append-only and hash-chained.** Nothing is edited. Corrections are new events.
- **Derived idempotency keys.** Every order intent, request and event has a stable identity so a
  crash never duplicates an order or a paid model call.
- **Guardrails are code, not prompts.** The risk engine, broker gateway, evaluator, budget caps and
  publication policy are human-written and immutable at runtime. Everything else (playbooks,
  prompts, tool usage, mandates within bounds, capital allocation) is allowed to evolve.
- **Public by default.** Every event carries a `public` flag. Payload keys beginning with `_` are
  private and stripped before publication. Prompts, raw model output, credentials, account numbers
  and licensed quotes never leave the box.
- **Decimal money.** Prices, quantities and cash are `Decimal`, serialized as strings.

## Layout

| Module | Responsibility |
|---|---|
| `events.py` | The shared append-only event log (`EventLog`): streams, kinds, hash chain, public projection. |
| `broker.py` | Venue-neutral contracts: `Instrument`, `Quote`, `OrderIntent`, `Order`, `Fill`, `Position`, `Balance`, the `Broker` protocol and errors. |
| `manifest.py` | `DeskManifest`: the declarative description of a desk (mandate, venues, instruments, limits, model, cadence, tools, budget, capital, lineage, playbook). |
| `risk.py` | Deterministic pre-trade rules and circuit breakers. Returns a `Decision`; never a model call. |
| `ledger.py` | `DeskLedger`: each desk's book folded from allocations, fills and marks; time-weighted return, drawdown, daily P&L. |
| `gateway.py` | The only path from an intent to a venue: risk check, critic review, submission, fills, reconciliation, deferred-event release. |
| `critic.py` | The live-order critic: one cheap model call reads every real-money order against the desk's own rationale and can block it. Fails open. |
| `sim.py` | `ShadowBook`: the scoring engine for a shadow desk. Same `Broker` surface as a live adapter, filled at the real venue's quote with the real fee model, over any `MarketData` source. |
| `provider.py` | Sail Responses API client with function tools, background polling, idempotency, frozen rate card, per-request cost records and budget hooks. |
| `tools.py` | The research and action tools a desk may call, each with a JSON schema and an executor. |
| `desk.py` | The desk runtime: builds context, runs the tool-calling loop within budget, emits events, writes memory and memos, proposes orders. |
| `committee.py` | Meriwether: rules-based capital allocation across desks (weekly), the daily public memo, promotion and demotion by the fixed gates. |
| `evolve.py` | Variant populations per desk family: spawn, score on forward results, retire, mutate playbooks. |
| `publish.py` | Batches public events and leaderboard rows to the site API. |
| `analytics.py` | `ResultsLedger`: folds the log into per-desk, per-family and per-profile results for any window, renders the markdown lab report and publishes the daily `lab.result`. |
| `service.py` | The always-on loop: schedule desk sessions, tick simulators, mark ledgers, run risk breakers, run the committee and evolution on their cadences, publish. |
| `adapters/` | Live venue adapters (`alpaca.py`, `kalshi.py`, `coinbase.py`, later `schwab.py`, `tastytrade.py`). |
| `data/` | Market and document sources (`yahoo.py`, `alpaca.py`, `kalshi.py`, `coinbase.py`, `edgar.py`, `news.py`). |
| `desks/` | Desk manifests (JSON). `playbooks/` at the repository root holds the versioned playbooks desks edit. |

## Streams and event kinds

Streams: `desk:<id>`, `ledger:<id>`, `risk`, `broker:<venue>`, `committee`, `evolution`, `lab`, `ops`.
A shadow desk's orders and fills live on `broker:shadow`, and every payload the shadow book
produces carries `shadow: true`. Nothing marked `shadow` is money.

| Kind | Stream | Public | Payload (required keys) |
|---|---|---|---|
| `desk.session_started` | desk | yes | `session_id`, `trigger` |
| `desk.thought` | desk | yes | `session_id`, `text` (reasoning summary or note) |
| `desk.tool_call` | desk | yes | `session_id`, `call_id`, `tool`, `arguments` (redacted) |
| `desk.tool_result` | desk | yes | `session_id`, `call_id`, `tool`, `summary`, `document_sha256?` |
| `desk.memo` | desk | yes | `session_id`, `title`, `text` |
| `desk.intent` | desk | after fill | `intent_id`, `instrument`, `side`, `quantity`, `order_type`, `limit_price?`, `rationale` |
| `desk.playbook_updated` | desk | yes | `version`, `diff`, `reason` |
| `desk.postmortem` | desk | yes | `period`, `text`, `lessons[]` |
| `desk.outcome` | desk | yes | `instrument`, `market_id`, `result`, `entry_price`, `exit_price`, `quantity`, `pnl`, `held_for_hours`, `rationale_excerpt` |
| `desk.session_ended` | desk | yes | `session_id`, `requests`, `cost_usd`, `reason` |
| `desk.watch` | desk | yes | `trigger`, `detail`, `decision` (`wake`/`ignore`), `reason`, `cost_usd`, `session_id?` |
| `desk.exit_plan` | desk | yes | `intent_id`, `instrument`, `target_price?`, `stop_price?`, `time_stop_at?`, `venue_native`, `order_ids[]` |
| `risk.decision` | risk | yes | `intent_id`, `desk_id`, `approved`, `reasons[]` |
| `risk.review` | risk | yes | `intent_id`, `desk_id`, `verdict` (`approve` or `block`), `reason`, `model` |
| `risk.breaker` | risk | yes | `scope`, `rule`, `detail`, `action` |
| `broker.order` | broker | after fill | `order_id`, `intent_id`, `status`, `filled_quantity`, `average_price?`, `shadow?` |
| `broker.fill` | broker | yes | `fill_id`, `order_id`, `instrument`, `side`, `quantity`, `price`, `fee`, `shadow?` |
| `broker.reconciled` | broker | yes | `venue`, `matches`, `mismatches[]` |
| `ledger.mark` | ledger | yes | `equity`, `cash`, `positions[]`, `daily_pnl`, `as_of`, `shadow?` |
| `committee.allocation` | committee | yes | `allocations{desk_id: usd}`, `shadow{desk_id: true}`, `reasons{}` |
| `committee.memo` | committee | yes | `period`, `text` |
| `committee.gate` | committee | yes | `desk_id`, `gate`, `passed`, `evidence{}` |
| `evolution.spawned` | evolution | yes | `desk_id`, `family`, `parent_id`, `generation`, `mutation` |
| `evolution.retired` | evolution | yes | `desk_id`, `reason`, `score{}` |
| `evolution.promoted` | evolution | yes | `desk_id`, `from`, `to`, `score{}` |
| `lab.hypothesis` | lab | yes | `hypothesis_id`, `text`, `test_plan` |
| `lab.result` | lab | yes | `hypothesis_id`, `metrics{}`, `verdict` |
| `ops.alert` | ops | yes | `level`, `text` |
| `ops.budget` | ops | yes | `scope`, `spent_usd`, `cap_usd` |
| `provider.request` | ops | no | `request_id`, `desk_id`, `profile`, `cost_usd`, `usage{}` |

"After fill" means the event is written immediately but marked `public: false`; the publisher
releases it when the matching order reaches a terminal state. Nobody can trade ahead of a desk.

## Exits and the night desk

A desk states its exit with its entry: `propose_order` takes `target_price`, `stop_price` and
`holding_period_hours`, the risk engine refuses a stop on the wrong side of the entry, and the
plan is published as `desk.exit_plan` the moment the venue accepts the order (`ltcm/exits.py`).
From then on the floor keeps it: on Coinbase the target and the stop ride on the order itself
as an attached take-profit/stop-loss (`venue_native`), everywhere else the floor compares the
live mark with the levels every tick and files an exposure-reducing market exit
(`broker.order` with `purpose: exit` and `exit_reason`), and the time stop is a market exit at
that moment on every venue. Exits skip the critic; one exit per plan per reason.

Between sessions the night desk (`ltcm/watch.py`) looks, at no model cost, for a held market
or coin moving more than a threshold, a fill, a new market in a series the desk follows, or a
headline naming what it holds, then spends one flash-model turn deciding whether to wake the
desk. Both verdicts are published as `desk.watch`; a wake starts a session with trigger
`watch:<kind>`, at most once per half hour per desk, never while the desk is in session, and
never for a live desk on a venue the floor cannot trade. The checkpoint carries every desk's
positions with their thesis and plan, the running session, and the watch's day.

## Spend policy: a runway, not a cap

The floor has no daily inference cap. The Sail credit above a small reserve is the limit, read
live every tick, and `ltcm/runway.py` decides only how the floor approaches zero:

| Mode | When | What the floor does |
|---|---|---|
| `open` | runway longer than `throttle_days` (3) | No cap. Every desk runs its cadence, families are bred up to `target_variants`, the committee and the evolution loop run. |
| `throttled` | runway under `throttle_days` | The remaining credit is stretched over `stretch_days` (5); only live desks keep their sessions; breeding pauses. |
| `stopped` | balance at or under `reserve_usd` (10) | No new model call. Marks, order polling, settlements and publication continue. Credit added at Sail lifts the floor back to `open` on the next tick. |
| `unknown` | the balance could not be read | The floor keeps working under `fallback_cap_usd`; an outage at the usage API is not a reason to stop trading. |

Runway is `(balance - reserve) / burn`, where burn is the trailing day's settled model cost from
the provider's own ledger plus `infra_usd_per_day` for the box. The picture is published as
`ops.budget` (one event per change of mode, cap, dollar of balance or day of runway) and in the
checkpoint's `budget` block, so the site shows the credit, the runway and the mode. Every change
of mode is an `ops.alert`, and the gateway's watchdog mails the owner at a week of runway, at two
days, and when the floor has stopped.

One fuse survives: a desk may not commit more than `desk_fuse_pct` (25%) of the spendable
credit in a day (never under `desk_fuse_min_usd`). It is not a budget -- a desk working normally
never reaches it -- it is the difference between a desk stuck in a tool loop costing an afternoon
and costing the balance. `manifest.budget.usd_per_day` is ignored under this policy.

`spend_mode: "capped"` in `ltcm/config.json` restores the older policy: a fixed daily cap plus a
share of realized profit, and each desk's own daily budget. The provider still refuses a request
when the live Sail balance is below the reserve under either policy, and unknown request costs
keep their reservation until settled.

## The live-order critic

Every order from a desk on **live capital** that the deterministic engine approves is read once
more, by a different model, before it is sent (`critic.py`, wired in `Gateway.propose`). The critic
sees the desk's mandate and limits, the intent, the engine's reference price and notional, the
published rationale, the desk's latest memo and its current book, and answers with strict JSON:
`{"verdict": "approve"|"block", "reason": "<one sentence>"}`. It judges obvious contradictions only
-- a side that contradicts the rationale, a size or price that does not match the stated plan, an
instrument the rationale never names, an addition to a position beyond the mandate, a rationale
with no catalyst and no exit -- and is told to approve when in doubt.

A `block` writes a second `risk.decision` (`approved: false`, reasons `["critic: <reason>"]`) and
nothing is submitted. Either verdict is published as `risk.review`, whose payload is exactly
`{intent_id, desk_id, verdict, reason, model}` because the site rejects a batch containing any
other shape. A provider failure, a timeout, a budget refusal or any output that is not the JSON
asked for publishes nothing, raises an `ops.alert` and lets the order proceed: the deterministic
engine remains the guardrail, and a model that cannot answer can never halt the floor. Shadow
desks skip it: there is no money to protect. Configured by `critic_enabled` (default true) and
`critic_profile` (default `glm_asap`, `reasoning_effort` low, 1024 output tokens), and charged to
the desk's own daily budget under the request key `critic:<intent id>`.

## Shadow desks

A shadow desk is a full desk. It runs its cadence, spends its model budget, calls the same tools,
proposes orders with the same `OrderIntent`, and is checked by the same deterministic risk engine.
The one difference is the last step: `Gateway.route()` reads the desk's capital mode and sends an
approved order to the `shadow` book instead of to a venue.

* The order names the venue it **would** have traded on (`instrument.venue`), and the book prices
  it at that venue's quote and charges that venue's published fees (`ShadowBook.market_venue`), so
  a shadow result and a live result mean the same thing.
* `broker.order`, `broker.fill` and `ledger.mark` from a shadow desk carry `shadow: true`.
* The committee's allocation for a shadow desk is a **notional scoring budget** -- the capital its
  manifest asks for -- listed under `shadow` in the `committee.allocation` payload. It is never
  drawn from the floor's capital and never counted in the floor's equity: `floor_totals(...,
  include=live_ids)` and the checkpoint's `floor` block sum the live sleeves alone.
* Reconciliation never compares a shadow book against a venue, and the floor's daily-loss breaker
  cannot be tripped by a hypothetical loss.

Promotion needs two things and publishes both: the gate's evidence, and an open venue. A desk that
passes gate A onto a venue missing from `live_venues` is deferred with a public `committee.gate`
whose reason is `venue not enabled`; the next run after the venue opens promotes it on the same
evidence. Children of a live desk are born shadow.

## The checkpoint

`publish.checkpoint_body` is the contract with the site:

* every desk row carries `mode` (`shadow` or `live`). A shadow row's `equity` is its notional book
  and its `return_pct` and `daily_pnl` are hypothetical;
* `floor.live_equity` and `floor.live_daily_pnl` are the real numbers the site puts on the
  masthead, with `floor.live_desks` and `floor.shadow_desks` as counts;
* `infra` is `{host, box_id, checkpoint_count, spend_usd, uptime_seconds, region, requests_today}`,
  filled from `hostinfo.describe_host()` where that module exists and degrading to
  `{"host": "local"}` where it does not. Only those keys are published: the hostname, the pid and
  everything else `describe_host()` knows stay on the box;
* `budget` is unchanged.

## The lab report

The floor is a set of hypotheses -- this mandate, this model, this cadence, this budget -- and
`analytics.py` is how they are scored. `ResultsLedger` folds the event log over any window into
four rollups, each carrying the same metrics: the **floor**, each **desk**, each **family** and
each **model profile**. It reads nothing but the log, decides nothing, and writes nothing except
the one event below.

```sh
python3 -m ltcm report                        # the trailing 7 days, as JSON
python3 -m ltcm report --days 30 --markdown   # the table report
python3 -m ltcm report --days 7 --markdown --write docs/runs/
```

What it counts, and from what:

| Group | Metrics | Source |
|---|---|---|
| Work | `sessions`, `turns_per_session`, `tool_calls_per_session`, `seconds_to_first_order` | `desk.session_started`, `desk.session_ended`, `desk.tool_call`, `desk.intent` |
| Cost | `sail_cost_usd`, `requests`, `cost_per_decision_usd`, `overhead_cost_usd` | `provider.request` (private; only the aggregates are published) |
| Results | `decisions`, `closed_trades`, `win_rate`, `avg_pnl_usd`, `closed_pnl_usd`, `fees_usd`, `realized_pnl_usd`, `hypothetical_pnl_usd`, `net_pnl_usd`, `pnl_per_inference_dollar`, `max_drawdown_pct` | `broker.fill`, `desk.outcome`, `ledger.mark`, `committee.allocation` |
| Judgement | `brier`, `critic_block_rate`, `risk_rejection_rate`, `playbook_versions`, `postmortems` | `desk.outcome` rationales, `risk.review`, `risk.decision`, `desk.playbook_updated`, `desk.postmortem` |

Four rules make the numbers mean what they say:

* **A closed trade, not a position.** Event contracts are scored from `desk.outcome`, which the
  settlement writes; equities and crypto are closed by average cost out of the fills, the same
  arithmetic `DeskLedger` uses for realized P&L, so the two never disagree. The settling fill of
  an event contract is not counted twice.
* **Shadow is not money.** Closed P&L is split into `realized_pnl_usd` (live desks) and
  `hypothetical_pnl_usd` (shadow desks) and the two are never added.
* **A ratio with no denominator is absent**, not zero. A desk with no closed trades has no win
  rate.
* **Cost is the real bill.** `sail_cost_usd` is the sum of the private `provider.request` cost
  records, so `net_pnl_usd` (closed P&L less fees less inference) is the floor's actual result.
  The floor's cost includes the overhead nobody's desk paid for: the committee's memo, a spawned
  playbook, the critic.

`brier` scores only what a desk put in writing: the probability parsed out of its own rationale
(`probability: 0.62` or `p=0.62`), against 1 for a market that resolved yes and 0 for no. A trade
whose rationale states no number is not scored, and `brier_n` says how many were.

The per-profile rollup exists because the model is part of the genome: `evolve.mutate` breeds one
child in three onto a different profile from the curated list (`pro_flex`, `kimi_flex`,
`glm_flex`, `oss_asap`, `flash_flex`), never its parent's, and records both in
`evolution.spawned`. A family therefore always has siblings running the same mandate on different
models, and the report is where that experiment is read.

### The daily `lab.result`

Once per UTC day the floor publishes one `lab.result` on the `lab` stream, id `lab:daily:<date>`,
with `{hypothesis_id: "daily-<date>", metrics, verdict}`. `metrics` is a flat `{dotted key:
string}` block (`floor.*`, `desk.<id>.*`, `profile.<name>.*`) capped at 20 KB; `verdict` is one
sentence a human can read without opening it. The service writes it from the tick:

```python
from .analytics import ResultsLedger          # at the top of service.py

# in Service.tick(), after the evolution block and before result["published"] = self.publish(),
# so the day's record goes out on the same tick that writes it:
try:
    event = ResultsLedger.publish_daily(self.log, at, manifests=self.manifests)
    result["lab"] = None if event is None else event.id
except Exception as exc:                      # a scoreboard may never stop the floor
    self.alert("warning", f"lab result failed: {exc}")
```

Safe on every tick: `publish_daily` defaults to the **last complete UTC day**, so the record is
never a partial one, and it returns early on a single indexed lookup once that day's id exists --
the fold runs at most once a day. It returns `None` for a day with no sessions, no requests and
no decisions, so a floor that was switched off publishes silence rather than a row of zeroes.
Nothing else in the floor calls it, and nothing in it can block an order.

`docs/runs/README.md` explains what each metric means and how to read a week of them.

## Publication policy

Thoughts, tool calls, memos, marks, allocations and evolution events publish live. Order intents
and orders publish after fill or cancel. Prices shown publicly are the floor's own fills and
account-level marks, or delayed data labelled as such; licensed real-time quotes are never
republished. Published positions always match the real book, and every page carries the
position-disclosure notice.

## Migration from `portfolio_runtime`

The first-generation `portfolio_runtime` ran one S&P 500 paper portfolio. That was a different
system with a different purpose, and it is retired.

1. Until the scheduled week completes, `portfolio_runtime` and the Sailbox bundle are frozen.
2. The filings desk (`merton`) imports the research bank -- the written case and the open questions
   for each company -- as memory: `python3 scripts/import_research_bank.py` (add `--dry-run` first).
   One entry per company, idempotent, `kind` `research`, tags `portfolio-agent` and `2026-09`.
3. `portfolio_runtime` moves to `docs/history/` with its run records; its market calendar,
   Yahoo adapter and evidence capture are ported into `ltcm/data/`.
4. Repository, package, site section and docs take the Long Term Capital Management name in one commit.
