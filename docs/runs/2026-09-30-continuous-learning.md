# Continuous-learning run — September 30, 2026

This continues T0 `2026-09-26T06:23:14Z` and the existing financial reset. Objective and acceptance
evidence: [continuous learning](../goals/LTCM_CONTINUOUS_LEARNING.md). The goal is **not achieved**.

## Reconciliation at 04:32 UTC

- Origin/main: `a6bee4be`; deployed House: `20260929T134303Z-8366493c614c` (R11a).
- House and supervisor verified alive. Health fresh with no failures. Real money enabled; restored
  House real experiment still incorrectly reports `observe: "live"`.
- 55 live Gym families; 1,627 retired; two holdout looks, zero passes; qualified forward table empty.
- Real ledger: nine completed calibration round trips, approximately $18 loss. Calibration is not
  family-performance evidence. No qualified real strategy has established profitability.
- Sail funded balance about $197.88; Claude funded total $200, remaining $55.72. OpenAI roles are
  intentionally disabled and September's allowance is not renewed. No provider/model migration or
  funding increase is part of this run.
- The prior night's forward checkpoint exists. Next nightly job is scheduled for 06:00 UTC.

## Work in progress

- Restoration: reviewed and merged PR #429 as `87af7a62`; 82 local House/live tests pass with pinned
  Gym dependencies, and CI passed on Python 3.11 and 3.14. Release
  `20260930T045038Z-cb6035693ef4` promoted at 04:51:15 UTC and completed its ten-minute health watch
  at 05:01:20 UTC. The restored real instance reports `observe: false`, saved mode `live`; the
  money digest is unchanged. Source hashes confirmed this release changed only the restoration fix
  and its regression test from the previously deployed tree.
- Research efficiency: preserve R11b, fix normal/diagnostician retirement, replace repeated paid
  hold polling with durable waits, and integrate practice-feedback wake events.
- Experiment contract: enforce effective parameter overrides, fast preflight, runtime-state
  invariants, and grounded reviewer context. Any execution-semantics change must invalidate the
  appropriate caches/images/evidence before research/live adoption.
- Practice: build on PR #430 with bounded persistent immutable cohorts, feedback, and fresh
  post-revision evaluation. No practice observation is an automatic real-money promotion.
- Input coverage, economic reconciliation, and persistent measured harness self-improvement remain
  incomplete. Engineering and calibration progress do not establish positive Net.

Private operator evidence lives under the owner's `Work/ltcm-goal-ops/`; no raw quotes, program
parameters, credentials, or licensed data are committed with this record.

## Initial statistical benchmark

`python -m league.swarm.benchmarks --replications 32` exercised the actual summary, Train,
Validation and holdout arithmetic with generated cash outcomes. Protocol SHA:
`aa434f1015839bf98bd0fd4e6d038977bf29bb0933854e891e87e92e82f256ab`.
Evaluator SHA: `2783ee61c3d627754cdfa563ac8e9991fd70f7cda2154b223a35d6a5c911e0fe`.
The development and independent confirmation cohorts each produced:

| Generated case | Pipeline passes / 32 | Finding |
| --- | --- | --- |
| Absent signal | 0 | Rejected before holdout |
| Planted edge | 32 | Detected by the tested statistical path |
| Costs erase gross edge | 0 | Rejected before holdout |
| Edge disappears on unseen data | 0 | 32 holdout looks, all rejected |
| Positive low-frequency edge | 0 | Existing annual trade-count requirement rejects it |

Zero of 32 gives a one-sided 95% upper pass-rate bound of 8.94%, so these controls do not establish
a 5% false-promotion guarantee. This benchmark does not test adaptive search, drift screening,
code review, actual fills, or live promotion. It establishes no market edge. The sparse-case
result motivates an independent study of eligibility rules; no threshold was changed.

The published compute feed also omitted Claude charges while retaining historical OpenAI charges.
The fix uses the existing `other_usd` field, with an end-to-end checkpoint assertion; 63 publishing
tests pass. Complete all-input accounting remains outstanding.

## Integration and remaining adoption checks

The integration tree combines R11b, durable research waits/retirement, the practice league and
immutable cohorts, parameter binding, grounded gate reviews, and the existing history-window
controller (PR #413). The combined initial swarm suite passed 779 tests (one existing skip);
the cohort delta passed 247 focused tests; the merged data tools passed 158 data tests. These
changes are not yet deployed. Engine adoption must invalidate old selection caches, reject late
old-evaluator results, and require current qualification for entries while preserving exits,
historical trials and consumed holdout looks.

Read-only adoption audit: all living families are still Gym; no qualified real strategy. The real
House experiment reads `ctx.params` rather than global `PARAMS`, so binding global defaults does
not change that frozen program's decisions. The residual practice program has no overrides.

At 05:00 UTC the historical collector was alive, with eleven failing tasks left in optional older
history blocks. The base stages are complete. The runner's confirmed quiet cutoff is 05:20 UTC;
the next forward job is due at 06:00 UTC. Historical SIP completion has reached March 2022 but
waits while that collector is running. No vendor failure was relabeled valid data.

Cost reconciliation found another distinction to preserve: at approximately 04:56 UTC the Sail
provider reported $71.90 for all 307 project boxes since T0, whereas the swarm had booked $121.81
of estimated Gym-box usage. These are alternative measures, not additive charges. Recorded model
charges were Sail $197.70, OpenAI $50.23 and Claude $144.69. These were booked totals; that reading
did not establish settlement coverage, and the later journal audit identified outstanding holds.
Data subscriptions and any unallocated standalone work still need reconciliation; none of
these readings establishes complete project Net. Existing ledgers and financial baselines remain
unchanged.

## Release candidate at 05:25 UTC

The candidate now also includes evaluator-scoped adoption, executable qualification proofs,
causal optional share-volume inputs, and PR #425's two-sided single-option families. Adoption
archives old selections, requires current replay evidence, and preserves every trial, holdout
look and reservation. Colliding worker run IDs across evaluator bundles retain separate metrics
and result files. The declared `long_single` family still submits concrete call or put orders;
its joined lineages retain both sides' search history. Constitution and money digests are unchanged.

The combined Gym/live/swarm/data/publishing run exercised 1,599 tests. Its one failing integration
fixture constructed a live band without the newly required qualification proof; the fixture was
corrected and all 36 targeted proof tests passed. The adoption branch separately passed 382 live
and 123 final store/cache/sweep tests. Final combined swarm and hosted CI checks remain required
before promotion of this candidate. The complete final swarm rerun passed 816 tests (one existing
skip), and all 16 integrated harness-controller tests passed, including sandboxed comparisons of
two actual commits. These checks are engineering evidence, not trading returns.

At 05:20:54 UTC the historical runner stopped for its scheduled quiet window, with no requests in
flight and the eleven vendor failures preserved. The collector is clear for the 06:00 UTC nightly
forward job. An audit of the active Train image found volume in 991 of 21,349 underlying sessions;
891 of those sessions contain every expected minute. These historical values lack publication/as-of
receipts: a bar revised after its minute cannot be backdated into the original live decision. The
candidate therefore withholds those minute values and daily sums from strategies. Live first
observations remain available with explicit provenance and restart persistence. The correction's
115 targeted tests passed, including the concrete late-revision counterexample; final integrated
volume checks remain required. Raw coverage does not establish point-in-time input availability.

## Foundation merged; observation through 06:13 UTC

PR #431 passed the gateway job and both complete hosted Python 3.11/3.14 jobs on
`9249c470b48432f4f1116e07d7a7845aced256db`, then merged at 05:59:25 UTC as `ed545499`.
The final local volume/live/qualification checks passed 103 tests. The actual House remains on
`20260930T045038Z-cb6035693ef4`; none of the broader foundation changes has been deployed or
verified in production. The prepared adoption audit must compare the new evaluator, current
entry proofs, trials, consumed looks, frozen exit paths and persistent practice state before
deployment can be described as successful.

Read-only observations at 05:31, 06:05 and 06:13 UTC show a fresh House/swarm heartbeat and no
reported health failures. At the last reading there are 66 living Gym families and 1,676 retired
families, two failed holdout looks, zero passed looks and no qualified forward rows. Those are
research activity counts, not profits. The September 29 nightly forward job has completed and
published its checkpoint; the September 28 checkpoint remains recorded. No trade, allocation,
capital, provider-budget or live-release change was made during this follow-up.

Historical SIP completion still retries March 8, 2022. A read-only probe of the existing provider
endpoint found only the 21:00 UTC close-stamped PLTR bar and zero regular-session bars, both when
requested alone and with the full stock universe. BABA and TSM had one regular-session bar each;
most peers had 390. This establishes a source-coverage gap, not a calendar correction or permission
to synthesize bars. The missing day remains incomplete. Raw response prices are not in this record.

## Research supervision and evidence follow-up

The separate follow-up adds a release-bound read-only harness observer with an explicit private
policy, a lifetime lock, verified recovery after an interrupted process-record write, nonblocking
transition waits, pidfd-bound stop signals, and visible capture/reconciliation errors. The observer
does not author patches, call paid models, evaluate candidates, deploy code or place orders. No
production policy or observer was activated. The combined runtime/hook/lab tests passed 75 cases;
the final nested-error correction passed all 23 runtime/CLI cases. Independent review reproduced
the original failures and confirmed the corrections. Its runbook distinguishes exception handling
from a hard latency bound on synchronous House filesystem work.

Researchers and the Architect also receive cached metadata for the exact active Train image.
Missing, malformed or differently imaged cards remain unknown. Raw volume coverage never grants
point-in-time volume access; publication receipts are still absent from the historical reader.

The [frozen long-single diagnostic](../benchmarks/LONG_SINGLE_GATES_1.md) adds two independent
64-world cohorts using the actual frequency, drift, Validation, holdout and lineage functions.
Both cohorts reject all 12- and 48-trade positive controls, while the deliberately strong
126-trade signal passes in every world. Searching 64 noise policies produces many more attractive
Train candidates; one confirmation candidate passes Validation and is rejected by holdout. Failed
looks and later validations remain counted. No negative control completes the statistical path,
but zero of 64 permits a 4.57% one-sided 95% upper bound per case. This is a synthetic sensitivity
study, not evidence of a market edge, complete pipeline calibration or permission to lower a gate.

The private economic reporter now preserves source receipts and separates booked reservations,
priced charges, finalized box costs and estimates. Independent review caught unknown Claude
gateway settlements being mistaken for priced bills and missing fee/liability coverage being
treated as complete. Corrected schema 2 keeps these unresolved, rejects inconsistent position
counts, and settles a later verified bill exactly once. The 83 accounting regressions pass,
including 28 focused cases independently rechecked. Earlier reports remain historical snapshots;
they are not silently upgraded. External engineering attribution, outstanding reservations and
different billing cutoffs still prevent complete project Net. Fees already present in position
cash are not charged again, and provider box bills replace rather than add to Gym estimates.

The combined follow-up checks passed 178 tests. A final correction for the real book's explicit
reconciliation reason string passed all 28 economics tests; a missing reason remains unknown.
Content checks pass, and the execution fingerprint, model configuration and capital permissions
match the merged foundation. The schema 2 report captured at 06:16:22 UTC has $469.55 of known
inputs, excluding unresolved reservations and unknown external costs. Complete Net remains null.
Its live reconciliation receipt was 619 seconds old, so that snapshot also refuses to certify
broker-adjusted cash from a stale reading; the raw closed book cash remains minus $17.80.

PR #432 passed the gateway and both complete Python 3.11/3.14 jobs on `a79c4924`, then merged at
06:36:59 UTC as `0cf5219b`. The merged commit also passed those jobs. Neither this follow-up nor
the foundation has been deployed. Repeated independently retained harness improvements, qualified
forward strategy profits and positive all-input project Net have not been demonstrated.

## Fifteen-minute observation and historical-data repair

The private 06:15–06:30 UTC cohort records 263 completed cycles across 78 families, 279 returned
model calls, and 282 tool calls on the unchanged actual release. Eighty-four cycles (31.94%) were
paid holds with neither a new trial nor queued Gym work. That is a scheduling bottleneck signal,
not proof that every such call lacked useful context. Separately, 223 Train-window run rows record
222 trials; cycle and run totals overlap and must not be added. There was one cycle error and one
pool batch failure, twelve births, five retirements, and no band transitions. Recorded model
bookings total $1.036539; the separate Gym estimate is $0.282341. These are not reconciled provider
invoices, and the overlapping cycle-cost fields are not extra expenses.

The cohort's raw receipt used a misleading `durable_waits_at_observation` label. Its source was
`heartbeat.status.holding`: the actual deployed scheduler's in-memory backoff count. The private
summary records this correction while preserving the original immutable receipt and hash. It is
not evidence that the merged durable-wait implementation has been deployed.

At 06:51:26 UTC the same release has a fresh heartbeat, no reported House health failures,
77 living Gym families, 46 running researchers, two failed holdout looks, zero passes and no
qualified forward rows. The real ledger still contains only nine closed calibration positions,
with raw cash minus $17.80 including estimated fees. Historical completion still repeats the
March 8 missing-root error. A separate read-only coverage audit found complete minute grids,
matching manifest hashes and no duplicate/out-of-session minutes in all 25 underlying files for
each of September 28 and 29. This says nothing about option-chain completeness or profitability.

The [historical SIP repair](../data-sip-completion.md), frozen at `f02d34b8`, passes 208 focused
data, volume and store tests after integration with current main. Independent review reproduced
and checked the original counterexamples: sparse packets cannot overwrite canonical files;
later dates advance while gaps stay unresolved; retries retain their lifetime budgets; exhausted
queues perform no idle remote work; uncertain final writes get one read-only recovery with no
fourth provider attempt; snapshot/calibration records bind the actual source and image pair; and
nightly verification must match the exact files copied. Partial calibration and a lost final
acknowledgement preserve the original pair identity.

Its readiness certificate covers immutable checkpoints and the fixed historical stock-underlying
windows only. It excludes any retained forward files. Legacy forward auto-adoption remains a
separate protocol limitation, explicitly documented without retroactive certification. No bars
are invented, no sealed image is changed, and complete historical grids still lack publication
receipts for strategy volume. PR #433 passed gateway and complete Python 3.11/3.14 checks on
`a386c09f`, merged at 07:28:50 UTC as `6aa557d7`, and passed those checks on the merged commit.
No provider collection,
deployment, trade, allocation, capital or service-budget change was made during this follow-up.
The production-profitability goal remains unmet.

## Scheduler population scans and isolated local practice

PR #434 shares one lazy agenda read within each scheduler population scan, leaving per-family
notebooks/practice context and transactional hold creation fresh. An independent protocol was
frozen before implementation and produced 160 declared case observations across five alternating
repetitions. In twelve scans of 7, 23, 61 and 127 held families, total SQL statements fell by
40–49%, with unchanged semantic controls. The original one-family judge remained at 5/5 quality,
zero idle turns and 264 statements on both trees: its efficiency-improvement condition was
unsatisfied. This separate study supports an engineering change, not admission or retained
improvement under the registered harness protocol. The unchanged 124-test regression bundle
passed on both trees and the integration tree. Full hosted checks passed; the PR merged at
07:47:49 UTC as `c8313dbc`, which also passed those checks. Nothing was deployed.

The [finite local practice runner](../local-practice.md) is frozen at `b91f1d5d`. It takes only
explicit replay or synthetic snapshots, constructs neither brokerage account nor House, and
executes strategy code in a mandatory isolated child without the input, output, host credentials
or external network. Both code and input provenance are bound to private output. It makes no
eligibility claim and has no researcher-feedback or promotion bridge. Its finite replay and
restart checks do not establish continuous fresh-market learning.

The first independent CLI study used inputs frozen before execution and ran eleven invocations
against `fc889326`. It matched three prespecified invented price-path outcomes, modeled fees,
missing-quote coverage, timestamp refusals and restart totals. Thirteen of fourteen checks
passed. Identical cached reuse failed after read-only ledger inspection because SQLite sidecars
were included in artifact hashes. This failure remains retained. The corrected implementation
checkpoints and finalizes its private databases before hashing; changed committed WAL contents
still cause refusal. A separate exact-pattern scratch recovery fix covers interrupted shadow
writes only in marked incomplete attempts.

All fourteen checks passed in the subsequent exposed-case regression against `b91f1d5d`, with
the original inputs and assertions unchanged. It again terminated after five saved frames and
rebuilt one completed simulation without duplicated trades. Independent review verified both
durability fixes, busy-checkpoint refusal and preservation of committed data. The initial focused
integration suite passed 49 tests; the updated runner tests and new checkpoint regression passed.
Hosted checks are still required for this runner. Private evidence is retained in
`Work/ltcm-goal-ops/practice-runner-evidence` at `f988286`; first and corrected receipt SHA256s are
`3594b022cf0686f4470669e04df7133887bdae1e7635b08b7d499e1f315fe0cd` and
`6b2f8640a125ba2a1895fbe38b3fae5be997946ccda2729058dac6be138adda0`. These invented outcomes
are mechanical tests, never brokerage profit or evidence of an economic edge.

The latest read-only swarm snapshot at 07:38:42 UTC still shows the restoration-only release,
83 living families, 48 running researchers, two failed holdout looks, zero passes and no
qualified forward rows. The old historical completion controller reported a restarted backfill
and was waiting for it. A fresh brokerage read at
07:56:52 UTC reports an active account, no open orders and no options positions. The goal remains
unmet; merged code and synthetic checks do not establish deployed behavior or profitability.

## Sept 30 afternoon: Claude takes over

Codex ran this goal from 04:29 to 08:46 UTC, then reached its usage limit. A Claude session took over at about 15:00
UTC under the same objective and completion criteria. The owner is asked to clear the Codex goal, so that two runs
never operate the House at once.

Nothing below is deployed yet, and every figure is a snapshot. Private details (prices, programs, parameters, account
identifiers) stay in the operator's private goal folder.

### Reconciliation at 14:28 UTC (read-only)

Sources: git, GitHub, the House (SQLite opened read-only), the gateway and the prior transcripts. Nothing in production
was changed.

**Releases**
- **The House** runs the restoration fix, `20260930T045038Z-cb6035693ef4`, built from `87af7a62`: R11a plus #429.
- **Main** is `f082cf5e`. Its 69 commits since that release (#431-#436) are undeployed.
- **Money:** the money digest is `a3e2aa7c`, unchanged by main, and the grant is active.

**Research**
- About 90 living families, all in the Gym band. None holds a validation pass.
- Two holdout looks, both failed.
- Births are 100% debit verticals.
- About 80% of allocation weight sits on three families, none with a validation t of 1 or more.

**Real orders**
- **Calibration:** ten D3 round trips, realized −$16.29. Calibration only, never strategy evidence.
- **The House live test:** real and `observe false`, 2 of its 20 sessions used, no order.

**Cost**
- Known input costs since T0 were $504.64 at 14:17 UTC, a partial list. That puts project Net at about −$521.
- The public site understated cost by about $85. It published no Claude spend, and it booked Sail from the Gym's box
  estimate, not the bill.

**Findings**
1. #427's two money-path guards were not on main.
2. The live path loads Gym and swarm modules, so the D8 money path is wider than `league/live`.
   [operations](../operations.md) has the import-traced list.
3. At 14:03 UTC one program that parsed but did not compile failed a whole eight-program Gym batch, twice.
4. The Python 3.11 CI push job on main was cut off by its 20-minute limit. A cancelled run is not a verdict.
5. Most dormancy deaths in the graveyard were still worded "idle": 1,517 of 1,927 rows, awaiting R11b's migration.
6. **Pre-deploy scan:**
   - engine 4 loads all 106 programs: the alive families, the practice tier and the House test;
   - the House test program's intents were identical under engines 3 and 4 on synthetic data;
   - the live decider's sandbox does not fail open on the root House;
   - but the decider cached a timed-out namespace probe as a permanent failure. That would have refused every spawn
     until a restart, and after five minutes the House would have closed the positions of real instances. #443 fixes
     it.

**The owner's answers** (about 14:35-14:45 UTC):
- **The incubator:** one lot, $150 a week net.
- **Thresholds:** eligibility and scoring rules may change only with fixed-benchmark proof that false promotions do not
  rise and missed signals fall. The sealed holdout, the multiple-testing control and the forward requirement never
  loosen.
- **Spend:** cut burn to evidence, roughly halving $84-104 a day.
- **Net:** counted from the Sept 26 reset.

### Release A

Branch `release/a-20260930` (PR #450) is main `f082cf5e` plus six pull requests, each with adversarial reviews (two for
each money-path change):
- **#437:** #427's live guards on main. A real instance is never an observe one, and the order path refuses any
  instance that is not real.
- **#443:** the decider retries a failed namespace probe, fails closed off a root House, and caps the child's file size
  and processes.
- **#440:** one bad program no longer fails its Gym batch.
- **#439:** funding alerts before the Claude, OpenAI, Sail and burst cliffs.
- **#442:** CI's tests job gets 35 minutes, the hourly run no longer cancels a push run, and the workflow pin is
  re-pinned.
- **#441:** the public cost books Sail as billed and Claude as its own part. Personal-site PR #17 adds Net, the practice
  league and the Incubator label.

The money digest is unchanged. Release A deploys after the session, at 20:05 UTC or later.

**Held back:** #438, an API-misuse preflight. Its review left two should-fix findings. It is swarm-side and ships
separately once clean.

**What Release A resets.** It is the planned evidence reset 1: engine 4 and the Gym and live changes move the
evaluator's execution fingerprint.
- **Cleared:** at its first start, every alive family's derived selection evidence is archived and cleared.
- **Kept:** trials, lineages and consumed holdout looks.
- **Practice:** it starts under the new fingerprint, so the practice league is expected to start nearly empty.

**After promotion:** the operator's steps and checks are in [operations](../operations.md) ("Release A: after
promotion"). This record will log their results.

### The spend decision (16:07 and 16:41 UTC)

The spend review read 48 hours of House records, read-only. All counts below are from that review.

**What paid:**
- The Sail researchers wrote every strong validation: 13 at a validation t of 1.5 or more, 7 of them at 2 or more, and
  one full-line pass, which the audit refused.
- All 13 came from families under three hours old. Breadth beat depth.

**What did not:**
- **Stall rewrites:** 1,002 Train runs of rewritten versions produced 2 validation attempts, neither of them strong.
- **The diagnostician:** 19 rewrites led to 21 Train runs and no validation. It rewrote 10 strong families after they
  validated, and none validated again.
- **Architect births on Claude Sonnet 5.5:** 3 of 841 Sonnet-born families reached a real-type validation at t of 1.5
  or more. 2 of 329 Kimi-K3-born families did. Kimi-K3 is level or better per birth, at about a quarter of the cost.

**What changed.** The settings are in [CHANGELOG.md](../../CHANGELOG.md), Sept 30:
- architect births moved to Kimi-K3 on Sail;
- stall rewrites and the diagnostician were switched off;
- the researcher Sail pace went from $12 an hour (an interim $4 from 16:07) to $1.1;
- the Gym pool went to at most four boxes until Release A.

The gate's review and audit and the strategist stay on Claude. They are cheap, and they are the last reads before a
holdout look.

**The target:** about $2.10 an hour, about $50 a day, against about $4.30 an hour ($103 a day) over the prior six hours.
- Claude's funded room should then last to about Oct 10.
- The Sail guard's brake should move to about Oct 3.

These are projections, not measurements. Top-ups are asked for only when the evidence per dollar after the resets
justifies them. Claude's is $0 for now.

**Near misses.** All twelve families that validated strongly in those 48 hours were retired by the dormancy clause
within one to four hours. None got a second look.
- **The only full-line pass:** the audit refused it for leaking state across runs. That reason was wrong: the runtime
  gives each run a fresh module. But the program read its default parameters instead of its overrides, and engine 4's
  binding fixes that behavior.
- **Planned after Release A:**
  - the extension hold keeps near misses out of the dormancy clause;
  - the operator may revive near misses as lineage continuations. A revival inherits its lineage's trials and holdout
    looks, its re-validation under engine 4 is a new, counted trial, and the holdout still judges it;
  - this record will name the revivals and say that the operator chose them from the validation line.

### Planned Release B: the incubator

**Approval.** The owner approved the incubator on Sept 29, 14:51 UTC. The reading was settled Sept 30:
- **Size:** one lot of an approved real structure, with at most $50 of maximum loss each and at most four open.
- **Weekly stop:** the route stops for the week after $150 of net realized loss.
- **Eligibility:**
  - the family passes Train;
  - it passes the drift screen on its own;
  - its live practice is positive (the captain's reading: at least three sessions, ten closes and 80% coverage);
  - the gate's review and audit stay required.

**What it is not.** Incubator trades are real P&L, but never strategy evidence and never a path to Probe or Sized: only
D2 leads there. The plan is that no second family trades real money on any route, the incubator included, before
exposure-aware allocation exists. Until then, the incubator's caps are its only exposure bound.

**How it ships.** It is a new shadow-to-real route with a new money digest:
1. Release B ships it switched off;
2. the grant is re-ratified at once after promotion;
3. the site's Incubator label goes live (personal-site PR #17);
4. only then is the route switched on.

**When.** Release B deploys overnight, before 13:25 UTC Oct 1, with any Gym or live change left out of Release A. The
earliest possible incubator open is Oct 6, for cohorts that start practice on Oct 1.

**Research-side builds** (family cards, evaluator benchmarks, harness lanes, information-value allocation) do not move
the fingerprint. They ship as soon as they are reviewed.

### The evidence-reset plan

- **Reset 1:** Release A, tonight.
- **Reset 2:** Release B, overnight, before the Oct 1 open. Practice then starts Oct 1 on the final fingerprint, and
  B's reset costs only a few hours of overnight Train evidence instead of a day of research.
- **Until then:** the 16:07 UTC research throttle holds Gym and model spend down, because Train evidence from before B
  is archived at B.
- **After B, the Gym and live paths freeze** (`league/gym`, `league/live`, `LEAGUE_FILES`, the fill model, the Gym
  image) for at least five sessions, and for as long as any family holds Candidate, Probe or Sized or has an
  incubator-bound cohort.
  - The only exceptions are rollbacks and fixes for bugs that block or endanger real orders.
  - Everything else waits for planned releases between evidence windows: harness-lane changes, the fill-model refit
    and new images.
- **Every reset is logged here.** Evidence is never compared across fingerprints, and consumed holdout looks never
  reopen.

Evidence resets so far: 0.

The goal remains unmet. No qualified strategy has traded real money, no harness improvement has been retained, and
project Net is negative.

## Sept 30 night: release A live

All times UTC. Every figure below is a read-only snapshot from the House, the gateway and the broker's records. Private
details (prices, strikes, programs, parameters, account identifiers) stay in the operator's goal folder.

### The deploy

Release A deployed at 20:06Z, just after the money-path window opened at 20:05: House release
`20260930T200604Z-3bf48c3f8f9f`, built from main `777b894f` (PR #450).
- **The watchdog** staged it at 20:06:06, promoted it at 20:06:42 and passed its ten-minute watch with no error alert.
  The verdict was PROMOTED at 20:16:42.
- **The money digest** is unchanged (`a3e2aa7c`), so there was no re-ratify.
- **Evidence reset 1** happened at the first start. The swarm recorded its evaluator (the Gym bundle
  `gym-engine-4-e1c896f8d304`, the image, and the execution fingerprint) and archived every alive family's derived
  selection evidence.

**The adoption check.** A read-only snapshot of the swarm store was taken before the deploy and compared after it. It
covered 1,585 lineages and found **0 violations**: trials, inherited trials and consumed holdout looks were unchanged
in every lineage, with 2 looks in all. Runs only grew.

**After promotion** (the operator's steps; [CHANGELOG.md](../../CHANGELOG.md), Sept 30):
- **The graveyard verdict migration** re-headed 1,611 lessons: DRIFT 1,046, THIN 393, EXHAUSTED 145 and STRESS 27. Five
  IDLE rows remain, for families that never traded on Train. Before, most dormancy deaths still read "idle" (1,517 of
  1,927 rows at the 14:28 reconciliation).
- **The Gym pool** went back to 6 boxes, and the architect's refill to 12.
- **The input capability card** was installed.
- **The harness observer** was switched on in observe mode at 20:19. It has retained no improvement.

**The population** fell from 41 to the floor of 12 within 10 minutes of the deploy. R11b lets researchers retire
mechanisms they refuted themselves, down to the floor. The architect then refills up to 12 births every 20 minutes, on
Kimi-K3.

### Criterion 1 under release A: the restart test and an induced failure

- **The restart test** (20:19:00-20:19:17, `floor_box.py stop` then `start`) ran with a real position open.
  - The House live test's instance came back real, `observe` false, mode live, with no error.
  - The tuition instance holding the open position came back real, tuition and exits-only, with no error.
  - The position was restored.
  - Real money stayed on, and health listed no failure.
- **The induced failure** (about 20:50): the swarm process was killed with SIGKILL.
  - The House's swarm step started a new one within 15 s, with a fresh heartbeat.
  - The alive families (15) and the stored runs (75,473) were unchanged: nothing was lost and nothing was duplicated.

Both halves of criterion 1 have now been shown under the running release. They count only for the release they ran
under, so both are repeated after release B.

**The tuition position.** The first swarm D2 tuition trade, opened earlier on Sept 30 (a 1-lot GOOGL call vertical),
stays open. Release A's adoption dropped the family's tuition row: its validation ran on engine 3, and its review cited
no runtime contract. So its instance became exits-only by design. The program's own closes manage the position, and the
family must qualify again under engine 4 to trade tuition again.

### The first hour (20:17-21:21, read-only)

- 0 cycle errors; House load 0.72.
- 136 Train runs ok, 17 disqualified (11%), 8 validations.
- **Births diversified:** 7 debit verticals, 3 `long_single` and 2 `long_call`. Before, every birth was a debit
  vertical.
- **The tournament** spread its shares at about 10-13% a family. Before, about 80% of the weight sat on three families.
- No gate event yet.

### The near-miss revivals and their honest outcome

Before the deploy, all twelve families that validated strongly in 48 hours had been retired by the dormancy clause
within hours. After the deploy, the operator revived five of them from the validation line as lineage continuations.
Each revival inherits its lineage's trials and holdout looks (none had a look to inherit). Each was asked to re-run its
validated version unchanged under engine 4:
- `silver-industrial-cycle-debit-r` (from v58; its audit refusal for leaking state was a wrong claim, so the revival is
  a deliberate second look at an audit refusal);
- `etf-implied-move-ratio-follow-debi-3` (from v17);
- `second-session-assimilation-call-r` (from v31, lineage `positive-earnings-gap-drift-call`);
- `tlt-realrate-metals-catchup-debit-r` (from v30; it reads module-level parameters with one override, so under engine
  4 it tests the override's behaviour);
- `market-distraction-release-call-r-2` (from v11; a second revival of that program).

**Correction (Oct 1, 07:10).** The claim below was wrong for two of the three rows. A revival's researcher re-ran the
revived code without its stored parameters (or wrote new code), so only `silver-industrial-cycle-debit-r` (and
`etf-implied-move-ratio-follow-debi-3`) ran the revived program exactly. The `second-session` and `market-distraction`
rows are validations of different programs: same code, other parameters. See "Oct 1 morning" below.

**The outcome.** Three revivals have re-validated so far, with numbers identical to their original validations. But the
deflated-Sharpe check (a probability of at least 0.95) now fails for each of them:

| Family | Validation t | Checks met | Validated versions in its lineage | Deflated Sharpe |
|---|---|---|---|---|
| `silver-industrial-cycle-debit-r` | 2.71 | 7 of 8 | 8 | about 0 |
| `second-session-assimilation-call-r` | 2.42 | 7 of 8 | 4 | 0 |
| `market-distraction-release-call-r-2` | 1.78 | fails the t | 3 | 0.905 |

**This is the multiple-testing control working, not a defect.** The deflated Sharpe counts N as the lineage's validated
versions and uses their Sharpe spread (`league/swarm/evidence.py`). Silver's lineage kept producing validated variants
after v58, whose own check had counted N = 1. A heavily mined lineage cannot reach D2 by revival.

The route to D2 is a fresh lineage with few validated versions and a strong t. That is what the breadth-first spend
plan and architect agenda v15 favour (20:42: "what validated", with no clones of the revivals). The revivals can still
reach the incubator (Train, drift and positive practice), which is never evidence.

### Post-close economics

Cutoff 20:00, the Sept 30 close. Scope: from T0 (Sept 26, 06:23:14). Realized options P&L and every input cost; deposits
and equity changes are not P&L.

| Measure | USD |
|---|---:|
| Realized options P&L since T0, all routes, fees in | −27.02 |
| Input costs since T0 | 541.72 |
| **Net** | **−568.74** |
| Net with the open tuition position at conservative marks | −725.80 |

- **Realized P&L.** Calibration −25.80 over 15 round trips; order-less regulatory fees −1.19; an estimate of fees not
  yet posted −0.03. Tuition, the House live test, the incubator and D2 have realized nothing yet.
- **The open tuition position** is −157.06 at conservative marks (bid and ask, with an intrinsic floor), or −71.66 at
  the mid.
- **The broker and the book agree** on option fill cash. Nothing is unreconciled, and the deposit is excluded.
- **Input costs:**

  | Service | USD |
  |---|---:|
  | Sail (billed) | 303.22 |
  | Claude | 162.83 |
  | OpenAI (September, open holds included) | 50.23 |
  | ThetaData (pro rata) | 12.00 |
  | Alpaca market data (pro rata) | 12.50 |
  | TypeSafe (upper bound) | 0.94 |

  The owner's external costs (subscriptions, hosting, the domain) are not yet declared, so they are not included.
- **Burn:** $84.89 over the last 24 hours. At the pace of the last four hours, after the 16:41 cut, it is about $53 a
  day, near the plan's target of $50.
- **Runway at 21:04:** the Sail guard's brake about Oct 3, 20:00; Claude's funded room $37.17.

Net is negative, and criterion 5 is not met.

### The release B plan

Release B (branch `release/b-20261001`, PR #454) deploys overnight, before 13:25 Oct 1. It carries:
- the incubator's live route and money row (#451), shipped switched off;
- L1, the cohort keep (#445);
- the research library (#447) and the gateway's KV binding for it;
- the adoption fixes (#453).

**The order:**
1. the gateway (the library and its cache);
2. the House;
3. at once, the grant's ratification on the new money digest (`a3e2aa7c` → `42c4a3af`). Until then every real entry is
   refused;
4. the incubator switched on, outside a session (the site already labels its rows);
5. the library switched on (`research.enabled`);
6. the restart test and the induced failure again.

**It is evidence reset 2.** `league/live` changes, so the execution fingerprint moves; the Gym bundle and image do not.
- Selection is archived and cleared again.
- Extension holds stand.
- Every practice cohort from release A closes: a new cohort needs a version never practised before.
- Practice on the final code starts at the Oct 1 open. So the earliest possible incubator first look is at the Oct 6
  open, after the sessions of Oct 1, 2 and 5.

**After B, the Gym and live paths freeze** for at least five sessions, and for as long as any family holds Candidate,
Probe or Sized or has an incubator-bound cohort. Rollbacks and fixes for bugs that block or endanger real orders are
the only exceptions.

**Not in B:** the incubator's facts (B2, #444), which it needs before any family is eligible. B2 is swarm-side and no
reset, so it ships after a close once its review is clean. The other research-side builds (#438, #446, #448, #449,
#452) ship the same way.

Evidence resets so far: 1 (release A). Release B is reset 2.

The goal remains unmet. No qualified strategy has traded real money, no harness improvement has been retained, and
project Net is −$568.74.

## Oct 1 early: release B live

All times UTC, Oct 1. Every figure below is a read-only snapshot from the House, the gateway and the broker's records.
Private details (prices, strikes, programs, parameters, account identifiers) stay in the operator's goal folder.

### What release B carried

Release B grew overnight beyond the plan above. It merged to main as `3eaf4d06` (PR #454) with nine reviewed pull
requests and the gateway's KV binding:
- #451, the incubator's live route and money row (B1), shipped switched off;
- #444, B2: the incubator's facts (the Train-and-drift mark, and the incubator's own review and audit) and the reader's
  own belt. A failed review or audit is a bar on the program (its code and params), kept for good: no evaluator
  adoption clears it, and every family that holds the same program reads it;
- #445, L1, the cohort keep, and #455, which makes a restarted swarm whose first read fails keep the saved keep;
- #456, L2', the incubator's keep. A failed read never ends an incubation, and every first look and re-check reads the
  record before today only: the practice row's coverage and open mark are copied at the session day's roll, so today's
  values never decide a check;
- #447, the research library, off on the House until `research.enabled`;
- #453, the evaluator-adoption fixes;
- #448, research compute by expected information value, with structure and mechanism diversity;
- #438, the preflight. It refuses only market-independent misuse of the ctx API, and it refused none of 300 programs
  that ran OK in the Gym. It flags a program that cannot load on the House's Python 3.11
  (`preflight_house_unloadable`).

### The deploy

- **The gateway first:** version `dafcfa05` at 03:48, with the research library and its KV binding. The order routes
  are unchanged. The kill switch stayed false, `/v1/health` answered 200 and the library's health read OK.
- **The House:** release `20261001T034829Z-d823e014ce16`, staged at 03:48:34 and promoted at 03:49:07. The watch's
  verdict was PROMOTED.
- **The ratification** came at about 03:59, after the verdict, on the new money digest `42c4a3af` (the incubator's row):
  the grant's third ratification, active, with capital read afresh at $1,246.73. No real entry was due before the 13:30
  open.

### The checks after promotion (all passed)

- **Evidence reset 2.** The execution fingerprint moved; the Gym bundle and image did not. Each of the 51 families alive
  at the start adopted the new evaluator. A lineage snapshot before and after compared 1,690 lineages and found 0
  violations: trials, inherited trials and consumed holdout looks unchanged, with 2 looks in all.
- **The B2 backfill** read 14 gate events and barred 1 program, before the adoption could clear anything.
- **The live guards.** Real money on; no failures; no working order. The House live test's instance is real and live,
  the tuition instance real and exits-only with its position open, and no incubator (`:i`) instance exists. The
  incubator's block showed the committed table, 0 verdicts and a zero tally.
- **The harness observer** was re-pointed at B's base and release digest.

### Criterion 1 under release B

- **The restart test** (04:00:11-04:00:24, `floor_box.py stop` then `start`) ran with the tuition position open. Both
  real instances came back as before, the position was restored, real money stayed on and health listed no failure.
- **The induced failure** (about 04:00:31): the swarm process was killed with SIGKILL. The House's swarm step started a
  new one within 15 s, with a fresh heartbeat. The alive families (36) and the stored runs (77,027) were unchanged.

Both halves of criterion 1 now hold under the running release.

### The incubator on, and the freeze

The incubator was switched on at 04:01 (`live.incubator` true). Nothing trades on it yet: no family can be pinned
before its cohort's first look, which needs 3 completed sessions and 10 program closes in the record before today. For
cohorts admitted at the Oct 1 open, the earliest first look is the Oct 6 open.

From now on `league/live` and `league/gym` are frozen. Any change there moves the evaluator, which ends every practice
cohort and every incubation. Such changes are batched into planned releases.

### What did not work, honestly

- **The revived near-misses** (corrected Oct 1: only silver's revival re-ran its exact program) re-validated under engine 4, but they fail the deflated-Sharpe
  check: their lineages hold 3 to 8 validated versions (Sept 30 night, above). This is the multiple-testing control
  working, not a defect.
- **The harness's scheduler lane.** Its controller's built-in retention rule proved uninformative: on 291 windows with
  no patch at all, 93% counted as "improved". A rule that passes nearly everything cannot tell a real improvement from
  none. Retained harness improvements must come from the new harness lanes (#449, in review), with private held-out
  pools and real canaries.
- **A runtime skew.** The House runs Python 3.11 with numpy 2.4; the Gym runs Python 3.12 with numpy 2.5. A program can
  load and train in the Gym and still fail to load on the live path. The preflight now flags it; the fix is to align
  the runtimes in a planned release.

### Spend

At 02:47, before the deploy, two settings changed in `swarm.json`:
- `architect.every_seconds` 900 → 1800;
- `researcher.sail_usd_per_hour` 1.1 → 1.3.

With the architect's Claude line at 0, its passes fell back to Sail and used 73% of the $1.10 research pace ($4.14 of
$5.67 since 20:00 Sept 30). Research cycles were starved: no worker was running at 02:43. The architect now runs half as
often and research gets the room, at about the same total Sail draw. Train runs and validation attempts an hour are
re-checked about four hours after B.

### Scoreboard

| Measure | Value |
|---|---|
| Release running | B, `20261001T034829Z-d823e014ce16` (main `3eaf4d06`), gateway `dafcfa05` |
| Net since the Sept 26 reset, at the Sept 30 close | −$568.74 |
| Validation passes alive | 0 |
| Holdout looks | 2, 0 passed |
| Retained harness improvements | 0 |
| Evidence resets | 2 (releases A and B) |
| Incubator | on since 04:01; nothing pinned; earliest first look Oct 6 |

### Next

- **13:31-13:35, the first session under B:** the incubator's pins dated Oct 1, no incubator error, and practice
  cohorts admitted at the open.
- **After the Oct 1 close:** the close's economics, and B' (swarm side, no evidence reset).
- **The library** stays off until the order route's p99 is measured with it under load.

The goal remains unmet. No qualified strategy has traded real money, no harness improvement has been retained, and
project Net at the last close is −$568.74.

## Oct 1 morning: release B', the holdout gate, and two harness defects

### Release B'

B' was promoted at 07:11 as `20261001T071033Z-95efdb353597` (main `03c274c9`). No evaluator adoption followed, and the
lineage snapshots before and after show no change to any lineage's trials, inherited counts or looks. B' is swarm-side and resets no evidence: the money digest (42c4a3af) and the evaluator's execution fingerprint
(47587e22) are unchanged, with no change under `league/gym`, `league/live`, the shared league files, the constitution
or the gateway. It carries:
- **Family cards** (#446) and the final release-B nits (#458).
- **The architect's structure allowlist** (#459), switched on with `architect.structures = "real"`. Since release B,
  47 of 78 births were structures real money cannot trade at this equity (credit spreads, straddles, strangles,
  condors, calendars, diagonals). Births are now only of debit verticals, long butterflies and single long options.
- **The retire guard** (#461). Release B's evaluator adoption cleared every family's selection at 03:51. Within
  seconds, the four families holding validated versions retired themselves, each in a one-call cycle whose reason was
  the evaluator change. A researcher can no longer retire a family whose version's latest verdict is a pass because the
  evaluator changed. An evaluator change re-evaluates; it is never a refutation.

### Why research found almost no Train bests under B

Under release B, 76 of 81 Train runs that met the activity bar failed the drift screen: their profit was the market's
drift, not the signal. Release A passed 141 of 424. The robustness and pool paths were sound. Two causes, both in this
section: B's births leaned away from the structures that had validated, and the families that had passed were wiped and
retired themselves. A proposed change that would keep research selections when only live code changes (#462) is
deferred: the owner's rule treats a live change as an evidence reset.

### The holdout gate held only five roots

The sealed 2026 holdout look for `googl-lags-msft-ai-cloud-qqq-flat` v27 failed three times on Sept 30 with "no holdout
days for GOOGL, MSFT". These were infrastructure failures, not looks: the looks table still has two rows. The cause was
the nightly forward-day chain. It extended the original five-root gate image, and its published checkpoint overrode the
25-root gate named in `swarm.json`, so every gate box since Sept 29 forked from a five-root holdout. The operator
re-based the chain onto the 25-root gate image (no data fetched, no evidence identity moved, no look consumed).
Hardening (the ready file must name the base gate it extends; gate boxes check root coverage before a look) follows
as separate PRs.

### Operator revivals did not run the revived program

A revival makes the retired family's chosen version the new family's version 1, with its stored parameters. The
researcher was asked to re-run it unchanged. It never did. Re-running without code drops the stored parameters, and
cheap researchers often wrote new code at once. Of all revivals since Sept 26, only a handful ran their exact program;
of the Sept 30 night revivals, only silver's and the ETF implied-move family's. The fix (in review) runs an operator
revival's exact program in the harness before the researcher acts, with the same trial counting.

Three more families were revived at 07:02 for Train-tier practice, not D2: `silver-industrial-cycle-debit-r` v20,
`rate-lag-flat-index-meta-mara` v33 and `market-distraction-release-call-r-2` v2. Each passed Train at 1.5x and the
drift screen under release A. Their validation verdicts stand. Two of them (`rate-lag-…-r` and `market-distraction-…-r--2`) retired themselves within 15 minutes, after their
researchers ran new versions and never the revived one: the same defect. No more revivals until the fix deploys.

### Scoreboard (07:25 Oct 1)

| Measure | Value |
|---|---|
| Release running | B', `20261001T071033Z-95efdb353597` (main `03c274c9`), gateway `dafcfa05` |
| Real orders since T0 | calibration: 15 round trips closed; tuition (D2): 1 open, the GOOGL call vertical; House test: 0; incubator: 0; Probe/Sized: 0 |
| Realized options P&L since T0, at the Sept 30 close | −$27.02 (calibration −$25.80; regulatory fees −$1.22; strategy routes $0) |
| Input costs since T0, at the Sept 30 close | $541.72 |
| Net, at the Sept 30 close | −$568.74 |
| Families alive / validated / in practice | 83 / 0 / 0 |
| Holdout looks | 2, 0 passed |
| Births since release B (03:49), by structure | debit vertical 12, credit vertical 13, long single 11, straddle 11, strangle 11, long butterfly 7, condor 4, diagonal 4, iron butterfly 3, calendar 1, long put 1 |
| Train disqualification rate since B | 26 of 487 runs (5.3%) |
| Evidence resets | 2 (releases A and B; B' is not one) |
| Retained harness improvements | 0 |
| Spend, last hour | $1.93/h: Sail models $0.99, Gym boxes $0.94, Claude $0, OpenAI $0. Sail balance $155 at about $45/day during the pre-open burst (ends 13:15) |

The goal remains unmet: no D2-qualified strategy trades real money, no harness improvement is retained, and project
Net at the last close is −$568.74.

## Oct 1 late morning: three more releases, the first holdout look in four days, the swarm window

### Releases (none reset evidence)

- **09:16, money path (#468):** an operator revival now runs its program exactly, code and stored parameters, before
  its researcher can edit it (#465); and the gate hardening (#467): the nightly forward chain must name the gate image
  it extends and cover every root, a gate box checks its holdout coverage before a look, and a look that fails for
  missing data costs no try and bars nothing.
- **10:19, the site feed (#469 = #463):** the House now publishes the levels funnel and each trade's reason, filtered
  so no number, parameter or code reaches the page. The site (personal-site #18) deployed first, at 10:00.
- **11:45, the architect on Sail (#470):** from 08:15 every architect call on Sail spent its whole output budget on
  reasoning, so the answer was empty or cut and counted as no proposals. Family cards (release B') had doubled the
  answer's length. The architect now asks Sail at medium effort, and a cut answer is detected and its complete
  families are kept. The empty passes cost $4.43 today.

### The GOOGL family's holdout look

The revival fix ran the GOOGL family's validated program (MSFT leads GOOGL) exactly for the first time under the
current evaluator. It validated again (t 2.60, 335 trades, deflated Sharpe 0.96), passed review and audit, and took
its one sealed look at the 2026 holdout on the 25-root gate. **It failed:** over 184 sessions it lost $2,968.81 in
backtest terms, a daily Sharpe of −0.16 against 0.10 in validation (p 0.996). The catch-up did not hold out of sample.
The gate barred the program from the incubator. Its open tuition position stays exit-only until it closes. This is the
qualification path working: research, exact re-run, validation, review, audit and a sealed holdout, ending in an
honest no.

### Scoreboard (11:50 Oct 1)

| Measure | Value |
|---|---|
| Release running | `20261001T114505Z-2d791c2ca9e7` (main `9b6d8857`), gateway `dafcfa05` |
| Real orders since T0 | calibration: 15 round trips closed; tuition: 1 open (GOOGL); House test, incubator, Probe, Sized: 0 |
| Net since T0, at the Sept 30 close | −$568.74 (realized −$27.02; costs $541.72) |
| Families alive / validation passed / in practice | 63 / 1 (then failed its holdout) / 3 |
| Holdout looks | 3, 0 passed |
| Births since 07:11 | 11, all real-money structures (4 debit verticals, 7 long butterflies); none 08:15-11:45 (fixed) |
| Train disqualification rate since 07:11 | 19 of 291 (6.5%) |
| Evidence resets | 2 (releases A and B) |
| Retained harness improvements | 0 (the lanes release is in its final judge review) |
| Spend, last hour | $1.89/h; Sail balance $150.57 |

The goal remains unmet.

## Oct 1 afternoon: the lanes release, the edge study, agenda v16c

### Releases, candidates and the site

- **13:34, the lanes release (#466):** harness improvement lanes (#449), the evaluator benchmarks (#452), the memory
  judge's fourth hardening round and the architect's lenient read of a cut Sail answer (#472). Research-class; no
  evidence reset. Harness cycle 2 then registered two candidates on this base: a research-lane change against the
  Train disqualification rate, and a memory-lane change against validation attempts per research dollar. Both touch
  a module the live path loads, so each deploys after a close and runs a canary window during which no other House
  release is allowed.
- **The site.** The owner rejected the swarm-window redesign of the morning, and the prior page was restored at
  13:58 (personal-site #19). His ideas (trade reasons, the swarm's profit line, the live thought queue, performance
  over time, per-trade results, the game's levels) are being added to that prior design as small additions. The House
  already publishes the levels funnel and each trade's filtered reason.
- **14:43, seven operator revivals for practice, not D2:** six re-passed Train and the drift screen with their
  earlier numbers exactly (the revival fix of #465 at work); one failed the drift screen. They are lineage-counted.
- **PR #473 merged:** the gateway's Claude funded total rises to $265 after the owner's top-up. It deploys after the
  close, and the architect returns to Claude within that balance.
- **15:10, handoff:** the owner asked for a stopping point; a new session took the goal over at 15:14 and re-verified
  production (8 of 9 pre-open checks; the ninth is the OpenAI line at $0 by his rule).

### The edge study

Five read-only analyses (cells, structures and fills, deaths, births by route, forward predictiveness), a synthesis
and an adversarial critique. They are operator-only documents because they aggregate Validation and holdout results;
the public-safe conclusions:

- No out-of-sample edge has been shown. Train results predict 2025 weakly, and a Validation pass in 2025 has mostly
  measured the roots' own drift. The three holdout looks since the reset covered two programs, both long-delta.
- The Oct 1 yield collapse was mostly machinery, not the market: the strategist had closed the productive design
  shape on a handful of drift deaths, the architect ran on Sail only and its answers were cut, card refusals pushed
  births into long butterflies (0 drift passes in 40), and researchers retired families before validation.
- The critique corrected the proposed agenda. The corrected text (v16c) carries no cross-family holdout outcomes, caps
  the default shape at half of a pass's births, names the crowded root triangles, and admits a rebirth claim only for
  a real change in inputs. It also split the levers into settings the operator may change now and look-eligibility
  rules that need the owner.

**15:22, applied as settings, no deploy:** v16c is the locked preamble and the fallback agenda (the old fallback
carried Validation figures and is gone); births are limited to debit verticals and two-sided long singles; the cell
rebirth budget rises from 3 to 6 with the row budget and the rebirth rule unchanged; the strategist's single-lineage
section was cleared; and the two practice families of the GOOGL lineage, whose program failed its holdout look this
morning, were withdrawn from practice and the incubator by operator retirement. The open tuition lot stays exit-only to
its programmed exit. A pre-registered 24-hour read runs from 15:22: births of the default shape against the card
budget with refusals counted by cause, drift passes per birth and per shape birth, no root set born more than twice,
zero long butterflies, drift-passing families and validation runs per day, and self-retirements of families awaiting
validation. The stop rule is fixed in advance.

### Scoreboard (15:30 Oct 1)

| Measure | Value |
|---|---|
| Release running | `20261001T133355Z-67c841b645ca` (main `a7542c1c`; main is now `a5a52090` with #473), gateway `dafcfa05` |
| Real orders since T0 | calibration: 15 round trips closed; tuition: 1 open (GOOGL, exit-only); House test, incubator, Probe, Sized: 0; none today |
| Net since T0, at the Sept 30 close | −$568.74 (realized −$27.02; costs $541.72); today's close report follows after 20:05 |
| Families alive / validation passed / in practice | 66 / 1 (then failed its holdout) / 9 rows pinned at the open (7 once the two withdrawals take effect at the next open) |
| Holdout looks | 3, 0 passed |
| Births since 07:11 | 24 (11 long butterflies, 8 debit verticals, 4 long singles, 1 long call); the last three architect passes bore none; the first pass under v16c is due about 15:41 |
| Train disqualification rate since 07:11 | 21 of 496 (4.2%) |
| Validation runs since 07:11 | 12 |
| Evidence resets | 2 (releases A and B) |
| Retained harness improvements | 0 (cycle 2: the research candidate is in verification; the no-retire-while-awaiting-validation fix is in build) |
| Spend, last hour (15:21) | $1.48/h: Sail models $0.99, Gym boxes $0.49, Claude $0, OpenAI $0. Sail balance $145.81, about 4.4 days at $31/day; Claude $34.74 of $200 left until the gateway deploy |

The goal remains unmet: no D2-qualified strategy trades real money, no harness improvement is retained, and project
Net at the last close is −$568.74.

## Oct 1 evening: the close, the Claude top-up, the H1 release

### The close and the economics

- **The Oct 1 close report** (20:31, one cutoff at 20:00, read-only): realized options P&L since T0 is −$37.81, all of
  it calibration (19 closed round trips, −$36.28) and regulatory fees; strategy routes have closed nothing. Input costs
  since T0 are $579.00 on the conservative basis (Sail $331.82, Claude $166.14, OpenAI $50.23 including $20.16 of holds
  that may yet bill, ThetaData and Alpaca data pro rata $29.87, TypeSafe $0.94). **Net −$616.81**; with the open tuition
  lot at its conservative mark (−$133.16) it is −$749.97. Broker fills, fees and the book reconcile; no order was
  working at the cutoff.
- **Burn:** $37.28 over the last 24 hours (Sail models $22.49, Gym boxes $6.11, Claude $3.31, data $5.37). Sail balance
  $138.72.

### The Claude top-up and the H1 release

- **20:32, gateway `4471596a`:** the Claude funded total rises from $200 to $265, exactly the owner's top-up. **20:33:**
  the architect's Claude line goes from $0 to $5 a day inside it (the swarm's cap $263); reviews and audits keep theirs.
- **20:35, House release `20261001T203426Z-6fa69bfcda55` (main `665a9e8d`):** a family whose best Train version awaits
  validation can no longer retire itself (on Oct 1 seven of ten families with a drift-passing version retired before the
  tournament judged it, four of them holding a positive best); the research lane's held-out pool pin after a rotation;
  and the architect's recovery of an answer with a stray brace. No evidence reset (the evaluator's execution
  fingerprint, bundle and image are unchanged), no money digest change, the practice cohorts intact.
- **A harness-loop slip, recorded:** the first capture on the new base was measured 40 seconds after the promote, while
  the swarm still ran the old release, so the research candidate's key was bound to the old tree and its first stage was
  refused (one of its three attempts). The fix is procedural: capture only once the swarm's heartbeat names the new
  release. The candidate is re-captured on the next base.

### Agenda v16c, five hours in (an interim look; the pre-registered read is at 15:22 Oct 2)

Since the 15:22 apply: 43 architect births in 16 passes (31 debit verticals, 12 long singles, no long butterflies),
2.7 births a pass. Of the births at least two hours old, 18% passed the Train drift screen (the 24 hours before: 8%),
and 20-33% of the multi-root relative-state shape did. Drift-passing families ran at about 45 a day and validation runs
at about 58 a day, against targets of 20 each. Two checks fail so far: the same root set was born more than twice (SPY
alone five times) and four births sat entirely inside a crowded root triangle. Most architect proposals that were
refused were rebirths in a buried cell whose claim cited nothing checkable. A drift pass is a cheap filter, not
evidence of edge: these numbers say the funnel is working again, not that a profitable strategy exists.

### Scoreboard (20:45 Oct 1)

| Measure | Value |
|---|---|
| Release running | `20261001T203426Z-6fa69bfcda55` (main `665a9e8d`), gateway `4471596a` |
| Real orders since T0 | calibration: 19 round trips closed (4 today); tuition: 1 open (GOOGL, exit-only to its programmed exit Oct 7); House test, incubator, Probe, Sized: 0 |
| Realized options P&L since T0 | −$37.81 (calibration −$36.28, fees −$1.53; strategy routes $0.00) |
| Input costs since T0 | $579.00 (the owner's external costs not yet declared) |
| Net since T0, Oct 1 close | −$616.81; −$749.97 with the open lot at its conservative mark |
| Families alive / in practice | 17 (start 96, floor 12; the idle rule cleared about 54 parked families woken by the agenda change) / 9 cohorts active, 7 after the two withdrawals leave at the next open |
| Holdout looks | 3, 0 passed |
| Births since 15:22 | 43: 31 debit verticals, 12 long singles |
| Train disqualification rate, last 24 h | 12.4% of 3,788 Train runs |
| Evidence resets | 2 (releases A and B) |
| Retained harness improvements | 0; the research candidate (a static screen for programs that cannot run, gated to a quarter of families) is being re-captured for its 6-hour canary |
| Spend and runway | about $37/day; Sail $138.72 (to the brake line at $32 in about 3.7 days at the current pace), Claude $98.86 of $265, OpenAI $0 by rule |

The goal remains unmet: no D2-qualified strategy trades real money, no harness improvement is retained, and project
Net is −$616.81.
