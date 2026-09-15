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
