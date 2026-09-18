"""The Foundry: an hourly evidence loop for the floor's strategies (leap: foundry).

The floor already learns, but slowly: a shadow variant needs twelve settlements before
`Strategies.promote` reads it, the committee's gates need days, and the lab sits down once a
night. The Foundry turns that into an evidence loop that runs around the clock:

1. **Candidates.** Every `interval_minutes` (30) it takes the next family in round-robin, and the
   next of that family's strategies (its house starter, then whatever its live desk runs). It
   builds the baselines (the live desk's settings and the best shadow's), `param_candidates`
   (10) settings jittered around the best-known ones with categorical flips drawn from the
   family's `STARTER_VARIANTS`, all seeded by the cycle, and `code_candidates` (2) mutations of
   the code written by a model and validated with the lab's own `validate_change`.
2. **Backtests.** Every candidate is replayed on the last `window_days` (5) of real Kalshi and
   Coinbase history by the backtest engine (`python3 -m ltcm.backtest --spec FILE`), one run per
   Sail sandbox (`foundry-0` .. `foundry-7`), side by side.
3. **Selection** reads only the out-of-sample third of each run's closed positions: enough
   trades, a return on notional above the best baseline's by `margin`, and a 95% confidence
   lower bound on the mean P&L per trade above `min_ci_lower`.
4. **Shadow.** The best qualifier goes onto the family's worst-performing shadow desk at once:
   new params on that desk's strategy row, or new code through `Strategies.install`. A live
   desk is never touched here.
5. **Live.** A deployed candidate whose backtest cleared the confidence bound and whose forward
   shadow record since deployment has `min_forward_settled` (5) settlements at P&L >= 0 is
   adopted by the family's live desk, the way `Strategies.promote` moves settings; its
   `promoted_at` resets the evidence. A lopsided event strategy (favorites bought at 0.80 or
   more) also needs its forward record to pass `evidence.passes`. Risk limits, sizes, caps and
   capital never change here.

A family in `excluded_families` (the evolution loop's retired families, handed over by the
service) is never picked for a cycle and no candidate on one of its desks goes live.

Everything is on the tape with existing kinds: a `lab.hypothesis` per cycle, a `desk.code_run`
on every desk that received a deployment or an adoption, an `ops.alert` for an adoption. A
cycle never raises and never runs twice at once. Standard library only.
"""

from __future__ import annotations

import ast
import hashlib
import importlib
import inspect
import json
import math
import queue
import random
import re
import secrets
import threading
import time
import types
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, TimeoutError as FuturesTimeout, wait as wait_futures
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Mapping

from .events import now_iso
from .lab import KIT_API, LabError, validate_change
from .strategies import (
    QUOTE_VARIANTS,
    SECOND_STARTERS,
    STARTER_CADENCE,
    STARTER_VARIANTS,
    STARTERS,
    STARTERS_DIR,
    _epoch,
    _return_on_notional,
)

DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "interval_minutes": 30,
    # Weather is not backtestable: its starter prices from NWS forecasts, which have no history.
    # Ranges is retired (Sept 17, 2026: taking hourly buckets lost at every quote lag of a second
    # or more, and its shadow desks were down $43 to $90 each).
    "families": ["kalshi", "crypto"],
    #: Retired families, never picked and never fast-tracked (`evolution.excluded_families`).
    "excluded_families": [],
    "param_candidates": 10,
    "code_candidates": 2,
    "profile": "k3",
    "reasoning_effort": "high",
    "max_output_tokens": 16000,
    "budget_usd_per_day": "25",
    "sandboxes": 8,
    "backtest_timeout_seconds": 900,
    # Each backtest sandbox's own daily fuse; a desk's fuse would stop the loop by mid-morning.
    "sandbox_daily_seconds": 43200,
    "window_days": 5,
    # Sept 17, 2026: five days gave the leading Kalshi candidates 2-8 positions against the 60
    # the gate asks for, so nothing ever qualified. A family may replay a longer window and see
    # more of the board; the sandboxes' history cache keeps the cost to the first cycle.
    "family_window_days": {"kalshi": 10, "crypto": 7},
    "family_max_markets": {"kalshi": 8000},
    "step_minutes": 15,
    "family_step_minutes": {"ranges": 5},
    "learning_usd": 10,
    "fill_model": "conservative",
    "max_markets": 3000,
    "seed": 7,
    "split_fraction": 0.66,
    "min_oos_trades": 25,
    "min_trades": 60,
    "margin": 0.01,
    "min_ci_lower": 0.0,
    "min_forward_settled": 5,
    "jitter_min": 0.10,
    "jitter_max": 0.50,
    "code_chars": 20000,
    "model_wait_seconds": 600,
    "excluded_strategies": [],
    # A shadow desk that received a candidate is not handed another for this long, so the
    # candidate earns a forward record; after `forward_max_hours` without one it expires.
    "protect_hours": 6,
    "forward_max_hours": 72,
    # Size, order counts and price guards are the floor's, never a candidate's: they are neither
    # jittered nor taken from a model's params, and a desk keeps its own values when it adopts.
    # `maker_fee` and `min_margin` are spot_quotes' fee guard (Sept 17, 2026): jittered, they
    # moved the spread a bid needs, and a model told a lower fee would set it.
    "frozen_params": [
        "notional_usd", "no_max", "max_new", "max_intents", "max_quotes", "max_symbols",
        "max_open_per_series", "max_open_per_event", "pages", "maker_fee", "min_margin",
    ],
}
UNBACKTESTABLE_FAMILIES = ("weather",)
UNBACKTESTABLE_STRATEGIES = ("daily_temps", "temps_ensemble", "poly_cross", "perp_funding")
BUDGET_DESK = "foundry"
RESULT_MARKER = "BACKTEST-RESULT "
#: The longest result line the sandbox prints: its output is bounded at 4,000 characters.
RESULT_LINE_CHARS = 3600
#: A Foundry-made strategy name: `<starter>_f<cycle>` or `<starter>_f<cycle>_<n>`.
FOUNDRY_NAME = re.compile(r"_f\d+(?:_\d+)?$")
STRATEGY_NAME = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
PAYLOAD_BYTES = 3000
#: A `desk.code_run` the Foundry writes stays under this many bytes as JSON (the site takes 4 KB).
CODE_RUN_BYTES = 3200
DIRECTIONS = (
    "the pricing or selection model: which markets it trades and what it believes they are worth",
    "entries and exits: the price it pays, when it steps back, and what it declines to trade",
    "a filter that removes the kind of trade that loses out of sample",
    "fee-aware inventory management: trim or close existing holdings when the thesis decays; compare the cost of exiting now against holding, and cancel stale orders",
    "regime adaptation: distinguish persistent trends from mean reversion with past-only volatility and trend features, without increasing risk or size",
    "execution quality: maker-first entries, spread and fee hurdles, stale-order expiry, and selective fills rather than high turnover",
)


# --------------------------------------------------------------------------- model code
#: What a model-written strategy may import. The backtest engine runs `decide` in its own Python
#: process, so code that could reach the interpreter (sys, atexit, gc, the engine's modules, a
#: module's attributes) could write its own result. Everything a strategy reads comes through `kit`.
SAFE_MODULES = frozenset({
    "__future__", "bisect", "collections", "datetime", "decimal", "fractions", "functools", "heapq",
    "itertools", "json", "math", "random", "re", "statistics", "time", "typing", "zoneinfo",
})
SAFE_TYPING = frozenset({
    "Any", "Callable", "DefaultDict", "Dict", "FrozenSet", "Iterable", "Iterator", "List", "Mapping",
    "MutableMapping", "Optional", "Sequence", "Set", "Tuple", "Union",
})
#: Names a strategy may not use at all: evaluation, files, the interpreter's namespaces, and
#: library helpers that set attributes or evaluate annotations on the caller's behalf.
BANNED_NAMES = frozenset({
    "__import__", "breakpoint", "compile", "delattr", "eval", "exec", "exit", "globals", "help", "input",
    "locals", "memoryview", "open", "quit", "setattr", "vars",
    "get_type_hints", "singledispatch", "singledispatchmethod", "total_ordering", "update_wrapper", "wraps",
})
#: Attributes a strategy may not read: frames and code, dynamic lookups, and the modules a safe
#: module happens to import (statistics.sys, typing.types, fractions.operator, ...).
BANNED_ATTRIBUTES = frozenset({
    "ag_await", "ag_code", "ag_frame", "co_code", "co_consts", "cr_await", "cr_code", "cr_frame", "cr_origin",
    "f_back", "f_builtins", "f_code", "f_globals", "f_locals", "f_trace", "gi_code", "gi_frame", "gi_suspended",
    "gi_yieldfrom", "tb_frame", "tb_next",
    "format", "format_map", "attrgetter", "methodcaller",
    "get_type_hints", "singledispatch", "singledispatchmethod", "total_ordering", "update_wrapper", "wraps",
    "asyncio", "atexit", "builtins", "codecs", "concurrent", "copyreg", "ctypes", "enum", "environ",
    "gc", "importlib", "inspect", "io", "labkit", "ltcm", "marshal", "modules", "multiprocessing", "nt", "numbers",
    "operator", "os", "pathlib", "pickle", "popen", "posix", "runpy", "shutil", "signal", "socket", "stderr", "stdin",
    "stdout", "string", "subprocess", "sys", "system", "tempfile", "threading", "traceback", "types", "typing",
    "warnings", "weakref",
})
_REEXPORTED: frozenset[str] | None = None


def _reexported_modules() -> frozenset[str]:
    """Attribute names under which a safe module exposes a module that is not safe."""
    global _REEXPORTED
    if _REEXPORTED is not None:
        return _REEXPORTED
    found: set[str] = set()
    seen: set[int] = set()

    def scan(module: Any, depth: int) -> None:
        if id(module) in seen or depth > 3:
            return
        seen.add(id(module))
        for attr in dir(module):
            if attr.startswith("_"):
                continue
            try:
                value = getattr(module, attr)
            except Exception:
                continue
            if isinstance(value, types.ModuleType):
                if value.__name__.split(".")[0] in SAFE_MODULES:
                    scan(value, depth + 1)
                elif attr != "copy":  # dict.copy() is everywhere; the copy module is harmless
                    found.add(attr)

    for name in sorted(SAFE_MODULES - {"__future__"}):
        try:
            scan(importlib.import_module(name), 0)
        except Exception:
            continue
    _REEXPORTED = frozenset(found)
    return _REEXPORTED


def check_strategy_code(code: str) -> None:
    """Refuse model-written strategy code that could reach outside `decide(kit, params)`.

    The backtest runs a candidate inside the engine's own process, and a candidate that reached
    the interpreter could print its own result or rewrite the engine's (Sept 16, 2026: a
    candidate that registered an `atexit` handler printed a result line that qualified). So a
    candidate imports only `SAFE_MODULES`; never reads or writes an attribute that starts with an
    underscore (`__name__` read aside), a frame, or a module a safe module re-exports; never
    assigns or deletes an attribute at all (a module's function or a shared class's method would
    change for the engine too); calls `getattr` only with a plain literal name; and never uses
    `BANNED_NAMES` (evaluation, files, namespaces, `str.format` field lookups). Raises LabError
    with the first reason."""
    try:
        tree = ast.parse(str(code or ""))
    except (SyntaxError, ValueError) as exc:
        raise LabError(f"the code does not compile: {str(exc)[:120]}") from None
    banned_attributes = BANNED_ATTRIBUTES | _reexported_modules()
    literal_getattr: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("getattr", "hasattr"):
            name = node.args[1] if len(node.args) >= 2 else None
            if (
                isinstance(name, ast.Constant) and isinstance(name.value, str) and not name.value.startswith("_")
                and name.value not in banned_attributes and len(node.args) <= 3 and not node.keywords
            ):
                literal_getattr.add(id(node.func))

    def refuse(node: Any, text: str) -> None:
        raise LabError(f"line {getattr(node, 'lineno', '?')}: {text}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in SAFE_MODULES or root in ("typing", "__future__"):
                    refuse(node, f"import {alias.name} is not allowed; a strategy imports only {', '.join(sorted(SAFE_MODULES - {'__future__'}))}")
        elif isinstance(node, ast.ImportFrom):
            module = str(node.module or "")
            if node.level or module.split(".")[0] not in SAFE_MODULES:
                refuse(node, f"from {'.' * node.level}{module} import is not allowed")
            for alias in node.names:
                if alias.name == "*" or alias.name.startswith("_") or alias.name in banned_attributes:
                    refuse(node, f"from {module} import {alias.name} is not allowed")
                if module == "typing" and alias.name not in SAFE_TYPING:
                    refuse(node, f"from typing import {alias.name} is not allowed")
                if module == "__future__" and alias.name != "annotations":
                    refuse(node, f"from __future__ import {alias.name} is not allowed")
        elif isinstance(node, ast.Attribute):
            if not isinstance(node.ctx, ast.Load):
                refuse(node, f"assigning or deleting an attribute (.{node.attr}) is not allowed; keep state in dicts")
            if (node.attr.startswith("_") and node.attr != "__name__") or node.attr in banned_attributes:
                refuse(node, f".{node.attr} is not allowed")
        elif isinstance(node, ast.Name):
            if node.id.startswith("__") and node.id != "__name__":
                refuse(node, f"{node.id} is not allowed")
            if node.id in BANNED_NAMES:
                refuse(node, f"{node.id} is not allowed")
            if node.id == "getattr" and id(node) not in literal_getattr:
                refuse(node, "getattr takes a literal attribute name here")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name.startswith("__"):
                refuse(node, f"defining {node.name} is not allowed")
            if isinstance(node, ast.ClassDef) and node.keywords:
                refuse(node, "class keywords (a metaclass) are not allowed")
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            if any(name.startswith("__") for name in node.names):
                refuse(node, "a dunder global is not allowed")
        elif isinstance(node, ast.MatchClass):
            for attr in node.kwd_attrs:
                if attr.startswith("_") or attr in banned_attributes:
                    refuse(node, f"matching on .{attr} is not allowed")


# --------------------------------------------------------------------------- evidence
def split_evidence(trade_pnls, notional_usd, fraction=0.66):
    """In-sample and out-of-sample evidence from a backtest's closed positions, in order.

    The first `fraction` of the positions are in sample, the rest out of sample. Return on
    notional charges each position the run's average notional per position; the confidence
    interval is the normal one on the mean P&L per position (None under two positions). This
    function is also shipped verbatim inside the backtest runner, so it uses `math` only.
    """
    pnls = []
    for value in trade_pnls or []:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            pnls.append(number)
    count = len(pnls)
    cut = int(math.floor(count * float(fraction)))
    try:
        notional = float(notional_usd or 0.0)
    except (TypeError, ValueError):
        notional = 0.0
    per_position = notional / count if count and notional > 0 else 0.0

    def part(rows):
        n = len(rows)
        total = sum(rows)
        ron = round(total / (per_position * n), 6) if n and per_position > 0 else None
        ci = None
        if n >= 2:
            mean = total / n
            sd = math.sqrt(sum((x - mean) ** 2 for x in rows) / (n - 1))
            half = 1.96 * sd / math.sqrt(n)
            ci = [round(mean - half, 6), round(mean + half, 6)]
        return {"trades": n, "pnl_usd": round(total, 6), "return_on_notional": ron, "ci95_mean_pnl": ci}

    return {"in_sample": part(pnls[:cut]), "out_of_sample": part(pnls[cut:])}


#: Uploaded as the sandbox's `main.py` for one backtest: call the engine's `run_backtest` with a
#: History paced for the sandboxes running side by side, and print one compact result line (the
#: report with its split, sized to the sandbox's bounded output) under this run's own marker.
#:
#: The strategy runs inside this process, so nothing it prints may pass for the result: the
#: report is the engine's return value, never text read back from the run's output; everything
#: printed during the run goes to a buffer that is thrown away; a strategy's `SystemExit` is a
#: failed run; the marker carries a secret made for this run alone; and the process ends with
#: `os._exit` right after the line, so no exit handler or finalizer writes after it.
RUNNER = r"""
import contextlib, gc, io, json, math, os, sys, traceback
sys.path.insert(0, "/lab")
sys.path.insert(0, "/lab/floor")
SPEC = json.loads(%(spec)s)
FRACTION = %(fraction)r
LIMIT = %(limit)d
MARKER = %(marker)r
MIN_INTERVAL = %(min_interval)r

%(split_source)s

SCALARS = ("strategy", "start", "end", "steps", "trades", "fills", "settled", "wins", "notional_usd", "pnl_usd",
           "fees_usd", "return_on_notional", "max_drawdown_usd", "ci95_mean_pnl", "errors", "unsupported")

def compact(report, split):
    keep = {key: report[key] for key in SCALARS if key in report}
    if isinstance(keep.get("unsupported"), str):
        keep["unsupported"] = keep["unsupported"][:400]
    keep["notes"] = [str(note)[:200] for note in (report.get("notes") or [])[:4]]
    keep["daily"] = list(report.get("daily") or [])[-7:]
    keep["split"] = split
    pnls = [x for x in (report.get("trade_pnls") or []) if isinstance(x, (int, float))]
    for digits in (4, 2):
        keep["trade_pnls"] = [round(float(x), digits) for x in pnls]
        line = json.dumps(keep, separators=(",", ":"), default=str)
        if len(line) <= LIMIT:
            return line
    keep["trade_pnls"] = []
    keep["trade_pnls_dropped"] = len(pnls)
    keep["daily"] = keep["daily"][-2:]
    line = json.dumps(keep, separators=(",", ":"), default=str)
    if len(line) > LIMIT:
        keep["notes"], keep["daily"] = [], []
        line = json.dumps(keep, separators=(",", ":"), default=str)
    return line

def cache_dir(engine):
    finder = getattr(engine, "_default_cache_dir", None)
    if callable(finder):
        try:
            return finder()
        except Exception:
            pass
    if os.environ.get("LTCM_HISTORY_CACHE"):
        return os.environ["LTCM_HISTORY_CACHE"]
    return "/lab/cache/history" if os.path.isdir("/lab/cache") else None

report, failure, engine = None, None, None
buffer = io.StringIO()
try:
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        try:
            from ltcm import backtest as engine
            history = None
            try:
                from ltcm.history import History
                history = History(cache_dir=cache_dir(engine), min_interval=MIN_INTERVAL)
            except Exception:
                history = None
            report = engine.run_backtest(SPEC, history=history)
        except BaseException:
            report, failure = None, traceback.format_exc()[-400:]
        try:
            gc.collect()  # a strategy's leftovers finish while their output still goes to the buffer
        except BaseException:
            pass
        gc.disable()
except BaseException:
    failure = failure or traceback.format_exc()[-400:]
if not isinstance(report, dict):
    report = {"strategy": SPEC.get("strategy"), "trades": 0, "errors": 1, "trade_pnls": [],
              "unsupported": "engine failed: " + str(failure or ("no report; " + buffer.getvalue()[-300:]))}
split = None
try:
    split = engine.split_report(report, FRACTION)
except Exception:
    split = None
if not isinstance(split, dict) or not isinstance(split.get("out_of_sample"), dict):
    split = split_evidence(report.get("trade_pnls") or [], report.get("notional_usd"), FRACTION)
try:
    line = MARKER + compact(report, split)
except Exception:
    line = MARKER + json.dumps({"strategy": SPEC.get("strategy"), "trades": 0, "errors": 1, "unsupported": "the report did not serialize"})
sys.__stdout__.write(line + "\n")
sys.__stdout__.flush()
os._exit(0)
"""


def run_marker(token: str) -> str:
    """The result marker for one run: `BACKTEST-RESULT <token> ` (the bare prefix without one)."""
    return f"{RESULT_MARKER}{token} " if token else RESULT_MARKER


def runner_code(spec: Mapping[str, Any], *, fraction: float = 0.66, token: str = "", min_interval: float = 0.15) -> str:
    """The sandbox program for one backtest of `spec`, printing under `token`'s marker."""
    return RUNNER % {
        "spec": json.dumps(json.dumps(dict(spec), default=str)),
        "fraction": float(fraction),
        "limit": RESULT_LINE_CHARS,
        "marker": run_marker(token),
        "min_interval": float(min_interval),
        "split_source": inspect.getsource(split_evidence),
    }


def parse_result(stdout: str | None, token: str = "") -> dict[str, Any] | None:
    """The report on the last line carrying this run's marker, or None. A line without the
    run's token (anything a strategy could print) is never read."""
    text = str(stdout or "")
    marker = run_marker(token)
    found = text.rfind(marker)
    if found < 0 or (found > 0 and text[found - 1] != "\n"):
        return None
    line = text[found + len(marker):].split("\n", 1)[0].strip()
    try:
        data = json.loads(line)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


# --------------------------------------------------------------------------- candidates
def literal_defaults(code: str | None) -> dict[str, Any]:
    """A strategy module's `DEFAULTS = {...}`, read without running the module."""
    try:
        tree = ast.parse(str(code or ""))
    except (SyntaxError, ValueError):
        return {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "DEFAULTS" for t in node.targets):
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, TypeError, SyntaxError, RecursionError):
                return {}
            return dict(value) if isinstance(value, dict) else {}
    return {}


def _defines_defaults(code: str | None) -> bool:
    """Whether a module assigns `DEFAULTS` at its top level (literal or not)."""
    try:
        tree = ast.parse(str(code or ""))
    except (SyntaxError, ValueError):
        return False
    return any(
        isinstance(node, (ast.Assign, ast.AnnAssign))
        and any(isinstance(t, ast.Name) and t.id == "DEFAULTS" for t in (node.targets if isinstance(node, ast.Assign) else [node.target]))
        for node in tree.body
    )


def pinned_frozen(code: str | None, params: Mapping[str, Any] | None, frozen: list[str] | tuple[str, ...]) -> dict[str, Any]:
    """The frozen settings a strategy runs with: its row's params over its code's `DEFAULTS`."""
    effective = {**literal_defaults(code), **dict(params or {})}
    return {key: effective[key] for key in frozen if key in effective}


def base_name(name: str) -> str:
    """`kalshi_favorites_f12_2` -> `kalshi_favorites`."""
    return FOUNDRY_NAME.sub("", str(name or ""))


def categorical_pool(variants: list[Mapping[str, Any]], defaults: Mapping[str, Any]) -> dict[str, list[Any]]:
    """Every choice (a string, a boolean, a list) the family's variants explore, with the code's
    default among them, for the keys where there is more than one value to flip between."""
    pool: dict[str, list[Any]] = {}
    for row in variants:
        for key, value in row.items():
            if isinstance(value, (bool, str, list)):
                values = pool.setdefault(key, [])
                if key in defaults and defaults[key] not in values and isinstance(defaults[key], (bool, str, list)):
                    values.append(defaults[key])
                if value not in values:
                    values.append(value)
    return {key: values for key, values in sorted(pool.items()) if len(values) >= 2}


def jitter_variants(
    base: Mapping[str, Any],
    *,
    seed: str,
    count: int,
    low: float = 0.10,
    high: float = 0.50,
    frozen: tuple[str, ...] | list[str] = (),
    pool: Mapping[str, list[Any]] | None = None,
    exclude: list[Mapping[str, Any]] | None = None,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """`count` distinct settings around `base`, decided by `seed`.

    Variant i moves every number by up to a scale that runs from `low` to `high` across the
    variants (integers stay integers and at least one; a fraction stays inside [0, 1]); every
    other variant also flips one choice to another value from `pool`. Frozen keys never move.
    Returns (params, how) pairs; a setting equal to `base`, to one in `exclude` or to an earlier
    variant is drawn again, a bounded number of times."""
    rng = random.Random(int.from_bytes(hashlib.sha256(seed.encode("utf-8")).digest()[:8], "big"))
    choices = {k: list(v) for k, v in (pool or {}).items() if k not in frozen}
    seen = [dict(base)] + [dict(row) for row in (exclude or [])]
    out: list[tuple[dict[str, Any], dict[str, Any]]] = []
    count = max(0, int(count))
    attempt = 0
    while len(out) < count and attempt < count * 6:
        index = attempt % max(1, count)
        attempt += 1
        scale = low + (high - low) * (index / max(1, count - 1))
        params: dict[str, Any] = {}
        for key in sorted(base):
            value = base[key]
            if key in frozen or isinstance(value, bool) or not isinstance(value, (int, float)):
                params[key] = value
                continue
            moved = value * (1.0 + rng.uniform(-scale, scale))
            if isinstance(value, int):
                moved = int(round(moved))
                if value >= 1:
                    moved = max(1, moved)
            else:
                moved = round(moved, 4)
                if 0.0 <= value <= 1.0:
                    moved = min(1.0, max(0.0, moved))
            params[key] = moved
        flipped = None
        if choices and index % 2 == 1:
            keys = sorted(choices)
            key = keys[rng.randrange(len(keys))]
            others = [v for v in choices[key] if v != params.get(key)]
            if others:
                params[key] = others[rng.randrange(len(others))]
                flipped = key
        if params in seen:
            continue
        seen.append(params)
        out.append((params, {"scale": round(scale, 3), "flip": flipped}))
    return out


def parse_reply(body: str | None) -> dict[str, Any] | None:
    """The JSON object in a model reply, tolerating prose and a fence around it."""
    text = str(body or "")
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


# --------------------------------------------------------------------------- small helpers
def _sha(text: str | None) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def _dec(value: Any) -> Decimal | None:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return number if number.is_finite() else None


def _float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _iso(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _clean(value: Any) -> Any:
    """Safe for the public tape: no markup, recursively."""
    if isinstance(value, str):
        return value.replace("<", "\u2039")
    if isinstance(value, Mapping):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    return value


def _clip_bytes(text: str, limit: int) -> str:
    """`text` cut to at most `limit` bytes of UTF-8, on a character boundary."""
    data = str(text or "").encode("utf-8")
    if len(data) <= limit:
        return str(text or "")
    return data[: max(0, limit)].decode("utf-8", "ignore")


def _json_bytes(payload: Any) -> int:
    return len(json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8"))


def _fmt(value: Any, spec: str = "+.3f") -> str:
    number = _float(value)
    return "n/a" if number is None else format(number, spec)


def _full(params: Mapping[str, Any], defaults: Mapping[str, Any]) -> dict[str, Any]:
    return {**dict(defaults), **dict(params)}


def _compact(full: Mapping[str, Any], defaults: Mapping[str, Any], keep: set[str]) -> dict[str, Any]:
    """The overrides a strategy row needs: keys the code lacks, keys set away from the code's
    default, and keys the best-known setting already named."""
    return {k: v for k, v in sorted(full.items()) if k in keep or k not in defaults or defaults[k] != v}


class Foundry:
    """Generate, backtest, select, deploy, fast-track. Owned by the service; `cycle()` is the
    whole loop and runs off the tick."""

    def __init__(
        self,
        *,
        log: Any,
        strategies: Any,
        sandboxes: Any,
        manifests: Callable[[], Mapping[str, Any]],
        state_path: str | Path,
        provider: Any = None,
        clock: Callable[[], float] = time.time,
        alert: Callable[[str, str], None] | None = None,
        config: Mapping[str, Any] | None = None,
        equity: Callable[[str], Any] | None = None,
        halted: Callable[[], bool] | None = None,
    ):
        self.log = log
        self.strategies = strategies
        self._sandboxes = sandboxes
        self.manifests = manifests
        self.state_path = Path(state_path)
        self.provider = provider
        self.clock = clock
        self._alert = alert
        self.config = {**DEFAULTS, **dict(config or {})}
        self.equity = equity
        #: True while the kill switch is engaged: a cycle that started before it keeps its
        #: backtests but moves nothing onto a live desk.
        self.halted = halted
        self._running = threading.Lock()
        self._cycle_fees: dict[str, Any] | None = None
        self._state_lock = threading.RLock()
        self._result_cache = None
        if self.config.get("result_cache", False):
            from .research_cache import ResearchCache
            from .sandbox import floor_extras
            engine = _sha(json.dumps(floor_extras(), sort_keys=True) + RUNNER
                          + inspect.getsource(runner_code) + inspect.getsource(split_evidence))
            self._result_cache = ResearchCache(self.state_path.with_name("research-cache.sqlite"), engine=engine,
                                               ttl_seconds=float(self.config.get("result_cache_seconds", 3600)), clock=clock)

    # ------------------------------------------------------------------ handles
    def sandboxes(self) -> Any:
        handle = self._sandboxes
        if callable(handle) and not hasattr(handle, "run"):
            try:
                return handle()
            except Exception:
                return None
        return handle

    def store(self) -> Any:
        return self.strategies.store

    def now(self) -> str:
        return now_iso(self.clock)

    def alert(self, level: str, text: str) -> None:
        if self._alert is None:
            return
        try:
            self._alert(level, _clean(str(text))[:500])
        except Exception:
            pass

    def enabled(self) -> bool:
        return bool(self.config.get("enabled", True)) and self.strategies is not None and self.sandboxes() is not None

    def due(self, at: str, last: str | None) -> bool:
        if not last:
            return True
        return _epoch(at) - _epoch(last) >= float(self.config["interval_minutes"]) * 60.0

    def running(self) -> bool:
        return self._running.locked()

    # ------------------------------------------------------------------ state
    def state(self) -> dict[str, Any]:
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, data: Mapping[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_name(self.state_path.name + f".tmp-{threading.get_ident()}")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        tmp.chmod(0o600)
        tmp.replace(self.state_path)

    def _save(self, **updates: Any) -> dict[str, Any]:
        with self._state_lock:
            data = {**self.state(), **updates}
            self._write(data)
            return data

    def _deployment(self, fid: str | None, **fields: Any) -> None:
        if not fid:
            return
        with self._state_lock:
            data = self.state()
            deployments = dict(data.get("deployments") or {})
            if fid not in deployments:
                return
            deployments[fid] = {**deployments[fid], **fields}
            data["deployments"] = deployments
            self._write(data)

    def _add_deployment(self, record: Mapping[str, Any]) -> None:
        with self._state_lock:
            data = self.state()
            deployments = dict(data.get("deployments") or {})
            for fid, other in list(deployments.items()):
                if other.get("status") == "shadow" and other.get("desk_id") == record["desk_id"] and (
                    other.get("strategy") == record["strategy"] or (other.get("kind") == "code" and record["kind"] == "code")
                ):
                    deployments[fid] = {**other, "status": "replaced", "ended_at": record["deployed_at"]}
            deployments[record["id"]] = dict(record)
            # Bounded: every open deployment, and the newest sixty that ended.
            ended = sorted((d for d in deployments.values() if d.get("status") != "shadow"), key=lambda d: str(d.get("deployed_at")))
            for old in ended[:-60]:
                deployments.pop(old["id"], None)
            data["deployments"] = deployments
            self._write(data)

    def summary(self) -> dict[str, Any] | None:
        """The last cycle, for the health file."""
        last = self.state().get("last")
        if not isinstance(last, Mapping):
            return None
        keys = ("at", "cycle", "family", "strategy", "candidates", "backtested", "cache_hits", "fresh_backtests", "qualified", "best_oos_return", "winner", "deployed_to", "fast_tracked", "seconds", "sandbox_seconds", "model_cost_usd", "skipped", "failed")
        return {k: last.get(k) for k in keys if k in last}

    def _next_cycle(self, state: Mapping[str, Any]) -> int:
        known = _int(state.get("cycle"))
        if known is not None:
            return known + 1
        # A lost state file must not reuse a cycle number (names and event ids carry it).
        highest = 0
        reader = getattr(self.log, "read", None)
        if callable(reader):
            try:
                for event in reader(kind="lab.hypothesis", limit=500, newest=True):
                    match = re.match(r"^foundry-(\d+)$", str(event.payload.get("hypothesis_id") or ""))
                    if match:
                        highest = max(highest, int(match.group(1)))
            except Exception:
                highest = 0
        return highest + 1

    # ------------------------------------------------------------------ the family
    @staticmethod
    def live_desk(family: str, manifests: Mapping[str, Any]) -> Any:
        live = sorted((m for m in manifests.values() if m.family == family and m.live), key=lambda m: m.id)
        return live[0] if live else None

    @staticmethod
    def shadow_desks(family: str, manifests: Mapping[str, Any]) -> list[Any]:
        return sorted((m for m in manifests.values() if m.family == family and not m.live), key=lambda m: m.id)

    def subjects(self, family: str, manifests: Mapping[str, Any]) -> list[str]:
        """The family's house starter, then every other strategy its live desk runs. A strategy
        the live desk has paused (a house starter a mutation replaced) is not mutated again:
        its descendants are, so two mutations of one parent never compete for the live desk."""
        names: list[str] = []
        house = STARTERS.get(family)
        # `excluded_strategies` (config): strategies whose replay can say nothing (Sept 18, 2026:
        # spot quoting at this account's fees makes no trade at any spread; its cycles cost the
        # crypto family a third of its research turns).
        excluded = {str(x) for x in (self.config.get("excluded_strategies") or ())} | set(UNBACKTESTABLE_STRATEGIES)
        live = self.live_desk(family, manifests)
        rows = self.store().for_desk(live.id) if live is not None else {}
        if house and house not in excluded and (rows.get(house) or {}).get("enabled", True):
            names.append(house)
        if live is not None:
            for name, row in sorted(rows.items()):
                if row.get("enabled", True) and name not in names and base_name(name) not in excluded:
                    names.append(name)
        # A paused live family can still search for a successor in isolated research. This
        # never enables its live parent or bypasses adoption/promotion gates. Prefer an active
        # descendant whenever one exists; never revive a retired/excluded family.
        recovery = self.config.get("paused_research_families") or []
        if (family in recovery and family not in self.excluded_families()
                and house and house not in UNBACKTESTABLE_STRATEGIES
                and not any(base_name(name) == house for name in names)):
            names.insert(0, house)
        return names

    def source_of(self, name: str, live: Any) -> str | None:
        """The code the live desk runs under `name`, else the house starter's file."""
        if not STRATEGY_NAME.match(str(name or "")):
            return None
        manager = self.sandboxes()
        if live is not None and manager is not None and hasattr(manager, "toolbox_files"):
            try:
                code = manager.toolbox_files(live.id).get(f"{name}.py")
            except Exception:
                code = None
            if code:
                return code
        path = STARTERS_DIR / f"{name}.py"
        return path.read_text(encoding="utf-8") if path.is_file() else None

    @staticmethod
    def variants_for(family: str, name: str) -> list[Mapping[str, Any]]:
        root = base_name(name)
        if root == STARTERS.get(family):
            return list(STARTER_VARIANTS.get(family) or [])
        if root == SECOND_STARTERS.get(family):
            return list(QUOTE_VARIANTS.get(family) or [])
        return []

    def cadence_of(self, family: str, name: str, live: Any) -> int:
        row = self.store().for_desk(live.id).get(name) if live is not None else None
        return int((row or {}).get("cadence_seconds") or STARTER_CADENCE.get(base_name(name)) or STARTER_CADENCE.get(family) or 600)

    def excluded_families(self) -> set[str]:
        configured = self.config.get("excluded_families") or ()
        return {str(f) for f in ((configured,) if isinstance(configured, str) else configured)}

    def _pick(self, manifests: Mapping[str, Any], state: Mapping[str, Any]) -> tuple[str, str, int, dict[str, int]] | None:
        excluded = self.excluded_families()
        families = [f for f in (self.config.get("families") or []) if f not in UNBACKTESTABLE_FAMILIES and f not in excluded]
        if not families:
            return None
        start = int(state.get("family_index") or 0) % len(families)
        subject_index = {str(k): int(v) for k, v in dict(state.get("subject_index") or {}).items()}
        for offset in range(len(families)):
            family = families[(start + offset) % len(families)]
            if not any(m.family == family for m in manifests.values()):
                continue
            names = self.subjects(family, manifests)
            if not names:
                continue
            index = subject_index.get(family, 0) % len(names)
            subject_index[family] = index + 1
            return family, names[index], (start + offset + 1) % len(families), subject_index
        return None

    def _evidence_config(self) -> dict[str, Any]:
        """The evidence gate's settings: the strategy runner's (`strategies.evidence`), so the
        fast-track and the hourly promotion judge a record the same way."""
        from . import evidence

        return evidence.settings(dict(getattr(self.strategies, "config", {}) or {}).get("evidence"))

    def _record(self, desk_id: str, name: str, since: str | None, **options: Any) -> dict[str, Any]:
        try:
            return dict(self.strategies.record(desk_id, name, since=since, **options) or {})
        except Exception:
            return {}

    def _equity(self, desk_id: str) -> Decimal | None:
        if self.equity is None:
            return None
        try:
            return _dec(self.equity(desk_id))
        except Exception:
            return None

    # ------------------------------------------------------------------ the cycle
    def cycle(self, at: str | None = None) -> dict[str, Any]:
        """One pass of the loop. Never raises; a cycle already running is not started again."""
        if not self._running.acquire(blocking=False):
            return {"skipped": "a foundry cycle is already running"}
        started = time.monotonic()
        at = at or self.now()
        try:
            summary = self._cycle(at)
        except Exception as exc:
            summary = {"at": at, "failed": f"{type(exc).__name__}: {str(exc)[:200]}"}
            self.alert("warning", f"foundry cycle failed: {type(exc).__name__}: {str(exc)[:160]}")
        finally:
            self._running.release()
        summary["seconds"] = round(time.monotonic() - started, 1)
        try:
            with self._state_lock:
                data = self.state()
                history = [row for row in (data.get("history") or []) if isinstance(row, Mapping)][-23:]
                data["last"] = {k: v for k, v in summary.items() if k != "candidates_detail"}
                data["history"] = history + [data["last"]]
                self._write(data)
        except Exception:
            pass
        return summary

    def progress(self, stage: str, message: str, **facts: Any) -> None:
        """Small factual milestones, streamed while a cycle is still running; never model
        chain-of-thought, credentials, source code or unexecuted order intentions."""
        try:
            self.log.append("lab", "lab.progress", {"component": "foundry", "stage": stage,
                            "message": str(message)[:600], **facts}, at=self.now())
        except Exception:
            pass

    def _cycle(self, at: str) -> dict[str, Any]:
        cfg = self.config
        manager = self.sandboxes()
        if manager is None or self.strategies is None:
            return {"at": at, "skipped": "no sandboxes"}
        problems: list[str] = []
        manifests = dict(self.manifests() or {})
        state = self.state()
        cycle = self._next_cycle(state)
        fast = self.fast_track(manifests, problems)
        try:
            self.prune_explorers(manifests)
        except Exception as exc:
            problems.append(f"explorer pruning failed: {type(exc).__name__}: {str(exc)[:120]}")
        pick = self._pick(manifests, state)
        if pick is None:
            self._save(cycle=cycle)
            self._report_problems(cycle, problems)
            return {"at": at, "cycle": cycle, "skipped": "no backtestable family has desks", "fast_tracked": fast}
        family, subject, family_index, subject_index = pick
        self.progress("research", f"Cycle {cycle}: exploring {family}/{subject}", cycle=cycle, family=family, strategy=subject)
        self._save(cycle=cycle, family_index=family_index, subject_index=subject_index)
        live = self.live_desk(family, manifests)
        shadows = self.shadow_desks(family, manifests)
        parent = live or (shadows[0] if shadows else None)
        source = self.source_of(subject, live)
        summary: dict[str, Any] = {"at": at, "cycle": cycle, "family": family, "strategy": subject, "fast_tracked": fast}
        if source is None or parent is None:
            summary["skipped"] = f"no source for {subject}"
            self._report_problems(cycle, problems)
            return summary

        self._cycle_fees = None
        if family == "crypto":
            try:
                self._cycle_fees = self.coinbase_fees()
            except ValueError as exc:
                self.progress("fees_unavailable", str(exc), cycle=cycle, family=family)
                return {**summary, "skipped": str(exc)}
        else:
            # Coinbase availability must never block another venue's research.
            self._cycle_fees = {"maker": "0.005", "taker": "0.009", "source": "unused crypto snapshot"}
        summary["coinbase_fees"] = dict(self._cycle_fees)
        if family == "crypto":
            self.progress("fees", f"Coinbase replay uses authenticated tier: {float(self._cycle_fees['maker']) * 100:g}% maker / {float(self._cycle_fees['taker']) * 100:g}% taker; same snapshot for all candidates", cycle=cycle, family=family)

        defaults = literal_defaults(source)
        frozen = [str(k) for k in (cfg.get("frozen_params") or [])]
        baselines, best_known, records = self.baselines(cycle, family, subject, source, live, shadows, defaults, frozen)
        variants = self.param_candidates(cycle, family, subject, source, defaults, best_known, baselines, frozen)
        cadence = self.cadence_of(family, subject, live)
        for candidate in baselines + variants:
            candidate["cadence_seconds"] = cadence
        # The window ends `window_end_lag_hours` back: Kalshi lists a market as settled only once
        # it settles, so a window ending now sees a board thinned by the settlements still to come
        # (the engine refuses to peek past them).
        end = math.floor(_epoch(at) / 3600.0) * 3600.0 - float(cfg.get("window_end_lag_hours", 0)) * 3600.0
        window_days = float(dict(cfg.get("family_window_days") or {}).get(family, cfg["window_days"]))
        window = {
            "family": family,
            "start": _iso(end - window_days * 86400.0),
            "end": _iso(end),
            "step_minutes": int(dict(cfg.get("family_step_minutes") or {}).get(family, cfg["step_minutes"])),
            "coinbase_fees": dict(self._cycle_fees),
        }
        summary["window"] = [window["start"], window["end"], window["step_minutes"]]

        workers = max(1, int(cfg["sandboxes"]))
        ready = getattr(manager, "ready_for_run", lambda desk_id: True)
        available = [f"foundry-{index}" for index in range(workers) if ready(f"foundry-{index}")]
        if not available:
            return {**summary, "skipped": "research sandboxes are awaiting execution confirmation or daily capacity"}
        workers = len(available)
        self.progress("test", f"Testing {len(baselines)} baselines and {len(variants)} parameter variants across {workers} Sail sandboxes", cycle=cycle, family=family, strategy=subject)
        ids: "queue.Queue[str]" = queue.Queue()
        for desk_id in available:
            ids.put(desk_id)
        code: list[dict[str, Any]] = []
        asked: dict[str, Any] = {"asked": 0, "valid": 0, "rejected": [], "skipped": None, "cost_usd": "0"}
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="foundry") as pool:
            base_futures = [pool.submit(self._backtest, c, window, ids) for c in baselines]
            variant_futures = [pool.submit(self._backtest, c, window, ids) for c in variants]
            wait_futures(base_futures)
            unsupported = [c for c in baselines if (c.get("report") or {}).get("unsupported")]
            unmeasured = [c for c in baselines if not self.measured(c)]
            if baselines and len(unsupported) == len(baselines):
                for future in variant_futures:
                    future.cancel()
                reason = str((unsupported[0].get("report") or {}).get("unsupported"))[:200]
                asked["skipped"] = f"the engine cannot backtest {subject}: {reason}"
            elif unmeasured:
                # Nothing can qualify without every baseline (`select`), so no model is paid and
                # no sandbox starts another run for this cycle.
                for future in variant_futures:
                    future.cancel()
                first = unmeasured[0]
                asked["skipped"] = f"baseline {first.get('label')} was not measured: {str(first.get('error') or 'no report')[:160]}"
            else:
                self.progress("think", f"Generating {cfg['code_candidates']} code mutations from measured baselines", cycle=cycle, family=family, strategy=subject)
                code, asked = self.code_candidates(cycle, family, subject, source, parent, live, baselines, records, window, problems,
                                                  on_candidate=lambda candidate: pool.submit(self._backtest, candidate, window, ids))
        candidates = baselines + variants + code
        for candidate in candidates:
            if candidate.get("report") is None and not candidate.get("error"):
                candidate["error"] = "not run"

        qualified, reference = self.select(candidates)
        scored = [c for c in candidates if c["kind"] != "baseline" and c.get("evidence") and c["evidence"]["out_of_sample"]["return_on_notional"] is not None]
        best = max(scored, key=lambda c: c["evidence"]["out_of_sample"]["return_on_notional"], default=None)
        winner = qualified[0] if qualified else None
        deployment = None
        if bool(cfg.get("deploy_live")) and live is not None and live.live:
            # The arena (Sept 18, 2026): a candidate earns its forward record with real fills at
            # learning size on the live book, not with modelled fills on a shadow desk. The
            # winner goes; when nothing qualified, the best candidate that beat the baselines
            # goes as an explorer. `prune_explorers` retires the ones that lose.
            # The winner, else the best few candidates that beat the baselines, in order: a
            # candidate that passed its replay can still fail its dry run on the live kit
            # (cycle 157: a favorites mutation raised in `decide`), and the next best takes its place.
            ranked = sorted(scored, key=lambda c: -(_float(c["evidence"]["out_of_sample"]["return_on_notional"]) or 0.0))
            explorers = [c for c in ranked if bool(cfg.get("explorers", True)) and (_float(c["evidence"]["out_of_sample"]["return_on_notional"]) or 0.0) > reference][:3]
            for chosen, role in ([(winner, "winner")] if winner is not None else []) + [(c, "explorer") for c in explorers if c is not winner]:
                deployment = self.deploy_live(chosen, family, subject, live, problems, source=source, role=role, cycle=cycle)
                if deployment is not None:
                    winner = chosen
                    break
        elif winner is not None:
            deployment = self.deploy(winner, family, subject, shadows, problems, source=source)
        self.progress("learn", f"Cycle {cycle}: {sum(1 for c in candidates if self.measured(c))}/{len(candidates)} candidates measured successfully; {len(qualified)} qualified; "
                      + ("winner deployed for forward testing" if deployment else "no new deployment"),
                      cycle=cycle, family=family, strategy=subject, candidates=len(candidates), qualified=len(qualified))
        summary.update(
            {
                "candidates": len(variants) + len(code),
                "baselines": len(baselines),
                "backtested": sum(1 for c in candidates if self.measured(c)),
                "cache_hits": sum(1 for c in candidates if c.get("cache_hit")),
                "fresh_backtests": sum(1 for c in candidates if self.measured(c) and not c.get("cache_hit")),
                "failed_backtests": sum(1 for c in candidates if c.get("error")),
                "qualified": len(qualified),
                "reference_oos_return": reference,
                "best_oos_return": None if best is None else best["evidence"]["out_of_sample"].get("return_on_notional"),
                "best": None if best is None else best["id"],
                "winner": None if deployment is None else deployment["id"],
                "deployed_to": None if deployment is None else deployment["desk_id"],
                "code": {k: asked.get(k) for k in ("asked", "valid", "repaired", "rejected", "skipped")},
                "model_cost_usd": asked.get("cost_usd"),
                "sandbox_seconds": round(sum(_float(c.get("seconds")) or 0.0 for c in candidates), 1),
                "candidates_detail": candidates,
            }
        )
        if winner is not None and deployment is None:
            summary["undeployed"] = winner["id"]
        self.publish_cycle(summary, window, reference, winner, deployment)
        self._report_problems(cycle, problems)
        summary["problems"] = problems[:6]
        return summary

    def _report_problems(self, cycle: int, problems: list[str]) -> None:
        if problems:
            self.alert("warning", f"foundry cycle {cycle}: " + "; ".join(p[:160] for p in problems[:3]))

    # ------------------------------------------------------------------ candidates
    def _candidate(self, cycle: int, kind: str, label: str, strategy: str, subject: str, params: Mapping[str, Any], code: str, **extra: Any) -> dict[str, Any]:
        material = json.dumps({"strategy": strategy, "params": params, "code": _sha(code), "kind": kind}, sort_keys=True, default=str)
        return {
            "id": f"fdy-{cycle}-{hashlib.sha256(material.encode('utf-8')).hexdigest()[:8]}",
            "kind": kind,
            "label": label,
            "strategy": strategy,
            "subject": subject,
            "params": dict(params),
            "code": code,
            "report": None,
            "evidence": None,
            "error": None,
            "seconds": 0.0,
            **extra,
        }

    def baselines(
        self, cycle: int, family: str, subject: str, source: str, live: Any, shadows: list[Any], defaults: Mapping[str, Any], frozen: list[str]
    ) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
        """The live desk's settings and the best shadow's, the best-known settings between them
        (by forward record), and the family's forward record as lines for the model."""
        store = self.store()
        records: list[str] = []
        live_row = store.for_desk(live.id).get(subject) if live is not None else None
        live_params = {k: v for k, v in dict((live_row or {}).get("params") or {}).items() if k not in frozen}
        live_ron = None
        out = [self._candidate(cycle, "baseline", f"live {live.id}" if live is not None else "house defaults", subject, subject, live_params, source)]
        scored: list[tuple[tuple[int, Decimal, Decimal], str, dict[str, Any]]] = []
        for desk in ([live] if live is not None else []) + list(shadows):
            for name, row in sorted(store.for_desk(desk.id).items()):
                if not row.get("enabled", True):
                    continue
                record = self._record(desk.id, name, row.get("promoted_at") or row.get("deployed_at"))
                ron = _return_on_notional(record) if record else None
                settled = int(record.get("settled") or 0)
                if len(records) < 24:
                    records.append(
                        f"- {desk.id}{' (live)' if desk.live else ''}/{name}: params {json.dumps(row.get('params') or {}, sort_keys=True)[:300]}, "
                        f"{record.get('fills', 0)} fills, {settled} settled, {record.get('wins', 0)} won, "
                        f"P&L {record.get('settled_pnl_usd', '0')}, fees {record.get('fees_usd', '0')}, return per $ {ron if ron is not None else 'n/a'}"
                    )
                if name != subject:
                    continue
                if desk is live:
                    live_ron = ron if settled else None
                    continue
                pnl = _dec(record.get("settled_pnl_usd")) or Decimal(0)
                scored.append(((1 if settled and ron is not None else 0, ron or Decimal(0), pnl), desk.id, row))
        best_known = dict(live_params)
        best_known_from = "live"
        if scored:
            scored.sort(key=lambda s: (-s[0][0], -s[0][1], -s[0][2], s[1]))
            (evidence, ron, _), desk_id, row = scored[0]
            params = {k: v for k, v in dict(row.get("params") or {}).items() if k not in frozen}
            if _full(params, defaults) != _full(live_params, defaults):
                out.append(self._candidate(cycle, "baseline", f"shadow {desk_id}", subject, subject, params, source))
            if evidence and (live_ron is None or ron > live_ron):
                best_known, best_known_from = params, f"shadow {desk_id}"
        for candidate in out:
            candidate["best_known"] = best_known_from
        return out, best_known, records

    def param_candidates(
        self, cycle: int, family: str, subject: str, source: str, defaults: Mapping[str, Any], best_known: Mapping[str, Any], baselines: list[dict[str, Any]], frozen: list[str]
    ) -> list[dict[str, Any]]:
        cfg = self.config
        full = {k: v for k, v in _full(best_known, defaults).items() if k not in frozen}
        pool = categorical_pool(self.variants_for(family, subject), defaults)
        drawn = jitter_variants(
            full,
            seed=f"foundry:{cycle}:{family}:{subject}",
            count=int(cfg["param_candidates"]),
            low=float(cfg["jitter_min"]),
            high=float(cfg["jitter_max"]),
            frozen=frozen,
            pool=pool,
            exclude=[{k: v for k, v in _full(b["params"], defaults).items() if k not in frozen} for b in baselines],
        )
        keep = set(best_known)
        out = []
        for params, how in drawn:
            label = f"settings +-{int(how['scale'] * 100)}%" + (f", {how['flip']} flipped" if how.get("flip") else "")
            out.append(self._candidate(cycle, "params", label, subject, subject, _compact(params, defaults, keep), source))
        return out

    def instructions(self, name: str) -> str:
        cfg = self.config
        fees = self._cycle_fees or self.coinbase_fees()
        return (
            f"You are the Foundry of a public, fully automated trading floor: a research loop scheduled every {cfg['interval_minutes']} minutes, "
            "mutates a strategy's code, backtests every mutation on the last days of real Kalshi and Coinbase history, "
            "deploys the out-of-sample winner to a shadow desk and moves it to real money when its forward record holds.\n"
            "Write ONE mutation of the strategy below that you expect to earn more per dollar out of sample. Change how it "
            "trades (pricing, selection, entries, exits, market filters), not only its settings; keep what already works.\n"
            "Rules: a Python module defining decide(kit, params); no files, processes, sockets or network (the kit is the "
            f"only door to data); at most {int(cfg['code_chars'])} characters. Imports: only "
            f"{', '.join(sorted(SAFE_MODULES - {'__future__'}))} (from typing: {', '.join(sorted(SAFE_TYPING))}). "
            "Refused: any attribute that starts with an underscore (type(x).__name__ aside), assigning or deleting any "
            "attribute (keep state in dicts and lists), getattr with a computed name, str.format and format_map (use "
            "f-strings), eval, exec, compile, open, globals, vars, setattr, and dunder methods. "
            f"It runs under the strategy name `{name}`: where it "
            f"recognises its own resting orders by kit.context['open_orders'][i]['strategy'], compare with '{name}'. Size from "
            "params.get('notional_usd') or kit.context['learning_usd']; the floor caps size in any case. The backtest replays "
            "kit.kalshi_markets, kit.kalshi_series, kit.kalshi_market, kit.kalshi_orderbooks (top of book only, sizes None), "
            "kit.bars, kit.quote and kit.products from history at each step; kit.weather is not available.\n"
            f"The kit: {KIT_API}\n"
            "The backtest charges a Kalshi taker fill 0.07 * contracts * p * (1 - p) dollars rounded up to $0.0001 (the venue's "
            "rounding, not to the cent); some Kalshi series also charge maker fees. "
            f"Coinbase {float(fees['maker']) * 100:g}% maker and {float(fees['taker']) * 100:g}% taker. "
            "Read kit.context['fee_rates']['coinbase'] for the exact rates used by this replay. "
            "Require the target move to exceed both entry and exit fees plus spread/slippage; a dip alone is not an edge.\n"
            f"How it is judged: the closed positions are split in time; on the last third it needs at least "
            f"{int(cfg['min_oos_trades'])} positions ({int(cfg['min_trades'])} trades in all), a return on notional above the "
            f"best baseline's by {cfg['margin']}, and a 95% confidence lower bound on mean P&L per position above "
            f"{cfg['min_ci_lower']}. Fitting the in-sample period does not help.\n"
            f"Reply with JSON only: {{\"name\": \"{name}\", \"code\": \"<the whole module>\", \"params\": {{...}}, "
            "\"hypothesis\": \"one sentence: what you changed and why it should earn more out of sample\"}. params holds "
            "overrides of the module's DEFAULTS as plain strings, numbers, booleans or lists (no null, no nested objects). "
            f"Keep DEFAULTS a literal dict, and keep the values of {', '.join(str(k) for k in (cfg.get('frozen_params') or []))} "
            "exactly as the source has them (or leave them out): they are the floor's and a change is refused."
        )

    def packet(
        self, *, family: str, subject: str, name: str, source: str, window: Mapping[str, Any], baselines: list[dict[str, Any]], records: list[str], index: int, count: int
    ) -> str:
        parts = [
            f"# Family {family}, strategy `{subject}`; your mutation is `{name}` (candidate {index + 1} of {count})",
            f"Backtest window {window['start']} to {window['end']}, a decision every {window['step_minutes']} minutes.",
            f"Explore {DIRECTIONS[index % len(DIRECTIONS)]}.",
            "## Baseline backtests (the settings the family trades today)",
        ]
        for candidate in baselines:
            parts.append(self._report_line(candidate))
        parts.append("## Forward record since each setting was dealt (real prices; shadow desks are scored, live desks trade money)")
        parts.append("\n".join(records) if records else "(no strategy records yet)")
        if self._result_cache:
            try:
                lessons = self._result_cache.lessons(subject)
            except Exception:
                lessons = []
            if lessons:
                parts.append("## Persistent research memory\nThese are prior search results, NOT independent validation. "
                             "Avoid repeating failed ideas without a concrete causal correction. Explain what your hypothesis learns from this record. "
                             "Only fresh forward outcomes can establish that an adaptive search generalizes.\n" + json.dumps(lessons, default=str)[:10000])
        # The Firm Mind: rules measured across every desk's settled trades, with their evidence. A
        # mutation that heeds them starts from what the floor has already paid to learn.
        try:
            from .mind import rules_for_family

            firm = rules_for_family(family)
        except Exception:
            firm = ""
        if firm:
            parts.append("## What the firm has measured (every desk's settled trades; evidence, not instructions)\n" + firm)
        clipped = source[:16000]
        parts.append(f"## Source of `{subject}` ({len(source)} characters{', clipped' if len(source) > len(clipped) else ''})\n```python\n{clipped}\n```")
        return "\n\n".join(parts)

    @staticmethod
    def _report_line(candidate: Mapping[str, Any]) -> str:
        report = candidate.get("report") or {}
        evidence = candidate.get("evidence") or {}
        ins, oos = evidence.get("in_sample") or {}, evidence.get("out_of_sample") or {}
        line = (
            f"- {candidate.get('label')} params {json.dumps(candidate.get('params') or {}, sort_keys=True)[:400]}: "
            f"{report.get('trades')} trades, {report.get('settled')} settled, {report.get('wins')} won, P&L {report.get('pnl_usd')} "
            f"after {report.get('fees_usd')} fees on {report.get('notional_usd')} notional, max drawdown {report.get('max_drawdown_usd')}; "
            f"in sample {ins.get('trades')} positions, return {ins.get('return_on_notional')}, CI {ins.get('ci95_mean_pnl')}; "
            f"out of sample {oos.get('trades')} positions, return {oos.get('return_on_notional')}, CI {oos.get('ci95_mean_pnl')}"
        )
        if report.get("unsupported"):
            line += f"; unsupported: {str(report['unsupported'])[:200]}"
        if candidate.get("error") and not report:
            line += f"; failed: {str(candidate['error'])[:200]}"
        notes = [str(n)[:160] for n in (report.get("notes") or [])[:3]]
        return line + (f"; notes: {' | '.join(notes)}" if notes else "")

    def code_candidates(
        self,
        cycle: int,
        family: str,
        subject: str,
        source: str,
        parent: Any,
        live: Any,
        baselines: list[dict[str, Any]],
        records: list[str],
        window: Mapping[str, Any],
        problems: list[str],
        *, on_candidate: Callable[[dict[str, Any]], Any] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Ask the model for `code_candidates` mutations, validated before any backtest."""
        cfg = self.config
        count = max(0, int(cfg["code_candidates"]))
        asked: dict[str, Any] = {"asked": 0, "valid": 0, "rejected": [], "skipped": None, "cost_usd": "0"}
        if count == 0:
            return [], asked
        if self.provider is None:
            asked["skipped"] = "no model provider"
            return [], asked
        budget = _dec(cfg["budget_usd_per_day"]) or Decimal(0)
        try:
            spent = _dec(self.provider.spent_today(BUDGET_DESK)) or Decimal(0)
        except Exception:
            spent = Decimal(0)
        if spent >= budget:
            asked["skipped"] = f"model budget used: {spent} of {budget} today"
            return [], asked
        root = base_name(subject)[: 40 - len(f"_f{cycle}_{count}")]
        cadence = self.cadence_of(family, subject, live)
        names = [f"{root}_f{cycle}" if k == 0 else f"{root}_f{cycle}_{k + 1}" for k in range(count)]
        profiles = cfg.get("code_profiles") or [cfg["profile"]]
        if not isinstance(profiles, list) or not profiles or not all(isinstance(p, str) for p in profiles):
            profiles = [cfg["profile"]]
        selected_profiles = [profiles[(cycle + index) % len(profiles)] for index in range(count)]
        efforts = cfg.get("profile_reasoning_effort") or {}

        def ask(index: int) -> tuple[int, Any, str | None]:
            name = names[index]
            try:
                response = self.provider.respond(
                    selected_profiles[index],
                    [
                        {"role": "system", "content": self.instructions(name)},
                        {"role": "user", "content": self.packet(family=family, subject=subject, name=name, source=source, window=window, baselines=baselines, records=records, index=index, count=count)},
                    ],
                    tools=None,
                    desk_id=BUDGET_DESK,
                    session_id=f"foundry-{cycle}",
                    request_key=f"foundry:{cycle}:{subject}:{index}",
                    reasoning_effort=efforts.get(selected_profiles[index], cfg["reasoning_effort"]),
                    max_output_tokens=int(cfg["max_output_tokens"]),
                    desk_cap_usd_per_day=cfg["budget_usd_per_day"],
                )
            except Exception as exc:
                return index, None, f"{type(exc).__name__}: {str(exc)[:160]}"
            return index, response, None

        # Sept 18, 2026: a model call that never answered held a cycle for an hour (the wait
        # had no end). After `model_wait_seconds` the cycle goes on with the answers it has;
        # the abandoned calls finish in the background at the provider's own idempotent pace.
        deadline = time.monotonic() + float(cfg.get("model_wait_seconds", 600))

        def answers():
            pool = ThreadPoolExecutor(max_workers=count, thread_name_prefix="foundry-model")
            pending = {pool.submit(ask, index) for index in range(count)}
            started = time.monotonic()
            try:
                while pending:
                    done, pending = wait_futures(pending, timeout=30, return_when=FIRST_COMPLETED)
                    if not done:
                        self.progress("think", f"{len(pending)}/{count} model jobs still running; {round(time.monotonic() - started)}s elapsed. Completed candidates test independently.",
                                      cycle=cycle, family=family, strategy=subject, pending_models=len(pending))
                    for future in done:
                        yield future.result()
                    if pending and time.monotonic() > deadline:
                        self.progress("think", f"{len(pending)}/{count} model jobs abandoned after {round(time.monotonic() - started)}s; the cycle goes on with {count - len(pending)} answer(s)",
                                      cycle=cycle, family=family, strategy=subject, pending_models=len(pending))
                        for future in pending:
                            future.cancel()
                        break
            finally:
                pool.shutdown(wait=False)
        out: list[dict[str, Any]] = []
        cost = Decimal(0)
        result_lock = threading.Lock()
        def consume(index, response, failure):
            nonlocal cost
            with result_lock:
                asked["asked"] += 1
            name = names[index]
            if failure is not None:
                if "Budget" in failure:
                    asked["skipped"] = f"model budget: {failure[:120]}"
                else:
                    problems.append(f"model call for {name} failed: {failure}")
                    asked["rejected"].append(f"{name}: no answer")
                return
            with result_lock:
                cost += _dec(getattr(response, "cost_usd", None)) or Decimal(0)
            try:
                spec, hypothesis = self.validate_code(parse_reply(getattr(response, "output_text", "") or ""), name, parent, cadence, source=source)
            except LabError as exc:
                # Repair only the contract, not the measured result: the repaired program still
                # faces the identical compiler, sandbox and out-of-sample admission gates.
                if not cfg.get("repair_invalid_code", False):
                    asked["rejected"].append(f"{name}: {str(exc)[:160]}")
                    return
                try:
                    repair = self.provider.respond(
                        selected_profiles[index],
                        [{"role": "system", "content": self.instructions(name)},
                         {"role": "user", "content": "Repair this rejected candidate. Preserve its hypothesis; return one valid JSON object, no commentary. "
                          f"Validation error: {str(exc)[:400]}\nOriginal candidate:\n{str(getattr(response, 'output_text', '') or '')[:24000]}"}],
                        tools=None, desk_id=BUDGET_DESK, session_id=f"foundry-{cycle}",
                        request_key=f"foundry:{cycle}:{subject}:repair:{index}",
                        reasoning_effort=efforts.get(selected_profiles[index], cfg["reasoning_effort"]), max_output_tokens=int(cfg["max_output_tokens"]),
                        desk_cap_usd_per_day=cfg["budget_usd_per_day"],
                    )
                    with result_lock:
                        asked["asked"] += 1
                        cost += _dec(getattr(repair, "cost_usd", None)) or Decimal(0)
                    spec, hypothesis = self.validate_code(parse_reply(getattr(repair, "output_text", "") or ""), name, parent, cadence, source=source)
                    with result_lock:
                        asked["repaired"] = asked.get("repaired", 0) + 1
                except Exception as repair_error:
                    asked["rejected"].append(f"{name}: repair failed: {str(repair_error)[:160]}")
                    return
            candidate = self._candidate(cycle, "code", f"model mutation {index + 1}", name, subject, spec["params"], spec["code"], hypothesis=hypothesis, cadence_seconds=spec["cadence_seconds"], profile=selected_profiles[index])
            with result_lock:
                asked["valid"] += 1
                out.append(candidate)
            if self._result_cache:
                try:
                    self._result_cache.remember(candidate, window)
                except Exception:
                    pass
            self.progress("candidate", f"{name}: validated; queued for an out-of-sample backtest", cycle=cycle, family=family, strategy=name)
            if on_candidate is not None:
                on_candidate(candidate)
        # Validation/repair is independent per answer. A slow compiler-repair call must not
        # prevent another already-completed model's valid candidate from reaching the tests.
        consumers = ThreadPoolExecutor(max_workers=count, thread_name_prefix="foundry-repair")
        try:
            pending = [consumers.submit(consume, *answer) for answer in answers()]
            for future in pending:
                try:
                    future.result(timeout=max(30.0, deadline - time.monotonic()))
                except FuturesTimeout:
                    self.progress("think", "a candidate's validation or repair did not finish in time; the cycle goes on without it", cycle=cycle, family=family, strategy=subject)
        finally:
            consumers.shutdown(wait=False)
        asked["cost_usd"] = format(cost, "f")
        return sorted(out, key=lambda candidate: candidate["label"]), asked

    def validate_code(self, data: Any, name: str, parent: Any, cadence: int, *, source: str | None = None) -> tuple[dict[str, Any], str]:
        """The lab's own strategy validation, a compile, `check_strategy_code`, and the frozen
        settings, before a single backtest.

        A candidate's `DEFAULTS` may not move a frozen setting away from `source`'s (the code it
        mutates): until Sept 16, 2026 the freeze filtered only the params a model sent, and a
        mutation that wrote `max_new: 40` and `no_max: 0.999` into its own defaults carried them
        onto the live desk."""
        if not isinstance(data, Mapping):
            raise LabError("the reply is not a JSON object")
        hypothesis = str(data.get("hypothesis") or "").strip()
        if not hypothesis:
            raise LabError("the reply has no hypothesis")
        frozen = set(str(k) for k in (self.config.get("frozen_params") or []))
        params = data.get("params") if data.get("params") is not None else {}
        if not isinstance(params, Mapping):
            raise LabError("params must be an object")
        params = {k: v for k, v in params.items() if v is not None and k not in frozen}
        change = {"strategy": {"name": name, "cadence_seconds": cadence, "params": params, "code": data.get("code")}}
        spec = validate_change(change, parent, {"strategy_code_chars": int(self.config["code_chars"])})["strategy"]
        try:
            compile(spec["code"], f"{name}.py", "exec")
        except (SyntaxError, ValueError) as exc:
            raise LabError(f"the code does not compile: {str(exc)[:120]}") from None
        check_strategy_code(spec["code"])
        if source is not None:
            parent_defaults = literal_defaults(source)
            if _defines_defaults(source) and parent_defaults and not literal_defaults(spec["code"]):
                raise LabError("DEFAULTS must stay a literal dict, as in the code it mutates")
            mine = literal_defaults(spec["code"])
            for key in sorted(frozen):
                if key in mine and (key not in parent_defaults or mine[key] != parent_defaults[key]):
                    was = parent_defaults.get(key, "absent")
                    raise LabError(f"DEFAULTS[{key!r}] is frozen: {was!r} in the code it mutates, {mine[key]!r} here")
        return spec, hypothesis[:300]

    # ------------------------------------------------------------------ backtests
    def min_interval(self) -> float:
        """Seconds between one sandbox's requests to a venue. The sandboxes run side by side
        with caches of their own, so the floor's 0.15 s (under seven a second) is shared among
        them: eight sandboxes at 0.15 s each asked Kalshi for 53 a second on a cold cache."""
        configured = _float(self.config.get("history_min_interval"))
        if configured is not None and configured > 0:
            return configured
        return round(0.15 * max(1, int(self.config["sandboxes"])), 3)

    def spec_for(self, candidate: Mapping[str, Any], window: Mapping[str, Any]) -> dict[str, Any]:
        cfg = self.config
        fees = window.get("coinbase_fees") or self.coinbase_fees()
        return {
            "strategy": candidate["strategy"],
            "code": candidate["code"],
            "params": dict(candidate.get("params") or {}),
            "start": window["start"],
            "end": window["end"],
            "step_minutes": int(window["step_minutes"]),
            "learning_usd": cfg["learning_usd"],
            "fill_model": cfg["fill_model"],
            "max_markets": int(dict(cfg.get("family_max_markets") or {}).get(str(candidate.get("family") or window.get("family") or ""), cfg["max_markets"])),
            "seed": int(cfg["seed"]),
            "coinbase_maker_fee": float(fees["maker"]),
            "coinbase_taker_fee": float(fees["taker"]),
        }

    def coinbase_fees(self) -> dict[str, Any]:
        """Authenticated current rates in production; explicit snapshot for offline research.

        Rates belong in the spec/cache key, never in candidate-editable params. A production
        lookup failure must not silently price experiments using an obsolete cheaper tier.
        """
        reader = getattr(getattr(self.strategies, "service", None), "venue_fee_rates", None)
        if not callable(reader):
            return {"maker": "0.005", "taker": "0.009", "source": "offline snapshot 2026-09-17"}
        rates = (reader() or {}).get("coinbase") or {}
        values = {side: _float(rates.get(side)) for side in ("maker", "taker")}
        age = _float(rates.get("age_seconds"))
        if age is None or not 0 <= age <= 900 or any(v is None or not 0 <= v <= 0.1 for v in values.values()):
            raise ValueError("current Coinbase fees unavailable; crypto research cannot be scored")
        return {**values, "source": "authenticated account tier"}

    def _backtest(self, candidate: dict[str, Any], window: Mapping[str, Any], ids: "queue.Queue[str]") -> dict[str, Any]:
        """One backtest in one free sandbox. Fills in the candidate's report and evidence."""
        desk = None
        try:
            spec = self.spec_for(candidate, window)
            cache = self._result_cache
            cache_key = cache.key(spec, float(self.config["split_fraction"])) if cache else None
            cached = None
            if cache:
                try:
                    cached = cache.get(cache_key)
                except Exception:
                    pass  # A cache failure never prevents a fresh experiment.
            if cached is not None:
                candidate.update(report=cached, evidence=self.evidence(cached), cache_hit=True, seconds=0.0)
                return candidate
            desk = ids.get()
            manager = self.sandboxes()
            token = secrets.token_hex(16)
            code = runner_code(spec, fraction=float(self.config["split_fraction"]), token=token, min_interval=self.min_interval())
            run = manager.run(desk, code, purpose=f"foundry backtest {candidate['id']} ({candidate['strategy']})", timeout=int(self.config["backtest_timeout_seconds"]))
            candidate["sandbox"] = desk
            candidate["seconds"] = _float(getattr(run, "seconds", 0)) or 0.0
            report = parse_result(getattr(run, "stdout", ""), token)
            if report is None:
                candidate["error"] = f"exit {getattr(run, 'exit_code', '?')}: no result line ({str(getattr(run, 'stdout', ''))[-160:]})"
                return candidate
            candidate["report"] = report
            candidate["evidence"] = self.evidence(report)
            errors = _int(report.get("errors"))
            if getattr(run, "exit_code", 0) != 0:
                candidate["error"] = f"sandbox exit {getattr(run, 'exit_code', '?')}; report is not a confirmed successful run"
            elif report.get("unsupported"):
                candidate["error"] = f"unsupported: {str(report['unsupported'])[:200]}"
            elif errors is None or errors > 0:
                # A failed history request leaves markets unpriced, so the run did not see the
                # data its rivals saw; a strategy that raised did not run the whole window.
                notes = "; ".join(str(n)[:120] for n in (report.get("notes") or [])[:2])
                candidate["error"] = f"{'unknown' if errors is None else errors} engine errors" + (f": {notes}" if notes else "")
            if cache and not candidate.get("error") and getattr(run, "exit_code", 0) == 0:
                try:
                    cache.put(cache_key, report)
                except Exception:
                    pass
        except Exception as exc:
            candidate["error"] = f"{type(exc).__name__}: {str(exc)[:160]}"
        finally:
            if desk is not None:
                ids.put(desk)
            if self._result_cache:
                try:
                    self._result_cache.remember(candidate, window)
                except Exception:
                    pass
            report = candidate.get("report") or {}
            self.progress("tested", f"{candidate['strategy']}: " + (str(candidate['error'])[:180] if candidate.get("error") else
                          f"{report.get('trades', 0)} trades, simulated net P&L {report.get('pnl_usd', 'unknown')}"),
                          candidate_id=candidate["id"], strategy=candidate["strategy"], cache_hit=bool(candidate.get("cache_hit")), seconds=round(float(candidate.get("seconds") or 0), 2))
        return candidate

    def evidence(self, report: Mapping[str, Any]) -> dict[str, Any]:
        """Total trades and the in-sample and out-of-sample halves, as plain numbers."""
        split = report.get("split")
        if not (isinstance(split, Mapping) and isinstance(split.get("out_of_sample"), Mapping)):
            split = split_evidence(report.get("trade_pnls") or [], report.get("notional_usd"), float(self.config["split_fraction"]))

        def plain(part: Any) -> dict[str, Any]:
            part = part if isinstance(part, Mapping) else {}
            ci = part.get("ci95_mean_pnl")
            bounds = [_float(ci[0]), _float(ci[1])] if isinstance(ci, (list, tuple)) and len(ci) == 2 else None
            if bounds is not None and None in bounds:
                bounds = None
            return {"trades": _int(part.get("trades")) or 0, "pnl_usd": _float(part.get("pnl_usd")), "return_on_notional": _float(part.get("return_on_notional")), "ci95_mean_pnl": bounds}

        total = _int(report.get("trades"))
        if total is None:
            total = len(report.get("trade_pnls") or []) or (_int(report.get("trade_pnls_dropped")) or 0)
        return {"trades": total, "in_sample": plain(split.get("in_sample")), "out_of_sample": plain(split.get("out_of_sample"))}

    # ------------------------------------------------------------------ selection
    def select(self, candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], float]:
        """The candidates that qualify on out-of-sample evidence, best first, and the baseline
        return they had to beat. In-sample numbers are never read here."""
        references = []
        baselines = [c for c in candidates if c["kind"] == "baseline"]
        unmeasured = [c for c in baselines if not self.measured(c)]
        for candidate in baselines:
            if not self.measured(candidate):
                continue
            oos = candidate["evidence"]["out_of_sample"]
            if oos["trades"] > 0 and oos["return_on_notional"] is not None:
                references.append(oos["return_on_notional"])
        # A baseline that did not trade in the window sets the bar at zero. Every baseline must be
        # measured: until Sept 16, 2026 a live baseline that timed out left the bar at the shadow's,
        # and settings that earned less than the live desk's own qualified.
        reference = max(references) if references else 0.0
        if not baselines:
            missing = "no baseline was measured to beat"
        elif unmeasured:
            missing = f"no bar: baseline {unmeasured[0].get('label')} was not measured ({str(unmeasured[0].get('error') or 'no report')[:120]})"
        else:
            missing = None
        qualified = []
        for candidate in candidates:
            if candidate["kind"] == "baseline":
                continue
            ok, verdict = self.qualifies(candidate, reference) if missing is None else (False, missing)
            candidate["verdict"] = verdict
            if ok:
                qualified.append(candidate)
        qualified.sort(key=lambda c: (-c["evidence"]["out_of_sample"]["return_on_notional"], -c["evidence"]["out_of_sample"]["ci95_mean_pnl"][0], c["id"]))
        return qualified, reference

    @staticmethod
    def measured(candidate: Mapping[str, Any]) -> bool:
        """A run that finished with evidence, no error and no engine errors."""
        report = candidate.get("report")
        return bool(
            isinstance(report, Mapping) and candidate.get("evidence") and not candidate.get("error")
            and not report.get("unsupported") and _int(report.get("errors")) == 0
        )

    def qualifies(self, candidate: Mapping[str, Any], reference: float) -> tuple[bool, str]:
        cfg = self.config
        if candidate.get("error"):
            return False, str(candidate["error"])[:200]
        evidence = candidate.get("evidence")
        if not evidence:
            return False, "no backtest evidence"
        if _int((candidate.get("report") or {}).get("errors")) != 0:
            return False, f"{(candidate.get('report') or {}).get('errors')} engine errors"
        oos = evidence["out_of_sample"]
        if int(evidence["trades"]) < int(cfg["min_trades"]):
            return False, f"{evidence['trades']} trades, {cfg['min_trades']} needed"
        if int(oos["trades"]) < int(cfg["min_oos_trades"]):
            return False, f"{oos['trades']} out-of-sample positions, {cfg['min_oos_trades']} needed"
        ron = oos["return_on_notional"]
        if ron is None or ron <= reference + float(cfg["margin"]):
            return False, f"out-of-sample return {_fmt(ron)} does not beat {reference:+.3f} by {cfg['margin']}"
        ci = oos["ci95_mean_pnl"]
        if ci is None or ci[0] <= float(cfg["min_ci_lower"]):
            return False, f"out-of-sample 95% lower bound {_fmt(ci[0] if ci else None, '+.4f')} is not above {cfg['min_ci_lower']}"
        return True, "qualified"

    # ------------------------------------------------------------------ shadow deployment
    def _code_sha(self, manager: Any, desk_id: str, name: str, row: Mapping[str, Any] | None) -> str | None:
        """The hash of the code a desk runs under `name`: its toolbox file when it can be read
        (a desk may edit the file without redeploying), else its strategy row's."""
        files = None
        if manager is not None and hasattr(manager, "toolbox_files"):
            try:
                files = manager.toolbox_files(desk_id)
            except Exception:
                files = None
        if isinstance(files, Mapping) and isinstance(files.get(f"{name}.py"), str):
            return _sha(files[f"{name}.py"])
        return (row or {}).get("code_sha256")

    def target_desk(self, winner: Mapping[str, Any], shadows: list[Any], at: str) -> Any:
        """The family's worst-performing shadow desk that can take the winner: lowest settled
        strategy P&L, then lowest equity. A desk still proving an earlier candidate is spared.
        Settings go only to a desk that runs exactly the code they were backtested with."""
        store = self.store()
        manager = self.sandboxes()
        deployments = dict(self.state().get("deployments") or {})
        protect = float(self.config["protect_hours"]) * 3600.0
        now = _epoch(at)
        protected = {
            d.get("desk_id") for d in deployments.values()
            if d.get("status") == "shadow" and now - _epoch(d.get("deployed_at")) < protect
        }
        rows = {m.id: store.for_desk(m.id) for m in shadows if not m.live}
        pool = [m for m in shadows if not m.live and m.id not in protected]
        name = winner["strategy"]
        if winner["kind"] == "params":
            sha = _sha(winner.get("code"))
            # Until Sept 16, 2026 a desk running other code under the same name was taken when
            # none ran the backtested code, and its forward record then spoke for code never tested.
            pool = [
                m for m in pool
                if name in rows[m.id] and rows[m.id][name].get("enabled", True)
                and self._code_sha(manager, m.id, name, rows[m.id][name]) == sha
            ]
        else:
            limit = int(dict(getattr(self.strategies, "config", {}) or {}).get("max_per_desk", 3))
            pool = [
                m for m in pool
                if sum(1 for r in rows[m.id].values() if not r.get("foundry_code")) < limit
                # Never over a desk's own strategy of the same name (a house starter, say).
                and (name not in rows[m.id] or rows[m.id][name].get("foundry_code"))
            ]
        if not pool:
            return None

        def score(desk: Any) -> tuple[Decimal, Decimal, str]:
            pnl = Decimal(0)
            for strategy, row in rows[desk.id].items():
                if row.get("enabled", True):
                    record = self._record(desk.id, strategy, row.get("promoted_at") or row.get("deployed_at"))
                    pnl += _dec(record.get("settled_pnl_usd")) or Decimal(0)
            equity = self._equity(desk.id)
            return pnl, equity if equity is not None else Decimal("Infinity"), desk.id

        return min(pool, key=score)

    def deploy(self, winner: dict[str, Any], family: str, subject: str, shadows: list[Any], problems: list[str], *, source: str | None = None) -> dict[str, Any] | None:
        """Put the winner on a shadow desk now. Never a live desk. `source` is the code of the
        strategy the winner was measured against (the subject's)."""
        at = self.now()
        desk = self.target_desk(winner, shadows, at)
        if desk is None and winner["kind"] == "params":
            # No shadow desk runs this strategy (a live desk's own, or an adopted candidate): the
            # settings go out with the live desk's code, installed on the worst shadow desk.
            carried = {**winner, "kind": "code"}
            desk = self.target_desk(carried, shadows, at)
            winner = carried if desk is not None else winner
        if desk is None:
            problems.append(f"{winner['id']} qualified but no shadow desk of {family} can take it")
            return None
        if desk.live:  # belt and braces: the target list never holds a live desk
            return None
        store = self.store()
        manager = self.sandboxes()
        frozen = [str(k) for k in (self.config.get("frozen_params") or [])]
        fid, name = winner["id"], winner["strategy"]
        source = winner.get("code") if source is None else source
        oos = winner["evidence"]["out_of_sample"]
        note = f"foundry {fid}: out-of-sample {oos['trades']} positions, {_fmt(oos['return_on_notional'])} per $"
        try:
            if winner["kind"] == "params":
                own = dict((store.for_desk(desk.id).get(name) or {}).get("params") or {})
                params = {**{k: v for k, v in winner["params"].items() if k not in frozen}, **{k: own[k] for k in frozen if k in own}}
                store.update(desk.id, name, params=params, promoted_at=at, note=note[:200], foundry_id=fid)
                code_sha = _sha(winner.get("code"))
            else:
                # Size, counts and price guards are the parent's (its row over its code's
                # DEFAULTS), whatever the candidate's own defaults say.
                parent_row = store.for_desk(desk.id).get(subject) or {}
                params = {**{k: v for k, v in dict(winner["params"]).items() if k not in frozen}, **pinned_frozen(source, parent_row.get("params"), frozen)}
                existed = name in store.for_desk(desk.id)
                for other, row in list(store.for_desk(desk.id).items()):
                    if row.get("foundry_code") and other != name:
                        store.remove(desk.id, other)
                        self._remove_file(manager, desk.id, other)
                        self._deployment(row.get("foundry_id"), status="replaced", ended_at=at)
                try:
                    self.strategies.install(
                        desk,
                        {"name": name, "code": winner["code"], "cadence_seconds": int(winner.get("cadence_seconds") or 600), "params": params},
                        note=f"foundry {fid}",
                    )
                except Exception:
                    if not existed:
                        self._remove_file(manager, desk.id, name)
                    raise
                store.update(desk.id, name, foundry_id=fid, foundry_code=True, promoted_at=at)
                code_sha = _sha(winner["code"])
        except Exception as exc:
            problems.append(f"{fid} not deployed to {desk.id}: {type(exc).__name__}: {str(exc)[:160]}")
            return None
        record = {
            "id": fid,
            "family": family,
            "subject": subject,
            "strategy": name,
            "kind": winner["kind"],
            "desk_id": desk.id,
            "deployed_at": at,
            "status": "shadow",
            "params": params,
            "code_sha256": code_sha,
            # The parent's code when it was measured: a live desk that changed it since has moved on.
            "subject_sha256": _sha(source) if source else None,
            "cadence_seconds": int(winner.get("cadence_seconds") or 0) or None,
            "trades": winner["evidence"]["trades"],
            "oos_trades": oos["trades"],
            "oos_return": oos["return_on_notional"],
            "oos_ci_lower": oos["ci95_mean_pnl"][0],
            "hypothesis": winner.get("hypothesis"),
        }
        self._add_deployment(record)
        lines = [
            f"foundry {fid} ({winner['label']}) deployed to shadow desk {desk.id} as {name}",
            f"backtest: {winner['evidence']['trades']} trades; out of sample {oos['trades']} positions, return {_fmt(oos['return_on_notional'])} per $, "
            f"95% CI on mean P&L [{_fmt(oos['ci95_mean_pnl'][0], '+.4f')}, {_fmt(oos['ci95_mean_pnl'][1], '+.4f')}]",
            f"params: {json.dumps(params, sort_keys=True)[:800]}",
        ]
        if winner.get("hypothesis"):
            lines.append(f"hypothesis: {winner['hypothesis']}")
        lines.append(f"live after {self.config['min_forward_settled']} positions opened and settled here at P&L after fees >= 0, and a favorites record that passes the evidence gate")
        self.publish_desk(desk, name, f"foundry-{fid}-shadow", at, f"foundry {fid}: {name} on shadow desk {desk.id}", lines, code_sha, winner.get("seconds"))
        return record

    # ------------------------------------------------------------------ the arena: live explorers
    def explorer_rows(self, desk_id: str) -> dict[str, dict[str, Any]]:
        return {name: row for name, row in self.store().for_desk(desk_id).items() if row.get("foundry_explorer")}

    def deploy_live(self, candidate: dict[str, Any], family: str, subject: str, live: Any, problems: list[str], *, source: str | None, role: str, cycle: int) -> dict[str, Any] | None:
        """Install a candidate on the family's live desk as its own strategy row, at learning
        size (a row with no record sizes at `learning_usd`; `Strategies.size_cap` ramps it on its
        own settled record and the family's pooled one). A params candidate becomes a code row
        under a Foundry name, so its record is its own and the live desk's house row is untouched.
        At most `max_explorers_per_desk` rows: the one with the worst record makes room."""
        at = self.now()
        store = self.store()
        manager = self.sandboxes()
        cfg = self.config
        frozen = [str(k) for k in (cfg.get("frozen_params") or [])]
        fid = candidate["id"]
        source = candidate.get("code") if source is None else source
        code = candidate.get("code") or source
        if not code:
            problems.append(f"{fid} has no code to deploy")
            return None
        if candidate["kind"] == "params":
            name = f"{base_name(subject)}_f{cycle}_{100 + int(str(fid).rsplit('-', 1)[-1][:4], 16) % 900}"
        else:
            name = str(candidate["strategy"])
        parent_row = store.for_desk(live.id).get(subject) or {}
        params = {**{k: v for k, v in dict(candidate.get("params") or {}).items() if k not in frozen}, **pinned_frozen(code, parent_row.get("params"), frozen)}
        limit = max(1, int(cfg.get("max_explorers_per_desk", 4)))
        rows = self.explorer_rows(live.id)
        if name not in rows and len(rows) >= limit:
            # The explorer with the least to show for itself leaves: lowest settled P&L after
            # fees since it was dealt, then the oldest.
            def worth(item: tuple[str, dict[str, Any]]) -> tuple[Decimal, str]:
                other, row = item
                record = self._record(live.id, other, row.get("promoted_at") or row.get("deployed_at"), opened_since=True)
                net = (_dec(record.get("settled_pnl_usd")) or Decimal(0)) - (_dec(record.get("fees_usd")) or Decimal(0))
                return net, str(row.get("promoted_at") or "")
            gone, gone_row = min(rows.items(), key=worth)
            store.remove(live.id, gone)
            self._remove_file(manager, live.id, gone)
            self._deployment(gone_row.get("foundry_id"), status="replaced", ended_at=at, reason=f"made room for {fid}")
        oos = candidate["evidence"]["out_of_sample"]
        note = f"foundry {fid} {role}: out-of-sample {oos['trades']} positions, {_fmt(oos['return_on_notional'])} per $; learning size on the live book"
        try:
            self.strategies.install(live, {"name": name, "code": code, "cadence_seconds": int(candidate.get("cadence_seconds") or 600), "params": params}, note=note[:200])
            store.update(live.id, name, foundry_id=fid, foundry_code=True, foundry_explorer=True, promoted_at=at, note=note[:200])
        except Exception as exc:
            self._remove_file(manager, live.id, name)
            problems.append(f"{fid} not deployed to {live.id}: {type(exc).__name__}: {str(exc)[:160]}")
            return None
        code_sha = _sha(code)
        record = {
            "id": fid, "family": family, "subject": subject, "strategy": name, "kind": candidate["kind"], "role": role,
            "desk_id": live.id, "live_desk_id": live.id, "deployed_at": at, "status": "live", "params": params, "code_sha256": code_sha,
            "subject_sha256": _sha(source) if source else None, "cadence_seconds": int(candidate.get("cadence_seconds") or 0) or None,
            "trades": candidate["evidence"]["trades"], "oos_trades": oos["trades"], "oos_return": oos["return_on_notional"],
            "oos_ci_lower": oos["ci95_mean_pnl"][0], "hypothesis": candidate.get("hypothesis"),
        }
        self._add_deployment(record)
        lines = [
            f"foundry {fid} ({candidate['label']}) deployed to live desk {live.id} as {name} ({role}, learning size)",
            f"backtest: {candidate['evidence']['trades']} trades; out of sample {oos['trades']} positions, return {_fmt(oos['return_on_notional'])} per $, "
            f"95% CI on mean P&L [{_fmt(oos['ci95_mean_pnl'][0], '+.4f')}, {_fmt(oos['ci95_mean_pnl'][1], '+.4f')}]",
            f"params: {json.dumps(params, sort_keys=True)[:800]}",
        ]
        if candidate.get("hypothesis"):
            lines.append(f"hypothesis: {candidate['hypothesis']}")
        lines.append(f"size ramps on its own real record; retired after {cfg['min_forward_settled']} settled positions at a loss after fees, or {cfg['forward_max_hours']} hours without fills")
        self.publish_desk(live, name, f"foundry-{fid}-live", at, f"foundry {fid}: {name} on live desk {live.id} at learning size", lines, code_sha, candidate.get("seconds"))
        return record

    def prune_explorers(self, manifests: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Retire every live explorer whose forward record says no: `min_forward_settled`
        positions opened and settled since it was dealt at a loss after fees, or
        `forward_max_hours` gone by with fewer than two fills. A winner at learning size stays and
        `Strategies.size_cap` grows it."""
        cfg = self.config
        store = self.store()
        manager = self.sandboxes()
        need = int(cfg["min_forward_settled"])
        horizon = float(cfg["forward_max_hours"]) * 3600.0
        out: list[dict[str, Any]] = []
        for desk in [m for m in manifests.values() if getattr(m, "live", False)]:
            for name, row in sorted(self.explorer_rows(desk.id).items()):
                at = self.now()
                since = row.get("promoted_at") or row.get("deployed_at")
                record = self._record(desk.id, name, since, opened_since=True)
                settled = int(record.get("settled") or 0)
                fills = int(record.get("fills") or 0)
                net = (_dec(record.get("settled_pnl_usd")) or Decimal(0)) - (_dec(record.get("fees_usd")) or Decimal(0))
                age = _epoch(at) - _epoch(since)
                reason = None
                if settled >= need and net < 0:
                    reason = f"{settled} settled at {net:+.2f} after fees"
                elif age > horizon and fills < 2:
                    reason = f"{fills} fills in {age / 3600:.0f} hours"
                if reason is None:
                    continue
                store.remove(desk.id, name)
                self._remove_file(manager, desk.id, name)
                self._deployment(row.get("foundry_id"), status="retired", ended_at=at, reason=reason, forward={"settled": settled, "fills": fills, "pnl_usd": format(net, "f")})
                self.alert("info", f"foundry: {desk.id}/{name} retired from the live book ({reason})")
                self.publish_desk(desk, name, f"foundry-{row.get('foundry_id')}-retired", at, f"foundry {row.get('foundry_id')}: {name} retired from live desk {desk.id}", [f"retired: {reason}"], row.get("code_sha256"), None)
                out.append({"desk_id": desk.id, "strategy": name, "reason": reason})
        return out

    @staticmethod
    def _remove_file(manager: Any, desk_id: str, name: str) -> None:
        remover = getattr(manager, "toolbox_remove", None)
        if callable(remover) and FOUNDRY_NAME.search(str(name)):
            try:
                remover(desk_id, name)
            except Exception:
                pass

    # ------------------------------------------------------------------ fast-track to live
    def fast_track(self, manifests: Mapping[str, Any], problems: list[str]) -> list[dict[str, Any]]:
        """Move every deployed candidate that has earned it onto its family's live desk.

        The forward record counts only positions the candidate opened after it was deployed
        (`Strategies.record(opened_since=True)`), needs as many of its own fills as settlements,
        and is judged after fees. Until Sept 16, 2026 it counted settlements dated after the
        deployment, and the old settings' positions settling that afternoon put new settings,
        taker orders among them, on a live desk.

        A lopsided event strategy (every settled position an event contract, average entry price
        at or above the evidence gate's `skew_price`) must also pass `evidence.passes` on that
        forward record. Sept 17, 2026: five favorites settled at 0.93 with P&L >= 0 is what a
        strategy with no edge produces about 70% of the time. A family in `excluded_families`
        never goes live from here."""
        from . import evidence

        cfg = self.config
        store = self.store()
        manager = self.sandboxes()
        frozen = [str(k) for k in (cfg.get("frozen_params") or [])]
        need = int(cfg["min_forward_settled"])
        excluded = self.excluded_families()
        gate = self._evidence_config()
        adopted: list[dict[str, Any]] = []
        if self.halted is not None:
            try:
                if self.halted():
                    return adopted
            except Exception:
                return adopted
        for fid, dep in sorted(dict(self.state().get("deployments") or {}).items()):
            if dep.get("status") != "shadow":
                continue
            at = self.now()
            desk = manifests.get(dep.get("desk_id"))
            name = str(dep.get("strategy") or "")
            if desk is None or desk.live:
                self._deployment(fid, status="gone", ended_at=at)
                continue
            row = store.for_desk(desk.id).get(name)
            if not row or not row.get("enabled", True) or row.get("foundry_id") != fid:
                self._deployment(fid, status="superseded", ended_at=at)
                continue
            if dep.get("kind") == "params" and dict(row.get("params") or {}) != dict(dep.get("params") or {}):
                self._deployment(fid, status="superseded", ended_at=at)
                continue
            if dep.get("code_sha256") and self._code_sha(manager, desk.id, name, row) != dep.get("code_sha256"):
                self._deployment(fid, status="superseded", ended_at=at, reason="the shadow desk's code changed under the candidate")
                continue
            if str(dep.get("family")) in excluded or desk.family in excluded:
                continue  # a retired family trades out its shadow record; none of it goes live
            lower = _float(dep.get("oos_ci_lower"))
            if lower is None or lower <= 0 or int(dep.get("oos_trades") or 0) < int(cfg["min_oos_trades"]):
                continue  # a candidate may trade in shadow, but only a confident backtest goes live
            record = self._record(desk.id, name, dep.get("deployed_at"), opened_since=True)
            settled = int(record.get("settled") or 0)
            fills = int(record.get("fills") or 0)
            pnl = _dec(record.get("settled_pnl_usd")) or Decimal(0)
            fees = _dec(record.get("fees_usd")) or Decimal(0)
            net = pnl - fees
            unproven = evidence.lopsided(record, gate["skew_price"]) and not evidence.passes(record, **gate)[0]
            if settled < need or fills < need or net < 0 or unproven:
                if _epoch(at) - _epoch(dep.get("deployed_at")) > float(cfg["forward_max_hours"]) * 3600.0:
                    forward = {"settled": settled, "fills": fills, "pnl_usd": format(pnl, "f"), "fees_usd": format(fees, "f")}
                    self._deployment(fid, status="expired", ended_at=at, forward=forward)
                continue
            live = self.live_desk(str(dep.get("family")), manifests)
            if live is None or not live.live:
                continue
            try:
                result = self._adopt(dep, desk, live, name, record, at, store, manager, frozen)
            except Exception as exc:
                attempts = int(dep.get("attempts") or 0) + 1
                # Three refusals (a full live desk, a dry run that fails) and it stays in shadow.
                self._deployment(fid, attempts=attempts, **({"status": "failed", "ended_at": at} if attempts >= 3 else {}))
                problems.append(f"{fid} not adopted by {live.id}: {type(exc).__name__}: {str(exc)[:160]}")
                continue
            if result is not None:
                adopted.append(result)
        return adopted

    def _adopt(self, dep: Mapping[str, Any], desk: Any, live: Any, name: str, record: Mapping[str, Any], at: str, store: Any, manager: Any, frozen: list[str]) -> dict[str, Any] | None:
        fid = str(dep["id"])
        live_rows = store.for_desk(live.id)
        subject = str(dep.get("subject") or name)
        settled, pnl, fees = record.get("settled"), record.get("settled_pnl_usd"), record.get("fees_usd") or "0"
        note = f"foundry {fid} from {desk.id}: {settled} settled at {pnl} less {fees} fees since {str(dep.get('deployed_at'))[:16]}"

        def supersede(reason: str) -> None:
            self._deployment(fid, status="superseded", ended_at=at, reason=reason[:200])

        if dep.get("kind") == "params":
            own = live_rows.get(name)
            if not own or not own.get("enabled", True):
                # The live desk does not run this strategy: the settings have nowhere to go.
                self._deployment(fid, status="unadoptable", ended_at=at)
                return None
            if dep.get("code_sha256") and self._code_sha(manager, live.id, name, own) != dep.get("code_sha256"):
                supersede(f"{live.id} no longer runs the {name} code the settings were backtested with")
                return None
            # The same code (checked above), so its defaults are the ones backtested; the desk's own
            # frozen values stay.
            mine = dict(own.get("params") or {})
            params = {**{k: v for k, v in dict(dep.get("params") or {}).items() if k not in frozen}, **{k: mine[k] for k in frozen if k in mine}}
            store.update(live.id, name, params=params, promoted_at=at, promoted_from=desk.id, foundry_id=fid, note=note[:200])
            code_sha = own.get("code_sha256")
        else:
            code = (manager.toolbox_files(desk.id) if manager is not None and hasattr(manager, "toolbox_files") else {}).get(f"{name}.py")
            if code is None or _sha(code) != dep.get("code_sha256"):
                supersede("the shadow desk's copy of the candidate changed")
                return None
            parent = live_rows.get(subject)
            if subject != name and parent is not None and not parent.get("enabled", True):
                # A disabled house baseline is not a permanent dead end for recovery research.
                # Only a new code challenger with strong independent forward evidence can
                # replace it. A replaced lineage, changed code, retired family or kill switch
                # still blocks adoption; the old strategy itself is never re-enabled.
                from . import evidence
                recovery = (live.family in (self.config.get("paused_replacement_families") or [])
                            and parent.get("house") and not parent.get("foundry_id")
                            and not any(r.get("enabled", True) and base_name(n) == base_name(subject) for n, r in live_rows.items()))
                if not recovery:
                    supersede(f"{subject} is paused on {live.id}: no eligible recovery lineage")
                    return None
                if int(record.get("independent_settled") or 0) < 25:
                    self._deployment(fid, recovery_wait="25 independently grouped forward outcomes required")
                    return None
                passed, reason, _ = evidence.passes(record, z=1.645, q=0.05, min_n=25, min_days=3)
                if not passed:
                    self._deployment(fid, recovery_wait=reason[:300])
                    return None
            if subject != name and parent is not None and dep.get("subject_sha256") and self._code_sha(manager, live.id, subject, parent) != dep.get("subject_sha256"):
                supersede(f"{live.id} changed {subject} since the candidate was measured against it")
                return None
            if name in live_rows and self._code_sha(manager, live.id, name, live_rows[name]) != dep.get("code_sha256"):
                # Settings carried with a snapshot of the live desk's own code: the desk has
                # written a newer version since, and the snapshot must never overwrite it.
                supersede(f"{live.id} changed {name} since the snapshot was taken")
                return None
            params = {
                **{k: v for k, v in dict(dep.get("params") or {}).items() if k not in frozen},
                **pinned_frozen(self.source_of(subject, live), (parent or {}).get("params"), frozen),
            }
            for other, row in list(live_rows.items()):
                if row.get("foundry_code") and not row.get("enabled", True) and other not in (name, subject):
                    store.remove(live.id, other)
                    self._remove_file(manager, live.id, other)
            limit = int(dict(getattr(self.strategies, "config", {}) or {}).get("max_per_desk", 3))
            current = store.for_desk(live.id)
            set_aside = None
            if name not in current and len(current) >= limit and parent is not None and parent.get("foundry_code") and subject != name:
                # A full live desk: the foundry strategy this one replaces makes the room, and is
                # put back exactly as it was if the new code's dry run refuses.
                set_aside = (dict(current[subject]), (manager.toolbox_files(live.id) or {}).get(f"{subject}.py"))
                store.remove(live.id, subject)
            try:
                self.strategies.install(
                    live,
                    {"name": name, "code": code, "cadence_seconds": int(dep.get("cadence_seconds") or (parent or {}).get("cadence_seconds") or 600), "params": params},
                    note=f"foundry {fid}",
                )
            except Exception:
                if name not in current:
                    self._remove_file(manager, live.id, name)
                if set_aside is not None:
                    store.update(live.id, subject, **set_aside[0])
                raise
            if set_aside is not None:
                self._remove_file(manager, live.id, subject)
                parent = None
            marks = {"foundry_code": True} if name not in current else {}
            store.update(live.id, name, foundry_id=fid, promoted_at=at, promoted_from=desk.id, note=note[:200], **marks)
            if name not in current:
                # The mutation replaces the code it came from and anything else of its line on the
                # live desk; running both would double the exposure on the same markets.
                lineage = {base_name(name), base_name(subject)}
                for other, row in sorted(store.for_desk(live.id).items()):
                    if other == name or not row.get("enabled", True):
                        continue
                    if other == subject or base_name(other) in lineage:
                        store.update(live.id, other, enabled=False, note=f"replaced by foundry {fid} ({name})"[:200])
                        if row.get("foundry_id") and row.get("foundry_id") != fid:
                            self._deployment(row.get("foundry_id"), status="retired", ended_at=at)
            code_sha = _sha(code)
        self._deployment(fid, status="live", live_desk_id=live.id, promoted_at=at, forward={"settled": settled, "pnl_usd": pnl, "fees_usd": fees})
        lines = [
            f"foundry {fid}: {name} adopted by live desk {live.id} from shadow desk {desk.id}",
            f"backtest out of sample: {dep.get('oos_trades')} positions, return {_fmt(dep.get('oos_return'))} per $, 95% lower bound {_fmt(dep.get('oos_ci_lower'), '+.4f')}",
            f"forward on {desk.id} since {dep.get('deployed_at')}: {settled} positions opened and settled, P&L {pnl}, fees {fees}",
            f"params: {json.dumps(params, sort_keys=True)[:800]}",
            "sizes, limits and capital unchanged; evidence resets at this promotion",
        ]
        if dep.get("kind") == "code" and subject != name:
            lines.append(f"{subject} paused on {live.id}")
        self.publish_desk(live, name, f"foundry-{fid}-live", at, f"foundry {fid}: {name} takes live desk {live.id}", lines, code_sha, 0)
        self.alert("info", f"foundry: {live.id}/{name} adopts {fid} from {desk.id} ({settled} settled at {pnl} less {fees} fees; backtest out-of-sample {_fmt(dep.get('oos_return'))} per $)")
        return {"id": fid, "live_desk_id": live.id, "from": desk.id, "strategy": name, "kind": dep.get("kind")}

    # ------------------------------------------------------------------ publication
    def publish_desk(self, manifest: Any, name: str, suffix: str, at: str, purpose: str, lines: list[str], code_sha: str | None, seconds: Any) -> None:
        stamp = at[:16].replace("-", "").replace(":", "").replace("T", "-")
        # Bounded in bytes, not characters: `_clean` turns "<" into a three-byte character and a
        # model's params or hypothesis can carry four-byte ones (a 4,146-byte event, Sept 16, 2026).
        text = _clean("\n".join(_clip_bytes(str(line), 900) for line in lines))
        payload = {
            "session_id": f"{manifest.id}:{stamp}:strategy:{name}",
            "code_sha256": str(code_sha or "")[:64] or "0" * 64,
            "language": "python",
            "stdout": _clip_bytes(text, 2400),
            "exit_code": 0,
            "seconds": f"{_float(seconds) or 0.0:.1f}",
            "sandbox": None,
            "purpose": _clip_bytes(_clean(purpose), 200),
        }
        budget = 2400
        while _json_bytes(payload) > CODE_RUN_BYTES and budget > 200:
            budget -= 400
            payload["stdout"] = _clip_bytes(text, budget)
        try:
            self.log.append(manifest.stream, "desk.code_run", payload, id=f"{suffix}:{at}"[:200], at=at)
        except Exception as exc:
            self.alert("warning", f"foundry run not published: {type(exc).__name__}")

    def publish_cycle(self, summary: Mapping[str, Any], window: Mapping[str, Any], reference: float, winner: Mapping[str, Any] | None, deployment: Mapping[str, Any] | None) -> None:
        cfg = self.config
        candidates = list(summary.get("candidates_detail") or [])
        family, subject, cycle = summary.get("family"), summary.get("strategy"), summary.get("cycle")
        params_n = sum(1 for c in candidates if c["kind"] == "params")
        code_n = sum(1 for c in candidates if c["kind"] == "code")
        best = summary.get("best_oos_return")
        if deployment is not None and winner is not None and deployment.get("status") == "live":
            outcome = f"{deployment.get('role') or 'winner'} {deployment['id']} ({winner['label']}) deployed to live desk {deployment['desk_id']} at learning size"
        elif deployment is not None and winner is not None:
            outcome = f"winner {deployment['id']} ({winner['label']}) deployed to shadow desk {deployment['desk_id']}"
        elif winner is not None:
            outcome = f"winner {winner['id']} qualified but found no shadow desk"
        else:
            outcome = "no winner"
        text = (
            f"Foundry cycle {cycle}: {params_n + code_n} candidates for {family}/{subject} "
            f"({params_n} settings, {code_n} code) against {summary.get('baselines')} baselines; "
            f"best out-of-sample return {_fmt(best)} per $; {outcome}."
        )
        plan = (
            f"Backtest {window['start']} to {window['end']} every {window['step_minutes']} min, one sandbox per run. "
            f"Qualify on the last {round((1 - float(cfg['split_fraction'])) * 100)}% of positions: >= {cfg['min_oos_trades']} positions, "
            f">= {cfg['min_trades']} trades, return above the best baseline {reference:+.3f} by {cfg['margin']}, 95% lower bound on "
            f"mean P&L above {cfg['min_ci_lower']}. The best goes to the worst shadow desk; live after {cfg['min_forward_settled']} "
            "settled positions there at P&L >= 0."
        )
        top = sorted(
            (c for c in candidates if c.get("evidence")),
            key=lambda c: -(c["evidence"]["out_of_sample"]["return_on_notional"] if c["evidence"]["out_of_sample"]["return_on_notional"] is not None else -1e9),
        )
        rows = []
        for c in top[:6]:
            oos = c["evidence"]["out_of_sample"]
            rows.append({
                "id": c["id"], "kind": c["kind"], "label": str(c["label"])[:60], "trades": c["evidence"]["trades"],
                "oos_trades": oos["trades"], "oos_return": None if oos["return_on_notional"] is None else _fmt(oos["return_on_notional"], "+.4f"),
                "oos_ci_lower": None if not oos["ci95_mean_pnl"] else _fmt(oos["ci95_mean_pnl"][0], "+.4f"), "verdict": str(c.get("verdict") or "baseline")[:100],
            })
        code = dict(summary.get("code") or {})
        payload: dict[str, Any] = {
            "hypothesis_id": f"foundry-{cycle}",
            "text": text,
            "test_plan": plan,
            "family": family,
            "strategy": subject,
            "cycle": cycle,
            "candidates": params_n + code_n,
            "backtested": summary.get("backtested"),
            "qualified": summary.get("qualified"),
            "baseline_oos_return": _fmt(reference, "+.4f"),
            "best_oos_return": None if best is None else _fmt(best, "+.4f"),
            "winner": deployment["id"] if deployment is not None else "no winner",
            "deployed_to": None if deployment is None else deployment["desk_id"],
            "hypothesis": None if winner is None else winner.get("hypothesis"),
            "code_rejected": [str(r)[:160] for r in (code.get("rejected") or [])[:3]],
            "code_skipped": code.get("skipped"),
            "top": rows,
        }
        payload = _clean(payload)
        while _json_bytes(payload) > PAYLOAD_BYTES:
            if payload["top"]:
                payload["top"] = payload["top"][:-1]
            elif payload["code_rejected"]:
                payload["code_rejected"] = payload["code_rejected"][:-1]
            else:
                payload["text"] = _clip_bytes(payload["text"], 400)
                payload["test_plan"] = _clip_bytes(payload["test_plan"], 400)
                payload["hypothesis"] = _clip_bytes(payload.get("hypothesis") or "", 200) or None
                payload["code_skipped"] = _clip_bytes(payload.get("code_skipped") or "", 120) or None
                payload["strategy"] = _clip_bytes(str(payload.get("strategy") or ""), 60)
                break
        at = str(summary.get("at") or self.now())
        try:
            self.log.append("lab", "lab.hypothesis", payload, id=f"foundry:{cycle}:{at}"[:200], at=self.now())
        except Exception as exc:
            self.alert("warning", f"foundry cycle not published: {type(exc).__name__}")


__all__ = [
    "DEFAULTS",
    "Foundry",
    "check_strategy_code",
    "pinned_frozen",
    "categorical_pool",
    "jitter_variants",
    "literal_defaults",
    "parse_result",
    "runner_code",
    "split_evidence",
]
