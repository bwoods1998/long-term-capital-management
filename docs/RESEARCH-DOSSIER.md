# A research dossier with a checked numerical bridge

The dossier asks how Microsoft's reported cash generation, infrastructure spending,
and investment commitments fit together—and which conclusions the disclosures
cannot support. It puts multiple models through a connected research task, with
source evidence and arithmetic carried into reconciliation, synthesis, and critique.

The first twelve-stage run and a separate two-stage follow-up are complete.
[Measured results](DOSSIER-RESULTS.md) preserve the failed final revision and the
follow-up's narrower improvement. A saved request, a completed stage, and a useful
research result are different outcomes; neither automated score approves publication.

## The research problem

Three related themes give the analysts different responsibilities:

- **Cash generation:** reconcile the complete reported cash-flow adjustments and
  distinguish their combined effect from selected positive contributions.
- **Investment commitments:** separate cash property purchases, reported capital
  expenditures, lease classifications, and forward investment plans.
- **Demand and AI attribution:** identify what company and segment disclosures actually say,
  preserving the gap between company-wide cash generation and AI-specific returns.

The earlier [working-capital audit](../data/research/working-capital-audit.json)
shows why numerical completeness matters. The change in accounts payable and
unearned-revenue contributions is positive, but other reported adjustments offset
much of that movement. A persuasive account of selected rows can miss the full
bridge. These cash-flow-statement adjustments are also not simple differences
between balance-sheet balances.

The dossier should produce a source-linked account of that bridge, disputed
interpretations, and remaining questions. It does not estimate investment returns
or turn company-wide cash flow into an AI profitability measure.

## Twelve connected stages

| Stage group | Calls | Responsibility |
| --- | ---: | --- |
| Three themes, two analysts each | 6 | DeepSeek Pro and Kimi K3 examine the same frozen evidence independently. |
| Theme reconciliations | 3 | Pro compares both analyses with the source evidence and checked arithmetic. |
| Dossier synthesis | 1 | Kimi combines the reconciliations into a coherent account with unresolved issues. |
| Substantive critique | 1 | Kimi checks the synthesis for support, scope, completeness, and unjustified certainty. |
| Bounded revision | 1 | Pro responds to the critique using the existing evidence. |

The two initial analysts do not see each other's answers; the current controller
executes the stages sequentially. Later stages receive the
relevant earlier work as candidate interpretations, alongside the evidence needed
to challenge them. Agreement is not an additional source. Kimi supplies a second
model family, but a shared evidence packet and related prompts can still produce
correlated mistakes.

Each reconciliation receives eleven fixed source passages selected when the rubric
was authored, plus any passages cited by its two analysts. This supplies review
locations without exposing reference values. Synthesis, critique, and revision
receive only the passages their immediate parent reports cited. That keeps requests
bounded, but an important passage omitted upstream may stay absent downstream.
The final external review must check the full source record, including omissions;
agreement across these stages cannot rule out that failure.

This protocol deliberately moves beyond the earlier short synthetic checks. Its
unit of work is a connected financial argument, rather than another count of
isolated correct labels. It remains one company, one evidence set, and one pilot;
it cannot establish general model superiority or long-run investing ability.

## What is frozen and what is checked

Before the first paid request, the protocol must identify its stage dependencies,
model profiles, input limits, source hashes, checked quantities, and deadline.
Every admitted request keeps its exact body and stable task identity in the shared
ledger. New source-watch candidates do not enter this dossier automatically.
See [source curation](SOURCE-CURATION.md) for the separate acceptance and fact-review
handoff used by future assignments.

Numeric statements need an explicit unit, period, scope, source location, and
operation. The models propose values for sixty-four requested metrics. This dossier
does not give them a calculator tool: deterministic local grading compares their
answers with a separately checked numerical rubric, including exact units, periods,
and required source coverage. The expected values are withheld from prompts;
downstream stages may see earlier answers and failed-check categories. A useful review asks:

1. Does the full bridge reconcile, including negative and offsetting rows?
2. Does each source actually support the associated claim and its time period?
3. Are management statements, accounting presentation, forecasts, and observed
   results distinguished?
4. Does the account preserve uncertainty about persistence and AI-specific returns?
5. Did reconciliation or critique resolve a disagreement with evidence, or merely
   replace it with more confident prose?

All candidate analyses and critiques remain private until an explicit editorial
decision. In particular, the final revision happens **after** the automated critic;
the critic's verdict does not approve that revised text. No stage automatically
publishes a dossier, changes the reviewed thesis, or starts another assignment.

## Cost and time

The proposed ceiling is **twelve requests and $6.40 in additional permanent
reservations**: seven Pro calls at $0.20 each and five Kimi calls at $1.00 each.
This preserves the earlier $88.20 of reservations. Fully admitting this protocol
would bring cumulative holds to $94.60 under the explicitly increased $95 inference
ceiling, leaving room below the separate $100 overall authorization for other
already recorded product costs. These are authorization ceilings, not bills, and
unused historical reservations are not refunded or reused.

After the original run exposed lost evidence, one separately frozen two-call
follow-up received a $1.20 allowance. The explicitly revised cumulative inference
ceiling was $96; all fourteen admissions brought holds to $95.80. Earlier history
remains intact and the overall authorized ceiling stays $100. This is a closed
follow-up, not permission to keep creating revisions until one passes.

Separate dossier profiles use Pro Flex and Kimi K3 ASAP, each with at most 32,768
output tokens. Ordinary investigation profiles retain their earlier limits.
Their input/cached/output rates per million tokens are
$0.66/$0.022/$1.98 and $3/$0.30/$15 respectively, checked September 13, 2026.
Kimi's premium buys a different analyst and reviewer; it does not buy a correctness
guarantee. Token-based estimates and missing usage must remain visible separately
from reservations and reconciled billing. [Official pricing](https://docs.sailresearch.com/pricing)

Sail lists a one-million-token context for both models, but the current application
envelope is much smaller: at most 96,000 serialized request bytes. A large provider
context is capacity, not evidence that this experiment exercised it.
[Model capabilities](https://docs.sailresearch.com/models)

The dossier stops advancing on September 13, 2026 at **05:00 UTC**, leaving ten
minutes before the session ends for review and reconciliation. Flex has no promised
time-to-first-token or generation-speed target. Sequential execution makes later
stages depend on the time consumed by earlier ones. The cutoff preserves incomplete
outcomes rather than adding replacement requests. Accepted background work may
continue afterward: a client timeout does not cancel it. Its original response
identity remains in the ledger for explicit reconciliation.
[Completion windows](https://docs.sailresearch.com/completion-windows)

## Which Sail products this exercises

The connected stages use **Responses inference** for the actual financial work and
**Voyages** to attribute stage activity, model requests, and outcomes across a
durable workflow. Voyage correlation adds observability; orchestration, accounting,
review, and publication remain responsibilities of this application.
[Voyage inference integration](https://docs.sailresearch.com/voyages-sdk-inference)

Sail does not provide the research agent with hosted web search or a hosted code
interpreter. Those tools are not available merely because an OpenAI-compatible
request accepts their names. Source retrieval, source selection, calculations,
and conversation assembly must be implemented locally. The current support matrix
also requires sending the needed input each turn rather than chaining with
`previous_response_id`.
[API support](https://docs.sailresearch.com/support)

Ordinary prompt caching may reduce repeated input cost, but hits must be measured.
The dossier does not enable **Supercache**: its documented write charge is one
hundred times normal input, while reads cost one tenth of ordinary cached input.
A dozen stages across two models do not justify assuming enough reuse to repay
that write. The [cache economics calculation](SAIL-PRODUCTS.md#cache-economics-before-enabling-another-product)
states its assumptions explicitly. [Supercache documentation](https://docs.sailresearch.com/supercache)

**LoRA training and serving remain future work.** Sail currently documents adapter
serving for Kimi K2.6, with rank at most thirty-two and Balanced or Flex requests.
A useful financial adapter would first need a larger reviewed corpus and a separate
evaluation set; fitting the small development fixtures would not demonstrate
research improvement. [LoRA support](https://docs.sailresearch.com/loras)
Sail's Tinker integration serves rollouts while Tinker owns optimization and
requires its own account credentials. That is a distinct training experiment,
not an extra switch on this dossier. [Tinker workflow](https://docs.sailresearch.com/tinker-rl)

The earlier [Sailbox validation](SAIL-PRODUCTS.md#observed-sailbox-validation--september-12-2026)
already exercised isolated execution and recovery. This dossier does not create
another VM merely to repeat that demonstration. Hosting a genuinely persistent
research controller is a later deployment choice.

## Evidence of progress

Record completed, invalid, failed, and unfinished stages; exact input and source
hashes; numerical reconciliation checks; source-supported disagreements; changes
made after critique; tokens, cache usage, cost estimates, and elapsed observations.
Report which stages were actually admitted and which downstream work could not
run. A successful protocol outcome requires substantive review, not only valid JSON.

The public website continues to load reviewed static exports. A future reviewed
dossier can add a short finding and an expandable numerical bridge; visiting it
must not submit model requests. The source record and learning notes can hold the
detail without making the personal website wordy.
