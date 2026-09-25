# Forward first — September 25, 2026

Execution record for the owner's goal of Sept 25, 2026: execute
[the forward-first plan](../goals/LTCM_FORWARD_FIRST.md) autonomously, with no deadline, outside US
market hours, until its Done list holds. The Sept 25 gap review (memory note
`ltcm-gap-review-2026-09-25`) is the baseline.

## The clock

- **T0:** 2026-09-25T04:22:57Z (the session's first `date -u` after reading the plan).
- **No deadline.** The run ends when the plan's Done list holds. A context reset does not end it.
- **Progress notes:** a scoreboard reading and a short state note every four hours from T0
  (08:23Z, 12:23Z, 16:23Z, ... Sept 25), in "Progress notes" below.
- **US sessions:** Friday Sept 25 13:30-20:00Z (no deploy 13:25-20:05Z), then Monday Sept 28.
  The weekend has no stock or options session; Kalshi and Alpaca crypto trade throughout.

## The owner's message (Sept 25, 2026, at T0)

- The /goal text is the plan's last section with the funding and owner-step lines left as the
  template's placeholders. At 04:25Z the owner added: "you can ignore the things that require things
  from me like api keys. we can do those later i cant provide those now."
- **Read as:** no owner-stated funding figure, so "funded" means the balances read from the
  providers at T0 (below) and no cap is raised; no Sail top-up and no October `FRONTIER_MONTH_USD`
  this run; no Sail checkpoint ticket, no Odds API key, no EIA key. No notification is sent for them
  (the owner said so in the session); the exact commands are in the report.
- Authority: the plan's "Authorized" list and money-rule table (M1-M5, C8, H4), with a re-ratify of
  `earned-live-20260921` within a minute of each promotion that moves the digest (two digest
  changes, a third only for a money-path defect found in the watch). Nothing in "Not authorized".

## The first hour's decisions

1. **The deploy path (04:08-04:22Z).** H1 had already run before this session started: release
   `20260925T040816Z-532b1cd9b20c` was sent from `~/Work/ltcm-deploy` at `origin/main` `3defc0d`
   (#294) with the loop stopped (`watch_seconds 0`, canary 3 ticks), promoted at 04:09:55.8Z,
   `ops.started` at 04:11:49Z. It ships #289 (backup backoff, `began_at`), #292 and Merton's #288,
   #290, #291, #293, #294. The previous release `main-849c905c7146` (the updater's, 01:14Z) was
   rolled back at 01:17:55Z on the backup 503 ("prewarm base snapshot ... DeadlineExceeded").
   Still to verify: the backup alert's cadence (30 min doubling), and the updater's next release
   (this plan's merge, #295) not rolled back.
2. **Real books (04:21Z).** None frozen. The real Alpaca book failed to reconcile every ~5 minutes
   from at least 03:35Z to 04:03:42Z on `cash_diff` 0.01075037 (expected 465.61688803, venue
   465.627638403755211532, `dust_booked` 0), one error alert per failure; since the restart at
   04:11:49Z it reconciles. H4 still ships in Deploy A: the difference is unexplained by the book
   and will recur on the next venue fee activity.
3. **Ratify (04:26Z).** `ratify.py earned-live-20260921` (the no-restart wrapper around
   `league.live_trading --ratify`) returned `active True`, digest `535a7f15`, and wrote nothing
   (the policy is unchanged). This session can ratify: Deploys A and B may move the digest.
4. **Compute truth (04:25Z, `scripts/gateway_admin.py status`).** OpenAI gateway month $523.74 of
   $607.00 (settled $517.98, in flight $5.76); the House's OpenAI line $83.24; Sail $152.35 at about
   $16.17 a day (9.4 days); Jev $16.22 of $42.00. The gateway's profit index: equity $1,025.47
   (Kalshi $542.78, Alpaca $482.69), profit $7.72 above the $1,017.75 baseline. Kill switch off.
5. **The money set.** Deploy A carries H4's constitution key `allocator.real_book_dust_usd`
   (digest change 1 of 2). Deploy B carries M1-M5 and C8 (digest change 2 of 2).
6. **File owners, Wave 0:** H2 `league/watchdog.py`, `league/backup.py` (and the backup call and
   graceful shutdown in `house.py`, minimal); H3 `league/updater.py`; H4 `league/book.py`,
   `league/constitution.py`; H5/H6 `league/house.py` (the tick). Z `scripts/gap_scoreboard.py`.

## Checklist

| # | Item | State |
|---|---|---|
| 0.1 | T0 recorded and committed | done |
| 0.2 | Plan merged to main (#295) | done 04:31:43Z (`2470d26`) |
| 0.3 | First-hour decisions | done 04:28Z (above) |
| 0.4 | The scoreboard at T0 | snapshot taken 04:23-04:26Z (`--take`); the plan's seven rows from Z |
| H1 | Ship the stuck head | promoted 04:09:55Z (not by this session); Sail's checkpoints recovered at 01:55:04Z, so the backup alert is quiet until the next failure; the updater's next CODE release is the last check |
| B | `kalshi-open` offered markets with no intent | not a defect (05:00Z, below) |

## Findings before Wave 0 reports

- **Sail's checkpoint service recovered at 01:55:04Z Sept 25** (a successful backup after 73 failures since
  21:31:55Z Sept 24). The owner step "a Sail checkpoint ticket" is moot; H2 still ships (the next vendor outage
  must not roll a release back).
- **A docs-only merge to main is not a release.** The updater's 04:44Z check of `2470d26` (#295, the plan) wrote
  no row: a release tree holds `league/`, `ltcm/`, `scripts/`, `playbooks/` and `deploy/` only, so its digest
  equals the running one ("the box already runs main"). The Sept 25 memory note said the opposite; run-record
  merges restart nothing.
- **`kalshi-open` (the plan's bug list):** 2 living members; greenwich-h4cb387 woke 22 times in the 6 h to 04:23Z
  and made 3 intents; its thought each time is its program's screen ("Screen low-priced YES football outcomes and
  place bounded post-only NO bids; at most one position per event"), which rarely fires. Not a defect. The desk's
  gap is seats: 2 of 8 held, 4 waiters over 2 h, refused because the league's 128 seats are held (F3's case).

## Progress notes

## Watch log

## Report
