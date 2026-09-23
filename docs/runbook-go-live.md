# Switching the floor on

Written at the end of the overnight build (Sept 20, 2026). Every command runs from
`~/Work/long-term-capital-management` on your Mac unless it says otherwise. Nothing here asks you
to paste a secret into a chat or a file.

> Since then: real money is on, the owner's persistent live grant is active, and the House deploys
> attested merged code by itself. "Where things stand now" below is current as of Sept 23, 2026.
> Sections 1 to 3 describe the switch as it was made on Sept 20 and are kept for the record;
> sections 4 to 6 still apply, and section 7 is superseded. The running league is operated from [operations.md](operations.md), and its state is in the
> [README's status](../README.md#status).

## Where things stand now (Sept 23, 2026)

- **Real money is on.** `league/config.json` says `"real_money": true` (your switch, Sept 20) and
  the persistent live grant is active. The in-box updater deploys attested merged code every half
  hour, except a change to the judges (`ci.FORBIDDEN`, which holds the money rules), the workflows
  or `real_money`: those are your deploy.
- **Capital is the ladder.** Since the allocator's release (`20260923T082402Z-7c69b3eb57f0`,
  promoted at 08:27:54Z on Sept 23) an agent's evidence, its wealth multiple, moves it between
  bands at every mark pass, around the clock:
  - **Bunt:** $10 at Kalshi or $25 at Alpaca, once E ≥ 1.01 with 5 closed paper trades (or 3
    settlements on Kalshi).
  - **Swing:** the bunt × min(E, 20), up to 60% of the venue, once E ≥ 1.5, W_real ≥ 1 and 8 real
    closed trades. The first swing is audited.
  - **Down as fast:** hysteresis, a 35% real drawdown straight back to paper, death on paper
    wealth under 0.80, and a floor throttle that halves every real stake once the floor's real P&L
    falls below −30% of the envelope, until it recovers to −15%.

  The README's [Bands of capital](../README.md#bands-of-capital) has the whole rule.
  `allocator.enabled: False` in `league/constitution.py` is the rollback to the old ladder of
  sections 2 and 3. It is a money rule, so it needs your deploy and a ratify.
- **The grant.** `earned-live-20260921`: Alpaca $500, Kalshi $517.75, a $1,017.75 loss line, no
  expiry. It counts 101 agents, the allocation over the $10 stake line (the smallest bunt). It is
  pinned to money digest `44e8d48d…` (constitution `9fa83727…`), ratified at 08:28:13Z on Sept 23.
  The allocator's envelope at each venue is that capital plus the realized profit there.
- **After a money-rule change**, from a clean worktree at `origin/main`:

  ```sh
  cd ~/Work/ltcm-deploy && git fetch -q origin && git checkout -q --detach origin/main
  python3 scripts/floor_box.py deploy      # in the background; watch its log for promoted, ROLLED_BACK, EXIT
  python3 scripts/live_trading.py --ratify earned-live-20260921   # at once, the moment it says promoted
  ```

  Until the ratify, the grant reads inactive: real-money entries are refused (exits continue) and
  no agent moves up. On Sept 23 the ratify came 19 s after promotion; a late one had once stopped
  the floor for 9 minutes. A rollback across a money-rule change leaves the grant pinned to the
  new digest, so ratify again on the rolled-back release. To check whether a change touches a money
  rule, compare `python3 -c "from league.constitution import money_digest; print(money_digest())"`
  with the grant's digest.
- **The lab box.** The Alpha Lab runs on its own Sailbox, `ltcm-lab`
  (`sb_742fe765-f041-450a-acda-e9d898137949`, size l, sealed, created 07:01:49Z on Sept 23), named
  in `league/config.json` `lab`. `python3 scripts/lab_box.py status` reads it and `sleep` puts it to
  sleep; it also sleeps by itself after ten idle minutes. If Sail terminates it, the lab stops with
  an error alert and is never given a replacement from the agents' image: make one with
  `python3 scripts/lab_box.py create`, which records the new id in `league/config.json`, and deploy.
- **Compute.** The OpenAI month is $408 and Jev's allowance $42, each metered spend plus your funded
  balance on Sept 23. The gateway indexes the OpenAI month to profit (0.3 of the real accounts'
  equity above $1,017.75), but holds it to the funded $408, so profit buys nothing more until you
  fund more. Sail is prepaid; its auto-recharge is your decision.
- **The watch.** `python3 scripts/floor_watch.py` prints, read-only, the bands, real money,
  evidence, the lab, costs, health and the site's checkpoint. Section 5 has the rest.

## What state things were in at the build (Sept 20, 2026)

- **Nothing is trading and nothing is publishing.** The gateway's kill switch is engaged. The
  House loop is stopped. The production page `https://blakewoods.us/capital/` is empty and shows
  the red "stopped" dot by itself (it reads the dot from the data: no fresh checkpoint, no green).
- **The House box** (`ltcm-floor`) holds the league at the release the watchdog promoted during
  the build. It is paused. It holds three secrets and no venue key.
- **`league/config.json` says `"real_money": false`.** That is the practice league: Alpaca's paper
  account and the Kalshi shadow book. No real order is possible in this mode whatever the kill
  switch says, because the real books are never built.
- **The Alpaca paper account is flat** (no positions, no open orders). Leftover open orders there
  are cancelled by the House when it first opens its book; leftover positions are simply recorded
  as not the book's.

## 1. Switch on the practice league (no real money)

```sh
python3 scripts/floor_box.py resume        # the box wakes; nothing starts by itself
python3 scripts/floor_box.py deploy        # sends main; the in-box watchdog runs it as a canary first
python3 scripts/floor_box.py start         # the supervised House loop starts from /workspace/current
python3 scripts/floor_box.py status        # loop alive, current release, health, log tail
```

`deploy` prints `PROMOTED: <release id>` when the canary passes (three ticks of a House that can
hurt nothing: a simulated paper account, its own shadow book, no publishing). It takes a few
minutes. If it prints `REFUSED`, the reasons are on the line below and in
`python3 scripts/floor_box.py logs --deploy`; the box keeps running the release it had.
If `deploy` says the current release already has this content, skip straight to `start`.

That is the whole switch. The page turns itself on: within about two minutes of the first
published checkpoint the dot goes green and says "live".

## 2. What you will see in the first hour

- **Minutes 0 to 5.** The House takes each book's baseline, then founds the 28 specialists of
  `league/niches.json` (each one's strategy file is read inside a sealed Sailbox; two to three
  minutes for all of them) and stakes each with $200 of practice money. `status` shows
  `living: 28`. The live stream shows 28 "is born" lines. In the background it surveys Kalshi once
  (about a minute and a half) so every specialty's universe is ranked by what is trading today.
- **Minutes 5 to 20.** Every agent wakes on its own clock (5 to 60 minutes). You will see their
  thoughts ("Saw 27 hourly markets, 2 favourites in the band..."), resting Kalshi bids on the shadow
  book, crypto limit orders on Alpaca paper, and "failed replay" lines: each seed's own code is
  replayed once against recorded history and most seeds honestly fail that test (crypto reversion
  lost 2.7% after fees; Kalshi favourites scored a deflated Sharpe of 0.85 against the 0.90 line).
  Founders trade on paper anyway; their children will have to pass.
- **From minute 10 on.** Research passes: one agent at a time thinks with a cheap Sail model
  (about a tenth of a cent a pass), searches the shared library and the web, writes notes other
  agents can read, and files tool requests.
- **Total profit stays at $0.00 and the balance chart stays flat** for as long as the league is on
  practice money: both show only the real Kalshi and Alpaca accounts. When your transfer from
  Coinbase lands it is read as a deposit, not as profit. Closed practice trades appear in the
  closed table tagged "practice"; open practice positions are listed under the real ones, tagged.
- **The self-improvement chart** shows generation 1 only until an agent earns enough credits to
  fork (about three dollars of credits: days, not hours) or a seed dies and is replaced.
- **Equity and option strategies do nothing until Monday 09:30 New York**; over the weekend the two
  option founders and the six equity ones research (the option chain and Friday's closing quotes are readable).

Nothing can reach real money in this mode. Under the rules in force since Sept 23, 2026 the
earliest an agent can become eligible is after 3 active hourly blocks (1 finished day for a daily
agent) and 3 closed trades, with growth above zero and a drawdown under 25% (the owner's
swing-and-bunt revision, Sept 23, 2026 ~03:10 UTC). At the build it was 15 active blocks and 10 closed trades: about a day
for the fastest hourly agents, two to three weeks for a daily one.

## 3. Turning real money on (your call, any time)

Two switches, both yours, in this order:

```sh
# 1. Tell the House it may open the real books (then send it to the box through the canary).
python3 - <<'PY'
import json, pathlib
p = pathlib.Path("league/config.json"); c = json.loads(p.read_text()); c["real_money"] = True
p.write_text(json.dumps(c, indent=2) + "\n")
PY
git commit -am "Real money on: the owner's switch" && git push
python3 scripts/floor_box.py deploy

# 2. Release the gateway's kill switch (it is engaged now).
python3 scripts/gateway_admin.py unkill
```

A third switch has been yours since Sept 21: the persistent live grant,
`python3 scripts/live_trading.py --enable <identity>`
([persistent earned live trading](runs/2026-09-21-persistent-live-trading.md)). The campaign
admits no agent to real money without it, and a change to any money rule leaves it inactive until
you re-ratify it for the same capital (`--ratify <identity>`; see [operations](operations.md)).

What changes: the House opens a book on the real Kalshi and Alpaca accounts and records their
baselines. (Since Sept 23, 2026 the allocator decides who reaches real money; see "Where things
stand now" above. What follows is the old ladder, which is now the rollback path.) **Still no order
is sent** until an agent has cleared the paper screen: 3 active hourly
blocks or 1 finished day, or 10 completed exposures; 3 closed trades; growth above zero, the block
in progress counted; a drawdown under 25%. Then it
takes a $60 real stake with positions and orders of at most $30, and Merton's audit follows on
that rung (since Sept 23, 2026). A veto sends it back to paper, and so does a 20% loss since
promotion. An agent with a known defect is audited before it is promoted. The screen is easy on
purpose, and what it may cost you is capped in dollars. While the grant is active its envelope is
the cap: 16 agents on this path (101 under the allocator), a $1,017.75 loss line, and $500 on
Alpaca and $517.75 on Kalshi. Without a
grant it is the constitution's tuition: at most 4 agents on that rung at once, and a $50 net
loss. When a line is reached everyone on that rung goes back to paper (for a venue's line, the
agents on that venue), and the aggregate line also raises an error alert. The constitution's line is raised by changing `tuition.max_loss_usd` in
`league/constitution.py`, re-pinning the digest the test prints and deploying; the grant's
envelope is fixed. To reach a larger stake an agent must then show a lower confidence bound on
its growth above zero -- the lower 80% bound, promotion's alpha of 0.20 spent across looks -- over
3 active blocks or 10 completed exposures of REAL fills, with 3 closed trades; it is then sized at
full Kelly on that bound, up to 60% of the venue's cash, so the swing grows with the evidence. The gateway's caps stand behind all of it: $75 an order, $4,000
and 2,000 orders a day. If the real account has open orders the House did not send, it refuses to
open that book and says so in `status`; cancel them at the venue.

## 4. Letting Merton open pull requests (optional, one secret)

The auditor works now. Merton's other five jobs (architect, toolsmith, operator, game designer,
teacher) can only act through pull requests, and the credential for that lives in the gateway like
every other. Create a fine-grained GitHub token for this one repository with **Contents: read and
write** and **Pull requests: read and write**, then:

```sh
cd gateway && npx wrangler secret put GITHUB_TOKEN    # paste the token at the prompt
```

Until you do, each scheduled pass still runs and is recorded on the public tape with what Merton
concluded, and any change it wanted is dropped with "GitHub is not configured". With the token, a
proposal becomes a branch `merton/<role>/...` and a pull request; GitHub's `Merton` workflow judges it
(the path guard from main's copy, the content checks, the replay regression, the whole suite) and
merges it only when everything is green. Merged code reaches the box by itself.

- **When.** Every half hour the House reads main's head commit and downloads that exact commit. The
  repository is public, so the box needs no credential.
- **Only if attested.** GitHub's API must show that the Checks workflow and its required jobs passed
  on that exact sha. This needs `api.github.com` on the box's egress list:
  `floor_box.py hosts --add api.github.com`.
- **Judged by the running release.** The running release's content checks are run against the
  commit.
- **Then the watchdog.** The commit goes to the in-box watchdog, which runs it as a canary, promotes
  it, watches the House for ten minutes and rolls back if health degrades.

The same is true of anything you push to `main`. Some things never travel that way; only your own
`floor_box.py deploy` lands them:

- a change to `real_money`;
- a change to the judges (the files `ci.FORBIDDEN` lists);
- a change to the workflows.

## 5. Watching it during the week

```sh
python3 scripts/floor_box.py status            # loop, release, health, last deploy, log tail
python3 scripts/floor_box.py logs -n 50        # the House's own log: one JSON line a tick
python3 scripts/gateway_admin.py status        # kill switch, today's real orders, OpenAI month, Sail balance
python3 scripts/floor_watch.py                 # the watch (Sept 23, 2026): bands, money, lab, costs, health
python3 scripts/lab_box.py status              # the Alpha Lab's box: its seal, python, the tapes it holds
```

The page is the rest: `https://blakewoods.us/capital/`. The test tape used during the build is at
`https://blakewoods.us/capital/?tape=test`.

You will get email from the gateway's watchdog when it has run out of things it can do by itself
(the box will not come back, Sail credit is low) and an evening digest. It restarts a quiet House
by itself, at most every thirty minutes.

## 6. Stopping everything

```sh
python3 scripts/gateway_admin.py kill          # no real order can pass the gateway, from this second
python3 scripts/floor_box.py stop              # the House finishes its tick, sleeps its agents' boxes, exits
python3 scripts/floor_box.py pause             # the box stops billing
```

`stop` alone ends the league; `kill` alone ends real trading and leaves the practice league
running. Open real positions are not closed by stopping: Kalshi contracts settle by themselves;
anything on Alpaca stays until you sell it or restart the floor.

One thing to know about `pause`: once the production page has a checkpoint, the gateway's
watchdog reads a stale one as "the floor went quiet", resumes the box and runs its restart script.
A stopped House stays stopped (the restart script cannot start a stopped supervisor), so nothing
trades, but the box goes back to billing about half a cent an hour. To park the box for longer than
a day, stop it, pause it, and clear the public tape (`POST /api/capital/reset?confirm=erase-everything`
with the publish token) so the watchdog sees nothing to revive.

## 7. What the fortnight is expected to cost

Superseded since September 20, 2026, when production spending moved to the funded campaign
([phase one](phase-one.md)); the fourteen-day pacer below remains only for compatibility and
fixtures. Kept for the record.

This replaces the thrifty estimate below it: on Sept 19 you asked for both budgets to be USED, in
full, over fourteen days (Sept 19 to Oct 2). `python3 -m league status` and the public tape's
`ops.budget` rows show the pace every day: day N of 14, spent, and today's allowance.

| What | How it is paced | The fortnight |
|---|---|---|
| Sail | about $7.14 a day at the start, recomputed daily from what is left. 85% of it is the day's credit pool; research runs on DeepSeek V4 Pro (measured $0.02 a pass) every 3 hours an agent, every 1.5 while the day is underspent | up to **$100**, less the $5 the House never spends. Your Sail balance was $97 at the start, so about $92 is reachable without a top-up |
| Frontier model (Merton) | about $7.14 a day: architect, operator and toolsmith every 8 hours, teacher every 12, designer every 36, one at a time while the day's allowance lasts; audits are not paced | up to **$100**; the gateway's $100-a-month cap resets on Oct 1 and the House's own count of the expedition's spend is what stops it at $100 |

When either is gone, or on Oct 3, that kind of spending stops for good and you get one email saying
so. Agents still wake and trade. To go on, change `budgets.expedition` in `league/constitution.py`,
re-pin the digest the test prints, and deploy.

### Before the expedition: the thrifty estimate (kept for the record)

Measured during the build, at Sail's and OpenAI's current prices:

| What | Basis | A week |
|---|---|---|
| The House box | one small box, mostly idle: about half a cent an hour | about $1 |
| Agents' sandbox seconds | about 9 s a wake; 28 agents; 5 to 60 minute clocks | about $2 |
| Research passes (cheap Sail models, flex window) | measured $0.001 to $0.002 a pass, at most one per agent every four hours | about $2 |
| Web searches | Sail does not publish a price; the House assumes $0.01 each | under $2 |
| **Sail total** | bounded above by the economy: agents cannot spend credits they were not granted ($2 a day plus $26 of endowments), and the House stops research at $100 in a calendar month | **$5 to $9, at most about $40** |
| Merton, auditor | $0.23 measured for one audit; an agent is audited at most once every 72 hours | $0 to $3 |
| Merton, other roles (only with the GitHub token, but the passes run either way) | operator daily (about $0.10), toolsmith daily when the queue has requests ($0.06), teacher every three days, designer and architect weekly ($0.10 measured; up to $1.25 when it writes code) | $2 to $4 |
| **OpenAI total** | hard-capped by the gateway at $100 a month | **$2 to $7** |

Real-money risk in the first week, if you turn it on: at most a handful of $1 to $10 positions,
and none at all until an agent clears the paper test and the audit.
