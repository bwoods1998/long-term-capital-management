"""THE PANEL KIND'S SLOT (release E1, the captain's amendment A13): the package a later release's cross-sectional
(panel) lane is built in. Nothing runs here yet.

Why it exists now. The decider's kind table (league/equity/kinds.py `KINDS`) names "panel" -> `league.xs.child`, and
the child's sealed runtime carries this directory (`RUNTIME` "league/xs/"), so the panel's store, ctx, program, engine
and screen can land as modules of THIS package: not in league/equity, whose evidence modules are the equity identity
(`league.swarm.evaluator.EQUITY_EVIDENCE`; a change there sends every live equity band back to the Gym), and not in
league/live, whose every file is the options execution fingerprint. Until then `child.handle` refuses every op.

A module of this package imports nothing of league.live and nothing of league.swarm (league/tests/
test_equity_isolation.py holds it), and league/live never names it (the decider reaches it through the kind table).
"""

__all__: list[str] = []
