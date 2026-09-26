# Operating the options House

How to pause, deploy, roll back, inspect and recover the House, the gateway, the data box and the
Gym, and the switches that govern them. The design is in [design.md](design.md). Commands run from
the repository root on the owner's machine unless they say "on the box". Sections that depend on
the swarm (Wave 4) or the live path (Wave 5) are marked **(to be completed when the swarm/live path
lands)**. Written Sept 26, 2026 for main after PR #359 (the House options-only); the old operator's
page is [archive/docs/operations.md](../archive/docs/operations.md).

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
deploys first: it refuses a whole checkpoint for one field it does not allow.

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
  counters, the OpenAI month (spent, settled, in flight, the cap), the Sail balance and the House
  box's state.
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
by other users. Local runs as an ordinary user retain that user's file permissions. One child and
one memory allowance are shared, so a hung or exhausted child can cost all programs that minute.
Loads, pipe writes, decisions and recovery share at most 40 seconds, clamped to five seconds before
the next minute. Recovery after a timeout happens within a later request's budget.

```sh
python3 -m league.live --root /workspace/state                        # the live state: stops, freeze, proof, positions, orders
python3 -m league.live --root /workspace/state --release-drawdown     # owner: lift the drawdown stop's pause
python3 -m league.live --root /workspace/state --clear-assignment     # owner: lift an assignment's freeze by hand
```

Real entries need all of: `real_money` true; the grant active on the running money digest; the kill
switch off; no stop tripped (daily 25% of start-of-day equity, drawdown 50% from the peak since the
reset, deposits netted, a pending deposit or withdrawal settling nothing); reconciliation clean (two
readings in a row that disagree freeze entries, two clean ones lift it; the LTC dust is known); no
unresolved assignment; the paper proof passed; the House not paused. Exits need only the kill switch
off, and go first: an exit cancels another family's resting open on its contracts and waits for them.
A forced exit also cancels a blocking program close; ordinary exits do so after waiting two minutes.
Expiring equity structures with a leg in or within 1% of the money are the House's to close from ten
minutes before the close cutoff (15:00 ET for most roots, 15:15 for SPY and QQQ): a program's own
close is cancelled for the forced one; index structures settle in cash. A family moved onto real money
trades it from the next session; a Candidate whose typical maximum loss is unknown stays shadow-only
(`live.band` rows with `held` say why, once a day). A Probe becomes Sized only after five real Probe
trades and a whole session at Probe. Each real instance has 60 orders a day (the Gym's), charged for
orders that reached the venue and checked for opens only: an exit is never refused on it. A program's
closes (and cancels of its closes) keep room for the House's own exits under 250 legs, and the gateway
stops opens at 250 orders while exits go on to 300. An exit waiting for its contracts is kept across a
restart and dropped at the day's end (its program is told).

Demotion, retirement and an unavailable program cancel the instance's working opens. Programs kept
for exits still reload after a decider failure; five minutes without recovery makes their positions
orphans for the House to close. Closed real trades are acknowledged individually, so an older
position that closes late cannot be lost behind a newer trade's export. After expiry, external
liquidation fills reconcile the missing legs and fees. Missing fill values leave an explicit
`unpriced_close` row, release stale exposure and block new entries until venue fills or expiry events
resolve the accounting; estimated intrinsic values never become forward evidence.

The checked-in deployment remains in paper readiness: `real_money: false`, no enabled grant, and
the gateway's `OPTION_STRUCTURES_REAL: off`. The gateway still admits paper structures and verified
closes of held real positions. A disabled gateway is a permitted stricter setting in `league.ci`.

**Turning real money on** (M4b): the gateway deployed with the caps by maximum loss and
`OPTION_STRUCTURES_REAL` set to the five types; a second owner deploy with `real_money` true (the
release carries the options money table: a new money digest); `python3 scripts/live_trading.py
--ratify` within a minute of it (`--enable` the first time). Then the House promotes Candidates that
qualify to Probe within five minutes (`live.band` rows), and the paper proof runs at the next session's
09:35 ET before any real order.

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
   $1,000 and 15% of equity, today's opening maximum loss 0 of 100% of equity, credit opens admitted only if
   equity >= $2,000; `caps.max_day_orders` 300; the deployed `OPTION_STRUCTURES_REAL` is the five types.
5. **The live state**: `python3 -m league.live --root /workspace/state`: `stops` not tripped (no
   `drawdown_tripped`), `reconciliation.frozen` empty, no `assignment_latch`, `paper_proof` absent or
   `passed`, no working orders, no open real positions but the ones expected.
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
| `MAX_ORDER_USD*`, `MAX_DAY_USD`, `MAX_DAY_ORDERS` | `gateway/wrangler.jsonc` | $75, $4,000, 2,000 | caps by notional; to become caps by maximum loss (live path) | gateway deploy |
| `OPTION_STRUCTURES_REAL` | `gateway/wrangler.jsonc` | off | structure types real money may open; must equal the constitution's list | gateway deploy with the matching House deploy and a ratify |
| `FRONTIER_MONTH_USD`, `FRONTIER_MONTH_MAX_USD`, `FRONTIER_FUNDED_MONTH` | `gateway/wrangler.jsonc` | $707, September 2026 only | the OpenAI month; expires before an unfunded month can renew it | gateway deploy |
| The money rules | `league/constitution.py` | Deploy G's (money `be1e3ce9`); the options table arrives with the live path | what real money may do | owner deploy, then `--ratify` |
