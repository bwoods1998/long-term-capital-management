# One source corpus, several research questions

## Observed result — September 13, 2026 UTC

All nine company questions completed. Every read reported **14,336 Supercache
tokens**, or **129,024 reused tokens** in total. No second write occurred.
[Machine-readable result](../../../experiments/public/shared-research-context.json)

| Recorded expense | Estimated USD |
|---|---:|
| Initial write request, including output | 0.51841595 |
| Nine later requests, including output | 0.07046359 |
| Total | **0.58887954** |

The initial source-index generation reached its 8,192-token output limit, while
Sail reported 14,336 tokens written. Its original incomplete result remains
unchanged. A separate, immutable continuation receipt permitted only the nine
original read attempts; their returned counters then demonstrated actual reuse.
The incomplete source index is not a completed research result.

Repricing the same observed token counts gives $0.10374930 with ordinary cache
hits, or $0.13600530 if the reused tokens instead missed ordinary cache. Those are
counterfactual calculations, not alternate executions. This short experiment did
**not** recover the write cost. Its useful findings are confirmed cross-company
reuse and recovery without buying another write. The financial drafts still need
source review before they can become published company cases.

## Design

This separately bounded pilot uses a shared collection of issuer disclosures for
cross-company research. One supervised Supercache write creates a source index;
nine to twelve declared questions then reuse that exact prefix. Research drafts
remain private pending separate source and financial review. The export contains
request outcomes, token counters and cost comparisons only.

Sail documents a 24-hour prefix lifetime, an explicit
`metadata.supercache_write: "24h"` write, and automatic matching reads. Writing
again renews the lifetime; reading does not. Its documentation calls for at least
1,025 reusable tokens. Our substantial-prefix check is a byte guard, not a token
count; later reads require confirmed returned write counters. A read during this
pilot does not demonstrate the complete lifetime.
[Supercache documentation](https://docs.sailresearch.com/supercache)

## Frozen allowance

Kimi-K2.6 Flex is fixed at $0.35 input, $0.10 regular cached input and $2 output
per million tokens, checked September 13, 2026. Requests have at most 96,000
serialized bytes and 8,192 output tokens. Using the full byte limit as a
conservative input-token bound, the write costs at most
`96,000 × 100 × $0.35 / 1M + 8,192 × $2 / 1M = $3.376384`.
Its allowance is $3.50. Each read reserves $0.10; twelve reads plus the write
therefore reserve **at most $4.70**. Nine reads require $4.40.
[Dated rates](https://docs.sailresearch.com/pricing)

These request allowances share the original ledger and its active budget policy.
They do not raise the $96 inference ceiling or the overall $100 authorization.
The single pilot keeps its own cumulative admission cap even after any requests
settle. It cannot replace a failed write or add unreviewed questions. Earlier
cache experiments, deadlines, failures and reservations remain unchanged.

## Accounting contract

Let `i` be all input, `c` all cached input, `s` Supercache reads, `w` Supercache
writes and `o` output. With ordinary rates `I`, `C`, `O`, the estimate is:

```text
((i-c-w) × I + (c-s) × C + s × 0.1 × C + w × 100 × I + o × O) / 1,000,000
```

Written tokens are removed from ordinary input, so the write is priced once.
Supercache reads are already inside cached input. All explicit-pilot counters
must be present and consistent: `s <= c` and `w <= i-c`. Ambiguous overlaps,
missing counters or an unexpected write on a read request retain an unknown
cost and its full allowance. Other request profiles still reject writes.
[Token accounting fields](https://docs.sailresearch.com/usage-endpoints),
[Responses support](https://docs.sailresearch.com/support)

Two counterfactual estimates hold observed input and output token counts fixed.
One prices Supercache reads as ordinary cache hits; the other treats those tokens
as misses while keeping the actually observed regular cache hits. Neither is an
observed alternate execution: regular caching might behave differently without
the write. Report the upfront write alongside read discounts; this short pilot
does not claim that Supercache breaks even or improves research quality.

## Prepare, inspect, run

The ignored local specification has exactly two fields:

```json
{
  "prefix": "Reviewed shared source corpus and source identifiers...",
  "tasks": [{"id": "company-question", "symbol": "MSFT", "question": "A source-grounded question..."}]
}
```

Supply nine to twelve unique task IDs in the real specification. The example is
abbreviated. Preparation validates every complete request and freezes its prefix,
body hash, profiles, code hashes and deadline without buying inference:

```sh
python3 supercache_experiment.py prepare .data/shared-context-spec.json --deadline YYYY-MM-DDTHH:MM:SSZ
python3 supercache_experiment.py status CAMPAIGN_ID
```

After reviewing that exact frozen protocol, this command **can buy inference**:

```sh
.venv/bin/python supercache_experiment.py --voyage run CAMPAIGN_ID --seconds 300
```

Resume the same campaign. Known responses use their original accepted IDs, and
an uncertain submission retains its original idempotency key. A crash after
reservation but before step attachment finds that same request. New code or a
changed prefix blocks new admissions; already reserved work can still be observed.
Voyages trace the actual model stages and can attach across controller invocations.
The local controller owns inference and accounting; this pilot does not run it
inside a Sailbox.

## An incomplete write response

The original write reached its 8,192-token output limit. Sail returned an
`incomplete` response with reason `max_output_tokens`, 14,336 written prefix
tokens, and complete usage costing an estimated $0.51841595. The frozen policy
stopped with `write_unconfirmed`; that result and its failed Voyage are retained.
Reported write tokens describe a cache operation, while the unfinished source
index describes generation. They are separate outcomes. Sail's documentation
does not explicitly guarantee retention following an incomplete generation.

A separate local review receipt may authorize **attempts of the original nine
reads** using those reported write counters. It binds the original protocol,
request, response, usage, result, read bodies, prices, expiry and newly reviewed
code hashes. It creates no replacement write or new questions. Failed, cancelled,
counterless, over-budget or differently incomplete writes cannot use it. The
original $4.40 allowance and deadline still apply. This offline command records
the separate decision; running the controller afterwards can buy the remaining
inference:

```sh
python3 supercache_experiment.py authorize-reads CAMPAIGN_ID --reviewer 'Local reviewer'
```

The continuation has its own Voyage. `write_confirmed` stays false and
`original_write_outcome` stays `write_unconfirmed`; a separate continuation field
explains why reads were attempted. Only returned read counters can demonstrate
reuse. An authorized attempt is not proof of retention or a completed draft.

```sh
python3 supercache_experiment.py export CAMPAIGN_ID public/shared-research-context.json
python3 -m unittest discover -s tests -p test_supercache_experiment.py
```

Export never deploys the site or publishes generated research. Completing these
questions supplies candidate material for the living case; independent review
must decide which claims are supported and what to investigate next.
