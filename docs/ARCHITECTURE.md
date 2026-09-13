# Architecture

The project follows public companies across the AI stack: what the evidence says,
what remains uncertain, and what would change the view. Microsoft is the first
reviewed case. The other eight companies have sourced profiles and bounded
research questions; they are not holdings or fully reviewed investment cases.

```mermaid
flowchart LR
    Sources[Issuer disclosures] --> Evidence[Frozen evidence and source dates]
    Evidence --> Agent[Research controller]
    Agent <--> Sail[Sail inference]
    Agent <--> Tools[Local tools or isolated Sailbox]
    Agent <--> Ledger[Private request and memory ledger]
    Agent --> Critic[Evidence critic and bounded repair]
    Critic --> Review[Publication review]
    Review --> Site[Saved public website]
    Review --> Agent
    Agent --> Voyage[Voyages trace]
    Failures[Recorded failures] --> Candidate[Candidate research method]
    Candidate --> Gate[Separate development and validation checks]
    Gate --> Champion[Promote or retain current method]
```

## Evidence and research

Checked facts preserve units, periods, arithmetic, and source IDs. Registered
source captures preserve publication/retrieval dates, hashes, and exact passage
positions. Source text is evidence, never permission to execute instructions.

The investigator chooses bounded source reads and calculations, saves hypotheses
and invalidation conditions, and drafts a report. Its next invocation resumes
saved requests and evidence. Context compaction preserves observed passages,
calculations, and hypotheses while removing repeated transcript text.

The original live tool registry covers two Microsoft documents. The broader
nine-company corpus is a separately frozen research input; listing a company
on the website does not silently add it to the live source monitor.

An independent critic may request one repair. Schema and citation checks cannot
prove arbitrary prose correct, so research publication has a separate review
boundary. New investigations accept a single optional JSON fence under a frozen
format policy; this does not repair content or change historical results.

[Research loop](RESEARCH-LOOP.md) · [Source inbox](SOURCE-WATCH.md) ·
[Checked source handoff](SOURCE-CURATION.md)

## Execution and memory

The MacBook currently owns the authoritative SQLite ledger and credentials.
The [Sailbox worker](CLOUD-WORKER.md) executes allowlisted tools against uploaded
public evidence, without credentials or network access. Receipts survive sleep
and are verified locally. It does not yet host the complete controller.

Reviewed research can inform later investigations. Draft experiments and critic
benchmarks cannot become company facts. The original assignment queue has two
permanent pilot slots; a new experiment never resets their history.

[Queue protocol](RESEARCH-QUEUE.md) · [Sail products](SAIL-PRODUCTS.md)

## Requests, improvement, and costs

Every model request freezes its body, model, completion window, rates, and
allowance before submission. Recovery keeps the original request identity and
retrieves a known response. Missing usage or an uncertain submission is not free.

The [settlement policy](BUDGET.md) replaces a completed request's conservative
hold with a validated usage estimate through an immutable receipt. Historical
requests remain unchanged. Shared-context caching uses a separate explicit
write/read cost contract inside this same ledger.

The improvement gate compares a candidate evidence-critic prompt with the
current prompt on fixed development and separately authored validation cases.
It can promote the prompt only under its frozen no-regression rule. This is
bounded method selection, not permission to edit arbitrary code, alter tests,
change budgets, publish reports, or trade. See [current state](CURRENT-STATE.md)
for what has actually run.

## Public and account boundaries

The website serves allowlisted saved JSON. Visitors cannot launch model requests
or access private prompts, full captures, credentials, or account identifiers.
Technical experiment results live on GitHub; the page highlights companies and
the first checked cash-flow scenario. Deployment is separate from research.

Schwab is disconnected. Future execution will require a separate structured
order service with an owner-defined mandate, deterministic exposure and order
checks, reconciliation, and a stop control. Research prose cannot grant itself
account access. The existing performance calculator uses synthetic fixtures;
there are no live trades or reported investment returns.
