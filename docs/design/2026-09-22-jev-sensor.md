# Jev as the cheap sensor and router

Sept 22, 2026, overnight rebuild, section 2 of `docs/goals/LTCM_OVERNIGHT_GOAL.md`. This turns
Jev from a continuous market labeller into a cheap semantic step that sits in front of expensive
work. Jev still has no order, promotion, spending or merge authority.

## 1. The semantic lab is off by default (`config.json` `"semantic_lab": false`)

The lab ran from Sept 20 20:23 UTC to Sept 22 06:50 UTC. It completed 136,308 labels with 239
unconfirmed, and spent **$13.93** of the $20 lifetime Jev cap: $13.67 on 128,179 market labels
(324M input tokens). Its three evolved-question rounds cost another $0.86 of Astra.

The evaluation below is free and read-only, run on its own store (`/workspace/state/semantic.sqlite`):

- **Rows.** Each row joins the 8 fixed noul features to later minute-sampled quotes of the same
  market. In the executable variant a stale label enters at the first quote after the label
  existed; 67% of labels were fresh, with a median lag of 76 s.
- **Split.** Chronological at 60% of the time range. Test events never appear in training.
- **Models.** Three arms on identical rows: base rate, a numeric logistic model (mid, spread,
  log OI, hours, drift), and the numeric model plus the 8 Jev features.
- **Intervals.** 95% intervals come from an event-clustered bootstrap.

Scripts and full output are in `scripts/jev_lab_eval/`. The bulk extracts stay private.

| executable rows | 5 min | 15 min | 60 min |
|---|---:|---:|---:|
| test rows / unseen events | 38,124 / 473 | 36,061 / 142 | 27,928 / 72 |
| share of flat mids | 0.60 | 0.53 | 0.37 |
| mean \|mid move\| vs mean half-spread | 0.0166 vs 0.0229 | 0.0147 vs 0.0237 | 0.0179 vs 0.0272 |
| "moves at all": AUC numeric / +Jev | 0.609 / 0.766 | 0.616 / 0.757 | 0.659 / 0.749 |
| **direction** (moving mids): AUC numeric / +Jev | 0.557 / 0.549 | 0.540 / 0.541 | 0.558 / 0.529 |
| direction Brier gain from Jev [95%] | −0.0014 [−.0022, −.0002] | −0.0004 [−.0017, +.0010] | −0.0044 [−.0107, −.0002] |
| trade at P>0.55, $/contract after spread (numeric / +Jev) | −0.053 / −0.049 | −0.082 / −0.084 | −0.026 / −0.034 |
| same trades, mid to mid, frictionless | −0.0001 / −0.0000 | −0.0005 / +0.0004 | −0.0003 / +0.0001 |
| perfect foresight: share of rows profitable after spread | 0.103 | 0.106 | 0.154 |

**Verdict: no incremental tradable value.**

- **The lab's own gain is real but is not direction.** Its "up vs not" gain (+0.010 Brier) is
  real, but it measures whether a midpoint moves at all, not which way.
- **Direction.** Jev adds nothing to direction and makes it worse at 5 and 60 minutes.
- **Tradability.** Every threshold trade loses 2 to 8 cents a contract after the spread, with or
  without Jev. The typical move is smaller than half the spread.
- **Caveats.** Observations are heavily correlated, there are only 72 unseen events at 60
  minutes, and the quotes are REST samples, not fills.

**Switch.** The lab stays constructible behind `"semantic_lab": true` during a burst.

## 2. Measured research waste the gate targets

The production ledger for Sept 19 to 22 holds 7,370 research summaries costing $160, a median of
$0.016 per session:

- **Abstentions.** 6,531 (88.6%) ended with no candidate and no replay.
- **Candidates.** 489 retained a candidate.
- **Provider failures.** 325 failed at the provider.
- **Replays with no candidate.** 25 ran a replay and kept nothing.

Abstention predicts abstention:

| consecutive abstentions before the session | 1 | 2 | 3 | 5 or more |
|---|---:|---:|---:|---:|
| sessions that retained a candidate | 11% | 7% | 6% | 3.3% (147/4,513) |

### Offline replay of the gate

`scripts/jev_lab_eval/gate_replay.py` replays the gate's deterministic rules, on the v0 dials
(`after` 2, `max_factor` 8), over the same 7,370 sessions, read-only:

| Measure | Result |
|---|---:|
| Sessions the gate would have skipped | **4,978 (67.5%)** |
| Model cost of those sessions | **$86.56 of $160.17** |
| Skipped sessions that had abstained | 4,674 |
| Skipped sessions that were provider failures | 157 |
| Skipped sessions that retained a candidate (the estimated miss) | **146 (2.9%)** |

Most retained candidates fail replay, so the true miss rate for useful work is lower.

The replay is approximate:

- It has no triggers for market availability, a lifting blocker or Jev relevance, so it
  overstates skips.
- It ignores the 10% sample that would still run.
- It assumes each skipped session would have abstained again.

Treat it as a planning estimate. The live `report()` numbers are the measurement.

## 3. What is built

| Piece | Module | House hook |
|---|---|---|
| Capped, cached, batched Jev client with a breaker | `league/jev.py` (`Sensor`) | built in `service.build` |
| Research gate plus `report()` / `python -m league.research_gate LEDGER` | `league/research_gate.py` | `House.research_due` → `JevFloor.research_due` |
| Explicit `agent.inactive` reasons | `league/research_gate.py` (`Inactivity`) | `House.tick` → `JevFloor.tick`, swept every 5 min |
| Triage into `repair.reported` (`source: triage`) and `triage.item` | `league/triage.py` | background job every 30 min |
| Hypothesis memory: `hypothesis.link` and `failure_history()` | `league/hypothesis_memory.py` | background job every hour |
| Exposure groups, report only | `league/exposure.py` | background job every 30 min; `health.json` `jev.exposure` |

`health.json` gains a `jev` block. It holds Sensor spend and caps, gate totals, inactivity
counts, triage groups, the hypothesis index and exposure groups.

### Research gate rules

- **Where it runs.** The gate runs inside `House._gate`, the overnight v0 gate, and replaces it
  whenever the Jev floor is wired. It uses the same dials in `game.json` `research.gate`:
  `enabled`, `after`, `max_factor` and `sample_percent`. It keeps the v0 row shape and adds
  extra fields: `triggers`, `cost_usd`, `sessions`, `inactive`. It runs only after every existing
  check and the clock say a session is due, so it can only skip. The refusal fast path is
  unchanged.
- **Always run.** The following always run a session:
  - its own fills and settlements;
  - a new `book.refused`;
  - a code or rung change;
  - a material `eval.verdict` (not `look`/`progress`);
  - a `tool.fulfilled` for a request from its line;
  - new credits;
  - another agent's note in its niche;
  - a market opening or closing;
  - a Kalshi window becoming non-empty;
  - a blocker lifting.
- **Last session produced something.** A clock-due session runs.
- **Abstention.** From `after` consecutive empty passes the interval doubles per further empty
  pass, up to `max_factor`. With the defaults (2 and 8) that is ×2 after two, ×4 after three and
  ×8 after four. A pass counts as empty when it has no candidate, no replay and no strategy
  written by Merton, as in v0. A provider failure neither adds to nor resets the count.
- **Known blockers.** An agent blocked by missing data or a closed market waits for the blocker
  to change.
- **Heartbeat.** Every agent runs at least once every 24 h.
- **Jev.** Jev answers only "does this note or lesson from outside the niche matter to this
  strategy?".
  - Answers are cached by (note id, strategy sha) and batched 16 notes to a request.
  - Any p ≥ 0.35 runs, so an uncertain answer favours research.
  - If Jev is down or capped, the deterministic decision stands.
- **Sampling.** `sample_percent` (10%) of would-be skips run anyway as `sample`. The choice is a
  hash of the agent, the window and the slot, so a restart does not re-roll it.
- **What v0 did not have.** Routine `look`/`progress` verdicts no longer count as news. They
  arrive every mark, so under v0 a paper agent almost never backed off.
- **Miss rate.** A miss is a sampled session that retained a candidate or adopted code. `report()`
  prints skipped sessions, estimated savings (skipped × median session cost), the sampled miss
  rate and Jev spend.
- **Ledger rows.** Repeated identical skips are aggregated (`sessions` counts them), so one row
  covers up to 12 skipped sessions.
- **Failure.** A gate that raises fails open to the clock.

## 4. Jev budget and live probe

- **Caps.** `config.json` `jev` caps Jev at $0.25 and 400 calls per UTC day, split per purpose
  as gate 150, triage 120, links 60 and exposure 40.
- **Unconfirmed calls.** A call whose cost is unconfirmed counts as $0.003, the 64k-token worst
  case.

Live probe, Sept 22, from the Mac. The labels were frozen before the calls. There were two
requests and 16 questions:

| Question | Agreement | Threshold | Latency | Cost |
|---|---:|---:|---:|---:|
| "Does this text report a House defect?" | 12/12 (yes 0.89–0.94, no 0.05–0.21) | 0.7 | 0.61 s | $0.000069 |
| "Same missing feed as the reference request?" | 3/4 (a settlement-source request scored 0.14, so it stays separate; a true duplicate scored exactly 0.80) | 0.8 | 0.60 s | $0.000028 |

Total development spend was **$0.000097**. This is a small curated set, not a held-out
benchmark. The same-feed threshold sits on the edge of a true positive, and a missed merge
leaves a duplicate report, which is the safe failure.

## 5. Triage and hypothesis links on production text (read-only copy, real Jev)

The dry run used 11,192 production rows from Sept 19 to 22 (tool requests, post-mortems,
research summaries, journals and research thoughts), copied into a local ledger. It ran four
capped triage runs and three link runs:

- **Triage groups.** The 3-day backfill produced 147 groups and 227 `repair.reported` rows:
  - 208 for missing data (tool requests and the abstentions they cost);
  - 18 `bug_report`;
  - 1 `strategy_defect` (a `stuck` death).

  The run predates two changes. Tool requests are now keyed exactly as the repair worklist
  (night/repairs, #94) keys them, with the same excerpts, so the worklist's fold counts a row
  once whichever reporter wrote it. Every request is now `missing_data`; the run had split 19 off
  as `shared_defect`.
- **Request merges.** Jev merged 6 differently named requests into older groups. Examples:
  - `crypto_strike_spot_and_vol` and `kalshi_15m_underlying_spot_on_replay_tap` into
    `kalshi_crypto_underlier`;
  - `attention_count_snapshot` into `kalshi_attention_underlying_value_feed_c`;
  - `kalshi_sports_historical_settlement_tape` into `sports_price_history_with_outcome`.
- **Unrequested missing data.** Abstentions that cite missing data without a request join one
  group per niche, `missing_data:research:<niche>`. That is the worklist's own key for research
  that stops at a missing input. A key per sentence had produced 897 groups.
- **Bug groups.** There are 17 bug groups. They include:
  - the options desk's OCC exit-routing bug, which it restated across several passes;
  - "replay still miscounts diesel as wins";
  - a stale-rest defect that leaves resting bids dead;
  - underlying SIP quotes without timestamps;
  - an option chain still stamped Friday on Sunday.

  Some are strategy bugs rather than House bugs. The labels are fallible, and the repair queue
  decides.
- **Hypothesis index.** It holds 484 mechanisms, from docstrings and candidate purposes. Jev
  answered 62 pairs: 22 `related` and 40 `distinct`. None reached the 0.9 bar for `rewording`.
- **Cost.** Development Jev spend was 77 calls and 322 cached answers for $0.0049, with a median
  latency of 0.55 s. The live probe in §4 adds $0.0001. One call was refused as a repeated
  identity (409) and is counted locally at the $0.003 worst case. Request identities are now
  salted per store, and the total is at most $0.008 of the $0.30 authorized.

## 6. Switches (all in `league/config.json` unless noted)

- `"semantic_lab": false` turns off the continuous lab.
- `game.json` `research.gate.enabled: false` turns every research gate off, v0's and this one.
- `"jev": {"enabled": false}` removes the whole sensor; the House behaves exactly as before.
- `jev.research_gate.enabled`, `jev.triage.enabled`, `jev.hypothesis_links.enabled` and
  `jev.exposure.enabled` each switch one piece off.
- `daily_usd`, `daily_calls`, `purpose_calls`, `sample_rate`, `backoff_max_multiple` and
  `max_skip_hours` are dials.
