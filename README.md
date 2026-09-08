# Portfolio Agent

Building a persistent AI investor with Sail and Charles Schwab. A personal experiment in research, portfolio management, and the cost of useful intelligence.

**Early development.** Financial extraction and cost measurement work today. Brokerage connectivity, portfolio management, and the public dashboard are planned. No brokerage orders can be placed by the current code.

## The vision

One small portfolio, with a living record of why each position exists, what would change the thesis, and what the agent spends investigating it. Research can span hours or days, resume after interruptions, and return when new evidence arrives.

The owner controls assignments, budgets, and any future trading permissions. Public visitors see selected research and results through a separate read-only view. The first implementation will be for one owner.

The question: **Can an agent maintain a coherent investment strategy over time—and justify its research costs?**

## Start reading

- [Project roadmap](docs/ROADMAP.md): milestones and tomorrow's starting point.
- [Architecture](docs/ARCHITECTURE.md): research, brokerage, and public-view boundaries.
- [Learning path](lessons/README.md): what to understand at each stage.
- [Lesson 1](lessons/01-first-experiment.md) and [first result](lessons/01-result.md): the working foundation.
- [Run the existing experiment](docs/EXPERIMENTS.md): setup, commands, and spending controls.

## What works now

A Python program extracts five financial facts from a small public filing table, checks values and evidence, and records token usage and estimated cost. The first trial passed all five facts at an estimated $0.00011808. One development example is not a benchmark of investment ability.

```sh
python3 lab.py preview
python3 -m unittest discover -s tests -v
```

Both commands run locally without API calls. Python 3.10+; no third-party packages required for the current experiment.

Sail credentials are stored in an owner-readable, Git-ignored `.env`. Local runs and documentation snapshots stay in ignored `.data/`. Preserve that directory: it includes the experiment's persistent budget history. No Schwab credentials are needed at this stage.

## How it grows

Read-only portfolio reconciliation → one persistent investment thesis → scheduled research with traces and cost controls → simulated trade proposals → owner-approved live orders → optionally, a precisely bounded autonomous mandate.

Sail inference supplies model calls; Sailboxes and Voyages can later supply execution and tracing. We build the memory, planner, evaluations, and financial controls. Each new capability must earn its complexity through a useful experiment.

Research costs and investment results will be reported separately. Public market-data display depends on the applicable data permissions. This is a personal software experiment, with no customer funds or public trading controls.
