"""The event lane (EVL): long-only whole-share trades in US common stocks on public events, the goal of Oct 19, 2026.

The rules are PREREG-EVL-1 (docs/prereg/PREREG-EVL-1.md, pinned by its commit before the first counted event); this
package builds them and never changes them. Events are SEC EDGAR filings (8-K, Form 4) and Alpaca news headlines.
Every pre-registered program is shadow-traded on every qualifying event from its registration time; real money waits
for the screen (league.events.screen). Model verdicts (Claude Haiku 4.5 through the gateway) are stored once and read
back by every replay, so a replay is exact.

Standard library only, like the rest of the league. Modules: store (events.sqlite and the document store), calendar
(sessions, Eastern time), edgar (filings), news, universe, verdicts, programs, score, screen, report; the CLI is
`python -m league.events <command> --state DIR`.

THE EVENT LANE'S RECEIPTS, the House's contract with the lane (release R1: the stall job's four causes,
league/ops/evl_health.py, read them read-only from `<state>/events/events.sqlite` `receipts`; a pass that writes them
differently goes unjudged or stands as stalled):
- `record` (run.record_pass): one a pass, `ok` when it finished (its `news.error`, when the news read failed);
- `decide-open:<day>` and `decide-close:<day>` (run.decide_open, run.decide_close): one a decision run, `ok`, or
  `pending` while a reading program waits for a verdict; the summary carries `verdicts: {needed, answered}`, the
  distinct (event, prompt) verdicts the decision's reading programs need and how many have a stored answer (a
  close-entry reading program tallies its own the same way);
- `score` (score.settle): one a pass, `ok` unless every due intent failed (`failed`), counts only.
The daily report the stall job mails is report.build's, read through a read-only store.
"""
