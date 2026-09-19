# Switching the floor on

Written at the end of the overnight build (Sept 20, 2026). Every command runs from
`~/Work/long-term-capital-management` on your Mac unless it says otherwise. Nothing here asks you
to paste a secret into a chat or a file.

## What state things are in right now

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

- **Minutes 0 to 5.** The House takes each book's baseline, then founds the 26 specialists of
  `league/niches.json` (each one's strategy file is read inside a sealed Sailbox; two to three
  minutes for all of them) and stakes each with $200 of practice money. `status` shows
  `living: 26`. The live stream shows 26 "is born" lines. In the background it surveys Kalshi once
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
- **Equity strategies do nothing until Monday 09:30 New York.**

Nothing can reach real money in this mode. The earliest an agent can become eligible is after 15
active blocks and 10 closed trades with growth above zero and a drawdown under 15%: about a day
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

What changes: the House opens a book on the real Kalshi and Alpaca accounts and records their
baselines. **Still no order is sent** until an agent has (a) cleared the paper screen (15 active
blocks, 10 closed trades, growth above zero, a drawdown under 15%) and (b) passed Astra's audit.
Then it gets a $25 real stake and positions of at most $10. The screen is easy on purpose, and what
it may cost you is capped in dollars: at most 4 agents hold real money on that rung at once, and
when the rung has lost $50 net it closes, everyone on it goes back to paper, and you get an email.
Reopening it is yours: raise `tuition.max_loss_usd` in `league/constitution.py`, re-pin the digest
the test prints, and deploy. To reach a quarter-Kelly stake an agent must then show a lower
confidence bound on its growth above zero over 30 active blocks of REAL fills. The gateway's caps stand behind all of it: $75 an order, $4,000
and 2,000 orders a day. If the real account has open orders the House did not send, it refuses to
open that book and says so in `status`; cancel them at the venue.

## 4. Letting Astra open pull requests (optional, one secret)

The auditor works now. Astra's other five jobs (architect, toolsmith, operator, game designer,
teacher) can only act through pull requests, and the credential for that lives in the gateway like
every other. Create a fine-grained GitHub token for this one repository with **Contents: read and
write** and **Pull requests: read and write**, then:

```sh
cd gateway && npx wrangler secret put GITHUB_TOKEN    # paste the token at the prompt
```

Until you do, each scheduled pass still runs and is recorded on the public tape with what Astra
concluded, and any change it wanted is dropped with "GitHub is not configured". With the token, a
proposal becomes a branch `astra/<role>/...` and a pull request; GitHub's `Astra` workflow judges it
(the path guard from main's copy, the content checks, the replay regression, the whole suite) and
merges it only when everything is green. Merged code reaches the box by itself: every half hour the
House downloads `main` (the repository is public, so the box needs no credential), runs the running
release's own content checks on it, and hands it to the in-box watchdog, which runs it as a canary,
promotes it, watches the House for ten minutes and rolls back if health degrades. The same is true
of anything you push to `main`. One thing never travels that way: a change to `real_money` is
refused by the updater, so that switch is only ever your own `floor_box.py deploy`.

## 5. Watching it during the week

```sh
python3 scripts/floor_box.py status            # loop, release, health, last deploy, log tail
python3 scripts/floor_box.py logs -n 50        # the House's own log: one JSON line a tick
python3 scripts/gateway_admin.py status        # kill switch, today's real orders, OpenAI month, Sail balance
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

## 7. What the unattended week is expected to cost

Measured during the build, at Sail's and OpenAI's current prices:

| What | Basis | A week |
|---|---|---|
| The House box | one small box, mostly idle: about half a cent an hour | about $1 |
| Agents' sandbox seconds | about 9 s a wake; 26 agents; 5 to 60 minute clocks | about $2 |
| Research passes (cheap Sail models, flex window) | measured $0.001 to $0.002 a pass, at most one per agent every four hours | about $2 |
| Web searches | Sail does not publish a price; the House assumes $0.01 each | under $2 |
| **Sail total** | bounded above by the economy: agents cannot spend credits they were not granted ($2 a day plus $26 of endowments), and the House stops research at $100 in a calendar month | **$5 to $9, at most about $40** |
| Astra, auditor | $0.23 measured for one audit; an agent is audited at most once every 72 hours | $0 to $3 |
| Astra, other roles (only with the GitHub token, but the passes run either way) | operator daily (about $0.10), toolsmith daily when the queue has requests ($0.06), teacher every three days, designer and architect weekly ($0.10 measured; up to $1.25 when it writes code) | $2 to $4 |
| **OpenAI total** | hard-capped by the gateway at $100 a month | **$2 to $7** |

Real-money risk in the first week, if you turn it on: at most a handful of $1 to $10 positions,
and none at all until an agent clears the paper test and the audit.
