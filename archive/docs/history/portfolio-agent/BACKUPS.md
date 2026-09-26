# Private recovery snapshots

The cloud supervisor requests a snapshot every 30 minutes and after stopping the service. R2 stores immutable artifacts; the final manifest is uploaded only after every referenced object has a confirmed upload receipt. Each file records its original and compressed SHA-256 and size.

Unchanged artifacts reuse an earlier object from the **same service**, including across snapshot directories. Local confirmation records avoid uploading or recompressing those bytes again. Retain referenced objects when pruning snapshots: deleting an old snapshot directory can break newer manifests that reference it.

Timestamped market responses and metadata are packed by capture date into SQLite bundles. A `market-receipts-v1` row retains every original relative path, payload and SHA-256. Packing changes storage layout; it does not discard price evidence. Research, request, portfolio and policy databases remain ordinary independently checked SQLite artifacts.

## Restore

1. Stop writers and keep new research admission disabled. Download a chosen manifest through the authenticated supervisor backup endpoint.
2. Verify the manifest against the hash in its object key. For every row, require a same-service object key ending in its declared compressed SHA-256; the object may belong to an earlier snapshot.
3. Download and verify compressed bytes, decompress, and verify the original size and hash. Write ordinary artifacts to their recorded paths inside a new private directory. Run SQLite `PRAGMA quick_check` on restored databases.
4. Expand market bundles after verifying them:

```python
from portfolio_runtime.supervisor_guest import restore_market_receipts

for row in manifest["files"]:
    if row.get("format") == "market-receipts-v1":
        restore_market_receipts(destination / row["path"], destination)
```

5. Install the runtime matching the saved host manifest. Reconcile accepted provider IDs, unknown cost holds and the paper ledger before granting new authority. Never turn a lost submission receipt into a fresh request identity.

Snapshots taken while research is running are individually consistent databases, **not an atomic snapshot across databases**. Restoring files alone does not authorize a restart. The supervisor retains the existing stopped service identity during a reviewed code release; a lost disk requires explicit reconciliation.

Offline tests cover a full 120-hour fixture with 6,000 price/metadata files, exact restoration, shared objects across snapshots and failed-upload recovery.
