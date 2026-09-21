# Long-Term Capital Management

**An experimental trading league on Kalshi and Alpaca: agents compete for compute and improve
strategy programs, with an autonomous API chief architect as the next engineering milestone.**

Cheap open models on [Sail](https://sailresearch.com) research and write trading strategies. A
strategy climbs a ladder from mechanical replay, to paper trading, to a few real dollars, to real
size, and only evidence moves it up. Agents earn their share of the compute budget by what they
prove, die when they run out, and fork when they thrive. A frontier model audits every candidate
before it touches money and writes new strategy code, tools and fixes as pull requests that must
pass the tests. Venue keys, order caps, OpenAI/Jev limits and the kill switch live in a Cloudflare
gateway that agent code cannot change. The House still holds Sail credentials and enforces its
campaign budget; moving that authority outside the mutable House is part of the architect handoff.

**Current authorization:** [persistent earned live trading](docs/runs/2026-09-21-persistent-live-trading.md)
was activated by the owner on September 21 at 14:10 UTC, using existing venue balances with no live deadline.
It retains the original $500 foundation plus $325 burst accounting and resumes only unused
OpenAI/Sail allowance. Deployment alone cannot activate it; inspect `live_trading.active`.
The [September 21 live watch](docs/runs/2026-09-21-live-hour.md) records current provider funding,
paid SIP/OPRA readiness, the public agent ladder, and the first earned live execution and
settlement: a $5.6733 loss including fees. Its receipt exposed a Kalshi price/fee parsing defect;
the [accounting contract](docs/contracts/2026-09-21-kalshi-fill-accounting.md) documents the fix,
append-only recovery and exclusion of contaminated performance. A profitable live edge and
autonomous repair of the whole harness are still unproved.
Read the [foundation run](docs/runs/2026-09-20-foundation-progress.md),
[phase policy](docs/phase-one.md), [architect handoff](docs/design/2026-09-20-chief-architect-handoff.md),
[model comparison](docs/runs/2026-09-20-model-routing.md) and
[Jev integration](docs/design/2026-09-20-typesafe-pilot.md).

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
Sail model that researches on its behalf, a small memory, and an account of compute credits. The
first run's chat desks lost money; its code strategies were the only part that learned, so the
rebuild selects on code.

**The ladder.** Every agent climbs the same four rungs, and only evidence moves it. The thresholds
are versioned in [`league/constitution.py`](league/constitution.py). The owner-requested
September 20 revision removes the 30-block micro wait and adds a completed-exposure route;
see the [gate audit and live-learning window](docs/runs/2026-09-21-game-gate-audit.md).
What is measured is after-cost log growth in hour/day blocks or completed portfolio exposures.

| Rung | Where it trades | Stake and limits | What moves it up |
|---|---|---|---|
| 0. Replay | nowhere: its code is walked over recorded history in its own sealed box | none | at least 20 closed trades, 20 blocks and 8 positive-growth tail blocks (reused development data, not independent forward evidence), and a deflated Sharpe ratio of 0.5 or more against every replay in its own LINE (itself and its ancestors, not its cousins). The seat it wins costs nothing but compute, so the bar is better-than-even and not 90%: the gates that spend money come later (owner revision of Sept 21, 2026; it was 0.75 and 30 blocks) |
| 1. Paper | Alpaca's paper account; a Kalshi shadow book that reads live quotes and fills conservatively | $200 stake, $100 a position, $75 an order (the live account's limits, not the paper account's $100,000) | a **screen**, not a bound: 15 active hourly blocks (5 daily), **or 10 completed portfolio exposures**, with at least 10 closed trades, growth above zero and a drawdown under 15% over the last 30 blocks; then Merton's audit; only once the owner has turned real money on; and only while the micro rung's **tuition** has room (below). The drawdown is a trailing window because `max_drawdown` is a running maximum and never falls: read over a whole stay, one bad afternoon barred an agent from real money for the rest of its life, and between the screen's 15% and death's 30% it could be neither promoted nor killed. Death still reads the whole stay |
| 2. Micro-real | the real Kalshi and Alpaca accounts | $60 stake, $30 a position, $30 an order ($25 / $10 / $10 before the Sept 21 learning surge); down 20% since promotion returns it to paper | **5 active blocks or 10 completed portfolio exposures**, at least 10 closed trades of real fills, and a one-sided lower confidence bound on mean growth above zero (its own, or its family's pooled real-money record when its own growth is above zero) |
| 3. Scaled | the real accounts | half of Kelly on the lower bound of its growth (a quarter before the Sept 21 learning surge): never under the $60 micro stake, never over 40% of the venue's cash, a position up to half the stake and never above $60 (so one order under the $75 cap can always close it), $75 an order | nothing: it is resized every epoch, and a drift alarm sends it back down a rung |

These are rung ceilings. Event concentration can be tighter: a new $25 live agent has a
$7.50 single-market cap. The shared cap uses the existing funded venue authorization,
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
guarding a $25 stake. So the loss of the micro rung is capped in dollars instead of statistics. The
constitution's **tuition**: at most 4 agents hold real money on rung 2 at once; a new one is seated
only while the net loss of every real-money account that has not earned rung 3, plus what the seated
agents could still lose, reserving each **full $25 stake**, fits under **$50**. A drawdown stop cannot guarantee an exit price.
The rung is CLOSED when no further agent can ever be seated -- at $50, or when the reserve for one
more no longer fits and nobody is seated to change that -- and then everyone on it goes back to
paper and only the owner reopens it. Those two were once different numbers, and between $42.50 and
$50 with nobody seated the gate sealed itself: nothing could be promoted, and the alert that asks
the owner to raise the line could only fire by seating an agent the gate had just forbidden. An
agent that clears the screen and is turned away here now says so, once, with the seats and the
headroom. The strict
test stays where the money is, between micro-real and scaled. Promotion and death spend separate
alpha series there (a look that can only kill spends none of promotion's).

**Death on paper** (owner revision of Sept 21, 2026). A paper seat is free and scarce, so a clear loser
gives it up without waiting for a statistical bound: down 10% or more after 10 active blocks, or not
above where it started after 30. Death on real money is unchanged. The owner's live-trading grant now
pins only the rules that govern real money (`constitution.money_digest`), so the risk-free rungs can be
tuned without silently revoking it, and any change to a money rule still does; the grant recorded before
this revision is honoured only while its money rules are unchanged (`LEGACY_GRANT_DIGESTS`).

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
smaller, so the micro rung allows an option position of one contract up to $20. No entry in a
contract that expires today; the House sells anything still held at 14:30 New York on its last
day. Option quotes are fifteen minutes old (the live feed needs the OPRA agreement signed on the
account), which is why every option order is a limit order. There is no replay (no recorded
chains): paper is this specialty's replay. Not yet measured, because the market was closed: a
filled option order, Alpaca's end-of-day regulatory fees (the book now books any FEE activity
that explains a cash shortfall), and whether Alpaca holds cash behind a resting option bid (the
book accepts either). An unexplained difference freezes entries, never exits -- on a real-money book until the owner
clears it, and on a practice book only until the third reading that does not reconcile, when the
House takes the venue's word and carries the difference on its own row, crediting no agent.

**The funded campaign.** Production now uses `league/campaigns.py` and the persistent
[phase-one policy](docs/phase-one.md). The initial allowance is $500 over 48 hours, including
external engineering and infrastructure reserves; $50 is available to automated foundation
model work and up to $45 to Sail after its operating reserve. Jev's $20 allowance is backed
inside that existing model allocation. Calls reserve money before transmission; unresolved
bills retain their holds. Restarts, deposits and calendar changes do not renew the phase.
The legacy fourteen-day pacer remains for compatibility and fixtures. Current campaigns have
no catch-up spending or underspend acceleration. The gateway's monthly cap is an additional
ceiling. Credit rewards allocate research access within these limits; creating credits cannot
create vendor budget.

The [September 20 evening experiment](docs/runs/2026-09-20-evening-watch.md) adds one immutable
eight-hour research allowance: $250 OpenAI and $75 Sail, ending at 4:01 AM Pacific September 21.
It retains the foundation policy and Jev backing. New sessions compare 75% Luna with 25% Sail,
research runs every fifteen minutes, and a shared Jev lab tests fixed and architect-proposed
classification features against a numerical baseline. Faster cycles and stronger resource
rewards are experimental; independent forward evidence still decides whether they help.

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
hour scaled; losing, 8, 3 and 1. So the loop closes: trade well, earn a much larger share of the
day's pool, buy the best mind in the firm oftener, trade better. The rules text tells every agent
this in as many words.

The [persistent owner activation](docs/runs/2026-09-21-persistent-live-trading.md#account-owner-command)
replaces the timed $200 pilot. Agents begin with $25 and earn larger stakes under the existing
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
four times the share. Tonight's burst uses a one-hour payout, an exponent of three (8× the
performance share for twice the matched growth), and a 15% niche floor. A qualifying completed
exposure record can earn research resources before an hourly block. Promotion preserves earned
evidence: paper evidence keeps paper weight until real results mature, and loses that fallback
when real losses appear. Scaled agents keep the real record that qualified them. Measured on the first steep payout: two agents took 78% of the
pool and eighteen of thirty-five earned nothing at all. Before anyone is profitable the won share
goes to the least-bad TRADER, ranked by how far above the worst it is; an agent with no active
block earns none of it. Agents pay for what they use: model
tokens at Sail's prices, sandbox seconds ($0.04 an hour), web searches ($0.01) and their own audit
(at cost: $0.23 for the one measured). Credits cannot be created by an agent; every grant is a
House row on the ledger. These dials live in [`league/game.json`](league/game.json), inside bounds
the same file lists.

**Death.** Credits at zero; a 30% drawdown; an upper confidence bound on growth below zero after 20
active blocks or 10 completed exposures; on rung 0, twelve epochs without passing replay; **stuck and broke** -- thirty wakes
in a row with a live market in front of it and nothing done, and too little left to research its
way out; or **displaced**, when the league is full and a newcomer takes its seat. Idleness is not
safety: the niche floor is paid only to an agent that has traded within the epoch or has an order
resting, so one that does neither earns nothing and spends down what it has. A market that is SHUT
does not count against it, though -- an equity desk must not be starved to death over a weekend for
a session it does not control, and its floor is what pays for the only work a weekend has. The
House closes the account, retires the box and writes a post-mortem that every living agent's
research reads.

**The last seat is a tournament.** A ceiling with nothing dying under it is a floor that has
stopped searching: thirty-three agents were born in twelve hours and not one died, four births from
a league that could never try anything again. So when the population is full, a newcomer takes the
place of the worst agent that has had a fair chance -- never one on real money, never a profitable
one however small its record, never one younger than two epochs. Never having traded is the weakest
thing an agent can be, ahead of any amount of losing: an agent that trades and loses is being judged
by the evaluator and will be killed on its own evidence, while an agent that trades nothing is
judged by nobody and costs a box and a seat for as long as it is left alone.

**Forks.** An agent with $4.00 of credits or more may fork, and must endow the child with $1.50 of
its own ($1.00 is what the House stakes when it cannot). An agent above rung 0 never edits itself, because its record belongs to its code: an
improvement is a child, a mutation of its parameters or new code its researcher wrote, and the child
answers for itself from replay up — unless it has NO record at all (no holding, no working order, no active
block, no closed trade), in which case code that passes replay simply becomes its own, with no fork to pay for:
there is nothing for new code to inherit unfairly and no position to leave it holding. **And if its own rules
have not fired for ten wakes with a live market in front of them, a file that merely TRADES on the tape becomes
its own, failed verdict and all.** A candidate is adopted only when its replay passes, and passing needs twenty
closed trades -- so a looser rule that fires twice on a thin tape can never clear the bar, and the replay cannot
tell a better strategy from a worse one, only fail both. Six agents of the sports desk sat frozen for nine hours
that way, each shown up to two hundred live markets, paying for research they could never act on. The trial is
still counted and still deflates the lineage; paper is then the test, which is what paper is for. The population
is kept between 12 and 36; the House fills an empty seat within the hour, on the desk with the most room -- and
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
| **Merton** (the frontier model, `gpt-6-astra`) | behind the gateway's metered route | nothing | veto a candidate before real money; propose changes by pull request | pick a trade; touch the ledger; merge; change its own judges |

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
| a commit widens a bound and uses the wider value | the box judged it with the previous release's rules and refused it for ever | the incoming tree runs its own checks on itself, as GitHub already did |
| the expedition's Sail budget is spent | the meter latched "stopped" permanently -- no wakes, no research, no payouts, no deaths -- and the notice that would have said so sat inside the payout the flag closed | the meter guards the account; the pacer stops each kind of spending where it is spent, and says so outside every gate |
| an agent's rules never fire | it paid for research it could never act on, for ever | ten barren wakes pull research forward within the hour; with no record it adopts a file that merely trades; thirty and no credits left is a death |
| the league fills up | it stopped searching: nothing died, nothing new could be born | the last seat is a tournament, and never having traded is the weakest thing an agent can be |
| a number is written in two places | they drifted apart in silence, three times in one day | two tests refuse a brief that restates a bound `league.ci` or the constitution owns |

What still needs the owner: a **real-money** book that freezes on a position (deliberately -- there
the freeze is the point), the `real_money` switch itself, the gateway's keys and its kill switch,
and raising `tuition.max_loss_usd` when the micro rung closes.

## The constitution

What no model and no code path on Sail may change, and where each item is enforced.

| Item | Value | Enforced |
|---|---|---|
| Order caps | $75 an order, $4,000 and 2,000 orders a day | in the gateway, before anything is signed (`gateway/wrangler.jsonc`); `league/book.py` refuses first so it can say why |
| Kill switch | engaged or released | in the gateway; the House's token can engage it, only the owner's separate token releases it. The paper venue passes it, because no money is behind it |
| Jev allowance | $20 and 500,000 calls until September 21, 4:01 AM Pacific | external Durable Object; backed by retained campaign earmarks, with no calendar reset |
| OpenAI budget | $300 a month; tighter immutable campaign windows also apply | in the gateway: a call is reserved at its worst case and refused (402) when the month cannot cover it |
| Sail budget | $100 a month, $5 reserve | in `league/budget.py`, because Sail has no spend caps: at the line research and practice stop and only agents holding real positions are still woken, so they can exit |
| The ladder | every threshold, stake and limit above | constants in `league/constitution.py`; a test pins the file's digest, and the House writes the digest to the ledger every time it starts |
| The judges | `constitution.py`, `ci.py`, `ledger.py`, `book.py`, `evaluator.py`, `stats.py`, `auditor.py`, `watchdog.py`, `safety.py`, `replay.py`, `updater.py`, `gateway/`, `.github/` | out of reach of every Merton role: the gateway refuses the path before a branch exists, and CI's path guard refuses it again. GitHub runs that guard from `main`'s copy, so a branch cannot rewrite its judge |
| Real money | `"real_money": true` in `league/config.json` -- the owner threw that switch on Sept 20 | only the owner changes it; CI refuses an operator change to anything but four operating dials; the House refuses real money unless agents run in sealed Sailboxes |

## Merton's six jobs

Merton never picks a trade. As auditor it can only veto; in the other five roles it can do exactly one
thing, propose a pull request, and each role may touch only its own paths. The gateway opens the pull
request, [CI](.github/workflows/merton.yml) judges it (path guard, content checks, the replay
regression, the whole league suite) and a workflow job that never runs the branch's code merges a
green one. The workflow accepts `merton/` and the historical `astra/` prefix; accepting both
fixed an earlier source/deployment mismatch that left proposals unjudged. The role is the
second segment either way. Every pass is recorded with its cost. Failed checks still need
external repair; the durable API engineering worker has not been built yet.

| Job | When | What it does | May touch |
|---|---|---|---|
| Auditor | when a paper record clears the test; normally a 24-hour retry cooldown, but the accelerated game permits reconsideration after five fresh complete exposures or five fresh active blocks; half an hour after a provider error | reads the agent's whole evidence packet and hunts for look-ahead, fee errors, thin data, a record carried by one fill, duplicated exposure. A fresh audit still must approve promotion. The agent pays. Vetoes are scored afterwards as if taken | nothing |
| Architect | every 3 hours | reads the league table, the graveyard and the replay trials; writes at most two new strategies, born on rung 0. He aims at the desks where the EVIDENCE is worst, not at empty ones: each specialty reports how many of its members have looked at a live market and placed nothing, how many trade and lose, and the best growth anyone there has managed. An occupied desk full of agents that cannot trade is the emptiest thing on the floor, and twice he declined a pass with "every specialty is occupied" while twenty-six agents had never placed an order | `league/strategies/` |
| Toolsmith | every 3 hours, when agents have filed requests | builds pure-Python helpers agents may import, with tests; answers every request. The queue is ordered by how many different agents have asked for the same tool by name -- the best evidence the floor produces about what is missing -- then newest first. Unresolved and blocked engineering requests remain visible; an explanation without an implemented capability does not resolve them | `league/tools/`, `league/tests/test_tool_*` |
| Operator | every 4 hours | reads alerts, health and budget. It carries no bound of its own: the permitted range for every dial is read from `league.ci`, the checker that will judge its pull request, because two places holding one number is how the cap got put back where it throttled the floor | the dials in `league/config.json`, inside bounds |
| Game designer | every 12 hours | judges the economy: diversity, causes of death, where compute goes | `league/game.json`, inside the bounds it lists |
| Teacher | every 6 hours | distils the graveyard into specific, checkable lessons | `league/playbook/` |

## What is public

The House publishes to [blakewoods.us/capital](https://blakewoods.us/capital/), which draws five
sections from the tape:

1. a live stream of agents' thoughts, research and trades, and the league's own news (births,
   replays, promotions, audits, deaths);
2. total profit and running time;
3. the balance chart: the real Kalshi and Alpaca accounts against the owner's baseline, deposits
   and withdrawals taken out. Practice money is never added to it;
4. open and closed positions, each with the agent's own reason (practice positions are tagged);
5. [the live ladder](https://blakewoods.us/capital/#improvement): one dot per agent on Replay,
   Paper, Live or Scaled, recent promotion/demotion arrows, births and retired agents. Hover,
   keyboard focus or tap shows the agent's record. Invalid accounting is marked for review.
   The roster refreshes every 30 seconds; stale data is labelled. The
   [publisher contract](docs/contracts/2026-09-21-game-ladder.md) separates confirmed rank from
   audit approval, allocation and actual fills.

Strategy source stays private; its hash, parameters, family and results are public. The site
validates every byte and refuses a whole batch for one bad event
([the contract](league/tests/fixtures/site_contract.md)). A **test tape**
([blakewoods.us/capital/?tape=test](https://blakewoods.us/capital/?tape=test), `--tape test`) is the
same page over separate storage; the production tape stays empty until go-live.

## Repository layout

| Path | What it is |
|---|---|
| `league/` | The rebuilt runtime: the House. Standard library only. [Its own guide](league/README.md). |
| `ltcm/` | The first run's runtime. No longer run; the league imports its venue adapters, broker types, risk engine, fee model, Sail clients and data readers. [What is still used](ltcm/README.md). |
| `gateway/` | The Cloudflare Worker holding venue, OpenAI, TypeSafe and GitHub credentials, external caps and kill switch. |
| `scripts/` | The owner's tools: `floor_box.py` (the House's Sailbox), `gateway_admin.py` (kill switch and status), and the first run's scripts. |
| `deploy/` | [How the House runs on its box](deploy/README.md): releases, the canary, the two watchdogs. |
| `docs/` | [Index](docs/README.md): the design, the build log, the runbook, and the first run's record. |
| `playbooks/` | The first run's desk playbooks, kept as history. The league's lessons are in `league/playbook/`. |
| `.github/workflows/` | `merton.yml` judges and merges Merton's pull requests; `checks.yml` runs all three suites on every push to `main` and every pull request. |

The `league/` modules:

| Module | What it does |
|---|---|
| `ledger.py` | One append-only, hash-chained SQLite record of everything that decides an agent's fate. |
| `book.py` | One netting book per venue account: risk rules, netting, fill attribution, reconciliation to the cent. |
| `fees.py` | What a fill costs at each venue, as measured. |
| `venues.py` | The venue adapters in gateway mode (`alpaca`, `alpaca-paper`, `kalshi`). |
| `constitution.py` | The constants no model may change, and their digest. |
| `stats.py` | The statistics the ladder decides on: bounds, alpha spending, the loss-rate gate, deflated Sharpe, CUSUM, quarter-Kelly. |
| `evaluator.py`, `episodes.py` | The ladder: trials, blocks and completed portfolio exposures, promotion, death and drift. |
| `live_pilot.py` | Explicit owner activation and immutable deadline for the bounded live-learning window. |
| `live_trading.py` | Owner activation/revocation of persistent earned trading on a fixed allocation of existing venue cash. |
| `replay.py` | Rung 0: the mechanical replay simulator. Self-contained; runs inside the agent's box. |
| `tapes.py` | Recorded history for replay and live snapshots of the same shape, for both venues. |
| `paper.py` | The Kalshi shadow account: live quotes, conservative fills, no order ever sent. |
| `sim.py` | A simulated Alpaca account, the venue a canary House trades on. |
| `economy.py`, `game.json` | Compute credits: grants, charges, payouts, forks; the tunable dials and their bounds. |
| `agents.py` | Who is in the league: identity, strategy, lineage and fate, folded from the ledger. |
| `sandbox.py` | One sealed Sailbox per agent (or a local subprocess for tests). |
| `runner.py` | Runs one `decide` inside the box and prints one token-marked line. |
| `safety.py` | What a strategy file may contain: the import whitelist and the banned constructs. |
| `commons.py` | What agents share: web search, the research library, the tool-request queue, the playbook. |
| `researcher.py` | The research loop a cheap Sail model runs for one agent, at that agent's expense. |
| `rules.py` | The text every agent is told, generated from the constitution and the game file. |
| `seeds/` | The fourteen founding programs. |
| `pacer.py` | The expedition's pace: the owner's two budgets turned into a daily allowance that the credit pool, research and Merton follow. |
| `backup.py` | A daily checkpoint of the House's own box, kept by Sail: the ledger must outlive one disk. |
| `niches.py`, `niches.json` | The specialties: universes, briefs, founders, and the daily survey that lets a universe follow the season. |
| `strategies/`, `tools/`, `playbook/` | What Merton adds by pull request: strategies, helper modules, lessons. |
| `house.py` | The House: one `tick()` is the whole loop. |
| `budget.py` | The Sail budget meter. |
| `frontier.py` | The client for the gateway's metered frontier route. |
| `auditor.py` | The veto before real money, and its counterfactual score. |
| `merton.py` | Merton's five pull-request roles. |
| `ci.py` | The judge of every change: path guard, content checks, the suite. |
| `capital.py` | Rung 3 sizing and the standing capital recommendation for the owner. |
| `publish.py` | The public tape. |
| `service.py`, `config.json` | Builds the real House from the config and three secrets. |
| `__main__.py` | The command line. |
| `watchdog.py` | In-box releases: stage, canary, promote, watch, roll back. |
| `updater.py` | Pulls `main` every half hour on the House box and hands a changed tree to the watchdog; never lets `real_money` change that way. |
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
`python3 scripts/gateway_admin.py status | kill | unkill` reads and sets the gateway's kill switch.

**Switching the floor on** is in [docs/runbook-go-live.md](docs/runbook-go-live.md).

## Status

Built on September 19 and 20, 2026 ([the build log](docs/runs/2026-09-20-overnight-build.md) has
every decision and its reason), then watched for twenty hours and repaired where it did not work
([the watch](docs/runs/2026-09-20-the-watch.md)).

**Foundation phase is active.** The underlying real-money configuration remains enabled, but
the campaign blocks new live capital and buy intents while preserving reconciliation and exits.
At the verified 6:06 PM Pacific snapshot, 36 agents were alive, 18 retired, 70 research summaries
were complete, and 18 archived replay trials included two historical passes. Only Meriwether-8
had been promoted to paper in this phase. All four books reconciled. These are dated operational
counts; the [run report](docs/runs/2026-09-20-foundation-progress.md) records their limitations.

Known limits:

- **Daily-bar replay now has separate execution bars.** Signal bars become available after
  their market day ends; five-minute execution observations provide trading opportunities.
  Unsupported or missing candidate inputs are reported explicitly. Existing historical tails
  remain development data; corrected clocks do not establish realistic fills or a market edge.
- **Self-improvement is partial.** Merton can propose and deploy bounded strategy, tool, lesson
  and configuration changes. It cannot yet repair failed CI or core House code autonomously.
  PR #21 required external repairs before merging. The next milestone is the
  [durable chief architect and independent verifier](docs/design/2026-09-20-chief-architect-handoff.md).
- **Merged code reaches the box by itself, and only through the canary.** Every half hour the House
  downloads `main` (public, so the box holds no GitHub credential), lets that tree run its OWN
  content checks on itself (`league.ci --content-only`, a subprocess inside the tree, which is what
  GitHub already did to the same commit) and hands it to the in-box watchdog (`league/updater.py`,
  `league/watchdog.py`). It used to judge an incoming tree with the RUNNING release's checks, so
  the two judges disagreed by exactly one commit and a change that widened a bound and used the
  wider value could never reach the box -- for ever, because main is cumulative. A change to
  `real_money` is still refused on that path. This incoming-tree checker is insufficient for
  broad autonomous core editing; a protected verifier must precede that expansion.
- **Practice fills are kinder than real ones.** Alpaca's paper account fills market orders at the
  touch with no queue; the Kalshi shadow book fills a resting order only when the market trades
  through it, but models no depth. Rung 2 exists to measure the difference at $10 a position.
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
