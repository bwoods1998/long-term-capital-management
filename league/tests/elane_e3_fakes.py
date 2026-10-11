"""Fakes for release E3's memory tests (the hidden year, the out-of-fold arithmetic, the memory tables and their seals):
a family born with a hidden year, a program whose sizes and STATE would carry a hidden year into every later decision,
E1's synthetic store with one year's opens moved, and an invented market whose runner answers each span with that
span's rows and a small real slice of bars. Every family, program, price and number here is invented; no market data
is read."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

import numpy as np

from league.equity.store import Bars, nyse_sessions, ordinal, write_store
from league.swarm import elane_births, elane_train
from league.swarm.store import SwarmStore
from league.tests import elane_e2_fakes as fx

#: Whether this tree carries release E3's patches to E2's files (league/ops/E3_INTERFACES.md: 11.7 `elane_train`, 11.8
#: `elane_births`, 11.9 `elane_seal`). A builder's own branch does not: the tests of the wired flow run at integration.
WIRED = hasattr(elane_train, "elane_memory") and hasattr(elane_births, "elane_folds")
NOT_WIRED = "release E3's patches to league/swarm/elane_train.py and elane_births.py (11.7, 11.8) are not on this tree"

WORK_YEARS = (2016, 2017, 2018, 2019, 2022, 2023, 2024)


def settings(mode: str = "record", **e2: Any) -> dict[str, Any]:
    """The swarm's settings with the lanes on, E2's `e2` keys and `elane.memory.mode`."""
    return {"elane": {"mode": "gate", "universe": ["SPY", "QQQ", "IWM", "DIA"], "structures": ["etf"],
                      "birth_share": 0.25, "e2": {"train_budget": 3, "train_per_round": 5, **e2},
                      "memory": {"mode": mode}},
            "population": {"start": 48, "ceiling": 96, "floor": 2}, "architect": {}, "gym": {}}


def hidden_family(store: SwarmStore, slug: str, hidden: int | None, *, lane: str = "beta", agenda: str = "overnight",
                  symbols: tuple[str, ...] = ("SPY",), code: str | None = None, route: str = "sail:pro_asap",
                  mechanism: str | None = None) -> dict[str, Any]:
    """An E2 family as the equity pass bears it under release E3: its spec carries `hidden_year` (None: seven Train
    years), `gid` and the reserved `expected_oof`; a v1 when `code` is given."""
    spec = {"id": slug, "mechanism": mechanism or f"Invented mechanism {slug}: holders are paid for overnight index risk.",
            "structure": "etf", "roots": list(symbols), "symbols": list(symbols), "lane": lane, "agenda": agenda,
            "e2_route": route, "hidden_year": hidden, "gid": "g0", "expected_oof": None}
    fam = store.add_family(spec, origin="architect")
    if code is not None:
        store.add_version(fam["id"], code, {}, author="architect:test")
    store.set_state(fam["id"], **{elane_train.STATE_KEY: {"status": "researching", "versions": {}}})
    return store.family(fam["id"])


#: An invented program that would carry a hidden year into every later decision of a whole-span run, three ways: it
#: sizes each buy from `ctx.cash` (the sleeve's cash holds every earlier session's P&L), it keeps a STATE flag that
#: only a bar with a huge overnight gap sets (the moved store's hidden-year bars; no other bar has one), and it holds
#: a lot over every close, so a lot would cross the year's edge.
CARRIES = '''import math

NEEDS = {"symbols": ["SPY"], "history": 3, "max_hold_sessions": 2}
PARAMS = {"part": 0.5, "gap": 0.2}
STATE = {}


def decide(ctx):
    bars = ctx.bars["SPY"]
    if len(bars.close) > 1 and abs(float(bars.open[-1]) / float(bars.close[-2]) - 1.0) > ctx.params["gap"]:
        STATE["gapped"] = True
    out = [{"sell": lot["id"], "at": "open"} for lot in ctx.positions]
    part = ctx.params["part"] * (0.5 if STATE.get("gapped") else 1.0)
    usd = math.floor(100.0 * part * ctx.cash) / 100.0
    if usd >= 20.0:
        out.append({"buy": "SPY", "usd": usd, "at": "close"})
    return out
'''
#: `CARRIES`' NEEDS history: the moved store keeps that many of the year's last sessions as they were.
CARRIES_HISTORY = 3


def moved_store(source: str | Path, target: str | Path, *, year: int, keep_last: int, factor: float = 1.3) -> Path:
    """A copy of the synthetic store at `source` that differs ONLY inside `year`: the open (raw and adjusted) of each of
    its sessions before the last `keep_last` is multiplied by `factor` (its high raised to wrap it). The same closes
    everywhere, so no price level moves outside the year, and the year's last `keep_last` sessions (the look-back of
    the stretch that follows) are as they were."""
    source, target = Path(source), Path(target)
    with np.load(source / "calendar.npz") as cal:
        days = [dt.date(1970, 1, 1) + dt.timedelta(days=int(d)) for d in cal["days"]]
        early = [bool(e) for e in cal["early"]]
    series: dict[str, dict[str, Any]] = {}
    for path in sorted((source / "bars").glob("*.npz")):
        with np.load(path) as held:
            arrays = {name: np.array(held[name]) for name in held.files}
        own = [dt.date(1970, 1, 1) + dt.timedelta(days=int(d)) for d in arrays["days"]]
        inside = [i for i, d in enumerate(own) if d.year == int(year)]
        moved = inside[:-int(keep_last)] if keep_last else inside
        for prefix in ("raw", "all"):
            arrays[f"{prefix}_o"][moved] = np.round(arrays[f"{prefix}_o"][moved] * float(factor), 4)
            arrays[f"{prefix}_h"][moved] = np.maximum(arrays[f"{prefix}_h"][moved], arrays[f"{prefix}_o"][moved])
        series[path.stem] = {"days": own, **{name: [float(v) for v in values] for name, values in arrays.items()
                                              if name != "days"}}
    write_store(target, calendar=list(zip(days, early)), series=series, classes={s: "etf" for s in series},
                fetched_through=days[-1], source="synthetic", gate=False)
    return target


def year_figures(**override: Any) -> dict[str, Any]:
    """One year's invented row of the invented market (league/equity/results.py's by-year keys) and its lot's weight."""
    return {"trades": 60, "days": 252, "days_traded": 30, "pnl": 20.0, "t_daily": 0.6, "exposure_mean": 0.3, "bh_pnl": 6.0,
            "weight": 0.3, **override}


class InventedMarket:
    """E1's isolated runner over an invented market (a by-year row each year 2016-2024): `train(start, end)` answers
    only the requested sessions' years, its summary summed from them, with a small real slice of bars (the first five
    sessions of each year, invented prices) and one closed lot a year, so the out-of-fold arithmetic has a series to
    read. `figures[year]` overrides a year's row and its lot's weight (what two markets differ in). A program whose
    text holds "fails" loses at the stress. It has NO LOOK-BACK: a span's rows never depend on another year's. Its
    `decider` is E2's fake (the restart check's kinds). What a test can make of THE HIDDEN RUN (a run over exactly the
    year `hidden`, 1 January to 31 December): `hidden_status` (how it ended) and `fails` (an exception it raises)."""

    def __init__(self, figures: Mapping[int, Mapping[str, Any]] | None = None, *, hidden: int | None = None,
                 hidden_status: str = "ok", fails: BaseException | None = None):
        self.rows = {y: year_figures() for y in range(2016, 2025)}
        for y, row in (figures or {}).items():
            self.rows[int(y)] = year_figures(**row)
        self.hidden = hidden
        self.hidden_status = hidden_status
        self.fails = fails
        self.calls: list[tuple[float, dt.date, dt.date]] = []
        self.runs: list[Any] = []
        self.decider = fx.FakeDecider()

    @staticmethod
    def sessions(year: int) -> list[dt.date]:
        return [d for d, _ in nyse_sessions(dt.date(year, 1, 1), dt.date(year, 1, 31))][:5]

    def bars(self, years: list[int]) -> Bars:
        days = [d for y in years for d in self.sessions(y)]
        level = np.array([100.0 + 3.0 * (d.year % 7) + 0.5 * i * (1 + d.year % 3) for i, d in enumerate(days)])
        raw = np.column_stack([level, level + 0.4, level - 0.4, level + 0.2, np.full(len(days), 1e6)])
        return Bars(days=np.array([ordinal(d) for d in days], dtype=np.int32), early=np.zeros(len(days), dtype=bool),
                    first=0, symbols=("SPY",), raw={"SPY": raw}, adj={"SPY": raw[:, :4].copy()}, window="train",
                    data_version="invented")

    def train(self, code: str, params: Any, *, name: str, start: Any = None, end: Any = None, k: float = 1.0) -> Any:
        self.calls.append((float(k), start, end))
        hidden_run = self.hidden is not None and (start, end) == (dt.date(self.hidden, 1, 1), dt.date(self.hidden, 12, 31))
        if hidden_run and self.fails is not None:
            raise self.fails
        years = [y for y in self.rows if start.year <= y <= end.year]
        factor = 1.0 if k == 1.0 else (-0.5 if "fails" in code else 0.7)
        rows = {str(y): {key: (round(value * factor, 2) if key == "pnl" else value)
                         for key, value in self.rows[y].items() if key != "weight"} for y in years}
        lots = []
        for i, y in enumerate(years):
            days = self.sessions(y)
            lots.append({"lid": i + 1, "symbol": "SPY", "class": "etf", "weight": float(self.rows[y]["weight"]),
                         "qty": 1.0, "entry_day": days[0].isoformat(), "entry_at": "close", "entry_px": 100.0,
                         "exit_day": days[2].isoformat(), "exit_at": "open", "exit_px": 101.0, "fees": 0.02, "div": 0.0,
                         "hs": 0.0001 * float(k), "reason": "program", "held_sessions": 2})
        result = {"run_id": f"{name}-{k}-{start}", "run_sha": "invented-run", "status": "ok", "window": "train",
                  "start": start.isoformat(), "end": end.isoformat(), "symbols": ["SPY"], "capital": "1000",
                  "needs": {"symbols": ["SPY"], "history": 0, "max_hold_sessions": 2}, "by_year": rows,
                  "daily": fx.daily_rows(rows), "lots": lots,
                  "summary": {"trades": sum(r["trades"] for r in rows.values()),
                              "days_traded": sum(r["days_traded"] for r in rows.values()),
                              "pnl": round(sum(r["pnl"] for r in rows.values()), 2), "fees": 1.0, "win_rate": 0.55,
                              "exposure_mean": 0.3, "max_drawdown": 30.0, "mean_net_return": 0.001},
                  "bh": {"pnl": round(sum(r["bh_pnl"] for r in rows.values()), 2)},
                  "mte": {"mean": 0.0004, "t": 0.9, "n": 40}}
        if hidden_run:
            result["status"] = self.hidden_status
        run = SimpleNamespace(result=result, bars=self.bars(years))
        self.runs.append(run)
        return run


def table(store: SwarmStore, name: str) -> list[dict[str, Any]]:
    """Every row of a swarm store table, in its key order ([] for a table that does not exist)."""
    if store._one("SELECT 1 AS ok FROM sqlite_master WHERE type='table' AND name=?", (name,)) is None:
        return []
    return store._all(f"SELECT * FROM {name} ORDER BY 1, 2")


def dump(store: SwarmStore, *, less: tuple[str, ...] = ()) -> dict[str, list[dict[str, Any]]]:
    """Every table of the swarm store but `less`, row by row (a whole-store snapshot for "nothing else changed")."""
    names = [r["name"] for r in store._all("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    return {name: store._all(f"SELECT * FROM {name}") for name in names
            if name not in less and not name.startswith("sqlite_")}


__all__ = ["WIRED", "NOT_WIRED", "WORK_YEARS", "settings", "hidden_family", "CARRIES", "CARRIES_HISTORY", "moved_store",
           "year_figures", "InventedMarket", "table", "dump"]
