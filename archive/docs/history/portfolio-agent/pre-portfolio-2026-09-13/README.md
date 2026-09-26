# Technical reference

[Project overview](../../../../README.md) · [Current results](CURRENT-STATE.md) · [Reproduce the figures](START-HERE.md)

## Core reading

- [AI cash flows](AI-STACK.md): the nine-company financial record and its definitions.
- [Sail’s role](SAIL-PRODUCTS.md): applied products, actual measurements and limits.
- [Latest experiment](NIGHT-SHIFT.md): the research protocol and what survived its checks.
- [Architecture](ARCHITECTURE.md): evidence, orchestration, memory and publication.
- [Roadmap](ROADMAP.md): the next useful milestone and the path to a portfolio.

<details>
<summary>Implementation and earlier experiments</summary>

## Run and understand the system

- [Research loop](RESEARCH-LOOP.md): the investigator, tools, critique, review,
  and request recovery. This is the tool-assisted research workflow.
- [Operations](OPERATIONS.md): inspect an existing local ledger without advancing work.
- [Architecture](ARCHITECTURE.md): evidence, memory, execution, and public exports.
- [Source inbox](SOURCE-WATCH.md), [reviewed handoff](SOURCE-CURATION.md), and
  [assignment queue](RESEARCH-QUEUE.md): carry checked updates into explicit work.
- [Sail product record](SAIL-PRODUCTS.md) and [API notes](SAIL-API-NOTES.md):
  documented capabilities, observed usage, and limits.
- [Live cloud tool trial](CLOUD-WORKER.md), [shared research context](SHARED-RESEARCH-CONTEXT.md),
  and [budget settlement](BUDGET.md): the current integration work.
- [Method improvement](AUTONOMY.md): candidate prompts, separate validation,
  automatic promotion rules, and rollback.
- [Performance accounting](PERFORMANCE.md): the synthetic returns calculator.
- [Original thesis-runner guide](V1.md) and [first extraction setup](EXPERIMENTS.md):
  earlier workflows retained for reproduction.
- [Private Schwab setup](../SCHWAB-SETUP.md): paused integration; separate from research.

## Measured experiments

These are development experiments with their own dates and limitations. Scores
measure the stated checks, not investing ability. Invalid and unsuccessful attempts
remain in the record.

| Question | Experiment |
|---|---|
| What changes with the model or an added critic? | [Model evaluation](EVALUATION-RESULTS.md) |
| Can memory follow changing evidence? | [Fictional timeline replay](TRAJECTORY-REPLAY.md) |
| When does caching reduce the whole bill? | [Scheduling and cache pilot](POLICY-EXPERIMENT.md) |
| Do models preserve units and resist source instructions? | [Source-instruction pilot](ROBUSTNESS.md) |
| What happened during the first extended build? | [Dated build record](BUILD-RECORD.md) |

## Public data

The website reads saved JSON. Public visitors cannot start model requests.

- Shared-context measurements (`experiments/public/shared-research-context.json`),
  prompt-selection decision (`experiments/public/self-improvement.json`), and
  current budget accounting (`experiments/public/research-budget.json`) record the newest
  experiments without private prompts or model drafts.

- Research universe (`experiments/public/universe.json`) lists nine company profiles and
  official sources. A profile is not a reviewed investment case or a holding.
- Thesis history (`experiments/public/portfolio.json`) and reviewed investigations (`experiments/public/investigations.json`)
  contain selected published research. Their cost fields distinguish known estimates
  from unknown usage; they are not a reconciled provider bill.
- Cash-flow bridge (`experiments/public/cashflow-bridge.json`) contains independently checked
  issuer figures and source metadata.
- Original dossier (`experiments/public/research-dossier.json`) and
  separate follow-up (`experiments/public/dossier-followup.json`) contain measured checks,
  not approval of their model drafts.
- Evaluation (`experiments/public/research-evaluation.json`), replay (`experiments/public/trajectory-replay.json`),
  cache pilot (`experiments/public/policy-experiment.json`), and robustness (`experiments/public/robustness.json`)
  preserve experiment measurements. The rejected scheduling configuration (`experiments/public/experiments/rejected-asap/policy-experiment.json`)
  is retained separately.

Raw responses, private run databases, full source captures, and credentials are
not included in a public clone. Historical documents describe their recorded
protocols; consult the relevant current runner before starting new paid work.

</details>

Public data for the current page: cash bridges (`experiments/public/cash-map.json`) · source review (`experiments/data/research/cash-map-review.json`) · agent checkpoint (`experiments/public/agent-state.json`).
