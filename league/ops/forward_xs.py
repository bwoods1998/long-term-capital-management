"""The forward record and the shadow twin of a panel program. PACKAGE J OF RELEASE E4: OWED, NOT BUILT IN THIS BUILD.

Owner: package J, which waits for release E3 (the forward shadow swarm: `forward_db`, `forward_register`,
`forward_shadow`, `forward_audit`, `forward_twins`, `forward_report`, `fill_minutes`, built in parallel on
feat/equity-e3). The captain's ruling for this build: J is left out, its stubs are kept, and the rule that depends on
it stands exactly as E4-SPEC has it: WHILE J IS NOT MERGED, OR ITS NIGHTLY RUN HAS NOT WRITTEN THE MARKER,
`elane.panel.mode` "live" READS AS "gate" (`league.swarm.elane_xs.live_ready`): no panel program opens a position the
forward record is not shadowing. Every function here raises NotImplementedError; nothing imports E3 at import time.

WHY IT IS OWED AND NOT OPTIONAL. E3's registry skips any structure but "etf" and "stock", and a counted session with
no `fwd_twins` row is NOT agreed: the first live panel close would enter the next Done checkpoint with every session
missing and A14 would read "not consistent" for the whole checkpoint, the seeds' closes included.

WHAT J BUILDS (E4-SPEC 10.6):
1. THE REGISTRY. `scored`: every version of a panel family judged on the Train bar (its `elane_xs` record and the
   scored event `elane_xs.score` writes), registered "train_pass" or "train_fail"; row: lane "equity", `ugroup`
   `UGROUP`, `needs` (the literal NEEDS parsed by `league.xs.program.parse_needs`), `route` and `alpha_f`.
2. THE NIGHTLY RUN. `run_program`: `league.xs.runner.Isolated.forward` on the program's forward days through the
   forward job's OWN decider, at k 1.0 and 1.5, recomputed whole each night. `series`: r = the run's daily r, w = its
   w, b = bench / w (0 where w is 0), so E3's x = r - w x b IS the panel's residual.
3. THE TWIN OF A LIVE INSTANCE. The same program run flat from the session after the instance's first, RUN KEY = THE
   INSTANCE ID and the store's columns built for the same aids. agree(I, d) = the same sell keys, the same buy keys,
   and every buy's WEIGHT (usd over its own book's budget) within `WEIGHT_TOL` of its twin's.
4. THE MARKER. After the twins, `league.xs.book.TWINS_FILE` is rewritten (ids and days only).

THE FORWARD CHECKPOINTS ARE THE PINNED PRE-REGISTRATION'S (XSCREEN-1 section 11; `league.xs.screen.CHECKPOINTS`,
`ALPHA_F`): n in 20, 60, 120, 250 forward sessions; a pass = t_n >= c_FX AND sum x > 1e-12 AND sum x15 > 1e-12 AND the
placebo rank over the same sessions <= alpha_f; alpha_f 0.12 for a fresh lineage that declares the route at
registration (it can never take an XS1 look), 0.03 after an XS1 look. Its own receipt comes from a later study.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

UGROUP = "panel:sp500"
ROUTE = "XS1"
#: A row registered before its forward screen is pinned (E3's rule): the after-a-look alpha.
ALPHA_F = "0.03"
WEIGHT_TOL = 1e-3
GROUPS = ("xs:train_pass", "xs:train_fail", "xs:look_pass", "xs:look_fail")

_STUB = ("league.ops.forward_xs is package J of release E4: owed, not built (it waits for release E3; until its "
         "marker exists elane.panel.mode 'live' reads as 'gate')")


def scored(store: Any) -> list[dict[str, Any]]:
    """The registry rows of every panel version judged on the Train bar (1)."""
    raise NotImplementedError(_STUB)


def run_program(shadow: Any, program: Mapping[str, Any]) -> tuple[Any, dict[str, Any]]:
    """One registered panel program's nightly forward runs: (E3's ShadowRun of the k 1.0 run, the k 1.5 result) (2)."""
    raise NotImplementedError(_STUB)


def series(result: Mapping[str, Any]) -> Any:
    """A forward run as E3's series (r, w, b = bench / w), so that E3's x is the panel's residual (2)."""
    raise NotImplementedError(_STUB)


def keys(picks: Mapping[str, Any], symbols: Mapping[int, str]) -> dict[str, Any]:
    """A decision's order keys: {"sells": {"S|SYM|at|<lot opened day>"}, "buys": {"B|SYM|at": weight}} (3)."""
    raise NotImplementedError(_STUB)


def agree(live: Mapping[str, Any], twin: Mapping[str, Any]) -> bool:
    """Whether a live session's keys and its twin's agree (3): a session with no program order on either side does."""
    raise NotImplementedError(_STUB)


def twin(shadow: Any, instance: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The `fwd_twins` rows of one alive panel instance, one a decision session whose next session has closed (3)."""
    raise NotImplementedError(_STUB)


def write_marker(root: str | Path, instances: Mapping[str, Mapping[str, Any]], *, through: str, at: str) -> Path:
    """Rewrite the twin marker (4): `league.xs.book.TWINS_FILE`, version `TWINS_VERSION`; instance ids and days only."""
    raise NotImplementedError(_STUB)


def rebalance_agreement(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Beside, for the reports, never a rule: an instance's REBALANCE sessions agreed k of n, and the sessions that
    disagreed."""
    raise NotImplementedError(_STUB)


__all__ = ["UGROUP", "ROUTE", "ALPHA_F", "WEIGHT_TOL", "GROUPS", "scored", "run_program", "series", "keys", "agree",
           "twin", "write_marker", "rebalance_agreement"]
