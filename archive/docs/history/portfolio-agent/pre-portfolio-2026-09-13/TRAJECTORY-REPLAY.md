# Research across an evidence timeline

This is an explicitly **synthetic stress experiment**. Three fictional companies
receive dated disclosures, corrections, and rejected updates. It tests whether an
agent retains useful evidence and revises its prior view. It is not a historical
backtest, investment result, or new Microsoft disclosure.

## Frozen protocol

| Dimension | Configuration |
|---|---|
| Trajectories | Cash-flow correction; genuine investment-plan cut; withdrawn guidance |
| Model-eligible updates | Four per trajectory, in sequence |
| Local gates | Duplicate content, future-dated evidence, unapproved provenance |
| Memory policies | Full document/agent-view history; current evidence notebook plus latest agent view |
| Models | DeepSeek V4 Pro 0813 Flex; DeepSeek V4 Flash 0731 ASAP |
| Maximum model requests | 3 × 4 × 2 × 2 = 48 |
| Maximum reservations | 24 × $0.20 + 24 × $0.10 = $7.20 |

This is a separate protocol from the 128-call short-case evaluation. Both use the
same permanent money ledger. Replay requests have purpose `replay`; they cannot
create thesis revisions or enter real-company investigation memory. The controller
does not reset or increase the shared spending allowance.

The fixtures and prompt templates are frozen before execution. Each next request
waits for the previous episode to reach a terminal state, then freezes the actual
prior typed model state into its input. An invalid prior response is explicitly
unavailable. Even a structurally valid but wrong prior answer carries forward as a
fallible belief. The model never receives reference answers or grades.

Both policies receive the same current eligible evidence. Full history also retains
superseded documents and all prior typed agent views. The notebook retains current
documents, supersession references, and only the latest typed agent view. Its source
reducer is deterministic; the carried research state comes from the model. This
comparison tests this combined memory policy, not a pure isolated context-length
effect or preservation of internal model reasoning.

## What must remain correct

Each episode reports five structured fields: the latest company-wide cash proxy,
its change from the prior fiscal year, management's investment-commitment outlook,
the explanation for reported capex changes, and whether AI-specific returns can be
established. The grader checks exact arithmetic, units, periods, supported labels,
current citation IDs, and required evidence coverage.

A correction must replace the affected statement while retaining the other fiscal
year. Accounting-only guidance must not rewrite realized cash flows. A withdrawn
forecast requires abstention without erasing historical financial facts. None of
these fixtures supplies AI-only returns.

Duplicate, future, and unapproved records are rejected before inference. The
unapproved record contains a hostile instruction; blocking it demonstrates the
provenance gate, **not** model resistance to instructions inside an approved source.
The fixtures are released through a condensed local replay, not a live issuer feed.

## Session procedure and recovery

These commands document the completed September 12–13 pilot. Its one-time task
allowance has been consumed, and new admissions also stop at September 13, 05:10
UTC. A later deadline argument cannot extend that window. To explore the results
now, use the saved replay (`experiments/public/trajectory-replay.json`) and
[Lesson 5](../lessons/05-research-across-time.md); neither requires another model
call. A future paid comparison needs a new bounded protocol that preserves this
experiment and its spending history.

Creating and inspecting a campaign makes no provider calls:

```sh
python3 trajectory_replay.py create
python3 trajectory_replay.py status CAMPAIGN_ID
```

This command **can submit paid requests** and optionally records a private Voyage:

```sh
.venv/bin/python trajectory_replay.py --voyage run CAMPAIGN_ID --seconds 300
```

After the first accepted response ID is persisted, the controller deliberately
returns. Run the same command in a **new process**. It retrieves the original ID and
checks the unchanged request and reservation before advancing. Even an already
completed response is retrieved once for this recovery milestone. A pending or
failed retrieval never authorizes a replacement submission. Unknown usage remains
unknown. An uncertain initial submission retains its original idempotency key.

Live compatibility check: Sail's catalog uses `deepseek-ai/DeepSeek-V4-Pro-0813`
and `deepseek-ai/DeepSeek-V4-Flash-0731`, while authenticated response objects used
`deepseek/deepseek-v4-pro-0813` and `deepseek/deepseek-v4-flash-0731`. Recovery permits
only these exact observed aliases and the requested identifiers, preserving model
versions. Its first strict equality check stopped safely on this naming difference;
no replacement model request was submitted.

Continue with the same campaign ID. Terminal invalid answers are recorded as
failures; they do not buy unlimited retries. The deadline stops new work and reports
unfinished requests, which may still finish at the provider.

```sh
python3 trajectory_replay.py export CAMPAIGN_ID public/trajectory-replay.json
python3 -m unittest discover -s tests -p test_trajectory_replay.py -v
```

The synthetic export has its own fixed filename and cannot replace the real-company
snapshot or investigation artifact. It contains authored scenario labels, enum and
numeric observations, grades, source IDs, usage, and recovery results. Raw model
responses, request IDs, credentials, and arbitrary generated prose stay private.

## Connect the rehearsal to real sources

The [source-update inbox](SOURCE-WATCH.md) supplies the arrival side of this future
workflow: it checks registered real pages and preserves changed captures for
inspection. Its first live false alarms came from request trace identifiers, not
financial disclosures. A versioned comparison now excludes that narrowly defined
noise while retaining full raw observations.

The replay asks what the agent should remember and change **after** evidence is
admitted. The inbox asks whether a retrieved page deserves inspection in the first
place. Accepting a source candidate still requires checking new facts and preparing
a new assignment; neither component automatically publishes a thesis.

## Read the economics honestly

Report complete-trajectory passes as well as individual field/step scores. Include
failed and incomplete work in costs. Compare input bytes and reported cached/input/
output tokens per policy; smaller memory may not improve quality or cost. Price
snapshots yield estimates, not reconciled billing. Reservations are allowances.

Inspect performance after an earlier failed step separately. This includes wrong
answers, invalid formats, and provider failures that supplied no usable view; these
causes remain distinguishable in the step states. If none occurred, that metric has
no observations. One run per model/policy on
three authored trajectories is a development result, not a reliable population
estimate. A successful fresh-process checkpoint demonstrates recovery across
invocations, not months of autonomous operation.

Pro uses Flex and Flash uses ASAP in this protocol. Differences between them mix
model and scheduling choices; this experiment cannot isolate the effect of a
completion window. The comparison between memory policies within each model keeps
that model's completion window fixed.

## Measured result — September 12, 2026

All 48 updates and all 12 complete trajectories passed the frozen checks. The
public result (`experiments/public/trajectory-replay.json`) retains each expected and observed
typed state. Total estimated token cost was **$0.08635149**, against $7.20 reserved;
all requests had reported usage. None reported cached tokens.

| Model / policy | Evidence payload bytes | Input tokens | Output tokens | Estimated USD |
|---|---:|---:|---:|---:|
| Pro / full history | 23,910 | 12,927 | 13,386 | 0.03503610 |
| Pro / notebook | 18,284 | 11,313 | 19,578 | 0.04623102 |
| Flash / full history | 23,253 | 12,714 | 6,962 | 0.00239742 |
| Flash / notebook | 17,875 | 11,181 | 9,337 | 0.00268695 |

The notebook reduced evidence payload size by about 23% and reported input tokens
by about 12%. Nevertheless, its output tokens increased 46.3% for Pro and 34.1% for
Flash, making it **32.0% and 12.1% more expensive**, respectively. Reducing stored
context did not reduce total inference cost in this run. Private usage records
classified 11,228 versus 17,447 Pro tokens and 5,186 versus 7,464 Flash tokens as
reasoning output. Those are subsets of output usage, not an additional charge;
these counters do not explain the cause of the difference.

Cedar's correction changed the cash proxy from 25 to 55 and its annual direction
from falling to rising. The agent retained the separate accounting-only forecast.
Harbor changed the investment outlook while retaining the historical cash result;
Mesa abstained after forecast withdrawal without forgetting its historical result.
No earlier model step failed, so recovery from an incorrect prior belief has **zero
observations** here. Fresh examples and repeated runs are needed before making
broader quality or cost claims.

The first accepted response was checkpointed, the process exited, and a fresh
process retrieved that same provider response with the same request and allowance.
There were two recovery GET attempts: the first stopped on the exact model-alias
check described above, and the second verified the checkpoint. Recovery submitted
zero replacement jobs. Across the campaign, 15 initially uncertain POST attempts
were reconciled with their original idempotency keys; the final ledger has 48
distinct accepted response IDs and 48 reservations. HTTP attempt count therefore
differs from logical paid-request count.

The observed gate ledger contains 48 admissions and 12 each of duplicate,
future-dated, and unapproved rejections, with zero paid calls for blocked events.
The private Voyage finished with confirmed event delivery. Client timings include
queue waits, timeouts, polling, and process restarts; they do not measure model
time to first token or isolate inference latency.
