# Running the House

The House (`python3 -m league run`) runs on one Sailbox, `ltcm-floor` (size s: 1 vCPU, 32 GiB disk),
in Sail's cloud. The owner's laptop is the console: it holds the credentials and decides, and it can
be closed without the House missing a tick. One script drives the box, from the repository root:
`python3 scripts/floor_box.py --help`. Day-to-day operation (pause, deploy, roll back, inspect,
recover) is in [docs/operations.md](../docs/operations.md); this page is the box itself. The old,
long version is [archive/docs/deploy-README-pre-options.md](../archive/docs/deploy-README-pre-options.md).

Box state (ids, the allowlist in effect, releases sent and their verdicts, checkpoints) lives in
`.data/ltcm/box.json`: owner-only, gitignored, no credential.

## The box

Everything is under `/workspace`:

| Path | What it is |
|---|---|
| `releases/<id>/` | one full code tree per release, never edited again |
| `current`, `previous` | symlinks into `releases/`; only `league.watchdog` moves them |
| `state/` | the House's state: the ledger, `health.json`, `live-grant.sqlite`, `PAUSE`, `STOP` |
| `canary/` | throwaway state for canary runs |
| `incoming/<id>/` | an upload before the watchdog stages it |
| `archive/` | the league's state as it stood on Sept 26, 2026, and its tarball |
| `.env` | the three secrets, mode 600 |
| `.venv` | the interpreter |
| `run.sh`, `restart.sh` | the supervisor loop, and the one signal that restarts the House |
| `run.pid`, `loop.pid`, `deploy.pid` | the supervisor, the House, a deploy being judged |
| `league.log`, `deploy.log`, `deploys.jsonl` | the House's log, the last deploy's log, the watchdog's append-only record |

## Setting up a box

```sh
python3 scripts/floor_box.py create      # the box, the egress allowlist (read back and checked), the venv, run.sh
python3 scripts/floor_box.py secrets     # the three values the box needs -> /workspace/.env
python3 scripts/floor_box.py deploy      # a release, through the in-box watchdog
python3 scripts/floor_box.py start       # the supervised loop
python3 scripts/floor_box.py status
```

- **`create`** makes the box with automatic sleep off, attaches the egress allowlist, builds the
  venv and writes `run.sh` and `restart.sh`. It uploads no code and leaves the loop stopped.
- **`secrets`** is the one command that touches a credential. The box gets exactly three:
  `SAIL_API_KEY` (Sail inference and boxes), `GATEWAY_TOKEN` (the account and OpenAI, through the
  gateway) and `CAPITAL_PUBLISH_TOKEN` (the public site). They are read from the local `.env` and
  uploaded as bytes; the command prints names and sizes only. **No venue key and no ThetaData key
  ever goes to this box.**
- **`deploy`** packs `league/`, `ltcm/`, `scripts/`, `deploy/` and `playbooks/` into a deterministic
  tarball named `YYYYMMDDTHHMMSSZ-<12 hex of its sha256>`; the in-box watchdog stages it, runs a
  canary on throwaway state, promotes it and watches it for ten minutes, rolling back on a bad
  reading. It refuses a `.env`, anything under `.data/` and any private key. It never starts a
  stopped loop.
- **`start` / `stop`**: `run.sh` runs one House at a time from `/workspace/current`
  (`LEAGUE_ENV=/workspace/.env python -m league run --root /workspace/state`), restarting it 30 s after
  it exits, until `/workspace/STOP` or `/workspace/state/STOP` exists. `stop` writes both, sends TERM
  and waits up to 120 s. `restart.sh` only signals the House, so it cannot undo a `stop`.

Also `logs [-n N] [--deploy]`, `checkpoint --name why [--ttl-days 30]`, `checkpoints`,
`fork --from sbcp_...` (a second box; the loop is not started, and it carries the `.env`), `sleep`,
`resume`, `pause`, `terminate --yes`, `maintenance on|off|status`, `hosts [--add HOST ...]` and
`rollback --reason why`.

## Two watchdogs

| | In the box: `league/watchdog.py` | Outside: `gateway/lib/watchdog.mjs` |
|---|---|---|
| Runs | once per deploy | every five minutes, as the gateway's cron |
| Reads | `state/health.json` and the ledger, read-only | the site's checkpoint, Sail's balance, the box's state |
| Decides | which release `current` points at | whether the box is awake and the House publishing |
| Does | stage, canary, promote, watch, roll back | resume a paused or sleeping box; `restart.sh` on a stale checkpoint; mail the owner |
| Never | touches Sail or publishes | moves a link or chooses a release |

Both restart the House the same harmless way: `restart.sh`, after which the supervisor starts the
House from whatever `current` is.

## Egress

The box can reach only its allowlist; Sail resolves the names itself. The options House needs the
gateway's exact `*.workers.dev` name (every account and OpenAI call), `api.sailresearch.com` (models),
`sailbox-api.sailresearch.com` (Gym and gate boxes), `blakewoods.us` (the site), and `pypi.org` with
`files.pythonhosted.org` for the venv's packages (the box's Python 3.11 has no numpy, which the Gym's
live-path pieces need). `LEAGUE_HOSTS` in
`scripts/floor_box.py` still lists the old league's data hosts until the prune (Wave 2b) trims it.
`floor_box.py hosts` prints the list and what is missing; `hosts --add` widens it and records it.

## Real money

Every book is practice until `"real_money": true` in `league/config.json` (false today) and an active
grant (`options-swarm-20260928`, `scripts/live_trading.py`). Behind both stands the gateway's kill
switch, which nothing on Sail can release. `floor_box.py stop` stops the House; it does not engage the
kill switch.

## On a developer's machine

```sh
python3 -m unittest discover -s league/tests -t .     # one process at a time on the laptop
python3 -m league tick --local-sandbox --no-publish   # one tick here; never with real money
python3 -m league.watchdog status --base DIR          # releases, links, health, the last verdicts
```
