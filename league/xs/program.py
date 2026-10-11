"""Loading a panel program (XS.md: NEEDS, PARAMS, decide(ctx)) and running it safely.

Owner: package C. STEP 0 STUB: `Needs` and the constants are the contract; everything else raises NotImplementedError
until C lands.

NEEDS = {"panel": "sp500", "history": 20..252 (default 252), "max_names": 5..40 (default 10), "rebalance": "weekly" |
"monthly", "weekday": 0..4 (weekly only; default 0), "max_hold_sessions": 5..60 (default 60)}; no other key.

decide(ctx) returns `{"target": {id: w}, "at": "open" | "close"}`, `{"hold": True}` or None (a hold). THE TARGET (the
pinned pre-registration's C2, narrowed by E4-SPEC D10): every id is in `ctx.ids`; every w is finite and 0 < w <=
`config.MAX_WEIGHT` + 1e-9 (a weight of exactly 0 is read as the id's absence); sum w <= 1 + 1e-9; the number of names
is 0 (all cash) or between `config.MIN_NAMES` and NEEDS max_names. An invalid target is a malformed answer: an error
counted against the program, positions held, never a failed decide. The engine turns a valid target into orders by THE
KEEP RULE (`league.xs.engine.plan_orders`).

Evidence module (in the xs identity). The safety check and the runtime are the Gym's own (`league.gym.safety.
check_program`, `league.gym.runtime.Runner`), unchanged; NEEDS and PARAMS refusals are E1's classes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from ..equity.program import CodeRefused, NeedsRefused
from ..gym import runtime as _rt

NEEDS_KEYS = ("panel", "history", "max_names", "rebalance", "weekday", "max_hold_sessions")
DEFAULT_HISTORY = 252
DEFAULT_MAX_NAMES = 10
DEFAULT_WEEKDAY = 0
DEFAULT_MAX_HOLD = 60
AT = ("open", "close")
#: The slack a weight and a target's sum may carry (float arithmetic in a program's own normalisation).
WEIGHT_SLACK = 1e-9

_STUB = "league.xs.program is a Step 0 stub: package C builds it (league/xs/E4_INTERFACES.md)"


@dataclass(frozen=True)
class Needs:
    """What a panel program asks for (XS.md, "NEEDS")."""

    panel: str
    history: int
    max_names: int
    rebalance: str
    weekday: int
    max_hold_sessions: int

    def as_dict(self) -> dict[str, Any]:
        """The six NEEDS keys, JSON-safe."""
        return {"panel": self.panel, "history": self.history, "max_names": self.max_names,
                "rebalance": self.rebalance, "weekday": self.weekday, "max_hold_sessions": self.max_hold_sessions}


def parse_needs(raw: Any) -> Needs:
    """NEEDS as a `Needs`; `NeedsRefused` (E1's) says how it is malformed: a key outside `NEEDS_KEYS`, a panel outside
    `league.xs.PANELS`, a figure outside its bound, a schedule outside `config.REBALANCE` (a daily one included), a
    `weekday` on a monthly program."""
    raise NotImplementedError(_STUB)


@dataclass
class XsProgram:
    """A checked panel program with its merged PARAMS. `sha` names the code, `run_sha` the code with its parameters
    (as `league.gym.runtime.Program`)."""

    name: str
    code: str
    needs: Needs
    params: dict[str, Any]
    sha: str
    run_sha: str
    _compiled: Any = field(repr=False, default=None)

    def start(self, *, timeout: float = 1.0, max_errors: int = 25,
              budget_seconds: float | None = None) -> "XsRunner":
        """A runner with fresh module state."""
        raise NotImplementedError(_STUB)


def load_program(code: str, *, name: str = "program", params: Mapping[str, Any] | None = None) -> XsProgram:
    """Check (`league.gym.safety.check_program`, unchanged), compile with PARAMS bound at the declaration, parse NEEDS
    (`parse_needs`) and merge PARAMS, as E1's `load_program`. CodeRefused / NeedsRefused say why not."""
    raise NotImplementedError(_STUB)


class XsRunner(_rt.Runner):
    """One run's instance of a panel program (its module globals are its memory): the Gym runtime's `Runner` timing,
    error counting and disqualification, with the panel's answer (`normalize_target`). `last_failed`: whether the last
    decide call failed (raised, timed out, or the runner is disqualified): E1's flag, with E1's meaning."""

    def __init__(self, program: XsProgram, *, timeout: float = 1.0, max_errors: int = 25,
                 budget_seconds: float | None = None):
        raise NotImplementedError(_STUB)

    def decide(self, ctx: Any) -> dict[str, Any]:  # type: ignore[override]
        """`{"target": {id: w}, "at"}` or `{"hold": True}` (a hold on an error, a timeout, a malformed target or once
        disqualified)."""
        raise NotImplementedError(_STUB)

    def stats(self) -> dict[str, Any]:
        """{calls, errors, timeouts, seconds, disqualified, messages}: the restart check reads `calls`, `errors` and
        `disqualified`."""
        raise NotImplementedError(_STUB)


def normalize_target(raw: Any, ids: Sequence[int], max_names: int,
                     on_error: Callable[[str], None] | None = None) -> dict[str, Any]:
    """A program's answer as `{"target": {int id: float w}, "at"}` or `{"hold": True}` (the module docstring's rule).
    A target's keys are read with `int()`, so one that came back through JSON (string keys) is the same target.
    `on_error(text)` is called once for a malformed answer, which is then a hold."""
    raise NotImplementedError(_STUB)


__all__ = ["NEEDS_KEYS", "DEFAULT_HISTORY", "DEFAULT_MAX_NAMES", "DEFAULT_WEEKDAY", "DEFAULT_MAX_HOLD", "AT",
           "WEIGHT_SLACK", "NeedsRefused", "CodeRefused", "Needs", "parse_needs", "XsProgram", "load_program",
           "XsRunner", "normalize_target"]
