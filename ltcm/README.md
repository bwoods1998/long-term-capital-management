# Long Term Capital Management runtime

`ltcm` is the second-generation runtime of this repository: a roster of autonomous
portfolio-manager **desks** that research, argue and trade across several venues, a deterministic
**risk engine** between every desk and every broker, a rules-based **committee** (the agent is
called Helm) that allocates capital by track record, an **evolution** loop that breeds and retires
desk variants on forward results, and a **publisher** that streams every thought, tool call, memo,
order, fill and mark to the public site. The first-generation `portfolio_runtime` (one S&P 500
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
| `gateway.py` | The only path from an intent to a venue: risk check, submission, fills, reconciliation, deferred-event release. |
| `sim.py` | `PaperBroker`: a venue simulator over any `MarketData` source, with the same `Broker` surface as live adapters. |
| `provider.py` | Sail Responses API client with function tools, background polling, idempotency, frozen rate card, per-request cost records and budget hooks. |
| `tools.py` | The research and action tools a desk may call, each with a JSON schema and an executor. |
| `desk.py` | The desk runtime: builds context, runs the tool-calling loop within budget, emits events, writes memory and memos, proposes orders. |
| `committee.py` | Helm: rules-based capital allocation across desks, weekly memo, promotion and demotion by the fixed gates. |
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

## Publication policy

Thoughts, tool calls, memos, marks, allocations and evolution events publish live. Order intents
and orders publish after fill or cancel. Prices shown publicly are the floor's own fills and
account-level marks, or delayed data labelled as such; licensed real-time quotes are never
republished. Published positions always match the real book, and every page carries the
position-disclosure notice.

## Migration from `portfolio_runtime`

1. Until the scheduled week completes, `portfolio_runtime` and the Sailbox bundle are frozen.
2. The Filings desk imports the research bank (dated facts, reviews, open questions) as memory.
3. `portfolio_runtime` moves to `docs/history/` with its run records; its market calendar,
   Yahoo adapter and evidence capture are ported into `ltcm/data/`.
4. Repository, package, site section and docs take the Long Term Capital Management name in one commit.
