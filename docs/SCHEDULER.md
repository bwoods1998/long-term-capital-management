# The decision scheduler: one pre-registered slot per file at each auction (release 1019i, A120)

For the branches that add a file's part (feat/evl-6, feat/evl-7, feat/evl-8, PREREG-EVL-9's), and for the reader of
the timing table in [events.md](events.md). The code is `league/events/scheduler.py` (behind league/ci.py's wall, as
calendar.py's decision times are), its House hooks in `league/events/house.py` (`SLOT_TASK`'s comment), its book
hooks in `league/events/book.py` (`slot_of`, `slot_files`, `send_window`, `slot_receipt`) and
`league/equity/live.py` (`_event_decide_slots`, `_event_send`'s per-file windows). Tests:
`league/tests/test_events_scheduler.py`.

## As merged (release 1019n-r2, onto release 1019m-cost; A152)

The branch below was built on release 1019h and is merged onto today's main with these readings, each held by a test:

- **PREREG-EVL-7's learners are NOT a scheduler file.** Their own live receipt (`decide-<at>-lrnlive:<D>`, run by
  run.py's `learner_part` after the House's receipt) and the book's learners' pass (`_event_decide_lrn`: R3's births
  after the learners in ROOM, A140's last-minute rule at both auctions) stay exactly as live since release 1019j:
  PREREG-EVL-7 section 1.9's ROOM, which the "feat/evl-7" adoption below would have moved into the main slot. Every
  later file's pass waits for the learners' pass.
- **A later file's book pass** (`_event_decide_slot`) plans at the first tick inside its window at which the main pass,
  the learners' pass and every earlier file's pass are decided and its own live receipt is made, carrying release
  1019l's per-program rules (`max_open(band, program)` less the seat's count, the `evl6` flag's Probe slots, the
  unsettled-stay hold, its summary merged into the auction's own row, the window row at the last book minute, A140's
  late learners' pass read as a pass still waiting); its buys go after every main row's (`_file_rank`) and its entries
  keep the earlier rows' orders on the day's line.
- **A file may have no catch-up** (`catchup` None: PREREG-EVL-10's session with no live run has no decision).
- **A slot never takes an earlier file's turn**: after a clock-started slot before the main decision the House's turn goes
  on into the task that was due (house.py `_clock_slot`).
- **The registered parts are imported by every reader of them** (`PART_MODULES`, `load_parts`), so no reader ever sees
  a file's program as a main row. The one registered part is PREREG-EVL-10's READER-2 (league/events/reader2.py), its
  row the close table's last (docs/events.md's timing table; the digest `3514111b`, the main rows alone `40a08163`).

## The problem it removes

The House makes ONE open decision (09:15 ET) and ONE close decision (its first tick at or after 15:47:00 ET, orders
sent by 15:49:00 ET). Every new file added its own isolated part INSIDE that one decision (PREREG-EVL-5's 45 s;
PREREG-EVL-7's learners 90 / 120 s; PREREG-EVL-8's PX 60 s and META 30 s; PREREG-EVL-9's warm part), and both
PREREG-EVL-7's and -8's re-checks found the structural blocker: the parts cannot all fit before the send line, a
part's bound is measured from its own start (so the parts' bounds add), and a late part delays or loses real money
for the rows behind it.

## The design

- **A timing table, one pinned constant per auction** (`scheduler.TABLE`, sha256 `scheduler.digest()`; the pinned
  digest is in `test_events_scheduler.TheTable.test_the_digest_is_pinned`): each file's slot states its start, its
  bound, the book's send window for its buys, its receipt kinds and the slots it follows. Every time is a `Wall`, an
  offset from the session's own open or close, so an early close (13:00 ET) moves every close-side row with the
  session.
- **The main slot** (file `main`: every row of PREREG-EVL-1 to -6 and R3's births) keeps EXACTLY today's timing. Its
  rows are read from the constants the House and the book already run on (`scheduler.main_rows`: calendar.py's
  `OPEN_DECIDE_AT` and `CLOSE_DECIDE_BEFORE`, house.py's `DECIDE_BUDGET` and `CLOSE_GRACE`, schedule.py's
  `EVENT_DEFAULTS`), and a test pins them, so the table cannot state a main timing other than today's. The main
  decision's code (run.py `decide_open` / `decide_close`, PREREG-EVL-4's and -5's parts inside it, `part_hold`,
  `HeldAhead`, ROOM) is untouched: the simulation test shows the main receipt and the main rows' intents
  byte-identical with and without a file's part registered.
- **A file's slot** runs in ITS OWN RUN on the House's lane: a task of its own with the slot's bound measured from its
  own start, its own receipt (`decide-<kind>:<day>`), never inside the main decision. It starts at a clock time
  (`start`) or on the finish of the slots it names (`after`: the main receipt finished `ok` or `pending`; any other
  slot's receipt finished, whatever its status), never before `not_before` and NEVER PAST `never_past`. A slot that
  starts before the main decision of its auction is bounded by the House to end `DECISION_MARGIN` (5 s) before it
  (house.py `_deadline`: a slot task is not a "decide-" task), so it cannot delay the main rows; `scheduler.check`
  refuses a table in which such a slot's `never_past + bound` reaches that margin. A slot after the main decision
  cannot cut the main rows: they are decided and their receipt finished before it starts.
- **In the same turn.** A due slot runs in the turn that made the main decision's receipt (or whose task returned at
  the slot's clock start), never at the next House publish (house.py `run`: the turn goes on into a due slot as it
  goes on into the owed close decision).
- **Final at the auction, decided later by itself.** A live run that failed, was cut at its bound, or never started by
  `never_past` is FINAL for that auction: no retry. A window that closed with no run gets a `missed` receipt and a
  House warning (`decision slot <file> <auction>`: the alarm; the health page's `slots` and `timing_table` show it).
  The file's rows of that auction are then decided by the CATCH-UP (`decide-<catchup>:<day>`, after the record pass,
  oldest first, once each, shadow only). The book plans a file's buys only from a live receipt `ok` or `pending`.
- **The book's per-file send windows.** The main pass (`_event_decide`) plans and sends the main rows exactly as
  today. Each file with a registered part gets its own pass (`_event_decide_slot`, the row `(day, "<at>-<file>")` of
  `eq_event_decisions`), made once the main pass is done and the file's live receipt is made, inside the file's own
  window: its picks from `book.picks`, every name given at the auction already passed over, the room left, planned as
  buys sent after every main row in ROOM's order and ONLY inside `[send_from, send_until)` (`_event_send`). A file's
  buy never keeps room from a main row (`HeldAhead` is the main pass's, unchanged); a receipt final without being made,
  or a window that closed first, decides the file with no buy and says why.
- **Pre-passes.** A row with `prepass` True is a file's reads ahead of its decision on data knowable then, run as the
  plan's last task inside `[start, never_past]`, bounded to end before any decision, its receipt its kind itself
  (`prepass-meta:open:<day>`), no intent, no send window, no catch-up; one cut at its bound goes on from what it
  stored, one not done by `never_past` is simply not done.

## The interface (what a branch adds: a row and a `register` call)

```python
from league.events import scheduler as X

X.TABLE["close"] = X.TABLE["close"] + (
    X.Slot("evl7", "close", 120.0, "close-lrnlive", after=("main",), never_past=X.Wall("close", -630),
           send_from=X.Wall("close", -780), send_until=X.Wall("close", -660), catchup="close-lrn"),)
X.register(X.Part("evl7", run=live_part, catchup=catchup_part, programs=lambda: [p.id for p in P.learners()],
                  since=lambda: REGISTERED_AT_7_as_datetime))
```

- `Part.run(ctx, day, auction, slot, rid)`: the LIVE part. `ctx` is the lane's `LaneContext` (`ctx.store`, `ctx.gw`
  bounded and cut at the slot's bound, `ctx.sec`, `ctx.now()`, `ctx.deadline` on `ctx.mono()`'s clock: the slot's
  own bound from its own start). It returns the receipt's summary: it must NAME the file's programs the way the
  file's judge reads them (screen.py `names`), and may return `_status: "pending"` (its own verdicts). Its writes
  are its own one transaction. Raising `league.events.run.Deadline` (or the gateway's `LaneDeadline`) ends the run
  `cut`; any other exception `failed`; both final for the auction (a warning, the catch-up later).
- `Part.catchup(ctx, day, auction, slot, rid)`: the file's rows of that auction decided BY THEMSELVES, exactly as of
  the auction's decision time from stored times, shadow only. None: no catch-up.
- `Part.programs()`: the ids the file decides; `book.slot_of(program)` reads it, so the main pass keeps them out and
  the file's pass takes them. `Part.since()`: the file's registration time (None: nothing of it runs yet).
- `Part.prepass(ctx, day, auction, slot, rid)`: the pre-pass of a `prepass` row.
- Receipt kinds are the row's: the frozen texts' names fit (`decide-open-lrnlive:<D>` / `decide-open-lrn:<D>`;
  `decide-open-px8:<D>` / `decide-px:open:<D>`; `decide-close-warm9:<D>` / `decide-close-warm9-late:<D>`). A file's
  judge reads its own kinds; the House's `decide-open:<D>` / `decide-close:<D>` never name a later file's program.
- Nothing else: no `part_until`, no `EVL5_FINISH`, no `EVENT_DECIDE_WAIT_S` wait, no `book.part_hold` for a file's
  rows. The catch-up is run by the House (`catchup-<auction>-<file>`), so `league.events.__main__ catchup` needs no
  change for it; a branch may add its own CLI entry.

### feat/evl-6

Nothing to adopt: PREREG-EVL-6's versions are rows of the main slot (the same families, the same decision), as
today.

### feat/evl-7 (PREREG-EVL-7 sections 1.7 and 1.11): NOT TAKEN on release 1019n-r2 (the section above)

Replace run.py's `learner_part` call after the receipt with two rows (open: after main, 90 s, never past 09:25:30,
sends 09:16-09:27, kinds `open-lrnlive` / `open-lrn`; close: after main (or after `meta8` when PREREG-EVL-8's row
is in: the order of the followers is the table's), 120 s, never past 15:49:30, sends 15:47-15:49, kinds
`close-lrnlive` / `close-lrn`) and one `register` (run = `learner.live_part` without `receipt_id` reads of the main
receipt: the slot's start IS the main receipt's finish, the E5 eligibility cut; catchup = the `decide-*-lrn`
decision; programs = `P.learners()`). The book's `_event_decide_lrn` and `EVENT_LRN_WAIT_S` are no longer needed:
the file's pass is the scheduler's. The text's claims hold: the part is not inside the House's decision, its bound
is 90 / 120 s from its own start, a failed or expired part writes nothing and is decided later by itself, the
House's receipts never name a learner, and a pick not sent by the cut-off is a 'window' row (the stated effect).

### feat/evl-8 (PREREG-EVL-8 section 4.6)

Rows: `prepass-meta:open` (09:00:00, never past 09:13:00, 60 s, a pre-pass), `px-am` (09:05:00, never past 15:30:00,
60 s, a pre-pass that goes on from what it stored: the morning pass), `open-px8` (after main, 60 s, never past
09:19:30, sends 09:16-09:27, catch-up `px:open`), `prepass-meta:close` (15:30:00, never past 15:43:00),
`close-px8` (a clock start at 15:46:00, never past 15:46:05, 50 s: the House bounds it to end by 15:46:55; its reads'
own timeouts make the gateway's overrun 0, as the text states), `close-meta8` (after main, 15 s, never past 15:48:40,
catch-up `meta:close`). The late passes of section 4.6 ARE the scheduler's per-file passes (the book's pass of the
file at the first tick inside its window at which its receipt is made, after every main row). The text's test (i)-(v)
holds: (i) `close-px8` ends by 15:46:55 whatever the gateway does and the main decision starts at 15:47:00 (the
simulation's `pre` slot); (ii) a record pass due inside a slot waits for it, and one started before ends
DECISION_MARGIN before the main decision; (iii) PREREG-EVL-5's pre-pass keeps its own place (unchanged); (iv) a
pre-pass is bounded to end before any decision; (v) with the lane's close receipt at 15:47:40 the file's buys are
planned at the 15:48 tick after every main row, and at 15:48:20 + 15 s a `close-meta8` receipt is made by 15:48:35
and its buys planned at the 15:49 tick... which is past the line: not planned (the window). THE TEXT'S "WHAT DOES
NOT ALWAYS FIT" is the table's worst-case line below, honestly.

### PREREG-EVL-9 (section 7.3)

Rows: `prepass-warm9:open` (09:01:00, never past 09:13:00, 120 s), `open-warm9` (after `px8`, 60 s, never past
09:20:30, catch-up `open-warm9-late`), `prepass-warm9:close` (15:33:00, never past 15:43:00, 120 s), `close-warm9`
(after `evl7`, 10 s, never past the close - 5 minutes, sends to 15:49:00, catch-up `close-warm9-late`). The warm
part makes no network read; the eligibility cut is the main receipt's finish.

## The rows the drafts imply, and their worst case

Computed by `scheduler.table_text` and `scheduler.worst_case` on the rows above (not pinned: each branch pins its own
rows; the main rows are the pinned table's). The lane runs one task at a time, so a follower's latest start is the
latest finish of the slot before it in time.

**The open auction** (times ET on a full day; an early close moves every close-side row with the session):

| file | starts | never past | bound | sends | receipt | catch-up | after |
|---|---|---|---|---|---|---|---|
| main | 09:15:00 | - | 150 s | 09:16:00-09:27:00 | `decide-open:<day>` | - | - |
| meta8-pre | 09:00:00 | 09:13:00 | 60 s | none (a pre-pass) | `prepass-meta:open:<day>` | - | - |
| px8am-pre | 09:05:00 | 15:30:00 | 60 s | none (a pre-pass) | `px-am:<day>` | - | - |
| warm9-pre | 09:01:00 | 09:13:00 | 120 s | none (a pre-pass) | `prepass-warm9:open:<day>` | - | - |
| evl7 | on main's receipt | 09:25:30 | 90 s | 09:16:00-09:27:00 | `decide-open-lrnlive:<day>` | `decide-open-lrn:<day>` | main |
| px8 | on main's receipt | 09:19:30 | 60 s | 09:16:00-09:27:00 | `decide-open-px8:<day>` | `decide-px:open:<day>` | main |
| warm9 | on px8's receipt | 09:20:30 | 60 s | 09:16:00-09:27:00 | `decide-open-warm9:<day>` | `decide-open-warm9-late:<day>` | px8 |

**The close auction**:

| file | starts | never past | bound | sends | receipt | catch-up | after |
|---|---|---|---|---|---|---|---|
| main | 15:47:00 | - | 150 s | 15:47:00-15:49:00 | `decide-close:<day>` | - | - |
| meta8-pre | 15:30:00 | 15:43:00 | 60 s | none (a pre-pass) | `prepass-meta:close:<day>` | - | - |
| warm9-pre | 15:33:00 | 15:43:00 | 120 s | none (a pre-pass) | `prepass-warm9:close:<day>` | - | - |
| px8 | 15:46:00 | 15:46:05 | 50 s | 15:47:00-15:49:00 | `decide-close-px8:<day>` | `decide-px:close:<day>` | - |
| meta8 | on main's receipt | 15:48:40 | 15 s | 15:47:00-15:49:00 | `decide-close-meta8:<day>` | `decide-meta:close:<day>` | main |
| evl7 | on meta8's receipt | 15:49:30 | 120 s | 15:47:00-15:49:00 | `decide-close-lrnlive:<day>` | `decide-close-lrn:<day>` | meta8 |
| warm9 | on evl7's receipt | 15:55:00 | 10 s | 15:47:00-15:49:00 | `decide-close-warm9:<day>` | `decide-close-warm9-late:<day>` | evl7 |

Every part at its bound, each read returning 0 s after it:

| auction | file | latest start | latest finish | its sends fit | missed |
|---|---|---|---|---|---|
| open | main | 09:15:00 | 09:17:30 | yes | no |
| open | evl7 | 09:17:30 | 09:19:00 | yes | no |
| open | px8 | 09:19:00 | 09:20:00 | yes | no |
| open | warm9 | 09:20:00 | 09:21:00 | yes | no |
| close | px8 | 15:46:00 | 15:46:50 | yes | no |
| close | main | 15:47:00 | 15:49:30 | no (line 15:49:00) | no |
| close | meta8 | 15:49:30 | 15:49:45 | no (line 15:49:00) | yes |
| close | evl7 | 15:49:45 | 15:51:45 | no (line 15:49:00) | yes |
| close | warm9 | 15:51:45 | 15:51:55 | no (line 15:49:00) | no |

Every part at its bound, each read returning 45 s after it (the gateway's timeout; `close-px8`'s own read timeouts
make its overrun 0, so the main decision's 15:47:35 start in this line is the model's bound, not its design):

| auction | file | latest start | latest finish | its sends fit | missed |
|---|---|---|---|---|---|
| open | main | 09:15:00 | 09:18:15 | yes | no |
| open | evl7 | 09:18:15 | 09:20:30 | yes | no |
| open | px8 | 09:20:30 | 09:22:15 | yes | yes |
| open | warm9 | 09:22:15 | 09:24:00 | yes | yes |
| close | px8 | 15:46:00 | 15:47:35 | yes | no |
| close | main | 15:47:35 | 15:50:50 | no (line 15:49:00) | no |
| close | meta8 | 15:50:50 | 15:51:50 | no (line 15:49:00) | yes |
| close | evl7 | 15:51:50 | 15:54:35 | no (line 15:49:00) | yes |
| close | warm9 | 15:54:35 | 15:55:30 | no (line 15:49:00) | no |

What this says, plainly: at the open everything fits at the worst bound, and only a 45 s gateway overrun on top of
every bound misses `px8` and `warm9` (their catch-ups decide them, shadow only). At the close the main decision at
its own full bound (150 s from 15:47:00) already ends after the 15:49:00 line, as it does today (the book decides at
15:48:03 on the store as it stands, and PREREG-EVL-5's rows wait by `part_hold`); every follower of the main receipt
can therefore miss its window on a bad day, and the scheduler's promise is not that they fit but that THEIR cost is
theirs alone: the main rows' decision, timing and picks never change for them, a late follower is missed with a
receipt and an alarm instead of cutting the rows behind it, and its rows are decided later by themselves. The
followers fit when the main decision takes its usual seconds, not its bound; the daily report's missed-slot counts
are the evidence of how often it does not. PREREG-EVL-7's and -8's texts already state these effects ('window'
rows; "what does not always fit"); the table makes them true by construction instead of by hope.

## What the scheduler never does

It moves no money row or constitution row (the identities stay `8e63ce64` / `c3026eba`), edits no judge
(screen.py, bands.py, programs.py are untouched; each file's judge reads its own receipt kinds), changes no main
decision time or send window (pinned to today's constants), keeps no room for a file's buy from a main row, and
never trades a file's rows at an auction whose live receipt is not `ok` or `pending`.
