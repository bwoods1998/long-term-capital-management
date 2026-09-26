"""Loading a program and calling `decide(ctx)` safely: the same code in a replay and live.

    program = load_program(code, name="condor-vrp", params={"entry_delta": 0.12})
    runner = program.start()               # a fresh module: the program's globals are its memory
    intents = runner.decide(ctx)           # a list of intent dicts, [] on an error or a timeout

`load_program` checks the code (`safety.check_program`), parses `NEEDS` (`parse_needs`) and merges
`PARAMS` with the caller's overrides (keys must exist, types must match). `Program.sha` names the
code and `Program.run_sha` the code with its parameters: a trivial parameter change is a new trial.

`start()` executes the code in a fresh namespace whose builtins are a short list (no open, no print,
an `__import__` that hands out math and numpy only). Each `decide` call runs under a wall-clock limit
(`signal.setitimer`, main thread only; elsewhere the limit is measured after the fact and a slow call
counts as an error), its exceptions are caught and counted with the program's line number, and after
`max_errors` the runner is disqualified: it returns [] ever after and says why.

numpy is imported only when a program imports it. Python 3.11+.
"""

from __future__ import annotations

import hashlib
import json
import math
import signal
import threading
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Mapping

from .safety import CodeRefused, check_program

PROGRAM_FILENAME = "<gym-program>"
MAX_ROOTS = 5
MAX_INTENTS = 12
DEFAULT_TIMEOUT = 1.0
DEFAULT_MAX_ERRORS = 25


class NeedsRefused(CodeRefused):
    """NEEDS or PARAMS is malformed (the message says how)."""


@dataclass(frozen=True)
class Needs:
    """What a program asks the engine for (PROGRAM.md, "NEEDS")."""

    roots: tuple[str, ...]
    dte_min: int
    dte_max: int
    band: float          # strikes within +-band of spot, as a fraction (0.05 = 5%)
    cadence: int         # minutes between decide calls, 1-30
    history: int         # prior sessions of daily bars in ctx.under[root]
    start: int           # first decision minute (minutes since midnight ET)
    end: int             # last decision minute

    def as_dict(self) -> dict[str, Any]:
        return {"roots": list(self.roots), "dte": [self.dte_min, self.dte_max], "band": self.band, "cadence": self.cadence,
                "history": self.history, "start": self.start, "end": self.end}


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise NeedsRefused(f"NEEDS[{name!r}] must be a number")
    return float(value)


def parse_needs(raw: Any) -> Needs:
    """Validate a program's NEEDS dict (NeedsRefused says what is wrong)."""
    if not isinstance(raw, Mapping):
        raise NeedsRefused("NEEDS is a dict")
    unknown = set(raw) - {"roots", "dte", "band", "cadence", "history", "start", "end"}
    if unknown:
        raise NeedsRefused(f"NEEDS has unknown keys: {', '.join(sorted(map(str, unknown)))}")
    roots = raw.get("roots")
    if isinstance(roots, str):
        roots = [roots]
    if not isinstance(roots, (list, tuple)) or not roots or not all(isinstance(r, str) and r.strip() for r in roots):
        raise NeedsRefused("NEEDS['roots'] is a list of one to five option roots, e.g. ['SPY']")
    roots = tuple(dict.fromkeys(r.strip().upper() for r in roots))
    if len(roots) > MAX_ROOTS:
        raise NeedsRefused(f"NEEDS['roots'] names at most {MAX_ROOTS} roots")
    dte = raw.get("dte", [0, 7])
    if not isinstance(dte, (list, tuple)) or len(dte) != 2:
        raise NeedsRefused("NEEDS['dte'] is [min, max] calendar days to expiry")
    lo, hi = int(_number(dte[0], "dte")), int(_number(dte[1], "dte"))
    if not 0 <= lo <= hi <= 60:
        raise NeedsRefused("NEEDS['dte'] needs 0 <= min <= max <= 60")
    band = _number(raw.get("band", 0.05), "band")
    if not 0.002 <= band <= 0.30:
        raise NeedsRefused("NEEDS['band'] is a fraction of spot from 0.002 to 0.30")
    cadence = int(_number(raw.get("cadence", 5), "cadence"))
    if not 1 <= cadence <= 30:
        raise NeedsRefused("NEEDS['cadence'] is 1 to 30 minutes")
    history = int(_number(raw.get("history", 10), "history"))
    if not 0 <= history <= 60:
        raise NeedsRefused("NEEDS['history'] is 0 to 60 sessions")
    start = int(_number(raw.get("start", 571), "start"))
    end = int(_number(raw.get("end", 958), "end"))
    if not 570 <= start <= end <= 960:
        raise NeedsRefused("NEEDS['start'] and ['end'] are minutes since midnight ET within 570..960, start <= end")
    return Needs(roots, lo, hi, band, cadence, history, start, end)


def _json_scalar(value: Any) -> bool:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return True
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    if isinstance(value, (list, tuple)):
        return len(value) <= 64 and all(_json_scalar(v) and not isinstance(v, (list, tuple)) for v in value)
    return False


def merge_params(defaults: Any, overrides: Mapping[str, Any] | None) -> dict[str, Any]:
    """PARAMS with the overrides applied: every key must already be in PARAMS, and a number stays a
    number (bools stay bools, strings stay strings)."""
    if not isinstance(defaults, Mapping):
        raise NeedsRefused("PARAMS is a dict of numbers, booleans, strings or short lists")
    out = {}
    for key, value in defaults.items():
        if not isinstance(key, str) or not _json_scalar(value):
            raise NeedsRefused(f"PARAMS[{key!r}] must be a number, boolean, string or short list")
        out[key] = list(value) if isinstance(value, tuple) else value
    for key, value in (overrides or {}).items():
        if key not in out:
            raise NeedsRefused(f"parameter {key!r} is not in the program's PARAMS")
        base = out[key]
        if not _json_scalar(value):
            raise NeedsRefused(f"parameter {key!r} must be a number, boolean, string or short list")
        numeric = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)  # noqa: E731
        if (numeric(base) != numeric(value)) or (isinstance(base, bool) != isinstance(value, bool)) or \
                (isinstance(base, str) != isinstance(value, str)) or (isinstance(base, list) != isinstance(value, (list, tuple))):
            raise NeedsRefused(f"parameter {key!r} keeps the type of its default ({type(base).__name__})")
        out[key] = list(value) if isinstance(value, tuple) else value
    return out


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


# --------------------------------------------------------------------------- the sandboxed namespace
#: Standard-library modules numpy's own C code may import lazily while a program's frame is current
#: (C-level imports look `__import__` up in the CALLING frame's builtins: the program's).
_NUMPY_NEEDS = frozenset({"warnings", "operator", "functools", "contextlib", "collections", "copyreg", "itertools", "numbers",
                          "types", "re", "math"})


def _importer(name: str, globals: Any = None, locals: Any = None, fromlist: Any = (), level: int = 0) -> Any:
    """The `__import__` a program's builtins carry. A program's own import statements were checked by
    `safety.check_program` (math and numpy, nothing else, no submodule); this hands out math, numpy,
    and whatever numpy's internals ask for on its behalf (numpy.* and a few standard modules)."""
    import importlib

    if level != 0:
        raise ImportError("a program imports only math and numpy")
    root = name.split(".")[0]
    if name == "math":
        return math
    if root == "numpy" or name in _NUMPY_NEEDS:
        module = importlib.import_module(name)
        return module if fromlist else importlib.import_module(root)
    raise ImportError(f"a program imports only math and numpy, not {name}")


_SAFE_BUILTIN_NAMES = (
    "abs", "all", "any", "bool", "callable", "chr", "complex", "dict", "divmod", "enumerate", "filter", "float",
    "frozenset", "getattr", "hasattr", "int", "isinstance", "iter", "len", "list", "map", "max", "min", "next", "ord",
    "pow", "range", "reversed", "round", "set", "slice", "sorted", "str", "sum", "tuple", "zip",
    "ArithmeticError", "AssertionError", "Exception", "IndexError", "KeyError", "LookupError", "OverflowError",
    "RuntimeError", "StopIteration", "TypeError", "ValueError", "ZeroDivisionError", "True", "False", "None",
)


def _safe_builtins() -> dict[str, Any]:
    import builtins

    out = {name: getattr(builtins, name) for name in _SAFE_BUILTIN_NAMES if hasattr(builtins, name)}
    out["__import__"] = _importer
    return out


class ProgramTimeout(BaseException):
    """A decide call ran past its limit. A BaseException, so a program's `except Exception` cannot
    swallow it (bare `except:` and the BaseException family are refused by the safety check)."""


#: True only while a program's code runs under the alarm: a SIGALRM handled after the call has
#: returned (a signal is handled between bytecodes) must not raise inside the engine.
_ARMED = False
#: The alarm re-fires this often after its first shot, so a program that keeps running (a loop in a
#: `finally` block) is interrupted again until it unwinds.
REARM_SECONDS = 0.02


def _on_alarm(signum: int, frame: Any) -> None:
    if _ARMED:
        raise ProgramTimeout("decide ran past its time limit")


_ALARM_INSTALLED = False


def _can_alarm() -> bool:
    global _ALARM_INSTALLED
    if threading.current_thread() is not threading.main_thread() or not hasattr(signal, "setitimer"):
        return False
    if not _ALARM_INSTALLED:
        signal.signal(signal.SIGALRM, _on_alarm)
        _ALARM_INSTALLED = True
    return True


LOAD_TIMEOUT = 5.0


def _limited(fn: Any, seconds: float) -> Any:
    """fn() under a re-arming wall-clock alarm where one can be set (the main thread)."""
    global _ARMED
    if not _can_alarm():
        return fn()
    _ARMED = True
    signal.setitimer(signal.ITIMER_REAL, seconds, REARM_SECONDS)
    try:
        return fn()
    finally:
        _ARMED = False
        signal.setitimer(signal.ITIMER_REAL, 0.0, 0.0)


def _where(exc: BaseException) -> str:
    """'line N' of the deepest frame inside the program, for the error message."""
    lines = [f.lineno for f in traceback.extract_tb(exc.__traceback__) if f.filename == PROGRAM_FILENAME]
    return f"line {lines[-1]}" if lines else "load"


@dataclass
class Program:
    """A checked program with its parameters. `start()` makes a runner with fresh state."""

    name: str
    code: str
    needs: Needs
    params: dict[str, Any]
    sha: str
    run_sha: str
    _compiled: Any = field(repr=False, default=None)

    def start(self, *, timeout: float = DEFAULT_TIMEOUT, max_errors: int = DEFAULT_MAX_ERRORS,
              budget_seconds: float | None = None) -> "Runner":
        return Runner(self, timeout=timeout, max_errors=max_errors, budget_seconds=budget_seconds)


def load_program(code: str, *, name: str = "program", params: Mapping[str, Any] | None = None) -> Program:
    """Check, compile and read a program's NEEDS and PARAMS (CodeRefused / NeedsRefused say why not)."""
    check_program(code)
    compiled = compile(code, PROGRAM_FILENAME, "exec")
    namespace = _fresh_namespace()
    try:
        _limited(lambda: exec(compiled, namespace), LOAD_TIMEOUT)  # noqa: S102 - checked code, short builtins
    except ProgramTimeout:
        raise CodeRefused(f"the program's module body ran past {LOAD_TIMEOUT:.0f} s") from None
    except Exception as exc:  # the module body itself failed
        raise CodeRefused(f"{_where(exc)}: the program fails to load: {type(exc).__name__}: {str(exc)[:160]}") from None
    needs = parse_needs(namespace.get("NEEDS"))
    merged = merge_params(namespace.get("PARAMS"), params)
    sha = hashlib.sha256(code.encode("utf-8")).hexdigest()
    run_sha = hashlib.sha256((sha + canonical(merged)).encode("utf-8")).hexdigest()
    return Program(name=str(name), code=code, needs=needs, params=merged, sha=sha, run_sha=run_sha, _compiled=compiled)


def _fresh_namespace() -> dict[str, Any]:
    return {"__builtins__": _safe_builtins(), "__name__": "gym_program"}


class Runner:
    """One run's instance of a program: its module globals persist from call to call (its memory)."""

    def __init__(self, program: Program, *, timeout: float = DEFAULT_TIMEOUT, max_errors: int = DEFAULT_MAX_ERRORS,
                 budget_seconds: float | None = None):
        self.program = program
        self.timeout = float(timeout)
        self.max_errors = int(max_errors)
        #: All of a run's decide calls together may take this long (None: no limit); then disqualified.
        self.budget_seconds = None if budget_seconds is None else float(budget_seconds)
        self.calls = 0
        self.errors = 0
        self.timeouts = 0
        self.seconds = 0.0
        self.messages: list[str] = []
        self.disqualified: str | None = None
        self._namespace = _fresh_namespace()
        _limited(lambda: exec(program._compiled, self._namespace), LOAD_TIMEOUT)  # noqa: S102
        self._decide = self._namespace["decide"]
        self._alarm = _can_alarm()

    def _error(self, text: str) -> None:
        self.errors += 1
        if len(self.messages) < 10 and text not in self.messages:
            self.messages.append(text)
        if self.errors >= self.max_errors and not self.disqualified:
            self.disqualified = f"{self.errors} errors (first: {self.messages[0] if self.messages else text})"

    def decide(self, ctx: Any) -> list[dict[str, Any]]:
        """Call the program's decide(ctx) and return its intents as a list of plain dicts ([] when it
        errs, times out, or is disqualified)."""
        if self.disqualified:
            return []
        self.calls += 1
        began = time.perf_counter()
        try:
            raw = _limited(lambda: self._decide(ctx), self.timeout) if self._alarm else self._decide(ctx)
        except ProgramTimeout:
            self.timeouts += 1
            self._error(f"decide ran past {self.timeout:.2f} s")
            return []
        except RecursionError:
            self._error("decide recursed too deep")
            return []
        except Exception as exc:
            self._error(f"{_where(exc)}: {type(exc).__name__}: {str(exc)[:160]}")
            return []
        finally:
            spent = time.perf_counter() - began
            self.seconds += spent
        if spent > self.timeout:
            # Whatever the program did with the alarm, a call that ran past its limit returns nothing.
            self.timeouts += 1
            self._error(f"decide ran past {self.timeout:.2f} s")
            return []
        if self.budget_seconds is not None and self.seconds > self.budget_seconds and not self.disqualified:
            self.disqualified = f"decide used {self.seconds:.0f} s, over the run's budget of {self.budget_seconds:.0f} s"
            return []
        return normalize_intents(raw, self._error)

    def stats(self) -> dict[str, Any]:
        return {"calls": self.calls, "errors": self.errors, "timeouts": self.timeouts, "seconds": round(self.seconds, 4),
                "messages": list(self.messages), "disqualified": self.disqualified}


def _plain(value: Any, depth: int = 0) -> Any:
    """A program's returned value as plain Python (numbers from numpy scalars, lists from arrays)."""
    if depth > 6:
        raise ValueError("an intent nests too deep")
    if value is None or isinstance(value, (bool, str)):
        return value[:300] if isinstance(value, str) else value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return float(value)
    if isinstance(value, Mapping):
        return {str(k): _plain(v, depth + 1) for k, v in list(value.items())[:32]}
    if isinstance(value, (list, tuple)):
        return [_plain(v, depth + 1) for v in list(value)[:32]]
    item = getattr(value, "item", None)  # a numpy scalar
    if callable(item):
        return _plain(item(), depth + 1)
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        return _plain(tolist(), depth + 1)
    raise ValueError(f"an intent holds a {type(value).__name__}")


def normalize_intents(raw: Any, on_error: Any = None) -> list[dict[str, Any]]:
    """decide's return (None, one dict, or a list of dicts) as a list of plain intent dicts. Each must
    have exactly one of "open", "close", "cancel"; malformed ones are dropped and reported."""
    if raw is None:
        return []
    if isinstance(raw, Mapping):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        if on_error:
            on_error(f"decide returned a {type(raw).__name__}; it returns a list of intents")
        return []
    out = []
    for item in list(raw)[:MAX_INTENTS]:
        try:
            row = _plain(item)
        except (ValueError, TypeError) as exc:
            if on_error:
                on_error(f"malformed intent: {exc}")
            continue
        if not isinstance(row, dict) or sum(1 for k in ("open", "close", "cancel") if k in row) != 1:
            if on_error:
                on_error("an intent has exactly one of 'open', 'close' or 'cancel'")
            continue
        out.append(row)
    return out


__all__ = ["Needs", "Program", "Runner", "load_program", "parse_needs", "merge_params", "normalize_intents",
           "NeedsRefused", "CodeRefused", "ProgramTimeout"]
