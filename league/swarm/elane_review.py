"""THE EQUITY REVIEW (release E2, Oct 2026): the leakage check every share program the swarm breeds passes before its
lineage's one Validation try, and the review record E1's look reads (league/swarm/elane.py `look` -> `reviewed`).

Why. E1 takes a sealed look only of a captain-seeded program or of a version whose state carries a passed review AND a
passed audit of its exact program (`state["review"]` = {"sha": gate.run_sha(version), "verdict": "pass", "audit":
{"verdict": "pass"}}). The models that write equity programs know the market's history, Validation's year and part of
the holdout's: a rule keyed to an absolute level ("buy SPY while it sits above 1234.5", an invented level) does nothing
on Train and encodes a remembered later market. The options gate refuses such programs in its paid review (league/swarm/gate.py `REVIEW`:
ABSOLUTE PRICE-LEVEL CONSTANTS, CALENDAR RECONSTRUCTION); this is that review for share programs, in two steps.

1. THE LEVEL RULE (`level_refusals`; static, free, no model call): a program is refused when a raw level field (a
   price: `ctx.prices[s]`, `ctx.bars[s].open/high/low/close`, a lot's or a closed lot's `entry`, `mark` or `exit`; a
   share volume: `ctx.bars[s].volume`), or the log of one, or anything that keeps its units (a moving average, a high,
   a difference of two prices, a price times a constant), is COMPARED with, OFFSET by (+, -), BUCKETED by (//, %) or
   CLIPPED against (max, min, clip, where) a constant or a PARAMS value. A ratio of two levels (a price over its own
   average, a return) is scale-free and is not touched; a comparison with zero (a sign or a missing-bar check) is not
   either. A taint pass over the module (module constants, PARAMS, names, helpers' returns, comprehensions); what it
   cannot follow (a value through STATE, an unknown call) is left to the paid review, never refused on a guess.
   It runs in `elane_train.check_code`, so such a program is never stored or run: the researcher hears why.
2. THE PAID REVIEW AND AUDIT (`EquityReview`): at a version's first Train pass (equity-v1), BEFORE it is the lineage's
   Validation try, two different models read the exact program, its card and its own Train facts (never a Validation
   or look figure: A9 D3) under `REVIEW` (the gate's leakage rubric for daily share programs) and answer
   pass / fail / unclear. A failure must be grounded (`grounded`: a verbatim excerpt of the file, a reference among
   `FACTS`, a causal counterexample), else it reads unclear; `max_unclear` unclear reads of one stage fail the version.
   The review is asked on the first route of `review_routes` that answers; the audit on the first route whose MODEL
   differs from the reviewer's. A pass of both writes the record E1 reads (`record`); a failure is a Train failure of
   that version ("REVIEW", its reasons in the researcher's brief) and spends no Validation try. A question no route
   answered is asked again next round and counts nothing. Their dollars are E2's (`elane.e2.usd_day`), booked in the
   ledger under "review:<route>" (league/swarm/elane_yield.py), never on a birth route's row.

Settings (`elane.e2`; defaults `DEFAULTS`, each held to its bound): `review_routes`, `review_max_output_tokens`,
`review_effort`, `review_max_unclear`. Standard library only.
"""

from __future__ import annotations

import ast
import json
import math
from typing import Any, Iterable, Mapping, Sequence

#: The review's objective (its record names it).
OBJECTIVE = "equity-review-1"
#: E1's family-state key of a program's passed review and audit (league/swarm/elane.py `reviewed`, the gate's shape).
STATE_REVIEW = "review"
DEFAULTS: dict[str, Any] = {"review_routes": ["sail:pro_balanced", "sail:k3_balanced", "sail:glm_balanced"],
                            "review_max_output_tokens": 6000, "review_effort": "medium", "review_max_unclear": 3}
BOUNDS: dict[str, tuple[float, float]] = {"review_max_output_tokens": (1000, 32000), "review_max_unclear": (1, 10)}
EFFORTS = ("minimal", "low", "medium", "high", "xhigh")

# ------------------------------------------------------------------------------------------------------- the level rule
#: The raw level fields: a symbol's bars (`ctx.bars[s].<field>`, or ["field"]) and a lot's prices.
BAR_FIELDS = ("open", "high", "low", "close", "volume")
LOT_FIELDS = ("entry", "mark", "exit")
#: A constant this close to zero is a sign check or an epsilon, never a level.
ZERO = 1e-6
#: Functions whose result keeps the units of their arguments (a mean of prices is a price).
KEEP = frozenset({
    "mean", "nanmean", "median", "nanmedian", "max", "min", "nanmax", "nanmin", "amax", "amin", "percentile",
    "nanpercentile", "quantile", "nanquantile", "sum", "nansum", "abs", "fabs", "absolute", "round", "around", "rint",
    "floor", "ceil", "trunc", "float", "int", "sqrt", "cumsum", "maximum", "minimum", "fmax", "fmin", "clip", "array",
    "asarray", "asanyarray", "ravel", "copy", "sort", "flatten", "concatenate", "hstack", "vstack", "stack", "where",
    "nan_to_num", "average", "convolve", "std", "nanstd", "var", "nanvar", "ptp", "diff", "ediff1d", "gradient", "sorted",
    "list", "tuple", "reversed", "full_like", "take"})
#: Of those, the ones whose result on a LOG level is scale-free (a dispersion or a difference of logs).
SPREAD = frozenset({"std", "nanstd", "var", "nanvar", "ptp", "diff", "ediff1d", "gradient"})
#: The ones that combine their arguments: a level among them with a constant is a clip or a floor at a level.
COMBINE = frozenset({"max", "min", "maximum", "minimum", "fmax", "fmin", "clip", "where", "nanmax", "nanmin", "amax",
                     "amin"})
LOG = frozenset({"log", "log10", "log2", "log1p"})
EXP = frozenset({"exp", "expm1"})
#: Functions whose result carries no unit (a flag, a count, a correlation).
UNITLESS = frozenset({"isnan", "isfinite", "isinf", "len", "argmax", "argmin", "argsort", "sign", "count_nonzero",
                      "nonzero", "any", "all", "bool", "isclose", "corrcoef", "range", "enumerate", "zip", "str"})
MODULES = frozenset({"np", "numpy", "math"})

_L, _G, _C, _U = "L", "G", "C", "U"
#: The container marks: ctx.prices, ctx.bars, one symbol's bars, PARAMS.
_PRICES, _BARS, _BAR, _PARAMS = "PRICES", "BARS", "BAR", "PARAMS"
_NONE: frozenset[str] = frozenset()


def _norm(tags: Iterable[str]) -> frozenset[str]:
    """A value's unit: a level (L) over a log level (G) over unknown (U) over a constant (C); empty is unit-free."""
    t = set(tags)
    for mark in (_L, _G, _U, _C):
        if mark in t:
            return frozenset({mark})
    return _NONE


def _level(t: frozenset[str]) -> bool:
    return _L in t or _G in t


def _const(t: frozenset[str]) -> bool:
    return t == frozenset({_C})


def _key(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


class _Levels:
    """The taint pass (the module docstring, 1). `found`: [(line, why)]."""

    def __init__(self, tree: ast.Module):
        self.tree = tree
        self.found: list[tuple[int, str]] = []
        self.record = False
        self.returns: dict[str, frozenset[str]] = {}
        self.modules = set(MODULES)
        self._ret: list[set[str]] = []
        self._accum: set[str] = set()

    # ------------------------------------------------------------------ the module
    def run(self) -> list[tuple[int, str]]:
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                self.modules.update(a.asname or a.name.split(".")[0] for a in node.names)
        for record in (False, False, True):  # helpers' returns settle first; refusals are kept on the last pass only
            self.record = record
            env: dict[str, set[str]] = {}
            self._block(self.tree.body, env)
        seen, out = set(), []
        for item in self.found:
            if item not in seen:
                seen.add(item)
                out.append(item)
        return out

    def _refuse(self, node: ast.AST, why: str) -> None:
        if self.record:
            self.found.append((int(getattr(node, "lineno", 0) or 0), why))

    # ------------------------------------------------------------------ statements
    def _block(self, body: Sequence[ast.stmt], env: dict[str, set[str]]) -> None:
        for stmt in body:
            self._stmt(stmt, env)

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, env: dict[str, set[str]]) -> None:
        inner = {k: set(v) for k, v in env.items()}
        args = node.args
        for a in [*args.posonlyargs, *args.args, *args.kwonlyargs, *([args.vararg] if args.vararg else []),
                  *([args.kwarg] if args.kwarg else [])]:
            inner[a.arg] = {_U}
        for default in [*args.defaults, *[d for d in args.kw_defaults if d is not None]]:
            self._tag(default, env)
        self._ret.append(set())
        for _ in range(2):  # loops: a name assigned late in the body reaches the reads above it
            self._block(node.body, inner)
        self.returns[node.name] = _norm(self._ret.pop())
        env.setdefault(node.name, set()).add(_U)

    def _stmt(self, node: ast.stmt, env: dict[str, set[str]]) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self._function(node, env)
        elif isinstance(node, ast.Assign):
            # A running extreme (`best = max(best, x)`, its start a sentinel such as -1e9) is no clip at a level.
            names = {t.id for t in node.targets if isinstance(t, ast.Name)}
            held, self._accum = self._accum, names if isinstance(node.value, ast.Call) else set()
            try:
                tag = self._tag(node.value, env)
            finally:
                self._accum = held
            for target in node.targets:
                self._assign(target, node.value, tag, env)
        elif isinstance(node, ast.AnnAssign):
            if node.value is not None:
                self._assign(node.target, node.value, self._tag(node.value, env), env)
        elif isinstance(node, ast.AugAssign):
            target = node.target
            current = self._name(target.id, env) if isinstance(target, ast.Name) else self._tag(target, env)
            tag = self._binop(node, current, node.op, self._tag(node.value, env))
            if isinstance(node.target, ast.Name):
                env.setdefault(node.target.id, set()).update(tag)
        elif isinstance(node, ast.Return):
            if node.value is not None and self._ret:
                self._ret[-1].update(self._tag(node.value, env))
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            self._assign(node.target, None, self._element(self._tag(node.iter, env)), env)
            for _ in range(2):
                self._block(node.body, env)
            self._block(node.orelse, env)
        elif isinstance(node, ast.While):
            for _ in range(2):
                self._tag(node.test, env)
                self._block(node.body, env)
            self._block(node.orelse, env)
        elif isinstance(node, ast.If):
            self._tag(node.test, env)
            self._block(node.body, env)
            self._block(node.orelse, env)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                self._tag(item.context_expr, env)
            self._block(node.body, env)
        elif isinstance(node, ast.Try):
            self._block(node.body, env)
            for handler in node.handlers:
                self._block(handler.body, env)
            self._block(node.orelse, env)
            self._block(node.finalbody, env)
        elif isinstance(node, ast.Expr):
            self._tag(node.value, env)
        elif isinstance(node, (ast.Assert,)):
            self._tag(node.test, env)
        else:
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.expr):
                    self._tag(child, env)
                elif isinstance(child, ast.stmt):
                    self._stmt(child, env)

    def _assign(self, target: ast.AST, value: ast.AST | None, tag: frozenset[str], env: dict[str, set[str]]) -> None:
        if isinstance(target, ast.Name):
            env.setdefault(target.id, set()).update(tag or {"_free"})
        elif isinstance(target, (ast.Tuple, ast.List)):
            if isinstance(value, (ast.Tuple, ast.List)) and len(value.elts) == len(target.elts):
                for t, v in zip(target.elts, value.elts):
                    self._assign(t, v, self._tag(v, env), env)
            else:
                for t in target.elts:
                    self._assign(t, None, self._element(tag) if tag else tag, env)
        elif isinstance(target, ast.Starred):
            self._assign(target.value, None, tag, env)
        else:  # STATE["x"] = ..., an attribute: evaluated, never followed (left to the paid review)
            self._tag(target, env)

    # ------------------------------------------------------------------ expressions
    @staticmethod
    def _element(tag: frozenset[str]) -> frozenset[str]:
        """What iterating a value yields: a level array's elements are levels; ctx's containers yield keys."""
        if tag & {_PRICES, _BARS, _BAR, _PARAMS}:
            return frozenset({_U})
        return _norm(tag) if tag else _NONE

    def _name(self, name: str, env: dict[str, set[str]]) -> frozenset[str]:
        if name == "PARAMS":
            return frozenset({_PARAMS})
        held = env.get(name)
        if held is None:
            return frozenset({_U})
        marks = {t for t in held if t in (_PRICES, _BARS, _BAR, _PARAMS)}
        if marks:
            return frozenset(marks)
        return _norm(t for t in held if t != "_free")

    def _subscript(self, base: frozenset[str], key: str | None) -> frozenset[str]:
        if _PRICES in base:
            return frozenset({_L})
        if _BARS in base:
            return frozenset({_BAR})
        if _BAR in base:
            return frozenset({_L}) if key in BAR_FIELDS else _NONE if key == "ret" else frozenset({_U})
        if _PARAMS in base:
            return frozenset({_C})
        if key in LOT_FIELDS:
            return frozenset({_L})
        return _norm(base) if base else _NONE

    def _tag(self, node: ast.AST | None, env: dict[str, set[str]]) -> frozenset[str]:
        if node is None:
            return _NONE
        if isinstance(node, ast.Constant):
            v = node.value
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                return _NONE
            return _NONE if not math.isfinite(float(v)) or abs(float(v)) <= ZERO else frozenset({_C})
        if isinstance(node, ast.Name):
            return self._name(node.id, env)
        if isinstance(node, ast.Attribute):
            base = self._tag(node.value, env)
            if node.attr == "prices":
                return frozenset({_PRICES})
            if node.attr == "bars":
                return frozenset({_BARS})
            if node.attr == "params":
                return frozenset({_PARAMS})
            if _BAR in base:
                return frozenset({_L}) if node.attr in BAR_FIELDS else _NONE if node.attr == "ret" else frozenset({_U})
            if isinstance(node.value, ast.Name) and node.value.id in self.modules:
                return frozenset({_U})  # np.nan, math.pi: no level
            return frozenset({_U})
        if isinstance(node, ast.Subscript):
            base = self._tag(node.value, env)
            self._tag(node.slice, env)
            return self._subscript(base, _key(node.slice))
        if isinstance(node, ast.Call):
            return self._call(node, env)
        if isinstance(node, ast.BinOp):
            return self._binop(node, self._tag(node.left, env), node.op, self._tag(node.right, env))
        if isinstance(node, ast.UnaryOp):
            inner = self._tag(node.operand, env)
            return _NONE if isinstance(node.op, ast.Not) else _norm(inner) if inner else _NONE
        if isinstance(node, ast.Compare):
            tags = [self._tag(node.left, env)] + [self._tag(c, env) for c in node.comparators]
            for op, a, b in zip(node.ops, tags, tags[1:]):
                if isinstance(op, (ast.In, ast.NotIn, ast.Is, ast.IsNot)):
                    continue
                a, b = _norm(a), _norm(b)
                if (_level(a) and _const(b)) or (_level(b) and _const(a)):
                    self._refuse(node, "compares a price or volume level (or its log) with a constant or a PARAMS "
                                       "value")
            return _NONE
        if isinstance(node, ast.BoolOp):
            return _norm(t for v in node.values for t in self._tag(v, env))
        if isinstance(node, ast.IfExp):
            self._tag(node.test, env)
            return _norm([*self._tag(node.body, env), *self._tag(node.orelse, env)])
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            return _norm(t for e in node.elts for t in self._tag(e, env))
        if isinstance(node, ast.Dict):
            for k in node.keys:
                self._tag(k, env)
            return _norm(t for v in node.values for t in self._tag(v, env))
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
            inner = {k: set(v) for k, v in env.items()}
            for gen in node.generators:
                self._assign(gen.target, None, self._element(self._tag(gen.iter, inner)), inner)
                for cond in gen.ifs:
                    self._tag(cond, inner)
            if isinstance(node, ast.DictComp):
                self._tag(node.key, inner)
                return _norm(self._tag(node.value, inner))
            return _norm(self._tag(node.elt, inner))
        if isinstance(node, ast.Lambda):
            inner = {k: set(v) for k, v in env.items()}
            for a in node.args.args:
                inner[a.arg] = {_U}
            self._tag(node.body, inner)
            return frozenset({_U})
        if isinstance(node, ast.Starred):
            return self._tag(node.value, env)
        if isinstance(node, ast.NamedExpr):
            tag = self._tag(node.value, env)
            self._assign(node.target, node.value, tag, env)
            return tag
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.expr):
                self._tag(child, env)
        return frozenset({_U})

    def _call(self, node: ast.Call, env: dict[str, set[str]]) -> frozenset[str]:
        func = node.func
        args = [self._tag(a, env) for a in node.args] + [self._tag(k.value, env) for k in node.keywords]
        if isinstance(func, ast.Attribute):
            base = self._tag(func.value, env)
            if func.attr == "get" and base & {_PRICES, _BARS, _BAR, _PARAMS}:
                return self._subscript(base, _key(node.args[0]) if node.args else None)
            name = func.attr
            method = not (isinstance(func.value, ast.Name) and func.value.id in self.modules)
            if method:
                args = [base] + args  # a method of a value (close.mean()): the value is its first argument
        elif isinstance(func, ast.Name):
            name, method = func.id, False
            if name in self.returns:
                return self.returns[name] or _NONE
        else:
            self._tag(func, env)
            return frozenset({_U})
        units = [_norm(a) for a in args]
        direct = [*node.args, *(k.value for k in node.keywords)]
        if method:
            direct = [func.value, *direct]
        consts = [u for u, a in zip(units, direct)
                  if _const(u) and not (isinstance(a, ast.Name) and a.id in self._accum)]
        if name in COMBINE and len(units) > 1 and any(_level(u) for u in units) and consts:
            self._refuse(node, f"clips or floors a price or volume level against a constant or a PARAMS value ({name})")
        if name in UNITLESS:
            return _NONE
        if name in LOG:
            first = units[0] if units else _NONE
            return frozenset({_G}) if _L in first else frozenset({_U}) if _G in first else first
        if name in EXP:
            first = units[0] if units else _NONE
            return frozenset({_L}) if _G in first else frozenset({_U}) if _L in first else first
        if name in KEEP:
            joined = _norm(t for u in units for t in u)
            if name in SPREAD and _G in joined:
                return _NONE
            digits = direct[1:]  # round(px, -1), np.round(px, -1), px.round(-1): a negative ndigits is a level grid
            if name in ("round", "around") and units and _level(units[0]) and \
                    any(isinstance(a, ast.UnaryOp) and isinstance(a.op, ast.USub) for a in digits):
                self._refuse(node, "rounds a price or volume level to a fixed grid (a level bucket)")
            return joined
        return frozenset({_U})

    def _binop(self, node: ast.AST, a: frozenset[str], op: ast.operator, b: frozenset[str]) -> frozenset[str]:
        a, b = _norm(a), _norm(b)
        if isinstance(op, (ast.Add, ast.Sub)):
            if (_level(a) and _const(b)) or (_level(b) and _const(a)):
                self._refuse(node, "offsets a price or volume level (or its log) by a constant or a PARAMS value")
            if _L in a and _L in b:
                return frozenset({_L})
            if _G in a and _G in b:
                return _NONE if isinstance(op, ast.Sub) else frozenset({_G})
            if _U in a or _U in b:
                return frozenset({_U})
            if _L in a or _L in b:
                return frozenset({_L})
            if _G in a or _G in b:
                return frozenset({_G})
            return frozenset({_C}) if _const(a) and _const(b) else _NONE
        if isinstance(op, (ast.FloorDiv, ast.Mod)):
            if (_level(a) and (_const(b) or not b)) or (_level(b) and _const(a)):
                self._refuse(node, "buckets a price or volume level by a constant or a PARAMS value (// or %)")
            return a if _level(a) else frozenset({_U}) if (_U in a or _U in b) else _norm([*a, *b])
        if isinstance(op, ast.Div):
            if _L in a and _L in b:
                return _NONE  # a ratio of two levels: scale-free
            if _U in a or _U in b or (_G in a and _L in b) or (_L in a and _G in b) or (_G in a and _G in b):
                return frozenset({_U})
            if _L in a or _L in b:
                return frozenset({_L})
            if _G in a:
                return frozenset({_G})
            return frozenset({_C}) if _const(a) and _const(b) else _NONE
        if isinstance(op, ast.Mult):
            if _U in a or _U in b or (_G in a and (_G in b or _L in b)) or (_L in a and _G in b):
                return frozenset({_U})
            if _L in a or _L in b:
                return frozenset({_L})
            if _G in a or _G in b:
                return frozenset({_G})
            return frozenset({_C}) if _const(a) and _const(b) else _NONE
        if isinstance(op, ast.Pow):
            if _level(a):
                return a
            return frozenset({_C}) if _const(a) and _const(b) else frozenset({_U}) if (_U in a or _U in b) else _NONE
        return frozenset({_U})


def level_refusals(code: Any) -> list[str]:
    """THE LEVEL RULE (the module docstring, 1): every place the program holds a raw level against a constant or a PARAMS
    value, as "line N: why" ([] for none, and for a file that does not parse: the code rules refuse that)."""
    try:
        tree = ast.parse(str(code or ""))
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return []
    try:
        found = _Levels(tree).run()
    except RecursionError:
        return ["the program is nested too deeply to be read for absolute levels"]
    except Exception:  # noqa: BLE001 - a shape the pass cannot follow is never refused on a guess (the paid review reads it)
        return []
    return [f"line {line}: {why}" for line, why in found]


def level_text(code: Any) -> str | None:
    """Why a program is refused by THE LEVEL RULE, in one sentence for its author, or None."""
    found = level_refusals(code)
    if not found:
        return None
    return ("refused by the equity level rule (absolute levels identify the years: hold prices only against other prices, "
            "e.g. a ratio to their own average or recent high, never against a constant or a PARAMS value): "
            + "; ".join(found[:4]) + (f"; and {len(found) - 4} more" if len(found) > 4 else ""))


# ------------------------------------------------------------------------------------------------------- the paid review
#: The contract references a failure may cite (`grounded`).
FACTS: dict[str, str] = {
    "levels": "A price, an average or range of prices, a lot's entry or mark, a share volume, or the log of any of them, "
              "held against a constant or a PARAMS value identifies the years. A ratio of a symbol's price to its own "
              "average, high or prior close, a return, a realized volatility, a z-score or a rank is scale-free.",
    "calendar": "ctx gives no date or year: weekday, session_of_month, sessions_to_month_end and the event flags only. "
                "Counting sessions, months or event flags across a run in STATE to work out the date or the year, or a "
                "table of dates, levels or events, is prohibited. A warm-up that waits for enough history is permitted.",
    "context": "Only ctx's fields exist (league/equity/EQUITY.md): symbols, bars (open, high, low, close, volume, ret), "
               "prices, weekday, events, events_next, session_of_month, sessions_to_month_end, positions, orders, closed, "
               "rejects, cash, equity, budget, caps, params. Module STATE persists within one run, never across runs.",
    "fills": "decide(ctx) runs after session t's close; every intent executes in the NEXT session at its open or close. "
             "A rule that needs session t+1's prices to decide is lookahead.",
}
REVIEW = """You review long-only ETF programs before their ONE Validation try and ONE sealed holdout look. A program is one Python
file (NEEDS, PARAMS, decide(ctx)) that the House runs once a session after the close on daily bars: on Train (2016-2024),
then unchanged on Validation (2025), the holdout and real money. Its author saw only its Train runs, but the models that
write programs remember the market's history, so a program can encode a remembered period without any figure in sight.
Refuse it (verdict "fail") for any of:
- LEAKAGE: recognizing the calendar or a specific period. Refuse ABSOLUTE LEVELS: a price, an average or range of prices,
  a lot's entry or mark, a share volume, or the log of any of them, compared with, offset by, bucketed by or clipped at a
  constant or a PARAMS value (invented examples: "SPY above 1234.5", "volume over 9,876,543", "log price over 7.7"): a
  level identifies the years; likewise the ratio of two DIFFERENT symbols' prices held against a constant. Refuse CALENDAR RECONSTRUCTION:
  counting sessions, months, weekdays or event flags across a run in STATE to work out the date or the year, or a rule
  that changes after a count that matters only because the author knows when a run starts; regime switches keyed to
  values that identify periods; and any table of dates, levels, returns or events. Relative measures (returns, a
  symbol's price against its own moving average, high or prior close, realized volatility, z-scores, ranks across
  symbols) and ctx's own calendar fields (weekday, session_of_month, sessions_to_month_end, the event flags) are fine; a
  warm-up that waits for enough history is fine.
- LOOKAHEAD: anything that could know the future inside the replay (it only sees ctx at session t's close; its intents
  fill at the NEXT session's open or close).
Use the contract in this prompt as the execution contract. Do not invent unavailable fields. Distinguish a verified defect
from an unresolved concern; reply unclear when the evidence is insufficient. An inactive strategy, a causal STATE
dictionary, or a price sampled from ctx and compared with another price is not a violation.
For EACH failure provide a verbatim code excerpt present in the submitted file, a contract_reference (one of: levels,
calendar, context, fills), and a causal counterexample: exact input conditions and the bad decision that follows.
Otherwise pass it. Reply with ONE JSON object: {"verdict": "pass" or "fail" or "unclear", "reasons": ["..."],
"findings": [{"code_excerpt": "...", "contract_reference": "...", "counterexample": "..."}], "notes": "..."}.

THE PROGRAM CONTRACT (league/equity/EQUITY.md):
"""


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def cfg(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    """The review's settings from `elane.e2`, each inside its bound (a malformed value is its default)."""
    from . import elane_yield

    raw = elane_yield.e2_settings(settings)
    out = dict(DEFAULTS)
    routes = raw.get("review_routes")
    if isinstance(routes, list):
        kept = [str(r) for r in routes if isinstance(r, str) and r.split(":", 1)[0] in elane_yield.ROUTE_KINDS
                and ":" in r and r.split(":", 1)[1].strip()]
        if kept:
            out["review_routes"] = list(dict.fromkeys(kept))
    for key, (lo, hi) in BOUNDS.items():
        x = _num(raw.get(key))
        if x is not None and lo <= x <= hi:
            out[key] = int(x)
    if raw.get("review_effort") in EFFORTS:
        out["review_effort"] = raw["review_effort"]
    return out


def model_of(route_key: str) -> str:
    """The model a route reaches (two routes on one Sail model, e.g. its asap and balanced windows, are one reader)."""
    kind, _, name = str(route_key).partition(":")
    if kind == "sail":
        try:
            from ltcm.provider import PROFILES

            return str(PROFILES[name][0])
        except Exception:  # noqa: BLE001 - an unknown profile is its own model
            return f"sail:{name}"
    return f"{kind}:{name}"


def grounded(answer: Mapping[str, Any] | None, code: str) -> dict[str, Any]:
    """A review answer as it binds (the gate's `grounded_answer` on `FACTS`): {verdict "pass" | "fail" | "unclear",
    reasons, findings}. A failure needs every finding grounded (a verbatim excerpt of `code`, a reference of `FACTS`, a
    counterexample of 20 characters or more), else it reads unclear. No failure becomes a pass."""
    from .models import extract_json

    answer = answer or {}
    raw = answer.get("json") if isinstance(answer.get("json"), Mapping) else extract_json(str(answer.get("text") or ""))
    raw = raw if isinstance(raw, Mapping) else {}
    verdict = raw.get("verdict") if raw.get("verdict") in ("pass", "fail") else "unclear"
    reasons = raw.get("reasons") or []
    reasons = [" ".join(str(r).split())[:400] for r in reasons[:6]] if isinstance(reasons, list) else [str(reasons)[:400]]
    findings = raw.get("findings") or []
    verified = []
    if isinstance(findings, list):
        for f in findings[:6]:
            if not isinstance(f, Mapping):
                continue
            quote, ref, why = f.get("code_excerpt"), f.get("contract_reference"), f.get("counterexample")
            if isinstance(quote, str) and len(quote.strip()) >= 4 and quote in code and ref in FACTS and \
                    isinstance(why, str) and len(why.strip()) >= 20:
                verified.append({"code_excerpt": quote[:600], "contract_reference": ref, "counterexample": why[:800]})
    missing = verdict == "fail" and (not verified or len(verified) != len(findings if isinstance(findings, list) else []))
    return {"verdict": "unclear" if missing else verdict, "claimed": verdict, "reasons": reasons, "findings": verified,
            "model": answer.get("model"), "route": answer.get("route"), "cost_usd": answer.get("cost_usd")}


def question(fam: Mapping[str, Any], version: Mapping[str, Any], *, card: Mapping[str, Any] | None, train: str,
             lane_label: str, stage: str) -> str:
    """The review's user turn: the family's birth facts and card, the exact program, its PARAMS and its own Train
    verdict (Train facts only: never a Validation or look figure)."""
    spec = fam.get("spec") if isinstance(fam.get("spec"), Mapping) else {}
    lines = [f"{'AUDIT. ' if stage == 'audit' else ''}Family {fam.get('id')}, lane {lane_label}, symbols "
             f"{', '.join(str(s) for s in (spec.get('symbols') or fam.get('roots') or []))}. Mechanism: "
             f"{' '.join(str(fam.get('mechanism') or '').split())[:600]}"]
    for name in ("hypothesis", "comparison", "falsification"):
        if (card or {}).get(name):
            lines.append(f"Card {name}: {' '.join(str(card[name]).split())[:600]}")
    if train:
        lines.append(f"Its Train verdict (2016-2024, the only data its author saw): {train}")
    lines.append(f"```python\n{str(version.get('code') or '')[:16000]}\n```\nPARAMS overrides: "
                 f"{json.dumps(version.get('params') or {}, sort_keys=True)}")
    return "\n\n".join(lines)


def record(sha: str, review: Mapping[str, Any], audit: Mapping[str, Any], *, at: str, version: int) -> dict[str, Any]:
    """The record E1's look reads (`elane.reviewed`: the gate's shape), with the readers' models and E2's objective."""
    return {"sha": sha, "verdict": "pass", "audit": {"verdict": "pass", "model": audit.get("model"),
                                                       "route": audit.get("route")},
            "model": review.get("model"), "route": review.get("route"), "objective": OBJECTIVE, "version": int(version),
            "at": at, "source": "elane_e2"}


def holds(state: Mapping[str, Any] | None, sha: str) -> bool:
    """Whether a family's state carries the passed review and audit of program `sha` (E1's `reviewed`, read here)."""
    review = (state or {}).get(STATE_REVIEW) if isinstance(state, Mapping) else None
    review = review if isinstance(review, Mapping) else {}
    audit = review.get("audit") if isinstance(review.get("audit"), Mapping) else {}
    return review.get("sha") == sha and review.get("verdict") == "pass" and audit.get("verdict") == "pass"


__all__ = ["OBJECTIVE", "STATE_REVIEW", "DEFAULTS", "BOUNDS", "BAR_FIELDS", "LOT_FIELDS", "FACTS", "REVIEW", "cfg",
           "model_of", "level_refusals", "level_text", "grounded", "question", "record", "holds"]
