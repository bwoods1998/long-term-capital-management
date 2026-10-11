"""Loading a panel program (XS.md: NEEDS, PARAMS, decide(ctx)) and running it safely.

Owner: package C.

NEEDS = {"panel": "sp500", "history": 20..252 (default 252), "max_names": 5..40 (default 10), "rebalance": "weekly" |
"monthly", "weekday": 0..4 (weekly only; default 0), "max_hold_sessions": 5..60 (default 60)}; no other key. "panel"
and "rebalance" have no default: a panel program says which panel it reads and when it is asked.

decide(ctx) returns `{"target": {id: w}, "at": "open" | "close"}`, `{"hold": True}` or None (a hold). THE TARGET (the
pinned pre-registration's C2, narrowed by E4-SPEC D10): every id is in `ctx.ids`; every w is finite and 0 < w <=
`config.MAX_WEIGHT` + 1e-9 (a weight of exactly 0 is read as the id's absence); sum w <= 1 + 1e-9; the number of names
is 0 (all cash) or between `config.MIN_NAMES` and NEEDS max_names. An invalid target is a malformed answer: an error
counted against the program, positions held, never a failed decide. The engine turns a valid target into orders by THE
KEEP RULE (`league.xs.engine.plan_orders`).

A decide call FAILED (`XsRunner.last_failed`) when it raised, ran past its limit or the runner is disqualified: the
House's exit rule counts those (`league.equity.config.FAILED_DECIDES_EXIT`), never a malformed answer.

Evidence module (in the xs identity). The safety check and the runtime are the Gym's own (`league.gym.safety.
check_program`, `league.gym.runtime.Runner`), unchanged; NEEDS and PARAMS refusals are E1's classes.
"""

from __future__ import annotations

import ast
import hashlib
import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from ..equity.program import CodeRefused, NeedsRefused
from ..gym import runtime as _rt
from ..gym.safety import check_program, params_declaration
from . import PANELS, config

NEEDS_KEYS = ("panel", "history", "max_names", "rebalance", "weekday", "max_hold_sessions")
DEFAULT_HISTORY = 252
DEFAULT_MAX_NAMES = 10
DEFAULT_WEEKDAY = 0
DEFAULT_MAX_HOLD = 60
AT = ("open", "close")
#: The slack a weight and a target's sum may carry (float arithmetic in a program's own normalisation).
WEIGHT_SLACK = 1e-9
#: The keys an answer may carry.
ANSWER_KEYS = ("target", "at", "hold")


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


def _whole(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or \
            float(value) != int(value):
        raise NeedsRefused(f"NEEDS[{name!r}] is a whole number")
    return int(value)


def parse_needs(raw: Any) -> Needs:
    """NEEDS as a `Needs`; `NeedsRefused` (E1's) says how it is malformed: a key outside `NEEDS_KEYS`, a panel outside
    `league.xs.PANELS`, a figure outside its bound, a schedule outside `config.REBALANCE` (a daily one included), a
    `weekday` on a monthly program (but its default, 0: `parse_needs(needs.as_dict())` is `needs`)."""
    if not isinstance(raw, Mapping):
        raise NeedsRefused("NEEDS is a dict")
    unknown = set(map(str, raw)) - set(NEEDS_KEYS)
    if unknown:
        raise NeedsRefused(f"NEEDS has unknown keys: {', '.join(sorted(unknown))}")
    panel = raw.get("panel")
    if not isinstance(panel, str) or panel not in PANELS:
        raise NeedsRefused(f"NEEDS['panel'] is one of {', '.join(PANELS)}")
    rebalance = raw.get("rebalance")
    if not isinstance(rebalance, str) or rebalance not in config.REBALANCE:
        raise NeedsRefused(f"NEEDS['rebalance'] is one of {', '.join(config.REBALANCE)} (a program is asked once a "
                           "week or once a month, never daily)")
    history = _whole(raw.get("history", DEFAULT_HISTORY), "history")
    if not config.MIN_HISTORY <= history <= config.MAX_HISTORY:
        raise NeedsRefused(f"NEEDS['history'] is {config.MIN_HISTORY} to {config.MAX_HISTORY} sessions")
    max_names = _whole(raw.get("max_names", DEFAULT_MAX_NAMES), "max_names")
    if not config.MIN_NAMES <= max_names <= config.MAX_NAMES:
        raise NeedsRefused(f"NEEDS['max_names'] is {config.MIN_NAMES} to {config.MAX_NAMES} names")
    weekday = _whole(raw.get("weekday", DEFAULT_WEEKDAY), "weekday")
    if not 0 <= weekday <= 4:
        raise NeedsRefused("NEEDS['weekday'] is 0 (Monday) to 4 (Friday)")
    if rebalance == "monthly" and weekday != DEFAULT_WEEKDAY:
        # the default is read back (`Needs.as_dict` always carries the key: the parent re-parses the child's answer)
        raise NeedsRefused("NEEDS['weekday'] is a weekly program's: a monthly one is asked before the month's first "
                           "session")
    max_hold = _whole(raw.get("max_hold_sessions", DEFAULT_MAX_HOLD), "max_hold_sessions")
    if not config.MIN_HOLD_CAP <= max_hold <= config.MAX_HOLD_CAP:
        raise NeedsRefused(f"NEEDS['max_hold_sessions'] is {config.MIN_HOLD_CAP} to {config.MAX_HOLD_CAP} sessions")
    return Needs(panel, history, max_names, rebalance, weekday, max_hold)


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
        return XsRunner(self, timeout=timeout, max_errors=max_errors, budget_seconds=budget_seconds)


def load_program(code: str, *, name: str = "program", params: Mapping[str, Any] | None = None) -> XsProgram:
    """Check (`league.gym.safety.check_program`, unchanged), compile with PARAMS bound at the declaration, parse NEEDS
    (`parse_needs`) and merge PARAMS, as E1's `load_program`. CodeRefused / NeedsRefused say why not."""
    check_program(code)
    tree = ast.parse(code)
    declaration = params_declaration(tree)
    declaration.value = ast.copy_location(ast.Call(func=ast.Name(id="__gym_bind_params", ctx=ast.Load()),
                                                   args=[declaration.value], keywords=[]), declaration.value)
    try:
        compiled = compile(ast.fix_missing_locations(tree), _rt.PROGRAM_FILENAME, "exec")
    except (SyntaxError, ValueError, RecursionError, MemoryError) as exc:
        raise CodeRefused(f"the program does not compile: {type(exc).__name__}: {str(exc)[:160]}") from None
    namespace = _rt._fresh_namespace(params)
    try:
        _rt._limited(lambda: exec(compiled, namespace), _rt.LOAD_TIMEOUT)  # noqa: S102 - checked code, short builtins
    except _rt.ProgramTimeout:
        raise CodeRefused(f"the program's module body ran past {_rt.LOAD_TIMEOUT:.0f} s") from None
    except _rt.NeedsRefused as exc:  # PARAMS' overrides (merge_params): the lane's own refusal type
        raise NeedsRefused(str(exc)) from None
    except Exception as exc:  # the module body itself failed
        raise CodeRefused(f"{_rt._where(exc)}: the program fails to load: {type(exc).__name__}: {str(exc)[:160]}") \
            from None
    needs = parse_needs(namespace.get("NEEDS"))
    merged = namespace["__gym_bound_params"]
    if _rt.canonical(namespace.get("PARAMS")) != _rt.canonical(merged):
        raise CodeRefused("the module body mutates PARAMS after its declaration; keep run memory in STATE")
    sha = hashlib.sha256(code.encode("utf-8")).hexdigest()
    run_sha = hashlib.sha256((sha + _rt.canonical(merged)).encode("utf-8")).hexdigest()
    return XsProgram(name=str(name), code=code, needs=needs, params=merged, sha=sha, run_sha=run_sha,
                     _compiled=compiled)


class XsRunner(_rt.Runner):
    """One run's instance of a panel program (its module globals are its memory): the Gym runtime's `Runner` timing,
    error counting and disqualification, with the panel's answer (`normalize_target`). `last_failed`: whether the last
    decide call failed (raised, timed out, or the runner is disqualified): E1's flag, with E1's meaning."""

    def __init__(self, program: XsProgram, *, timeout: float = 1.0, max_errors: int = 25,
                 budget_seconds: float | None = None):
        super().__init__(program, timeout=timeout, max_errors=max_errors,  # type: ignore[arg-type]
                         budget_seconds=budget_seconds)
        #: Whether the last decide call failed (raised, timed out, or the runner is disqualified).
        self.last_failed = False

    def decide(self, ctx: Any) -> dict[str, Any]:  # type: ignore[override]
        """`{"target": {id: w}, "at"}` or `{"hold": True}` (a hold on an error, a timeout, a malformed target or once
        disqualified)."""
        self.last_failed = True
        if self.disqualified:
            return {"hold": True}
        self.calls += 1
        began = time.perf_counter()
        try:
            raw = _rt._limited(lambda: self._decide(ctx), self.timeout) if self._alarm else self._decide(ctx)
        except _rt.ProgramTimeout:
            self.timeouts += 1
            self._error(f"decide ran past {self.timeout:.2f} s")
            return {"hold": True}
        except RecursionError:
            self._error("decide recursed too deep")
            return {"hold": True}
        except Exception as exc:
            self._error(f"{_rt._where(exc)}: {type(exc).__name__}: {str(exc)[:160]}")
            return {"hold": True}
        finally:
            spent = time.perf_counter() - began
            self.seconds += spent
        if spent > self.timeout:
            # Whatever the program did with the alarm, a call that ran past its limit answers nothing.
            self.timeouts += 1
            self._error(f"decide ran past {self.timeout:.2f} s")
            return {"hold": True}
        if self.budget_seconds is not None and self.seconds > self.budget_seconds and not self.disqualified:
            self.disqualified = (f"decide used {self.seconds:.0f} s, over the run's budget of "
                                 f"{self.budget_seconds:.0f} s")
            return {"hold": True}
        self.last_failed = False
        return normalize_target(raw, getattr(ctx, "ids", ()), self.program.needs.max_names,  # type: ignore[attr-defined]
                                self._error)

    def stats(self) -> dict[str, Any]:
        """{calls, errors, timeouts, seconds, disqualified, messages}: the restart check reads `calls`, `errors` and
        `disqualified`."""
        return super().stats()


def _number(value: Any) -> float | None:
    """A program's number as a float (a numpy scalar through its `item`), or None when it is none or not finite."""
    item = getattr(value, "item", None)
    if callable(item) and not isinstance(value, (int, float)):
        try:
            value = item()
        except (TypeError, ValueError):
            return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        return None
    return float(value)


def _slot(key: Any) -> int | None:
    """A target's key as an id: a whole number, or its decimal string (a target that came back through JSON)."""
    if isinstance(key, str):
        text = key.strip()
        if not text or len(text) > 12 or not (text.isdigit() or (text[0] == "-" and text[1:].isdigit())):
            return None
        return int(text)
    number = _number(key)
    if number is None or number != int(number):
        return None
    return int(number)


def _target(raw: Any, ids: Sequence[int], max_names: int) -> tuple[dict[str, Any] | None, str]:
    """(the normalized answer, "") or (None, why it is malformed)."""
    if not isinstance(raw, Mapping):
        return None, f"decide returned a {type(raw).__name__}; it returns a dict with 'target' and 'at', or 'hold'"
    unknown = sorted(str(k) for k in raw if k not in ANSWER_KEYS)
    if unknown:
        return None, f"an answer has 'target' and 'at', or 'hold'; not {', '.join(unknown[:3])}"
    if "target" not in raw:
        if raw.get("hold") is True and "at" not in raw:
            return {"hold": True}, ""
        return None, "an answer is {'target': {id: weight}, 'at': 'open' | 'close'} or {'hold': True}"
    if "hold" in raw:
        return None, "an answer has a target or a hold, never both"
    at = raw.get("at", "open")
    if not isinstance(at, str) or at not in AT:
        return None, "'at' is 'open' or 'close'"
    target = raw["target"]
    if not isinstance(target, Mapping):
        return None, "'target' is a dict of slot id to weight"
    if len(target) > 4 * config.MAX_NAMES:
        return None, f"a target names at most {max_names} slots"
    known = {int(i) for i in (ids.tolist() if hasattr(ids, "tolist") else ids)}
    weights: dict[int, float] = {}
    for key, value in target.items():
        ident = _slot(key)
        if ident is None:
            return None, "a target's keys are slot ids (whole numbers of ctx.ids)"
        if ident in weights:
            return None, f"a target names the slot {ident} twice"
        weight = _number(value)
        if weight is None or weight < 0:
            return None, "a target's weights are finite numbers, none negative (long only)"
        if weight > config.MAX_WEIGHT + WEIGHT_SLACK:
            return None, f"a weight is at most {config.MAX_WEIGHT:.2f} (a stock is at most 20% of the sleeve)"
        if ident not in known:
            return None, (f"the slot {ident} is not in ctx.ids (a held slot that left ctx.ids is sold by the House "
                          "at the next open: leave it out)")
        weights[ident] = weight
    weights = {ident: weight for ident, weight in sorted(weights.items()) if weight > 0}
    if math.fsum(weights.values()) > 1.0 + WEIGHT_SLACK:
        return None, "a target's weights sum to at most 1"
    if weights and not config.MIN_NAMES <= len(weights) <= int(max_names):
        return None, (f"a target holds no name (all cash) or {config.MIN_NAMES} to {int(max_names)} names (NEEDS "
                      f"max_names), not {len(weights)}")
    return {"target": weights, "at": at}, ""


def normalize_target(raw: Any, ids: Sequence[int], max_names: int,
                     on_error: Callable[[str], None] | None = None) -> dict[str, Any]:
    """A program's answer as `{"target": {int id: float w}, "at"}` or `{"hold": True}` (the module docstring's rule).
    A target's keys are read with `int()`, so one that came back through JSON (string keys) is the same target.
    `on_error(text)` is called once for a malformed answer, which is then a hold. None is a hold; a weight of exactly
    0 is the id's absence; the target's ids come back ascending."""
    if raw is None:
        return {"hold": True}
    try:
        answer, why = _target(raw, ids, max_names)
    except Exception as exc:  # noqa: BLE001 - whatever a program's object does when read, its answer is malformed
        answer, why = None, f"{type(exc).__name__}: {str(exc)[:160]}"
    if answer is None:
        if on_error:
            on_error(f"malformed answer: {why}")
        return {"hold": True}
    return answer


__all__ = ["NEEDS_KEYS", "DEFAULT_HISTORY", "DEFAULT_MAX_NAMES", "DEFAULT_WEEKDAY", "DEFAULT_MAX_HOLD", "AT",
           "WEIGHT_SLACK", "ANSWER_KEYS", "NeedsRefused", "CodeRefused", "Needs", "parse_needs", "XsProgram",
           "load_program", "XsRunner", "normalize_target"]
