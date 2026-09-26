# The sprint: an options swarm trading for profit from Monday's open

**One goal.** A swarm of options-trading agents that is profitable on the owner's Brokerage Account from
Monday September 28, 2026, 13:30Z. It learns at agent speed, not human speed, and uses Sail, OpenAI,
the Claude API, ThetaData and the Alpaca data plan to the full.

This file amends `docs/goals/LTCM_OPTIONS_SWARM.md` (the plan). Where the two differ, this file wins.
The plan's venue facts, prune, site rules and Not-authorized list still hold. The sprint continues the
same run:

- T0 stays `2026-09-26T06:23:14Z`.
- Append to the run record `docs/runs/2026-09-26-options-swarm.md` on `run/options-swarm-2026-09-26`.
- Never restart the clock.

This file lifts the Saturday continuation's "engineering and paper only" scope. Real options trading
is authorized inside the Money section below.

## The owner's direction (Saturday Sept 26, afternoon Pacific)

- "Push these agents at agent time scale (not human) and make the absolute most of our
  infrastructure here (sail, openai api, claude api, theta data, alpaca market data plan)."
- "10k agents solved navier stokes in 86 hours. We can certainly reach our goal of a swarm of
  options trading agents that are profitable on my alpaca account when monday market open comes
  around."
- "I never put money in alpaca I'm not okay with losing fully so don't shy away from risk. It's a
  singular focus you should have on the goal here."
- The owner added a Claude API key with a $100 balance. It is in the gateway as `CLAUDE_API_KEY`
  and has no route yet. The owner expects Claude Opus 5.5 to beat GPT-6 Astra on quality and cost.

**What makes this game work.** A proof search at agent scale succeeds because every candidate can be
checked by a verifier. This game's verifier is data the agents have never seen: the sealed 2026
holdout, then the live market. The sprint does two things:

1. It makes the search much faster and aims it at robust mechanisms instead of Train noise.
2. It guarantees that every idea the verifier accepts is trading real money at Monday's open, and
   that every other agent is trading forward in shadow.

The verifier itself is never weakened except by the owner's decision D2 below. A trade forced past it
is a coin flip that pays the spread both ways.

## Where things stand (read 20:51Z Sept 26)

| Area | State |
|---|---|
| House | release `20260926T181814Z-b4bc25619f84` (main `60b34dd9`), healthy. Main `f789e7e0` holds #378-#383, not deployed. Open: #381 (execution receipts, CI green, review pending), #384 (catalog), #385 (post-burst lifecycle), #375 (prune draft, after Monday's close) |
| Swarm | 16 families alive, exactly the floor; 60 retired, 76 in total. 18,226 trials, 26,392 program-years. 721 cycles an hour. **7 of 8 Gym boxes idle** |
| Evidence | **0 families over the validation line.** The nearest has 64 of the required 100 trades on 28 of the required 60 days. 0 holdout looks. The gate is off (`gate_checkpoint` null) |
| Data | Core five complete for 2022, 2023-2025 and the 2026 holdout; `trade_quote` samples done. 20 names 11,680 of 23,740 tasks (about 10.5 h left). SPY/QQQ back months 0 of 2,374. Active Gym image v1 (Train 2023-24). Images v2/v2b and a calibrated core pair are built but not adopted. The core five's gate image exists |
| Money | equity $481.63, all cash; level 3; limited margin, so debit structures only under $2,000; no positions or orders. `real_money` false; grant `options-swarm-20260928` not enabled; gateway `OPTION_STRUCTURES_REAL` "off" |
| Inputs | Sail $187.57 (reserve line $32; swarm about $2.6/h). OpenAI September $598.90 of $707, no October allowance. Claude API $100 (key placed, no route). ThetaData Options Standard. Alpaca Algo Trader Plus |
| Monday as it stands | Only the one-lot SPY paper route proof trades. The shadow book has nothing to run: only Candidates enter it, and Gym families cannot. Real money is off |

## Why nothing passes: the review's diagnosis

Three independent code reviews on Sept 26 found seven causes. Most can be fixed before Monday.

1. **The population collapsed and cannot refill.**
   - #376 gave researchers a `retire` tool on the REVISE turn, which requires a tool call and has no
     evidence minimum (`researcher.py:82, 90-92, 497-501`). Alive families fell from 49 to 16
     between 17:57Z and 18:21Z.
   - At the floor, each birth is cancelled by the next deferred retirement (`store.py:475-477`).
     Every cycle error is such a deferral, and each backs off up to 30 minutes (`loop.py:101-103`).
   - The tournament also retires any family without a new validation maximum in 30 revisions,
     about 35 minutes at the current rate (`tournament.py:154-157, 260-263`).
2. **Researchers climb the wrong hill.**
   - A family's best version is the highest full-Train `t` on traded days, with a 30-trade floor
     (`evidence.py:147-157`). That rewards sparse filters that can never meet the line's frequency.
   - Inside Train there is no held-out fold, no year consistency and no stress test.
   - Researchers see Validation's numbers and failed checks (`diagnostics.py:117-125`), so
     Validation has become a second training set.
3. **The line's statistics punish sparse trading twice.**
   - The deflated Sharpe uses the all-days Sharpe, which is capped at √(f/(1−f)) for a family
     trading a fraction f of days.
   - N counts every Train trial in the lineage (about 300-800), although selection on Validation
     happens only among the few validated versions (`store.py:571-585`).
   - Families hold at most two roots (`architect.py:165`), and forks one. Same-day trades across
     roots count as one day, so a weekly mechanism can never reach 60 days.
4. **Execution is priced at the worst case and never measured.**
   - Every leg fills at the natural price, in and out; a condor pays 8 half-spreads.
   - Researchers are told mid limits will not fill (`CONTRACT.md:147`).
   - Far out-of-the-money expiring legs are liquidated at the natural price (`venue.py:94`).
   - A retired SEC fee is charged (`venue.py:44-46`).
   - Split runs force-close at the natural price at every segment boundary: 8 on Train, 4 on
     Validation (`engine.py:751-757`).
   - No real fill has ever been recorded, and execution tuition only serves validation passers, so
     none ever will be.
5. **The world is narrow.**
   - Five roots, 0-14 DTE only.
   - Train 2023-24 was calm, while Validation 2025 held the April shock; 2022 is downloaded but not
     in the active image.
   - No back months.
   - No earnings dates, cross-root context or volatility-index context in `ctx` (`events.py:69`).
   - XSP's $0.50 a contract makes narrow XSP structures uneconomic.
6. **The cheapest model does all the thinking.**
   - DeepSeek V4 Flash at minimal effort, at most 3 calls a cycle.
   - The architect nets about 3 families an hour.
   - No strong model diagnoses a near-miss.
7. **Monday has no way in.**
   - Only Candidates shadow-trade, and Gym-band families are refused (`bands.py:69-71, 104`;
     `live/families.py:34-35`).
   - Long calls and puts are not real-money types.
   - Under $2,000, only debit verticals and long butterflies can trade real
     (`constitution.py:707-709`).

## The game, re-tuned for agent time

### The verifier chain

| Stage | Window | Who sees what | Role |
|---|---|---|---|
| Train | 2022-01-03 to 2024-12-31 (2022 added) | researchers, full diagnostics, **scored on the worst Train year** | the inner loop |
| Robustness | the same Train, automatically | researchers | every best-version candidate re-run per year, at 1.5x stress and at mid, on idle boxes |
| Validation | 2025 | the tournament; researchers see **pass or fail and the number of checks passed only** | selection |
| Holdout (sealed) | 2026-01-02 to 2026-09-25 | the gate box only; one look per version, at most 3 per lineage, Holm across every look | **the verifier** |
| Forward | Monday on | observe shadow (every family), Candidate shadow, real Probes; nightly replays from Tuesday | the judge of money and size |

### The loops

| Loop | Cadence | Model | Change in the sprint |
|---|---|---|---|
| Inner loop | about 50 s a cycle, 48-96 families | Sail V4 Flash; V4 Pro or K3 at low effort for the bandit's top 10 | the robust Train score; retirement only by the tournament; 1-5 pooled roots per family |
| Robustness runs | on every new best version | the Gym, no model | per-year, stress and mid results come back to the researcher; this fills the idle boxes |
| Diagnostician (new) | when a family reaches 2 validations or a near-miss | **Claude Opus 5.5, effort high** | reads the family's full Train diagnostics and robustness results (never Validation's numbers); rewrites the mechanism, not the parameters; or writes the lesson and retires |
| Architect | every 20 min below `population.start`, then every 2 h | **Claude Opus 5.5 high**; alternate passes GPT-6 Astra (Flex) for diversity | proposes up to 12; must cover single calls and puts, multi-day holds, pooled roots and the back-month horizon when admitted |
| Tournament | hourly | none | retire only after 200 revisions or 4,000 evaluations without validation improvement, or DSR below the line after 6 validations |
| Gate | every 5 min | **Claude Opus 5.5 audit** (Astra fallback); GPT-6 Sol Flex program review | on from Wave 0 |
| Live | 09:30-16:00 ET | none | observe shadow for every alive family; Candidates in shadow; Probes real; real-fill round trips (D3) |
| Post-close and nightly | after each close; Tuesday 06:00Z on | Opus 5.5 post-mortem | fills recalibrated from real fills; forward replays of Candidates |

## Owner decisions (answer them in the /goal message)

| # | Decision | Recommendation |
|---|---|---|
| D1 | Real money on for Monday: families that pass the holdout trade at Probe size from their first signal after the paper proof passes | **Yes**. Switch it on Sunday, before any Probe exists, so the switch is verified on a closed market |
| D2 | **Evidence reform.** (a) Researchers see Validation only as pass or fail and a count of checks passed. (b) The deflated Sharpe uses the traded-day Sharpe, with N = the lineage's validated versions (inherited ones included). (c) Frequency: at least 50 trades on at least 25 distinct days. Unchanged: t ≥ 2, positive in 3 of 4 quarters, positive at 1.5x the half-spread, and the whole holdout line (bootstrap lower bound above zero with Holm, holdout Sharpe at least half of validation's, at most 3 looks per lineage) | **Yes**. (a) restores Validation as a clean selection set. (b) and (c) stop the line from rejecting sparse mechanisms for being sparse. This loosens the line's letter, so it is the owner's call. The sealed holdout, Holm and the forward record remain the verifier, and Probe size bounds the cost of a false pass |
| D3 | **Real-fill calibration round trips**: the House, not an agent, sends 1-lot SPY and QQQ debit verticals at mid and at mid plus one tick, opens and closes them, capped at $50 of maximum loss a day, every session until 30 samples per cell. Receipts through #381; never evidence for a family | **Yes**. Without real fills the Gym's execution cost is a guess, and it is the biggest single term in every family's result |
| D4 | **Money table at the bold end of the plan's ranges**: Probe max loss 5% of equity and a $100 floor; family total 15%; book 90%; daily stop 35%; drawdown stop 60%; tuition $200 a day | **Yes**, given the owner's stated risk appetite. At $481.63, the floor lets a Probe hold a $1-2-wide SPY or QQQ debit vertical or a narrow butterfly |
| D5 | A deposit to the Brokerage Account | Optional. Equity of $2,000 or more unlocks credit structures (condors, credit verticals) and larger Probes once the deposit lands (ACH takes 1-3 business days). The sprint does not depend on it |
| D6 | Sail top-up | Optional, about $100. A 48-96 family swarm plus 8-12 busy Gym boxes may use $80-120 through Monday. The guard stops the swarm before the House at $32 |
| D7 | The Claude API | $100 funded, key in the gateway as `CLAUDE_API_KEY`. The gateway caps Claude at the funded amount |

## Money on Monday

| Rule | Sprint setting (D4) |
|---|---|
| Real types under $2,000 of equity | debit verticals, long butterflies, **long calls, long puts** (B4) |
| Credit types | only at $2,000 of equity or more (a landed deposit re-ratifies the grant) |
| Probe | a Candidate (holdout passed) with an enabled real type whose typical maximum loss fits the cap. Moved to Probe before 13:30Z to trade that session |
| Probe maximum loss per structure | 5% of equity, or one contract when its maximum loss is at most $100 |
| Probe open structures per family / family total | 3 / 15% of equity (the floor applies) |
| Sized | unchanged from the plan: at least 20 forward trades on the current version, including at least 5 real, then quarter-Kelly on the lower bound |
| Book | open maximum loss across all families at most 90% of equity |
| Daily stop / drawdown stop | 35% of start-of-day equity / 60% from the peak since the reset; exits go on, and the owner is notified |
| Gateway | `OPTION_STRUCTURES_REAL` names exactly the real types above. The per-order maximum-loss cap is set so the Probe floor fits (never above funded money). 250 orders a day including cancels and legs; the kill switch unchanged |
| Tuition and calibration | tuition $200 a day for validation passers before their holdout; calibration round trips $50 a day (D3); neither counts as evidence |
| Observe shadow | never real, never a forward row, never Profit |

## Compute and models

| Role | Service and model | Sprint budget to Monday 13:30Z |
|---|---|---|
| Researchers (48-96) | Sail: V4 Flash, minimal effort; the top 10 on V4 Pro or K3 at low effort | Sail pace up to $4/h while the balance stays above the guard line |
| Gym | Sail: 8 l boxes, up to 12 while the robustness queue is long | inside the same Sail pace |
| Diagnostician, architect, gate audit, post-mortem | **Claude Opus 5.5** (`claude-opus-5-5`) through the gateway, effort high | at most $70 of the $100 before Monday's open |
| Architect alternate, program review | OpenAI GPT-6 Astra and Sol, Flex | at most $80 of the $108 left in September; the $25 reserve stays |
| History, nightly forward | ThetaData, the data box's single session | subscription |
| Live quotes, SIP bars, orders | Alpaca through the gateway | subscription |

Claude integration facts (verified Sept 26 from Anthropic's model reference):

- Opus 5.5 costs $4 input, $0.20 cached input and $20 output per million tokens, against Astra's $10 /
  $1 / $50 (Flex $5 / $0.50 / $25).
- 1M-token context, 128K output. Batch runs at half price.
- The Messages API is not OpenAI's Responses API:
  - thinking cannot be disabled; control it with `output_config.effort`, whose default is
    `medium`, so set `high` explicitly;
  - forced `tool_choice` is refused (use `auto` or structured outputs);
  - no assistant prefill and no sampling parameters;
  - check `stop_reason` for `refusal` before reading content.
- Put the stable system prefix (the contract, the rules, the graveyard digest) under
  `cache_control`. The gateway meters input, cache-read, cache-write and output tokens separately.

## Order of work

The external clock is Monday's open. Everything else is dependency order. A slipped item never skips
its Done line. What misses Monday goes live at the first verified moment after it.

### Wave 0: now, configuration and operations only (no deploy)

1. Record the sprint's start in the run record: the time, this file's commit and the owner's
   decisions.
2. **Stop the retirement ratchet.** Edit `/workspace/state/swarm.json` on the House and keep a
   before-copy:
   - `population.floor` 44 (start 48, ceiling 96);
   - `architect.refill_seconds` 1200, `architect.every_seconds` 7200, `architect.max_refill` 12;
   - `tournament.retire_revisions` 200, `tournament.retire_evaluations` 4000.

   Done: alive families rising within two hours, deferral errors falling toward zero, and
   `verify_swarm` read with the floor's FAIL understood.
3. **The mid-fill diagnostic.** Re-run the best version of every alive family, and of every retired
   family that reached validation, on Validation at `--stress 0` and `--stress 0.5`
   (`league/gym/batch.py`).
   - Results stay private and never reach researchers; count them as diagnostic trials on the
     ledger.
   - The finding decides where Wave 1 pushes. If families turn positive at mid, execution is the
     binding constraint: favour D3 and patient mid-limit exits. If they stay negative at mid, the
     signals are the binding constraint: favour the architect, the diagnostician and the wider world.
4. **The gate goes on.** Set `gym.gate_checkpoint` to the core five's gate image recorded in
   `.data/gym/images.json`, the one paired with the active Gym image. Nothing is over the line, so
   this costs nothing until something is. Then a pass reaches its holdout look at once instead of
   waiting for a data ceremony.
5. **Data order.** Check whether the backfill can run stage 6 (SPY/QQQ back months to 45 DTE, about
   2 h) before it finishes stage 4 (the names, about 10.5 h) without losing progress. Either way,
   use the data box's single ThetaData session and never start a duplicate collector. If it can,
   reorder: longer horizons cost less spread per unit of edge than more short-dated names.
6. Push-notify the owner with the decisions still open (D5, D6) and the sprint's start.

### Wave 1: four builders, Saturday night (worktrees; one test process at a time; CI is the truth)

**B1 — the swarm's search** (`league/swarm/`, the highest impact; ships first as release R1)

- The `retire` tool:
  - offered only above `population.start` and after at least 2 validations;
  - never on the REVISE turn.
- **The robust Train objective:**
  - a family's best version is scored on its worst Train year: the per-year `t`, multiplied by the
    share of Train quarters that were positive;
  - to be eligible, a version needs the line's frequency on Train and positive P&L at 1.5x stress;
  - reset `best_train` so old and new scores are never compared.
- Researchers see Validation only as pass or fail and the number of checks passed (D2a).
- Families hold 1-5 roots from the admitted list, and the architect and researcher may set them.
  Take XSP out of the rotation for structures narrower than its fees allow.
- Robustness runs: per Train year, at 1.5x stress and at mid, queued automatically on idle boxes for
  every new best version, with the results in the researcher's diagnostics.
- The bandit's top 10 run on the stronger Sail profile at low effort.
- Re-seed the unused seeds and the graveyard's near-misses on roots they never tried.
- D2's line changes in `evidence.py`, committed with the owner's decision quoted in the commit.
- Tests for each change.

**B2 — the Gym's honesty and world** (`league/gym/`, `scripts/data/`; ships in R2 with the image adoption)

- Expiring legs:
  - far out of the money expire at intrinsic value;
  - only in-the-money or near-the-money legs are liquidated at natural (the venue's rule).
- The SEC fee set to zero.
- Positions and STATE carry across split boundaries: no forced natural closes between segments.
- A mid limit prices at the true mid rounded toward the order's side and fills per the fill model.
  Update `CONTRACT.md` to match.
- Admit 15-45 DTE for SPY and QQQ once stage 6 lands.
- If time allows, add to `ctx`: cross-root returns (SPY, QQQ, IWM), and an index implied-volatility
  level derived inside the Gym from the SPXW chain (never exported).
- Tests: the hand-computed P&L cases still reproduce to the cent, plus new cases for each change.

**B3 — Claude through the gateway** (`gateway/`, `league/frontier.py` or a sibling module, `league/swarm/models.py`)

- The gateway route `/v1/claude/messages`:
  - forwards to Anthropic's Messages API with `CLAUDE_API_KEY`;
  - caps Claude with its own funded meter (`CLAUDE_USD` = 100);
  - prices each model (Opus 5.5 and Sonnet 5 from Anthropic's page at build time), counting cache
    reads and writes;
  - settles refusals and errors honestly;
  - carries the role header; the kill switch applies.
- A House client with adaptive thinking, explicit effort, prompt caching on the stable prefix, no
  forced tool choice and no prefill.
- Roles: the diagnostician (new) and the architect on Opus 5.5 high, with Astra alternating. The gate
  audit on Opus 5.5 high, with Astra as fallback. Durable spend reservations as #380 built for OpenAI.
- First step: one probe call through the deployed route, confirming the key, the model ID and the
  meter.

**B4 — the live path** (`league/live/`, `league/swarm/bands.py`, `league/constitution.py`, `gateway/`; money code)

- The **observe band**:
  - every alive Gym family's current best validated version trades live shadow;
  - the version is pinned for the whole session;
  - no forward rows, never real;
  - switched in `swarm.json` so it can be turned off during the no-deploy window.
- **Long calls and long puts** as real types: constitution, gateway list, closing path, expiry-day
  rules, and tests against recorded venue responses.
- The **D3 calibration round trips**, with receipts through #381. Merge #381 after its independent
  review.
- The D4 money table in the constitution. The digest moves, so ratify within a minute of the deploy.
- One adversarial review in three lenses at once (money loss, evidence leakage, venue refusal).
  Fix the confirmed findings and re-verify only those.

### Wave 2: Sunday — two releases, then the search runs

1. **R1** (main plus B1), as soon as B1 is green and reviewed. It changes the Gym bundle (#382), so
   every family re-validates once; idle boxes make that cheap.
2. **R2**, by Sunday 16:00Z. Deploy the gateway first (Claude route, real types, caps), then the
   owner deploy of B2, B3 and B4 with `real_money` true. Then:
   - adopt the core-five image pair with 2022 in Train (v2b or the calibrated pair) in one
     verification pass: sealed with `no_network`, no holdout, forward days or key in the Gym, and
     manifest hashes matching;
   - point the gate at its partner;
   - `scripts/live_trading.py --enable options-swarm-20260928`, then `--ratify` within a minute;
   - verify on the box: the grant active on the running digest, real openings waiting on Monday's
     paper proof, the observe list populated, Claude calls metered.

   When the 20 names land, adopt the 25-root pair the same way.
3. **The search runs.**
   - Opus 5.5 architect waves read the graveyard, the robustness results and only the verdict of the
     Wave 0 diagnostic (execution-bound or signal-bound), never its per-family numbers.
   - The population fills to 48, then toward 96 while the Sail pace allows.
   - The diagnostician works the near-misses.
   - The gate audits and looks as families qualify.
4. **Watch every two hours.** Write the scoreboard into the run record, fix every defect with a test,
   and deploy fixes until Monday 10:00Z (the last feature deploy). Changes to `swarm.json` need no
   deploy.

### Wave 3: Monday pre-open (10:00-13:25Z)

1. Reconcile:
   - release identity;
   - House, swarm and data heartbeats;
   - the gate and image identities;
   - the Candidate and Probe lists: every Probe moved before 13:30Z, with its structure, maximum
     loss and why each Candidate is shadow-only;
   - grant, digest, gateway caps and types, kill switch off, equity, stops clear;
   - the observe list, the armed paper proof and the armed calibration program.
2. Read the day's expiry calendar and event flags.
3. Push-notify the owner with the Probe list and anything to do.

### Wave 4: Monday's session (13:30-20:00Z)

- **13:30Z:** observe shadow for every alive family. Candidates in shadow.
- **13:35Z:** the paper route proof. Real Probes open from their first signal after it passes.
  Calibration round trips (D3).
- **Every 30 minutes, check:**
  - fills against the Gym at mid and natural;
  - refusals;
  - the order count against 250;
  - buying power;
  - the stops;
  - the 0DTE cutoffs the venue actually enforces.
- **No deploy 13:25-20:05Z except a rollback.** `swarm.json` switches are allowed. On any money
  defect, use the kill switch first, then tell the owner.

### Wave 5: after the close, and on

1. **Post-mortem:**
   - every real and shadow trade against the Gym's expectation;
   - the fill model recalibrated from real fills (calibration round trips and Probes);
   - Net for the day: options P&L after fees, minus every input.
2. **After 20:05Z:**
   - re-integrate the prune #375 with everything since, and merge it with CI under 5 minutes;
   - rebase #385 on the new main and deploy it for post-burst budgets.
3. **Tuesday 06:00Z:** verify the first nightly forward collection and replays.
4. Keep going every session: new holdout passes become Probes, forward records size money, and
   compute follows Net (the plan's rule).
5. Write the report and update the memory.

## Scoreboard (every two hours in the sprint, and at each wave)

| # | Metric |
|---|---|
| 1 | Population: alive, running, births and retirements an hour, deferral errors |
| 2 | Throughput: cycles an hour, Gym box utilization, robustness runs queued and done |
| 3 | Robustness: families positive in every Train year; the mid-fill diagnostic (private); best robust score |
| 4 | Evidence: validation passes, gate audits, holdout looks and passes, the leakage alarm |
| 5 | Readiness: `real_money`, grant and digest, gateway types and caps, observe list, paper proof, calibration program |
| 6 | Monday on: shadow and real trades, real fills against the Gym, real options P&L, Net |
| 7 | Compute: Sail, OpenAI and Claude spend against the sprint budgets; Sail balance against the guard |

## Working rules

- **Speed over ceremony.** Checks that protect money, the holdout and licensed data stay. Receipts
  that only restate a check do not block a release. Money code gets one adversarial review with three
  lenses in parallel; fix the confirmed findings and re-verify only those.
- **Configuration before code.** `swarm.json` changes need no deploy and are the first lever.
- At most two releases before Monday, so every family re-validates at most twice.
- At most four builders, each in its own worktree. One test process at a time on the laptop (8 cores,
  7 GiB), under `flock /tmp/ltcm-options-tests.lock`. CI is the source of truth. Verify every change
  on the box.
- **Boxes:**
  - the House is `sb_1d99c4a7`;
  - the data box `sb_d69a1ebe` owns the only ThetaData session;
  - never fork a running House checkpoint into an uncontrolled clone;
  - no rollback before `20260926T084913Z-8158a11cfe3f`.
- `date -u` before every time written. Append the run record at every wave. A usage limit can stop
  the session for hours, so keep the record and the handoff current.

## Authority

**Authorized:** everything in the plan's Authorized list, and:

- real options trading on the Brokerage Account inside "Money on Monday" (D1, D4), including
  `real_money` true, enabling and ratifying `options-swarm-20260928`, the gateway's real types, and
  caps up to funded money;
- the D3 calibration round trips: House orders that no agent's intent produced. They are the only
  such orders besides the paper route proof;
- the D2 evidence reform exactly as written, and no other loosening;
- Claude API calls through the gateway up to the funded $100;
- `swarm.json` changes, Gym and gate image adoption, and turning the gate on;
- merging #381 after review, re-integrating #375 after Monday's close, and rebasing #385.

**Not authorized:** the plan's Not-authorized list stands. In particular:

- deposits, withdrawals or transfers; venue settings; secrets;
- naked short options;
- an evidence change beyond D2;
- real money for a family that has not passed the holdout (tuition and D3 aside);
- any cap above funded money;
- giving a Gym box the holdout or forward days;
- publishing or committing quotes, spreads, fitted parameters or programs;
- forcing a trade, or fabricating or back-filling evidence.

## Done

The sprint is done when all of these hold, or the record says with numbers why one cannot:

1. **Monday 13:30Z:**
   - every alive family trades observe shadow;
   - every family that passed the holdout trades real money at Probe size;
   - the paper proof passed;
   - the calibration round trips ran.

   Otherwise, the record names for each item what stopped it.
2. **Waves 0-2 are merged, deployed and verified on the box:**
   - the population held at 48 or more;
   - the robust objective live;
   - the Claude route live and metered;
   - the observe band;
   - long calls and puts as real types;
   - D2 as decided;
   - the gate on the adopted image pair.
3. The scoreboard carries the mid-fill diagnostic's verdict (execution-bound or signal-bound) and
   every validation pass, holdout look and result.
4. After Monday's close: the trade-by-trade post-mortem, real fills against the Gym, the fill model
   recalibrated from real fills, and the day's Net.
5. Tuesday's nightly forward job has run. The prune has merged after Monday's close, and #385 is
   rebased and deployed.
6. The swarm runs 24/7 with compute following Net. The report and the memory are written.

## The /goal message

The owner starts the sprint by pasting this, with D5 and D6 made true:

```
/goal Execute docs/goals/LTCM_SWARM_SPRINT.md (branch goal/swarm-sprint-2026-09-26; merge it to main first) autonomously until its Done list holds. It amends docs/goals/LTCM_OPTIONS_SWARM.md and continues the same run (T0 2026-09-26T06:23:14Z; run record docs/runs/2026-09-26-options-swarm.md and its handoff on branch run/options-swarm-2026-09-26: read them after the sprint file).

- One goal: a swarm of options-trading agents profitable on my Brokerage Account from Monday Sept 28's open (13:30Z). Agent time, not human time: use Sail, OpenAI, the Claude API, ThetaData and the Alpaca data plan to the full. Be bold: the money in the account can be lost fully. Keep the verifier honest: the sealed holdout and the live market judge; never force a trade or fake evidence.
- My decisions: D1 real money on for Monday: yes. D2 evidence reform as written: yes. D3 real-fill calibration round trips at $50 a day: yes. D4 money table at the bold end: yes. D5 deposit: <none | $AMOUNT initiated, landing DATE>. D6 Sail: <no top-up | $AMOUNT added>. D7 Claude API: $100 funded, key in the gateway as CLAUDE_API_KEY.
- Authority: the sprint's Authorized list (the plan's, plus real options trading inside the sprint's Money table, real_money true, enabling and ratifying options-swarm-20260928, the gateway's real types and caps up to funded money, the calibration round trips, the D2 change, Claude through the gateway up to $100). Nothing in its Not-authorized list.
- Method: Wave 0 configuration first; at most four builders in worktrees; one test process at a time on the laptop; one adversarial review of money code; at most two releases before Monday; verify every change on the box; the scoreboard every two hours; no deploy 13:25-20:05Z Monday except a rollback; report with numbers, including zero if nothing qualifies.
```
