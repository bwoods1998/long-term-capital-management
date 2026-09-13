# Follow the AI dollar

**Where does the AI buildout turn into cash flow?**

Cloud and application companies fund capacity; chips, networks, power and cooling support it. These are overlapping economic roles, not a claim that every company below has a direct contract with another. Owning several layers may still expose a portfolio to the same spending cycle.

## The cash record

Each row is one company’s stated period, in millions of its own currency. Compare a company with its prior period in the [explorer](https://blakewoods.us/portfolio/), not by ranking this mixed-period table.

| Company / primary source | Period | Currency | Operating cash | Capital deductions | Remaining / gap |
|---|---|---|---:|---:|---:|
| [NVIDIA](https://nvidianews.nvidia.com/news/nvidia-announces-financial-results-for-second-quarter-fiscal-2027) | Q2 FY2027 | USD | 24077 | 2736 | 21341 |
| [TSMC](https://investor.tsmc.com/english/encrypt/files/encrypt_file/reports/2026-07/114aaca0fea2050e96b91fffbab9ed04ba09cd92/FS.pdf) | Q2 2026 | TWD | 783365 | 496002 | 287363 |
| [Broadcom](https://investors.broadcom.com/news-releases/news-release-details/broadcom-inc-announces-third-quarter-fiscal-year-2026-financial) | Q3 FY2026 | USD | 14197 | 532 | 13665 |
| [Constellation Energy](https://www.sec.gov/Archives/edgar/data/1168165/000186827526000104/ceg-20260630.htm) | H1 2026 | USD | 1553 | 2521 | -968 |
| [Vertiv](https://investors.vertiv.com/news/news-details/2026/Vertiv-Reports-Strong-Second-Quarter-2026-with-Diluted-EPS-Growth-of-53-Adjusted-Diluted-EPS-Growth-of-60-Raises-Full-Year-2026-Guidance-Across-All-Key-Metrics/default.aspx) | Q2 2026 | USD | 1099.8 | 174.5 | 925.3 |
| [Microsoft](https://www.microsoft.com/en-us/investor/earnings/fy-2026-q4/press-release-webcast) | FY2026 | USD | 182935 | 115948 | 66987 |
| [Amazon](https://www.sec.gov/Archives/edgar/data/1018724/000101872426000026/amzn-20260630.htm) | 12 months to Jun 2026 | USD | 161403 | 169007 | -7604 |
| [Alphabet](https://www.sec.gov/Archives/edgar/data/1652044/000165204426000066/googexhibit991q22026.htm) | Q2 2026 | USD | 39069 | 44924 | -5855 |
| [Meta Platforms](https://investor.atmeta.com/investor-news/press-release-details/2026/Meta-Reports-Second-Quarter-2026-Results/default.aspx) | Q2 2026 | USD | 31862 | 31078 | 784 |

Operating cash minus the listed capital deductions equals the remaining cash or funding gap. This is not all cash available to shareholders: acquisitions, financing and other uses may remain outside the bridge. A gap does not establish insolvency.

## What to notice

**NVDA — Cash has to catch up with sales.** Receivables and inventory can absorb cash even when sales are growing.

**TSM — Factories consume cash before they earn it.** Capacity expansion turns today’s cash into assets that must earn a return over time.

**AVGO — Low capex can still mean shared exposure.** A company can spend little on its own equipment while depending on customers’ infrastructure budgets.

**CEG — Investment can outrun operating cash.** A cash shortfall after capital spending leaves other funding sources to bridge the gap.

**VRT — Working capital changes the cash story.** Customer collections and supplier payments can move cash faster than reported earnings.

**MSFT — More operating cash. Less left over.** Operating cash grew, but cash property spending grew faster.

**AMZN — Growth can have a funding gap.** Operating cash rose while net capital spending pushed free cash flow below zero.

**GOOGL — Cash today pays for capacity tomorrow.** Quarterly capital spending exceeded operating cash, despite growth in cash generation.

**META — Almost all the operating cash went back in.** Capital spending absorbed most of the quarter’s operating cash generation.

## Definitions matter

These figures cover whole companies. They cannot isolate AI profitability or justify an investment on their own. Quarterly, half-year, annual and trailing-year periods differ; TSMC also reports in New Taiwan dollars under TIFRS.

- **NVDA:** Includes intangible purchases and capital principal payments; this is the company’s disclosed free-cash-flow definition.
- **TSM:** New Taiwan dollars. TIFRS classifies interest differently from US GAAP. Gross PP&E purchases exclude disposal proceeds and other investing flows.
- **AVGO:** Company-wide operating cash less PP&E purchases; includes software and non-AI businesses.
- **CEG:** Parent-company consolidated cash flows include Calpine in 2026. The bridge excludes acquisition payments, financing and other investing flows.
- **VRT:** Operating cash less capex and capitalized software; matches the issuer’s adjusted free-cash-flow reconciliation for these periods.
- **MSFT:** Full fiscal year. Cash property purchases exclude noncash finance-lease additions and other commitments.
- **AMZN:** Trailing twelve months, not one quarter. Net property spending deducts sales proceeds and incentives; excludes debt principal, acquisitions and other financing.
- **GOOGL:** Quarterly company-wide operating cash less PP&E purchases; other investments and acquisitions are outside this bridge.
- **META:** Includes finance-lease principal, consistent with the issuer’s free-cash-flow definition. Company-wide figures do not isolate AI returns.

The [public dataset](../../../experiments/public/cash-map.json) preserves current and prior figures, deductions, source URLs and capture hashes. The [review record](../../../experiments/data/research/cash-map-review.json) binds the published bytes to a source-table and arithmetic review by an AI coding agent. It does not approve investment theses. [Reproduce all 18 bridges](START-HERE.md).

## The next research question

Which changes in customer spending, working capital and financing would alter this picture—and where would those changes travel across the stack? Backlog, commitments and forecasts are not cash receipts. The agent must distinguish disclosed facts from inferred dependencies and explain what could change its view.
