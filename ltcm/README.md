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
| `evolve.py` | Variant populations per desk family: spawn, score on forward results, retire, mutate playbooks; the house genome of adopted changes. A child is born with its parent's playbook; the model's rewrite runs on the service's worker thread and lands as a versioned `desk.playbook_updated` on a later tick (`evolution.deferred_rewrites`, default on), so a spawn never stalls the loop. |
| `calibration.py` | Every probability a desk states (`record_forecast`), scored at resolution: Brier, reliability by decile, by desk, family, generation and floor. |
| `sandbox.py` | One forked Sailbox per desk for the code it writes (`run_code`): the lab image, a toolbox that persists, a daily fuse, data-only egress. |
| `history.py` | Public venue history for backtests: settled Kalshi markets, Kalshi candlesticks (batched), Coinbase candles; throttled, byte-capped disk cache. |
| `backtest.py` | Replays a strategy's `decide(kit, params)` over past days against a conservative simulator; `python3 -m ltcm.backtest --spec` prints one `BACKTEST-RESULT` line. |
| `runclock.py` | The public run clock: how long the desks have worked, sessions and decisions, Sail spend, profit per Sail dollar. |
| `exits.py` | The exit plans the floor keeps: stops, targets and time stops enforced every tick as exposure-reducing orders; Coinbase brackets ride on the order. |
| `watch.py` | The night desk: triggers over held markets, fills, new markets and headlines, one flash-model verdict on whether to wake a desk. |
| `notify.py` | Trade notices: one email per live fill and per settlement, folded from the log and sent through the gateway. |
| `runway.py` | The spend policy: open, throttled or stopped against the Sail credit; no daily cap. |
| `sailbox.py` | The Sailbox API client the operator scripts and the sandboxes use: create, fork, exec, egress, checkpoints. |
| `hostinfo.py` | What machine the floor runs on and for how long, for the checkpoint's infra block. |
| `lab.py` | The research lab: nightly directed experiments in a bounded vocabulary, bred as shadow variants, judged on gate evidence, adopted into the genome. |
| `mind.py` | The Firm Mind: every desk's closed positions scored into evidence-gated rules, proposed hourly by one model call from the older part of the tape and admitted only on the newest part it never read, retired in code, read as evidence by every session prompt and strategy generator. |
| `founding.py` | The firm hires itself: one model call a night proposes a new family from what the venues list and the floor does not trade, validated in code and born shadow; founded families that fail are wound down whole. |
| `publish.py` | Batches public events and leaderboard rows to the site API. |
| `analytics.py` | `ResultsLedger`: folds the log into per-desk, per-family and per-profile results for any window, renders the markdown lab report and publishes the daily `lab.result`. |
| `service.py` | The always-on loop: schedule desk sessions, tick simulators, mark ledgers, run risk breakers, run the committee and evolution on their cadences, publish. |
| `adapters/` | Live venue adapters (`alpaca.py`, `kalshi.py`, `coinbase.py`, later `schwab.py`, `tastytrade.py`). |
| `data/ws.py` | A standard-library RFC 6455 WebSocket client: TLS, handshake with extra headers, masked frames out, control frames answered, fragmentation reassembled, read deadlines. |
| `feeds/` | The floor's ears: `FeedHub` keeps venue sockets open on their own threads (Kalshi `fill`, `market_lifecycle_v2`, `ticker`; Coinbase `ticker` and `user`), caches fresh prices for `Service.quote`, and hands the tick fill candidates and resolutions. The REST sweeps stay the record; the sockets make them run sooner. Credential material comes from the gateway (`GET /v1/kalshi/ws-auth`, `GET /v1/coinbase/ws-jwt`). |
| `data/` | Market and document sources (`yahoo.py`, `alpaca.py`, `kalshi.py`, `coinbase.py`, `edgar.py`, `news.py`, `weather.py` for the National Weather Service forecasts and readings the weather desk prices from). |
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
| `desk.code_run` | desk | yes | `session_id`, `code_sha256`, `language`, `stdout`, `exit_code`, `seconds`, `sandbox`, `purpose`, `saved_as?` |
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
| `desk.forecast` | desk | yes | `session_id`, `market`, `venue`, `probability`, `market_price`, `side`, `resolves_at`, `reasoning` |
| `lab.calibration` | lab | yes | `scope`, `desk_id`, `family`, `generation`, `n`, `brier`, `reliability[]`, `as_of`, `since` |
| `lab.experiment` | lab | yes | `experiment_id`, `hypothesis`, `family`, `parent_id`, `change`, `variant_desk_id`, `status`, `proposed_at`, `evaluate_after`, `reason?` |
| `lab.verdict` | lab | yes | `experiment_id`, `status` (`adopted` or `rejected`), `evidence`, `reason`, `as_of` |
| `floor.mark` | ops | yes | `account_equity`, `account_cash`, `venues[]`, `as_of` (the real account balances, marked every five minutes) |
| `lab.resolution` | lab | no | `market`, `venue`, `result`, `settled_at`, `source` (the fact a market resolved, recorded once) |
| `committee.gate` | committee | yes | `desk_id`, `gate`, `passed`, `evidence{}` |
| `evolution.spawned` | evolution | yes | `desk_id`, `family`, `parent_id`, `generation`, `mutation` |
| `evolution.retired` | evolution | yes | `desk_id`, `reason`, `score{}` |
| `evolution.promoted` | evolution | yes | `desk_id`, `from`, `to`, `score{}` |
| `evolution.founded` | evolution | yes | `desk_id`, `family`, `name`, `rationale`, `venues[]`, `asset_classes[]`, `universe`, `model`, `as_of` |
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
## The lab and the calibration record

Two records feed the loop that improves the loop.

**Calibration** (`calibration.py`). An event desk states its probability of YES with the
`record_forecast` tool whether or not it trades; the statement is a public `desk.forecast`. When
the market resolves -- the floor's own settlement path says so when a desk held it, the venue
says so when none did, asked once and recorded privately as `lab.resolution` -- every forecast on
it is scored: Brier, `(p - outcome)^2`, and a reliability table by decile of stated probability.
The record is published daily as `lab.calibration` per desk, family, generation and floor, rides
in the checkpoint, and the desk's post-mortem reads its own two-sentence brief.

**The lab** (`lab.py`). Once a night, at `lab_time`, for each family with a live desk, a model
reads the results ledger, the last lab reports, the calibration and the recent post-mortems and
proposes at most two experiments: a hypothesis and a change from a fixed vocabulary (model,
effort, session times, memory, a tool, a symbol, a limit inside `lab.hard_limits`, a playbook
note). Each proposal is validated before anything else happens; a valid one is published as a
`lab.experiment` and bred at once as a directed shadow variant of the live desk. After the
evolution loop's `min_days`, the verdict compares the variant's gate evidence with its parent's
and is published as a `lab.verdict`: adopted means the change joins the family's house genome
(`ltcm/desks/genomes/<family>.json`), which every future child inherits; rejected retires the
variant. A live desk's manifest is never edited by the lab -- promotion through the gates is
the only way a live sleeve changes hands.

**Capital as a bandit** (`committee.py`). On a resize day each live desk's sleeve is a draw from
a normal posterior over its cost-adjusted excess return, seeded by the date so the draw is
reproducible from the public record, mapped to a multiple of manifest capital inside the
committee's floor and ceiling. `committee.bandit_enabled: false` restores the ratio rule.

## The weather desk

Kalshi's daily high and low temperature markets settle every day on one named National Weather
Service station per city, and the NWS publishes the point forecast for that station. Haghani
(`ltcm/desks/haghani.json`, family `weather`) reads both through the `weather_forecast` tool
(`ltcm/data/weather.py`: today's and tomorrow's highs and lows, the hourly path, the latest
reading, an explicit error band), prices every bucket a market lists against that band, records
a `record_forecast` for each bucket priced whether or not it trades, and buys the cheaper side
only when the edge after fees clears three cents. Daily resolution is the point: it is the
fastest source of scored decisions the loop can get.

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
`ops.budget` (one event per change of mode, cap, dollar of balance or spend, or day of runway) and in the
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
* The fees are the ones the account really pays, not a hopeful tier. Coinbase is 0.5% for a
  resting fill and 1.2% for a taker fill, what every real fill paid on Sept 16, 2026. The model
  charged 0.15% and 0.25% before, so quoting strategies that lose money after the real fee
  scored as winners, and one was promoted. On Kalshi, the 160 series that charge makers (sports
  games, the Fed, CPI) charge a shadow resting fill too, and a series' fee multiplier scales
  both sides (`ltcm/data/kalshi_fees.json`, from Kalshi's public series list).
* `broker.order`, `broker.fill` and `ledger.mark` from a shadow desk carry `shadow: true`.
* The committee's allocation for a shadow desk is a **notional scoring budget** -- the capital its
  manifest asks for -- listed under `shadow` in the `committee.allocation` payload. It is never
  drawn from the floor's capital and never counted in the floor's equity: `floor_totals(...,
  include=live_ids)` and the checkpoint's `floor` block sum the live sleeves alone.
* Reconciliation never compares a shadow book against a venue, and the floor's daily-loss breaker
  cannot be tripped by a hypothetical loss.

Two firm rules bind every desk, shadow and live, before any other limit (`event_rules` in
`ltcm/config.json`, `risk.rule_event_longshot` and `risk.rule_event_market_cap`):

* **No longshots.** No desk opens a position in an event contract priced under 15 cents. People
  who buy Kalshi longshots lose money: makers who bought at 10 cents or less lost 0.9 to 6.7 cents
  a contract across 1,054 program-days. The floor's own 1-3 cent weather tails lost most of their
  cost in a day. The rule tells the desk to take the other side instead. Exits are never refused.
* **No single market is a big bet.** What one Kalshi market can cost a desk includes both legs
  held at cost, its resting buys there, and the new order. That total is capped at 15% of the
  desk's equity. On real money it is also capped at 3.5% of the live floor. On Sept 16, 2026 one
  discretionary Fed position held 8% of the firm.

Promotion needs two things and publishes both: the gate's evidence, and an open venue. A desk that
passes gate A onto a venue missing from `live_venues` is deferred with a public `committee.gate`
whose reason is `venue not enabled`; the next run after the venue opens promotes it on the same
evidence. Children of a live desk are born shadow.

### The learning policy

The first day on the box produced 49 sessions, 80 recorded forecasts and 3 orders: the desks did
the work and then passed, because a mandate gates full size on an ex-ante edge the models rarely
see, and a floor that never decides has nothing to post-mortem, calibrate, breed or promote. The
desk header (`desk.header_for`, numbers from `config.json` `learning`) therefore asks for a
decision every session:

* A **shadow desk** ends every session with its best-ranked idea on the book at learning size
  (`shadow_notional_usd`, $15), taking the price so it fills, with the forecast recorded and the
  exit set. A mature shadow desk with no decisions is retired as a dud (`evolution.min_days`, now
  one day).
* A **live desk** trades in two sizes: a learning position (`live_kalshi_usd` $10,
  `live_coinbase_usd` $25, at most `live_orders_per_day` a day) on its best idea whenever its own
  number says the expected value after fees is not negative, and a full, edge-sized position only
  when the mandate's threshold is cleared. The risk engine's limits and the gateway's caps bind
  either way.
* Orders on Kalshi and Coinbase rest until filled or cancelled (`gtc`), as they do at the venue; a
  "day" order used to die at UTC midnight in the shadow book alone. The limit-sanity rule judges an
  event contract in cents through the touch (five), not as a percentage of a penny reference.

### Strategies: code that trades between sessions

A model session is the slow, expensive, cautious way to make a decision. A **strategy** is the
desk's judgement as code: a toolbox module with `decide(kit, params) -> list of order dicts`,
deployed with the `deploy_strategy` tool, which `ltcm/strategies.py` runs every
`cadence_seconds` in the desk's sandbox and whose limit orders it proposes through the same
risk engine (and, for a live desk, the same critic) under a session id of the form
`<desk>:<stamp>:strategy:<name>`. Every run that proposes or fails is a public `desk.code_run`
(purpose `strategy <name>`), idle runs once an hour; the orders are ordinary intents, decisions,
orders and fills. `kit` reads bars, quotes, `kalshi_series` and `kalshi_market`, and
`kit.context` carries the clock, the desk's positions and its learning size. A live desk's
strategy orders are capped at the learning size; `config.json` `strategies` bounds the rest
(three per desk, five intents a run, two runs a tick, a 300-second floor on the cadence, the
sandbox's daily fuse). Desks of the `ranges` and `crypto` families that have no strategy get the
house starters in `ltcm/starters/` (hourly range pricing from realized volatility; hourly mean
reversion), exactly as bred desks get the house playbook: the desk owns the file from then on.
The state lives in `.data/ltcm/strategies.json`.

A strategy may also return `cancels`, a list of its own resting order ids (a strategy can never
cancel another strategy's or a session's order), and `kit.context["open_orders"]` names each
resting order's strategy, so a strategy can quote and replace. The ranges family's second house
starter, `hourly_quotes`, rests a YES bid and a NO bid a spread under fair value on the buckets
nearest spot and replaces them as fair drifts: the maker side of the market the first starter
takes. The weather family's starter, `daily_temps`, prices the daily high-temperature markets
from the NWS forecast through `kit.weather(city)`. Shadow desks of a family are dealt different
house params round-robin by desk id (`STARTER_VARIANTS`), so siblings compare settings on the
same markets at the same hours; the live desk keeps the code's defaults. House params, cadence
and code follow the repo until the desk edits its copy or redeploys it as its own.
`strategy_report` carries each strategy's record from the tape: fills, fees, and the settled
P&L of the positions it opened (attributed by the `[strategy <name>]` prefix on its rationales).

### Promotion: the family's record chooses the live desk's settings

`Strategies.promote` runs once an hour (`config.json` `promotion`, defaults in
`strategies.PROMOTION`). For every house strategy a live desk runs it scores each shadow
variant of that strategy in the family on settled P&L per dollar of filled notional since the
variant was last dealt (`record(..., since=)`), and the live desk's own setting the same way.
When the best variant has at least `min_settled` (12) settlements, a positive return and a
`min_margin` (0.01) over the live setting, the live desk adopts its params; the winning shadow
keeps them as the control; every other shadow is dealt a jittered copy (`_jitter_params`,
numbers moved by up to a quarter, choices kept) so the search continues around the new best.
A promotion is a `desk.code_run` on the live desk ("strategy X promoted: Y's settings take
the live desk") and an `ops.alert`. `bootstrap` never overwrites a promoted or dealt setting
(`promoted_at`); only an untouched house row follows the house params.

### Backtests

`ltcm/backtest.py` replays a strategy's `decide(kit, params)` over past days in minutes instead
of waiting for settlements: `run_backtest(spec)` steps a clock every `step_minutes`, answers every
`Kit` call from `ltcm/history.py` as of that moment (settled Kalshi markets open then, priced from
the last candlestick that had ended, listed at the close they showed while open; Coinbase bars
that had closed), and books intents in a conservative simulator: takers pay the ask and Kalshi's
fee, resting bids fill at their limit only on a later candle that trades strictly through them
(minute candles are fetched once an order rests), post-only crossings are refused, positions
settle at close, notional is capped at 10x learning size. `fill_model: "touch"` also fills on a
touch or a print: the optimistic bracket for a maker. The report carries trades, P&L, fees,
return on notional, drawdown, daily P&L, per-trade P&L with a seeded bootstrap CI and its
`split_report` in and out of sample. Weather is unsupported (no forecast history). Run it with
`python3 scripts/backtest.py --strategy kalshi_favorites --days 3`, or in a desk's sandbox with
`python3 -m ltcm.backtest --spec spec.json` (one `BACKTEST-RESULT` line, printed whatever the
strategy raises; `compact` fits the sandbox's 4,000 characters and silences everything else).
Reads back off on 429s and cache settled data under 128 MB, a cap shared by every process on the
directory (`flock`).

What keeps the replay honest (the Sept 16 review): nothing picks markets by what a settled row
knows only after the close; a capped listing (`max_markets`) is a seeded draw spread over events,
since the winning bucket of a busy event is the one that traded most by its end. Settled markets
are listed through `end + listing_horizon_hours` (48) and no later than `settle_lag_hours` (24)
before the run, and one listed to close past that is hidden even if it closed early, so the board
near `end` does not favour early closes; a window that ends near now thins toward its end, so the
full board needs a window ending about three days back. A taker is never filled against an hourly
close more than five minutes old (minute candles are fetched first). The strategy gets a facade
kit with no path to the history, and its code must pass `check_code` (safe imports, no
underscore attributes); code a person did not write runs only in a desk's sandbox
(`run_backtest(..., trusted_code=True)` is for your own). `max_seconds` bounds loading too (540 by
default in a sandbox, under its 600-second kill); a run cut while loading replays nothing and says
`incomplete`, and a second run continues from the warm cache. Biases left: trade-through fills are
the adverse ones (maker P&L reads low, `touch` reads high); a capped board shows each strategy a
sample, so trade counts scale with the sampled share; an early close is recognised by its
off-minute timestamp.

### The floor board

Every session's user turn carries `# The floor board`: the newest memo of every other desk
from the last day (`DeskContext.floor_board`), framed as evidence about their markets, never
orders. It is how a weather desk hears what the crypto desk sees, and how a shadow child
hears its parent, without a shared memory that would make them converge.

### The lab writes code

A lab experiment's change may carry `strategy {name, cadence_seconds, params, code}`. The
lab's instructions describe the strategy kit (`lab.KIT_API`) and its packet shows the family's
strategy records and the house strategy's source, so a proposal starts from the code that runs
today. Validation (`validate_change`): `decide(kit, params)` present, no process or network
access, at most `strategy_code_chars` (6000), cadence inside `strategy_cadence_seconds`. The
service installs the code on the variant once its manifest is loaded
(`_install_experiment_strategies` -> `Strategies.install`). An adopted experiment puts the
strategy in the family's genome, and `bootstrap` installs genome strategies on every desk of
the family, the live desk included (`_genome_strategies`). The checkpoint carries a strategy
change as name, cadence, params, code digest and length (`publish.public_change`): the site
caps a change at 4 KB; the code is on the tape in the `lab.experiment` event.

### Collateral and the disk

`Service._fund_kalshi_shards` (hourly, `config.json` `kalshi_shards`) reads the cash per Kalshi
exchange shard and moves `top_up_usd` to any traded shard under `floor_usd` from the richest
shard that keeps `keep_usd`; every move is an `ops.alert`. `Service._disk_check` (every ten
minutes, `config.json` `disk`) trims the HTTP cache under `warn_gb` and files a warning, and
under `stop_gb` files an error and posts a `disk_low` notice the gateway mails. The HTTP cache
(`data.HttpTransport`) is capped at `cache_cap_bytes` (256 MB) and trimmed every fifty stores;
on Sept 16, 2026 it had filled a 32 GiB disk because the event-index sweep put the raw clock
in every listing URL.

### The loop closes on itself

The audit of Sept 16, 2026 found the places where the self-improvement loop still needed a
person, and closed them:

* **A promotion is live everywhere.** `Service._apply_capital_modes` (on start and after
  every `reload_manifests`) rewrites a promoted desk's frozen manifest in memory to
  `capital_mode "live"`, so starter params, learning size, order caps and the session prompt
  all see the desk the way the gateway already did. Before, `manifest.live` stayed False
  after a promotion and shadow settings controlled real money until a restart.
* **A bred child trades from its first tick.** `Strategies.tick` bootstraps every desk it
  has not seen (`_bootstrapped_ids`), not just the roster at start.
* **A spot position is scored when it is sold.** `Gateway._score_reduction` writes
  `desk.outcome` (result `sold`, entry at the ledger's average cost, exit at the fill, the
  fee taken) for a sell that reduces a non-event position, so crypto strategies earn the
  settled record that sizes them up and promotes them. Settlement remains the event path.
* **The recent tape, not the first ten thousand rows.** `EventLog.read(newest=True)` returns
  the last `limit` events, oldest first; every state-folding read uses it (promotions,
  retirements, breakers, reconciliations, spend, fills, intents, experiments, records).
* **The evolution loop judges with the committee's gates** (`config.json` `committee` is
  passed to `Evolution`), an event contract is never time-stopped (it settles), the feeds
  follow the markets the desks are quoting as well as the ones they hold, the quoting
  starter does not re-quote a leg that filled, and an outcome's sentence comes from an
  accepted intent, never a refused one. Kalshi orders carry no `reduce_only`, and a `day`
  time-in-force maps to GTC (the floor's exits bound a resting order).

What still needs a person (Sept 16, 2026, evening): code and deploys, credentials and venue
deposits, Sail credit, enabling Coinbase derivatives on the account (`cfm/balance_summary` is
null), and the four human founders' manifests. Everything else runs without one: the floor
founds and winds down its own families (`ltcm/founding.py`), the ranges starter prices every
Kalshi crypto series with a Coinbase reference and the weather starter every Kalshi city,
strategy orders and session learning sizes fit each desk's limits at its equity, capital is
resized daily, compute follows P&L per Sail dollar, and every session reads the standings and
the other partners' open probabilities.

### The firm founds families

`ltcm/founding.py` lets the floor open a line of business itself. Once a day after `founding.founding_time`
(21:30 New York, after the evolution run), `Service._founding_tick` reads the floor's coverage on the tick
(each family's venues, asset classes, the Kalshi series and Coinbase products its desks filled or proposed
in 30 days, its best score and P&L) and hands a worker the rest: a digest of the venues of at most 6 KB
(Kalshi's open markets by category and series, ranked by dollar volume, combos left out; Coinbase's USD
spot products by 24h dollar volume) and one call to `founding.profile` (Kimi K3, high effort). The model
answers with a family, an id, a rationale, its targets, a manifest in the founders' shape and a playbook
that opens with an `## Edge thesis`. `Founding.validate` refuses, with the reason in one `ops.alert`: a
name already used (parked desks included), a target the floor already trades or the venues do not list,
a venue outside `live_venues`, a tool no human founder carries, a limit outside `lab.hard_limits`, any
capital mode but shadow or more than `founding.capital_usd`, sessions under 30 minutes apart, a playbook
over 12 KB. A valid family is written like a spawned child (generation 1, no parent), published as
`evolution.founded`, and loaded by `reload_manifests` on the same tick; `seed` breeds its variants and
only the committee's gates can promote one. Caps: one founding in 24 hours, eight active founded
families, `founding.budget_usd_per_day` of model spend. The request key is the day, so a restart pays once.

The same slot winds founded families down. A family an `evolution.founded` names, and never one with a
human founder in it, is retired whole (`evolution.retired`, reason "founded family wound down") when no
desk is live, it is `min_days` old, and its best desk with `min_decisions` has `min_days` behind it and a
cost-adjusted excess below `retire_below` percent; or when after `idle_days` (10) no desk has reached
`min_decisions`. By hand: `scripts/found_family.py --packet | --dry-run | --apply`, `--wind-down [--apply]`.

### Keeping the tick's clock

The tick is the floor's heartbeat: stops, targets, marks, order polls and strategy dispatch all
wait on it. Everything slow runs beside it. Desk sessions run on their own threads; strategy
runs go to a pool (`strategies.parallel_runs`, one run per desk, each desk on its own Sail
sandbox); the night watch's model calls, the Kalshi index warm-up, the lab's night and the
committee memo run on single named workers (`Service._off_tick`, `background_work`) whose
results the next tick picks up; trade notices read from a log cursor (`notify_seq`); settlement
sweeps run every `settlement_interval_seconds`; strategy records share one order-and-fill index
for `strategies.record_cache_seconds`. Each tick writes the step it is in to
`.data/ltcm/tick-phase.json` and the seconds each step took to `health.json` `last_tick.timing`,
so a slow tick names its own culprit. On Sept 16, 2026 this took the tick from 4 to 10 minutes
to about 30 seconds.

### The Foundry: an evidence loop every half hour

`ltcm/foundry.py` replaces days of waiting (twelve settlements, three-day gates, one lab night) with a
cycle every `foundry.interval_minutes` (30) off the tick (`Service._foundry_tick`, worker `foundry`,
`last_foundry_at`; state in `.data/ltcm/foundry.json`). A cycle takes the next family of `families`
(kalshi, ranges, crypto; weather has no forecast history) and the next of its strategies (house starter,
then what the live desk runs):
1. **Candidates.** Baselines are the live settings and the best shadow's. `param_candidates` (10) jitter
   the best-known settings 10-50%, seeded by the cycle, every other one flipping a `STARTER_VARIANTS`
   choice. `code_candidates` (2) come from `profile` (K3, high, 16,000 tokens, $25 a day on desk
   `foundry`) and must pass the lab's `validate_change`, compile, and `check_strategy_code` (imports from
   `SAFE_MODULES` only; no underscore attributes, attribute assignment, computed `getattr`, `str.format`,
   frames or re-exported modules: a candidate runs inside the engine's process). `frozen_params` never
   move, in params or in a candidate's own `DEFAULTS`; deployments and adoptions pin the parent's values.
2. **Backtests side by side**, one per sandbox `foundry-0..7` (own fuse, 900 s cap via
   `SandboxManager.set_limits`): the runner calls `ltcm.backtest.run_backtest` with a History paced at
   0.15 s times the sandbox count (`history_min_interval`), and prints one compact line under
   `BACKTEST-RESULT <token>`, a secret per run, then `os._exit`s; what a strategy prints is never read.
   `window_days` (5) to the last whole hour, `step_minutes` 15 (5 ranges). A run with engine `errors` is
   not evidence.
3. **Selection on the out-of-sample third only**: >= 25 positions, >= 60 trades, return on notional above
   the best baseline by `margin` (0.01), 95% lower bound on mean P&L above 0. Every baseline must be
   measured, or nothing qualifies and no model is asked.
4. **Shadow at once**: the worst shadow desk (settled P&L, then equity; one still proving a candidate for
   `protect_hours` is spared) gets the params (`promoted_at`, `foundry_id`; only a desk running the
   backtested code) or the code (`Strategies.install`). Never a live desk.
5. **Live**: a positive backtest bound and `min_forward_settled` (5) positions opened since deployment
   and settled (`Strategies.record(opened_since=True)`), as many fills, P&L after fees >= 0, and the live
   desk adopts it (params as `Strategies.promote` does; code installed, its parent and anything else of
   its line paused). Superseded instead when the live desk's code is not what was measured (its own
   strategy, the parent, a snapshot's file) or the parent is already paused. Never under the kill
   switch; sizes, limits, capital unchanged; unproven in 72 h, expired. `Strategies.promote` leaves a
   Foundry adoption until the live desk has its own record and does not re-deal a Foundry trial for
   `promotion.foundry_hold_hours` (72).
Tape: a `lab.hypothesis` per cycle (`foundry-<n>`), a `desk.code_run` per deployment or adoption, an
`ops.alert` per adoption. `health.json` carries `last_foundry`.

### The Firm Mind

What one desk learns, every desk inherits (`ltcm/mind.py`, config `mind`). A rule is a filter
(series prefix, family, strategy, leg, entry band, held hours, real money, venue) and a direction
(avoid or prefer), scored in code on the newest 10,000 `desk.outcome` events of every desk: n counts
independent positions (every desk, leg and strike of one Kalshi event is one draw; the partial sells
of one spot position are one), each position's return is its P&L net of entry fees per dollar of
entry, and the score is their mean with a seeded bootstrap interval (normal above 300 positions) plus,
for settled contracts, an exact binomial test of wins against the break-even count. A score needs
n >= `min_n` (15), 3 winning and 3 losing positions and an interval with width that excludes zero in
the rule's direction.

Every hour, on the `mind` worker and under `mind.json.lock`, a pass splits the tape by log order. It
re-scores each book rule on the outcomes newer than what its proposer read, retiring it when that
interval no longer excludes zero or when 15 positions closed since its admission average the wrong
side of zero. When the tape moved and the held-out part could admit anything, one `k3` call (budget
desk `mind`, $8 a day held by the mind's own tally, which books the estimate before the call and keeps
it if the call fails; the provider's per-desk figure is the floor's desk fuse, not this) reads a packet
built from the older 70% only (the aggregate table, the book, retirements, lessons written before the
held-out outcomes) and proposes up to eight rules. Each is admitted only on the newest 30% alone, at
99.375% (the eight share 5%), with the older part agreeing in sign; a near-duplicate of an active rule
(80% the same trades) is refused, and a retired filter is tested only on outcomes after its
retirement. The book keeps `max_rules` (12), ranked by the interval's bound nearest zero x sqrt(n).
Every session prompt carries the rules that apply to the desk under "# What the firm has learned"
(`DeskContext.firm_rules`), the lab's packet carries the family's, and
`mind.rules_for_family(family)` renders the same block for any strategy generator: evidence, not
instructions, one line per rule written by code from its filter and numbers (the model's statement
stays on the public record only). Each pass publishes a `lab.hypothesis`; a changed book publishes a
`lab.result` with the evidence. By hand, on the box (`cd /workspace`):
`.venv/bin/python scripts/mind_pass.py --dry-run` prints the table and the book re-scored, read-only;
`--dry-run --ask` adds one model call and scores its proposals without writing rules or the log (its
cost joins the book's spend tally); `--apply` runs a full pass now: writes the book, publishes, and the
floor reads it next session. `--ask` and `--apply` refuse while the floor's pass holds the lock.

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
with `{hypothesis_id: "daily-<date>", metrics, verdict}`. `metrics` is `{window, floor,
profiles{<name>}, desks{<id>}, by_generation[]}` of string values, capped at 20 KB and at the
site's hundred keys per object (a day that shed detail says `truncated: "true"`; the quietest
desks go first); `verdict` is one sentence a human can read without opening it. The service
writes it from the tick:

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
