"""The event lane (EVL): long-only whole-share trades in US common stocks on public events, the goal of Oct 19, 2026.

The rules are PREREG-EVL-1 to PREREG-EVL-4 (docs/prereg/, each pinned by its commit and tag before its first counted
event); this package builds them and never changes them. Events are SEC EDGAR filings (8-K, Form 4) and Alpaca news
headlines. Every pre-registered program is shadow-traded on every qualifying event from its own registration time; the
versions that may seat (version 2 of PREREG-EVL-1's and -2's seatable programs, version 1 of PREREG-EVL-4's) trade real
money at the learning band from their first event and move between bands by the screen's event-counted looks
(league.events.screen, league.events.bands). Model verdicts (Claude Haiku 4.5 through the gateway) are stored once and
read back by every replay, so a replay is exact.

Standard library only, like the rest of the league. Modules: store (events.sqlite and the document store), calendar
(sessions, Eastern time), edgar (filings), news, universe, verdicts, programs, score, screen, report; the CLI is
`python -m league.events <command> --state DIR`.

THE EVENT LANE'S RECEIPTS, the House's contract with the lane (release 1019c). The stall job's event-lane causes
(league/ops/evl_health.py) read them read-only from `<state>/events/events.sqlite` `receipts` and judge what a pass DID,
never its status alone (a pass that says `ok` and read nothing is no progress). Every writer keeps to this:
- `record` (house.py `_record`): one a record pass, `ok` when it ran to its end (a bound reached mid-fetch included),
  `failed` when it raised. Its summary holds one block per read: `"8-K"` and `"4"` (EDGAR's current feeds: `new`,
  `fetched`, `failed`, `unlisted`, `waiting`) and `"news"` (Alpaca's: news.record's counts, or `{"cut": true}` at its
  bound), each with `"error": "<why>"` when that read failed, and `"tickers": {"error": ...}` when no tickers copy could
  be read (no 8-K can be fetched then). A CLEAN pass finished `ok` with the three blocks, none in error, no EDGAR feed
  whose every fetch failed and no tickers error: `evl_record` stands when none finished in 30 minutes, naming the feeds.
  The screen's fast path (league/events/screen.py, A69 (i) as A84 reads it) reads the same blocks FEED BY FEED: a pass
  whose read of a feed errored, was cut (the news) or had no tickers copy (the 8-Ks) is a missing read of that feed, and
  each feed's clean reads must be at most 15 minutes apart across a close's span; `evl_final` reads the horizon that
  gives (`screen.final_until`), never a receipt of its own.
- `decide-open:<day>` and `decide-close:<day>` (run.decide_open, run.decide_close; none under `ask_only`): one a
  decision run, `ok`, `pending` while a reading program waits for a verdict, `cut` (the House's bound) or `failed`. The
  summary carries `verdicts: {needed, answered}`, the distinct (event, prompt) verdicts the decision's reading programs
  need, open-entry and close-entry alike, and how many have a stored answer (also returned under `ask_only`); and
  `kept` (release 1019c, run._scope: the programs the run left as they were, a written look of their group standing
  over the session, each with why and the events left out of its record, `events` and `unjudged`), which
  league/events/report.py `kept_out` counts. A kept program is asked no verdict, so its events are not in the tally.
  `evl_decide` counts a decision made when a receipt that started within 10 minutes of its time finished `ok` or
  `pending`; `evl_verdicts` reads the latest receipt's tally (a receipt from before it, its `pending` counts). A close
  decision's summary also carries PREREG-EVL-5's `evl5` (its funnels), or `evl5_error` when its part failed or ran past
  its own bound (its rows then named nowhere in it); `decide-close-evl4:<day>` and `decide-close-evl5:<day>` are those
  files' rows decided by themselves (run.decide_close with `evl4_only` / `evl5_only`), and meta `evl5:pre:<day>` is the
  session's PREREG-EVL-5 pre-pass (no receipt).
- `score` (house.py `_score`): one a nightly pass, bounded and resumable: `ok` once every intent due that night was
  tried, `partial` before; `evl_score` judges the intents themselves (still `planned` or `entered` after 23:00 ET), never
  the receipt.
- `verdicts` (a task that asked: its call counts), `universe`, `equity`, `screen`, `report`, `tickers`, `backfill`: the
  House's record of each task. The `report` receipt ({day}) is what the stall job's daily mail waits for.
"""
