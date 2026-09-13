# Portfolio Agent

**Building an autonomous portfolio manager on Sail to outperform the S&P 500.**

One paper portfolio across S&P 500 stocks and cash. The goal is a continuous loop: **invest, observe outcomes, revise the decision process, test again**. Sail agents follow financial disclosures and revisit their investment cases against the portfolio's record. Every decision and revision is timestamped. The benchmark is the **S&P 500 Total Return Index**.

[Portfolio](https://blakewoods.us/portfolio/) · [Research history](https://blakewoods.us/portfolio/research/) · [How it works](docs/ARCHITECTURE.md)

## Current state

- Paper portfolio and source-linked research history; live Schwab execution comes later.
- Weekday service implemented: persistent history, daily evidence, scheduled paper accounting, cloud supervision and private backups. The portfolio page shows deployment status.
- Recorded outcomes return to subsequent allocation reviews. Controlled memory experiments support research reliability; autonomous investment-policy selection and proven outperformance remain ahead.

Sail supplies inference, persistent cloud execution and Voyages tracing. The project measures research quality, latency and cost, including memory, scheduling and cache comparisons. Training a specialized model is a later experiment.

[Evaluation](docs/EVALUATION.md) · [Operations](docs/OPERATIONS.md) · [Roadmap](docs/ROADMAP.md)
