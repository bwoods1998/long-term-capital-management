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
   either. The ratio of two DIFFERENT symbols' levels (QQQ over SPY) is not scale-free in time: held against a
   constant it is refused as a level is. A taint pass over the module (module constants, PARAMS, names, what
   `ctx.bars.items()` and `.values()` yield, a lot's field by `[...]` or `.get`, a helper or a named lambda read again
   with each call's own arguments, numpy's comparison, arithmetic and table functions as the operators they are, a
   constant written as arithmetic or as text, comprehensions, `zip` taken apart in a loop, and what the program puts
   into a container of its own and reads back in the same function: `closes[s] = c[-1]`, `xs.append(px)`,
   `STATE["px"] = px`, each string key of a dict kept apart so a counter beside a price stays a counter); what it
   cannot follow (a tuple or a dict stored whole, a container read in another function, a level's digits, a level
   through a call it does not know) is left to the paid review, never refused on a guess.
   It runs in `elane_train.check_code`, so such a program is never stored or run: the researcher hears why.
1b. RUN-START DEPENDENCE, in the same pass (the integration review's seal-1). Every judged run starts flat: each
   Train span, Validation and the look, with `ctx.budget` the run's constant capital while `ctx.equity` moves. A
   program that reads its own profit since the run began (`ctx.equity / ctx.budget - 1 >= PARAMS["lock"]`, then a
   token size) keys its decisions to where the window starts, which live trading never repeats; the share screen's
   floor is built from windows of one long run and never sees that fresh-start behaviour, so its false-positive cap
   holds only for programs blind to their run's start. THE RUN'S DOLLARS are the sleeve's now (`ctx.equity`,
   `ctx.cash`, a lot's `value` and `pnl`, a closed lot's `net`) and the run's anchor (`ctx.budget`, `ctx.caps[sym]`).
   Refused: any of them compared with, offset by, bucketed by or clipped at a constant or a PARAMS value; and the
   sleeve's dollars now held against the anchor in any way (compared, subtracted, divided, multiplied by its
   reciprocal: a ratio among them). A constant over the run's dollars and their log are the run's dollars still
   (`1000.0 / ctx.equity`, `math.log(ctx.equity)`: the same profit written another way).
   Allowed: sizing proportional to them (`"usd": 0.5 * ctx.equity`, `min(ctx.cash, ctx.caps[s])`), a sign or zero
   check (`lot["pnl"] < 0`, `ctx.caps[s] <= 0`), and the position's own state among the sleeve's dollars now
   (`ctx.cash / ctx.equity`, a lot's `value` over `ctx.equity`, `pnl` over `value`).
1d. THE RUN'S CAPITAL FROM A LOT, in the same pass (the verification's seal-1 residual). The anchor need not come from
   ctx. The House sizes an entry as the asked share of the run's capital, so WHAT A LOT COST is that capital times a
   share the program chose itself. A program with no memory at all rebuilt it from its own lots (a lot's `qty` times
   its `entry` or `exit`, its `value` less its `pnl`, `exit` times `qty` less `net`), held `ctx.cash` or `ctx.equity`
   against it and was the profit lock again: lot for lot the same trades on synthetic stores, and the restart check
   passed it, for it keeps nothing in STATE. So a lot's `qty` and what a lot cost ARE the run's anchor. Refused: the
   sleeve's dollars now (`ctx.equity`, `ctx.cash`) held against them in any way, as against `ctx.budget`; and they
   against a constant or a PARAMS value, as every dollar of the run is. The pass follows the spellings: a number of
   shares times a price is dollars and dollars over a price a number of shares (`ctx.cash / px` against a lot's
   `qty`); a lot's own dollars now times or over anything but a constant read as what the lot cost from there on (its
   `value` over its `mark` is its qty, its `value` over its own return what it cost); the run's dollars stay the run's
   dollars through a product of two of them, a reciprocal, an exponent, their text (`float(str(ctx.equity))`, an
   f-string) and a call the pass does not know (`math.copysign(ctx.equity, 1)`). THE RUN'S DOLLARS COME FIRST IN A
   MIXED VALUE: plus, less, times or over a level, a log or a cross-symbol ratio they are the run's dollars still, and
   so is a value that may hold them and a level (a list of both, one name given each, the smaller of cash and a
   price). Read as the level, `(ctx.equity + px - px) / (ctx.budget + px - px)` was a ratio of two prices, and the
   lock passed. ctx's and a lot's counts (`ctx.weekday`, a lot's `held_sessions`) are of no unit and known to be: as
   unknowns they took the run's dollars out of sight (`ctx.equity * (ctx.weekday + 1)`). And THE RUN'S DOLLARS WRITTEN INTO
   AN INTENT'S "tag" are refused: the House keeps a lot's tag across a restart, so the first equity a run saw,
   carried from lot to lot, is the lock's memory where the restart check cannot see it (same trades as the lock on
   synthetic stores; the check matched every session).
   Allowed: A LOT'S OWN RETURN however it is written (`mark / entry`, `pnl / value`, `pnl / (qty * entry)`,
   `pnl / (value - pnl)`: a lot's own dollars against what a lot cost hold nothing of the sleeve's), a lot's average
   entry (`sum(qty * entry) / sum(qty)`: a price), a sign check, a count of sessions held, a size from the sleeve
   or from `ctx.budget`.
   THE COST, stated: an honest program that writes a lot's weight through its qty (`qty * price / ctx.equity`) or
   scales a lot's value by a ratio before setting it against the sleeve (`value * (1 - stop / mark) / ctx.equity`)
   is refused with this reason, and must write the weight as `lot["value"] / ctx.equity` (allowed, below). So is one
   that keeps a price and dollars in ONE value (a helper returning both in a tuple, one name used for each) and then
   reads the price back from it: the value is the run's dollars.
   WHAT THIS RULE CANNOT SEE, AND THE PAID REVIEW MUST (`REVIEW`, "RUN-START DEPENDENCE"; ELANE_E2.md says it too).
   (a) The position's own state used as the anchor. A lot's weight in the sleeve (`lot["value"] / ctx.equity`) and
   the sleeve's cash share (`ctx.cash / ctx.equity`) are allowed against a constant, and a weight is the asked share
   times the lot's own return times budget over equity: set against that return, or read in the lot's entry session,
   it is the run's profit, and nothing static tells it from an honest weight cap. A program built on it trades as
   the lock does and passes this rule and the restart check. (b) What the pass cannot follow: a function reached
   through an expression, a tuple or a dict stored whole, a container read in another function, a lot's tag read
   back as a number, a call the pass does not know on a value that is not the run's dollars; and the run's dollars
   plus, less, times or over such a value are unknown with it, never refused on a guess. (c) Memory in STATE:
   the first equity a run saw, kept there, passes this rule; the Train bar's restart check judges it.
1c. THE MEMORY RULE (`memory_refusals`; static, free; the integration review's seal-5). The swarm's one decider child
   runs every equity program and run in ONE interpreter (Train runs, the restart check, Validation, the sealed look),
   and the Gym's code rules (league/gym/safety.py) refuse attribute assignment but not a change to an object that
   hangs off an imported module (`np.typecodes.setdefault("anchor", x)`). Such an object is memory OUTSIDE STATE: it
   survives the restart check's fresh load (so a first-seen price kept there passes STATE and a deploy would clear it
   live), and it is shared by every program and run in the child, the look's run included. For the programs the swarm
   breeds the rule shuts the door whole: of `numpy` and `math` a program CALLS functions (`np.mean(x)`,
   `np.linalg.norm(x)`, `np.maximum.accumulate(x)`), reads constants and types (`np.nan`, `math.pi`, `np.float64`)
   and hands on a function the level rule knows (`key=np.abs`); any other object of a module read as a value (held,
   aliased, indexed, passed on, reached by `getattr`, imported by name) is refused, reader and writer alike. It runs
   in `elane_train.check_code` beside the level rule. Why here and not in league/gym/safety.py: that file is in the
   options execution fingerprint and the equity evidence identity, and a hardening rule there would reset every band
   proof; the root (one interpreter for every run) is E1's, for its next identity move.
1e. THE READING RULE (`reading_refusals`, `READING_CTX`; static, free; release E2.2). Most of the first programs the
   equity researcher wrote on the House read `ctx.bars[sym]` by key (`ctx.bars[sym]["close"]`) or as rows: every
   decide raised a TypeError, the version was disqualified, and each cost model dollars and one of its family's scored
   versions. What a program receives is E1's (league/equity/ctx.py; EQUITY.md "Reading ctx"), and the misreadings that
   can be SEEN in the source are refused here, before a version is stored or run, each with what to write instead:
   a symbol's bars read by key, by position or as rows, iterated, measured, unpacked or put into arithmetic (they are
   ONE object whose six arrays are read by attribute: `ctx.bars[sym].close`), or a field they do not have; a field ctx
   does not have; a lot or a closed lot read by attribute (each is a dict in a list: `lot["id"]`), a key it does not
   have, `ctx.positions` or `ctx.closed` read as a dict by symbol; `ctx.events` read by attribute or by an unknown
   flag; `ctx.prices[sym]` or `ctx.caps[sym]` (floats) subscripted; and, among the dicts `decide` returns, an intent
   with none or two of "buy", "sell", "cancel", an "at" that is neither "open" nor "close", a buy with neither
   "share" nor "usd" (or a constant size outside its range) and a sell that names a symbol or a whole lot instead of
   the lot's id. The pass follows a name only while EVERY binding of it in its function gives it the same kind of
   value (`bars = ctx.bars[sym]`, a loop over `ctx.positions`, `ctx.bars.items()`, a helper's parameter when every
   call hands it the same kind), and an intent only from `decide`'s own return (a list, a name appended to, a helper's
   return); a name bound two ways, a value through a call it does not know, a dict changed after it was written, a
   read inside a `try` that has a handler and a kind of value the program asks the type of (`isinstance(bars, dict)`:
   it reads it both ways on purpose) are left alone, never refused on a guess. It reads nothing but the source, so it
   says nothing of any market. It runs first of the three rules in `elane_train.check_code`: a refusal is recorded
   with its reason for the next brief and counts one of the family's write attempts (`train_max_attempts`), never one
   of its scored versions.
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
#: THE SLEEVE'S DOLLARS OF THE RUN (the module docstring, 1b). What the sleeve holds NOW: `ctx.equity`, `ctx.cash`, a
#: lot's `value` and `pnl`, a closed lot's `net`. THE RUN'S ANCHOR: `ctx.budget` (the Gym: the run's capital, a
#: constant) and `ctx.caps[sym]` (a share of it less the holding).
NOW_FIELDS = ("equity", "cash")
ANCHOR_FIELDS = ("budget",)
MONEY_KEYS = ("value", "pnl", "net")
#: A lot's share count (the module docstring, 1d): the capital it was bought with over its fill price.
QTY_KEY = "qty"
#: ctx's and a lot's COUNTS: of no unit, and KNOWN to be (an unknown value would take the run's dollars out of the pass's
#: sight: `ctx.equity * (ctx.weekday + 1) / (ctx.budget * (ctx.weekday + 1))`).
CTX_COUNTS = ("weekday", "session_of_month", "sessions_to_month_end")
LOT_COUNTS = ("held_sessions", "id")
#: A constant this close to zero is a sign check or an epsilon, never a level.
ZERO = 1e-6
#: Functions whose result keeps the units of their arguments (a mean of prices is a price).
KEEP = frozenset({
    "mean", "nanmean", "median", "nanmedian", "max", "min", "nanmax", "nanmin", "amax", "amin", "percentile",
    "nanpercentile", "quantile", "nanquantile", "sum", "nansum", "abs", "fabs", "absolute", "round", "around", "rint",
    "floor", "ceil", "trunc", "float", "int", "sqrt", "cumsum", "maximum", "minimum", "fmax", "fmin", "clip", "array",
    "asarray", "asanyarray", "ravel", "copy", "sort", "flatten", "concatenate", "hstack", "vstack", "stack", "where",
    "nan_to_num", "average", "convolve", "std", "nanstd", "var", "nanvar", "ptp", "diff", "ediff1d", "gradient", "sorted",
    "list", "tuple", "reversed", "full_like", "take", "float64", "float32", "squeeze", "atleast_1d", "next", "iter",
    "prod", "nanprod", "cumprod", "nancumprod", "nancumsum", "fsum", "reduce", "accumulate"})
#: Of those, the ones whose result on a LOG level is scale-free (a dispersion or a difference of logs).
SPREAD = frozenset({"std", "nanstd", "var", "nanvar", "ptp", "diff", "ediff1d", "gradient"})
#: The ones that combine their arguments: a level among them with a constant is a clip or a floor at a level.
COMBINE = frozenset({"max", "min", "maximum", "minimum", "fmax", "fmin", "clip", "where", "nanmax", "nanmin", "amax",
                     "amin"})
LOG = frozenset({"log", "log10", "log2", "log1p"})
EXP = frozenset({"exp", "expm1"})
#: Functions whose result carries no unit (a flag, a count, a correlation).
UNITLESS = frozenset({"isnan", "isfinite", "isinf", "len", "argmax", "argmin", "argsort", "sign", "count_nonzero",
                      "nonzero", "any", "all", "bool", "corrcoef", "range", "zip", "str"})
#: numpy's comparison functions: the operators they are (`np.greater(px, 400)` is `px > 400`).
COMPARES = frozenset({"greater", "greater_equal", "less", "less_equal", "equal", "not_equal", "isclose", "allclose",
                      "array_equal"})
#: numpy's arithmetic functions, by the operator each is.
ARITHMETIC: dict[str, type] = {"add": ast.Add, "subtract": ast.Sub, "multiply": ast.Mult, "divide": ast.Div,
                               "true_divide": ast.Div, "floor_divide": ast.FloorDiv, "mod": ast.Mod, "remainder": ast.Mod,
                               "fmod": ast.Mod, "power": ast.Pow, "float_power": ast.Pow, "pow": ast.Pow,
                               "divmod": ast.FloorDiv}
#: Functions that write a value as text (`float(str(ctx.equity))` is the same dollars read back).
TEXT = frozenset({"str", "format"})
#: Functions that place a value among the points of a table: a level placed among constants is a level bucket.
BUCKETS = frozenset({"digitize", "searchsorted", "interp"})
MODULES = frozenset({"np", "numpy", "math"})

_L, _G, _C, _U = "L", "G", "C", "U"
#: The sleeve's dollars now, the run's anchor, both met in one value; a ratio of two different symbols' levels.
_M, _B, _X, _K = "M", "B", "X", "K"
#: WHAT RIDES WITH THE RUN'S DOLLARS (the module docstring, 1d), so the pass can tell a lot's own return in dollars (its
#: pnl over what it cost: allowed) from the run's profit (the sleeve's dollars over what a lot cost: refused).
#: With M: `_SLEEVE`, ctx.equity or ctx.cash went in (without it the dollars are a lot's own: its value, pnl or net);
#: `_VALUE` and `_PNL`, a lot's value, and its pnl or a closed lot's net, went in. With B: `_CTX`, ctx.budget or
#: ctx.caps went in (without it the anchor is THE CAPITAL A LOT WAS BOUGHT WITH: its qty, its qty times a price, its
#: value less its pnl). With either: `_SHARES`, the dollars were divided by a price (a number of shares: a lot's qty,
#: cash over a price), so dollars over them are a price again; `_INV`, the dollars are written as a reciprocal
#: (`1 / ctx.equity`), so a product with them is a ratio.
_SLEEVE, _CTX, _VALUE, _PNL, _SHARES, _INV = "$S", "$A", "$v", "$p", "$q", "$i"
_RIDERS = frozenset({_SLEEVE, _CTX, _VALUE, _PNL, _SHARES, _INV})
#: A lot's dollar fields as the pass reads them (`_Levels._field`).
_LOT_DOLLARS: dict[str, frozenset[str]] = {
    **{key: frozenset({_M, _VALUE if key == "value" else _PNL}) for key in MONEY_KEYS},
    QTY_KEY: frozenset({_B, _SHARES})}
_NOW = frozenset({_M, _SLEEVE})
_ANCHOR = frozenset({_B, _CTX})
#: The container marks: ctx.prices, ctx.bars, one symbol's bars, PARAMS, ctx.caps, ctx.positions or ctx.closed, one lot.
_PRICES, _BARS, _BAR, _PARAMS, _CAPS, _LOTS, _LOT = "PRICES", "BARS", "BAR", "PARAMS", "CAPS", "LOTS", "LOT"
_CONTAINERS = frozenset({_PRICES, _BARS, _BAR, _PARAMS, _CAPS, _LOTS, _LOT})
#: The views of a container: `.items()`, `.values()`, `enumerate(...)`.
_ITEMS, _VALUES, _ENUM = "ITEMS", "VALUES", "ENUM"
_VIEWS = frozenset({_ITEMS, _VALUES, _ENUM})
_NONE: frozenset[str] = frozenset()
#: How deep a helper's call is followed with its call-site arguments.
CALL_DEPTH = 6
#: THE PROGRAM'S OWN CONTAINERS (`_Levels._store`). The methods that put ONE value in (the argument that is the value),
#: the ones that put an iterable's values in, and the separator of a container's name and one string key of it in the
#: pass's table of names (`STATE["px"]` is kept apart from `STATE["n"]`).
PUTS = {"append": 0, "add": 0, "appendleft": 0, "insert": 1}
PUTS_MANY = frozenset({"extend", "extendleft"})
_SEP = "\x00"
#: The entry of what a container holds under keys that are no string in the file (`closes[s] = ...`, an append): it
#: may sit under any key, so every string key's reading holds it too.
_ANY = _SEP + "*"


def _origin(tags: Iterable[str]) -> frozenset[str]:
    """Whose level a value is: "@SPY" (a symbol named in the file) or "@$s" (the symbol a variable holds)."""
    return frozenset(t for t in tags if t.startswith("@"))


def _norm(tags: Iterable[str]) -> frozenset[str]:
    """A value's unit: the run's dollars (X when the sleeve's dollars now and the run's anchor met, else M or B, with
    what rides with them: `_RIDERS`); then a level (L) over a log level (G), each with whose it is; a cross-symbol ratio
    (K); unknown (U); a constant (C); empty is unit-free."""
    t = set(tags)
    # THE RUN'S DOLLARS COME FIRST: a value that may hold them AND a level (a list of both, one name given each, the
    # smaller of cash and a price) is the run's dollars. Read as the level, `(ctx.equity + px - px) / (ctx.budget + px
    # - px)` was a ratio of two prices and the profit lock passed.
    if _X in t:
        return frozenset({_X})
    if _M in t and _B in t:
        if t & {_SLEEVE, _CTX}:
            return frozenset({_X})
        return frozenset({_B}) | (t & {_SHARES, _INV})  # a lot's dollars now with what it cost: the lot's own still
    if _M in t:
        return frozenset({_M}) | (t & {_SLEEVE, _VALUE, _PNL, _SHARES, _INV})
    if _B in t:
        return frozenset({_B}) | (t & {_CTX, _SHARES, _INV})
    for mark in (_L, _G):
        if mark in t:
            return frozenset({mark}) | _origin(t)
    if _K in t:
        return frozenset({_K})
    for mark in (_U, _C):
        if mark in t:
            return frozenset({mark})
    return _NONE


def _level(t: frozenset[str]) -> bool:
    return _L in t or _G in t


def _money(t: frozenset[str]) -> bool:
    return bool(t & {_M, _B, _X})


def _held(t: frozenset[str]) -> bool:
    """A value that may not be held against a constant: a level, a cross-symbol ratio, the run's dollars."""
    return _level(t) or _K in t or _money(t)


def _const(t: frozenset[str]) -> bool:
    return t == frozenset({_C})


def _meets(a: frozenset[str], b: frozenset[str]) -> bool:
    """The sleeve's dollars now on one side and the run's anchor on the other (or a value that already holds both). The
    anchor is ctx's (`ctx.budget`, `ctx.caps`) or the capital a lot was bought with (its qty, its qty times a price, its
    value less its pnl). ONE PAIR IS NO MEETING: a lot's own dollars now (its value, pnl or net, nothing of the
    sleeve's) against what a lot cost, which is the lot's own return written in dollars (`lot["pnl"] / (lot["qty"] *
    lot["entry"])`)."""
    both = a | b
    if not (_money(a) and _money(b)):
        return False
    if _X in both:
        return True
    return _M in both and _B in both and bool(both & {_SLEEVE, _CTX})


def _dollars(t: frozenset[str]) -> frozenset[str]:
    """The marks of the run's dollars in a value, with what rides with them."""
    return t & ({_M, _B, _X} | _RIDERS)


def _lots_own(t: frozenset[str]) -> bool:
    """A lot's own dollars now (its value, pnl or net) with nothing of the sleeve's or the anchor's in them."""
    return _M in t and not t & {_B, _X, _SLEEVE}


def _scaled(m: frozenset[str], by: frozenset[str]) -> frozenset[str]:
    """The run's dollars `m` times or over a value `by` that is none of them. By a constant they are what they were.
    A LOT'S OWN DOLLARS NOW times or over anything else stop being its dollars now: its value over its mark is its qty,
    its value over its own return (or its pnl over that return less one) is what it cost. They read as the capital the
    lot was bought with from there on."""
    if _const(by) or not _lots_own(m):
        return m
    return frozenset({_B}) | (m & {_SHARES, _INV})


def _cross(a: frozenset[str], b: frozenset[str]) -> bool:
    """Two levels of DIFFERENT symbols, each known."""
    return bool(_origin(a)) and bool(_origin(b)) and _origin(a) != _origin(b)


def _what(t: frozenset[str]) -> str:
    if _level(t):
        return "a price or volume level (or its log)"
    if _K in t:
        return "the ratio of two different symbols' prices"
    return ("the sleeve's dollars of this run (ctx.equity, ctx.cash, ctx.budget, ctx.caps, a lot's value, pnl or qty, "
            "or what a lot cost)")


TAGGED = ("keeps the run's dollars in a lot's tag (the House keeps a tag across a restart: the sleeve's dollars of an "
          "earlier call carried from lot to lot are a memory of where the run started)")
ANCHORED = ("the sleeve's dollars now against the run's anchor (ctx.budget, ctx.caps, or the capital a lot was bought "
            "with: its qty times a price, its value less its pnl): the run's own profit since it began, which reads "
            "where the run starts")


def _key(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _whose(node: ast.AST | None) -> frozenset[str]:
    """The origin mark of a symbol key: a literal symbol, or the variable that holds one."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return frozenset({"@" + node.value})
    if isinstance(node, ast.Name):
        return frozenset({"@$" + node.id})
    return _NONE


class _Levels:
    """The taint pass (the module docstring, 1). `found`: [(line, why)]."""

    def __init__(self, tree: ast.Module):
        self.tree = tree
        self.found: list[tuple[int, str]] = []
        self.record = False
        self.returns: dict[str, frozenset[str]] = {}
        #: The file's helpers: name -> (its def, the names in scope where it is defined), for a call's own arguments.
        self.functions: dict[str, tuple[ast.FunctionDef | ast.AsyncFunctionDef, dict[str, set[str]]]] = {}
        self.modules = set(MODULES)
        self._ret: list[set[str]] = []
        self._accum: set[str] = set()
        self._stack: list[str] = []
        self._memo: dict[tuple, frozenset[str]] = {}
        self._early = 0  # above zero inside a function body's first reading (`_twice`)

    # ------------------------------------------------------------------ the module
    def run(self) -> list[tuple[int, str]]:
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                self.modules.update(a.asname or a.name.split(".")[0] for a in node.names)
        for record in (False, False, True):  # helpers' returns settle first; refusals are kept on the last pass only
            self.record = record
            self._memo = {}
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

    def _twice(self, body: Sequence[ast.stmt], env: dict[str, set[str]], test: ast.AST | None = None, *,
               loop: bool = True) -> None:
        """A body that may run again is read TWICE, so a name assigned late reaches the reads above it.
        A LOOP's first reading only gathers what each name can hold; refusals are kept on its second reading alone.
        Kept on the first, a placeholder was read as the number it starts as (`prev = None` ... `px / prev - 1` ...
        `prev = px`; `lo = 1e9` ... `if x < lo: lo = x`) and a scale-free program was refused for a level it never
        holds against a constant.
        A FUNCTION's body (`loop` False) keeps its refusals on both readings: the first is the order the statements
        run in, so a constant held against a level is refused though its name is given a level further down
        (`x = 400.0` ... `px > x` ... `x = px`). What carries from one call to the next is the program's own
        containers (STATE), so on that first reading a key of one that holds nothing with a unit yet is read as
        unknown (`_early`, `_keyed`): the price a program will put there is not the None it starts as."""
        held = self.record
        if loop:
            self.record = False
        else:
            self._early += 1
        try:
            if test is not None:
                self._tag(test, env)
            self._block(body, env)
        finally:
            self.record = held
            if not loop:
                self._early -= 1
        if test is not None:
            self._tag(test, env)
        self._block(body, env)

    @staticmethod
    def _params(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda) -> list[ast.arg]:
        args = node.args
        return [*args.posonlyargs, *args.args, *args.kwonlyargs, *([args.vararg] if args.vararg else []),
                *([args.kwarg] if args.kwarg else [])]

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, env: dict[str, set[str]]) -> None:
        inner = {k: set(v) for k, v in env.items()}
        args = node.args
        for a in self._params(node):
            inner[a.arg] = {_U}
        for default in [*args.defaults, *[d for d in args.kw_defaults if d is not None]]:
            self._tag(default, env)
        self._ret.append(set())
        self._twice(node.body, inner, loop=False)
        self.returns[node.name] = _norm(self._ret.pop())
        self.functions[node.name] = (node, env)
        env.setdefault(node.name, set()).add(_U)

    def _invoke(self, name: str, node: ast.Call, args: Sequence[frozenset[str]],
                keywords: Mapping[str, frozenset[str]]) -> frozenset[str]:
        """A call of one of the file's helpers, read with THIS call's arguments (a level handed to `sma(xs, n)` comes back
        a level; a level and a constant handed to `above(x, k)` meet inside it). A helper that calls itself, or a chain
        deeper than `CALL_DEPTH`, reads as the helper did with unknown arguments."""
        fn, home = self.functions[name]
        # A silent reading records nothing and an early one reads the program's own empty keys as unknown: each kind
        # of reading remembers its own.
        memo = (name, tuple(args), tuple(sorted(keywords.items())), self.record, self._early > 0)
        if memo in self._memo:
            return self._memo[memo]
        if name in self._stack or len(self._stack) >= CALL_DEPTH:
            return self.returns.get(name, frozenset({_U})) or _NONE
        inner = {k: set(v) for k, v in home.items()}
        spec = fn.args
        positional = [*spec.posonlyargs, *spec.args]
        defaults = dict(zip([a.arg for a in positional][len(positional) - len(spec.defaults):], spec.defaults))
        defaults.update({a.arg: d for a, d in zip(spec.kwonlyargs, spec.kw_defaults) if d is not None})
        for a in self._params(fn):
            inner[a.arg] = {_U}
        for a, default in defaults.items():
            inner[a] = set(self._tag(default, home)) or {"_free"}
        for a, tag in zip(positional, args):
            inner[a.arg] = set(tag) or {"_free"}
        for key, tag in keywords.items():
            if key in inner:
                inner[key] = set(tag) or {"_free"}
        self._ret.append(set())
        self._stack.append(name)
        try:
            self._twice(fn.body, inner, loop=False)
        finally:
            self._stack.pop()
            out = _norm(self._ret.pop())
        self._memo[memo] = out
        return out

    def _stmt(self, node: ast.stmt, env: dict[str, set[str]]) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self._function(node, env)
        elif isinstance(node, ast.Assign):
            if isinstance(node.value, ast.Lambda):  # `last = lambda b: b.close[-1]`: a helper, read at each call
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        helper = ast.FunctionDef(name=target.id, args=node.value.args, decorator_list=[],
                                                 body=[ast.copy_location(ast.Return(value=node.value.body), node.value)])
                        self._function(ast.copy_location(helper, node.value), env)
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
            self._loop(node.target, node.iter, env)
            self._twice(node.body, env)
            self._block(node.orelse, env)
        elif isinstance(node, ast.While):
            self._twice(node.body, env, test=node.test)
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
            if isinstance(value, ast.Dict) and target.id != "PARAMS":
                # info = {"px": c[-1], "n": 20}: each string key is read back as itself (never PARAMS: a PARAMS value
                # is a constant whatever number the file declares for it, zero included)
                for k, v in zip(value.keys, value.values):
                    if k is not None:
                        slot = target.id + (_SEP + str(_key(k)) if _key(k) is not None else _ANY)
                        env.setdefault(slot, set()).update(self._tag(v, env) or {"_free"})
        elif isinstance(target, (ast.Tuple, ast.List)):
            if isinstance(value, (ast.Tuple, ast.List)) and len(value.elts) == len(target.elts):
                for t, v in zip(target.elts, value.elts):
                    self._assign(t, v, self._tag(v, env), env)
            else:
                for t in target.elts:
                    self._assign(t, None, self._element(tag) if tag else tag, env)
        elif isinstance(target, ast.Starred):
            self._assign(target.value, None, tag, env)
        elif isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name):
            self._tag(target.slice, env)  # closes[s] = c[-1], STATE["px"] = px: read back as what was put in
            self._tagged(target, target.slice, tag)
            self._store(target.value.id, _key(target.slice), value, tag, env)
        else:  # an attribute, a nested container: evaluated, never followed (left to the paid review)
            self._tag(target, env)

    def _tagged(self, node: ast.AST, key: ast.AST | str | None, tag: frozenset[str]) -> None:
        """An intent's "tag" is the one text of a program's the House keeps with a lot and hands back (`lot["tag"]`), a
        restart of the decider included. A label is what it is for; the run's dollars written there (`"tag":
        str(ctx.equity)`) are the sleeve's dollars of an earlier call, read back from the next lot: the profit lock's
        memory, which the Train bar's restart check cannot see (it resets STATE, never a lot)."""
        name = key if isinstance(key, str) else _key(key) if key is not None else None
        if name == "tag" and _money(self._unit(tag)):
            self._refuse(node, TAGGED)

    def _store(self, name: str, key: str | None, value: ast.AST | None, tag: frozenset[str],
               env: dict[str, set[str]]) -> None:
        """WHAT A PROGRAM PUTS INTO A CONTAINER OF ITS OWN IS WHAT IT READS BACK FROM IT (`closes[s] = c[-1]` then
        `closes["SPY"] > 400`; `xs.append(px)`; `STATE["px"] = px`): the container's name carries the unit of what was
        put in. A string key is kept apart from the others (`name<_SEP>key`), so a counter beside a price stays a
        counter. Only a single value is followed: a tuple, a list or a dict stored whole mixes units (a symbol, a
        return and a price in one row) and is left to the paid review, as is a container read in another function."""
        if name == "PARAMS" or name in self.modules or isinstance(value, (ast.Tuple, ast.List, ast.Set, ast.Dict)):
            return
        if tag & {_LOT, _LOTS}:
            unit = {_LOTS}  # the program's own list of lots: its rows are lots
        elif tag & (_CONTAINERS | _VIEWS):
            return
        else:
            unit = set(_norm(tag)) or {"_free"}
        if key is None:  # by a key that is no string, or appended: whose level each is is not kept
            unit = {t for t in unit if not t.startswith("@")} or {"_free"}
            env.setdefault(name + _ANY, set()).update(unit)
        env.setdefault(name if key is None else name + _SEP + key, set()).update(unit)

    def _loop(self, target: ast.AST, iterable: ast.AST, env: dict[str, set[str]]) -> None:
        """A loop's (or a comprehension's) target over its iterable; `for s, px in zip(symbols, levels)` binds each name
        to its own argument's elements."""
        if (isinstance(iterable, ast.Call) and isinstance(iterable.func, ast.Name) and iterable.func.id == "zip"
                and not iterable.keywords and isinstance(target, (ast.Tuple, ast.List))
                and len(target.elts) == len(iterable.args)
                and not any(isinstance(a, ast.Starred) for a in [*iterable.args, *target.elts])):
            for t, a in zip(target.elts, iterable.args):
                self._bind(t, self._tag(a, env), env)
        else:
            self._bind(target, self._tag(iterable, env), env)

    def _bind(self, target: ast.AST, tag: frozenset[str], env: dict[str, set[str]]) -> None:
        """A loop's (or a comprehension's) target over an iterable: `for s, b in ctx.bars.items()` gives the key and one
        symbol's bars; `for i, lot in enumerate(ctx.positions)` a count and a lot."""
        pair = isinstance(target, (ast.Tuple, ast.List)) and len(target.elts) == 2
        if pair and _ITEMS in tag:
            self._assign(target.elts[0], None, frozenset({_U}), env)
            self._assign(target.elts[1], None, self._element((tag - {_ITEMS}) | {_VALUES}), env)
        elif pair and _ENUM in tag:
            self._assign(target.elts[0], None, _NONE, env)
            self._assign(target.elts[1], None, self._element(tag - {_ENUM}), env)
        else:
            self._assign(target, None, self._element(tag), env)

    # ------------------------------------------------------------------ expressions
    @staticmethod
    def _element(tag: frozenset[str]) -> frozenset[str]:
        """What iterating a value yields: a level array's elements are levels; ctx's containers yield keys, their
        `.values()` what they hold; ctx.positions its lots."""
        if _VALUES in tag:
            for mark, held in ((_PRICES, _L), (_CAPS, _B), (_BARS, _BAR), (_LOTS, _LOT), (_PARAMS, _C)):
                if mark in tag:
                    return _ANCHOR if held == _B else frozenset({held})
            return frozenset({_U})
        if tag & _VIEWS:
            return frozenset({_U})
        if _LOTS in tag:
            return frozenset({_LOT})
        if tag & _CONTAINERS:
            return frozenset({_U})
        return _norm(tag) if tag else _NONE

    def _unit(self, tag: frozenset[str]) -> frozenset[str]:
        """An argument's unit: `ctx.prices.values()` is levels, `ctx.caps.values()` the run's anchor."""
        if _VALUES in tag and tag & {_PRICES, _CAPS}:
            return self._element(tag)
        return _norm(tag)

    def _name(self, name: str, env: dict[str, set[str]]) -> frozenset[str]:
        if name == "PARAMS":
            return frozenset({_PARAMS})
        held = env.get(name)
        if held is None:
            return frozenset({_U})
        marks = {t for t in held if t in _CONTAINERS or t in _VIEWS}
        if marks:
            return frozenset(marks) | _origin(held)
        return _norm(t for t in held if t != "_free")

    def _own(self, holder: ast.AST, key: str | None, env: dict[str, set[str]]) -> frozenset[str] | None:
        """What the program itself put under one string key of a container of its own (`_store`, a dict literal), or
        None when it put nothing there by that key. What ctx gives (its lots, bars, prices, caps, params) is never the
        program's own, whatever the program writes into it (`_keyed`)."""
        if key is None or not isinstance(holder, ast.Name) or holder.id == "PARAMS" or holder.id + _SEP + key not in env:
            return None
        own = self._name(holder.id + _SEP + key, env)
        if holder.id + _ANY in env:  # what went in under a key the file does not spell may sit under this one
            own = self._join([own, self._name(holder.id + _ANY, env)])
        return own

    def _keyed(self, holder: ast.AST, base: frozenset[str], slice_: ast.AST | None,
               env: dict[str, set[str]]) -> frozenset[str]:
        """`holder[key]` (or `holder.get(key)`): what the program put under that string key itself (`_own`), else the
        field or element of `base` (`_subscript`). A dict of levels the program built, read by a key written as a
        symbol is (upper case), is that symbol's level (`closes["QQQ"] / closes["SPY"]` is a ratio of two different
        symbols'; `stats["hi"] / stats["lo"]` is not)."""
        key = _key(slice_) if slice_ is not None else None
        own = None if base & (_CONTAINERS | _VIEWS) else self._own(holder, key, env)
        out = self._subscript(base, key, slice_)
        if self._early and isinstance(holder, ast.Name) and not base and not (own if own is not None else out):
            # A function's first reading (`_twice`): a container of the program's own that holds nothing with a unit
            # yet, under this key or at all. What a later statement puts there (a price kept from the last call) is
            # read on the second reading; here it is unknown, never the None or zero it starts as.
            return frozenset({_U})
        if own is not None:
            # The program's own key. Under a name the House uses for a lot's field ("entry", "pnl"), or in a value the
            # pass cannot place (a helper's argument), it may be the House's row all the same: both readings hold, so
            # writing a zero over a lot's entry launders nothing.
            return self._join([own, out]) if (key in LOT_FIELDS or key in _LOT_DOLLARS or _U in base) else own
        if key and key == key.upper() and any(ch.isalpha() for ch in key) and isinstance(holder, ast.Name) \
                and _level(base) and _level(out):
            out = frozenset(t for t in out if not t.startswith("@")) | {"@" + key}
        return out

    def _field(self, base: frozenset[str], name: str | None) -> frozenset[str] | None:
        """A named field of one symbol's bars or of one lot (an attribute, a string key or a `.get`), or None for a base
        that is neither."""
        if _BAR in base:
            return (frozenset({_L}) | _origin(base)) if name in BAR_FIELDS else _NONE if name == "ret" else frozenset({_U})
        if _LOT in base:
            if name in LOT_FIELDS:
                return frozenset({_L})
            return _NONE if name in LOT_COUNTS else _LOT_DOLLARS.get(str(name), frozenset({_U}))
        return None

    def _subscript(self, base: frozenset[str], key: str | None, slice_: ast.AST | None = None) -> frozenset[str]:
        if _VIEWS & base:
            return frozenset({_U})
        if _PRICES in base:
            return frozenset({_L}) | _whose(slice_)
        if _BARS in base:
            return frozenset({_BAR}) | _whose(slice_)
        field = self._field(base, key)
        if field is not None:
            return field
        if _PARAMS in base:
            return frozenset({_C})
        if _CAPS in base:
            return _ANCHOR
        if _LOTS in base:
            return frozenset({_LOTS if isinstance(slice_, ast.Slice) else _LOT})
        if key in LOT_FIELDS:
            return frozenset({_L})
        if key in _LOT_DOLLARS and _U in base:  # a lot handed around (a helper's argument): never the program's own
            return _LOT_DOLLARS[key]
        return _norm(base) if base else _NONE

    def _attribute(self, base: frozenset[str], attr: str, module: bool) -> frozenset[str]:
        if attr == "prices":
            return frozenset({_PRICES})
        if attr == "bars":
            return frozenset({_BARS})
        if attr == "params":
            return frozenset({_PARAMS})
        if attr == "caps":
            return frozenset({_CAPS})
        if attr in ("positions", "closed"):
            return frozenset({_LOTS})
        if attr in CTX_COUNTS and not module:
            return _NONE
        if attr in NOW_FIELDS and not module:
            return _NOW
        if attr in ANCHOR_FIELDS and not module:
            return _ANCHOR
        field = self._field(base, attr)
        if field is not None:
            return field
        return frozenset({_U})  # np.nan, math.pi, anything else: no level

    def _fold(self, node: ast.AST | None, depth: int = 0) -> float | None:
        """The number a constant expression is (`400 + 0`, `2 * 200`, `float('400')`, `-5`), or None for anything that
        reads a name: a constant written as arithmetic or as text is still a constant."""
        if node is None or depth > 12:
            return None
        if isinstance(node, ast.Constant):
            v = node.value
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                return None
            return float(v) if math.isfinite(float(v)) else None
        try:
            if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
                x = self._fold(node.operand, depth + 1)
                return None if x is None else (-x if isinstance(node.op, ast.USub) else x)
            if isinstance(node, ast.BinOp):
                a, b = self._fold(node.left, depth + 1), self._fold(node.right, depth + 1)
                if a is None or b is None:
                    return None
                if isinstance(node.op, ast.Add):
                    out = a + b
                elif isinstance(node.op, ast.Sub):
                    out = a - b
                elif isinstance(node.op, ast.Mult):
                    out = a * b
                elif isinstance(node.op, ast.Div):
                    out = a / b
                elif isinstance(node.op, ast.FloorDiv):
                    out = a // b
                elif isinstance(node.op, ast.Mod):
                    out = a % b
                elif isinstance(node.op, ast.Pow) and abs(a) <= 1e6 and abs(b) <= 64:
                    out = a ** b
                else:
                    return None
                return float(out) if isinstance(out, (int, float)) and math.isfinite(out) else None
            if isinstance(node, ast.Call) and len(node.args) == 1 and not node.keywords:
                func = node.func
                name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else None
                if name in ("float", "int", "float64", "float32"):
                    text = _key(node.args[0])
                    x = float(text.strip()) if text is not None else self._fold(node.args[0], depth + 1)
                    if x is None or not math.isfinite(x):
                        return None
                    return float(int(x)) if name == "int" else x
                if name in ("abs", "fabs"):
                    x = self._fold(node.args[0], depth + 1)
                    return None if x is None else abs(x)
        except (ArithmeticError, ValueError, TypeError):
            return None
        return None

    def _tag(self, node: ast.AST | None, env: dict[str, set[str]]) -> frozenset[str]:
        if node is None:
            return _NONE
        if isinstance(node, (ast.Constant, ast.UnaryOp, ast.BinOp, ast.Call)):
            v = self._fold(node)
            if v is not None:
                return _NONE if abs(v) <= ZERO else frozenset({_C})
            if isinstance(node, ast.Constant):
                return _NONE
        if isinstance(node, ast.Name):
            return self._name(node.id, env)
        if isinstance(node, ast.Attribute):
            base = self._tag(node.value, env)
            return self._attribute(base, node.attr, isinstance(node.value, ast.Name) and node.value.id in self.modules)
        if isinstance(node, ast.Subscript):
            base = self._tag(node.value, env)
            self._tag(node.slice, env)
            return self._keyed(node.value, base, node.slice, env)
        if isinstance(node, ast.Call):
            return self._call(node, env)
        if isinstance(node, ast.BinOp):
            left, right = self._tag(node.left, env), self._tag(node.right, env)
            if isinstance(node.op, (ast.Add, ast.Sub)):  # x + 0, x - 0, 0 + x: x itself (a constant stays one)
                zero = self._fold(node.right)
                if zero is not None and abs(zero) <= ZERO:
                    return _norm(left)
                zero = self._fold(node.left)
                if zero is not None and abs(zero) <= ZERO and isinstance(node.op, ast.Add):
                    return _norm(right)
            return self._binop(node, left, node.op, right)
        if isinstance(node, ast.UnaryOp):
            inner = self._tag(node.operand, env)
            return _NONE if isinstance(node.op, ast.Not) else _norm(inner) if inner else _NONE
        if isinstance(node, ast.Compare):
            tags = [self._tag(node.left, env)] + [self._tag(c, env) for c in node.comparators]
            for op, a, b in zip(node.ops, tags, tags[1:]):
                if isinstance(op, (ast.In, ast.NotIn, ast.Is, ast.IsNot)):
                    continue
                self._compare(node, self._unit(a), self._unit(b))
            return _NONE
        if isinstance(node, ast.BoolOp):
            return _norm(t for v in node.values for t in self._tag(v, env))
        if isinstance(node, ast.IfExp):
            self._tag(node.test, env)
            return self._join([self._tag(node.body, env), self._tag(node.orelse, env)])
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            return self._join([self._tag(e, env) for e in node.elts], many=True)
        if isinstance(node, ast.Dict):
            for k in node.keys:
                self._tag(k, env)
            values = [self._tag(v, env) for v in node.values]
            for k, v in zip(node.keys, values):
                self._tagged(node, k, v)
            return self._join(values, many=True)
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
            inner = {k: set(v) for k, v in env.items()}
            for gen in node.generators:
                self._loop(gen.target, gen.iter, inner)
                for cond in gen.ifs:
                    self._tag(cond, inner)
            if isinstance(node, ast.DictComp):
                self._tag(node.key, inner)
                return self._join([self._tag(node.value, inner)], many=True)
            return self._join([self._tag(node.elt, inner)], many=True)
        if isinstance(node, ast.Lambda):
            inner = {k: set(v) for k, v in env.items()}
            for a in self._params(node):
                inner[a.arg] = {_U}
            self._tag(node.body, inner)
            return frozenset({_U})
        if isinstance(node, ast.Starred):
            return self._tag(node.value, env)
        if isinstance(node, ast.NamedExpr):
            tag = self._tag(node.value, env)
            self._assign(node.target, node.value, tag, env)
            return tag
        if isinstance(node, (ast.JoinedStr, ast.FormattedValue)):
            # f"{ctx.equity}": the run's dollars written as text are the run's dollars read back (`TEXT`); a level's
            # digits stay unknown, as through `str`.
            parts = node.values if isinstance(node, ast.JoinedStr) else [node.value, node.format_spec]
            tags = [self._unit(self._tag(part, env)) for part in parts if part is not None]
            if any(_money(t) for t in tags):
                return _norm(m for t in tags if _money(t) for m in _dollars(t))
            return frozenset({_U})
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.expr):
                self._tag(child, env)
        return frozenset({_U})

    @staticmethod
    def _join(tags: Sequence[frozenset[str]], *, many: bool = False) -> frozenset[str]:
        """Several values as one: their unit; lots stay lots (`many`: a collection of them is the lots)."""
        marks = {t for tag in tags for t in tag}
        if marks & {_LOT, _LOTS}:
            return frozenset({_LOTS if many or _LOTS in marks else _LOT})
        if _BAR in marks and not many:
            return frozenset({_BAR}) | _origin(marks)
        return _norm(marks)

    def _compare(self, node: ast.AST, a: frozenset[str], b: frozenset[str]) -> None:
        a, b = _norm(a), _norm(b)
        for x, y in ((a, b), (b, a)):
            if _held(x) and _const(y):
                self._refuse(node, f"compares {_what(x)} with a constant or a PARAMS value")
                return
        if _meets(a, b):
            self._refuse(node, f"compares {ANCHORED}")
        elif (_money(a) and _level(b)) or (_money(b) and _level(a)):
            self._refuse(node, "compares a price level with the sleeve's dollars (a known amount at the run's start)")

    def _call(self, node: ast.Call, env: dict[str, set[str]]) -> frozenset[str]:
        func = node.func
        if isinstance(func, ast.Name) and func.id == "getattr" and len(node.args) >= 2 and _key(node.args[1]) is not None:
            base = self._tag(node.args[0], env)  # getattr(ctx, "bars"): the attribute it names
            for extra in node.args[2:]:
                self._tag(extra, env)
            return self._attribute(base, str(_key(node.args[1])), False)
        raw = [self._tag(a, env) for a in node.args]
        named = {k.arg: self._tag(k.value, env) for k in node.keywords if k.arg}
        for k in node.keywords:
            if not k.arg:
                self._tag(k.value, env)
        args = raw + list(named.values())
        if isinstance(func, ast.Attribute):
            base = self._tag(func.value, env)
            name = func.attr
            if base & _CONTAINERS and not base & _VIEWS:
                if name == "get":
                    return self._subscript(base, _key(node.args[0]) if node.args else None, node.args[0] if node.args else None)
                if name in ("items", "values"):
                    return frozenset({_ITEMS if name == "items" else _VALUES}) | base
                if name == "keys":
                    return frozenset({_U})
            if name == "get" and node.args and isinstance(func.value, ast.Name) and not base & (_CONTAINERS | _VIEWS) \
                    and (_held(base) or self._own(func.value, _key(node.args[0]), env) is not None):
                # STATE.get("px", 0.0), closes.get("SPY"): what the program put there, or the default
                return self._join([self._keyed(func.value, base, node.args[0], env), *raw[1:]])
            if name == "get" and node.args and (_key(node.args[0]) in LOT_FIELDS or _key(node.args[0]) in _LOT_DOLLARS):
                return self._subscript(base, _key(node.args[0]), node.args[0])  # a lot's field by .get, as by [...]
            if isinstance(func.value, ast.Name) and not base & (_CONTAINERS | _VIEWS):
                holder = func.value.id  # a container of the program's own: what is put in is what is read back
                if name in PUTS and len(node.args) > PUTS[name]:
                    self._store(holder, None, node.args[PUTS[name]], raw[PUTS[name]], env)
                elif name in PUTS_MANY and node.args:
                    self._store(holder, None, None, self._element(raw[0]), env)
                elif name == "setdefault" and len(node.args) >= 2:
                    self._store(holder, _key(node.args[0]), node.args[1], raw[1], env)
                elif name == "update":
                    for k in node.keywords:
                        if k.arg:
                            self._store(holder, k.arg, k.value, named[k.arg], env)
                    for a in node.args:
                        if isinstance(a, ast.Dict):
                            for dk, dv in zip(a.keys, a.values):
                                if dk is not None:
                                    self._store(holder, _key(dk), dv, self._tag(dv, env), env)
            method = not (isinstance(func.value, ast.Name) and func.value.id in self.modules)
            if method:
                args = [base] + args  # a method of a value (close.mean()): the value is its first argument
        elif isinstance(func, ast.Name):
            name, method = func.id, False
            if name == "dict":  # dict(buy="SPY", share=0.5, tag=...): an intent written as a call
                for arg, tag in named.items():
                    self._tagged(node, arg, tag)
            if name in self.functions:
                return self._invoke(name, node, raw, named)
            if name in self.returns:
                return self.returns[name] or _NONE
        else:
            self._tag(func, env)
            return frozenset({_U})
        if name == "enumerate" and args:
            return frozenset({_ENUM}) | (args[0] - _VIEWS)
        if name in ("list", "tuple", "sorted", "reversed", "filter", "iter") and any(_LOTS in a for a in args):
            return frozenset({_LOTS})
        if name in ("max", "min", "next") and args and _LOTS in args[0] and len(raw) <= 1:
            return frozenset({_LOT})  # max(ctx.positions, key=...): one lot
        units = [self._unit(a) for a in args]
        direct = [*node.args, *(k.value for k in node.keywords if k.arg)]
        if method:
            direct = [func.value, *direct]
        if name in COMPARES and len(units) >= 2:
            self._compare(node, units[0], units[1])
            return _NONE
        if name in ARITHMETIC and len(units) >= 2:
            return self._binop(node, units[0], ARITHMETIC[name](), units[1])
        if name in BUCKETS and len(units) >= 2:
            for x, y in ((units[0], units[1]), (units[1], units[0])):
                if _held(x) and _const(y):
                    self._refuse(node, f"places {_what(x)} among constants ({name}: a level bucket)")
                    break
            return _NONE
        consts = [u for u, a in zip(units, direct)
                  if _const(u) and not (isinstance(a, ast.Name) and a.id in self._accum)]
        if name in COMBINE and len(units) > 1 and consts:
            held = next((u for u in units if _held(u)), None)
            if held is not None:
                self._refuse(node, f"clips or floors {_what(held)} against a constant or a PARAMS value ({name})"
                             if not _level(held) else
                             f"clips or floors a price or volume level against a constant or a PARAMS value ({name})")
        if name in TEXT and any(_money(u) for u in units):
            # str(ctx.equity), "{}".format(ctx.cash): the run's dollars written as text are the run's dollars read back
            return _norm(t for u in units if _money(u) for t in _dollars(u))
        if name in UNITLESS:
            return _NONE
        if name in LOG:
            first = units[0] if units else _NONE
            if _L in first:
                return frozenset({_G}) | _origin(first)
            if _money(first):
                return first  # log(ctx.equity): the run's dollars still (against a constant, or the anchor's log)
            return frozenset({_U}) if _G in first else first
        if name in EXP:
            first = units[0] if units else _NONE
            if _G in first:
                return frozenset({_L}) | _origin(first)
            if _money(first):
                return first
            return frozenset({_U}) if _L in first else first
        if name in KEEP:
            joined = _norm(t for u in units for t in u)
            if name in SPREAD and _G in joined:
                return _NONE
            digits = direct[1:]  # round(px, -1), np.round(px, -1), px.round(-1): a negative ndigits is a level grid
            if name in ("round", "around") and units and _held(units[0]) and \
                    any(isinstance(a, ast.UnaryOp) and isinstance(a.op, ast.USub) for a in digits):
                self._refuse(node, "rounds a price or volume level to a fixed grid (a level bucket)" if _level(units[0])
                             else f"rounds {_what(units[0])} to a fixed grid (a bucket)")
            return joined
        if any(_money(u) for u in units):
            # A call the pass does not know, handed the run's dollars (math.copysign(ctx.equity, 1), np.dot of qtys and
            # entries, x.item()): the run's dollars still. A level through an unknown call stays unknown (above).
            return _norm(t for u in units if _money(u) for t in _dollars(u))
        return frozenset({_U})

    def _ratio(self, node: ast.AST, a: frozenset[str], b: frozenset[str], verb: str,
               met: frozenset[str]) -> frozenset[str]:
        """The run's dollars `a` TIMES the run's dollars `b` (a division hands `b` in inverted). The sleeve's dollars
        now with the run's anchor are refused whichever way they are written (`met` is what the caller reads on).
        One of the two inverted, they are a ratio: of no unit (cash over equity, a lot's pnl over what it cost: the
        position's own state), or a price when one side is a number of shares (a lot's cost over its qty). Neither or
        both inverted, dollars times dollars: the run's dollars still, never a value of no unit."""
        if _meets(a, b):
            self._refuse(node, f"{verb} {ANCHORED}")
            return met
        if (_INV in a) != (_INV in b):
            return frozenset({_L}) if (_SHARES in a) != (_SHARES in b) else _NONE
        return _norm([*_dollars(a), *_dollars(b)]) - {_SHARES}

    def _binop(self, node: ast.AST, a: frozenset[str], op: ast.operator, b: frozenset[str]) -> frozenset[str]:
        a, b = _norm(a), _norm(b)
        if isinstance(op, (ast.Add, ast.Sub)):
            for x, y in ((a, b), (b, a)):
                if _held(x) and _const(y):
                    self._refuse(node, f"offsets {_what(x)} by a constant or a PARAMS value")
                    break
            if _meets(a, b):
                self._refuse(node, f"sets {ANCHORED}")
                return frozenset({_X})
            if _L in a and _L in b:
                return frozenset({_L}) | _origin(a) | _origin(b)
            if _G in a and _G in b:
                if isinstance(op, ast.Sub):
                    return frozenset({_K}) if _cross(a, b) else _NONE
                return frozenset({_G}) | _origin(a) | _origin(b)
            if _U in a or _U in b:
                return frozenset({_U})
            if _money(a) or _money(b):  # before a level's turn: the run's dollars plus a price are the run's dollars
                if _lots_own(a) and _lots_own(b) and ((_VALUE in a and _PNL in b) or (_PNL in a and _VALUE in b)):
                    return frozenset({_B})  # a lot's value less its pnl: what it cost (the capital it was bought with)
                return _norm([*_dollars(a), *_dollars(b)])
            for mark in (_L, _G):
                if mark in a or mark in b:
                    return a if mark in a else b
            if _K in a or _K in b:
                return frozenset({_K})
            return frozenset({_C}) if _const(a) and _const(b) else _NONE
        if isinstance(op, (ast.FloorDiv, ast.Mod)):
            if (_held(a) and (_const(b) or not b)) or (_held(b) and _const(a)):
                self._refuse(node, f"buckets {_what(a if _held(a) else b)} by a constant or a PARAMS value (// or %)")
            if _money(a) or _money(b):
                return _norm([*_dollars(a), *_dollars(b)])
            return a if _held(a) else frozenset({_U}) if (_U in a or _U in b) else _norm([*a, *b])
        if isinstance(op, ast.Div):
            if _L in a and _L in b:
                return frozenset({_K}) if _cross(a, b) else _NONE  # a ratio of two levels: scale-free on ONE symbol
            if _money(a) and _money(b):
                return self._ratio(node, a, b ^ {_INV}, "divides", frozenset({_U}))
            if _money(a) and _L in b:
                # The run's dollars over a price: a number of shares, and the run's dollars still (cash over a price
                # against a lot's qty is cash against what the lot cost).
                return _scaled(a, b) | {_SHARES}
            if _L in a and _money(b):
                return (_scaled(b, a) | {_SHARES}) ^ {_INV}
            if _U in a or _U in b or (_G in a and _L in b) or (_L in a and _G in b) or (_G in a and _G in b):
                return frozenset({_U})
            if _money(a):  # over a constant, a count, a log or a cross ratio: the run's dollars still
                return _scaled(a, b)
            if _money(b):
                return _scaled(b, a) ^ {_INV}  # 1000.0 / ctx.equity, 1 / ctx.budget: the run's dollars still, inverted
            if _L in a or _L in b:
                return frozenset({_L}) | _origin(a) | _origin(b)
            if _K in a and _K in b:
                return _NONE
            if _K in a or _K in b:
                return frozenset({_K})
            if _G in a:
                return a
            return frozenset({_C}) if _const(a) and _const(b) else _NONE
        if isinstance(op, ast.Mult):
            if _U in a or _U in b or (_G in a and (_G in b or _L in b)) or (_L in a and _G in b):
                return frozenset({_U})
            if _money(a) and _money(b):  # ctx.equity * (1 / ctx.budget): the ratio, written as a product
                return self._ratio(node, a, b, "sets", frozenset({_X}))
            if _money(a) or _money(b):
                m, other = (a, b) if _money(a) else (b, a)
                if _L in other:  # a number of shares times a price: dollars (a lot's qty times its entry: what it cost)
                    return _scaled(m, other) - {_SHARES}
                return _scaled(m, other)  # times a constant, a count, a log or a cross ratio: the run's dollars still
            if _L in a or _L in b:
                return frozenset({_L}) | _origin(a) | _origin(b)
            if _G in a or _G in b:
                return a if _G in a else b
            if _K in a or _K in b:
                return frozenset({_K})
            return frozenset({_C}) if _const(a) and _const(b) else _NONE
        if isinstance(op, ast.Pow):
            if _money(a) or _money(b):  # 1.001 ** ctx.equity, px ** ctx.cash: the run's dollars still
                return _norm([*_dollars(a), *_dollars(b)])
            if _held(a):
                return a
            if _held(b):
                return b  # 1.001 ** px: a level still, written as an exponent
            return frozenset({_C}) if _const(a) and _const(b) else frozenset({_U}) if (_U in a or _U in b) else _NONE
        return frozenset({_U})


def level_refusals(code: Any) -> list[str]:
    """THE LEVEL RULE (the module docstring, 1): every place the program holds a raw level, a cross-symbol ratio or the
    run's own dollars against a constant or a PARAMS value (or the sleeve's dollars against the run's anchor), as
    "line N: why" ([] for none, and for a file that does not parse: the code rules refuse that)."""
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
    return ("refused by the equity level rule (absolute levels identify the years: hold prices only against other prices "
            "of the same symbol, e.g. a ratio to their own average or recent high, never against a constant or a PARAMS "
            "value; and every judged run starts flat, so the sleeve's dollars since the run began are no signal: size by "
            "a share of the sleeve, exit on a lot's own return (mark over entry), and never hold ctx.equity, ctx.cash, "
            "ctx.budget, ctx.caps or a lot's value, pnl or qty against a constant or a PARAMS value, nor the sleeve's "
            "dollars against ctx.budget, ctx.caps or what a lot cost (its qty times a price, its value less its pnl; "
            "write a lot's weight as its value over ctx.equity), nor keep them in a lot's tag): "
            + "; ".join(found[:4]) + (f"; and {len(found) - 4} more" if len(found) > 4 else ""))


# ------------------------------------------------------------------------------------------------------- the memory rule
#: What of a module a program may read as a VALUE (the module docstring, 1c): its constants and its scalar and array
#: types. Everything else of `numpy` and `math` is reached by CALLING it (or by handing a known function on, below).
MODULE_VALUES = frozenset({
    "nan", "inf", "pi", "e", "tau", "newaxis", "euler_gamma", "NaN", "NAN", "Inf", "Infinity", "PINF", "NINF", "PZERO",
    "NZERO", "ndarray", "generic", "number", "floating", "integer", "signedinteger", "unsignedinteger", "inexact",
    "bool_", "bool", "float16", "float32", "float64", "float_", "double", "single", "half", "longdouble", "int8", "int16",
    "int32", "int64", "int_", "intp", "intc", "uint8", "uint16", "uint32", "uint64", "uint", "uintp", "complex64",
    "complex128", "str_", "object_", "dtype"})
#: numpy's submodules whose functions a program may call (`np.linalg.norm(x)`); the others are shut by name already
#: (league/gym/safety.py `NUMPY_BANNED`).
MODULE_PARTS = frozenset({"linalg", "fft", "polynomial", "emath", "exceptions", "dtypes"})
#: A ufunc's own methods (`np.maximum.accumulate(x)`).
UFUNC_METHODS = frozenset({"reduce", "accumulate", "outer", "reduceat", "at"})
#: The functions a program may hand on as a value (`key=np.abs`): the ones the level rule knows by name.
MODULE_FUNCTIONS = KEEP | COMBINE | LOG | EXP | UNITLESS | COMPARES | BUCKETS | frozenset(ARITHMETIC)


def memory_refusals(code: Any) -> list[str]:
    """THE MEMORY RULE (the module docstring, 1c): every place the program reads an object that BELONGS TO A MODULE as a
    value (`np.typecodes`, `t = np.typecodes`, `from numpy import typecodes`, `getattr(np, "typecodes")`, the module
    itself handed on), as "line N: why". Such an object lives in the decider child's interpreter, not in the program: it
    is shared by every program and run there and survives the restart check's fresh load, so it is memory outside STATE.
    [] for none, and for a file that does not parse (the code rules refuse that)."""
    try:
        tree = ast.parse(str(code or ""))
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return []
    modules: dict[str, str] = {}
    imported: dict[str, str] = {}
    parent: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[id(child)] = node
        if isinstance(node, ast.Import):
            for a in node.names:
                modules[a.asname or a.name.split(".")[0]] = a.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and str(node.module or "") != "__future__":
            for a in node.names:
                imported[a.asname or a.name] = a.name
    found: list[tuple[int, str]] = []

    def called(node: ast.AST) -> bool:
        up = parent.get(id(node))
        return isinstance(up, ast.Call) and up.func is node

    def chain(node: ast.AST) -> tuple[list[str], ast.AST]:
        """The attributes read one after another from `node` (`np.a.b.c`: [a, b, c]) and the outermost of them."""
        names: list[str] = []
        while True:
            up = parent.get(id(node))
            if not (isinstance(up, ast.Attribute) and up.value is node):
                return names, node
            names.append(up.attr)
            node = up

    def refuse(node: ast.AST, what: str) -> None:
        found.append((int(getattr(node, "lineno", 0) or 0),
                      f"reads {what} as a value: an object that belongs to a module is shared by every program the "
                      "House's decider runs and outlives a restart (memory outside STATE)"))

    def judge(node: ast.AST, names: list[str], top: ast.AST, owner: str) -> None:
        """`names` read from a module (or, from its second name on, from one of its parts)."""
        while len(names) > 1 and names[0] in MODULE_PARTS:
            owner, names = f"{owner}.{names[0]}", names[1:]
        if not names:
            refuse(node, f"the module {owner}")
        elif len(names) == 1:
            if not called(top) and names[0] not in MODULE_VALUES and names[0] not in MODULE_FUNCTIONS:
                refuse(node, f"{owner}.{names[0]}")
        elif not (len(names) == 2 and names[0] in MODULE_FUNCTIONS and names[1] in UFUNC_METHODS and called(top)):
            refuse(node, f"{owner}.{names[0]} (through .{'.'.join(names[1:])})")

    for node in ast.walk(tree):
        if not isinstance(node, ast.Name) or not isinstance(node.ctx, ast.Load):
            continue
        if node.id in modules:
            names, top = chain(node)
            judge(node, names, top, modules[node.id])
        elif node.id in imported:
            names, top = chain(node)
            judge(node, [imported[node.id], *names], top, "the module's")
    seen, out = set(), []
    for item in sorted(found):
        if item not in seen:
            seen.add(item)
            out.append(f"line {item[0]}: {item[1]}")
    return out


def memory_text(code: Any) -> str | None:
    """Why a program is refused by THE MEMORY RULE, in one sentence for its author, or None."""
    found = memory_refusals(code)
    if not found:
        return None
    return ("refused by the equity memory rule (call numpy's and math's functions and read their constants; never hold, "
            "alias, index or change an object that belongs to a module: it is not your program's memory): "
            + "; ".join(found[:4]) + (f"; and {len(found) - 4} more" if len(found) > 4 else ""))


# ------------------------------------------------------------------------------------------------------- the reading rule
#: WHAT A PROGRAM RECEIVES (league/equity/ctx.py; a test holds each tuple to that module's own definitions, and the
#: intent's words to league/equity/program.py's): ctx's fields, one symbol's bars' fields, an open lot's keys, a closed
#: lot's keys, the event flags, and the intent's kinds and fill points.
READ_CTX = ("symbols", "bars", "prices", "weekday", "events", "events_next", "session_of_month", "sessions_to_month_end",
            "positions", "orders", "closed", "rejects", "cash", "equity", "budget", "caps", "params")
READ_BAR = ("symbol", "open", "high", "low", "close", "volume", "ret")
READ_LOT = ("id", "symbol", "class", "qty", "entry", "mark", "value", "pnl", "held_sessions", "at", "tag")
READ_CLOSED = ("id", "symbol", "qty", "entry", "exit", "net", "held_sessions", "reason", "tag")
READ_EVENTS = ("fomc", "cpi", "jobs", "monthly_opex", "quarter_end", "half_day")
INTENT_KINDS = ("buy", "sell", "cancel")
INTENT_AT = ("open", "close")
#: The keys of an intent the House reads (league/equity/program.py `_intent`): written into a dict AFTER its display
#: (`order["at"] = "close"`), the display alone no longer says what the intent is.
INTENT_KEYS = frozenset({*INTENT_KINDS, "share", "usd", "at"})
#: The kinds of value the pass knows (`_Reading.kinds`): ctx; `ctx.bars` and its views; ONE symbol's bars; one of its
#: arrays; the lists of lots and one lot of each; the dicts of floats and one float of each; the rest of ctx.
_R_CTX, _R_BARS, _R_BAR, _R_ARR, _R_VALUES, _R_ITEMS = "ctx", "bars", "bar", "arr", "bars.values", "bars.items"
_R_LOTS, _R_LOT, _R_SHUT, _R_SHUT1, _R_ENUM, _R_ENUM1 = "lots", "lot", "closed", "closed1", "lots.enum", "closed.enum"
_R_PRICES, _R_PRICE, _R_CAPS, _R_CAP, _R_EVENTS = "prices", "price", "caps", "cap", "events"
_R_REJECTS, _R_REJECT, _R_SYMBOLS, _R_SYM, _R_ID = "rejects", "reject", "symbols", "sym", "lot.id"
_R_OF_CTX: dict[str, str] = {"bars": _R_BARS, "positions": _R_LOTS, "closed": _R_SHUT, "prices": _R_PRICES,
                             "caps": _R_CAPS, "events": _R_EVENTS, "events_next": _R_EVENTS, "rejects": _R_REJECTS,
                             "symbols": _R_SYMBOLS}
#: What one element of a kind is (a loop over it, a subscript that is no slice), what a pair of one is, and what a
#: lot's key holds.
_R_EACH: dict[str, str] = {_R_LOTS: _R_LOT, _R_SHUT: _R_SHUT1, _R_REJECTS: _R_REJECT, _R_SYMBOLS: _R_SYM,
                           _R_BARS: _R_SYM, _R_VALUES: _R_BAR}
_R_PAIR: dict[str, tuple[str | None, str | None]] = {_R_ITEMS: (_R_SYM, _R_BAR), _R_ENUM: (None, _R_LOT),
                                                     _R_ENUM1: (None, _R_SHUT1)}
_R_KEY: dict[str, str] = {"id": _R_ID, "symbol": _R_SYM}
_R_ROWS = frozenset({_R_LOT, _R_SHUT1})
_R_LISTS = frozenset({_R_LOTS, _R_SHUT, _R_REJECTS})
_R_DICTS = frozenset({_R_BARS, _R_PRICES, _R_CAPS, _R_EVENTS})
#: The names a dict and a list answer to as attributes (anything else read from a lot or from `ctx.positions` is no
#: method: the misreading).
DICT_METHODS = frozenset({"get", "items", "keys", "values", "copy", "pop", "popitem", "setdefault", "update", "clear",
                          "fromkeys"})
LIST_METHODS = frozenset({"append", "extend", "insert", "remove", "pop", "clear", "index", "count", "sort", "reverse",
                          "copy"})
#: Builtins that iterate, measure or convert their argument: handed ONE symbol's bars they raise.
_R_WALKS = frozenset({"len", "list", "tuple", "sorted", "reversed", "enumerate", "zip", "iter", "next", "sum", "max",
                      "min", "any", "all", "set", "frozenset", "map", "filter", "dict", "float", "int", "abs", "round",
                      "range"})
_R_ORDER = (ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn)
#: The dict and list methods that change one in place (a dict or list so changed is no longer its display).
_R_CHANGES = frozenset({"update", "setdefault", "pop", "popitem", "clear", "remove", "sort", "reverse"})
#: What each misreading is told (the same words as EQUITY.md's "Reading ctx").
_BARS_ARE = ("ctx.bars[sym] is ONE object whose six arrays are read BY ATTRIBUTE (open, high, low, close, volume, ret: "
             "numpy arrays, oldest first, the last element this session)")
_LOT_IS = "a lot is a dict in the list ctx.positions (a closed lot in ctx.closed)"
#: READING CTX, for everyone who writes an equity program (the equity architect's lanes block, the equity researcher's
#: system prompt and its brief after a disqualification or a refusal by this rule): one sentence and the two lines. No
#: outcome and no figure: what E1's ctx builder gives (league/equity/ctx.py), which the contract's worked example runs.
READING_CTX = (
    "READING CTX (a program that misreads it is refused before it runs, or fails in decide and is disqualified): "
    "ctx.bars[sym] is ONE object whose six numpy arrays (open, high, low, close, volume, ret; oldest first, the last "
    "element this session) are read BY ATTRIBUTE, never by key and never as rows; a lot is a dict in the list "
    "ctx.positions and is sold by its id:\n"
    "    close = ctx.bars[sym].close        # never ctx.bars[sym][\"close\"]; check len(close) before you index a window\n"
    "    sells = [{\"sell\": lot[\"id\"], \"at\": \"open\"} for lot in ctx.positions if lot[\"symbol\"] == sym]\n"
    "The contract's \"Reading ctx\" has a whole worked program and the common faults.")


def _text(node: ast.AST | None) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _src(node: ast.AST) -> str:
    try:
        return " ".join(ast.unparse(node).split())[:60]
    except Exception:  # noqa: BLE001 - an expression that cannot be written back is named by its kind
        return type(node).__name__


class _Scope:
    """One function's names (or the module's, or a comprehension's): each name's bindings, as (how, ...) tuples."""

    def __init__(self, node: ast.AST, up: "_Scope | None", *, own: bool = True):
        self.node, self.up, self.own = node, up, own  # `own` False: a comprehension (a walrus binds above it)
        self.names: dict[str, list[tuple]] = {}

    def bind(self, name: str, how: tuple) -> None:
        self.names.setdefault(name, []).append(how)

    def find(self, name: str) -> "_Scope | None":
        scope: _Scope | None = self
        while scope is not None and name not in scope.names:
            scope = scope.up
        return scope


class _Reading:
    """THE READING RULE's pass (the module docstring, 1e) over one parsed program: `run()` gives its (line, why) rows."""

    def __init__(self, tree: ast.Module):
        self.tree = tree
        self.found: list[tuple[int, str]] = []
        self.scope_of: dict[int, _Scope] = {}
        self.memo: dict[tuple[int, str], frozenset[str] | None] = {}
        self.busy: set[tuple[int, str]] = set()
        self.calls: dict[str, list[ast.Call]] = {}
        self.heads: set[int] = set()  # the names that are a call's function (`f` in `f(x)`)
        self.defs: dict[str, list[ast.AST]] = {}
        self.module = _Scope(tree, None)
        #: What the program writes into dicts and lists of its own after they were made: the string keys written or
        #: taken out anywhere (`touched`), the names changed in place (`changed`), and whether something was changed in
        #: a way the pass cannot place (`rebuilt`: a computed key or an update on something that is no plain local name).
        self.touched: set[str] = set()
        self.changed: set[str] = set()
        self.rebuilt = False
        #: WHAT THE PROGRAM ITSELF TAKES CARE OF: the nodes inside a `try` that has a handler (a read that raises there
        #: is caught: whether the program then trades is Train's to judge), and the kinds of value it asks the type of
        #: (`isinstance(bars, dict)`, `hasattr(lot, "id")`: it reads them both ways on purpose). Neither is refused.
        self.guarded: set[int] = set()
        self.probed: set[str] = set()
        self.build(tree, self.module)
        for node in ast.walk(tree):
            if isinstance(node, ast.Try) and node.handlers:
                self.guarded |= {id(sub) for stmt in node.body for sub in ast.walk(stmt)}
            elif type(node).__name__ == "TryStar":
                self.guarded |= {id(sub) for stmt in node.body for sub in ast.walk(stmt)}
        #: Functions read as a value somewhere (handed on, stored, returned): their parameters may be anything.
        self.loose = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
                      and id(n) not in self.heads and n.id in self.defs}

    # ------------------------------------------------------------------ the names
    def targets(self, target: ast.AST, scope: _Scope, how: Any) -> None:
        """Bind an assignment's or a loop's target: a name by `how(None)`, a flat pair's names by `how(i)`, anything
        else as unknown."""
        if isinstance(target, ast.Name):
            scope.bind(target.id, how(None))
        elif isinstance(target, (ast.Tuple, ast.List)):
            flat = all(isinstance(e, ast.Name) for e in target.elts)
            for i, e in enumerate(target.elts):
                if isinstance(e, ast.Name):
                    scope.bind(e.id, how(i) if flat else ("other",))
                else:
                    self.unknown(e, scope)
        else:
            self.unknown(target, scope)

    @staticmethod
    def unknown(node: ast.AST, scope: _Scope) -> None:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Name) and isinstance(sub.ctx, (ast.Store, ast.Del)):
                scope.bind(sub.id, ("other",))

    def placed(self, receiver: ast.AST, scope: _Scope) -> bool:
        """Whether a dict or list changed in place is a plain name of the program's own making (assigned, never a loop's
        variable, a parameter or a name from outside): its change is then that name's alone."""
        if not isinstance(receiver, ast.Name):
            return False
        home = scope.find(receiver.id)
        return home is not None and all(how[0] == "value" for how in home.names[receiver.id])

    def writes(self, node: ast.AST, scope: _Scope) -> None:
        """Book a change in place (`touched`, `changed`, `rebuilt`): a subscript written or deleted, or a changing
        method called."""
        if isinstance(node, ast.Subscript):
            receiver, key = node.value, _text(node.slice)
            computed = key is None and not isinstance(node.slice, ast.Slice) and not (
                isinstance(node.slice, ast.Constant) or (isinstance(node.slice, ast.UnaryOp)
                                                         and isinstance(node.slice.operand, ast.Constant)))
        else:
            receiver, name = node.func.value, node.func.attr  # type: ignore[attr-defined]
            args = list(node.args)  # type: ignore[attr-defined]
            key = _text(args[0]) if args and name in ("setdefault", "pop") else None
            computed = name == "update" or (name in ("setdefault", "pop") and bool(args) and key is None)
            if name == "update":
                shown = [a for a in args if isinstance(a, ast.Dict) and all(_text(k) is not None for k in a.keys)]
                named = [k.arg for k in node.keywords]  # type: ignore[attr-defined]
                if len(shown) == len(args) and None not in named:
                    self.touched |= {_text(k) or "" for a in shown for k in a.keys} | {str(n) for n in named}
                    computed = False
        if key is not None:
            self.touched.add(key)
        if isinstance(receiver, ast.Name):
            self.changed.add(receiver.id)
        if computed and not self.placed(receiver, scope):
            self.rebuilt = True

    def build(self, node: ast.AST, scope: _Scope) -> None:
        self.scope_of[id(node)] = scope
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            scope.bind(node.name, ("def", node))
            self.defs.setdefault(node.name, []).append(node)
            inner = _Scope(node, scope)
            a = node.args
            for i, arg in enumerate([*a.posonlyargs, *a.args]):
                inner.bind(arg.arg, ("param", node, i, arg.arg))
            for arg in a.kwonlyargs:
                inner.bind(arg.arg, ("param", node, None, arg.arg))
            for arg in (a.vararg, a.kwarg):
                if arg is not None:
                    inner.bind(arg.arg, ("other",))
            for sub in (*a.defaults, *(d for d in a.kw_defaults if d is not None), *node.decorator_list):
                self.build(sub, scope)
            for sub in node.body:
                self.build(sub, inner)
            return
        if isinstance(node, ast.Lambda):
            inner = _Scope(node, scope)
            for sub in ast.walk(node.args):
                if isinstance(sub, ast.arg):
                    inner.bind(sub.arg, ("other",))
            self.build(node.body, inner)
            return
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
            inner = _Scope(node, scope, own=False)
            for n, gen in enumerate(node.generators):
                where = scope if n == 0 else inner
                self.scope_of[id(gen)] = where
                self.build(gen.iter, where)
                self.targets(gen.target, inner, lambda i, gen=gen, where=where: ("each", gen.iter, where, i))
                self.build(gen.target, inner)
                for cond in gen.ifs:
                    self.build(cond, inner)
            for sub in ((node.key, node.value) if isinstance(node, ast.DictComp) else (node.elt,)):
                self.build(sub, inner)
            return
        if isinstance(node, (ast.For, ast.AsyncFor)):
            self.targets(node.target, scope, lambda i: ("each", node.iter, scope, i))
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                value = node.value
                if isinstance(target, (ast.Tuple, ast.List)) and isinstance(value, (ast.Tuple, ast.List)) \
                        and len(target.elts) == len(value.elts) \
                        and not any(isinstance(e, ast.Starred) for e in (*target.elts, *value.elts)):
                    for t, v in zip(target.elts, value.elts):
                        self.targets(t, scope, lambda i, v=v: ("value", v, scope) if i is None else ("other",))
                else:
                    self.targets(target, scope, lambda i: ("value", value, scope) if i is None else ("other",))
        elif isinstance(node, ast.AnnAssign):
            self.targets(node.target, scope,
                         lambda i: ("value", node.value, scope) if i is None and node.value is not None else ("other",))
        elif isinstance(node, ast.NamedExpr):
            home = scope
            while not home.own and home.up is not None:
                home = home.up
            self.targets(node.target, home, lambda i: ("value", node.value, scope) if i is None else ("other",))
        elif isinstance(node, ast.AugAssign):
            if isinstance(node.target, ast.Name):
                scope.bind(node.target.id, ("more",))  # `out += [...]`: of no known kind, and no second assignment
        elif isinstance(node, ast.Delete):
            self.unknown(node, scope)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                scope.bind((alias.asname or alias.name).split(".")[0], ("other",))
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            for name in node.names:
                scope.bind(name, ("other",))
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if item.optional_vars is not None:
                    self.unknown(item.optional_vars, scope)
        elif isinstance(node, ast.ExceptHandler):
            if node.name:
                scope.bind(node.name, ("other",))
        elif type(node).__name__ in ("MatchAs", "MatchStar"):
            if getattr(node, "name", None):
                scope.bind(node.name, ("other",))
        elif type(node).__name__ == "MatchMapping":
            if getattr(node, "rest", None):
                scope.bind(node.rest, ("other",))
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                self.calls.setdefault(node.func.id, []).append(node)
                self.heads.add(id(node.func))
        for sub in ast.iter_child_nodes(node):
            self.build(sub, scope)

    def settle(self) -> None:
        """Book every change in place and every kind the program asks the type of, once every name is bound (`writes`
        asks how a changed name was bound)."""
        for node in ast.walk(self.tree):
            scope = self.scope_of.get(id(node))
            if scope is None:
                continue
            if isinstance(node, ast.Subscript) and isinstance(node.ctx, (ast.Store, ast.Del)):
                self.writes(node, scope)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in _R_CHANGES:
                self.writes(node, scope)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.args \
                    and node.func.id in ("isinstance", "hasattr", "callable") and scope.find(node.func.id) is None:
                self.probed |= self.kinds(node.args[0], scope) or frozenset()

    def name(self, name: str, scope: _Scope) -> frozenset[str] | None:
        """The kinds a name holds where it is read: every binding of it in its scope gives a known kind, else None."""
        home = scope.find(name)
        if home is None:
            return None
        key = (id(home), name)
        if key in self.memo:
            return self.memo[key]
        if key in self.busy:
            return None  # bound from itself (`x = x[1:]`): unknown
        self.busy.add(key)
        out: set[str] | None = set()
        for how in home.names[name]:
            got = self.bound(how)
            if got is None:
                out = None
                break
            out |= got
        self.busy.discard(key)
        self.memo[key] = frozenset(out) if out else None
        return self.memo[key]

    def bound(self, how: tuple) -> frozenset[str] | None:
        if how[0] == "value":
            return self.kinds(how[1], how[2])
        if how[0] == "each":
            whole = self.kinds(how[1], how[2])
            if whole is None:
                return None
            out = set()
            for kind in whole:
                if how[3] is None:
                    each = _R_EACH.get(kind)
                else:
                    each = (_R_PAIR.get(kind) or (None, None))[how[3]] if how[3] in (0, 1) else None
                if each is None:
                    return None
                out.add(each)
            return frozenset(out)
        if how[0] == "param":
            return self.param(how[1], how[2], how[3])
        return None

    def param(self, fn: ast.AST, index: int | None, name: str) -> frozenset[str] | None:
        """A parameter's kinds: decide's first is ctx; a helper's are what EVERY call of it hands in (None when it is
        never called by name, is read as a value somewhere, is defined twice, or a call spreads its arguments)."""
        fname = getattr(fn, "name", "")
        home = self.scope_of.get(id(fn))
        if len(self.defs.get(fname, ())) != 1 or home is None or len(home.names.get(fname, ())) != 1:
            return None
        if fname == "decide" and home is self.module:
            return frozenset({_R_CTX}) if index == 0 else None
        calls = self.calls.get(fname, [])
        if not calls or fname in self.loose:
            return None
        out: set[str] = set()
        for call in calls:
            if any(isinstance(a, ast.Starred) for a in call.args) or any(k.arg is None for k in call.keywords):
                return None
            given = next((k.value for k in call.keywords if k.arg == name), None)
            if given is None and index is not None and index < len(call.args):
                given = call.args[index]
            got = self.kinds(given, self.scope_of[id(call)]) if given is not None else None
            if got is None:
                return None
            out |= got
        return frozenset(out) or None

    # ------------------------------------------------------------------ the kinds
    def kinds(self, node: ast.AST | None, scope: _Scope) -> frozenset[str] | None:
        """The kinds of value an expression gives, when the pass knows them all; None for anything else."""
        if isinstance(node, ast.Name):
            return self.name(node.id, scope)
        if isinstance(node, ast.Attribute):
            return self.field(self.kinds(node.value, scope), node.attr)
        if isinstance(node, ast.Subscript):
            whole = self.kinds(node.value, scope)
            if whole is None:
                return None
            cut = isinstance(node.slice, ast.Slice)
            out = set()
            for kind in whole:
                if kind in _R_LISTS or kind == _R_SYMBOLS:
                    each = kind if cut else _R_EACH[kind]
                elif cut:
                    each = None
                elif kind == _R_BARS:
                    each = _R_BAR
                elif kind in (_R_PRICES, _R_CAPS):
                    each = _R_PRICE if kind == _R_PRICES else _R_CAP
                elif kind in _R_ROWS:
                    each = _R_KEY.get(_text(node.slice) or "")
                else:
                    each = None
                if each is None:
                    return None
                out.add(each)
            return frozenset(out)
        if isinstance(node, ast.Call):
            return self.called(node, scope)
        if isinstance(node, ast.IfExp):
            a, b = self.kinds(node.body, scope), self.kinds(node.orelse, scope)
            return a | b if a is not None and b is not None else None
        if isinstance(node, ast.NamedExpr):
            return self.kinds(node.value, scope)
        return None

    @staticmethod
    def field(whole: frozenset[str] | None, attr: str) -> frozenset[str] | None:
        if whole is None:
            return None
        out = set()
        for kind in whole:
            if kind == _R_CTX:
                each = _R_OF_CTX.get(attr)
            elif kind == _R_BAR:
                each = _R_SYM if attr == "symbol" else _R_ARR if attr in READ_BAR else None
            else:
                each = None
            if each is None:
                return None
            out.add(each)
        return frozenset(out)

    def called(self, node: ast.Call, scope: _Scope) -> frozenset[str] | None:
        func = node.func
        first = node.args[0] if node.args and not isinstance(node.args[0], ast.Starred) else None
        if isinstance(func, ast.Attribute):
            whole = self.kinds(func.value, scope)
            if whole is None or len(whole) != 1:
                return None
            (kind,) = whole
            if kind == _R_BARS:
                if func.attr == "get" and first is not None and not node.keywords and \
                        (len(node.args) == 1 or (len(node.args) == 2 and isinstance(node.args[1], ast.Constant)
                                                 and node.args[1].value is None)):
                    return frozenset({_R_BAR})
                if node.args or node.keywords:
                    return None
                return {"values": frozenset({_R_VALUES}), "items": frozenset({_R_ITEMS})}.get(func.attr)
            if kind in _R_ROWS and func.attr == "get" and len(node.args) == 1 and not node.keywords:
                each = _R_KEY.get(_text(first) or "")
                return frozenset({each}) if each else None
            if kind in _R_LISTS and func.attr == "copy" and not node.args:
                return whole
            return None
        if isinstance(func, ast.Name) and scope.find(func.id) is None and first is not None and not node.keywords:
            whole = self.kinds(first, scope)
            if func.id == "getattr" and len(node.args) == 2 and _text(node.args[1]) is not None:
                return self.field(whole, _text(node.args[1]) or "")
            if whole is None or len(whole) != 1 or len(node.args) != 1:
                return None
            (kind,) = whole
            if func.id == "enumerate":
                return {_R_LOTS: frozenset({_R_ENUM}), _R_SHUT: frozenset({_R_ENUM1})}.get(kind)
            if func.id in ("list", "tuple", "reversed") and kind in (*_R_LISTS, _R_SYMBOLS):
                return whole
            if func.id == "dict" and kind in _R_ROWS:
                return whole
        return None

    # ------------------------------------------------------------------ the misreadings
    def say(self, node: ast.AST, why: str, *, raises: bool = True) -> None:
        """Book a misreading; one that RAISES is left alone inside a `try` with a handler (`guarded`)."""
        if raises and id(node) in self.guarded:
            return
        self.found.append((int(getattr(node, "lineno", 0) or 0), why))

    def known(self, node: ast.AST | None, scope: _Scope) -> frozenset[str] | None:
        """`kinds`, less anything the program asks the type of (`probed`: None, it reads that both ways on purpose)."""
        whole = self.kinds(node, scope) if node is not None else None
        return None if whole is None or whole & self.probed else whole

    def all_of(self, node: ast.AST | None, scope: _Scope, kinds: Iterable[str]) -> bool:
        whole = self.known(node, scope)
        return whole is not None and whole <= frozenset(kinds)

    def rows(self, node: ast.AST, what: str) -> None:
        self.say(node, f"{what}: {_BARS_ARE}; there are no rows to walk, count or unpack: take a window of one array, "
                       "close = ctx.bars[sym].close; close[-20:], len(close)")

    def check(self, node: ast.AST) -> None:
        scope = self.scope_of.get(id(node))
        if scope is None:
            return
        if isinstance(node, ast.Subscript):
            self.subscript(node, scope)
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            self.attribute(node, node.value, node.attr, scope)
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
            if self.all_of(node.iter, scope, (_R_BAR,)):
                self.rows(node.iter, f"`{_src(node.iter)}` is iterated as rows and raises a TypeError")
        elif isinstance(node, ast.Call):
            self.call(node, scope)
        elif isinstance(node, ast.Assign):
            if any(isinstance(t, (ast.Tuple, ast.List)) for t in node.targets) and self.all_of(node.value, scope, (_R_BAR,)):
                self.rows(node, f"`{_src(node.value)}` is unpacked and raises a TypeError")
        elif isinstance(node, ast.BinOp) and not isinstance(node.left, ast.JoinedStr) and _text(node.left) is None:
            for side in (node.left, node.right):
                if self.all_of(side, scope, (_R_BAR,)):
                    self.say(side, f"`{_src(side)}` is put into arithmetic and raises a TypeError: {_BARS_ARE}; compute "
                                   "on one array, ctx.bars[sym].close")
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd, ast.Invert)):
            if self.all_of(node.operand, scope, (_R_BAR,)):
                self.say(node, f"`{_src(node.operand)}` is put into arithmetic and raises a TypeError: {_BARS_ARE}")
        elif isinstance(node, ast.Compare):
            sides = [node.left, *node.comparators]
            for i, op in enumerate(node.ops):
                if not isinstance(op, _R_ORDER):
                    continue
                for side in ((sides[i + 1],) if isinstance(op, (ast.In, ast.NotIn)) else (sides[i], sides[i + 1])):
                    if self.all_of(side, scope, (_R_BAR,)):
                        self.say(side, f"`{_src(side)}` is compared or searched and raises a TypeError: {_BARS_ARE}; "
                                       "compare a value of one array, ctx.bars[sym].close[-1]")

    def subscript(self, node: ast.Subscript, scope: _Scope) -> None:
        whole = self.known(node.value, scope)
        if whole is None:
            return
        key = _text(node.slice)
        load = isinstance(node.ctx, ast.Load)
        if whole == {_R_BAR}:
            if key is not None and key in READ_BAR:
                self.say(node, f"`{_src(node)}` reads a symbol's bars by key and raises a TypeError: {_BARS_ARE}; write "
                               f"`{_src(node.value)}.{key}`")
            elif key is not None:
                self.say(node, f"`{_src(node)}` reads a symbol's bars by key and raises a TypeError: {_BARS_ARE}; they "
                               f"have no {key!r}")
            else:
                self.rows(node, f"`{_src(node)}` reads a symbol's bars by position and raises a TypeError")
        elif whole <= {_R_LOTS, _R_SHUT} and key is not None:
            self.say(node, f"`{_src(node)}` reads ctx.positions (or ctx.closed) as a dict and raises a TypeError: it is a "
                           "LIST of lots, each a dict; find a symbol's lots with [lot for lot in ctx.positions if "
                           "lot[\"symbol\"] == sym]")
        elif whole <= {_R_PRICE, _R_CAP}:
            self.say(node, f"`{_src(node)}` subscripts a float and raises a TypeError: ctx.prices[sym] is this session's "
                           "close and ctx.caps[sym] dollars; a symbol's history is ctx.bars[sym].close")
        elif whole <= _R_ROWS and key is not None and load:
            if key not in self.keys(whole):
                self.say(node, f"`{_src(node)}`: {self.keys_of(whole)} has no key {key!r} (a KeyError)")
        elif whole == {_R_EVENTS} and key is not None and load and key not in READ_EVENTS:
            self.say(node, f"`{_src(node)}`: ctx.events and ctx.events_next hold {', '.join(READ_EVENTS)} only (a "
                           "KeyError)")
        elif whole == {_R_REJECT} and key is not None:
            self.say(node, f"`{_src(node)}`: ctx.rejects is a list of strings (each says why an intent was refused), "
                           "not of dicts (a TypeError)")

    @staticmethod
    def keys(whole: frozenset[str]) -> list[str]:
        """The keys at least one of the kinds of lot has (a key outside them is in no lot the name can hold)."""
        return [k for kind, keys in ((_R_LOT, READ_LOT), (_R_SHUT1, READ_CLOSED)) if kind in whole for k in keys]

    @staticmethod
    def keys_of(whole: frozenset[str]) -> str:
        if whole == {_R_SHUT1}:
            return f"a closed lot ({', '.join(READ_CLOSED)})"
        if whole == {_R_LOT}:
            return f"an open lot ({', '.join(READ_LOT)})"
        return f"a lot (open: {', '.join(READ_LOT)}; closed: {', '.join(READ_CLOSED)})"

    def attribute(self, node: ast.AST, value: ast.AST, attr: str, scope: _Scope) -> None:
        whole = self.known(value, scope)
        if whole is None:
            return
        told = f"`{_src(value)}.{attr}`"
        if whole == {_R_CTX} and attr not in READ_CTX:
            self.say(node, f"{told}: ctx has no field {attr!r} (an AttributeError); its fields are "
                           f"{', '.join(READ_CTX)}, and it never holds a date")
        elif whole == {_R_BAR} and attr not in READ_BAR:
            self.say(node, f"{told}: a symbol's bars have open, high, low, close, volume and ret only (an "
                           f"AttributeError): {_BARS_ARE}")
        elif whole <= _R_ROWS and attr not in DICT_METHODS:
            self.say(node, f"{told} reads a lot by attribute and raises an AttributeError: {_LOT_IS}; write "
                           f"`{_src(value)}[\"{attr}\"]` ({self.keys_of(whole)})")
        elif whole <= _R_LISTS and attr not in LIST_METHODS:
            what = "ctx.rejects is a list of strings" if whole == {_R_REJECTS} else \
                "ctx.positions and ctx.closed are LISTS of lots, each a dict: loop over them"
            self.say(node, f"{told}: {what} (an AttributeError)")
        elif whole <= _R_DICTS and attr not in DICT_METHODS:
            what = ("ctx.events is a dict of booleans read by key: ctx.events[\"fomc\"]" if whole == {_R_EVENTS} else
                    "ctx.bars, ctx.prices and ctx.caps are dicts by symbol: ctx.bars[\"SPY\"].close, ctx.prices[\"SPY\"]")
            self.say(node, f"{told}: {what} (an AttributeError)")

    def call(self, node: ast.Call, scope: _Scope) -> None:
        func = node.func
        plain = [a for a in node.args if not isinstance(a, ast.Starred)]
        if isinstance(func, ast.Name) and scope.find(func.id) is None:
            if func.id == "getattr" and len(node.args) == 2 and _text(node.args[1]) is not None:
                self.attribute(node, node.args[0], _text(node.args[1]) or "", scope)
            elif func.id in _R_WALKS:
                for arg in plain:
                    if self.all_of(arg, scope, (_R_BAR,)):
                        self.rows(arg, f"`{func.id}({_src(arg)})` walks, counts or converts a symbol's bars and raises a "
                                       "TypeError")
        elif isinstance(func, ast.Attribute):
            owner = func.value
            if isinstance(owner, ast.Name) and owner.id in MODULES and scope.find(owner.id) is self.module:
                for arg in plain:
                    if self.all_of(arg, scope, (_R_BAR,)):
                        self.say(arg, f"`{owner.id}.{func.attr}({_src(arg)})` is handed a symbol's bars whole: "
                                      f"{_BARS_ARE}; hand it one array, ctx.bars[sym].close")
            whole = self.known(owner, scope)
            key = _text(plain[0]) if plain else None
            if whole is not None and func.attr == "get" and key is not None:
                if whole <= _R_ROWS and key not in self.keys(whole):
                    self.say(node, f"`{_src(node)}`: {self.keys_of(whole)} has no key {key!r}; the get is always its "
                                   "default", raises=False)
                elif whole == {_R_EVENTS} and key not in READ_EVENTS:
                    self.say(node, f"`{_src(node)}`: ctx.events and ctx.events_next hold {', '.join(READ_EVENTS)} only; "
                                   "the get is always its default", raises=False)

    # ------------------------------------------------------------------ the intents
    @staticmethod
    def inside(stmt: ast.AST) -> Iterable[ast.AST]:
        """Every node of a statement that belongs to its own function (no nested def's or lambda's body)."""
        stack = [stmt]
        while stack:
            node = stack.pop()
            yield node
            for sub in ast.iter_child_nodes(node):
                if not isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                    stack.append(sub)

    def returned(self, fn: ast.AST, depth: int = 0, seen: set[int] | None = None) -> list[tuple[ast.Dict, _Scope, str | None]]:
        """THE INTENTS A FUNCTION RETURNS that the source shows as dict displays, each with its scope and the one name it
        was assigned to (None: written in place): in a return value, in a list it returns, appended or added to the ONE
        list a returned name was assigned (a name assigned twice, or changed in place otherwise, is followed nowhere:
        it may have held something else), and in the return of a helper it passes on."""
        seen = set() if seen is None else seen
        out: list[tuple[ast.Dict, _Scope, str | None]] = []
        if id(fn) in seen or depth > CALL_DEPTH:
            return out
        seen.add(id(fn))
        body = [n for stmt in getattr(fn, "body", []) for n in self.inside(stmt)]
        inner = self.scope_of.get(id(fn.body[0])) if getattr(fn, "body", None) else None  # type: ignore[attr-defined]
        if inner is None:
            return out
        names: set[str] = set()

        def puts(name: str) -> list[tuple[ast.AST, bool]] | None:
            """(what goes into a local name, whether by its one assignment); None for a name the pass does not follow."""
            got: list[tuple[ast.AST, bool]] = []
            assigned = 0
            for n in body:
                if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in n.targets):
                    got.append((n.value, True))
                    assigned += 1
                elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.target.id == name:
                    assigned += 1
                    if n.value is not None:
                        got.append((n.value, True))
                elif isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name) and n.target.id == name:
                    if not isinstance(n.op, ast.Add):
                        return None
                    got.append((n.value, False))
                elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name) \
                        and n.func.value.id == name and n.func.attr in (*PUTS, *PUTS_MANY):
                    at = PUTS.get(n.func.attr, 0)
                    if len(n.args) > at and not n.keywords:
                        got.append((n.args[at], False))
            home = inner.find(name)
            if assigned != 1 or home is not inner or any(how[0] not in ("value", "more") for how in inner.names[name]):
                return None
            return got

        def walk(node: ast.AST | None, via: str | None = None, level: int = 0) -> None:
            if node is None or level > 40:
                return
            step = level + 1
            if isinstance(node, ast.Dict):
                out.append((node, self.scope_of.get(id(node), inner), via))
            elif isinstance(node, (ast.List, ast.Tuple, ast.Set)):
                for e in node.elts:
                    walk(e.value if isinstance(e, ast.Starred) else e, None, step)
            elif isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
                walk(node.elt, None, step)
            elif isinstance(node, ast.IfExp):
                walk(node.body, None, step)
                walk(node.orelse, None, step)
            elif isinstance(node, ast.BoolOp):
                for v in (node.values if isinstance(node.op, ast.Or) else node.values[-1:]):
                    walk(v, None, step)
            elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
                walk(node.left, None, step)
                walk(node.right, None, step)
            elif isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Slice):
                walk(node.value, None, step)
            elif isinstance(node, ast.Name):
                if node.id in names:
                    return
                names.add(node.id)
                into = puts(node.id)
                changed = node.id in self.changed
                for put, assigned in into or ():
                    if isinstance(put, ast.Dict):
                        # The name's one value is a dict display: an intent of that name (left alone if it is changed).
                        if assigned and len(into or ()) == 1:
                            walk(put, node.id, step)
                        elif not assigned and not changed:
                            walk(put, None, step)
                    elif not changed:
                        walk(put, None, step)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                made = self.defs.get(node.func.id, [])
                if len(made) == 1 and self.scope_of.get(id(made[0])) is self.module \
                        and len(self.module.names.get(node.func.id, ())) == 1 and inner.find(node.func.id) is self.module:
                    out.extend(self.returned(made[0], depth + 1, seen))
                elif node.func.id in ("list", "tuple", "sorted", "reversed") and len(node.args) == 1 \
                        and inner.find(node.func.id) is None:
                    walk(node.args[0], None, step)

        for n in body:
            if isinstance(n, ast.Return):
                walk(n.value)
        return out

    def intent(self, node: ast.Dict, scope: _Scope, via: str | None) -> None:
        keys = [_text(k) for k in node.keys]
        if any(k is None for k in keys) or self.rebuilt or (via is not None and via in self.changed):
            return  # a computed key, a dict built on another (**), or a dict changed after it was written: not judged
        row = dict(zip(keys, node.values))
        kinds = [k for k in INTENT_KINDS if k in row]
        shown = "{" + ", ".join(f'"{k}"' for k in keys) + "}"
        fixed = not (self.touched & INTENT_KEYS)  # no intent key is written into any dict after its display
        if not kinds:
            if fixed and not keys:
                self.say(node, "decide returns an empty dict: a dict is read as ONE intent, and one with none of \"buy\", "
                               "\"sell\", \"cancel\" is dropped and counted as an error (25 errors disqualify the run); "
                               "for no order return []", raises=False)
            elif fixed:
                self.say(node, f"decide returns the dict {shown}, which has none of \"buy\", \"sell\", \"cancel\": an "
                               "intent has EXACTLY one of them (it is dropped and counted as an error, and 25 errors "
                               "disqualify the run); write {\"buy\": \"SPY\", \"share\": 0.5, \"at\": \"open\"} or "
                               "{\"sell\": lot[\"id\"], \"at\": \"open\"}", raises=False)
            return
        if len(kinds) > 1:
            if not self.touched & set(INTENT_KINDS):
                self.say(node, f"the intent {shown} has {' and '.join(repr(k) for k in kinds)}: an intent has EXACTLY one "
                               "of \"buy\", \"sell\", \"cancel\" (it is dropped and counted as an error); return one "
                               "intent for the sell and another for the buy", raises=False)
            return
        kind = kinds[0]
        if kind == "cancel":
            return
        at = row.get("at")
        if isinstance(at, ast.Constant) and at.value not in INTENT_AT and "at" not in self.touched:
            self.say(at, f"the intent's \"at\" is {at.value!r}: it is \"open\" or \"close\" (the NEXT session's; left out, "
                         "it is \"open\"); anything else drops the intent and counts as an error", raises=False)
        value = row[kind]
        if kind == "sell":
            whole = self.known(value, scope)
            if _text(value) is not None or (whole is not None and whole <= {_R_SYM, _R_LOT, _R_SHUT1, _R_BAR}):
                self.say(value, f"the intent sells `{_src(value)}`: a lot is sold whole BY ITS ID, never by its symbol "
                                "(the intent is dropped and counted as an error); write {\"sell\": lot[\"id\"]} for each "
                                "lot in ctx.positions you want out of", raises=False)
            return
        if isinstance(value, ast.Constant) and not (isinstance(value.value, str) and value.value.strip()):
            self.say(value, f"the intent buys {value.value!r}: \"buy\" names a symbol of your NEEDS, e.g. \"SPY\"",
                     raises=False)

        def given(key: str) -> bool:
            return key in row and not (isinstance(row[key], ast.Constant) and row[key].value is None)
        if fixed and not given("share") and not given("usd"):
            self.say(node, f"the buy {shown} has neither \"share\" nor \"usd\": a buy has exactly one (\"share\": 0.5 is "
                           "half of the sleeve's equity; \"usd\": 250.0 is dollars); without one it is dropped and "
                           "counted as an error", raises=False)
        elif fixed and given("share") and given("usd") and all(isinstance(row[k], ast.Constant) for k in ("share", "usd")):
            self.say(node, "the buy has both \"share\" and \"usd\": a buy has exactly one of them (it is dropped and "
                           "counted as an error)", raises=False)
        for key, high, what in (("share", 1.0, "a share of the sleeve's equity above 0 and at most 1 (0.5 is half)"),
                                ("usd", math.inf, "dollars above 0")):
            size = row.get(key)
            sign = -1.0 if isinstance(size, ast.UnaryOp) and isinstance(size.op, ast.USub) else 1.0
            inner = size.operand if isinstance(size, ast.UnaryOp) and isinstance(size.op, (ast.USub, ast.UAdd)) else size
            if not isinstance(inner, ast.Constant) or inner.value is None or key in self.touched:
                continue
            number = inner.value
            if isinstance(number, bool) or not isinstance(number, (int, float)) or not 0.0 < sign * float(number) <= high:
                self.say(size, f"the buy's \"{key}\" is `{_src(size)}`: it is {what}; the intent is dropped and counted "
                               "as an error", raises=False)

    def run(self) -> list[tuple[int, str]]:
        self.settle()
        for node in ast.walk(self.tree):
            self.check(node)
        decide = self.defs.get("decide", [])
        if len(decide) == 1 and self.scope_of.get(id(decide[0])) is self.module \
                and len(self.module.names.get("decide", ())) == 1:
            for node, scope, via in self.returned(decide[0]):
                self.intent(node, scope, via)
        seen, out = set(), []
        for item in sorted(self.found):
            if item not in seen:
                seen.add(item)
                out.append(item)
        return out


def reading_refusals(code: Any) -> list[str]:
    """THE READING RULE (the module docstring, 1e): every place the program can be SEEN to misread what ctx gives or to
    return a malformed intent, as "line N: what is wrong and what to write" ([] for none, and for a file that does not
    parse: the code rules refuse that). Reads the source only."""
    try:
        tree = ast.parse(str(code or ""))
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return []
    try:
        found = _Reading(tree).run()
    except Exception:  # noqa: BLE001 - a shape the pass cannot follow is never refused on a guess (its Train run judges it)
        return []
    return [f"line {line}: {why}" for line, why in found]


def reading_text(code: Any) -> str | None:
    """Why a program is refused by THE READING RULE, in one sentence for its author, or None."""
    found = reading_refusals(code)
    if not found:
        return None
    return ("refused before it ran by the equity reading rule (the program misreads what ctx gives, or returns an intent "
            "the House drops: on the House it would fail in decide and be disqualified; the contract's \"Reading ctx\" "
            "has a worked example): " + "; ".join(found[:4]) + (f"; and {len(found) - 4} more" if len(found) > 4 else ""))


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
               "rejects, cash, equity, budget, caps, params. Module STATE persists between calls of one loaded program, "
               "never across runs, and a restart of the House's decider empties it (the Train bar's STATE check, not "
               "this review, judges a program that needs it to persist).",
    "fills": "decide(ctx) runs after session t's close; every intent executes in the NEXT session at its open or close. "
             "A rule that needs session t+1's prices to decide is lookahead.",
    "run": "Every judged run starts flat with the same capital: ctx.budget is that capital (a constant in a replay) and "
           "ctx.equity, ctx.cash and a lot's value and pnl move with the run. A rule keyed to the sleeve's dollars since "
           "the run began (equity against budget, a constant or a PARAMS value; a profit lock, a loss stop on the "
           "sleeve, a size that changes once the run is ahead or behind) depends on where the run starts, which live "
           "trading never repeats. The capital is also what a lot cost over the share it asked, so the same rule is "
           "ctx.equity or ctx.cash against a lot's qty times its entry or exit, its value less its pnl, or exit times "
           "qty less net; a lot's weight in the sleeve (its value over ctx.equity) or the sleeve's cash share set "
           "against the lot's own return or the share it asked; and the sleeve's dollars of an earlier call kept in "
           "STATE or in a lot's tag. A rule whose trading depends on how far the run is ahead or behind is refused, "
           "whatever its spelling. Sizing by a share of the sleeve, a lot's own return (mark over entry, its pnl over "
           "what it cost), a count of sessions held and a weight cap that does not work out the run's profit are fine.",
}
REVIEW = """You review long-only ETF programs before their ONE Validation try and ONE sealed holdout look. A program is one Python
file (NEEDS, PARAMS, decide(ctx)) that the House runs once a session after the close on daily bars: on the Train years
(2016-19 and 2022-24), then unchanged on Validation (2025), the holdout and real money. Its author saw only its Train
runs, but the models that write programs remember the market's history, so a program can encode a remembered period
without any figure in sight.
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
- RUN-START DEPENDENCE: a rule keyed to the sleeve's own dollars since the run began. Every judged run starts flat with
  the same capital (ctx.budget, a constant in a replay), so ctx.equity against ctx.budget, or ctx.equity, ctx.cash,
  ctx.caps or a lot's value or pnl against a constant or a PARAMS value, is the run's profit so far: a profit lock ("once
  the sleeve is 3% ahead, trade a token size"), a loss stop on the whole sleeve, a size or a rule that changes once the
  run is ahead or behind, however it is computed (a ratio, a difference, a running peak of equity kept in STATE). Such a
  program trades one way from a fresh start and another way mid-run, and no live program restarts where a window does.
  THE CAPITAL NEED NOT BE READ FROM ctx.budget: the House sizes an entry as the asked share of the run's capital, so a
  program can rebuild that capital from its own lots with no memory at all (a lot's qty times its entry or exit, its
  value less its pnl, exit times qty less net, each over the share it asked) and hold ctx.cash or ctx.equity against
  it; or read it off the position's state (a lot's weight in the sleeve, value over ctx.equity, or the sleeve's cash
  share, set against the lot's own return or the share it asked: the weight is that share times the lot's return times
  budget over equity); or carry the sleeve's dollars of an earlier call in STATE or in a lot's tag. A rule whose
  trading depends on how far the run is ahead or behind is refused, whatever its spelling.
  Sizing by a share of the sleeve, a sign check (a lot's pnl below zero), an exit on a lot's own return (mark over
  entry, or its pnl over what it cost), a count of sessions held and a cap on a lot's weight that does not work out the
  run's profit are fine.
- LOOKAHEAD: anything that could know the future inside the replay (it only sees ctx at session t's close; its intents
  fill at the NEXT session's open or close).
Use the contract in this prompt as the execution contract. Do not invent unavailable fields. Distinguish a verified defect
from an unresolved concern; reply unclear when the evidence is insufficient. An inactive strategy, a causal STATE
dictionary, or a price sampled from ctx and compared with another price is not a violation.
For EACH failure provide a verbatim code excerpt present in the submitted file, a contract_reference (one of: levels,
calendar, context, fills, run), and a causal counterexample: exact input conditions and the bad decision that follows.
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
        lines.append(f"Its Train verdict (Train years 2016-19 and 2022-24, the only data its author saw): {train}")
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
           "model_of", "level_refusals", "level_text", "memory_refusals", "memory_text", "grounded", "question", "record",
           "holds", "READ_CTX", "READ_BAR", "READ_LOT", "READ_CLOSED", "READ_EVENTS", "INTENT_KINDS", "INTENT_AT",
           "READING_CTX", "reading_refusals", "reading_text"]
