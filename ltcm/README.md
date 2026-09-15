# Long Term Capital Management runtime

`ltcm` is the second-generation runtime of this repository: a roster of autonomous
portfolio-manager **desks** that research, argue and trade across several venues, a deterministic
**risk engine** between every desk and every broker, a second-model **critic** on every real-money
order, a rules-based **committee** (the agent is called Meriwether) that allocates capital by track
record, an **evolution** loop that breeds and retires desk variants on forward results, and a
**publisher** that streams every thought, tool call, memo, order, fill and mark to the public site. The first-generation `portfolio_runtime` (one S&P 500
paper portfolio) keeps running its scheduled week untouched; after it completes, its research bank
seeds the Filings desk and the old runtime retires into `docs/history/`.

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
| `sim.py` | `PaperBroker`: a venue simulator over any `MarketData` source, with the same `Broker` surface as live adapters. |
| `provider.py` | Sail Responses API client with function tools, background polling, idempotency, frozen rate card, per-request cost records and budget hooks. |
| `tools.py` | The research and action tools a desk may call, each with a JSON schema and an executor. |
| `desk.py` | The desk runtime: builds context, runs the tool-calling loop within budget, emits events, writes memory and memos, proposes orders. |
| `committee.py` | Meriwether: rules-based capital allocation across desks (weekly), the daily public memo, promotion and demotion by the fixed gates. |
| `evolve.py` | Variant populations per desk family: spawn, score on forward results, retire, mutate playbooks. |
| `publish.py` | Batches public events and leaderboard rows to the site API. |
| `service.py` | The always-on loop: schedule desk sessions, tick simulators, mark ledgers, run risk breakers, run the committee and evolution on their cadences, publish. |
| `adapters/` | Live venue adapters (`alpaca.py`, `kalshi.py`, `coinbase.py`, later `schwab.py`, `tastytrade.py`). |
| `data/` | Market and document sources (`yahoo.py`, `alpaca.py`, `kalshi.py`, `coinbase.py`, `edgar.py`, `news.py`). |
| `desks/` | Desk manifests (JSON). `playbooks/` at the repository root holds the versioned playbooks desks edit. |

## Streams and event kinds

Streams: `desk:<id>`, `ledger:<id>`, `risk`, `broker:<venue>`, `committee`, `evolution`, `lab`, `ops`.

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
| `desk.session_ended` | desk | yes | `session_id`, `requests`, `cost_usd`, `reason` |
| `risk.decision` | risk | yes | `intent_id`, `desk_id`, `approved`, `reasons[]` |
| `risk.review` | risk | yes | `intent_id`, `desk_id`, `verdict` (`approve` or `block`), `reason`, `model` |
| `risk.breaker` | risk | yes | `scope`, `rule`, `detail`, `action` |
| `broker.order` | broker | after fill | `order_id`, `intent_id`, `status`, `filled_quantity`, `average_price?` |
| `broker.fill` | broker | yes | `fill_id`, `order_id`, `instrument`, `side`, `quantity`, `price`, `fee` |
| `broker.reconciled` | broker | yes | `venue`, `matches`, `mismatches[]` |
| `ledger.mark` | ledger | yes | `equity`, `cash`, `positions[]`, `daily_pnl`, `as_of` |
| `committee.allocation` | committee | yes | `allocations{desk_id: usd}`, `reasons{}` |
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

## Budget policy

The floor has one daily Sail cap (`ops.budget` scope `floor`) and each desk has its own
(`manifest.budget.usd_per_day`). The provider refuses a request when either would be exceeded or
when the live Sail balance is below the floor's reserve. Unknown request costs keep their
reservation until settled, exactly as in the first generation.

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
engine remains the guardrail, and a model that cannot answer can never halt the floor. Paper desks skip it. Configured by `critic_enabled` (default true) and
`critic_profile` (default `glm_asap`, `reasoning_effort` low, 1024 output tokens), and charged to
the desk's own daily budget under the request key `critic:<intent id>`.

## Publication policy

Thoughts, tool calls, memos, marks, allocations and evolution events publish live. Order intents
and orders publish after fill or cancel. Prices shown publicly are the floor's own fills and
account-level marks, or delayed data labelled as such; licensed real-time quotes are never
republished. Published positions always match the real book, and every page carries the
position-disclosure notice.

## Migration from `portfolio_runtime`

1. Until the scheduled week completes, `portfolio_runtime` and the Sailbox bundle are frozen.
2. The filings desk (`merton`) imports the research bank -- the written case and the open questions
   for each company -- as memory: `python3 scripts/import_research_bank.py` (add `--dry-run` first).
   One entry per company, idempotent, `kind` `research`, tags `portfolio-agent` and `2026-09`.
3. `portfolio_runtime` moves to `docs/history/` with its run records; its market calendar,
   Yahoo adapter and evidence capture are ported into `ltcm/data/`.
4. Repository, package, site section and docs take the Long Term Capital Management name in one commit.
