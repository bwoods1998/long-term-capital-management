# A research investigation that can resume

The investigator follows one question through primary-source retrieval, calculations,
a draft, and an independent critique. It saves its work between calls. It can discover
an accounting distinction beyond the initial evidence packet; it can also fail. Neither
a fluent answer nor a critic's approval publishes anything automatically.

## Follow one assignment

The initial question asks whether changes in reported capital expenditures imply
changes in underlying infrastructure investment commitments. Read the
[source notes](../data/research/source-notes.json) and try
[Lesson 4](../lessons/04-research-loop.md) before inspecting the answer.

These commands inspect saved work locally, without model calls:

```sh
python3 investigator.py status INVESTIGATION_ID
python3 investigator.py inspect INVESTIGATION_ID
```

`inspect` includes private working hypotheses and tool results; it is not a public
export. Starting an assignment saves state without calling Sail:

```sh
python3 investigator.py start
```

Save the returned ID. The next command **can submit paid requests**:

```sh
.venv/bin/python investigator.py --voyage run INVESTIGATION_ID --seconds 300
```

The optional Voyage integration requires `requirements-sail.txt`; omit `--voyage`
to use the standard-library research runner. Reuse the same ID after an interruption.
The five-minute controller limit is separate from the saved work deadline. A timeout
does not cancel accepted provider work. Do not start a replacement merely because a
background response is still waiting.

## What each layer owns

| Layer | Responsibility |
|---|---|
| Sail inference | Proposes tool calls, drafts, and critiques |
| Local controller | Chooses permitted tools, validates arguments, enforces limits, saves state |
| Source store | Freezes approved documents, their retrieval dates, hashes, and exact passages |
| SQLite ledger | Reserves spending and preserves request identities, responses, usage, and history |
| Sail Voyages | Associates actual inference and tool stages with a private trace |
| Explicit review | Decides whether a checked result may enter the public record and future memory |

The default investigator uses DeepSeek V4 Pro with Flex background requests; its
critic uses Kimi K3 with ASAP requests. Those choices and dated prices are explicit
profiles in `portfolio.py`. They are experiment configurations, not a claim that a
particular model or completion window is universally best.

## Evidence, memory, and recovery

The model can search two registered Microsoft sources, retrieve checked facts,
calculate with compatible units and periods, and save hypotheses with invalidation
conditions. It cannot fetch arbitrary URLs or execute code. Source passages are data,
not instructions. Hashes and character offsets identify the text actually observed;
they do not establish whether its interpretation is correct.

Publication date, retrieval date, financial reporting period, and research date are
different. A frozen capture preserves what was retrieved, not proof of what a website
looked like at an earlier historical date. A newly discovered passage is not a newly
published disclosure.

Long conversations are compacted into a notebook retaining observed passages,
citation IDs, calculations, hypotheses, and search history. Repeated transcript text
and model reasoning are removed; full provider responses remain private in the
ledger. This is evidence memory, not preservation of every internal inference.
Reviewed conclusions from up to three prior investigations seed future assignments
as dated views to reconsider, never as fresh source evidence.

Each model step reserves its exact request under a stable key before submission.
Recovery retrieves a known response ID; uncertain submissions retain their original
idempotency key and allowance. Terminal failures do not trigger unlimited redrafting.
A critic can require one automatic repair. An explicit editorial amendment preserves
the original and requires a fresh critique before review.

## Review and publish

Inspect cited passages and qualifications before these separate local actions:

```sh
python3 investigator.py review INVESTIGATION_ID --reviewer 'Your name'
python3 investigator.py export public/investigations.json
```

Only reviewed records are exported. Export does not deploy the website. Public
records contain concise findings, source links, milestones, and measured usage;
credentials, full source captures, raw prompts, and provider responses stay private.

Compare model performance using the authored development cases in
`data/evals/research-cases.json`. Report failures and unknown usage alongside passes.
Reservations are spending allowances; token-price estimates are not reconciled bills.
Include failed attempts when calculating cost per useful reviewed result. Elapsed
workflow time includes waiting and interruptions, not just model computation.

The [Sailbox experiment](SAIL-PRODUCTS.md) demonstrated clean-VM checks and fresh-process
recovery of a synthetic accepted request without another submission. It did not run
live inference inside the VM or establish investment quality. Scheduling, broader
source coverage, and portfolio decisions remain subsequent work.
