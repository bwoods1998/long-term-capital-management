# THE DONE RULE OF THE GOAL OF OCT 19, 2026 (V2): every 100 settled Probe+ real-money events

The pinned reading of the owner's Done for the event lane (EVL). Its sha256 is `league/events/done.py` `RULE_SHA256`,
and `league/tests/test_events_done.py` fails when this file and that constant differ: a change of this file is a new
rule, recorded as an amendment, never a silent edit. Written Oct 21, 2026, before any program was promoted (no row in
`bands` or `band_history`; 26 real round trips, every one at learning size): no checkpoint can have been seen.

AMENDED BY A84 (Oct 21, 2026, about 20:00Z, the review of `feat/done-reader`; still before any promotion: the House
read at 19:36Z had 0 rows in `bands` and `band_history`, no `done.json` and no `done` receipt): item 1 counts every
Probe+ buy after the program's EARLIEST move to probe (a demotion drops nothing) and item 4.3 fails on a Probe+ event
left out of the count; item 3's history is kept in an append-only log as well, and a record that cannot be read is
never written over; item 4.8 is never a pass from the House's records alone, and Done at a checkpoint waits on the
captain's attestation of its span; a deploy's hand steps are captain steps. Each is item 10's reading less likely to
pass.

AMENDED AT RELEASE 1019f's INTEGRATION (Oct 21, 2026; the captain's A86 REVISED and the record of the Probe size,
`fix/probe-target-honesty` and its independent check; still before any promotion): item 1's "AT PROBE SIZE OR ABOVE"
reads the buy's record: the dollars its send asked (`sized_usd`: the whole shares sent x the limit) against its band's
target (`target_usd`), never the fill's cost (which the open's gap moves); a buy without that record is not at Probe
size. It is item 10's reading less likely to pass.

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
   was filled AFTER the program's PROMOTION: strictly after the moment of its EARLIEST move to `probe` in
   `band_history` (`league/events/done.py` `promoted_at`: the later of that move's `since` and its `written_at`).
   Every Probe+ buy after the promotion counts, whatever the program's stays since: a demotion and a return to Probe
   drop nothing (a demotion fires on losses only, so the stay it ends is never left out; the band review's own current
   stay, `bands.probe_since`, is not this count). The `before_promotion` events are a GUARD, never counted: a Probe+
   buy of a program with no move to probe on record, one not after its promotion, or one whose time cannot be read
   (item 4.3 fails on one inside a checkpoint's span). AT PROBE SIZE OR ABOVE (release 1019f): a Probe+ buy after
   its promotion counts only when its `real_fills` buy row's `sized_usd` (the whole shares its send asked x its limit,
   1.25 x the previous close) is at least `PROBE_SIZE_SHARE` (0.8) x its `target_usd` (its band's `position_share` x E
   at the previous close: Probe 3.5% from the captain's A86 REVISED, Sized 10%): a full, uncut buy counts whatever the
   open's gap (a fill near the previous close costs about 0.8 of its target, so the fill's cost is never the test); a
   buy a wall, the cash, the loss budget or the floor to whole shares took under 0.8 of its target does not, nor a
   Sized buy under 0.8 of the Sized target, nor one whose `sized_usd` or `target_usd` is missing (a buy sized before
   release 1019f recorded them). Those are `under_size`: reported beside, never counted, failing nothing; the
   `before_promotion` guard is read first, whatever the size. The order of the count is the sale's time, then program,
   version and event.
2. PER-EVENT AFTER-COST RETURN. `r` = (sale proceeds - buy cost) / buy cost, at the broker's fill prices, quantities
   and posted fees (the regulatory fees the broker posts on a sale update its row): proceeds = sell qty x sell price -
   sell fee; cost = buy qty x buy price + buy fee (`bands.real_events`). P&L is proceeds - cost, account-shown.
3. WHEN IT IS READ. At every 100th Probe+ event: checkpoint c (100, 200, 300, ...) is written at the House's first
   nightly reading at which at least c events count, and it reads EXACTLY THE FIRST c events in the count's order. A
   written checkpoint is never rewritten: each is appended once, whole, to `<state>/events/done-history.jsonl` before
   `<state>/events/done.json` is written again, and the history is the two together (the log's record of a c wins).
   When `done.json` exists but cannot be read at its schema (a cut write, a restore, a release of another schema),
   when the log has a line that cannot be read, or when a `done` receipt names a checkpoint that neither holds, the
   reader writes nothing and the House warns (`done.py` `Unreadable`): a lost record is never written again from a
   later night's figures. A count that falls (a fill row lost, a version out of `SEATING`) writes no checkpoint until
   it reaches the next unwritten multiple of 100. The figures that are not over the c events (item 4.6's profit and
   compute, item 7's loss budget) are read at the checkpoint's writing and say when.
4. THE ITEMS, each with its number and pass or fail; Done holds at checkpoint c when every one passes (item 8: or
   reads unverifiable and the captain's attestation of its span is read):
   1. `events`: c >= 300.
   2. `programs`: at least 3 programs (program, version) each with at least 50 of the c events.
   3. `after_promotion`: every Probe+ event of the span was bought after its program's promotion: the count (item 1
      makes it so) and no `before_promotion` event sold at or before the c-th counted event's sale (a Probe+ buy with
      no promotion on record is a Probe+ event the count cannot hold, so the item fails rather than leave it out).
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
      earliest buy to the latest sale among them. The item reads FAIL when the House's records show any of
      - AN OPERATOR EDIT: a file in the House's state root with `.before` in its name (an operator tool's before-copy,
        stamped `<file>.before-<what>-<YYYYMMDDTHHMMSSZ>` or not, e.g. `swarm.json.before-train2020`), or one of
        `swarm.json`, `ops.json`, `PAUSE`, `swarm.stop`, with a moment in the span: its stamp, its modification time
        or its status-change time (ctime: a copy's own making, which neither a copy that keeps the original's mtime
        nor a later `touch` moves back);
      - A CAPTAIN STEP AT A STALL RUN: an `ok` `stall` run in `<state>/ops.sqlite` (`runs`, job `stall`) due on a UTC
        day of the span with a check that is `stalled` and names an `owner_step` (any cause but `done`, which is news,
        not a step), or that found a pause (`paused`: `maintenance_pause` or `swarm_stopped`) or the gateway's kill
        switch (`kill_on`: `kill_switch`) standing, however briefly;
      - NOBODY LOOKED: a UTC day of the span with no `ok` `stall` run (a day the stall job did not run is never a day
        with no step waiting);
      or when those records cannot be read. Otherwise it reads UNVERIFIABLE, NEVER A PASS: the House keeps no record
      of every operator channel (a Sail exec such as boxrun, `floor_box`, the ship scripts, the gateway's admin), of a
      pause or a kill-switch flip between two stall runs, or of a hand write to sqlite, kv or the bands, and a change
      after the span can hide one in it. The reader names, beside, the operator files changed after the span and the
      owner's deploys in the span from `<base>/deploys.jsonl` (a promotion or rollback with no updater `sha`, no
      drill's). A release deploy itself (the ship script's own run) is not a captain step (the goal's item 5 asks to
      ship continuously; each release is judged by CI on its exact head and its money and constitution digests are
      checked when it ships); EVERY HAND STEP OF A DEPLOY'S RUNBOOK IS ONE (a setting written, a research switch, a
      script run on the box), the reading less likely to pass.
      THE CAPTAIN'S ATTESTATION. A checkpoint c >= 300 whose every other item passes and whose item 8 reads
      UNVERIFIABLE is written with `pending` "attestation"; Done holds at c when an attestation of c is read: one JSON
      line in `<state>/events/done-attest.jsonl`, appended after the span, `{"c", "from", "to", "steps", "execs",
      "sha256", "at"}`: the checkpoint, its item-8 span exactly as the checkpoint records it, the calls of every
      operator channel the captain's own records show in the span (boxrun's `calls.log`, `floor_box`, the ship
      scripts, the gateway's admin; `execs`), the `steps` among them (a call that writes on the House or the gateway
      or changes a setting, a deploy's hand steps included, the ship script's own run excepted; a call that cannot be
      shown to write nothing is a step), the sha256 of the record it was read from, and when it was written (at or
      after `to`). It is taken only when `steps` is the integer 0 and every attestation of c in the file names the
      same span with steps 0, and only from a file that reads whole. The checkpoint is never written again; the
      attestation is read beside it every night. A later release that gives every operator channel an append-only
      record on the House may make item 8 a pass from the House's records, by a new rule.
5. BESIDE, NEVER COUNTED. Learning-band events (count and P&L), the `before_promotion` and `under_size` events, and
   the BENCHMARK-NET figure: a = r - b with b the shadow's benchmark return of the same event (`outcomes.b`), its mean
   and its 95% issuer-block lower bound (seed `DONE-RULE-EVL-2|done-a|issuer`), so a rising market is visible beside
   the after-cost test. The Done test is on `r` as the goal states.
6. THE PIVOT. At every checkpoint c >= 400, over the same c events as the count (item 1: every Probe+ event after
   each program's promotion, a demoted stay included): when the 95% upper bound of their per-event after-cost return
   is below zero (`bootstrap_bounds(rows, "issuer", 0.95, 10000, seed_of("DONE-RULE-EVL-2|pivot|issuer"), sided="one")`,
   its `upper`: the 95th percentile, as PREREG-EVL-1's Kill reads it), the event lane is to be retired and its budget
   moved to the next lane. The reader says so in its record; it changes nothing (a band move or a retirement is the
   judges' and the captain's, by amendment).
7. THE $800 STOP. At each reading (item 3): the loss budget's total from inception, the House's own figures
   (`league/ops/fast_lane.py` `probe_budget` over `<state>/live.sqlite`, read-only: `realized_total_usd` +
   `at_risk_usd` against `total_budget_usd`, $800, the 95% holding-period open risk as the money table counts it).
   SPENT when the total realized loss plus the open risk is at least $800: then all spend stops and is reported. The
   reader reports it; the money table's walls already refuse every new entry past the room.
8. READ ONLY. The reader (`league/events/done.py`, behind `league/ci.py`'s wall: no main commit the House's updater
   ships can change how Done is read) opens nothing for writing but `<state>/events/done.json` and the append-only
   `<state>/events/done-history.jsonl`, and only reads `<state>/events/done-attest.jsonl`. The House runs it in the
   nightly screen task after the band review and keeps a `done` receipt. It sends no order, moves no
   band, changes no setting and never reads a price after an event other than the real fills and the shadow's own
   prices. The old `dlane` Done meter (DONE-RULE-A50) keeps running beside and is never read for this Done.
9. REPORTING. Account-shown profit first, Net after costs beside it (`league/ops/daily_report.py`'s one-screen report
   carries one Done line: the Probe+ events toward 300 by program, the next checkpoint, the bound).
10. AMBIGUITY. Where this reading is ambiguous, the reading less likely to pass is taken, fixed before the first
    promotion and recorded as an amendment; a later resolution is a new rule file and a new sha256.
