# Weekday launch audit · September 13, 2026

**The cloud rehearsal is progressing after fixes to credit admission, backups and reporting.** This is an audit during the test, not a completed five-day reliability record.

The rehearsal runs Sunday **12:45–17:45 Pacific**. The same service and paper account remain scheduled for **Sunday September 13 at 21:00 through Friday September 18 at 21:00 Pacific**. Accepted requests settle after the rehearsal admission deadline before its completion email. Brokerage execution remains disabled.

## Live evidence

At **16:10 Pacific**, the public checkpoint showed **179 completed requests out of 196**, **five pending**, and **$9.816789780** in recorded inference cost. The remaining 12 were unsuccessful terminal requests, retained in the record. These are cumulative service counters, not success rates for investment decisions. The deployment resumed at 16:02; new requests, an allocation review and its critic subsequently completed and appeared in the public history.

The paper ledger retained its original **$100,000 virtual cash**, account anchor and pending allocation. Sunday research produced no market fills or invented returns. Subsequent market observations are required before performance can be measured against the S&P 500 Total Return benchmark.

## Findings and deployed corrections

| Finding | Correction and verification |
|---|---|
| Visa’s chart encoded a historical dividend with a map key one day apart from its explicit effective date, rejecting the entire chart and threatening the pending multi-stock fill. | The parser now uses the validated event date rather than equating it with the provider’s map key. Original responses remain preserved. Future or malformed actions and unhandled actions during ownership still block execution; historical pre-account dividends do not fabricate cash flows. |
| One session stopped admitting useful work with only a three-cent frozen allowance, despite available provider credit. Its heartbeat still looked healthy. | Available-credit mode now checks live authority and actual commitments for each reservation. The initial session snapshot is an audit record, not an hourly cap. Regressions cover the three-cent case, top-ups, falling credit, unknown costs and branch reservations. Fresh live dispatch was verified after deployment. |
| Market receipt files accumulated fast enough to threaten the backup manifest limit during the week. | Exact receipts are packed by capture date, with per-file hashes and verified restoration. Deterministic compression and confirmed object reuse avoid repeatedly uploading unchanged history. A 120-hour, 6,000-receipt fixture passed. |
| A prior low-credit warning could suppress the later message that research actually stopped for funding. | Funding exhaustion now has a separate once-per-episode alert. Unknown terminal costs also prevent a false clean-completion message. The alert branches passed controller tests; actual funding was not deliberately exhausted during this audit. |
| ASAP comparisons were rejected for the transport difference that the experiment intentionally changes; several window responses exhausted their output allowance. | The evaluator normalizes only the documented completion-window transport treatment. New matched window triplets use the same 16,384-token allowance. Existing requests and failures remain immutable. |
| Empty work queues and hourly transitions could confuse the public status and allocation display. | Checkpoints distinguish scheduled waiting, funding waits and active work. Coverage is labeled per session; costs and requests remain cumulative. The last published reviewed allocation remains visible through session changes. Reaffirming identical targets is labeled a hold; it preserves the original pending order and timestamp. |

No fixed inference dollar cap was introduced. New work still requires current provider credit, reserves for accepted requests and hosting, and the configured small balance floor. Unknown outcomes retain their reservations rather than being retried under new identities.

## Recovery and verification

The runtime was updated on the existing Sailbox after pausing and verifying a fresh backup. All 22 installed source/configuration files matched the reviewed manifest before authorization. The same request journals, paper ledger, configuration and schedule were retained.

The first live backup under the new format completed in **45 seconds** with **87 artifacts**, down from 484 in the preceding snapshot. An isolated restore verified every compressed and raw hash, all **22 SQLite databases**, and **398 exact market receipts**. All 129 requests and 11 paper events checked from the earlier audit snapshot remained intact. This proves recovery of those records; independently copied databases still require cross-journal reconciliation before restoring trading authority.

The second live snapshot finished in **seven seconds**, reused 74 existing objects and uploaded **90% less artifact data**. Its full restore also passed, preserving 166 prior requests and all prior market receipts and paper events. The bucket has no completed-object expiration rule; shared objects must also be preserved during any manual cleanup.

Validation: **310 Python tests, 50 supervisor tests and 70 website tests passed**. GitHub CI passed for runtime commit [`1e00841`](https://github.com/bwoods1998/long-term-capital-management/commit/1e0084115250f31051b6ba187ab4f90c099511e7). Website commit `0c9d16b` was deployed and checked on mobile, including the existing stock-exchange page. Live publication and fresh request completion were independently observed. The allocation-wording correction is in commit [`760176a`](https://github.com/bwoods1998/long-term-capital-management/commit/760176a8e79742243d82dd900749e11daca06cc3); its full test suite and [GitHub CI](https://github.com/bwoods1998/long-term-capital-management/actions/runs/34789140120) passed, including preservation of the original pending order. The final release adds the Visa parser fix in [`08dc9ab`](https://github.com/bwoods1998/long-term-capital-management/commit/08dc9abfb5f366b623f63a79ab6f6fbb4b993871). Its full suite and [CI](https://github.com/bwoods1998/long-term-capital-management/actions/runs/34789454411) passed. Its regressions cover a modeled multi-stock Monday fill and unchanged protection against unhandled actions during ownership; the captured live Visa response also parsed successfully offline.

## What the Sail experiments established

The rehearsal uses hosted execution, multiple inference profiles, matched completion-window experiments, retained research, cache comparisons and Voyage events. A delivered trace event proves telemetry delivery, not agent effectiveness. Inference requests carry Voyage correlation headers, but provider-side model-call attribution counts were not independently exposed by the documented API; explicit task spans and execution correlation are not yet instrumented.

At an earlier fully settled cache checkpoint, **30 reads reused 2,519,040 tokens**. Compared with ordinary cached-input pricing, those same tokens saved **$0.2267**, against a **$2.9395 write**: net **−$2.7128**. Conditional break-even at that token mix was 389 useful reads total, within the prefix's lifetime. This is measured reuse, not demonstrated net savings. Sail documents the write premium, read discount and 24-hour lifetime in its [Supercache reference](https://docs.sailresearch.com/supercache).

Critics have requested revisions for unsupported financial claims and inconsistent sector comparisons. No research policy has been promoted, and no forward investment outcome exists yet. Passing source checks does not establish that every assertion is correct or that a portfolio will outperform.

## What the week must prove

- Broader company coverage and decision-specific evidence: valuations, sector-appropriate accounting and evidence that could overturn proposed holdings.
- Actual session fills, benchmark observations and dated portfolio outcomes that feed subsequent reviews without hindsight.
- Useful completion rates, latency and total cost for matched Sail treatments, including failed responses and cache setup costs.
- Sustained cloud operation, periodic recoverable backups, funding recovery and honest completion reporting.

The rehearsal is still underway. Saved equity captures and the total-return benchmark validated through Friday’s close; this does not certify Monday delivery. Unhandled corporate actions during ownership still require explicit accounting before trading or marking. Full-week reliability, profitable decisions and investment-policy self-improvement remain unproven. Available credit can run out; low-funding and stopped-work alerts are configured, and top-ups permit automatic recovery. There is no unattended guarantee against provider outages or unreconciled accounting.

[Live portfolio](https://blakewoods.us/portfolio/) · [Research history](https://blakewoods.us/portfolio/research/) · [Operations](../OPERATIONS.md) · [Backup recovery](../BACKUPS.md) · [Evaluation](../EVALUATION.md)
