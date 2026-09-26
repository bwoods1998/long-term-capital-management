# The options House, Gym and swarm

One account, one options game, and an honest record of returns and costs. Researchers learn in accelerated market time from recorded quotes. Live results decide whether that learning survives execution, fees and changing conditions.

## Processes and state

The House performs short ticks. It owns the hash-chained `ledger.sqlite`, the owner grant handle, public checkpoint publication and supervised jobs. `OptionsLive` reconciles the venue and routes every shadow, paper and real option action. The swarm is a separate process with `swarm.sqlite`, a private program store and notebooks. The optional data daemon has its own lifetime lock and heartbeat. Neither a slow researcher nor an image build blocks a House tick.

The service builds this composition directly. It does not construct a second legacy book, roster, campaign store or researcher alongside it. PAUSE closes admission to new work while the existing live path continues reconciliation and exits. A hard STOP ends the loop; it is not a way to keep exits running.

| Earlier responsibility | Current owner |
|---|---|
| `book`, `options_shadow`, simulation | `live.real`, `live.shadow`, `gym.engine` |
| Allocator, capital ladder, evaluator, families, auditor | `live.money` and swarm bands, evidence, gate and store |
| Researcher, commons, admissions, research jobs, credits | `swarm` family budgets, private programs and tournament |
| Old runner, replay, options history and sandbox | Gym runtime/driver plus the live decider |
| Campaign grant and risk policy | `live_trading.LiveGrant`, constitution and gateway |
| Budget and pacer | Swarm guard and externally funded gateway caps |
| Needed `ltcm` broker, calendar, provider, Sail, funding readers | Focused modules under `league`; no legacy package import |

The source survey in the archived goal predates these new components. These replacements retain the current tested behavior; the old keep list is not a requirement to run duplicate engines.

## Data separation

| Window | Sessions | Access |
|---|---|---|
| Train | 2022-01-03 through 2024-12-31 | Researchers may inspect results and revise |
| Validation | 2025-01-02 through 2025-12-31 | Counted selection evidence |
| Holdout | 2026-01-02 through 2026-09-25 | Sealed gate only, bounded lineage looks |
| Forward | Sessions after the run's cutoff | Nightly replay and observed live outcomes |

The data box ingests licensed option NBBO and trade/quote samples with explicit coverage journals. It alone holds the ThetaData credential. A single vendor session and a remote lease serialize backfill, SIP ingestion, image publication and checkpoint operations. Missing coverage is a failed or incomplete job, not an empty profitable day.

A trusted House relay requests underlying SIP OHLCV through its gateway token and uploads only the bar payload. Start-stamped bars become completed-minute bars before programs can observe them. ETF and stock histories use raw prices and the historical symbol mapping. This relay never gives a data box the token. Index roots keep their dedicated underlying source.

The Gym image contains Train and Validation, no gate marker or holdout. The gate image has its capability marker and holdout/forward days, and is inaccessible to researcher data tools. Both images have `no_network` and no credentials. Images are verified and checkpointed twice before readiness is published. Changing a data checkpoint, engine bundle or model creates a new evidence identity; old results cannot stand in for a run against the new identity.

## Programs and fills

The [contract](../league/CONTRACT.md) defines `NEEDS`, `PARAMS` and `decide(ctx)`. Programs see minute, weekday and events, not calendar dates or years. They can use approved math/numpy operations, not files, network, clocks or process APIs. The runtime bounds errors and CPU time. Programs, fitted parameters and raw data stay private.

One signed structure value represents both debits and credits. Sizing includes maximum loss and round-trip fees. The same leg resolution and price conventions serve Gym, live shadow and real intents. Real P&L always comes from venue fills and marked remaining inventory; the fill model does not invent real fills.

Passive-fill calibration uses Train-only `trade_quote` samples on the sealed Gym. Exposure includes sampled NBBO contracts with zero valid prints; conditioning exposure on printed contracts would bias fills upward. The fitted artifact is private. Calibration receipts contain only identity and aggregate sample counts. Gym, Validation, gate and the live shadow path must use the same model version. The live service loads that model on construction, so changing it requires a controlled restart. Paper fills prove the route and are never calibration observations.

## Evidence and capital

A family identifies a mechanism, structure and universe slice. The swarm begins with unfitted mechanisms and counts every distinct program/parameter trial, including failed ones. It retains lineage identity and validation attempts. Evidence checks include support, diversity, trial adjustment and controls; the gate reserves its bounded look before using the holdout. Failed/no-data forward jobs remain retryable and cannot be recorded as successful evidence.

A Candidate trades live shadow. A Probe needs the gate and all current route, account and grant checks. Sized requires its forward evidence and real Probe experience; a restart or a new program version cannot inherit those receipts. Deteriorating evidence demotes a family while existing positions remain exit-owned. The paper account proves an actual same-session multi-leg open and close with broker reconciliation and position witnesses. Ambiguous, partial or recovered inventory cannot silently pass it.

`constitution.options_money` is the authoritative money table. The live grant pins its money digest and ratified capital, capped by the owner's ceiling. Live and gateway limits size by maximum loss, apply credit eligibility and limit requests/orders. Daily and drawdown stops net out executed funding flows. A deposit changes funding, never profit. A changed digest requires owner ratification before new real entries.

Unknown orders retain stable client IDs and reservations until reconciliation resolves them. A transport timeout is not a refusal or permission to submit another order. Closing orders retain a route through admission stops. Held assigned shares may be reduced; speculative stock, crypto and event trading have no route.

## Public record and repair authority

Schema-2 checkpoints expose allowlisted account, funding, cost, Gym, agent and structure summaries. Optional `trading: {as_of, pnl_usd}` aggregates the complete real-options book in a read-only transaction, independent of the public roster. Fees and partial closes are included. The mark uses copied quotes and database position quantities, with accounting and quote revision checks. Frozen, broken, unknown or unpriced state produces `null`. A missing book is zero only when the ledger proves no real option fill.

Private prompts, quotes, source programs, tuned parameters, credentials and fitted fill tables never enter the site. `league/tests/fixtures/site_*.json` are synthetic contract fixtures, not performance results.

Public repair proposals may touch only pure `league/tools/` helpers and their tests. Private strategy reports stay with the swarm. Money code, judges, runtime, data and operator tools require owner review. CI uses read-only tokens and never merges. The in-box updater defaults off; owner releases pass an isolated synthetic canary and a rollback watch.
