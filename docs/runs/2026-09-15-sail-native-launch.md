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
