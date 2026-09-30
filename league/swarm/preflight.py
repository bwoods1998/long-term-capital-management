"""THE PREFLIGHT: a candidate program meets a small synthetic session in the decider's sandbox before a Train run is spent.

About one Train run in nine came back disqualified on Sept 30, 2026, and the retained ones were not losing ideas but
programs that could not run: `ctx.positions.items()` (a list used as a mapping), `ctx.under.get("price")` (the
underlying is an object), arithmetic on a None, a root the program never asked for. Each cost a multi-year replay on a
Gym box, a trial, and a research cycle. `check_experiment` (league/gym/experiment.py) is static; this is the runtime
half, and it runs nowhere near the Gym:

- **Where the code runs.** In the live path's own sandbox, `league.live.decider.Decider`: a child process with an
  empty environment, `-E -s`, a capped address space and (as root, on the House) uid 65534 in a private network
  namespace. The House never executes a program in its own process. `load` is the Gym's `load_program` (safety
  check, NEEDS, PARAMS, the module body) and each call is the Gym's `Runner.decide` with its one-second limit.
- **What it sees.** Up to three synthetic sessions (Tuesday to Thursday, a regular 09:30-16:00 day, no event) on the
  program's own NEEDS: every root it names, with a full chain (every weekday expiry in its dte range, strikes past its
  band, two-sided quotes priced by Black-Scholes with a skew), the underlying's prices from the open, NEEDS['history']
  prior sessions, volume unknown (NaN, as in the replay), the Gym's venue rules, and a flat account of the Gym's
  capital. It is called at the Gym's own decision minutes (`engine.Account.decision_minutes`). The market is made up;
  nothing here reads recorded data, so it is no trial and says nothing about profit.
- **When it refuses.** Only when the Gym would refuse or disqualify the same program on the same kind of input:
  1. `load` refuses it (the Gym's worker would refuse it identically), except a load that ran out of time or memory
     (this box is not a Gym box: that says nothing);
  2. decide raised on `STREAK` (25, the Gym's `DEFAULT_MAX_ERRORS`) consecutive calls spanning at least two sessions,
     BEFORE the program returned any intent. Until its first intent a Gym account is flat too, and an erring call
     returns no intent, so the Gym's account would stay exactly as flat as this one while the program erred: the only
     difference left is the market's numbers, and a program that errs on every call across two made-up sessions
     errs on real ones.
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

VERSION = "preflight-v1"
#: Consecutive erring calls that refuse: the Gym's own disqualification count (`league.gym.runtime.DEFAULT_MAX_ERRORS`).
STREAK = 25
#: Synthetic sessions at most (a third only to confirm a streak that began in the second).
SESSIONS = 3
#: The account's capital: the Gym's default (`swarm.json` `gym.capital` overrides it for real runs; a flat account's
#: numbers are the same either way up to scale).
CAPITAL = 10_000.0
#: The preflight's wall-clock budget; past it the program passes (inconclusive).
DEADLINE_SECONDS = 30.0
#: Weekdays of the synthetic sessions (Tuesday, Wednesday, Thursday).
WEEKDAYS = (1, 2, 3)
OPEN, CLOSE = 570, 960
MINUTES = CLOSE - OPEN + 1
RATE = 0.04
VOL = 0.18
SPOTS = {"SPY": 450.0, "QQQ": 380.0, "IWM": 190.0, "DIA": 350.0, "XSP": 450.0, "SPXW": 4500.0, "SPX": 4500.0}


# ------------------------------------------------------------------------------------------------ the synthetic market
def _rng(root: str, salt: int) -> Any:
    import numpy as np

    return np.random.default_rng(zlib.crc32(f"{root}:{salt}".encode()) & 0xFFFFFFFF)


def _step(root: str, spot: float, band: float) -> float:
    """A strike step like the listed ones near the money, widened so a wide band stays at most ~60 strikes a side."""
    base = 5.0 if root in ("SPXW", "SPX") else (1.0 if spot >= 50 else 0.5)
    for step in (base, base * 2.5, base * 5, base * 10, base * 25, base * 50):
        if spot * (band + 0.02) / step <= 60:
            return step
    return base * 100


class Market:
    """Synthetic sessions for a program's NEEDS (the module docstring). Deterministic: the same roots and NEEDS make the
    same market."""

    def __init__(self, roots: Sequence[str], needs: Mapping[str, Any]):
        import numpy as np

        from ..gym import greeks as G

        self.roots = tuple(roots)
        self.needs = dict(needs)
        dte_min, dte_max = (int(x) for x in needs["dte"])
        band, history = float(needs["band"]), int(needs["history"])
        per_minute = VOL / math.sqrt(252 * 390)
        self.days: dict[str, list[dict[str, Any]]] = {}
        for root in self.roots:
            rng = _rng(root, 1)
            spot = SPOTS.get(root, 100.0)
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
                weekday = WEEKDAYS[s]
                dtes = [d for d in range(dte_min, dte_max + 1) if (weekday + d) % 7 < 5]
                s0 = float(path[0])
                step = _step(root, s0, band)
                reach = s0 * (band + 0.02)
                atm = round(s0 / step) * step
                ks = atm + step * np.arange(-math.ceil(reach / step), math.ceil(reach / step) + 1)
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
        return ("a numpy array was used as one boolean: chain fields are arrays, one entry per contract; use `.any()`, "
                "`.all()`, or index a single contract first.")
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
        if "ran past" in message or "MemoryError" in message:
            return _answer("inconclusive", f"the load says nothing on this box: {message[:300]}")
        line, source = _located(message, code)
        return _answer("refused", "the program does not load (the Gym's worker would refuse it the same way)", stage="load",
                       error=message[:500], line=line, source=source, calls=0,
                       hint=advice(message, params=params, source=source))
    except DeciderError as exc:
        return _answer("inconclusive", f"the sandbox failed: {str(exc)[:300]}")
    try:
        return _decide_loop(code, params or {}, decider, key, info["needs"], universe, began, deadline, clock)
    except DeciderError as exc:
        return _answer("inconclusive", f"the sandbox failed: {str(exc)[:300]}")
    finally:
        try:
            decider.drop(key)
        except Exception:  # noqa: BLE001 - dropping a runner never fails the preflight
            pass


def _decide_loop(code: str, params: Mapping[str, Any], decider: Any, key: str, needs: Mapping[str, Any],
                 universe: Sequence[str] | None, began: float, deadline: float, clock: Callable[[], float]) -> dict:
    from ..gym import venue as V
    from ..gym.events import EVENT_NAMES

    wanted = [str(r).upper() for r in needs["roots"]]
    roots = [r for r in wanted if not universe or r in {str(u).upper() for u in universe}]
    schedule = decision_minutes(needs)
    if not roots or not schedule:
        return _answer("passed", "the program has no decision in the run's roots and hours", calls=0)
    market = Market(roots, needs)
    rules = {r: V.rules_for(r).as_dict() for r in roots}
    quiet = {name: False for name in EVENT_NAMES}
    restarts = getattr(decider, "restarts", 0)
    calls = errors = timeouts = 0
    streak: list[tuple[int, int]] = []    # (session, call) of the current run of erring calls
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
                   "weekday": WEEKDAYS[s], "positions": [], "orders": [], "cash": CAPITAL, "equity": CAPITAL,
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
            erred = int(stats.get("errors") or 0) > errors
            errors = int(stats.get("errors") or 0)
            seen = [str(m) for m in stats.get("messages") or []]
            if answer.get("intents"):
                return _answer("passed", f"the program returned an intent at call {calls}; a flat account no longer "
                                         "mirrors the Gym's from there", calls=calls, errors=errors)
            if not erred:
                streak, first_message = [], ""
                messages = seen
                continue
            new = [m for m in seen if m not in messages]
            if not streak:
                first_message = new[0] if new else (seen[-1] if seen else "")
            messages = seen
            streak.append((s, calls))
            if len(streak) >= STREAK and len({x[0] for x in streak}) >= 2:
                line, source = _located(first_message, code)
                return _answer("refused", f"decide raised on every call from call {streak[0][1]} ({len(streak)} calls over "
                                          f"{len({x[0] for x in streak})} synthetic sessions, before any intent)",
                               stage="decide", error=first_message[:500], line=line, source=source, calls=calls,
                               errors=errors, messages=[m[:200] for m in messages[:4]],
                               hint=advice(first_message, roots=roots, params=params, source=source))
    return _answer("passed", "no persistent error on the synthetic sessions", calls=calls, errors=errors)


# ------------------------------------------------------------------------------------------------ the House's instance
class Preflight:
    """The researcher's preflight: one sandboxed decider child for the process, one preflight at a time (the House has
    one core; a Gym run can wait a second, the live minute cannot). `decider` for tests (an InlineDecider)."""

    def __init__(self, decider: Any = None, *, deadline: float = DEADLINE_SECONDS, wait: float = 60.0):
        self._decider = decider
        self.deadline, self.wait = float(deadline), float(wait)
        self._lock = threading.Lock()

    def decider(self) -> Any:
        if self._decider is None:
            from ..live.decider import Decider

            # max_errors: every call's own outcome is read (the preflight counts its streak itself, at the Gym's 25).
            self._decider = Decider(timeout=1.0, max_errors=10 ** 9)
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


__all__ = ["VERSION", "STREAK", "SESSIONS", "Market", "Preflight", "advice", "decision_minutes", "run"]
