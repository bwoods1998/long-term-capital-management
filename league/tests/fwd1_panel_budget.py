"""THE FORWARD SCREEN'S PANEL RUNS AT THE REAL PANEL'S SIZE, under the ops child's own address-space limit (the House
review's major: each panel call opened its own copy of the panel store and the ops child ran out of memory at the
third; `league/tests/test_forward_screen.py` `TheJobFitsItsMemory` drives it). Not a test module: the made-up store,
and the child that makes the job's panel runs on it.

THE STORE (`build`): `league.xs.synth.synthetic_panel` at the production panel's shape (505 members a day with 5% of
churn a year from 2016, through mid-December 2026 so the forward days exist: about 2,750 sessions by 767 columns, the
two bar arrays about 135 MB on disk), invented prices, and a forward record holding ONE registered panel program
(invented: league/tests/test_forward_xs.py's `CODE`).

THE CHILD (`child`, started by `BOOT`): exactly the ops child's order (`league/ops/__main__.py`): THE LIMIT FIRST
(`limit(None, extra_mb)`: RLIMIT_AS = the address space now + `extra_mb`), then the job's imports, then the work: the
job's own `forward_screen.HouseRuns` making `calls` forward runs of the representative (its sides), `calls` placebo
legs and one own floor's two Train segments. What is real: the panel store, the panel night (`forward_xs.panel_shadow`)
and its runner, the House's side of the decider (`league.live.decider.Decider`: the pickle, the frame, the pipe, the
answer's JSON), the decider's own child process and its serve loop. What is not: the engine (a real run of three Train
years takes seconds and the cap is on the PARENT), so the child's `run_bars` is `canned`: it reads the bars it was sent
and answers a result of a real one's shape for the slice it was sent.

`mode` "as_it_was" is the job AS IT WAS: a panel store opened for every call (a `HouseRuns` made for each, as the
build opened one in each method). It does not fit, and the test holds that too, so the measurement is known to see
what it is for.

It prints one JSON line: what each call answered, the kernel's high-water mark of the address space and the cap.
Synthetic figures only; nothing here is market data.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

FIRST, LAST = dt.date(2016, 1, 4), dt.date(2026, 12, 15)
MEMBERS, CHURN, SEED = 505, 0.05, 11
BOOT = ("import sys; from league.ops import __main__ as ops; limits = ops.limit(None, int(sys.argv[2])); "
        "from league.tests import fwd1_panel_budget as B; B.child(sys.argv[1], sys.argv[3], int(sys.argv[4]), limits)")
STUB = ("import sys; sys.path.insert(0, {repo!r}); from league.tests import fwd1_panel_budget as B; B.serve()")
SWITCH_ON = '{"elane": {"mode": "gate", "panel": {"mode": "train"}, "forward": {"mode": "record"}}}'
KEY = "fwd1-mem@1"


def code() -> str:
    from league.tests import test_forward_xs as TX

    return TX.CODE


def build(state: Path) -> dict[str, int]:
    """The panel store on disk under `state`, the lane's switch up, and a forward record with one registered panel
    program (an invented row). Returns {"sessions", "columns", "pid"}."""
    import numpy as np

    from league.equity import results
    from league.ops import forward_db, forward_xs
    from league.xs import synth

    state.mkdir(parents=True, exist_ok=True)
    root = synth.synthetic_panel(state / "equity-daily", n_assets=MEMBERS, seed=SEED, churn=CHURN, gate=True,
                                 start=FIRST, end=LAST)
    (state / "swarm.json").write_text(SWITCH_ON, encoding="utf-8")
    text = code()
    needs = forward_xs.needs_of(text)
    first_day = forward_db.t0()
    db = forward_db.open_db(state)
    try:
        db.execute("INSERT INTO fwd_registry(pid, key, family, version, lane, reason, ugroup, lineage, code, params, "
                   "needs, program_sha, run_sha, author, created_at, evidence, first_close, first_day, registered_at, "
                   "route, alpha_f, prev_hash, row_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (1, KEY, "fwd1-mem", 1, "equity", "train_pass", "panel:sp500", "equity:fwd1-mem", text,
                    results.canonical({}), results.canonical(needs), hashlib.sha256(text.encode()).hexdigest(),
                    "r" * 64, "", 1.0, "registry", forward_db.t0().isoformat(), first_day.isoformat(), 1.0,
                    forward_db.XS_ROUTE, forward_db.E3_ALPHA_F, "0" * 64, "1" * 64))
        db.commit()
    finally:
        db.close()
    raw = np.load(Path(root) / "panel" / "raw.npy", mmap_mode="r")
    return {"sessions": int(raw.shape[0]), "columns": int(raw.shape[1]), "pid": 1}


def canned(code: str, params: Any, bars: Any, **kw: Any) -> dict[str, Any]:
    """`league.xs.runner.run_bars` without the engine: a result of a real run's shape for the slice it was sent (a
    daily row a run session, flat, a few lots), no decide timeout, "ok"; with placebos, their block on the run's
    sessions."""
    from league.equity.store import from_ordinal

    days = [from_ordinal(int(d)).isoformat() for d in list(bars.days)[int(bars.first):]]
    result: dict[str, Any] = {
        "status": "ok", "window": bars.window, "needs": {},
        "daily": [[day, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, False, 1000.0] for day in days],
        "lots": [{"aid": i, "entry_day": days[0], "exit_day": days[-1], "weight": 0.1, "x": 0.0} for i in range(8)],
        "picks": [{"decided": day, "called": 1, "ctx_sha": "0" * 64, "targets": list(range(8))} for day in days[::5]],
        "runtime": {"calls": max(1, len(days) // 5), "errors": 0, "timeouts": 0, "disqualified": None,
                    "decide_seconds": 0.1}}
    draws = int(kw.get("placebos") or 0)
    if draws:
        result["placebo"] = {"n": draws, "seed": kw.get("seed"), "rung": "R1", "lots": 8,
                             "spans": {"run": {"days": len(days), "t": [0.0] * draws}}}
    return result


def serve() -> None:  # pragma: no cover - the decider's child process
    """The decider child's own loop, its panel kind's engine `canned`."""
    from league.live import decider
    from league.xs import runner

    runner.run_bars = canned
    decider._serve(sys.stdin.buffer, sys.stdout.buffer)


def vm_mb(field: str) -> int:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith(field + ":"):
            return int(line.split()[1]) // 1024
    return 0


def child(state: str, mode: str, calls: int, limits: dict[str, Any]) -> None:  # pragma: no cover - a subprocess
    """`calls` forward runs and `calls` placebo legs of the one panel representative and one own floor's Train
    segments through the job's `HouseRuns` on the store at `state` (`mode` "job": one `HouseRuns`, as the job holds one
    a run; "as_it_was": a store opened for every call), and the one JSON line."""
    import sqlite3
    import tempfile

    from league.live.decider import Decider
    from league.ops import forward_db
    from league.ops import forward_screen as FS

    repo = str(Path(__file__).resolve().parents[2])
    tmp = Path(tempfile.mkdtemp(prefix="fwd1-mem-"))
    python = tmp / "python"
    python.write_text("#!/bin/sh\nexec " + json.dumps(sys.executable) + " -c " + json.dumps(STUB.format(repo=repo))
                      + "\n", encoding="utf-8")
    python.chmod(python.stat().st_mode | stat.S_IXUSR)
    decider = Decider(python=str(python), allow_unisolated=True)
    root = Path(state)
    settings = json.loads((root / "swarm.json").read_text())
    fdb = forward_db.open_db(root, readonly=True)
    fdb.row_factory = sqlite3.Row
    program = forward_db.program(fdb, KEY)
    out: dict[str, Any] = {"mode": mode, "answers": [], "error": None}
    held: list[Any] = []

    def make() -> Any:
        return FS.HouseRuns(root, budget_seconds=120.0, decider=decider, fdb=fdb, settings=settings)

    try:
        runs = make()
        start = program.first_day
        for i in range(calls):
            if mode == "as_it_was" and i:
                held.append(runs)           # the build's methods each opened a store and nothing collected it
                runs = make()
            try:
                found = runs.forward_sides(program, "PANEL", settings=settings, fdb=fdb)
                out["answers"].append(["sides", len(found["r"])])
                days = sorted(found["r"])
                block = runs.panel_placebo(program, start=start, end=dt.date.fromisoformat(days[-1]), seed=7)
                out["answers"].append(["placebo", block["days"]])
            except Exception as exc:  # noqa: BLE001 - the measurement's own answer
                out["answers"].append(["error", f"{type(exc).__name__}: {str(exc)[:160]}"])
        pools = runs.panel_pools(program)
        out["answers"].append(["pools", [None if p is None else len(p[0]) for p in pools]])
        out["opens"] = runs.opens + sum(r.opens for r in held)
        runs.close()
    except BaseException as exc:  # noqa: BLE001 - the measurement's own answer
        out["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    finally:
        try:
            decider.close()
        except Exception:  # noqa: BLE001
            pass
        fdb.close()
        try:
            os.unlink(python)
            os.rmdir(tmp)
        except OSError:
            pass
    out.update(vm_peak_mb=vm_mb("VmPeak"), cap_mb=int(limits.get("as_bytes") or 0) // 2 ** 20)
    print(json.dumps(out))


__all__ = ["FIRST", "LAST", "MEMBERS", "CHURN", "SEED", "BOOT", "STUB", "SWITCH_ON", "KEY", "code", "build", "canned",
           "serve", "vm_mb", "child"]
