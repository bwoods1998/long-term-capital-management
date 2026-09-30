# Persistent harness improvement

`scripts/harness_improve.py` runs a bounded improvement loop with the existing hash-chained
`Ledger` and `Worklist`, in a **separate private journal**. It does not reactivate the old Merton
or Engineer services, which the options swarm disables. It makes no provider calls, places no
orders, and does not write to the swarm database, change a running release, or deploy code.

The first lane addresses scheduler waste; the sections below up to "Lanes beyond the scheduler"
describe it. Four more lanes (research workflow and tools, prompts/memory/retrieval, data
processing, execution reliability) run the same loop, each with its own predeclared metric, surface,
fixed judge, held-out split and canary: see [Lanes beyond the scheduler](#lanes-beyond-the-scheduler).
No lane's success is evidence of strategy alpha or a declaration that the project's profit goal
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
fixed synthetic statistical protocol/generator in `league/swarm/benchmarks.py`. Candidates cannot
edit evaluation or sealed-data definitions as part of improving their own score. Changes to
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

## Lanes beyond the scheduler

`league/swarm/harness_lanes.py` defines four more lanes. Everything a candidate is judged by is
declared there before the candidate exists, and a candidate can never change it: the lanes module,
the judges (`league/swarm/harness_judges/`), the canary gate (`league/swarm/canary.py`), this
controller and every existing test are protected paths. `python scripts/harness_improve.py lanes`
prints the definitions and each lane's hash; staging refuses a candidate whose lane changed after
its capture.

| Lane | Bottleneck (primary metric, lower is better unless noted) | Must not worsen | Surface a candidate may change | Release class | Fixed judge | Canary |
|---|---|---|---|---|---|---|
| `research` | `train_dq_rate` = runtime-disqualified Train runs / Train runs; captured at >= 5% of >= 200 runs; retained on a 25% fall | `gym_seconds_wasted_per_birth` (Gym seconds of cycles whose run was disqualified, refused or erred / births); `ok_runs_per_usd` (10%); `cycle_error_rate` (20%) | `league/swarm/researcher.py`, `preflight.py`, `claude_research.py`, `league/CONTRACT.md` | research or money path | `research-workflow-v1`: synthetic programs through the tree's static check and preflight; `gym_seconds_wasted` must fall 20% on the held-out split, `false_refusals` stays 0; the added screening time must be under a quarter of the Gym seconds it saves | arms: 25% of families, 6 hours |
| `memory` | `graveyard_rebirth_rate` = births restating an earlier graveyard mechanism on the same slice / births; captured at >= 5% of >= 30 births; retained on a 50% fall | `validation_attempts_per_usd` | architect, strategist, diagnostician, researcher, seeds | research or money path | `memory-rebirth-v1`: the architect's admission of restated and novel proposals; `rebirths_admitted` must fall 25% on the held-out split, `novel_refused` must not rise | arms: 50% of mechanisms, 12 hours |
| `memory` | `validation_attempts_per_usd` (higher is better) = validation runs / research dollars; captured below 10 a dollar with >= $10; retained on a 25% rise | `graveyard_rebirth_rate` (at most +2 points) | as above | as above | same judge, `hold`: nothing may worsen offline (a prompt cannot be priced without a provider call); the canary carries the claim | as above |
| `data` | `slot_failure_rate` = job slots in failed Gym batches / job slots attempted; captured at >= 0.5% of >= 100 slots; retained on a 50% fall | `run_error_rate`; `gym_usd_per_ok_slot` (10%) | `league/sailbox.py`, `league/swarm/pool.py`, `league/data_job.py`, `scripts/data/{boxlib,locking,nightly,sip_progress}.py` | research or money path | `data-retry-v1`: injected network faults through the tree's real transport and the driver's download retry; `failed_transient` must fall 50%, `retried_permanent` stays 0 | window: 24 hours after promotion against the capture's window |
| `execution` | `harness_reject_rate` = practice rejects whose reason names a harness condition / intents; captured at >= 2% of >= 50 intents; retained on a 50% fall | `reject_rate`; `live_error_rate` | the practice, paper and real order lifecycle and live state (`league/live/{shadow,paper,real,venue,chains,state,observe,decider}.py`) | evidence reset only: a planned release | `execution-recovery-v1`: restart equivalence and reject correctness of the practice engine; `hold` | practice arms: 50% of families, five sessions |
| `execution` | `restart_failure_rate` = restarts not restoring every live instance cleanly within 10 minutes / restarts; any failure captures; retained when none fail | `live_error_rate` | as above | as above | same judge, `hold` (its restart scenarios already pass); the restarts after the release carry the claim | window: deliberate post-close restarts over five days (>= 3), exact test |

The observers read only operational counts through read-only SQLite opens: run statuses and times,
cycle counters, births' mechanisms and the graveyard's mechanism column, spend totals, pool events,
practice receipts' kinds and reject reasons, live order statuses and event kinds, and the House's
restarts. They never read a program, a quote, a parameter, a validation figure or the holdout's
`looks`; error texts are reduced to a normalized signature. The rebirth detector is frozen in the
lanes module (not the architect's own rule, which a candidate may change): the same slice, and a
first-sentence content-word Jaccard of at least 0.3 or a whole-text one of at least 0.5. It was
calibrated on the House's births of Sept 29-30, 2026 by inspection: every pair inspected at or above
0.3 restated a buried claim.

### What a candidate can never touch

A candidate is refused at staging when it changes any path in `PROTECTED` or any path outside its
lane's surface, whatever its purpose. The protected set names why: the objective (this loop, its
judges, the gate, the benchmarks, the statistics, the goal documents, every existing test), sealed
evaluation data and the evaluator (the Gym, the gate, the bands, the evaluator, the settings, what a
researcher may see of Validation, the data definitions), funded spending limits (the guard, the
model router and its budgets, the funding alerts, the config, the gateway), capital permissions (the
constitution, grants, the money table, the House test, calibration, the live step, the allocator)
and the release train. A candidate may add a test file named `league/tests/test_harness_candidate_*.py`
but never edit an existing test. In the files it may change, it may not introduce a process,
network, reflection or file-write call, global mutation, or an import of a spend, capital or release
module. The staging receipt classifies the change against the live path's import closure (D8's
method: every import of `league/live`, then module-level imports) and states its deploy rule:
research-side, money path (after the close, two money-path reviews), or evidence reset (a planned
release only). A lane refuses a class it does not allow. Note that `league/swarm/gate.py` imports the
researcher at module level, so the researcher, pool, inputs, diagnostics and the Claude research
adapter load on the live path whenever the gate does: changes there are money-path.

### Held out, twice

1. **Offline.** Each judge has a fixed `dev` split (the failure shapes the brief shows the author)
   and a `heldout` split generated from a seed that is `sha256(journal secret, key, candidate
   commit)`. The secret lives only in the journal (`heldout.secret`, mode 0600); the seed exists
   only once the commit is staged, so no author can see or tune to the held-out cases. Both trees
   are scored on both splits with the same seed. The receipt records the seed afterwards.
2. **Operational.** A capture names its motivating units: the families, mechanisms or boxes whose
   rows the brief shows. The retention comparison excludes them from both arms, and every window is
   later than the capture, so a retained change must work on units its author never saw.

### Retain or revert, with cost

- Arms modes (research, memory, execution's practice): the gate routes a deterministic fraction of
  units (`canary.in_arm`: a salted hash of the key and the unit) to the new behavior; the rest are
  the concurrent control. After the registered window the primary metric must be better in the
  canary arm by the predeclared effect with a one-sided cluster-bootstrap p <= 0.05 (units resampled
  whole) and enough denominator in each arm; every secondary and guard metric, the cost ones
  included (research dollars per useful run or validation attempt, Gym dollars per slot), must not
  worsen beyond its tolerance. Too little activity is `insufficient_activity`: no retention and no
  second look. A supported change sets the gate to `retained`; a failed one flips it to `reverted`,
  which is the old behavior at the next read (within 30 seconds), with no deploy.
- Window mode (data, execution restarts): the window after the watchdog's promotion against the
  capture's window, motivating units excluded; House-wide counts use an exact one-sided test. A
  failed comparison records `revert_recommended`; the operator rolls back through the watchdog, as
  for the scheduler lane.
- The first registered decision is final. A rollback reported by the watchdog later marks the
  candidate reverted. Removing the retained gate's old branch is a later reviewed change.

### The procedure: one command per step

The journal is the laptop's (for example `~/Work/.ltcm-main/harness/journal`); it holds the
ledger, the held-out secret, the candidates' patches and receipts, and `canary.json`. The House
reads only `<swarm-state>/harness/canary.json`. `next` prints every candidate's next command.

```sh
J=~/Work/.ltcm-main/harness/journal; R=~/Work/ltcm-deploy
# 1. Measure (on the House, read only; minutes of CPU at most):
python -B scripts/harness_improve.py measure --swarm /workspace/state --seconds 86400 > m.json
# 2. Rank and register the bottlenecks over their thresholds (laptop):
python scripts/harness_improve.py --root $J rank --measurement m.json --base FULL_RUNNING_COMMIT --out candidates.json
python scripts/harness_improve.py --root $J --repo $R next
# 3. Open the patch leg and read the brief (never the held-out split):
python scripts/harness_improve.py --root $J --repo $R prepare KEY --worktree ~/Work/harness-cand/KEY
python scripts/harness_improve.py --root $J brief KEY
# 4. The authorized agent writes and commits the patch in that worktree, gated by
#    canary.enabled("KEY", <unit>, root=<state dir>) for the arms lanes.
python scripts/harness_improve.py --root $J --repo $R stage KEY --candidate FULL_CANDIDATE_SHA
python scripts/harness_improve.py --root $J --repo $R evaluate KEY --python ~/Work/.ltcm-main/scratch/venv-a/bin/python
# 5. Deploy exactly the evaluated tree through the watchdog under the receipt's deploy rule. Then:
python -B scripts/harness_improve.py measure --swarm /workspace/state --seconds 900 > m.json   # House
python scripts/harness_improve.py --root $J canary KEY --measurement m.json                     # laptop
#    and install $J/canary.json as /workspace/state/harness/canary.json (mode 0600, atomically) within two minutes.
# 6. After the window `next` names:
python -B scripts/harness_improve.py measure --swarm /workspace/state --since S --until U --lanes LANE > m.json
python scripts/harness_improve.py --root $J reconcile KEY --measurement m.json
#    Install canary.json again: it now says retained or reverted.
```

`evaluate` runs the lane's judge on both trees, both splits, and the lane's fixed regressions, in
the same credential-free sandbox as the scheduler lane. A failed evaluation leaves the candidate
`revising`; a bottleneck gets three attempts on one base (each with a fresh held-out seed), then it is
`rejected` until a new capture on a new base. `canary --revert` flips a gate by hand at any time
(anyone may stop a canary); `canary --retain` is an operator decision recorded as such, never a
substitute for the registered comparison when counting retained improvements.

The loop never changes the objective, sealed data, spend limits or capital permissions: those files
are outside every surface, and the controller writes only its journal, its candidates' artifacts and
its own `canary.json`. It never places an order, funds a service or deploys; the gate never raises a
cap, because every lane's surface excludes the code that holds caps.

### Before release B runs

The lanes, the gate and the `measure` command reach the House with release B. Until then (and to
produce the first ranked list on Sept 30, 2026), the operator measured the running House read-only
by sending this module's source to a read-only Python on the House with a guard that refuses every
writable SQLite open, and ranked the result on the laptop. Candidates captured on a release other
than the one that will run their canary cannot be staged (the base must reproduce the measured
running tree): after release B deploys, measure and rank again, then run the cycle. The first cycle's
canary needs release B's gate on the House.
