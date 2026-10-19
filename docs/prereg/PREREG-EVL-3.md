# PREREG-EVL-3: version 2 of the nine seatable programs, real money at learning size from the first event

Pre-registered by the LTCM captain (Claude Opus 5.5, session 6f078599) under the owner's goal as he re-set it at
05:15Z Mon Oct 19, 2026 (`goal-2026-10-19/GOAL-MESSAGE-V2.txt`): "Every seatable program trades REAL money at learning
size from its first event (whole shares, about 2% of equity a position, never above 5%) with a full-size shadow beside
it. Promotion to Probe and Sized, demotion and retirement are pre-registered sequential tests counted in settled
events, never days, at a false-positive rate <= 15% by issuer-block permutation." Written 05:16-05:22Z Mon Oct 19,
before any event of Mon Oct 19 was read and before any outcome (a price after an event) of any event was looked at by
the captain or any agent: the lane's store held no bar, mark or outcome.

REGISTRATION TIME: the later of this file's commit time and GitHub's receipt of the push of the tag `prereg-evl-3`
(recorded in amendment A64); the tag never moves. A program of this file counts only events knowable after THIS
registration time. Nothing here changes for a registered program: a change is a new version.

## 1. The programs

Version 2 of each seatable program of PREREG-EVL-1 (EVL-ERN-READ-O1, EVL-ERN-REACT-C1, EVL-8K-READ-O1,
EVL-NEWS-READ-O1) and of PREREG-EVL-2 (EVL-ERN-REACT-ON, EVL-ERN-GUIDE-O1, EVL-INS-BUY-O1, EVL-NEWS-READ-ON,
EVL-NEWS-REACT-ON). Each version 2 takes its version 1's events, rule, verdicts, entry, exit, ranking, costs, TRADABLE
and per-event returns word for word, with PREREG-EVL-2's LIMIT AT ENTRY for all nine (an entry auction above 1.25 x the
previous SIP close is not filled, shadow and real alike), and differs only in its bands (section 2) and its looks
(section 3). Version 1 of each stays what its file says, a shadow record with its own screen reported beside, and
never trades: version 2 supersedes it for every seat. The records and controls of both files continue unchanged; a
version 2 READ program is compared with its version 1's control over its own block sessions.

## 2. Bands: real money from the first event

- LEARNING, the band at registration: every TRADABLE version 2 event that fits the walls is entered with real money.
  Target 2% of the account equity at the previous close; whole shares = floor(min(target, 10% of equity - the name's
  book-wide value) / limit), the limit 1.25 x the previous SIP close (PREREG-EVL-1 section 8's order types and
  prices); one share when that rounds to zero and one share at the limit is at most 5% of equity and fits every wall;
  otherwise skipped (the shadow keeps the event). At most 8 open learning positions per program. Real money starts at
  the first decision after the House release that carries this band is live and the auction paper proof's BUY stage
  has passed; until then version 2 is decided by the same rules in shadow only.
- PROBE: from the first decision after a passed look (section 3): PREREG-EVL-1 section 8 (target 5%, at most 6 open).
- SIZED: PREREG-EVL-1 section 8 unchanged (>= 150 settled real-money events at Probe size or above with the 80%
  session-block bootstrap lower bound of the per-event after-cost return above zero: target 10%, at most 8 open).
- ROOM: when more events qualify than room (the book at most 100% invested, the loss budget, the 10% name wall),
  Sized programs first, then Probe, then learning; within a band the program table order (PREREG-EVL-1's rows, then
  PREREG-EVL-2's); within a program its own ranking.
- DEMOTION to learning: a Probe or Sized program whose last 50 settled real-money events at Probe size or above lost
  more than $150 net, or whose last 100 such events have a negative mean after-cost return; it returns to Probe at its
  next passed look.
- RETIREMENT (no more real money; the shadow continues as a record; a new version is the only way back): at a held
  look (section 3) whose mean after-cost abnormal return a of the TRADABLE events is below zero and whose one-sided
  sign-flip p for a mean BELOW zero (the session-block test with every value's sign reversed) is at most 0.05.
- OPEN RISK for the loss budget: each open event position counts value x max(0.10, 1.65 x sigma x sqrt(h))
  (PREREG-EVL-1 section 8); until the release carrying it is live the House's 0.40 floor applies.

## 3. The screen: PREREG-EVL-1 section 7 with looks counted in events

- Everything of PREREG-EVL-1 section 7 holds for version 2 (the TRADABLE population, block values, the sign-flip p and
  its vectors with seed strings `{id}|v2|look{k}`, the skew check, the issuer-block test, mean a > 0, mean raw r > 0, a
  READ program beating its control) except the looks and the threshold:
- LOOKS: look k (k = 1..10) is computed at the first session close at which the program has at least N_k settled
  TRADABLE events, N = 60, 90, 135, 200, 300, 450, 675, 1000, 1500, 2250, AND at least 40 distinct issuers among them
  AND at least 8 session blocks (8 independent market sessions holding an event: the fewest at which a session-block
  sign-flip p can be small and honest, a count of independent units, not a waiting period). It covers every block
  whose scheduled exits are at or before that close. Looks happen in order, at most one at a session close; a look
  whose minimums are reached at the same close as an earlier look's is that look (it is not computed twice). No other
  look exists.
- THRESHOLD: the skew check starts from alpha = 0.018 a look (and only tightens it, PREREG-EVL-1 section 7).
- MEASURED FALSE-POSITIVE RATE (synthetic, `prereg/evl-3/calibrate_events.py`, seeded; the model of PREREG-EVL-1:
  per-session residual common shock t(4) at 0.4%, 3% an event t(4), event rates drawn per program): a zero-edge
  program passes any look 5.2% of the time at 1 event a session, 8.4% at 6, 7.5% at 40 and 5.0% at 150
  (`prereg/evl-3/calib_variants.py` with this schedule, seeds 11-13) (session-block test alone), under the goal's 15%;
  the issuer-block test, the skew check and the beat-the-control rule can only lower it.
- POWER (same model): an edge of 0.4% an event passes about 91% of the time at 40 events a session (median session 24)
  and 82% at 6 (median session 91); 0.8% about 99.8% at 40 (median session 10) and 98% at 6 (median session 35); 0.2%
  about 44% at 40. The issuer-block test, the skew check, the beat-the-control rule and the TRADABLE count lower these
  and are not measured.

## 4. Expected false passes and what learning costs

- 0.10 x every version that can seat: the nine version 2 programs, 0.9 (version 1 never seats).
- Learning money at zero edge costs the round-trip cost, about 11-21 bp of a position plus about $0.02 of fees: at
  about $38 a position and 40 positions a session, about $3-4 a session, inside the walls. A program that loses is
  retired by section 2's rule; the loss budget stops every new entry before it is crossed.

## 5. Done, pivot and reporting (the owner's goal, restated so the reader is pinned)

- Done is read at every 100th settled real-money event at Probe size or above: >= 300 such events, all after their
  program's promotion, from >= 3 programs with >= 50 each; realized after-fee P&L positive; the 95% issuer-block
  bootstrap lower bound of the per-event after-cost return above zero (10,000 resamples, seed fixed); realized profit
  since the first promotion >= metered compute over the same span; real fills within 15 bp of the shadow auction prices
  (signed mean, per side); the last 100 of those events with no captain step. Learning events are reported beside and
  never counted.
- PIVOT: a lane whose 95% upper bound of the per-event after-cost return is below zero at 400 such events is retired
  and its budget moves to the next lane; when the $800 loss budget is spent, all spend stops and is reported.
- Every report: account-shown profit first, Net after metered costs beside, by program and band; the market-direction
  share; same-risk buy-and-hold; the expected false passes.

## 6. What is not decided here

The House code that carries the bands, the gateway's event-buy branch, the site and the docs, built after this file
to these rules. If an implementation finds a rule here ambiguous, it takes the reading LESS LIKELY TO PASS (screen
rules) or that trades less (trading rules), fixed before the program's first settled event and recorded as an
amendment; a later resolution is a new version.
