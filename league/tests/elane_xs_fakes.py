"""Fakes for package G's tests (release E4, the panel lane in the swarm): league.xs AT ITS INTERFACES, as E1's gate
tests fake the runner and the screen at theirs. The store, the engine, the placebos, the screen, the style rule and
the identity are other packages' (C, D, E); what is tested here is the swarm's own conduct around them, so every
test of package G runs the same whether or not those packages are built in the tree.

What is faked, each to the contract's own shape (league/xs/E4_INTERFACES.md):
- the panel runner (`league.xs.runner.Isolated`): `FakeRunner`, an invented engine. A program's PARAMS say what its
  runs are (its daily residual edge, by year when asked; its noise; its cost at 1.5x; its halves; its placebos; its
  style; a status), and each run's result is that program's daily rows on the TRUE NYSE sessions of the span asked,
  starting flat (a run knows nothing of another run). Its `market` adds a per-year term to the programs that ask for
  it, so a test can change one year of the market and see what moves;
- the panel kind of the decider (`FakeDecider`): a program loaded in this process, its STATE fresh at every load;
- `league.xs.results.pooled` and `view`, `league.xs.placebo.stat` and `look_seed`, `league.xs.style.pooled`,
  `style_open` and `seat_refusal`, `league.xs.screen` (the pin, `series`, the pre-check, the floor, the gate's rule in
  integers, the sentence, the lineage rule in either series), `league.xs.identity`, `league.xs.config.quiet`,
  `league.xs.runner.state_stream`, `league.xs.store.Universe`;
- the panel manifest, the twin marker and the probe's file, written as JSON under a temporary state root.
`switch_on(case)` installs them for the life of a test. `PATCHED` says whether package G's patches to E1's and E2's
files are applied (the integrated tree): where they are not, `switch_on` also gives the store the panel structure as
patch 1 does, so `elane_xs`'s own functions are tested on either tree; a test that holds a PATCHED file's behaviour
(the ration's members, the band reader, the dispatches) is skipped until then and says which patch it holds.
Every family, program and number here is invented; no market data is read.
"""

from __future__ import annotations

import ast
import datetime as dt
import hashlib
import json
import math
import random
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping, Sequence
from unittest import mock

from league.equity.store import GATE_MARK, nyse_sessions, ordinal
from league.swarm import elane, elane_xs
from league.swarm import store as store_mod
from league.swarm.store import SwarmStore
from league.tests.swarm_fakes import Clock
from league.xs import XS_ENGINE_VERSION
from league.xs import config as xconfig
from league.xs import identity as xidentity
from league.xs import placebo as xplacebo
from league.xs import results as xresults
from league.xs import runner as xrunner
from league.xs import screen as xscreen
from league.xs import store as xstore
from league.xs import style as xstyle

#: Package G's patches to E1's and E2's files are applied in this tree (league/swarm/e4_patches/G.md, patch 1).
PATCHED = "panel" in store_mod.EQUITY_STRUCTURES
HOLDS = "holds package G's patch {n} (league/swarm/e4_patches/G.md): applied at integration"
#: A release root with no docs/ (the House box's): no receipt file is at hand.
NO_DOCS = Path(__file__).resolve().parent / "fixtures" / "no-such-release-root"
FAKE_SHA = "ab" * 32
#: The fake receipt's sentence: every placeholder of `screen.BESIDE_FIELDS`, and nothing a real receipt measured.
FAKE_BESIDE = ("FAKE XS1 sentence: bar {c_used} (own floor {c_p}), own rate {own_fp}%, earlier looks in its cell "
               "{n_cell}, P&L {basket}, French {label}, flags {flags}")
#: The decision calls the fake restart check's stream gives a seen span (resets fall after calls 3, 10, 13, 20, 23, 30).
STATE_CALLS = 34
ROUTE = "sail:pro_asap"


def pin_block(**over: Any) -> dict[str, Any]:
    """`elane.screens.equity_xs` as an integrator would fill it from a receipt (`screen.PIN_KEYS`), with FAKE figures
    (c_XS is the fake's own: no test reads a real threshold)."""
    block = {"name": "XS1", "screen": "XS1", "receipt_sha256": FAKE_SHA, "c_XS": 1.0, "c_margin": 0.05,
             "alpha_plac": 0.12, "placebo_draws": 999, "rung": "R0", "fp_cap": 0.12, "owner_wall": 0.15,
             "validation_tries": 1, "holdout_looks": 1, "retry": False, "flags": {}, "screen_flags": ["style-open"],
             "beside": FAKE_BESIDE}
    block.update(over)
    assert tuple(block) == xscreen.PIN_KEYS, "the fake pin has the pin's keys, in its order"
    return block


def settings(mode: str = "gate", *, lane: str = "gate", e2: Mapping[str, Any] | None = None,
             **panel: Any) -> dict[str, Any]:
    """The swarm's settings with the equity lanes on (`lane`) and `elane.panel` at `mode` with `panel` keys."""
    return {"elane": {"mode": lane, "universe": ["SPY", "QQQ", "IWM", "DIA"], "structures": ["etf"], "birth_share": 0.25,
                      "roster": 3, "e2": dict(e2 or {}), "panel": {"mode": mode, **panel}},
            "population": {"start": 48, "ceiling": 96}, "architect": {}, "gym": {}}


# ------------------------------------------------------------------------------------------------- invented programs
def program(*, names: int = 5, rebalance: str = "weekly", weekday: int = 0, body: str | None = None,
            state: str = "", **params: Any) -> str:
    """An invented panel program (XS.md's shape) whose PARAMS tell `FakeRunner` what its runs are. `body`: the body of
    decide(ctx) (default: the first `names` slots at equal weights); `state`: a module-level line (a STATE dict)."""
    needs = {"panel": "sp500", "history": 60, "max_names": names, "rebalance": rebalance, "max_hold_sessions": 30}
    if rebalance == "weekly":
        needs["weekday"] = weekday
    body = body or ("    ids = [int(i) for i in ctx.ids[:ctx.params[\"names\"]]]\n"
                    "    return {\"target\": {i: 1.0 / len(ids) for i in ids}, \"at\": \"open\"}\n")
    return ("import math\n\nNEEDS = " + repr(needs) + "\nPARAMS = " + repr({"names": names, **params}) + "\n"
            + (state + "\n" if state else "") + "\n\ndef decide(ctx):\n" + body)


#: A program whose residual has an invented edge in every year (it passes the fake bar), and one with none.
def good(**params: Any) -> str:
    return program(edge=0.0012, sd=0.004, **params)


def flat(**params: Any) -> str:
    return program(edge=0.0, sd=0.004, **params)


#: An invented program that counts its calls in STATE: its targets change when STATE is emptied.
COUNTER_BODY = ("    STATE[\"n\"] = STATE.get(\"n\", 0) + 1\n"
                "    ids = [int(i) for i in ctx.ids]\n"
                "    start = STATE[\"n\"] % ctx.params[\"every\"]\n"
                "    picked = ids[start:start + 5]\n"
                "    return {\"target\": {i: 0.2 for i in picked}, \"at\": \"open\"}\n")


def counter(every: int, **params: Any) -> str:
    """A program with a call counter of period `every` in STATE (2, 4, 5, 10: the periods a naive reset keeps in phase
    with)."""
    return program(edge=0.0012, sd=0.004, every=int(every), body=COUNTER_BODY, state="STATE = {}", **params)


RAISES_BODY = "    raise ValueError(\"an invented failure\")\n"
#: A program that reads what STATE held before a restart: with STATE emptied it raises (no match with one that holds).
NEEDS_STATE_BODY = ("    if ctx.i == 0:\n"
                    "        STATE[\"first\"] = [int(i) for i in ctx.ids[:5]]\n"
                    "    return {\"target\": {i: 0.2 for i in STATE[\"first\"]}, \"at\": \"open\"}\n")


def _model(code: str, params: Mapping[str, Any] | None) -> dict[str, Any]:
    """The invented engine's reading of a program: its literal PARAMS under the version's own."""
    out: dict[str, Any] = {}
    for node in ast.parse(code).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and getattr(node.targets[0], "id", None) in (
                "PARAMS", "NEEDS"):
            out[node.targets[0].id] = ast.literal_eval(node.value)
    return {"needs": dict(out.get("NEEDS") or {}), **dict(out.get("PARAMS") or {}), **dict(params or {})}


def _days(first: dt.date, last: dt.date) -> list[dt.date]:
    return [day for day, _ in nyse_sessions(first, last)]


def _t(xs: Sequence[float]) -> float | None:
    """D15 by E1's expression (the mean over the sample sd, times the root of n), with `math.fsum`."""
    n = len(xs)
    if n < 2:
        return None
    mean = math.fsum(xs) / n
    sd = math.sqrt(math.fsum((x - mean) ** 2 for x in xs) / (n - 1))
    return mean / sd * math.sqrt(n) if sd >= 1e-12 else None


def _summary(daily: Sequence[Sequence[Any]], model: Mapping[str, Any], rebalances: int) -> dict[str, Any]:
    ix = {name: i for i, name in enumerate(xresults.DAILY)}
    x = [float(row[ix["x"]]) for row in daily]
    r = [float(row[ix["r"]]) for row in daily]
    shift = float(model.get("h1_shift") or 0.0)
    return {"days": len(daily), "invested_days": sum(1 for row in daily if row[ix["invested"]]),
            "rebalances": rebalances, "calls": rebalances, "lots": rebalances * 2, "closed": rebalances * 2,
            "round_trips": rebalances * 2, "pnl": round(1000.0 * math.fsum(r), 2), "fees": 1.0, "dividends": 0.0,
            "sum_r": math.fsum(r), "sum_x": math.fsum(x), "sum_x15": math.fsum(float(row[ix["x15"]]) for row in daily),
            "sum_u": math.fsum(float(row[ix["u"]]) for row in daily),
            "sum_bench": math.fsum(float(row[ix["bench"]]) for row in daily), "t_x": _t(x), "t_x_nw5": _t(x),
            "t_r": _t(r), "basket": "selection-led", "exposure_mean": float(model.get("invested", 1.0)),
            "names_mean": float(model.get("names", 5)), "turnover": 0.4, "cost_share": 0.1, "dilution": 0.9,
            "cells": {"small": 0, "under5": 0}, "vanished": {"deal": 1, "other": 0, "unknown": 0},
            "sum_x_h0": math.fsum(x), "sum_x_h1": math.fsum(x) + shift, "close_dates": rebalances,
            "sd_date_return": float(model.get("sd_date", 0.011))}


def _by_year(daily: Sequence[Sequence[Any]], every: int) -> dict[str, dict[str, Any]]:
    ix = {name: i for i, name in enumerate(xresults.DAILY)}
    rows: dict[str, list[Sequence[Any]]] = {}
    for row in daily:
        rows.setdefault(str(row[0])[:4], []).append(row)
    return {year: {"days": len(part), "sum_x": math.fsum(float(r[ix["x"]]) for r in part),
                   "sumsq_x": math.fsum(float(r[ix["x"]]) ** 2 for r in part),
                   "sum_x15": math.fsum(float(r[ix["x15"]]) for r in part),
                   "sum_r": math.fsum(float(r[ix["r"]]) for r in part), "rebalances": len(part) // every,
                   "closed": 2 * (len(part) // every)} for year, part in rows.items()}


class FakeRunner:
    """`league.xs.runner.Isolated` at its interface (the module docstring): `train`, `validation`, `look`, `segments`,
    each answering a `runner.Run`-shaped object (`result`, `slice`); every call kept in `calls`. `market` {year: a
    daily term} is added to the residual of a program whose PARAMS carry `mkt`; `fail` {window: an Exception} raises;
    `decider` is the panel kind's fake."""

    def __init__(self, *, market: Mapping[int, float] | None = None):
        self.calls: list[dict[str, Any]] = []
        self.market = dict(market or {})
        self.fail: dict[str, BaseException] = {}
        self.decider = FakeDecider()

    def needs(self, code: str, params: Any, *, name: str) -> dict[str, Any]:
        return dict(_model(code, params)["needs"])

    def _result(self, code: str, params: Any, *, name: str, window: str, first: dt.date, last: dt.date, k: float,
                half: int | None = None, placebos: int = 0, seed: int | None = None, calls: bool = False,
                style: bool = False, spans: Mapping[str, tuple[dt.date, dt.date]] | None = None) -> Any:
        self.calls.append({"window": window, "name": name, "start": first, "end": last, "k": float(k), "half": half,
                           "placebos": placebos, "seed": seed, "calls": calls, "style": style})
        if window in self.fail:
            raise self.fail[window]
        model = _model(code, params)
        status = str(model.get("status") or "ok")
        if isinstance(model.get("status_in"), Mapping):
            status = str(model["status_in"].get(window, status))
        sha = hashlib.sha256(json.dumps([code, dict(params or {})], sort_keys=True).encode()).hexdigest()
        every = 5 if model["needs"].get("rebalance") == "weekly" else 21
        days = _days(first, last) if status != "no_data" else []
        noise = random.Random(f"{model.get('seed', 0)}|{model.get('tag', '')}|{window}|{first}|{half}")
        sd = float(model.get("sd", 0.004))
        by_year = model.get("edge_by_year") if isinstance(model.get("edge_by_year"), Mapping) else {}
        by_window = model.get("edge_in") if isinstance(model.get("edge_in"), Mapping) else {}
        halves = model.get("half_edge")
        common = random.Random(f"common|{model.get('family_noise', '')}|{window}|{first}")
        share = float(model.get("common", 0.0))
        daily = []
        for i, day in enumerate(days):
            z = (noise.random() + noise.random() + noise.random() + noise.random() - 2.0) * math.sqrt(3.0)
            zc = (common.random() + common.random() + common.random() + common.random() - 2.0) * math.sqrt(3.0)
            edge = float(by_year.get(str(day.year), by_window.get(window, model.get("edge", 0.0))))
            if half is not None and isinstance(halves, (list, tuple)):
                edge = float(halves[half])
            x10 = edge + float(model.get("mkt", 0.0)) * float(self.market.get(day.year, 0.0)) \
                + sd * (share * zc + math.sqrt(max(0.0, 1.0 - share * share)) * z)
            drag = float(model.get("cost", 0.0002))
            x = x10 - (float(k) - 1.0) * 2.0 * drag
            bench = 0.0003
            invested = (i % 10) < round(10 * float(model.get("invested", 1.0)))
            daily.append([day.isoformat(), x + bench, x, x10 - drag, x + 0.3 * bench, 1.0 if invested else 0.0, bench,
                          1 if i % every == 0 else 0, bool(invested), 1000.0])
        rebalances = int(model.get("rebalances_span", len(days) // every))
        result: dict[str, Any] = {
            "run_id": f"xs-{sha[:10]}-{window}-{first}-{k:g}-{half}", "program": name, "program_sha": sha[:16],
            "run_sha": sha, "params": dict(params or {}), "window": window, "panel": "sp500", "half": half,
            "engine": XS_ENGINE_VERSION, "data_version": "fake", "capital": "1000", "k": float(k), "rung": "R0",
            "trials": 1, "status": status, "needs": dict(model["needs"]),
            "summary": _summary(daily, model, rebalances), "by_year": _by_year(daily, every), "daily": daily,
            "lots": [], "picks": [], "picks_sha": sha[:12], "factors": [], "runtime": {"seconds": 0.01},
            "start": days[0].isoformat() if days else None, "end": days[-1].isoformat() if days else None}
        leak = model.get("leak_day")
        if leak and window == "train":
            result["daily"] = [*daily, [str(leak), 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, False, 1000.0]]
        if status == "disqualified":
            result["reason"] = "25 errors"
        if placebos:
            result["placebo"] = self._placebo(model, daily, placebos, seed, spans or {"run": (first, last)}, window)
        if style:
            lean = model.get("style") if isinstance(model.get("style"), Mapping) else {}
            lots = int(model.get("lots", 30))
            result["style"] = None if model.get("style") == "missing" else {
                "lots": lots, "n": {c: lots for c in xstyle.CHARACTERISTICS},
                "weight": {c: 0.2 * lots for c in xstyle.CHARACTERISTICS},
                "sum": {c: 0.2 * lots * float(lean.get(c, 0.0)) for c in xstyle.CHARACTERISTICS}}
        if calls:
            result["calls"] = [{"t": i} for i in range(rebalances)]
        result["result_sha"] = hashlib.sha256(json.dumps(result, sort_keys=True, default=str).encode()).hexdigest()
        return SimpleNamespace(result=result, slice=SimpleNamespace(window=window, run_key=f"{sha}|{window}|{first}"))

    @staticmethod
    def _placebo(model: Mapping[str, Any], daily: Sequence[Sequence[Any]], n: int, seed: int | None,
                 spans: Mapping[str, tuple[dt.date, dt.date]], window: str) -> dict[str, Any]:
        """A placebo block of the documented shape: per span and draw the t, the sum and the sum of squares of an
        invented placebo residual (its mean the program's `placebo_edge`, default none)."""
        draw = random.Random(f"placebo|{seed}|{model.get('tag', '')}|{window}|{daily[0][0] if daily else ''}")
        sd = float(model.get("sd", 0.004))
        mean = float(model.get("placebo_edge", 0.0))
        out: dict[str, Any] = {"n": n, "rung": "R0", "seed": seed, "spans": {}, "reused": 0, "identity_share": 0.05}
        for name, (first, last) in spans.items():
            days = sum(1 for row in daily if first.isoformat() <= str(row[0]) <= last.isoformat())
            sums, squares, ts = [], [], []
            for _ in range(n):
                z = (draw.random() + draw.random() + draw.random() + draw.random() - 2.0) * math.sqrt(3.0)
                total = days * mean + sd * math.sqrt(max(days, 1)) * z
                square = (days - 1) * sd * sd + total * total / max(days, 1)
                sums.append(total)
                squares.append(square)
                ts.append((total / days) / sd * math.sqrt(days) if days > 1 else None)
            out["spans"][name] = {"days": days, "t": ts, "sum": sums, "sumsq": squares}
        return out

    def train(self, code: str, params: Any, *, name: str, start: dt.date, end: dt.date, k: float = 1.0,
              half: int | None = None, placebos: int = 0, calls: bool = False, style: bool = False) -> Any:
        for first, last in xconfig.TRAIN_SEGMENTS:
            if first <= start and end <= last:
                break
        else:
            raise AssertionError(f"a Train run asked outside one Train segment: {start}..{end}")
        return self._result(code, params, name=name, window="train", first=start, last=end, k=k, half=half,
                            placebos=placebos, seed=1, calls=calls, style=style)

    def segments(self, code: str, params: Any, *, name: str) -> list[Any]:
        return [self._result(code, params, name=name, window="train", first=first, last=last, k=1.0)
                for first, last in xconfig.TRAIN_SEGMENTS]

    def validation(self, code: str, params: Any, *, name: str, k: float = 1.0) -> Any:
        return self._result(code, params, name=name, window="validation", first=dt.date(2025, 1, 2),
                            last=dt.date(2025, 12, 31), k=k)

    def look(self, code: str, params: Any, *, name: str, gate: Any, k: float = 1.0, placebos: int, seed: int) -> Any:
        assert type(gate).__name__ == "EquityGateCapability", "the sealed look takes E1's own capability"
        spans = {"V": (dt.date(2025, 1, 2), dt.date(2025, 12, 31)), "H": (dt.date(2026, 1, 2), dt.date(2026, 10, 9))}
        return self._result(code, params, name=name, window="look", first=dt.date(2025, 1, 2),
                            last=dt.date(2026, 10, 9), k=k, placebos=placebos, seed=seed, spans=spans)


class FakeDecider:
    """The decider's panel kind in this process (`kind_load`, `kind` "decide", `kind_drop`): a load executes the
    invented program in a namespace of its own (so its STATE starts empty, as a fresh instance's does in the child); a
    decide calls its `decide` on the job's invented inputs and answers the child's shape ({hold, target (string keys,
    as JSON gives them), at, stats {calls, errors, disqualified}, failed}). `restart_after`, `reload_after`, `counts`,
    `fails`: what a test can make of the child (E2's fake's own knobs)."""

    def __init__(self) -> None:
        self.instances: dict[str, dict[str, Any]] = {}
        self.loads: list[str] = []
        self.decides = 0
        self.restarts = 0
        self.restart_after: int | None = None
        self.reload_after: int | None = None
        self.counts = True
        self.fails: BaseException | None = None

    def _fresh(self, key: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        space: dict[str, Any] = {}
        exec(compile(str(payload["code"]), f"<{key}>", "exec"), space)  # noqa: S102 - an invented test program
        params = {**dict(space.get("PARAMS") or {}), **dict(payload.get("params") or {})}
        self.instances[key] = {"space": space, "params": params, "payload": dict(payload), "calls": 0, "errors": 0,
                               "disqualified": None}
        return self.instances[key]

    def kind_load(self, kind: str, key: str, payload: Mapping[str, Any], *, budget_seconds: Any = None) -> dict:
        assert kind == "panel", kind
        instance = self._fresh(str(key), payload)
        self.loads.append(str(key))
        return {"needs": dict(instance["space"].get("NEEDS") or {}), "params": instance["params"]}

    def kind_drop(self, kind: str, key: str, *, budget_seconds: float = 10.0) -> None:
        assert kind == "panel", kind
        self.instances.pop(str(key), None)

    def kind(self, kind: str, op: str, payload: Mapping[str, Any], *, budget_seconds: Any = None) -> dict:
        assert (kind, op) == ("panel", "decide"), (kind, op)
        if self.fails is not None:
            raise self.fails
        if self.reload_after is not None and self.decides >= self.reload_after:
            self.reload_after = None
            for key, instance in list(self.instances.items()):
                self._fresh(key, instance["payload"])
        results: dict[str, Any] = {}
        for job in payload.get("jobs") or ():
            assert job.get("called") is True, "the restart check decides on CALLED decisions only"
            key = str(job["key"])
            instance = self.instances.get(key)
            if instance is None:
                results[key] = {"hold": True, "target": None, "stats": None, "missing": True, "failed": True}
                continue
            answer: Any = None
            failed = bool(instance["disqualified"])
            if not instance["disqualified"]:
                instance["calls"] += 1
                try:
                    answer = instance["space"]["decide"](SimpleNamespace(**dict(job["inputs"]),
                                                                         params=instance["params"]))
                except Exception:  # noqa: BLE001 - a failed decide is a hold and one error, as the runner counts it
                    failed = True
                    instance["errors"] += 1
                    if instance["errors"] >= int(instance["payload"].get("max_errors", 25)):
                        instance["disqualified"] = f"{instance['errors']} errors"
            stats = {"calls": instance["calls"], "errors": instance["errors"], "disqualified": instance["disqualified"]}
            target = answer.get("target") if isinstance(answer, Mapping) else None
            results[key] = {"hold": target is None, "at": answer.get("at") if isinstance(answer, Mapping) else None,
                            "target": json.loads(json.dumps({str(k): v for k, v in target.items()})) if target else
                            ({} if target == {} else None), "orders": [], "rejects": [], "ineligible": [],
                            "stats": stats if self.counts else {}, "ctx_sha": "fake", "failed": failed}
            self.decides += 1
        if self.restart_after is not None and self.decides >= self.restart_after:
            self.restarts += 1
            self.restart_after = None
        return {"ok": True, "results": results}


def state_stream(run: Any, calls: int = STATE_CALLS) -> Any:
    """`league.xs.runner.state_stream`, invented: `calls` called decisions of one seen span's k 1.5 run, each the same
    twelve slot ids and the call's index (no ctx is built: package C's `build` is not under test here)."""
    assert (getattr(run, "result", None) or {}).get("calls") is not None, "the restart check reads a run made with calls=True"
    for i in range(calls):
        yield {"i": i, "ids": [101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112], "positions": [], "n": 12}


# --------------------------------------------------------------------------------- league.xs's functions, to the contract
def pooled(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """`league.xs.results.pooled`: several runs at one k read as one (the sums added, T and the year rows from the
    concatenated daily x)."""
    ix = {name: i for i, name in enumerate(xresults.DAILY)}
    daily = [row for r in results for row in (r.get("daily") or [])]
    x = [float(row[ix["x"]]) for row in daily]
    r_ = [float(row[ix["r"]]) for row in daily]
    sums = [r.get("summary") or {} for r in results]
    by_year: dict[str, Any] = {}
    for r in results:
        by_year.update(r.get("by_year") or {})

    def total(key: str) -> Any:
        return sum(int(s.get(key) or 0) for s in sums)

    def mean(key: str) -> float | None:
        days = [(float(s.get(key) or 0.0), int(s.get("days") or 0)) for s in sums]
        n = sum(d for _, d in days)
        return math.fsum(v * d for v, d in days) / n if n else None

    return {"summary": {"days": len(daily), "invested_days": total("invested_days"), "rebalances": total("rebalances"),
                        "calls": total("calls"), "sum_x": math.fsum(x), "sum_r": math.fsum(r_), "t_x": _t(x),
                        "t_r": _t(r_), "names_mean": mean("names_mean"), "turnover": mean("turnover"),
                        "cost_share": mean("cost_share"), "exposure_mean": mean("exposure_mean"),
                        "vanished": {k: sum(int((s.get("vanished") or {}).get(k) or 0) for s in sums)
                                     for k in ("deal", "other", "unknown")},
                        "sum_x_h0": math.fsum(float(s.get("sum_x_h0") or 0.0) for s in sums),
                        "sum_x_h1": math.fsum(float(s.get("sum_x_h1") or 0.0) for s in sums),
                        "close_dates": total("close_dates"), "sd_date_return": 0.011},
            "by_year": by_year}


def view(result: Mapping[str, Any], window: str) -> dict[str, Any]:
    """`league.xs.results.view`: "train": `TRAIN_VIEW`; any other window: the status alone."""
    if window == "train":
        return {"status": result.get("status"), "summary": dict(result.get("summary") or {}),
                "by_year": dict(result.get("by_year") or {}), "pick_counts": {"decisions": 0},
                "runtime": dict(result.get("runtime") or {})}
    return {"status": result.get("status")}


def stat(blocks: Sequence[Mapping[str, Any]], span: str = "run") -> list[float]:
    """`league.xs.placebo.stat`: T per placebo index over several runs' blocks pooled from their sums."""
    rows = [block["spans"][span] for block in blocks]
    days = sum(int(row["days"]) for row in rows)
    out = []
    for m in range(min(len(row["sum"]) for row in rows)):
        total = math.fsum(float(row["sum"][m]) for row in rows)
        square = math.fsum(float(row["sumsq"][m]) for row in rows)
        var = (square - total * total / days) / (days - 1) if days > 1 else 0.0
        out.append((total / days) / math.sqrt(var) * math.sqrt(days) if var > 1e-24 else float("nan"))
    return out


def look_seed(receipt_sha256: str, code_sha256: str) -> int:
    text = xplacebo.LOOK_SEED.format(receipt=receipt_sha256, code=code_sha256)
    return int.from_bytes(hashlib.sha256(text.encode()).digest()[:16], "big")


def style_pooled(blocks: Sequence[Mapping[str, Any] | None]) -> dict[str, Any]:
    """`league.xs.style.pooled`: {"lots", "n", "loadings"}; a missing block makes the reading None-valued."""
    if not blocks or any(not isinstance(b, Mapping) for b in blocks):
        return {"lots": None, "n": {c: None for c in xstyle.CHARACTERISTICS},
                "loadings": {c: None for c in xstyle.CHARACTERISTICS}}
    weight = {c: math.fsum(float(b["weight"][c]) for b in blocks) for c in xstyle.CHARACTERISTICS}
    return {"lots": sum(int(b["lots"]) for b in blocks),
            "n": {c: sum(int(b["n"][c]) for b in blocks) for c in xstyle.CHARACTERISTICS},
            "loadings": {c: (math.fsum(float(b["sum"][c]) for b in blocks) / weight[c] if weight[c] else None)
                         for c in xstyle.CHARACTERISTICS}}


def style_open(reading: Mapping[str, Any] | None) -> dict[str, Any]:
    """`league.xs.style.style_open`: THE RULE on a pooled reading, under the module's own `TILT` and `MIN_LOTS`."""
    rule = {"tilt": xstyle.TILT, "min_lots": xstyle.MIN_LOTS}
    loadings = dict((reading or {}).get("loadings") or {}) if isinstance(reading, Mapping) else {}
    lots = (reading or {}).get("lots") if isinstance(reading, Mapping) else None
    values = [loadings.get(c) for c in xstyle.CHARACTERISTICS]
    if not isinstance(lots, int) or lots < xstyle.MIN_LOTS or any(
            not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
        return {"open": True, "why": xstyle.UNMEASURED, "tilts": [], "loadings": loadings, "lots": lots, "rule": rule}
    tilts = [[c, 1 if loadings[c] > 0 else -1] for c in xstyle.CHARACTERISTICS if abs(loadings[c]) >= xstyle.TILT]
    return {"open": bool(tilts), "why": xstyle.OPEN if tilts else None, "tilts": tilts, "loadings": loadings,
            "lots": lots, "rule": rule}


def seat_refusal(verdict: Mapping[str, Any] | None) -> str | None:
    """`league.xs.style.seat_refusal`: None only for a well-formed verdict that is not open under this rule."""
    if not isinstance(verdict, Mapping) or verdict.get("rule") != {"tilt": xstyle.TILT, "min_lots": xstyle.MIN_LOTS}:
        return f"{xstyle.OPEN}: {xstyle.UNMEASURED}"
    if verdict.get("open") is False:
        return None
    tilts = ", ".join(f"{c} {'+' if int(s) > 0 else '-'}" for c, s in (verdict.get("tilts") or []))
    return f"{xstyle.OPEN}: {tilts or verdict.get('why') or xstyle.UNMEASURED}"


def pinned_receipt(block: Mapping[str, Any] | None) -> Any:
    """`league.xs.screen.pinned_receipt`: the pin as a `ReceiptXS`, or None for nulls or a figure the pre-registration
    does not allow."""
    block = block if isinstance(block, Mapping) else {}
    sha = block.get("receipt_sha256")
    try:
        if not (isinstance(sha, str) and len(sha) == 64) or block.get("screen") != "XS1" \
                or float(block["alpha_plac"]) > xscreen.ALPHA_PLAC or int(block["placebo_draws"]) != xscreen.PLACEBO_DRAWS \
                or block.get("rung") not in xscreen.RUNGS or block.get("retry") is not False \
                or not isinstance(block.get("beside"), str):
            return None
        return xscreen.ReceiptXS(
            receipt_sha256=sha, c_XS=float(block["c_XS"]), c_margin=float(block["c_margin"]),
            alpha_plac=float(block["alpha_plac"]), placebo_draws=int(block["placebo_draws"]), rung=str(block["rung"]),
            fp_cap=float(block["fp_cap"]), owner_wall=float(block["owner_wall"]),
            validation_tries=int(block["validation_tries"]), holdout_looks=int(block["holdout_looks"]), retry=False,
            flags={k: tuple(v) for k, v in (block.get("flags") or {}).items()},
            screen_flags=tuple(block.get("screen_flags") or ()), beside=block["beside"], fp={})
    except (KeyError, TypeError, ValueError):
        return None


def series(result: Mapping[str, Any], column: str = "x") -> Any:
    """`league.xs.screen.series`: a run's daily series as E1's `Series` (r = the named column)."""
    import numpy as np

    ix = {name: i for i, name in enumerate(xresults.DAILY)}
    daily = result.get("daily")
    if not isinstance(daily, list) or not daily:
        raise ValueError("a result without its daily rows")
    values = [float(row[ix[column]]) for row in daily]
    if not all(math.isfinite(v) for v in values):
        raise ValueError("a value that is not finite")
    return xscreen.Series(days=np.array([ordinal(dt.date.fromisoformat(str(row[0]))) for row in daily], dtype=np.int32),
                          r=np.array(values, dtype=np.float64),
                          w=np.array([float(row[ix["w"]]) for row in daily], dtype=np.float64),
                          b=np.zeros(len(daily)), exits=np.array([int(row[ix["exits"]]) for row in daily]),
                          invested=np.array([bool(row[ix["invested"]]) for row in daily]))


def precheck(v: Any) -> dict[str, Any]:
    """`league.xs.screen.precheck`: (lots fully exited >= 20 or invested sessions >= 120) AND sum_V x > 1e-12."""
    trips, invested = int(sum(int(e) for e in v.exits)), int(sum(1 for i in v.invested if i))
    total = math.fsum(float(x) for x in v.r)
    checks = {"activity": trips >= xscreen.ACTIVITY_ROUND_TRIPS or invested >= xscreen.ACTIVITY_INVESTED_DAYS,
              "sum_positive": total > xscreen.ZERO}
    return {"passed": all(checks.values()), "round_trips": trips, "invested_days": invested, "sum": total,
            "sessions": len(v.r), "checks": checks}


class Screen:
    """What a test can make of the fake screen: `eligible` (the program floor), `c_p` (its own floor), `floors` (how
    often the floor was computed), `beside_fails` (the sentence cannot be filled)."""

    def __init__(self) -> None:
        self.eligible = True
        self.c_p = 0.80
        self.floors = 0
        self.verdicts = 0
        self.beside_fails = False

    def floor(self, segments: Sequence[Any], *, receipt: Any) -> dict[str, Any]:
        self.floors += 1
        assert len(segments) == len(xconfig.TRAIN_SEGMENTS), "one residual series a Train segment"
        k_p = int(round(self.c_p * 100))
        k_used = max(int(round(receipt.c_XS * 100)), k_p + int(round(receipt.c_margin * 100)))
        return {"screen": "XS1", "eligible": self.eligible, "why": None if self.eligible else "no floor cell",
                "method": "exact", "L": xscreen.H_LENGTH, "c_p": k_p / 100, "k_p": k_p, "c_used": k_used / 100,
                "k_used": k_used, "own_fp": 0.07, "fp_cap": receipt.fp_cap, "c_XS": receipt.c_XS,
                "c_margin": receipt.c_margin, "cells": {"both": {"pools": [len(s.r) for s in segments]}}}

    @staticmethod
    def floor_fits(program_floor: Any, receipt: Any) -> bool:
        return (isinstance(program_floor, Mapping) and program_floor.get("screen") == "XS1"
                and program_floor.get("fp_cap") == receipt.fp_cap and program_floor.get("c_XS") == receipt.c_XS
                and program_floor.get("c_margin") == receipt.c_margin and program_floor.get("L") == xscreen.H_LENGTH)

    def verdict(self, look_result: Mapping[str, Any], *, receipt: Any, program_floor: Mapping[str, Any],
                code_sha256: str, french: Any = None) -> dict[str, Any]:
        """`league.xs.screen.verdict`: THE GATE as the pre-registration writes it, on the look run's two windows:
        pre-check AND sum_H x > 1e-12 AND sum_H x15 > 1e-12 AND t_H >= c_used AND (1 + count) x 100 <= 12 x 1000."""
        self.verdicts += 1
        if receipt is None:
            raise xscreen.ScreenRefused("no pinned receipt")
        block = look_result.get("placebo") or {}
        assert block.get("seed") == look_seed(receipt.receipt_sha256, code_sha256), "the seed fixed before the look"
        ix = {name: i for i, name in enumerate(xresults.DAILY)}
        daily = look_result["daily"]
        v = [row for row in daily if str(row[0]) < "2026"]
        h = [row for row in daily if str(row[0]) >= "2026"]
        assert len(v) == xscreen.V_LENGTH and len(h) == xscreen.H_LENGTH, "the look's run is Validation, then the holdout"
        pre = precheck(series({"daily": v}))
        xh = [float(row[ix["x"]]) for row in h]
        t_h = _t(xh)
        sum_h, sum_h15 = math.fsum(xh), math.fsum(float(row[ix["x15"]]) for row in h)
        placebo_t = block["spans"]["H"]["t"]
        count = sum(1 for t in placebo_t if t is not None and t_h is not None and t >= t_h)
        c_used = float(program_floor["c_used"])
        checks = {"precheck": bool(pre["passed"]), "sum_h": sum_h > xscreen.ZERO, "sum_h15": sum_h15 > xscreen.ZERO,
                  "t_H": t_h is not None and t_h >= c_used,
                  "placebo": (1 + count) * 100 <= 12 * (len(placebo_t) + 1)}
        passed = all(checks.values())
        why = None if passed else next(name for name, held in checks.items() if not held)
        return {"screen": "XS1", "passed": passed, "why": why, "c_used": c_used, "c_p": program_floor["c_p"],
                "k_used": program_floor["k_used"], "t_H": t_h, "sum_h": sum_h, "sum_h15": sum_h15,
                "p_plac": (1 + count) / (len(placebo_t) + 1), "count": count, "n_placebo": len(placebo_t),
                "rung": receipt.rung, "own_fp": program_floor["own_fp"], "t_raw": t_h, "t_nw5": t_h,
                "basket": "selection-led", "label": xscreen.UNMEASURED, "loadings": {}, "identity_share": 0.05,
                "precheck": pre, "look": {"checks": checks}, "windows": {"ok": True},
                "flags": list(receipt.screen_flags), "receipt": receipt.receipt_sha256}

    def beside_line(self, result: Mapping[str, Any], receipt: Any, *, n_cell: int) -> str:
        if self.beside_fails:
            raise ValueError("a placeholder cannot be filled")
        return receipt.beside.format(c_used=f"{result['c_used']:.2f}", c_p=f"{result['c_p']:.2f}",
                                     own_fp=f"{100 * result['own_fp']:.1f}", n_cell=n_cell, basket=result["basket"],
                                     label=result["label"], flags=", ".join(result["flags"]) or "none")


def same_lineage(x: Any, u: Any, other_x: Any, other_u: Any, *, same_template: bool = False) -> bool:
    """`league.xs.screen.same_lineage`: the template, or E1's correlation test on the residuals OR on the universe
    excesses."""
    from league.equity import screen as E1

    return bool(same_template or E1.same_lineage(x, other_x) or E1.same_lineage(u, other_u))


class World:
    """What a test holds of the fakes for its life: `runner`, `screen`, `quiet` (why no run may start, or None), the
    xs identity's sha (`xs_sha`; None: it cannot be computed), the pin (`pin`: a block; `elane_xs.SCREEN_NULLS` for
    none), the universe's facts (`tradable`: the share of the day's members the constitution lists; `stale_days`)."""

    def __init__(self) -> None:
        self.runner = FakeRunner()
        self.screen = Screen()
        self.quiet: str | None = None
        self.quiet_asked: list[tuple[float, float]] = []
        self.xs_sha: str | None = "c" * 64
        self.pin: Mapping[str, Any] = pin_block()
        self.tradable = 1.0
        self.stale_days = 0

    def fingerprint(self, repo: Any = None) -> str:
        if self.xs_sha is None:
            raise FileNotFoundError("an xs evidence file is missing")
        return self.xs_sha

    def ask_quiet(self, now: float, need_s: float) -> str | None:
        self.quiet_asked.append((float(now), float(need_s)))
        return self.quiet


def _universe(world: World) -> Any:
    class Universe:
        def __init__(self, root: Any):
            self.root = root

        def members(self, day: dt.date) -> list[tuple[int, str]]:
            return [(100 + i, f"S{i:03d}") for i in range(500)]

        def tradable(self, day: dt.date) -> set[str]:
            return {f"S{i:03d}" for i in range(int(round(500 * world.tradable)))}

        def stale_days(self, day: dt.date) -> int:
            return int(world.stale_days)

    return Universe


_FAMILIES = SwarmStore.families
_ADD = SwarmStore.add_family


def _families(self: SwarmStore, *, alive: bool | None = None, lanes: Any = None) -> list[dict[str, Any]]:
    """`SwarmStore.families` as patch 1 leaves it (the unpatched tree's stand-in): an equity family is one whose
    structure is an equity structure, the panel's among them."""
    fams = _FAMILIES(self, alive=alive, lanes="all")
    if lanes == "all":
        return fams
    equity = [f for f in fams if f.get("structure") in store_mod.EQUITY_STRUCTURES]
    if lanes is None:
        return [f for f in fams if f.get("structure") not in store_mod.EQUITY_STRUCTURES]
    wanted = {lanes} if isinstance(lanes, str) else set(lanes)
    return [f for f in equity if (f.get("spec") or {}).get("lane") in wanted]


def _add_family(self: SwarmStore, spec: Mapping[str, Any], **kw: Any) -> dict[str, Any]:
    """`SwarmStore.add_family` as patch 1 leaves it (the unpatched tree's stand-in): a panel family names no root."""
    if spec.get("structure") != "panel" or spec.get("roots"):
        return _ADD(self, spec, **kw)
    fam = _ADD(self, {**dict(spec), "roots": ["PANEL"]}, **kw)
    body = {**dict(fam["spec"]), "roots": []}
    self._exec("UPDATE families SET roots=?, spec=? WHERE id=?", ("[]", store_mod.dumps(body), fam["id"]))
    return self.family(fam["id"])  # type: ignore[return-value]


def _members(store: Any, fid: str) -> list[str]:
    """`elane._members` as patch 4 leaves it (the unpatched tree's stand-in): every equity structure's families."""
    row = store._one("SELECT lineage FROM families WHERE id=?", (str(fid),))
    lines = store._connected_lineages(row["lineage"]) if row is not None else []
    if not lines:
        return []
    marks = ",".join("?" * len(store_mod.EQUITY_STRUCTURES))
    return [r["id"] for r in store._all(f"SELECT id FROM families WHERE lineage IN ({','.join('?' * len(lines))}) "
                                        f"AND structure IN ({marks})", (*lines, *store_mod.EQUITY_STRUCTURES))]


def switch_on(case: Any, world: World | None = None) -> World:
    """Install the fakes for the life of `case` (the module docstring) and return the test's `World`."""
    world = world or World()
    patches = [
        mock.patch.object(xconfig, "quiet", world.ask_quiet),
        mock.patch.object(xresults, "pooled", pooled), mock.patch.object(xresults, "view", view),
        mock.patch.object(xplacebo, "stat", stat), mock.patch.object(xplacebo, "look_seed", look_seed),
        mock.patch.object(xstyle, "pooled", style_pooled), mock.patch.object(xstyle, "style_open", style_open),
        mock.patch.object(xstyle, "seat_refusal", seat_refusal),
        mock.patch.object(xscreen, "pinned_receipt", pinned_receipt), mock.patch.object(xscreen, "series", series),
        mock.patch.object(xscreen, "precheck", precheck), mock.patch.object(xscreen, "floor", world.screen.floor),
        mock.patch.object(xscreen, "floor_fits", world.screen.floor_fits),
        mock.patch.object(xscreen, "verdict", world.screen.verdict),
        mock.patch.object(xscreen, "beside_line", world.screen.beside_line),
        mock.patch.object(xscreen, "same_lineage", same_lineage),
        mock.patch.object(xidentity, "xs_fingerprint", world.fingerprint),
        mock.patch.object(xidentity, "xs_identity", lambda: {"xs": world.fingerprint(), "engine": XS_ENGINE_VERSION}),
        mock.patch.object(xrunner, "state_stream", state_stream),
        mock.patch.object(xstore, "Universe", _universe(world)),
        mock.patch.object(elane_xs, "pin", lambda policy=None: world.pin),
        mock.patch.object(elane, "REPO", NO_DOCS),
    ]
    if not PATCHED:
        patches += [
            mock.patch.object(store_mod, "EQUITY_STRUCTURES", (*store_mod.EQUITY_STRUCTURES, "panel")),
            mock.patch.object(SwarmStore, "families", _families),
            mock.patch.object(SwarmStore, "add_family", _add_family),
            mock.patch.object(elane, "_members", _members),
        ]
    for p in patches:
        p.start()
        case.addCleanup(p.stop)
    with elane_xs._cache_lock:
        elane_xs._mode_cache.clear()
        elane_xs._json_cache.clear()
    return world


# ------------------------------------------------------------------------------------------- the state root's files
def new_store(case: Any, clock: Clock | None = None) -> SwarmStore:
    tmp = tempfile.TemporaryDirectory()
    case.addCleanup(tmp.cleanup)
    store = SwarmStore(tmp.name, clock=clock or Clock())
    case.addCleanup(store.close)
    return store


def write_manifest(root: Any, **over: Any) -> dict[str, Any]:
    """panel/PANEL_MANIFEST.json under the state root's daily store, as the layout has it (counts and verdicts only),
    and E1's GATE mark beside (so E1's own capability can be minted on it)."""
    doc = {"version": "xs-panel-v1", "fetched_through": "2026-10-09", "full_at": "2026-10-09", "sha256": {},
           "vintage": {}, "coverage": {str(y): {"member_days": 100, "with_bar": 99, "share": 0.99}
                                       for y in (*xconfig.HISTORY_YEARS, *xconfig.TRAIN_YEARS, 2025, 2026)},
           "train_years_ok": list(xconfig.TRAIN_YEARS), "verdict": "ok", "vanished": [], "audit": {},
           "i6": {"day": "2026-10-09", "equal": True, "source": "fetch", "live": {}}, "revisions": 0,
           "hs_share": 0.95, "live_from": None}
    doc.update(over)
    base = Path(root) / elane_xs.STORE_DIR
    (base / "panel").mkdir(parents=True, exist_ok=True)
    (base / elane_xs.PANEL_MANIFEST).write_text(json.dumps(doc))
    (base / GATE_MARK).write_text("the House's equity store (a test's)\n")
    with elane_xs._cache_lock:
        elane_xs._mode_cache.clear()
    return doc


def write_twins(root: Any, *, through: str = "2026-10-09", instances: Mapping[str, Any] | None = None,
                version: str | None = None) -> None:
    """The twin marker (package J's file): ids and days only."""
    from league.xs import book

    doc = {"version": version or book.TWINS_VERSION, "through": through, "at": "2026-10-10T01:00:00Z",
           "instances": dict(instances or {})}
    base = Path(root) / elane_xs.STORE_DIR
    base.mkdir(parents=True, exist_ok=True)
    (base / book.TWINS_FILE).write_text(json.dumps(doc))
    with elane_xs._cache_lock:
        elane_xs._mode_cache.clear()


def write_probe(root: Any, route: str = ROUTE, *, strata: Sequence[str] = elane_xs.PROBE_STRATA,
                published: bool = True) -> None:
    """The contamination probe's file (release E3's shape: aggregates only), with the panel strata for `route`."""
    cell = {"n": 40, "correct": 21, "acc": 0.52, "base": 0.55, "p_perm": 0.6, "readable": True, "recalled": False}
    row: dict[str, Any] = {"model": "fake-model", "usd": 0.5, "probes": 1,
                           "cells": {s: {"2016-24": dict(cell), "2025": dict(cell)} for s in ("S1", *strata)}}
    if published:
        row["at"] = "2026-10-10T00:20:00Z"
    (Path(root) / elane_xs.PROBE_FILE).write_text(json.dumps({"version": "contam-1", "routes": {route: row},
                                                               "history": []}))


def ready(root: Any, **manifest: Any) -> None:
    """A state root on which the panel lane can reach "live": the manifest with the universe deploy in force, the
    twin marker and the probe's file."""
    write_manifest(root, **{"live_from": "2026-09-01", **manifest})
    write_twins(root)
    write_probe(root)


# --------------------------------------------------------------------------------------------------------- families
CARD = {"lane": "equity", "structure": "panel", "panel": "sp500", "max_names": 5, "rebalance": "weekly", "weekday": 0,
        "hypothesis": "Liquidity providers are paid to absorb a week's selling in single names, and the names that "
                      "fell most against their sector rebound (an invented test card; Lehmann 1990).",
        "mechanism_class": "reversal_liquidity", "inputs": ["underlying_price", "cross_asset"], "holding": "days_4_10",
        "cost": {"hurdle": 0.0006, "why": "two half-spreads and the sell fees on a liquid large-cap name"},
        "comparison": "matched random portfolios from the same cells on the same days",
        "falsification": "the residual's sum at or below zero at 1.5x the half-spread over the seen Train years"}


def card(**over: Any) -> dict[str, Any]:
    return {**CARD, **over}


def panel_family(store: SwarmStore, slug: str, *, agenda: str = "xs_reversal", code: str | None = None,
                 hidden: int | None = None, route: str = ROUTE, names: int = 5, rebalance: str = "weekly",
                 mechanism: str | None = None, parent: str | None = None,
                 record: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """A panel family as the panel's admission bears it (its spec), with a v1 when `code` is given."""
    spec = {"id": slug, "mechanism": mechanism or f"Invented mechanism {slug}: liquidity providers are paid to absorb "
                                                  "a week's selling in single names.",
            "structure": "panel", "roots": [], "lane": "equity", "agenda": agenda, "panel": "sp500",
            "max_names": names, "rebalance": rebalance, "weekday": 0 if rebalance == "weekly" else None,
            "e2_route": route, "hidden_year": hidden, "gid": "g0"}
    fam = store.add_family(spec, origin="architect", parent=parent)
    if code is not None:
        store.add_version(fam["id"], code, {}, author="architect:test")
    store.set_state(fam["id"], **{elane_xs.STATE_KEY: dict(record or {"status": "researching", "versions": {}})})
    return store.family(fam["id"])  # type: ignore[return-value]


def owner(store: SwarmStore, world: World, settings_: Mapping[str, Any], *, router: Any = None,
          clock: Any = None) -> Any:
    """What `elane_xs` is handed for a researcher, a tournament or a gate: the store, the settings, a clock, the root
    and the test's panel runner."""
    return SimpleNamespace(store=store, settings=settings_, clock=clock or store.clock, root=store.root,
                           xs_runner=world.runner, router=router)


def reviewed(store: SwarmStore, fid: str, n: int = 1) -> None:
    """The review record a panel look reads for version `n` (E1's shape, under the panel rubric), and the panel
    record's pass."""
    from league.swarm import elane_review
    from league.swarm.gate import run_sha

    sha = run_sha(store.version(fid, n))
    held = {**elane_review.record(sha, {"model": "pro_balanced", "route": "sail:pro_balanced"},
                                  {"model": "k3_balanced", "route": "sail:k3_balanced"}, at=store.now(), version=n),
            "objective": elane_xs.REVIEW_OBJECTIVE, "source": "elane_xs", "rubric": elane_xs.rubric_sha()}
    store.set_state(fid, review=held)
    rec = elane_xs.record_of(store.family(fid))
    rec.update(status="passed", passed_version=n, passed_review=held)
    store.set_state(fid, **{elane_xs.STATE_KEY: rec})


__all__ = ["PATCHED", "HOLDS", "NO_DOCS", "FAKE_SHA", "FAKE_BESIDE", "STATE_CALLS", "ROUTE", "pin_block", "settings",
           "program", "good", "flat", "counter", "COUNTER_BODY", "RAISES_BODY", "NEEDS_STATE_BODY", "FakeRunner",
           "FakeDecider", "state_stream", "pooled", "view", "stat", "look_seed", "style_pooled", "style_open",
           "seat_refusal", "pinned_receipt", "series", "precheck", "Screen", "same_lineage", "World", "switch_on",
           "new_store", "write_manifest", "write_twins", "write_probe", "ready", "CARD", "card", "panel_family",
           "owner", "reviewed", "Clock"]
