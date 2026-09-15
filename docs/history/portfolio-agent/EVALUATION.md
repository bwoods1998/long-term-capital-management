# Evaluation

Can a persistent agent improve its investment decisions and outperform the S&P 500 Total Return Index? The feedback loop is **dated decision → paper execution → observed outcome → revised hypothesis → next decision**. More inference is useful only when it improves that process.

## Forward investment feedback

Paper returns begin with sourced observations and dated decisions. Deposits are excluded; recorded trading costs are included. Comparisons require matching total-return observations. Missing benchmark data remains missing. Research expenses are tracked separately.

`portfolio_runtime/outcomes.py` preserves original decisions and appends outcomes from actual ledger closing marks. Each executed allocation has its own cohort, ending before the next rebalance; feedback reports the latest recorded close in that interval, not a reconstructed exit price. Execution costs remain included. Unexecuted orders and future sessions produce no return. A benchmark arriving later adds a receipt without changing what an earlier review could know.

Subsequent allocation reviews receive the original thesis, targets, observed account return and matching index-relative outcome. They can investigate mistaken assumptions and propose falsifiable changes for the next decision. These are uncontrolled observations: successive closes overlap, market conditions change, and good returns can follow poor reasoning. They are not independent trials or causal attribution. **There is no outcome-trained investment policy or demonstrated investment improvement yet.**

New outcomes can trigger another investment review, regardless of whether returns were positive or negative. Reviews draw on available Sail credit; more spending does not change the evidence needed to establish improvement. A future investment-policy promotion needs a predeclared challenger, prospective comparable decisions, sufficient independent market periods and a fixed evaluator that accounts for costs. Source-extraction scores and a handful of profitable trades cannot substitute for that evidence.

Source checks are not investment skill. They cannot establish sound business reasoning, valuation completeness or forecast accuracy. Historical replay tests software behavior; it is not an out-of-sample investment record because a model may know later events. Short-term P&L never rewards a research-policy change.

## Supporting research-policy tests

`portfolio_runtime/improvement.py` compares two fixed policies: **memory_3**, which includes up to three earlier company reviews, and **fresh**, which omits them. Both arms receive the same dated company facts, question, Kimi K2.6 ASAP model, system instructions and output limit. Arm order varies deterministically by company and date. This changes context handling, not model weights.

The evaluator selects three distinct accounting metrics and periods before receiving any answer. Each result must satisfy the existing output schema, reproduce those source observations exactly, and contain no unsupported entries in its numerical claim list or allocation instruction. Confidence, persuasive prose and an agent's own score are ignored. A missing or malformed response is not a pass.

Each epoch can schedule at most four pairs, inside its existing research allowance. No prior company work means no meaningful memory comparison, so that pair is skipped. Planning saves both task identities and their exact inputs before submission; recovery cannot replace a failed arm with a different question.

Planning stops when its 20-pair cohort awaits settlement. After two complete non-improving looks, this fixed comparison stops; additional audits are not scheduled alone. Repeating the same unsuccessful experiment indefinitely is not self-improvement.

| Promotion requirement | Fixed rule |
|---|---|
| Prospective sample | 20 distinct companies across at least two evidence dates; at most ten selection pairs per date. |
| Complete comparison | Both arms have terminal responses and settled costs. Earlier unfinished pairs cannot be skipped for later winners. |
| Consistent reliability | Challenger passes at least 90%; at least five net paired wins; positive net wins on every sampled date. |
| Repeated testing | Exact one-sided paired sign test, with threshold `0.01 / (look × (look + 1))`. Each look consumes a disjoint batch. |
| Cost | Challenger's measured inference cost is no more than twice the incumbent's. |

Each evaluated batch reports both policies' source passes, actual cost, net additional passes, passes per dollar and policy cost difference. **Net additional source passes per comparison dollar** is `(challenger passes − incumbent passes) / cost of both arms`. It can be negative; zero cost gives no ratio. Unknown costs remain incomplete. These are source-handling diagnostics, not investment ROI; held-out audits never determine policy choices or spending.

The sign test assumes independent pairs. Distinct companies reduce repeated-company dependence, but shared models, accounting patterns and market conditions can still correlate errors. These thresholds are conservative engineering criteria, not a proof of general improvement.

A deterministic fifth of company symbols is reserved for **audit only**. Those paired outcomes are recorded separately and never select or roll back a policy. Trial outputs are excluded from ordinary research memory and follow-up questions. Candidates and selection rules are fixed before future evidence dates arrive.

Promotion creates an immutable policy version, applied only to the next research epoch. New dated pairs continue comparing the promoted policy with its predecessor. A qualifying forward regression rolls back to the original policy. This first implementation allows one promotion and one rollback; it cannot edit its evaluator, add policies, change funding authority, alter the portfolio mandate or modify the benchmark. Ties, missing evidence and inconclusive results preserve the current policy.

## Sail comparisons

| Capability | Question and measurement |
|---|---|
| [Completion windows](https://docs.sailresearch.com/completion-windows) | Does a longer deadline reduce cost for the same task? Record completion time, failures and actual usage. |
| [Supercache](https://docs.sailresearch.com/supercache) | Does repeated stable context repay its write charge? Include writes, reads, ordinary-cache behavior and missing usage. |
| Independent models | Which source errors or allocation assumptions survive a separate critic? Agreement is not financial truth. |
| [Sailboxes](https://docs.sailresearch.com/sailboxes) and [forks](https://docs.sailresearch.com/sailboxes-forking) | Can isolated research survive interruption without duplicated work or changed inputs? Compare scoped context on matched questions. |
| [Voyages](https://docs.sailresearch.com/voyages) | Can the recorded trace connect requests, research and recovery? Configuring a trace does not establish successful delivery. |

Window comparisons normalize only the required transport difference: ASAP runs synchronously; Balanced and Flex run in the background. Prompts, model, reasoning settings and output limits must still match. New triplets share a 16,384-token output limit; earlier truncated attempts remain in their original cohorts.

Cache economics span every epoch, counting each write charge once. Actual Supercache read tokens are also repriced against each request's frozen ordinary cached-input rate, separately from observed paired controls. This same-token counterfactual includes the write charge before reporting a net result; missing receipts prevent a complete savings claim. Conditional break-even assumes useful reads of the same still-valid prefixes, not extra requests created to recover sunk costs.

The initial fork design compares five company questions under full-universe and selected context. Its receipts must distinguish completed comparisons from proposed work; this is a bounded test, not a general conclusion about long context. Current policy changes use the stricter prospective process above. Tinker training and LoRA serving are not implemented.

Every report should separate completed work, source failures, unsettled requests, measured cost and open questions. Unknown usage retains its reservation. Cloud compute and storage require separate reconciliation. Request volume and spending are workload measures, not quality scores.

[Architecture](ARCHITECTURE.md) · [Operations](OPERATIONS.md) · [Earlier experiments](README.md)
