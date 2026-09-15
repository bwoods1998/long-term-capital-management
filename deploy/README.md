# Running the floor

The floor runs on a **Sailbox** -- one small always-on Linux VM in Sail's cloud. The MacBook is
the operator terminal: it holds the credentials, it decides, and it can be closed without the
floor missing an open. Everything below is run from the repository on the MacBook.

One script drives the box:

```sh
python3 scripts/floor_box.py --help
```

Box state (ids, the allowlist in effect, uploaded-file digests, checkpoints) lives in
`.data/ltcm/box.json`. It is owner-only and contains no credential.

## The five steps

```sh
python3 scripts/floor_box.py create      # 1. the box, the network policy, the code, the venv
python3 scripts/floor_box.py secrets     # 2. .env and .data/ltcm/keys -> the box, mode 600
python3 scripts/floor_box.py start       # 3. start the supervised loop
python3 scripts/floor_box.py status      # 4. box, spend, loop, log tail, the floor's health
python3 scripts/floor_box.py checkpoint --name before-<change>   # 5. before anything risky
```

and then, for every code change afterwards:

```sh
python3 scripts/floor_box.py deploy      # re-upload what changed; restart a running loop
```

### 1. `create`

Creates one **size `s`** Sailbox (1 vCPU, 16 GiB memory ceiling, 32 GiB disk) from
`BASE_IMAGE_DEBIAN`, private to the owner's key, in the `ltcm` app. Then, in order: attaches the
egress allowlist, **reads the policy back from the live API and refuses to go on if it differs**,
uploads `ltcm/` (including `ltcm/config.json`), `playbooks/`, `scripts/` and `deploy/` as one tar,
builds `/workspace/.venv` and installs `cryptography` into it, and writes `/workspace/run.sh` and
`/workspace/restart.sh`.

It leaves the loop **stopped**. Nothing trades until `start`.

Sail bills observed usage, not the ceiling: `$0.015` per used vCPU-hour, `$0.008` per used
GiB-hour of memory, `$0.0007` per used GiB-hour of disk, plus `$0.005` once to create an `s` box.
An idle floor uses a small fraction of one vCPU, so the box costs single-digit dollars a month.
`status` prints the running rate at the box's actual usage.

### 2. `secrets` -- the one command that touches a credential

```sh
python3 scripts/floor_box.py secrets
```

Reads the local `.env` and every file in `.data/ltcm/keys/`, refuses any of them that is group- or
world-readable, and uploads them as bytes to `/workspace/.env` and `/workspace/.data/ltcm/keys/`
with mode 600. It never parses, prints or logs a value -- the output is names and byte counts.

No other command reads a secret. The code upload refuses `.env`, anything under `.data/`, and any
private-key file, whatever the working tree happens to contain.

**After this the box can move real money.** A checkpoint taken from here on carries these files,
and so does any Sailbox forked from that checkpoint.

### 3. `start` / `stop`

`start` clears the stop latch, releases the kill switch, and launches `/workspace/run.sh` as a
detached process. `run.sh` runs one `python -m ltcm run` at a time, logs everything to
`/workspace/ltcm.log`, and restarts the loop 30 seconds after it exits -- unless
`/workspace/STOP` exists, which is how a deliberate stop survives the restart delay.

`stop` does the three things in the only order that is safe:

1. engages the kill switch on the box (`python -m ltcm kill`), so no new order can be placed;
2. writes `/workspace/STOP` so the supervisor will not bring the loop back;
3. `SIGTERM`s the loop and waits up to **120 seconds** for it to finish its tick and exit, then
   kills it and the supervisor.

`stop` leaves the kill switch engaged. `start` releases it again, or `start --keep-kill-switch`
brings the loop up halted so you can watch it without letting it trade.

`restart.sh` on the box signals only the loop and lets the supervisor restart it; `deploy` uses it.

### 4. `status` and `logs`

```sh
python3 scripts/floor_box.py status           # human-readable
python3 scripts/floor_box.py status --json    # the same thing for a script
python3 scripts/floor_box.py logs -n 300
```

`status` shows the Sailbox state and size, observed CPU/memory/disk, spend so far this month and
the hourly rate that implies, whether the egress allowlist still matches the recorded one, whether
the supervisor and the loop are alive, whether the stop latch or the kill switch is set, the
floor's own `health.json` read off the box, and the tail of the log.

### 5. `checkpoint`, `fork`, `sleep`

```sh
python3 scripts/floor_box.py checkpoint --name before-live-kalshi --ttl-days 30
python3 scripts/floor_box.py checkpoints
python3 scripts/floor_box.py fork --from sbcp_...
python3 scripts/floor_box.py sleep | resume | pause
python3 scripts/floor_box.py terminate --yes
```

A checkpoint is a durable snapshot of the whole machine -- disk *and* memory. Take one before any
upgrade: Sail also restores the box from its most recent checkpoint if the hardware under it
fails. The default TTL is 30 days; the API's own default is seven.

`fork` starts a second Sailbox from a checkpoint and **does not start the loop on it** -- it
writes the stop latch and signals anything that came back with the memory image. A fork inherits
the disk, so a checkpoint taken after `secrets` produces a copy that can reach the live venues:
`fork` says so, and refuses outright to fork a checkpoint that was taken while the loop was
running unless you pass `--i-know`. Every fork bills like a full Sailbox until it is terminated.

`sleep` stops the billing and keeps the disk; a command, a file transfer or `resume` wakes it.
`pause` is the same but only `resume` brings it back. Neither is part of normal running.

## Autosleep

The box is created with **automatic sleep turned off** (`auto_sleep: {"automatic": false}`), so
Sail will never sleep it on its own. That is deliberate: the floor has to be awake for every open,
and "it happens to look busy" is not a guarantee.

It would in fact look busy. Sail sleeps a Sailbox only when *nothing inside would notice*, and one
of the conditions is that no process is waiting on a timer. `Service.run` sleeps
`sleep_seconds` (30) between ticks, which is exactly such a timer, so the idle test never passes
while the loop runs. But that is a side effect of a value in `ltcm/config.json`, not a promise --
turn the tick down to a wall-clock schedule and the box would become sleepable overnight. The
`auto_sleep` setting is the promise; the 30-second tick is the belt as well as the braces.

To let the box sleep between sessions later (a real saving -- sleeping time is not billed), set it
explicitly rather than relying on the tick:

```sh
python3 -c "from ltcm.sailbox import SailboxClient; \
  SailboxClient().set_auto_sleep('sb_...', automatic=True, min_seconds_before_sleep=600)"
```

## What the box can reach

The Sailbox is created with an **egress allowlist** and can open a connection to nothing else.
Sail resolves the names itself, so `/etc/hosts` on the box cannot redirect anything, and a
connection to an unlisted host is accepted and then closed rather than refused.

```sh
python3 scripts/floor_box.py hosts                      # what the box may reach
python3 scripts/floor_box.py hosts --add gw.example.workers.dev   # widen the live list
```

Sail's allowlist is applied at DNS resolution and a wildcard such as `*.workers.dev` is
accepted but never resolves, so the gateway is listed by its exact name. `hosts --add` sends
the widened list as an inline policy document, reads it back, and records what the API kept
in `.data/ltcm/box.json`, which is what `status` checks against and what a fork inherits.

| Host | Why |
|---|---|
| `api.sailresearch.com` | the model provider: every desk session, the critic, the committee |
| `api.elections.kalshi.com`, `api.coinbase.com` | the live venues |
| `advanced-trade-ws.coinbase.com`, `advanced-trade-ws-user.coinbase.com` | the Coinbase WebSockets (prices, order state); Kalshi's socket shares its API host. Read-only: no venue takes an order over a socket, and the box opens them with credential material the gateway mints for seconds |
| `blakewoods.us` | the public site the publisher pushes the tape to |
| `*.workers.dev` | the owner's publish gateway |
| `www.sec.gov`, `data.sec.gov`, `efts.sec.gov` | EDGAR: filings, company facts, full-text search |
| `query2.finance.yahoo.com`, `feeds.finance.yahoo.com` | quotes and bars, headlines |
| `news.google.com` | the news source |
| `docs.sailresearch.com` | the published rate card the provider diffs its frozen prices against |
| `pypi.org`, `files.pythonhosted.org` | `cryptography`, the floor's one non-stdlib dependency |

Debian package mirrors are deliberately **not** on the list, so nothing on the box can `apt-get`
its way to a new dependency. Add a host by editing `FLOOR_HOSTS` in `ltcm/sailbox.py`; the policy
can be changed on a live box with `PUT /v1/sailboxes/{id}/egress-policy`, and `status` reports the
moment the box stops matching the list recorded in `.data/ltcm/box.json`.

The floor's own credentials are **files on the box**, not Sail secrets: every venue request is
signed by the adapter that builds it, so there is no HTTP policy and Sail is never handed a key to
inject.

## The lab image and the desks' sandboxes

A desk that writes code runs it on its own Sailbox, never on the floor box. The **lab image** is
one box provisioned once with python3, numpy, pandas, the floor's read-only market-data package
and `labkit`, then checkpointed; each desk's sandbox is a fork of that checkpoint, created on
its first `run_code`, woken for a run and asleep otherwise (asleep is free). A sandbox has a
data-only egress allowlist and carries no venue key, no gateway token and no Sail key.

```sh
python3 scripts/lab_image.py build       # provision, check, checkpoint, record (a few minutes)
python3 scripts/lab_image.py status      # the recorded checkpoint
python3 scripts/lab_image.py sandboxes   # every desk's sandbox and its sleep state
python3 scripts/lab_image.py sleep       # put them all to sleep now
```

The checkpoint id goes in `ltcm/config.json` under `sandbox.image_checkpoint`, which is how the
floor box learns it; rebuild the image when the data package changes and update the id.

## Going live

Every desk starts **shadow**: it runs full sessions and its proposals are scored against real
prices, but nothing is sent. Moving one to live capital is an owner decision, recorded as a public
event. Do it in this order:

```sh
# 1. name the venue in ltcm/config.json:  "live_venues": ["kalshi", "coinbase"]
python3 scripts/floor_box.py deploy
python3 scripts/floor_box.py checkpoint --name before-live-kalshi

# 2. the decision itself, made on the box
python3 -c "
from ltcm.sailbox import SailboxClient
print(SailboxClient().exec('sb_...', ['sh', '-c',
  'cd /workspace && .venv/bin/python -m ltcm promote kalshi-01 --to live '
  '--reason \"first live sleeve\"']).output)"

# 3. restart the loop into the decision
python3 scripts/floor_box.py deploy
```

Each desk's `capital.usd` in its manifest is its live sleeve. `promote <desk> --to shadow` sends a
desk back. `python3 scripts/floor_box.py stop` is the brake: kill switch first, then quiesce, then
stop -- and the kill switch stays engaged until `start` releases it.

## Local development

The MacBook still runs the floor for development, with the same code and every desk in shadow:

```sh
python3 -m unittest discover -s ltcm/tests -t .   # the whole suite, no network
python3 -m ltcm init                              # create .data/ltcm and check the roster
python3 -m ltcm run --once                        # one tick, printed
python3 -m ltcm status                            # the health projection
python3 -m ltcm session merton --trigger manual   # one desk session now
python3 -m ltcm kill | unkill                     # the switch the risk engine reads first
```

`python3 -c "import json,ltcm.hostinfo as h; print(json.dumps(h.describe_host(), indent=2))"`
says which machine a process is on -- `"host": "sailbox"` with the box id when it is running on
the box, `"host": "local"` here.

`deploy/ltcm.service` is the systemd unit for running the floor on a Linux machine of your own. It
is kept for that case and for disaster recovery; the Sailbox does not use it. The keep-awake
service from `~/Work/agent-host` is no longer part of running the floor -- the box does not sleep.
