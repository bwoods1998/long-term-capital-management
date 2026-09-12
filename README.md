# Portfolio Agent

An AI investor that remembers its reasoning. A personal experiment in research, portfolio management, and the cost of useful intelligence.

[Research ledger](https://blakewoods.us/portfolio/) · [Research loop](docs/RESEARCH-LOOP.md) · [Learning path](lessons/README.md)

**V1: an investigator with evidence and memory.** The agent searches registered primary sources, checks calculations, saves hypotheses, and submits a report to a separate critic. Reviewed work becomes a public research record and memory for future assignments. Sail supplies inference and tracing; Python and SQLite preserve requests, evidence, and spending through interruptions. The optional private account connector remains separate; no code here submits brokerage orders.

## The vision

One small portfolio, with a living record of why each position exists, what would change the thesis, and what the agent spends investigating it. Research can span hours or days, resume after interruptions, and return when new evidence arrives.

The owner controls assignments, budgets, and any future trading permissions. Public visitors see selected research and results through a separate read-only view. The first implementation will be for one owner.

The question: **Can an agent maintain a coherent investment strategy over time—and justify its research costs?**

## Start reading

- [Research loop](docs/RESEARCH-LOOP.md) and [Lesson 4](lessons/04-research-loop.md): tools, evidence memory, critique, and recovery.
- [Measured model comparisons](docs/EVALUATION-RESULTS.md): all attempts, costs, and limits of the development test.
- [Applied Sail products](docs/SAIL-PRODUCTS.md): live Voyages and a measured Sailbox persistence experiment.
- [V1 runbook](docs/V1.md): preview, predict, research, review, export.
- [Private Schwab access](docs/SCHWAB-SETUP.md): authorize locally and read a private account snapshot.
- [Lesson 3](lessons/03-schwab-access.md): app credentials, account consent, and token refresh.
- [A thesis with memory](lessons/02-thesis-with-memory.md): the next learning exercise.
- [First thesis results](lessons/02-result.md): five attempts, one accepted view, and their costs.
- [Project roadmap](docs/ROADMAP.md): milestones and next steps.
- [Architecture](docs/ARCHITECTURE.md): research, brokerage, and public-view boundaries.
- [Learning path](lessons/README.md): what to understand at each stage.
- [Lesson 1](lessons/01-first-experiment.md) and [first result](lessons/01-result.md): the working foundation.
- [Run the existing experiment](docs/EXPERIMENTS.md): setup, commands, and spending controls.

## What works now

The first thesis asks whether Microsoft's AI investment can turn into durable cash flow. A checked [evidence packet](data/thesis/msft-ai-infrastructure.json) supplies company-wide financial facts and attributed management commentary. The investigator can read beyond that packet: its first reviewed run found how lease classification changes reported capex without establishing a change in actual construction commitments. A single-pass comparison, rejected attempt, and editorial corrections preserve what extra research did and did not accomplish. Public visitors read precomputed snapshots and cannot launch paid work.

The model comparison uses sixteen authored cases, repeated across three models, plus a separate uniform-critic experiment. It is a development regression, not a benchmark of investment performance. The [Sailbox proof](data/experiments/sailbox-validation-2026-09-12.json) tested isolated execution and recovery after sleep/pause/resume with synthetic request state; it did not place live inference or trading inside the VM.

The original extraction experiment remains available. Its first trial passed five facts in one response at an estimated $0.00011808; one development example is not a benchmark of investment ability.

```sh
python3 portfolio.py init
python3 portfolio.py preview
python3 brokerage.py demo
python3 -m unittest discover -s tests -v
```

These commands run locally without API calls. Python 3.10+; no third-party packages required for research or the synthetic demo. The demo implements our internal accounting contract, not Schwab's API schema. The optional real-account connector uses separately pinned community SDK dependencies in `.venv`; see [setup](docs/SCHWAB-SETUP.md).

Sail credentials are stored in an owner-readable, Git-ignored `.env`. Local runs, documentation snapshots, and private Schwab state stay in ignored `.data/`. Preserve that directory: it includes the experiment's persistent budget history. Research does not require Schwab credentials or account authorization.

## How it grows

One persistent thesis and a public ledger → controlled research comparisons and private read-only portfolio reconciliation → scheduled research with traces and cost controls → simulated trade proposals → owner-approved live orders → optionally, a precisely bounded autonomous mandate.

Sail inference supplies model calls, Voyages trace live workflows, and Sailbox execution has a measured persistence proof. We build the memory, planner, evaluations, and financial controls. Scheduling, broader source coverage, and portfolio decisions are subsequent work. Each new capability must earn its complexity through a useful experiment.

Research costs and investment results will be reported separately. Public market-data display depends on the applicable data permissions. This is a personal software experiment, with no customer funds or public trading controls.
