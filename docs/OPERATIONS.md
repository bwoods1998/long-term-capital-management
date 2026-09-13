# Read the research ledger without advancing it

```sh
python3 operations.py
```

This command reads the existing local SQLite ledger in read-only mode. It makes no
API calls, loads no credentials, fetches no source documents, and never resumes a
model request. A missing ledger produces an error rather than an empty new one.

The summary separates three things that can otherwise look deceptively similar:

- **Provider state:** whether an admitted request is waiting, completed, or ended
  unsuccessfully. A completed response can still contain a bad answer.
- **Research review:** how many investigations were explicitly reviewed, remain
  unreviewed after a critic pass, or stopped for attention. A critic pass does not
  count as editorial acceptance.
- **Money:** known token-price estimates, requests with unknown usage, and permanent
  reservation allowances. An allowance is not a charge. Unknown usage is never
  silently treated as zero.

One read transaction gives a consistent view even while a controller is running.
The output contains counts and fixed labels; it excludes prompts, responses,
private errors, reviewer names, source text, and account state. Unknown schema
values or a changed reviewed investigation stop the summary for local inspection.

Costs cover the shared **portfolio research ledger**, including failed research and
the separate evaluation protocols. The original extraction experiment has its own
ledger, and Sailbox charges are reported separately in the
[Sail product notes](SAIL-PRODUCTS.md). This summary does not infer an itemized bill
from the provider's account balance.

Source observations show the last recorded check, not a promise that a process is
still running. For a particular assignment, use the
[investigator commands](RESEARCH-LOOP.md) or [queue status](RESEARCH-QUEUE.md).
Inspecting a saved status is always separate from advancing paid work.
