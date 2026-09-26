# Pre-week impact audit · September 13, 2026

**The paper week is ready for its Sunday 9 p.m. Pacific start.** This final audit improved the evidence reaching Sail's agents and the durability of the outcome-feedback loop. It did not alter the portfolio, schedule, spending policy or frozen policy experiment.

## What changed

| Rehearsal finding | Weekday behavior |
|---|---|
| Only 54 of 222 accepted company reviews included a price | Exact dated quotes persist for seven days; refreshes prioritize all held/pending names, the next research selections and allocation candidates |
| Current capital spending was missing for important companies | The parser now accepts the broader `PaymentsToAcquireProductiveAssets` tag and keeps it distinct from PP&E payments |
| A failed session could reserve an outcome without reviewing it | An outcome is complete only after a source-passed allocation and matching critic review its exact observation; failed or empty sessions retry |
| A live allocator exhausted 16,384 output tokens before returning JSON | New allocations and their dependent critics allow 32,768 output tokens; existing request bodies remain immutable |

The price migration recovered **179 exact historical quote observations**. Before the change, only **3 of the next 12** research selections and **8 of 36** checked allocation candidates had prices. Refresh priority now follows those actual queues instead of an unrelated rotation. Retained quotes preserve their original date and are never treated as execution prices.

Across the current 503-company source bank, **105 companies had a more recent productive-assets observation** than the narrower PP&E tag. The two definitions overlap and are never added. Explanatory tag labels are excluded from evidence-identity hashes, so new wording cannot masquerade as a new financial observation.

Outcome-review receipts are append-only. They require the exact recorded outcome in a settled, source-passed allocation and its matching proposal-hash critic. Approval is not required: a supported revision or abstention is also a completed review. Unfinished work keeps its original request identity; failed or empty reviews retry after one, two, four, then six hours.

## Live Sail diagnostic

Six isolated requests cost **$0.736046992** and made no paper-account or public-journal changes.

- Three focused company reviews—Nvidia, Amazon and Home Depot—used the broader capital-spending evidence correctly and passed exact source checks.
- A 16,384-token allocation spent 16,350 tokens on reasoning and ended before final JSON.
- The same input with a 32,768-token allowance completed, passed 20 exact claims and proposed a 20-stock portfolio.
- The independent K3 critic passed 11 source claims but returned **revise**. It caught a cross-company mix-up between Nvidia and Alphabet figures and a contradictory Amazon cash-flow statement.

This is the intended separation of duties: a checked final answer, followed by an exact-proposal critic that can reject an apparently valid allocation. The diagnostic establishes that the accounting evidence and larger completion window work. It does not establish investment skill or a causal benefit from the larger window.

## Final verification

The release replayed all **401 historical request identities** without changing their bodies, results or grades. The original system prompt, grader and policy evaluator remain unchanged. Local validation passed **354 Python tests**, and [GitHub's full matrix](https://github.com/bwoods1998/long-term-capital-management/actions/runs/34798845902) passed on Python 3.10 and 3.14 with Sail, Schwab and cloud-supervisor checks.

Runtime commit [`7a09032`](https://github.com/bwoods1998/long-term-capital-management/commit/7a09032d1fa1d90217cabb95356841a6eec1c277) was installed on the existing Sailbox. A fresh R2 snapshot verified **101 artifacts and 25 SQLite databases**, preserving 17 paper-ledger events, the pending 64%-stock allocation and the original account history.

At **7:26 p.m. Pacific**, the supervisor was unpaused with zero failures and no pending requests. The Sailbox was sleeping with its original **9 p.m. Sunday through 9 p.m. Friday Pacific** window armed. The public site accepted the latest checkpoint.

There are no forward portfolio outcomes yet. A review receipt proves that an agent processed supplied feedback; only an accumulating paper record can show whether decisions improve or beat the S&P 500 Total Return Index.
