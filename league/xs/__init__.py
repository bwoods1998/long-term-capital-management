"""THE PANEL LANE (release E4, "breadth"): cross-sectional programs on the point-in-time S&P 500, judged by screen XS1.

A panel program picks 5 to 12 names out of the day's index members by a symmetric cross-sectional rule (reversal,
momentum, industry momentum, low volatility, rotation). It sees salted slots: no ticker, no date, no price level. It
is judged on its daily RESIDUAL (its P&L after costs minus the cost-free P&L of the cells its names were picked from)
against matched placebo portfolios, by the pre-registered screen XS1 (`league/xs/screen.py`; the rule is the pinned
pre-registration XSCREEN-1, its thresholds the receipt docs/benchmarks/equity_screen_xs_1.json: no pinned receipt, no
look).

Why this package (the captain's A13). The decider's kind table (league/equity/kinds.py `KINDS`) names "panel" ->
`league.xs.child`, and the child's sealed runtime carries this directory (`RUNTIME` "league/xs/"), so the panel's
store, ctx, program, engine and screen are modules of THIS package: not of league/equity, whose evidence modules are
the equity identity (`league.swarm.evaluator.EQUITY_EVIDENCE`; a change there sends every live equity band back to the
Gym), and not of league/live, whose every file is the options execution fingerprint. The panel has its own identity
(`league/xs/identity.py` `xs_fingerprint`); nothing here enters league/equity's evidence import closure.

A module of this package imports nothing of league.live, league.swarm or league.ops (league/tests/
test_equity_isolation.py holds the first two; `test_xs_identity.py` the list), and league/live never names it (the
decider reaches it through the kind table). The package stays FLAT: the decider child's runtime copies
`league/xs/*.py` only.

The build's contract between its packages is `league/xs/E4_INTERFACES.md` (every module, its owner, the shared
shapes, and where the pinned pre-registration overrides the spec). The pieces:

- `config`    the lane's constants (spans, the contract's limits, the strata, the dither) and its quiet windows;
- `store`     the panel store (members, bars, the House salt) and what a run is sent of it (`PanelBars`);
- `ctx`       what a panel program sees at a decision close, built by one function in the Gym and live (I6);
- `program`   loading a panel program (XS.md: NEEDS, PARAMS, decide(ctx)) and running it safely;
- `engine`    the daily replay: the KEEP rule's orders, E1's fills, fees and sizing, the House exits, the holdings log;
- `results`   what a run returns and what leaves each window (`view`);
- `placebo`   the residual, the stress residual, the universe excess and the matched placebos, from the log alone;
- `runner`    the in-process entry points and the decider-isolated wrapper;
- `child`     the module the decider child runs for the "panel" kind;
- `screen`    XS1: the pre-check, the program's own floor, the look, the sentence stated beside every live trade;
- `identity`  the xs evidence identity (panel bands bind to it);
- `synth`     synthetic panels for tests (never market data);
- `book`      the parent-side adapter between a live panel program and E1's EquityBook (plumbing: no identity).

Standard library and numpy only (the House runs Python 3.11 with numpy, never pyarrow).
"""

#: Bumped whenever the engine's arithmetic or runtime semantics change what a run returns: part of every run's hash.
XS_ENGINE_VERSION = "xs-engine-1"
#: The panel store layout `store.PanelStore` reads and `store.write_panel` writes.
XS_STORE_VERSION = "xs-panel-v1"
#: The panels a program may name in NEEDS.
PANELS = ("sp500",)
#: The decider kind (league/equity/kinds.py `KINDS`) and the swarm structure of a panel family.
KIND = "panel"
STRUCTURE = "panel"

__all__ = ["XS_ENGINE_VERSION", "XS_STORE_VERSION", "PANELS", "KIND", "STRUCTURE"]
