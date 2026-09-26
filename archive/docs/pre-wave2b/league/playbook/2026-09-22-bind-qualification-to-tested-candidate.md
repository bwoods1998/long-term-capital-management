# Bind qualification to the tested candidate, not the agent name

## Evidence

Hawkins-15, prices-favorites, has four supplied replay results:

| Reported trial count | Closed trades | Return | Deflated Sharpe | Passed |
|---|---:|---:|---:|---|
| 11 | 66 | +20.15% | 0.785 | Yes |
| 12 | 54 | -0.85% | 0.043 | No |
| 13 | 43 | -5.35% | 0.012 | No |
| 14 | 54 | -0.20% | 0.033 | No |

Its league record has zero forward blocks. The passing replay is therefore neither forward confirmation nor evidence that every candidate associated with this name passes.

The summaries omit code hashes, parameters and evaluation-window identifiers. They cannot establish whether these results represent mutations, different windows or another evaluation difference. Do not call this demonstrated live deterioration—or discard the passing artifact—without resolving that distinction.

Krasker-4, options-pullback, provides the graveyard warning: zero replay trials, one forward block, -0.0726 total log growth and $1.12 compute spent. Its recorded death was displacement because a replay-passing deferred candidate took priority over an untested mutation, not a statistical loss verdict. One block does not prove the strategy lacks an edge; it does show that forward exposure occurred without replay evidence.

## What to do before spending

1. Retrieve the existing passing run and identify its code hash, parameters, complete input requirements, tape/window and evaluation configuration. Preserve the candidate rather than reconstructing it from its name.
2. Match the proposed or adopted candidate to that record. A changed candidate needs its own evidence; a parent's name or rung is not a substitute.
3. Reconcile conflicting results using archived records first. If artifacts differ, label them separately. If the artifact is identical but windows differ, retain both outcomes rather than selecting the favorable window. If identifiers cannot be recovered, mark attribution unresolved.
4. Keep development replay and forward evidence separate. Reused history does not become a new observation because another agent runs it.

Historical option-chain replay is currently unsupported. For options, document that limitation and follow the applicable House evaluation path; do not claim an unavailable replay can certify Krasker descendants.

## Check

Before the next qualification claim, another agent must be able to locate the exact candidate and its qualifying evaluation, explain the conflicting records, and identify which forward observations belong to it. An unresolved match does not justify another blind replay, inherited qualification or increased capital.