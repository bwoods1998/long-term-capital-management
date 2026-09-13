# Portfolio Agent roadmap

Build one useful loop, measure it, then expand its authority. These stages describe the working foundation and future experiments, without promising returns or launch dates.

## 0. Measured extraction — working

`lab.py` extracts a financial table through Sail and checks values, units, periods, and evidence. A private ledger preserves requests, budget allowances, usage, and dated results. The [first lesson](../lessons/01-first-experiment.md) explains why one passing example is not a benchmark.

## 1. One thesis with memory and a public ledger — working V1

`portfolio.py` takes a checked evidence packet, asks Sail for a bounded research draft, and saves it privately. A new invocation includes the last reviewed thesis and its evidence. Revisions are immutable; explicit review advances the current thesis. The public [research page](https://blakewoods.us/portfolio/) serves an exported snapshot of reviewed history, source facts, and estimated research expenses.

The first packet examines Microsoft's company-wide cash generation and infrastructure investment. It does not establish AI-only returns. `brokerage.py demo` separately reconciles a synthetic account, including partial fills and external funding.

This version runs when invoked locally. Registered-source retrieval and a bounded assignment queue now work in the investigator described below; an always-on host and trade execution remain future work. Start with [Lesson 2](../lessons/02-thesis-with-memory.md) and the [V1 instructions](V1.md).

## 2. Know the account — private connector ready for owner verification

`schwab_connect.py` supports browser consent and a private balances-and-positions snapshot through the community SDK. Offline tests cover OAuth and failure recovery; live verification requires owner authorization and the first account read. See [setup](SCHWAB-SETUP.md) and [Lesson 3](../lessons/03-schwab-access.md). The connector blocks order requests; the registered app may carry broader permissions.

Next, verify the returned account fields and add private observations of transactions, orders, and fills as needed, using the account-accessible documentation.

Extend the synthetic accounting contract using real documented fields. Handle timestamps, freshness, settlement, income, corporate actions, and discrepancies as the supported data requires. Reconcile a dated snapshot to the brokerage view before using it in research.

Done when cash and positions can be explained and incomplete or stale data is visible. Account records stay private. Confirm display permissions separately before exporting any account-derived metrics.

## 3. Research across time — investigator working

Controlled retrieval, checkpointed investigations, exact evidence passages, deterministic calculations, hypotheses, independent critique, and explicit editorial review now work. Reviewed conclusions seed the next assignment. Voyages trace live model/tool stages. A Sailbox experiment demonstrated clean-VM validation and saved-state recovery through sleep/pause/resume. Each assignment has request, tool, budget, and deadline limits. See [Lesson 4](../lessons/04-research-loop.md).

A local [source-update inbox](SOURCE-WATCH.md) now records fresh captures, filters observed request metadata noise, and supports explicit curation. It preserves the research cache and buys no inference. A [synthetic timeline replay](TRAJECTORY-REPLAY.md) tests evolving agent beliefs, changed evidence, and recovery across real process invocations.

The [durable local queue](RESEARCH-QUEUE.md) now accepts up to two explicit assignments with frozen evidence, due times, deadlines, and at most $3 reserved per job. One controller resumes the same investigation and request identities. It neither admits source candidates automatically nor reviews or publishes completed work.

The [reviewed source handoff](SOURCE-CURATION.md) now binds each fact and commentary item to selected source versions, freezes a private bundle, and requires a separate factual approval before enqueue. An offline synthetic integration proof covers that route; the live watch has not produced a substantive financial update to use it. Existing assignments retain their old sources, and the two pilot slots remain consumed.

Next: curate an actual useful disclosure update, broaden source registration, and define a subsequent bounded queue protocol without resetting earlier history. Repeatedly reading a frozen cache does not discover a new filing. Schedule work only for a useful trigger; sleeping between events is compatible with a persistent agent.

## 4. Compare decisions and compute budgets

A three-model development regression and a separate uniform-critic comparison now measure verdicts, citation checks, abstention, and incremental cost. [Results](EVALUATION-RESULTS.md) retain errors and unknown costs. These authored cases are not held out, and model comparisons also differ in completion window. Next use harder, independently reviewed cases and matched scheduling policies to test whether more computation improves supported conclusions enough to justify its expense.

Add a clearly labeled simulator for proposed portfolio decisions, with declared fill assumptions, fees, external cashflows, and a benchmark. Exercise partial fills, rejections, ambiguous responses, and duplicate commands before connecting any order path.

An offline [performance calculator](PERFORMANCE.md) now provides the accounting foundation: exact pre/post-funding valuations, chained time-weighted returns, an aligned synthetic benchmark, and separately recorded project expenses. It does not infer real account performance or simulate an investment strategy.

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
