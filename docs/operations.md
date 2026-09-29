# Operating the options House

How to pause, deploy, roll back, inspect and recover the House, the gateway, the data box and the
Gym, and the switches that govern them. The design is in [design.md](design.md). Commands run from
the repository root on the owner's machine unless they say "on the box". Sections that depend on
the swarm or live path describe their implementation, not evidence that production trading is
enabled. Current direction is in [the goal](goals/LTCM_OPTIONS_SWARM.md); the old operator's page
is [archive/docs/operations.md](../archive/docs/operations.md).

## Current operation and next work — September 26, 20:10Z

The House is healthy on release `20260926T181814Z-b4bc25619f84` (`60b34dd9`), with real money off,
no enabled live grant and no production options orders/positions. Training is running on five
roots. At 20:01Z there were 16 active families, 17,631 trials, no validation passes and no holdout
looks. The gate is disabled pending final data/image adoption. These are observations, not a
readiness promise for Monday.

The owner's new priority is broad, rapid options research: simple and complex strategies, all
Alpaca-supported securities discoverable, data readiness recorded by root and expiry, and a real
agent paper-testing environment. Current limits are five actively trained roots, 11 simulator
types, no covered-call/cash-secured-put inventory, and a single SPY paper connectivity proof.
Changing a prompt, symbol list or allowlist does not implement the missing mechanics.

In order: finish and verify the 25-root data batch; adopt only the final sealed/restored images;
broaden strategy exploration and the paper order/accounting path; finish execution receipts and
reports plus the funded post-burst budget; verify the Monday paper/shadow session. Keep paper,
shadow and real outcomes separate. No new real-money activation occurs in this engineering
continuation. Existing instructions below for grants describe the mechanism, not current state.

At this checkpoint #378 (complete universe context), #379 (shadow restart flags) and #380
(role/Flex routing and durable spend reservations) are merged, not deployed. Main is `e73e7740`;
#380 merged at 20:05Z after full CI, independent review and 221 actual-House tests. Execution
reporting (#381) and lifecycle changes are still under review. Re-read main,
open PRs and the running release before acting; a document timestamp is not a fresh health check.

The existing ThetaData collector owns the only account session; preserve it while it downloads.
Do not log in again or launch a duplicate collector to widen the universe. New discovery belongs
in a data backlog until coverage and capacity are verified. Retain funded caps: Sail reserve $32,
Sail researcher-model pace $2.25/hour, OpenAI September cap $707, no October allowance. The planned
larger deposits are not confirmed funding.

No trading-day deploy 13:25–20:05Z except rollback. The full prune remains after Monday September
28 at 20:05Z, with fresh integration/review of these additions. First actual nightly forward job:
Tuesday September 29 at 06:00Z; the Saturday rehearsal does not satisfy it.

## What runs where

| Piece | Where | Driven by | Local record (gitignored) |
|---|---|---|---|
| The House (`python3 -m league run`) | Sailbox `ltcm-floor`, size s, `/workspace` | `scripts/floor_box.py` | `.data/ltcm/box.json` |
| The gateway (venue, OpenAI and GitHub keys, caps, kill switch, outside watchdog) | Cloudflare Worker `ltcm-gateway` | `gateway/`, `scripts/gateway_admin.py` | `.data/ltcm/keys/gateway-admin.token` (owner only) |
| The data box (ThetaData downloads, the store) | Sailbox `ltcm-data`, size l, `/data` | `scripts/data/box.py`, `nightly.py` | `.data/gym/data_box.json`, `universe.json` |
| The Gym and gate images | Sail checkpoints (two each, one-year TTL) | `scripts/data/images.py` | `.data/gym/images.json` |
| Gym boxes and the gate box | sealed forks of the images | the swarm's pool (`league/swarm/pool.py`) | the House's state |
| The public page | blakewoods.us/capital (`~/Work/personal-site`) | the House's publisher | - |

Owner deploys run from the checkout `~/Work/ltcm-deploy`. Its `.data` is a symlink into the main
checkout's `.data` (the box record and the admin token): never `ln -sfn` over it.

## Rules that hold every day

- **No deploy from 13:25Z to 20:05Z on a trading day** (or from five minutes before the open to five
  minutes after the close when that is wider: 14:25-21:05Z in winter), except a rollback. That
  covers the House, the gateway and the site.
- **A merged PR is not a deployed feature.** Verify on the box, in the change's window: the release
  id in `floor_box.py status`, the ledger rows the change should write, the behaviour itself.
- **A deploy does not start a stopped loop**; `floor_box.py start` does.
- **The in-box updater is off** (`auto_update` false in `league/config.json`, and a missing key now
  means off). Every release is an owner deploy until the owner turns it back on.
- **Ratify at promotion, not later**: a deploy that moves the money digest leaves the grant inactive
  until `live_trading.py --ratify`.
- Run `date -u` before writing any time; take event times from the box.
- Never chain a deploy on another command's exit code (a grep, a filter): run the tests, read the
  result, then deploy.

## Pause, resume, stop

```sh
python3 scripts/floor_box.py maintenance on --reason "why"   # pause: paid work and new entries stop
python3 scripts/floor_box.py maintenance status
python3 scripts/floor_box.py maintenance off                 # resume on the next tick
```

`maintenance on` writes `/workspace/state/PAUSE` with the reason; the House keeps ticking.

- **What stops:** paid model work, replays, births, promotions and every new entry.
- **What goes on:** reconciliation, marks and publishing; agents holding a position are still
  woken, and their exits and cancels reach the books; work in flight defers at its next paid turn.
- **The swarm and the Gym under a pause:** (to be completed when the swarm lands).

`python3 scripts/floor_box.py stop --reason "why"` writes both stop files (`/workspace/STOP`, the
supervisor's, and `/workspace/state/STOP`, the House's), sends TERM, waits up to 120 s for the tick
in hand, then stops the supervisor. It ends every exit with the loop: prefer `maintenance on`.
`start` clears both files and starts the supervisor, which runs the House from
`/workspace/current` and restarts it 30 s after it exits.

Neither command touches real money. To stop real orders at once, whatever the House does:
`python3 scripts/gateway_admin.py kill` (below, **Real money**).

## Deploy

**The House.** In `~/Work/ltcm-deploy`, check out the exact commit to ship (detached, `git status`
clean: `deploy` sends the working tree), then:

```sh
python3 scripts/floor_box.py deploy              # wait for the verdict (up to 1500 s)
python3 scripts/floor_box.py deploy --no-wait    # launch and return; `status` has the verdict
```

The release is the whole tree (`league/`, `ltcm/`, `scripts/`, `deploy/`, `playbooks/`; never
`docs/`, `archive/` or `.data/`), named `YYYYMMDDTHHMMSSZ-<12 hex of its sha256>`. The in-box
watchdog (`league/watchdog.py`) then:

1. **stages** it as `/workspace/releases/<id>/`;
2. runs a **canary**: 3 ticks of a whole House on throwaway state with a simulated paper venue, no
   publishing, no research and no real money. An error, a traceback, a timeout or bad health
   refuses the release and leaves `current` alone;
3. **promotes** it (`previous` := old `current`, `current` := the release) and restarts the House;
4. **watches** `health.json` every 30 s for 10 minutes and, after a grace of two readings, rolls back
   on the first bad one: a stale `health.json`, a tick that raised, a frozen book, a health failure
   or an unmarked error alert.

A condition that began before the promotion is inherited, reported and never a rollback. **A
vendor's outage never rolls a release back**: an error the House raised because Sail, the site, the
gateway or GitHub failed on its side carries `environment: "<service>"` and is only counted
(`detail.environment_alerts` in the watch rows). Nothing on the trading path is ever marked.

`deploy` exits 0 for promoted, 2 refused, 3 rolled back, 4 failed with nothing to roll back to, 1 no
verdict seen. Only one deploy runs at a time: `REFUSED: another deploy or rollback is running (pid
N)` means wait for that watchdog (`status`) and deploy again. With the loop stopped there is no House
to watch, so the watchdog canaries and promotes only; then `start`.

**The first release on the new state root.** The old House's state was moved aside on Sept 26; the
new House starts on an empty `/workspace/state` with `real_money` false. Its first owner deploy
makes the watchdog's `previous` a release of the new era. **Never roll back past that release**:
the release before it (Deploy G, `20260926T032739Z-aaf5ac74637c`) would run the old Kalshi and Jev
code on the new root. [CHANGELOG.md](../CHANGELOG.md) records the release id.

**A money rule.** The grant pins `constitution.money_digest()`. Changing a money rule takes three
steps: change `league/constitution.py` and re-pin `PINNED_DIGEST` in the same commit (a test checks
it); deploy it with the owner's deploy; at `promoted`, run `python3 scripts/live_trading.py
--ratify` at once. To see whether a tree moves the money digest:

```sh
python3 -c "from league.constitution import digest, money_digest; print(digest(), money_digest())"
```

and compare the second with the grant's `constitution_digest` (`python3 scripts/live_trading.py`
prints it).

**The gateway.** In `gateway/`: `npm run check && npm test`, read the result, then `npx wrangler
deploy`. Deploy the gateway before a House release that needs its change. After a deploy, read
`python3 scripts/gateway_admin.py status`. Caps and `OPTION_STRUCTURES_REAL` change only this way.

**The site.** In `~/Work/personal-site`: `npm test`, then `npm run build && npx wrangler deploy`
(its `DEPLOYMENT.md` has the details). When the publisher's schema or a bound changes, the site
deploys first: it refuses a whole checkpoint for one field it does not allow. The one exception is the
positions table (`positions`, Sept 28, 2026): refused, the publisher posts the checkpoint again without it
and offers it again half an hour later (a warning per distinct reply of the site, "positions table: the site
refused the positions table (old site, or a row it rejects) ... (the site said: ...)"), so either may go
first. The planned order for this first release: the House, then the site.

**Checkpoint the House box before risky work:** `python3 scripts/floor_box.py checkpoint --name why
--ttl-days 30` (`checkpoints` lists them). A checkpoint holds the box's `.env`. Sail's checkpoint
API failed twice on Sept 26 (06:35Z and 07:00Z, HTTP 503); the old state's archive is a tarball
instead.

## Roll back

```sh
python3 scripts/floor_box.py rollback --reason "why"
```

It asks the in-box watchdog (`current` := `previous`, restart) after the structures guard below.
Only when `floor_box.py` cannot reach the box, on the box and with no guard:

```sh
cd /workspace/previous && /workspace/.venv/bin/python -m league.watchdog rollback --base /workspace --reason "why"
```

- **Never past the first release of the new era** (above).
- **After a rollback across a money-digest change**, re-ratify at once on the restored release:
  `python3 scripts/live_trading.py --ratify`. Until then real entries are refused.
- **Structures.** `rollback` and `deploy` refuse a target release that cannot hold structures while
  the practice account's ledger shows a structure held or an order open, or cannot be read.
  `--force-structures-risk` overrides it; use it only when the venue itself shows the account flat
  of option legs. Never roll back to a release that cannot close a structure the real account holds
  in one multi-leg order: close it first, or roll forward.
- **The real book** (the sprint, Sept 26, 2026). `rollback` refuses while the box's `live.sqlite` shows a
  real position held or a real order working and the previous release has `real_money` false (it builds no
  real account: the positions would sit unmanaged) or lacks the long-single code (it cannot close a long
  call or put; a same-day long call could be exercised into 100 shares the account cannot carry).
  `--force-real-risk` overrides it. **Close the real positions, or roll forward, before a rollback.**
- **The gateway:** `npx wrangler rollback` in `gateway/`. **The site:** the same in
  `~/Work/personal-site`.

## Inspect

- **`python3 scripts/floor_box.py status [--json]`:** the box, its spend and rate, whether the egress
  allowlist matches the record, the supervisor and the House, both stop files, `current` and
  `previous`, the last line of `deploys.jsonl`, `health.json` and the log tail.
- **`python3 scripts/floor_box.py logs -n 200`** (`/workspace/league.log`); **`logs --deploy`**
  (`/workspace/deploy.log`, the last deploy).
- **On the box:** `tail -n 40 /workspace/deploys.jsonl` (every stage, reading, verdict and reason);
  `/workspace/state/health.json` (written every tick); the ledger read-only,
  `sqlite3 'file:/workspace/state/ledger.sqlite?mode=ro'`; `cd /workspace/current &&
  /workspace/.venv/bin/python -m league.watchdog status --base /workspace`.
- **The grant:** `python3 scripts/live_trading.py` (no flag) reports it and what enabling would
  record now.
- **The gateway:** `python3 scripts/gateway_admin.py status`: the kill switch, today's order
  counters, the OpenAI month (spent, settled, in flight, the cap), the Claude meter (the funded total,
  spent, in flight, remaining, the priced models, spend by role such as `researcher`), the Sail balance
  and the House box's state.
- **Claude's top band** (Sept 29, 2026): each `swarm.cycle` event of a family on Claude carries `route:
  "claude"`, `claude_calls`, `claude_usd`, `claude_usage` (input, cache write, cache read and output
  tokens summed over the cycle) and, when a turn fell back to Sail, `claude_fallback` (`<kind>: <why>`).
  The swarm's own `spend` rows (kind `claude`, `detail.role` "researcher") hold the holds and their
  settlements; `kv claude_unsettled` lists holds whose bill is not yet known.
- **The public page:** `curl -s https://blakewoods.us/api/capital/checkpoint`: 404 until the House's
  first checkpoint after the reset, then its `published_at`.
- **The data:** `python3 scripts/data/box.py status` (the box, its egress, the backfill's progress);
  `python3 scripts/data/box.py run -- check.py report` (underlying-days by window and root, the
  queue, the rate); `python3 scripts/data/images.py status`; `python3 scripts/data/nightly.py status`.
  Numbers derived from the data stay on the boxes and in `.data/`.
- **The swarm and the scoreboard** (families, trials, validation passes, holdout looks, Gym
  throughput, compute against the budgets): (to be completed when the swarm lands).
  `scripts/floor_watch.py` is being rewritten for the options scoreboard; until then use `status`,
  `health.json` and the ledger.

## The data box, the images and the Gym boxes

The data box holds the ThetaData key in `/data/secrets/thetadata.env` (0600) and nothing else
secret. Its egress is the two ThetaData hosts (PyPI only during `setup`).

```sh
python3 scripts/data/box.py status              # the box, its egress, the backfill's progress
python3 scripts/data/box.py start [--stages 1,2,3,5,6]   # the backfill in the background; resumable
python3 scripts/data/box.py stop                # stop it (it resumes from its journal)
python3 scripts/data/box.py slots N             # how many of ThetaData's four requests it may use
python3 scripts/data/box.py sleep [--wake-at ISO]
python3 scripts/data/box.py run -- ARGS         # run backfill.py ARGS (or check.py ...) on the box
```

- **ThetaData allows one session per account.** A login anywhere else kicks the box's session:
  nobody else authenticates while the backfill runs. Every file is journaled with its sha256, so a
  kicked or stopped backfill resumes where it stopped.
- **Sleep the data box, never pause it:** a paused box cannot wake on a schedule.
- **Images.** `python3 scripts/data/images.py build gym|gate [--version vN]` stops the backfill,
  checkpoints the data box, restarts the backfill, forks, seals the fork (`no_network`) before
  anything runs on it, prunes it, verifies from inside and checkpoints it twice with a one-year TTL.
  The Gym image has no key, no holdout and no forward days; the gate image has no key but has both,
  and carries the `GATE` mark. `images.py verify gym|gate` re-checks one. Either image can be rebuilt
  from the data box at any time.
- **The nightly forward job.** `python3 scripts/data/nightly.py run [--day YYYY-MM-DD] [--dry-run]`
  pulls the last trading day (from 01:45 ET) into the data box's store and the gate image only,
  stopping and restarting the backfill around it, re-checkpoints the gate and puts both boxes to
  sleep; `nightly.py schedule` sleeps the data box until the next 06:00Z wake. It is idempotent:
  rerun it after any failure. It refuses the Gym image's box as a target.
- **Gym boxes** are forks of the Gym image checkpoint, sealed, driven through Sail's file and exec
  APIs (`league/gym/driver.py`, `python -m league.gym.batch` on the box). The swarm's pool starts
  four when there is work, grows to eight, sleeps a box after ten idle minutes, and the Sail guard
  brakes it to zero before the House is at risk. Operating them: (to be completed when the swarm
  lands).

## Real money

Real money is off until the live path lands: `real_money` is false in `league/config.json`, and the
House sends no real opening order without an active grant.

**The grant** `options-swarm-20260928`, the Brokerage Account only, lives on the box in
`/workspace/state/live-grant.sqlite`. The House reads it at every check, so nothing restarts.

```sh
python3 scripts/live_trading.py              # report
python3 scripts/live_trading.py --enable     # create it; capital = min(equity, live_trading.ceiling_usd)
python3 scripts/live_trading.py --ratify     # re-pin to the current money digest; capital read afresh
python3 scripts/live_trading.py --disable    # revoke for good: no new real entry; exits go on
```

Ratify within a minute of any promotion that moves the money digest, when a deposit lands (capital
rises up to the ceiling), and after a rollback across a digest change. A revoked grant is never
reactivated; a new one needs a new id. The old grant `earned-live-20260921` was disabled at
06:25:00Z on Sept 26.

**The kill switch** stops every order-creating call on the real account at the gateway, exits
included; reads and cancels pass, and the paper account is unaffected.

```sh
python3 scripts/gateway_admin.py kill      # any holder of the gateway token may stop
python3 scripts/gateway_admin.py unkill    # the owner's admin token only, from the owner's machine
python3 scripts/gateway_admin.py status
```

A kill the run engaged may be released once its cause is fixed and verified; tell the owner at once
either way.

**The live path** (`league/live/`, Sept 26, 2026, Wave 5) is `House.options_live`, on when `config.json`
`live.enabled`. Once a minute in the session (a few seconds past the minute) it reads each needed root's
chain through the gateway, steps every Candidate's shadow book (the Gym's own engine, one minute behind
the wall clock), reads the Brokerage Account (equity, orders, positions, option events, funding) and
sends Probe and Sized families' orders sized by the constitution's `options_money` table. It owns both
Alpaca accounts: no old `Book` is built for them. Its state is `/workspace/state/live.sqlite` (the real
book: every order written before it is sent, positions by family, fills, the stops, the counters) and
`live-shadow.json`; programs run in a child process (`live-decider.log` beside them). The House box needs
numpy in `/workspace/.venv`. `health.json` carries its block (`options_live`: the last minute, what shuts
real entries now, the stops, reconciliation, the paper proof, every instance).

On the root House, the decider runs under host uid/gid 65534 with no supplementary groups, in a
mandatory private network namespace. Its runtime is a root-owned read-only source copy under `/tmp`;
the production env stays root-owned mode 0600 and the state/deploy directories must not be writable
by other users. Local runs as an ordinary user retain that user's file permissions. The real and Candidate
programs share one child and one memory allowance (2 GB), so a hung or exhausted child can cost all of them
that minute; the observe band's programs run in a second child (1 GB), asked after the real decisions. A
minute whose budget is spent skips a request without killing a child.
Loads, pipe writes, decisions and recovery share at most 40 seconds, clamped to five seconds before
the next minute. Recovery after a timeout happens within a later request's budget.

```sh
python3 -m league.live --root /workspace/state                        # the live state: stops, freeze, proof, positions, orders
python3 -m league.live --root /workspace/state --release-drawdown     # owner: lift the drawdown stop's pause
python3 -m league.live --root /workspace/state --clear-assignment     # owner: lift an assignment's freeze by hand
```

Real entries need all of: `real_money` true; the grant active on the running money digest; the kill
switch off; no stop tripped (daily 35% of start-of-day equity, drawdown 60% from the peak since the
reset, deposits netted, a pending deposit or withdrawal settling nothing); reconciliation clean (two
readings in a row that disagree freeze entries, two clean ones lift it; the LTC dust is known); no
unresolved assignment; the paper proof passed (for a long call or put, the single-leg proof too); the
House not paused. Exits need only the kill switch
off, and go first: an exit cancels another family's resting open on its contracts and waits for them.
A forced exit also cancels a blocking program close; ordinary exits do so after waiting two minutes.
Expiring equity structures with a leg in or within 1% of the money are the House's to close from ten
minutes before the close cutoff (15:00 ET for most roots, 15:15 for SPY and QQQ): a program's own
close is cancelled for the forced one; index structures settle in cash. An expiring long call or put is
the House's to sell there whatever its moneyness while it has a bid (never exercised: the account cannot
carry 100 shares). The last forced close before the cutoff is never cancelled for a re-price. A family moved onto real money
trades it from the next session; a Candidate whose typical maximum loss is unknown stays shadow-only
(`live.band` rows with `held` say why, once a day). A Probe becomes Sized only after five real Probe
trades and a whole session at Probe. Each real instance has 60 orders a day (the Gym's), charged for
orders that reached the venue and checked for opens only: an exit is never refused on it. A program's
closes (and cancels of its closes) keep room for the House's own exits under 250 legs, and the gateway
stops opens at 250 orders while exits go on to 300. An exit waiting for its contracts is kept across a
restart and dropped at the day's end (its program is told).

Money-band decisions commit only while the selected version and its forward evidence still match.
Promotion time commits in that same swarm transaction, so a crash cannot bypass the next-session
wait; a legacy row without a known promotion time starts its wait at the House's first sighting.
When executed funding changes, the House rereads equity between matching funding histories before
latching a stop. An account read taken before that transition is only provisional.

Demotion, retirement and an unavailable program cancel the instance's working opens. Programs kept
for exits still reload after a decider failure; five minutes without recovery makes their positions
orphans for the House to close. Closed real trades are acknowledged individually, so an older
position that closes late cannot be lost behind a newer trade's export. After expiry, external
liquidation fills reconcile the missing legs and fees, including remaining legs of a broken structure.
Consumed quantity and value are persisted together, so a later cumulative fill price cannot reprice
contracts already attributed to another family. Missing fill values leave an explicit
`unpriced_close` row, release stale exposure and block new entries until venue fills or expiry events
resolve the accounting; estimated intrinsic values never become forward evidence.

The checked-in deployment remains in paper readiness: `real_money: false`, no enabled grant, and
the gateway's `OPTION_STRUCTURES_REAL: off`. The gateway still admits paper structures and verified
closes of held real positions. A disabled gateway is a permitted stricter setting in `league.ci`.
The paper route proof runs from 09:35 ET during this readiness stage, even with no real-account
client, grant or eligible family. It keeps an unfinished attempt's identity and owned contracts
through restarts. Passing records paper execution evidence; the real-money flags remain off.

**The money table (the sprint, owner decision D4, Sept 26, 2026)**: real types under $2,000 of equity are
exactly `debit_vertical`, `long_butterfly`, `long_call`, `long_put` (the credit types come back only with a
deposit to $2,000, in one deploy with the gateway, and a re-ratified grant); Probe 5% of equity a structure
with a $100 one-contract floor, 3 open, 15% the family; the book 90%; daily stop 35%, drawdown stop 60%;
tuition $200 a day; the D3 calibration's day bounded at $50 of possible loss. The gateway's per-order cap is the lower of
$1,000 and 25% of equity (a $100 Probe fits at $481.63), 100% of equity opened a day, 250 of 300 orders open.

**The single-leg paper proof**: once the vertical's has passed, the practice account opens and closes a
1-lot SPY call about 1-2% out of the money (nearest expiry at least a day out, at the natural, held two
minutes) with single-leg orders. Real long calls and puts open only after it (`paper_proof_single`).

**The observe band**: every alive Gym-band family's validated version trades the shadow book as
`<family>@<version>:o`, its version pinned for the session (pins in `live.sqlite`), never real, never a
forward row, never on the site. Its programs load and decide after every real decision of the minute, in
their own decider child (1 GB); its chains are read after the real path, under the minute's data budget.
Its trades are kept in `/workspace/state/observe.sqlite` (0600) for the post-mortem only.

**The D3 calibration round trips**: 1-lot SPY, QQQ and IWM call verticals one dollar wide nearest the
money, hourly at 10:00, 11:00, 12:00, 13:00, 14:00 and 15:00 ET (none starts from 15:15); open at the mid
for 5 minutes -- at 12:00 and 14:00 the patient cell `mid25`, the mid for 25 minutes -- then once at the mid
plus a tick (its own cell `mid25+1` after the patient open), only after an open its time in force ended;
close at the mid, a tick under, then the natural (at most six close attempts a position a day, backing off
after a refusal; every ladder, at its slowest, is sent before the 15:45 last resort). One round trip at a
time, within a strict $50 bound on the day's possible loss: a new open goes only while today's realized
calibration loss (net, floored at zero) plus what is still held or working plus its own maximum loss stays
within $50; a closed round trip frees its maximum loss. What it leaves the families: every calibration open
leaves two Probe floors ($200) of the account-wide day cap (1.0 x sizing equity, which every dispatched open
fills by its whole maximum loss, cancelled ones too); no round trip starts once its own legs today (orders
and cancels) reach 80 of the day's 250 (a round trip is 4 legs when both mids fill, about 30 at its
slowest, so at most about 110 before the House's backstop); and a working open whose contracts a family's
real open was refused on is cancelled at once, its round trip ended (recorded `interrupted`). An attempt
cancelled before its time in force ran out (a real-entry block, the House's cancel, that yield) is
`interrupted`: never a sample, never in a fill rate. Only with real money on, the grant active, real
entries open and the paper proof passed; family `house:calibration`, never evidence; in Profit since Sept 28, 2026, as the positions table's "House
calibration" rows (`league/trading_profit.py`; the table must add up to Profit). The owner's written D3 terms (`league/constitution.py`'s
comments) say 1-lot SPY and QQQ; IWM and the six slots' volume (about $430-540 of maximum loss dispatched
on a heavy day, against about $270 before) are the operator's decision inside D3's $50 net bound (Sept 28,
2026), the money table unchanged. Samples: `/workspace/state/calibration.sqlite` (0600; each row its
order's time in force and cancel reason), read with `python3 -m league.live --root /workspace/state
--calibration` (the plan, then every cell, `mid25`, `mid25+1` and the unsampled included: working minutes,
attempts, outcomes, fill rate, mean fill against the mid in ticks, median seconds to fill). Off by default:
`swarm.json` `{"live": {"calibration": true}}` turns it on.

**The House live test** (the owner, Sept 28, 2026; `league/live/house_test.py`; a new shadow-to-real route,
pre-registered in a private file whose sha256 is `c73e2d262b8d2e9493b53c427400ba7adc37490db8c981ddd96644fdb6977954`):
one frozen swarm program (1-lot debit verticals; private, only its hashes are public) runs as the House's own
real instance `house:rebound-live@0:h`, through the families' decider child and order path, only to measure its
real fills and P&L. Never a band, a promotion, evidence or a forward record; D2 unchanged.

- Bounds (the money table's `options_money.house_test`): one structure of at most $100 with fees, at most 3 held or
  working, its NET realized loss plus what is held or working plus the new open at most $300 at every open, no new
  open ever again once its net realized loss reaches $150 (from the book's fee estimates; Profit uses the broker's, so
  they can differ by cents), new opens only through its 20th session from the start and while its round trips are
  under 30. It leaves the families $200 (two Probe floors) of both the day cap and the book's cap, and opens nothing
  while its record (`/workspace/state/house-test.sqlite`) cannot be written.
- The families first: its intents go after theirs each minute, and its working open yields to a family order refused
  on its contracts after the open was placed (never to an older refusal). A position it holds refuses a family's open
  of the other side of that contract ("positions net across the account"), as any held position does.
- The same gates as the calibration (real money, the grant, the kill switch, the stops, reconciliation, the paper
  proof). Its losses count toward the account's daily and drawdown stops like any position's: a bad day for it can
  trip them for everyone.
- Its orders say "House live test (pre-registered)", never the program's note. Its positions are Profit, the positions
  table's "House live test" rows (`source` `house`, which `league/trading_profit.py` gives only this family).
- The program and its params: on the box at `/workspace/state/house-test/rebound-live/program.py` and `params.json`
  (directory 700, files 600, root's), placed by the operator's private upload script (`--apply`, through the Sail
  file API, never on a command line), and in `live.sqlite`'s `instances` row as every real instance's. Checked at
  every load: an identity mismatch (the hashes, the run sha) and it never runs, a restored instance fails for good and
  the House closes what it holds; any other load failure is retried as a decider failure.
- `health.json` `options_live.house_test` shows the files, the start (day, release, fill model), the sessions used, the
  round trips, the realized and possible loss, and a stop or end. Each order's quotes at submit and its outcome are in
  `house-test.sqlite` (an unfilled order ended by its time in force, the close cutoff for expiring contracts or the
  session's close is a full-window sample; any other end is "interrupted").
- Off by default: `swarm.json` `{"live": {"house_test": true}}` turns it on (only after the analysis script's sha256
  is pinned in the private addendum); off again sends it to exits only and cancels its working open within a minute.
- While it runs: no House deploy or restart inside the decision window the private pre-registration names (each load
  of its program is a `live.instance` "house test program loaded (fresh memory)" row; one inside that window, a
  decider-child restart or a skipped minute there is a deviation of the test, logged in the private addendum). Before a rollback
  past the release that carries it: switch it off and wait until it is flat (an older release would run it as an
  ordinary instance, export its trades as forward rows and show its positions as an agent's).

**Turning real money on** (M4b; the sprint's R2): the gateway deployed first (`OPTION_STRUCTURES_REAL`
`debit_vertical,long_butterfly,long_call,long_put`, `MAX_ORDER_EQUITY_SHARE` 0.25); then the owner deploy
with `real_money` true (a new money digest); `python3 scripts/live_trading.py --enable` (first time), then
`--ratify` within a minute. Then the House promotes Candidates that qualify to Probe within five minutes
(`live.band` rows). Real entries still require the paper route proofs' witnessed round trips.

### Monday's pre-open (12:00-13:25Z Sept 28)

1. **The box** (`python3 scripts/floor_box.py status`, then on the box): the loop and supervisor up;
   `health.json` `options_live.summary.state` is "before the open", `options_live.instances` lists every
   Candidate's shadow instance and every Probe's real one with no `error`; `/workspace/.venv/bin/python -c
   "import numpy"` works; `live-decider.log` has no traceback; `release` is the M4b release.
2. **The account** (through the gateway, reads only): equity, `last_equity`, `options_buying_power`,
   options level 3, multiplier; no open order; positions only the LTC dust (0.000373062); whether the
   deposit has landed (a `CSD` activity).
3. **The grant**: `python3 scripts/live_trading.py` on the box: `active` true, `constitution_digest` equal
   to the running release's money digest, capital = min(equity, `live_trading.ceiling_usd`). A deposit
   that landed: `--ratify` now (capital follows it up to the ceiling; above the ceiling is the owner's call).
4. **The gateway**: `python3 scripts/gateway_admin.py status`: `kill_switch` false; `max_loss` shows a
   fresh equity reading (it reads the account on the first open if stale), the per-order cap = the lower of
   $1,000 and 25% of equity, today's opening maximum loss 0 of 100% of equity; `caps.max_day_orders` 300; the
   deployed `OPTION_STRUCTURES_REAL` is `debit_vertical,long_butterfly,long_call,long_put`.
5. **The live state**: `python3 -m league.live --root /workspace/state`: `stops` not tripped (no
   `drawdown_tripped`), `reconciliation.frozen` empty, no `assignment_latch`, `paper_proof` absent or
   `passed`, no working orders, no open real positions but the ones expected.
5b. **The sprint's checks**: `health.json` `options_live.fill_model` names the refitted model (its `source`
   and `version`; `GYM_FILL_MODEL` or `/data/calibration/fill_model.json`, loaded once at the House's start);
   `options_live.observe.switches` shows observe on and calibration as intended; `swarm.json` reads as a
   JSON object; after 13:30Z `options_live.observe.pins` lists the session's families; after the proofs,
   `paper_proof_single` passed; after 14:00Z `options_live.calibration.slots` and
   `python3 -m league.live --root /workspace/state --calibration`.
6. **The Probe list**: `live.band` rows since Sunday (who became Probe or Sized and why; who stayed a
   Candidate and why: not through the holdout, a type real money does not open, a credit type under $2,000,
   a typical structure over the Probe's cap or unknown). It must match M4's list in the run record. Bands
   move only while real money is on and the grant active, and a family moved onto real money trades from
   the NEXT session: only families promoted before Monday's open trade Monday.
7. **The day**: Sept 28 is a full session (not a half day), no FOMC, CPI or jobs release; 0DTE expiries on
   SPY, QQQ, IWM, XSP and SPXW. No deploy from 13:25Z to 20:05Z except a rollback.
8. **At the open** (13:30-13:45Z): the paper proof (`live.paper_proof` "passed" in the ledger by about
   13:40Z; if "failed", read `paper_proof` in the live state and the proof's events before anything else);
   then the first real orders (`live.order`), the refusals (`live.refusal`: each says which rule), the day's
   order count against 250, `reconciliation.frozen` staying empty. Watch every 30 minutes: fills against the
   Gym's expectation, the stops, the index 0DTE cutoff actually enforced by the venue at 15:00 ET.
9. **To stop real money at once**: `python3 scripts/gateway_admin.py kill` (exits stop too; release with
   `unkill` from the owner's machine). `live_trading.py --disable` revokes the grant for good: not for a pause.

## Recover

- **The House is not ticking.** `floor_box.py status`: if a stop file is set and nobody meant it,
  `start`. The gateway's outside watchdog (every five minutes) runs `/workspace/restart.sh` when the
  production checkpoint is over 30 minutes old (at most once in 30 minutes) and resumes a paused or
  sleeping House box when Sail credit is above $10. It acts only once the site has a checkpoint:
  while the checkpoint route answers 404 it touches nothing.
- **Sail credits ran out.** Every box pauses, the House included. The owner tops up; then
  `floor_box.py resume` and, if the loop is down, `start`. The swarm's Sail guard is meant to stop
  the Gym and the researchers well before this.
- **A release was refused or rolled back.** Read the reasons in `deploys.jsonl` (or `logs
  --deploy`), fix the defect with a test, deploy again.
- **The grant reads inactive.** The money digest moved: ratify (above).
- **"publishing failed (... HTTP 400 {"error":"Invalid checkpoint."})".** The site refuses the whole
  checkpoint for one field it does not allow, and the page keeps the last one it accepted. Rebuild
  the body the House would post from `/workspace/state` (read-only) and run the site's validators
  (`capital/schema.js`) over it to find the field. Widen a bound on the site first and deploy the
  site before the House.
- **"positions table: ..." warnings.** The positions table and Profit are read from the live book and the
  account's own activity (`league/account_activity.py`). Each reason the table does not reconcile is said
  once: a fill or a fee on an order the live book does not hold (an owner's trade by hand, a lost answer),
  a finished order whose fills at the broker differ from the book's, an option event on a contract the book
  never held, a cash event the book never counts, the broker's cash for an assignment, an exercise or an
  index expiry the book settled against the book's own value, an activity of an unknown type; and "the
  table carries an unreconciled X", the line the page shows beside the rows. Nothing is hidden: fix the book
  or classify the type, and the line goes back to 0.00. Profit shows a dash (said once) while shares an
  assignment left are held, while the book has not taken an assignment, and while a broker fill on a
  contract the book still holds is unmatched. "position real:N cannot be described" or "open position
  real:N is not listed": the row is counted in the page's not-listed line. "could not be read": Profit
  shows a dash ten minutes after the last good reading (a restart keeps the last reading).
- **Sail's checkpoint API is down.** The House's backup fails as a marked vendor error (one error,
  then warnings at 30 min, 1 h, 2 h, 4 h, then every 6 h) and never rolls a release back. The images
  have two checkpoints each and `images.py` rebuilds them.
- **The data box's session was kicked or the backfill stopped.** `box.py status`, then `box.py
  start`: it resumes from its journal. A night's forward pull that failed: `nightly.py run` again.
- **A structure is left on the real account.** The gateway admits a close of any defined-risk type
  once the account holds every leg, whatever `OPTION_STRUCTURES_REAL` says; close it with one
  multi-leg order. Legging out is a last resort. An assigned short leg becomes shares: (to be
  completed when the live path lands).

## Switches

| Switch | Where | Now | What it does | How it changes |
|---|---|---|---|---|
| `real_money` | `league/config.json` | false | real orders at all | owner deploy (Wave 5) |
| `auto_update` | `league/config.json` | false | the in-box updater; a missing key means off | owner deploy |
| `live_trading.ceiling_usd` | `league/config.json` | 5500 | the grant's capital ceiling | owner deploy, then `--ratify` |
| `performance.start_at`, `start_equity` | `league/config.json` | 06:25:30Z Sept 26, $481.65 | the profit baseline; equals the site's `PERFORMANCE_START_AT` | only with a site reset |
| `gym.enabled`, `swarm.enabled` | `league/config.json` | false | the Gym and the swarm in the House's tick | (to be completed when the swarm lands) |
| `swarm.json` | `/workspace/state/` on the box | absent | the swarm's throughput and budget settings, re-read every loop, no deploy; never the evidence lines | (to be completed when the swarm lands) |
| `options_structures.book`, `practice_account` | `league/config.json` | options-shadow, false | which book structures practise on | owner deploy of a release changing only that key |
| `PAUSE` | `/workspace/state/` | absent | the maintenance pause | `floor_box.py maintenance` |
| `STOP`, `state/STOP` | `/workspace/` | absent | the loop ends | `floor_box.py stop` / `start` |
| Kill switch | the gateway | off | every real order-creating call refused | `gateway_admin.py kill` / `unkill` |
| `MAX_ORDER_MAX_LOSS_USD`, `MAX_ORDER_EQUITY_SHARE`, `MAX_DAY_EQUITY_SHARE`, `MAX_DAY_ORDERS`, `MAX_DAY_OPEN_ORDERS` | `gateway/wrangler.jsonc` | $1,000, 0.25, 1.0, 300, 250 | the real account's caps by maximum loss; equal to the constitution's `options_money.gateway` | gateway deploy with the matching House deploy |
| `OPTION_STRUCTURES_REAL` | `gateway/wrangler.jsonc` | `debit_vertical,long_butterfly,long_call,long_put` | the types real money may open; must equal the constitution's `options_money.real_types` (`league.ci`) | gateway deploy with the matching House deploy and a ratify |
| `live.observe`, `live.observe_max` | `swarm.json` on the box | true, 48 | the observe band and its cap; read each minute, no deploy (a swarm.json that is not a JSON object turns it off) | edit `swarm.json` |
| `live.calibration`, `live.calibration_samples` | `swarm.json` on the box | false, 30 | the D3 round trips (still only with real money on, the grant and the paper proof); samples a symbol's open cell (the mid, or the patient mid at 12:00 and 14:00) stops at | edit `swarm.json` |
| `live.house_test` | `swarm.json` on the box | false | the House live test (still only with real money on, the grant, the paper proof and its private program verified); off: exits only | edit `swarm.json` |
| The House live test's program | `/workspace/state/house-test/rebound-live/` on the box | absent | the frozen program and its params, hash-checked against `league/live/house_test.py` `FROZEN` | the operator's private upload script, `--apply` |
| `FRONTIER_MONTH_USD`, `FRONTIER_MONTH_MAX_USD`, `FRONTIER_FUNDED_MONTH` | `gateway/wrangler.jsonc` | $707, September 2026 only | the OpenAI month; expires before an unfunded month can renew it | gateway deploy |
| `CLAUDE_USD`, `CLAUDE_MODELS` | `gateway/wrangler.jsonc` | $100; Opus 5.5, Sonnet 5, Sonnet 5.5 | the Anthropic account's funded total (never resets) and the priced models (the allowlist) | gateway deploy after the owner adds funds |
| `claude.usd_cap`, `claude.role_usd_day`, `claude.roles` | `swarm.json` on the box | 100, `{"researcher": 100}`, architect, audit, diagnostician, researcher | the swarm's own lifetime Claude line, each role's line a UTC day, and who asks Claude first | edit `swarm.json` |
| The money rules | `league/constitution.py` | the sprint's D4 table and the House live test's bounds (money `a3e2aa7c`) | what real money may do | owner deploy, then `--ratify` |

In `swarm.json`, `researcher.usd_per_hour` keeps the combined Sail-model and OpenAI trailing-hour pace.
Set the optional `researcher.sail_usd_per_hour` to the funded Sail rate to pace Sail models separately;
absent or null keeps the combined behavior. OpenAI holds still count against its own burst cap and funded
gateway month. Invalid, nonfinite or negative limits pause research. The heartbeat's
`status.researcher_pace` reports the scope, limit, spend and pause reason, so a quiet research loop can be
distinguished from a publication delay.

A Gym researcher can call `retire(reason)` to abandon its whole family, but only on a READ turn while more
families live than `population.start` and the family has had at least two validations (Sept 26: an unguarded
retire on the REVISE turn took the population from 49 to 16), or while more live than `population.floor` and the
family is dead by the idle rule (R3, Sept 27; `researcher.idle_dead`): `researcher.retire_idle_evaluations` (default
150; 0 or null turns the rule off, in `swarm.json` without a deploy; a boolean or a non-number also reads as off) Gym
evaluations since its birth or last validation without an eligible Train version, or three times as many with its
best Train score below zero. It counts evaluations, not versions: the store keeps one version for identical code and
parameters, so a family re-running one placeholder makes trials but no revisions. A family whose validated version
awaits the gate (`gate_ready`) or whose holdout look is out is never dead. With the population held at its start,
dead families never qualified before and looped on placeholder runs (the operator retired 48 by hand on Sept 27). The
tournament retires a dead family that never calls retire by the same rule, down to `population.floor`; the
architect refills below `population.start`. The graveyard lesson and the public cause say the idle rule retired it
(a time limit, not a refutation); the family's own last notebook lines carry its verdict.

No duplicate runs (R3; the harness audit of Sept 28 found 44% of cycles wasted and 45% of trials identical
re-runs). A `gym_run` or `gym_sweep` variant a family already ran to completion (the same code, merged params,
stress, window, sorted roots, Gym image and engine, Train split and capital: its `eval_key`, kept in the run row's
summary with the result's fill model) is answered from the store, marked `already_run`: no Gym job, no trial, no
version, no revision, and the cycle's REVISE turn goes on. A failed run runs again, and so does a stored result on
another fill model than the one the Gym last returned (a calibration changed on a box in place) or one that can no
longer be scored. The key is coarser than the Gym's run_id on purpose: the Gym's day list is the union of its batch's
roots, so a stored result is the sample of the batch it ran in and is not run again for another batch. Data and the
fill model are the image's, so a new data set or calibration should come as a new image checkpoint (which is in the
key). A run that lands after the wait gave up is recorded with its Train score, so asked for again it is scored like
any run and can become the best. `researcher.reuse_results` (default true, `swarm.json`) false turns it off. A
REVISE turn may also call `gym_run` with `hold=true`: no run, no trial, a notebook line (its `note` only), and the
cycle ends; a run call after it in the same answer is refused, and code or params passed beside it are ignored. A
row recorded before R3 has no key: the next identical run is one more trial (the same Gym run_id, the same row) and
writes the key, and from then on it answers.

Because stored results and holds add no evaluations, the idle rule has a dormancy clause: a Gym family whose last
`researcher.dormant_cycles` (default 40; 0 or null turns it off) cycles made no new Gym evaluation, only stored
results, holds and runs refused for its own doing (its program, NEEDS, params or variants), is dead (the same floor,
gate exemption and graveyard wording), unless its best awaits validation (not yet validated and not lost at 1.5x).
A new evaluation of its own restarts the count as soon as it is recorded (in the cycle, or when a run lands after
the wait), and so does a counted validation. A cycle that asked the Gym for a new evaluation the Gym did not make (a
Gym error; a run, or every new variant of a sweep, that did not land) leaves it, and a sweep whose new variants all
failed is a Gym error even when some of its variants were read back from the store. A sweep refused for room leaves
it too, unless the cycle also held, got a stored result or had a run refused. The count is zero outside the Gym band,
and a Candidate sent back to the Gym starts afresh. A holding cycle is one model call, so 40 of them can pass in
well under an hour of a family's cycles; the count is the family's state `dormant_cycles`, and each dormant cycle's
`swarm.cycle` event carries it.

The operator's gate hold (R3): `python -m league.swarm hold-gate --root /workspace/state --family <id> --reason
"..."` (or `SwarmStore.hold_gate(fid)` from a shell on the box; a second connection is safe beside the running
swarm) sets `gate_hold` in the family's state. The gate then starts nothing for it (no review, audit or holdout
look; a hold set while a review is out stops the stage after it) and leaves `gate_ready` as it is; a look already
in flight is still judged when it lands. `--clear` releases it, and the next gate round looks at it. The gate
round's answer lists it under `held`; `python -m league.swarm status` (`gate_held`), the tournament's board and the
researcher's status say "held by the operator"; the public checklist shows `gate_paused`, since the site's list of
blockers is closed. Each hold and release is a private `swarm.gate` event with its reason. While a family is held
with `gate_ready`, no rule retires it: not the idle rule, not the tournament's revision, evaluation or deflated
Sharpe rules, not its own researcher and not the diagnostician (`SwarmStore.retire_gym` refuses it; `hold-gate`
answers `retire_exempt: true`). Its clocks keep running while it is held, so a family past one of those rules can
retire at a tournament round after the hold is cleared if the gate has not started its look by then (the gate
round comes every few minutes, the tournament hourly). A hold on a family without `gate_ready` protects nothing.
The hold does not touch tuition of a version whose review and audit already passed (`bands.read`).

Deploy impact (R3): the rule applies at once to every family that is already past it. On Sept 27 (start 72, floor
44, 74 alive) about 29 families were past it, nearly all long-refuted placeholders, so the first tournament round and
the dead researchers retiring themselves take the population to about 45 within minutes, and the architect's refill
(a handful of births a pass) takes hours to restore the start. To stage it, set `researcher.retire_idle_evaluations`
high in `swarm.json` before the deploy (for example 500, which catches only the longest loops) and lower it toward
150 over the following passes; the setting reloads each step. Retirement stops queued research, keeps the best
programs and every trial/look, and leaves existing positions under their exit owner. Researchers and the
tournament share the same atomic population-floor check. A refused retire (not offered, or the floor) is a plain
tool answer: no cycle error and no cooldown; it does not retire the family. The raw reason stays private in its
notebook and graveyard; the public event carries only filtered prose.

The sprint's search settings (Sept 26), all in `swarm.json` without a deploy: `researcher.top_profile` (default
`pro_asap`, null turns it off), `researcher.top_reasoning_effort` (`low`), `researcher.top_families` (10) and
`researcher.top_max_output_tokens` (12000) put the bandit's top ten on the stronger Sail profile inside the same
hourly pace; `architect.agenda` (default empty) closes every architect request as the operator's research agenda
(at most 4,000 characters); `population.reseed_max` (default 0, off) founds the seeds' mechanisms again on roots they
never tried while the population is below its start and the architect is not due; `tournament.require_robustness`
(default true) validates a version only after its 1.5x Train robustness run came back with a profit. The robust Train
objective, its robustness runs (1.5x and mid, at the pool's lowest priority, never starting or keeping a box awake) and
the D2 validation line are code, not settings. The objective's one-time migration beats the heartbeat while it runs,
skips a family it already moved and empties (never keeps) the best of a family it cannot rescore.

The top band on Claude (Sept 29, 2026, the owner's decision to use Claude Sonnet 5.5 boldly; only Sail and Claude are
topped up from now on), all in `swarm.json` without a deploy: `researcher.claude_top` (default 12; 0 turns it off)
puts the bandit's top families by weight on `researcher.claude_model` (`claude-sonnet-5-5`) at
`researcher.claude_effort` (`medium`), with `researcher.claude_max_tokens` (16000, streamed; it sizes each call's
hold) and `researcher.claude_timeout_seconds` (180), while "researcher" is in `claude.roles` (removing it turns the
band off). Four fuses bound the spend: `claude.role_usd_day.researcher` (default $100 a UTC day, holds included),
`researcher.claude_family_usd_day` ($15 a family a UTC day), `researcher.claude_min_room_usd` ($25 of the funded
room the researcher never takes, left to the architect, the audit and the diagnostician) and the gateway's
`CLAUDE_USD`; the swarm's lifetime `claude.usd_cap` counts the researcher's spend too. Any Claude failure (a refusal, a
cut answer, a 402 at the funded total, 403 for an unpriced model, 423, 429 or 5xx, a line, a fuse or the reserve, a
stream timeout, an input that does not parse or validate) finishes that turn on the family's own Sail profile
(`top_profile` for the top band) and keeps the rest of the cycle there; it is never a cycle error. The expected cost
at medium effort (a dry estimate on a real House cycle, Sept 29) is about $0.05 a cycle with a typical history and
$0.09 with a long one: about $60 a day at N=12 (capped at the $100 line) and $30 at N=6. Read the first day's
`claude_usage` and `claude_usd` from the cycle events after about 50 Claude cycles: above about $0.08 a cycle, drop to
`low` or `claude_top` 6; below about $0.04, consider `high` for the top six.

Before the band spends anything, the owner (none of this is done by the code): deploys the gateway with Sonnet 5.5
priced (#415) and this change's tool admission (a House call before that is a 403 or a 400 and falls back to Sail);
adds funds to the Anthropic account and raises `CLAUDE_USD` by what was added (a gateway deploy: with $22.77 left on
Sept 29, below `claude_min_room_usd` plus a hold, the band stays on Sail); raises `claude.usd_cap` in `swarm.json`
(98 on the box, $78.82 spent lifetime); and deploys the House release.
