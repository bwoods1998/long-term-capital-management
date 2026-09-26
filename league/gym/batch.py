"""The batch runner: many programs over one window, day-major, across N worker processes on a box.

    python -m league.gym.batch --programs DIR --window train --roots SPY,QQQ --out FILE
        [--store /data/store] [--workers 8] [--split 1] [--stress 1.0] [--capital 10000]
        [--start YYYY-MM-DD] [--end YYYY-MM-DD] [--fill-model PATH] [--detail full|summary]
        [--gate REASON] [--check]

DIR holds programs as `*.py`; a `<name>.json` beside one holds its parameter overrides, one dict or
a list of dicts (each a separate run: a trial). Each worker takes a share of the programs and runs
them together, loading each day's chain once. `--split N` also cuts the window into N consecutive
segments run in parallel and merged per program (the inner loop's latency: one program over three
years on eight cores); positions still open at a segment's end close there, so split and unsplit
runs differ slightly, and each is deterministic.

The output (FILE, JSON): {"batch": {...the run's settings, trials, program-years, seconds...},
"results": [one result per (program, parameters), in DIR's order; a program the safety check
refuses gets {"status": "refused", "reason": ...}]}.

Exit codes: 0 done; 2 bad arguments or no programs; 3 the store lacks the data (the message names
it: the box is missing data); 4 a sealed window without the gate. `--check` only reports what the
store holds for the window and roots (exit 3 when a root has no day).

The holdout and forward windows open only with `--gate REASON` on a store with the gate's mark.
Runs under PYTHONHASHSEED=0 (the CLI re-executes itself to set it), so even a program that iterates
a set of strings is reproducible from one invocation to the next.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import multiprocessing
import os
import sys
import time
from pathlib import Path
from typing import Any, Sequence

from . import ENGINE_VERSION

EXIT_OK, EXIT_USAGE, EXIT_MISSING, EXIT_SEALED = 0, 2, 3, 4


def find_programs(directory: str | os.PathLike) -> list[tuple[str, str, dict]]:
    """[(name, code, params)] from DIR: each *.py, once per parameter set in its *.json (if any)."""
    root = Path(directory)
    jobs = []
    for path in sorted(root.glob("*.py")):
        code = path.read_text()
        sets: list[dict] = [{}]
        side = path.with_suffix(".json")
        if side.is_file():
            loaded = json.loads(side.read_text())
            sets = loaded if isinstance(loaded, list) else [loaded]
        for i, params in enumerate(sets):
            name = path.stem if len(sets) == 1 else f"{path.stem}#{i}"
            jobs.append((name, code, dict(params or {})))
    return jobs


def _segments(days: Sequence[dt.date], n: int) -> list[tuple[dt.date, dt.date]]:
    n = max(1, min(int(n), len(days)))
    size = math.ceil(len(days) / n)
    return [(days[i], days[min(i + size, len(days)) - 1]) for i in range(0, len(days), size)]


def _chunks(items: Sequence[Any], n: int) -> list[list[Any]]:
    n = max(1, min(int(n), len(items)))
    return [list(items[i::n]) for i in range(n)]


def _unit(args: tuple) -> list[tuple[int, int, dict]]:
    """One worker's share: a list of (job index, program) over one segment, run together."""
    store_root, gate_reason, cfg_kw, seg_index, segment, jobs, detail = args
    _cap_memory()
    import pyarrow

    pyarrow.set_cpu_count(1)          # N workers already use the cores; no thread pools on top
    pyarrow.set_io_thread_count(1)
    from . import engine as E
    from . import fills as F
    from .runtime import load_program
    from .store import Store, mint_gate_capability

    gate = mint_gate_capability(store_root, gate_reason) if gate_reason else None
    store = Store(store_root, gate=gate)
    model = F.FillModel.load(cfg_kw.pop("fill_model_path")) if cfg_kw.get("fill_model_path") else F.FillModel.load()
    cfg_kw.pop("fill_model_path", None)
    cfg = E.RunConfig(fill_model=model, start=segment[0], end=segment[1], **cfg_kw)
    programs = [load_program(code, name=name, params=params) for _, (name, code, params) in jobs]
    results = E.run(programs, store, cfg)
    return [(job_index, seg_index, result) for (job_index, _), result in zip(jobs, results)]


def _cap_memory() -> None:
    """A worker's address space is capped (GYM_WORKER_MEMORY_GB, default 6): a program that allocates
    without end meets a MemoryError it is charged for, not the box's OOM killer."""
    try:
        import resource

        limit = int(float(os.environ.get("GYM_WORKER_MEMORY_GB", "6")) * (1 << 30))
        soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        if hard == resource.RLIM_INFINITY or hard > limit:
            resource.setrlimit(resource.RLIMIT_AS, (limit, hard if hard != resource.RLIM_INFINITY else resource.RLIM_INFINITY))
    except (ImportError, ValueError, OSError):  # pragma: no cover - not every platform has it
        pass


def _failed(unit: tuple, why: str) -> list[tuple[int, int, dict]]:
    """A unit whose worker died: each of its programs gets an error result (no trial is counted)."""
    return [(job_index, unit[3], {"program": job[0], "status": "error", "reason": why[:500], "trials": 0,
                                  "summary": {}, "fills": {}, "daily": [], "trades": [], "data_version": "",
                                  "runtime": {"calls": 0, "errors": 0, "timeouts": 0, "messages": [why[:200]], "disqualified": None}})
            for job_index, job in unit[5]]


def _trim(result: dict, detail: str) -> dict:
    if detail == "summary":
        return {k: v for k, v in result.items() if k not in ("trades", "daily")}
    return result


def run_batch(jobs: Sequence[tuple[str, str, dict]], *, store_root: str, window: str, roots: Sequence[str], workers: int = 1,
              split: int = 1, stress: float = 1.0, capital: float = 10_000.0, start: dt.date | None = None,
              end: dt.date | None = None, fill_model_path: str | None = None, gate_reason: str | None = None,
              detail: str = "full") -> dict:
    """Run the jobs and return the output document (the module docstring)."""
    from . import results as R
    from .runtime import CodeRefused, load_program
    from .store import Store, mint_gate_capability

    began = time.time()
    gate = mint_gate_capability(store_root, gate_reason) if gate_reason else None
    store = Store(store_root, gate=gate)
    roots = tuple(r.upper() for r in roots)
    days = [d for d in store.days(window, [], start=start, end=end) if any(store.has("nbbo", r, d) for r in roots)]
    out: list[dict | None] = [None] * len(jobs)
    valid = []
    for i, (name, code, params) in enumerate(jobs):
        try:
            load_program(code, name=name, params=params)
            valid.append((i, (name, code, params)))
        except CodeRefused as exc:
            out[i] = {"program": name, "status": "refused", "reason": str(exc), "trials": 0}
    segments = _segments(days, split) if days else [(start, end)]
    cfg_kw = {"window": window, "roots": roots, "stress": float(stress), "capital": float(capital), "fill_model_path": fill_model_path}
    per_segment = max(1, math.ceil(max(1, workers) / len(segments)))
    units = [(store_root, gate_reason, dict(cfg_kw), s, seg, chunk, detail)
             for s, seg in enumerate(segments) for chunk in _chunks(valid, per_segment) if chunk]
    parts: dict[int, dict[int, dict]] = {}
    produced: list[tuple[int, int, dict]] = []
    if workers <= 1 or len(units) <= 1:
        for unit in units:
            try:
                produced += _unit(unit)
            except Exception as exc:  # the engine itself failed on this unit: say so, keep the rest
                produced += _failed(unit, f"{type(exc).__name__}: {exc}")
    else:
        from concurrent.futures import ProcessPoolExecutor

        methods = multiprocessing.get_all_start_methods()
        ctx = multiprocessing.get_context("forkserver" if "forkserver" in methods else "spawn")
        with ProcessPoolExecutor(max_workers=min(workers, len(units)), mp_context=ctx) as pool:
            futures = [(unit, pool.submit(_unit, unit)) for unit in units]
            for unit, future in futures:
                try:
                    produced += future.result()
                except Exception as exc:  # a worker died (BrokenProcessPool) or the engine failed
                    produced += _failed(unit, f"{type(exc).__name__}: {exc}")
    for job_index, seg_index, result in produced:
        parts.setdefault(job_index, {})[seg_index] = result
    for job_index, by_segment in parts.items():
        pieces = [by_segment[s] for s in sorted(by_segment)]
        broken = [p for p in pieces if p.get("status") == "error"]
        out[job_index] = broken[0] if broken else _trim(R.merge(pieces), detail)
    finished = [r for r in out if r is not None]
    program_years = sum(len(r.get("daily") or []) / 252.0 * max(1, len(r.get("roots") or [])) for r in finished
                        if r.get("status") != "refused") if detail == "full" else \
        sum((r.get("summary") or {}).get("days", 0) / 252.0 * max(1, len(r.get("roots") or [])) for r in finished
            if r.get("status") != "refused")
    seconds = time.time() - began
    return {"batch": {"engine": ENGINE_VERSION, "store": str(store_root), "window": window, "roots": list(roots),
                      "days": len(days), "first_day": days[0].isoformat() if days else None,
                      "last_day": days[-1].isoformat() if days else None, "workers": workers, "split": split,
                      "stress": stress, "capital": capital, "programs": len(jobs),
                      "trials": sum(r.get("trials", 0) for r in finished), "program_years": round(program_years, 3),
                      "seconds": round(seconds, 2),
                      "program_years_an_hour": round(program_years / seconds * 3600.0, 1) if seconds > 0 else None,
                      "gate": bool(gate_reason)},
            "results": out}


def _date(text: str | None) -> dt.date | None:
    return dt.date.fromisoformat(text) if text else None


def main(argv: Sequence[str] | None = None) -> int:
    from .store import MissingData, Store, StoreRefused, describe, mint_gate_capability

    parser = argparse.ArgumentParser(prog="python -m league.gym.batch", description="Run Gym programs over a window.")
    parser.add_argument("--programs", help="directory of *.py programs (and *.json parameter sets)")
    parser.add_argument("--window", required=True, choices=("train", "validation", "holdout", "forward"))
    parser.add_argument("--roots", required=True, help="comma-separated option roots, e.g. SPY,QQQ")
    parser.add_argument("--out", help="output JSON file")
    parser.add_argument("--store", default="/data/store")
    parser.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    parser.add_argument("--split", type=int, default=1)
    parser.add_argument("--stress", type=float, default=1.0)
    parser.add_argument("--capital", type=float, default=10_000.0)
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--fill-model")
    parser.add_argument("--detail", choices=("full", "summary"), default="full")
    parser.add_argument("--gate", help="the gate's reason for opening sealed days (the store must carry its mark)")
    parser.add_argument("--check", action="store_true", help="only report what the store holds")
    args = parser.parse_args(argv)
    roots = [r.strip().upper() for r in args.roots.split(",") if r.strip()]
    try:
        gate = mint_gate_capability(args.store, args.gate) if args.gate else None
        store = Store(args.store, gate=gate)
        if args.check:
            report = describe(store, args.window, roots)
            print(json.dumps(report, sort_keys=True))
            missing = [r for r, row in report["roots"].items() if not row["nbbo"] or not row["underlying"]]
            if missing:
                print(f"the box is missing data: no {args.window} days for {', '.join(missing)} in {args.store}", file=sys.stderr)
                return EXIT_MISSING
            return EXIT_OK
        if not args.programs or not args.out:
            parser.error("--programs and --out are required (or --check)")
        jobs = find_programs(args.programs)
        if not jobs:
            print(f"no programs (*.py) in {args.programs}", file=sys.stderr)
            return EXIT_USAGE
        missing = [r for r in roots if not store.days(args.window, [r], start=_date(args.start), end=_date(args.end))]
        if missing:
            print(f"the box is missing data: no {args.window} days for {', '.join(missing)} in {args.store}", file=sys.stderr)
            return EXIT_MISSING
        doc = run_batch(jobs, store_root=args.store, window=args.window, roots=roots, workers=args.workers, split=args.split,
                        stress=args.stress, capital=args.capital, start=_date(args.start), end=_date(args.end),
                        fill_model_path=args.fill_model, gate_reason=args.gate, detail=args.detail)
    except StoreRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return EXIT_SEALED
    except MissingData as exc:
        print(f"the box is missing data: {exc}", file=sys.stderr)
        return EXIT_MISSING
    tmp = Path(args.out + ".part")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(json.dumps(doc, sort_keys=True, default=str))
    tmp.replace(args.out)
    b = doc["batch"]
    print(json.dumps({"trials": b["trials"], "program_years": b["program_years"], "seconds": b["seconds"],
                      "program_years_an_hour": b["program_years_an_hour"], "out": args.out}))
    return EXIT_OK


if __name__ == "__main__":
    if os.environ.get("PYTHONHASHSEED") != "0":
        env = dict(os.environ, PYTHONHASHSEED="0")
        os.execve(sys.executable, [sys.executable, "-m", "league.gym.batch", *sys.argv[1:]], env)
    sys.exit(main())
