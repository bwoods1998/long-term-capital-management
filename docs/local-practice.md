# Finite local practice simulations

`scripts/practice_run.py` runs explicit recorded or synthetic snapshots through the
observe-cohort engine. It does not start the House, acquire market data, construct a
brokerage client, call a model, change a band, publish forward evidence, or feed a
researcher. It is a finite local engineering tool, not a trading service.

Run from a system-Python virtual environment containing NumPy, with Linux
`bubblewrap` installed and user/PID/network namespaces available:

```sh
/path/to/venv/bin/python scripts/practice_run.py \
  --input /private/inputs/mechanics.json \
  --output /private/results/new-mechanics-run
```

The output parent must already exist. The output directory must be new, or an
owner-only (0700) directory previously marked by this runner. An existing empty
unmarked directory is refused. The Python API is
`league.practice_runner.run(Path(input_file), Path(output_directory))`.
Neither interface has an isolation bypass, arbitrary command, decider injection,
live-input mode, automatic input discovery, or daemon option.
Keep source and dependency files immutable during an invocation. The Python API
does not support hot reload; start a fresh interpreter after editing code. Source
hashes are freshly checked at invocation and before result publication, including
the session-calendar implementation and settings outside the Gym/live hash.

## Input contract (schema 1)

The input is one strict JSON object. Duplicate keys, unknown fields and non-finite
numbers are refused. Limit: 32 MiB, four programs, four distinct roots, 800 frames,
512 option rows in a frame, 256 distinct contracts per root/session. The parent
stops after 180 seconds of work (an already running bounded decision can finish).
The child has a 1 GiB address-space limit and 120 seconds CPU per child lifetime.

```json
{
  "schema": 1,
  "kind": "synthetic",
  "label": "Invented example",
  "programs": [{
    "family": "example",
    "version": 1,
    "code": "NEEDS = {\"roots\": [\"SPY\"], \"dte\": [0, 3], \"band\": 0.03, \"cadence\": 1, \"history\": 0, \"start\": 571, \"end\": 958}\nPARAMS = {}\ndef decide(ctx):\n    return []\n",
    "params": {},
    "roots": ["SPY"],
    "structure": "debit_vertical"
  }],
  "frames": [{
    "at": "2026-09-28T13:30:03Z",
    "stocks": {"SPY": {"latestQuote": {"t": "2026-09-28T13:30:02Z", "bp": 599.99, "ap": 600.01}}},
    "options": {"SPY260929C00600000": {"latestQuote": {"t": "2026-09-28T13:30:02Z", "bp": 1.90, "ap": 2.10, "bs": 20, "as": 20}}}
  }]
}
```

`kind` is exactly `synthetic` or `replay`. Family identifiers match
`[a-z][a-z0-9_]{0,39}` and are unique. Versions are positive integers. Program
source and parameter overrides are supplied explicitly; local admission makes no
claim of Train/Validation qualification. The engine prefixes family IDs with
`local_`. Both the literal source declaration and the sandbox child's actual
`NEEDS` roots must match the input roots. Parameters/defaults retain the existing
Gym runtime contract. A code/parameter/input/runtime change requires a new output.

Each frame is one observation. UTC `at` timestamps must increase into distinct
minutes. Stock rows can contain `latestQuote` (`t,bp,ap,bs,as`), `latestTrade`
(`t,p,s`), and `minuteBar` (`t,o,h,l,c,v`). Option rows accept only `latestQuote`.
Each supplied packet requires `t`; numeric fields may be absent/null, otherwise
must be finite and nonnegative. Omit provider exchange/condition/greeks fields.
Quote/trade timestamps cannot exceed the frame timestamp. No old snapshot is
automatically carried into a later frame. Missing quotes cause missed coverage.

A minute bar is exposed only after its full minute has ended. The engine retains
the first value observed for that completed bar and its first observation time;
later revisions do not rewrite it. Missing volume remains unknown. These receipts
describe availability in the *supplied recording*: the runner cannot authenticate
the provider's original publication/revision timing. Finalized historical bars
without original observation receipts must not be presented as point-in-time data.
No previous-session history is supplied or inferred; that API returns empty data.

For a wholly invented fixture exercising open/fill/close mechanics, a trusted test
builder is available as `league.tests.test_practice_runner.bundle(minutes=16)`.
Serialize its result to an explicit private JSON input; do not commit licensed
recordings or private strategy programs to this public repository.

## Isolation and execution

The trusted parent constructs `OptionsLive(real=None, paper=None, thread=False)`
with a read-only observation adapter and an explicit natural-only fill model. It
calls `minute()` over the finite input and never starts the engine thread.
Real-instance rows and non-observe shadow accounts are rejected before any engine
constructor. Bands, ordinary admission, and forward writes raise errors.

Only `SandboxedDecider` can execute supplied code. Every spawn uses mandatory
`bwrap --unshare-all --clearenv --die-with-parent` with dropped capabilities and
closed inherited descriptors. The child sees `/usr`, system libraries, a minimal
Python virtual-environment layout, NumPy/its native libraries, and the eleven
explicit source files in `RUNTIME_FILES`, all read-only. `/tmp` is ephemeral. It
does not see host home, the checkout, `.git`, `.data`, `.env`, input frames, or
writable results. No entire virtual environment or checkout is mounted. A probe
must succeed before any program loads; subsequent startup/protocol/load failures
leave the run incomplete. The existing parent-to-child data/child-to-parent JSON
boundary remains in use. `InlineDecider` appears only in trusted fixture tests.

Symlinks, hard-linked input/output files, normalized paths inside mounted runtime
trees, outputs inside this checkout, input/output overlap, and unknown state are refused.
This protects the sandbox boundary against accidental path aliases; it is not a
claim of protection from a hostile host administrator altering mounts or files.

## Results and restart

The output contains `local-practice.json` (identity/status), `input.json` (the
frozen canonical input), `report.json`, and `state/` (private cohort/book/receipt
files). Every report identifies replay/synthetic origin, input/program digests,
source execution/runner hashes, Python/NumPy versions, and the natural-only fill
identity. Cohort evaluator IDs start `local-simulation-natural-only:`. Reports
explicitly exclude live practice, forward/promotion evidence, and researcher
feedback. Open positions remain marked at input exhaustion; no closing market
data or liquidation is invented. A completed run is not a profitability finding.

`run.lock` prevents simultaneous writers. During work, `attempt/progress.json` is
atomically updated after every minute: `{frames_completed, last_at,
input_sha256, use}`. An interrupted run has status `running`, never `complete`.
On restart with identical frozen identities, the runner verifies the private
directory and discards only its previous checked scratch attempt, then rebuilds
the input from frame zero. It does not resume partially committed SQLite/JSON
books or preserve a strategy's interrupted in-memory globals. Recovery also
discards single-link, owner-owned files matching the engine's exact
`live-shadow.json.<eight lowercase/digit/underscore characters>.tmp` scratch name,
only inside a marked incomplete attempt. Unknown files still cause refusal.
Successful recovery records `recovery: "replayed_from_start"`. No previous attempt's trades are added
to the rebuilt aggregate. Identical completed input returns its hash-verified
cached result without running strategies again. Modified frozen input, completed
state, report, or evaluator identity is refused. Use a new output for a new run.

Choose a dedicated output outside every production/researcher root and every
other checkout; the runner does not discover those locations. It creates no
top-level `observe.sqlite` or `swarm.sqlite`. Do not point a researcher, publisher
or live service at the nested simulation state. A live feed, eligibility export, feedback
bridge, scheduling service, or automatic strategy revision loop is separate work.
