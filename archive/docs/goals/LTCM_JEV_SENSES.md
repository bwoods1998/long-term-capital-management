# LTCM run: Jev as the swarm's senses

A fourth autonomous run, beside forward-first, the options desk and Kalshi at scale. Its job: turn
Jev, the cheapest and fastest model the floor can call, from a gatekeeper that runs out of calls
by midday into the swarm's always-on senses. That means point-in-time features strategies can
trade on and replay, a filter in front of every expensive model call, and a cheap reader for the
floor's own text.

- **The superpower, measured.** Jev (`jev-1.13.0`, TypeSafe) returns typed answers (a choice among
  named options, or a yes/no probability) over supplied text or JSON in about 0.5 s for about
  $0.00007 a call: $0.042 per million input tokens, output free. A Luna research session costs
  $0.02-0.06 and takes 10-90 s. Jev is 300-800 times cheaper per decision.
- **The one trading result.** The semantic lab (Sept 20-22, 136,308 labels, $13.93) found that
  eight Jev features on Kalshi market text lift prediction of **whether a market's midpoint moves**
  in the next 5, 15 and 60 minutes from AUC 0.609 / 0.616 / 0.659 (numeric model) to
  0.766 / 0.757 / 0.749, with no gain on **direction** (`docs/design/2026-09-22-jev-sensor.md`).
  Whether a price is about to move is exactly what a maker needs to avoid being picked off, and
  what an options seller needs to judge implied volatility against realized. The floor's real
  profits are maker favourites on Kalshi, and the options run is about to sell defined-risk premium.
- **Its limits, documented.** Weak at numeric precision, time comparisons, indirect reasoning,
  long irrelevant context and adversarial text (TypeSafe's model notes). Its confidence is not
  calibrated: in the Sept 20 probe it gave high confidence to some wrong answers. It agreed
  with 9 of 12 frozen labels against Luna's 11.
- **Today's use (Sept 22-25).** Four purposes only (the research gate's note relevance, triage,
  hypothesis links, exposure groups) at about $0.02 a day. Per-purpose call caps (gate 150,
  triage 120, links 60, exposure 40) bind daily, and the gate then decides without Jev
  (91 `jev_unavailable` gate rows in the 24 h to 06:00Z Sept 25). The gateway's lifetime Jev
  line: $16.21 spent of $42; the owner reports about $25 in the account.

## The owner's direction

Sept 25, 2026: "Can we do a fourth session that utilizes jevs cheap super powers better in this
project given it's so cheap and fast and I have $25 in that account? ... see how we could make it a
more impactful part of this project."

Standing direction (Sept 23): bold inside the envelope, evidence honest, docs and repo clean.
Jev keeps no order, promotion, spending or merge authority. It supplies features, filters and
labels; deterministic code and the ladder decide.

## Coordination with the other three runs

The options plan's "Coordination" section applies, across four runs now. This run owns the Jev
files: `league/jev.py`, `league/sensors.py`, `league/triage.py`, `league/hypothesis_memory.py`,
`league/exposure.py`, `league/semantic_lab.py`, a new `league/jev_features.py`, `scripts/jev_lab_eval/`,
`gateway/lib/typesafe.mjs`, and `config.json`'s `jev` block. Everything else it touches is a hook:
- the research gate (`league/research_gate.py`) is the forward-first run's F2: J2 lands as a PR on
  top of F2 after F2 merges;
- feeds (`league/feeds.py`) belong to the Kalshi run: J1's features publish through the feeds
  interface with that run's agreement, as a new source;
- the lab (`league/lab.py`) belongs to forward-first: J3 is a hook after its F1;
- the gateway is shared with the options run (multi-leg) and the Kalshi run (`web_fetch`): whoever
  deploys the gateway later rebases on the earlier deploys and re-runs every gateway test.
One deploy at a time across four runs; none 13:25-20:05Z on a trading day or while a real family's
game is in play. No money rule changes in this run, so it never moves the grant's digest.

## Budget

- The lifetime Jev line is the gateway's (`$42` cap, $16.21 spent). The run aligns it to the funded
  balance the owner states (about $25 left) and never above it.
- The House's daily cap rises from $0.25 to **$1.50** (about 21,000 calls a day at today's
  size), split by measured yield, not fixed per purpose: at that rate $25 lasts about 16 days, and
  the run reports the burn so the owner can top up. A purpose that shows no lift by the end is cut
  back.
- Cache everything by (content hash, question hash, model version). Fan several questions over
  one shared state in one call (TypeSafe's fan-out pattern). Most repeated calls are cache hits.

## Workstreams

### J0. Baseline (first hour)

- Read `jev.sqlite` (calls, answers, hits by purpose), the semantic lab's evaluation, the gate's
  `report()`, the four sensors' outputs, and the gateway's `/v1/health` `typesafe` block.
- Measure the research gate's Jev-unavailable share, triage's backlog, and hypothesis links' coverage.
- Raise the per-purpose caps into one yield-weighted daily pool (config only, no code).

### J1. The move sensor: a tradable feature (the headline)

- `league/jev_features.py`: every 5 minutes, for each market a living Kalshi strategy is shown
  (and each options underlying the options run trades), ask Jev the semantic lab's fixed eight
  questions plus a "will this price move within 15 / 60 minutes" pair over the market's rules text,
  recent quotes as text and the recorded news and scores context (the Kalshi run's recorders).
  Deterministic code turns the answers and the numeric features into `move_p15` and `move_p60`
  with a logistic model fitted on DEVELOPMENT data only.
- Recorded point-in-time in the feeds store and served as `ctx["feeds"]["move"]` (name agreed with
  the Kalshi run), so a strategy can use it live and a replay sees exactly what a live wake saw.
  Rows before the recorder existed are unavailable, never back-filled.
- Validation before any strategy relies on it: chronological split, event-clustered bootstrap, the
  lab's own evaluation scripts; the feature ships only if its held-out AUC for "moves at all" stays
  at or above 0.70 on events after the ship date's cutoff.
- First users (children written with each desk's owner run): maker strategies that pull or widen
  quotes when `move_p15` is high (weather and sports favourites, crypto-strike far-favourite
  makers), and options structures that sell premium only when `move_p60` is low against implied
  volatility.
- **Acceptance:** the feature recorded for every shown Kalshi market; the held-out AUC reported;
  at least three strategies using it seated; after 3 days, adverse-selection loss (fills followed
  by a move against them within 15 minutes) compared between users and their parents.

### J2. A filter in front of every expensive call (hook on forward-first's F2)

- **Research.** Before a Luna or Sail session, Jev answers "is there decision-relevant new evidence
  for this agent since its last session?" over the agent's new rows (fills, settlements, refusals,
  lessons, notes, feed changes). A no skips the session. A sampled 10% of skips run anyway, and the
  miss rate is measured as the gate already does.
- **Merton.** Before a consultant, engineer or architect call, Jev classifies the request (a known
  repair, a duplicate of an open repair, missing data, a strategy question, a House defect). The
  cheap classes route to the existing deterministic path instead of Astra.
- **Foundry and lab.** Before a card or a lab child is replayed, Jev answers "is this a mechanism
  already in the graveyard, a parameter nudge, or a new mechanism?" against `hypothesis_memory`'s
  index. Rewordings of dead mechanisms skip replay; new mechanisms go first.
- **Acceptance:** research and Astra dollars a day down at least 30% against J0's baseline with
  candidates and positive forward blocks a day not down, measured by the yield row.

### J3. The swarm's shared memory (hook on forward-first's F1)

- Every research summary, post-mortem, lesson and library note is classified once into a small,
  versioned taxonomy (mechanism, market, failure cause, data needed, verdict) and indexed. A
  research session is handed the 5 most relevant prior results by Jev relevance instead of a raw
  journal dump. Measure turns per session and abstention against sessions without it (agent-id
  parity split).
- The graveyard becomes queryable: "has any agent tried X on desk Y, and how did it end?"
  answered with ledger references.

### J4. Reading the world (with the Kalshi run's recorders)

- News and scores text (GDELT, ESPN scoreboards and injury notes, EDGAR filing headlines, NWS
  alerts) classified as it arrives into point-in-time event features: "a starter ruled out",
  "a severe weather alert for a settlement station", "an 8-K with guidance". They are recorded and
  served through feeds like J1, validated the same way before any strategy leans on them.
- Kalshi market discovery: the daily survey's thousands of markets classified by resolution source,
  settlement mechanics and which recorded feed could price them. That shows which open-desk markets
  have an input the swarm can model.

### J5. The gateway's `score` answers

- `gateway/lib/typesafe.mjs` supports `choice` and `noul` today. Add `score` (rubric scores) with
  the same validation, reservation and 409 identity rules, for J3's taxonomy and J4's severity.

## The scoreboard

| # | Metric | Baseline (Sept 25) | Target |
|---|---|---|---|
| 1 | Jev calls a day; dollars a day; cache hit rate | about 200-420; $0.02; unmeasured | ≥ 10,000; ≤ $1.50; ≥ 50% |
| 2 | Gate decisions made without Jev because a cap bound | 91 a day | 0 |
| 3 | The move sensor's held-out AUC ("moves at all", 15 min) | 0.757 (lab, Sept 22) | ≥ 0.70 on post-ship events |
| 4 | Strategies using a Jev feature; their adverse-selection loss against their parents | 0; — | ≥ 3; lower |
| 5 | Research + Astra dollars a day | about $77 (research $48.62, consultant $28.72) | ≥ 30% lower, yield not lower |
| 6 | Research sessions handed Jev-retrieved prior results; their abstention against control | 0; — | all; lower |

## Done

- J1-J5 live and verified, or blocked with the numbers;
- every Jev feature validated on held-out, post-ship data before any strategy relies on it; none
  back-filled;
- the Jev line's burn reported with days of runway at the end; no cap above funded money;
- tests and CI green; no harness incident; none of the other three runs blocked;
- docs (`docs/design/2026-09-22-jev-sensor.md` updated, operations, README), memory and the run
  record current; the report delivered with the owner's next decision on the Jev balance.

## The /goal message

```
/goal Execute docs/goals/LTCM_JEV_SENSES.md (branch goal/jev-2026-09-25; merge it to main first) autonomously with no deadline, beside the forward-first, options-desk and Kalshi-scale runs, until its Done list holds.

- Direction: make Jev, our cheapest and fastest model, the swarm's always-on senses. Ship its one measured trading superpower (predicting whether a price is about to move) as a point-in-time, replayable feature for maker and options strategies; put it in front of every expensive model call so research, Merton and replays only run when there is something new; make it the swarm's shared memory; and have it read news, scores and filings into event features. Spend the Jev balance boldly but only on work that shows lift: about $25 is funded, so align the gateway's Jev line to that and never above it.
- Coordinate with the other three runs exactly as the plan's "Coordination" section says: this run owns the Jev files only, lands hooks into research_gate.py, feeds.py and lab.py after their owners' waves merge, rebases any gateway deploy on the others', one deploy at a time across four runs, none 13:25-20:05Z on a trading day or while a real family's game is in play. This run changes no money rule.
- Authority: the forward-first plan's "Authorized" list applied to this run's workstreams. Jev never gets order, promotion, spending or merge authority. Nothing in "Not authorized": no back-filled or fabricated evidence, no cap above funded money, no test orders. No owner steps needed.
- Method: validate every feature on held-out, post-ship data before a strategy relies on it; builders in worktrees; tests for every change; report with the scoreboard, the Jev burn and runway, and which uses earned their keep.
```

And one line for each of the other three sessions:

```
A fourth run is executing docs/goals/LTCM_JEV_SENSES.md. It owns only the Jev files (league/jev.py, sensors.py, triage.py, hypothesis_memory.py, exposure.py, semantic_lab.py, jev_features.py, scripts/jev_lab_eval/, gateway/lib/typesafe.mjs, config.json's jev block) and lands small hooks into research_gate.py, feeds.py and lab.py only after your waves that own them merge. It changes no money rule. One deploy at a time now across four runs; any gateway deploy rebases on the others' gateway changes and re-runs every gateway test.
```
