# Chief architect handoff and the $10,000 mandate

Design decision, September 20, 2026. The recommendations below are a build specification.
They are not a claim that the autonomous engineering worker, external Sail broker or independent
promotion authority already exist. Current implementation evidence is listed separately below.

The immediate objective is an autonomous research and engineering operation that can produce,
test, deploy and retain useful improvements without this chat repairing it. Profitable trading
is a further empirical requirement. The $10,000 buys experiments and a chance to discover an
edge; it cannot establish an exponential profit trajectory in advance.

## 1. Build the API chief architect around a durable engineering queue

The loop is **observe → choose a bottleneck → reproduce → change → independently test →
canary → deploy or roll back → measure → retain the result**. A proposal, a passing unit test
or a merged PR is insufficient to mark an issue resolved. The relevant agent must actually
be able to perform the previously blocked experiment on the deployed release.

Each job needs a stable identity, original evidence, frozen baseline, reproduction, acceptance
checks, expected benefit, maximum spend, dependency list, attempt history, exact commit and
artifact hashes. States should distinguish proposed, admitted, reproducing, patching, testing,
revising, canary, observing, verified, rejected and dormant. Rejected or ambiguous work retains
its costs and evidence. Resume the same accepted provider request after a restart; do not buy
an untracked replacement. Limit attempts, then move to another issue or a different hypothesis.

Astra owns architecture, dependency decisions and difficult repairs. Luna is the first
candidate for inexpensive scoped implementation and error-feedback repair; Sail remains
available for cheap parallel research and isolated execution. Jev supplies frequent typed
semantic judgments and candidate features shared across the fleet. Code handles arithmetic,
exact identifiers and authority. Each model must earn its route through measured task performance.
The objective is useful verified improvements per dollar and per hour, not tokens or PR count.

Current Merton can propose strategies, pure tools, bounded configuration/game changes and
lessons. `league/ci.py` and the gateway prohibit editing core House, accounting, evaluator and
release files. `Merton.follow()` records failed CI but does not repair the proposal. PR #21
demonstrated both registry-format and shared-test-fixture failures that required this chat.
Those are concrete regression tasks for the new worker, using the original failing commits.

Do not broaden the role's file allowlist before the authority separation below exists.

## 2. Keep resource and release authority outside the code it improves

An autonomous architect can have broad ability to propose and test code without possessing
the credentials or authority to approve its own spending and promotion. Routine acceptance
is automated; no human review is required for each ordinary change.

| Component | Architect can improve | Independent enforcement |
|---|---|---|
| Research workers | Prompts, programs, tools, routing and schedules | Reserved budgets, task-scoped capability, sandbox lifetime and concurrency |
| House services | Candidate orchestration, adapters, reports and game allocation | No raw vendor/venue keys; protected accounting and promotion authority |
| Game design | Birth/death policy, research rewards, selection proposals and resource shares | Fixed economic outcome measures; controlled comparison before adoption |
| Experiment methods | New evaluators and simulator versions as candidates | Versioned baseline, independent calibration and real execution evidence |
| Releases | Patches, tests, migrations and rollback proposals | Trusted verifier, exact-commit attestation, canary, rollback and durable audit |

The current gateway already isolates OpenAI, GitHub and venue credentials and imposes caps.
However, the House still holds `SAIL_API_KEY`, and the Sail campaign meter lives in editable
House code. An architect that could replace that code could bypass its own Sail budget.
Add a resource broker outside the mutable House, then remove that key from the House.

The broker must reserve aggregate money before accepting inference or box creation; scope
box IDs to jobs; enforce allowed images, egress, maximum runtime, concurrency and storage;
track ambiguous provider outcomes; and reclaim abandoned boxes. It must reject raw provider
pass-through requests. The existing protected gateway is a candidate location, subject to
provider/Worker timeout and streaming tests. Reuse current services before adding a framework.

The mutable House's shared gateway token must also stop being sufficient authority for new
real-money allocation. An independent promotion service should issue bounded trading mandates
tied to the strategy/release, account, exposure group, capital, loss allowance and expiry.
The order gateway enforces the mandate against its own state. Evidence receipts and capital
records must be stored outside a worker's writable filesystem; SQLite append-only triggers
alone do not protect them from a process that can replace the database.

`Updater._judged_by_itself()` currently runs the incoming release's own content checker.
Present role path guards constrain this arrangement, but it is insufficient for arbitrary core
editing. The independent release verifier must execute trusted checks from a separately
protected version, attest the exact candidate commit, and prevent a later head from inheriting
an earlier head's approval. Candidate tests supplement these checks. Canary health includes
accounting, budget and research semantics as well as process uptime. Failed migrations must
have a tested recovery path before they reach production.

The permanent boundary is the owner's financial mandate, credentials, evidence integrity and
approval authority. Game rules and implementation can evolve through independent comparison.
This allows recursive improvement without asking the candidate to judge its own success.

## 3. Make selection honest before making it large

The current replay archive is useful: code, parameters, data, evaluator and outcomes can be
reproduced. On September 20, Meriwether-8 became the first phase candidate to pass its
historical replay and enter paper trading. A fresh sealed box reproduced both the complete
70-trade result and evaluator output exactly over 2,634 steps. This demonstrates repeatability,
not independent market validation or realized profit.

Current replay penalties follow the candidate's ancestry. `House.enroll()` introduces an
architect strategy without a parent, so a related new founder can start a fresh selection
history. Founder names and family labels are not sufficient identities for experiments.
Record the hypothesis, borrowed artifacts, shared data, search history and dependencies in a
research graph. Do not erase failed trials when an agent dies, renames itself or is reborn.

Keep development data reusable and label it honestly. Lock candidates before independent
evaluation. Separate holdouts and later forward observations from data shown in research;
repeatedly inspecting a historical tail turns it into development data. Calibrate the
selection process on null strategies and planted edges, and account for related trials and
correlated event outcomes. Hundreds of agents betting on the same event do not create hundreds
of independent observations. Repeated search creates selection bias; this is a statistical
constraint on the swarm. [Primary research: The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf).

Researcher-declared probabilities, confidence, win rate and backtest return are not allocation
authority. Measure after-fee, after-spread and after-slippage outcomes, tail losses and capital
utilization. Later validate simulated fills with bounded real execution. Alpaca explicitly
documents omissions such as market impact, latency slippage and queue position in its paper
environment. [Alpaca paper-trading documentation](https://docs.alpaca.markets/us/docs/paper-trading).

Before buying additional data, require a specific hypothesis, existing-data baseline, recorded
coverage gap, limited trial cost, point-in-time timestamps and an acceptance comparison. A
service earns renewal when it enables useful experiments or improves independent outcomes.
Start with the current best-supported market hypotheses; do not fund every niche equally just
because it has a desk. Missing external information and bad execution can dominate model size.

## 4. Turn the incentives into actual allocation and retained knowledge

Use two separate reward mechanisms. Engineering receives a fixed bounty for independently
verified repairs or a measured improvement in cost, latency or experiment reliability. Trading
receives greater resources for credible forward economic performance after costs. Startup
research needs limited seed funding before it has a trading record; it should not have to fake
confidence or depend on winning trades to afford its first useful experiment.

Once credible winners exist, test an initial 80/20 split of discretionary research resources:
80% follows verified marginal benefit and 20% funds different hypotheses and challengers. Compare
this allocation against a fixed baseline before adopting it. Winners can earn 5–10 times the
research allowance, better models and more parallel descendants, within the aggregate budget.
Real capital expands more slowly, using independent forward evidence and total correlated
exposure. A trade winner and an engineering winner need not receive the same reward.

Death means stopping resource consumption and unwinding risk; it must preserve source,
ancestry, negative findings and the reason for retirement. Reward a falsified hypothesis when
it cheaply eliminates a real uncertainty. Do not reward repeating known failures or inventing
novelty. Store many candidate genomes cheaply and schedule bounded concurrent workers, rather
than paying for an always-running sandbox for each identity. More logical candidates can be
useful without increasing active capital or permanent compute in proportion.

Keep fast market decisions in tested programs. Invoke models when evidence, failures or a
research task justify the call. Changing code, tools, strategy parameters and allocation policy
is already meaningful recursive improvement; fine-tuning model weights is optional and should
wait for a substantial set of validated learning examples and a measured cost/quality benefit.

## 5. Spend against milestones and demonstrate the handoff

The accepted $10,000 envelope remains:

| Use | Maximum allocation | Release condition |
|---|---:|---|
| OpenAI architecture, implementation and review | $1,500 | Measured engineering/research outcomes |
| Sail inference and execution | $750 | Completed useful experiments; all hosting included |
| Alternative model/provider comparisons | $250 | A demonstrated unresolved task or cost bottleneck |
| Specific data trials | $300 | Written hypothesis and baseline comparison |
| Shared infrastructure | $200 | Required operation, persistence and recovery |
| Kalshi capital | $1,000 | Staged eligibility; includes existing usable balance |
| Alpaca capital | $1,000 | Staged eligibility; includes existing usable balance |
| Uncommitted reserve | $5,000 | A further justified scaling decision |
| **Total** | **$10,000** | **Ceilings, not prepaid balances or a spending target** |

The initial $500/48-hour foundation phase is already active. It includes $350 reserved for
external OpenAI engineering, $50 for automated OpenAI work, $50 Sail including its $5 operating
reserve, and $50 infrastructure reserve. The grant pilot uses the existing automated allowance.
These reservation figures are not a vendor bill. Its original expiry is September 22 at
1:22 PM Pacific; no deployment resets it and no new live allocation is allowed in this phase.

Accelerate by engineering gates, not by empty observation periods:

| Target window | Concrete deliverable | Acceptance before further expansion |
|---|---|---|
| Next 24–48 hours of engineering | External resource/release authority and the first durable API chief worker | Reproduce and repair a real queued failure; exact-commit independent checks; deploy and verify the unblocked operation |
| Following 2–3 days, or sooner if verified | Close the repair loop and prove recovery | At least three complete unattended repair cycles, plus a forced restart and rejected-regression rollback; a 12–24 hour run with no chat patches and no budget/evidence violations |
| After those gates | Increase experiment throughput, then candidate population | Better useful results per dollar/hour on fresh tasks; trustworthy shared-history accounting; begin staged 100-candidate experiments with concurrency fixed by actual capacity |
| As independent market evidence arrives | Paper candidates, then tightly bounded micro trading | Existing execution, loss-reserve and forward qualification rules; no calendar-based release of money |

These are engineering targets, not a promise that an edge will emerge in that interval.
Financial evidence can take weeks and several market conditions even when software improves
hourly. The service should be capable of operating 24/7; it should also abstain when no eligible
opportunity exists. Keeping the system running and placing trades continuously are different
operating decisions.

The next incremental R&D tranche is at most $750 after the first accepted autonomous loop,
with the later $750 and $1,000 tied to further demonstrated progress. Earlier completion can
bring a release forward; elapsed time alone does not release funds. Current phase limits stay
unchanged until the corresponding budget configuration is deliberately installed. The $5,000
reserve remains outside automatic replenishment. Conditional trading capital is not an R&D
wallet. At a $2,000 trading book, $100/month of recurring costs requires 5% monthly trading
profit just to pay that bill; $300 requires 15%. Those are arithmetic break-even hurdles,
not projected returns. R&D spending and sustainable operating cost need separate reports.

No new account, deposit or subscription is required to complete the next engineering step.
Existing OpenAI access, Sail, Cloudflare and GitHub are sufficient for the first version.
Do not buy another orchestration platform to substitute for the missing loop and verifier.

The installed Jev lane has $10 and up to 100,000 calls, backed by a retained earmark inside
the existing $50 automated foundation allocation. It has no production trading or release
authority. The first 12-case probe measured 0.416-second median latency and $0.000241 total
cost, with 9/12 label agreement; Luna reached 11/12 at greater latency and cost. Jev therefore
earns a broader evaluation, not blanket responsibility for correctness.

The higher-value design is a shared semantic feature service. The API architect generates
and revises question sets; Jev computes them cheaply over recorded evidence and market text;
simple code/statistical models combine them; independent evaluation decides which workflows
survive. Cache versioned features once for the whole swarm and preserve every trial. This
creates another thing the architect can recursively improve without requiring model-weight
training. The [Jev design and measured probe](2026-09-20-typesafe-pilot.md) specify the loop,
current limits and promotion criteria.

## Build order and falsifiable completion checks

1. **External budget broker and trading mandates.** Demonstrate that a modified House cannot
   exceed the campaign, access provider keys, mint a live mandate or create an unmetered box.
   Test parallel requests, provider timeouts, retries, expired leases and broker restarts.
2. **Independent release verifier.** Demonstrate refusal of candidate changes to the verifier,
   evidence tampering and stale-commit approvals. A broken canary recovers the prior release
   with books and state intact. The verifier's code is not part of the candidate's authority.
3. **Durable API chief worker.** Close the original PR #21 failure cases in isolated replicas,
   then a newly observed real issue; preserve failed attempts and resume after interruption.
   Close jobs only after runtime acceptance, and bound each job's cost and attempts.
4. **Independent selection and research graph.** A renamed/reborn related candidate keeps its
   search history; a stale, leaked or repeatedly inspected holdout cannot authorize capital.
   Null-strategy false discoveries and planted-edge power are measured before a large rollout.
5. **Allocator comparison and scale.** Test the proposed reward policy on equal-budget runs.
   Require more useful independent findings or better forward economics, not more births,
   messages, apparent confidence or selected backtest winners.

## Current implemented foundation

- Durable researcher sessions and accepted request identities survive House restarts.
- Candidate input coverage, parameter validation, recorded experiments and blocked engineering
  requests provide useful inputs to the chief worker.
- Priced OpenAI tiers and conservative cost reservation are available through the gateway.
- Luna startup grants and a narrowly scoped invalid-parameter repair path are implemented.
- Architect registry output and the shared test fixtures that blocked a genuine proposal have
  been corrected; the architect's sports candidate merged after checks.
- The first passing replay and its evaluator result reproduced in a fresh credential-free box.

The final deployment capture is the [foundation run report](../runs/2026-09-20-foundation-progress.md). Model-selection
evidence and limitations are in the [model comparison](../runs/2026-09-20-model-routing.md). None of these establish an
autonomous chief architect or a profitable trading business yet. The next release should be
judged on whether the system can close an engineering loop without this chat doing the repair.

## Independent release verification: what exists (Sept 22, 2026)

Build-order item 2 is implemented inside the House box, in `league/updater.py` and
`league/watchdog.py`. The external budget broker (item 1) is **out of scope for this change and is
not built**: the House still holds `SAIL_API_KEY`, and the Sail campaign meter is still House
code. What the in-box verifier guarantees, and what it cannot, is listed below.

A commit of `main` reaches the box automatically only when all of these hold. Each one fails
closed: nothing deploys, and a warning goes on the ledger naming the commit and the rule.

1. **Exact-commit attestation.** `api.github.com` (unauthenticated) must show a run of
   `.github/workflows/checks.yml` on the exact sha, on `main`, started by a push, a dispatch or the
   schedule, completed with `success`. That run's jobs `gateway`, `tests (3.11)` and
   `tests (3.14)` must each have completed with `success` on the same sha.
   - Workflow runs and their jobs are read, not bare check runs or commit statuses. Any workflow
     granted `checks: write` can create a check run in GitHub Actions' name through the API, but
     only a real run of the workflow file has jobs.
   - The tarball is downloaded by that sha, and every member must sit under `<repo>-<sha>/`.
   - Nothing carries over from one head to the next.
2. **The judges do not change by this path.** The candidate may not add, remove or change any
   file in the running release's `ci.FORBIDDEN`: the constitution, the ledger, the book, the
   evaluator, the auditor, `ci.py`, `updater.py`, `watchdog.py`, the campaign and live-money files,
   and now `league/sandbox.py`, which seals the agents' boxes.
   - Its `.github/workflows/` must also hash to `TRUSTED_WORKFLOWS_SHA256`.
   - Such a change lands only through the owner's `scripts/floor_box.py deploy`.
3. **The trusted content checks.** These are the running release's `league/ci.py`, replay
   simulator, safety scanner and bounds, run against the candidate tree as their own process.
   - The process gets a scrubbed environment (PR #82).
   - Its verdict line is keyed by a nonce it reads from stdin before any candidate code loads.
   - `config.json` may move only its dials from the running release.
4. **`real_money` may not change by this path.**
5. **The canary, promotion, watch and rollback**, all unchanged.
   - The attestation is recorded in the watchdog's `start` row, and every row of the deploy
     carries the sha.
   - A staged tree whose digest differs from the attested digest is refused.
   - The attestation also goes on the ledger as `ops.deploy`.

**Owner steps.**
- `api.github.com` is **not** on the box's egress allowlist. On Sept 22, 2026 a lookup from the
  box failed with a name-resolution error, while `github.com` and `codeload.github.com` resolved.
  Until the owner runs `python3 scripts/floor_box.py hosts --add api.github.com`, every automatic
  update is blocked. It fails closed, with the fix in the warning.
- Merton's squash merges are pushed with the Actions token, and GitHub starts no workflow for
  such a push. Commits #86 and #88 reached `main` with no check run at all. The Merton merge job
  now dispatches the Checks workflow, and the Checks workflow also runs hourly.

**Why an engineer worker cannot approve its own deployment through this path.**
- Every signal of approval comes from something its commit cannot change in the same step:
  - a real run of the pinned Checks workflow and its jobs;
  - the running release's checker;
  - the protected-file list of the running release.
- Commit statuses and bare check runs are ignored, since a write token or another workflow can
  create those.
- Changing a workflow or a judge file is refused, and the same edit fails the candidate's own test
  suite on GitHub (`ThePinsFollowTheRepository`).

**What remains in the authority boundary.**
- Once a release is deployed, its code runs as the same Unix user that owns `releases/` and
  `current`. Non-protected House code (`house.py`, `service.py`) could therefore carry a latent
  bypass for the *next* deploy.
  - Examples: a second updater, or a direct call to `league.watchdog deploy`.
  - The in-box verifier judges each candidate; it cannot judge what an approved release does
    afterwards.
  - Closing this needs one of two things: release promotion moved out of the box (the gateway or a
    separate verifier box holding the only write access), or the watchdog run as a separate user
    with `releases/` unwritable by the House.
- The House still holds `SAIL_API_KEY` and the shared gateway token. An approved release can spend
  within the gateway's caps and the Sail account.
- The spending broker and the trading-mandate service remain unbuilt, as described in section 2.
