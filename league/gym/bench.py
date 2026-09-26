"""Measure the Gym's speed on a store: python -m league.gym.bench --store PATH --roots SPY [--window train]

Prints JSON: the chain load time per root-day; seconds per program-day and per program-year (252
days) for each benchmark program run ALONE on one core (loads included: the "one program over one
year of one underlying" target); and a day-major batch of `--batch` programs on one core
(program-years an hour a core, the Gym's throughput per core). Extrapolations are labelled as such.
The programs are generic workloads (a light cadence-10 program, the two examples, and a heavy one
that reads every greek every minute and trades often); none of them is fitted to anything.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import time
from pathlib import Path

from . import engine as E
from .runtime import load_program
from .store import Store

EXAMPLES = Path(__file__).resolve().parent / "examples"

HEAVY = '''
import numpy as np
NEEDS = {"roots": ["ROOT"], "dte": [0, 3], "band": 0.03, "cadence": 1, "history": 20}
PARAMS = {"every": 30, "hold": 20}
STATE = {"n": 0}
def decide(ctx):
    ch = ctx.chain
    STATE["n"] += 1
    skew = float(np.nanmean(ch.iv[~ch.is_call])) - float(np.nanmean(ch.iv[ch.is_call])) if ch.n else 0.0
    g = float(np.nansum(np.abs(ch.gamma * ch.oi))) + float(np.nansum(ch.theta)) + float(np.nansum(ch.vega)) + skew
    out = [{"close": p["id"]} for p in ctx.positions if p["held_minutes"] >= ctx.params["hold"]]
    if STATE["n"] % ctx.params["every"] == 0 and ctx.minute < 890 and len(ctx.positions) < 3 and ch.n and g == g:
        dte = int(ch.expiries[0])
        out.append({"open": "iron_condor", "legs": [
            {"side": "long", "right": "P", "rel": 1, "offset": -2.0}, {"side": "short", "right": "P", "dte": dte, "delta": 0.2},
            {"side": "short", "right": "C", "dte": dte, "delta": 0.2}, {"side": "long", "right": "C", "rel": 2, "offset": 2.0}],
            "max_loss": 300, "limit": "natural", "tif": 3})
    return out
'''

LIGHT = '''
NEEDS = {"roots": ["ROOT"], "dte": [0, 1], "band": 0.02, "cadence": 10}
PARAMS = {}
def decide(ctx):
    out = [{"close": p["id"]} for p in ctx.positions if p["held_minutes"] >= 60]
    if not ctx.positions and 600 <= ctx.minute < 880 and ctx.chain.n:
        out.append({"open": "debit_vertical", "legs": [{"side": "long", "right": "C", "dte": 0, "atm": 0},
                    {"side": "short", "right": "C", "rel": 0, "offset": 2.0}], "qty": 1})
    return out
'''


def programs_for(root: str) -> dict[str, str]:
    swap = lambda code: code.replace('"roots": ["SPY"]', f'"roots": ["{root}"]').replace("ROOT", root)  # noqa: E731
    return {"light": swap(LIGHT), "condor_vrp": swap((EXAMPLES / "condor_vrp.py").read_text()),
            "putspread_dip": swap((EXAMPLES / "putspread_dip.py").read_text()), "heavy": swap(HEAVY)}


def measure(store_root: str, roots: list[str], window: str, batch: int) -> dict:
    store = Store(store_root)
    out: dict = {"store": store_root, "window": window, "roots": roots, "measured_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    for root in roots:
        days = store.days(window, [root])
        began = time.perf_counter()
        for day in days:
            store.chain(root, day)
        load = (time.perf_counter() - began) / max(1, len(days))
        row: dict = {"days": len(days), "load_s_per_root_day": round(load, 4), "alone": {}}
        progs = programs_for(root)
        for name, code in progs.items():
            program = load_program(code, name=name)
            began = time.perf_counter()
            [result] = E.run([program], store, E.RunConfig(window=window, roots=(root,)))
            spent = time.perf_counter() - began
            per_day = spent / max(1, len(days))
            row["alone"][name] = {"seconds": round(spent, 3), "s_per_program_day": round(per_day, 4),
                                  "s_per_program_year_extrapolated": round(per_day * 252, 1),
                                  "trades": result["summary"]["trades"], "calls": result["runtime"]["calls"],
                                  "decide_seconds": result["runtime"]["decide_seconds"], "status": result["status"]}
        mix = [load_program(code, name=f"{name}-{i}", params={}) for i in range(max(1, batch // len(progs))) for name, code in progs.items()]
        began = time.perf_counter()
        E.run(mix, store, E.RunConfig(window=window, roots=(root,)))
        spent = time.perf_counter() - began
        program_years = len(mix) * len(days) / 252.0
        row["batch_one_core"] = {"programs": len(mix), "seconds": round(spent, 2), "program_years": round(program_years, 3),
                                 "program_years_an_hour_a_core": round(program_years / spent * 3600.0, 1),
                                 "s_per_program_year": round(spent / program_years, 1)}
        out[root] = row
    return out


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m league.gym.bench")
    parser.add_argument("--store", required=True)
    parser.add_argument("--roots", default="SPY")
    parser.add_argument("--window", default="train")
    parser.add_argument("--batch", type=int, default=16)
    args = parser.parse_args()
    print(json.dumps(measure(args.store, [r.strip().upper() for r in args.roots.split(",")], args.window, args.batch), indent=1))


if __name__ == "__main__":
    main()
