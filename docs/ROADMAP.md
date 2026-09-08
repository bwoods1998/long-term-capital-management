# Portfolio Agent roadmap

This is a staged plan, not a list of capabilities already implemented. A new stage starts only after the previous stage has usable evidence. No launch dates or profit targets are assumed.

## 0. Measured extraction — working

- A sourced financial table and local answer key.
- A single bounded Sail request, persistent budget allowance, and restart-safe retrieval.
- Correctness, token accounting, estimated expense, and six offline tests.

Read Lesson 1 and explain the first result before expanding the workload. Next evaluation work includes controlled synthetic changes and unfamiliar held-out documents.

## 1. Know the account — next

Privately connect to one owner-selected Schwab account for balances, holdings, transactions, and orders, subject to its approved API capabilities. Use a dedicated connector that exposes only reads at this stage; do not assume the token itself is technically read-only.

Store normalized snapshots with timestamps, units, and provenance. Reconcile cash and positions against the owner's brokerage view. Make missing, stale, or incomplete data explicit. Inspect authentication expiry and reauthorization requirements in current account-accessible documentation.

Done when we can reproduce a dated portfolio snapshot and explain every discrepancy. No live order submission, public raw snapshots, or research-agent access to credentials.

**Tomorrow's first session:** review the existing extraction lesson; map holdings, cash, transactions, orders, and fills; inspect the Schwab app's permissions and documentation; then build a mocked read-only connector before using real credentials. Enter any future secret through a private terminal prompt.

## 2. Maintain one thesis

Choose one holding or watchlist instrument. Save its thesis, evidence, assumptions, open questions, invalidation conditions, and next review event. New evidence creates a new version rather than overwriting the record.

Done when the agent can resume its work in a new process, cite source passages, distinguish observation from interpretation, and explain what changed. It may recommend holding cash or taking no action.

## 3. Research across time

Add a durable task queue and checkpointed investigations. Introduce Sailboxes when isolated calculation or persistent execution is needed, Voyages when multi-step traces become useful, and completion-window comparisons on the same workload. Each investigation has a budget and a clear stopping condition.

Done when a deliberately interrupted assignment resumes without repeating paid work, losing evidence, or silently claiming completion. Measure end-to-end cost, quality, latency, and owner interventions. Sleeping between events is part of persistence; continuous token generation is not the objective.

## 4. Simulated execution and public replay

Translate a thesis into structured proposed orders. Compare with a declared baseline in a clearly labeled simulator, including fill assumptions, transaction costs, deposits, and corporate actions as applicable. Exercise rejections, partial fills, ambiguous submissions, and duplicate commands with fixtures.

Build a separate public read model: selected thesis summaries, decision history, quality measures, and operating costs. Confirm data-display rights before publishing prices or account-derived metrics. Distinguish simulations from real results and from the website's fictional $WOODS exchange.

Done when a visitor can follow a historical decision, while public requests have no route to the brokerage or an unbounded inference budget.

## 5. Owner-approved live execution

Define the account, allowed instruments, cash constraints, maximum exposure, order size/frequency, and permitted order types. Approvals bind to an exact order proposal and expire. Recheck current state before placement. Keep order and fill reconciliation separate from the research agent.

Done when controlled small live orders reconcile correctly and uncertain outcomes stop new execution. Stopping new orders, cancelling open orders, and liquidating positions are separate controls. Strong owner authentication is required.

## 6. Bounded autonomy — optional later

The owner may explicitly authorize a versioned mandate after reviewing simulation and execution evidence. A deterministic service enforces it. The agent cannot enlarge its own authority, change risk limits, deploy code, or expose secrets. Strategy versions retain prospective results; no rewriting losing histories.

Explore whether additional research improves measurable decisions at acceptable cost. Fine-tuning is optional and follows a robust evaluation dataset; a small portfolio's noisy returns are not sufficient training evidence.

## Measures of progress

- Engineering: recovery correctness, stale-data detection, reconciled orders, and manual interventions.
- Research: factual accuracy, source support, hypothesis revisions, and cost per accepted result.
- Economics: inference and execution expenses, incremental value of extra research, and modeled infrastructure costs.
- Portfolio: cash-flow-adjusted performance, a declared benchmark, drawdown, turnover, and separately recorded project expenses. Investment returns alone do not establish agent skill.
