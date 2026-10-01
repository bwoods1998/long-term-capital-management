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
   archived baseline must reproduce the measured running release's exact upload digest. `stage`
   and `evaluate` run only as the base commit's controller (see [The pinned base](#the-pinned-base)).
3. **Compare.** The base archive and the candidate (the base archive with only `loop.py` laid over
   it) run under `bwrap` with no host home, production state, inherited credentials or network,
   and with read-only code and judge directories. The fixed benchmark is the base tree's, copied
   out of it, never the candidate's or the operator's checkout. Both trees run the same scheduler,
   hold, store, retirement and event-wait regressions. The candidate must preserve five
   responsiveness controls, use no additional idle model turns, and either reduce those turns
   or reduce SQLite operations by at least 20%, without a material fixture CPU regression.
   Namespace support is mandatory; there is no unsandboxed fallback. Each subprocess has a
   600-second wall limit, a 240-second CPU limit, 2 GiB address-space limit and 32 MiB file limit.
4. **Canary.** A separate agent reviews the concrete patch and evaluated tree adversarially and
   the review is recorded (`review`, verdict approve; see [The adversarial review](#the-adversarial-review)).
   Then the loop's deploy step (`deploy`) checks that approval and issues the ticket the tree is
   deployed under; only then deploy through the existing deployment watchdog. A tree the watchdog
   shows on the House before the approval or the ticket, more than two hours after its ticket, or
   inside the hours its release class forbids gets no observation window: `reconcile` records
   `rollback_required`. The controller follows its append-only receipts: the exact evaluated upload tree,
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
The adversarial review of the exact patch and evaluated tree is mandatory and recorded in the
journal before the deploy step issues its ticket, and both precede the tree's first watchdog row.

Every other path is protected, including tests, this controller and judge, settings and model
budgets, capital controls, provider routing, the evaluator, goal criteria, data access, and the
fixed synthetic statistical protocol/generator in `league/swarm/benchmarks.py` and the pinned evaluator suite in
`league/swarm/evaluator_benchmarks.py`. No lane scores the evaluator today: the suite's `--tree` mode is an operator
tool for trusted trees (the tree's code runs in the suite's interpreter with the operator's environment, and a run needs
more CPU than a lane's sandbox allows), not a judge of an untrusted candidate. Candidates cannot edit evaluation or
sealed-data definitions as part of improving their own score. Changes to
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
  CANDIDATE_KEY --candidate FULL_CANDIDATE_COMMIT_SHA --author AGENT
python scripts/harness_improve.py --root /private/harness --repo /owner/repo evaluate \
  CANDIDATE_KEY --python /owner/test-venv/bin/python

# Another agent reviews exactly that patch and tree; the deploy step checks the approval and issues
# the ticket; then deploy exactly that tree through the existing watchdog, and observe.
python scripts/harness_improve.py --root /private/harness --repo /owner/repo review \
  CANDIDATE_KEY --report review.md --reviewer AGENT2 --patch-sha PATCH_SHA256
python scripts/harness_improve.py --root /private/harness --repo /owner/repo deploy CANDIDATE_KEY
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

What keeps a candidate from changing its own score: the paths it may touch (the diff's file list,
checked by the controller); the adversarial review of its patch and evaluated tree (mandatory,
recorded in the journal, checked by the deploy step, and checked again against the watchdog's
receipts when the canary is registered); judging and deciding with the pinned base commit's code
(the judge, the rules and the decision are the base's; the candidate's modules still run inside
the judge's interpreter, which imports the tree); the judges' and regressions' runtime checks, the
D2a sentinels among them; and the concurrent canary. The import and state rule and the per-name
content and symbol guards are static analysis of arbitrary Python: defense in depth that refuses
the routes reviewers have found, never a guarantee.

| Lane | Bottleneck (primary metric, lower is better unless noted) | Must not worsen | Surface a candidate may change | Release class | Fixed judge | Canary |
|---|---|---|---|---|---|---|
| `research` | `train_dq_rate` = runtime-disqualified Train runs / Train runs; captured at >= 5% of >= 200 runs; retained on a 25% fall | `gym_seconds_wasted_per_birth`; `ok_runs_per_usd` (10%); `cycle_error_rate` (20%); `unmatched_gym_cycle_rate` (+1 point); `zero_trade_ok_rate` (OK Train runs that traded nothing: a program whose errors were hidden from the Gym; 10% or +2 points); population: research $ with no family per hour (+25%) | `league/swarm/researcher.py`, `preflight.py`, `claude_research.py` | research or money path | `research-workflow-v3`: synthetic programs through the tree's static check, `Researcher._admit` and preflight; `gym_seconds_wasted` must fall 20% on the held-out and the dev split, `false_refusals` stays 0; screens at most 0.25 CPU seconds a program and at most a quarter of the Gym box-seconds they save at the House's rate | arms: 25% of families, 6 hours |
| `memory` | `graveyard_rebirth_rate` = births restating an earlier graveyard mechanism on the same slice / births; captured at >= 5% of >= 30 births; retained on a 50% fall | `validation_attempts_per_usd`; birth balance (the canary arm's share of births not below its fraction, one-sided binomial); population: research $ with no family per hour | architect, strategist, diagnostician, researcher, seeds | research or money path | `memory-rebirth-v4`: the architect's admission of restated and novel proposals as production runs it since release B' (family cards: every case carries a complete card the judge derives at run time from the case's own text and days to expiry, never from the pool, so the private pool needs no card field; `require_card` and `card_rebirth` at their defaults). The graveyard holds idea rows (THIN, EXHAUSTED or STALL deaths, which the card check does not cover: the lane's lever acts on their restatements) and card-path rows (REFUTED and long-dated: the card check must refuse their restatements, `card_path_admitted`). The held-out split draws its card-path rows (at most two) from the pool's bank only when the bank can spare texts without repeating a novel one: a pool with none to spare has no held-out card path, and then only the dev split's two rows exercise it. A restatement carries its buried row's exact card key on that row's slice, so every idea row's slice also holds a same-cell control: a novel proposal under the row's exact class, inputs and holding, with a new idea's words (`same_cell_proposed`, `same_cell_refused`). A lever that refuses by card key (equal to a dead family's on its slice, or matching it on overlapping inputs) refuses those controls too and fails on `novel_refused`: only the words tell a restatement from a new idea. Narrowed to cards whose own words read (production's keyword reading) as the dead key too, it still refuses controls: on dev, two controls (founding families' mechanisms) read exactly as their rows and one as its class; on held-out each control takes the pool's novel text that reads closest to its row's first, so how often it sees such a refusal depends on the pool. No novel card falls in a refuted cell, by construction, checked with the card module's own matching before the tree's architect loads, and a tree whose tags read the graveyard otherwise gets no answer. `rebirths_admitted` must fall 25% on the held-out and the dev split; `trials_uncounted`, `mechanism_rewritten` and `card_path_admitted` stay 0; `novel_refused` and `rebirths_fresh_lineage` must not rise; Release B's birth quota rests in the judge; with the gate open the regressions that pin the admission of a restated dead idea are superseded (`Lane.supersedes`, the admission halves only; closed, they must pass); the researcher's, strategist's and diagnostician's tests run too, and so do release B's card, structures and mechanism tests (`test_swarm_cards`, `test_swarm_architect_structures`, `test_swarm_mechanism`: complete cards, the card-based rebirth refusal, a rebirth's lineage and its budgets, which the rounds' and graveyard digest's tests leave to them) | arms: 50% of mechanisms born in the window, 12 hours |
| `memory` | `validation_attempts_per_usd` (higher is better) = Validation runs at the normal spread / research dollars; captured below 10 a dollar with >= $10; retained on a 25% rise | `graveyard_rebirth_rate` (at most +2 points); birth balance; population cost | as above | as above | same judge, `hold`: nothing may worsen offline (a prompt cannot be priced without a provider call); the canary carries the claim | arms: 50% of mechanisms born in the window, 48 hours |
| `data` | `slot_failure_rate` = job slots in failed Gym batches / job slots attempted; captured at >= 0.5% of >= 100 slots; retained on a 50% fall | `run_error_rate`; `gym_usd_per_ok_slot` (10%) | `league/sailbox.py`, `league/data_job.py`, `scripts/data/{boxlib,locking,nightly,sip_progress}.py`; never the Gym pool, which writes this lane's own metric (its `batch_failed` events and the job slots it books) and which the judge never runs | research or money path | `data-retry-v3`: injected network faults through the tree's real transport and the driver's download retry; `failed_transient` must fall 50% (held out; on dev too where its baseline has any: the truncated read, `IncompleteRead`, is a dev case), `retried_permanent` stays 0 | window: the 24 hours after promotion against a fresh control day before the deploy |
| `execution` | `harness_reject_rate` = practice rejects whose reason names a harness condition / intents; captured at >= 2% of >= 50 intents; retained on a 50% fall | `reject_rate`; `live_error_rate` | the practice engine, its chains, its receipts and the decider (`league/live/{shadow,chains,observe,decider}.py`); never the real-money order path, the venue, the live state or paper orders (capital); the receipts' writers and the reject reasons the metric classifies stay the baseline's | evidence reset only: a planned release | `execution-recovery-v2`: restart equivalence and reject correctness of the practice engine; `hold` | window: a week of practice after the planned release against a fresh control week before it |
| `execution` | `restart_failure_rate` = restarts not restoring every live instance cleanly within 10 minutes / restarts; any failure captures when the exact test can reach p <= 0.05 with at most 15 deliberate restarts | `live_error_rate` | as above | as above | same judge, `hold` | window: deliberate post-close restarts over five days (at most three an evening), as many as the exact test needs against the control's restarts; a control that would need more voids the canary at its start |

The observers read only operational counts through read-only SQLite opens: run statuses and times,
cycle counters, births' mechanisms and the graveyard's mechanism column, spend totals, pool events,
practice receipts' kinds and reject reasons, live order statuses and event kinds, and the House's
restarts. They never read a program, a quote, a parameter, a validation figure or the holdout's
`looks`; error texts are reduced to a normalized signature. The rebirth detector is frozen in the
lanes module (not the architect's own rule, which a candidate may not change either): the same slice,
and a first-sentence content-word Jaccard of at least 0.3 or a whole-text one of at least 0.5. It was
calibrated on the House's births of Sept 29-30, 2026 by inspection: every pair inspected at or above
0.3 restated a buried claim.

A captured bottleneck must also repay a cycle: its dollars a day at the predeclared effect, over 30
days, must cover the estimated cycle ($10 research-side, $25 money path, $40 evidence reset:
authoring, adversarial reviews, a deploy and its verification). Staging checks it again with the
candidate's actual release class. Execution is ranked by severity instead (real orders and evidence).

### What the controller refuses (machine-checked steps)

These read file names, statuses, journal rows and the watchdog's receipts, not what code means.

- **Paths.** Staging lists the diff with `git diff --no-renames --name-status` and refuses a candidate
  that touches any path in `PROTECTED`, with any status: a modification, a deletion, a type change,
  or either side of a rename (with `--no-renames` a rename is a delete and an add). It also refuses
  any path outside its lane's surface, any delete, rename, copy or mode change, whatever its purpose.
  The protected set names why: the objective (this loop, its judges, the gate, the benchmarks, the
  statistics, the goal documents, every existing test), sealed evaluation data and the evaluator,
  funded spending limits, capital permissions (the constitution, grants, the money table, the House
  test, calibration, the live step, the allocator, the real-money order path, the venue, the live
  state and paper orders) and the release train. A candidate may add a test file named
  `league/tests/test_harness_candidate_*.py` but never edit or delete an existing test, an earlier
  candidate's included.
- **The adversarial review and the deploy step** (below): an approving review of the exact patch and
  evaluated tree, then the deploy step's ticket, both before the watchdog's first row for that tree.
  The release train does not read the journal: a deploy around the loop is caught when the canary is
  registered (void, rollback), not prevented.
- **The pinned base** (below): the judge, the rules and the decision are the base commit's code.

### Static guards (defense in depth, never a guarantee)

Inside the files it may change, four guards (`harness_lanes.py`). They are static analysis of
arbitrary Python: each refuses a route a reviewer found, none proves that a candidate cannot change
trial counts, read sealed data or write files by a route nobody listed. The review checks for those
routes, and the judges' runtime checks catch what they can.

- **Imports and protected state** (`protected_routes`, in `content_guard`). No new route to the
  store, the evaluator, the gate, the bands, the settings or the constitution
  (`league.swarm.{store,evaluator,gate,bands,settings}`, `league.constitution`): an import of one or
  of a name from it (absolute or relative); an import of their parent packages (`import league`,
  `import league.<anything>`, which binds `league`, `from league import swarm`, `from .. import
  swarm`); any star import; a name another module re-exports or computes from one (`from .architect
  import SwarmStore`, a `CFG = settings_mod.DEFAULTS` the candidate adds elsewhere: resolved over the
  base tree for the baseline and the candidate's tree for the change); an imported module's attribute
  that reaches one (`researcher.settings_mod`). No import of `os`, `subprocess`, `shutil`, `socket`,
  `pathlib`, `io`, `logging`, `tempfile`, `importlib` or `ctypes`, and no route to them or to any
  other process, file, network, loader or interpreter module through another module of the tree that
  imports one (`from .loop import os as _o`, `from . import hook` then `hook.subprocess`,
  `from .loop import Path`, a module's `_o = os`), nor to `builtins` through a module's
  `__builtins__` (imported or read as an attribute; an imported dunder such as `__builtins__`,
  `__loader__` or `__spec__` also counts as reflection). Counted per import statement and per
  attribute read: a second `import os` inside a function is one more, even where the file imports os
  at the top. And through the names a file already binds to a protected module or its tables
  (`settings_mod`, `from .store import STRUCTURES`): no new item or attribute assignment or deletion
  (a loop or `with` target included), no mutator (`.clear()`, `.update(...)`, called or held, also on
  a part a call returns: `settings_mod.DEFAULTS.get("gym").update(...)`), and no bare hand-out of the
  module or a part of it where other code could mutate it: `d = settings_mod.DEFAULTS`,
  `f(settings_mod.TRAIN_STARTS)`, a return, a container, a loop's or a comprehension's iterable
  (`for d in settings_mod.DEFAULTS.values()`), a function's or lambda's default value
  (`def f(d=settings_mod.DEFAULTS)`), a `match` subject, through a conditional or `or`. Read a setting
  inline. An object handed over at run time (an instance's attribute, a function's result such as
  `settings_mod.load()`) is not followed. A candidate's new test file is held to the same rule.
- **Frozen symbols** (`FROZEN_SYMBOLS`, `symbol_guard`). Every function that writes trial, lineage,
  look, graveyard, state or receipt records is frozen whole: the trial writers (`add_run`,
  `add_family`, `link_lineages`, `retire_gym`, ...), the store's general writers (`update_family`,
  `bump`, `set_state`, `compare_and_set_state`, `add_version`: the lineage, the trial counters, the
  robustness and drift marks eligibility reads), raw SQL that writes (or SQL that is not a plain
  string), and the practice engine's receipts (`practice_event`, `_reject`). This refuses the known ways
  to drop an evaluation from the lineage's trial count, clear an eligibility mark or give a restated
  idea a fresh look ration; it does not prove there is no other. Train eligibility, the idle and drift screens, the evaluation key, the cycle
  record (the research lane's metrics come from it), a program's path from the model's tool call to
  the Gym (`Researcher._model_cycle`, `_execute`, `_gym_sweep`, the program helpers, and
  `claude_research`'s tool-call parsing: no candidate may rewrite the program the Gym evaluates, for
  example wrap its decide in try/except so runtime errors never disqualify it), the architect's
  same-idea rule and its pass from the model call to `admit` are frozen by name. `Architect.admit`
  is the memory lane's lever: it may refuse more proposals, but its trial writes, the conditions
  around them and what an admitted birth keeps (its text, slice, lineage and trials) are the
  baseline's: no rebinding, mutation, mutator reference (`forget = dead.clear`) or alias of what it
  keeps (`rows = dead`). A function that names a record writer without calling it
  (`mark = self.store.set_state`) is a writer too, and a new call of (or reference to) any function
  of the module that writes records, directly or through another such function, is refused (a new
  path to a writer: a gated branch calling `self._demote(...)`). Passing a guarded binding to new code
  as an argument is not refused (reading the graveyard rows is the lever's job): the review checks
  that the new code does not mutate it.
- **Content** (`content_guard`, counted per name wherever the name is used, so moving existing code is
  allowed and an alias hides nothing): no new process, network, reflection, file write or move
  (`open` and the writers that are not `open`: logging's file handlers and `basicConfig`, `io.FileIO`,
  archives, temporary files, `json.dump`, numpy and pandas savers), no new member of a file, logging
  or archive module the file already imports, process replacement, print, exit, dynamic attribute
  access (`attrgetter`, `methodcaller`), a call through an expression (`[f][0](...)`),
  interpreter plumbing (`sys.modules`, `sys.argv`, `os.environ`, `sys.exc_info`, ...), `os` member
  beyond the path helpers, member of a process or interpreter module the file already imports
  (`subprocess.run`), aliased import of such a module, dunder or frame access, assignment to another
  object's attribute (or to one of an object's own methods or collaborators), mutation of the shared
  collaborators (`self.settings[...] = ...`: an arm's change would reach the control), store writer
  named anywhere (called or held; the everyday names among them, `run`, `runs`, `note`, `put`,
  `event`, `refuse`, `retire`, `bump` and `forward`, count on any object, so a new `runner.run(...)`
  or `result.note` is refused too: name new methods otherwise), reader of the holdout, Validation or forward evidence (`looks`,
  `lineage_validated`, and `runs`, `run`, `run_result`, which return a Validation run's row or full
  result as readily as a Train one's), a key naming Validation, the holdout or a line's figures
  (`state["validation_line"]["numbers"]`, `window="validation"`), new or changed raw SQL statement,
  access to a collaborator's private attributes (`self.store._db`), import of a spend, capital or
  release module, or mention of the judges' override. In the practice engine no reject reason the
  execution lane classifies may be reworded or dropped. No gate may sit in the evaluator
  fingerprint's files. The judges' override counts only inside the judges' sandbox
  (`LTCM_HARNESS_JUDGE=1`): on the House a candidate's code cannot force a gate however it reaches
  the override.
- **Gate coverage** (`gate_coverage`, arms lanes): with its gate closed the module must reduce to
  the baseline's (statically: its AST with every gated branch replaced by the old one). Every change sits in `if canary.enabled("<key>", <unit>, root=<state dir>): new
  else: old` (or the `new if <gate> else old` expression), with the old branch the baseline's code
  byte for byte, or is a new definition with no load-time effect, a new plain constant or a new
  import, each under a name no existing code uses (a new `def round`, `LONG_SINGLE = ...` or
  `from x import same_slice` would change what existing code, a frozen function included, calls). No
  new dunder (a module's `__getattr__`, a class's `__bool__`), no new member of an existing class with
  bases or decorators (a base's method or a `NodeTransformer.visit_*` dispatch, a dataclass's or
  NamedTuple's fields), no new class attribute, and a new class only on builtin bases: each acts with
  the gate closed. The gate is asked about the lane's unit, the one its observer splits: a name for
  the family (`fam["id"]`) in the research lane; in the memory lane `canary.mechanism_unit(mechanism)`
  inside `Architect.admit` (the admitted text) or `canary.mechanism_unit(fam["mechanism"])` in
  `league/swarm/researcher.py` only. A changed
  existing constant or prose cannot be gated per unit: put new text in a new constant chosen under the
  gate. An architect prompt is per pass, not per mechanism, so it cannot be a memory-lane arms
  candidate.

### The adversarial review

Every candidate, in every lane, gets an adversarial review of its exact patch and evaluated tree by
an agent other than its author BEFORE the tree can reach the House. The controller checks it three
times:

- `review` is accepted only once `evaluate` passed (the tree's release digest is then known); the row
  records the patch's sha256, the commit and that digest.
- The loop's deploy step, `deploy KEY`, refuses unless the journal's latest review of exactly that
  patch and tree approves, and outside its release class's hours (a money-path or evidence-reset tree
  never in New York's session; a research-side one never 15:30-16:00 New York). It records a ticket and
  names the exact commit and digest to send through the watchdog. Deploy only after it.
- `canary` (lanes) and the scheduler lane's `reconcile` read the watchdog's receipts: when the tree's
  first watchdog row (the `start` of any attempt that staged it) is earlier than the first approving
  review on the journal's clock, or any attempt that staged it began without a deploy ticket issued
  in the two hours before it (`TICKET_SECONDS`: a ticket is for a deploy now, not whenever), or ran
  (its first row to its verdict) inside the hours its release class forbids, the candidate is voided
  (`rollback_required` on the scheduler lane), no canary or window opens, and `next` asks to roll the
  release back through the watchdog. A review recorded after the exposure never makes it acceptable.
  The release train (`floor_box.py`, the watchdog) does not read the journal, so a deploy around the
  loop is caught here rather than prevented: keep the laptop's and the House's clocks on NTP.
  `measure` keeps the last 400 watchdog rows whole and, before them, each attempt's first row and its
  stage, verdict and rollback rows, so a tree's first exposure stays in view however many deploys
  followed.

1. `next` prints the review step with the patch's sha256 once `evaluate` passes. Give the reviewing
   agent `<journal>/candidates/<id>/candidate.patch`, the brief (`brief KEY`) and this checklist;
   never the held-out directory or the journal.
2. The reviewer tries to break the candidate. At least:
   - Does it change, by any route, a trial count, a lineage, an eligibility mark, a look, the
     graveyard, the cycle record or a practice receipt (a writer reached through a helper, a
     callback, a guarded binding passed to new code and mutated there, an element of a guarded list)?
   - Does any text a model reads gain a Validation figure, a check's name, holdout or forward
     evidence (D2a), through the store, a family's state, a tool's answer or a cached object?
   - Does it write, move or delete a file (the House's `harness/canary.json` included), open a
     process or a connection, or reach a module the import rule refuses through one already loaded?
   - With its gate closed, does anything run differently (a new module-level effect, a dispatch by
     name, a changed default, shared state an arm's branch mutates and the control reads)?
   - Is the gate asked about the lane's unit, and does the change do what the brief's bottleneck
     needs, not what the dev split's examples alone reward?
   - (memory) Does it refuse a proposal by anything but its words against the graveyard's: its card
     key (the judge's same-cell controls share a restatement's), or the judge's construction (its
     batch, its order, its sketch markers)? Production's card check stays as release B' made it.
3. The report cites the patch's sha256 (or its first 16 hex) and states exactly one verdict on its own
   line: `VERDICT: approve` or `VERDICT: reject`. Record it:
   `python scripts/harness_improve.py --root $J --repo $R review KEY --report review.md --reviewer
   <agent> --patch-sha <sha256> [--review-usd 2]`. The report is kept beside the patch. A reject
   sends the candidate back to revising (on its last attempt, rejected), and the author may read it;
   a reject after a deploy ticket also asks for the tree's rollback (`next` names it, on the last
   attempt too). `stage --author <agent>` is
   required and records the author; the controller refuses a review by the same name.
4. Then `deploy KEY` (the deploy step), and deploy exactly the named commit through the watchdog
   (from a clean checkout of it, `python3 scripts/floor_box.py deploy`; the watchdog's stage
   receipt must show the evaluated digest). A data-lane candidate changes `league/sailbox.py`, which
   `floor_box.py` itself imports: run from the candidate checkout, its transport runs on the
   laptop too, and the review covers that.

### The pinned base

Capture, staging, evaluation, the judges, the benchmarks and the retain/revert decision run from the
candidate's PINNED BASE commit, never from the candidate's tree or an unreviewed checkout:

- The controller refuses to compute anything about a candidate unless its own code (`CONTROLLER` in
  `improvement.py`: the lanes module, this controller, the gate, the judges, the benchmark, the
  journal, the watchdog's digest, the CLI) is the base commit's, blob for blob
  (`HarnessImprovement.pinned`). `scripts/harness_improve.py` re-executes `rank`, `stage`,
  `evaluate`, `review`, `deploy`, `canary` and `reconcile` from a separate read-only checkout of the base
  (`<journal>/controllers/<base>`, `git archive` of league/ and scripts/, made once), with `--repo`
  naming the owner repository. A flip by hand (`canary --revert`, `--retain`, `--graduated`) needs
  no checkout.
- The judges and the benchmark are copied out of the base tree (pinned by hash at staging). The
  candidate is judged as the base tree with only its staged files laid over it, so every protected
  file the judges import and every fixed test is the base's by construction; a candidate commit that
  differs from its base beyond its staged files is refused.
- A House measurement records the git blob id of every repository module the measuring process
  loaded (`code`). `canary` and `reconcile` refuse a measurement whose measuring code is not the
  base's: measure with the base release's copy of the script
  (`python -B /workspace/releases/<base release>/scripts/harness_improve.py measure ...`; the
  watchdog keeps the previous release for rollback, and `next` prints the path).

The staging receipt classifies the change against the live path's import closure (D8's method:
every import of `league/live`, then module-level imports) and states its deploy rule: research-side,
money path (after the close, two money-path reviews), or evidence reset (a planned release only). A
lane refuses a class it does not allow. `league/swarm/gate.py` imports the researcher at module
level, so the researcher, pool, inputs, diagnostics, the Claude research adapter, public and evidence
load on the live path whenever the gate does: changes there are money path.

### Held out, honestly

1. **Offline.** Each judge has a fixed `dev` split in its public file (the failure shapes the brief
   shows the author) and a `heldout` split of PRIVATE classes the dev split never uses: each lane's
   pool is a file outside the repo (`~/Work/.ltcm-main/harness-heldout/<judge>.json`, mode 0600 in a
   0700 directory), pinned by its SHA-256 in `harness_lanes.HELDOUT_POOLS` (so it is part of the lane's
   hash). `evaluate` reads it (`--heldout DIR`, or `$LTCM_HARNESS_HELDOUT`), checks the hash and hands
   it to the judge on standard input in held-out runs only: it is never a file in the sandbox, never in
   a brief, never in git history. Its cases are drawn every class in every placement (stratified), from
   a seed that is `sha256(journal secret, key, candidate commit)`: it exists only once the commit is
   staged. The author sees only pass or fail for the held-out split: the receipt in the owner's
   journal keeps its scalar counts and the verdict's full reasons, never its per-class detail or
   anything the run printed, and the revising note and the brief carry only the public reasons. An "improve" rule also asks the dev split's count (the motivating failures) to fall by the
   same effect wherever its baseline has any. The patch author works in its worktree only: never give
   it the held-out directory (or the journal). A lost pool is restored from its backup, never
   regenerated (a new pool is a new lane hash; every open capture must be taken again). Burns are by
   FAMILY, not by case: a fault family (a status-code range, an errno group, a kind of misuse or of
   malformed intent) any public text names (a PR body, whose edit history GitHub keeps, a comment, a
   commit, a docstring, a test fixture, a judge's own vocabulary) is burned whole, and its cases are
   rotated out for cases from families no public text names, chosen against a scan of every public
   text; the owner's private notes beside the pools record which families are burned. Public text
   describes the pools only by their count and hash, and a judge resolves a held-out case's exception
   class by name at run time, so its public file lists only the dev split's. The concurrent canary (or
   the window after a release) is the held-out test of the House itself.
2. **Gate open and closed.** An arms-lane candidate is judged twice more than the baseline: with its
   gate forced open (`canary._FORCED`, set only by the judges in their sandboxed process, honored only
   under the sandbox's marker) it must meet the lane's rules; forced closed it must equal the baseline
   on every judge count, dev and held out, and both ways it must pass the fixed regressions (open, the
   lane's superseded tests, which pin the old admission the lever changes, are skipped; closed, they
   run). Each judge run carries a nonce on standard input that its answer must repeat, so a line the
   tree's code prints is no answer.
3. **Operational.** A capture names its motivating units: the families, mechanisms or boxes whose
   rows the brief shows. An arms comparison excludes them (and pseudo-units) from both arms; the
   memory lane compares only families born in the window, since its gate acts at birth. A
   before/after window is later than every motivating row.

### Retain, revert or void, with cost

- Arms modes (research, memory): the gate routes a deterministic fraction of units
  (`canary.in_arm`: a salted hash of the key and the unit) to the new behavior; the rest are the
  concurrent control. After the registered window the primary metric must be better in the canary
  arm by the predeclared effect with a one-sided cluster-bootstrap p <= 0.05 (units resampled whole)
  and enough denominator in each arm; every secondary and guard metric, the cost ones included, must
  not worsen beyond its tolerance; the population guards (research dollars with no family, which no
  arm can carry) compare the window with the capture; the memory lane's canary arm must keep its
  share of births. A supported change sets the gate to `retained`; a failed one flips it to
  `reverted` (the old behavior at the next read, within 30 seconds, with no deploy); too little
  activity also flips it back, with no second look.
- Window modes (data, execution): the window after the watchdog's promotion against a fresh control
  window of the same length that ends before the deploy began and starts after the capture's window
  (the capture was chosen for being bad; comparing with it would favor retention). House-wide counts
  use an exact one-sided test, with as many deliberate post-release restarts as it needs to reach alpha
  against the control (at most 15; `next` names the count). A failed comparison, or too little activity,
  records `revert_recommended` or `insufficient_activity`, and `next` names the rollback through the
  watchdog; the next `reconcile` records the watchdog's rollback as `reverted`.
- **Once, after it ends.** The registered window is judged only when the clock is past its end, on a
  measurement of exactly that window (within a minute) taken after it ended (`taken_at`); `measure`
  refuses a window that ends in the future. The first registered decision is final.
- **Void.** Another release promoted inside the window, or a start of another release inside it (a
  restart of the candidate's own release changes no code and voids nothing), or a change to the lane's
  predeclared rules (the lane's hash covers the rebirth detector, the reject classes, the cost
  constants, the observers and the comparison), voids the comparison: the gate flips back and the
  candidate is closed. So does a deploy that replaced a release other than the measured base (a
  candidate captured on a stale measurement: `next` says to roll back to the release it replaced), or
  a restart control that would need more deliberate restarts than the window allows. The next `rank`
  on a newer measurement reopens the bottleneck (on a new base it is a new key anyway). The first
  void does not count against its three attempts; every later one does (each void cost a deploy, and
  on the execution lane an evidence reset), so declare a release freeze over the next window before
  its canary. A watchdog rollback marks the candidate reverted.
- **Fresh capture.** `rank` registers a candidate only from a measurement taken in the last hour of a
  swarm with a fresh heartbeat: the candidate is bound to the release that measurement saw running.
- **The window is read once.** On the House watch path the registered window's measurement is taken
  once, after the window ends, and kept in the journal (`windows/`): a decision that must wait (a
  money-path gate before the close) re-reads that copy.
- **Money path.** A gate in code the live path loads turns new behavior on only outside New York's
  session (09:30-16:05): `canary` start and a retaining `reconcile` wait for the close; flipping back
  is allowed at any time.
- **By hand.** `canary KEY --revert` flips a gate back at any time. `canary KEY --retain` only
  re-installs a gate the registered decision retained (for a lost `canary.json`); it never overrides
  a decision.
- **Graduation.** A retained gate lives only in `canary.json`, which fails closed: if the House's copy
  is lost the change silently reverts, and the next release built from main drops its code. So `next`
  asks for graduation: from main, apply the candidate's patch keeping only the new branch (the gate
  and the old branch removed), open a PR under the same deploy rule, and after it merges run
  `canary KEY --graduated <main commit>`, which drops the arm. A retained window-lane change (no gate)
  runs only in its candidate release: `next` asks to merge its commit into main, then
  `canary KEY --graduated <main commit>`. `status` lists retained changes not yet in main; the
  observer's heartbeat lists the gates the House reads, to compare.
- **Cost.** Each step can record what it cost (`stage --authoring-usd`, `canary --deploy-usd`) and the
  job sums them; the evaluation receipt records the sandbox's CPU seconds. Authoring and review
  dollars already spent do not enter the retention decision (they are sunk); the payback test decides
  whether a cycle starts, and the guards decide whether the change's running cost is acceptable.

### Hard controls and known limits

Three controls hold whatever a candidate's code does: the protected paths and the lane's surface
(the diff's file list), the adversarial review recorded before the tree reaches the House (the
deploy step's ticket, and the exposure check when the canary is registered), and the pinned-base
evaluation (the judges, the rules and the decision are the base commit's code, run on the base tree
with only the candidate's staged files laid over it). Everything static, the import and state rule,
the content and symbol guards and gate coverage, is defense in depth: it refuses the routes
reviewers have found and promises nothing about the rest. Known limits, each left to the review:

- The static guards do not follow an object handed over at run time (an instance's attribute, a
  function's result) or a dispatch through data the code already holds, and they resolve imports over
  the base and candidate trees only.
- The candidate's modules run inside the judge's interpreter: the per-run nonce, the static guards,
  the review and the canary stand between them and the judge's answer, not a process boundary.
- The release train does not read the journal: a deploy around the loop is voided and rolled back
  when its canary is registered, not prevented. The hours and ticket checks read the watchdog's row
  times against the journal's clock (keep both on NTP).
- The D2a sentinels catch a sealed figure in its common printed forms only (rounded or truncated);
  arithmetic of the code's own, or an unusual format, is the review's.
- The held-out pools are burned by family against a scan of every public text when they rotate; a
  family made public later (a new PR body, a comment) needs the scan again before the next
  evaluation.
- `measure` keeps the watchdog rows older than its last 400 only as each attempt's first, stage,
  verdict and rollback rows: enough for the exposure check, not for an old attempt's full receipts.

### The procedure: one command per step

The journal is the laptop's (for example `~/Work/.ltcm-main/harness/journal`); it holds the
ledger, the held-out secret, the candidates' patches and receipts, and `canary.json`. The House
reads only `<swarm-state>/harness/canary.json`. `next` prints every candidate's next command.

Once the supervised observer's policy (the `runtime.json` above) is enabled on the House, which is an
operator step with the owner's approval, the observer also measures the last day read-only every 30
minutes and writes `lanes-measurement.json` and `lanes-ranked.json` (mode 0600) into its own
directory; its heartbeat carries `lanes_at`, `lanes_captured`, any `lanes_error` and the gates the
House reads. It never registers a candidate: the operator reads that measurement off the House and
runs `rank` with it, which is the same as step 1 below.

```sh
J=~/Work/.ltcm-main/harness/journal; R=<the owner repository holding the running release's commit>
export LTCM_HARNESS_HELDOUT=~/Work/.ltcm-main/harness-heldout   # the private pools (evaluate only; never the author's)
# The journal commands below re-execute themselves from $J/controllers/<base> (the pinned base's own code).
# 1. Measure (on the House, read only, with the running base release's script; about 1.5 CPU seconds):
python -B /workspace/releases/<running release>/scripts/harness_improve.py measure --swarm /workspace/state --seconds 86400 > m.json
# 2. Rank and register the bottlenecks over their thresholds that repay a cycle (laptop):
python scripts/harness_improve.py --root $J rank --measurement m.json --base FULL_RUNNING_COMMIT --out candidates.json
python scripts/harness_improve.py --root $J --repo $R next
# 3. Open the patch leg and read the brief (never the held-out split):
python scripts/harness_improve.py --root $J --repo $R prepare KEY --worktree ~/Work/harness-cand/KEY
python scripts/harness_improve.py --root $J brief KEY
# 4. The authorized agent writes and commits the patch in that worktree, within the brief
#    (arms lanes: every change in a gated branch whose else is the baseline's code).
python scripts/harness_improve.py --root $J --repo $R stage KEY --candidate FULL_CANDIDATE_SHA --author AGENT --authoring-usd 1.40
python scripts/harness_improve.py --root $J --repo $R evaluate KEY --python ~/Work/.ltcm-main/scratch/venv-a/bin/python
# 5. The adversarial review of the exact patch and tree by another agent (the checklist above), then record it:
python scripts/harness_improve.py --root $J --repo $R review KEY --report review.md --reviewer AGENT2 --patch-sha PATCH_SHA256
#    The deploy step: refuses without that approval (and outside the class's deploy hours); issues the ticket.
python scripts/harness_improve.py --root $J --repo $R deploy KEY
# 6. Only now deploy exactly the named commit through the watchdog under the receipt's deploy rule. Measure on the House
#    with the BASE release's script (B=/workspace/releases/<base release>; `next` prints it).
#    Window lanes: just before the deploy (no earlier than `next` says), measure the control on the House:
python -B $B/scripts/harness_improve.py measure --swarm /workspace/state --since S --until U > control.json   # House
#    After the promotion:
python -B $B/scripts/harness_improve.py measure --swarm /workspace/state --seconds 900 > m.json            # House
python scripts/harness_improve.py --root $J --repo $R canary KEY --measurement m.json [--control control.json] --deploy-usd 3
#    Arms lanes: install $J/canary.json as /workspace/state/harness/canary.json (mode 0600, atomically) within two minutes.
# 7. After the window `next` names:
python -B $B/scripts/harness_improve.py measure --swarm /workspace/state --since S --until U --lanes LANE > m.json
python scripts/harness_improve.py --root $J --repo $R reconcile KEY --measurement m.json
#    Install canary.json again: it now says retained or reverted.
# 8. A retained arms change: graduate it into main without its gate, then
python scripts/harness_improve.py --root $J canary KEY --graduated FULL_MAIN_COMMIT
```

`evaluate` runs the lane's judge on both trees (the candidate with its gate open and closed for the
arms lanes), both splits, and the lane's fixed regressions, in the same credential-free sandbox as
the scheduler lane. The research and memory lanes' regressions include the D2a sentinels
(`league/tests/test_swarm_d2a_sentinel.py`): Validation runs, lines, views and a leaderboard seeded
with sentinel figures, and every text a model reads (the researcher's cycle, status, brief, prompt
and `read_run` tool, the architect's prompt, the strategist's and the diagnostician's packets)
checked for them in their common printed forms (each figure and its 1.5x twin's rounded or truncated
to 1-6 decimals, as a percent, with separators, in scientific notation, the large ones whole, rounded
or truncated), with the gate forced open as well as closed. A gated leak that prints a sealed figure
in one of those forms fails there by whichever route it came, a key built at run time included; a
figure the model sees only in another form (after arithmetic of its own: a ratio of two sealed
figures, a rank, a shifted or scaled figure; an unusual format) is not caught, and the review checks
for that. Both lanes' regressions also run release B's mechanism test
(`league/tests/test_swarm_mechanism.py`: the researcher runs it, and a shadow verdict stays blind),
and the memory lane's run the card and structures tests (`test_swarm_cards.py`,
`test_swarm_architect_structures.py`): a lever may refuse more, never loosen a complete card, the
card-based rebirth refusal, a rebirth's lineage or its row's and cell's budgets. A failed evaluation
leaves the candidate `revising`; a bottleneck gets three
attempts on one base (each with a fresh held-out seed), then it is `rejected` until a new capture on
a new base.

The loop never changes the objective, sealed data, spend limits or capital permissions: those files
are outside every surface, and the controller writes only its journal, its candidates' artifacts and
its own `canary.json`. It never places an order, funds a service or deploys (its deploy step issues a ticket and
names the tree; the operator sends it through the watchdog); the gate never raises a
cap, because every lane's surface excludes the code that holds caps.

### Before release B runs

The lanes, the gate, the judges' override and the `measure` command reach the House with release B.
Until then (and to produce the first ranked list on Sept 30, 2026), the operator measured the running
House read-only by sending this module's source to a read-only Python on the House with a guard that
refuses every writable SQLite open, and ranked the result on the laptop. Candidates captured on a
release other than the one that will run their canary cannot be staged (the base must reproduce the
measured running tree): after release B deploys, measure and rank again, then run the cycle. The
first cycle's canary needs release B's gate on the House.
