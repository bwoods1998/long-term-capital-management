# LTCM overnight build: capital is the ladder (Sept 23, 2026)

An eight-hour autonomous build. It turns the league into a floor where an agent's money is its
rank and moves at every settlement, where research is machine-scale search against a verifier the
agents cannot fool, and where the swarm pays for and repairs itself. It ends with at least ninety
minutes of watching the agents play and fixing what breaks.

## The owner's direction

The owner, Sept 23, 2026, at about 06:00 UTC:

> "I deeply want to speed up the dynamism of agents moving up and down the levels of the game as
> quickly as possible and aggressively aligned on incentives so star traders can compound and run
> wild and profit exponentially and losing agents die off and we have this beautiful creative
> destruction in our agents and you can see it on the website ... allow for trading to be done on
> the timescale of 24/7 agents not human clocks and defined times."

> "I don't want to force the agents into any predefined strategies that would be too rigid ...
> we're here to simply design the most aggressive incentivized and resource rich environment for
> them to find that alpha."

> "I still have $100 in each sail and openai and $26 at jev so don't hesitate to burn as much of it
> as you need ... trading live on both my kalshi and alpaca account, I'm willing to accept
> volatility and risk of these funds ... The worst thing to me is making no progress and seeing no
> trading besides these tiny weather kalshi contracts."

The proposal behind this plan is in [the north-star run record](../runs/2026-09-23-north-star.md)
("Top three ideas") and in the four swings discussed after it. The owner approved all four.

## The target at the deadline

1. **Capital is the ladder.** Every agent's rank is its capital. Capital moves at every mark and
   settlement, driven by evidence, with no calendar gates.
2. **Both venues trade live.** Real-money bunts and swings run on both Kalshi and Alpaca, around
   the clock, sized by evidence.
3. **The Alpha Lab runs.** It evaluates at least a thousand strategy programs an hour in a sealed
   batch evaluator, evolves them, and graduates survivors to paper.
4. **Compute follows profit.** Compute grows with verified profit, and the House tick never stalls
   on background work.
5. **The site shows it live.** The capital board shows agents crossing bands, being born and dying.
6. **The build is watched.** At least ninety minutes of observation are recorded, with the defects
   fixed, docs current, the repo clean, and a morning report delivered.

## Principles that must hold

1. **Evidence is wealth.**
   - An agent's paper purse is traded under conservative fills with fees, so its wealth multiple
     is an anytime-valid e-value against "no edge after fees". By Ville's inequality, an edgeless
     strategy reaches W ≥ 1/α with probability at most α, however it sizes or times its bets.
   - So there are no looks, no blocks and no calendars. Sizing is the agent's own choice: a big
     swing with an edge compounds evidence fastest, and one without an edge ends in death.
2. **We design the environment and the agents find the alpha.** No predefined strategies, no
   forced templates, no desk-specific strategy data mandated by the House. Give them resources,
   verifiers and incentives.
3. **Money moves at agent speed.** Promotion, demotion, stake size and death are decided at each
   mark pass and settlement, around the clock.
4. **Incentives have teeth.** Capital, compute (a performance fee), reproduction and death all
   follow evidence. Stars compound, and losers drain and die.
5. **Verifiers are honest.**
   - Paper fills are conservative. The sealed holdout stays rationed.
   - No agent grades its own work. No trade is forced to make the night look good.
   - No evidence is fabricated.
6. **The envelope and the gateway are the whole risk budget.** They are the live grant's per-venue
   capital ($517.75 Kalshi, $500 Alpaca), the gateway's $75 order cap, day caps and kill switch,
   and no leverage or shorts. Inside them, the allocator decides.

## Clock, budget, authority

- **The clock.** The first action is to write the absolute start time T0 and deadline T0 + 8h into
  the execution record `docs/runs/2026-09-23-capital-ladder.md`, then commit it. A context reset
  does not restart the clock.

**Budget.** The owner's funded balances. Measure them at T0 and use them freely.

| Line | Approx. at plan time | Tonight's use |
|---|---|---|
| OpenAI (gateway month, House line) | ~$79 left of the gateway's $374 September line; House line ~$75 | Floor research (Luna, ~$4/h), lab mutations (Luna), lab leaps (Sol), audits. Keep $8 for audits. |
| Sail | ~$102 balance, ~$36/day burn | Floor, agents' boxes, the lab box. Keep the House's $10 reserve. |
| Jev (typesafe) | $16.14 of the gateway's $20 cap spent; owner reports $26 at Jev | Classification and hypothesis linking. The cap may be aligned to the funded balance. |

**Authorized:**
- Implement, refactor, test, commit, merge, and run owner deploys (`scripts/floor_box.py deploy`).
- Change money rules, then re-ratify the live grant `earned-live-20260921` within a minute of each
  promotion that changes the money digest.
- Trade real money on Kalshi and Alpaca inside the grant's envelope. Accept volatility.
- Spend the funded compute. Raise the gateway's `FRONTIER_MONTH_USD` and `TYPESAFE_PILOT_USD`, and
  record House top-ups (`scripts/campaign_topup.py`), only up to the owner's funded balances.
- Create one additional Sailbox for the lab.
- Deploy the gateway (`cd gateway && npx wrangler deploy`) and the site
  (`npm run build && npx wrangler deploy` in `~/Work/personal-site`), with their tests green.

**Not authorized:**
- Deposits, transfers between venues, or enlarging the envelope beyond the profit-indexing rule
  (E2).
- Raising any cap above funded money.
- Disabling the kill switch or the gateway caps.
- Running two Houses on one paper account.
- Committing secrets.
- Forcing trades, or fabricating or back-filling evidence.
- Deleting unmerged work.

## Where the floor stands (Sept 23, 2026, about 06:10 UTC)

- **Release:**
  - `main-59f614320f2d` was auto-deployed by the in-box updater. It carries PR #146: a $10 fork
    threshold, no forks into a spent holdout, and the revival skips corrected code.
  - PR #153 (poll the venue before the startup reconcile) is merged. Confirm the updater deployed
    it; if not, owner-deploy main first.
- **Constitution:**
  - The swing-and-bunt revision (PR #143) is in force: constitution digest `64a206c6`, money digest
    `a6b83f9e`.
  - Grant `earned-live-20260921` is active: 16 agents at most, Kalshi $517.75, Alpaca $500.
- **Live agents:** three, all Kalshi favourites — mullins-2, mullins-6, hawkins-19 — holding about
  $183.6 on $180 staked. **The Alpaca real account has never traded.**
- **Population:**
  - 96, the cap: about 41 on Alpaca paper (10+ crypto agents resting orders around the clock) and
    43 on Kalshi paper.
  - Twelve fixed desks (`league/niches.json`).
- **What binds dynamism today:**
  - Evidence clocks: the paper screen needs 3 active hours or a finished day plus 3 closed or
    settled trades. Rung 3 needs a lower confidence bound; a 94¢ favourite needs about 45 clean
    settlements.
  - Scaled positions are capped at $60 (`capital.scaled_limits`), because the book cannot split an
    exit larger than the gateway's $75 order.
- **What binds research today:**
  - One sandboxed replay took about 10 s (03:55Z), and each replay uploads its whole tape. A Sail
    upload hung the House's first tick for about 12 minutes at 05:07Z.
  - 70% of research sessions abstain.
  - The foundry writes one card per call and cards pass replay about a fifth of the time.
- **Box sizes:**
  - The House box has 1 vCPU.
  - The history store is 1.2 GB (`/workspace/state/history/history.sqlite`).
  - The ledger is 204 MB.
- **Watch scripts from the Sept 23 session** (read-only, run on the box through `rx.py`) are in
  `/tmp/claude-1000/-home-bwoods1998-Work/a9b8e67b-f972-4710-bc38-a5a98d444dbd/scratchpad/watch/`:
  `post.py`, `swing.py`, `events.py`, `holds.py`, `births.py`, `inv.py`, `oaih3.py`, `gwh.py`.
  Phase 0 turns them into a durable `scripts/floor_watch.py`.

## Timeline

| When | Main agent | Builders (their own worktrees, merged by the main agent) |
|---|---|---|
| T+0:00-0:30 | Phase 0 | Spawn B, C, D with this file as their brief |
| T+0:30-3:00 | **A**: the allocator | **B**: the capital board. **C**: exit splitting and stake-scaled positions. **D1-D2**: the lab box and batch evaluator |
| T+3:00-3:30 | **Deploy 1** (A+B+C): ratify at promotion, then a 20-minute watch | D continues |
| T+3:30-5:30 | **E**: profit-indexed compute and a tick that never blocks. Integrate **D3-D6** (evolution, graduation, royalties, lab tools) | **F** (stretch) |
| T+5:30-6:00 | **Deploy 2** | |
| T+6:00-8:00 | **The watch**: fix, redeploy as needed, docs, cleanup, report | |

If a workstream slips:
- **A and B come first.** They are what the owner wakes up to see.
- **C and E3 next**: safety for bigger swings, and uptime.
- **D after that.** Ship the lab as far as it is correct, even if graduation is the only piece that
  lands.
- **E1 and F** are welcome but last.
- Never give up the final ninety minutes of watching.

## Phase 0: orient and set up (T+0:00-0:30)

1. Write the execution record with T0, the deadline, and the checklist below. Commit it.
2. Baseline snapshot:
   - release, grant, money digest;
   - population by venue and rung;
   - live agents and equity;
   - real and paper fills in the last hour;
   - OpenAI, Sail and Jev lines;
   - foundry state.
3. **Alpaca live crypto check** (read-only, through the gateway): the account is active and crypto
   trading is enabled (`crypto_status`). If it is not, record it as the owner's step
   (enable crypto in the Alpaca dashboard). Then plan for Alpaca live equities from 13:30 UTC and
   crypto for Kalshi.
4. **Align compute to funded balances:**
   - OpenAI: owner-funded balance versus the gateway month's remaining; raise
     `FRONTIER_MONTH_USD` only up to the funded amount, and top up the House line to match.
   - Sail: read the balance.
   - Jev: raise `TYPESAFE_PILOT_USD` to spent + funded.
5. Create `scripts/floor_watch.py`: one read-only command that prints the watch metrics (see the
   watch section), built from the scratchpad scripts.
6. Spawn the builders (B, C, D), each in its own worktree from `origin/main`, with its section of
   this file as the brief:
   - Run tests with the parallel per-module runner: the scratchpad's `ptest/run.sh`, or recreate
     it. `unittest discover` takes over 20 minutes; the per-module runner takes about 2.
   - Commit and push when green.
   - Report what was verified and what was not.

## Workstream A: capital is the ladder (Swing 1, P0, main agent)

### A1. Evidence as wealth
- `W_paper(agent)`:
  - The agent's wealth multiple on its paper book since it was seated there, stakes added or
    withdrawn excluded. It comes from the evaluator's finished blocks plus the block in progress
    (`Evaluator._unfinished_growth`).
  - Alpaca's paper fills looked optimistic in Sept 22 evidence (haghani's +7.4% paper against
    negative replays). So subtract a conservative execution haircut per filled notional on
    `alpaca-paper` (`evidence.alpaca_paper_haircut_bps`, 10 per side). The Kalshi shadow book
    already fills conservatively: no haircut.
- `W_real(agent)`: the same on its real book since its first real dollar. A real account's evidence
  is never reset by a promotion or a sweep.
- **Combined evidence** `E = W_paper ^ paper_weight × W_real`, with `paper_weight` 0.5: paper
  counts as its square root, and real results dominate as they accrue.
- Compute on every mark pass. Persist `evidence` rows (agent, W_paper, W_real, E, closed trades,
  at) so the site and the watch read one source.

### A2. Bands (the levels the owner watches)

| Band | Rung | Entry | Stake |
|---|---|---|---|
| Replay | 0 | new code, before replay | none |
| Paper | 1 | passed replay | paper purse ($200, as now) |
| Bunt | 2 | `E ≥ bunt_at` (1.03) and ≥ `bunt_min_trades` closed or settled paper trades (5; 3 settlements on event books) | `bunt_usd` per venue: Kalshi $10, Alpaca $15 (Alpaca crypto's $10 order minimum plus fees) |
| Swing | 3 | `E ≥ swing_at` (1.5), `W_real ≥ 1.0`, ≥ `swing_min_real_trades` (8) real closed trades | `bunt_usd × min(E, e_cap)^kappa` (kappa 1, e_cap 20), up to `max_share_of_venue` (0.6) of the venue's capital |
| Star | 3 | top `stars` (3) by real P&L among Swing agents with `W_real ≥ 1.25` | Swing stake, plus perks (A4) |

- Bands are computed, not gated: an agent crosses a band at any mark pass.
- Bunt and Swing map onto rungs 2 and 3, so the grant, tuition, publish and book machinery keep
  working. Every band move writes the usual `eval.verdict` promote or demote row (the site's ladder
  feed shows it) and a `size` row when only the stake changes.
- **Oversubscription:** when the envelope cannot seat every eligible agent, rank by E and seat the
  best. The envelope is the budget, and a newcomer with higher E displaces the lowest bunt.

### A3. Moves down, and death
- **Hysteresis:** leave Bunt when `E < bunt_at × 0.85`; leave Swing when `E < swing_at × 0.85` or
  `W_real < 0.9`.
- **Real drawdown:** an agent that has lost ≥ 35% of its real stake from its high-water mark goes
  back to paper at once. This replaces `micro_demotion` for the allocator path.
- **Death:**
  - `W_paper < die_below` (0.80) after ≥ 10 closed trades, plus the existing `paper_death`
    and statistical death;
  - credits at zero;
  - displacement of the lowest-evidence resident when the league is full.
- **Floor throttle:** if the floor's real P&L since the grant falls below −30% of the envelope,
  every real stake is halved until it recovers to −15%. That is Kelly's own advice when losing, and
  it keeps the night alive.
- Stake changes under 10% are ignored. Shrinking never forces a sale; only free cash comes back
  (as in `capital.resize`).

### A4. Incentives with teeth
- **Performance fee in compute:** 20% (`performance_fee_share`) of each agent's realized real
  profit on a settlement or sell becomes its compute credits, with idempotent ledger ids per
  settlement. Losses charge nothing. Stars buy frontier research, consults and forks with it.
- **Star perks:**
  - research at the winner pace (exists);
  - priority for frontier consults (exists by profit);
  - forks paid from their own credits, now that the fork threshold ($10) sits above the
    endowment (#146).
- **The audit** moves to the first entry into Swing, where size is at stake. Bunts are cheap tests
  and start at once. An agent with a known defect is still audited before any real dollar.

### A5. Integration
- **`league/constitution.py`:**
  - A new money-rule section `allocator` holding every parameter in the table at the end of this
    file, with `enabled: true`.
  - `rungs.2` and `rungs.3` sizing are superseded while it is enabled; keep them for rollback.
  - Re-pin `PINNED_DIGEST` and add the owner-revision comment in the file's style.
- **`league/allocator.py`** (new): evidence, bands, targets and throttle, as pure functions over
  the ledger and books, plus `rebalance(house)`. Add it to `league/ci.py` `FORBIDDEN` (it is a money
  judge).
- **`league/evaluator.py`:**
  - A `wealth()` helper.
  - When the allocator is enabled, the paper screen and micro bound no longer promote; death,
    drift and replay stay.
- **`league/house.py`:**
  - Call `allocator.rebalance` in the mark pass, after `book.poll/mark/reconcile`.
  - Performance-fee grants.
  - `seat()` limits follow the allocator's stake: position cap `position_share` (0.5) of the stake,
    never under the venue minimum, and above $75 only once C lands.
  - The tuition and headroom logic becomes the envelope check.
- **`league/capital.py`:** `resize`, `top_up_micro` and `kelly_stake` are replaced by the
  allocator's targets when enabled.
- **`league/publish.py`:** per agent `band`, `stake_usd`, `evidence` {`W_paper`, `W_real`, `E`,
  `trades`} and `last_move`.
- **`league/rules.py`, `league/playbook/`, `README.md`, `docs/operations.md`,
  `docs/runbook-go-live.md`:** tell the agents and the operators the new game: evidence is wealth,
  the bands, the stake rule, the performance fee, death.

### A6. Tests (write them first where possible)
1. **Evidence:**
   - flows excluded;
   - the unfinished block counts;
   - the haircut applies to Alpaca paper only;
   - W_real survives a promotion and a sweep.
2. **Bands:**
   - crossings in both directions with hysteresis;
   - oversubscription ranks by E;
   - the envelope is never exceeded, per venue and in total;
   - the floor throttle halves and restores.
3. **Stakes:**
   - bunt sizes per venue;
   - E scaling and caps;
   - under-10% moves ignored;
   - shrinking never forces a sale.
4. **Performance fee:** idempotent per settlement; losses charge nothing.
5. **Death:** `die_below`; paper death still applies.
6. **Integration** (a House with a fake real venue):
   - a paper agent with rising W is bunted and trades real money;
   - its stake follows E;
   - a loser is sent back to paper and later dies.
7. **Grant and digest:** the money digest changes, the grant goes inactive until ratified, and
   ratification restores it.
8. **Old-ladder tests** still pass with `allocator.enabled` false (pin them to a pre-allocator
   constitution, as `before_swing` did in `test_evaluator.py`).

### A7. Acceptance
Within 60 minutes of Deploy 1, on the live floor:
- band moves in both directions;
- at least one new real-money agent on each venue (on Alpaca, only if crypto is enabled);
- every real fill inside the envelope;
- the site showing it.

If a venue shows none, say why with the numbers: no agent's E crossed `bunt_at`, the venue
refused, or the market was closed.

## Workstream B: the capital board (builder, P0)
- **Publisher** (`league/publish.py`): the A5 fields plus a `bands` summary (count and capital per
  band per venue) and the last 50 band moves.
- **Site** (`~/Work/personal-site`):
  1. First, `capital/schema.js` accepts the new optional fields (validators refuse unknown fields
     today). **Deploy the site before the floor publishes the fields.**
  2. `capital/capital.js`: The ladder section becomes a live board:
     - one lane per band (Star, Swing, Bunt, Paper, Replay);
     - each agent a bar sized by stake (paper agents by W);
     - moves animated between lanes;
     - births entering at the bottom and deaths fading out;
     - practice rows following the existing practice switch.
  3. Keep the page's rules: no links, "practice" never "paper" (a test enforces it), phone-first,
     CSSOM only.
  4. Update `DESIGN.md`.
- **Tests:** `node --test test/*.test.mjs` plus the contract test on the new fixtures; `npm run
  check`.
- **Acceptance:** blakewoods.us/capital/ shows agents moving between lanes within a minute of a
  published move.

## Workstream C: swings that can be exited (builder, P1, protected files)
- **`league/book.py`:** a reducing order whose notional exceeds the gateway's order cap is sent as
  slices of at most the cap. Each slice is its own venue order; fills are attributed to the one
  intent, with outcome and accounting per slice. Entries are unchanged (each order ≤ $75).
- **Position caps scale with the stake:** `position_share × stake`, no longer capped at four fifths
  of $75.
- **Tests:** a $200 exit becomes three orders ≤ $75; partial fills; a refused slice; reconcile ok
  after every slice; Kalshi and Alpaca; paper and real.
- **Acceptance:** a Swing agent's position above $75 is exited in slices on the fake venue, and the
  book reconciles after each slice.

## Workstream D: the Alpha Lab (Swing 2; builder for D1-D2, then main)

### D1. The lab box
- One dedicated Sailbox, `ltcm-lab`, larger than the House box. Use the Sail API client
  `ltcm/sailbox.py`; the size is the builder's measured choice. Same seal as agent boxes: no
  network, no credentials.
- Development tapes (the dev window only, never the sealed holdout) are uploaded once, keyed by
  digest, and reused.

### D2. Batch evaluation
- `sandbox.replay_batch` (`league/sandbox.py`, protected) and a batch mode in `league/replay.py`
  (protected) run many candidates against one cached tape. The results are the same numbers the
  existing replay gives; a test compares batch against single on the same candidates.
- Target: ≥ 1 candidate a second on the lab box, against about 0.1 a second now.

### D3. Evolution
`league/lab.py` (new) runs a MAP-Elites archive (`lab.sqlite`):
- **Descriptors:** venue, horizon, trades per day bucket, correlation with the live book's returns.
- **Fitness:** walk-forward out-of-sample growth after fees on the development window, with
  minimum trades.
- **Loop:**
  1. Pick parents from the archive: the seeds are living agents' programs, foundry cards and
     founders.
  2. Luna writes batches of mutations and crossovers, told the parent's per-fold results and its
     niche neighbours.
  3. Every Nth batch, Sol makes a conceptual leap, told the archive's shape and the edge map.
  4. Batch-evaluate, then update the archive.
  5. Publish throughput and pass rates.
- **Diversity** comes from the grid, not from House-chosen strategies.

### D4. Graduation
- The best of each niche that clears the replay gate goes to the sealed holdout, through the
  existing `HoldoutSeal` rationing.
- It is then born as an agent with `founder=lab:<lineage>` and seated on paper, where A1's evidence
  takes over.
- At most `lab.max_births_per_hour` (6).

### D5. Royalties
- 10% of the performance fee on a lab graduate's real profit goes to the lab's own compute line.
- Research methods that produce alpha get more search; a lineage whose graduates lose gets less.
- Record authorship on every graduate.

### D6. Scientist tools
Researchers (`league/researcher.py`) get:
- `lab_query`: archive and leaderboard.
- `lab_submit`: queue up to N candidates for batch evaluation on development data; results come
  back in the next pass.

Agents with evidence get longer sessions (`max_turns` 10 → 20).

### Tests and acceptance
- **Tests:**
  - batch equals single;
  - the tape cache never includes holdout data;
  - archive insert and replace per niche;
  - graduation respects holdout rationing and the birth cap;
  - royalties are idempotent;
  - lab spend stays under its line.
- **Acceptance:**
  - ≥ 1,000 candidates evaluated in the first hour of the lab running;
  - archive coverage and pass rates published;
  - at least one graduate born on paper, or the exact stage where candidates fail, with numbers.

## Workstream E: the swarm pays for itself and never stalls (Swing 4)

- **E1. Profit-indexed compute** (P2, gateway):
  - The monthly OpenAI cap becomes `FRONTIER_MONTH_USD + COMPUTE_PROFIT_SHARE × max(0,
    venue_equity − EQUITY_BASELINE_USD)`.
  - The gateway reads venue equity itself, through the venue keys it already holds, cached ten
    minutes.
  - `COMPUTE_PROFIT_SHARE` is 0.3 and the baseline is the grant's capital.
  - Node tests in `gateway/test`. The House line mirrors the gateway's reported cap.
  - Sail cannot be auto-funded from profit (it is prepaid). Report it as the owner's auto-recharge
    decision.
- **E2. Profit-indexed envelope** (P1):
  - The allocator's per-venue capital is `grant capital + max(0, realized P&L at that venue)`, so
    stars' compounding is not capped at the starting envelope.
  - Losses still count in full against the loss line.
- **E3. The tick never blocks** (P1):
  - The tick path never waits on a lock held by background work. The probe box gets a try-lock
    with a timeout; if it is busy, the enrolment defers to the next tick.
  - Sail uploads and execs in background lanes get tighter timeouts, with the failure recorded as
    infrastructure, not as the strategy's.
  - Test it with a stalled fake Sail client: the tick completes and health stays fresh.
- **E4. Caps aligned to funded balances:** Phase 0's step, recorded in the execution record.

## Workstream F: open desks (Swing 3, stretch)
- Add one open desk per venue (`kalshi-open`, `alpaca-open`) whose universe is every tradable
  market on the venue. Capacity is small (8 each) and crowding is priced by the allocator.
- Lab graduates whose programs span desks are born there.
- Agents can request public data through the toolsmith queue (exists). The owner keeps the egress
  allowlist.

## Parameters (defaults; tune within these bounds from evidence)

| Key | Default | Bounds | Why |
|---|---|---|---|
| `allocator.enabled` | true | - | Rollback switch |
| `evidence.paper_weight` | 0.5 | 0.25-1 | Paper is weaker evidence than real |
| `evidence.alpaca_paper_haircut_bps` | 10 | 0-50 | Alpaca paper fills look optimistic |
| `bunt_at`, `bunt_min_trades` | 1.03, 5 (3 settlements on event books) | 1.0-1.25, 3-20 | Cheap real tests, fast |
| `bunt_usd` | Kalshi 10, Alpaca 15 | venue minimum-60 | More agents live at once |
| `swing_at`, `swing_min_real_trades` | 1.5, 8 | 1.2-3, 5-30 | Size needs real evidence |
| `kappa`, `e_cap` | 1, 20 | 0.5-2, 5-50 | Stake doubles with evidence |
| `max_share_of_venue` | 0.6 | ≤ 0.8 | One star cannot take the venue |
| `position_share` | 0.5 | 0.25-1 | Position size follows the stake |
| `stars` | 3 | 1-10 | The site's top lane |
| `hysteresis` | 0.85 | 0.7-0.95 | No flapping |
| `real_drawdown_demote` | 0.35 | 0.2-0.5 | Rise fast, fall fast |
| `die_below` | 0.80 after 10 trades | 0.6-0.95 | Creative destruction |
| `throttle` | −30% halves, −15% restores | - | Survive the night |
| `performance_fee_share` | 0.2 | 0.05-0.5 | Stars earn brainpower |
| `lab.max_births_per_hour` | 6 | 1-20 | Graduates, not floods |
| `COMPUTE_PROFIT_SHARE` | 0.3 | 0-1 | Profit buys compute |

## Deploys and ratification (the runbook)

1. **Merge, then deploy from a clean detached worktree at `origin/main`:**
   - Merge the PR only after CI is green.
   - `cd ~/Work/ltcm-deploy && git fetch -q origin && git checkout -q --detach origin/main && python3 scripts/floor_box.py deploy`
   - Run it in the background, and watch its log for `promoted`, `ROLLED_BACK` and `EXIT`.
2. **Money-rule deploy:** the moment the log says `promoted`, run
   `python3 scripts/live_trading.py --ratify earned-live-20260921` from the same worktree. On Sept
   23 this took 18 s, and the floor never stopped.
3. **The in-box updater** auto-deploys attested main commits that touch no protected file, every 30
   minutes. A manual deploy while it runs is refused ("another deploy or rollback is running");
   wait and retry.
4. **Rollback across a money-rule change** leaves the grant pinned to the new digest. Re-ratify on
   the rolled-back release.
5. **After every promotion, check:**
   - health is fresh;
   - no book is frozen;
   - the grant is active on the expected digest;
   - the first ticks complete.
6. **Gateway and site deploys:**
   - Run their own test suites first.
   - Deploy the site before the floor publishes new fields.
   - Deploy the gateway's profit-indexing with the old cap as the floor.

## The watch (the final ninety to one hundred and twenty minutes)
Every 15 minutes, `scripts/floor_watch.py` records into the execution record:
- **Bands:** agents per band per venue, band moves up and down, and time from birth to first real
  dollar.
- **Real money:**
  - fills per venue (Kalshi and Alpaca), notional and P&L;
  - agents with a real stake;
  - envelope use;
  - throttle state.
- **Evidence:** the top ten by E, and the death count with causes.
- **Lab:** candidates evaluated, archive coverage, pass rates per stage, graduates.
- **Costs:**
  - OpenAI settled plus holds;
  - Sail balance;
  - Jev;
  - compute per $ of real P&L.
- **Health:**
  - tick durations;
  - frozen books;
  - refusals by reason;
  - alerts;
  - publication freshness on the site.

Fix what breaks, and redeploy through the runbook. Do not tune a threshold to manufacture a move.
If a venue has no real trades, report the numbers that explain it.

## Documentation and cleanup
- Keep one execution record (`docs/runs/2026-09-23-capital-ladder.md`): the checklist, decisions,
  deployed commits, measured before/after numbers and remaining work.
- Update:
  - `README.md`: the ladder is now bands of capital;
  - `docs/operations.md`: every new dial;
  - `docs/runbook-go-live.md`;
  - `league/README.md`;
  - `league/CONTRACT.md` (lab tools);
  - `gateway/README.md` (profit-indexed cap);
  - the site's `DESIGN.md`;
  - the agents' rules text and playbook.
- **Cleanup:**
  - Remove the worktrees and branches this build created once merged.
  - List, but never delete, older unmerged work: many `~/Work/ltcm-*` worktrees exist.
  - Leave the owner's main checkout (`~/Work/long-term-capital-management`, which holds untracked
    `docs/goals/`) alone.
- **Memory:** a new project memory for this build, with its MEMORY.md line.

## The morning report (at the deadline)
1. **What is live:** release, commits, money digest, grant state.
2. **What happened to the ladder:**
   - band moves overnight;
   - agents with real stakes per venue;
   - the first Alpaca real trades, or the exact blocker;
   - the top agents and their evidence.
3. **Real P&L per venue**, and the throttle's history.
4. **The lab:** throughput, pass rates, graduates, and what they trade.
5. **Costs:** OpenAI, Sail, Jev, and cost per dollar of real P&L.
6. **Defects** found and fixed, and anything still open.
7. **Rollback instructions**, and the owner's decisions pending: Sail auto-recharge, Alpaca
   permissions if any, envelope and compute indexing.

## Lessons from Sept 22-23 (read before building)
- **Ratify at promotion, not later.** A late ratification once stopped the floor for 9 minutes.
- **A restart can race a fill.** Poll before reconciling (#153). A watchdog reading of a frozen book
  rolls the release back.
- **A background job holding the probe box blocked the tick for 12 minutes** (E3). Until E3 lands,
  a hung first tick clears when the Sail call returns; do not kill the House unless its health is
  more than ten minutes stale.
- **The burst's fork threshold below the endowment filled every desk with forks and stalled the
  foundry** (#146). Watch births by source.
- **The site's validators refuse unknown fields.** A desk row may carry only `DESK_FIELDS` and
  `DESK_OPTIONAL` in `capital/schema.js`, so deploy the site first. That file reads as binary to
  this machine's `grep` (ugrep); use `grep -a` or Python.
- **Never `pkill -f "unittest discover"`:** it kills other agents' runs. Use the per-module runner.
- **Never chain a deploy on grep's exit code.** Commit each merge before the next.
- **Keep the page's copy rule:** practice, never paper.
- **A merged PR is not a deployed feature.** Check the running release's files on the box.
