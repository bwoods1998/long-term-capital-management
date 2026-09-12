# Lesson 4: Evidence that changes the question

The useful outcome of research is sometimes a better distinction. This exercise
follows reported capital spending through financial statements, management guidance,
agent memory, and review. No paid call is required.

## Predict first

A company's reported capital-expenditure outlook falls. Write two explanations that
would have different implications for its underlying investment plans. Then name the
evidence that could distinguish them. Avoid assuming that a changed accounting
measure means fewer buildings or less computing capacity.

Now open the [registered source notes](../data/research/source-notes.json) and the
[Microsoft earnings call](https://www.microsoft.com/en-us/investor/events/fy-2026/earnings-fy-2026-q4).
Find the passage about estimated useful lives and future lease classification.
Separate four things in your notes:

| Question | Your answer |
|---|---|
| What accounting assumption changes? | |
| How does management expect that to affect reported capex? | |
| What does management say about its investment plans? | |
| What remains unverified about actual future commitments or cash payments? | |

The passage describes management's outlook. It cannot establish realized construction
activity, future cash payments, or investment returns. Write one sentence preserving
that distinction. Then explain why the headline “investment commitments are unchanged”
would claim more than the passage proves.

## Reconcile the measures

Use the [checked financial packet](../data/thesis/msft-ai-infrastructure.json) and
[cash flow statements](https://www.microsoft.com/en-us/investor/earnings/fy-2026-q4/press-release-webcast).
All amounts here are USD millions:

| Full-company measure | FY2025 | FY2026 |
|---|---:|---:|
| Operating cash flow | 136,162 | 182,935 |
| Cash PP&E purchases | 64,551 | 115,948 |

Calculate each growth rate and each year's cash flow remaining after cash PP&E.
Check your arithmetic against Lesson 2 only after writing your answer.

Explain why a change in forward reported-capex guidance does not reverse the
historical cash PP&E increase. Keep fiscal-year results separate from calendar-year
plans. Cash PP&E, capital expenditures including finance leases, and operating-lease
commitments measure different things. Company-wide cash after PP&E is a useful
research proxy; it does not isolate AI profit or establish a project's return.

## Inspect how the agent learns

Follow these functions in [investigator.py](../investigator.py):

1. `_tool` restricts available actions. Identify a question the current calculator
   cannot answer because its inputs are limited to checked facts.
2. `compact_memory` retains passages and calculation results while removing repeated
   transcript text. Name something preserved and something deliberately lost.
3. `research_memory` uses prior reviewed conclusions. Explain why an old conclusion
   must remain distinguishable from a newly retrieved source.
4. `_critique_input`, `amend`, and `review` separate criticism, correction, and
   publication. Explain why a passing critic is useful but insufficient.

If you have a saved investigation, run these local commands:

```sh
python3 investigator.py status INVESTIGATION_ID
python3 investigator.py inspect INVESTIGATION_ID
```

Choose one claim and follow its citation back to its source. Check the headline and
summary too: they can overstate certainty even when a detailed claim is qualified.
Write an invalidation condition that refers to observable evidence, rather than
“if the model changes its mind.”

## Decide what deserves another dollar

Read the [Sail product experiment](../docs/SAIL-PRODUCTS.md). The cloud recovery test
retained one reservation, retrieved one synthetic known response, and submitted no
new request. Explain why this demonstrates engineering recovery rather than model
intelligence. What additional observation would demonstrate useful research recovery
after a real model request?

Inspect the evaluation fixtures and available `public/research-evaluation.json`
results. State the denominator before quoting a pass rate. Distinguish a failed
answer, an unfinished request, and missing usage. Explain why a perfect score on
sixteen authored development cases would still leave substantial uncertainty.

Finish with a short experiment proposal: one hypothesis, one changed variable, one
quality measure, one cost measure, and a stopping rule. For example, test whether a
critic improves unsupported-claim detection across a new held-out set. Predict the
result before spending; retain unsuccessful attempts in the economics afterward.
