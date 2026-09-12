# Portfolio Agent roadmap

Build one useful loop, measure it, then expand its authority. These stages describe the working foundation and future experiments, without promising returns or launch dates.

## 0. Measured extraction — working

`lab.py` extracts a financial table through Sail and checks values, units, periods, and evidence. A private ledger preserves requests, budget allowances, usage, and dated results. The [first lesson](../lessons/01-first-experiment.md) explains why one passing example is not a benchmark.

## 1. One thesis with memory and a public ledger — working V1

`portfolio.py` takes a checked evidence packet, asks Sail for a bounded research draft, and saves it privately. A new invocation includes the last reviewed thesis and its evidence. Revisions are immutable; explicit review advances the current thesis. The public [research page](https://blakewoods.us/portfolio/) serves an exported snapshot of reviewed history, source facts, and estimated research expenses.

The first packet examines Microsoft's company-wide cash generation and infrastructure investment. It does not establish AI-only returns. `brokerage.py demo` separately reconciles a synthetic account, including partial fills and external funding.

This version runs when invoked locally. There is no scheduler, automatic document retrieval, or trade execution. Start with [Lesson 2](../lessons/02-thesis-with-memory.md) and the [V1 instructions](V1.md).

## 2. Know the account — private connector ready for owner verification

`schwab_connect.py` supports browser consent and a private balances-and-positions snapshot through the community SDK. Offline tests cover OAuth and failure recovery; live verification requires owner authorization and the first account read. See [setup](SCHWAB-SETUP.md) and [Lesson 3](../lessons/03-schwab-access.md). The connector blocks order requests; the registered app may carry broader permissions.

Next, verify the returned account fields and add private observations of transactions, orders, and fills as needed, using the account-accessible documentation.

Extend the synthetic accounting contract using real documented fields. Handle timestamps, freshness, settlement, income, corporate actions, and discrepancies as the supported data requires. Reconcile a dated snapshot to the brokerage view before using it in research.

Done when cash and positions can be explained and incomplete or stale data is visible. Account records stay private. Confirm display permissions separately before exporting any account-derived metrics.

## 3. Research across time

Add controlled retrieval, a durable task queue, review triggers, and checkpointed investigations. Introduce Sailboxes when isolated code execution is useful and Voyages when multistep traces help explain the work. Each assignment has a budget and a stopping condition.

Done when an interrupted investigation resumes without duplicating paid work or losing evidence, and new evidence produces an inspectable revision. Measure source support, latency, cost, and owner interventions. Sleeping between events is compatible with a persistent agent.

## 4. Compare decisions and compute budgets

Run the same assignments under different model, scheduling, and spending policies. Use held-out evidence tasks and explicit baselines. Check whether more computation improves supported conclusions enough to justify its expense.

Add a clearly labeled simulator for proposed portfolio decisions, with declared fill assumptions, fees, external cashflows, and a benchmark. Exercise partial fills, rejections, ambiguous responses, and duplicate commands before connecting any order path.

Extend the public ledger with selected decision outcomes and measured operating costs. Keep simulated and live results distinct, including from the personal site's fictional $WOODS exchange.

## 5. Owner-approved live execution

Define a narrow mandate: account, permitted instruments and order types, cash constraints, exposure, order size, and frequency. Strong owner authentication approves an exact proposal with an expiry. A separate deterministic service rechecks current state and limits before submission.

Done when small authorized orders reconcile correctly and an uncertain outcome blocks additional execution until resolved. Stopping new orders, cancelling open orders, and liquidating positions remain separate actions.

## 6. Bounded autonomy and deeper economics — optional later

An explicitly authorized, versioned mandate may eventually permit limited action. The agent cannot enlarge its authority, change risk limits, deploy code, or reveal secrets. Keep prospective results for every strategy version, including unsuccessful ones.

Use measured workloads to explore GPU throughput, utilization, capacity costs, and hypothetical provider economics. Customer API spending does not reveal Sail's internal costs or margins. Fine-tuning follows a reliable evaluation dataset; a small portfolio's noisy returns are not a sufficient training signal.

## Measures of progress

- Research: supported claims, factual accuracy, useful revisions, and cost per accepted result.
- Engineering: correct recovery, stale-data detection, reconciliation, and required interventions.
- Economics: workload expenses, forecast variance, and the incremental value of extra research.
- Portfolio, once connected: cash-flow-adjusted performance, a declared benchmark, drawdown, turnover, and separately recorded project expenses.
