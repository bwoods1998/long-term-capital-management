"""THE DEEP KEY (history-expansion plan, amendment A58; release R1 "deep-report"): the sealed 2001-04-09..2008-12-31
era (DVAL) judged beside a recent key, as the two-key screen S3, with NO identity move.

The pinned pre-registration is PREREG-H (the plan's Appendix A, sha256 6ca65b3e...; pinned before any code of this
package was written). This package implements it; where its words leave a choice, the choice is stated in the module
that makes it (`config.READINGS`).

WHY NO IDENTITY MOVES. Programs never see a date (league/equity/ctx.py): a calendar-blind program's results depend on
its bars alone. So a deep segment's bars are written session for session onto the first N Train-window sessions from
2016-01-04 (`relabel`), and the UNCHANGED equity engine runs them (league/equity/runner.py `Isolated` on that store).
Nothing of league/equity, league/gym, league/live or ltcm/ is edited: the equity identity (78022ca6) and the options
execution fingerprint (b60410ad) stay byte-identical. Calendar and event readers would read scrambled dates there, so
they are found (`blind`: an AST scan AND a behavioural test on two relabelings) and are not eligible.

THE SEAL. DVAL rows never touch the desktop: the House fetches them through the gateway's Tiingo route
(league/ops/equity_deep.py) into `<state>/equity-deep/sealed/` (0700, the `DEEP_GATE` mark). Sealed blocks open only
with a `gate.DeepGateCapability` (minted on a store carrying the mark, for a named reason), only inside a look, and
only into a temporary store inside the sealed tree that is removed when the look ends, even on failure
(`relabel.relabeled`), and swept when a killed look could not remove it (`blocks.sweep`). TRAIN-D
(2010-15) is open and never opens `sealed/`. Outputs are verdicts and counts only (`report`): no DVAL figure beyond
pass or fail, nothing derived from vendor data is committed, and births see nothing (this package imports nothing of
league.swarm, league.live or league.ops; league/swarm never names it).

THE PIECES (flat: the House's release copies league/deep/*.py and the two date fixtures):

- `config`    the eras, segments, mask, universe, eligibility rules, bars, look budget and the receipt pin;
- `calendar`  the deep NYSE calendar (the repo's pre-2022 rules plus the four closures), the fixtures, the
              pseudo-dates;
- `blocks`    the deep store's blocks (raw OHLCV + divCash + splitFactor), open and sealed, and their reader;
- `relabel`   a segment written onto Train-window pseudo-dates in a temporary store, `all` rebuilt as of the
              segment's last session;
- `blind`     the calendar-blind check: the scan and the behavioural test;
- `stat`      x2, the per-symbol drift-free timing excess;
- `screen3`   S3's keys, bars, own floors (null worlds on TRAIN and TRAIN-D, with a crash-stress null) and rules;
- `gate`      the deep gate's capability, one look per version, the look ledger, the budget and the canaries;
- `report`    counts only, for the captain;
- `identity`  the deep evidence identity (a verdict binds to it; the league/xs pattern).

`DEEP.md` beside them is the release's contract. Standard library and numpy only (the House runs Python 3.11).
"""

#: Bumped whenever what a look computes changes (part of every ledger row, beside the deep identity).
DEEP_ENGINE_VERSION = "deep-engine-1"
#: The deep store's layout (`blocks.DeepStore` reads it, league/ops/equity_deep.py writes it).
DEEP_STORE_VERSION = "equity-deep-v1"
#: The screen this package implements.
SCREEN = "S3"

__all__ = ["DEEP_ENGINE_VERSION", "DEEP_STORE_VERSION", "SCREEN"]
