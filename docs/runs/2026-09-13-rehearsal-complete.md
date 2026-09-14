# Completed rehearsal · September 13, 2026

**The five-hour cloud rehearsal settled cleanly. It exposed research and accounting gaps that needed correction before the paper week.** The final hour completed 144 of 144 requests. Earlier interruptions remain part of the record.

The same service is scheduled for **Sunday September 13, 9 p.m. through Friday September 18, 9 p.m. Pacific**. The objective is an autonomous S&P 500 stock portfolio measured against the **S&P 500 Total Return Index**. Brokerage execution remains disabled.

At **6:47 p.m. Pacific**, final verification found the updated host sleeping, the supervisor unpaused with zero current failures, and the original 9 p.m. wake armed. The public checkpoint showed the expected scheduled wait.

## What finished

| Measure | Reconciled result |
|---|---:|
| Accepted requests | 401 |
| Completed responses | 388 |
| Incomplete responses | 13, all output-limit stops |
| Recorded inference cost | $17.046332130 |
| Pending requests / unknown costs / duplicate accepted IDs | 0 / 0 / 0 |
| Company reviews / distinct companies / source-checked companies | 222 / 125 / 123 |
| Allocation reviews / K3 critics | 16 / 16 |
| Delivered Voyage events / undelivered events | 273 / 0 |

These are operational and source-grounding measurements, not investment success rates. All five hourly sessions closed, but one admitted no requests because of the credit bug corrected during the rehearsal. The [earlier audit](2026-09-13-rehearsal-audit.md) preserves that interruption and its fixes. The final two sessions completed 269 of 272 requests and recorded $9.516091662 in inference cost.

The completion marker at **5:45:11 p.m. Pacific**, settled request journals and accepted completion email agree. The original paper account still has **$100,000 virtual cash**, no fills and no measured investment return. Its final pending allocation targets **22 stocks, 64% invested and 36% cash**, with the first possible fill at Monday's observed opening. A subsequent review reaffirmed those targets without replacing the pending order.

## What changed for the week

- **Allocation evidence:** company-level prices and filing facts were not consistently reaching the portfolio decision. New allocation packets carry dated quotes and compact primary financial observations for candidates and existing positions; the critic receives the same evidence. Every new target needs a checked filing claim. Historical request bodies and grades remain unchanged.
- **Coverage:** a changed quote could reset a company's apparent research coverage. Unreviewed companies now keep priority while changed-price valuation follow-ups remain possible. The website counts distinct current constituents with retained source-checked reviews, rather than resetting each hour. This describes research history, not freshness of every company's filings.
- **Dividends:** ordinary cash dividends previously triggered an unsupported-action stop. The paper ledger now recognizes sourced ex-date entitlements as receivables, based on actual pre-ex-date simulated holdings. Receivables affect returns but cannot fund purchases. Payment still requires separate dated evidence; splits, large distributions and ambiguous actions remain blocked.
- **Alerts:** repeated reports of one service failure send one notice. After an observed recovery, a later recurrence can notify again; ambiguous email delivery remains protected against automatic duplicates.
- **Recovery:** the last routine snapshot predated completion by 26 minutes. The supervisor now requires a backup requested after the rehearsal completion marker before it sleeps until the week starts.
- **Experiment continuity:** a live restart caught a policy-evaluator fingerprint mismatch that fresh-journal tests did not expose. The allocation checks were separated from the original company grader, preserving the frozen policy experiment instead of rewriting its contract or results.

Dividend accounting matters immediately: AMETEK, a pending holding, declared a $0.34 dividend with a September 15 record date and September 30 payment date. The adapter uses the provider's observed ex-date, not a guessed date from the declaration. [AMETEK announcement](https://www.ametek.com/newsroom/news/investor/2026/august/ametek-declares-quarterly-dividend), [SEC investor explanation of ex-dates](https://www.investor.gov/introduction-investing/investing-basics/glossary/ex-dividend-dates-when-are-you-entitled-stock-and).

An isolated live check of the revised prompts completed **two additional Sail requests for $0.58885764**. The allocator proposed 21 targets with 23 verified filing claims; K3 approved the exact proposal with five checked claims. The 395 KB allocation and 403 KB critic requests both fit their limits. These diagnostic results did not change the public portfolio, rehearsal counters, outcome history or policy. They establish that the revised evidence path works, not that the proposed investments will outperform.

The diagnostic used supplied prices and correctly compared Microsoft's annual capital spending with operating cash flow. It also overlooked some supplied interim facts, mislabeled one fiscal quarter and left position sizing largely qualitative. Exact numerical source checks do not establish that every sentence or investment judgment is correct; critic approval is not an independent proof of quality.

## What Sail's experiments showed

One Supercache write stored **83,968 tokens**; **90 reads reused 7,557,120 tokens**. Against ordinary cached input for the same tokens, those reads saved **$0.6801408**, while the write cost **$2.93948615**. The observed net saving was therefore **negative $2.25934535**. At the same prefix size and rates, the write needs 389 useful reads within its lifetime to break even. Cache reuse worked; this sample did not establish positive cache ROI.

Across 57 descriptive memory comparisons, retained context passed source checks 54 times for $1.1581; fresh context passed 55 times for $0.7132. This sample does not support paying more for memory indiscriminately. The separate promotion experiment has seven samples toward ten planned pairs and has not promoted a policy. New completion-window comparisons finished 33/33 requests with the larger output allowance, versus 11/18 older requests; this is an operational comparison, not a controlled investment result. Delivered traces and measured completion windows do not establish which model makes better investments. That needs forward portfolio outcomes and comparable repeated trials.

## Recovery evidence and remaining limits

A fresh post-completion R2 snapshot completed at **6:02 p.m. Pacific**. An isolated restore verified **100 artifacts, 25 SQLite databases and 506 exact market receipts**, including the completed request journals and unchanged paper events. The bucket has no completed-object expiration rule. Backups are internally consistent per database; restoring trading authority still requires cross-journal reconciliation and one authorized writer.

After the final runtime restart, the **6:45 p.m.** snapshot included the healthy checkpoint and updated source manifest. All **101 artifacts** were verified, reusing 94 previously downloaded immutable objects; all 25 SQLite integrity checks passed. The 401 rehearsal request identities and costs, 17 paper events and original account configuration survived the release.

Validation passed: **330 Python tests, 55 supervisor tests and 73 website tests**. The actual Python dividend projection also passed the website's strict accounting validator. Final runtime commit [`e6b869f`](https://github.com/bwoods1998/portfolio-agent/commit/e6b869fa56d47302f58339e1f4579cf1a41d66d9) passed [GitHub CI](https://github.com/bwoods1998/portfolio-agent/actions/runs/34796819376), restarted against the production journals and published the expected waiting checkpoint with 123 retained companies. Both diagnostic grades also replay identically under this final version. The website's deployed assets match commit [`2d7b8fb`](https://github.com/bwoods1998/personal-site/commit/2d7b8fb); recurring failure alerts are in [`1a8b88c`](https://github.com/bwoods1998/portfolio-agent/commit/1a8b88c0e42edb5a246ca14f2209527c5522d6ae).

The deployment retains the original paper account, research identities, available-credit spending policy and scheduled week. No fixed inference dollar cap was added. Current credit, accepted commitments, cloud reserves and a small balance floor still control admission. Funding and service alerts are separate from the completion email.

A five-hour rehearsal cannot prove five-day uptime, predictive skill or positive research ROI. Research can continue while evidence supports useful work; identical requests are not repeated merely to increase spend. Real execution, automatic accounting for every corporate action, model training and autonomous production-code changes remain outside this release.

One display limitation remains: six historical critic entries show "unverified" because publication filtering mistakes mathematical inequalities for markup. Their private numerical checks passed. Those immutable public entries were not rewritten; the labels do not control paper execution.
