# Portfolio Agent

**Building an autonomous portfolio manager on Sail to outperform the S&P 500.**

The agent researches companies, maintains investment theses and allocates a paper portfolio across S&P 500 stocks and cash. The benchmark is the **S&P 500 Total Return Index**. Live execution through Charles Schwab comes later.

The experiment: does a persistent agent make better decisions when it can spend more time researching, remember earlier work and test competing explanations? Sail supplies the inference and cloud infrastructure; the project records the decisions, failures and cost.

[Public portfolio](https://blakewoods.us/portfolio/) · [Architecture](docs/ARCHITECTURE.md) · [Evaluation](docs/EVALUATION.md)

## Current state

- Paper ledger implemented; no live trades or investment performance yet.
- Dated SEC financial facts captured for all 503 securities in the current research universe.
- Hosted research is underway. The [live portfolio](https://blakewoods.us/portfolio/) shows the latest work and checkpoint; [run notes](docs/runs/2026-09-13.md) record the first sustained experiment.

[Run and inspect](docs/OPERATIONS.md) · [Roadmap](docs/ROADMAP.md)
