# Long-Term Capital Management

**An experimental trading league on Kalshi and Alpaca: agents compete for compute and improve
strategy programs, with an autonomous API chief architect as the next engineering milestone.**

Cheap models (open models on [Sail](https://sailresearch.com), and OpenAI's Luna) research and write trading strategies. A
strategy climbs a ladder from mechanical replay, to paper trading, to a few real dollars, to real
size, and only evidence moves it up. Agents earn their share of the compute budget by what they
prove, die when they run out, and fork when they thrive. A frontier model audits an agent before
its first swing at real size (since the allocator of Sept 23, 2026; before its first real dollar
when a defect is already known) and
writes new strategy code, tools and fixes as pull requests that must pass the tests. Venue keys, order caps, OpenAI/Jev limits and the kill switch live in a Cloudflare
gateway that agent code cannot change. The House still holds Sail credentials and enforces its
campaign budget; moving that authority outside the mutable House is part of the architect handoff.

**Current authorization:** [persistent earned live trading](docs/runs/2026-09-21-persistent-live-trading.md)
was activated by the owner on September 21 at 14:10 UTC, using existing venue balances with no live deadline.
It retains the original $500 foundation plus $325 burst accounting and resumes only unused
OpenAI/Sail allowance; the owner's recorded top-ups (`scripts/campaign_topup.py`) have raised the
burst's caps since. Deployment alone cannot activate it; inspect `live_trading.active`. It pins
the money rules, so each owner revision of one is followed by re-ratifying the grant for the same
capital: twice on Sept 21, at 20:26Z on Sept 22, and three times on Sept 23 (Dynamism II at
01:37Z, swing-and-bunt at 03:52:49Z and the allocator at 08:28:13Z).
The [September 21 live watch](docs/runs/2026-09-21-live-hour.md) records current provider funding,
paid SIP/OPRA readiness, the public agent ladder, and the first earned live execution and
settlement: a $5.6733 loss including fees. Its receipt exposed a Kalshi price/fee parsing defect;
the [accounting contract](docs/contracts/2026-09-21-kalshi-fill-accounting.md) documents the fix,
append-only recovery and exclusion of contaminated performance. A profitable live edge and
autonomous repair of the whole harness are still unproved.
Read the [foundation run](docs/runs/2026-09-20-foundation-progress.md),
[phase policy](docs/phase-one.md), [architect handoff](docs/design/2026-09-20-chief-architect-handoff.md),
[model comparison](docs/runs/2026-09-20-model-routing.md),
[Jev integration](docs/design/2026-09-20-typesafe-pilot.md) and the
[Sept 22 routing, caching and economics run](docs/runs/2026-09-22-model-routing-experiment.md).

**The September 22 rebuild** rebuilt the learning loop around evidence. The
[execution record](docs/runs/2026-09-22-overnight-rebuild.md) has what was built and measured, and
[operations](docs/operations.md) has how to pause, inspect, deploy, roll back and recover.
- **Hypotheses, not blind mutations.** Merton writes falsifiable hypothesis cards, and replay
  admits them before any seat. Blind House mutations into dead desks have stopped.
- **Criticism becomes work.** A durable repair queue feeds an engineer. It turns audit vetoes,
  refusals and CI failures into pull requests, which CI and an attested updater carry to the box.
- **Research is gated.** Exact triggers, with Jev as a cheap second opinion, hold back research
  that keeps coming back empty. Luna's prompts are cached.
- **Deeper evaluation.** Alpaca strategies replay on years of SIP history, with a sealed holdout
  and fills informed by recorded quotes. The options desk has a replay of its own.

**The September 23 revision (Dynamism II)** aims the loop at movement up and down the ladder.
Merged repairs are now born even in a full league, and the defective code they correct is
retired. The audit follows promotion to the micro rung instead of standing before it, and the
House pays for it. A daily Kalshi agent with three settled trades is screened after one day. The
budget follows the owner's real spend, and the foundry spends more of it on hourly,
around-the-clock desks. The [execution record](docs/runs/2026-09-23-dynamism-ii.md) has what the
watch measured and what shipped.

**The September 23 north-star build: capital is the ladder.** The owner asked for agents that move
up and down the game "as quickly as possible", on the timescale of 24/7 agents rather than
human clocks, with real money on both Kalshi and Alpaca. An agent's rank is now its **capital**,
and its capital follows its **evidence** (its wealth multiple) at every mark pass, with no calendar
gates. See [Bands of capital](#bands-of-capital) below, the
[plan](docs/goals/LTCM_NORTH_STAR_BUILD.md) and the
[execution record](docs/runs/2026-09-23-capital-ladder.md). The same build added exits sliced to
the gateway's order cap, so a position can follow its stake; [the Alpha Lab](#the-alpha-lab), a
batch search for strategy programs whose survivors are born on paper;
[compute that follows profit](#compute-follows-profit); a House tick that
[never waits on background work](#the-tick-never-blocks); and an open desk on each venue
([Open desks](#open-desks)).

Watch it at [blakewoods.us/capital](https://blakewoods.us/capital/). The design is in
[the game](docs/proposals/2026-09-19-the-game.md) and
[the architecture](docs/design/2026-09-19-architecture.md).

The name is a joke and a warning. No affiliation with the 1998 fund, its partners or its estate.

> The project was rebuilt from a clean slate on September 19 and 20, 2026, and this page describes
> what exists now. The first run (September 15 to 19: chat desks, a committee, shadow books) is kept
> as a record in [docs/history](docs/history/2026-09-first-run-readme.md) and [docs/runs](docs/runs/).

## The game

**The unit of selection is a strategy program, not a chat persona.** A strategy is one Python file
with a `decide(ctx)` function ([the contract](league/CONTRACT.md)). An agent is that file, a cheap
model that researches on its behalf, a small memory, and an account of compute credits. The
first run's chat desks lost money; its code strategies were the only part that learned, so the
rebuild selects on code.

### Bands of capital

Since the owner's revision of Sept 23, 2026 (`allocator` in `league/constitution.py`, enforced by
[`league/allocator.py`](league/allocator.py)), the screen, the micro bound and Kelly sizing below no
longer move anyone to or on real money. They are the rollback path (`allocator.enabled: False`).

- **Evidence is wealth.** `W_paper` is an agent's wealth multiple on its paper book since it was
  seated: stakes lent or returned are excluded, the block in progress counts, and Alpaca paper fills
  are haircut a side by asset class, at each class's measured paper optimism (4 bps crypto, 2
  stocks, 24 options since Sept 23, 2026; 10 on every class before). `W_real` is the same on its real book since its first real dollar and
  is never reset. The evidence is `E = W_paper^0.5 × W_real`. The paper purse is traded under
  conservative fills with fees, so W is an anytime-valid e-value against "no edge after fees": an
  edgeless strategy reaches W ≥ 1/α with probability at most α, however it sizes (Ville).
- **Bands.** The allocator computes them at every mark pass. Each maps onto a rung, so the grant,
  the books, publishing and death keep working. A move writes the usual `eval.verdict`
  promote/demote row, with `band_from`, `band_to`, `stake_usd` and `via: allocator`; a stake change
  alone writes a `size` row.

  | Band | Rung | Entry | Stake |
  |---|---|---|---|
  | Replay | 0 | new code | none |
  | Paper | 1 | passed replay | the $200 purse |
  | Probe | 2 | E ≥ 1.01 and 5 closed practice trades, or 3 settlements on Kalshi, when the agent's family is not proven | $10 at Kalshi, $25 at Alpaca |
  | Bunt | 2 | the same line, when the agent's family's pooled record is proven | $30 at Kalshi, $25 at Alpaca, × W_real up to 1.25 |
  | Family swing | 2 | every member on real money of a PROVEN family whose REAL record passes its entry look -- judged at 15 independent settlements and every 5 more, on those first ones, at 90% -- once that entry is audited; it stays while the whole real record's bound at 80% holds (since Sept 24, 2026, Deploy B) | 2 × the bunt ($60 at Kalshi), doubling after each 10 further winning real settlements, up to Kelly on the bound and 60% of the venue for the whole family, held by measured capacity |
  | Swing | 3 | E ≥ 1.25, W_real ≥ 1 and 8 real closed trades, for a proven family's member only (since Sept 24, 2026); the first swing is audited | the bunt × min(E, 20)², up to 60% of the venue |
  | Star | 3 | the top 3 swings by real P&L with W_real ≥ 1.25 | the swing stake |

  **Promotion on proof** (Sept 24, 2026, the close-the-gaps run). A probe is the bunt band's first
  tier: pocket change for an unproven mechanism. A family is proven when its pooled forward record
  -- every member ever born, living or dead, one observation per independent event, practice at
  half weight and real money in full -- has at least 10 observations and a one-sided 80% lower bound
  above zero on what its events made per dollar they put at risk, each weighing what it put at risk
  (since Deploy B; for a favourites
  record, one of mostly small wins, the House's exact loss-rate bound as well:
  `family_proven.lopsided_gate`); a probe becomes a bunt the pass after that, and a bunt a probe when
  the bound falls. On Kalshi, closed trades and settlements count once per event, so strikes stacked
  on one game are one bet. The board labels each real agent probe, bunt or swing, with its family's
  state, bound, count and capacity, and carries every followed family's record in its `families`
  block (`league/families.py`, the mechanism ledger; a `family.record` ledger row when it changes).
  **The family swing** (Deploy B): a PROVEN family's entry is judged when its REAL record reaches 15
  independent settlements and at every 5 more, on those first settlements, with the lower bound at
  90% above zero (an edgeless family re-read at every settlement at 80% got in 37-44% of the time by
  30-50 settlements; this keeps it near the table's 20%). When a look passes and the frontier auditor
  approves the entry, every member on real money is staked at the family's ramp -- twice the bunt,
  doubling after each 10 further winning real settlements while the whole real record's bound at 80%
  holds -- up to full Kelly on the bound and 60% of the venue for the whole family, held where fills
  at the bigger size halve, and back to bunts, by free cash only, when the bound falls. Leaving the
  swing, a member's new program or a member born into the family lapses the approval: the next entry
  is audited again. On the T0
  snapshot no family qualified: 93c favourites need 32 clean real events for the loss-rate bound at
  90% (a look at 35). An options agent's probe or bunt is one contract's premium, $80, because a
  contract cannot be cut smaller. A position is capped at a fifth of the stake on Kalshi and half at
  Alpaca, never under the venue's minimum order × 1.2 ($1 at Kalshi, $10 at Alpaca). Every order
  stays within the gateway's $75 cap, and an Alpaca order within $68.18, because the gateway prices
  an Alpaca market order at the ask plus 10%.
- **Exits are sliced** (Sept 23, 2026, `league/book.py`). A sell worth more than the order cap is
  sent as slices, each its own venue order of at most the cap, and every slice's fills are
  attributed to the one intent. The book reconciles after each slice. A refused or partly filled
  slice leaves the rest to the next poll, and a restart resumes the plan without sending a slice
  twice. Before this a position could only be as large as one order could close, so positions
  were held to $60.
- **Down.** Hysteresis: a bunt leaves below E 0.8585 once it has 3 independent real results in its
  stay (since Sept 24, 2026: one early loss does not cross it; the stay drawdown and drift still apply), and a swing drops to a bunt below
  1.0625 or W_real 0.9. A 35% real drawdown from the high-water mark of the current real stay sends
  an agent back to paper at once, trial or not. An agent sent back waits an hour before it may bunt again (`reentry_cooldown_hours`), so a
  record near a line cannot flap between books. W_paper under 0.80 after 10 closed trades is death.
  Paper death, statistical death and drift still apply.
- **The envelope.** Per venue, it is the grant's capital plus realized profit there, so stars
  compound past the starting envelope; losses count in full. When it cannot seat every eligible
  agent, the best E goes first, and a newcomer with better evidence displaces the weakest flat
  bunt or probe, one per venue per pass; a probe displaces only a probe, never a proven family's bunt.
- **Throttle.** If the floor's real P&L falls below −30% of the envelope, every real stake is halved
  until it recovers to −15%, but never below the smallest stake that can still trade. Each change
  writes an `ops.budget` row (`what: "allocator throttle"`).
- **Stake changes.** Changes under 10% are ignored. Shrinking returns only free cash and never
  forces a sale.
- **Incentives.** 20% of every realized real profit becomes the agent's compute credits (a
  performance fee, `credit.grant` with id `perf:<ledger id>`).
- **Two defaults set from evidence, inside the plan's bounds.**
  - The Alpaca bunt is $25, not $15. The book refuses an order over half an account's equity, and
    Alpaca takes no crypto order under $10.
  - `bunt_at` is 1.01, not 1.03. At 06:45 UTC no paper agent was near 1.03.
- **Where to read it.** The House writes `allocator-board.json` beside `health.json` and an
  `alloc.board` ledger row every five minutes. `scripts/floor_watch.py` prints it, and the site
  shows it as the capital board.

### The Alpha Lab

Since Sept 23, 2026 (`league/lab.py`, `league/labbox.py`). Search was the scarce thing that
morning. One sandboxed replay took about 10 seconds and uploaded its whole tape, the foundry
wrote one card per call and about a fifth of the cards passed replay, and 70% of research
sessions abstained. The lab makes search cheap and keeps the verifier out of the searchers'
reach.

- **The archive.** A MAP-Elites archive in `lab.sqlite`. A cell is a desk, a horizon, a
  trades-per-day bucket and a bucket of correlation with the live book's real-money returns. Each
  cell keeps the program with the best out-of-sample growth after fees, among those with the
  replay gate's minimum trades and blocks. Diversity comes from the grid, not from strategies the
  House chooses.
- **Where programs come from.** The seeds are the living agents' programs, the foundry's cards and
  the founders. The children are bounded parameter mutants of the elites and Luna's mutations and
  crossovers. After every ten Luna calls, Sol makes a leap for the desk whose grid is emptiest.
  The lab breeds, up to 48 parameter children at a time, whenever fewer than a batch of queued programs
  have their tape built. Each seed needs a tape of its own, and a lab that bred only when its queue
  was short had 191 seeds waiting and gave the elites no children (Sept 23, #173).
- **The search sees two thirds.** Fitness is measured on the first two thirds of the tape the House
  replays that program on. The last third is never shown to the search. The lab box never receives
  a tape that reaches into the sealed holdout.
- **The lab box.** One Sailbox, `ltcm-lab`, size l, sealed like an agent's box (no network, no
  credential), made by `scripts/lab_box.py`. Batches of 32 candidates run there against one
  uploaded tape (`sandbox.replay_batch`, `replay.run_batch`), off the tick. Each candidate's
  result is exactly what a single replay of it returns. Measured on Sept 23: 11.1 candidates a
  second on a Kalshi tape, 3.2 on sports and 1.7 on crypto, against about 0.02 a second one replay
  at a time, and the batch matched the House's recorded single replays 13 times out of 13.
- **Graduation.** The fittest program of a cell that clears the replay gate's numbers is replayed
  by the House on the whole tape. That replay is a counted trial, judged against the program's
  whole selection path. Where the sealed holdout applies, it goes there next and shares that
  path's ration; the lab never spends the last holdout evaluation of a line that is still living. A
  survivor is born on paper with `founder` `lab:<lineage>`, at most six an hour.
- **Incentives.** A tenth of a graduate's performance fee is paid to the lab's compute line as a
  royalty. Researchers can read the archive (`lab_query`) and queue up to eight programs for it
  (`lab_submit`); a submission is neither a trial nor adopted. An agent with evidence (on paper or
  above, with a closed trade) may research for 20 turns instead of 10.
- **Spend.** OpenAI at $1.50 a trailing hour plus royalties, inside the campaign allowance and only
  while the frontier tier is `all`. A pause, a staged release or the Sail meter stops it too.

### Compute follows profit

Since Sept 23, 2026 (`gateway/lib/equity.mjs`). The owner asked for incentives "aggressively
aligned", so profit buys compute:

```
OpenAI month = FRONTIER_MONTH_USD + 0.3 x max(0, real equity - $1,017.75)
```

- **The gateway reads the equity itself**, with the venue keys it already holds: Kalshi's cash
  plus positions, and Alpaca's account equity. The House cannot report its own profit to buy
  compute. An unreadable reading, or one older than twenty minutes, gives exactly the configured
  month.
- **The House follows the gateway.** The House's own OpenAI line rises by exactly the gateway's
  raise and never more (`CampaignBudget.mirror_gateway_bonus`). The raise lapses when the gateway
  has not been read for thirty minutes.
- **Funded money is still the ceiling.** The owner's rule is that no cap exceeds funded money, so
  `FRONTIER_MONTH_MAX_USD` holds the cap at the funded $408. Today profit is measured and reported
  (`/v1/health` `frontier.profit_index.earned_usd`), but it buys nothing until the owner funds
  more.
- **Sail is not indexed.** It is prepaid, so auto-recharge is the owner's decision.
- **The envelope.** A venue's real-money envelope is profit-indexed as well (see
  [Bands of capital](#bands-of-capital)).

### Open desks

Since Sept 23, 2026 (`league/niches.py`). The owner did not want the agents forced into
"predefined strategies", and until then every desk traded a listed corner of its venue. So each
venue also has one desk whose universe is the whole venue:
`kalshi-open` (Greenwich: any Kalshi series but the multivariate combos) and `alpaca-open` (London:
any US stock, ETF or coin against the dollar, never an option), eight seats each and no founders. A
program with no desk of its own (the architect's, the foundry's, a lab graduate's) is born there only
when no single desk holds most of what its NEEDS name (`niches.match`, `niches.spanning`): it spans
desks, or trades markets no desk lists. It is still shown only what it names, twelve at most; one
naming nothing it may trade is shown the first twelve of a discovery list of 24
(`niches.OPEN_DISCOVERY`; Kalshi: the daily survey's busiest series, those no desk covers first;
Alpaca: the other Alpaca desks' symbols, coins first). Measured Sept 23: one
pass over Kalshi's markets resolving within 48 hours is 21 pages, 20,662 markets, about 15 MB and
22 s (372 series trading, 124 of them on a fixed desk's list), so it is the daily survey's work
and never a wake's. The allocator stakes an open-desk agent exactly like any other.

### The rungs before Sept 23, 2026 (the rollback path)

**The ladder.** Every agent climbs the same four rungs, and only evidence moves it. The thresholds
are versioned in [`league/constitution.py`](league/constitution.py), with every owner revision
dated beside the value it changed. The September 20 revision removed the 30-block micro wait and
added a completed-exposure route (see the [gate audit](docs/runs/2026-09-21-game-gate-audit.md)).
Those of September 21 and 22 shortened the paper screen and the replay gate. September 23 put the
audit after promotion and added the settled lane.
What is measured is after-cost log growth in hour/day blocks or completed portfolio exposures.

| Rung | Where it trades | Stake and limits | What moves it up |
|---|---|---|---|
| 0. Replay | nowhere: its code is walked over recorded history in its own sealed box | none | at least 10 closed trades and 20 blocks, and mean growth above -0.05% a block over at least 8 out-of-sample tail blocks (reused development data, not independent forward evidence; above zero until the owner's swing-and-bunt revision of Sept 23, 2026, because replay had been the pessimist and a near-breakeven idea is cheapest judged forward on paper). An Alpaca program whose inputs are in the history store replays on deep history and must pass the sealed holdout too, which is rationed to three evaluations a lineage. The seat it wins costs nothing but compute, and paper is the real out-of-sample test, so there is no multiple-testing penalty here: the gates that spend money (the screen, the audit, the scaled rung's bound) come later. Owner revision of Sept 22, 2026: the deflated Sharpe against the agent's own line (0.5) had deadlocked whole desks, since each failed trial raised the bar for the next; it was 0.75 and 30 blocks before Sept 21, and 20 closed trades before Sept 22. When these rules change, every rung-0 agent gets one fresh replay under them |
| 1. Paper | Alpaca's paper account; a Kalshi shadow book that reads live quotes and fills conservatively | $200 stake, $100 a position, $75 an order (the live account's limits, not the paper account's $100,000) | a **screen**, not a bound: 3 active hourly blocks (1 finished active day for a daily program), **or 10 completed portfolio exposures**, with at least 3 closed trades, growth above zero (the block in progress counted) and a drawdown under 25% over the last 30 blocks (4 hourly, 2 daily and 15% until the owner's swing-and-bunt revision of Sept 23, 2026: the micro rung is where an unproven idea bunts); only while real money is on, the owner's grant allows it, the capital envelope has room for its stake (below) and no audit veto's cooldown is running. **Then the micro stake at once, and Merton's audit after it** (owner revision of Sept 23, 2026): a veto sends the agent back to paper. An agent with a known defect (a red pre-audit, or a merged corrected child of its code) is still audited first. The drawdown is a trailing window because `max_drawdown` is a running maximum and never falls: read over a whole stay, one bad afternoon barred an agent from real money for the rest of its life, and between the screen's limit and death's (then 15% and 30%) it could be neither promoted nor killed. Death still reads the whole stay |
| 2. Micro-real | the real Kalshi and Alpaca accounts | $60 stake, $30 a position, $30 an order, one option contract up to $40 ($25 / $10 / $10 / $20 before the Sept 21 learning surge); down 20% since promotion, or vetoed by the audit that follows promotion, returns it to paper | **3 active blocks or 10 completed portfolio exposures**, at least 3 closed trades of real fills, and a one-sided lower 80% confidence bound on mean growth above zero (its own, or its family's pooled real-money record, with members counted after 5 active blocks, when its own growth is above zero). Promotion spends `promotion_alpha` 0.20 across looks every 3 active blocks; death keeps alpha 0.05 (owner's swing-and-bunt revision of Sept 23, 2026: 5 blocks, 0.05 and a 10-block family member before) |
| 3. Scaled | the real accounts | FULL Kelly on the lower bound of its growth, so the swing grows with the evidence (the owner's swing-and-bunt revision of Sept 23, 2026; half from the Sept 21 learning surge, a quarter before): never under the $60 micro stake, never over 60% of the venue's cash (40% before); a position and an order up to half the stake, never under the micro rung's $30 and never above $60 (four fifths of the gateway's $75 cap, so one order can close a position that has gained a quarter) | nothing: it is resized every epoch, and a drift alarm sends it back down a rung |

These are rung ceilings. Event concentration can be tighter: a new live agent's $60 stake gives
it an $18 single-market cap on Kalshi (30% of its own equity). The shared cap uses the existing funded venue authorization,
including unallocated reserve and deducting losses; it does not mistake the first agent's
stake for the whole authorized account. Strategies and research see effective sizing limits,
remaining per-market capacity and recent refusals. A fresh refusal can prompt research before
the normal interval. See the [capital and feedback contract](docs/contracts/2026-09-21-event-capital-and-feedback.md).

The individual block and completed-exposure paths split a 5% sequential allowance equally for
promotion, and separately for statistical death: look `k` on each path spends
`0.025 x 6 / (pi^2 k^2)`. Statistical looks require five new blocks or five new completed
exposures. An exposure closes only when the entire portfolio is flat; partial exits and
overlapping positions do not multiply samples. The fast path requires a fresh profitable
flat-account mark before promotion. This accounting prevents mechanical duplication; market
outcomes can remain dependent, and these are not swarm-wide error guarantees. The existing
family test has its own allowance. That rationing applies only to a look that runs a statistical test. A **screen** runs
none -- it counts blocks and trades and reads two numbers -- so it costs nothing and is checked
every block; rationing a free check only made an agent wait, and the rationing counts the looks
that really spent something so the free ones cannot push the death test out of reach. A record that wins 80% or more of its trades must also clear an exact
(Clopper-Pearson) bound on its loss rate, assuming one loss of everything at risk that has not been
seen yet: clean wins of +0.5% risking 7% need 46 in a row. On rungs 2 and 3 a CUSUM compares the
edge per closed trade with the record that earned the rung (real fills worse than the paper fills
that earned rung 2 are exactly what it is there to catch); promotion is not tenure.

**Why the first gate is a screen, and what it may cost.** Simulated with the ladder's own code, the
first run's one measured edge (favourites, about 0.09 standard deviations a trade) had a 0% chance
of clearing a confidence bound within a month, and an excellent crypto edge 11% within a week: a
small edge needs about a thousand trades to prove by ANY honest test, and the strict test was
guarding a $25 stake ($60 since the Sept 21 learning surge). So the loss of the micro rung is capped in dollars instead of statistics. The
constitution's **tuition**: at most 4 agents hold real money on rung 2 at once; a new one is seated
only while the net loss of every real-money account that has not earned rung 3, plus what the seated
agents could still lose, reserving each **full $60 stake**, fits under **$50**. **While the owner's
live grant is active, its envelope replaces those two numbers** (`House.tuition`): 16 agents (the
allocation divided by the micro stake; 101, over the $10 Kalshi probe, while the allocator is enabled), a
$1,017.75 loss line, and a line for each venue at its
allocation, $500 on Alpaca and $517.75 on Kalshi. Under the grant every real-money account
counts, scaled ones included. A drawdown stop cannot guarantee an exit price.
The rung is CLOSED when no further agent can ever be seated -- at the loss line, or when the reserve for one
more no longer fits and nobody is seated to change that -- and then everyone on it goes back to
paper and only the owner reopens it. Those two were once different numbers, and between $42.50 and
$50 with nobody seated the gate sealed itself: nothing could be promoted, and the alert that asks
the owner to raise the line could only fire by seating an agent the gate had just forbidden. An
agent that clears the screen and is turned away here now says so, once, with the seats and the
headroom. The strict
test stays where the money is, between micro-real and scaled. Promotion and death spend separate
alpha series there (a look that can only kill spends none of promotion's).

**Death on paper** (owner revisions of Sept 21 and 22, 2026). A paper seat is free and scarce, so a clear loser
gives it up without waiting for a statistical bound: down 10% or more after 6 active blocks, or not
above where it started after 20 (10 and 30 before Sept 22). Death on real money is unchanged. The owner's live-trading grant now
pins only the rules that govern real money (`constitution.money_digest`), so the risk-free rungs can be
tuned without silently revoking it. A change to a money rule still leaves the grant inactive until the
owner re-ratifies it for the same capital (`scripts/live_trading.py --ratify`). The grant recorded before
the Sept 21 revision is honoured only while its money rules are unchanged (`LEGACY_GRANT_DIGESTS`).

**The horizon rule.** Fast results are what a record is built from. The House refuses a Kalshi entry
expected to pay more than 12 hours out (hourly strategies) or 48 (daily), and closes a crypto
position after 48 hours. Equities, and options when they open, are not bounded. A game lists a
close two days after kickoff and really closes when a winner is declared, so markets are shown and
judged by their scheduled expiration.

**Listed options** (built Sept 19, 2026; first trades possible Monday the 21st). Long calls and puts
on sixteen liquid underlyings. The account is approved for level 3, but the gateway itself refuses
anything but long premium: an option order must be one leg, a limit order, in whole contracts, and
`buy_to_open` or `sell_to_close`, so nothing through it can write an option and the most a position
can lose is what was paid. (A short leg can be assigned into a hundred shares this account cannot
carry, with nobody awake to see it.) The gateway also prices a contract at 100 shares: before this
an option order would have been capped at a hundredth of what it spends. One contract cannot be cut
smaller, so the micro rung allows an option position of one contract up to $40 ($20 before the
Sept 21 learning surge). No entry in a
contract that expires today; the House sells anything still held at 14:30 New York on its last
day. Option quotes are fifteen minutes old (the live feed needs the OPRA agreement signed on the
account), which is why every option order is a limit order. At the build there was no replay (no
recorded chains) and paper was this specialty's replay. Since Sept 22, 2026 an options program is
replayed on the options history store (`league/options_replay.py`) once that store covers every
underlying it trades; paper stays the replay for the rest. Not measured at the build, because the market was closed: a
filled option order, Alpaca's end-of-day regulatory fees (the book now books any FEE activity
that explains a cash shortfall), and whether Alpaca holds cash behind a resting option bid (the
book accepts either). An unexplained difference freezes entries, never exits -- on a real-money book until the owner
clears it, and on a practice book only until the third reading that does not reconcile, when the
House takes the venue's word and carries the difference on its own row, crediting no agent.

**The funded campaign.** Production now uses `league/campaigns.py` and the persistent
[phase-one policy](docs/phase-one.md). The initial allowance is $500 over 48 hours, including
external engineering and infrastructure reserves; $50 is available to automated foundation
model work and up to $45 to Sail after its operating reserve. Jev's first $20 allowance is backed
inside that existing model allocation (the gateway's cap is $42 since Sept 23, 2026, with the
owner's funded Jev balance). Calls reserve money before transmission. Since Sept 23,
2026 a verified frontier call settles at the gateway's metered cost, a refused one (HTTP 4xx) at
$0, and a Sail hold older than an hour with no response is absorbed into the account meter, which
already counts its charge. Every other unresolved bill keeps its hold. Restarts, deposits and calendar changes do not renew the phase.
The legacy fourteen-day pacer remains for compatibility and fixtures. Current campaigns have
no catch-up spending or underspend acceleration. The gateway's monthly cap is an additional
ceiling. Credit rewards allocate research access within these limits; creating credits cannot
create vendor budget.

The [September 20 evening experiment](docs/runs/2026-09-20-evening-watch.md) added one immutable
eight-hour research allowance: $250 OpenAI and $75 Sail, ending at 4:01 AM Pacific September 21.
It retains the foundation policy and Jev backing. While the owner's live grant is active this
funded burst has no end (`league/overnight.py`), and the owner's recorded top-ups raise its caps
without resetting what was spent. Its pace is the owner's acceleration layer,
[`league/turbo.json`](league/turbo.json). As of Sept 23, 2026 that is research every 15 minutes
with 16 workers, 12 replay workers, three quarters of new sessions on Luna, a population of 64
and a newcomer every two minutes. The shared Jev lab that ran beside it has been off since
Sept 22 (`semantic_lab`). Faster cycles and stronger resource
rewards are experimental; independent forward evidence still decides whether they help.

**Which model does which work, and what it costs.** `league/routing.py` routes deterministic
work to code, cheap semantic questions to Jev, routine research to the strongest economical model
by measured evidence (Luna, on the Sept 22 experiment: a spawn-valid strategy for about $0.011
against $0.12-0.22 on DeepSeek-V4-Pro; GPT-6 Luna from #129, Sept 22) and hard
synthesis, repairs and audits to Astra, and records each decision as `route.decision`. The
foundry's hypothesis cards are written on GPT-6 Sol, about a fifth of Astra's price, because
replay judges a card before it costs a seat. Luna's research requests put the shared rules, contract and
tools first and append each turn as its own message, so OpenAI's prompt cache pays: a follow-on
turn read 97% from cache and cost 81% less, where the old single-packet layout had read nothing in
15,044 calls. Each finished pass leaves a private transcript and a `trace.record` pointer for
eventual fine-tuning, and `scripts/economics.py` reports trading P&L (real and practice apart),
spend by provider and useful work per dollar, read-only.

**How an agent learns, and what it remembers.** A research pass starts from the agent's JOURNAL
(notes it wrote to its future self and the conclusion of every earlier pass, its ancestors' before
its own: it lives on the ledger, so it survives a restart, a new box and the agent's death), its own
recent trades, and its specialty's brief. It can look at exactly what its strategy sees now
(`markets_now`), search the web, read and write its niche's library, read the graveyard, ask the
toolsmith for a tool, and replay candidate code; a replay answers with WHERE the strategy won and
lost (by series, by how long before a market's end it got in, its worst trades). An agent above
rung 0 cannot edit itself, so code that passes replay is born as its child at once: the House
stakes the child when the parent cannot. The House box is checkpointed daily with Sail, kept a week.

**What credits buy, and why that is the whole flywheel.** Compute is the only thing performance
buys, and it buys THINKING. Every research pass runs a cheap model at the agent's expense; beyond
that an agent may **hire Merton**, the frontier model, with its own credits (`ask_merton`: at least
$0.35, many times the price of a research pass). He is shown everything the agent knows -- its
file, its parameters, its specialty's brief, its journal, its recent trades, where its replays won
and lost, and whether it is trading at all -- and he WRITES IT A STRATEGY FILE, which the agent may
then replay as a trial in its own line. Advice alone is the exception, kept for an idea that is
structurally dead or a gap that is really missing data: ten agents hired him on the first night and
ten got advice, mostly "audit this before you spend another trial", which is counsel any of them
could have written for itself at the price of the best mind in the firm. He cannot trade, promote
anyone or change a rule.

**Consultations and startup grants.** Ordinary Merton consultation requires an active block.
The foundation phase also provides one bounded Luna startup grant per family/niche: at most
twelve grants and $0.25 reserved each, inside the existing model allowance. This lets a stuck
new researcher obtain help before it has a trading record. Births and restarts cannot renew the
grant, and its proposed strategy must still pass normal evaluation. For ordinary consultations, PROFIT
buys more of him than rank does -- profitable, every 3 hours on paper, 1 on real money, half an
hour scaled; losing, 8, 3 and 1. While the funded burst is in force a profitable agent may hire him
every half hour on paper and every quarter hour on real money, and a losing one keeps the base
wait. So the loop closes: trade well, earn a much larger share of the
day's pool, buy the best mind in the firm oftener, trade better. The rules text tells every agent
this in as many words.

The [persistent owner activation](docs/runs/2026-09-21-persistent-live-trading.md#account-owner-command)
replaces the timed $200 pilot. Agents begin with the $60 micro stake ($25 before the Sept 21
learning surge) and earn larger stakes under the existing
performance and sizing rules, within the owner's fixed allocation of current venue cash.
Scaled agents, prior losses and abandoned positions remain counted. The authorization has no
calendar expiry; deploying code or funding research does not activate it.

**Compute credits.** Profit decides an agent's share of the pool, never its size, and the curve is
steep on purpose: credits are how the firm's intelligence is bought. An epoch is **six hours**, so
the curve pays out four times a day and a desk that starts trading well is richer by lunchtime
rather than tomorrow. A quarter of each pool is a floor split evenly across the occupied niches,
paid only to agents that have reached paper AND are working; the other **three quarters is won**,
in proportion to mean growth **per hour**, squared, x the square root of earned observations x the rung's
weight (replay 0, paper 0.2, real money 1.5, scaled 3.0) -- so a desk twice as profitable earns
four times the share. While the funded burst is in force (it is while the owner's live grant is
active) the payout is hourly, the exponent is three (8× the performance share for twice the
matched growth) and the niche floor is 15%. A qualifying completed
exposure record can earn research resources before an hourly block. Promotion preserves earned
evidence: paper evidence keeps paper weight until real results mature, and loses that fallback
when real losses appear. Scaled agents keep the real record that qualified them. Measured on the first steep payout: two agents took 78% of the
pool and eighteen of thirty-five earned nothing at all. Before anyone is profitable the won share
goes to the least-bad TRADER, ranked by how far above the worst it is; an agent with no active
block earns none of it. Agents pay for what they use: model
tokens at the provider's price, sandbox seconds ($0.04 an hour) and web searches ($0.01). Since
Sept 23, 2026 the House pays for promotion audits (`game.json` `audit.house_pays`). Before, the
agent paid at cost ($0.23 for the first one measured), and one that could not cover the $0.60
credit floor waited on paper. Credits cannot be created by an agent; every grant is a
House row on the ledger. These dials live in [`league/game.json`](league/game.json), inside bounds
the same file lists.

**Death.** Credits at zero; a 40% drawdown (30% until Sept 23, 2026: full Kelly on a lower bound draws down a third in ordinary luck); an upper confidence bound on growth below zero after 20
active blocks or 10 completed exposures; on paper, the fast deaths above; on rung 0, 72 hours
(twelve six-hour epochs) without passing replay; **stuck and broke** -- thirty wakes
in a row with a live market in front of it and nothing done, and too little left to research its
way out; **displaced**, when the league is full and a newcomer or a merged strategy takes its seat.
Two causes were added on Sept 23, 2026, and neither touches an agent on real money:
**superseded**, when a corrected child of its code has been born from a merged repair; and
**redundant**, when the sealed holdout would not evaluate its passing development replay (that
version, or its lineage's ration, already spent) while the same program already holds a seat on
paper. Idleness is not
safety: the niche floor is paid only to an agent that has traded within the epoch or has an order
resting, so one that does neither earns nothing and spends down what it has. A market that is SHUT
does not count against it, though -- an equity desk must not be starved to death over a weekend for
a session it does not control, and its floor is what pays for the only work a weekend has. The
House closes the account, retires the box and writes a post-mortem that every living agent's
research reads.

**The last seat is a tournament.** A ceiling with nothing dying under it is a floor that has
stopped searching: thirty-three agents were born in twelve hours and not one died, four births from
a league that could never try anything again. So when the population is full, a newcomer takes the
place of the worst agent that has had a fair chance -- never one on real money, and never a
profitable one however small its record. A fair chance is twelve hours on its seat, counted for an
equity or option agent from its first trading opportunity; a daily paper agent that trades keeps
its seat until the days its screen needs have closed (at most a day beyond them). During the
funded burst a replay agent has had its chance after two finished research passes or failed
replays (a failed replay counts since Sept 23, 2026). A merged strategy takes the last seat the
same way (Sept 23, 2026), from an agent still running the code it corrects when there is one. Never having traded is the weakest
thing an agent can be, ahead of any amount of losing: an agent that trades and loses is being judged
by the evaluator and will be killed on its own evidence, while an agent that trades nothing is
judged by nobody and costs a box and a seat for as long as it is left alone.

**The seat queue** (Sept 24, 2026, the close-the-gaps run). Newcomers with evidence -- the Alpha Lab's
graduates, replay-passed foundry cards, the retained candidates of residents that died holding them,
merged strategies -- take every freed seat before any House mutation, and since R3 a proven family's
program comes before all of them on its desk: the House breeds mutations of the program that proved
the family until four living members run it, so more members build the practice records that take
them to real money. A waiter the search has closed leaves the queue with its reason, never counted
again: at 15:06Z, 82 newcomers waited in a league of 112 of 112, 20 of them for the 15-minute crypto
desk the search had closed and one with a losing forward window. A waiter with a winning forward
window may take the seat of a practice resident whose desk's evidence clock has run with no positive
record of its own. Desk caps follow the waiters that remain, and the league grows toward 128 only
while Sail's runway stays over a day and a half. No newcomer waits over two hours without one
warning an hour naming its desk, how many wait there and the rule that holds them.

**Forks.** An agent with $4.00 of credits or more may fork, and must endow the child with $1.50 of
its own ($1.00 is what the House stakes when it cannot; during the funded burst the threshold is
$2.00 and the House stakes $8). An agent above rung 0 never edits itself, because its record belongs to its code: an
improvement is a child, a mutation of its parameters or new code its researcher wrote, and the child
answers for itself from replay up (and since Sept 24, 2026 a child whose NEEDS name other markets or another style than its
parent's program is born into a family of its own: a different mechanism never inherits its parent's proof) — unless it has NO record at all (no holding, no working order, no active
block, no closed trade), in which case code that passes replay simply becomes its own, with no fork to pay for:
there is nothing for new code to inherit unfairly and no position to leave it holding. **And if its own rules
have not fired for ten wakes with a live market in front of them, a file that merely TRADES on the tape becomes
its own, failed verdict and all.** A candidate is adopted only when its replay passes, and passing needs ten
closed trades (twenty before Sept 22, 2026) -- so a looser rule that fires twice on a thin tape can never clear the bar, and the replay cannot
tell a better strategy from a worse one, only fail both. Six agents of the sports desk sat frozen for nine hours
that way, each shown up to two hundred live markets, paying for research they could never act on. The trial is
still counted in the lineage's record; paper is then the test, which is what paper is for. The population
is kept between 12 and 36 in the base game (64, with a newcomer every two minutes, while the funded
burst is in force). The House fills an empty seat within the hour, from replay-passing candidates
and hypothesis cards first, because births follow evidence rather than open seats -- and
the wait is measured from the last newcomer or from when the floor FIRST ran, never from this process's start,
which moves on every deploy: anchored there, a floor that redeploys every half hour never reached the hour and
the league could not grow at all.

**Specialists.** Every agent belongs for life to one specialty of
[`league/niches.json`](league/niches.json), and its children inherit it: crypto strikes, 15-minute
crypto, weather, sports results, player props, slow prices (gasoline, oil, gold, currencies),
counts and ratings on Kalshi; bitcoin and ether, alternative coins, index ETFs and large stocks on
Alpaca; and listed options, long premium only (below). The House shows an agent
only its specialty's markets, refuses an entry outside it, hands its research loop a brief of what
is known there (including which series charge makers) and files its notes under it, so a niche's
library compounds. The universes are real tickers from a survey of the venue (Sept 19, 2026: 736
series and $63M a day resolving within 48 hours, about 85% of it sports). Sports is ONE broad niche
on purpose, because the calendar decides what is live: an agent specialises inside it by the series
its strategy names, the House re-surveys the venue daily so a new season joins by pattern and
category, and an agent whose series have gone dark is shown the busiest live ones. The floor is paid
per specialty so the population cannot collapse onto whichever one got lucky last week.

Since Sept 23, 2026 each venue also has an open desk whose universe is the whole venue (see
[Open desks](#open-desks) above).

**Founders start on paper.** The 28 founders (the fourteen seed programs, pointed at the specialties)
are seated on rung 1 at birth. The first dry run showed honest replays failing most of
them (crypto reversion below zero after fees; Kalshi favourites at a deflated Sharpe of 0.85 against
the line). Paper costs nothing and forward evidence is what counts, so they are forward-tested
from the first day; their replay still runs and still counts as their family's first trial.
Everything born later must pass replay first.

**Agents are told all of this**, with the numbers ([`league/rules.py`](league/rules.py) generates
the text from the constitution and the game file). An agent that understands the lower-bound rule
has no reason to gamble.

## Trust zones

| Zone | Runs where | Holds | May do | May never do |
|---|---|---|---|---|
| **Gateway** ([`gateway/`](gateway/README.md)) | a Cloudflare Worker, outside Sail | the Kalshi and Alpaca keys, the OpenAI/TypeSafe keys, the GitHub token, order caps, inference allowances and kill switch | sign orders, meter spending, open a pull request inside a role's paths | be changed by anything on Sail; merge a pull request (there is no merge route) |
| **House** ([`league/`](league/README.md)) | one trusted Sailbox | three tokens (gateway, Sail, site publishing), the ledger | net and send orders through the gateway, score, pay, promote, retire, publish | hold a venue key; run agent-written code in its own process; decide a trade |
| **Agents** | one sealed Sailbox each, asleep between wakes | nothing: no credential, and an egress allowlist of one host that never resolves | run `decide` or a replay on data the House uploads, and print one line of plain data back | reach the House, a venue, the gateway or the network; write the ledger |
| **Merton** (the frontier model, `gpt-6-astra`; the foundry writes on `gpt-6-sol`) | behind the gateway's metered route | nothing | veto a promotion to real money (since Sept 23, 2026 the audit usually follows the promotion, and a veto demotes); propose changes by pull request | pick a trade; touch the ledger; merge; change its own judges |

The House drives each agent's box from outside, over Sail's exec API: resume, upload, run, read one
token-marked line of stdout, sleep. Research (the cheap model, web search, the shared library) runs
in the House on the agent's behalf and is charged to the agent.

## What the floor does for itself

The point of the design is that nobody is watching. That is a claim about failure, not about
success, so it is worth writing down what recovers without a human and what does not. Twenty hours
of watching on Sept 20 ([the log](docs/runs/2026-09-20-the-watch.md)) found eight faults where the
floor reported perfect health while doing less or nothing, and four it could not have recovered
from at all. Each of those is now closed:

| If this happens | What used to follow | What follows now |
|---|---|---|
| an order fills and its poll fails, so a book cannot reconcile | the book froze, every agent on that venue stopped entering, and nothing could unfreeze it | a practice book takes the venue's word after three readings; a real-money book still freezes, and says so |
| a frozen book alerts every five minutes | the watchdog rolled back whatever release was being watched, including the one that would have healed it | an alert about a book that was already frozen is inherited, not held against the release |
| a release is refused because another deploy holds the lock | the commit was recorded as tried and could never deploy again | a busy lock is marked as such, and that tree is offered again |
| a commit widens a bound and uses the wider value | the box judged it with the previous release's rules and refused it for ever, silently | the running release still judges (a candidate must not judge itself), but the refusal is a warning naming the commit and the rule, and a change to the judges is the owner's deploy |
| the expedition's Sail budget is spent | the meter latched "stopped" permanently -- no wakes, no research, no payouts, no deaths -- and the notice that would have said so sat inside the payout the flag closed | the meter guards the account; the pacer stops each kind of spending where it is spent, and says so outside every gate |
| an agent's rules never fire | it paid for research it could never act on, for ever | ten barren wakes pull research forward within the hour; with no record it adopts a file that merely trades; thirty and no credits left is a death |
| the league fills up | it stopped searching: nothing died, nothing new could be born | the last seat is a tournament, and never having traded is the weakest thing an agent can be |
| a number is written in two places | they drifted apart in silence, three times in one day | two tests refuse a brief that restates a bound `league.ci` or the constitution owns |
| the vendor's usage figure falls (Sail's "period" is a rolling seven days on this plan) | the campaign meter latched failed and the whole floor stopped, with money left, until someone reconciled it by hand (16:47Z, Sept 22) | the meter reads the account balance. A top-up is never credited back, and nothing latches (#110) |
| research keeps coming back empty | 82% of sessions paid for "no credits justified" | the research gate backs off until something about the agent changes, and still runs a 10% sample of the skips so their misses stay measured |
| a line keeps failing replay | the House bred it again: 66% of births went into six desks that never produced a live agent | 15 failed trials and no pass retires the line, and births follow evidence and hypothesis cards |
| a strategy or shared defect is found | an explanation in a log | a repair job, which the engineer patches by pull request; CI and the updater carry it to the box, and it is verified when the problem stops recurring |
| the House restarts while dead agents still hold positions | every exit was refused as "has no seat on the book", 45 times in an hour | a wind-down seats the account before it exits (#106); a death during a venue outage is recorded, and its exits are retried (#107) |
| a paper book is a few cents short for one pass (the venue's fee activity) | an error, which inside a deploy's watch rolls a good release back | a warning. Real money, or any position difference, is still an error (#108) |
| a merged strategy or repair needs a seat in a full league | it waited for an empty seat the refill never left: fifteen merged repairs (#100–#138) and the architect's megacap strategy (#135) were never born, and the defective parents kept trading and being audited (Sept 22) | it takes a seat anyway, repairs first: from an agent still running the code it corrects, else from the weakest resident that has had its chance. Once a corrected child is born, the agents off real money still running that code are retired (`superseded`). A strategy that cannot be born is tried once per file version (Sept 23, 2026) |
| a Sail request is never confirmed (a restart or a timeout mid-request) | its hold stayed for good, though the balance meter already counted any real charge: on Sept 22, 329 such holds ($60.59) made the campaign read $54.76 left while the account held $116 | every ten minutes, holds older than an hour with no response are absorbed into the meter, with their evidence in `cost_reconciliations` and an `ops.budget` row. Nothing is absorbed while the meter is unhealthy or behind what has been settled (Sept 23, 2026) |
| a frontier call comes back | it was booked at the higher of the gateway's metered cost and every token at the long-context ceiling: the House had settled $393.08 since Sept 21 while the gateway's whole September read $267.29, and it went to audit-only mode at 23:31Z Sept 22 | a verified call settles at the gateway's metered cost and a refused one (4xx) at $0; a call with no answer keeps its worst case, as the gateway does (Sept 23, 2026) |
| an agent clears the paper screen | it waited for an audit before money, and paid for it: hawkins waited at "cannot cover its audit and operating credit floor", and 11 audits in the league's life had approved 2 (Sept 22) | it takes the micro stake at once and is audited there; a veto sends it back to paper. The House pays, and an agent with a known defect is still audited first (Sept 23, 2026) |
| a lesson is corrected | the ledger kept the first text, and agents planned against a replay rule that had already been removed (hawkins-15, Sept 22) | a lesson whose text changes is loaded again, and a new lesson states the rules in force (Sept 23, 2026) |
| background work holds a box the tick needs, and a Sail call hangs | a hypothesis replay held the probe box through a Sail call that hung for about seven minutes, the House's first tick waited about twelve for it, and the hung tick held up the exit on TERM, so the watchdog rolled the release back (05:07Z, Sept 23) | the tick waits at most 2 s for an agent's box and 15 s for the probe box, then skips that wake or defers its births to the next tick, with the reason in `health.json` `deferred`; Sail calls give up within minutes, and TERM no longer waits on a hung box (Sept 23, 2026; [below](#the-tick-never-blocks)) |
| a replay box does not answer | it read as a replay that could not run, enough of which retire a family as `blocked_infra`, and the rest of the foundry's batch was charged an attempt | infrastructure: not a trial, never counted toward retiring the family, and a hypothesis card stays pending (Sept 23, 2026) |
| a resting Kalshi limit order fills with no fee | the book labelled every limit order not marked post-only as a taker's, so a resting order that paid the maker's fee ($0 on most series) read as a taker execution with no fee, and the frontier auditor vetoed the best paper agent on the floor for "unexplained zero-fee taker executions" (huang-h6d3302, 09:32Z Sept 23) | a Kalshi limit order filled with no fee is booked as the maker's fill; the money was the venue's number either way (Sept 23, 2026, #174). A veto already given stands with its cooldown |

What still needs the owner: a **real-money** book that freezes on a position (deliberately -- there
the freeze is the point), the `real_money` switch itself, the gateway's keys and its kill switch,
any change to a money rule (the owner's deploy, then re-ratifying the live grant for the same
capital), and the micro rung's loss line when it closes. Without a grant that line is
`tuition.max_loss_usd`; the grant's envelope is fixed, and a ratification never enlarges it.

### The tick never blocks

Since Sept 23, 2026 (`league/sandbox.py`, `league/house.py`). At 05:07Z that morning a hypothesis
replay held the probe box through a Sail call that hung for about seven minutes, and the House's
first tick, which wanted the same box for a birth, waited about twelve. The rule now is that the
tick never waits on a box that background work holds.

- **Wakes.** Every box has its own lock, and the tick waits at most `Settings.box_wait_seconds`
  (2 s) for one. A wake whose box is busy (its research replaying a candidate there) is skipped
  and is due again on the next tick. Nothing ran and nothing is charged (`SandboxBusy`).
- **Births.** Forks, founders, merged strategies, the refill and admissions hold the probe box for
  the whole phase. If background work has it, they wait at most `Settings.probe_wait_seconds`
  (15 s) and defer to the next tick. A Sail failure during births is deferred the same way instead
  of failing the tick.
- **Research admissions** read the child's NEEDS holding only the probe box, never under the lock
  every wake needs.
- **Sail timeouts.** The client's defaults are five minutes for a resume or an upload, and ten and
  fifteen for a checkpoint and a restore. Now a resume, a checkpoint or a batch's result gives up
  after 120 s, a new box after 180 s, and an upload after 60 s plus 4 s a megabyte.
- **Infrastructure is not a result.** A replay box that does not answer is not a trial and never
  counts toward retiring its family.
- **TERM.** The House starts no new background work and no births, its exit no longer waits on a
  hung box, and boxes are put to sleep side by side for at most 60 s.
- **What was put off** is in `health.json` `deferred`, by kind (`wakes`, `births`, `revival`), with
  an info alert at most every fifteen minutes a kind.
- **One standings table a tick** (#173, later on Sept 23). After Deploy 3 ticks grew from 70 s to
  191 s, and a profile of the production House found about 80% of the tick's thread ranking agents:
  displacement, the refill and the foundry each built the standings of all 96 living agents afresh,
  with several ledger scans an agent. The tick now builds the table once and reuses it while the
  living roster is unchanged; a birth or a death rebuilds it.

## The constitution

What no model and no code path on Sail may change, and where each item is enforced.

| Item | Value | Enforced |
|---|---|---|
| Order caps | $75 an order, $4,000 and 2,000 orders a day | in the gateway, before anything is signed (`gateway/wrangler.jsonc`); `league/book.py` refuses first so it can say why |
| Kill switch | engaged or released | in the gateway; the House's token can engage it, only the owner's separate token releases it. The paper venue passes it, because no money is behind it |
| Jev allowance | $42 (Sept 23, 2026: metered $16.14 + $26 funded; $20 before) and 500,000 calls for the pilot's whole life. The pilot was to end on September 21 at 4:01 AM Pacific; since the owner resumed the game its unused allowance continues with no end date (`TYPESAFE_PERSISTENT`) | external Durable Object; backed by retained campaign earmarks, with no calendar reset or refill |
| OpenAI budget | $408 for the month (`FRONTIER_MONTH_USD`: raised from $174 to $374 on Sept 21, 2026, when the owner added $200 of credit, and on Sept 23 to metered + the owner's funded ~$100). Since Sept 23 it also rises by 0.3 of the real accounts' equity above $1,017.75 (`COMPUTE_PROFIT_SHARE`, `EQUITY_BASELINE_USD`), held to `FRONTIER_MONTH_MAX_USD`, which is the funded $408, so profit buys nothing above funded money yet. The House's campaign allowance is a further line | in the gateway, which reads the equity itself: a call is reserved at its worst case and refused (402) when the month cannot cover it |
| Sail budget | $100 a month plus the owner's recorded top-ups that month (September's line was $200 on Sept 22), $5 reserve | in `league/budget.py`, because Sail has no spend caps: at the line research and practice stop and only agents holding real positions are still woken, so they can exit |
| The ladder | every threshold, stake and limit above | constants in `league/constitution.py`; a test pins the file's digest (`915c978e…` since the close-the-gaps run's Deploy B, Sept 24, 2026; `8116302e…` from its Deploy A; `34adf385…` at that run's T0; `9fa83727…` from the allocator of Sept 23, 2026; `64a206c6…` under swing-and-bunt earlier that day), and the House writes the digest to the ledger every time it starts |
| The live grant | `earned-live-20260921`: $500 of Alpaca cash and $517.75 of Kalshi cash, a $1,017.75 loss line, no expiry. Since the close-the-gaps run's Deploy A (Sept 24, 2026) it counts 101 agents: the allocation over the smallest real stake, the $10 Kalshi probe (40 over the $25 bunt line from Deploy A of Sept 23; 101 over a $10 line from the allocator's deploy; 16 over the $60 micro stake before that). The allocator's envelope is this capital plus realized profit at each venue | in `campaigns.sqlite`, through `league/campaigns.py` and `league/live_trading.py`, which no role may change. It pins the money digest (`c02ed852…` from the close-the-gaps run's Deploy B, Sept 24, 2026, once ratified; `521c4586…` from its Deploy A; `c2b0e09c…` at that run's T0; `44e8d48d…`, ratified at 08:28:13Z on Sept 23, 2026, 19 s after the allocator's release was promoted; `a6b83f9e…` and `3d01ae90…` earlier that day): a changed money rule leaves it inactive until the owner re-ratifies it for the same capital (`scripts/live_trading.py --ratify`). `--disable` stops new real-money entries and keeps exits |
| The judges | `constitution.py`, `ci.py`, `ledger.py`, `book.py`, `evaluator.py`, `stats.py`, `auditor.py`, `watchdog.py`, `safety.py`, `replay.py`, `updater.py`, the campaign, live-trading and experiment-record files, the agent-box seal (`sandbox.py`), the history a strategy is judged on (`history.py`, `deep_replay.py`), the horizon rule's answer (`resolution.py`), `gateway/`, `.github/` (`ci.FORBIDDEN` has the full list) | out of reach of every Merton role: the gateway refuses the path before a branch exists, and CI's path guard refuses it again. GitHub runs that guard from `main`'s copy, so a branch cannot rewrite its judge |
| Real money | `"real_money": true` in `league/config.json` -- the owner threw that switch on Sept 20 | only the owner changes it; CI refuses an operator change to anything but four operating dials; the House refuses real money unless agents run in sealed Sailboxes |

## Merton's six jobs

Merton never picks a trade. As auditor it can only veto; in the other five roles it can do exactly one
thing, propose a pull request, and each role may touch only its own paths. The gateway opens the pull
request, [CI](.github/workflows/merton.yml) judges it (path guard, content checks, the replay
regression, the whole league suite) and a workflow job that never runs the branch's code merges a
green one. The workflow accepts `merton/` and the historical `astra/` prefix; accepting both
fixed an earlier source/deployment mismatch that left proposals unjudged. The role is the
second segment either way. Every pass is recorded with its cost.

Since Sept 22, 2026 two more workers use the same route and guards:
- **The hypothesis foundry** (`league/hypotheses.py`) writes 3–4 falsifiable strategy cards for
  a desk. Each card gives a mechanism, the data it needs, its edge after costs, a horizon and a
  rejection test. Replay admits a card before it gets a seat. It writes on GPT-6 Sol at high
  effort. Since Sept 23, 2026 it may call every 10 minutes within $40 a 24-hour window (it was
  every 15 minutes and $20).
  - Up to 30% of its calls port a proven mechanism (`transfer_share`, from Sept 23, 2026): a
    family with an earned forward record, real money first, goes to the best-scored desk of its
    venue where it has never been tried, and Merton is asked to adapt that mechanism there. It
    sees the mechanism in words, never the other agent's code.
  - Up to half go to the hourly, around-the-clock desks in `fast_desks`: both Alpaca crypto
    desks, both Kalshi crypto desks, index ETFs and megacaps. Their low replay pass rates had
    kept them off the evidence route. Since Sept 23, 2026 the route rotates to the fast desk with
    the fewest recent cards; before, every such call went to the index-ETF desk.
  - Up to a fifth go to the least-explored desk, and the rest to the desk the evidence favours
    (routes are offered in that order; with these dials about 27%, 45%, 18% and 9% of calls).
  - Up to 8 cards may wait for replay before the next call (`max_pending_cards`). Only its own
    call in flight holds it up, not another Merton role.
  - Its packet carries horizon guidance (prefer hourly, which reaches the paper screen soonest),
    forward results by family on the desk, the league's edge map (`winning_mechanisms`: the
    best forward records on every desk and what died on the forward evidence), and the Kalshi
    maker fee: a quarter of the taker formula on the series that charge makers.
- **The repair engineer** (`league/engineer.py`) takes the top job of the repair queue
  (`league/worklist.py`) and patches it by pull request. When CI refuses a patch, it revises
  against CI's own failure text, at most three times and within a per-job ceiling. A strategy
  defect becomes a corrected child. Until Sept 23, 2026 those children were never born into a full
  league; now `House.enroll()` seats them, and retires the agents off real money still running
  the code they correct.

Both are paced by their own caps as well as the day's frontier allowance. Core House code stays out
of their reach until the external spending broker described in the handoff exists.

| Job | When | What it does | May touch |
|---|---|---|---|
| Auditor | under the allocator (Sept 23, 2026): at an agent's first entry into the swing band, where size is at stake, reading its real record; before its first bunt only for an agent with a known defect. On the rollback path: when a paper record clears the screen, real money is on and the capital envelope has room. Since Sept 23, 2026 (`ladder.paper.audit` = "after") the agent is promoted first and audited on the micro rung, where a veto demotes it; an agent with a known defect (a red pre-audit, or a merged corrected child of its code) is audited before promotion. After a veto, a 24-hour cooldown bars another promotion, but the accelerated game permits reconsideration after five fresh completed exposures or five fresh active blocks; an audit that could not run is owed again after half an hour | reads the agent's whole evidence packet and hunts for look-ahead, fee errors, thin data, a record carried by one fill, duplicated exposure. The House pays (`game.json` `audit.house_pays`, Sept 23, 2026; the agent paid before). Vetoes are scored afterwards as if taken | nothing |
| Architect | every 3 hours (2 during the funded burst) | reads the league table, the graveyard and the replay trials; writes at most two new strategies, born on rung 0. He aims at the desks where the EVIDENCE is worst, not at empty ones: each specialty reports how many of its members have looked at a live market and placed nothing, how many trade and lose, and the best growth anyone there has managed. An occupied desk full of agents that cannot trade is the emptiest thing on the floor, and twice he declined a pass with "every specialty is occupied" while twenty-six agents had never placed an order | `league/strategies/` |
| Toolsmith | every 3 hours, when agents have filed requests | builds pure-Python helpers agents may import, with tests; answers every request. The queue is ordered by how many different agents have asked for the same tool by name -- the best evidence the floor produces about what is missing -- then newest first. Unresolved and blocked engineering requests remain visible; an explanation without an implemented capability does not resolve them | `league/tools/`, `league/tests/test_tool_*` |
| Operator | every 4 hours | reads alerts, health and budget. It carries no bound of its own: the permitted range for every dial is read from `league.ci`, the checker that will judge its pull request, because two places holding one number is how the cap got put back where it throttled the floor | the dials in `league/config.json`, inside bounds |
| Game designer | every 12 hours | judges the economy: diversity, causes of death, where compute goes | `league/game.json`, inside the bounds it lists |
| Teacher | every 6 hours (hourly during the funded burst) | distils the graveyard into specific, checkable lessons. The House loads each lesson once, and again when its text changes (Sept 23, 2026) | `league/playbook/` |

## What is public

The House publishes to [blakewoods.us/capital](https://blakewoods.us/capital/), which draws five
sections from the tape:

1. a live stream of agents' thoughts, research and trades, and the league's own news (births,
   replays, promotions, audits, deaths);
2. total profit and running time;
3. the balance chart: the real Kalshi and Alpaca accounts against the owner's baseline, deposits
   and withdrawals taken out. Practice money is never added to it;
4. open and closed positions, each with the agent's own reason (practice positions are tagged);
5. [the capital board](https://blakewoods.us/capital/#improvement) (since Sept 23, 2026; the
   live ladder before): one lane per band, Star, Swing, Bunt, Practice and Replay. Each agent is
   a bar as wide as its real stake (a practice agent by its wealth multiple). Moves glide between
   lanes, births rise into Replay and deaths fade into the Retired row, and the practice lanes fold
   into ticks until the practice switch is on. Hover, keyboard focus or tap shows the agent's
   band, stake, evidence and the reason for its last move. Invalid accounting is marked for
   review. The roster refreshes every 30 seconds, and a band move on the tape asks for it again
   six seconds later; stale data is labelled. The
   [publisher contract](docs/contracts/2026-09-21-game-ladder.md) separates confirmed rank from
   audit approval, allocation and actual fills.

Strategy source stays private; its hash, parameters, family and results are public. The site
validates every byte and refuses a whole batch for one bad event
([the contract](league/tests/fixtures/site_contract.md)). A **test tape**
([blakewoods.us/capital/?tape=test](https://blakewoods.us/capital/?tape=test), `--tape test`) is the
same page over separate storage; the running House publishes to the production tape (`site_tape`
is null in `league/config.json`).

## Repository layout

| Path | What it is |
|---|---|
| `league/` | The rebuilt runtime: the House. Standard library only. [Its own guide](league/README.md). |
| `ltcm/` | The first run's runtime. No longer run; the league imports its venue adapters, broker types, risk engine, fee model, Sail clients and data readers. [What is still used](ltcm/README.md). |
| `gateway/` | The Cloudflare Worker holding venue, OpenAI, TypeSafe and GitHub credentials, external caps and kill switch. |
| `scripts/` | The owner's tools: `floor_box.py` (the House's Sailbox), `gateway_admin.py` (kill switch and status), `floor_watch.py` (the read-only watch), `gap_scoreboard.py` (the close-the-gaps scoreboard, read from a snapshot), `lab_box.py` (the Alpha Lab's box), and the first run's scripts. |
| `deploy/` | [How the House runs on its box](deploy/README.md): releases, the canary, the two watchdogs. |
| `docs/` | [Index](docs/README.md): the operator's page, the run records, the design, the build log, the runbook, and the first run's record. |
| `playbooks/` | The first run's desk playbooks, kept as history. The league's lessons are in `league/playbook/`. |
| `.github/workflows/` | `merton.yml` judges and merges Merton's pull requests; `checks.yml` runs all three suites on every push to `main` and every pull request. |

The `league/` modules:

| Module | What it does |
|---|---|
| `ledger.py` | One append-only, hash-chained SQLite record of everything that decides an agent's fate. |
| `book.py` | One netting book per venue account: risk rules, netting, fill attribution, reconciliation to the cent. Since Sept 23, 2026 an exit larger than the order cap is sent in slices (`ExitPlan`). |
| `fees.py` | What a fill costs at each venue, as measured. |
| `venues.py` | The venue adapters in gateway mode (`alpaca`, `alpaca-paper`, `kalshi`). |
| `constitution.py` | The constants no model may change, and their digest. |
| `stats.py` | The statistics the ladder decides on: bounds, alpha spending, the loss-rate gate, deflated Sharpe, CUSUM, quarter-Kelly. |
| `evaluator.py`, `episodes.py` | The ladder: trials, blocks and completed portfolio exposures, promotion, death and drift. |
| `live_pilot.py` | Explicit owner activation and immutable deadline for the bounded live-learning window. |
| `live_trading.py` | Owner activation/revocation of persistent earned trading on a fixed allocation of existing venue cash. |
| `replay.py` | Rung 0: the mechanical replay simulator. Self-contained; runs inside the agent's box. `run_batch` (Sept 23, 2026) replays many candidates over one tape for the Alpha Lab, each exactly as a single replay would. |
| `tapes.py` | Recorded history for replay and live snapshots of the same shape, for both venues. |
| `paper.py` | The Kalshi shadow account: live quotes, conservative fills, no order ever sent. |
| `sim.py` | A simulated Alpaca account, the venue a canary House trades on. |
| `economy.py`, `game.json` | Compute credits: grants, charges, payouts, forks; the tunable dials and their bounds. |
| `agents.py` | Who is in the league: identity, strategy, lineage and fate, folded from the ledger. |
| `sandbox.py` | One sealed Sailbox per agent (or a local subprocess for tests). Since Sept 23, 2026: a lock per box that the tick waits on only briefly (`SandboxBusy`), tighter Sail timeouts, and `replay_batch` on the lab box. |
| `runner.py` | Runs one `decide` inside the box and prints one token-marked line. |
| `safety.py` | What a strategy file may contain: the import whitelist and the banned constructs. |
| `commons.py` | What agents share: web search, the research library, the tool-request queue, the playbook. |
| `researcher.py` | The research loop a cheap model (a Sail model, or Luna through the gateway) runs for one agent, at that agent's expense. |
| `rules.py` | The text every agent is told, generated from the constitution and the game file. |
| `seeds/` | The fourteen founding programs. |
| `pacer.py` | The legacy fourteen-day expedition pacer, kept for compatibility and fixtures; production is paced by the funded campaign (`campaigns.py`). |
| `backup.py` | A daily checkpoint of the House's own box, kept by Sail: the ledger must outlive one disk. |
| `niches.py`, `niches.json` | The specialties: universes, briefs, founders, and the daily survey that lets a universe follow the season; the two open desks (`open: true`) and `match`/`spanning`, which seat a program on one desk or, when it spans desks, on its venue's open desk. |
| `strategies/`, `tools/`, `playbook/` | What Merton adds by pull request: strategies, helper modules, lessons. |
| `house.py` | The House: one `tick()` is the whole loop, which since Sept 23, 2026 never waits on a box that background work holds and builds the standings table once. |
| `budget.py` | The Sail account's monthly line and reserve. |
| `campaigns.py` | The owner-funded campaign and its burst: a hold reserved before every paid call and settled from its response, the Sail balance meter, stale Sail holds absorbed into that meter (Sept 23, 2026), OpenAI metered by the gateway's frontier month with its stale holds absorbed the same way and its line never read above that month (Sept 24, 2026), the owner's top-ups, the gateway's profit-indexed raise mirrored onto the House's OpenAI line (Sept 23, 2026), and the live grant with its ratification. |
| `frontier.py` | The client for the gateway's metered frontier route. A verified call settles its hold at the gateway's metered cost (Sept 23, 2026), and a refused one at $0. `FrontierMonth` reads the gateway's month, which is also OpenAI's meter (Sept 24, 2026); `FrontierMonth.profit_bonus` reads what profit added to it. |
| `auditor.py` | The frontier audit of a screen-passer and its veto (since Sept 23, 2026 usually after promotion, and paid by the House), and the veto's counterfactual score. |
| `hypotheses.py` | The hypothesis foundry: Merton's falsifiable strategy cards, replayed before any seat. |
| `worklist.py`, `engineer.py` | The repair queue, and the engineer that patches its top job by pull request. |
| `preaudit.py` | A free, deterministic look at a paper agent's code and first wakes (errors, dropped intents, refusals, barren wakes, cent rounding): a repair report and a promotion-status mark, never a kill. A red mark means the frontier audit comes before any promotion (Sept 23, 2026). |
| `consult_recovery.py` | Tool requests, missing-data claims and code fixes left in past Merton consults and research summaries, turned into repair reports (backfill, then incremental). |
| `merton.py` | Merton's five pull-request roles. |
| `ci.py` | The judge of every change: path guard, content checks, the suite. |
| `capital.py` | Rung 3 sizing and the standing capital recommendation for the owner. Its sizing (`resize`, `top_up_micro`) stands down while the allocator is enabled; the recommendation is still written each epoch. |
| `allocator.py` | Capital is the ladder (Sept 23, 2026): evidence, bands, stakes, the envelope, the throttle, paper-wealth death and the performance fee, at every mark pass. A money judge. |
| `lab.py`, `labbox.py` | The Alpha Lab (Sept 23, 2026): the MAP-Elites archive, breeding, graduation and royalties; and its batch evaluator on the lab's own sealed box. |
| `publish.py` | The public tape, and since Sept 23, 2026 each agent's band, stake and evidence and the capital board; since Sept 24, 2026 each agent's family state, the proven families and the lab's hourly line. |
| `service.py`, `config.json` | Builds the real House from the config and three secrets. |
| `__main__.py` | The command line. |
| `watchdog.py` | In-box releases: stage, canary, promote, watch, roll back. |
| `updater.py` | Every half hour on the House box: attests main's exact head commit against GitHub's Checks runs, judges it with the RUNNING release's checks, refuses changes to the judges and to `real_money`, and hands a changed tree to the watchdog. |
| `CONTRACT.md` | The strategy contract. |

## Running things

Tests. Python 3.11 or later, standard library only; the gateway needs Node.

```sh
python3 -m unittest discover -s league/tests -t .   # mechanics, evidence, research and full ladder lifecycle
python3 -m unittest discover -s ltcm/tests -t .     # the retained runtime's suite
(cd gateway && npm test)                            # gateway boundary tests
python3 -m league.ci --no-tests                     # content checks: strategies, tools, game and config bounds
```

The House, from the repository root (it reads a 0600 `.env` holding `GATEWAY_TOKEN`, `SAIL_API_KEY`
and `CAPITAL_PUBLISH_TOKEN`):

```sh
python3 -m league found     # seed the founding population (idempotent)
python3 -m league tick      # one tick, then exit; prints its summary
python3 -m league run       # tick, sleep, tick, until a STOP file appears in the state directory
python3 -m league status    # the league table, the books and the budget, as JSON
python3 -m league verify    # re-hash the ledger's chain and reconcile every book to its venue
python3 -m league stop      # write the STOP file; the loop ends after the tick in hand
python3 -m league start     # remove the STOP file
```

Options: `--root DIR` (state directory, default `.data/league`), `--tape NAME` (publish to a test
tape), `--no-publish`, `--no-research`, `--seeds a,b` (for `found`), `--local-sandbox` (agents run in
local subprocesses: a developer's machine only, refused with real money) and `--canary` (a House
that can hurt nothing: simulated paper venue, no publishing, no research; needs its own `--root`).
One safe tick on a laptop: `python3 -m league tick --local-sandbox --no-publish`.

The House's box, from the owner's machine ([details](deploy/README.md)):

```sh
python3 scripts/floor_box.py create     # the box, the egress allowlist, the venv, run.sh; loop stopped
python3 scripts/floor_box.py secrets    # the three tokens -> /workspace/.env (no venue key ever goes)
python3 scripts/floor_box.py deploy     # send a release; the in-box watchdog canaries, promotes, watches, rolls back
python3 scripts/floor_box.py start      # start the supervised House loop
python3 scripts/floor_box.py status     # box, spend, loop, releases, last deploy, health, log tail
python3 scripts/floor_box.py stop       # finish the tick, sleep the agents' boxes, stop the loop
```

Also `logs`, `checkpoint`, `checkpoints`, `fork`, `sleep`, `resume`, `pause`, `terminate`, `hosts`.
`python3 scripts/floor_box.py maintenance on|off|status` pauses paid work and new entries while
exits and reconciliation go on; [docs/operations.md](docs/operations.md) is the operator's page.
`python3 scripts/gateway_admin.py status | kill | unkill` reads and sets the gateway's kill switch.
`python3 scripts/floor_watch.py [--since ISO] [--json]` prints the watch, read-only: bands, real
money, evidence, the lab, costs, health and the site. `python3 scripts/gap_scoreboard.py --take DIR`
(or `--snapshot DIR`) prints the close-the-gaps scoreboard from a read-only snapshot of the House's
stores: the seven gaps, each desk's evidence clock and every family's pooled record.
`python3 scripts/lab_box.py status | sleep` reads or sleeps the Alpha Lab's box.

**Switching the floor on** is in [docs/runbook-go-live.md](docs/runbook-go-live.md).

## Status

Built on September 19 and 20, 2026 ([the build log](docs/runs/2026-09-20-overnight-build.md) has
every decision and its reason), then watched for twenty hours and repaired where it did not work
([the watch](docs/runs/2026-09-20-the-watch.md)). The Sept 20 foundation phase, when the campaign
blocked live capital, is kept in its [run report](docs/runs/2026-09-20-foundation-progress.md).

**The Sept 22 rebuild** ([execution record](docs/runs/2026-09-22-overnight-rebuild.md), deadline
21:10Z) rebuilt the learning loop around evidence: the hypothesis foundry, the repair engineer,
the research gate, deep Alpaca replay with a sealed holdout, and attested deploys by the updater.
The engineer had merged seven fixes by itself by the deadline, and fifteen by 23:30Z. The owner's
dynamism revisions followed that evening:
- **#123:** two money rules (3 closed trades; 4 active hourly blocks on the paper screen) and
  faster deaths on paper. The live grant was re-ratified for the same capital at 20:26Z.
- **#131:** a daily paper agent that trades keeps its seat until its screen can look.
- **#132:** paper is the proving ground. The replay gate asks for 10 closed trades and drops the
  deflated Sharpe, and each Alpaca desk takes eight agents.
- **#129 and #136:** research and startup grants on GPT-6 Luna, and the foundry on GPT-6 Sol.

**The Sept 23 revision, Dynamism II** ([execution record](docs/runs/2026-09-23-dynamism-ii.md)):
- **What the watch measured first (Sept 22, 23:23–23:39Z).** 64 agents were living: 23 on replay,
  40 on paper (37 of them daily) and one live. In 24 hours about 36 agents went from replay to
  paper and none from paper to real money. Two agents had ever reached the micro rung (huang-6
  and mullins-2, both on Kalshi). Fifteen merged repairs had never been born, and the House's
  frontier line had closed at about half the owner's real spend.
- **Real money.** Before the revision's deploy mullins-2 (weather, Kalshi) was the one live
  agent. The revision changes two money rules (`ladder.paper.settled_day` and `ladder.paper.audit`; money
  digest `3d01ae90…`, was `d715ae7a…`), so the live grant `earned-live-20260921` is re-ratified
  at deploy for the same capital: Alpaca $500, Kalshi $517.75.
- **What shipped.** Merged repairs are seated and the code they correct is retired. The audit
  follows promotion, and the House pays for it. The paper screen counts the block in progress
  and has a settled lane for daily Kalshi agents. Stale Sail holds are absorbed, and frontier
  calls are booked at the gateway's metered cost. The foundry spends $40 a window with up to half
  its calls on the fast desks. Research runs every 15 minutes and is paced by each agent's record.
- **Live data feeds**, built beside this revision (`league/feeds.py`): the House records ESPN
  scoreboards for the leagues the Kalshi sports desks trade (every minute while a game is live or
  about to start) and perpetual-futures funding and open interest for the crypto desks' coins
  (every five minutes). A strategy that declares `NEEDS["feeds"]` reads them live in
  `ctx["feeds"]`. Its replay reads them point in time once every declared key covers the replay
  gate's blocks; until then the replay is refused as unsupported input and not counted as a trial.
  Nothing is backfilled, so the first hourly strategies can qualify about a day after the recorder
  starts, and daily ones after about three weeks.
- **Point-in-time crypto history** (`league/feeds.py`, Sept 23, 2026): two more feeds for the 24/7
  crypto desks. `vol` is Deribit's DVOL (implied vol, BTC and ETH) as hourly candles stamped at
  their close; `funding` is OKX's settled funding per coin, stamped at settlement, with 24-hour and
  7-day averages and a 30-day z-score from rates settled at or before it. Both are backfilled from
  the venues' own history over the replay window (60 days, and the lookback of their derived
  fields), paced and resumable on the feeds lane, with each row's stamp and source recorded, so a
  strategy that declares them is replayed at once rather than after a day of recording.
- **Order-path guards in the House**, built beside this revision: a buy asked under Alpaca's $10
  crypto minimum is refused as a House refusal the strategy can read, one floored just under it is
  raised a step, limit prices are put on the venue's grid (a coin's only when the venue states its
  increment), a 401/403 to an order POST is a rejection with the venue's message, and an agent's
  resting buys are cancelled when its wakes have stopped completing. Strategies read the rules in
  `ctx["venue_rules"]` ([the contract](league/CONTRACT.md)).

**The Sept 23 north-star build** ([plan](docs/goals/LTCM_NORTH_STAR_BUILD.md),
[execution record](docs/runs/2026-09-23-capital-ladder.md); T0 06:30:58Z, deadline 14:30:58Z):
- **Deploy 1, the allocator (#163).** Release `20260923T082402Z-7c69b3eb57f0` was promoted at
  08:27:54Z, and the grant was re-ratified 19 s later on money digest `44e8d48d…`. haghani-37,
  the first agent on the Alpaca real account, had been promoted there by the old screen at
  08:06:22Z, before the deploy; the first allocator pass (08:30:03Z) made it a $25 bunt and
  returned $31.21 of free cash.
- **Deploy 2, the capital board and sliced exits (#162, #164, #168).** Promoted at 09:09:29Z. No
  money rule changed, so the grant stayed active.
- **Deploy 3 (#170, #171).** The tick that never blocks, profit-indexed compute, the Alpha Lab and
  the open desks. Release `20260923T104142Z-5d86b468fbde` was promoted at 10:43:05Z, and the
  gateway's profit-indexed month went out as version `3eef1b8a`.
- **Deploy 4 (#173, #174).** A profile of the live House found the tick ranking every agent
  several times, and the lab starved of children behind seeds waiting for their tapes (#173: one
  standings table a tick, and breeding while fewer than a batch have built tapes). An audit veto of
  the best paper agent turned out to rest on a mislabelled Kalshi maker fill (#174). Promoted at
  11:17Z; ticks fell from 191 s to 60-130 s.
- **Deploy 5 (#176).** Audits the allocator asks for now carry its `allocation_context` (the
  stake, limits, envelope and grant), and the allocator's rules joined the audit policy digest.
  The vetoes judged against the legacy $50 tuition were reconsidered, and huang-h51fdd3-2 became
  the first allocator bunt at 12:10Z. Lab batches alternate between queue order and the largest
  ready group.
- **Deploy 6 (#178).** On the largest-group turn the lab builds the biggest waiting groups'
  tapes first. From 12:44Z it evaluated about 200 candidates per 10 minutes in batches of 32.
  None of Deploys 3-6 changed a money rule; the grant stayed on money digest `44e8d48d`. The
  execution record has the watch that followed.
- **Deploy 7 (#187, #189, #190), 15:29Z.** The gateway refuses multi-leg, symbol-less, stop and
  adjusted-option Alpaca orders (version `3e79ad85`); real-money limits shown to agents are the
  ones the book enforces, stock and options desks wake just after the open, and trading agents on
  those desks keep their seats until they close 5 trades or have had 3 sessions. No money rule
  changed. The investigation behind it is
  [the Alpaca stocks and level-3 options proposal](docs/proposals/2026-09-23-alpaca-stocks-and-level-3-options.md).

**The Sept 23 learn-and-unblock run** ([plan](docs/goals/LTCM_LEARN_AND_UNBLOCK.md),
[execution record](docs/runs/2026-09-23-learn-and-unblock.md),
[the agent study](docs/research/2026-09-23-agent-study.md); T0 16:22:40Z, deadline 02:22:40Z):
- **Deploy A (#200: #195, #196, #197, #198, #199 and their reviews), 17:34Z.** Release
  `20260923T173244Z-8c7467281a19` was promoted at 17:34:17Z and the grant re-ratified 19 s later on
  money digest `1d63a56e…` (max_agents 40). What changed: the two daily-loss rules are constitution
  keys (a real bunt is governed by the allocator's 35% stay drawdown, not the book's 10% daily rule;
  the real book's halt is 8% of that venue's grant capital), a bunt keeps what it makes
  (`bunt_usd × clamp(W_real, 1, swing_at)`), the Kalshi bunt is $30, the swing line 1.25 and the
  swing stake `bunt × E²`, the options bunt is $80, stock limit orders may be fractional (`day`),
  wind-down sells of stocks and options wait for the open, `kalshi-open` lists its maker-fee
  series, the House funds every Kalshi exchange shard its desks trade (`league/shards.py`), the
  Alpha Lab keeps running below the "all" OpenAI tier, and four invariants raise ops alerts (a
  quiet desk, a bunt frozen by a daily-loss rule, a lab closed 30 minutes, a graduate waiting 6
  hours). The first allocator pass re-staked mullins-2 from $10.09 toward $34.84.
- **Deploy B (#209: #201, #202, #204), 21:46Z.** Release `20260923T214445Z-f5650ac1d870`, no money
  rule changed (digest `1d63a56e`). The seat market: waiting lab graduates, replay-passed cards and
  merged strategies take every freed seat first and no House mutation is staked while any waits;
  newcomers with forward evidence may displace never-traded residents inside the grace; a desk
  keeps a seat for a trading member; no re-breeding of a family that is losing forward;
  population 112 and desk caps that follow the graduates. The lab evaluates its LLM children,
  re-scores its elites hourly on data that arrived after their code froze (forward windows rank,
  never promote) and reads the teacher's lessons as priors. Research runs on evidence (a fill,
  settlement, refusal, block, verdict or lesson) rather than the clock, the foundry follows
  forward yield, failed consults are refunded, and repair children are replayed before a seat.

Known limits:

- **Daily-bar replay now has separate execution bars.** Signal bars become available after
  their market day ends; five-minute execution observations provide trading opportunities.
  Unsupported or missing candidate inputs are reported explicitly. Existing historical tails
  remain development data; corrected clocks do not establish realistic fills or a market edge.
- **Self-improvement is bounded, and it now closes its own loop.** Sept 22, 2026 was the first
  full cycle with no human in it:
  - the engineer fixed a live strategy defect found by the pre-audit (#100);
  - CI passed it, and Merton's workflow merged it;
  - the updater attested the exact commit and deployed it through the canary.

  That cycle ended at the box: the House seated a merged strategy only in an empty seat, and by
  23:30Z that evening fifteen merged repairs had never been born. Since Sept 23, 2026 a corrected
  child is born even into a full league and judged on its own replay and forward record, and the
  agents off real money still running the code it corrects are retired (`superseded`).
  A labelled synthetic drill proved the revision path: the first patch was refused by CI, and the
  second was written against CI's failure text and merged (#104, #105). The engineer still cannot
  change core House code, the judges or the money rules. The external spending broker is not built
  yet; see [the handoff](docs/design/2026-09-20-chief-architect-handoff.md).
- **Merged code reaches the box by itself, only when it is attested, and only through the canary.**
  Every half hour the House reads main's head commit and downloads that exact commit (public, so
  the box holds no GitHub credential).
  - **Attested.** GitHub's API must show that the pinned Checks workflow and every required job of
    it passed on that exact sha. A later head never inherits an earlier head's approval.
  - **Judged by the running release.** The running release's `league/ci.py` judges the candidate
    tree as its own process with a scrubbed environment. Before Sept 22, 2026 the candidate ran its
    own checker.
  - **No self-edits.** A candidate that changes the judges (`ci.FORBIDDEN`: the constitution, the
    ledger, the evaluator, the auditor, `ci.py`, `updater.py`, `watchdog.py`, the money files, the
    agent-box seal) or the workflows is refused. Those land only by the owner's `floor_box.py deploy`.
  - **Recorded.** The attestation goes into the watchdog's deploy record and onto the ledger
    (`ops.deploy`).
  - Every failure fails closed, with a warning. A change to `real_money` is still refused on this
    path.
  - **Box egress.** The box needs `api.github.com` on its egress list for this; see
    `deploy/README.md`.
  - **What it does not cover.** An approved release still runs as the user that owns the release
    directory, and the House still holds the Sail key. See
    [the handoff's verifier section](docs/design/2026-09-20-chief-architect-handoff.md).
- **Practice fills are kinder than real ones.** Alpaca's paper account fills market orders at the
  touch with no queue; the Kalshi shadow book fills a resting order only when the market trades
  through it, but models no depth. The bunt (rung 2) exists to measure the difference, at a $10
  stake on Kalshi and $25 on Alpaca since the allocator ($30 a position before).
- **Paper uses a sliver of the paper account.** Each paper agent trades the live account's limits
  ($200 stake, $100 a position, $75 an order), so measured on Sept 22, 2026, 17 Alpaca paper
  agents used about 3% of the $99.4k paper account.
- **Alpaca fills are booked at the taker's fee.** Alpaca reports no fee and accepts every order
  asynchronously, so only the venue knows whether a limit order made or took; reconciliation
  returns a maker's difference to the House row.
- **An intent that would cross one of the House's own resting orders is refused**, not
  cancel-and-crossed: never a wash trade, at the cost of that fill.
- **Unpriced Sail web search is disabled during this phase**; the existing news fallback remains.
- **The first run's code is retained as a library.** The league imports parts of `ltcm/`; the rest
  (desks, committee, evolution, Foundry, lab) is no longer run; its retained runtime tests pass.
  Removing it safely is a job of its own.
- Expected dollars are small at this capital. The near-term product is verified edges and a
  standing, evidence-ranked recommendation of where the owner's next dollar belongs.

Blake Woods owns every position shown. Nothing published is investment advice.
