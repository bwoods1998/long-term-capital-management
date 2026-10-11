"""The `equity_neff` job: how many independent names the panel holds (D21), for the funnel's independent asset-years.

Owner: package B of release E4. Protected (league/ops/). STEP 0 STUB: every function raises NotImplementedError until
B lands. The registry row is package A's patch (E4-SPEC 13: monthly).

On Train segment 2 (2022-24: no sealed row), names with a full series: R = the correlation matrix of their daily
SECTOR-RESIDUAL returns (a name's close-to-close return less its sector's equal-weight mean, sectors re-formed monthly
by `league.xs.ctx.derive`); neff_rho = n / (1 + (n - 1) x the mean off-diagonal of R); neff_pr = (the sum of R's
eigenvalues)^2 / the sum of their squares. Into `<state>/equity-daily/neff.json` {"sp500": {"window", "names", "rho",
"neff_rho", "neff_pr", "computed_at"}}. Receipts and the funnel carry N_eff, never a return. Every sum is `math.fsum`.
"""

from __future__ import annotations

from typing import Any

FILE = "neff.json"
#: The job's own wall (seconds): what `league.xs.config.quiet` is asked with (held equal to its registry row).
WALL_S = 900

_STUB = "league.ops.equity_neff is a Step 0 stub: package B builds it (league/xs/E4_INTERFACES.md)"


def neff(returns: Any) -> dict[str, Any]:
    """{names, rho, neff_rho, neff_pr} of a (sessions, names) array of residual returns with no missing value."""
    raise NotImplementedError(_STUB)


def run(ctx: Any) -> dict[str, Any]:
    """The job. Its first statement is `league.xs.config.quiet(ctx.now(), WALL_S)`."""
    raise NotImplementedError(_STUB)


__all__ = ["FILE", "WALL_S", "neff", "run"]
