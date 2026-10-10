# Release E2: the swarm breeds share programs for the BETA and EQUITY lanes

E1 gave the equity lanes their live path, engine, store, screen and three captain-seeded programs (league/equity/
INTERFACES.md). E2 makes the swarm itself breed them, around the clock: the architect proposes equity-lane families
with their first program, a minimal researcher iterates each on Train, the first version to pass the Train bar takes
its lineage's one Validation try, and the model routes are chosen by measured yield per dollar. No figure appears here
or in the code: the bar's constants are rules, and the Train map shown to agents is computed on the House from the
swarm's own Train runs.

## The switch

`elane.mode` "gate" (E1) AND `elane.birth_share` above zero. E1 ships the lanes with `mode` "off" and `birth_share`
0.0, so E2 does nothing until the captain sets both in swarm.json. The equity researcher (Train) needs `mode` "gate"
alone, so families already born finish their Train research if births are paused. Rollback: `elane.birth_share` 0.0
stops births at once; `elane.mode` "off" stops everything E2 does (E1's own rollback).

## The design

1. **Births** (`league/swarm/elane_births.py`). The architect's equity pass (`Architect.equity_pass`, its own loop round)
   is a separate request from the options pass, so the options request, graveyard and births stay byte for byte as
   they were. Its request holds the LANES/EQUITY block (what BETA and EQUITY mean and their labels, the universe by
   class and group, the contract in brief, the ration, the Train bar), THE AGENDA (overnight effect, short-term
   reversal, time-series trend, cross-sectional and sector momentum and rotation, low volatility, turn of the month,
   each with its published prior; post-earnings drift named and refused until earnings data exist), THE EQUITY QUOTA,
   THE EQUITY TRAIN MAP, the equity graveyard that binds (E2's Train refutations and the CLOSED cells), the lineages
   whose one try is taken (seeded programs and Train passes, outcomes sealed), the equity families' Train facts, the
   card vocabulary, and the last pass's refusals. EQUITY.md rides in the system prompt.
   - THE EQUITY QUOTA (`EquityQuota`): the equity lanes' share of the swarm's births over the last 24 hours is
     `elane.birth_share`; a pass asks for the births that bring the lanes to it, at least `min_per_pass` and at most
     `max_per_pass`, never past `max_alive` families in Train research. The equity lanes have their own population (E1's
     `families` filter keeps them out of every options count), so an options population at its ceiling never stops an
     equity birth, and E2 takes no options birth. This is how E2 reads the design's "taken out of the alpha share
     first": the share is of births, and an equity birth takes no options place, so reducing the options births would
     only slow the options refill and free nothing the equity lanes use.
   - THE ADMISSION: lane, structure (a beta card is "etf"), symbols (in `elane.universe`, of the structure's class),
     agenda (an available mechanism), the cell not CLOSED, no family in Train research with the same idea on the same
     slice, a valid card (`cards.validate`, E1's equity admission), a continued lineage that has no try (no seeded
     program and no Train pass in it), and the quota. A born family's spec carries `lane`, `symbols`, `agenda`, the
     card's sha and `e2_route`; a program that passes the static checks is its version 1.

2. **Train** (`league/swarm/elane_train.py`). THE BAR equity-v1 (the design's 6b): at 1.0x and 1.5x the half-spread
   over the House store's Train window 2016-2024 (never 2025-2026; a result that carries another year is refused whole),
   through E1's isolated runner: at least 40 closed lots and 20 entry days in each of three or more Train years; no
   year's daily t below -1.0; net P&L above zero at 1.5x; the 1.5x P&L at least half the 1.0x P&L (which must be above
   zero). Beside it, never a bar: the same-exposure buy-and-hold, MTE and the drift share.
   - THE RESEARCHER (`EquityResearcher`, minimal): each round gives a few families one step: score the newest version,
     or ask the family's birth route for its first program or a revision (the brief holds the card, the agenda prior,
     the bar and the family's own Train versions only), or refute it. The first passing version ends the research: it
     is the lineage's one Validation try (`awaiting_validation`, which E1's tournament reads; `best_version` set). A
     spent Train budget (`train_budget` scored versions) retires the family REFUTED on Train, with a graveyard row in
     E2's own words.
   - THE EQUITY TRAIN MAP: lane x agenda x universe group, with births, Train passes (the best passing pooled t),
     refutations, and CLOSED cells (`refuted_cell_cap` refutations, no pass). In-sample, labelled so.

3. **No feedback** (`league/swarm/elane_seal.py`, A9 D3). No Validation or look outcome of a share program reaches a
   generator. The equity generators read equity families through `train_facts` only (birth facts and E2's own Train
   record; never a band, a retirement, a validated version, E1's try, look, floor or sigma, a look row, a forward
   record, or a graveyard lesson someone else wrote). The options generators read no equity-lane graveyard row at all
   (architect.py: the digest, `graves`, `unseen`, `graveyard_ids`; researcher.py: the `graveyard` tool; game.py's
   `visible_graveyard` by patch 4, for the diagnostician). The test is invariance: two stores that differ only in what
   happened after Train give the same equity request, researcher brief, route choice, Train map and options graveyard
   reads (league/tests/test_elane_e2_seal.py).

4. **Yield per dollar** (`league/swarm/elane_yield.py`). One ledger row a model route ("sail:<profile>",
   "openai:<model>", "claude:<role>"): requests, answers, failures, dollars (births and research), births; the Train
   counts are read from E2's records, and the operator's report adds Validation entries, looks, looks passed and live
   programs, each per dollar. THE ROUTE CHOICE: with no births anywhere, the first route of `elane.e2.routes` (cheapest
   list price first); before every route has `min_births` births, every `explore_every`-th request goes to the route
   furthest from its sample and the rest DEFAULT TO THE CHEAPEST ROUTE THAT HAS PRODUCED BIRTHS (the lowest mean
   dollars a request); once every route has its sample, the most Train passes per dollar (ties: births per dollar,
   then the cheaper request). The yield the choice reads is Train passes, never a later stage: a choice made on look
   outcomes would feed the holdout back into which model writes the next programs (A9 D3). A family's revisions are
   asked on its birth route, so its cost and its yield sit on one row. `usd_day` caps E2's model dollars a UTC day.

## The files

| file | what |
|---|---|
| `league/swarm/elane_births.py` | the switch, THE EQUITY QUOTA, the request's blocks, the equity pass and its admission |
| `league/swarm/elane_train.py` | equity-v1, the record, the Train map and graveyard, the agenda, the equity researcher |
| `league/swarm/elane_yield.py` | the route ledger, the operator's report, THE ROUTE CHOICE, one route a question |
| `league/swarm/elane_seal.py` | what of an equity family a generator may read; the graveyard filter |
| `league/swarm/architect.py` | `equity_due`, `equity_pass`; equity rows out of the digest, `graves`, `unseen`, `graveyard_ids` |
| `league/swarm/researcher.py` | equity rows out of the `graveyard` tool |
| `league/tests/test_elane_e2_*.py`, `elane_e2_fakes.py` | births, Train, seal (D3), yield; E1's names faked as INTERFACES fixes them |

## Settings (`elane.e2`; every default in code, the policy.json block in patch 6)

Births: `births_every_seconds`, `births_refill_seconds` (while fewer than `start` families research), `start`,
`max_alive`, `min_per_pass`, `max_per_pass`, `window_hours`, `births_max_output_tokens`, `births_effort`,
`families_shown`. Train: `train_budget`, `train_max_attempts`, `train_max_errors`, `train_every_seconds`,
`train_per_round`, `train_max_output_tokens`, `train_effort`, `refuted_cell_cap`. Routes: `routes`, `min_births`,
`explore_every`, `usd_day`. Each is held to its bound in code; a malformed value is its default.

## The patches (league/swarm/ELANE_E2_PATCHES.md)

E2 edits no file E1 owns. Eight patches for the integrator: the loop's two rounds; dlane's and the birth quota's
windows skipping equity births; `game.visible_graveyard` dropping equity rows (the diagnostician's read); the
tournament validating an E2 family only at its first Train pass; the `elane.e2` policy block; the four modules
protected in league/ci.py; the operator's yield record in the dlane report. Plus what E2 needs E1 to build as
INTERFACES says (the store's equity structures and `lanes` filter, `elane.cfg`/`on`/`isolated_runner`,
`cards.validate` for equity cards) and one question for the integrator: the isolated runner is shared by E1's
tournament and E2's Train round, so its calls must be serialized.
