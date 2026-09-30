# Persistent harness improvement

`scripts/harness_improve.py` runs a bounded improvement loop with the existing hash-chained
`Ledger` and `Worklist`, in a **separate private journal**. It does not reactivate the old Merton
or Engineer services, which the options swarm disables. It makes no provider calls, places no
orders, and does not write to the swarm database, change a running release, or deploy code.

The first lane addresses scheduler waste. More lanes require separate review of their measured
problem, permitted capabilities, fixed controls and operational decision rule. A scheduler
success is neither evidence of strategy alpha nor a declaration that the project's profit goal
has been achieved.

## The working loop

1. **Measure.** Read only `swarm.cycle` counts over the last hour, restricted to the current
   process's release cohort. At least 20 cycles and a paid-hold share of at least 25% produce a
   durable candidate. A paid hold means a model call whose cycle produced neither a new trial
   nor a queued run; it is a bottleneck signal, not proof that the call was useless. The candidate
   carries counts, metered research dollars, bounded event references, and the digest of the
   actual fresh-heartbeat release. Quotes, programs, validation results and sealed data are not
   read. Repeated scans with no new evidence do not append reports or create new attempts.
2. **Patch in isolation.** `prepare` creates a detached Git worktree at the measured baseline.
   An authorized coding agent writes and commits a candidate there. `stage` freezes its full
   commit, diff, baseline counts, judge hash, regression list and observation duration. The
   archived baseline must reproduce the measured running release's exact upload digest.
3. **Compare.** Both immutable Git archives run under `bwrap` with no host home, production
   state, inherited credentials or network, and with read-only code and judge directories.
   The fixed judge lives outside the candidate archive. Both trees run the same scheduler,
   hold, store, retirement and event-wait regressions. The candidate must preserve five
   responsiveness controls, use no additional idle model turns, and either reduce those turns
   or reduce SQLite operations by at least 20%, without a material fixture CPU regression.
   Namespace support is mandatory; there is no unsandboxed fallback. Each subprocess has a
   600-second wall limit, a 240-second CPU limit, 2 GiB address-space limit and 32 MiB file limit.
4. **Canary.** An authorized agent reviews the concrete patch and uses the existing deployment
   watchdog. The controller follows its append-only receipts: the exact evaluated upload tree,
   at least three passing canary ticks, a watch configured for at least 600 seconds, passing
   non-grace readings, and a promoted verdict. It also requires the real `current` symlink and
   the swarm heartbeat to identify that tree. Offline success alone never means retained.
5. **Retain or revert.** The registered interval is the first 900 seconds after the watchdog's
   promoted verdict, with at least 20 cycles. Paid-hold share must fall at least 20%; error and
   refusal rates must not rise; new trials must exist; and trials per metered research dollar
   must not decrease. Missing cost denominators do not earn credit. The first comparison is
   permanent: extending the window or repeatedly peeking cannot turn failure into success.
   A supported change becomes `verified`. A failed comparison records `revert_recommended`;
   an authorized operator/agent must execute the rollback and the watchdog must confirm it
   before the journal says `reverted`. Too little activity remains `insufficient_activity`, not
   retained. A later watchdog rollback also invalidates a previously retained change.

The comparison is an operational cohort comparison, not a randomized estimate. Workload changes
can confound it. All baseline, comparison and canary receipts remain in the journal, including
failed attempts. Model-turn/SQLite counts are cost proxies; fixture CPU and elapsed time are
measured. External patch-authoring charges and priced local compute are explicitly unknown in
this journal, not counted as free. Keep their real charges in the project's all-in cost ledger.

## Protected boundary

A candidate may change only the `Scheduler` class body in `league/swarm/loop.py`. Imports, other
module definitions and the class's execution context remain fixed; added reflection, global
mutation, reflective attributes and new persistent-store capabilities are refused. This is a
narrow structural guard plus a sandbox, not a proof that arbitrary Python is safe to deploy.
The separate deployment leg includes ordinary code review by the authorized agent/operator.

Every other path is protected, including tests, this controller and judge, settings and model
budgets, capital controls, provider routing, the evaluator, goal criteria, data access, and the
fixed synthetic statistical protocol/generator in `league/swarm/benchmarks.py` and the pinned evaluator suite in
`league/swarm/evaluator_benchmarks.py`. An evaluator-lane change is judged by running the trusted suite file against the
candidate tree (`python -m league.swarm.benchmarks --suite evaluator --json --tree CANDIDATE`), never the candidate's
own copy. Candidates cannot edit evaluation or sealed-data definitions as part of improving their own score. Changes to
those definitions require a separate reviewed change and new protocol; neither passing this
lane nor an old receipt authorizes them. No funding limits or model stack change here.

## Operation

Use a dedicated directory such as `/workspace/state/harness`; never pass the House's ledger as
the harness journal. Capture and reconciliation run where the actual read-only swarm state,
heartbeat, release tree and watchdog log are available. Patch preparation and isolated
evaluation also need the owner Git repository and `bwrap`; these may run on the owner machine.
If transferring a journal between hosts, stop its watcher, take a consistent SQLite backup,
and keep one authoritative writer. Do not copy a live SQLite main file without its WAL or let
two independent journal copies diverge. The CLI locks each transition locally.

The baseline argument is the complete reviewed commit SHA of the running release. A release
without `.git` can capture a candidate; the owner's staging step verifies the actual bytes.
The examples use placeholders for the reported candidate key and committed candidate SHA.

```sh
python scripts/harness_improve.py --root /private/harness capture \
  --swarm /workspace/state --base FULL_BASE_COMMIT_SHA

python scripts/harness_improve.py --root /private/harness --repo /owner/repo prepare \
  CANDIDATE_KEY --worktree /owner/worktrees/scheduler-candidate

# The authorized agent writes and commits the patch in that isolated worktree.
python scripts/harness_improve.py --root /private/harness --repo /owner/repo stage \
  CANDIDATE_KEY --candidate FULL_CANDIDATE_COMMIT_SHA
python scripts/harness_improve.py --root /private/harness --repo /owner/repo evaluate \
  CANDIDATE_KEY --python /owner/test-venv/bin/python

# Review and deploy exactly that tree through the existing watchdog, then observe.
python scripts/harness_improve.py --root /private/harness reconcile CANDIDATE_KEY \
  --swarm /workspace/state --deploy-base /workspace
python scripts/harness_improve.py --root /private/harness status
```

For continuous, free capture and receipt reconciliation:

```sh
python scripts/harness_improve.py --root /workspace/state/harness watch \
  --swarm /workspace/state --base FULL_BASE_COMMIT_SHA \
  --release /workspace/releases/EXACT_RELEASE \
  --deploy-base /workspace --interval 60
```

The watcher holds `watch.lock` for its lifetime, so another watcher cannot scan or overwrite its
heartbeat. It attempts the transition lock without waiting. A long evaluation produces a fresh
waiting heartbeat every 30–60 seconds, rather than making the observer appear hung. Capture is
bound to the supplied release directory (the executable checkout by default); a different swarm
heartbeat produces an explicit error and cannot create a candidate under the old base. Capture
can derive a base from a retained candidate only when the measured tree matches exactly.

It does not generate patches, repeatedly re-evaluate failed candidates, change the evaluator,
or deploy/roll back by itself. Those steps remain agent/operator-mediated. Installing code or
running tests does not start a production controller.

### Supervised observer

The House can supervise this same read-only observer when an operator installs an explicit private
`<swarm-state>/harness/runtime.json`. A missing or disabled policy starts nothing. Its shape is:

```json
{
  "schema": 1,
  "enabled": true,
  "mode": "observe",
  "base": "FULL_REVIEWED_40_HEX_GIT_COMMIT",
  "release_digest": "ACTUAL_RUNNING_TREE_64_HEX_SHA256"
}
```

Replace both placeholders with the reviewed release's full commit and `league.watchdog.tree_digest`
digest. The staged Git archive must reproduce that digest; a commit label alone is not evidence.
Install the policy by atomic replacement in the private directory with mode 0600. This policy
does not enable a patch author, paid queries, evaluation, deployment or orders. A new release
requires a reviewed policy update, even after a retained improvement; an unrelated rollout never
inherits a guessed base SHA.

The supervisor checks a small heartbeat on each House tick and hashes the immutable release once
per House process. It reaps its own exited child, waits 60 seconds between launches, and recovers
an existing observer only from its Linux start token and exact journal, state, release, base,
digest and policy arguments. If the House crashes between spawn and process-record persistence,
the lifetime lock prevents duplicate observation and the verified heartbeat permits recovery.
An occupied lock without a verifiable heartbeat is reported as waiting and is not force-killed.

A heartbeat older than 180 seconds, a changed policy or a state/parent `STOP` file stops the managed
observer. Signals use Linux pidfds with identity checked after opening the descriptor; PID reuse
cannot redirect a signal. There is no raw-PID fallback. Capture errors and transition waits remain
visible in the House's `harness` status without restarting a responsive observer. Disabling the
policy stops the verified child while preserving the journal and receipts. Filesystem work on the
House thread is small but synchronous; exception isolation is not a hard latency guarantee.
