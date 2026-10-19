"""The event lane (EVL): long-only whole-share trades in US common stocks on public events, the goal of Oct 19, 2026.

The rules are PREREG-EVL-1 (docs/prereg/PREREG-EVL-1.md, pinned by its commit before the first counted event); this
package builds them and never changes them. Events are SEC EDGAR filings (8-K, Form 4) and Alpaca news headlines.
Every pre-registered program is shadow-traded on every qualifying event from its registration time; real money waits
for the screen (league.events.screen). Model verdicts (Claude Haiku 4.5 through the gateway) are stored once and read
back by every replay, so a replay is exact.

Standard library only, like the rest of the league. Modules: store (events.sqlite and the document store), calendar
(sessions, Eastern time), edgar (filings), news, universe, verdicts, programs, score, screen, report; the CLI is
`python -m league.events <command> --state DIR`.
"""
