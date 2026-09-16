# The floor moves to Sail · September 15, 2026, evening

Second hand-off record of the day. The morning record (`2026-09-15-ltcm-launch.md`) describes
the floor on the MacBook with paper desks. By the evening the owner had asked for three things:
nothing running on the Mac, no paper trading, and only real production trading on Kalshi and
Coinbase (Alpaca when the live account opens). This is the state after that move.

## What is running

- **Floor loop on a Sailbox**: `sb_d36bc830-0d04-4761-8898-0ff4daa199dc` (`ltcm-floor`, size s:
  1 vCPU, 16 GiB, 32 GiB disk, autosleep off, about $0.005 an hour at this load). `run.sh` on the
  box supervises one `python -m ltcm run` and restarts it 30 seconds after it exits;
  `scripts/floor_box.py` is the operator's console (`status`, `logs`, `deploy`, `checkpoint`,
  `stop`, `start`, `hosts`). The Mac unit `ltcm.service` is disabled.
- **Two desks, both live, real money**: Mullins on Kalshi ($492.29 sleeve; sessions 08:10, 13:30
  and 20:30 New York plus a session whenever a market it held settles) and Hilibrand on Coinbase
  ($487.32 sleeve; sessions 00:30, 06:30, 12:30 and 18:30 UTC). Both on DeepSeek V4 Pro in the
  flex window. The four equity desks are parked in `ltcm/desks/pending-alpaca/`.
- **Order gateway**: the Cloudflare Worker `ltcm-gateway` holds the venue keys as secrets and is
  the only thing that can sign a Kalshi or Coinbase request. Caps: $50 an order, $400 and 60
  orders a day, kill switch. Its five-minute cron is also the watchdog: it reads the published
  checkpoint, the Sail balance and the box state, restarts the loop when the checkpoint goes
  stale, and emails the owner about a low Sail balance or a box it could not bring back.
- **Aggregate balance on the site**: the checkpoint carries `floor.account_equity` as the sum of
  the Kalshi and Coinbase balances ($979.61 at 18:23 UTC) and `floor.venues` with each venue's
  numbers; `floor.mark` events keep the history.

## Timeline

| UTC | What happened |
|---|---|
| 18:09 | Owner placed the secrets (`scripts/place_secrets.sh`) and started the loop |
| 18:10 | Watchdog found the site checkpoint stale (the Mac's last one) and signalled a restart |
| 18:11 | Mullins opened the 13:30 New York slot: reviewed the book, searched Kalshi for Fed markets ahead of the September 16 FOMC decision, read the news |
| 18:13 | Operator stop to drop the parked desks from the box roster; the session was killed |
| 18:23 | Exact gateway host added to the box's egress allowlist; first venue balances reached the site |
| 18:29 | Loop restarted into the new code; Mullins' interrupted slot was sat down again at once |
| 18:30 | Hilibrand opened its 18:30 slot |

## What was verified live

| Check | Result |
|---|---|
| Box reaches the gateway | `ltcm-gateway.blake-woods-personal-site.workers.dev` resolves from the box once listed by its exact name; the `*.workers.dev` wildcard was accepted by the API and never resolved |
| Kalshi balance through the gateway | $492.29 in 0.2 s from inside the box |
| Coinbase balance through the gateway | $487.32 in 0.4 s from inside the box |
| Site checkpoint | `floor.account_equity` 979.61, both venues listed, `floor.mark` on the tape |
| Gateway health | ok, kill switch off, 0 orders today, Sail balance $279.87, watchdog age 1 s |
| Rate card | all fourteen model profiles match Sail's published prices |
| Interrupted-slot retry | Mullins' killed 13:30 session re-opened one second after the restart |
| Sailbox checkpoint | `sbcp_f01dad7a-7290-4d03-98eb-f782d7f0476d`, live-ready, contains credentials |

## Known gaps

- **A deploy kills a running session.** `floor_box.py deploy` restarts the loop into the new
  code; the schedule retries the slot once, but the desk's reasoning up to that point is spent.
  Deploy between sessions where possible.
- **The Kalshi order path is still unexercised.** Every order goes out through the gateway with
  the v2 endpoint, fixed-point strings and the price grid check, but no live Kalshi order has
  been placed yet; the first one is the thing to watch on the committee page.
- **The 409s from the Mac run.** The site holds 24 budget events from the Mac's afternoon with a
  different digest than the box computed; the publisher skipped them and alerted once. They do
  not recur.
- **No email has been seen end to end.** The watchdog recorded a `box_not_running` alert at
  18:10 UTC during the start-up; whether the mail arrived is for the owner to confirm.

## Operating

```sh
.venv/bin/python scripts/floor_box.py status        # box, loop, floor, spend, checkpoints
.venv/bin/python scripts/floor_box.py logs          # the box's own log
.venv/bin/python scripts/floor_box.py deploy        # push the working tree, restart the loop
.venv/bin/python scripts/floor_box.py checkpoint    # a live-ready snapshot (holds credentials)
.venv/bin/python scripts/floor_box.py hosts --add <host>   # widen the egress allowlist
```

When Alpaca opens: `scripts/setup_venues.py setup` for the live keys, move the manifests back
from `ltcm/desks/pending-alpaca/`, add `alpaca` to `live_venues` in `ltcm/config.json`, run
`bash scripts/place_secrets.sh`, then `floor_box.py deploy`.

## Addendum, 19:10 UTC: no cap on infrastructure spend

The owner's instruction: no cap on infra spend, as long as he is told when to top up and the
floor stops gracefully when he does not; be as bold as the credit allows in pursuit of
recursive self-improvement. What changed:

- **Spend policy is a runway** (`ltcm/runway.py`). No daily cap: the Sail credit above a $10
  reserve is the limit. Under three days of runway the floor throttles to the live desks; at
  the reserve it stops new sessions and waits; credit added at Sail reopens it within a minute.
  The mode, the balance and the runway are published in every checkpoint and on the tape.
- **Notifications are by runway.** The gateway mails at seven days of runway with the date the
  credit runs out, again at two days, and once more when the floor reports itself stopped.
  A paused box is resumed whenever the balance is above the reserve.
- **The race is seeded.** Each family is bred up to four variants: the live desk plus three
  shadow children (mutated persona, effort, session times, and one in three on another
  model), two per hour until full. The children score against real prices without money and
  the promotion gates decide who takes the sleeve. Selection retires the laggards.
- **The live desks think harder and more often.** High reasoning effort, 16k output tokens,
  40 and 32 turns, five Kalshi sessions a day and six crypto sessions a day.
- **One fuse.** A desk may not commit more than a quarter of the spendable credit in a day: a
  guard against a tool loop, not a budget.

## Addendum, 20:30 UTC: the leap, phase one through three, foundations laid

Built in one evening by four parallel workstreams against `docs/contracts/2026-09-15-floor-v2.md`
and merged: 980 runtime tests, 69 gateway tests, 46 site tests.

- **Feeds.** A standard-library WebSocket client; Kalshi fills, resolutions and tickers and
  Coinbase ticker and user channels, with socket credentials minted by the gateway so no key
  reaches the box; fills confirmed by REST before the ledger; the Kalshi API tier upgrade asked
  once after the first fill. Three persistent connections from the box.
- **Exits the floor keeps.** Every proposal may name a target, a stop and a holding period; the
  risk engine refuses a stop on the wrong side; Coinbase carries the bracket on the order, the
  floor enforces Kalshi levels and every time stop as exposure-reducing exits.
- **The night desk.** Between sessions the floor watches held markets, coins, fills, new markets
  and headlines, spends one flash-model turn on whether to wake the desk, and publishes both
  verdicts.
- **Calibration and the lab.** Every stated probability is scored at resolution (Brier,
  reliability by decile, by desk, family, generation). Nightly the lab proposes bounded
  experiments, breeds them as directed shadow variants, judges them on gate evidence, and folds
  adopted changes into the family's house genome. Capital is allocated as a bandit.
- **Sandboxes.** A lab image (python, numpy, pandas, labkit over the read-only data package) is
  checkpointed once; each desk forks its own box on first `run_code`, keeps a toolbox its
  children inherit, and every run is public with the code's hash. A probe fork came up in four
  seconds and read real BTC bars.
- **The site.** A portfolio board with every holding and the desk's reasoning inline, a run
  clock (how long, how much, profit per Sail dollar), lineage tree, experiments and the
  improvement curve, trade stories and calibration on the desk pages, and a one-screen explainer
  of the three loops.

Two production incidents on the way, both fixed within minutes: the runway budget event reused
an id with different content and stalled every tick for half an hour; the WebSocket client's
GUID had a transposed character and every real server refused the handshake.

## Addendum, 22:20 UTC: why nothing traded, and what changed

The owner asked why a 24/7 recursive fund made no trade on its first day. The honest answer:
the floor was set up to pass. Both live desks had narrow mandates and strict thresholds (eight
cents of edge on Kalshi; a one percent move on Coinbase at taker fees), only two families
covered a sliver of what the venues offer, most of the day was spent restarting into new
code, and the flex completion window queued turns for minutes. A floor that makes no
decisions produces no outcomes, and the loop selects on outcomes. Changes, all live:

- **Mullins**: every public event series; three cents of edge after fees (and 1.5 times the
  fee) instead of eight; a recorded forecast for every market priced; eight sessions a day;
  sleeve $200 of the Kalshi cash.
- **Scholes** (new, live, $142): Kalshi's hourly, daily and weekly BTC, ETH and index range
  markets, each bucket priced from realized volatility in his sandbox; twelve sessions a day;
  settlements within hours.
- **Haghani** (new, live, $150, being built as this is written): Kalshi daily temperature
  markets priced from National Weather Service forecasts; resolves every day.
- **Hilibrand**: ten pairs, maker orders, a hurdle of twice the round-trip fee, intraday
  setups, up to four positions, twelve sessions a day; the house view appended to the family's
  live playbooks rather than overwriting the desks' own rewrites.
- **Every desk** in the asap window; children inherit the founder's tools; duds are retired;
  Kimi K3 in the gene pool; gateway caps sized so the desks' own limits bind first.

## Addendum, 23:35 UTC: four reviewers on the live run

Four parallel reviews of the evening's sessions, the loop machinery, the plumbing and the
public output, each fixing what it found. The three that mattered most:

- **No forecast could ever have been scored.** Kalshi reports a settled market as
  `finalized`; the resolver waited for `settled`. Calibration, the post-mortem's calibration
  block and the lab's evidence would have stayed empty forever.
- **Every desk read one shared memory pool.** Children copied their parent's and each other's
  notes, six of them wrote the same three rules into their playbooks, and the abandoned
  eight-cent threshold re-entered the crypto and range families as a "learned rule". Memory is
  per desk now; the contaminated rule sections and thirteen copied lessons were removed by hand.
- **The box could not reach the Sailbox API**, so every `run_code` failed in forty
  milliseconds; the host is on the allowlist now and a run from the box takes four seconds.

Also fixed: sessions no longer die on a long turn (every request is dispatched in the
background and polled), the lab spreads its night over ticks instead of blocking the loop
past the watchdog's threshold, post-mortems run only after a trading session, lessons written
as prose are parsed, incomplete playbook rewrites fall back to the parent's, bars are five
times smaller on the wire, search matches inside tickers, idle lines carry the next session,
end reasons read as words, and bred desks outside the partner table render by name.

## Addendum, 23:30 UTC: the verification sweep

Four more agents checked the merged floor for bugs. What they found and what was done:

- **The trading review had been lost.** An aborted merge earlier in the evening silently
  discarded it; the memory fix survived through another branch but the bars, search, playbook
  and header fixes did not. Re-merged, with a broken post-mortem gate found and fixed on top.
- **Venue keys were on the box and in every checkpoint.** The secrets command had uploaded the
  whole `.env` and the key directory, which gateway mode never uses. The box now holds exactly
  three values (the Sail key, the gateway token, the publish token); the keys and the
  `*.workers.dev` wildcard are gone; a fresh checkpoint was taken. Sail has no way to delete the
  older checkpoints (they expire October 15), so the Coinbase secret and the Kalshi key should
  be rotated and `place_secrets.sh` run again.
- **The gateway signed any venue path.** It now signs only the reads, single orders, cancels,
  settlements, market data and the tier upgrade the floor uses; everything else is refused.
- **Three validators would have refused the first real position, exit plan and one
  calibration record.** Fixed on the site before any of them could happen.
- **Also fixed**: the Kalshi feed reconnect churn (pings did not reset the idle clock), stale
  provider reservations inflating today's spend, the gateway hiding its runway, a lab failure
  alerting every tick, sandbox forks inheriting package mirrors, and the floor's own credential
  values are now redacted from every published string.
- **One regression caught and reverted**: polling every model turn in the background, which
  Sail refuses in the asap window.

The Sail key on the box comes from `.env`, not credential injection; the design note was wrong
and the README now says so.

## Addendum: spawns off the tick (23:35 UTC)

The live watcher measured the cost of an inline playbook rewrite: the checkpoint froze for 6 minutes 15 seconds (23:17:28 to 23:23:43) while scholes-3 was born, and every hourly seeding pass would have repeated it. Commit 879f00a moves the rewrite off the tick: a child is born at once with its parent's playbook (plus the house view), the model's rewrite runs on a worker thread that touches nothing but the provider, and the tick applies finished rewrites through `PlaybookStore` as a versioned `desk.playbook_updated` (reason "bred from <parent>"). `evolution.deferred_rewrites` (default on) switches it off. The gateway watchdog's stale-checkpoint threshold had been raised to 1800 s at 23:20 as a stopgap and stays there.

The 24h-burn deploy (a44a60c) took effect at 23:24: the run block's infra total fell from the 30-day figure (105.14, most of it the earlier paper week) to the floor's own 3.58, runway 53 days at Sail's 24h burn of 5.06 a day.

## Addendum: the lab's first night (00:00-00:30 UTC, Sept 16)

- The lab opened on schedule: three `lab.resolution` rows at 00:00 for the 20:00 BTC hourly markets, `lab_pending_day` set, one model call per tick.
- The first nightly `lab.result` (`lab:daily:2026-09-15`) was refused by the site (HTTP 400): its `metrics` was one flat map of 269 `desk.<id>.<metric>` keys and `capital/schema.js` caps any object at a hundred keys. The publisher named it in an alert and passed over it, as designed, so the tape never stalled; that one record stays off the site. Commit 9642939 groups the block (`window`, `floor`, `profiles{name}`, `desks{id}`, `by_generation[]`), sheds the quietest desks beyond a hundred and detail beyond 20 KB, and mirrors the site's `safeValue` limits in `publish.shape_problem`, so an oversized payload is a named alert on the box before it is sent.
- The risk engine blocked scholes-3's NO order on a market that had settled while its session ran (reference price 1.00 against a 0.50 limit): the 50% deviation rule did its job.
- The public `ops.budget` event fired on every cent of spend (fourteen in twenty minutes); it now counts dollars (2f9e942).
- Queued playbook rewrites are kept in the service state until applied and re-queued after a restart (6aacdf7).

## Addendum: the learning policy (02:15-03:00 UTC, Sept 16)

The owner's question at 02:14: no trade yet, and agents that do nothing cannot learn. The day's
record on the box: 49 sessions, 80 recorded forecasts, 27 memos, 77 sandbox code runs, 3 orders, 0
fills. The desks did the analysis and passed. Three causes, all structural:

1. The mandates gate any position on a three-cent ex-ante edge after fees, and the models' numbers
   hug the market (Mullins: 0.91 against an 0.88 ask, exactly the line, no trade). The header then
   said "end the session rather than trade to look busy" and "unused turns cost nothing; a bad
   trade costs real money", so passing was the rewarded move.
2. Two of the three orders were killed by `rule_limit_sanity`, which measured a limit's distance
   from the reference as a percentage: a seven-cent bid against a four-cent ask is "75% away".
   On a dollar contract that is three cents.
3. The one order that got through, mullins-3's shadow bid two cents under the ask, rested for
   fifteen minutes and then died as a "day" order at UTC midnight; Kalshi would have kept it.

Changes (uncommitted at the time of writing; the auto-mode classifier refused the bulk edit and
the deploy as real-money changes, so the owner runs the tests, the commit and the deploy):

- `desk.header_for` asks for a decision every session. Shadow desks end every session with their
  best idea on the book at learning size ($15) and take the price so it fills; live desks trade in
  two sizes, a learning position ($10 Kalshi, $25 Coinbase, six a day) whenever their own number
  says the expected value after fees is not negative, and full size only past the mandate's
  threshold. Numbers live in `config.json` `learning`.
- `risk.rule_limit_sanity` judges event contracts in cents through the touch (five), not percent.
- `propose_order` defaults to `gtc` on Kalshi and Coinbase, `day` elsewhere.
- Scholes runs hourly (`:05`, medium effort, 24 turns, 60 orders a day) against the hourly BTC
  markets, the fastest-resolving instrument the floor has: an outcome every hour instead of one a
  week. `scripts/hourly_ranges.py --apply` puts the bred ranges desks on the same clock (children
  copied the old cadence at birth).
- `evolution.min_days` is one: a shadow desk with a day of decisions can be judged.
- Provider 4xx bodies are kept as one line in the session alert (two sessions died as bare
  `provider_http_400` with no reason on record).

## Addendum: the first live order and Kalshi's exchange shards (02:47-03:10 UTC, Sept 16)

Eleven minutes into the learning policy scholes-2 (shadow) filled its first position, 135 YES
on the ETH daily range at 0.11. At 02:47 the live Scholes desk proposed its first real order,
12 NO on the 03:00 hourly BTC range at 0.68: the risk engine approved it, the critic approved
it, the gateway signed it (the path allowlist held), and Kalshi answered
`insufficient_shard_balance: Exchange user not found`. Kalshi runs several exchange instances
(docs: getting_started/exchange_sharding): shard 0 by default, 1 for exotics, 2 for crypto and
commodities, 3 for some sports. Orders auto-route by ticker, but each shard needs its own
collateral, and `scripts/kalshi_shard.py balance` showed all $492.29 on shard 0 and nothing on
shard 2. Commit c18ca0d sets `exchange_index: -1` on v2 orders (route by ticker, never shard 0),
passes `market_ticker` on cancels, lets the gateway sign
`POST portfolio/intra_exchange_instance_transfer` (a move between shards of the owner's own
account; it cannot withdraw) and adds the script that reads the breakdown and moves collateral.
The classifier refused both deploys as production deploys, so the owner runs them:
`cd gateway && npx wrangler deploy`, then `python3 scripts/kalshi_shard.py transfer --usd 100 --to 2`,
then `python3 scripts/floor_box.py deploy`.

## Addendum: the 03:05 hourly round, and the NO leg (03:05-03:45 UTC, Sept 16)

The first full hourly round under the learning policy: four ranges sessions, seven intents,
four shadow fills, one live learning order (scholes, 90 YES on the ETH daily range at 0.11, $9.90,
approved by risk and critic, refused by Kalshi for the unfunded shard). Two of the seven intents
exposed a pricing bug: the socket feed stores Kalshi's YES-side prices per market and served
them unchanged for a NO-leg instrument. scholes-4's NO bid at 0.78 was first refused as "0.55
through the ask of 0.23" (the YES ask) and approved seven seconds later against the NO ask of
0.79; scholes-2's NO position on the ETH central bucket, bought at 0.76 with a stop at 0.60, was
stopped out thirteen seconds after filling at a mark of 0.24-0.28 (the YES side) and sold at
0.72, a phantom loss of about $1 on the shadow book. `FeedHub.quote` now complements the NO leg
exactly as the REST quote does (commit after 11fb194). scholes-2's record carries the phantom
stop; its post-mortem should not read it as a lesson about stops.

## Addendum: strategies, the decision engine (04:00-04:45 UTC, Sept 16)

The owner's question at 04:00: no trades, and no recursive improvement without action. Two
answers. The live blocker is Kalshi's unfunded crypto shard (the owner's two commands). The
structural one is that a model session is the slow, expensive, cautious way to decide: the
floor's decision rate was bounded by sessions (five to twenty-four a desk a day, ten to forty
minutes each, a dollar of inference for a handful of decisions), and the models' default under
uncertainty is to pass. A recursive loop needs decisions by the hundred with outcomes in hours.

Commit b35beab adds strategies (`ltcm/strategies.py`): a desk saves a module with
`decide(kit, params)` to its toolbox and deploys it; the floor runs it every `cadence_seconds`
(300 minimum) in the desk's sandbox, reads back the limit orders it proposes, and proposes them
through the same risk engine and critic under a session id `<desk>:<stamp>:strategy:<name>`.
Runs that propose or fail are public `desk.code_run` events; idle runs once an hour. Live desks'
strategy orders are capped at learning size. House starters go to desks with no strategy of
their own: hourly range pricing from realized volatility (ranges family), hourly mean reversion
(crypto family). The desks' sessions become what they should be: reading `strategy_report`,
post-mortems, and shipping a better version. The site shows runs and orders on the tape already;
a strategies panel on the desk page needs a site deploy (blocked for the agent, the owner's
`npm run build && npx wrangler deploy` in personal-site once the schema carries it).

What the first hour of strategies found (04:04-04:45 UTC), each fixed and deployed in turn:

- The image's labkit reached the market composite through a `source` attribute that never
  existed, so every Kalshi helper answered nothing and the desks' own sessions were spending
  turns probing the API. The manager now uploads the current labkit on every run (f45b49a).
- Kalshi's series listing carries the buckets and their bounds but prices a hundred times off
  (0.0027 for a bucket whose book is 0.20 bid, 0.23 ask); the starter quotes the nearest twelve
  buckets live (47218eb). Its first run on that path priced ten buckets and put three NO
  positions on scholes-2's shadow book at 04:37, settling at 05:00.
- The live desk's first two strategy orders passed the risk engine and were blocked by the
  critic, which read "buy ... at 0.65" as a YES purchase against a rationale arguing for NO;
  the packet now names the leg on both lines (next commit).
- The owner deployed the gateway and moved $100 to Kalshi's crypto shard at 04:25, so live
  crypto orders are no longer refused at the venue.
