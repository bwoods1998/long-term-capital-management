"""The panel engine (release E4, package D; league/xs/engine.py, league/xs/results.py): the KEEP rule, the standing
target, E1's fills and sizing, the House exits, the holdings log and the result record.

SYNTHETIC DATA ONLY: seeded pseudo-random prices on a weekday calendar; no market row, no real ticker or date.

PACKAGE C AT ITS INTERFACE. The engine calls package C's functions (`league.xs.ctx.inputs_from_panel`, `derive`,
`ineligible`, `build`, `ctx_bytes`; `league.xs.config.decision_due`; a `league.xs.program.XsProgram`'s runner), which
were importable stubs when this package was built. These tests replace them, at their published signatures, by the
plain DOUBLES below, written from the same contract (league/xs/E4_INTERFACES.md and the stubs' docstrings): a small
panel then needs no 253 sessions of look-back, and what is held here is the engine's own logic, whatever package C's
arithmetic. The doubles are used by `test_xs_runner.py` too. The engine over package C's REAL functions is held by
`test_xs_runner.WithTheRealCore` and `test_xs_i6.py`, which run once package C is built.

This module is imported by the other package D tests for its fixtures: its top level defines no test but its own."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import unittest
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Callable, Mapping, Sequence
from unittest import mock

import numpy as np

from league.equity import config as e1
from league.equity import engine as e1_engine
from league.equity.ctx import _encode
from league.equity.store import from_ordinal, ordinal
from league.gym.safety import CodeRefused
from league.xs import config, ctx, engine, placebo, program, results, store
from league.xs import style as xs_style

REF = len(config.REF)
HS = config.HS_FLOOR_BP / 10_000.0
FIXTURES = __import__("pathlib").Path(__file__).resolve().parent / "fixtures"


# ====================================================================================== package C's doubles
class Core:
    """Package C at its interface: plain doubles of what the engine, the runner and the child call. The eligible set
    and the cells follow the pre-registration's 3.1-3.3 on SHORT windows (`WINDOW` returns, not 252), with the sector
    GIVEN by the column (a test's panel says which), so a 60-session panel has cells."""

    WINDOW = 20
    MIN_VALID = 15
    MOM_SKIP, MOM_BACK = 2, 20
    SECTORS = 3

    # ------------------------------------------------------------------ config
    @staticmethod
    def rebalance_session(day: dt.date, rule: str, weekday: int = 0) -> bool:
        """D9 on the tests' calendar (every weekday a session)."""
        if rule == "weekly":
            return day.weekday() == int(weekday)
        if rule == "monthly":
            first = dt.date(day.year, day.month, 1)
            while first.weekday() > 4:
                first += dt.timedelta(days=1)
            return day == first
        raise ValueError(f"no rebalance rule {rule!r}")

    @classmethod
    def decision_due(cls, t: dt.date, rule: str, weekday: int = 0) -> bool:
        return cls.rebalance_session(next_weekday(t), rule, weekday)

    # ------------------------------------------------------------------ program
    @staticmethod
    def parse_needs(raw: Any) -> program.Needs:
        if not isinstance(raw, Mapping) or set(map(str, raw)) - set(program.NEEDS_KEYS):
            raise program.NeedsRefused("NEEDS is a dict of the six keys")
        needs = program.Needs(str(raw.get("panel", "sp500")), int(raw.get("history", 20)),
                              int(raw.get("max_names", program.DEFAULT_MAX_NAMES)),
                              str(raw.get("rebalance", "weekly")), int(raw.get("weekday", 0)),
                              int(raw.get("max_hold_sessions", program.DEFAULT_MAX_HOLD)))
        if needs.rebalance not in config.REBALANCE or needs.panel != "sp500":
            raise program.NeedsRefused("a panel program rebalances weekly or monthly on sp500")
        return needs

    @staticmethod
    def normalize_target(raw: Any, ids: Sequence[int], max_names: int,
                         on_error: Callable[[str], None] | None = None) -> dict[str, Any]:
        def bad(text: str) -> dict[str, Any]:
            if on_error:
                on_error(text)
            return {"hold": True}

        if raw is None:
            return {"hold": True}
        if not isinstance(raw, Mapping):
            return bad("decide returns a dict")
        if raw.get("hold"):
            return {"hold": True}
        target, at = raw.get("target"), raw.get("at", "open")
        if not isinstance(target, Mapping) or at not in program.AT:
            return bad("a target is {id: w} at open or close")
        known = {int(i) for i in ids}
        out: dict[int, float] = {}
        for key, weight in target.items():
            try:
                slot, weight = int(key), float(weight)
            except (TypeError, ValueError):
                return bad("malformed target")
            if slot not in known or not math.isfinite(weight) or weight < 0 or weight > config.MAX_WEIGHT + 1e-9:
                return bad("malformed target")
            if weight > 0:
                out[slot] = weight
        if math.fsum(out.values()) > 1 + 1e-9 or (out and not config.MIN_NAMES <= len(out) <= int(max_names)):
            return bad("malformed target")
        return {"target": out, "at": at}

    @classmethod
    def load_program(cls, code: str, *, name: str = "program", params: Mapping[str, Any] | None = None) -> "Program":
        """A code string as a `Program` (no safety check: the tests' own code)."""
        if "refuse me" in code:
            raise CodeRefused("the program does not load")
        space: dict[str, Any] = {}
        exec(compile(code, "<panel program>", "exec"), space)  # noqa: S102 - a test's own program
        merged = {**dict(space.get("PARAMS") or {}), **dict(params or {})}
        space["PARAMS"] = merged
        return Program(space["decide"], cls.parse_needs(space.get("NEEDS") or {}), merged, name=name, code=code,
                       space=space)

    # ------------------------------------------------------------------ ctx
    @staticmethod
    def inputs_from_panel(bars: Any, t: int, *, needs: Any, positions: Sequence[dict] = (),
                          closed: Sequence[dict] = (), rejects: Sequence[str] = (), cash: float, equity: float,
                          budget: float, params: Mapping[str, Any]) -> ctx.Inputs:
        t = int(t)
        if not 0 <= t < bars.n:
            raise ValueError(f"session index {t} is outside the slice")
        lo = max(0, t - (config.DERIVE_SESSIONS - 1))
        return ctx.Inputs(
            days=np.array(bars.days[lo:t + 1], dtype=np.int32), raw=np.array(bars.raw[lo:t + 1], dtype=np.float64),
            adj=np.array(bars.adj[lo:t + 1], dtype=np.float64), elig0=np.array(bars.elig0[t], dtype=bool),
            ref=int(bars.ref), ids=np.array(bars.ids, dtype=np.int32), dither_key=bars.dither_key,
            sector_perm=np.array(bars.sector_perm, dtype=np.int8), history=int(needs.history),
            max_names=int(needs.max_names), trading_days=np.array(bars.days[lo:t + 2], dtype=np.int32),
            early=np.zeros(len(bars.days[lo:t + 2]), dtype=bool), positions=tuple(dict(p) for p in positions),
            closed=tuple(dict(c) for c in closed), rejects=tuple(str(r) for r in rejects), cash=float(cash),
            equity=float(equity), budget=float(budget), params=json.loads(json.dumps(dict(params))))

    @classmethod
    def derive(cls, inputs: ctx.Inputs, *, rung: str | None = None) -> ctx.Derived:
        rung = config.RUNG if rung is None else rung
        raw, adj = np.asarray(inputs.raw), np.asarray(inputs.adj)
        n, m = raw.shape[:2]
        ok = np.isfinite(raw[:, :, 3]) & (raw[:, :, 3] > 0) & np.isfinite(raw[:, :, 4]) & (raw[:, :, 4] > 0) & \
            np.isfinite(adj[:, :, 3]) & (adj[:, :, 3] > 0)
        close = np.where(ok, adj[:, :, 3], np.nan)
        beta = np.full(m, np.nan)
        mom = np.full(m, np.nan)
        sector = np.full(m, -1, dtype=np.int8)
        if n > cls.WINDOW:
            window = close[-(cls.WINDOW + 1):]
            with np.errstate(invalid="ignore", divide="ignore"):
                moves = window[1:] / window[:-1] - 1.0
                mom = close[-1 - cls.MOM_SKIP] / close[-1 - cls.MOM_BACK] - 1.0
            market = moves[:, config.MARKET_COLUMN] if inputs.ref else np.nanmean(moves, axis=1)
            for col in range(inputs.ref, m):
                valid = np.isfinite(moves[:, col]) & np.isfinite(market)
                if int(valid.sum()) < cls.MIN_VALID:
                    continue
                a, b = moves[valid, col], market[valid]
                spread = float(((b - b.mean()) ** 2).sum())
                if spread > 0:
                    beta[col] = float(((a - a.mean()) * (b - b.mean())).sum()) / spread
                    sector[col] = (col - inputs.ref) % cls.SECTORS
        elig = np.asarray(inputs.elig0, dtype=bool).copy()
        elig &= ok[-1] & (ok[-2] if n > 1 else False) & np.isfinite(beta) & np.isfinite(mom) & (sector >= 0)
        elig[:inputs.ref] = False
        bg, mg, cell = cells(elig, sector, beta, mom, rung)
        return ctx.Derived(elig=elig, beta=beta, mom=mom, sector=np.where(elig, sector, -1).astype(np.int8), bg=bg,
                           mg=mg, cell=cell, rung=rung)

    @staticmethod
    def ineligible(inputs: ctx.Inputs, derived: ctx.Derived) -> list[int]:
        return [int(row["lid"]) for row in inputs.positions if not bool(derived.elig[int(row["col"])])]

    @classmethod
    def build(cls, inputs: ctx.Inputs) -> ctx.XsCtx:
        derived = cls.derive(inputs)
        cols = np.flatnonzero(derived.elig)
        ids = np.asarray(inputs.ids, dtype=np.int32)[cols - inputs.ref]
        h = min(int(inputs.history), np.asarray(inputs.adj).shape[0] - 1)
        close = np.asarray(inputs.adj)[-(h + 1):, :, 3]
        with np.errstate(invalid="ignore", divide="ignore"):
            moves = np.vstack([np.full((1, close.shape[1]), np.nan), close[1:] / close[:-1] - 1.0])
        day = from_ordinal(int(inputs.days[-1]))
        slot_of = {inputs.ref + i: int(s) for i, s in enumerate(np.asarray(inputs.ids))}
        equity = float(inputs.equity) or 1.0
        return ctx.XsCtx(
            n=int(len(cols)), ids=ids, ret=np.round(moves[:, cols].T, config.CTX_PLACES),
            sector=np.asarray(inputs.sector_perm)[derived.sector[cols]].astype(np.int8),
            beta=np.round(derived.beta[cols], config.BETA_PLACES),
            mkt=ctx.Fields(ret=np.round(moves[:, config.MARKET_COLUMN], config.CTX_PLACES)) if inputs.ref else None,
            positions=[{"id": int(p["lid"]), "slot": slot_of[int(p["col"])],
                        "weight": round(float(p["value"]) / equity, 4),
                        "ret": round(float(p["value"]) / float(p["entry_value"]) - 1.0, 4),
                        "held_sessions": int(p["held_sessions"]), "at": str(p["at"]), "tag": str(p.get("tag") or "")}
                       for p in inputs.positions],
            closed=[{"id": int(c["lid"]), "slot": slot_of[int(c["col"])], "net_ret": float(c["net_ret"]),
                     "held_sessions": int(c["held_sessions"]), "reason": str(c["reason"]),
                     "tag": str(c.get("tag") or "")} for c in inputs.closed],
            rejects=[str(r) for r in inputs.rejects], cash=float(inputs.cash), equity=float(inputs.equity),
            budget=float(inputs.budget), weekday=int(day.weekday()), session_of_month=int(day.day),
            sessions_left_in_month=0, last_session_of_week=day.weekday() == 4, max_names=int(inputs.max_names),
            params=json.loads(json.dumps(dict(inputs.params))))

    @staticmethod
    def ctx_bytes(value: ctx.XsCtx) -> bytes:
        out: list[bytes] = [ctx.CTX_PREFIX]
        for name in ctx.XsCtx.__slots__:
            _encode(name, out)
            item = getattr(value, name)
            if isinstance(item, ctx.Fields):
                item = {field: getattr(item, field) for field in ctx.Fields.__slots__}
            _encode(item, out)
        return b"".join(out)

    # ------------------------------------------------------------------ installing them
    @classmethod
    def install(cls, case: unittest.TestCase) -> None:
        """Replace package C's functions by these doubles for one test (the engine reads them through its modules)."""
        for module, names in ((ctx, ("inputs_from_panel", "derive", "ineligible", "build", "ctx_bytes")),
                              (config, ("decision_due", "rebalance_session")),
                              (program, ("parse_needs", "normalize_target", "load_program"))):
            for name in names:
                patcher = mock.patch.object(module, name, getattr(cls, name))
                patcher.start()
                case.addCleanup(patcher.stop)


def next_weekday(day: dt.date) -> dt.date:
    day += dt.timedelta(days=1)
    while day.weekday() > 4:
        day += dt.timedelta(days=1)
    return day


def cells(elig: np.ndarray, sector: np.ndarray, beta: np.ndarray, mom: np.ndarray,
          rung: str = "R0") -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The pre-registration's 3.3 by column: (beta group, momentum group, cell id), -1 outside U."""
    m = len(elig)
    bg = np.full(m, -1, dtype=np.int8)
    mg = np.full(m, -1, dtype=np.int8)
    cell = np.full(m, -1, dtype=np.int32)
    for g in sorted({int(s) for s in sector[elig]}):
        names = [int(c) for c in np.flatnonzero(elig & (sector == g))]
        count = len(names)
        if count < config.MIN_CELL:
            for c in names:
                bg[c], mg[c], cell[c] = 0, 0, config.SMALL_CELL
            continue
        nb, nm = next(groups for least, groups in config.RUNGS[rung] if count >= least)
        by_beta = sorted(names, key=lambda c: (beta[c], c))
        for group in range(nb):
            inside = [c for q, c in enumerate(by_beta) if (q * nb) // count == group]
            for q, c in enumerate(sorted(inside, key=lambda c: (mom[c], c))):
                bg[c], mg[c] = group, (q * nm) // len(inside)
                cell[c] = config.CELL_SECTOR * g + config.CELL_BETA * group + int(mg[c])
    return bg, mg, cell


# ============================================================================================ the tests' programs
class Runner:
    """A double of `program.XsRunner`: one run's instance (its `state` is its memory), with the Gym runner's counts."""

    def __init__(self, prog: "Program", *, timeout: float = 1.0, max_errors: int = 25,
                 budget_seconds: float | None = None):
        self.program, self.max_errors = prog, int(max_errors)
        self.state: dict[str, Any] = {}
        self.calls = self.errors = 0
        self.messages: list[str] = []
        self.disqualified: str | None = None
        self.last_failed = False
        self.space = dict(prog.space) if prog.space is not None else None
        if self.space is not None and "STATE" in self.space:
            self.space["STATE"] = json.loads(json.dumps(self.space["STATE"]))

    def _error(self, text: str) -> None:
        self.errors += 1
        self.messages.append(text)
        if self.errors >= self.max_errors:
            self.disqualified = f"{self.errors} errors"

    def decide(self, value: Any) -> dict[str, Any]:
        self.last_failed = True
        if self.disqualified:
            return {"hold": True}
        self.calls += 1
        try:
            if self.space is not None:
                namespace = self.space
                raw = eval("decide(__ctx)", namespace, {"__ctx": value})  # noqa: S307 - a test's own program
            else:
                raw = self.program.fn(value, self.state)
        except Exception as exc:  # noqa: BLE001 - a program's error is counted, as the Gym runner counts it
            self._error(f"{type(exc).__name__}: {exc}")
            return {"hold": True}
        self.last_failed = False
        return program.normalize_target(raw, value.ids, value.max_names, self._error)

    def stats(self) -> dict[str, Any]:
        return {"calls": self.calls, "errors": self.errors, "timeouts": 0, "seconds": 0.0,
                "messages": list(self.messages), "disqualified": self.disqualified}


class Program:
    """A double of `program.XsProgram`: `fn(ctx, state)` is its decide (or a code string's, `space`)."""

    def __init__(self, fn: Callable[..., Any], needs: Any = None, params: Mapping[str, Any] | None = None, *,
                 name: str = "program", code: str | None = None, space: dict[str, Any] | None = None, **needs_kw: Any):
        self.fn, self.name, self.space = fn, name, space
        self.needs = needs or program.Needs("sp500", needs_kw.get("history", 20), needs_kw.get("max_names", 10),
                                            needs_kw.get("rebalance", "weekly"), needs_kw.get("weekday", 0),
                                            needs_kw.get("max_hold_sessions", 60))
        self.params = dict(params or {})
        self.code = code if code is not None else getattr(fn, "__name__", "fn")
        self.sha = hashlib.sha256(self.code.encode()).hexdigest()
        self.run_sha = hashlib.sha256((self.sha + json.dumps(self.params, sort_keys=True)).encode()).hexdigest()

    def start(self, *, timeout: float = 1.0, max_errors: int = 25, budget_seconds: float | None = None) -> Runner:
        return Runner(self, timeout=timeout, max_errors=max_errors, budget_seconds=budget_seconds)


def first_k(k: int = 5, weight: float = 0.2, at: str = "open") -> Callable[..., Any]:
    """decide: hold the `k` lowest slot ids of the day at `weight` each."""
    def decide(value: Any, state: dict) -> Any:
        return {"target": {int(slot): weight for slot in sorted(value.ids)[:k]}, "at": at}
    return decide


def keyed(k: int = 5, weight: float = 0.2, at: str = "open", salt: int = 0) -> Callable[..., Any]:
    """decide: a no-skill picker: the `k` slots with the smallest seeded key of (slot, call number)."""
    def decide(value: Any, state: dict) -> Any:
        state["n"] = state.get("n", 0) + 1
        def key(slot: int) -> bytes:
            return hashlib.sha256(f"{salt}|{state['n']}|{slot}".encode()).digest()
        return {"target": {int(slot): weight for slot in sorted(value.ids, key=key)[:k]}, "at": at}
    return decide


# ================================================================================================= synthetic panels
def weekdays(start: dt.date, count: int) -> list[dt.date]:
    out, day = [], start
    while len(out) < count:
        if day.weekday() < 5:
            out.append(day)
        day += dt.timedelta(days=1)
    return out


def panel(*, sessions: int = 70, names: int = 30, first: int = 25, seed: int = 3, window: str = "train",
          start: dt.date = dt.date(2031, 1, 6), drift: float = 0.0) -> store.PanelBars:
    """A synthetic `PanelBars`: the 12 REF columns then `names` member columns in ascending id, seeded lognormal
    prices off the cent grid, every bar valid, raw = adj (no split, no dividend). 2031 is no year of any store."""
    rng = np.random.default_rng([20261011, 4, int(seed)])
    m = REF + names
    market = rng.normal(0.0003, 0.008, sessions)
    moves = market[:, None] * rng.normal(1.0, 0.3, m)[None, :] + rng.normal(drift, 0.012, (sessions, m))
    moves[:, config.MARKET_COLUMN] = market
    close = 40.0 * np.exp(np.cumsum(np.log1p(moves), axis=0)) * rng.uniform(0.5, 4.0, m)[None, :]
    before = np.vstack([close[:1] / (1.0 + moves[:1]), close[:-1]])
    open_ = before * (1.0 + 0.4 * moves + rng.normal(0.0, 0.002, (sessions, m)))
    raw = np.empty((sessions, m, 5))
    raw[:, :, 0], raw[:, :, 3] = open_, close
    raw[:, :, 1], raw[:, :, 2] = np.maximum(open_, close) * 1.002, np.minimum(open_, close) * 0.998
    raw[:, :, 4] = rng.integers(100_000, 900_000, (sessions, m)).astype(float)
    ids = np.sort(rng.choice(2 ** 31 - 1, size=names, replace=False)).astype(np.int32)
    elig0 = np.ones((sessions, m), dtype=bool)
    elig0[:, :REF] = False
    return store.PanelBars(
        days=np.array([ordinal(d) for d in weekdays(start, sessions)], dtype=np.int32),
        early=np.zeros(sessions, dtype=bool), first=int(first), raw=raw, adj=raw[:, :, :4].copy(), elig0=elig0,
        ref=REF, ids=ids, exit=np.zeros(m, dtype=np.int8), hs=np.full((m, 2), HS),
        sector_perm=np.arange(11, dtype=np.int8)[::-1].copy(), dither_key=b"synthetic", window=window,
        data_version="synthetic-1")


def changed(bars: store.PanelBars, **fields: Any) -> store.PanelBars:
    """`bars` with some fields replaced (arrays copied first by the caller)."""
    values = {name: getattr(bars, name) for name in bars.__dataclass_fields__}
    values.update(fields)
    return store.PanelBars(**values)


def no_bar(bars: store.PanelBars, col: int, sessions: Sequence[int]) -> store.PanelBars:
    raw, adj = bars.raw.copy(), bars.adj.copy()
    for t in sessions:
        raw[t, col], adj[t, col] = np.nan, np.nan
    return changed(bars, raw=raw, adj=adj)


def col_of(bars: store.PanelBars, slot: int) -> int:
    return bars.ref + int(np.flatnonzero(np.asarray(bars.ids) == slot)[0])


def day_index(bars: store.PanelBars, iso: str) -> int:
    return [from_ordinal(int(d)).isoformat() for d in bars.days].index(iso)


class EngineCase(unittest.TestCase):
    def setUp(self):
        Core.install(self)

    def run_log(self, prog: Program, bars: store.PanelBars, **kw: Any) -> tuple[dict[str, Any], engine.Log]:
        """One run and its holdings log (which a run never returns: the test reads it off the residual's call)."""
        seen: list[engine.Log] = []
        real = placebo.residual

        def spy(b: Any, log: Any, **k: Any) -> Any:
            seen.append(log)
            return real(b, log, **k)

        with mock.patch.object(placebo, "residual", spy):
            result = engine.run(prog, bars, **kw)
        return result, seen[0]


# =================================================================================================== the KEEP rule
class TheKeepRule(unittest.TestCase):
    LOTS = [{"lid": 1, "id": 11, "pending": False}, {"lid": 2, "id": 22, "pending": False},
            {"lid": 3, "id": 33, "pending": False}]

    def test_sells_the_absent_buys_the_new_keeps_the_held(self):
        orders, rejects = engine.plan_orders({22: 0.1, 44: 0.15, 55: 0.2, 66: 0.15}, "open", self.LOTS, 1000)
        self.assertEqual(orders, [{"sell": 1, "at": "open"}, {"sell": 3, "at": "open"},
                                  {"buy_id": 55, "usd": 200.0, "at": "open"},
                                  {"buy_id": 44, "usd": 150.0, "at": "open"},
                                  {"buy_id": 66, "usd": 150.0, "at": "open"}])
        self.assertEqual(rejects, [])

    def test_a_held_name_is_kept_whatever_its_weight_no_resize(self):
        for weight in (0.01, 0.2):
            orders, _ = engine.plan_orders({11: weight, 22: weight, 33: weight}, "close", self.LOTS, 1000)
            self.assertEqual(orders, [])

    def test_a_buy_is_one_lot_of_w_times_the_budget_floored_to_the_cent(self):
        orders, _ = engine.plan_orders({7: 0.123456}, "close", [], Decimal("557.25"))
        self.assertEqual(orders, [{"buy_id": 7, "usd": 68.79, "at": "close"}])     # 68.7958... floored

    def test_buys_by_descending_weight_then_ascending_id_sells_in_lot_order(self):
        lots = [{"lid": 9, "id": 5}, {"lid": 4, "id": 6}]
        orders, _ = engine.plan_orders({3: 0.1, 1: 0.1, 2: 0.2}, "open", lots, 1000)
        self.assertEqual([o.get("sell", o.get("buy_id")) for o in orders], [4, 9, 2, 1, 3])

    def test_under_the_minimum_order_is_rejected_and_the_rest_goes(self):
        orders, rejects = engine.plan_orders({1: 0.2, 2: 0.009}, "open", [], 1000)
        self.assertEqual(orders, [{"buy_id": 1, "usd": 200.0, "at": "open"}])
        self.assertEqual(len(rejects), 1)
        self.assertIn("buy 2: under the minimum order", rejects[0])
        self.assertFalse(engine.refused_whole(rejects))

    def test_the_order_cap_refuses_the_target_whole(self):
        twelve = {i: 0.05 for i in range(1, 13)}
        orders, rejects = engine.plan_orders(twelve, "open", [], 1000)
        self.assertEqual((len(orders), rejects), (12, []))
        thirteen = {i: 0.05 for i in range(1, 14)}
        orders, rejects = engine.plan_orders(thirteen, "open", [], 1000)
        self.assertEqual(orders, [])
        self.assertTrue(engine.refused_whole(rejects))
        self.assertIn("order cap", rejects[0])
        held = [{"lid": i, "id": 100 + i} for i in range(1, 14)]
        orders, rejects = engine.plan_orders({1: 0.2}, "open", held, 1000)         # 13 sells
        self.assertEqual(orders, [])
        self.assertTrue(engine.refused_whole(rejects))
        orders, rejects = engine.plan_orders({1: 0.2}, "open", held[:12], 1000)    # 12 sells and a buy
        self.assertEqual(len(orders), 13)

    def test_a_target_through_json_is_the_same_target_and_zero_is_absence(self):
        direct = engine.plan_orders({22: 0.1, 44: 0.2, 11: 0.0}, "open", self.LOTS, 1000)
        through = engine.plan_orders(json.loads(json.dumps({22: 0.1, 44: 0.2, 11: 0.0})), "open", self.LOTS, 1000)
        self.assertEqual(direct, through)
        self.assertIn({"sell": 1, "at": "open"}, direct[0])

    def test_the_standing_target_plans_buys_only(self):
        lots = [{"lid": 1, "id": 11}, {"lid": None, "id": 44, "pending": True}]
        target = {11: 0.2, 22: 0.2, 33: 0.2, 44: 0.2, 55: 0.2}
        orders, rejects = engine.plan_orders(target, "close", lots, 1000, standing=True, exited=[33],
                                             eligible=[11, 22, 33, 44])
        # 11 is held, 44 has a buy working, 33 was a House exit, 55 is not eligible today
        self.assertEqual(orders, [{"buy_id": 22, "usd": 200.0, "at": "close"}])
        self.assertEqual(rejects, [])
        # never a sell, even of a lot the standing target does not name
        orders, _ = engine.plan_orders({22: 0.2}, "open", [{"lid": 1, "id": 11}], 1000, standing=True)
        self.assertEqual(orders, [{"buy_id": 22, "usd": 200.0, "at": "open"}])

    def test_a_pending_buy_is_not_sold_and_not_bought_again(self):
        orders, _ = engine.plan_orders({1: 0.2}, "open", [{"lid": None, "id": 2, "pending": True},
                                                          {"lid": None, "id": 1, "pending": True}], 1000)
        self.assertEqual(orders, [])

    def test_it_is_pure_and_refuses_what_it_cannot_read(self):
        target, lots = {5: 0.2}, [{"lid": 1, "id": 4}]
        before = (dict(target), [dict(row) for row in lots])
        engine.plan_orders(target, "open", lots, 1000)
        self.assertEqual((target, lots), before)
        for bad in ({"target": {5: float("nan")}}, {"at": "noon"}, {"budget": float("inf")}, {"budget": -1}):
            args = {"target": {5: 0.2}, "at": "open", "budget": 1000, **bad}
            with self.assertRaises(ValueError):
                engine.plan_orders(args["target"], args["at"], [], args["budget"])


# ============================================================================================ the vendor's cents
class TheVendorsCents(unittest.TestCase):
    def test_the_steps_tolerance_is_e1s_or_the_rounding_of_its_two_closes(self):
        self.assertEqual(engine.ratio_tolerance(1e6, 1e6), e1_engine.RATIO_TOLERANCE)
        self.assertAlmostEqual(engine.ratio_tolerance(10.0, 10.0), config.rounding_bound(10.0, 10.0), places=15)
        self.assertGreater(engine.ratio_tolerance(10.0, 10.0), e1_engine.RATIO_TOLERANCE)
        self.assertEqual(engine.ratio_tolerance(float("nan"), 10.0), e1_engine.RATIO_TOLERANCE)

    def test_a_split_whose_step_the_rounding_pushed_past_its_factor_is_still_that_split(self):
        """E1's rehearsal on real bars: a 20-for-1 read as 39-for-2 with a dividend under the fixed bound."""
        tolerance = 4e-4
        for factor, numerator, denominator in ((20.0, 20, 1), (2.0, 2, 1), (1.5, 3, 2), (0.1, 1, 10)):
            for nudge in (-0.9 * tolerance, 0.0, 0.9 * tolerance):
                found = engine._split_own((1.0 + nudge) / factor, tolerance)
                self.assertEqual((found.numerator, found.denominator), (numerator, denominator), (factor, nudge))
        self.assertIsNone(engine._split_own(0.99, tolerance), "a small dividend is no split")
        self.assertIsNone(engine._split_own(float("nan"), tolerance))

    def test_the_own_copy_is_e1s_rule_and_e1s_is_called_once_it_takes_the_tolerance(self):
        for step in (0.05, 0.5, 2 / 3, 0.25, 4.0, 10.0):
            self.assertEqual(engine._split_own(step, e1_engine.RATIO_TOLERANCE), e1_engine.split_factor(step), step)
        calls = []
        with mock.patch.object(engine, "_E1_SPLIT_TOLERANCE", True), \
                mock.patch.object(e1_engine, "split_factor", lambda step, tolerance: calls.append((step, tolerance))):
            engine.split_of(0.5, 3e-4)
        self.assertEqual(calls, [(0.5, 3e-4)])
        with mock.patch.object(engine, "_E1_SPLIT_TOLERANCE", False):
            self.assertEqual(engine.split_of(0.5, 3e-4), engine._split_own(0.5, 3e-4))


# ==================================================================================================== the session
class TheSession(EngineCase):
    def test_a_weekly_program_trades_baskets_and_the_cash_book_holds(self):
        bars = panel()
        result, log = self.run_log(Program(keyed(5)), bars)
        self.assertEqual(result["status"], "ok")
        summary = result["summary"]
        self.assertEqual(summary["days"], bars.n - bars.first)
        self.assertGreater(summary["lots"], 10)
        self.assertGreater(summary["closed"], 5)
        self.assertEqual(summary["calls"], sum(1 for p in result["picks"] if p["called"]))
        # a lot is a fifth of E0 at most, never sold in the session it was bought, and filled at the official price
        raw = bars.raw
        for row, lot in zip(result["lots"], log.lots):
            self.assertLessEqual(row["weight"], 0.2 + 1e-12)
            self.assertGreater(row["weight"], 0.01)
            self.assertEqual(lot["entry"], lot["decided"] + 1)
            if lot["exit"] is not None:
                self.assertGreater(lot["exit"], lot["entry"])
        self.assertTrue(all(row["weight"] > 0.1999 for row in result["lots"][:5]), "a lot of weight w is w x E0")
        self.assertEqual([row["lid"] for row in result["lots"]], list(range(1, len(log.lots) + 1)))
        # the daily cash book: equity moves by what the lots made, and never a negative cash (asserted in the engine)
        equity = results.column(result, "equity")
        self.assertEqual(len(equity), bars.n - bars.first)
        self.assertAlmostEqual(equity[-1] - 1000.0, summary["pnl"], places=2)
        self.assertTrue(all(isinstance(v, float) and math.isfinite(v) for v in equity))
        self.assertIsNotNone(raw)

    def test_the_fills_are_e1s_and_the_fee_is_e1s(self):
        bars = panel()
        prog = Program(keyed(5, at="open"))
        result, log = self.run_log(prog, bars, cfg=engine.EngineConfig(k=1.5))
        lot = next(row for row in log.lots[:5] if row["exit"] is not None)      # a lot of the first, uncut, basket
        row = next(r for r in result["lots"] if r["lid"] == lot["lid"])
        buy = Decimal(f"{e1_engine.fill_price(bars.raw[lot['entry'], lot['col'], 0], 'buy', HS, 1.5):.6f}")
        qty = (Decimal("200.00") / buy).quantize(Decimal("0.000001"), rounding="ROUND_DOWN")
        self.assertAlmostEqual(row["weight"], float(qty * buy / 1000), places=8)
        column = 0 if lot["exit_at"] == "open" else 3
        sell = Decimal(f"{e1_engine.fill_price(bars.raw[lot['exit'], lot['col'], column], 'sell', HS, 1.5):.6f}")
        fees = e1.sell_fees(qty * sell, qty)
        self.assertEqual(row["fees"], float(fees))
        self.assertAlmostEqual(row["net"], float((qty * sell - qty * buy - fees).quantize(Decimal("0.01"))), places=2)

    def test_the_sessions_order_open_exits_open_entries_close_exits_close_entries(self):
        """A full rotation at the close: the five sales fund the five buys, in one session, and never the reverse."""
        bars = panel()

        def decide(value: Any, state: dict) -> Any:
            state["n"] = state.get("n", 0) + 1
            ids = sorted(value.ids)
            pick = ids[:5] if state["n"] % 2 else ids[5:10]
            return {"target": {int(s): 0.2 for s in pick}, "at": "close"}

        result, log = self.run_log(Program(decide), bars)
        rotations = [p for p in result["picks"] if p["called"] and len(p["sells"]) == 5 and len(p["buys"]) == 5]
        self.assertGreaterEqual(len(rotations), 3)
        for pick in rotations:
            self.assertEqual(pick["dropped"], [], "with the sales made first, no buy is refused for cash")
            j = day_index(bars, pick["exec"])
            sold = [lot for lot in log.lots if lot["exit"] == j]
            bought = [lot for lot in log.lots if lot["entry"] == j]
            self.assertEqual((len(sold), len(bought)), (5, 5))
            self.assertTrue(all(lot["exit_at"] == "close" and lot["reason"] == "program" for lot in sold))
            self.assertTrue(all(lot["entry_at"] == "close" for lot in bought))

    def test_decisions_run_from_the_close_before_the_first_session_to_the_one_before_the_last(self):
        bars = panel()
        result, log = self.run_log(Program(first_k(5)), bars)
        self.assertEqual([row["t"] for row in log.decisions], list(range(bars.first - 1, bars.n - 1)))
        days = [from_ordinal(int(d)) for d in bars.days]
        for row in log.decisions:
            self.assertEqual(row["called"], days[row["t"] + 1].weekday() == 0, "called iff the next session is Monday")
        self.assertEqual(min(lot["entry"] for lot in log.lots), min(
            t + 1 for t in range(bars.first - 1, bars.n - 1) if days[t + 1].weekday() == 0))
        self.assertNotIn(bars.n - 1, [lot["decided"] for lot in log.lots])

    def test_a_monthly_program_is_called_once_a_month(self):
        bars = panel(sessions=90)
        result, log = self.run_log(Program(first_k(5), rebalance="monthly"), bars)
        called = [row["t"] for row in log.decisions if row["called"]]
        days = [from_ordinal(int(d)) for d in bars.days]
        self.assertEqual(called, [t for t in range(bars.first - 1, bars.n - 1) if days[t + 1].month != days[t].month])
        self.assertEqual(result["summary"]["calls"], len(called))

    def test_the_same_inputs_give_the_same_result_sha(self):
        bars = panel()
        one = engine.run(Program(keyed(6)), bars)
        two = engine.run(Program(keyed(6)), bars)
        self.assertEqual(one["result_sha"], two["result_sha"])
        self.assertEqual(one["run_id"], two["run_id"])
        other = engine.run(Program(keyed(6)), bars, cfg=engine.EngineConfig(k=1.5))
        self.assertNotEqual(other["run_id"], one["run_id"])
        self.assertNotEqual(other["result_sha"], one["result_sha"])

    def test_no_look_ahead_a_later_price_changes_nothing_decided_before_it(self):
        bars = panel()
        cut = 45
        raw, adj = bars.raw.copy(), bars.adj.copy()
        raw[cut + 2:, REF:, :4] *= 1.37
        adj[cut + 2:, REF:] *= 1.37
        later = changed(bars, raw=raw, adj=adj)
        prog = Program(keyed(5))
        (one, log1), (two, log2) = self.run_log(prog, bars), self.run_log(prog, later)
        iso = [from_ordinal(int(d)).isoformat() for d in bars.days]
        through = iso[cut]
        self.assertEqual([p for p in one["picks"] if p["decided"] <= through],
                         [p for p in two["picks"] if p["decided"] <= through])
        for a, b in zip(log1.decisions, log2.decisions):
            if a["t"] <= cut:
                self.assertTrue(np.array_equal(a["derived"].cell, b["derived"].cell))
        x1, x2 = results.column(one, "x"), results.column(two, "x")
        upto = cut - bars.first + 1
        self.assertEqual(x1[:upto], x2[:upto])
        self.assertNotEqual(x1[upto + 2:], x2[upto + 2:])


# ================================================================================================ the House exits
class TheHouseExits(EngineCase):
    def test_a_lot_at_its_maximum_hold_is_sold_at_the_next_open(self):
        bars = panel()
        result, log = self.run_log(Program(first_k(5), max_hold_sessions=7), bars)
        out = [lot for lot in log.lots if lot["reason"] == "max_hold"]
        self.assertGreaterEqual(len(out), 5)
        for lot in out:
            self.assertEqual((lot["exit"] - lot["entry"], lot["exit_at"]), (7, "open"))
        # the KEEP rule kept them until then, and the next called decision buys the names again as new lots
        again = [lot for lot in log.lots if lot["decided"] > out[0]["exit"] - 1 and lot["col"] == out[0]["col"]]
        self.assertTrue(again, "a name the House sold is bought again at the next called decision")

    def test_a_name_out_of_u_at_any_close_is_sold_at_the_next_open(self):
        bars = panel()
        base, _ = self.run_log(Program(first_k(5)), bars)
        held = base["lots"][0]
        col = col_of(bars, held["id"])
        # the name leaves the index two sessions after its entry, on a close the program is not called at
        entry = day_index(bars, held["entry_day"])
        elig0 = bars.elig0.copy()
        elig0[entry + 2:, col] = False
        result, log = self.run_log(Program(first_k(5)), changed(bars, elig0=elig0))
        lot = next(row for row in log.lots if row["col"] == col)
        self.assertFalse(log.decision(entry + 2)["called"])
        self.assertEqual((lot["exit"], lot["exit_at"], lot["reason"]), (entry + 3, "open", "house"))
        row = next(r for r in result["lots"] if r["lid"] == lot["lid"])
        self.assertEqual((row["reason"], row["tag"]), ("house", "ineligible"))
        # the program reads why at its next call, by slot and lot id, never by a day
        self.assertEqual([lot2 for lot2 in log.lots if lot2["col"] == col and lot2["decided"] > entry + 2], [],
                         "a name out of U is no slot of any later ctx, so it is never bought again")

    def test_the_house_exit_goes_at_the_open_whatever_the_target_planned_at_the_close(self):
        bars = panel()

        def decide(value: Any, state: dict) -> Any:
            state["n"] = state.get("n", 0) + 1
            ids = sorted(value.ids)
            return {"target": {int(s): 0.2 for s in (ids[:5] if state["n"] == 1 else ids[5:10])}, "at": "close"}

        base, base_log = self.run_log(Program(decide), bars)
        first = base_log.lots[0]
        second_call = [row["t"] for row in base_log.decisions if row["called"]][1]
        elig0 = bars.elig0.copy()
        elig0[second_call:, first["col"]] = False       # out of U at the very close the program sells it "at close"
        result, log = self.run_log(Program(decide), changed(bars, elig0=elig0))
        lot = log.lots[0]
        self.assertEqual((lot["exit"], lot["exit_at"], lot["reason"]), (second_call + 1, "open", "house"))
        others = [row for row in log.lots[1:5]]
        self.assertTrue(all((row["exit"], row["exit_at"], row["reason"]) == (second_call + 1, "close", "program")
                            for row in others))

    def test_two_failed_called_decides_exit_every_lot(self):
        bars = panel(sessions=80)

        def decide(value: Any, state: dict) -> Any:
            state["n"] = state.get("n", 0) + 1
            if state["n"] in (3, 4):
                raise RuntimeError("boom")
            return {"target": {int(s): 0.2 for s in sorted(value.ids)[:5]}, "at": "open"}

        result, log = self.run_log(Program(decide), bars)
        calls = [row["t"] for row in log.decisions if row["called"]]
        out = [lot for lot in log.lots if lot["reason"] == "house"]
        self.assertEqual(len(out), 5)
        self.assertTrue(all((lot["exit"], lot["exit_at"]) == (calls[3] + 1, "open") for lot in out))
        self.assertEqual(result["runtime"]["errors"], 2)
        # one failed decide exits nothing: the lots were still held at the fourth call
        self.assertTrue(all(lot["exit"] > calls[2] + 1 for lot in out))

    def test_a_malformed_target_is_an_error_and_a_hold_never_a_failed_decide(self):
        bars = panel(sessions=80)

        def decide(value: Any, state: dict) -> Any:
            state["n"] = state.get("n", 0) + 1
            if state["n"] >= 2:
                return {"target": {int(s): 0.9 for s in sorted(value.ids)[:5]}, "at": "open"}   # over 20% a name
            return {"target": {int(s): 0.2 for s in sorted(value.ids)[:5]}, "at": "open"}

        result, log = self.run_log(Program(decide), bars)
        self.assertGreaterEqual(result["runtime"]["errors"], 3)
        self.assertEqual([lot["reason"] for lot in log.lots], ["open"] * 5, "positions held, nothing sold")
        self.assertEqual(result["status"], "ok")

    def test_a_disqualified_program_ends_flat_and_its_run_says_so(self):
        bars = panel(sessions=80)

        def decide(value: Any, state: dict) -> Any:
            state["n"] = state.get("n", 0) + 1
            if state["n"] > 1:
                raise RuntimeError("boom")
            return {"target": {int(s): 0.2 for s in sorted(value.ids)[:5]}, "at": "open"}

        result, log = self.run_log(Program(decide), bars, cfg=engine.EngineConfig(max_errors=2))
        self.assertEqual(result["status"], "disqualified")
        self.assertIn("errors", result["reason"])
        self.assertTrue(all(lot["exit"] is not None for lot in log.lots))


class TheVanishRule(EngineCase):
    def setUp(self):
        super().setUp()
        self.bars = panel()
        base, log = self.run_log(Program(first_k(5)), self.bars)
        self.lot = log.lots[0]
        self.col, self.entry = self.lot["col"], self.lot["entry"]

    def test_a_held_name_whose_bars_end_is_closed_on_the_third_session_with_the_haircut_and_no_fee(self):
        last = self.entry + 4                           # its last bar
        gone = no_bar(self.bars, self.col, range(last + 1, self.bars.n))
        result, log = self.run_log(Program(first_k(5)), changed(gone, exit=np.where(
            np.arange(gone.raw.shape[1]) == self.col, 1, 0).astype(np.int8)))
        lot = log.lots[0]
        self.assertEqual((lot["exit"], lot["exit_at"], lot["reason"]), (last + 3, "close", "vanished"))
        row = result["lots"][0]
        self.assertEqual(row["fees"], 0.0)
        qty = Decimal(str(row["weight"])) * 1000 / Decimal(f"{self.bars.raw[self.entry, self.col, 0] * (1 + HS):.6f}")
        expected = float(qty) * self.bars.raw[last, self.col, 3] * (1 - config.VANISH_HAIRCUT) - row["weight"] * 1000
        self.assertAlmostEqual(row["net"], expected, places=1)
        self.assertEqual(result["summary"]["vanished"], {"deal": 1, "other": 0})
        self.assertIn({"id": row["id"], "day": row["exit_day"], "kind": "vanished", "exit": "deal"}, result["actions"])
        # the House tried to sell it at the open after its first close out of U, and could not
        self.assertFalse(log.decision(last + 1)["derived"].elig[self.col])

    def test_the_haircut_is_the_lots_its_counterparts_and_its_cells_alike(self):
        """The pre-registration's 5.5: the vanish leg is -haircut for the lot AND for every member of a cell, so it
        makes and destroys no residual: the mean over a cell's members of (leg - the cell's mean) stays zero."""
        last = self.entry + 4
        gone = no_bar(self.bars, self.col, range(last + 1, self.bars.n))
        result, log = self.run_log(Program(first_k(5)), gone)
        v = last + 3
        series = placebo.residual(gone, log)
        at = v - gone.first
        own = log.lots[0]
        # the lot's own residual at the vanish session: w x (-h) less w x its cell's mean, whose members hold it too
        others = [lot for lot in log.lots if lot is not own and lot["entry"] <= v <= (lot["exit"] or gone.n)]
        tables = placebo._Tables(gone, log)
        row = placebo._Lot(own, tables, 1.0)
        legs = placebo._legs(tables, row, row.members, config.VANISH_HAIRCUT)
        k = v - own["entry"]
        mine = int(np.flatnonzero(row.members == self.col)[0])
        self.assertEqual(legs[mine, k], -config.VANISH_HAIRCUT)
        self.assertTrue(np.isnan(legs[mine, k - 2:k]).all(), "no leg on the sessions it had no bar")
        mean = np.nanmean(legs[:, k])
        self.assertAlmostEqual(float(np.nanmean(legs[:, k] - mean)), 0.0, places=15)
        # a lot of ANOTHER name whose cell holds the vanished name takes the same leg in its mean
        for lot in others:
            if self.col in lot["members"]:
                other = placebo._Lot(lot, tables, 1.0)
                theirs = placebo._legs(tables, other, other.members, config.VANISH_HAIRCUT)
                a = int(np.flatnonzero(other.members == self.col)[0])
                self.assertEqual(theirs[a, v - lot["entry"]], -config.VANISH_HAIRCUT)
        # and the sensitivity beside: at haircut 0 the lot loses nothing there, at 1 everything
        self.assertGreater(result["summary"]["sum_x_h0"], result["summary"]["sum_x"])
        self.assertLess(result["summary"]["sum_x_h1"], result["summary"]["sum_x"])
        zero = placebo.residual(gone, log, haircut=0.0)
        self.assertAlmostEqual(result["summary"]["sum_x_h0"], math.fsum(zero["x"].tolist()), places=15)
        self.assertNotEqual(series["x"][at], zero["x"][at])

    def test_two_sessions_without_a_bar_are_no_vanish_the_house_sells_when_the_bar_returns(self):
        gap = no_bar(self.bars, self.col, (self.entry + 5, self.entry + 6))
        result, log = self.run_log(Program(first_k(5)), gap)
        lot = log.lots[0]
        # out of U at the first close without a bar; the open after has none either; sold at the first open there is
        self.assertEqual((lot["exit"], lot["exit_at"], lot["reason"]), (self.entry + 7, "open", "house"))
        self.assertEqual(result["summary"]["vanished"], {"deal": 0, "other": 0})
        series = placebo.residual(gap, log)
        self.assertTrue(np.isfinite(series["x"]).all())

    def test_a_vanished_name_is_not_bought_back_by_the_standing_target(self):
        last = self.entry + 4
        gone = no_bar(self.bars, self.col, range(last + 1, last + 9))     # nine sessions dark, then it trades again
        result, log = self.run_log(Program(first_k(5)), gone)
        again = [lot for lot in log.lots[1:] if lot["col"] == self.col]
        for lot in again:
            self.assertTrue(log.decision(lot["decided"])["called"], "only a called decision buys it again")


# ============================================================================== entry validity, the standing target
class EntryValidityAndTheStandingTarget(EngineCase):
    def setUp(self):
        super().setUp()
        self.bars = panel()
        base, log = self.run_log(Program(first_k(5)), self.bars)
        self.base, self.lot = base, log.lots[0]
        self.col, self.entry = self.lot["col"], self.lot["entry"]

    def test_a_buy_with_no_bar_at_the_fill_is_not_opened_and_the_standing_target_buys_it_the_next_session(self):
        gap = no_bar(self.bars, self.col, (self.entry,))
        # still in U at the decision (it has its closes), no bar at the fill session
        result, log = self.run_log(Program(first_k(5)), gap)
        first = [lot for lot in log.lots if lot["decided"] == self.entry - 1]
        self.assertEqual(len(first), 4)
        self.assertEqual(result["picks"][0]["dropped"], [[int(self.lot["id"]), "no bar at the fill"]])
        self.assertEqual(result["summary"]["refused"]["no_bar"], 1)
        # the close of the fill session is no called decision, and the name is out of U there (no close): the
        # standing target waits until it is eligible again, then buys it as ONE lot with its own decision day
        back = next(t for t in range(self.entry, gap.n - 1) if log.decision(t)["derived"].elig[self.col])
        self.assertGreater(back, self.entry)
        late = [lot for lot in log.lots if lot["col"] == self.col]
        self.assertEqual((late[0]["decided"], late[0]["entry"]), (back, back + 1))
        self.assertFalse(log.decision(back)["called"])
        standing = [p for p in result["picks"] if not p["called"]]
        self.assertEqual(len(standing), 1, "one retry: once the name is held the standing target says nothing")
        self.assertEqual(day_index(gap, standing[0]["decided"]), back)
        self.assertEqual((standing[0]["buys"], standing[0]["sells"], standing[0]["ctx_sha"]),
                         ([[int(self.lot["id"]), 200.0]], [], None))
        self.assertEqual(standing[0]["targets"], result["picks"][0]["targets"])
        # its cell and members are that later close's
        derived = log.decision(late[0]["decided"])["derived"]
        self.assertEqual(late[0]["cell"], int(derived.cell[self.col]))

    def test_the_peek_a_buy_needs_a_valid_close_the_session_after_its_fill(self):
        gap = no_bar(self.bars, self.col, (self.entry + 1,))
        result, log = self.run_log(Program(first_k(5)), gap)
        self.assertEqual([lot for lot in log.lots if lot["col"] == self.col and lot["entry"] == self.entry], [])
        # the standing target tried again at the next close (the name still had its closes): no bar at that fill
        self.assertEqual(result["summary"]["refused"], {"no_bar": 1, "ahead": 1, "last": 0})
        self.assertEqual([why for _, why in result["picks"][0]["dropped"]],
                         ["no bar (its data do not hold through the session after the fill)"])

    def test_no_lot_is_opened_at_the_slices_last_session(self):
        bars = self.bars
        days = [from_ordinal(int(d)) for d in bars.days]
        # cut the slice so that its last session is a Monday: the decision before it is a called one
        last = max(t for t in range(bars.first + 5, bars.n) if days[t].weekday() == 0)
        cut = changed(bars, days=bars.days[:last + 1], early=bars.early[:last + 1], raw=bars.raw[:last + 1],
                      adj=bars.adj[:last + 1], elig0=bars.elig0[:last + 1])

        def decide(value: Any, state: dict) -> Any:
            state["n"] = state.get("n", 0) + 1
            ids = sorted(value.ids)
            return {"target": {int(s): 0.2 for s in ids[5 * (state["n"] % 2):][:5]}, "at": "open"}

        result, log = self.run_log(Program(decide), cut)
        self.assertNotIn(last, [lot["entry"] for lot in log.lots])
        self.assertEqual(result["summary"]["refused"]["last"], 5)
        self.assertEqual(len([lot for lot in log.lots if lot["exit"] == last]), 5, "its sales still go")

    def test_a_lots_cell_is_its_names_cell_at_the_decision_less_the_members_entry_validity_refuses(self):
        cell = self.lot["cell"]
        derived_members = [int(c) for c in self.lot["members"]]
        self.assertIn(self.col, derived_members)
        other = next(c for c in derived_members if c != self.col)
        gap = no_bar(self.bars, other, (self.entry + 1,))        # a cell-mate fails entry validity (the peek)
        result, log = self.run_log(Program(first_k(5)), gap)
        lot = next(row for row in log.lots if row["col"] == self.col and row["entry"] == self.entry)
        derived = log.decision(lot["decided"])["derived"]
        self.assertEqual(lot["cell"], cell)
        self.assertTrue(bool(derived.elig[other]) and int(derived.cell[other]) == cell)
        self.assertEqual([int(c) for c in lot["members"]], [c for c in derived_members if c != other])
        self.assertEqual(lot["members"].dtype, np.int32)
        self.assertEqual(result["summary"]["cells"], {"small": 0, "under5": sum(
            1 for row in log.lots if len(row["members"]) < config.MIN_CELL)})

    def test_a_hold_a_none_and_a_refused_target_leave_the_standing_target_standing(self):
        for answer in ({"hold": True}, None, "cap"):
            with self.subTest(answer=answer):
                def decide(value: Any, state: dict, answer=answer) -> Any:
                    state["n"] = state.get("n", 0) + 1
                    ids = sorted(value.ids)
                    if state["n"] == 1:
                        return {"target": {int(s): 0.2 for s in ids[:5]}, "at": "open"}
                    if answer == "cap":
                        return {"target": {int(s): 0.05 for s in ids[5:18]}, "at": "open"}    # 13 buys: refused whole
                    return answer

                gap = no_bar(self.bars, self.col, (self.entry + 5, self.entry + 6))
                result, log = self.run_log(Program(decide, max_names=20), gap)
                # the House sold the name when it lost its bars: no standing buy brings back a House exit
                mine = [lot for lot in log.lots if lot["col"] == self.col]
                self.assertEqual(len(mine), 1)
                self.assertEqual(len(log.lots), 5, "the later answers planned nothing")
                if answer == "cap":
                    refused = [p for p in result["picks"] if p["dropped"] == [[None, "order cap"]]]
                    self.assertGreaterEqual(len(refused), 2)
                    self.assertTrue(all(p["targets"] == [] and p["buys"] == [] for p in refused))

    def test_the_cash_cut_a_buy_the_sleeve_cannot_fund_is_cut_and_never_a_negative_cash(self):
        bars = panel(drift=-0.004)                      # a falling market: each rotation leaves less cash

        def decide(value: Any, state: dict) -> Any:
            state["n"] = state.get("n", 0) + 1
            ids = sorted(value.ids)
            return {"target": {int(s): 0.2 for s in ids[5 * (state["n"] % 2):][:5]}, "at": "open"}

        result, log = self.run_log(Program(decide), bars)
        self.assertLess(result["summary"]["pnl"], -20)
        weights = [lot["weight"] for lot in log.lots]
        self.assertLess(min(weights), 0.199, "the last buy of a rotation is cut to the cash the sleeve has")
        self.assertLessEqual(max(weights), 0.2 + 1e-12, "and nothing compounds: a lot is never more than w x E0")


# ============================================================================================= the result record
class TheResultRecord(EngineCase):
    def setUp(self):
        super().setUp()
        self.bars = panel()
        self.result, self.log = self.run_log(Program(keyed(5), params={"a": 1}), self.bars)

    def test_its_keys_and_its_daily_rows(self):
        result = self.result
        for key in ("run_id", "program", "program_sha", "run_sha", "params", "window", "panel", "half", "engine",
                    "data_version", "universe", "capital", "k", "rung", "trials", "status", "needs", "summary",
                    "by_year", "daily", "lots", "picks", "picks_sha", "factors", "actions", "runtime", "result_sha",
                    "start", "end"):
            self.assertIn(key, result)
        for absent in ("placebo", "style", "calls"):
            self.assertNotIn(absent, result)
        self.assertEqual((result["engine"], result["panel"], result["rung"], result["trials"], result["half"]),
                         ("xs-engine-1", "sp500", "R0", 1, None))
        self.assertEqual((result["capital"], result["k"], result["window"]), ("1000", 1.0, "train"))
        self.assertEqual(result["params"], {"a": 1})
        self.assertEqual(len(result["daily"][0]), len(results.DAILY))
        iso = [from_ordinal(int(d)).isoformat() for d in self.bars.days[self.bars.first:]]
        self.assertEqual(results.column(result, "day"), iso)
        self.assertEqual((result["start"], result["end"]), (iso[0], iso[-1]))
        json.dumps(result, allow_nan=False)             # the child answers JSON: every value is plain and finite

    def test_the_daily_series_is_the_pre_registered_residual_of_the_holdings_log(self):
        series = placebo.residual(self.bars, self.log)
        for name, key in (("r", "r"), ("x", "x"), ("x15", "x15"), ("u", "u"), ("w", "w"), ("bench", "bench")):
            self.assertEqual(results.column(self.result, name), series[key].tolist(), name)
        self.assertEqual(results.column(self.result, "exits"), series["exits"].tolist())
        self.assertEqual(results.column(self.result, "invested"), series["invested"].tolist())
        x, r, bench = (np.array(results.column(self.result, n)) for n in ("x", "r", "bench"))
        self.assertTrue(np.array_equal(x, r - bench))
        summary = self.result["summary"]
        self.assertEqual(summary["sum_x"], math.fsum(x.tolist()))
        self.assertEqual(summary["t_x"], results.t_stat(x))
        self.assertEqual(summary["round_trips"], sum(1 for lot in self.log.lots if lot["exit"] is not None))
        self.assertEqual((summary["sum_x_h0"], summary["sum_x_h1"]), (summary["sum_x"], summary["sum_x"]))
        self.assertEqual(summary["basket"], "basket-led" if summary["sum_bench"] >= summary["sum_x"]
                         else "selection-led")
        self.assertGreater(summary["costs"], 0.0)
        self.assertTrue(0.5 < summary["dilution"] < 1.0, "a lot's own name is one member of its cell")

    def test_the_lots_rows_hold_ids_and_cells_never_a_column_or_a_symbol(self):
        ids = {int(s) for s in self.bars.ids}
        for row, lot in zip(self.result["lots"], self.log.lots):
            self.assertEqual(set(row), {"lid", "id", "cell", "weight", "decided_day", "entry_day", "entry_at",
                                        "exit_day", "exit_at", "net", "fees", "div", "hs", "hs_exit", "reason", "tag",
                                        "held_sessions"})
            self.assertIn(row["id"], ids)
            self.assertEqual(row["id"], int(self.bars.ids[lot["col"] - REF]))
            self.assertEqual(row["cell"], lot["cell"])
            self.assertEqual(row["hs"], HS)
        self.assertNotIn("col", json.dumps(self.result["lots"]))

    def test_the_picks_one_a_called_decision_and_their_sha(self):
        picks = self.result["picks"]
        self.assertEqual(self.result["picks_sha"], results.sha(picks))
        called = [row["t"] for row in self.log.decisions if row["called"]]
        self.assertEqual([day_index(self.bars, p["decided"]) for p in picks if p["called"]], called)
        for pick in picks:
            self.assertEqual(day_index(self.bars, pick["exec"]), day_index(self.bars, pick["decided"]) + 1)
            self.assertEqual(len(pick["ctx_sha"]), 64)
            self.assertEqual(pick["budget"], 1000.0)
            for slot, usd in pick["buys"]:
                self.assertEqual(usd, 200.0)
            for lid, slot, day in pick["sells"]:
                self.assertEqual(self.result["lots"][lid - 1]["id"], slot)
                self.assertEqual(self.result["lots"][lid - 1]["entry_day"], day)

    def test_the_summary_counts_by_close_date(self):
        capital = 1000.0
        dates = results.close_dates(self.result["lots"], capital)
        by_day: dict[str, list] = {}
        for row in self.result["lots"]:
            if row["exit_day"]:
                by_day.setdefault(row["exit_day"], []).append(row)
        self.assertEqual(sorted(dates), sorted(by_day))
        for day, rows in by_day.items():
            self.assertAlmostEqual(dates[day], math.fsum(r["net"] for r in rows) / math.fsum(
                r["weight"] * capital for r in rows), places=12)
        summary = self.result["summary"]
        self.assertEqual(summary["close_dates"], len(dates))
        values = list(dates.values())
        mean = math.fsum(values) / len(values)
        self.assertAlmostEqual(summary["sd_date_return"], math.sqrt(math.fsum((v - mean) ** 2 for v in values) / (
            len(values) - 1)), places=15)

    def test_the_views(self):
        train = results.view(self.result, "train")
        self.assertEqual(tuple(train), results.TRAIN_VIEW)
        text = json.dumps(train)
        for slot in self.bars.ids[:5]:
            self.assertNotIn(str(int(slot)), text)
        self.assertNotIn("daily", train)
        self.assertEqual(train["pick_counts"]["called"], self.result["summary"]["calls"])
        for window in ("validation", "look", "forward"):
            self.assertEqual(results.view(self.result, window), {"status": "ok"})
        with self.assertRaises(ValueError):
            results.view(self.result, "gate")

    def test_the_house_panel_factors_beside(self):
        factors = self.result["factors"]
        self.assertEqual([row[0] for row in factors], results.column(self.result, "day"))
        self.assertTrue(all(len(row) == 5 and all(math.isfinite(v) for v in row[1:]) for row in factors))
        closes = self.bars.adj[:, config.MARKET_COLUMN, 3]
        first = self.bars.first
        self.assertAlmostEqual(factors[3][1], closes[first + 3] / closes[first + 2] - 1.0, places=9)
        self.assertTrue(any(abs(row[2]) > 0 for row in factors))

    def test_calls_rebuild_each_called_decisions_inputs(self):
        result, _ = self.run_log(Program(keyed(5), params={"a": 1}), self.bars, calls=True)
        self.assertEqual(result["result_sha"], self.result["result_sha"], "the calls are outside the result's sha")
        called = [p for p in result["picks"] if p["called"]]
        self.assertEqual(len(result["calls"]), len(called))
        needs = program.Needs(**result["needs"])
        for call, pick in zip(json.loads(json.dumps(result["calls"])), called):
            self.assertEqual(set(call), {"t", "positions", "closed", "rejects", "cash", "equity", "budget"})
            self.assertEqual(day_index(self.bars, pick["decided"]), call["t"])
            book = {k: v for k, v in call.items() if k != "t"}
            again = ctx.inputs_from_panel(self.bars, call["t"], needs=needs, params=result["params"], **book)
            self.assertEqual(hashlib.sha256(ctx.ctx_bytes(ctx.build(again))).hexdigest(), pick["ctx_sha"])

    def test_placebos_and_the_style_block_only_when_asked(self):
        block = {"lots": 3, "n": {}, "weight": {}, "sum": {}}
        seen = []

        def fake(bars: Any, log: Any) -> Any:
            seen.append((bars, log))
            return block

        with mock.patch.object(xs_style, "block", fake):
            result = engine.run(Program(keyed(5), params={"a": 1}), self.bars, placebos=40, style=True)
        self.assertEqual(result["style"], block)
        self.assertEqual(len(seen), 1, "ONE call: the rule is package E's")
        self.assertIs(seen[0][0], self.bars)
        self.assertIsInstance(seen[0][1], engine.Log)
        placebos = result["placebo"]
        self.assertEqual((placebos["n"], placebos["rung"], list(placebos["spans"])), (40, "R0", ["run"]))
        self.assertEqual(placebos["seed"], placebo.train_seed(result["run_sha"], "train"))
        self.assertEqual(placebos["spans"]["run"]["days"], self.bars.n - self.bars.first)
        other = engine.run(Program(keyed(5), params={"a": 1}), self.bars, placebos=40, seed=7)
        self.assertEqual(other["placebo"]["seed"], 7)
        self.assertNotEqual(other["placebo"]["spans"]["run"]["t"], placebos["spans"]["run"]["t"])

    def test_the_looks_run_reads_its_placebos_on_validation_and_on_the_holdout(self):
        start = dt.date(2025, 10, 1)                    # a synthetic calendar that straddles the two windows
        bars = panel(sessions=120, first=25, window="look", start=start)
        spans = engine.look_spans(bars)
        days = [from_ordinal(int(d)) for d in bars.days]
        self.assertEqual(set(spans), {"V", "H"})
        self.assertEqual(spans["V"][0], bars.first)
        self.assertTrue(days[spans["V"][1]].year == 2025 and days[spans["V"][1] + 1].year == 2026)
        self.assertEqual(spans["H"], (next(i for i, d in enumerate(days) if d >= e1.LOOK_FIRST), bars.n - 1))
        self.assertIsNone(engine.look_spans(panel()))
        result = engine.run(Program(keyed(5)), bars, placebos=25, seed=99)
        self.assertEqual(set(result["placebo"]["spans"]), {"V", "H"})

    def test_an_exception_is_a_failed_record_and_no_data_is_said(self):
        failed = engine.run_isolated(Program(first_k(5)), "not bars")
        self.assertEqual((failed["status"], failed["trials"]), ("error", 0))
        self.assertIn("Error", failed["reason"])
        bars = panel()
        empty = changed(bars, first=bars.n)
        result = engine.run(Program(first_k(5)), empty)
        self.assertEqual((result["status"], result["daily"], result["lots"]), ("no_data", [], []))

    def test_the_universe_is_part_of_a_runs_identity(self):
        elig0 = self.bars.elig0.copy()
        elig0[:, REF::2] = False                        # a half run: the other half's members are invisible
        half, log = self.run_log(Program(keyed(5), params={"a": 1}), changed(self.bars, elig0=elig0))
        self.assertNotEqual(half["run_id"], self.result["run_id"])
        self.assertNotEqual(half["universe"], self.result["universe"])
        visible = {int(c) for c in range(REF, self.bars.raw.shape[1], 2)}
        hidden = set(range(REF, self.bars.raw.shape[1])) - visible
        self.assertTrue(hidden)
        for lot in log.lots:
            self.assertNotIn(lot["col"], visible)
            self.assertFalse(visible & {int(c) for c in lot["members"]}, "in no cell, no placebo candidate")


class SplitsAndDividends(EngineCase):
    def setUp(self):
        super().setUp()
        self.bars = panel()
        base, log = self.run_log(Program(first_k(5)), self.bars)
        self.base, self.lot = base, log.lots[0]
        self.col, self.entry = self.lot["col"], self.lot["entry"]

    def test_the_cent_rounding_of_the_adjusted_series_books_nothing(self):
        """The vendor rounds adjustment=all prices to the cent: the all/raw ratio jitters with no event at all."""
        adj = np.round(self.bars.adj * 0.731, 2)        # a restated history, on the cent grid
        result, log = self.run_log(Program(first_k(5)), changed(self.bars, adj=adj))
        self.assertEqual([a for a in result["actions"] if a["kind"] in ("dividend", "split", "anomaly")], [])
        self.assertEqual(result["summary"]["dividends"], 0.0)

    def test_a_split_keeps_the_lots_value_and_a_dividend_is_credited(self):
        raw, adj = self.bars.raw.copy(), self.bars.adj.copy()
        split = self.entry + 3
        raw[split:, self.col, :4] /= 4.0                # a 4-for-1: the raw price falls to a quarter
        raw[split:, self.col, 4] *= 4.0
        adj[:, self.col] = raw[:, self.col, :4]
        adj[:split, self.col] /= 4.0                    # the adjusted series is continuous across it
        ex = self.entry + 5
        cash = 0.02 * raw[ex - 1, self.col, 3]          # a 2% dividend
        adj[:ex, self.col] *= 1.0 - cash / raw[ex - 1, self.col, 3]
        result, log = self.run_log(Program(first_k(5)), changed(self.bars, raw=raw, adj=adj))
        kinds = [(a["kind"], a.get("factor")) for a in result["actions"] if a["id"] == int(self.lot["id"])]
        self.assertEqual(kinds, [("split", "4:1"), ("dividend", None)])
        row = result["lots"][0]
        qty = Decimal(str(row["weight"])) * 1000 / Decimal(f"{self.bars.raw[self.entry, self.col, 0] * (1 + HS):.6f}")
        self.assertAlmostEqual(row["div"], float(qty) * 4 * cash, places=1)
        self.assertEqual(result["summary"]["dividends"], row["div"])
        # the split made no P&L: the day's equity moved as the unsplit name's would have
        base_equity = results.column(self.base, "equity")
        equity = results.column(result, "equity")
        at = split - self.bars.first
        self.assertAlmostEqual(equity[at], base_equity[at], places=1)


class ThePooledReading(EngineCase):
    def test_several_runs_of_one_version_read_as_one(self):
        one = engine.run(Program(keyed(5)), panel(seed=3))
        two = engine.run(Program(keyed(5)), panel(seed=4, start=dt.date(2032, 3, 1)))
        pooled = results.pooled([one, two])
        self.assertEqual((pooled["runs"], pooled["status"]), (2, "ok"))
        x = results.column(one, "x") + results.column(two, "x")
        summary = pooled["summary"]
        self.assertEqual(summary["t_x"], results.t_stat(x))
        self.assertEqual(summary["sum_x"], math.fsum([one["summary"]["sum_x"], two["summary"]["sum_x"]]))
        self.assertAlmostEqual(summary["sum_x"], math.fsum(x), places=12)
        for key in ("days", "lots", "closed", "calls", "rebalances", "round_trips", "invested_days"):
            self.assertEqual(summary[key], one["summary"][key] + two["summary"][key], key)
        dates = [*results.close_dates(one["lots"], 1000).values(), *results.close_dates(two["lots"], 1000).values()]
        self.assertEqual(summary["close_dates"], len(dates))
        self.assertEqual(sorted(pooled["by_year"]), ["2031", "2032"])
        self.assertEqual(pooled["by_year"]["2031"]["days"], one["by_year"]["2031"]["days"])
        self.assertEqual(math.fsum(row["sum_x"] for row in pooled["by_year"].values()), summary["sum_x"])
        bad = results.pooled([one, results.failed("p", "boom")])
        self.assertEqual(bad["status"], "error")

    def test_t_is_e1s_expression_and_the_newey_west_t_beside(self):
        from league.equity.screen import holdout_t

        rng = np.random.default_rng(5)
        x = rng.normal(0.0002, 0.004, 194)
        self.assertEqual(results.t_stat(x), holdout_t(x))
        self.assertEqual(results.t_stat(x.tolist()), float(np.mean(x)) / float(np.std(x, ddof=1)) * math.sqrt(194))
        self.assertIsNone(results.t_stat(np.zeros(50)))
        self.assertIsNone(results.t_stat([1.0]))
        # with no serial dependence asked for, the Newey-West t is the plain t on the ddof-0 variance
        plain = float(np.mean(x)) / math.sqrt(float(np.var(x)) / len(x))
        self.assertAlmostEqual(results.nw_t(x, lag=0), plain, places=10)
        self.assertIsNone(results.nw_t([0.0] * 10))
        slow = np.repeat(rng.normal(0.0, 0.004, 40), 5)          # positively autocorrelated: a smaller |t|
        self.assertLess(abs(results.nw_t(slow)), abs(results.nw_t(slow, lag=0)))


class TheCtxBuilder(unittest.TestCase):
    def test_the_decisions_own_derived_is_handed_over_when_build_takes_it(self):
        seen: list[Any] = []
        with mock.patch.object(ctx, "build", lambda inputs, derived=None: seen.append((inputs, derived)) or "ctx"):
            self.assertEqual(engine.build_ctx("inputs", "derived"), "ctx")
        with mock.patch.object(ctx, "build", lambda inputs: seen.append((inputs,)) or "ctx"):
            self.assertEqual(engine.build_ctx("inputs", "derived"), "ctx")
        self.assertEqual(seen, [("inputs", "derived"), ("inputs",)])


class TheDoubleIsTheContract(unittest.TestCase):
    """The doubles' cells are the pre-registration's 3.3: the study's own vector (CH) holds them."""

    def test_the_cells_of_the_studys_hundred_names(self):
        vector = json.loads((FIXTURES / "xs1_conformance.json").read_text())["vectors"]["CH"]["cells"]
        count = vector["names"]
        elig = np.ones(count, dtype=bool)
        elig[vector["not_in_U"]] = False
        _, _, cell = cells(elig, np.array(vector["sector"]), np.array(vector["beta"]), np.array(vector["mom"]))
        self.assertEqual(cell.tolist(), vector["cell_id"])


if __name__ == "__main__":
    unittest.main()
