# THE DONE RULE OF THE GOAL OF OCT 19, 2026 (V2): every 100 settled Probe+ real-money events

The pinned reading of the owner's Done for the event lane (EVL). Its sha256 is `league/events/done.py` `RULE_SHA256`,
and `league/tests/test_events_done.py` fails when this file and that constant differ: a change of this file is a new
rule, recorded as an amendment, never a silent edit. Written Oct 21, 2026, before any program was promoted (no row in
`bands` or `band_history`; 26 real round trips, every one at learning size): no checkpoint can have been seen.

## The goal's words, verbatim (goal-2026-10-19/GOAL-MESSAGE-V2.txt)

"Done (read every 100 settled real-money events at Probe size or above): >= 300 such events, all after their program's
promotion, from >= 3 programs with >= 50 each; realized after-fee P&L positive; the 95% issuer-block bootstrap lower
bound of per-event after-cost return above zero; realized profit since the first promotion >= metered compute over the
same span; fills within 15 bp of replay; the last 100 of those events with no captain step."

"Pivot, never stall: a lane whose 95% upper bound of per-event after-cost return is below zero at 400 events is retired
and its budget moves to the next lane; when the $800 loss budget is spent, stop all spend and report. Report
account-shown profit first, Net after costs beside it."

## The reading

1. WHAT COUNTS (a "Probe+ event"). A settled real-money round trip of a seating program version
   (`league/events/programs.py` `SEATING`): a `buy` and a `sell` row of the same (program, version, event) in the lane's
   `real_fills` (`league/events/bands.py` `real_events`), whose BUY fill's `band` is `probe` or `sized`, and whose buy
   was filled AFTER the program's promotion: strictly after the moment of its latest move to `probe` in `band_history`
   as `bands.probe_since` reads it (the later of the move's `since` and its `written_at`). A program with no move to
   probe on record has no Probe+ event; a buy whose time cannot be read is not counted. Probe+ events bought before the
   latest move to probe (an earlier Probe stay, before a demotion and a return) are reported beside as
   `before_promotion`, never counted. The order of the count is the sale's time, then program, version and event.
2. PER-EVENT AFTER-COST RETURN. `r` = (sale proceeds - buy cost) / buy cost, at the broker's fill prices, quantities
   and posted fees (the regulatory fees the broker posts on a sale update its row): proceeds = sell qty x sell price -
   sell fee; cost = buy qty x buy price + buy fee (`bands.real_events`). P&L is proceeds - cost, account-shown.
3. WHEN IT IS READ. At every 100th Probe+ event: checkpoint c (100, 200, 300, ...) is written at the House's first
   nightly reading at which at least c events count, and it reads EXACTLY THE FIRST c events in the count's order. A
   written checkpoint is never rewritten (the history in `<state>/events/done.json` is append-only); a count that falls
   (a demotion and a return to Probe) writes no checkpoint until it reaches the next unwritten multiple of 100. The
   figures that are not over the c events (item 4.6's profit and compute, item 7's loss budget) are read at the
   checkpoint's writing and say when.
4. THE ITEMS, each with its number and pass or fail; Done holds at checkpoint c when every one passes:
   1. `events`: c >= 300.
   2. `programs`: at least 3 programs (program, version) each with at least 50 of the c events.
   3. `after_promotion`: every counted event was bought after its program's promotion (item 1 makes it so; the
      `before_promotion` events beside it are the ones left out).
   4. `pnl`: the c events' summed realized after-fee P&L above $0.
   5. `bound`: the 95% issuer-block bootstrap lower bound of the per-event after-cost return `r` above zero:
      `league/events/screen.py` `bootstrap_bounds(rows, "issuer", 0.95, 10000, seed_of("DONE-RULE-EVL-2|done|issuer"),
      sided="two")`, its `lower` (the 2.5th percentile of 10,000 resampled means; issuers, the intent's `cik`, else its
      symbol, resampled with replacement to their observed count, each resample's mean over all its events).
   6. `profit_vs_compute`: the lane's realized profit since the first promotion >= the metered compute over the same
      span. FIRST PROMOTION: the earliest move to `probe` in `band_history` (any seating program), at the later of its
      `since` and `written_at`. PROFIT: the P&L of every settled real-money event of the lane, EVERY band (learning
      money is real money), whose sale is at or after the first promotion. COMPUTE: `league/ops/metered.py`
      `since(ledger, <the first promotion's UTC day>, <the reading's time>)` over `<state>/metered.json`, the House's
      measured meters (the Sail guard's metered spend, the gateway's settled Claude meter, its OpenAI meter, the fixed
      Cloudflare and data fees), from 00:00 UTC of that day. The item fails while the compute is unmeasured (`usd`
      None) or partly measured (`partial`).
   7. `fills`: real fills within 15 bp of replay: the signed mean gap PER SIDE over the c events against the shadow's
      auction prices in `outcomes` (the same program, version and event), each made raw again by dividing out the
      split and dividend adjustment the score applied (`bars` adjusted close / raw close of the day, 1.0 when a bar is
      missing, as `league/events/score.py` `_ratio`): entry gap = (buy price / shadow entry - 1) x 10,000; exit gap = (1
      - sell price / shadow exit) x 10,000, the exit on the session it actually exited (`screen.exit_overrides`, else
      the intent's `exit_day`); positive when real money did worse. Passes when both sides have at least one gap and
      each side's |mean| <= 15 bp. An event with no outcome or a zero price has no gap on that side.
   8. `no_captain`: the last 100 of the c events (events c-99 to c) settled with no captain step: in the span from the
      earliest buy to the latest sale among them, the House's records show none of
      - AN OPERATOR EDIT: a file in the House's state root named `swarm.json.before-<what>-<YYYYMMDDTHHMMSSZ>`,
        `ops.json.before-...` or `budget.json.before-...` (the operator tools' before-copies, e.g. `scripts/set_swarm.py`
        "set", `scripts/agenda_install.py` "agenda") whose stamp is in the span; or the modification time of
        `<state>/swarm.json` or `<state>/ops.json` in the span (an edit with no before-copy; the House only reads both
        files);
      - AN OWNER STEP: an `ok` `stall` run in `<state>/ops.sqlite` (`runs`, job `stall`) due in the span with a check
        that is `stalled` and names an `owner_step` (any cause but `done`, which is news, not a step);
      - NOBODY LOOKED: a UTC day of the span with no `ok` `stall` run fails the item (a day the stall job did not run is
        never a day with no step waiting).
      A release deploy is not a captain step by this rule (the goal's item 5 asks to ship continuously; each release
      is judged by CI on its exact head and its money and constitution digests are checked when it ships).
5. BESIDE, NEVER COUNTED. Learning-band events (count and P&L), the `before_promotion` events, and the BENCHMARK-NET
   figure: a = r - b with b the shadow's benchmark return of the same event (`outcomes.b`), its mean and its 95%
   issuer-block lower bound (seed `DONE-RULE-EVL-2|done-a|issuer`), so a rising market is visible beside the after-cost
   test. The Done test is on `r` as the goal states.
6. THE PIVOT. At every checkpoint c >= 400: when the 95% upper bound of the c events' per-event after-cost return is
   below zero (`bootstrap_bounds(rows, "issuer", 0.95, 10000, seed_of("DONE-RULE-EVL-2|pivot|issuer"), sided="one")`,
   its `upper`: the 95th percentile, as PREREG-EVL-1's Kill reads it), the event lane is to be retired and its budget
   moved to the next lane. The reader says so in its record; it changes nothing (a band move or a retirement is the
   judges' and the captain's, by amendment).
7. THE $800 STOP. At each reading (item 3): the loss budget's total from inception, the House's own figures
   (`league/ops/fast_lane.py` `probe_budget` over `<state>/live.sqlite`, read-only: `realized_total_usd` +
   `at_risk_usd` against `total_budget_usd`, $800, the 95% holding-period open risk as the money table counts it).
   SPENT when the total realized loss plus the open risk is at least $800: then all spend stops and is reported. The
   reader reports it; the money table's walls already refuse every new entry past the room.
8. READ ONLY. The reader (`league/events/done.py`) opens nothing for writing but `<state>/events/done.json`; the House
   runs it in the nightly screen task after the band review and keeps a `done` receipt. It sends no order, moves no
   band, changes no setting and never reads a price after an event other than the real fills and the shadow's own
   prices. The old `dlane` Done meter (DONE-RULE-A50) keeps running beside and is never read for this Done.
9. REPORTING. Account-shown profit first, Net after costs beside it (`league/ops/daily_report.py`'s one-screen report
   carries one Done line: the Probe+ events toward 300 by program, the next checkpoint, the bound).
10. AMBIGUITY. Where this reading is ambiguous, the reading less likely to pass is taken, fixed before the first
    promotion and recorded as an amendment; a later resolution is a new rule file and a new sha256.
