# Operating the options House

How to pause, deploy, roll back, inspect and recover the House, the gateway, the data box and the
Gym, and the switches that govern them. The design is in [design.md](design.md). Commands run from
the repository root on the owner's machine unless they say "on the box". Sections that depend on
the swarm or live path describe their implementation, not evidence that production trading is
enabled. Current direction is in [the goal](goals/LTCM_OPTIONS_SWARM.md); the old operator's page
is [archive/docs/operations.md](../archive/docs/operations.md).

## Current operation and next work: October 1, 04:05Z

**The running House.** The House runs Release B, `20261001T034829Z-d823e014ce16`, built from main `3eaf4d06` (PR #454):
Release A plus #451, #444, #445, #455, #456, #447, #453, #448 and #438, and the gateway's KV binding.
- It was promoted at 03:49:07Z Oct 1, and its watch's verdict was PROMOTED.
- It was evidence reset 2. The checks after promotion passed: 0 lineage violations; every alive family adopted the new
  execution fingerprint, with the Gym bundle and image unchanged; the B2 backfill read 14 gate events and barred 1
  program.
- A deliberate restart (04:00Z) and an induced swarm crash (SIGKILL, recovered in 15 s) both recovered under it
  ([CHANGELOG.md](../CHANGELOG.md), Oct 1).
- The gateway runs `dafcfa05` (03:48Z): the research library and its KV binding, with the order routes unchanged. Its
  rollback target is `ac2779ac`.

**Real money is on** (since R2, Sept 27). The grant `options-swarm-20260928` was re-ratified at about 03:59Z Oct 1 on
money digest `42c4a3af` (its third ratification). No family has passed the holdout: two looks, both failed. So the real
orders are the House's own, plus one earlier tuition position:
- D3 calibration round trips;
- the House live test: armed. It decides only inside its private, pre-registered window;
- one tuition position opened Sept 30, before Release A, held by `googl-lags-msft-ai-cloud-qqq-flat@27:t`. Its instance
  is exits only, since Release A's adoption dropped its engine-3 tuition row. Its program's own closes manage it.

**The incubator is on** (since 04:01Z Oct 1: `live.incubator` true). Nothing can trade on it yet.
- A cohort is pinned only after its first look passes, and a first look needs 3 completed sessions and 10 program closes
  in the record before today. For cohorts admitted at the Oct 1 open, that is the Oct 6 open at the earliest (sessions
  Oct 1, 2 and 5).
- After that, the swarm's facts (B2), the caps and the weekly envelope still decide every open (**Real money**, "The
  incubator", below).
- **To switch it off**, on the box: keep a before-copy, set `live.incubator` to JSON `false` and replace the file
  atomically, then read the switch back.

  ```sh
  cd /workspace/state && cp -p swarm.json "swarm.json.before-off-$(date -u +%Y%m%dT%H%M%SZ)"
  /workspace/.venv/bin/python - <<'EOF'
  import json, os
  path, tmp = "/workspace/state/swarm.json", "/workspace/state/swarm.json.tmp"
  with open(path) as f:
      data = json.load(f)
  data.setdefault("live", {})["incubator"] = False
  with open(tmp, "w") as f:
      json.dump(data, f, indent=2)
  os.chmod(tmp, 0o600)
  os.replace(tmp, path)
  EOF
  cd /workspace/current && /workspace/.venv/bin/python -B -m league.live --root /workspace/state --incubator
  ```

  The last command must show `switch` `on` false. Within a minute the incubator's instances go to exits only and their
  working opens are cancelled. First looks are still recorded. Switch it off before any rollback across Release
  B (**Roll back**, below).

**The freeze** (since Release B). `league/live` and `league/gym` change only in a planned, deliberate release.
- A change to either, or to `LEAGUE_FILES`, the fill model or the Gym image, moves the evaluator. Every practice cohort
  is bound to its evaluator, so such a change ends every practice cohort, and with them every incubation, for good. It
  also re-adopts selection (**Evaluator adoption and `gym-engine-4`**, below).
- Batch such changes into planned releases. Rollbacks and fixes for bugs that block or endanger real orders are the only
  exceptions.
- Swarm-side changes that the fingerprint does not hash are no reset. They still deploy only outside the session when
  the live path loads the module.

**Next:**
- **Oct 1, 13:31-13:35Z, the first session under B.** The deploy's canary never exercises the live path or the swarm,
  so check by hand:
  - `health.json` `options_live.incubator.pins.day` is `2026-10-01`;
  - no incubator error alert, and no "the incubator's first looks failed" or "pins failed" warning;
  - practice cohorts admitted at the open.
- **About 4 hours after B:** Train runs and validation attempts an hour, against the spend plan's rule.
- **After the Oct 1 close:** the close's economics, and B' (swarm side, no evidence reset): #446 family cards and the
  final review's two fail-closed findings.
- **In review:** #449 (harness lanes), #452 (evaluator benchmarks) and #446.
- **The library stays off** (`research.enabled` false) until the order route's p99 is measured with the library under
  load.
- **The runtime skew.** The House runs Python 3.11 with numpy 2.4, the Gym Python 3.12 with numpy 2.5. A program can
  train in the Gym and still fail to load on the live path; the preflight flags it (`preflight_house_unloadable`).
  Align the runtimes in a planned release.

**Spend** (the owner, Sept 30: cut burn to evidence). Since 16:41Z Sept 30:
- architect births run on Kimi-K3 on Sail (`claude.role_usd_day.architect` 0);
- stall rewrites and the diagnostician are off;
- the Gym pool is at most 6 boxes (4 until Release A).

Since 02:47Z Oct 1:
- the architect runs every 1,800 s (`architect.every_seconds`, 900 before);
- the researcher Sail pace is $1.30 an hour (`researcher.sail_usd_per_hour`, $1.10 before).

With the architect's Claude line at 0, its passes fell back to Sail and took about 73% of the research pace, which
starved research. Running the architect half as often and raising the pace moves that Sail draw to research, at about
the same total. The gate's review and audit and the strategist stay on Claude. **Models and Claude** and **Funding cliffs
and alerts**, below, have the details.

**Funding cliffs** (as read at 21:04Z Sept 30):
- The OpenAI month's cap is $0 since 00:00Z Oct 1. No role uses OpenAI.
- Claude's funded room was $37.17.
- The Sail guard's brake is projected for about 20:00Z Oct 3 ($161.86 of balance).
- `guard.burst_until` ends Oct 5 00:00Z.

The swarm says each of these ahead of time (#439).

**Unchanged:** D2, the sealed holdout, no forced trades and the Sail guard's line. The money table gained only the
incubator's row, with Release B.

Re-read main, the open PRs and the running release before acting: a document's timestamp is not a fresh health check.

The existing ThetaData collector owns the only account session; preserve it while it downloads. Do not log in again, or
launch a duplicate collector to widen the universe. New discovery belongs in a data backlog until coverage and capacity
are verified.

No trading-day deploy 13:25-20:05Z except a rollback.

## What runs where

| Piece | Where | Driven by | Local record (gitignored) |
|---|---|---|---|
| The House (`python3 -m league run`) | Sailbox `ltcm-house` (`sb_1d99c4a7`; `floor_box.py`'s default name for a new box is `ltcm-floor`), size s, `/workspace` | `scripts/floor_box.py` | `.data/ltcm/box.json` |
| The gateway (venue, OpenAI, Anthropic and GitHub keys, caps, the OpenAI month, Claude's funded total, kill switch, outside watchdog) | Cloudflare Worker `ltcm-gateway` | `gateway/`, `scripts/gateway_admin.py` | `.data/ltcm/keys/gateway-admin.token` (owner only) |
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
- **The money path (D8, amended Sept 29).** A research-side release may deploy in the session only when it touches
  none of the money path. The money path is:
  - `league/live`;
  - the gateway;
  - `league/constitution.py`;
  - every module the live path loads.

  An import trace of Release A's tree (Sept 30) finds these loaded, and a static trace of Release B's tree finds the
  same plus one:
  - **at module level:** `league/gym/{__init__,ctx,day,engine,events,fills,greeks,legs,runtime,safety,venue}.py` and
    `league/{safety,stats,structure_core}.py`;
  - **lazily:**
    - `league/gym/{driver,experiment,review_contract}.py`;
    - `league/constitution.py`;
    - `league/swarm/{__init__,store,bands,gate,evaluator,settings}.py`;
    - through `gate`, `league/swarm/{evidence,pool,researcher,claude_research,diagnostics,inputs,public}.py`;
    - from Release B, through `researcher`, `league/swarm/library.py` (#447).

  `league/swarm/{funding,models,loop,guard,practice,tournament}.py` are not loaded. Re-derive the list with an import trace of
  `league/live/*.py` on each release's tree. Any change under `league/gym/` or `league/live/`, to `LEAGUE_FILES`, to the
  fill model or to the Gym image also moves the evaluator's fingerprint: it is an evidence reset (below).
- **A workflow change re-pins the updater in the same commit.** A change to `.github/workflows/` needs
  `TRUSTED_WORKFLOWS_SHA256` in `league/updater.py` re-pinned in the same commit (a test checks it). If the in-box
  updater were on, the running release would refuse main heads that carry the new workflows until an owner deploy
  carries the new pin. CI's `tests` job has a 35-minute limit (Release A; it was 20). The hourly run has its own
  concurrency group, so it never cancels a push run. `league/updater.py` reads a cancelled run as no verdict, so a
  cancelled run is not green.

### Evaluator adoption and `gym-engine-4`

Engine 4 binds parameter overrides to module `PARAMS` at its declaration, before aliases and helper
defaults capture values; `ctx.params` starts with the same values. Each independent run still executes
the module in a fresh namespace. Persistent module state within one run is permitted. This changes
execution semantics for old programs that read global `PARAMS` with nondefault overrides, so prior
results cannot qualify them under the new runtime.

At swarm startup, before any research or tournament worker, `research_evaluator` records the current
data image, full Gym bundle and execution fingerprint. An identity change archives and clears derived
Train bests, candidates, submissions, stress/drift views, validation and review. Runs, versions, lineage
trial counts, refusals, notebooks and consumed holdout looks remain. Late old-evaluator results are
still counted but cannot refill current selection or forward evidence. Full result pruning retains
each worker's actual image and bundle in its run summary. The replay key and standalone engine hash
also change, so the old cache cannot supply a new result.
If two different evaluator identities return the same standalone worker run ID, the store keeps
separate result rows and files; it never relabels old metrics as new evidence.

An old contract's pre-holdout refusal is archived and its active veto cleared, allowing a fresh review
only after new-evaluator qualification. The refusal record stays; an actually consumed look remains
in `looks` and cannot be reopened for that same program hash.

Candidate, Probe and Sized entry authority additionally pins the program hash and the executable
Gym/live/shared-source fingerprint in `banded_evaluator`. An old/missing fingerprint denies new opens
and band confirmation; startup returns that family to Gym so researchers can requalify it. Frozen
live instances and their positions keep their exit/reconciliation path, and historical band/forward
records remain. A docs-only bundle change does not erase a band whose executable fingerprint still
matches. A runtime, fill or context change does, even if an engine-version bump was missed. A new
qualification still needs all existing Train, validation, independent review and holdout requirements;
an identical code+parameter hash cannot acquire another sealed look because the evaluator changed.

New practice cohorts require a current-image/current-bundle eligible Train or completed Validation
replay; an old `best_train_version` or `validation_version` label alone is insufficient. A zero-trade or
failed validation line remains information, not an automatic experiment-contract failure. Existing
immutable cohorts separately pin their bundle, fill-model label and executable fingerprint: a changed evaluator makes them close-only, with
forced wind-down outcomes excluded from strategy feedback. Their `(family, version)` identity cannot
be reused for a new evaluator; re-entry requires a newly eligible source version.

Adoption needs a new code release, not a new data checkpoint solely for this parameter fix: GymDriver
uploads the content-addressed engine bundle to sealed workers, and results identify both bundle and
data image. Verify the deployed `research_evaluator`, adoption events, unchanged total trials/looks,
worker `gym_bundle`, real entry proof and practice evaluator before treating new observations as
current evidence. Evaluator adoption is not a strategy promotion or a claim of profitability.

**Evidence resets are planned releases** (Sept 30, 2026).
- A change to any of the following re-adopts the evaluator:
  - anything under `league/gym/` or `league/live/`;
  - `LEAGUE_FILES` (`league/{__init__,safety,structure_core,stats}.py`);
  - the fill model;
  - the Gym image.
- The release before Release A had no evaluator record, so Release A's first start adopted one for every alive family.
  That was reset 1 (20:06Z Sept 30).
- Release B, the incubator, was reset 2 (03:49Z Oct 1). It changed `league/live` only, not `league/gym` or
  `LEAGUE_FILES`, so the execution fingerprint moved while the Gym bundle and image stayed Release A's:
  - selection is archived and cleared again, as at reset 1;
  - extension holds and the operator's clears stand, since only a new Gym image or bundle clears them (#453,
    `evaluator.gym_changed`);
  - a validation recorded on the same image and bundle may be judged again;
  - every practice cohort from Release A completes ("evaluator changed; a new version needs fresh practice"), because
    the practice evaluator is the bundle, the fill model and the fingerprint together.

  After an adoption, the idle count restarts from `evaluator_trials`, and an idle retirement says "since the evaluator
  changed" (#453).
- Since B, those paths are frozen for at least five sessions, and for as long as any family holds Candidate, Probe or
  Sized or has an incubator-bound cohort. A change to them ends every practice cohort and every incubation. The only
  exceptions are rollbacks and fixes for bugs that block or endanger real orders.
- Other changes to those paths are batched into planned releases between evidence windows: harness-lane changes, the
  fill-model refit and new images.
- The run record logs every reset. Never compare evidence across fingerprints.

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
- **The swarm and the Gym under a pause:** a paused House starts no swarm process (and no nightly
  job), but a swarm already running goes on, and the Gym trains through a pause. To stop the swarm,
  write `/workspace/state/swarm.stop`; the House starts it again once the file is gone and the House
  is not paused.

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
prints it). Release B moves it (`a3e2aa7c` → `42c4a3af`, the incubator's row).

**The gateway.** In `gateway/`: `npm run check && npm test`, read the result, then `npx wrangler
deploy`. Deploy the gateway before a House release that needs its change. After a deploy, read
`python3 scripts/gateway_admin.py status`. Caps and `OPTION_STRUCTURES_REAL` change only this way. Deploy from a clean
checkout of exactly `origin/main`: a deploy from a branch drops whatever else main holds. From Release B the gateway
binds a KV namespace (`LIBRARY`, `ltcm-gateway-library`) for the research library; never delete it.

**The site.** In `~/Work/personal-site`: `npm test`, then `npm run build && npx wrangler deploy`
(its `DEPLOYMENT.md` has the details). When the publisher's schema or a bound changes, the site
deploys first: it refuses a whole checkpoint for one field it does not allow. The one exception is the
positions table (`positions`, Sept 28, 2026): refused, the publisher posts the checkpoint again without it
and offers it again half an hour later (a warning per distinct reply of the site, "positions table: the site
refused the positions table (old site, or a row it rejects) ... (the site said: ...)"), so either may go
first. The first release of the table went site first (#15, 16:59Z Sept 28), then the House (R6, 20:08Z).
The practice league's block (`practice`, Sept 29, 2026) and Claude's own compute part (`compute.claude_usd`, Release
A, #441) are the second exception, handled together.
- **The order it tries:** a site that refuses the checkpoint is sent each older shape alone, then both:
  1. without the positions table;
  2. without the practice block and with the five-part bill (Claude folded into `other_usd`,
     `publish.legacy_compute`);
  3. both at once.
- **What gets marked:** only the part the site then took is marked refused, and it is offered again after 30 minutes.
- **The warning,** one per distinct reply: "the site refused the practice league block or Claude's own compute part
  (old site, or a row it rejects) ... (the site said: ...)".
- **The site that takes both:** personal-site PR #17 (`capital/cost-net-practice`). It also adds the Net line, costs by
  service and the Incubator label. Its Worker serves the new shapes only to the page's own read
  (`?progress=1&positions=1&practice=1`), so either repository may deploy first. Site first is preferred: the page
  then shows Net as a dash until the House sends `claude_usd`. The site must be live before the incubator is switched
  on.

The swarm window (`levels` and `rationale`, Oct 1, 2026: each agent's level and the levels funnel, each agent's thesis,
and why each real position opened and closed) is the third exception.
- **The order it tries:** a site that refuses a checkpoint carrying the window is sent it again without the window first
  (`publish.windowless`). Refused again, the ladder above goes on without the window.
- **What gets marked:** the window, only when the windowless checkpoint was taken; it is offered again after 30 minutes,
  and the House does not read it meanwhile. A site that refuses the table too is told the window's refusal on the next
  publish.
- **The byte limit:** the window leaves first (its theses, then all of it), before any agent or row, and the body is
  fitted 32 KiB under the site's 512 KiB so the names the site's public read adds (a 40-character name on each of
  at most 508 rows) never push it over.
- **The warning,** one per distinct reply: "the site refused the swarm window (levels and rationale: old site, or an
  entry it rejects) ... (the site said: ...)".
- **The site that takes it:** personal-site branch `capital/swarm-window`. Its Worker serves the window only to
  `?progress=1&positions=1&practice=1&window=1`; every older read gets exactly the keys it validated. Site first is
  preferred; either order works.

**Checkpoint the House box before risky work:** `python3 scripts/floor_box.py checkpoint --name why
--ttl-days 30` (`checkpoints` lists them). A checkpoint holds the box's `.env`. Sail's checkpoint
API failed twice on Sept 26 (06:35Z and 07:00Z, HTTP 503); the old state's archive is a tarball
instead.

## Release A: after promotion (Sept 30, 2026; done 20:16-20:50Z)

Done: the results are in [CHANGELOG.md](../CHANGELOG.md), Sept 30. The steps stay here as the reference for the next
adoption.

**The deploy.** Release A deploys like any House release (above): at 20:05Z or later, from a clean detached checkout of
its main commit.
- **Before:** check that no calibration position or working order is open, `deploys.jsonl` is idle and the latest backup
  is under 30 hours old. Note any House live test position.
- **The verdict:** `deploy` exiting 0 means promoted. On any other exit, stop and read `status`.
- **Right after promotion:** `real_money` true, the money digest `a3e2aa7c`, and the House live test's instance real
  with `observe false`.

**Right after promotion, before the next architect pass** (900 s on the box), on the box:

1. **The graveyard verdict migration** (R11-1, once). Run the dry run, read the counts by verdict, then apply:
   ```sh
   /workspace/.venv/bin/python /workspace/current/scripts/graveyard_verdicts.py --state /workspace/state
   /workspace/.venv/bin/python /workspace/current/scripts/graveyard_verdicts.py --state /workspace/state --apply
   ```
   The backup and `--rollback` are described under **R11b**, below.
2. **The R11b setting.** In `swarm.json` (keep a before-copy), set `claude.role_effort` to `{"architect": "medium"}`.
   It changes nothing while the architect's Claude line is $0 (Sept 30), and holds if that line is restored. The Gym's
   zero-trade probe stays off: leave `researcher.probe_year` unset.
3. **The extension hold seed: skip it after an adoption.** Adoption clears `validation_version` first, so the seed list
   (`scripts/extension_hold.py --state /workspace/state --seed`, a dry run) is empty by design. It was skipped at
   Release A. Families are held when a validation under the new evaluator meets the checks.
4. **The input capability card** (#432).
   - Check that the private Train audit's `image_checkpoint` equals `swarm.json` `gym.image_checkpoint`.
   - Upload it as `/workspace/state/input-capabilities.json.tmp`, set mode 600, then `mv` it over
     `/workspace/state/input-capabilities.json`, so the replacement is atomic.
   - Its schema is under **Input capability card**, below. The card never enters the repository.
5. **The data side.**
   - `pgrep -af window.py`. If the history window controller's loop (#413, `scripts/data/window.py ... loop --every
     60`) is gone, start it again detached. Only one runs at a time.
   - Set up `sip-progress.sqlite` and the legacy readiness rescan, as
     [data-sip-completion.md](data-sip-completion.md) describes (#433).
6. **Operator revivals** (optional). A near-miss family that the dormancy clause retired may be revived as a lineage
   continuation (origin `operator-revive`, **The graveyard**, below).
   - It inherits its lineage's trials and holdout looks.
   - Its re-validation under engine 4 is a new, counted trial, and the holdout still judges it.
   - Run a dry run first. The revived family is held once its re-validation meets the checks.
   - Record in the run record which families were revived, and that the operator chose them from the validation line.
   - **The harness runs the revived program exactly** (Oct 1, `researcher.py` THE OPERATOR'S RUN). Take a living Gym
     family's latest version written by the operator (author `operator-revive`). If it has no Train run at the normal
     spread on the current evaluator (image and bundle) and Train span that is the program's answer, the harness runs it
     at the start of the family's next cycle, before any rewrite, queued run or model turn. An answer is a run of status
     ok, disqualified, no_data or refused. A run of status `error` is not one: the Gym could not finish it (a dead
     worker, or a unit killed, perhaps for another program in its batch), with no trial and no figures.
     - It runs with the version's stored code and params, through `gym_run`'s own path: the same refusals, no-duplicate
       rule, lineage trial, Train score, drift screen, best and robustness runs. It is never probed. It is recorded as
       that version (no version row, no revision).
     - Any new evaluation of it, ok or not, is the cycle's one run. A rewrite and a run queued last cycle wait for the
       next cycle, and the model reads the result. A run call the model makes in that cycle replaces the queued run.
     - A Gym error, a run the Gym could not finish, or a failure of the attempt itself ends the cycle with no model call.
       The harness tries again next cycle, at most 3 times. When a wait gave up while the Gym was still running the job,
       the harness does not submit it again. It waits up to one more run timeout (`late_until`) and reads the result
       back from the store when it lands, with no second job and no second trial. That holds even after it gave up.
     - A refusal, or the third failure, gives up with a notebook note. The note and the status say how the researcher
       can run the version itself. A gate-mode mechanism test that did not pass is the version's answer.
     - The family state's `operator_run` keeps the record per version, evaluator and Train span, so a later adoption
       owes one more run. The harness's own stored result or refusal never counts toward the dormancy clause.
     - The status tells the researcher that its revival runs unchanged first, that its evidence decides, and that an
       evaluator change is never a reason to retire.
   - **Before this fix, revivals did not run the revived program.** Between Sept 30 and the fix, the harness never ran a
     revival's version 1. A `gym_run` with no code reran the latest code with params `{}`, which dropped the revived
     params; unless they equalled the program's `PARAMS` defaults, a different program ran. Researchers also often wrote
     new code at once. A revival's Train, 1.5x and drift evidence on the evaluator in force therefore mostly never
     landed. Check any run-record claim from that window that a revival "re-validated with identical numbers" by
     evaluation, not by version number. Compare the run's code sha and merged params (its `eval_key`) with version 1's:
     the revived program is that code with version 1's params merged over the `PARAMS` defaults, whichever version row
     the run is under. On the first deploy with the fix, each living revived family whose version 1 has no such run gets
     it in its next cycle. The deploy is a new release, so it also wakes a parked family.
   - `gym_run` with neither `code` nor `params` now reruns the latest version exactly: its params carry over. Explicit
     params, `{}` included, still replace them.

**Checks after promotion.** Record each one in the run record.
- **Evaluator adoption.**
  - `research_evaluator` is set, and each alive family has an `evaluator_adopted` event.
  - Lineage trial counts and consumed holdout looks match a snapshot taken before the deploy.
  - Workers report the new `gym_bundle`, and the practice evaluator is bound to the new fingerprint.
  - The paper route proofs still read passed.
- **The live guards** (#437).
  - `options_live.instances["house:rebound-live@0:h"]` is `kind` real with `observe` false.
  - Every `:o` instance has `observe` true.
  - There is no "is not a real instance" alert.
- **The decider** (#443).
  - `live-decider.log` and `live-decider-observe.log` show no traceback.
  - There is no "requires a network namespace" error.
  - The child's `/proc/<pid>/limits` shows a 64 MB file size and 0 processes.
- **Research.**
  - Retirements happen at `population.floor` and `researcher.retire_min_trials`.
  - After one tournament round (3,600 s), no family without a positive validation mean holds exploit weight.
  - Sampled reviews and audits cite the runtime contract, the evidence or a counterexample.
  - Holding families stay on the same cycle count until new evidence wakes them.
- **Funding** (#439).
  - A few `swarm: funding: ...` warnings are expected in the first minutes.
  - The heartbeat has `status.funding`.
  - Architect calls show up as `claude_fallback` events (kind `line`, route Sail) while its Claude line is $0.
- **The practice league:** the checks in [CHANGELOG.md](../CHANGELOG.md). Right after the reset it is expected to be
  nearly empty.
- **A deliberate restart**, at a quiet moment with no calibration order working and outside the House test's window.
  Run `floor_box.py stop`, then `start`. Then verify:
  - the House test instance comes back real with `observe false`;
  - cohorts, waits and any open position survive;
  - health is clean.
- **The harness observer** (optional, #432). Write `/workspace/state/harness/runtime.json`, mode 600, with:
  - `enabled` true;
  - `schema` 1;
  - `mode` "observe";
  - `base`: the deployed commit's full SHA;
  - `release_digest`: `league.watchdog.tree_digest` of `/workspace/current`.

  [playbooks/harness-improvement.md](../playbooks/harness-improvement.md) has the details. Then check that the House's
  swarm step reports it running, under `harness`.
- **Watch for an hour:** cycle latency, House CPU, `observe_reads_skipped`, `shed` and `restarts_24h`.
  - If the House starves, first lower `live.observe_roots_max` or `live.observe_read_calls`, or set
    `live.observe_train` false. These switch things off, which is allowed in session.
  - Roll back only if that fails, and never past the House test's start release while it holds anything.
- **Then:** apply the Gym settings planned for after Release A: `gym.max_boxes` 6 and `architect.max_refill` 12
  (CHANGELOG, Sept 30).

## Release B: deploy, ratify, switch on (Oct 1, 2026; done 03:48-04:01Z)

Done: the results are in [CHANGELOG.md](../CHANGELOG.md), Oct 1. Steps 1-7, 9 and 10 ran in order (the ratify after the
watch's PROMOTED verdict). Step 8, the library, waits: `research.enabled` stays false until the order route's p99 is
measured with the library under load. The steps stay here as the reference for the next money-path release.

Release B (PR #454) is the incubator (B1 and B2), L1 and its restart fix, L2', the research library, the adoption fixes,
information-value allocation and the preflight. It moved the money digest (`a3e2aa7c` → `42c4a3af`) and was evidence
reset 2. It deployed outside the session, before 13:25Z Oct 1, and never 19:30-20:00Z.

**The order.** Nothing here may be reordered.
1. **Merge #454 to main** once CI is green. On the merge commit,
   `python3 -c "from league.constitution import digest, money_digest; print(digest(), money_digest())"` prints
   `595228a6…` and `42c4a3af…`.
2. **Before anything:** no calibration position or working order is open; `deploys.jsonl` is idle; the latest backup is
   under 30 hours old. Note the House live test's position, if any, and every open tuition position (one at Sept 30's
   close). Take a read-only lineage snapshot of `swarm.sqlite` (trials, inherited trials and looks by lineage, and the
   run count).
3. **The gateway first.** It carries the library's code and its KV binding. From a clean checkout of exactly the merge
   commit, in `gateway/`: `npm run check && npm test`, read the result, then `npx wrangler deploy`. Then:
   - `python3 scripts/gateway_admin.py status`: the kill switch unchanged, the caps and `OPTION_STRUCTURES_REAL` as
     before;
   - `GET /v1/research/health` answers a `library` block with `cap` 600;
   - a search twice (`X-LTCM-Library: miss`, then `hit`: the KV cache is bound), and one read of a result's id.

   The House keeps `research.enabled` false throughout, so nothing on the House calls the library yet.
4. **The House:** `python3 scripts/floor_box.py deploy` from the same checkout.
5. **Ratify at once**, as soon as `floor_box.py status` shows `current` = the new release (the promote comes about a
   minute into the deploy; the ten-minute watch follows it): `python3 scripts/live_trading.py --ratify`.
   - It runs on the box against `/workspace/current`, so it pins the digest of the release that is running.
   - It prints the grant: `active` true, `policy.constitution_digest` `42c4a3af…`, and one more ratification.
   - Capital is read afresh: the lower of equity and the ceiling. It follows equity down as well as up, so expect it
     below Sept 28's $1,473.11.
   - Until the ratify, every real entry is refused (the House live test, the calibration, tuition). Exits go on.
   - If the watch then rolls the release back, ratify again at once on the restored release (`a3e2aa7c`).
6. **Checks after promotion.** Record each in the run record.
   - **The adoption (reset 2).** `research_evaluator`'s `execution` has changed, while its `bundle` and `image` have
     not. Every alive family has an `evaluator_adopted` event. A second lineage snapshot shows the same trials,
     inherited trials and looks by lineage, and no fewer runs.
   - **The practice league.** Release A's cohorts in `observe.sqlite` are `complete`, with the reason "evaluator
     changed; a new version needs fresh practice". New cohorts can start at the Oct 1 open, from eligible versions not
     practised before.
   - **The instances** (`health.json` `options_live.instances`):
     - `house:rebound-live@0:h` is real, `observe` false, mode live, with no error;
     - the tuition instance is `exit_only`, tuition, with no error, and its position is open in `live.sqlite`;
     - no `:i` instance exists.
   - **The incubator's block** (`options_live.incubator`): the table as committed (50, 1, 4, 150, 3, 10, 0.80); 0
     verdicts; a zero tally; no weekly stop. `python3 -m league.live --root /workspace/state --incubator` (on the box,
     read-only) says the same, and `switch` `on` false.
   - **Guards:** no "not a real tuition incubator instance" alert and no `:i` id in the swarm's `forward`; `real_money`
     true; `failures` empty.
7. **Switch the incubator on**, outside a session, once the checks pass. The site already labels its rows (personal-site
   #17). In `swarm.json`, set `live.incubator` to JSON `true`, keeping a before-copy. Check it with `--incubator`:
   `switch.on` true.
   - Nothing can be pinned before a first look passes (Oct 6 at the earliest). So switching on early costs nothing.
   - `health.json` `options_live.incubator.switch` shows the last minute's read of `swarm.json`. Outside the session
     the switches are read only at a families pass (every 5 minutes), so between passes it can read false.
     `--incubator` reads the file itself.
8. **The library on:** set `research.enabled` to true in `swarm.json` (**The research library**, below).
9. **Criterion 1 again, under B:** a deliberate restart (`floor_box.py stop`, then `start`, with no calibration order
   working and outside the House test's window), then an induced swarm crash. Verify what Release A's tests verified
   (CHANGELOG, Sept 30). Evidence counts only under the running release.
10. **Close-out:** record releases A and B as order-path deviations in the House live test's private addendum; update
    the run record and the CHANGELOG entry with the times and figures.

**Rolling back across B.** Switch `live.incubator` off first and wait until no `:i` position is held or working.
Release A does not know the route: it would restore an `:i` instance, send it to exits only and count its rows as
tuition. Then roll back (**Roll back**, below) and ratify again at once on `a3e2aa7c`. In an emergency with `:i`
positions held: the kill switch first, close them at the venue, then roll back. Roll the gateway back
(`npx wrangler rollback <version>`) only if the gateway itself is at fault: Release A never calls the library. Never
delete the KV namespace. A rollback moves the execution fingerprint back, so the swarm adopts Release A's evaluator
again at its start: that is one more evidence reset, to be logged in the run record like the planned ones.

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
- **`long_single` (#425).** Once any `long_single` family exists, alive or retired, a release before #425
  fails every architect pass (its coverage has no `long_single` row: a caught KeyError, so no family is
  born) and refuses forks of it. Roll forward, or hotfix, rather than roll back past #425.
- **Across Release B** (the incubator): switch `live.incubator` off and wait until no `:i` position is held or working
  before a rollback; ratify again at once on `a3e2aa7c` after it (**Release B: deploy, ratify, switch on**, above).
- **The gateway:** `npx wrangler rollback` in `gateway/`. **The site:** the same in
  `~/Work/personal-site`. Never delete the gateway's KV namespace `ltcm-gateway-library` (Release B): a rollback to a
  version that binds it needs it.

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
- **The incubator** (Release B), on the box: `python3 -m league.live --root /workspace/state --incubator`, read-only.
- **The research library** (Release B): `GET /v1/research/health` on the gateway (the `library` block of `/v1/health`),
  and the swarm's private `swarm.research` events.
- **The gateway:** `python3 scripts/gateway_admin.py status`: the kill switch, today's order
  counters, the OpenAI month (spent, settled, in flight, the cap), Claude's funded meter (`claude`: the
  cap, spent, in flight, remaining, holds, the priced models, spend by role and agent), the Sail balance
  and the House box's state. Since PR #417 it also has `overruns` and `overrun_usd`: calls whose settled cost ran
  past their hold (never expected; the House pauses its Claude research band on one).
- **Claude's top band** (PR #417): a `swarm.cycle` event of a top family carries `route: "claude"` once a Claude
  turn was answered, `claude_calls`, `claude_usd`, `claude_usage` (input, cache write, cache read and output tokens
  summed over the cycle, refused and cut answers included), and when it applies `claude_fallback` (`<kind>: <why>`,
  the turn that went to Sail), `claude_skipped` (`hold_streak: ...` or `paused: ...`: the cycle stayed on Sail),
  `claude_paused` (this cycle's trouble paused the band) and `claude_overrun`. The swarm's `spend` rows (kind
  `claude`, `detail.role` "researcher") hold the holds and their settlements; `kv claude_unsettled` lists holds whose
  bill is not yet known; `kv claude_band` is the breaker (`trouble`, `paused_until`, `why`).
- **The public page:** `curl -s https://blakewoods.us/api/capital/checkpoint` (its `published_at`);
  `curl -s 'https://blakewoods.us/api/capital/checkpoint?progress=1&positions=1'` adds the positions
  table, which the default read omits; `...&practice=1&window=1` adds the practice league and the swarm window
  (`levels`: each agent's level and the funnel since the reset; `rationale`: each agent's thesis and each real
  position's route, reasons, exit and maximum loss).
- **The public cost and Net** (Release A, #441, with personal-site PR #17).
  - **`compute` is the bill since the reset, by service.**
    - `sail_usd` is what Sail billed. It is the Sail guard's balance meter (`swarm.sqlite` kv `metered_spent`, since the
      swarm began at 10:22:26Z Sept 26) plus `sitefeed.PRE_METER_SAIL_USD` ($0.46, the provider's box billing from T0
      to the meter's start). It is never the Gym's booked `gym_box` estimate, which runs about 70% above the bill. It is
      never below the swarm's booked model calls.
    - `claude_usd` is the swarm's Claude spend, settled plus in-flight holds.
    - `openai_usd` includes unresolved OpenAI holds.
    - The two data subscriptions are prorated from the reset.
    - `other_usd` holds what the owner declares; it is $0.00 until a declaration.
  - **Net** = realized options P&L since T0 minus every input cost since T0. Open gains are excluded and open losses
    included. It is a dash while any part is null or older than ten minutes.
  - **Known limits:**
    - the meter trails the provider's receipts by about $0.5, and the gap closes as late debits post;
    - if a new swarm store is ever started, the meter restarts, and `sail_usd` falls back to the booked figures (which
      overstate) until the pre-meter constant is re-derived.
- **The data:** `python3 scripts/data/box.py status` (the box, its egress, the backfill's progress);
  `python3 scripts/data/box.py run -- check.py report` (underlying-days by window and root, the
  queue, the rate); `python3 scripts/data/images.py status`; `python3 scripts/data/nightly.py status`.
  Numbers derived from the data stay on the boxes and in `.data/`.
- **The swarm and the scoreboard** (families, trials, validation passes, holdout looks, Gym
  throughput, compute against the budgets), on the box:
  - `cd /workspace/current && /workspace/.venv/bin/python -m league.swarm status --root /workspace/state`:
    the heartbeat, the totals (trials, holdout looks and passes), families by band, the live rows and the
    families held at the gate;
  - `python3 scripts/verify_swarm.py --root /workspace/state`: process, population, cycles, the Gym,
    the tournament, each PASS, FAIL or WAIT;
  - `/workspace/state/swarm.heartbeat` (JSON): families, cycles and spend in the last hour by kind, the
    guard, the pool, `status.researcher_pace`;
  - `health.json` `options_live`: the observe band, the calibration, the House live test, the stops;
  - Claude and OpenAI spend: `gateway_admin.py status` (above). `scripts/floor_watch.py` is not
    rewritten for the options scoreboard.

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
- **Train's span in a Gym image.** `images.py build gym --train-from 2020-01-02` (the running image) or
  `--train-from 2017-01-03` (Train from 2017, released in R11a on Sept 29) keeps those years as Train and the underlying of
  the 60 sessions before as history; without it Train starts 2022-01-03. `--root-first ROOT=DATE,...` gives a root
  its own later first Train day (its history is then the 60 sessions before that day): a 2017 image lists every root
  fetched only from 2020 at 2020-01-02 (the 20 names, until their earlier years and split rows are adopted), and XSP
  too if its 2017-19 is thin. Pruning keeps files by date, so a partly fetched early year of a name would enter Train
  without it; a build from 2017 therefore takes `--roots` and refuses unless every name there has a `--root-first` on
  or after 2020-01-02 or is named in `--early-names` (only once its split rows are in `league/gym/events.py` and its
  years are complete). It refuses `--early-roots`. The fork prunes with the build's own data tools (pushed to it
  first; the data box may run a fetch's code). images.json records `train_from`, `root_first` and `early_names`.
  The inside check (`images.py verify`, and every build) holds each listed root to its own day, every other name to
  2020-01-02 in an image from 2017, and the image's first chain to its `train_from` exactly; `verify --root-first`
  reads the recorded `train_from`. The Gym reads a store's first Train day from its first chain (`train_first`), so
  a 2020 image's 2019 history sessions stay out of Train, and the pool refuses a Gym box whose first Train day is not
  the swarm's span, both ways. `batch --check --window train` on the running image reports its first Train day
  (2020-01-02). The swarm moves only when `gym.train_from` and `gym.image_checkpoint` change together.
- **The nightly forward job.** `python3 scripts/data/nightly.py run [--day YYYY-MM-DD] [--dry-run]`
  pulls the last trading day (from 01:45 ET) into the data box's store and the gate image only,
  stopping and restarting the backfill around it, re-checkpoints the gate and puts both boxes to
  sleep; `nightly.py schedule` sleeps the data box until the next 06:00Z wake. It is idempotent:
  rerun it after any failure. It refuses the Gym image's box as a target. On the House the supervised
  `nightly.py daemon --state <root>/data --ready-file <root>/gym-forward.json` runs it each night and publishes the
  ready file the swarm reads.
- **The chain's rule** (Oct 1, 2026). The nightly extends the gate image that `<root>/data/images.json` names
  (`gate.current`), and the swarm uses the gate that `swarm.json` names (`gym.gate_checkpoint`). On Sept 29-30 the two
  differed: images.json still named the original five-root gate, the 25-root gate had been adopted through
  `swarm.json` alone, and the ready file's checkpoint silently replaced it. Every gate box then forked from a five-root
  holdout. These rules now keep them together:
  - **Each day names its image.** The nightly records the image it extended with each day (`forward_days[day]`
    `base_checkpoint` and `holdout_roots`, and `base` on each `gate.checkpoints` entry), and the ready file carries
    `base_checkpoint` (the image's first checkpoint) and `holdout_roots` (the roots it was built with). A day finished
    without them (by an earlier release) is completed but not published (`nightly.json` `unpublished`).
  - **The swarm takes the chain only while it extends the named gate.** `settings.load` replaces `gym.gate_checkpoint`
    with the ready file's checkpoint only when `base_checkpoint` equals it and `holdout_roots` covers `gym.roots`.
    Otherwise the swarm uses the named gate itself, with no forward days, and the loop raises one `gate_chain_ignored`
    alert per ignored file. An unreadable file never moves the gate.
  - **A legacy ready file** (no `base_checkpoint`, written before this release) stands only when images.json proves
    the same. Its current gate's first checkpoint must be the named gate, and its recorded roots must cover
    `gym.roots`. The file's checkpoint must be its day's recorded checkpoint, adopted after the image was recorded
    (`forward_days[day].adopted` not before `current.built_at`). It must also be on the image's chain
    (`settings.chain_refusal`): it and every later `gate.checkpoints` entry name the image as `base`, or (an entry
    written before this release) were taken after `built_at`. It need not be the chain's tip, because the nightly
    records a new day's checkpoint shortly before it publishes the day. Production's file at this release is such a
    file (written after the Oct 1 re-base), so the gate does not move at the deploy or at the first publish after it.
    `nightly.py --state <root>/data stamp-ready --ready-file <root>/gym-forward.json [--apply]` writes
    `base_checkpoint` and `holdout_roots` into a legacy file that stands. It needs the daemon stopped, because it
    takes `nightly.lock`. It puts the old file back unless the swarm takes the new one with the same gate.
  - **The nightly never extends a gate that lacks the swarm's roots, or a chain that is not on it.** `run` (and the
    daemon) refuses before any box is woken (`preflight`, before the data box is resumed). It refuses when images.json's
    gate does not list its roots or lacks a root of `gym.roots` (read from `<root>/swarm.json`; the daemon's root is the
    ready file's folder, `run --swarm-root` for a hand run). It also refuses when the chain's tip (`current_checkpoint`)
    is not proven on that gate (`settings.chain_refusal`): the chain records were not reset when the image was
    adopted, and a re-fork of the gate box would carry another image's holdout under this one's name. The refusal is
    the controller's `error` in `nightly.json`, retried every 300 s with no box woken. `schedule` and rehearsals are
    not refused.
  - **A day an earlier release checkpointed** (the daemon was stopped between its checkpoint and its publish) is
    published with its image's name when the chain's records prove it (`Nightly.proven_identity`), and is completed
    without a publish otherwise (`nightly.json` `unpublished`); the next day's publish names its chain.
  - **To adopt a new gate image:** build it (`images.py build gate --roots ...`, which records its roots; or a staging
    build), then point images.json's gate at it with the chain reset, as the operator's Oct 1 re-base did. The reset
    sets `current` to the image's record, `current_checkpoint` to its first checkpoint, `checkpoints` to [] and
    `forward_days` to the `pulled` markers only, and sets `nightly.json` `completed` to {}. Then name the same
    checkpoint in `swarm.json`. Until the nightly publishes on the new chain, the swarm uses the new image itself.
    `images.py build` and `finish` do not reset the chain records; until they are reset, the nightly refuses to run.
- **Gym boxes** are forks of the Gym image checkpoint, sealed, driven through Sail's file and exec
  APIs (`league/gym/driver.py`, `python -m league.gym.batch` on the box). The swarm's pool starts
  `gym.start_boxes` when there is work (4 by default; 2 on the box since Sept 30's throttle), grows to
  `gym.max_boxes` (8 by default; 4 on the box since Sept 30, 6 planned after Release A), sleeps a box after
  ten idle minutes, terminates a box whose image is no longer the configured one, and the Sail guard brakes
  it to zero before the House is at risk. They need no operator step: `swarm.json` sizes the pool, and
  adopting an image is one edit of `gym.image_checkpoint` (with `gym.gate_checkpoint` for its gate partner).
- **One program's failure is its own** (Release A, #440).
  - **Admission.** `check_program` compiles as well as parses, so code that the compiler refuses is refused at the
    House's admission (`researcher.check_code`) with its line. That covers an assignment expression in a comprehension's
    iterable, or an expression nested past the compiler's stack.
  - **The parent's load check.** A program it cannot load comes back `refused` ("the program fails to load: ...") and
    never reaches a worker.
  - **In a worker.** Each program loads on its own, and the engine runs the unit with `isolate=True`. A program that
    fails to load there, or whose run raises (its start, a step, its day's open or close, its result), comes back
    `error` with 0 trials. The unit's other programs run on and return exactly what they would alone.
  - **Still whole-unit failures:** a `MemoryError` (the worker's memory cap is shared by the unit), a worker that dies,
    and the unit's deadline.
  - Before, one program that parsed but did not compile failed its whole 8-program batch twice (14:03Z Sept 30), and
    three failed batches in a row retire a box.
- **Result downloads** (#436). A timed-out or dropped download of a finished result file is retried inside the
  driver's existing attempt limit and backoff, instead of requeuing the batch. TLS, permanent DNS, permission and
  unknown failures are not retried.
- **Volume context** (#431, Release A). `ctx.under.minute_volumes` exposes completed regular-session
  share volume only with first-observation receipts. Finalized historical SIP bars lack these receipts and remain
  unknown in both minute and daily inputs: completion time alone does not exclude later vendor revisions.
  `volume_coverage` names minute/history provenance and counts known/expected bars and prior sessions;
  `volume`, `daily_volumes` and `prior_volume` require complete coverage of first observations. The House persists its observed
  bars and first-observation minutes in `live.sqlite` KV `underlying_volume_session`; `underlying_volume_history`
  keeps the last 60 observed sessions per root, including incomplete-coverage counts and provenance
  `first_observed_session_sum`. A saved daily total without that provenance is unknown. Back up `live.sqlite` as usual.
  No SQL migration, site schema change, new data call, or money-rule change is required. Deploy the matching House
  and Gym bundle together; changed evaluator fingerprints require fresh qualifying evidence. Price-only images
  do not gain usable volume merely by adopting the code. Daily API totals and SPY volume for index roots are not substituted.
  `options_live.summary.volume_error` reports checkpoint/history failures; unknown values remain unavailable after restart.
- **Input capability card** (#432, Release A; the install is a step in **Release A: after promotion**). An
  operator's private Train audit can be installed as
  `/workspace/state/input-capabilities.json`, beside `swarm.sqlite` (use the actual swarm root if different).
  The Researcher family brief and Architect proposal request read it before hypothesis selection. Reads are local
  and cached by file revision; there is no model, data-provider, or Gym query to refresh coverage on a turn. Replace
  the file atomically after an audit. Missing, invalid, oversized (over 128 KiB), or different-image cards report
  unknown coverage; changing `gym.image_checkpoint` invalidates the old counts immediately. A new card does not
  by itself wake event-held families; an image change or an explicit `research_wake` does.
  Schema 1 requires `image_checkpoint`, ISO `audited_at`, `train_from`, `train_through`, `raw_file_count`,
  `raw_volume_file_count`, `raw_complete_volume_sessions`, `point_in_time_verified_volume_sessions`, and `roots`.
  Each root has `train_sessions`, `raw_volume_sessions`, `raw_complete_sessions`, `asof_verified_sessions`,
  `raw_first`, and `raw_last` (both null when no raw volume). Counts must reconcile across roots; other audit fields
  stay private and are not rendered as prompt instructions. Raw counts/date coverage and verified as-of counts are
  labeled separately; the current historical reader loads no volume receipts, so all historical strategy volume
  remains unavailable even with a matching card. No image, SQL or public-site schema change is needed for this card.
  Generate audits from nonsealed Train inputs/metadata only; never infer coverage from holdout/forward prices.
  The measured card itself belongs in private state, not in the repository or a public checkpoint.

  **Future replay receipt requirement (not implemented here):** the current-day volume KV is overwritten on the
  next session, and 60 daily aggregates cannot reconstruct first observations. Replay needs an append-only private
  archive per root/session/bar of the first accepted value, its bar interval and first-available decision minute,
  plus the actual receive timestamp, source/feed, and the extraction/evaluator version. Preserve session calendars,
  explicit gaps and polling failures, restart/duplicate identity, and a content hash so later vendor corrections
  cannot silently replace an observation. Persist each receipt before day rollover with restart-safe idempotency;
  retain the minute series as long as the evidence using it. Archive completeness must itself be measured. Current
  KV rows preserve values and decision minutes, but lack wall-clock receive/source receipts and durable multi-day
  minute history. Any future replay ingestion needs a reviewed as-of schema and explicit evidence-window policy;
  live observations must not silently enter the sealed historical Train image.

## Real money

Real money has been on since R2 (00:30Z Sept 27): `real_money` is true in `league/config.json`. The
House opens real only under the active grant, with the kill switch off and the gates below.

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
by other users. The real and Candidate programs share one child and one memory allowance (2 GB), so a hung
or exhausted child can cost all of them that minute. The observe band's programs run in a second child (1 GB),
asked after the real decisions. A minute whose budget is spent skips a request without killing a child. Loads,
pipe writes, decisions and recovery share at most 40 seconds, clamped to five seconds before the next minute.
Recovery after a timeout happens within a later request's budget.

Release A (#443) hardens the decider:
- **Off a root House it refuses to start a child.** Only tests and a developer's machine pass
  `allow_unisolated=True`, in code: there is no switch.
- **A failed namespace probe is never cached.** A probe that fails or times out is retried at a spawn at least 30 s
  later. The probe's timeout is 3-10 s whatever is left of the minute, so a nearly spent minute can overrun by at most
  3 s. While a failed probe stands, the root House refuses the spawn: "the production decider requires a network
  namespace under its separate uid; the namespace probe failed and is retried ...". The next minute, or the 60 s retry
  of a failed real instance, probes again. There are about four chances before a real instance's positions become
  orphans for the House to close, which happens after five minutes.
- **The child's limits:**
  - any file it writes is capped at 64 MB;
  - it can start no process or thread;
  - a write past the cap fails, and does not kill the child.
- **Logs:** `live-decider.log` and `live-decider-observe.log` at 32 MB or more are moved to `<log>.1` before a spawn, so
  the two files hold at most twice the cap.

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

The checked-in deployment has `real_money: true`, the grant is active on `a3e2aa7c`, and the gateway's
`OPTION_STRUCTURES_REAL` names the four debit types. The gateway still admits paper structures and
verified closes of held real positions; `off` is still a permitted stricter setting in `league.ci`. The
paper route proof runs from 09:35 ET until it has passed, even with no real-account client, grant or
eligible family, and keeps an unfinished attempt's identity and owned contracts through restarts. Both
proofs (the multi-leg vertical and the single-leg call) passed on Sept 28; a passed proof is not run
again. Passing records paper execution evidence, never a family's evidence.

**The money table (the sprint, owner decision D4, Sept 26, 2026)**: real types under $2,000 of equity are
exactly `debit_vertical`, `long_butterfly`, `long_call`, `long_put` (the credit types come back only with a
deposit to $2,000, in one deploy with the gateway, and a re-ratified grant); Probe 5% of equity a structure
with a $100 one-contract floor, 3 open, 15% the family; the book 90%; daily stop 35%, drawdown stop 60%;
tuition $200 a day; the D3 calibration's day bounded at $50 of possible loss. The gateway's per-order cap is the lower of
$1,000 and 25% of equity (at $1,473.11 of sizing equity: $368.27; 5% is $73.65, so a Probe's $100 floor
applies), 100% of equity opened a day, 250 of 300 orders open.

**The single-leg paper proof**: once the vertical's has passed, the practice account opens and closes a
1-lot SPY call about 1-2% out of the money (nearest expiry at least a day out, at the natural, held two
minutes) with single-leg orders. Real long calls and puts open only after it (`paper_proof_single`).

**Two-sided single families (`long_single`, #425; ships in Release A)**: a family may declare `long_single`, one
program whose every open is one `long_call` or one `long_put` (one leg, long), the side chosen by its rule,
in place of a call/put twin pair. It is a declared structure, never an order type: the money table's
`real_types`, the money digest (`a3e2aa7c`) and the gateway's `OPTION_STRUCTURES_REAL` are unchanged, and
none of them may name it. The live path maps it to real (tuition, Probe, Sized, the site's `real_structure`
check) only while BOTH `long_call` and `long_put` are real types (`money.order_types`, `Table.family_real`,
`Table.family_allowed`); drop either and the family is held at Candidate with the reason recorded. Every
order it sends still carries its own type and is checked (`type_allowed`, the single-leg paper proof, the
gateway) and sized by its own unit, exactly as a one-sided family's. Its declared type is enforced on real
opens only: the live path refuses a real open of any other type from it ("a long_single family opens only
long_call or long_put for real, never ..."; `money.DECLARED_TYPES`, the instance's `structure`, read at each
sync). The Gym and the shadow book never read a family's structure: there, as for every family, each order is
judged by its own type, and a one-sided `long_call` or `long_put` family is unchanged everywhere. Its forward
record, D2 and the drift screen are any family's (it is only as drift-neutral as its side rule: the screen
charges whatever net exposure it holds). The site shows the agent's structure as null (the site's schema has only the
eleven order types) and each of its positions as `long_call` or `long_put`. The Gym is unchanged: it never
reads a family's structure, so its bundle version does not move.

**The practice league** (the observe band). The league's code was merged Sept 29-30, 2026 through #431 and deploys with
Release A. The running release still has the older observe band, which admits only validated versions.
- **Who:** every alive Gym-band family with a validated version, or with an eligible Train version (the version the
  tournament validates next, not demoted).
- **How:** it trades the shadow book on live quotes as `<family>@<version>:o`, on a $10,000 practice account. Its program
  is frozen in `observe.sqlite` before the first decision. Session admissions are in `live.sqlite` `observe_pins`.
- **Never** real, tuition, a forward row or a band move. Two code guards hold this (Release A, #437):
  - an observe instance is only ever a shadow, non-tuition `:o` instance (`Instance.__post_init__`);
  - the order path refuses any instance that is not real, with an error alert: "live: `<key>` is not a real instance and
    asked for a real order: refused".
- **When:** its programs load and decide after every real decision of the minute, in their own decider child (1 GB).
  Its chains are read after the real path, under the minute's data budget.

- **Tiers and order.** The validated tier by validation t, then the Train tier by Train score (highest first, unknown
  last), then by id (`bands.priority`). `live.observe_train` false leaves the Train tier out and winds its pins down at
  the next families pass.
- **Two caps.** `live.observe_max` instances (48) and `live.observe_roots_max` distinct roots (24). Roots bind first:
  every root is read every minute at about 1.1-1.5 data calls, and holds a full-day grid in the House (about 3 MB, at
  most 28 MB). A family whose roots would pass the roots cap is skipped, not stopped at: a later family on roots already
  read may still join. A cap lowered at runtime keeps the first families pinned. The held-back families are said once a
  day (`live.observe` {capped, why: "cap" | "roots"}).
- **Measured** (the House, read-only, 13:33-13:50Z Sept 29): 1 vCPU, 4,284 MB, 3,510 MB available; the House 135-141 MB,
  the swarm 470-513 MB, the observe child 36 MB; a minute of 1 real and 7-8 observe instances took 2.4-3.5 s end to end,
  a decision under 50 ms; 11-16 data calls a minute for about 11 roots against the observe phase's 40. 24 roots is about
  30-36 observe calls a minute. Expect 7-20 instances, not 48: eligibility is hard and families live hours.
- **Degradation.** As before: at most 16 loads a minute above a 10 s floor; observe reads stop at
  `live.observe_read_calls` (40; raise it with the roots cap, about 1.5 calls a root) and at 3 pages and 5 s a root;
  a `BudgetSpent` batch waits a minute. New: when 3 of the last 10 session minutes were **pressed** (the observe batch
  skipped or failed, or an observe read skipped), the lowest-priority quarter (at least one) of the Train-tier pins is
  shed for the rest of the session, at most once every 10 minutes, and no new family joins past what is left
  (`observe_shed` in the live state, so a restart keeps it; one `live.observe` {shed, effective_cap, why} and one
  alert). Validated pins are never shed. The next session admits surviving frozen cohorts at the full caps.
- **Frozen cohorts.** Research retirement and newer revisions do not terminate a cohort. It finishes between sessions
  after at least three observed sessions and ten program closes while flat; otherwise its maximum is ten session days,
  extended to cover the program's declared DTE horizon plus three sessions, bounded at sixty. An expired snapshot never
  rejoins; a newer eligible version may. Switches, caps and pressure can still wind it down. These are practice durations,
  not capital gates (`OptionsLive` config `observe_min_sessions`, `observe_min_trades`, `observe_max_sessions`).
  Snapshots pin the Gym bundle and fill model. If either changes, old cohorts become close-only and their wind-down
  outcomes are excluded from program feedback. The family/version ledger currently requires a newly eligible source
  version for fresh practice after an evaluator change; it never mixes evaluators into one successful cohort.
- **Private receipts.** `observe.sqlite.events` records decisions, coverage, intents, rejections, orders and fills with
  leg quotes, fees and slippage against decision mid. The shadow account saves unacknowledged receipts and retries
  idempotently after a restart. Events retain 120 days; a prolonged ledger outage has a 10,000-event per-account buffer
  with an explicit dropped count. This private market data is never published. Program errors are `missed_errors`,
  separate from missed quotes and budget; they do not count as successful decisions.
- **The record.** `/workspace/state/observe.sqlite` (0600): `trades` (one row a closed practice trade: its session,
  exit reason and `forced` when the House closed it winding down) and `practice` (one row per family and version from
  its first live minute, kept after the family retires: tier, lineage, structure, roots, sessions, minutes, decisions
  due / made / missed for want of quotes / missed for want of the budget / program errors, the per-minute marked P&L's peak and drawdown,
  open positions at the engine's mark). Realized P&L is the headline; open positions are apart, at the mark.
- **Who reads it.** Nothing that feeds evidence or money (the gate, the verifier, the bands, the money table, tuition,
  Profit). The swarm reads its summary as a research signal (`league/swarm/practice.py`: the strategist's PRACTICE table,
  the architect's PRACTICE BY CLASS lines, the bandit's bonus: at most +25% of a family's share and at most 10% of all
  share moved). `family_feedback` also supplies researcher context after ten program closes over three close-session
  days; its revision token changes on a new close day or another five closes, so idle researchers can wake on meaningful
  observations. `practice.feedback` false turns these off. The site shows its aggregates (`practice`, below).
- **The forward embargo.** Because practice feeds research, a Sized move also needs the forward record of the sessions
  after the later of its version's creation and selection (`banded_at`) to meet Sized on its own (`OptionsLive._move_band`; held moves are `live.band` {held}
  rows). The whole record still decides negative, Candidate and Probe.

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
`swarm.json` `{"live": {"calibration": true}}` turns it on (on since 00:31Z Sept 27).

How samples may change the Gym (Sept 28, 2026): only through the frozen recalibration protocol, PROTOCOL-v2
(private; sha256 `10f78877…`). Real calibration fills move the Gym's patient-fill table only through a
pre-registered, held-out test: even sessions fit, odd sessions test, at most four looks, sessions as the unit.
Adoption needs significance, no root or patient cell getting worse, and the Gym never more optimistic than real
fills on price. The owner committed in advance to adopt on a passing look without first seeing any strategy's
results under the new table (sha256 `befe90dc…`). The first test session is Tuesday Sept 29. The tool is private.
`live.calibration_samples` is 100 (the owner, Sept 28): the same $50 a day bound, months of sampling, a 1.5x
error in a cell's fill rate caught about half the time (at 30 samples only a 2x error is caught), false adoption
0-1%.

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
- **State:** on since 00:17:28Z Sept 29, switched on after its analysis script was pinned. It has started. At 14:28Z
  Sept 30 it had used 2 of its 20 sessions and sent no order.
- **After a restart:**
  - a restored House test instance is always `kind` real and `observe` false: #429 restores by keyword, and from
    Release A, `Instance` coerces the flag (#437);
  - its program's own orders pass the order path's belt;
  - after Release A, check `options_live.instances["house:rebound-live@0:h"]` for both.
- While it runs: no House deploy or restart inside the decision window the private pre-registration names (each load
  of its program is a `live.instance` "house test program loaded (fresh memory)" row; one inside that window, a
  decider-child restart or a skipped minute there is a deviation of the test, logged in the private addendum). Before a rollback
  past the release that carries it: switch it off and wait until it is flat (an older release would run it as an
  ordinary instance, export its trades as forward rows and show its positions as an agent's).

**The incubator** (Release B, #451; `league/live/incubator.py`; the money row `options_money.incubator`). This is a new
shadow-to-real route: one lot of real money for a family whose live practice was positive. Its P&L is real, and it is
never evidence.
- **The owner's terms.** Approved Sept 29, 14:51Z; the reading was settled Sept 30. A family that passes Train and the
  drift screen on its own, shows positive live practice, and passed the gate's review and audit, trades one lot of an
  approved real structure: at most $50 of maximum loss a structure, fees included, and at most 4 held or working. The
  route stops for the ISO week once its net realized loss reaches $150. It never promotes: D2 is the only route to
  Probe and Sized.
- **What it trades.** The unit is a practice cohort `(family, version)`. Its frozen snapshot is the program the
  incubator trades, byte for byte, as the real, tuition-flagged instance `<family>@<version>:i`.
- **The first look** (pre-registered; `money.practice_ok`). It is taken once per cohort, at the first session pin at
  which the cohort's record before today holds at least `min_sessions` (3) completed sessions and `min_trades` (10)
  program-closed trades under the running evaluator. It passes only with all of:
  - decision coverage of at least `min_coverage` (0.80);
  - realized practice P&L above $0 over the program's closes;
  - above $0 over all closes;
  - above $0 over all closes plus the open mark.

  The look is saved in the live state (`incubator_verdicts`) first, and only then recorded as a private `live.incubator`
  `first_look` row (with the program and run sha it judged), whether or not the switch is on. A failed look is final. A
  cohort with a `first_look` row under the running evaluator is never looked at again, even if its saved verdict were
  lost: the verdict is restored from the row as recorded, and a recorded `ended` row still ends it. After a pass, each
  later session re-checks coverage and the three P&L tests on the longer record, and a failure ends the incubation for
  good. A program with no edge passes roughly a third to a half of the time: the weekly envelope bounds the cost, not
  the screen.
- **The swarm's facts** (`league.swarm.bands.incubator`). The family must be:
  - alive, in the Gym band, with the version not demoted (at 1.5x or by drift);
  - carrying a Train-and-drift pass for the version under the current evaluator and Train objective, with a positive
    1.5x Train P&L;
  - reviewed and audited by the gate on the version's run sha, under the current review contract;
  - not refused, failed or demoted by the gate on that sha;
  - not on D2's route: a validated version that met the line gives it a tuition row, which comes first.

  **The reader's belt** (`bands.incubator_refusal`, with B2 #444) comes first and reads the verdicts themselves, not
  only the mark, so a program whose review or audit failed never trades the incubator (the owner's term). There is no
  row for a program the swarm barred (`incubator_barred`: bars are kept for good, and no evaluator adoption clears
  them), one the gate's `review` names without a readable pass and a passed audit (a pass whose audit is still owed
  waits), one whose incubator review or audit failed or was revoked, a version the gate refused at any stage, a program
  whose holdout look failed, or a family whose verdict records cannot be read. These are read for the PROGRAM (the
  same code and params, so the same run sha) in every family that holds it, alive or retired, and a program the gate
  owes a bar is refused too (`incubator-bars-owed.json` beside the swarm store, written only when the store errs; if it
  cannot be read, every incubator row is refused until the gate writes it again). The swarm start backfills bars from
  release B's gate events (log line `incubator backfill: N programs barred`), and an evaluator adoption records every
  failure it would clear before it clears it. The swarm reads the belt's own rules in every other family holding the
  program before it marks a version or pays for an incubator review (`incubator.program_bar`, Release B'), so it never
  pays to review a program the belt would refuse. Another family's gate review that passed with its audit still owed
  holds the program off until that audit lands, and for good if that family retired. This is not a verdict: nothing is
  recorded and no passed review is revoked.

  An unreadable store refuses: no pin and no open, while exits go on. B2 (#444, in Release B) writes the
  Train-and-drift pass and the incubator's reviews.
- **Pins,** at the session's first families pass. A restart reuses them, and nothing joins mid-session. At most 8
  cohorts, one per family, by first-look return on risk. Each needs:
  - the switch on and real money on;
  - a first look that passed, and a record that still passes today;
  - an active cohort with its program unchanged;
  - the facts, with the snapshot's run sha;
  - no D2 route for the family (`:r` > `:t` > `:i`);
  - a real structure;
  - at least one sampled program close that one lot could open under the $50 cap.

  Every families pass checks again, and a failure sends the instance to exits only, its working opens cancelled.
  `health.json` `options_live.incubator.pins.refused` says why each passing cohort was not pinned.
- **Keep (L2').** While the switch is on, a cohort whose first look passed keeps practising past its observation target
  to its bounded window (at most 8), so its re-checks go on. Off, the practice league's own rule is unchanged.
  - **A failed read never ends an incubation.** Sometimes today's check cannot be taken: the cohorts or a cohort's
    record cannot be read, or the first looks raise. Then the last keep's cohorts that no re-check ended stay kept, and
    so does an active cohort whose first look could not read its record (first look or not, and across a restart).
    A cohort kept without a verdict (its first look unread, or waiting for the next session's record) stays kept for
    the rest of the day, a restart after the day's retries included. It is never a pin candidate, and its look is
    taken at the next session's first pass.
  - While the cohorts themselves cannot be read, and on a pass where the keep raises, the practice league completes
    no cohort at its observation target (`observe.HOLD`). That is practising only, for that pass, and only while the
    day's retries remain. After them the carried keep (or, if the keep still raises, the last saved keep) alone is kept
    and the rest of the league completes by its own rule; one error alert a day says so. If the saved keep cannot be
    read either, the House keeps the last keep it took itself, or, if it has taken none since it started, completes no
    cohort at its target. It never falls back to keeping nothing, which would complete pinned cohorts.
  - Such a cohort is never pinned on the untaken check. `pins.refused` says so, and a private `live.incubator` event
    (`unread`, `keep_carried`) and one alert a day record it. A failed ledger write never changes the keep.
  - The keep is marked `unread` (health `keep_carried`), and the next families pass, 5 minutes later, takes the checks
    again, for at most 12 counted passes after the day's first. After that the day's keep stands and the next
    session's first pass reads again. Pins are still taken once a session.
  - The day's passes are counted durably in the live state (`incubator_session`: day, passes, the last counted pass's
    time, the day's waiting first looks), written at the START of each in-session families pass, before the bands or
    anything else is read. A pass whose reads all fail still counts, and a restart keeps the count.
  - A pass counts only 5 minutes (`FAMILIES_EVERY`) or more after the last counted one. A pass forced sooner (a forward
    read that fails, a band not confirmed, the decider losing a program, a restart) reads again but spends no retry, so
    the 12 retries span at least an hour.
  - Within a day the keep only grows. A cohort kept at an earlier pass leaves it only when a check ends it (or its first
    look fails) or its cohort is no longer active, so a pinned cohort is never completed mid-session. A cohort held on
    an untaken check is kept beyond the 8 and never takes the place of one checked that day.
  - **Every first look and re-check reads the record before today, never today's values**, at the session's first
    pass or at a retry alike, whatever failed before it. `observe.practice_record` leaves out today's closes and
    today's session, and it reads the practice row's decision coverage and open mark as its last session before today
    left them. The practice row keeps those (`prior_due`, `prior_made`, `prior_open_mark`), copied at the first minute
    of each new session day and stamped with that day (`prior_day`, the day of the copy, not the day the values came
    from). They are read only when `prior_day` is today. So a retry reads the same before-today record as the first
    pass, plus any before-today closes recorded since (a trade written again after a failed write, a missed expiry
    settled on its day): today's mark can neither end an incubation nor pin one.
  - A record that cannot say what its row held before today (`intraday`) decides nothing on P3 or P6. That is a row
    stepped today before those columns were kept (only around the release), or one stepped today by a release that never
    copies them, as after a rollback to release A: its `prior_day` is then an earlier day, and its values an older
    session's. A re-check then ends only on P4 or P5, evaluated whatever P3 says, and is otherwise `deferred`: kept, not
    pinned, and re-checked at the next session's first pass. A first look then fails only on P4 or P5, and otherwise
    waits, kept, for the next session's record. It is never taken again that day.
  - The first pass of a session day that cannot pin is retried every 5 minutes, not every minute. That covers the bands,
    the observe band or its cohorts being unreadable, and the incubator's pins raising. A restart asks again at once,
    and switching the observe band on mid-session still pins it at the next minute.
- **The caps** (`money.plan_incubator`, with the tally read afresh from `live.sqlite` at every open). They live in the
  House only: the gateway cannot tell routes apart, so its caps are the backstop.
  - One lot; at most $50 a structure; at most $50 held or working per family.
  - At most 4 structures held or working.
  - **The weekly envelope:** this ISO week's net realized loss, plus what is held, plus what is working, plus the new
    unit, at most $150 at every open. Once the week's net realized loss has reached $150 at any close, the route is
    stopped until the next ISO week, a later gain notwithstanding. The stop is alerted once a week: "live: the incubator
    its net realized loss this week reached $X, at or over $150: stopped for the rest of the week (exits go on)".
  - 40 order legs a day, and 25% of the gateway's day cap.
  - Room kept in the book's and the day's caps: two Probe floors ($200) and, while the House live test can still open,
    its structure ($100).

  The $150 is a true bound apart from residuals: broker fees above the book's estimate, and a broken structure closed
  leg by leg.
- **The order of a minute.** The D2 families' intents go first (`:r`, `:t`), then the incubator's, then the House live
  test's, then the calibration's. A working incubator open is cancelled, recorded "yielded", when a D2 family's real
  order is refused on one of its contracts after the open was placed. The House live test yields to an incubator
  refusal as to a family's.
- **Never evidence.** Its rows are tuition-flagged, but never in tuition's own day and week sums. It is never:
  - a forward row;
  - a band move or a promotion;
  - read by the swarm.

  Its positions are Profit, on the site with the source "incubator" (the agent's id as an agent's).
- **The belt.** An `:i` instance must be real, tuition-flagged, on a House with an incubator, and its route is its key's
  alone. Anything else that asks for a real order is refused before the venue, with an error alert: "live: `<key>` is
  not a real tuition incubator instance and asked for a real order: refused". A restored `:i` instance is
  tuition-flagged whatever its row says.
- **The cost.** Expected value is negative until a family has a real edge: at most about $650 a month on average ($750
  in a five-week month), plus residuals.
- **The switch:** `live.incubator` in `swarm.json`, off by default. Only JSON `true` turns it on; any other value reads
  off and is alerted once. Switch it on only outside a session, after the ratification. Off takes effect within a
  minute: exits only, and working opens cancelled. First looks are recorded either way.
- **Where it shows:**
  - `health.json` `options_live.incubator`: the switch as last read, the table, today's pins and refusals, the keep,
    the verdict counts, the tally and the weekly stop;
  - `options_live.instances[...].incubator`;
  - `python3 -m league.live --root /workspace/state --incubator`, read-only: the switch as `swarm.json` says, the pins,
    every first look with its P1-P6 values, the tally, the instances and today's refusals;
  - private `live.incubator` ledger rows: first looks, ends, pins, yields and the weekly stop.
- **To stop it,** in order of reach:
  1. `live.incubator` false (within a minute);
  2. `max_open`, `week_loss_usd` or `max_loss_usd` set to 0 in the money table: a tightening, so a new digest, an
     owner deploy after a close and a ratify. The constitution is outside the fingerprint, so it is no evidence reset;
  3. `python3 scripts/gateway_admin.py kill`, which stops every route.
- **Earliest possible open:** Tuesday Oct 6, 13:30Z, for cohorts that begin practice on Oct 1 (sessions Oct 1, 2 and 5).
  B2 is live with Release B.

**L1, the cohort keep** (Release B, #445; `league/swarm/tournament.py`, `league/swarm/practice.py`; research side). So
that a family is still alive when its cohort's sample is complete, the tournament spares a living Gym family with an
active practice cohort. It is spared the revision, evaluation and idle rules, and the idle pass, until the cohort
completes, fails or reaches its session window.
- **The record it reads** is the cohort's realized record before today, under its own evaluator. Until the cohort meets
  the incubator's sample (3 sessions, 10 program closes), it is kept whatever that record says. After that, it is kept
  only while program-closed P&L and all-closes P&L are both at least 0.
- **Not kept:** a cohort the House has not practised on 2 sessions while it practises others, or one whose practice row
  began before it.
- **At most `tournament.incubator_keep_max` (12) families;** 0, null, a boolean or a string turns it off. Those that
  meet the sample come first, by return on risk.
- **The incubator's cohorts come first and are never cut by the cap** (Release B', `tournament.incubator_held`). These
  are cohorts that met the sample with a record that is not negative, and whose program the swarm's own incubator
  facts admit (`bands.incubator`, the reader the House pins by). Every cohort the House can pin (L2', at most 8) is one
  of them. The swarm never reads the House's live state, so it cannot see which ones were pinned and holds them all
  (at most 96). So the keep never holds fewer families than the House can have pinned, and a pinned family is never
  retired because a cohort with a higher return took its place. If the facts cannot be read, every cohort past the
  sample is held for that read. The saved keep (`cohort_keep`) lists them under `held`, and a fresh process whose
  first read fails keeps those families first, beyond the cap.
- **What it never spares:** the deflated-Sharpe rule, the researcher's or the diagnostician's own retire, the
  population floor, and the operator's gate hold.
- **Its record:** one private `swarm.status` event a round (`incubator_keep`), with each kept family, the rule it was
  spared, and `held`, the incubator's cohorts' families, when there are any.
- **The researcher's status line.** The keep is saved (`cohort_keep` in the swarm's kv), so a kept family's researcher
  is told that idleness is no reason to retire it. The retire tool stays offered.
- **An unreadable record.** When `observe.sqlite` or the swarm's families cannot be read, the last good keep stands for
  an hour (`KEEP_STALE_SECONDS`), then none does, with one alert in the round's event. A fresh swarm process (a deploy,
  a restart, the induced-failure kill test) runs its idle pass at once; if its first read fails, it takes the keep the
  last process saved (`cohort_keep`, read `stale` in the event) for the rest of that hour and does not overwrite it
  before then, so a restart never retires a kept family on one failed read.
- **Research attention only:** no trial count, look, validation, gate, band or money rule reads it.

**Turning real money on** (M4b; the sprint's R2; done: the grant was enabled at 00:30:15Z Sept 27, re-ratified at
$1,473.11 after the deposit and on `a3e2aa7c` at R7): the gateway deployed first (`OPTION_STRUCTURES_REAL`
`debit_vertical,long_butterfly,long_call,long_put`, `MAX_ORDER_EQUITY_SHARE` 0.25); then the owner deploy with
`real_money` true (a new money digest); `python3 scripts/live_trading.py --enable` (first time), then `--ratify`
within a minute. Then the House promotes Candidates that qualify to Probe within five minutes (`live.band` rows). Real
entries still require the paper route proofs' witnessed round trips.

### Pre-open (each trading day, 12:00-13:25Z; first run Sept 28)

1. **The box** (`python3 scripts/floor_box.py status`, then on the box): the loop and supervisor up;
   `health.json` `options_live.summary.state` is "before the open", `options_live.instances` lists every
   Candidate's shadow instance and every Probe's real one with no `error`; `/workspace/.venv/bin/python -c
   "import numpy"` works; `live-decider.log` has no traceback; `release` is the release you expect.
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
   JSON object; after 13:30Z `options_live.observe.pins` lists the session's families with their `tiers` and
   `roots`, and `options_live.observe` shows `roots_used` under `roots_max` and `effective_cap` (no `shed`);
   `observe_reads_skipped` stays 0 and `budget_spent` {}; `observe.sqlite` `practice` has a row per pinned family and
   version; `live.sqlite` has no `:o` order, position or instance and `swarm.sqlite` `forward` no `:o` id; after the proofs,
   `paper_proof_single` passed; after 14:00Z `options_live.calibration.slots` and
   `python3 -m league.live --root /workspace/state --calibration`; `options_live.house_test`: `files`
   verified, `wanted` as intended, and no stop or end you did not expect; from Release B,
   `python3 -m league.live --root /workspace/state --incubator` (the switch as intended, the pins and first looks,
   the tally within its caps, no weekly stop you did not expect) and no `:i` id in the swarm's `forward`.
6. **The Probe list**: `live.band` rows since the last session (who became Probe or Sized and why; who
   stayed a Candidate and why: not through the holdout, a type real money does not open, a credit type
   under $2,000, a typical structure over the Probe's cap or unknown). It must match the run record's list.
   Bands move only while real money is on and the grant active, and a family moved onto real money trades
   from the NEXT session: only families promoted before the open trade that session.
7. **The day**: a full session or a half day; any FOMC, CPI or jobs release; which admitted roots have
   0DTE expiries. No deploy from 13:25Z to 20:05Z except a rollback.
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
  multi-leg order. Legging out is a last resort. An assigned short leg becomes shares: an OPASN or
  OPEXC activity latches `assignment_latch`, which freezes real entries, and the owner is told. The
  House closes the shares at once (the gateway admits stock orders only to close assigned shares) and
  closes the structure's other legs alone. The latch lifts by itself once no broken structure and no
  shares remain and reconciliation is clean; `python3 -m league.live --root /workspace/state
  --clear-assignment` lifts it by hand.

From Release A:

- **The error alert "live: `<key>` is not a real instance and asked for a real order: refused"** (#437). A bug put a
  non-real instance (a practice `:o` shadow, a Candidate's shadow, or an instance whose observe flag is not False) on the
  real order path. The belt refused it before anything reached the venue, so nothing was sent.
  - Treat it like a reconciliation error: read that instance's `live.refusal` rows and the live state
    (`python3 -m league.live --root /workspace/state`).
  - Do not switch anything on to make it go away.
  - It repeats once per intent a minute while the bug stands, loud on purpose.
- **"the production decider requires a network namespace under its separate uid; the namespace probe failed ..."**
  (#443). The root House could not make a network namespace for the decider child in time, so the spawn was refused.
  - This is not cached: the next spawn at least 30 s later probes again.
  - One such line on a busy minute needs no action.
  - If it repeats for several minutes, real instances will be orphaned and closed after five. Check the box's load, and
    that unprivileged network namespaces work for uid 65534: the probe runs `unshare --net --map-root-user true` as
    that uid. A House restart does not fix a box that refuses namespaces.
- **"generated programs run only as uid 65534 in a private network namespace (a root House)"** (#443). A `Decider` was
  built off a root House. On the House it means the House is not running as root; fix that. It never runs generated
  code unisolated.
- **A Gym result `refused` with "the program does not compile" or "the program fails to load"** (#440). It is the
  program's own code, for example code that parses but that the compiler refuses. Admission now refuses such code with
  its line, so the family's researcher sees the reason and fixes it.
- **A Gym result `error`** (#440), 0 trials, with any of these reasons:
  - "the program failed to load in its worker";
  - "the program failed to start";
  - "the program's run stopped on an error".

  It names an engine-side exception on that one program. The other programs in the batch are unaffected, and their
  results are what they would be alone. Look at it as a possible engine bug, and keep the reason text: it is the only
  signal.
- **`pool.batch_failed`** (Release A). It should now mean box, transport, deadline or memory trouble: a dead worker, the
  unit deadline or a `MemoryError` still fail the whole unit. It should no longer mean one bad program. A timed-out or
  dropped download of a finished result is retried inside the driver's attempt limit before the batch is requeued
  (#436).
- **"swarm: funding: ..." warnings** (#439): a funding cliff ahead. The next section, **Funding cliffs and alerts**,
  explains them. They are warnings, never errors, so the watchdog never rolls a release back over one.
- **"the site refused the practice league block or Claude's own compute part ..."** (#441). The site predates
  personal-site PR #17. The House sent it the older shape: no practice block, and Claude inside `other_usd`. It offers
  the newer shape again in 30 minutes. Deploy the site; nothing is lost.
- **"the site refused the swarm window ..."** (the swarm window, Oct 1, 2026). The site predates the window (personal-site
  `capital/swarm-window`), or it refused an entry. The House sent the checkpoint without `levels` and `rationale` and
  offers them again in 30 minutes. Deploy the site; nothing is lost. If the deployed site should take it, read the reply
  the warning quotes; `curl -s 'https://blakewoods.us/api/capital/checkpoint?progress=1&positions=1&practice=1&window=1'`
  shows what the site serves.

From Release B:

- **"live: `<key>` is not a real tuition incubator instance and asked for a real order: refused"** (error). A bug put an
  `:i` instance that is not a real, tuition-flagged one on the real order path, or a non-`:i` instance claimed the
  route. The belt refused it before anything reached the venue. Treat it like the observe belt's alert above: read the
  instance's `live.refusal` rows and `--incubator`, and switch nothing on to make it go away.
- **"live: the incubator's facts could not be read (...)"** (warning, once). The swarm store could not be read, so no
  incubator pin or open happens until it can; exits are unaffected.
- **"live: the incubator could not read the practice cohorts; no first look and no new pin until it can"** and **"live:
  the incubator's first looks failed (...)"** (warnings). That pass takes no first look; the practice league goes on
  under its own rule.
- **"live: the incubator's pins failed (...)"** (warning). That pass wants no incubator instance, so its instances go to
  exits only until a pass succeeds.
- **"live: swarm.json live.incubator is X, not true or false: the incubator reads OFF"** (warning, once). Fix the value.
- **"live: the incubator its net realized loss this week reached $X, at or over $150: stopped for the rest of the week
  (exits go on)"** (warning, once a week). The weekly stop latched, as designed. It lifts at the next ISO week; nothing
  is to be done.
- **A library call refused with `cap` or `busy`** (in `swarm.research` events). `cap` means the gateway's day of arXiv
  requests (`LIBRARY_DAY_UPSTREAM`) or a House line is spent; `busy` means arXiv's one-at-a-time queue was full. Both
  are plain refusals. A long run of `busy` or a `backoff_until` in `/v1/research/health` means arXiv asked us to slow
  down: leave it.

## Funding cliffs and alerts (Release A, #439)

The swarm says each funding cliff ahead of time (`league/swarm/funding.py`, `FundingWatch`, on the swarm's main loop
right after the Sail guard's reading). It changes no route, line, hold or guard decision.

| Cliff | Measured as | Leads: notice / warning / urgent |
|---|---|---|
| Claude's room (`claude_room`) | runway: the room above `claude.reserve_usd`, less `funding.claude_out_usd` ($2), over the measured burn | 48 / 24 / 6 h |
| The Sail guard (`sail_guard`) | runway to the guard's brake line, from the guard's own reading | 72 / 24 / 6 h |
| The OpenAI month (`openai_month`) | calendar: the next UTC month boundary, while the gateway's frontier month has room | 48 / 24 / 6 h |
| The burst's end (`burst_end`) | calendar: `guard.burst_until`, with the research cut that `after_burst_usd_day` implies; said only when there is a cut | 96 / 24 / 6 h |

**Burn.** The measured burn is the larger of the last 24 hours' and the last `funding.burn_window_hours` (6) hours'
rate. It comes from the swarm's booked spend and from the meter's own fall between samples taken every ten minutes. A
top-up is a rise, never negative spend. Because it takes the larger rate, the runway errs early: right after a pace cut
it looks shorter than the new pace implies.

**Tiers:** notice, warning, urgent, then out once the cliff is here.
- **Rises:** a rise to a tier not yet said is said at once. Warning, urgent and out repeat every `funding.repeat_hours`
  (12) while they stand. A calendar cliff's out is said once.
- **Falls:** a fall is silent. A fall of two tiers or more (a top-up) makes the tiers above it news again.
- **Recovery:** a recovery past `funding.clear_factor` (1.5) times the first lead is one `funding_ok` event, and the
  cliff is forgotten.
- **No burn:** a runway with no burn measured is shown as state `no burn`, with no tier. It neither clears nor repeats
  an alert.
- **Sail braked:** while the Sail guard is braked and its balance is under its release line (the line plus
  `guard.release_margin_usd`), the Sail cliff stays out, with state `braked`.
- **Restarts:** what was said is kept in the swarm store, so a restart repeats nothing.

**Fallbacks.** Every call that asked Claude and ended somewhere else (the next route, Sail, or no route) is counted by
role, Claude failure kind and route.
- Each key is said the first time it appears as a `claude_fallback` event, then at most every 6 h with the count since.
- Only `no_room` (a funding cliff) is an alert.
- A role's own daily line (kind `line`, such as the architect's $0 line since Sept 30) and errors are events without an
  alert.

**Where it shows:**
- **Swarm events:** `swarm.status` events with `action` `funding_alert` or `claude_fallback` (and `alert` true only for
  alerts), or `funding_ok` for a recovery.
- **The House:** the House mirrors them into its private ledger and turns each alert into an `ops.alert` at level
  warning, reading "swarm: funding: ...". `scripts/floor_watch.py` shows it.
- **The heartbeat:** the last assessment of each cliff (tier, hours, room or balance, burn, projected time) is under
  `status.funding` (`python -m league.swarm status --root /workspace/state`).
- **The site:** nothing is published, and no key, account number or secret is read.
- **Swarm store keys:** `funding_alerts`, `funding_fallbacks`, `funding_samples` and `funding_openai_seen`.

**Settings.** Set them in `swarm.json` `"funding"`, read every tick, with no deploy:
- `enabled` (true);
- `every_seconds` (300);
- `fallback_flush_seconds` (30);
- `lead_hours`, keyed `claude_room`, `sail_guard`, `openai_month` and `burst_end`;
- `repeat_hours` (12);
- `clear_factor` (1.5);
- `claude_out_usd` (2);
- `burn_window_hours` (6);
- `after_end_hours` (48: a calendar cliff older than this is not announced);
- `fallback_every_seconds` (21600).

A value that is not a finite, non-negative number is its default. On a gateway hang, the check's meter refresh can hold
the swarm's loop for up to the meters' 20 s timeouts, at most once every 5 minutes.

## Switches

| Switch | Where | Now | What it does | How it changes |
|---|---|---|---|---|
| `real_money` | `league/config.json` | true (since R2, Sept 27) | real orders at all | owner deploy |
| `auto_update` | `league/config.json` | false | the in-box updater; a missing key means off | owner deploy |
| `live_trading.ceiling_usd` | `league/config.json` | 5500 | the grant's capital ceiling | owner deploy, then `--ratify` |
| `performance.start_at`, `start_equity` | `league/config.json` | 06:25:30Z Sept 26, $481.65 | the profit baseline; equals the site's `PERFORMANCE_START_AT` | only with a site reset |
| `gym.enabled`, `swarm.enabled` | `league/config.json`, overlaid by `swarm.json` | false in `config.json`; true in `swarm.json` | the Gym and the swarm in the House's tick | edit `swarm.json`; a change of `enabled` takes a House restart (`config.json` `swarm._about`) |
| `swarm.json` | `/workspace/state/` on the box | present, mode 600 | the swarm's throughput and budget settings and the live switches, re-read every loop (the live path each minute), no deploy; never the evidence lines | edit it on the box, keeping a before-copy |
| `options_structures.book`, `practice_account` | `league/config.json` | options-shadow, false | which book structures practise on | owner deploy of a release changing only that key |
| `PAUSE` | `/workspace/state/` | absent | the maintenance pause | `floor_box.py maintenance` |
| `STOP`, `state/STOP` | `/workspace/` | absent | the loop ends | `floor_box.py stop` / `start` |
| `swarm.stop` | `/workspace/state/` | absent | the swarm process leaves and is not restarted | create / delete it |
| Kill switch | the gateway | off | every real order-creating call refused | `gateway_admin.py kill` / `unkill` |
| `MAX_ORDER_MAX_LOSS_USD`, `MAX_ORDER_EQUITY_SHARE`, `MAX_DAY_EQUITY_SHARE`, `MAX_DAY_ORDERS`, `MAX_DAY_OPEN_ORDERS` | `gateway/wrangler.jsonc` | $1,000, 0.25, 1.0, 300, 250 | the real account's caps by maximum loss; equal to the constitution's `options_money.gateway` | gateway deploy with the matching House deploy |
| `OPTION_STRUCTURES_REAL` | `gateway/wrangler.jsonc` | `debit_vertical,long_butterfly,long_call,long_put` | the types real money may open; must equal the constitution's `options_money.real_types` (`league.ci`) | gateway deploy with the matching House deploy and a ratify |
| `LIBRARY_DAY_UPSTREAM`, the `LIBRARY` KV binding | `gateway/wrangler.jsonc` | 600; namespace `ltcm-gateway-library` (Release B) | the research library's requests to arXiv a UTC day for the whole floor (`"0"` stops them; cache hits still answer), and its cache | gateway deploy; never delete the namespace |
| `live.observe`, `live.observe_max` | `swarm.json` on the box | true, 48 (since 13:36Z Sept 29) | the practice league (the observe band) and its instance cap (default 48); read each minute, no deploy (a swarm.json that is not a JSON object turns it off) | edit `swarm.json` |
| `live.observe_train`, `live.observe_roots_max`, `live.observe_read_calls` | `swarm.json` on the box | defaults: true, 24, 40 (from Release A) | the Train tier; the distinct roots the league may read (1-128); the minute's data calls before observe reads stop (10-200; unset: the step's own 40) | edit `swarm.json` |
| `practice.feedback`, `sessions`, `bonus`, `bonus_total`, `min_trades` | `swarm.json` on the box | defaults: true, 10, 0.25, 0.10, 3 (from Release A) | the practice league's research feedback: the strategist's table, the architect's lines, the bandit's bonus (code ceilings 0.5 and 0.2); off: none of the three | edit `swarm.json` |
| `live.calibration`, `live.calibration_samples` | `swarm.json` on the box | true, 100 | the D3 round trips (still only with real money on, the grant and the paper proof); samples a symbol's open cell (the mid, or the patient mid at 12:00 and 14:00) stops at (defaults false, 30) | edit `swarm.json` |
| `live.house_test` | `swarm.json` on the box | true (since 00:17:28Z Sept 29) | the House live test (still only with real money on, the grant, the paper proof and its private program verified); off: exits only | edit `swarm.json` |
| `live.incubator` | `swarm.json` on the box | true (since 04:01Z Oct 1); default false (Release B ships it off) | the incubator (still only with real money on, the grant, a passed first look and the swarm's facts, which B2 writes); only JSON `true` is on; off: exits only, working opens cancelled within a minute; first looks are recorded either way | edit `swarm.json`, and switch on only outside a session |
| The House live test's program | `/workspace/state/house-test/rebound-live/` on the box | present, verified | the frozen program and its params, hash-checked against `league/live/house_test.py` `FROZEN` | the operator's private upload script, `--apply` |
| `FRONTIER_MONTH_USD`, `FRONTIER_MONTH_MAX_USD`, `FRONTIER_FUNDED_MONTH` | `gateway/wrangler.jsonc` | $707, September 2026 only; not topped up again (the owner, Sept 29), so $0 from Oct 1 | the OpenAI month; expires before an unfunded month can renew it | gateway deploy |
| `CLAUDE_USD`, `CLAUDE_MODELS` | `gateway/wrangler.jsonc` | $265 (since Oct 1: the owner topped the account up to a $100 balance against $165.26 spent; $200 from 05:29Z Sept 29); Opus 5.5, Sonnet 5, Sonnet 5.5 | the Anthropic account's funded total (never resets) and the priced models (the allowlist) | gateway deploy after the owner adds funds |
| `claude.model`, `claude.usd_cap`, `claude.max_tokens` | `swarm.json` on the box | `claude-sonnet-5-5` (since 04:53Z Sept 29), 198 (since 05:29Z Sept 29), 32000 | the swarm's Claude model, its own lifetime Claude line inside `CLAUDE_USD`, a call's output ceiling (defaults `claude-opus-5-5`, 100, 16000) | edit `swarm.json` |
| `claude.roles`, `claude.role_usd_day`, `claude.role_model` | `swarm.json` on the box | architect, audit, diagnostician, rewrite, review, researcher, strategist; lines: architect $0 (since 16:41Z Sept 30: births on Kimi-K3), rewrite $0, researcher $0, review $5, strategist $6, diagnostician $6; audit on `claude-opus-5-5` (since 04:53Z Sept 29) | who asks Claude first; a role's own Claude line a UTC day; a role's own Claude model (defaults since PR #417: architect, audit, diagnostician, researcher; the researcher $100; the researcher on `claude-sonnet-5-5`; the box's `roles` list replaces the default, so the box's research band is off until "researcher" is added to it) | edit `swarm.json` |
| `researcher.claude_top`, `claude_effort`, `claude_max_tokens`, `claude_hold_every` | `swarm.json` on the box | 0 on the box (the band is off); defaults: 12, `medium`, 12000, 3 | the top band on Claude (PR #417): how many of the bandit's top families, at what effort, each call's output ceiling (it sizes the hold), and how often Claude looks during a hold streak (1: every cycle) | edit `swarm.json` |
| `researcher.claude_family_usd_day`, `claude_min_room_usd`, `claude_timeout_seconds`, `claude_breaker_failures`, `claude_breaker_window_seconds`, `claude_breaker_pause_seconds` | `swarm.json` on the box | defaults: $15, $25, 180, 3, 3600, 3600 | the band's fuses: one family's Claude a UTC day, the funded room left to the other roles, one call's limit, and the breaker (unknown bills in the window that pause the band, and for how long) | edit `swarm.json` |
| `gate.review_openai_model`, `gate.audit_openai_model` | `swarm.json` on the box | null, null (since 04:53Z Sept 29) | the review's and the audit's OpenAI route; null skips it (defaults `gpt-6-sol`, `gpt-6-astra`) | edit `swarm.json` |
| `architect.openai_model`, `every_seconds`, `refill_seconds`, `max_refill`, `max_output_tokens` | `swarm.json` on the box | null, 1800 (since 02:47Z Oct 1; 900 before), 1200, 12 (since Release A, Sept 30; 4 from 16:07Z), 32000 | the architect: null leaves it Claude first (Sail's Kimi-K3 as the fallback, and its route while `claude.role_usd_day.architect` is 0); its cadence, its refill below `population.start` and each pass's births (defaults `gpt-6-astra`, 14400, 3600, 12, 12000) | edit `swarm.json` |
| `architect.sail_effort` | `swarm.json` on the box | unset: `medium` (Oct 1; before it, `high` was hard-coded) | the architect's reasoning effort on Sail (Kimi-K3) and OpenAI; Claude's is `claude.role_effort` / `claude.effort`. One of `minimal`, `low`, `medium`, `high`, `xhigh`; anything else reads as `medium`. At `high`, from 08:15Z Oct 1 every pass spent the whole 32,000-token output on reasoning and came back cut, most with no text; the same request at `medium` completed in 66 s with 12 carded families. A cut Sail answer is salvaged like a Claude one (its complete families born, fewer than 3 buy the one retry on Claude alone), and the pass's `swarm.architect` event says its `effort`, its `usage` (input, cached, output and reasoning tokens) and, when cut, its `incomplete_reason`. At `medium`, k3 sometimes writes stray trailing commas (`,}`, `,]`) into a complete answer; when the strict read finds no `families` array and the families object has such a comma, the architect reads it again without them, from the `{` that opens that object (`read_families`; the event says `lenient`), where before it read as no proposals (11:57Z Oct 1). Any other unreadable answer still reads as none. The operator set this key to `high` in `swarm.json` at 12:00Z Oct 1 (with `architect.max_refill` 6, which completed with 6 proposals a pass) until the re-read deploys | edit `swarm.json` |
| `population.start`, `ceiling`, `floor` | `swarm.json` on the box | 96, 96, 12 | the refill target, the most alive, the fewest retirement may leave (defaults 48, 96, 16) | edit `swarm.json` |
| `gym.start_boxes`, `max_boxes`, `train_from`, `image_checkpoint`, `gate_checkpoint` | `swarm.json` on the box | 2, 6 (since Release A, Sept 30; 4 from 16:07Z), "2020-01-02", the sealed 2020-24 image, its gate partner | the Gym pool, Train's first day and the images (defaults 4, 8, unset, none, none: the gate is off without a gate image). `train_from` takes "2022-01-03", "2020-01-02" or (since R11a) "2017-01-03"; the derived split and time limit are 8 and 900 s, 16 and 1500 s, 24 and 2400 s | edit `swarm.json`; `train_from` and a new image together |
| `researcher.sail_usd_per_hour`, `usd_per_hour`, `top_families` | `swarm.json` on the box | 1.3 (since 02:47Z Oct 1; 1.1 from 16:41Z Sept 30; 12 before), 5 (not read while the Sail pace is set), 0 | the researcher pace (below) and the bandit's top band (defaults null, 4.0, 10) | edit `swarm.json` |
| `researcher.retire_idle_evaluations`, `dormant_cycles`; `tournament.retire_revisions`, `retire_evaluations` | `swarm.json` on the box | 500, 12; 200, 4000 | the idle rule and its dormancy clause; the tournament's retirement (defaults 150, 40; 30, 2000) | edit `swarm.json` |
| `tournament.incubator_keep_max` | `swarm.json` on the box | default 12 (Release B, L1) | the most families the cohort keep spares from the revision, evaluation and idle rules (at most 96), beside the incubator's cohorts, which it never cuts (Release B'); 0, null, a boolean or a string turns it off | edit `swarm.json` |
| `guard.burst_cap_usd`, `burst_until` | `swarm.json` on the box | $900, 2026-10-05 | the swarm's Sail spend for the research burst (the owner's 24/7 research, Sept 27); the $32 line is unchanged (defaults $350 until Monday Sept 28's open) | edit `swarm.json` |
| `diagnostician.enabled`, `usd_day`, `per_round`, `family_hours`, `min_validations`, `near_miss_checks` | `swarm.json` on the box | false (since 16:41Z Sept 30), $60, 6, 3, 2, 5 | the diagnostician on or off; its Claude spend a day, families a round, how often a family, who is eligible (defaults true, $15, 2, 6, 2, 6) | edit `swarm.json` |
| `researcher.stall_revisions`, `rewrites_per_day` | `swarm.json` on the box | 10000 (since 16:41Z Sept 30: stall rewrites off; 12 before), 1 | the stall that buys a researcher one rewrite from a stronger model, and at most how many a family a day (defaults 5, 4) | edit `swarm.json` |
| `claude.role_effort` | `swarm.json` on the box | `{"architect": "medium"}` (since Release A, Sept 30; it matters only while the architect has a Claude line) | a role's own Claude effort when the caller names none (R11b; default `{}`: `claude.effort` for every role, so the gate keeps "high") | edit `swarm.json` |
| `architect.max_alive_per_class` | `swarm.json` on the box | default 12 (R11b) | the most living families of one mechanism class (structure x root group); `admit` refuses births past it; 0 or null off | edit `swarm.json` |
| `architect.structures` | `swarm.json` on the box | default null: every type (Oct 1) | the structure types a birth may be. `"real"` reads the allocator's `allocation.real_structures` (one list for both, so a change of the account's real types is one edit); a list such as the gateway's real types (`["debit_vertical", "long_butterfly", "long_call", "long_put"]`) also admits `long_single` (a list must then change beside `allocation.real_structures`). The architect's and the strategist's GAPS and coverage show only these (a list naming one side alone makes that side a gap), the architect's request names them and its BIRTH QUOTAS show only their structure families, `admit` refuses any other type and the next request names each refusal still outside the list (kv `architect_structure_refusals`); the tournament forks and the loop's founding seeds and reseeds are only of these types, and a living family of another type keeps researching until a rule retires it. The pass's event: `structures`, `structure_not_allowed` by type, `structures_ignored` (a value naming no known type is ignored whole: every type) | edit `swarm.json` |
| `researcher.retire_hold_cycles`, `retire_hold_trials`, `extension_hold_checks` | `swarm.json` on the box | defaults 3, 10, 6 (R11b) | the hold offer (retire after that many holds in a row with an eligible Train run or that many trials); the extension hold (a validation with that many checks met is exempt from the dormancy clause until cleared); 0 turns each off | edit `swarm.json` |
| `researcher.probe_year`, `probe_timeout_seconds` | `swarm.json` on the box | default null (off), 300 (R11b) | the Gym's zero-trade probe: 2022 switches it on | edit `swarm.json` |
| `tournament.exploit_per_positive` | `swarm.json` on the box | default 0.15 (R11b) | the bandit's exploit share a positive old family earns; null: `explore_share` alone, as before | edit `swarm.json` |
| `researcher.hold_until_news`, `retire_min_trials` | `swarm.json` on the box | defaults true, 10 (Release A, #431) | durable holds that only new evidence wakes (false: the R4 timer); the trials after which a researcher may retire its family | edit `swarm.json` |
| `researcher.retire_guard_days` | `swarm.json` on the box | default 14 (Oct 1) | the validated-family guard: a researcher may not retire a family that holds a version which passed the validation line (in its state, in the tournament's verdict records, or archived by any evaluator adoption) last validated within this many days, unless a later validation of that version failed the line; a number at or below 0 turns it off; null, a boolean or a string reads as 14 | edit `swarm.json` |
| `funding` (`enabled`, `every_seconds`, `lead_hours`, `repeat_hours`, `clear_factor`, `claude_out_usd`, `burn_window_hours`, `after_end_hours`, `fallback_every_seconds`, `fallback_flush_seconds`) | `swarm.json` on the box | defaults (Release A, #439): on, 300, per cliff, 12, 1.5, 2, 6, 48, 21600, 30 | the funding cliff alerts (**Funding cliffs and alerts**) | edit `swarm.json` |
| `research.enabled`, `requests_day`, `family_requests_day`, `cycle_calls` | `swarm.json` on the box | defaults (Release B, #447): false, 300, 12, 2 | the research library on the House, and its lines: calls a UTC day for the floor, a family, a research cycle (**The research library**) | edit `swarm.json`; on only after the gateway and the House that carry it |
| The money rules | `league/constitution.py` | the sprint's D4 table and the House live test's bounds (money `a3e2aa7c`); Release B adds the incubator's row (`42c4a3af`) | what real money may do | owner deploy, then `--ratify` |
| `options_money.incubator` | `league/constitution.py` | from Release B: `max_loss_usd` 50, `contracts` 1, `max_open` 4, `week_loss_usd` 150, `min_sessions` 3, `min_trades` 10, `min_coverage` 0.80 | the incubator's caps and its pre-registered practice rule; each row may only tighten, and 0 in `max_open`, `week_loss_usd` or `max_loss_usd` stops the route | owner deploy, then `--ratify` (no evidence reset) |

In `swarm.json`, `researcher.sail_usd_per_hour`, when set, is the researcher pace: the Sail models' spend over the
trailing hour (1.1 on the box since 16:41Z Sept 30; 12 from Sept 29), and `researcher.usd_per_hour` is then NOT read
(the box's 5 is inert). Absent or null, `usd_per_hour` paces Sail models and OpenAI together. OpenAI holds still count
against its own burst cap and funded gateway month. Claude is outside the research pace: it has its own lines
(`claude.usd_cap`, `claude.role_usd_day`, `diagnostician.usd_day`) inside the gateway's funded total. Invalid,
nonfinite or negative limits pause research. The heartbeat's `status.researcher_pace` reports the scope, limit, spend
and pause reason, so a quiet research loop can be distinguished from a publication delay.

A Gym researcher can call `retire(reason)` to abandon its whole family, but only on a READ turn while more families
live than `population.start` and the family has had at least two validations (Sept 26: an unguarded retire on the
REVISE turn took the population from 49 to 16), or while more live than `population.floor` and the family is dead by
the idle rule (R3, Sept 27; `researcher.idle_dead`): `researcher.retire_idle_evaluations` (default 150, 500 on the
box; 0 or null turns the rule off, in `swarm.json` without a deploy; a boolean or a non-number also reads as off) Gym
evaluations since its birth or last validation without an eligible Train version, or three times as many with its best
Train score below zero. It counts evaluations, not versions: the store keeps one version for identical code and
parameters, so a family re-running one placeholder makes trials but no revisions. A family whose validated version
awaits the gate (`gate_ready`) or whose holdout look is out is never dead. With the population held at its start, dead
families never qualified before and looped on placeholder runs (the operator retired 48 by hand on Sept 27). The
tournament retires a dead family that never calls retire by the same rule, down to `population.floor`; the architect
refills below `population.start`. The graveyard lesson and the public cause say the idle rule retired it; since R11b
the lesson carries the verdict of its Train record (DRIFT, STRESS, THIN or EXHAUSTED, tested findings), and only a
family that never traded on Train is "a time limit, not a refutation" (IDLE). The family's own last notebook lines carry
its researcher's verdict.

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
`researcher.dormant_cycles` (default 40, 12 on the box; 0 or null turns it off) cycles made no new Gym evaluation,
only stored results, holds and runs refused for its own doing (its program, NEEDS, params or variants), is dead (the
same floor, gate exemption and graveyard wording), unless its best awaits validation (not yet validated and not lost
at 1.5x). A new evaluation of its own restarts the count as soon as it is recorded (in the cycle, or when a run lands
after the wait), and so does a counted validation. A cycle that asked the Gym for a new evaluation the Gym did not
make (a Gym error; a run, or every new variant of a sweep, that did not land) leaves it, and a sweep whose new
variants all failed is a Gym error even when some of its variants were read back from the store. A sweep refused for
room leaves it too, unless the cycle also held, got a stored result or had a run refused. The count is zero outside
the Gym band, and a Candidate sent back to the Gym starts afresh. A holding cycle is one model call, so 40 of them can
pass in well under an hour of a family's cycles; the count is the family's state `dormant_cycles`, and each dormant
cycle's `swarm.cycle` event carries it.

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

The gate's data (Oct 1, 2026). A look needs the gate image to hold the holdout of every root the program needs. On
Sept 30, three looks of a GOOGL/MSFT program failed with "no holdout days for GOOGL, MSFT". Each counted as a try, and
the third wrote a stage "gym" refusal that bars the program from the incubator, although no verdict was made.
- **Each gate box lists its holdout when it starts**, by file name only (holdout-dated `nbbo/<ROOT>/*.parquet` and
  `underlying/<ROOT>/*.parquet`; no file is opened and the gate's capability is never minted). Its roots with the
  image's full count of both (the count most roots have, 184 sessions on the current images) are the box's
  `holdout_roots` (the `boxes` row and the `box_ready` event); a root copied only in part is not among them. A holdout
  job needing another root fails at once as missing data. A store with no holdout at all fails the box, records the
  image as holding none, and fails the holdout looks waiting for a gate box as missing data. The pool keeps the
  coverage per gate image in kv `gate_coverage`, with the roots any Gym exit-3 answer named since ("no holdout days
  for GOOGL, MSFT in ..."). An exit-3 answer that names no root (no store, a missing package) is a fault of the box,
  not missing data: it is not recorded, and its look fails and counts a try as before. An image that lacks a root of
  `gym.roots` raises one `gate_coverage` alert.
- **The record is per image**, keyed by `gym.gate_checkpoint`, so each nightly publish starts a fresh one. To clear a
  record that is wrong (say a Gym fault that named roots the image holds), drop that image's entry from kv
  `gate_coverage` on the House:
  `s=SwarmStore('/workspace/state'); c=s.get('gate_coverage') or {}; c.pop('<checkpoint>', None); s.put('gate_coverage', c)`.
  The next gate box lists the image again.
- **The gate refuses a look up front** when that record, or the ready file's `holdout_roots` while its chain is the
  gate, says the image lacks a root the program needs. No look is marked, no try is counted, nothing is refused,
  `gate_ready` stays, the round lists the family under `waiting`, and one `gate_missing_data` alert is raised per
  program, image and gap (kv `gate_missing:<run_sha>`). The look runs once `gym.gate_checkpoint` names an image that
  holds those roots (a new image starts with no record).
- **A look that fails for missing data all the same** (the first look on an image no gate box has listed yet) is owed
  again on the same terms: no try, no refusal, no incubator bar, the same alert.
- **Any other failure counts a try** (kv `look_tries:<run_sha>`, kept by program). The third writes the "gym" refusal
  and its incubator bar, as before. The `look_failed_three_times` alert now fires at every count from three on (its
  `tries` field says which). A fourth failure, as when a revived family runs the same program, therefore parks the
  version loudly instead of silently. After fixing the gate, reset the count: on the House,
  `SwarmStore('/workspace/state').put('look_tries:<run_sha>', 0)`.
- **A look that never reached a gate box** (the queue gave up on it after the run timeout because no gate box became
  ready) still counts a try. The try is the loop's bound: a look holds the gate's round for up to the run timeout, and
  gate boxes have no probe fork to find the image back. A store with no holdout is the one start-up failure that is
  missing data (above).
- **Sept 30's leftovers are not changed by this release.** The GOOGL/MSFT program of
  `googl-lags-msft-ai-cloud-qqq-flat` v27 still has `look_tries` 3, the stage "gym" refusal row and its incubator bar,
  from three failures this release treats as missing data. The revived `-r` family runs the same program. A single
  real failure there makes the count 4 and parks it at once (with the alert). Reset the count once the gate is right
  (above). Whether the refusal row and the bar stand is the owner's call: should an infrastructure refusal bar a
  program from the incubator?

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
`pro_asap`, null turns it off), `researcher.top_reasoning_effort` (`low`), `researcher.top_families` (10; 12 on the
box since Sept 29) and `researcher.top_max_output_tokens` (12000) put the bandit's top families on the stronger Sail
profile inside the same hourly pace; `architect.agenda` (default empty) closes every architect request as the
operator's research agenda (at most 4,000 characters; the box's agenda, v14 since 02:30Z Sept 29, steers where to look
and changes no evidence line or kill test; its text stays private); `population.reseed_max` (default 0, off) founds
the seeds' mechanisms again on roots they never tried while the population is below its start and the architect is not
due; `tournament.require_robustness` (default true) validates a version only after its 1.5x Train robustness run came
back with a profit. The robust Train objective, its robustness runs (1.5x and mid, at the pool's lowest priority,
never starting or keeping a box awake) and the D2 validation line are code, not settings. The objective's one-time
migration beats the heartbeat while it runs, skips a family it already moved and empties (never keeps) the best of a
family it cannot rescore.

## R11b: honest verdicts, corrections that land, effort where it pays (Sept 29)

R11b was merged through #431 and ships in Release A. The operator's steps after it are in **Release A: after
promotion**.

### Goal continuation: event-driven research and reachable retirement (Sept 30)

The goal continuation keeps the R11b fixes and adds these defaults without changing models, funded budgets or any
promotion threshold:

- `researcher.hold_until_news: true`: a hold is stored in `family.state.research_wait`. Time and process restarts alone
  never schedule another paid call. New trials, gate state, a rewrite, notebook guidance, the agenda, data image or
  harness release can wake it. To deliver explicit new guidance, append a factual notebook note or change the family's
  `research_wake` state token. `false` restores the optional R4 timer. A worker with nothing ready inspects local state
  every few seconds; this does not contact a model.
- `researcher.retire_min_trials: 10`: a researcher may retire after this many counted trials, or after two validations,
  on either its REVISE or READ turn. It need not spend three holding cycles to receive the tool. All researcher and
  diagnostician retirements use the atomic `population.floor`. `population.start` only governs refilling. Pending gate
  work and extension/operator holds remain protected, and so is a best Train version that awaits validation (Oct 1, H1;
  `awaiting_validation`, the dormancy clause's own exemption: not validated, not lost at 1.5x, not failed by the drift
  screen): the tool is not offered, a call is refused with the reason (the cycle's record carries `retire_awaiting`),
  the status says so in place of any offer, and the diagnostician's retire defers the same way; the tournament's
  verdict, pass or fail, ends it, and so does a demotion. On Oct 1 seven of the ten families that made a drift-passing
  Train version had retired themselves before the tournament validated it. The tournament's own rules, operator
  retirements and `SwarmStore.retire_gym` are unchanged (a 1.5x run that never lands must not make a family no rule
  can retire). The floor prevents concurrent retirements from draining the
  population. The agent must explain abandonment, and all prior evidence remains.
- The validated-family guard (Oct 1, `researcher.retire_guard_days`, default 14): the retire tool refuses while the
  family holds a version whose latest validation passed the line, last validated within that many days (the
  tournament keeps each version's latest verdict and its evaluator in `validation_verdicts`). A pass counts wherever it
  is held: the family's line, a passed record in `validation_verdicts` (no adoption clears it and no other version's
  validation replaces it), `previous_evaluator_selection`, and the selection each adoption within the window archived
  in its own append-only `evaluator_adopted` event. So a second adoption, which overwrites
  `previous_evaluator_selection` with the selection the first one already cleared (the House adopted at Sept 30 20:08Z
  and again at Oct 1 03:51Z), never lifts it. An archived pass counts only while it is still that version's latest
  verdict: a record of the version (always its newest verdict) or a newer adoption's archive that shows it failed
  refutes it. So a version that passed under one evaluator and failed its re-run under the next stays refuted after a
  third adoption. A version whose validation time is unknown guards only from an adoption's archive, counted from that
  adoption. A
  failed holdout look does not end it (the gate retires nobody; the tournament's rules still apply). The refusal says
  why and, for a version passed under an earlier evaluator, returns its program to re-run unchanged; the status says so
  in place of any offer to retire, and the prompt says an evaluator change is never a reason to retire. It exists
  because googl-lags-msft-ai-cloud-qqq-flat, the only D2-tuition family, was retired by its own researcher 17 seconds
  after the Sept 30 20:08Z adoption. Operator retirements, the tournament's rules (the deflated-Sharpe rule and the
  idle rule among them), the diagnostician and the population floor are unaffected.
- `gym_run` and every variant of `gym_sweep` receive the static experiment-contract check before any version or Gym job
  is created. Changed parameters that are provably unread, invalid override types and malformed declarations return
  an actionable refusal without consuming a replay trial. A valid zero-trade control remains admissible.
- Graveyard format 4 limits economic claims to the versions actually tested. Drift-screen failure means the required
  alpha beyond exposure was not demonstrated. `UNRESOLVED` identifies missing/failed robustness evidence, rather than
  falsely labeling an execution failure a measured stress loss. The digest reseals automatically. Run the existing
  graveyard migration dry-run and review its counts before applying it to pre-R11b idle deaths.

At deployment, verify `holding` families remain on the same cycle count without new evidence, then verify a genuine
new result or guidance note wakes its family. Inspect retirement events to confirm tested families can exit below the
refill target while the living count remains at or above the floor. The zero-trade probe remains off by default; no
model migration or additional service funding is part of this change.

The ROI audit and plan of Sept 29 (the operator's `scratch/roi/PLAN.md`, section (b)) found the swarm's inputs untrue in
places: 99% of the dormancy deaths filed as "a time limit, not a finding" had been screened on Train, the strategist read
them as untested, and its 13:10Z correction was voided by a family id. R11b is research-side only: no file under
`league/live`, the gateway or the constitution changed, and the money digest stays `a3e2aa7c`. Train figures only (D2).

- **The idle rule's verdict (R11-1).** An idle-rule death is filed under what its Train record shows
  (`researcher.train_record`, from the family's `best_train`, `drift_failed`, `robust_failed`, `robust_why` and its Train
  rows' `train_eligible` and `trades`): DRIFT (its eligible versions failed the drift screen), STRESS (they lost at 1.5x
  the half-spread), THIN (it traded, never 40 trades on 20 days in every Train year), EXHAUSTED (it reached a Train
  score, then ran dry). Only a family that never traded on Train keeps IDLE and the old words. The public cause of a
  tested death is "Retired by the idle rule after its Train record was screened." The digest (format 3, one reseal)
  tags each row by its verdict and says in its header that they are tested findings; the ladder shortens DRIFT, STRESS
  and THIN rows with no Train score exactly as it shortened those IDLE rows, and its id lists name each verdict. The
  strategist's evidence carries `screen` (scored, drift, stress, thin, untested) per family in place of
  `eligible_train_version`, and its SYSTEM text says DRIFT, STRESS, THIN and EXHAUSTED are tested.
- **The hold offer (R11-1).** A Gym family that held `researcher.retire_hold_cycles` (3) cycles in a row with an eligible
  Train run, or `researcher.retire_hold_trials` (10) trials, behind it is offered `retire` on its REVISE turn too, down to
  `population.floor` (the floor rule is unchanged). Every retirement a researcher calls is SELF-REFUTED in the graveyard
  ("Self-refuted by its researcher: " and its reason; its last notes follow as before).
- **The migration (R11-1, once, the operator's).** `scripts/graveyard_verdicts.py` re-heads the rows already buried from
  the same function. Run it on the box right after the release is promoted and before the next architect pass, so the
  digest reseals once:
  `/workspace/.venv/bin/python /workspace/current/scripts/graveyard_verdicts.py --state /workspace/state` (a dry run:
  counts by verdict and clause, examples, the digest's ladder before and after), then the same with `--apply` (a backup
  of every changed row in `state/backups/graveyard-before-verdicts-<UTC>.json`, mode 600; compare-and-set in one
  transaction; the seal emptied; the tags counted after). `--rollback <backup> --apply` restores. On the Sept 29 03:51Z
  graveyard (809 rows) enriched with the ROI extracts, 473 of 474 IDLE rows re-head (305 DRIFT, 92 THIN, 50 EXHAUSTED,
  26 STRESS) and the ladder stays at level 0.
- **The strategist's corrections land (R11-2).** Every known graveyard or family id in a section is masked before the
  content rules read it (an id is a name). The prompt asks for about 85% of `strategist.max_chars` ("at most 1,600
  characters; about 1,350 is right"); the validator still checks the cap, and a section refused for its length alone and
  at most 15% over is cut at its last sentence end inside the cap and validated again (the event's `trimmed`), instead
  of paying for a repair turn.
- **The class cap (R11-2).** `architect.max_alive_per_class` (12) living families of one mechanism class (structure x
  root group, the strategist's `mechanism_class`); `admit` refuses births past it whatever the agenda says, the request
  names the full classes, and the pass's event counts the refusals (`class_capped`).
- **Per-role effort and truncation salvage (R11-3).** `claude.role_effort` {role: effort} applies when the caller names
  no effort; `claude.effort` stays the default (the gate keeps "high"). After the deploy, set
  `claude.role_effort.architect` to "medium" in `swarm.json`; roll back by removing the entry. An architect answer cut
  at max_tokens keeps its complete families; fewer than 3 buys one retry on Claude alone at medium effort. A cut never
  falls to a Kimi-K3 refill: a retry Claude has no room or line for leaves the pass, and the next pass routes as usual.
  The event's `truncated` says what was salvaged and retried.
- **The bandit exploits only positive evidence (R11-5).** Only an old family whose latest validation mean is positive is
  in the exploit pool, each earning at most `tournament.exploit_per_positive` (0.15) of the share; the explore pool (new
  families, and old ones at zero or below drawing from their own posterior) takes the rest, never less than
  `explore_share`. It replaces the A4 stopgap (`explore_share` 0.75): with it, return `explore_share` to 0.25.
- **The zero-trade probe (R11-6).** Off by default: `researcher.probe_year` 2022 in `swarm.json` switches it on. A new
  version's first Train run at the normal spread is then preceded by a run over 2022 on the family's first root; a probe
  with no trade is the answer ("disqualified: no trades in the probe year", one trial, a `probe` run row that no Train
  score, best or drift screen reads), and the five-year run is skipped; the same program asked again is answered from
  that row. A probe that trades, fails or does not answer in `researcher.probe_timeout_seconds` (300) says nothing and
  the full run follows unrecorded. `gym_run` full=true skips it; sweeps and 1.5x runs are never probed. The risk is a
  false negative (a program that trades only in other years or roots): watch `probe` in the cycle events.
- **The extension hold (R11-4's swarm rule).** A validation that meets `researcher.extension_hold_checks` (6) of the
  line's checks sets the family's `extension_hold`, and the family is exempt from the dormancy clause while it stands
  (for the version its latest validation judged). The operator clears it once the 2017-19 extension result lands:
  `scripts/extension_hold.py --state /workspace/state` lists the holds and the alive families that met the checks before
  the rule shipped; `--seed --apply` holds those; `--clear FID ... --apply` ends a hold (the version is never held again
  on the same Gym; the state keeps `extension_cleared`). From Release B (#453):
  - a validation of the held version that falls below the checks ends the hold (`extension_lapsed`), and a later one
    that meets them holds it again;
  - an adoption that changes the Gym's image or bundle archives and clears these records, and one that changes only
    `league/live` keeps them.

Checks after R11b ships (with the plan's 4-hour check): the share of new graveyard rows tagged IDLE (expect under 5%),
strategist acceptance (2 of 3 runs or better) and the largest mechanism class's share of births (expect under 25%),
architect truncations and births per Claude pass, and `probe` outcomes once it is on.

## The research library (Release B, #447)

The agents read the literature through the gateway: arXiv's quantitative finance, econometrics, statistics and machine
learning on markets, posted before 2025 and nothing later. Open web access would let them read about the Validation
year and the sealed holdout and select on them, so they get a library. The date rule is code in the gateway
([gateway/README.md](../gateway/README.md), "The research library"), and the House checks every answer again
(`league/swarm/library.py`). What it does not do: the models' weights already hold 2025 and part of 2026. The library
adds nothing after 2024, but it removes nothing a model already knows ([design.md](design.md)).

- **The gateway.** It serves `GET /v1/research/search?q=&cat=&max=`, `GET /v1/research/read?id=&start=&chars=` and
  `GET /v1/research/health`, with the ordinary gateway token.
  - **Pace:** it keeps to arXiv's terms: one request at a time, 3 s apart on the API, 15 s on arxiv.org.
  - **Budget:** `LIBRARY_DAY_UPSTREAM` (600) requests to arXiv a UTC day for the whole floor; `"0"` stops them.
  - **Cache:** KV, binding `LIBRARY`, namespace `ltcm-gateway-library`. A cache hit is free and answers even at the
    cap; the answer's `X-LTCM-Library` header says `hit` or `miss`.
  - **Health:** `/v1/health` carries the same `library` block as `/v1/research/health`.
  - **The kill switch does not stop it:** it moves no money.
- **The House.**
  - The Claude researchers get a `literature` tool: search, and read. The Claude researcher band is off on the box, so
    it goes unused for now.
  - The architect and the strategist get a retrieved block of abstracts before their calls, and the strategist names
    the next searches. The block is kept 3 hours, so the hourly passes make no new call.
  - Sail's profiles never see it.
  - Every agent cites the ids it relied on. A paper's finding is a hypothesis, judged by Train, the drift screen, the
    verifier and the holdout like any idea.
- **The House's lines** (`swarm.json`, `research`): `requests_day` 300 calls a UTC day for every role together,
  `family_requests_day` 12 and `cycle_calls` 2. A call they refuse is a plain refusal with no request. Each call is a
  private `swarm.research` event (the query or id, the ids served, the status, and whether it counted), never mirrored
  to the ledger.
- **The switch:** `research.enabled`, false by default. The rollout order:
  1. the gateway that carries the library, with its KV binding;
  2. the House that carries the client (Release B);
  3. then `research.enabled` true in `swarm.json`.

  To stop it, set `research.enabled` false: no deploy needed. At the gateway, `LIBRARY_DAY_UPSTREAM` `"0"` stops every
  request to arXiv (a gateway deploy).
- **After switching it on,** check:
  - `swarm.research` events from the architect and the strategist, with status ok and ids served;
  - `/v1/research/health`: `upstream` under `cap`, and `backoff_until` empty;
  - no refusal loop (`cap`, `busy`) in the events.
- **Never delete the KV namespace** once a deployed gateway version binds it: that would block `wrangler rollback` to
  that version.

## Models and Claude

Every paid model call goes through the gateway: Claude against the owner's funded total (`CLAUDE_USD`, $200; it
never resets), OpenAI against the funded month (September 2026 only; $0 from Oct 1). Sail models (DeepSeek, Kimi)
are the inner loop and every role's last fallback but the diagnostician's (it has none). `league/swarm/models.py`
routes a role's call:

- **Claude first** for the roles in `claude.roles`: by default the architect, the gate's audit, the diagnostician and
  (since PR #417) the researcher's top band.
  Since R8 the researcher's stall rewrite and the gate's program review ask for Claude too, so adding "rewrite" or
  "review" to `claude.roles` in `swarm.json` routes them to Claude with no deploy; the box has all five since 04:53Z
  Sept 29. Claude answers while the gateway's total has room above `claude.reserve_usd` (5) and the swarm's own Claude
  spend is under `claude.usd_cap` (198 on the box since 05:29Z Sept 29).
- **The model** is `claude.model` (`claude-sonnet-5-5` on the box since 04:53Z Sept 29, the owner's Sonnet 5.5; the
  default is `claude-opus-5-5`), or a role's own model in `claude.role_model` {role: model id} (the box: the audit on
  `claude-opus-5-5`). A role model must be priced both in `league/claude.py` `MODEL_CEILINGS` and in
  the gateway's `CLAUDE_MODELS`, else the role falls to its next route. Sonnet 5.5's list prices: $2 input, $2.50 a
  five-minute cache write, $0.20 a cache hit, $10 output per million tokens (Opus 5.5: $4, $5, $0.20, $20). Sonnet 5.5's
  default effort is `high` (Opus's is `medium`); the House always sends an effort.
- **A role's daily line**: `claude.role_usd_day` {role: usd}, a UTC day with holds included; a call counts on the day
  its hold was booked, even when it settles after midnight. A call that would pass the line skips Claude for the
  role's next route. No entry is no extra line (the box: the rewrite $15, the review $5). The diagnostician also keeps
  its own `diagnostician.usd_day`.
- **The next routes**: the architect falls to Kimi-K3 on Sail, at `architect.sail_effort` (`medium` by default); with a
  model named in `architect.openai_model` (null on the box), every other pass would ask GPT-6 Astra first, at the same
  effort. A Sail answer cut short is salvaged as a Claude one, and its retry asks Claude alone. The audit falls to GPT-6
  Astra while the OpenAI month has room and `gate.audit_openai_model` names it, then to a second, different Sail model;
  the review to GPT-6 Sol on the same terms (`gate.review_openai_model`), else DeepSeek-V4-Pro on Sail; the stall rewrite
  to its Sail profile. Both gate OpenAI models are null on the box, so no role calls OpenAI; from Oct 1 the gateway's
  month would refuse it anyway.
- **Two readers**: the plan wants two different paid models to read a program before its holdout look. A review or
  an audit on Sail, or one Claude model reading both (with "review" and "audit" both in `claude.roles`), raises the
  gate's `not_the_plans_reviewer` alert (`same_reader` true for the second); the cure is a different
  `claude.role_model` for one of them (the box gives the audit Opus 5.5).
- **The top band on Claude** (PR #417, the owner's Sept 29 decision to use Claude Sonnet 5.5 boldly): the bandit's
  top `researcher.claude_top` families by weight (12) run their research cycles on `claude.role_model.researcher`
  (`claude-sonnet-5-5`) at `researcher.claude_effort` (`medium`), streamed, with `researcher.claude_max_tokens`
  (12000; a call's hold is about $0.31 on a median body) and `claude_timeout_seconds` (180), while "researcher" is in
  `claude.roles`. The loop, the tools, their limits and their semantics are the Sail loop's
  (league/swarm/claude_research.py adapts the tools and the history, checks every input against its schema before it
  runs, and caches the tools, the system prompt and the conversation's tail). A cycle is Claude's when a queued run or
  a rewrite landed in it, when the family's last cycle did not hold, and on every `claude_hold_every`-th cycle (3) of
  a hold streak; the rest of a streak runs on the family's Sail profile. Any Claude failure (a refusal, a cut answer,
  a 402, 403, 423, 429 or 5xx, the researcher's line, the family's `claude_family_usd_day` ($15), the
  `claude_min_room_usd` ($25) left to the other roles, a stream timeout, an input that does not parse or validate, a
  REVISE answer without an offered run, an answer that cannot be read) finishes that turn on the family's Sail
  profile, never a cycle error. THE BREAKER: `claude_breaker_failures` (3) calls whose bill stayed unknown (their
  whole hold booked: a cut stream, a 5xx, a 429) inside `claude_breaker_window_seconds` (3600), or one bill above its
  hold, pause the band for `claude_breaker_pause_seconds` (3600); `kv claude_band` says why and until when (the
  operator can end a pause early by setting its `paused_until` to 0).
- **The band's cost** (a dry estimate, Sept 29: the median top-band request of the last 3 h through this adapter, and
  the top band's measured pace of 914 cycles in 12 h, 1.01 calls a cycle): about $0.051 a call at medium (14,500
  tokens of tools and system read from the cache at $0.20, 9,300 of the family's own written at $2.50, 2,500 output
  at $10), and about 1,050 Claude cycles a day with the hold rule (1,830 without it): about $59 a day at medium
  ($48 at low; $103 without the hold rule, where the $100 line binds), 10% more if the Anthropic workspace bills
  US-only inference (`/v1/health` `claude.geos` shows "us"). The top band's Sail spend falls by about $12 a day.
  After about 50 Claude cycles, read `claude_usage` and `claude_usd` from the cycle events: above about $0.08 a
  cycle, drop to `low` or `claude_top` 6; below about $0.04, consider `high` for the top six or `claude_hold_every` 1.
- **Switching the band on** (the owner's or operator's steps, none done by the code; the runbook is in the PR): deploy
  the gateway (PR #417's tool admission, the US multiplier on every row, the checked body forwarded, overruns counted;
  until then a House tool call is a 400 and falls back to Sail), then the House release; then add "researcher" to
  `claude.roles` in `swarm.json` and raise `claude.usd_cap` by the day's expected Claude spend (the researcher's line
  counts against it; 198 on the box at 05:29Z Sept 29, $82 spent lifetime), and keep `CLAUDE_USD` funded above
  everything else plus `claude_min_room_usd`, `claude.reserve_usd` and one hold. Remove "researcher" from
  `claude.roles`, or set `researcher.claude_top` to 0, to turn the band off.
- **The meters**: `python3 scripts/gateway_admin.py status` (`claude`: the funded total, spent, in flight, remaining,
  holds, the priced models, `by_role`); the swarm's `spend` rows (kind `claude`, by family and role); the
  diagnostician's refusals name the line that stopped it.
- **The spend cut of Sept 30** (16:41Z; the owner's answer was to cut burn to evidence). Claude now answers only the
  gate's review and audit (Opus 5.5 for the audit) and the strategist.
  - `claude.role_usd_day.architect` 0: every architect call takes the role's line and falls to Kimi-K3 on Sail. From
    Release A, the funding watch counts these as `claude_fallback` events of kind `line`, without an alert.
  - The researcher's top band (`researcher.claude_top` 0, the researcher's line $0) is off, and so are stall rewrites
    (`researcher.stall_revisions` 10000) and the diagnostician (`diagnostician.enabled` false).
  - The Sail pace is $1.1 an hour.
  - The evidence behind the cut is in the run record, `docs/runs/2026-09-30-continuous-learning.md`.
  - To undo it, restore the earlier values (CHANGELOG, Sept 30).

## The graveyard

A retired family's lesson (its mechanism, what it tried, its best numbers, its last notebook lines) goes to the
graveyard in `swarm.sqlite`, which researchers search and every architect request and new family reads. Since R8 the
search ranks rows by BM25 (a word's repeats saturate and a long row is discounted, so a long lesson no longer outranks
a short one about the query), and a new family is born with three distinct lessons.

Operator lessons (Sept 29, 2026): the operator's own experiments are in the graveyard as rows with `op-` ids (45 at
04:33Z Sept 29), each dated when its experiment concluded and ending with a "do not re-propose unless ..." line. They
are compiled from private results, reviewed as public-safe, and inserted by the operator's private tool with a backup.
Operator revivals are lineage continuations (origin `operator-revive`): a fork that inherits its lineage's trials and
holdout looks, so the deflated Sharpe and the holdout ration count every version. Since Oct 1 the harness runs the
revived version exactly, with its code and params, before its researcher edits it (**Operator revivals**, above).
Before that fix, the harness never ran a revived program, and a bare `gym_run` dropped its params.

The full graveyard and the strategist (Sept 29, 2026; `league/swarm/architect.py`, `league/swarm/strategist.py`), all in
`swarm.json`. On the Claude route the architect reads every graveyard row as one sealed, cached digest ahead of its own
instructions (`architect.full_graveyard`, default true; `architect.graveyard_digest_tokens`, 100000;
`architect.graveyard_digest_tail_share`, 0.15; `architect.graveyard_digest_ttl`: "5m" marks the digest only when the
strategist's call just wrote it, "1h" marks every call and needs `claude.cache_1h: true`, which is set only after the
gateway admits the 1-hour cache, "off" never marks it). The operator's rows (`op-` ids with no family row; no proposed
family is born with an `op-` id) come first and whole; the other rows shorten on a ladder as the graveyard grows (at the
default budget: every row in full to ~900 rows, idle rows shortened to ~1,600, one line per refuted, diagnosed or scored
row from ~1,800 and fewer such lines from ~3,000, id lists from ~6,500; past ~7,000 the idle ids are cut, with the count
stated). OpenAI and Sail keep the 20 newest rows. Every lesson a model reads loses any sentence about Validation, the
holdout, out-of-sample results or 2025 (`lesson_view`). Each `swarm.architect` event carries `digest` (rows, level, sha,
ttl, `cache_miss`), `usage` and `cited` (proposals naming a real graveyard row). The agenda splits in two:
`architect.agenda_locked` is the operator's preamble, which no model edits; while it is non-empty the strategist runs
before an architect pass that has room (at most every `strategist.every_seconds`, 10800) and writes only the WHERE TO
LOOK section after it (kv `architect_agenda_section`, the previous one kept inside it), every line quoted under a header
that says it changes no rule, the verifier or money. A validator rejects money, real-money or envelope talk, a verifier
word beside a changing verb or a voiding state (paused, advisory, not binding ...), numeric rules, 2025, the holdout or
the Validation period in any words, the operator's voice, overrides and revivals, non-ASCII, and fewer than
`strategist.min_cites` real ids; a rejection goes back once with its reasons (`strategist.repair_turns`, 1), and a final
rejection or any failure keeps the last section. Its Claude line is `claude.role_usd_day["strategist"]` (4.0 a UTC day
by default), and "strategist" must be in `claude.roles` (the default; the box's `swarm.json` overrides the list, so add
it there, or the strategist runs on Sail's small packet and its event says so). The architect has no daily Claude line
of its own unless `claude.role_usd_day["architect"]` is set: with the digest each call carries ~85k more input tokens.
Each run is a private `swarm.strategist` event. Emptying `architect.agenda_locked` returns to `architect.agenda` as before.

Two-sided singles (#425, ships in Release A; `league/swarm/store.py`, `architect.py`). The architect's structure types include
`long_single` (one program that buys calls or puts by its rule; a proposal states the side rule and why its calls
and puts balance, since the drift screen charges whatever net exposure it holds), and its prompt asks for one
`long_single` family where it would have proposed a call/put twin pair. `admit` enforces it: a `long_call` or `long_put`
is refused while a living family on the same roots with the same idea (`same_idea`, one born earlier in the same pass
too) is a `long_single` or the other side. In GAPS a single option's one gap is `long_single`, covered only by a living
`long_single` family on the root; the one-sided `long_call` and `long_put` are never gaps (still admitted when proposed,
on other roots or another idea), and the coverage table has a `long_single` row. A `long_single` and the singles it
sends are one slice for lineage matching (`same_slice`): the same idea as a dead call or put twin on the same roots
continues its lineage and joins BOTH twins' (`SwarmStore.link_lineages`: the other twin of its idea or its parent's,
dead or alive, so their trials, looks and validated versions all count); a `long_single` of a living twin's idea
continues that twin's lineage and joins the other's; another idea on the slice counts the newest dead lineage of each
type there, its own first (`slice_priors`, stored as `prior_lineage` and `prior_lineages`; every other structure keeps
its one `prior_lineage`, as before); and identical code links their lineages. So relabeling a program two-sided buys no
trials or looks. Its graveyard reads include its singles' lessons. The researcher, the reviewer, the auditor and the diagnostician read what its orders are (`structure_text`);
every other family's prompts are byte-identical.
