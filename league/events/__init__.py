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
"""
