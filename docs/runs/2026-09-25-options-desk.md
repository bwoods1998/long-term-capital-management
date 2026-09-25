# The options desk — September 25, 2026

Execution record for the owner's goal of Sept 25, 2026: execute
[the options-desk plan](../goals/LTCM_OPTIONS_DESK.md) autonomously, with no deadline, beside the
forward-first run ([its record](2026-09-25-forward-first.md) on `run/forward-first-2026-09-25`),
until its Done list holds.

## The clock

- **T0:** 2026-09-25T05:50:40Z (the session's first `date -u` after reading the plan).
- **No deadline.** The run ends when the plan's Done list holds. A context reset does not end it.
- **Windows:** Wave 1 (V, spreads on practice) deploys between 10:00Z and 12:25Z Sept 25, after the
  forward-first run's Deploy A and its watch. Friday's session 13:30-20:00Z is watched every 30
  minutes with no deploy. Wave 2 (G, real spreads switched off) deploys after 20:05Z Friday, after the
  forward-first run's Deploy B. The first real spreads, if a family meets O4: Monday Sept 28 13:30Z.

## The owner's message (Sept 25, 2026, 05:47Z)

- The /goal text is the plan's last section; the session received it cut at the start ("section
  says: ..."), so the plan's own copy of the message is the one followed.
- **Read as:** the owner's grant of the gateway's multi-leg route for debit verticals, and of real
  debit verticals once O4's line is met, is specific to this run and takes precedence over the
  forward-first plan's general "multi-leg option orders on either account" line, which this run's
  plan inherits otherwise. Everything else in both "Not authorized" lists holds: no credit spread,
  no naked short, no legging, no multi-leg order on the shared practice account, no test order, no
  cap raise, no owner step.

## Coordination with the forward-first run

Read before every merge and deploy: the forward-first record's "Coordination with the options-desk
run" section (its current wave, file owners and announced deploys).

**This run's current wave, file owners and deploys (kept current):**

| Wave | State | Files owned |
|---|---|---|
| 1 (V, the practice deploy) | building | new: `league/verticals.py`, `league/options_shadow.py`, spread founders under `league/strategies/`, their tests; `league/options_replay.py`; `league/service.py` (the options-shadow broker beside kalshi-shadow); `league/house.py` `_chain` and new options hooks outside the forward-first run's listed regions (the spread intent at wake, a spread agent's practice book, the pre-expiry spread close); the `alpaca-options` row of `league/niches.json`; `league/CONTRACT.md` "Options" |
| 2 (G, real spreads off) | not started | `gateway/lib/caps.mjs`, `gateway/lib/router.mjs`, `gateway/test/`; `league/book.py` (the real book's spreads); `ltcm/adapters/alpaca.py` (mleg submit and fills); `league/allocator.py` and `league/constitution.py` (O1-O5), only after the forward-first run's Wave 1 has merged |

- **Announced deploys:** Deploy V (practice; no money-digest change expected) between 10:00Z and
  12:25Z Sept 25, never within 30 minutes of the forward-first run's Deploy A; its exact start is
  written here first. Deploy G (the gateway's multi-leg route and the book's spreads, switch off;
  money-digest change 1 of 2) after the forward-first run's Deploy B, not before 20:05Z Sept 25.

## Checklist

| # | Item | State |
|---|---|---|
| 0.1 | T0 recorded and committed | done |
| 0.2 | Plan merged to main | PR #299 |

## Progress notes

## Watch log

## Report
