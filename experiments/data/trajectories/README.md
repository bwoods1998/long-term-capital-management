# Synthetic evidence timelines

`fixtures.json` defines three fictional companies. Every amount, document, and
release date is authored for this development stress test. The accounting
distinctions are motivated by the primary-source research, but the fixtures are
not issuer statements, brokerage observations, or a historical backtest.

Each trajectory has four admitted research updates and three local gate events:
duplicate content, future-dated disclosure, and unapproved provenance. Expected
states and minimum support IDs are kept out of model prompts.

| Company | Initial cash proxy | Next-year proxy | Final event |
|---|---:|---:|---|
| Cedar Compute | 40 | 25 | Corrected cash PP&E makes the next-year proxy 55 |
| Harbor Systems | 70 | 65 | Management replaces accounting-only guidance with a planned investment cut |
| Mesa Networks | 40 | 55 | Management withdraws its outlook; historical cash flows remain |

Cash proxies are company-wide operating cash flow less cash PP&E, in USD millions.
All scenarios lack AI-only return evidence. A prospective investment plan is not a
realized cash-flow observation. See [the protocol](https://github.com/bwoods1998/portfolio-agent/blob/6b881a04bb27818c6f4d82b0a26b2422bd5ae8fd/docs/TRAJECTORY-REPLAY.md)
for model, memory, cost, recovery, and publication boundaries.
