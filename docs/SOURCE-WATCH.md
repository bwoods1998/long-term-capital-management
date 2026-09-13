# A source-update inbox

A persistent researcher should wake for useful evidence. `source_watch.py` checks
the two registered Microsoft pages and records changes without calling Sail,
changing checked facts, replacing frozen captures, or publishing a new conclusion.
It is a local source monitor, not an autonomous assignment scheduler.

## Run it

The investigator must already have captured the registered sources. Seeding reads
those existing files; it never downloads a missing baseline.

```sh
python3 source_watch.py seed
python3 source_watch.py scan
python3 source_watch.py status
python3 source_watch.py watch --seconds 21600
```

`scan` performs at most one bounded fetch per due source. Checks are one hour apart.
The next slot is persisted before downloading, so a crash or restart does not
create a rapid retry loop. Failed fetches back off, up to a day. A process lock
prevents overlapping watchers. The bounded watch exits after its requested local
duration; it is not installed as a desktop service or a cloud worker.

## What a change means

Every distinct raw capture is retained privately with its hash and retrieval date.
A different page is a candidate for inspection, not proof of a new disclosure or
a material change. The original publication date is separate from the date on
which this project first observed the candidate. This monitor checks existing
URLs; it does not discover a new earnings release or filing.

The first live check found an instructive false alarm: both Microsoft pages change
their request trace identifier on each fetch. Inspection showed that the second
normalized line was the only difference. Those two candidates were rejected;
their original observations and review decisions remain in the private ledger.

The versioned comparison now ignores only that exact trace-line format in that
exact position. It preserves complete raw captures and every other line, including
financial figures and dates. Repeated content with a different trace does not
create another substantive candidate. Tests show that a changed cash figure still
does. Earlier raw-hash observations retain their earlier comparison version.

## Curate a candidate

```sh
python3 source_watch.py inspect VERSION_ID
python3 source_watch.py review VERSION_ID reject --reviewer 'Local Editor'
# Or, after checking the source:
python3 source_watch.py review VERSION_ID accept --reviewer 'Local Editor'
```

Inspection shows a local diff against the original frozen research baseline.
Accepting means the capture is suitable for further curation. It does **not**
approve any financial facts, change the evidence packet, start an investigation,
or authorize publication. A changed number still needs its units, period,
definition, and source checked before it enters a new packet. Decisions are final
for that content version; a later genuinely different capture has its own record.

The [reviewed source handoff](SOURCE-CURATION.md) can now bind an accepted
substantive capture to a manually checked packet and exact item-level provenance.
That private bundle needs its own factual approval before the
[durable local queue](RESEARCH-QUEUE.md) can copy it into a new assignment.
The queue never directly imports an unchecked candidate. Existing jobs and the
baseline cache remain frozen, so rerunning an old assignment alone does not
consume newer evidence. Neither candidate acceptance, bundle approval, nor queue
completion reviews or publishes the resulting research report. This route has
an offline synthetic proof; the live watch has not supplied a substantive update.

## What is measured

The private ledger records each fetch, result, comparison algorithm, raw version,
first observation, next due time, consecutive failures, and curation decision.
Local status exposes registry metadata and counts, not full source text, raw
errors, or reviewer names. Source checks make zero model calls and leave research
spending, reviewed thesis history, and public snapshots unchanged.

The archive grows with distinct raw captures. Long-term deployment will need a
declared retention policy and an always-on host; the present bounded run uses the
local machine. No brokerage state participates in this monitor.

## First repeated live check

At 00:44 UTC on September 13, both registered pages were fetched again from their
persisted due times. Their complete raw captures changed, but the versioned
comparison classified both as `metadata_only`: the observed request-trace line
changed and the remaining normalized content did not. The earlier raw-hash
candidates and their rejection records remain intact. No new candidate, checked
fact, or paid investigation was created. Later checks continue under the same
hourly schedule and bounded session deadline.
