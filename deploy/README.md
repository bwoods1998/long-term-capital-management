# Running the House

The House (`python3 -m league run`) runs on one trusted **Sailbox**: a small always-on Linux VM in
Sail's cloud. The MacBook is the operator terminal: it holds the credentials, it decides, and it
can be closed without the House missing a tick. Everything below is run from the repository on
the MacBook, and one script drives the box:

```sh
python3 scripts/floor_box.py --help
```

Box state (ids, the allowlist in effect, the releases sent and their verdicts, checkpoints) lives
in `.data/ltcm/box.json`. It is owner-only and contains no credential.

## The box

Everything is under `/workspace`:

| Path | What it is |
|---|---|
| `releases/<id>/` | one full code tree per release (`league/`, `ltcm/`, `scripts/`, `deploy/`, `playbooks/`), never edited again |
| `current`, `previous` | symlinks into `releases/`. Only `league.watchdog` moves them |
| `state/` | the House's state: the ledger, `health.json`, `STOP`, `sandbox.json`, caches |
| `canary/` | throwaway state for canary runs; the real state is never touched by one |
| `incoming/<id>/` | where an upload is unpacked before the watchdog stages it |
| `.env` | the three secrets, mode 600 |
| `.venv` | the interpreter |
| `run.sh`, `restart.sh` | the supervisor loop, and the one signal that restarts the House |
| `run.pid`, `loop.pid`, `deploy.pid` | the supervisor, the House, a deploy being judged |
| `league.log` | the House and its supervisor |
| `deploy.log` | what the watchdog said during the last deploy |
| `deploys.jsonl` | the watchdog's append-only record: every stage, reading, verdict and reason |

`/workspace/ltcm`, `/workspace/.data`, `/workspace/.archive` and `/workspace/ltcm.log` are the first
run's record. Nothing the script does for the league reads, moves, overwrites or deletes them.

## The steps

```sh
python3 scripts/floor_box.py create      # 1. the box, the network policy, the venv, run.sh
python3 scripts/floor_box.py secrets     # 2. the three values the box needs -> /workspace/.env
python3 scripts/floor_box.py deploy      # 3. the first release, through the watchdog
python3 scripts/floor_box.py start       # 4. start the supervised loop
python3 scripts/floor_box.py status      # 5. box, spend, loop, releases, health, log tail
python3 scripts/floor_box.py checkpoint --name before-<change>   # before anything risky
```

and then, for every code change afterwards, `deploy` again.

### 1. `create`

Creates one **size `s`** Sailbox (1 vCPU, 16 GiB memory ceiling, 32 GiB disk) from
`BASE_IMAGE_DEBIAN`, private to the owner's key, in the `ltcm` app. Then, in order: attaches the
egress allowlist, **reads the policy back from the live API and refuses to go on if it differs**,
builds `/workspace/.venv`, writes `run.sh` and `restart.sh`, and makes the directories above.

It uploads no code and leaves the loop **stopped**. The first release needs the `.env` (its canary
talks to the gateway), so `secrets` comes before `deploy`.

The league is standard library only. `cryptography` is still installed when it can be, because
`ltcm.adapters` imports it lazily for a signing path the box never takes; if the install fails,
`create` says so and carries on.

Sail bills observed usage, not the ceiling: `$0.015` per used vCPU-hour, `$0.008` per used
GiB-hour of memory, `$0.0007` per used GiB-hour of disk, plus `$0.005` once to create an `s` box.
`status` prints the running rate at the box's actual usage.

### 2. `secrets` -- the one command that touches a credential

The box needs exactly three values and gets exactly three: `SAIL_API_KEY` (agent boxes and
cheap-model inference), `GATEWAY_TOKEN` (venues and the frontier model, through the gateway) and
`CAPITAL_PUBLISH_TOKEN` (the public site). They are read from the local `.env`, composed into a
three-line file and uploaded as bytes to `/workspace/.env`, mode 600. **No venue key ever goes to
the box**: they live only in the gateway's Cloudflare secrets, so a fork or a checkpoint of the box
can never reach a venue without the gateway's caps.

No value is decoded, logged or kept; the command prints names and byte counts only. It deletes
nothing on the box. If `box.json` says an earlier run put a key file under `/workspace/.data`, it
says so: removing it is the owner's step.

### 3. `deploy` -- through the in-box watchdog

```sh
python3 scripts/floor_box.py deploy              # wait for the verdict (up to 1500 s)
python3 scripts/floor_box.py deploy --no-wait    # launch and return; `status` has the verdict
```

A release is always the whole tree. `deploy` packs it into a deterministic tarball, names it
`YYYYMMDDTHHMMSSZ-<first 12 hex of the tarball's sha256>`, unpacks it into
`/workspace/incoming/<id>/`, and hands it to `python -m league.watchdog deploy`, detached, run
from the known-good `current` code when there is one. The watchdog then:

1. **stages** the tree as `releases/<id>/`;
2. runs it as a **canary**: a whole House on throwaway state, a simulated paper account, no
   publishing, no research, no real money. A non-zero exit, a traceback, a timeout or bad health
   and the release is **refused**: `current` is not touched;
3. **promotes** it (`previous` := old `current`, `current` := the release) and runs `restart.sh`;
4. **watches** the real House's `health.json` for ten minutes. After a grace of two readings, the
   first bad one **rolls back**: `current` goes back, the House is restarted again.

On a first deploy, or when the loop is not running, there is no House to watch and the watchdog
is told `--watch-seconds 0`: canary, then promote.

`deploy` prints the verdict and the reasons, records both in `box.json` (the last 20 releases),
and exits 0 only for `promoted` (2 refused, 3 rolled back, 4 failed: it went bad with nothing to
roll back to, 1 no verdict seen). It never moves a link, never restarts the loop and never starts
one. The same tree as `current` is not sent again, and a second deploy is refused while the first
is still being judged.

To go back by hand, on the box, from the code being gone back to:

```sh
cd /workspace/previous && /workspace/.venv/bin/python -m league.watchdog rollback --base /workspace
```

### 4. `start` / `stop`

`start` refuses when there is no `/workspace/current` (deploy first). Otherwise it removes both
stop files and launches `/workspace/run.sh` as a detached process. `run.sh` runs one House at a
time: `cd /workspace/current` (the link is resolved again on every restart, which is how a
promotion or a rollback takes effect), then
`LEAGUE_ENV=/workspace/.env python -m league run --root /workspace/state`, restarted 30 seconds
after it exits. Either stop file ends the loop: `/workspace/STOP` (the supervisor's) or
`/workspace/state/STOP` (the league's own, which `python -m league stop` writes).

`stop` writes both stop files, `SIGTERM`s the House and waits up to **120 seconds** for it to
finish its tick, then kills it if it must, then stops the supervisor. The House puts its agent
boxes to sleep on its way out; a House that had to be killed did not, and `stop` says so.

Neither command touches real money. That is `real_money` in `league/config.json` and the
gateway's kill switch (below), and this script changes neither.

`restart.sh` signals only the House and lets the supervisor restart it from `current`. It never
starts a supervisor that is not up, so it cannot undo a `stop`.

### 5. `status` and `logs`

```sh
python3 scripts/floor_box.py status           # human-readable
python3 scripts/floor_box.py status --json    # the same thing for a script
python3 scripts/floor_box.py logs -n 300      # /workspace/league.log
python3 scripts/floor_box.py logs --deploy    # /workspace/deploy.log
```

`status` shows the Sailbox state and size, observed CPU/memory/disk, spend and the hourly rate,
whether the egress allowlist still matches the recorded one, whether the supervisor and the House
are alive, both stop files, the `current` and `previous` release ids, the last line of
`deploys.jsonl`, the House's `state/health.json` (living and dead agents, ledger sequence, frozen
books, the release it is running), and the tail of `league.log`.

### Checkpoints, forks, sleep

```sh
python3 scripts/floor_box.py checkpoint --name before-real-money --ttl-days 30
python3 scripts/floor_box.py checkpoints
python3 scripts/floor_box.py fork --from sbcp_...
python3 scripts/floor_box.py sleep | resume | pause
python3 scripts/floor_box.py terminate --yes
```

A checkpoint is a durable snapshot of the whole machine, disk *and* memory. Sail also restores the
box from its most recent checkpoint if the hardware under it fails. The default TTL is 30 days.

`fork` starts a second Sailbox from a checkpoint and **does not start the loop on it**: it writes
both stop files and signals anything that came back with the memory image. A fork inherits the
disk, so it carries `/workspace/.env`: `fork` says so, and refuses outright to fork a checkpoint
taken while the loop was running unless you pass `--i-know`. Every fork bills like a full Sailbox
until it is terminated.

`sleep` stops the billing and keeps the disk; a command, a file transfer or `resume` wakes it.
`pause` is the same but only `resume` brings it back.

## Two watchdogs

| | In the box: `league/watchdog.py` | Outside: `gateway/lib/watchdog.mjs` |
|---|---|---|
| Runs | once per deploy, started by `floor_box.py deploy` | every five minutes, as the gateway's cron |
| Reads | `state/health.json` and the ledger, read-only | the public checkpoint on the site, the Sail balance, the box's state |
| Decides | which release `current` points at | whether the box is awake and the House is publishing |
| Does | stage, canary, promote, watch, roll back | resumes a paused or sleeping box; runs `/workspace/restart.sh` when the checkpoint is over 15 minutes stale, at most once in 30 minutes; mails the owner when it has run out of things to do |
| Never | touches Sail, publishes, or writes the ledger | moves a link or chooses a release |

The only thing both do is run `restart.sh`, which is the same harmless signal from either: the
supervisor starts the next House from whatever `current` is at that moment.

## Autosleep

The box is created with **automatic sleep turned off** (`auto_sleep: {"automatic": false}`), so
Sail will never sleep it on its own. The House's tick timer would keep the box looking busy
anyway, but that is a side effect of a config value, not a promise; the setting is the promise.

## What the box can reach

The Sailbox is created with an **egress allowlist** and can open a connection to nothing else.
Sail resolves the names itself, so `/etc/hosts` on the box cannot redirect anything, and a
connection to an unlisted host is accepted and then closed rather than refused.

```sh
python3 scripts/floor_box.py hosts                      # the list, and what the league still lacks
python3 scripts/floor_box.py hosts --add gw.example.workers.dev   # widen the live list
```

A wildcard such as `*.workers.dev` is accepted but never resolves, so the gateway is listed by its
exact name. `hosts --add` sends the widened list, reads it back, and records what the API kept in
`.data/ltcm/box.json`, which is what `status` checks against and what a fork inherits.

What the league needs:

| Host | Why |
|---|---|
| the gateway's exact `*.workers.dev` name | every venue request and the frontier model; the gateway holds the venue keys and signs |
| `api.sailresearch.com` | cheap-model inference and search |
| `sailbox-api.sailresearch.com` | the agents' boxes |
| `blakewoods.us` | the public site |
| `api.elections.kalshi.com` | Kalshi market data (orders go through the gateway) |
| `news.google.com` | the news reader |
| `github.com`, `codeload.github.com` | pulling merged code without credentials |
| `pypi.org`, `files.pythonhosted.org` | `create` only: pip and `cryptography` |

The base list is `FLOOR_HOSTS` in `ltcm/sailbox.py`, which also carries the first run's data
hosts. `hosts` prints any host from the table above that the recorded allowlist lacks. Debian
package mirrors are deliberately **not** on the list, so nothing on the box can `apt-get` its way
to a new dependency.

## The agents' boxes

Agent-written code never runs on the House box. Each agent has a Sailbox of its own, forked from
the image named by `agent_image_checkpoint` in `league/config.json`, with no network and no
credential; the House uploads the strategy and the data, runs it over Sail's exec API and puts the
box back to sleep (a sleeping box costs nothing). The registry is `/workspace/state/sandbox.json`.

## Real money

Every book is practice until `"real_money": true` in `league/config.json`, a line only the owner
changes; it reaches the box as a release like any other, canary and all. Behind it stands the
gateway's kill switch, which refuses real orders while it is engaged and which nothing on Sail can
change (`python3 scripts/gateway_admin.py unkill` releases it, from the owner's machine).
`python3 scripts/floor_box.py stop` stops the House; it does not engage the kill switch.

## Local development

```sh
python3 -m unittest discover -s ltcm/tests -t .     # the first run's suite, with this script's tests
python3 -m unittest discover -s league/tests -t .   # the league's
python3 -m league tick --local-sandbox --no-publish # one tick here (reads the local .env; never with real money)
python3 -m league status                            # the table, the books and the budget
python3 -m league.watchdog status --base DIR        # releases, links, health, the last verdicts
```

`deploy/ltcm.service` is the first run's systemd unit. The Sailbox does not use it.
