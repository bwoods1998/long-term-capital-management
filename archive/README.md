# The archive: how the project got here

This folder keeps the documents of everything the repository did before September 26, 2026, when it
narrowed to one goal: a swarm of AI agents trading level-3 options. None of it runs. The current
project is in the [README](../README.md); the current design is [docs/design.md](../docs/design.md).

## Four generations in nineteen days

**1. Portfolio Agent (Sept 7-15, 2026).** The repository began on Sept 7 as a small lab for
measuring inference on [Sail](https://sailresearch.com), and became Portfolio Agent: one persistent
S&P 500 paper portfolio researched by models on Sail, with a Cloudflare supervisor for funding,
availability and backups, a read-only Schwab connector, and checkpoints published to
blakewoods.us/portfolio. It measured research quality and cost; it never traded real money.
Records: [docs/history/portfolio-agent/](docs/history/portfolio-agent/README.md).

**2. The first LTCM run: chat desks (Sept 15-19).** On Sept 15 the runtime was rebuilt as many
desks instead of one portfolio and renamed Long Term Capital Management, each desk named after a
partner of the 1998 fund. A desk was a model session with a mandate: Mullins traded Kalshi event
contracts and Hilibrand traded crypto on Coinbase with real money; the equity desks ran in shadow;
Meriwether was a committee that allocated among them. The same day the floor moved from the laptop
to a Sailbox, and the venue keys moved into a Cloudflare Worker (the gateway) with order caps and a
kill switch, where they still are. Over the next days came strategies written as code with a Foundry
and a lab (Sept 15), pooled family evidence and Coinbase perpetuals (Sept 17), and the retirement
of 66 desks of nine families in favour of live books (Sept 18). What it measured: a Coinbase spot
round trip cost 1.0-2.4% in fees, which no active strategy survived; its one measured edge was
resting Kalshi bids on favorites above 90 cents (+2.15 cents a contract); and Sail cost about $145
a day. The owner stopped and wiped it on Sept 19 (03:30-04:10Z) and closed the Coinbase
account. Records: [the first run's README](docs/history/2026-09-first-run-readme.md), the
[proposals](docs/proposals/) and the Sept 15-19 [run notes](docs/runs/).

**3. The league (Sept 19-26).** Designed in [the game memo](docs/proposals/2026-09-19-the-game.md)
and built overnight on Sept 19-20 as the `league/` package: a House on one Sailbox ran the loop,
agents were Python strategy programs written by cheap models and run in sealed Sailboxes, and
evidence moved each agent up a ladder from replay to paper to a few real dollars to real size on
Kalshi and Alpaca. Agents earned their share of the compute budget by what they proved; a
hash-chained ledger recorded every decision; a frontier model (Merton, on OpenAI) audited
promotions and wrote code by pull request.
The owner's grant of real money (`earned-live-20260921`) was activated on Sept 21. Each following
day had its own run: the rebuild of the learning loop (Sept 22), bands of capital and the Alpha Lab
(Sept 23), closing the gaps (Sept 24), and four parallel runs on Sept 25, one of which added
level-3 option structures. The House was paused at 03:55:56Z and stopped at 06:24:56Z on Sept 26
with 128 agents alive in 121 families and 627 dead. Its tracked profit from Sept 19 was +$4.84
against about $680 of compute. At the tag the repository held 1,103 files and 360,821 lines, a
104.6 KB README, a 75.6 KB strategy contract that every model call paid for, and 119 Markdown
documents. Records: [the docs index as it stood](docs/README.md) and
[the run records](docs/runs/README.md).

**4. Options only (from Sept 26).** On the evening of Sept 25 (Pacific) the owner set one goal: a
swarm of AI agents trading level-3 options on the brokerage account profitably, with options
returns greater than every input cost. The reasons, as given and as measured:

- Kalshi's markets were not liquid enough to scale, and the league's profit did not pay for its
  compute: +$4.84 against about $680 in a week.
- Options give upside, bets in both directions, and room to add capital. The account is approved
  for level 3, the pattern-day-trader rule ended on June 4, 2026, and the venue added index
  options on Sept 2.
- Learning at the market's speed was too slow and too expensive. The new design trains in a Gym on
  recorded one-minute option quotes from ThetaData at thousands of times real speed, and uses the
  live market as the judge, not the teacher.

The plan is [docs/goals/LTCM_OPTIONS_SWARM.md](../docs/goals/LTCM_OPTIONS_SWARM.md).

## Where everything went

| What | Where |
|---|---|
| The code of every generation | git tag `archive/pre-options-2026-09-26` (main at `89bc49a1`, Sept 26 03:24Z) |
| Branches that were on GitHub | 78 tags `archive/branch/<name>`; the branches themselves were deleted |
| Branches that existed only on the laptop | `git bundle` files on the owner's machine, never pushed (the repository is public) |
| Documents | `archive/docs/`: `docs/` as it stood on Sept 26, moved with `git mv` (`git log --follow` works); only the live plan stayed |
| The old front page | [archive/docs/README-pre-options.md](docs/README-pre-options.md) |
| The old operator's page | [archive/docs/operations.md](docs/operations.md) |
| The old House's state | a tarball on the House box (`/workspace/archive/state-pre-options-20260926.tar.gz`, 8.26 GB, sha256 `e9e5c044...`); a copy to the owner's machine was in progress on Sept 26 |

`archive/docs/` holds the runs, research, history, proposals, goals, design notes and contracts.
Their links are relative to where they stood (`docs/` at the repository root), and many point at
code that has since been removed; follow them on GitHub at the tag
`archive/pre-options-2026-09-26`. Code comments that cite `docs/...` now resolve under
`archive/docs/...`. Code is not copied here: the tags are the archive of code.
