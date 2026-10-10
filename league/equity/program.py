"""Loading an equity program (league/equity/EQUITY.md) and calling its `decide(ctx)` safely, in the Gym and live alike.

Owner: core. The code rules are the options contract's, imported unchanged: `league.gym.safety.check_program` (math and
numpy only, no date, no I/O) and the Gym runtime's sandbox (`league.gym.runtime`: its short builtins, its importer, its
per-call wall-clock limit, its error count and disqualification, PARAMS bound at the declaration). What differs is
NEEDS (`parse_needs`: symbols, history, max_hold_sessions) and the intents (`normalize_intents`: buy, sell, cancel).
league/gym is never edited for the lane (it is inside the options fingerprint): this module reuses its pieces by
import, and `league.swarm.evaluator.EQUITY_GYM_FILES` lists every league/gym module the lane imports.

    program = load_program(code, name="seed-overnight-spy", params={"theta": 0.02})
    runner = program.start()            # a fresh module: the program's globals are its memory
    intents = runner.decide(ctx)        # a list of plain intent dicts, [] on an error or a timeout

NEEDS = {"symbols": [...] (1-20, inside config.UNIVERSE), "history": 0-504 sessions, "max_hold_sessions": 1-60
(default 20)}. Intents (at most `config.MAX_INTENTS` a call; each exactly one of "buy", "sell", "cancel"):

    {"buy": "SPY", "share": 0.5 | "usd": 250.0, "at": "open" | "close", "tag": "..."}   # share of the sleeve's equity
    {"sell": <lot id>, "at": "open" | "close", "tag": "..."}                            # a whole lot
    {"cancel": <order id>}

"at" defaults to "open". A malformed intent is dropped and counted as an error with its reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from ..gym.safety import CodeRefused


class NeedsRefused(CodeRefused):
    """NEEDS or PARAMS is malformed (the message says how)."""


@dataclass(frozen=True)
class Needs:
    """What an equity program asks for (EQUITY.md, "NEEDS")."""

    symbols: tuple[str, ...]
    history: int
    max_hold_sessions: int

    def as_dict(self) -> dict[str, Any]:
        """{"symbols": [...], "history": n, "max_hold_sessions": n} (JSON-safe)."""
        raise NotImplementedError("core: league/equity/program.py Needs.as_dict")


def parse_needs(raw: Any) -> Needs:
    """Validate an equity program's NEEDS (NeedsRefused names what is wrong): symbols a list of 1-20 distinct symbols of
    `config.UNIVERSE` (upper-cased), history 0-504 (default 252), max_hold_sessions 1-60 (default 20); no other key."""
    raise NotImplementedError("core: league/equity/program.py parse_needs")


@dataclass
class EquityProgram:
    """A checked equity program with its merged PARAMS. `sha` names the code, `run_sha` the code with its parameters
    (as `league.gym.runtime.Program`)."""

    name: str
    code: str
    needs: Needs
    params: dict[str, Any]
    sha: str
    run_sha: str
    _compiled: Any = field(repr=False, default=None)

    def start(self, *, timeout: float = 1.0, max_errors: int = 25,
              budget_seconds: float | None = None) -> "EquityRunner":
        """A runner with fresh module state."""
        raise NotImplementedError("core: league/equity/program.py EquityProgram.start")


def load_program(code: str, *, name: str = "program", params: Mapping[str, Any] | None = None) -> EquityProgram:
    """Check (`league.gym.safety.check_program`), compile with PARAMS bound at the declaration (the Gym runtime's way),
    parse NEEDS (`parse_needs`) and merge PARAMS (`league.gym.runtime.merge_params`). CodeRefused / NeedsRefused say
    why not."""
    raise NotImplementedError("core: league/equity/program.py load_program")


class EquityRunner:
    """One run's instance of an equity program (its module globals are its memory): the Gym runtime's `Runner` timing,
    error counting and disqualification, with the equity intents (`normalize_intents`)."""

    def __init__(self, program: EquityProgram, *, timeout: float = 1.0, max_errors: int = 25,
                 budget_seconds: float | None = None):
        raise NotImplementedError("core: league/equity/program.py EquityRunner")

    def decide(self, ctx: Any) -> list[dict[str, Any]]:
        """The program's intents as plain dicts ([] on an error, a timeout or once disqualified)."""
        raise NotImplementedError("core: league/equity/program.py EquityRunner.decide")

    def stats(self) -> dict[str, Any]:
        """{calls, errors, timeouts, seconds, messages, disqualified} (the Gym runner's shape)."""
        raise NotImplementedError("core: league/equity/program.py EquityRunner.stats")


def normalize_intents(raw: Any, on_error: Any = None) -> list[dict[str, Any]]:
    """decide's return (None, one dict or a list) as plain intent dicts: exactly one of "buy", "sell", "cancel"; "at"
    "open" (default) or "close"; a buy's "share" in (0, 1] or "usd" > 0 (exactly one); at most `config.MAX_INTENTS`.
    Malformed ones are dropped and reported through `on_error(text)`."""
    raise NotImplementedError("core: league/equity/program.py normalize_intents")


__all__ = ["NeedsRefused", "CodeRefused", "Needs", "parse_needs", "EquityProgram", "load_program", "EquityRunner",
           "normalize_intents"]
