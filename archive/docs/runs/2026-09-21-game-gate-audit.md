# Evidence gates, reward continuity and the live-learning window

September 20 Pacific / September 21 UTC. This revision follows the owner's explicit request
to remove arbitrary waiting, make the accelerated game mechanically reachable, reward winners
aggressively and replace unsuccessful agents after actual opportunity. It supersedes the
30-block micro rule and the one-hour replay replacement minimum in the earlier
[evening-watch report](2026-09-20-evening-watch.md). Historical results are unchanged.

The owner subsequently replaced the timed pilot with [persistent earned live trading](2026-09-21-persistent-live-trading.md).
The account-action section below records the former, expired window. Use the newer activation
command; the evidence gates and incentive changes in this audit remain in force.

## Findings and changes

The game had genuine mechanical obstacles. A fresh 04:20 UTC snapshot had 25 paper agents,
23 replay agents and no live agents. Hilibrand-2 and Haghani met the paper screen, but the
campaign blocked live admission before a fresh production audit. Their approximately +6.30%
and +3.93% marked paper returns are not realized live returns. Separately, the 30-active-block
micro minimum could not fit inside an eight-hour run. Promotion also reset the record used
for research rewards, consultations and capital recommendations.

The revision implements the following review decisions:

| Requirement | Decision and reason |
|---|---|
| Replay: 20 closed trades, 30 historical blocks, positive tail and lineage-adjusted deflated Sharpe | Retain. This is a computational test of executable code on recorded history, not a required wait in live time. Reusing the tail does not make it independent validation. |
| Paper: 15 hourly or 5 daily blocks | Add an alternative: **10 completed portfolio exposures**, at least 10 closed trades, positive cash-flow-adjusted growth, a fresh profitable flat-account mark and recent drawdown below 15%. Existing block route remains available to overlapping or longer-held strategies. |
| Micro: 30 active blocks | Remove. Conventional route now needs **5 active blocks** and 10 closed trades; alternatively, **10 completed exposures** can qualify without any elapsed-time minimum. Both still require a positive lower confidence bound, nonzero variance and the lopsided-loss check when applicable. |
| Statistical death: wait for 20 blocks | Keep the block route and add death from sufficiently negative completed-exposure evidence after 10 exposures. The 30% drawdown rule remains. |
| Drift needs a long hourly reference | A fast-qualified agent is compared with its qualifying completed-exposure record. Negative drift can demote it before an hourly reference accumulates. |
| Repeated statistical looks | Retain evidence increments: five new blocks or five new exposures. Individual block/exposure routes each receive half of the original promotion allowance and half of the separate death allowance. Polling does not replenish either. |
| Promotion resets resource rewards | Remove. Paper evidence keeps paper weight during early micro trading; current live losses remove that fallback. Scaling keeps the qualifying real record and earns scaled weight. Returns are normalized per hour before comparison. |
| Frontier consultation requires an hourly block | Earned exposure evidence and preserved qualification now count. Credit requirements and short burst consultation pacing remain; shared architect/toolsmith help still serves unqualified agents. |
| Replay replacement requires an hour plus two research attempts | Remove the additional hour. Two completed attempts, no active paid job, and a valid replacement are sufficient. Provider failures are not completed opportunity. The stored v1 `replay_lease_minutes` field remains for compatibility and no longer adds a mandatory wait after completed work. |
| Paper displacement grace | Ten completed exposures let an evidenced non-winner compete for replacement earlier. Positive evidence and active paid jobs are protected. The existing grace remains a fallback for fresh programs or strategies without completed opportunity; a closed market is not an opportunity. |
| Audit veto cooldown | Keep protection against repeatedly purchasing the same verdict. A changed trusted audit policy or a failed API call gets the existing short retry, rather than inheriting a day-long veto. Passing a screen never bypasses the production audit. |
| Full population or niche | Keep bounded concurrency, but retain qualified candidates in the durable queue. Forty-eight active agents can generate many successive experiments; births alone do not establish learning. |
| Research phase blocks all new live money | Prepare a separate, explicit owner activation with a fixed live risk envelope. Research funding and deployment alone do not activate trading. |
| Account reconciliation, fees, cash, reducing-quantity checks, fresh quotes, no shorts/leverage | Retain. These make observations interpretable and constrain actual losses. Entry caps already exempt valid reducing exits. |
| Eight-hour provider deadline and unknown-cost holds | Retain. They define the purchased experiment and prevent retries/restarts from creating an unbounded bill. Existing reconciliation and exits continue. |

An exposure begins when a flat portfolio buys and ends when **all** its positions are flat.
Overlapping contracts and partial exits therefore count as one exposure. The fold uses trusted
cash/position changes, fees and settlements; it retains write-offs, excludes capital transfers
from profit, normalizes by opening capital, and excludes records crossing a rung boundary.
Incomplete legacy or malformed receipts cannot manufacture favorable evidence.

Previously spent statistical allowances remain spent, including legacy full-alpha block looks;
adding the exposure route cannot replenish them. This removes mechanical duplication, not market dependence. Ten exposures are an opportunity
threshold, not proof of an edge. Student-t and loss-rate tests have assumptions; the family
route has its own allowance, and hundreds of selected agents do not have a swarm-wide 5%
false-promotion guarantee. A bounded live pilot is an execution experiment, not authorization
to compound the entire project budget.

## Rewards and providers

Tonight retains hourly payouts, a performance exponent of three, a 15% niche floor, 15-minute
research eligibility, 12 research workers and four replay workers. At matched evidence and rung,
twice the growth earns eight times the performance component. Earned real evidence receives
greater weight than paper; promotion no longer erases it. Replacement requires completed work
or trading opportunity and a ready entrant; no agent earns promotion merely by surviving.

OpenAI's architect/auditor provides expensive design and critique; the frozen Luna/Sail cohort
comparison tests strategy research. Sail also supplies isolated execution. Jev classifies shared
market packets and research outcomes; architect-proposed questions are frozen before later
evaluation. Jev labels cannot promote agents or authorize orders. The burst remains capped at
$250 OpenAI + $75 Sail, with $20 of separately backed Jev allowance. These are ceilings, not
invoices or evidence of positive ROI.

Architect, designer and other role packets now include the actual ladder, remaining experiment
time, live-pilot state and specific promotion holds. They are asked to seek new forward evidence
within that window without forcing unprofitable turnover or counting repeated backtests as learning.

At 05:04 UTC, production reported 48 living agents, 354 completed research sessions, 72 archived
trials (all with manifests), 13 historical passes, and all four books unfrozen. Jev had 19,387
completed market classifications and 797 research classifications, with about $1.995 of known
cost. Unconfirmed work retains its cost holds. These throughput counts do not establish that
selected strategies generalize or that trading profits exceed provider expenditure.

## Verification

The fake-venue integration exercises paper qualification, production-style audit gating, $25
admission, order submission, fills, scaling, reduced performance and demotion/death, with book
reconciliation and ledger verification. Independent replay tests exercise entry to paper.
No verification order reaches a financial account. Additional adversarial tests cover partial
and overlapping positions, deposits, withdrawals, settlement losses, dust write-offs, malformed
receipts, stale marks, open losers, repeated looks, audit races, fixed expiry, preserved losses,
capital headroom, reward continuity and evidence-based replacement.

The reproducible [96-agent synthetic controls](data/2026-09-21-game-gate-controls.json) produced:

| Cohort | Result within at most 48 completed exposures |
|---|---|
| 24 engineered strong mixed-win/loss records | All 24 eligible to scale, after 10–40 exposures |
| 24 zero-gross-edge records with fees | None eligible; 22 held, 2 died |
| 24 negative-edge records | All 24 died |
| 24 tiny all-winning records with substantial downside exposure | None eligible; all held by the loss-risk gate |

These controls establish reachable mechanics and meaningful rejection, not the probability
that a real strategy will pass tonight. Reproduce with:

```sh
python scripts/verify_learning_gates.py
python -m unittest league.tests.test_episodes league.tests.test_live_pilot league.tests.test_ladder
```

Full CI and production deployment acceptance are recorded on the implementation pull request.
A finite test suite cannot certify the absence of every bug. Actual live execution remains
unverified until the account action below is taken and an agent earns admission.

## Account action

The prepared window permits up to **eight** live agents, each starting at **$25**. An agent that
passes the scaling gate may receive up to **$50 of net capital**, subject to remaining aggregate
headroom. **$200** is the single aggregate loss/risk envelope across micro and scaled agents,
including earlier losses and abandoned exposure. Scaling and expiry never erase that accounting;
profits are not a license to raise the net owner-funded ceiling. Eight seats are a maximum, not
a promise: a winner's larger allocation can leave room for fewer agents.

After the implementation release is accepted, the account owner can inspect and activate:

```sh
cd ~/Work/long-term-capital-management
python scripts/live_pilot.py
python scripts/live_pilot.py --activate micro-learning-20260921
```

The first command only reports. The second enables eligible agents to seek fresh audits and
trade automatically inside the prepared policy. No agent is selected by this command. Existing
venue balances suffice for this envelope; no deposit is part of activation. The assistant's
verification/deployment does not execute the activation command.

The window ends at the existing burst deadline: **04:01:16 AM Pacific September 21**
(`11:01:16 UTC`). Restarting or rerunning the same command cannot extend it, create another
window or reset losses. New buys are checked again at submission; exits remain available.
Outstanding orders still require normal polling and reconciliation. The original foundation
and all provider commitments are retained. A changed constitution invalidates the grant.

`health.json` exposes `campaign.live_pilot` and each current program's `promotion_status`:
evidence, campaign, live book, tuition, audit credits, audit cooldown, auditing, veto or promoted.
Agents receive the same effective policy and status in research context. A paper screen pass
must therefore no longer disappear into an unexplained hold.
