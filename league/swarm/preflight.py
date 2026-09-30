"""THE PREFLIGHT: a candidate program meets a small synthetic session in the decider's sandbox before a Train run is spent.

About one Train run in nine came back disqualified on Sept 30, 2026, and the retained ones were not losing ideas but
programs that could not run: `ctx.positions.items()` (a list used as a mapping), `ctx.under.get("price")` (the
underlying is an object), arithmetic on a None, a root the program never asked for. Each cost a multi-year replay on a
Gym box, a trial, and a research cycle. `check_experiment` (league/gym/experiment.py) is static; this is the runtime
half, and it runs nowhere near the Gym:

- **Where the code runs.** In the live path's own sandbox: `league.live.decider.Decider` itself, its spawn and every
  isolation rule it has (an empty environment, `-E -s`, the child's own limits, a read-only runtime copy, fail-closed
  off a root House, a mandatory private network namespace whose failed probe is retried), with one difference: the
  child runs under its own uid (`PREFLIGHT_UID`, not the 65534 the live and observe deciders run as, so an escaped
  program cannot signal or trace them). The House never executes a program in its own process. `load` is the Gym's
  `load_program` (safety check, NEEDS, PARAMS, the module body) and each call is the Gym's `Runner.decide` with its
  one-second limit.
- **What it sees.** Up to three synthetic sessions (a regular 09:30-16:00 day, no event; Tuesday to Thursday, or the
  weekdays on which its roots list the most expiries in its dte range, `session_weekdays`) on the program's own NEEDS:
  every root it names, with the chain the Gym's store lists for it (`listing`: the root's expiry weekdays within its dte
  range and the store's reach, 14 days, 45 for SPY and QQQ; the store's count of strikes a side on the root's listed
  step, $1 for the index ETFs, $5 for SPX/SPXW, a stock's by its price; two-sided quotes priced by Black-Scholes with a
  skew), the underlying's prices from the open, NEEDS['history'] prior sessions, volume unknown (NaN, as in the replay),
  the Gym's venue rules, and a flat account of the Gym's capital. It is called at the Gym's own decision minutes
  (`engine.Account.decision_minutes`). The market is made up; nothing here reads recorded data, so it is no trial and
  says nothing about profit.
- **When it refuses.** Only when the Gym would refuse or disqualify the same program on the same kind of input:
  1. `load` refuses it (the Gym's worker would refuse it identically), except a load that ran out of time or memory
     (this box is not a Gym box: that says nothing) or an `environmental` error (the House's Python, numpy and memory
     cap are not the Gym boxes');
  2. decide raised on `STREAK` (25, the Gym's `DEFAULT_MAX_ERRORS`) consecutive calls spanning at least two sessions,
     BEFORE the program returned any intent, and every error the streak may hold is named in the Runner's message
     list and is neither `environmental` nor `market_dependent` (an empty selection, a division by zero, a numeric
     key, a None: the made-up numbers could cause or spare those). Until its first intent a Gym account is flat too,
     and an erring call returns no intent, so the Gym's account would stay exactly as flat as this one while the
     program erred: the only difference left is the market's numbers, which such an error does not depend on;
  3. and a decide refusal recurs, the same error at the same line, on a fresh instance of the program meeting a sparser
     listing of the same roots (`listing(sparse=True)`: one expiry a week, the next wider strike step). A listing is
     one the Gym holds over a long stretch of Train, not on every day: a selection that keeps one contract on a
     coarser day keeps several on it (`float(...)` of it, or its truth value, then raises). The sparse listing covers a
     listing one step or one expiry schedule finer than the Gym's; a listing coarser than the Gym's only costs
     inconclusives (an empty selection is `market_dependent`).
  Anything else passes: the first intent ends the preflight (a flat account no longer mirrors the Gym's), as does a
  call past its time limit, a decider failure or the preflight's own deadline. The preflight never blocks on its own
  failure. A clean program costs one session plus `STREAK` calls of the next (a streak that begins later could only
  be confirmed by yet another session, and is left to the Gym).
- **What the researcher gets.** The exception, the line and its source, the call it began at, and the ctx API it
  should have used (`advice`): no Gym job, no version and no trial are made, and the refusal is written in the family's
  notebook.

numpy on the calling side (the House has it; the Gym's store and pyarrow are not needed). Python 3.11+.
"""

from __future__ import annotations

import atexit
import difflib
import hashlib
import math
import re
import threading
import time
import zlib
from typing import Any, Callable, Mapping, Sequence

VERSION = "preflight-v3"
#: Consecutive erring calls that refuse: the Gym's own disqualification count (`league.gym.runtime.DEFAULT_MAX_ERRORS`).
STREAK = 25
#: Synthetic sessions at most (a third only to confirm a streak that began in the second).
SESSIONS = 3
#: Distinct messages a Gym Runner keeps (`league.gym.runtime.Runner._error`): an error past them is not reported.
RUNNER_MESSAGES = 10
#: The account's capital: the Gym's default (`swarm.json` `gym.capital` overrides it for real runs; a flat account's
#: numbers are the same either way up to scale).
CAPITAL = 10_000.0
#: The preflight's wall-clock budget; past it the program passes (inconclusive).
DEADLINE_SECONDS = 20.0
#: Weekdays of the synthetic sessions when the roots list as much every weekday (Tuesday, Wednesday, Thursday), and the
#: order ties are broken in otherwise (`session_weekdays`).
WEEKDAYS = (1, 2, 3)
PREFERRED_WEEKDAYS = (1, 2, 3, 0, 4)
OPEN, CLOSE = 570, 960
MINUTES = CLOSE - OPEN + 1
RATE = 0.04
VOL = 0.18
#: What the Gym's store holds of a root's chain (scripts/data/storelib.py): NBBO 0-14 days to expiry (`MAX_DTE`) for every
#: root and, for SPY and QQQ only, their back months out to 45 (`BACK_MONTH_DTE`); `STRIKE_RANGE` listed strikes a side
#: of the money (25; 40 for SPXW).
FRONT_DTE, BACK_MONTH_DTE = 14, 45
BACK_MONTH_ROOTS = frozenset({"SPY", "QQQ"})
STORE_STRIKES = {"SPXW": 40, "SPX": 40}
STORE_DEFAULT_STRIKES = 25
DAILY, MON_WED_FRI, FRIDAY = (0, 1, 2, 3, 4), (0, 2, 4), (4,)
#: THE LISTING: each root's chain as the exchanges list it near the money over Train (2022-2024), which is what the
#: store holds: a representative price, the strike step at that price, and the weekdays that have an expiry within
#: FRONT_DTE (past it, Fridays). SPY, QQQ and SPXW list an expiry every weekday (Tuesdays and Thursdays since 2022),
#: IWM and XSP on Monday, Wednesday and Friday, every other root on Fridays (the weeklies and the monthly). The index
#: ETFs and GLD list $1 strikes and SPX/SPXW $5 at any price; a stock or another ETF lists by its price (`equity_step`:
#: $0.5 under $75, $1 under $150, $2.5 under $500, $5 above). A root not named here is a $100 stock with Friday
#: expiries.
LISTING: dict[str, tuple[float, float, tuple[int, ...]]] = {
    "SPY": (450.0, 1.0, DAILY), "QQQ": (380.0, 1.0, DAILY), "SPXW": (4500.0, 5.0, DAILY), "SPX": (4500.0, 5.0, FRIDAY),
    "IWM": (190.0, 1.0, MON_WED_FRI), "XSP": (450.0, 1.0, MON_WED_FRI), "DIA": (350.0, 1.0, FRIDAY),
    "GLD": (180.0, 1.0, FRIDAY),
}
#: Representative Train prices of the rest of the universe (`equity_step` gives their strike step, Fridays their
#: expiries).
PRICES = {"SLV": 22.0, "TLT": 100.0, "SMH": 220.0, "NVDA": 400.0, "MSFT": 300.0, "AMZN": 130.0, "AMD": 110.0,
          "GOOGL": 120.0, "TSM": 100.0, "TSLA": 220.0, "PLTR": 20.0, "SMCI": 250.0, "META": 300.0, "AAPL": 170.0,
          "MARA": 15.0, "MU": 80.0, "BABA": 90.0, "SOXL": 25.0, "TQQQ": 40.0}
DEFAULT_PRICE = 100.0
#: The roots whose near-money step is the same on every Train day (the $1 index ETFs, SPX's $5): a sparser listing
#: (`listing(sparse=True)`) keeps it; any other root's sparser listing takes the next wider step.
FIXED_STEP = frozenset({"SPY", "QQQ", "IWM", "XSP", "DIA", "SPXW", "SPX"})
WIDER = {0.5: 1.0, 1.0: 2.5, 2.5: 5.0, 5.0: 10.0}


def equity_step(price: float) -> float:
    """The strike step a stock's weekly lists near the money at `price` (`LISTING`)."""
    return 0.5 if price < 75 else 1.0 if price < 150 else 2.5 if price < 500 else 5.0


def listing(root: str, *, sparse: bool = False) -> tuple[float, float, tuple[int, ...]]:
    """(price, strike step, expiry weekdays) of `root` (`LISTING`). `sparse`: the same root listed more thinly, one
    expiry a week (Fridays) and, unless the root's step never changes, the next wider strike step. A refusal on the
    listing must recur on the sparse one (`run`): a listing one step finer than the Gym's on some day (a selection that
    holds one contract there holds several here) then never refuses on its own."""
    root = str(root).upper()
    if root in LISTING:
        price, step, weekdays = LISTING[root]
    else:
        price = PRICES.get(root, DEFAULT_PRICE)
        step, weekdays = equity_step(price), FRIDAY
    if sparse:
        return price, (step if root in FIXED_STEP else WIDER.get(step, 2.0 * step)), FRIDAY
    return price, step, weekdays


def expiries(root: str, weekday: int, dte_min: int, dte_max: int, weekdays: Sequence[int]) -> list[int]:
    """The days to expiry listed on a session of `weekday` (0 = Monday) within [dte_min, dte_max]: an expiry on each of
    `weekdays` out to FRONT_DTE, Fridays past it, and nothing past what the store keeps for the root."""
    top = BACK_MONTH_DTE if str(root).upper() in BACK_MONTH_ROOTS else FRONT_DTE
    return [d for d in range(int(dte_min), min(int(dte_max), top) + 1)
            if (weekday + d) % 7 in (weekdays if d <= FRONT_DTE else FRIDAY)]


def session_weekdays(roots: Sequence[str], needs: Mapping[str, Any], *, sparse: bool = False) -> tuple[int, ...]:
    """The synthetic sessions' weekdays: the SESSIONS weekdays on which the roots' listings hold the most expiries in the
    program's dte range (ties: Tuesday, Wednesday, Thursday, Monday, Friday), in calendar order. A Friday-only root with
    dte [10, 20] lists on Monday, Tuesday and Friday (11, 10 and 14 days out), not midweek: its sessions are those."""
    dte_min, dte_max = (int(x) for x in needs["dte"])
    held = {day: sum(len(expiries(root, day, dte_min, dte_max, listing(root, sparse=sparse)[2])) for root in roots)
            for day in PREFERRED_WEEKDAYS}
    ranked = sorted(PREFERRED_WEEKDAYS, key=lambda day: (-held[day], PREFERRED_WEEKDAYS.index(day)))
    return tuple(sorted(ranked[:SESSIONS]))


# ------------------------------------------------------------------------------------------------ the synthetic market
def _rng(root: str, salt: int) -> Any:
    import numpy as np

    return np.random.default_rng(zlib.crc32(f"{root}:{salt}".encode()) & 0xFFFFFFFF)


class Market:
    """Synthetic sessions for a program's NEEDS (the module docstring) on each root's listed chain (`listing`), or on
    its sparser listing (`sparse`). Deterministic: the same roots and NEEDS make the same market."""

    def __init__(self, roots: Sequence[str], needs: Mapping[str, Any], *, sparse: bool = False):
        import numpy as np

        from ..gym import greeks as G

        self.roots = tuple(roots)
        self.needs = dict(needs)
        self.sparse = bool(sparse)
        self.weekdays = session_weekdays(self.roots, needs, sparse=self.sparse)
        dte_min, dte_max = (int(x) for x in needs["dte"])
        history = int(needs["history"])
        per_minute = VOL / math.sqrt(252 * 390)
        self.days: dict[str, list[dict[str, Any]]] = {}
        for root in self.roots:
            rng = _rng(root, 1)
            spot, step, weekdays = listing(root, sparse=self.sparse)
            side = STORE_STRIKES.get(root, STORE_DEFAULT_STRIKES)
            bars, paths = [], []
            for _ in range(history + SESSIONS):
                spot *= math.exp(rng.normal(0.0, 0.004))  # the overnight move
                path = spot * np.exp(np.cumsum(rng.normal(0.0, per_minute, MINUTES)))
                path[0] = spot
                bars.append((float(path[0]), float(path.max()), float(path.min()), float(path[-1])))
                paths.append(path)
                spot = float(path[-1])
            sessions = []
            for s in range(SESSIONS):
                i = history + s
                prior = np.array(bars[i - history:i], dtype=np.float64).reshape(-1, 4)
                path = paths[i]
                weekday = self.weekdays[s]
                dtes = expiries(root, weekday, dte_min, dte_max, weekdays)
                atm = round(float(path[0]) / step) * step
                ks = atm + step * np.arange(-side, side + 1)  # the store's strikes a side of the open's money
                ks = ks[ks > 0]
                dte = np.repeat(np.array(dtes, dtype=np.int64), ks.size * 2)
                strike = np.tile(np.repeat(ks, 2), len(dtes))
                is_call = np.tile(np.array([True, False]), ks.size * len(dtes))
                n = strike.size
                sessions.append({"weekday": weekday, "path": path, "prior": prior, "dte": dte, "strike": strike,
                                 "is_call": is_call, "oi": rng.integers(0, 50_000, n), "rng": _rng(root, 100 + s)})
            self.days[root] = sessions
        self._G = G

    def snapshot(self, root: str, session: int, mi: int) -> Any:
        """The root's chain at minute `mi` of the session (a `Snapshot`, as the replay makes one)."""
        import numpy as np

        from ..gym.ctx import Snapshot

        day = self.days[root][session]
        spot = float(day["path"][mi])
        dte, strike, is_call = day["dte"], day["strike"], day["is_call"]
        n = strike.size
        if n == 0:
            return Snapshot(root, OPEN + mi, spot, dte, strike, is_call, np.zeros(0), np.zeros(0), oi=day["oi"], rate=RATE)
        years = self._G.years_to_expiry(dte, OPEN + mi, close_minute=CLOSE)
        m = np.log(strike / spot)
        sigma = VOL * (1.0 - 1.5 * m + 8.0 * m * m)
        mid = self._G.bs_price(spot, strike, years, RATE, sigma, is_call)
        tick = 0.05 if root in ("SPXW", "SPX") else 0.01
        half = np.maximum(tick, np.round(mid * 0.03 / tick) * tick)
        bid = np.maximum(0.0, np.round((mid - half) / tick) * tick)
        ask = np.maximum(bid + tick, np.round((mid + half) / tick) * tick)
        rng = day["rng"]
        return Snapshot(root, OPEN + mi, spot, dte, strike, is_call, bid, ask, rng.integers(5, 400, n), rng.integers(5, 400, n),
                        oi=day["oi"], rate=RATE, close_minute=CLOSE)

    def under(self, root: str, session: int, mi: int) -> Any:
        """The root's underlying at minute `mi` (as `engine.DayData.under`: prices from the open, prior sessions, volume
        unknown as in a replay without first-observation receipts)."""
        from ..gym.ctx import underlying_view

        day = self.days[root][session]
        prior = day["prior"]
        return underlying_view(root, day["path"][: mi + 1], opens=prior[:, 0], highs=prior[:, 1], lows=prior[:, 2],
                               closes=prior[:, 3], volume_provenance="historical_without_asof",
                               daily_volume_provenance="unavailable")


def decision_minutes(needs: Mapping[str, Any]) -> list[int]:
    """The Gym's decision minutes on a regular session (`engine.Account.decision_minutes`)."""
    first = max(int(needs["start"]), OPEN + 1) - OPEN
    last = min(int(needs["end"]) - OPEN, MINUTES - 3)
    return list(range(first, last + 1, int(needs["cadence"]))) if first <= last else []


# ------------------------------------------------------------------------------------------------ what to say
_LIST_ROWS = ("ctx.positions, ctx.orders and ctx.closed are LISTS of dicts (ctx.rejects a list of strings), never "
              "mappings: iterate `for p in ctx.positions:` and read `p['id']`, `p['legs']`, `p['pnl']`; find one with "
              "`next((p for p in ctx.positions if p['id'] == pid), None)`; key them yourself with "
              "`{p['id']: p for p in ctx.positions}`.")
_NONE = ("a value was None. In the Gym: `ctx.chain`/`ctx.under` are None when the first root has no data now; "
         "`ctx.chains.get(root)` and `ctx.underlyings.get(root)` are None for a root without data; `dict.get` is None for "
         "a missing key (STATE starts empty in every run; ctx.params holds exactly your PARAMS keys{params}); a "
         "position's `mark`, `natural` and `pnl` are None without a two-sided quote. Test `is None` (or give `.get` a "
         "default) before arithmetic or a comparison.")
POSITION_KEYS = ("id", "type", "root", "qty", "legs", "entry", "credit", "max_loss", "mark", "natural", "pnl", "held_minutes",
                 "held_days", "tag")
LEG_KEYS = ("id", "dte", "strike", "is_call", "side", "ratio")
ORDER_KEYS = ("id", "kind", "type", "root", "qty", "filled", "limit", "age_minutes", "position", "tag")


def _names(cls: Any, extra: Sequence[str] = ()) -> list[str]:
    return [n for n in getattr(cls, "__slots__", ()) if not n.startswith("_")] + list(extra)


def _close(word: str, names: Sequence[str]) -> str:
    near = difflib.get_close_matches(word, list(names), n=1, cutoff=0.6)
    return f" Did you mean `{near[0]}`?" if near and near[0] != word else ""


def advice(message: str, *, roots: Sequence[str] = (), params: Mapping[str, Any] | None = None, source: str = "") -> str:
    """The ctx API a runtime error message points at (PROGRAM.md / league/CONTRACT.md, "ctx"): one or two sentences."""
    from ..gym.ctx import ChainView, Ctx, UnderlyingView

    chain = _names(ChainView, ("iv", "delta", "gamma", "theta", "vega"))
    under = _names(UnderlyingView)
    keys = sorted((params or {}).keys())
    shown = f": {', '.join(keys[:24])}" if keys else ""
    text = str(message or "")
    m = re.search(r"'(list|tuple)' object has no attribute '(\w+)'", text)
    if m:
        return _LIST_ROWS
    m = re.search(r"'UnderlyingView' object has no attribute '(\w+)'", text)
    if m:
        return ("ctx.under and ctx.underlyings[root] are objects read by ATTRIBUTE, not dicts (no `.get`, no `[...]`): "
                + ", ".join(under) + ". E.g. `u = ctx.underlyings.get(root)`, then `u.price`, `u.closes[-1]`; an optional "
                "field is `getattr(u, 'name', None)`." + _close(m.group(1), under))
    m = re.search(r"'ChainView' object has no attribute '(\w+)'", text)
    if m:
        return ("ctx.chains[root] (and ctx.chain) holds numpy arrays read by ATTRIBUTE, one entry per contract: "
                + ", ".join(chain) + " (`strike` is singular; `expiries` lists the days to expiry present)."
                + _close(m.group(1), chain))
    m = re.search(r"'Ctx' object has no attribute '(\w+)'", text)
    if m:
        fields = _names(Ctx)
        return "ctx has these fields only: " + ", ".join(fields) + "." + _close(m.group(1), fields)
    m = re.search(r"'dict' object has no attribute '(\w+)'", text)
    if m:
        return ("position and order rows, ctx.rules[root], ctx.params and ctx.events are dicts: read `row['name']`, not "
                "`row.name`. A position row's keys: " + ", ".join(POSITION_KEYS) + ".")
    if re.search(r"'(float|int)' object is not (subscriptable|iterable)", text):
        return ("a number was indexed or iterated: ctx.under.price, .open, .high, .low and .prior_close are numbers; "
                "ctx.under.prices (today's minutes) and .closes, .opens, .highs, .lows (prior sessions) are the arrays.")
    if re.search(r"'(ChainView|UnderlyingView|Ctx)' object is not (subscriptable|iterable)", text):
        return ("ctx, a chain (ctx.chains[root]) and an underlying (ctx.underlyings[root]) are objects: read their fields as "
                "attributes (`ctx.chain.strike`, `ctx.under.price`); only ctx.chains, ctx.underlyings, ctx.rules, "
                "ctx.params and ctx.events are dicts.")
    if "NoneType" in text:
        return _NONE.format(params=shown)
    m = re.search(r"KeyError: '([^']*)'", text)
    if m:
        key = m.group(1)
        if key.upper() == key and key.isalpha() and key not in keys:
            return (f"ctx.chains, ctx.underlyings and ctx.rules hold only the NEEDS['roots'] with data now "
                    f"({', '.join(roots) or 'none'}); `{key}` is not one of them. Name it in NEEDS['roots'] (the Gym's "
                    f"admitted roots only), or read `ctx.chains.get(root)` and skip a None.")
        if key in keys:
            return (f"`{key}` is one of your PARAMS: read it as `ctx.params['{key}']` (or `PARAMS['{key}']`); it is not in "
                    "STATE (empty at the start of every run), a position row or ctx.rules.")
        if key in LEG_KEYS and key not in POSITION_KEYS:
            return (f"a position row has no `{key}`; its legs do (`p['legs'][i]['{key}']`). A position row's keys: "
                    + ", ".join(POSITION_KEYS) + "; a leg's: " + ", ".join(LEG_KEYS) + ".")
        return ("a missing key. ctx.params holds exactly your PARAMS keys" + shown + "; STATE starts empty in every run "
                "(use `STATE.get(k, default)`); a position row's keys: " + ", ".join(POSITION_KEYS) + "; a working order's: "
                + ", ".join(ORDER_KEYS) + "; ctx.events: fomc, cpi, jobs, monthly_opex, quarter_end, half_day.")
    if re.search(r"list indices must be integers or slices, not (dict|str)", text):
        return "a list was indexed by a row or a key: " + _LIST_ROWS
    if re.search(r"'(int|float|str|bool|numpy\.\w+)' object has no attribute 'get'", text):
        return ("`.get` was called on a number or a string, not a dict: check what the name holds (a position row's "
                "fields are plain values; ctx.chain fields are numpy arrays; ctx.under fields are attributes).")
    if "truth value of an array" in text:
        return ("a numpy array was used as one boolean: chain fields are arrays, one entry per contract, and a mask keeps "
                "every contract that matches it (every listed expiry, every strike within a tolerance); use `.any()`, "
                "`.all()`, or index a single contract first (`i = np.flatnonzero(mask)`, check `i.size`).")
    if re.search(r"only (length-1|0-dimensional) arrays can be converted|convert an array of size 1", text):
        return ("an array was converted to one number: `float(c.bid[mask])` needs a mask that keeps exactly one contract, "
                "and the Gym's numpy refuses even that; index one contract first (`i = np.flatnonzero(mask)`, check "
                "`i.size`, then `float(c.bid[i[0]])`).")
    if "read-only" in text:
        return "arrays from ctx are read-only: copy one first (`np.array(ctx.chain.mid)`) before changing it."
    if "IndexError" in text:
        return ("an empty or short array or list was indexed: a chain slice can be empty (`ctx.chain.n == 0`, or a mask "
                "that matches no contract), ctx.under.closes holds at most NEEDS['history'] sessions, and ctx.positions "
                "is empty until an open fills. Check the length first.")
    if "ZeroDivisionError" in text:
        return "a division by zero: guard the denominator (a bid, a spread or a count can be 0)."
    if "decide returned" in text or "an intent" in text:
        return "decide returns a list of intent dicts (or [] / None), each with exactly one of 'open', 'close' or 'cancel'."
    if "is not defined" in text:
        return "a name is not defined: only math and numpy import, and the short list of safe builtins is all there is."
    return "check the line against the ctx section of league/CONTRACT.md."


#: Attribute names no Python or numpy version gives a number, a string or an array: reading one of them off such a value
#: is the program's mistake on every version (the ctx's own names are added in `environmental`).
_NEVER_ON_SCALARS = frozenset({"get", "items", "keys", "values", "update", "setdefault", "popitem", "append", "extend",
                               "insert", "remove", "add", "discard"})
#: Types whose attributes Python 3.11-3.14 all share (none gained a method since 3.11), and the ctx's own classes (the same
#: league/gym code on the House and in the Gym's bundle). An attribute missing on one of them is missing in the Gym too.
_STABLE_TYPES = frozenset({"list", "tuple", "dict", "set", "frozenset", "NoneType", "range", "ChainView", "UnderlyingView",
                           "Ctx", "Snapshot"})


def environmental(message: str) -> bool:
    """An error that could be this box's and not the Gym's: the House runs Python 3.11 with numpy 2.4 and caps the
    decider child at 2 GB, the Gym's boxes run 3.12+ with numpy 2.5 (requirements-gym.txt) and give a worker 6 GB. So a
    module attribute one version has and the other lacks (`math.sumprod`, a numpy function), a keyword, a method a
    newer Python gave a number, a string or a numpy value (`int.is_integer`), memory, or recursion depth says nothing
    about the program. Such an error never refuses."""
    text = str(message or "")
    if ("unexpected keyword argument" in text or "No module named" in text or "MemoryError" in text
            or "Unable to allocate" in text or "recursed too deep" in text or "RecursionError" in text):
        return True
    if re.search(r"module '[\w.]+' has no attribute", text):
        return True
    m = re.search(r"'([\w.]+)' object has no attribute '(\w+)'", text)
    if m and m.group(1) not in _STABLE_TYPES:
        from ..gym.ctx import ChainView, Ctx, UnderlyingView

        ctx_names = set(_names(ChainView)) | set(_names(UnderlyingView)) | set(_names(Ctx)) | set(POSITION_KEYS) | \
            set(ORDER_KEYS) | set(LEG_KEYS)
        return m.group(2) not in _NEVER_ON_SCALARS and m.group(2) not in ctx_names
    return False


#: Errors whose presence turns on the market's numbers, not on the program's use of the API: an empty selection, a
#: division by a price or a count, a strike looked up in a dict, a log of a non-positive number, a None from a search that
#: found nothing on this market. The synthetic market is not the real one, so such an error proves nothing about the Gym
#: and never refuses (the Gym still judges it).
_MARKET_ERRORS = re.compile(r"\b(IndexError|ZeroDivisionError|StopIteration|OverflowError|FloatingPointError|NoneType|"
                            r"KeyError: -?[\d.]+|KeyError: \(|KeyError: np\.|KeyError: nan)")
_MARKET_VALUES = ("empty sequence", "argument is empty", "zero-size array", "truth value of an empty array",
                  "math domain error", "not in list", "cannot convert float NaN", "cannot convert float infinity",
                  "attempt to get argm", "not enough values to unpack", "too many values to unpack",
                  "array must not contain infs or NaNs")


def market_dependent(message: str) -> bool:
    """An error the market's numbers could cause or spare (`_MARKET_ERRORS`, `_MARKET_VALUES`): never a refusal."""
    text = str(message or "")
    return bool(_MARKET_ERRORS.search(text)) or ("ValueError" in text and any(v in text for v in _MARKET_VALUES))


def _declared(code: str, params: Mapping[str, Any] | None) -> dict[str, Any]:
    """The program's PARAMS keys (its literal declaration with the overrides), for the advice; the overrides alone when
    the declaration is not a literal."""
    import ast

    out: dict[str, Any] = {}
    try:
        from ..gym.safety import params_declaration

        declared = ast.literal_eval(params_declaration(ast.parse(code)).value)
        if isinstance(declared, dict):
            out.update(declared)
    except Exception:  # noqa: BLE001 - advice only
        pass
    out.update(params or {})
    return out


def _located(message: str, code: str) -> tuple[int | None, str]:
    m = re.match(r"line (\d+):", str(message or ""))
    if not m:
        return None, ""
    line = int(m.group(1))
    lines = code.splitlines()
    return line, (lines[line - 1].strip()[:200] if 0 < line <= len(lines) else "")


# ------------------------------------------------------------------------------------------------ the run
def _answer(status: str, why: str, **fields: Any) -> dict[str, Any]:
    return {"status": status, "why": why, "version": VERSION, **fields}


def run(code: str, params: Mapping[str, Any] | None, decider: Any, *, universe: Sequence[str] | None = None,
        name: str = "preflight", deadline: float = DEADLINE_SECONDS, clock: Callable[[], float] = time.monotonic) -> dict:
    """The preflight of one (code, params) on `decider` (a `league.live.decider` Decider or InlineDecider). `universe`: the
    run's roots (a program trades its NEEDS roots within them). {"status": "passed" | "refused" | "inconclusive", ...}."""
    from ..live.decider import DeciderError, ProgramRefused

    began = clock()
    key = f"preflight:{hashlib.sha256((code + repr(sorted((params or {}).items()))).encode()).hexdigest()[:16]}:{began:.6f}"
    try:
        info = decider.load(key, code, dict(params or {}), name)
    except ProgramRefused as exc:
        message = str(exc)
        if "ran past" in message or environmental(message):
            return _answer("inconclusive", f"the load says nothing on this box: {message[:300]}")
        line, source = _located(message, code)
        return _answer("refused", "the program does not load (the Gym's worker would refuse it the same way)", stage="load",
                       error=message[:500], line=line, source=source, calls=0,
                       hint=advice(message, params=_declared(code, params), source=source))
    except DeciderError as exc:
        return _answer("inconclusive", f"the sandbox failed: {str(exc)[:300]}")
    try:
        verdict = _decide_loop(code, params or {}, decider, key, info["needs"], universe, began, deadline, clock)
    except DeciderError as exc:
        return _answer("inconclusive", f"the sandbox failed: {str(exc)[:300]}")
    finally:
        _drop(decider, key)
    if verdict["status"] != "refused":
        return verdict
    # THE SPARSE LISTING: a fresh instance of the program on the same roots listed more thinly (`listing(sparse=True)`).
    # The refusal stands only when the same error at the same line recurs there, so a listing one step finer than the
    # Gym's on some day (a selection that holds one contract in the Gym holds several here) never refuses on its own.
    again_key = key + ":sparse"
    try:
        decider.load(again_key, code, dict(params or {}), name)
        again = _decide_loop(code, params or {}, decider, again_key, info["needs"], universe, began, deadline, clock,
                             sparse=True)
    except (ProgramRefused, DeciderError) as exc:
        return _answer("inconclusive", f"the sandbox failed on the sparser listing: {str(exc)[:300]}",
                       calls=verdict.get("calls"))
    finally:
        _drop(decider, again_key)
    if again["status"] == "refused" and _kind(again.get("error")) == _kind(verdict.get("error")):
        verdict["why"] += "; again on a sparser listing (one expiry a week, a wider strike step)"
        verdict["calls"] = int(verdict.get("calls") or 0) + int(again.get("calls") or 0)
        return verdict
    return _answer("inconclusive", "the error did not recur on a sparser listing of the same roots (one expiry a week, a "
                                   "wider strike step): it may turn on how many contracts the chain lists, which the "
                                   f"Gym's store decides: {str(verdict.get('error') or '')[:240]}",
                   calls=int(verdict.get("calls") or 0) + int(again.get("calls") or 0))


def _drop(decider: Any, key: str) -> None:
    try:
        decider.drop(key)
    except Exception:  # noqa: BLE001 - dropping a runner never fails the preflight
        pass


def _kind(message: Any) -> tuple[str, str]:
    """An error's line and exception type (`line 12: TypeError: ...` -> ("12", "TypeError")): the same kind of error at
    the same place, whatever numbers it prints."""
    m = re.match(r"(?:line (\d+): )?([\w.]+)", str(message or ""))
    return (m.group(1) or "", m.group(2)) if m else ("", "")


def _decide_loop(code: str, params: Mapping[str, Any], decider: Any, key: str, needs: Mapping[str, Any],
                 universe: Sequence[str] | None, began: float, deadline: float, clock: Callable[[], float], *,
                 sparse: bool = False) -> dict:
    from ..gym import venue as V
    from ..gym.events import EVENT_NAMES

    wanted = [str(r).upper() for r in needs["roots"]]
    roots = [r for r in wanted if not universe or r in {str(u).upper() for u in universe}]
    schedule = decision_minutes(needs)
    if not roots or not schedule:
        return _answer("passed", "the program has no decision in the run's roots and hours", calls=0)
    market = Market(roots, needs, sparse=sparse)
    rules = {r: V.rules_for(r).as_dict() for r in roots}
    quiet = {name: False for name in EVENT_NAMES}
    restarts = getattr(decider, "restarts", 0)
    calls = errors = timeouts = 0
    streak: list[tuple[int, int]] = []    # (session, call) of the current run of erring calls
    named: list[str] = []                 # the streak's errors the Runner's message list names (new in it at the call)
    unnamed = blind = False               # a streak error already in the list / one the full list could not take
    first_message = ""
    messages: list[str] = []
    for s in range(SESSIONS):
        if s == SESSIONS - 1 and not streak:
            break  # the last session only confirms a streak still running at the end of the one before
        for k, mi in enumerate(schedule):
            if s and k >= STREAK and not streak:
                # A streak must span two sessions: one not running STREAK calls into a later session cannot, this session.
                return _answer("passed", "no persistent error on the synthetic sessions", calls=calls, errors=errors)
            if clock() - began > deadline:
                return _answer("inconclusive", f"the preflight's {deadline:.0f} s ran out after {calls} calls", calls=calls)
            token = s * 1000 + mi
            snaps = {(r, token): market.snapshot(r, s, mi) for r in roots}
            unders = {(r, int(needs["history"]), token): market.under(r, s, mi) for r in roots}
            job = {"key": key, "mi": token, "roots": roots, "minute": OPEN + mi, "open_minute": OPEN, "close_minute": CLOSE,
                   "weekday": market.weekdays[s], "positions": [], "orders": [], "cash": CAPITAL, "equity": CAPITAL,
                   "budget": CAPITAL, "buying_power": CAPITAL, "rules": rules, "events": quiet, "events_next": quiet,
                   "closed": [], "rejects": []}
            answer = decider.decide(snaps, unders, [job]).get(key) or {}
            stats = answer.get("stats")
            if answer.get("missing") or answer.get("skipped") or not isinstance(stats, Mapping) \
                    or getattr(decider, "restarts", 0) != restarts or int(stats.get("calls") or 0) != calls + 1:
                return _answer("inconclusive", "the sandbox lost the program's runner", calls=calls)
            calls += 1
            if int(stats.get("timeouts") or 0) > timeouts:
                return _answer("inconclusive", "a call ran past its time limit (this box is not a Gym box)", calls=calls)
            raised = int(stats.get("errors") or 0) - errors
            errors = int(stats.get("errors") or 0)
            seen = [str(m) for m in stats.get("messages") or []]
            if answer.get("intents"):
                return _answer("passed", f"the program returned an intent at call {calls}; a flat account no longer "
                                         "mirrors the Gym's from there", calls=calls, errors=errors)
            if raised <= 0:
                streak, named, unnamed, blind, first_message = [], [], False, False, ""
                messages = seen
                continue
            # The Runner keeps the first RUNNER_MESSAGES distinct messages only: a call's error is named when it is new in
            # the list; one already there is one of the list's; one the full list did not take could be anything.
            new = [m for m in seen if m not in messages]
            if not streak:
                first_message = new[0] if new else ""
            named.extend(new)
            if raised > len(new):
                if len(messages) + len(new) >= RUNNER_MESSAGES:
                    blind = True
                else:
                    unnamed = True
            messages = seen
            streak.append((s, calls))
            if len(streak) >= STREAK and len({x[0] for x in streak}) >= 2:
                return _verdict(code, params, roots, streak, named, unnamed, blind, first_message, seen, calls, errors)
    return _answer("passed", "no persistent error on the synthetic sessions", calls=calls, errors=errors)


def _verdict(code: str, params: Mapping[str, Any], roots: Sequence[str], streak: Sequence[tuple[int, int]],
             named: Sequence[str], unnamed: bool, blind: bool, first_message: str, seen: Sequence[str], calls: int,
             errors: int) -> dict:
    """A streak long enough to refuse: refused only when every error it may hold is known and says the program misuses the
    API on any market, on any box (not `environmental`, not `market_dependent`)."""
    if blind:
        return _answer("inconclusive", f"the Runner's list holds {RUNNER_MESSAGES} messages and the streak's error is not "
                                       "among them", calls=calls, errors=errors)
    candidates = list(dict.fromkeys([*named, *(seen if unnamed else ())]))
    if not first_message and len(candidates) == 1:
        first_message = candidates[0]
    if not first_message or not candidates:
        return _answer("inconclusive", "the streak's first error cannot be told apart from earlier ones", calls=calls,
                       errors=errors)
    if any(environmental(m) for m in [*candidates, *seen]):
        found = next(m for m in [*candidates, *seen] if environmental(m))
        return _answer("inconclusive", f"the error may be this box's Python, numpy or memory, not the Gym's: {found[:300]}",
                       calls=calls, errors=errors)
    if any(market_dependent(m) for m in candidates):
        found = next(m for m in candidates if market_dependent(m))
        return _answer("inconclusive", f"the error turns on the market's numbers, which are made up here: {found[:300]}",
                       calls=calls, errors=errors)
    line, source = _located(first_message, code)
    return _answer("refused", f"decide raised on every call from call {streak[0][1]} ({len(streak)} calls over "
                              f"{len({x[0] for x in streak})} synthetic sessions, before any intent)",
                   stage="decide", error=first_message[:500], line=line, source=source, calls=calls, errors=errors,
                   messages=[m[:200] for m in candidates[:4]],
                   hint=advice(first_message, roots=roots, params=_declared(code, params), source=source))


# ------------------------------------------------------------------------------------------------ the House's instance
#: The preflight child's uid and gid on the root House: not 65534, which the live and observe decider children run as.
#: Programs no Gym has run yet execute here, so a process that escaped the code check must not be able to signal or trace
#: the money path's decider (the kernel's kill and ptrace checks compare these uids). No process on the House runs as it.
PREFLIGHT_UID = 65533


def child_uids(pid: int) -> tuple[int, ...]:
    """A process's real and effective uid, from `/proc/<pid>/status` (as the parent's namespace sees them); () when it
    cannot be read."""
    try:
        with open(f"/proc/{int(pid)}/status", encoding="ascii", errors="replace") as status:
            for line in status:
                if line.startswith("Uid:"):
                    return tuple(int(x) for x in line.split()[1:3])
    except (OSError, ValueError):
        pass
    return ()


def _sandbox() -> Any:
    """`league.live.decider.Decider` under the preflight's own uid. Nothing of the decider is copied: the spawn is
    `Decider._spawn`, so every isolation rule it has or gains (fail-closed off a root House, the network-namespace probe
    and its retry window, the empty environment, the child's own limits, the read-only runtime copy) is the
    preflight's too. `Decider._spawn` builds the child's credentials and hands that very dict to `_namespace` (the
    probe runs under them) and then to `Popen`; `_namespace` here writes the preflight's uid into it. Should a later
    decider stop doing that, the child would run as 65534: `_spawn` then reads the child's uid back and kills a child
    that is not `PREFLIGHT_UID` before any program reaches it."""
    from ..live import decider as D

    class SandboxDecider(D.Decider):
        uid = PREFLIGHT_UID

        def _namespace(self, budget_seconds: float, credentials: Any) -> bool:
            if credentials:  # the root House's credentials (the child's): the preflight's own uid and gid
                credentials.update(user=self.uid, group=self.uid, extra_groups=[])
            return super()._namespace(budget_seconds, credentials)

        def _spawn(self, budget_seconds: float = 10.0) -> None:
            super()._spawn(budget_seconds)
            if self.isolated and self.proc is not None:
                uids = child_uids(self.proc.pid)
                if not uids or any(uid != self.uid for uid in uids):
                    self._kill()
                    raise D.DeciderError(f"the preflight's decider child runs as uid {uids or 'unknown'}, not "
                                         f"{self.uid}: it was killed before any program reached it")

    return SandboxDecider


class Preflight:
    """The researcher's preflight: one sandboxed decider child for the process, one preflight at a time (the House has
    one core; a Gym run can wait a second, the live minute cannot). `decider` for tests (an InlineDecider)."""

    def __init__(self, decider: Any = None, *, deadline: float = DEADLINE_SECONDS, wait: float = 60.0):
        self._decider = decider
        self.deadline, self.wait = float(deadline), float(wait)
        self._lock = threading.Lock()

    def decider(self) -> Any:
        if self._decider is None:
            # max_errors: every call's own outcome is read (the preflight counts its streak itself, at the Gym's 25).
            self._decider = _sandbox()(timeout=1.0, max_errors=10 ** 9)
            atexit.register(self.close)  # the child and its read-only runtime copy go with the process
        return self._decider

    def __call__(self, code: str, params: Mapping[str, Any] | None = None, *, roots: Sequence[str] | None = None,
                 name: str = "preflight") -> dict:
        began = time.monotonic()
        if not self._lock.acquire(timeout=self.wait):
            return _answer("inconclusive", "another preflight held the sandbox", seconds=0.0)
        try:
            out = run(code, params, self.decider(), universe=roots, name=name, deadline=self.deadline)
        finally:
            self._lock.release()
        out["seconds"] = round(time.monotonic() - began, 3)
        return out

    def close(self) -> None:
        if self._decider is not None and callable(getattr(self._decider, "close", None)):
            self._decider.close()


__all__ = ["VERSION", "STREAK", "SESSIONS", "PREFLIGHT_UID", "LISTING", "Market", "Preflight", "advice",
           "decision_minutes", "environmental", "equity_step", "expiries", "listing", "market_dependent", "run",
           "session_weekdays"]
