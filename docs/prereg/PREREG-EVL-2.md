# PREREG-EVL-2: the event lane's second wave of programs

Pre-registered by the LTCM captain (Claude Opus 5.5, session 6f078599) under the owner's goal of Oct 19, 2026
(`goal-2026-10-19/GOAL-MESSAGE.txt`), after the owner asked for maximum urgency (01:50Z Oct 19). Written 03:30-04:10Z
Mon Oct 19, 2026, before any event of Mon Oct 19 was read and before any outcome (a price after an event) of any event
was looked at by the captain or any agent: the lane's store holds filings, Form 4 transactions and session calendars,
and no bar, mark or outcome.

REGISTRATION TIME: the later of this file's commit time and GitHub's receipt of the push of the tag `prereg-evl-2`
(read from the GitHub API and recorded in amendment A63); the tag never moves. An event counts for a program of this
file only if its knowable time is after THIS registration time (not PREREG-EVL-1's). Nothing here changes for a
registered program: a change is a new program version with its own registration time.

## 1. What this file adds, and what it takes from PREREG-EVL-1

Nine new programs over the lane of PREREG-EVL-1 (frozen 2026-10-19T01:08:38Z, `docs/prereg/PREREG-EVL-1.md`, which
this file never edits): five seatable, three records, one control. Everything this file does not restate is PREREG-EVL-1's,
word for word: the universe (section 2), the events and their knowable times, backfill and the shadow rule (section 3),
the verdicts and their prompts, model and parsing (section 4), the execution model, auction prices, fallback exits,
costs, per-event and abnormal returns and TRADABLE (section 5), the one-position-per-issuer rule (section 5), THE
SCREEN with its looks, sign-flip test, skew check, issuer-block test and beat-the-control rule (section 7: the judge
is the same for every program of either file), real money, sizing and demotion (section 8), and Done, Kill and
reporting (section 9). No new prompt: every verdict here is a PROMPT-DOC or PROMPT-NEWS verdict, asked and stored as
PREREG-EVL-1 section 4 says, and a verdict already stored for an event is the verdict of every program that reads it.

## 2. New windows, rules and exits

- T29 of a session: the start of its regular-session SIP 1-minute bar 31 minutes before its close (15:29:00 ET on a
  full day, 12:29:00 ET on a 13:00 close).
- THE DAY-NEWS WINDOW of session D: ENEWS articles with exactly one symbol, that symbol the eligible ticker of its
  issuer on D, whose knowable time is after 09:00 ET of D and at or before T29 of D; the non-live exclusion of
  PREREG-EVL-1 section 3 applies. (The pre-market window of EVL-NEWS-READ-O1 ends at 09:00 ET; the two never share an
  article.)
- THE REACTION of an event with day 0 = D: the close of the regular-session SIP 1-minute bar starting at T29 of D (if
  that minute has no trade, the last earlier regular-session minute bar of D) over the raw SIP daily close of the last
  session that closed before the event's knowable time; no reaction when either price is missing (the event is not
  taken). For 8-K events this is exactly EVL-ERN-REACT-C1's rule and day 0 (PREREG-EVL-1 section 6); for day-news
  events day 0 is D. The bar ends 16 minutes before the close decision, so real money reads it from SIP history on
  Alpaca's Basic plan.
- EXIT AT THE OPEN of a session: the OPEN auction price of PREREG-EVL-1 section 5 (the listing exchange's `O` print,
  else its `Q` record). With no such print on the exit day the position exits by PREREG-EVL-1 section 5's ladder,
  unchanged: the next session's closing cross, with none within 5 sessions the first SIP trade of the next session on
  any venue, and 0 after 20 sessions. A program that enters at the CLOSE of D and exits at the OPEN of the next
  session holds one session in the screen's sense: its block is D, its first settled exit is session 1, and its
  blocks never overlap (the exit auction of D's positions comes before the entry auction of the next session's).
- THE LIMIT AT ENTRY (this file's programs, shadow and real alike): an event whose entry auction price is above 1.25 x
  the raw SIP close of the session before the entry session is not filled and is skipped (PREREG-EVL-1 section 8's
  real-money limit), so the shadow never counts a fill real money could not get.
- THE INSIDER BUY of a Form 4 filing F (EF4, form type exactly `4`): F reports at least one reporting owner who is a
  director or an officer of the issuer, and the sum over F's non-derivative transactions with code `P` and
  acquired/disposed `A`, transaction date within the 10 calendar days ending on F's acceptance date (Eastern), each
  transaction counted once however many owners share it, of shares x price (a transaction with no price counts 0), is
  >= $50,000. That sum is F's PURCHASE VALUE.

## 3. The programs

Seatable (may earn real money after a screen pass); each holds 1 session:

| id | event | rule | entry | exit |
|---|---|---|---|---|
| EVL-ERN-REACT-ON | the EVL-ERN-REACT-C1 events (E8K with item 2.02, day 0 as C1's) | reaction >= 1.04 (no model) | CLOSE of day 0 | OPEN of the next session |
| EVL-ERN-GUIDE-O1 | the EVL-ERN-READ-O1 events | PROMPT-DOC verdict `ok` with guidance exactly "raised" and score >= 1 | OPEN as for O1 | CLOSE of session 1 |
| EVL-INS-BUY-O1 | EF4 filings with an insider buy (section 2) | no model; one event per issuer per entry session, the earliest knowable | OPEN of the first session whose 09:00 ET is after the knowable time | CLOSE of session 1 |
| EVL-NEWS-READ-ON | day-news articles of D | PROMPT-NEWS score >= 2; one event per issuer per D (the highest score, then the earliest) | CLOSE of D | OPEN of the next session |
| EVL-NEWS-REACT-ON | day-news articles of D | reaction >= 1.04 (no model); one event per issuer per D, the earliest | CLOSE of D | OPEN of the next session |

Records (shadow only, never seated; reported beside):
- EVL-INS-BUY-O5: the INS-BUY-O1 events, exit at the CLOSE of session 5 (overlapping holds).
- EVL-ERN-REACT-READ-C1: the EVL-ERN-REACT-C1 events and rule that also have a stored PROMPT-DOC score >= 2; entry and
  exit as C1.
- EVL-ERN-READ3-O1: the EVL-ERN-READ-O1 events with score exactly 3; entry and exit as O1.

Control (it measures what the verdicts add to EVL-NEWS-READ-ON): EVL-CTRL-NEWS-DAY-ON, every EVL-NEWS-READ-ON event
before its score rule, one per issuer per D by the same order, entry and exit as NEWS-READ-ON. EVL-ERN-GUIDE-O1's
control is EVL-CTRL-ERN-ALL-O1 of PREREG-EVL-1 (the same events, entry and exit), compared over the same sessions.

RANKING when more events qualify than room (PREREG-EVL-1 section 8): REACT programs by reaction, higher first, then
ADV; GUIDE and NEWS-READ by verdict score, then ADV; INS-BUY by purchase value, then ADV. When two programs want the
same name at one auction, the rows of PREREG-EVL-1 section 6 go first, then this file's rows in the order above.

## 4. Why these five (the captain's prior, stated before any outcome)

- ERN-REACT-ON and NEWS-REACT-ON: stocks with a large, attention-drawing move on public news tend to earn positive
  close-to-open returns that reverse during the next day (the overnight-attention effect; Berkman, Koch, Tuttle and
  Zhang 2012; Aboody, Even-Tov, Lehavy and Trueman 2018). The exit at the next open keeps the overnight leg and skips the
  intraday reversal that EVL-ERN-REACT-C1's close-to-close hold carries.
- ERN-GUIDE-O1: raised guidance is news about future earnings, beyond the quarter just reported, that a reader can
  pick out of the release text; the field is in every stored PROMPT-DOC verdict, so the program costs no new verdict.
- INS-BUY-O1: open-market purchases by directors and officers carry abnormal returns concentrated in the days after the
  filing (Lakonishok and Lee 2001; Cohen, Malloy and Pomorski 2012); no model, so no verdict cost; far more events than
  the two-insider cluster record of PREREG-EVL-1.
- NEWS-READ-ON: the overnight leg after the day's single-stock news, chosen by the reading; it is the one new program
  that asks new verdicts (about 300-600 PROMPT-NEWS calls a session, roughly $0.30-$0.60 a day at Haiku 4.5's prices).

## 5. False passes and power

- Each program here faces PREREG-EVL-1 section 7's screen unchanged, whose measured false-positive rate for a
  zero-edge one-session program is 8.3-10.3% (at most 10.3% in the reviewer's crash-tail case), under the goal's 15%.
  The issuer-block and beat-the-control conditions can only lower it. The overnight holds and the insider events are
  the case those measurements simulated (one-session blocks, a per-session common shock, fat tails and a crash tail);
  at 2 events a session the measured rate was 5.6%.
- EXPECTED FALSE PASSES: 0.10 x every seatable version ever registered = 0.10 x (4 + 5) = 0.9 over both files. If
  every one of the nine had zero edge, the chance of at least one false pass is about 1 - 0.9^9 = 61%. The cost of a
  false pass is bounded by PREREG-EVL-1 section 8: Probe positions of 5% of equity, at most 6 open, the -$150 per 20
  sessions demotion, retirement after 100 settled real-money events with a negative mean, and the lane's $400 / $800
  loss budget; and Done (section 9) asks a 95% lower bound above zero over >= 300 real events, which a zero-edge
  program drags down.
- POWER: as PREREG-EVL-1 section 7 (an edge of 0.4% an event at 40 events a session passes about 93% of the time,
  median session 20). Expected event rates, before any was counted: ERN-REACT-ON the C1 rate (in earnings season, tens
  a session); ERN-GUIDE-O1 a share of O1's; INS-BUY-O1 roughly 5-15 a session; the day-news programs tens a session.

## 6. Implementation (after this file, to these rules)

`league/events/programs.py` gains these nine rows, each with this file's registration time, an exit kind (`open` or
`close`), the day-news window, the insider-buy trigger and the ranking above; `league/events/run.py` decides every
close-entry program at the close decision and every open-entry program at the open decision; `league/events/score.py`
already settles an exit at the open by the section 5 ladder. Every decision of these programs from the registration
time on is made by the shadow rule of PREREG-EVL-1 section 3, including the backfill of events knowable before the
code ships. If an implementation finds a rule here ambiguous, it takes the reading LESS LIKELY TO PASS (for screen
rules) or that trades less (for trading rules), fixed before the program's first settled event and recorded as an
amendment; a later resolution is a new version.
