# Portfolio Agent

An AI investor that remembers its reasoning. A personal experiment in research, portfolio management, and the cost of useful intelligence.

[Research ledger](https://blakewoods.us/portfolio/) · [V1 runbook](docs/V1.md) · [Learning path](lessons/README.md)

**V1: research only.** One persistent thesis, dated evidence, private drafts, explicit review, and a public decision history. Sail supplies inference; local Python and SQLite preserve the work. The brokerage demo uses synthetic data. Schwab connectivity and trading are future capabilities; no code here can submit brokerage orders.

## The vision

One small portfolio, with a living record of why each position exists, what would change the thesis, and what the agent spends investigating it. Research can span hours or days, resume after interruptions, and return when new evidence arrives.

The owner controls assignments, budgets, and any future trading permissions. Public visitors see selected research and results through a separate read-only view. The first implementation will be for one owner.

The question: **Can an agent maintain a coherent investment strategy over time—and justify its research costs?**

## Start reading

- [V1 runbook](docs/V1.md): preview, predict, research, review, export.
- [A thesis with memory](lessons/02-thesis-with-memory.md): the next learning exercise.
- [First thesis results](lessons/02-result.md): five attempts, one accepted view, and their costs.
- [Project roadmap](docs/ROADMAP.md): milestones and next steps.
- [Architecture](docs/ARCHITECTURE.md): research, brokerage, and public-view boundaries.
- [Learning path](lessons/README.md): what to understand at each stage.
- [Lesson 1](lessons/01-first-experiment.md) and [first result](lessons/01-result.md): the working foundation.
- [Run the existing experiment](docs/EXPERIMENTS.md): setup, commands, and spending controls.

## What works now

The first thesis asks whether Microsoft's AI investment can turn into durable cash flow. A checked [evidence packet](data/thesis/msft-ai-infrastructure.json) supplies company-wide financial facts and attributed management commentary. Each revision sees the previous reviewed thesis, preserves its own evidence, and records what would change the view. Public visitors read precomputed snapshots and cannot launch paid work.

The original extraction experiment remains available. Its first trial passed five facts in one response at an estimated $0.00011808; one development example is not a benchmark of investment ability.

```sh
python3 portfolio.py init
python3 portfolio.py preview
python3 brokerage.py demo
python3 -m unittest discover -s tests -v
```

These commands run locally without API calls. Python 3.10+; no third-party packages required. The brokerage demo implements our internal accounting contract, not Schwab's API schema.

Sail credentials are stored in an owner-readable, Git-ignored `.env`. Local runs and documentation snapshots stay in ignored `.data/`. Preserve that directory: it includes the experiment's persistent budget history. No Schwab credentials are needed at this stage.

## How it grows

One persistent thesis and a public ledger → controlled research comparisons and private read-only portfolio reconciliation → scheduled research with traces and cost controls → simulated trade proposals → owner-approved live orders → optionally, a precisely bounded autonomous mandate.

Sail inference supplies model calls; Sailboxes and Voyages can later supply execution and tracing. We build the memory, planner, evaluations, and financial controls. Each new capability must earn its complexity through a useful experiment.

Research costs and investment results will be reported separately. Public market-data display depends on the applicable data permissions. This is a personal software experiment, with no customer funds or public trading controls.
