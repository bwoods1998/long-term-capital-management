# Historical SIP completion and unresolved gaps

`completion-config.json` still opts the House supervisor into full historical-store completion.
The worker uses the existing nightly process lock, data-box operation lease, and backfill exclusion.
Historical relay work defers before the nightly quiet window. It neither logs into ThetaData nor
changes a provider subscription. Matching House/data tools must be released together: the new House
relay needs the data box's `sip-status` and `sip-plan` commands. Historical operations, manual relay,
and nightly already push these tools while holding their operation lease.

The SIP queue covers stock/ETF roots with NBBO files from the fixed Train start through the fixed
Holdout end. Its identity includes those roots and historical source symbols, session hours, windows,
dates, source, and coverage schema. XSP/SPXW retain their separate underlying path. The queue does not
cover pre-Train extensions or forward days.

## Progress and readiness

- `sip`: scans at most 31 calendar days per step. Each root's attempt is committed to the private
  `sip-progress.sqlite` before requesting its data. Complete roots can be ingested while another
  root remains unresolved, so a missing root cannot strand all later dates.
- `sip_gaps`: the initial scan finished with unresolved work. Retries visit at most five due dates
  per step, with three automatic attempts per root and persistent exponential backoff. Reservations
  survive a crash; an ingest whose acknowledgement was lost resolves only after current file/grid
  verification. A final unacknowledged or uncertain write gets one separately reserved read-only
  recovery observation, with no additional provider attempt. A failed/incomplete recovery is recorded
  and cannot repeat indefinitely. Exhausted roots then count as `deferred`, remain incomplete, and
  cause no further provider requests or data-box wakeups until reconsidered. There is no images-ready
  certificate while gaps remain.
- `gym`, `gate`, `calibrate`: reached only with complete queue receipts. Actual canonical file hashes
  and current journal identities are compared to those receipts before each source snapshot, under
  the lease for the exact box being checkpointed. Changed files reopen gaps; changed root/source/
  calendar plans fail closed and require a reviewed new queue. Stale staging source/universe metadata
  is rejected. The staged version includes the source-receipt hash, so an older SOURCE-only image
  cannot be reused as this candidate.
- `complete`: `images-ready.json` certifies an **immutable staged checkpoint pair**, with exact IDs,
  original source receipt, source verification times, requested identity, retained roots, and
  calibration identity. Calibration binds the exact expected source/pair/specification under its
  lease; repeated partial finishes retain the original input-pair identity independently of the
  checkpoint used for a later fit. A completed certificate does not poll or wake the collection box.
  Later collection changes do not rewrite the historical certificate for those sealed bytes.
- `review_required`: the explicitly requested configuration/version/source identity changed. The old
  certificate is archived as `images-ready-archived-*.json`; it is never silently reported as satisfying
  the new request. Review a new adoption cycle in a new private state directory, retaining the original
  queue/certificate. Do not delete its attempts or reinterpret it as the new plan.

On adoption of this code, legacy schema-1 completion records are archived and their cursor is rescanned
from the historical start. Old `images-ready.json` becomes `images-ready-legacy-sip-v1.json`. Existing
sealed checkpoints and the active `images.json` pair are unchanged. Independently verified current
images can continue serving research while this replacement queue is incomplete.

The SIP proof is explicitly limited to the fixed historical stock-underlying completed-minute grid.
A gate image can also retain forward files; **this historical certificate does not certify those
forward files**. Newly executed nightly work verifies the full current per-day SIP grid before gate
copy/checkpoint and retains that proof with the day. A resumed `pulled` marker cannot bypass it.
Legacy cached checkpoints without that proof are labeled `legacy_unverified`; today's mutable data-box
verification is never attached retroactively to them. Existing schema-1 ready-file auto-adoption remains
a separate protocol limitation; this change does not migrate readiness/settings or alter an active grant.

## Evidence, canonical protection, and retry review

A full session grid is the explicit canonical-ingest requirement: 390 completed minutes on a normal
session, 210 on a half day. It does not establish that every absent provider minute was an error.
Halts, no-trade minutes, vendor gaps, or incorrect upstream data can all leave work unresolved. The
worker never fills missing bars or volumes with zeros, interpolates prices, or waives a minute.

Each packet is independently validated for its full minute grid, OHLCV constraints, canonical root,
and source symbol before canonical write. A sparse/empty packet cannot replace a better canonical
underlying file. SOURCE alone is insufficient: legacy labeled files are read and their hash/grid
validated. Source-symbol receipts missing from otherwise complete legacy files remain explicitly
unknown; the status verifier records the expected historical alias.

Partial packets stay outside the store in private `/data/work/sip-partial-DATE-ROOT-SHA256.json` files.
Identical packet retries use the same path and bytes, so they do not grow quarantine storage. The
packet carries a digest of the decoded provider response; receipts retain packet/file hashes, source,
coverage counts and missing minutes. Quarantine packets are not ingested or copied as canonical data.
The SQLite attempt ledger retains each attempted receipt and all reconsideration evidence. Back up
that owner-private database with completion state. It contains no credential or fitted trading model.

Finalized historical OHLCV has no publication/as-of receipt. Its grid coverage is labeled
`finalized_without_publication_receipts`; even a complete grid does not make historical strategy volume
available. This repair does not change the volume API's unknown values or prove live/replay information
parity. Actual live first observations keep their separate checkpoint semantics.

After genuinely new data/provider evidence, an operator can grant one additional bounded retry batch
for a specific unresolved root without erasing lifetime attempts:

```sh
python3 scripts/data/complete.py --state /PRIVATE/STATE reconsider \
  --day 2022-03-08 --root PLTR \
  --evidence 'Specific provider case or dated observation showing a new packet is available'
```

Run this while the local nightly supervisor is stopped through its normal stop mechanism; its lock
prevents concurrent controller edits. Re-enable the supervisor normally afterward. The same evidence
text is idempotent and never repeatedly replenishes the budget. The next retry first checks current
canonical bytes; an independently repaired complete file can resolve without another provider request.
If the provider still supplies sparse data, the root stays unresolved. Changing the required plan,
source box, or image universe is an adoption review, not a retry-budget reset.
