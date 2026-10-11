"""THE EQUITY LANE (release E1, Oct 2026): agent programs that trade long-only ETFs (and later stocks) with real money.

The plan is the captain's design (private scratch) with its amendments; the build's contract between its packages is
`league/equity/INTERFACES.md` (every module, signature, shape, table and owner). This package is the lane's one home,
outside the options execution fingerprint (`league.swarm.evaluator.execution_fingerprint` hashes league/gym and
league/live only): equity semantics change here without resetting the options lane's evidence, and bind to their own
identity (`league.swarm.evaluator.equity_fingerprint`: the EVIDENCE modules only, the captain's A13: this file,
`config`, `store`, `program`, `ctx`, `engine`, `results`, `runner`, `synth`, `sizing`, `screen` and `child`; the
plumbing, `live`, `actions`, `schedule`, `families`, `bands` and `kinds`, moves no identity, so a plumbing fix retires
no live equity lineage). `league/live` reaches this package only through `league/live/equity_hook.py` and the decider's
kind table (`league/equity/kinds.py`).

The pieces:

- `config`    the lane's constants: universe and classes, half-spreads, fees, caps, windows, the hold rules;
- `store`     the daily store (raw and adjustment=all bars per symbol), its windows and the gate's capability;
- `program`   loading an equity program (EQUITY.md: NEEDS, PARAMS, decide(ctx)) and running it safely;
- `ctx`       what a program sees at the decision close, built identically in the Gym and live (I6);
- `engine`    the daily-bar replay (open and close fills at the official price x (1 +/- k x hs));
- `results`   what a run returns and what leaves each window (`view`);
- `runner`    the in-process entry points (Train, Validation, the sealed look) and the decider-isolated wrapper;
- `synth`     a synthetic store for tests (never market data);
- `sizing`    the one sizing function the book and the engine share;
- `bands`     the equity band rules: Probe seats, sizing up, EDM1 demotion;
- `screen`    the pre-registered share screen S1 (S1-R gates, S1-X labels);
- `live`      the EquityBook: lots, orders, fills, reconciliation, exports (the House's live equity path);
- `schedule`  the book's clock (16:20 bars, 16:30 decide, 09:25 pre-open, the open and close windows);
- `actions`   corporate actions and dividends from the venue's activities;
- `families`  the book's reader of the swarm (equity-lane rows, forward records, band writes);
- `kinds`     the decider's kind table (kind -> module run in the isolated child);
- `child`     the module the decider child runs for the "equity" kind.

Standard library and numpy only (the House runs Python 3.11 with numpy, never pyarrow).
"""

#: Bumped whenever the engine's arithmetic or runtime semantics change what a run returns: part of every run's hash.
EQUITY_ENGINE_VERSION = "equity-engine-1"
#: The daily store layout `store.EquityStore` reads and `store.write_store` writes.
EQUITY_STORE_VERSION = "equity-store-v1"
#: The two equity lanes (`league.swarm.elane` is their swarm-side home): "beta" (structure etf, labelled MARKET BETA
#: everywhere) and "equity" (etf and stock).
BETA, EQUITY = "beta", "equity"
LANES = (BETA, EQUITY)
#: Every equity order's client id starts so (`lq-<eid>-<family>`): the options book never takes one for its own or for
#: a foreign order (`league/live/real.py` `ingest`).
CLIENT_PREFIX = "lq-"
