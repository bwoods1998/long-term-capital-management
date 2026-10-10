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

"at" defaults to "open". A malformed intent is dropped and counted as an error with its reason. A decide call FAILED
(`EquityRunner.last_failed`) when it raised, ran past its limit or the runner is disqualified: the House's exit rule
counts those (`config.FAILED_DECIDES_EXIT`), never a malformed intent.
"""

from __future__ import annotations

import ast
import hashlib
import math
import time
from dataclasses import dataclass, field
from typing import Any, Mapping

from ..gym import runtime as _rt
from ..gym.safety import CodeRefused, check_program, params_declaration
from . import config

BUY, SELL, CANCEL = "buy", "sell", "cancel"
KINDS = (BUY, SELL, CANCEL)
AT = ("open", "close")
MAX_TAG = 64
NEEDS_KEYS = ("symbols", "history", "max_hold_sessions")


class NeedsRefused(_rt.NeedsRefused):
    """NEEDS or PARAMS is malformed (the message says how). A `CodeRefused`, and the Gym runtime's `NeedsRefused`."""


@dataclass(frozen=True)
class Needs:
    """What an equity program asks for (EQUITY.md, "NEEDS")."""

    symbols: tuple[str, ...]
    history: int
    max_hold_sessions: int

    def as_dict(self) -> dict[str, Any]:
        """{"symbols": [...], "history": n, "max_hold_sessions": n} (JSON-safe)."""
        return {"symbols": list(self.symbols), "history": self.history, "max_hold_sessions": self.max_hold_sessions}


def _whole(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or \
            float(value) != int(value):
        raise NeedsRefused(f"NEEDS[{name!r}] is a whole number")
    return int(value)


def parse_needs(raw: Any) -> Needs:
    """Validate an equity program's NEEDS (NeedsRefused names what is wrong): symbols a list of 1-20 distinct symbols of
    `config.UNIVERSE` (upper-cased), history 0-504 (default 252), max_hold_sessions 1-60 (default 20); no other key."""
    if not isinstance(raw, Mapping):
        raise NeedsRefused("NEEDS is a dict")
    unknown = set(map(str, raw)) - set(NEEDS_KEYS)
    if unknown:
        raise NeedsRefused(f"NEEDS has unknown keys: {', '.join(sorted(unknown))}")
    symbols = raw.get("symbols")
    if isinstance(symbols, str):
        symbols = [symbols]
    if not isinstance(symbols, (list, tuple)) or not symbols or \
            not all(isinstance(s, str) and s.strip() for s in symbols):
        raise NeedsRefused("NEEDS['symbols'] is a list of one to twenty symbols, e.g. ['SPY']")
    symbols = tuple(dict.fromkeys(s.strip().upper() for s in symbols))
    if len(symbols) > config.MAX_SYMBOLS:
        raise NeedsRefused(f"NEEDS['symbols'] names at most {config.MAX_SYMBOLS} symbols")
    outside = [s for s in symbols if config.class_of(s) is None]
    if outside:
        raise NeedsRefused(f"NEEDS['symbols'] names {', '.join(outside)}, outside the lane's universe")
    history = _whole(raw.get("history", config.DEFAULT_HISTORY), "history")
    if not 0 <= history <= config.MAX_HISTORY:
        raise NeedsRefused(f"NEEDS['history'] is 0 to {config.MAX_HISTORY} sessions")
    max_hold = _whole(raw.get("max_hold_sessions", config.DEFAULT_MAX_HOLD), "max_hold_sessions")
    if not 1 <= max_hold <= config.MAX_HOLD_CAP:
        raise NeedsRefused(f"NEEDS['max_hold_sessions'] is 1 to {config.MAX_HOLD_CAP} sessions")
    return Needs(symbols, history, max_hold)


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
        return EquityRunner(self, timeout=timeout, max_errors=max_errors, budget_seconds=budget_seconds)


def load_program(code: str, *, name: str = "program", params: Mapping[str, Any] | None = None) -> EquityProgram:
    """Check (`league.gym.safety.check_program`), compile with PARAMS bound at the declaration (the Gym runtime's way),
    parse NEEDS (`parse_needs`) and merge PARAMS (`league.gym.runtime.merge_params`). CodeRefused / NeedsRefused say
    why not."""
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
    return EquityProgram(name=str(name), code=code, needs=needs, params=merged, sha=sha, run_sha=run_sha,
                         _compiled=compiled)


class EquityRunner(_rt.Runner):
    """One run's instance of an equity program (its module globals are its memory): the Gym runtime's `Runner` timing,
    error counting and disqualification, with the equity intents (`normalize_intents`)."""

    def __init__(self, program: EquityProgram, *, timeout: float = 1.0, max_errors: int = 25,
                 budget_seconds: float | None = None):
        super().__init__(program, timeout=timeout, max_errors=max_errors,  # type: ignore[arg-type]
                         budget_seconds=budget_seconds)
        #: Whether the last decide call failed (raised, timed out, or the runner is disqualified).
        self.last_failed = False

    def decide(self, ctx: Any) -> list[dict[str, Any]]:
        """The program's intents as plain dicts ([] on an error, a timeout or once disqualified)."""
        self.last_failed = True
        if self.disqualified:
            return []
        self.calls += 1
        began = time.perf_counter()
        try:
            raw = _rt._limited(lambda: self._decide(ctx), self.timeout) if self._alarm else self._decide(ctx)
        except _rt.ProgramTimeout:
            self.timeouts += 1
            self._error(f"decide ran past {self.timeout:.2f} s")
            return []
        except RecursionError:
            self._error("decide recursed too deep")
            return []
        except Exception as exc:
            self._error(f"{_rt._where(exc)}: {type(exc).__name__}: {str(exc)[:160]}")
            return []
        finally:
            spent = time.perf_counter() - began
            self.seconds += spent
        if spent > self.timeout:
            self.timeouts += 1
            self._error(f"decide ran past {self.timeout:.2f} s")
            return []
        if self.budget_seconds is not None and self.seconds > self.budget_seconds and not self.disqualified:
            self.disqualified = (f"decide used {self.seconds:.0f} s, over the run's budget of "
                                 f"{self.budget_seconds:.0f} s")
            return []
        self.last_failed = False
        return normalize_intents(raw, self._error)

    def stats(self) -> dict[str, Any]:
        """{calls, errors, timeouts, seconds, messages, disqualified} (the Gym runner's shape)."""
        return super().stats()


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        return None
    return float(value)


def _whole_id(value: Any) -> int | None:
    number = _number(value)
    if number is None or number != int(number) or number < 0:
        return None
    return int(number)


def _intent(row: Any) -> tuple[dict[str, Any] | None, str]:
    """(the normalized intent, "") or (None, why it is malformed)."""
    if not isinstance(row, dict):
        return None, "an intent is a dict"
    kinds = [k for k in KINDS if k in row]
    if len(kinds) != 1:
        return None, "an intent has exactly one of 'buy', 'sell' or 'cancel'"
    kind = kinds[0]
    if kind == CANCEL:
        oid = _whole_id(row[CANCEL])
        return ({CANCEL: oid}, "") if oid is not None else (None, "'cancel' names an order id (a whole number)")
    at = row.get("at", "open")
    if at not in AT:
        return None, "'at' is 'open' or 'close'"
    tag = row.get("tag")
    tag = "" if tag is None else str(tag)[:MAX_TAG]
    if kind == SELL:
        lid = _whole_id(row[SELL])
        if lid is None:
            return None, "'sell' names a lot id (a whole number)"
        return {SELL: lid, "at": at, "tag": tag}, ""
    symbol = row[BUY]
    if not isinstance(symbol, str) or not symbol.strip():
        return None, "'buy' names a symbol"
    has_share, has_usd = row.get("share") is not None, row.get("usd") is not None
    if has_share == has_usd:
        return None, "a buy has exactly one of 'share' (of the sleeve's equity) or 'usd'"
    out: dict[str, Any] = {BUY: symbol.strip().upper()}
    if has_share:
        share = _number(row["share"])
        if share is None or not 0 < share <= 1:
            return None, "a buy's 'share' is in (0, 1]"
        out["share"] = share
    else:
        usd = _number(row["usd"])
        if usd is None or usd <= 0:
            return None, "a buy's 'usd' is a positive number"
        out["usd"] = usd
    out.update(at=at, tag=tag)
    return out, ""


def normalize_intents(raw: Any, on_error: Any = None) -> list[dict[str, Any]]:
    """decide's return (None, one dict or a list) as plain intent dicts: exactly one of "buy", "sell", "cancel"; "at"
    "open" (default) or "close"; a buy's "share" in (0, 1] or "usd" > 0 (exactly one); at most `config.MAX_INTENTS`.
    Malformed ones are dropped and reported through `on_error(text)`."""
    if raw is None:
        return []
    if isinstance(raw, Mapping):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        if on_error:
            on_error(f"decide returned a {type(raw).__name__}; it returns a list of intents")
        return []
    items = list(raw)
    if len(items) > config.MAX_INTENTS and on_error:
        on_error(f"decide returned {len(items)} intents; only the first {config.MAX_INTENTS} count")
    out = []
    for item in items[:config.MAX_INTENTS]:
        try:
            row = _rt._plain(item)
        except (ValueError, TypeError) as exc:
            if on_error:
                on_error(f"malformed intent: {exc}")
            continue
        intent, why = _intent(row)
        if intent is None:
            if on_error:
                on_error(f"malformed intent: {why}")
            continue
        out.append(intent)
    return out


__all__ = ["NeedsRefused", "CodeRefused", "Needs", "parse_needs", "EquityProgram", "load_program", "EquityRunner",
           "normalize_intents", "BUY", "SELL", "CANCEL", "AT"]
