# Night shift

**Can a persistent group of agents build a better map of the AI spending cycle than a first-pass analyst?**

An overnight research campaign follows NVIDIA, TSMC, Broadcom, Constellation, Vertiv, Microsoft, Amazon, Alphabet and Meta through their primary financial disclosures.

[Public checkpoint](https://blakewoods.us/portfolio/) · [Latest measured status](../public/overnight-research.json) · [Controller](../overnight.py)

## The work

Each company gets independent DeepSeek Pro and Kimi analyses, an opposing Kimi K3 critic, a revision, and two anonymously labeled comparisons. A final pass turns unresolved disagreements into concrete next research questions. The company cases feed two independent maps of spending dependencies, followed by critique and revision.

The evidence starts with **12 primary documents and 29 exact passages**. Cash flow, investment, currency and fiscal period stay attached to each number. A current filing can still leave AI-only economics unknown.

| Sail capability | What this run tests |
|---|---|
| Background Responses / Flex | Persistent dependent research that can wait for efficient capacity; accepted requests retain their identities across restarts. |
| Multiple models | Whether opposing analysis corrects financial interpretation, rather than merely changing the prose. |
| Supercache | Fresh risk questions reuse the previously purchased nine-company corpus. New financial disclosures remain separate; cache hits are measured, not assumed. |
| Voyages | One trace connects the analysts, critics, revisions and their request costs. |
| Sailbox | An isolated cloud verifier checks actual company cases against frozen evidence, with sleep/resume and local-versus-remote result comparisons. |

LoRA training is not part of this run. The useful prerequisite is a collection of validated corrections; these unreviewed drafts are not a training set.

## What counts as progress

- Source quotations match the frozen passages; numerical literals and compatible cash-flow arithmetic pass deterministic checks.
- Independent judges explain whether the revision improves on the original. Their preferences are fallible opinions, not an accuracy benchmark.
- Shared risks distinguish disclosed relationships from inferred economic connections.
- Every missing result, unresolved disagreement, known cost and unknown-cost reservation remains visible.

A format-valid answer can still misinterpret a filing. Company cases and the dependency map remain drafts until their financial claims are reviewed.

## Operating limits

The campaign admits work for up to eight hours, with six requests in flight and a fixed plan of at most **86 logical requests / $33.20 in inference reservations**. Unneeded repair calls are skipped. It stops when the work is complete rather than generating filler. The original shared budget still applies; unresolved calls retain their holds. A final 30-minute window retrieves accepted work without admitting new requests.

The coordinator and private ledger run on the plugged-in MacBook. Sail runs inference and the isolated cloud verifier. Voyages observes the workflow; it does not host the coordinator. A disconnected MacBook can delay local progress and the final publication.

The public page shows a dated checkpoint. Its final automatic update contains only typed progress and cost measurements. Detailed company drafts, comparisons and the morning report stay private in `.data/overnight/<campaign-id>/morning.md` for review. There is no brokerage connection or trading in this campaign.

## Resume or inspect

```bash
systemctl --user status portfolio-night-shift
journalctl --user -u portfolio-night-shift -n 20 --no-pager
.venv/bin/python overnight.py status CAMPAIGN_ID
.venv/bin/python overnight.py report CAMPAIGN_ID
```

Request identities, source hashes, code hashes and results are preserved in the existing private SQLite ledger. Restart the same saved campaign; do not create another campaign to replace an uncertain submission.
