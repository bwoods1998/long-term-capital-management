# Documentation

[The public page](https://blakewoods.us/capital/) · [Project overview](../README.md)

The project was rebuilt on September 19 and 20, 2026. The first section is the system as it exists
now; everything under "History" describes something that no longer runs.

## The system as it is now

- [Persistent earned live trading](runs/2026-09-21-persistent-live-trading.md): owner activation without a calendar expiry, full ladder, current venue cash and preserved research budgets.
- [Game gate audit and former live-learning window](runs/2026-09-21-game-gate-audit.md): completed-exposure qualification, reward continuity and evidence-based replacement.
- [Two-hour watch and accelerated overnight run](runs/2026-09-20-evening-watch.md): runtime findings, fixes, spend and acceptance.

- [Active foundation phase](phase-one.md): the funded campaign, current limits and reproducibility contract.
- [Latest foundation progress](runs/2026-09-20-foundation-progress.md): deployed changes, verified
  runtime state, first reproduced replay, Jev probe and unresolved issues.
- [Chief architect handoff and $10,000 plan](design/2026-09-20-chief-architect-handoff.md): the
  next architecture, independent acceptance, incentives and evidence-gated capital releases.
- [Model-routing evidence](runs/2026-09-20-model-routing.md): matched coding tasks, costs,
  failures and the implemented Luna grant path.
- [Jev's role and measured comparison](design/2026-09-20-typesafe-pilot.md): a funded integration,
  shared semantic features, recursive question discovery and development-probe results.
- [Project overview](../README.md): the game, the trust zones, the constitution, Merton's six jobs,
  what is public, how to run things, status and known limits.
- [The game](proposals/2026-09-19-the-game.md): the design memo for the rebuild. What the first run
  measured, what the venues reward, why the frontier model audits and never picks, and the game
  that follows from it.
- [The original rebuild architecture](design/2026-09-19-architecture.md): the September 19–20
  baseline. The active phase and architect handoff above supersede its budget and future-work plan.
- [The overnight build log](runs/2026-09-20-overnight-build.md): every decision made while
  building the league and its reason, the step log, and what was verified live. The source of
  truth for why things are the way they are. The goal the builder worked to is
  [overnight-goal.txt](design/overnight-goal.txt) ([short form](design/overnight-goal-short.txt)).
- [Switching the floor on](runbook-go-live.md): the owner's runbook. The state things were left
  in, starting the practice league, what the first hour looks like, turning real money on, giving
  Merton its GitHub token, watching, stopping, and what an unattended week should cost.
- [The league package](../league/README.md): the developer's guide to the House. Design rules,
  modules, the life of one tick, state on disk, tests, the replay regression, what is imported
  from the first run's code.
- [The strategy contract](../league/CONTRACT.md): the one Python file an agent is. `NEEDS`,
  `PARAMS`, `decide(ctx)`, what it is given, what it returns, how replay scores it.
- [The site contract](../league/tests/fixtures/site_contract.md): exactly what blakewoods.us
  accepts from the publisher: transport, formats, event and checkpoint shapes, the test tape.
- [Running the House](../deploy/README.md): the House's Sailbox, releases, the canary, the two
  watchdogs, the egress allowlist, `scripts/floor_box.py`.
- [The gateway](../gateway/README.md): venue/OpenAI/TypeSafe/GitHub credentials, caps, kill switch,
  inference routes and pull requests. The House still holds its Sail API key; removing that
  authority is a prerequisite for broad autonomous House editing.

## History

Nothing in this section runs today. It is kept because the rebuild was designed from what these
runs measured.

### The first run (September 15 to 19, 2026)

Chat desks named after the 1998 fund's partners, a committee, an evolution loop, a Foundry and a
lab, trading Kalshi and Coinbase. Stopped and wiped on September 19.

- [The first run's README](history/2026-09-first-run-readme.md): the repository's front page as it
  stood while the run was live.
- [The first run's runtime](../ltcm/README.md): the `ltcm/` package's design document, with a table
  of which of its modules the league still imports.
- [Floor contract v2](contracts/2026-09-15-floor-v2.md): the first run's agreement between its
  runtime, the gateway and the site. The league's is the site contract above.
- [Owner-account performance](account-performance.md): how the first run measured profit on the
  Kalshi and Coinbase accounts. The league's baseline is `performance` in `league/config.json`.

Proposals, oldest first:

- [The floor](proposals/2026-09-14-the-floor.md) (Sept 14): from one paper portfolio to a public
  swarm of desks. The proposal the first run was built from.
- [Push the limits](proposals/2026-09-15-push-the-limits.md) (Sept 15): a build backlog for Sail,
  Kalshi and Coinbase, with sources.
- [Sail-native](proposals/2026-09-15-sail-native.md) (Sept 15): the floor leaves the MacBook for a
  Sailbox, keys move to the gateway, shadow replaces paper.
- [The leap](proposals/2026-09-15-the-leap.md) (Sept 15): from prompted desks to strategies, a
  Foundry and a lab.
- [The exponential arena](proposals/2026-09-17-exponential-arena.md) (Sept 17): pooled family
  evidence, deep replays, every venue working.
- [The arena](proposals/2026-09-18-the-arena.md) (Sept 18): one learning loop, real money at
  learning size, a smaller board.

Run notes, oldest first:

- [Launch record](runs/2026-09-15-ltcm-launch.md) (Sept 15): the state at the first hand-off.
- [The floor moves to Sail](runs/2026-09-15-sail-native-launch.md) (Sept 15 to 16): the long record
  of the move and what followed.
- [The accountable arena](runs/2026-09-17-arena.md) (Sept 17): real P&L after fees and Sail costs as
  the objective.
- [Throughput](runs/2026-09-17-throughput.md) (Sept 17): faster research and complete position
  management.
- [Coinbase fee recovery](runs/2026-09-17-coinbase-fee-recovery.md) (Sept 17): the real 0.5% and
  1.2% fees, and what they did to spot quoting.
- [Overnight assessment](runs/2026-09-17-overnight-assessment.md) (Sept 17): a read-only audit of
  the accounts and the event log.
- [Coinbase futures](runs/2026-09-17-futures.md) (Sept 17): CDE perpetual futures go live.
- [The arena night](runs/2026-09-18-arena.md) (Sept 18): chat desks retired, live explorers, more
  data.
- [The pause and the clean slate](runs/2026-09-19-pause-and-reset.md) (Sept 19): what was closed,
  what was archived, what was wiped.
- [Run records and lab reports](runs/README.md): what the first run's generated lab reports
  measured and how to read them.

### Portfolio Agent (before September 15, 2026)

- [Portfolio Agent](history/portfolio-agent/README.md): the first generation. One persistent
  S&P 500 paper portfolio on Sail with a Cloudflare supervisor, retired on September 15, 2026.
