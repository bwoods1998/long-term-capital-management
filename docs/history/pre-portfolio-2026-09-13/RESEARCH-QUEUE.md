# A durable local research queue

`research_queue.py` turns explicit assignments into a small unattended workflow.
It runs the existing investigator, including evidence tools and bounded critique.
It never decides which source change deserves an assignment, reviews a result,
publishes a page, or places an order.

The current pilot permits **two durable jobs**, each with DeepSeek Pro research,
Kimi K3 critique, and two to four research turns. This is a session limit, not an
unbounded scheduling service. Job records and budget history cannot be deleted
through the queue. Existing research and private account state remain separate.

## Enqueue explicitly

For a baseline assignment, the checked packet and both registered source captures
must already exist. The queue reads the frozen baseline cache. A separately
approved [curation bundle](SOURCE-CURATION.md) supplies an alternative set of
checked inputs; raw source-watch candidates are never direct inputs.
Choose a stable nonsecret job key and explicit timezone-aware due/deadline values:

```sh
python3 research_queue.py enqueue lease-scope-review \
  --question 'Which evidence distinguishes accounting changes from investment changes?' \
  --packet data/thesis/msft-ai-infrastructure.json \
  --due YYYY-MM-DDTHH:MM:SSZ \
  --deadline YYYY-MM-DDTHH:MM:SSZ \
  --max-turns 4
```

Replace the timestamp placeholders. The deadline must be in the future and within
one day of enqueue. Enqueue performs no network request, creates no model request,
and reserves no money. It freezes the complete checked packet, registered source
artifacts, source hashes, question, model profiles, limits, and schedule privately
in the shared SQLite ledger. Reusing the key with identical inputs returns the
same job; changed inputs produce a collision error. Later cache changes cannot
refresh that job's evidence.

For a reviewed source update, replace `--packet ...` with `--bundle BUNDLE_ID`.
The two inputs are mutually exclusive. Enqueue validates the approval receipt and
current substantive source content, then saves the selected packet, complete
source snapshots, and receipt in one transaction. It does not copy facts from the
old packet or fill missing captures from the baseline cache. The bundle's checked
evidence date remains the assignment's cutoff; enqueue does not make it fresher.

The current pilot's two durable slots have already been consumed. These commands
describe the supported assignment contract; they do not grant a third job. The
new bundle route has an isolated synthetic integration proof and creates no new
live paid assignment in this session.

**Evidence freezes at enqueue; reviewed memory freezes when the investigation is
first created.** Memory can therefore be newer than the packet. It remains a dated
prior view to recheck, not evidence of a new disclosure. A baseline assignment uses
the enqueue date as its source cutoff; a curated assignment retains its bundle's
checked evidence date. This distinction also holds if a process stops between
creating the investigation and attaching its frozen source state.

## Run, pause, resume

These inspection and control commands make no API calls:

```sh
python3 research_queue.py status
python3 research_queue.py pause lease-scope-review
python3 research_queue.py resume lease-scope-review
```

The following commands **can submit paid Sail requests**:

```sh
python3 research_queue.py advance
python3 research_queue.py run --seconds 1800
```

One controller owns the queue through an OS lock. Due assignments run in due-time
order, with enqueue order breaking ties. A waiting first assignment retains its
place; pausing it lets another due job proceed. Each advance performs at most one
model submission/retrieval and the resulting local tools. A pause takes effect at
step boundaries; an already admitted request may finish. Resume retains the same
investigation and request identities. No external cron, desktop configuration,
cloud worker, or new hosting account is required. The local process must stay
alive for unattended progress.

A controller time limit is checked between steps. An in-flight bounded network
operation can finish after that limit. The immutable job deadline prevents another
queue step from starting afterward. Accepted provider requests may still finish;
the deadline does not cancel them or remove their reservations. A new assignment
is not a replacement retry for uncertain accepted work.

## What recovery preserves

The queue derives the investigation UUID from its frozen job key and input hash
before creating an investigation. A crash between creation and attachment finds
that same UUID and accepts it only if it is pristine and matches the assignment.
Frozen sources enter the investigation before its first paid step. A transaction
attaches the queue identity and source state together.

An identical existing job key returns its frozen assignment before consulting
live bundle freshness. Later source changes can block a new enqueue, but cannot
replace the evidence of an existing job or its accepted request. Curated jobs
validate their saved receipt against their saved packet and snapshots, without
reloading the current source inbox or bundle record. Legacy assignments retain
their original serialized inputs, hashes, and derived investigation identities.

The investigator's normal request ledger still owns idempotency and known response
IDs. A resumed queue retrieves known accepted work. An uncertain submission retains
its original request, credential binding, task key, and allowance. It does not
receive a fresh request key merely because observation failed. Uncertain work past
the transport's recovery window requires manual reconciliation.

Managed investigations cannot be advanced through the standalone investigator
CLI. Its guard requires the active queue controller, checks the frozen assignment,
source versions, pause/deadline, and spending envelope. This includes the brief
creation-to-attachment interval. Ordinary investigations keep their existing
behavior. Owner access to Python and credentials is not a sandbox; this protects
the application's supported entry points.

## Spending arithmetic

With `T` research turns, the maximum ordinary workflow has:

| Calls | Maximum reservations |
| --- | ---: |
| Pro research | `T × $0.20` |
| Pro repair | `$0.20` |
| Kimi critique and recheck | `2 × $1.00` |
| Total at four turns | **$3.00** |

The queue permits one repair and no automatic editorial recheck. Before each new
reservation it verifies that the shared ledger has room for the job's remaining
worst-case allowance. Existing known responses can still be retrieved when no
additional spending room remains. New request profiles must match the frozen
profiles; old response retrieval does not adopt new pricing or request settings.

This capacity check is not a separate escrow: other authorized workflows can
consume shared room and leave a job in `budget_wait`. The portfolio ledger's
atomic reservation check remains the final global spending gate. No allowance is
refunded or reset, and the queue never raises the shared budget. Costs from returned
token usage remain estimates, separately reported from permanent reservations.

## Terminal outcomes and next action

| Queue state | Meaning |
| --- | --- |
| `awaiting_review` | Research and critique finished; owner review is still required. |
| `needs_attention` | A bounded failure, exhausted research/repair path, or changed contract stopped work. |
| `deadline` | The job cannot start another step; already accepted provider work may still finish. |
| `budget_wait` | Shared room is insufficient for the remaining worst-case workflow. |
| `paused` | Explicitly paused before the next step. |

A failed or invalid response ends the job without a replacement draft. A separate
editorial amendment is outside the queue's mandate and is rejected before changing
the draft. A future editorial handoff would require its own bounded grant.
After inspecting a successful investigation, the owner can use the existing
explicit `investigator.py review` and export flow. Queue completion itself changes
neither reviewed thesis history nor public artifacts.

Offline tests exercise duplicate keys, immutable inputs, source-cache drift,
creation/attachment crashes, accepted-response recovery, FIFO/pause behavior,
competing controllers, CLI bypass prevention, deadlines, budget exhaustion,
failed outputs, and the complete seven-call repair path at exactly $3 reserved.

## A versioned response to the first planning failure

One original queued assignment exhausted all four research turns requesting tools
without producing a report. Its `needs_attention` outcome, request identities, and
costs remain intact; no higher turn limit or retry was granted. Another passed its
critic but still needed substantive corrections in independent review.

New investigations use `prerequisites-last-v2`. They state the remaining turns on each
research request and reserve the final turn for a report without tools. Missing
passage, calculation, or hypothesis checks stop that final request before spending.
A four-turn assignment therefore has at most three gathering turns. This may stop
an underprepared run earlier and does not guarantee a useful report. On the last
gathering turn, only tools for missing prerequisites are offered; the model must
still choose meaningful arguments. Existing unversioned and `synthesis-last-v1`
jobs keep their policies, and already reserved requests retain their exact bodies.

The [v1 follow-up](../../../experiments/data/experiments/synthesis-policy-2026-09-13.json)
is a separate standalone proof, outside this pilot's two job slots and still inside
the shared budget. It preserves the failed question and evidence for comparison;
it neither resets that job nor spends its allowance. The proof also stopped without
a report: three requests gathered passages but left calculation and hypothesis
checks missing. It cost an estimated $0.006013744 and stopped before reserving the
final request. See the [measured turn-policy result](RESEARCH-LOOP.md); one follow-up
does not establish improved quality.
